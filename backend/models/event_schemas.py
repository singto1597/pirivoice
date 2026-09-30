"""Schemas สำหรับ "กิจกรรม" (D1 — Events + การลงทะเบียน)

แยก "มุมมองผู้จัดการ" (`EventOut`) ออกจาก "มุมมองนักเรียน" (`EventPublicOut`) โดยเจตนา
— ต่างจากประกาศที่แยกเพราะฝั่ง public **ไม่ต้องล็อกอิน** · ที่นี่ทั้งคู่ต้องล็อกอิน
แต่เหตุผลยังเหมือนเดิม: `EventPublicOut` **ไม่ส่ง** `created_by` / `updated_by` /
`deleted_at` ออกไปเลย ⇒ ต่อให้วันหน้าฝั่ง UI เผลอ bind ทั้ง object ลง template
ก็ไม่มีข้อมูลผู้ดูแลหลุดไปหน้าเด็ก

⚠️ `published_at` / `cancelled_at` **ส่งออกโดยเจตนา** — ทั้งคู่ไม่ใช่ข้อมูลผู้ดูแล
แต่เป็น "ประกาศเมื่อไหร่ / ยกเลิกเมื่อไหร่" ซึ่งนักเรียนต้องรู้จริง (และ `cancel_event`
ก็แจ้งผู้สมัครทุกคนอยู่แล้ว) ⇒ **อย่าเผลอเพิ่มสองตัวนี้เข้าไปในลิสต์ที่ห้ามส่ง**

⚠️ **`status` ของ output เป็น `str` ไม่ใช่ `EventStatus`** — ตามแบบ `AnnouncementAdminOut.priority`
คอลัมน์ถูกคุมด้วย CHECK constraint อยู่แล้ว ⇒ การใส่ Literal ที่ output จะย้ายความเสี่ยง
จาก "แสดงค่าที่ไม่รู้จัก" (UI จัดการได้) ไปเป็น "response validation ล้ม = 500 ทั้งแถว"
(แถวเดียวพังทั้งหน้า) โดยไม่ได้อะไรกลับมา ⇒ **input เข้ม · output หลวมโดยเจตนา**
"""
from datetime import datetime, timedelta, timezone
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

# ต้องตรงกับ CHECK constraint `chk_events_status` ใน migration 025 / init_db
EventStatus = Literal["draft", "published", "cancelled"]

# ต้องตรงกับ CHECK constraint `chk_event_registrations_status`
#
# ⚠️ `checked_in` อยู่ในลิสต์ตั้งแต่รอบนี้ **ทั้งที่ D2 (QR check-in) ยังไม่ทำ** — เจตนา
#    เพราะ CHECK ที่ลิสต์ค่าตายตัวต้องออก migration ใหม่ทุกครั้งที่จะเพิ่มค่า (บทเรียน
#    จาก `piri_boards.board_type` ที่ E1 ต้องไป DROP CONSTRAINT) ⇒ ใส่รอไว้เลยฟรี
#    โดยที่ service ยังไม่เคยเขียนค่านี้
RegistrationStatus = Literal["registered", "waitlisted", "cancelled", "checked_in"]

# เขตเวลาโรงเรียน — ใช้ตัวเดียวกับ `dashboard_service.BKK` / `issue_countdowns`
BKK = timezone(timedelta(hours=7))


def _validate_cover_url(value: Optional[str]) -> Optional[str]:
    """
    🛡️ บังคับให้รูปปกเป็น http/https เท่านั้น — เหตุผลเดียวกับ `announcement._validate_link`

    ฝั่ง UI ผูก `<img :src="e.cover_image_url">` ตรง ๆ · `javascript:` ไม่รันใน `<img>`
    แต่ `data:` รันได้ในบางบริบทและ `file:` ในบางเบราว์เซอร์ ⇒ ปิดประตูตั้งแต่ชั้น schema
    ดีกว่าไปหวังว่าทุกที่ที่เอาไปใช้จะกรองเอง
    """
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    if not value.lower().startswith(("http://", "https://")):
        raise ValueError("ลิงก์รูปปกต้องขึ้นต้นด้วย http:// หรือ https:// เท่านั้น")
    return value


