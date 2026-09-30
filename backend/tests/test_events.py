"""
🎪 D1 — ระบบกิจกรรม + การลงทะเบียน/คิวสำรอง
============================================
สภาสร้างกิจกรรม → เผยแพร่ → นักเรียนลงทะเบียน · ที่นั่งเต็มเข้าคิวสำรอง **อัตโนมัติ**
→ ใครถอนที่นั่ง ระบบเลื่อนคิวถัดไปขึ้นมาแทนให้เอง

ทดสอบ 7 ระดับ:
  1) สิทธิ์ — `MANAGE_EVENTS` ต้องมาจาก **JSONB ของจริง** ไม่ใช่ `is_admin` เฉย ๆ
     (ผู้ใช้เลือก: backfill ให้ `council_president`/`teacher_council`/`admin` เท่านั้น
      ⇒ `council_member` ต้องถูกปฏิเสธ ต่างจาก migration 014 ที่ให้ทุกคน)
  2) สถานะสองแกน — `status` (draft/published/cancelled) **คนละมิติกับ** `deleted_at`
  3) ★ "แจ้งเฉพาะตอนกดเผยแพร่" — `publish_event` ต้องเป็น **ที่เดียว** ที่เรียก `notify*`
     ⇒ สร้าง/แก้ไขต้องไม่ทำให้ `notifications` หรือ `push_outbox` โตแม้แถวเดียว
  4) ★ คิวสำรอง — หัวใจของ D3 ที่รวมมาในรอบนี้:
     · กดซ้ำต้องไม่ทำให้คนที่มีที่นั่งแล้วตกไปเป็นคิวสำรอง (อ่านแถวตัวเอง **ก่อน** นับที่นั่ง)
     · กดซ้ำตอนเป็นคิวสำรองต้องไม่กระโดดคิว (registered_at ห้ามถูกเขียนทับ)
     · ตำแหน่งคิวต้องเทียบ **(registered_at, id)** ไม่ใช่ registered_at เดี่ยว ๆ
       (แถวที่ insert ใน transaction เดียวกันได้ NOW() เท่ากัน)
     · คนที่ "เป็นคิวสำรองอยู่แล้ว" ถอนตัว **ต้องไม่เลื่อนคิว** (ไม่มีที่นั่งให้ใคร)
  5) เขตเวลา — `datetime-local` ส่งมาแบบ naive ⇒ ต้องถูกตีเป็น `Asia/Bangkok` ไม่ใช่ UTC
  6) Audit — 8 action ใหม่ต้องลง `audit_logs` ใน transaction เดียวกัน + มีป้ายไทยครบ 2 ที่
  7) Migration 025 — idempotent + backfill ไม่เติมสิทธิ์ซ้ำ

ตาม docs/rules/testing.md: ทุก test ตรวจ DB ตรง ๆ ผ่าน db_pool ไม่เชื่อ HTTP response
"""
import importlib
import json
import random
from datetime import datetime, timedelta, timezone

import asyncpg

import pytest
import pytest_asyncio

from core.config import settings
from services import auth_service
from services import dashboard_service

# ============================================================
# Fixtures
# ============================================================

# `granted` = สมาชิกสภาที่ **ไม่ได้เป็น is_admin** แต่ได้สิทธิ์จาก JSONB ⇒ ถ้า service
# เผลอเช็คแต่ `is_admin` เทสต์ของมันจะพัง · `manager` = is_admin ⇒ ผ่านด้วย bypass
_ROLE_SPECS = (
    ("manager", "council_president"),
    ("granted", "council_member"),
    ("plain", "council_member"),
    ("alice", "student"),
    ("bob", "student"),
    ("carol", "student"),
)


@pytest_asyncio.fixture
async def ev_world(db_pool):
    """ผู้จัดการ 3 คน + นักเรียน 3 คน — `room_code=""` ⇒ students.room_id IS NULL

    (ไม่ต้องสร้างห้อง เพราะห้องไม่ได้เกี่ยวข้องกับกิจกรรมเลย และ
     `require_permission_anywhere` อ่านเฉพาะ `students` ที่ผูกกับ user_id เท่านั้น)
    """
    users = {}
    for label, role in _ROLE_SPECS:
        sid = f"S{random.randint(100000, 999999)}{label[:2].upper()}"
        uid = await auth_service.register_user(
            db_pool, sid, "1234", f"{label} ทดสอบ", sid, "", 0, role
        )
        users[label] = {
            "user_id": uid,
            "token": auth_service.create_access_token(uid),
            "student_id": sid,
        }

    async with db_pool.acquire() as conn:
        # ★ `granted` ได้สิทธิ์จาก **JSONB เท่านั้น** (is_admin ยังเป็น FALSE)
        await conn.execute(
            """
            UPDATE students
            SET permissions = COALESCE(permissions, '[]'::jsonb) || '["MANAGE_EVENTS"]'::jsonb
            WHERE user_id = $1
            """,
            users["granted"]["user_id"],
        )
    return users


def _auth(world, who="manager"):
    return {"Authorization": f"Bearer {world[who]['token']}"}


def _future(days=7):
    return datetime.now(timezone.utc) + timedelta(days=days)


def _body(**over):
    """body ตั้งต้นที่ใช้ได้จริง — ทับเฉพาะฟิลด์ที่เทสต์สนใจ"""
    payload = {
        "title": f"กิจกรรมทดสอบ {random.randint(1000, 9999)}",
        "description": "รายละเอียดกิจกรรม",
        "location": "หอประชุมพิริยาลัย",
        "event_date": _future(7).isoformat(),
        "capacity": None,
    }
    payload.update(over)
    return payload


def _create(client, world, who="manager", **over):
    res = client.post("/api/events", json=_body(**over), headers=_auth(world, who))
    assert res.status_code == 201, res.text
    return res.json()


def _publish(client, world, event_id, who="manager"):
    res = client.post(f"/api/events/{event_id}/publish", headers=_auth(world, who))
    assert res.status_code == 200, res.text
    return res.json()


def _register(client, world, event_id, who):
    return client.post(f"/api/events/{event_id}/register", headers=_auth(world, who))


def _cancel_reg(client, world, event_id, who):
    return client.delete(f"/api/events/{event_id}/register", headers=_auth(world, who))


async def _db_event(db_pool, event_id):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM events WHERE id = $1", event_id)


async def _db_reg(db_pool, event_id, user_id):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM event_registrations WHERE event_id = $1 AND user_id = $2",
            event_id, user_id,
        )


async def _count(db_pool, table):
    """นับทั้งตาราง — ชื่อตารางผ่าน whitelist เท่านั้น

    ⚠️ เขียนแบบ "ใส่เงื่อนไขเป็นพารามิเตอร์ $n IS NULL OR col = $n" ไม่ได้ เพราะแต่ละตาราง
    มีคอลัมน์ไม่เหมือนกัน (`push_outbox` ไม่มี `type`) และ Postgres วางแผนคิวรีทั้งประโยค
    **ก่อน** รู้ว่าพารามิเตอร์เป็น NULL ⇒ ยังไงก็ฟ้อง `column "type" does not exist`
    """
    assert table in (
        "notifications", "push_outbox", "audit_logs", "events", "event_registrations"
    ), f"ตาราง {table} ไม่อยู่ใน whitelist"
    async with db_pool.acquire() as conn:
        return await conn.fetchval(f"SELECT COUNT(*) FROM {table}")


async def _count_notifications(db_pool, ntype=None):
    async with db_pool.acquire() as conn:
        if ntype is None:
            return await conn.fetchval("SELECT COUNT(*) FROM notifications")
        return await conn.fetchval(
            "SELECT COUNT(*) FROM notifications WHERE type = $1", ntype
        )


async def _notified_ids(db_pool, ntype):
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT user_id FROM notifications WHERE type = $1 ORDER BY user_id", ntype
        )
    return sorted(r["user_id"] for r in rows)


def _as_utc(iso: str) -> datetime:
    """pydantic v2 เขียน UTC เป็น `Z` แต่ datetime.isoformat() เขียน `+00:00`
    ⇒ ต้องเทียบเป็น datetime ไม่ใช่เทียบสตริง (บทเรียน skills.md)"""
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


# สถานะ "ว่างเปล่า" ที่ `/my-registration` ต้องคืน **ทั้งก้อนเป๊ะ ๆ** (ยังไม่สมัคร / เพิ่งถอน)
#
# ⚠️ จงใจเทียบทั้ง dict ไม่ใช่เช็คทีละ key — เจตนาของเทสต์คือ "ไม่มีอะไรค้างอยู่เลย"
#    ⇒ ถ้าเพิ่มฟิลด์ใหม่ใน `MyRegistrationOut` แล้วสองเทสต์นี้พัง **นั่นคือสัญญาณที่ถูกต้อง**
#    (มีคนต้องมาตอบว่า "ว่าง" ยังแปลว่าว่างจริงไหม) ไม่ใช่ noise ที่ควรกดให้เงียบ
#    — ตอน D2 เพิ่ม `check_in_token`/`checked_in_at` ก็พังแบบนี้ แล้วคำตอบคือ "ยังว่างจริง"
_EMPTY_MY_REG = {
    "registered": False,
    "registration_id": None,
    "status": None,
    "queue_position": None,
    "check_in_token": None,
    "checked_in_at": None,
}


# ============================================================
# 1) สิทธิ์ — MANAGE_EVENTS ต้องมาจาก JSONB จริง
# ============================================================

@pytest.mark.asyncio
async def test_no_token_is_401(ev_world, client):
    assert client.get("/api/events").status_code == 401
    assert client.post("/api/events", json=_body()).status_code == 401


@pytest.mark.asyncio
async def test_api_key_gets_401_not_500(ev_world, client):
    """★ X-API-Key → get_current_user คืน user_id=None ⇒ `_ensure_user` ต้องดักเป็น 401

    ถ้าลืม จะกลายเป็น INSERT ที่ created_by = NULL แล้วได้ 500 แทน
    """
    res = client.post(
        "/api/events", json=_body(), headers={"X-API-Key": settings.API_KEY}
    )
    assert res.status_code == 401, res.text


@pytest.mark.asyncio
async def test_create_forbidden_without_permission(ev_world, client, db_pool):
    """`council_member` ไม่มี MANAGE_EVENTS และไม่ได้เป็น is_admin ⇒ 403"""
    res = client.post("/api/events", json=_body(), headers=_auth(ev_world, "plain"))
    assert res.status_code == 403, res.text

    async with db_pool.acquire() as conn:
        n = await conn.fetchval("SELECT COUNT(*) FROM events")
    assert n == 0, "403 แล้วต้องไม่มีแถวเกิด"


@pytest.mark.asyncio
async def test_create_allowed_with_explicit_permission(ev_world, client):
    """★ พิสูจน์ว่า "สิทธิ์ใน JSONB" ให้ผ่านได้จริง ไม่ใช่ผ่านเพราะ is_admin

    `granted` เป็น council_member (is_admin = FALSE) ที่ถูกเติม MANAGE_EVENTS ลง JSONB
    ⇒ ถ้า service เผลอเช็คแค่ is_admin เทสต์นี้จะได้ 403
    """
    res = client.post("/api/events", json=_body(), headers=_auth(ev_world, "granted"))
    assert res.status_code == 201, res.text


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path", [
    ("get", ""),
    ("get", "/{id}"),              # รอบ 4 — หน้าแก้ไข/หน้ารายชื่อผู้สมัคร
    ("get", "/{id}/registrations"),
    ("patch", "/{id}"),
    ("post", "/{id}/publish"),
    ("post", "/{id}/cancel"),
    ("delete", "/{id}"),
    ("post", "/{id}/restore"),
])
async def test_manage_endpoints_all_403_without_permission(
    ev_world, client, method, path
):
    """ทุก endpoint ฝั่งผู้จัดการต้องกั้นด้วยสิทธิ์เดียวกัน (ไม่มีช่องที่ลืมกั้น)"""
    event_id = _create(client, ev_world)["id"]
    url = f"/api/events{path}".replace("{id}", str(event_id))
    kwargs = {"json": {"title": "แก้"}} if method == "patch" else {}
    res = getattr(client, method)(url, headers=_auth(ev_world, "plain"), **kwargs)
    assert res.status_code == 403, f"{method.upper()} {url} → {res.status_code}"


# ============================================================
# 2) สร้างกิจกรรม — เกิดเป็นฉบับร่าง และยังไม่แจ้งใคร
# ============================================================

@pytest.mark.asyncio
async def test_create_makes_draft_and_notifies_nobody(ev_world, client, db_pool):
    """★ หัวใจของคำตอบผู้ใช้: "แจ้งเฉพาะตอนกดเผยแพร่ ไม่ใช่ตอนสร้าง" """
    res = client.post("/api/events", json=_body(), headers=_auth(ev_world))
    assert res.status_code == 201, res.text
    out = res.json()

    assert out["status"] == "draft"
    assert out["published_at"] is None
    assert out["deleted_at"] is None

    row = await _db_event(db_pool, out["id"])
    assert row["status"] == "draft", "deep DB: ต้องเป็น draft จริง"
    assert row["published_at"] is None
    assert row["created_by"] == ev_world["manager"]["user_id"]

    assert await _count(db_pool, "notifications") == 0
    assert await _count(db_pool, "push_outbox") == 0


@pytest.mark.asyncio
async def test_create_ignores_status_in_body(ev_world, client, db_pool):
    """ส่ง `status` มาในฟอร์มสร้างไม่ได้ — schema ไม่รับ และต้องไม่หลุดลง DB"""
    res = client.post(
        "/api/events",
        json=_body(status="published", published_at=_future(0).isoformat()),
        headers=_auth(ev_world),
    )
    assert res.status_code == 201, res.text
    assert res.json()["status"] == "draft"
    assert (await _db_event(db_pool, res.json()["id"]))["status"] == "draft"


@pytest.mark.asyncio
async def test_create_deadline_after_event_is_400(ev_world, client, db_pool):
    event_date = _future(7)
    res = client.post(
        "/api/events",
        json=_body(event_date=event_date.isoformat(),
                   registration_deadline=(event_date + timedelta(days=1)).isoformat()),
        headers=_auth(ev_world),
    )
    assert res.status_code == 400, res.text
    assert "กำหนดปิดรับสมัคร" in res.json()["detail"]

    async with db_pool.acquire() as conn:
        n = await conn.fetchval("SELECT COUNT(*) FROM events")
    assert n == 0, "validation ต้องเกิดก่อน acquire connection ⇒ ไม่มีแถวตกค้าง"


@pytest.mark.asyncio
async def test_create_deadline_equal_event_date_is_ok(ev_world, client):
    """ขอบเขต: เท่ากันได้ (ปิดรับพร้อมเริ่มกิจกรรม)"""
    same = _future(7)
    res = client.post(
        "/api/events",
        json=_body(event_date=same.isoformat(), registration_deadline=same.isoformat()),
        headers=_auth(ev_world),
    )
    assert res.status_code == 201, res.text


@pytest.mark.asyncio
@pytest.mark.parametrize("over", [
    {"title": "   "},
    {"title": ""},
    {"location": "ก" * 201},
    {"cover_image_url": "javascript:alert(1)"},
    {"cover_image_url": "ftp://x/y.png"},
    {"capacity": 0},
    {"capacity": -1},
    {"capacity": 100001},
    {"event_date": None},
])
async def test_create_validation_422(ev_world, client, over):
    res = client.post("/api/events", json=_body(**over), headers=_auth(ev_world))
    assert res.status_code == 422, f"{over} → {res.status_code} {res.text}"


@pytest.mark.asyncio
async def test_create_accepts_blank_cover_as_none(ev_world, client, db_pool):
    out = _create(client, ev_world, cover_image_url="   ")
    assert out["cover_image_url"] is None
    assert (await _db_event(db_pool, out["id"]))["cover_image_url"] is None


