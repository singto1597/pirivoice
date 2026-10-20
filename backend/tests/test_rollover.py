"""🔁 เลื่อนชั้นทั้งโรงเรียน (rollover) — P4

ทดสอบ 7 ระดับ:
  0) **helper บริสุทธิ์** — `target_room_code` / `classify_member` (ไม่ต้องมี DB)
  1) **preview** — ตัวเลขตรงกับโลกที่สร้างมือ และ **ไม่แตะข้อมูลสมาชิกเลย**
  2) **apply** — แถวใหม่เกิดจริง แถวเก่าถูกปิดจริง (deep-DB ทุกข้อ ไม่เชื่อ HTTP response)
  3) **invariant หลัง apply** — ไม่มี active ซ้อน · ประวัติไม่หาย · arbiter ของ index 028 ยังจริง
  4) **RBAC ยังชี้คนถูก** — คนที่มีทั้งแถว promoted และ active **ในห้องเดียวกัน** ต้องผ่าน
  5) **กันล็อกโรงเรียน** — ปีใหม่ไม่เหลือ `is_admin` → 400 และ **ไม่มีแถวไหนถูกแก้เลย**
  6) **ยิงพร้อมกัน** — apply สองคำขอด้วย `run_id` เดียว → สำเร็จ 1 อีกอัน 409
  7) **สิทธิ์/auth** — 401 · ครูทั่วไป/ประธานระดับ/สภานักเรียน 403 · ส่วนกลาง 200

⚠️ สองข้อที่แผนเดิมเขียนไว้ไม่ตรงกับข้อมูลจริง (เคาะกับเจ้าของระบบ 8 ต.ค. 2026):
   · `council_member`/`council_president` **ถูกยกเป็น `student`** (ไม่ใช่ "วาระหมดแล้วหายไป")
     เพราะข้อมูลจริงพบว่าทั้ง 23 คนมีแถวเดียว ⇒ ถ้าไม่ยกจะหายจากรายชื่อปีใหม่ทั้งหมด
   · `target_room_code()` สลับ token หน้า `/` — **ห้ามจับคู่ด้วย `room_number`** (เป็น NULL ทุกห้อง)

ตาม docs/rules/testing.md: ตรวจ DB ตรง ๆ ผ่าน `db_pool` ไม่เชื่อ HTTP response
"""
import asyncio
import json
import random

import pytest
import pytest_asyncio

from core.exceptions import ConflictError
from services import auth_service, rollover_service

# ============================================================
# โลกทดสอบ — สร้างมือ แล้ว assert ตัวเลขจากสิ่งที่สร้างจริง
# ============================================================
#
# ระดับชั้น → ห้องปลายทาง (สลับหัว token):
#   ม.1/1 → ม.2/1 ✓   ม.3/9 → ม.4/9 ✓   ม.4/8 → ม.5/8 ✓   ม.5/1 → ม.6/1 ✓
#   ม.6/1 → จบ
# ⇒ โลกนี้ **แมปครบ** ตอนแรก (can_apply = True)
#    เทสต์ที่ต้องทดสอบ "ห้องที่แมปไม่ได้" จะ soft-delete ห้องปลายทางเอาเอง
#    (เช่น ลบ ม.5/8 → ม.4/8 กลายเป็น unmapped) — สร้างสภาพจริงได้โดยไม่ต้องมีโลกที่สอง

_ROOMS = [
    ("ม.1/1", "ม.1"),
    ("ม.2/1", "ม.2"),
    ("ม.3/9", "ม.3"),
    ("ม.4/8", "ม.4"),
    ("ม.4/9", "ม.4"),
    ("ม.5/1", "ม.5"),
    ("ม.5/8", "ม.5"),
    ("ม.6/1", "ม.6"),
]

# (ห้อง, ตำแหน่ง) — ลำดับคงที่ เพื่อให้ assertions อ่านออก
_MEMBERS = [
    ("ม.1/1", "student"),
    ("ม.1/1", "student"),
    ("ม.1/1", "class_president"),
    ("ม.3/9", "student"),
    ("ม.3/9", "student"),
    ("ม.4/8", "student"),
    ("ม.4/8", "student"),
    ("ม.5/1", "student"),
    ("ม.5/1", "council_member"),
    ("ม.6/1", "student"),
    ("ม.6/1", "class_president"),
]

# (ตำแหน่ง, ห้อง) — `None` = ไม่มีห้อง (แบบเดียวกับ admin/ประธานสภาในข้อมูล production จริง)
_STAFF = [
    ("admin", None),
    ("teacher_council", "ม.1/1"),
    ("council_president", None),
]

# ---- ตัวเลขที่โลกนี้ต้องให้ (นับมือจากรายการข้างบน) ----
_TOTAL_ACTIVE = len(_MEMBERS) + len(_STAFF)          # 14
_GRADUATING = 2                                       # ม.6/1 สองคน (ไม่ใช่ staff)
_STAFF_CARRIED = 2                                    # admin + teacher_council
_PROMOTED = _TOTAL_ACTIVE - _GRADUATING - _STAFF_CARRIED   # 10
_POSITIONS_RESET = 1                                  # class_president ใน ม.1/1
_COUNCIL_LAPSING = 2                                  # council_member (ม.5/1) + council_president (ไม่มีห้อง)
_ROOMLESS = 1                                         # ประธานสภาที่ไม่มีห้อง

_NEXT_BE = 2570


@pytest_asyncio.fixture
async def rollover_world(db_pool, client):
    """ห้อง 8 ห้อง + สมาชิก 14 คน (นักเรียน/ตำแหน่ง/บุคลากร) + ปีปลายทางที่ยังว่าง

    ⚠️ รับ `client` โดยเจตนา — บังคับให้ TestClient เปิด app (รัน init_db + migrations)
       จบก่อน จึงค่อยใช้ตาราง (แบบเดียวกับ `year_world` ใน test_academic_years)
    """
    async with db_pool.acquire() as conn:
        # ⚠️ **ต้องล้างก่อนเสมอ**: `client` ทำให้ app เปิด → `seed_default_users()` ปลูกบัญชี
        #    กลาง 3 ใบ (admin / ครูสภา / ประธานสภา) พร้อม **แถวสมาชิกในปีปัจจุบัน**
        #    ⇒ ถ้าไม่ลบ โลกจะไม่ใช่ 14 คนที่สร้างมือ แต่เป็น 17 และตัวเลขทุกช่องเพี้ยน
        #    (แบบเดียวกับที่ test_academic_years.py:368 ทำเมื่อต้องการโลกที่ควบคุมได้)
        #    ลบแค่ `students` — บัญชี `users` ยังอยู่แต่ไม่มีสมาชิก ⇒ ไม่กวนเทสต์นี้
        await conn.execute("DELETE FROM students")

        rooms: dict[str, int] = {}
        for code, level in _ROOMS:
            rooms[code] = await conn.fetchval(
                "INSERT INTO rooms (room_code, room_name, level) VALUES ($1,$2,$3) RETURNING id",
                code, code, level,
            )
        to_year_id = await conn.fetchval(
            """
            INSERT INTO academic_years (year_be, name)
            VALUES ($1, $2) RETURNING id
            """,
            _NEXT_BE, f"ปีการศึกษา {_NEXT_BE}",
        )
        current = await conn.fetchrow(
            "SELECT id, year_be FROM academic_years WHERE is_current AND deleted_at IS NULL"
        )
    assert current is not None, "conftest ต้องปลูกปีปัจจุบันไว้เสมอ"

    users: dict[str, dict] = {}
    seq = 0
    # ⚠️ สองลิสต์เรียงคู่กลับกันโดยเจตนา (อ่านง่ายกว่าตอน assert) — ต้องพลิก `_STAFF` ก่อนรวม
    everyone = list(_MEMBERS) + [(room, role) for role, room in _STAFF]
    for room_code, role in everyone:
        seq += 1
        sid = f"RW{random.randint(10000, 99999)}{seq:02d}"  # ≤ 10 ตัว (student_id VARCHAR(10))
        uid = await auth_service.register_user(
            db_pool, f"rw_{role}_{seq}", "1234", f"{role} ทดสอบ", sid,
            room_code or "", seq, role,
        )
        # role ซ้ำกันมีหลายคน — เก็บ "คนแรกของแต่ละ role" ไว้เป็น actor
        users.setdefault(role, {"user_id": uid, "token": auth_service.create_access_token(uid)})

    return {
        "year_id": current["id"],
        "year_be": current["year_be"],
        "to_year_id": to_year_id,
        "to_year_be": _NEXT_BE,
        "rooms": rooms,
        "users": users,
    }


