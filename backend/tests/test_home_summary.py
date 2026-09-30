"""
🏠 Home รวมทุกอย่าง (B1) — GET /api/home/summary
================================================
ทดสอบ 6 ระดับ:
  1) HTTP — 401 (ไม่ล็อกอิน) · 401 (`X-API-Key` ไม่ใช่ 500) · ไม่รับ `user_id` จาก client
  2) **รอฉันตอบ** — เป้าแคบ: `current_assignee_id = ฉัน` เท่านั้น (ไม่ใช่ involved_cond ตัวกว้าง)
     · เรียง ด่วนก่อน แล้วในความด่วนเดียวกันเอาค้างนานสุดก่อน · total ไม่ถูก LIMIT ตัด
  3) **โหวตที่ยังไม่โหวต** — และบทเรียน skills.md L434: โหวตที่ soft-delete แล้ว
     **ต้องกลับมาโหวตได้** ⇒ บอร์ดต้องกลับเข้าลิสต์ (unique index เป็น partial)
  4) ประกาศ **ไม่ถูกตัด** — เจ้าของระบบสั่ง "โชว์ทั้งหมด" และ PR #31–#33 เพิ่งทำไป
  5) ตัวเลขต้อง **ตรงกับ endpoint เดิม** — `stats` = `/api/me/stats`, `my_issues` = `/api/issues/summary`
     (ถ้าไม่ตรง = มีคนแก้ query เดียวกันแล้วลืมอีกที่ ⇒ หน้าจะโชว์เลขไม่ตรงกัน)
  6) **กิจกรรมใกล้ปิดรับ** (4.5) — ⭐ "ปิดรับ" = `min(วันจัด, กำหนดปิดรับ)` ไม่ใช่
     `registration_deadline` เฉย ๆ ⇒ กิจกรรมที่ **ไม่ตั้งกำหนด** ต้องเข้ามาด้วย

ตาม docs/rules/testing.md: ตรวจ DB ตรง ๆ ผ่าน db_pool
"""
import random
from datetime import datetime

import pytest
import pytest_asyncio

from services import auth_service

QUEUE_LIMIT = 5  # ต้องตรงกับ services/home_service.QUEUE_LIMIT


def _ts(value: str) -> datetime:
    """'2026-05-16 00:30:00+07' → datetime tz-aware (asyncpg ไม่รับ str)"""
    return datetime.fromisoformat(value)


@pytest_asyncio.fixture
async def home_world(db_pool, client):
    """
    โลกทดสอบ: ห้องเดียว + ผู้ใช้ 2 คน

      - `me`    → คนที่เปิดหน้าแรก
      - `other` → คนอื่น (มีงาน/บอร์ดของตัวเอง เพื่อพิสูจน์ว่าไม่ปนกัน)

    ⚠️ รับ `client` เข้ามาโดยเจตนา — บังคับให้ TestClient เปิด app (init_db + migrations)
       จบก่อน จึงค่อยแตะข้อมูล (แบบเดียวกับ me_world)
    """
    room_code = f"ม.5/{random.randint(1, 90)}"
    async with db_pool.acquire() as conn:
        room_id = await conn.fetchval(
            "INSERT INTO rooms (room_code, room_name, level) VALUES ($1,$2,'ม.5') RETURNING id",
            room_code, room_code,
        )

    users = {"room_id": room_id, "room_name": room_code}
    for label in ("me", "other"):
        sid = f"HS{random.randint(1000, 9999)}{label[:2]}"  # ≤ 10 ตัว
        uid = await auth_service.register_user(
            db_pool, sid, "1234", f"{label} ทดสอบ", sid, room_code, 1, "student"
        )
        users[label] = {"user_id": uid, "token": auth_service.create_access_token(uid)}

    return users


def _auth(world, actor="me") -> dict:
    return {"Authorization": f"Bearer {world[actor]['token']}"}


# ── helpers สร้างข้อมูลดิบ (คุม created_at / assignee เองได้) ──

async def _issue(db_pool, world, *, title="เรื่องทดสอบ", assignee=None, status="pending",
                 priority="normal", created_at=None, deleted=False, actor="me") -> int:
    """สร้างเรื่อง 1 ใบ — `assignee` = ชื่อผู้ใช้ใน world หรือ None"""
    assignee_id = world[assignee]["user_id"] if assignee else None
    async with db_pool.acquire() as conn:
        return await conn.fetchval(
            """
            INSERT INTO issues
                (room_id, category, title, description, reporter_id,
                 current_assignee_id, status, priority, created_at, deleted_at)
            VALUES ($1, 'other', $2, 'รายละเอียด', $3,
                    $4, $5, $6, COALESCE($7::timestamptz, CURRENT_TIMESTAMP),
                    CASE WHEN $8::boolean THEN NOW() ELSE NULL END)
            RETURNING id
            """,
            world["room_id"], title, world[actor]["user_id"],
            assignee_id, status, priority, _ts(created_at) if created_at else None, deleted,
        )


