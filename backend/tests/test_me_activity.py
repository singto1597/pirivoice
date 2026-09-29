"""
🧭 กิจกรรมของฉัน (C1) — GET /api/me/activity
==============================================
ทดสอบ 5 ระดับ:
  1) HTTP — envelope ครบ · 401 (X-API-Key ต้องเป็น 401 **ไม่ใช่ 500**) · 422
  2) **สัญญากับ C3** — `counts` ต้องตรงกับ `GET /api/me/stats` **ทีละฟิลด์**
     นี่คือเหตุผลที่ C1 รวม **4** ประเภท ไม่ใช่ 3 ตามสเปกต้นทาง — ดู `models/me_schemas.py`
     L21-25 ที่เขียนเตือนไว้ว่า *"C1 ต้องใช้ชุดตัวนับเดียวกับ C3 ไม่งั้นเลขไม่ตรงกันแล้วดูเหมือนบั๊ก"*
     ⇒ เทสต์ A2 คือด่านที่บังคับสัญญานั้น ไม่ใช่แค่คอมเมนต์
  3) **ความทนของ join** — ต้นทางถูกลบ (soft) ⇒ คอมเมนต์/โหวต **ยังอยู่ใน feed**
     พร้อม `is_deleted_source = true` (ต้องเป็น LEFT JOIN ไม่ใช่ INNER)
     ⚠️ แต่ `issue_created` **ต้องหาย** — ให้ตรงกับ `total_reported` ของ C3 ที่มี `deleted_at IS NULL`
     สองข้อนี้ดูขัดกันแต่ถูกทั้งคู่: "เรื่องที่ฉันแจ้ง" เป็นของฉันที่ถูกลบ ⇒ ไม่นับ ·
     "คอมเมนต์ที่ฉันเขียน" ยังเป็นของฉัน แม้เรื่องแม่จะถูกซ่อน
  4) **pagination** — tie-break ต้องทำให้ลำดับคงที่ ไม่มีแถวซ้ำ/หายข้ามหน้า
     (`CURRENT_TIMESTAMP` = เวลา **เริ่มทรานแซกชัน** ⇒ แถวที่ insert พร้อมกันมี `created_at` เท่ากันเป๊ะ)
  5) Fallback — ผู้ใช้ใหม่ที่ไม่มีข้อมูลเลย ⇒ `items=[]` · `total=0` · `counts` เป็น 0 ครบ **ไม่ใช่ null/500**

ตาม docs/rules/testing.md: ตรวจ DB ตรง ๆ ผ่าน db_pool · ห้าม hardcode id
"""
import random
from datetime import datetime

import pytest
import pytest_asyncio

from services import auth_service

# ชุดตัวนับที่ C1 ใช้ — ต้องตรงกับ `ACTIVITY_TYPES` ใน `me_service.py`
ACTIVITY_TYPES = (
    "issue_created",
    "vote_cast",
    "board_comment_posted",
    "issue_comment_posted",
)

# 🔗 สะพานเชื่อม C1 ↔ C3 — `counts[activity_type]` ต้องเท่ากับฟิลด์นี้ของ `/api/me/stats`
#    (สร้างเป็น dict เพื่อให้เทสต์อ่านออกว่า "ข้อไหนคู่กับข้อไหน" ไม่ใช่ list ที่ต้องนับ index)
COUNT_TO_STAT_FIELD = {
    "issue_created": "total_reported",
    "vote_cast": "votes_cast",
    "board_comment_posted": "board_comments_posted",
    "issue_comment_posted": "issue_comments_posted",
}


