"""Schemas ของ "ข้อมูลของฉัน" (C3) — `/api/me/*`

⚠️ ทุก endpoint ในกลุ่มนี้ห้ามรับ `user_id` จาก client เด็ดขาด — เอาจาก JWT เท่านั้น
"""
from datetime import date
from typing import Optional

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
