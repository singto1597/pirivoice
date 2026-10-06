"""📖 เส้นทาง "อ่าน" ที่ต้องรู้จักปีการศึกษา — P2 ของงานเลื่อนชั้นทั้งโรงเรียน

**ทำไมแยกไฟล์จาก `test_academic_years.py`:**
  ที่นั่นทดสอบ *ตัวปี* (CRUD / invariant "ปีปัจจุบันมีได้ตัวเดียว" / สิทธิ์)
  ที่นี่ทดสอบ *ผลของปีต่อคิวรีเดิม* — ซึ่งเป็นที่ที่บั๊กจะโผล่ **เงียบ ๆ** หลังโรงเรียน
  ขึ้นปีใหม่ เพราะคิวรีเหล่านั้นถูกเขียนไว้ตอนที่สัจพจน์คือ "1 คน = 1 แถว"

🔴 **กับดักที่ไฟล์นี้กันไว้:** หลังมีปี (migration 027) คนหนึ่งมีได้หลายแถว **ในห้องเดียวกัน**
   (แถวปีเก่า `status='promoted'` + แถวปีใหม่ `status='active'`) ⇒ `fetchrow` ที่ไม่มี
   `ORDER BY` จะหยิบตามลำดับที่ planner คืน ซึ่งมักเป็น **แถวที่ insert ก่อน = ปีเก่า**
   ⇒ ผู้ใช้ที่ active จริงโดน 403 · ยอด dashboard บวมขึ้นทุกปี · audit log ชี้ห้องที่จากมาแล้ว

⚠️ **ทำไมต้อง `_promoted` ก่อน `_active` เสมอในเทสต์นี้:** เพราะ seq scan คืนแถวตามลำดับ
   ที่อยู่ในหน้า heap = ลำดับ insert ⇒ **แถวที่แทรกก่อนจะมี id ต่ำกว่าและถูกหยิบก่อน**
   ถ้าแทรกแถว active ก่อน เทสต์จะผ่านทั้งที่ยังไม่ได้แก้ `ORDER BY` = เทสต์ที่โกหก
   (พิสูจน์แล้ว: เทสต์นี้ล้มจริงเมื่อถอด `ORDER BY` ออกจาก `core/rbac.require_permission`)

⚠️ **ข้อจำกัดที่ยังเหลืออยู่จนกว่า migration 028 (P3):** unique index ปัจจุบันคือ
   `uq_students_room_student_active (room_id, student_id)` **ไม่มีปี** ⇒ ยังสร้างสองแถว
   ที่มี `student_id` **ตรงกัน** ในห้องเดียวกันไม่ได้ ⇒ เทสต์นี้จึงใช้ `student_id` ต่างกัน
   ทั้งที่ของจริงหลังเลื่อนชั้นคือ **รหัสเดิมทั้งสองปี** · 028 จะปลดข้อจำกัดนั้น
   (นี่คือเหตุผลที่ 028 ต้องออก **ก่อน** P4 — ถ้าไม่ ตัว apply จะ insert แถวปีใหม่ไม่ได้เลย)

ตาม docs/rules/testing.md: ตรวจ DB ตรง ๆ ผ่าน db_pool ไม่เชื่อ HTTP response
"""
import random

import pytest
import pytest_asyncio

from core.exceptions import ForbiddenError
from core.logger import AuditLogger
from core.rbac import require_permission
from services import auth_service, dashboard_service, student_service

# ปีใหม่ที่จะสร้างขึ้นในเทสต์ (conftest ปลูกปี SEED_YEAR_BE = 2569 ไว้เป็น "ปีเก่า")
_NEW_BE = 2570


