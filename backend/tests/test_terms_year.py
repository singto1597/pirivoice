"""📅 P6 — ผูกภาคเรียนเข้าปีการศึกษา (`academic_terms.academic_year_id`)

คอลัมน์นี้มีตั้งแต่ migration 027 (nullable โดยเจตนา) แต่ P6 คือเฟสที่ **เปิดใช้ทาง API/UI**
⇒ เทสต์ชุดนี้พิสูจน์ว่า:

  1) สร้างภาคพร้อมปี → ค่าลงตารางจริง (deep-DB) และตอบกลับมามีปี
  2) ปีที่ไม่มี/ถูกลบ → **400 พร้อมข้อความไทย** ไม่ใช่ 500 จาก FK violation
  3) `GET /terms?year_id=` กรองได้จริง และนับ `total` ตรงกับ items
  4) PATCH ผูกปี / **ล้างปีด้วย `null`** (ความหมายเดียวที่ `null` ถูกต้องใน PATCH นี้)
  5) PATCH `null` ในคอลัมน์ NOT NULL ยัง **ถูกปฏิเสธ 400** (regression ของ `_NOT_NULL_COLUMNS`)
  6) ไม่ผูกปีก็ยังสร้างได้ — ภาคเก่าก่อนมีฟีเจอร์นี้ต้องไม่พัง (backward compatible)

ตาม docs/rules/testing.md: ตรวจ DB ตรง ๆ ผ่าน db_pool ไม่เชื่อ HTTP response
"""
import random

import pytest
import pytest_asyncio

from services import auth_service, year_service


@pytest_asyncio.fixture
async def ty_world(db_pool, client):
    """ห้องเดียว + ผู้ดูแล (admin) + ปีการศึกษา 2 ปี

    ⚠️ รับ `client` เพื่อบังคับให้ app/init_db รันจบก่อนล้างข้อมูล (แบบเดียวกับ term_world)
    """
    room_code = f"ม.5/{random.randint(1, 90)}"
    async with db_pool.acquire() as conn:
        # ⚠️ ส่งค่าแยกพารามิเตอร์ — `$1, $1` ทำให้ asyncpg สรุปชนิดไม่ได้
        #    (room_code เป็น varchar · room_name เป็น text) ⇒ AmbiguousParameterError
        await conn.execute(
            "INSERT INTO rooms (room_code, room_name, level) VALUES ($1, $2, 'ม.5')",
            room_code, room_code,
        )

    sid = f"TY{random.randint(1000, 9999)}"
    admin_id = await auth_service.register_user(
        db_pool, sid, "1234", "ผู้ดูแล ทดสอบ", sid, room_code, 1, "admin"
    )

    # seeded current year = 2569 (conftest) ⇒ ปีเก่า 2568 ปลอดภัย
    old_year = await year_service.create_year(db_pool, admin_id, year_be=2568)

    async with db_pool.acquire() as conn:
        current_id = await conn.fetchval(
            "SELECT id FROM academic_years WHERE is_current AND deleted_at IS NULL LIMIT 1"
        )
        await conn.execute("DELETE FROM academic_terms")

    return {
        "admin_id": admin_id,
        "token": auth_service.create_access_token(admin_id),
        "old_year_id": old_year["id"],
        "current_year_id": current_id,
    }


def _auth(world) -> dict:
    return {"Authorization": f"Bearer {world['token']}"}


def _create(client, world, **overrides):
    payload = {
        "name": "ภาคเรียนที่ 1/2568",
        "start_date": "2026-05-16",
        "end_date": "2026-10-10",
    }
    payload.update(overrides)
    return client.post("/api/settings/terms", json=payload, headers=_auth(world))


async def _year_of(db_pool, term_id: int):
    async with db_pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT academic_year_id FROM academic_terms WHERE id = $1", term_id
        )


# ============================================================
# 1) สร้างพร้อมปี — ลง DB จริง + ตอบกลับครบ
# ============================================================
@pytest.mark.asyncio
async def test_create_term_with_year_persists_and_returns_it(ty_world, client, db_pool):
    res = _create(client, ty_world, academic_year_id=ty_world["old_year_id"])
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["academic_year_id"] == ty_world["old_year_id"]

    # deep-DB: ไม่เชื่อ response
    assert await _year_of(db_pool, body["id"]) == ty_world["old_year_id"]

    async with db_pool.acquire() as conn:
        audit = await conn.fetchrow(
            """
            SELECT new_values FROM audit_logs
            WHERE action = 'CREATE_ACADEMIC_TERM' AND entity_id = $1
            """,
            str(body["id"]),
        )
    assert audit is not None
    assert str(ty_world["old_year_id"]) in audit["new_values"]