async def _board(db_pool, world, *, title="บอร์ดทดสอบ", board_type="vote",
                 status="active", created_at=None, actor="me", deleted=False) -> int:
    """สร้างบอร์ด + ตัวเลือก 1 ตัว (piri_votes.choice_id เป็น NOT NULL ต้องมีตัวเลือก)"""
    async with db_pool.acquire() as conn:
        board_id = await conn.fetchval(
            """
            INSERT INTO piri_boards
                (board_type, title, description, author_id, status, created_at, deleted_at)
            VALUES ($1, $2, 'รายละเอียด', $3, $4,
                    COALESCE($5::timestamptz, CURRENT_TIMESTAMP),
                    CASE WHEN $6::boolean THEN NOW() ELSE NULL END)
            RETURNING id
            """,
            board_type, title, world[actor]["user_id"], status,
            _ts(created_at) if created_at else None, deleted,
        )
        await conn.execute(
            "INSERT INTO piri_vote_choices (board_id, choice_text, sort_order) VALUES ($1,'ตัวเลือก',1)",
            board_id,
        )
        return board_id


async def _vote(db_pool, world, board_id, *, actor="me", deleted=False):
    async with db_pool.acquire() as conn:
        choice_id = await conn.fetchval(
            "SELECT id FROM piri_vote_choices WHERE board_id = $1 ORDER BY id LIMIT 1", board_id
        )
        await conn.execute(
            """
            INSERT INTO piri_votes (board_id, choice_id, user_id, deleted_at)
            VALUES ($1, $2, $3, CASE WHEN $4::boolean THEN NOW() ELSE NULL END)
            """,
            board_id, choice_id, world[actor]["user_id"], deleted,
        )


async def _announce(db_pool, message: str) -> int:
    async with db_pool.acquire() as conn:
        return await conn.fetchval(
            "INSERT INTO announcements (message, priority) VALUES ($1,'normal') RETURNING id",
            message,
        )


def _get(client, world, actor="me", **params):
    return client.get("/api/home/summary", headers=_auth(world, actor), params=params)


# ══════════════════════════════════════════════════════════
# 1) HTTP / auth
# ══════════════════════════════════════════════════════════

def test_unauthenticated_returns_401(client, home_world):
    assert client.get("/api/home/summary").status_code == 401


def test_api_key_returns_401_not_500(client, home_world):
    """`X-API-Key` เป็น system RPC — `get_current_user` คืน user_id = None

    ⚠️ ถ้าไม่มี `_ensure_user()` จะได้ 200 พร้อมคิวว่างเปล่าของ `user_id = NULL`
    (แย่กว่า 500 เพราะเงียบ) ⇒ เทสนี้กันไว้
    """
    from core.config import settings

    r = client.get("/api/home/summary", headers={"X-API-Key": settings.API_KEY})
    assert r.status_code == 401, r.text


@pytest.mark.asyncio
async def test_user_id_param_does_not_switch_identity(db_pool, client, home_world):
    """ห้ามรับ `user_id` จาก client — ส่งของคนอื่นมาก็ต้องยังเห็นของตัวเอง"""
    await _issue(db_pool, home_world, title="ของ other", assignee="other", actor="other")

    r = _get(client, home_world, user_id=home_world["other"]["user_id"])
    assert r.status_code == 200, r.text
    body = r.json()
    # ของ other ไม่ใช่ของฉัน ⇒ ต้องไม่โผล่ แม้จะส่ง user_id มา
    assert body["pending_on_me"] == []
    assert body["pending_on_me_total"] == 0


# ══════════════════════════════════════════════════════════
# 2) รอฉันตอบ
# ══════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_pending_on_me_only_counts_my_assignments(db_pool, client, home_world):
    mine_a = await _issue(db_pool, home_world, title="ของฉัน A", assignee="me")
    mine_b = await _issue(db_pool, home_world, title="ของฉัน B", assignee="me")
    await _issue(db_pool, home_world, title="ของ other", assignee="other", actor="other")
    # ฉันเป็นผู้แจ้งแต่ไม่ใช่ผู้รับ ⇒ ไม่ใช่ "รอฉันตอบ"
    await _issue(db_pool, home_world, title="ฉันแจ้งแต่คนอื่นรับ", assignee="other")

    body = _get(client, home_world).json()
    ids = [i["id"] for i in body["pending_on_me"]]
    assert sorted(ids) == sorted([mine_a, mine_b])
    assert body["pending_on_me_total"] == 2
    assert body["pending_on_me"][0]["room_name"] == home_world["room_name"]


