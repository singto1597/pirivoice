from fastapi import APIRouter, Depends, HTTPException, Query
import asyncpg

from core.dependencies import get_db_pool, get_current_user
from core.exceptions import ValidationError
from models.notification_schemas import (
    NotificationListOut, NotificationOut, UnreadCountsOut,
    MarkReadRequest, MarkReadOut,
    NotificationPreferencesOut, UpdateNotificationPreferencesRequest,
)
from services import notification_service

router = APIRouter(prefix="/notifications", tags=["Notifications"])

GROUP_TYPE_PATTERN = "^(issue_mine|issue_received|board|report)$"


def _ensure_user(user_ctx: dict) -> int:
    """ดึง user_id หรือ raise 401"""
    uid = user_ctx.get("user_id")
    if not uid:
        raise HTTPException(status_code=401, detail="ต้องเข้าสู่ระบบ")
    return uid


def _err(e: Exception):
    if isinstance(e, ValidationError):
        return HTTPException(status_code=400, detail=str(e))
    return HTTPException(status_code=500, detail=f"เกิดข้อผิดพลาด: {e}")


@router.get("", response_model=NotificationListOut)
async def list_notifications(
    group_type: str | None = Query(None, pattern=GROUP_TYPE_PATTERN),
    unread_only: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    uid = _ensure_user(user_ctx)
    result = await notification_service.list_notifications(
        pool, uid,
        group_type=group_type, unread_only=unread_only,
        limit=limit, offset=offset,
    )
    return NotificationListOut(
        items=[NotificationOut(**i) for i in result["items"]],
        total=result["total"], page=result["page"],
        page_size=result["page_size"], pages=result["pages"],
    )


@router.get("/unread-count", response_model=UnreadCountsOut)
async def unread_counts(
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    uid = _ensure_user(user_ctx)
    return await notification_service.get_unread_counts(pool, uid)


@router.post("/read", response_model=MarkReadOut)
async def mark_read(
    req: MarkReadRequest,
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    uid = _ensure_user(user_ctx)
    try:
        updated = await notification_service.mark_read(
            pool, uid,
            ids=req.ids, group_type=req.group_type,
            entity_type=req.entity_type, entity_id=req.entity_id,
            board_id=req.board_id, all_=req.read_all,
        )
    except ValidationError as e:
        raise _err(e)
    return MarkReadOut(updated=updated)


@router.get("/preferences", response_model=NotificationPreferencesOut)
async def get_preferences(
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """ค่าตั้งค่าการแจ้งเตือนของฉัน — คืนครบทั้ง 4 กลุ่มเสมอ"""
    uid = _ensure_user(user_ctx)
    return await notification_service.get_preferences(pool, uid)


@router.put("/preferences", response_model=NotificationPreferencesOut)
async def update_preferences(
    req: UpdateNotificationPreferencesRequest,
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """ปิด/เปิดการแจ้งเตือนรายกลุ่ม — partial update (กลุ่มที่ไม่ส่งมาคงค่าเดิม)

    ใช้ PUT ไม่ใช่ PATCH เพราะ client ส่ง "สถานะที่ต้องการ" ของกลุ่มที่แสดงอยู่ครบชุด
    และ endpoint นี้ idempotent — ส่งซ้ำด้วยค่าเดิมได้ผลเท่าเดิม"""
    uid = _ensure_user(user_ctx)
    try:
        return await notification_service.update_preferences(
            pool, uid, [p.model_dump() for p in req.preferences]
        )
    except ValidationError as e:
        raise _err(e)
