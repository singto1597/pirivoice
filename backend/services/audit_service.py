"""
🛡️ Audit Service — บันทึก + อ่าน audit_logs

- `log_read`: บันทึก action ประเภท READ (ดึงข้อมูล) — "ทุกอย่าง" ตาม requirement
  (ip/user_agent/trace_id ได้จาก request context อัตโนมัติผ่าน AuditLogger)
- `list_audit_logs`: หน้า admin ดูประวัติ (สิทธิ์ VIEW_AUDIT_LOG + scope super/all เท่านั้น)
- `get_options`: ค่าที่มีจริงในบันทึก — เติม dropdown ของตัวกรอง

═══════════════════════════════════════════════════════════════════════════════
🔑 ทำไมหน้าดูใช้ keyset ไม่ใช่ OFFSET
═══════════════════════════════════════════════════════════════════════════════
`audit_logs` เดินโตตลอดเวลา (ทุก login/read/create) ⇒ `OFFSET 40` ที่หน้าถัดไป
**ไม่ใช่แถวเดิม** เพราะมีแถวใหม่แทรกหัวตารางระหว่างที่ผู้ใช้กำลังอ่าน ⇒ เห็นซ้ำ/ข้าม
keyset เทียบ `(created_at, id) < แถวสุดท้ายที่เห็น` จึงไม่สนว่ามีแถวใหม่แทรกแค่ไหน

⚠️ ต้องใช้สองคีย์ ไม่ใช่ `created_at` เดียว: หลายแถวเขียนใน transaction เดียวกันได้
(`CURRENT_TIMESTAMP` = เวลาที่เริ่ม transaction) ⇒ `created_at` อย่างเดียวจะตัดแถว
ที่ชนกันทิ้งเป็นช่วง ๆ · `id` (UUID) เป็นตัวตัดสินลำดับสุดท้ายที่นิ่งแล้ว

index ที่รองรับ: `idx_audit_logs_created_id (created_at DESC, id DESC)`
(migrations/030) — ถ้าไม่มี ตัวกรองจะกลายเป็น seq scan ทั้งตารางทุกหน้า
"""
import base64
import binascii
import json
from datetime import date, datetime
from typing import Optional
from uuid import UUID

import asyncpg

from core.exceptions import ForbiddenError, ValidationError
from core.logger import AuditLogger
from core.rbac import get_access_scope, require_permission_anywhere

DEFAULT_LIMIT = 30
MAX_LIMIT = 100

# ⚠️ dropdown จำกัดที่ 90 วันล่าสุด: ถ้าไม่จำกัด ตารางที่โตทุกวินาทีจะต้อง DISTINCT
#    ทั้งตารางทุกครั้งที่เปิดหน้า (ตัวกรองวันที่ของผู้ใช้ยังเลือกช่วงไหนก็ได้)
OPTIONS_LOOKBACK = "NOW() - INTERVAL '90 days'"


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


# ── ตัวช่วย: สิทธิ์ / cursor / การค้นหา ────────────────────────────────────
async def _require_view(conn: asyncpg.Connection, user_id: int) -> None:
    """ด่านเดียวของทั้งรายการและ options — permission ก่อน แล้วจึงตรวจ scope"""
    await require_permission_anywhere(conn, user_id, "VIEW_AUDIT_LOG")
    scope = await get_access_scope(conn, user_id)
    if scope["scope"] not in ("super", "all"):
        raise ForbiddenError("คุณไม่มีสิทธิ์ดูบันทึกการใช้งาน")


def _encode_cursor(created_at: datetime, row_id: UUID) -> str:
    raw = f"{created_at.isoformat()}|{row_id}"
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    """ถอด cursor — ค่าที่พิมพ์มือ/ตัดขาดต้องได้ 400 ไม่ใช่ 500"""
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
        ts_part, id_part = raw.split("|", 1)
        return datetime.fromisoformat(ts_part), UUID(id_part)
    except (ValueError, binascii.Error, UnicodeDecodeError) as exc:
        raise ValidationError(
            "cursor ไม่ถูกต้อง — ให้ใช้ค่าที่ API ส่งกลับมาเท่านั้น"
        ) from exc


def _escape_like(value: str) -> str:
    """ILIKE ใช้ `%`/`_` เป็นไวลด์การ์ด — ผู้ใช้พิมพ์ `%` ต้องค้นหา `%` จริง ๆ"""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