@pytest.mark.asyncio
async def test_create_stamps_naive_datetime_as_bangkok(ev_world, client):
    """★ `<input type="datetime-local">` ส่งมาไม่มี tz ⇒ ต้องตีเป็นเวลาไทย (+07:00)

    ถ้าปล่อยเป็น naive ตรง ๆ asyncpg จะโยน DataError ตอน execute = **500 แทน 400**
    และถ้าไปตีเป็น UTC เงียบ ๆ กิจกรรมจะเลื่อนไป 7 ชั่วโมงโดยไม่มีใครรู้
    """
    out = _create(client, ev_world, event_date="2026-12-01T09:00")
    assert _as_utc(out["event_date"]) == datetime(2026, 12, 1, 2, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_create_preserves_explicit_offset(ev_world, client):
    """ส่ง tz มาเองแล้วต้องไม่ถูกตีความใหม่"""
    out = _create(client, ev_world, event_date="2026-12-01T09:00:00+00:00")
    assert _as_utc(out["event_date"]) == datetime(2026, 12, 1, 9, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_create_writes_audit_in_same_transaction(ev_world, client, db_pool):
    event_id = _create(client, ev_world)["id"]
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT entity_type, entity_id, actor_identifier FROM audit_logs
            WHERE action = 'CREATE_EVENT' AND entity_id = $1
            """,
            # ⚠️ `audit_logs.entity_id` เป็น **VARCHAR(50)** ไม่ใช่ integer
            #    (`init_db.py` · logger เขียนผ่าน `_text()` = `str()`) ⇒ ส่ง int ไปจะได้
            #    `DataError: expected str, got int` ไม่ใช่ "ไม่พบแถว"
            str(event_id),
        )
    assert row is not None, "CREATE_EVENT ต้องถูกบันทึกพร้อมแถว"
    assert row["entity_type"] == "event"
    assert row["actor_identifier"] == str(ev_world["manager"]["user_id"])


# ============================================================
# 3) เผยแพร่ — ที่เดียวที่ยิงแจ้งเตือน
# ============================================================

@pytest.mark.asyncio
async def test_publish_notifies_everyone_except_publisher(ev_world, client, db_pool):
    """fan-out ไปทุก active student ยกเว้นคนที่กดเผยแพร่ (actor_id self-exclude)"""
    event_id = _create(client, ev_world)["id"]
    out = _publish(client, ev_world, event_id)

    assert out["status"] == "published"
    assert out["published_at"] is not None

    expected = {
        ev_world[k]["user_id"]
        for k in ("granted", "plain", "alice", "bob", "carol")
    }
    assert set(await _notified_ids(db_pool, "event_published")) == expected
    assert ev_world["manager"]["user_id"] not in expected

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT group_type, entity_type, entity_id FROM notifications WHERE type = 'event_published' LIMIT 1"
        )
    assert row["group_type"] == "event"
    assert row["entity_type"] == "event"
    assert row["entity_id"] == event_id


@pytest.mark.asyncio
async def test_publish_is_the_only_notify_site(ev_world, client, db_pool):
    """★ สร้าง + แก้ไข (หลายรอบ) ต้องไม่ทำให้ notification/outbox โตเลย"""
    event_id = _create(client, ev_world)["id"]
    for i in range(3):
        res = client.patch(
            f"/api/events/{event_id}", json={"title": f"แก้ครั้งที่ {i}"},
            headers=_auth(ev_world),
        )
        assert res.status_code == 200, res.text

    assert await _count(db_pool, "notifications") == 0
    assert await _count(db_pool, "push_outbox") == 0

    _publish(client, ev_world, event_id)
    assert await _count_notifications(db_pool, "event_published") == 5


@pytest.mark.asyncio
async def test_publish_past_event_is_400(ev_world, client, db_pool):
    """ร่างที่วันจัดผ่านไปแล้วต้องประกาศไม่ได้ — กันประกาศทั้งโรงเรียนที่กู้คืนไม่ได้"""
    event_id = _create(
        client, ev_world, event_date=(datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    )["id"]
    res = client.post(f"/api/events/{event_id}/publish", headers=_auth(ev_world))
    assert res.status_code == 400, res.text
    assert "ผ่านไปแล้ว" in res.json()["detail"]

    row = await _db_event(db_pool, event_id)
    assert row["status"] == "draft" and row["published_at"] is None
    assert await _count(db_pool, "notifications") == 0


@pytest.mark.asyncio
async def test_publish_twice_is_404(ev_world, client):
    event_id = _create(client, ev_world)["id"]
    _publish(client, ev_world, event_id)
    res = client.post(f"/api/events/{event_id}/publish", headers=_auth(ev_world))
    assert res.status_code == 404, res.text


@pytest.mark.asyncio
async def test_publish_cancelled_is_404(ev_world, client, db_pool):
    """ยกเลิกแล้ว = ไม่กลับมาเผยแพร่ซ้ำด้วยปุ่มเดิม (ต้องแก้สถานะผ่านทางอื่น)"""
    event_id = _create(client, ev_world)["id"]
    _publish(client, ev_world, event_id)
    assert client.post(f"/api/events/{event_id}/cancel", headers=_auth(ev_world)).status_code == 200

    res = client.post(f"/api/events/{event_id}/publish", headers=_auth(ev_world))
    assert res.status_code == 404, res.text
    assert (await _db_event(db_pool, event_id))["status"] == "cancelled"


@pytest.mark.asyncio
async def test_patch_with_only_status_is_400(ev_world, client, db_pool):
    """★ PATCH ต้องเผยแพร่กิจกรรมไม่ได้เด็ดขาด (ไม่งั้นจะยิงแจ้งเตือนข้ามด่านไปได้)"""
    event_id = _create(client, ev_world)["id"]
    res = client.patch(
        f"/api/events/{event_id}", json={"status": "published"}, headers=_auth(ev_world)
    )
    assert res.status_code == 400, res.text
    assert "ไม่มีข้อมูลที่จะแก้ไข" in res.json()["detail"]
    assert (await _db_event(db_pool, event_id))["status"] == "draft"


@pytest.mark.asyncio
async def test_patch_with_title_and_status_keeps_draft(ev_world, client, db_pool):
    event_id = _create(client, ev_world)["id"]
    res = client.patch(
        f"/api/events/{event_id}",
        json={"title": "แก้ชื่อ", "status": "published", "published_at": _future(0).isoformat()},
        headers=_auth(ev_world),
    )
    assert res.status_code == 200, res.text
    row = await _db_event(db_pool, event_id)
    assert row["title"] == "แก้ชื่อ"
    assert row["status"] == "draft" and row["published_at"] is None
    assert await _count(db_pool, "notifications") == 0


@pytest.mark.asyncio
async def test_patch_validates_deadline_against_merged_values(ev_world, client):
    """★ PATCH เป็น partial ⇒ ต้อง merge ค่ากับของเดิม *ก่อน* ตรวจคู่เส้นตาย

    ส่งมาแค่ `registration_deadline` ที่หลัง `event_date` เดิม ⇒ ต้องได้ 400
    (ถ้าตรวจแค่ค่าที่ส่งมา จะผ่านเพราะไม่เห็น event_date)
    """
    event_date = _future(7)
    event_id = _create(client, ev_world, event_date=event_date.isoformat())["id"]

    res = client.patch(
        f"/api/events/{event_id}",
        json={"registration_deadline": (event_date + timedelta(days=2)).isoformat()},
        headers=_auth(ev_world),
    )
    assert res.status_code == 400, res.text


@pytest.mark.asyncio
async def test_patch_records_only_changed_fields_in_audit(ev_world, client, db_pool):
    event_id = _create(client, ev_world)["id"]
    client.patch(f"/api/events/{event_id}", json={"location": "โรงยิม"}, headers=_auth(ev_world))

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT old_values, new_values FROM audit_logs WHERE action = 'UPDATE_EVENT'"
        )
    # ⚠️ `old_values`/`new_values` เป็น **JSONB** แต่ asyncpg บน pool เปล่า ๆ (ไม่มี codec)
    #    คืนมาเป็น **`str`** ⇒ ต้อง `json.loads` ก่อน `.keys()` ไม่งั้นได้
    #    `AttributeError: 'str' object has no attribute 'keys'`
    new_values = json.loads(row["new_values"])
    old_values = json.loads(row["old_values"])
    assert set(new_values.keys()) == {"location"}
    assert set(old_values.keys()) == {"location"}


# ============================================================
# 4) ลงทะเบียน — ★ คิวสำรองต้องไม่ขยับผิดทาง
# ============================================================

@pytest.mark.asyncio
async def test_register_creates_row_and_returns_201(ev_world, client, db_pool):
    event_id = _create(client, ev_world)["id"]
    _publish(client, ev_world, event_id)

    res = _register(client, ev_world, event_id, "alice")
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["registered"] is True
    assert body["status"] == "registered"
    assert body["queue_position"] is None

    row = await _db_reg(db_pool, event_id, ev_world["alice"]["user_id"])
    assert row["status"] == "registered"
    assert row["cancelled_at"] is None


@pytest.mark.asyncio
async def test_register_twice_returns_200_same_row(ev_world, client, db_pool):
    """ดับเบิลแท็ปต้องไม่พังและไม่สร้างแถวซ้ำ"""
    event_id = _create(client, ev_world)["id"]
    _publish(client, ev_world, event_id)

    first = _register(client, ev_world, event_id, "alice")
    assert first.status_code == 201
    second = _register(client, ev_world, event_id, "alice")
    assert second.status_code == 200, second.text
    assert second.json()["registration_id"] == first.json()["registration_id"]

    async with db_pool.acquire() as conn:
        n = await conn.fetchval(
            "SELECT COUNT(*) FROM event_registrations WHERE event_id = $1 AND user_id = $2",
            event_id, ev_world["alice"]["user_id"],
        )
    assert n == 1


@pytest.mark.asyncio
async def test_full_event_seats_first_then_waitlists(ev_world, client, db_pool):
    """capacity = 1 ⇒ คนที่สองได้เป็นคิวสำรองพร้อมตำแหน่ง 1"""
    event_id = _create(client, ev_world, capacity=1)["id"]
    _publish(client, ev_world, event_id)

    assert _register(client, ev_world, event_id, "alice").json()["status"] == "registered"

    bob = _register(client, ev_world, event_id, "bob").json()
    assert bob["status"] == "waitlisted"
    assert bob["queue_position"] == 1


@pytest.mark.asyncio
async def test_waitlist_join_notifies_once_with_position(ev_world, client, db_pool):
    """⭐ D3 — **การเข้าคิวต้องมีข้อความบอก** เพราะระบบ "ลดขั้น" ให้เงียบ ๆ

    คนที่กดลงทะเบียนแล้วกิจกรรมเต็ม **ไม่ได้การ์ดที่ขอ** แต่ **ไม่เห็น error**
    (นโยบาย auto-waitlist ของ D1) ⇒ ถ้าไม่มี notification เขาจะเข้าใจว่าสมัครติด
    จนถึงวันงาน · และ **คนที่ได้ที่นั่งต้องไม่ได้ข้อความนี้** (เขาได้สิ่งที่ขอแล้ว)

    ตรึง 4 อย่างที่พลาดได้จริง:
      · ข้อความไปถึง **คนที่เข้าคิว** ไม่ใช่คนอื่น (และไม่ไปหาคนที่มีที่นั่ง)
      · `queue_position` ในข้อความตรงกับที่ API คืน (2 ที่นี้เคยเถียงกันได้)
      · **กดซ้ำไม่สร้างข้อความซ้ำ** — ขั้น 3 คืนค่าเดิมก่อนถึงจุดแจ้ง ⇒ ต้องได้ 1 ใบ
      · `actor_id IS NULL` — ระบบเป็นคนพูด ไม่ใช่ตัวผู้ใช้ (ไม่งั้น `notify()` กรองทิ้ง
        ด้วยกฎ "ไม่สแปมตัวเอง" แล้วข้อความจะ **หายทั้งใบโดยไม่มี error**)

    mutation ที่ต้องทำให้แตก: ลบ `notification_service.notify(...)` ใน
    `register_event()` (สาขา `new_status == "waitlisted"`)
    """
    event_id = _create(client, ev_world, capacity=1)["id"]
    _publish(client, ev_world, event_id)

    _register(client, ev_world, event_id, "alice")  # ได้ที่นั่ง
    bob = _register(client, ev_world, event_id, "bob").json()
    carol = _register(client, ev_world, event_id, "carol").json()
    assert (bob["queue_position"], carol["queue_position"]) == (1, 2)

    # เฉพาะสองคนที่เข้าคิว — alice (เจ้าของที่นั่ง) ต้องไม่อยู่ในรายชื่อ
    assert await _notified_ids(db_pool, "event_waitlist_joined") == sorted([
        ev_world["bob"]["user_id"], ev_world["carol"]["user_id"],
    ])

    # กดซ้ำตอนเป็นคิวอยู่แล้ว → ไม่เขียน `registered_at` ทับ (เทสต์ข้างบนคุมไว้)
    # และ **ไม่แจ้งซ้ำ** — จำนวนต้องยังเท่าเดิม
    _register(client, ev_world, event_id, "bob")
    assert await _count_notifications(db_pool, "event_waitlist_joined") == 2

    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT user_id, group_type, entity_type, entity_id, actor_id, body
            FROM notifications WHERE type = 'event_waitlist_joined'
            ORDER BY user_id
            """
        )
    by_user = {r["user_id"]: r for r in rows}
    first = by_user[ev_world["bob"]["user_id"]]
    assert first["group_type"] == "event"
    assert (first["entity_type"], first["entity_id"]) == ("event", event_id)
    assert first["actor_id"] is None, "ระบบเป็นคนพูด — ถ้าใส่ actor_id = user_id จะถูกกรองทิ้ง"
    # ⚠️ ตำแหน่งในข้อความต้องตรงกับที่ API คืน ไม่ใช่ค่าที่คำนวณคนละจังหวะ
    assert "คิวที่ 1" in first["body"]
    assert "คิวที่ 2" in by_user[ev_world["carol"]["user_id"]]["body"]


@pytest.mark.asyncio
async def test_no_waitlist_notification_when_promoted_person_re_joins(
    ev_world, client, db_pool
):
    """คนที่ถูกเลื่อนขึ้นแล้ว "ไม่" ได้ข้อความเข้าคิว — คนละเหตุการณ์กันโดยสิ้นเชิง

    ลำดับ: bob เข้าคิว (ได้ข้อความ) → alice ถอน ⇒ bob ถูกเลื่อน (ได้ `promoted`)
    ⇒ ตอนนี้ bob มี **2 ใบ** คนละชนิด · ถ้าถอนแล้วสมัครใหม่ตอนเต็ม bob จะได้
    `joined` ใบที่สอง (คนละรอบ) — แต่ห้ามได้ `promoted` ซ้ำโดยไม่มีใครถอน

    ⚠️ เทสต์นี้กันความสับสนที่ **อ่านโค้ดไม่ออก**: สองไทป์นี้อยู่ใกล้กันใน `event_service`
       และใช้ปลายทางเดียวกัน ⇒ การสลับ `type=` ระหว่างสองจุดจะไม่มีอะไรพังเลย
       ถ้าไม่มีเทสต์ที่แยกสองเหตุการณ์ออกจากกัน
    """
    event_id = _create(client, ev_world, capacity=1)["id"]
    _publish(client, ev_world, event_id)

    _register(client, ev_world, event_id, "alice")
    _register(client, ev_world, event_id, "bob")
    cancelled = _cancel_reg(client, ev_world, event_id, "alice")
    assert cancelled.status_code == 200, cancelled.text

    bob_id = ev_world["bob"]["user_id"]
    assert await _notified_ids(db_pool, "event_waitlist_joined") == [bob_id]
    assert await _notified_ids(db_pool, "event_waitlist_promoted") == [bob_id]

    # bob มีที่นั่งแล้ว ⇒ สมัครซ้ำต้องไม่เกิดข้อความใด ๆ เพิ่ม (ทั้งสองชนิด)
    _register(client, ev_world, event_id, "bob")
    assert await _count_notifications(db_pool, "event_waitlist_joined") == 1
    assert await _count_notifications(db_pool, "event_waitlist_promoted") == 1


@pytest.mark.asyncio
async def test_re_register_on_full_event_does_not_demote_returning_user(
    ev_world, client, db_pool
):
    """★★ เทสต์สำคัญที่สุดของ D1

    alice ถือที่นั่งเดียวอยู่ · bob เป็นคิวสำรอง · **alice กดปุ่มลงทะเบียนซ้ำ**
    ⇒ alice ต้องยังเป็น `registered` ไม่ใช่ถูกคำนวณที่นั่งใหม่แล้วตกเป็นคิวสำรอง

    mutation: ย้ายการอ่านแถวตัวเองไปไว้ *หลัง* การนับที่นั่ง ⇒ alice กลายเป็น waitlisted
    (และที่นั่งเดียวจะว่างเปล่าโดยไม่มีใครได้ — หายนะที่ผู้ใช้เจอได้จริง)
    """
    event_id = _create(client, ev_world, capacity=1)["id"]
    _publish(client, ev_world, event_id)

    first = _register(client, ev_world, event_id, "alice").json()
    assert first["status"] == "registered"
    _register(client, ev_world, event_id, "bob")

    again = _register(client, ev_world, event_id, "alice")
    assert again.status_code == 200, again.text
    assert again.json()["status"] == "registered", "คนที่มีที่นั่งแล้วต้องไม่ถูกดึงลงคิวสำรอง"
    assert again.json()["registration_id"] == first["registration_id"]
    assert again.json()["queue_position"] is None

    row = await _db_reg(db_pool, event_id, ev_world["alice"]["user_id"])
    assert row["status"] == "registered"

    # และที่นั่งยังถูกจับอยู่จริง — bob ยังเป็นคิวสำรอง
    bob_row = await _db_reg(db_pool, event_id, ev_world["bob"]["user_id"])
    assert bob_row["status"] == "waitlisted"


@pytest.mark.asyncio
async def test_waitlisted_re_tap_does_not_jump_queue(ev_world, client, db_pool):
    """★ กดซ้ำตอนเป็นคิวสำรองต้องไม่เขียน `registered_at` ทับ = ไม่กระโดดคิว

    bob เป็นคิวที่ 1 · carol เป็นคิวที่ 2 · bob กดซ้ำ
    ⇒ bob ต้องยังเป็นคิวที่ 1 (ถ้าเขียน registered_at = NOW() เขาจะตกไปเป็นที่ 2)
    """
    event_id = _create(client, ev_world, capacity=1)["id"]
    _publish(client, ev_world, event_id)

    _register(client, ev_world, event_id, "alice")
    bob_first = _register(client, ev_world, event_id, "bob").json()
    carol = _register(client, ev_world, event_id, "carol").json()
    assert (bob_first["queue_position"], carol["queue_position"]) == (1, 2)

    # อ่านเวลาจริงจาก DB **ก่อน** กดซ้ำ — ค่านี้คือสิ่งที่ห้ามถูกเขียนทับ
    bob_before = await _db_reg(db_pool, event_id, ev_world["bob"]["user_id"])

    again = _register(client, ev_world, event_id, "bob")
    assert again.status_code == 200, again.text
    assert again.json()["status"] == "waitlisted"
    assert again.json()["queue_position"] == 1, "คิวต้องไม่ถูกดันไปข้างหลัง"

    bob_row = await _db_reg(db_pool, event_id, ev_world["bob"]["user_id"])
    assert bob_row["registered_at"] == bob_before["registered_at"], (
        "กดซ้ำแล้วห้ามเขียน registered_at ทับ — เขียนทับ = ตกไปต่อท้ายคิว"
    )

    # และลำดับยังเป็นจริงในตาราง: bob ต้องมาก่อน carol (ไม่ใช่แค่ตัวเลขที่ API บอก)
    carol_row = await _db_reg(db_pool, event_id, ev_world["carol"]["user_id"])
    assert bob_row["registered_at"] < carol_row["registered_at"]


@pytest.mark.asyncio
async def test_queue_position_uses_tuple_not_timestamp_alone(ev_world, client, db_pool):
    """★ ตำแหน่งคิวต้องเทียบ (registered_at, id) — แถวใน transaction เดียวกันได้ NOW() เท่ากัน

    บังคับให้ 3 แถวมี `registered_at` **เท่ากันเป๊ะ** ด้วย UPDATE ตรง ๆ (เลียนแบบ
    `executemany` / transaction เดียว) แล้วเช็คว่าลำดับยัง deterministic ตาม id
    ⇒ ถ้าโค้ดเทียบ `registered_at` เดี่ยว ๆ ตำแหน่งจะกลายเป็น 0 หรือกระโดดมั่ว
    """
    event_id = _create(client, ev_world, capacity=1)["id"]
    _publish(client, ev_world, event_id)
    _register(client, ev_world, event_id, "alice")
    _register(client, ev_world, event_id, "bob")
    _register(client, ev_world, event_id, "carol")

    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE event_registrations SET registered_at = TIMESTAMPTZ '2026-01-01 00:00:00+07'
            WHERE event_id = $1
            """,
            event_id,
        )

    res = client.get(
        f"/api/events/{event_id}/my-registration", headers=_auth(ev_world, "carol")
    )
    assert res.status_code == 200, res.text
    assert res.json()["queue_position"] == 2, "เวลาชนกันต้องเรียงด้วย id เป็นตัวตัดสิน"


@pytest.mark.asyncio
async def test_unlimited_capacity_registers_everyone(ev_world, client, db_pool):
    """★ capacity IS NULL = ไม่จำกัด ⇒ ต้องไม่เอา None ไปเทียบเลข (จะได้ TypeError = 500)"""
    event_id = _create(client, ev_world, capacity=None)["id"]
    _publish(client, ev_world, event_id)

    for who in ("alice", "bob", "carol"):
        res = _register(client, ev_world, event_id, who)
        assert res.status_code == 201, res.text
        assert res.json()["status"] == "registered"
        assert res.json()["queue_position"] is None

    async with db_pool.acquire() as conn:
        n = await conn.fetchval(
            "SELECT COUNT(*) FROM event_registrations WHERE event_id = $1 AND status = 'registered'",
            event_id,
        )
    assert n == 3


@pytest.mark.asyncio
async def test_capacity_boundary_last_seat_is_registered(ev_world, client, db_pool):
    """capacity = 2 ⇒ คนที่ 2 ได้ที่นั่งสุดท้าย (ใช้ `<` ไม่ใช่ `<=`)"""
    event_id = _create(client, ev_world, capacity=2)["id"]
    _publish(client, ev_world, event_id)
    assert _register(client, ev_world, event_id, "alice").json()["status"] == "registered"
    second = _register(client, ev_world, event_id, "bob").json()
    assert second["status"] == "registered", "ที่นั่งสุดท้ายต้องได้นั่ง ไม่ใช่ตกคิว"
    assert _register(client, ev_world, event_id, "carol").json()["status"] == "waitlisted"


@pytest.mark.asyncio
async def test_my_registration_when_none_is_200_false(ev_world, client):
    """★ "ยังไม่สมัคร" เป็นคำตอบที่ถูกต้อง ⇒ 200 ไม่ใช่ 404"""
    event_id = _create(client, ev_world)["id"]
    _publish(client, ev_world, event_id)

    res = client.get(
        f"/api/events/{event_id}/my-registration", headers=_auth(ev_world, "alice")
    )
    assert res.status_code == 200, res.text
    assert res.json() == _EMPTY_MY_REG


@pytest.mark.asyncio
@pytest.mark.parametrize("state,expected", [
    ("draft", "ยังไม่เปิดให้ลงทะเบียน"),
    ("cancelled", "ถูกยกเลิกแล้ว"),
])
async def test_register_on_unavailable_event_is_400(ev_world, client, db_pool, state, expected):
    event_id = _create(client, ev_world)["id"]
    if state == "cancelled":
        _publish(client, ev_world, event_id)
        client.post(f"/api/events/{event_id}/cancel", headers=_auth(ev_world))

    res = _register(client, ev_world, event_id, "alice")
    assert res.status_code == 400, res.text
    assert expected in res.json()["detail"]

    assert await _db_reg(db_pool, event_id, ev_world["alice"]["user_id"]) is None


@pytest.mark.asyncio
async def test_register_on_past_event_is_400(ev_world, client, db_pool):
    event_id = _create(
        client, ev_world, event_date=(datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    )["id"]
    # เผยแพร่ไม่ได้ (วันผ่านไปแล้ว) ⇒ เปิดสถานะเองเพื่อแยกทดสอบด่าน "ผ่านไปแล้ว" ของการสมัคร
    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE events SET status = 'published', published_at = NOW() WHERE id = $1", event_id
        )

    res = _register(client, ev_world, event_id, "alice")
    assert res.status_code == 400, res.text
    assert "ผ่านไปแล้ว" in res.json()["detail"]


@pytest.mark.asyncio
async def test_register_after_deadline_is_400(ev_world, client, db_pool):
    event_id = _create(
        client, ev_world, registration_deadline=(datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    )["id"]
    _publish(client, ev_world, event_id)

    res = _register(client, ev_world, event_id, "alice")
    assert res.status_code == 400, res.text
    assert "เลยกำหนดลงทะเบียนแล้ว" in res.json()["detail"]


@pytest.mark.asyncio
async def test_register_on_deleted_event_is_404(ev_world, client, db_pool):
    event_id = _create(client, ev_world)["id"]
    _publish(client, ev_world, event_id)
    assert client.delete(f"/api/events/{event_id}", headers=_auth(ev_world)).status_code == 200

    assert _register(client, ev_world, event_id, "alice").status_code == 404
    assert await _db_reg(db_pool, event_id, ev_world["alice"]["user_id"]) is None


@pytest.mark.asyncio
async def test_register_writes_audit(ev_world, client, db_pool):
    """การลงทะเบียนเป็น state ที่แชร์กันบนทรัพยากรจำกัด ⇒ ต้องมีร่องรอย"""
    event_id = _create(client, ev_world)["id"]
    _publish(client, ev_world, event_id)
    _register(client, ev_world, event_id, "alice")

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT actor_identifier, entity_type, entity_id FROM audit_logs
            WHERE action = 'REGISTER_EVENT'
            """
        )
    assert row is not None
    assert row["actor_identifier"] == str(ev_world["alice"]["user_id"])
    # `entity_id` เป็น VARCHAR(50) ⇒ เก็บ "3" ไม่ใช่ 3 (ดูเหตุผลที่เทสต์ CREATE_EVENT ข้างบน)
    assert row["entity_type"] == "event" and row["entity_id"] == str(event_id)


