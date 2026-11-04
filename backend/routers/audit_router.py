from fastapi import APIRouter, Depends, HTTPException, Query
import asyncpg
from datetime import date

from core.dependencies import get_db_pool, get_current_user
from core.exceptions import ForbiddenError, ValidationError
from models.audit_schemas import AuditLogOptions, AuditLogOut, AuditLogPage
from services import audit_service

router = APIRouter(prefix="/audit-logs", tags=["AuditLogs"])


@router.get("/options", response_model=AuditLogOptions)
async def get_audit_log_options(
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """ค่าที่มีจริงในบันทึก (90 วันล่าสุด) — เติม dropdown ของตัวกรองที่หน้าเว็บ"""
    uid = user_ctx.get("user_id")
    if not uid:
        raise HTTPException(status_code=401, detail="ต้องเข้าสู่ระบบ")

    try:
        result = await audit_service.get_options(pool, uid)
    except ForbiddenError as e:
        raise HTTPException(status_code=403, detail=str(e))

    return AuditLogOptions(**result)


@router.get("", response_model=AuditLogPage)
async def list_audit_logs(
    service_name: str | None = Query(None, max_length=100, description="กรองตามบริการ เช่น issue_service"),
    action: str | None = Query(None, max_length=50, description="กรองตาม action เช่น login/CREATE_ISSUE"),
    entity_type: str | None = Query(None, max_length=50, description="กรองตามชนิด entity เช่น issue/user"),
    entity_id: str | None = Query(None, max_length=50, description="กรองตาม id ของ entity"),
    status: str | None = Query(None, max_length=20, description="success/error/partial"),
    q: str | None = Query(None, max_length=100, description="ค้นหาตามผู้ทำ/endpoint/รหัส entity/ข้อความ error"),
    date_from: date | None = Query(None, description="จากวันที่ (YYYY-MM-DD, Asia/Bangkok)"),
    date_to: date | None = Query(None, description="ถึงวันที่ (YYYY-MM-DD, Asia/Bangkok)"),
    limit: int = Query(audit_service.DEFAULT_LIMIT, ge=1, le=audit_service.MAX_LIMIT),
    # ⚠️ keyset ไม่ใช่ offset — ใช้ `next_cursor` ที่ API ส่งกลับมาเท่านั้น
    cursor: str | None = Query(None, max_length=300, description="next_cursor จากหน้าถัดไป"),
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """ประวัติการใช้งานทั้งหมด (เฉพาะ VIEW_AUDIT_LOG + scope super/all — admin/ครูสภา/ประธานสภา)"""
    uid = user_ctx.get("user_id")
    if not uid:
        raise HTTPException(status_code=401, detail="ต้องเข้าสู่ระบบ")

    try:
        result = await audit_service.list_audit_logs(
            pool, uid,
            service_name=service_name, action=action,
            entity_type=entity_type, entity_id=entity_id,
            status=status, q=q, date_from=date_from, date_to=date_to,
            limit=limit, cursor=cursor,
        )
    except ValidationError as e:
        # cursor ที่พิมพ์มือ/ตัดขาด → 400 ไม่ใช่ 500
        raise HTTPException(status_code=400, detail=str(e))
    except ForbiddenError as e:
        raise HTTPException(status_code=403, detail=str(e))

    return AuditLogPage(
        items=[AuditLogOut(**i) for i in result["items"]],
        next_cursor=result["next_cursor"],
        has_more=result["has_more"],
    )
