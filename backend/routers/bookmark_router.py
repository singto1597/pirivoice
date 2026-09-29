"""Bookmark Router — "บันทึกไว้อ่านทีหลัง" (`/api/bookmarks`)

ชั้นนี้ทำแค่ HTTP: ดึง user จาก JWT → เรียก service → แปลง exception เป็น HTTPException

⚠️ **ไม่ต้องมี `require_permission`** — ข้อมูลของเจ้าของบัญชีล้วน (ตัวตนคือสิทธิ์)
   แต่ **ต้อง** กันด้วย `_ensure_user()` เพราะ `get_current_user` คืน `user_id = None`
   เมื่อถูกเรียกด้วย `X-API-Key` (system RPC) ⇒ ถ้าไม่กันจะสร้าง bookmark ของ user NULL
   แล้วพังด้วย FK violation = **500 แทนที่จะเป็น 401**

⚠️ **ห้ามรับ `user_id` จาก client** ทุกกรณี — เอาจาก `user_ctx` เท่านั้น

⭐ **POST เป็น idempotent** — 201 เมื่อเพิ่งบันทึก · **200 เมื่อมีอยู่แล้ว** (ไม่ใช่ 409)
   `bookmark` คือ "อยู่ในชุดที่บันทึก" ไม่ใช่การลงคะแนน ⇒ กดซ้ำต้องไม่เป็น error
   (ดับเบิลแท็ป / เน็ตช้า / ผู้ใช้กดสองแท็บ) — ดูเหตุผลเต็มใน plan §22.2 ข้อ 3
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
import asyncpg

from core.dependencies import get_db_pool, get_current_user
from core.exceptions import NotFoundError, ForbiddenError, ValidationError, ConflictError
from models.bookmark_schemas import (
    BookmarkCreateRequest,
    BookmarkListOut,
    BookmarkOut,
    BookmarkStatusOut,
    BookmarkEntityType,
)
from services import bookmark_service

router = APIRouter(prefix="/bookmarks", tags=["Bookmarks"])


def _ensure_user(user_ctx: dict) -> int:
    """ดึง user_id หรือ raise 401 (ไม่ใช่ 500)"""
    uid = user_ctx.get("user_id")
    if not uid:
        raise HTTPException(status_code=401, detail="ต้องเข้าสู่ระบบ")
    return uid


def _err(e: Exception):
    """แปลง domain exception → HTTPException (รูปเดียวกับ issue_router._err)"""
    if isinstance(e, NotFoundError):
        return HTTPException(status_code=404, detail=str(e))
    if isinstance(e, ForbiddenError):
        return HTTPException(status_code=403, detail=str(e))
    if isinstance(e, ValidationError):
        return HTTPException(status_code=400, detail=str(e))
    if isinstance(e, ConflictError):
        return HTTPException(status_code=409, detail=str(e))
    return HTTPException(status_code=500, detail=f"เกิดข้อผิดพลาด: {e}")


# ⚠️ `/status` ต้องประกาศ **ก่อน** route ที่มี path param ถ้ามี — ที่นี่ path param
#    อยู่คนละ method (DELETE) จึงไม่ชนกัน แต่เรียงไว้ก่อนเพื่อไม่ให้วันหน้ามีคนเพิ่ม
#    `GET /{id}` แล้ว `/status` ถูกกลืนเป็น id="status"
@router.get("/status", response_model=BookmarkStatusOut)
async def get_bookmark_status(
    entity_type: BookmarkEntityType = Query(..., description="'issue' หรือ 'board'"),
    entity_id: int = Query(..., gt=0),
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """สถานะของ entity เดียว — ให้ปุ่มไอคอนรู้ว่าจะวาดติ๊กหรือไม่"""
    uid = _ensure_user(user_ctx)
    try:
        return await bookmark_service.get_status(
            pool, uid, entity_type=entity_type, entity_id=entity_id
        )
    except Exception as e:  # noqa: BLE001 — แปลงเป็น HTTP ที่ชั้นนี้ (กฎ layering)
        raise _err(e)


@router.get("", response_model=BookmarkListOut)
async def list_bookmarks(
    entity_type: Optional[BookmarkEntityType] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """รายการที่ฉันบันทึกไว้ (ล่าสุดก่อน) — กรองตามชนิดได้"""
    uid = _ensure_user(user_ctx)
    try:
        return await bookmark_service.list_bookmarks(
            pool, uid, entity_type=entity_type, limit=limit, offset=offset
        )
    except Exception as e:  # noqa: BLE001
        raise _err(e)


@router.post("", response_model=BookmarkOut)
async def create_bookmark(
    req: BookmarkCreateRequest,
    response: Response,
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """บันทึก — **idempotent**: 201 = เพิ่งบันทึก · 200 = มีอยู่แล้ว (ไม่ใช่ 409)

    ⚠️ `user_id` มาจาก JWT เท่านั้น — `BookmarkCreateRequest` ไม่มีฟิลด์นี้
       ⇒ ถ้าส่งมาใน body จะถูก pydantic ทิ้ง
    """
    uid = _ensure_user(user_ctx)
    try:
        created, bookmark = await bookmark_service.create_bookmark(
            pool, uid, entity_type=req.entity_type, entity_id=req.entity_id
        )
    except Exception as e:  # noqa: BLE001
        raise _err(e)
    # 201 เฉพาะตอน "เพิ่งเกิด" จริง — status code คือคำตอบว่า created หรือไม่
    # (ไม่ส่งฟิลด์ `created` ซ้ำใน body — ซ้ำซ้อนและไม่มีใครใช้)
    response.status_code = 201 if created else 200
    return bookmark


@router.delete("/{bookmark_id}", status_code=204)
async def delete_bookmark(
    bookmark_id: int,
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """เลิกบันทึก — ลบได้เฉพาะของตัวเอง (404 ถ้าไม่ใช่ของตัวเอง — ไม่บอกว่ามีอยู่จริง)"""
    uid = _ensure_user(user_ctx)
    try:
        await bookmark_service.delete_bookmark(pool, uid, bookmark_id)
    except Exception as e:  # noqa: BLE001
        raise _err(e)
