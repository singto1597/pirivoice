"""
💡 E1 — Quick Suggestion (board_type = 'suggestion')
=====================================================
ผู้ใช้ทั่วไปเสนอไอเดียเองได้ **โดยไม่ผ่านด่านอนุมัติของสภา** (ผู้ใช้เลือก: "ขึ้นทันที +
ซ่อนย้อนหลังได้" · "ไม่แจ้งเตือนใครเลย")

ทดสอบ 5 ระดับ:
  1) HTTP — POST /api/boards/suggestions (201) + validation + auth guard
  2) Deep-DB — แถวที่เกิดจริงต้องมี source_issue_id/approved_by/approved_at เป็น NULL
     (นี่คือความต่างทั้งหมดจาก `approve_to_public` — ถ้าสามคอลัมน์นี้มีค่า
     แปลว่ามี "เงา" ของการอนุมัติที่ไม่มีอยู่จริง)
  3) ผลข้างเคียง — **ต้องไม่มี notification และไม่มี push_outbox** (ผู้ใช้เลือกข้อนี้)
  4) ชนิดบอร์ด — คอมเมนต์ได้ / โหวตไม่ได้ / ผ่าน CHECK constraint ใหม่
  5) Migration 022 — idempotent + CHECK รับ 3 ค่า

ตาม docs/rules/testing.md: ทุก test ตรวจ DB ตรง ๆ ผ่าน db_pool ไม่เชื่อ HTTP response
"""
import importlib
import random
from datetime import datetime

import pytest
import pytest_asyncio

from core.config import settings
from services import auth_service


@pytest_asyncio.fixture
async def sugg_world(db_pool):
    """room + student 2 คน — พอสำหรับทดสอบ "ใครสร้างของใคร" และ "ไม่แจ้งใคร"""
    room_code = f"บ.{random.randint(1, 90)}"
    async with db_pool.acquire() as conn:
        room_id = await conn.fetchval(
            "INSERT INTO rooms (room_code, room_name, level) VALUES ($1,$2,'ม.5') RETURNING id",
            room_code, room_code
        )

    users = {}
    for label, no in [("student", 1), ("other", 2)]:
        sid = f"S{random.randint(1000, 9999)}{label[:2].upper()}"
        uid = await auth_service.register_user(
            db_pool, sid, "1234", f"{label} ทดสอบ", sid, room_code, no, "student"
        )
        users[label] = {
            "user_id": uid,
            "token": auth_service.create_access_token(uid),
            "room_id": room_id,
        }
    return users


def _auth(world, who="student"):
    return {"Authorization": f"Bearer {world[who]['token']}"}


def _suggest(client, world, *, title="ควรมีน้ำดื่มฟรีที่โรงอาหาร",
             description="นักเรียนหลายคนไม่มีเงินซื้อน้ำระหว่างวัน",
             is_anonymous=False, who="student", extra=None):
    body = {"title": title, "description": description, "is_anonymous": is_anonymous}
    if extra:
        body.update(extra)
    return client.post("/api/boards/suggestions", json=body, headers=_auth(world, who))


async def _board_row(db_pool, board_id):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM piri_boards WHERE id = $1", board_id)


def _as_utc(iso: str) -> datetime:
    """สตริง ISO จาก API → datetime (aware, UTC) เพื่อเทียบ " instant " กับค่าจาก DB

    pydantic v2 เขียน UTC เป็น `…Z` ซึ่ง `datetime.fromisoformat` อ่านได้ตั้งแต่ 3.11
    แต่เติม replace ไว้ให้ชัดเจนและไม่ผูกกับเวอร์ชัน Python ที่รันเทสต์
    """
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


# ===================== 1) สร้าง + deep-DB =====================