@pytest.mark.asyncio
async def test_pending_on_me_ordering_priority_then_oldest(db_pool, client, home_world):
    """ด่วนก่อนเสมอ แม้สร้างทีหลัง · ความด่วนเดียวกัน → ค้างนานสุดก่อน"""
    old_normal = await _issue(db_pool, home_world, title="normal เก่า", assignee="me",
                              priority="normal", created_at="2026-01-01 09:00:00+07")
    new_normal = await _issue(db_pool, home_world, title="normal ใหม่", assignee="me",
                              priority="normal", created_at="2026-06-01 09:00:00+07")
    urgent_late = await _issue(db_pool, home_world, title="urgent ทีหลัง", assignee="me",
                               priority="urgent", created_at="2026-08-01 09:00:00+07")

    ids = [i["id"] for i in _get(client, home_world).json()["pending_on_me"]]
    assert ids == [urgent_late, old_normal, new_normal]


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["resolved", "cancelled", "rejected"])
async def test_pending_on_me_excludes_finished(db_pool, client, home_world, status):
    await _issue(db_pool, home_world, title="จบแล้ว", assignee="me", status=status)
    assert _get(client, home_world).json()["pending_on_me_total"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["pending", "in_progress", "escalated"])
async def test_pending_on_me_includes_open_statuses(db_pool, client, home_world, status):
    await _issue(db_pool, home_world, title="ยังเปิด", assignee="me", status=status)
    assert _get(client, home_world).json()["pending_on_me_total"] == 1


@pytest.mark.asyncio
async def test_pending_on_me_excludes_soft_deleted(db_pool, client, home_world):
    await _issue(db_pool, home_world, title="ถูกลบ", assignee="me", deleted=True)
    assert _get(client, home_world).json()["pending_on_me_total"] == 0


@pytest.mark.asyncio
async def test_pending_on_me_limit_but_total_is_real_count(db_pool, client, home_world):
    """ลิสต์ตัดที่ QUEUE_LIMIT แต่ `total` ต้องเป็นยอดจริง (ไว้ขึ้น 'และอีก N เรื่อง')"""
    for i in range(QUEUE_LIMIT + 2):
        await _issue(db_pool, home_world, title=f"งาน {i}", assignee="me")

    body = _get(client, home_world).json()
    assert len(body["pending_on_me"]) == QUEUE_LIMIT
    assert body["pending_on_me_total"] == QUEUE_LIMIT + 2

    # deep DB — ยืนยันว่าเป็นยอดจริง ไม่ใช่ length ของลิสต์
    async with db_pool.acquire() as conn:
        real = await conn.fetchval(
            """SELECT COUNT(*) FROM issues
               WHERE deleted_at IS NULL AND current_assignee_id = $1
                 AND status IN ('pending','in_progress','escalated')""",
            home_world["me"]["user_id"],
        )
    assert body["pending_on_me_total"] == real


# ══════════════════════════════════════════════════════════
# 3) โหวตที่ยังไม่โหวต
# ══════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_unvoted_boards_excludes_boards_i_voted(db_pool, client, home_world):
    voted = await _board(db_pool, home_world, title="โหวตแล้ว")
    not_voted = await _board(db_pool, home_world, title="ยังไม่โหวต")
    await _vote(db_pool, home_world, voted)

    ids = [b["id"] for b in _get(client, home_world).json()["unvoted_boards"]]
    assert ids == [not_voted]


@pytest.mark.asyncio
async def test_soft_deleted_vote_makes_board_unvoted_again(db_pool, client, home_world):
    """⭐ บทเรียน skills.md L434 — unique index ของ piri_votes เป็น *partial*
    (`WHERE deleted_at IS NULL`) ⇒ โหวตที่ soft-delete แล้วต้องโหวตใหม่ได้
    ⇒ `NOT EXISTS` **ต้อง** มี `v.deleted_at IS NULL` ไม่งั้นบอร์ดจะหายจากลิสต์ตลอดกาล
    ทั้งที่ผู้ใช้โหวตใหม่ได้จริง
    """
    board = await _board(db_pool, home_world, title="โหวตแล้วลบ")
    await _vote(db_pool, home_world, board, deleted=True)

    ids = [b["id"] for b in _get(client, home_world).json()["unvoted_boards"]]
    assert board in ids, "โหวตที่ถูกลบต้องไม่กันไม่ให้โหวตใหม่"

    # พิสูจน์ฝั่ง DB ว่ายัง insert ได้จริง (ไม่ใช่แค่ลิสต์โชว์)
    await _vote(db_pool, home_world, board)
    async with db_pool.acquire() as conn:
        live = await conn.fetchval(
            "SELECT COUNT(*) FROM piri_votes WHERE board_id = $1 AND deleted_at IS NULL",
            board,
        )
    assert live == 1


