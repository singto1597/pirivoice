import json
import time
import uuid
import asyncpg
from typing import Optional, Dict

from core.request_context import get_audit_context

# 🧩 ค่าที่ใช้แทน "ไม่มีข้อมูล" — audit_logs ห้ามเว้นว่าง (NULL) เด็ดขาด
#    หลักการ: ถ้าหาค่าจริงไม่ได้ ให้เก็บค่าที่ "อ่านออก" ว่าไม่รู้ ไม่ใช่ปล่อยว่าง
#    (DB บังคับ NOT NULL ทุกคอลัมน์ไว้แล้วที่ core/init_db.py + migration 013)
UNKNOWN = "-"        # คอลัมน์ข้อความ: ไม่ทราบค่า/ไม่มีค่า ณ ขณะบันทึก
EMPTY_JSON = {}      # คอลัมน์ JSONB: ไม่มีข้อมูล old/new (เช่น action ประเภทอ่าน)
UNRESOLVED_ID = -1   # room_id / user_id: ไม่ระบุห้อง/ไม่รู้จักตัวตน (ไม่มี FK ในตารางนี้แล้ว — ดู migration 013)


def _clean_ip(value: Optional[str]) -> Optional[str]:
    """ทำ IP ให้เป็นรูปเดียว — ตัด port, ตัด prefix IPv6-mapped (::ffff:10.0.0.1 → 10.0.0.1)"""
    if not value:
        return None
    ip = value.strip()
    if not ip:
        return None
    if ip.startswith("[") and "]" in ip:          # [2001:db8::1]:443
        ip = ip[1:ip.index("]")]
    elif ip.count(":") == 1 and "." in ip:        # 10.0.0.1:51234 (IPv4 + port)
        ip = ip.split(":")[0]
    if ip.lower().startswith("::ffff:"):
        ip = ip[7:]
    # คอลัมน์เป็น VARCHAR(45) — ตัดกันพลาด (IP ผิดรูปแบบ/มี garbage ต่อท้าย)
    return ip[:45] or None


def _text(value, default: str = UNKNOWN) -> str:
    """คืนค่า string ที่ไม่ว่าง — ค่าว่าง/None → ค่า default"""
    if value is None:
        return default
    value = str(value).strip()
    return value or default