@pytest.mark.asyncio
async def test_create_suggestion_201_and_deep_db(sugg_world, client, db_pool):
    """สร้างข้อเสนอ → 201 + แถวจริงในตารางมีค่าตั้งต้นครบ (ไม่มีเงาของการอนุมัติ)"""
    res = _suggest(client, sugg_world, is_anonymous=True)
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["board_type"] == "suggestion"
    assert body["title"] == "ควรมีน้ำดื่มฟรีที่โรงอาหาร"
    assert isinstance(body["id"], int) and body["id"] > 0
    assert body["created_at"], "ต้องคืน created_at จาก DB (RETURNING) ไม่ใช่เวลาที่ client เดา"

    row = await _board_row(db_pool, body["id"])
    assert row is not None, "ต้องมีแถวจริงใน piri_boards"
    assert row["board_type"] == "suggestion"
    assert row["status"] == "active", "ขึ้นบอร์ดทันที — ไม่มีสถานะ 'pending'"
    assert row["allow_comments"] is True
    assert row["author_id"] == sugg_world["student"]["user_id"]
    assert row["is_anonymous"] is True
    # ★ สามคอลัมน์นี้คือความต่างทั้งหมดจาก approve_to_public
    assert row["source_issue_id"] is None, "ข้อเสนอไม่ได้มาจาก issue"
    assert row["approved_by"] is None, "ไม่มีผู้อนุมัติ"
    assert row["approved_at"] is None
    assert row["deleted_at"] is None

    # created_at ที่คืนมาต้องตรงกับในตาราง (ไม่ใช่ datetime.now() ที่ฝั่ง router สร้างเอง)
    # ⚠️ เทียบ "เวลา" ไม่เทียบ "สตริง" — pydantic v2 serialize UTC เป็น `…Z`
    #    แต่ Python `.isoformat()` ให้ `…+00:00` ⇒ สตริงต่างกันทั้งที่เป็นเวลาเดียวกัน
    #    (ถ้าเทียบสตริง เทสต์จะพังด้วยเรื่องรูปแบบ ไม่ใช่ด้วยบั๊กที่มันเกิดมาดัก)
    assert _as_utc(body["created_at"]) == row["created_at"], (
        f"created_at ต้องมาจาก DB RETURNING ไม่ใช่เวลาที่ router สร้างเอง: "
        f"body={body['created_at']!r} row={row['created_at']!r}"
    )


@pytest.mark.asyncio
async def test_author_id_comes_from_token_not_body(sugg_world, client, db_pool):
    """ส่ง user_id ของคนอื่นมาใน body → ต้องถูก pydantic ตัดทิ้ง (เจ้าของคือผู้ถือ token)"""
    res = _suggest(
        client, sugg_world,
        extra={"user_id": sugg_world["other"]["user_id"], "board_type": "vote"},
    )
    assert res.status_code == 201, res.text

    row = await _board_row(db_pool, res.json()["id"])
    assert row["author_id"] == sugg_world["student"]["user_id"], "ห้ามรับ user_id จาก client"
    assert row["board_type"] == "suggestion", "ห้ามรับ board_type จาก client (ช่องเลี่ยงด่านสภา)"


