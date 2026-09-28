"""
ARQ Worker สำหรับ Web Push (A3)
================================
รันด้วย: python -m arq workers.push_worker.WorkerSettings

⭐ **ทำไมแยกไฟล์จาก `import_worker.py`** (ไม่ใช่ยัด cron เข้าไปในไฟล์เดิม):
   `import_worker` ตั้ง `max_jobs = 1` + `job_timeout = 3600` โดยเจตนา (กัน import
   นักเรียนสองงานชนกันสร้าง users ซ้ำ) ⇒ ถ้าเอา push cron ไปไว้ในไฟล์นั้น
   **การ import นักเรียนตอนเปิดเทอมจะบล็อก push ทั้งชั่วโมง** และไม่มีใครรู้
   จนมีคนบ่นว่า "เปิดเทอมแล้วการแจ้งเตือนเงียบ" ⇒ แยก worker คนละโปรเซสกันเลย

⭐ **ทำไมรอบละ 20 วินาที ไม่ใช่ 60:**
   เป้าของ A3 คือ "รู้สึกว่าทันที" (ในห้องเรียนมีคนตั้งเรื่อง → ครูรู้ภายในไม่กี่วินาที)
   และคิวว่าง = คิวรีเดียวบน partial index `idx_push_outbox_pending` ซึ่งแทบไม่มีต้นทุน
   ⇒ 20 วินาทีคือสมดุลที่จ่ายไหว (60 วินาทีจะรู้สึกช้า, 5 วินาทีจะเปลืองโดยไม่ได้อะไร)

⚠️ **`unique=True` เป็น default ของ ARQ cron** ⇒ ถ้ามีหลาย replica จะมีตัวเดียวทำงาน
   (กัน cron ซ้อน) · แต่ต่อให้ซ้อนจริง ด่าน `FOR UPDATE SKIP LOCKED` ใน `_claim()`
   ก็กันการส่งซ้ำได้อยู่ดี — สองชั้นนี้ตั้งใจให้เหลื่อมกัน
"""
import logging

import asyncpg
from arq import cron
from arq.connections import RedisSettings

from core.config import settings
from core.request_context import audit_scope
from services import push_service

logger = logging.getLogger("PUSH_WORKER")


async def startup(ctx: dict) -> None:
    """สร้าง db pool + กู้แถวที่ worker ก่อนหน้าจองค้างไว้

    ⚠️ `recover_stale_outbox()` ใน startup คือ **ด่านที่ขาดไม่ได้** — ถ้า worker ตาย
       หลัง claim แต่ก่อนจดผล แถวนั้นจะมี `processing_at` ค้าง และคิวรี claim
       (ที่กรอง `processing_at IS NULL`) จะ **ไม่มีวันหยิบมันอีกเลย** ⇒ push หยุดเงียบ
       ไม่มี error ที่ไหนให้เห็น · เป็นอาการที่หาสาเหตุยากที่สุดในระบบคิว
    """
    ctx["pool"] = await asyncpg.create_pool(settings.DATABASE_URL, min_size=1, max_size=5)
    try:
        # 📡 worker ไม่ได้ผ่าน HTTP → ต้องครอบ audit_scope เอง ไม่งั้น log ของงานนี้
        #    จะไม่มี trace_id/endpoint (ดู core/request_context.py)
        with audit_scope(endpoint="arq:recover_stale_outbox"):
            recovered = await push_service.recover_stale_outbox(ctx["pool"])
        if recovered:
            logger.warning("♻️ กู้แถว outbox ที่ค้างจากการ claim %d แถว", recovered)
    except Exception:
        logger.exception("❌ recover stale outbox ล้มเหลว (จะลองใหม่ตอน start ครั้งหน้า)")


async def shutdown(ctx: dict) -> None:
    await ctx["pool"].close()


async def process_push_outbox(ctx: dict) -> dict:
    """ARQ cron: ประมวลผลคิว push 1 รอบ (ทุก 20 วินาที)"""
    with audit_scope(endpoint="arq:process_push_outbox"):
        stats = await push_service.process_pending(ctx["pool"])

    # 📋 log เฉพาะรอบที่มีของจริง — ไม่งั้น log จะท่วมด้วย "claimed 0" ทุก 20 วินาที
    #    (3 บรรทัด/นาที × 60 × 24 = 4,320 บรรทัด/วัน ของศูนย์)
    if stats["claimed"]:
        logger.info(
            "📤 push: claimed=%d sent=%d gone=%d retry=%d dropped=%d skipped=%d stale=%d",
            stats["claimed"], stats["sent"], stats["gone"], stats["retry"],
            stats["dropped"], stats["skipped"], stats["stale"],
        )
    return stats


async def cleanup_push_outbox(ctx: dict) -> int:
    """ARQ cron: ลบแถว outbox ที่จบแล้วและเก่ากว่า `PUSH_RETENTION_DAYS` (วันละครั้ง)"""
    with audit_scope(endpoint="arq:cleanup_push_outbox"):
        deleted = await push_service.cleanup_outbox(ctx["pool"])
    if deleted:
        logger.info("🧹 ลบแถว outbox เก่า %d แถว", deleted)
    return deleted


class WorkerSettings:
    cron_jobs = [
        # ⏱️ ทุก 20 วินาที (นาทีที่ 0, 20, 40) — ดูเหตุผลใน docstring หัวไฟล์
        cron(process_push_outbox, second={0, 20, 40}, run_at_startup=True),
        # 🌙 ตี 3 — chosen ให้ห่างจาก import ตอนเปิดเทอม และเป็นช่วงที่คนใช้น้อยสุด
        cron(cleanup_push_outbox, hour={3}, minute={0}),
    ]
    on_startup = startup
    on_shutdown = shutdown
    # ถ้า REDIS_URL ว่าง (dev เครื่อง) ใช้ localhost กัน import พัง — production ตั้งค่าเสมอ
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL or "redis://localhost:6379/0")

    # ⚙️ max_jobs=2 (ไม่ใช่ 1) — ปลอดภัยเพราะ claim ใช้ `FOR UPDATE SKIP LOCKED`
    #    ⇒ สอง job พร้อมกันหยิบคนละแถว ไม่มีทางส่งซ้ำ
    #    (ต่างจาก import_worker ที่ต้อง max_jobs=1 เพราะสร้าง users ชนกันได้)
    max_jobs = 2

    # ⏱️ 1 รอบส่งได้สูงสุด PUSH_BATCH_SIZE (ค่าเริ่มต้น 100) ข้อความ
    #    ⇒ 120 วินาทีเหลือเฟือ · ถ้าปลายทางช้า งานจะถูกตัดและรอบถัดไปเริ่มใหม่
    job_timeout = 120
    keep_result = 300

    # 🔁 `process_pending` จัดการ retry เองผ่าน `attempts`/`next_attempt_at` ในตาราง
    #    ⇒ ไม่ให้ ARQ retry ซ้อน (จะกลายเป็นส่งซ้ำสองกลไก)
    max_tries = 1
