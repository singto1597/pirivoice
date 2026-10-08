"""Rollover Router — เลื่อนชั้นทั้งโรงเรียน (`/api/rollover/*`) — P4

ชั้นนี้ทำแค่ HTTP: ดึง user จาก header → เรียก service → แปลง domain exception เป็น
HTTPException (ตัวเช็คสิทธิ์ **สองชั้น** อยู่ใน service แล้ว — ดู `rollover_service._gate`)

**ทำไมแยกไฟล์จาก `settings_router`** ทั้งที่เป็นเรื่อง "ปีการศึกษา" เหมือนกัน:
  · `/settings/*` = ตั้งค่า (สร้าง/แก้ปี, ภาคเรียน, quiet hours) — ผิดแล้วแก้กลับได้ง่าย
  · `/rollover/*` = **ลงมือ** เขียนสมาชิกหลายพันแถวและสลับปีปัจจุบัน — ผิดแล้วต้องกู้ dump
  สิทธิ์ก็ต่างกัน (`MANAGE_SETTINGS` ล้วน vs `MANAGE_STUDENTS` + `mode == 'school'`)
  ⇒ รวมกันจะทำให้ "ตั้งค่า" กับ "ลงมือ" ใช้ประตูเดียวกัน ซึ่งเป็นสิ่งที่แผนเลี่ยงมาตั้งแต่ต้น
"""
from fastapi import APIRouter, Depends, HTTPException, Query
import asyncpg

from core.dependencies import get_db_pool, get_current_user
from core.exceptions import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from models.rollover_schemas import (
    ReconciliationOut,
    RolloverApplyOut,
    RolloverApplyRequest,
    RolloverPreviewOut,
    RolloverPreviewRequest,
    RolloverRunListOut,
    RolloverRunOut,
)
from services import rollover_service

router = APIRouter(prefix="/rollover", tags=["Rollover"])


def _ensure_user(user_ctx: dict) -> int:
    """ดึง user_id หรือ raise 401"""
    uid = user_ctx.get("user_id")
    if not uid:
        raise HTTPException(status_code=401, detail="ต้องเข้าสู่ระบบ")
    return uid


def _err(e: Exception) -> HTTPException:
    """แปลง domain exception → HTTPException

    ⚠️ **`ConflictError` → 409** ต่างจาก router อื่นในระบบ (ที่ 400 พอ) เพราะที่นี่มี
       "รอบที่ถูกใช้ไปแล้ว" กับ "มีคน import แทรกหลัง preview" ซึ่งเป็น **การชนกันของสถานะ**
       ไม่ใช่ข้อมูลที่ผู้ใช้กรอกผิด ⇒ ฝั่ง UI ต้องแยกได้ว่า "ยิงซ้ำ/มีคนแก้แข่ง" ไม่ใช่ "แก้ฟอร์มแล้วลองใหม่"
    """
    if isinstance(e, NotFoundError):
        return HTTPException(status_code=404, detail=str(e))
    if isinstance(e, ForbiddenError):
        return HTTPException(status_code=403, detail=str(e))
    if isinstance(e, ConflictError):
        return HTTPException(status_code=409, detail=str(e))
    if isinstance(e, ValidationError):
        return HTTPException(status_code=400, detail=str(e))
    return HTTPException(status_code=500, detail=f"เกิดข้อผิดพลาด: {e}")


_DOMAIN_ERRORS = (NotFoundError, ForbiddenError, ConflictError, ValidationError)


