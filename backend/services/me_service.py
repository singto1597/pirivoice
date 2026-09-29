"""สถิติส่วนตัว (C3) — นับเฉพาะข้อมูลของเจ้าของเท่านั้น

**ไม่ต้องมี `require_permission`** — ตัวตนคือสิทธิ์ (แบบเดียวกับ `GET /api/issues/summary`)
แต่ router **ต้อง** กันด้วย `_ensure_user()` เพราะ `get_current_user` คืน `user_id = None`
เมื่อถูกเรียกด้วย `X-API-Key` ⇒ ถ้าไม่กัน จะกลายเป็นนับของ user_id NULL เงียบ ๆ

⚠️ **การกรองตามภาคเรียน — จุดที่พลาดง่ายที่สุดในงานนี้**
`created_at` เป็น `TIMESTAMPTZ` แต่ `start_date`/`end_date` เป็น `DATE` ⇒ **ห้ามเขียน**
`created_at >= $2::date` ตรง ๆ เพราะ Postgres จะ cast date → timestamp เที่ยงคืนตาม
**TimeZone ของ session** ซึ่งไม่การันตีว่าเป็นไทย (แล้วแต่ว่าใครตั้ง `TimeZone` ไว้ตอนไหน)
ต้องบอกตรง ๆ ว่าเที่ยงคืนของ **Asia/Bangkok**:

    created_at >= ($2::date::timestamp AT TIME ZONE 'Asia/Bangkok')

และเพราะ `end_date` เป็น **inclusive** (วันสุดท้ายนับด้วย — ดู migration 017)
จึงใช้ `< (end_date + 1 วัน) เที่ยงคืนไทย` ไม่ใช่ `<= end_date`
(เทียบแบบเดียวกับ `dashboard_service.BKK` ที่จัดการวันแบบ UTC+7 ตรง ๆ)

**Fallback:** ถ้ายังไม่มีภาคปัจจุบัน (สถานะตั้งต้นของระบบ) ⇒ ไม่ใส่เงื่อนไขวันที่เลย
= นับทั้งหมด และคืน `"term": None` เพื่อให้ UI เขียนกำกับได้ตรง ๆ ว่า "สถิติทั้งหมด"
— **ห้ามเงียบ ๆ แล้วโชว์เลขที่ดูเหมือนเลขของภาค**
"""
import re
from typing import Optional

import asyncpg

from services import term_service

# จำนวนตัวนับที่คืน — ใช้ในเทสและในเอกสารกำกับ (แก้ที่นี่ที่เดียว)
STAT_FIELDS = (
    "total_reported",
    "resolved_count",
    "in_progress_count",
    "votes_cast",
    "board_comments_posted",
    "issue_comments_posted",
)

# สถานะที่นับเป็น "กำลังดำเนินการ" — ตรงกับที่อื่นในระบบใช้
_OPEN_STATUSES = ("pending", "in_progress", "escalated")

# ฝังเป็น SQL literal ไม่ใช่ parameter — ค่ามาจากค่าคงที่ในไฟล์นี้ ไม่มีทางมาจากผู้ใช้
# (ถ้าใส่เป็น $n ตัวเลข placeholder จะไม่คงที่ระหว่าง "มีภาค" กับ "ไม่มีภาค" แล้ว assert จะพัง)
_OPEN_STATUS_SQL = ", ".join(f"'{s}'" for s in _OPEN_STATUSES)


def _term_clause(col: str) -> str:
    """เงื่อนไขกรองช่วงวันที่ของภาคเรียน (placeholder $2 = start, $3 = end)

    ⚠️ `col` ต้องเป็นชื่อคอลัมน์ที่ **hardcode ในไฟล์นี้เท่านั้น** — ฟังก์ชันนี้ประกอบ SQL
    ด้วย f-string ไม่ใช่ parameter ⇒ ห้ามส่งค่าที่มาจากผู้ใช้เข้ามาเด็ดขาด
    """
    return (
        f" AND {col} >= ($2::date::timestamp AT TIME ZONE 'Asia/Bangkok')"
        f" AND {col} <  ((($3::date + 1)::timestamp) AT TIME ZONE 'Asia/Bangkok')"
    )


