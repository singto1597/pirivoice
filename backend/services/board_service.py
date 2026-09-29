"""
PIRI Boards — Phase 3: Board Service (PIRI Vote + PIRI Talk)
=============================================================
core engine สำหรับ board สาธารณะ (ไม่มี pyramid visibility — ข้อมูลสาธารณะทั้งโรงเรียน):
- list_public_boards  — feed board ที่ active (กรองประเภท/ค้นหา + แบ่งหน้า)
- get_board_detail    — board + choices (vote) + comments แบบ threaded (talk) + สถานะโหวตของ user
- submit_vote         — โหวต 1 เสียงต่อ board (จับ UniqueViolationError → ConflictError 409)
- add_comment         — คอมเมนต์/รีพลาย (เฉพาะ talk + allow_comments)

กฎ backend.md ที่ปฏิบัติตาม:
- ทุก UPDATE/INSERT → AuditLogger ใน transaction เดียว
- SQL parameterized ($1, $2, ...) — ห้าม f-string กับ user input
- soft delete: ตรวจ deleted_at IS NULL ตลอด
- jsonb (tags) asyncpg คืนเป็น string → json.loads (บทเรียนใน skills.md)
"""
import json
from typing import Optional, List
import asyncpg

from core.exceptions import NotFoundError, ForbiddenError, ValidationError, ConflictError

# 🔔 Notification writer (อยู่ใน transaction เดียวกับข้อมูลหลัก — ลอกแบบ AuditLogger)
from services.notification_service import notify, _user_display_name

# ⚠️ ความลึก reply ที่ปลอดภัย — กัน recursive Pydantic overflow:
# BoardCommentOut เป็น model ซ้อนตัวเอง — reply chain ~256 ชั้นทำ BoardDetailOut(**detail)
# เกิด 'recursion_loop' ValidationError → HTTP 500 ทุกครั้งที่ GET detail (adversarial review ยืนยันแล้ว)
# → (1) tree ที่ส่ง client ถูกพับไม่ให้ลึกเกิน MAX_DISPLAY_DEPTH, (2) สร้าง reply ใหม่ลึกเกิน MAX_REPLY_DEPTH ไม่ได้
MAX_DISPLAY_DEPTH = 8   # root = 0 → ลึกสุด 8 (reply เกินถูกย้ายไปพับใต้บรรพบุรุษที่ยังใต้ลิมิต — ไม่หาย)
MAX_REPLY_DEPTH = 30    # จำกัดความลึกตอนสร้าง reply ใหม่ (chain ยักษ์สร้างไม่ได้ผ่าน API)

# ============================================================
# 🏷️ ชนิดของ board — นิยามที่เดียว ให้ทุกจุดที่ตัดสินใจอ้างถึงตัวเดียวกัน
# ============================================================
# ⚠️ ค่าทั้งหมดต้องอยู่ใน `chk_piri_boards_type` (migration 022) ไม่งั้น INSERT จะได้
#    CheckViolationError ตอน runtime — ชุดนี้คือ "สัญญา" ระหว่าง Python กับ DB
BOARD_TYPE_VOTE = "vote"
BOARD_TYPE_TALK = "talk"
BOARD_TYPE_SUGGESTION = "suggestion"   # E1 — ผู้ใช้เสนอไอเดียเอง ไม่ผ่านด่านสภา

# ชนิดที่ **คอมเมนต์ได้** (ทางเขียน ⇒ whitelist / fail-closed)
# - vote: ไม่ได้ (มีตัวเลือกแทนช่องคอมเมนต์)
# - talk: ได้มาตั้งแต่ต้น
# - suggestion: ได้ — เป็นหัวใจของ E1 (คนอื่นต้องคุยใต้ข้อเสนอได้)
COMMENTABLE_BOARD_TYPES = (BOARD_TYPE_TALK, BOARD_TYPE_SUGGESTION)

# ชนิดที่ **โหวตได้** (มี `piri_vote_choices` + partial unique บน piri_votes)
# ⚠️ suggestion **ไม่อยู่ในนี้โดยเจตนา** — ข้อเสนอไม่ใช่การโหวต ถ้าอนาคตอยากให้กด "เห็นด้วย"
#    ต้องเป็นการตัดสินใจเชิงผลิตภัณฑ์ + เพิ่มตารางของตัวเอง (ไม่ใช่ยัดลง piri_votes)
VOTABLE_BOARD_TYPES = (BOARD_TYPE_VOTE,)