@router.post("/preview", response_model=RolloverPreviewOut)
async def preview_rollover(
    req: RolloverPreviewRequest,
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """ดูแผนการเลื่อนชั้น **ก่อน** ลงมือ — ไม่แก้ข้อมูลสมาชิกเลย (เรียกซ้ำได้ไม่จำกัด)

    คืน `run_id` มาด้วย ⇒ ต้องส่งตัวนี้กลับตอน `apply` (บังคับให้เห็นแผนก่อนกดจริง)

    - `can_apply=false` + `blockers` = ยังกดไม่ได้ (ต้องดู `blockers` ว่าให้แก้อะไร)
    - `warnings` = ทำได้ แต่ควรตรวจก่อน (เช่นมีคนไม่มีห้อง / บุคลากรในห้อง ม.6)
    - `unmapped` = ห้องที่หาปลายทางไม่ได้ — แก้ด้วย `room_overrides` **แล้ว preview ซ้ำ**
      จนกว่า `can_apply` จะเป็นจริง จากนั้นส่งค่าเดิมตอน `apply`
    """
    uid = _ensure_user(user_ctx)
    try:
        plan = await rollover_service.preview_rollover(
            pool,
            uid,
            from_year_id=req.from_year_id,
            to_year_id=req.to_year_id,
            room_overrides=req.room_overrides,
        )
    except _DOMAIN_ERRORS as e:
        raise _err(e)

    return RolloverPreviewOut(**plan)


@router.post("/apply", response_model=RolloverApplyOut)
async def apply_rollover(
    req: RolloverApplyRequest,
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """🔴 **ทำจริง** — เลื่อนทุกคนเข้าปีใหม่, ปิดแถวปีเก่า, ตั้งปีใหม่เป็นปีปัจจุบัน

    ทั้งหมดอยู่ใน **transaction เดียว**: ล้มกลางทาง = ไม่มีอะไรถูกแก้เลย (ไม่ต้องกู้ dump)

    - ต้องส่ง `run_id` จาก `/preview` — รอบเดิมใช้ซ้ำไม่ได้ (409)
    - `room_overrides` ใช้กับห้องที่ preview บอกว่าแมปไม่ได้ (เช่น `{"ม.3/14": "ม.4/13"}`)
    - ปีปลายทางต้องว่าง — ถ้ามีคน import แทรกหลัง preview จะได้ **409** ไม่ใช่ทับข้อมูล
    """
    uid = _ensure_user(user_ctx)
    try:
        result = await rollover_service.apply_rollover(
            pool, uid, run_id=req.run_id, room_overrides=req.room_overrides
        )
    except _DOMAIN_ERRORS as e:
        raise _err(e)

    return RolloverApplyOut(**result)


@router.get("/runs", response_model=RolloverRunListOut)
async def list_runs(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """ประวัติการเลื่อนชั้น (ใหม่สุดก่อน) — "ใครกด เมื่อไหร่ ผลเป็นยังไง"

    แต่ละรอบเก็บแผนเต็มไว้ใน `plan` ⇒ ย้อนดูได้ว่าตอนนั้นระบบคิดว่าจะเกิดอะไรขึ้น
    (ใช้ตอบคำถาม "ทำไมเด็กคนนี้หายไป" ได้โดยไม่ต้องเดา)
    """
    uid = _ensure_user(user_ctx)
    try:
        result = await rollover_service.list_runs(
            pool, uid, limit=limit, offset=offset
        )
    except _DOMAIN_ERRORS as e:
        raise _err(e)

    return RolloverRunListOut(
        items=[RolloverRunOut(**i) for i in result["items"]],
        total=result["total"],
    )


@router.get("/reconciliation", response_model=ReconciliationOut)
async def reconciliation(
    from_year_id: int = Query(..., description="ปีก่อน"),
    to_year_id: int = Query(..., description="ปีหลัง"),
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """กระทบยอดรายชื่อสองปี — ใครหายจากปีก่อน / ใครเพิ่มมาในปีใหม่

    ⭐ ตอบข้อกำหนด "เด็กจบต้องค้นชื่อเจอ" ได้จริง: ระบบ **บอกว่าใครหาย** แต่ **ไม่เดาสาเหตุ**
       (ย้ายออก / จบ / ตกหล่น) เพราะการเดาจะกลายเป็นข้อมูลผิดที่ไม่มีใครตรวจ

    ⚠️ คืนรายชื่อเต็มทั้งสองฝั่ง — ผู้ใช้ที่มีสิทธิ์นี้เห็นรายชื่อทั้งโรงเรียนอยู่แล้ว
       (ประตูเดียวกับ `/preview`) จึงไม่ใช่การเปิดข้อมูลใหม่ให้ใคร
    """
    uid = _ensure_user(user_ctx)
    try:
        result = await rollover_service.reconciliation(
            pool, uid, from_year_id=from_year_id, to_year_id=to_year_id
        )
    except _DOMAIN_ERRORS as e:
        raise _err(e)

    return ReconciliationOut(**result)
