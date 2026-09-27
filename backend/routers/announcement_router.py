"""Announcement Router — จัดการประกาศหน้า Landing Page (ต้องมีสิทธิ์ MANAGE_ANNOUNCEMENTS)

ชั้นนี้ทำแค่ HTTP: ดึง user จาก header → เรียก service → แปลง domain exception เป็น
HTTPException (ตัวเช็คสิทธิ์อยู่ใน service แล้ว ตามแบบ audit_service)

⚠️ ห้ามย้าย endpoint พวกนี้ไปไว้ใน public_router (prefix /api/v1/public) — ไฟล์นั้น
   มีสัญญาว่า "ไม่ต้องล็อกอิน" ทั้งไฟล์ การเอา mutation ที่ต้องเช็คสิทธิ์โรงเรียนไปแปะ
   จะทำให้คนที่มาอ่านทีหลังเข้าใจผิดว่าไม่ต้องยืนยันตัวตน
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
import asyncpg

from core.dependencies import get_db_pool, get_current_user
from core.exceptions import NotFoundError, ForbiddenError, ValidationError
from models.announcement_schemas import (
    AnnouncementCreateRequest,
    AnnouncementUpdateRequest,
    AnnouncementAdminOut,
    AnnouncementListOut,
)
from services import announcement_service

router = APIRouter(prefix="/announcements", tags=["Announcements"])


def _ensure_user(user_ctx: dict) -> int:
    """ดึง user_id หรือ raise 401"""
    uid = user_ctx.get("user_id")
    if not uid:
        raise HTTPException(status_code=401, detail="ต้องเข้าสู่ระบบ")
    return uid


def _err(e: Exception) -> HTTPException:
    """แปลง domain exception → HTTPException (pattern เดียวกับ boards/issue router)"""
    if isinstance(e, NotFoundError):
        return HTTPException(status_code=404, detail=str(e))
    if isinstance(e, ForbiddenError):
        return HTTPException(status_code=403, detail=str(e))
    if isinstance(e, ValidationError):
        return HTTPException(status_code=400, detail=str(e))
    return HTTPException(status_code=500, detail=f"เกิดข้อผิดพลาด: {e}")


@router.get("", response_model=AnnouncementListOut)
async def list_announcements(
    status: str = Query(
        "active",
        pattern="^(active|deleted|all)$",
        description="กรองสถานะ: active (ยังใช้อยู่) / deleted (ถูกลบ) / all (ทั้งหมด)",
    ),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """รายการประกาศทั้งหมด (หน้า admin) — เรียง urgent → high → normal แล้วใหม่สุดก่อน"""
    uid = _ensure_user(user_ctx)
    try:
        result = await announcement_service.list_announcements(
            pool, uid, status=status, limit=limit, offset=offset
        )
    except (ForbiddenError, ValidationError) as e:
        raise _err(e)

    return AnnouncementListOut(
        items=[AnnouncementAdminOut(**i) for i in result["items"]],
        total=result["total"],
        page=result["page"],
        page_size=result["page_size"],
        pages=result["pages"],
    )


@router.post("", response_model=AnnouncementAdminOut, status_code=201)
async def create_announcement(
    req: AnnouncementCreateRequest,
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """สร้างประกาศใหม่ — จะปรากฏบน Landing Page ทันที"""
    uid = _ensure_user(user_ctx)
    try:
        row = await announcement_service.create_announcement(
            pool, uid, message=req.message, priority=req.priority, link=req.link
        )
    except (ForbiddenError, ValidationError) as e:
        raise _err(e)

    return AnnouncementAdminOut(**row)


@router.patch("/{announcement_id}", response_model=AnnouncementAdminOut)
async def update_announcement(
    announcement_id: int,
    req: AnnouncementUpdateRequest,
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """แก้ประกาศ — ส่งเฉพาะฟิลด์ที่จะแก้ (ไม่ส่ง = ไม่แตะ)"""
    uid = _ensure_user(user_ctx)
    changes = req.model_dump(exclude_unset=True)
    try:
        row = await announcement_service.update_announcement(
            pool, uid, announcement_id, changes
        )
    except (NotFoundError, ForbiddenError, ValidationError) as e:
        raise _err(e)

    return AnnouncementAdminOut(**row)


@router.delete("/{announcement_id}", response_model=AnnouncementAdminOut)
async def delete_announcement(
    announcement_id: int,
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """ลบประกาศ (soft delete) — หายจาก Landing Page แต่ข้อมูลยังอยู่ กู้คืนได้"""
    uid = _ensure_user(user_ctx)
    try:
        row = await announcement_service.delete_announcement(pool, uid, announcement_id)
    except (NotFoundError, ForbiddenError) as e:
        raise _err(e)

    return AnnouncementAdminOut(**row)


@router.post("/{announcement_id}/restore", response_model=AnnouncementAdminOut)
async def restore_announcement(
    announcement_id: int,
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """กู้คืนประกาศที่ถูกลบ — กลับมาแสดงบน Landing Page อีกครั้ง"""
    uid = _ensure_user(user_ctx)
    try:
        row = await announcement_service.restore_announcement(pool, uid, announcement_id)
    except (NotFoundError, ForbiddenError) as e:
        raise _err(e)

    return AnnouncementAdminOut(**row)
