"""
🔖 บันทึกไว้อ่านทีหลัง (C2) — /api/bookmarks
============================================
ทดสอบ 5 ระดับ:
  1) HTTP — 201 (ใหม่) / **200 (มีอยู่แล้ว — ไม่ใช่ 409)** / 404 / 422 / 401 / 204
  2) Deep-DB — ทุก mutation ต้องพิสูจน์กับตารางจริง ไม่เชื่อ response
     (ตาม docs/rules/testing.md: "Deep DB verification is mandatory")
  3) **ความปลอดภัยข้ามผู้ใช้** — ★ หัวใจของตารางนี้
     `bookmarks` **ไม่มี FK ผูกกับเจ้าของ** และไม่มี RLS ⇒ ด่านเดียวคือ `AND user_id = $1`
     · B5 พิสูจน์ว่าลบข้ามคนไม่ได้
     · B10 พิสูจน์ว่า `X-API-Key` ได้ 401 (ไม่ใช่ 500 จาก FK violation ของ user NULL)
     · B9ข พิสูจน์ว่า `user_id` ใน body ถูก **ทิ้ง** ไม่ใช่ถูกใช้
  4) **ความทนของ join** — ต้นทางถูกลบ (soft) ⇒ bookmark **ยังอยู่ในลิสต์** + `is_deleted_source`
     (LEFT JOIN ไม่ใช่ INNER — ไม่งั้นผู้ใช้จะถามว่า "ที่บันทึกไว้หายไปไหน")
  5) idempotency — ★ `bookmark` = set membership ไม่ใช่การลงคะแนน ⇒ กดซ้ำต้องไม่ error
     (**เบี่ยงจาก `piri_votes` โดยเจตนา** — ที่นั่น 409 เพราะ "หนึ่งเสียง" มีความหมายจริง)

ตาม docs/rules/testing.md: ห้าม hardcode id · ใช้ fixture ล้างตารางก่อนทุกเทสต์
"""
import importlib
import random

import pytest
import pytest_asyncio

from services import auth_service


@pytest_asyncio.fixture
async def bm_world(db_pool, client):
    """ห้องเดียว + ผู้ใช้ 2 คน (`me` = เจ้าของ bookmark · `other` = ผู้บุกรุก)

    ⚠️ รับ `client` เข้ามาโดยเจตนา — บังคับให้ TestClient เปิด app (รัน init_db + migrations)
       จบก่อน แล้วค่อยล้างตาราง
    """
    room_code = f"ม.6/{random.randint(1, 90)}"
    async with db_pool.acquire() as conn:
        room_id = await conn.fetchval(
            "INSERT INTO rooms (room_code, room_name, level) VALUES ($1,$2,'ม.6') RETURNING id",
            room_code, room_code,
        )

    users = {"room_id": room_id}
    for label in ("me", "other"):
        sid = f"BM{random.randint(1000, 9999)}{label[:2]}"  # ≤ 10 ตัว (student_id VARCHAR(10))
        uid = await auth_service.register_user(
            db_pool, sid, "1234", f"{label} ทดสอบ", sid, room_code, 1, "student"
        )
        users[label] = {"user_id": uid, "token": auth_service.create_access_token(uid)}

    return users


def _auth(world, actor="me") -> dict:
    return {"Authorization": f"Bearer {world[actor]['token']}"}


# ── helpers สร้างข้อมูลดิบ ──

async def _issue(db_pool, world, *, title="เรื่องทดสอบ", deleted=False) -> int:
    """⚠️ `category` เป็น NOT NULL และ **ไม่มี default** ⇒ ต้องส่งเสมอ"""
    async with db_pool.acquire() as conn:
        return await conn.fetchval(
            """
            INSERT INTO issues (room_id, category, title, description, reporter_id, deleted_at)
            VALUES ($1, 'other', $2, 'รายละเอียดเรื่อง', $3,
                    CASE WHEN $4::boolean THEN NOW() ELSE NULL END)
            RETURNING id
            """,
            world["room_id"], title, world["me"]["user_id"], deleted,
        )


async def _board(db_pool, world, *, title="บอร์ดทดสอบ", deleted=False) -> int:
    async with db_pool.acquire() as conn:
        return await conn.fetchval(
            """
            INSERT INTO piri_boards (board_type, title, description, author_id, deleted_at)
            VALUES ('talk', $1, 'รายละเอียดบอร์ด', $2,
                    CASE WHEN $3::boolean THEN NOW() ELSE NULL END)
            RETURNING id
            """,
            title, world["me"]["user_id"], deleted,
        )