# ⚠️ asyncpg **ไม่รับ** `str` กับพารามิเตอร์ timestamptz — ต้องเป็น datetime จริง
def _ts(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


@pytest_asyncio.fixture
async def me_world(db_pool, client):
    """ห้องเดียว + ผู้ใช้ 2 คน (`me` = เจ้าของ feed · `other` = ตัวปน)

    ⚠️ รับ `client` เข้ามาโดยเจตนา — บังคับให้ TestClient เปิด app (รัน init_db + migrations)
       จบก่อน แล้วค่อยล้างตาราง (แบบเดียวกับ `me_world` ใน `test_me_stats.py`)

    ⚠️ ล้าง `academic_terms` ให้ว่าง — **จำเป็นต่อเทสต์ A2** เพราะ C3 กรองตามภาค
       แต่ C1 ไม่กรอง ⇒ ถ้ามีภาคปัจจุบันอยู่ สองฝั่งจะนับคนละช่วงแล้วเทสต์ A2 พัง
       (ซึ่งถูกต้องตามดีไซน์ — C1 เป็น all-time โดยเจตนา ดู plan §22.2 ข้อ 2)
    """
    room_code = f"ม.6/{random.randint(1, 90)}"
    async with db_pool.acquire() as conn:
        room_id = await conn.fetchval(
            "INSERT INTO rooms (room_code, room_name, level) VALUES ($1,$2,'ม.6') RETURNING id",
            room_code, room_code,
        )

    users = {"room_id": room_id}
    for label in ("me", "other"):
        sid = f"MA{random.randint(1000, 9999)}{label[:2]}"  # ≤ 10 ตัว (student_id VARCHAR(10))
        uid = await auth_service.register_user(
            db_pool, sid, "1234", f"{label} ทดสอบ", sid, room_code, 1, "student"
        )
        users[label] = {"user_id": uid, "token": auth_service.create_access_token(uid)}

    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM academic_terms")

    return users


def _auth(world, actor="me") -> dict:
    return {"Authorization": f"Bearer {world[actor]['token']}"}


# ── helpers สร้างข้อมูลดิบ (คุม created_at / deleted_at เองได้) ──

async def _issue(db_pool, world, *, title="เรื่องทดสอบ", created_at=None,
                 actor="me", deleted=False) -> int:
    """⚠️ `category` เป็น NOT NULL และ **ไม่มี default** ⇒ ต้องส่งเสมอ"""
    async with db_pool.acquire() as conn:
        return await conn.fetchval(
            """
            INSERT INTO issues
                (room_id, category, title, description, reporter_id,
                 status, created_at, deleted_at)
            VALUES ($1, 'other', $2, 'รายละเอียด', $3, 'pending',
                    COALESCE($4::timestamptz, CURRENT_TIMESTAMP),
                    CASE WHEN $5::boolean THEN NOW() ELSE NULL END)
            RETURNING id
            """,
            world["room_id"], title, world[actor]["user_id"], _ts(created_at), deleted,
        )


async def _board(db_pool, world, *, title="บอร์ดทดสอบ", board_type="vote",
                 created_at=None, actor="me", deleted=False) -> int:
    """สร้างบอร์ด + ตัวเลือก 1 ตัว (`piri_votes.choice_id` เป็น NOT NULL)"""
    async with db_pool.acquire() as conn:
        board_id = await conn.fetchval(
            """
            INSERT INTO piri_boards
                (board_type, title, description, author_id, created_at, deleted_at)
            VALUES ($1, $2, 'รายละเอียด', $3,
                    COALESCE($4::timestamptz, CURRENT_TIMESTAMP),
                    CASE WHEN $5::boolean THEN NOW() ELSE NULL END)
            RETURNING id
            """,
            board_type, title, world[actor]["user_id"], _ts(created_at), deleted,
        )
        await conn.execute(
            "INSERT INTO piri_vote_choices (board_id, choice_text, sort_order) "
            "VALUES ($1, 'ตัวเลือก', 1)",
            board_id,
        )
        return board_id


async def _vote(db_pool, world, board_id, *, created_at=None, actor="me",
                deleted=False) -> int:
    """คืน `piri_votes.id` (= `src_id` ของสาขา vote)"""
    async with db_pool.acquire() as conn:
        choice_id = await conn.fetchval(
            "SELECT id FROM piri_vote_choices WHERE board_id = $1 ORDER BY id LIMIT 1",
            board_id,
        )
        return await conn.fetchval(
            """
            INSERT INTO piri_votes (board_id, choice_id, user_id, created_at, deleted_at)
            VALUES ($1, $2, $3, COALESCE($4::timestamptz, CURRENT_TIMESTAMP),
                    CASE WHEN $5::boolean THEN NOW() ELSE NULL END)
            RETURNING id
            """,
            board_id, choice_id, world[actor]["user_id"], _ts(created_at), deleted,
        )


async def _board_comment(db_pool, world, board_id, *, body="คอมเมนต์บอร์ด",
                         created_at=None, actor="me", deleted=False) -> int:
    async with db_pool.acquire() as conn:
        return await conn.fetchval(
            """
            INSERT INTO piri_board_comments (board_id, user_id, body, created_at, deleted_at)
            VALUES ($1, $2, $3, COALESCE($4::timestamptz, CURRENT_TIMESTAMP),
                    CASE WHEN $5::boolean THEN NOW() ELSE NULL END)
            RETURNING id
            """,
            board_id, world[actor]["user_id"], body, _ts(created_at), deleted,
        )


async def _issue_comment(db_pool, world, issue_id, *, body="คอมเมนต์เรื่อง",
                         created_at=None, actor="me", deleted=False) -> int:
    async with db_pool.acquire() as conn:
        return await conn.fetchval(
            """
            INSERT INTO issue_comments (issue_id, user_id, body, created_at, deleted_at)
            VALUES ($1, $2, $3, COALESCE($4::timestamptz, CURRENT_TIMESTAMP),
                    CASE WHEN $5::boolean THEN NOW() ELSE NULL END)
            RETURNING id
            """,
            issue_id, world[actor]["user_id"], body, _ts(created_at), deleted,
        )


def _fetch(client, world, actor="me", **params):
    r = client.get("/api/me/activity", headers=_auth(world, actor), params=params)
    assert r.status_code == 200, r.text
    return r.json()


# ════════════════════════════════════════════════════════════
# 1) รูปร่างของ response — ครบ 4 ประเภท
# ════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_all_four_activity_types_appear(client, db_pool, me_world):
    """A1 — 4 ประเภท × อย่างละ 1 ⇒ ได้ 4 items เรียงใหม่ → เก่า"""
    issue_id = await _issue(db_pool, me_world, title="เรื่องของฉัน",
                            created_at="2026-05-10 09:00:00+07")
    board_id = await _board(db_pool, me_world, title="บอร์ดของฉัน",
                            created_at="2026-05-11 09:00:00+07")
    await _vote(db_pool, me_world, board_id, created_at="2026-05-12 09:00:00+07")
    await _board_comment(db_pool, me_world, board_id, body="คอมเมนต์บอร์ดของฉัน",
                         created_at="2026-05-13 09:00:00+07")
    await _issue_comment(db_pool, me_world, issue_id, body="คอมเมนต์เรื่องของฉัน",
                         created_at="2026-05-14 09:00:00+07")

    body = _fetch(client, me_world)

    assert body["total"] == 4
    assert {i["activity_type"] for i in body["items"]} == set(ACTIVITY_TYPES)
    # เรียงใหม่ → เก่า (คอมเมนต์เรื่อง 14 พ.ค. มาก่อน)
    assert [i["activity_type"] for i in body["items"]] == [
        "issue_comment_posted",
        "board_comment_posted",
        "vote_cast",
        "issue_created",
    ]


@pytest.mark.asyncio
async def test_counts_and_envelope_shape(client, db_pool, me_world):
    """A1ข — envelope ครบ + `counts` มีครบ 4 คีย์เสมอ (zero-fill)"""
    await _issue(db_pool, me_world)
    await _issue(db_pool, me_world)

    body = _fetch(client, me_world)

    assert set(body.keys()) == {"items", "total", "page", "page_size", "pages", "counts"}
    assert body["page"] == 1
    assert body["page_size"] == 20
    # ⚠️ ประเภทที่ไม่มีข้อมูลต้องได้ 0 **ไม่ใช่หายไปจาก dict** — ไม่งั้นป้ายตัวกรองฝั่ง FE จะพัง
    assert set(body["counts"].keys()) == set(ACTIVITY_TYPES)
    assert body["counts"]["issue_created"] == 2
    assert body["counts"]["vote_cast"] == 0


@pytest.mark.asyncio
async def test_title_and_excerpt_come_from_source(client, db_pool, me_world):
    """A1ค — `title` คือชื่อต้นทางจริง · `excerpt` คือเนื้อคอมเมนต์"""
    board_id = await _board(db_pool, me_world, title="บอร์ดชื่อเฉพาะ")
    await _board_comment(db_pool, me_world, board_id, body="เนื้อความคอมเมนต์")

    body = _fetch(client, me_world, activity_type="board_comment_posted")

    assert body["items"][0]["title"] == "บอร์ดชื่อเฉพาะ"
    assert body["items"][0]["excerpt"] == "เนื้อความคอมเมนต์"
    assert body["items"][0]["entity_type"] == "board"
    assert body["items"][0]["entity_id"] == board_id


# ════════════════════════════════════════════════════════════
# 2) ★ สัญญากับ C3 — หัวใจของงานนี้
# ════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_counts_match_personal_stats_field_by_field(client, db_pool, me_world):
    """A2 — ★ `counts` ต้องตรงกับ `GET /api/me/stats` **ทีละฟิลด์**

    ถ้าเทสต์นี้แตก แปลว่าผู้ใช้จะเห็นเลขบนการ์ดสถิติ (หน้า Profile/Home) ไม่เท่ากับ
    จำนวนแถวในหน้า "กิจกรรมของฉัน" ⇒ อ่านเป็นบั๊กทันที

    ⚠️ ต้องไม่มีภาคปัจจุบัน — `me_world` ล้าง `academic_terms` ให้แล้ว
       (C3 กรองตามภาค · C1 เป็น all-time ⇒ เทียบกันได้เฉพาะตอนที่ C3 = all-time)
    """
    # สร้างของให้ครบทั้ง 4 ประเภท + ของที่ต้องไม่ถูกนับ
    issue_id = await _issue(db_pool, me_world)
    await _issue(db_pool, me_world, deleted=True)          # soft-deleted ⇒ ไม่นับทั้งสองฝั่ง
    board_id = await _board(db_pool, me_world)
    await _vote(db_pool, me_world, board_id)
    await _board_comment(db_pool, me_world, board_id)
    await _board_comment(db_pool, me_world, board_id)
    await _issue_comment(db_pool, me_world, issue_id)
    await _issue_comment(db_pool, me_world, issue_id, deleted=True)   # soft-deleted ⇒ ไม่นับ

    # ของคนอื่น — ต้องไม่โผล่ในทั้งสองฝั่ง
    other_issue = await _issue(db_pool, me_world, actor="other")
    await _board_comment(db_pool, me_world, board_id, actor="other")
    await _issue_comment(db_pool, me_world, other_issue, actor="other")

    counts = _fetch(client, me_world)["counts"]

    r = client.get("/api/me/stats", headers=_auth(me_world))
    assert r.status_code == 200, r.text
    stats = r.json()

    assert stats["term"] is None, "ต้องไม่มีภาคปัจจุบัน ไม่งั้นเทียบกันไม่ได้"
    for activity_type, stat_field in COUNT_TO_STAT_FIELD.items():
        assert counts[activity_type] == stats[stat_field], (
            f"{activity_type} ({counts[activity_type]}) "
            f"!= stats.{stat_field} ({stats[stat_field]})"
        )

    # ค่าที่คาดไว้จริง (กันเทสต์ที่ผ่านเพราะทั้งสองฝั่งเป็น 0 ตรงกัน)
    assert counts == {
        "issue_created": 1,
        "vote_cast": 1,
        "board_comment_posted": 2,
        "issue_comment_posted": 1,
    }


# ════════════════════════════════════════════════════════════
# 3) ความทนของ join — ต้นทางถูกลบ
# ════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_vote_survives_soft_deleted_board(client, db_pool, me_world):
    """A3 — ★ บอร์ดถูกลบ (soft) ⇒ **โหวตยังอยู่ใน feed** + `is_deleted_source = true`

    ถ้าใช้ INNER JOIN `piri_boards` แถวนี้จะหายไปเงียบ ๆ ทั้งที่ C3 ยังนับ `votes_cast` อยู่
    (`votes_cast` นับแถวใน `piri_votes` ล้วน ๆ ไม่ join อะไร) ⇒ เลขไม่ตรงกันแบบหาสาเหตุยาก
    """
    board_id = await _board(db_pool, me_world, title="บอร์ดที่จะถูกลบ")
    vote_id = await _vote(db_pool, me_world, board_id)

    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE piri_boards SET deleted_at = NOW() WHERE id = $1", board_id)

    body = _fetch(client, me_world, activity_type="vote_cast")

    assert body["total"] == 1
    item = body["items"][0]
    assert item["src_id"] == vote_id
    assert item["entity_id"] == board_id
    assert item["is_deleted_source"] is True
    # ★ title **ยังเป็นชื่อจริง** ไม่ถูกแทนด้วย placeholder — ตรงกับ C2 `test_bookmarks.py::B6`
    #   แนวเดียวกันทั้งรอบ: แถวอยู่ต่อ + `is_deleted_source` เป็นตัวบอกสถานะ
    #   ส่วนจะแสดงอย่างไรเป็นเรื่องของ frontend (หรี่สี/ตัดลิงก์) ไม่ใช่ให้ backend ลบข้อมูลทิ้ง
    assert item["title"] == "บอร์ดที่จะถูกลบ"

    # ★ และ C3 ยังนับโหวตนั้นอยู่ ⇒ ต้องไม่กรอง `deleted_at` ของ *บอร์ด* ในสาขานี้
    stats = client.get("/api/me/stats", headers=_auth(me_world)).json()
    assert stats["votes_cast"] == 1


@pytest.mark.asyncio
async def test_vote_survives_soft_deleted_choice(client, db_pool, me_world):
    """A3ข — ★ `piri_vote_choices` **มี `deleted_at` ของตัวเอง** ⇒ ต้อง LEFT JOIN เช่นกัน

    ถ้า INNER JOIN ตัวเลือก โหวตนั้นจะหายจาก feed ทั้งที่ C3 ยังนับ
    (ของจริงในสคีมา — เจอตอนตรวจ `init_db.py` ไม่ใช่ตอนอ่านแผน)
    """
    board_id = await _board(db_pool, me_world)
    vote_id = await _vote(db_pool, me_world, board_id)

    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE piri_vote_choices SET deleted_at = NOW() WHERE board_id = $1", board_id
        )

    body = _fetch(client, me_world, activity_type="vote_cast")

    assert body["total"] == 1
    assert body["items"][0]["src_id"] == vote_id
    # ★ ข้อความตัวเลือก **ยังอยู่** — `meta` เป็น None เฉพาะเมื่อตัวเลือกหายไปจริง (hard delete)
    #   หลักเดียวกับ B6/A3: เก็บค่าจริงไว้ + ให้ธงบอกสถานะ ดีกว่าลบข้อมูลทิ้ง
    assert body["items"][0]["meta"] == "ตัวเลือก"
    assert body["items"][0]["is_deleted_source"] is False   # บอร์ดยังอยู่ ไม่ใช่ถูกลบ


