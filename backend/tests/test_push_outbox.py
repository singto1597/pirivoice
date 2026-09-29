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

⚠️ **ตั้งแต่ migration 019 มีเงื่อนไขนำเพิ่มอีกข้อ** (เพิ่ม 28 ก.ย. 2026):
    **"ผู้รับต้องมีแถวใน `push_subscriptions` ก่อน notification จึงจะเข้าคิว"**
    ⇒ เทสต์ที่จะเห็น outbox เกิด **ต้องเรียก `_give_device()` ก่อนเสมอ**
    ถ้าลืม เทสต์จะได้ 0 แถวและแยกไม่ออกว่า "trigger พัง" หรือ "ยังไม่ได้ให้อุปกรณ์"
    (กับดักเดียวกับที่ T3 เคยตก — ดู docstring ของ T3 และ T5b)

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


async def _give_device(db_pool, *user_ids) -> None:
    """ให้ผู้รับมีอุปกรณ์ก่อน — **จำเป็นตั้งแต่ migration 019**

    ⚠️ trigger `push_outbox_enqueue()` กรองผู้ใช้ที่ไม่มีแถวใน `push_subscriptions`
       ทิ้ง (ประตูที่ 1 — ดู `migrations/019_push_outbox_requires_device.py`)
       ⇒ เทสต์ที่จะเห็น "outbox เกิดขึ้น" **ต้องให้ผู้รับมีอุปกรณ์ก่อนเสมอ**

    ถ้าลืม เทสต์จะได้ 0 แถวและ **อ่านไม่ออกว่า "trigger พัง" หรือ "ยังไม่ได้ให้อุปกรณ์"**
    — ซึ่งเป็นกับดักเดียวกับที่ T3 เคยตก (ดู docstring ของ T3) · เขียนเป็น helper
    ตัวเดียวเพื่อให้เจตนาปรากฏชัดในทุกเทสต์ ไม่ใช่ซ่อนอยู่ในการเรียก `_subscribe` ตรง ๆ

    (นิยามไว้ก่อน `_subscribe` โดยเจตนา — Python หา name ตอนเรียก ไม่ใช่ตอน parse
     และการวางไว้ตรงนี้ทำให้เห็นว่ามันเป็น **เงื่อนไขนำ** ของทุกเทสต์ในส่วนที่ 1)
    """
    for uid in user_ids:
        await _subscribe(db_pool, uid)


# ============================================================
# 1) Trigger ยิงจริงในทุกรูปแบบการ insert   ← 🚧 ด่านสำคัญที่สุดของ A3
# ============================================================

