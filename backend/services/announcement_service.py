"""Announcement Service — จัดการประกาศหน้า Landing Page (CRUD + ปลดระวาง)

3 สถานะของประกาศ (ดู `_STATUS_CONDITIONS` — dict นั้นคือจุดเดียวที่นิยามคำว่าสถานะ):

    | สถานะ         | เงื่อนไข                                      | Landing/Home | แท็บ        |
    |---------------|-----------------------------------------------|--------------|-------------|
    | ใช้งานอยู่     | `retired_at IS NULL AND deleted_at IS NULL`   | แสดง         | active      |
    | ปลดระวางแล้ว   | `retired_at IS NOT NULL AND deleted_at IS NULL` | ไม่แสดง    | retired     |
    | ถูกลบ         | `deleted_at IS NOT NULL`                      | ไม่แสดง      | deleted     |

  ⭐ `retired_at` กับ `deleted_at` เป็น **อิสระต่อกัน** ⇒ "ปลดระวางแล้วเผลอลบ → กู้คืน"
     กลับมาเป็น *ปลดระวางแล้ว* ตามเดิม ไม่ใช่กลับไปโชว์บนหน้าเว็บ
     (`retire`/`unretire` ไม่แตะ `deleted_at` และ `delete`/`restore` ไม่แตะ `retired_at`)

กฎที่ยึดตาม docs/rules/backend.md:
  - SQL ทั้งหมดอยู่ในชั้นนี้เท่านั้น ใช้ parameterized query ($1..$n) ห้าม f-string ใส่ค่า
  - ทุก mutation อยู่ใน `async with conn.transaction():` และเขียน audit_logs
    **ใน transaction เดียวกัน** (ไม่ใช่หลัง commit)
  - ลบ = soft delete (`deleted_at = NOW()`) เสมอ
  - เช็คสิทธิ์ด้วย `require_permission_anywhere` แล้วโยน ForbiddenError ให้ router แปลงเป็น 403
    (แบบเดียวกับ audit_service.list_audit_logs)
  - การเปลี่ยนสถานะที่ผิดกติกาบังคับด้วยเงื่อนไขใน `WHERE` (ไม่ใช่ if ใน Python)
    ⇒ กดซ้ำ/กดผิดลำดับได้ 404 โดยไม่ทับ timestamp เดิม

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
from services import notification_service

# คอลัมน์ที่ยอมให้แก้ผ่าน PATCH — allowlist เพราะชื่อคอลัมน์ถูก interpolate ลง SQL
_EDITABLE_COLUMNS = ("message", "priority", "link")

# เงื่อนไขกรองสถานะในรายการฝั่ง admin
# ⭐ **dict นี้คือจุดเดียวที่นิยามคำว่าสถานะ** — ถูกใช้ทั้ง COUNT(*) และคิวรีหลัก
#    ⇒ total กับ items ตรงกันเสมอโดยไม่ต้องแก้อะไรเพิ่ม
# ⚠️ 3 สถานะ: ใช้งานอยู่ / ปลดระวางแล้ว / ถูกลบ — `retired_at` กับ `deleted_at` เป็นอิสระ
#    ต่อกัน ⇒ แถวที่ "ปลดระวาง + ถูกลบ" พร้อมกันจะอยู่แท็บ `deleted` ที่เดียว
#    (เพราะ `retired` กรอง `deleted_at IS NULL` ด้วย) ⇒ ไม่มีแถวโผล่สองแท็บ
_STATUS_CONDITIONS = {
    "active": "a.deleted_at IS NULL AND a.retired_at IS NULL",
    "retired": "a.retired_at IS NOT NULL AND a.deleted_at IS NULL",
    "deleted": "a.deleted_at IS NOT NULL",
    "all": "TRUE",
}

# 🏫 LEFT JOIN users สองครั้ง (ผู้สร้าง/ผู้แก้) — ต้อง LEFT เพราะ created_by เป็น NULL ได้
#    (ประกาศที่ seed ไว้ก่อนมีฟีเจอร์นี้) และผู้ใช้อาจถูกลบไปแล้ว
#    ⚠️ ห้าม JOIN students เพราะ user หนึ่งคนมีได้หลายแถว (หลายห้อง) → รายการจะบานออกเป็นซ้ำ
_SELECT_COLUMNS = """
    a.id, a.message, a.priority, a.link,
    a.created_at, a.updated_at, a.deleted_at, a.retired_at,
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