@pytest.mark.asyncio
async def test_vote_survives_hidden_board(client, db_pool, me_world):
    """A3ค — ★ บอร์ดที่ถูก **ซ่อน** (`status = 'hidden'`) ต้องติดธงเหมือนถูกลบ

    ⚠️ **บอร์ด "เปิดไม่ได้" มีสองทาง และอยู่คนละคอลัมน์:**
      · `deleted_at IS NOT NULL` → ลบแบบ soft
      · `status = 'hidden'`      → สภา/แอดมินกด "ซ่อนบอร์ด" (`board_moderation_service.hide_board`)
    และ `board_service.get_board_detail()` **404 ทั้งสองทาง** (ตัวหลังเขียนกำกับไว้ว่า
    "เหมือนซอฟต์ดีลีต") ⇒ ถ้าเช็คแค่ `deleted_at` แถวนี้จะยังเป็น **ลิงก์ที่กดได้**
    แล้วพาผู้ใช้ไป 404 ตรง ๆ — เป็นอาการที่ผู้ใช้เจอทันทีและอ่านว่าเป็นบั๊ก

    ⚠️ **A3 จับกับดักนี้ไม่ได้** เพราะ A3 ตั้ง `deleted_at` ด้วย SQL ตรง ๆ
       ไม่ได้เดินผ่านเส้นทางที่ผู้ใช้ใช้จริง (`hideBoard()` → `status = 'hidden'`)
    """
    board_id = await _board(db_pool, me_world, title="บอร์ดที่จะถูกซ่อน")
    vote_id = await _vote(db_pool, me_world, board_id)

    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE piri_boards SET status = 'hidden' WHERE id = $1", board_id)

    body = _fetch(client, me_world, activity_type="vote_cast")

    assert body["total"] == 1
    assert body["items"][0]["src_id"] == vote_id
    assert body["items"][0]["is_deleted_source"] is True
    assert body["items"][0]["title"] == "บอร์ดที่จะถูกซ่อน"   # เก็บชื่อจริงไว้เหมือน A3


