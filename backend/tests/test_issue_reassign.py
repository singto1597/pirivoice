"""🔁 มอบหมายเรื่องค้างต่อ หลังผู้รับหมดวาระ (P5 · ข้อตัดสินใจ #4)

สถานการณ์จริง: ขึ้นปีใหม่แล้ว `council_member` ถูกยกเป็น `student` / ประธานสภาหมดวาระ
⇒ เรื่องที่ยัง `pending/in_progress/escalated` มี `current_assignee_id` ชี้คนที่ **ไม่มีแถว
active ในปีนี้** และ `accept_issue` ช่วยไม่ได้ (ปฏิเสธเมื่อมี assignee อยู่แล้ว)
⇒ ต้องมีเครื่องมือ "หาเรื่องที่กำพร้า + มอบหมายให้ผู้รับใหม่"

ทดสอบ 5 ระดับ:
  1) **ตรวจจับ** — เรื่องที่ผู้รับหมดวาระโผล่ / เรื่องที่ผู้รับยัง active ไม่โผล่
  2) **ผู้รับที่แนะนำ** — ผู้ดำรงตำแหน่งเดียวกันในห้องนั้นในปีนี้ (ไม่ใช่คนที่หมดวาระ)
  3) **มอบหมาย** — แถว `issues` เปลี่ยนจริง + `issue_status_history` + notifications + audit
  4) **ปฏิเสธ** — ผู้รับใหม่ไม่มีแถว active (400) · เรื่องปิดแล้ว (400) · ไม่มีเรื่อง (404)
  5) **ประตูสิทธิ์** — นักเรียน 403 · ประธานระดับ (มี MANAGE_STUDENTS แต่ไม่ใช่ระดับโรงเรียน) 403

ตาม docs/rules/testing.md: ตรวจ DB ตรง ๆ ผ่าน `db_pool` ไม่เชื่อ HTTP response
"""
import random

import pytest
import pytest_asyncio

from services import auth_service, year_service

_ROOMS = [("ม.1/1", "ม.1"), ("ม.2/1", "ม.2")]


@pytest_asyncio.fixture
async def orphan_world(db_pool, client):
    """โลกจำลอง "หลังขึ้นปีใหม่": หัวหน้าห้อง ม.1/1 คนเก่าหมดวาระ · คนใหม่ active

    ⚠️ รับ `client` เพื่อให้ app เปิด (init_db) ก่อนใช้ตาราง
    """
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM students")
        rooms = {}
        for code, level in _ROOMS:
            rooms[code] = await conn.fetchval(
                "INSERT INTO rooms (room_code, room_name, level) VALUES ($1,$2,$3) RETURNING id",
                code, code, level,
            )

    users = {}

    async def make(username, role, room, no):
        sid = f"OR{random.randint(100000, 999999)}"
        uid = await auth_service.register_user(
            db_pool, username, "1234", f"{role} {username}", sid, room, no, role
        )
        users[username] = {"user_id": uid, "token": auth_service.create_access_token(uid)}
        return uid

    await make("or_admin", "admin", "", 0)
    await make("or_teacher", "teacher", "ม.1/1", 0)
    await make("or_level", "level_president", "ม.1/1", 1)   # MANAGE_STUDENTS แต่ mode='level'
    await make("or_old", "class_president", "ม.1/1", 2)     # ผู้รับเดิม — จะถูก flip
    await make("or_new", "class_president", "ม.1/1", 3)     # ผู้รับที่ควรแนะนำ
    await make("or_reporter", "student", "ม.1/1", 4)
    await make("or_other", "student", "ม.2/1", 5)

    async with db_pool.acquire() as conn:
        current = await year_service.fetch_current_year(conn)
        assert current is not None

        # 🔻 จำลองผลของ rollover: ผู้รับเดิมไม่มีแถว active ในปีปัจจุบันแล้ว
        await conn.execute(
            "UPDATE students SET status = 'promoted' WHERE user_id = $1",
            users["or_old"]["user_id"],
        )

        async def issue(assignee: str, status: str, room_code: str = "ม.1/1") -> int:
            return await conn.fetchval(
                """INSERT INTO issues
                       (room_id, main_category, category, title, description,
                        reporter_id, current_level, current_assignee_id,
                        current_assignee_role, status)
                   VALUES ($1,'suggestion','academic',$2,'รายละเอียด',
                           $3,'room',$4,'class_president',$5)
                   RETURNING id""",
                rooms[room_code], f"เรื่องของ {assignee} ({status})",
                users["or_reporter"]["user_id"], users[assignee]["user_id"], status,
            )

        # กำพร้า (ผู้รับหมดวาระ) — 3 สถานะเปิด
        orphan_ids = [
            await issue("or_old", "pending"),
            await issue("or_old", "in_progress"),
            await issue("or_old", "escalated"),
        ]
        # ไม่กำพร้า (ผู้รับยัง active) — ต้องไม่โผล่ในรายการ
        healthy_id = await issue("or_new", "in_progress")
        # ปิดแล้ว (แม้ผู้รับหมดวาระ) — ไม่ใช่ "เรื่องค้าง"
        closed_id = await issue("or_old", "resolved")

    return {
        "_client": client,
        "rooms": rooms,
        "users": users,
        "year_id": current["id"],
        "orphan_ids": orphan_ids,
        "healthy_id": healthy_id,
        "closed_id": closed_id,
    }


