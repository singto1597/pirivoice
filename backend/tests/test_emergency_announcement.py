"""🚨 E2 — ประกาศฉุกเฉิน (`priority='urgent'`) ยิงแจ้งเตือนทุกคน **ทันที** และทะลุ quiet hours (A8)

ทดสอบจาก **เส้นทางจริง** ไม่ใช่การจำลอง: เรียก `announcement_service.create_announcement()`
แล้วตรวจว่าแถวใน `notifications` / `push_outbox` เกิดจริง และ push ถูกส่งจริง
(ผ่าน sender ปลอม — **ห้ามมีเทสต์ที่ยิง HTTP ออกเน็ต** ตามแผน §20.14 ข้อ 6)

⭐ **ทำไมไฟล์นี้ต้องมี** — `test_quiet_hours.py` พิสูจน์ว่า "ด่านอ่านธง `bypass_quiet_hours`"
แต่ธงนั้นถูก **ติดด้วยมือ** ผ่าน `_mark_bypass()` (ซึ่งคอมเมนต์ของมันเขียนไว้เองว่า
*"การ thread flag ผ่าน `notify*` มีเทสต์ของตัวเองในชุด E2"*) ⇒ ถ้าไม่มีไฟล์นี้
**ทั้งห่วงโซ่ E2→A8 ไม่มีเทสต์ใดพิสูจน์ว่าธงถูกเขียนจริง** — โค้ดที่ลืมส่ง `bypass_quiet_hours=True`
จะผ่านทุกเทสต์ที่มีอยู่ แล้วประกาศฉุกเฉินจะถูก quiet hours กลั้นไว้เงียบ ๆ ซึ่งคือ
ความล้มเหลวที่ฟีเจอร์นี้เกิดมาเพื่อป้องกัน

⚠️ **สองด้านที่ต้องเทสต์คู่กันเสมอ** (บทเรียนเดียวกับ A8):
   · `urgent` → แจ้งคนอื่น **ครบ** และทะลุ quiet hours
   · `normal`/`high` → **ไม่แจ้งใครเลย** — `notify_fanout` ยิงทุก active student
     (~800–1,000 แถวต่อครั้ง) ⇒ พิมพ์ผิดเป็น `urgent` = push ทั้งโรงเรียนที่เรียกคืนไม่ได้
"""
import base64
import json
import random
from datetime import datetime

import pytest
import pytest_asyncio

from core.config import settings
from services import (
    announcement_service,
    app_settings_service,
    auth_service,
    notification_service,
    push_service,
)

BKK = app_settings_service.BKK


# ============================================================
# 0) Fixture — แอดมินผู้ประกาศ + นักเรียน 3 คน
# ============================================================

@pytest_asyncio.fixture
async def e2_world(db_pool):
    """ห้องเดียว + 4 คน: `admin` (ผู้ประกาศ) + `s1`/`s2`/`s3` (ผู้รับ)

    ⚠️ **ผู้รับมาจากตาราง `students` ทั้งหมด ไม่ใช่จากห้อง** — `notify_fanout` ยิงทุกแถวที่
       `deleted_at IS NULL AND status = 'active'` ⇒ เทสต์ต้องคุมจำนวนให้รู้แน่
       (`clean_database` เป็น autouse ⇒ โรงเรียนในเทสต์มี 4 คนนี้เท่านั้น)

    ⚠️ `class_role="admin"` ⇒ `is_admin = TRUE` ⇒ `require_permission_anywhere` ผ่านโดยไม่
       ต้องอ่าน `permissions` array (แบบเดียวกับ `test_announcements.py`)

    ⚠️ `student_id` เป็น `VARCHAR(10)` — รหัสที่สร้างต้องไม่เกิน 10 ตัว ไม่งั้น insert ล้ม
    """
    room_code = f"ฉ.{random.randint(1, 90)}"
    async with db_pool.acquire() as conn:
        room_id = await conn.fetchval(
            "INSERT INTO rooms (room_code, room_name, level) VALUES ($1,$2,'ม.6') RETURNING id",
            room_code, room_code,
        )

    users = {}
    for i, (label, role) in enumerate(
        [("admin", "admin"), ("s1", "student"), ("s2", "student"), ("s3", "student")]
    ):
        sid = f"E{random.randint(100000, 999999)}{i}"  # 8 ตัว — ใต้เพดาน 10
        uid = await auth_service.register_user(
            db_pool, sid, "1234", f"{label} ทดสอบ", sid, room_code, i + 1, role
        )
        users[label] = {
            "user_id": uid,
            "student_id": sid,
            "token": auth_service.create_access_token(uid),
        }

    users["room_id"] = room_id
    users["recipients"] = {users[k]["user_id"] for k in ("s1", "s2", "s3")}
    return users