@pytest.mark.asyncio
async def test_T1_trigger_enqueues_on_plain_insert(push_world, db_pool):
    """INSERT ตรง ๆ 1 แถว → outbox ได้ 1 แถว

    mutation ที่ต้องทำให้แตก: ลบ `CREATE TRIGGER` ใน migration 018 → outbox = 0
    """
    uid = push_world["student"]["user_id"]
    await _give_device(db_pool, uid)  # ★ ประตู migration 019 — ขาดแล้วเทสต์นี้ได้ 0
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
    await _give_device(db_pool, uid)  # ★ ประตู migration 019
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

    🚨 **`_give_device()` ในเทสต์นี้คือหัวใจ ไม่ใช่ของประดับ** — ถ้าไม่ให้อุปกรณ์
       เทสต์จะได้ `0 / 0` **เพราะประตู migration 019** ไม่ใช่เพราะ pref gate ทำงาน
       ⇒ เทสต์จะ "ผ่าน" ทั้งที่ไม่ได้พิสูจน์อะไรเลย และจะกลายเป็นเทสต์หลอกที่
       ผ่านตลอดไปแม้มีคนลบ pref gate ออก (เป็นความผิดพลาดที่เงียบที่สุดของไฟล์นี้)
    """
    uid = push_world["student"]["user_id"]
    await _give_device(db_pool, uid)  # ★ ต้องมี — ไม่งั้นเทสต์นี้ผ่านด้วยเหตุผลผิด
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
    # ★ ทั้งสามคนต้องมีอุปกรณ์ (ประตู migration 019) — ไม่งั้นได้ 3 notifications / 0 outbox
    await _give_device(db_pool, *ids)

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
    # ★ ต้องมีอุปกรณ์ครบทั้งสาม (ประตู migration 019) — fanout กรอง "คนที่ไม่มีอุปกรณ์"
    #    ทิ้งที่ trigger ⇒ ถ้าไม่ให้ เทสต์นี้จะได้ 3 / 0 และอ่านผิดว่า INSERT…SELECT พัง
    await _give_device(db_pool, *[push_world[k]["user_id"] for k in ("student", "student2", "student3")])

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


@pytest.mark.asyncio
async def test_T5b_no_device_user_still_gets_in_app_but_no_outbox(push_world, db_pool):
    """★ ผู้ใช้ที่ไม่มีอุปกรณ์ → `notifications` 1 แถว แต่ `push_outbox` **0 แถว**

    นี่คือ **ประตูที่ 1** ของ migration 019 — ต้นเหตุจริงของอาการ "แจ้งเตือนช้า/กอง/หยุด"
    (28 ก.ย. 2026): คิวบน staging มี **3,239 แถว แต่มีปลายทางจริงแค่ 9 แถว (0.28%)**
    ⇒ worker เอาเวลาไปวนกับ 3,230 งานที่ **ทำไม่ได้** แล้วของจริง 9 ชิ้นไปถึงหัวคิว
      ตอนอายุเกิน `PUSH_MAX_AGE_MINUTES` ⇒ ถูกทิ้งเป็น `stale` เงียบ ๆ

    ⚠️ **in-app ต้องไม่หาย** — แถวใน `notifications` ถูก insert แล้ว (ผู้ใช้เห็นในแอพ)
       ประตูนี้ตัดแค่ "การเข้าคิว push" เท่านั้น ⇒ assert ทั้งสองฝั่งพร้อมกัน
       ถ้าเทสต์นี้เหลือแค่ `outbox == 0` มันจะผ่านแม้มีคนไปปิด `notify()` ทิ้งทั้งฟังก์ชัน

    mutation ที่ต้องทำให้แตก: ถอดประตู `has_device` ออกจาก `push_outbox_enqueue()`
        (เช่นรัน migration 018 ทับ) → outbox = 1
    """
    uid = push_world["student"]["user_id"]
    # ⚠️ ตั้งใจไม่เรียก _give_device — นั่นคือสาระของเทสต์นี้
    await _notify_one(db_pool, user_id=uid)

    assert await _count(db_pool, "notifications") == 1, "in-app ต้องยังได้ — ประตูนี้ตัดแค่ push"
    assert await _count(db_pool, "push_outbox") == 0, "ไม่มีปลายทางแต่ยังเข้าคิว = คิวท่วม"


@pytest.mark.asyncio
async def test_T5c_late_device_does_not_backfill_old_notifications(push_world, db_pool):
    """อุปกรณ์มาทีหลัง → ของเก่า **ไม่**ถูกตามเก็บย้อนหลัง แต่ของใหม่เข้าคิวปกติ

    ⭐ ทำไมต้องเป็นแบบนี้ (ไม่ใช่บั๊ก): "ตามเก็บย้อนหลัง" = ยิงแจ้งเตือนเก่าทั้งกอง
       พรวดเดียวตอนนักเรียนเพิ่งกดเปิดการแจ้งเตือน ⇒ **push storm ในวินาทีแรก**
       ซึ่งเป็นวิธีที่ทำให้คนปิดการแจ้งเตือนถาวร (เหตุผลเดียวกับ `PUSH_MAX_AGE_MINUTES`)
       · และมันทำไม่ได้ด้วยซ้ำ: trigger ยิงเฉพาะแถวใหม่ ⇒ ไม่มีกลไกให้ตามเก็บ

    ⚠️ เทสต์นี้กัน **การแก้ที่ดูฉลาดแต่ผิด** — ถ้าวันหน้ามีคนเพิ่ม backfill ใน
       migration (เช่น `INSERT INTO push_outbox SELECT … WHERE NOT EXISTS`) เทสต์นี้จะจับได้

    mutation ที่ต้องทำให้แตก: เพิ่ม backfill เข้า migration → แถวที่สองโผล่ทันที = 2
    """
    uid = push_world["student"]["user_id"]

    await _notify_one(db_pool, user_id=uid)  # ① ก่อนมีอุปกรณ์
    assert await _count(db_pool, "push_outbox") == 0

    await _give_device(db_pool, uid)  # ② เปิดการแจ้งเตือน (สายไปแล้วสำหรับใบแรก)
    assert await _count(db_pool, "push_outbox") == 0, "ห้ามตามเก็บของเก่า — จะเป็น push storm"

    await _notify_one(db_pool, user_id=uid)  # ③ ของใหม่ต้องเข้าคิวปกติ
    assert await _count(db_pool, "push_outbox") == 1


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
    await _give_device(db_pool, uid)  # ★ ประตู migration 019 — ไม่มีอุปกรณ์ = ไม่มีแถวให้ claim
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
    await _give_device(db_pool, *ids)  # ★ ประตู migration 019
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

    ⚠️ **ทำไมต้อง subscribe แล้วลบทิ้ง ไม่ใช่ "ไม่ subscribe เลย"** (แก้ 28 ก.ย. 2026):
       ตั้งแต่ migration 019 trigger กรองคนที่ไม่มีอุปกรณ์ **ออกตั้งแต่ยังไม่เข้าคิว**
       ⇒ "notify คนที่ไม่มีอุปกรณ์" สร้าง **0 แถว** ไม่ใช่ 1 แถวที่ต้องมาทิ้งทีหลัง
       การไม่ subscribe เลยจึงเทสต์ไม่ผ่านด้วยเหตุผลที่ผิด และ **ไม่ได้ทดสอบ LEFT JOIN**
       อีกต่อไป (ไม่มีแถวให้ LEFT JOIN)

       สถานการณ์ที่เทสต์นี้ต้องครอบคือ **"มีอุปกรณ์ตอนเข้าคิว แต่หายไปก่อนถึงรอบส่ง"**
       — ซึ่งเกิดจริง: ผู้ใช้ปิดการแจ้งเตือนในเบราว์เซอร์, ถอนการติดตั้ง PWA,
       หรือ (กับดักที่อันตรายกว่า) แถวถูกลบเพราะอุปกรณ์อื่นตอบ 410 ไปก่อนหน้า
       ⇒ ด่าน LEFT JOIN นี้ยังจำเป็น และเทสต์ต้องสร้างเงื่อนไขนั้นขึ้นมาเอง
    """
    uid = push_world["student"]["user_id"]
    await _subscribe(db_pool, uid)                # ① ตอนเข้าคิว — มีอุปกรณ์
    await _notify_one(db_pool, user_id=uid)       #    ⇒ outbox ได้ 1 แถว (ผ่านประตู 019)
    async with db_pool.acquire() as conn:         # ② ก่อนถึงรอบส่ง — อุปกรณ์หายไป
        await conn.execute("DELETE FROM push_subscriptions WHERE user_id = $1", uid)

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


