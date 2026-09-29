"""Schemas สำหรับ "ตั้งค่าระบบ" (`/api/settings/*`)

สองเรื่อง:
- **ภาคเรียน** (`academic_terms`) — ต้องมีสิทธิ์ `MANAGE_SETTINGS` ทุก endpoint
- **quiet hours** (A8) — `GET` **เปิดให้ผู้ใช้ที่ล็อกอินทุกคน** · `PUT` ต้องมีสิทธิ์
  (เหตุผลอยู่ใน `services/app_settings_service.py` — ค่านี้มีไว้ *อธิบาย* ให้นักเรียน
  เข้าใจว่าทำไมมือถือเงียบ ⇒ ถ้าปิดการอ่าน เท่ากับซ่อนคำอธิบายจากคนที่ได้รับผลกระทบ)

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


# ============================================================
# 🔇 Quiet Hours (A8) — ช่วงเวลาที่โรงเรียนไม่ส่ง push
# ============================================================

class QuietHoursOut(BaseModel):
    """ค่าตั้ง quiet hours ปัจจุบัน

    ⚠️ ค่าที่คืน **ผ่าน `normalize_quiet_hours()` มาแล้วเสมอ** ⇒ `start`/`end` เป็น
       `"HH:MM"` แน่นอน และ `enabled=False` ถ้าค่าใน DB ใช้ไม่ได้ (แถวเสีย/parse ไม่ได้)
       ⇒ client ไม่ต้องป้องกันอะไรเพิ่ม และ **ห้ามเชื่อค่าดิบจาก DB เอง**

    `updated_at` เป็น `None` = **โรงเรียนยังไม่เคยตั้ง** — แยกจาก "ตั้งไว้แล้วแต่ปิดสวิตช์"
       ได้ ⇒ UI ใช้เขียนกำกับว่า "ค่าเริ่มต้น (ยังไม่ได้ตั้ง)" ต่างจาก "ปิดอยู่"
    """
    enabled: bool
    start: str = Field(..., description='เวลาเริ่ม "HH:MM" (เขต Asia/Bangkok)')
    end: str = Field(..., description='เวลาสิ้นสุด "HH:MM" — อาจน้อยกว่า start ได้ (= ข้ามเที่ยงคืน)')
    updated_at: Optional[datetime] = Field(
        None, description="None = โรงเรียนยังไม่เคยตั้งค่านี้ (ยังไม่มีแถวใน app_settings)"
    )


class QuietHoursUpdateRequest(BaseModel):
    """PUT = **full replace** ⇒ ส่งมาครบทั้ง 3 ฟิลด์เสมอ (ไม่ใช่ PATCH)

    ⚠️ **ไม่มี `pattern`/`max_length` ที่ชั้นนี้โดยเจตนา** — `app_settings_service._parse_hhmm()`
       เป็น **นิยามเดียว** ของ "เวลาที่ใช้ได้" และมันตัดช่องว่างหัวท้ายก่อน แล้วรับ `"7:00"`
       คืนเป็น `"07:00"` ด้วย · ถ้าใส่ pattern ที่นี่จะกลายเป็นสองนิยามที่ไม่ตรงกัน
       (`"7:00"` โดน 422 ที่นี่ แต่ service ทำได้) ⇒ ผู้ใช้เจอ error ทั้งที่ระบบรองรับ
       ⇒ **รูปแบบเวลาผิด = 400 เสมอ จากที่เดียว** (แบบเดียวกับเหตุผลของ `end_date >= start_date`
       ที่เขียนกำกับไว้ข้างบน — และที่นั่นก็เลือกตรวจที่ service ที่เดียวเหมือนกัน)

    ⚠️ `start == end` **ไม่ถูกปฏิเสธที่นี่** เพราะความหมายขึ้นกับ `enabled` (`enabled=False`
    คู่กับ `start == end` เป็นคำขอที่ถูกต้อง) ⇒ ตรวจที่ service
    """
    enabled: bool
    start: str = Field(..., description='เวลาเริ่ม "HH:MM" เช่น "22:00"')
    end: str = Field(..., description='เวลาสิ้นสุด "HH:MM" เช่น "06:00" (ข้ามเที่ยงคืนได้)')
