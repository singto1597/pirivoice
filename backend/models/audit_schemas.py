from typing import List, Optional
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
    client_source: str
    service_name: str
    action: str
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    status: str = "success"
    error_detail: Optional[str] = None
    old_values: Optional[dict] = None
    new_values: Optional[dict] = None
    endpoint_or_command: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    execution_time_ms: Optional[int] = None
    created_at: datetime


class AuditLogListOut(BaseModel):
    """หน้าประวัติ audit — envelope เดียวกับ /issues (แบ่งหน้า)"""
    items: List[AuditLogOut]
    total: int
    page: int
    page_size: int
    pages: int
