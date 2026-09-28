"""
📅 ภาคเรียน (academic_terms) — T1
=====================================
ทดสอบ 4 ระดับ:
  1) HTTP — CRUD + auth/permission (401 / 403 / 400)
  2) Deep-DB — ค่าลงตารางจริง + audit_logs ถูกเขียน
  3) **"มีภาคปัจจุบันได้ตัวเดียว"** — ทั้งทาง service (สลับ/ลบ) และทาง DB (unique index)
  4) **กับดักที่พังง่าย**: ลบภาคปัจจุบัน → ตั้งภาคใหม่ → กู้คืนตัวเก่า
     (ถ้าลบแล้วไม่เคลียร์ `is_current` การกู้คืนจะชน unique index → 500)

ตาม docs/rules/testing.md: ตรวจ DB ตรง ๆ ผ่าน db_pool ไม่เชื่อ HTTP response
"""
import importlib
import random

import asyncpg
import pytest
import pytest_asyncio

from services import auth_service, term_service


@pytest_asyncio.fixture
async def term_world(db_pool, client):
    """
    โลกทดสอบ: ห้องเดียว + 4 บทบาท

      - admin              → is_admin=true (ผ่านโดยไม่ดู permissions)
      - president          → council_president ← มี MANAGE_SETTINGS ใน roles.json
      - council            → council_member ← **ไม่มี** MANAGE_SETTINGS (ตัวที่ต้องโดน 403)
      - student            → นักเรียนทั่วไป

    ⚠️ รับ `client` เข้ามาโดยเจตนา — บังคับให้ TestClient เปิด app (รัน init_db + migrations)
       จบก่อน จึงค่อยล้างตาราง (แบบเดียวกับ announcement_world)
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
        sid = f"TM{random.randint(1000, 9999)}{label[:2]}"  # ≤ 10 ตัว (student_id VARCHAR(10))
        uid = await auth_service.register_user(
            db_pool, sid, "1234", f"{label} ทดสอบ", sid, room_code, 1, role
        )
        users[label] = {
            "user_id": uid,
            "token": auth_service.create_access_token(uid),
        }

    # เริ่มจากศูนย์ — ไม่มีภาคปัจจุบัน (สถานะตั้งต้นจริงของระบบ)
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM academic_terms")

    users["room_id"] = room_id
    return users


def _auth(world, actor="admin") -> dict:
    return {"Authorization": f"Bearer {world[actor]['token']}"}


def _create(client, world, actor="admin", **overrides):
    payload = {
        "name": "ภาคเรียนที่ 1/2569",
        "start_date": "2026-05-16",
        "end_date": "2026-10-10",
    }
    payload.update(overrides)
    return client.post("/api/settings/terms", json=payload, headers=_auth(world, actor))


async def _term_rows(db_pool, term_id=None):
    """อ่านค่าดิบจากตาราง (deep-DB)"""
    async with db_pool.acquire() as conn:
        if term_id is not None:
            return await conn.fetch(
                "SELECT * FROM academic_terms WHERE id = $1", term_id
            )
        return await conn.fetch(
            "SELECT * FROM academic_terms ORDER BY id"
        )


async def _current_flags(db_pool) -> dict:
    """{id: is_current} ของแถวที่ยังไม่ถูกลบ"""
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, is_current FROM academic_terms WHERE deleted_at IS NULL"
        )
    return {r["id"]: r["is_current"] for r in rows}


async def _audit_actions(db_pool, term_id: int):
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT action FROM audit_logs
            WHERE entity_type = 'academic_term' AND entity_id = $1
            ORDER BY created_at
            """,
            str(term_id),
        )
    return [r["action"] for r in rows]


# ===================== 1) สร้าง + deep-DB =====================

@pytest.mark.asyncio
async def test_create_term_writes_row(client, term_world, db_pool):
    """สร้างภาค → 201 + แถวลง DB จริง + ไม่เป็นภาคปัจจุบันโดยค่าเริ่มต้น"""
    res = _create(client, term_world, name="ภาคเรียนที่ 1/2569")
    assert res.status_code == 201, res.text
    term_id = res.json()["id"]

    rows = await _term_rows(db_pool, term_id)
    assert len(rows) == 1
    assert rows[0]["name"] == "ภาคเรียนที่ 1/2569"
    assert rows[0]["is_current"] is False, "ค่าเริ่มต้นต้องไม่ใช่ภาคปัจจุบัน"
    assert rows[0]["deleted_at"] is None
    assert str(rows[0]["start_date"]) == "2026-05-16"
    assert str(rows[0]["end_date"]) == "2026-10-10"


