"""🎓 ปีการศึกษา (Academic Years) — "ปี 2569 ใครอยู่ห้องไหน ตำแหน่งอะไร"

**ทำไมต้องมี (และทำไมไม่ใช้ `academic_terms` ที่มีอยู่):**
  ทั้งสองตอบคนละคำถาม —
    · ภาคเรียน = "ภาคนี้เป็นยังไง" → ใช้ **กรองสถิติตามช่วงวันที่** (me_service / home)
    · ปีการศึกษา = "ปีนี้ใครเป็นสมาชิกที่ไหน" → ใช้ **เก็บประวัติสมาชิก** และเป็นแกนของ
      "เลื่อนชั้นทั้งโรงเรียน"
  1 ปีมี 2 ภาค ⇒ ถ้าให้สมาชิกผูกกับ "ภาค" คำถาม "คนนี้ย้ายห้องตอนภาค 2 ใช่ไหม" จะตอบไม่ได้
  ตั้งแต่ต้น ⇒ มิติเวลาของ **สมาชิก** ต้องเป็นปี ไม่ใช่ภาค

**ทำไมไม่สร้าง "ห้องใหม่ทุกปี" (`ม.4/1 ปี 2569`):**
  "ม.4/1" คือห้องที่มีอยู่จริงในหลักสูตร — สิ่งที่เปลี่ยนทุกปีคือ *คน* ไม่ใช่ห้อง
  ⇒ มิติปีอยู่ที่ `students.academic_year_id` **ไม่ใช่ที่ `rooms`** ⇒ `rooms` ไม่ถูกแตะเลย

จุดที่ต้องระวัง (อ่านก่อนแก้):
  1. **มีปีปัจจุบันได้ตัวเดียว** — บังคับด้วย partial unique index
     `uq_academic_years_single_current` (migrations/027) ไม่ใช่ด้วยโค้ด
     ⚠️ index เป็น non-deferrable ⇒ ทุกที่ที่ตั้ง `is_current = TRUE` **ต้องล้างตัวเก่าก่อน**
        ใน transaction เดียวกัน (`_clear_current`) — สลับลำดับ = UniqueViolationError
  2. **ตั้งปีว่างเป็นปีปัจจุบันไม่ได้ ถ้าปีอื่นยังมีสมาชิก active** (`_assert_settable_as_current`)
     ⚠️ นี่คือด่านกันความผิดพลาดที่แพงที่สุดของทั้งระบบ: การกด "ตั้งเป็นปีปัจจุบัน" บนปีที่
        เพิ่งสร้างเสร็จ (ยังไม่มีใครอยู่) จะทำให้ **รายชื่อทั้งโรงเรียนหายวับในคลิกเดียว**
        เพราะทุกคิวรีรายชื่อกรองด้วยปีปัจจุบัน · และ DEFAULT ของ `students.academic_year_id`
        เปลี่ยนตาม ⇒ การลงทะเบียนใหม่ทั้งหมดจะไปลงปีผิดด้วย
     ✅ ลำดับที่ถูกคือ "import รายชื่อของปีใหม่ (ระบุปีในไฟล์) → แล้วค่อยตั้งเป็นปัจจุบัน"
        หรือ "กดเลื่อนชั้นทั้งโรงเรียน" ซึ่งสร้างแถวปีใหม่ให้ก่อนแล้วตั้ง current เองในทีเดียว
     ⚠️ `rollover_service` **ไม่ผ่านฟังก์ชันนี้** — มัน `UPDATE ... SET is_current` เองหลัง
        สร้างแถวเสร็จ (ไม่ต้องมีด่านนี้เพราะมันสร้างสมาชิกให้ก่อนอยู่แล้ว)
  3. **ลบปีที่ยังมีสมาชิกไม่ได้** — ไม่ใช่เพราะ FK (FK เป็น RESTRICT ซึ่งกันแค่ hard delete)
     แต่เพราะ soft delete ปีทิ้งไว้จะทำให้แถวสมาชิกชี้ไปปีที่ "ถูกลบ" ⇒ คิวรีที่กรองปีปกติ
     จะไม่เห็นเด็กเหล่านั้นอีกเลยทั้งที่ `deleted_at IS NULL`
     ⇒ ถ้าตั้งปีผิด ให้ **ย้าย/ลบสมาชิกในปีนั้นก่อน** แล้วค่อยลบปี
  4. **ลบปีปัจจุบันไม่ได้** — ต้องตั้งปีอื่นเป็นปัจจุบันก่อน (ถ้าปล่อย จะไม่มีปีปัจจุบัน ⇒
     `students.academic_year_id` DEFAULT ชี้ปีที่ถูกลบ และ `fetch_current_year()` คืน None
     ซึ่งผู้บริโภคหลายที่ตีความไม่ได้)
  5. **`end_date` รวมวันสุดท้าย (inclusive)** — เหมือนภาคเรียน (ดูกฎเดียวกันใน term_service)

ตาม docs/rules/backend.md: SQL อยู่ในชั้นนี้เท่านั้น · ทุก mutation อยู่ใน transaction
เดียวกับ audit log · ลบ = soft delete
"""
import math
from datetime import date
from typing import Optional