@pytest.mark.asyncio
async def test_closed_board_is_not_flagged_as_deleted(client, db_pool, me_world):
    """A3ง — ★ ด่านกันแก้เกิน: บอร์ดที่ **ปิด** (`status = 'closed'`) ต้อง **ไม่** ติดธง

    `get_board_detail()` **ไม่** 404 ให้ `'closed'` ⇒ ผู้ใช้กดเข้าไปดูได้จริง
    ⇒ ถ้าเผลอเขียนเงื่อนไขเป็น `status <> 'active'` เทสต์นี้จะล้ม (ลิงก์ถูกตัดทิ้งโดยไม่จำเป็น)
    ⇒ เงื่อนไขที่ถูกคือ `status = 'hidden'` เท่านั้น — ตรงกับที่ `get_board_detail` ใช้จริง
    """
    board_id = await _board(db_pool, me_world)
    await _vote(db_pool, me_world, board_id)

    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE piri_boards SET status = 'closed' WHERE id = $1", board_id)

    body = _fetch(client, me_world, activity_type="vote_cast")
    assert body["total"] == 1
    assert body["items"][0]["is_deleted_source"] is False


@pytest.mark.asyncio
async def test_issue_created_disappears_when_issue_soft_deleted(client, db_pool, me_world):
    """A4 — ★ เรื่องที่ถูกลบ ⇒ `issue_created` **ต้องไม่ถูกนับ** (ตรงกับ `total_reported`)

    ต่างจากคอมเมนต์โดยเจตนา: "เรื่องที่ฉันแจ้ง" ที่ถูกลบไม่ใช่ของฉันอีกแล้ว
    แต่คอมเมนต์ที่ฉันเขียนยังเป็นของฉัน แม้เรื่องแม่จะถูกซ่อน
    """
    await _issue(db_pool, me_world, deleted=True)
    await _issue(db_pool, me_world)

    body = _fetch(client, me_world, activity_type="issue_created")
    assert body["total"] == 1

    counts = _fetch(client, me_world)["counts"]
    stats = client.get("/api/me/stats", headers=_auth(me_world)).json()
    assert counts["issue_created"] == 1 == stats["total_reported"]


