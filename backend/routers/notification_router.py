from fastapi import APIRouter, Depends, HTTPException, Query, Request
import asyncpg

from core.dependencies import get_db_pool, get_current_user
from core.exceptions import ValidationError
from models.notification_schemas import (
    NotificationListOut, NotificationOut, UnreadCountsOut,
    MarkReadRequest, MarkReadOut,
    NotificationPreferencesOut, UpdateNotificationPreferencesRequest,
    PushStatusOut, PushSubscribeOut, PushSubscriptionIn,
    PushUnsubscribeIn, PushUnsubscribeOut,
)
from services import notification_service, push_service

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


# ============================================================
# 🔔 Web Push (A3)
# ------------------------------------------------------------
# ⚠️ **ไม่ต้องมี `require_permission` เลย** — ทั้งสาม route เป็น "การตั้งค่าส่วนตัว"
#    ตัวตนคือสิทธิ์ (แบบเดียวกับ `/api/me/stats` และ `/api/issues/summary`)
#    ผู้ใช้แก้ได้เฉพาะปลายทางของ *ตัวเอง* เพราะ `user_id` มาจาก JWT เสมอ
#    ⇒ ไม่ต้อง backfill permission และไม่ต้องแตะ `rbac.py`/`roles.json`
# ============================================================

@router.get("/push/status", response_model=PushStatusOut)
async def push_status(
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """สถานะ push ของฉัน + VAPID public key ที่เบราว์เซอร์ต้องใช้ subscribe

    ⭐ **public key ต้องเสิร์ฟจากที่นี่ ไม่ใช่ฝังตอน build frontend**
       เพราะ `docker build` ของ frontend ไม่อ่าน root `.env` (รับ build-arg ตัวเดียว
       คือ `VITE_API_BASE_URL`) ⇒ ถ้าฝังตอน build จะต้อง rebuild image ทุกครั้งที่
       rotate key และ staging/production จะได้คีย์เดียวกันโดยแยกไม่ออก
    """
    uid = _ensure_user(user_ctx)
    return await push_service.get_status(pool, uid)


@router.post("/push/subscribe", response_model=PushSubscribeOut)
async def push_subscribe(
    req: PushSubscriptionIn,
    request: Request,
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """บันทึกปลายทาง push ของอุปกรณ์นี้ — idempotent (กดซ้ำได้ ไม่เกิดแถวซ้ำ)

    ⚠️ **`user_id` มาจาก JWT เท่านั้น** — `PushSubscriptionIn` ไม่มีฟิลด์นี้
       โดยเจตนา (ดู docstring ของ schema) · ถ้าส่ง `user_id` มาใน body จะถูก
       pydantic ตัดทิ้งเงียบ ๆ ⇒ ลงทะเบียนปลายทางให้คนอื่นไม่ได้ (เทสต์ S8)

    📱 `user_agent` อ่านจาก header ตรงนี้ (ไม่ใช่จาก `user_ctx`) — `get_current_user`
       คืนแค่ `user_id`/`is_system` เท่านั้น · เก็บไว้ **เพื่อการวินิจฉัยเท่านั้น**
       ("เครื่องนี้คือ iPhone ของใคร" ตอนมีคนบ่นว่า push ไม่ขึ้น) ไม่มีตรรกะใดอ่านค่านี้
       ⇒ ถูกตัดให้สั้น 255 ตัวอักษรกันแถวบวม
    """
    uid = _ensure_user(user_ctx)
    await push_service.save_subscription(
        pool, uid,
        endpoint=req.endpoint, p256dh=req.keys.p256dh, auth=req.keys.auth,
        user_agent=(request.headers.get("user-agent") or "")[:255] or None,
    )
    return PushSubscribeOut(device_count=(await push_service.get_status(pool, uid))["device_count"])


@router.post("/push/unsubscribe", response_model=PushUnsubscribeOut)
async def push_unsubscribe(
    req: PushUnsubscribeIn,
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """ลบปลายทางของอุปกรณ์นี้

    ⚠️ **ไม่คืน 404 เมื่อไม่พบ** — คืน `removed: 0` แทน โดยเจตนา
       เพราะ "ลบสิ่งที่ไม่มีอยู่" = ผลลัพธ์ที่ client ต้องการแล้ว (idempotent)
       และเบราว์เซอร์อาจ unsubscribe ไปแล้วรอบหนึ่งก่อนถึงที่นี่
    """
    uid = _ensure_user(user_ctx)
    removed = await push_service.delete_subscription(pool, uid, endpoint=req.endpoint)
    return PushUnsubscribeOut(
        removed=removed,
        device_count=(await push_service.get_status(pool, uid))["device_count"],
    )