async def _fanout_if_urgent(
    conn,
    *,
    announcement_id: int,
    message: str,
    priority: str,
    actor_id: int,
) -> None:
    """E2: ประกาศ `urgent` → แจ้งเตือน **ทุก active student** ทันที (in-app + push)

    ⚠️ **เฉพาะ `urgent` เท่านั้น** — `normal`/`high` ไม่แจ้งใคร (ประกาศทั่วไปขึ้นบน Home
       อยู่แล้ว ไม่ต้องรบกวนมือถือทั้งโรงเรียน) · `notify_fanout` ยิง ~800–1,000 แถวต่อครั้ง
       ⇒ **ห้ามเรียกโดยไม่ตั้งใจ** — การพิมพ์ผิดเป็น `urgent` คือ push ทั้งโรงเรียนที่เรียกคืนไม่ได้

    ⚠️ **`group_type='announcement'` ไม่อยู่ใน `PREFERENCE_GROUPS`** ⇒ ผู้ใช้ปิดกลุ่มนี้ไม่ได้
       และไม่มีทางมีแถว preference ของกลุ่มนี้ → `NOT EXISTS` ใน `notify_fanout` เป็น no-op เอง
       (ตั้งใจ: ประกาศฉุกเฉินที่ปิดได้ = ล้มเหลวในหน้าที่ของมัน)
    ⚠️ **`bypass_quiet_hours=True`** — ทะลุ A8 · ด่านจริงอ่านธงนี้ตอน *ส่ง* ใน
       `push_service.process_pending` ⇒ ค่าในแถวคือสัญญาระหว่างสองงานนี้

    ⚠️ `actor_name` ไม่ได้ส่ง (None) — ประกาศฉุกเฉินเนื้อความสำคัญกว่าชื่อผู้ส่ง และการดึงชื่อ
       ต้องใช้ `_user_display_name` (private ของ notification_service) หรือคิวรีซ้ำที่ไม่คุ้มกัน
    ⚠️ `body=message` เต็มความยาว (สูงสุด 1,000 ตัวอักษรตาม schema) — คิดขนาด payload แล้ว
       อยู่ใต้เพดาน 4,096 byte ของ Web Push (ไทย 3 byte/ตัว ⇒ ~3.3 KB) จึงไม่ตัดทิ้ง
    """
    if priority != "urgent":
        return
    await notification_service.notify_fanout(
        conn,
        group_type="announcement",
        type="announcement_urgent",
        title="📢 ประกาศฉุกเฉิน",
        body=message,
        entity_type="announcement",
        entity_id=announcement_id,
        actor_id=actor_id,
        bypass_quiet_hours=True,
    )


