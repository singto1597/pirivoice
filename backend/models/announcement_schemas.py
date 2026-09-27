"""Schemas สำหรับ "จัดการประกาศ" (Announcement CRUD — ต้องมีสิทธิ์ MANAGE_ANNOUNCEMENTS)

แยกจาก `public_schemas.AnnouncementOut` โดยเจตนา: ฝั่ง public เป็น endpoint ที่
**ไม่ต้องล็อกอิน** จึงห้ามคืน `created_by` / `deleted_at` / เวลาที่แก้ — ข้อมูล
ผู้ดูแล + ชื่อไม่ควรหลุดไปหน้า Landing สาธารณะ
"""
from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

# ต้องตรงกับ CHECK constraint `chk_announcements_priority` ใน init_db
AnnouncementPriority = Literal["normal", "high", "urgent"]


def _validate_link(value: Optional[str]) -> Optional[str]:
    """
    🛡️ บังคับให้ลิงก์เป็น http/https เท่านั้น — ไม่ใช่แค่ความเรียบร้อยของข้อมูล

    หน้า Landing ผูก `<a :href="a.link">` ตรง ๆ (`Landing.vue`) ถ้าปล่อยให้เก็บ
    `javascript:...` ได้ มันจะรันตอนผู้ใช้คลิก บนหน้า public ที่ไม่ต้องล็อกอิน
    ⇒ ช่อง XSS ที่เปิดทันทีที่ประกาศแก้ได้จากหน้าเว็บ (เดิมตั้งได้แค่ทาง seed
      ซึ่งเชื่อถือได้ จึงไม่มีใครเห็นปัญหา)
    """
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    if not value.lower().startswith(("http://", "https://")):
        raise ValueError("ลิงก์ต้องขึ้นต้นด้วย http:// หรือ https:// เท่านั้น")
    return value


class AnnouncementCreateRequest(BaseModel):
    """ข้อมูลที่ส่งมาตอนสร้างประกาศ"""
    message: str = Field(min_length=1, max_length=1000)
    priority: AnnouncementPriority = "normal"
    link: Optional[str] = Field(None, max_length=500)

    @field_validator("message")
    @classmethod
    def _strip_message(cls, v: str) -> str:
        # "   " ผ่าน min_length=1 ได้ (นับเป็น 3 ตัว) ⇒ ต้อง strip แล้วเช็คซ้ำ
        v = v.strip()
        if not v:
            raise ValueError("ข้อความประกาศห้ามว่าง")
        return v

    @field_validator("link")
    @classmethod
    def _check_link(cls, v: Optional[str]) -> Optional[str]:
        return _validate_link(v)


class AnnouncementUpdateRequest(BaseModel):
    """ข้อมูลที่ส่งมาตอนแก้ประกาศ (PATCH — ส่งเฉพาะฟิลด์ที่จะแก้)

    ส่ง `link: null` มาชัด ๆ = สั่งล้างลิงก์ (ต่างจาก "ไม่ส่ง link มาเลย")
    """
    message: Optional[str] = Field(None, min_length=1, max_length=1000)
    priority: Optional[AnnouncementPriority] = None
    link: Optional[str] = Field(None, max_length=500)

    @field_validator("message")
    @classmethod
    def _strip_message(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip()
        if not v:
            raise ValueError("ข้อความประกาศห้ามว่าง")
        return v

    @field_validator("link")
    @classmethod
    def _check_link(cls, v: Optional[str]) -> Optional[str]:
        return _validate_link(v)


class AnnouncementAdminOut(BaseModel):
    """หนึ่งแถวสำหรับหน้า admin — มีข้อมูลผู้ประกาศ (ไม่ส่งออกทาง public)

    created_by_name / updated_by_name มาจาก LEFT JOIN users — เป็น None ได้เมื่อ
    ประกาศนั้นถูก seed ก่อนมีฟีเจอร์นี้ หรือผู้ใช้นั้นถูกลบไปแล้ว
    """
    id: int
    message: str
    priority: str
    link: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None
    created_by: Optional[int] = None
    updated_by: Optional[int] = None
    created_by_name: Optional[str] = None
    updated_by_name: Optional[str] = None


class AnnouncementListOut(BaseModel):
    """หน้ารายการประกาศ (admin) — envelope เดียวกับ /api/audit-logs (แบ่งหน้า)"""
    items: List[AnnouncementAdminOut]
    total: int
    page: int
    page_size: int
    pages: int
