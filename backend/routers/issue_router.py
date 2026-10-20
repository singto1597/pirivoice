from fastapi import APIRouter, Depends, HTTPException, Query
import asyncpg

from core.dependencies import get_db_pool, get_current_user
from core.rbac import require_permission_anywhere, get_manage_mode
from core.exceptions import NotFoundError, ForbiddenError, ValidationError, ConflictError
from core.categories import all_main_category_codes
from models.issue_schemas import (
    IssueCreateRequest, IssueUpdateRequest, IssueOut, IssueStepOut, IssueCountdownOut,
    StepCreateRequest, CountdownSetRequest, ChangeDestinationRequest, EscalateRequest,
    ApproveToPublicRequest, CommentCreateRequest, CommentOut, IssueListOut,
    MyIssueSummaryOut, ReassignRequest, OrphanedAssignmentsOut,
)
from services import issue_service
from services import audit_service

router = APIRouter(prefix="/issues", tags=["Issues"])


def _ensure_user(user_ctx: dict) -> int:
    """ดึง user_id หรือ raise 401"""
    uid = user_ctx.get("user_id")
    if not uid:
        raise HTTPException(status_code=401, detail="ต้องเข้าสู่ระบบ")
    return uid


def _err(e: Exception):
    """แปลง domain exception → HTTPException"""
    if isinstance(e, NotFoundError):
        return HTTPException(status_code=404, detail=str(e))
    if isinstance(e, ForbiddenError):
        return HTTPException(status_code=403, detail=str(e))
    if isinstance(e, ValidationError):
        return HTTPException(status_code=400, detail=str(e))
    if isinstance(e, ConflictError):
        return HTTPException(status_code=409, detail=str(e))
    return HTTPException(status_code=500, detail=f"เกิดข้อผิดพลาด: {e}")