def _auth(world, who="admin"):
    return {"Authorization": f"Bearer {world[who]['token']}"}


async def _announce(db_pool, world, *, priority: str = "urgent", message: str = "งดเรียนกะทันหัน"):
    """เรียก service ตรง — ที่นั่งของ E2 hook (router เป็นแค่ทางผ่าน ไม่มี logic)"""
    return await announcement_service.create_announcement(
        db_pool, world["admin"]["user_id"], message=message, priority=priority, link=None,
    )


async def _rows(db_pool, table: str, where: str = "TRUE", *params):
    async with db_pool.acquire() as conn:
        return await conn.fetch(f"SELECT * FROM {table} WHERE {where} ORDER BY id", *params)


async def _count(db_pool, table: str, where: str = "TRUE", *params) -> int:
    async with db_pool.acquire() as conn:
        return await conn.fetchval(f"SELECT COUNT(*) FROM {table} WHERE {where}", *params)


# ============================================================
# 1) ผู้รับ — ใครได้ ใครไม่ได้
# ============================================================

@pytest.mark.asyncio
async def test_urgent_creates_one_row_per_active_student_with_bypass_flag(db_pool, e2_world):
    """⭐⭐ **หัวใจของ E2** — `urgent` ⇒ 1 แถวต่อ active student 1 คน พร้อมธงทะลุ quiet hours

    ⚠️ **assert ทั้ง "จำนวน" และ "ตัวตนของผู้รับ"** — นับอย่างเดียวผ่านได้ทั้งที่ส่งผิดคน
       (เช่นถ้า `actor_id` ถูกส่งเป็นค่าอื่น ผู้ประกาศจะได้แถวของตัวเองแล้วมี 4 แถวแทน 3)
    ⚠️ **assert `bypass_quiet_hours is True` ต่อแถว** — นี่คือสัญญาระหว่าง E2 กับ A8:
       ค่าที่นี่ถูกอ่านที่ `push_service._load_payloads` ตอน *ส่ง* ⇒ ถ้าค่าหลุด
       ประกาศฉุกเฉินจะถูกกลั้นตอนกลางคืน (และ **เทสต์ทั้งชุดเดิมจะไม่จับได้เลย**)
    """
    ann = await _announce(db_pool, e2_world)
    rows = await _rows(db_pool, "notifications", "group_type = 'announcement'")

    assert len(rows) == 3, "ต้องได้เท่าจำนวน active student ที่ไม่ใช่ผู้ประกาศ"
    assert {r["user_id"] for r in rows} == e2_world["recipients"]

    for r in rows:
        assert r["type"] == "announcement_urgent"
        assert r["group_type"] == "announcement"
        assert r["entity_type"] == "announcement"
        assert r["entity_id"] == ann["id"], "ต้องชี้ไปใบที่เพิ่งสร้าง"
        assert r["bypass_quiet_hours"] is True, "★ ธงที่ A8 อ่านตอนส่ง — หลุดเมื่อไหร่ = ถูกกลั้น"
        assert r["actor_id"] == e2_world["admin"]["user_id"]
        assert r["body"] == "งดเรียนกะทันหัน", "เนื้อความเต็มไม่ถูกตัด (เพดาน 1,000 ตัวของ schema)"