def _hdr(world, who="or_admin") -> dict:
    return {"Authorization": f"Bearer {world['users'][who]['token']}"}


async def _get(client, path, headers):
    return client.get(path, headers=headers)


async def _post(client, path, headers, body):
    return client.post(path, json=body, headers=headers)


# ============================================================
# 1) + 2) ตรวจจับ และผู้รับที่แนะนำ
# ============================================================
@pytest.mark.asyncio
async def test_lists_only_issues_whose_assignee_lapsed(orphan_world):
    w = orphan_world
    resp = await _get(client_of(w), "/api/issues/orphaned-assignments", _hdr(w))
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["year_id"] == w["year_id"]
    got = {i["id"] for i in body["items"]}
    assert got == set(w["orphan_ids"]), "ต้องเห็นเฉพาะเรื่องที่ผู้รับไม่มีแถว active ในปีนี้"
    assert w["healthy_id"] not in got, "ผู้รับยัง active → ไม่ใช่เรื่องกำพร้า"
    assert w["closed_id"] not in got, "เรื่องที่ปิดแล้วไม่ใช่เรื่องค้าง"
    assert body["total"] == 3

    for item in body["items"]:
        assert item["assignee_id"] == w["users"]["or_old"]["user_id"]
        assert item["assignee_role"] == "class_president"
        # ประวัติห้องเดิมของผู้รับ (ให้เจ้าหน้าที่เห็นว่าหมดวาระจากห้องไหน)
        assert item["assignee_old_room_code"] == "ม.1/1"

        # ผู้รับที่แนะนำ = หัวหน้าห้อง ม.1/1 ของปีนี้ — ต้องไม่ใช่คนเดิม
        candidate_ids = {c["user_id"] for c in item["candidates"]}
        assert w["users"]["or_new"]["user_id"] in candidate_ids
        assert w["users"]["or_old"]["user_id"] not in candidate_ids, "คนหมดวาระต้องไม่ถูกแนะนำ"


