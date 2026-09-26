"""
🛡️ Audit Service — บันทึก + อ่าน audit_logs

- `log_read`: บันทึก action ประเภท READ (ดึงข้อมูล) — "ทุกอย่าง" ตาม requirement
  (ip/user_agent/trace_id ได้จาก request context อัตโนมัติผ่าน AuditLogger)
- `list_audit_logs`: หน้า admin ดูประวัติ (สิทธิ์ VIEW_AUDIT_LOG + scope super/all เท่านั้น)
"""
import asyncpg
from typing import Optional
from datetime import date

from core.logger import AuditLogger
from core.rbac import get_access_scope, require_permission_anywhere
from core.exceptions import ForbiddenError


async def log_read(
    pool: asyncpg.Pool,
    user_id: Optional[int],
    action: str,
    entity_type: str,
    entity_id: Optional[int] = None,
    endpoint: Optional[str] = None,
    room_id: Optional[int] = None,
) -> None:
    """
    บันทึก action ประเภท READ (ดึงข้อมูล) — ใช้ดูว่า user เข้าถึงข้อมูลอะไรบ่อยแค่ไหน
    best-effort: ถ้าบันทึกไม่ได้ อย่าทำให้ request หลักพัง (try/except เงียบ)
    """
    try:
        async with pool.acquire() as conn:
            await AuditLogger("read").log(
                conn=conn, action=action,
                actor_identifier=str(user_id) if user_id else "system",
                client_source="web",
                user_id=user_id,
                entity_type=entity_type,
                entity_id=entity_id,
                room_id=room_id,
                endpoint_or_command=endpoint,
            )
    except Exception:
        pass


async def list_audit_logs(
    pool: asyncpg.Pool,
    user_id: int,
    *,
    action: Optional[str] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    status: Optional[str] = None,
    q: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    limit: int = 20,
    offset: int = 0,
) -> dict:
    """
    ดึงประวัติ audit_logs (แบบแบ่งหน้า) — เฉพาะ admin/ครูสภา/ประธานสภา (VIEW_AUDIT_LOG + scope all)
    envelope: {items, total, page, page_size, pages} (pattern เดียวกับ /issues)
    """
    async with pool.acquire() as conn:
        await require_permission_anywhere(conn, user_id, "VIEW_AUDIT_LOG")
        scope = await get_access_scope(conn, user_id)
        if scope["scope"] not in ("super", "all"):
            raise ForbiddenError("คุณไม่มีสิทธิ์ดูบันทึกการใช้งาน")

        # ⚠️ ทุกคอลัมน์ใน WHERE/ORDER BY ต้อง up alias `a.` เพราะคิวรีหลัก JOIN rooms เข้ามา
        #    (ตอนนี้ยังไม่มีชื่อคอลัมน์ชนกัน แต่ rooms เพิ่มคอลัมน์เมื่อไหร่จะพังทันทีถ้าไม่ qualify)
        where = ["1 = 1"]
        params: list = []
        if action:
            params.append(action)
            where.append(f"a.action = ${len(params)}")
        if entity_type:
            params.append(entity_type)
            where.append(f"a.entity_type = ${len(params)}")
        if entity_id:
            params.append(entity_id)
            where.append(f"a.entity_id = ${len(params)}")
        if status:
            params.append(status)
            where.append(f"a.status = ${len(params)}")
        if q:
            params.append(f"%{q}%")
            where.append(
                f"(a.actor_identifier ILIKE ${len(params)} OR COALESCE(a.error_detail,'') ILIKE ${len(params)})"
            )
        if date_from:
            params.append(date_from)
            where.append(f"(a.created_at AT TIME ZONE 'Asia/Bangkok')::date >= ${len(params)}")
        if date_to:
            params.append(date_to)
            where.append(f"(a.created_at AT TIME ZONE 'Asia/Bangkok')::date <= ${len(params)}")

        where_sql = " AND ".join(where)
        filter_params = list(params)  # snapshot ก่อน append limit/offset (ใช้ตอน fallback total)

        # 🏫 LEFT JOIN rooms เพื่อโชว์ชื่อห้อง (audit_logs เก็บ room_id เป็นเลขล้วน ไม่มี FK)
        #    ⚠️ ไม่กรอง r.deleted_at — ห้องที่ถูกลบไปแล้วต้องยังอ่านชื่อได้ ประวัติต้องตรงกับ
        #       ความจริง ณ ตอนเกิดเหตุ ไม่ใช่สถานะปัจจุบันของห้อง
        #    LEFT JOIN (ไม่ใช่ JOIN) เพราะแถวที่ room_id = -1 (ไม่ระบุห้อง) ต้องยังออกมา
        rows = await conn.fetch(
            f"""
            SELECT a.*, r.room_name AS room_name, COUNT(*) OVER() AS total_count
            FROM audit_logs a
            LEFT JOIN rooms r ON r.id = a.room_id
            WHERE {where_sql}
            ORDER BY a.created_at DESC
            LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}
            """,
            *params, limit, offset
        )

        # total: COUNT(*) OVER() อ่านจากแถวแรก — ถ้าหน้า offset เลย (rows ว่าง) ต้องนับแยก
        # (บทเรียน: "List แบบแบ่งหน้า — COUNT(*) OVER() อ่าน total จากแถวที่ return")
        if rows:
            total = rows[0]["total_count"]
        else:
            total = None
        if total is None:
            total = await conn.fetchval(
                f"SELECT COUNT(*) FROM audit_logs a WHERE {where_sql}",
                *filter_params
            ) or 0

        items = [_audit_to_dict(r) for r in rows]

    return {
        "items": items,
        "total": total,
        "page": offset // limit + 1,
        "page_size": limit,
        "pages": (total + limit - 1) // limit,
    }


def _audit_to_dict(row: asyncpg.Record) -> dict:
    """แปลงแถว audit_logs → dict (parse jsonb ถ้า asyncpg คืน string — บทเรียนเดิม)"""
    import json
    old = row["old_values"]
    new = row["new_values"]
    if isinstance(old, str):
        try:
            old = json.loads(old)
        except json.JSONDecodeError:
            old = None
    if isinstance(new, str):
        try:
            new = json.loads(new)
        except json.JSONDecodeError:
            new = None
    return {
        "id": str(row["id"]),
        "trace_id": row["trace_id"],
        "user_id": row["user_id"],
        # 🏫 room_id = -1 คือ "ไม่ระบุห้อง" ; room_name = None เมื่อไม่มีห้องนั้นจริง (LEFT JOIN)
        "room_id": row["room_id"],
        "room_name": row["room_name"],
        "actor_identifier": row["actor_identifier"],
        "client_source": row["client_source"],
        "service_name": row["service_name"],
        "action": row["action"],
        "entity_type": row["entity_type"],
        "entity_id": row["entity_id"],
        "status": row["status"],
        "error_detail": row["error_detail"],
        "old_values": old,
        "new_values": new,
        "endpoint_or_command": row["endpoint_or_command"],
        "ip_address": row["ip_address"],
        "user_agent": row["user_agent"],
        "execution_time_ms": row["execution_time_ms"],
        "created_at": row["created_at"],
    }