# ============================================================
# 5) ถอนการลงทะเบียน + เลื่อนคิว
# ============================================================

@pytest.mark.asyncio
async def test_cancel_promotes_next_and_notifies_them(ev_world, client, db_pool):
    """★ alice ถอนที่นั่ง → bob (คิวที่ 1) ได้ที่นั่ง + ได้รับแจ้งเตือน event_waitlist_promoted"""
    event_id = _create(client, ev_world, capacity=1)["id"]
    _publish(client, ev_world, event_id)
    _register(client, ev_world, event_id, "alice")
    _register(client, ev_world, event_id, "bob")
    _register(client, ev_world, event_id, "carol")

    res = _cancel_reg(client, ev_world, event_id, "alice")
    assert res.status_code == 200, res.text
    # หลังถอนต้องกลับมา "ว่างเปล่า" เหมือนยังไม่เคยสมัคร — ไม่เหลือร่องรอยของที่นั่งเดิม
    # (รวม `check_in_token` ที่ต้องหายไปด้วย ไม่งั้นคนที่ถอนแล้วยังถือบัตรเช็คอินได้)
    assert res.json() == _EMPTY_MY_REG

    alice_row = await _db_reg(db_pool, event_id, ev_world["alice"]["user_id"])
    assert alice_row["status"] == "cancelled" and alice_row["cancelled_at"] is not None

    bob_row = await _db_reg(db_pool, event_id, ev_world["bob"]["user_id"])
    assert bob_row["status"] == "registered", "คิวถัดไปต้องได้ที่นั่ง"

    carol_row = await _db_reg(db_pool, event_id, ev_world["carol"]["user_id"])
    assert carol_row["status"] == "waitlisted", "ต้องเลื่อนขึ้นมาแค่คนเดียว"

    assert await _notified_ids(db_pool, "event_waitlist_promoted") == [ev_world["bob"]["user_id"]]

    async with db_pool.acquire() as conn:
        n = await conn.fetchrow(
            "SELECT group_type, actor_id FROM notifications WHERE type = 'event_waitlist_promoted'"
        )
    assert n["group_type"] == "event"
    assert n["actor_id"] is None, "ข้อความมาจากระบบ ไม่ใช่จากคนที่ถอนตัว"

    # carol ต้องเห็นตัวเองเป็นคิวที่ 1 หลัง bob ได้ที่นั่ง
    # ⚠️ `client` เป็น `TestClient` แบบ **sync** ⇒ ห้าม `await` (จะได้ TypeError ทันที)
    pos = client.get(
        f"/api/events/{event_id}/my-registration", headers=_auth(ev_world, "carol")
    )
    assert pos.json()["queue_position"] == 1


@pytest.mark.asyncio
async def test_cancel_by_waitlisted_does_not_promote_anyone(ev_world, client, db_pool):
    """★ คนที่เป็นคิวสำรองถอนตัว **ต้องไม่** เลื่อนคิวให้ใคร

    ไม่มีที่นั่งว่างเกิดขึ้นเลย ⇒ ถ้าโค้ดเลื่อนคิวทุกครั้งที่ถอน carol จะได้ที่นั่ง
    ลอย ๆ ที่ไม่เคยมี (และ alice ยังนั่งอยู่)
    """
    event_id = _create(client, ev_world, capacity=1)["id"]
    _publish(client, ev_world, event_id)
    _register(client, ev_world, event_id, "alice")
    _register(client, ev_world, event_id, "bob")
    _register(client, ev_world, event_id, "carol")

    assert _cancel_reg(client, ev_world, event_id, "bob").status_code == 200

    bob_row = await _db_reg(db_pool, event_id, ev_world["bob"]["user_id"])
    assert bob_row["status"] == "cancelled"

    carol_row = await _db_reg(db_pool, event_id, ev_world["carol"]["user_id"])
    assert carol_row["status"] == "waitlisted", "ไม่มีที่นั่งว่าง ⇒ ห้ามเลื่อนคิว"

    assert await _count_notifications(db_pool, "event_waitlist_promoted") == 0


@pytest.mark.asyncio
async def test_cancel_when_not_registered_is_404(ev_world, client, db_pool):
    event_id = _create(client, ev_world)["id"]
    _publish(client, ev_world, event_id)
    res = _cancel_reg(client, ev_world, event_id, "alice")
    assert res.status_code == 404, res.text
    assert "ยังไม่ได้ลงทะเบียน" in res.json()["detail"]


@pytest.mark.asyncio
async def test_cancel_twice_is_404(ev_world, client):
    """ยกเลิกซ้ำ = "ยังไม่ได้ลงทะเบียน" เหมือนกัน (เจตนา — แยกสองกรณีไม่ได้)"""
    event_id = _create(client, ev_world)["id"]
    _publish(client, ev_world, event_id)
    _register(client, ev_world, event_id, "alice")

    assert _cancel_reg(client, ev_world, event_id, "alice").status_code == 200
    res = _cancel_reg(client, ev_world, event_id, "alice")
    assert res.status_code == 404, res.text
    assert "ยังไม่ได้ลงทะเบียน" in res.json()["detail"]


@pytest.mark.asyncio
async def test_rejoin_after_cancel_goes_to_back_of_queue(ev_world, client, db_pool):
    """★ สมัครใหม่หลังถอน = ต่อท้ายคิว ไม่ใช่ได้ที่นั่งคืน (ใช้แถวเดิมแต่ registered_at ใหม่)

    capacity = 1 ⇒ alice ถอน → bob ได้ที่นั่ง → alice กลับมาเป็นคิวที่ 2 (ต่อจาก carol)
    """
    event_id = _create(client, ev_world, capacity=1)["id"]
    _publish(client, ev_world, event_id)
    _register(client, ev_world, event_id, "alice")
    _register(client, ev_world, event_id, "bob")
    _register(client, ev_world, event_id, "carol")
    _cancel_reg(client, ev_world, event_id, "alice")

    before = await _db_reg(db_pool, event_id, ev_world["alice"]["user_id"])

    res = _register(client, ev_world, event_id, "alice")
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "waitlisted"
    assert res.json()["queue_position"] == 2, "กลับมาต้องต่อท้าย carol"

    after = await _db_reg(db_pool, event_id, ev_world["alice"]["user_id"])
    assert after["id"] == before["id"], "ใช้แถวเดิม (unique index ไม่ใช่ partial) — ไม่สร้างแถวใหม่"
    assert after["cancelled_at"] is None
    assert after["registered_at"] > before["registered_at"]