@pytest.mark.asyncio
async def test_create_with_is_current(client, term_world, db_pool):
    """สร้างพร้อม is_current=true → เป็นภาคปัจจุบันทันที (deep-DB)"""
    res = _create(client, term_world, is_current=True)
    assert res.status_code == 201, res.text
    assert res.json()["is_current"] is True
    assert await _current_flags(db_pool) == {res.json()["id"]: True}


@pytest.mark.asyncio
async def test_create_writes_audit_log(client, term_world, db_pool):
    """ทุก mutation ต้องมี audit log (กฎ backend.md) — ตรวจถึง DB"""
    res = _create(client, term_world)
    term_id = res.json()["id"]
    assert await _audit_actions(db_pool, term_id) == ["CREATE_ACADEMIC_TERM"]


# ===================== 2) "มีภาคปัจจุบันได้ตัวเดียว" =====================

@pytest.mark.asyncio
async def test_create_second_current_clears_first(client, term_world, db_pool):
    """สร้างภาคปัจจุบันตัวที่สอง → ตัวแรกต้องถูกปลด เหลือ TRUE แถวเดียว"""
    first = _create(client, term_world, name="ภาค 1", is_current=True).json()["id"]
    second = _create(client, term_world, name="ภาค 2", is_current=True).json()["id"]

    flags = await _current_flags(db_pool)
    assert sum(flags.values()) == 1, f"ต้องมีภาคปัจจุบันตัวเดียว แต่ได้ {flags}"
    assert flags[second] is True
    assert flags[first] is False


@pytest.mark.asyncio
async def test_set_current_switches_from_old(client, term_world, db_pool):
    """set-current บนภาคที่สอง → สลับจากตัวแรก (deep-DB)"""
    first = _create(client, term_world, name="ภาค 1", is_current=True).json()["id"]
    second = _create(client, term_world, name="ภาค 2").json()["id"]

    res = client.post(
        f"/api/settings/terms/{second}/set-current", headers=_auth(term_world)
    )
    assert res.status_code == 200, res.text

    flags = await _current_flags(db_pool)
    assert sum(flags.values()) == 1
    assert flags[second] is True and flags[first] is False

    actions = await _audit_actions(db_pool, second)
    assert "SET_CURRENT_TERM" in actions


@pytest.mark.asyncio
async def test_set_current_twice_does_not_touch_timestamp(client, term_world, db_pool):
    """กด set-current ซ้ำบนตัวที่เป็นปัจจุบันอยู่ → ไม่ error และ **ไม่ทับ updated_at**"""
    term_id = _create(client, term_world, is_current=True).json()["id"]
    before = (await _term_rows(db_pool, term_id))[0]["updated_at"]

    res = client.post(
        f"/api/settings/terms/{term_id}/set-current", headers=_auth(term_world)
    )
    assert res.status_code == 200, res.text

    after = (await _term_rows(db_pool, term_id))[0]["updated_at"]
    assert after == before, "กดซ้ำต้องไม่ทับ timestamp เดิม (กัน audit หลอก)"
    assert sum((await _current_flags(db_pool)).values()) == 1


@pytest.mark.asyncio
async def test_unique_index_blocks_second_current_bypassing_service(
    client, term_world, db_pool
):
    """⚠️ ยิงตรง ๆ ที่ DB (ข้าม service) ตั้ง is_current=TRUE สองแถว → ต้องได้ UniqueViolationError

    ตัวนี้พิสูจน์ว่า "มีภาคปัจจุบันได้ตัวเดียว" บังคับที่ DB จริง ไม่ใช่แค่ในโค้ด service
    (ถ้า index ถูกสร้างผิด เช่นไม่มี WHERE is_current ก็จะไม่กันอะไรเลย)
    """
    a = _create(client, term_world, name="ภาค A", is_current=True).json()["id"]
    b = _create(client, term_world, name="ภาค B").json()["id"]

    async with db_pool.acquire() as conn:
        with pytest.raises(asyncpg.UniqueViolationError):
            await conn.execute(
                "UPDATE academic_terms SET is_current = TRUE WHERE id = $1", b
            )

    flags = await _current_flags(db_pool)
    assert flags[a] is True and flags[b] is False


