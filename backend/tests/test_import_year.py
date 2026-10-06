# === Integration Tests: Excel Import × ปีการศึกษา (migration 028) ===
# ครอบคลุม: ไฟล์เก่า (8 คอลัมน์ ไม่มีปี) · ไฟล์ใหม่ (มีคอลัมน์ "ปีการศึกษา") · ปีของ job
#           · ปีที่ไม่มีในระบบ (ต้องไม่สร้างปีผี) · เซลล์ไม่ตรงกับปีของ job · import ซ้ำ
#           · ย้ายห้องในปีเดียวกัน (superseded) · เลื่อนชั้นแล้ว import ต้องไม่ชน/ไม่ซ้อน
#
# ⚠️ แยกจาก `test_import_jobs.py` โดยเจตนา: ไฟล์นั้นล็อก "พฤติกรรมของ import"
#    ไฟล์นี้ล็อก **"มิติปีของ import"** — และแตะ unique index ใหม่
#    `uq_students_room_year_student` ซึ่งเป็นของ migration 028 โดยเฉพาะ
#
# ⚠️ ไฟล์นี้ **ยืนได้เอง** (ไม่ import ข้ามไฟล์เทสต์ — ธรรมเนียมของ repo นี้)
#    helper ที่ซ้ำกับ `test_import_jobs.py` คือสำเนาโดยเจตนา: ถ้าอีกไฟล์แก้
#    ไฟล์นี้ต้องไม่พังตาม (และในทางกลับกัน)
#
# 🔴 ห้าม hardcode id ของปี — `clean_database` TRUNCATE `academic_years` ทุกเทสต์
#    แล้วปลูกปีปัจจุบันกลับ ⇒ sequence ไม่ reset และ id เปลี่ยนทุกเทสต์
#    ปีปัจจุบันต้องอ่านจาก DB เสมอ (ดู `_current_year_id`)
#
# ตามกฎ testing.md: Deep DB verification ทุกกรณี + random ID กัน state รั่ว + mock Redis
import io
import json
import random

import pytest
import pytest_asyncio
import openpyxl
from openpyxl import Workbook

from services import auth_service, import_service

# ปีในอนาคตที่เทสต์สร้างเอง — ห้ามชนกับ SEED_YEAR_BE (2569) ของ conftest
# (ชนแล้ว INSERT จะล้มด้วย uq_academic_years_year_be แล้วอ่านไม่ออกว่าทำไม)
NEXT_BE = 2570
FAR_BE = 2571
PHANTOM_BE = 2751  # "ปีผี" — พิมพ์ผิดแล้วต้องไม่ถูกสร้างขึ้นมาจริง ๆ

OLD_HEADER = [
    "รหัสนักเรียน", "ห้องเรียน", "เลขที่",
    "คำนำหน้า", "ชื่อ", "นามสกุล", "ชื่อเล่น", "ตำแหน่งในห้องเรียน",
]
FULL_HEADER = OLD_HEADER + ["ปีการศึกษา"]


# ============================================================
# Helpers (สำเนาจาก test_import_jobs.py — ดูหมายเหตุหัวไฟล์)
# ============================================================

def make_xlsx_bytes(rows, header=None):
    """สร้างไฟล์ .xlsx ในหน่วยความจำ (bytes) — ตาม Format ที่ระบบรองรับ"""
    wb = Workbook()
    ws = wb.active
    ws.append(header or OLD_HEADER)
    for r in rows:
        ws.append(r)
    bio = io.BytesIO()
    wb.save(bio)
    return bio.getvalue()


@pytest_asyncio.fixture
async def admin_user(db_pool):
    """admin (school-wide, room_id NULL) — มี MANAGE_STUDENTS ผ่าน is_admin"""
    username = f"adm{random.randint(100000, 999999)}"  # ≤10 chars (student_id VARCHAR(10))
    uid = await auth_service.register_user(
        db_pool, username, "1234", "แอดมิน เทส", username, "", 0, "admin"
    )
    return uid, username, "1234"


def login_token(client, username, password):
    res = client.post("/api/auth/login", json={"username": username, "password": password})
    assert res.status_code == 200, res.text
    return res.json()["access_token"]