@pytest.mark.asyncio
async def test_checked_in_seat_also_frees_on_cancel(ev_world, client, db_pool):
    """คนที่เช็คอินแล้วถอน ⇒ ยังต้องเลื่อนคิว (สถานะ checked_in นับเป็นผู้ถือที่นั่ง)"""
    event_id = _create(client, ev_world, capacity=1)["id"]
    _publish(client, ev_world, event_id)
    _register(client, ev_world, event_id, "alice")
    _register(client, ev_world, event_id, "bob")

    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE event_registrations SET status = 'checked_in' WHERE event_id = $1 AND user_id = $2",
            event_id, ev_world["alice"]["user_id"],
        )

    assert _cancel_reg(client, ev_world, event_id, "alice").status_code == 200
    bob_row = await _db_reg(db_pool, event_id, ev_world["bob"]["user_id"])
    assert bob_row["status"] == "registered"


# ============================================================
# 6) มุมมองสาธารณะ (นักเรียน)
# ============================================================

@pytest.mark.asyncio
async def test_public_list_shows_only_published(ev_world, client):
    draft = _create(client, ev_world, title="ฉบับร่าง")["id"]
    published = _create(client, ev_world, title="เผยแพร่แล้ว")["id"]
    _publish(client, ev_world, published)

    res = client.get("/api/events/public", headers=_auth(ev_world, "alice"))
    assert res.status_code == 200, res.text
    ids = {i["id"] for i in res.json()["items"]}
    assert published in ids
    assert draft not in ids, "ฉบับร่างต้องไม่โผล่ให้ทุกคนเห็น"


@pytest.mark.asyncio
async def test_public_list_hidden_by_soft_delete_and_cancel(ev_world, client):
    published = _create(client, ev_world)["id"]
    _publish(client, ev_world, published)

    cancelled = _create(client, ev_world)["id"]
    _publish(client, ev_world, cancelled)
    client.post(f"/api/events/{cancelled}/cancel", headers=_auth(ev_world))

    deleted = _create(client, ev_world)["id"]
    _publish(client, ev_world, deleted)
    client.delete(f"/api/events/{deleted}", headers=_auth(ev_world))

    res = client.get("/api/events/public?scope=all", headers=_auth(ev_world, "alice"))
    ids = {i["id"] for i in res.json()["items"]}
    assert ids == {published}


@pytest.mark.asyncio
async def test_public_detail_of_draft_is_404(ev_world, client):
    draft = _create(client, ev_world)["id"]
    res = client.get(f"/api/events/public/{draft}", headers=_auth(ev_world, "alice"))
    assert res.status_code == 404, res.text


@pytest.mark.asyncio
async def test_public_seats_remaining_and_open_flag(ev_world, client):
    """`seats_remaining` คำนวณใน SQL: None = ไม่จำกัด · 0 = เต็ม (สองความหมายต่างกัน)"""
    unlimited = _create(client, ev_world, capacity=None)["id"]
    limited = _create(client, ev_world, capacity=2)["id"]
    _publish(client, ev_world, unlimited)
    _publish(client, ev_world, limited)
    _register(client, ev_world, unlimited, "alice")
    _register(client, ev_world, limited, "alice")
    _register(client, ev_world, limited, "bob")

    res = client.get("/api/events/public?scope=all", headers=_auth(ev_world, "carol"))
    by_id = {i["id"]: i for i in res.json()["items"]}

    assert by_id[unlimited]["seats_remaining"] is None
    assert by_id[unlimited]["registered_count"] == 1
    assert by_id[limited]["seats_remaining"] == 0
    assert by_id[limited]["registered_count"] == 2
    assert by_id[limited]["is_registration_open"] is True


@pytest.mark.asyncio
async def test_public_closed_after_deadline(ev_world, client, db_pool):
    event_id = _create(
        client, ev_world, registration_deadline=(datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    )["id"]
    _publish(client, ev_world, event_id)

    res = client.get(f"/api/events/public/{event_id}", headers=_auth(ev_world, "alice"))
    assert res.json()["is_registration_open"] is False


@pytest.mark.asyncio
async def test_public_my_registration_status_normalizes_cancelled(ev_world, client):
    """★ `cancelled` ต้องถูกทำให้เป็น None — ไม่งั้น UI จะขึ้น "ยกเลิกแล้ว" ค้างตลอดไป"""
    event_id = _create(client, ev_world)["id"]
    _publish(client, ev_world, event_id)
    _register(client, ev_world, event_id, "alice")

    res = client.get(f"/api/events/public/{event_id}", headers=_auth(ev_world, "alice"))
    assert res.json()["my_registration_status"] == "registered"

    _cancel_reg(client, ev_world, event_id, "alice")
    res = client.get(f"/api/events/public/{event_id}", headers=_auth(ev_world, "alice"))
    assert res.json()["my_registration_status"] is None


@pytest.mark.asyncio
async def test_public_list_is_per_user(ev_world, client):
    """ทุกคนเห็นรายการเดียวกัน ต่างกันแค่ `my_registration_status`"""
    event_id = _create(client, ev_world)["id"]
    _publish(client, ev_world, event_id)
    _register(client, ev_world, event_id, "alice")

    a = client.get("/api/events/public", headers=_auth(ev_world, "alice")).json()["items"][0]
    b = client.get("/api/events/public", headers=_auth(ev_world, "bob")).json()["items"][0]
    assert a["my_registration_status"] == "registered"
    assert b["my_registration_status"] is None


@pytest.mark.asyncio
async def test_public_scope_upcoming_vs_past(ev_world, client, db_pool):
    future = _create(client, ev_world, title="อนาคต")["id"]
    past = _create(
        client, ev_world, title="อดีต",
        event_date=(datetime.now(timezone.utc) - timedelta(days=3)).isoformat(),
    )["id"]
    _publish(client, ev_world, future)
    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE events SET status='published', published_at=NOW() WHERE id = $1", past
        )

    up = client.get("/api/events/public?scope=upcoming", headers=_auth(ev_world, "alice")).json()
    assert {i["id"] for i in up["items"]} == {future}

    old = client.get("/api/events/public?scope=past", headers=_auth(ev_world, "alice")).json()
    assert {i["id"] for i in old["items"]} == {past}


@pytest.mark.asyncio
async def test_public_scope_bad_value_is_422(ev_world, client):
    res = client.get("/api/events/public?scope=mine", headers=_auth(ev_world, "alice"))
    assert res.status_code == 422, res.text


@pytest.mark.asyncio
async def test_public_payload_has_no_admin_fields(ev_world, client):
    """★ ห้ามหลุดฟิลด์ภายใน (`created_by` / `deleted_at` / ชื่อผู้สร้าง) ให้ฝั่งนักเรียน

    ⚠️ `published_at` / `cancelled_at` **ไม่อยู่ในลิสต์นี้โดยเจตนา** — สองตัวนี้เป็นข้อมูล
    ที่นักเรียนควรเห็นจริง ("ประกาศเมื่อไหร่" / "ยกเลิกเมื่อไหร่") และ `EventPublicOut`
    ประกาศรับไว้แล้ว · ต่างจาก `deleted_at` ซึ่งเป็นกลไกภายในที่ไม่ควรปรากฏ
    """
    event_id = _create(client, ev_world)["id"]
    _publish(client, ev_world, event_id)

    item = client.get("/api/events/public", headers=_auth(ev_world, "alice")).json()["items"][0]
    for leaked in ("created_by", "updated_by", "deleted_at",
                   "created_by_name", "updated_by_name"):
        assert leaked not in item, f"{leaked} ไม่ควรอยู่ใน payload สาธารณะ"

    # และฟิลด์ที่นักเรียน *ควร* เห็นต้องมีจริง — กันเทสต์ที่ผ่านเพราะ payload ว่างเปล่า
    for present in ("published_at", "registered_count", "is_registration_open"):
        assert present in item, f"{present} ควรอยู่ใน payload สาธารณะ"


# ============================================================
# 7) หน้าจัดการ — กรองสถานะ / ลบ / กู้คืน
# ============================================================

@pytest.mark.asyncio
async def test_list_events_status_filters(ev_world, client):
    draft = _create(client, ev_world)["id"]
    published = _create(client, ev_world)["id"]
    _publish(client, ev_world, published)
    cancelled = _create(client, ev_world)["id"]
    _publish(client, ev_world, cancelled)
    client.post(f"/api/events/{cancelled}/cancel", headers=_auth(ev_world))
    deleted = _create(client, ev_world)["id"]
    client.delete(f"/api/events/{deleted}", headers=_auth(ev_world))

    def ids(query):
        res = client.get(f"/api/events?status={query}", headers=_auth(ev_world))
        assert res.status_code == 200, res.text
        return {i["id"] for i in res.json()["items"]}

    assert ids("live") == {draft, published, cancelled}
    assert ids("draft") == {draft}
    assert ids("published") == {published}
    assert ids("cancelled") == {cancelled}
    assert ids("deleted") == {deleted}
    assert ids("all") == {draft, published, cancelled, deleted}


@pytest.mark.asyncio
async def test_list_events_bad_status_is_422(ev_world, client):
    res = client.get("/api/events?status=trash", headers=_auth(ev_world))
    assert res.status_code == 422, res.text


@pytest.mark.asyncio
async def test_list_events_envelope(ev_world, client):
    created = {_create(client, ev_world)["id"] for _ in range(3)}
    # ไม่มี `page` query — แบ่งหน้าด้วย offset เท่านั้น
    res = client.get("/api/events?limit=2&offset=0", headers=_auth(ev_world))
    body = res.json()
    assert body["total"] == 3 and body["page_size"] == 2 and body["pages"] == 2
    assert len(body["items"]) == 2
    assert {i["id"] for i in body["items"]} <= created

    page2 = client.get("/api/events?limit=2&offset=2", headers=_auth(ev_world)).json()
    assert len(page2["items"]) == 1
    assert page2["total"] == 3
    assert not ({i["id"] for i in body["items"]} & {i["id"] for i in page2["items"]})


@pytest.mark.asyncio
async def test_delete_is_soft_and_restore_brings_it_back(ev_world, client, db_pool):
    event_id = _create(client, ev_world)["id"]
    _publish(client, ev_world, event_id)

    res = client.delete(f"/api/events/{event_id}", headers=_auth(ev_world))
    assert res.status_code == 200, res.text
    row = await _db_event(db_pool, event_id)
    assert row["deleted_at"] is not None, "deep DB: ต้องเป็น soft delete"
    assert await _count(db_pool, "events") == 1, "แถวยังอยู่"

    assert client.get(f"/api/events/public/{event_id}", headers=_auth(ev_world, "alice")).status_code == 404

    res = client.post(f"/api/events/{event_id}/restore", headers=_auth(ev_world))
    assert res.status_code == 200, res.text
    row = await _db_event(db_pool, event_id)
    assert row["deleted_at"] is None
    assert row["status"] == "published", "กู้คืนแล้วต้องกลับมาสถานะเดิม"


@pytest.mark.asyncio
async def test_delete_twice_is_404(ev_world, client, db_pool):
    """ลบซ้ำต้องไม่เขียน `deleted_at` ทับของเดิม (หลักฐานว่าโดนลบเมื่อไหร่หายไป)"""
    event_id = _create(client, ev_world)["id"]
    assert client.delete(f"/api/events/{event_id}", headers=_auth(ev_world)).status_code == 200
    first = (await _db_event(db_pool, event_id))["deleted_at"]

    assert client.delete(f"/api/events/{event_id}", headers=_auth(ev_world)).status_code == 404
    assert (await _db_event(db_pool, event_id))["deleted_at"] == first


@pytest.mark.asyncio
async def test_restore_non_deleted_is_404(ev_world, client):
    event_id = _create(client, ev_world)["id"]
    res = client.post(f"/api/events/{event_id}/restore", headers=_auth(ev_world))
    assert res.status_code == 404, res.text


@pytest.mark.asyncio
async def test_restore_does_not_renotify(ev_world, client, db_pool):
    """★ กู้คืนเป็นเรื่องของผู้ดูแล ไม่ใช่เหตุการณ์ใหม่ ⇒ ห้ามยิงแจ้งเตือนซ้ำ"""
    event_id = _create(client, ev_world)["id"]
    _publish(client, ev_world, event_id)
    before = await _count(db_pool, "notifications")

    client.delete(f"/api/events/{event_id}", headers=_auth(ev_world))
    client.post(f"/api/events/{event_id}/restore", headers=_auth(ev_world))

    assert await _count(db_pool, "notifications") == before


@pytest.mark.asyncio
async def test_patch_soft_deleted_event_is_404(ev_world, client, db_pool):
    event_id = _create(client, ev_world)["id"]
    client.delete(f"/api/events/{event_id}", headers=_auth(ev_world))

    res = client.patch(
        f"/api/events/{event_id}", json={"title": "แอบแก้"}, headers=_auth(ev_world)
    )
    assert res.status_code == 404, res.text
    assert (await _db_event(db_pool, event_id))["title"] != "แอบแก้"


@pytest.mark.asyncio
async def test_cancel_only_works_on_published(ev_world, client, db_pool):
    draft = _create(client, ev_world)["id"]
    res = client.post(f"/api/events/{draft}/cancel", headers=_auth(ev_world))
    assert res.status_code == 404, res.text
    assert (await _db_event(db_pool, draft))["status"] == "draft"


@pytest.mark.asyncio
async def test_cancel_keeps_registrations_and_does_not_promote(ev_world, client, db_pool):
    """★ ยกเลิกกิจกรรม = ไม่มีที่นั่งให้ใคร ⇒ ห้ามเลื่อนคิว และห้ามลบประวัติการสมัคร"""
    event_id = _create(client, ev_world, capacity=1)["id"]
    _publish(client, ev_world, event_id)
    _register(client, ev_world, event_id, "alice")
    _register(client, ev_world, event_id, "bob")

    assert client.post(f"/api/events/{event_id}/cancel", headers=_auth(ev_world)).status_code == 200

    assert (await _db_reg(db_pool, event_id, ev_world["alice"]["user_id"]))["status"] == "registered"
    assert (await _db_reg(db_pool, event_id, ev_world["bob"]["user_id"]))["status"] == "waitlisted"
    assert await _count_notifications(db_pool, "event_waitlist_promoted") == 0

    assert sorted(await _notified_ids(db_pool, "event_cancelled")) == sorted([
        ev_world["alice"]["user_id"], ev_world["bob"]["user_id"],
    ])


@pytest.mark.asyncio
async def test_cancel_notifies_registrants_only(ev_world, client, db_pool):
    """ยกเลิก = แจ้งเฉพาะคนที่ลงทะเบียน ไม่ใช่ทั้งโรงเรียน"""
    event_id = _create(client, ev_world)["id"]
    _publish(client, ev_world, event_id)
    _register(client, ev_world, event_id, "alice")

    client.post(f"/api/events/{event_id}/cancel", headers=_auth(ev_world))

    ids = await _notified_ids(db_pool, "event_cancelled")
    assert ids == [ev_world["alice"]["user_id"]]
    assert ev_world["bob"]["user_id"] not in ids
    assert ev_world["manager"]["user_id"] not in ids


# ============================================================
# 8) รายชื่อผู้สมัคร (สภาดู)
# ============================================================

@pytest.mark.asyncio
async def test_list_registrations_order_and_names(ev_world, client):
    event_id = _create(client, ev_world, capacity=1)["id"]
    _publish(client, ev_world, event_id)
    _register(client, ev_world, event_id, "alice")
    _register(client, ev_world, event_id, "bob")
    _register(client, ev_world, event_id, "carol")

    res = client.get(f"/api/events/{event_id}/registrations", headers=_auth(ev_world))
    assert res.status_code == 200, res.text
    items = res.json()["items"]
    assert [i["user_id"] for i in items] == [
        ev_world["alice"]["user_id"],
        ev_world["bob"]["user_id"],
        ev_world["carol"]["user_id"],
    ], "เรียง: ผู้ถือที่นั่งก่อน แล้วต่อด้วยคิวตามลำดับ"
    assert [i["status"] for i in items] == ["registered", "waitlisted", "waitlisted"]
    assert all(i["user_name"] for i in items), "ต้องมีชื่อไว้ให้สภาดู"


