# === Announcement Tests: จัดการประกาศ (CRUD) + migration 014 (คอลัมน์ผู้ประกาศ + backfill สิทธิ์) ===
#
# กฎที่ยึดตาม docs/rules/testing.md:
#   - ทุกเทสต์ยืนยันผลถึงชั้น DB จริง (ไม่เชื่อแค่ HTTP status)
#   - id สุ่มทุกครั้ง ไม่ hardcode
#   - mock side effect ภายนอก (ที่นี่ไม่มี — ไม่มี Redis/API นอก)
import importlib
import json
import random

import asyncpg
import pytest
import pytest_asyncio

from services import auth_service


@pytest_asyncio.fixture
async def announcement_world(db_pool, client):
    """
    โลกทดสอบ: ห้องเดียว + 4 บทบาท

      - admin            → is_admin=true  (ผ่านได้โดยไม่ต้องดู permissions)
      - council          → council_member, is_admin=FALSE ← ตัวสำคัญที่สุด
      - teacher          → ครูทั่วไป (มี MANAGE_STUDENTS แต่ไม่มีสิทธิ์ประกาศ)
      - student          → นักเรียนทั่วไป

    ⚠️ ต้องรับ `client` เข้ามาใน signature โดยเจตนา — เพื่อ "บังคับลำดับ" ให้ TestClient
       เปิด app (ซึ่งรัน init_db → seed ประกาศ 2 แถว) จบก่อน แล้วเราจึงล้างตารางได้จริง
       ถ้าไม่รับ `client` ลำดับ fixture ไม่การันตี → seed อาจวิ่งมาหลังการล้าง แล้วเทสต์
       นับจำนวนผิดแบบไม่ deterministic (ดูบทเรียนใน test_public.py)
    """
    room_code = f"ม.6/{random.randint(1, 90)}"
    async with db_pool.acquire() as conn:
        room_id = await conn.fetchval(
            "INSERT INTO rooms (room_code, room_name, level) VALUES ($1,$2,'ม.6') RETURNING id",
            room_code, room_code,
        )

    users = {}
    for label, role in [
        ("admin", "admin"),
        ("council", "council_member"),
        ("teacher", "teacher"),
        ("student", "student"),
    ]:
        sid = f"AN{random.randint(1000, 9999)}{label[:2]}"  # ≤ 10 ตัว (student_id VARCHAR(10))
        uid = await auth_service.register_user(
            db_pool, sid, "1234", f"{label} ทดสอบ", sid, room_code, 1, role
        )
        users[label] = {
            "user_id": uid,
            "username": sid,
            "token": auth_service.create_access_token(uid),
        }

    # ล้างประกาศที่ seed มาจาก init_db ให้เทสต์เริ่มจากศูนย์ที่รู้แน่
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM announcements")

    users["room_id"] = room_id
    return users


def _auth(world, actor: str) -> dict:
    return {"Authorization": f"Bearer {world[actor]['token']}"}


def _create(client, world, actor="admin", **overrides):
    payload = {"message": "ประกาศทดสอบ", "priority": "normal"}
    payload.update(overrides)
    return client.post("/api/announcements", json=payload, headers=_auth(world, actor))


async def _audit_rows(db_pool, announcement_id: int):
    """อ่าน audit_logs ของประกาศนี้ (jsonb ต้อง json.loads ก่อนใช้)"""
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT action, user_id, old_values, new_values
            FROM audit_logs
            WHERE entity_type = 'announcement' AND entity_id = $1
            ORDER BY created_at
            """,
            str(announcement_id),
        )
    out = []
    for r in rows:
        d = dict(r)
        for key in ("old_values", "new_values"):
            if isinstance(d[key], str):
                d[key] = json.loads(d[key])
        out.append(d)
    return out


# === Section 1: สร้าง + อ่านรายการ ===
@pytest.mark.asyncio
async def test_create_announcement_success(client, db_pool, announcement_world):
    """สร้างประกาศสำเร็จ → 201 + ค่าลง DB ครบ + created_by/updated_by = ผู้สร้าง"""
    world = announcement_world
    res = _create(client, world, message="ปิดโรงยิมชั่วคราว", priority="urgent",
                  link="https://example.com/notice")

    assert res.status_code == 201
    body = res.json()
    assert body["message"] == "ปิดโรงยิมชั่วคราว"
    assert body["priority"] == "urgent"
    assert body["link"] == "https://example.com/notice"
    assert body["created_by"] == world["admin"]["user_id"]
    assert body["created_by_name"] == "admin ทดสอบ"
    assert body["deleted_at"] is None

    # Deep DB verify
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT message, priority, link, created_by, updated_by, deleted_at, updated_at
            FROM announcements WHERE id = $1
            """,
            body["id"],
        )
    assert row is not None
    assert row["message"] == "ปิดโรงยิมชั่วคราว"
    assert row["priority"] == "urgent"
    assert row["link"] == "https://example.com/notice"
    assert row["created_by"] == world["admin"]["user_id"]
    assert row["updated_by"] == world["admin"]["user_id"]
    assert row["deleted_at"] is None
    assert row["updated_at"] is not None


