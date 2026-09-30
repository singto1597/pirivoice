"""Event Service — กิจกรรมของสภา (D1: สร้าง/เผยแพร่/ยกเลิก + ลงทะเบียน + คิวสำรอง)

⭐ **สองแกนสถานะที่เป็นอิสระต่อกัน — อย่ายุบรวม** (บทเรียนเดียวกับ `announcements`):

    | แกน            | คอลัมน์       | ค่า                                  |
    |----------------|---------------|--------------------------------------|
    | การเผยแพร่     | `status`      | draft / published / cancelled        |
    | การมีอยู่      | `deleted_at`  | NULL = ยังอยู่ / NOT NULL = ถูกลบ     |

  `status` **ไม่ใช่** soft delete — กิจกรรมที่ยกเลิกยังต้องอยู่ในรายการ (พร้อมป้าย "ยกเลิก")
  เพราะคนที่ลงทะเบียนไปแล้วต้องเปิดดูได้ว่าเกิดอะไรขึ้น · การ "ลบ" คือ `deleted_at`
  ซึ่งซ่อนจากทุกมุมมองและกู้คืนได้
  ⇒ กิจกรรมที่ "ยกเลิก + ถูกลบ" เป็นไปได้ และจะอยู่แท็บ `deleted` ที่เดียว (ไม่โผล่สองแท็บ)

⭐ **`capacity IS NULL` = ไม่จำกัด** — `0` ไม่ใช่ "ไม่จำกัด" (CHECK `capacity > 0` กันไว้)
  ⇒ โค้ดทุกที่ที่เทียบจำนวนต้องเช็ค `capacity is None` **ก่อน** เทียบตัวเลข
  ถ้าเขียน `taken >= capacity` ลอย ๆ จะได้ `TypeError` เทียบ int กับ None

⭐ **การแจ้งเตือนยิงตอน "เผยแพร่" เท่านั้น ไม่ใช่ตอนสร้าง** (ผู้ใช้เลือก) ⇒ กิจกรรมเกิดเป็น
  `draft` เสมอ และ `publish_event()` เป็น **ที่เดียว** ที่เรียก `notify_fanout`
  ⇒ การแก้ `status` ตรง ๆ ผ่าน PATCH ต้องเป็นไปไม่ได้ (`EventUpdateRequest` ไม่มีฟิลด์นี้)
  ไม่งั้นกิจกรรมที่เผยแพร่แล้วจะไม่มีใครรู้ — เงียบโดยไม่มีร่องรอย

⭐ **การลงทะเบียนเขียน audit log ด้วย** — ต่างจาก A2 (ตั้งค่าการแจ้งเตือน) / C2 (บันทึกไว้)
  ที่เป็น *ค่าส่วนตัว* ⇒ ไม่ audit · ที่นี่เป็น **state สาธารณะที่แย่งกันใช้ของจำกัด**
  (ที่นั่งมีจำนวนจำกัด และคนอื่นเห็นว่าคุณเอาไป) ⇒ ต้องมีร่องรอยว่าใครได้ที่นั่งตอนไหน
  — หลักเดียวกับ `board_service.create_suggestion` / `submit_vote`

กฎตาม docs/rules/backend.md:
  - SQL ทั้งหมดอยู่ที่ชั้นนี้ ใช้ parameterized query ($1..$n) ห้าม f-string ใส่ค่า
  - ทุก mutation อยู่ใน `async with conn.transaction():` + audit ใน transaction เดียวกัน
  - `created_by` / `updated_by` เป็น INTEGER เปล่า **ไม่มี FK** (บทเรียน: "ลบผู้ใช้ = หลักฐานหาย")
    ⇒ อ่านชื่อต้อง LEFT JOIN users เอง และต้อง LEFT เท่านั้น
  - เปลี่ยนสถานะที่ผิดกติกาบังคับด้วยเงื่อนไขใน `WHERE` ไม่ใช่ `if` ใน Python
    ⇒ กดซ้ำ/กดผิดลำดับได้ 404 โดยไม่ทับ timestamp เดิม
"""
import math
from typing import Optional

import asyncpg

from core import check_in_token
from core.exceptions import NotFoundError, ValidationError
from core.logger import AuditLogger
from core.rbac import require_permission_anywhere
from models.event_schemas import EVENT_CATEGORIES
from services import notification_service

# คอลัมน์ที่ยอมให้แก้ผ่าน PATCH — allowlist เพราะชื่อคอลัมน์ถูก interpolate ลง SQL
#
# ⚠️ **ไม่มี `status` / `published_at` / `cancelled_at` โดยเจตนา** — การเผยแพร่ต้องผ่าน
#    `publish_event()` ซึ่งเป็นที่เดียวที่ยิงแจ้งเตือน · ถ้าใส่ `status` เข้ามาที่นี่
#    PATCH ใบเดียวจะเผยแพร่กิจกรรมแบบเงียบ ๆ ได้
_EDITABLE_COLUMNS = (
    "title", "description", "location", "cover_image_url",
    "event_date", "registration_deadline", "capacity", "category",
)

# สถานะที่ใช้กรองในรายการฝั่งจัดการ
# ⭐ **dict นี้คือจุดเดียวที่นิยามคำว่าสถานะ** — ใช้ทั้ง COUNT(*) และคิวรีหลัก ⇒ total กับ
#    items ตรงกันเสมอโดยไม่ต้องแก้อะไรเพิ่ม
# ⚠️ `deleted` กรองด้วย `deleted_at IS NOT NULL` **อย่างเดียว** (ไม่สนใจ `status`)
#    ⇒ แถวที่ "ยกเลิก + ถูกลบ" พร้อมกันอยู่แท็บนี้ที่เดียว ไม่โผล่สองแท็บ
# ⚠️ `live` = "ทุกอย่างที่ยังไม่ถูกลบ" (ทั้ง draft/published/cancelled) — เป็นค่าเริ่มต้น
#    ของหน้ารายการ เพราะสภาต้องเห็นร่างที่ยังไม่เผยแพร่ของตัวเองด้วย
_STATUS_CONDITIONS = {
    "live": "e.deleted_at IS NULL",
    "draft": "e.deleted_at IS NULL AND e.status = 'draft'",
    "published": "e.deleted_at IS NULL AND e.status = 'published'",
    "cancelled": "e.deleted_at IS NULL AND e.status = 'cancelled'",
    "deleted": "e.deleted_at IS NOT NULL",
    "all": "TRUE",
}

# ขอบเขตของรายการฝั่งนักเรียน (เห็นเฉพาะที่เผยแพร่แล้ว + ยังไม่ถูกลบ)
_PUBLIC_SCOPES = {
    "upcoming": "e.event_date >= NOW()",
    "past": "e.event_date < NOW()",
    "all": "TRUE",
}

# 🏫 LEFT JOIN users สองครั้ง (ผู้สร้าง/ผู้แก้) — ต้อง LEFT เพราะ created_by เป็น NULL ได้
#    (กิจกรรมที่ seed มาก่อนมีฟีเจอร์นี้ / ผู้ใช้อาจถูกลบไปแล้ว)
#    ⚠️ **ห้าม JOIN students** — user หนึ่งคนมีได้หลายแถว (หลายห้อง) → รายการจะบานเป็นซ้ำ
#       (บทเรียนเดียวกับ `announcement_service._SELECT_COLUMNS`)
_JOINS = """
    LEFT JOIN users cu ON cu.id = e.created_by
    LEFT JOIN users uu ON uu.id = e.updated_by
"""

# นับที่นั่ง/คิวด้วย LATERAL ครั้งเดียวแล้วให้ทุกคอลัมน์ที่ต้องใช้ต่อยอดจากมัน
# ⚠️ ทำไมต้อง LATERAL: `registered_count` ถูกใช้ทั้งตอนแสดงผล **และ** คำนวณ
#    `seats_remaining` — ถ้าเขียนเป็น scalar subquery สองอันจะนับซ้ำสองรอบต่อแถว
#    และถ้าอยากอ้าง alias ใน SELECT เดียวกันจะทำไม่ได้ (SQL ไม่อนุญาต)
# ⚠️ `COUNT(*) FILTER` นับเฉพาะแถวที่เข้าเงื่อนไข ⇒ คิวรีเดียวได้สองตัวนับ โดยไม่ต้อง GROUP BY
_STATS_JOIN = """
    LEFT JOIN LATERAL (
        SELECT
            COUNT(*) FILTER (WHERE r.status IN ('registered', 'checked_in')) AS registered_count,
            COUNT(*) FILTER (WHERE r.status = 'waitlisted') AS waitlisted_count
        FROM event_registrations r
        WHERE r.event_id = e.id
    ) c ON TRUE
"""

# คอลัมน์ดิบของกิจกรรม (ยังไม่คำนวณอะไรเพิ่ม) — ใช้ร่วมกันทั้งสองมุมมอง
_ROW_COLUMNS = """
    e.id, e.title, e.description, e.location, e.cover_image_url,
    e.event_date, e.registration_deadline, e.capacity, e.category,
    e.status, e.published_at, e.cancelled_at,
    e.created_at, e.updated_at, e.deleted_at,
    e.created_by, e.updated_by
"""

# ฝั่งจัดการ — เพิ่มชื่อผู้ดูแล + ตัวนับสองตัว
_MANAGE_COLUMNS = f"""
    {_ROW_COLUMNS},
    cu.full_name AS created_by_name,
    uu.full_name AS updated_by_name,
    c.registered_count::int AS registered_count,
    c.waitlisted_count::int AS waitlisted_count
"""

# ฝั่งนักเรียน — `created_by` / `updated_by` / `deleted_at` **ไม่หลุดถึงนักเรียน** โดยเจตนา
# ⚠️ คอลัมน์เหล่านี้ยังถูก SELECT มาตรง ๆ (มาจาก `_ROW_COLUMNS` ร่วมกัน) — ตัวที่กรองออก
#    คือ `EventPublicOut` ⇒ **ด่านอยู่ที่ schema ไม่ใช่ที่ SQL** (ดู docstring ของ
#    `models/event_schemas.py`: ต่อให้ UI เผลอ bind ทั้ง object ก็ไม่มีข้อมูลผู้ดูแลหลุด)
# ⚠️ `published_at` / `cancelled_at` **ผ่านออกไปถึงนักเรียน** — ไม่ใช่ข้อมูลผู้ดูแล
#    แต่เป็น "ประกาศเมื่อไหร่ / ยกเลิกเมื่อไหร่" ⇒ อย่าเอาสองตัวนี้ไปรวมกับลิสต์ข้างบน
#
# ⚠️ `is_registration_open` คำนวณ **ที่ SQL** ไม่ใช่ Python — เขตเวลาของ DB กับของโปรเซส
#    ไม่มีทางรับประกันว่าตรงกัน และกติกา "ปิดเมื่อถึงวันจัด/เลยกำหนด" เป็นกติกาของ *ระบบ*
#    ⇒ ต้องตัดสินที่เดียว (แหล่งความจริงเดียว) ไม่ใช่ที่สองที่แล้วมาเถียงกัน
#
# ⭐ แยกกติกาออกมาเป็นชื่อ (`_REGISTRATION_OPEN_SQL`) **เพราะมีผู้ใช้มากกว่าหนึ่งที่** —
#    `_PUBLIC_COLUMNS` และ `list_closing_soon_events` (4.5) ⇒ ถ้าปล่อยเป็นสำนวนในที่เดียว
#    แล้วอีกที่พิมพ์ซ้ำ วันที่มีคนแก้ (เช่น เพิ่ม "ปิดรับล่วงหน้า 1 วัน") จะแก้ไม่ครบ
#    แล้วบล็อกในหน้าแรกจะชี้กิจกรรมที่สมัครไม่ได้ ซึ่งเชื่อได้ยากว่าเกิดจากอะไร
_REGISTRATION_OPEN_SQL = """(
    e.status = 'published' AND e.deleted_at IS NULL
    AND e.event_date > NOW()
    AND (e.registration_deadline IS NULL OR e.registration_deadline >= NOW())
)"""

