"""🎓 ปีการศึกษา (academic_years) — migration 027

ทดสอบ 6 ระดับ:
  1) HTTP — CRUD + auth/permission (401 / 403 / 400)
  2) Deep-DB — ค่าลงตารางจริง + audit_logs ถูกเขียน
  3) **"มีปีปัจจุบันได้ตัวเดียว"** — ทั้งทาง service (สลับ/ลบ) และทาง DB (unique index)
  4) **ด่านกันล็อกโรงเรียน** — ตั้งปีว่างเป็นปีปัจจุบันขณะโรงเรียนมีคน = 400 และ **ไม่มีอะไรถูกแก้**
  5) **`students.academic_year_id` ผูกกับปีจริง** — DEFAULT ชี้ปีปัจจุบัน และเปลี่ยนตาม set-current
     ⚠️ อันนี้คือหัวใจของโมเดล "1 แถว = สมาชิก 1 คน ใน 1 ปี"
  6) **กับดักที่พังง่าย**: ลบปีปัจจุบัน / ลบปีที่ยังมีสมาชิก / กู้คืนปีที่ พ.ศ. ชนกับปีใหม่

ตาม docs/rules/testing.md: ตรวจ DB ตรง ๆ ผ่าน db_pool ไม่เชื่อ HTTP response
"""
import importlib
import random

import asyncpg
import pytest
import pytest_asyncio

from core.config import settings
from services import auth_service, year_service


@pytest_asyncio.fixture
async def year_world(db_pool, client):
    """โลกทดสอบ: ห้องเดียว + 4 บทบาท + "ปีปัจจุบัน" ที่ conftest ปลูกไว้

      - admin      → is_admin=true (ผ่านโดยไม่ดู permissions)
      - president  → council_president ← มี MANAGE_SETTINGS ใน roles.json
      - council    → council_member ← **ไม่มี** MANAGE_SETTINGS (ตัวที่ต้องโดน 403)
      - student    → นักเรียนทั่วไป

    ⚠️ **ไม่ลบ `academic_years` ทิ้ง** (ต่างจาก term_world ที่ลบ academic_terms)
       เพราะ `students.academic_year_id` เป็น NOT NULL DEFAULT <id ของปีปัจจุบัน>
       ⇒ ถ้าลบปีทิ้ง การสร้าง user ในฟิกซ์เจอร์นี้จะ FK violation ทันที
       (และนั่นคือเหตุผลที่ conftest ต้องปลูกปีกลับ — ดู SEED_YEAR_BE ที่นั่น)

    ⚠️ รับ `client` เข้ามาโดยเจตนา — บังคับให้ TestClient เปิด app (รัน init_db + migrations)
       จบก่อน จึงค่อยใช้ตาราง (แบบเดียวกับ term_world / announcement_world)
    """
    room_code = f"ม.5/{random.randint(1, 90)}"
    async with db_pool.acquire() as conn:
        room_id = await conn.fetchval(
            "INSERT INTO rooms (room_code, room_name, level) VALUES ($1,$2,'ม.5') RETURNING id",
            room_code, room_code,
        )

    users = {}
    for label, role in [
        ("admin", "admin"),
        ("president", "council_president"),
        ("council", "council_member"),
        ("student", "student"),
    ]:
        sid = f"YR{random.randint(1000, 9999)}{label[:2]}"  # ≤ 10 ตัว (student_id VARCHAR(10))
        uid = await auth_service.register_user(
            db_pool, sid, "1234", f"{label} ทดสอบ", sid, room_code, 1, role
        )
        users[label] = {
            "user_id": uid,
            "token": auth_service.create_access_token(uid),
        }

    async with db_pool.acquire() as conn:
        current = await conn.fetchrow(
            "SELECT id, year_be FROM academic_years WHERE is_current AND deleted_at IS NULL"
        )
    assert current is not None, "conftest ต้องปลูกปีปัจจุบันไว้เสมอ"

    users["room_id"] = room_id
    users["room_code"] = room_code
    users["year_id"] = current["id"]
    users["year_be"] = current["year_be"]
    return users


def _auth(world, actor="admin") -> dict:
    return {"Authorization": f"Bearer {world[actor]['token']}"}


# ปี พ.ศ. ที่ไม่ชนกับ SEED_YEAR_BE (2569) — ใช้ค่าคงที่เพื่อให้เทสต์อ่านออก
_NEXT_BE = 2570
_OLD_BE = 2568


def _create(client, world, actor="admin", **overrides):
    payload = {"year_be": _NEXT_BE}
    payload.update(overrides)
    return client.post("/api/settings/years", json=payload, headers=_auth(world, actor))


async def _year_rows(db_pool, year_id=None):
    """อ่านค่าดิบจากตาราง (deep-DB)"""
    async with db_pool.acquire() as conn:
        if year_id is not None:
            return await conn.fetch("SELECT * FROM academic_years WHERE id = $1", year_id)
        return await conn.fetch("SELECT * FROM academic_years ORDER BY id")


async def _current_flags(db_pool) -> dict:
    """{id: is_current} ของแถวที่ยังไม่ถูกลบ"""
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, is_current FROM academic_years WHERE deleted_at IS NULL"
        )
    return {r["id"]: r["is_current"] for r in rows}