@pytest.mark.asyncio
async def test_create_writes_audit_log(client, db_pool, announcement_world):
    """ทุกการสร้างต้องมี audit_logs แถว CREATE_ANNOUNCEMENT (เขียนใน transaction เดียว)"""
    world = announcement_world
    ann_id = _create(client, world, priority="high").json()["id"]

    rows = await _audit_rows(db_pool, ann_id)
    assert len(rows) == 1
    assert rows[0]["action"] == "CREATE_ANNOUNCEMENT"
    assert rows[0]["user_id"] == world["admin"]["user_id"]
    assert rows[0]["new_values"]["priority"] == "high"


@pytest.mark.asyncio
async def test_council_member_can_manage_announcements(client, db_pool, announcement_world):
    """
    🔑 เทสต์สำคัญ: สภานักเรียน (council_member) ต้องประกาศได้

    council_member เป็น is_admin=False ⇒ ไม่มีทาง bypass การเช็คสิทธิ์ได้เลย
    ต้องได้สิทธิ์จาก `permissions` จริง ๆ เท่านั้น (บทเรียน skills.md: scope ≠ permission)
    """
    world = announcement_world
    res = _create(client, world, actor="council", message="สภานักเรียนประกาศ")

    assert res.status_code == 201, res.json()
    async with db_pool.acquire() as conn:
        created_by = await conn.fetchval(
            "SELECT created_by FROM announcements WHERE id = $1", res.json()["id"]
        )
    assert created_by == world["council"]["user_id"]


@pytest.mark.asyncio
async def test_list_envelope_and_pagination(client, db_pool, announcement_world):
    """envelope ถูกต้อง + offset เลยหน้าสุดท้ายต้องไม่ทำให้ total เพี้ยนเป็น 0"""
    world = announcement_world
    for i in range(5):
        _create(client, world, message=f"ประกาศที่ {i}")

    res = client.get("/api/announcements?limit=2&offset=0", headers=_auth(world, "admin"))
    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 5
    assert body["page"] == 1
    assert body["page_size"] == 2
    assert body["pages"] == 3
    assert len(body["items"]) == 2

    # Deep DB verify — total ต้องตรงกับของจริงในตาราง
    async with db_pool.acquire() as conn:
        db_total = await conn.fetchval(
            "SELECT COUNT(*) FROM announcements WHERE deleted_at IS NULL"
        )
    assert db_total == body["total"] == 5

    # ⚠️ regression: COUNT(*) OVER() จะคืน total=0 เมื่อ offset เลยข้อมูล
    res = client.get("/api/announcements?limit=2&offset=10", headers=_auth(world, "admin"))
    body = res.json()
    assert body["items"] == []
    assert body["total"] == 5, "หน้าว่างต้องยังรู้ total (ห้ามใช้ COUNT(*) OVER())"


@pytest.mark.asyncio
async def test_list_orders_urgent_first(client, db_pool, announcement_world):
    """เรียง urgent → high → normal แล้วใหม่สุดก่อน"""
    world = announcement_world
    _create(client, world, message="ปกติ", priority="normal")
    _create(client, world, message="ด่วน", priority="urgent")
    _create(client, world, message="สำคัญ", priority="high")

    res = client.get("/api/announcements", headers=_auth(world, "admin"))
    priorities = [i["priority"] for i in res.json()["items"]]
    assert priorities == ["urgent", "high", "normal"]