# ===================== 3) ลบ / กู้คืน (กับดักตัวจริง) =====================

@pytest.mark.asyncio
async def test_delete_current_clears_is_current(client, term_world, db_pool):
    """ลบภาคที่เป็นปัจจุบัน → deleted_at มีค่า **และ** is_current ถูกเคลียร์"""
    term_id = _create(client, term_world, is_current=True).json()["id"]

    res = client.delete(
        f"/api/settings/terms/{term_id}", headers=_auth(term_world)
    )
    assert res.status_code == 200, res.text

    row = (await _term_rows(db_pool, term_id))[0]
    assert row["deleted_at"] is not None, "deep-DB: ต้องเป็น soft delete"
    assert row["is_current"] is False, "ต้องเคลียร์ is_current ตอนลบ"

    # และต้องตั้งภาคอื่นเป็นปัจจุบันได้ (ไม่ติด index ค้าง)
    other = _create(client, term_world, name="ภาคใหม่", is_current=True)
    assert other.status_code == 201, other.text


@pytest.mark.asyncio
async def test_restore_after_new_current_is_set_does_not_crash(
    client, term_world, db_pool
):
    """⚠️ กับดัก: ลบภาคปัจจุบัน → ตั้งภาคใหม่เป็นปัจจุบัน → กู้คืนตัวเก่า

    ถ้าตอนลบไม่เคลียร์ `is_current` การกู้คืนจะชน partial unique index → 500
    ที่นี่ต้องได้ 200 และตัวที่กู้คืนกลับมาเป็น **ภาคธรรมดา** (is_current = FALSE)
    """
    old = _create(client, term_world, name="ภาคเก่า", is_current=True).json()["id"]
    assert client.delete(
        f"/api/settings/terms/{old}", headers=_auth(term_world)
    ).status_code == 200

    new = _create(client, term_world, name="ภาคใหม่", is_current=True).json()["id"]

    res = client.post(
        f"/api/settings/terms/{old}/restore", headers=_auth(term_world)
    )
    assert res.status_code == 200, f"กู้คืนต้องไม่ระเบิด: {res.text}"

    row = (await _term_rows(db_pool, old))[0]
    assert row["deleted_at"] is None, "กู้คืนแล้วต้องไม่ถูกลบ"
    assert row["is_current"] is False, "กู้คืนมาเป็นภาคธรรมดา ต้องกดตั้งปัจจุบันเอง"

    flags = await _current_flags(db_pool)
    assert sum(flags.values()) == 1 and flags[new] is True

    assert "RESTORE_ACADEMIC_TERM" in await _audit_actions(db_pool, old)


@pytest.mark.asyncio
async def test_restore_unregistered_term_404(client, term_world):
    """กู้คืนแถวที่ไม่ได้ถูกลบ → 404 (ไม่ใช่ 200 เงียบ ๆ)"""
    term_id = _create(client, term_world).json()["id"]
    res = client.post(
        f"/api/settings/terms/{term_id}/restore", headers=_auth(term_world)
    )
    assert res.status_code == 404, res.text


# ===================== 4) วันที่ (400 ไม่ใช่ 500) =====================

@pytest.mark.asyncio
async def test_create_end_before_start_400(client, term_world, db_pool):
    """end_date < start_date → 400 พร้อมข้อความไทย (ไม่ใช่ 500 จาก CHECK constraint)"""
    res = _create(client, term_world, start_date="2026-10-10", end_date="2026-05-16")
    assert res.status_code == 400, res.text
    assert "วันสิ้นสุด" in res.json()["detail"]
    assert await _term_rows(db_pool) == [], "ต้องไม่ insert อะไรเลย"


@pytest.mark.asyncio
async def test_patch_start_after_existing_end_400(client, term_world, db_pool):
    """PATCH ส่งมาวันเดียว → ต้องเทียบกับ end_date ที่เก็บอยู่จริง (ไม่ใช่กับ None)"""
    term_id = _create(client, term_world).json()["id"]  # 05-16 .. 10-10

    res = client.patch(
        f"/api/settings/terms/{term_id}",
        json={"start_date": "2027-01-01"},  # เลย end_date เดิมไปแล้ว
        headers=_auth(term_world),
    )
    assert res.status_code == 400, res.text

    row = (await _term_rows(db_pool, term_id))[0]
    assert str(row["start_date"]) == "2026-05-16", "ค่าต้องไม่ถูกแก้"


