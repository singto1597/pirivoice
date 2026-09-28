"""
📊 สถิติส่วนตัว (C3) — GET /api/me/stats
=========================================
ทดสอบ 4 ระดับ:
  1) HTTP — 401 (X-API-Key) · ตัวเลขครบ 6 ตัว
  2) Deep-DB — ตัวเลขตรงกับ COUNT(*) จริง (ไม่เชื่อ response)
  3) **เขตเวลา** — หัวใจของงานนี้: created_at (timestamptz) เทียบกับ start/end_date (date)
     ต้องตีความเป็นเที่ยงคืน **Asia/Bangkok** และ end_date เป็น inclusive
     ถ้าเขียนเทียบ date ตรง ๆ แถวที่ 00:30 น. ไทยของวันแรก และ 23:30 น. ไทยของวันสุดท้าย
     จะหลุดทั้งคู่ (และแถวหลังวันสุดท้ายจะถูกนับเข้ามาแทน)
  4) Fallback — ไม่มีภาคปัจจุบัน ⇒ นับทั้งหมด + `term: null` (ห้ามเงียบ ๆ โชว์เลขดูเหมือนเลขภาค)

ตาม docs/rules/testing.md: ตรวจ DB ตรง ๆ ผ่าน db_pool
"""
import random
from datetime import date, datetime

import pytest
import pytest_asyncio

from services import auth_service, term_service

# ภาคทดสอบ: 16 พ.ค. 2569 – 10 ต.ค. 2569
TERM_START = "2026-05-16"
TERM_END = "2026-10-10"


# ⚠️ asyncpg **ไม่รับ** `str` กับพารามิเตอร์ timestamptz/date — ต้องเป็น datetime/date จริง
#    (เขียนเป็น string ในเทสเพราะอ่านง่ายกว่า โดยเฉพาะ offset +07 ที่เป็นหัวใจของเทสเขตเวลา)
def _ts(value: str | None) -> datetime | None:
    """'2026-05-16 00:30:00+07' → datetime แบบ tz-aware"""
    return datetime.fromisoformat(value) if value else None


