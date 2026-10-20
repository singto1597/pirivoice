"""Schemas สำหรับ **การเลื่อนชั้นทั้งโรงเรียน** (`/api/rollover/*`) — P4

⚠️ **คนละเรื่องกับ `/api/settings/years` (CRUD ปี) และ `/api/settings/terms` (ภาคเรียน):**
  · `/settings/years` = สร้าง/แก้/ตั้งปีปัจจุบัน
  · `/rollover/*`      = **ลงมือ** เลื่อนเด็กทั้งโรงเรียนเข้าปีใหม่ (เขียนจริงหลายพันแถว)

⚠️ **`apply` ต้องส่ง `run_id` จาก `preview` เสมอ — ไม่รับ `from_year_id`/`to_year_id` ตรง ๆ**
   โดยเจตนา: ปีคู่ที่เลื่อนถูก "ตรึง" ไว้ตั้งแต่ตอน preview ⇒ ผู้ใช้ต้องเห็นแผนก่อนกดจริง
   และยิง apply ด้วยคู่ปีอื่นที่ไม่ได้ดูไว้ไม่ได้ (ลดการกดผิดปี ซึ่งแก้ยากมาก)

⚠️ `room_overrides` = `{รหัสห้องต้นทาง: รหัสห้องปลายทาง}` — **ทางเดียว** ที่ผู้ใช้ระบุห้องปลายทางเอง
   ใช้กับห้องที่ระบบหาปลายทางไม่ได้ (เช่นข้อมูลจริง: `ม.3/14` มี 40 คน แต่ไม่มี `ม.4/14`)
   ⇒ ระบบ **ห้ามเดา** แทน · ค่าที่ส่งต้องเป็นห้องที่มีอยู่จริง (ไม่สร้างห้องใหม่ให้)
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


def _clean_overrides(v: Dict[str, str]) -> Dict[str, str]:
    """ตัดคู่ที่ค่าเป็นค่าว่างทิ้ง — ช่องว่างใน UI แปลว่า "ยังไม่เลือก" ไม่ใช่ห้องชื่อ ''"""
    cleaned = {}
    for key, value in (v or {}).items():
        key = (key or "").strip()
        value = (value or "").strip()
        if key and value:
            cleaned[key] = value
    return cleaned


class RolloverPreviewRequest(BaseModel):
    """ขอแผนการเลื่อนชั้นจากปีหนึ่งไปอีกปีหนึ่ง (ยังไม่เขียนข้อมูลสมาชิก)

    ⚠️ **รับ `room_overrides` ด้วย ไม่ใช่แค่ตอน apply** — โดยเจตนา: หน้าจอให้ผู้ใช้เลือก
       ห้องปลายทางของห้องที่แมปไม่ได้ *ก่อน* กดปุ่มอันตราย ⇒ ต้อง preview ซ้ำได้ว่าหลังเลือกแล้ว
       (ก) `can_apply` เป็นจริงหรือยัง และ (ข) มีปัญหาอื่นโผล่ไหม (เช่นเลขประจำตัวซ้ำเพราะยุบห้อง)
       ถ้า preview ไม่รับค่านี้ ผู้ใช้จะเห็นคำเตือนพวกนี้ **ครั้งแรกตอนกด apply** ซึ่งสายเกินไป
    """
    from_year_id: int = Field(..., description="ปีต้นทาง — ต้องเป็นปีปัจจุบัน")
    to_year_id: int = Field(..., description="ปีปลายทาง — ต้องยังว่างอยู่")
    room_overrides: Dict[str, str] = Field(
        default_factory=dict,
        description="ห้องที่เลือกปลายทางเอง (ดูคำอธิบายใน RolloverApplyRequest)",
    )

    @field_validator("room_overrides")
    @classmethod
    def _v(cls, v: Dict[str, str]) -> Dict[str, str]:
        return _clean_overrides(v)


class RolloverApplyRequest(BaseModel):
    """ยืนยันทำจริง — อ้าง `run_id` ที่ได้จาก preview"""
    run_id: int = Field(..., description="`run_id` ที่ได้จาก POST /rollover/preview")
    room_overrides: Dict[str, str] = Field(
        default_factory=dict,
        description=(
            "แก้ห้องที่ระบบหาปลายทางไม่ได้: {รหัสห้องต้นทาง: รหัสห้องปลายทาง} "
            "เช่น {\"ม.3/14\": \"ม.4/13\"} — รหัสห้องต้องมีอยู่จริงในระบบ"
        ),
    )

    @field_validator("room_overrides")
    @classmethod
    def _v(cls, v: Dict[str, str]) -> Dict[str, str]:
        return _clean_overrides(v)


class RolloverYearRef(BaseModel):
    """ปีอ้างอิงแบบย่อ — ใช้ทั้งฝั่งต้นทางและปลายทาง"""
    id: int
    year_be: int
    name: str


class RolloverCountByRole(BaseModel):
    """จำนวนคน แยกตามบทบาท — `by_role` ว่าง = ไม่มีใครในกลุ่มนั้น"""
    count: int = 0
    by_role: Dict[str, int] = Field(default_factory=dict)


class RolloverRoomRow(BaseModel):
    """หนึ่งห้องในแผน — `status='unmapped'` คือห้องที่ต้องเลือกปลายทางเอง"""
    from_room_code: Optional[str] = None
    to_room_code: Optional[str] = None
    student_count: int = 0
    status: str = "ok"


class RolloverLevelGroup(BaseModel):
    """สรุปต่อระดับชั้น — `target_level=None` = ระดับที่จบ (ม.6) หรือระดับที่ไม่รู้จัก"""
    level: Optional[str] = None
    target_level: Optional[str] = None
    student_count: int = 0
    mapped_rooms: int = 0
    unmapped_rooms: int = 0
    rooms: List[RolloverRoomRow] = Field(default_factory=list)


class RolloverGraduatingRoom(BaseModel):
    room_code: Optional[str] = None
    student_count: int = 0


class RolloverGraduating(BaseModel):
    """ผู้จบการศึกษา (ม.6) — แถวเดิมจะกลายเป็น `graduated` และ **ไม่สร้างแถวใหม่**"""
    count: int = 0
    rooms: List[RolloverGraduatingRoom] = Field(default_factory=list)


class RolloverUnmappedRoom(BaseModel):
    """ห้องที่หาปลายทางไม่ได้ — **ต้องแก้ก่อนจึงจะ apply ได้**"""
    from_room_code: Optional[str] = None
    from_room_id: Optional[int] = None
    level: Optional[str] = None
    student_count: int = 0
    reason: str = ""


class RolloverPreviewOut(BaseModel):
    """ผล preview ครบชุด — `can_apply=False` พร้อม `blockers` คือเหตุผลที่ยังกดไม่ได้"""
    run_id: int
    from_year: RolloverYearRef
    to_year: RolloverYearRef
    total_active: int = 0
    promoted: RolloverCountByRole = Field(default_factory=RolloverCountByRole)
    graduating: RolloverGraduating = Field(default_factory=RolloverGraduating)
    staff_carried: RolloverCountByRole = Field(default_factory=RolloverCountByRole)
    positions_reset: RolloverCountByRole = Field(default_factory=RolloverCountByRole)
    council_lapsing: RolloverCountByRole = Field(default_factory=RolloverCountByRole)
    roomless: RolloverCountByRole = Field(default_factory=RolloverCountByRole)
    by_level: List[RolloverLevelGroup] = Field(default_factory=list)
    unmapped: List[RolloverUnmappedRoom] = Field(default_factory=list)
    blockers: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    can_apply: bool = False


class RolloverApplyOut(BaseModel):
    """ผลการทำจริง — ตัวเลขที่ **เกิดขึ้นจริง** (ไม่ใช่ที่ preview ไว้)"""
    run_id: int
    from_year: RolloverYearRef
    to_year: RolloverYearRef
    promoted_count: int = 0
    graduated_count: int = 0
    staff_carried_count: int = 0
    positions_reset_count: int = 0
    closed_count: int = 0
    room_overrides: Dict[str, str] = Field(default_factory=dict)
    plan: Dict[str, Any] = Field(
        default_factory=dict,
        description="แผนชุดสุดท้ายที่ใช้จริง (หลังใช้ room_overrides แล้ว)",
    )


class RolloverRunOut(BaseModel):
    """หนึ่งรอบการเลื่อนชั้น — ใช้ทั้งหน้าประวัติและผลลัพธ์ของ preview/apply"""
    id: int
    from_year_id: int
    to_year_id: int
    status: str = Field(..., description="PREVIEWED / APPLIED / FAILED")
    from_year: RolloverYearRef
    to_year: RolloverYearRef
    promoted_count: int = 0
    graduated_count: int = 0
    staff_carried_count: int = 0
    positions_reset_count: int = 0
    unmapped_count: int = 0
    error_message: Optional[str] = None
    created_by: Optional[int] = None
    created_at: Optional[datetime] = None
    applied_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    plan: Dict[str, Any] = Field(default_factory=dict)


class RolloverRunListOut(BaseModel):
    """ประวัติการเลื่อนชั้น — ใหม่สุดก่อน (ไม่แบ่งหน้าแบบ envelope เพราะจำนวนรอบน้อยมาก)"""
    items: List[RolloverRunOut]
    total: int


class ReconciliationPerson(BaseModel):
    """หนึ่งคนในรายงานกระทบยอด — `user_id=None` = แถวที่ไม่มีบัญชีผูกอยู่"""
    user_id: Optional[int] = None
    student_id: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    class_role: Optional[str] = None
    room_code: Optional[str] = None


class ReconciliationOut(BaseModel):
    """กระทบยอดรายชื่อสองปี — **ไม่เดาสาเหตุ** แค่บอกว่าใครหาย/ใครเพิ่ม

    `missing` = มีในปีก่อน แต่ไม่มีในปีใหม่ (ย้ายออก / จบ / ตกหล่น — คนตัดสิน)
    `added`   = มีในปีใหม่ แต่ไม่มีในปีก่อน (ย้ายเข้า)
    """
    from_year_id: int
    to_year_id: int
    missing_count: int = 0
    added_count: int = 0
    missing: List[ReconciliationPerson] = Field(default_factory=list)
    added: List[ReconciliationPerson] = Field(default_factory=list)
