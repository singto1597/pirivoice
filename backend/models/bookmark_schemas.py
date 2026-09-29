"""Schemas ของ "บันทึกไว้อ่านทีหลัง" (C2)

⚠️ **ไม่มีฟิลด์ `user_id` ใน schema ใด ๆ โดยเจตนา** — ตัวตนมาจาก JWT เท่านั้น
   และเพราะ pydantic ตัดฟิลด์ที่ไม่ประกาศทิ้งอัตโนมัติ ⇒ ถ้าผู้ใช้ส่ง `{"user_id": 999}`
   มาใน body มันจะถูกทิ้งเงียบ ๆ ไม่ใช่ถูกใช้ (มีเทสต์ B10/S-style คุมไว้)
"""
from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

# ⚠️ ชุดเดียวกับ `BookmarkEntityType` ฝั่ง frontend (`types/bookmark.ts`)
#    และ **ไม่มี CHECK ที่ DB โดยเจตนา** (ดู migration 021) ⇒ ที่นี่คือด่านเดียว
#    ⇒ เพิ่มชนิดใหม่ (D1 `'event'`) แก้ที่บรรทัดนี้ + `_EXISTS_SQL` ใน service
BookmarkEntityType = Literal["issue", "board"]


class BookmarkCreateRequest(BaseModel):
    """★ ไม่มี `user_id` — เอาจาก JWT"""

    entity_type: BookmarkEntityType
    entity_id: int = Field(gt=0)


class BookmarkOut(BaseModel):
    id: int
    entity_type: BookmarkEntityType
    entity_id: int
    created_at: datetime


class BookmarkItemOut(BaseModel):
    """แถวในลิสต์ — `title`/`excerpt` มาจาก join กลับไปหาต้นทาง"""

    id: int
    entity_type: BookmarkEntityType
    entity_id: int
    title: str
    excerpt: Optional[str] = None
    created_at: datetime
    # ต้นทางถูก soft delete ⇒ **frontend ต้องไม่ลิงก์** (กดไปจะ 404)
    is_deleted_source: bool


class BookmarkListOut(BaseModel):
    items: List[BookmarkItemOut]
    total: int
    page: int
    page_size: int
    pages: int


class BookmarkStatusOut(BaseModel):
    bookmarked: bool
    # id ที่ใช้ลบ — `None` เมื่อยังไม่บันทึก
    bookmark_id: Optional[int] = None