def _d(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


@pytest_asyncio.fixture
async def me_world(db_pool, client):
    """
    โลกทดสอบ: ห้องเดียว + ผู้ใช้ 2 คน

      - `me`    → เจ้าของสถิติ (คนที่ยิง /api/me/stats)
      - `other` → คนอื่น (มีข้อมูลของตัวเอง เพื่อพิสูจน์ว่าไม่ปนกัน)

    ⚠️ รับ `client` เข้ามาโดยเจตนา — บังคับให้ TestClient เปิด app (รัน init_db + migrations)
       จบก่อน จึงค่อยล้างตาราง (แบบเดียวกับ term_world / announcement_world)
    """
    room_code = f"ม.6/{random.randint(1, 90)}"
    async with db_pool.acquire() as conn:
        room_id = await conn.fetchval(
            "INSERT INTO rooms (room_code, room_name, level) VALUES ($1,$2,'ม.6') RETURNING id",
            room_code, room_code,
        )

    users = {"room_id": room_id}
    for label in ("me", "other"):
        sid = f"MS{random.randint(1000, 9999)}{label[:2]}"  # ≤ 10 ตัว (student_id VARCHAR(10))
        uid = await auth_service.register_user(
            db_pool, sid, "1234", f"{label} ทดสอบ", sid, room_code, 1, "student"
        )
        users[label] = {"user_id": uid, "token": auth_service.create_access_token(uid)}

    # เริ่มจากศูนย์ — ไม่มีภาคปัจจุบัน (สถานะตั้งต้นจริงของระบบ)
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM academic_terms")

    return users


def _auth(world, actor="me") -> dict:
    return {"Authorization": f"Bearer {world[actor]['token']}"}


# ── helpers สร้างข้อมูลดิบ (deep insert เพื่อคุม created_at ได้เอง) ──

async def _issue(db_pool, world, *, status="pending", created_at=None, actor="me",
                 deleted=False) -> int:
    """สร้างเรื่อง 1 ใบ — created_at รับ timestamptz literal เช่น '2026-05-16 00:30:00+07'"""
    async with db_pool.acquire() as conn:
        return await conn.fetchval(
            """
            INSERT INTO issues
                (room_id, category, title, description, reporter_id,
                 status, created_at, deleted_at)
            VALUES ($1, 'other', 'เรื่องทดสอบ', 'รายละเอียด',
                    $2, $3,
                    COALESCE($4::timestamptz, CURRENT_TIMESTAMP),
                    CASE WHEN $5::boolean THEN NOW() ELSE NULL END)
            RETURNING id
            """,
            world["room_id"], world[actor]["user_id"], status, _ts(created_at), deleted,
        )


async def _board(db_pool, world, *, created_at=None, actor="me") -> int:
    """สร้าง board แบบ vote + ตัวเลือก 1 ตัว (piri_votes.choice_id เป็น NOT NULL)"""
    async with db_pool.acquire() as conn:
        board_id = await conn.fetchval(
            """
            INSERT INTO piri_boards (board_type, title, description, author_id, created_at)
            VALUES ('vote', 'บอร์ดทดสอบ', 'รายละเอียด', $1,
                    COALESCE($2::timestamptz, CURRENT_TIMESTAMP))
            RETURNING id
            """,
            world[actor]["user_id"], _ts(created_at),
        )
        await conn.execute(
            "INSERT INTO piri_vote_choices (board_id, choice_text, sort_order) VALUES ($1, 'ตัวเลือก', 1)",
            board_id,
        )
        return board_id


async def _vote(db_pool, world, board_id, *, created_at=None, actor="me", deleted=False):
    async with db_pool.acquire() as conn:
        choice_id = await conn.fetchval(
            "SELECT id FROM piri_vote_choices WHERE board_id = $1 ORDER BY id LIMIT 1", board_id
        )
        await conn.execute(
            """
            INSERT INTO piri_votes (board_id, choice_id, user_id, created_at, deleted_at)
            VALUES ($1, $2, $3, COALESCE($4::timestamptz, CURRENT_TIMESTAMP),
                    CASE WHEN $5::boolean THEN NOW() ELSE NULL END)
            """,
            board_id, choice_id, world[actor]["user_id"], _ts(created_at), deleted,
        )


async def _board_comment(db_pool, world, board_id, *, created_at=None, actor="me",
                         deleted=False):
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO piri_board_comments (board_id, user_id, body, created_at, deleted_at)
            VALUES ($1, $2, 'คอมเมนต์', COALESCE($3::timestamptz, CURRENT_TIMESTAMP),
                    CASE WHEN $4::boolean THEN NOW() ELSE NULL END)
            """,
            board_id, world[actor]["user_id"], _ts(created_at), deleted,
        )


async def _issue_comment(db_pool, world, issue_id, *, created_at=None, actor="me",
                         deleted=False):
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO issue_comments (issue_id, user_id, body, created_at, deleted_at)
            VALUES ($1, $2, 'คอมเมนต์', COALESCE($3::timestamptz, CURRENT_TIMESTAMP),
                    CASE WHEN $4::boolean THEN NOW() ELSE NULL END)
            """,
            issue_id, world[actor]["user_id"], _ts(created_at), deleted,
        )


async def _set_term(db_pool, *, start=TERM_START, end=TERM_END, name="ภาคเรียนที่ 1/2569"):
    """ตั้งภาคปัจจุบันตรง ๆ (T1 มีเทส API ครบแล้ว — ที่นี่ต้องการแค่ให้มีภาค)"""
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM academic_terms")
        return await conn.fetchval(
            """
            INSERT INTO academic_terms (name, start_date, end_date, is_current)
            VALUES ($1, $2::date, $3::date, TRUE) RETURNING id
            """,
            name, _d(start), _d(end),
        )


async def _count(db_pool, sql, *params) -> int:
    """COUNT(*) จริงจาก DB — ใช้เทียบกับตัวเลขที่ API คืน"""
    async with db_pool.acquire() as conn:
        return await conn.fetchval(sql, *params)


