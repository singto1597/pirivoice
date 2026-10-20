"""🔀 ย้ายห้อง + แก้ข้อมูลที่กรอกผิด + ประวัติรายคน (P5 · migration 029)

ทดสอบ 6 ระดับ:
  1) **ย้ายกลุ่ม** — UPDATE ห้องจริง + เขียน `student_moves` + audit ใน transaction เดียว
  2) **ไม่สร้างแถว active ซ้อน** — กรณีห้องปลายทางมีแถวของคนนี้อยู่แล้ว (unique index 028)
  3) **ขอบเขต** — ย้ายได้เฉพาะปีปัจจุบัน และครู/ประธานระดับได้เฉพาะระดับของตัวเอง
  4) **PATCH ข้อมูลตัวตน** — แก้ชื่อ/เลขที่/รหัสได้ แต่ **ไม่แตะ `users.username`**
  5) **validate** — รหัสซ้ำในห้องเดียวกัน 400 · status นอกรายการ 422 (Literal)
  6) **ประวัติ** — timeline เห็นทั้งแถวปีและรายการย้าย

ตาม docs/rules/testing.md: ตรวจ DB ตรง ๆ ผ่าน `db_pool` ไม่เชื่อ HTTP response
"""
import random

import pytest
import pytest_asyncio

from services import auth_service

_ROOMS = [
    ("ม.1/1", "ม.1"),
    ("ม.1/2", "ม.1"),
    ("ม.2/1", "ม.2"),
]


@pytest_asyncio.fixture
async def move_world(db_pool, client):
    """3 ห้อง · admin (ไม่ผูกห้อง) · ครู ม.1 · นักเรียน 4 คน

    ⚠️ รับ `client` เพื่อบังคับให้ app เปิด (init_db + migration 029) ก่อนใช้ตาราง
    ⚠️ ลบ `students` ที่ `seed_default_users()` ปลูกไว้ — ไม่งั้นจำนวนแถวเพี้ยน
    """
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM students")
        rooms = {}
        for code, level in _ROOMS:
            rooms[code] = await conn.fetchval(
                "INSERT INTO rooms (room_code, room_name, level) VALUES ($1,$2,$3) RETURNING id",
                code, code, level,
            )

    def sid() -> str:
        return f"MV{random.randint(100000, 999999)}"

    users = {}

    async def make(username, role, room, no):
        uid = await auth_service.register_user(
            db_pool, username, "1234", f"{role} {username}", sid(), room, no, role
        )
        users[username] = {"user_id": uid, "token": auth_service.create_access_token(uid)}
        return uid

    await make("mv_admin", "admin", "", 0)
    await make("mv_teacher", "teacher", "ม.1/1", 0)
    await make("mv_s1", "student", "ม.1/1", 1)
    await make("mv_s2", "student", "ม.1/1", 2)
    await make("mv_s3", "student", "ม.1/2", 3)
    await make("mv_s4", "student", "ม.2/1", 4)

    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, user_id, student_id FROM students WHERE deleted_at IS NULL ORDER BY id"
        )
        current_year = await conn.fetchval(
            "SELECT id FROM academic_years WHERE is_current AND deleted_at IS NULL"
        )

    by_user = {r["user_id"]: dict(r) for r in rows}
    return {
        "_client": client,
        "rooms": rooms,
        "users": users,
        "rows": {u: by_user[v["user_id"]] for u, v in users.items()},
        "year_id": current_year,
    }


def _hdr(world, who="mv_admin") -> dict:
    return {"Authorization": f"Bearer {world['users'][who]['token']}"}


async def _room_of(db_pool, student_row_id: int):
    async with db_pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT room_id FROM students WHERE id = $1", student_row_id
        )