# ============================================================
# 🔧 Helpers
# ============================================================
def _parse_json(raw, default=None):
    """jsonb ที่ asyncpg คืนเป็น string → list/dict (บทเรียนเดิมจาก audit_service)"""
    if raw is None:
        return default if default is not None else []
    if isinstance(raw, (list, dict)):
        return raw
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default if default is not None else []


def _display_name(row) -> Optional[str]:
    """ชื่อแสดง: prefix+first_name+last_name จาก students (fallback users.full_name)
    row ต้องมาจาก query ที่ LEFT JOIN users/students แล้ว (pattern เดียวกับ issue_service)"""
    parts = [p for p in (row.get("prefix"), row.get("first_name"), row.get("last_name")) if p]
    student_name = " ".join(parts).strip()
    return student_name or row.get("author_full_name")


# SQL fragment: ชื่อผู้เขียน + ผู้คอมเมนต์ (LEFT JOIN users/students/rooms)
# ใช้ซ้ำในทุก query ที่อยากได้ชื่อจริง — ลดซ้ำ (เหมือน _student_display_name)
_AUTHOR_JOIN = """
    LEFT JOIN users u_author ON u_author.id = b.author_id
    LEFT JOIN students s_author
        ON s_author.user_id = b.author_id AND s_author.deleted_at IS NULL AND s_author.status = 'active'
"""
_COMMENTER_JOIN = """
    LEFT JOIN users u_comm ON u_comm.id = c.user_id
    LEFT JOIN students s_comm
        ON s_comm.user_id = c.user_id AND s_comm.deleted_at IS NULL AND s_comm.status = 'active'
    LEFT JOIN rooms r_comm ON r_comm.id = s_comm.room_id
"""


def _board_to_dict(row) -> dict:
    """แถว piri_boards (หลัง JOIN users/students) → dict สำหรับ response
    ⚠️ board anonymous: author_id/author_name เป็น None ทั้งคู่ — กันเทียบ user_id กับคนจริง (deanonymization)"""
    if row["is_anonymous"]:
        author_id = None
        author_name = None
    else:
        author_id = row["author_id"]
        author_name = _display_name(row)
    return {
        "id": row["id"],
        "board_type": row["board_type"],
        "title": row["title"],
        "description": row["description"],
        "cover_image_url": row["cover_image_url"],
        "source_issue_id": row["source_issue_id"],
        "author_id": author_id,
        "author_name": author_name,
        "is_anonymous": row["is_anonymous"],
        "comment_count": row["comment_count"],
        "view_count": row["view_count"],
        "status": row["status"],
        "tags": _parse_json(row["tags"], []),
        "total_votes": row.get("total_votes", 0),
        "created_at": row["created_at"],
    }


