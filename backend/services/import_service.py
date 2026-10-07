"""
Service ชั้นธุรกิจสำหรับระบบ Import นักเรียนจาก Excel แบบ Queue (ARQ Worker)
=============================================================================
แทนที่ `import_students_from_excel` แบบซิงโครนัส (รันยาวๆ ค้าง request) ด้วย
สถาปัตยกรรมคิว:

  POST /upload-student-excel   → เช็คคอลัมน์แบบเป๊ะ + บันทึกไฟล์ + สร้าง job (PENDING)
  POST /start-import-job/{id}  → ยิง job_id เข้า Redis (ARQ) → worker เริ่มทำงาน
  GET  /import-jobs            → ดูสถานะ / ความคืบหน้า (progress bar)

Status flow: PENDING → QUEUED → PROCESSING → COMPLETED / FAILED
"""
import json
import logging
import os
import uuid
import io
from typing import Optional, Tuple, List

import asyncpg
import openpyxl
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from core.config import settings
from core.exceptions import (
    NotFoundError, ForbiddenError, ValidationError, ConflictError, ServiceUnavailableError,
)
from core.logger import AuditLogger
from core.queues import IMPORT_QUEUE
from core.rbac import get_role_permissions, get_role_is_admin
from models.import_schemas import (
    IMPORT_STATUS_PENDING,
    IMPORT_STATUS_QUEUED,
    IMPORT_STATUS_PROCESSING,
    IMPORT_STATUS_COMPLETED,
    IMPORT_STATUS_FAILED,
    RESTARTABLE_STATUS,
    CLAIMABLE_STATUS,
)
from services import auth_service, year_service
from services.student_service import map_role_label

logger = logging.getLogger("IMPORT_SERVICE")

# ============================================================
# 📋 คอลัมน์ของไฟล์ Excel (Format — ตรวจแบบเป๊ะ)
# ============================================================
KNOWN_COLUMNS = [
    "รหัสนักเรียน", "ห้องเรียน", "เลขที่",
    "คำนำหน้า", "ชื่อ", "นามสกุล", "ชื่อเล่น", "ตำแหน่งในห้องเรียน",
    # 🌟 "ปีการศึกษา" ( migration 028) — ต่อท้ายโดยเจตนา ⇒ ไฟล์เก่า 8 คอลัมน์ยังผ่าน
    #    (validate_columns ปฏิเสธแค่คอลัมน์ **แปลกปลอม** ไม่ได้บังคับว่าครบ)
    #    ช่องว่างในเซลล์ = ใช้ปีของ job · และ build_template_xlsx_bytes สร้างหัวตาราง
    #    จากลิสต์นี้ ⇒ template อัปเดตเองอัตโนมัติโดยไม่ต้องแก้โค้ด
    "ปีการศึกษา",
]
KNOWN_COLUMNS_SET = set(KNOWN_COLUMNS)
REQUIRED_COLUMNS = {"รหัสนักเรียน", "ห้องเรียน", "เลขที่"}

# จำนวน error รายแถวที่เก็บใน DB (กัน JSONB โตไม่มีขอบเขต)
MAX_ERROR_LOGS = 500

# 🛡️ Role ระดับโรงเรียน (ทำงานทั้งโรงเรียน ไม่ผูกห้อง/ระดับ) — สร้างได้เฉพาะผู้ดูแลทั้งโรงเรียน
# (allowed_level is None) เท่านั้น ครูระดับชั้น (allowed_level set) นำเข้า role เหล่านี้ไม่ได้
SCHOOL_WIDE_ROLES = {"admin", "teacher_council", "council_president", "council_member"}


# ============================================================
# 🧾 การอ่าน / ตรวจสอบไฟล์ Excel (Column validation แบบเป๊ะ)
# ============================================================
def validate_columns(header: list) -> dict:
    """
    ตรวจสอบหัวคอลัมน์แบบเคร่งครัด (ต้องเป๊ะ):
      1. ต้องมีคอลัมน์ที่จำเป็นครบ: รหัสนักเรียน, ห้องเรียน, เลขที่
      2. ห้ามมีคอลัมน์ซ้ำ
      3. ห้ามมีคอลัมน์ที่ไม่อยู่ใน KNOWN_COLUMNS (คอลัมน์เกิน/แปลกปลอม)

    คืน: {ชื่อคอลัมน์: index} (ข้ามคอลัมน์ว่าง)
    Raise: ValidationError พร้อมข้อความไทยที่ชี้ปัญหา
    """
    normalized = [str(c).strip() if c is not None else "" for c in header]

    if not normalized or all(c == "" for c in normalized):
        raise ValidationError("ไฟล์ว่างเปล่า — ไม่พบหัวคอลัมน์")

    seen: dict = {}
    for name in normalized:
        if name == "":
            continue
        if name in seen:
            raise ValidationError(f"พบคอลัมน์ซ้ำในไฟล์: '{name}'")
        seen[name] = True

    missing = [c for c in sorted(REQUIRED_COLUMNS) if c not in seen]
    if missing:
        raise ValidationError(
            f"ไม่พบคอลัมน์: {', '.join(missing)} — ไฟล์ต้องมีคอลัมน์ {', '.join(sorted(REQUIRED_COLUMNS))}"
        )

    unknown = [c for c in normalized if c and c not in KNOWN_COLUMNS_SET]
    if unknown:
        raise ValidationError(
            f"พบคอลัมน์ที่ไม่อยู่ในรูปแบบ: {', '.join(sorted(set(unknown)))} — รองรับเฉพาะ {', '.join(KNOWN_COLUMNS)}"
        )

    return {name: idx for idx, name in enumerate(normalized) if name}


def load_workbook_rows(file_bytes: bytes) -> Tuple[List, dict]:
    """
    อ่านไฟล์ .xlsx → (data_rows, col_index)
    - ตัดแถวว่างทิ้ง (คำนวณ total_rows = len(data_rows))
    - ตรวจคอลัมน์แบบเป๊ะ (validate_columns)
    Raise: ValidationError ถ้าอ่านไม่ได้ / คอลัมน์ผิด
    """
    try:
        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
    except Exception as e:
        raise ValidationError(f"อ่านไฟล์ Excel ไม่สำเร็จ — ตรวจสอบว่าเป็นไฟล์ .xlsx ที่ถูกต้อง ({e})")

    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        raise ValidationError("ไฟล์ว่างเปล่า")

    col_index = validate_columns(list(rows[0]))

    data_rows = []
    for r in rows[1:]:
        # ข้ามแถวที่ว่างทั้งแถว (ไม่มีข้อมูลอะไรเลย)
        if all(c is None or str(c).strip() == "" for c in r):
            continue
        data_rows.append(r)

    return data_rows, col_index


