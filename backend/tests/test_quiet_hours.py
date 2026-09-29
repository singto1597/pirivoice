"""🔇 Quiet Hours (A8) — ช่วงเวลาที่โรงเรียนไม่ส่ง push

ทดสอบ 4 ระดับ:
  1) **ตรรกะบริสุทธิ์** — `normalize_quiet_hours` / `quiet_hours_active` / `quiet_hours_resumes_at`
     (ไม่ต้องมี DB) · เป็นชั้นที่พลาดง่ายที่สุดเพราะ "ข้ามเที่ยงคืน" ตัดสินด้วยการเทียบ "นาทีในวัน"
  2) HTTP — `GET`/`PUT /api/settings/quiet-hours` (+ auth / permission / validation)
  3) Deep-DB — แถวใน `app_settings` เกิดจริง + audit log ใน transaction เดียวกัน
  4) **ผลจริงต่อ push worker** — แถวใน `push_outbox` ถูกปิดด้วย `last_error='quiet-hours'`
     และ `stats["quiet"]` นับถูก · พร้อมกับธง `bypass_quiet_hours` (E2) ทะลุออกไปได้
     (นี่คือเหตุผลทั้งหมดของการมีฟีเจอร์นี้ — ถ้าพลาดข้อนี้ ก็ได้หน้าจอตั้งค่าที่กดแล้วไม่มีอะไรเกิดขึ้น)

ตาม docs/rules/testing.md: ตรวจ DB ตรง ๆ ผ่าน `db_pool` ไม่เชื่อ HTTP response
"""
import base64
import importlib
import json
import random
from datetime import datetime, timezone

import pytest
import pytest_asyncio

from core.config import settings
from services import app_settings_service, auth_service, notification_service, push_service

BKK = app_settings_service.BKK


def _covering_now() -> dict:
    """ช่วงเวลาที่ **ครอบเวลาปัจจุบันเสมอ** (เวลาไทย) — ใช้เมื่อเทสต์ต้องการ "ตอนนี้อยู่ในช่วงปิด"

    ⭐ **ทำไมไม่ hardcode "00:00–23:59":** ช่วงนั้นมีรู 1 นาทีต่อวัน (นาทีที่ 23:59 ซึ่ง
       `minutes >= 1439` ไม่จริง ⇒ ไม่ถือว่าอยู่ในช่วง) ⇒ เทสต์จะ **ล้มแบบสุ่มวันละครั้ง**
       ซึ่งเป็นความล้มเหลวที่แย่ที่สุด เพราะทำซ้ำยากและดูเหมือนความผิดพลาดของโค้ด
       ⇒ คำนวณจากนาฬิกาจริงแทน: เริ่มก่อน 5 นาที จบหลัง 10 นาที (ข้ามเที่ยงคืนก็ได้)

    ⚠️ ความกว้าง 15 นาที > เวลาที่เทสต์ใช้จริง (ไม่กี่วินาที) ⇒ ไม่มีทางหลุดกลางทาง
    """
    cur = datetime.now(BKK)
    minutes = cur.hour * 60 + cur.minute
    fmt = app_settings_service._fmt_hhmm
    return {
        "enabled": True,
        "start": fmt((minutes - 5) % app_settings_service._MINUTES_PER_DAY),
        "end": fmt((minutes + 10) % app_settings_service._MINUTES_PER_DAY),
    }


# ============================================================
# 0) Fixture — 2 คน: นักเรียน (ไม่มีสิทธิ์) + แอดมิน (is_admin ⇒ ผ่าน require_permission_anywhere)
# ============================================================

@pytest_asyncio.fixture
async def qh_world(db_pool):
    """room + student + admin — พอสำหรับทดสอบทั้ง auth และ permission

    ⚠️ `class_role="admin"` ⇒ `is_admin = TRUE` (มาจาก config/roles.json) ⇒
       `require_permission_anywhere` ผ่านโดยไม่ต้องอ่าน `permissions` array
    """
    room_code = f"บ.{random.randint(1, 90)}"
    async with db_pool.acquire() as conn:
        room_id = await conn.fetchval(
            "INSERT INTO rooms (room_code, room_name, level) VALUES ($1,$2,'ม.5') RETURNING id",
            room_code, room_code,
        )

    users = {}
    for label, role, no in [("student", "student", 1), ("admin", "admin", 2)]:
        sid = f"P{random.randint(1000, 9999)}{label[:2].upper()}"
        uid = await auth_service.register_user(
            db_pool, sid, "1234", f"{label} ทดสอบ", sid, room_code, no, role
        )
        users[label] = {
            "user_id": uid,
            "token": auth_service.create_access_token(uid),
            "room_id": room_id,
        }
    return users


def _auth(world, who="student"):
    return {"Authorization": f"Bearer {world[who]['token']}"}


async def _setting_row(db_pool):
    """อ่านค่าดิบจาก `app_settings` (deep-DB) — คืน `None` ถ้ายังไม่มีแถว"""
    async with db_pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM app_settings WHERE key = $1", app_settings_service.QUIET_HOURS_KEY
        )


async def _count(db_pool, table: str, where: str = "TRUE", *params) -> int:
    async with db_pool.acquire() as conn:
        return await conn.fetchval(f"SELECT COUNT(*) FROM {table} WHERE {where}", *params)


async def _audit_rows(db_pool):
    async with db_pool.acquire() as conn:
        return await conn.fetch(
            "SELECT * FROM audit_logs WHERE action = 'UPDATE_QUIET_HOURS' ORDER BY id"
        )