@pytest.mark.asyncio
async def test_T17a_drain_empties_more_than_one_batch(push_world, db_pool, monkeypatch):
    """★ `drain()` ต้องระบาย **หลาย batch ในรอบเดียว** ไม่ใช่ batch เดียว

    นี่คือหัวใจของ **F4** (แก้ 28 ก.ย. 2026): ก่อนหน้านี้ throughput =
       `PUSH_BATCH_SIZE × ความถี่ที่ cron มาจริง` ⇒ เมื่อ cron หลุดนัด (วัดได้ ~150 วิ
       แทน 20 วิ) คิวก็ระบายช้าลงตามไปด้วย **โดยไม่มีใครสั่งให้ช้า**
    ⇒ `drain()` ตัดการผูกกันนั้น: คนเรียกถี่แค่ไหน คิวก็เกลี้ยงเท่านั้น

    ⚠️ ตั้ง `PUSH_BATCH_SIZE = 2` **โดยเจตนา** เพื่อบังคับให้ต้องวนหลายรอบจริง
       (ถ้าใช้ค่า default 100 เทสต์จะผ่านด้วย batch เดียว = ไม่ได้ทดสอบอะไร)

    mutation ที่ต้องทำให้แตก: เปลี่ยน `drain()` ให้เรียก `process_pending()` ครั้งเดียว
    """
    uid = push_world["student"]["user_id"]
    await _subscribe(db_pool, uid)
    for _ in range(5):
        await _notify_one(db_pool, user_id=uid)

    monkeypatch.setattr(settings, "PUSH_BATCH_SIZE", 2)

    sender = _recorder()
    stats = await push_service.drain(db_pool, sender=sender, deadline_seconds=30)

    assert stats["claimed"] == 5, f"ระบายไม่ครบในรอบเดียว — ได้ {stats}"
    assert stats["sent"] == 5
    assert await _count(db_pool, "push_outbox", "processed_at IS NULL") == 0, "ยังมีของค้าง"


@pytest.mark.asyncio
async def test_T17b_drain_stops_at_deadline_instead_of_being_killed(push_world, db_pool,
                                                                     monkeypatch):
    """★ หมดงบ ⇒ หยุดเอง **ก่อน** ARQ ตัดงานทิ้งกลางคัน

    ⚠️ ทำไมสำคัญ: `job_timeout = 120` ของ ARQ ฆ่างานที่เกินเวลา และแถวที่ claim ไว้
       จะ **ค้าง** (`processing_at` ไม่เป็น NULL) จนกว่าจะถึงรอบกู้ = push ช้าเพิ่มอีก
       `PUSH_RECOVER_MINUTES` นาที ⇒ "ช้าเพราะแก้ให้เร็ว" เป็นกับดักที่เคาน์เตอร์อินทูอิทีฟ
       ⇒ `drain()` ต้องรู้จักหยุดเอง

    ⚠️ งบต้องเป็น 0 (หรือติดลบ) เพื่อให้แน่ใจว่าเข้าทาง `break` ที่สอง — เขียนเป็น
       `deadline_seconds=0` ตรง ๆ **ห้ามใช้ค่าจริง** ไม่งั้นเทสต์จะกิน 45 วิทุกครั้ง

    mutation ที่ต้องทำให้แตก: ลบ `if time.monotonic() >= deadline: break`
        → วนจนคิวเกลี้ยง (เทสต์นี้จะได้ claimed = 5 ไม่ใช่ 2)
    """
    uid = push_world["student"]["user_id"]
    await _subscribe(db_pool, uid)
    for _ in range(5):
        await _notify_one(db_pool, user_id=uid)

    monkeypatch.setattr(settings, "PUSH_BATCH_SIZE", 2)

    sender = _recorder()
    stats = await push_service.drain(db_pool, sender=sender, deadline_seconds=0)

    # ทำได้แค่ batch แรก (2 แถว) แล้วต้องหยุด — ที่เหลือยังรออยู่ ไม่หายไปไหน
    assert stats["claimed"] == 2, f"ไม่หยุดตามงบ — ได้ {stats}"
    assert await _count(db_pool, "push_outbox", "processed_at IS NULL") == 3, (
        "ของที่ยังไม่ทำต้องยังอยู่ในคิว (ไม่ใช่ถูกทิ้ง)"
    )