async def _count_bookmarks(db_pool) -> int:
    async with db_pool.acquire() as conn:
        return await conn.fetchval("SELECT COUNT(*)::int FROM bookmarks")


def _post(client, world, entity_type, entity_id, actor="me", **extra):
    return client.post(
        "/api/bookmarks",
        headers=_auth(world, actor),
        json={"entity_type": entity_type, "entity_id": entity_id, **extra},
    )


# ════════════════════════════════════════════════════════════
# 1) สร้าง — และ idempotency
# ════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_create_bookmark_returns_201_and_persists(client, db_pool, bm_world):
    """B1 — POST เรื่องจริง ⇒ 201 + **แถวเกิดจริงใน DB** (ไม่เชื่อ response)"""
    issue_id = await _issue(db_pool, bm_world)

    r = _post(client, bm_world, "issue", issue_id)

    assert r.status_code == 201, r.text
    body = r.json()
    assert body["entity_type"] == "issue"
    assert body["entity_id"] == issue_id
    assert body["id"] > 0

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT user_id, entity_type, entity_id FROM bookmarks WHERE id = $1", body["id"]
        )
    assert row is not None, "ต้องมีแถวจริงใน DB"
    assert row["user_id"] == bm_world["me"]["user_id"]
    assert row["entity_type"] == "issue"
    assert row["entity_id"] == issue_id


@pytest.mark.asyncio
async def test_create_board_bookmark(client, db_pool, bm_world):
    """B1ข — บอร์ดก็บันทึกได้ (ตารางนี้ polymorphic)"""
    board_id = await _board(db_pool, bm_world)

    r = _post(client, bm_world, "board", board_id)
    assert r.status_code == 201
    assert r.json()["entity_type"] == "board"

    assert await _count_bookmarks(db_pool) == 1


@pytest.mark.asyncio
async def test_duplicate_create_returns_200_and_keeps_one_row(client, db_pool, bm_world):
    """B2 — ★ POST ซ้ำ ⇒ **200 (ไม่ใช่ 201 ไม่ใช่ 409)** และมีแถวเดียว

    `bookmark` = "อยู่ในชุดที่บันทึก" ⇒ ดับเบิลแท็ป/เน็ตช้า/กดสองแท็บ ต้องไม่เป็น error
    ถ้าเปลี่ยนไปใช้ `ConflictError` (แบบ `piri_votes`) เทสต์นี้จะแตกทันที
    """
    issue_id = await _issue(db_pool, bm_world)

    first = _post(client, bm_world, "issue", issue_id)
    second = _post(client, bm_world, "issue", issue_id)

    assert first.status_code == 201
    assert second.status_code == 200, "ซ้ำต้องได้ 200 ไม่ใช่ 409/500"
    # ★ id เดิม ⇒ พิสูจน์ว่าเป็นแถวเดิมจริง ไม่ได้สร้างใหม่แล้วลบเก่า
    assert second.json()["id"] == first.json()["id"]
    assert await _count_bookmarks(db_pool) == 1


@pytest.mark.asyncio
async def test_same_entity_can_be_bookmarked_by_two_users(client, db_pool, bm_world):
    """B2ข — unique เป็น (user_id, entity_type, entity_id) ไม่ใช่ (entity_type, entity_id)"""
    issue_id = await _issue(db_pool, bm_world)

    assert _post(client, bm_world, "issue", issue_id, actor="me").status_code == 201
    assert _post(client, bm_world, "issue", issue_id, actor="other").status_code == 201

    assert await _count_bookmarks(db_pool) == 2


