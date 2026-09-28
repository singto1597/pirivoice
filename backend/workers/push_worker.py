"""
ARQ Worker สำหรับ Web Push (A3)
================================
รันด้วย: python -m arq workers.push_worker.WorkerSettings

⭐ **ทำไมแยกไฟล์จาก `import_worker.py`** (ไม่ใช่ยัด cron เข้าไปในไฟล์เดิม):
   `import_worker` ตั้ง `max_jobs = 1` + `job_timeout = 3600` โดยเจตนา (กัน import
   นักเรียนสองงานชนกันสร้าง users ซ้ำ) ⇒ ถ้าเอา push cron ไปไว้ในไฟล์นั้น
   **การ import นักเรียนตอนเปิดเทอมจะบล็อก push ทั้งชั่วโมง** และไม่มีใครรู้
   จนมีคนบ่นว่า "เปิดเทอมแล้วการแจ้งเตือนเงียบ" ⇒ แยก worker คนละโปรเซสกันเลย

⭐⭐ **จังหวะส่งเป็นของลูปในไฟล์นี้ ไม่ใช่ของ ARQ cron** (แก้ 28 ก.ย. 2026)
   รอบแรกของ A3 พึ่ง ARQ cron (`second={0,20,40}`) เป็นตัวกำหนดจังหวะ ซึ่ง **พังจริง**:
   วัดบน staging ได้ cron ยิงทุก **~150 วินาที** แทนที่จะเป็น 20 และ **ไม่มี error
   ให้เห็นเลย** ⇒ คิว 733 แถวใช้เวลา 40 นาที ของจริงหมดอายุ (`PUSH_MAX_AGE_MINUTES`)
   แล้วถูกทิ้งเงียบ ๆ — อาการที่ผู้ใช้รายงานคือ "แจ้งเตือนแค่ครั้งแรก แล้วไม่แจ้งอีก"

   กลไกที่ทำให้พัง (อ่านซอร์ส ARQ 0.28.0 ในอิมเมจจริง):
     `run_cron` ยิงรอบหนึ่งก็ต่อเมื่อ **heartbeat ตกลงในหน้าต่าง 1 วินาที** ก่อนถึง
     `next_run` (`cron_window_size = max(poll_delay_s, 0.5)`, `num_windows = 2`)
     และเมื่อยิงแล้วมัน **ไล่ `next_run` ไปได้ทีละรอบเท่านั้น** (ไม่มี while-loop)
     ⇒ พอ heartbeat ห่างเกิน 1 วินาที `next_run` จะตกหลังนาฬิกาจริง แล้ว
     **ตามไม่ทันตลอดไป** เพราะแต่ละ heartbeat ไล่ได้ 20 วิ แต่นาฬิกาเดิน 150 วิ
     ⇒ ยิ่งช้า ยิ่งตามไม่ทัน (self-reinforcing lag) · รอบที่ได้จะหลุดกริด :00/:20/:40
     ซึ่งเป็นร่องรอยที่ตรวจพบได้ใน log

   ⇒ **ทางแก้คือไม่พึ่ง cron ในการกำหนดอัตราส่ง** — `_delivery_loop()` ข้างล่างตื่นทุก
     `PUSH_TICK_SECONDS` (ค่าเริ่มต้น 5 วิ) แล้วเรียก `push_service.drain()` ซึ่งระบาย
     คิวจนเกลี้ยง · ส่วน cron ยังเก็บไว้เป็น **ตาข่ายกันลูปตาย** ไม่ใช่ตัวจับจังหวะ
     (ถ้าลูปในโปรเซสตายด้วย exception ที่หลุด ด่าน `except` ในลูปกันไว้แล้วชั้นหนึ่ง
      และ cron ก็ยังเคาะอยู่ ⇒ push ไม่หยุดสนิท)

⚠️ **`unique=True` เป็น default ของ ARQ cron** ⇒ ถ้ามีหลาย replica จะมีตัวเดียวทำงาน
   (กัน cron ซ้อน) · ส่วน `_delivery_loop` รัน**ทุก replica** โดยเจตนา — ปลอดภัยเพราะ
   `_claim()` ใช้ `FOR UPDATE SKIP LOCKED` ⇒ สองตัวพร้อมกันหยิบคนละแถว ไม่มีทางส่งซ้ำ
   (ถ้าวันหน้าขึ้น replicas > 1 จริง ควรตรวจว่า ARQ cron ยัง unique อยู่)
"""
import asyncio
import logging