async def list_audit_logs(
    pool: asyncpg.Pool,
    user_id: int,
    *,
    action: Optional[str] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    status: Optional[str] = None,
    service_name: Optional[str] = None,
    q: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    limit: int = DEFAULT_LIMIT,
    cursor: Optional[str] = None,
) -> dict:
    """
    ดึงประวัติ audit_logs แบบ keyset — เฉพาะ admin/ครูสภา/ประธานสภา
    (VIEW_AUDIT_LOG) และ scope super/all

    คืน `{items, next_cursor, has_more}`
    """
    safe_limit = min(max(int(limit), 1), MAX_LIMIT)

    cursor_ts: Optional[datetime] = None
    cursor_id: Optional[UUID] = None
    if cursor:
        cursor_ts, cursor_id = _decode_cursor(cursor)

    async with pool.acquire() as conn:
        await _require_view(conn, user_id)

        # ⚠️ ทุกคอลัมน์ใน WHERE/ORDER BY ต้อง up alias `a.` เพราะคิวรี JOIN users + rooms
        #    (rooms/users เพิ่มคอลัมน์เมื่อไหร่จะพังทันทีถ้าไม่ qualify)
        where = ["1 = 1"]
        params: list = []

        for column, value in (
            ("a.service_name", service_name),
            ("a.action", action),
            ("a.entity_type", entity_type),
            ("a.entity_id", entity_id),
            ("a.status", status),
        ):
            if value:
                params.append(value)
                where.append(f"{column} = ${len(params)}")

        if q and q.strip():
            params.append(f"%{_escape_like(q.strip())}%")
            n = len(params)
            # ค้นในคอลัมน์ที่ผู้ใช้พิมพ์จับได้ (ไม่ค้น old/new_values — JSON ใหญ่ค้นช้า)
            where.append(
                f"(a.actor_identifier ILIKE ${n} ESCAPE '\\'"
                f" OR a.endpoint_or_command ILIKE ${n} ESCAPE '\\'"
                f" OR a.entity_id ILIKE ${n} ESCAPE '\\'"
                f" OR a.error_detail ILIKE ${n} ESCAPE '\\')"
            )

        # ช่วงวันที่เป็น "วันตามเวลาไทย" ⇒ เทียบกับ date หลังแปลง TZ
        # (ถ้าใช้ UTC แถว 00:00–07:00 ไทยจะตกไปวันก่อนหน้า)
        if date_from:
            params.append(date_from)
            where.append(
                f"(a.created_at AT TIME ZONE 'Asia/Bangkok')::date >= ${len(params)}"
            )
        if date_to:
            params.append(date_to)
            where.append(
                f"(a.created_at AT TIME ZONE 'Asia/Bangkok')::date <= ${len(params)}"
            )

        # keyset: (created_at, id) ของแถวสุดท้ายที่เห็น เป็นขอบบนของหน้าถัดไป
        if cursor_ts is not None and cursor_id is not None:
            params.append(cursor_ts)
            ts_idx = len(params)
            params.append(cursor_id)
            id_idx = len(params)
            where.append(
                f"(a.created_at, a.id) < (${ts_idx}::timestamptz, ${id_idx}::uuid)"
            )

        limit_idx = len(params) + 1
        rows = await conn.fetch(
            f"""
            SELECT
                a.id, a.trace_id, a.user_id, a.room_id,
                r.room_name AS room_name,
                NULLIF(TRIM(u.full_name), '') AS actor_name,
                a.actor_identifier, a.client_source, a.service_name, a.action,
                a.entity_type, a.entity_id, a.status, a.error_detail,
                a.old_values, a.new_values, a.endpoint_or_command,
                a.ip_address, a.user_agent, a.execution_time_ms, a.created_at
            FROM audit_logs a
            LEFT JOIN users u ON u.id = a.user_id
            LEFT JOIN rooms r ON r.id = a.room_id
            WHERE {" AND ".join(where)}
            ORDER BY a.created_at DESC, a.id DESC
            LIMIT ${limit_idx}
            """,
            *params, safe_limit + 1,
        )

        has_more = len(rows) > safe_limit
        page = rows[:safe_limit]
        next_cursor = (
            _encode_cursor(page[-1]["created_at"], page[-1]["id"])
            if has_more and page
            else None
        )

    return {
        "items": [_audit_to_dict(r) for r in page],
        "next_cursor": next_cursor,
        "has_more": has_more,
    }


async def get_options(pool: asyncpg.Pool, user_id: int) -> dict:
    """ค่าที่มีจริงในบันทึก 90 วันล่าสุด — เติม dropdown โดยไม่ต้องเดาจากโค้ด"""
    async with pool.acquire() as conn:
        await _require_view(conn, user_id)

        service_names = await conn.fetch(
            f"""
            SELECT DISTINCT service_name FROM audit_logs
            WHERE created_at >= {OPTIONS_LOOKBACK} AND service_name <> '-'
            ORDER BY service_name
            """
        )
        actions = await conn.fetch(
            f"""
            SELECT DISTINCT action FROM audit_logs
            WHERE created_at >= {OPTIONS_LOOKBACK} AND action <> '-'
            ORDER BY action
            """
        )
        statuses = await conn.fetch(
            f"""
            SELECT DISTINCT status FROM audit_logs
            WHERE created_at >= {OPTIONS_LOOKBACK} AND status <> '-'
            ORDER BY status
            """
        )
        entity_types = await conn.fetch(
            f"""
            SELECT DISTINCT entity_type FROM audit_logs
            WHERE created_at >= {OPTIONS_LOOKBACK} AND entity_type <> '-'
            ORDER BY entity_type
            """
        )

    return {
        "service_names": [r["service_name"] for r in service_names],
        "actions": [r["action"] for r in actions],
        "statuses": [r["status"] for r in statuses],
        "entity_types": [r["entity_type"] for r in entity_types],
    }


def _audit_to_dict(row: asyncpg.Record) -> dict:
    """แปลงแถว audit_logs → dict (parse jsonb ถ้า asyncpg คืน string — บทเรียนเดิม)"""
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
        "actor_name": row["actor_name"],
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
