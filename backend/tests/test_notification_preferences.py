"""
⚙️ ตั้งค่าการแจ้งเตือนรายกลุ่ม (Notification Preferences)
=============================================================
ทดสอบ 3 ระดับ:
  1) HTTP — GET/PUT /api/notifications/preferences (+ auth guard)
  2) Deep-DB — ค่าลงตารางจริง + unique index กันแถวซ้ำ
  3) **ผลจริงต่อการยิงแจ้งเตือน** — notify / notify_bulk / notify_fanout ต้องเงียบ
     กับคนที่ปิดกลุ่มนั้นไว้ (นี่คือเหตุผลทั้งหมดของการมีตารางนี้ ถ้าพลาดข้อนี้
     ก็ได้หน้าจอตั้งค่าที่กดแล้วไม่มีอะไรเกิดขึ้น)

ตาม docs/rules/testing.md: ทุก test ตรวจ DB ตรง ๆ ผ่าน db_pool ไม่เชื่อ HTTP response
"""
import random

import pytest
import pytest_asyncio

from services import auth_service, notification_service


@pytest_asyncio.fixture
async def pref_world(db_pool):
    """room + student + student2 — พอสำหรับทดสอบ gate ทุกแบบ"""
    room_code = f"บ.{random.randint(1, 90)}"
    async with db_pool.acquire() as conn:
        room_id = await conn.fetchval(
            "INSERT INTO rooms (room_code, room_name, level) VALUES ($1,$2,'ม.5') RETURNING id",
            room_code, room_code
        )

    users = {}
    for label, role, no in [("student", "student", 1), ("student2", "student", 2)]:
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


async def _pref_rows(db_pool, user_id, group_type=None):
    """อ่านค่าดิบจากตาราง (deep-DB)"""
    async with db_pool.acquire() as conn:
        if group_type:
            return await conn.fetch(
                "SELECT * FROM notification_preferences WHERE user_id = $1 AND group_type = $2",
                user_id, group_type,
            )
        return await conn.fetch(
            "SELECT * FROM notification_preferences WHERE user_id = $1 ORDER BY group_type",
            user_id,
        )


async def _count_notifs(db_pool, user_id, group_type=None):
    async with db_pool.acquire() as conn:
        if group_type:
            return await conn.fetchval(
                "SELECT COUNT(*) FROM notifications WHERE user_id = $1 AND group_type = $2",
                user_id, group_type,
            )
        return await conn.fetchval(
            "SELECT COUNT(*) FROM notifications WHERE user_id = $1", user_id
        )


# ===================== 1) GET — zero-fill ครบทุกกลุ่ม =====================

@pytest.mark.asyncio
async def test_get_preferences_zero_fill_when_never_set(client, pref_world, db_pool):
    """ผู้ใช้ใหม่ยังไม่มีแถวเลย → ต้องได้ครบ 4 กลุ่ม enabled=True (ไม่ใช่ [] หรือ null)"""
    res = client.get("/api/notifications/preferences", headers=_auth(pref_world))
    assert res.status_code == 200, res.text
    body = res.json()

    got = {p["group_type"]: p["enabled"] for p in body["preferences"]}
    assert got == {
        "issue_mine": True, "issue_received": True, "board": True, "report": True,
    }, "ต้องคืนครบ 4 กลุ่ม เปิดหมด"

    # deep-DB: ยังไม่มีแถวจริง — ค่ามาจาก zero-fill ไม่ใช่จากตาราง
    assert await _pref_rows(db_pool, pref_world["student"]["user_id"]) == []


# ===================== 2) PUT — ลงตารางจริง =====================

@pytest.mark.asyncio
async def test_put_disable_writes_row(client, pref_world, db_pool):
    """ปิด board → ต้องมีแถว enabled=False ใน DB จริง (ไม่ใช่แค่ echo กลับ)"""
    uid = pref_world["student"]["user_id"]
    res = client.put(
        "/api/notifications/preferences",
        json={"preferences": [{"group_type": "board", "enabled": False}]},
        headers=_auth(pref_world),
    )
    assert res.status_code == 200, res.text

    rows = await _pref_rows(db_pool, uid, "board")
    assert len(rows) == 1, "ต้องมีแถวเดียว"
    assert rows[0]["enabled"] is False, "deep-DB: ต้องเป็น False จริง"

    # response ต้องสะท้อนค่าที่บันทึกแล้ว
    got = {p["group_type"]: p["enabled"] for p in res.json()["preferences"]}
    assert got["board"] is False
    assert got["issue_mine"] is True, "กลุ่มที่ไม่ได้ส่งมาคงค่าเดิม"