@pytest.mark.asyncio
async def test_list_status_filter(client, db_pool, announcement_world):
    """กรอง active / deleted / all แยกกันถูกต้อง + deep DB verify"""
    world = announcement_world
    keep_id = _create(client, world, message="ยังอยู่").json()["id"]
    del_id = _create(client, world, message="จะถูกลบ").json()["id"]
    client.delete(f"/api/announcements/{del_id}", headers=_auth(world, "admin"))

    active = client.get("/api/announcements?status=active", headers=_auth(world, "admin")).json()
    deleted = client.get("/api/announcements?status=deleted", headers=_auth(world, "admin")).json()
    allof = client.get("/api/announcements?status=all", headers=_auth(world, "admin")).json()

    assert [i["id"] for i in active["items"]] == [keep_id]
    assert [i["id"] for i in deleted["items"]] == [del_id]
    assert len(allof["items"]) == 2

    async with db_pool.acquire() as conn:
        assert await conn.fetchval(
            "SELECT COUNT(*) FROM announcements WHERE deleted_at IS NULL"
        ) == active["total"]
        assert await conn.fetchval(
            "SELECT COUNT(*) FROM announcements WHERE deleted_at IS NOT NULL"
        ) == deleted["total"]


@pytest.mark.asyncio
async def test_seeded_row_without_author_still_listed(client, db_pool, announcement_world):
    """ประกาศที่ created_by เป็น NULL (seed เก่า) ต้องยังออกมาในรายการ — พิสูจน์ว่าเป็น LEFT JOIN"""
    world = announcement_world
    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO announcements (message, priority) VALUES ($1, 'normal')",
            "ประกาศจาก seed",
        )

    res = client.get("/api/announcements", headers=_auth(world, "admin"))
    assert res.status_code == 200
    items = res.json()["items"]
    assert len(items) == 1, "แถวที่ไม่มีผู้ประกาศต้องไม่ถูก JOIN ตัดทิ้ง"
    assert items[0]["created_by"] is None
    assert items[0]["created_by_name"] is None


# === Section 2: แก้ไข ===
@pytest.mark.asyncio
async def test_update_partial_does_not_touch_other_fields(client, db_pool, announcement_world):
    """PATCH ส่งฟิลด์เดียว → ฟิลด์อื่นคงเดิม (model_dump(exclude_unset=True))"""
    world = announcement_world
    ann_id = _create(client, world, message="ข้อความเดิม", priority="normal").json()["id"]

    res = client.patch(
        f"/api/announcements/{ann_id}",
        json={"priority": "urgent"},
        headers=_auth(world, "admin"),
    )
    assert res.status_code == 200

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT message, priority, updated_by FROM announcements WHERE id = $1", ann_id
        )
    assert row["priority"] == "urgent"
    assert row["message"] == "ข้อความเดิม", "ฟิลด์ที่ไม่ได้ส่งมาต้องไม่ถูกแตะ"
    assert row["updated_by"] == world["admin"]["user_id"]


@pytest.mark.asyncio
async def test_update_writes_audit_old_and_new_values(client, db_pool, announcement_world):
    """audit ของการแก้ต้องมีทั้ง old_values และ new_values"""
    world = announcement_world
    ann_id = _create(client, world, priority="normal").json()["id"]

    client.patch(
        f"/api/announcements/{ann_id}",
        json={"priority": "high"},
        headers=_auth(world, "admin"),
    )

    rows = await _audit_rows(db_pool, ann_id)
    actions = [r["action"] for r in rows]
    assert actions == ["CREATE_ANNOUNCEMENT", "UPDATE_ANNOUNCEMENT"]

    upd = rows[1]
    assert upd["old_values"]["priority"] == "normal"
    assert upd["new_values"]["priority"] == "high"
    assert upd["user_id"] == world["admin"]["user_id"]


@pytest.mark.asyncio
async def test_update_can_clear_link(client, db_pool, announcement_world):
    """ส่ง link: null มาชัด ๆ = สั่งล้างลิงก์ (ต่างจากไม่ส่งมาเลย)"""
    world = announcement_world
    ann_id = _create(client, world, link="https://example.com/a").json()["id"]

    res = client.patch(
        f"/api/announcements/{ann_id}", json={"link": None}, headers=_auth(world, "admin")
    )
    assert res.status_code == 200

    async with db_pool.acquire() as conn:
        link = await conn.fetchval("SELECT link FROM announcements WHERE id = $1", ann_id)
    assert link is None


