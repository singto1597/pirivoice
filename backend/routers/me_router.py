"""Me Router — ข้อมูลของเจ้าของบัญชีเท่านั้น (`/api/me/*`)

ชั้นนี้ทำแค่ HTTP: ดึง user จาก JWT → เรียก service → แปลง exception เป็น HTTPException

⚠️ **ไม่ต้องมี `require_permission`** — ตัวตนคือสิทธิ์ (แบบเดียวกับ `GET /api/issues/summary`)
   แต่ **ต้อง** กันด้วย `_ensure_user()` เพราะ `get_current_user` คืน `user_id = None`
   เมื่อถูกเรียกด้วย `X-API-Key` (system RPC) ⇒ ถ้าไม่กันจะนับของ user_id NULL เงียบ ๆ
   แล้วคืน 0 ทุกช่องโดยไม่มีใครรู้ว่าผิด

⚠️ **ห้ามรับ `user_id` จาก client** ทุกกรณี — เอาจาก `user_ctx` เท่านั้น
"""
from fastapi import APIRouter, Depends, HTTPException
import asyncpg

from core.dependencies import get_db_pool, get_current_user
from models.me_schemas import PersonalStatsOut
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