def _hdr(world, actor="admin") -> dict:
    return {"Authorization": f"Bearer {world['users'][actor]['token']}"}


def _url(path: str) -> str:
    return f"/api/rollover{path}"


# ============================================================
# helpers อ่าน DB ตรง (deep-DB verification)
# ============================================================

async def _student_rows(db_pool, year_id=None):
    async with db_pool.acquire() as conn:
        if year_id is None:
            rows = await conn.fetch("SELECT * FROM students ORDER BY id")
        else:
            rows = await conn.fetch(
                "SELECT * FROM students WHERE academic_year_id = $1 ORDER BY id", year_id
            )
    return [_decode_jsonb(dict(r)) for r in rows]


async def _active_rows(db_pool, year_id):
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT * FROM students
            WHERE academic_year_id = $1 AND status = 'active' AND deleted_at IS NULL
            ORDER BY id
            """,
            year_id,
        )
    return [_decode_jsonb(dict(r)) for r in rows]


async def _row_for(db_pool, year_id, user_id):
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM students WHERE academic_year_id = $1 AND user_id = $2",
            year_id, user_id,
        )
    return _decode_jsonb(dict(row)) if row else None


async def _year_flags(db_pool) -> dict:
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, is_current FROM academic_years WHERE deleted_at IS NULL"
        )
    return {r["id"]: r["is_current"] for r in rows}


async def _column_default(db_pool):
    """ค่า DEFAULT ของ `students.academic_year_id` (ข้อความดิบจาก pg_attrdef)"""
    async with db_pool.acquire() as conn:
        return await conn.fetchval(
            """
            SELECT pg_get_expr(d.adbin, d.adrelid)
            FROM pg_attrdef d
            JOIN pg_attribute a ON a.attrelid = d.adrelid AND a.attnum = d.adnum
            WHERE d.adrelid = 'students'::regclass AND a.attname = 'academic_year_id'
            """
        )


async def _runs(db_pool, run_id=None):
    async with db_pool.acquire() as conn:
        if run_id is not None:
            row = await conn.fetchrow("SELECT * FROM rollover_runs WHERE id = $1", run_id)
            return _decode_jsonb(dict(row)) if row else None
        return [_decode_jsonb(dict(r)) for r in await conn.fetch("SELECT * FROM rollover_runs ORDER BY id")]


_JSONB_COLUMNS = {"plan", "permissions", "responsibilities"}


def _decode_jsonb(row: dict) -> dict:
    """⚠️ asyncpg คืน `jsonb` เป็น **`str`** ⇒ ต้อง `json.loads` ก่อนใช้ (บทเรียนเดิมใน tests/test_events.py)"""
    for key in _JSONB_COLUMNS & row.keys():
        if isinstance(row[key], str):
            row[key] = json.loads(row[key])
    return row


async def _audit_actions(db_pool, run_id):
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT action FROM audit_logs
            WHERE entity_type = 'rollover_run' AND entity_id = $1
            ORDER BY created_at
            """,
            str(run_id),
        )
    return [r["action"] for r in rows]


def _preview(client, world, actor="admin", **payload_overrides):
    """`**payload_overrides` ใช้ได้ทั้งเขียนทับ `to_year_id` และส่ง `room_overrides={...}`"""
    payload = {"from_year_id": world["year_id"], "to_year_id": world["to_year_id"]}
    payload.update(payload_overrides)
    return client.post(_url("/preview"), json=payload, headers=_hdr(world, actor))


def _apply(client, world, run_id, actor="admin", room_overrides=None):
    return client.post(
        _url("/apply"),
        json={"run_id": run_id, "room_overrides": room_overrides or {}},
        headers=_hdr(world, actor),
    )


async def _preview_and_apply(client, world, *, actor="admin", room_overrides=None):
    """ทางเดินปกติ: preview → apply (คืน response ของ apply)"""
    res = _preview(client, world, actor=actor)
    assert res.status_code == 200, res.text
    return _apply(client, world, res.json()["run_id"], actor=actor, room_overrides=room_overrides)


async def _soft_delete_room(db_pool, code: str):
    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE rooms SET deleted_at = NOW() WHERE room_code = $1", code
        )


# ============================================================
# 0) helper บริสุทธิ์ — ไม่ต้องมี DB
# ============================================================

@pytest.mark.parametrize("room_code,expected", [
    ("ม.4/1", "ม.5/1"),        # เลื่อนขึ้นหนึ่งระดับ
    ("ม.1/14", "ม.2/14"),      # เลขห้องหลายหลัก
    ("ม.3/14", "ม.4/14"),      # ⚠️ เคสจริงบน production: ม.3/14 มี 40 คน แต่ ม.4/14 ไม่มี
    ("ม.6/3", None),           # ม.6 → จบ (ไม่สร้างแถวใหม่)
    ("ม.7/1", None),           # ระดับที่ไม่รู้จัก — ห้ามเดา
    ("A101", None),            # ไม่มี `/` → แยกหัว/ท้ายไม่ได้
    ("ม.4/", None),            # ท้ายว่าง
    ("/1", None),              # หัวว่าง
    (None, None),
    ("", None),
])
def test_target_room_code(room_code, expected):
    """สลับ **หัว token** หน้า `/` เท่านั้น — ห้ามใช้ `rooms.room_number` (เป็น NULL ทุกห้องจริง)"""
    assert rollover_service.target_room_code(room_code) == expected


@pytest.mark.parametrize("room_code,head,tail", [
    ("ม.3/14", "ม.3", "14"),
    ("ม.6/1", "ม.6", "1"),
    ("A101", None, None),
    (None, None, None),
])
def test_room_head_and_tail(room_code, head, tail):
    assert rollover_service.room_head(room_code) == head
    assert rollover_service.room_tail(room_code) == tail


@pytest.mark.parametrize("role,room_code,expected", [
    ("student", "ม.1/1", "promote"),
    ("class_president", "ม.1/1", "promote"),
    ("council_president", "ม.5/1", "promote"),      # ตำแหน่งระดับโรงเรียน → ยกเป็น student
    ("student", "ม.6/1", "graduate"),
    ("class_president", "ม.6/1", "graduate"),       # ตำแหน่งไม่กันจบ
    ("admin", None, "staff"),
    ("teacher_council", "ม.6/1", "staff"),          # ⚠️ staff มาก่อน "จบ" — ครูไม่จบ
    ("teacher", "ม.1/1", "staff"),
    (None, "ม.1/1", "promote"),                     # class_role ว่าง = student (default ของคอลัมน์)
    ("student", None, "promote"),                   # ไม่มีห้อง → ยกไปแบบไม่มีห้อง
])
def test_classify_member(role, room_code, expected):
    """ลำดับสำคัญ: staff → จบ → เลื่อน · ครูในห้อง ม.6 ต้องถูกยก ไม่ใช่จบ"""
    assert rollover_service.classify_member(role, room_code) == expected