@pytest.mark.asyncio
async def test_announcer_is_excluded_from_their_own_fanout(db_pool, e2_world):
    """ผู้ประกาศต้องไม่ได้รับแจ้งเตือนของตัวเอง (`actor_id=user_id` ⇒ `NOT EXISTS` ใน SQL)

    ⚠️ แยกจากเทสต์ข้างบนโดยเจตนา — ถ้ารวมกัน ข้อความ fail จะบอกได้แค่ "จำนวนไม่ใช่ 3"
       ซึ่งชี้ไปทาง "fanout พัง" ทั้งที่ความจริงคือ "กรองตัวเองพลาด"
    """
    admin_id = e2_world["admin"]["user_id"]
    await _announce(db_pool, e2_world)

    assert await _count(db_pool, "notifications", "user_id = $1", admin_id) == 0
    assert await _count(db_pool, "notifications") == 3, "คนอื่นยังต้องได้ครบ"


@pytest.mark.asyncio
@pytest.mark.parametrize("priority", ["normal", "high"])
async def test_non_urgent_notifies_nobody(db_pool, e2_world, priority):
    """⛔ **`normal`/`high` ต้องไม่แจ้งใครเลย** — ประกาศทั่วไปขึ้น Home อยู่แล้ว

    ⭐ นี่คือด่านกันความเสียหายระดับ "กดผิดครั้งเดียว = push ทั้งโรงเรียน":
       `notify_fanout` ยิงทุก active student (~800–1,000 แถว) และ **เรียกคืนไม่ได้**
       ⇒ ถ้ามีคนแก้เงื่อนไข `if priority != "urgent": return` พลาด เทสต์นี้คือตัวจับ

    ⚠️ assert **ทั้ง `notifications` และ `push_outbox`** — outbox มาจาก trigger บน
       `notifications` ⇒ ถ้าไม่มีแถวใน notifications ก็ไม่มีทางมี outbox
       แต่ assert ตรง ๆ ไว้กันวันที่มีคนเปลี่ยนไป enqueue จากที่อื่น
    """
    await _announce(db_pool, e2_world, priority=priority, message="ประกาศทั่วไป")

    assert await _count(db_pool, "notifications") == 0, f"{priority} ต้องไม่แจ้งใคร"
    assert await _count(db_pool, "push_outbox") == 0, f"{priority} ต้องไม่แตะคิว push"


# ============================================================
# 2) ถึงมือถือจริง — outbox + payload
# ============================================================

@pytest.fixture(autouse=True)
def vapid_configured(monkeypatch):
    """ตั้งคีย์ VAPID ให้ทุกเทสต์ในไฟล์นี้ — `process_pending()` มีด่านแรก "ไม่มีคีย์ = ปิดทั้งคิว"

    ⚠️ ถ้าไม่ตั้ง ทุกเทสต์ที่เรียก `process_pending` จะหยุดที่ด่านนั้นแล้ว **ดูเหมือน "ผ่าน"**
       เพราะ stats ว่างเปล่า (กับดักที่ `test_push_outbox.py` จดไว้)
    """
    monkeypatch.setattr(settings, "VAPID_PUBLIC_KEY", "test-public-key")
    monkeypatch.setattr(settings, "VAPID_PRIVATE_KEY", "test-private-key")
    push_service._reset_vapid_cache()
    yield
    push_service._reset_vapid_cache()


async def _subscribe(db_pool, user_id: int) -> str:
    """ให้ผู้รับมีอุปกรณ์ — **จำเป็นตั้งแต่ migration 019** (trigger กรองคนไม่มีอุปกรณ์ทิ้ง)

    ⚠️ ไม่มีบรรทัดนี้ = `push_outbox` ว่างเปล่า = เทสต์ push ทั้งไฟล์กลายเป็น no-op
    """
    endpoint = f"https://fcm.googleapis.com/fcm/send/{random.randint(10**9, 10**10)}"
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
    """sender ปลอม — เก็บทุกครั้งที่ถูกเรียกไว้ตรวจ payload"""
    calls = []

    async def send(client, sub, payload, *, ttl):
        calls.append({"sub": sub, "payload": payload, "ttl": ttl})
        return status

    send.calls = calls
    return send