@pytest.mark.asyncio
async def test_issue_comment_survives_soft_deleted_issue(client, db_pool, me_world):
    """A4ข — คอมเมนต์ในเรื่องที่ถูกลบ **ยังอยู่ใน feed** + ติดธง `is_deleted_source`"""
    issue_id = await _issue(db_pool, me_world)
    comment_id = await _issue_comment(db_pool, me_world, issue_id, body="คอมเมนต์ของฉัน")

    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE issues SET deleted_at = NOW() WHERE id = $1", issue_id)

    body = _fetch(client, me_world, activity_type="issue_comment_posted")

    assert body["total"] == 1
    assert body["items"][0]["src_id"] == comment_id
    assert body["items"][0]["is_deleted_source"] is True

    # ★ แต่ `issue_created` ของเรื่องเดียวกันหายไปแล้ว (A4)
    assert _fetch(client, me_world)["counts"]["issue_created"] == 0


@pytest.mark.asyncio
async def test_soft_deleted_comments_are_excluded(client, db_pool, me_world):
    """A4ค — คอมเมนต์/โหวตที่ตัวเองถูกลบ ⇒ ไม่นับ (ตรงกับ `deleted_at IS NULL` ของ C3)"""
    board_id = await _board(db_pool, me_world)
    issue_id = await _issue(db_pool, me_world)
    await _vote(db_pool, me_world, board_id, deleted=True)
    await _board_comment(db_pool, me_world, board_id, deleted=True)
    await _issue_comment(db_pool, me_world, issue_id, deleted=True)

    counts = _fetch(client, me_world)["counts"]
    stats = client.get("/api/me/stats", headers=_auth(me_world)).json()

    assert counts["vote_cast"] == 0 == stats["votes_cast"]
    assert counts["board_comment_posted"] == 0 == stats["board_comments_posted"]
    assert counts["issue_comment_posted"] == 0 == stats["issue_comments_posted"]