# ============================================================
# 📜 1) list_public_boards — feed ที่ active (ไม่มี pyramid visibility)
# ============================================================
async def list_public_boards(
    pool: asyncpg.Pool,
    *,
    board_type: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
) -> dict:
    """
    feed board ที่ active — ทุกคนที่ล็อกอินเห็นได้ (ข้อมูลสาธารณะ ไม่ต้องเช็คระดับ)
    กรอง: board_type ('vote'/'talk'/'suggestion'), q (ค้นหา title/description — escape wildcard)
    เรียง: สร้างใหม่สุดก่อน → แบ่งหน้า
    envelope: {items, total, page, page_size, pages} (pattern เดียวกับ /issues)

    ⚠️ `board_type` ไม่ถูก whitelist ที่ชั้นนี้ — ค่ามาจาก `Query(pattern=...)` ของ router
    ⇒ ค่าที่หลุดมาถึงนี่มีแต่ค่าที่ผ่าน regex แล้ว (ไม่ใช่ SQL injection เพราะ parameterized อยู่แล้ว
    แต่กันการกรองด้วยค่าที่ไม่มีความหมายแล้วได้ [] เงียบ ๆ)
    """
    where = ["b.deleted_at IS NULL", "b.status = 'active'"]
    params: list = []
    if board_type:
        params.append(board_type)
        where.append(f"b.board_type = ${len(params)}")
    if q:
        # หนี wildcard (% _ \\) กันคำค้นกลายเป็น LIKE pattern (pattern เดียวกับ list_issues)
        escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        params.append(f"%{escaped}%")
        where.append(f"(b.title ILIKE ${len(params)} ESCAPE '\\' OR b.description ILIKE ${len(params)} ESCAPE '\\')")
    where_sql = " AND ".join(where)

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            SELECT b.*, u_author.full_name AS author_full_name,
                   s_author.prefix, s_author.first_name, s_author.last_name,
                   COALESCE((SELECT SUM(c.vote_count) FROM piri_vote_choices c
                             WHERE c.board_id = b.id AND c.deleted_at IS NULL), 0) AS total_votes,
                   COUNT(*) OVER() AS total_count
            FROM piri_boards b
            {_AUTHOR_JOIN}
            WHERE {where_sql}
            ORDER BY b.created_at DESC, b.id DESC
            LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}
            """,
            *params, limit, offset
        )

        # total: COUNT(*) OVER() อ่านจากแถวแรก — หน้า offset เลย (rows ว่าง) ต้องนับแยก
        if rows:
            total = rows[0]["total_count"]
        else:
            total = await conn.fetchval(
                f"SELECT COUNT(*) FROM piri_boards b WHERE {where_sql}",
                *params
            ) or 0

    return {
        "items": [_board_to_dict(r) for r in rows],
        "total": total,
        "page": offset // limit + 1,
        "page_size": limit,
        "pages": (total + limit - 1) // limit if total else 0,
    }


# ============================================================
# 🔍 2) get_board_detail — vote: choices + my_vote; talk: comments (threaded)
# ============================================================
async def get_board_detail(pool: asyncpg.Pool, user_id: int, board_id: int) -> dict:
    """
    รายละเอียด board:
    - vote board → choices (พร้อม vote_count) + my_vote_choice_id (user โหวตตัวไหนอยู่)
    - talk / suggestion board → comments แบบ threaded (replies ซ้อนได้ลึกเท่าไหร่ก็ได้)
    hidden board (แอดมินซ่อน) → 404 (ไม่มีข้อมูลรั่ว — เหมือนซอฟต์ดีลีต)
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"""
            SELECT b.*, u_author.full_name AS author_full_name,
                   s_author.prefix, s_author.first_name, s_author.last_name,
                   COALESCE((SELECT SUM(c.vote_count) FROM piri_vote_choices c
                             WHERE c.board_id = b.id AND c.deleted_at IS NULL), 0) AS total_votes
            FROM piri_boards b
            {_AUTHOR_JOIN}
            WHERE b.id = $1 AND b.deleted_at IS NULL
            """,
            board_id
        )
        if not row:
            raise NotFoundError("ไม่พบ board นี้")
        if row["status"] == "hidden":
            raise NotFoundError("ไม่พบ board นี้")

        detail = _board_to_dict(row)
        detail["allow_comments"] = row["allow_comments"]

        if row["board_type"] in VOTABLE_BOARD_TYPES:
            choices = await conn.fetch(
                """
                SELECT id, choice_text, description, image_url, sort_order, vote_count
                FROM piri_vote_choices
                WHERE board_id = $1 AND deleted_at IS NULL
                ORDER BY sort_order ASC, id ASC
                """,
                board_id
            )
            detail["choices"] = [
                {
                    "id": c["id"], "choice_text": c["choice_text"],
                    "description": c["description"], "image_url": c["image_url"],
                    "sort_order": c["sort_order"], "vote_count": c["vote_count"],
                }
                for c in choices
            ]
            # สถานะโหวตของ user นี้ (row ยัง active — partial unique index)
            # JOIN ตัวเลือกที่ยัง active — กัน my_vote_choice_id ชี้ choice ที่ soft-delete แล้ว (หาใน choices ไม่เจอ)
            my_vote = await conn.fetchval(
                """
                SELECT v.choice_id
                FROM piri_votes v
                JOIN piri_vote_choices c ON c.id = v.choice_id AND c.deleted_at IS NULL
                WHERE v.board_id = $1 AND v.user_id = $2 AND v.deleted_at IS NULL
                """,
                board_id, user_id
            )
            detail["my_vote_choice_id"] = my_vote
        else:
            # 'talk' และ 'suggestion' (E1) — ทั้งคู่ใช้เลย์เอาต์คอมเมนต์เดียวกัน
            # ⚠️ ใช้ `else` (ไม่ใช่ `elif == 'talk'`) **โดยเจตนา — ตัวอ่าน default เปิด**:
            #    ชนิดใหม่ที่เพิ่มในอนาคตจะแสดงได้ทันทีแทนที่จะได้ board เปล่า ๆ ที่อธิบายไม่ได้
            #    (ทางเขียนคือที่ที่ต้อง fail-closed — ดู `add_comment` ที่ whitelist ไว้)
            comment_rows = await conn.fetch(
                f"""
                SELECT c.*, u_comm.full_name AS author_full_name,
                       s_comm.prefix, s_comm.first_name, s_comm.last_name
                FROM piri_board_comments c
                {_COMMENTER_JOIN}
                WHERE c.board_id = $1 AND c.deleted_at IS NULL AND c.is_hidden_by_admin = FALSE
                ORDER BY c.created_at ASC, c.id ASC
                LIMIT 1000
                """,
                board_id
            )
            detail["comments"] = _thread_comments(comment_rows)

        # 👁️ นับ view_count — dedup ต่อ user (กัน F5 ปั่นยอด): user 1 คน นับ 1 ครั้ง
        # ต่อ VIEW_DEDUP_WINDOW ต่อ board ผ่าน piri_board_views (board_id,user_id PK)
        # INSERT..ON CONFLICT..WHERE viewed_at < NOW()-window → คืน 1 เฉพาะ "ยังไม่เคยดู" หรือ
        # "เลย window แล้ว" → ถึงจะ +1; ภายใน window (refresh รัวๆ) ไม่นับ
        # ไม่ audit (กัน noise — การดู board ถูก audit ผ่าน log_read ใน router แล้ว)
        VIEW_DEDUP_WINDOW = "10 minutes"
        # ⚠️ ต้องเป็น data-modifying CTE (WITH ... INSERT ... RETURNING) —
        # วาง INSERT ตรงๆ ใน FROM ของ subquery → PostgresSyntaxError 'syntax error at or near INTO'
        counted = await conn.fetchval(
            f"""
            WITH ins AS (
                INSERT INTO piri_board_views (board_id, user_id, viewed_at)
                VALUES ($1, $2, NOW())
                ON CONFLICT (board_id, user_id)
                DO UPDATE SET viewed_at = NOW()
                WHERE piri_board_views.viewed_at < NOW() - INTERVAL '{VIEW_DEDUP_WINDOW}'
                RETURNING 1
            )
            SELECT COUNT(*) FROM ins
            """,
            board_id, user_id
        )
        if counted:
            await conn.execute(
                "UPDATE piri_boards SET view_count = view_count + 1, updated_at = NOW() WHERE id = $1 AND deleted_at IS NULL",
                board_id
            )

    return detail