def _covering_now() -> dict:
    """ช่วง quiet hours ที่ **ครอบเวลาปัจจุบันเสมอ** (เวลาไทย)

    ⚠️ ห้าม hardcode "00:00–23:59" — มีรู 1 นาทีต่อวัน (นาทีที่ 23:59) ⇒ เทสต์จะล้ม
       แบบสุ่มวันละครั้ง ซึ่งเป็นความล้มเหลวที่แย่ที่สุด (ทำซ้ำยาก) · ใช้ `BKK` ไม่ใช่
       `ZoneInfo` ตามธรรมเนียมโปรเจค
    """
    cur = datetime.now(BKK)
    minutes = cur.hour * 60 + cur.minute
    fmt = app_settings_service._fmt_hhmm
    return {
        "enabled": True,
        "start": fmt((minutes - 5) % app_settings_service._MINUTES_PER_DAY),
        "end": fmt((minutes + 10) % app_settings_service._MINUTES_PER_DAY),
    }


async def _seed_quiet_hours(db_pool, value: dict, *, user_id: int) -> None:
    """เขียนค่าตั้ง **ตรงเข้า DB ข้าม service** — เทสต์ฝั่ง worker ไม่ต้องล็อกอิน"""
    async with db_pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO app_settings (key, value, description, updated_by)
               VALUES ($1, $2::jsonb, 'seed', $3)
               ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()""",
            app_settings_service.QUIET_HOURS_KEY, json.dumps(value), user_id,
        )


@pytest.mark.asyncio
async def test_urgent_reaches_devices_with_home_deep_link(db_pool, e2_world):
    """⭐ ประกาศฉุกเฉินต้อง **ถึงมือถือจริง** และกดแล้วไป **หน้า Home** (A4 ∩ E2)

    ⚠️ ผู้รับ 3 คน แต่มีอุปกรณ์แค่ 1 (s1) ⇒ outbox ต้องมี **1 แถว ไม่ใช่ 3**
       (migration 019 กรองคนไม่มีอุปกรณ์ตั้งแต่ตอนเข้าคิว — กันคิวท่วมด้วยงานที่ทำไม่ได้)
    """
    s1 = e2_world["s1"]["user_id"]
    await _subscribe(db_pool, s1)
    await _announce(db_pool, e2_world)

    assert await _count(db_pool, "notifications") == 3, "in-app ได้ทุกคน"
    outbox = await _rows(db_pool, "push_outbox")
    assert len(outbox) == 1 and outbox[0]["user_id"] == s1, "คิว push มีเฉพาะคนที่มีอุปกรณ์"

    sender = _recorder()
    stats = await push_service.process_pending(db_pool, sender=sender)

    assert stats["sent"] == 1
    assert len(sender.calls) == 1, "ต้องยิงจริง 1 ครั้ง"
    payload = sender.calls[0]["payload"]
    assert payload["data"]["url"] == "/app/home", "★ ประกาศแสดงบน Home — ไม่ใช่หน้ารวมแจ้งเตือน"
    assert payload["data"]["type"] == "announcement_urgent"
    assert payload["data"]["entity_id"] is not None
    assert "ฉุกเฉิน" in payload["title"], "ผู้ใช้ต้องเห็นได้ทันทีว่านี่คือประกาศฉุกเฉิน"


# ============================================================
# 3) ★★ E2 ∩ A8 — ธงที่ E2 เขียน คือธงที่ A8 อ่าน
# ============================================================

@pytest.mark.asyncio
async def test_urgent_escapes_quiet_hours_while_normal_is_suppressed(db_pool, e2_world):
    """⭐⭐⭐ **เทสต์ที่สำคัญที่สุดของไฟล์นี้** — ในช่วงเวลาเดียวกัน ประกาศฉุกเฉิน **ส่ง**
    แต่แจ้งเตือนธรรมดา **ถูกกลั้น** ⇒ พิสูจน์ว่าธง `bypass_quiet_hours` ไหลครบวงจร

    โซ่ที่ต้องต่อกัน 3 ทอด (ขาดทอดใดทอดหนึ่ง = เทสต์นี้ fail):
      1. `announcement_service._fanout_if_urgent` ส่ง `bypass_quiet_hours=True`
      2. `notification_service.notify_fanout` เขียนค่าลง **คอลัมน์** (ไม่ใช่ทิ้ง)
      3. `push_service._load_payloads` อ่านค่ากลับจาก JOIN แล้วข้ามด่าน quiet hours

    ⚠️ **ต้องมีทั้งสองครึ่งในเทสต์เดียว** — ถ้าแยกเป็นสองเทสต์ จะมี "ช่วงเวลาที่ quiet hours
       ไม่ทำงาน" คั่นกลาง และเทสต์ "urgent ถูกส่ง" จะผ่านได้แม้ **ไม่มีธงเลย**
       (เพราะเวลานั้นไม่ได้อยู่ในช่วงปิด) ⇒ การเทียบในหน้าต่างเดียวกันคือสิ่งที่ทำให้
       ข้อสรุปมีน้ำหนัก — และเป็นเหตุผลที่วันนี้ต้องตรงกันทั้งวัน

    ⚠️ s3 ไม่มีอุปกรณ์ ⇒ ไม่มีแถวในคิว ⇒ ปรากฏใน `stats` แค่ผ่าน s1/s2 เท่านั้น
       (ถ้าคาดว่า `claimed == 3` จะ fail ด้วยเหตุผลที่ผิด)
    """
    s1, s2 = e2_world["s1"]["user_id"], e2_world["s2"]["user_id"]
    await _subscribe(db_pool, s1)
    await _subscribe(db_pool, s2)
    await _seed_quiet_hours(db_pool, _covering_now(), user_id=e2_world["admin"]["user_id"])

    # ① ประกาศฉุกเฉิน → 2 แถวในคิว (s1, s2)
    await _announce(db_pool, e2_world)
    # ② ตามด้วยแจ้งเตือนธรรมดาถึง s1 — อยู่ในช่วงปิดเดียวกันเป๊ะ
    async with db_pool.acquire() as conn:
        async with conn.transaction():
            await notification_service.notify(
                conn,
                user_id=s1, group_type="issue_mine", type="issue_update",
                title="เรื่องของคุณถูกตอบกลับ", body="ข้อความ",
                entity_type="issue", entity_id=999001,
            )

    assert await _count(db_pool, "push_outbox") == 3, "urgent 2 + ธรรมดา 1"

    sender = _recorder()
    stats = await push_service.process_pending(db_pool, sender=sender)

    assert stats["claimed"] == 3
    assert stats["sent"] == 2, "★ ประกาศฉุกเฉินต้องทะลุ quiet hours"
    assert stats["quiet"] == 1, "★ แจ้งเตือนธรรมดาในหน้าต่างเดียวกันต้องถูกกลั้น"

    # ── ตรวจระดับแถว ไม่ใช่แค่ตัวนับ (ตัวนับถูกอย่างเดียวไม่พอ) ──
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT o.user_id, o.last_error, o.processed_at, n.group_type
               FROM push_outbox o JOIN notifications n ON n.id = o.notification_id
               ORDER BY o.id"""
        )
    urgent = [r for r in rows if r["group_type"] == "announcement"]
    ordinary = [r for r in rows if r["group_type"] == "issue_mine"]

    assert len(urgent) == 2 and len(ordinary) == 1
    for r in urgent:
        assert r["processed_at"] is not None
        assert r["last_error"] is None, "ส่งสำเร็จต้องไม่มี last_error"
    assert ordinary[0]["last_error"] == "quiet-hours", "ต้องถูกกลั้นด้วยเหตุผลที่อ่านออก"
    assert len(sender.calls) == 2, "ยิง HTTP แค่ 2 ครั้ง (ฉุกเฉิน) — ธรรมดาไม่ยิงเลย"


