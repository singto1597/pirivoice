"""
📤 Web Push — Outbox + Trigger (A3)
====================================
ไฟล์นี้พิสูจน์ "ท่อ" ทั้งเส้นของ A3 ที่ **ไม่ต้องมี backend จริงเลย**:
    notifications INSERT  →  (trigger)  →  push_outbox  →  worker claim  →  ส่ง

ทำไมไฟล์นี้สำคัญที่สุดในชุด A3
------------------------------
ดีไซน์ทั้งหมดของ A3 วางบนสมมติฐานเดียวว่า
    **"trigger `AFTER INSERT … FOR EACH ROW` ยิงครบทุกลายที่ insert"**
รวมถึงเส้นทางที่ **ไม่ใช่ INSERT ธรรมดา**:
  - `notify_bulk()` ใช้ `conn.executemany()`  → asyncpg ห่อเป็น pipeline
  - `notify_fanout()` ใช้ `INSERT … SELECT`   → หลายแถวจากคำสั่งเดียว

ถ้าสมมติฐานนี้ผิด (เช่น executemany ไม่ยิง row trigger ต่อแถว) ระบบจะ **ดูปกติทุกอย่าง**
— in-app notification ยังขึ้นครบ — แต่ **ไม่มี push ออกไปเลยแม้แต่ครั้งเดียว**
โดยไม่มี error ที่ไหนให้เห็น ⇒ ต้องพิสูจน์ด้วยเทสต์ ไม่ใช่ด้วยการอ่านเอกสาร

ตาม docs/rules/testing.md: ทุกเทสต์ยืนยัน DB ตรง ๆ ผ่าน db_pool ไม่เชื่อ response
"""
import base64
import importlib
import random

import pytest
import pytest_asyncio

from core.config import settings
from services import auth_service, notification_service, push_service


# ============================================================
# Fixtures / helpers
# ============================================================

@pytest_asyncio.fixture
async def push_world(db_pool):
    """3 active students ในห้องเดียว — พอสำหรับ notify 1 คน / bulk 3 คน / fanout 3 คน"""
    room_code = f"บ.{random.randint(1, 90)}"
    async with db_pool.acquire() as conn:
        room_id = await conn.fetchval(
            "INSERT INTO rooms (room_code, room_name, level) VALUES ($1,$2,'ม.5') RETURNING id",
            room_code, room_code,
        )

    users = {}
    for label, no in [("student", 1), ("student2", 2), ("student3", 3)]:
        sid = f"P{random.randint(1000, 9999)}{label[:2].upper()}"
        uid = await auth_service.register_user(
            db_pool, sid, "1234", f"{label} ทดสอบ", sid, room_code, no, "student"
        )
        users[label] = {
            "user_id": uid,
            "token": auth_service.create_access_token(uid),
            "room_id": room_id,
        }
    return users


@pytest.fixture(autouse=True)
def vapid_configured(monkeypatch):
    """ตั้งคีย์ VAPID ให้ทุกเทสต์ในไฟล์นี้ — **จำเป็น ไม่ใช่ของประดับ**

    ⚠️ `process_pending()` มีด่านแรกคือ "ไม่มีคีย์ = ปิดทั้งคิว" (§20.11 กับดัก 9)
       ⇒ ถ้าไม่ตั้งคีย์ ทุกเทสต์จะ **หยุดที่ด่านนั้นแล้วไม่ทดสอบอะไรที่ตั้งใจเลย**
       และดูเหมือน "ผ่าน" เพราะ stats ว่างเปล่า (ถูกจับได้ตอนรันครั้งแรก: 6 เทสต์ล้ม
       ด้วย `stats["stale"] == 0`, `sender.calls == []` ทั้งที่เหตุจริงคือไม่มีคีย์)

    ใช้สตริงปลอมได้ เพราะทุกเทสต์ในไฟล์นี้ **แทน sender ด้วยของปลอม** ⇒ `_send_one()`
    (ที่เดียวที่แตะคีย์จริง) ไม่ถูกเรียกเลย · ส่วนความถูกต้องของ *รูปแบบ* คีย์
    ถูกตรวจแล้วใน `scripts/generate_vapid_keys.py` ซึ่งมีด่าน 3 ชั้นก่อนพิมพ์ออกมา
    (round-trip ผ่าน `Vapid02.from_string` · public ตรงกับที่deriveจาก private · sign() ได้จริง)
    """
    monkeypatch.setattr(settings, "VAPID_PUBLIC_KEY", "test-public-key")
    monkeypatch.setattr(settings, "VAPID_PRIVATE_KEY", "test-private-key")
    push_service._reset_vapid_cache()
    yield
    push_service._reset_vapid_cache()


def _auth(world, who="student"):
    return {"Authorization": f"Bearer {world[who]['token']}"}


async def _outbox_rows(db_pool):
    async with db_pool.acquire() as conn:
        return await conn.fetch("SELECT * FROM push_outbox ORDER BY id")


async def _count(db_pool, table: str, where: str = "TRUE", *params) -> int:
    async with db_pool.acquire() as conn:
        return await conn.fetchval(f"SELECT COUNT(*) FROM {table} WHERE {where}", *params)


async def _notify_one(db_pool, *, user_id, group_type="issue_mine", actor_id=None):
    """เรียก notification_service.notify() ให้ถูกสัญญา — conn ต้องอยู่ใน transaction ของ caller"""
    async with db_pool.acquire() as conn:
        async with conn.transaction():
            await notification_service.notify(
                conn,
                user_id=user_id, group_type=group_type, type="issue_update",
                title="ทดสอบ", body="ข้อความทดสอบ",
                entity_type="issue", entity_id=999001, actor_id=actor_id,
            )


