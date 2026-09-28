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

    temp_pool = None
    try:
        temp_pool = await asyncpg.create_pool(new_db_url)
        await init_db(temp_pool)
    except Exception as e:
        print(f"⚠️ Error initializing test database schema: {e}")
    finally:
        if temp_pool:
            await temp_pool.close()
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
    """ล้างข้อมูลทุกตารางก่อนแต่ละ test"""
    async with db_pool.acquire() as conn:
        await conn.execute("""
            TRUNCATE TABLE users, rooms, students, issues,
                issue_steps, issue_escalations, issue_countdowns,
                issue_status_history, audit_logs, student_import_jobs,
                issue_comments, piri_boards, piri_board_comments,
                piri_vote_choices, piri_votes, piri_board_reactions,
                piri_board_reports, piri_board_views, notifications,
                notification_preferences, announcements
            CASCADE
        """)
    yield


@pytest.fixture(scope="function")
def client(test_db_url):
    """TestClient ที่ชี้ไปยัง test DB"""
    original_db_url = settings.DATABASE_URL
    settings.DATABASE_URL = test_db_url

    with TestClient(app) as test_client:
        yield test_client

    settings.DATABASE_URL = original_db_url
