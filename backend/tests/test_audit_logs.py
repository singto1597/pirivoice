# === Audit Logs Tests: เก็บทุก action (login / create / accept / escalate / resolve / cancel / reject / read) + API ดู ===
import json
import random
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


# === Section 4: GET /api/audit-logs (RBAC + filter + pagination) ===
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
    assert body["total"] >= 1
    assert body["page_size"] == 20
    assert len(body["items"]) >= 1
    assert "action" in body["items"][0]

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
    """filter ตาม action + แบ่งหน้า (limit/offset) + deep-DB ตรงกัน"""
    world = audit_world

    # สร้าง activity หลายแบบ: login + create_issue x2 + accept
    client.post("/api/auth/login", json={"username": world["student"]["username"], "password": "1234"})
    r1 = _create_issue(client, world, title="เรื่องที่หนึ่ง")
    r2 = _create_issue(client, world, title="เรื่องที่สอง")
    client.post(f"/api/issues/{r1.json()['id']}/accept", json={"estimated_days": 1},
                headers={"Authorization": f"Bearer {world['head']['token']}"})

    # filter action=CREATE_ISSUE → เฉพาะ 2 อัน
    res = client.get("/api/audit-logs", params={"action": "CREATE_ISSUE"},
                     headers={"Authorization": f"Bearer {world['admin']['token']}"})
    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 2, f"ต้องมี CREATE_ISSUE 2 อัน แต่ได้ {body['total']}"
    assert all(i["action"] == "CREATE_ISSUE" for i in body["items"])

    # ยอดทั้งหมด (ก่อน filter) สำหรับเทียบ pagination
    res_all = client.get("/api/audit-logs", headers={"Authorization": f"Bearer {world['admin']['token']}"})
    full_total = res_all.json()["total"]
    assert full_total >= 4

    # pagination: limit=1 → 1 item ต่อหน้า, total เท่าเดิม
    res = client.get("/api/audit-logs", params={"limit": 1, "offset": 0},
                     headers={"Authorization": f"Bearer {world['admin']['token']}"})
    body = res.json()
    assert len(body["items"]) == 1
    assert body["total"] == full_total
    assert body["page"] == 1
    assert body["pages"] == full_total

    # deep-DB verify: item แรก (ใหม่สุด) ตรงกับ audit_logs ล่าสุด
    async with db_pool.acquire() as conn:
        newest = await conn.fetchrow("SELECT action FROM audit_logs ORDER BY created_at DESC LIMIT 1")
    assert body["items"][0]["action"] == newest["action"]