@pytest.mark.asyncio
async def test_same_id_different_type_is_a_separate_bookmark(client, db_pool, bm_world):
    """B2ค — ★ `entity_id` ซ้ำกันข้ามชนิดต้องเป็นคนละอัน (unique ต้องมี `entity_type` อยู่ด้วย)

    ถ้า unique index เป็น `(user_id, entity_id)` เฉย ๆ (ลืม `entity_type`) เทสต์นี้จะได้
    **200 ทั้งคู่และเหลือแถวเดียว** — ซึ่งผิด เพราะเรื่อง #7 กับบอร์ด #7 คนละสิ่งกัน

    ⚠️ **ตั้งใจยัด id ให้ชนกัน** — `TRUNCATE` ของ conftest ไม่ได้ `RESTART IDENTITY`
       ⇒ ลำดับของ SERIAL แต่ละตารางวิ่งคนละความเร็ว ⇒ พึ่ง "บังเอิญเท่ากัน" ไม่ได้
       จึง insert ด้วย id ที่ระบุเอง แล้ว `setval` ให้ sequence ข้ามไปพ้น
       (ไม่งั้น insert ปกติครั้งถัดไปอาจชนกับ id ที่ยัดไว้)
    """
    collide_id = 900_000
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO issues (id, room_id, category, title, description, reporter_id)
            VALUES ($1, $2, 'other', 'เรื่อง id ชน', 'รายละเอียด', $3)
            """,
            collide_id, bm_world["room_id"], bm_world["me"]["user_id"],
        )
        await conn.execute(
            """
            INSERT INTO piri_boards (id, board_type, title, description, author_id)
            VALUES ($1, 'talk', 'บอร์ด id ชน', 'รายละเอียด', $2)
            """,
            collide_id, bm_world["me"]["user_id"],
        )
        await conn.execute("SELECT setval('issues_id_seq', $1)", collide_id)
        await conn.execute("SELECT setval('piri_boards_id_seq', $1)", collide_id)

    assert _post(client, bm_world, "issue", collide_id).status_code == 201
    assert _post(client, bm_world, "board", collide_id).status_code == 201

    assert await _count_bookmarks(db_pool) == 2

    body = client.get("/api/bookmarks", headers=_auth(bm_world)).json()
    assert {i["entity_type"] for i in body["items"]} == {"issue", "board"}


# ════════════════════════════════════════════════════════════
# 2) entity ที่ไม่มีจริง / ถูกลบ
# ════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_create_for_missing_entity_returns_404(client, db_pool, bm_world):
    """B3 — entity ที่ไม่มีจริง ⇒ 404 (ไม่ใช่ 201 แล้วได้ bookmark ลอยที่ join ไม่เจออะไร)"""
    r = _post(client, bm_world, "issue", 999_999)

    assert r.status_code == 404, r.text
    assert await _count_bookmarks(db_pool) == 0


@pytest.mark.asyncio
async def test_create_for_soft_deleted_entity_returns_404(client, db_pool, bm_world):
    """B4 — entity ที่ถูกลบ (soft) ⇒ 404

    ถ้าลบเงื่อนไข `deleted_at IS NULL` ออก จะบันทึกได้ ⇒ ผู้ใช้จะบันทึกสิ่งที่ตัวเองมองไม่เห็น
    """
    issue_id = await _issue(db_pool, bm_world, deleted=True)
    board_id = await _board(db_pool, bm_world, deleted=True)

    assert _post(client, bm_world, "issue", issue_id).status_code == 404
    assert _post(client, bm_world, "board", board_id).status_code == 404
    assert await _count_bookmarks(db_pool) == 0


@pytest.mark.asyncio
async def test_create_missing_board_returns_404(client, db_pool, bm_world):
    """B4ข — 'board' ที่ไม่มี ⇒ 404 เหมือนกัน (ไม่ใช่ 500 จาก KeyError)"""
    r = _post(client, bm_world, "board", 999_999)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_create_for_hidden_board_returns_404(client, db_pool, bm_world):
    """B4ค — ★ บอร์ดที่ถูก **ซ่อน** (`status = 'hidden'`) ⇒ 404 เหมือนถูกลบ

    `get_board_detail()` 404 ให้บอร์ดที่ซ่อน ⇒ บันทึกไปก็เปิดดูไม่ได้
    ⇒ ต้องปฏิเสธตั้งแต่ตอนบันทึก (สัญญาเดียวกับ B4 ที่ใช้ `deleted_at`)
    ⚠️ ห้ามใช้ `status <> 'active'` — `'closed'` ยังเปิดดูได้ ⇒ จะปฏิเสธของที่ดูได้จริง
    """
    board_id = await _board(db_pool, bm_world)
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE piri_boards SET status = 'hidden' WHERE id = $1", board_id)

    assert _post(client, bm_world, "board", board_id).status_code == 404
    assert await _count_bookmarks(db_pool) == 0


# ════════════════════════════════════════════════════════════
# 3) ลบ — และด่านกันลบข้ามคน
# ════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_delete_own_bookmark(client, db_pool, bm_world):
    """B5ก — ลบของตัวเอง ⇒ 204 + **แถวหายจริง** (DELETE จริง ไม่ใช่ soft delete)"""
    issue_id = await _issue(db_pool, bm_world)
    bookmark_id = _post(client, bm_world, "issue", issue_id).json()["id"]

    r = client.delete(f"/api/bookmarks/{bookmark_id}", headers=_auth(bm_world))

    assert r.status_code == 204
    assert r.content == b"", "204 ต้องไม่มี body"
    assert await _count_bookmarks(db_pool) == 0


@pytest.mark.asyncio
async def test_delete_someone_elses_bookmark_is_404_and_keeps_the_row(client, db_pool, bm_world):
    """B5 — ★★★ ลบของคนอื่น ⇒ **404 และแถวของเจ้าของยังอยู่**

    นี่คือด่านความปลอดภัย **เดียว** ของตารางนี้ (`AND user_id = $2` ใน `delete_bookmark`)
    ตารางไม่มี FK ผูกกับเจ้าของ ไม่มี RLS ⇒ ถ้าลบเงื่อนไขนั้นออก ผู้ใช้คนไหนก็ลบ bookmark
    ของคนอื่นได้ถ้าเดา id ถูก — และจะ **ไม่ error ด้วย** (แถวของเจ้าของหายเงียบ ๆ)
    """
    issue_id = await _issue(db_pool, bm_world)
    bookmark_id = _post(client, bm_world, "issue", issue_id).json()["id"]

    r = client.delete(f"/api/bookmarks/{bookmark_id}", headers=_auth(bm_world, "other"))

    assert r.status_code == 404, "ต้องไม่ยืนยันว่ามีอยู่จริง"
    assert await _count_bookmarks(db_pool) == 1, "แถวของเจ้าของต้องไม่หาย"

    async with db_pool.acquire() as conn:
        owner = await conn.fetchval("SELECT user_id FROM bookmarks WHERE id = $1", bookmark_id)
    assert owner == bm_world["me"]["user_id"]


@pytest.mark.asyncio
async def test_delete_twice_returns_404(client, db_pool, bm_world):
    """B5ข — ลบซ้ำ ⇒ 404 (ไม่ใช่ 204 ปลอมที่โกหกว่าลบสำเร็จ)"""
    issue_id = await _issue(db_pool, bm_world)
    bookmark_id = _post(client, bm_world, "issue", issue_id).json()["id"]

    assert client.delete(f"/api/bookmarks/{bookmark_id}", headers=_auth(bm_world)).status_code == 204
    assert client.delete(f"/api/bookmarks/{bookmark_id}", headers=_auth(bm_world)).status_code == 404


@pytest.mark.asyncio
async def test_delete_missing_bookmark_returns_404(client, bm_world):
    r = client.delete("/api/bookmarks/999999", headers=_auth(bm_world))
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_delete_requires_authentication(client, bm_world):
    r = client.delete("/api/bookmarks/1")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_list_keeps_hidden_board_with_flag(client, db_pool, bm_world):
    """B6ข — ★ บันทึกไว้ **ก่อน** บอร์ดถูกซ่อน ⇒ ยังอยู่ในลิสต์ + ติดธง + ชื่อจริง

    ถ้าเช็คแค่ `deleted_at` ลิสต์จะโชว์เป็นลิงก์ปกติ ⇒ กดแล้ว 404
    (ผู้ใช้จะอ่านว่า "บันทึกไว้พาไปหน้าที่ไม่มี" ซึ่งหาสาเหตุยาก)
    """
    board_id = await _board(db_pool, bm_world, title="บอร์ดที่จะถูกซ่อน")
    assert _post(client, bm_world, "board", board_id).status_code == 201

    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE piri_boards SET status = 'hidden' WHERE id = $1", board_id)

    body = client.get("/api/bookmarks", headers=_auth(bm_world)).json()
    assert body["total"] == 1
    item = body["items"][0]
    assert item["is_deleted_source"] is True
    assert item["title"] == "บอร์ดที่จะถูกซ่อน"


@pytest.mark.asyncio
async def test_closed_board_is_bookmarkable_and_not_flagged(client, db_pool, bm_world):
    """B6ค — ★ ด่านกันแก้เกิน: บอร์ดที่ **ปิด** ต้องบันทึกได้ และ **ไม่** ติดธง

    เปิดดูได้จริง (detail ไม่ 404) ⇒ ทั้ง `_EXISTS_SQL` และ `is_deleted_source`
    ต้องไม่ตัดมันออก · ถ้าใช้ `status <> 'active'` เทสต์นี้จะล้มทั้งสอง assert
    """
    board_id = await _board(db_pool, bm_world)
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE piri_boards SET status = 'closed' WHERE id = $1", board_id)

    assert _post(client, bm_world, "board", board_id).status_code == 201

    body = client.get("/api/bookmarks", headers=_auth(bm_world)).json()
    assert body["total"] == 1
    assert body["items"][0]["is_deleted_source"] is False


# ════════════════════════════════════════════════════════════
# 4) ลิสต์
# ════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_list_returns_real_title_from_source(client, db_pool, bm_world):
    """B6ก — `title` มาจาก join กลับไปหาต้นทางจริง (ไม่ใช่คัดลอกมาตอนบันทึก)"""
    issue_id = await _issue(db_pool, bm_world, title="เรื่องชื่อเฉพาะ")
    board_id = await _board(db_pool, bm_world, title="บอร์ดชื่อเฉพาะ")
    _post(client, bm_world, "issue", issue_id)
    _post(client, bm_world, "board", board_id)

    r = client.get("/api/bookmarks", headers=_auth(bm_world))
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["total"] == 2
    titles = {i["entity_type"]: i["title"] for i in body["items"]}
    assert titles == {"issue": "เรื่องชื่อเฉพาะ", "board": "บอร์ดชื่อเฉพาะ"}
    assert all(i["is_deleted_source"] is False for i in body["items"])


@pytest.mark.asyncio
async def test_list_keeps_deleted_source_with_flag(client, db_pool, bm_world):
    """B6 — ★ ต้นทางถูกลบ ⇒ **ยังอยู่ในลิสต์** + `is_deleted_source = true`

    ถ้าใช้ INNER JOIN แถวนั้นจะหายไปเงียบ ๆ ⇒ ผู้ใช้จะถามว่า "ที่บันทึกไว้หายไปไหน"
    และจะไม่มีทางรู้ว่าต้นทางถูกลบ (ต้องบอกให้ชัด ไม่ใช่ซ่อน)
    """
    issue_id = await _issue(db_pool, bm_world, title="เรื่องที่จะถูกลบ")
    bookmark_id = _post(client, bm_world, "issue", issue_id).json()["id"]

    # บันทึกไว้ **แล้ว** ต้นทางถูกลบ ⇒ bookmark ต้องอยู่ต่อ
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE issues SET deleted_at = NOW() WHERE id = $1", issue_id)

    body = client.get("/api/bookmarks", headers=_auth(bm_world)).json()

    assert body["total"] == 1
    item = body["items"][0]
    assert item["id"] == bookmark_id
    assert item["is_deleted_source"] is True
    # ★ title ยังเป็นชื่อจริง (ไม่ถูกแทนด้วยข้อความ placeholder) — ให้ frontend เป็นคนตัดสินใจแสดง
    assert item["title"] == "เรื่องที่จะถูกลบ"


@pytest.mark.asyncio
async def test_list_is_own_only_and_newest_first(client, db_pool, bm_world):
    """B6ข — เห็นแต่ของตัวเอง · เรียงล่าสุดก่อน"""
    mine_a = await _issue(db_pool, bm_world, title="ของฉัน A")
    mine_b = await _issue(db_pool, bm_world, title="ของฉัน B")
    theirs = await _issue(db_pool, bm_world, title="ของคนอื่น")

    _post(client, bm_world, "issue", mine_a)
    _post(client, bm_world, "issue", mine_b)
    _post(client, bm_world, "issue", theirs, actor="other")

    body = client.get("/api/bookmarks", headers=_auth(bm_world)).json()

    assert body["total"] == 2
    # ล่าสุด (B) มาก่อน — insert ทีหลัง ⇒ created_at ใหม่กว่า
    assert [i["title"] for i in body["items"]] == ["ของฉัน B", "ของฉัน A"]


@pytest.mark.asyncio
async def test_list_filters_by_entity_type(client, db_pool, bm_world):
    """B7 — `?entity_type=board` ⇒ เฉพาะบอร์ด และ `total` ตรงกับที่กรอง"""
    issue_id = await _issue(db_pool, bm_world)
    board_id = await _board(db_pool, bm_world)
    _post(client, bm_world, "issue", issue_id)
    _post(client, bm_world, "board", board_id)

    body = client.get(
        "/api/bookmarks", headers=_auth(bm_world), params={"entity_type": "board"}
    ).json()

    assert body["total"] == 1
    assert [i["entity_type"] for i in body["items"]] == ["board"]

    # ไม่กรอง ⇒ ได้ทั้งคู่ (พิสูจน์ว่าไม่ใช่เพราะอันหนึ่งไม่ถูกสร้าง)
    assert client.get("/api/bookmarks", headers=_auth(bm_world)).json()["total"] == 2


@pytest.mark.asyncio
async def test_list_envelope_and_pagination(client, db_pool, bm_world):
    """B7ข — envelope เดียวกับ `list_notifications` + แบ่งหน้าได้จริง"""
    for n in range(3):
        _post(client, bm_world, "issue", await _issue(db_pool, bm_world, title=f"เรื่อง {n}"))

    body = client.get(
        "/api/bookmarks", headers=_auth(bm_world), params={"limit": 2, "offset": 0}
    ).json()

    assert set(body.keys()) == {"items", "total", "page", "page_size", "pages"}
    assert (body["total"], body["page"], body["page_size"], body["pages"]) == (3, 1, 2, 2)
    assert len(body["items"]) == 2

    page2 = client.get(
        "/api/bookmarks", headers=_auth(bm_world), params={"limit": 2, "offset": 2}
    ).json()
    assert len(page2["items"]) == 1
    assert page2["page"] == 2


@pytest.mark.asyncio
async def test_empty_list_for_new_user(client, bm_world):
    """B7ค — ผู้ใช้ใหม่ ⇒ ลิสต์ว่าง + total 0 (ไม่ใช่ null/500)"""
    body = client.get("/api/bookmarks", headers=_auth(bm_world)).json()
    assert body == {"items": [], "total": 0, "page": 1, "page_size": 20, "pages": 0}


# ════════════════════════════════════════════════════════════
# 5) สถานะ (ให้ปุ่มไอคอนรู้ว่าจะวาดติ๊กหรือไม่)
# ════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_status_before_and_after(client, db_pool, bm_world):
    """B8 — ก่อนบันทึก `{false, null}` → หลังบันทึก `{true, id}` → ลบแล้วกลับเป็น `{false, null}`"""
    issue_id = await _issue(db_pool, bm_world)
    params = {"entity_type": "issue", "entity_id": issue_id}

    before = client.get("/api/bookmarks/status", headers=_auth(bm_world), params=params).json()
    assert before == {"bookmarked": False, "bookmark_id": None}

    bookmark_id = _post(client, bm_world, "issue", issue_id).json()["id"]

    after = client.get("/api/bookmarks/status", headers=_auth(bm_world), params=params).json()
    assert after == {"bookmarked": True, "bookmark_id": bookmark_id}

    client.delete(f"/api/bookmarks/{bookmark_id}", headers=_auth(bm_world))

    again = client.get("/api/bookmarks/status", headers=_auth(bm_world), params=params).json()
    assert again == {"bookmarked": False, "bookmark_id": None}


@pytest.mark.asyncio
async def test_status_is_per_user(client, db_pool, bm_world):
    """B8ข — ★ คนอื่นบันทึกไว้ ⇒ สถานะของ **ฉัน** ยังเป็น false (ห้ามรั่วข้ามคน)"""
    issue_id = await _issue(db_pool, bm_world)
    params = {"entity_type": "issue", "entity_id": issue_id}
    _post(client, bm_world, "issue", issue_id, actor="other")

    mine = client.get("/api/bookmarks/status", headers=_auth(bm_world), params=params).json()
    theirs = client.get(
        "/api/bookmarks/status", headers=_auth(bm_world, "other"), params=params
    ).json()

    assert mine["bookmarked"] is False
    assert theirs["bookmarked"] is True


@pytest.mark.asyncio
async def test_status_for_deleted_entity_is_false(client, db_pool, bm_world):
    """B8ค — ต้นทางถูกลบ ⇒ สถานะยังบอกว่าบันทึกไว้ (ให้ผู้ใช้กดยกเลิกได้) ไม่ใช่ 500"""
    issue_id = await _issue(db_pool, bm_world)
    _post(client, bm_world, "issue", issue_id)

    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE issues SET deleted_at = NOW() WHERE id = $1", issue_id)

    body = client.get(
        "/api/bookmarks/status",
        headers=_auth(bm_world),
        params={"entity_type": "issue", "entity_id": issue_id},
    ).json()
    assert body["bookmarked"] is True


# ════════════════════════════════════════════════════════════
# 6) Validation + ความปลอดภัย
# ════════════════════════════════════════════════════════════

@pytest.mark.asyncio
@pytest.mark.parametrize("bad_type", ["event", "ISSUE", "issues", "", "board ' OR 1=1 --"])
async def test_unknown_entity_type_is_422(client, bm_world, bad_type):
    """B9 — `entity_type` นอกลิสต์ ⇒ 422 จาก `Literal` **ก่อน**ถึง service

    ★ มีเคส injection อยู่ในพารามิเตอร์นี้โดยเจตนา — ถ้ามีวันไหนมีคนเปลี่ยน `Literal`
    เป็น `str` แล้วต่อชื่อตารางด้วย f-string เทสต์นี้จะกลายเป็นด่านที่จับได้
    """
    r = _post(client, bm_world, bad_type, 1)
    assert r.status_code == 422, f"{bad_type!r} ควรได้ 422"


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_id", [0, -1])
async def test_non_positive_entity_id_is_422(client, bm_world, bad_id):
    """B9ข — `entity_id` ต้อง > 0 (`Field(gt=0)`)"""
    r = _post(client, bm_world, "issue", bad_id)
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_user_id_in_body_is_ignored(client, db_pool, bm_world):
    """B9ค — ★★ ส่ง `user_id` ของคนอื่นมาใน body ⇒ ต้องถูก **ทิ้ง** ไม่ใช่ถูกใช้

    `BookmarkCreateRequest` ไม่ประกาศฟิลด์นี้ และ pydantic ตัดฟิลด์ที่ไม่รู้จักทิ้ง
    ⇒ ถ้ามีวันไหนมีคนเพิ่ม `user_id: int` เข้า schema เทสต์นี้จะแตกทันที
    (นี่คือด่าน security ไม่ใช่ด่าน validation)
    """
    issue_id = await _issue(db_pool, bm_world)

    r = _post(client, bm_world, "issue", issue_id, user_id=bm_world["other"]["user_id"])

    assert r.status_code == 201
    async with db_pool.acquire() as conn:
        owner = await conn.fetchval("SELECT user_id FROM bookmarks WHERE id = $1", r.json()["id"])
    assert owner == bm_world["me"]["user_id"], "ต้องเป็นเจ้าของ token ไม่ใช่ค่าที่ส่งมา"


@pytest.mark.asyncio
async def test_api_key_is_rejected_with_401_everywhere(client, bm_world):
    """B10 — ⚠️ `X-API-Key` ต้องได้ **401 ไม่ใช่ 500**

    ถ้าไม่มี `_ensure_user()` จะเกิด `user_id = None` ⇒ `INSERT ... user_id NULL`
    ⇒ FK violation = **500** (และ list/status จะเงียบ ๆ นับของ NULL)
    """
    headers = {"X-API-Key": "test-api-key"}

    assert client.get("/api/bookmarks", headers=headers).status_code == 401
    assert client.get(
        "/api/bookmarks/status", headers=headers, params={"entity_type": "issue", "entity_id": 1}
    ).status_code == 401
    assert client.post(
        "/api/bookmarks", headers=headers, json={"entity_type": "issue", "entity_id": 1}
    ).status_code == 401
    assert client.delete("/api/bookmarks/1", headers=headers).status_code == 401


@pytest.mark.asyncio
async def test_requires_authentication(client, bm_world):
    """B10ข — ไม่มี token เลย ⇒ 401 ทุก endpoint"""
    assert client.get("/api/bookmarks").status_code == 401
    assert client.get(
        "/api/bookmarks/status", params={"entity_type": "issue", "entity_id": 1}
    ).status_code == 401
    assert client.post(
        "/api/bookmarks", json={"entity_type": "issue", "entity_id": 1}
    ).status_code == 401


@pytest.mark.asyncio
async def test_status_requires_valid_params(client, bm_world):
    """B10ค — `/status` ไม่มี query ⇒ 422 (ไม่ใช่ 500)"""
    assert client.get("/api/bookmarks/status", headers=_auth(bm_world)).status_code == 422


# ════════════════════════════════════════════════════════════
# 7) service layer ตรง ๆ
# ════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_service_unknown_type_raises_not_found(db_pool, bm_world):
    """B11ก — `_checked()` แปลงชนิดที่ไม่รู้จักเป็น `NotFoundError` (404) **ไม่ใช่ KeyError (500)**

    เป็นด่านกันวันที่มีคนเพิ่ม `Literal` แล้วลืมเพิ่ม `_EXISTS_SQL`
    """
    from core.exceptions import NotFoundError
    from services import bookmark_service

    with pytest.raises(NotFoundError):
        await bookmark_service.get_status(
            db_pool, bm_world["me"]["user_id"], entity_type="event", entity_id=1
        )

    with pytest.raises(NotFoundError):
        await bookmark_service.create_bookmark(
            db_pool, bm_world["me"]["user_id"], entity_type="event", entity_id=1
        )


@pytest.mark.asyncio
async def test_service_create_reports_created_flag(db_pool, bm_world):
    """B11ข — `create_bookmark` คืน `(created, row)` — ธงนี้คือสิ่งที่ router ใช้ตัดสิน 201/200"""
    from services import bookmark_service

    issue_id = await _issue(db_pool, bm_world)
    uid = bm_world["me"]["user_id"]

    created, row = await bookmark_service.create_bookmark(
        db_pool, uid, entity_type="issue", entity_id=issue_id
    )
    assert created is True
    assert row["entity_id"] == issue_id

    created_again, row_again = await bookmark_service.create_bookmark(
        db_pool, uid, entity_type="issue", entity_id=issue_id
    )
    assert created_again is False, "ครั้งที่สองต้องไม่ใช่ของใหม่"
    assert row_again["id"] == row["id"]


# ════════════════════════════════════════════════════════════
# 8) migration 021 — รันท้ายไฟล์โดยเจตนา (มัน DROP ตารางจริง)
# ════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_migration_021_creates_table_and_indexes(bm_world, db_pool):
    """B11 — จำลอง DB ที่ยังไม่มีตาราง → รัน `upgrade()` ตรง ๆ 2 ครั้ง → ได้ของครบ

    ⚠️ **รันท้ายไฟล์โดยเจตนา** เพราะมัน `DROP TABLE` ทิ้งแล้วสร้างใหม่ —
       `upgrade()` ต้องสร้างคืนครบทั้งตารางและ index ไม่งั้นเทสต์ไฟล์อื่นที่รันต่อจะพัง

    ⚠️ รัน `upgrade()` **สองครั้ง** เพื่อบังคับ idempotency ของทุกคำสั่ง DDL
       (`CREATE TABLE IF NOT EXISTS` · `CREATE INDEX IF NOT EXISTS`) — ถ้าลบ `IF NOT EXISTS`
       ตัวใดตัวหนึ่งออก รอบที่สองจะพังทันที
    """
    bm_world
    mig = importlib.import_module("migrations.021_bookmarks")

    async with db_pool.acquire() as conn:
        await conn.execute("DROP TABLE IF EXISTS bookmarks CASCADE")

        assert await conn.fetchval(
            "SELECT to_regclass('public.bookmarks') IS NULL"
        ) is True, "ต้องลบตารางได้จริงก่อนทดสอบ"

        await mig.upgrade(conn)
        await mig.upgrade(conn)  # idempotent

        assert await conn.fetchval(
            "SELECT to_regclass('public.bookmarks') IS NOT NULL"
        ) is True

        # index ของตารางใหม่ — unique คือหัวใจ ("อยู่ในชุดแล้วหรือยัง")
        indexes = {
            r["indexname"]
            for r in await conn.fetch(
                "SELECT indexname FROM pg_indexes WHERE tablename = 'bookmarks'"
            )
        }
        assert {"uq_bookmarks_user_entity", "idx_bookmarks_user_created"} <= indexes

        # ★ index ที่ migration เดียวกันนี้เพิ่มให้ตารางเดิม (ปิดช่อง C1/C3 seq scan)
        extras = {
            r["indexname"]
            for r in await conn.fetch(
                "SELECT indexname FROM pg_indexes WHERE tablename IN ('piri_votes','issue_comments')"
            )
        }
        assert {"idx_piri_votes_user", "idx_issue_comments_user"} <= extras

    # ⚠️ unique บังคับจริง — พิสูจน์ที่ระดับ DB ไม่ใช่เชื่อ service
    from asyncpg.exceptions import UniqueViolationError

    issue_id = await _issue(db_pool, bm_world)
    uid = bm_world["me"]["user_id"]
    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO bookmarks (user_id, entity_type, entity_id) VALUES ($1,'issue',$2)",
            uid, issue_id,
        )
        with pytest.raises(UniqueViolationError):
            await conn.execute(
                "INSERT INTO bookmarks (user_id, entity_type, entity_id) VALUES ($1,'issue',$2)",
                uid, issue_id,
            )