import asyncpg

from core.exceptions import NotFoundError, ValidationError
from core.logger import AuditLogger
from core.rbac import require_permission_anywhere

# สิทธิ์เดียวกับภาคเรียน — มีอยู่แล้วใน config/roles.json (admin / teacher_council / council_president)
# ⚠️ **ไม่ใช่** `MANAGE_STUDENTS` — การเปลี่ยนปีปัจจุบันกระทบทั้งโรงเรียน จึงยกระดับเป็น
#    "ตั้งค่าระบบ" และครูระดับชั้น (ที่มี MANAGE_STUDENTS) ต้องแตะไม่ได้
PERMISSION = "MANAGE_SETTINGS"

# คอลัมน์ที่ยอมให้แก้ผ่าน PATCH — allowlist เพราะชื่อคอลัมน์ถูก interpolate ลง SQL
# ⚠️ **ไม่รวม `is_current`** — ต้องผ่าน set_current_year() เท่านั้น (ดูข้อ 1-2 หัวไฟล์)
_EDITABLE_COLUMNS = ("year_be", "name", "start_date", "end_date")

# เงื่อนไขกรองสถานะ — dict นี้คือ **จุดเดียวที่นิยามคำว่าสถานะ**
# ใช้ทั้ง COUNT(*) และคิวรีหลัก ⇒ total กับ items ตรงกันเสมอ
_STATUS_CONDITIONS = {
    "current": "y.deleted_at IS NULL AND y.is_current",
    "active": "y.deleted_at IS NULL",
    "deleted": "y.deleted_at IS NOT NULL",
    "all": "TRUE",
}

# ปีปัจจุบันขึ้นก่อน แล้วใหม่สุดก่อน · `y.id DESC` รองท้าย (กันหน้าทับกันเมื่อ year_be ซ้ำ — เป็นไปไม่ได้
# เพราะมี unique index แต่คงไว้ให้ลำดับนิ่งแน่นอนเวลาเทสต์)
_ORDER_BY = "ORDER BY y.is_current DESC, y.year_be DESC, y.id DESC"

# `member_count` นับ **ทุกสถานะ** ที่ยังไม่ถูกลบ (ไม่กรอง status) — ปีที่จบไปแล้วต้องยังโชว์
# จำนวนจริงได้ ไม่ใช่ 0 · subquery ต่อแถว แต่อ่านทีละ ≤ 200 แถว ⇒ ถูกกว่าการ GROUP BY join
_SELECT_COLUMNS = """
    y.id, y.year_be, y.name, y.start_date, y.end_date, y.is_current,
    y.created_at, y.updated_at, y.deleted_at,
    (SELECT COUNT(*) FROM students s
      WHERE s.academic_year_id = y.id AND s.deleted_at IS NULL) AS member_count
"""