# ════════════════════════════════════════════════════════════
# 1) ตัวเลข 6 ตัว + deep-DB
# ════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_all_six_counters(db_pool, client, me_world):
    """เรื่อง 3 ใบ (resolved 1 · open 1 · cancelled 1) + โหวต 1 + คอมเมนต์ 2"""
    i1 = await _issue(db_pool, me_world, status="resolved")
    await _issue(db_pool, me_world, status="pending")
    await _issue(db_pool, me_world, status="cancelled")  # นับใน total แต่ไม่ใช่ in_progress

    board = await _board(db_pool, me_world)
    await _vote(db_pool, me_world, board)
    await _board_comment(db_pool, me_world, board)
    await _issue_comment(db_pool, me_world, i1)

    r = client.get("/api/me/stats", headers=_auth(me_world))
    assert r.status_code == 200
    body = r.json()

    assert body["total_reported"] == 3
    assert body["resolved_count"] == 1
    assert body["in_progress_count"] == 1  # pending เท่านั้น — cancelled ไม่นับ
    assert body["votes_cast"] == 1
    assert body["board_comments_posted"] == 1
    assert body["issue_comments_posted"] == 1

    # deep-DB: พิสูจน์ว่าเลขตรงกับของจริงในตาราง
    uid = me_world["me"]["user_id"]
    assert body["total_reported"] == await _count(
        db_pool, "SELECT COUNT(*) FROM issues WHERE reporter_id = $1 AND deleted_at IS NULL", uid
    )
    assert body["votes_cast"] == await _count(
        db_pool, "SELECT COUNT(*) FROM piri_votes WHERE user_id = $1 AND deleted_at IS NULL", uid
    )


@pytest.mark.asyncio
async def test_soft_deleted_rows_are_not_counted(db_pool, client, me_world):
    """แถวที่ soft-delete แล้วต้องไม่ถูกนับ — ทุกตาราง"""
    await _issue(db_pool, me_world, deleted=True)
    board = await _board(db_pool, me_world)
    await _vote(db_pool, me_world, board, deleted=True)
    await _board_comment(db_pool, me_world, board, deleted=True)
    i = await _issue(db_pool, me_world)
    await _issue_comment(db_pool, me_world, i, deleted=True)

    body = client.get("/api/me/stats", headers=_auth(me_world)).json()

    # issue ที่ลบไปแล้วไม่นับ · แต่ i (อันที่คอมเมนต์) ยังอยู่ ⇒ total = 1
    assert body["total_reported"] == 1
    assert body["votes_cast"] == 0
    assert body["board_comments_posted"] == 0
    assert body["issue_comments_posted"] == 0


@pytest.mark.asyncio
async def test_other_users_data_does_not_leak(db_pool, client, me_world):
    """ข้อมูลของคนอื่นต้องไม่โผล่ในสถิติของฉัน"""
    await _issue(db_pool, me_world, actor="other")
    board = await _board(db_pool, me_world, actor="other")
    await _vote(db_pool, me_world, board, actor="other")
    await _board_comment(db_pool, me_world, board, actor="other")

    body = client.get("/api/me/stats", headers=_auth(me_world)).json()

    assert body["total_reported"] == 0
    assert body["votes_cast"] == 0
    assert body["board_comments_posted"] == 0


@pytest.mark.asyncio
async def test_user_without_any_data_returns_zeros(db_pool, client, me_world):
    """ผู้ใช้ใหม่ที่ยังไม่มีอะไรเลย → 0 ทุกช่อง (ไม่ใช่ null และไม่ใช่ 500)"""
    r = client.get("/api/me/stats", headers=_auth(me_world))
    assert r.status_code == 200

    body = r.json()
    for field in (
        "total_reported", "resolved_count", "in_progress_count",
        "votes_cast", "board_comments_posted", "issue_comments_posted",
    ):
        assert body[field] == 0, f"{field} ควรเป็น 0"