@pytest.mark.asyncio
async def test_unvoted_boards_excludes_other_users_vote(db_pool, client, home_world):
    """โหวตของคนอื่นไม่ทำให้บอร์ดหายจากลิสต์ของฉัน"""
    board = await _board(db_pool, home_world, title="other โหวต")
    await _vote(db_pool, home_world, board, actor="other")
    assert board in [b["id"] for b in _get(client, home_world).json()["unvoted_boards"]]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kwargs",
    [
        {"board_type": "talk"},          # ไม่ใช่บอร์ดโหวต
        {"status": "closed"},            # ปิดแล้ว
        {"deleted": True},               # ถูกลบ
    ],
)
async def test_unvoted_boards_excludes_ineligible(db_pool, client, home_world, kwargs):
    await _board(db_pool, home_world, title="ไม่เข้าเกณฑ์", **kwargs)
    assert _get(client, home_world).json()["unvoted_boards"] == []


@pytest.mark.asyncio
async def test_unvoted_board_vote_count_is_whole_board(db_pool, client, home_world):
    """`vote_count` = โหวตของทั้งบอร์ด (ไม่ใช่ของฉัน) — ไว้โชว์ว่าคนอื่นสนใจแค่ไหน"""
    board = await _board(db_pool, home_world, title="นับโหวต")
    await _vote(db_pool, home_world, board, actor="other")

    item = next(b for b in _get(client, home_world).json()["unvoted_boards"] if b["id"] == board)
    assert item["vote_count"] == 1


@pytest.mark.asyncio
async def test_unvoted_boards_ordering_newest_first_and_total(db_pool, client, home_world):
    first = await _board(db_pool, home_world, title="เก่า", created_at="2026-01-01 09:00:00+07")
    second = await _board(db_pool, home_world, title="ใหม่", created_at="2026-06-01 09:00:00+07")
    for i in range(QUEUE_LIMIT):
        await _board(db_pool, home_world, title=f"เพิ่ม {i}", created_at="2026-07-01 09:00:00+07")

    body = _get(client, home_world).json()
    ids = [b["id"] for b in body["unvoted_boards"]]
    assert len(ids) == QUEUE_LIMIT
    assert ids[0] not in (first, second)  # ใหม่สุดมาก่อน ⇒ ตัว ก.ค. ขึ้นหัว
    assert body["unvoted_boards_total"] == QUEUE_LIMIT + 2


# ══════════════════════════════════════════════════════════
# 4) ประกาศ — ห้ามตัด
# ══════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_announcements_not_truncated(db_pool, client, home_world):
    """⭐ เจ้าของระบบสั่ง "โชว์ทั้งหมดที่ยังไม่ถอดออก" (PR #31–#33) ⇒ ห้าม slice

    ⚠️ ใส่ 25 อัน (มากกว่า LIMIT ที่ใครจะเผลอใส่อย่าง 5/10/20) แล้ว assert ว่า **ครบทุก id**
    · ไม่ assert จำนวนตายตัว เพราะ init_db seed ประกาศเริ่มต้นไว้เมื่อตารางว่าง
      ⇒ จำนวนรวมขึ้นกับลำดับ setup ของ fixture (เปราะโดยไม่จำเป็น)
    """
    ids = {await _announce(db_pool, f"ประกาศที่ {i}") for i in range(25)}

    body = _get(client, home_world).json()
    got = {a["id"] for a in body["announcements"]}
    assert ids <= got, f"ประกาศหายไป {len(ids - got)} อัน"

    async with db_pool.acquire() as conn:
        real = await conn.fetchval(
            "SELECT COUNT(*) FROM announcements WHERE deleted_at IS NULL AND retired_at IS NULL"
        )
    assert len(body["announcements"]) == real


@pytest.mark.asyncio
async def test_announcements_ordered_priority_first(db_pool, client, home_world):
    await _announce(db_pool, "ธรรมดา")
    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO announcements (message, priority) VALUES ('ด่วน','urgent')"
        )
    body = _get(client, home_world).json()
    assert body["announcements"][0]["priority"] == "urgent"