# ⏳ **เวลาที่ "ปิดรับ" จริง** — อันที่ถึงก่อน ระหว่าง deadline กับวันจัด
#
# 🚨 ต้องเป็น `LEAST` **ไม่ใช่ `COALESCE`** — `_REGISTRATION_OPEN_SQL` ปิดที่ *วันจัด*
#    ไม่ว่าอย่างไร ⇒ ถ้าแถวไหนมี deadline หลังวันจัด แล้วเราใช้ COALESCE จะได้ deadline
#    กลับมา แล้วบล็อก "ใกล้ปิดรับ" จะบอกว่ายังเปิดรับอยู่ทั้งที่เลยวันจัดไปแล้ว
#
# ⚠️ `event_date` ไม่มีทางเป็น NULL (NOT NULL) ⇒ `LEAST` ไม่คืน NULL
#    แต่ `COALESCE` ข้างในยังต้องมี เพราะ `registration_deadline` เป็น NULL ได้จริง
#    (= "ไม่ตั้งกำหนด ปิดเอาวันจัด") และนั่นคือกรณีที่พบบ่อยที่สุด
#
# ℹ️ ปกติเส้นทาง API กัน deadline-หลังวันจัดไว้แล้วที่ `_assert_deadline_not_after_event`
#    ⇒ `LEAST` กับ `COALESCE` จึงให้ผลเท่ากัน — `LEAST` เป็นด่านที่สองรองรับแถวที่
#    bypass ด่านนั้น (seed ตรงเข้า DB / แถวก่อนมีด่าน) ไม่ใช่สมมติฐานว่าด่านพัง
#
# ⚠️ ค่านี้เทียบเท่ากับ `_REGISTRATION_OPEN_SQL` ทุกกรณี **ยกเว้น** ขอบเขตที่ `event_date`
#    เท่ากับ `NOW()` พอดี (ตัวบนใช้ `>` ตัวนี้ใช้ `>=`) ซึ่งเกิดขึ้นไม่ได้ในทางปฏิบัติ
#    (timestamptz ความละเอียดไมโครวินาที) — และมีเทสต์ยืนยันว่าสองตัวไม่ขัดกัน
_CLOSES_AT_SQL = "LEAST(e.event_date, COALESCE(e.registration_deadline, e.event_date))"

# หน้าต่าง "ใกล้ปิดรับ" ของบล็อกในหน้าแรก (4.5)
CLOSING_SOON_DAYS = 7

_PUBLIC_COLUMNS = f"""
    {_ROW_COLUMNS},
    c.registered_count::int AS registered_count,
    c.waitlisted_count::int AS waitlisted_count,
    CASE
        WHEN e.capacity IS NULL THEN NULL
        ELSE GREATEST(0, e.capacity - c.registered_count)::int
    END AS seats_remaining,
    {_REGISTRATION_OPEN_SQL} AS is_registration_open,
    {_CLOSES_AT_SQL} AS closes_at
"""

# เงื่อนไข "ผู้ใช้รายนี้สมัครอยู่ไหม" สำหรับเติมป้ายในลิสต์ — LEFT JOIN โดยเจตนา
# เพื่อให้แถวที่ยังไม่สมัครยังออกมา (แค่ my_registration_id เป็น NULL)
# ⚠️ `$1` ถูกจองให้ `user_id` **เสมอ** ในคิวรีฝั่ง public ⇒ limit/offset ต้องเป็น $2/$3
_MY_REG_JOIN = """
    LEFT JOIN event_registrations mr
           ON mr.event_id = e.id AND mr.user_id = $1
"""

_ORDER_BY_MANAGE = """
    ORDER BY
        (CASE e.status WHEN 'draft' THEN 0 WHEN 'published' THEN 1 ELSE 2 END),
        e.event_date DESC,
        e.id DESC
"""

# ฝั่งนักเรียน: ใกล้ถึงก่อน — กิจกรรมที่ยังไม่จัดต้องอยู่บนสุดเสมอ
_ORDER_BY_PUBLIC = """
    ORDER BY e.event_date ASC, e.id ASC
"""


def _rows(data: dict) -> dict:
    """ตัดคีย์ที่ models ไม่รู้จักออก — `my_registration_id` ใช้แค่คิดสถานะ ไม่ได้ส่งออก"""
    data.pop("my_registration_id", None)
    return data


def _public_row(row) -> dict:
    """แถวฝั่งนักเรียน — แปลง 'cancelled' เป็น None (UI ต้องเห็นเป็น "ยังไม่สมัคร")"""
    data = _rows(dict(row))
    if data.get("my_registration_status") == "cancelled":
        data["my_registration_status"] = None
    return data


def _seat_token(event_id: int, registration_id: int, status: str) -> Optional[str]:
    """บัตรเช็คอินของแถวนี้ — `None` สำหรับคนที่ยังไม่ถือที่นั่ง

    ⭐ **ที่เดียวที่นิยาม "ใครมีสิทธิ์ได้บัตร"** — ทั้ง `get_my_registration` และ `register_event`
       เรียกตัวนี้ ⇒ สองเส้นทางไม่มีทางตีความไม่ตรงกัน (ถ้าต่างคนต่างเขียน `if status in (...)`
       เอง วันหน้าที่เพิ่มสถานะใหม่จะมีเส้นทางหนึ่งลืม = บัตรโผล่/หายไม่ตรงกันโดยไม่มีใครรู้)

    ⚠️ `waitlisted` **ไม่ได้บัตร** — ยังไม่มีที่นั่งให้เช็คอิน · ถ้าให้ไป สภาที่สแกนจะเจอ
       "อยู่ในคิวสำรอง" ซึ่งควรรู้ตั้งแต่ยังไม่ยื่นบัตร (ผู้ใช้จะยื่นบัตรที่ตัวเองมีอยู่แล้ว)
    """
    if status not in ("registered", "checked_in"):
        return None
    return check_in_token.make(event_id, registration_id)


def _assert_deadline_not_after_event(event_date, registration_deadline) -> None:
    """
    กำหนดปิดรับสมัครต้องไม่หลังวันจัดกิจกรรม

    ⚠️ **ตรวจที่ชั้นนี้ ไม่ใช่ที่ Pydantic** — PATCH เป็น partial ⇒ ที่ชั้น schema ไม่มีทาง
    รู้ค่าอีกฝั่งที่ผู้ใช้ไม่ได้ส่งมา ⇒ ตรวจที่นั่นจะได้ด่านที่ถูกเฉพาะตอน POST
    ซึ่งเป็นครึ่งเดียวของเส้นทาง (คลาสสิกของ "ด่านที่ป้องกันได้ครึ่งเดียว")
    """
    if registration_deadline is not None and registration_deadline > event_date:
        raise ValidationError("กำหนดปิดรับสมัครต้องไม่หลังวันจัดกิจกรรม")


async def _fetch_one(conn: asyncpg.Connection, event_id: int) -> dict:
    """อ่านกิจกรรม 1 แถวในมุมมองฝั่งจัดการ (พร้อมชื่อผู้ดูแล + ตัวนับ)"""
    row = await conn.fetchrow(
        f"""
        SELECT {_MANAGE_COLUMNS}
        FROM events e
        {_JOINS}
        {_STATS_JOIN}
        WHERE e.id = $1
        """,
        event_id,
    )
    return dict(row) if row else {}


async def _envelope(conn, *, count_sql: str, count_params: list, rows_sql: str,
                    rows_params: list, limit: int, offset: int) -> dict:
    """ประกอบ envelope {items,total,page,page_size,pages} จากคิวรีสองอัน

    ⚠️ **นับ total แยกจากคิวรีหลัก — ห้ามใช้ `COUNT(*) OVER()`** เพราะเมื่อ `offset` เลย
    หน้าสุดท้ายไปแล้ว แถวที่ return จะว่าง ⇒ อ่าน total ไม่ได้ ⇒ ได้ 0 ผิด ๆ

    ⚠️ **`count_params` กับ `rows_params` แยกกันโดยเจตนา — ห้ามรวมเป็นชุดเดียว**
    คิวรีนับมีแค่ `WHERE` ที่บางครั้งไม่มี placeholder เลย (เช่น `_PUBLIC_SCOPES` เทียบ `NOW()`
    ล้วน) แต่คิวรีแถวมี `$1` จองไว้ให้ `_MY_REG_JOIN` ⇒ ถ้าใช้ชุดเดียวกัน asyncpg จะโยน
    `InterfaceError: the server expects 0 arguments for this query, 1 was passed`
    · และถ้าฝืนเติม placeholder ปลอมลง `count_sql` เพื่อให้จำนวนตรงกัน วันหน้าที่WHERE
    ของ count เพี้ยน จะไม่มีใครรู้ว่าที่เติมไปนั้นไม่มีความหมาย
    """
    total = await conn.fetchval(count_sql, *count_params)
    rows = await conn.fetch(rows_sql, *rows_params, limit, offset)
    page_size = max(1, limit)
    return {
        "items": rows,
        "total": total or 0,
        "page": offset // page_size + 1,
        "page_size": page_size,
        "pages": max(1, math.ceil((total or 0) / page_size)),
    }


# ============================================================
# 📖 อ่าน — ฝั่งจัดการ (ต้องมีสิทธิ์)
# ============================================================