@pytest.mark.asyncio
async def test_list_registrations_status_filter(ev_world, client):
    event_id = _create(client, ev_world, capacity=1)["id"]
    _publish(client, ev_world, event_id)
    _register(client, ev_world, event_id, "alice")
    _register(client, ev_world, event_id, "bob")

    res = client.get(
        f"/api/events/{event_id}/registrations?status=waitlisted", headers=_auth(ev_world)
    )
    body = res.json()
    assert body["total"] == 1
    assert body["items"][0]["user_id"] == ev_world["bob"]["user_id"]


@pytest.mark.asyncio
async def test_list_registrations_of_missing_event_is_404(ev_world, client):
    """★ 404 ไม่ใช่ลิสต์ว่าง — "ไม่มีกิจกรรมนี้" ต่างจาก "ยังไม่มีใครสมัคร" """
    res = client.get("/api/events/999999/registrations", headers=_auth(ev_world))
    assert res.status_code == 404, res.text


@pytest.mark.asyncio
async def test_list_registrations_of_deleted_event_is_404(ev_world, client):
    event_id = _create(client, ev_world)["id"]
    client.delete(f"/api/events/{event_id}", headers=_auth(ev_world))
    res = client.get(f"/api/events/{event_id}/registrations", headers=_auth(ev_world))
    assert res.status_code == 404, res.text


@pytest.mark.asyncio
async def test_registration_survives_event_update(ev_world, client, db_pool):
    """แก้รายละเอียดกิจกรรมต้องไม่กระทบที่นั่ง/คิว"""
    event_id = _create(client, ev_world, capacity=1)["id"]
    _publish(client, ev_world, event_id)
    _register(client, ev_world, event_id, "alice")
    _register(client, ev_world, event_id, "bob")

    client.patch(
        f"/api/events/{event_id}", json={"title": "เปลี่ยนชื่อ", "capacity": 5},
        headers=_auth(ev_world),
    )

    assert (await _db_reg(db_pool, event_id, ev_world["alice"]["user_id"]))["status"] == "registered"
    assert (await _db_reg(db_pool, event_id, ev_world["bob"]["user_id"]))["status"] == "waitlisted"


# ============================================================
# 9) Audit labels — กฎ "audit action ใหม่ = 2 ที่" (ฝั่ง backend)
# ============================================================

D1_ACTIONS = (
    "CREATE_EVENT", "UPDATE_EVENT", "PUBLISH_EVENT", "CANCEL_EVENT",
    "DELETE_EVENT", "RESTORE_EVENT", "REGISTER_EVENT", "UNREGISTER_EVENT",
)


@pytest.mark.parametrize("action", D1_ACTIONS)
def test_d1_audit_actions_have_thai_labels(action):
    """★ ถ้าลืมเพิ่มป้าย frontend จะโชว์ชื่อ action ดิบ — และไม่มีอะไรฟ้อง

    ฝั่ง frontend (`views/audit/AuditLogs.vue`) มี map คู่กันและ **ต้องแก้ทั้งสองที่**
    (กฎที่เขียนกำกับไว้ใน `dashboard_service.ACTION_LABELS` เอง)
    """
    label = dashboard_service.ACTION_LABELS.get(action)
    assert label, f"{action} ไม่มีป้ายใน ACTION_LABELS"
    assert label != action, "ป้ายต้องเป็นภาษาไทย ไม่ใช่ชื่อ action"


@pytest.mark.asyncio
async def test_unregister_writes_audit(ev_world, client, db_pool):
    event_id = _create(client, ev_world)["id"]
    _publish(client, ev_world, event_id)
    _register(client, ev_world, event_id, "alice")
    _cancel_reg(client, ev_world, event_id, "alice")

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT actor_identifier FROM audit_logs WHERE action = 'UNREGISTER_EVENT'"
        )
    assert row is not None
    assert row["actor_identifier"] == str(ev_world["alice"]["user_id"])


@pytest.mark.asyncio
async def test_lifecycle_actions_all_recorded(ev_world, client, db_pool):
    """เดินครบวงจรชีวิต → ต้องเห็น action ครบทุกตัวใน audit_logs"""
    event_id = _create(client, ev_world)["id"]
    _publish(client, ev_world, event_id)
    client.patch(f"/api/events/{event_id}", json={"location": "โรงยิม"}, headers=_auth(ev_world))
    client.post(f"/api/events/{event_id}/cancel", headers=_auth(ev_world))
    client.delete(f"/api/events/{event_id}", headers=_auth(ev_world))
    client.post(f"/api/events/{event_id}/restore", headers=_auth(ev_world))

    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT DISTINCT action FROM audit_logs")
    seen = {r["action"] for r in rows}
    assert {
        "CREATE_EVENT", "PUBLISH_EVENT", "UPDATE_EVENT",
        "CANCEL_EVENT", "DELETE_EVENT", "RESTORE_EVENT",
    } <= seen


# ============================================================
# 10) Migration 025
# ============================================================

@pytest.mark.asyncio
async def test_migration_025_recreates_schema_when_missing(ev_world, db_pool):
    """★ จำลอง DB ที่ยังไม่มีตาราง → `upgrade()` ต้องสร้างคืนครบ (ตาราง/index/constraint)

    ทำใน transaction แล้ว **rollback** ⇒ ไม่ทิ้งสภาพให้เทสต์ไฟล์อื่นพัง
    (ต่างจาก `test_academic_terms.py` ที่ DROP จริงเพราะตารางนั้นไม่มีใครใช้ต่อ)
    """
    mig = importlib.import_module("migrations.025_events")

    async with db_pool.acquire() as conn:
        tx = conn.transaction()
        await tx.start()
        try:
            await conn.execute("DROP TABLE IF EXISTS event_registrations")
            await conn.execute("DROP TABLE IF EXISTS events CASCADE")
            assert await conn.fetchval("SELECT to_regclass('public.events') IS NULL") is True

            await mig.upgrade(conn)
            await mig.upgrade(conn)  # idempotent — รันซ้ำต้องไม่ error

            assert await conn.fetchval("SELECT to_regclass('public.events') IS NOT NULL") is True
            assert await conn.fetchval(
                "SELECT to_regclass('public.event_registrations') IS NOT NULL"
            ) is True

            indexes = {
                r["indexname"] for r in await conn.fetch(
                    """
                    SELECT indexname FROM pg_indexes
                    WHERE tablename IN ('events', 'event_registrations')
                    """
                )
            }
            for name in (
                "uq_event_registrations_event_user",
                "idx_events_status_date",
                "idx_events_created_by",
                "idx_event_registrations_event_status",
                "idx_event_registrations_user",
            ):
                assert name in indexes, f"ขาด index {name}"

            constraints = {
                r["conname"] for r in await conn.fetch(
                    "SELECT conname FROM pg_constraint WHERE conrelid = 'events'::regclass"
                )
            }
            assert "chk_events_status" in constraints
            assert "chk_events_capacity" in constraints
        finally:
            await tx.rollback()

    # ยืนยันว่าถอยกลับจริง — เทสต์ไฟล์ถัดไปยังใช้งานได้
    async with db_pool.acquire() as conn:
        assert await conn.fetchval("SELECT to_regclass('public.events') IS NOT NULL") is True


@pytest.mark.asyncio
async def test_migration_025_backfill_is_idempotent(ev_world, db_pool):
    """★ backfill ต้องไม่เติม MANAGE_EVENTS ซ้ำ และต้องไม่แตะ council_member

    (ผู้ใช้เลือก: ให้เหมือน MANAGE_SETTINGS ⇒ เฉพาะ council_president/teacher_council/admin
     ⇒ **ต่างจาก migration 014** ที่ให้ council_member ด้วย)
    """
    mig = importlib.import_module("migrations.025_events")

    async def perms_count(user_id):
        async with db_pool.acquire() as conn:
            return await conn.fetchval(
                """
                SELECT COUNT(*) FROM students s,
                     LATERAL jsonb_array_elements_text(COALESCE(s.permissions, '[]'::jsonb)) AS p
                WHERE s.user_id = $1 AND p = 'MANAGE_EVENTS'
                """,
                user_id,
            )

    async with db_pool.acquire() as conn:
        await mig.upgrade(conn)
        await mig.upgrade(conn)  # รันซ้ำ

    assert await perms_count(ev_world["manager"]["user_id"]) == 1, "ต้องมีตัวเดียว ไม่ซ้ำ"
    assert await perms_count(ev_world["granted"]["user_id"]) == 1, "มีอยู่แล้วต้องไม่ถูกเติมซ้ำ"
    assert await perms_count(ev_world["plain"]["user_id"]) == 0, (
        "council_member ต้องไม่ถูก backfill (ต่างจาก migration 014)"
    )
    assert await perms_count(ev_world["alice"]["user_id"]) == 0