async def _fetch_one(conn: asyncpg.Connection, year_id: int) -> dict:
    row = await conn.fetchrow(
        f"SELECT {_SELECT_COLUMNS} FROM academic_years y WHERE y.id = $1", year_id
    )
    return dict(row) if row else {}


async def _clear_current(conn: asyncpg.Connection) -> None:
    """ล้างปีปัจจุบันตัวเก่า — ต้องเรียก **ก่อน** ตั้งตัวใหม่เสมอ (index non-deferrable)"""
    await conn.execute(
        """
        UPDATE academic_years
        SET is_current = FALSE, updated_at = NOW()
        WHERE is_current AND deleted_at IS NULL
        """
    )


async def _members(conn: asyncpg.Connection, year_id: int) -> int:
    """จำนวนแถวสมาชิกที่ยังไม่ถูกลบในปีนี้ (ทุกสถานะ)"""
    return await conn.fetchval(
        "SELECT COUNT(*) FROM students WHERE academic_year_id = $1 AND deleted_at IS NULL",
        year_id,
    )


async def _assert_settable_as_current(
    conn: asyncpg.Connection, year_id: Optional[int]
) -> None:
    """ด่านกัน "ล็อกโรงเรียน" — ดูเหตุผลเต็มที่ข้อ 2 ของ docstring หัวไฟล์

    อนุญาตเมื่อ: ปีนั้นมีสมาชิกอยู่แล้ว **หรือ** ทั้งโรงเรียนยังไม่มีสมาชิก active เลย
    (กรณีหลัง = โรงเรียนเพิ่งติดตั้ง ยังไม่มีใคร import — ต้องตั้งปีแรกเป็นปัจจุบันได้)

    ⚠️ `year_id=None` = ปีที่ **กำลังจะถูกสร้าง** (ยังไม่มี id) ⇒ ข้ามฝั่ง "ปีนี้มีสมาชิกไหม"
       เพราะคำตอบคือไม่มีแน่นอน เหลือแค่เช็คฝั่ง "ที่อื่นมีไหม" ซึ่งเป็นเจตนาจริง ๆ
    """
    if year_id is not None and await _members(conn, year_id):
        return
    elsewhere = await conn.fetchval(
        "SELECT COUNT(*) FROM students WHERE deleted_at IS NULL AND status = 'active'"
    )
    if elsewhere:
        raise ValidationError(
            f"ตั้งปีที่ยังไม่มีสมาชิกเป็นปีปัจจุบันไม่ได้ "
            f"(ขณะนี้มีสมาชิกที่ใช้งานอยู่ {elsewhere} คนในปีอื่น) — "
            "ถ้าขึ้นปีใหม่ ให้กด «เลื่อนชั้นทั้งโรงเรียน» หรือ import รายชื่อของปีใหม่ "
            "โดยระบุคอลัมน์ «ปีการศึกษา» ในไฟล์ แล้วจึงตั้งเป็นปีปัจจุบัน"
        )


# ============================================================
# 📖 อ่าน "ปีปัจจุบัน" — ผู้บริโภคทุกที่ใช้ตัวนี้
# ============================================================

async def fetch_current_year(conn: asyncpg.Connection) -> Optional[dict]:
    """อ่านปีปัจจุบันโดยใช้ connection ของ caller (ให้ reuse ได้ในคิวรีชุดเดียว)

    ⚠️ กรอง `deleted_at IS NULL` ด้วย — ปีที่ถูกลบไม่ใช่ปีปัจจุบัน (แต่ตามข้อ 4 เราห้าม
       ลบปีปัจจุบันอยู่แล้ว ⇒ เงื่อนไขนี้เป็นเข็มขัดนิรภัยชั้นสอง)
    """
    row = await conn.fetchrow(
        """
        SELECT id, year_be, name, start_date, end_date
        FROM academic_years
        WHERE is_current AND deleted_at IS NULL
        LIMIT 1
        """
    )
    return dict(row) if row else None


