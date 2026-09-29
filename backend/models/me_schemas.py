"""Schemas ของ "ข้อมูลของฉัน" (C3) — `/api/me/*`

⚠️ ทุก endpoint ในกลุ่มนี้ห้ามรับ `user_id` จาก client เด็ดขาด — เอาจาก JWT เท่านั้น
"""
from datetime import date, datetime
from typing import List, Literal, Optional

from pydantic import BaseModel


class PersonalStatsTermOut(BaseModel):
    """ภาคที่ใช้กรองสถิติชุดนี้ — `None` = ยังไม่ได้ตั้งภาค ⇒ นับทั้งหมด"""

    id: int
    name: str
    start_date: date
    end_date: date  # ★ inclusive (รวมวันสุดท้าย)


class PersonalStatsOut(BaseModel):
    """สถิติส่วนตัว 6 ตัวเลข — แยกคอมเมนต์บอร์ด/คอมเมนต์เรื่องโดยเจตนา

    เพราะ C1 (My Activity) จะต้องใช้ชุดตัวนับเดียวกัน — ถ้ารวมเป็น `comments_posted`
    ตัวเดียว วันหน้าเลขจะไม่ตรงกันแล้วดูเหมือนบั๊ก
    """

    term: Optional[PersonalStatsTermOut] = None

    total_reported: int  # เรื่องที่ฉันแจ้ง (ทั้งหมด)
    resolved_count: int  # …ที่ปิดสำเร็จแล้ว
    in_progress_count: int  # …ที่ยังดำเนินอยู่ (pending/in_progress/escalated)
    votes_cast: int  # โหวตใน PIRI Boards
    board_comments_posted: int  # คอมเมนต์ใน PIRI Boards
    issue_comments_posted: int  # คอมเมนต์ในเรื่อง


# ─────────────────────────────────────────────────────────────
# 🧭 C1 — กิจกรรมของฉัน (`GET /api/me/activity`)
#
# ⚠️ **ไม่กรองตามภาคเรียนโดยเจตนา** ต่างจาก C3 — C1 คือ "ทุกอย่างที่เคยทำ"
#    แต่ **ยอดต่อประเภทต้องเท่ากับตัวนับของ C3 ทีละตัว** ตามที่ docstring ของ
#    `PersonalStatsOut` ข้างบนเขียนเตือนไว้ (มีเทสต์ A2 ใน `test_me_activity.py` บังคับ)
# ─────────────────────────────────────────────────────────────

# ⚠️ ชุดนี้ต้องตรงกับ **2 ที่**: `ACTIVITY_TYPES` ใน `services/me_service.py`
#    และ `ActivityType` ใน `frontend/src/types/me.ts`
#    ⇒ ฝั่ง Python มีเทสต์ A13 บังคับว่าสองที่ตรงกัน (ไม่พึ่งความจำ)
ActivityType = Literal[
    "issue_created",
    "vote_cast",
    "board_comment_posted",
    "issue_comment_posted",
]

# ชนิดของ "ต้นทาง" ที่กิจกรรมชี้ไป — ใช้ทำลิงก์ (`/app/issues/:id` หรือ `/app/boards/:id`)
# ⚠️ ชุดเดียวกับ `BookmarkEntityType` (`bookmark_schemas.py`) และ `ENTITY_TYPES` (FE)
ActivityEntityType = Literal["issue", "board"]


class ActivityItemOut(BaseModel):
    """1 เหตุการณ์ใน timeline — รูปเดียวกันทุกประเภท (ให้ frontend เรนเดอร์ด้วย component เดียว)"""

    activity_type: ActivityType
    entity_type: ActivityEntityType
    # id ของเรื่อง/บอร์ด — ใช้ทำลิงก์
    entity_id: int
    # id ของแถวต้นทาง (issue/vote/comment) — **ใช้เป็น key ของ v-for**
    # เพราะ `entity_id` ซ้ำกันข้ามประเภทได้ (เรื่อง #7 กับบอร์ด #7)
    src_id: int
    title: str
    # ⚠️ ความหมาย **ขึ้นกับ `activity_type`** — ดูคอมเมนต์ใน `types/me.ts`:
    #    `issue_created` → สถานะของเรื่อง · `vote_cast` → ข้อความตัวเลือก · คอมเมนต์ → null
    meta: Optional[str] = None
    excerpt: Optional[str] = None  # ตัด 160 ตัวอักษรที่ SQL (`LEFT()` นับตัวอักษร ไม่ใช่ byte)
    created_at: datetime
    # ต้นทางถูก soft delete ⇒ frontend **ต้องไม่ลิงก์** (กดไปจะ 404)
    is_deleted_source: bool


class ActivityCountsOut(BaseModel):
    """ยอดแยกประเภท — **ประกาศครบทุกประเภทเสมอ** (zero-fill) ไม่ใช่ dict อิสระ

    ⭐ **ทำไมไม่ใช้ `Dict[str, int]`** — dict เปิดกว้างจนตรวจ drift ไม่ได้: ถ้ามีคนเพิ่ม
       ประเภทที่ 5 ใน `me_service.ACTIVITY_TYPES` แล้วลืมเพิ่มที่นี่ `Dict` จะเงียบ
       (ผ่านทุกอย่าง) ส่วนโมเดลนี้ **บังคับให้เทสต์ A13 จับได้ทันที** ว่าสองที่ตกหล่น
       ⇒ แลกความยืดหยุ่นที่ไม่จำเป็น กับด่านที่จับ drift ได้จริง

    และต้อง zero-fill (ประเภทที่ไม่มีข้อมูลได้ `0` ไม่ใช่หายไปจาก response)
    ไม่งั้นป้ายตัวกรองฝั่ง frontend จะแสดง `undefined`
    """

    issue_created: int
    vote_cast: int
    board_comment_posted: int
    issue_comment_posted: int


class ActivityListOut(BaseModel):
    """envelope เดียวกับ `NotificationListOut` / `BookmarkListOut`"""

    items: List[ActivityItemOut]
    total: int  # ยอดของ **ประเภทที่กรอง** (ถ้ากรอง) — ไม่ใช่ยอดรวมเสมอ
    page: int
    page_size: int
    pages: int
    counts: ActivityCountsOut  # ยอดของ **ทุกประเภท** เสมอ (ไม่สนใจ filter) ⇒ ใช้ทำป้าย
