from fastapi import APIRouter, Depends, HTTPException, Query, Request
import asyncpg

from core.dependencies import get_db_pool, get_current_user
from core.exceptions import NotFoundError, ForbiddenError, ValidationError, ConflictError
from models.board_schemas import (
    VoteSubmitRequest, CommentCreateRequest, VoteResultOut,
    BoardSummaryOut, BoardDetailOut, BoardCommentOut, BoardListOut,
    ReportCreateRequest, HideCommentRequest, HideBoardRequest,
    ResolveReportRequest, ReportOut, ReportListOut,
    SuggestionCreateRequest, SuggestionCreatedOut,
)
from services import board_service
from services import board_moderation_service
from services import audit_service

router = APIRouter(prefix="/boards", tags=["PIRI Boards"])


def _ensure_user(user_ctx: dict) -> int:
    """ดึง user_id หรือ raise 401"""
    uid = user_ctx.get("user_id")
    if not uid:
        raise HTTPException(status_code=401, detail="ต้องเข้าสู่ระบบ")
    return uid


def _err(e: Exception):
    """แปลง domain exception → HTTPException (pattern เดียวกับ issue_router)"""
    if isinstance(e, NotFoundError):
        return HTTPException(status_code=404, detail=str(e))
    if isinstance(e, ForbiddenError):
        return HTTPException(status_code=403, detail=str(e))
    if isinstance(e, ValidationError):
        return HTTPException(status_code=400, detail=str(e))
    if isinstance(e, ConflictError):
        return HTTPException(status_code=409, detail=str(e))
    return HTTPException(status_code=500, detail=f"เกิดข้อผิดพลาด: {e}")


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