# ============================================================
# 1) Trigger ยิงจริงในทุกรูปแบบการ insert   ← 🚧 ด่านสำคัญที่สุดของ A3
# ============================================================

@pytest.mark.asyncio
async def test_T1_trigger_enqueues_on_plain_insert(push_world, db_pool):
    """INSERT ตรง ๆ 1 แถว → outbox ได้ 1 แถว

    mutation ที่ต้องทำให้แตก: ลบ `CREATE TRIGGER` ใน migration 018 → outbox = 0
    """
    uid = push_world["student"]["user_id"]
    await _notify_one(db_pool, user_id=uid)

    rows = await _outbox_rows(db_pool)
    assert len(rows) == 1
    assert rows[0]["user_id"] == uid
    # ⭐ outbox ต้องมี FK ชี้ notification จริง (ไม่ใช่แถวลอย)
    assert rows[0]["notification_id"] is not None
    assert rows[0]["processed_at"] is None
    assert rows[0]["attempts"] == 0


@pytest.mark.asyncio
async def test_T2_trigger_is_after_insert_so_id_is_filled(push_world, db_pool):
    """`notification_id` ต้องเป็น id จริง ไม่ใช่ NULL — พิสูจน์ว่าเป็น AFTER ไม่ใช่ BEFORE

    ⚠️ ถ้าเปลี่ยน trigger เป็น `BEFORE INSERT` ค่า NEW.id จะยังไม่ถูก allocate
       ⇒ notification_id = NULL (หรือ FK violation) · เทสต์นี้จับได้ทันที
    """
    uid = push_world["student"]["user_id"]
    await _notify_one(db_pool, user_id=uid)

    async with db_pool.acquire() as conn:
        notif_id = await conn.fetchval("SELECT id FROM notifications LIMIT 1")
        row = await conn.fetchrow(
            """
            SELECT o.notification_id, n.user_id AS notif_user_id
            FROM push_outbox o JOIN notifications n ON n.id = o.notification_id
            LIMIT 1
            """
        )
    assert row is not None, "JOIN ไม่เจอ ⇒ notification_id ไม่ตรงกับ notifications.id"
    assert row["notification_id"] == notif_id
    assert row["notif_user_id"] == uid


@pytest.mark.asyncio
async def test_T3_pref_gate_applies_before_outbox(push_world, db_pool):
    """ปิดกลุ่มไว้ → ทั้ง `notifications` และ `push_outbox` ต้องเป็น 0

    ⭐ นี่คือเทสต์ที่พิสูจน์ว่า **ไม่ต้องใส่ pref gate ซ้ำใน trigger**
       `notify()` กรองก่อน insert อยู่แล้ว ⇒ outbox จึงว่างตามไปเอง
       ถ้ามีคนเผลอ insert notification ตรง ๆ ข้าม `notify*` เทสต์นี้จะยังเขียว
       (เพราะมันทดสอบเส้นทางปกติ) — ความเสี่ยงนั้นถูกบันทึกไว้ใน docstring ของ trigger

    mutation ที่ต้องทำให้แตก: ย้าย pref gate ไปทำที่ trigger แทน (จะได้ 0/1 สลับกัน)
        หรือใส่ trigger ที่ bypass gate
    """
    uid = push_world["student"]["user_id"]
    await notification_service.update_preferences(
        db_pool, uid, [{"group_type": "issue_mine", "enabled": False}]
    )

    await _notify_one(db_pool, user_id=uid)

    assert await _count(db_pool, "notifications") == 0
    assert await _count(db_pool, "push_outbox") == 0


@pytest.mark.asyncio
async def test_T4_trigger_fires_for_executemany_in_notify_bulk(push_world, db_pool):
    """★ notify_bulk (3 คน) → notifications 3 **และ** outbox 3

    ⚠️ **นี่คือสมมติฐานที่ทั้ง A3 ยืนอยู่** — asyncpg ส่ง `executemany` เป็น pipeline
       (คำสั่งเดียวหลายชุดพารามิเตอร์) ถ้า PostgreSQL ไม่ยิง row trigger ต่อชุด
       เราจะได้ outbox = 0 ทั้งที่ notifications = 3
       ⇒ ในแอพจริง: "มีคนตอบเรื่องของฉัน" เด้งในแอพแต่ **ไม่เคยเด้งถึงมือถือ**
         และไม่มี error ที่ไหนให้เห็นเลย — เป็นบั๊กที่แพงที่สุดของ A3

    mutation ที่ต้องทำให้แตก: เปลี่ยน `FOR EACH ROW` เป็น `FOR EACH STATEMENT`
        (จะได้ outbox = 1 ไม่ใช่ 3) · หรือลบ trigger (ได้ 0)
    """
    ids = [push_world[k]["user_id"] for k in ("student", "student2", "student3")]
    uid, uid2, uid3 = ids

    async with db_pool.acquire() as conn:
        async with conn.transaction():
            await notification_service.notify_bulk(
                conn, [uid, uid2, uid3],
                group_type="issue_received", type="issue_new",
                title="เรื่องใหม่", body="มีเรื่องใหม่ในห้อง",
                entity_type="issue", entity_id=999002,
            )

    assert await _count(db_pool, "notifications") == 3
    assert await _count(db_pool, "push_outbox") == 3, (
        "executemany ไม่ยิง row trigger ⇒ push จะไม่ทำงานเลยในเส้นทาง notify_bulk"
    )

    # จับคู่ถูกคน ไม่ใช่แค่ถูกจำนวน
    async with db_pool.acquire() as conn:
        outbox_users = {
            r["user_id"] for r in await conn.fetch("SELECT user_id FROM push_outbox")
        }
    assert outbox_users == set(ids)