@pytest.mark.asyncio
async def test_update_nonexistent_returns_404(client, db_pool, announcement_world):
    """แก้ประกาศที่ไม่มี → 404 และต้องไม่เขียน audit ทิ้งไว้"""
    world = announcement_world
    res = client.patch(
        "/api/announcements/999999999", json={"priority": "high"}, headers=_auth(world, "admin")
    )
    assert res.status_code == 404

    async with db_pool.acquire() as conn:
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM audit_logs WHERE action = 'UPDATE_ANNOUNCEMENT'"
        )
    assert count == 0


@pytest.mark.asyncio
async def test_update_empty_body_returns_400(client, db_pool, announcement_world):
    """PATCH ที่ไม่มีฟิลด์ที่จะแก้เลย → 400 (ไม่ใช่ 200 เงียบ ๆ)"""
    world = announcement_world
    ann_id = _create(client, world).json()["id"]

    res = client.patch(
        f"/api/announcements/{ann_id}", json={}, headers=_auth(world, "admin")
    )
    assert res.status_code == 400


# === Section 3: ลบ (soft) + กู้คืน ===
@pytest.mark.asyncio
async def test_soft_delete_keeps_row(client, db_pool, announcement_world):
    """ลบ = soft delete → แถวยังอยู่ แต่ deleted_at มีค่า (ไม่ hard delete)"""
    world = announcement_world
    ann_id = _create(client, world).json()["id"]

    res = client.delete(f"/api/announcements/{ann_id}", headers=_auth(world, "admin"))
    assert res.status_code == 200

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT deleted_at, count(*) OVER () AS n FROM announcements WHERE id = $1", ann_id
        )
    assert row is not None, "ต้องยังมีแถวอยู่ (soft delete)"
    assert row["deleted_at"] is not None
    assert row["n"] == 1


@pytest.mark.asyncio
async def test_deleted_announcement_hidden_from_public(client, db_pool, announcement_world):
    """ประกาศที่ลบแล้วต้องหายจาก Landing Page (public endpoint)"""
    world = announcement_world
    ann_id = _create(client, world, message="จะหายไป").json()["id"]

    before = client.get("/api/v1/public/announcements").json()
    assert any(a["id"] == ann_id for a in before)

    client.delete(f"/api/announcements/{ann_id}", headers=_auth(world, "admin"))

    after = client.get("/api/v1/public/announcements").json()
    assert not any(a["id"] == ann_id for a in after), "ลบแล้วต้องไม่โชว์บน Landing"


@pytest.mark.asyncio
async def test_public_endpoint_does_not_leak_author(client, db_pool, announcement_world):
    """public endpoint ต้องไม่คืน created_by / deleted_at (schema แยกกันโดยเจตนา)"""
    world = announcement_world
    _create(client, world, message="ประกาศสาธารณะ")

    items = client.get("/api/v1/public/announcements").json()
    assert len(items) == 1
    for leaked in ("created_by", "updated_by", "created_by_name", "deleted_at", "created_at"):
        assert leaked not in items[0], f"ห้ามหลุดฟิลด์ {leaked} ออกไปหน้า public"


@pytest.mark.asyncio
async def test_delete_twice_returns_404(client, db_pool, announcement_world):
    """ลบซ้ำ → 404 และ deleted_at เดิมต้องไม่ถูกทับด้วย NOW() ใหม่"""
    world = announcement_world
    ann_id = _create(client, world).json()["id"]

    assert client.delete(f"/api/announcements/{ann_id}", headers=_auth(world, "admin")).status_code == 200
    async with db_pool.acquire() as conn:
        first = await conn.fetchval("SELECT deleted_at FROM announcements WHERE id = $1", ann_id)

    res = client.delete(f"/api/announcements/{ann_id}", headers=_auth(world, "admin"))
    assert res.status_code == 404

    async with db_pool.acquire() as conn:
        second = await conn.fetchval("SELECT deleted_at FROM announcements WHERE id = $1", ann_id)
    assert first == second, "กดลบซ้ำต้องไม่เขียนทับเวลาที่ลบจริง"