class AuditLogger:
    """บันทึก Audit Log ทุกการ CREATE/UPDATE/DELETE ภายใน Transaction เดียวกับข้อมูลหลัก.

    📌 สัญญาของคลาสนี้: "ทุกคอลัมน์ถูกบันทึกเสมอ" (ไม่เว้นว่าง)
    ค่าที่ caller ไม่ส่งมา จะถูกเติมจาก (1) request context (2) ข้อมูลที่หาได้จาก DB
    (3) ค่า sentinel ที่อ่านออก — ดู fallback ของแต่ละคอลัมน์ใน `log()`
    """

    def __init__(self, service_name: str):
        self.service_name = service_name

    async def _resolve_room_id(self, conn: asyncpg.Connection, user_id: int) -> Optional[int]:
        """หา room_id ของผู้กระทำ (นักเรียน/ครู → ห้องที่สังกัด ; หัวหน้าห้อง → ห้องที่เป็นเจ้าของ)"""
        return await conn.fetchval(
            """
            SELECT room_id FROM (
                SELECT s.room_id AS room_id, 1 AS prio
                FROM students s
                WHERE s.user_id = $1 AND s.deleted_at IS NULL AND s.room_id IS NOT NULL
                UNION ALL
                SELECT r.id AS room_id, 2 AS prio
                FROM rooms r
                WHERE r.owner_id = $1 AND r.deleted_at IS NULL
            ) t
            ORDER BY prio
            LIMIT 1
            """,
            user_id
        )

    async def log(
        self,
        conn: asyncpg.Connection,
        action: str,
        actor_identifier: str,
        client_source: str,
        room_id: Optional[int] = None,
        user_id: Optional[int] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        status: str = 'success',
        error_detail: Optional[str] = None,
        old_values: Optional[Dict] = None,
        new_values: Optional[Dict] = None,
        endpoint_or_command: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        execution_time_ms: Optional[int] = None,
        trace_id: Optional[str] = None
    ):
        ctx = get_audit_context()

        # --- 1) ข้อมูล network/request: param → request context → sentinel -------------
        # 📡 context ถูกตั้งโดย middleware (HTTP) หรือ audit_scope() (worker/script)
        current_ip = _clean_ip(ip_address) or _clean_ip(ctx.get("ip_address")) or UNKNOWN
        current_ua = _text(user_agent) if user_agent else _text(ctx.get("user_agent"))
        current_trace_id = _text(trace_id) if trace_id else _text(ctx.get("trace_id")) or str(uuid.uuid4())

        # endpoint_or_command: path ของ request ปัจจุบัน → param → "<client_source>:<action>"
        # ⚠️ ให้ context มาก่อน param เพราะ path จริงจาก middleware ถูกต้องกว่าและสม่ำเสมอกว่า
        #    (ค่าที่ caller พิมพ์ไว้เองมักเป็นชื่อย่อ เช่น "POST /auth/login" ที่ขาด prefix /api)
        #    งานที่ไม่ผ่าน HTTP จะได้ "<client_source>:<action>" — ไม่ปล่อยว่าง
        current_endpoint = (
            _text(ctx.get("endpoint")) if ctx.get("endpoint")
            else _text(endpoint_or_command) if endpoint_or_command
            else f"{_text(client_source, 'unknown')}:{_text(action)}"
        )

        # --- 2) execution_time_ms: param → เวลาที่ผ่านไปตั้งแต่เริ่มงาน → 0 ------------
        # ⏱️ วัดจาก started_at ใน context ( middleware/audit_scope ตั้งไว้ )
        #    request เดียวที่เขียนหลาย log → ค่าไล่ขึ้นตามลำดับ ; แถวสุดท้าย = เวลารวมของ request
        #    0 = วัดไม่ได้ เพราะไม่มี context (ไม่ปล่อยว่าง — ตัวเลข 0 สื่อว่า "ไม่ได้วัด")
        current_exec_ms = execution_time_ms
        if current_exec_ms is None:
            started_at = ctx.get("started_at")
            current_exec_ms = max(0, int((time.monotonic() - started_at) * 1000)) if started_at else 0
        current_exec_ms = max(0, int(current_exec_ms))

        # --- 3) user_id: param → -1 (ไม่รู้จักตัวตน เช่น login ที่หาชื่อไม่เจอ) ---------
        current_user_id = UNRESOLVED_ID if user_id is None else int(user_id)

        # --- 4) room_id: param → ห้องของผู้กระทำ (cache ต่อ request) → -1 --------------
        current_room_id = int(room_id) if room_id is not None else None
        if current_room_id is None and current_user_id != UNRESOLVED_ID:
            # cache ไว้ใน context (1 request = query ห้องครั้งเดียว ไม่ว่าจะ log กี่แถว)
            # ⚠️ cache เฉพาะเมื่อมี context จริง — ห้ามเขียนทับ default {} ของ ContextVar
            cache = ctx.get("room_cache") if ctx else None
            if cache is None:
                cache = {}
                if ctx:
                    ctx["room_cache"] = cache
            if current_user_id not in cache:
                try:
                    cache[current_user_id] = await self._resolve_room_id(conn, current_user_id)
                except Exception:
                    cache[current_user_id] = None
            current_room_id = cache[current_user_id]
        if current_room_id is None:
            current_room_id = UNRESOLVED_ID

        await conn.execute("""
            INSERT INTO audit_logs (
                trace_id, room_id, user_id, actor_identifier, client_source,
                service_name, action, entity_type, entity_id, status,
                error_detail, old_values, new_values, endpoint_or_command,
                ip_address, user_agent, execution_time_ms
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12::jsonb, $13::jsonb, $14, $15, $16, $17)
        """,
            current_trace_id, current_room_id, current_user_id,
            _text(actor_identifier), _text(client_source),
            _text(self.service_name), _text(action), _text(entity_type),
            # entity_id: ค่าว่าง → "-" (การอ่านระดับ collection/ล็อกอิน ไม่มีเอนทิตีจริง)
            _text(entity_id),
            _text(status, 'success'), _text(error_detail),
            # JSONB: ไม่มีข้อมูล → {} (ไม่ใช่ NULL) — {} = "ไม่มีการเปลี่ยนแปลงข้อมูล"
            json.dumps(old_values, default=str) if old_values else json.dumps(EMPTY_JSON),
            json.dumps(new_values, default=str) if new_values else json.dumps(EMPTY_JSON),
            current_endpoint, current_ip, current_ua, current_exec_ms
        )