# ============================================================
# 4) กลุ่ม `announcement` ปิดไม่ได้
# ============================================================

@pytest.mark.asyncio
async def test_announcement_group_is_readable_but_not_silenceable(client, db_pool, e2_world):
    """`announcement` **อ่าน/กรองได้** (6 กลุ่ม) แต่ **ปิดไม่ได้** (5 กลุ่ม) — สองลิสต์ไม่เท่ากันโดยเจตนา

    ⭐ ประกาศฉุกเฉินที่ผู้ใช้ปิดได้ = ล้มเหลวในหน้าที่ของมัน ⇒ กลุ่มนี้ถูกกันออกจาก
       `PREFERENCE_GROUPS` ทั้งฝั่ง backend และ frontend (ไม่มีสวิตช์ให้กดตั้งแต่แรก)
       ⇒ เทสต์นี้ตรึง "ช่องที่ผู้ใช้จะปิดมันได้" ว่าต้องปิดไม่ลง

    ⚠️ assert **ทั้งสองด้าน** — ถ้า `GROUP_TYPE_PATTERN` (ของ preference) ถูกเผลอทำให้เท่ากับ
       ตัวอ่าน เทสต์นี้จะ fail · และถ้าตัวอ่านถูกทำให้แคบลง `GET ?group_type=announcement`
       จะตอบ 422 ทั้งที่มีแถวชนิดนั้นจริงใน DB (ผู้ใช้เห็น badge แต่กรองดูไม่ได้)
    """
    await _announce(db_pool, e2_world)

    # (ก) อ่าน/กรองได้ — 6 กลุ่ม
    res = client.get("/api/notifications", params={"group_type": "announcement"},
                     headers=_auth(e2_world, "s1"))
    assert res.status_code == 200, res.text
    assert res.json()["total"] == 1, "ผู้รับ 1 คนมีประกาศฉุกเฉิน 1 ใบ"

    # (ข) ปิดไม่ได้ — 422 (ไม่ใช่ 200 ที่เงียบ ๆ ไม่มีผล)
    res = client.put(
        "/api/notifications/preferences",
        headers=_auth(e2_world, "s1"),
        json={"preferences": [{"group_type": "announcement", "enabled": False}]},
    )
    assert res.status_code == 422, (
        "กลุ่ม announcement ต้องอยู่นอกลิสต์ที่ปิดได้ — ถ้าผ่าน แสดงว่าประกาศฉุกเฉินถูกปิดได้"
    )

    # (ค) หน้าตั้งค่าต้องไม่โชว์กลุ่มนี้เลย (5 กลุ่มเท่านั้น)
    res = client.get("/api/notifications/preferences", headers=_auth(e2_world, "s1"))
    groups = {p["group_type"] for p in res.json()["preferences"]}
    assert groups == {"issue_mine", "issue_received", "board", "report", "event"}
    assert "announcement" not in groups


