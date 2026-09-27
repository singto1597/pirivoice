"""Announcement Service — จัดการประกาศหน้า Landing Page (CRUD)

กฎที่ยึดตาม docs/rules/backend.md:
  - SQL ทั้งหมดอยู่ในชั้นนี้เท่านั้น ใช้ parameterized query ($1..$n) ห้าม f-string ใส่ค่า
  - ทุก mutation อยู่ใน `async with conn.transaction():` และเขียน audit_logs
    **ใน transaction เดียวกัน** (ไม่ใช่หลัง commit)
  - ลบ = soft delete (`deleted_at = NOW()`) เสมอ
  - เช็คสิทธิ์ด้วย `require_permission_anywhere` แล้วโยน ForbiddenError ให้ router แปลงเป็น 403
    (แบบเดียวกับ audit_service.list_audit_logs)

หมายเหตุการออกแบบ:
  - `created_by` / `updated_by` เป็น INTEGER เปล่า **ไม่มี FK** (บทเรียน skills.md:623)
    ⇒ อ่านชื่อต้อง LEFT JOIN users เอาเอง และต้องเป็น LEFT เท่านั้น เพราะแถวที่ยัง
      ไม่มีผู้ประกาศ (seed เก่า) ต้องยังออกมาในรายการ
"""
import math
from typing import Optional

import asyncpg

from core.exceptions import NotFoundError, ValidationError
from core.logger import AuditLogger
from core.rbac import require_permission_anywhere

# คอลัมน์ที่ยอมให้แก้ผ่าน PATCH — allowlist เพราะชื่อคอลัมน์ถูก interpolate ลง SQL
_EDITABLE_COLUMNS = ("message", "priority", "link")

# เงื่อนไขกรองสถานะในรายการฝั่ง admin
_STATUS_CONDITIONS = {
    "active": "a.deleted_at IS NULL",
    "deleted": "a.deleted_at IS NOT NULL",
    "all": "TRUE",
}

# 🏫 LEFT JOIN users สองครั้ง (ผู้สร้าง/ผู้แก้) — ต้อง LEFT เพราะ created_by เป็น NULL ได้
#    (ประกาศที่ seed ไว้ก่อนมีฟีเจอร์นี้) และผู้ใช้อาจถูกลบไปแล้ว
#    ⚠️ ห้าม JOIN students เพราะ user หนึ่งคนมีได้หลายแถว (หลายห้อง) → รายการจะบานออกเป็นซ้ำ
_SELECT_COLUMNS = """
    a.id, a.message, a.priority, a.link,
    a.created_at, a.updated_at, a.deleted_at,
    a.created_by, a.updated_by,
    cu.full_name AS created_by_name,
    uu.full_name AS updated_by_name
"""

_JOINS = """
    LEFT JOIN users cu ON cu.id = a.created_by
    LEFT JOIN users uu ON uu.id = a.updated_by
"""

# เรียง urgent → high → normal แล้วใหม่สุดก่อน ; `a.id DESC` รองท้ายกันหน้าไม่เสถียร
# เวลาที่ created_at ซ้ำกัน (บทเรียน skills.md: ORDER BY ต้องมี id เสมอ)
_ORDER_BY = """
    ORDER BY
        (CASE a.priority WHEN 'urgent' THEN 0 WHEN 'high' THEN 1 ELSE 2 END),
        a.created_at DESC,
        a.id DESC
"""


async def _fetch_one(conn: asyncpg.Connection, announcement_id: int) -> dict:
    """อ่านประกาศ 1 แถว (พร้อมชื่อผู้ประกาศ)"""
    row = await conn.fetchrow(
        f"SELECT {_SELECT_COLUMNS} FROM announcements a {_JOINS} WHERE a.id = $1",
        announcement_id,
    )
    return dict(row) if row else {}


