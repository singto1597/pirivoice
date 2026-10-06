"""Schemas สำหรับ **ปีการศึกษา** (`academic_years`) — `/api/settings/years*`

⚠️ **ปี ≠ ภาคเรียน — อย่าสลับ:**
  · ภาคเรียน (`academic_terms`) = "ภาคนี้เป็นยังไง" → ใช้ *กรองสถิติตามช่วงวันที่*
  · ปีการศึกษา (`academic_years`) = "ปี 2569 ใครอยู่ห้องไหน ตำแหน่งอะไร" → ใช้ *เก็บประวัติสมาชิก*
  หนึ่งปีมีสองภาค ⇒ "สมาชิกผูกกับภาคไหน" ไม่มีความหมาย ⇒ สมาชิกผูกกับ **ปี** เท่านั้น

⚠️ **`year_be` เป็น พ.ศ. ไม่ใช่ ค.ศ.** — 2569 ไม่ใช่ 2026 · เดาวันที่จาก `date.today().year`
   แล้วได้ 2026 มาใส่ช่องนี้ = ปีการศึกษา 2026 ซึ่งไม่มีความหมาย ⇒ ระบบจะไม่แปลงให้
   (ดู docs/glossary.md §6 — ทั้งระบบแสดง พ.ศ.)

⚠️ `start_date`/`end_date` เป็นชนิด `date` ไม่ใช่ `str` (กฎ backend.md) และ **ไม่บังคับ**
   ต่างจากภาคเรียน — โรงเรียนสร้างปีการศึกษาล่วงหน้าก่อนรู้วันเปิดเทอมได้
   (ถ้าส่งมา ต้องมี `end_date >= start_date` — ตรวจที่ service ที่เดียว ให้ได้ 400 ไม่ใช่ 422)
"""
from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class AcademicYearCreateRequest(BaseModel):
    """ข้อมูลตอนสร้างปีการศึกษา

    `name` **ไม่บังคับ** — ไม่ส่งมา = ใช้ `"ปีการศึกษา {year_be}"` (เหมือนที่ migration 027 seed ไว้)
    ⇒ ครูไม่ต้องพิมพ์ชื่อยาว ๆ ทุกครั้ง และชื่อจะตรงกันทั้งระบบโดยอัตโนมัติ
    """
    year_be: int = Field(
        ..., ge=2400, le=2700,
        description="พ.ศ. เช่น 2569 — ⚠️ ไม่ใช่ ค.ศ.",
    )
    name: Optional[str] = Field(
        None, min_length=1, max_length=50,
        description='เว้นว่าง = "ปีการศึกษา {year_be}"',
    )
    start_date: Optional[date] = Field(None, description="ไม่บังคับ — ปีที่ยังไม่รู้วันเปิดเทอมก็สร้างได้")
    end_date: Optional[date] = None
    is_current: bool = Field(
        False,
        description=(
            "ตั้งเป็นปีปัจจุบันทันที (ปลดตัวเก่าให้ในทรานแซกชันเดียว) — "
            "⚠️ ตั้งปีที่ยังไม่มีสมาชิกเป็นปัจจุบันไม่ได้ ถ้าปีอื่นยังมีสมาชิกอยู่"
        ),
    )

    @field_validator("name")
    @classmethod
    def _strip_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip()
        if not v:
            raise ValueError("ชื่อปีการศึกษาห้ามว่าง (ถ้าไม่ต้องการตั้งเอง ให้เว้นว่างทั้งฟิลด์)")
        return v


class AcademicYearUpdateRequest(BaseModel):
    """PATCH — ส่งเฉพาะฟิลด์ที่จะแก้ (ไม่ส่ง = ไม่แตะ)

    ⚠️ **ไม่มี `is_current` ที่นี่** — เปลี่ยนปีปัจจุบันต้องเรียก `POST .../set-current`
    (ต้องล้างตัวเก่าก่อนเสมอ + มีด่าน "ปีว่างตั้งเป็นปัจจุบันไม่ได้" ⇒ ต้องมีทางเดียวที่ทำถูก)
    """
    year_be: Optional[int] = Field(None, ge=2400, le=2700, description="แก้ พ.ศ. ที่พิมพ์ผิด")
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
            raise ValueError("ชื่อปีการศึกษาห้ามว่าง")
        return v


class AcademicYearOut(BaseModel):
    """หนึ่งแถวปีการศึกษา

    `member_count` = จำนวนแถวสมาชิก (`students`) ที่ยังไม่ถูกลบในปีนี้ — **ทุกสถานะ** ไม่ใช่แค่
    active ⇒ ปีที่ผ่านมาแล้วจะยังโชว์จำนวนจริง (ใช้เป็นหลักฐานว่า "ปีนี้มีคน 512 คน")
    ⚠️ ไม่ใช่ "จำนวนนักเรียนที่ใช้งานอยู่" — ตัวนั้นต้องกรอง `status='active'` เพิ่ม
    """
    id: int
    year_be: int
    name: str
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    is_current: bool
    member_count: int = 0
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None


class AcademicYearListOut(BaseModel):
    """หน้ารายการปีการศึกษา — envelope เดียวกับ /api/settings/terms (แบ่งหน้า)"""
    items: List[AcademicYearOut]
    total: int
    page: int
    page_size: int
    pages: int
