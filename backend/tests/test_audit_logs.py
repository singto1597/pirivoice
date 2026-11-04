# === Audit Logs Tests: เก็บทุก action (login / create / accept / escalate / resolve / cancel / reject / read) + API ดู ===
import json
import random
from datetime import datetime, timezone

import pytest
import pytest_asyncio

from services import auth_service


@pytest_asyncio.fixture
async def audit_world(db_pool):
    """สร้าง room + users: student (ผู้แจ้ง), head (หัวหน้าห้อง), admin"""
    room_code = f"ม.4/{random.randint(1, 90)}"
    async with db_pool.acquire() as conn:
        room_id = await conn.fetchval(
            "INSERT INTO rooms (room_code, room_name, level) VALUES ($1,$2,'ม.4') RETURNING id",
            room_code, room_code
        )

    users = {}
    for label, role in [("student", "student"), ("head", "class_president"), ("admin", "admin")]:
        sid = f"AU{random.randint(1000, 9999)}{label[:2]}"
        uid = await auth_service.register_user(
            db_pool, sid, "1234", f"{label} ทดสอบ", sid, room_code, 1, role
        )
        users[label] = {
            "user_id": uid,
            "username": sid,
            "token": auth_service.create_access_token(uid),
            "room_id": room_id,
        }
    return users


def _create_issue(client, users, *, title="เรื่องทดสอบ", desc="รายละเอียด", token=None):
    return client.post("/api/issues", json={
        "main_category": "suggestion", "category": "academic", "title": title,
        "description": desc, "is_anonymous": False,
        "room_id": users["student"]["room_id"],
    }, headers={"Authorization": f"Bearer {token or users['student']['token']}"})


# === Section 1: login (success + failure) ===
@pytest.mark.asyncio
async def test_login_audit_success_and_failure(client, db_pool, audit_world):
    """login สำเร็จ → status='success'; ผิดรหัส/ไม่เจอชื่อ → status='error' (deep-DB verify)"""
    world = audit_world
    sid = world["student"]["username"]

    # login สำเร็จ
    res = client.post("/api/auth/login", json={"username": sid, "password": "1234"})
    assert res.status_code == 200

    # login ผิดรหัส (รู้ user)
    res = client.post("/api/auth/login", json={"username": sid, "password": "wrong"})
    assert res.status_code == 401

    # login ไม่เจอชื่อ (ไม่มี user)
    res = client.post("/api/auth/login", json={"username": f"{sid}NO", "password": "1234"})
    assert res.status_code == 401

    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT status, error_detail, user_id, actor_identifier FROM audit_logs WHERE action = 'login' ORDER BY created_at"
        )
    assert len(rows) == 3, f"ต้องมี 3 rows แต่ได้ {len(rows)}"
    assert rows[0]["status"] == "success"
    assert rows[0]["user_id"] == world["student"]["user_id"]
    assert rows[1]["status"] == "error"
    assert rows[1]["user_id"] == world["student"]["user_id"], "รหัสผิด → รู้ user"
    assert rows[1]["error_detail"] is not None
    assert rows[2]["status"] == "error"
    assert rows[2]["user_id"] == -1, "ไม่เจอชื่อ → ไม่รู้ user (sentinel -1 ไม่ปล่อยว่าง)"
    assert rows[2]["actor_identifier"] == f"{sid}NO"