@pytest.mark.asyncio
async def test_T5_trigger_fires_for_insert_select_in_notify_fanout(push_world, db_pool):
    """★ notify_fanout (ทุก active student) → จำนวน outbox = จำนวน notifications

    ⚠️ เส้นทางนี้ใช้ `INSERT … SELECT` ซึ่งสร้างหลายแถวจากคำสั่งเดียว — เหมือน T4
       แต่ต่างกลไก ⇒ ต้องพิสูจน์แยก ไม่ใช่เหมาว่า "T4 ผ่านก็พอ"

    ⚠️ `notify_fanout` คือ **เส้นทางที่ดังที่สุดในระบบ**: อนุมัติบอร์ด 1 ใบ =
       push หาทุก active student (ระดับโรงเรียน 800–1,000 คน) · ดูความเสี่ยงเชิงสังคม
       ในแผน §20.14 ข้อ 7 — เทสต์นี้ยืนยันว่ามันทำงาน *จริง* ไม่ได้ตัดสินว่าควรทำหรือไม่
    """
    push_world  # สร้าง 3 students (active) — fanout ยิงหาทุกคนในตาราง students

    async with db_pool.acquire() as conn:
        async with conn.transaction():
            await notification_service.notify_fanout(
                conn,
                group_type="board", type="board_new",
                title="บอร์ดใหม่", body="มีบอร์ดใหม่ให้โหวต",
                entity_type="board", entity_id=999003,
            )

    notif_count = await _count(db_pool, "notifications")
    outbox_count = await _count(db_pool, "push_outbox")
    assert notif_count == 3
    assert outbox_count == 3, (
        "INSERT … SELECT ไม่ยิง row trigger ⇒ อนุมัติบอร์ดแล้วไม่มี push ถึงใครเลย"
    )

    # ทุกแถว outbox ต้องชี้ notification ที่เป็นของผู้ใช้คนเดียวกัน (ไม่สลับคู่)
    async with db_pool.acquire() as conn:
        mismatched = await conn.fetchval(
            """
            SELECT COUNT(*) FROM push_outbox o
            JOIN notifications n ON n.id = o.notification_id
            WHERE n.user_id <> o.user_id
            """
        )
    assert mismatched == 0


# ============================================================
# 2) Worker — claim / ส่ง / retry / เก็บกวาด
#     ⚠️ ทุกเทสในส่วนนี้ใช้ **sender ปลอม** — ห้ามมีเทสที่ยิง HTTP ออกเน็ตจริง
#        (plan §20.14 ข้อ 6)
# ============================================================