# ============================================================
# 📥 Template — ไฟล์ตัวอย่างสำหรับให้ผู้ใช้ดาวน์โหลด/ดูรูปแบบ
# ============================================================
def build_template_xlsx_bytes() -> bytes:
    """
    สร้างไฟล์ตัวอย่าง .xlsx ให้ครู/แอดมินดาวน์โหลดดูรูปแบบที่ระบบรองรับ

    - หัวคอลัมน์มาจาก KNOWN_COLUMNS — แหล่งเดียวกับ `validate_columns` (กัน format drift)
    - มีแถวตัวอย่าง 2 แถว (รหัสขึ้นต้น 000 — เห็นชัดว่าไม่ใช่รหัสนักเรียนจริง)
      เพื่อให้เห็น "ข้อมูลควรเป็นยังไง"; และถึงแม้ user อัปโหลดตัวอย่างเข้าโดยไม่ลบแถว
      `_process_single_row` จะข้ามแถวที่รหัสขึ้นต้น 000 (กันสร้าง account ปลอม) เสมอ
    - Sheet 'คำแนะนำ' อธิบายกฎรูปแบบเป็นภาษาไทย
    """
    wb = Workbook()
    ws = wb.active
    ws.title = "ข้อมูล"

    # หัวตาราง — ต้องตรง KNOWN_COLUMNS เป๊ะ (ระบบตรวจแบบเคร่งครัด)
    ws.append(KNOWN_COLUMNS)

    # แถวตัวอย่าง (000xx — ไม่ใช่รหัสนักเรียนจริง)
    ws.append(["00001", "ม.4/1", 1, "นาย", "สมชาย", "ใจดี", "ชาย", ""])
    ws.append(["00002", "ม.4/2", 1, "นางสาว", "สมหญิง", "รักเรียน", "หญิง", "หัวหน้าห้อง"])

    # ✨ ตกแต่งหัวตารางให้เด่น (แดงแบรนด์ + ตัวขาว) — ผู้ใช้เห็นได้ทันทีว่าคอลัมน์ไหนต้องมี
    header_fill = PatternFill(start_color="DC2626", end_color="DC2626", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF")
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center")

    # กำหนดความกว้างคอลัมน์ให้พอดีกับชื่อหัวตาราง
    for idx in range(1, len(KNOWN_COLUMNS) + 1):
        ws.column_dimensions[get_column_letter(idx)].width = max(16, len(KNOWN_COLUMNS[idx - 1]) * 2 + 4)

    # 📖 Sheet คำแนะนำ (ภาษาไทย)
    ws2 = wb.create_sheet("คำแนะนำ")
    tips = [
        "📌 รูปแบบไฟล์ที่ระบบอ่านได้ — หัวคอลัมน์ต้องตรงเป๊ะกับ Sheet 'ข้อมูล' เท่านั้น",
        "",
        "1. คอลัมน์ที่ต้องมี (จำเป็น): รหัสนักเรียน | ห้องเรียน | เลขที่",
        "   • ห้ามลบ / เปลี่ยนชื่อ / เพิ่มคอลัมน์ที่ไม่ใช่รูปแบบ — ระบบจะปฏิเสธไฟล์ (คอลัมน์ต้องเป๊ะ)",
        "   • คอลัมน์เสริม (เว้นได้): คำนำหน้า | ชื่อเล่น | ตำแหน่งในห้องเรียน — ชื่อ/นามสกุล เว้นได้อย่างละหนึ่ง แต่ห้ามเว้นทั้งสองคอลัมน์",
        "",
        "2. ตัวอย่างข้อมูลที่ถูกต้อง:",
        "   • รหัสนักเรียน: เลขประจำตัวนักเรียน เช่น 47001 (ใช้เป็น username + รหัสผ่านเริ่มต้น)",
        "   • ห้องเรียน: เช่น ม.4/1 (ระบบสร้างห้องอัตโนมัติถ้ายังไม่มี)",
        "   • เลขที่: ตัวเลข เช่น 1, 2, 3 ...",
        "   • ตำแหน่งในห้องเรียน: เว้นว่าง = นักเรียนธรรมดา; ระบุได้ เช่น หัวหน้าห้อง, รองวิชาการ,",
        "     รองวินัย, รองกิจกรรม, รองปฏิคม, ประธานระดับ, สภานักเรียน, ประธานสภา, ครู, ครูสภา, แอดมิน",
        "",
        "3. รหัสผ่านเริ่มต้นของนักเรียนที่นำเข้า = เลขรหัสนักเรียน (เช่น รหัส 47001 → เข้าสู่ระบบด้วย 47001/47001)",
        "",
        "4. ⚠️ แถวตัวอย่าง (00001, 00002) ใน Sheet 'ข้อมูล' เป็นเพียงตัวอย่าง — ลบออกก่อนอัปโหลด",
        "   (หรือก๊อปเฉพาะหัวตารางไปสร้างไฟล์ใหม่)",
        "",
        "5. ไฟล์ต้องเป็น .xlsx เท่านั้น",
    ]
    for t in tips:
        ws2.append([t])
    ws2.column_dimensions["A"].width = 110

    bio = io.BytesIO()
    wb.save(bio)
    return bio.getvalue()


# ============================================================
# 💾 Storage — บันทึกไฟล์ลง Server/Storage
# ============================================================
def ensure_storage_dir() -> str:
    """สร้างโฟลเดอร์เก็บไฟล์ถ้ายังไม่มี (เรียกทุกครั้งที่บันทึก — กัน deploy ลบ folder)"""
    d = settings.IMPORT_STORAGE_DIR
    os.makedirs(d, exist_ok=True)
    return d


def save_upload_file(content: bytes, original_filename: str) -> str:
    """
    บันทึกไฟล์ลง storage ด้วยชื่อสุ่ม (uuid) — กัน path traversal / ชื่อชนกัน
    คืน: absolute file_path (เก็บใน DB ใช้ worker อ่านต่อ)
    """
    ensure_storage_dir()
    stored_name = f"{uuid.uuid4().hex}.xlsx"
    file_path = os.path.join(settings.IMPORT_STORAGE_DIR, stored_name)
    with open(file_path, "wb") as f:
        f.write(content)
    return file_path


# ============================================================
# 🔁 ARQ Redis — Enqueue Job เข้าคิว
# ============================================================
async def create_arq_redis():
    """สร้าง ArqRedis (pool) จาก settings.REDIS_URL"""
    from arq.connections import RedisSettings, create_pool as arq_create_pool

    return await arq_create_pool(RedisSettings.from_dsn(settings.REDIS_URL))


async def enqueue_import_job(job_id: int) -> None:
    """ยิง job_id เข้า Redis queue เพื่อให้ ARQ Worker รับไปทำงาน"""
    redis = await create_arq_redis()
    try:
        # ⚠️ ต้องตรงกับ WorkerSettings ของ import_worker **สองอย่าง**:
        #    1. ชื่อฟังก์ชัน = __qualname__ ของ task ('process_student_import')
        #    2. ชื่อคิว     = IMPORT_QUEUE
        #    พลาดข้อ 2 = งานลงคิว `arq:queue` ที่ทั้งสอง worker ไม่ฟัง ⇒ หายเงียบ
        #    (enqueue_job คืน None ตอนลงคิวสำเร็จปกติ จึงไม่มีสัญญาณเตือนใด ๆ)
        await redis.enqueue_job("process_student_import", job_id, _queue_name=IMPORT_QUEUE)
        logger.info(f"✅ Enqueued import job {job_id} → Redis ({IMPORT_QUEUE})")
    finally:
        await redis.aclose()


# ============================================================
# 📝 สร้าง Job (Upload)
# ============================================================
async def create_import_job(
    pool: asyncpg.Pool,
    *,
    content: bytes,
    original_filename: str,
    default_password: str = "1234",
    allowed_level: Optional[str] = None,
    academic_year_id: Optional[int] = None,
    actor_user_id: Optional[int] = None,
    client_source: str = "web",
) -> dict:
    """
    ตรวจคอลัมน์แบบเป๊ะ → บันทึกไฟล์ลง storage → สร้าง record (status=PENDING) + audit
    (ตรวจคอลัมน์ก่อนบันทึกไฟล์ กันไฟล์ขยะค้างใน storage เมื่อคอลัมน์ผิด)

    🌟 `academic_year_id` (migration 028) — ปีของชุดที่กำลังนำเข้า
      · ระบุ → แถวที่ **ไม่กรอก** คอลัมน์ "ปีการศึกษา" ตกมาอยู่ปีนี้ และแถวที่กรอก
        **ต้องตรงกัน** ไม่งั้นเป็น error รายแถว (กันไฟล์ค้างปีถูกนำเข้าทับลงปีใหม่เงียบ ๆ)
      · ไม่ระบุ (None) → โหมดผ่อนปรน: แถวไหนไม่กรอกก็ใช้ **ปีปัจจุบัน** และแถวที่กรอก
        ปีใดก็ได้ที่ **มีอยู่ในระบบ** (ใช้ตอน backfill ประวัติย้อนหลัง)
    """
    data_rows, _ = load_workbook_rows(content)  # Raise ValidationError ถ้าคอลัมน์/ไฟล์ผิด

    # ไฟล์ที่ไม่มีข้อมูลเลย (มีแค่หัวตาราง / แถวว่างล้วน) — กันส่งงานที่เปล่าประโยชน์เข้าคิว
    if not data_rows:
        raise ValidationError("ไฟล์นี้มีแค่หัวตาราง ไม่มีข้อมูลนักเรียนให้นำเข้า — กรุณาใส่ข้อมูลก่อนอัปโหลด")

    # จำกัดจำนวนแถวต่อไฟล์ (กันไฟล์ยักษ์ลาก worker หลายชั่วโมง — DoS)
    if len(data_rows) > settings.IMPORT_MAX_ROWS:
        raise ValidationError(
            f"ไฟล์มีข้อมูลเกิน {settings.IMPORT_MAX_ROWS} แถว — กรุณาแบ่งไฟล์ออกเป็นหลายไฟล์"
        )

    # 🌟 ตรวจว่าปีที่ระบุมีอยู่จริง **ก่อน** บันทึกไฟล์ — หลักการเดียวกับ "ตรวจคอลัมน์ก่อน
    #    บันทึกไฟล์": ถ้าปีผิด ให้ล้มตั้งแต่ยังไม่มีไฟล์ตกค้างใน storage
    if academic_year_id is not None:
        async with pool.acquire() as conn:
            year_ok = await conn.fetchval(
                "SELECT 1 FROM academic_years WHERE id = $1 AND deleted_at IS NULL",
                academic_year_id,
            )
        if not year_ok:
            raise ValidationError("ไม่พบปีการศึกษาที่ระบุ — อาจถูกลบไปแล้ว")

    file_path = save_upload_file(content, original_filename)

    async with pool.acquire() as conn:
        async with conn.transaction():
            job_id = await conn.fetchval(
                """
                INSERT INTO student_import_jobs
                    (file_name, file_path, status, total_rows, default_password, allowed_level,
                     academic_year_id, created_by)
                VALUES ($1, $2, 'PENDING', $3, $4, $5, $6, $7)
                RETURNING id
                """,
                original_filename, file_path, len(data_rows),
                default_password or "1234", allowed_level, academic_year_id, actor_user_id,
            )

            # 🛡️ Audit log (กฎ: ทุก create ต้องบันทึกใน transaction เดียวกัน)
            await AuditLogger("import_service").log(
                conn=conn,
                action="UPLOAD_IMPORT_EXCEL",
                actor_identifier=str(actor_user_id) if actor_user_id else "system",
                client_source=client_source,
                user_id=actor_user_id,
                entity_type="student_import_job",
                entity_id=str(job_id),
                new_values={"file_name": original_filename, "total_rows": len(data_rows)},
            )

            row = await conn.fetchrow("SELECT * FROM student_import_jobs WHERE id = $1", job_id)

    return dict(row)


# ============================================================
# ▶️ เริ่ม Job (Start → Enqueue)
# ============================================================
async def start_import_job(
    pool: asyncpg.Pool,
    job_id: int,
    *,
    actor_user_id: Optional[int] = None,
    client_source: str = "web",
    access_scope: str = "all",
    access_level: Optional[str] = None,
) -> dict:
    """
    สั่งรันงาน: ล็อกแถว (FOR UPDATE) → ตรวจสิทธิ์/สถานะ → ตั้ง QUEUED (ล้าง error เก่า) → ยิง Redis
    ถ้า Redis ล้มเหลว → rollback (สถานะกลับเดิม) + Raise ServiceUnavailableError (503)
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            job = await conn.fetchrow(
                "SELECT * FROM student_import_jobs WHERE id = $1 FOR UPDATE", job_id
            )
            if not job:
                raise NotFoundError("ไม่พบงาน import นี้")

            # 🛡️ scope check: ครูระดับชั้นเริ่มงานได้เฉพาะของระดับชั้นตัวเอง; ครูที่ยังไม่มีระดับชั้นเริ่มไม่ได้
            if access_scope == "none":
                raise ForbiddenError("คุณยังไม่มีระดับชั้นที่รับผิดชอบ — ไม่สามารถเริ่มงานนำเข้าได้")
            if access_scope == "level" and job["allowed_level"] != access_level:
                raise ForbiddenError("งานนี้ไม่ใช่ระดับชั้นของคุณ — ไม่สามารถเริ่มได้")

            if job["status"] not in RESTARTABLE_STATUS:
                raise ConflictError(
                    f"งานนี้เริ่มไม่ได้เพราะสถานะ '{job['status']}' — รอให้เสร็จ/รอ worker ทำงานก่อน"
                )

            # ล้าง error/ความคืบหน้าเก่า (กรณี FAILED → ลองใหม่) เพื่อให้ progress bar เริ่มนับใหม่
            await conn.execute(
                """
                UPDATE student_import_jobs
                SET status = 'QUEUED', error_message = NULL, error_logs = '[]'::jsonb,
                    processed_rows = 0, imported_count = 0, skipped_count = 0,
                    completed_at = NULL, updated_at = NOW()
                WHERE id = $1
                """,
                job_id,
            )

            # 🛡️ Audit log (ภายใน transaction เดียวกับสถานะ)
            await AuditLogger("import_service").log(
                conn=conn,
                action="START_IMPORT_JOB",
                actor_identifier=str(actor_user_id) if actor_user_id else "system",
                client_source=client_source,
                user_id=actor_user_id,
                entity_type="student_import_job",
                entity_id=str(job_id),
                old_values={"status": job["status"]},
                new_values={"status": "QUEUED"},
            )

            # 🚀 ยิงเข้า Redis — ถ้าล้ม (Redis ลง) transaction rollback → สถานะกลับ PENDING
            try:
                await enqueue_import_job(job_id)
            except Exception as e:
                logger.error(f"❌ enqueue job {job_id} ล้มเหลว: {e}")
                raise ServiceUnavailableError("ระบบคิว (Redis) ไม่พร้อมใช้งาน — กรุณาลองใหม่ภายหลัง")

            row = await conn.fetchrow("SELECT * FROM student_import_jobs WHERE id = $1", job_id)

    return dict(row)


# ============================================================
# 📋 ดูรายการ Job + Progress
# ============================================================
async def list_import_jobs(
    pool: asyncpg.Pool,
    limit: int = 50,
    *,
    access_scope: str = "all",
    access_level: Optional[str] = None,
) -> list:
    """รายการงาน import เรียงใหม่สุดก่อน (มี LIMIT) — กรองตาม access scope ของผู้เรียก"""
    safe_limit = max(1, min(int(limit), 200))
    async with pool.acquire() as conn:
        if access_scope == "level":
            # ครูระดับชั้น: เห็นเฉพาะงานของระดับชั้นตัวเอง
            rows = await conn.fetch(
                """
                SELECT * FROM student_import_jobs
                WHERE allowed_level = $2
                ORDER BY created_at DESC
                LIMIT $1
                """,
                safe_limit, access_level,
            )
        elif access_scope == "none":
            # ครูที่ยังไม่มีระดับชั้น: ไม่เห็นงาน import ใดๆ เลย (upload/start ก็ถูก block แล้ว)
            rows = []
        else:
            rows = await conn.fetch(
                """
                SELECT * FROM student_import_jobs
                ORDER BY created_at DESC
                LIMIT $1
                """,
                safe_limit,
            )
    return [dict(r) for r in rows]


# ============================================================
# ⚙️ Worker — ประมวลผลงาน import (ทยอย insert + progress)
# ============================================================
class _ImportCtx:
    """Cache ต่อ 1 job — กัน SELECT ซ้ำ + กันสร้าง user/room ซ้ำในไฟล์เดียวกัน"""

    def __init__(self) -> None:
        self.room_cache: dict = {}   # room_code -> room_id
        self.user_cache: dict = {}   # username -> user_id
        # 🌟 year_be -> academic_year_id (None = ไม่พบในระบบ) — migration 028
        #    ⚠️ cache ค่า None ไว้ด้วยโดยเจตนา: ปีที่ไม่มีจะไม่มีโผล่มาระหว่าง job
        #       ⇒ ไม่ต้อง query ซ้ำทุกแถวที่มีปีผิด (ไฟล์ 2,000 แถวพิมพ์ปีผิด = 2,000 query)
        self.year_cache: dict = {}


def _get(r: tuple, col_index: dict, name: str):
    """ดึงค่าคอลัมน์ตามชื่อจาก tuple แถว (ปลอดภัยถ้า index เกิน)"""
    i = col_index.get(name)
    return r[i] if i is not None and i < len(r) else None


def _cell_to_str(value) -> str:
    """แปลงค่าเซลล์ Excel → string ที่อ่านง่าย (ไม่มี .0 ต่อท้ายเลขทศนิยมที่ลงตัว เช่น 40000.0 → '40000')"""
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _to_int(value) -> int:
    """แปลงค่าจาก Excel → int (รับได้ทั้ง int/float/str; ว่าง = 0)"""
    if value is None:
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    s = str(value).strip()
    return int(s) if s else 0


async def _resolve_row_year(
    conn: asyncpg.Connection,
    r: tuple,
    col_index: dict,
    ctx: _ImportCtx,
    job_year_id: Optional[int],
) -> Tuple[Optional[int], Optional[str]]:
    """ปีการศึกษาของแถวนี้ — คืน (year_id, error)

    ลำดับการตัดสิน:
      1. เซลล์ "ปีการศึกษา" กรอกมา → **ต้องเป็น พ.ศ. ที่มีอยู่ในระบบเท่านั้น**
         🔴 **ห้ามสร้างปีจากเซลล์ Excel เงียบ ๆ** — ถ้าพิมพ์ 2571 ผิดเป็น 2751 แล้วระบบ
            สร้างปีให้เอง จะได้ปีผีที่ลบยาก และเทสต์/invariant "ปีปัจจุบันมีได้ตัวเดียว"
            จะพังแบบหาสาเหตุไม่เจอ ⇒ ปีที่ไม่มี = **error รายแถว** (ไม่ใช่ FAILED ทั้ง job
            ตาม contract เดิมของ import: แถวผิด = ข้าม + บันทึก error_logs)
      2. เซลล์ว่าง → ใช้ **ปีของ job** (ไม่ใช่ "ปีปัจจุบัน" — ถ้ากำลัง import ย้อนหลัง
         ปีปัจจุบันจะผิดทันที) · job เก่าที่ไม่มีปี → ปีปัจจุบัน (พฤติกรรมเดิม)
    """
    raw = _cell_to_str(_get(r, col_index, "ปีการศึกษา"))

    if not raw:
        if job_year_id is not None:
            return job_year_id, None
        current = await year_service.fetch_current_year(conn)
        return (current["id"] if current else None), None

    # _cell_to_str แปลง float ที่ลงตัวเป็น "2569" แล้ว (ไม่ใช่ "2569.0") ⇒ int() ตรง ๆ ได้
    try:
        year_be = int(raw)
    except (ValueError, TypeError):
        return None, f"ปีการศึกษาต้องเป็นตัวเลข พ.ศ. (ได้ค่า: {raw!r})"

    if year_be not in ctx.year_cache:
        ctx.year_cache[year_be] = await conn.fetchval(
            "SELECT id FROM academic_years WHERE year_be = $1 AND deleted_at IS NULL",
            year_be,
        )
    found = ctx.year_cache[year_be]
    if found is None:
        return None, f"ไม่พบปีการศึกษา {year_be} ในระบบ — สร้างปีการศึกษาก่อนนำเข้า"
    # ⚠️ ไม่ตรงกับปีของ job = error โดยเจตนา — กันไฟล์ที่ค้างมาจากปีก่อนถูกนำเข้าทับ
    #    ลงปีใหม่เงียบ ๆ (ข้อมูลจะไปอยู่ผิดปีโดยที่ผู้ใช้อ่านหน้าจอไม่ออก)
    if job_year_id is not None and found != job_year_id:
        return None, "ปีการศึกษาในไฟล์ไม่ตรงกับปีของงานนำเข้านี้"
    return found, None


async def _process_single_row(
    conn: asyncpg.Connection,
    r: tuple,
    col_index: dict,
    ctx: _ImportCtx,
    *,
    default_password: str,
    allowed_level: Optional[str],
    job_year_id: Optional[int] = None,
) -> Tuple[bool, Optional[str]]:
    """
    ประมวลผล 1 แถว (สร้าง/อัปเดต users + rooms + students)
    คืน (success, error_msg) — จับเฉพาะ data error (ValueError/TypeError/UniqueViolation);
    asyncpg error อื่นๆ ปล่อยให้ลอยขึ้นไป (batch จะ fallback / job จะ FAILED)
    """
    try:
        # ⚠️ ใช้ _cell_to_str — ถ้าเซลล์ว่าง (None) `str(None)` = "None" (truthy!) → จะไปสร้าง user/room ปลอม;
        # และถ้า Excel เก็บตัวเลขเป็น float (40000.0) ต้องตัด .0 ทิ้ง (ไม่งั้น username = "40000.0")
        student_id = _cell_to_str(_get(r, col_index, "รหัสนักเรียน"))
        room_code = _cell_to_str(_get(r, col_index, "ห้องเรียน"))
        try:
            student_no = _to_int(_get(r, col_index, "เลขที่"))
        except (ValueError, TypeError):
            return False, f"เลขที่ต้องเป็นตัวเลข (ได้ค่า: {_get(r, col_index, 'เลขที่')!r})"
        prefix = str(_get(r, col_index, "คำนำหน้า") or "").strip() or None
        first_name = str(_get(r, col_index, "ชื่อ") or "").strip()
        last_name = str(_get(r, col_index, "นามสกุล") or "").strip()
        nickname = str(_get(r, col_index, "ชื่อเล่น") or "").strip() or None
        role_label = str(_get(r, col_index, "ตำแหน่งในห้องเรียน") or "").strip()
        class_role = map_role_label(role_label)
        role_perms = get_role_permissions(class_role)
        role_is_admin = get_role_is_admin(class_role)

        if not student_id:
            return False, "ไม่มีรหัสนักเรียน"
        # 🛡️ กันแถวตัวอย่างจาก Template (000xx) หลุดเข้ามาเป็น account จริง —
        # ผู้ใช้ที่ดาวน์โหลด Template แล้วอัปโหลดทั้งไฟล์ (ลืมลบแถวตัวอย่าง) ต้องไม่สร้าง
        # user/student ปลอมที่มี password เดาได้ (00001/00001) เป็นต้น
        if student_id.startswith("000"):
            return False, "รหัสขึ้นต้น 000 = แถวตัวอย่างจาก Template — ลบแถวตัวอย่างออกก่อนอัปโหลด"
        if not first_name and not last_name:
            return False, "ไม่มีชื่อ-นามสกุล"

        # 🛡️ กัน privilege escalation: ครูระดับชั้น (allowed_level set) สร้าง role ระดับโรงเรียน
        # (แอดมิน/ครูสภา/สภานักเรียน/ประธานสภา) ไม่ได้ — เพราะจะได้สิทธิ์จัดการทั้งโรงเรียน
        if allowed_level is not None and class_role in SCHOOL_WIDE_ROLES:
            return False, (
                f"ตำแหน่ง '{role_label}' ({class_role}) สร้างได้เฉพาะผู้ดูแลทั้งโรงเรียน — "
                f"ครูระดับชั้น ({allowed_level}) นำเข้าไม่ได้"
            )

        # 🌟 0. ปีการศึกษา (migration 028) — ต้องรู้ก่อน INSERT เพราะ `academic_year_id`
        #    เป็น NOT NULL และเป็นส่วนหนึ่งของ unique index ใหม่
        row_year_id, year_err = await _resolve_row_year(conn, r, col_index, ctx, job_year_id)
        if year_err:
            return False, year_err
        if row_year_id is None:
            # เกิดไม่ได้ในทางปฏิบัติ (027 รับประกันว่ามีปีปัจจุบันเสมอ) — แต่ถ้าเกิด
            # อย่าปล่อยให้ล้มด้วย NotNullViolation ที่อ่านไม่ออก ให้บอกตรง ๆ ว่าต้องทำอะไร
            return False, "ยังไม่มีปีการศึกษาในระบบ — สร้างปีการศึกษาก่อนนำเข้า"

        # 🌟 1. Room — ครูสภา/แอดมิน (school-wide) ไม่ผูกห้องเฉพาะ; ระบุห้องได้แต่ไม่บังคับ
        school_wide = class_role in SCHOOL_WIDE_ROLES
        room_id = None
        room_level = None
        if room_code:
            if room_code in ctx.room_cache:
                room_id = ctx.room_cache[room_code]
            else:
                room_id = await conn.fetchval(
                    "SELECT id FROM rooms WHERE room_code = $1 AND deleted_at IS NULL", room_code
                )
                if not room_id:
                    level = room_code.split("/")[0] if "/" in room_code else room_code
                    room_id = await conn.fetchval(
                        """
                        INSERT INTO rooms (room_code, room_name, level, room_number)
                        VALUES ($1, $2, $3, NULL)
                        RETURNING id
                        """,
                        room_code, room_code, level,
                    )
                ctx.room_cache[room_code] = room_id
            room_level = await conn.fetchval("SELECT level FROM rooms WHERE id = $1", room_id)

        # 🛡️ scope: ครูทั่วไปนำเข้าได้เฉพาะระดับชั้นตัวเอง
        if allowed_level and not school_wide and room_level != allowed_level:
            return False, f"ระดับชั้น {room_level or '-'} ไม่ตรงกับสิทธิ์ของคุณ ({allowed_level})"

        # ครูทั่วไป → staff_level = ระดับชั้นของห้องในแถวนั้น
        staff_level = room_level if class_role == "teacher" else None

        # 🌟 2. User — ใช้/สร้างตาม username (เช็ค cache ก่อนเสมอ)
        username = student_id
        if username in ctx.user_cache:
            user = ctx.user_cache[username]
        else:
            user = await conn.fetchval(
                "SELECT id FROM users WHERE username = $1 AND deleted_at IS NULL", username
            )
            if not user:
                initial_password = student_id if default_password in ("", "1234") else default_password
                hashed = auth_service.hash_password(initial_password)
                # ⚠️ ใช้ join เฉพาะค่าที่มี — ถ้า prefix ว่าง (None) f-string จะได้ "None ชื่อ นามสกุล"
                full_name = " ".join(p for p in (prefix, first_name, last_name) if p).strip() or username
                user = await conn.fetchval(
                    """
                    INSERT INTO users (username, password_hash, full_name)
                    VALUES ($1, $2, $3)
                    RETURNING id
                    """,
                    username, hashed, full_name,
                )
            ctx.user_cache[username] = user

        # 🌟 3. Student — upsert แบบ atomic กัน 2 worker/reimport ชนกันสร้างแถวซ้ำ
        if room_id is not None:
            # แถวที่มีห้อง → ON CONFLICT ต้องตรงกับ partial unique index
            # `uq_students_room_year_student (room_id, academic_year_id, student_id)` (migration 028)
            # 🔴 **ห้ามถอยกลับไปใช้ `(room_id, student_id)`** — index นั้นถูก DROP ไปแล้ว
            #    และถ้าใส่ arbiter ที่ไม่มี index รองรับ PostgreSQL จะโยน error ทันที
            #    ("there is no unique or exclusion constraint matching the ON CONFLICT
            #     specification") ⇒ **import พังทั้งงาน** ไม่ใช่แค่แถวเดียว
            await conn.execute(
                """
                INSERT INTO students
                    (room_id, user_id, student_id, student_no, prefix,
                     first_name, last_name, nickname, class_role, staff_level,
                     is_admin, permissions, academic_year_id)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                ON CONFLICT (room_id, academic_year_id, student_id) WHERE deleted_at IS NULL
                DO UPDATE SET
                    user_id = EXCLUDED.user_id,
                    student_no = EXCLUDED.student_no,
                    prefix = EXCLUDED.prefix,
                    first_name = EXCLUDED.first_name,
                    last_name = EXCLUDED.last_name,
                    nickname = EXCLUDED.nickname,
                    class_role = EXCLUDED.class_role,
                    staff_level = EXCLUDED.staff_level,
                    is_admin = EXCLUDED.is_admin,
                    permissions = EXCLUDED.permissions,
                    updated_at = NOW()
                """,
                room_id, user, student_id, student_no, prefix, first_name, last_name,
                nickname, class_role, staff_level, role_is_admin, json.dumps(role_perms),
                row_year_id,
            )

            # 🛡️ กัน "แถว active ซ้อนในปีเดียวกัน" — ถ้านักเรียนรหัสเดิมถูกนำเข้าซ้ำ
            #    **คนละห้องในปีเดียวกัน** (แก้ห้องที่กรอกผิด / ย้ายห้องกลางปี) แถวใหม่ถูก
            #    upsert ลงห้องใหม่ แต่ **แถวเดิมในห้องเก่ายัง active อยู่** ⇒ คนเดียวปรากฏ
            #    สองห้อง · ยอด dashboard บวม · RBAC เห็นสิทธิ์จากห้องที่ไม่อยู่แล้ว
            #    ⚠️ แตะเฉพาะ `status='active'` — ไม่ยุ่งกับ pending/suspended/history
            #    ⚠️ แตะเฉพาะแถวที่มีห้อง (`room_id IS NOT NULL`) — แถว school-wide
            #       (room_id NULL) เป็น "บทบาทระดับโรงเรียน" ไม่ใช่ "การย้ายห้อง"
            #    ⚠️ รัน **หลัง** upsert แล้วจึงกัน `room_id <> $3` ได้ (แถวที่เพิ่งเขียน
            #       อยู่ห้อง $3 ⇒ ไม่ถูกแตะ) — ถ้ารันก่อน จะ supersede แถวตัวเองทิ้ง
            await conn.execute(
                """
                UPDATE students SET status = 'superseded', updated_at = NOW()
                WHERE academic_year_id = $1 AND student_id = $2 AND deleted_at IS NULL
                  AND status = 'active' AND room_id IS NOT NULL AND room_id <> $3
                """,
                row_year_id, student_id, room_id,
            )
        else:
            # school-wide (room_id NULL): NULL ไม่ชนกันใน unique index → ใช้ SELECT-แล้ว-INSERT/UPDATE ตามเดิม
            # 🌟 เพิ่ม `academic_year_id = $2` (migration 028) — มิติปีต้องอยู่ในตัวค้นหาด้วย
            #    ไม่งั้น SELECT จะเจอแถวของปีเก่า (room_id NULL ไม่ชนกันใน index ⇒ มีได้หลายปี)
            #    แล้ว UPDATE ทับ ⇒ **ปลุกแถวปีเก่า** เหมือนบั๊กที่แก้ใน auth_service
            student = await conn.fetchval(
                """
                SELECT id FROM students
                WHERE room_id IS NULL AND student_id = $1 AND deleted_at IS NULL
                  AND academic_year_id = $2
                """,
                student_id, row_year_id,
            )
            if student:
                await conn.execute(
                    """
                    UPDATE students
                    SET user_id = $1, student_no = $2, prefix = $3,
                        first_name = $4, last_name = $5, nickname = $6,
                        class_role = $7, staff_level = $8, is_admin = $9,
                        permissions = $10, updated_at = NOW()
                    WHERE id = $11
                    """,
                    user, student_no, prefix, first_name, last_name, nickname,
                    class_role, staff_level, role_is_admin, json.dumps(role_perms), student,
                )
            else:
                await conn.execute(
                    """
                    INSERT INTO students
                        (room_id, user_id, student_id, student_no, prefix,
                         first_name, last_name, nickname, class_role, staff_level,
                         is_admin, permissions, academic_year_id)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                    """,
                    room_id, user, student_id, student_no, prefix, first_name, last_name,
                    nickname, class_role, staff_level, role_is_admin, json.dumps(role_perms),
                    row_year_id,
                )

        return True, None
    except (ValueError, TypeError, asyncpg.UniqueViolationError) as e:
        return False, f"ข้อมูลผิดรูปแบบ/ซ้ำ ({e})"


async def _claim_job(pool: asyncpg.Pool, job_id: int) -> Optional[dict]:
    """
    worker ครอบงาน: ล็อกแถว → ตรวจสถานะ (PENDING/QUEUED) → ตั้ง PROCESSING + audit
    คืน job dict (พร้อม file_path) หรือ None ถ้าจบ/ถูกครอบไปแล้ว
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            job = await conn.fetchrow(
                "SELECT * FROM student_import_jobs WHERE id = $1 FOR UPDATE", job_id
            )
            if not job:
                logger.warning(f"⚠️ Job {job_id} ไม่มีอยู่ — ข้าม")
                return None
            if job["status"] not in CLAIMABLE_STATUS:
                logger.info(f"ℹ️ Job {job_id} จบ/ถูกครอบไปแล้ว (status={job['status']}) — ข้าม")
                return None

            await conn.execute(
                """
                UPDATE student_import_jobs
                SET status = 'PROCESSING', started_at = COALESCE(started_at, NOW()), updated_at = NOW()
                WHERE id = $1
                """,
                job_id,
            )
            await AuditLogger("import_service").log(
                conn=conn,
                action="PROCESS_IMPORT_JOB",
                actor_identifier=str(job["created_by"]) if job["created_by"] else "worker",
                client_source="worker",
                user_id=job["created_by"],
                entity_type="student_import_job",
                entity_id=str(job_id),
                old_values={"status": job["status"]},
                new_values={"status": "PROCESSING"},
            )
    return dict(job)


async def _set_job_result(
    pool: asyncpg.Pool,
    job_id: int,
    *,
    status: str,
    error_message: Optional[str] = None,
    total: Optional[int] = None,
    imported: Optional[int] = None,
    skipped: Optional[int] = None,
    errors: Optional[list] = None,
) -> None:
    """จบงาน: เขียนผลลัพธ์ (COMPLETED/FAILED) + error_logs + audit ภายใน transaction เดียว"""
    error_logs = (errors or [])[:MAX_ERROR_LOGS]

    async with pool.acquire() as conn:
        async with conn.transaction():
            job = await conn.fetchrow(
                "SELECT status, created_by, file_path FROM student_import_jobs WHERE id = $1", job_id
            )
            if not job:
                return
            old_status = job["status"]

            if status == IMPORT_STATUS_FAILED:
                await conn.execute(
                    """
                    UPDATE student_import_jobs
                    SET status = 'FAILED', error_message = $2, error_logs = $3::jsonb,
                        completed_at = NOW(), updated_at = NOW()
                    WHERE id = $1
                    """,
                    job_id, error_message, json.dumps(error_logs, ensure_ascii=False),
                )
            else:
                await conn.execute(
                    """
                    UPDATE student_import_jobs
                    SET status = 'COMPLETED', total_rows = $2, processed_rows = $2,
                        imported_count = $3, skipped_count = $4, error_logs = $5::jsonb,
                        error_message = NULL,   -- ล้าง error เก่า (กัน UI โชว์ค้างหลังเสร็จ)
                        completed_at = NOW(), updated_at = NOW()
                    WHERE id = $1
                    """,
                    job_id, total, imported, skipped, json.dumps(error_logs, ensure_ascii=False),
                )

            # 🛡️ Audit log — ต้องอยู่ใน transaction เดียวกับการเปลี่ยนสถานะ (กฎทุก create/update/delete)
            # (เดิมเขียนผิดไปอยู่ใต้ except ของการลบไฟล์ → audit ไม่ถูกเขียนตอนจบงานปกติ)
            await AuditLogger("import_service").log(
                conn=conn,
                action="COMPLETE_IMPORT_JOB" if status == IMPORT_STATUS_COMPLETED else "FAIL_IMPORT_JOB",
                actor_identifier=str(job["created_by"]) if job["created_by"] else "worker",
                client_source="worker",
                user_id=job["created_by"],
                entity_type="student_import_job",
                entity_id=str(job_id),
                status="success" if status == IMPORT_STATUS_COMPLETED and not error_logs else
                       ("partial" if status == IMPORT_STATUS_COMPLETED else "error"),
                error_detail=error_message,
                old_values={"status": old_status},
                new_values={"status": status, **({"error_message": error_message} if error_message else {})},
            )

    # งานเสร็จแล้ว → ลบไฟล์ออกจาก storage (นอก transaction — ไม่กระทบสถานะงาน)
    # FAILED เก็บไฟล์ไว้ให้ลองใหม่ (start_import_job ล้าง error และสร้าง queue ใหม่)
    if status == IMPORT_STATUS_COMPLETED and job.get("file_path"):
        try:
            os.remove(job["file_path"])
        except OSError as e:
            logger.warning(f"⚠️ ลบไฟล์ storage ไม่สำเร็จ: {job['file_path']} ({e})")


async def process_import_job(pool: asyncpg.Pool, job_id: int) -> dict:
    """
    ⚙️ ฟังก์ชันหลักของ Worker — ครอบงาน → อ่านไฟล์ → ทยอย insert เป็น batch → update progress → จบ

    - แต่ละ batch เป็น transaction แยก (กันล็อกยาว + commit progress เป็นระยะ)
    - อัปเดต processed_rows ทุก batch → เอาไปทำ progress bar
    - แถวที่ข้อมูลผิด → ข้าม (บันทึกลง error_logs) ; ไฟล์พัง/ข้อผิดพลาดร้ายแรง → FAILED
    """
    job = await _claim_job(pool, job_id)
    if job is None:
        return {"status": "SKIPPED", "reason": "already_finished_or_claimed"}

    file_path = job["file_path"]
    default_password = job["default_password"] or "1234"
    allowed_level = job["allowed_level"]
    created_by = job["created_by"]
    # 🌟 ปีของงานนี้ (migration 028) — ไฟล์ที่ไม่มีคอลัมน์ "ปีการศึกษา" จะตกมาอยู่ปีนี้
    #    job เก่าที่ค้างอยู่ (คอลัมน์ยัง NULL) → worker จะถอยไปใช้ปีปัจจุบันให้เอง
    job_year_id = job["academic_year_id"]
    imported = 0
    skipped = 0
    errors: List[str] = []

    try:
        # 1. อ่านไฟล์จาก storage
        try:
            with open(file_path, "rb") as f:
                content = f.read()
        except FileNotFoundError:
            # แสดงแค่ basename — อย่า leak path เต็มบน server ออกไปยังผู้ใช้
            raise ValidationError(f"ไม่พบไฟล์บน storage: {os.path.basename(file_path)}")
        except OSError as e:
            raise ValidationError(f"อ่านไฟล์จาก storage ไม่สำเร็จ: {e}")

        # 2. แยกแถว + ตรวจคอลัมน์ (เป๊ะ)
        data_rows, col_index = load_workbook_rows(content)
        total = len(data_rows)

        # 3. ทยอย insert เป็น batch
        batch_size = settings.IMPORT_BATCH_SIZE
        ctx = _ImportCtx()

        async with pool.acquire() as conn:
            for start in range(0, total, batch_size):
                chunk = data_rows[start:start + batch_size]

                # 📸 snapshot ตัวนับก่อนลอง batch — ถ้า batch rollback จะได้คืนค่า (กันนับซ้ำ)
                snapshot_imported, snapshot_skipped, snapshot_errors_len = imported, skipped, len(errors)
                try:
                    # Batch ปกติ: transaction เดียวทั้ง chunk
                    async with conn.transaction():
                        for idx, r in enumerate(chunk):
                            ok, err = await _process_single_row(
                                conn, r, col_index, ctx,
                                default_password=default_password, allowed_level=allowed_level,
                                job_year_id=job_year_id,
                            )
                            row_no = start + idx + 1
                            if ok:
                                imported += 1
                            else:
                                skipped += 1
                                errors.append(f"แถว {row_no}: {err}")
                except asyncpg.PostgresError as e:
                    # Batch พัง (rollback ทั้ง chunk) → คืน counter + เคลียร์ cache
                    # (IDs ที่ insert ใน batch ที่พังถูก rollback ไปแล้ว → cache เก่า = phantom ID)
                    imported, skipped = snapshot_imported, snapshot_skipped
                    del errors[snapshot_errors_len:]
                    ctx.room_cache.clear()
                    ctx.user_cache.clear()
                    # 🌟 year_cache ต้องเคลียร์ด้วยเหตุผลเดียวกัน — แต่จริง ๆ แล้วค่าปีไม่ผูกกับ
                    #    transaction (อ่านจาก academic_years ซึ่งไม่ได้ถูก insert ในงานนี้)
                    #    ⇒ เคลียร์เพื่อความสม่ำเสมอของสัญญา "cache ทั้งชุดถูกล้างพร้อมกัน"
                    ctx.year_cache.clear()
                    logger.error(f"⚠️ batch job {job_id} พัง ({e}) — fallback ทีละแถว")
                    for idx, r in enumerate(chunk):
                        row_no = start + idx + 1
                        try:
                            async with conn.transaction():
                                ok, err = await _process_single_row(
                                    conn, r, col_index, ctx,
                                    default_password=default_password, allowed_level=allowed_level,
                                job_year_id=job_year_id,
                                )
                        except Exception as row_err:
                            ok, err = False, f"ไม่สามารถบันทึกแถวนี้ได้ ({row_err})"
                        if ok:
                            imported += 1
                        else:
                            skipped += 1
                            errors.append(f"แถว {row_no}: {err}")

                # 4. อัปเดต progress ทุก batch (หลังจาก batch commit แล้ว)
                await conn.execute(
                    """
                    UPDATE student_import_jobs
                    SET processed_rows = $2, updated_at = NOW()
                    WHERE id = $1
                    """,
                    job_id, start + len(chunk),
                )

    except ValidationError as e:
        logger.error(f"❌ Job {job_id} invalid: {e}")
        await _set_job_result(pool, job_id, status=IMPORT_STATUS_FAILED, error_message=str(e), errors=errors)
        return {"status": "FAILED", "reason": str(e)}
    except Exception as e:
        logger.exception(f"❌ Job {job_id} พังแบบไม่คาดคิด: {e}")
        await _set_job_result(pool, job_id, status=IMPORT_STATUS_FAILED, error_message=str(e), errors=errors)
        return {"status": "FAILED", "reason": str(e)}
    else:
        # 5. สำเร็จ — เขียนผลรวม + COMPLETED
        await _set_job_result(
            pool, job_id,
            status=IMPORT_STATUS_COMPLETED,
            total=total, imported=imported, skipped=skipped, errors=errors,
        )
        logger.info(f"✅ Job {job_id} COMPLETED — total={total} imported={imported} skipped={skipped}")
        return {"status": "COMPLETED", "total_rows": total, "imported": imported, "skipped": skipped, "errors": errors[:50]}


# ============================================================
# 🔧 Recovery — กู้คืนงานค้างเมื่อ worker restart
# ============================================================
async def recover_stuck_jobs(pool: asyncpg.Pool) -> None:
    """
    เรียกตอน worker เริ่มต้น: งานที่ค้างนานเกิน → reset กลับ QUEUED + ยิงคิวใหม่
    - PROCESSING ค้าง > 35 นาที: worker ก่อนหน้าตายกลางคัน
    - QUEUED ค้าง > 35 นาที: Redis หายไป (job ที่ start แล้วแต่คิวหาย) — กันติดค้างถาวร
      (QUEUED ถูกกันออกจาก RESTARTABLE_STATUS แล้ว ต้องพึ่ง recovery นี้แทน)
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            rows = await conn.fetch(
                """
                SELECT id, created_by, status FROM student_import_jobs
                WHERE status IN ('PROCESSING', 'QUEUED')
                  AND updated_at < NOW() - make_interval(mins => $1)
                FOR UPDATE
                """,
                settings.IMPORT_RECOVERY_STALE_MINUTES,
            )
            for r in rows:
                await conn.execute(
                    "UPDATE student_import_jobs SET status = 'QUEUED', updated_at = NOW() WHERE id = $1",
                    r["id"],
                )
                await AuditLogger("import_service").log(
                    conn=conn,
                    action="RECOVER_IMPORT_JOB",
                    actor_identifier=str(r["created_by"]) if r["created_by"] else "worker",
                    client_source="worker",
                    user_id=r["created_by"],
                    entity_type="student_import_job",
                    entity_id=str(r["id"]),
                    old_values={"status": r["status"]},
                    new_values={"status": "QUEUED"},
                )

    for r in rows:
        try:
            await enqueue_import_job(r["id"])
        except Exception as e:
            logger.error(f"⚠️ re-enqueue job {r['id']} หลัง recovery ล้มเหลว: {e}")