@pytest.mark.asyncio
async def test_put_is_partial_not_full_replace(client, pref_world, db_pool):
    """ส่งแค่กลุ่มเดียว → กลุ่มอื่นต้องไม่ถูกแตะ/reset"""
    uid = pref_world["student"]["user_id"]
    client.put(
        "/api/notifications/preferences",
        json={"preferences": [{"group_type": "board", "enabled": False}]},
        headers=_auth(pref_world),
    )
    # รอบสอง: เปิด report (ไม่ได้ส่ง board มา)
    client.put(
        "/api/notifications/preferences",
        json={"preferences": [{"group_type": "report", "enabled": False}]},
        headers=_auth(pref_world),
    )

    rows = {r["group_type"]: r["enabled"] for r in await _pref_rows(db_pool, uid)}
    assert rows == {"board": False, "report": False}, (
        "ต้องมี 2 แถว — board ต้องยังเป็น False (ไม่ถูก reset) และไม่มีแถวของกลุ่มที่ไม่ได้ส่งมา"
    )


@pytest.mark.asyncio
async def test_put_twice_no_duplicate_row(client, pref_world, db_pool):
    """ยิงซ้ำค่าเดิม → unique index ต้องกันแถวซ้ำ (upsert ไม่ใช่ insert ใหม่)"""
    uid = pref_world["student"]["user_id"]
    payload = {"preferences": [{"group_type": "board", "enabled": False}]}
    for _ in range(2):
        res = client.put(
            "/api/notifications/preferences", json=payload, headers=_auth(pref_world)
        )
        assert res.status_code == 200, res.text

    rows = await _pref_rows(db_pool, uid, "board")
    assert len(rows) == 1, "ต้องมีแถวเดียว (ON CONFLICT DO UPDATE ทำงาน)"


@pytest.mark.asyncio
async def test_put_duplicate_group_in_one_request_last_wins(client, pref_world, db_pool):
    """ส่ง group_type เดิมซ้ำในคำขอเดียว → ตัวหลังชนะ ไม่ระเบิด
    (กัน 'ON CONFLICT DO UPDATE command cannot affect row a second time')"""
    uid = pref_world["student"]["user_id"]
    res = client.put(
        "/api/notifications/preferences",
        json={"preferences": [
            {"group_type": "board", "enabled": True},
            {"group_type": "board", "enabled": False},
        ]},
        headers=_auth(pref_world),
    )
    assert res.status_code == 200, res.text
    rows = await _pref_rows(db_pool, uid, "board")
    assert len(rows) == 1 and rows[0]["enabled"] is False, "ตัวหลังต้องชนะ"


# ===================== 3) ผลจริงต่อการยิงแจ้งเตือน =====================

@pytest.mark.asyncio
async def test_notify_silent_when_group_disabled(pref_world, db_pool):
    """⚠️ หัวใจของงานนี้: ปิดกลุ่มแล้ว notify() ต้องไม่ insert อะไรเลย"""
    uid = pref_world["student"]["user_id"]
    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO notification_preferences (user_id, group_type, enabled) VALUES ($1,'board',FALSE)",
            uid,
        )
        async with conn.transaction():
            await notification_service.notify(
                conn, user_id=uid, group_type="board", type="board_new",
                title="ควรถูกบล็อก", body="—", entity_type="board", entity_id=999,
            )
    assert await _count_notifs(db_pool, uid, "board") == 0, "ปิดอยู่ต้องไม่มีแถวเลย"


@pytest.mark.asyncio
async def test_notify_delivers_when_group_enabled(pref_world, db_pool):
    """กลุ่มที่เปิด (หรือไม่มีแถว) ต้องได้ตามปกติ — กัน gate บล็อกเกิน"""
    uid = pref_world["student"]["user_id"]
    async with db_pool.acquire() as conn:
        # ปิด board ไว้ แต่ยิงกลุ่ม report → ต้องผ่าน
        await conn.execute(
            "INSERT INTO notification_preferences (user_id, group_type, enabled) VALUES ($1,'board',FALSE)",
            uid,
        )
        async with conn.transaction():
            await notification_service.notify(
                conn, user_id=uid, group_type="report", type="report_new",
                title="ต้องได้", body="—", entity_type="report", entity_id=1,
            )
    assert await _count_notifs(db_pool, uid, "report") == 1, "กลุ่มอื่นต้องไม่ถูกกระทบ"


@pytest.mark.asyncio
async def test_notify_bulk_filters_only_disabled(pref_world, db_pool):
    """2 ผู้รับ ปิดคนหนึ่ง → ต้องได้แถวเดียว"""
    u1 = pref_world["student"]["user_id"]
    u2 = pref_world["student2"]["user_id"]
    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO notification_preferences (user_id, group_type, enabled) VALUES ($1,'board',FALSE)",
            u2,
        )
        async with conn.transaction():
            await notification_service.notify_bulk(
                conn, [u1, u2], group_type="board", type="board_new",
                title="ทดสอบ bulk", body="—", entity_type="board", entity_id=1,
            )

    assert await _count_notifs(db_pool, u1, "board") == 1, "คนที่เปิดต้องได้"
    assert await _count_notifs(db_pool, u2, "board") == 0, "คนที่ปิดต้องไม่ได้"