# ════════════════════════════════════════════════════════════
# 2) fallback — ยังไม่มีภาคปัจจุบัน
# ════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_no_current_term_counts_everything_and_returns_null_term(db_pool, client, me_world):
    """ไม่มีภาค → นับทั้งหมด และ `term` ต้องเป็น null (UI จะได้เขียนกำกับถูก)"""
    # สร้างย้อนหลังไกล ๆ ก่อนภาคที่จะตั้ง — ถ้าเผลอกรองด้วยภาคอะไรสักอย่างจะไม่ถูกนับ
    await _issue(db_pool, me_world, created_at="2020-01-01 10:00:00+07")
    await _issue(db_pool, me_world)

    body = client.get("/api/me/stats", headers=_auth(me_world)).json()

    assert body["term"] is None
    assert body["total_reported"] == 2


@pytest.mark.asyncio
async def test_term_filter_narrows_the_numbers(db_pool, client, me_world):
    """มีภาค → เรื่องนอกช่วงต้องหลุด และ `term` ต้องส่ง 4 ฟิลด์ที่ UI ใช้"""
    await _set_term(db_pool)
    await _issue(db_pool, me_world, created_at="2026-05-16 10:00:00+07")
    await _issue(db_pool, me_world, created_at="2026-03-01 10:00:00+07")  # ก่อนภาค

    body = client.get("/api/me/stats", headers=_auth(me_world)).json()

    assert body["total_reported"] == 1
    assert body["term"]["name"] == "ภาคเรียนที่ 1/2569"
    assert body["term"]["start_date"] == TERM_START
    assert body["term"]["end_date"] == TERM_END
    assert set(body["term"]) == {"id", "name", "start_date", "end_date"}


@pytest.mark.asyncio
async def test_deleted_current_term_falls_back_to_all_time(db_pool, client, me_world):
    """ภาคปัจจุบันถูกลบ → กลับไปนับทั้งหมด (`fetch_current_term` กรอง deleted_at อยู่แล้ว)"""
    term_id = await _set_term(db_pool)
    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE academic_terms SET deleted_at = NOW(), is_current = FALSE WHERE id = $1",
            term_id,
        )
    await _issue(db_pool, me_world, created_at="2020-01-01 10:00:00+07")

    body = client.get("/api/me/stats", headers=_auth(me_world)).json()

    assert body["term"] is None
    assert body["total_reported"] == 1


# ════════════════════════════════════════════════════════════
# 3) ⚠️ เขตเวลา — หัวใจของงานนี้
# ════════════════════════════════════════════════════════════

@pytest.mark.parametrize(
    "created_at, expected, why",
    [
        # วันแรกของภาค — 00:30 น. ไทย (ยังเป็น 17:30 ของ "เมื่อวาน" ถ้ามองเป็น UTC!)
        ("2026-05-16 00:30:00+07", 1, "วันแรก 00:30 น. ไทย ต้องถูกนับ"),
        # วันสุดท้ายของภาค — 23:30 น. ไทย ⇒ end_date inclusive ต้องนับ
        ("2026-10-10 23:30:00+07", 1, "วันสุดท้าย 23:30 น. ไทย ต้องถูกนับ (inclusive)"),
        # หลังวันสุดท้าย 30 นาที เวลาไทย ⇒ ต้องไม่นับ
        ("2026-10-11 00:30:00+07", 0, "หลังวันสุดท้าย 00:30 น. ไทย ต้องไม่ถูกนับ"),
        # ก่อนวันแรก 30 นาที เวลาไทย ⇒ ต้องไม่นับ
        ("2026-05-15 23:30:00+07", 0, "ก่อนวันแรก 23:30 น. ไทย ต้องไม่ถูกนับ"),
        # เที่ยงคืนตรงของวันแรก (ขอบล่าง) ⇒ นับ
        ("2026-05-16 00:00:00+07", 1, "เที่ยงคืนวันแรก ต้องถูกนับ"),
        # 23:59:59 ของวันสุดท้าย ⇒ นับ
        ("2026-10-10 23:59:59+07", 1, "สิ้นวันสุดท้ายพอดี ต้องถูกนับ"),
        # เที่ยงคืนของวันถัดจากวันสุดท้าย ⇒ ไม่นับ
        ("2026-10-11 00:00:00+07", 0, "เที่ยงคืนหลังวันสุดท้าย ต้องไม่ถูกนับ"),
    ],
)
@pytest.mark.asyncio
async def test_term_boundaries_use_bangkok_midnight(
    db_pool, client, me_world, created_at, expected, why
):
    """⚠️ ถ้าเขียน `created_at >= $2::date` ตรง ๆ เทสนี้จะพังหลายเคส

    โดยเฉพาะ 2 เคสนี้ซึ่งเป็นเหตุผลที่ต้อง `AT TIME ZONE 'Asia/Bangkok'`:
      - '2026-05-16 00:30+07' = '2026-05-15 17:30 UTC' → ถ้า Postgres ตีความเที่ยงคืนเป็น UTC
        แถวนี้จะกลายเป็น "ก่อนภาค" แล้วหลุด
      - '2026-10-10 23:30+07' = '2026-10-10 16:30 UTC' → ต้องนับ (inclusive)
    """
    await _set_term(db_pool)
    await _issue(db_pool, me_world, created_at=created_at)

    body = client.get("/api/me/stats", headers=_auth(me_world)).json()

    assert body["total_reported"] == expected, f"{created_at} — {why}"