@pytest_asyncio.fixture
async def read_world(db_pool, client):
    """ห้องเดียว + ปีเก่า (ของ conftest) + ปีปัจจุบัน (สร้างใหม่) + คนหนึ่งคน

    🔴 **ทำไมต้องสร้างปีใหม่แล้วลดปีของ conftest ลง — ไม่ใช่แค่ INSERT ปีเก่าเพิ่ม:**
       `_resolve_room_id` (และที่อื่น) เรียงด้วย `academic_year_id DESC` ⇒ เรียงตาม **id**
       ซึ่งเท่ากับเรียงตาม **ลำดับเวลาที่สร้าง** เพราะ rollover **ต่อท้ายปีใหม่เสมอ**
       ⇒ ถ้าเทสต์สร้าง "ปีเก่า" ทีหลัง (id สูงกว่า) จะได้โลกที่ **เป็นไปไม่ได้จริง**
          แล้วเทสต์จะล้มด้วยเหตุผลปลอม (ของจริง: id ของปีเก่า < ปีใหม่ เสมอ)
       ⇒ fixture นี้จึงจำลองสภาพ **"เพิ่งกดเลื่อนชั้นเสร็จ"** ตาม `apply_rollover` ขั้น 5:
          ปีใหม่เป็น current · ปีเดิมเป็นปีเก่า · **DEFAULT ของคอลัมน์ชี้ปีใหม่**
          (ขั้น 5 ของ apply ทำ `ALTER COLUMN ... SET DEFAULT <new id>` — ทำให้ที่นี่ด้วย
           ไม่งั้นแถวที่ insert โดยไม่ระบุปีจะตกไปอยู่ปีเก่า ซึ่งไม่ตรงกับสภาพหลัง rollover)

    ⚠️ รับ `client` โดยเจตนา — บังคับให้ TestClient เปิด app (รัน init_db + migrations)
       จบก่อน จึงค่อยแตะตาราง (แบบเดียวกับ year_world / term_world)
    """
    room_code = f"ม.3/{random.randint(1, 90)}"
    async with db_pool.acquire() as conn:
        room_id = await conn.fetchval(
            "INSERT INTO rooms (room_code, room_name, level) VALUES ($1,$2,'ม.3') RETURNING id",
            room_code, room_code,
        )
        # ปีของ conftest = ปีเก่า · ต้องปลด is_current ก่อน (uq_academic_years_single_current)
        old_id = await conn.fetchval(
            "SELECT id FROM academic_years WHERE is_current AND deleted_at IS NULL"
        )
        assert old_id is not None, "conftest ต้องปลูกปีปัจจุบันไว้เสมอ"
        await conn.execute(
            "UPDATE academic_years SET is_current = FALSE WHERE id = $1", old_id
        )
        current_id = await conn.fetchval(
            """
            INSERT INTO academic_years (year_be, name, is_current)
            VALUES ($1, $2, TRUE) RETURNING id
            """,
            _NEW_BE, f"ปีการศึกษา {_NEW_BE}",
        )
        # DDL ไม่รับ parameter ⇒ ต้อง interpolate (ใช้ int() กันฉีด — แบบเดียวกับ conftest)
        await conn.execute(
            f"ALTER TABLE students ALTER COLUMN academic_year_id SET DEFAULT {int(current_id)}"
        )
    assert current_id > old_id, "ปีใหม่ต้องมี id สูงกว่าปีเก่า (rollover ต่อท้ายเสมอ)"

    sid = f"RP{random.randint(1000, 9999)}"
    user_id = await auth_service.register_user(
        db_pool, sid, "1234", "ผู้ทดสอบ ระบบอ่าน", sid, room_code, 1, "council_member"
    )

    # 🔴 **ลบแถวสมาชิกที่ `register_user` สร้างให้ทิ้งไป — ห้ามลบ 3 บรรทัดนี้**
    #    `register_user` สร้างทั้ง user **และ** แถว `students` ของปีปัจจุบันให้เสมอ
    #    ⇒ ถ้าปล่อยไว้ ทุกเทสต์จะเริ่มด้วย "แถว active ปีปัจจุบัน 1 แถว" ซึ่งทำลาย 3 เทสต์:
    #      · "มีแต่แถว promoted ต้องโดน 403"     → มีแถว active อยู่แล้ว ⇒ ไม่โดน = เทสต์หลอก
    #      · "แถว active ไม่มีสิทธิ์ ต้องโดน 403" → แถวนั้นมีสิทธิ์ ⇒ ผ่าน = เทสต์หลอก
    #      · "_resolve_room_id เลือกปีใหม่"       → เสมอด้วยปีเดียวกัน ⇒ ผลขึ้นกับ planner (flaky)
    #    ⇒ ให้ fixture คืน "user เปล่า" แล้ว **แต่ละเทสต์สร้างแถวที่ตัวเองต้องการ** เท่านั้น
    #    (ใช้ soft delete ตามกติกา repo — และ `require_permission`/`list_students` กรอง `deleted_at` อยู่แล้ว)
    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE students SET deleted_at = NOW() WHERE user_id = $1", user_id
        )

    return {
        "room_id": room_id,
        "room_code": room_code,
        "old_year_id": old_id,
        "current_year_id": current_id,
        "user_id": user_id,
    }


