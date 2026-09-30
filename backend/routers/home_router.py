"""Home Router — ก้อนเดียวจบของหน้าแรก (`/api/home/*`)

ชั้นนี้ทำแค่ HTTP: ดึง user จาก JWT → เรียก service → คืนตาม response_model

⚠️ ต้องมี `_ensure_user()` เหมือน `me_router` — `get_current_user` คืน `user_id = None`
   เมื่อถูกเรียกด้วย `X-API-Key` (system RPC) ⇒ ถ้าไม่กันจะได้คิว "รอฉันตอบ" ของ
   `user_id = NULL` กลับไปเงียบ ๆ (ว่างเปล่าเสมอ) โดยไม่มีใครรู้ว่าผิด

⚠️ **ห้ามรับ `user_id` จาก client** — เอาจาก `user_ctx` เท่านั้น
"""
from fastapi import APIRouter, Depends, HTTPException
import asyncpg

from core.dependencies import get_db_pool, get_current_user
from models.home_schemas import HomeSummaryOut
from services import home_service

router = APIRouter(prefix="/home", tags=["Home"])


def _ensure_user(user_ctx: dict) -> int:
    """ดึง user_id หรือ raise 401"""
    uid = user_ctx.get("user_id")
    if not uid:
        raise HTTPException(status_code=401, detail="ต้องเข้าสู่ระบบ")
    return uid


@router.get("/summary", response_model=HomeSummaryOut)
async def get_home_summary(
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """ทุกอย่างที่หน้าแรกต้องใช้ — ประกาศ · สรุปเรื่องของฉัน · รอฉันตอบ ·
    โหวตที่ยังไม่โหวต · กิจกรรมใกล้ปิดรับ · สถิติส่วนตัว

    ❌ ไม่รวมแดชบอร์ดและคิวรายงาน — เป็น permission-gated และแดชบอร์ดหนัก
    ⇒ frontend ยิงสองตัวนั้นแยก เฉพาะคนที่มีสิทธิ์
    """
    uid = _ensure_user(user_ctx)
    return HomeSummaryOut(**await home_service.get_home_summary(pool, uid))
