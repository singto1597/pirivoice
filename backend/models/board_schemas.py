"""
PIRI Boards — Pydantic v2 Schemas (PIRI Vote + PIRI Talk)

แบ่งเป็น 2 กลุ่ม:
- Request: VoteSubmitRequest (โหวต), CommentCreateRequest (คอมเมนต์)
- Response: BoardSummaryOut (รายการ), BoardDetailOut (รายละเอียด), BoardCommentOut (threaded)

หมายเหตุ: `response_model` ทำหน้าที่กรอง field หวงห้าม (เช่น อย่าให้ secret รั่ว) ตามกฎ backend.md
"""
from typing import Optional, List
from pydantic import BaseModel, Field, field_validator
from datetime import datetime

# หมวดเหตุผลที่แจ้งความไม่เหมาะสมได้ (ตรงกับ piri_board_reports.reason CHECK + service)
REPORT_REASONS = ("bullying", "profanity", "spam", "privacy", "other")


# ===================== Request =====================
class VoteSubmitRequest(BaseModel):
    """ส่งเสียงโหวต — ผู้ใช้โหวตได้ 1 เสียงต่อ board (โหวตซ้ำ → 409)"""
    choice_id: int = Field(..., description="ตัวเลือกที่โหวต (id ใน piri_vote_choices)")


class CommentCreateRequest(BaseModel):
    """คอมเมนต์/รีพลายใน board (PIRI Talk + ข้อเสนอแนะ)"""
    body: str = Field(..., min_length=1, max_length=1000)
    parent_id: Optional[int] = Field(None, description="reply ต่อคอมเมนต์ (id ของคอมเมนต์ต้นทาง)")


class SuggestionCreateRequest(BaseModel):
    """💡 E1 — ผู้ใช้เสนอไอเดียเอง (board ชนิด 'suggestion') — ฟอร์มสั้น แค่หัวข้อ + รายละเอียด

    ⚠️ **ไม่มีฟิลด์ `board_type` โดยเจตนา** — endpoint นี้สร้างได้ **ชนิดเดียว** เท่านั้น
    ถ้าเปิดให้ส่ง `board_type` มาจะกลายเป็นช่องเลี่ยงด่านอนุมัติของสภาสำหรับ `talk`/`vote`
    (บอร์ดสองชนิดนั้นต้องเกิดจาก `issue_service.approve_to_public()` เท่านั้น)
    ⇒ ชนิดถูกกำหนดเป็น literal ที่ service — ไม่ใช่ค่าที่ client เลือกได้

    ⚠️ **ไม่มีฟิลด์ `user_id`** — เจ้าของคือผู้ถือ token (pattern เดียวกับ bookmark/push:
    pydantic ตัดทิ้งอัตโนมัติถ้าส่งมา ⇒ มีเทสต์ยืนยันว่าไม่รั่วข้ามคน)

    ⚠️ **ไม่รับ `cover_image_url`** — ยังไม่มีช่องอัปโหลดในฟอร์มสั้นโดยเจตนา (ผู้ใช้ขอ "ฟอร์มสั้น")
    ถ้าวันหน้าจะเพิ่ม ต้องคิดเรื่อง moderation ของรูปก่อน (ตอนนี้ `approve_to_public` คัดรูปมา
    จาก issue ที่ผ่านสายตาสภาแล้ว ซึ่งเป็นด่านที่ E1 ไม่มี)
    """
    title: str = Field(..., min_length=3, max_length=200, description="หัวข้อข้อเสนอ")
    description: str = Field(..., min_length=1, max_length=2000, description="รายละเอียด")
    is_anonymous: bool = Field(False, description="แสดงชื่อหรือไม่ (True = ซ่อนชื่อผู้เสนอ)")


# ===================== Response =====================
class VoteChoiceOut(BaseModel):
    """ตัวเลือกโหวต 1 อัน (มี vote_count เพื่อคำนวณ % บน frontend)"""
    id: int
    choice_text: str
    description: Optional[str] = None
    image_url: Optional[str] = None
    sort_order: int
    vote_count: int


class VoteResultOut(BaseModel):
    """ผลการโหวต — typed response (ไม่ใช่ dict เปล่า) ตามกฎ response_model กรอง field หวงห้าม"""
    status: str
    vote_id: int
    board_id: int
    choice_id: int
    choice_text: str


class BoardCommentOut(BaseModel):
    """คอมเมนต์ใน board — แบบ threaded (replies ซ้อนกัน; ความลึกถูกจำกัดฝั่ง service
    กัน recursive Pydantic overflow — reply ลึกเกินถูกพับใต้บรรพบุรุษ, ไม่หาย)"""
    id: int
    parent_comment_id: Optional[int] = None
    user_id: Optional[int] = None
    commenter_name: Optional[str] = None
    commenter_first_name: Optional[str] = None  # ชื่อจริง (avatar ใช้ตัวแรกของชื่อ) — fallback commenter_name
    body: str
    is_edited: bool = False
    created_at: datetime
    updated_at: Optional[datetime] = None
    replies: List["BoardCommentOut"] = []


