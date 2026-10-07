"""
ARQ Worker สำหรับ Import นักเรียนจาก Excel
===========================================
รันด้วย: python -m arq workers.import_worker.WorkerSettings

Worker นี้เป็น "ตัวต่อ" บางๆ กับ ARQ เท่านั้น — business logic ทั้งหมดอยู่ที่
`services/import_service.process_import_job` (เลเยอร์ service ตามกฎโปรเจค)
"""
import logging

import asyncpg
from arq.connections import RedisSettings

from core.config import settings
from core.queues import IMPORT_QUEUE
from core.request_context import audit_scope
from services import import_service

logger = logging.getLogger("IMPORT_WORKER")


async def startup(ctx: dict) -> None:
    """สร้าง db pool ของ worker + กู้คืนงานค้าง (worker ก่อนหน้าตายกลางคัน)"""
    ctx["pool"] = await asyncpg.create_pool(settings.DATABASE_URL, min_size=1, max_size=5)
    try:
        # 📡 worker ไม่ได้ผ่าน HTTP → ต้องครอบ audit_scope เอง ไม่งั้น audit_logs
        #    ของงานนี้จะไม่มี trace_id/endpoint/execution_time_ms (ดู core/request_context.py)
        with audit_scope(endpoint="arq:recover_stuck_jobs"):
            await import_service.recover_stuck_jobs(ctx["pool"])
    except Exception:
        logger.exception("❌ recover stuck import jobs ล้มเหลว (จะลองใหม่ตอน start ครั้งหน้า)")


async def shutdown(ctx: dict) -> None:
    await ctx["pool"].close()


async def process_student_import(ctx: dict, job_id: int) -> dict:
    """
    ARQ task: รับ job_id จากคิว → ส่งต่อให้ service (ทุก business logic อยู่ที่ service)

    ⚠️ ต้องตรงกับ `import_service.enqueue_import_job` **สองอย่าง**:
       1. ชื่อฟังก์ชัน = __qualname__ ของฟังก์ชันนี้ ('process_student_import')
       2. ชื่อคิว     = IMPORT_QUEUE (ดู core/queues.py) — พลาดข้อนี้ = งานหายเงียบ ไม่มี error
    """
    # 📡 ครอบ audit_scope: ทุก audit log ของงานนี้ได้ trace_id เดียวกัน + วัด execution_time_ms ได้
    with audit_scope(endpoint=f"arq:process_student_import job_id={job_id}"):
        return await import_service.process_import_job(ctx["pool"], job_id)


class WorkerSettings:
    functions = [process_student_import]
    on_startup = startup
    on_shutdown = shutdown
    # ถ้า REDIS_URL ว่าง (dev เครื่อง) ใช้ localhost กัน import พัง — production/container ตั้งค่าเสมอ
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL or "redis://localhost:6379/0")

    # 🚧 คิวแยกจาก push_worker เด็ดขาด — ถ้าไม่ตั้ง ARQ จะใช้ `arq:queue` ร่วมกัน
    #    แล้วดึงงานแบบ atomic ⇒ งาน import ตกไปฝั่ง push_worker = หายเงียบ (ดู core/queues.py)
    queue_name = IMPORT_QUEUE

    # 🔒 max_jobs=1 → worker ประมวลผลทีละ 1 งาน
    #    (กัน 2 งานพร้อมกันชนกันสร้าง users/students ซ้ำ — unique constraint)
    max_jobs = 1

    # ⏱️ งาน import อาจนาน (ไฟล์ใหญ่หลายพันแถว) — กัน ARQ ตัดงานกลางคัน
    job_timeout = 3600
    keep_result = 3600

    # process_import_job จัดการ error เอง (จดสถานะ FAILED ลง DB) → ไม่ให้ ARQ retry ซ้ำซ้อน
    max_tries = 1