# ══════════════════════════════════════════════════════════
# 5) ตัวเลขต้องตรงกับ endpoint เดิม
# ══════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_stats_identical_to_me_stats_endpoint(db_pool, client, home_world):
    """⭐ ถ้าไม่ตรง = มีคนแก้ query เดียวกันแล้วอัปเดตไม่ครบ ⇒ หน้าสองหน้าจะโชว์เลขคนละชุด"""
    await _issue(db_pool, home_world, title="ของฉัน", assignee="me")
    await _issue(db_pool, home_world, title="ปิดแล้ว", assignee="me", status="resolved")

    home = _get(client, home_world).json()["stats"]
    direct = client.get("/api/me/stats", headers=_auth(home_world)).json()
    assert home == direct


@pytest.mark.asyncio
async def test_my_issues_identical_to_issue_summary_endpoint(db_pool, client, home_world):
    await _issue(db_pool, home_world, title="เรื่อง A")
    await _issue(db_pool, home_world, title="เรื่อง B", status="resolved")

    home = _get(client, home_world).json()["my_issues"]
    direct = client.get("/api/issues/summary", headers=_auth(home_world)).json()
    assert home == direct


@pytest.mark.asyncio
async def test_empty_world_returns_zero_filled_not_error(db_pool, client, home_world):
    """ผู้ใช้ใหม่เอี่ยม (ไม่มีงาน ไม่มีบอร์ด) ต้องได้ 200 + ค่า 0/[] ไม่ใช่ null หรือ 500"""
    body = _get(client, home_world).json()
    assert body["pending_on_me"] == []
    assert body["unvoted_boards"] == []
    assert body["closing_soon_events"] == []  # ไม่มีกิจกรรมเลย ⇒ บล็อกว่าง ไม่ใช่ error
    assert body["closing_soon_events_total"] == 0
    assert body["my_issues"]["total_issues"] == 0
    assert body["stats"]["term"] is None  # ยังไม่มีภาคปัจจุบัน (สถานะตั้งต้นจริง)
    for key in ("total_reported", "resolved_count", "in_progress_count",
                "votes_cast", "board_comments_posted", "issue_comments_posted"):
        assert body["stats"][key] == 0, key


# ══════════════════════════════════════════════════════════
# 6) ⏳ กิจกรรมใกล้ปิดรับ (4.5) — คิวที่ 3
# ══════════════════════════════════════════════════════════
#
# ⭐ หัวใจของพาร์ทนี้คือ **"ปิดรับ" ไม่ได้แปลว่า `registration_deadline`** —
#    กิจกรรมที่ไม่ได้ตั้งกำหนดปิดรับจะปิดที่ *วันจัด* ซึ่งเป็นกลุ่มที่นักเรียนพลาดมากที่สุด
#    (ไม่มี deadline ให้เห็น จึงไม่มีอะไรเตือน) ⇒ เทสต์ชุดนี้ต้องมีเคส "ไม่มี deadline"
#    อยู่เสมอ ไม่ใช่มีแต่เคสที่มี deadline ครบ
#
# ⚠️ วันที่ทั้งหมดคำนวณจาก `NOW()` ของ **DB** (ไม่ใช่ของ Python) เพราะกติกา
#    "ยังเปิดรับไหม" ตัดสินที่ SQL ⇒ ใช้ `datetime.now()` ของโปรเซสมาคำนวณแล้วเทียบ
#    จะเสี่ยง timezone/clock drift ทำให้เทสต์ล้มแบบสุ่ม


async def _event(db_pool, world, *, title="กิจกรรมทดสอบ", days_until=3,
                 deadline_days=None, status="published", capacity=None,
                 category="other", actor="me", deleted=False) -> int:
    """สร้างกิจกรรม 1 ใบ

    `days_until`     = อีกกี่วันถึงวันจัด (ติดลบ = ผ่านไปแล้ว)
    `deadline_days`  = อีกกี่วันถึงกำหนดปิดรับ · `None` = ไม่ตั้งกำหนด (ปิดเอาวันจัด)
    """
    async with db_pool.acquire() as conn:
        return await conn.fetchval(
            """
            INSERT INTO events
                (title, event_date, registration_deadline, capacity, category,
                 status, published_at, created_by, deleted_at)
            VALUES ($1,
                    NOW() + make_interval(days => $2::int),
                    CASE WHEN $3::int IS NULL THEN NULL
                         ELSE NOW() + make_interval(days => $3::int) END,
                    $4, $5, $6::text,
                    -- ⚠️ `$6::text` **ต้อง cast ทั้งสองที่** — ถ้าปล่อยให้ตัวหนึ่งอนุมานจาก
                    --    คอลัมน์ (varchar) และอีกตัวจาก literal (text) Postgres จะโยน
                    --    `AmbiguousParameterError: inconsistent types deduced for parameter $6`
                    CASE WHEN $6::text = 'published' THEN NOW() ELSE NULL END,
                    $7,
                    CASE WHEN $8::boolean THEN NOW() ELSE NULL END)
            RETURNING id
            """,
            title, days_until, deadline_days, capacity, category, status,
            world[actor]["user_id"], deleted,
        )