@pytest.mark.asyncio
async def test_term_filter_applies_to_votes_and_comments_too(db_pool, client, me_world):
    """การกรองภาคต้องใช้กับทุกตัวนับ ไม่ใช่แค่ issues (คนละ alias/คอลัมน์)"""
    await _set_term(db_pool)
    board = await _board(db_pool, me_world, created_at="2026-06-01 12:00:00+07")
    await _vote(db_pool, me_world, board, created_at="2026-06-01 12:00:00+07")

    # ⚠️ โหวตนอกภาคต้องคนละ board — unique index (board_id, user_id) ห้ามโหวตซ้ำใบเดิม
    other_board = await _board(db_pool, me_world, actor="other")
    await _vote(db_pool, me_world, other_board, created_at="2026-01-01 12:00:00+07")

    await _board_comment(db_pool, me_world, board, created_at="2026-01-01 12:00:00+07")
    issue = await _issue(db_pool, me_world, created_at="2026-06-01 12:00:00+07")
    await _issue_comment(db_pool, me_world, issue, created_at="2026-01-01 12:00:00+07")

    body = client.get("/api/me/stats", headers=_auth(me_world)).json()

    assert body["votes_cast"] == 1
    assert body["board_comments_posted"] == 0
    assert body["issue_comments_posted"] == 0


# ════════════════════════════════════════════════════════════
# 4) auth
# ════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_api_key_is_rejected_with_401(client, me_world):
    """⚠️ X-API-Key ต้องได้ 401 ไม่ใช่ 500 และไม่ใช่ 200 ที่นับของ user_id = NULL"""
    r = client.get("/api/me/stats", headers={"X-API-Key": "test-api-key"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_requires_authentication(client, me_world):
    r = client.get("/api/me/stats")
    assert r.status_code == 401


# ════════════════════════════════════════════════════════════
# 5) service layer ตรง ๆ
# ════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_service_uses_one_connection_for_term_lookup(db_pool, me_world):
    """⚠️ `get_personal_stats` ต้องเรียก `fetch_current_term(conn)` ไม่ใช่ `get_current_term(pool)`

    ถ้าเรียกเวอร์ชัน pool จะ acquire connection ใบที่สองทั้งที่ถืออยู่ ⇒ pool เล็ก = ค้างตาย
    เทสนี้พิสูจน์ทางอ้อมว่าไม่ค้าง (ถ้าค้าง จะ timeout ทั้งชุด) และค่าตรง
    """
    from services import me_service, term_service

    await _set_term(db_pool)
    async with db_pool.acquire() as conn:
        term = await term_service.fetch_current_term(conn)
    assert term is not None

    stats = await me_service.get_personal_stats(db_pool, me_world["me"]["user_id"])
    assert stats["term"]["id"] == term["id"]
    assert set(stats) == {
        "term", "total_reported", "resolved_count", "in_progress_count",
        "votes_cast", "board_comments_posted", "issue_comments_posted",
    }