async def get_current_year(pool: asyncpg.Pool) -> Optional[dict]:
    """ปีปัจจุบัน หรือ `None` ถ้ายังไม่มี (ตามทฤษฎีเกิดไม่ได้หลัง migration 027 seed ไว้)"""
    async with pool.acquire() as conn:
        return await fetch_current_year(conn)


async def get_current_year_id(pool: asyncpg.Pool) -> Optional[int]:
    """`id` ของปีปัจจุบัน — ทางลัดสำหรับ service อื่นที่ต้องการแค่ตัวเลขไปใส่ WHERE"""
    year = await get_current_year(pool)
    return year["id"] if year else None


# ============================================================
# 📋 รายการ (หน้า admin)
# ============================================================

async def list_years(
    pool: asyncpg.Pool,
    user_id: int,
    *,
    status: str = "active",
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """รายการปีการศึกษา — envelope {items,total,page,page_size,pages} เหมือน /api/settings/terms"""
    if status not in _STATUS_CONDITIONS:
        raise ValidationError("สถานะที่กรองไม่ถูกต้อง")

    async with pool.acquire() as conn:
        await require_permission_anywhere(conn, user_id, PERMISSION)

        where_sql = _STATUS_CONDITIONS[status]

        # นับ total แยกจากคิวรีหลัก — ห้ามใช้ COUNT(*) OVER() (offset เลยหน้าสุดท้ายแล้วจะได้ 0)
        total = await conn.fetchval(
            f"SELECT COUNT(*) FROM academic_years y WHERE {where_sql}"
        )

        rows = await conn.fetch(
            f"""
            SELECT {_SELECT_COLUMNS}
            FROM academic_years y
            WHERE {where_sql}
            {_ORDER_BY}
            LIMIT $1 OFFSET $2
            """,
            limit,
            offset,
        )

    page_size = max(1, limit)
    return {
        "items": [dict(r) for r in rows],
        "total": total or 0,
        "page": offset // page_size + 1,
        "page_size": page_size,
        "pages": max(1, math.ceil((total or 0) / page_size)),
    }


async def get_year(pool: asyncpg.Pool, user_id: int, year_id: int) -> dict:
    """ปีการศึกษารายตัว — สำหรับ **หน้าแก้ไข** (เต็มหน้า) ที่โหลดข้อมูลเองจาก URL

    ⚠️ **คืนปีที่ถูกลบด้วย** (ต่างจาก `list_years status='active'`) แล้วให้ผู้เรียกดู
       `deleted_at` เอง — เพราะเหตุผลที่ต้องมีฟังก์ชันนี้คือ "โหลดจาก URL ได้"
       ถ้ากรอง deleted ทิ้ง ผู้ใช้ที่เปิด URL ของปีที่เพิ่งถูกลบจะได้ 404 ที่อ่านไม่ออก
       แทนที่จะได้ข้อความ "ปีนี้ถูกลบแล้ว — กู้คืนก่อนจึงจะแก้ได้"
       (ตัวด่านจริงอยู่ที่ `update_year` อยู่แล้ว ⇒ ไม่มีทางแก้ปีที่ถูกลบได้)
    """
    async with pool.acquire() as conn:
        await require_permission_anywhere(conn, user_id, PERMISSION)
        row = await _fetch_one(conn, year_id)

    if not row:
        raise NotFoundError("ไม่พบปีการศึกษานี้")
    return row


# ============================================================
# ✍️ Mutations
# ============================================================

async def create_year(
    pool: asyncpg.Pool,
    user_id: int,
    *,
    year_be: int,
    name: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    is_current: bool = False,
) -> dict:
    """สร้างปีการศึกษา + audit

    - `name` เว้นว่าง → `"ปีการศึกษา {year_be}"`
    - `is_current=True` → ปลดปีปัจจุบันตัวเก่าในทรานแซกชันเดียวกัน (ผ่านด่านข้อ 2)
    - `year_be` ซ้ำ (กับปีที่ยังไม่ถูกลบ) → **400 พร้อมข้อความไทย** ไม่ใช่ 500 จาก IntegrityError
      (unique index `uq_academic_years_year_be` เป็นด่านสุดท้ายที่ DB)
    """
    if start_date and end_date and end_date < start_date:
        raise ValidationError("วันสิ้นสุดต้องไม่ก่อนวันเริ่มต้น")

    async with pool.acquire() as conn:
        async with conn.transaction():
            await require_permission_anywhere(conn, user_id, PERMISSION)

            dup = await conn.fetchval(
                "SELECT id FROM academic_years WHERE year_be = $1 AND deleted_at IS NULL",
                year_be,
            )
            if dup:
                raise ValidationError(f"มีปีการศึกษา {year_be} อยู่แล้ว")

            if is_current:
                await _assert_settable_as_current(conn, None)  # ปีใหม่ยังไม่มี id
                await _clear_current(conn)

            new_id = await conn.fetchval(
                """
                INSERT INTO academic_years (year_be, name, start_date, end_date, is_current)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id
                """,
                year_be,
                name or f"ปีการศึกษา {year_be}",
                start_date,
                end_date,
                is_current,
            )

            await AuditLogger("year_service").log(
                conn=conn,
                action="CREATE_ACADEMIC_YEAR",
                actor_identifier=str(user_id),
                client_source="web",
                user_id=user_id,
                entity_type="academic_year",
                entity_id=new_id,
                new_values={
                    "year_be": year_be,
                    "name": name or f"ปีการศึกษา {year_be}",
                    "start_date": str(start_date) if start_date else None,
                    "end_date": str(end_date) if end_date else None,
                    "is_current": is_current,
                },
            )

        return await _fetch_one(conn, new_id)


async def update_year(
    pool: asyncpg.Pool,
    user_id: int,
    year_id: int,
    changes: dict,
) -> dict:
    """แก้ปีการศึกษา (PATCH — เฉพาะฟิลด์ที่ส่งมา) + audit old/new values

    ⚠️ แก้ได้เฉพาะปีที่ยังไม่ถูกลบ — ปีที่ถูกลบต้อง "กู้คืน" ก่อน ไม่ให้แก้ประวัติเงียบ ๆ

    ⚠️ **PATCH ที่ส่ง `null` มาตรง ๆ ต้องโดนปฏิเสธที่นี่ — ไม่ใช่ปล่อยผ่าน แล้วไปพังเป็น 500**
       `exclude_unset` ไม่ช่วยเลย: ส่ง `{"year_be": null}` มา = ฟิลด์นั้นถูก "set" แล้ว
       ⇒ ค่าที่ได้คือ `{"year_be": None}` ซึ่งผ่าน allowlist ต่อไป ⇒ `UPDATE ... SET year_be = NULL`
       = `NotNullViolationError` → 500
       ⚠️ **แต่ `start_date`/`end_date` ส่ง `null` ได้จริง** เพราะสองคอลัมน์นั้น nullable
          และการ "ล้างวันที่" เป็นคำขอที่มีความหมาย ("ปีนี้ยังไม่รู้วันเปิดเทอม")
          ⇒ กรองเฉพาะฟิลด์ที่ `NOT NULL` (แบบเดียวกับ `announcement_service.link`)
    """
    not_nullable = {"year_be", "name"}
    nulls = sorted(k for k, v in changes.items() if k in not_nullable and v is None)
    if nulls:
        raise ValidationError(
            f"ห้ามส่งค่า null ในฟิลด์ {', '.join(nulls)} — ถ้าไม่ต้องการแก้ฟิลด์นั้น ให้ไม่ส่งมาที่เลย"
        )

    safe = {k: v for k, v in changes.items() if k in _EDITABLE_COLUMNS}
    # `null` ของวันที่ = คำสั่งล้างค่า ⇒ ต้องนับเป็น "มีการแก้" ไม่ใช่ทิ้ง (ต่างจาก term_service
    # ที่ทุกคอลัมน์ NOT NULL ⇒ ที่นั่น `safe` ว่างก็ต่อเมื่อไม่มีอะไรส่งมาจริง ๆ)
    if not safe:
        raise ValidationError("ไม่มีข้อมูลที่จะแก้ไข")

    async with pool.acquire() as conn:
        async with conn.transaction():
            await require_permission_anywhere(conn, user_id, PERMISSION)

            before = await conn.fetchrow(
                """
                SELECT year_be, name, start_date, end_date
                FROM academic_years
                WHERE id = $1 AND deleted_at IS NULL
                FOR UPDATE
                """,
                year_id,
            )
            if not before:
                raise NotFoundError("ไม่พบปีการศึกษานี้ (อาจถูกลบไปแล้ว)")

            # PATCH ส่งมาอาจเป็นวันเดียว ⇒ เทียบกับค่าที่เก็บอยู่จริง ไม่ใช่กับ None
            # (ค่าว่างทั้งคู่ = "ยังไม่รู้วัน" ซึ่งเป็นสถานะถูกต้อง ⇒ ไม่ต้องเทียบ)
            new_start = safe.get("start_date", before["start_date"])
            new_end = safe.get("end_date", before["end_date"])
            if new_start and new_end and new_end < new_start:
                raise ValidationError("วันสิ้นสุดต้องไม่ก่อนวันเริ่มต้น")

            # แก้ พ.ศ. = แก้ตัวตนของปี ⇒ ต้องกันซ้ำเองก่อน ไม่งั้น IntegrityError → 500
            new_be = safe.get("year_be")
            if new_be is not None and new_be != before["year_be"]:
                dup = await conn.fetchval(
                    "SELECT id FROM academic_years WHERE year_be = $1 AND deleted_at IS NULL AND id <> $2",
                    new_be, year_id,
                )
                if dup:
                    raise ValidationError(f"มีปีการศึกษา {new_be} อยู่แล้ว")

            # dynamic SET: จอง $1 ไว้ให้ WHERE แล้วฟิลด์เริ่มที่ len(params)+1
            params: list = [year_id]
            sets: list = []
            for column, value in safe.items():
                params.append(value)
                sets.append(f"{column} = ${len(params)}")

            # `updated_at = NOW()` ไม่มี param จึงไม่กระทบเลข placeholder
            sql = (
                f"UPDATE academic_years SET {', '.join(sets)}, updated_at = NOW() "
                "WHERE id = $1"
            )
            assert sql.count("$") == len(params), "placeholder ไม่ตรงกับจำนวน param"

            await conn.execute(sql, *params)

            await AuditLogger("year_service").log(
                conn=conn,
                action="UPDATE_ACADEMIC_YEAR",
                actor_identifier=str(user_id),
                client_source="web",
                user_id=user_id,
                entity_type="academic_year",
                entity_id=year_id,
                old_values={
                    k: str(before[k]) if isinstance(before[k], date) else before[k]
                    for k in safe
                },
                new_values={
                    k: str(v) if isinstance(v, date) else v for k, v in safe.items()
                },
            )

        return await _fetch_one(conn, year_id)


async def set_current_year(pool: asyncpg.Pool, user_id: int, year_id: int) -> dict:
    """ตั้งปีนี้เป็น "ปีปัจจุบัน" — ปลดตัวเก่าก่อน แล้วตั้งตัวใหม่ (ลำดับสำคัญมาก)

    ⚠️ **การกระทำนี้เปลี่ยน DEFAULT ของ `students.academic_year_id` ให้ชี้ปีใหม่**
       ⇒ แถวสมาชิกที่สร้างหลังจากนี้ (เช่น การลงทะเบียนใหม่) จะไปอยู่ปีนี้ทันที
       ⇒ จึงไม่ใช่แค่ "เปลี่ยนป้ายชื่อ" แต่เป็นการย้ายจุดที่คนใหม่จะไปลง

    มี endpoint แยกจาก PATCH โดยเจตนา: การเปลี่ยนปีปัจจุบันเป็นการกระทำที่มีความหมาย
    ต่างจากการแก้ชื่อ/วันที่ และต้องผ่านด่านข้อ 2 เสมอ ⇒ ให้มีทางเดียวที่ทำถูก
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            await require_permission_anywhere(conn, user_id, PERMISSION)

            row = await conn.fetchrow(
                """
                SELECT id, year_be, name, is_current FROM academic_years
                WHERE id = $1 AND deleted_at IS NULL
                FOR UPDATE
                """,
                year_id,
            )
            if not row:
                raise NotFoundError("ไม่พบปีการศึกษานี้ (อาจถูกลบไปแล้ว)")
            if row["is_current"]:
                # กดซ้ำ = ไม่ทำอะไร ไม่ทับ timestamp เดิม (คืนแถวเดิมไปเลย)
                return await _fetch_one(conn, year_id)

            # ด่านกันล็อกโรงเรียน (ข้อ 2) — ต้องเช็ค **ก่อน** ล้างตัวเก่า ไม่งั้น rollback
            # ไปแล้วยังเสีย timestamp ของปีเก่าโดยไม่จำเป็น
            await _assert_settable_as_current(conn, year_id)

            # ⚠️ ล้างก่อนตั้ง — สลับสองบรรทัดนี้ = UniqueViolationError
            await _clear_current(conn)
            await conn.execute(
                "UPDATE academic_years SET is_current = TRUE, updated_at = NOW() WHERE id = $1",
                year_id,
            )

            # 🔑 ทำให้แถวใหม่ (DEFAULT) ไปลงปีนี้ — เป็น metadata-only operation (PG 11+)
            #    ไม่ rewrite ตาราง ⇒ เร็วแม้ `students` มีหลายพันแถว
            #    ⚠️ ใช้ literal ที่ interpolate (ค่าเป็น int จาก DB ⇒ ไม่มีทาง inject)
            await conn.execute(
                f"ALTER TABLE students ALTER COLUMN academic_year_id SET DEFAULT {int(year_id)}"
            )

            await AuditLogger("year_service").log(
                conn=conn,
                action="SET_CURRENT_YEAR",
                actor_identifier=str(user_id),
                client_source="web",
                user_id=user_id,
                entity_type="academic_year",
                entity_id=year_id,
                old_values={"is_current": False},
                new_values={"year_be": row["year_be"], "name": row["name"], "is_current": True},
            )

        return await _fetch_one(conn, year_id)


async def delete_year(pool: asyncpg.Pool, user_id: int, year_id: int) -> dict:
    """ลบปีการศึกษา (soft delete) + audit

    ⚠️ สองด่านที่ห้ามข้าม (เหตุผลเต็มที่ข้อ 3-4 ของ docstring หัวไฟล์):
       1. **ลบปีปัจจุบันไม่ได้** — ต้องตั้งปีอื่นเป็นปัจจุบันก่อน
       2. **ลบปีที่ยังมีสมาชิกไม่ได้** — ต้องย้าย/เลื่อนชั้นเด็กออกก่อน
       ทั้งสองกรณีตอบ **400 พร้อมข้อความไทยที่บอกทางออก** ไม่ใช่ 409/500
       ⇒ `delete` จึงหมายถึง "สร้างผิด ยังไม่เคยใช้" เท่านั้น ซึ่งเป็นความหมายที่ปลอดภัย
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            await require_permission_anywhere(conn, user_id, PERMISSION)

            row = await conn.fetchrow(
                """
                SELECT id, year_be, name, is_current FROM academic_years
                WHERE id = $1 AND deleted_at IS NULL
                FOR UPDATE
                """,
                year_id,
            )
            if not row:
                # ไม่พบ หรือ ถูกลบไปแล้ว (กันกดซ้ำ — ไม่ทับ deleted_at เดิมด้วย NOW() ใหม่)
                raise NotFoundError("ไม่พบปีการศึกษานี้ (อาจถูกลบไปแล้ว)")

            if row["is_current"]:
                raise ValidationError(
                    "ลบปีปัจจุบันไม่ได้ — ต้องตั้งปีอื่นเป็นปีปัจจุบันก่อน แล้วจึงลบปีนี้"
                )

            members = await _members(conn, year_id)
            if members:
                raise ValidationError(
                    f"ลบปีนี้ไม่ได้เพราะยังมีสมาชิก {members} คนอยู่ในปี "
                    f"{row['year_be']} — ให้ย้ายหรือเลื่อนชั้นสมาชิกเหล่านั้นออกก่อน "
                    "(ถ้าต้องการแค่ซ่อนจากรายการ ให้ใช้การกรองสถานะแทน)"
                )

            await conn.execute(
                """
                UPDATE academic_years
                SET deleted_at = NOW(), is_current = FALSE, updated_at = NOW()
                WHERE id = $1
                """,
                year_id,
            )

            await AuditLogger("year_service").log(
                conn=conn,
                action="DELETE_ACADEMIC_YEAR",
                actor_identifier=str(user_id),
                client_source="web",
                user_id=user_id,
                entity_type="academic_year",
                entity_id=year_id,
                old_values={"deleted_at": None},
                new_values={"deleted_at": "NOW()"},
            )

        return await _fetch_one(conn, year_id)


async def restore_year(pool: asyncpg.Pool, user_id: int, year_id: int) -> dict:
    """กู้คืนปีที่ถูกลบ — กลับมาเป็น **ปีธรรมดา** (ไม่ใช่ปีปัจจุบัน)

    ต้องกด "ใช้เป็นปีปัจจุบัน" เองอีกครั้ง เพราะระหว่างที่ถูกลบ อาจมีปีอื่นถูกตั้งเป็น
    ปัจจุบันไปแล้ว — การกู้คืนแล้วแอบตั้งเป็นปัจจุบันให้จะชน unique index (ดูข้อ 1 หัวไฟล์)
    ⚠️ แต่ต้องผ่านด่านข้อ 2 เหมือนกันถ้าจะตั้ง current ⇒ ไม่แอบตั้งให้จึงเป็นทางที่ถูกอยู่แล้ว
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            await require_permission_anywhere(conn, user_id, PERMISSION)

            row = await conn.fetchrow(
                """
                SELECT id, year_be FROM academic_years
                WHERE id = $1 AND deleted_at IS NOT NULL
                FOR UPDATE
                """,
                year_id,
            )
            if not row:
                raise NotFoundError("ไม่พบปีการศึกษาที่ถูกลบนี้")

            # ⚠️ กู้คืนปีที่ พ.ศ. ไปชนกับปีที่ถูกสร้างใหม่ระหว่างนั้น = IntegrityError → 500
            #    เช็คเอง **ก่อน** UPDATE เพื่อให้ได้ 400 พร้อมข้อความที่อ่านรู้เรื่อง
            #    (unique index uq_academic_years_year_be กรอง deleted_at IS NULL ⇒ ตอน UPDATE
            #     แถวนี้กลับเข้าไปใน index จึงต้องไม่มีตัวอื่นถือ year_be เดียวกันอยู่)
            dup = await conn.fetchval(
                "SELECT id FROM academic_years WHERE year_be = $1 AND deleted_at IS NULL AND id <> $2",
                row["year_be"], year_id,
            )
            if dup:
                raise ValidationError(
                    f"กู้คืนไม่ได้ — มีปีการศึกษา {row['year_be']} อยู่แล้ว "
                    "(ให้ลบปีที่ซ้ำก่อน หรือแก้ พ.ศ. ของปีนั้น)"
                )

            await conn.execute(
                "UPDATE academic_years SET deleted_at = NULL, updated_at = NOW() WHERE id = $1",
                year_id,
            )

            await AuditLogger("year_service").log(
                conn=conn,
                action="RESTORE_ACADEMIC_YEAR",
                actor_identifier=str(user_id),
                client_source="web",
                user_id=user_id,
                entity_type="academic_year",
                entity_id=year_id,
                old_values={"deleted_at": "NOT NULL"},
                new_values={"deleted_at": None},
            )

        return await _fetch_one(conn, year_id)