async def _register(db_pool, world, event_id, *, actor="me", status="registered"):
    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO event_registrations (event_id, user_id, status) VALUES ($1,$2,$3)",
            event_id, world[actor]["user_id"], status,
        )


@pytest.mark.asyncio
async def test_closing_soon_without_deadline_uses_event_date(db_pool, client, home_world):
    """★ กับดักหลัก: กิจกรรมที่ไม่ตั้งกำหนดปิดรับ ต้องถูกนับว่าปิดที่ *วันจัด*

    ถ้ามีคนเปลี่ยน `_CLOSES_AT_SQL` เป็น `COALESCE` หรือเผลอกรองด้วย
    `registration_deadline IS NOT NULL` แถวนี้จะหายจากบล็อกทั้งที่มันคือแถวที่
    ควรเตือนมากที่สุด — เทสต์นี้คือสิ่งเดียวที่จับได้
    """
    ev = await _event(db_pool, home_world, title="ไม่มีกำหนดปิดรับ", days_until=3)

    body = _get(client, home_world).json()
    ids = [e["id"] for e in body["closing_soon_events"]]
    assert ev in ids
    row = next(e for e in body["closing_soon_events"] if e["id"] == ev)
    # closes_at ต้องเป็นวันจัด ไม่ใช่ null และไม่ใช่ค่าอื่น
    async with db_pool.acquire() as conn:
        expected = await conn.fetchval("SELECT event_date FROM events WHERE id = $1", ev)
    assert _ts(row["closes_at"]) == expected


@pytest.mark.asyncio
async def test_closing_soon_uses_earlier_of_deadline_and_event_date(db_pool, client, home_world):
    """กำหนดปิดรับอยู่ก่อนวันจัด ⇒ `closes_at` = กำหนดปิดรับ (อันที่ถึงก่อน)"""
    ev = await _event(db_pool, home_world, days_until=10, deadline_days=2)

    body = _get(client, home_world).json()
    row = next(e for e in body["closing_soon_events"] if e["id"] == ev)
    async with db_pool.acquire() as conn:
        deadline = await conn.fetchval(
            "SELECT registration_deadline FROM events WHERE id = $1", ev
        )
    assert _ts(row["closes_at"]) == deadline


@pytest.mark.asyncio
async def test_closing_soon_deadline_after_event_does_not_extend_the_window(
    db_pool, client, home_world
):
    """★★ กับดักที่ต้อง `LEAST` ไม่ใช่ `COALESCE`

    แถวที่ **กำหนดปิดรับอยู่หลังวันจัด** เป็นแถวที่ "ด่านที่สอง" ของเรามีไว้เพื่อรองรับ
    (`_assert_deadline_not_after_event` กันไว้ที่ชั้น service ⇒ สร้างผ่าน API ไม่ได้
    แต่ seed ตรงเข้า DB ได้ และแถวก่อนมีด่านก็มีอยู่จริง)

    ⭐ ถ้าใช้ `COALESCE(e.registration_deadline, e.event_date)` แถวนี้จะได้ `closes_at`
       = อีก 30 วัน ⇒ **หลุดออกจากหน้าต่าง 7 วันทั้งที่ความจริงปิดรับอีก 3 วัน**
       (แย่กว่านั้น: มันจะ *โผล่* ผิดที่เมื่อ deadline อยู่ใกล้ แต่ไม่ตรงกับความจริงเลย)
    ⇒ เทสต์นี้ล้มถ้าเปลี่ยน `LEAST` เป็น `COALESCE` — เป็นเทสต์เดียวที่จับได้
    """
    ev = await _event(db_pool, home_world, title="deadline หลังวันจัด", days_until=3,
                      deadline_days=30)

    body = _get(client, home_world).json()
    row = next(e for e in body["closing_soon_events"] if e["id"] == ev)
    async with db_pool.acquire() as conn:
        event_date = await conn.fetchval("SELECT event_date FROM events WHERE id = $1", ev)
    # closes_at ต้องเป็น *วันจัด* (อันที่ถึงก่อน) ไม่ใช่ deadline ที่ตั้งไว้ 30 วัน
    assert _ts(row["closes_at"]) == event_date