# ════════════════════════════════════════════════════════════
# 4) แยกของตัวเองออกจากของคนอื่น
# ════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_other_users_activity_is_not_visible(client, db_pool, me_world):
    """A5 — กิจกรรมของคนอื่นต้องไม่โผล่ (และ `counts` ต้องไม่นับ)"""
    board_id = await _board(db_pool, me_world, actor="other")
    other_issue = await _issue(db_pool, me_world, actor="other")
    await _vote(db_pool, me_world, board_id, actor="other")
    await _board_comment(db_pool, me_world, board_id, actor="other")
    await _issue_comment(db_pool, me_world, other_issue, actor="other")

    body = _fetch(client, me_world)
    assert body["items"] == []
    assert body["total"] == 0
    assert all(v == 0 for v in body["counts"].values())

    # และคนอื่นมองเห็นของตัวเอง (พิสูจน์ว่าไม่ใช่เพราะข้อมูลไม่ได้ถูกสร้าง)
    other_body = _fetch(client, me_world, actor="other")
    assert other_body["total"] == 4


@pytest.mark.asyncio
async def test_activity_is_not_leaked_by_query_param(client, db_pool, me_world):
    """A5ข — ★ ส่ง `user_id` ของคนอื่นมาใน query ต้องถูก **เพิกเฉย** (เอาจาก JWT เท่านั้น)

    FastAPI จะทิ้ง query param ที่ไม่ได้ประกาศ ⇒ ต้องไม่มีทางที่ค่าจากผู้ใช้จะกลายเป็นตัวตน
    """
    await _issue(db_pool, me_world, actor="other")
    await _issue(db_pool, me_world)

    body = _fetch(client, me_world, user_id=me_world["other"]["user_id"])

    assert body["total"] == 1        # ยังเห็นแค่ของตัวเอง
    assert body["counts"]["issue_created"] == 1


# ════════════════════════════════════════════════════════════
# 5) ตัวกรอง + pagination
# ════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_filter_by_activity_type(client, db_pool, me_world):
    """A7 — กรอง `vote_cast` ⇒ ได้เฉพาะโหวต และ `total` = จำนวนโหวต (ไม่ใช่ยอดรวม)"""
    # ⚠️ **คนเดียวกันโหวตบอร์ดเดียวกัน 2 ครั้งไม่ได้** — `uq_piri_votes_board_user_active`
    #    เป็น unique `(board_id, user_id) WHERE deleted_at IS NULL` ⇒ ต้องใช้ 2 บอร์ด
    #    (เดิมเทสต์นี้เรียก `_vote` บอร์ดเดิมซ้ำ ⇒ `UniqueViolationError` ซึ่งเป็นความผิดของเทสต์)
    board_a = await _board(db_pool, me_world)
    board_b = await _board(db_pool, me_world)
    await _vote(db_pool, me_world, board_a)
    await _vote(db_pool, me_world, board_b)
    await _issue(db_pool, me_world)

    body = _fetch(client, me_world, activity_type="vote_cast")

    assert body["total"] == 2
    assert [i["activity_type"] for i in body["items"]] == ["vote_cast", "vote_cast"]
    # ⚠️ `counts` ต้องเป็นยอดของ **ทุกประเภท** เสมอ ไม่ใช่ยอดของตัวที่กรองอยู่
    #    ไม่งั้นป้ายตัวกรองจะโชว์ 0 ให้ทุกแท็บที่ไม่ได้เลือก
    assert body["counts"]["issue_created"] == 1
    assert body["counts"]["vote_cast"] == 2


