"""📅 ภาคเรียน (Academic Terms) — จัดการช่วงวันที่ของภาค + "ภาคปัจจุบันคืออะไร"

ทำไมต้องมี: สถิติส่วนตัว (C3) และ Home summary (B1) ต้องตอบคำถาม "ภาคนี้เป็นยังไง"
  ⇒ ต้องรู้ว่าภาคปัจจุบันเริ่ม/จบวันไหน · และต้องดูย้อนหลังได้ว่าภาคก่อนเป็นยังไง
  ⇒ จึงเป็น **ตารางจริงมีประวัติ** ไม่ใช่ key-value ใน `.env`

จุดที่ต้องระวัง (อ่านก่อนแก้):
  1. **มีภาคปัจจุบันได้ตัวเดียว** — บังคับด้วย partial unique index
     `uq_academic_terms_single_current` (ดู migrations/017) ไม่ใช่ด้วยโค้ด
     ⚠️ index เป็น non-deferrable ⇒ ทุกที่ที่ตั้ง `is_current = TRUE` **ต้องล้างตัวเก่าก่อน**
        ใน transaction เดียวกัน (`_clear_current`) ถ้าตั้งก่อนล้าง = UniqueViolationError
  2. **`end_date` รวมวันสุดท้าย (inclusive)** — ตอนกรองวันที่ต้องใช้ `< end_date + 1 วัน`
     ห้ามใช้ `<= end_date` (ดู me_service — และระวังเรื่อง timezone ด้วย)
  3. **soft delete ต้องเคลียร์ `is_current` ด้วย** — ไม่ใช่เพื่อให้ index ผ่าน (index กรอง
     `deleted_at IS NULL` อยู่แล้ว) แต่เพื่อกัน **restore พัง**: ถ้าแถวที่ถูกลบยัง `is_current = TRUE`
     แล้วระหว่างนั้นมีภาคอื่นถูกตั้งเป็น current การกู้คืนจะชน unique index ทันที
     ⇒ ลบ = หลุดจากตำแหน่งปัจจุบัน · กู้คืน = กลับมาเป็นภาคธรรมดา (ต้องกด "ใช้เป็นภาคปัจจุบัน" เอง)
  4. **ไม่มีคอลัมน์ `created_by`/`updated_by` โดยเจตนา** — ต่างจาก announcements
     เพราะตารางนี้ไม่ได้แสดง "ใครตั้ง" ที่ไหนใน UI และ `audit_logs` บันทึกผู้กระทำไว้ครบแล้ว
     (ไม่ต้องเก็บซ้ำสองที่ให้ไม่ตรงกัน)
  5. **ไม่มีภาคปัจจุบันก็เป็นสถานะที่ถูกต้อง** — `get_current_term()` คืน `None`
     ผู้บริโภคต้องตีความเป็น "นับทั้งหมด" ไม่ใช่ error (โรงเรียนยังไม่เคยตั้งภาค)

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

# สิทธิ์ที่ใช้ — มีอยู่แล้วใน config/roles.json (council_president / teacher_council / admin)
# ⇒ **ไม่ต้องมี migration backfill permission** (ต่างจาก D1 ที่จะเพิ่ม MANAGE_EVENTS)
PERMISSION = "MANAGE_SETTINGS"

# คอลัมน์ที่ยอมให้แก้ผ่าน PATCH — allowlist เพราะชื่อคอลัมน์ถูก interpolate ลง SQL
# ⚠️ **ไม่รวม `is_current`** — การเปลี่ยนภาคปัจจุบันต้องผ่าน set_current_term() เท่านั้น
#    เพราะต้องล้างตัวเก่าก่อน (ข้อ 1 ด้านบน) ถ้าปล่อยให้ PATCH มันได้ จะมีสองทางที่ทำแล้วไม่เหมือนกัน
_EDITABLE_COLUMNS = ("name", "start_date", "end_date")

# เงื่อนไขกรองสถานะ — dict นี้คือ **จุดเดียวที่นิยามคำว่าสถานะ**
# ใช้ทั้ง COUNT(*) และคิวรีหลัก ⇒ total กับ items ตรงกันเสมอ
_STATUS_CONDITIONS = {
    "current": "t.deleted_at IS NULL AND t.is_current",
    "active": "t.deleted_at IS NULL",
    "deleted": "t.deleted_at IS NOT NULL",
    "all": "TRUE",
}

# ภาคปัจจุบันขึ้นก่อน แล้วใหม่สุดก่อน · `t.id DESC` รองท้าย (กันหน้าทับกันเมื่อ start_date ซ้ำ)
_ORDER_BY = "ORDER BY t.is_current DESC, t.start_date DESC, t.id DESC"

_SELECT_COLUMNS = """
    t.id, t.name, t.start_date, t.end_date, t.is_current,
    t.created_at, t.updated_at, t.deleted_at
