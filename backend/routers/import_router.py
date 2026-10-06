"""
Router: Import นักเรียนจาก Excel แบบ Queue (ARQ Worker)
======================================================
HTTP layer เท่านั้น — ไม่มี SQL / business logic (ตามกฎ backend.md)

Endpoints:
- POST /api/upload-student-excel      → อัปโหลด + ตรวจคอลัมน์ (เป๊ะ) + สร้าง job PENDING
- POST /api/start-import-job/{id}     → ยิง job_id เข้า Redis (ARQ) ให้ worker เริ่มงาน
- GET  /api/import-jobs               → รายการงานทั้งหมด + progress
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, Response
import asyncpg

from core.config import settings
from core.dependencies import get_db_pool, get_current_user
from core.rbac import require_permission_anywhere, get_access_scope
from core.exceptions import NotFoundError, ForbiddenError, ValidationError, ConflictError, ServiceUnavailableError
from models.import_schemas import ImportJobOut
from services import import_service
from services import audit_service

router = APIRouter(tags=["Student Import"])

MAX_FILE_BYTES = settings.IMPORT_FILE_SIZE_LIMIT_MB * 1024 * 1024


async def _require_manage_students(pool: asyncpg.Pool, user_id: int) -> dict:
    """เช็คสิทธิ์ MANAGE_STUDENTS + คืน access scope (ครูทั่วไปนำเข้าได้เฉพาะระดับชั้นตัวเอง)"""
    async with pool.acquire() as conn:
        try:
            await require_permission_anywhere(conn, user_id, "MANAGE_STUDENTS")
        except ForbiddenError as e:
            raise HTTPException(status_code=403, detail=str(e))
        scope = await get_access_scope(conn, user_id)
    return scope


@router.get("/import-student-template")
async def download_import_template(
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """
    ดาวน์โหลดตัวอย่างไฟล์ Excel (.xlsx) ที่ระบบอ่านได้
    - หัวคอลัมน์มาจาก KNOWN_COLUMNS (แหล่งเดียวกับตัวตรวจ — กัน format drift)
    - ไม่แตะฐานข้อมูล → เร็ว/ไม่เสี่ยง; ต้องมีสิทธิ์ MANAGE_STUDENTS เท่านั้น (ตรงกับหน้า import)
    """
    uid = user_ctx.get("user_id")
    if not uid:
        raise HTTPException(status_code=401, detail="ต้องเข้าสู่ระบบ")

    await _require_manage_students(pool, uid)

    content = import_service.build_template_xlsx_bytes()
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="student_import_template.xlsx"'},
    )


@router.post("/upload-student-excel", response_model=ImportJobOut)
async def upload_student_excel(
    file: UploadFile = File(...),
    default_password: str = Query("1234"),
    academic_year_id: int | None = Query(
        None,
        description='ปีการศึกษาของชุดที่นำเข้า — ไม่ระบุ = ผ่อนปรน (แถวไม่กรอกปี → ปีปัจจุบัน · กรอกปีใดก็ได้ที่มีในระบบ)',
    ),
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """
    อัปโหลดไฟล์ Excel (.xlsx) เพื่อนำเข้านักเรียน
    - ตรวจคอลัมน์แบบเป๊ะ: ต้องมี รหัสนักเรียน | ห้องเรียน | เลขที่ (+ ไม่มีคอลัมน์เกิน/ซ้ำ)
    - บันทึกลง storage + สร้าง record (status=PENDING) — ยังไม่เริ่มทำงาน
    - เริ่มงานจริงต้องกด POST /api/start-import-job/{id} อีกครั้ง

    🌟 `academic_year_id` (migration 028) — ระบุปีของชุดนี้ ⇒ แถวที่ไม่กรอกคอลัมน์
       "ปีการศึกษา" ตกมาอยู่ปีนี้ และแถวที่กรอก **ต้องตรงกัน** ไม่งั้นเป็น error รายแถว
       (กันไฟล์ที่ค้างมาจากปีก่อนถูกนำเข้าทับลงปีใหม่เงียบ ๆ · ปีที่ระบุต้องมีอยู่แล้ว
        — ระบบ **ไม่สร้างปี** จากที่ผู้ใช้อัปโหลดมา)
    """
    uid = user_ctx.get("user_id")
    if not uid:
        raise HTTPException(status_code=401, detail="ต้องเข้าสู่ระบบ")

    # เฉพาะ .xlsx เท่านั้น — openpyxl อ่าน legacy .xls (BIFF/OLE) ไม่ได้
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="กรุณาอัปโหลดไฟล์ .xlsx")

    scope = await _require_manage_students(pool, uid)

    # 🛡️ ครูที่ยังไม่มีระดับชั้น (scope='none') — มีสิทธิ์ MANAGE_STUDENTS แต่ไม่มีขอบเขต นำเข้าไม่ได้
    # (ไม่งั้นจะ "นำเข้าทั้งโรงเรียน" โดยไม่รู้ว่าดูแลระดับไหน)
    if scope["scope"] == "none":
        raise HTTPException(
            status_code=403,
            detail="คุณยังไม่มีระดับชั้นที่รับผิดชอบ — กรุณาให้แอดมินกำหนดระดับชั้นก่อนจึงจะนำเข้านักเรียนได้",
        )

    # รหัสผ่านเริ่มต้นรองรับเฉพาะ 1234 (ระบบตั้งเป็นเลขรหัสนักเรียน) — กันค่ามั่วๆ/ผูกกับข้อมูลของระบบ
    if default_password not in ("", "1234"):
        raise HTTPException(
            status_code=400,
            detail="กำหนดรหัสผ่านเริ่มต้นได้เฉพาะค่า 1234 (ระบบจะตั้งเป็นเลขรหัสนักเรียน) — ไม่อนุญาตให้กำหนดเอง",
        )

    allowed_level = scope.get("level") if scope["scope"] == "level" else None

    # อ่านไฟล์พร้อมจำกัดขนาด (กันไฟล์ยักษ์ลาก worker)
    content = await file.read(MAX_FILE_BYTES + 1)
    if len(content) > MAX_FILE_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"ไฟล์ใหญ่เกิน {settings.IMPORT_FILE_SIZE_LIMIT_MB} MB — กรุณาแบ่งไฟล์",
        )

    try:
        job = await import_service.create_import_job(
            pool,
            content=content,
            original_filename=file.filename,
            default_password=default_password,
            allowed_level=allowed_level,
            academic_year_id=academic_year_id,
            actor_user_id=uid,
            client_source="web",
        )
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return ImportJobOut.from_db_row(job)


@router.post("/start-import-job/{job_id}", response_model=ImportJobOut)
async def start_import_job(
    job_id: int,
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """กดสั่งรันงาน: ยิง job_id เข้า Redis (ARQ) → worker เริ่มทยอย insert"""
    uid = user_ctx.get("user_id")
    if not uid:
        raise HTTPException(status_code=401, detail="ต้องเข้าสู่ระบบ")

    scope = await _require_manage_students(pool, uid)

    try:
        job = await import_service.start_import_job(
            pool, job_id,
            actor_user_id=uid,
            client_source="web",
            access_scope=scope["scope"],
            access_level=scope.get("level") if scope["scope"] == "level" else None,
        )
    except ForbiddenError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ServiceUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e))

    return ImportJobOut.from_db_row(job)


@router.get("/import-jobs", response_model=list[ImportJobOut])
async def list_import_jobs(
    limit: int = Query(50, ge=1, le=200),
    user_ctx: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    """รายการงาน import ทั้งหมด + progress (ใหม่สุดก่อน) — ใช้ทำ progress bar"""
    uid = user_ctx.get("user_id")
    if not uid:
        raise HTTPException(status_code=401, detail="ต้องเข้าสู่ระบบ")

    scope = await _require_manage_students(pool, uid)

    jobs = await import_service.list_import_jobs(
        pool,
        limit=limit,
        access_scope=scope["scope"],
        access_level=scope.get("level") if scope["scope"] == "level" else None,
    )
    # 🛡️ Audit: ดูงานนำเข้า (best-effort)
    await audit_service.log_read(pool, uid, "READ_IMPORT_JOBS", "student_import_job", endpoint="GET /api/import-jobs")
    return [ImportJobOut.from_db_row(j) for j in jobs]