async def list_events(
    pool: asyncpg.Pool,
    user_id: int,
    *,
    status: str = "live",
    category: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """รายการกิจกรรมสำหรับหน้าจัดการ (เห็นร่าง/ยกเลิก/ถูกลบ ได้ตาม `status`)

    `category` (D4) = กรองหมวด · `None` = **ทุกหมวด** (ไม่ใช่ "หมวด other")
    """
    if status not in _STATUS_CONDITIONS:
        raise ValidationError("สถานะที่กรองไม่ถูกต้อง")
    if category is not None and category not in EVENT_CATEGORIES:
        raise ValidationError("หมวดกิจกรรมไม่ถูกต้อง")

    where_sql = _STATUS_CONDITIONS[status]
    # ⚠️ ที่นี่ count กับ rows ใช้ **เลข placeholder ชุดเดียวกัน** ได้ เพราะ `_STATUS_CONDITIONS`
    #    เป็น literal ล้วน (ไม่มี param) และฝั่งจัดการไม่มี `_MY_REG_JOIN` มาจอง `$1`
    #    ⇒ ต่างจาก `list_public_events` ที่ต้องแยกสองชุด (ดู `_envelope`)
    params: list = []
    if category is not None:
        params.append(category)
        where_sql += f" AND e.category = ${len(params)}"

    async with pool.acquire() as conn:
        await require_permission_anywhere(conn, user_id, "MANAGE_EVENTS")
        result = await _envelope(
            conn,
            count_sql=f"SELECT COUNT(*) FROM events e WHERE {where_sql}",
            rows_sql=f"""
                SELECT {_MANAGE_COLUMNS}
                FROM events e
                {_JOINS}
                {_STATS_JOIN}
                WHERE {where_sql}
                {_ORDER_BY_MANAGE}
                LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}
            """,
            count_params=params,
            rows_params=params,
            limit=limit,
            offset=offset,
        )
    result["items"] = [dict(r) for r in result["items"]]
    return result


async def get_event(pool: asyncpg.Pool, user_id: int, event_id: int) -> dict:
    """กิจกรรมหนึ่งใบในมุมมองฝั่งจัดการ — **เห็นฉบับร่างด้วย** (ต่างจาก `get_public_event`)

    ⭐ ทำไมต้องมีทั้งที่ `list_events` มีอยู่แล้ว — หน้าแก้ไข/หน้ารายชื่อผู้สมัครเป็น **หน้าเต็มหน้า**
       ที่เปิดตรงได้และ refresh ได้ ⇒ ต้องมี endpoint ที่หยิบใบเดียวด้วย id
       (`list_events` ไม่มีตัวกรอง id เลย และ `get_public_event` กรอง `status='published'`
       ⇒ กิจกรรมที่เป็น**ฉบับร่างจะ 404** ซึ่งเป็นเคสที่สภาต้องแก้บ่อยที่สุด)

    ⚠️ **คืนแถวที่ถูกลบ (soft delete) ตามจริง ไม่กรอง `deleted_at IS NULL`** — ต่างจาก
       `list_registrations` ที่ต้อง 404 เพราะที่นั่นถามถึง *รายชื่อผู้สมัคร* ของกิจกรรม
       ที่ไม่มีอยู่จริง · ที่นี่ถามถึง *ตัวกิจกรรม* ซึ่งยังมีอยู่ (แค่ถูกลบ) ⇒ ต้องตอบตามจริง
       ไม่งั้นหน้าแก้ไขจะบอกว่า "ไม่พบกิจกรรม" ทั้งที่ผู้ใช้เพิ่งเห็นมันในลิสต์ status=deleted
       **และต้องไม่ 404** เพราะ frontend ต้องเอา `deleted_at` ไปแสดงการ์ด "ถูกลบแล้ว —
       กู้คืนก่อนจึงจะแก้ได้" (PATCH มี `deleted_at IS NULL` ⇒ ถ้าเปิดให้แก้จะได้ 404 ตอนบันทึก
       = "แก้แล้วไม่บันทึก" ซึ่งเป็นอาการที่หาสาเหตุยากที่สุด)
    """
    async with pool.acquire() as conn:
        await require_permission_anywhere(conn, user_id, "MANAGE_EVENTS")
        row = await _fetch_one(conn, event_id)

    if not row:
        raise NotFoundError("ไม่พบกิจกรรมนี้")
    return row


async def list_registrations(
    pool: asyncpg.Pool,
    user_id: int,
    event_id: int,
    *,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """รายชื่อผู้สมัครของกิจกรรมหนึ่ง — สภาต้องเห็น waitlist ถึงจะจัดการคิวได้จริง

    เรียง "ได้ที่นั่งก่อน แล้วต่อด้วยคิวสำรอง" ⇒ สภาอ่านจากบนลงล่าง = ลำดับที่คนจะได้เข้า

    ⚠️ JOIN แค่ `users` **ไม่ JOIN `students`** — user หนึ่งคนมีได้หลายแถว (หลายห้อง)
       ⇒ JOIN students จะทำให้รายชื่อบานออกเป็นซ้ำ (บทเรียนเดียวกับ `_JOINS`)
    """
    async with pool.acquire() as conn:
        await require_permission_anywhere(conn, user_id, "MANAGE_EVENTS")

        # ต้องแยกการมีอยู่ของกิจกรรมจากรายชื่อ — กิจกรรมที่ไม่มี/ถูกลบต้องได้ 404
        # ไม่ใช่ได้ลิสต์ว่าง (สองอย่างนี้ผู้ใช้ตีความต่างกันมาก)
        exists = await conn.fetchval(
            "SELECT 1 FROM events WHERE id = $1 AND deleted_at IS NULL", event_id
        )
        if not exists:
            raise NotFoundError("ไม่พบกิจกรรมนี้")

        where = ["r.event_id = $1"]
        params: list = [event_id]
        if status:
            params.append(status)
            where.append(f"r.status = ${len(params)}")
        where_sql = " AND ".join(where)

        order_sql = """
            ORDER BY
                (CASE r.status WHEN 'registered' THEN 0 WHEN 'waitlisted' THEN 1 ELSE 2 END),
                r.registered_at ASC,
                r.id ASC
        """

        result = await _envelope(
            conn,
            count_sql=f"SELECT COUNT(*) FROM event_registrations r WHERE {where_sql}",
            rows_sql=f"""
                SELECT r.id, r.event_id, r.user_id, r.status,
                       r.registered_at, r.cancelled_at, r.checked_in_at,
                       u.full_name AS user_name
                FROM event_registrations r
                LEFT JOIN users u ON u.id = r.user_id
                WHERE {where_sql}
                {order_sql}
                LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}
            """,
            # ★ ที่นี่ `where_sql` มี placeholder จริง ⇒ count กินชุดเดียวกับ rows
            count_params=params,
            rows_params=params,
            limit=limit,
            offset=offset,
        )
    result["items"] = [dict(r) for r in result["items"]]
    return result


# ============================================================
# 📖 อ่าน — ฝั่งนักเรียน (ต้องล็อกอิน แต่ไม่ต้องมีสิทธิ์จัดการ)
# ============================================================

async def list_public_events(
    pool: asyncpg.Pool,
    user_id: int,
    *,
    scope: str = "upcoming",
    category: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """กิจกรรมที่เผยแพร่แล้ว + ยังไม่ถูกลบ — พร้อมสถานะการสมัครของ *ฉัน* ในแต่ละแถว

    ⚠️ **ไม่กรองด้วยสิทธิ์** — นักเรียนทุกคนเห็นกิจกรรมเหมือนกันหมด (นั่นคือความหมายของ
    "ประกาศให้ทั้งโรงเรียน") · ที่ต้องมีคือ `user_id` เพื่อรู้ว่า *ฉัน* สมัครหรือยัง

    `category` (D4) = กรองหมวด · `None` = **ทุกหมวด**
    """
    if scope not in _PUBLIC_SCOPES:
        raise ValidationError("ขอบเขตที่กรองไม่ถูกต้อง")
    if category is not None and category not in EVENT_CATEGORIES:
        raise ValidationError("หมวดกิจกรรมไม่ถูกต้อง")

    where_sql = (
        "e.deleted_at IS NULL AND e.status = 'published' "
        f"AND ({_PUBLIC_SCOPES[scope]})"
    )

    # ⚠️ **ต้องสร้างเงื่อนไขหมวดสองสำเนา** เพราะเลข placeholder ของ count กับ rows
    #    ไม่เท่ากัน — rows จอง `$1` ให้ `_MY_REG_JOIN` (user_id) แต่ count ไม่มี JOIN
    #    นั้น ⇒ ถ้าใช้สตริงเดียวกันทั้งคู่ ฝั่งใดฝั่งหนึ่งจะอ้าง `$2` ที่ไม่มีในคำขอ
    #    (asyncpg โยน `the server expects N arguments`) — ดู docstring ของ `_envelope`
    count_params: list = []
    rows_params: list = [user_id]
    count_extra = ""
    rows_extra = ""
    if category is not None:
        count_params.append(category)
        count_extra = f" AND e.category = ${len(count_params)}"
        rows_params.append(category)
        rows_extra = f" AND e.category = ${len(rows_params)}"

    async with pool.acquire() as conn:
        result = await _envelope(
            conn,
            count_sql=f"SELECT COUNT(*) FROM events e WHERE {where_sql}{count_extra}",
            rows_sql=f"""
                SELECT {_PUBLIC_COLUMNS},
                       mr.id AS my_registration_id,
                       mr.status AS my_registration_status
                FROM events e
                {_STATS_JOIN}
                {_MY_REG_JOIN}
                WHERE {where_sql}{rows_extra}
                {_ORDER_BY_PUBLIC}
                LIMIT ${len(rows_params) + 1} OFFSET ${len(rows_params) + 2}
            """,
            # ⚠️ `_PUBLIC_SCOPES` เทียบ `NOW()` ล้วน ⇒ count_sql มี placeholder
            #    **เฉพาะตอนกรองหมวด** (ไม่ใช่ `$1` ของ user_id)
            count_params=count_params,
            rows_params=rows_params,
            limit=limit,
            offset=offset,
        )
    result["items"] = [_public_row(r) for r in result["items"]]
    return result


async def list_closing_soon_events(
    pool: asyncpg.Pool,
    user_id: int,
    *,
    days: int = CLOSING_SOON_DAYS,
    limit: int = 5,
) -> dict:
    """กิจกรรมที่ **ยังเปิดรับสมัครอยู่** และจะปิดภายใน `days` วัน — บล็อกในหน้าแรก (4.5)

    คืน `{"items": [...], "total": n}` · `total` = จำนวนที่เข้าเงื่อนไขทั้งหมด (อาจมากกว่า
    `items`) ⇒ ฝั่งจอเขียน "ดูทั้งหมด N" ได้โดยไม่ต้องยิงคำขอที่สอง

    ⭐ **"ปิดรับ" ไม่ได้แปลว่า `registration_deadline` เสมอ** — กิจกรรมที่ไม่ได้ตั้งกำหนด
       ปิดรับจะปิดที่ *วันจัด* ซึ่งเป็นกลุ่มที่นักเรียนพลาดมากที่สุด (ไม่มีอะไรเตือนเลย
       เพราะไม่มี deadline ให้เห็น) ⇒ เงื่อนไขใช้ `_CLOSES_AT_SQL` ไม่ใช่คอลัมน์ดิบ

    ⭐ **ไม่กรองด้วยสถานะการสมัครของตัวเอง** — ทั้งที่ดูเหมือนควรกรอง ("สมัครแล้วก็ไม่ต้อง
       เตือน") เพราะ
         1. บล็อกที่ว่างเกือบตลอดเวลา จะถูกอ่านข้ามไปทั้งบล็อก — รวมวันที่มันมีของจริง
         2. "สมัครแล้ว" ≠ "เรียบร้อย" — กิจกรรมที่ตัวเองสมัครไว้คือสิ่งที่ต้อง *อย่าลืมไป*
            มากที่สุด ⇒ แถวที่สมัครแล้วมีค่าเท่ากับแถวที่ยังไม่สมัคร
       ⇒ สิ่งที่ต้องต่างกันคือ *ปุ่ม* ไม่ใช่ *การมีอยู่ของแถว* — ฝั่งจออ่าน
       `my_registration_status` แล้วแสดงป้าย "สมัครแล้ว" แทนปุ่มสมัคร

    ⚠️ **ไม่มี pagination โดยเจตนา** — เป็นบล็อกสรุปในหน้าแรก ใช้ `limit` อย่างเดียว
       (ต่างจาก `list_public_events` ที่เป็นหน้ารายการเต็มที่มี envelope 5 ช่อง)
       ⇒ ห้ามเอา `_envelope` มาใช้ เพราะมันบังคับให้มี `page`/`pages` ซึ่งไม่มีความหมายที่นี่
    """
    if days < 1:
        raise ValidationError("จำนวนวันต้องมากกว่า 0")

    # ⚠️ **ต้องมีสองสำเนาของเงื่อนไขหน้าต่างเวลา** เพราะเลข placeholder ไม่เท่ากัน —
    #    `count_sql` ไม่มี `_MY_REG_JOIN` จึงไม่จอง `$1` ให้ user_id แต่ `rows_sql` จอง
    #    ⇒ ฝั่ง count เริ่มที่ $1 ฝั่ง rows เริ่มที่ $2 (บทเรียนเดียวกับ `list_public_events`)
    #
    # ⚠️ **`days` ต้องผูกเป็นพารามิเตอร์ ไม่ใช่ต่อสตริง `INTERVAL '{days} days'`** —
    #    ถึงตอนนี้ `days` จะเป็น int ที่เราคุมเองทั้งหมด แต่วันที่มีคนส่งค่าจาก config
    #    หรือจาก query param เข้ามา การต่อสตริงจะกลายเป็นช่องฉีด SQL ทันที
    #    โดยที่โค้ดหน้าตาแทบไม่เปลี่ยน ⇒ กันตั้งแต่วันนี้ราคาถูกกว่า
    count_window = "NOW() + make_interval(days => $1::int)"
    rows_window = "NOW() + make_interval(days => $2::int)"

    # 🚨 `_REGISTRATION_OPEN_SQL` จำเป็น **ไม่ใช่ซ้ำซ้อน** — ตัว `_CLOSES_AT_SQL <= now+N`
    #    เดี่ยว ๆ เป็นจริงกับกิจกรรมที่ **ปิดไปแล้ว** ด้วย (`closes_at` อดีตก็ <= อนาคต)
    #    ⇒ ถ้าตัดออก บล็อก "ใกล้ปิดรับ" จะเต็มไปด้วยกิจกรรมที่หมดเขตไปแล้ว
    #    (โชคดีที่ตัวนั้นพ่วงเงื่อนไข published/not-deleted มาให้ด้วย จึงไม่ต้องเขียนซ้ำ)
    where_count = f"""
        FROM events e
        WHERE {_REGISTRATION_OPEN_SQL}
          AND {_CLOSES_AT_SQL} <= {count_window}
    """
    where_rows = f"""
        FROM events e
        {_STATS_JOIN}
        {_MY_REG_JOIN}
        WHERE {_REGISTRATION_OPEN_SQL}
          AND {_CLOSES_AT_SQL} <= {rows_window}
    """

    async with pool.acquire() as conn:
        total = await conn.fetchval(f"SELECT COUNT(*) {where_count}", days)
        rows = await conn.fetch(
            f"""
            SELECT {_PUBLIC_COLUMNS},
                   mr.id AS my_registration_id,
                   mr.status AS my_registration_status
            {where_rows}
            ORDER BY closes_at ASC, e.id ASC
            LIMIT $3  -- $1 = user_id · $2 = days (อยู่นอกสตริง) ⇒ limit ต้องเป็น $3
            """,
            user_id, days, limit,
        )

    return {"items": [_public_row(r) for r in rows], "total": total or 0}


async def get_public_event(pool: asyncpg.Pool, user_id: int, event_id: int) -> dict:
    """รายละเอียดกิจกรรมหนึ่งใบ (ฝั่งนักเรียน) — เห็นได้เฉพาะที่เผยแพร่แล้ว"""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"""
            SELECT {_PUBLIC_COLUMNS},
                   mr.id AS my_registration_id,
                   mr.status AS my_registration_status
            FROM events e
            {_STATS_JOIN}
            {_MY_REG_JOIN}
            WHERE e.id = $2 AND e.deleted_at IS NULL AND e.status = 'published'
            """,
            user_id, event_id,
        )
    if not row:
        raise NotFoundError("ไม่พบกิจกรรมนี้")
    return _public_row(row)


async def get_my_registration(pool: asyncpg.Pool, user_id: int, event_id: int) -> dict:
    """สถานะการสมัครของฉัน + **ลำดับคิว** (เฉพาะคนที่รออยู่จริง)

    ⚠️ ลำดับคิวต้องเทียบแบบ **tuple** `(registered_at, id)` ไม่ใช่ `registered_at` เดี่ยว ๆ
       เพราะคิวที่เข้าพร้อมกันจะได้ `registered_at` เท่ากัน (NOW() คงที่ทั้ง transaction)
       ⇒ เทียบเดี่ยวจะนับข้ามคน ⇒ ลำดับที่โชว์ไม่ตรงกับลำดับที่ระบบจะเลื่อนจริง
       ซึ่งเป็นบั๊กที่ผู้ใช้เห็นชัด ("บอกว่าฉันเป็นคิวที่ 3 แต่พอคนหน้าเลื่อนกลับไม่ใช่ฉัน")
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, status, registered_at, checked_in_at
            FROM event_registrations
            WHERE event_id = $1 AND user_id = $2
            """,
            event_id, user_id,
        )
        if not row or row["status"] == "cancelled":
            return {"registered": False, "registration_id": None, "status": None,
                    "queue_position": None, "check_in_token": None,
                    "checked_in_at": None}

        queue_position = None
        if row["status"] == "waitlisted":
            queue_position = await conn.fetchval(
                """
                SELECT COUNT(*)::int FROM event_registrations
                WHERE event_id = $1 AND status = 'waitlisted'
                  AND (registered_at, id) <= ($2::timestamptz, $3::int)
                """,
                event_id, row["registered_at"], row["id"],
            )

    return {
        "registered": True,
        "registration_id": row["id"],
        "status": row["status"],
        "queue_position": queue_position,
        "check_in_token": _seat_token(event_id, row["id"], row["status"]),
        "checked_in_at": row["checked_in_at"],
    }


# ============================================================
# ✍️ เขียน — จัดการกิจกรรม (ต้องมีสิทธิ์ MANAGE_EVENTS)
# ============================================================

async def create_event(pool: asyncpg.Pool, user_id: int, data: dict) -> dict:
    """สร้างกิจกรรมใหม่เป็น **ฉบับร่าง** + audit

    ⚠️ **ไม่ยิงแจ้งเตือนที่นี่** (ผู้ใช้เลือก: "แจ้งเฉพาะตอนกดเผยแพร่ ไม่ใช่ตอนสร้าง")
       ⇒ กิจกรรมทุกใบเกิดเป็น `draft` และรอจนกว่าจะมีคนกดเผยแพร่ · `publish_event()`
       เป็นที่เดียวที่เรียก `notify_fanout` — **ห้ามย้ายมาไว้ที่นี่** ไม่งั้นร่างที่ยัง
       ตรวจไม่เสร็จจะ push ถึงทั้งโรงเรียนทันทีที่กดบันทึก
    """
    _assert_deadline_not_after_event(
        data["event_date"], data.get("registration_deadline")
    )

    async with pool.acquire() as conn:
        async with conn.transaction():
            await require_permission_anywhere(conn, user_id, "MANAGE_EVENTS")

            new_id = await conn.fetchval(
                """
                INSERT INTO events
                    (title, description, location, cover_image_url,
                     event_date, registration_deadline, capacity, category,
                     created_by, updated_by)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                RETURNING id
                """,
                data["title"], data.get("description"), data.get("location"),
                data.get("cover_image_url"), data["event_date"],
                data.get("registration_deadline"), data.get("capacity"),
                # ⚠️ `data.get("category") or "other"` **ไม่ใช่** `data.get("category")`
                #    เฉย ๆ — เผื่อผู้เรียกส่ง dict ที่ไม่มีคีย์นี้มา (เส้นทางที่ไม่ผ่าน
                #    Pydantic เช่น script/seed) คอลัมน์เป็น NOT NULL ⇒ ถ้าปล่อย None
                #    จะได้ NotNullViolationError เป็น 500 · ค่า default ของ schema
                #    ยังเป็น "other" อยู่ (สองชั้นนี้ครอบคนละเส้นทาง)
                data.get("category") or "other",
                user_id, user_id,
            )

            await AuditLogger("event_service").log(
                conn=conn,
                action="CREATE_EVENT",
                actor_identifier=str(user_id),
                client_source="web",
                user_id=user_id,
                entity_type="event",
                entity_id=new_id,
                new_values={
                    "title": data["title"],
                    "event_date": str(data["event_date"]),
                    "capacity": data.get("capacity"),
                    "category": data.get("category") or "other",
                    "status": "draft",
                },
            )

        return await _fetch_one(conn, new_id)


async def update_event(
    pool: asyncpg.Pool, user_id: int, event_id: int, changes: dict
) -> dict:
    """แก้กิจกรรม (PATCH — เฉพาะฟิลด์ที่ส่งมา) + audit old/new values

    ⚠️ อ่านแถวเดิมก่อน **แล้ว merge กับค่าที่ส่งมา** เพื่อตรวจ `registration_deadline`
       กับ `event_date` บน **ค่าที่จะเขียนจริง** — ถ้าตรวจแค่ค่าที่ส่งมาจะพลาดเคส
       "แก้วันจัดให้เร็วขึ้นจนเลยกำหนดปิดรับสมัครที่ตั้งไว้แล้ว"

    ⚠️ **ยังไม่แจ้งเตือนเมื่อเลื่อนวันจัด** — คนที่ลงทะเบียนไปแล้วจะไม่รู้ว่าวันเปลี่ยน
       เป็นข้อจำกัดที่รู้ตัวของ D1 (การยิง fanout ซ้ำทุกครั้งที่แก้เป็นพฤติกรรมที่ต้อง
       ให้ผู้ใช้ตัดสินก่อน ไม่ควรเดา) — บันทึกไว้ใน `docs/skills.md` ตอนปิดรอบ
    """
    safe = {k: v for k, v in changes.items() if k in _EDITABLE_COLUMNS}
    if not safe:
        raise ValidationError("ไม่มีข้อมูลที่จะแก้ไข")

    async with pool.acquire() as conn:
        async with conn.transaction():
            await require_permission_anywhere(conn, user_id, "MANAGE_EVENTS")

            # FOR UPDATE — ล็อกแถวกัน TOCTOU กับการเผยแพร่/ยกเลิกที่วิ่งมาพร้อมกัน
            before = await conn.fetchrow(
                """
                SELECT title, description, location, cover_image_url,
                       event_date, registration_deadline, capacity, category
                FROM events
                WHERE id = $1 AND deleted_at IS NULL
                FOR UPDATE
                """,
                event_id,
            )
            if not before:
                raise NotFoundError("ไม่พบกิจกรรมนี้ (อาจถูกลบไปแล้ว)")

            merged = {**dict(before), **safe}
            _assert_deadline_not_after_event(
                merged["event_date"], merged["registration_deadline"]
            )

            # dynamic SET: จอง $1 ไว้ให้ WHERE เสมอ แล้วฟิลด์เริ่มที่ len(params)+1
            # (บทเรียน: asyncpg AmbiguousParameterError/IndeterminateDatatypeError)
            params: list = [event_id]
            sets: list = []
            for column, value in safe.items():
                params.append(value)
                sets.append(f"{column} = ${len(params)}")

            params.append(user_id)
            sets.append(f"updated_by = ${len(params)}")

            # `updated_at = NOW()` ไม่มี param จึงไม่กระทบเลข placeholder
            sql = f"UPDATE events SET {', '.join(sets)}, updated_at = NOW() WHERE id = $1"
            assert sql.count("$") == len(params), "placeholder ไม่ตรงกับจำนวน param"

            await conn.execute(sql, *params)

            await AuditLogger("event_service").log(
                conn=conn,
                action="UPDATE_EVENT",
                actor_identifier=str(user_id),
                client_source="web",
                user_id=user_id,
                entity_type="event",
                entity_id=event_id,
                # เก็บเฉพาะฟิลด์ที่สั่งแก้จริง — audit ที่เก็บทั้งแถวจะอ่านไม่ออกว่าอะไรเปลี่ยน
                old_values={k: str(before[k]) for k in safe},
                new_values={k: str(v) for k, v in safe.items()},
            )

        return await _fetch_one(conn, event_id)


async def publish_event(pool: asyncpg.Pool, user_id: int, event_id: int) -> dict:
    """
    เผยแพร่กิจกรรม (draft → published) + **ยิงแจ้งเตือนทุก active student**

    ⭐ นี่คือ **ที่เดียว** ในระบบที่แจ้งข่าวกิจกรรม — ตรงตามที่ผู้ใช้เลือก
       ("แจ้งเฉพาะตอนกดเผยแพร่ ไม่ใช่ตอนสร้าง") ⇒ กิจกรรมที่ยังเป็นร่างเงียบสนิท

    ⚠️ **`bypass_quiet_hours=False` โดยเจตนา** — กิจกรรมไม่ใช่เรื่องฉุกเฉิน
       (ต่างจาก E2 ประกาศฉุกเฉินที่ทะลุ A8) ⇒ โรงเรียนที่ตั้ง "ช่วงเวลาไม่ส่งแจ้งเตือน"
       ต้องได้รับการเคารพ · และ `group_type="event"` อยู่ใน `PREFERENCE_GROUPS`
       ⇒ ผู้ใช้ที่ไม่อยากได้ข่าวกิจกรรมปิดได้ (ไม่งั้นสภาที่จัดกิจกรรมทุกสัปดาห์
       จะกลายเป็นสแปมที่ปิดไม่ได้)

    🚫 **ห้ามเผยแพร่กิจกรรมที่วันจัดผ่านไปแล้ว** — การ push ถึงทั้งโรงเรียนเพื่อกิจกรรม
       ที่จบไปแล้วคือความผิดพลาดที่เรียกคืนไม่ได้ · ตรวจก่อนแตะ DB ⇒ ถ้าตั้งวันที่ผิด
       ให้แก้ไขวันที่ก่อนแล้วค่อยเผยแพร่ (ข้อความบอกทางออกไว้แล้ว)
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            await require_permission_anywhere(conn, user_id, "MANAGE_EVENTS")

            # อ่านก่อนเพื่อ (ก) เช็ควันที่ผ่านไปแล้ว (ข) ได้ชื่อมาใส่ข้อความแจ้งเตือน
            #    — `RETURNING` ของ UPDATE ให้ค่า *หลัง* แก้ ซึ่งไม่มี `event_date` ติดมา
            before = await conn.fetchrow(
                """
                SELECT title, location, event_date
                FROM events
                WHERE id = $1 AND status = 'draft' AND deleted_at IS NULL
                FOR UPDATE
                """,
                event_id,
            )
            if not before:
                raise NotFoundError("ไม่พบกิจกรรมฉบับร่างนี้ (อาจถูกเผยแพร่หรือลบไปแล้ว)")

            is_past = await conn.fetchval(
                "SELECT $1::timestamptz <= NOW()", before["event_date"]
            )
            if is_past:
                raise ValidationError(
                    "วันจัดกิจกรรมผ่านไปแล้ว — แก้ไขวันจัดให้เป็นวันในอนาคตก่อนเผยแพร่"
                )

            await conn.execute(
                """
                UPDATE events
                SET status = 'published', published_at = NOW(),
                    updated_at = NOW(), updated_by = $2
                WHERE id = $1
                """,
                event_id, user_id,
            )

            await AuditLogger("event_service").log(
                conn=conn,
                action="PUBLISH_EVENT",
                actor_identifier=str(user_id),
                client_source="web",
                user_id=user_id,
                entity_type="event",
                entity_id=event_id,
                old_values={"status": "draft", "published_at": None},
                new_values={"status": "published", "published_at": "NOW()"},
            )

            # ⚠️ `actor_id=user_id` ⇒ ผู้เผยแพร่ไม่ได้รับ push ของตัวเอง (fanout กรองให้)
            #    และ **แถว in-app ของตัวเองก็ไม่เกิดด้วย** — ยอมรับได้ เขารู้อยู่แล้ว
            #    ว่าเพิ่งเผยแพร่อะไร (แบบเดียวกับ `_fanout_if_urgent` ของประกาศ)
            location = before["location"]
            await notification_service.notify_fanout(
                conn,
                group_type="event",
                type="event_published",
                title="📣 เปิดรับสมัครกิจกรรมใหม่",
                body=f"{before['title']} — {location}" if location else before["title"],
                entity_type="event",
                entity_id=event_id,
                actor_id=user_id,
            )

        return await _fetch_one(conn, event_id)


async def cancel_event(pool: asyncpg.Pool, user_id: int, event_id: int) -> dict:
    """
    ยกเลิกกิจกรรม (published → cancelled) + แจ้งคนที่ลงทะเบียน/รอคิวไว้

    ⚠️ **ไม่ลบแถวการสมัคร** — ประวัติต้องอยู่ (ใครสมัครไว้บ้าง) · แถวที่ยัง `status='registered'`
       จะค้างอยู่ แต่ `events.status='cancelled'` เป็นตัวบอกความจริง · และ **ไม่เลื่อนคิว**
       (การเลื่อนคิวตอนยกเลิก = เลื่อนให้คนที่ไม่มีกิจกรรมให้เข้าแล้ว)
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            await require_permission_anywhere(conn, user_id, "MANAGE_EVENTS")

            row = await conn.fetchrow(
                """
                UPDATE events
                SET status = 'cancelled', cancelled_at = NOW(),
                    updated_at = NOW(), updated_by = $2
                WHERE id = $1 AND status = 'published' AND deleted_at IS NULL
                RETURNING id, title
                """,
                event_id, user_id,
            )
            if not row:
                # ไม่พบ / ยังเป็นร่าง / ยกเลิกไปแล้ว — ทั้งสามกรณีไม่ควรทับ cancelled_at เดิม
                raise NotFoundError(
                    "ไม่พบกิจกรรมที่เผยแพร่แล้วนี้ (อาจยังเป็นฉบับร่างหรือถูกยกเลิกไปแล้ว)"
                )

            await AuditLogger("event_service").log(
                conn=conn,
                action="CANCEL_EVENT",
                actor_identifier=str(user_id),
                client_source="web",
                user_id=user_id,
                entity_type="event",
                entity_id=event_id,
                old_values={"status": "published", "cancelled_at": None},
                new_values={"status": "cancelled", "cancelled_at": "NOW()"},
            )

            rows = await conn.fetch(
                """
                SELECT user_id FROM event_registrations
                WHERE event_id = $1
                  AND status IN ('registered', 'checked_in', 'waitlisted')
                """,
                event_id,
            )
            await notification_service.notify_bulk(
                conn,
                [r["user_id"] for r in rows],
                group_type="event",
                type="event_cancelled",
                title="❌ กิจกรรมถูกยกเลิก",
                body=f"{row['title']} ถูกยกเลิก",
                entity_type="event",
                entity_id=event_id,
                actor_id=user_id,
            )

        return await _fetch_one(conn, event_id)


async def delete_event(pool: asyncpg.Pool, user_id: int, event_id: int) -> dict:
    """ลบกิจกรรม (soft delete) + audit — คืนแถวที่อัปเดตแล้ว (มี deleted_at ติดมาด้วย)"""
    async with pool.acquire() as conn:
        async with conn.transaction():
            await require_permission_anywhere(conn, user_id, "MANAGE_EVENTS")

            row = await conn.fetchrow(
                """
                UPDATE events
                SET deleted_at = NOW(), updated_at = NOW(), updated_by = $2
                WHERE id = $1 AND deleted_at IS NULL
                RETURNING id
                """,
                event_id, user_id,
            )
            if not row:
                # ไม่พบ หรือ ถูกลบไปแล้ว (กันกดซ้ำ — ไม่ทับ deleted_at เดิมด้วย NOW() ใหม่)
                raise NotFoundError("ไม่พบกิจกรรมนี้ (อาจถูกลบไปแล้ว)")

            await AuditLogger("event_service").log(
                conn=conn,
                action="DELETE_EVENT",
                actor_identifier=str(user_id),
                client_source="web",
                user_id=user_id,
                entity_type="event",
                entity_id=event_id,
                old_values={"deleted_at": None},
                new_values={"deleted_at": "NOW()"},
            )

        return await _fetch_one(conn, event_id)


async def restore_event(pool: asyncpg.Pool, user_id: int, event_id: int) -> dict:
    """กู้คืนกิจกรรมที่ถูกลบ + audit

    ⚠️ กู้คืนแล้วได้ **สถานะเดิมกลับมา** (draft/published/cancelled) — `deleted_at` กับ
       `status` เป็นคนละแกน ⇒ กิจกรรมที่ "เผยแพร่แล้วถูกลบ" กลับมาเป็นเผยแพร่อีกครั้ง
       ⇒ **ไม่ต้องยิงแจ้งเตือนซ้ำ** (คนที่เคยได้ push ไปแล้วไม่ควรได้อีก)
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            await require_permission_anywhere(conn, user_id, "MANAGE_EVENTS")

            row = await conn.fetchrow(
                """
                UPDATE events
                SET deleted_at = NULL, updated_at = NOW(), updated_by = $2
                WHERE id = $1 AND deleted_at IS NOT NULL
                RETURNING id
                """,
                event_id, user_id,
            )
            if not row:
                raise NotFoundError("ไม่พบกิจกรรมที่ถูกลบนี้")

            await AuditLogger("event_service").log(
                conn=conn,
                action="RESTORE_EVENT",
                actor_identifier=str(user_id),
                client_source="web",
                user_id=user_id,
                entity_type="event",
                entity_id=event_id,
                old_values={"deleted_at": "NOT NULL"},
                new_values={"deleted_at": None},
            )

        return await _fetch_one(conn, event_id)


# ============================================================
# 🎟️ ลงทะเบียน — ฝั่งนักเรียน
# ============================================================

async def register_event(pool: asyncpg.Pool, user_id: int, event_id: int) -> tuple:
    """
    ลงทะเบียนกิจกรรม — ได้ที่นั่งถ้ายังว่าง ไม่ว่างก็เข้าคิวสำรอง **โดยอัตโนมัติ**

    คืน `(created, payload)` ⇒ router แปลงเป็น 201 / 200
    ⚠️ `created = True` **เฉพาะเมื่อ INSERT แถวใหม่** — สมัครซ้ำ, สมัครใหม่หลังถอน, และ
       คนที่เป็นคิวสำรองอยู่แล้ว กดซ้ำ ⇒ `False` (200) ทั้งหมด เพราะแถวเดิมถูกใช้ต่อ

    ⭐ **ลำดับของ 3 ขั้นนี้คือหัวใจ ห้ามสลับ:**

      1. `SELECT … FOR UPDATE` บนแถว **กิจกรรม** = mutex ⇒ ที่นั่งสุดท้ายถูกขายซ้ำไม่ได้
         (สองคำขอที่วิ่งพร้อมกันจะถูกจัดคิวที่ล็อกนี้ ไม่ใช่ต่างคนต่างนับแล้ว insert ทั้งคู่)

      2. **อ่านแถวเดิมของ *ฉัน* ก่อนนับที่นั่ง** ← จุดที่พังเงียบที่สุดถ้าสลับ
         ถ้านับก่อน: คนที่ **สมัครอยู่แล้ว** กลับมากดซ้ำตอนกิจกรรมเต็ม ⇒ การนับรวมตัวเขาเอง
         ⇒ `taken >= capacity` เป็นจริง ⇒ **ถูกลดสถานะจาก `registered` เป็น `waitlisted`**
         ทั้งที่ไม่ได้ทำอะไรผิด — เป็นบั๊กที่ผู้ใช้เห็น ("กดดูอีกทีกลายเป็นคิวสำรอง")
         และเกิดเฉพาะตอนกิจกรรมเต็ม ซึ่งเป็นตอนที่คนกดดูบ่อยที่สุด

      3. คนที่มีสถานะอยู่แล้ว (`registered`/`checked_in`/`waitlisted`) → **คืนค่าเดิมทันที**
         ⚠️ คนที่ `waitlisted` **ห้ามถูกเลื่อนขึ้น** ด้วยการกดซ้ำ — การเลื่อนต้องมาจาก
            "มีคนข้างหน้าถอน" เท่านั้น ไม่งั้นการกดรัว ๆ = แซงคิว
         ⇒ มีแต่แถว `cancelled` (หรือไม่มีแถวเลย) ที่ถูกประเมินที่นั่งใหม่

    ⚠️ **สมัครใหม่/สมัครซ้ำหลังถอน = เขียน `registered_at = NOW()` ใหม่ ⇒ ต่อท้ายคิว**
       (ตั้งใจ: การถอนแล้วกลับเข้ามาใหม่คือการต่อคิวใหม่ ไม่ใช่การรักษาที่เดิม)
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            # ── ขั้น 1: ล็อกแถวกิจกรรม ────────────────────────────────────────────
            event = await conn.fetchrow(
                """
                SELECT id, title, capacity, status, event_date, registration_deadline,
                       deleted_at
                FROM events
                WHERE id = $1
                FOR UPDATE
                """,
                event_id,
            )
            if not event or event["deleted_at"] is not None:
                raise NotFoundError("ไม่พบกิจกรรมนี้")
            if event["status"] == "draft":
                raise ValidationError("กิจกรรมนี้ยังไม่เปิดให้ลงทะเบียน")
            if event["status"] == "cancelled":
                raise ValidationError("กิจกรรมนี้ถูกยกเลิกแล้ว")

            # เวลาอ่านจาก DB เสมอ — นาฬิกาของโปรเซสกับของ DB ไม่รับประกันว่าตรงกัน
            # และกติกานี้เป็นกติกาของระบบ ไม่ใช่การแสดงผล
            closed_reason = await conn.fetchval(
                """
                SELECT CASE
                    WHEN $1::timestamptz <= NOW() THEN 'passed'
                    WHEN $2::timestamptz IS NOT NULL AND $2::timestamptz < NOW() THEN 'deadline'
                    ELSE NULL
                END
                """,
                event["event_date"], event["registration_deadline"],
            )
            if closed_reason == "passed":
                raise ValidationError("กิจกรรมนี้ผ่านไปแล้ว")
            if closed_reason == "deadline":
                raise ValidationError("เลยกำหนดลงทะเบียนแล้ว")

            # ── ขั้น 2: อ่านแถวเดิมของฉัน "ก่อน" นับที่นั่ง ─────────────────────────
            mine = await conn.fetchrow(
                """
                SELECT id, status FROM event_registrations
                WHERE event_id = $1 AND user_id = $2
                FOR UPDATE
                """,
                event_id, user_id,
            )

            # ── ขั้น 3: มีสถานะอยู่แล้ว → คืนค่าเดิม (ไม่นับใหม่ ไม่เลื่อนคิว) ───────
            if mine and mine["status"] in ("registered", "checked_in", "waitlisted"):
                payload = await _my_registration_conn(conn, event_id, user_id)
                return False, payload

            taken = await conn.fetchval(
                """
                SELECT COUNT(*) FROM event_registrations
                WHERE event_id = $1 AND status IN ('registered', 'checked_in')
                """,
                event_id,
            )
            capacity = event["capacity"]
            # `capacity is None` = ไม่จำกัด ⇒ ต้องเช็คก่อนเทียบตัวเลขเสมอ (ดู docstring หัวไฟล์)
            new_status = (
                "registered"
                if capacity is None or taken < capacity
                else "waitlisted"
            )

            # ⚠️ `created` = "**แถวใหม่**ถูกสร้าง" ไม่ใช่ "การลงทะเบียนเกิดขึ้น"
            #    มาถึงตรงนี้ได้ มีแค่ 2 กรณี: ไม่มีแถวเลย (INSERT) หรือมีแถว `cancelled` ค้างอยู่
            #    (UPDATE — unique index ไม่ใช่ partial ⇒ สมัครใหม่หลังถอนต้องใช้แถวเดิม)
            #    ⇒ สมัครใหม่หลังถอนต้องได้ **200** ให้ตรงกับสัญญาที่ router เขียนไว้
            #    ("201 เมื่อสร้างแถวใหม่ · 200 เมื่อมีแถวอยู่แล้ว") — การคืน 201 ตรงนี้สื่อว่า
            #    "สร้างแถวใหม่" ทั้งที่ฐานข้อมูลเพิ่ง UPDATE แถวเดิม (registration_id คงเดิม)
            if mine:
                created = False
                rows = await conn.fetchrow(
                    """
                    UPDATE event_registrations
                    SET status = $3, registered_at = NOW(), cancelled_at = NULL,
                        checked_in_at = NULL, updated_at = NOW()
                    WHERE id = $1 AND user_id = $2
                    RETURNING id
                    """,
                    mine["id"], user_id, new_status,
                )
            else:
                created = True
                rows = await conn.fetchrow(
                    """
                    INSERT INTO event_registrations (event_id, user_id, status)
                    VALUES ($1, $2, $3)
                    RETURNING id
                    """,
                    event_id, user_id, new_status,
                )

            await AuditLogger("event_service").log(
                conn=conn,
                action="REGISTER_EVENT",
                actor_identifier=str(user_id),
                client_source="web",
                user_id=user_id,
                entity_type="event",
                entity_id=event_id,
                old_values={"status": mine["status"] if mine else None},
                new_values={"status": new_status, "registration_id": rows["id"]},
            )

            if new_status == "waitlisted":
                queue_position = await conn.fetchval(
                    """
                    SELECT COUNT(*)::int FROM event_registrations
                    WHERE event_id = $1 AND status = 'waitlisted'
                    """,
                    event_id,
                )
                # ⭐ **แจ้งเตือนตอน "เข้าคิว"** — ไม่ใช่ของแถม แต่เป็นการชดเชยสิ่งที่ระบบทำเงียบ ๆ
                #
                # คนที่กด "ลงทะเบียน" แล้วกิจกรรมเต็ม **ไม่ได้การ์ดที่ขอ** แต่ก็ **ไม่เห็น error**
                # (นโยบาย auto-waitlist: ไม่ปฏิเสธคำขอ) ⇒ ถ้าไม่มีข้อความนี้ คนคนนั้นจะเข้าใจว่า
                # "สมัครติดแล้ว" จนกระทั่งถึงวันงาน — ซึ่งเป็นวันที่สายเกินจะแก้
                # ⇒ ข้อความนี้คือ **หลักฐานถาวรในรายการแจ้งเตือน** ที่เขากลับมาดูได้ (ต่างจากป้ายบนจอ
                # ที่หายไปเมื่อปิดหน้า) · และเป็นเหตุผลว่า **ทำไมไม่แจ้งตอนสมัครติดปกติ** — ที่นั่น
                # ผู้ใช้ได้สิ่งที่ขอ จึงไม่ต้องมีข้อความยืนยันการกระทำของตัวเอง
                #
                # ⚠️ `actor_id=None` — ระบบเป็นคนพูด ไม่ใช่ตัวเขา (ไม่งั้นจะถูก `notify()` กรองทิ้ง
                #    ด้วยกฎ "ไม่สแปมตัวเอง" เพราะ `actor_id == user_id`)
                # ⚠️ มาถึงตรงนี้ได้เฉพาะ **เพิ่งเข้าคิว** — คนที่เป็นคิวอยู่แล้วถูกคืนค่าเดิมที่ขั้น 3
                #    ⇒ กดซ้ำไม่สร้างข้อความซ้ำ (ดู docstring ขั้น 3)
                await notification_service.notify(
                    conn,
                    user_id=user_id,
                    group_type="event",
                    type="event_waitlist_joined",
                    title="⏳ กิจกรรมเต็ม — คุณได้คิวสำรอง",
                    body=f"{event['title']} — คุณอยู่คิวที่ {queue_position}",
                    entity_type="event",
                    entity_id=event_id,
                    actor_id=None,
                )
                payload = {
                    "registered": True,
                    "registration_id": rows["id"],
                    "status": new_status,
                    "queue_position": queue_position,
                    "check_in_token": _seat_token(event_id, rows["id"], new_status),
                    # สมัครใหม่ = ยังไม่เคยเช็คอินในรอบนี้ · UPDATE ข้างบนล้าง `checked_in_at`
                    # ของรอบก่อนทิ้งไปแล้ว ⇒ ค่าที่คืนตรงกับของจริงใน DB เสมอ
                    # (ไม่คืน `None` ลอย ๆ ขณะที่ DB ยังมีค่าเก่าค้าง — สองที่นั้นจะเถียงกัน)
                    "checked_in_at": None,
                }
            else:
                payload = {
                    "registered": True,
                    "registration_id": rows["id"],
                    "status": new_status,
                    "queue_position": None,
                    "check_in_token": _seat_token(event_id, rows["id"], new_status),
                    # สมัครใหม่ = ยังไม่เคยเช็คอินในรอบนี้ · UPDATE ข้างบนล้าง `checked_in_at`
                    # ของรอบก่อนทิ้งไปแล้ว ⇒ ค่าที่คืนตรงกับของจริงใน DB เสมอ
                    # (ไม่คืน `None` ลอย ๆ ขณะที่ DB ยังมีค่าเก่าค้าง — สองที่นั้นจะเถียงกัน)
                    "checked_in_at": None,
                }
            return created, payload


async def _my_registration_conn(conn, event_id: int, user_id: int) -> dict:
    """เวอร์ชันรับ `conn` ของ `get_my_registration` — ใช้ภายใน transaction ที่ล็อกอยู่แล้ว

    ⚠️ ต้องมีเพราะ `get_my_registration` รับ `pool` แล้ว `acquire()` เอง ⇒ เรียกซ้อน
       จากใน transaction ที่ถือ connection อยู่จะ **ขอ connection ที่สอง** ซึ่ง pool
       อาจไม่มีให้ (และถ้ามีก็เป็น snapshot คนละอันกับที่กำลังแก้)
    """
    # ⚠️ อ่าน `id` มาด้วยเพื่อออกบัตรเช็คอิน — บัตรผูกกับ *แถวการลงทะเบียน* ไม่ใช่ (กิจกรรม, คน)
    #    แต่ในทางปฏิบัติสองอย่างนี้เทียบเท่ากันเพราะ unique index `uq_event_registrations_event_user`
    #    ⇒ แถวเดิมถูกใช้ซ้ำเสมอเมื่อสมัครใหม่ (ไม่มีการออก id ใหม่ให้คนเดิม)
    row = await conn.fetchrow(
        """
        SELECT id, status, registered_at, checked_in_at FROM event_registrations
        WHERE event_id = $1 AND user_id = $2
        """,
        event_id, user_id,
    )
    if not row or row["status"] == "cancelled":
        return {"registered": False, "registration_id": None, "status": None,
                "queue_position": None, "check_in_token": None,
                "checked_in_at": None}

    queue_position = None
    if row["status"] == "waitlisted":
        queue_position = await conn.fetchval(
            """
            SELECT COUNT(*)::int FROM event_registrations
            WHERE event_id = $1 AND status = 'waitlisted'
              AND (registered_at, id) <= ($2::timestamptz, $3::int)
            """,
            event_id, row["registered_at"], row["id"],
        )
    return {
        "registered": True,
        "registration_id": row["id"],
        "status": row["status"],
        "queue_position": queue_position,
        "check_in_token": _seat_token(event_id, row["id"], row["status"]),
        "checked_in_at": row["checked_in_at"],
    }


async def cancel_registration(pool: asyncpg.Pool, user_id: int, event_id: int) -> tuple:
    """
    ถอนการลงทะเบียนของตัวเอง + **เลื่อนคิวถัดไปขึ้นมาแทนทันที** (transaction เดียวกัน)

    คืน `(promoted_user_id_or_None, payload)`

    ⭐ **ทำไมต้องเลื่อนใน transaction เดียวกัน:** ถ้าแยกเป็นสองรอบ มีช่วงเวลาที่ที่นั่งว่าง
       โดยยังไม่มีใครได้ ⇒ คำขอลงทะเบียนที่วิ่งเข้ามาพอดีจะ **แย่งที่นั่งนั้นไป** แล้วคิว
       ที่เหลือถูกเลื่อนตามทีหลัง = คนที่รอนานกว่าโดนแซง — ซึ่งเป็นสิ่งที่ระบบคิวมีไว้กัน
       (`FOR UPDATE` บนแถวกิจกรรมในตอนต้นทำหน้าที่เป็น mutex ร่วมกับ `register_event`)

    ⚠️ **เลื่อนเฉพาะเมื่อคนที่ถอน "ถือที่นั่งจริง"** — คนที่อยู่ในคิวสำรองถอนตัวเอง
       ไม่ได้ทำให้ที่นั่งว่าง ⇒ ต้องไม่เลื่อนใคร (ไม่งั้นคิวจะเดินหน้าเปล่า ๆ ทุกครั้ง
       ที่มีคนเบื่อแล้วออกจากคิว)
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            # ล็อกแถวกิจกรรมก่อน — mutex เดียวกับ `register_event` ⇒ การนับที่นั่งกับ
            # การเลื่อนคิวไม่สามารถสอดแทรกกันกลางทางได้
            event = await conn.fetchrow(
                "SELECT id, deleted_at FROM events WHERE id = $1 FOR UPDATE", event_id
            )
            if not event or event["deleted_at"] is not None:
                raise NotFoundError("ไม่พบกิจกรรมนี้")

            mine = await conn.fetchrow(
                """
                SELECT id, status, checked_in_at FROM event_registrations
                WHERE event_id = $1 AND user_id = $2
                FOR UPDATE
                """,
                event_id, user_id,
            )
            # ⚠️ "ยังไม่เคยสมัคร" กับ "ถอนไปแล้ว" ให้ผลเดียวกัน ⇒ 404 ทั้งคู่
            #    (แยกข้อความให้ต่างกันจะรั่วว่ามีแถวอยู่จริงหรือไม่ ซึ่งไม่จำเป็นต้องรู้)
            if not mine or mine["status"] == "cancelled":
                raise NotFoundError("คุณยังไม่ได้ลงทะเบียนกิจกรรมนี้")

            await conn.execute(
                """
                UPDATE event_registrations
                SET status = 'cancelled', cancelled_at = NOW(),
                    checked_in_at = NULL, updated_at = NOW()
                WHERE id = $1
                """,
                mine["id"],
            )

            await AuditLogger("event_service").log(
                conn=conn,
                action="UNREGISTER_EVENT",
                actor_identifier=str(user_id),
                client_source="web",
                user_id=user_id,
                entity_type="event",
                entity_id=event_id,
                # ⭐ เก็บ `checked_in_at` ลง old_values ด้วย — การถอน **ล้างเวลาที่เช็คอิน**
                #    (ดู invariant ที่ `check_in_registration`) ⇒ ถ้าไม่เก็บตรงนี้ หลักฐานว่า
                #    "คนนี้เคยมาถึงกี่โมง" จะหายไปจากทั้งตารางและ log
                old_values={"status": mine["status"], "checked_in_at": mine["checked_in_at"]},
                new_values={"status": "cancelled", "checked_in_at": None},
            )

            # ── เลื่อนคิว — เฉพาะเมื่อที่นั่งจริงว่างลง ──────────────────────────────
            promoted_user_id = None
            if mine["status"] in ("registered", "checked_in"):
                promoted = await conn.fetchrow(
                    """
                    UPDATE event_registrations
                    SET status = 'registered', updated_at = NOW()
                    WHERE id = (
                        SELECT id FROM event_registrations
                        WHERE event_id = $1 AND status = 'waitlisted'
                        ORDER BY registered_at ASC, id ASC
                        LIMIT 1
                    )
                    RETURNING id, user_id
                    """,
                    event_id,
                )
                if promoted:
                    promoted_user_id = promoted["user_id"]
                    event_title = await conn.fetchval(
                        "SELECT title FROM events WHERE id = $1", event_id
                    )
                    # ⚠️ `actor_id=None` — นี่เป็นข้อความจาก *ระบบ* ไม่ใช่จากการกระทำของ
                    #    คนที่ถอน (การใส่ชื่อเขาจะทำให้ดูเหมือนเขาทำอะไรให้ ซึ่งไม่จริง
                    #    และจะกลายเป็น "ผู้กระทำ" ที่ถูกกรองตัวเองออกผิดคนถ้าซ้ำกัน)
                    await notification_service.notify(
                        conn,
                        user_id=promoted_user_id,
                        group_type="event",
                        type="event_waitlist_promoted",
                        title="🎉 คุณได้ที่นั่งแล้ว",
                        body=f"{event_title} — ถึงคิวของคุณแล้ว",
                        entity_type="event",
                        entity_id=event_id,
                        actor_id=None,
                    )

            payload = {
                "registered": False,
                "registration_id": None,
                "status": None,
                "queue_position": None,
                "check_in_token": None,
                "checked_in_at": None,
            }
            return promoted_user_id, payload


# ============================================================
# 🚫 สองอย่างที่ D3 **จงใจไม่ทำ** — ตัดสินแล้ว ห้าม "เติม" โดยไม่อ่าน
# ============================================================
#
# ทั้งสองข้อเคยอยู่ในลิสต์ "งานที่เหลือ" ของแผนรอบ 4 · เจ้าของระบบเลือก **ไม่ทำ**
# ⇒ บล็อกนี้มีไว้เพื่อให้คนที่มาอ่านทีหลัง (รวมถึงอนาคตของผมเอง) **ไม่เผลอไปทำ**
# เพราะทั้งคู่ *ฟังดูสมเหตุสมผล* จนดูเหมือนช่องโหว่ที่ต้องปิด — ซึ่งไม่จริง
#
# ── (1) กลไก "หมดอายุคิว / หมดเวลายืนยันที่นั่ง" ──────────────────────────
#   ไอเดีย: ได้ที่นั่งจากคิวแล้วไม่กดยืนยันใน N ชั่วโมง ⇒ ยึดที่นั่งคืนให้คนถัดไป
#
#   ⚠️ **ทำไมไม่ทำ:** ที่นั่งในระบบนี้ **ไม่เคยค้างอยู่กับคนที่ไม่ต้องการมัน** —
#      คนที่เข้าคิวจองที่นั่งเพราะ *เขาอยากไป* (การเข้าคิวนั้นเป็นการขอโดยสมัครใจ)
#      ⇒ "ไม่ยืนยัน" ไม่ได้แปลว่า "ไม่เอา" ส่วนใหญ่แปลว่า "ยังไม่เปิดแอพ"
#      · และคนที่เอาไม่จริงจะ **ถอนเอง** ซึ่งเลื่อนคิวให้คนถัดไปทันทีอยู่แล้ว
#      · ที่แย่กว่านั้น: กลไกนี้จะ **ยึดที่นั่งคืนจากคนที่กำลังนอนหลับ** แล้วส่ง
#        ข้อความ "คุณเสียที่นั่ง" — ความผิดที่ผู้ใช้ไม่ได้ทำ และแก้ไม่ได้ด้วยการกระทำใด ๆ
#      ⇒ ราคาที่จ่ายคือกลไกใหม่ทั้งก้อน (คอลัมน์ + cron + แจ้งเตือน + เทสต์) เพื่อ
#        แลกกับความผิดที่ผู้ใช้มองไม่เห็นสาเหตุ · **กำไรไม่คุ้มและเสี่ยงกว่าปัญหา**
#
#   📌 ที่นั่งที่ "เสียเปล่า" จริง ๆ ถูกเปิดโปงอยู่แล้วที่ **หน้างาน** — สภาเห็นว่าใคร
#      ยังไม่เช็คอิน (`GET /{id}/registrations` + `checked_in_at`) และ **กดมือให้คนที่
#      มาถึงได้** (D2) ⇒ ทางออกของปัญหานี้คือ *คน* ที่ประตู ไม่ใช่ *เวลา* ในฐานข้อมูล
#
# ── (2) endpoint ให้สภา "จัดคิวมือ" (เลื่อน/สลับ/ถอดคนออกจากคิว) ─────────────
#   ⚠️ **ทำไมไม่ทำ:** "เลื่อน/สลับ" = ให้สภาตัดหน้าคิวได้ ⇒ **รูความเป็นธรรมที่เปิดไว้
#      ถาวรโดยไม่มีใครเห็น** (ไม่มีอะไรในระบบบอกได้ว่าการเลื่อนครั้งหนึ่ง ๆ ยุติธรรมไหม
#      เพราะมันดูเหมือนการเลื่อนปกติทุกประการ) — ในระบบที่ทั้งจุดประสงค์คือ *ความยุติธรรม
#      ในการเข้าถึง* การเพิ่มอำนาจนี้ต้องมีเหตุผลหนักกว่านี้มาก
#      · "ถอดคนออกจากคิว" ก็ **ไม่จำเป็น** — คนนั้นถอดตัวเองได้ (`DELETE /register`
#        ใช้ได้กับทุกสถานะที่ไม่ใช่ `cancelled`) ⇒ ทางออกที่มีอยู่แล้วถูกกว่าและ
#        **ไม่ต้องให้สภาเป็นคนตัดสินใจแทนเจ้าตัว**
#      · ⚠️ และมันยัง **ไม่ได้แก้ปัญหาที่คนมักอ้าง** — ถอดคนในคิวออก **ไม่ทำให้ใครได้
#        ที่นั่ง** (ไม่มีที่นั่งว่างลง) ⇒ คนถัดไปยังต้องรอคน *ถือที่นั่ง* ถอนอยู่ดี
#
#   📌 ถ้าวันหนึ่งจำเป็นจริง ๆ (เช่น มีคนในคิวที่ติดต่อไม่ได้และไม่กดถอนเอง) ⇒ สิ่งที่ต้อง
#      คุยกันก่อนคือ **"สภาควรมีอำนาจตัดสินใจแทนเจ้าตัวได้แค่ไหน"** ซึ่งเป็นคำถามเชิงนโยบาย
#      ไม่ใช่คำถามทางเทคนิค · ทางที่เบากว่ามากคือ **ให้สภาติดต่อคนนั้นแล้วให้เขากดถอนเอง**


# ============================================================
# 🎟️ เช็คอินหน้างาน (D2) — ต้องมีสิทธิ์ MANAGE_EVENTS
# ============================================================

async def check_in_registration(
    pool: asyncpg.Pool,
    user_id: int,
    event_id: int,
    *,
    token: Optional[str] = None,
    registration_id: Optional[int] = None,
) -> dict:
    """
    เช็คอินผู้เข้าร่วม — รับได้สองทาง: **สแกนบัตร QR** (`token`) หรือ **กดมือ** (`registration_id`)

    คืน payload เดียวกันทั้งสองทาง · `user_id` ที่รับมาคือ **สภาที่ทำรายการ (ผู้กระทำ)**
    ไม่ใช่นักเรียนที่ถูกเช็คอิน (คนนั้นอยู่ใน `payload["user_id"]`)

    ⭐ **สแกนซ้ำต้องไม่เป็น error และต้องไม่ทับเวลาที่เช็คอินจริงครั้งแรก**
       `checked_in_at` = "เวลาที่คนนี้มาถึง" ไม่ใช่ "เวลาที่สแกนล่าสุด" ⇒ ถ้าเขียนทับ
       หลักฐานการมาถึงจะเพี้ยนทุกครั้งที่มีคนเผลอสแกนรัว (ซึ่งเกิดตลอดหน้างาน) และ
       คำถาม "มากี่โมง" จะตอบไม่ได้อีกเลย

    ⚠️ **ไม่ล็อกแถวกิจกรรม (`FOR UPDATE` บน `events`) ต่างจาก `register_event`** — การเช็คอิน
       **ไม่แตะจำนวนที่นั่ง** (`registered → checked_in` ยังนับเป็นคนถือที่นั่งเท่าเดิม — ดู
       `_STATS_JOIN`) ⇒ ไม่มีอะไรให้แย่งกับคนที่กำลังสมัคร/ถอน · ล็อกแค่แถวการลงทะเบียนก็พอ
       (การล็อกเกินจำเป็นทำให้สภาในสนามสแกนช้าเวลาคนต่อคิว)

    ⚠️ **ไม่ยิงแจ้งเตือน** — นักเรียนยืนอยู่ตรงหน้าสภาอยู่แล้ว (เหตุผลเดียวกับ `restore_event`)

    ⭐ **invariant ของตารางนี้: `checked_in_at IS NOT NULL` ⟺ `status = 'checked_in'`**
       ⇒ การถอน (`cancel_registration`) และการสมัครใหม่บนแถวเดิม (`register_event`) **ล้างค่านี้ทิ้ง**
       เพราะเวลานั้นเป็นของ *รอบการลงทะเบียนที่จบไปแล้ว* ไม่ใช่ของรอบใหม่ — ถ้าปล่อยค้าง
       แถวสถานะ `registered` จะมีเวลาที่เช็คอินติดมาด้วย แล้วคำถาม "คนนี้เช็คอินหรือยัง"
       จะตอบด้วยสองวิธีที่ให้คำตอบต่างกัน (ดูจาก `status` หรือดูจาก `checked_in_at`)
       · หลักฐานไม่หาย: ค่าเดิมถูกเก็บลง `old_values` ของ audit ทั้งสองเส้นทาง
    """
    async with pool.acquire() as conn:
        await require_permission_anywhere(conn, user_id, "MANAGE_EVENTS")

        method = "qr" if token is not None else "manual"
        if method == "qr":
            parsed = check_in_token.parse(token)
            if not parsed:
                raise ValidationError("รหัสเช็คอินไม่ถูกต้อง")
            token_event_id, registration_id = parsed
            # ⚠️ **ด่านนี้ไม่ใช่กำแพงความปลอดภัย — เป็นข้อความที่ทำให้สภาหน้างานรู้ว่าเกิดอะไรขึ้น**
            #
            # 🧪 พิสูจน์ด้วย mutation แล้ว (ปิดบรรทัดนี้ → `test_check_in_token_of_other_event_is_rejected`
            #    ตก): บัตรของงาน A ยิงไปที่งาน B **ไม่ได้อยู่ดี** เพราะคิวรีข้างล่างกรอง
            #    `AND r.event_id = $2` ⇒ `registration_id` (SERIAL ร่วมกันทุกกิจกรรม) ไปไม่ถึงแถว
            #    ของอีกงานหนึ่งได้เลย · ที่เปลี่ยนไปคือ **ข้อความ**: ปิดแล้วได้ 404
            #    "ไม่พบการลงทะเบียนนี้ในกิจกรรมนี้" แทนที่จะเป็น 400 "รหัสนี้เป็นของกิจกรรมอื่น"
            #
            # ⇒ ตอนประตูงาน ที่มีเด็กยื่นบัตรผิดงาน 404 ชี้ว่า "ระบบหาข้อมูลไม่เจอ" ซึ่งทำให้สภา
            #    ไปไล่หาปัญหาที่อื่น (เน็ต? ยังไม่กดยืนยัน?) แทนที่จะรู้ทันทีว่าหยิบบัตรผิดใบ
            #    — เก็บไว้เพราะราคาคือ 2 บรรทัด และสิ่งที่ซื้อมาคือคำวินิจฉัยที่ถูกตั้งแต่ครั้งแรก
            if token_event_id != event_id:
                raise ValidationError("รหัสนี้เป็นของกิจกรรมอื่น")

        async with conn.transaction():
            # ⚠️ กิจกรรมที่ถูกลบต้อง 404 — ให้ตรงกับ `list_registrations` ที่ 404 เหมือนกัน
            #    (ถ้าที่นี่ผ่าน สภาจะเช็คอินคนในกิจกรรมที่ไม่มีอยู่ในระบบได้ = ข้อมูลผี)
            # ⭐ แต่กิจกรรมที่ **ยกเลิก** (`cancelled`) เช็คอินได้ — เป็นการตัดสินใจโดยเจตนา:
            #    การยกเลิกในระบบกับการที่งานยังจัดจริง เป็นเรื่องที่เกิดขึ้นได้ (สภาแก้ไม่ทัน)
            #    และการ "ห้าม" จะทำให้สภาหน้างานทำอะไรไม่ได้เลยในวันที่สายเกินแก้
            #    ⇒ ปล่อยให้เช็คอินได้ ประวัติยังอยู่ครบ และไม่มีที่ไหนพังเพราะมัน
            exists = await conn.fetchval(
                "SELECT 1 FROM events WHERE id = $1 AND deleted_at IS NULL", event_id
            )
            if not exists:
                raise NotFoundError("ไม่พบกิจกรรมนี้")

            row = await conn.fetchrow(
                """
                SELECT r.id, r.event_id, r.user_id, r.status, r.checked_in_at,
                       u.full_name AS user_name
                FROM event_registrations r
                LEFT JOIN users u ON u.id = r.user_id
                WHERE r.id = $1 AND r.event_id = $2
                FOR UPDATE OF r
                """,
                registration_id, event_id,
            )
            if not row:
                raise NotFoundError("ไม่พบการลงทะเบียนนี้ในกิจกรรมนี้")

            # ⚠️ ข้อความแยกกันสองแบบโดยเจตนา — คนละสถานการณ์และคนละทางแก้:
            #    · ยกเลิกแล้ว = "ใบนี้ตายแล้ว" (ควรตรวจว่ามาสแกนผิดงานหรือเปล่า)
            #    · คิวสำรอง  = "ยังไม่ได้ที่นั่ง" (ต้องไปดูว่ามีคนไม่มาให้เลื่อนคิวหรือไม่)
            #    ถ้ารวมเป็นข้อความเดียว สภาหน้างานจะไม่รู้ว่าควรทำอะไรต่อ
            if row["status"] == "cancelled":
                raise ValidationError("การลงทะเบียนนี้ถูกยกเลิกแล้ว")
            if row["status"] == "waitlisted":
                raise ValidationError("คนนี้อยู่ในคิวสำรอง ยังไม่ได้ที่นั่ง")

            already_checked_in = row["status"] == "checked_in"
            if already_checked_in:
                checked_in_at = row["checked_in_at"]
            else:
                # เงื่อนไข `AND status = 'registered'` อยู่ใน WHERE ไม่ใช่ `if` ใน Python
                # (แบบเดียวกับ `publish_event`) ⇒ แม้มีคนสแกนพร้อมกันสองเครื่องจากสอง replica
                # การเขียนทับกันก็เป็นไปไม่ได้ในระดับ DB
                checked_in_at = await conn.fetchval(
                    """
                    UPDATE event_registrations
                    SET status = 'checked_in', checked_in_at = NOW(), updated_at = NOW()
                    WHERE id = $1 AND status = 'registered'
                    RETURNING checked_in_at
                    """,
                    row["id"],
                )
                if checked_in_at is None:
                    # ป้องกันไว้เฉย ๆ — แถวถูกล็อกอยู่ (FOR UPDATE) ⇒ มาถึงตรงนี้ไม่ได้จริง
                    raise ValidationError("สถานะเปลี่ยนไปแล้ว กรุณาสแกนใหม่")

            await AuditLogger("event_service").log(
                conn=conn,
                action="CHECK_IN_EVENT",
                actor_identifier=str(user_id),
                client_source="web",
                # ผู้กระทำ = สภาที่สแกน ⇒ เก็บในคอลัมน์ `user_id` (ตามสัญญาของ AuditLogger)
                user_id=user_id,
                entity_type="event",
                entity_id=event_id,
                old_values={
                    "status": row["status"],
                    "checked_in_at": row["checked_in_at"],
                },
                new_values={
                    "status": "checked_in",
                    "checked_in_at": checked_in_at,
                    # ⭐ `method` = หลักฐานที่โทเคนซื้อมา: `qr` พิสูจน์ได้ว่าเป็นบัตรที่ระบบออกให้
                    #    ส่วน `manual` คือสภากดเอง — สองอย่างนี้ต่างกันจริงในทางปฏิบัติ
                    "method": method,
                    "registration_id": row["id"],
                    "attendee_user_id": row["user_id"],
                    "already_checked_in": already_checked_in,
                },
            )

    return {
        "registration_id": row["id"],
        "event_id": event_id,
        "user_id": row["user_id"],
        "user_name": row["user_name"],
        "status": "checked_in",
        "checked_in_at": checked_in_at,
        "already_checked_in": already_checked_in,
        "method": method,
    }