# === Section 2: issue mutations ===
@pytest.mark.asyncio
async def test_issue_mutation_audits(client, db_pool, audit_world):
    """create / accept / step / resolve → มี audit ถูก action (deep-DB verify)"""
    world = audit_world
    res = _create_issue(client, world, title="เสียงดังรบกวน")
    assert res.status_code == 200
    issue_id = res.json()["id"]

    # accept (หัวหน้าห้อง)
    res = client.post(f"/api/issues/{issue_id}/accept", json={"estimated_days": 2},
                      headers={"Authorization": f"Bearer {world['head']['token']}"})
    assert res.status_code == 200

    # เพิ่มขั้นตอน + ทำสำเร็จ
    res = client.post(f"/api/issues/{issue_id}/steps", json={"step_title": "ตรวจสอบ"},
                      headers={"Authorization": f"Bearer {world['head']['token']}"})
    assert res.status_code == 200
    step_id = res.json()["id"]
    res = client.patch(f"/api/issues/{issue_id}/steps/{step_id}/complete",
                       headers={"Authorization": f"Bearer {world['head']['token']}"})
    assert res.status_code == 200

    # ยืดเวลา countdown (ต้องได้ audit UPDATE_COUNTDOWN ด้วย)
    res = client.patch(f"/api/issues/{issue_id}/countdown", json={"estimated_days": 5},
                       headers={"Authorization": f"Bearer {world['head']['token']}"})
    assert res.status_code == 200

    # resolve
    res = client.post(f"/api/issues/{issue_id}/resolve", json={"reason": "เสร็จแล้ว"},
                      headers={"Authorization": f"Bearer {world['head']['token']}"})
    assert res.status_code == 200

    async with db_pool.acquire() as conn:
        issue_actions = [r["action"] for r in await conn.fetch(
            "SELECT action FROM audit_logs WHERE entity_type = 'issue' AND entity_id = $1 ORDER BY created_at",
            str(issue_id)
        )]
        step_actions = [r["action"] for r in await conn.fetch(
            "SELECT action FROM audit_logs WHERE entity_type = 'issue_step' ORDER BY created_at"
        )]

    assert issue_actions[0] == "CREATE_ISSUE"
    assert "ACCEPT_ISSUE" in issue_actions
    assert "UPDATE_COUNTDOWN" in issue_actions
    assert "RESOLVE_ISSUE" in issue_actions
    assert "CREATE_STEP" in step_actions
    assert "UPDATE_STEP" in step_actions

    # CREATE_ISSUE ต้องเก็บ new_values (title/status) เป็น jsonb
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT new_values FROM audit_logs WHERE action = 'CREATE_ISSUE' AND entity_id = $1",
            str(issue_id)
        )
    nv = row["new_values"]
    if isinstance(nv, str):
        nv = json.loads(nv)  # asyncpg คืน jsonb เป็น string (บทเรียนเดิม)
    assert nv["title"] == "เสียงดังรบกวน"
    assert nv["status"] == "pending"


@pytest.mark.asyncio
async def test_cancel_reject_audit(client, db_pool, audit_world):
    """ผู้แจ้งยกเลิก → CANCEL_ISSUE; ผู้ดูแลปัดตก → REJECT_ISSUE"""
    world = audit_world

    # ผู้แจ้งยกเลิก
    res = _create_issue(client, world, title="ส่งผิด")
    issue_id = res.json()["id"]
    res = client.post(f"/api/issues/{issue_id}/cancel", json={"reason": "ส่งผิด"},
                      headers={"Authorization": f"Bearer {world['student']['token']}"})
    assert res.status_code == 200
    assert res.json()["status"] == "cancelled"

    # ผู้ดูแลปัดตก
    res = _create_issue(client, world, title="ไม่เข้าเงื่อนไข")
    issue2 = res.json()["id"]
    res = client.post(f"/api/issues/{issue2}/cancel", json={"reason": "ข้อมูลไม่ครบ"},
                      headers={"Authorization": f"Bearer {world['admin']['token']}"})
    assert res.status_code == 200
    assert res.json()["status"] == "rejected"

    async with db_pool.acquire() as conn:
        cancel_row = await conn.fetchrow(
            "SELECT action FROM audit_logs WHERE entity_type='issue' AND entity_id=$1 AND action='CANCEL_ISSUE'",
            str(issue_id)
        )
        reject_row = await conn.fetchrow(
            "SELECT action FROM audit_logs WHERE entity_type='issue' AND entity_id=$1 AND action='REJECT_ISSUE'",
            str(issue2)
        )
    assert cancel_row is not None, "ผู้แจ้งยกเลิกต้องได้ CANCEL_ISSUE"
    assert reject_row is not None, "ผู้ดูแลปัดตกต้องได้ REJECT_ISSUE"


@pytest.mark.asyncio
async def test_change_password_audit(client, db_pool, audit_world):
    """เปลี่ยนรหัสผ่าน → audit CHANGE_PASSWORD"""
    world = audit_world
    res = client.post("/api/auth/change-password",
                      json={"old_password": "1234", "new_password": "5678"},
                      headers={"Authorization": f"Bearer {world['student']['token']}"})
    assert res.status_code == 200

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT action FROM audit_logs WHERE action='CHANGE_PASSWORD' AND user_id=$1",
            world["student"]["user_id"]
        )
    assert row is not None