@pytest.mark.asyncio
async def test_T18a_subscription_health_records_success_and_resets_failures(push_world,
                                                                           db_pool):
    """สำเร็จ → `last_success_at` ถูกจด **และรีเซ็ต `failure_count` เป็น 0**

    ⚠️ คอลัมน์สองตัวนี้มีมาตั้งแต่ migration 018 แต่ **ไม่มีโค้ดไหนเขียนเลยทั้งรอบ**
       ⇒ เปิดตารางก็ตอบไม่ได้ว่าอุปกรณ์ไหนยังใช้ได้จริง (ต้องไล่เดาจาก outbox)
       ⇒ "วัดผลหลัง deploy" ทำไม่ได้ และเคส "push ไม่เด้งบนเครื่องนี้" วินิจฉัยไม่ได้
       (F5 — แก้ 28 ก.ย. 2026)

    ⭐ `failure_count` ต้อง **รีเซ็ต** ไม่ใช่แค่ไม่เพิ่ม — อุปกรณ์ที่ล้ม 3 ครั้งเพราะ
       เน็ตหลุดแล้วกลับมาปกติ ต้องไม่ถูกลงโทษจากอดีต (ไม่งั้นจะดู "พัง" ตลอดไป)

    mutation ที่ต้องทำให้แตก: เอา `_mark_subscription_health` ออก →
        `last_success_at` ยังเป็น NULL
    """
    uid = push_world["student"]["user_id"]
    await _subscribe(db_pool, uid)
    await _notify_one(db_pool, user_id=uid)

    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE push_subscriptions SET failure_count = 3")

    sender = _recorder(status=201)
    stats = await push_service.process_pending(db_pool, sender=sender)
    assert stats["sent"] == 1

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT last_success_at, failure_count FROM push_subscriptions LIMIT 1"
        )
    assert row["last_success_at"] is not None, "สำเร็จแล้วไม่จด ⇒ วัดผลหลัง deploy ไม่ได้"
    assert row["failure_count"] == 0, "สำเร็จแล้วต้องล้างประวัติล้ม ไม่ใช่ค้างไว้"


@pytest.mark.asyncio
async def test_T18b_subscription_health_counts_failures_without_touching_success(
    push_world, db_pool
):
    """ล้มเหลว (5xx) → `failure_count` +1 · **`last_success_at` ต้องไม่ถูกแตะ**

    ⚠️ ถ้าเผลอเขียน `last_success_at = NOW()` ในฝั่งล้มเหลว โมดูลัส "เครื่องนี้ยังดีอยู่ไหม"
       จะตอบผิดตลอดกาล — และจะไม่มีอะไรจับได้เลยเพราะคอลัมน์ไม่เป็น NULL
       ⇒ assert ทั้งสองด้าน ไม่ใช่แค่ด้านที่เพิ่มขึ้น

    ⚠️ `gone` (404/410) **ต้องไม่นับ** — แถวถูกลบไปแล้ว การ UPDATE จะไปโดน 0 แถว
       (ไม่ error แต่เสียคำสั่งเปล่า) · และไม่มีความหมายทางธุรกิจ

    mutation ที่ต้องทำให้แตก: ใช้ชุด id เดียวกันทั้ง ok และ failed (จะทับกัน)
    """
    uid = push_world["student"]["user_id"]
    await _subscribe(db_pool, uid)
    await _notify_one(db_pool, user_id=uid)

    sender = _recorder(status=503)
    stats = await push_service.process_pending(db_pool, sender=sender)
    assert stats["retry"] == 1

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT last_success_at, failure_count FROM push_subscriptions LIMIT 1"
        )
    assert row["failure_count"] == 1, "5xx ต้องถูกนับเป็นความล้มเหลว"
    assert row["last_success_at"] is None, "ยังไม่เคยสำเร็จ ห้ามจดว่าสำเร็จ"