# ============================================================
# 1) PREVIEW
# ============================================================

@pytest.mark.asyncio
async def test_preview_counts_match_hand_built_world(client, rollover_world, db_pool):
    """ตัวเลขทุกช่องตรงกับโลกที่สร้างมือ — และ `can_apply` เป็นจริงเพราะแมปครบ"""
    res = _preview(client, rollover_world)
    assert res.status_code == 200, res.text
    body = res.json()

    assert body["can_apply"] is True, body["blockers"]
    assert body["blockers"] == []
    assert body["total_active"] == _TOTAL_ACTIVE

    assert body["promoted"]["count"] == _PROMOTED
    assert body["graduating"]["count"] == _GRADUATING
    assert body["staff_carried"] == {"count": _STAFF_CARRIED, "by_role": {"admin": 1, "teacher_council": 1}}
    assert body["positions_reset"] == {"count": _POSITIONS_RESET, "by_role": {"class_president": 1}}
    assert body["council_lapsing"] == {
        "count": _COUNCIL_LAPSING,
        "by_role": {"council_member": 1, "council_president": 1},
    }
    assert body["roomless"] == {"count": _ROOMLESS, "by_role": {"council_president": 1}}

    assert body["from_year"]["id"] == rollover_world["year_id"]
    assert body["to_year"]["id"] == rollover_world["to_year_id"]
    assert body["unmapped"] == []

    # by_level: เรียงตามระดับ และจำนวนรวมต้องเท่ากับ promoted ลบคนที่ไม่มีห้อง
    levels = {g["level"]: g for g in body["by_level"]}
    assert list(levels) == ["ม.1", "ม.3", "ม.4", "ม.5"]
    assert levels["ม.1"]["target_level"] == "ม.2"
    assert levels["ม.5"]["target_level"] == "ม.6"
    assert sum(g["student_count"] for g in body["by_level"]) == _PROMOTED - _ROOMLESS

    room_map = {
        r["from_room_code"]: r["to_room_code"]
        for g in body["by_level"] for r in g["rooms"]
    }
    assert room_map == {
        "ม.1/1": "ม.2/1", "ม.3/9": "ม.4/9", "ม.4/8": "ม.5/8", "ม.5/1": "ม.6/1",
    }
    assert all(r["status"] == "ok" for g in body["by_level"] for r in g["rooms"])
    assert body["graduating"]["rooms"] == [{"room_code": "ม.6/1", "student_count": 2}]

    # คำเตือนเรื่องคนไม่มีห้องต้องโผล่ (ไม่บล็อก แต่ต้องเห็น)
    assert any("ไม่มีห้อง" in w for w in body["warnings"])


@pytest.mark.asyncio
async def test_preview_does_not_touch_member_rows(client, rollover_world, db_pool):
    """🔴 preview ต้อง **ไม่แก้ข้อมูลสมาชิกเลย** — snapshot ทั้งตารางเทียบก่อน/หลัง"""
    before = await _student_rows(db_pool)
    default_before = await _column_default(db_pool)
    flags_before = await _year_flags(db_pool)

    assert _preview(client, rollover_world).status_code == 200

    assert await _student_rows(db_pool) == before, "preview ห้ามแตะแถวสมาชิก"
    assert await _column_default(db_pool) == default_before, "preview ห้ามแตะ DEFAULT"
    assert await _year_flags(db_pool) == flags_before, "preview ห้ามสลับปีปัจจุบัน"


@pytest.mark.asyncio
async def test_preview_writes_previewed_run_with_plan(client, rollover_world, db_pool):
    """preview บันทึกแถว `PREVIEWED` + plan เต็ม ⇒ เป็นหลักฐานว่า "ตอนนั้นเห็นอะไร" """
    run_id = _preview(client, rollover_world).json()["run_id"]

    run = await _runs(db_pool, run_id)
    assert run is not None
    assert run["status"] == "PREVIEWED"
    assert run["from_year_id"] == rollover_world["year_id"]
    assert run["to_year_id"] == rollover_world["to_year_id"]
    assert run["applied_at"] is None
    assert run["promoted_count"] == _PROMOTED
    assert run["graduated_count"] == _GRADUATING
    assert run["staff_carried_count"] == _STAFF_CARRIED
    assert run["positions_reset_count"] == _POSITIONS_RESET
    assert run["plan"]["can_apply"] is True
    assert run["plan"]["by_level"], "plan ต้องเก็บรายละเอียดต่อระดับไว้ด้วย"
    assert await _audit_actions(db_pool, run_id) == ["PREVIEW_ROLLOVER"]


@pytest.mark.asyncio
async def test_preview_is_repeatable(client, rollover_world, db_pool):
    """เรียก preview ซ้ำได้ไม่จำกัด — ได้ run ใหม่ทุกครั้ง (ไม่ทับของเดิม)"""
    first = _preview(client, rollover_world).json()["run_id"]
    second = _preview(client, rollover_world).json()["run_id"]
    assert first != second
    assert len(await _runs(db_pool)) == 2


@pytest.mark.asyncio
async def test_preview_blocks_when_target_room_missing(client, rollover_world, db_pool):
    """⚠️ ห้องที่ไม่มีปลายทาง → **บล็อก ห้ามเดา** (เคสจริง: ม.3/14 มี 40 คน แต่ ม.4/14 ไม่มี)

    ที่นี่จำลองด้วยการ soft-delete ห้องปลายทาง `ม.5/8` ⇒ `ม.4/8` กลายเป็น unmapped
    """
    await _soft_delete_room(db_pool, "ม.5/8")

    body = _preview(client, rollover_world).json()
    assert body["can_apply"] is False
    assert any("ห้องปลายทาง" in b for b in body["blockers"]), body["blockers"]

    assert len(body["unmapped"]) == 1
    entry = body["unmapped"][0]
    assert entry["from_room_code"] == "ม.4/8"
    assert entry["level"] == "ม.4"
    assert entry["student_count"] == 2
    assert "ม.5/8" in entry["reason"]

    group = {g["level"]: g for g in body["by_level"]}["ม.4"]
    # ⚠️ `by_level` จัดกลุ่มตาม **ห้องต้นทาง** ไม่ใช่ห้องปลายทาง ⇒ `ม.4/9` ไม่โผล่ที่นี่
    #    เพราะเป็นห้องว่าง (มีแต่ปลายทางของ ม.3/9) — คน ม.4 อยู่ห้องเดียวคือ ม.4/8
    assert group["unmapped_rooms"] == 1 and group["mapped_rooms"] == 0
    statuses = {r["from_room_code"]: r["status"] for r in group["rooms"]}
    assert statuses == {"ม.4/8": "unmapped"}


@pytest.mark.parametrize("reason_key,mutate", [
    ("ปีเดียวกัน", lambda w, c: _preview(c, w, to_year_id=w["year_id"])),
    ("ไม่ใช่ปีปัจจุบัน", None),   # เตรียมสภาพในเทสต์ (ต้องรอ DB)
])
@pytest.mark.asyncio
async def test_preview_blockers(client, rollover_world, db_pool, reason_key, mutate):
    """blocker ที่เหลือ — ปีเดียวกัน และปีต้นทางไม่ใช่ปีปัจจุบัน"""
    if mutate is not None:
        res = mutate(rollover_world, client)
    else:
        # ย้าย "ปีปัจจุบัน" ไปปีปลายทางตรง ๆ ที่ DB (เลี่ยงด่านของ year_service ที่ต้องมีสมาชิก)
        async with db_pool.acquire() as conn:
            await conn.execute(
                "UPDATE academic_years SET is_current = FALSE WHERE id = $1",
                rollover_world["year_id"],
            )
            await conn.execute(
                "UPDATE academic_years SET is_current = TRUE WHERE id = $1",
                rollover_world["to_year_id"],
            )
        res = _preview(client, rollover_world)

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["can_apply"] is False
    assert any(reason_key in b for b in body["blockers"]), body["blockers"]