def _thread_comments(rows) -> List[dict]:
    """แปลงแถวคอมเมนต์ (เรียงตามเวลา) → tree แบบ threaded:
    คอมเมนต์หลักที่ root, reply ซ้อนใน replies ของ parent (เรียงตามเวลาภายในกลุ่ม)
    - parent ที่ถูก soft delete → ลูกย้ายขึ้นระดับบน (ยังแสดงต่อได้ ไม่หายทั้งต้น)
    - ⚠️ ความลึกถูกจำกัดที่ MAX_DISPLAY_DEPTH: reply ที่ลึกเกินถูก "พับ" ไปใต้บรรพบุรุษ
      ที่ยังใต้ลิมิต (ยังโชว์ ไม่หาย) — กัน recursive Pydantic overflow (BoardCommentOut
      ซ้อนตัวเอง ~256 ชั้น → ValidationError 'recursion_loop' → 500)
    - order: เรียงตาม created_at — หน้า feed อ่านง่ายขึ้น (เหมือน YouTube)"""
    nodes = {}
    roots: List[dict] = []
    for r in rows:
        node = {
            "id": r["id"],
            "parent_comment_id": r["parent_comment_id"],
            "user_id": r["user_id"],
            "commenter_name": _display_name(r),
            "commenter_first_name": r.get("first_name"),
            "body": r["body"],
            "is_edited": r["is_edited"],
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
            "replies": [],
        }
        nodes[node["id"]] = node

    depth: dict = {}  # comment id → ความลึกจาก root (0 = root comment)
    for nid, node in nodes.items():
        pid = node["parent_comment_id"]
        parent = nodes.get(pid) if pid else None
        if parent is None:
            # parent โดน soft delete/หาย → ยกเป็น root จริง + รีเซ็ต parent_comment_id
            # (กัน frontend เจอ id แขวนที่ไม่มีใน list แล้ว render ผิดที่)
            node["parent_comment_id"] = None
            depth[nid] = 0
            roots.append(node)
            continue
        node_depth = depth.get(pid, 0) + 1
        if node_depth <= MAX_DISPLAY_DEPTH:
            depth[nid] = node_depth
            parent["replies"].append(node)
            continue
        # ลึกเกิน MAX_DISPLAY_DEPTH → หาบรรพบุรุษที่ลึกที่สุดที่ยังใต้ลิมิต แล้วแปะใต้บรรพบุรุษนั้น
        target = parent
        while target and depth.get(target["id"], 0) >= MAX_DISPLAY_DEPTH:
            tp = target["parent_comment_id"]
            target = nodes.get(tp) if tp else None
        if target is None:
            depth[nid] = 1
            roots.append(node)
        else:
            depth[nid] = depth.get(target["id"], 0) + 1
            target["replies"].append(node)
    return roots