def upload_excel(client, token, file_bytes, filename="students.xlsx",
                 default_password="1234", academic_year_id=None):
    """POST /api/upload-student-excel (sync — TestClient)

    🌟 `academic_year_id` ส่งเป็น **query param** — ต้องหายไปจาก URL เมื่อเป็น None
       (ส่ง `academic_year_id=` เปล่า ๆ จะกลายเป็น 422 ไม่ใช่ "ไม่ระบุ")
    """
    params = {"default_password": default_password}
    if academic_year_id is not None:
        params["academic_year_id"] = academic_year_id
    return client.post(
        "/api/upload-student-excel",
        files={"file": (filename, file_bytes,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers={"Authorization": f"Bearer {token}"},
        params=params,
    )


async def upload_and_get_job(client, token, rows, header=None, **kwargs):
    res = upload_excel(client, token, make_xlsx_bytes(rows=rows, header=header), **kwargs)
    assert res.status_code == 200, res.text
    return res.json()["id"]


# ============================================================
# Helpers ฝั่ง DB
# ============================================================

async def _current_year_id(db_pool):
    async with db_pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT id FROM academic_years WHERE is_current AND deleted_at IS NULL"
        )


async def _seed_year(db_pool, year_be):
    """สร้างปีที่ไม่ใช่ปีปัจจุบัน (ใช้เป็น 'ปีของ job' / 'ปีปลายทาง' ในเทสต์)"""
    async with db_pool.acquire() as conn:
        return await conn.fetchval(
            """
            INSERT INTO academic_years (year_be, name, is_current)
            VALUES ($1, $2, FALSE) RETURNING id
            """,
            year_be, f"ปีการศึกษา {year_be}",
        )


async def _student_rows(db_pool, student_id):
    """ทุกแถวของรหัสนี้ (รวมที่ถูก supersede แล้ว) — เรียงตาม id"""
    async with db_pool.acquire() as conn:
        return await conn.fetch(
            """
            SELECT s.id, s.status, s.room_id, s.academic_year_id, s.deleted_at,
                   r.room_code, y.year_be
            FROM students s
            LEFT JOIN rooms r ON r.id = s.room_id
            LEFT JOIN academic_years y ON y.id = s.academic_year_id
            WHERE s.student_id = $1
            ORDER BY s.id
            """,
            student_id,
        )


async def _job_row(db_pool, job_id):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM student_import_jobs WHERE id = $1", job_id)


# ============================================================
# 1. ไฟล์เก่า (8 คอลัมน์) — backward compatibility
#    🔴 เทสต์ชุดนี้คือ "สัญญาว่าครูที่ยังใช้ไฟล์เดิมอยู่นำเข้าได้ตามปกติ"
# ============================================================

@pytest.mark.asyncio
async def test_old_8_column_file_lands_in_current_year(client, db_pool, admin_user):
    """ไฟล์ไม่มีคอลัมน์ปี + ไม่ระบุปีของ job ⇒ แถวลง **ปีปัจจุบัน** (พฤติกรรมเดิมไม่เปลี่ยน)"""
    _, username, password = admin_user
    token = login_token(client, username, password)
    current_id = await _current_year_id(db_pool)

    job_id = await upload_and_get_job(client, token, [
        ["47001", "ม.4/1", 1, "นาย", "สมชาย", "ใจดี", "ชาย", ""],
    ])
    result = await import_service.process_import_job(db_pool, job_id)
    assert result["status"] == "COMPLETED"
    assert result["imported"] == 1
    assert result["errors"] == [], result["errors"]

    # 🔍 Deep DB: แถวอยู่ในปีปัจจุบัน + job ไม่มีปีของตัวเอง (NULL = โหมดผ่อนปรน)
    rows = await _student_rows(db_pool, "47001")
    assert len(rows) == 1
    assert rows[0]["academic_year_id"] == current_id
    assert rows[0]["status"] == "active"
    assert (await _job_row(db_pool, job_id))["academic_year_id"] is None


@pytest.mark.asyncio
async def test_old_8_column_file_ignores_job_year_when_blank(client, db_pool, admin_user):
    """ไฟล์เก่า 8 คอลัมน์ (ไม่มีช่องให้กรอกปี) + **ระบุปีของ job** ⇒ ลงปีของ job

    นี่คือทางที่ครูใช้ import ย้อนหลัง/ล่วงหน้าจริง: ไฟล์เดิมไม่ต้องแก้หัวตาราง
    """
    _, username, password = admin_user
    token = login_token(client, username, password)
    current_id = await _current_year_id(db_pool)
    next_id = await _seed_year(db_pool, NEXT_BE)

    job_id = await upload_and_get_job(
        client, token,
        [["47002", "ม.4/1", 1, "นาย", "สมชาย", "ใจดี", "", ""]],
        academic_year_id=next_id,
    )
    result = await import_service.process_import_job(db_pool, job_id)
    assert result["status"] == "COMPLETED"
    assert result["imported"] == 1, result["errors"]

    rows = await _student_rows(db_pool, "47002")
    assert len(rows) == 1
    assert rows[0]["academic_year_id"] == next_id, "ต้องเป็นปีของ job ไม่ใช่ปีปัจจุบัน"
    assert rows[0]["academic_year_id"] != current_id
    assert rows[0]["year_be"] == NEXT_BE
    assert (await _job_row(db_pool, job_id))["academic_year_id"] == next_id


# ============================================================
# 2. ไฟล์ใหม่ (มีคอลัมน์ "ปีการศึกษา")
# ============================================================

@pytest.mark.asyncio
async def test_year_column_can_target_a_past_or_future_year(client, db_pool, admin_user):
    """ไฟล์มีคอลัมน์ปี + ไม่ระบุปีของ job ⇒ ใช้ **ปีในเซลล์** (ไม่ใช่ปีปัจจุบัน)

    🔴 นี่คือหัวใจของ backward/forward compat: ครูที่มีไฟล์รวมหลายปีในชุดเดียว
       ต้องนำเข้าแล้วไปลงปีที่ถูกของแต่ละแถวได้
    """
    _, username, password = admin_user
    token = login_token(client, username, password)
    current_id = await _current_year_id(db_pool)
    next_id = await _seed_year(db_pool, NEXT_BE)

    job_id = await upload_and_get_job(
        client, token,
        [["47003", "ม.4/1", 1, "นาย", "สมชาย", "ใจดี", "", "", NEXT_BE]],
        header=FULL_HEADER,
    )
    result = await import_service.process_import_job(db_pool, job_id)
    assert result["status"] == "COMPLETED"
    assert result["imported"] == 1, result["errors"]

    rows = await _student_rows(db_pool, "47003")
    assert len(rows) == 1
    assert rows[0]["academic_year_id"] == next_id
    assert rows[0]["academic_year_id"] != current_id
    # job ยังไม่มีปีของตัวเอง — ปีมาจากข้อมูลรายแถว
    assert (await _job_row(db_pool, job_id))["academic_year_id"] is None


@pytest.mark.asyncio
async def test_year_cell_as_float_is_accepted(client, db_pool, admin_user):
    """เซลล์ปีที่ Excel เก็บเป็นตัวเลขทศนิยม (2570.0) → ใช้ได้ ไม่ใช่ error

    กับดักเดียวกับรหัสนักเรียน (`_cell_to_str` ต้องตัด `.0` ทิ้ง) — ถ้าไม่ตัด
    `int("2570.0")` จะ ValueError ⇒ ครูเห็น error ที่อ่านไม่ออกทั้งที่ข้อมูลถูก
    """
    _, username, password = admin_user
    token = login_token(client, username, password)
    next_id = await _seed_year(db_pool, NEXT_BE)

    job_id = await upload_and_get_job(
        client, token,
        [["47004", "ม.4/1", 1, "นาย", "สมชาย", "ใจดี", "", "", float(NEXT_BE)]],
        header=FULL_HEADER,
    )
    result = await import_service.process_import_job(db_pool, job_id)
    assert result["status"] == "COMPLETED"
    assert result["imported"] == 1, result["errors"]

    rows = await _student_rows(db_pool, "47004")
    assert len(rows) == 1
    assert rows[0]["academic_year_id"] == next_id


# ============================================================
# 3. ปีของ job — โหมดเข้ม (strict)
# ============================================================

@pytest.mark.asyncio
async def test_job_year_fills_blank_cells(client, db_pool, admin_user):
    """ระบุปีของ job + เซลล์ว่าง ⇒ ใช้ปีของ job (ไม่ใช่ปีปัจจุบัน)"""
    _, username, password = admin_user
    token = login_token(client, username, password)
    current_id = await _current_year_id(db_pool)
    next_id = await _seed_year(db_pool, NEXT_BE)

    job_id = await upload_and_get_job(
        client, token,
        [["47005", "ม.5/1", 1, "นาย", "สมชาย", "ใจดี", "", "", ""]],
        header=FULL_HEADER,
        academic_year_id=next_id,
    )
    result = await import_service.process_import_job(db_pool, job_id)
    assert result["status"] == "COMPLETED"
    assert result["imported"] == 1, result["errors"]

    rows = await _student_rows(db_pool, "47005")
    assert rows[0]["academic_year_id"] == next_id
    assert rows[0]["academic_year_id"] != current_id


@pytest.mark.asyncio
async def test_cell_year_conflicting_with_job_year_is_row_error(client, db_pool, admin_user):
    """ปีของ job = 2570 แต่เซลล์บอก 2569 ⇒ **error รายแถว** ไม่ใช่ลงปีใดปีหนึ่งเงียบ ๆ

    🔴 ทำไมต้องเข้ม: ไฟล์ที่ค้างมาจากปีก่อน (หัวตารางยังเป็นปีเก่า) ถ้าถูกนำเข้ากับ
       job ของปีใหม่แล้วระบบ "เชื่อ job" เงียบ ๆ ข้อมูลจะไปอยู่ผิดปีโดยไม่มีใครรู้
       ⇒ ต้องหยุดแล้วบอกผู้ใช้ ไม่ใช่เดาแทน
    """
    _, username, password = admin_user
    token = login_token(client, username, password)
    current_id = await _current_year_id(db_pool)
    next_id = await _seed_year(db_pool, NEXT_BE)

    job_id = await upload_and_get_job(
        client, token,
        [
            # เซลล์บอกปีเก่า (2569 = ปีปัจจุบัน) แต่ job เป็นปีใหม่
            ["47006", "ม.4/1", 1, "นาย", "คนละปี", "ต้องไม่ลง", "", "", 2569],
            ["47007", "ม.4/1", 2, "นาย", "แถวดี", "ต้องลงได้", "", "", NEXT_BE],
        ],
        header=FULL_HEADER,
        academic_year_id=next_id,
    )
    result = await import_service.process_import_job(db_pool, job_id)

    # แถวผิด = ข้าม (ไม่ใช่ FAILED ทั้งงาน) · แถวที่เหลือต้องเข้าได้
    assert result["status"] == "COMPLETED"
    assert result["imported"] == 1
    assert result["skipped"] == 1
    assert any("ไม่ตรงกับปีของงานนำเข้า" in e for e in result["errors"]), result["errors"]

    # 🔍 Deep DB: แถวที่ผิดต้องไม่ถูกสร้างในปีไหนเลย
    assert await _student_rows(db_pool, "47006") == []
    rows = await _student_rows(db_pool, "47007")
    assert len(rows) == 1
    assert rows[0]["academic_year_id"] == next_id
    assert rows[0]["academic_year_id"] != current_id


@pytest.mark.asyncio
async def test_upload_rejects_unknown_job_year(client, db_pool, admin_user):
    """ระบุปีของ job ที่ไม่มีในระบบ ⇒ 400 **ตอนอัปโหลด** + ไม่มี job ถูกสร้าง

    ต่างจากปีผีในเซลล์ (รายแถว) — ปีของ job เป็นค่าที่ผู้เรียกส่งมาตรง ๆ
    ⇒ ตรวจได้ทันทีที่ขอบ ⇒ ไม่ต้องรอ worker แล้วปล่อยให้แถวทั้งหมดพัง
    """
    _, username, password = admin_user
    token = login_token(client, username, password)

    res = upload_excel(
        client, token,
        make_xlsx_bytes([["47008", "ม.4/1", 1, "นาย", "สมชาย", "ใจดี", "", ""]]),
        academic_year_id=999999,
    )
    assert res.status_code == 400, res.text
    assert "ปีการศึกษา" in res.json()["detail"]

    async with db_pool.acquire() as conn:
        count = await conn.fetchval("SELECT count(*) FROM student_import_jobs")
        assert count == 0, "ต้องไม่ทิ้ง job ค้างไว้เมื่อปีไม่ถูกต้อง"


# ============================================================
# 4. ปีที่ไม่มีในระบบ — 🔴 ห้ามสร้าง "ปีผี"
# ============================================================

@pytest.mark.asyncio
async def test_unknown_year_in_cell_is_row_error_and_creates_no_phantom_year(
    client, db_pool, admin_user
):
    """เซลล์บอกปี 2751 (พิมพ์ผิดจาก 2571) ⇒ error รายแถว + **ต้องไม่มีปี 2751 เกิดขึ้น**

    🔴 นี่คือเทสต์ที่กันความเสียหายระยะยาว: ถ้าระบบสร้างปีจากเซลล์เอง จะได้ปีผีที่
       (ก) ไปชน invariant "ปีปัจจุบันมีได้ตัวเดียว" แบบหาสาเหตุไม่เจอ
       (ข) ถูกลบยากเพราะอาจมีแถว students อ้างอยู่
       (ค) ผู้ใช้เห็นปีแปลกในหน้าจอโดยไม่รู้ว่ามาจากไหน
    """
    _, username, password = admin_user
    token = login_token(client, username, password)

    job_id = await upload_and_get_job(
        client, token,
        [
            ["47009", "ม.4/1", 1, "นาย", "พิมพ์ผิด", "ปีผี", "", "", PHANTOM_BE],
            ["47010", "ม.4/1", 2, "นาย", "แถวดี", "ปกติ", "", "", ""],
        ],
        header=FULL_HEADER,
    )
    result = await import_service.process_import_job(db_pool, job_id)

    assert result["status"] == "COMPLETED"
    assert result["imported"] == 1
    assert result["skipped"] == 1
    assert any(str(PHANTOM_BE) in e for e in result["errors"]), result["errors"]

    # 🔍 Deep DB: ปีผีต้องไม่มีจริง + แถวนี้ต้องไม่ถูกสร้าง
    async with db_pool.acquire() as conn:
        phantom_id = await conn.fetchval(
            "SELECT id FROM academic_years WHERE year_be = $1", PHANTOM_BE
        )
        assert phantom_id is None, f"❌ ระบบสร้างปีผี {PHANTOM_BE} ขึ้นมาจริง"

        total_years = await conn.fetchval(
            "SELECT count(*) FROM academic_years WHERE deleted_at IS NULL"
        )
        assert total_years == 1, "ต้องมีแค่ปีปัจจุบัน — ไม่มีปีใหม่ถูกสร้างจากไฟล์ Excel"

    assert await _student_rows(db_pool, "47009") == []


@pytest.mark.parametrize("bad", ["abc", "2570.5", "2570 ปี", "พ.ศ. 2570"])
@pytest.mark.asyncio
async def test_non_numeric_year_cell_is_row_error(client, db_pool, admin_user, bad):
    """ค่าในช่องปีที่ **แปลงเป็น พ.ศ. ไม่ได้** ⇒ error รายแถว (ไม่ล้มทั้งงาน · ไม่สร้างปี)

    ⚠️ สองอย่างที่ **ไม่อยู่** ในรายการนี้ โดยเจตนา — แต่ละอย่างมีเทสต์ของตัวเอง:
       · `" "` (เว้นวรรคล้วน) → `_cell_to_str` strip ⇒ เป็น "ช่องว่าง" ไม่ใช่ "ค่าผิด"
       · `"๒๕๗๐"` (เลขไทย) → `int()` ของ Python รับ Unicode decimal digit ⇒ เป็น 2570 จริง
    """
    _, username, password = admin_user
    token = login_token(client, username, password)

    job_id = await upload_and_get_job(
        client, token,
        [["47011", "ม.4/1", 1, "นาย", "ค่าเพี้ยน", "ทดสอบ", "", "", bad]],
        header=FULL_HEADER,
    )
    result = await import_service.process_import_job(db_pool, job_id)

    assert result["status"] == "COMPLETED"
    assert result["imported"] == 0, result["errors"]
    assert result["skipped"] == 1
    assert await _student_rows(db_pool, "47011") == []
    async with db_pool.acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM academic_years") == 1


@pytest.mark.asyncio
async def test_thai_digit_year_cell_resolves_to_the_same_year(client, db_pool, admin_user):
    """เลขไทย `๒๕๗๐` ⇒ ปี 2570 ตามปกติ (int() ของ Python รับ Unicode decimal digit)

    🔒 ล็อกพฤติกรรมนี้ไว้โดยเจตนา **ไม่ใช่ฟลุ๊กที่ปล่อยผ่าน**: ระบบนี้เป็นภาษาไทย
       ทั้งระบบ ครูพิมพ์เลขไทยเป็นเรื่องที่เกิดได้จริง ⇒ ถ้าวันหนึ่งมีใครเปลี่ยนไปใช้
       regex `^\\d+$` (ซึ่ง `\\d` ใน Python ก็ยังรับเลขไทย) หรือ `re.ASCII` (ซึ่งไม่รับ)
       เทสต์นี้จะเป็นตัวบอกว่า "พฤติกรรมเปลี่ยนแล้ว" ไม่ใช่ให้ครูเจอเอง

    ⚠️ ที่ "ใช้ได้" เพราะปีนั้นมีอยู่จริงเท่านั้น — ถ้าพิมพ์เลขไทยของปีที่ไม่มี
       ก็ยังเป็น error รายแถวเหมือนเลขอาหรับ (ดูเทสต์ปีผี)
    """
    _, username, password = admin_user
    token = login_token(client, username, password)
    next_id = await _seed_year(db_pool, NEXT_BE)
    thai = "".join("๐๑๒๓๔๕๖๗๘๙"[int(d)] for d in str(NEXT_BE))
    assert thai == "๒๕๗๐", thai  # กันตัวเองเขียนผิด

    job_id = await upload_and_get_job(
        client, token,
        [["47020", "ม.4/1", 1, "นาย", "เลขไทย", "ทดสอบ", "", "", thai]],
        header=FULL_HEADER,
    )
    result = await import_service.process_import_job(db_pool, job_id)
    assert result["status"] == "COMPLETED"
    assert result["imported"] == 1, result["errors"]

    rows = await _student_rows(db_pool, "47020")
    assert len(rows) == 1
    assert rows[0]["academic_year_id"] == next_id


@pytest.mark.asyncio
async def test_whitespace_only_year_cell_is_treated_as_blank(client, db_pool, admin_user):
    """ช่องปีที่มีแต่เว้นวรรค ⇒ ถือเป็น **ช่องว่าง** (ใช้ปีปัจจุบัน) ไม่ใช่ error

    เจตนา: ครูพิมพ์ space หลงในช่อง (หรือ copy มาจาก Excel ที่มี trailing space)
    เป็นเรื่องปกติ ⇒ ต้องไม่ทำให้ทั้งแถวถูกทิ้ง เพราะ "ช่องว่าง" กับ "ค่าผิด"
    เป็นคนละเรื่อง — ค่าผิดคือ "2751" หรือ "abc" ซึ่งระบบไม่รู้จะทำอะไรต่อ
    """
    _, username, password = admin_user
    token = login_token(client, username, password)
    current_id = await _current_year_id(db_pool)

    job_id = await upload_and_get_job(
        client, token,
        [["47019", "ม.4/1", 1, "นาย", "เว้นวรรค", "ทดสอบ", "", "", "   "]],
        header=FULL_HEADER,
    )
    result = await import_service.process_import_job(db_pool, job_id)
    assert result["status"] == "COMPLETED"
    assert result["imported"] == 1, result["errors"]

    rows = await _student_rows(db_pool, "47019")
    assert len(rows) == 1
    assert rows[0]["academic_year_id"] == current_id


# ============================================================
# 5. import ซ้ำ / ย้ายห้องในปีเดียวกัน
# ============================================================

@pytest.mark.asyncio
async def test_reimport_same_year_does_not_duplicate(client, db_pool, admin_user):
    """import ไฟล์เดิมซ้ำ (ปีเดียวกัน ห้องเดิม) ⇒ ยังมีแถวเดียว (upsert ไม่ใช่ insert ซ้ำ)

    ล็อก arbiter ใหม่ `(room_id, academic_year_id, student_id)` — ถ้า ON CONFLICT
    ไม่ตรงกับ index จริง PostgreSQL จะโยน error ⇒ เทสต์นี้จะพังทันที
    """
    _, username, password = admin_user
    token = login_token(client, username, password)
    current_id = await _current_year_id(db_pool)
    rows = [["47012", "ม.4/1", 1, "นาย", "สมชาย", "ใจดี", "", ""]]

    job1 = await upload_and_get_job(client, token, rows)
    assert (await import_service.process_import_job(db_pool, job1))["imported"] == 1

    # รอบ 2 — ชื่อเล่นเปลี่ยน เพื่อพิสูจน์ว่า DO UPDATE ทำงานจริง ไม่ใช่ DO NOTHING
    rows2 = [["47012", "ม.4/1", 1, "นาย", "สมชาย", "ใจดี", "ชายสอง", ""]]
    job2 = await upload_and_get_job(client, token, rows2)
    r2 = await import_service.process_import_job(db_pool, job2)
    assert r2["status"] == "COMPLETED", r2["errors"]

    got = await _student_rows(db_pool, "47012")
    assert len(got) == 1, f"ต้องมีแถวเดียว — ได้ {len(got)}"
    assert got[0]["academic_year_id"] == current_id
    async with db_pool.acquire() as conn:
        assert await conn.fetchval(
            "SELECT nickname FROM students WHERE student_id = '47012'"
        ) == "ชายสอง"


@pytest.mark.asyncio
async def test_same_year_room_move_supersedes_the_old_row(client, db_pool, admin_user):
    """นำเข้าใหม่โดยเปลี่ยนห้อง (ปีเดียวกัน) ⇒ **แถวเก่าเป็น `superseded` ไม่ใช่ค้าง active**

    🔴 ถ้าไม่มี guard นี้: คนเดียวปรากฏสองห้อง · ยอด dashboard บวม ·
       RBAC เห็นสิทธิ์จากห้องที่เด็กไม่อยู่แล้ว ⇒ ต้องเหลือ active แถวเดียว
    """
    _, username, password = admin_user
    token = login_token(client, username, password)
    current_id = await _current_year_id(db_pool)

    job1 = await upload_and_get_job(client, token, [
        ["47013", "ม.4/1", 1, "นาย", "ย้ายห้อง", "ทดสอบ", "", ""],
    ])
    await import_service.process_import_job(db_pool, job1)

    job2 = await upload_and_get_job(client, token, [
        ["47013", "ม.4/2", 1, "นาย", "ย้ายห้อง", "ทดสอบ", "", ""],
    ])
    r2 = await import_service.process_import_job(db_pool, job2)
    assert r2["status"] == "COMPLETED", r2["errors"]

    got = await _student_rows(db_pool, "47013")
    assert len(got) == 2, "ต้องเหลือ 2 แถว (ห้องเก่า = ประวัติ · ห้องใหม่ = ปัจจุบัน)"

    old, new = got[0], got[1]
    assert old["room_code"] == "ม.4/1"
    assert old["status"] == "superseded", "แถวห้องเก่าต้องถูก supersede"
    assert old["deleted_at"] is None, "ห้ามลบ — ต้องเหลือเป็นประวัติ (soft delete เท่านั้น)"
    assert new["room_code"] == "ม.4/2"
    assert new["status"] == "active"
    assert old["academic_year_id"] == new["academic_year_id"] == current_id

    # 🔍 Deep DB: ไม่มีทางมี active ซ้อนในปีเดียวกัน
    async with db_pool.acquire() as conn:
        overlap = await conn.fetch(
            """
            SELECT user_id, count(*) FROM students
            WHERE deleted_at IS NULL AND status = 'active'
            GROUP BY user_id HAVING count(*) > 1
            """
        )
        assert overlap == [], f"มี active ซ้อน: {overlap}"


# ============================================================
# 6. เลื่อนชั้นแล้ว import — 🔴 เหตุผลที่ต้องมี migration 028
# ============================================================

@pytest.mark.asyncio
async def test_import_after_promotion_does_not_collide_with_old_year_row(
    client, db_pool, admin_user
):
    """ปีเก่ามีแถว (ห้องเดิม, รหัสเดิม) สถานะ `promoted` อยู่แล้ว ⇒ ปีใหม่ import ลงห้องใหม่ได้

    🔴 **นี่คือเทสต์ที่ index เก่าทำให้ล้ม**: `uq_students_room_student_active
       (room_id, student_id)` ไม่มีมิติปี ⇒ มันห้ามคนเดิมมีสองแถว "ห้องเดียวกัน"
       คนละปี ซึ่งเป็นสิ่งที่การเลื่อนชั้นต้องการพอดี ⇒ ถ้า 028 ไม่ทำงาน
       เทสต์นี้จะล้มด้วย UniqueViolation
    """
    uid, username, password = admin_user
    token = login_token(client, username, password)
    current_id = await _current_year_id(db_pool)
    next_id = await _seed_year(db_pool, NEXT_BE)

    # จำลอง "หลัง apply_rollover": แถวปีเก่า = promoted · แถวปีใหม่ = active (ห้องใหม่)
    async with db_pool.acquire() as conn:
        room_old = await conn.fetchval(
            "INSERT INTO rooms (room_code, room_name, level) VALUES ('ม.4/1','ม.4/1','ม.4') RETURNING id"
        )
        room_new = await conn.fetchval(
            "INSERT INTO rooms (room_code, room_name, level) VALUES ('ม.5/1','ม.5/1','ม.5') RETURNING id"
        )
        for year_id, room_id, status in (
            (current_id, room_old, "promoted"),
            (next_id, room_new, "active"),
        ):
            await conn.execute(
                """
                INSERT INTO students
                    (room_id, user_id, student_id, student_no, first_name, last_name,
                     class_role, is_admin, permissions, status, academic_year_id)
                VALUES ($1, $2, '47014', 1, 'เลื่อนชั้น', 'ทดสอบ',
                        'student', FALSE, '[]'::jsonb, $3, $4)
                """,
                room_id, uid, status, year_id,
            )

    # ครูนำเข้ารายชื่อปีใหม่ (ห้อง ม.5/1) — ต้องไม่ UniqueViolation
    job_id = await upload_and_get_job(
        client, token,
        [["47014", "ม.5/1", 1, "นาย", "เลื่อนชั้น", "ทดสอบ", "ใหม่", ""]],
        academic_year_id=next_id,
    )
    result = await import_service.process_import_job(db_pool, job_id)
    assert result["status"] == "COMPLETED", result["errors"]
    assert result["imported"] == 1, result["errors"]

    got = await _student_rows(db_pool, "47014")
    assert len(got) == 2, "upsert ต้องทับแถวปีใหม่ ไม่สร้างแถวที่สาม"

    old = next(r for r in got if r["academic_year_id"] == current_id)
    new = next(r for r in got if r["academic_year_id"] == next_id)
    assert old["status"] == "promoted", "ประวัติปีเก่าต้องไม่ถูกแตะ"
    assert old["deleted_at"] is None
    assert new["status"] == "active"
    assert new["room_code"] == "ม.5/1"

    # 🔍 Deep DB: nickname ถูกทับจากไฟล์ (พิสูจน์ว่า DO UPDATE ลงแถวเดิมจริง)
    async with db_pool.acquire() as conn:
        assert await conn.fetchval(
            "SELECT nickname FROM students WHERE student_id='47014' AND academic_year_id=$1",
            next_id,
        ) == "ใหม่"
        assert await conn.fetchval(
            "SELECT count(*) FROM students WHERE student_id='47014' AND deleted_at IS NULL"
        ) == 2


@pytest.mark.asyncio
async def test_promotion_year_import_does_not_touch_the_old_year_row(
    client, db_pool, admin_user
):
    """แถวปีเก่า (คนละห้อง) ต้องไม่ถูก supersede ทับ — guard ต้องจำกัดที่ปีเดียวกัน

    ถ้า guard ลืมกรอง `academic_year_id` มันจะไป supersede แถวปีเก่าของทุกคน
    ที่เคยอยู่ห้องอื่น ⇒ ประวัติถูกทำลายเงียบ ๆ ตอน import ปีใหม่
    """
    uid, username, password = admin_user
    token = login_token(client, username, password)
    current_id = await _current_year_id(db_pool)
    next_id = await _seed_year(db_pool, NEXT_BE)

    async with db_pool.acquire() as conn:
        room_old = await conn.fetchval(
            "INSERT INTO rooms (room_code, room_name, level) VALUES ('ม.4/3','ม.4/3','ม.4') RETURNING id"
        )
        await conn.execute(
            """
            INSERT INTO students
                (room_id, user_id, student_id, student_no, first_name, last_name,
                 class_role, is_admin, permissions, status, academic_year_id)
            VALUES ($1, $2, '47015', 1, 'ปีเก่า', 'ต้องรอด',
                    'student', FALSE, '[]'::jsonb, 'promoted', $3)
            """,
            room_old, uid, current_id,
        )

    job_id = await upload_and_get_job(
        client, token,
        [["47015", "ม.5/3", 1, "นาย", "ปีใหม่", "ทดสอบ", "", ""]],
        academic_year_id=next_id,
    )
    result = await import_service.process_import_job(db_pool, job_id)
    assert result["status"] == "COMPLETED", result["errors"]

    got = await _student_rows(db_pool, "47015")
    old = next(r for r in got if r["academic_year_id"] == current_id)
    assert old["status"] == "promoted", "แถวปีเก่าต้องเป็น promoted ต่อไป — ไม่ใช่ superseded"
    assert old["room_code"] == "ม.4/3", "ห้องเดิมต้องไม่ถูกแก้"


# ============================================================
# 7. template ต้องประกาศคอลัมน์ปีให้ผู้ใช้เห็น
# ============================================================

@pytest.mark.asyncio
async def test_template_header_includes_year_column(client, db_pool, admin_user):
    """ไฟล์ตัวอย่างที่ระบบให้ดาวน์โหลดต้องมีหัวคอลัมน์ "ปีการศึกษา"

    🔴 ตรวจผ่าน **ไฟล์ที่ดาวน์โหลดจริง** (ไม่ใช่ตัวแปร `KNOWN_COLUMNS`) — ถ้า
       `build_template_xlsx_bytes` หลุดจาก `KNOWN_COLUMNS` วันหนึ่ง ผู้ใช้จะได้
       ไฟล์ที่ไม่มีช่องปี แล้วเทสต์นี้ต้องเป็นตัวบอก ไม่ใช่ให้ครูเจอเอง
    """
    _, username, password = admin_user
    token = login_token(client, username, password)

    res = client.get(
        "/api/import-student-template",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200, res.text

    ws = openpyxl.load_workbook(io.BytesIO(res.content)).active
    header = [c.value for c in ws[1]]
    assert "ปีการศึกษา" in header, f"template ไม่มีคอลัมน์ปี: {header}"
    assert header[-1] == "ปีการศึกษา", "คอลัมน์ปีต้องอยู่ท้ายสุด (ไฟล์เก่ายังใช้ได้)"
    assert header[:8] == OLD_HEADER, "8 คอลัมน์แรกต้องเหมือนเดิมเป๊ะ"


# ============================================================
# 8. งานเก่าที่ค้างในตาราง (job.academic_year_id = NULL)
# ============================================================

@pytest.mark.asyncio
async def test_legacy_job_row_with_null_year_still_processes(client, db_pool, admin_user):
    """job ที่ถูกสร้างก่อน migration 028 (คอลัมน์เป็น NULL) ต้องยังประมวลผลได้

    🔴 เหตุผลที่คอลัมน์นี้ **nullable โดยเจตนา**: ระหว่าง deploy จะมี job ค้าง
       ที่ยังไม่ถูกรัน (status=PENDING) อยู่ในตาราง ⇒ ถ้าบังคับ NOT NULL
       การ ALTER จะล้มกลาง deploy หรือ job เหล่านั้นรันไม่ได้ตลอดไป
    """
    _, username, password = admin_user
    token = login_token(client, username, password)
    current_id = await _current_year_id(db_pool)

    job_id = await upload_and_get_job(client, token, [
        ["47016", "ม.4/1", 1, "นาย", "งานเก่า", "ค้างอยู่", "", ""],
    ])

    # จำลอง job สมัยก่อน 028: ไม่มีปีของตัวเอง
    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE student_import_jobs SET academic_year_id = NULL WHERE id = $1", job_id
        )

    result = await import_service.process_import_job(db_pool, job_id)
    assert result["status"] == "COMPLETED", result["errors"]
    assert result["imported"] == 1, result["errors"]

    rows = await _student_rows(db_pool, "47016")
    assert len(rows) == 1
    assert rows[0]["academic_year_id"] == current_id, "fallback = ปีปัจจุบัน"


# ============================================================
# 9. audit / error_logs ยังทำงานกับมิติปี
# ============================================================

@pytest.mark.asyncio
async def test_year_errors_are_recorded_in_error_logs_jsonb(client, db_pool, admin_user):
    """error จากปีต้องลง `error_logs` (JSONB) พร้อมเลขแถว — ไม่ใช่แค่ log ฝั่ง server"""
    _, username, password = admin_user
    token = login_token(client, username, password)

    job_id = await upload_and_get_job(
        client, token,
        [
            ["47017", "ม.4/1", 1, "นาย", "ปกติ", "ผ่าน", "", "", ""],
            ["47018", "ม.4/1", 2, "นาย", "ปีผิด", "ไม่ผ่าน", "", "", PHANTOM_BE],
        ],
        header=FULL_HEADER,
    )
    await import_service.process_import_job(db_pool, job_id)

    job = await _job_row(db_pool, job_id)
    logs = job["error_logs"]
    if isinstance(logs, str):
        logs = json.loads(logs)
    assert len(logs) == 1, logs
    assert str(PHANTOM_BE) in json.dumps(logs, ensure_ascii=False)
    assert job["skipped_count"] == 1