async def get_personal_stats(pool: asyncpg.Pool, user_id: int) -> dict:
    """สถิติส่วนตัว 6 ตัวเลข — กรองตามภาคปัจจุบันถ้ามี

    ลอกโครง `public_service.get_system_stats()`: `pool.acquire()` ครั้งเดียวแล้ว `fetchval`
    เรียงกัน — **ห้ามใช้ `asyncio.gather`** เพราะ connection เดียวกันรัน query พร้อมกันไม่ได้
    """
    async with pool.acquire() as conn:
        # ⚠️ เรียก fetch_current_term(conn) ไม่ใช่ get_current_term(pool) — อย่างหลังจะ
        #    acquire connection ใบที่สองทั้งที่เราถืออยู่ ⇒ ถ้า pool เล็กจะค้างตาย
        term = await term_service.fetch_current_term(conn)

        counts = {}
        for key, sql in _QUERIES.items():
            if term:
                sql = sql.format(
                    term=_term_clause(_CREATED_AT_COLUMN[key]), statuses=_OPEN_STATUS_SQL
                )
                params = [user_id, term["start_date"], term["end_date"]]
            else:
                sql = sql.format(term="", statuses=_OPEN_STATUS_SQL)
                params = [user_id]

            assert sql.count("$") == len(params), f"{key}: placeholder ไม่ตรงกับ params"

            counts[key] = await conn.fetchval(sql, *params) or 0

    return {
        "term": _term_out(term),
        **{k: int(counts[k]) for k in STAT_FIELDS},
    }


def _term_out(term: Optional[dict]) -> Optional[dict]:
    """ตัดเอาเฉพาะ 4 ฟิลด์ที่ UI ต้องใช้ — ไม่ส่ง created_at/is_current ออกไปให้รก"""
    if not term:
        return None
    return {
        "id": term["id"],
        "name": term["name"],
        "start_date": term["start_date"],
        "end_date": term["end_date"],
    }


# คอลัมน์เวลาที่ใช้กรองแต่ละตัวนับ (คอลัมน์ทั้งหมดมี created_at TIMESTAMPTZ)
_CREATED_AT_COLUMN = {
    "total_reported": "i.created_at",
    "resolved_count": "i.created_at",
    "in_progress_count": "i.created_at",
    "votes_cast": "v.created_at",
    "board_comments_posted": "bc.created_at",
    "issue_comments_posted": "ic.created_at",
}

# `{term}` ถูกเติมด้วย _term_clause() ตอน runtime — ดูคอมเมนต์ในฟังก์ชันนั้น
_QUERIES = {
    "total_reported": """
        SELECT COUNT(*) FROM issues i
        WHERE i.deleted_at IS NULL AND i.reporter_id = $1{term}
    """,
    "resolved_count": """
        SELECT COUNT(*) FROM issues i
        WHERE i.deleted_at IS NULL AND i.reporter_id = $1
          AND i.status = 'resolved'{term}
    """,
    "in_progress_count": """
        SELECT COUNT(*) FROM issues i
        WHERE i.deleted_at IS NULL AND i.reporter_id = $1
          AND i.status IN ({statuses}){term}
    """,
    "votes_cast": """
        SELECT COUNT(*) FROM piri_votes v
        WHERE v.deleted_at IS NULL AND v.user_id = $1{term}
    """,
    "board_comments_posted": """
        SELECT COUNT(*) FROM piri_board_comments bc
        WHERE bc.deleted_at IS NULL AND bc.user_id = $1{term}
    """,
    "issue_comments_posted": """
        SELECT COUNT(*) FROM issue_comments ic
        WHERE ic.deleted_at IS NULL AND ic.user_id = $1{term}
    """,
}


# ─────────────────────────────────────────────────────────────
# 🧭 C1 — กิจกรรมของฉัน (timeline ส่วนตัว)
#
# ⚠️ **ไม่กรองตามภาคเรียนโดยเจตนา** ต่างจาก C3 — C1 คือ "ทุกอย่างที่เคยทำ"
#    แต่ **ยอดต่อประเภทต้องเท่ากับตัวนับของ C3 ทีละตัว** (สัญญาที่ `me_schemas.py`
#    L21-25 เขียนเตือนไว้ และมีเทสต์ A2 บังคับ) ⇒ ถ้าสองหน้าเลขไม่ตรงกัน
#    ผู้ใช้จะอ่านว่าเป็นบั๊ก
# ─────────────────────────────────────────────────────────────

ACTIVITY_TYPES = (
    "issue_created",
    "vote_cast",
    "board_comment_posted",
    "issue_comment_posted",
)


