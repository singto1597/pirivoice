from datetime import datetime
from typing import Optional, List, Literal
from pydantic import BaseModel, Field

# สถานะของแถวสมาชิก — **ปิดรู "free text"** ที่เดิม `StudentUpdateRequest.status`
# รับ string อะไรก็ได้ ⇒ พิมพ์ "Activ" แล้วแถวหลุดจากทุก query ที่กรอง status='active'
# เงียบ ๆ (ไม่มี error ให้ตามหา) · `superseded` = แถวซ้ำที่ถูกแทนที่ด้วยการย้ายห้อง
StudentStatus = Literal[
    "active",           # กำลังศึกษาอยู่ในปีนั้น
    "pending",          # รออนุมัติ/ยังไม่ยืนยัน
    "suspended",        # พักการเรียน
    "promoted",         # ปีเก่าที่ถูกเลื่อนชั้นไปแล้ว (P4)
    "graduated",        # จบการศึกษา (P4)
    "transferred_out",  # ย้ายออกนอกโรงเรียน
    "left",             # ออกกลางคัน
    "superseded",       # แถวซ้ำในปีเดียวกันที่ถูกแทนที่ (การย้ายห้อง)
]


# ===================== Room =====================
class RoomOut(BaseModel):
    id: int
    room_code: str
    room_name: str
    level: Optional[str] = None
    room_number: Optional[int] = None


# ===================== Student =====================
class StudentOut(BaseModel):
    id: int
    room_id: Optional[int] = None
    room_code: Optional[str] = None
    room_name: Optional[str] = None
    student_id: str
    student_no: Optional[int] = None
    prefix: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    nickname: Optional[str] = None
    class_role: str
    staff_level: Optional[str] = None   # ระดับชั้นที่ครูทั่วไปรับผิดชอบ เช่น 'ม.4'
    is_admin: bool = False
    permissions: List[str] = []
    responsibilities: List[str] = []    # หน้าที่รับผิดชอบ (สภานักเรียน/ผู้ช่วยหัวหน้าระดับ) — ตรงกับ issues.category
    status: str = "active"


class StudentUpdateRequest(BaseModel):
    """แก้ข้อมูลสมาชิก — ทุกฟิลด์เป็น optional (PATCH semantics: ไม่ส่ง = ไม่แก้)

    ⚠️ **แก้ `student_id` ไม่แก้ `users.username`** โดยเจตนา — username คือกุญแจล็อกอิน
       และถูกอ้างใน `users` (ไม่ใช่ `students`) ⇒ ถ้าแก้ตามกันด้วย การแก้เลขที่พิมพ์ผิด
       จะทำให้เด็กคนนั้น **ล็อกอินไม่ได้** จนกว่าแอดมินจะแก้ users ให้ (งานคนละส่วน)
    """
    class_role: Optional[str] = None
    status: Optional[StudentStatus] = None
    is_admin: Optional[bool] = None
    staff_level: Optional[str] = None   # อัปเดตระดับชั้นที่ครูดูแลได้
    responsibilities: Optional[List[str]] = None   # แก้หน้าที่รับผิดชอบได้ (เฉพาะ role ที่มีหน้าที่)
    # --- ข้อมูลตัวตน (P5: แก้ข้อมูลที่กรอกผิด) ---
    prefix: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    nickname: Optional[str] = None
    student_no: Optional[int] = Field(None, ge=1, description="เลขที่ในห้อง")
    student_id: Optional[str] = Field(None, min_length=1, max_length=10, description="รหัสนักเรียน (ไม่แก้ users.username)")


class BulkMoveRequest(BaseModel):
    """ย้ายนักเรียนหลายคนเข้าห้องเดียวพร้อมกัน (ภายในปีปัจจุบันเท่านั้น)

    ⚠️ `student_ids` คือ **`students.id` ของแถวสมาชิก** ไม่ใช่ `users.id` — เพราะการย้าย
       ต้องระบุว่าย้าย *แถวของปีไหน* · ระบบจะปฏิเสธแถวที่ไม่ใช่ปีปัจจุบัน
    """
    student_ids: List[int] = Field(..., min_length=1, description="students.id ของแถวสมาชิกที่จะย้าย")
    to_room_code: str = Field(..., min_length=1, description="รหัสห้องปลายทาง เช่น ม.4/1")
    note: Optional[str] = None


class StudentMoveOut(BaseModel):
    """หนึ่งรายการย้ายห้อง — ใช้ทั้งในผลลัพธ์ bulk-move และ timeline ประวัติ"""
    id: int
    from_room_id: Optional[int] = None
    from_room_code: Optional[str] = None
    to_room_id: Optional[int] = None
    to_room_code: Optional[str] = None
    academic_year_id: Optional[int] = None
    year_be: Optional[int] = None
    note: Optional[str] = None
    moved_by: Optional[int] = None
    moved_by_name: Optional[str] = None
    moved_at: Optional[datetime] = None


class StudentHistoryYear(BaseModel):
    """หนึ่งปีของชีวิตนักเรียน — ประกอบ timeline ข้ามปี"""
    student_row_id: int
    academic_year_id: Optional[int] = None
    year_be: Optional[int] = None
    room_id: Optional[int] = None
    room_code: Optional[str] = None
    level: Optional[str] = None
    student_no: Optional[int] = None
    class_role: str
    status: str


class StudentHistoryOut(BaseModel):
    """ไทม์ไลน์ประวัติ: ข้ามปี (students) + ย้ายในปี (student_moves)"""
    user_id: int
    student_id: Optional[str] = None
    full_name: Optional[str] = None
    years: List[StudentHistoryYear] = []
    moves: List[StudentMoveOut] = []


class StudentCreateRequest(BaseModel):
    """เพิ่มผู้ใช้งานแบบ Manual (สำหรับกรณี import Excel ไม่ครบ)"""
    username: str = Field(..., description="รหัสนักเรียน/username")
    password: Optional[str] = Field(None, min_length=4, description="รหัสผ่าน (ถ้าไม่ระบุ = เปลี่ยนครั้งแรก)")
    prefix: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    nickname: Optional[str] = None
    room_code: Optional[str] = Field(None, description="รหัสห้อง เช่น ม.4/1 — สร้างห้องให้ถ้าไม่มี")
    class_role: str = Field(..., description="ตำแหน่ง เช่น council_member / level_vice_president / class_president")
    responsibilities: Optional[List[str]] = None   # หน้าที่รับผิดชอบ (เฉพาะ role ที่มีหน้าที่)


# ===================== My Profile =====================
class MyProfileOut(BaseModel):
    id: int
    student_id: str
    student_no: Optional[int] = None
    prefix: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    nickname: Optional[str] = None
    class_role: str
    staff_level: Optional[str] = None   # ระดับชั้นที่ครูทั่วไปรับผิดชอบ
    status: str
    room_id: Optional[int] = None
    room_code: Optional[str] = None
    room_name: Optional[str] = None
    level: Optional[str] = None
    # จาก users
    username: str
    full_name: Optional[str] = None
    phone_number: Optional[str] = None
    email: Optional[str] = None


class UpdateProfileRequest(BaseModel):
    prefix: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    nickname: Optional[str] = None
    phone_number: Optional[str] = None
    email: Optional[str] = None