@pytest.mark.asyncio
async def test_filter_unknown_type_returns_422(client, me_world):
    """A6 — `activity_type` นอกลิสต์ ⇒ 422 จาก `Literal` (ไม่ใช่ 500 และไม่ใช่ 200 เปล่า)"""
    r = client.get(
        "/api/me/activity", headers=_auth(me_world), params={"activity_type": "hacked"}
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_pagination_is_stable_with_identical_timestamps(client, db_pool, me_world):
    """A8 — ★ 5 แถวที่ `created_at` **เท่ากันเป๊ะ** · limit=2 ⇒ 3 หน้า ไม่มีแถวซ้ำ/หาย

    `CURRENT_TIMESTAMP` คือเวลา **เริ่มทรานแซกชัน** ไม่ใช่เวลาที่แถวถูกเขียน
    ⇒ แถวที่ insert ในทรานแซกชันเดียวกัน (หรือในเทสต์นี้ที่ส่งค่าเดียวกัน) มี `created_at` เท่ากัน
    ถ้า `ORDER BY created_at DESC` อย่างเดียว ลำดับจะแล้วแต่ดวง ⇒ pagination พัง
    tie-break ที่ถูกคือ `activity_type, src_id DESC`
    """
    issue_id = await _issue(db_pool, me_world)
    same_moment = "2026-05-20 12:00:00+07"
    ids = [
        await _issue_comment(db_pool, me_world, issue_id, created_at=same_moment)
        for _ in range(5)
    ]

    seen: list[int] = []
    for page in (1, 2, 3):
        body = _fetch(
            client, me_world, activity_type="issue_comment_posted", limit=2, offset=(page - 1) * 2
        )
        assert body["page"] == page
        assert body["page_size"] == 2
        assert body["total"] == 5
        assert body["pages"] == 3
        seen.extend(i["src_id"] for i in body["items"])

    assert len(seen) == 5
    assert sorted(seen) == sorted(ids)      # ทุกแถวมา 1 ครั้งพอดี — ไม่ซ้ำ ไม่หาย


@pytest.mark.asyncio
async def test_last_page_may_be_short(client, db_pool, me_world):
    """A8ข — หน้าสุดท้ายที่มีของไม่เต็มหน้า ต้องได้เท่าที่มี (ไม่ error)"""
    issue_id = await _issue(db_pool, me_world)
    for _ in range(3):
        await _issue_comment(db_pool, me_world, issue_id)

    # ⚠️ ต้องกรอง `issue_comment_posted` — `_issue()` เองก็สร้างแถว `issue_created`
    #    ⇒ ถ้าไม่กรองจะได้ 4 แถว (3 คอมเมนต์ + 1 เรื่อง) แล้วหน้าสุดท้ายเต็มพอดี
    #    = ไม่ได้ทดสอบเคส "หน้าสุดท้ายสั้น" ตามชื่อเทสต์เลย
    body = _fetch(client, me_world, activity_type="issue_comment_posted", limit=2, offset=2)
    assert len(body["items"]) == 1
    assert body["total"] == 3
    assert body["pages"] == 2


# ════════════════════════════════════════════════════════════
# 6) `excerpt` — ตัดที่ SQL
# ════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_excerpt_is_truncated_at_160_characters(client, db_pool, me_world):
    """A9 — ★ ตัดที่ **160 ตัวอักษร** ไม่ใช่ 160 byte (ภาษาไทย 1 ตัว = 3 byte)

    ถ้าใช้ `LEFT(body, 160)` ผิดฝั่ง (เช่นตัดใน Python ด้วย `body[:160]` ก็ได้ผลเท่ากัน
    แต่ถ้าไปตัดด้วย byte หรือ `substring` ที่นับ byte จะได้ครึ่งตัวอักษร = ตัวอักษรเสีย)
    """
    board_id = await _board(db_pool, me_world)
    await _board_comment(db_pool, me_world, board_id, body="ก" * 200)

    body = _fetch(client, me_world, activity_type="board_comment_posted")
    excerpt = body["items"][0]["excerpt"]

    assert len(excerpt) == 160
    assert excerpt == "ก" * 160          # ไม่มีตัวอักษรเสียปนท้าย


@pytest.mark.asyncio
async def test_short_body_is_not_padded_or_cut(client, db_pool, me_world):
    """A9ข — ข้อความสั้นกว่า 160 ต้องได้มาครบ ไม่ถูกตัด/ไม่ถูกเติม"""
    board_id = await _board(db_pool, me_world)
    await _board_comment(db_pool, me_world, board_id, body="สั้น ๆ")

    body = _fetch(client, me_world, activity_type="board_comment_posted")
    assert body["items"][0]["excerpt"] == "สั้น ๆ"


# ════════════════════════════════════════════════════════════
# 7) ความปลอดภัย + สภาพตั้งต้น
# ════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_api_key_is_rejected_with_401(client, me_world):
    """A10 — ⚠️ `X-API-Key` ต้องได้ **401 ไม่ใช่ 500** และไม่ใช่ 200 ที่นับของ user_id = NULL"""
    r = client.get("/api/me/activity", headers={"X-API-Key": "test-api-key"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_requires_authentication(client, me_world):
    r = client.get("/api/me/activity")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_empty_activity_returns_zeros_not_null(client, me_world):
    """A11 — ผู้ใช้ใหม่ที่ไม่มีข้อมูลเลย ⇒ ลิสต์ว่าง + 0 ครบ ไม่ใช่ null/500"""
    body = _fetch(client, me_world)

    assert body["items"] == []
    assert body["total"] == 0
    assert body["pages"] == 0
    assert body["counts"] == {t: 0 for t in ACTIVITY_TYPES}


@pytest.mark.asyncio
async def test_page_size_boundaries(client, me_world):
    """A11ข — `limit` นอกช่วง ⇒ 422 (กันดึงทั้งตารางทีเดียว)"""
    for bad in (0, -1, 101):
        r = client.get("/api/me/activity", headers=_auth(me_world), params={"limit": bad})
        assert r.status_code == 422, f"limit={bad} ควรได้ 422"

    r = client.get("/api/me/activity", headers=_auth(me_world), params={"offset": -1})
    assert r.status_code == 422


# ════════════════════════════════════════════════════════════
# 8) service layer ตรง ๆ
# ════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_service_returns_dict_shape(db_pool, me_world):
    """A12 — เรียก service ตรง ๆ (ไม่ผ่าน HTTP) ⇒ รูปเดียวกัน

    กันไม่ให้มีตรรกะ envelope ไปซ่อนอยู่ใน router จนเทสต์ HTTP ผ่านแต่ B1 เรียกใช้ไม่ได้
    """
    from services import me_service

    await _issue(db_pool, me_world)

    result = await me_service.get_my_activity(db_pool, me_world["me"]["user_id"])

    assert set(result.keys()) == {"items", "total", "page", "page_size", "pages", "counts"}
    assert result["total"] == 1
    assert result["counts"]["issue_created"] == 1


def test_activity_types_match_schema_field_names():
    """A13 — ★ ด่านกัน drift: `ACTIVITY_TYPES` (service) ต้องตรงกับฟิลด์ของ `ActivityCountsOut`

    ⚠️ ชุดนี้ถูกประกาศ **2 ที่** โดยตั้งใจ — service ต้องรู้ว่าจะ `GROUP BY` อะไร
       และ schema ต้องประกาศฟิลด์ให้ pydantic validate ⇒ ถ้าเพิ่มประเภทที่ 5 แล้วแก้ที่เดียว
       อีกที่จะเงียบ (pydantic v2 ทิ้งคีย์เกินให้เอง) ⇒ badge ฝั่ง frontend จะเป็น `undefined`
       เทสต์นี้ทำให้ความเงียบนั้นกลายเป็นความล้มเหลวที่อ่านออก
    """
    from models.me_schemas import ActivityCountsOut
    from services import me_service

    assert set(me_service.ACTIVITY_TYPES) == set(ACTIVITY_TYPES), (
        "ACTIVITY_TYPES ใน service ไม่ตรงกับที่เทสต์นี้รู้จัก — แก้ทั้งสองฝั่ง"
    )
    assert set(ActivityCountsOut.model_fields) == set(me_service.ACTIVITY_TYPES), (
        "ฟิลด์ของ ActivityCountsOut กับ ACTIVITY_TYPES ไม่ตรงกัน — เพิ่ม/ลบต้องแก้ทั้งคู่"
    )


def test_count_to_stat_field_map_covers_every_activity_type():
    """A13ข — สะพาน C1↔C3 ต้องครอบ **ทุก** ประเภท และชี้ไปฟิลด์ที่มีจริงของ C3

    ถ้ามีประเภทที่ไม่มีคู่ เทสต์ A2 จะเงียบ ๆ ข้ามมันไป (วนตาม dict) ⇒ สัญญาก็ขาดครึ่ง
    และถ้าชื่อฟิลด์ฝั่ง C3 ถูกเปลี่ยน A2 จะพังด้วย `KeyError` ที่อ่านไม่ออกว่าเกิดจากอะไร
    ⇒ ตรวจชื่อฟิลด์กับ `PersonalStatsOut` ตรงนี้ เพื่อให้ข้อความพังบอกสาเหตุ
    """
    from models.me_schemas import PersonalStatsOut

    assert set(COUNT_TO_STAT_FIELD) == set(ACTIVITY_TYPES)

    stat_fields = set(PersonalStatsOut.model_fields) - {"term"}
    assert set(COUNT_TO_STAT_FIELD.values()) <= stat_fields, (
        f"ชี้ไปฟิลด์ที่ C3 ไม่มี: {set(COUNT_TO_STAT_FIELD.values()) - stat_fields}"
    )

    # `resolved_count` / `in_progress_count` เป็นสถานะของเรื่อง ไม่ใช่ "กิจกรรม"
    # ⇒ ไม่มีคู่ใน C1 โดยเจตนา (C1 ไม่ได้แยกแยะสถานะ) — ถ้ามีคนเพิ่มคู่ให้สองตัวนี้
    # แปลว่ากำลังเปลี่ยนความหมายของ counts ต้องรู้ตัว
    assert stat_fields - set(COUNT_TO_STAT_FIELD.values()) == {
        "resolved_count",
        "in_progress_count",
    }