async def _add_row(
    db_pool, world, *, year_id, status, student_id, room_id=None, class_role="council_member"
):
    """แทรกแถวสมาชิกตรง ๆ (ไม่ผ่าน service) เพื่อจำลองสภาพ 'หลังเลื่อนชั้น' ได้แม่น

    ⚠️ ลำดับการเรียกสำคัญ — ดูหัวไฟล์ (`_promoted` ต้องมาก่อน `_active`)
    """
    async with db_pool.acquire() as conn:
        return await conn.fetchval(
            """
            INSERT INTO students
                (room_id, user_id, student_id, student_no, first_name, last_name,
                 class_role, is_admin, permissions, status, academic_year_id)
            VALUES ($1, $2, $3, 1, 'ทดสอบ', 'อ่าน',
                    $4, FALSE, '["MANAGE_STUDENTS"]'::jsonb, $5, $6)
            RETURNING id
            """,
            room_id if room_id is not None else world["room_id"],
            world["user_id"], student_id, class_role, status, year_id,
        )


# ============================================================
# 1. 🔴 หัวใจของ P2 — require_permission ต้องหยิบแถว active
# ============================================================

@pytest.mark.asyncio
async def test_require_permission_picks_active_row_when_promoted_row_is_older(db_pool, read_world):
    """แถวปีเก่า (`promoted`) แทรกก่อน + แถวปีใหม่ (`active`) แทรกทีหลัง **ห้องเดียวกัน**

    ⇒ ต้องผ่าน — ถ้าไม่มี `ORDER BY` ใน `require_permission` แถว promoted (id ต่ำกว่า)
      จะถูกหยิบก่อน แล้วผู้ใช้ที่ active จริงจะโดน 403
    """
    w = read_world
    await _add_row(
        db_pool, w, year_id=w["old_year_id"], status="promoted", student_id="OLD0001"
    )
    await _add_row(
        db_pool, w, year_id=w["current_year_id"], status="active", student_id="NEW0001"
    )

    async with db_pool.acquire() as conn:
        # ต้องไม่ raise
        assert await require_permission(conn, w["room_id"], w["user_id"], "MANAGE_STUDENTS")


@pytest.mark.asyncio
async def test_require_permission_picks_active_row_regardless_of_insert_order(db_pool, read_world):
    """ทิศกลับกัน — แถว active แทรกก่อน แล้วค่อย promoted ⇒ ต้องได้ผลเหมือนกัน

    ⚠️ เทสต์คู่นี้กัน "แก้แล้วผ่านเพราะบังเอิญ" — การเรียงต้องมาจาก `ORDER BY`
       ไม่ใช่จากลำดับที่ข้อมูลบังเอิญอยู่
    """
    w = read_world
    await _add_row(
        db_pool, w, year_id=w["current_year_id"], status="active", student_id="NEW0002"
    )
    await _add_row(
        db_pool, w, year_id=w["old_year_id"], status="promoted", student_id="OLD0002"
    )

    async with db_pool.acquire() as conn:
        assert await require_permission(conn, w["room_id"], w["user_id"], "MANAGE_STUDENTS")