@pytest.mark.asyncio
async def test_restore_announcement(client, db_pool, announcement_world):
    """กู้คืน → deleted_at กลับเป็น NULL และโผล่บน Landing อีกครั้ง"""
    world = announcement_world
    ann_id = _create(client, world, message="ลบแล้วกู้คืน").json()["id"]
    client.delete(f"/api/announcements/{ann_id}", headers=_auth(world, "admin"))

    res = client.post(f"/api/announcements/{ann_id}/restore", headers=_auth(world, "admin"))
    assert res.status_code == 200

    async with db_pool.acquire() as conn:
        deleted_at = await conn.fetchval(
            "SELECT deleted_at FROM announcements WHERE id = $1", ann_id
        )
    assert deleted_at is None

    public = client.get("/api/v1/public/announcements").json()
    assert any(a["id"] == ann_id for a in public)

    actions = [r["action"] for r in await _audit_rows(db_pool, ann_id)]
    assert actions == ["CREATE_ANNOUNCEMENT", "DELETE_ANNOUNCEMENT", "RESTORE_ANNOUNCEMENT"]


@pytest.mark.asyncio
async def test_restore_active_returns_404(client, db_pool, announcement_world):
    """กู้คืนประกาศที่ยังไม่ถูกลบ → 404"""
    world = announcement_world
    ann_id = _create(client, world).json()["id"]

    res = client.post(f"/api/announcements/{ann_id}/restore", headers=_auth(world, "admin"))
    assert res.status_code == 404


# === Section 4: สิทธิ์ + validation ===
@pytest.mark.asyncio
async def test_create_requires_auth(client, db_pool, announcement_world):
    """ไม่ส่ง token → 401 และต้องไม่มีแถวเกิดขึ้นใน DB"""
    res = client.post("/api/announcements", json={"message": "แอบประกาศ", "priority": "normal"})
    assert res.status_code == 401

    async with db_pool.acquire() as conn:
        assert await conn.fetchval("SELECT COUNT(*) FROM announcements") == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("actor", ["student", "teacher"])
async def test_create_forbidden_for_unauthorized_roles(
    client, db_pool, announcement_world, actor
):
    """
    403 สำหรับผู้ที่ไม่มีสิทธิ์ — รวม 'teacher' ที่มี MANAGE_STUDENTS/VIEW_DASHBOARD
    แต่ไม่มี MANAGE_ANNOUNCEMENTS ⇒ พิสูจน์ว่าไม่ได้แปลว่า "เป็นครูแล้วประกาศได้"
    """
    world = announcement_world
    res = _create(client, world, actor=actor, message=f"ประกาศโดย {actor}")

    assert res.status_code == 403, res.json()
    async with db_pool.acquire() as conn:
        assert await conn.fetchval("SELECT COUNT(*) FROM announcements") == 0, (
            "คำขอที่ถูกปฏิเสธต้องไม่เขียนข้อมูลค้าง"
        )


@pytest.mark.asyncio
async def test_update_and_delete_forbidden(client, db_pool, announcement_world):
    """PATCH/DELETE โดยไม่มีสิทธิ์ → 403 และแถวเดิมต้องไม่ถูกแตะ"""
    world = announcement_world
    ann_id = _create(client, world, message="ของเดิม", priority="normal").json()["id"]

    assert client.patch(
        f"/api/announcements/{ann_id}", json={"priority": "urgent"}, headers=_auth(world, "student")
    ).status_code == 403
    assert client.delete(
        f"/api/announcements/{ann_id}", headers=_auth(world, "student")
    ).status_code == 403

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT message, priority, deleted_at FROM announcements WHERE id = $1", ann_id
        )
    assert row["message"] == "ของเดิม"
    assert row["priority"] == "normal"
    assert row["deleted_at"] is None


@pytest.mark.asyncio
async def test_list_requires_permission(client, db_pool, announcement_world):
    """GET รายการ (หน้า admin) ก็ต้องมีสิทธิ์ — ไม่ใช่เปิดให้ทุกคนที่ล็อกอิน"""
    world = announcement_world
    assert client.get("/api/announcements", headers=_auth(world, "student")).status_code == 403
    assert client.get("/api/announcements", headers=_auth(world, "council")).status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_priority", ["low", "URGENT", "", "critical"])
async def test_invalid_priority_rejected(client, db_pool, announcement_world, bad_priority):
    """priority นอกเหนือ normal/high/urgent → 422 (Literal)"""
    world = announcement_world
    res = _create(client, world, priority=bad_priority)
    assert res.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize("blank", ["", "   ", "\n\t "])
