from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import asyncpg
import logging
import uuid

from core.config import settings
from core.init_db import init_db
from core.request_context import set_audit_context, clear_audit_context
# 📡 hub ระดับโมดูล — import ที่นี่ (ไม่ใช่ใน lifespan) เพื่อให้ฝั่ง shutdown
#    อ้างถึงได้เสมอ แม้บางขั้นตอนใน lifespan จะล้มไปก่อน
from services.notification_stream import hub

from routers import auth_router
from routers import issue_router
from routers import dashboard_router
from routers import student_router
from routers import import_router
from routers import audit_router
from routers import boards
from routers import notification_router
from routers import announcement_router
from routers import settings_router
from routers import bookmark_router, me_router
from routers import event_router
from routers import home_router
from routers import public_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("API_MAIN")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """ก่อน yield = ตอนเปิด, หลัง yield = ตอนปิด"""
    logger.info("🚀 Starting PIRIvoice API...")

    try:
        app.state.db_pool = await asyncpg.create_pool(
            settings.DATABASE_URL,
            min_size=1,
            max_size=10
        )
        logger.info("✅ Database Connection Pool Created Successfully!")

        # 🚀 เรียกใช้ Schema Setup จาก core.init_db
        await init_db(app.state.db_pool)

        # 👥 สร้างบัญชีผู้ดูแลระบบเริ่มต้น (admin/ครูสภา/ประธานสภา) ถ้ายังไม่มี
        #    (idempotent + ตั้ง must_change_password → บังคับเปลี่ยนรหัสตอน login ครั้งแรก)
        from core.seed_users import seed_default_users
        await seed_default_users(app.state.db_pool)

        # 📡 เปิด LISTEN สำหรับ SSE (badge อัปเดตทันที) — migration 020
        #    ⚠️ ต้องเรียก **หลัง** `init_db` เพราะ trigger ที่ยิง `pg_notify` ถูกสร้างที่นั่น
        #       (จริง ๆ LISTEN ไม่ต้องรอ channel มีอยู่ — แต่รอให้ schema พร้อมก่อนคือลำดับ
        #        ที่อ่านแล้วไม่ต้องคิดต่อ)
        #    ⚠️ `start()` **ไม่ raise** ถ้าต่อไม่ได้ โดยเจตนา — ดู docstring ใน notification_stream.py
        #       (in-app ยังใช้ poll 30 วิได้ ⇒ ไม่ควรล้มทั้งระบบเพราะของที่ทำให้ "เร็วขึ้น")
        await hub.start(settings.DATABASE_URL)

    except Exception as e:
        logger.error(f"❌ Failed to connect to Database: {e}")
        raise e

    yield

    logger.info("🛑 Shutting down... Closing Database Pool.")
    # ปิด stream ก่อน pool — ผู้รับที่ค้างอยู่จะได้ไม่ตื่นมาใช้ pool ที่ปิดแล้ว
    await hub.stop()
    await app.state.db_pool.close()
    logger.info("✅ Database Pool Closed.")

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.PROJECT_VERSION,
    description="PIRIvoice API — ระบบรับฟังความคิดเห็นและปัญหาสภานักเรียน (เสียงจากชาวพิริยาลัย)",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://0.0.0.0:5173",
        # 🔄 โดเมนใหม่ PIRIvoice (rebrand)
        "https://pirivoice.com",
        "https://www.pirivoice.com",
        "https://test.pirivoice.com",
        "https://staging.pirivoice.com",
        # 🔁 โดเมนเก่าช่วงเปลี่ยนผ่าน (ยังไม่ย้าย DNS) — เก็บไว้กัน CORS พัง อย่าลบจนกว่าจะย้ายเสร็จ
        "https://prsc-test.singto1597.xyz",
        "https://prsc-test.pirivoice.com",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # ให้ JS ฝั่ง SPA อ่าน X-Trace-Id ได้ (middleware ส่งกลับทุก response) — ไม่งั้นเบราว์เซอร์ซ่อน
    expose_headers=["X-Trace-Id"],
)


def _client_ip(request: Request) -> str:
    """🌐 IP จริงของ client — อ่านตามลำดับความเชื่อถือได้ของ header

    🔗 เส้นทางจริงของ production/staging:
       client → Cloudflare → origin:80 (Swarm ingress) → Traefik 3 → backend

    ⚠️ ทำไมต้องอ่าน CF-Connecting-IP ก่อน XFF:
       Traefik publish พอร์ตแบบ `PublishMode: ingress` → Swarm routing mesh SNAT
       source IP ทิ้งไปแล้ว (Traefik เห็น peer เป็น 10.0.0.2 = ingress-endpoint)
       และ Traefik v3 ค่า default `forwardedHeaders.insecure=false` → **เมิน XFF
       ที่ Cloudflare ส่งมา แล้วเขียนทับด้วย 10.0.0.2** ⇒ อ่าน XFF ได้ค่าไร้ความหมาย
       ส่วน `CF-Connecting-IP` เป็น header ที่ Traefik ไม่ยุ่งด้วย จึงรอดมาถึง backend

    🔒 ขอบเขตความเชื่อถือ: header เหล่านี้ "ปลอมได้" ถ้ามีใครยิงเข้า origin ตรง ๆ
       (ข้าม Cloudflare) — ควรล็อกพอร์ต 80 ของ origin ให้รับเฉพาะ IP ของ Cloudflare
       ที่ระดับ firewall ก่อนถือว่า ip_address ใช้เป็นหลักฐานได้จริง
    """
    cf_ip = request.headers.get("cf-connecting-ip")
    if cf_ip:
        return cf_ip.strip()
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.headers.get("x-real-ip") or (request.client.host if request.client else "")


@app.middleware("http")
async def audit_context_middleware(request: Request, call_next):
    """📡 ตั้ง request context (ip จริง / user-agent / endpoint / trace_id / เวลาเริ่ม)
    ให้ AuditLogger เก็บอัตโนมัติ — services ไม่ต้องรับ param เพิ่ม
    (contextvar; ล้างหลัง request จบกัน leak ข้าม request)
    """
    trace_id = str(uuid.uuid4())
    set_audit_context(
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        trace_id=trace_id,
        endpoint=f"{request.method} {request.url.path}",
    )
    try:
        response = await call_next(request)
    finally:
        clear_audit_context()
    # ส่ง trace_id กลับไปด้วย — ผู้ใช้แจ้งปัญหาแล้วเทียบกับ audit_logs ได้ตรงแถว
    response.headers["X-Trace-Id"] = trace_id
    return response


app.include_router(auth_router.router, prefix="/api")
app.include_router(issue_router.router, prefix="/api")
app.include_router(dashboard_router.router, prefix="/api")
app.include_router(student_router.router, prefix="/api")
app.include_router(import_router.router, prefix="/api")
app.include_router(audit_router.router, prefix="/api")
app.include_router(boards.router, prefix="/api")
app.include_router(notification_router.router, prefix="/api")
app.include_router(announcement_router.router, prefix="/api")
app.include_router(settings_router.router, prefix="/api")
app.include_router(me_router.router, prefix="/api")
app.include_router(bookmark_router.router, prefix="/api")
app.include_router(event_router.router, prefix="/api")
app.include_router(home_router.router, prefix="/api")
app.include_router(public_router.router, prefix="/api/v1")


@app.get("/health", tags=["Health"])
async def health_check():
    try:
        # ถ้า Pool ทำงานได้ SELECT 1 จะคืนค่า 1
        async with app.state.db_pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        return {"status": "ok", "database": "connected"}
    except Exception as e:
        return {"status": "error", "database": "disconnected"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
