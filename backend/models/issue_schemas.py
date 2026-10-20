from typing import Optional, List
from pydantic import BaseModel, Field, field_validator
from datetime import datetime

from core.categories import all_main_category_codes, is_valid_category


# ===================== สร้างปัญหา =====================
class IssueCreateRequest(BaseModel):
    # หมวดหลัก: suggestion (เสนอความคิดเห็น) / wellbeing (สุขภาวะทางกายและใจ) / report (แจ้งเหตุ)
    main_category: str = Field(..., description="หมวดหลัก: suggestion / wellbeing / report")
    # หมวดย่อยในหมวดหลัก (ตาม config/categories.json)
    category: str = Field(..., description="หมวดย่อยของหมวดหลัก")
    title: str = Field(..., min_length=3, max_length=200)
    description: str = Field(..., min_length=3)
    is_anonymous: bool = False
    # ระบุห้องที่แจ้ง (default = ห้องตัวเอง ถ้าไม่ระบุ)
    room_id: Optional[int] = None
    # ระดับเริ่มต้นของเรื่อง (room/level/council) — default room
    # เฉพาะผู้มีระดับสูงขึ้นจึงเลือกได้
    start_level: str = "room"
    # 🆕 ปลายทางที่ผู้แจ้งขอ: 'normal' / 'vote' / 'talk' (PIRI Boards)
    # vote/talk → เรื่องตรงไปที่สภา (current_level='council') ให้สภาอนุมัติเป็น board สาธารณะ
    requested_destination: str = "normal"

    @field_validator("requested_destination")
    @classmethod
    def _validate_destination(cls, v: str) -> str:
        if v not in ("normal", "vote", "talk"):
            raise ValueError(f"ปลายทางที่ขอไม่ถูกต้อง: {v} (ต้องเป็น normal/vote/talk)")
        return v

    @field_validator("main_category")
    @classmethod
    def _validate_main_category(cls, v: str) -> str:
        if v not in all_main_category_codes():
            raise ValueError(f"หมวดหลักไม่ถูกต้อง: {v} (ต้องเป็น {', '.join(all_main_category_codes())})")
        return v

    @field_validator("category")
    @classmethod
    def _validate_category(cls, v: str, info) -> str:
        main_cat = info.data.get("main_category")
        if main_cat and not is_valid_category(main_cat, v):
            raise ValueError(f"หมวดย่อย '{v}' ไม่ได้อยู่ในหมวดหลัก '{main_cat}'")
        return v