# ============================================================
# 2.5) 🚨 sender โยน exception — "แถวค้างถาวร" (29 ก.ย. 2026)
#
#       บั๊กจริงที่พบจากการวัดบน staging **หลัง deploy A3** — ไม่ได้มาจากการอ่านโค้ด:
#         PUSH  - ERROR - ❌ sender โยน exception
#                binascii.Error: Invalid base64-encoded string: number of data
#                characters (1) cannot be 1 more than a multiple of 4
#         PUSH_WORKER - INFO - 📤 push[loop]: claimed=1 sent=0 gone=0 retry=0
#                                     dropped=0 skipped=0 stale=0
#       ⇒ ตัวนับเป็น 0 หมดทั้งที่ claim มาแล้ว 1 แถว ⇒ แถวนั้นค้าง `processing_at`
#         อยู่ 47+ วินาที (ทั้งที่ `_SEND_TIMEOUT_SECONDS = 10`) และไม่มีอะไรมาปลด
#         จนกว่าจะ redeploy (ซึ่งจะเรียก `recover_stale_outbox()`)
#
#       ราก: `one()` ปล่อย exception ให้ `asyncio.gather(return_exceptions=True)`
#         ⇒ ได้ exception แทน tuple ⇒ **`g` ที่ผูก outbox_id หายไปทั้งก้อน**
#         ⇒ ฝั่งจับผลเขียน `{"outbox_id": None, "cls": "retry"}` แล้ว **ทิ้งมัน**
#         ในลูป `per_outbox` ที่มี `if r["outbox_id"] is None: continue`
#         ⇒ "retry" ที่เพิ่งจดไปไม่ถึงใครเลย — **แถวไม่ถูกจัดประเภท ไม่จบ ไม่ retry**
#
#       ⚠️ เทสต์ชุดเดิม 486 ตัว **จับไม่ได้ทั้งหมด** เพราะทุกตัวใช้ sender ที่
#          "โยนหรือไม่โยนก็คืนค่าเสมอ" ⇒ ไม่มีตัวใดเคยพา exception ออกจาก `one()`
#          (บทเรียนเดียวกับ H9 ของ SSE: **สาขา error ที่ไม่มีเทสต์เดินเข้า = สาขาที่พังได้ฟรี**)
#
#       ⇒ `T20a` คือด่านที่ขาดไป (sender โยน), `T20c` คือของจริงเป๊ะ ๆ (คีย์เสีย)
# ============================================================

def _raiser(exc: BaseException = None):
    """sender ปลอมที่ **โยน** ทุกครั้ง — จำลองทั้ง network error ที่หลุด และ crypto พัง"""
    calls = []

    async def send(client, sub, payload, *, ttl):
        calls.append(sub["id"])
        raise exc or RuntimeError("sender ระเบิด")

    send.calls = calls
    return send


@pytest.mark.asyncio
async def test_T20a_sender_exception_reschedules_row_instead_of_sticking(push_world,
                                                                        db_pool):
    """★ sender โยน exception → แถวต้องถูก **เลื่อนส่ง** ไม่ใช่ค้าง `processing_at`

    นี่คือเทสต์ที่บั๊ก 29 ก.ย. 2026 ต้องทำให้แตก — ก่อนแก้จะได้:
        stats["retry"] == 0  (ทั้งที่ควรเป็น 1)
        row["processing_at"] is not None  ⇒ **ค้าง ไม่มีใครหยิบได้อีก**
        row["next_attempt_at"] == created_at (ไม่ถูกเลื่อน)

    mutation ที่ต้องทำให้แตก (แต่ละข้อทำให้เทสต์นี้ FAIL):
      ① `one()` ปล่อย exception ออกไป (ถอด try/except) → retry=0 + ค้าง
      ② คืน `{"outbox_id": None, "cls": "retry"}` แบบเดิม → เหมือน ①
      ③ `except Exception` → `return g, sub, 500` (500 = permanent กว่าที่ควร)
         ⇒ `dropped`/`done` ผิด · ยังผ่านข้อ retry แต่ผิดเจตนา ⇒ assert `last_error`
    """
    uid = push_world["student"]["user_id"]
    await _subscribe(db_pool, uid)
    await _notify_one(db_pool, user_id=uid)
    outbox_id = await _single_outbox_id(db_pool)

    sender = _raiser()
    stats = await push_service.process_pending(db_pool, sender=sender)

    assert len(sender.calls) == 1, "ต้องลองส่งจริง 1 ครั้ง"
    assert stats["claimed"] == 1
    assert stats["retry"] == 1, "exception ต้องถูกนับเป็น retryable ไม่ใช่หายเงียบ"
    assert stats["dropped"] == 0, "ยังไม่ครบเพดาน attempts — ห้ามทิ้ง"

    row = await _outbox_row(db_pool, outbox_id)
    assert row["processed_at"] is None, "ปิดแถวทั้งที่ยังไม่ส่งสำเร็จ = push หายถาวร"
    assert row["processing_at"] is None, (
        "🚨 processing_at ยังไม่ถูกล้าง = **แถวค้างถาวร** (บั๊ก 29 ก.ย. 2026) "
        "ไม่มีใครหยิบได้อีกจนกว่า worker จะ restart"
    )
    assert row["attempts"] == 1
    assert row["last_error"] == "send-failed"

    async with db_pool.acquire() as conn:
        later = await conn.fetchval(
            "SELECT next_attempt_at > NOW() FROM push_outbox WHERE id = $1", outbox_id
        )
    assert later is True, "ต้องเลื่อนไปอนาคต ไม่งั้นรอบถัดไปหยิบทันที (busy loop)"

    # ★ พิสูจน์ว่ากลับเข้าคิวได้จริง — ไม่ใช่แค่ค่าคอลัมน์ถูก
    again = await push_service._claim(db_pool, 100)
    assert [c["id"] for c in again] == [], "next_attempt_at ยังไม่ถึง ⇒ รอบนี้ต้องไม่ได้"
    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE push_outbox SET next_attempt_at = NOW() - INTERVAL '1 second' WHERE id = $1",
            outbox_id,
        )
    assert [c["id"] for c in await push_service._claim(db_pool, 100)] == [outbox_id], (
        "แถวที่โยน exception ต้องกลับมาถูกหยิบได้ — ไม่ใช่ค้างอยู่ตลอดกาล"
    )


