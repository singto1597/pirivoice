"""Schemas ของหน้าแรก (B1) — `/api/home/summary`

ทุกอย่างที่ `Home.vue` ต้องใช้ใน **call เดียว** — ประกอบจากของที่มีอยู่แล้วเป็นหลัก
(`AnnouncementOut`, `MyIssueSummaryOut`, `PersonalStatsOut`) ไม่ประกาศซ้ำ
"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel

from models.issue_schemas import MyIssueSummaryOut
from models.me_schemas import PersonalStatsOut
from models.public_schemas import AnnouncementOut


class PendingOnMeItem(BaseModel):
    """เรื่องที่ `current_assignee_id` เป็นฉันและยังไม่จบ — "รอฉันตอบ"

    ⚠️ เป้าแคบกว่า `GET /api/issues?received=true` โดยเจตนา — ตัวนั้นรวมเรื่องที่ฉัน
    แค่ไปเกี่ยวข้อง (เป็นผู้แจ้ง / มี countdown ของฉัน) ซึ่งไม่ใช่ "ต้องรอฉันตอบ"
    """

    id: int
    title: str
    status: str
    priority: str
    current_level: str
    created_at: datetime
    room_name: Optional[str] = None  # LEFT JOIN rooms — issue อาจไม่มีห้อง (NULL ได้)


class UnvotedBoardItem(BaseModel):
    """บอร์ดโหวตที่ยังเปิดอยู่และฉันยังไม่ได้โหวต — "โหวตที่ยังไม่โหวต" """

    id: int
    title: str
    created_at: datetime
    vote_count: int  # จำนวนโหวตของทั้งบอร์ด (ไม่ใช่ของฉัน) — ให้เห็นว่าคนอื่นสนใจแค่ไหน


class ClosingSoonEventItem(BaseModel):
    """กิจกรรมที่ยังเปิดรับและกำลังจะปิดรับ — "กิจกรรมใกล้ปิดรับ" (4.5)

    ⭐ **ไม่ใช่ `EventPublicOut` โดยเจตนา** — บล็อกในหน้าแรกเป็น *สรุป* ไม่ใช่หน้ารายการ
       ⇒ `EventPublicOut` ลาก `description` / `cover_image_url` / ตัวนับอีก 4 ตัว
       ที่การ์ดนี้ไม่ได้ใช้เข้ามาด้วย · ประกาศเป็น schema ของตัวเองทำให้การเพิ่มฟิลด์
       ฝั่ง detail ไม่ทำให้หน้าแรกหนักขึ้นโดยไม่มีใครตั้งใจ

    ⚠️ **ไม่มี `is_registration_open`** — คิวรีที่ดึงมาเข้าเงื่อนไข "ยังเปิดรับ" อยู่แล้ว
       ⇒ ค่าจะเป็น `true` ทุกแถวเสมอ ⇒ ฟิลด์ที่ไม่เคยเป็นเท็จคือฟิลด์ที่คนอ่านโค้ด
       จะเข้าใจผิดว่ามีกรณีเท็จ (และมีคนเขียน `if` กันไว้ ซึ่งไม่มีวันทำงาน)
    """

    id: int
    title: str
    location: Optional[str] = None
    event_date: datetime
    closes_at: datetime  # min(วันจัด, กำหนดปิดรับ) — คำนวณที่ SQL · NULL ไม่ได้ (ดูเหตุผลใน EventPublicOut)
    # `None` = ไม่จำกัดจำนวน (ไม่ใช่ 0) — 0 แปลว่าเต็ม ⇒ ฝั่งจอต้องเช็ค `=== null` ก่อนเทียบ
    seats_remaining: Optional[int] = None
    # "registered" / "checked_in" / None — คนละความหมายกับ `seats_remaining`
    # ⇒ จอใช้ตัดสินว่าแถวนี้ควรมี *ปุ่มสมัคร* หรือ *ป้าย "สมัครแล้ว"*
    my_registration_status: Optional[str] = None


class HomeSummaryOut(BaseModel):
    """ก้อนเดียวจบของหน้าแรก

    ⚠️ `announcements` **ไม่ถูกตัด** — `get_announcements()` ไม่มี LIMIT โดยเจตนา
    ของเจ้าของระบบ ("โชว์ทั้งหมดที่ยังไม่ถอดออก")

    ❌ ไม่มีแดชบอร์ดและคิวรายงานอยู่ในนี้โดยเจตนา — ทั้งคู่เป็น permission-gated
    และแดชบอร์ดรัน aggregate หนักทั้งโรงเรียน ⇒ ย้ายเข้ามาจะทำให้ Home ช้าลงทุกคน
    """

    announcements: List[AnnouncementOut]
    my_issues: MyIssueSummaryOut
    pending_on_me: List[PendingOnMeItem]
    pending_on_me_total: int  # ยอดจริง (ไม่จำกัด QUEUE_LIMIT) — ใช้ขึ้น "และอีก N เรื่อง"
    unvoted_boards: List[UnvotedBoardItem]
    unvoted_boards_total: int
    # กิจกรรมใกล้ปิดรับ (4.5) — คิวที่ 3 ต่อจากสองคิวก่อน
    # ⚠️ **ไม่กรองตามการสมัครของฉัน** (ดูเหตุผลใน `list_closing_soon_events`) ⇒ บล็อกนี้
    #    มีของให้เห็นได้แม้สมัครไปหมดแล้ว — ซึ่งเป็นตอนที่มันมีค่าที่สุด ("อย่าลืมไป")
    closing_soon_events: List[ClosingSoonEventItem]
    closing_soon_events_total: int
    stats: PersonalStatsOut