@pytest.mark.asyncio
async def test_end_date_is_inclusive_stored_as_is(client, term_world, db_pool):
    """end_date เก็บตามที่ส่ง (ไม่ลบ 1 วัน) — ความหมาย inclusive ถูกจัดการตอนกรองวันที่"""
    res = _create(client, term_world, start_date="2026-05-16", end_date="2026-05-16")
    assert res.status_code == 201, res.text
    row = (await _term_rows(db_pool, res.json()["id"]))[0]
    assert str(row["start_date"]) == str(row["end_date"]) == "2026-05-16", (
        "ภาควันเดียวต้องสร้างได้ (CHECK เป็น >= ไม่ใช่ >)"
    )


# ===================== 5) PATCH =====================

@pytest.mark.asyncio
async def test_patch_is_partial(client, term_world, db_pool):
    """ส่งแค่ name → วันที่ต้องไม่ถูกแตะ"""
    term_id = _create(client, term_world).json()["id"]

    res = client.patch(
        f"/api/settings/terms/{term_id}",
        json={"name": "ภาคเรียนที่ 2/2569"},
        headers=_auth(term_world),
    )
    assert res.status_code == 200, res.text

    row = (await _term_rows(db_pool, term_id))[0]
    assert row["name"] == "ภาคเรียนที่ 2/2569"
    assert str(row["start_date"]) == "2026-05-16"
    assert str(row["end_date"]) == "2026-10-10"
    assert "UPDATE_ACADEMIC_TERM" in await _audit_actions(db_pool, term_id)


@pytest.mark.asyncio
async def test_patch_cannot_set_is_current(client, term_world, db_pool):
    """⚠️ ส่ง is_current ผ่าน PATCH ต้องไม่มีผล — ต้องใช้ set-current เท่านั้น

    (ถ้าหลุดเข้ามาได้ = มีสองทางเปลี่ยนภาคปัจจุบัน ทางหนึ่งไม่ล้างตัวเก่า → index พัง)
    """
    term_id = _create(client, term_world).json()["id"]
    res = client.patch(
        f"/api/settings/terms/{term_id}",
        json={"is_current": True},
        headers=_auth(term_world),
    )
    assert res.status_code == 400, res.text
    assert (await _term_rows(db_pool, term_id))[0]["is_current"] is False


@pytest.mark.asyncio
async def test_patch_deleted_term_404(client, term_world):
    """แก้ภาคที่ถูกลบ → 404 (ต้องกู้คืนก่อน กันแก้ประวัติเงียบ ๆ)"""
    term_id = _create(client, term_world).json()["id"]
    client.delete(f"/api/settings/terms/{term_id}", headers=_auth(term_world))

    res = client.patch(
        f"/api/settings/terms/{term_id}",
        json={"name": "แอบแก้"},
        headers=_auth(term_world),
    )
    assert res.status_code == 404, res.text


# ⚠️ `null` ที่ส่งมาชัด ๆ — ทั้งสามคอลัมน์เป็น NOT NULL ⇒ ต้องได้ 400 ไม่ใช่ 500
#    (`exclude_unset` ไม่กรองให้ เพราะการส่ง `null` มา = ฟิลด์ถูก "set" แล้ว)
#    เดิมพังเป็น 500 สองทาง: `None < date` = TypeError และ `SET name = NULL` = NotNullViolation
@pytest.mark.parametrize("field", ["name", "start_date", "end_date"])
@pytest.mark.asyncio
async def test_patch_explicit_null_400(client, term_world, db_pool, field):
    """ส่ง `{field: null}` → 400 พร้อมบอกชื่อฟิลด์ และ**แถวต้องไม่ถูกแตะเลย**"""
    term_id = _create(client, term_world).json()["id"]
    before = (await _term_rows(db_pool, term_id))[0]

    res = client.patch(
        f"/api/settings/terms/{term_id}",
        json={field: None},
        headers=_auth(term_world),
    )
    assert res.status_code == 400, f"ต้องเป็น 400 ไม่ใช่ {res.status_code}: {res.text}"
    assert field in res.json()["detail"], "ข้อความต้องบอกว่าฟิลด์ไหน"

    after = (await _term_rows(db_pool, term_id))[0]
    assert dict(after) == dict(before), "ห้ามแก้ค่าจริง"