@pytest.mark.asyncio
async def test_closing_soon_block_agrees_with_is_registration_open_endpoint(
    db_pool, client, home_world
):
    """★ ความสอดคล้องข้ามคิวรี — ทุกแถวในบล็อกต้อง "ยังเปิดรับ" จริงตาม endpoint ตัวเอง

    `list_closing_soon_events` กับ `get_public_event` เป็นโค้ดคนละเส้นที่ประกอบ
    `_PUBLIC_COLUMNS` ร่วมกัน ⇒ ถ้าวันหนึ่งมีคนแก้กติกา "เปิดรับ" ที่เดียว
    บล็อกหน้าแรกจะชี้กิจกรรมที่กดสมัครไม่ได้ ซึ่งเชื่อได้ยากว่าเกิดจากอะไร
    (ผู้ใช้จะบอกว่า "ปุ่มสมัครหาย" ไม่ใช่ "บล็อกผิด")

    เทสต์นี้ตั้งใจให้มีทั้งแถวที่เข้าและไม่เข้าเงื่อนไข ⇒ มันพิสูจน์ *ทั้งสองทิศ*
    ไม่ใช่แค่ทิศที่สะดวก
    """
    inside = await _event(db_pool, home_world, title="เข้าเงื่อนไข", days_until=2)
    await _event(db_pool, home_world, title="ปิดไปแล้ว", days_until=2, deadline_days=-1)
    await _event(db_pool, home_world, title="ไกลเกิน", days_until=40)

    ids = [e["id"] for e in _get(client, home_world).json()["closing_soon_events"]]
    assert ids == [inside]  # มีแถวเดียวที่ควรเข้า และมันต้องเข้าให้ได้

    detail = client.get(f"/api/events/public/{inside}", headers=_auth(home_world)).json()
    assert detail["is_registration_open"] is True
    block_row = _get(client, home_world).json()["closing_soon_events"][0]
    assert _ts(detail["closes_at"]) == _ts(block_row["closes_at"])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kwargs",
    [
        {"days_until": 30},                       # ปิดอีก 30 วัน — ไกลเกินหน้าต่าง 7 วัน
        {"days_until": -1},                       # วันจัดผ่านไปแล้ว
        {"days_until": 3, "deadline_days": -1},   # กำหนดปิดรับผ่านไปแล้ว (ยังไม่ถึงวันจัด)
        {"days_until": 3, "status": "draft"},     # ยังไม่เผยแพร่
        {"days_until": 3, "status": "cancelled"},  # ยกเลิกแล้ว
        {"days_until": 3, "deleted": True},       # ถูกลบ (soft)
    ],
    ids=["too-far", "past-event", "deadline-passed", "draft", "cancelled", "deleted"],
)
async def test_closing_soon_excludes_out_of_window(db_pool, client, home_world, kwargs):
    """ทุกกรณีที่ **ไม่ควร** เข้าบล็อก — และต้องไม่ทำให้ total เพี้ยน"""
    await _event(db_pool, home_world, **kwargs)
    body = _get(client, home_world).json()
    assert body["closing_soon_events"] == []
    assert body["closing_soon_events_total"] == 0


@pytest.mark.asyncio
async def test_closing_soon_ordering_soonest_first(db_pool, client, home_world):
    """เรียงจากที่จะปิดเร็วสุดขึ้นก่อน — บล็อกนี้มีค่าเพราะ "อันที่ใกล้ที่สุด" อยู่บนสุด"""
    far = await _event(db_pool, home_world, title="ไกล", days_until=6)
    near = await _event(db_pool, home_world, title="ใกล้", days_until=1)
    mid = await _event(db_pool, home_world, title="กลาง", days_until=4)

    body = _get(client, home_world).json()
    assert [e["id"] for e in body["closing_soon_events"]] == [near, mid, far]


@pytest.mark.asyncio
async def test_closing_soon_limit_but_total_is_real_count(db_pool, client, home_world):
    """`items` ถูกตัดที่ QUEUE_LIMIT แต่ `total` ต้องเป็นยอดจริง (ไว้ขึ้น "ดูทั้งหมด N")"""
    for i in range(QUEUE_LIMIT + 2):
        await _event(db_pool, home_world, title=f"กิจกรรม {i}", days_until=1)

    body = _get(client, home_world).json()
    assert len(body["closing_soon_events"]) == QUEUE_LIMIT
    assert body["closing_soon_events_total"] == QUEUE_LIMIT + 2