# ============================================================
# 5) Atomicity — hook อยู่ใน transaction เดียวกับประกาศ
# ============================================================

@pytest.mark.asyncio
async def test_failed_fanout_rolls_back_the_announcement(db_pool, e2_world, monkeypatch):
    """fanout ล้ม ⇒ **ประกาศต้องไม่ถูกสร้าง** และ **audit ต้องไม่ถูกเขียน**

    ⭐ ทำไมต้องเป็นแบบนี้: hook อยู่ใน `async with conn.transaction()` เดียวกับ INSERT
       ประกาศ ⇒ ประกาศที่มีคนไม่ได้รับ (หรือได้รับบางส่วน) แย่กว่าการไม่มีประกาศเลย
       เพราะผู้ประกาศเห็น "สำเร็จ" แล้วเข้าใจว่าทั้งโรงเรียนรู้แล้ว

    ⚠️ `announcement_service` import เป็น **โมดูล** (`from services import notification_service`)
       ⇒ patch ที่ attribute ของโมดูลจึงมีผลกับ call site จริง — ถ้าวันหนึ่งมีคนเปลี่ยนเป็น
       `from services.notification_service import notify_fanout` เทสต์นี้จะหยุดจับ (และ
       จะ fail ทันทีตั้งแต่รอบแรก ⇒ รู้ตัว ไม่ใช่เงียบ)
    """
    async def boom(*args, **kwargs):
        raise RuntimeError("fanout ล้มกลางทาง")

    monkeypatch.setattr(notification_service, "notify_fanout", boom)

    with pytest.raises(RuntimeError):
        await _announce(db_pool, e2_world)

    assert await _count(db_pool, "announcements") == 0, "★ ประกาศต้องถูก rollback"
    assert await _count(db_pool, "notifications") == 0
    assert await _count(
        db_pool, "audit_logs", "action = 'CREATE_ANNOUNCEMENT'"
    ) == 0, "audit อยู่ใน transaction เดียวกัน ⇒ ต้องหายไปด้วย"