@pytest.mark.asyncio
async def test_T20b_every_device_of_one_row_raising_still_retries_exactly_once(
    push_world, db_pool,
):
    """★ แถวเดียว 2 อุปกรณ์ **โยนทั้งคู่** → ต้องได้ `retry == 1` พอดี (ไม่ใช่ 0 ไม่ใช่ 2)

    ⭐ ทำไมต้องมีเทสต์นี้แยกจาก T20a — T20a มีอุปกรณ์เดียว จึงพิสูจน์ได้แค่ว่า
       "1 exception → 1 retry" · ตัวนี้พิสูจน์ว่า **การจับกลุ่มตาม outbox ยังถูกต้อง
       เมื่อมี exception หลายตัว** ⇒ กันการแก้ที่ดูเข้าท่าแต่ผิดสองแบบ:
         ① นับ retry ต่อ *exception* (จะได้ 2) — ผู้ใช้จะถูกเลื่อนส่งซ้ำซ้อน
         ② สร้างแถว retry แยกต่ออุปกรณ์ — ผิดโมเดล (retry เป็นของ *แถว* ไม่ใช่ของอุปกรณ์)

    ⚠️ **กรณี "เครื่องหนึ่งโยน เครื่องหนึ่งสำเร็จ" ไม่ได้อยู่ในเทสต์นี้โดยเจตนา** —
       ตรวจแล้วว่ามัน**ผ่านตั้งแต่ก่อนแก้** (ผลของเครื่องที่สำเร็จยังมีเจ้าของ เพราะ
       `results` มีทั้งใบที่เสียและใบที่สำเร็จปนกัน) ⇒ เอามาเขียนเป็นเทสต์จะได้
       เทสต์ที่ **ไม่มีฟัน** และ docstring ที่อ้างว่าจับบั๊กไม่ได้ = โกหกคนอ่าน
       ⇒ เก็บเฉพาะกรณีที่ **พิสูจน์แล้วว่าแตกก่อนแก้** (ยืนยันด้วยการ stash โค้ดที่แก้)

    mutation ที่ต้องทำให้แตก: ถอด try/except ใน `one()` → `retry == 0` + แถวค้าง
    """
    uid = push_world["student"]["user_id"]
    await _subscribe(db_pool, uid)                       # เครื่องที่ 1 — จะโยน
    await _subscribe(db_pool, uid)                       # เครื่องที่ 2 — จะโยน
    await _notify_one(db_pool, user_id=uid)
    outbox_id = await _single_outbox_id(db_pool)

    sender = _raiser()
    stats = await push_service.process_pending(db_pool, sender=sender)

    assert len(sender.calls) == 2, "ต้องลองทั้งสองเครื่อง — เครื่องหนึ่งพังต้องไม่ตัดรอบทิ้ง"
    assert stats["claimed"] == 1, "2 อุปกรณ์ของ notification เดียว = outbox **1** แถว"
    assert stats["retry"] == 1, (
        "ต้องเป็น 1 (ของแถว) ไม่ใช่ 0 (หายเงียบ) และไม่ใช่ 2 (นับต่ออุปกรณ์)"
    )
    assert stats["dropped"] == 0

    row = await _outbox_row(db_pool, outbox_id)
    assert row["processing_at"] is None, "🚨 ค้าง = ไม่มีใครหยิบได้อีก"
    assert row["attempts"] == 1, "claim นับ attempt ครั้งเดียวต่อแถว ไม่ใช่ต่ออุปกรณ์"


