"""Home summary (B1) — รวมทุกอย่างที่หน้าแรกต้องใช้ไว้ใน request เดียว

**ทำไมต้องมี:** `Home.vue` เดิมยิง 5 endpoint ขนานกัน (summary / received / reports /
dashboard / announcements) ซึ่งแปลว่าเปิดหน้าเดียว = 5 round-trip + 5 การต่อ DB
รอบนี้ยุบ **3 อย่างที่ทุกคนเห็นเหมือนกัน** (ประกาศ · สรุปเรื่องของฉัน · สถิติส่วนตัว)
บวก **2 คิวใหม่** เข้าเป็นตัวเดียว ⇒ เหลือ 1 call

**เส้นที่ลากไว้ (ผู้ใช้เลือก "ตัวเดียว" แต่ไม่เอาทุกอย่าง):**
- ❌ **แดชบอร์ด** — `get_dashboard()` รัน 5 aggregate pass ทั้งโรงเรียน
  ถ้าย้ายเข้ามาจะทำให้ **Home ช้าลงทุกคน** เพื่อตอบคนกลุ่มเดียวที่มี `VIEW_DASHBOARD`
  ⇒ คงเป็น call เดิม แยกไป
- ❌ **คิวรายงาน** — permission-gated (`isCouncilAuthority`) ⇒ แยกไปเช่นกัน

⇒ หน้า Home ยิงแค่ `getHomeSummary()` + อีก 2 ตัวที่ยิงเฉพาะคนมีสิทธิ์

⚠️ **ห้ามเรียก service อื่นขณะถือ connection อยู่** — `public_service.get_announcements`,
`issue_service.my_issue_summary`, `me_service.get_personal_stats` ต่างก็
`pool.acquire()` เองทั้งหมด (pool max = 10) ⇒ ที่นี่เรียก **เรียงกันแบบ await**
และปล่อย connection ของตัวเองก่อนทุกครั้ง · **ห้ามใช้ `asyncio.gather`** เพราะจะยึด
connection พร้อมกันหลายใบโดยไม่จำเป็น

⭐ กติกาเดียวกันนี้คุม `event_service.list_closing_soon_events` (4.5) ด้วย — มัน
`pool.acquire()` เองเหมือนกัน ⇒ เรียกต่อ **หลัง** `_queues()` คืนค่า (ที่จุดนั้น
connection ของ `_queues` ถูกคืนเข้าพูลแล้ว) ไม่ใช่เรียกซ้อนข้างใน `_queues`
"""
import asyncpg

from services import event_service, issue_service, me_service, public_service

# จำนวนรายการสูงสุดต่อคิว — หน้าแรกไม่ใช่หน้าคิวเต็ม
QUEUE_LIMIT = 5

# ── "รอฉันตอบ" ───────────────────────────────────────────────
# ⚠️ เป้าแคบกว่า list_issues(received=True) เดิมโดยเจตนา — ตัวนั้นใช้ `involved_cond`
#    ที่กว้างกว่ามาก (reporter OR assignee OR escalation OR countdown) ⇒ ผู้ใช้เห็น
#    เรื่องที่ไม่ใช่ "ต้องรอฉันตอบ" ปนอยู่เยอะ · ที่นี่เอา `current_assignee_id = $1`
#    ซึ่งกรองด้วยตัวตนอยู่แล้ว ⇒ **ไม่ต้องมี class_role gate** (แน่นกว่า gate ด้วย role)
#
# เรียง: ด่วนก่อน แล้วในความด่วนเดียวกันเอาที่ค้างนานสุดขึ้นก่อน (created_at ASC)
_ORDER_PRIORITY = """
    CASE i.priority
        WHEN 'urgent' THEN 0
        WHEN 'high' THEN 1
        WHEN 'normal' THEN 2
        ELSE 3
    END
"""

_PENDING_ON_ME_SQL = f"""
    SELECT i.id, i.title, i.status, i.priority, i.current_level, i.created_at,
           r.room_name
    FROM issues i
    LEFT JOIN rooms r ON r.id = i.room_id
    WHERE i.deleted_at IS NULL
      AND i.current_assignee_id = $1
      AND i.status IN ('pending', 'in_progress', 'escalated')
    ORDER BY {_ORDER_PRIORITY}, i.created_at ASC
    LIMIT {QUEUE_LIMIT}
"""

# นับทั้งหมดของเงื่อนไขเดียวกัน (ไม่ LIMIT) — ใช้บอกว่า "และอีก N เรื่อง"
_PENDING_ON_ME_COUNT_SQL = """
    SELECT COUNT(*)
    FROM issues i
    WHERE i.deleted_at IS NULL
      AND i.current_assignee_id = $1
      AND i.status IN ('pending', 'in_progress', 'escalated')
"""

