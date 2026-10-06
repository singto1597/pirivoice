from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
import asyncpg

from core.dependencies import get_db_pool, get_current_user
from core.rbac import (
    require_permission_anywhere,
    MANAGE_RANK,
    # 🌟 ย้ายมาจากไฟล์นี้ (ชื่อเดิม `_manage_mode`) — ดูเหตุผลที่ `core/rbac.py`
    # ⚠️ `get_access_scope` / `get_user_grade_scope` ถูกถอดออกจาก import แล้ว —
    #    ทั้งคู่ถูกเรียกจาก `_manage_mode` ที่ย้ายไป ⇒ ถ้าปล่อยไว้จะเป็น import ที่ตาย
    get_manage_mode,
)
from core.exceptions import NotFoundError, ForbiddenError, ValidationError, ConflictError
from models.student_schemas import (
    StudentOut, StudentUpdateRequest, StudentCreateRequest, RoomOut,
    MyProfileOut, UpdateProfileRequest,
)
from services import student_service
from services import audit_service

router = APIRouter(tags=["Students"])


async def _assert_manage_target(
    conn,
    actor_user_id: int,
    *,
    target_role: str,
    current_role: Optional[str] = None,
    target_grade: Optional[str] = None,
) -> None:
    """
    ตรวจ hierarchy + grade scope ว่าผู้จัดการ (actor) แก้ไข/สร้างเป้าหมายนี้ได้หรือไม่
    เรียก AFTER require_permission_anywhere(MANAGE_STUDENTS) ผ่านแล้วเท่านั้น
    """
    mode = await get_manage_mode(conn, actor_user_id)
    if mode["mode"] == "school":
        return
    if mode["mode"] == "none":
        raise ForbiddenError("คุณไม่มีขอบเขตสิทธิ์ในการจัดการนักเรียน")

    # teacher / level: ต้องอยู่ระดับชั้นเดียวกันกับเป้าหมาย (ยกเว้นเป้าหมายไม่มีห้อง เช่น ผู้บริหาร)
    if target_grade is not None and mode["grade"] and target_grade != mode["grade"]:
        raise ForbiddenError(f"คุณจัดการได้เฉพาะระดับ {mode['grade']}")

    # teacher: จัดการได้ทุก role ในระดับชั้นตัวเอง (คงพฤติกรรมเดิม)
    if mode["mode"] == "teacher":
        # กันครูแก้ role ระดับผู้บริหาร/ครูด้วยกัน (ไม่อยู่ใน MANAGE_RANK)
        if target_role not in MANAGE_RANK and target_role not in ("student",):
            if current_role is None or current_role not in MANAGE_RANK:
                raise ForbiddenError("คุณไม่สามารถจัดการตำแหน่งนี้ได้")
        return

    # level (ประธานระดับ/ผู้ช่วย): จัดการได้เฉพาะ role ใน MANAGE_RANK ที่ rank ≤ manage_rank
    target_rank = MANAGE_RANK.get(target_role)
    if target_rank is None:
        raise ForbiddenError("คุณไม่สามารถตั้งตำแหน่งนี้ได้ (เกินขอบเขต)")
    # role ปัจจุบันของเป้าหมาย ถ้าสูงกว่าเรา → ห้ามแม้แต่แก้ไข
    if current_role is not None and current_role in MANAGE_RANK and MANAGE_RANK[current_role] > mode["manage_rank"]:
        raise ForbiddenError("คุณไม่สามารถจัดการตำแหน่งที่สูงกว่าได้")
    if target_rank > mode["manage_rank"]:
        raise ForbiddenError("คุณไม่สามารถตั้งตำแหน่งที่สูงกว่าตัวเองได้")


