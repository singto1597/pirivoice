"""Settings Router — ตั้งค่าระบบ (`/api/settings/*`)

ชั้นนี้ทำแค่ HTTP: ดึง user จาก header → เรียก service → แปลง domain exception เป็น
HTTPException (ตัวเช็คสิทธิ์อยู่ใน service แล้ว ตามแบบ audit_service / announcement_service)

ปัจจุบัน 2 เรื่อง — **สิทธิ์ไม่เหมือนกัน อย่าเหมารวม**:
- **ภาคเรียน** (`/terms`) — ทุก endpoint (รวม GET) ต้องมีสิทธิ์ `MANAGE_SETTINGS`
  เพราะรายการภาคเรียนไม่ใช่ข้อมูลสาธารณะ
- **quiet hours** (`/quiet-hours`) — `GET` **เปิดให้ผู้ใช้ที่ล็อกอินทุกคน** · `PUT` ต้องมีสิทธิ์
  ⭐ โดยเจตนา: ค่านี้มีไว้ *อธิบาย* ให้นักเรียนเข้าใจว่าทำไมมือถือเงียบ ⇒ ปิดการอ่าน
  เท่ากับซ่อนคำอธิบายจากคนที่ได้รับผลกระทบ · และมันไม่มีข้อมูลอ่อนไหว (แค่ช่วงเวลา)

เพิ่มเรื่องอื่นในอนาคตให้แยก tag/ไฟล์ย่อยถ้ามันโตจนไม่เกี่ยวกับ "การตั้งค่า" อีกต่อไป
"""
from fastapi import APIRouter, Depends, HTTPException, Query
import asyncpg

from core.dependencies import get_db_pool, get_current_user
from core.exceptions import NotFoundError, ForbiddenError, ValidationError
from models.settings_schemas import (
    AcademicTermCreateRequest,
    AcademicTermUpdateRequest,
    AcademicTermOut,
    AcademicTermListOut,
    QuietHoursOut,
    QuietHoursUpdateRequest,
)
from services import app_settings_service, term_service

router = APIRouter(prefix="/settings", tags=["Settings"])


def _ensure_user(user_ctx: dict) -> int:
    """ดึง user_id หรือ raise 401"""
    uid = user_ctx.get("user_id")
    if not uid:
        raise HTTPException(status_code=401, detail="ต้องเข้าสู่ระบบ")
    return uid


def _err(e: Exception) -> HTTPException:
    """แปลง domain exception → HTTPException (pattern เดียวกับ announcements/boards)"""
    if isinstance(e, NotFoundError):
        return HTTPException(status_code=404, detail=str(e))
    if isinstance(e, ForbiddenError):
        return HTTPException(status_code=403, detail=str(e))
    if isinstance(e, ValidationError):
        return HTTPException(status_code=400, detail=str(e))
    return HTTPException(status_code=500, detail=f"เกิดข้อผิดพลาด: {e}")


