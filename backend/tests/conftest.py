"""
Fixtures & Setup สำหรับ Pytest integration tests ของ PIRIvoice

Pattern ตามโปรเจคเก่า:
- test_db_url: สร้าง DB ใหม่แบบสุ่มชื่อทุก session → init_db → drop ตอนจบ
- client: เปลี่ยน settings.DATABASE_URL ไปยัง test DB
- clean_database: ล้าง master tables ก่อนทุก test
"""
import pytest_asyncio
import pytest
import asyncpg
import asyncio
import uuid
import tempfile
import os
from urllib.parse import urlparse
from fastapi.testclient import TestClient

from core.config import settings
from main import app
from core.init_db import init_db

# 📁 โฟลเดอร์เก็บไฟล์ Excel สำหรับเทส (แทน /data/imports ของ Docker)
settings.IMPORT_STORAGE_DIR = tempfile.mkdtemp(prefix="piri_import_test_")

# 🔑 ไฟล์ credentials ของ seed users — ชี้ไป temp dir (กันเขียนทับไฟล์จริงตอนเทส)
settings.SEED_CREDENTIALS_FILE = os.path.join(
    tempfile.mkdtemp(prefix="piri_seed_test_"), "seed_credentials.txt"
)

# 🧹 ตารางที่ต้องถูกล้างก่อนทุก test — **แหล่งความจริงเดียวของรายการนี้**
#
# ⚠️ ทำไมต้องเป็นค่าคงที่ตัวเดียว: รายการนี้ถูกใช้ **สองที่** — `clean_database` (ล้างจริง)
#    และ post-condition ของ `test_db_url` (พิสูจน์ว่า schema สร้างครบ) ⇒ ถ้าเขียนซ้ำสองที่
#    วันที่เพิ่มตารางใหม่แล้วลืมที่หนึ่ง จะได้ "ตารางที่ไม่เคยถูกล้าง" ซึ่งอ่านไม่ออกว่า
#    เป็นเพราะอะไร (เทสต์ผ่านบ้างไม่ผ่านบ้างตามลำดับการรัน) — คลาสเดียวกับ skills.md เรื่อง
#    "สำนวน SQL เดียวกันเขียนสองที่"
#
# 📌 เพิ่มตารางใหม่ ⇒ **เพิ่มที่นี่ที่เดียว** (ทั้งการล้างและการตรวจ schema ได้พร้อมกัน)
_TABLES = (
    "users", "rooms", "students", "issues",
    "issue_steps", "issue_escalations", "issue_countdowns",
    "issue_status_history", "audit_logs", "student_import_jobs",
    "issue_comments", "piri_boards", "piri_board_comments",
    "piri_vote_choices", "piri_votes", "piri_board_reactions",
    "piri_board_reports", "piri_board_views", "notifications",
    "notification_preferences", "academic_terms", "announcements",
    "push_subscriptions", "push_outbox", "bookmarks", "app_settings",
    "event_registrations", "events", "academic_years", "rollover_runs",
)

# 🌟 ปีการศึกษาที่ `clean_database` ปลูกกลับหลัง TRUNCATE (migration 027)
#
# ⚠️ **ทำไมต้องปลูกกลับ — ไม่ใช่ของแถม:**
#   `students.academic_year_id` เป็น `NOT NULL DEFAULT <id ของปีปัจจุบัน>` (literal)
#   พอ `TRUNCATE` ลบแถวปีทิ้ง ค่า DEFAULT จะกลายเป็น id ที่ **ไม่มีอยู่จริง**
#   ⇒ `INSERT INTO students` ทุกครั้งที่ไม่ระบุปี (ซึ่งคือ *ทุกเทสต์* — ทั้ง create_student,
#      register_user และ import) จะล้มด้วย FK violation ทันที
#   ⇒ การปลูกกลับจึงเป็นสิ่งที่ทำให้ **เทสต์ทั้งชุดยังรันได้** ไม่ใช่แค่เรื่องของเทสต์ปีการศึกษา
#
# ⚠️ ค่าคงที่ (ไม่ใช้สูตร พ.ศ. แบบ migration 027) โดยเจตนา — เทสต์ต้อง **เดาได้**
#    ว่าแถวไหนคือปีปัจจุบัน · ใช้ id ที่ INSERT คืนมา **เขียน DEFAULT ทับ** ด้านล่าง
#    (ไม่ hardcode id เพราะ sequence ไม่ได้ reset) ⇒ ตรงกับที่ `set_current_year` ทำจริง
SEED_YEAR_BE = 2569