async def _subscribe(db_pool, user_id: int, *, endpoint: str = None) -> str:
    """สร้างปลายทาง push ปลอมสำหรับ user 1 คน — คืน endpoint ที่ใช้"""
    endpoint = endpoint or f"https://fcm.googleapis.com/fcm/send/{random.randint(10**9, 10**10)}"
    async with db_pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO push_subscriptions (user_id, endpoint, p256dh, auth)
               VALUES ($1, $2, $3, $4)""",
            user_id, endpoint,
            base64.urlsafe_b64encode(b"x" * 65).decode().rstrip("="),
            base64.urlsafe_b64encode(b"y" * 16).decode().rstrip("="),
        )
    return endpoint


def _recorder(status=201):
    """sender ปลอม — บันทึกทุกครั้งที่ถูกเรียก แล้วคืน status ที่กำหนด

    `status` รับได้ทั้ง int และ callable(sub)->int (สำหรับเทสหลายอุปกรณ์ที่ต้อง
    ให้ผลต่างกันตาม endpoint)
    """
    calls = []

    async def send(client, sub, payload, *, ttl):
        calls.append({"sub": sub, "payload": payload, "ttl": ttl})
        return status(sub) if callable(status) else status

    send.calls = calls
    return send


async def _outbox_row(db_pool, outbox_id: int):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM push_outbox WHERE id = $1", outbox_id)


async def _single_outbox_id(db_pool) -> int:
    async with db_pool.acquire() as conn:
        return await conn.fetchval("SELECT id FROM push_outbox ORDER BY id LIMIT 1")


@pytest.mark.asyncio
async def test_T7_claim_is_single_flight(push_world, db_pool):
    """claim รอบสองต้องไม่ได้แถวเดิมซ้ำ — ไม่งั้นผู้ใช้ได้ push ซ้ำสองอัน

    ⚠️ สองอย่างที่กันซ้ำคนละชั้น และ **ต้องมีทั้งคู่**:
       1. `processing_at IS NULL` ในคิวรี claim — กัน worker อีกตัวหยิบแถวที่
          กำลังส่งอยู่ (แถวนั้นยัง `processed_at IS NULL` + `next_attempt_at <= NOW()`)
       2. `FOR UPDATE SKIP LOCKED` — กันสอง transaction ล็อกแถวเดียวกัน

    mutation ที่ต้องทำให้แตก: ลบ `processing_at IS NULL` → รอบสองได้แถวเดิม
    """
    uid = push_world["student"]["user_id"]
    await _notify_one(db_pool, user_id=uid)

    first = await push_service._claim(db_pool, 100)
    assert len(first) == 1
    assert first[0]["attempts"] == 1  # claim นับ attempt ให้ด้วย

    second = await push_service._claim(db_pool, 100)
    assert second == [], "claim ซ้ำได้แถวเดิม ⇒ push ซ้ำถึงผู้ใช้"


@pytest.mark.asyncio
async def test_T7b_concurrent_claims_get_disjoint_rows(push_world, db_pool):
    """★ สอง claim พร้อมกัน (batch 3 จากของ 5) → union = 5 และ **ไม่ทับกัน**

    นี่คือคุณสมบัติที่กัน push ซ้ำเมื่อมี worker หลายตัว/replica หลายตัว
    (`FOR UPDATE SKIP LOCKED`)

    ⚠️ เขียนตามจริง: เทสต์นี้พิสูจน์ **ความไม่ทับกัน** ไม่ได้พิสูจน์ว่า
       `SKIP LOCKED` ถูกใช้ — ถ้าลบ `SKIP LOCKED` ออก ตัวที่สองจะ *บล็อกรอ* แล้ว
       พอคิวแรก commit ก็เห็น `processing_at` ถูกตั้งแล้วจึงได้แถวอื่น ⇒ เทสต์ยังเขียว
       (สิ่งที่เสียไปคือ *เวลา* ไม่ใช่ *ความถูกต้อง*) — คอมเมนต์ไว้เพื่อไม่ให้เข้าใจผิด
    """
    ids = [push_world[k]["user_id"] for k in ("student", "student2", "student3")]
    for uid in ids:
        await _notify_one(db_pool, user_id=uid, group_type="issue_mine")
    await _notify_one(db_pool, user_id=ids[0], group_type="issue_received")
    await _notify_one(db_pool, user_id=ids[1], group_type="board")

    import asyncio
    a, b = await asyncio.gather(
        push_service._claim(db_pool, 3),
        push_service._claim(db_pool, 3),
    )

    got = [r["id"] for r in a] + [r["id"] for r in b]
    assert len(got) == 5, f"ของ 5 แถวต้องถูกจองครบ 5 (ได้ {len(got)})"
    assert len(set(got)) == 5, "สอง claim ได้แถวทับกัน ⇒ push ซ้ำ"


@pytest.mark.asyncio
async def test_T8_no_subscription_marks_processed_and_never_sends(push_world, db_pool):
    """ผู้ใช้ที่ยังไม่เปิด push → ปิดแถวทันที และ **ไม่เรียก sender เลย**

    ⚠️ ถ้าใช้ INNER JOIN แทน LEFT JOIN แถวนี้จะ **หายจากผลลัพธ์** แล้วค้าง
       `processed_at IS NULL` ตลอดกาล — คิวโตขึ้นเรื่อย ๆ โดยที่ทุกอย่างดูปกติ
       (เทสต์นี้จับด้วยการ assert `processed_at IS NOT NULL`)

    mutation ที่ต้องทำให้แตก: เปลี่ยน LEFT JOIN เป็น INNER JOIN → processed_at ยัง NULL
    """
    uid = push_world["student"]["user_id"]
    await _notify_one(db_pool, user_id=uid)  # ⚠️ ไม่มี _subscribe

    sender = _recorder()
    stats = await push_service.process_pending(db_pool, sender=sender)

    assert sender.calls == [], "ไม่มีปลายทาง แต่ sender ถูกเรียก"
    assert stats["skipped"] == 1
    row = await _outbox_row(db_pool, await _single_outbox_id(db_pool))
    assert row["processed_at"] is not None, "แถวค้างในคิวตลอดกาล"
    assert row["last_error"] is None


@pytest.mark.asyncio
async def test_T9_gone_410_deletes_subscription(push_world, db_pool):
    """404/410 = อุปกรณ์ตายแล้ว → ลบ subscription ทิ้ง + ปิดแถว

    ⚠️ ถ้าไม่ลบ ปลายทางที่ตายจะถูกยิงซ้ำ **ทุกครั้งที่มี notification ใหม่**
       ตลอดไป — เปลืองและทำให้ log เต็มไปด้วย 410

    mutation ที่ต้องทำให้แตก: ลบ `delete_subscriptions_by_id` ออก → แถวยังอยู่ (count 1)
    """
    uid = push_world["student"]["user_id"]
    await _subscribe(db_pool, uid)
    await _notify_one(db_pool, user_id=uid)

    sender = _recorder(status=410)
    stats = await push_service.process_pending(db_pool, sender=sender)

    assert len(sender.calls) == 1
    assert stats["gone"] == 1
    assert await _count(db_pool, "push_subscriptions") == 0, "ปลายทางตายไม่ถูกลบ"
    row = await _outbox_row(db_pool, await _single_outbox_id(db_pool))
    assert row["processed_at"] is not None, "410 แล้วยัง retry = ยิงซ้ำตลอดกาล"


@pytest.mark.asyncio
async def test_T10_server_error_schedules_retry(push_world, db_pool):
    """5xx / network ล่ม → **ไม่** ปิดแถว แต่เลื่อนไปรอบหน้า

    mutation ที่ต้องทำให้แตก: mark processed ทันทีไม่ว่า status ไหน → ไม่มี retry
    """
    uid = push_world["student"]["user_id"]
    await _subscribe(db_pool, uid)
    await _notify_one(db_pool, user_id=uid)

    sender = _recorder(status=503)
    stats = await push_service.process_pending(db_pool, sender=sender)

    assert stats["retry"] == 1
    row = await _outbox_row(db_pool, await _single_outbox_id(db_pool))
    assert row["processed_at"] is None, "5xx แล้วปิดแถว = push หายถาวร"
    assert row["attempts"] == 1
    assert row["processing_at"] is None, "ไม่ล้าง processing_at = แถวค้าง ไม่มีใครหยิบได้อีก"
    assert row["last_error"] == "send-failed"

    async with db_pool.acquire() as conn:
        later = await conn.fetchval("SELECT next_attempt_at > NOW() FROM push_outbox WHERE id = $1", row["id"])
    assert later is True, "next_attempt_at ต้องเป็นอนาคต ไม่งั้นรอบถัดไปหยิบทันที (busy loop)"


@pytest.mark.asyncio
async def test_T11_retry_gives_up_after_max_attempts(push_world, db_pool):
    """ลองครบ `PUSH_MAX_ATTEMPTS` แล้ว → ปิดแถวถาวร ไม่ retry ไม่จบ

    ตั้ง `attempts` ให้ถึงเพดานก่อน (claim จะบวกอีก 1) ⇒ รอบนี้ต้องเป็นรอบสุดท้าย

    mutation ที่ต้องทำให้แตก: ลบด่าน `attempts >= PUSH_MAX_ATTEMPTS` → retry ไม่มีวันจบ
    """
    uid = push_world["student"]["user_id"]
    await _subscribe(db_pool, uid)
    await _notify_one(db_pool, user_id=uid)

    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE push_outbox SET attempts = $1", settings.PUSH_MAX_ATTEMPTS
        )

    sender = _recorder(status=500)
    stats = await push_service.process_pending(db_pool, sender=sender)

    # ⭐ `retry` กับ `dropped` ต้องแยกกัน — `retry` = "จะลองอีก", `dropped` = "ยอมแพ้แล้ว"
    #    (เวอร์ชันแรกของ service นับรวมกัน ⇒ log บอก "เลื่อนส่ง" ทั้งที่ของถูกทิ้งถาวร
    #     เทสต์นี้คือตัวที่จับได้ — ดูคอมเมนต์ใน `_retry_later`)
    assert stats["retry"] == 0, "ถึงเพดานแล้วต้องไม่ถูกนับเป็น 'จะลองอีก'"
    assert stats["dropped"] == 1, "push ที่ยอมแพ้ต้องถูกนับแยก ไม่งั้นของหายเงียบ" 
    row = await _outbox_row(db_pool, await _single_outbox_id(db_pool))
    assert row["processed_at"] is not None, "ถึงเพดานแล้วยังไม่ปิด = วนไม่จบ"
    assert "max-attempts" in row["last_error"]


@pytest.mark.asyncio
async def test_T12_stale_notification_is_not_pushed(push_world, db_pool):
    """notification เก่ากว่า `PUSH_MAX_AGE_MINUTES` → ทิ้ง ไม่ส่ง

    ⏰ สถานการณ์จริง: worker ล่มไป 3 ชั่วโมงแล้วกลับมา — คิวมีแจ้งเตือนเก่าค้าง
       หลายพันอัน ถ้าส่งหมดผู้ใช้จะได้ push พรวดเดียวเต็มหน้าจอ ("push storm")
       ซึ่งเป็นอาการที่ทำให้คนปิดการแจ้งเตือนถาวร

    mutation ที่ต้องทำให้แตก: ลบด่าน stale → sender ถูกเรียก + stats["stale"] == 0
    """
    uid = push_world["student"]["user_id"]
    await _subscribe(db_pool, uid)
    await _notify_one(db_pool, user_id=uid)

    minutes = settings.PUSH_MAX_AGE_MINUTES + 5
    async with db_pool.acquire() as conn:
        # ⚠️ backdate ที่ `notifications.created_at` (ไม่ใช่ที่ outbox) เพราะ
        #    ด่าน stale อ่านเวลาของ *การแจ้งเตือน* — คิวห่างจากเหตุการณ์ได้
        await conn.execute(
            f"UPDATE notifications SET created_at = NOW() - INTERVAL '{minutes} minutes'"
        )

    sender = _recorder()
    stats = await push_service.process_pending(db_pool, sender=sender)

    assert sender.calls == [], "ส่งแจ้งเตือนเก่า = push storm"
    assert stats["stale"] == 1
    row = await _outbox_row(db_pool, await _single_outbox_id(db_pool))
    assert row["processed_at"] is not None
    assert row["last_error"] == "stale"


@pytest.mark.asyncio
async def test_T13_recover_clears_stuck_processing_at(push_world, db_pool):
    """กู้แถวที่ถูก claim ค้าง (worker ตายหลัง claim ก่อนจดผล)

    ⚠️ นี่คือด่านที่ขาดไม่ได้: คิวรี claim กรอง `processing_at IS NULL`
       ⇒ แถวที่ค้างจะ **ไม่มีวันถูกหยิบอีกเลย** — push หยุดเงียบ ๆ ไม่มี error ที่ไหน

    ⭐ เทสต์นี้ **จับบั๊กจริงได้ตอนรันครั้งแรก**: เวอร์ชันแรกผมใช้เกณฑ์
       `PUSH_MAX_AGE_MINUTES` (15 นาที) เป็นเกณฑ์กู้ด้วย ⇒ กู้ได้แต่แถวนั้นจะถูก
       mark `stale` ทันทีในรอบเดียวกัน = **ไม่เคยกู้ push ถึงมือใครได้เลย**
       (assert ตัวสุดท้ายนี้คือตัวที่จับ — "กู้แล้วต้องหยิบได้ **และส่งได้**")

    mutation ที่ต้องทำให้แตก: ให้ `recover_stale_outbox` คืน 0 เสมอ → แถวค้างตลอดกาล
    """
    uid = push_world["student"]["user_id"]
    await _subscribe(db_pool, uid)
    await _notify_one(db_pool, user_id=uid)

    outbox_id = await _single_outbox_id(db_pool)
    stuck_for = settings.PUSH_RECOVER_MINUTES + 1
    async with db_pool.acquire() as conn:
        await conn.execute(
            f"""UPDATE push_outbox
                   SET processing_at = NOW() - INTERVAL '{stuck_for} minutes'
                 WHERE id = $1""",
            outbox_id,
        )

    # แถวนี้ต้องหยิบไม่ได้ก่อนกู้
    assert await push_service._claim(db_pool, 100) == []

    assert await push_service.recover_stale_outbox(db_pool) == 1

    row = await _outbox_row(db_pool, outbox_id)
    assert row["processing_at"] is None

    # ★ ครึ่งหลังสำคัญกว่าครึ่งแรก: กู้คืนมาต้อง **ส่งได้จริง** ไม่ใช่ถูกทิ้งเป็น stale
    sender = _recorder()
    stats = await push_service.process_pending(db_pool, sender=sender)
    assert stats["stale"] == 0, (
        "🚨 กู้คืนมาแล้วยังถูก mark stale ⇒ เกณฑ์กู้ >= เกณฑ์ stale "
        "(PUSH_RECOVER_MINUTES ต้องน้อยกว่า PUSH_MAX_AGE_MINUTES)"
    )
    assert len(sender.calls) == 1, "กู้คืนมาแล้วต้องได้ส่งจริง"


def test_T13b_recover_window_is_shorter_than_staleness_window():
    """🚨 กันคนตั้งค่าเพี้ยนในอนาคต: `PUSH_RECOVER_MINUTES < PUSH_MAX_AGE_MINUTES`

    ถ้าเท่ากันหรือมากกว่า ด่านกู้จะกลายเป็นพิธีกรรม — กู้แถวคืนมาแล้วรอบเดียวกัน
    mark ทิ้งเป็น stale ⇒ **push หายเงียบ ๆ โดยไม่มี error** และเทสต์ T13
    จะเป็นตัวเดียวที่จับได้ (และต้องมีคนรันมัน)
    """
    assert settings.PUSH_RECOVER_MINUTES < settings.PUSH_MAX_AGE_MINUTES, (
        "เกณฑ์กู้ต้องสั้นกว่าเกณฑ์ stale ไม่งั้นกู้คืนมาแล้วถูกทิ้งทันที"
    )


@pytest.mark.asyncio
async def test_T14_cleanup_never_deletes_pending(push_world, db_pool):
    """ลบเฉพาะแถวที่ **จบแล้ว** และเก่ากว่า N วัน — ของค้างต้องรอด

    🚨 อันตรายที่สุดในไฟล์นี้: ถ้าแถวที่ยัง **ไม่ได้ส่ง** ถูกลบ ⇒ **push หายเงียบ ๆ**
       โดยไม่มีร่องรอยเลย (ไม่มี error, ไม่มี log, ผู้ใช้แค่ไม่ได้รับการแจ้งเตือน)

    ⚠️ **แก้ความเข้าใจผิดของผมเอง (พิสูจน์ด้วย mutation แล้ว):** ผมเคยเขียนใน
       docstring นี้ว่า "ลบ `processed_at IS NOT NULL` แล้วเทสต์จะล้ม" — **ไม่จริง**
       เพราะ `NULL < timestamp` ใน SQL ประเมินเป็น `NULL` (ไม่ใช่ TRUE) ⇒ แถวที่ยัง
       ไม่ได้ส่ง **ไม่ถูกแตะอยู่ดี** จากเงื่อนไขตัวที่สอง
       ⇒ `processed_at IS NOT NULL` เป็น *defense-in-depth + เอกสารเจตนา* ไม่ใช่ด่านหลัก
       (ทดสอบแล้ว: ลบออก → เทสต์ยัง PASS)

    ⭐ **เงื่อนไขที่รับน้ำหนักจริงคือ `processed_at < ...`** ⇒ mutation ที่ต้องทำให้แตก
       คือเปลี่ยนคีย์เวลาจาก `processed_at` เป็น `created_at` (ซึ่งคือรูปที่คนเขียน
       "ลบของเก่ากว่า 7 วัน" มักเผลอเขียน) — ตรวจแล้วว่าเทสต์ล้มจริง
    """
    uid = push_world["student"]["user_id"]
    await _subscribe(db_pool, uid)

    # ① ค้างอยู่ (ยังไม่ส่ง) ② จบแล้วและเก่า ③ จบแล้วและใหม่
    await _notify_one(db_pool, user_id=uid, group_type="issue_mine")
    await _notify_one(db_pool, user_id=uid, group_type="issue_received")
    await _notify_one(db_pool, user_id=uid, group_type="board")

    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT id FROM push_outbox ORDER BY id")
        await conn.execute(
            "UPDATE push_outbox SET processed_at = NOW() - INTERVAL '30 days' WHERE id = $1",
            rows[1]["id"],
        )
        await conn.execute(
            "UPDATE push_outbox SET processed_at = NOW() WHERE id = $1", rows[2]["id"]
        )

    deleted = await push_service.cleanup_outbox(db_pool, days=7)

    assert deleted == 1, "ต้องลบเฉพาะแถวที่จบแล้วและเก่าเกิน 7 วัน"
    assert await _count(db_pool, "push_outbox", "processed_at IS NULL") == 1, (
        "🚨 ลบแถวที่ยังไม่ได้ส่งทิ้ง = push หายเงียบ ๆ"
    )
    assert await _count(db_pool, "push_outbox") == 2


@pytest.mark.asyncio
async def test_T15_missing_vapid_key_drains_queue(push_world, db_pool, monkeypatch):
    """ไม่ได้ตั้งคีย์ VAPID → **ต้องปิดแถวทิ้ง** ไม่ใช่คืนเฉย ๆ

    ⚠️ ถ้า `return` เฉย ๆ โดยไม่ปิด คิวจะโตไม่หยุด: โรงเรียนใช้ระบบต่อทุกวัน
       แต่ไม่มีใครเก็บกวาด ⇒ `push_outbox` โตเป็นล้านแถวในไม่กี่เดือน และวันที่
       ใส่คีย์กลับ ผู้ใช้จะได้ push ย้อนหลังทั้งเทอม

    mutation ที่ต้องทำให้แตก: `return stats` ก่อน `_finish` → processed_at ยัง NULL
    """
    uid = push_world["student"]["user_id"]
    await _subscribe(db_pool, uid)
    await _notify_one(db_pool, user_id=uid)

    monkeypatch.setattr(settings, "VAPID_PUBLIC_KEY", "")
    monkeypatch.setattr(settings, "VAPID_PRIVATE_KEY", "")

    sender = _recorder()
    stats = await push_service.process_pending(db_pool, sender=sender)

    assert sender.calls == []
    assert stats["skipped"] == 1
    row = await _outbox_row(db_pool, await _single_outbox_id(db_pool))
    assert row["processed_at"] is not None, "ไม่มีคีย์แล้วปล่อยให้คิวโตไม่หยุด"
    assert row["last_error"] == "vapid-not-configured"


# ============================================================
# 3) ฟังก์ชันบริสุทธิ์ — ไม่ต้องมี DB เลย
# ============================================================

def test_T16a_build_payload_shape_matches_sw_js():
    """⭐ payload คือ **สัญญา** ระหว่าง backend กับ `frontend/public/sw.js`

    `sw.js` อ่าน `event.data.json()` แล้วใช้ `title` · `body` · `tag` · `data.url`
    ⇒ ถ้าที่นี่เปลี่ยนชื่อคีย์ `sw.js` จะพัง **โดยไม่มีอะไรจับได้ฝั่ง Python**
       (notification ยังขึ้นในแอพ แต่ push เงียบ) — เทสต์นี้คือด่านเดียว

    ⚠️ `data.url` ต้องเป็น `/app/notifications` **ไม่ใช่** `/notifications`
       เพราะ router ของ frontend มี redirect แบบ string ที่ทำ query หลุด (แผน §20.8)

    mutation ที่ต้องทำให้แตก: เปลี่ยนเป็น '/notifications' หรือเปลี่ยนชื่อคีย์ 'tag'
    """
    payload = push_service.build_payload({
        "notification_id": 42, "type": "issue_update",
        "title": "มีคนตอบเรื่องของคุณ", "body": "เรื่อง #12 ถูกตอบกลับแล้ว",
        "entity_type": "issue", "entity_id": 12, "board_id": None,
    })

    assert payload["title"] == "มีคนตอบเรื่องของคุณ"
    assert payload["body"] == "เรื่อง #12 ถูกตอบกลับแล้ว"
    assert payload["tag"] == "piri-notif-42", "tag ต้องไม่ซ้ำข้าม notification"
    assert payload["data"]["url"] == "/app/notifications"
    assert payload["data"]["notification_id"] == 42
    assert payload["data"]["entity_type"] == "issue"
    assert payload["data"]["entity_id"] == 12
    assert "board_id" in payload["data"]


def test_T16b_build_payload_tag_is_stable_per_notification():
    """notification เดียวกันสร้าง payload ซ้ำกี่ครั้งก็ได้ tag เดิม

    ⇒ มือถือจะ **แทนที่** notification เก่าของเรื่องเดียวกัน ไม่ขึ้นซ้อนกัน 5 อัน
    """
    row = {
        "notification_id": 7, "type": "board_new", "title": "t", "body": "b",
        "entity_type": "board", "entity_id": 1, "board_id": 1,
    }
    assert push_service.build_payload(row)["tag"] == push_service.build_payload(row)["tag"]


def test_T16c_decode_key_accepts_paddingless_base64url():
    """🔑 base64url ที่เบราว์เซอร์ส่งมา **ไม่มี `=` padding** และมี `-`/`_`

    ⚠️ นี่คือกับดักที่พังแบบเงียบ: `base64.urlsafe_b64decode` ตรง ๆ จะโยน
       `binascii.Error: Incorrect padding` สำหรับสตริงที่ความยาว % 4 != 0
       ⇒ ผู้ใช้บางคน subscribe ไม่ได้โดยไม่มีสาเหตุที่เห็นได้

    mutation ที่ต้องทำให้แตก: ลบ `_repad` → ข้อความ 43 ตัวอักษร (65-byte key) โยน error
    """
    # p256dh จริง = 65 byte uncompressed point → base64url 87 ตัวอักษร (87 % 4 == 3)
    raw_pub = bytes([4]) + bytes(range(64))
    encoded_pub = base64.urlsafe_b64encode(raw_pub).decode().rstrip("=")
    assert len(encoded_pub) % 4 != 0, "ตัวอย่างต้องไม่มี padding จริง ๆ ถึงจะทดสอบได้"
    assert push_service._decode_key(encoded_pub) == raw_pub

    # auth secret = 16 byte → 22 ตัวอักษร (22 % 4 == 2)
    raw_auth = b"\xfb\xff\x00\x01" * 4
    encoded_auth = base64.urlsafe_b64encode(raw_auth).decode().rstrip("=")
    assert push_service._decode_key(encoded_auth) == raw_auth


@pytest.mark.parametrize(
    "status,expected",
    [
        (201, "ok"), (200, "ok"), (204, "ok"),
        (404, "gone"), (410, "gone"),
        (429, "retry"),
        (400, "permanent"), (401, "permanent"), (413, "permanent"),
        (500, "retry"), (503, "retry"),
        (None, "retry"),          # network ล่ม / timeout
    ],
)
def test_T16d_classify_status(status, expected):
    """ตารางตัดสินว่าปลายทางตอบอะไรแล้วต้องทำยังไง — pure function

    ⚠️ 404/410 ต้องเป็น `gone` **ไม่ใช่** `permanent` เฉย ๆ เพราะ `gone` มีผล
       ข้างเคียงคือ **ลบ subscription** (ปลายทางตายแล้ว)

    mutation ที่ต้องทำให้แตก: ย้าย 404/410 ไปรวมกับ permanent → subscription ตายค้างถาวร
    """
    assert push_service._classify(status) == expected


# ============================================================
# 4) migration 018 — ⚠️ ต้องอยู่ท้ายไฟล์ (มัน DROP ตารางจริง)
# ============================================================

@pytest.mark.asyncio
async def test_T6_migration_018_is_idempotent_and_recreates_everything(push_world, db_pool):
    """จำลอง DB ที่ยังไม่มีตาราง → `upgrade()` **สองครั้ง** → ต้องได้ของครบ

    ⚠️ รันซ้ำต้องไม่ error — เส้นทางนี้เกิดจริง: `DROP TABLE` แล้ว `upgrade()` ซ้ำ
       ในเทสต์นี้เอง และในเทสต์ migration ไฟล์อื่น
       ⇒ `DROP TRIGGER IF EXISTS` ก่อน `CREATE TRIGGER` **จำเป็นจริง** เพราะ
         `CREATE TRIGGER` ไม่มี `IF NOT EXISTS` (PostgreSQL 16 มี `CREATE OR REPLACE
         TRIGGER` แต่โปรเจคเลือกแบบ DROP+CREATE เพื่อความชัด)

    mutation ที่ต้องทำให้แตก: ลบ `DROP TRIGGER IF EXISTS` → รอบสองโยน
       "trigger already exists" · ลบ `ON CONFLICT DO NOTHING` → รอบสองไม่มีอะไรพัง
       แต่ trigger จะ insert ซ้ำได้ (กันด้วย unique index อยู่ดี)
    """
    push_world
    mig = importlib.import_module("migrations.018_push_notifications")

    async with db_pool.acquire() as conn:
        # ⚠️ `notifications` ไม่ถูก drop — เก็บไว้ให้เทสต์ไฟล์ถัดไปใช้ต่อ
        await conn.execute("DROP TABLE IF EXISTS push_outbox CASCADE")
        await conn.execute("DROP TABLE IF EXISTS push_subscriptions CASCADE")

        assert await conn.fetchval(
            "SELECT to_regclass('public.push_outbox') IS NULL"
        ) is True, "ต้องลบตารางได้จริงก่อนทดสอบ"

        await mig.upgrade(conn)
        await mig.upgrade(conn)  # idempotent — รันซ้ำต้องไม่ error

        for tbl in ("push_subscriptions", "push_outbox"):
            assert await conn.fetchval(
                f"SELECT to_regclass('public.{tbl}') IS NOT NULL"
            ) is True, f"{tbl} ไม่ถูกสร้างคืน"

        indexes = {
            r["indexname"]
            for r in await conn.fetch(
                "SELECT indexname FROM pg_indexes WHERE tablename LIKE 'push%'"
            )
        }
        assert {
            "uq_push_subscriptions_endpoint",
            "idx_push_subscriptions_user",
            "uq_push_outbox_notification_user",
            "idx_push_outbox_pending",
        } <= indexes, f"index ขาด: {indexes}"

        # trigger ยังอยู่บน `notifications` (ไม่ถูก drop ไปกับตาราง push)
        assert await conn.fetchval(
            "SELECT COUNT(*) FROM pg_trigger WHERE tgname = 'trg_notifications_push_outbox'"
        ) == 1

        # ✅ พิสูจน์ว่า trigger ที่สร้างคืน **ทำงานจริง** ไม่ใช่แค่มองเห็นใน catalog
        #    (เป็นด่านสุดท้ายของไฟล์นี้ — ถ้า migration สร้าง trigger พลาด เทสต์ T1-T5
        #     ที่รันไปก่อนหน้าจะจับไม่ได้เลย เพราะตอนนั้น trigger ตัวเดิมยังอยู่)
        uid = push_world["student"]["user_id"]
        await _notify_one(db_pool, user_id=uid)
        assert await conn.fetchval("SELECT COUNT(*) FROM push_outbox") == 1