# ============================================================
# 💡 3) create_suggestion — E1: ผู้ใช้เสนอไอเดียเอง (ไม่ผ่านด่านสภา)
# ============================================================
async def create_suggestion(
    pool: asyncpg.Pool,
    user_id: int,
    *,
    title: str,
    description: str,
    is_anonymous: bool = False,
) -> dict:
    """
    สร้าง board ชนิด 'suggestion' จากผู้ใช้ทั่วไป — **คนละทางกับ `approve_to_public()`**

    ความต่างที่ตั้งใจ (ทั้ง 4 ข้อ):
    | | `approve_to_public` (talk/vote) | `create_suggestion` (E1) |
    |---|---|---|
    | ใครสร้างได้ | สภา/แอดมินเท่านั้น (`_has_council_authority`) | ผู้ใช้ที่ล็อกอินแล้วทุกคน |
    | ต้นทาง | ต้องมี `issue` ที่ขอปลายทางสาธารณะ | ไม่มี issue — ตั้งต้นจากฟอร์มสั้น |
    | `source_issue_id` / `approved_*` | มีค่า | **NULL ทั้งสาม** (ไม่มีต้นทาง ไม่มีผู้อนุมัติ) |
    | แจ้งเตือน | `notify_fanout` (ทุกคน) | **ไม่แจ้งใครเลย** — ผู้ใช้เลือก "ไม่แจ้งใครเลย" (§4) |

    ⚠️ **`status = 'active'` ทันที ไม่มีขั้นอนุมัติ** — ผู้ใช้เลือก "ขึ้นทันที + ซ่อนย้อนหลังได้"
    ⇒ เครื่องมือ moderation คือปุ่ม "ซ่อนบอร์ด" ที่มีอยู่แล้ว (`board_moderation_service.hide_board`)
    **ไม่ต้องมีสถานะ 'pending'** ในสคีมา และไม่ต้องขยาย `chk_piri_boards_status`

    ⚠️ **ไม่เรียก `notify_fanout` โดยเจตนา** — ถ้าวันหน้าจะเพิ่ม ต้องคิดเรื่อง push storm ก่อน:
    fanout ยิงทุก active student (~800–1,000 คน) ⇒ ข้อเสนอที่ส่งได้ทุกคนจะกลายเป็นสแปมทันที
    (บทเรียน §20.14 ข้อ 7 — ความดังของ push เป็นความเสี่ยงเชิงสังคม ไม่ใช่เทคนิค)

    ⚠️ **`author_id` = เจ้าของ token เท่านั้น** — ไม่รับจาก body (router ไม่มีฟิลด์นั้นในสคีมา)
    และ `is_anonymous=True` จะถูก `_board_to_dict` ปิดชื่อให้เอง (เหมือน talk/vote)

    คืน `{"id", "title", "created_at"}` **จากค่า `RETURNING` จริงของ INSERT**
    — ไม่ใช่ `datetime.now()` ที่ router ประกอบเอง (ค่าที่ประทับตราคือ `CURRENT_TIMESTAMP`
    ของ DB ⇒ สองค่านี้อาจต่างกันได้ และ client จะเห็นเวลาที่ไม่ตรงกับที่ list แสดง)
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                INSERT INTO piri_boards
                    (source_issue_id, board_type, title, description, cover_image_url,
                     author_id, is_anonymous, approved_by, approved_at,
                     status, allow_comments, tags)
                VALUES (NULL, $1, $2, $3, NULL, $4, $5, NULL, NULL, 'active', TRUE, '[]'::jsonb)
                RETURNING id, title, created_at
                """,
                BOARD_TYPE_SUGGESTION, title, description, user_id, is_anonymous
            )
            board_id = row["id"]

            # 🛡️ Audit log (ภายใน transaction เดียว — ตามกฎ backend.md)
            # ⚠️ ต่างจาก A2/C2 ที่ **ไม่** audit (ค่าส่วนตัว) — อันนี้เป็น **state สาธารณะ**
            #    ที่ทุกคนเห็น ⇒ ต้องมีร่องรอยว่าใครสร้างอะไร และใครซ่อน (hide_board audit อยู่แล้ว)
            from core.logger import AuditLogger
            await AuditLogger("board_service").log(
                conn=conn, action="CREATE_SUGGESTION",
                actor_identifier=str(user_id), client_source="web",
                user_id=user_id,
                entity_type="piri_board", entity_id=board_id,
                old_values=None,
                new_values={
                    "board_type": BOARD_TYPE_SUGGESTION,
                    "title": title,
                    "is_anonymous": is_anonymous,
                    "status": "active",
                    "source_issue_id": None,
                },
            )
            return {"id": board_id, "title": row["title"], "created_at": row["created_at"]}


