"""
Regression: migration 013 — audit_logs "ครบทุกคอลัมน์" บน DB เก่า

เรื่องจริงบน production: audit_logs ปล่อยคอลัมน์เป็น NULL ได้ (execution_time_ms ว่าง 100%,
room_id 94.7%, entity_id 42%, ip/user_agent 3.2%) → ตรวจย้อนหลังไม่ครบ

เทสต์นี้จำลอง DB "เก่า" (สคีมาเดิม: ทุกคอลัมน์ nullable + FK room_id ON DELETE CASCADE,
user_id ON DELETE SET NULL) แล้วรัน migration 013 ตรง ๆ บน DB นั้น ต้องได้ผลว่า
  1. room_id ของแถวเก่าถูก "กู้คืน" จากห้องที่ผู้กระทำสังกัด (ข้อมูลจริง ไม่ใช่ sentinel)
  2. แถวที่กู้คืนไม่ได้ → sentinel (-1 / '-' / {} / 0) และ **ต้องไม่ติด FK เดิม**
     (บั๊กที่เทสต์นี้จับ: ถ้าถอด FK ทีหลัง การเติม -1 จะ ForeignKeyViolationError)
  3. ทุกคอลัมน์กลายเป็น NOT NULL
  4. FK ถูกถอดออก → "ลบห้อง" ต้องไม่ลบประวัติ audit ทิ้งอีก
"""
import importlib
import json
import uuid
from urllib.parse import urlparse

import asyncpg
import pytest

from core.config import settings

# สคีมา audit_logs "เวอร์ชันเก่า" — คัดจาก core/init_db.py ก่อน migration 013 (ห้ามแก้ตามสคีมาใหม่)
OLD_AUDIT_LOGS_DDL = """
CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trace_id VARCHAR(50),
    room_id INTEGER REFERENCES rooms(id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    actor_identifier VARCHAR(100) NOT NULL,
    client_source VARCHAR(20) NOT NULL,
    service_name VARCHAR(50) NOT NULL,
    action VARCHAR(50) NOT NULL,
    entity_type VARCHAR(50),
    entity_id VARCHAR(50),
    status VARCHAR(20) DEFAULT 'success',
    error_detail TEXT,
    old_values JSONB,
    new_values JSONB,
    endpoint_or_command TEXT,
    ip_address VARCHAR(45),
    user_agent TEXT,
    execution_time_ms INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
"""

SUPPORT_TABLES_DDL = """
CREATE TABLE rooms (
    id SERIAL PRIMARY KEY, room_code VARCHAR(10) UNIQUE, room_name TEXT NOT NULL,
    level TEXT, room_number INTEGER, owner_id INTEGER, deleted_at TIMESTAMP
);
CREATE TABLE users (
    id SERIAL PRIMARY KEY, username VARCHAR(100) UNIQUE NOT NULL,
    password_hash TEXT NOT NULL, full_name TEXT, deleted_at TIMESTAMP
);
CREATE TABLE students (
    id SERIAL PRIMARY KEY, room_id INTEGER, user_id INTEGER, class_role TEXT,
    status TEXT DEFAULT 'active', deleted_at TIMESTAMP
);
"""


