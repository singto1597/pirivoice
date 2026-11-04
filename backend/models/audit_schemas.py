from typing import Any, List, Optional
from pydantic import BaseModel
from datetime import datetime


class AuditLogOut(BaseModel):
    """หนึ่งแถวใน audit_logs (response ของ GET /api/audit-logs)"""
    id: str
    trace_id: Optional[str] = None
    user_id: Optional[int] = None
    # 🏫 room_id = -1 เมื่อไม่ระบุห้อง ; room_name = None เมื่อไม่พบห้องนั้น (soft delete ได้)
    room_id: Optional[int] = None
    room_name: Optional[str] = None
    actor_identifier: str
    # ชื่อจากตาราง users (null ถ้าผู้ใช้ถูกลบ/ไม่มีแถว) — ใช้เป็นป้ายหลักในรายการ
    actor_name: Optional[str] = None
    client_source: str
    service_name: str
    action: str
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    status: str = "success"
    error_detail: Optional[str] = None
    # ⚠️ jsonb คืนได้ทั้ง object และ array ⇒ `Any` ไม่ใช่ `dict`
    #    (การเดาเป็น dict แล้วเจอ array จะทำให้ response validation ล้มทั้งหน้า)
    old_values: Optional[Any] = None
    new_values: Optional[Any] = None
    endpoint_or_command: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    execution_time_ms: Optional[int] = None
    created_at: datetime


class AuditLogPage(BaseModel):
    """หน้าประวัติ audit — แบบ keyset (ไม่มี total/offset)

    ⚠️ `audit_logs` มีแถวใหม่แทรกหัวตลอดเวลา ⇒ `OFFSET` ทำให้หน้าถัดไปเห็นซ้ำ/ข้าม
    ⇒ ส่ง `next_cursor` กลับมาเป็น `cursor` ของคำขอถัดไปเท่านั้น ห้ามคำนวณเอง
    """
    items: List[AuditLogOut]
    # null = หมดแล้ว
    next_cursor: Optional[str] = None
    has_more: bool = False


class AuditLogOptions(BaseModel):
    """ค่าที่มีจริงในบันทึก — เติม dropdown ของตัวกรอง (ไม่ต้องเดาจากโค้ด)"""
    service_names: List[str]
    actions: List[str]
    statuses: List[str]
    entity_types: List[str]