@pytest.mark.asyncio
async def test_preview_blocks_when_target_year_not_empty(client, rollover_world, db_pool):
    """ปีปลายทางมีคนอยู่แล้ว → บล็อก (การเลื่อนชั้นต้องทำลงปีที่ว่าง)"""
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO students (room_id, class_role, status, academic_year_id)
            VALUES ($1, 'student', 'active', $2)
            """,
            rollover_world["rooms"]["ม.2/1"], rollover_world["to_year_id"],
        )

    body = _preview(client, rollover_world).json()
    assert body["can_apply"] is False
    assert any("มีสมาชิกอยู่แล้ว" in b for b in body["blockers"]), body["blockers"]


# ============================================================
# 2) APPLY
# ============================================================

@pytest.mark.asyncio
async def test_apply_refuses_while_unmapped_and_changes_nothing(
    client, rollover_world, db_pool
):
    """ยิง apply ทั้งที่ยังแมปไม่ครบ → 400 และ **ไม่มีแถวไหนถูกแก้เลย**"""
    await _soft_delete_room(db_pool, "ม.5/8")
    run_id = _preview(client, rollover_world).json()["run_id"]

    before = await _student_rows(db_pool)
    default_before = await _column_default(db_pool)

    res = _apply(client, rollover_world, run_id)
    assert res.status_code == 400, res.text
    assert "ม.4/8" in res.json()["detail"]

    assert await _student_rows(db_pool) == before
    assert await _column_default(db_pool) == default_before
    assert (await _runs(db_pool, run_id))["status"] == "PREVIEWED", "รอบที่ล้มต้องไม่ถูกปิดเป็น APPLIED"


@pytest.mark.asyncio
async def test_apply_creates_new_rows_and_closes_old_ones(client, rollover_world, db_pool):
    """🔑 หัวใจ: แถวใหม่เกิดในปีใหม่ + แถวเก่าถูกปิด (deep-DB)"""
    res = await _preview_and_apply(client, rollover_world)
    assert res.status_code == 200, res.text
    body = res.json()

    assert body["promoted_count"] == _PROMOTED
    assert body["graduated_count"] == _GRADUATING
    assert body["staff_carried_count"] == _STAFF_CARRIED
    assert body["closed_count"] == _TOTAL_ACTIVE

    old = await _student_rows(db_pool, rollover_world["year_id"])
    new = await _student_rows(db_pool, rollover_world["to_year_id"])

    # แถวเก่า: ไม่ถูกลบ แต่ไม่มี active เหลือแล้ว
    assert len(old) == _TOTAL_ACTIVE
    assert all(r["deleted_at"] is None for r in old), "ต้องเป็น soft-history ไม่ใช่ลบ"
    assert all(r["status"] != "active" for r in old)
    # ⚠️ `promoted` ของปีเก่า = ทุกคนที่ "ไม่จบ" **รวมบุคลากรด้วย** (ครูก็ถูกยกไปปีใหม่
    #    ⇒ แถวปีเก่าของครูต้องไม่ค้างเป็น active ไม่งั้น RBAC จะเห็นครูคนเดิมสองปี)
    #    ต่างจาก `promoted_count` ของผลลัพธ์ที่เป็น "จำนวนแถวใหม่ที่สร้าง" (นักเรียนล้วน)
    assert sum(1 for r in old if r["status"] == "promoted") == _PROMOTED + _STAFF_CARRIED
    assert sum(1 for r in old if r["status"] == "graduated") == _GRADUATING

    # แถวใหม่: active ทุกแถว และอยู่ปีใหม่เท่านั้น
    assert len(new) == _PROMOTED + _STAFF_CARRIED
    assert all(r["status"] == "active" for r in new)
    assert all(r["deleted_at"] is None for r in new)

    # ห้องปลายทางถูกต้องตามการสลับ token
    # ⚠️ ประธานสภาที่ไม่มีห้องถูกยกไปเป็น `student` + `room_id IS NULL` ⇒ ต้องแยกนับ
    #    (ถ้าไม่กัน `None` จะ KeyError — และถ้ากรองด้วย `class_role='student'` เฉย ๆ
    #     แถวนั้นจะถูกนับเป็น "นักเรียนที่มีห้อง" ซึ่งไม่จริง)
    rooms_by_id = {v: k for k, v in rollover_world["rooms"].items()}
    landed: dict = {}
    roomless_promoted = 0
    for row in new:
        if row["class_role"] != "student":
            continue
        if row["room_id"] is None:
            roomless_promoted += 1
        else:
            code = rooms_by_id[row["room_id"]]
            landed[code] = landed.get(code, 0) + 1
    assert landed == {"ม.2/1": 3, "ม.4/9": 2, "ม.5/8": 2, "ม.6/1": 2}
    assert roomless_promoted == _ROOMLESS
    assert sum(landed.values()) + roomless_promoted == _PROMOTED


@pytest.mark.asyncio
async def test_apply_graduates_only_m6(client, rollover_world, db_pool):
    """ม.6 → `graduated` และ **ไม่มีแถวใหม่ในปีใหม่** (คนอื่นเป็น promoted)"""
    await _preview_and_apply(client, rollover_world)

    m6_room = rollover_world["rooms"]["ม.6/1"]
    async with db_pool.acquire() as conn:
        old_m6 = await conn.fetch(
            "SELECT user_id FROM students WHERE room_id = $1 AND academic_year_id = $2",
            m6_room, rollover_world["year_id"],
        )
        new_ids = {
            r["user_id"]
            for r in await conn.fetch(
                "SELECT user_id FROM students WHERE academic_year_id = $1",
                rollover_world["to_year_id"],
            )
        }
    assert len(old_m6) == 2
    for row in old_m6:
        assert row["user_id"] not in new_ids, "เด็ก ม.6 ต้องไม่ถูกยกไปปีใหม่"


@pytest.mark.asyncio
async def test_apply_carries_staff_with_role_permissions_and_room(
    client, rollover_world, db_pool
):
    """บุคลากรยกไป **บทบาท/สิทธิ์/ห้องเดิม** และแถวใหม่ต้องเหมือนเดิมทุกช่องที่มีความหมาย"""
    await _preview_and_apply(client, rollover_world)

    for label in ("admin", "teacher_council"):
        uid = rollover_world["users"][label]["user_id"]
        before = await _row_for(db_pool, rollover_world["year_id"], uid)
        after = await _row_for(db_pool, rollover_world["to_year_id"], uid)

        assert after is not None, f"{label} ต้องถูกยกไปปีใหม่"
        assert after["status"] == "active"
        assert after["class_role"] == before["class_role"] == label
        assert after["is_admin"] is True
        assert after["permissions"] == before["permissions"], "สิทธิ์ต้องยกมาเหมือนเดิม"
        assert after["room_id"] == before["room_id"], "ห้องต้องยกมาเหมือนเดิม"
        # แถวเก่าของคนเดียวกันยังอยู่ (เป็นประวัติ)
        assert before["status"] == "promoted"


@pytest.mark.asyncio
async def test_apply_resets_elected_positions_to_student(client, rollover_world, db_pool):
    """ตำแหน่งเลือกตั้งวาระหมด → แถวใหม่เป็น `student` (ไม่ใช่ตำแหน่งเดิม) + สิทธิ์ของ student

    ⚠️ **รวม `council_member`/`council_president` ด้วย** — มติเจ้าของระบบ 8 ต.ค. 2026:
       คนกลุ่มนี้มีแถวเดียวในปีนี้ ⇒ ถ้าไม่ยกเป็น student จะหายจากรายชื่อปีใหม่ทั้งหมด
    """
    await _preview_and_apply(client, rollover_world)

    student_perms = auth_service.get_role_permissions("student")
    for label in ("class_president", "council_member", "council_president"):
        uid = rollover_world["users"][label]["user_id"]
        before = await _row_for(db_pool, rollover_world["year_id"], uid)
        after = await _row_for(db_pool, rollover_world["to_year_id"], uid)

        assert before["class_role"] == label
        assert after is not None, f"{label} ต้องไม่หายไปจากปีใหม่"
        assert after["class_role"] == "student", f"{label} ต้องกลายเป็น student"
        assert after["permissions"] == student_perms
        assert after["is_admin"] is False
        assert after["responsibilities"] == []
        assert after["staff_level"] is None


@pytest.mark.asyncio
async def test_apply_keeps_roomless_members_with_null_room(client, rollover_world, db_pool):
    """คนที่ไม่มีห้องถูกยกไปโดย `room_id = NULL` — **ไม่ใช่หายไป** (เคสจริง: ประธานสภาที่ไม่มีห้อง)"""
    await _preview_and_apply(client, rollover_world)

    uid = rollover_world["users"]["council_president"]["user_id"]
    after = await _row_for(db_pool, rollover_world["to_year_id"], uid)
    assert after is not None
    assert after["room_id"] is None
    assert after["class_role"] == "student"
    assert after["status"] == "active"


@pytest.mark.asyncio
async def test_apply_sets_new_year_current_and_flips_default(client, rollover_world, db_pool):
    """ตั้งปีใหม่เป็นปัจจุบัน + DEFAULT ของ `students.academic_year_id` ชี้ปีใหม่

    ⚠️ ขั้นนี้เกิด **หลัง** สร้างสมาชิกแล้วเท่านั้น (สลับลำดับ = รายชื่อทั้งโรงเรียนหายวับ)
    """
    assert await _column_default(db_pool) == str(rollover_world["year_id"])

    await _preview_and_apply(client, rollover_world)

    flags = await _year_flags(db_pool)
    assert sum(flags.values()) == 1
    assert flags[rollover_world["to_year_id"]] is True
    assert flags[rollover_world["year_id"]] is False
    assert await _column_default(db_pool) == str(rollover_world["to_year_id"])

    # พิสูจน์ปลายทางจริง: insert โดยไม่ระบุปี → ไปลงปีใหม่ และได้สิทธิ์จากปีใหม่
    async with db_pool.acquire() as conn:
        landed = await conn.fetchval(
            """
            INSERT INTO students (room_id, class_role, status)
            VALUES ($1, 'student', 'active') RETURNING academic_year_id
            """,
            rollover_world["rooms"]["ม.2/1"],
        )
    assert landed == rollover_world["to_year_id"]


@pytest.mark.asyncio
async def test_apply_closes_run_and_writes_audit(client, rollover_world, db_pool):
    """รอบถูกปิดเป็น `APPLIED` + เก็บแผนที่ใช้จริง + audit ใน transaction เดียว"""
    res = await _preview_and_apply(client, rollover_world)
    run_id = res.json()["run_id"]

    run = await _runs(db_pool, run_id)
    assert run["status"] == "APPLIED"
    assert run["applied_at"] is not None
    assert run["promoted_count"] == _PROMOTED
    assert run["graduated_count"] == _GRADUATING
    assert run["unmapped_count"] == 0
    # เก็บทั้ง "ที่ preview ไว้" และ "ที่ทำจริง"
    assert set(run["plan"]) == {"preview", "applied", "room_overrides"}
    assert run["plan"]["applied"]["promoted"]["count"] == _PROMOTED

    assert await _audit_actions(db_pool, run_id) == ["PREVIEW_ROLLOVER", "APPLY_ROLLOVER"]


@pytest.mark.asyncio
async def test_apply_twice_second_is_409(client, rollover_world, db_pool):
    """ยิง apply ด้วย `run_id` เดิมซ้ำ → 409 (รอบถูกใช้ไปแล้ว) และข้อมูลไม่ถูกแตะรอบสอง"""
    first = await _preview_and_apply(client, rollover_world)
    assert first.status_code == 200, first.text
    run_id = first.json()["run_id"]

    snapshot = await _student_rows(db_pool)
    second = _apply(client, rollover_world, run_id)
    assert second.status_code == 409, second.text
    assert "ถูกใช้ไปแล้ว" in second.json()["detail"]
    assert await _student_rows(db_pool) == snapshot


@pytest.mark.asyncio
async def test_apply_unknown_run_404(client, rollover_world):
    assert _apply(client, rollover_world, 99999999).status_code == 404


# ============================================================
# 3) ROOM OVERRIDES — ทางเดียวที่ผู้ใช้ระบุห้องปลายทางเอง
# ============================================================

@pytest.mark.asyncio
async def test_apply_with_room_override_resolves_unmapped(client, rollover_world, db_pool):
    """`ม.4/8` ไม่มีปลายทาง → override ไป `ม.5/1` (ห้องที่มีอยู่จริง) → เลื่อนได้ครบ

    ⚠️ `ม.5/1` ในปีใหม่ว่าง (คนเดิมย้ายไป ม.6/1 แล้ว) ⇒ ไม่ทับกัน
    """
    await _soft_delete_room(db_pool, "ม.5/8")
    res = await _preview_and_apply(
        client, rollover_world, room_overrides={"ม.4/8": "ม.5/1"}
    )
    assert res.status_code == 200, res.text
    assert res.json()["room_overrides"] == {"ม.4/8": "ม.5/1"}

    async with db_pool.acquire() as conn:
        landed = await conn.fetchval(
            """
            SELECT COUNT(*) FROM students
            WHERE academic_year_id = $1 AND room_id = $2 AND status = 'active'
            """,
            rollover_world["to_year_id"], rollover_world["rooms"]["ม.5/1"],
        )
    assert landed == 2, "สองคนจาก ม.4/8 ต้องไปอยู่ ม.5/1"

    run = await _runs(db_pool, res.json()["run_id"])
    assert run["plan"]["room_overrides"] == {"ม.4/8": "ม.5/1"}
    # แผนที่บันทึกต้องสะท้อนผลหลังใช้ override (ไม่ใช่สถานะก่อนแก้)
    assert run["plan"]["applied"]["unmapped"] == []


@pytest.mark.asyncio
async def test_apply_override_to_unknown_room_400(client, rollover_world, db_pool):
    """override ไปห้องที่ไม่มีอยู่จริง → 400 และไม่สร้างห้องใหม่ให้"""
    await _soft_delete_room(db_pool, "ม.5/8")
    run_id = _preview(client, rollover_world).json()["run_id"]

    before = await _student_rows(db_pool)
    res = _apply(client, rollover_world, run_id, room_overrides={"ม.4/8": "ม.9/99"})
    assert res.status_code == 400, res.text
    assert "ม.9/99" in res.json()["detail"]

    async with db_pool.acquire() as conn:
        created = await conn.fetchval(
            "SELECT COUNT(*) FROM rooms WHERE room_code = $1", "ม.9/99"
        )
    assert created == 0, "ห้ามสร้างห้องใหม่ให้เอง"
    assert await _student_rows(db_pool) == before


@pytest.mark.asyncio
async def test_apply_override_merging_rooms_with_duplicate_student_id_400(
    client, rollover_world, db_pool
):
    """⚠️ ยุบสองห้องเป็นห้องเดียวแล้ว **เลขประจำตัวนักเรียนซ้ำ** → 400 ก่อนชน unique index 028

    ถ้าไม่ดักไว้ จะได้ `UniqueViolationError` กลาง transaction = 500 ที่อ่านไม่ออก
    (เกิดได้จริงเฉพาะเมื่อมี override — การเลื่อนชั้นปกติไม่ยุบห้อง)
    """
    room_id = rollover_world["rooms"]["ม.4/8"]           # มีนักเรียนอยู่แล้ว 2 คน
    extra_room = await _insert_room(db_pool, "ม.4/7", "ม.4")  # ปลายทาง ม.5/7 ไม่มี → unmapped

    dup_sid = "DUP0001"
    await auth_service.register_user(
        db_pool, "rw_dup_1", "1234", "ซ้ำ หนึ่ง", dup_sid, "ม.4/7", 91, "student"
    )
    await auth_service.register_user(
        db_pool, "rw_dup_2", "1234", "ซ้ำ สอง", dup_sid, "ม.4/8", 92, "student"
    )
    assert extra_room and room_id

    await _soft_delete_room(db_pool, "ม.5/8")            # ทำให้ ม.4/8 unmapped ด้วย
    run_id = _preview(client, rollover_world).json()["run_id"]
    before = await _student_rows(db_pool)

    res = _apply(
        client, rollover_world, run_id,
        room_overrides={"ม.4/7": "ม.4/9", "ม.4/8": "ม.4/9"},
    )
    assert res.status_code == 400, res.text
    assert "ซ้ำ" in res.json()["detail"]
    assert await _student_rows(db_pool) == before


@pytest.mark.asyncio
async def test_preview_with_override_flips_can_apply_to_true(
    client, rollover_world, db_pool
):
    """🔑 หัวใจของ wizard: เลือกห้องปลายทาง → **preview ซ้ำ** → `can_apply` กลับมาเป็นจริง

    ถ้า preview ไม่รับ `room_overrides` ผู้ใช้จะไม่มีทางรู้ว่าเลือกถูกหรือยังจนกว่าจะกด apply
    (ซึ่งเป็นปุ่มที่เขียนข้อมูลหลายพันแถว)
    """
    await _soft_delete_room(db_pool, "ม.5/8")

    before = _preview(client, rollover_world).json()
    assert before["can_apply"] is False
    assert before["unmapped"][0]["from_room_code"] == "ม.4/8"

    after = _preview(client, rollover_world, room_overrides={"ม.4/8": "ม.5/1"}).json()
    assert after["can_apply"] is True, after["blockers"]
    assert after["unmapped"] == []
    assert after["blockers"] == []

    # แผนที่ผู้ใช้เห็นต้องสะท้อนห้องที่เลือกแล้ว — ไม่ใช่สถานะก่อนแก้
    group = {g["level"]: g for g in after["by_level"]}["ม.4"]
    assert {r["from_room_code"]: r["to_room_code"] for r in group["rooms"]} == {"ม.4/8": "ม.5/1"}
    assert group["mapped_rooms"] == 1 and group["unmapped_rooms"] == 0

    # และแถวประวัติของรอบนั้นเก็บ override ที่ใช้ตอน preview ไว้ด้วย
    run = await _runs(db_pool, after["run_id"])
    assert run["plan"]["room_overrides"] == {"ม.4/8": "ม.5/1"}


@pytest.mark.asyncio
async def test_preview_blocks_duplicate_student_id_from_override(
    client, rollover_world, db_pool
):
    """เลขประจำตัวซ้ำ (เพราะ override ยุบสองห้อง) → **blocker ตั้งแต่ preview** ไม่ใช่ warning

    🔴 `apply` จะ `raise` 400 ทันทีที่เจอเลขซ้ำ ⇒ ถ้า preview บอกแค่ "ควรดู" แล้วกดได้
       ผู้ใช้จะเจอทางตันที่ระบบเตือนไว้แล้วแต่ไม่หยุด — ขัดกับสัญญาของ `can_apply`

    ⚠️ เคสนี้ **เกิดได้เฉพาะเมื่อมี override** — การแมปอัตโนมัติสลับแค่หัวรหัสห้อง
       (`ม.4/8` → `ม.5/8`) ⇒ ห้องต่างกันไม่มีทางยุบรวมกันเอง
    """
    await _insert_room(db_pool, "ม.4/7", "ม.4")
    await auth_service.register_user(
        db_pool, "rw_dup_3", "1234", "ซ้ำ สาม", "DUP0002", "ม.4/7", 93, "student"
    )
    await auth_service.register_user(
        db_pool, "rw_dup_4", "1234", "ซ้ำ สี่", "DUP0002", "ม.4/8", 94, "student"
    )
    await _soft_delete_room(db_pool, "ม.5/8")   # ทำให้ ม.4/8 ต้อง override เองด้วย

    overrides = {"ม.4/7": "ม.4/9", "ม.4/8": "ม.4/9"}
    body = _preview(client, rollover_world, room_overrides=overrides).json()

    assert body["can_apply"] is False
    assert body["unmapped"] == [], "แก้ห้องครบแล้ว — เหลือปัญหาเดียวคือเลขซ้ำ"
    assert any("DUP0002" in b for b in body["blockers"]), body["blockers"]

    # และกดจริงก็ยังต้อง 400 (ด่านสุดท้าย) + ไม่มีแถวถูกแตะ
    before = await _student_rows(db_pool)
    res = _apply(client, rollover_world, body["run_id"], room_overrides=overrides)
    assert res.status_code == 400, res.text
    assert "DUP0002" in res.json()["detail"]
    assert await _student_rows(db_pool) == before


async def _insert_room(db_pool, code: str, level: str) -> int:
    async with db_pool.acquire() as conn:
        return await conn.fetchval(
            "INSERT INTO rooms (room_code, room_name, level) VALUES ($1,$2,$3) RETURNING id",
            code, code, level,
        )


# ============================================================
# 4) 🛡️ กันล็อกโรงเรียน
# ============================================================

@pytest.mark.asyncio
async def test_apply_guard_refuses_when_no_admin_left(client, rollover_world, db_pool):
    """🔴 ปีใหม่ไม่เหลือ `is_admin` → 400 และ **ไม่มีแถวไหนถูกแก้เลย**

    สร้างสภาพจริงที่อันตราย: โรงเรียนมีแค่ "ประธานสภา" เป็นผู้ดูแล (ไม่มี admin/ครูสภา)
    ⇒ พอเลื่อนชั้น ประธานสภาถูกยกเป็น `student` + `is_admin=FALSE` ⇒ ปีใหม่ไม่มีแอดมินเลย
       และสิทธิ์ทั้งระบบอ่านจากตารางนี้ ⇒ ไม่มีใครตั้งค่าอะไรได้อีกตลอดไป

    (production จริงมี admin + teacher_council เป็น staff ⇒ ด่านนี้ไม่ยิง — แต่ยิงได้จริง
     ถ้าโรงเรียนเหลือแค่ประธานสภา ซึ่งเป็นสภาพที่เกิดได้จากการนำเข้าข้อมูล)
    """
    async with db_pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM students WHERE class_role IN ('admin','teacher_council')"
        )

    actor = "council_president"
    run_id = _preview(client, rollover_world, actor=actor).json()["run_id"]
    before = await _student_rows(db_pool)
    default_before = await _column_default(db_pool)

    res = _apply(client, rollover_world, run_id, actor=actor)
    assert res.status_code == 400, res.text
    assert "ผู้ดูแลระบบ" in res.json()["detail"]

    assert await _student_rows(db_pool) == before, "ห้ามมีแถวถูกแก้แม้แต่แถวเดียว"
    assert await _column_default(db_pool) == default_before, "ห้ามสลับ DEFAULT"
    assert (await _runs(db_pool, run_id))["status"] == "PREVIEWED"


@pytest.mark.asyncio
async def test_apply_guard_warning_is_not_needed_when_staff_exist(
    client, rollover_world, db_pool
):
    """เทียบกัน: โลกที่มี admin/ครูสภา (ค่าเริ่มต้น) → ผ่าน เพราะ staff ถูกยกไปพร้อม is_admin"""
    assert (await _preview_and_apply(client, rollover_world)).status_code == 200

    async with db_pool.acquire() as conn:
        admins = await conn.fetchval(
            """
            SELECT COUNT(*) FROM students
            WHERE academic_year_id = $1 AND status = 'active' AND is_admin
            """,
            rollover_world["to_year_id"],
        )
    assert admins == 2, "admin + teacher_council"


# ============================================================
# 5) INVARIANT หลัง apply
# ============================================================

@pytest.mark.asyncio
async def test_no_duplicate_active_rows_per_user_per_year(client, rollover_world, db_pool):
    """④ คนหนึ่งมี active ได้ปีละ 1 แถว — ตรวจตรงที่ DB หลัง apply"""
    await _preview_and_apply(client, rollover_world)

    async with db_pool.acquire() as conn:
        dupes = await conn.fetch(
            """
            SELECT user_id, academic_year_id FROM students
            WHERE deleted_at IS NULL AND status = 'active'
            GROUP BY 1, 2 HAVING COUNT(*) > 1
            """
        )
    assert dupes == [], f"มี active ซ้อน: {[dict(d) for d in dupes]}"


@pytest.mark.asyncio
async def test_unique_index_arbiter_holds_after_apply(client, rollover_world, db_pool):
    """arbiter ของ `uq_students_room_year_student` (028) — ต้องไม่มีคีย์ซ้ำหลัง apply"""
    await _preview_and_apply(client, rollover_world)

    async with db_pool.acquire() as conn:
        dupes = await conn.fetch(
            """
            SELECT room_id, academic_year_id, student_id FROM students
            WHERE deleted_at IS NULL
            GROUP BY 1, 2, 3 HAVING COUNT(*) > 1
            """
        )
    assert dupes == []


@pytest.mark.asyncio
async def test_history_of_old_year_is_queryable(client, rollover_world, db_pool):
    """③ ประวัติไม่หาย — ย้อนดู "ปีก่อนใครอยู่ห้องไหน ตำแหน่งอะไร" ได้จากแถวเดิม"""
    await _preview_and_apply(client, rollover_world)

    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT s.class_role, r.room_code, s.status
            FROM students s JOIN rooms r ON r.id = s.room_id
            WHERE s.academic_year_id = $1 AND s.deleted_at IS NULL
              AND r.room_code = 'ม.1/1' AND s.class_role = 'class_president'
            """,
            rollover_world["year_id"],
        )
    assert len(rows) == 1
    assert rows[0]["status"] == "promoted", "แถวปีเก่าต้องยังอยู่และบอกว่าถูกเลื่อน"
    assert rows[0]["room_code"] == "ม.1/1"