@router.post("", response_model=IssueOut)
async def create_issue(
    req: IssueCreateRequest,
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """สร้างปัญหาใหม่ (เริ่มที่ระดับห้อง หรือระดับที่เลือกได้สำหรับผู้มีสิทธิ์)"""
    uid = _ensure_user(user_ctx)
    try:
        issue_id = await issue_service.create_issue(
            pool, uid, req.main_category, req.category, req.title,
            req.description, req.is_anonymous, req.room_id,
            req.start_level, req.requested_destination,
        )
        issue = await issue_service.get_issue(pool, uid, issue_id)
    except (NotFoundError, ValidationError, ForbiddenError) as e:
        raise _err(e)
    return IssueOut(**issue)


@router.get("", response_model=IssueListOut)
async def list_issues(
    mine: bool = Query(False, description="เฉพาะเรื่องที่ฉันแจ้ง"),
    received: bool = Query(False, description="เรื่องที่ฉันรับ/อยู่ในระดับฉัน (มองเห็นได้ทั้งหมด)"),
    status: str | None = Query(None),
    category: str | None = Query(None),
    main_category: str | None = Query(None, description="กรองตามหมวดหลัก: suggestion/wellbeing/report"),
    level: str | None = Query(None, description="กรองตามระดับ: room/level/council"),
    levels: str | None = Query(None, description="ระดับที่อยากดู (comma เช่น room,level) — เฉพาะ received=true, มองลงตามพีระมิด ≤ ระดับตัวเอง"),
    q: str | None = Query(None, max_length=100, description="ค้นหาแบบคำต่อคำ: ชื่อเรื่อง/คำอธิบาย/ห้อง/ชื่อคน"),
    sort: str = Query("desc", pattern="^(asc|desc)$", description="เรียงตามวันที่สร้าง: asc=เก่าไปใหม่, desc=ใหม่ไปเก่า"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """รายการปัญหา (visibility ตามพีระมิด + ตัวกรอง + ค้นหา + แบ่งหน้า)"""
    uid = _ensure_user(user_ctx)
    if main_category and main_category not in all_main_category_codes():
        raise HTTPException(status_code=400, detail=f"หมวดหลักไม่ถูกต้อง: {main_category}")
    if levels:
        invalid = [lv for lv in (s.strip() for s in levels.split(",")) if lv and lv not in issue_service.LEVEL_ORDER]
        if invalid:
            raise HTTPException(status_code=400, detail=f"ระดับไม่ถูกต้อง: {', '.join(invalid)}")
    result = await issue_service.list_issues(
        pool, uid, only_mine=mine, received=received,
        status_filter=status, category=category, main_category=main_category,
        level_filter=level, levels=levels, q=q, sort=sort, limit=limit, offset=offset,
    )
    # 🛡️ Audit: ดึงรายการเรื่อง (best-effort)
    await audit_service.log_read(pool, uid, "READ_ISSUES", "issue", endpoint="GET /api/issues")
    total = result["total"]
    page = offset // limit + 1
    pages = (total + limit - 1) // limit if total else 0
    return IssueListOut(
        items=[IssueOut(**i) for i in result["items"]],
        total=total, page=page, page_size=limit, pages=pages,
    )


@router.get("/summary", response_model=MyIssueSummaryOut)
async def my_issue_summary(
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """
    สรุปเรื่องที่ฉันแจ้ง (หน้า Home/Welcome): จำนวนรวม + นับตามสถานะ 6 สถานะ + 5 เรื่องล่าสุด
    — แทนการเรียก listIssues({mine:true}) หลายครั้ง ต้องอยู่ก่อน GET /{issue_id} กัน route ชน
    """
    uid = _ensure_user(user_ctx)
    result = await issue_service.my_issue_summary(pool, uid)
    # 🛡️ Audit: อ่านสรุปเรื่องของตัวเอง (best-effort)
    await audit_service.log_read(
        pool, uid, "READ_ISSUES", "issue", endpoint="GET /api/issues/summary"
    )
    return MyIssueSummaryOut(**result)


@router.get("/orphaned-assignments", response_model=OrphanedAssignmentsOut)
async def list_orphaned_assignments(
    year_id: int | None = Query(None, description="ไม่ระบุ = ปีปัจจุบัน"),
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """🔁 เรื่องที่ยังเปิดอยู่แต่ผู้รับไม่มีสมาชิกภาพในปีนี้ (ผลจาก rollover)

    ⚠️ **ประกาศก่อน `GET /{issue_id}` โดยเจตนา** — ถ้าอยู่หลัง เส้นทางนี้จะถูกจับด้วย
       `{issue_id}` (แปลงเป็น int ไม่ได้ → 422) ไม่ใช่ 404 ที่อ่านรู้เรื่อง

    ประตู: `MANAGE_STUDENTS` **และ** โหมดจัดการระดับโรงเรียน — การมอบหมายข้ามห้อง/ข้ามระดับ
    เป็นเรื่องส่วนกลาง (ครูระดับชั้นย้ายเรื่องข้ามระดับไม่ได้)
    """
    uid = _ensure_user(user_ctx)
    async with pool.acquire() as conn:
        try:
            await require_permission_anywhere(conn, uid, "MANAGE_STUDENTS")
            mode = await get_manage_mode(conn, uid)
            if mode["mode"] != "school":
                raise ForbiddenError("เฉพาะผู้ดูแลระดับโรงเรียนเท่านั้น")
        except ForbiddenError as e:
            raise HTTPException(status_code=403, detail=str(e))

    try:
        return await issue_service.list_orphaned_assignments(pool, year_id=year_id)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{issue_id}/reassign", response_model=dict)
async def reassign_issue(
    issue_id: int,
    req: ReassignRequest,
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """มอบหมายเรื่องค้างให้ผู้รับคนใหม่ (ต้อง active ในปีปัจจุบัน) — เขียน history + แจ้งเตือน + audit"""
    uid = _ensure_user(user_ctx)
    async with pool.acquire() as conn:
        try:
            await require_permission_anywhere(conn, uid, "MANAGE_STUDENTS")
            mode = await get_manage_mode(conn, uid)
            if mode["mode"] != "school":
                raise ForbiddenError("เฉพาะผู้ดูแลระดับโรงเรียนเท่านั้น")
        except ForbiddenError as e:
            raise HTTPException(status_code=403, detail=str(e))

    try:
        return await issue_service.reassign_issue(
            pool, user_id=uid, issue_id=issue_id,
            to_user_id=req.to_user_id, note=req.note,
        )
    except (NotFoundError, ForbiddenError, ValidationError, ConflictError) as e:
        raise _err(e)


@router.get("/{issue_id}", response_model=IssueOut)
async def get_issue(
    issue_id: int,
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """ดูรายละเอียดปัญหา"""
    uid = _ensure_user(user_ctx)
    try:
        issue = await issue_service.get_issue(pool, uid, issue_id)
    except (NotFoundError, ForbiddenError) as e:
        raise _err(e)
    # 🛡️ Audit: ดูรายละเอียดเรื่อง (best-effort)
    await audit_service.log_read(
        pool, uid, "READ_ISSUE", "issue", entity_id=issue_id,
        endpoint=f"GET /api/issues/{issue_id}",
        room_id=issue.get("room_id") if hasattr(issue, "get") else None,
    )
    return IssueOut(**issue)


@router.patch("/{issue_id}", response_model=IssueOut)
async def update_issue(
    issue_id: int,
    req: IssueUpdateRequest,
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """แก้ไขเรื่อง (ผู้แจ้ง/admin) — ส่งเฉพาะฟิลด์ที่ต้องการแก้"""
    uid = _ensure_user(user_ctx)
    try:
        await issue_service.update_issue(
            pool, uid, issue_id, **req.model_dump(exclude_unset=True)
        )
        issue = await issue_service.get_issue(pool, uid, issue_id)
    except (NotFoundError, ForbiddenError, ValidationError) as e:
        raise _err(e)
    return IssueOut(**issue)


# ==================== อนุมัติเผยแพร่สาธารณะ (PIRI Boards) ====================
@router.post("/{issue_id}/approve-to-public", response_model=dict)
async def approve_to_public(
    issue_id: int,
    req: ApproveToPublicRequest,
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """🏛️ สภานักเรียน/แอดมิน อนุมัติเรื่องขอเผยแพร่สาธารณะ → สร้าง PIRI Board + ปิดเรื่อง"""
    uid = _ensure_user(user_ctx)
    try:
        board_id = await issue_service.approve_to_public(
            pool, uid, issue_id, req.board_type,
            vote_choices=req.vote_choices, allow_comments=req.allow_comments,
        )
    except (NotFoundError, ForbiddenError, ValidationError, ConflictError) as e:
        raise _err(e)
    return {"board_id": board_id, "status": "approved"}


# ==================== เปลี่ยนปลายทาง (แก้แจ้งผิด — normal/vote/talk) ====================
@router.patch("/{issue_id}/destination", response_model=IssueOut)
async def change_destination(
    issue_id: int,
    req: ChangeDestinationRequest,
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """🔁 เปลี่ยนปลายทางของเรื่อง (หัวหน้าห้อง/รอง + สภานักเรียน/แอดมิน)
    เช่น แจ้งเป็น 'ดำเนินการปกติ' แต่ควรเป็น 'บอร์ดพูดคุย' → เปลี่ยนแล้วส่งสภานักเรียนพิจารณา"""
    uid = _ensure_user(user_ctx)
    try:
        await issue_service.change_destination(pool, uid, issue_id, req.requested_destination)
        issue = await issue_service.get_issue(pool, uid, issue_id)
    except (NotFoundError, ForbiddenError, ValidationError, ConflictError) as e:
        raise _err(e)
    return IssueOut(**issue)


# ==================== รับเรื่อง + Countdown ====================
@router.post("/{issue_id}/accept", response_model=dict)
async def accept_issue(
    issue_id: int,
    req: CountdownSetRequest,
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """รับเรื่อง + ตั้งเวลานับถอยหลัง (กี่วัน)"""
    uid = _ensure_user(user_ctx)
    try:
        await issue_service.accept_issue(pool, uid, issue_id, req.estimated_days)
    except (NotFoundError, ForbiddenError, ValidationError) as e:
        raise _err(e)
    return {"status": "accepted"}


@router.patch("/{issue_id}/countdown", response_model=dict)
async def update_countdown(
    issue_id: int,
    req: CountdownSetRequest,
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """แก้ไข countdown (ยืดเวลา)"""
    uid = _ensure_user(user_ctx)
    try:
        await issue_service.update_countdown(pool, uid, issue_id, req.estimated_days)
    except (NotFoundError, ForbiddenError, ValidationError) as e:
        raise _err(e)
    return {"status": "ok"}


# ==================== Steps ====================
@router.post("/{issue_id}/steps", response_model=IssueStepOut)
async def add_step(
    issue_id: int,
    req: StepCreateRequest,
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """เพิ่มขั้นตอนการดำเนินงาน"""
    uid = _ensure_user(user_ctx)
    try:
        step_id = await issue_service.add_step(pool, uid, issue_id, req.step_title, req.step_detail)
    except (NotFoundError, ForbiddenError, ValidationError) as e:
        raise _err(e)

    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM issue_steps WHERE id = $1", step_id)
    return IssueStepOut(**issue_service._step_to_dict(row))


@router.patch("/{issue_id}/steps/{step_id}/complete", response_model=dict)
async def complete_step(
    issue_id: int,
    step_id: int,
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """ทำขั้นตอนสำเร็จ"""
    uid = _ensure_user(user_ctx)
    try:
        await issue_service.complete_step(pool, uid, issue_id, step_id)
    except (NotFoundError, ForbiddenError) as e:
        raise _err(e)
    return {"status": "ok"}


# ==================== Escalate / Resolve ====================
@router.post("/{issue_id}/escalate", response_model=dict)
async def escalate_issue(
    issue_id: int,
    req: EscalateRequest,
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """ส่งต่อไประดับบน (เกินความสามารถ/ไม่ทัน)"""
    uid = _ensure_user(user_ctx)
    try:
        await issue_service.escalate_issue(pool, uid, issue_id, req.reason)
    except (NotFoundError, ForbiddenError, ValidationError) as e:
        raise _err(e)
    return {"status": "escalated"}


@router.post("/{issue_id}/resolve", response_model=dict)
async def resolve_issue(
    issue_id: int,
    req: EscalateRequest,  # reuse (มี field note? ใช้ reason เป็น note)
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """ปิดเรื่อง (แก้ไขเสร็จสิ้น)"""
    uid = _ensure_user(user_ctx)
    try:
        await issue_service.resolve_issue(pool, uid, issue_id, req.reason)
    except (NotFoundError, ForbiddenError, ValidationError) as e:
        raise _err(e)
    return {"status": "resolved"}


@router.post("/{issue_id}/cancel", response_model=dict)
async def cancel_issue(
    issue_id: int,
    req: EscalateRequest,  # reuse (field reason = เหตุผลยกเลิก/ปัดตก)
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """ยกเลิก/ปัดตกเรื่อง — ผู้แจ้งยกเลิก (cancelled) / ผู้ดูแลปัดตก (rejected)"""
    uid = _ensure_user(user_ctx)
    try:
        new_status = await issue_service.cancel_issue(pool, uid, issue_id, req.reason)
    except (NotFoundError, ForbiddenError, ValidationError) as e:
        raise _err(e)
    return {"status": new_status}


# ==================== คอมเมนต์ (แบบ YouTube) ====================
@router.post("/{issue_id}/comments", response_model=CommentOut)
async def create_comment(
    issue_id: int,
    req: CommentCreateRequest,
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """เพิ่มคอมเมนต์ในเรื่อง (ต้องมองเห็นเรื่องได้)"""
    uid = _ensure_user(user_ctx)
    try:
        comment_id = await issue_service.add_comment(pool, uid, issue_id, req.body)
        comment = await issue_service.get_comment(pool, uid, issue_id, comment_id)
    except (NotFoundError, ForbiddenError, ValidationError) as e:
        raise _err(e)
    return CommentOut(**comment)


@router.patch("/{issue_id}/comments/{comment_id}", response_model=CommentOut)
async def update_comment(
    issue_id: int,
    comment_id: int,
    req: CommentCreateRequest,
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """แก้คอมเมนต์ของตัวเอง"""
    uid = _ensure_user(user_ctx)
    try:
        await issue_service.update_comment(pool, uid, issue_id, comment_id, req.body)
        comment = await issue_service.get_comment(pool, uid, issue_id, comment_id)
    except (NotFoundError, ForbiddenError, ValidationError) as e:
        raise _err(e)
    return CommentOut(**comment)


@router.delete("/{issue_id}/comments/{comment_id}", response_model=dict)
async def delete_comment(
    issue_id: int,
    comment_id: int,
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """ลบคอมเมนต์ของตัวเอง (soft delete)"""
    uid = _ensure_user(user_ctx)
    try:
        await issue_service.delete_comment(pool, uid, issue_id, comment_id)
    except (NotFoundError, ForbiddenError) as e:
        raise _err(e)
    return {"status": "ok"}