@pytest.mark.asyncio
async def test_T20c_corrupt_stored_key_is_retried_and_counted_not_stuck(push_world,
                                                                       db_pool,
                                                                       monkeypatch):
    """★★ ของจริงเป๊ะ ๆ — คีย์ใน DB เสียหาย → `_send_one` ตัวจริงโยน **ต้องไม่ค้าง**

    ต่างจาก T20a/T20b ตรงที่ **ไม่ได้ฉีด sender ปลอม** — เรียก `_send_one` ของจริง
    ผ่าน `process_pending(sender=None)` และคีย์ที่เก็บไว้ถอด base64 ไม่ได้
    ⇒ ล้มที่ `_decode_key()` **ก่อน** จะยิง HTTP ⇒ ไม่ต้องมี server และไม่ออกเน็ต
    (ตรงกับ plan §20.14 ข้อ 6)

    ⭐ ทำไมต้องเป็นเทสต์แยกจาก T20a: T20a พิสูจน์ "sender โยน ⇒ จัดการถูก"
       แต่เทสต์นี้พิสูจน์ว่า **เส้นทาง crypto จริงเดินเข้าไปในสาขานั้นได้**
       (บั๊กเดิมรอดเพราะ `_send_one` catch แค่ `httpx.HTTPError`
        ซึ่ง **ไม่ครอบ `binascii.Error`** ที่โผล่มาใน log จริง)

    🔑 ต้องตั้งคีย์ VAPID ให้ **ใช้ได้** ก่อน ไม่งั้น `_vapid().sign()` จะพังก่อน
       แล้วเทสต์จะผ่านด้วยเหตุผลผิด (และจะไม่ทดสอบ `_decode_key` เลย)
    """
    from py_vapid import Vapid02
    import importlib.util
    from pathlib import Path

    from core.config import settings

    script = Path(__file__).resolve().parent.parent / "scripts" / "generate_vapid_keys.py"
    spec = importlib.util.spec_from_file_location("gen_vapid_t20c", script)
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)

    key = Vapid02()
    key.generate_keys()
    monkeypatch.setattr(settings, "VAPID_PUBLIC_KEY",
                        gen._b64url(gen._raw_public(key.public_key)))
    monkeypatch.setattr(settings, "VAPID_PRIVATE_KEY",
                        gen._b64url(key.private_key.private_numbers().private_value
                                    .to_bytes(32, "big")))
    monkeypatch.setattr(settings, "VAPID_SUBJECT", "mailto:council@piriyalai.ac.th")
    push_service._reset_vapid_cache()

    uid = push_world["student"]["user_id"]
    endpoint = f"https://fcm.googleapis.com/fcm/send/{random.randint(10**9, 10**10)}"
    async with db_pool.acquire() as conn:
        # ⚠️ คีย์แบบที่ `_decode_key` ถอดไม่ได้ — 1 ตัวอักษร เติม '=' แล้วยังหาร 4 ไม่ลงตัว
        #    ("x" 1 ตัว = repro เดิมจาก log จริง: "number of data characters (1)")
        await conn.execute(
            """INSERT INTO push_subscriptions (user_id, endpoint, p256dh, auth)
               VALUES ($1, $2, 'x', 'y')""",
            uid, endpoint,
        )
    await _notify_one(db_pool, user_id=uid)
    outbox_id = await _single_outbox_id(db_pool)

    stats = await push_service.process_pending(db_pool)  # ← sender ตัวจริง

    assert stats["claimed"] == 1
    assert stats["retry"] == 1, (
        "คีย์เสียต้องถูกนับเป็น retryable — ก่อนแก้จะได้ retry=0 และแถวค้าง"
    )
    row = await _outbox_row(db_pool, outbox_id)
    assert row["processing_at"] is None, "🚨 แถวค้างเพราะ crypto โยน (บั๊ก 29 ก.ย. 2026)"
    assert row["processed_at"] is None
    assert row["attempts"] == 1

    push_service._reset_vapid_cache()


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
# 4) migration 018 + 019 — ⚠️ สองเทสต์นี้ต้องอยู่ท้ายไฟล์ (มัน DROP ตารางจริง)
#    และ **ต้องคืนสภาพสคีมาให้เป็นรุ่นล่าสุด (019) ก่อนจบ** — ดูคอมเมนต์ใน T6
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

    🚨 **กับดักที่เทสต์นี้ก่อเอง (แก้ 28 ก.ย. 2026):** `DROP TABLE push_subscriptions CASCADE`
       แล้วรัน **018** `upgrade()` จะติดตั้ง `push_outbox_enqueue()` **รุ่นที่ยังไม่มีประตู**
       กลับคืนมา (`CREATE OR REPLACE FUNCTION`) ⇒ ถ้าจบเทสต์ตรงนั้น สคีมาจะถอยกลับไปเป็น
       **018 ทั้งที่ migration ล่าสุดคือ 019** และ **ร่องรอยจะไปโผล่ในไฟล์เทสต์ถัดไป**
       (pytest เรียงตามชื่อไฟล์: `test_push_send` · `test_push_subscriptions` รันต่อจากไฟล์นี้)
       ⇒ **ต้องปิดท้ายด้วย `019.upgrade()` เสมอ** เพื่อคืนสภาพจริง — ตัวเทสต์ประตูอยู่ที่ T19
    """
    push_world
    mig = importlib.import_module("migrations.018_push_notifications")
    mig19 = importlib.import_module("migrations.019_push_outbox_requires_device")

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

        # ⬆️ ถึงตรงนี้ trigger เป็น **รุ่น 018 (ยังไม่มีประตู)** — คืนสภาพล่าสุดก่อนไปต่อ
        await mig19.upgrade(conn)

        # ✅ พิสูจน์ว่า trigger ที่สร้างคืน **ทำงานจริง** ไม่ใช่แค่เห็นใน catalog
        #    (ด่านสุดท้าย — ถ้า migration สร้าง trigger พลาด เทสต์ T1-T5 ที่รันไปก่อนหน้า
        #     จะจับไม่ได้เลย เพราะตอนนั้น trigger ตัวเดิมยังอยู่)
        uid = push_world["student"]["user_id"]
        await _give_device(db_pool, uid)
        await _notify_one(db_pool, user_id=uid)
        assert await conn.fetchval("SELECT COUNT(*) FROM push_outbox") == 1


@pytest.mark.asyncio
async def test_T19_migration_019_adds_device_gate_and_is_idempotent(push_world, db_pool):
    """★ migration 019 — **พิสูจน์ด้วยการถอดออกแล้วใส่กลับ** (ไม่ใช่แค่ "มีประตูอยู่")

    วิธี: ยิง input เดียวกันเป๊ะ (notify คนที่ไม่มีอุปกรณ์) สองครั้ง
      · ครั้งแรกตอนสคีมาเป็น **018** ⇒ ต้องได้ outbox **1 แถว** (พฤติกรรมเก่า)
      · ครั้งที่สองตอนสคีมาเป็น **019** ⇒ ต้องยังเป็น 1 แถว (ประตูกันไว้)

    ⭐ **ทำไมต้องเทสต์แบบ mutation แทนการ assert เฉย ๆ:** ถ้าเขียนแค่ "notify คนไม่มี
       อุปกรณ์ → outbox 0" เทสต์นั้นจะผ่าน **แม้ลบ migration 019 ทิ้งทั้งไฟล์**
       ถ้าสคีมาบังเอิญถูก drop ไปก่อนหน้า (T6) หรือถ้า trigger ไม่ถูกสร้างเลย
       ⇒ "0 แถว" ไม่ใช่หลักฐานว่ามีประตู — ต้องเห็น **ความต่าง** ระหว่างสองรุ่นจึงเป็นหลักฐาน

    ⚠️ **ต้องอยู่ท้ายไฟล์เป็นตัวสุดท้าย** — มันรัน 018 ทับ (ถอยสคีมา) แล้วคืน 019
       ถ้ารันก่อน T6/T5b จะทำให้เทสต์เหล่านั้นเห็นสคีมาผิดรุ่น
    """
    mig18 = importlib.import_module("migrations.018_push_notifications")
    mig19 = importlib.import_module("migrations.019_push_outbox_requires_device")

    no_device = push_world["student"]["user_id"]
    has_device = push_world["student2"]["user_id"]
    await _give_device(db_pool, has_device)

    # ---------- ① สคีมาเป็น 018: ยังไม่มีประตู → ของที่ทำไม่ได้ก็ยังเข้าคิว ----------
    async with db_pool.acquire() as conn:
        await mig18.upgrade(conn)
    await _notify_one(db_pool, user_id=no_device)
    assert await _count(db_pool, "push_outbox") == 1, (
        "018 ต้องยอมให้เข้าคิว — ถ้าไม่ แปลว่าเทสต์กำลังพิสูจน์ผิดเรื่อง"
    )

    # ---------- ② คืน 019 (สองครั้ง = idempotent) ----------
    async with db_pool.acquire() as conn:
        await mig19.upgrade(conn)
        await mig19.upgrade(conn)  # CREATE OR REPLACE + DROP TRIGGER IF EXISTS ⇒ รันซ้ำได้

        # trigger ต้องยัง **เปิด** อยู่ (DROP+CREATE อาจจบด้วย tgenabled ≠ 'O')
        # ⚠️ `tgenabled` เป็นชนิด `"char"` ของ pg_catalog ⇒ asyncpg คืน **bytes**
        #    (ไม่ใช่ str) · cast เป็น text ใน SQL เพื่อให้เทียบกับ 'O' ได้ตรง ๆ
        #    (ถ้าเทียบ `== "O"` จะล้มด้วย `assert b'O' == 'O'` ซึ่งอ่านแล้วงงมาก)
        assert await conn.fetchval(
            "SELECT tgenabled::text FROM pg_trigger "
            "WHERE tgname = 'trg_notifications_push_outbox'"
        ) == "O", "trigger ถูกสร้างคืนแต่ปิดอยู่ = push เงียบทั้งระบบ"

    # ---------- ③ ประตูทำงาน: คนไม่มีอุปกรณ์ **ไม่เพิ่ม** ----------
    await _notify_one(db_pool, user_id=no_device)
    assert await _count(db_pool, "push_outbox") == 1, (
        "019 ต้องกันคนไม่มีอุปกรณ์ — ถ้าเพิ่มเป็น 2 แปลว่าประตูไม่ได้ผล"
    )
    # และ in-app ต้องยังได้ (ประตูตัดแค่ push)
    assert await _count(db_pool, "notifications") == 2

    # ---------- ④ คนที่มีอุปกรณ์ยังเข้าคิวได้ปกติ (ประตูไม่ได้ปิดทางทั้งหมด) ----------
    await _notify_one(db_pool, user_id=has_device)
    assert await _count(db_pool, "push_outbox") == 2
