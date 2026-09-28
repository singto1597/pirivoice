"""Schemas สำหรับ "ตั้งค่าระบบ" (`/api/settings/*`) — ต้องมีสิทธิ์ MANAGE_SETTINGS

ปัจจุบันมีอย่างเดียว: **ภาคเรียน** (academic_terms) — ดู services/term_service.py

⚠️ `start_date`/`end_date` เป็นชนิด `date` ไม่ใช่ `str` โดยเจตนา (กฎ backend.md:
"Date params ต้อง typed date/datetime เสมอ เพื่อกันบั๊ก toordinal()") — Pydantic จะ
ปฏิเสธ "16/05/2026" ให้เองเป็น 422 แทนที่จะหลุดไปพังที่ชั้น SQL

⚠️ **ไม่มีการตรวจ `end_date >= start_date` ที่ชั้นนี้** โดยเจตนา — PATCH เป็น partial
จึงเทียบไม่ได้ว่าอีกด้านหนึ่งคืออะไร (ต้องอ่านค่าที่เก็บอยู่จริงก่อน) ⇒ ตรวจที่
`term_service` ที่เดียว ทั้ง create และ update ⇒ **ผิดวันที่ได้ 400 เสมอ ไม่ใช่ 422**
(และมี CHECK constraint `chk_academic_terms_range` ที่ DB เป็นด่านสุดท้าย)
"""
from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class AcademicTermCreateRequest(BaseModel):
    """ข้อมูลตอนสร้างภาคเรียน"""
    name: str = Field(..., min_length=1, max_length=50, description='เช่น "ภาคเรียนที่ 1/2569"')
    start_date: date
    end_date: date = Field(..., description="รวมวันสุดท้าย (inclusive)")
    is_current: bool = Field(False, description="ตั้งเป็นภาคปัจจุบันทันที (ปลดตัวเก่าให้ในทรานแซกชันเดียว)")

    @field_validator("name")
    @classmethod
    def _strip_name(cls, v: str) -> str:
        # "   " ผ่าน min_length=1 ได้ (นับเป็น 3 ตัว) ⇒ strip แล้วเช็คซ้ำ
        v = v.strip()
        if not v:
            raise ValueError("ชื่อภาคเรียนห้ามว่าง")
        return v


class AcademicTermUpdateRequest(BaseModel):
    """PATCH — ส่งเฉพาะฟิลด์ที่จะแก้ (ไม่ส่ง = ไม่แตะ)

    ⚠️ ไม่มี `is_current` ที่นี่ — เปลี่ยนภาคปัจจุบันต้องเรียก `POST .../set-current`
    (ต้องล้างตัวเก่าก่อนเสมอ ⇒ ต้องมีทางเดียวที่ทำถูก)
    """
    name: Optional[str] = Field(None, min_length=1, max_length=50)
    start_date: Optional[date] = None
    end_date: Optional[date] = None

    @field_validator("name")
    @classmethod
    def _strip_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip()
        if not v:
            raise ValueError("ชื่อภาคเรียนห้ามว่าง")
        return v


class AcademicTermOut(BaseModel):
    """หนึ่งแถวภาคเรียน — `deleted_at` มีค่า = ถูกลบ (soft delete)"""
    id: int
    name: str
    start_date: date
    end_date: date
    is_current: bool
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None


class AcademicTermListOut(BaseModel):
    """หน้ารายการภาคเรียน — envelope เดียวกับ /api/audit-logs (แบ่งหน้า)"""
    items: List[AcademicTermOut]
    total: int
    page: int
    page_size: int
    pages: int
