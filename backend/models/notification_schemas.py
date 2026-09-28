from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import datetime


class NotificationOut(BaseModel):
    id: int
    group_type: str
    type: str
    title: str
    body: str
    entity_type: Optional[str] = None
    entity_id: Optional[int] = None
    board_id: Optional[int] = None
    actor_id: Optional[int] = None
    actor_name: Optional[str] = None
    read_at: Optional[datetime] = None
    created_at: datetime


class NotificationListOut(BaseModel):
    items: List[NotificationOut]
    total: int
    page: int
    page_size: int
    pages: int


class UnreadCountsOut(BaseModel):
    counts: dict[str, int]  # {"issue_mine": 1, "issue_received": 0, "board": 3, "report": 0}
    total: int


class MarkReadRequest(BaseModel):
    # อย่างน้อยต้องระบุหนึ่งอย่าง หรือ read_all=True (กันเผลอเคลียร์ทุกอย่าง)
    ids: Optional[List[int]] = None
    group_type: Optional[str] = Field(None, pattern="^(issue_mine|issue_received|board|report)$")
    entity_type: Optional[str] = None
    entity_id: Optional[int] = None
    board_id: Optional[int] = None
    read_all: bool = Field(False, description="อ่านทั้งหมด (เคลียร์ทุกกลุ่ม)")


class MarkReadOut(BaseModel):
    updated: int


# ⚠️ pattern นี้ต้องตรงกับ GROUP_TYPES ใน services/notification_service.py
# และ GROUP_TYPE_PATTERN ใน routers/notification_router.py (ซ้ำ 3 ที่โดยเจตนา — เหมือน
# ตัว group_type ของ notifications ที่มีมาก่อนแล้ว; เพิ่มกลุ่มใหม่ต้องแก้ทั้ง 3 + frontend)
GROUP_TYPE_PATTERN = "^(issue_mine|issue_received|board|report)$"


class NotificationPreferenceItem(BaseModel):
    group_type: str = Field(..., pattern=GROUP_TYPE_PATTERN)
    enabled: bool = Field(..., description="False = ปิดแจ้งเตือนกลุ่มนี้ (เงียบทั้ง in-app และ push)")


class NotificationPreferencesOut(BaseModel):
    """คืนครบทุกกลุ่มเสมอ (กลุ่มที่ไม่มีแถว = enabled True)"""
    preferences: List[NotificationPreferenceItem]


class UpdateNotificationPreferencesRequest(BaseModel):
    # 1–4 รายการ: ต้องส่งมาอย่างน้อย 1 (ไม่งั้นเป็น no-op ที่ไม่มีความหมาย) และไม่เกิน
    # จำนวนกลุ่มที่มีจริง — กัน client ส่งขยะยาว ๆ มา
    preferences: List[NotificationPreferenceItem] = Field(..., min_length=1, max_length=4)