# ============================================================
# 3) มอบหมายต่อ — deep DB + trace ครบ
# ============================================================
@pytest.mark.asyncio
async def test_reassign_moves_issue_and_writes_full_trail(orphan_world, db_pool):
    w = orphan_world
    issue_id = w["orphan_ids"][0]
    new_uid = w["users"]["or_new"]["user_id"]

    resp = await _post(
        client_of(w), f"/api/issues/{issue_id}/reassign", _hdr(w),
        {"to_user_id": new_uid, "note": "ยกเลิกตำแหน่งเดิมหลังขึ้นปี"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["to_user_id"] == new_uid

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT current_assignee_id, current_assignee_role, status FROM issues WHERE id = $1",
            issue_id,
        )
        assert row["current_assignee_id"] == new_uid
        assert row["current_assignee_role"] == "class_president"   # ตำแหน่งจริงของแถวปีนี้
        assert row["status"] == "in_progress"

        hist = await conn.fetch(
            "SELECT status, changed_by, note FROM issue_status_history WHERE issue_id = $1 ORDER BY id",
            issue_id,
        )
        assert len(hist) == 1
        assert hist[0]["status"] == "in_progress"
        assert hist[0]["changed_by"] == w["users"]["or_admin"]["user_id"]
        assert hist[0]["note"] == "ยกเลิกตำแหน่งเดิมหลังขึ้นปี"

        notes = await conn.fetch(
            """SELECT user_id, group_type FROM notifications
               WHERE entity_type = 'issue' AND entity_id = $1 ORDER BY id""",
            issue_id,
        )
        assert (new_uid, "issue_received") in [(n["user_id"], n["group_type"]) for n in notes]
        assert (
            w["users"]["or_reporter"]["user_id"], "issue_mine"
        ) in [(n["user_id"], n["group_type"]) for n in notes]

        audit = await conn.fetchrow(
            """SELECT old_values, new_values FROM audit_logs
               WHERE action = 'REASSIGN_ISSUE' AND entity_id = $1::text""",
            str(issue_id),
        )
        assert audit is not None


# ============================================================
# 4) ปฏิเสธ
# ============================================================
@pytest.mark.asyncio
async def test_reassign_rejects_assignee_without_active_row(orphan_world):
    w = orphan_world
    resp = await _post(
        client_of(w), f"/api/issues/{w['orphan_ids'][0]}/reassign", _hdr(w),
        {"to_user_id": w["users"]["or_old"]["user_id"]},
    )
    assert resp.status_code == 400, resp.text
    assert "สมาชิกภาพ" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_reassign_rejects_closed_issue(orphan_world, db_pool):
    w = orphan_world
    resp = await _post(
        client_of(w), f"/api/issues/{w['closed_id']}/reassign", _hdr(w),
        {"to_user_id": w["users"]["or_new"]["user_id"]},
    )
    assert resp.status_code == 400, resp.text

    async with db_pool.acquire() as conn:
        assert await conn.fetchval(
            "SELECT current_assignee_id FROM issues WHERE id = $1", w["closed_id"]
        ) == w["users"]["or_old"]["user_id"], "เรื่องปิดแล้วต้องไม่ถูกแตะ"


@pytest.mark.asyncio
async def test_reassign_returns_404_for_unknown_issue(orphan_world):
    w = orphan_world
    resp = await _post(
        client_of(w), "/api/issues/999999999/reassign", _hdr(w),
        {"to_user_id": w["users"]["or_new"]["user_id"]},
    )
    assert resp.status_code == 404, resp.text


# ============================================================
# 5) ประตูสิทธิ์ — สองด่าน: permission + mode
# ============================================================
@pytest.mark.asyncio
async def test_orphan_tools_require_school_scope(orphan_world):
    w = orphan_world
    c = client_of(w)

    # นักเรียน — ไม่มี MANAGE_STUDENTS
    assert (await _get(c, "/api/issues/orphaned-assignments", _hdr(w, "or_other"))).status_code == 403

    # ประธานระดับ — **มี** MANAGE_STUDENTS แต่ mode='level' ⇒ ยัง 403 (ด่านที่สองทำงาน)
    assert (await _get(c, "/api/issues/orphaned-assignments", _hdr(w, "or_level"))).status_code == 403

    # ครูทั่วไป — ไม่มีสิทธิ์จัดการนักเรียน
    assert (await _get(c, "/api/issues/orphaned-assignments", _hdr(w, "or_teacher"))).status_code == 403

    # และ reassign ก็ประตูเดียวกัน
    resp = await _post(
        c, f"/api/issues/{w['orphan_ids'][0]}/reassign", _hdr(w, "or_level"),
        {"to_user_id": w["users"]["or_new"]["user_id"]},
    )
    assert resp.status_code == 403, resp.text


# ============================================================
# helpers
# ============================================================
def client_of(world):
    return world["_client"]