@pytest.mark.asyncio
async def test_audit_log_written_in_same_transaction(sugg_world, client, db_pool):
    """ต้องมี audit CREATE_SUGGESTION 1 แถว ชี้ entity_id ของบอร์ดที่เพิ่งสร้าง"""
    board_id = _suggest(client, sugg_world).json()["id"]

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT action, entity_type, entity_id, user_id, new_values
            FROM audit_logs WHERE action = 'CREATE_SUGGESTION'
            """
        )
    assert row is not None, "ต้องมี audit — เป็น create ที่ผู้ใช้ทั่วไปทำได้ ต้องตรวจย้อนหลังได้"
    assert row["entity_type"] == "piri_board"
    assert row["entity_id"] == str(board_id)
    assert row["user_id"] == sugg_world["student"]["user_id"]


# ===================== 2) validation =====================

@pytest.mark.asyncio
@pytest.mark.parametrize("field,value", [
    ("title", "ab"),            # สั้นกว่า min_length=3
    ("title", ""),              # ว่าง
    ("description", ""),        # ว่าง
    ("title", "x" * 201),       # ยาวกว่า max_length=200
    ("description", "x" * 2001),
])
async def test_validation_rejects(sugg_world, client, field, value):
    """ค่าที่ผิดขอบเขต → 422 (pydantic) — ไม่แตะ DB"""
    payload = {"title": "หัวข้อปกติ", "description": "รายละเอียดปกติ", "is_anonymous": False}
    payload[field] = value
    res = client.post("/api/boards/suggestions", json=payload, headers=_auth(sugg_world))
    assert res.status_code == 422, res.text


@pytest.mark.asyncio
@pytest.mark.parametrize("title,description", [
    ("   ", "รายละเอียดปกติ"),      # ★ ช่องโหว่ที่ pydantic จับไม่ได้: min_length นับ " " เป็น 3 ตัว
    ("หัวข้อปกติ", "   "),           # ★ รายละเอียดมีแต่ช่องว่าง
    ("  ab  ", "รายละเอียดปกติ"),    # strip แล้วเหลือ 2 ตัวอักษร
])
async def test_whitespace_only_rejected_422(sugg_world, client, db_pool, title, description):
    """★ ช่องว่างล้วนต้องไม่ผ่าน — pydantic นับความยาวก่อน strip ⇒ ต้องมีด่านที่ router"""
    res = _suggest(client, sugg_world, title=title, description=description)
    assert res.status_code == 422, res.text

    async with db_pool.acquire() as conn:
        n = await conn.fetchval("SELECT COUNT(*) FROM piri_boards")
    assert n == 0, "ต้องไม่สร้างบอร์ดที่หัวข้อ/รายละเอียดว่าง"


@pytest.mark.asyncio
async def test_whitespace_is_stripped_before_save(sugg_world, client, db_pool):
    """ข้อความที่มีช่องว่างหัวท้าย → เก็บแบบ strip แล้ว (ไม่เก็บขยะลง DB)"""
    res = _suggest(client, sugg_world, title="  หัวข้อมีช่องว่าง  ", description="  รายละเอียด  ")
    assert res.status_code == 201, res.text
    assert res.json()["title"] == "หัวข้อมีช่องว่าง"

    row = await _board_row(db_pool, res.json()["id"])
    assert row["title"] == "หัวข้อมีช่องว่าง"
    assert row["description"] == "รายละเอียด"


@pytest.mark.asyncio
async def test_missing_token_401(sugg_world, client):
    """ไม่มี token → 401"""
    res = client.post("/api/boards/suggestions", json={
        "title": "หัวข้อปกติ", "description": "รายละเอียดปกติ",
    })
    assert res.status_code == 401, res.text


@pytest.mark.asyncio
async def test_api_key_without_user_401_not_500(sugg_world, client, db_pool):
    """★ X-API-Key (system RPC) → get_current_user คืน user_id=None ⇒ ต้อง 401 ไม่ใช่ 500

    (ถ้าลืม `_ensure_user` จะกลายเป็น INSERT ที่ author_id = NULL → 500 จาก NOT NULL
    หรือแย่กว่านั้นคือสร้างบอร์ดที่ไม่มีเจ้าของ)
    """
    res = client.post(
        "/api/boards/suggestions",
        json={"title": "หัวข้อปกติ", "description": "รายละเอียดปกติ"},
        headers={"X-API-Key": settings.API_KEY},
    )
    assert res.status_code == 401, res.text

    async with db_pool.acquire() as conn:
        n = await conn.fetchval("SELECT COUNT(*) FROM piri_boards")
    assert n == 0, "401 แล้วต้องไม่มีแถวเกิด"


# ===================== 3) ★ ไม่แจ้งเตือนใครเลย (ผู้ใช้เลือก) =====================

@pytest.mark.asyncio
async def test_no_notifications_and_no_push_outbox(sugg_world, client, db_pool):
    """★ หัวใจของข้อตัดสินใจ "ไม่แจ้งใครเลย" — ต้องไม่มี notification และไม่มี outbox

    ถ้าวันหน้ามีคนไปเรียก `notify_fanout` ใน `create_suggestion` (ลอกมาจาก
    `approve_to_public` โดยไม่คิด) เทสต์นี้จะแตกทันที — และมันสำคัญเพราะ fanout
    ยิงทุก active student (~800-1,000 คน) ต่อข้อเสนอ 1 อันที่ใครก็กดได้
    """
    assert _suggest(client, sugg_world).status_code == 201

    async with db_pool.acquire() as conn:
        notif = await conn.fetchval("SELECT COUNT(*) FROM notifications")
        outbox = await conn.fetchval("SELECT COUNT(*) FROM push_outbox")
    assert notif == 0, "ข้อเสนอใหม่ต้องไม่แจ้งเตือนใคร"
    assert outbox == 0, "ห้ามมีงาน push ค้าง — trigger 018 จะสร้างให้ทันทีถ้ามี notification"


# ===================== 4) ชนิดบอร์ด: เห็นในฟีด / คอมเมนต์ได้ / โหวตไม่ได้ =====================

@pytest.mark.asyncio
async def test_appears_in_board_list_with_type_filter(sugg_world, client):
    """บอร์ดข้อเสนอโผล่ในฟีดรวม และกรอง ?board_type=suggestion ได้"""
    board_id = _suggest(client, sugg_world).json()["id"]

    res = client.get("/api/boards", headers=_auth(sugg_world))
    assert res.status_code == 200, res.text
    assert board_id in [b["id"] for b in res.json()["items"]]

    res = client.get("/api/boards?board_type=suggestion", headers=_auth(sugg_world))
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["total"] == 1
    assert data["items"][0]["id"] == board_id
    assert data["items"][0]["board_type"] == "suggestion"

    # กรองชนิดอื่นแล้วต้องไม่โผล่
    res = client.get("/api/boards?board_type=vote", headers=_auth(sugg_world))
    assert res.json()["total"] == 0


@pytest.mark.asyncio
async def test_board_type_query_pattern_rejects_bogus(sugg_world, client):
    """ค่า board_type นอก regex ของ router → 422 (ไม่ใช่กรองเงียบ ๆ ได้ [])"""
    res = client.get("/api/boards?board_type=bogus", headers=_auth(sugg_world))
    assert res.status_code == 422, res.text


@pytest.mark.asyncio
async def test_detail_returns_comments_layout_not_choices(sugg_world, client):
    """GET detail ของข้อเสนอ → ใช้เลย์เอาต์คอมเมนต์ (choices ว่าง) + view_count ถูกนับ"""
    board_id = _suggest(client, sugg_world).json()["id"]

    res = client.get(f"/api/boards/{board_id}", headers=_auth(sugg_world))
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["board_type"] == "suggestion"
    assert data["choices"] == [], "ข้อเสนอไม่ใช่บอร์ดโหวต"
    assert data["comments"] == []
    assert data["allow_comments"] is True


@pytest.mark.asyncio
async def test_comment_on_suggestion_allowed(sugg_world, client, db_pool):
    """★ คอมเมนต์บนข้อเสนอได้ — นี่คือพฤติกรรมที่เปลี่ยนจากเดิม (เดิม talk เท่านั้น)"""
    board_id = _suggest(client, sugg_world).json()["id"]

    res = client.post(
        f"/api/boards/{board_id}/comments",
        json={"body": "เห็นด้วยมาก"},
        headers=_auth(sugg_world, "other"),
    )
    assert res.status_code == 200, res.text
    assert res.json()["body"] == "เห็นด้วยมาก"

    async with db_pool.acquire() as conn:
        n = await conn.fetchval(
            "SELECT COUNT(*) FROM piri_board_comments WHERE board_id = $1 AND deleted_at IS NULL",
            board_id,
        )
        cnt = await conn.fetchval("SELECT comment_count FROM piri_boards WHERE id = $1", board_id)
    assert n == 1
    assert cnt == 1, "comment_count ต้องถูกอัปเดตด้วย"


@pytest.mark.asyncio
async def test_vote_on_suggestion_rejected_400(sugg_world, client, db_pool):
    """★ โหวตบนข้อเสนอ → 400 (ข้อเสนอไม่ใช่บอร์ดโหวต โดยเจตนา)"""
    board_id = _suggest(client, sugg_world).json()["id"]

    res = client.post(
        f"/api/boards/{board_id}/vote",
        json={"choice_id": 1},
        headers=_auth(sugg_world, "other"),
    )
    assert res.status_code == 400, res.text

    async with db_pool.acquire() as conn:
        n = await conn.fetchval("SELECT COUNT(*) FROM piri_votes WHERE board_id = $1", board_id)
    assert n == 0


@pytest.mark.asyncio
async def test_talk_board_still_commentable_and_vote_still_works(sugg_world, client, db_pool):
    """★ ด่านกันแก้เกิน: บอร์ด talk/vote แบบเดิมต้องไม่พังจากการเปลี่ยนเป็น whitelist"""
    async with db_pool.acquire() as conn:
        talk_id = await conn.fetchval(
            """
            INSERT INTO piri_boards (board_type, title, description, status, allow_comments)
            VALUES ('talk', 'บอร์ดพูดคุย', 'รายละเอียด', 'active', TRUE) RETURNING id
            """
        )
        vote_id = await conn.fetchval(
            """
            INSERT INTO piri_boards (board_type, title, description, status, allow_comments)
            VALUES ('vote', 'บอร์ดโหวต', 'รายละเอียด', 'active', FALSE) RETURNING id
            """
        )
        choice_id = await conn.fetchval(
            "INSERT INTO piri_vote_choices (board_id, choice_text, sort_order) VALUES ($1,'ก',1) RETURNING id",
            vote_id,
        )

    assert client.post(
        f"/api/boards/{talk_id}/comments", json={"body": "ยังคอมเมนต์ได้"},
        headers=_auth(sugg_world),
    ).status_code == 200

    assert client.post(
        f"/api/boards/{vote_id}/vote", json={"choice_id": choice_id},
        headers=_auth(sugg_world, "other"),
    ).status_code == 200

    # บอร์ดโหวตยังคอมเมนต์ไม่ได้ (ไม่ถูกขยายมั่วไปด้วย)
    assert client.post(
        f"/api/boards/{vote_id}/comments", json={"body": "พยายาม"},
        headers=_auth(sugg_world),
    ).status_code == 400


@pytest.mark.asyncio
async def test_board_type_check_constraint_accepts_three_values(sugg_world, client, db_pool):
    """★ CHECK constraint ใหม่ต้องรับ 3 ค่า และยังปฏิเสธค่าที่สี่ (ด่านฐานข้อมูล)"""
    import asyncpg as _asyncpg

    async with db_pool.acquire() as conn:
        for bt in ("talk", "vote", "suggestion"):
            await conn.execute(
                "INSERT INTO piri_boards (board_type, title, description) VALUES ($1,$2,'x')",
                bt, f"ทดสอบ {bt}",
            )

        with pytest.raises(_asyncpg.exceptions.CheckViolationError):
            await conn.execute(
                "INSERT INTO piri_boards (board_type, title, description) VALUES ('event','x','y')"
            )

        # ความยาวคอลัมน์ต้องรองรับ 'suggestion' (10 ตัวอักษรพอดีเพดานเดิม VARCHAR(10))
        maxlen = await conn.fetchval(
            """
            SELECT character_maximum_length FROM information_schema.columns
            WHERE table_name = 'piri_boards' AND column_name = 'board_type'
            """
        )
    assert maxlen == 20, f"ต้องเป็น VARCHAR(20) ไม่ใช่ {maxlen} — 'suggestion' ยาว 10 พอดีเพดานเดิม"


@pytest.mark.asyncio
async def test_hide_board_still_works_on_suggestion(sugg_world, client, db_pool):
    """★ "ซ่อนย้อนหลังได้" — เครื่องมือ moderation เดิมต้องใช้กับข้อเสนอได้ (ข้อตัดสินใจของผู้ใช้)"""
    board_id = _suggest(client, sugg_world).json()["id"]

    async with db_pool.acquire() as conn:
        # ให้ student คนแรกเป็นประธานสภา (มีอำนาจ moderation)
        await conn.execute(
            "UPDATE students SET is_admin = TRUE WHERE user_id = $1",
            sugg_world["student"]["user_id"],
        )

    res = client.post(
        f"/api/boards/{board_id}/hide",
        json={"reason": "เนื้อหาไม่เหมาะสม"},
        headers=_auth(sugg_world),
    )
    assert res.status_code == 200, res.text

    assert client.get(
        f"/api/boards/{board_id}", headers=_auth(sugg_world, "other")
    ).status_code == 404, "ซ่อนแล้วต้อง 404 กับคนอื่น"

    async with db_pool.acquire() as conn:
        row = await _board_row(db_pool, board_id)
    assert row["status"] == "hidden"
    assert row["deleted_at"] is None, "ซ่อน ≠ ลบ — ต้องกู้คืนได้"


# ===================== 5) migration 022 =====================
# ⚠️ ต้องอยู่ท้ายไฟล์: มัน DROP CONSTRAINT/ALTER คอลัมน์จริง แล้วสร้างคืน

@pytest.mark.asyncio
async def test_migration_022_idempotent_and_accepts_suggestion(sugg_world, db_pool):
    """จำลองสคีมาเก่า (CHECK 2 ค่า + VARCHAR(10)) → upgrade() 2 ครั้ง → ต้องรับ 'suggestion' ได้"""
    sugg_world
    mig = importlib.import_module("migrations.022_board_type_suggestion")

    async with db_pool.acquire() as conn:
        # ถอยสคีมากลับเป็นเวอร์ชันก่อน 022 (แบบที่ DB จริงบน production/staging เป็น)
        await conn.execute("ALTER TABLE piri_boards DROP CONSTRAINT IF EXISTS chk_piri_boards_type")
        await conn.execute("ALTER TABLE piri_boards ALTER COLUMN board_type TYPE VARCHAR(10)")
        await conn.execute(
            "ALTER TABLE piri_boards ADD CONSTRAINT chk_piri_boards_type "
            "CHECK (board_type IN ('talk','vote'))"
        )

        # ยืนยันว่าถอยจริง — 'suggestion' ต้องถูกปฏิเสธก่อน migrate
        import asyncpg as _asyncpg
        with pytest.raises(_asyncpg.exceptions.CheckViolationError):
            await conn.execute(
                "INSERT INTO piri_boards (board_type, title, description) VALUES ('suggestion','x','y')"
            )

        await mig.upgrade(conn)
        await mig.upgrade(conn)  # idempotent — รันซ้ำต้องไม่ error

        # หลัง migrate: รับ 3 ค่า + ความยาว 20
        for bt in ("talk", "vote", "suggestion"):
            await conn.execute(
                "INSERT INTO piri_boards (board_type, title, description) VALUES ($1,$2,'x')",
                bt, f"หลัง migrate {bt}",
            )
        with pytest.raises(_asyncpg.exceptions.CheckViolationError):
            await conn.execute(
                "INSERT INTO piri_boards (board_type, title, description) VALUES ('bogus','x','y')"
            )

        maxlen = await conn.fetchval(
            """
            SELECT character_maximum_length FROM information_schema.columns
            WHERE table_name = 'piri_boards' AND column_name = 'board_type'
            """
        )
    assert maxlen == 20
