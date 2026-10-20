"""🔎 P6 — ค้นชื่อข้ามปี (ข้อตัดสินใจ #8: "เด็กจบ/ย้ายออกต้องค้นชื่อเจอ")

พฤติกรรมเดิม (P2): `list_students` ไม่ระบุปี = **ปีปัจจุบันเสมอ** ⇒ เด็กจบหายจากการค้น
⇒ P6 เพิ่ม `all_years=true` ซึ่ง **ต้องมาพร้อม `search`** (ไม่มีคำค้น = 400) เพราะการไม่กรองปี
   โดยไม่มีคำค้นคือการดัมป์รายชื่อทุกปีของทั้งโรงเรียน

เทสต์ชุดนี้พิสูจน์:
  1) ค้นปกติ (ปีปัจจุบัน) **ไม่เห็น** เด็กที่จบแล้ว
  2) ระบุปีเก่า → เห็นเด็กปีนั้น
  3) `all_years=true` + คำค้น → เห็นทั้งสองปี
  4) `all_years=true` ไม่มีคำค้น → 400 (ไม่ใช่ดัมป์ทั้งโรงเรียน)
  5) ขอบเขตระดับชั้นยังบังคับกับเส้นทางข้ามปี (ครูเห็นแค่ระดับตัวเอง)
"""
import random

import pytest
import pytest_asyncio

from services import auth_service, year_service


@pytest_asyncio.fixture
async def cy_world(db_pool, client):
    level = "ม.5"
    room_code = f"{level}/{random.randint(1, 90)}"
    other_level = "ม.2"
    other_room_code = f"{other_level}/{random.randint(1, 90)}"
    async with db_pool.acquire() as conn:
        #⚠️ `$1, $1` ทำให้ asyncpg สรุปชนิดไม่ได้ (varchar vs text) ⇒ ต้องส่งค่าแยกพารามิเตอร์
        await conn.execute(
            "INSERT INTO rooms (room_code, room_name, level) VALUES ($1, $2, $3)",
            room_code, room_code, level,
        )
        await conn.execute(
            "INSERT INTO rooms (room_code, room_name, level) VALUES ($1, $2, $3)",
            other_room_code, other_room_code, other_level,
        )

    admin_sid = f"CA{random.randint(1000, 9999)}"
    admin_id = await auth_service.register_user(
        db_pool, admin_sid, "1234", "ผู้ดูแล ทดสอบ", admin_sid, room_code, 1, "admin"
    )
    old_year = await year_service.create_year(db_pool, admin_id, year_be=2568)

    # เด็กปัจจุบัน (ปีที่ seeded = 2569)
    cur_sid = f"CUR{random.randint(100, 999)}"
    await auth_service.register_user(
        db_pool, cur_sid, "1234", "เด็กปัจจุบัน", cur_sid, room_code, 2
    )

    # เด็กที่จบไปแล้ว — สมัครในปีปัจจุบันแล้วย้ายแถวไปปีเก่า + ปิดสถานะ (จำลองผลของ rollover)
    # ⚠️ อยู่ **ม.2** โดยเจตนา — ให้ครู ม.5 ด้านล่างพิสูจน์ว่า all_years ไม่ขยายขอบเขตระดับชั้น
    old_sid = f"OLD{random.randint(100, 999)}"
    old_uid = await auth_service.register_user(
        db_pool, old_sid, "1234", "เด็กจบแล้ว", old_sid, other_room_code, 3
    )
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE students
            SET academic_year_id = $1, status = 'graduated'
            WHERE user_id = $2
            """,
            old_year["id"], old_uid,
        )

    # ครูระดับ ม.5 — ใช้ตรวจว่า all_years ไม่ใช่ช่องข้ามระดับชั้น
    teacher_sid = f"CT{random.randint(1000, 9999)}"
    teacher_id = await auth_service.register_user(
        db_pool, teacher_sid, "1234", "ครู ทดสอบ", teacher_sid, other_room_code, 1, "teacher"
    )
    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE students SET staff_level = $1 WHERE user_id = $2",
            level, teacher_id,
        )

    return {
        "admin_token": auth_service.create_access_token(admin_id),
        "teacher_token": auth_service.create_access_token(teacher_id),
        "old_year_id": old_year["id"],
        "cur_sid": cur_sid,
        "old_sid": old_sid,
    }


def _ids(res) -> set[str]:
    assert res.status_code == 200, res.text
    return {s["student_id"] for s in res.json()}


def _get(client, world, token_key="admin_token", **params):
    return client.get(
        "/api/students", params=params, headers={"Authorization": f"Bearer {world[token_key]}"}
    )


@pytest.mark.asyncio
async def test_default_search_is_current_year_only(cy_world, client):
    """ค้นแบบเดิมต้องไม่คืนเด็กที่จบแล้ว — พฤติกรรม P2 ต้องไม่ถอยหลัง"""
    assert _ids(_get(client, cy_world, search=cy_world["cur_sid"])) == {cy_world["cur_sid"]}
    assert _ids(_get(client, cy_world, search=cy_world["old_sid"])) == set()


@pytest.mark.asyncio
async def test_search_past_year_explicitly(cy_world, client):
    res = _get(client, cy_world, search=cy_world["old_sid"], year_id=cy_world["old_year_id"])
    assert _ids(res) == {cy_world["old_sid"]}


@pytest.mark.asyncio
async def test_all_years_finds_graduated_student(cy_world, client):
    """หัวใจของข้อตัดสินใจ #8 — ค้นข้ามปีต้องเจอ"""
    res = _get(client, cy_world, search=cy_world["old_sid"], all_years=True)
    assert _ids(res) == {cy_world["old_sid"]}


@pytest.mark.asyncio
async def test_all_years_without_search_is_400(cy_world, client):
    """ไม่มีคำค้น = ห้ามดัมป์ทุกปี"""
    res = _get(client, cy_world, all_years=True)
    assert res.status_code == 400, res.text
    assert "คำค้น" in res.json()["detail"]

    # ช่องว่างล้วนก็ไม่ผ่าน
    assert _get(client, cy_world, all_years=True, search="   ").status_code == 400


@pytest.mark.asyncio
async def test_all_years_still_respects_level_scope(cy_world, client):
    """ครู ม.5 ค้นข้ามปีได้ แต่ต้องไม่เห็นเด็ก ม.2 ที่ย้ายไปปีเก่า

    ⇒ all_years เป็นการขยาย "แกนเวลา" ไม่ใช่การขยาย "ขอบเขตสิทธิ์"
    """
    # เด็ก ม.2 (ระดับของครูเอง) ที่จบไปแล้ว — ครูต้องเจอ
    res = _get(
        client, cy_world, token_key="teacher_token",
        search=cy_world["old_sid"], all_years=True,
    )
    assert res.status_code == 200, res.text
    assert _ids(res) == set()  # เด็กจบอยู่ ม.2 — ครู ม.5 ต้องไม่เห็น แม้ค้นข้ามปี
