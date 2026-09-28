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