def _assert_placeholders(sql: str, params: list) -> None:
    """ตรวจว่า **เลข placeholder สูงสุด = จำนวน params**

    ⚠️ **ทำไมไม่ใช้ `sql.count("$")` แบบ `get_personal_stats`** — ที่นั่นแต่ละ placeholder
    ปรากฏครั้งเดียว จึงนับ `$` ได้ผลเท่ากัน แต่คิวรีนี้มี `$1` (user_id) **ซ้ำ 4 ครั้ง**
    (สาขาละครั้งใน `UNION ALL`) ⇒ นับ `$` ได้ 7 ทั้งที่มีของจริง 4 ตัว แล้ว assert จะพัง
    ทั้งที่โค้ดถูก ⇒ **ตัวนับต้องนับให้ถูก** ไม่ใช่เลิกนับ
    (asyncpg บังคับเงื่อนไขนี้อยู่แล้ว ⇒ helper นี้คือด่านที่บอก *สาเหตุ* ก่อนถึง asyncpg)
    """
    highest = max((int(m) for m in re.findall(r"\$(\d+)", sql)), default=0)
    assert highest == len(params), (
        f"placeholder สูงสุด ${highest} ไม่ตรงกับ params {len(params)} ตัว"
    )


# `$1` = user_id ปรากฏ 4 ครั้ง (สาขาละครั้ง) — ตั้งใจ ไม่ใช่การพิมพ์ผิด
#   ⇒ อย่า "รวบ" ให้เหลือครั้งเดียวด้วยการ cross join ตาราง params
#     เพราะจะทำให้อ่านยากขึ้นโดยไม่ได้อะไรกลับมา
_ACTIVITY_CTE = """
    WITH activity AS (
        -- ① เรื่องที่ฉันแจ้ง
        -- ⚠️ ต้องมี `i.deleted_at IS NULL` ให้ตรงกับ `total_reported` ของ C3 เป๊ะ
        --    (เรื่องที่ถูกลบไม่ถูกนับในสถิติ ⇒ feed ก็ต้องไม่นับด้วย)
        SELECT 'issue_created' AS activity_type, 'issue' AS entity_type,
               i.id AS entity_id, i.id AS src_id,
               i.title AS title, i.status AS meta, NULL::text AS excerpt,
               i.created_at AS created_at, FALSE AS is_deleted_source
        FROM issues i
        WHERE i.reporter_id = $1 AND i.deleted_at IS NULL

        UNION ALL

        -- ② โหวต — **LEFT JOIN ทั้งคู่โดยเจตนา ห้ามเปลี่ยนเป็น INNER**
        --    `votes_cast` ของ C3 นับแถวใน `piri_votes` ล้วน ๆ (ไม่ join อะไรเลย)
        --    ⇒ ที่นี่ต้องไม่ให้ join ตัดแถวทิ้ง ไม่งั้นยอดไม่ตรงกัน
        --    ★ ของจริงที่เจอตอนตรวจสคีมา: `piri_vote_choices` **มี `deleted_at` ของตัวเอง**
        --      ⇒ ถ้าใช้ INNER JOIN แล้วมีคน soft-delete ตัวเลือก โหวตนั้นจะหายจาก feed
        --        ทั้งที่ C3 ยังนับอยู่ = เลขไม่ตรงกันแบบหาสาเหตุยากมาก
        --    `meta` = ข้อความตัวเลือกที่โหวต (เป็น `null` ได้ถ้าตัวเลือกหายไปจริง ๆ)
        SELECT 'vote_cast', 'board',
               pb.id, v.id,
               COALESCE(pb.title, '(ต้นทางถูกลบแล้ว)'), vc.choice_text, NULL,
               v.created_at,
               (pb.id IS NULL OR pb.deleted_at IS NOT NULL OR pb.status = 'hidden')
        FROM piri_votes v
        LEFT JOIN piri_vote_choices vc ON vc.id = v.choice_id
        LEFT JOIN piri_boards pb ON pb.id = v.board_id
        --    ⚠️ ลิงก์จะพาไป 404 ถ้าต้นทางเปิดไม่ได้ ⇒ 'เปิดไม่ได้' มี **สองทาง**:
        --       `deleted_at IS NOT NULL` (ลบ) และ `status = 'hidden'` (สภากดซ่อนบอร์ด
        --       — คนละคอลัมน์!) · `get_board_detail()` 404 ทั้งคู่
        --       ⇒ ห้ามใช้ `status <> 'active'` เพราะ `'closed'` ยังเปิดดูได้ (ไม่ 404)
        WHERE v.user_id = $1 AND v.deleted_at IS NULL

        UNION ALL

        -- ③ คอมเมนต์ใน PIRI Boards — `excerpt` ตัดที่ SQL ด้วย `LEFT()` ซึ่งนับ
        --    **ตัวอักษร** ไม่ใช่ byte ⇒ ปลอดภัยกับภาษาไทย (และไม่ลาก body เต็มผ่าน asyncpg)
        SELECT 'board_comment_posted', 'board',
               pb.id, bc.id,
               COALESCE(pb.title, '(ต้นทางถูกลบแล้ว)'), NULL, LEFT(bc.body, 160),
               bc.created_at,
               (pb.id IS NULL OR pb.deleted_at IS NOT NULL OR pb.status = 'hidden')
        FROM piri_board_comments bc
        LEFT JOIN piri_boards pb ON pb.id = bc.board_id
        WHERE bc.user_id = $1 AND bc.deleted_at IS NULL

        UNION ALL

        -- ④ คอมเมนต์ในเรื่อง — บอร์ด/เรื่องที่ถูกลบ **ยังอยู่ใน feed** แต่ติดธง
        --    `is_deleted_source` (คอมเมนต์ของฉันยังเป็นของฉัน แม้ต้นทางจะถูกซ่อน)
        SELECT 'issue_comment_posted', 'issue',
               i.id, ic.id,
               COALESCE(i.title, '(ต้นทางถูกลบแล้ว)'), NULL, LEFT(ic.body, 160),
               ic.created_at,
               (i.id IS NULL OR i.deleted_at IS NOT NULL)
        FROM issue_comments ic
        LEFT JOIN issues i ON i.id = ic.issue_id
        WHERE ic.user_id = $1 AND ic.deleted_at IS NULL
    )
"""