# ============================================================
# 1) ย้ายกลุ่ม
# ============================================================
@pytest.mark.asyncio
async def test_bulk_move_updates_room_and_writes_history(move_world, db_pool):
    w = move_world
    ids = [w["rows"]["mv_s1"]["id"], w["rows"]["mv_s2"]["id"]]

    resp = await _post(client_of(w), "/api/students/bulk-move", _hdr(w), {
        "student_ids": ids, "to_room_code": "ม.1/2", "note": "สลับห้องตามคำสั่งโรงเรียน",
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["moved"]) == 2

    target = w["rooms"]["ม.1/2"]
    for sid in ids:
        assert await _room_of(db_pool, sid) == target

    async with db_pool.acquire() as conn:
        moves = await conn.fetch(
            "SELECT * FROM student_moves ORDER BY id"
        )
        assert len(moves) == 2
        assert {m["student_id"] for m in moves} == {
            w["rows"]["mv_s1"]["student_id"], w["rows"]["mv_s2"]["student_id"]
        }
        assert all(m["from_room_id"] == w["rooms"]["ม.1/1"] for m in moves)
        assert all(m["to_room_id"] == target for m in moves)
        assert all(m["academic_year_id"] == w["year_id"] for m in moves)
        assert all(m["note"] == "สลับห้องตามคำสั่งโรงเรียน" for m in moves)

        audit = await conn.fetchval(
            "SELECT COUNT(*) FROM audit_logs WHERE action = 'MOVE_STUDENTS'"
        )
        assert audit == 1


@pytest.mark.asyncio
async def test_bulk_move_skips_students_already_in_target(move_world, db_pool):
    w = move_world
    resp = await _post(client_of(w), "/api/students/bulk-move", _hdr(w), {
        "student_ids": [w["rows"]["mv_s3"]["id"]], "to_room_code": "ม.1/2",
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["moved"] == []
    assert len(body["skipped"]) == 1

    async with db_pool.acquire() as conn:
        assert await conn.fetchval("SELECT COUNT(*) FROM student_moves") == 0


@pytest.mark.asyncio
async def test_bulk_move_rejects_previous_year_rows(move_world, db_pool):
    w = move_world
    async with db_pool.acquire() as conn:
        old_year = await conn.fetchval(
            "INSERT INTO academic_years (year_be, name) VALUES (2500, 'ปีเก่า') RETURNING id"
        )
        old_row = await conn.fetchval(
            """INSERT INTO students (user_id, room_id, academic_year_id, student_id,
                                     student_no, class_role, permissions, responsibilities)
               VALUES ($1,$2,$3,'OLD1',1,'student','[]'::jsonb,'[]'::jsonb) RETURNING id""",
            w["users"]["mv_s1"]["user_id"], w["rooms"]["ม.1/1"], old_year,
        )

    resp = await _post(client_of(w), "/api/students/bulk-move", _hdr(w), {
        "student_ids": [old_row], "to_room_code": "ม.1/2",
    })
    assert resp.status_code == 400, resp.text
    # ไม่มีอะไรถูกแก้
    assert await _room_of(db_pool, old_row) == w["rooms"]["ม.1/1"]


# ============================================================
# 2) ไม่สร้างแถว active ซ้อน
# ============================================================
@pytest.mark.asyncio
async def test_bulk_move_supersedes_when_target_already_has_row(move_world, db_pool):
    """ห้องปลายทางมีแถวของคนนี้อยู่แล้ว → แถวนั้นชนะ แถวที่เลือกมาถูก superseded

    นี่คือเส้นทางที่ถ้าไม่จัดการจะชน `uq_students_room_year_student` (index 028)
    """
    w = move_world
    async with db_pool.acquire() as conn:
        dup_row = await conn.fetchval(
            """INSERT INTO students (user_id, room_id, academic_year_id, student_id,
                                     student_no, class_role, permissions, responsibilities)
               VALUES ($1,$2,$3,$4,9,'student','[]'::jsonb,'[]'::jsonb) RETURNING id""",
            w["users"]["mv_s1"]["user_id"], w["rooms"]["ม.1/2"], w["year_id"],
            w["rows"]["mv_s1"]["student_id"],
        )

    resp = await _post(client_of(w), "/api/students/bulk-move", _hdr(w), {
        "student_ids": [w["rows"]["mv_s1"]["id"]], "to_room_code": "ม.1/2",
    })
    assert resp.status_code == 200, resp.text

    async with db_pool.acquire() as conn:
        active = await conn.fetch(
            """SELECT id FROM students
               WHERE user_id = $1 AND academic_year_id = $2
                 AND deleted_at IS NULL AND status = 'active'""",
            w["users"]["mv_s1"]["user_id"], w["year_id"],
        )
        assert [r["id"] for r in active] == [dup_row], "ต้องเหลือ active แถวเดียว = แถวปลายทาง"
        assert await conn.fetchval(
            "SELECT status FROM students WHERE id = $1", w["rows"]["mv_s1"]["id"]
        ) == "superseded"
        # ประวัติการย้ายยังถูกบันทึก
        assert await conn.fetchval("SELECT COUNT(*) FROM student_moves") == 1


# ============================================================
# 3) ขอบเขตสิทธิ์
# ============================================================
@pytest.mark.asyncio
async def test_teacher_moves_only_within_their_grade(move_world):
    w = move_world
    c = client_of(w)

    ok = await _post(c, "/api/students/bulk-move", _hdr(w, "mv_teacher"), {
        "student_ids": [w["rows"]["mv_s1"]["id"]], "to_room_code": "ม.1/2",
    })
    assert ok.status_code == 200, ok.text

    other_grade = await _post(c, "/api/students/bulk-move", _hdr(w, "mv_teacher"), {
        "student_ids": [w["rows"]["mv_s4"]["id"]], "to_room_code": "ม.1/2",
    })
    assert other_grade.status_code == 400, other_grade.text

    other_target = await _post(c, "/api/students/bulk-move", _hdr(w, "mv_teacher"), {
        "student_ids": [w["rows"]["mv_s2"]["id"]], "to_room_code": "ม.2/1",
    })
    assert other_target.status_code == 400, other_target.text


@pytest.mark.asyncio
async def test_bulk_move_requires_manage_students(move_world):
    w = move_world
    resp = await _post(client_of(w), "/api/students/bulk-move", _hdr(w, "mv_s1"), {
        "student_ids": [w["rows"]["mv_s2"]["id"]], "to_room_code": "ม.1/2",
    })
    assert resp.status_code == 403, resp.text


# ============================================================
# 4) PATCH ข้อมูลตัวตน
# ============================================================
@pytest.mark.asyncio
async def test_patch_identity_keeps_users_username(move_world, db_pool):
    w = move_world
    row = w["rows"]["mv_s1"]

    resp = client_of(w).patch(
        f"/api/students/{row['id']}",
        json={
            "prefix": "นาย", "first_name": "สมชาย", "last_name": "ใจดี",
            "nickname": "ชาย", "student_no": 7, "student_id": "NEWCODE1",
        },
        headers=_hdr(w),
    )
    assert resp.status_code == 200, resp.text

    async with db_pool.acquire() as conn:
        got = await conn.fetchrow(
            "SELECT prefix, first_name, last_name, nickname, student_no, student_id FROM students WHERE id = $1",
            row["id"],
        )
        assert dict(got) == {
            "prefix": "นาย", "first_name": "สมชาย", "last_name": "ใจดี",
            "nickname": "ชาย", "student_no": 7, "student_id": "NEWCODE1",
        }
        # 🔴 username ต้องไม่ถูกแตะ — เป็นกุญแจล็อกอิน ไม่ใช่ข้อมูลสมาชิก
        assert await conn.fetchval(
            "SELECT username FROM users WHERE id = $1", w["users"]["mv_s1"]["user_id"]
        ) == "mv_s1"


@pytest.mark.asyncio
async def test_patch_rejects_duplicate_student_code_in_same_room(move_world):
    w = move_world
    # mv_s2 → ใช้รหัสเดียวกับ mv_s1 (ห้องเดียวกัน ปีเดียวกัน)
    resp = client_of(w).patch(
        f"/api/students/{w['rows']['mv_s2']['id']}",
        json={"student_id": w["rows"]["mv_s1"]["student_id"]},
        headers=_hdr(w),
    )
    assert resp.status_code == 400, resp.text


@pytest.mark.asyncio
async def test_patch_rejects_unknown_status(move_world):
    w = move_world
    resp = client_of(w).patch(
        f"/api/students/{w['rows']['mv_s1']['id']}",
        json={"status": "Activ"},
        headers=_hdr(w),
    )
    # Literal ของ Pydantic → 422 ก่อนถึง service (เดิมเป็น free text ที่หลุดเงียบ ๆ)
    assert resp.status_code == 422, resp.text


# ============================================================
# 5) ประวัติ
# ============================================================
@pytest.mark.asyncio
async def test_history_returns_years_and_moves(move_world):
    w = move_world
    c = client_of(w)
    row = w["rows"]["mv_s1"]["id"]

    await _post(c, "/api/students/bulk-move", _hdr(w), {
        "student_ids": [row], "to_room_code": "ม.1/2", "note": "ย้ายทดสอบ",
    })

    resp = c.get(f"/api/students/{row}/history", headers=_hdr(w))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["user_id"] == w["users"]["mv_s1"]["user_id"]
    assert len(body["years"]) == 1
    assert body["years"][0]["room_code"] == "ม.1/2"
    assert len(body["moves"]) == 1
    assert body["moves"][0]["from_room_code"] == "ม.1/1"
    assert body["moves"][0]["to_room_code"] == "ม.1/2"
    assert body["moves"][0]["note"] == "ย้ายทดสอบ"


# ============================================================
# helpers
# ============================================================
# ⚠️ `client` ของ conftest เป็น TestClient แบบ sync (httpx) — เก็บ reference ไว้ใน world
#    แล้วห่อด้วย `async def` เพื่อให้เทสต์เรียกด้วย `await` ได้เหมือน service อื่น
def client_of(world):
    return world["_client"]


async def _post(client, path: str, headers: dict, body: dict):
    return client.post(path, json=body, headers=headers)