@pytest.mark.asyncio
async def test_create_term_without_year_still_works(ty_world, client, db_pool):
    """ภาคเก่า/โรงเรียนที่ยังไม่สนใจปี ต้องสร้างได้เหมือนเดิม"""
    res = _create(client, ty_world)
    assert res.status_code == 201, res.text
    assert res.json()["academic_year_id"] is None
    assert await _year_of(db_pool, res.json()["id"]) is None


@pytest.mark.asyncio
async def test_create_term_with_unknown_year_is_400(ty_world, client):
    """FK มีจริงที่ DB แต่ผู้ใช้ต้องได้ 400 อ่านรู้เรื่อง ไม่ใช่ 500"""
    res = _create(client, ty_world, academic_year_id=999_999_999)
    assert res.status_code == 400, res.text
    assert "ปีการศึกษา" in res.json()["detail"]


@pytest.mark.asyncio
async def test_create_term_with_deleted_year_is_400(ty_world, client, db_pool):
    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE academic_years SET deleted_at = NOW() WHERE id = $1",
            ty_world["old_year_id"],
        )
    res = _create(client, ty_world, academic_year_id=ty_world["old_year_id"])
    assert res.status_code == 400, res.text


# ============================================================
# 2) ตัวกรองปีในรายการ
# ============================================================
@pytest.mark.asyncio
async def test_list_terms_filters_by_year(ty_world, client):
    in_year = _create(client, ty_world, name="ภาค 1/2568", academic_year_id=ty_world["old_year_id"])
    no_year = _create(client, ty_world, name="ภาคไม่มีปี")
    assert in_year.status_code == 201 and no_year.status_code == 201

    res = client.get(
        "/api/settings/terms",
        params={"year_id": ty_world["old_year_id"]},
        headers=_auth(ty_world),
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert [t["id"] for t in body["items"]] == [in_year.json()["id"]]
    # ⚠️ total ต้องกรองด้วย — ถ้าลืม สคริปต์แบ่งหน้าจะโชว์ "2 ภาคเรียน" ทั้งที่เห็น 1
    assert body["total"] == 1

    # ไม่ระบุปี = ทุกปี (พฤติกรรมเดิมของหน้า admin)
    all_res = client.get("/api/settings/terms", headers=_auth(ty_world))
    assert all_res.json()["total"] == 2


# ============================================================
# 3) PATCH — ผูกปี / ล้างปี / ปีปลอม
# ============================================================
@pytest.mark.asyncio
async def test_patch_links_and_unlinks_year(ty_world, client, db_pool):
    term_id = _create(client, ty_world).json()["id"]
    assert await _year_of(db_pool, term_id) is None

    res = client.patch(
        f"/api/settings/terms/{term_id}",
        json={"academic_year_id": ty_world["old_year_id"]},
        headers=_auth(ty_world),
    )
    assert res.status_code == 200, res.text
    assert await _year_of(db_pool, term_id) == ty_world["old_year_id"]

    # `null` = สั่งล้างการผูก — **ความหมายที่ถูกต้อง** (ต่างจาก 3 คอลัมน์ที่เหลือ)
    res = client.patch(
        f"/api/settings/terms/{term_id}",
        json={"academic_year_id": None},
        headers=_auth(ty_world),
    )
    assert res.status_code == 200, res.text
    assert await _year_of(db_pool, term_id) is None


@pytest.mark.asyncio
async def test_patch_unknown_year_is_400(ty_world, client, db_pool):
    term_id = _create(client, ty_world).json()["id"]
    res = client.patch(
        f"/api/settings/terms/{term_id}",
        json={"academic_year_id": 999_999_999},
        headers=_auth(ty_world),
    )
    assert res.status_code == 400, res.text
    assert await _year_of(db_pool, term_id) is None


@pytest.mark.asyncio
async def test_patch_null_on_not_null_column_still_rejected(ty_world, client):
    """regression: การเปิด `null` ให้ academic_year_id ต้องไม่เปิดให้คอลัมน์อื่นด้วย"""
    term_id = _create(client, ty_world).json()["id"]
    for field in ("name", "start_date", "end_date"):
        res = client.patch(
            f"/api/settings/terms/{term_id}",
            json={field: None},
            headers=_auth(ty_world),
        )
        assert res.status_code == 400, f"{field}: {res.text}"