# ============================================================
# 🗳️ 4) submit_vote — โหวต 1 เสียงต่อ board
# ============================================================
async def submit_vote(
    pool: asyncpg.Pool,
    user_id: int,
    board_id: int,
    choice_id: int,
    *,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> dict:
    """
    โหวต board แบบ vote:
    1. board ต้อง active + เป็น vote board (โหวต talk board → 400)
    2. choice ต้องอยู่ใน board นั้น (choice ของ board อื่น → 404)
    3. INSERT piri_votes — partial unique (board_id, user_id) WHERE deleted_at IS NULL
       → โหวตซ้ำโดน UniqueViolationError → ConflictError 409
       (soft delete แล้วโหวตใหม่ได้ — เหมือน uq_students_room_student_active)
    4. INCREMENT vote_count ใน piri_vote_choices
    5. AuditLogger(action="SUBMIT_VOTE")
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            board = await conn.fetchrow(
                "SELECT * FROM piri_boards WHERE id = $1 AND deleted_at IS NULL AND status = 'active'",
                board_id
            )
            if not board:
                raise NotFoundError("ไม่พบ board นี้")
            if board["board_type"] not in VOTABLE_BOARD_TYPES:
                raise ValidationError("board นี้ไม่ใช่แบบโหวต")

            choice = await conn.fetchrow(
                """
                SELECT * FROM piri_vote_choices
                WHERE id = $1 AND board_id = $2 AND deleted_at IS NULL
                """,
                choice_id, board_id
            )
            if not choice:
                raise NotFoundError("ไม่พบตัวเลือกนี้")

            try:
                vote_id = await conn.fetchval(
                    """
                    INSERT INTO piri_votes (board_id, choice_id, user_id, ip_address, user_agent)
                    VALUES ($1, $2, $3, $4, $5)
                    RETURNING id
                    """,
                    board_id, choice_id, user_id, ip, user_agent
                )
            except asyncpg.exceptions.UniqueViolationError:
                # partial unique (board_id, user_id) WHERE deleted_at IS NULL — โหวตซ้ำ
                raise ConflictError("คุณโหวต board นี้ไปแล้ว")

            await conn.execute(
                """
                UPDATE piri_vote_choices
                SET vote_count = vote_count + 1, updated_at = NOW()
                WHERE id = $1
                """,
                choice_id
            )

            # 🛡️ Audit log (ภายใน transaction เดียว — ตามกฎ backend.md)
            from core.logger import AuditLogger
            await AuditLogger("board_service").log(
                conn=conn, action="SUBMIT_VOTE",
                actor_identifier=str(user_id), client_source="web",
                user_id=user_id,
                entity_type="piri_vote", entity_id=vote_id,
                new_values={
                    "board_id": board_id, "board_type": "vote",
                    "choice_id": choice_id, "choice_text": choice["choice_text"],
                },
            )

    return {
        "status": "ok",
        "vote_id": vote_id,
        "board_id": board_id,
        "choice_id": choice_id,
        "choice_text": choice["choice_text"],
    }


# ============================================================
# 💬 5) add_comment — คอมเมนต์/รีพลาย (PIRI Talk + ข้อเสนอแนะ)
# ============================================================
async def add_comment(
    pool: asyncpg.Pool,
    user_id: int,
    board_id: int,
    body: str,
    *,
    parent_id: Optional[int] = None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> int:
    """
    คอมเมนต์/รีพลายใน board:
    - เฉพาะ talk/suggestion board + allow_comments=True (vote board → 400, ปิดคอมเมนต์ → 403)
    - parent_id: reply ต่อคอมเมนต์ (ต้องเป็นคอมเมนต์ที่ยัง active ใน board เดียวกัน)
    - INCREMENT comment_count ใน piri_boards
    - AuditLogger(action="ADD_COMMENT")

    ⚠️ **whitelist ชนิด ไม่ใช่ blacklist** — ทางเขียนต้อง fail-closed (ต่างจาก `get_board_detail`
    ที่ใช้ `else` เปิดกว้างโดยเจตนา): ชนิดใหม่ที่ยังไม่มีใครตรวจว่าควรคอมเมนต์ได้ไหม
    **ต้องถูกปฏิเสธ** ไม่ใช่ถูกเขียนข้อมูลลงไปก่อนแล้วค่อยรู้ตัว
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            board = await conn.fetchrow(
                "SELECT * FROM piri_boards WHERE id = $1 AND deleted_at IS NULL AND status = 'active'",
                board_id
            )
            if not board:
                raise NotFoundError("ไม่พบ board นี้")
            if board["board_type"] not in COMMENTABLE_BOARD_TYPES:
                raise ValidationError("คอมเมนต์ได้เฉพาะ board แบบ PIRI Talk และข้อเสนอแนะ")
            if not board["allow_comments"]:
                raise ForbiddenError("board นี้ปิดคอมเมนต์แล้ว")

            if parent_id:
                # ต้องยัง active และไม่ถูกแอดมินซ่อน (กัน reply ต่อคอมเมนต์ที่ moderation ซ่อนไว้แล้ว)
                # เลือก user_id ด้วย → ใช้แจ้งเตือนเจ้าของคอมเมนต์ต้นทางว่ามีคนตอบกลับ
                parent = await conn.fetchrow(
                    """
                    SELECT id, user_id FROM piri_board_comments
                    WHERE id = $1 AND board_id = $2 AND deleted_at IS NULL AND is_hidden_by_admin = FALSE
                    """,
                    parent_id, board_id
                )
                if not parent:
                    raise NotFoundError("คอมเมนต์ต้นทางที่รีพลายไม่พบ")
                # ⚠️ กันสร้าง reply chain ลึกเกิน MAX_REPLY_DEPTH (recursive Pydantic overflow —
                # adversarial review ยืนยัน chain ~256 ชั้นทำ detail endpoint 500). depth = ความยาว chain ถึง root
                parent_depth = await conn.fetchval(
                    """
                    WITH RECURSIVE chain(depth, cid) AS (
                        SELECT 1, $1::integer
                        UNION ALL
                        SELECT chain.depth + 1, c.parent_comment_id
                        FROM piri_board_comments c
                        JOIN chain ON c.id = chain.cid
                        WHERE c.parent_comment_id IS NOT NULL AND chain.depth < 100
                    )
                    SELECT COALESCE(MAX(depth), 0) FROM chain
                    """,
                    parent_id
                )
                if parent_depth >= MAX_REPLY_DEPTH:
                    raise ValidationError(f"รีพลายได้ลึกไม่เกิน {MAX_REPLY_DEPTH} ชั้น")

            comment_id = await conn.fetchval(
                """
                INSERT INTO piri_board_comments
                    (board_id, parent_comment_id, user_id, body, ip_address, user_agent)
                VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING id
                """,
                board_id, parent_id, user_id, body, ip, user_agent
            )

            await conn.execute(
                """
                UPDATE piri_boards
                SET comment_count = comment_count + 1, updated_at = NOW()
                WHERE id = $1
                """,
                board_id
            )

            # 🛡️ Audit log (ภายใน transaction เดียว — ตามกฎ backend.md)
            from core.logger import AuditLogger
            await AuditLogger("board_service").log(
                conn=conn, action="ADD_COMMENT",
                actor_identifier=str(user_id), client_source="web",
                user_id=user_id,
                entity_type="piri_board_comment", entity_id=comment_id,
                new_values={
                    "board_id": board_id, "parent_comment_id": parent_id,
                    "body": body,
                },
            )

            # 🔔 แจ้งเตือน: reply → เจ้าของคอมเมนต์ต้นทาง; top-level → เจ้าของบอร์ด
            # (ทั้งคู่ group 'board' → badge PIRI Boards; self-guard กันตอบ/คอมเมนต์บอร์ดตัวเอง)
            body_snippet = body if len(body) <= 80 else body[:80] + "…"
            actor_name = await _user_display_name(conn, user_id) or "ผู้ใช้"
            if parent_id and parent["user_id"]:
                await notify(
                    conn, user_id=parent["user_id"],
                    group_type="board", type="board_reply",
                    title="มีผู้ตอบกลับความคิดเห็นของคุณ",
                    body=f'{actor_name}: "{body_snippet}"',
                    entity_type="piri_board_comment", entity_id=comment_id,
                    board_id=board_id,
                    actor_id=user_id, actor_name=actor_name,
                )
            elif board["author_id"]:
                await notify(
                    conn, user_id=board["author_id"],
                    group_type="board", type="board_reply",
                    title="มีคอมเมนต์ใหม่ในกระทู้ของคุณ",
                    body=f'{actor_name}: "{body_snippet}"',
                    entity_type="piri_board_comment", entity_id=comment_id,
                    board_id=board_id,
                    actor_id=user_id, actor_name=actor_name,
                )
            return comment_id


async def get_comment(pool: asyncpg.Pool, board_id: int, comment_id: int) -> dict:
    """ดึงคอมเมนต์เดี่ยว (ยังไม่ soft-delete) — ตอบ API หลัง insert เท่านั้น
    ⚠️ ตั้งใจไม่ filter is_hidden_by_admin: เรียกเฉพาะหลัง add_comment ใน router เดียวกัน —
    ถ้า moderator ซ่อนคอมเมนต์คั่นระหว่าง add กับ get (TOCTOU) จะได้ไม่ 404 ทั้งที่เพิ่ง insert
    (adversarial review จับ: 404 → client retry → คอมเมนต์ซ้ำ)"""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"""
            SELECT c.*, u_comm.full_name AS author_full_name,
                   s_comm.prefix, s_comm.first_name, s_comm.last_name
            FROM piri_board_comments c
            {_COMMENTER_JOIN}
            WHERE c.id = $1 AND c.board_id = $2 AND c.deleted_at IS NULL
            """,
            comment_id, board_id
        )
        if not row:
            raise NotFoundError("ไม่พบคอมเมนต์นี้")
        return {
            "id": row["id"],
            "parent_comment_id": row["parent_comment_id"],
            "user_id": row["user_id"],
            "commenter_name": _display_name(row),
            "commenter_first_name": row.get("first_name"),
            "body": row["body"],
            "is_edited": row["is_edited"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "replies": [],
        }