async def _seed_setting(db_pool, value: dict, *, user_id: int) -> None:
    """เขียนค่าตั้ง **ตรงเข้า DB ข้าม service** — สำหรับเทสต์ฝั่ง worker ที่ไม่ต้องล็อกอิน

    ⚠️ ต้อง `json.dumps` แล้ว cast `$2::jsonb` (ไม่ส่ง dict ตรง ๆ เพราะ asyncpg ไม่รู้จักชนิด)
    """
    async with db_pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO app_settings (key, value, description, updated_by)
               VALUES ($1, $2::jsonb, 'seed', $3)
               ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()""",
            app_settings_service.QUIET_HOURS_KEY, json.dumps(value), user_id,
        )


# ============================================================
# 1) ตรรกะบริสุทธิ์ — ไม่ต้องมี DB
# ============================================================

@pytest.mark.parametrize(
    "raw, expected",
    [
        ("00:00", 0),
        ("22:00", 1320),
        ("23:59", 1439),
        ("6:30", 390),          # ไม่มี 0 นำหน้า — ต้องรับได้
        ("  22:00  ", 1320),    # ช่องว่างหัวท้าย
        ("24:00", None),        # ชั่วโมงเกิน
        ("22:60", None),        # นาทีเกิน
        ("-1:00", None),
        ("22", None),           # ไม่มี ":"
        ("22:00:00", None),     # สามส่วน
        ("", None),
        (None, None),
        (1320, None),           # ไม่ใช่ string
    ],
)
def test_parse_hhmm(raw, expected):
    """`_parse_hhmm` — ด่านเดียวที่นิยามว่า "เวลาที่ใช้ได้" คืออะไร

    ⚠️ `QuietHoursUpdateRequest` **ไม่มี pattern โดยเจตนา** — ถ้าใส่ pattern ที่ schema
       จะกลายเป็นนิยามที่สองที่ไม่ตรงกับตัวนี้ (ผู้ใช้เจอ 422 ทั้งที่ระบบรองรับ "7:00")
    """
    assert app_settings_service._parse_hhmm(raw) == expected


def test_parse_fmt_roundtrip():
    """`_fmt_hhmm` เป็นทิศทางกลับของ `_parse_hhmm` — เติม 0 นำหน้าให้เสมอ"""
    fmt = app_settings_service._fmt_hhmm
    assert fmt(1320) == "22:00"
    assert fmt(0) == "00:00"
    assert fmt(390) == "06:30"
    for m in (0, 1, 59, 60, 719, 1439):
        assert app_settings_service._parse_hhmm(fmt(m)) == m


def test_normalize_no_row_is_disabled():
    """ไม่มีค่า ⇒ ปิด + ค่าเริ่มต้น (UI จะโชว์ค่านี้เป็น "คำแนะนำ" ไม่ใช่ค่าที่บังคับใช้)"""
    assert app_settings_service.normalize_quiet_hours(None) == {
        "enabled": False,
        "start": app_settings_service.DEFAULT_START,
        "end": app_settings_service.DEFAULT_END,
    }


@pytest.mark.parametrize(
    "raw",
    [
        "ไม่ใช่ json",
        '{"enabled": true}',                          # json ที่ไม่มี start/end
        "[]",                                          # json ที่ไม่ใช่ object
        '{"enabled": true, "start": "xx", "end": "06:00"}',
        '{"enabled": true, "start": 22, "end": 6}',    # ตัวเลข ไม่ใช่ string
        b"\x00\x01",                                   # bytes ที่ไม่ใช่ json
        12345,
    ],
)
def test_normalize_corrupt_value_is_disabled_not_crash(raw):
    """⭐ **jsonb ที่เสีย = ปิดไว้ก่อน ห้ามเดา**

    ทางเลือกอีกทางคือเดา — ซึ่งถ้าเดาผิดจะกลายเป็น **ปิด push ทั้งโรงเรียน** ด้วยข้อมูลที่เสีย
    ⇒ เลือก "ปิดการปิดกั้น" (fail-open) โดยเจตนา

    ⚠️ asyncpg คืน jsonb เป็น **string** ในโปรเจคนี้ (บทเรียนใน skills.md) ⇒ ค่าที่เข้ามา
       ในชีวิตจริงคือ string ⇒ เทสต์นี้ยิง string ตรง ๆ จึงตรงกับเส้นทางจริง
    """
    out = app_settings_service.normalize_quiet_hours(raw)
    assert out["enabled"] is False
    assert out["start"] == app_settings_service.DEFAULT_START


def test_normalize_start_equals_end_forces_disabled():
    """`22:00–22:00` = ช่วงที่ไม่มีความยาว ⇒ ปิด แม้ `enabled` จะเป็น true

    (ชั้น API ปฏิเสธคำขอนี้อยู่แล้ว — ข้อนี้กันข้อมูลที่เขียนตรงเข้า DB)
    """
    out = app_settings_service.normalize_quiet_hours(
        '{"enabled": true, "start": "22:00", "end": "22:00"}'
    )
    assert out["enabled"] is False
    assert (out["start"], out["end"]) == ("22:00", "22:00")


def test_normalize_accepts_dict_and_normalizes_hhmm():
    """รับ dict ผ่านตรง ๆ ได้ และปรับ "7:00" → "07:00" ให้เป็นรูปเดียว"""
    assert app_settings_service.normalize_quiet_hours(
        {"enabled": True, "start": "7:00", "end": "9:00"}
    ) == {"enabled": True, "start": "07:00", "end": "09:00"}


# ⭐ ตารางเวลาที่สำคัญที่สุดของไฟล์นี้ — "ข้ามเที่ยงคืน" คือกรณีที่พลาดง่ายที่สุด
@pytest.mark.parametrize(
    "start, end, thai_hhmm, expected",
    [
        # ── ช่วงข้ามเที่ยงคืน 22:00–06:00 (กรณีใช้งานจริงของโรงเรียน) ──
        ("22:00", "06:00", "23:59", True),
        ("22:00", "06:00", "22:00", True),    # ★ ขอบเริ่ม: รวม
        ("22:00", "06:00", "00:00", True),    # เที่ยงคืนตรง = อยู่ในช่วง
        ("22:00", "06:00", "05:59", True),
        ("22:00", "06:00", "06:00", False),   # ★ ขอบจบ: ไม่รวม
        ("22:00", "06:00", "12:00", False),   # กลางวัน = ส่งปกติ
        ("22:00", "06:00", "21:59", False),   # ก่อนเริ่ม 1 นาที
        # ── ช่วงปกติ (ไม่ข้ามเที่ยงคืน) ──
        ("08:00", "12:00", "09:30", True),
        ("08:00", "12:00", "08:00", True),
        ("08:00", "12:00", "12:00", False),
        ("08:00", "12:00", "07:59", False),
        ("08:00", "12:00", "23:00", False),   # ★ ช่วงปกติต้อง **ไม่** ใช้ตรรกะข้ามคืน
        # ── ช่วงเกือบทั้งวัน ──
        ("00:01", "23:58", "12:00", True),
        ("00:01", "23:58", "00:00", False),   # ★ ขอบเขตล่างของช่วงนี้
        # ── start > end แต่เป็นช่วงสั้น ๆ คร่อมเที่ยงคืน ──
        ("23:30", "00:30", "23:45", True),
        ("23:30", "00:30", "00:15", True),
        ("23:30", "00:30", "01:00", False),
    ],
)
def test_quiet_hours_active_boundaries(start, end, thai_hhmm, expected):
    """⭐ ขอบเขตของช่วงเวลา — ตรวจว่า `[start, end)` เป็นครึ่งเปิด และข้ามคืนถูกต้อง

    mutation ที่ต้องทำให้แตก: เขียน `minutes <= end_min` หรือลืมสาขา `minutes < end_min`
        ของช่วงข้ามคืน → ขอบทั้งสองข้างพลาด
    """
    hour, minute = (int(p) for p in thai_hhmm.split(":"))
    # สร้างเป็น "เวลาไทย" แล้วแปลงกลับเป็น UTC ที่ตรงกัน (naive = UTC ตาม `_now_bkk`)
    now_utc = (
        datetime(2026, 9, 29, hour, minute, tzinfo=BKK)
        .astimezone(timezone.utc)
        .replace(tzinfo=None)
    )
    cfg = {"enabled": True, "start": start, "end": end}
    assert app_settings_service.quiet_hours_active(cfg, now=now_utc) is expected


def test_quiet_hours_active_uses_bangkok_not_server_time():
    """★ **เขตเวลาตายตัวที่ Asia/Bangkok** — เซิร์ฟเวอร์รัน UTC

    ⚠️ ถ้าใช้เวลาของเซิร์ฟเวอร์ตรง ๆ "22:00" จะหมายถึงตี 5 ไทย ⇒ กลางคืนทั้งคืนไม่ถูกปิด
       และเทสต์นี้คือด่านเดียวที่จับได้
    """
    cfg = {"enabled": True, "start": "22:00", "end": "06:00"}
    # 15:00 UTC = 22:00 ไทย → ต้องเข้าช่วงทันที
    assert app_settings_service.quiet_hours_active(cfg, now=datetime(2026, 9, 29, 15, 0)) is True
    # 14:00 UTC = 21:00 ไทย → ยังไม่เข้า
    assert app_settings_service.quiet_hours_active(cfg, now=datetime(2026, 9, 29, 14, 0)) is False


@pytest.mark.parametrize(
    "cfg",
    [
        None,
        {"enabled": False, "start": "00:00", "end": "23:59"},
        {"enabled": True, "start": "22:00", "end": "22:00"},   # ความยาวศูนย์
        {"enabled": True, "start": "bad", "end": "06:00"},
        {"enabled": True},                                     # ไม่มี start/end
    ],
)
def test_quiet_hours_active_disabled_shapes(cfg):
    """ทุกรูปที่ "ไม่ปิดกั้น" ต้องคืน False — ไม่มีทางที่ค่าตั้งเสียแล้วปิด push ทั้งโรงเรียน"""
    assert app_settings_service.quiet_hours_active(cfg, now=datetime(2026, 9, 29, 16, 0)) is False


def test_quiet_hours_resumes_at_wraps_to_tomorrow():
    """`quiet_hours_resumes_at` — ใช้บอกใน log ว่า "จะกลับมาส่งกี่โมง" (เขตไทย)"""
    cfg = {"enabled": True, "start": "22:00", "end": "06:00"}
    resumes = app_settings_service.quiet_hours_resumes_at(cfg, now=datetime(2026, 9, 29, 16, 0))
    assert resumes is not None
    assert (resumes.hour, resumes.minute) == (6, 0)
    assert resumes.tzinfo == BKK
    # 23:00 ไทย → กลับมาส่ง 06:00 ของ **วันรุ่งขึ้น**
    assert resumes.date() == datetime(2026, 9, 30).date()


def test_quiet_hours_resumes_at_same_day_when_not_wrapped():
    """ช่วงปกติ (08:00–12:00) และตอนนี้ 09:00 ⇒ กลับมาส่ง 12:00 **วันเดียวกัน**"""
    cfg = {"enabled": True, "start": "08:00", "end": "12:00"}
    resumes = app_settings_service.quiet_hours_resumes_at(cfg, now=datetime(2026, 9, 29, 2, 0))
    assert resumes is not None
    assert (resumes.hour, resumes.minute) == (12, 0)
    assert resumes.date() == datetime(2026, 9, 29).date()


@pytest.mark.parametrize("cfg", [None, {"enabled": False, "start": "22:00", "end": "06:00"}])
def test_quiet_hours_resumes_at_none_when_not_active(cfg):
    """ไม่ได้ปิดอยู่ ⇒ `None` (ไม่ใช่เวลามั่ว)

    ไม่งั้น log จะรายงาน "จะกลับมาส่ง 06:00" ทั้งที่ไม่มีอะไรถูกระงับ
    """
    assert app_settings_service.quiet_hours_resumes_at(
        cfg, now=datetime(2026, 9, 29, 16, 0)
    ) is None


# ============================================================
# 2) HTTP — GET / PUT
# ============================================================

@pytest.mark.asyncio
async def test_get_without_row_returns_defaults(client, qh_world):
    """โรงเรียนยังไม่เคยตั้ง ⇒ `enabled=false` + ค่าเริ่มต้น + **`updated_at=null`**

    ⭐ `updated_at = null` คือสิ่งที่ UI ใช้แยก "ค่าเริ่มต้นที่เราเสนอ" ออกจาก
       "ตั้งไว้แล้วแต่ปิดสวิตช์" ⇒ ถ้าหายไป สองสภาพจะแยกไม่ออก (การ์ดจะขึ้น
       "ปิดอยู่ — ส่งแจ้งเตือนทุกเวลา" ทั้งที่โรงเรียนไม่เคยตั้งอะไรเลย)
    """
    res = client.get("/api/settings/quiet-hours", headers=_auth(qh_world, "student"))
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["enabled"] is False
    assert body["start"] == app_settings_service.DEFAULT_START
    assert body["end"] == app_settings_service.DEFAULT_END
    assert body["updated_at"] is None


@pytest.mark.asyncio
async def test_get_is_open_to_every_authenticated_user(client, qh_world, db_pool):
    """⭐ **GET เปิดให้ทุกคน** — ต่างจาก `/terms` โดยเจตนา

    เหตุผล: ค่านี้มีไว้ **อธิบายให้นักเรียนเข้าใจว่าทำไมมือถือเงียบ**
    ถ้าปิดการอ่าน = ซ่อนคำอธิบายจากคนที่ได้รับผลกระทบพอดี (และมันมีแค่ช่วงเวลา)

    ⚠️ ต้องยืนยันด้วยว่า **นักเรียนอ่านได้โดยไม่สร้างแถว** — GET ต้องไม่มี side effect
       (ถ้าเผลอ upsert ตอนอ่าน ค่าที่อ่านได้จะกลายเป็นค่าที่ถูกเขียน ซึ่งตรวจย้อนหลังไม่ได้)
    """
    assert client.get(
        "/api/settings/quiet-hours", headers=_auth(qh_world, "student")
    ).status_code == 200
    assert await _setting_row(db_pool) is None


@pytest.mark.asyncio
async def test_put_requires_manage_settings(client, qh_world, db_pool):
    """นักเรียน PUT ไม่ได้ → 403 · **และ DB ต้องไม่ถูกแตะเลย**"""
    res = client.put(
        "/api/settings/quiet-hours",
        headers=_auth(qh_world, "student"),
        json={"enabled": True, "start": "22:00", "end": "06:00"},
    )
    assert res.status_code == 403, res.text
    # 403 ต้องแปลว่า "ไม่เกิดขึ้นเลย" ไม่ใช่ "เกิดแล้วแต่ตอบ 403"
    assert await _setting_row(db_pool) is None
    assert await _audit_rows(db_pool) == []


@pytest.mark.asyncio
async def test_put_then_get_roundtrip(client, db_pool, qh_world):
    """PUT (admin) → 200 + **deep-DB assert** ว่าแถวเกิดจริงและค่าตรง"""
    res = client.put(
        "/api/settings/quiet-hours",
        headers=_auth(qh_world, "admin"),
        json={"enabled": True, "start": "22:00", "end": "06:00"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["enabled"] is True
    assert (body["start"], body["end"]) == ("22:00", "06:00")
    assert body["updated_at"] is not None, "PUT สำเร็จต้องมี updated_at — UI ใช้แยกจากค่าเริ่มต้น"

    row = await _setting_row(db_pool)
    assert row is not None, "แถวต้องเกิดจริงใน app_settings"
    assert row["key"] == app_settings_service.QUIET_HOURS_KEY
    assert row["updated_by"] == qh_world["admin"]["user_id"]
    # jsonb ถูกคืนเป็น string ในโปรเจคนี้ ⇒ ตรวจผ่าน normalizer (ไม่ parse เอง)
    assert app_settings_service.normalize_quiet_hours(row["value"]) == {
        "enabled": True, "start": "22:00", "end": "06:00",
    }

    # อ่านซ้ำผ่าน HTTP ต้องได้ค่าเดียวกัน (source of truth เดียว)
    again = client.get("/api/settings/quiet-hours", headers=_auth(qh_world, "student"))
    assert again.status_code == 200
    assert again.json()["enabled"] is True


@pytest.mark.asyncio
async def test_put_writes_audit_log_in_same_transaction(client, db_pool, qh_world):
    """⭐ audit ต้องถูกเขียน — **ต่างจาก A2 (การตั้งค่าส่วนตัว) โดยเจตนา**

    A2 ไม่เขียน audit เพราะเป็นค่าส่วนตัวของคนคนเดียว · ที่นี่เป็น **ค่าของทั้งโรงเรียน**
    ⇒ ต้องตอบได้ว่า "ใครปิด push ทั้งโรงเรียนเมื่อไร"
    """
    res = client.put(
        "/api/settings/quiet-hours",
        headers=_auth(qh_world, "admin"),
        json={"enabled": True, "start": "22:00", "end": "06:00"},
    )
    assert res.status_code == 200, res.text

    rows = await _audit_rows(db_pool)
    assert len(rows) == 1, "ต้องมี audit log 1 แถวต่อการเขียน 1 ครั้ง"
    assert rows[0]["user_id"] == qh_world["admin"]["user_id"]
    assert rows[0]["entity_type"] == "app_setting"
    assert rows[0]["entity_id"] == app_settings_service.QUIET_HOURS_KEY


@pytest.mark.asyncio
async def test_put_second_time_upserts_and_logs_old_values(client, db_pool, qh_world):
    """PUT ซ้ำ = **upsert** (ไม่ใช่แถวที่สอง) และ audit เก็บ `old_values` ของเดิมไว้

    mutation ที่ต้องทำให้แตก: ถอด `ON CONFLICT (key) DO UPDATE` → unique violation 500
    """
    headers = _auth(qh_world, "admin")
    assert client.put(
        "/api/settings/quiet-hours", headers=headers,
        json={"enabled": True, "start": "22:00", "end": "06:00"},
    ).status_code == 200
    assert client.put(
        "/api/settings/quiet-hours", headers=headers,
        json={"enabled": False, "start": "23:00", "end": "05:00"},
    ).status_code == 200

    assert await _count(db_pool, "app_settings", "key = $1",
                        app_settings_service.QUIET_HOURS_KEY) == 1, \
        "PUT ต้อง upsert ไม่ใช่สร้างแถวใหม่"

    rows = await _audit_rows(db_pool)
    assert len(rows) == 2
    # แถวที่สองต้องมีของเดิมติดมาด้วย — ไม่งั้นตอบไม่ได้ว่า "เปลี่ยนจากอะไร"
    assert rows[1]["old_values"] is not None
    assert "22:00" in str(rows[1]["old_values"])


@pytest.mark.asyncio
async def test_put_disable_keeps_the_window(client, db_pool, qh_world):
    """ปิดสวิตช์ ⇒ `enabled=false` แต่ **ช่วงเวลาที่ตั้งไว้ต้องยังอยู่**

    ⭐ เหตุผล: ผู้ที่ปิดแล้วเปิดใหม่ต้องได้ช่วงเวลาเดิม ไม่ต้องพิมพ์ใหม่
       ⇒ ถ้าล้างค่าเป็น 00:00 ทั้งคู่ "ปิดแล้วเปิด" จะกลายเป็นการเปลี่ยนค่าที่ตั้งไว้
    """
    headers = _auth(qh_world, "admin")
    client.put("/api/settings/quiet-hours", headers=headers,
               json={"enabled": True, "start": "22:00", "end": "06:00"})
    res = client.put("/api/settings/quiet-hours", headers=headers,
                     json={"enabled": False, "start": "22:00", "end": "06:00"})

    assert res.status_code == 200, res.text
    assert res.json()["enabled"] is False
    assert (res.json()["start"], res.json()["end"]) == ("22:00", "06:00")
    # ★ ยังต้องมี updated_at (แยกจาก "ยังไม่เคยตั้ง")
    assert res.json()["updated_at"] is not None
    assert await _count(db_pool, "app_settings", "key = $1",
                        app_settings_service.QUIET_HOURS_KEY) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_start, bad_end", [
    ("25:00", "06:00"),
    ("22:60", "06:00"),
    ("22", "06:00"),
    ("", "06:00"),
    ("เที่ยงคืน", "06:00"),
    ("22:00", "6:0:0"),
])
async def test_put_malformed_time_is_400(client, qh_world, bad_start, bad_end):
    """⭐ รูปแบบเวลาผิด ⇒ **400 (ไม่ใช่ 422)** พร้อมข้อความไทย

    ⚠️ `QuietHoursUpdateRequest` **ไม่มี pattern โดยเจตนา** — `_parse_hhmm()` เป็นนิยามเดียว
       ของ "เวลาที่ใช้ได้" และมันรับ `"7:00"` ด้วย ⇒ ถ้าใส่ pattern ที่ schema
       จะกลายเป็นสองนิยามที่ไม่ตรงกัน (ผู้ใช้เจอ 422 ทั้งที่ระบบรองรับ)
    """
    res = client.put(
        "/api/settings/quiet-hours",
        headers=_auth(qh_world, "admin"),
        json={"enabled": True, "start": bad_start, "end": bad_end},
    )
    assert res.status_code == 400, f"ควรเป็น 400 จาก service ไม่ใช่ 422 จาก schema: {res.text}"


@pytest.mark.asyncio
async def test_put_enabled_with_equal_times_is_400(client, db_pool, qh_world):
    """⭐ `enabled=true` + `start == end` ⇒ **400 พร้อมบอกสาเหตุ** ไม่ใช่ปิดเงียบ ๆ

    แผนแรกเขียนว่าจะ "บังคับปิด" — เปลี่ยนเป็นปฏิเสธ เพราะการปิดสวิตช์ที่ผู้ใช้เพิ่งเปิด
    โดยไม่บอกอะไรเลย จะเห็นเป็น "กดเปิดแล้วมันเด้งกลับ" โดยไม่รู้ว่าทำไม

    ⚠️ ต้องยืนยันด้วยว่า **ไม่เขียนแถว** — การปฏิเสธที่ทิ้งแถวไว้ครึ่งทางแย่กว่าการรับ
    """
    res = client.put(
        "/api/settings/quiet-hours",
        headers=_auth(qh_world, "admin"),
        json={"enabled": True, "start": "22:00", "end": "22:00"},
    )
    assert res.status_code == 400, res.text
    assert "เท่ากัน" in res.json()["detail"]
    assert await _setting_row(db_pool) is None, "400 ต้องไม่ทิ้งแถวไว้"


@pytest.mark.asyncio
async def test_put_disabled_with_equal_times_is_accepted(client, db_pool, qh_world):
    """แต่ `enabled=false` + `start == end` **ถูกต้อง** (ความหมายขึ้นกับ `enabled`)

    ⇒ ด่านต้องผูกกับ `enabled` ไม่ใช่ปฏิเสธ `start == end` เปล่า ๆ
       (ไม่งั้น "ปิดสวิตช์" จะทำไม่ได้เลยถ้าช่วงเวลาบังเอิญเท่ากัน)
    """
    res = client.put(
        "/api/settings/quiet-hours",
        headers=_auth(qh_world, "admin"),
        json={"enabled": False, "start": "22:00", "end": "22:00"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["enabled"] is False


@pytest.mark.asyncio
async def test_put_accepts_single_digit_hour(client, qh_world):
    """`"7:00"` ผ่านและถูกคืนเป็น `"07:00"` — ผู้ใช้ไม่ต้องพิมพ์ 0 นำหน้าเอง"""
    res = client.put(
        "/api/settings/quiet-hours",
        headers=_auth(qh_world, "admin"),
        json={"enabled": True, "start": "7:00", "end": "9:30"},
    )
    assert res.status_code == 200, res.text
    assert (res.json()["start"], res.json()["end"]) == ("07:00", "09:30")


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["get", "put"])
async def test_api_key_caller_gets_401_not_500(client, method):
    """⚠️ `X-API-Key` (system RPC) ⇒ `get_current_user` คืน `user_id=None`
    ⇒ ต้องได้ **401** จาก `_ensure_user()` ไม่ใช่ 500 จาก `require_permission_anywhere(None)`

    (บทเรียนเดียวกับ `issue_router.py:19` — และเทสต์นี้คือด่านที่จับได้)
    """
    kwargs = {"headers": {"X-API-Key": settings.API_KEY}}
    if method == "put":
        kwargs["json"] = {"enabled": True, "start": "22:00", "end": "06:00"}
    res = getattr(client, method)("/api/settings/quiet-hours", **kwargs)
    assert res.status_code == 401, res.text


@pytest.mark.asyncio
async def test_put_without_token_is_401(client, db_pool):
    """ไม่มี token เลย ⇒ 401 (ไม่ใช่ 403/500) และไม่มีอะไรถูกเขียน"""
    res = client.put("/api/settings/quiet-hours",
                     json={"enabled": True, "start": "22:00", "end": "06:00"})
    assert res.status_code == 401, res.text
    assert await _setting_row(db_pool) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [
    {"enabled": True, "start": "22:00"},              # ขาด end
    {"start": "22:00", "end": "06:00"},               # ขาด enabled
    {"enabled": True, "start": "22:00", "end": "06:00", "extra": 1},  # เกิน
])
async def test_put_field_shape(client, qh_world, payload):
    """PUT = full replace ⇒ ขาดฟิลด์ = 422 · แต่ฟิลด์เกินถูกละเว้น (ไม่ใช่ error)

    ⭐ ข้อที่สามโดยเจตนา: schema ที่ "เข้มเกิน" จะพังทันทีที่มีคนเพิ่มฟิลด์ฝั่ง client
       รุ่นใหม่ก่อน backend — ซึ่งเกิดบ่อยกว่าและเจ็บกว่า
    """
    res = client.put("/api/settings/quiet-hours",
                     headers=_auth(qh_world, "admin"), json=payload)
    expected = 422 if len(payload) < 3 else 200
    assert res.status_code == expected, res.text


# ============================================================
# 3) ผลจริงต่อ push worker — หัวใจของ A8
# ============================================================

@pytest.fixture(autouse=True)
def vapid_configured(monkeypatch):
    """ตั้งคีย์ VAPID ให้ทุกเทสต์ — `process_pending()` มีด่านแรก "ไม่มีคีย์ = ปิดทั้งคิว"

    ⚠️ ถ้าไม่ตั้ง ทุกเทสต์จะหยุดที่ด่านนั้นและ **ดูเหมือน "ผ่าน"** เพราะ stats ว่างเปล่า
       (กับดักเดียวกับที่ `test_push_outbox.py` จดไว้ — ที่นั่นเขียนว่า
       "ถ้าไม่มี fixture นี้ 6 เทสต์ล้มด้วย `stats['stale'] == 0`")
    """
    monkeypatch.setattr(settings, "VAPID_PUBLIC_KEY", "test-public-key")
    monkeypatch.setattr(settings, "VAPID_PRIVATE_KEY", "test-private-key")
    push_service._reset_vapid_cache()
    yield
    push_service._reset_vapid_cache()


async def _subscribe(db_pool, user_id: int, *, endpoint: str = None) -> str:
    """ให้ผู้รับมีอุปกรณ์ — **จำเป็นตั้งแต่ migration 019** (trigger กรองคนไม่มีอุปกรณ์ทิ้ง)"""
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


async def _notify_one(db_pool, *, user_id: int, group_type: str = "issue_mine") -> None:
    """เรียก `notify()` ตามสัญญา — `conn` ต้องอยู่ใน transaction ของ caller"""
    async with db_pool.acquire() as conn:
        async with conn.transaction():
            await notification_service.notify(
                conn,
                user_id=user_id, group_type=group_type, type="issue_update",
                title="ทดสอบ quiet hours", body="ข้อความ",
                entity_type="issue", entity_id=999001,
            )


async def _mark_bypass(db_pool, user_id: int) -> None:
    """ติดธง `bypass_quiet_hours` ให้แถวล่าสุดของผู้ใช้ — จำลองสิ่งที่ E2 ทำ

    ⚠️ ติด **หลัง** insert ได้ เพราะด่าน quiet hours อ่านธงตอน *ส่ง* (JOIN ใน
       `_load_payloads`) ไม่ใช่ตอนเข้าคิว ⇒ เทสต์นี้พิสูจน์ "ด่านอ่านธงรายแถว"
       ได้จริง โดยไม่ผูกกับว่าตอนนี้ `notify*` รับพารามิเตอร์นั้นแล้วหรือยัง
       (การ thread flag ผ่าน `notify*` มีเทสต์ของตัวเองในชุด E2)
    """
    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE notifications SET bypass_quiet_hours = TRUE WHERE user_id = $1",
            user_id,
        )


def _recorder(status=201):
    """sender ปลอม — **ห้ามมีเทสต์ที่ยิง HTTP จริง** (แผน §20.14 ข้อ 6)"""
    calls = []

    async def send(client, sub, payload, *, ttl):
        calls.append({"sub": sub, "payload": payload, "ttl": ttl})
        return status(sub) if callable(status) else status

    send.calls = calls
    return send


async def _outbox_rows(db_pool):
    async with db_pool.acquire() as conn:
        return await conn.fetch("SELECT * FROM push_outbox ORDER BY id")


@pytest.mark.asyncio
async def test_worker_suppresses_rows_during_quiet_hours(db_pool, qh_world):
    """⭐ **แถวที่ตกในช่วงถูกปิดด้วย `last_error='quiet-hours'` และไม่มีการยิง HTTP เลย**

    ⚠️ สามสิ่งที่ต้องจริงพร้อมกัน (ถ้าตรวจแค่ข้อเดียวจะผ่านทั้งที่พัง):
       1. `processed_at IS NOT NULL` + `last_error = 'quiet-hours'` (ปิดถาวร ไม่ค้างในคิว)
       2. `sender.calls == []` (**ไม่มี HTTP ออกไปเลย** — ไม่ใช่แค่ "ดูเหมือนปิด")
       3. `stats["quiet"] == 1` (ตัวนับ — ทำให้เหตุการณ์มองเห็นได้ใน log)
    """
    uid = qh_world["student"]["user_id"]
    await _subscribe(db_pool, uid)
    await _seed_setting(db_pool, _covering_now(), user_id=qh_world["admin"]["user_id"])
    await _notify_one(db_pool, user_id=uid)

    sender = _recorder()
    stats = await push_service.process_pending(db_pool, sender=sender)

    assert stats["claimed"] == 1
    assert stats["quiet"] == 1, "ต้องนับใน stats['quiet'] — ไม่งั้นเหตุการณ์นี้มองไม่เห็นใน log"
    assert stats["sent"] == 0
    assert sender.calls == [], "ปิดอยู่ต้องไม่ยิง HTTP ออกไปเลย"

    rows = await _outbox_rows(db_pool)
    assert len(rows) == 1
    assert rows[0]["processed_at"] is not None, "ต้องปิดแถว ไม่ใช่ค้างในคิว"
    assert rows[0]["last_error"] == "quiet-hours"
    assert rows[0]["processing_at"] is None


@pytest.mark.asyncio
async def test_worker_sends_normally_when_quiet_hours_disabled(db_pool, qh_world):
    """ด่าน "ปิด" ของประตูเดียวกัน — ปิดสวิตช์ ⇒ ส่งปกติ

    ⚠️ ต้องมีเทสต์คู่นี้เสมอ: เทสต์ที่พิสูจน์แค่ "ปิดได้" จะผ่านแม้โค้ดไปปิด push **ตลอดเวลา**
    """
    uid = qh_world["student"]["user_id"]
    await _subscribe(db_pool, uid)
    # ใช้ช่วงเดียวกับเทสต์ข้างบน แต่ `enabled = false` ⇒ ต้องไม่มีผลอะไรเลย
    disabled = {**_covering_now(), "enabled": False}
    await _seed_setting(db_pool, disabled, user_id=qh_world["admin"]["user_id"])
    await _notify_one(db_pool, user_id=uid)

    sender = _recorder()
    stats = await push_service.process_pending(db_pool, sender=sender)

    assert stats["quiet"] == 0
    assert stats["sent"] == 1
    assert len(sender.calls) == 1


@pytest.mark.asyncio
async def test_worker_sends_when_no_setting_row_exists(db_pool, qh_world):
    """⭐⭐ **ไม่มีแถวใน `app_settings` ⇒ ส่งปกติ** — ปรัชญา "ค่าตั้งต้น = ไม่ปิดกั้น"

    นี่คือเทสต์ที่กันความผิดพลาดร้ายแรงที่สุดของ A8: โรงเรียนที่ไม่เคยแตะการ์ดนี้
    ต้องไม่มีการปิด push แม้แต่วินาทีเดียว (ถ้า default เป็น "ปิดกลางคืน" แล้วบั๊ก
    ทำให้อ่านค่าไม่ได้ ก็จะกลายเป็นปิด push ทั้งโรงเรียนโดยไม่มีใครสั่ง)
    """
    uid = qh_world["student"]["user_id"]
    await _subscribe(db_pool, uid)
    await _notify_one(db_pool, user_id=uid)

    sender = _recorder()
    stats = await push_service.process_pending(db_pool, sender=sender)

    assert stats["quiet"] == 0
    assert stats["sent"] == 1


@pytest.mark.asyncio
async def test_corrupt_setting_does_not_silence_push(db_pool, qh_world):
    """⭐ ค่าใน DB เสียรูป (jsonb ที่ไม่มี start/end) ⇒ **ต้องไม่ปิด push**

    ทางเลือกคือเดา — ซึ่งถ้าเดาผิดจะกลายเป็นปิด push ทั้งโรงเรียนด้วยข้อมูลที่เสีย
    ⇒ `normalize_quiet_hours` เลือก "ปิดการปิดกั้น" (fail-open) โดยเจตนา
    """
    uid = qh_world["student"]["user_id"]
    await _subscribe(db_pool, uid)
    await _seed_setting(db_pool, {"enabled": True}, user_id=qh_world["admin"]["user_id"])
    await _notify_one(db_pool, user_id=uid)

    sender = _recorder()
    stats = await push_service.process_pending(db_pool, sender=sender)

    assert stats["quiet"] == 0, "ค่าที่อ่านไม่ได้ต้องไม่ถูกตีความว่า 'ปิดอยู่'"
    assert stats["sent"] == 1


@pytest.mark.asyncio
async def test_bypass_flag_escapes_quiet_hours(db_pool, qh_world):
    """⭐⭐ **E2: ประกาศฉุกเฉินทะลุ quiet hours ได้** — และพร้อมกันนั้นแถวปกติยังถูกกลืน

    ⚠️ ต้องมี **ทั้งสองอย่างในเทสต์เดียว** — ถ้าเทสต์แค่ "urgent ส่งได้" จะผ่านแม้
       ด่าน quiet hours ถูกถอดออกทั้งหมด (เพราะทุกอย่างส่งได้หมด)
    """
    uid = qh_world["student"]["user_id"]
    uid2 = qh_world["admin"]["user_id"]
    await _subscribe(db_pool, uid)
    await _subscribe(db_pool, uid2)
    await _seed_setting(db_pool, _covering_now(), user_id=uid2)

    await _notify_one(db_pool, user_id=uid)          # ปกติ → ถูกกลืน
    await _notify_one(db_pool, user_id=uid2)         # ปกติ → แล้วติดธงทีหลัง = ฉุกเฉิน
    await _mark_bypass(db_pool, uid2)

    sender = _recorder()
    stats = await push_service.process_pending(db_pool, sender=sender)

    assert stats["quiet"] == 1, "แถวปกติต้องถูกกลืนแม้มีแถวฉุกเฉินอยู่ในรอบเดียวกัน"
    assert stats["sent"] == 1, "แถวที่ติดธงต้องถูกส่ง"
    assert len(sender.calls) == 1

    rows = {r["user_id"]: r for r in await _outbox_rows(db_pool)}
    assert rows[uid]["last_error"] == "quiet-hours"
    assert rows[uid]["processed_at"] is not None
    assert rows[uid2]["last_error"] is None
    assert rows[uid2]["processed_at"] is not None


@pytest.mark.asyncio
async def test_bypass_column_defaults_to_false(db_pool, qh_world):
    """คอลัมน์ `bypass_quiet_hours` มีค่าเริ่มต้น FALSE — ทางเรียกเก่าไม่ต้องแก้

    ⚠️ ผูกกับข้อผูกพันใน `migrations/016_notification_preferences.py` L15-17:
       **เพิ่มคอลัมน์ ไม่ rename ของเดิม** ⇒ `notify()` ที่ไม่ส่ง flag ต้องไม่เปลี่ยนพฤติกรรม
    """
    uid = qh_world["student"]["user_id"]
    await _notify_one(db_pool, user_id=uid)
    async with db_pool.acquire() as conn:
        val = await conn.fetchval(
            "SELECT bypass_quiet_hours FROM notifications WHERE user_id = $1", uid
        )
    assert val is False


@pytest.mark.asyncio
async def test_quiet_rows_are_not_retried_and_do_not_grow_the_queue(db_pool, qh_world):
    """⭐ แถวที่ถูกกลืนต้อง **ไม่ถูกหยิบซ้ำ** และต้องไม่ถูกตีเป็น `stale`

    ⚠️ ทางเลือกที่แผนปฏิเสธคือ "ค้างแถวไว้ในคิว" (`next_attempt_at` เลื่อนออกไป)
       ซึ่งจะไปชนด่าน `PUSH_MAX_AGE_MINUTES` แล้ว **ทิ้งทุกแถวตอนพ้นช่วงพอดี**
       ⇒ เทสต์นี้พิสูจน์ว่าทางที่เลือกไม่ทิ้งของและไม่ค้าง

    ⚠️ ต้องแยกจาก `stale` ให้ได้ — "หายเพราะหมดอายุ" กับ "ระงับเพราะความเงียบ"
       ต้องไม่ถูกบันทึกเป็นค่าเดียวกัน ไม่งั้นอ่าน log ไม่ออกว่ามีของหายจริงหรือไม่
    """
    uid = qh_world["student"]["user_id"]
    await _subscribe(db_pool, uid)
    await _seed_setting(db_pool, _covering_now(), user_id=qh_world["admin"]["user_id"])
    await _notify_one(db_pool, user_id=uid)

    sender = _recorder()
    first = await push_service.process_pending(db_pool, sender=sender)
    assert first["quiet"] == 1
    assert first["stale"] == 0

    # รอบที่สองต้องไม่มีอะไรให้ทำเลย
    second = await push_service.process_pending(db_pool, sender=sender)
    assert second["claimed"] == 0, "แถวที่ถูกกลืนต้องไม่กลับเข้าคิว"
    assert second["quiet"] == 0

    rows = await _outbox_rows(db_pool)
    assert rows[0]["last_error"] == "quiet-hours", "ต้องเป็น quiet-hours ไม่ใช่ stale"
    assert rows[0]["attempts"] == 1, "นับเป็น 1 attempt (ถูก claim ครั้งเดียว) — ไม่ถูก retry"


@pytest.mark.asyncio
async def test_drain_counter_covers_quiet(db_pool, qh_world):
    """⭐ `drain()` ต้องส่งคีย์ `quiet` ต่อออกมา — ไม่งั้น `_log_stats` จะ `KeyError`

    ⚠️ นี่คือบั๊กที่เกิดขึ้นจริงตอนเขียนรอบนี้: เพิ่ม `quiet` ใน `_log_stats` แล้ว
       แต่ `drain()` ยังวนจาก dict `total` ของตัวเอง ⇒ `KeyError: 'quiet'`
       ทุก tick ที่ `claimed > 0` — คือ **ตอนที่มีงานจริงเท่านั้น** (ตอนว่างจะ early-return
       ผ่านไปได้) ⇒ เป็นบั๊กแบบ "ทำงานได้จนถึงวินาทีที่สำคัญที่สุด"
    """
    uid = qh_world["student"]["user_id"]
    await _subscribe(db_pool, uid)
    await _seed_setting(db_pool, _covering_now(), user_id=qh_world["admin"]["user_id"])
    await _notify_one(db_pool, user_id=uid)

    sender = _recorder()
    total = await push_service.drain(db_pool, sender=sender, deadline_seconds=5)

    assert "quiet" in total, "drain() ต้องคืนคีย์ quiet — _log_stats อ่านคีย์นี้ตรง ๆ"
    assert total["quiet"] == 1
    assert total["claimed"] == 1


# ============================================================
# 4) Migration — รันท้ายไฟล์โดยเจตนา (มัน DROP ตารางจริง)
# ============================================================

@pytest.mark.asyncio
async def test_migration_023_idempotent_and_restores_schema(db_pool):
    """จำลอง DB ที่ยังไม่มีตาราง → `upgrade()` 2 ครั้ง → ต้องได้ตารางคืนครบ

    ⚠️ เทสต์ที่ถอยสคีมากลับ **ต้องคืนสคีมาให้ครบเสมอ** ไม่งั้นเทสต์ไฟล์ถัดไปจะพังด้วย
       "relation does not exist" ซึ่งเป็นเหตุผลผิด (บทเรียนที่จดไว้ใน skills.md)
       · และ `conftest.clean_database` ทำ `TRUNCATE ... app_settings` โดยไม่มี
       `IF EXISTS` ⇒ ตารางหายเมื่อไหร่ ทุกเทสต์ถัดไปล้มทันที
    """
    mig = importlib.import_module("migrations.023_app_settings")

    async with db_pool.acquire() as conn:
        await conn.execute("DROP TABLE IF EXISTS app_settings CASCADE")
        assert await conn.fetchval(
            "SELECT to_regclass('public.app_settings') IS NULL"
        ) is True, "ต้องลบตารางได้จริงก่อนทดสอบ"

        await mig.upgrade(conn)
        await mig.upgrade(conn)   # idempotent — รันซ้ำต้องไม่ error

        assert await conn.fetchval(
            "SELECT to_regclass('public.app_settings') IS NOT NULL"
        ) is True

        # คอลัมน์ตรงสเปก (ชื่อ + NOT NULL) — 'value' ต้องเป็น jsonb จริง
        cols = {
            r["column_name"]: (r["data_type"], r["is_nullable"])
            for r in await conn.fetch(
                "SELECT column_name, data_type, is_nullable FROM information_schema.columns "
                "WHERE table_name = 'app_settings'"
            )
        }
        assert cols["key"][0] == "character varying"
        assert cols["value"] == ("jsonb", "NO")
        assert cols["updated_by"][1] == "YES", "updated_by ต้อง nullable (ON DELETE SET NULL)"

        # ★ ไม่มีแถว seed — "ไม่มีแถว = ไม่ปิดกั้นอะไร" คือสัญญาของ A8
        assert await conn.fetchval("SELECT COUNT(*) FROM app_settings") == 0