# ===================== feed board =====================
@router.get("", response_model=BoardListOut)
async def list_public_boards(
    board_type: str | None = Query(
        None, pattern="^(vote|talk|suggestion)$",
        description="กรองตามประเภท: vote/talk/suggestion",
    ),
    q: str | None = Query(None, max_length=100, description="ค้นหา: ชื่อ/รายละเอียด board"),
    limit: int = Query(20, ge=1, le=50),
    offset: int = Query(0, ge=0),
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """📋 feed board สาธารณะ (active เท่านั้น) — ทุกคนที่ล็อกอินเห็นได้ (ไม่ต้องเช็คระดับ)"""
    uid = _ensure_user(user_ctx)
    result = await board_service.list_public_boards(
        pool, board_type=board_type, q=q, limit=limit, offset=offset
    )
    # 🛡️ Audit: เปิด feed (best-effort)
    await audit_service.log_read(pool, uid, "READ_PUBLIC_BOARDS", "piri_board", endpoint="GET /api/boards")
    return BoardListOut(
        items=[BoardSummaryOut(**b) for b in result["items"]],
        total=result["total"], page=result["page"],
        page_size=result["page_size"], pages=result["pages"],
    )


# ===================== คิวรายงาน (สภา/แอดมิน — moderation) =====================
# ⚠️ ต้องอยู่ก่อน GET /{board_id} (ไม่งั้น 'reports' ถูก match เป็น board_id → 422)
@router.get("/reports", response_model=ReportListOut)
async def list_reports(
    status: str | None = Query(None, pattern="^(open|resolved|dismissed)$"),
    reason: str | None = Query(None, pattern="^(bullying|profanity|spam|privacy|other)$"),
    q: str | None = Query(None, max_length=100, description="ค้นหา: ชื่อ board / เนื้อความคอมเมนต์"),
    limit: int = Query(20, ge=1, le=50),
    offset: int = Query(0, ge=0),
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """📋 คิวรายงานความไม่เหมาะสม (เฉพาะสภานักเรียน/แอดมิน) — กรอง/ค้นหา + แบ่งหน้า"""
    uid = _ensure_user(user_ctx)
    try:
        result = await board_moderation_service.list_reports(
            pool, uid, status=status, reason=reason, q=q, limit=limit, offset=offset
        )
    except ForbiddenError as e:
        raise _err(e)
    return ReportListOut(
        items=[ReportOut(**r) for r in result["items"]],
        total=result["total"], page=result["page"],
        page_size=result["page_size"], pages=result["pages"],
    )


@router.get("/{board_id}", response_model=BoardDetailOut)
async def get_board_detail(
    board_id: int,
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """🔍 รายละเอียด board: vote → choices + my_vote; talk → comments (threaded)"""
    uid = _ensure_user(user_ctx)
    try:
        detail = await board_service.get_board_detail(pool, uid, board_id)
    except NotFoundError as e:
        raise _err(e)
    # 🛡️ Audit: ดู board (best-effort)
    await audit_service.log_read(
        pool, uid, "READ_BOARD", "piri_board", entity_id=board_id,
        endpoint=f"GET /api/boards/{board_id}",
    )
    return BoardDetailOut(**detail)


# ===================== E1: เสนอไอเดีย (ผู้ใช้ทั่วไป — ไม่ผ่านด่านสภา) =====================
# ⚠️ **ทำไมเป็น route เฉพาะ `/suggestions` ไม่ใช่ `POST /boards` ทั่วไป**
#    endpoint สร้างแบบเปิดกว้างจะให้ใครก็ได้สร้าง board `talk`/`vote` ตรง ๆ
#    ⇒ **เลี่ยงด่านอนุมัติของสภาทั้งด่าน** (บอร์ดสองชนิดนั้นต้องมาจาก
#    `issue_service.approve_to_public()` ที่ตรวจ `_has_council_authority` + ผูก issue ต้นทาง)
#    ⇒ route นี้ **สร้างได้ชนิดเดียว** และไม่รับ `board_type` จาก client เลย
#    ⇒ การเพิ่มชนิดใหม่ในอนาคตต้อง "เพิ่ม route" ซึ่งเป็นการตัดสินใจที่มองเห็นได้
#      ต่างจากการเพิ่มค่าที่รับได้ในพารามิเตอร์ (ซึ่งเงียบกว่า)
#
# ⚠️ **ไม่ต้องใช้ `require_permission`** — สิทธิ์คือ "เป็นผู้ใช้ที่ล็อกอินแล้ว" (ตัวตนคือสิทธิ์)
#    แบบเดียวกับ `/api/issues` (แจ้งเรื่อง) · **แต่ต้องมี `_ensure_user`** เพราะ
#    `get_current_user` คืน `{"user_id": None}` เมื่อเรียกด้วย `X-API-Key` (system RPC)
@router.post("/suggestions", response_model=SuggestionCreatedOut, status_code=201)
async def create_suggestion(
    req: SuggestionCreateRequest,
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """💡 เสนอไอเดีย/ข้อเสนอแนะ — ขึ้นบอร์ดสาธารณะทันที (สภาซ่อนย้อนหลังได้)

    - **ไม่แจ้งเตือนใคร** โดยเจตนา (ผู้ใช้เลือก "ไม่แจ้งใครเลย") — กัน push storm
    - **ไม่ต้องมี issue ต้นทาง** และไม่ต้องรออนุมัติ — ต่างจาก `talk`/`vote`
    """
    uid = _ensure_user(user_ctx)
    # `.strip()` ที่ชั้น router: `min_length` ของ pydantic นับ " " เป็น 1 ตัวอักษร ⇒
    # `"   "` ผ่าน validation ได้แต่กลายเป็นหัวข้อว่างในบอร์ด (strip ก่อนตรวจจะต้องทำใน
    # schema — ซึ่งจะกระทบ response ที่ echo กลับ ⇒ ทำที่นี่ที่เดียวและคืนค่าที่ strip แล้ว)
    title = req.title.strip()
    description = req.description.strip()
    if len(title) < 3 or not description:
        raise HTTPException(status_code=422, detail="หัวข้อต้องมีอย่างน้อย 3 ตัวอักษร และรายละเอียดห้ามว่าง")

    created = await board_service.create_suggestion(
        pool, uid,
        title=title, description=description, is_anonymous=req.is_anonymous,
    )
    return SuggestionCreatedOut(
        id=created["id"],
        board_type=board_service.BOARD_TYPE_SUGGESTION,
        title=created["title"],
        created_at=created["created_at"],
    )


# ===================== โหวต (PIRI Vote) =====================
@router.post("/{board_id}/vote", response_model=VoteResultOut)
async def submit_vote(
    board_id: int,
    req: VoteSubmitRequest,
    request: Request,
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """🗳️ โหวต board แบบ vote — 1 เสียงต่อ board (โหวตซ้ำ → 409)"""
    uid = _ensure_user(user_ctx)
    try:
        result = await board_service.submit_vote(
            pool, uid, board_id, req.choice_id,
            ip=_client_ip(request), user_agent=request.headers.get("user-agent"),
        )
    except (NotFoundError, ValidationError, ConflictError) as e:
        raise _err(e)
    return result


# ===================== คอมเมนต์ (PIRI Talk) =====================
@router.post("/{board_id}/comments", response_model=BoardCommentOut)
async def add_comment(
    board_id: int,
    req: CommentCreateRequest,
    request: Request,
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """💬 คอมเมนต์/รีพลายใน board (talk เท่านั้น — reply ผ่าน parent_id)"""
    uid = _ensure_user(user_ctx)
    try:
        comment_id = await board_service.add_comment(
            pool, uid, board_id, req.body, parent_id=req.parent_id,
            ip=_client_ip(request), user_agent=request.headers.get("user-agent"),
        )
        comment = await board_service.get_comment(pool, board_id, comment_id)
    except (NotFoundError, ForbiddenError, ValidationError) as e:
        raise _err(e)
    return BoardCommentOut(**comment)


# ===================== Report (นักเรียนแจ้งความไม่เหมาะสม) =====================
@router.post("/{board_id}/comments/{comment_id}/report", response_model=dict)
async def report_comment(
    board_id: int,
    comment_id: int,
    req: ReportCreateRequest,
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """🚩 แจ้งความไม่เหมาะสมของคอมเมนต์ (ทุกคน) → สภานักเรียนรอจัดการ (แจ้งซ้ำ → 409)"""
    uid = _ensure_user(user_ctx)
    try:
        result = await board_moderation_service.report_comment(
            pool, uid, board_id, comment_id, reason=req.reason, detail=req.detail
        )
    except (NotFoundError, ValidationError, ConflictError) as e:
        raise _err(e)
    return result


# ===================== Moderation: ซ่อน/แสดงคอมเมนต์ (สภา/แอดมิน) =====================
@router.post("/{board_id}/comments/{comment_id}/hide", response_model=dict)
async def hide_comment(
    board_id: int,
    comment_id: int,
    req: HideCommentRequest,
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """🛡️ ซ่อนคอมเมนต์ + ลูกหลาน (subtree) — ลด comment_count ตามจำนวนที่ซ่อนจริง"""
    uid = _ensure_user(user_ctx)
    try:
        result = await board_moderation_service.hide_comment(
            pool, uid, board_id, comment_id, reason=req.reason
        )
    except (NotFoundError, ForbiddenError, ConflictError, ValidationError) as e:
        raise _err(e)
    return result


@router.post("/{board_id}/comments/{comment_id}/unhide", response_model=dict)
async def unhide_comment(
    board_id: int,
    comment_id: int,
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """🛡️ กลับมาแสดงคอมเมนต์ + ลูกหลานที่ถูกซ่อน — เพิ่ม comment_count คืน"""
    uid = _ensure_user(user_ctx)
    try:
        result = await board_moderation_service.unhide_comment(pool, uid, board_id, comment_id)
    except (NotFoundError, ForbiddenError, ConflictError) as e:
        raise _err(e)
    return result


# ===================== Moderation: ซ่อน/แสดง board (สภา/แอดมิน) =====================
@router.post("/{board_id}/hide", response_model=dict)
async def hide_board(
    board_id: int,
    req: HideBoardRequest,
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """🛡️ ซ่อน board ทั้งบอร์ด — หลุดจาก feed + detail 404 (ไม่มีข้อมูลรั่ว)"""
    uid = _ensure_user(user_ctx)
    try:
        result = await board_moderation_service.hide_board(pool, uid, board_id, reason=req.reason)
    except (NotFoundError, ForbiddenError, ConflictError, ValidationError) as e:
        raise _err(e)
    return result


@router.post("/{board_id}/unhide", response_model=dict)
async def unhide_board(
    board_id: int,
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """🛡️ กลับมาแสดง board (status='active')"""
    uid = _ensure_user(user_ctx)
    try:
        result = await board_moderation_service.unhide_board(pool, uid, board_id)
    except (NotFoundError, ForbiddenError, ConflictError) as e:
        raise _err(e)
    return result


# ===================== จัดการรายงาน (สภา/แอดมิน) =====================
@router.post("/reports/{report_id}/resolve", response_model=dict)
async def resolve_report(
    report_id: int,
    req: ResolveReportRequest,
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """✅ จัดการรายงาน: action='hide' (ซ่อนคอมเมนต์ + ลด counter) / 'dismiss' (ปัดตก ไม่ซ่อน)"""
    uid = _ensure_user(user_ctx)
    try:
        result = await board_moderation_service.resolve_report(
            pool, uid, report_id, action=req.action, note=req.note
        )
    except (NotFoundError, ForbiddenError, ConflictError, ValidationError) as e:
        raise _err(e)
    return result