import asyncpg
from arq import cron
from arq.connections import RedisSettings

from core.config import settings
from core.request_context import audit_scope
from services import push_service

# 🚨 **บรรทัดนี้จำเป็นจริง ไม่ใช่พิธีกรรม** — worker ไม่ได้ import `main.py` หรือ
#    `core/init_db.py` ซึ่งเป็นสองที่เดียวที่เรียก `logging.basicConfig` ⇒ root logger
#    ไม่มี handler ⇒ `logging.lastResort` ปล่อยเฉพาะ WARNING+ ออก stderr และ
#    **`logger.info` ถูกทิ้งเงียบ ๆ ทั้งหมด**
#    ผลที่เกิดจริง (28 ก.ย. 2026): บรรทัด `📤 push:` ซึ่งเป็น **ที่เดียว** ที่โชว์
#    `stale`/`skipped`/`dropped` **ไม่เคยขึ้นเลยแม้แต่ครั้งเดียว** ⇒ บั๊กคิวท่วมซ่อนตัว
#    อยู่ได้ทั้งรอบโดยไม่มีใครเห็น · ถ้าลบสองบรรทัดนี้ ระบบจะกลับไปตาบอดทันที
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger("PUSH_WORKER")


def _log_stats(stats: dict, *, source: str) -> None:
    """log เฉพาะรอบที่มีของจริง — ไม่งั้น log จะท่วมด้วย "claimed 0"

    ⚠️ `stale` และ `dropped` ในบรรทัดนี้คือ **ของที่หายถาวร** ไม่ใช่สถิติเฉย ๆ
       ⇒ ห้ามตัดออกรอบหน้า (ดู `_log_stats` ที่ต้องมีครบทั้ง 7 ตัวนับ)
    """
    if not stats["claimed"]:
        return
    logger.info(
        "📤 push[%s]: claimed=%d sent=%d gone=%d retry=%d dropped=%d skipped=%d stale=%d",
        source, stats["claimed"], stats["sent"], stats["gone"], stats["retry"],
        stats["dropped"], stats["skipped"], stats["stale"],
    )


async def _delivery_loop(ctx: dict) -> None:
    """ลูปลำเลียงของ worker เอง — **ตัวกำหนดจังหวะส่งจริง** (ดู docstring หัวไฟล์)

    ตื่นทุก `PUSH_TICK_SECONDS` แล้วระบายคิวจนเกลี้ยง · คิวว่าง = คิวรีเดียวแล้วหลับ
    ⇒ จ่ายถูกพอจะตื่นทุก 5 วินาที และเป็นเหตุที่ "จังหวะส่ง" ไม่ผูกกับ ARQ cron อีก

    ⚠️ `except Exception` **ต้องกว้างแบบนี้** — ลูปนี้ห้ามตาย เพราะถ้าตายจะไม่มีอะไร
       เตือน (งานจะยังไหลผ่าน cron แต่ช้าลงเงียบ ๆ) ⇒ จับทุกอย่างที่ไม่ใช่
       `CancelledError` แล้วไปต่อรอบหน้า
    """
    while True:
        await asyncio.sleep(settings.PUSH_TICK_SECONDS)
        try:
            # 📡 worker ไม่ได้ผ่าน HTTP → ต้องครอบ audit_scope เอง ไม่งั้น log ของงานนี้
            #    จะไม่มี trace_id/endpoint (ดู core/request_context.py)
            with audit_scope(endpoint="arq:push_delivery_loop"):
                stats = await push_service.drain(ctx["pool"])
            _log_stats(stats, source="loop")
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("❌ ลูปลำเลียงล้ม — จะลองใหม่รอบถัดไป")