@pytest.mark.asyncio
async def test_checked_in_status_passes_check_constraint(ev_world, client, db_pool):
    """CHECK ของ event_registrations ต้องรับ `checked_in` (D2 QR จะใช้ค่า�นี้)"""
    event_id = _create(client, ev_world)["id"]
    _publish(client, ev_world, event_id)
    _register(client, ev_world, event_id, "alice")

    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE event_registrations SET status = 'checked_in', checked_in_at = NOW()
            WHERE event_id = $1 AND user_id = $2
            """,
            event_id, ev_world["alice"]["user_id"],
        )
        status = await conn.fetchval(
            "SELECT status FROM event_registrations WHERE event_id = $1 AND user_id = $2",
            event_id, ev_world["alice"]["user_id"],
        )
    assert status == "checked_in"


@pytest.mark.asyncio
async def test_capacity_check_constraint_rejects_zero(ev_world, db_pool):
    """DB ต้องกัน capacity = 0 ไว้เองด้วย ไม่พึ่ง Pydantic อย่างเดียว"""
    import asyncpg

    async with db_pool.acquire() as conn:
        with pytest.raises(asyncpg.CheckViolationError):
            await conn.execute(
                """
                INSERT INTO events (title, event_date, capacity, created_by, updated_by)
                VALUES ('ผิดกฎ', NOW() + INTERVAL '1 day', 0, 0, 0)
                """
            )


# ============================================================
# 8) D2 — เช็คอินหน้างาน (QR + กดมือ)
# ============================================================
#
# ⭐ หัวใจที่ต้องพิสูจน์ให้ได้ (ไม่ใช่แค่ "ยิงแล้วได้ 200"):
#   · `checked_in` ยังนับเป็น **คนถือที่นั่ง** ⇒ ที่นั่งไม่หาย ไม่มีใครถูกเลื่อนคิวเกิน
#   · สแกนซ้ำ **ไม่ทับ** `checked_in_at` ครั้งแรก (เวลาที่มาถึงคือหลักฐาน)
#   · บัตรของกิจกรรมหนึ่ง **ใช้กับอีกกิจกรรมไม่ได้** (`registration_id` เป็น SERIAL ร่วมกัน)
#   · รหัสที่ถูกแก้ไบต์เดียวต้องไม่ผ่าน
#   · `waitlisted` / `cancelled` ต้องถูกปฏิเสธ **โดยไม่แตะ DB**

def _check_in(client, world, event_id, who="manager", **body):
    return client.post(
        f"/api/events/{event_id}/check-in", json=body, headers=_auth(world, who)
    )


def _my_token(client, world, event_id, who) -> str:
    res = client.get(f"/api/events/{event_id}/my-registration", headers=_auth(world, who))
    assert res.status_code == 200, res.text
    return res.json()["check_in_token"]


@pytest.mark.asyncio
async def test_check_in_requires_manage_events(ev_world, client, db_pool):
    """★ นักเรียนเช็คอินให้ตัวเองไม่ได้ — แม้จะเป็นใบสมัครของตัวเอง

    ⚠️ ด่านนี้สำคัญกว่าปกติ: "เช็คอินตัวเองได้" = ระบบที่ไม่ยืนยันอะไรเลย
       (คนที่อยู่หน้างานเท่านั้นที่ยืนยันได้ว่ามีตัวตนอยู่หน้างาน)
    """
    event_id = _create(client, ev_world)["id"]
    _publish(client, ev_world, event_id)
    _register(client, ev_world, event_id, "alice")
    reg = await _db_reg(db_pool, event_id, ev_world["alice"]["user_id"])

    # `alice` = เจ้าของใบเอง · `plain` = สมาชิกสภาที่ไม่มีสิทธิ์จาก JSONB และไม่ใช่ is_admin
    # (`granted` ไม่ได้อยู่ในลิสต์นี้โดยเจตนา — มัน**มี** MANAGE_EVENTS ⇒ ต้องผ่าน)
    for who in ("alice", "plain"):
        res = _check_in(client, ev_world, event_id, who, registration_id=reg["id"])
        assert res.status_code == 403, f"{who} ต้องโดน 403 แต่ได้ {res.status_code}"

    # ไม่มี token เลยก็ 401
    res = client.post(f"/api/events/{event_id}/check-in", json={"registration_id": reg["id"]})
    assert res.status_code == 401

    # DB ยังไม่ถูกแตะ
    assert (await _db_reg(db_pool, event_id, ev_world["alice"]["user_id"]))["status"] == "registered"


@pytest.mark.asyncio
async def test_check_in_manual_sets_status_and_audit(ev_world, client, db_pool):
    """กดมือจากรายชื่อ ⇒ สถานะเปลี่ยน + `checked_in_at` ถูกเขียน + audit ใน transaction เดียวกัน"""
    event_id = _create(client, ev_world)["id"]
    _publish(client, ev_world, event_id)
    _register(client, ev_world, event_id, "alice")
    reg = await _db_reg(db_pool, event_id, ev_world["alice"]["user_id"])

    res = _check_in(client, ev_world, event_id, registration_id=reg["id"])
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "checked_in"
    assert body["already_checked_in"] is False
    assert body["method"] == "manual"
    assert body["registration_id"] == reg["id"]
    assert body["user_id"] == ev_world["alice"]["user_id"]
    assert "alice" in (body["user_name"] or "")

    row = await _db_reg(db_pool, event_id, ev_world["alice"]["user_id"])
    assert row["status"] == "checked_in"
    assert row["checked_in_at"] is not None

    async with db_pool.acquire() as conn:
        audit = await conn.fetchrow(
            """
            SELECT * FROM audit_logs
            WHERE action = 'CHECK_IN_EVENT' AND entity_id = $1
            ORDER BY id DESC LIMIT 1
            """,
            str(event_id),
        )
    assert audit is not None, "ต้องมี audit log ของการเช็คอิน"
    assert audit["user_id"] == ev_world["manager"]["user_id"], "ผู้กระทำคือสภาที่สแกน"
    new_values = json.loads(audit["new_values"])
    assert new_values["method"] == "manual"
    assert new_values["attendee_user_id"] == ev_world["alice"]["user_id"]


@pytest.mark.asyncio
async def test_check_in_by_qr_token(ev_world, client, db_pool):
    """สแกนบัตรจริง — โทเคนมาจาก `my-registration` ของนักเรียน (ทางที่ QR บนจอใช้)"""
    event_id = _create(client, ev_world)["id"]
    _publish(client, ev_world, event_id)
    _register(client, ev_world, event_id, "bob")
    token = _my_token(client, ev_world, event_id, "bob")
    assert token, "คนที่ถือที่นั่งต้องได้บัตร"

    res = _check_in(client, ev_world, event_id, token=token)
    assert res.status_code == 200, res.text
    assert res.json()["method"] == "qr"
    assert res.json()["user_id"] == ev_world["bob"]["user_id"]

    row = await _db_reg(db_pool, event_id, ev_world["bob"]["user_id"])
    assert row["status"] == "checked_in"


@pytest.mark.asyncio
async def test_check_in_twice_keeps_first_timestamp(ev_world, client, db_pool):
    """★★ สแกนซ้ำ = 200 + `already_checked_in` และ **เวลาครั้งแรกต้องไม่ถูกทับ**

    เวลาที่เช็คอินคือ "เวลาที่คนนี้มาถึง" ไม่ใช่ "เวลาที่สแกนล่าสุด" — ถ้าเขียนทับ
    หลักฐานการมาถึงจะเพี้ยนทุกครั้งที่มีคนสแกนรัว (ซึ่งเกิดตลอดหน้างาน)
    """
    event_id = _create(client, ev_world)["id"]
    _publish(client, ev_world, event_id)
    _register(client, ev_world, event_id, "alice")
    token = _my_token(client, ev_world, event_id, "alice")

    first = _check_in(client, ev_world, event_id, token=token)
    assert first.status_code == 200
    first_at = first.json()["checked_in_at"]
    assert first.json()["already_checked_in"] is False

    second = _check_in(client, ev_world, event_id, token=token)
    assert second.status_code == 200, "สแกนซ้ำต้องไม่เป็น error"
    assert second.json()["already_checked_in"] is True
    assert second.json()["checked_in_at"] == first_at, "เวลาครั้งแรกถูกทับ"

    row = await _db_reg(db_pool, event_id, ev_world["alice"]["user_id"])
    assert row["checked_in_at"] == _as_utc(first_at)


@pytest.mark.asyncio
async def test_check_in_token_of_other_event_is_rejected(ev_world, client, db_pool):
    """★★ บัตรข้ามงาน ⇒ **400 พร้อมข้อความที่บอกสาเหตุจริง** ไม่ใช่ 404

    🧪 mutation proof (ปิดการเทียบ `event_id` ใน service): เทสต์นี้ตก และได้ **404**
       ไม่ใช่การหลุดเข้าไปเช็คอินสำเร็จ ⇒ **การเทียบนี้ไม่ได้กันการบุกรุก** (คิวรีกรอง
       `r.event_id` อยู่แล้ว) — มันซื้อ *ข้อความ* ให้สภาแยกออกว่า "เด็กหยิบบัตรผิดงาน"
       กับ "ระบบหาข้อมูลไม่เจอ" ซึ่งนำไปสู่การแก้ปัญหาคนละทาง
       (เขียนเหตุผลให้ตรงกับที่พิสูจน์ได้ ไม่ใช่ให้ดูขลัง — ดู CLAUDE.md เรื่องความซื่อสัตย์ของหลักฐาน)
    """
    a = _create(client, ev_world)["id"]
    b = _create(client, ev_world)["id"]
    _publish(client, ev_world, a)
    _publish(client, ev_world, b)
    _register(client, ev_world, a, "carol")
    token = _my_token(client, ev_world, a, "carol")

    res = _check_in(client, ev_world, b, token=token)
    assert res.status_code == 400, res.text
    assert "กิจกรรมอื่น" in res.json()["detail"]

    # ใบที่งาน A ต้องยังไม่ถูกเช็คอิน (การปฏิเสธต้องไม่ทำอะไรข้าง ๆ)
    assert (await _db_reg(db_pool, a, ev_world["carol"]["user_id"]))["status"] == "registered"


@pytest.mark.asyncio
async def test_check_in_forged_or_tampered_token_is_400(ev_world, client, db_pool):
    """รหัสที่ถูกแก้ — ทั้งแก้ลายเซ็นและแก้เลขข้างใน ⇒ 400 และ DB ไม่ขยับ"""
    event_id = _create(client, ev_world)["id"]
    _publish(client, ev_world, event_id)
    _register(client, ev_world, event_id, "alice")
    token = _my_token(client, ev_world, event_id, "alice")
    head, sig = token.rsplit(":", 1)

    for bad in (
        f"{head}:{'A' * len(sig)}",                     # ลายเซ็นมั่ว
        f"{head}:{sig[:-1]}{'A' if sig[-1] != 'A' else 'B'}",  # พลิกไบต์เดียว
        "PIRI-EVT1:1:1:deadbeefdeadbeefdeadbe",
        token.replace("PIRI-EVT1", "PIRI-EVT9"),
    ):
        res = _check_in(client, ev_world, event_id, token=bad)
        assert res.status_code == 400, f"{bad!r} ต้องโดน 400 แต่ได้ {res.status_code}"

    assert (await _db_reg(db_pool, event_id, ev_world["alice"]["user_id"]))["status"] == "registered"


@pytest.mark.asyncio
async def test_check_in_rejects_waitlisted_without_touching_db(ev_world, client, db_pool):
    """★ คิวสำรองเช็คอินไม่ได้ — และการปฏิเสธต้องไม่แตะ DB เลย"""
    event_id = _create(client, ev_world, capacity=1)["id"]
    _publish(client, ev_world, event_id)
    _register(client, ev_world, event_id, "alice")
    _register(client, ev_world, event_id, "bob")   # เต็ม ⇒ waitlisted
    reg = await _db_reg(db_pool, event_id, ev_world["bob"]["user_id"])
    assert reg["status"] == "waitlisted"
    before = await _count_notifications(db_pool)

    res = _check_in(client, ev_world, event_id, registration_id=reg["id"])
    assert res.status_code == 400, res.text
    assert "คิวสำรอง" in res.json()["detail"]

    row = await _db_reg(db_pool, event_id, ev_world["bob"]["user_id"])
    assert row["status"] == "waitlisted"
    assert row["checked_in_at"] is None
    assert await _count_notifications(db_pool) == before, "การปฏิเสธต้องไม่แจ้งใคร"


@pytest.mark.asyncio
async def test_check_in_waitlisted_person_has_no_token(ev_world, client, db_pool):
    """คนที่ยังไม่มีที่นั่ง **ไม่ได้รับบัตร** — สวิตช์เดียวกับที่ UI ใช้ตัดสินว่าจะโชว์บัตรไหม"""
    event_id = _create(client, ev_world, capacity=1)["id"]
    _publish(client, ev_world, event_id)
    _register(client, ev_world, event_id, "alice")
    _register(client, ev_world, event_id, "bob")

    assert _my_token(client, ev_world, event_id, "alice"), "คนถือที่นั่งต้องได้บัตร"
    assert _my_token(client, ev_world, event_id, "bob") is None, "คิวสำรองต้องไม่ได้บัตร"


@pytest.mark.asyncio
async def test_check_in_cancelled_registration_is_400(ev_world, client, db_pool):
    """ใบที่ถูกยกเลิกแล้วเช็คอินไม่ได้ (ข้อความต้องต่างจากเคสคิวสำรอง — คนละทางแก้)"""
    event_id = _create(client, ev_world)["id"]
    _publish(client, ev_world, event_id)
    _register(client, ev_world, event_id, "alice")
    reg = await _db_reg(db_pool, event_id, ev_world["alice"]["user_id"])
    _cancel_reg(client, ev_world, event_id, "alice")

    res = _check_in(client, ev_world, event_id, registration_id=reg["id"])
    assert res.status_code == 400, res.text
    assert "ยกเลิก" in res.json()["detail"]


@pytest.mark.asyncio
async def test_check_in_unknown_registration_is_404(ev_world, client):
    event_id = _create(client, ev_world)["id"]
    _publish(client, ev_world, event_id)

    res = _check_in(client, ev_world, event_id, registration_id=999999999)
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_check_in_registration_of_other_event_is_404(ev_world, client, db_pool):
    """ใบของงาน A กดมือที่งาน B ⇒ 404 (ไม่ใช่ 200) — กัน `registration_id` ข้ามงาน"""
    a = _create(client, ev_world)["id"]
    b = _create(client, ev_world)["id"]
    _publish(client, ev_world, a)
    _publish(client, ev_world, b)
    _register(client, ev_world, a, "alice")
    reg = await _db_reg(db_pool, a, ev_world["alice"]["user_id"])

    assert _check_in(client, ev_world, b, registration_id=reg["id"]).status_code == 404


@pytest.mark.asyncio
async def test_check_in_deleted_event_is_404(ev_world, client, db_pool):
    """กิจกรรมที่ถูกลบ ⇒ 404 ให้ตรงกับ `list_registrations` (ไม่ให้เช็คอินเข้าข้อมูลผี)"""
    event_id = _create(client, ev_world)["id"]
    _publish(client, ev_world, event_id)
    _register(client, ev_world, event_id, "alice")
    reg = await _db_reg(db_pool, event_id, ev_world["alice"]["user_id"])
    res = client.delete(f"/api/events/{event_id}", headers=_auth(ev_world))
    assert res.status_code == 200

    assert _check_in(client, ev_world, event_id, registration_id=reg["id"]).status_code == 404


@pytest.mark.asyncio
async def test_check_in_body_needs_exactly_one_field(ev_world, client, db_pool):
    """ส่งทั้งคู่ / ไม่ส่งอะไรเลย ⇒ 422 (ไม่เดาเจตนาให้ผู้ใช้)"""
    event_id = _create(client, ev_world)["id"]
    _publish(client, ev_world, event_id)
    _register(client, ev_world, event_id, "alice")
    reg = await _db_reg(db_pool, event_id, ev_world["alice"]["user_id"])
    token = _my_token(client, ev_world, event_id, "alice")

    assert _check_in(client, ev_world, event_id).status_code == 422
    assert _check_in(client, ev_world, event_id, token=token, registration_id=reg["id"]).status_code == 422


@pytest.mark.asyncio
async def test_check_in_does_not_change_seat_count_or_queue(ev_world, client, db_pool):
    """★★ `checked_in` ยังนับเป็น **คนถือที่นั่ง** — เช็คอินต้องไม่ทำให้ที่นั่งว่างหรือเลื่อนคิว

    (กับดักที่แผน §4.1 เตือนไว้: ถ้ามีใครถอด `'checked_in'` ออกจากชุด `status IN (...)`
     ที่นับที่นั่ง ⇒ เช็คอินคนแรกแล้วระบบจะเห็นที่นั่งว่าง ⇒ เลื่อนคิวเกินจริง)
    """
    event_id = _create(client, ev_world, capacity=1)["id"]
    _publish(client, ev_world, event_id)
    _register(client, ev_world, event_id, "alice")
    _register(client, ev_world, event_id, "bob")

    assert _check_in(client, ev_world, event_id, registration_id=(
        await _db_reg(db_pool, event_id, ev_world["alice"]["user_id"])
    )["id"]).status_code == 200

    assert (await _db_reg(db_pool, event_id, ev_world["bob"]["user_id"]))["status"] == "waitlisted", (
        "เช็คอินไม่ใช่การถอน ⇒ คิวต้องไม่ขยับ"
    )
    public = client.get(f"/api/events/public/{event_id}", headers=_auth(ev_world, "bob")).json()
    assert public["registered_count"] == 1, "คนที่เช็คอินแล้วยังนับเป็นผู้ถือที่นั่ง"
    assert public["seats_remaining"] == 0


@pytest.mark.asyncio
async def test_checked_in_person_cancel_promotes_next(ev_world, client, db_pool):
    """★ เช็คอินแล้วถอน ⇒ ยังต้องเลื่อนคิวให้คนถัดไป (พิสูจน์ว่า `checked_in` อยู่ในชุด "ถือที่นั่ง" ของ `cancel_registration` ด้วย)"""
    event_id = _create(client, ev_world, capacity=1)["id"]
    _publish(client, ev_world, event_id)
    _register(client, ev_world, event_id, "alice")
    _register(client, ev_world, event_id, "bob")
    reg = await _db_reg(db_pool, event_id, ev_world["alice"]["user_id"])
    _check_in(client, ev_world, event_id, registration_id=reg["id"])

    res = _cancel_reg(client, ev_world, event_id, "alice")
    assert res.status_code == 200, res.text

    assert (await _db_reg(db_pool, event_id, ev_world["bob"]["user_id"]))["status"] == "registered"
    assert await _notified_ids(db_pool, "event_waitlist_promoted") == [ev_world["bob"]["user_id"]]


@pytest.mark.asyncio
async def test_check_in_sends_no_notification(ev_world, client, db_pool):
    """★ เช็คอินต้องเงียบ — นักเรียนยืนอยู่ตรงหน้าสภาอยู่แล้ว"""
    event_id = _create(client, ev_world)["id"]
    _publish(client, ev_world, event_id)
    _register(client, ev_world, event_id, "alice")
    before = await _count_notifications(db_pool)
    reg = await _db_reg(db_pool, event_id, ev_world["alice"]["user_id"])

    assert _check_in(client, ev_world, event_id, registration_id=reg["id"]).status_code == 200
    assert await _count_notifications(db_pool) == before
    assert await _count(db_pool, "push_outbox") == 0


@pytest.mark.asyncio
async def test_check_in_token_is_stable_across_calls(ev_world, client):
    """บัตรใบเดิมต้องได้รหัสเดิมทุกครั้งที่เปิดดู — ไม่งั้นนักเรียนที่แคปจอไว้ถือบัตรคนละใบกับหน้าเว็บ"""
    event_id = _create(client, ev_world)["id"]
    _publish(client, ev_world, event_id)
    _register(client, ev_world, event_id, "alice")

    first = _my_token(client, ev_world, event_id, "alice")
    assert first == _my_token(client, ev_world, event_id, "alice")


@pytest.mark.asyncio
async def test_register_response_carries_token_immediately(ev_world, client):
    """★ สมัครเสร็จต้องได้บัตรทันทีในคำตอบเดียว — ไม่ต้องยิง `my-registration` ซ้ำอีกรอบ

    (สำคัญกับคนที่สมัครตอนเน็ตช้า: หน้า detail ใช้คำตอบนี้วาดบัตรได้เลย)
    """
    event_id = _create(client, ev_world)["id"]
    _publish(client, ev_world, event_id)
    body = _register(client, ev_world, event_id, "alice").json()
    assert body["status"] == "registered"
    assert body["check_in_token"]

    # คิวสำรอง — ต้องเป็น None
    full = _create(client, ev_world, capacity=1)["id"]
    _publish(client, ev_world, full)
    _register(client, ev_world, full, "alice")
    wl = _register(client, ev_world, full, "bob").json()
    assert wl["status"] == "waitlisted"
    assert wl["check_in_token"] is None


@pytest.mark.asyncio
async def test_cancel_clears_checked_in_at_but_keeps_it_in_audit(ev_world, client, db_pool):
    """★★ ถอนหลังเช็คอิน ⇒ `checked_in_at` ถูกล้าง **แต่ค่าที่ล้างต้องไม่หายไปจากหลักฐาน**

    ⭐ invariant ของตารางนี้คือ **`checked_in_at IS NOT NULL` ⟺ `status = 'checked_in'`**
       ⇒ ถ้าปล่อยค่าเก่าค้าง แถว `cancelled` จะมี "เวลาที่มาถึง" ติดมาด้วย แล้วคำถาม
       "คนนี้เช็คอินหรือยัง" จะตอบได้สองแบบที่ขัดกัน (ดู `status` หรือดู `checked_in_at`)
       ⇒ **การถอนคือจุดที่ invariant นี้พังได้ง่ายที่สุด** และพังเงียบ (ไม่มีอะไร error)

    ⚠️ แต่การล้างค่าเฉย ๆ = **ทำลายหลักฐานว่า "คนนี้เคยมาถึงกี่โมง"** ซึ่งเป็นข้อมูลที่
       โรงเรียนต้องใช้ตอบย้อนหลัง (มาสาย/มาแต่ถอนกลางงาน) · ตารางเก็บไม่ได้แล้วก็ต้องเก็บ
       ใน log ⇒ เทสต์นี้จึงยืนยัน **ทั้งสองครึ่ง**: คอลัมน์ว่าง และ `old_values` ยังมีค่าเดิม
       (ครึ่งหลังคือครึ่งที่ลืมกันบ่อย — ล้างแล้วคิดว่าเสร็จ)
    """
    event_id = _create(client, ev_world)["id"]
    _publish(client, ev_world, event_id)
    _register(client, ev_world, event_id, "alice")
    reg = await _db_reg(db_pool, event_id, ev_world["alice"]["user_id"])

    assert _check_in(client, ev_world, event_id, registration_id=reg["id"]).status_code == 200
    checked_in_at = (await _db_reg(db_pool, event_id, ev_world["alice"]["user_id"]))["checked_in_at"]
    assert checked_in_at is not None

    assert _cancel_reg(client, ev_world, event_id, "alice").status_code == 200

    row = await _db_reg(db_pool, event_id, ev_world["alice"]["user_id"])
    assert row["status"] == "cancelled"
    assert row["checked_in_at"] is None, "invariant พัง — แถวที่ถอนแล้วยังมีเวลาที่เช็คอินค้างอยู่"

    async with db_pool.acquire() as conn:
        audit = await conn.fetchrow(
            """
            SELECT * FROM audit_logs
            WHERE action = 'UNREGISTER_EVENT' AND entity_id = $1
            ORDER BY id DESC LIMIT 1
            """,
            str(event_id),
        )
    assert audit is not None
    # ⭐ หลักฐานต้องรอด — ล้างคอลัมน์ได้ แต่ต้องเหลือร่องรอยว่าล้างอะไรทิ้ง
    assert json.loads(audit["old_values"])["checked_in_at"] is not None


@pytest.mark.asyncio
async def test_re_register_clears_checked_in_at_from_the_previous_round(ev_world, client, db_pool):
    """★★ สมัครใหม่บนแถวเดิม (unique index ⇒ ไม่มีแถวใหม่) ต้องไม่ลากเวลาที่เช็คอินของ **รอบก่อน** มาด้วย

    ⭐ แถวนี้คือกับดักของ invariant: `register_event` เขียนทับ `status` เป็น `registered`
       แต่ถ้าไม่ได้ล้าง `checked_in_at` ไปพร้อมกัน แถวสถานะ `registered` จะมีเวลาที่เช็คอิน
       ค้างอยู่ ⇒ UI ที่อ่าน `checked_in_at` (แทน `status`) จะโชว์ "เช็คอินแล้ว" ให้คนที่
       **ยังไม่ได้เช็คอินในรอบนี้** — และจะไม่มีใครรู้จนถึงวันงาน

    ⚠️ คำตอบของ API ก็ต้องตรงกันด้วย ไม่ใช่แค่ DB — frontend ใช้ body ของ `register` วาดบัตร
       ทันที (ไม่ยิง `my-registration` ซ้ำ) ⇒ ถ้า service คืน `None` ลอย ๆ ขณะที่ DB ยังมีค่าเก่า
       สองที่จะเถียงกัน แล้วบัตรที่โชว์จะผิดโดยที่เทสต์ DB-only จับไม่ได้
    """
    event_id = _create(client, ev_world, capacity=1)["id"]
    _publish(client, ev_world, event_id)
    _register(client, ev_world, event_id, "alice")
    reg = await _db_reg(db_pool, event_id, ev_world["alice"]["user_id"])
    assert _check_in(client, ev_world, event_id, registration_id=reg["id"]).status_code == 200

    assert _cancel_reg(client, ev_world, event_id, "alice").status_code == 200

    # เติมที่นั่งให้ bob ก่อน ⇒ alice ที่กลับมาต้องได้ waitlisted ไม่ใช่ registered
    # (ยังต้องล้างค่าเหมือนกัน — คนละสถานะแต่แถวเดียวกัน)
    _register(client, ev_world, event_id, "bob")

    res = _register(client, ev_world, event_id, "alice")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "waitlisted"
    assert body["checked_in_at"] is None, "คำตอบของ API ต้องบอกว่า 'ยังไม่เช็คอิน'"

    row = await _db_reg(db_pool, event_id, ev_world["alice"]["user_id"])
    assert row["id"] == reg["id"], "ต้องเป็นแถวเดิม ไม่ใช่แถวใหม่"
    assert row["checked_in_at"] is None, "เวลาที่เช็คอินของรอบก่อนค้างอยู่ในแถวใหม่"


# ============================================================
# 11) D4 — หมวดกิจกรรม (`category`)
# ============================================================
#
# ⭐ หัวใจที่ต้องพิสูจน์ (ไม่ใช่แค่ "ส่งค่าไปแล้วได้ค่าเดิม"):
#
#   1. **ค่าไม่ถูกทิ้งเงียบ ๆ** — แผนเตือนไว้ตรง ๆ ว่า `_EDITABLE_COLUMNS` เป็น allowlist
#      ⇒ เพิ่มคอลัมน์แล้วไม่แตะ `_ROW_COLUMNS` **และ** schema ⇒ เขียนลง DB ได้แต่อ่านไม่ขึ้น
#      ซึ่งเป็นความผิดที่ **เทสต์ที่ดูแค่ HTTP 200 จับไม่ได้** (200 = "สำเร็จ" ทั้งที่ค่าหาย)
#      ⇒ ทุกเทสต์ที่นี่อ่าน **DB ตรง ๆ** ประกอบเสมอ
#   2. **ตัวกรองหมายถึงสิ่งที่พูด** — `None` = ทุกหมวด **ไม่ใช่** หมวด `other`
#      (เป็นบั๊กคลาสสิกของ `if category:` กับ `if category is not None:`)
#   3. **CHECK ที่ DB ทำงานจริง** — พิสูจน์ด้วยการ INSERT ค่าที่ผิด **ตรงเข้าไปในตาราง**
#      เพราะชั้น API กรองไว้ก่อนถึง DB ⇒ ถ้าดูแค่ HTTP จะไม่รู้เลยว่าด่าน DB มีอยู่จริง

# ค่าที่ระบบรู้จัก — ต้องตรงกับ `EventCategory` (backend) และ `EVENT_CATEGORIES` (frontend)
_KNOWN_CATEGORIES = ("academic", "sports", "arts", "service", "club", "meeting", "other")


async def _db_category(db_pool, event_id):
    async with db_pool.acquire() as conn:
        return await conn.fetchval("SELECT category FROM events WHERE id = $1", event_id)


async def _count_events(db_pool):
    async with db_pool.acquire() as conn:
        return await conn.fetchval("SELECT COUNT(*) FROM events")


@pytest.mark.asyncio
async def test_create_without_category_defaults_to_other(ev_world, client, db_pool):
    """ไม่ส่ง `category` มา ⇒ ได้ `other` **ใน DB จริง** (ไม่ใช่แค่ใน response)

    ⭐ สัญญาที่สำคัญคือ "สร้างกิจกรรมได้เหมือนเดิม" — ฟอร์ม/สคริปต์เดิมที่ไม่มีฟิลด์นี้
       ต้องไม่พัง (คอลัมน์เป็น `NOT NULL` ⇒ ถ้า default หลุด จะได้ 500 ไม่ใช่ 400)
    """
    event_id = _create(client, ev_world)["id"]
    assert await _db_category(db_pool, event_id) == "other"


@pytest.mark.asyncio
async def test_create_and_patch_category_round_trip(ev_world, client, db_pool):
    """★★ เทสต์หลักของ D4 — สร้างด้วยหมวดหนึ่ง แก้เป็นอีกหมวด แล้ว **อ่านจาก DB**

    ตรึงกับดัก "ค่าถูกทิ้งเงียบ ๆ" ทั้งสองทาง:
      · ขาเขียน — `_EDITABLE_COLUMNS` ต้องมี `category` ไม่งั้น PATCH จะไม่เขียนอะไรเลย
      · ขาอ่าน — `_ROW_COLUMNS` + `EventOut` ต้องมี ไม่งั้น response จะคืน `other` ลอย ๆ
        (ค่า default ของ schema) แทนค่าจริง — ซึ่ง **ดูเหมือนสำเร็จ** ทุกประการ
    """
    created = _create(client, ev_world, category="sports")
    event_id = created["id"]
    assert created["category"] == "sports"
    assert await _db_category(db_pool, event_id) == "sports"

    res = client.patch(
        f"/api/events/{event_id}", json={"category": "arts"}, headers=_auth(ev_world)
    )
    assert res.status_code == 200, res.text
    assert res.json()["category"] == "arts"
    assert await _db_category(db_pool, event_id) == "arts"

    # อ่านซ้ำผ่าน GET — พิสูจน์ว่าค่ามาจากคอลัมน์จริง ไม่ใช่ค่าที่ค้างอยู่ใน response ของ PATCH
    fetched = client.get(f"/api/events?status=live", headers=_auth(ev_world)).json()
    row = next(i for i in fetched["items"] if i["id"] == event_id)
    assert row["category"] == "arts"


@pytest.mark.asyncio
async def test_unknown_category_is_rejected_with_422_not_500(ev_world, client, db_pool):
    """🚨 ค่าที่ DB ไม่รู้จักต้องได้ **422 พร้อมข้อความที่อ่านออก** ไม่ใช่ 500 จาก CHECK violation

    ⭐ นี่คือเหตุผลที่ต้องมี `EventCategory` (Literal) **ทั้งที่มี CHECK ที่ DB แล้ว** —
       สองชั้นทำคนละอย่าง: DB กันข้อมูลเสียถาวร · schema แปลงเป็นคำตอบที่ผู้ใช้อ่านออก
       ⇒ ถ้าถอด Literal ออก เทสต์นี้จะได้ 500 (asyncpg CheckViolationError หลุดเป็น
         unexpected error ที่ router ไม่ได้ดัก) ซึ่ง **ไม่มีใครรู้ว่าต้องแก้ตรงไหน**

    ⚠️ **422 ไม่ใช่ 400 โดยเจตนา** — เป็นการตรวจที่ชั้น schema (body) ซึ่งทั้งระบบใช้ 422
       เหมือนกันหมด (`test_create_validation_422` · `test_list_events_bad_status_is_422`)
       ⇒ ผู้ใช้เห็นข้อความไทยจาก `api.ts` ที่แปลง `detail[]` ให้อยู่แล้ว
       · ส่วน **query param** ของตัวกรองก็ 422 เช่นกัน (มาจาก `pattern=` ที่ router
         ไม่ใช่จาก service) — ดู `test_unknown_category_filter_is_422_on_both_lists`

    ⚠️ และต้องไม่มีแถวถูกสร้างด้วย — การปฏิเสธต้องไม่ทิ้งขยะไว้
    """
    before = await _count_events(db_pool)

    res = client.post(
        "/api/events", json=_body(category="ท่องเที่ยว"), headers=_auth(ev_world)
    )
    assert res.status_code == 422, res.text
    assert await _count_events(db_pool) == before

    event_id = _create(client, ev_world)["id"]
    patched = client.patch(
        f"/api/events/{event_id}", json={"category": "ไม่รู้จัก"}, headers=_auth(ev_world)
    )
    assert patched.status_code == 422, patched.text
    assert await _db_category(db_pool, event_id) == "other", "ค่าของเดิมต้องไม่ถูกแตะ"


@pytest.mark.asyncio
async def test_patch_category_null_is_422_and_leaves_value_untouched(ev_world, client, db_pool):
    """`category: null` = คำขอที่ทำไม่ได้ ⇒ **422** ไม่ใช่ 500 (NotNullViolation)

    ⚠️ คอลัมน์เป็น `NOT NULL` ⇒ ถ้าปล่อย `null` ผ่าน schema ไปถึง SQL จะได้
       `NotNullViolationError` = 500 ซึ่งอ่านไม่ออกว่าใครผิด
       · ต่างจาก `location`/`capacity` ที่ `null` มีความหมายว่า "ล้างค่า" จริง ๆ
       · เทสต์นี้จึงต้องคู่กับการยืนยันว่า **ค่าเดิมยังอยู่** — ไม่ใช่แค่ "ไม่พัง"

    📌 เทสต์นี้คือด่านของ `_reject_null_category` — pydantic v2 **ไม่เรียก validator
       เมื่อฟิลด์ไม่ถูกส่งมา** ⇒ ตัวนั้นยิงเฉพาะตอนได้ `null` มาจริง ๆ ซึ่งเทสต์นี้พิสูจน์
       · และมีเทสต์คู่กันที่พิสูจน์ว่า **"ไม่ส่ง" ยังคงทำงานถูก** (ค่าคงเดิม) —
         `test_create_and_patch_category_round_trip` ส่ง `{"category": "arts"}` เท่านั้น
    """
    event_id = _create(client, ev_world, category="club")["id"]

    res = client.patch(
        f"/api/events/{event_id}", json={"category": None}, headers=_auth(ev_world)
    )
    assert res.status_code == 422, res.text
    assert await _db_category(db_pool, event_id) == "club"


@pytest.mark.asyncio
async def test_category_filter_distinguishes_none_from_other(ev_world, client, db_pool):
    """★ `category=None` (ไม่ส่งมา) = **ทุกหมวด** · `category=other` = **เฉพาะ other**

    🚨 กับดักที่เทสต์นี้จับ: เขียน `if category:` แทน `if category is not None:`
       ⇒ สตริงว่างจะกลายเป็น "ไม่กรอง" (ซึ่งบังเอิญถูก) แต่โค้ดที่เผลอเขียน
         `if category != "other"` หรือใช้ `or` ในการเลือกค่า จะรวมสองความหมายเข้าด้วยกัน
       · ที่เจ็บจริงคือผู้ใช้ที่ **อยากดูเฉพาะ "อื่น ๆ"** แล้วได้ทั้งหมดแทน — ซึ่ง
         "ดูเหมือนทำงาน" เพราะได้รายการมาแสดงเต็มไปหมด
    """
    sports_id = _create(client, ev_world, category="sports", title="แข่งกีฬา")["id"]
    other_id = _create(client, ev_world, category="other", title="อื่น ๆ")["id"]

    async def ids(**params):
        res = client.get("/api/events?status=live", params=params, headers=_auth(ev_world))
        assert res.status_code == 200, res.text
        return {i["id"] for i in res.json()["items"]}

    every = await ids()
    assert {sports_id, other_id} <= every, "ไม่ส่ง category ⇒ ต้องได้ทุกหมวด"

    only_other = await ids(category="other")
    assert other_id in only_other
    assert sports_id not in only_other, (
        "กรอง 'other' แล้วยังเห็นหมวดอื่น — นี่คืออาการของ `if category:` ที่หลุด"
    )

    only_sports = await ids(category="sports")
    assert only_sports == {sports_id}


@pytest.mark.asyncio
async def test_unknown_category_filter_is_422_on_both_lists(ev_world, client, db_pool):
    """กรองด้วยหมวดที่ไม่มีอยู่ **ไม่ใช่** "ได้ลิสต์ว่าง" — ต้องเป็น 422

    ⚠️ สองอย่างนี้ผู้ใช้ตีความต่างกันมาก: ลิสต์ว่างอ่านได้ว่า "ไม่มีกิจกรรมหมวดนี้"
       ซึ่งเป็นข้อมูลที่ผิด ⇒ ต้องบอกว่า "คำขอผิด" ไม่ใช่ "ไม่มีข้อมูล"
       (หลักเดียวกับ `scope`/`status` ที่ปฏิเสธด้วย 422 ผ่าน `pattern=` เหมือนกัน)

    ⭐ เทสต์นี้ยิง **ทั้งสอง endpoint** โดยเจตนา — pattern ถูกประกาศเป็น `_CATEGORY_PATTERN`
       ตัวเดียวแล้วอ้างสองที่ ⇒ ถ้ามีคนเผลอเขียน regex ซ้ำเฉพาะที่ใดที่หนึ่ง
       (ซึ่งจะเพี้ยนจาก `EventCategory` ทันทีที่มีคนเพิ่มหมวด) ที่นี่จะจับได้
    """
    _create(client, ev_world)

    for url in ("/api/events?status=live", "/api/events/public?scope=all"):
        res = client.get(url, params={"category": "quidditch"}, headers=_auth(ev_world))
        assert res.status_code == 422, f"{url} → {res.status_code}: {res.text}"


@pytest.mark.asyncio
async def test_public_list_carries_and_filters_category(ev_world, client, db_pool):
    """ฝั่งนักเรียนก็เห็นหมวด และกรองได้ — ใช้ตัวกรอง **คนละชุด param** กับฝั่งจัดการ

    ⚠️ ฝั่ง public มี `_MY_REG_JOIN` จอง `$1` ไว้ ⇒ เลข placeholder ของ count กับ rows
       **ไม่เท่ากัน** (ดู `_envelope`) ⇒ เทสต์นี้คือด่านที่จับ "สลับเลข placeholder"
       ซึ่งจะพังเป็น `the server expects N arguments` — แต่ถ้าเลขบังเอิญตรงกัน
       (เช่นตอนไม่ส่ง category) ก็จะผ่าน ⇒ ต้องยิง **ทั้งตอนกรองและตอนไม่กรอง**
    """
    meeting_id = _create(client, ev_world, category="meeting")["id"]
    service_id = _create(client, ev_world, category="service")["id"]
    for eid in (meeting_id, service_id):
        _publish(client, ev_world, eid)

    all_res = client.get("/api/events/public?scope=all", headers=_auth(ev_world, "alice"))
    assert all_res.status_code == 200, all_res.text
    assert {i["id"] for i in all_res.json()["items"]} >= {meeting_id, service_id}

    filtered = client.get(
        "/api/events/public?scope=all",
        params={"category": "meeting"},
        headers=_auth(ev_world, "alice"),
    )
    assert filtered.status_code == 200, filtered.text
    body = filtered.json()
    assert {i["id"] for i in body["items"]} == {meeting_id}
    # ⚠️ `total` ต้องถูกกรองด้วย ไม่ใช่ยอดรวมทั้งตาราง — ตัวนับผิดจะทำให้ UI แสดง
    #    "มี 2 รายการ" ทั้งที่โชว์ 1 แถว (และ pagination เพี้ยน)
    assert body["total"] == 1
    assert body["items"][0]["category"] == "meeting"


@pytest.mark.asyncio
async def test_db_check_constraint_rejects_unknown_category(db_pool):
    """🔒 พิสูจน์ **CHECK ที่ฐานข้อมูล** — ยิง INSERT ตรงเข้าตาราง ข้ามชั้น API

    ⭐ ทำไมต้องมีเทสต์นี้ทั้งที่ชั้น API กรองแล้ว: `EventCategory` เป็น **โค้ด Python**
       ซึ่งกันได้เฉพาะเส้นทางที่ผ่าน Pydantic · ส่วน `CHECK` เป็น **สัญญาของข้อมูล**
       ที่กันทุกเส้นทาง (สคริปต์, seed, psql, หรือโค้ดในอนาคตที่ลืมใช้ schema)
       ⇒ ถ้าเทสต์นี้หายไป การเผลอลบ CHECK จะไม่มีอะไรจับได้เลย

    ⚠️ เทสต์นี้จะไม่มีทางผ่านถ้า CHECK ถูกถอด — และจะไม่ผ่านถ้าใส่ค่าได้ (นั่นคือประเด็น)
    """
    async with db_pool.acquire() as conn:
        uid = await conn.fetchval("SELECT id FROM users LIMIT 1")
        with pytest.raises(asyncpg.CheckViolationError):
            await conn.execute(
                """
                INSERT INTO events (title, event_date, category, created_by)
                VALUES ('หมวดเถื่อน', NOW() + INTERVAL '1 day', 'quidditch', $1)
                """,
                uid,
            )
        # และค่า NULL ก็ต้องไม่ผ่านเช่นกัน — คอลัมน์เป็น NOT NULL
        with pytest.raises(asyncpg.NotNullViolationError):
            await conn.execute(
                """
                INSERT INTO events (title, event_date, category, created_by)
                VALUES ('ไม่มีหมวด', NOW() + INTERVAL '1 day', NULL, $1)
                """,
                uid,
            )


@pytest.mark.asyncio
async def test_migration_026_is_idempotent_and_backfills_by_default(ev_world, client, db_pool):
    """★★ migration 026 รันซ้ำได้ และ **ไม่ต้องมี UPDATE backfill** เลย

    ⭐ สองข้อที่พิสูจน์ที่นี่ (ที่อื่นพิสูจน์ไม่ได้):

      1. **`upgrade()` รันซ้ำไม่ error** — ๓ คำสั่งของ 026 เป็น
         `DROP CONSTRAINT IF EXISTS` → `ADD COLUMN IF NOT EXISTS` → `ADD CONSTRAINT`
         ⚠️ `ADD CONSTRAINT` **ไม่ idempotent** (ตัวอื่นมี `IF EXISTS`/`IF NOT EXISTS` คุมไว้)
         ⇒ ลำดับนี้เท่านั้นที่ปลอดภัย · ถ้ามีคนสลับหรือถอด `DROP` ออก
         การรัน migration ซ้ำ (เช่นบน DB ที่สร้างจาก `init_db.py` ซึ่งมี constraint อยู่แล้ว)
         จะพังด้วย `constraint already exists` — และพัง **ตอน deploy** ไม่ใช่ตอนเทสต์ปกติ

      2. **แถวที่มีอยู่ก่อนได้ `'other'` จาก DEFAULT ไม่ใช่ NULL** — เอกสารของ 026 อ้างว่า
         "ไม่ต้อง backfill" · คำอ้างนั้นจะกลายเป็นเท็จทันทีที่ใครเปลี่ยน `NOT NULL DEFAULT 'other'`
         เป็นคอลัมน์ที่ nullable หรือ `ADD COLUMN category` เฉย ๆ (ซึ่งจะได้ NULL กับทุกแถว
         แล้ว `EventOut` จะคืน `null` ไปให้นักเรียนเห็นช่องว่าง)

    ⚠️ ทำใน transaction แล้ว **rollback** (แบบเดียวกับ `test_migration_025_recreates_schema_when_missing`)
       — DDL ใน PostgreSQL เป็น transactional ⇒ ถอยกลับได้จริง ไม่ทิ้งสภาพให้เทสต์ไฟล์อื่นพัง
    """
    mig = importlib.import_module("migrations.026_event_category")

    # สร้าง "แถวที่มีมาก่อน migration" — ต้องอยู่นอก tx ที่เราจะ rollback ไม่งั้นหายไปด้วย
    event_id = _create(client, ev_world, category="sports")["id"]

    async with db_pool.acquire() as conn:
        tx = conn.transaction()
        await tx.start()
        try:
            # ย้อนสภาพกลับเป็น "DB ก่อน 026" — ไม่มีทั้งคอลัมน์และ constraint
            await conn.execute("ALTER TABLE events DROP CONSTRAINT IF EXISTS chk_events_category")
            await conn.execute("ALTER TABLE events DROP COLUMN IF EXISTS category")
            assert (
                await conn.fetchval(
                    """
                    SELECT COUNT(*) FROM information_schema.columns
                    WHERE table_name = 'events' AND column_name = 'category'
                    """
                )
                == 0
            )

            await mig.upgrade(conn)
            await mig.upgrade(conn)  # ← หัวใจ: รันซ้ำต้องไม่ error

            col = await conn.fetchrow(
                """
                SELECT is_nullable, column_default FROM information_schema.columns
                WHERE table_name = 'events' AND column_name = 'category'
                """
            )
            assert col is not None, "026 ต้องสร้างคอลัมน์ category"
            assert col["is_nullable"] == "NO", "คอลัมน์ต้องเป็น NOT NULL"
            assert "other" in (col["column_default"] or ""), (
                "ต้องมี DEFAULT 'other' — ไม่มีแล้วแถวเดิมจะได้ NULL"
            )

            constraints = {
                r["conname"]
                for r in await conn.fetch(
                    "SELECT conname FROM pg_constraint WHERE conrelid = 'events'::regclass"
                )
            }
            assert "chk_events_category" in constraints

            # ⭐ แถวที่สร้างไว้ **ก่อน** คอลัมน์มีอยู่ ต้องได้ 'other' จาก DEFAULT เอง
            assert (
                await conn.fetchval("SELECT category FROM events WHERE id = $1", event_id) == "other"
            ), "แถวเดิมต้องไม่เป็น NULL — นี่คือเหตุผลที่ 026 ไม่ต้องมี UPDATE backfill"
        finally:
            await tx.rollback()

    # ถอยกลับจริง — ค่าที่เทสต์สร้างไว้ยังอยู่และยังเป็นค่าที่ตั้งไว้
    assert await _db_category(db_pool, event_id) == "sports"


# ============================================================
# 12) อ่านกิจกรรมใบเดียว (`GET /events/{id}`) — รอบ 4
# ============================================================

@pytest.mark.asyncio
async def test_get_event_returns_draft(ev_world, client, db_pool):
    """★ หัวใจ: **ฉบับร่างต้องอ่านได้** — นี่คือเหตุผลทั้งหมดที่ต้องมี endpoint นี้

    หน้าแก้ไข/หน้ารายชื่อเป็นหน้าเต็มหน้าที่เปิดตรงได้ ⇒ ต้องอ่านใบเดียวด้วย id
    และ `GET /events/public/{id}` ทำหน้าที่นี้ไม่ได้เพราะกรอง `status='published'`
    (เทสต์นี้จึงเทียบกับฝั่งนักเรียนด้านล่าง เพื่อพิสูจน์ว่าไม่ใช่ของซ้ำกัน)
    """
    event_id = _create(client, ev_world)["id"]   # สร้าง = draft เสมอ

    res = client.get(f"/api/events/{event_id}", headers=_auth(ev_world))
    assert res.status_code == 200, res.text
    out = res.json()

    assert out["id"] == event_id
    assert out["status"] == "draft"

    # เทียบกับ DB จริง (RULE 2) — ไม่เชื่อ response อย่างเดียว
    row = await _db_event(db_pool, event_id)
    assert out["title"] == row["title"]
    assert out["status"] == row["status"] == "draft"

    # ⭐ พิสูจน์ว่าทำไม `/public/{id}` ใช้แทนไม่ได้ — ฉบับร่างต้อง 404 ที่นั่น
    pub = client.get(f"/api/events/public/{event_id}", headers=_auth(ev_world))
    assert pub.status_code == 404, "ฉบับร่างต้องไม่หลุดทางฝั่งนักเรียน (นี่คือเหตุผลของ endpoint ใหม่)"


@pytest.mark.asyncio
async def test_get_event_matches_list_row(ev_world, client, db_pool):
    """ใบเดียวกับในลิสต์ต้องให้ค่า **ชุดเดียวกัน** — ไม่งั้นหน้าแก้ไขจะเติมฟอร์มไม่ครบ

    ⚠️ ทั้งสองที่ใช้ `_MANAGE_COLUMNS` ร่วมกันโดยเจตนา ⇒ เทสต์นี้กันวันที่คนใดคนหนึ่ง
       เผลอ SELECT คนละชุด (อาการ: เปิดจากลิสต์เห็นข้อมูลครบ แต่เปิดตรง ๆ แล้วช่องว่าง)
    """
    event_id = _create(client, ev_world, category="sports", capacity=30)["id"]
    _publish(client, ev_world, event_id)
    _register(client, ev_world, event_id, "alice")

    listed = next(
        i for i in client.get("/api/events?status=all", headers=_auth(ev_world)).json()["items"]
        if i["id"] == event_id
    )
    single = client.get(f"/api/events/{event_id}", headers=_auth(ev_world)).json()

    assert single == listed, "ใบเดียวกับในลิสต์ต้องให้ field ชุดเดียวกันและค่าเดียวกัน"

    # ตัวนับต้องเป็นของจริง ไม่ใช่ค่าคงที่ 0 ที่เผลอ hardcode
    assert single["registered_count"] == 1
    assert single["waitlisted_count"] == 0
    # ชื่อผู้ดูแลมาจาก `_JOINS` — ถ้าหลุด หน้าแก้ไขจะไม่รู้ว่าใครสร้าง (แต่ยังบันทึกได้)
    assert single["created_by"] == ev_world["manager"]["user_id"]
    assert single["created_by_name"] == "manager ทดสอบ"


@pytest.mark.asyncio
async def test_get_event_allowed_with_explicit_permission(ev_world, client):
    """สิทธิ์ต้องมาจาก JSONB จริง — `granted` เป็น council_member ที่ is_admin = FALSE"""
    event_id = _create(client, ev_world)["id"]
    res = client.get(f"/api/events/{event_id}", headers=_auth(ev_world, "granted"))
    assert res.status_code == 200, res.text


@pytest.mark.asyncio
@pytest.mark.parametrize("event_id", [999_999, 0])
async def test_get_event_404_when_missing(ev_world, client, event_id):
    """ไม่มี id นี้ → 404 (ไม่ใช่ 200 กับ body ว่าง ซึ่ง frontend จะเติมฟอร์มด้วย undefined)"""
    res = client.get(f"/api/events/{event_id}", headers=_auth(ev_world))
    assert res.status_code == 404, res.text


@pytest.mark.asyncio
async def test_get_event_returns_deleted_row(ev_world, client, db_pool):
    """★ ใบที่ถูกลบ (soft delete) ต้องได้ **200 พร้อม `deleted_at`** ไม่ใช่ 404

    เหตุผล: หน้าแก้ไขต้องรู้ว่า "ถูกลบอยู่" เพื่อปิดปุ่มบันทึก — `PATCH` มี
    `deleted_at IS NULL` ⇒ ถ้าหน้านี้ 404 ผู้ใช้จะเจอ "แก้แล้วไม่บันทึก" แทนที่จะรู้สาเหตุ
    ⚠️ ต่างจาก `list_registrations` ที่ **ต้อง** 404 เคสนี้ (ดู docstring ที่นั่น)
       — ที่นั่นถามถึงรายชื่อของกิจกรรมที่ไม่มีอยู่ · ที่นี่ถามถึงตัวกิจกรรมซึ่งยังมีอยู่
    """
    event_id = _create(client, ev_world)["id"]
    assert client.delete(f"/api/events/{event_id}", headers=_auth(ev_world)).status_code == 200

    res = client.get(f"/api/events/{event_id}", headers=_auth(ev_world))
    assert res.status_code == 200, res.text
    assert res.json()["deleted_at"] is not None

    # deep DB — ยืนยันว่าที่ได้มาเป็นแถวที่ถูกลบจริง ไม่ใช่ค่าที่ service แต่งขึ้น
    assert (await _db_event(db_pool, event_id))["deleted_at"] is not None

    # ⭐ และยืนยันว่าทำไมต้องเตือนผู้ใช้: บันทึกทับไม่ได้จนกว่าจะกู้คืน
    patch = client.patch(
        f"/api/events/{event_id}", json={"title": "แก้ใบที่ถูกลบ"}, headers=_auth(ev_world)
    )
    assert patch.status_code == 404, "PATCH บนใบที่ถูกลบต้อง 404 — คือเหตุผลที่หน้าต้องปิดปุ่ม"

    # กู้คืนแล้วต้องแก้ได้ตามปกติ (พิสูจน์ว่า 404 ข้างบนมาจาก deleted_at ไม่ใช่จาก id)
    assert client.post(f"/api/events/{event_id}/restore", headers=_auth(ev_world)).status_code == 200
    assert client.patch(
        f"/api/events/{event_id}", json={"title": "แก้หลังกู้คืน"}, headers=_auth(ev_world)
    ).status_code == 200


@pytest.mark.asyncio
async def test_public_list_survives_adding_by_id_route(ev_world, client):
    """★ regression ของ **ลำดับ route** — `/events/public` (1 segment) ต้องไม่ถูก `/{event_id}` กลืน

    ⚠️ ถ้ามีคนย้าย `GET /{event_id}` ขึ้นไปเหนือกลุ่ม `/public` วันหนึ่ง `public` จะถูก
       parse เป็น `int` ⇒ **422** และหน้ารายการกิจกรรมฝั่งนักเรียนจะพังทั้งหน้า
       ซึ่งอ่านไม่ออกเลยว่ามาจากการเพิ่ม route (ดูคำเตือนที่หัว `event_router.py`)
    """
    event_id = _create(client, ev_world)["id"]
    _publish(client, ev_world, event_id)

    res = client.get("/api/events/public", headers=_auth(ev_world, "alice"))
    assert res.status_code == 200, res.text
    assert event_id in {i["id"] for i in res.json()["items"]}

    # สอง path ที่ความยาวเท่ากันต้องแยกกันได้จริงตามลำดับที่ประกาศ
    assert client.get(
        f"/api/events/public/{event_id}", headers=_auth(ev_world, "alice")
    ).status_code == 200
    assert client.get(
        f"/api/events/{event_id}/my-registration", headers=_auth(ev_world, "alice")
    ).status_code == 200
