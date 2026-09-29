"""Me Router — ข้อมูลของเจ้าของบัญชีเท่านั้น (`/api/me/*`)

ชั้นนี้ทำแค่ HTTP: ดึง user จาก JWT → เรียก service → แปลง exception เป็น HTTPException

⚠️ **ไม่ต้องมี `require_permission`** — ตัวตนคือสิทธิ์ (แบบเดียวกับ `GET /api/issues/summary`)
   แต่ **ต้อง** กันด้วย `_ensure_user()` เพราะ `get_current_user` คืน `user_id = None`
   เมื่อถูกเรียกด้วย `X-API-Key` (system RPC) ⇒ ถ้าไม่กันจะนับของ user_id NULL เงียบ ๆ
   แล้วคืน 0 ทุกช่องโดยไม่มีใครรู้ว่าผิด

⚠️ **ห้ามรับ `user_id` จาก client** ทุกกรณี — เอาจาก `user_ctx` เท่านั้น
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
import asyncpg

from core.dependencies import get_db_pool, get_current_user
from models.me_schemas import ActivityListOut, ActivityType, PersonalStatsOut
from services import me_service

router = APIRouter(prefix="/me", tags=["Me"])


def _ensure_user(user_ctx: dict) -> int:
    """ดึง user_id หรือ raise 401"""
    uid = user_ctx.get("user_id")
    if not uid:
        raise HTTPException(status_code=401, detail="ต้องเข้าสู่ระบบ")
    return uid


@router.get("/stats", response_model=PersonalStatsOut)
async def get_my_stats(
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """สถิติส่วนตัว 6 ตัวเลข — กรองตามภาคปัจจุบัน (ถ้ายังไม่ตั้งภาค = นับทั้งหมด)

    `term` ในผลลัพธ์เป็น `null` เมื่อยังไม่มีภาคปัจจุบัน ⇒ frontend ต้องเขียนกำกับว่า
    "สถิติทั้งหมด (ยังไม่ได้ตั้งภาคเรียน)" ห้ามเงียบ ๆ แล้วโชว์เลขที่ดูเหมือนเลขของภาค
    """
    uid = _ensure_user(user_ctx)
    return PersonalStatsOut(**await me_service.get_personal_stats(pool, uid))


@router.get("/activity", response_model=ActivityListOut)
async def get_my_activity(
    activity_type: Optional[ActivityType] = Query(
        None, description="กรองเฉพาะประเภท (ไม่ส่ง = ทั้งหมด)"
    ),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """กิจกรรมของฉัน — timeline รวม 4 ประเภท (เรื่องที่แจ้ง · โหวต · คอมเมนต์บอร์ด · คอมเมนต์เรื่อง)

    ⚠️ **ไม่กรองตามภาคเรียนโดยเจตนา** ต่างจาก `/stats` — ที่นี่คือ "ทุกอย่างที่เคยทำ"
       แต่ **ยอดต่อประเภทเท่ากับตัวนับของ `/stats` ทีละตัว** ⇒ สองหน้าเลขตรงกันเสมอ
       (บังคับด้วยเทสต์ A2 — ดู `models/me_schemas.py`)

    ⚠️ `limit` จำกัดที่ 100 — เป็น feed ที่ JOIN 4 ตาราง ไม่ควรดึงทีละมาก ๆ

    ⚠️ `activity_type` ถูก validate ด้วย `Literal` ⇒ ค่านอกลิสต์ได้ 422 ก่อนถึง service
       และค่าถูกส่งเป็น **parameter** ไม่ใช่ f-string ⇒ ไม่มีทางเข้า SQL
    """
    uid = _ensure_user(user_ctx)
    return ActivityListOut(
        **await me_service.get_my_activity(
            pool, uid, activity_type=activity_type, limit=limit, offset=offset
        )
    )