class IssueUpdateRequest(BaseModel):
    """แก้ไขเรื่อง (ผู้แจ้ง) — PATCH: ส่งเฉพาะฟิลด์ที่ต้องการแก้ (exclude_unset)"""
    main_category: Optional[str] = None
    category: Optional[str] = None
    title: Optional[str] = Field(None, min_length=3, max_length=200)
    description: Optional[str] = Field(None, min_length=3)
    is_anonymous: Optional[bool] = None

    @field_validator("main_category")
    @classmethod
    def _validate_main_category(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in all_main_category_codes():
            raise ValueError(f"หมวดหลักไม่ถูกต้อง: {v} (ต้องเป็น {', '.join(all_main_category_codes())})")
        return v

    @field_validator("category")
    @classmethod
    def _validate_category(cls, v: Optional[str], info) -> Optional[str]:
        # ตรวจคู่ main_category+category เฉพาะเมื่อส่งทั้งคู่พร้อมกัน
        # (ถ้าส่งแค่ category ตัวเดียว ตรวจกับ main_category ปัจจุบันใน service แทน)
        if v is None:
            return v
        main_cat = info.data.get("main_category")
        if main_cat and not is_valid_category(main_cat, v):
            raise ValueError(f"หมวดย่อย '{v}' ไม่ได้อยู่ในหมวดหลัก '{main_cat}'")
        return v


class StepCreateRequest(BaseModel):
    step_title: str = Field(..., min_length=1, max_length=200)
    step_detail: Optional[str] = None


class CountdownSetRequest(BaseModel):
    estimated_days: int = Field(..., ge=1, le=365, description="จำนวนวันที่ใช้แก้ปัญหา")


class ChangeDestinationRequest(BaseModel):
    """เปลี่ยนปลายทางของเรื่อง (แก้แจ้งผิด) — หัวหน้าห้อง/สภา เปลี่ยน normal/vote/talk"""
    requested_destination: str = Field(..., description="ปลายทางใหม่: normal/vote/talk")

    @field_validator("requested_destination")
    @classmethod
    def _check_destination(cls, v: str) -> str:
        if v not in ("normal", "vote", "talk"):
            raise ValueError(f"ปลายทางไม่ถูกต้อง: {v} (ต้องเป็น normal/vote/talk)")
        return v


class EscalateRequest(BaseModel):
    reason: Optional[str] = None


class ApproveToPublicRequest(BaseModel):
    """อนุมัติเรื่องขอเผยแพร่สาธารณะ (สภานักเรียน/แอดมิน) → สร้าง PIRI Board จากเรื่อง"""
    # ประเภท board: 'talk' / 'vote' — ต้องตรงกับ requested_destination ของเรื่อง
    board_type: str = Field(..., description="ประเภท board ที่จะสร้าง: talk / vote")
    # ตัวเลือกโหวต — จำเป็นถ้า board_type='vote' (อย่างน้อย 2)
    vote_choices: Optional[List[str]] = Field(None, description="ตัวเลือกโหวต (จำเป็นถ้า board_type=vote)")
    # เปิดให้คอมเมนต์บน board ได้ไหม (default True)
    allow_comments: bool = True

    @field_validator("board_type")
    @classmethod
    def _validate_board_type(cls, v: str) -> str:
        if v not in ("talk", "vote"):
            raise ValueError(f"ประเภท board ไม่ถูกต้อง: {v} (ต้องเป็น talk/vote)")
        return v

    @field_validator("vote_choices")
    @classmethod
    def _validate_vote_choices(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is None:
            return v
        cleaned = [c.strip() for c in v if c and c.strip()]
        if not cleaned:
            return None
        if len(cleaned) < 2:
            raise ValueError("Board แบบโหวตต้องมีตัวเลือกอย่างน้อย 2 ตัวเลือก")
        if len(cleaned) > 10:
            raise ValueError("Board แบบโหวตมีตัวเลือกได้ไม่เกิน 10 ตัวเลือก")
        return cleaned


class CommentCreateRequest(BaseModel):
    """สร้าง/แก้ไขคอมเมนต์ (แก้ได้เฉพาะ body)"""
    body: str = Field(..., min_length=1, max_length=1000)


# ===================== Response =====================
class CommentOut(BaseModel):
    id: int
    user_id: Optional[int] = None          # ให้ frontend เทียบกับ authStore.user.id (เหมือน reporter_id ใน IssueOut)
    commenter_name: Optional[str] = None   # ชื่อจริงเสมอ (แม้เรื่อง anonymous)
    commenter_room: Optional[str] = None
    commenter_first_name: Optional[str] = None  # ชื่อจริง (avatar ใช้ตัวแรกของชื่อ) — fallback commenter_name
    body: str
    created_at: datetime
    updated_at: Optional[datetime] = None


class IssueStepOut(BaseModel):
    id: int
    step_title: str
    step_detail: Optional[str] = None
    step_order: int
    is_completed: bool
    completed_at: Optional[datetime] = None


class IssueCountdownOut(BaseModel):
    id: int
    estimated_days: int
    started_at: datetime
    deadline: datetime
    is_overdue: bool


class EscalationOut(BaseModel):
    id: int
    from_level: str
    to_level: str
    reason: Optional[str] = None
    created_at: datetime


class StatusHistoryOut(BaseModel):
    id: int
    status: str
    note: Optional[str] = None
    created_at: datetime


class IssueOut(BaseModel):
    id: int
    room_id: Optional[int] = None
    room_name: Optional[str] = None
    main_category: str
    category: str
    title: str
    description: str
    image_url: Optional[str] = None
    reporter_id: Optional[int] = None
    reporter_name: Optional[str] = None
    reporter_room: Optional[str] = None
    current_level: str
    current_assignee_id: Optional[int] = None
    current_assignee_role: Optional[str] = None
    current_assignee_name: Optional[str] = None
    status: str
    priority: str
    is_anonymous: bool
    # 🆕 ปลายทางที่ผู้แจ้งขอ (normal/vote/talk) + board สาธารณะที่สภาอนุมัติแล้ว (ชี้ piri_boards.id)
    requested_destination: str = "normal"
    published_board_id: Optional[int] = None
    resolved_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    # รายละเอียดเสริม (เฉพาะ detail)
    steps: List[IssueStepOut] = []
    countdown: Optional[IssueCountdownOut] = None
    escalations: List[EscalationOut] = []
    status_history: List[StatusHistoryOut] = []
    comments: List[CommentOut] = []


class IssueListOut(BaseModel):
    """รายการเรื่องแบบแบ่งหน้า (Pagination) — total นับก่อน limit/offset"""
    items: List[IssueOut]
    total: int          # จำนวนทั้งหมดที่ตรงเงื่อนไข
    page: int           # 1-based
    page_size: int
    pages: int


class IssueStatusCountOut(BaseModel):
    """จำนวนเรื่องแยกตามสถานะเดียว (zero-fill ให้ครบทุกสถานะ)"""
    status: str
    count: int


class MyIssueSummaryOut(BaseModel):
    """สรุปเรื่องที่ฉันแจ้ง (สำหรับหน้า Home/Welcome) — 1 request แทนการเรียก list หลายครั้ง"""
    total_issues: int                              # จำนวนเรื่องที่ฉันแจ้งทั้งหมด
    by_status: List[IssueStatusCountOut]           # นับแยกตามสถานะทั้ง 6 (zero-fill)
    recent: List[IssueOut]                         # 5 เรื่องล่าสุด (การ์ดบนหน้า Welcome)


# ===================== P5: เรื่องค้างที่ผู้รับหมดวาระ =====================
class ReassignRequest(BaseModel):
    """มอบหมายเรื่องที่ผู้รับเดิมหมดวาระ ให้ผู้รับคนใหม่ (ต้อง active ในปีปัจจุบัน)"""
    to_user_id: int = Field(..., description="users.id ของผู้รับใหม่")
    note: Optional[str] = Field(None, max_length=500)


class OrphanCandidate(BaseModel):
    """ผู้ที่ดำรงตำแหน่งเดียวกันในปีปัจจุบัน — ตัวเลือก 'มอบหมายต่อ'"""
    user_id: int
    full_name: Optional[str] = None
    class_role: str
    room_code: Optional[str] = None


class OrphanedIssueOut(BaseModel):
    """เรื่องที่ยังเปิดอยู่แต่ผู้รับไม่มีสมาชิกภาพในปีปัจจุบัน"""
    id: int
    title: str
    status: str
    current_level: Optional[str] = None
    room_id: Optional[int] = None
    room_code: Optional[str] = None
    assignee_id: int
    assignee_name: Optional[str] = None
    assignee_role: Optional[str] = None
    assignee_old_room_code: Optional[str] = None
    reporter_id: Optional[int] = None
    created_at: Optional[datetime] = None
    candidates: List[OrphanCandidate] = []


class OrphanedAssignmentsOut(BaseModel):
    year_id: int
    items: List[OrphanedIssueOut] = []
    total: int = 0