"""


async def _fetch_one(conn: asyncpg.Connection, term_id: int) -> dict:
    row = await conn.fetchrow(
        f"SELECT {_SELECT_COLUMNS} FROM academic_terms t WHERE t.id = $1", term_id
    )
    return dict(row) if row else {}


async def _clear_current(conn: asyncpg.Connection) -> None:
    """ล้างภาคปัจจุบันตัวเก่า — ต้องเรียก **ก่อน** ตั้งตัวใหม่เสมอ (index non-deferrable)"""
    await conn.execute(
        """
        UPDATE academic_terms
        SET is_current = FALSE, updated_at = NOW()
        WHERE is_current AND deleted_at IS NULL
        """
    )


# ============================================================
# 📖 อ่าน "ภาคปัจจุบัน" — C3 (สถิติส่วนตัว) และ B1 (Home) ใช้ตัวนี้
# ============================================================

async def fetch_current_term(conn: asyncpg.Connection) -> Optional[dict]:
    """อ่านภาคปัจจุบันโดยใช้ connection ของ caller (ให้ reuse ได้ในคิวรีชุดเดียว)

    ⚠️ กรอง `deleted_at IS NULL` ด้วย — ภาคที่ถูกลบไม่ใช่ภาคปัจจุบัน
    """
    row = await conn.fetchrow(
        """
        SELECT id, name, start_date, end_date
        FROM academic_terms
        WHERE is_current AND deleted_at IS NULL
        LIMIT 1
        """
    )
    return dict(row) if row else None


async def get_current_term(pool: asyncpg.Pool) -> Optional[dict]:
    """ภาคปัจจุบัน หรือ `None` ถ้ายังไม่มี (สถานะตั้งต้นของระบบ — ไม่ใช่ error)"""
    async with pool.acquire() as conn:
        return await fetch_current_term(conn)


# ============================================================
# 📋 รายการ (หน้า admin)
# ============================================================

async def list_terms(
    pool: asyncpg.Pool,
    user_id: int,
    *,
    status: str = "active",
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """รายการภาคเรียน — envelope {items,total,page,page_size,pages} เหมือน /api/audit-logs"""
    if status not in _STATUS_CONDITIONS:
        raise ValidationError("สถานะที่กรองไม่ถูกต้อง")

    async with pool.acquire() as conn:
        await require_permission_anywhere(conn, user_id, PERMISSION)

        where_sql = _STATUS_CONDITIONS[status]

        # นับ total แยกจากคิวรีหลัก — ห้ามใช้ COUNT(*) OVER() (offset เลยหน้าสุดท้ายแล้วจะได้ 0)
        total = await conn.fetchval(
            f"SELECT COUNT(*) FROM academic_terms t WHERE {where_sql}"
        )

        rows = await conn.fetch(
            f"""
            SELECT {_SELECT_COLUMNS}
            FROM academic_terms t
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


# ============================================================
# ✍️ Mutations
# ============================================================

async def create_term(
    pool: asyncpg.Pool,
    user_id: int,
    *,
    name: str,
    start_date: date,
    end_date: date,
    is_current: bool = False,
) -> dict:
    """สร้างภาคเรียน + audit — ถ้า `is_current` จะปลดภาคปัจจุบันตัวเก่าให้ในทรานแซกชันเดียวกัน

    CHECK `chk_academic_terms_range` กัน end < start ที่ DB อยู่แล้ว แต่ตรวจที่ชั้นนี้ด้วย
    เพื่อให้ได้ 400 พร้อมข้อความไทย แทน 500 จาก IntegrityError
    """
    if end_date < start_date:
        raise ValidationError("วันสิ้นสุดต้องไม่ก่อนวันเริ่มต้น")

    async with pool.acquire() as conn:
        async with conn.transaction():
            await require_permission_anywhere(conn, user_id, PERMISSION)

            if is_current:
                await _clear_current(conn)

            new_id = await conn.fetchval(
                """
                INSERT INTO academic_terms (name, start_date, end_date, is_current)
                VALUES ($1, $2, $3, $4)
                RETURNING id
                """,
                name, start_date, end_date, is_current,
            )

            await AuditLogger("term_service").log(
                conn=conn,
                action="CREATE_ACADEMIC_TERM",
                actor_identifier=str(user_id),
                client_source="web",
                user_id=user_id,
                entity_type="academic_term",
                entity_id=new_id,
                new_values={
                    "name": name,
                    "start_date": str(start_date),
                    "end_date": str(end_date),
                    "is_current": is_current,
                },
            )

        return await _fetch_one(conn, new_id)