@pytest.mark.asyncio
async def test_migration_013_backfills_old_audit_rows_and_drops_fk():
    """DB เก่า (nullable + FK CASCADE) → migration 013 ต้องเติมครบทุกคอลัมน์โดยไม่พัง FK"""
    parsed = urlparse(settings.DATABASE_URL)
    base_url = (
        f"{parsed.scheme}://{parsed.username}:{parsed.password}"
        f"@{parsed.hostname}:{parsed.port}"
    )
    db_name = f"audit013_{uuid.uuid4().hex}"

    sys_conn = await asyncpg.connect(f"{base_url}/postgres")
    try:
        await sys_conn.execute(f'CREATE DATABASE "{db_name}"')
    finally:
        await sys_conn.close()

    pool = await asyncpg.create_pool(f"{base_url}/{db_name}")
    try:
        async with pool.acquire() as conn:
            await conn.execute(SUPPORT_TABLES_DDL)
            await conn.execute(OLD_AUDIT_LOGS_DDL)

            # ข้อมูลตั้งต้น: ห้อง 1 ; user 10 อยู่ห้อง 1 ; user 11 ไม่สังกัดห้อง
            await conn.execute(
                "INSERT INTO rooms (id, room_code, room_name, level) VALUES (1, 'ม.4/1', 'ม.4/1', 'ม.4')"
            )
            await conn.execute(
                "INSERT INTO users (id, username, password_hash) VALUES (10, 'u10', 'x'), (11, 'u11', 'x')"
            )
            await conn.execute(
                "INSERT INTO students (room_id, user_id, class_role, status) VALUES (1, 10, 'student', 'active')"
            )

            # A: แถวที่มี user (กู้คืนห้องได้) แต่คอลัมน์อื่นว่างหมด
            await conn.execute(
                """
                INSERT INTO audit_logs (user_id, actor_identifier, client_source, service_name, action)
                VALUES (10, 'u10', 'web', 'auth_service', 'login')
                """
            )
            # B: login ที่หาชื่อไม่เจอ (user_id NULL) → ไม่มีทางกู้คืน
            await conn.execute(
                """
                INSERT INTO audit_logs (actor_identifier, client_source, service_name, action, status, error_detail)
                VALUES ('ghost', 'web', 'auth_service', 'login', 'error', 'ไม่พบชื่อผู้ใช้นี้')
                """
            )
            # C: user ที่ไม่สังกัดห้อง
            await conn.execute(
                """
                INSERT INTO audit_logs (user_id, actor_identifier, client_source, service_name, action)
                VALUES (11, 'u11', 'worker', 'import_service', 'PROCESS_IMPORT_JOB')
                """
            )

        # --- รัน migration 013 ตรง ๆ บน DB เก่านี้ ---------------------------------
        migration = importlib.import_module("migrations.013_audit_logs_completeness")
        async with pool.acquire() as conn:
            await migration.upgrade(conn)

        async with pool.acquire() as conn:
            # 1) ไม่มีคอลัมน์ใดเป็น NULL อีก
            rows = await conn.fetch("SELECT * FROM audit_logs ORDER BY actor_identifier")
            assert len(rows) == 3
            for row in rows:
                for col, value in dict(row).items():
                    assert value is not None, f"{row['action']}: {col} ยังเป็น NULL"
                    if isinstance(value, str):
                        assert value != "", f"{row['action']}: {col} เป็นสตริงว่าง"

            by_actor = {r["actor_identifier"]: r for r in rows}

            # 2) กู้คืน room_id จากห้องที่ผู้กระทำสังกัด (ข้อมูลจริง)
            assert by_actor["u10"]["room_id"] == 1, "user 10 อยู่ห้อง 1 → ต้องกู้คืนได้"
            # 3) กู้คืนไม่ได้ → sentinel -1 (และต้องไม่ติด FK เดิม)
            assert by_actor["ghost"]["user_id"] == -1
            assert by_actor["ghost"]["room_id"] == -1
            assert by_actor["u11"]["room_id"] == -1, "user 11 ไม่มีห้อง → -1"

            # คอลัมน์อื่นได้ sentinel ที่อ่านออก
            login = by_actor["u10"]
            assert login["execution_time_ms"] == 0
            assert login["ip_address"] == "-"
            assert login["user_agent"] == "-"
            assert login["endpoint_or_command"] == "-"
            assert login["entity_type"] == "-"
            assert login["entity_id"] == "-"
            assert login["error_detail"] == "-"
            assert login["trace_id"] == "-"
            assert json.loads(login["old_values"]) == {}
            assert json.loads(login["new_values"]) == {}
            # error_detail ของ login ที่ล้มเหลวต้องคงค่าจริงไว้ (ไม่ถูกทับด้วย sentinel)
            assert by_actor["ghost"]["error_detail"] == "ไม่พบชื่อผู้ใช้นี้"

            # 4) DB บังคับ NOT NULL ทุกคอลัมน์แล้ว
            nullable = await conn.fetch(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'audit_logs' AND is_nullable = 'YES'
                """
            )
            assert not nullable, f"ยังมีคอลัมน์ที่ปล่อยว่างได้: {[r['column_name'] for r in nullable]}"

            # 5) FK ถูกถอดออก
            fks = await conn.fetch(
                """
                SELECT conname FROM pg_constraint
                WHERE conrelid = 'audit_logs'::regclass AND contype = 'f'
                """
            )
            assert not fks, f"ต้องไม่มี FK เหลืออยู่ แต่พบ {[r['conname'] for r in fks]}"

            # 6) ลบห้องแล้วประวัติ audit ต้องอยู่ครบ (เดิม FK CASCADE ลบทิ้งทั้งห้อง)
            await conn.execute("DELETE FROM rooms WHERE id = 1")
            assert await conn.fetchval("SELECT COUNT(*) FROM audit_logs") == 3, \
                "ลบห้องแล้ว audit log ต้องไม่หาย"
    finally:
        await pool.close()
        sys_conn = await asyncpg.connect(f"{base_url}/postgres")
        try:
            await sys_conn.execute(
                """
                SELECT pg_terminate_backend(pg_stat_activity.pid)
                FROM pg_stat_activity
                WHERE pg_stat_activity.datname = $1 AND pid <> pg_backend_pid()
                """,
                db_name
            )
            await sys_conn.execute(f'DROP DATABASE IF EXISTS "{db_name}"')
        finally:
            await sys_conn.close()