@pytest.mark.asyncio
async def test_closing_soon_includes_events_i_already_registered_for(db_pool, client, home_world):
    """★ **ต้องไม่กรองตามการสมัครของฉัน** — "สมัครแล้ว" ≠ "เรียบร้อย"

    บล็อกนี้มีค่าที่สุดตอนที่ฉันสมัครไปแล้วแต่ยังไม่ได้ไป ("อย่าลืมไป") ⇒ ถ้ามีคน
    "ปรับ" ให้กรอง `my_registration_status IS NULL` (ดูเหมือนสมเหตุสมผล) เทสต์นี้จะจับได้
    และสิ่งที่ต้องต่างกันคือ *ปุ่ม* ไม่ใช่ *การมีอยู่ของแถว*
    """
    mine = await _event(db_pool, home_world, title="ฉันสมัครแล้ว", days_until=2)
    others = await _event(db_pool, home_world, title="ฉันยังไม่สมัคร", days_until=3)
    await _register(db_pool, home_world, mine)

    body = _get(client, home_world).json()
    ids = [e["id"] for e in body["closing_soon_events"]]
    assert mine in ids and others in ids

    row = next(e for e in body["closing_soon_events"] if e["id"] == mine)
    assert row["my_registration_status"] == "registered"
    row2 = next(e for e in body["closing_soon_events"] if e["id"] == others)
    assert row2["my_registration_status"] is None


@pytest.mark.asyncio
async def test_closing_soon_my_registration_is_mine_not_others(db_pool, client, home_world):
    """`my_registration_status` ต้องเป็นของ *ฉัน* — `other` สมัครไว้ต้องไม่ทำให้ฉันขึ้นว่าสมัครแล้ว

    ⚠️ `_MY_REG_JOIN` ผูกด้วย `$1` = user_id ของฉัน ⇒ เทสต์นี้กันการเผลอส่ง user_id ผิดตัว
    (ซึ่งจะทำให้ปุ่มในหน้าแรกขึ้น "สมัครแล้ว" ทั้งที่ยังไม่ได้สมัคร = กดสมัครไม่ได้)
    """
    ev = await _event(db_pool, home_world, days_until=2)
    await _register(db_pool, home_world, ev, actor="other")

    row = next(e for e in _get(client, home_world).json()["closing_soon_events"] if e["id"] == ev)
    assert row["my_registration_status"] is None
    # ฝั่ง other เห็นของตัวเอง
    row_other = next(
        e for e in _get(client, home_world, actor="other").json()["closing_soon_events"]
        if e["id"] == ev
    )
    assert row_other["my_registration_status"] == "registered"


@pytest.mark.asyncio
async def test_closing_soon_seats_remaining_none_when_unlimited(db_pool, client, home_world):
    """`capacity IS NULL` = ไม่จำกัด ⇒ `seats_remaining` ต้องเป็น **None ไม่ใช่ 0**

    ⚠️ 0 แปลว่า "เต็ม" ⇒ ถ้าคืน 0 ฝั่งจอจะขึ้น "เต็ม" ทั้งที่ไม่จำกัดจำนวน
    """
    unlimited = await _event(db_pool, home_world, title="ไม่จำกัด", days_until=2)
    limited = await _event(db_pool, home_world, title="จำกัด 2", days_until=2, capacity=2)
    await _register(db_pool, home_world, limited)

    rows = {e["id"]: e for e in _get(client, home_world).json()["closing_soon_events"]}
    assert rows[unlimited]["seats_remaining"] is None
    assert rows[limited]["seats_remaining"] == 1


@pytest.mark.asyncio
async def test_closing_soon_does_not_leak_admin_fields(db_pool, client, home_world):
    """แถวในบล็อกหน้าแรกต้องไม่มีข้อมูลผู้ดูแลหลุด — ด่านอยู่ที่ schema

    `_PUBLIC_COLUMNS` SELECT `created_by` / `deleted_at` มาตรง ๆ (ใช้ร่วมกับฝั่งจัดการ)
    ⇒ ที่กันคือ `ClosingSoonEventItem` ที่ไม่ประกาศฟิลด์เหล่านั้น — เทสต์นี้ยืนยันว่า
    ยังไม่มีใครเผลอเพิ่มเข้าไป (ซึ่งจะทำให้หน้าแรกของนักเรียนทุกคนเห็นว่าใครสร้าง)
    """
    await _event(db_pool, home_world, days_until=2)
    row = _get(client, home_world).json()["closing_soon_events"][0]
    for leaked in ("created_by", "updated_by", "created_by_name", "updated_by_name",
                   "deleted_at", "description", "cover_image_url"):
        assert leaked not in row, leaked