def _ensure_tz(value: Optional[datetime]) -> Optional[datetime]:
    """
    ⚠️ **จุดที่พังเงียบถ้าลืม** — `<input type="datetime-local">` ฝั่ง frontend ส่ง
    `"2026-10-15T09:00"` ซึ่ง pydantic แปลงเป็น datetime **naive** (ไม่มี tzinfo)

    คอลัมน์ `events.event_date` / `registration_deadline` เป็น `TIMESTAMP WITH TIME ZONE`
    ⇒ asyncpg จะโยน `DataError: invalid input for query argument … can't subtract
    offset-naive and offset-aware datetimes` **ตอน execute** ไม่ใช่ตอน validate
    ⇒ ผู้ใช้เห็น 500 แทน 400 และร่องรอยไปโผล่ที่ชั้น DB ซึ่งหาสาเหตุยาก

    ค่าที่ไม่มี tz จากฟอร์มนี้ **คือเวลาไทยเสมอ** (ผู้ใช้กรอกในเขตเวลาโรงเรียน)
    ⇒ ติด Asia/Bangkok ให้ตรงนี้ · ค่าที่มี tz มาแล้ว (ISO 8601 พร้อม offset) ปล่อยผ่าน
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=BKK)
    return value


def _strip_required(value: str, label: str) -> str:
    """`"   "` ผ่าน `min_length=1` ได้ (นับเป็น 3 ตัว) ⇒ ต้อง strip แล้วเช็คซ้ำ"""
    value = value.strip()
    if not value:
        raise ValueError(f"{label}ห้ามว่าง")
    return value


def _strip_optional(value: Optional[str]) -> Optional[str]:
    """ค่าว่าง/ช่องว่างล้วน → None (ไม่เก็บสตริงว่างลง DB ให้กำกวมกับ "ไม่มีค่า")"""
    if value is None:
        return None
    value = value.strip()
    return value or None


class EventCreateRequest(BaseModel):
    """ข้อมูลที่ส่งมาตอนสร้างกิจกรรม

    ⚠️ **ไม่รับ `status` จาก client** — กิจกรรมเกิดเป็น `draft` เสมอ (ค่า default ของคอลัมน์)
    และเปลี่ยนสถานะได้ทาง `POST /{id}/publish` / `/{id}/cancel` เท่านั้น
    (ผู้ใช้เลือก: "แจ้งเฉพาะตอนกดเผยแพร่ ไม่ใช่ตอนสร้าง" ⇒ การเผยแพร่ต้องเป็นการกระทำ
    ที่แยกออกมาชัด ๆ ไม่ใช่ผลข้างเคียงของการส่งฟอร์ม)

    ⚠️ `registration_deadline` ต้องไม่หลัง `event_date` — **ตรวจที่ service ไม่ใช่ที่นี่**
    เพราะ PATCH เป็น partial ⇒ ที่ชั้น schema ไม่มีทางรู้ค่าอีกฝั่งที่ผู้ใช้ไม่ได้ส่งมา
    (ตรวจที่นี่จะได้ด่านที่ถูกเฉพาะตอน POST ซึ่งเป็นครึ่งเดียวของเส้นทาง)
    """
    title: str = Field(min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=5000)
    location: Optional[str] = Field(None, max_length=200)
    cover_image_url: Optional[str] = Field(None, max_length=500)
    event_date: datetime
    registration_deadline: Optional[datetime] = None
    # None = ไม่จำกัดจำนวน · 0 **ไม่ใช่** "ไม่จำกัด" (CHECK `capacity > 0` กันไว้)
    capacity: Optional[int] = Field(None, ge=1, le=100000)

    @field_validator("title")
    @classmethod
    def _check_title(cls, v: str) -> str:
        return _strip_required(v, "ชื่อกิจกรรม")

    @field_validator("description")
    @classmethod
    def _check_description(cls, v: Optional[str]) -> Optional[str]:
        # description ยอมให้เป็นค่าว่างได้ (ชาวบ้านเฟ้น) — แค่ normalize
        return v.strip() if isinstance(v, str) and v.strip() else None

    @field_validator("location")
    @classmethod
    def _check_location(cls, v: Optional[str]) -> Optional[str]:
        return _strip_optional(v)

    @field_validator("cover_image_url")
    @classmethod
    def _check_cover(cls, v: Optional[str]) -> Optional[str]:
        return _validate_cover_url(v)

    @field_validator("event_date", "registration_deadline")
    @classmethod
    def _check_dt(cls, v: Optional[datetime]) -> Optional[datetime]:
        return _ensure_tz(v)


class EventUpdateRequest(BaseModel):
    """ข้อมูลที่ส่งมาตอนแก้กิจกรรม (PATCH — ส่งเฉพาะฟิลด์ที่จะแก้)

    ส่ง `location: null` / `registration_deadline: null` / `capacity: null` มาชัด ๆ
    = สั่ง **ล้างค่า** · ไม่ส่งมาเลย = คงค่าเดิม (ดู `model_dump(exclude_unset=True)`
    ที่ router — ต่างกันที่ `exclude_unset` ไม่ใช่ `exclude_none`)

    ⚠️ ไม่มี `status` / `published_at` / `cancelled_at` — เปลี่ยนสถานะมี endpoint ของตัวเอง
    ไม่งั้น PATCH ใบเดียวสามารถ "เผยแพร่" กิจกรรมโดยไม่ยิงแจ้งเตือน (ข้าม `publish_event`
    ที่เป็นที่เดียวที่ยิง `notify_fanout`) ⇒ กิจกรรมที่เผยแพร่แล้วไม่มีใครรู้
    """
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=5000)
    location: Optional[str] = Field(None, max_length=200)
    cover_image_url: Optional[str] = Field(None, max_length=500)
    event_date: Optional[datetime] = None
    registration_deadline: Optional[datetime] = None
    capacity: Optional[int] = Field(None, ge=1, le=100000)

    @field_validator("title")
    @classmethod
    def _check_title(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        return _strip_required(v, "ชื่อกิจกรรม")

    @field_validator("description")
    @classmethod
    def _check_description(cls, v: Optional[str]) -> Optional[str]:
        return v.strip() if isinstance(v, str) and v.strip() else None

    @field_validator("location")
    @classmethod
    def _check_location(cls, v: Optional[str]) -> Optional[str]:
        return _strip_optional(v)

    @field_validator("cover_image_url")
    @classmethod
    def _check_cover(cls, v: Optional[str]) -> Optional[str]:
        return _validate_cover_url(v)

    @field_validator("event_date", "registration_deadline")
    @classmethod
    def _check_dt(cls, v: Optional[datetime]) -> Optional[datetime]:
        return _ensure_tz(v)


class EventOut(BaseModel):
    """หนึ่งแถวสำหรับหน้าจัดการ (ต้องมีสิทธิ์ MANAGE_EVENTS)

    `*_count` มาจาก scalar subquery ใน `_SELECT_COLUMNS` ของ `event_service` ไม่ใช่
    คอลัมน์จริง — นับเฉพาะแถวที่ยังมีชีวิตอยู่โดยธรรมชาติ (ตารางนี้ **ไม่มี** `deleted_at`
    ⇒ การยกเลิกพลิก `status='cancelled'` ไม่ได้ลบแถว) ⇒ ประวัติการสมัครยังอยู่ครบ

    `deleted_at` = "ถูกลบจากระบบ" (soft delete) · `cancelled_at` = "สภายกเลิกกิจกรรม"
    เป็นสองแกนอิสระต่อกัน เหมือน `announcements.deleted_at` กับ `retired_at`
    """
    id: int
    title: str
    description: Optional[str] = None
    location: Optional[str] = None
    cover_image_url: Optional[str] = None
    event_date: datetime
    registration_deadline: Optional[datetime] = None
    capacity: Optional[int] = None
    status: str
    published_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    created_by: Optional[int] = None
    updated_by: Optional[int] = None
    created_by_name: Optional[str] = None
    updated_by_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None
    registered_count: int = 0
    waitlisted_count: int = 0


class EventPublicOut(BaseModel):
    """หนึ่งแถวสำหรับนักเรียน — ตัดข้อมูลผู้ดูแลออกทั้งหมด

    `seats_remaining` = `None` เมื่อไม่จำกัดจำนวน (ไม่ใช่ 0 — 0 แปลว่าเต็ม)
    `my_registration_status` = None เมื่อยังไม่เคยสมัคร (หรือเคยยกเลิกแล้วถูกเขียนสถานะ
    เป็น 'cancelled' ซึ่ง UI ควรแสดงเป็น "ยังไม่ได้สมัคร" ไม่ใช่ป้าย "ยกเลิกแล้ว")

    `is_registration_open` คำนวณฝั่ง server **เสมอ** — ห้ามให้ frontend เทียบเวลาเอง
    เพราะนาฬิกาเครื่องผู้ใช้เพี้ยนได้ และกฎ "ปิดเมื่อ event_date ผ่านไปแล้ว" เป็น
    กติกาของระบบ ไม่ใช่การแสดงผล
    """
    id: int
    title: str
    description: Optional[str] = None
    location: Optional[str] = None
    cover_image_url: Optional[str] = None
    event_date: datetime
    registration_deadline: Optional[datetime] = None
    capacity: Optional[int] = None
    status: str
    published_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    registered_count: int = 0
    waitlisted_count: int = 0
    seats_remaining: Optional[int] = None
    is_registration_open: bool = False
    my_registration_status: Optional[str] = None


class EventListOut(BaseModel):
    """หน้ารายการกิจกรรม (ฝั่งจัดการ) — envelope เดียวกับ /api/audit-logs"""
    items: List[EventOut]
    total: int
    page: int
    page_size: int
    pages: int


class EventPublicListOut(BaseModel):
    """หน้ารายการกิจกรรม (ฝั่งนักเรียน) — envelope เดียวกัน คนละชนิดแถว"""
    items: List[EventPublicOut]
    total: int
    page: int
    page_size: int
    pages: int


class EventRegistrationOut(BaseModel):
    """หนึ่งแถวในรายชื่อผู้สมัคร (สภาดูได้ เพื่อจัดการ waitlist ได้จริง)

    `user_name` มาจาก LEFT JOIN กับ students/users — เป็น None ได้ถ้าผู้ใช้ถูกลบ
    ⚠️ ไม่คืน `endpoint`/ข้อมูลอุปกรณ์หรืออะไรที่แตะ push — คนละเรื่องกัน
    """
    id: int
    event_id: int
    user_id: int
    user_name: Optional[str] = None
    status: str
    registered_at: datetime
    cancelled_at: Optional[datetime] = None
    checked_in_at: Optional[datetime] = None


class EventRegistrationListOut(BaseModel):
    """รายชื่อผู้สมัครของกิจกรรมหนึ่ง (เรียงตามคิว — registered_at ASC)"""
    items: List[EventRegistrationOut]
    total: int
    page: int
    page_size: int
    pages: int


class MyRegistrationOut(BaseModel):
    """สถานะการสมัครของ *ฉัน* ในกิจกรรมหนึ่ง — ใช้เติมไอคอน/ปุ่มในหน้า detail

    แยกจาก `EventPublicOut.my_registration_status` เพราะสองอันตอบคำถามต่างกัน:
    อันนั้นตอบ "ฉันสมัครหรือยัง" ในลิสต์ · อันนี้ตอบ "ได้คิวที่เท่าไร" ในหน้า detail
    """
    registered: bool
    registration_id: Optional[int] = None
    status: Optional[str] = None
    queue_position: Optional[int] = None