class BoardSummaryOut(BaseModel):
    """การ์ด board ใน feed — ไม่มี pyramid visibility (ข้อมูลสาธารณะ)"""
    id: int
    board_type: str
    title: str
    description: str
    cover_image_url: Optional[str] = None
    source_issue_id: Optional[int] = None
    author_id: Optional[int] = None
    author_name: Optional[str] = None          # None ถ้า board anonymous (is_anonymous=True)
    is_anonymous: bool
    comment_count: int
    view_count: int
    status: str
    tags: List[str] = []
    total_votes: int = 0                       # เฉพาะ vote board (รวมทุก choice) — ให้การ์ดโชว์ยอด
    created_at: datetime


class BoardDetailOut(BoardSummaryOut):
    """รายละเอียด board — vote: choices + my_vote; talk: comments (threaded)"""
    allow_comments: bool
    my_vote_choice_id: Optional[int] = None    # board ที่ user โหวตแล้ว (ชี้ choice_id) — ใช้ highlight ปุ่ม
    choices: List[VoteChoiceOut] = []
    comments: List[BoardCommentOut] = []


class BoardListOut(BaseModel):
    """feed แบบแบ่งหน้า (pattern เดียวกับ /issues)"""
    items: List[BoardSummaryOut]
    total: int
    page: int
    page_size: int
    pages: int


class SuggestionCreatedOut(BaseModel):
    """ผลของการสร้างข้อเสนอ (E1) — **ไม่คืนรายละเอียดเต็ม** โดยเจตนา

    เหตุผลที่แยกจาก `BoardSummaryOut`: `GET /boards/{id}` มี **ผลข้างเคียง** คือ `view_count += 1`
    (dedup 10 นาที) ⇒ ถ้า POST คืน detail ผู้สร้างจะ "นับวิวให้ตัวเอง" ทุกครั้งที่กดส่ง
    ⇒ คืนแค่สิ่งที่ client ต้องใช้ตัดสินใจ (id สำหรับพาไปหน้า detail + title ให้ toast อ่านรู้เรื่อง)
    แล้วให้ client ยิง `GET /boards/{id}` เองถ้าต้องการรายละเอียด — วิวจะถูกนับตอนนั้น
    ซึ่งตรงกับความหมายของ "มีคนเปิดดู" มากกว่า
    """
    id: int
    board_type: str
    title: str
    created_at: datetime


# ===================== Moderation / Report (Phase 5) =====================
class ReportCreateRequest(BaseModel):
    """🚩 นักเรียนแจ้งความไม่เหมาะสมของคอมเมนต์ (PIRI Talk)"""
    reason: str = Field(..., description="เหตุผล: bullying/profanity/spam/privacy/other")
    detail: Optional[str] = Field(None, max_length=500, description="รายละเอียดเพิ่มเติม (ไม่บังคับ)")

    @field_validator("reason")
    @classmethod
    def _check_reason(cls, v: str) -> str:
        if v not in REPORT_REASONS:
            raise ValueError(f"เหตุผลการแจ้งไม่ถูกต้อง: {v} (ต้องเป็นหนึ่งใน {', '.join(REPORT_REASONS)})")
        return v


class HideCommentRequest(BaseModel):
    """🛡️ สภา/แอดมินซ่อนคอมเมนต์ (จำเป็นต้องระบุเหตุผล — เขียน audit)"""
    reason: str = Field(..., min_length=1, max_length=200)


class HideBoardRequest(BaseModel):
    """🛡️ สภา/แอดมินซ่อน board ทั้งบอร์ด"""
    reason: str = Field(..., min_length=1, max_length=200)


class ResolveReportRequest(BaseModel):
    """✅ จัดการรายงาน: action='hide' (ซ่อนคอมเมนต์) / 'dismiss' (ปัดตก ไม่ซ่อน)"""
    action: str = Field(..., description="hide (ซ่อนคอมเมนต์) / dismiss (ปัดตก)")
    note: Optional[str] = Field(None, max_length=500, description="หมายเหตุ (ไม่บังคับ)")

    @field_validator("action")
    @classmethod
    def _check_action(cls, v: str) -> str:
        if v not in ("hide", "dismiss"):
            raise ValueError(f"การจัดการไม่ถูกต้อง: {v} (ต้องเป็น hide/dismiss)")
        return v


class ReportOut(BaseModel):
    """รายงาน 1 รายการในคิว (สภา/แอดมิน) — รวมชื่อ board + เนื้อความคอมเมนต์ + ผู้แจ้ง"""
    id: int
    board_id: int
    board_title: str
    comment_id: int
    comment_body: str
    reporter_id: Optional[int] = None
    reporter_name: Optional[str] = None
    reason: str
    detail: Optional[str] = None
    status: str
    resolved_by: Optional[int] = None
    resolved_at: Optional[datetime] = None
    resolution_note: Optional[str] = None
    created_at: datetime


class ReportListOut(BaseModel):
    """คิวรายงานแบบแบ่งหน้า"""
    items: List[ReportOut]
    total: int
    page: int
    page_size: int
    pages: int


BoardCommentOut.model_rebuild()