async def startup(ctx: dict) -> None:
    """สร้าง db pool + กู้แถวที่ worker ก่อนหน้าจองค้างไว้ + สตาร์ทลูปลำเลียง

    ⚠️ `recover_stale_outbox()` ใน startup คือ **ด่านที่ขาดไม่ได้** — ถ้า worker ตาย
       หลัง claim แต่ก่อนจดผล แถวนั้นจะมี `processing_at` ค้าง และคิวรี claim
       (ที่กรอง `processing_at IS NULL`) จะ **ไม่มีวันหยิบมันอีกเลย** ⇒ push หยุดเงียบ
       ไม่มี error ที่ไหนให้เห็น · เป็นอาการที่หาสาเหตุยากที่สุดในระบบคิว
    """
    ctx["pool"] = await asyncpg.create_pool(settings.DATABASE_URL, min_size=1, max_size=5)
    try:
        with audit_scope(endpoint="arq:recover_stale_outbox"):
            recovered = await push_service.recover_stale_outbox(ctx["pool"])
        if recovered:
            logger.warning("♻️ กู้แถว outbox ที่ค้างจากการ claim %d แถว", recovered)
    except Exception:
        logger.exception("❌ recover stale outbox ล้มเหลว (จะลองใหม่ตอน start ครั้งหน้า)")

    # เก็บ task ไว้ที่ ctx เพื่อให้ shutdown ยกเลิกได้ (ไม่ให้ค้างตอน redeploy)
    ctx["delivery_task"] = asyncio.create_task(_delivery_loop(ctx))


async def shutdown(ctx: dict) -> None:
    task = ctx.get("delivery_task")
    if task is not None:
        task.cancel()
        # กลืน CancelledError ของตัวเอง — ถ้าปล่อยให้หลุด ARQ จะ log ว่า shutdown ล้มเหลว
        # ทั้งที่มันจบตามที่สั่ง (และจะทำให้เข้าใจผิดว่า worker มีบั๊ก)
        try:
            await task
        except asyncio.CancelledError:
            pass
    await ctx["pool"].close()


async def process_push_outbox(ctx: dict) -> dict:
    """ARQ cron: ตาข่ายกันลูปตาย — **ไม่ใช่ตัวกำหนดจังหวะส่ง** (ดู docstring หัวไฟล์)

    เรียก `drain()` เหมือนลูป ⇒ ถ้าลูปในโปรเซสตาย cron ยังเก็บงานให้ ไม่มีอะไรค้าง
    """
    with audit_scope(endpoint="arq:process_push_outbox"):
        stats = await push_service.drain(ctx["pool"])
    _log_stats(stats, source="cron")
    return stats


async def cleanup_push_outbox(ctx: dict) -> int:
    """ARQ cron: ลบแถว outbox ที่จบแล้วและเก่ากว่า `PUSH_RETENTION_DAYS` (วันละครั้ง)

    งานนี้ **จังหวะไม่สำคัญ** (วันละครั้ง ไม่มีใครรอ) ⇒ ใช้ ARQ cron ตามปกติได้
    ต่างจาก `process_push_outbox` ที่จังหวะคือ "ผู้ใช้รอนานแค่ไหน" โดยตรง
    """
    with audit_scope(endpoint="arq:cleanup_push_outbox"):
        deleted = await push_service.cleanup_outbox(ctx["pool"])
    if deleted:
        logger.info("🧹 ลบแถว outbox เก่า %d แถว", deleted)
    return deleted


class WorkerSettings:
    cron_jobs = [
        # ⏱️ ทุก 20 วินาที — **ตาข่ายกันลูปตาย** ไม่ใช่ตัวจับจังหวะ (ตัวจริงคือ
        #    `_delivery_loop` ที่ตื่นทุก PUSH_TICK_SECONDS) ⇒ ต่อให้ cron หลุดนัด
        #    (ซึ่งเกิดขึ้นจริง วัดได้ ~150 วิ) เวลาส่งก็ยังเป็น 5 วิตามเดิม
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

    # ⏱️ 1 รอบระบายได้หลาย batch จนหมด `PUSH_DRAIN_SECONDS` (45 วิ) — ไม่ใช่
    #    `PUSH_BATCH_SIZE` × 1 อีกต่อไป ⇒ 120 วิเหลือ margin 2.6 เท่า
    #    ⚠️ ถ้าจะเพิ่ม `PUSH_DRAIN_SECONDS` ต้องเพิ่มค่านี้ตาม (และกลับกัน)
    job_timeout = 120
    keep_result = 300

    # 🔁 `process_pending` จัดการ retry เองผ่าน `attempts`/`next_attempt_at` ในตาราง
    #    ⇒ ไม่ให้ ARQ retry ซ้อน (จะกลายเป็นส่งซ้ำสองกลไก)
    max_tries = 1