@pytest_asyncio.fixture(scope="session")
async def test_db_url():
    """สร้าง PostgreSQL Database ใหม่แบบสุ่มชื่อ และคืนค่า URL"""
    db_name = f"test_db_{uuid.uuid4().hex}"

    parsed_url = urlparse(settings.DATABASE_URL)
    base_url = f"{parsed_url.scheme}://{parsed_url.username}:{parsed_url.password}@{parsed_url.hostname}:{parsed_url.port}"
    sys_db_url = f"{base_url}/postgres"

    sys_conn = await asyncpg.connect(sys_db_url)
    try:
        await sys_conn.execute(f'CREATE DATABASE "{db_name}"')
    finally:
        await sys_conn.close()

    new_db_url = f"{base_url}/{db_name}"

    # เปลี่ยน URL ชั่วคราว + สร้าง schema
    original_db_url = settings.DATABASE_URL
    settings.DATABASE_URL = new_db_url

    # ⚠️⚠️ **ห้ามครอบด้วย try/except ที่แค่ print** — เคยเป็นแบบนั้นและมันกลืนความล้มเหลว
    #    ของ `init_db` ทิ้ง ⇒ session เดินต่อด้วย DB ที่ **ว่างเปล่า** แล้วเทสต์ 250 ตัว
    #    ล้มด้วย `relation "issues" does not exist` ซึ่งชี้ไปที่เทสต์ ไม่ได้ชี้ที่ต้นเหตุ
    #    (และถ้าเทสต์ไหนไม่แตะตารางที่หาย มันจะ **ผ่าน** ทั้งที่ schema ไม่ครบ)
    #    ⇒ ปล่อยให้ exception หลุดออกไปเลย · งานเก็บกวาดยังอยู่ใน `finally` ตามเดิม
    try:
        temp_pool = await asyncpg.create_pool(new_db_url)
        try:
            await init_db(temp_pool)   # ← สร้างตาราง + รัน migrations ทั้งหมด

            # 🔎 Post-condition: พิสูจน์ว่า schema สร้าง **ครบ** ไม่ใช่แค่ "ไม่ throw"
            #    `init_db` รัน `CREATE TABLE IF NOT EXISTS` ทีละตาราง ⇒ ถ้ามีอะไรผิดกลางทาง
            #    (หรือ migration ที่เพิ่มตารางถูกลบ/เปลี่ยนชื่อ) มันจะจบแบบ "สำเร็จ" ทั้งที่ขาด
            #    ⇒ ตรวจรายการเดียวกับที่ `clean_database` จะใช้จริง — ตรงกับอาการที่เกิดขึ้นจริง
            existing = {
                r["tablename"]
                for r in await temp_pool.fetch(
                    "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
                )
            }
            missing = [t for t in _TABLES if t not in existing]
            assert not missing, (
                f"⚠️ init_db สร้าง schema ไม่ครบ — ขาดตาราง: {', '.join(missing)}\n"
                f"   (สร้างได้ {len(existing)} ตาราง) — ต้นเหตุอยู่ที่ core/init_db.py "
                f"หรือ migrations/ ไม่ใช่ที่เทสต์"
            )
        finally:
            await temp_pool.close()
    finally:
        settings.DATABASE_URL = original_db_url

    yield new_db_url

    # cleanup: drop database
    sys_conn = await asyncpg.connect(sys_db_url)
    try:
        await sys_conn.execute(f"""
            SELECT pg_terminate_backend(pg_stat_activity.pid)
            FROM pg_stat_activity
            WHERE pg_stat_activity.datname = '{db_name}'
            AND pid <> pg_backend_pid();
        """)
        await sys_conn.execute(f'DROP DATABASE "{db_name}"')
    finally:
        await sys_conn.close()


@pytest_asyncio.fixture(scope="function")
async def db_pool(test_db_url):
    pool = await asyncpg.create_pool(test_db_url)
    yield pool
    await pool.close()


@pytest_asyncio.fixture(scope="function", autouse=True)
async def clean_database(db_pool):
    """ล้างข้อมูลทุกตารางก่อนแต่ละ test (รายการมาจาก `_TABLES` — ดูคอมเมนต์ที่นั่น)
    แล้วปลูก "ปีการศึกษาปัจจุบัน" กลับ (ดู `SEED_YEAR_BE`)"""
    async with db_pool.acquire() as conn:
        # ⚠️ `TRUNCATE` รับได้แค่ชื่อตารางที่ **ไม่ใช่** ค่าที่ผูกเป็น parameter ($1)
        #    ⇒ ต้องประกอบสตริง · ปลอดภัยเพราะ `_TABLES` เป็นค่าคงที่ในไฟล์นี้ ไม่มีทางมาจากผู้ใช้
        await conn.execute(f"TRUNCATE TABLE {', '.join(_TABLES)} CASCADE")

        # 🌟 ปลูกปีปัจจุบันกลับ + ชี้ DEFAULT ของ students มาที่แถวใหม่ (ดูเหตุผลที่ SEED_YEAR_BE)
        #    เรียงสองบรรทัดนี้สำคัญ: INSERT ก่อน แล้วค่อย ALTER (ต้องรู้ id ก่อน)
        year_id = await conn.fetchval(
            """
            INSERT INTO academic_years (year_be, name, is_current)
            VALUES ($1, $2, TRUE)
            RETURNING id
            """,
            SEED_YEAR_BE, f"ปีการศึกษา {SEED_YEAR_BE}",
        )
        assert year_id is not None
        await conn.execute(
            f"ALTER TABLE students ALTER COLUMN academic_year_id SET DEFAULT {int(year_id)}"
        )
    yield


@pytest_asyncio.fixture(scope="function")
async def current_year(db_pool):
    """แถวปีการศึกษาปัจจุบันที่ `clean_database` ปลูกไว้ — `{id, year_be, name}`

    ใช้เมื่อเทสต์ต้องรู้ id ของปีปัจจุบัน (เช่น สร้างสมาชิกในปีนี้ หรือยืนยันว่า
    `list_students` กรองปีถูก) — **ห้าม hardcode id** ตามกฎ testing.md
    """
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, year_be, name FROM academic_years WHERE is_current AND deleted_at IS NULL"
        )
    assert row is not None, "clean_database ต้องปลูกปีปัจจุบันไว้เสมอ"
    return dict(row)


@pytest.fixture(scope="function")
def client(test_db_url):
    """TestClient ที่ชี้ไปยัง test DB"""
    original_db_url = settings.DATABASE_URL
    settings.DATABASE_URL = test_db_url

    with TestClient(app) as test_client:
        yield test_client

    settings.DATABASE_URL = original_db_url