# ===================== My Profile =====================
@router.get("/students/me/profile", response_model=MyProfileOut)
async def get_my_profile(
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """ดูโปรไฟล์ตัวเอง"""
    uid = user_ctx.get("user_id")
    if not uid:
        raise HTTPException(status_code=401, detail="ต้องเข้าสู่ระบบ")

    try:
        profile = await student_service.get_my_profile(pool, uid)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    # 🛡️ Audit: ดูโปรไฟล์ตัวเอง (best-effort)
    await audit_service.log_read(pool, uid, "READ_PROFILE", "user", entity_id=uid, endpoint="GET /api/students/me/profile")
    return MyProfileOut(**profile)


@router.patch("/students/me/profile", response_model=MyProfileOut)
async def update_my_profile(
    req: UpdateProfileRequest,
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """แก้ไขโปรไฟล์ตัวเอง (เฉพาะฟิลด์ที่ส่ง)"""
    uid = user_ctx.get("user_id")
    if not uid:
        raise HTTPException(status_code=401, detail="ต้องเข้าสู่ระบบ")

    try:
        await student_service.update_my_profile(
            pool, uid,
            prefix=req.prefix, first_name=req.first_name, last_name=req.last_name,
            nickname=req.nickname, phone_number=req.phone_number, email=req.email,
        )
        profile = await student_service.get_my_profile(pool, uid)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return MyProfileOut(**profile)


@router.get("/rooms", response_model=list[RoomOut])
async def list_rooms(
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """รายการห้องเรียนทั้งหมด (สำหรับ dropdown)"""
    rooms = await student_service.list_rooms(pool)
    # 🛡️ Audit: ดูรายการห้อง (best-effort)
    await audit_service.log_read(pool, user_ctx.get("user_id"), "READ_ROOMS", "room", endpoint="GET /api/rooms")
    return [RoomOut(**r) for r in rooms]


@router.get("/students", response_model=list[StudentOut])
async def list_students(
    room_id: int | None = Query(None),
    search: str | None = Query(None),
    role: str | None = Query(None, description="กรองตามตำแหน่ง (เช่น council_member)"),
    year_id: int | None = Query(
        None, description="ปีการศึกษาที่จะดู — ไม่ระบุ = ปีปัจจุบัน (ดูย้อนหลังได้)"
    ),
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """รายชื่อนักเรียน/สมาชิก (filter ตามห้อง/ค้นหา/ตำแหน่ง/ปี) — ต้องมีสิทธิ์ MANAGE_STUDENTS
    ขอบเขต: admin/ครูสภา/ประธานสภา เห็นทุกคน; ครู/ประธานระดับ/ผู้ช่วย เห็นเฉพาะระดับชั้นตัวเอง
    (ประธานระดับ/ผู้ช่วย เห็นเฉพาะ role ที่ต่ำกว่าหรือเท่ากับตัวเอง — กันดู role สูงกว่า)

    🌟 `year_id` (เพิ่มพร้อม migration 027) — ไม่ระบุ = ปีปัจจุบัน
       ⇒ ถ้าไม่ส่ง รายชื่อจะ **ไม่บวมด้วยแถวของปีเก่า** (ซึ่งคือพฤติกรรมที่ต้องการ)
       ⚠️ ขอบเขตระดับชั้น (`level`) ยังใช้กับปีที่ขอดูย้อนหลังด้วย — ครูยังเห็นได้แค่ระดับตัวเอง
          แม้จะดูปีเก่า (ไม่ใช่ช่องทางข้ามสิทธิ์)"""
    if not user_ctx.get("user_id"):
        raise HTTPException(status_code=401, detail="ต้องเข้าสู่ระบบ")

    # ตรวจสิทธิ์ (Super Admin / is_admin ผ่าน) + หา scope (ครู/ประธานระดับ เห็นได้เฉพาะระดับชั้นตัวเอง)
    async with pool.acquire() as conn:
        try:
            await require_permission_anywhere(conn, user_ctx["user_id"], "MANAGE_STUDENTS")
        except ForbiddenError as e:
            raise HTTPException(status_code=403, detail=str(e))
        mode = await get_manage_mode(conn, user_ctx["user_id"])

    if mode["mode"] == "none":
        raise HTTPException(status_code=403, detail="คุณไม่มีขอบเขตสิทธิ์ในการจัดการนักเรียน")

    level = mode["grade"] if mode["mode"] in ("teacher", "level") else None
    students = await student_service.list_students(
        pool, room_id=room_id, search=search, level=level, role=role, year_id=year_id
    )
    # ประธานระดับ/ผู้ช่วย: เห็นได้เฉพาะ role ที่จัดการได้ (rank ≤ ตัวเอง) ภายในระดับชั้น
    if mode["mode"] == "level":
        allowed = {r for r, rk in MANAGE_RANK.items() if rk <= mode["manage_rank"]}
        students = [s for s in students if s["class_role"] in allowed]
    # 🛡️ Audit: ดูรายชื่อนักเรียน (best-effort)
    await audit_service.log_read(pool, user_ctx["user_id"], "READ_STUDENTS", "student", endpoint="GET /api/students")
    return [StudentOut(**s) for s in students]


@router.patch("/students/{student_id}", response_model=dict)
async def update_student(
    student_id: int,
    req: StudentUpdateRequest,
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """แก้ไขตำแหน่ง/สถานะ/หน้าที่ของนักเรียน (ต้องมี MANAGE_STUDENTS + อยู่ในขอบเขต hierarchy)"""
    if not user_ctx.get("user_id"):
        raise HTTPException(status_code=401, detail="ต้องเข้าสู่ระบบ")

    async with pool.acquire() as conn:
        try:
            await require_permission_anywhere(conn, user_ctx["user_id"], "MANAGE_STUDENTS")
        except ForbiddenError as e:
            raise HTTPException(status_code=403, detail=str(e))

        # ข้อมูลเป้าหมาย (ตำแหน่งปัจจุบัน + ระดับชั้น) — ใช้เช็ค hierarchy/grade scope
        target = await conn.fetchrow(
            """
            SELECT s.class_role AS cur_role, r.level AS grade
            FROM students s
            LEFT JOIN rooms r ON r.id = s.room_id
            WHERE s.id = $1 AND s.deleted_at IS NULL
            """,
            student_id
        )
        if not target:
            raise HTTPException(status_code=404, detail="ไม่พบนักเรียน")

        new_role = req.class_role if req.class_role is not None else target["cur_role"]
        try:
            await _assert_manage_target(
                conn, user_ctx["user_id"],
                target_role=new_role,
                current_role=target["cur_role"],
                target_grade=target["grade"],
            )
        except ForbiddenError as e:
            raise HTTPException(status_code=403, detail=str(e))

    try:
        await student_service.update_student(
            pool, student_id,
            class_role=req.class_role,
            status=req.status,
            is_admin=req.is_admin,
            staff_level=req.staff_level,
            responsibilities=req.responsibilities,
            actor_user_id=user_ctx["user_id"],
            client_source="web",
        )
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"status": "ok"}


@router.post("/students", response_model=dict, status_code=201)
async def create_student(
    req: StudentCreateRequest,
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """เพิ่มผู้ใช้งานแบบ Manual (หน้า User Management — "เพิ่มผู้ใช้งาน")
    ใช้เมื่อ import Excel ไม่ครบ/ต้องการเพิ่มเฉพาะคน ต้องมี MANAGE_STUDENTS + อยู่ในขอบเขต hierarchy"""
    if not user_ctx.get("user_id"):
        raise HTTPException(status_code=401, detail="ต้องเข้าสู่ระบบ")

    async with pool.acquire() as conn:
        try:
            await require_permission_anywhere(conn, user_ctx["user_id"], "MANAGE_STUDENTS")
        except ForbiddenError as e:
            raise HTTPException(status_code=403, detail=str(e))

        # หาระดับชั้นของห้องเป้าหมาย (ถ้าระบุ) — ใช้เช็ค grade scope
        target_grade = None
        if req.room_code:
            target_grade = await conn.fetchval(
                "SELECT level FROM rooms WHERE room_code = $1 AND deleted_at IS NULL",
                req.room_code
            )
            if not target_grade:
                raise HTTPException(status_code=404, detail=f"ไม่พบห้องเรียน {req.room_code}")

        try:
            await _assert_manage_target(
                conn, user_ctx["user_id"],
                target_role=req.class_role,
                current_role=None,
                target_grade=target_grade,
            )
        except ForbiddenError as e:
            raise HTTPException(status_code=403, detail=str(e))

    try:
        new_student_id = await student_service.create_student(
            pool,
            username=req.username,
            password=req.password,
            prefix=req.prefix,
            first_name=req.first_name,
            last_name=req.last_name,
            nickname=req.nickname,
            room_code=req.room_code,
            class_role=req.class_role,
            responsibilities=req.responsibilities,
            actor_user_id=user_ctx["user_id"],
            client_source="web",
        )
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))

    return {"status": "ok", "student_id": new_student_id}