async def get_my_activity(
    pool: asyncpg.Pool,
    user_id: int,
    *,
    activity_type: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
) -> dict:
    """timeline ส่วนตัว รวม 4 ประเภท — envelope + `counts` แยกประเภท

    ⚠️ `activity_type` ถูก validate ด้วย `Literal` ที่ router แล้ว ⇒ 422 มาก่อนถึงนี่
       และค่ามันถูกส่งเป็น **parameter** ไม่ใช่ f-string ⇒ ไม่มีทางเข้า SQL
    """
    async with pool.acquire() as conn:
        # ยอดแยกประเภท — **ไม่ใส่ filter** ⇒ ใช้ทำป้ายตัวกรองได้เสมอ
        # (ป้ายต้องโชว์ยอดของ "ทั้งหมด" ไม่ใช่ยอดของตัวที่กำลังกรองอยู่)
        rows = await conn.fetch(
            _ACTIVITY_CTE
            + "SELECT activity_type, COUNT(*)::int AS cnt FROM activity GROUP BY activity_type",
            user_id,
        )
        counts = {t: 0 for t in ACTIVITY_TYPES}  # zero-fill: ประเภทที่ไม่มีข้อมูลต้องได้ 0 ไม่ใช่หายไป
        for r in rows:
            counts[r["activity_type"]] = r["cnt"]

        # `total` ของลิสต์ = ยอดของประเภทที่กรอง (ถ้ากรอง) ⇒ ไม่ต้อง COUNT ซ้ำอีกรอบ
        # และรับประกันว่า `total` ตรงกับ `counts[activity_type]` เสมอ (สัญญา A7)
        total = counts.get(activity_type, 0) if activity_type else sum(counts.values())

        sql = _ACTIVITY_CTE + """
            SELECT activity_type, entity_type, entity_id, src_id,
                   title, meta, excerpt, created_at, is_deleted_source
            FROM activity
            WHERE ($2::text IS NULL OR activity_type = $2)
            -- ⚠️ **ห้ามตัด tie-break ออก** — `CURRENT_TIMESTAMP` คือเวลา *เริ่มทรานแซกชัน*
            --    ⇒ แถวที่ถูกสร้างในทรานแซกชันเดียวกันมี `created_at` **เท่ากันเป๊ะ**
            --    (เช่น คอมเมนต์ 2 อันในบอร์ดเดียวที่ insert พร้อมกัน) ⇒ ถ้าเรียงด้วย
            --    `created_at` อย่างเดียว ลำดับระหว่างสองแถวนั้น "แล้วแต่ดวง"
            --    = pagination ได้แถวซ้ำ/แถวหายข้ามหน้า (เทสต์ A8 บังคับเรื่องนี้)
            --    `src_id` = PK ของตารางต้นทาง ⇒ ไม่ซ้ำภายในประเภทเดียวกัน
            --    ⇒ (created_at, activity_type, src_id) ไม่มีทางซ้ำกัน
            ORDER BY created_at DESC, activity_type, src_id DESC
            LIMIT $3 OFFSET $4
        """
        params = [user_id, activity_type, limit, offset]
        _assert_placeholders(sql, params)
        items = await conn.fetch(sql, *params)

    return {
        "items": [dict(r) for r in items],
        "total": total,
        "page": offset // limit + 1 if limit else 1,
        "page_size": limit,
        "pages": (total + limit - 1) // limit if limit and total else 0,
        "counts": counts,
    }