# ── "โหวตที่ยังไม่ได้โหวต" ────────────────────────────────────
# ⚠️ `v.deleted_at IS NULL` ใน NOT EXISTS **ห้ามลืม** — unique index ของ piri_votes
#    เป็น *partial* (`WHERE deleted_at IS NULL`) ⇒ โหวตที่ soft-delete แล้วต้องกลับมา
#    โหวตได้ ถ้าลืมเงื่อนไขนี้ บอร์ดจะหายจากลิสต์ทั้งที่โหวตใหม่ได้ (skills.md L434)
_UNVOTED_BOARDS_SQL = f"""
    SELECT b.id, b.title, b.created_at,
           (SELECT COUNT(*) FROM piri_votes v
             WHERE v.board_id = b.id AND v.deleted_at IS NULL) AS vote_count
    FROM piri_boards b
    WHERE b.deleted_at IS NULL
      AND b.status = 'active'
      AND b.board_type = 'vote'
      AND NOT EXISTS (
          SELECT 1 FROM piri_votes v
          WHERE v.board_id = b.id AND v.user_id = $1 AND v.deleted_at IS NULL
      )
    ORDER BY b.created_at DESC
    LIMIT {QUEUE_LIMIT}
"""

_UNVOTED_BOARDS_COUNT_SQL = """
    SELECT COUNT(*)
    FROM piri_boards b
    WHERE b.deleted_at IS NULL
      AND b.status = 'active'
      AND b.board_type = 'vote'
      AND NOT EXISTS (
          SELECT 1 FROM piri_votes v
          WHERE v.board_id = b.id AND v.user_id = $1 AND v.deleted_at IS NULL
      )
"""


async def get_home_summary(pool: asyncpg.Pool, user_id: int) -> dict:
    """ทุกอย่างที่หน้าแรกต้องใช้ — เรียก service เดิมซ้ำ ไม่เขียน query ซ้ำ

    ⚠️ **ประกาศไม่ถูกตัด/ไม่ถูก slice** — `get_announcements()` จงใจไม่มี LIMIT
    ตามที่เจ้าของระบบสั่ง ("โชว์ทั้งหมดที่ยังไม่ถอดออก") ⇒ ส่งออกไปทั้งชุดเหมือนเดิม
    """
    announcements = await public_service.get_announcements(pool)
    my_issues = await issue_service.my_issue_summary(pool, user_id)
    stats = await me_service.get_personal_stats(pool, user_id)
    pending_on_me, pending_total, unvoted, unvoted_total = await _queues(pool, user_id)
    # ⏳ คิวที่ 3 (4.5) — เรียก **หลัง** `_queues` ปล่อย connection แล้ว ไม่ใช่ซ้อนข้างใน
    #    (เหตุผลอยู่ใน docstring ของโมดูลนี้: pool max = 10 และห้ามยึด connection ซ้อนกัน)
    closing = await event_service.list_closing_soon_events(pool, user_id, limit=QUEUE_LIMIT)

    return {
        "announcements": announcements,
        "my_issues": my_issues,
        "pending_on_me": pending_on_me,
        "pending_on_me_total": pending_total,
        "unvoted_boards": unvoted,
        "unvoted_boards_total": unvoted_total,
        "closing_soon_events": closing["items"],
        "closing_soon_events_total": closing["total"],
        "stats": stats,
    }


async def _queues(pool: asyncpg.Pool, user_id: int) -> tuple[list, int, list, int]:
    """2 คิวใหม่ + ยอดรวม — ใช้ connection เดียวกัน 4 query (ไม่ใช่ 4 connection)

    คืน (pending, pending_total, unvoted, unvoted_total)
    """
    # SQL ทั้ง 4 ตัวประกอบจาก f-string (มี `{_ORDER_PRIORITY}` / `{QUEUE_LIMIT}` ฝังอยู่)
    # ⇒ กันพลาดด้วยการนับ placeholder ตรง ๆ (บทเรียน skills.md L507 — เคยพังมาแล้ว)
    for sql in (_PENDING_ON_ME_SQL, _UNVOTED_BOARDS_SQL):
        assert sql.count("$") == 1, "placeholder ในลิสต์ query ไม่ตรงกับ params"
    for sql in (_PENDING_ON_ME_COUNT_SQL, _UNVOTED_BOARDS_COUNT_SQL):
        assert sql.count("$") == 1, "placeholder ใน count query ไม่ตรงกับ params"

    async with pool.acquire() as conn:
        pending = await conn.fetch(_PENDING_ON_ME_SQL, user_id)
        pending_total = await conn.fetchval(_PENDING_ON_ME_COUNT_SQL, user_id) or 0
        unvoted = await conn.fetch(_UNVOTED_BOARDS_SQL, user_id)
        unvoted_total = await conn.fetchval(_UNVOTED_BOARDS_COUNT_SQL, user_id) or 0

    return (
        [dict(r) for r in pending],
        int(pending_total),
        [dict(r) for r in unvoted],
        int(unvoted_total),
    )