async def update_term(
    pool: asyncpg.Pool,
    user_id: int,
    term_id: int,
    changes: dict,
) -> dict:
    """แก้ภาคเรียน (PATCH — เฉพาะฟิลด์ที่ส่งมา) + audit old/new values

    ⚠️ แก้ได้เฉพาะภาคที่ยังไม่ถูกลบ — ตัวที่ถูกลบต้อง "กู้คืน" ก่อน ไม่ให้แก้ประวัติเงียบ ๆ

    ⚠️ **PATCH ที่ส่ง `null` มาตรง ๆ ต้องโดนปฏิเสธที่นี่ — ไม่ใช่ปล่อยผ่าน แล้วไปพังเป็น 500**
       `exclude_unset` ไม่ช่วยเลย: ส่ง `{"name": null}` มา = ฟิลด์นั้นถูก "set" แล้ว
       ⇒ ค่าที่ได้คือ `{"name": None}` ซึ่งผ่าน allowlist ต่อไปได้ ⇒
         · `{"end_date": null}` → `None < date` = `TypeError` → 500
         · `{"name": null}`     → `UPDATE ... SET name = NULL` = `NotNullViolationError` → 500
       ทั้งสามคอลัมน์เป็น `NOT NULL` ⇒ `null` **ไม่มีความหมายที่ใช้ได้** ในที่นี้
       (ต่างจาก `announcement_service` ที่ `link: null` แปลว่า "สั่งล้างลิงก์" จริง ๆ
        เพราะคอลัมน์นั้น nullable — ที่นี่ไม่มีการล้างค่าให้)
       ⇒ **ปฏิเสธด้วย 400 ไม่ใช่เงียบ ๆ ทิ้ง** เพราะถ้าทิ้ง ผู้เรียกจะได้ 200 แล้วเข้าใจว่าบันทึกแล้ว
    """
    nulls = sorted(k for k, v in changes.items() if k in _EDITABLE_COLUMNS and v is None)
    if nulls:
        raise ValidationError(
            f"ห้ามส่งค่า null ในฟิลด์ {', '.join(nulls)} — ถ้าไม่ต้องการแก้ฟิลด์นั้น ให้ไม่ส่งมาที่เลย"
        )

    safe = {k: v for k, v in changes.items() if k in _EDITABLE_COLUMNS}
    if not safe:
        raise ValidationError("ไม่มีข้อมูลที่จะแก้ไข")

    async with pool.acquire() as conn:
        async with conn.transaction():
            await require_permission_anywhere(conn, user_id, PERMISSION)

            before = await conn.fetchrow(
                """
                SELECT name, start_date, end_date
                FROM academic_terms
                WHERE id = $1 AND deleted_at IS NULL
                FOR UPDATE
                """,
                term_id,
            )
            if not before:
                raise NotFoundError("ไม่พบภาคเรียนนี้ (อาจถูกลบไปแล้ว)")

            # PATCH ส่งมาอาจเป็นวันเดียว ⇒ เทียบกับค่าที่เก็บอยู่จริง ไม่ใช่กับ None
            new_start = safe.get("start_date", before["start_date"])
            new_end = safe.get("end_date", before["end_date"])
            if new_end < new_start:
                raise ValidationError("วันสิ้นสุดต้องไม่ก่อนวันเริ่มต้น")

            # dynamic SET: จอง $1 ไว้ให้ WHERE แล้วฟิลด์เริ่มที่ len(params)+1
            params: list = [term_id]
            sets: list = []
            for column, value in safe.items():
                params.append(value)
                sets.append(f"{column} = ${len(params)}")

            # `updated_at = NOW()` ไม่มี param จึงไม่กระทบเลข placeholder
            sql = (
                f"UPDATE academic_terms SET {', '.join(sets)}, updated_at = NOW() "
                "WHERE id = $1"
            )
            assert sql.count("$") == len(params), "placeholder ไม่ตรงกับจำนวน param"

            await conn.execute(sql, *params)

            await AuditLogger("term_service").log(
                conn=conn,
                action="UPDATE_ACADEMIC_TERM",
                actor_identifier=str(user_id),
                client_source="web",
                user_id=user_id,
                entity_type="academic_term",
                entity_id=term_id,
                old_values={
                    k: str(before[k]) if isinstance(before[k], date) else before[k]
                    for k in safe
                },
                new_values={
                    k: str(v) if isinstance(v, date) else v for k, v in safe.items()
                },
            )

        return await _fetch_one(conn, term_id)