# === Section 3: read audits ===
@pytest.mark.asyncio
async def test_read_audits_logged(client, db_pool, audit_world):
    """GET /issues → READ_ISSUES; dashboard ที่ไม่มีสิทธิ์ (403) ต้องไม่ log"""
    world = audit_world

    res = client.get("/api/issues", headers={"Authorization": f"Bearer {world['student']['token']}"})
    assert res.status_code == 200

    # head ไม่มี VIEW_DASHBOARD → 403 → ต้องไม่ log READ_DASHBOARD
    res = client.get("/api/dashboard/summary", headers={"Authorization": f"Bearer {world['head']['token']}"})
    assert res.status_code == 403

    async with db_pool.acquire() as conn:
        read_issues = await conn.fetchval(
            "SELECT COUNT(*) FROM audit_logs WHERE action='READ_ISSUES' AND user_id=$1",
            world["student"]["user_id"]
        )
        read_dashboard = await conn.fetchval(
            "SELECT COUNT(*) FROM audit_logs WHERE action='READ_DASHBOARD'"
        )
    assert read_issues == 1
    assert read_dashboard == 0, "HEAD โดน 403 ต้องไม่ log READ_DASHBOARD"


# === Section 3.5: ความครบถ้วนของทุกคอลัมน์ (ห้ามเว้นว่าง) ===
@pytest.mark.asyncio
async def test_audit_logs_every_column_populated(client, db_pool, audit_world):
    """ทุก action (login สำเร็จ/ล้มเหลว / create / read) → audit row ต้องไม่มีคอลัมน์ใดว่าง

    deep-DB: อ่าน "รายชื่อคอลัมน์ที่ DB บังคับ NOT NULL" จาก information_schema แล้ว
    ไล่ยืนยันทีละคอลัมน์ — เทสต์จะตามสคีมาให้เองถ้าอนาคตมีคอลัมน์เพิ่ม
    """
    world = audit_world
    sid = world["student"]["username"]

    client.post("/api/auth/login", json={"username": sid, "password": "1234"})           # login สำเร็จ
    client.post("/api/auth/login", json={"username": f"{sid}NO", "password": "1234"})    # login หาชื่อไม่เจอ
    client.post("/api/auth/login", json={"username": sid, "password": "wrong"})          # login รหัสผิด
    res = _create_issue(client, world, title="เรื่องตรวจความครบถ้วน")
    assert res.status_code == 200
    issue_id = res.json()["id"]
    client.get("/api/issues", headers={"Authorization": f"Bearer {world['student']['token']}"})

    async with db_pool.acquire() as conn:
        not_null_cols = [
            r["column_name"] for r in await conn.fetch(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'audit_logs' AND is_nullable = 'NO'
                """
            )
        ]
        rows = await conn.fetch("SELECT * FROM audit_logs ORDER BY created_at")

    assert not_null_cols, "อ่านสคีมา audit_logs ไม่ได้"
    assert len(rows) >= 5, f"ต้องมีอย่างน้อย 5 audit rows แต่ได้ {len(rows)}"

    for row in rows:
        for col in not_null_cols:
            value = row[col]
            assert value is not None, f"{row['action']}: คอลัมน์ {col} เป็น NULL"
            if col in ("old_values", "new_values"):
                continue
            if isinstance(value, str):
                assert value.strip() != "", f"{row['action']}: คอลัมน์ {col} เป็นสตริงว่าง"

    def _json(value):
        """asyncpg คืน jsonb เป็น string (บทเรียนเดิม) — แปลงให้เป็น dict ก่อนเทียบ"""
        return json.loads(value) if isinstance(value, str) else value

    login_ok = next(r for r in rows if r["action"] == "login" and r["status"] == "success")
    login_unknown = next(r for r in rows if r["action"] == "login" and r["actor_identifier"].endswith("NO"))
    create_row = next(r for r in rows if r["action"] == "CREATE_ISSUE")
    read_row = next(r for r in rows if r["action"] == "READ_ISSUES")

    # user_id / room_id: login สำเร็จ → รู้ตัวตน + ห้องที่สังกัด (resolve จาก students ให้เอง)
    assert login_ok["user_id"] == world["student"]["user_id"]
    assert login_ok["room_id"] == world["student"]["room_id"], "ต้องเติม room_id ของผู้กระทำอัตโนมัติ"
    # login ที่หาชื่อไม่เจอ → ไม่รู้ตัวตน/ห้อง → sentinel -1 (ไม่ใช่ NULL)
    assert login_unknown["user_id"] == -1
    assert login_unknown["room_id"] == -1

    # endpoint_or_command: เติมจาก request path ให้เอง ไม่ต้องพึ่ง caller ส่งมา
    assert login_ok["endpoint_or_command"] == "POST /api/auth/login"
    assert read_row["endpoint_or_command"] == "GET /api/issues"
    assert create_row["endpoint_or_command"] == "POST /api/issues"
    # การอ่านระดับ collection ไม่มีเอนทิตีจริง → "-" (ไม่ปล่อยว่าง)
    assert read_row["entity_id"] == "-"
    assert create_row["entity_id"] == str(issue_id)

    # execution_time_ms: วัดจาก middleware — 0 คือ "วัดไม่ได้" เท่านั้น (ต้องเป็น int เสมอ)
    assert all(isinstance(r["execution_time_ms"], int) for r in rows)
    assert all(r["execution_time_ms"] >= 0 for r in rows)

    # ip/user_agent: ต้องถูกเติมจาก request context (TestClient → 'testclient')
    assert login_ok["ip_address"] != "-"
    assert login_ok["user_agent"] != "-"

    # old/new values: {} แทน NULL (การอ่าน/ล็อกอินไม่มีการเปลี่ยนแปลงข้อมูล)
    assert _json(read_row["old_values"]) == {}
    assert _json(read_row["new_values"]) == {}
    assert _json(create_row["new_values"]), "CREATE_ISSUE ต้องมี new_values ไม่ว่าง"
    assert _json(create_row["old_values"]) == {}, "สร้างใหม่ → ไม่มีค่าเดิม"


@pytest.mark.asyncio
async def test_trace_id_response_header_matches_audit_row(client, db_pool, audit_world):
    """middleware คืน X-Trace-Id → trace_id ใน audit_logs ต้องตรงกัน (ตามรอย request ได้)"""
    world = audit_world
    res = _create_issue(client, world, title="เรื่องตามรอย trace")
    assert res.status_code == 200
    trace_id = res.headers.get("X-Trace-Id")
    assert trace_id, "ต้องมี header X-Trace-Id"

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT trace_id FROM audit_logs WHERE action = 'CREATE_ISSUE' AND entity_id = $1",
            str(res.json()["id"])
        )
    assert row["trace_id"] == trace_id, "trace_id ใน DB ต้องตรงกับ header ที่ตอบกลับ"


# === Section 4: GET /api/audit-logs (RBAC + filter + keyset pagination) ===
async def _seed_rows(db_pool, *, service_name: str, count: int,
                     created_at: datetime | None = None, action: str = "SEED"):
    """แทรกแถว audit ตรง ๆ (ข้าม HTTP) — เพื่อคุม `created_at` ให้เท่ากันเป๊ะได้

    จำเป็นเพราะ keyset มีสองคีย์: ถ้าเทสต์ผ่าน HTTP อย่างเดียว `created_at` จะต่างกันทุกแถว
    แล้วจะไม่มีทางพิสูจน์ว่าการตัดสินลำดับด้วย `id` ทำงาน
    """
    ids = []
    async with db_pool.acquire() as conn:
        for _ in range(count):
            ids.append(await conn.fetchval(
                """
                INSERT INTO audit_logs
                    (actor_identifier, client_source, service_name, action,
                     entity_type, entity_id, status, old_values, new_values,
                     endpoint_or_command, ip_address, user_agent, execution_time_ms, created_at)
                VALUES ('tester', 'web', $1, $2, 'issue', '-', 'success',
                        '{}'::jsonb, '{}'::jsonb, 'GET /seed', '127.0.0.1', 'pytest', 1,
                        COALESCE($3, CURRENT_TIMESTAMP))
                RETURNING id
                """,
                service_name, action, created_at,
            ))
    return ids


@pytest.mark.asyncio
async def test_audit_logs_endpoint_access(client, db_pool, audit_world):
    """admin ดูได้ 200; ครู/สภานักเรียน/หัวหน้าห้อง → 403"""
    world = audit_world

    # สร้าง activity ให้มีข้อมูล
    res = _create_issue(client, world, title="เรื่องสำหรับ audit")
    issue_id = res.json()["id"]
    client.post(f"/api/issues/{issue_id}/accept", json={"estimated_days": 1},
                headers={"Authorization": f"Bearer {world['head']['token']}"})

    # admin → 200
    res = client.get("/api/audit-logs", headers={"Authorization": f"Bearer {world['admin']['token']}"})
    assert res.status_code == 200, f"→ {res.status_code}: {res.text}"
    body = res.json()
    assert len(body["items"]) >= 1
    assert "action" in body["items"][0]
    # keyset ไม่มี total/page/pages — ตัวเลขพวกนั้นเพี้ยนทันทีที่ตารางมีแถวใหม่
    assert "total" not in body
    assert "page" not in body
    assert "has_more" in body and "next_cursor" in body

    # head (ไม่มี VIEW_AUDIT_LOG) → 403
    res = client.get("/api/audit-logs", headers={"Authorization": f"Bearer {world['head']['token']}"})
    assert res.status_code == 403

    # ครูทั่วไป → 403
    sid = f"AU{random.randint(1000, 9999)}TE"
    tid = await auth_service.register_user(db_pool, sid, "1234", "ครู", sid, "", 1, "teacher")
    res = client.get("/api/audit-logs",
                     headers={"Authorization": f"Bearer {auth_service.create_access_token(tid)}"})
    assert res.status_code == 403

    # สภานักเรียน (scope all แต่ไม่มี VIEW_AUDIT_LOG) → 403 — กันข้อมูลอ่อนไหวรั่ว
    sid = f"AU{random.randint(1000, 9999)}CM"
    cmid = await auth_service.register_user(db_pool, sid, "1234", "สภานักเรียน", sid, "", 1, "council_member")
    res = client.get("/api/audit-logs",
                     headers={"Authorization": f"Bearer {auth_service.create_access_token(cmid)}"})
    assert res.status_code == 403, "สภานักเรียนต้องไม่มีสิทธิ์ดู audit"


@pytest.mark.asyncio
async def test_audit_logs_endpoint_filters_pagination(client, db_pool, audit_world):
    """filter ตาม action + แบ่งหน้าแบบ keyset (limit/cursor) + deep-DB ตรงกัน"""
    world = audit_world
    admin_h = {"Authorization": f"Bearer {world['admin']['token']}"}

    # สร้าง activity หลายแบบ: login + create_issue x2 + accept
    client.post("/api/auth/login", json={"username": world["student"]["username"], "password": "1234"})
    r1 = _create_issue(client, world, title="เรื่องที่หนึ่ง")
    r2 = _create_issue(client, world, title="เรื่องที่สอง")
    client.post(f"/api/issues/{r1.json()['id']}/accept", json={"estimated_days": 1},
                headers={"Authorization": f"Bearer {world['head']['token']}"})

    # filter action=CREATE_ISSUE → เฉพาะ 2 อัน
    res = client.get("/api/audit-logs", params={"action": "CREATE_ISSUE"}, headers=admin_h)
    assert res.status_code == 200
    body = res.json()
    assert len(body["items"]) == 2, f"ต้องมี CREATE_ISSUE 2 อัน แต่ได้ {len(body['items'])}"
    assert all(i["action"] == "CREATE_ISSUE" for i in body["items"])
    assert body["has_more"] is False
    assert body["next_cursor"] is None, "หมดแล้วต้องไม่ส่ง cursor"

    # limit=1 → 1 แถว/หน้า + ต้องมี cursor ให้หน้าถัดไป
    res = client.get("/api/audit-logs", params={"limit": 1}, headers=admin_h)
    assert res.status_code == 200
    body = res.json()
    assert len(body["items"]) == 1
    assert body["has_more"] is True
    assert body["next_cursor"], "has_more=True ต้องมี next_cursor"

    # deep-DB verify: item แรก (ใหม่สุด) ตรงกับ audit_logs ล่าสุด (เรียงคีย์เดียวกับ service)
    async with db_pool.acquire() as conn:
        newest = await conn.fetchrow(
            "SELECT action FROM audit_logs ORDER BY created_at DESC, id DESC LIMIT 1"
        )
    assert body["items"][0]["action"] == newest["action"]

    # หน้าถัดไปต่อจาก cursor ได้ และไม่เห็นแถวซ้ำ
    res = client.get("/api/audit-logs", params={"limit": 1, "cursor": body["next_cursor"]},
                     headers=admin_h)
    assert res.status_code == 200, res.text
    assert res.json()["items"][0]["id"] != body["items"][0]["id"]


@pytest.mark.asyncio
async def test_audit_logs_keyset_survives_identical_timestamps(client, db_pool, audit_world):
    """แถวที่ `created_at` เท่ากันเป๊ะ (transaction เดียวกัน) ต้องไม่ถูกตัดทิ้งทั้งกลุ่ม

    เทสต์นี้จะพังทันทีถ้า keyset เทียบแค่ `created_at` เดียว หรือถ้า index composite
    ไม่ได้ถูกใช้ตามที่ออกแบบไว้
    """
    ts = datetime(2026, 1, 1, 5, 0, tzinfo=timezone.utc)
    ids = await _seed_rows(db_pool, service_name="tie_service", count=5, created_at=ts)
    admin_h = {"Authorization": f"Bearer {audit_world['admin']['token']}"}

    seen: list[str] = []
    cursor = None
    pages = 0
    while True:
        params: dict = {"service_name": "tie_service", "limit": 2}
        if cursor:
            params["cursor"] = cursor
        res = client.get("/api/audit-logs", params=params, headers=admin_h)
        assert res.status_code == 200, res.text
        body = res.json()
        seen.extend(i["id"] for i in body["items"])
        pages += 1
        assert pages < 10, "วนหน้าไม่จบ"
        if not body["has_more"]:
            assert body["next_cursor"] is None
            break
        cursor = body["next_cursor"]
        assert cursor

    assert pages == 3, f"5 แถว limit=2 ต้องได้ 3 หน้า แต่ได้ {pages}"
    assert len(seen) == 5, f"created_at เท่ากันต้องไม่หลุด/ซ้ำ — ได้ {len(seen)} แถว"
    assert set(seen) == {str(i) for i in ids}, "ต้องได้แถวครบและเป็นชุดเดียวกัน"


@pytest.mark.asyncio
async def test_audit_logs_keyset_ignores_rows_inserted_mid_walk(client, db_pool, audit_world):
    """ระหว่างที่ผู้ใช้กำลังอ่าน มีแถวใหม่แทรกหัว — หน้าถัดไปต้องไม่เห็นซ้ำ

    นี่คือเหตุผลทั้งหมดที่เลิกใช้ OFFSET (ตารางนี้โตทุกวินาที)
    """
    await _seed_rows(db_pool, service_name="walk_service", count=4)
    admin_h = {"Authorization": f"Bearer {audit_world['admin']['token']}"}

    first = client.get("/api/audit-logs",
                       params={"service_name": "walk_service", "limit": 2},
                       headers=admin_h)
    assert first.status_code == 200, first.text
    first_body = first.json()
    assert len(first_body["items"]) == 2
    assert first_body["has_more"] is True

    # แถวใหม่ (created_at ใหม่กว่า) แทรกหัวระหว่างการอ่าน
    await _seed_rows(db_pool, service_name="walk_service", count=1)

    second = client.get("/api/audit-logs",
                        params={"service_name": "walk_service", "limit": 2,
                                "cursor": first_body["next_cursor"]},
                        headers=admin_h)
    assert second.status_code == 200, second.text
    second_body = second.json()

    first_ids = {i["id"] for i in first_body["items"]}
    second_ids = {i["id"] for i in second_body["items"]}
    assert len(second_body["items"]) == 2
    assert first_ids.isdisjoint(second_ids), "แถวที่แทรกหัวต้องไม่ทำให้หน้าถัดไปเห็นซ้ำ"
    assert second_body["next_cursor"] is None, "แถวเดิมครบแล้ว → จบ (ไม่นับแถวใหม่ที่แทรก)"


@pytest.mark.parametrize("bad_cursor", ["not-a-cursor", "%%%", "abc", "2567a2F8"])
@pytest.mark.asyncio
async def test_audit_logs_rejects_bad_cursor(client, db_pool, audit_world, bad_cursor):
    """cursor ที่พิมพ์มือ/ตัดขาด → 400 ไม่ใช่ 500 (ผู้ใช้เห็นข้อความ ไม่ใช่ stack trace)"""
    res = client.get("/api/audit-logs", params={"cursor": bad_cursor},
                     headers={"Authorization": f"Bearer {audit_world['admin']['token']}"})
    assert res.status_code == 400, f"{bad_cursor!r} → {res.status_code}: {res.text}"
    assert "cursor" in res.json()["detail"]


@pytest.mark.asyncio
async def test_audit_logs_endpoint_exposes_room(client, db_pool, audit_world):
    """🏫 API ต้องส่ง room_id + room_name ออกมาด้วย (LEFT JOIN rooms) — ไม่ใช่ -1/None เสมอ"""
    world = audit_world
    admin_h = {"Authorization": f"Bearer {world['admin']['token']}"}

    # login ที่ไม่เจอชื่อ → ไม่รู้ว่าใคร → room_id = -1 และ room_name = None (ไม่มีห้องให้ join)
    client.post("/api/auth/login", json={"username": "ไม่มีคนนี้เลย", "password": "1234"})
    # login สำเร็จ + แจ้งเรื่อง → resolve ห้องของผู้กระทำได้
    client.post("/api/auth/login", json={"username": world["student"]["username"], "password": "1234"})
    created = _create_issue(client, world, title="เรื่องของห้อง")
    assert created.status_code == 200, f"→ {created.status_code}: {created.text}"
    issue_id = created.json()["id"]

    async with db_pool.acquire() as conn:
        expected_name = await conn.fetchval(
            "SELECT room_name FROM rooms WHERE id = $1", world["student"]["room_id"]
        )

    # 1) แถวที่มีห้อง → room_id ตรง + room_name มาจากตาราง rooms
    res = client.get("/api/audit-logs", params={"entity_id": issue_id}, headers=admin_h)
    assert res.status_code == 200, f"→ {res.status_code}: {res.text}"
    items = res.json()["items"]
    assert items, "ต้องมี audit ของ CREATE_ISSUE"
    assert items[0]["room_id"] == world["student"]["room_id"]
    assert items[0]["room_name"] == expected_name, (
        f"room_name ต้อง join ได้จาก rooms แต่ได้ {items[0]['room_name']!r}"
    )

    # 2) แถวที่ไม่มีห้อง (-1) → ต้องไม่ถูก JOIN ตัดแถวทิ้ง และ room_name เป็น null
    res = client.get("/api/audit-logs", params={"action": "login", "status": "error"}, headers=admin_h)
    assert res.status_code == 200
    unknown = [i for i in res.json()["items"] if i["actor_identifier"] == "ไม่มีคนนี้เลย"]
    assert unknown, "แถว room_id = -1 ต้องยังออกมา (LEFT JOIN ไม่ใช่ JOIN)"
    assert unknown[0]["room_id"] == -1
    assert unknown[0]["room_name"] is None, "ไม่มีห้อง → room_name เป็น null ไม่ใช่ '-'"

    # 3) deep-DB: ค่าที่ API ส่งตรงกับแถวจริงใน audit_logs
    async with db_pool.acquire() as conn:
        # entity_id เป็น VARCHAR — issue id เป็น int ต้อง str() ก่อน ไม่งั้น asyncpg DataError
        row = await conn.fetchrow(
            "SELECT room_id FROM audit_logs WHERE entity_id = $1 AND action = 'CREATE_ISSUE'",
            str(issue_id)
        )
    assert row["room_id"] == items[0]["room_id"]


@pytest.mark.asyncio
async def test_audit_logs_service_filter_and_actor_name(client, db_pool, audit_world):
    """กรองด้วย service_name ได้ + `actor_name` ต้อง join จาก users.full_name"""
    world = audit_world
    created = _create_issue(client, world, title="เรื่องมีชื่อผู้ทำ")
    assert created.status_code == 200
    issue_id = created.json()["id"]

    res = client.get("/api/audit-logs",
                     params={"service_name": "issue_service", "entity_id": issue_id},
                     headers={"Authorization": f"Bearer {world['admin']['token']}"})
    assert res.status_code == 200, res.text
    items = res.json()["items"]
    assert items, "ต้องมี audit ของ CREATE_ISSUE"
    assert all(i["service_name"] == "issue_service" for i in items), \
        "ตัวกรอง service_name ต้องกรองจริง"

    create_item = next(i for i in items if i["action"] == "CREATE_ISSUE")
    # issue_service ส่ง actor_identifier = str(user_id) ⇒ ชื่อจริงต้องมาจากตาราง users
    assert create_item["actor_identifier"] == str(world["student"]["user_id"])
    assert create_item["actor_name"] == "student ทดสอบ", (
        f"actor_name ต้อง join จาก users.full_name แต่ได้ {create_item['actor_name']!r}"
    )

    # login ที่หาชื่อไม่เจอ → user_id = -1 → ไม่มีแถว users ให้ join ⇒ actor_name = null
    client.post("/api/auth/login", json={"username": "ไม่มีคนนี้เลย", "password": "1234"})
    res = client.get("/api/audit-logs",
                     params={"action": "login", "status": "error"},
                     headers={"Authorization": f"Bearer {world['admin']['token']}"})
    assert res.status_code == 200
    unknown = next(i for i in res.json()["items"] if i["actor_identifier"] == "ไม่มีคนนี้เลย")
    assert unknown["actor_name"] is None, "ไม่รู้จักผู้ใช้ → actor_name ต้องเป็น null (หน้าเว็บใช้ identifier แทน)"


@pytest.mark.asyncio
async def test_audit_logs_options_endpoint(client, db_pool, audit_world):
    """`/options` คืนค่าที่มีจริงสำหรับเติม dropdown — เรียงแล้ว ไม่ซ้ำ ไม่มี sentinel '-'"""
    world = audit_world
    client.post("/api/auth/login", json={"username": world["student"]["username"], "password": "1234"})
    created = _create_issue(client, world, title="เรื่องเติม dropdown")
    assert created.status_code == 200

    res = client.get("/api/audit-logs/options",
                     headers={"Authorization": f"Bearer {world['admin']['token']}"})
    assert res.status_code == 200, res.text
    body = res.json()

    assert "login" in body["actions"]
    assert "CREATE_ISSUE" in body["actions"]
    assert "issue_service" in body["service_names"]
    assert "auth_service" in body["service_names"]
    assert "success" in body["statuses"]
    assert "issue" in body["entity_types"]

    for key in ("service_names", "actions", "statuses", "entity_types"):
        values = body[key]
        assert "-" not in values, f"{key} ต้องไม่ส่ง sentinel '-' ออกมา (ไม่ใช่ตัวเลือกจริง)"
        assert values == sorted(values), f"{key} ต้องเรียงแล้ว (หน้าเว็บใช้ตรง ๆ)"
        assert len(values) == len(set(values)), f"{key} ต้องไม่ซ้ำกัน"

    # สิทธิ์เดียวกับรายการ: หัวหน้าห้องไม่มี VIEW_AUDIT_LOG → 403
    res = client.get("/api/audit-logs/options",
                     headers={"Authorization": f"Bearer {world['head']['token']}"})
    assert res.status_code == 403


# === Section: IP จริงของผู้ใช้หลัง proxy chain ===
@pytest.mark.asyncio
async def test_client_ip_prefers_cf_connecting_ip(client, db_pool, audit_world):
    """☁️ Cloudflare อยู่หน้า Traefik → CF-Connecting-IP ต้องชนะ X-Forwarded-For

    ของจริงเคยพลาด: Traefik publish แบบ ingress (Swarm SNAT) + forwardedHeaders
    default (insecure=false) → Traefik เขียนทับ XFF ด้วย 10.0.0.2 ของ ingress-endpoint
    ⇒ audit_logs.ip_address เป็น 10.0.0.2 ทุกแถว อ่านย้อนหลังไม่ได้
    """
    res = client.post(
        "/api/auth/login",
        json={"username": "cf_probe", "password": "xxxx"},
        headers={
            "CF-Connecting-IP": "203.0.113.9",   # ค่าจริงจาก Cloudflare
            "X-Forwarded-For": "10.0.0.2",        # ค่าที่ Traefik ใส่ทับ (ไร้ความหมาย)
            "User-Agent": "cf-probe/1.0",
        },
    )
    assert res.status_code == 401

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT ip_address FROM audit_logs WHERE actor_identifier = 'cf_probe' ORDER BY created_at DESC LIMIT 1"
        )
    assert row["ip_address"] == "203.0.113.9", (
        f"ต้องใช้ CF-Connecting-IP ไม่ใช่ XFF แต่ได้ {row['ip_address']!r}"
    )


@pytest.mark.asyncio
async def test_client_ip_falls_back_to_xff_leftmost(client, db_pool, audit_world):
    """ไม่มี CF-Connecting-IP (dev/local) → ใช้ XFF ตัวซ้ายสุด แล้ว normalize ให้สะอาด"""
    res = client.post(
        "/api/auth/login",
        json={"username": "xff_probe", "password": "xxxx"},
        headers={"X-Forwarded-For": "198.51.100.7:51234, 10.0.0.2, 10.0.0.3"},
    )
    assert res.status_code == 401

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT ip_address FROM audit_logs WHERE actor_identifier = 'xff_probe' ORDER BY created_at DESC LIMIT 1"
        )
    # ตัวซ้ายสุด + ตัด port ทิ้ง (VARCHAR(45) ต้องไม่เก็บ "198.51.100.7:51234")
    assert row["ip_address"] == "198.51.100.7", f"ได้ {row['ip_address']!r}"