@pytest.mark.asyncio
async def test_require_permission_still_denies_when_only_promoted_row_exists(db_pool, read_world):
    """🔒 การแก้ `ORDER BY` ต้อง **ไม่เปิดรู** — คนที่มีแต่แถวปีเก่ายังต้องโดน 403

    (คือเด็กที่จบ/ย้ายออกแล้ว และไม่มีแถวในปีปัจจุบัน — ต้องแตะห้องนั้นไม่ได้)
    """
    w = read_world
    await _add_row(
        db_pool, w, year_id=w["old_year_id"], status="promoted", student_id="OLD0003"
    )

    async with db_pool.acquire() as conn:
        with pytest.raises(ForbiddenError):
            await require_permission(conn, w["room_id"], w["user_id"], "MANAGE_STUDENTS")


@pytest.mark.asyncio
async def test_require_permission_denies_when_permission_missing_on_active_row(db_pool, read_world):
    """🔒 แถว active ต้องเป็นตัวตัดสินจริง ๆ — ไม่ใช่แค่ 'มีแถว active ก็ผ่าน'

    แถวปีเก่ามีสิทธิ์ แต่แถวปีใหม่ (active) ไม่มี ⇒ ต้อง 403
    """
    w = read_world
    await _add_row(
        db_pool, w, year_id=w["old_year_id"], status="promoted", student_id="OLD0004"
    )
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO students
                (room_id, user_id, student_id, student_no, first_name, last_name,
                 class_role, is_admin, permissions, status, academic_year_id)
            VALUES ($1, $2, 'NEW0004', 1, 'ทดสอบ', 'อ่าน',
                    'student', FALSE, '[]'::jsonb, 'active', $3)
            """,
            w["room_id"], w["user_id"], w["current_year_id"],
        )
        with pytest.raises(ForbiddenError):
            await require_permission(conn, w["room_id"], w["user_id"], "MANAGE_STUDENTS")


# ============================================================
# 2. list_students — รายชื่อต้องไม่บวมด้วยแถวของปีเก่า
# ============================================================

@pytest.mark.asyncio
async def test_list_students_defaults_to_current_year(db_pool, read_world):
    """ไม่ระบุปี → ได้เฉพาะสมาชิกของ **ปีปัจจุบัน** (ไม่ลากแถวปีเก่ามาด้วย)"""
    w = read_world
    await _add_row(
        db_pool, w, year_id=w["old_year_id"], status="promoted", student_id="OLD0010"
    )
    await _add_row(
        db_pool, w, year_id=w["current_year_id"], status="active", student_id="NEW0010"
    )

    rows = await student_service.list_students(db_pool, room_id=w["room_id"])
    sids = [r["student_id"] for r in rows]
    assert "NEW0010" in sids
    assert "OLD0010" not in sids, "แถวของปีเก่าต้องไม่โผล่ในรายชื่อปีปัจจุบัน"


@pytest.mark.asyncio
async def test_list_students_can_read_a_past_year(db_pool, read_world):
    """🌟 ระบุ `year_id` ของปีเก่า → ต้องเห็นแถวของปีนั้น (ประวัติต้องดูย้อนหลังได้)"""
    w = read_world
    await _add_row(
        db_pool, w, year_id=w["old_year_id"], status="promoted", student_id="OLD0011"
    )
    await _add_row(
        db_pool, w, year_id=w["current_year_id"], status="active", student_id="NEW0011"
    )

    rows = await student_service.list_students(db_pool, room_id=w["room_id"], year_id=w["old_year_id"])
    sids = [r["student_id"] for r in rows]
    assert "OLD0011" in sids
    assert "NEW0011" not in sids


@pytest.mark.asyncio
async def test_list_students_keeps_non_active_statuses_of_the_same_year(db_pool, read_world):
    """🔴 ตัวกรองคือ **ปี** ไม่ใช่ **สถานะ** โดยเจตนา

    เพราะมี UI "รออนุมัติ" ที่ต้องเห็นแถว `pending` ⇒ ถ้ากรอง `status='active'`
    เด็กที่รออนุมัติจะหายจากรายชื่อทั้งที่ควรเห็น
    """
    w = read_world
    await _add_row(
        db_pool, w, year_id=w["current_year_id"], status="pending", student_id="PEND01"
    )

    rows = await student_service.list_students(db_pool, room_id=w["room_id"])
    assert "PEND01" in [r["student_id"] for r in rows]


# ============================================================
# 3. dashboard — ยอดต้องไม่บวมขึ้นทุกปี
# ============================================================

@pytest.mark.asyncio
async def test_count_people_does_not_double_count_old_years(db_pool, read_world):
    """เพิ่มแถวปีเก่าเข้าไป → ยอดรวมต้อง **เท่าเดิม** (ไม่นับคนเดียวกันสองรอบ)"""
    w = read_world
    async with db_pool.acquire() as conn:
        scope = {"scope": "all", "level": None, "is_admin": True}
        before, _ = await dashboard_service._count_people(conn, scope)

        await _add_row(
            db_pool, w, year_id=w["old_year_id"], status="promoted", student_id="OLD0020"
        )
        after, _ = await dashboard_service._count_people(conn, scope)

    assert after == before, f"ยอดบวมเพราะนับแถวปีเก่า ({before} → {after})"


@pytest.mark.asyncio
async def test_count_people_increases_when_a_current_year_row_is_added(db_pool, read_world):
    """เทียบเคียง — แถวของ **ปีปัจจุบัน** ต้องถูกนับ (พิสูจน์ว่าตัวกรองไม่ได้ปิดทิ้งหมด)"""
    w = read_world
    async with db_pool.acquire() as conn:
        scope = {"scope": "all", "level": None, "is_admin": True}
        before, _ = await dashboard_service._count_people(conn, scope)
        await _add_row(
            db_pool, w, year_id=w["current_year_id"], status="active", student_id="NEW0020"
        )
        after, _ = await dashboard_service._count_people(conn, scope)

    assert after == before + 1


# ============================================================
# 4. audit log — ต้องไม่ชี้ห้องที่ผู้ใช้จากมาแล้ว
# ============================================================

@pytest.mark.asyncio
async def test_resolve_room_prefers_the_newest_year(db_pool, read_world):
    """คนที่ย้ายระดับชั้น (ปีเก่าห้อง A → ปีใหม่ห้อง B) → audit ต้องบันทึก **ห้อง B**

    ⚠️ ถ้าไม่มี `ORDER BY year DESC` จะได้ห้อง A (แถวที่แทรกก่อน) ⇒ ประวัติการใช้งาน
       ชี้ผิดห้อง ซึ่งอ่านแล้วดูสมเหตุสมผล — บั๊กชนิดที่ไม่มีใครจับได้จากหน้าจอ
    """
    w = read_world
    # ห้องใหม่ (คนละห้อง) สำหรับปีปัจจุบัน
    async with db_pool.acquire() as conn:
        new_room_id = await conn.fetchval(
            "INSERT INTO rooms (room_code, room_name, level) VALUES ($1,$2,'ม.4') RETURNING id",
            f"ม.4/{random.randint(1, 90)}", "ห้องปีใหม่",
        )

    await _add_row(
        db_pool, w, year_id=w["old_year_id"], status="promoted",
        student_id="OLD0030", room_id=w["room_id"],
    )
    await _add_row(
        db_pool, w, year_id=w["current_year_id"], status="active",
        student_id="NEW0030", room_id=new_room_id,
    )

    async with db_pool.acquire() as conn:
        resolved = await AuditLogger("test")._resolve_room_id(conn, w["user_id"])

    assert resolved == new_room_id, "audit ต้องชี้ห้องของปีปัจจุบัน ไม่ใช่ห้องปีเก่า"