@pytest.mark.asyncio
async def test_require_permission_still_points_at_active_row(client, rollover_world, db_pool):
    """⑤ RBAC ยังชี้คนถูก — บุคลากรที่ถูกยก **อยู่ในห้องเดิม** ⇒ มี 2 แถวในห้องเดียว

    นี่คือเทสต์ระดับ integration ของ `ORDER BY (status='active') DESC` ใน
    `core/rbac.require_permission` (P2 มีเทสต์ระดับหน่วยอยู่แล้วใน test_year_read_paths.py):
    หลัง rollover จริง แถว `promoted` (id ต่ำกว่า) กับ `active` อยู่ในห้องเดียวกัน
    ⇒ ถ้าไม่มี ORDER BY จะหยิบแถว promoted แล้วได้ 403 กับคนที่ยังทำงานอยู่จริง
    """
    from core.rbac import require_permission

    await _preview_and_apply(client, rollover_world)

    uid = rollover_world["users"]["teacher_council"]["user_id"]
    room_id = rollover_world["rooms"]["ม.1/1"]

    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, status, academic_year_id FROM students
            WHERE room_id = $1 AND user_id = $2 AND deleted_at IS NULL
            ORDER BY id
            """,
            room_id, uid,
        )
        assert len(rows) == 2, "ต้องมีสองแถวในห้องเดียวกัน (ปีเก่า promoted + ปีใหม่ active)"
        assert [r["status"] for r in rows] == ["promoted", "active"]
        assert rows[0]["id"] < rows[1]["id"], "แถวปีเก่าต้อง id ต่ำกว่า (ถ้าไม่ ORDER BY จะหยิบตัวนี้)"

        # 🎯 ต้องผ่าน — ทั้งที่แถวแรกที่เจอตามลำดับ id คือ promoted
        assert await require_permission(conn, room_id, uid, "MANAGE_STUDENTS") is True


@pytest.mark.asyncio
async def test_promoted_student_gets_permission_in_new_room_only(client, rollover_world, db_pool):
    """นักเรียนที่เลื่อนขึ้น: ใช้สิทธิ์ในห้องใหม่ได้ และห้องเดิมต้องปฏิเสธ (แถวนั้นเป็นประวัติ)"""
    from core.exceptions import ForbiddenError
    from core.rbac import require_permission

    await _preview_and_apply(client, rollover_world)

    uid = rollover_world["users"]["class_president"]["user_id"]
    old_room = rollover_world["rooms"]["ม.1/1"]
    new_room = rollover_world["rooms"]["ม.2/1"]

    async with db_pool.acquire() as conn:
        # ปีใหม่เขาถูกยกเป็น student ⇒ ไม่มี RECEIVE_ISSUES แล้ว (ตำแหน่งต้องแต่งตั้งใหม่)
        with pytest.raises(ForbiddenError):
            await require_permission(conn, new_room, uid, "RECEIVE_ISSUES")
        # แต่ยังเป็นสมาชิกห้องใหม่ ⇒ สิทธิ์พื้นฐานของนักเรียนผ่าน
        assert await require_permission(conn, new_room, uid, "SUBMIT_ISSUE") is True
        # ห้องเดิมต้องปฏิเสธ (ไม่ใช่สมาชิก active ที่นั่นอีกแล้ว)
        with pytest.raises(ForbiddenError):
            await require_permission(conn, old_room, uid, "SUBMIT_ISSUE")


# ============================================================
# 6) ยิงพร้อมกัน
# ============================================================

@pytest.mark.asyncio
async def test_concurrent_apply_one_wins_one_conflict(client, rollover_world, db_pool):
    """⑪ apply สองคำขอด้วย `run_id` เดียว → สำเร็จ 1 · อีกอัน `ConflictError` (409 ที่ชั้น router)

    พิสูจน์ว่าการล็อกกันการเขียนซ้อนจริง ⇒ คำขอที่แพ้ต้อง **ไม่** สร้างแถวชุดที่สอง

    🔴 **เทสต์นี้เคยจับบั๊กจริง**: ก่อนมี advisory lock คำขอที่แพ้ได้
       `DeadlockDetectedError` (→ 500) ไม่ใช่ 409 — เพราะ `_gate` อ่านตาราง `students`
       แล้วไปรอแถว `rollover_runs` ที่อีกคำขอถืออยู่ ส่วนอีกคำขอต้องการ ACCESS EXCLUSIVE
       บน `students` (จาก `ALTER TABLE` ในขั้นที่ 5) ⇒ วงจรรอ
       ⚠️ อย่าเปลี่ยนไป assert แค่ "ล้มสักอัน" — ต้องเป็น `ConflictError` เท่านั้น (409 = กดซ้ำ, 500 = ระบบพัง)
    """
    run_id = _preview(client, rollover_world).json()["run_id"]
    admin_id = rollover_world["users"]["admin"]["user_id"]

    results = await asyncio.gather(
        rollover_service.apply_rollover(db_pool, admin_id, run_id=run_id),
        rollover_service.apply_rollover(db_pool, admin_id, run_id=run_id),
        return_exceptions=True,
    )

    ok = [r for r in results if not isinstance(r, Exception)]
    failed = [r for r in results if isinstance(r, Exception)]
    assert len(ok) == 1, f"ต้องสำเร็จหนึ่งคำขอ แต่ได้ {results}"
    assert len(failed) == 1 and isinstance(failed[0], ConflictError), f"ได้ {failed}"

    new = await _active_rows(db_pool, rollover_world["to_year_id"])
    assert len(new) == _PROMOTED + _STAFF_CARRIED, "ต้องไม่ถูกสร้างสองรอบ"


# ============================================================
# 7) สิทธิ์ + auth
# ============================================================

@pytest.mark.asyncio
async def test_requires_login_401(client, rollover_world):
    """X-API-Key (system RPC) → user_id เป็น None → 401 ไม่ใช่ 500"""
    headers = {"X-API-Key": "test-api-key"}
    assert client.post(
        _url("/preview"),
        json={"from_year_id": rollover_world["year_id"], "to_year_id": rollover_world["to_year_id"]},
        headers=headers,
    ).status_code == 401
    assert client.post(_url("/apply"), json={"run_id": 1}, headers=headers).status_code == 401
    assert client.get(_url("/runs"), headers=headers).status_code == 401


@pytest.mark.parametrize("role", ["student", "council_member"])
@pytest.mark.asyncio
async def test_non_privileged_roles_forbidden_403(client, rollover_world, role):
    """นักเรียนทั่วไป และสภานักเรียน (scope all แต่ is_admin=False) → 403

    ⚠️ `council_member` เป็นเคสที่ต้องระวัง: `get_access_scope` ให้ scope='all'
       แต่ `is_admin=False` ⇒ `get_manage_mode()` คืน 'none' ⇒ ต้องโดน 403
       (ถ้าเช็คแต่ scope จะหลุด)
    """
    assert _preview(client, rollover_world, actor=role).status_code == 403


@pytest.mark.parametrize("role,room", [
    ("teacher", "ม.1/1"),                 # ครูทั่วไป — จัดการได้เฉพาะระดับชั้นตัวเอง
    ("level_president", "ม.3/9"),         # ประธานระดับ — ระดับชั้นของห้องตัวเอง (rooms.level)
    ("level_vice_president", "ม.1/1"),
])
@pytest.mark.asyncio
async def test_scoped_roles_forbidden_403(client, rollover_world, db_pool, role, room):
    """🔴 ครูทั่วไป/ประธานระดับ **มี `MANAGE_STUDENTS` เหมือนกัน** แต่ต้องเลื่อนทั้งโรงเรียนไม่ได้

    นี่คือเหตุผลที่ต้องมีประตูที่สอง (`get_manage_mode()['mode'] == 'school'`) —
    ถ้าเช็คแต่สิทธิ์ ครู ม.4 คนเดียวจะกดเลื่อนชั้นทั้งโรงเรียนได้ (ข้อ 7 ของแผน)
    """
    sid = f"SC{random.randint(10000, 99999)}"
    uid = await auth_service.register_user(
        db_pool, f"sc_{role}", "1234", f"{role} ทดสอบ", sid, room, 77, role
    )
    headers = {"Authorization": f"Bearer {auth_service.create_access_token(uid)}"}

    res = client.post(
        _url("/preview"),
        json={"from_year_id": rollover_world["year_id"], "to_year_id": rollover_world["to_year_id"]},
        headers=headers,
    )
    assert res.status_code == 403, res.text
    assert "ส่วนกลาง" in res.json()["detail"]


@pytest.mark.parametrize("actor", ["admin", "teacher_council", "council_president"])
@pytest.mark.asyncio
async def test_school_wide_roles_allowed(client, rollover_world, actor):
    """ส่วนกลางทั้งสาม (admin / ครูสภา / ประธานสภา) ผ่าน — และทำได้จริงจนจบ"""
    preview = _preview(client, rollover_world, actor=actor)
    assert preview.status_code == 200, preview.text
    assert _apply(client, rollover_world, preview.json()["run_id"], actor=actor).status_code == 200


# ============================================================
# 8) ประวัติรอบ + กระทบยอด
# ============================================================

@pytest.mark.asyncio
async def test_list_runs_returns_history_newest_first(client, rollover_world):
    """ประวัติรอบ — ใหม่สุดก่อน และมีทั้ง PREVIEWED ที่ไม่ได้ใช้ กับ APPLIED ที่ใช้แล้ว"""
    first = _preview(client, rollover_world).json()["run_id"]
    second = _preview(client, rollover_world).json()["run_id"]
    _apply(client, rollover_world, second)

    body = client.get(_url("/runs"), headers=_hdr(rollover_world)).json()
    assert body["total"] == 2
    assert [i["id"] for i in body["items"]] == [second, first]
    assert body["items"][0]["status"] == "APPLIED"
    assert body["items"][0]["applied_at"] is not None
    assert body["items"][1]["status"] == "PREVIEWED"
    assert body["items"][0]["from_year"]["id"] == rollover_world["year_id"]
    assert body["items"][0]["to_year"]["year_be"] == rollover_world["to_year_be"]


@pytest.mark.asyncio
async def test_reconciliation_reports_missing_and_added(client, rollover_world, db_pool):
    """กระทบยอด: ม.6 จบ → โผล่ฝั่ง `missing` ของปีใหม่ (ไม่เดาสาเหตุ) · เด็กใหม่ → `added`"""
    await _preview_and_apply(client, rollover_world)

    # เด็กย้ายเข้า หลังขึ้นปีใหม่ (สร้างในปีใหม่ตรง ๆ)
    await auth_service.register_user(
        db_pool, "rw_newcomer", "1234", "ย้าย เข้า", "NEW0001", "ม.2/1", 99, "student"
    )
    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE students SET academic_year_id = $1 WHERE user_id = "
            "(SELECT id FROM users WHERE username = 'rw_newcomer')",
            rollover_world["to_year_id"],
        )

    body = client.get(
        _url("/reconciliation"),
        params={
            "from_year_id": rollover_world["year_id"],
            "to_year_id": rollover_world["to_year_id"],
        },
        headers=_hdr(rollover_world),
    ).json()

    # ฝั่ง missing = คน ม.6 ที่จบ (ไม่มีแถวในปีใหม่) เท่านั้น
    assert body["missing_count"] == _GRADUATING
    assert all(p["room_code"] == "ม.6/1" for p in body["missing"])
    assert body["added_count"] == 1
    assert body["added"][0]["student_id"] == "NEW0001"


@pytest.mark.asyncio
async def test_reconciliation_requires_school_scope(client, rollover_world):
    """กระทบยอดเปิดรายชื่อทั้งโรงเรียน ⇒ ประตูเดียวกับ preview (สภานักเรียน/นักเรียน → 403)"""
    res = client.get(
        _url("/reconciliation"),
        params={
            "from_year_id": rollover_world["year_id"],
            "to_year_id": rollover_world["to_year_id"],
        },
        headers=_hdr(rollover_world, "student"),
    )
    assert res.status_code == 403