async def list_announcements(
    pool: asyncpg.Pool,
    user_id: int,
    *,
    status: str = "active",
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """
    รายการประกาศสำหรับหน้า admin (เห็นรายการที่ soft-delete ได้ตาม `status`)

    envelope: {items, total, page, page_size, pages} — pattern เดียวกับ /api/audit-logs
    """
    if status not in _STATUS_CONDITIONS:
        raise ValidationError("สถานะที่กรองไม่ถูกต้อง")

    async with pool.acquire() as conn:
        await require_permission_anywhere(conn, user_id, "MANAGE_ANNOUNCEMENTS")

        where_sql = _STATUS_CONDITIONS[status]

        # ⚠️ นับ total แยกจากคิวรีหลัก — ห้ามใช้ COUNT(*) OVER() เพราะเมื่อ `offset`
        #    เลยหน้าสุดท้ายไปแล้ว แถวที่ return จะว่าง ทำให้อ่าน total ไม่ได้ → ได้ 0 ผิด ๆ
        #    (บทเรียน skills.md: COUNT(*) OVER() กับ LIMIT/OFFSET)
        total = await conn.fetchval(
            f"SELECT COUNT(*) FROM announcements a WHERE {where_sql}"
        )

        rows = await conn.fetch(
            f"""
            SELECT {_SELECT_COLUMNS}
            FROM announcements a
            {_JOINS}
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


async def create_announcement(
    pool: asyncpg.Pool,
    user_id: int,
    *,
    message: str,
    priority: str,
    link: Optional[str],
) -> dict:
    """สร้างประกาศใหม่ + บันทึก audit (ใน transaction เดียวกัน)"""
    async with pool.acquire() as conn:
        async with conn.transaction():
            await require_permission_anywhere(conn, user_id, "MANAGE_ANNOUNCEMENTS")

            new_id = await conn.fetchval(
                """
                INSERT INTO announcements (message, priority, link, created_by, updated_by)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id
                """,
                message, priority, link, user_id, user_id,
            )

            await AuditLogger("announcement_service").log(
                conn=conn,
                action="CREATE_ANNOUNCEMENT",
                actor_identifier=str(user_id),
                client_source="web",
                user_id=user_id,
                entity_type="announcement",
                entity_id=new_id,
                new_values={"message": message, "priority": priority, "link": link},
            )

        # อ่านหลัง commit เพื่อให้ได้ชื่อผู้ประกาศจาก JOIN ครบ
        return await _fetch_one(conn, new_id)


async def update_announcement(
    pool: asyncpg.Pool,
    user_id: int,
    announcement_id: int,
    changes: dict,
) -> dict:
    """แก้ประกาศ (PATCH — เฉพาะฟิลด์ที่ส่งมา) + audit old/new values"""
    # allowlist: กันคีย์แปลกปลอมจาก client หลุดเข้าไปเป็นชื่อคอลัมน์ใน SQL
    safe = {k: v for k, v in changes.items() if k in _EDITABLE_COLUMNS}
    if not safe:
        raise ValidationError("ไม่มีข้อมูลที่จะแก้ไข")

    async with pool.acquire() as conn:
        async with conn.transaction():
            await require_permission_anywhere(conn, user_id, "MANAGE_ANNOUNCEMENTS")

            # FOR UPDATE — ล็อกแถวกัน TOCTOU กับคำสั่งลบ/กู้คืนที่วิ่งมาพร้อมกัน
            before = await conn.fetchrow(
                """
                SELECT message, priority, link
                FROM announcements
                WHERE id = $1 AND deleted_at IS NULL
                FOR UPDATE
                """,
                announcement_id,
            )
            if not before:
                raise NotFoundError("ไม่พบประกาศนี้ (อาจถูกลบไปแล้ว)")

            # dynamic SET: จอง $1 ไว้ให้ WHERE เสมอ แล้วฟิลด์เริ่มที่ len(params)+1
            # (บทเรียน skills.md: asyncpg AmbiguousParameterError/IndeterminateDatatypeError)
            params: list = [announcement_id]
            sets: list = []
            for column, value in safe.items():
                params.append(value)
                sets.append(f"{column} = ${len(params)}")

            params.append(user_id)
            sets.append(f"updated_by = ${len(params)}")

            # `updated_at = NOW()` ไม่มี param จึงไม่กระทบเลข placeholder
            sql = (
                f"UPDATE announcements SET {', '.join(sets)}, updated_at = NOW() "
                "WHERE id = $1"
            )
            assert sql.count("$") == len(params), "placeholder ไม่ตรงกับจำนวน param"

            await conn.execute(sql, *params)

            await AuditLogger("announcement_service").log(
                conn=conn,
                action="UPDATE_ANNOUNCEMENT",
                actor_identifier=str(user_id),
                client_source="web",
                user_id=user_id,
                entity_type="announcement",
                entity_id=announcement_id,
                # เก็บเฉพาะฟิลด์ที่สั่งแก้จริง เพื่อให้อ่าน audit แล้วรู้ว่าอะไรเปลี่ยน
                old_values={k: before[k] for k in safe},
                new_values=safe,
            )

        return await _fetch_one(conn, announcement_id)


async def delete_announcement(
    pool: asyncpg.Pool, user_id: int, announcement_id: int
) -> dict:
    """ลบประกาศ (soft delete) + audit — คืนแถวที่อัปเดตแล้ว (มี deleted_at ติดมาด้วย)"""
    async with pool.acquire() as conn:
        async with conn.transaction():
            await require_permission_anywhere(conn, user_id, "MANAGE_ANNOUNCEMENTS")

            row = await conn.fetchrow(
                """
                UPDATE announcements
                SET deleted_at = NOW(), updated_at = NOW(), updated_by = $2
                WHERE id = $1 AND deleted_at IS NULL
                RETURNING id
                """,
                announcement_id, user_id,
            )
            if not row:
                # ไม่พบ หรือ ถูกลบไปแล้ว (กันกดลบซ้ำ — ไม่ทับ deleted_at เดิมด้วย NOW() ใหม่)
                raise NotFoundError("ไม่พบประกาศนี้ (อาจถูกลบไปแล้ว)")

            await AuditLogger("announcement_service").log(
                conn=conn,
                action="DELETE_ANNOUNCEMENT",
                actor_identifier=str(user_id),
                client_source="web",
                user_id=user_id,
                entity_type="announcement",
                entity_id=announcement_id,
                old_values={"deleted_at": None},
                new_values={"deleted_at": "NOW()"},
            )

        return await _fetch_one(conn, announcement_id)


async def restore_announcement(
    pool: asyncpg.Pool, user_id: int, announcement_id: int
) -> dict:
    """กู้คืนประกาศที่ถูกลบ (soft delete) + audit"""
    async with pool.acquire() as conn:
        async with conn.transaction():
            await require_permission_anywhere(conn, user_id, "MANAGE_ANNOUNCEMENTS")

            row = await conn.fetchrow(
                """
                UPDATE announcements
                SET deleted_at = NULL, updated_at = NOW(), updated_by = $2
                WHERE id = $1 AND deleted_at IS NOT NULL
                RETURNING id
                """,
                announcement_id, user_id,
            )
            if not row:
                raise NotFoundError("ไม่พบประกาศที่ถูกลบนี้")

            await AuditLogger("announcement_service").log(
                conn=conn,
                action="RESTORE_ANNOUNCEMENT",
                actor_identifier=str(user_id),
                client_source="web",
                user_id=user_id,
                entity_type="announcement",
                entity_id=announcement_id,
                old_values={"deleted_at": "NOT NULL"},
                new_values={"deleted_at": None},
            )

        return await _fetch_one(conn, announcement_id)