async def test_blank_message_rejected(client, db_pool, announcement_world, blank):
    """ข้อความว่าง/มีแต่ช่องว่าง → 422 (min_length=1 อย่างเดียวไม่พอ ต้อง strip ก่อน)"""
    world = announcement_world
    res = _create(client, world, message=blank)
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_message_too_long_rejected(client, db_pool, announcement_world):
    """ข้อความเกิน 1000 ตัว → 422"""
    world = announcement_world
    res = _create(client, world, message="ก" * 1001)
    assert res.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad_link",
    ["javascript:alert(1)", "JavaScript:alert(1)", "data:text/html,<script>x</script>",
     "ftp://example.com", "/relative-path"],
)
async def test_unsafe_link_scheme_rejected(client, db_pool, announcement_world, bad_link):
    """
    🛡️ ช่อง XSS: Landing Page ผูก `<a :href="a.link">` ตรง ๆ
    ⇒ ลิงก์ที่ไม่ใช่ http/https ต้องถูกปฏิเสธตั้งแต่ชั้น schema (ไม่ใช่แค่ "ไม่สวย")
    """
    world = announcement_world
    res = _create(client, world, link=bad_link)

    assert res.status_code == 422, f"{bad_link} ต้องถูกปฏิเสธ"
    async with db_pool.acquire() as conn:
        assert await conn.fetchval("SELECT COUNT(*) FROM announcements") == 0


@pytest.mark.asyncio
async def test_blank_link_becomes_null(client, db_pool, announcement_world):
    """ลิงก์ที่เป็นค่าว่าง → เก็บเป็น NULL (ไม่เก็บสตริงว่าง)"""
    world = announcement_world
    ann_id = _create(client, world, link="   ").json()["id"]

    async with db_pool.acquire() as conn:
        assert await conn.fetchval(
            "SELECT link FROM announcements WHERE id = $1", ann_id
        ) is None


@pytest.mark.asyncio
async def test_priority_check_constraint_still_guards_table(db_pool, announcement_world):
    """ต่อให้绕过 API ตรงไปที่ DB — CHECK constraint ต้องยังกัน priority ที่ผิดไว้"""
    with pytest.raises(asyncpg.exceptions.CheckViolationError):
        async with db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO announcements (message, priority) VALUES ($1, $2)", "x", "low"
            )


