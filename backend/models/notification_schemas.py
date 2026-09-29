from typing import List, Optional
from pydantic import BaseModel, Field, field_validator
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
    # ⚠️ 5 กลุ่ม (announcement มาจาก E2) — ไม่ fix ตายตัวเพราะ GROUP_TYPES โตได้
    counts: dict[str, int]  # {"issue_mine": 1, …, "board": 3, "report": 0, "announcement": 0}
    total: int


# ⚠️ **สอง pattern นี้ต้องไม่เหมือนกัน — อย่ารวมเป็นตัวเดียว**
#   · READ_GROUP_TYPE_PATTERN     = 5 กลุ่ม: ใช้ *กรอง/อ่าน* (list, mark_read) ⇒ ต้องมี announcement
#   · GROUP_TYPE_PATTERN (ของ preference) = 4 กลุ่ม: ใช้ *ปิด/เปิด* ⇒ **ห้ามมี announcement**
#   ซ้ำโดยเจตนากับ `GROUP_TYPES`/`PREFERENCE_GROUPS` ใน services/notification_service.py
#   และ `GROUP_TYPE_PATTERN` (read) ใน routers/notification_router.py — เพิ่มกลุ่มใหม่ต้องแก้ทั้งชุด
#   เชิงอ่าน + frontend
READ_GROUP_TYPE_PATTERN = "^(issue_mine|issue_received|board|report|announcement)$"


class MarkReadRequest(BaseModel):
    # อย่างน้อยต้องระบุหนึ่งอย่าง หรือ read_all=True (กันเผลอเคลียร์ทุกอย่าง)
    ids: Optional[List[int]] = None
    group_type: Optional[str] = Field(None, pattern=READ_GROUP_TYPE_PATTERN)
    entity_type: Optional[str] = None
    entity_id: Optional[int] = None
    board_id: Optional[int] = None
    read_all: bool = Field(False, description="อ่านทั้งหมด (เคลียร์ทุกกลุ่ม)")


class MarkReadOut(BaseModel):
    updated: int


# pattern ของกลุ่มที่ **ผู้ใช้ปิดได้** — ต้องตรงกับ PREFERENCE_GROUPS ใน
# services/notification_service.py ⇒ `announcement` ไม่มีทางเข้ามาที่นี่ได้ (ปิดประกาศฉุกเฉินไม่ได้)
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


# ============================================================
# 🔔 Web Push (A3)
# ============================================================

def _require_https_endpoint(v: str) -> str:
    """endpoint ของ Push API ต้องเป็น `https://` เท่านั้น

    ⭐ ไม่ใช่พิธีกรรม: `http://` จะถูกปฏิเสธด้วย error ที่อ่านไม่ออกตอนส่งจริง
       (`_send_one` ยิงไปแล้วได้ 400 จากผู้ให้บริการ) ⇒ **จับที่ทางเข้า** ดีกว่า
       ปล่อยให้ไปพังใน worker ที่ไม่มีใครเห็น response
       และเบราว์เซอร์ทุกตัวให้ endpoint เป็น `https://` อยู่แล้ว ⇒ ค่าที่ไม่ใช่
       แปลว่ามีอะไรผิดปกติ (หรือมีคนยิง API ตรง) ไม่ใช่ผู้ใช้จริงพิมพ์ผิด
    """
    if not v.startswith("https://"):
        raise ValueError("endpoint ต้องขึ้นต้นด้วย https:// (Push API บังคับ)")
    return v


class PushKeys(BaseModel):
    """คู่กุญแจของอุปกรณ์ ที่เบราว์เซอร์สร้างให้ตอน `pushManager.subscribe()`

    ⚠️ **ห้ามใช้ `min_length` กับสองตัวนี้แบบเดา ๆ** — `p256dh` คือ P-256 public key
       แบบ uncompressed point (65 byte → base64url 87 ตัวอักษร) และ `auth` คือ secret
       16 byte (→ 22 ตัวอักษร) · แต่ค่าที่แน่นอน **ขึ้นกับเบราว์เซอร์** (บางตัวมี padding
       บางตัวไม่มี) ⇒ ตรวจแค่ "ไม่ว่าง" แล้วให้ `push_service._decode_key()` เป็นคน
       ตัดสินตอนส่งจริง — ถ้าเข้มเกินไปจะปฏิเสธอุปกรณ์ที่ใช้ได้จริง โดยหาสาเหตุยากมาก
    """
    p256dh: str = Field(..., min_length=1, max_length=255)
    auth: str = Field(..., min_length=1, max_length=255)


class PushSubscriptionIn(BaseModel):
    """body ของ `POST /notifications/push/subscribe`

    🚨 **ไม่มีฟิลด์ `user_id` โดยเจตนา — ห้ามเพิ่มเด็ดขาด**
       เจ้าของ subscription ต้องมาจาก JWT เท่านั้น (ดู `_ensure_user`)
       ถ้ามีฟิลด์นี้ ผู้ใช้คนใดก็ลงทะเบียนปลายทางของตนให้เป็นของคนอื่นได้
       ⇒ **push ของเหยื่อจะถูกส่งไปที่อุปกรณ์ของผู้โจมตี**
       · pydantic ตัดฟิลด์แปลกปลอมทิ้งอยู่แล้ว (`extra` ถูกละเว้นโดย default)
         ⇒ ส่ง `user_id` มาใน body ก็ไม่มีผล (เทสต์ S8 พิสูจน์เรื่องนี้)
    """
    endpoint: str = Field(
        ...,
        min_length=8,
        max_length=1000,
        description="URL ปลายทาง push จาก PushSubscription.endpoint (ต้องเป็น https)",
    )
    keys: PushKeys

    _https_only = field_validator("endpoint")(_require_https_endpoint)


class PushSubscribeOut(BaseModel):
    device_count: int = Field(..., description="จำนวนอุปกรณ์ที่เปิด push อยู่ (หลังบันทึก)")


class PushUnsubscribeIn(BaseModel):
    endpoint: str = Field(..., min_length=8, max_length=1000)

    _https_only = field_validator("endpoint")(_require_https_endpoint)


class PushUnsubscribeOut(BaseModel):
    removed: int = Field(..., description="จำนวนแถวที่ลบจริง (0 = ไม่มีของตัวเองที่ตรงกัน)")
    device_count: int


class PushStatusOut(BaseModel):
    """สถานะ push ของผู้ใช้คนนี้ + public key ที่เบราว์เซอร์ต้องใช้ subscribe

    ⚠️ `enabled=False` = เซิร์ฟเวอร์ยังไม่ได้ตั้งคีย์ VAPID ⇒ frontend ต้อง **ซ่อนการ์ด
       ทั้งใบ** ไม่ใช่โชว์ปุ่มที่กดแล้วไม่เกิดอะไร
    """
    enabled: bool
    public_key: str = Field("", description="VAPID public key (base64url) — ว่างเมื่อ enabled=false")
    device_count: int