async def set_current_term(pool: asyncpg.Pool, user_id: int, term_id: int) -> dict:
    """ตั้งภาคนี้เป็น "ภาคปัจจุบัน" — ปลดตัวเก่าก่อน แล้วตั้งตัวใหม่ (ลำดับสำคัญมาก)

    มี endpoint แยกจาก PATCH โดยเจตนา: การเปลี่ยนภาคปัจจุบันเป็นการกระทำที่มีความหมาย
    ต่างจากการแก้ชื่อ/วันที่ และต้องล้างตัวเก่าเสมอ ⇒ ให้มีทางเดียวที่ทำถูก
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            await require_permission_anywhere(conn, user_id, PERMISSION)

            row = await conn.fetchrow(
                """
                SELECT id, name, is_current FROM academic_terms
                WHERE id = $1 AND deleted_at IS NULL
                FOR UPDATE
                """,
                term_id,
            )
            if not row:
                raise NotFoundError("ไม่พบภาคเรียนนี้ (อาจถูกลบไปแล้ว)")
            if row["is_current"]:
                # กดซ้ำ = ไม่ทำอะไร ไม่ทับ timestamp เดิม (คืนแถวเดิมไปเลย)
                return await _fetch_one(conn, term_id)

            # ⚠️ ล้างก่อนตั้ง — สลับสองบรรทัดนี้ = UniqueViolationError
            await _clear_current(conn)
            await conn.execute(
                "UPDATE academic_terms SET is_current = TRUE, updated_at = NOW() WHERE id = $1",
                term_id,
            )

            await AuditLogger("term_service").log(
                conn=conn,
                action="SET_CURRENT_TERM",
                actor_identifier=str(user_id),
                client_source="web",
                user_id=user_id,
                entity_type="academic_term",
                entity_id=term_id,
                new_values={"name": row["name"], "is_current": True},
            )

        return await _fetch_one(conn, term_id)


async def delete_term(pool: asyncpg.Pool, user_id: int, term_id: int) -> dict:
    """ลบภาคเรียน (soft delete) + audit

    ⚠️ เคลียร์ `is_current` ไปพร้อมกันด้วย — ดูเหตุผลข้อ 3 ใน docstring หัวไฟล์
       (ถ้าไม่เคลียร์ การกู้คืนภายหลังจะชน unique index)
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            await require_permission_anywhere(conn, user_id, PERMISSION)

            row = await conn.fetchrow(
                """
                UPDATE academic_terms
                SET deleted_at = NOW(), is_current = FALSE, updated_at = NOW()
                WHERE id = $1 AND deleted_at IS NULL
                RETURNING id
                """,
                term_id,
            )
            if not row:
                # ไม่พบ หรือ ถูกลบไปแล้ว (กันกดซ้ำ — ไม่ทับ deleted_at เดิมด้วย NOW() ใหม่)
                raise NotFoundError("ไม่พบภาคเรียนนี้ (อาจถูกลบไปแล้ว)")

            await AuditLogger("term_service").log(
                conn=conn,
                action="DELETE_ACADEMIC_TERM",
                actor_identifier=str(user_id),
                client_source="web",
                user_id=user_id,
                entity_type="academic_term",
                entity_id=term_id,
                old_values={"deleted_at": None},
                new_values={"deleted_at": "NOW()"},
            )

        return await _fetch_one(conn, term_id)


async def restore_term(pool: asyncpg.Pool, user_id: int, term_id: int) -> dict:
    """กู้คืนภาคที่ถูกลบ — กลับมาเป็น **ภาคธรรมดา** (ไม่ใช่ภาคปัจจุบัน)

    ต้องกด "ใช้เป็นภาคปัจจุบัน" เองอีกครั้ง เพราะระหว่างที่ถูกลบ อาจมีภาคอื่นถูกตั้งเป็น
    ปัจจุบันไปแล้ว — การกู้คืนแล้วแอบตั้งเป็นปัจจุบันให้จะชน unique index (ดูข้อ 3 หัวไฟล์)
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            await require_permission_anywhere(conn, user_id, PERMISSION)

            row = await conn.fetchrow(
                """
                UPDATE academic_terms
                SET deleted_at = NULL, updated_at = NOW()
                WHERE id = $1 AND deleted_at IS NOT NULL
                RETURNING id
                """,
                term_id,
            )
            if not row:
                raise NotFoundError("ไม่พบภาคเรียนที่ถูกลบนี้")

            await AuditLogger("term_service").log(
                conn=conn,
                action="RESTORE_ACADEMIC_TERM",
                actor_identifier=str(user_id),
                client_source="web",
                user_id=user_id,
                entity_type="academic_term",
                entity_id=term_id,
                old_values={"deleted_at": "NOT NULL"},
                new_values={"deleted_at": None},
            )

        return await _fetch_one(conn, term_id)