async def _audit_actions(db_pool, year_id: int):
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT action FROM audit_logs
            WHERE entity_type = 'academic_year' AND entity_id = $1
            ORDER BY created_at
            """,
            str(year_id),
        )
    return [r["action"] for r in rows]


async def _column_default(db_pool) -> str:
    """ค่า DEFAULT ปัจจุบันของ `students.academic_year_id` (ข้อความดิบจาก pg_attrdef)"""
    async with db_pool.acquire() as conn:
        return await conn.fetchval(
            """
            SELECT pg_get_expr(d.adbin, d.adrelid)
            FROM pg_attrdef d
            JOIN pg_attribute a ON a.attrelid = d.adrelid AND a.attnum = d.adnum
            WHERE d.adrelid = 'students'::regclass AND a.attname = 'academic_year_id'
            """
        )


async def _give_member(db_pool, room_id: int, year_id: int) -> int:
    """ใส่สมาชิก 1 แถวลงปีที่ระบุ (คืน `students.id`) — สร้างสภาพ "ปีนี้มีคนแล้ว"

    ⚠️ **`student_id`/`student_no` ต้องเป็น NULL โดยเจตนา** — คัดลอกค่ามาด้วยจะชน
       `uq_students_room_student_active (room_id, student_id) WHERE deleted_at IS NULL`
       เพราะแถวต้นทางอยู่ในห้องเดียวกัน
       ⇒ นี่คือกับดักของ index เดิมที่ migration 028 จะมาแก้ (คนเดิมต้องมีได้หลายแถว
         ในห้องเดิมเมื่อคนละปี) — ระหว่างนี้เทสต์จึงต้องสร้างแถวที่ไม่ชน
    """
    async with db_pool.acquire() as conn:
        return await conn.fetchval(
            """
            INSERT INTO students (room_id, user_id, class_role, status, academic_year_id)
            SELECT s.room_id, s.user_id, 'student', 'active', $2
            FROM students s
            WHERE s.room_id = $1 AND s.deleted_at IS NULL
            ORDER BY s.id LIMIT 1
            RETURNING id
            """,
            room_id, year_id,
        )


# ===================== 1) สร้าง + deep-DB =====================

@pytest.mark.asyncio
async def test_create_year_writes_row(client, year_world, db_pool):
    """สร้างปี → 201 + แถวลง DB จริง + ไม่เป็นปีปัจจุบันโดยค่าเริ่มต้น"""
    res = _create(client, year_world, year_be=_NEXT_BE, name="ปีการศึกษา 2570")
    assert res.status_code == 201, res.text
    year_id = res.json()["id"]

    rows = await _year_rows(db_pool, year_id)
    assert len(rows) == 1
    assert rows[0]["year_be"] == _NEXT_BE
    assert rows[0]["name"] == "ปีการศึกษา 2570"
    assert rows[0]["is_current"] is False, "ค่าเริ่มต้นต้องไม่ใช่ปีปัจจุบัน"
    assert rows[0]["deleted_at"] is None


@pytest.mark.asyncio
async def test_create_without_name_defaults_from_year_be(client, year_world, db_pool):
    """ไม่ส่ง `name` → ใช้ "ปีการศึกษา {year_be}" (ครูไม่ต้องพิมพ์ชื่อยาว ๆ ทุกครั้ง)"""
    res = _create(client, year_world, year_be=_NEXT_BE)
    assert res.status_code == 201, res.text
    assert res.json()["name"] == f"ปีการศึกษา {_NEXT_BE}"
    assert (await _year_rows(db_pool, res.json()["id"]))[0]["name"] == f"ปีการศึกษา {_NEXT_BE}"


@pytest.mark.asyncio
async def test_dates_optional_and_range_checked(client, year_world, db_pool):
    """ปีที่ไม่รู้วันเปิดเทอมสร้างได้ (วันที่ไม่บังคับ) — แต่ถ้าส่งมา end ต้องไม่ก่อน start"""
    ok = _create(client, year_world, year_be=_NEXT_BE)
    assert ok.status_code == 201, ok.text
    row = (await _year_rows(db_pool, ok.json()["id"]))[0]
    assert row["start_date"] is None and row["end_date"] is None

    bad = _create(
        client, year_world, year_be=_OLD_BE,
        start_date="2027-05-16", end_date="2027-03-01",
    )
    assert bad.status_code == 400, bad.text
    assert "วันสิ้นสุด" in bad.json()["detail"]


@pytest.mark.asyncio
async def test_create_writes_audit_log(client, year_world, db_pool):
    """ทุก mutation ต้องมี audit log (กฎ backend.md) — ตรวจถึง DB"""
    res = _create(client, year_world, year_be=_NEXT_BE)
    assert await _audit_actions(db_pool, res.json()["id"]) == ["CREATE_ACADEMIC_YEAR"]


@pytest.mark.asyncio
async def test_duplicate_year_be_400_not_500(client, year_world, db_pool):
    """`year_be` ซ้ำ (กับปีที่ยังไม่ถูกลบ) → 400 ไทย ไม่ใช่ 500 จาก unique index"""
    first = _create(client, year_world, year_be=_NEXT_BE)
    assert first.status_code == 201

    dup = _create(client, year_world, year_be=_NEXT_BE)
    assert dup.status_code == 400, dup.text
    assert str(_NEXT_BE) in dup.json()["detail"]

    # ของเดิมยังอยู่ ไม่มีแถวที่สอง
    assert len(await _year_rows(db_pool, first.json()["id"])) == 1


# ===================== 2) "มีปีปัจจุบันได้ตัวเดียว" =====================

@pytest.mark.asyncio
async def test_seed_year_is_current(client, year_world, db_pool):
    """หลัง clean_database ต้องมีปีปัจจุบันหนึ่งปีพอดี (invariant ที่เทสต์อื่นพึ่ง)"""
    flags = await _current_flags(db_pool)
    assert sum(flags.values()) == 1
    assert flags[year_world["year_id"]] is True


@pytest.mark.asyncio
async def test_unique_index_blocks_second_current_bypassing_service(
    client, year_world, db_pool
):
    """⚠️ ยิงตรง ๆ ที่ DB (ข้าม service) ตั้ง is_current=TRUE สองแถว → UniqueViolationError

    ตัวนี้พิสูจน์ว่า "มีปีปัจจุบันได้ตัวเดียว" บังคับที่ DB จริง ไม่ใช่แค่ในโค้ด service
    (ถ้า index ถูกสร้างผิด เช่นไม่มี `WHERE is_current` ก็จะไม่กันอะไรเลย)
    """
    new_id = _create(client, year_world, year_be=_NEXT_BE).json()["id"]

    async with db_pool.acquire() as conn:
        with pytest.raises(asyncpg.UniqueViolationError):
            await conn.execute(
                "UPDATE academic_years SET is_current = TRUE WHERE id = $1", new_id
            )

    flags = await _current_flags(db_pool)
    assert flags[year_world["year_id"]] is True and flags[new_id] is False


@pytest.mark.asyncio
async def test_set_current_switches_from_old(client, year_world, db_pool):
    """set-current บนปีที่มีสมาชิกแล้ว → สลับจากปีเดิม (deep-DB) + เขียน audit"""
    new_id = _create(client, year_world, year_be=_NEXT_BE).json()["id"]
    await _give_member(db_pool, year_world["room_id"], new_id)

    res = client.post(
        f"/api/settings/years/{new_id}/set-current", headers=_auth(year_world)
    )
    assert res.status_code == 200, res.text

    flags = await _current_flags(db_pool)
    assert sum(flags.values()) == 1, f"ต้องมีปีปัจจุบันตัวเดียว แต่ได้ {flags}"
    assert flags[new_id] is True and flags[year_world["year_id"]] is False

    assert "SET_CURRENT_YEAR" in await _audit_actions(db_pool, new_id)


@pytest.mark.asyncio
async def test_set_current_flips_students_default(client, year_world, db_pool):
    """🔑 ตั้งปีใหม่เป็นปัจจุบัน → DEFAULT ของ `students.academic_year_id` ต้องชี้ปีใหม่

    นี่คือสิ่งที่ทำให้ "สมาชิกที่สร้างหลังจากนี้ไปอยู่ปีใหม่" จริง — ถ้าลืม ALTER DEFAULT
    การลงทะเบียนใหม่ทั้งหมดจะยังไปลงปีเก่าเงียบ ๆ (และจะดูเหมือนระบบทำงานปกติ)
    """
    new_id = _create(client, year_world, year_be=_NEXT_BE).json()["id"]
    assert await _column_default(db_pool) == str(year_world["year_id"])

    await _give_member(db_pool, year_world["room_id"], new_id)
    res = client.post(
        f"/api/settings/years/{new_id}/set-current", headers=_auth(year_world)
    )
    assert res.status_code == 200, res.text

    assert await _column_default(db_pool) == str(new_id)

    # พิสูจน์ปลายทางจริง: insert โดยไม่ระบุปี → ไปลงปีใหม่
    async with db_pool.acquire() as conn:
        landed = await conn.fetchval(
            """
            INSERT INTO students (room_id, class_role, status)
            VALUES ($1, 'student', 'active') RETURNING academic_year_id
            """,
            year_world["room_id"],
        )
    assert landed == new_id


@pytest.mark.asyncio
async def test_set_current_twice_does_not_touch_timestamp(client, year_world, db_pool):
    """กด set-current ซ้ำบนปีที่เป็นปัจจุบันอยู่ → 200 และ **ไม่ทับ updated_at**"""
    year_id = year_world["year_id"]
    before = (await _year_rows(db_pool, year_id))[0]["updated_at"]

    res = client.post(
        f"/api/settings/years/{year_id}/set-current", headers=_auth(year_world)
    )
    assert res.status_code == 200, res.text

    after = (await _year_rows(db_pool, year_id))[0]["updated_at"]
    assert after == before, "กดซ้ำต้องไม่ทับ timestamp เดิม (กัน audit หลอก)"
    assert sum((await _current_flags(db_pool)).values()) == 1


# ===================== 3) ด่านกันล็อกโรงเรียน =====================

@pytest.mark.asyncio
async def test_cannot_set_empty_year_current_while_school_has_members(
    client, year_world, db_pool
):
    """⚠️ ด่านที่แพงที่สุด: ตั้งปีที่ยังไม่มีใครอยู่เป็นปัจจุบัน ขณะที่ปีอื่นยังมีสมาชิก active

    ถ้าหลุด ด่านนี้จะทำให้ **รายชื่อทั้งโรงเรียนหายในคลิกเดียว** (ทุกคิวรีกรองด้วยปีปัจจุบัน)
    ⇒ ต้องได้ 400 และ **ปีปัจจุบันเดิมต้องไม่ถูกแตะเลย** (รวม DEFAULT ของ students)
    """
    empty_id = _create(client, year_world, year_be=_NEXT_BE).json()["id"]
    assert await _year_rows(db_pool, empty_id) is not None
    default_before = await _column_default(db_pool)

    res = client.post(
        f"/api/settings/years/{empty_id}/set-current", headers=_auth(year_world)
    )
    assert res.status_code == 400, res.text
    assert "ยังไม่มีสมาชิก" in res.json()["detail"]

    flags = await _current_flags(db_pool)
    assert flags[year_world["year_id"]] is True, "ปีปัจจุบันเดิมต้องยังเป็นปัจจุบัน"
    assert flags[empty_id] is False
    assert await _column_default(db_pool) == default_before, "DEFAULT ต้องไม่ถูกแตะ"


@pytest.mark.asyncio
async def test_cannot_create_empty_year_as_current_while_school_has_members(
    client, year_world, db_pool
):
    """เส้นทาง `create_year(is_current=True)` ต้องผ่านด่านเดียวกัน — และต้องไม่สร้างแถวเลย"""
    res = _create(client, year_world, year_be=_NEXT_BE, is_current=True)
    assert res.status_code == 400, res.text

    async with db_pool.acquire() as conn:
        created = await conn.fetchval(
            "SELECT COUNT(*) FROM academic_years WHERE year_be = $1", _NEXT_BE
        )
    assert created == 0, "คำขอที่ถูกปฏิเสธต้องไม่ทิ้งแถวค้าง (transaction ต้อง rollback)"


@pytest.mark.asyncio
async def test_school_without_members_has_no_admin_at_all(client, year_world, db_pool):
    """🔑 โรงเรียนที่ไม่มีแถวใน `students` เลย = **ไม่มีใครเป็นแอดมินได้** → 403

    เพราะสิทธิ์ทั้งหมดอ่านจาก `students.permissions` (snapshot ตอนแต่งตั้ง) ไม่ใช่จาก `users`
    ⇒ นี่คือเหตุผลที่ด่าน "ปีปัจจุบันต้องมีคน" ของ P4 (rollover guard) จำเป็นจริง ๆ
       การ flip ทุกแถวออกจาก active โดยไม่สร้างแถวใหม่ให้ส่วนกลาง = ล็อกโรงเรียนถาวร
    """
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM students")

    res = _create(client, year_world, year_be=_NEXT_BE)
    assert res.status_code == 403, res.text
    assert "ไม่พบข้อมูลของคุณ" in res.json()["detail"]


@pytest.mark.asyncio
async def test_create_current_allowed_when_school_is_empty(
    client, year_world, db_pool, monkeypatch
):
    """โรงเรียนยังไม่มีสมาชิก active เลย → ตั้งปีแรกเป็นปัจจุบันได้ (สถานะติดตั้งใหม่)

    ⚠️ **ต้องปลอมเป็น `SUPER_ADMIN_ID` ถึงจะไปถึงด่านนี้ได้** — ทาง HTTP ปกติ แอดมินเองก็ต้อง
       มีแถว active ใน `students` (ไม่งั้น 403 ตามเทสต์ด้านบน) ⇒ "ที่อื่นไม่มีใคร active"
       จึงเป็นจริงได้เฉพาะเส้นทาง super admin เท่านั้น · ถ้าลบเทสต์นี้ กิ่งนั้นจะไม่ถูกตรวจเลย

    ⚠️ ต้องลบสมาชิก **แบบ hard** ที่นี่ (ต่างจากกฎ soft delete ของโดเมน) เพราะสิ่งที่ทดสอบ
       คือ "ไม่มีแถวอยู่เลย" ไม่ใช่ "ถูกซ่อนไว้" — และเป็นข้อมูลที่เทสต์สร้างเอง
    """
    monkeypatch.setattr(settings, "SUPER_ADMIN_ID", year_world["admin"]["user_id"])

    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM students")
        await conn.execute("DELETE FROM academic_years")

    res = _create(client, year_world, year_be=_NEXT_BE, is_current=True)
    assert res.status_code == 201, res.text
    assert res.json()["is_current"] is True

    flags = await _current_flags(db_pool)
    assert flags == {res.json()["id"]: True}


# ===================== 4) ลบ / กู้คืน (กับดักตัวจริง) =====================

@pytest.mark.asyncio
async def test_cannot_delete_current_year(client, year_world, db_pool):
    """ลบปีปัจจุบัน → 400 + บอกทางออก และแถวต้องยังไม่ถูกลบ"""
    res = client.delete(
        f"/api/settings/years/{year_world['year_id']}", headers=_auth(year_world)
    )
    assert res.status_code == 400, res.text
    assert "ปีปัจจุบัน" in res.json()["detail"]
    assert (await _year_rows(db_pool, year_world["year_id"]))[0]["deleted_at"] is None


@pytest.mark.asyncio
async def test_cannot_delete_year_with_members(client, year_world, db_pool):
    """ลบปีที่ยังมีสมาชิก → 400 + บอกจำนวนคน (soft delete ปีทิ้งจะทำให้เด็กหายจากทุกคิวรี)"""
    year_id = _create(client, year_world, year_be=_NEXT_BE).json()["id"]
    await _give_member(db_pool, year_world["room_id"], year_id)

    res = client.delete(f"/api/settings/years/{year_id}", headers=_auth(year_world))
    assert res.status_code == 400, res.text
    assert "สมาชิก" in res.json()["detail"]
    assert (await _year_rows(db_pool, year_id))[0]["deleted_at"] is None


@pytest.mark.asyncio
async def test_delete_empty_year_then_restore(client, year_world, db_pool):
    """ปีว่างที่ยังไม่เคยใช้ → ลบได้ (soft delete) แล้วกู้คืนได้ (กลับมาเป็นปีธรรมดา)"""
    year_id = _create(client, year_world, year_be=_NEXT_BE).json()["id"]

    assert client.delete(
        f"/api/settings/years/{year_id}", headers=_auth(year_world)
    ).status_code == 200

    row = (await _year_rows(db_pool, year_id))[0]
    assert row["deleted_at"] is not None, "deep-DB: ต้องเป็น soft delete"
    assert row["is_current"] is False

    res = client.post(
        f"/api/settings/years/{year_id}/restore", headers=_auth(year_world)
    )
    assert res.status_code == 200, res.text
    row = (await _year_rows(db_pool, year_id))[0]
    assert row["deleted_at"] is None
    assert row["is_current"] is False, "กู้คืนมาเป็นปีธรรมดา ต้องกดตั้งปัจจุบันเอง"

    actions = await _audit_actions(db_pool, year_id)
    assert actions == ["CREATE_ACADEMIC_YEAR", "DELETE_ACADEMIC_YEAR", "RESTORE_ACADEMIC_YEAR"]


@pytest.mark.asyncio
async def test_delete_frees_the_year_be_for_reuse(client, year_world, db_pool):
    """ลบปีว่างแล้วสร้าง พ.ศ. เดิมซ้ำได้ — พิสูจน์ว่า unique index เป็น partial จริง"""
    first = _create(client, year_world, year_be=_NEXT_BE).json()["id"]
    client.delete(f"/api/settings/years/{first}", headers=_auth(year_world))

    again = _create(client, year_world, year_be=_NEXT_BE)
    assert again.status_code == 201, again.text
    assert again.json()["id"] != first


@pytest.mark.asyncio
async def test_restore_conflicting_year_be_400(client, year_world, db_pool):
    """⚠️ กับดัก: ลบปี 2570 → สร้างปี 2570 ใหม่ → กู้คืนตัวเก่า = ชน unique index

    ต้องได้ 400 พร้อมข้อความที่อ่านรู้เรื่อง ไม่ใช่ 500 จาก IntegrityError
    """
    old = _create(client, year_world, year_be=_NEXT_BE).json()["id"]
    client.delete(f"/api/settings/years/{old}", headers=_auth(year_world))
    _create(client, year_world, year_be=_NEXT_BE)

    res = client.post(
        f"/api/settings/years/{old}/restore", headers=_auth(year_world)
    )
    assert res.status_code == 400, res.text
    assert str(_NEXT_BE) in res.json()["detail"]

    row = (await _year_rows(db_pool, old))[0]
    assert row["deleted_at"] is not None, "กู้คืนที่ไม่สำเร็จต้องไม่แก้แถวเลย"


@pytest.mark.asyncio
async def test_restore_not_deleted_404(client, year_world):
    """กู้คืนแถวที่ไม่ได้ถูกลบ → 404 (ไม่ใช่ 200 เงียบ ๆ)"""
    year_id = _create(client, year_world, year_be=_NEXT_BE).json()["id"]
    res = client.post(
        f"/api/settings/years/{year_id}/restore", headers=_auth(year_world)
    )
    assert res.status_code == 404, res.text


# ===================== 5) PATCH =====================

@pytest.mark.asyncio
async def test_patch_is_partial_and_writes_audit(client, year_world, db_pool):
    """ส่งแค่ name → พ.ศ./วันที่ต้องไม่ถูกแตะ"""
    year_id = _create(
        client, year_world, year_be=_NEXT_BE, start_date="2027-05-16", end_date="2028-03-31"
    ).json()["id"]

    res = client.patch(
        f"/api/settings/years/{year_id}",
        json={"name": "ปีการศึกษา 2570 (แก้ชื่อ)"},
        headers=_auth(year_world),
    )
    assert res.status_code == 200, res.text

    row = (await _year_rows(db_pool, year_id))[0]
    assert row["name"] == "ปีการศึกษา 2570 (แก้ชื่อ)"
    assert row["year_be"] == _NEXT_BE
    assert str(row["start_date"]) == "2027-05-16"
    assert "UPDATE_ACADEMIC_YEAR" in await _audit_actions(db_pool, year_id)


@pytest.mark.asyncio
async def test_patch_can_fix_typo_year_be(client, year_world, db_pool):
    """แก้ พ.ศ. ที่พิมพ์ผิดได้ (ข้อกำหนดเจ้าของระบบ: "ถ้าข้อมูลผิด ต้องแก้ไขได้")"""
    year_id = _create(client, year_world, year_be=_NEXT_BE).json()["id"]

    res = client.patch(
        f"/api/settings/years/{year_id}",
        json={"year_be": 2571},
        headers=_auth(year_world),
    )
    assert res.status_code == 200, res.text
    assert (await _year_rows(db_pool, year_id))[0]["year_be"] == 2571


@pytest.mark.asyncio
async def test_patch_year_be_conflict_400(client, year_world, db_pool):
    """แก้ พ.ศ. ไปชนปีที่มีอยู่แล้ว → 400 และค่าเดิมต้องไม่ถูกแก้"""
    a = _create(client, year_world, year_be=_NEXT_BE).json()["id"]
    _create(client, year_world, year_be=2571)

    res = client.patch(
        f"/api/settings/years/{a}", json={"year_be": 2571}, headers=_auth(year_world)
    )
    assert res.status_code == 400, res.text
    assert (await _year_rows(db_pool, a))[0]["year_be"] == _NEXT_BE


@pytest.mark.asyncio
async def test_patch_can_clear_dates(client, year_world, db_pool):
    """⚠️ ต่างจาก terms: ส่ง `null` ในวันที่ = "ล้างวันที่" **ทำได้จริง**

    เพราะสองคอลัมน์นี้ nullable และ "ปีนี้ยังไม่รู้วันเปิดเทอม" เป็นคำขอที่มีความหมาย
    """
    year_id = _create(
        client, year_world, year_be=_NEXT_BE, start_date="2027-05-16", end_date="2028-03-31"
    ).json()["id"]

    res = client.patch(
        f"/api/settings/years/{year_id}",
        json={"start_date": None, "end_date": None},
        headers=_auth(year_world),
    )
    assert res.status_code == 200, res.text

    row = (await _year_rows(db_pool, year_id))[0]
    assert row["start_date"] is None and row["end_date"] is None


@pytest.mark.asyncio
async def test_patch_start_after_existing_end_400(client, year_world, db_pool):
    """PATCH ส่งมาวันเดียว → ต้องเทียบกับ end_date ที่เก็บอยู่จริง (ไม่ใช่กับ None)"""
    year_id = _create(
        client, year_world, year_be=_NEXT_BE, start_date="2027-05-16", end_date="2028-03-31"
    ).json()["id"]

    res = client.patch(
        f"/api/settings/years/{year_id}",
        json={"start_date": "2029-01-01"},
        headers=_auth(year_world),
    )
    assert res.status_code == 400, res.text
    assert str((await _year_rows(db_pool, year_id))[0]["start_date"]) == "2027-05-16"


@pytest.mark.asyncio
async def test_patch_cannot_set_is_current(client, year_world, db_pool):
    """⚠️ ส่ง is_current ผ่าน PATCH ต้องไม่มีผล — ต้องใช้ set-current เท่านั้น

    (ถ้าหลุดเข้ามาได้ = มีสองทางเปลี่ยนปีปัจจุบัน ทางหนึ่งไม่ล้างตัวเก่า/ไม่ผ่านด่านปีว่าง → index พัง)
    """
    year_id = _create(client, year_world, year_be=_NEXT_BE).json()["id"]
    res = client.patch(
        f"/api/settings/years/{year_id}",
        json={"is_current": True},
        headers=_auth(year_world),
    )
    assert res.status_code == 400, res.text
    assert (await _year_rows(db_pool, year_id))[0]["is_current"] is False
    assert sum((await _current_flags(db_pool)).values()) == 1


# ⚠️ `null` ที่ส่งมาชัด ๆ ในฟิลด์ NOT NULL ⇒ ต้องได้ 400 ไม่ใช่ 500
#    (`exclude_unset` ไม่กรองให้ เพราะการส่ง `null` มา = ฟิลด์ถูก "set" แล้ว)
@pytest.mark.parametrize("field", ["year_be", "name"])
@pytest.mark.asyncio
async def test_patch_explicit_null_400(client, year_world, db_pool, field):
    """ส่ง `{field: null}` → 400 พร้อมบอกชื่อฟิลด์ และ**แถวต้องไม่ถูกแตะเลย**"""
    year_id = _create(client, year_world, year_be=_NEXT_BE).json()["id"]
    before = dict((await _year_rows(db_pool, year_id))[0])

    res = client.patch(
        f"/api/settings/years/{year_id}", json={field: None}, headers=_auth(year_world)
    )
    assert res.status_code == 400, f"ต้องเป็น 400 ไม่ใช่ {res.status_code}: {res.text}"
    assert field in res.json()["detail"], "ข้อความต้องบอกว่าฟิลด์ไหน"

    after = dict((await _year_rows(db_pool, year_id))[0])
    assert after == before, "ห้ามแก้ค่าจริง"


@pytest.mark.asyncio
async def test_patch_deleted_year_404(client, year_world):
    """แก้ปีที่ถูกลบ → 404 (ต้องกู้คืนก่อน กันแก้ประวัติเงียบ ๆ)"""
    year_id = _create(client, year_world, year_be=_NEXT_BE).json()["id"]
    client.delete(f"/api/settings/years/{year_id}", headers=_auth(year_world))

    res = client.patch(
        f"/api/settings/years/{year_id}", json={"name": "แอบแก้"}, headers=_auth(year_world)
    )
    assert res.status_code == 404, res.text


@pytest.mark.parametrize("payload", [
    {"year_be": 1000},           # ต่ำกว่าเขตที่รับ (2400)
    {"year_be": 2900},           # สูงเกิน
    {"year_be": 2569.5},         # เศษทศนิยม — Pydantic v2 ปฏิเสธ float ที่มีเศษสำหรับ int
    {"name": "   "},             # ช่องว่างล้วน → ผ่าน min_length แต่ validator ปฏิเสธ (และขาด year_be)
    {"year_be": "สองหกเก้า"},     # สตริงที่ไม่ใช่ตัวเลข
])
@pytest.mark.asyncio
async def test_create_invalid_payload_422(client, year_world, payload):
    """ค่าที่ผิดรูปต้องถูกปฏิเสธที่ชั้น model (422) ไม่หลุดไปถึง SQL (500)"""
    res = client.post(
        "/api/settings/years", json=payload, headers=_auth(year_world)
    )
    assert res.status_code == 422, res.text


# ===================== 6) รายการ =====================

@pytest.mark.asyncio
async def test_list_status_filter_and_order(client, year_world):
    """status=active/current/deleted กรองถูก + ปีปัจจุบันขึ้นก่อน + ใหม่สุดก่อน"""
    cur = year_world["year_id"]
    new = _create(client, year_world, year_be=_NEXT_BE).json()["id"]
    old = _create(client, year_world, year_be=_OLD_BE).json()["id"]
    client.delete(f"/api/settings/years/{old}", headers=_auth(year_world))

    active = client.get(
        "/api/settings/years?status=active", headers=_auth(year_world)
    ).json()
    assert active["total"] == 2
    ids = [i["id"] for i in active["items"]]
    assert ids[0] == cur, "ปีปัจจุบันต้องขึ้นก่อน"
    assert ids == [cur, new], f"ที่เหลือเรียงใหม่สุดก่อน แต่ได้ {ids}"

    current = client.get(
        "/api/settings/years?status=current", headers=_auth(year_world)
    ).json()
    assert current["total"] == 1 and current["items"][0]["id"] == cur

    deleted = client.get(
        "/api/settings/years?status=deleted", headers=_auth(year_world)
    ).json()
    assert deleted["total"] == 1 and deleted["items"][0]["id"] == old


@pytest.mark.asyncio
async def test_list_member_count_excludes_deleted_rows(client, year_world, db_pool):
    """`member_count` นับแถวที่ยังไม่ถูกลบ **ทุกสถานะ** (ไม่ใช่แค่ active)

    ปีที่ผ่านมาแล้วต้องยังโชว์จำนวนจริงได้ — ไม่ใช่ 0 เพราะเด็กถูก flip เป็น promoted
    """
    year_id = _create(client, year_world, year_be=_NEXT_BE).json()["id"]
    member = await _give_member(db_pool, year_world["room_id"], year_id)
    assert member is not None

    # flip เป็น 'promoted' (สถานะของปีที่ผ่านไปแล้ว) — ต้องยังถูกนับ
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE students SET status = 'promoted' WHERE id = $1", member)

    items = client.get("/api/settings/years?status=active", headers=_auth(year_world)).json()["items"]
    by_id = {i["id"]: i for i in items}
    assert by_id[year_id]["member_count"] == 1

    # ลบแบบ soft → ต้องหลุดจากการนับ
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE students SET deleted_at = NOW() WHERE id = $1", member)
    items = client.get("/api/settings/years?status=active", headers=_auth(year_world)).json()["items"]
    assert {i["id"]: i for i in items}[year_id]["member_count"] == 0


@pytest.mark.asyncio
async def test_list_rejects_unknown_status(client, year_world):
    """status นอกลิสต์ → 422 ที่ชั้น Query pattern (ไม่หลุดถึง SQL)"""
    res = client.get("/api/settings/years?status=banana", headers=_auth(year_world))
    assert res.status_code == 422, res.text


# ----- GET /years/{id} — หน้า "แก้ไข" แบบเต็มหน้าโหลดเองจาก URL -----

@pytest.mark.asyncio
async def test_get_year_returns_row_with_member_count(client, year_world, db_pool):
    """อ่านปีเดี่ยวได้ พร้อม `member_count` ชุดเดียวกับที่รายการใช้

    ⚠️ ทำไมต้องมี endpoint นี้: ฟอร์มปีการศึกษาเป็น **หน้าเต็ม** ⇒ เปิด `/settings/years/:id/edit`
       แล้วกด F5 ต้องได้ข้อมูลครบ · ถ้าดึงจากลิสต์แทน จะพังกับปีที่อยู่นอกหน้าปัจจุบัน
       หรืออยู่นอกตัวกรอง (เช่นเปิด URL ของปีที่ถูกลบ)
    """
    year_id = _create(client, year_world, year_be=_NEXT_BE, name="ปีหน้า").json()["id"]
    member = await _give_member(db_pool, year_world["room_id"], year_id)
    assert member is not None

    res = client.get(f"/api/settings/years/{year_id}", headers=_auth(year_world))
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["id"] == year_id
    assert body["year_be"] == _NEXT_BE
    assert body["name"] == "ปีหน้า"
    assert body["is_current"] is False
    assert body["deleted_at"] is None
    assert body["member_count"] == 1


@pytest.mark.asyncio
async def test_get_year_returns_soft_deleted_row(client, year_world, db_pool):
    """🔴 ปีที่ถูกลบ **ยังอ่านได้** (ต่างจาก `list status=active`) — ให้ UI บอกได้ว่า
    "ปีนี้ถูกลบแล้ว กู้คืนก่อน" แทนที่จะเป็น 404 ที่อ่านไม่ออก

    ตัวด่านจริงอยู่ที่ PATCH/DELETE ⇒ การอ่านแถวที่ถูกลบไม่เปิดช่องให้แก้ประวัติ
    """
    year_id = _create(client, year_world, year_be=_NEXT_BE).json()["id"]
    assert client.delete(
        f"/api/settings/years/{year_id}", headers=_auth(year_world)
    ).status_code == 200

    res = client.get(f"/api/settings/years/{year_id}", headers=_auth(year_world))
    assert res.status_code == 200, res.text
    assert res.json()["deleted_at"] is not None

    # ...แต่ PATCH ต้องยังปฏิเสธ (พิสูจน์ว่าการอ่านที่ผ่อนคลายไม่ทำให้แก้ได้)
    patch = client.patch(
        f"/api/settings/years/{year_id}", json={"name": "แก้ปีที่ลบ"}, headers=_auth(year_world)
    )
    assert patch.status_code == 404, patch.text


@pytest.mark.asyncio
async def test_get_year_not_found_404(client, year_world):
    res = client.get("/api/settings/years/99999999", headers=_auth(year_world))
    assert res.status_code == 404, res.text


# ===================== 7) สิทธิ์ + auth =====================

@pytest.mark.asyncio
async def test_council_member_forbidden(client, year_world):
    """council_member ไม่มี MANAGE_SETTINGS → 403 ทุก endpoint (รวม GET)"""
    assert client.get(
        "/api/settings/years", headers=_auth(year_world, "council")
    ).status_code == 403
    # รายตัวก็ต้องโดนด้วย — ไม่งั้นหน้าแก้ไขแบบเต็มหน้าจะรั่วข้อมูลให้คนที่ไม่มีสิทธิ์
    assert client.get(
        f"/api/settings/years/{year_world['year_id']}", headers=_auth(year_world, "council")
    ).status_code == 403
    assert _create(client, year_world, actor="council").status_code == 403
    assert client.post(
        f"/api/settings/years/{year_world['year_id']}/set-current",
        headers=_auth(year_world, "council"),
    ).status_code == 403


@pytest.mark.asyncio
async def test_teacher_role_cannot_touch_years(client, year_world, db_pool):
    """⚠️ ครูทั่วไปมี `MANAGE_STUDENTS` แต่ **ต้องไม่มี** `MANAGE_SETTINGS` → 403

    นี่คือเหตุผลที่เลือกใช้ MANAGE_SETTINGS ไม่ใช่ MANAGE_STUDENTS:
    การเปลี่ยนปีปัจจุบันกระทบทั้งโรงเรียน ⇒ ครูระดับชั้นต้องแตะไม่ได้ (ข้อ 7 ของแผน)
    """
    sid = f"TC{random.randint(1000, 9999)}"
    uid = await auth_service.register_user(
        db_pool, sid, "1234", "ครู ทดสอบ", sid, year_world["room_code"], 1, "teacher"
    )
    headers = {"Authorization": f"Bearer {auth_service.create_access_token(uid)}"}

    assert client.get("/api/settings/years", headers=headers).status_code == 403
    assert client.post(
        "/api/settings/years", json={"year_be": _NEXT_BE}, headers=headers
    ).status_code == 403


@pytest.mark.asyncio
async def test_council_president_allowed(client, year_world):
    """council_president มี MANAGE_SETTINGS อยู่แล้ว → ผ่านโดยไม่ต้อง backfill สิทธิ์"""
    res = _create(client, year_world, actor="president", year_be=_NEXT_BE)
    assert res.status_code == 201, res.text
    assert client.get(
        "/api/settings/years", headers=_auth(year_world, "president")
    ).status_code == 200


@pytest.mark.asyncio
async def test_requires_login_api_key_401(client, year_world):
    """X-API-Key (system RPC) → user_id เป็น None → ต้อง 401 ไม่ใช่ 500"""
    headers = {"X-API-Key": "test-api-key"}
    assert client.get("/api/settings/years", headers=headers).status_code == 401
    assert client.post(
        "/api/settings/years", json={"year_be": _NEXT_BE}, headers=headers
    ).status_code == 401


# ===================== 8) helper ที่ service อื่นจะใช้ =====================

@pytest.mark.asyncio
async def test_get_current_year_returns_row(client, year_world, db_pool):
    """`get_current_year()` คืน id/year_be/name/dates ของปีปัจจุบัน"""
    year = await year_service.get_current_year(db_pool)
    assert year is not None
    assert year["id"] == year_world["year_id"]
    assert year["year_be"] == year_world["year_be"]
    assert year["name"] == f"ปีการศึกษา {year_world['year_be']}"
    assert await year_service.get_current_year_id(db_pool) == year_world["year_id"]


@pytest.mark.asyncio
async def test_get_current_year_ignores_deleted(client, year_world, db_pool):
    """ปีที่ถูกลบต้องไม่ถูกมองเป็นปีปัจจุบัน (ยิงตรงที่ DB เพื่อข้ามด่านห้ามลบปีปัจจุบัน)"""
    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE academic_years SET deleted_at = NOW(), is_current = FALSE WHERE id = $1",
            year_world["year_id"],
        )
    assert await year_service.get_current_year(db_pool) is None
    assert await year_service.get_current_year_id(db_pool) is None


# ===================== 9) migration 027 =====================

@pytest.mark.asyncio
async def test_conftest_seed_keeps_student_default_valid(client, year_world, db_pool):
    """🔑 ผู้คุมกัน conftest: หลัง TRUNCATE + ปลูกปีกลับ **ต้อง insert student ได้โดยไม่ระบุปี**

    ถ้า `clean_database` ลืม ALTER DEFAULT (หรือปลูกปีไม่สำเร็จ) ทุกเทสต์ที่สร้าง user
    จะล้มด้วย FK violation — เทสต์นี้ทำให้ความล้มนั้นอ่านออกทันทีว่ามาจากไหน
    """
    async with db_pool.acquire() as conn:
        landed = await conn.fetchval(
            """
            INSERT INTO students (room_id, class_role, status)
            VALUES ($1, 'student', 'active') RETURNING academic_year_id
            """,
            year_world["room_id"],
        )
        exists = await conn.fetchval(
            "SELECT EXISTS (SELECT 1 FROM academic_years WHERE id = $1)", landed
        )
    assert exists is True, "DEFAULT ที่ค้างอยู่ต้องชี้ปีที่มีจริง"


@pytest.mark.asyncio
async def test_migration_027_is_idempotent_and_complete(year_world, db_pool):
    """จำลอง DB เก่าที่ยังไม่มีปีการศึกษา → รัน upgrade() ตรง ๆ → ต้องได้ครบทุกอย่างคืน

    ⚠️ รันท้ายไฟล์โดยเจตนา เพราะมัน DROP ของจริงทิ้งแล้วสร้างใหม่
       (แบบเดียวกับ test_migration_017_creates_table_and_indexes)

    ⚠️ ลบให้ **ครบทั้งสามที่** — ไม่ใช่แค่ DROP TABLE CASCADE:
       `CASCADE` จะลบ constraint บน `rollover_runs` ทิ้งด้วย แต่ **ไม่ลบตาราง**
       ⇒ พอรัน upgrade() อีกครั้ง `CREATE TABLE IF NOT EXISTS rollover_runs` เป็น no-op
       ⇒ FK หายถาวรโดยไม่มีใครรู้ ⇒ ลบตาราง rollover_runs เองด้วยเพื่อให้สร้างใหม่ครบ
    """
    year_world
    mig = importlib.import_module("migrations.027_academic_years")

    async with db_pool.acquire() as conn:
        await conn.execute("DROP TABLE IF EXISTS rollover_runs CASCADE")
        await conn.execute("ALTER TABLE students DROP COLUMN IF EXISTS academic_year_id CASCADE")
        await conn.execute("ALTER TABLE academic_terms DROP COLUMN IF EXISTS academic_year_id CASCADE")
        await conn.execute("DROP TABLE IF EXISTS academic_years CASCADE")

        assert await conn.fetchval("SELECT to_regclass('public.academic_years') IS NULL") is True
        assert await conn.fetchval("SELECT to_regclass('public.rollover_runs') IS NULL") is True

        await mig.upgrade(conn)
        await mig.upgrade(conn)  # idempotent — รันซ้ำต้องไม่ error

        # 1) ตารางเกิดจริง
        assert await conn.fetchval(
            "SELECT to_regclass('public.academic_years') IS NOT NULL"
        ) is True
        assert await conn.fetchval(
            "SELECT to_regclass('public.rollover_runs') IS NOT NULL"
        ) is True

        # 2) seed ปีตั้งต้น + เป็น current
        seeded = await conn.fetchrow(
            "SELECT id, year_be, name FROM academic_years WHERE is_current AND deleted_at IS NULL"
        )
        assert seeded is not None, "ต้องมีปีปัจจุบัน (ไม่งั้น DEFAULT ของ students จะไม่มีปลายทาง)"
        assert 2400 < seeded["year_be"] < 2700

        # 3) index ครบ (รวมตัวที่ init_db สร้างในบล็อก index — ต้องเป็นชื่อเดียวกัน ไม่ซ้ำ)
        idx = {
            r["indexname"]
            for r in await conn.fetch(
                "SELECT indexname FROM pg_indexes "
                "WHERE tablename IN ('academic_years','rollover_runs','students')"
            )
        }
        for name in (
            "uq_academic_years_single_current",
            "uq_academic_years_year_be",
            "idx_rollover_runs_from_to",
            "idx_students_year_room",
        ):
            assert name in idx, f"ขาด index {name}"

        # 4) คอลัมน์กลับมา + NOT NULL + DEFAULT ชี้ปีปัจจุบัน (ทั้ง 2 ตาราง)
        for table in ("students", "academic_terms"):
            assert await conn.fetchval(
                """
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = $1 AND column_name = 'academic_year_id'
                )
                """,
                table,
            ) is True, f"{table} ต้องมี academic_year_id"

        assert await conn.fetchval(
            """
            SELECT is_nullable FROM information_schema.columns
            WHERE table_name = 'students' AND column_name = 'academic_year_id'
            """
        ) == "NO", "students.academic_year_id ต้องเป็น NOT NULL"

        # 5) FK ของ rollover_runs กลับมาจริง (ข้อที่ CASCADE ทำหายได้)
        fks = {
            r["conname"]
            for r in await conn.fetch(
                """
                SELECT conname FROM pg_constraint
                WHERE conrelid = 'rollover_runs'::regclass AND contype = 'f'
                """
            )
        }
        assert len(fks) == 3, f"rollover_runs ต้องมี FK 3 ตัว (from/to year + created_by) แต่ได้ {fks}"

        # 6) ใช้งานได้จริงหลัง migrate
        await conn.execute(
            """
            INSERT INTO rollover_runs (from_year_id, to_year_id, status)
            VALUES ($1, $1, 'PREVIEWED')
            """,
            seeded["id"],
        )
        await conn.execute("DELETE FROM rollover_runs")