@pytest.mark.asyncio
async def test_patch_null_alongside_valid_field_400(client, term_world, db_pool):
    """ส่ง `null` ปนกับฟิลด์ที่แก้ได้ → ต้องไม่บันทึก **แม้แต่ฟิลด์ที่ดี**

    (การปฏิเสธทั้งคำขอ กันสภาพครึ่ง ๆ กลาง ๆ ที่ผู้เรียกเข้าใจผิดว่าบันทึกแล้ว)
    """
    term_id = _create(client, term_world).json()["id"]

    res = client.patch(
        f"/api/settings/terms/{term_id}",
        json={"name": "ภาคใหม่", "end_date": None},
        headers=_auth(term_world),
    )
    assert res.status_code == 400, res.text
    assert (await _term_rows(db_pool, term_id))[0]["name"] == "ภาคเรียนที่ 1/2569", (
        "ชื่อต้องไม่ถูกแก้ (ทั้งคำขอถูกปฏิเสธ)"
    )


@pytest.mark.asyncio
async def test_patch_all_null_400_not_500(client, term_world):
    """ส่ง null ครบทุกฟิลด์ → 400 (ไม่ใช่ 500 และไม่ใช่ 200 เงียบ ๆ)"""
    term_id = _create(client, term_world).json()["id"]
    res = client.patch(
        f"/api/settings/terms/{term_id}",
        json={"name": None, "start_date": None, "end_date": None},
        headers=_auth(term_world),
    )
    assert res.status_code == 400, res.text


# ===================== 6) รายการ =====================

@pytest.mark.asyncio
async def test_list_status_filter(client, term_world):
    """status=active/current/deleted กรองถูก + ภาคปัจจุบันขึ้นก่อน"""
    a = _create(client, term_world, name="ภาค A", is_current=True).json()["id"]
    b = _create(client, term_world, name="ภาค B").json()["id"]
    c = _create(client, term_world, name="ภาค C").json()["id"]
    client.delete(f"/api/settings/terms/{c}", headers=_auth(term_world))

    active = client.get(
        "/api/settings/terms?status=active", headers=_auth(term_world)
    ).json()
    assert active["total"] == 2
    assert [i["id"] for i in active["items"]][0] == a, "ภาคปัจจุบันต้องขึ้นก่อน"
    assert b in [i["id"] for i in active["items"]]

    current = client.get(
        "/api/settings/terms?status=current", headers=_auth(term_world)
    ).json()
    assert current["total"] == 1 and current["items"][0]["id"] == a

    deleted = client.get(
        "/api/settings/terms?status=deleted", headers=_auth(term_world)
    ).json()
    assert deleted["total"] == 1 and deleted["items"][0]["id"] == c


@pytest.mark.asyncio
async def test_list_rejects_unknown_status(client, term_world):
    """status นอกลิสต์ → 422 ที่ชั้น Query pattern (ไม่หลุดถึง SQL)"""
    res = client.get(
        "/api/settings/terms?status=banana", headers=_auth(term_world)
    )
    assert res.status_code == 422, res.text


# ===================== 7) สิทธิ์ + auth =====================

@pytest.mark.asyncio
async def test_council_member_forbidden(client, term_world):
    """council_member ไม่มี MANAGE_SETTINGS → 403 ทุก endpoint (รวม GET)"""
    assert client.get(
        "/api/settings/terms", headers=_auth(term_world, "council")
    ).status_code == 403
    assert _create(client, term_world, actor="council").status_code == 403


@pytest.mark.asyncio
async def test_council_president_allowed(client, term_world):
    """council_president มี MANAGE_SETTINGS อยู่แล้ว → ผ่านโดยไม่ต้อง backfill สิทธิ์"""
    res = _create(client, term_world, actor="president")
    assert res.status_code == 201, res.text
    assert client.get(
        "/api/settings/terms", headers=_auth(term_world, "president")
    ).status_code == 200


@pytest.mark.asyncio
async def test_requires_login_api_key_401(client, term_world):
    """X-API-Key (system RPC) → user_id เป็น None → ต้อง 401 ไม่ใช่ 500"""
    headers = {"X-API-Key": "test-api-key"}
    assert client.get("/api/settings/terms", headers=headers).status_code == 401
    assert client.post(
        "/api/settings/terms",
        json={"name": "x", "start_date": "2026-05-16", "end_date": "2026-10-10"},
        headers=headers,
    ).status_code == 401