async def create_announcement(
    pool: asyncpg.Pool,
    user_id: int,
    *,
    message: str,
    priority: str,
    link: Optional[str],
) -> dict:
    """สร้างประกาศใหม่ + บันทึก audit + **ยิง push ถ้าเป็นประกาศฉุกเฉิน** (transaction เดียวกัน)

    ⭐ E2 — `priority='urgent'` จะ `notify_fanout` ไปทุก active student **ทันที** ไม่ใช่แค่
       insert แถวรอ badge · `bypass_quiet_hours=True` เพราะนี่เป็นเคสเดียวที่ควรทะลุ A8
       (น้ำท่วม/ไฟดับ/งดเรียนกะทันหัน — ประกาศที่ถูก quiet hours กลั้น = ประกาศที่ล้มเหลว)

    ⚠️ **hook อยู่ *ใน* transaction เดียวกัน ไม่ใช่หลัง commit** — ถ้า insert notification ล้ม
       ประกาศก็ต้องไม่ถูกสร้างด้วย (atomicity) · และ `notify_fanout` รับ `conn` จาก caller
       ตามสัญญาของ `notification_service` (มันไม่เปิด transaction เอง)

    ⚠️ `actor_id=user_id` ⇒ ผู้ประกาศไม่ได้รับ push ของตัวเอง (`notify_fanout` กรองออกให้)
       แต่ **แถว in-app ของตัวเองก็ไม่เกิดด้วย** — ยอมรับได้: เขารู้อยู่แล้วว่าเพิ่งประกาศอะไร
    """
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

            await _fanout_if_urgent(
                conn, announcement_id=new_id, message=message,
                priority=priority, actor_id=user_id,
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

            # FOR UPDATE — ล็อกแถวกัน TOCTOU กับคำสั่งลบ/กู้คืน/ปลดระวางที่วิ่งมาพร้อมกัน
            # ⚠️ แก้ได้เฉพาะประกาศที่ *ใช้งานอยู่* — ตัวที่ปลดระวางต้อง "นำกลับมาใช้" ก่อน
            #    (ประกาศที่ปลดระวางคือประวัติ ไม่ควรถูกแก้เงียบ ๆ)
            before = await conn.fetchrow(
                """
                SELECT message, priority, link
                FROM announcements
                WHERE id = $1 AND deleted_at IS NULL AND retired_at IS NULL
                FOR UPDATE
                """,
                announcement_id,
            )
            if not before:
                raise NotFoundError(
                    "ไม่พบประกาศนี้ (อาจถูกลบหรือถูกปลดระวางไปแล้ว)"
                )

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


async def retire_announcement(
    pool: asyncpg.Pool, user_id: int, announcement_id: int
) -> dict:
    """
    ปลดระวางประกาศ — เอาออกจากหน้า Landing/Home แต่ **เก็บไว้เป็นประวัติ**
    ต่างจากการลบ: ตั้งใจเอาออกเพราะหมดอายุ/ใช้การไม่ได้แล้ว ไม่ใช่เพราะผิดพลาด

    ⚠️ ตั้ง `retired_at` **ไม่แตะ `deleted_at`** และต้องเป็นประกาศที่ยังใช้งานอยู่เท่านั้น
       ⇒ แถวที่ถูกลบไปแล้วปลดระวางไม่ได้ (404) และกดซ้ำก็ไม่ทับ timestamp เดิม
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            await require_permission_anywhere(conn, user_id, "MANAGE_ANNOUNCEMENTS")

            row = await conn.fetchrow(
                """
                UPDATE announcements
                SET retired_at = NOW(), updated_at = NOW(), updated_by = $2
                WHERE id = $1 AND deleted_at IS NULL AND retired_at IS NULL
                RETURNING id
                """,
                announcement_id, user_id,
            )
            if not row:
                # ไม่พบ / ถูกลบไปแล้ว / ถูกปลดระวางไปแล้ว — ทั้งสามกรณีไม่ควรทับค่าที่มีอยู่
                raise NotFoundError(
                    "ไม่พบประกาศนี้ที่ยังใช้งานอยู่ (อาจถูกลบหรือถูกปลดระวางไปแล้ว)"
                )

            await AuditLogger("announcement_service").log(
                conn=conn,
                action="RETIRE_ANNOUNCEMENT",
                actor_identifier=str(user_id),
                client_source="web",
                user_id=user_id,
                entity_type="announcement",
                entity_id=announcement_id,
                old_values={"retired_at": None},
                new_values={"retired_at": "NOW()"},
            )

        return await _fetch_one(conn, announcement_id)


async def unretire_announcement(
    pool: asyncpg.Pool, user_id: int, announcement_id: int
) -> dict:
    """
    นำประกาศที่ปลดระวางกลับมาใช้ — ล้าง `retired_at` ให้กลับไปแสดงบน Landing/Home

    ⚠️ ต้องเป็นแถวที่ `deleted_at IS NULL` ⇒ ตัวที่ "ปลดระวาง + ถูกลบ" ต้องกู้คืนก่อน
       (กู้คืนแล้วมันจะกลับมาเป็น "ปลดระวางแล้ว" ไม่ใช่กลับไปโชว์ทันที)
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            await require_permission_anywhere(conn, user_id, "MANAGE_ANNOUNCEMENTS")

            row = await conn.fetchrow(
                """
                UPDATE announcements
                SET retired_at = NULL, updated_at = NOW(), updated_by = $2
                WHERE id = $1 AND retired_at IS NOT NULL AND deleted_at IS NULL
                RETURNING id
                """,
                announcement_id, user_id,
            )
            if not row:
                raise NotFoundError("ไม่พบประกาศที่ถูกปลดระวางนี้")

            await AuditLogger("announcement_service").log(
                conn=conn,
                action="UNRETIRE_ANNOUNCEMENT",
                actor_identifier=str(user_id),
                client_source="web",
                user_id=user_id,
                entity_type="announcement",
                entity_id=announcement_id,
                old_values={"retired_at": "NOT NULL"},
                new_values={"retired_at": None},
            )

        return await _fetch_one(conn, announcement_id)