@router.get("/terms", response_model=AcademicTermListOut)
async def list_terms(
    status: str = Query(
        "active",
        pattern="^(current|active|deleted|all)$",
        description=(
            "กรองสถานะ: current (ภาคปัจจุบัน) / active (ยังไม่ถูกลบ) / "
            "deleted (ถูกลบ) / all (ทั้งหมด)"
        ),
    ),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """รายการภาคเรียน — ภาคปัจจุบันขึ้นก่อน แล้วใหม่สุดก่อน"""
    uid = _ensure_user(user_ctx)
    try:
        result = await term_service.list_terms(
            pool, uid, status=status, limit=limit, offset=offset
        )
    except (ForbiddenError, ValidationError) as e:
        raise _err(e)

    return AcademicTermListOut(
        items=[AcademicTermOut(**i) for i in result["items"]],
        total=result["total"],
        page=result["page"],
        page_size=result["page_size"],
        pages=result["pages"],
    )


@router.post("/terms", response_model=AcademicTermOut, status_code=201)
async def create_term(
    req: AcademicTermCreateRequest,
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """สร้างภาคเรียน — ส่ง `is_current: true` เพื่อตั้งเป็นภาคปัจจุบันทันที"""
    uid = _ensure_user(user_ctx)
    try:
        row = await term_service.create_term(
            pool, uid,
            name=req.name, start_date=req.start_date,
            end_date=req.end_date, is_current=req.is_current,
        )
    except (ForbiddenError, ValidationError) as e:
        raise _err(e)

    return AcademicTermOut(**row)


@router.patch("/terms/{term_id}", response_model=AcademicTermOut)
async def update_term(
    term_id: int,
    req: AcademicTermUpdateRequest,
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """แก้ชื่อ/ช่วงวันที่ของภาค — ส่งเฉพาะฟิลด์ที่จะแก้ (ไม่ส่ง = ไม่แตะ)

    ไม่มี `is_current` ที่นี่ — ใช้ `POST /terms/{id}/set-current`
    """
    uid = _ensure_user(user_ctx)
    changes = req.model_dump(exclude_unset=True)
    try:
        row = await term_service.update_term(pool, uid, term_id, changes)
    except (NotFoundError, ForbiddenError, ValidationError) as e:
        raise _err(e)

    return AcademicTermOut(**row)


@router.post("/terms/{term_id}/set-current", response_model=AcademicTermOut)
async def set_current_term(
    term_id: int,
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """ตั้งภาคนี้เป็น "ภาคปัจจุบัน" — ปลดภาคปัจจุบันตัวเก่าให้อัตโนมัติ

    มีภาคปัจจุบันได้ตัวเดียวเสมอ (บังคับด้วย partial unique index ที่ DB)
    """
    uid = _ensure_user(user_ctx)
    try:
        row = await term_service.set_current_term(pool, uid, term_id)
    except (NotFoundError, ForbiddenError) as e:
        raise _err(e)

    return AcademicTermOut(**row)


@router.delete("/terms/{term_id}", response_model=AcademicTermOut)
async def delete_term(
    term_id: int,
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """ลบภาคเรียน (soft delete) — ถ้าเป็นภาคปัจจุบันอยู่ จะหลุดจากตำแหน่งนั้นด้วย"""
    uid = _ensure_user(user_ctx)
    try:
        row = await term_service.delete_term(pool, uid, term_id)
    except (NotFoundError, ForbiddenError) as e:
        raise _err(e)

    return AcademicTermOut(**row)


@router.post("/terms/{term_id}/restore", response_model=AcademicTermOut)
async def restore_term(
    term_id: int,
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """กู้คืนภาคที่ถูกลบ — กลับมาเป็น **ภาคธรรมดา** ต้องกดตั้งเป็นปัจจุบันเองอีกครั้ง"""
    uid = _ensure_user(user_ctx)
    try:
        row = await term_service.restore_term(pool, uid, term_id)
    except (NotFoundError, ForbiddenError) as e:
        raise _err(e)

    return AcademicTermOut(**row)


# ============================================================
# 🔇 Quiet Hours (A8) — ช่วงเวลาที่โรงเรียนไม่ส่ง push
# ============================================================

@router.get("/quiet-hours", response_model=QuietHoursOut)
async def get_quiet_hours(
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """ช่วงเวลา "โรงเรียนไม่ส่ง push" — **ผู้ใช้ที่ล็อกอินแล้วทุกคนอ่านได้**

    ⭐ **ทำไม GET ไม่ต้องมี `MANAGE_SETTINGS`** (ต่างจาก `/terms` ข้างบนโดยเจตนา):
       ค่านี้ตอบคำถามที่นักเรียนทุกคนสงสัยตอนมือถือเงียบ — *"ทำไมไม่มีเสียง"*
       ⇒ ถ้าปิดการอ่าน เราจะซ่อนคำอธิบายจาก **คนที่ได้รับผลกระทบ** ซึ่งเป็นกลุ่มเดียว
       ที่ต้องการมัน · และเนื้อหามีแค่ช่วงเวลา ไม่มีข้อมูลส่วนบุคคลใด ๆ

    ⚠️ ยังต้องล็อกอิน (`_ensure_user`) — ไม่ใช่ endpoint สาธารณะ และการเรียกด้วย
       `X-API-Key` (ที่ `user_id` เป็น None) ต้องได้ **401 ไม่ใช่ 500**
    """
    _ensure_user(user_ctx)
    return QuietHoursOut(**await app_settings_service.get_quiet_hours(pool))


@router.put("/quiet-hours", response_model=QuietHoursOut)
async def put_quiet_hours(
    req: QuietHoursUpdateRequest,
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """ตั้งค่า quiet hours ทั้งโรงเรียน (upsert) — ต้องมี `MANAGE_SETTINGS`

    `PUT` = full replace ⇒ ส่งครบ 3 ฟิลด์เสมอ (idempotent — ส่งค่าเดิมซ้ำได้ไม่มีผลข้างเคียง)
    · เขียน audit log `UPDATE_QUIET_HOURS` **ใน transaction เดียวกัน** (ต่างจาก A2 ที่เป็น
      ค่าส่วนตัวจึงไม่บันทึก — อันนี้เป็น **state ที่แชร์ทั้งโรงเรียน** ⇒ ต้องตอบได้ว่าใครเปลี่ยน)
    """
    uid = _ensure_user(user_ctx)
    try:
        result = await app_settings_service.set_quiet_hours(
            pool, uid, enabled=req.enabled, start=req.start, end=req.end
        )
    except (ForbiddenError, ValidationError) as e:
        raise _err(e)

    return QuietHoursOut(**result)