# ===================== 8) helper ที่ C3/B1 จะใช้ =====================

@pytest.mark.asyncio
async def test_get_current_term_none_when_never_set(client, term_world, db_pool):
    """⚠️ ยังไม่มีภาคปัจจุบัน = สถานะที่ถูกต้อง → คืน None (ไม่ใช่ raise)

    C3/B1 พึ่งพฤติกรรมนี้เพื่อ fallback ไป "นับทั้งหมด"
    """
    term_world  # ให้ fixture ทำงาน (สร้าง user + ล้างตาราง)
    assert await term_service.get_current_term(db_pool) is None


@pytest.mark.asyncio
async def test_get_current_term_returns_dates(client, term_world, db_pool):
    """มีภาคปัจจุบัน → คืน id/name/start_date/end_date (C3 ต้องใช้วันที่ไปกรอง)"""
    term_id = _create(
        client, term_world, name="ภาคเรียนที่ 1/2569", is_current=True
    ).json()["id"]

    term = await term_service.get_current_term(db_pool)
    assert term is not None
    assert term["id"] == term_id
    assert term["name"] == "ภาคเรียนที่ 1/2569"
    assert str(term["start_date"]) == "2026-05-16"
    assert str(term["end_date"]) == "2026-10-10"


@pytest.mark.asyncio
async def test_get_current_term_ignores_deleted(client, term_world, db_pool):
    """ภาคที่ถูกลบต้องไม่ถูกมองเป็นภาคปัจจุบัน"""
    term_id = _create(client, term_world, is_current=True).json()["id"]
    client.delete(f"/api/settings/terms/{term_id}", headers=_auth(term_world))

    assert await term_service.get_current_term(db_pool) is None


# ===================== 9) migration 017 =====================

@pytest.mark.asyncio
async def test_migration_017_creates_table_and_indexes(term_world, db_pool):
    """จำลอง DB ที่ยังไม่มีตาราง → รัน upgrade() ตรง ๆ → ต้องได้ตาราง + index ครบ

    (เทสต์นี้รันท้ายไฟล์โดยเจตนา เพราะมัน DROP ตารางทิ้งแล้วสร้างใหม่ — upgrade()
    ต้องสร้างคืนครบทั้งตาราง/index/constraint ไม่งั้นเทสต์ไฟล์อื่นที่รันต่อจะพัง)
    """
    term_world
    mig = importlib.import_module("migrations.017_academic_terms")

    async with db_pool.acquire() as conn:
        await conn.execute("DROP TABLE IF EXISTS academic_terms CASCADE")

        missing = await conn.fetchval(
            "SELECT to_regclass('public.academic_terms') IS NULL"
        )
        assert missing is True, "ต้องลบตารางได้จริงก่อนทดสอบ"

        await mig.upgrade(conn)
        await mig.upgrade(conn)  # idempotent — รันซ้ำต้องไม่ error

        # ตารางเกิดจริง
        assert await conn.fetchval(
            "SELECT to_regclass('public.academic_terms') IS NOT NULL"
        ) is True

        # index ครบ 2 ตัว (unique ปัจจุบัน + ช่วงวันที่)
        indexes = {
            r["indexname"]
            for r in await conn.fetch(
                "SELECT indexname FROM pg_indexes WHERE tablename = 'academic_terms'"
            )
        }
        assert "uq_academic_terms_single_current" in indexes
        assert "idx_academic_terms_dates" in indexes

        # CHECK constraint ยังอยู่ (ด่านสุดท้ายกัน end < start)
        constraints = {
            r["conname"]
            for r in await conn.fetch(
                """
                SELECT conname FROM pg_constraint
                WHERE conrelid = 'academic_terms'::regclass AND contype = 'c'
                """
            )
        }
        assert "chk_academic_terms_range" in constraints

        # ใช้งานได้จริงหลัง migrate
        await conn.execute(
            """
            INSERT INTO academic_terms (name, start_date, end_date, is_current)
            VALUES ('ภาคทดสอบ', '2026-05-16', '2026-10-10', TRUE)
            """
        )
        await conn.execute("DELETE FROM academic_terms")
