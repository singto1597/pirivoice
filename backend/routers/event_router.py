"""Event Router — ระบบกิจกรรม + การลงทะเบียน (D1)

ชั้นนี้ทำแค่ HTTP: ดึง user จาก header → เรียก service → แปลง domain exception เป็น
HTTPException (ตัวเช็คสิทธิ์อยู่ใน service แล้ว ตามแบบ announcement_router)

⚠️ **สองมุมมองในไฟล์เดียวโดยเจตนา** — `/events/public*` (นักเรียน) กับ `/events*` (ผู้จัดการ)
อยู่ router เดียวกันเพราะใช้ตาราง/service ชุดเดียวกัน การแยกไฟล์จะทำให้ต้องมี `_ensure_user`/
`_err` สองชุดแล้วค่อย ๆ เพี้ยนจากกัน · **สิ่งที่กันการสับสนคือชื่อ path ไม่ใช่ชื่อไฟล์**

⚠️ **ห้ามย้าย endpoint พวกนี้ไป `public_router` (prefix /api/v1/public)** — ไฟล์นั้นมีสัญญาว่า
   "ไม่ต้องล็อกอิน" ทั้งไฟล์ · แม้แต่ `/events/public` ที่ทุกคนเห็นเหมือนกันก็ **ต้องล็อกอิน**
   เพราะต้องรู้ว่า "ฉันสมัครแล้วหรือยัง" (`my_registration_status`) ⇒ ตัวตนเป็นส่วนหนึ่งของผลลัพธ์

⚠️ **ลำดับการประกาศ route มีความหมาย** — Starlette จับคู่ตามลำดับที่ประกาศ ⇒ `/events/public`
   ต้องมาก่อน `/events/{event_id}/...` · ตอนนี้ไม่ชนกันเพราะ path ต่างความยาวกัน (`public` อยู่
   ตำแหน่งที่ path อื่นเป็น int) แต่ถ้าวันหน้าเพิ่ม `GET /events/{event_id}` **ต้องย้ายกลุ่ม public
   ขึ้นบนสุดก่อน** ไม่งั้น `public` จะถูก parse เป็น int แล้วได้ 422 แทนที่จะเข้ากิจกรรมได้
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
import asyncpg

from core.dependencies import get_db_pool, get_current_user
from core.exceptions import NotFoundError, ForbiddenError, ValidationError
from models.event_schemas import (
    EVENT_CATEGORIES,
    EventCreateRequest,
    EventUpdateRequest,
    # D2 — input มาก่อน output เหมือนสองตัวบน
    CheckInRequest,
    CheckInResultOut,
    EventOut,
    EventListOut,
    EventPublicOut,
    EventPublicListOut,
    EventRegistrationListOut,
    MyRegistrationOut,
)
from services import event_service

router = APIRouter(prefix="/events", tags=["Events"])

# 🏷️ ตัวกรองหมวด (D4) ใช้ร่วมกันทั้งสอง endpoint — สร้าง **ครั้งเดียวจากลิสต์จริง**
# ⚠️ เขียน regex ด้วยมือจะเพี้ยนจาก `EventCategory` ทันทีที่มีคนเพิ่มหมวด (แล้วอาการคือ
#    "เพิ่มหมวดใหม่แล้วกรองไม่ได้" ซึ่งหาสาเหตุยาก เพราะค่าใหม่ผ่าน schema ได้ปกติ)
# ⚠️ ทำไมต้องมี `pattern` ที่นี่ **ทั้งที่ service ตรวจซ้ำ** — `pattern` ทำให้ FastAPI
#    ตอบ **422** ตั้งแต่ชั้น request (แบบเดียวกับ `status`/`scope`) ⇒ ทั้ง API มี
#    พฤติกรรมเดียวกันหมด · ส่วนด่านใน service เป็นชั้นที่สองสำหรับผู้เรียกที่ไม่ผ่าน HTTP
_CATEGORY_PATTERN = "^(" + "|".join(EVENT_CATEGORIES) + ")$"


def _ensure_user(user_ctx: dict) -> int:
    """ดึง user_id หรือ raise 401"""
    uid = user_ctx.get("user_id")
    if not uid:
        raise HTTPException(status_code=401, detail="ต้องเข้าสู่ระบบ")
    return uid


def _err(e: Exception) -> HTTPException:
    """แปลง domain exception → HTTPException (pattern เดียวกับ announcements/issues)"""
    if isinstance(e, NotFoundError):
        return HTTPException(status_code=404, detail=str(e))
    if isinstance(e, ForbiddenError):
        return HTTPException(status_code=403, detail=str(e))
    if isinstance(e, ValidationError):
        return HTTPException(status_code=400, detail=str(e))
    return HTTPException(status_code=500, detail=f"เกิดข้อผิดพลาด: {e}")


# ============================================================
# 🎓 ฝั่งนักเรียน — ต้องล็อกอิน แต่ไม่ต้องมีสิทธิ์พิเศษ
# (ประกาศก่อนกลุ่มผู้จัดการ — ดูคำเตือนเรื่องลำดับที่หัวไฟล์)
# ============================================================

@router.get("/public", response_model=EventPublicListOut)
async def list_public_events(
    scope: str = Query(
        "upcoming",
        pattern="^(upcoming|past|all)$",
        description=(
            "กรองช่วงเวลา: upcoming (ยังไม่ถึงวันจัด) / past (ผ่านไปแล้ว) / all (ทั้งหมด)"
        ),
    ),
    category: Optional[str] = Query(
        None,
        pattern=_CATEGORY_PATTERN,
        description=(
            "กรองหมวดกิจกรรม (D4): academic/sports/arts/service/club/meeting/other "
            "— ไม่ส่งมา = ทุกหมวด"
        ),
    ),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """รายการกิจกรรมที่เผยแพร่แล้ว — ทุกคนเห็นเหมือนกัน ต่างกันแค่ `my_registration_status`"""
    uid = _ensure_user(user_ctx)
    try:
        result = await event_service.list_public_events(
            pool, uid, scope=scope, category=category, limit=limit, offset=offset
        )
    except ValidationError as e:
        raise _err(e)

    return EventPublicListOut(
        items=[EventPublicOut(**i) for i in result["items"]],
        total=result["total"],
        page=result["page"],
        page_size=result["page_size"],
        pages=result["pages"],
    )


@router.get("/public/{event_id}", response_model=EventPublicOut)
async def get_public_event(
    event_id: int,
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """รายละเอียดกิจกรรมหนึ่งใบ (เฉพาะที่เผยแพร่แล้ว) — ฉบับร่าง/ที่ถูกลบ = 404"""
    uid = _ensure_user(user_ctx)
    try:
        row = await event_service.get_public_event(pool, uid, event_id)
    except NotFoundError as e:
        raise _err(e)

    return EventPublicOut(**row)


@router.get("/{event_id}/my-registration", response_model=MyRegistrationOut)
async def get_my_registration(
    event_id: int,
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """สถานะการสมัครของ *ฉัน* — ใช้เติมปุ่ม/ไอคอนในหน้า detail

    ⚠️ คืน 200 พร้อม `registered: false` เมื่อยังไม่สมัคร (**ไม่ใช่ 404**) — "ยังไม่สมัคร"
       เป็นคำตอบที่ถูกต้องของคำถามนี้ ไม่ใช่ความผิดพลาด ⇒ 404 จะทำให้ frontend ต้องแยกแยะ
       "ยังไม่สมัคร" กับ "ไม่มีกิจกรรมนี้" ซึ่งแยกไม่ได้ถ้าดูแค่ status code
    """
    uid = _ensure_user(user_ctx)
    return MyRegistrationOut(**await event_service.get_my_registration(pool, uid, event_id))


@router.post("/{event_id}/register", response_model=MyRegistrationOut)
async def register_event(
    event_id: int,
    response: Response,
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """ลงทะเบียน — ที่นั่งเต็มจะเข้าคิวสำรอง **โดยอัตโนมัติ** (ไม่ใช่ error)

    คืน **201** เมื่อสร้างแถวใหม่ · **200** เมื่อมีแถวอยู่แล้ว (กดซ้ำ/ดับเบิลแท็ป)
    ⇒ การกดซ้ำต้องไม่พัง และต้องไม่ทำให้คิวขยับ (service จัดการไว้แล้ว)
    """
    uid = _ensure_user(user_ctx)
    try:
        created, payload = await event_service.register_event(pool, uid, event_id)
    except (NotFoundError, ForbiddenError, ValidationError) as e:
        raise _err(e)

    response.status_code = 201 if created else 200
    return MyRegistrationOut(**payload)


@router.delete("/{event_id}/register", response_model=MyRegistrationOut)
async def cancel_registration(
    event_id: int,
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """ถอนการลงทะเบียนของตัวเอง — ถ้าถือที่นั่งจริง ระบบจะเลื่อนคิวถัดไปขึ้นมาแทนทันที

    คืน 200 เสมอ (ไม่ใช่ 204) เพราะ body ที่คืนคือ "สถานะหลังถอน" ที่ frontend ใช้ต่อได้เลย
    """
    uid = _ensure_user(user_ctx)
    try:
        _promoted_user_id, payload = await event_service.cancel_registration(
            pool, uid, event_id
        )
    except (NotFoundError, ForbiddenError, ValidationError) as e:
        raise _err(e)

    return MyRegistrationOut(**payload)


# ============================================================
# 🛠️ ฝั่งผู้จัดการ — ต้องมีสิทธิ์ MANAGE_EVENTS (ตรวจใน service)
# ============================================================

@router.get("", response_model=EventListOut)
async def list_events(
    status: str = Query(
        "live",
        pattern="^(live|draft|published|cancelled|deleted|all)$",
        description=(
            "กรองสถานะ: live (ยังไม่ถูกลบ — ค่าเริ่มต้น) / draft (ฉบับร่าง) / "
            "published (เผยแพร่แล้ว) / cancelled (ยกเลิก) / deleted (ถูกลบ) / all (ทั้งหมด)"
        ),
    ),
    category: Optional[str] = Query(
        None,
        pattern=_CATEGORY_PATTERN,
        description=(
            "กรองหมวดกิจกรรม (D4): academic/sports/arts/service/club/meeting/other "
            "— ไม่ส่งมา = ทุกหมวด"
        ),
    ),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """รายการกิจกรรมทั้งหมด (หน้าจัดการ) — ร่างขึ้นก่อน แล้วเรียงตามวันจัดใหม่→เก่า"""
    uid = _ensure_user(user_ctx)
    try:
        result = await event_service.list_events(
            pool, uid, status=status, category=category, limit=limit, offset=offset
        )
    except (ForbiddenError, ValidationError) as e:
        raise _err(e)

    return EventListOut(
        items=[EventOut(**i) for i in result["items"]],
        total=result["total"],
        page=result["page"],
        page_size=result["page_size"],
        pages=result["pages"],
    )


@router.post("", response_model=EventOut, status_code=201)
async def create_event(
    req: EventCreateRequest,
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """สร้างกิจกรรม — เกิดเป็น **ฉบับร่าง** เสมอ และ **ยังไม่แจ้งเตือนใคร**

    ⚠️ การเผยแพร่เป็นการกระทำแยก (`POST /{id}/publish`) จึงจะยิงแจ้งเตือน
       (ผู้ใช้เลือกไว้: "แจ้งเฉพาะตอนกดเผยแพร่ ไม่ใช่ตอนสร้าง")
       ⇒ ฟอร์มสร้างต้องส่ง `status` มาไม่ได้ และ schema ก็ไม่รับ (ดู `EventCreateRequest`)
    """
    uid = _ensure_user(user_ctx)
    try:
        row = await event_service.create_event(pool, uid, req.model_dump())
    except (ForbiddenError, ValidationError) as e:
        raise _err(e)

    return EventOut(**row)


@router.get("/{event_id}/registrations", response_model=EventRegistrationListOut)
async def list_registrations(
    event_id: int,
    status: Optional[str] = Query(
        None,
        pattern="^(registered|waitlisted|cancelled|checked_in)$",
        description="กรองเฉพาะสถานะหนึ่ง (ไม่ส่ง = ทั้งหมด เรียงตามคิว)",
    ),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """รายชื่อผู้สมัครของกิจกรรมหนึ่ง (สภาดูเพื่อเลื่อนคิว/เช็คอินด้วยมือได้)"""
    uid = _ensure_user(user_ctx)
    try:
        result = await event_service.list_registrations(
            pool, uid, event_id, status=status, limit=limit, offset=offset
        )
    except (NotFoundError, ForbiddenError, ValidationError) as e:
        raise _err(e)

    return EventRegistrationListOut(
        items=result["items"],
        total=result["total"],
        page=result["page"],
        page_size=result["page_size"],
        pages=result["pages"],
    )


@router.post("/{event_id}/check-in", response_model=CheckInResultOut)
async def check_in_registration(
    event_id: int,
    req: CheckInRequest,
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """เช็คอินผู้เข้าร่วม (D2) — **สแกน QR** (`token`) หรือ **กดมือจากรายชื่อ** (`registration_id`)

    ⚠️ **คืน 200 เสมอทั้งการเช็คอินครั้งแรกและการสแกนซ้ำ** — แยกด้วย `already_checked_in`
       ใน body · สแกนรัว/สแกนสองเครื่องเป็นเรื่องปกติหน้างาน ⇒ การตอบ 4xx จะทำให้สภาอ่านว่า
       "ระบบพัง" แล้วหันไปจดใส่กระดาษ (ซึ่งคือความล้มเหลวของฟีเจอร์ ไม่ใช่ของผู้ใช้)

    ⚠️ ต้องมีสิทธิ์ `MANAGE_EVENTS` (ตรวจใน service) — **นักเรียนเช็คอินตัวเองไม่ได้**
       โดยเจตนา: การเช็คอินคือการยืนยันว่า "มีตัวตนอยู่ที่หน้างาน" ซึ่งคนที่อยู่หน้างานยืนยันให้ตัวเอง
       ไม่ได้ · ถ้าวันหน้าต้องการ "นักเรียนเช็คอินเอง" นั่นคือฟีเจอร์ใหม่ (คนละการตัดสินใจ) ไม่ใช่
       การผ่อนด่านนี้
    """
    uid = _ensure_user(user_ctx)
    try:
        result = await event_service.check_in_registration(
            pool, uid, event_id,
            token=req.token, registration_id=req.registration_id,
        )
    except (NotFoundError, ForbiddenError, ValidationError) as e:
        raise _err(e)

    return CheckInResultOut(**result)


@router.patch("/{event_id}", response_model=EventOut)
async def update_event(
    event_id: int,
    req: EventUpdateRequest,
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """แก้กิจกรรม — ส่งเฉพาะฟิลด์ที่จะแก้ (ไม่ส่ง = ไม่แตะ · ส่ง null = ล้างค่า)

    ⚠️ ไม่มีช่องทางเปลี่ยน `status` ที่นี่ — PATCH ใบเดียวต้องเผยแพร่กิจกรรมโดยไม่ยิง
       แจ้งเตือนไม่ได้ (ดู docstring ของ `EventUpdateRequest`)
    """
    uid = _ensure_user(user_ctx)
    try:
        row = await event_service.update_event(
            pool, uid, event_id, req.model_dump(exclude_unset=True)
        )
    except (NotFoundError, ForbiddenError, ValidationError) as e:
        raise _err(e)

    return EventOut(**row)


@router.post("/{event_id}/publish", response_model=EventOut)
async def publish_event(
    event_id: int,
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """เผยแพร่กิจกรรม — **ที่นี่ที่เดียวที่ยิงแจ้งเตือนหาทุกคน**

    เผยแพร่ได้ครั้งเดียว (ร่าง → เผยแพร่) · ร่างที่วันจัดผ่านไปแล้วจะถูกปฏิเสธด้วย 400
    พร้อมบอกทางออก — กันประกาศโรงเรียนทั้งโรงเรียนที่กู้คืนไม่ได้สำหรับกิจกรรมที่จบไปแล้ว
    """
    uid = _ensure_user(user_ctx)
    try:
        row = await event_service.publish_event(pool, uid, event_id)
    except (NotFoundError, ForbiddenError, ValidationError) as e:
        raise _err(e)

    return EventOut(**row)


@router.post("/{event_id}/cancel", response_model=EventOut)
async def cancel_event(
    event_id: int,
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """ยกเลิกกิจกรรมที่เผยแพร่แล้ว — แจ้งเฉพาะคนที่ลงทะเบียนไว้ (ไม่ใช่ทั้งโรงเรียน)

    แถวการลงทะเบียน **ไม่ถูกลบ** — เก็บไว้เป็นประวัติว่าใครเคยสมัคร และไม่เลื่อนคิว
    (กิจกรรมไม่ได้จัด ⇒ ไม่มีที่นั่งให้ใคร)
    """
    uid = _ensure_user(user_ctx)
    try:
        row = await event_service.cancel_event(pool, uid, event_id)
    except (NotFoundError, ForbiddenError, ValidationError) as e:
        raise _err(e)

    return EventOut(**row)


@router.delete("/{event_id}", response_model=EventOut)
async def delete_event(
    event_id: int,
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """ลบกิจกรรม (soft delete) — หายจากทุกหน้า แต่ข้อมูลยังอยู่ กู้คืนได้"""
    uid = _ensure_user(user_ctx)
    try:
        row = await event_service.delete_event(pool, uid, event_id)
    except (NotFoundError, ForbiddenError) as e:
        raise _err(e)

    return EventOut(**row)


@router.post("/{event_id}/restore", response_model=EventOut)
async def restore_event(
    event_id: int,
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """กู้คืนกิจกรรมที่ถูกลบ — กลับมาในสถานะเดิม (ร่าง/เผยแพร่/ยกเลิก ตามที่ค้างไว้)

    ⚠️ **ไม่ยิงแจ้งเตือนซ้ำ** — คนที่เคยได้รับแจ้งตอนเผยแพร่แล้วไม่ควรได้อีก
       (การกู้คืนเป็นเรื่องของผู้ดูแล ไม่ใช่เหตุการณ์ใหม่ของนักเรียน)
    """
    uid = _ensure_user(user_ctx)
    try:
        row = await event_service.restore_event(pool, uid, event_id)
    except (NotFoundError, ForbiddenError) as e:
        raise _err(e)

    return EventOut(**row)