# === Section 5: migration 014 ===
@pytest.mark.asyncio
async def test_migration_014_backfills_permission_and_is_idempotent(db_pool):
    """
    🔑 เทสต์ migration 014 บน DB "เก่า" — หัวใจของงานนี้

    บริบท: `students.permissions` เป็น snapshot ที่ไม่มีกลไก sync จาก roles.json
    ⇒ ถ้า migration นี้ไม่ทำงาน ผู้ใช้สภานักเรียนที่มีอยู่แล้วจะ "ไม่เห็นเมนู"
      โดยไม่มี error ให้ตามหาเลย

    จำลอง DB เก่า = ถอดคอลัมน์ใหม่ออก + ใส่ students ที่ permissions ยังไม่มี
    MANAGE_ANNOUNCEMENTS แล้วรัน upgrade() ตรง ๆ (แบบเดียวกับ test_audit_logs_migration)
    """
    migration = importlib.import_module("migrations.014_announcement_management")

    async with db_pool.acquire() as conn:
        # --- จำลองสคีมาก่อน migration -------------------------------------------
        await conn.execute("ALTER TABLE announcements DROP COLUMN IF EXISTS created_by")
        await conn.execute("ALTER TABLE announcements DROP COLUMN IF EXISTS updated_by")

        room_id = await conn.fetchval(
            "INSERT INTO rooms (room_code, room_name, level) VALUES ($1,$2,'ม.6') RETURNING id",
            f"ม.6/{random.randint(1, 90)}", "ห้องทดสอบ migration",
        )

        # ผู้ใช้เดิม: permissions ยังเป็นชุดเก่า (ไม่มี MANAGE_ANNOUNCEMENTS)
        old_perms = '["SUBMIT_ISSUE", "VIEW_OWN_ISSUES", "VIEW_DASHBOARD"]'
        council_uid = await conn.fetchval(
            "INSERT INTO users (username, password_hash, full_name) VALUES ($1,'x','สภาทดสอบ') RETURNING id",
            f"council_{random.randint(10000, 99999)}",
        )
        council_sid = await conn.fetchval(
            """
            INSERT INTO students (room_id, user_id, student_id, class_role, permissions)
            VALUES ($1, $2, $3, 'council_member', $4::jsonb) RETURNING id
            """,
            room_id, council_uid, f"MG{random.randint(1000, 9999)}", old_perms,
        )
        # แถวที่ permissions เป็น NULL — ต้องไม่ถูกข้าม (COALESCE ทุกจุด)
        null_uid = await conn.fetchval(
            "INSERT INTO users (username, password_hash, full_name) VALUES ($1,'x','สภา NULL') RETURNING id",
            f"council_null_{random.randint(10000, 99999)}",
        )
        null_sid = await conn.fetchval(
            """
            INSERT INTO students (room_id, user_id, student_id, class_role, permissions)
            VALUES ($1, $2, $3, 'council_member', NULL) RETURNING id
            """,
            room_id, null_uid, f"MG{random.randint(1000, 9999)}",
        )
        # แถวที่ถูกลบไปแล้ว — ต้องไม่ถูกเติมสิทธิ์
        del_uid = await conn.fetchval(
            "INSERT INTO users (username, password_hash, full_name) VALUES ($1,'x','สภาที่ถูกลบ') RETURNING id",
            f"council_del_{random.randint(10000, 99999)}",
        )
        del_sid = await conn.fetchval(
            """
            INSERT INTO students (room_id, user_id, student_id, class_role, permissions, deleted_at)
            VALUES ($1, $2, $3, 'council_member', $4::jsonb, NOW()) RETURNING id
            """,
            room_id, del_uid, f"MG{random.randint(1000, 9999)}", old_perms,
        )
        # นักเรียนทั่วไป — ต้องไม่ถูกเติมสิทธิ์
        stu_uid = await conn.fetchval(
            "INSERT INTO users (username, password_hash, full_name) VALUES ($1,'x','นักเรียน') RETURNING id",
            f"student_{random.randint(10000, 99999)}",
        )
        stu_sid = await conn.fetchval(
            """
            INSERT INTO students (room_id, user_id, student_id, class_role, permissions)
            VALUES ($1, $2, $3, 'student', '["SUBMIT_ISSUE"]'::jsonb) RETURNING id
            """,
            room_id, stu_uid, f"MG{random.randint(1000, 9999)}",
        )

        # --- รัน migration 014 ตรง ๆ บน DB เก่านี้ ---------------------------------
        await migration.upgrade(conn)

        # 1) คอลัมน์ใหม่ถูกเพิ่มกลับมา
        cols = await conn.fetch(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'announcements' AND column_name IN ('created_by', 'updated_by')
            """
        )
        assert {c["column_name"] for c in cols} == {"created_by", "updated_by"}

        # 2) สภานักเรียนได้สิทธิ์ (กรณี permissions มีค่าเดิมอยู่)
        perms = json.loads(
            await conn.fetchval("SELECT permissions FROM students WHERE id = $1", council_sid)
        )
        assert "MANAGE_ANNOUNCEMENTS" in perms
        assert "SUBMIT_ISSUE" in perms, "สิทธิ์เดิมต้องไม่หายไป"

        # 3) แถวที่ permissions เป็น NULL ก็ต้องได้สิทธิ์ (ไม่ถูกข้ามเงียบ ๆ)
        null_perms = json.loads(
            await conn.fetchval("SELECT permissions FROM students WHERE id = $1", null_sid)
        )
        assert "MANAGE_ANNOUNCEMENTS" in null_perms

        # 4) แถวที่ถูกลบแล้ว และนักเรียนทั่วไป ต้องไม่ถูกแตะ
        del_perms = json.loads(
            await conn.fetchval("SELECT permissions FROM students WHERE id = $1", del_sid)
        )
        assert "MANAGE_ANNOUNCEMENTS" not in del_perms, "แถวที่ถูกลบแล้วต้องไม่ถูกเติมสิทธิ์"
        stu_perms = json.loads(
            await conn.fetchval("SELECT permissions FROM students WHERE id = $1", stu_sid)
        )
        assert "MANAGE_ANNOUNCEMENTS" not in stu_perms, "นักเรียนทั่วไปต้องไม่ถูกเติมสิทธิ์"

        # 5) รันซ้ำต้องไม่ทำให้สิทธิ์ซ้ำ (idempotent)
        await migration.upgrade(conn)
        perms_again = json.loads(
            await conn.fetchval("SELECT permissions FROM students WHERE id = $1", council_sid)
        )
        assert perms_again.count("MANAGE_ANNOUNCEMENTS") == 1, "รัน migration ซ้ำต้องไม่เติมสิทธิ์ซ้ำ"