@pytest.mark.asyncio
async def test_notify_bulk_all_disabled_no_error(pref_world, db_pool):
    """ปิดกันหมด → ต้องไม่ error และไม่ insert"""
    u1 = pref_world["student"]["user_id"]
    u2 = pref_world["student2"]["user_id"]
    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO notification_preferences (user_id, group_type, enabled) "
            "VALUES ($1,'board',FALSE), ($2,'board',FALSE)",
            u1, u2,
        )
        async with conn.transaction():
            await notification_service.notify_bulk(
                conn, [u1, u2], group_type="board", type="board_new",
                title="ทดสอบ bulk", body="—", entity_type="board", entity_id=1,
            )
    assert await _count_notifs(db_pool, u1) == 0
    assert await _count_notifs(db_pool, u2) == 0


@pytest.mark.asyncio
async def test_notify_fanout_skips_disabled_user(pref_world, db_pool):
    """⚠️ fan-out ยิงทุก active user — ต้องกรองคนที่ปิดออกใน SQL
    (ตัวนี้พลาดง่ายสุด เพราะเงื่อนไขอยู่ใน INSERT … SELECT ไม่ใช่ Python)"""
    u1 = pref_world["student"]["user_id"]
    u2 = pref_world["student2"]["user_id"]
    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO notification_preferences (user_id, group_type, enabled) VALUES ($1,'board',FALSE)",
            u2,
        )
        async with conn.transaction():
            await notification_service.notify_fanout(
                conn, group_type="board", type="board_new",
                title="fan-out", body="—", entity_type="board", entity_id=1,
            )

    assert await _count_notifs(db_pool, u1, "board") == 1, "u1 เปิดอยู่ต้องได้"
    assert await _count_notifs(db_pool, u2, "board") == 0, "u2 ปิดอยู่ต้องไม่ได้"


@pytest.mark.asyncio
async def test_notify_fanout_actor_exclusion_still_works(pref_world, db_pool):
    """ตรวจว่าแก้ SQL แล้ว self-exclusion เดิม (actor_id) ยังทำงาน
    + DISTINCT ยังกันแถวซ้ำ (แก้ SQL พลาดข้อนี้ได้ง่าย)"""
    u1 = pref_world["student"]["user_id"]
    async with db_pool.acquire() as conn:
        async with conn.transaction():
            await notification_service.notify_fanout(
                conn, group_type="board", type="board_new",
                title="fan-out", body="—", entity_type="board", entity_id=1,
                actor_id=u1,
            )
    assert await _count_notifs(db_pool, u1, "board") == 0, "actor ต้องไม่แจ้งตัวเอง"


# ===================== 4) Auth + validation =====================

@pytest.mark.asyncio
async def test_preferences_require_login(client, pref_world):
    """X-API-Key (system RPC) → user_id เป็น None → ต้อง 401 ไม่ใช่ 500"""
    headers = {"X-API-Key": "test-api-key"}
    assert client.get("/api/notifications/preferences", headers=headers).status_code == 401
    assert client.put(
        "/api/notifications/preferences",
        json={"preferences": [{"group_type": "board", "enabled": False}]},
        headers=headers,
    ).status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_group", ["", "events", "board' OR 1=1--", "issue_mine2", "BOARD"])
async def test_put_rejects_unknown_group_type(client, pref_world, bad_group):
    """group_type นอกลิสต์ → 422 ที่ชั้น Pydantic (ไม่หลุดไปถึง SQL)"""
    res = client.put(
        "/api/notifications/preferences",
        json={"preferences": [{"group_type": bad_group, "enabled": False}]},
        headers=_auth(pref_world),
    )
    assert res.status_code == 422, f"group_type={bad_group!r} ต้องถูกปฏิเสธ"


@pytest.mark.asyncio
async def test_put_rejects_empty_list(client, pref_world):
    """ส่งรายการว่าง → 422 (no-op ที่ไม่มีความหมาย)"""
    res = client.put(
        "/api/notifications/preferences",
        json={"preferences": []},
        headers=_auth(pref_world),
    )
    assert res.status_code == 422, res.text


@pytest.mark.asyncio
async def test_preferences_are_per_user(client, pref_world, db_pool):
    """ค่าของ student ต้องไม่รั่วไปหา student2 — regression กันพลาดใช้ user_id จาก client"""
    client.put(
        "/api/notifications/preferences",
        json={"preferences": [{"group_type": "board", "enabled": False}]},
        headers=_auth(pref_world, "student"),
    )

    res = client.get("/api/notifications/preferences", headers=_auth(pref_world, "student2"))
    got = {p["group_type"]: p["enabled"] for p in res.json()["preferences"]}
    assert got["board"] is True, "student2 ต้องไม่ได้รับผลจากการตั้งค่าของ student"
    assert await _pref_rows(db_pool, pref_world["student2"]["user_id"]) == []
