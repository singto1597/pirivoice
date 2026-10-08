"""🔁 เลื่อนชั้นทั้งโรงเรียน (Academic Year Rollover) — P4

**ปัญหาที่แก้:** โรงเรียนขึ้นปีใหม่ทุกปี — เด็ก ม.1→ม.2 … ม.5→ม.6, ม.6 จบ, มีเด็กย้ายออก/เข้า
และบางระดับสลับห้องกันใหม่ ก่อนหน้านี้ระบบทำเหตุการณ์นี้ไม่ได้เลย (ต้องไล่แก้ทีละคน)

**หลักการที่ทำให้ทั้งระบบไม่ต้องแก้:** `students` 1 แถว = สมาชิก 1 คน ใน 1 ห้อง **ของ 1 ปี**
⇒ พอ `apply` แล้ว **ปิดแถวปีเก่า** (`promoted`/`graduated`) และ **สร้างแถวปีใหม่**
คิวรีเดิมทุกที่ที่กรอง `status='active' AND deleted_at IS NULL` จะหมายถึง
"สมาชิกปีปัจจุบัน" เหมือนเดิมโดยไม่ต้องแก้อะไรเลย (ไม่ต้องแตะ RBAC / notification /
issue pyramid / board joins) — นี่คือเหตุผลที่เลือกโมเดลนี้ตั้งแต่ต้น

**การจำแนก 3 ทาง (ไม่มีการเดา):**
  · `STAFF_ROLES`        → ยกไปปีใหม่ **บทบาท/ห้อง/สิทธิ์เดิม** (ครูไม่เลื่อนชั้น)
  · ระดับ `ม.6` (ที่ไม่ใช่ staff) → จบ → แถวเดิม `graduated` และ **ไม่สร้างแถวใหม่**
  · ที่เหลือ             → **แถวใหม่เป็น `class_role='student'`** เข้าห้องปลายทาง

**🔴 สองอย่างที่แผนเคยเขียนไว้ไม่ตรงกับข้อมูลจริง (แก้ 8 ต.ค. 2026 หลังเคาะกับเจ้าของระบบ):**
  1. `council_member` / `council_president` — แผนเดิมเขียนว่า "วาระหมด ไม่สร้างแถวใหม่"
     แต่ข้อมูลจริงพบว่า **ทั้ง 23 คนมีแถวเดียวเท่านั้นในปีนี้** (ไม่มีแถว 'นักเรียน' ซ้อน)
     ⇒ ถ้าไม่สร้างแถวใหม่ คนเหล่านี้จะ **หายจากรายชื่อปีใหม่ทั้งหมด** จนกว่าจะ import ทับ
     และในกลุ่มนี้มี **ประธานสภาที่ไม่มีห้อง 1 คน** ซึ่งจะไม่มีแถวสมาชิกเลย = เข้าระบบไม่ได้
     ⇒ **มติ: ยกเป็น `student` ตามห้องปลายทาง** (คนไม่มีห้องยกไปโดย `room_id = NULL`
        เหมือนที่ `admin`/`teacher_council` ที่ไม่มีห้องถูกยกอยู่แล้ว)
     ⇒ `positions_reset` กับ `council_lapsing` จึงต่างกันแค่ **ป้ายกำกับ** ไม่ใช่พฤติกรรม
  2. `target_room_code()` **ห้ามจับคู่ด้วย `rooms.room_number`** — ข้อมูลจริงพบว่า
     `room_number` เป็น `NULL` ทุกห้อง (import สร้างห้องโดยไม่ใส่) ⇒ ต้องสลับ token หน้า `/`
     ของ `room_code` เท่านั้น

**⚠️ ระดับชั้นอ่านจาก `room_code` ไม่ใช่ `rooms.level`** — ใช้หัว token หน้า `/` เป็นแหล่งเดียว
   (`ม.3/14` → หัว = `ม.3`) แล้วเตือนถ้า `rooms.level` ไม่ตรง · เหตุผล: ถ้าสองที่ขัดกัน
   ต้องมีที่หนึ่งที่ "ถูก" — เลือกอันที่ผูกกับตัวห้องจริงที่เด็กอยู่ และเป็นอันที่การจับคู่ห้องใช้อยู่
   (rooms.level เป็นคอลัมน์ว่างได้ และข้อมูลจริงไม่ขัดกันเลย 0 ห้อง)

**ไม่ผ่าน `year_service.set_current_year()` โดยเจตนา** — ฟังก์ชันนั้นเปิด
`pool.acquire()` + `conn.transaction()` ของตัวเอง ⇒ เรียกจากใน transaction เราจะเสีย atomicity
⇒ ที่นี่ inline `_clear_current` + `SET is_current` + `ALTER ... SET DEFAULT` บน conn เดียวกัน
(และไม่ต้องผ่านด่าน `_assert_settable_as_current` เพราะเราสร้างสมาชิกให้ปีใหม่ **ก่อน** ตั้ง current)

ตาม docs/rules/backend.md: SQL อยู่ในชั้นนี้เท่านั้น · ทุก mutation อยู่ใน transaction
เดียวกับ audit log · ชื่อคอลัมน์ที่ interpolate ลง SQL ต้องมาจาก allowlist
"""
import json
from typing import Any, Dict, List, Optional, Tuple

import asyncpg

from core.exceptions import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from core.logger import AuditLogger
from core.rbac import get_manage_mode, get_role_permissions, require_permission_anywhere

# ============================================================
# กติกาการจำแนก — แก้ที่นี่ที่เดียว
# ============================================================

# ลำดับชั้นถัดไป · `None` = จบการศึกษา (ไม่สร้างแถวใหม่)
LEVEL_NEXT: Dict[str, Optional[str]] = {
    "ม.1": "ม.2",
    "ม.2": "ม.3",
    "ม.3": "ม.4",
    "ม.4": "ม.5",
    "ม.5": "ม.6",
    "ม.6": None,
}
# ระดับที่ "จบ" — ใช้เทียบกับ **หัว token ของ room_code** (ดูหมายเหตุหัวไฟล์)
GRADUATING_LEVEL = "ม.6"

# บทบาทบุคลากร — ไม่เลื่อนชั้น ยกบทบาท/ห้อง/สิทธิ์ไปปีใหม่เหมือนเดิม
STAFF_ROLES = {"admin", "teacher_council", "teacher"}

# ตำแหน่งที่ผูกกับ "ห้อง" — วาระหมดพร้อมปี ⇒ ยกเป็น student เข้าห้องปลายทาง
ELECTED_ROOM_ROLES = {
    "class_president",
    "vice_academic",
    "vice_discipline",
    "vice_activity",
    "vice_reception",
    "level_president",
    "level_vice_president",
}

# ตำแหน่งระดับโรงเรียน — วาระหมดพร้อมปีเหมือนกัน แต่ **ไม่มีห้องปลายทางที่ผูกกับตำแหน่ง**
# ⚠️ ต่างจาก ELECTED_ROOM_ROLES แค่ป้ายกำกับ (ทั้งคู่ยกเป็น student) — ดูข้อ 1 หัวไฟล์
SCHOOL_WIDE_ELECTED_ROLES = {"council_member", "council_president"}

# ส่งเป็น array ให้ SQL (`= ANY($n)`) — เรียงแล้วเพื่อให้ผลลัพธ์นิ่ง
_STAFF_ROLES_SQL = sorted(STAFF_ROLES)

# ลำดับการแสดงผลระดับชั้น (ให้ by_level อ่านจากบนลงล่างเสมอ)
_LEVEL_ORDER = ["ม.1", "ม.2", "ม.3", "ม.4", "ม.5", "ม.6"]

# 🚪 ประตูที่หนึ่ง — ครูทั่วไป/ประธานระดับก็มีสิทธิ์นี้ ⇒ **ไม่พอถ้าใช้ตัวเดียว** (ดู _gate)
PERMISSION = "MANAGE_STUDENTS"

# สถานะของรอบเลื่อนชั้น
STATUS_PREVIEWED = "PREVIEWED"
STATUS_APPLIED = "APPLIED"
STATUS_FAILED = "FAILED"

# 🔒 กุญแจกัน apply สองคำขอทำพร้อมกัน (advisory lock ผูกกับ transaction — คืนเองตอน commit/rollback)
#    ⚠️ **ต้องเป็นคำสั่งแรกของ transaction ก่อนแตะตาราง `students`** — ไม่ใช่ของประดับ:
#       ขั้นที่ 5 ทำ `ALTER TABLE students` ซึ่งต้องได้ ACCESS EXCLUSIVE บนตารางนั้น
#       ส่วน `_gate` ต้อง **อ่าน** `students` (ACCESS SHARE) ⇒ ถ้าคำขอที่สองถือ lock อ่านไว้
#       แล้วไปรอแถว `rollover_runs` ที่คำขอแรก lock ไว้ = **วงจรรอ** (คำขอแรกต้องการ
#       ACCESS EXCLUSIVE แต่ติด lock อ่านของคำขอที่สอง) ⇒ ผู้ใช้ได้ 500
#       `DeadlockDetectedError` แทนที่จะเป็น 409 "รอบนี้ถูกใช้ไปแล้ว"
#       จับเจอจริงตอนเทสต์ยิง `apply_rollover` สองคำขอพร้อมกัน (test_rollover.py §6)
#    ✅ advisory lock บังคับให้เข้าคิวกัน **ตั้งแต่ยังไม่ถือ lock ใด ๆ** ⇒ ไม่มีทางเป็นวงจร
_APPLY_LOCK_KEY = 0x524F4C4C  # "ROLL"

_ROLE_FALLBACK = "student"


# ============================================================
# 🔧 helpers บริสุทธิ์ (ไม่แตะ DB) — เทสต์ตรงได้โดยไม่ต้องมีฐานข้อมูล
# ============================================================

def room_head(room_code: Optional[str]) -> Optional[str]:
    """หัว token หน้า `/` ของ `room_code` — `'ม.3/14'` → `'ม.3'`

    `None` เมื่อ: ไม่มีค่า / ไม่มี `/` / หัวว่าง ⇒ ผู้เรียกตีความเป็น "หระดับไม่ได้" (ห้ามเดา)
    """
    if not room_code:
        return None
    head, sep, _tail = room_code.partition("/")
    if not sep:
        return None
    head = head.strip()
    return head or None


def room_tail(room_code: Optional[str]) -> Optional[str]:
    """ท้าย token หลัง `/` — `'ม.3/14'` → `'14'` (คืน `None` ถ้าไม่มี/ว่าง)"""
    if not room_code:
        return None
    _head, sep, tail = room_code.partition("/")
    if not sep:
        return None
    tail = tail.strip()
    return tail or None


def target_room_code(room_code: Optional[str]) -> Optional[str]:
    """ห้องปลายทางของ `room_code` — สลับ **หัว token** ตาม `LEVEL_NEXT` แล้วต่อท้ายเดิม

      `'ม.4/1'` → `'ม.5/1'` · `'ม.3/14'` → `'ม.4/14'` · `'ม.6/3'` → `None` (จบ)
      `'ม.7/1'` → `None` (ไม่รู้จัก) · `'A101'` → `None` (ไม่มี `/`) · `None` → `None`

    ⚠️ **ห้ามจับคู่ด้วย `rooms.room_number`** — เป็น `NULL` ทุกห้องในข้อมูลจริง
       (import สร้างห้องโดยไม่ใส่ค่านั้น) ⇒ จับคู่ด้วยจะได้ห้องปลายทาง `NULL` ทั้งโรงเรียน
       เงียบ ๆ · การสลับ token ใช้ได้เพราะรหัสห้องเป็น `'<ระดับ>/<เลข>'` มาตลอด (0 ห้องที่ไม่มี `/`)
    """
    head = room_head(room_code)
    tail = room_tail(room_code)
    if head is None or tail is None:
        return None
    next_head = LEVEL_NEXT.get(head)
    if not next_head:
        return None
    return f"{next_head}/{tail}"


def classify_member(class_role: Optional[str], room_code: Optional[str]) -> str:
    """จำแนกสมาชิก 1 แถว → `'staff'` | `'graduate'` | `'promote'`

    ลำดับสำคัญ: **staff มาก่อน** — ครูที่บังเอิญมีห้องเป็น ม.6 ต้องถูกยกไปปีใหม่
    ไม่ใช่จบการศึกษา (ครูไม่จบ) · และคนที่ไม่มีห้องก็ยังเป็น `'promote'`
    (ยกไปแบบไม่มีห้อง ไม่ใช่หายไป — ดูข้อ 1 หัวไฟล์)
    """
    role = class_role or _ROLE_FALLBACK
    if role in STAFF_ROLES:
        return "staff"
    if room_head(room_code) == GRADUATING_LEVEL:
        return "graduate"
    return "promote"


def _level_sort_key(level: Optional[str]) -> Tuple[int, str]:
    if level in _LEVEL_ORDER:
        return (_LEVEL_ORDER.index(level), "")
    return (len(_LEVEL_ORDER), level or "")


def _role_counts(roles: List[Optional[str]]) -> Dict[str, int]:
    """นับตามบทบาท (บทบาทว่าง → `'student'` ตาม default ของคอลัมน์) เรียงชื่อนิ่ง"""
    counts: Dict[str, int] = {}
    for role in roles:
        key = role or _ROLE_FALLBACK
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


# ============================================================
# 🚪 ประตูสิทธิ์ (สองชั้น)
# ============================================================

async def _gate(conn: asyncpg.Connection, user_id: int) -> None:
    """ประตู **สองชั้น** สำหรับงานที่กระทบทั้งโรงเรียน

    1. `MANAGE_STUDENTS` — มีหรือไม่
    2. `get_manage_mode()['mode'] == 'school'` — กระทบ **ทั้งโรงเรียน** ได้หรือไม่

    🔴 **ต้องมีทั้งสอง** — `MANAGE_STUDENTS` อย่างเดียวไม่พอ: จาก `config/roles.json`
       ครูทั่วไป (`teacher`) และประธานระดับ (`level_president`/`level_vice_president`)
       **มีสิทธิ์นี้เหมือนกัน** แต่การเลื่อนชั้นทั้งโรงเรียนจะพลิกสถานะของทุกคนในทุกระดับ
       ⇒ ถ้าเช็คแต่สิทธิ์ ครู ม.4 คนเดียวจะกดเลื่อนชั้นทั้งโรงเรียนได้ (ข้อ 7 ของแผน)

    `mode == 'school'` เป็นจริงเฉพาะ `admin` / `teacher_council` / `council_president`
    (scope `all` + `is_admin`) — `council_member` ได้ scope `all` แต่ `is_admin=False`
    ⇒ mode `none` ⇒ 403 (ถูกต้อง: สภานักเรียนดูได้แต่ไม่จัดการ)
    """
    await require_permission_anywhere(conn, user_id, PERMISSION)
    mode = await get_manage_mode(conn, user_id)
    if mode.get("mode") != "school":
        raise ForbiddenError(
            "การเลื่อนชั้นทั้งโรงเรียนทำได้เฉพาะส่วนกลาง (ผู้ดูแลระบบ / ครูสภา / ประธานสภา) "
            "เท่านั้น — ตำแหน่งอื่นจัดการรายคน/รายห้องได้ตามขอบเขตของตัวเอง"
        )


# ============================================================
# 📖 อ่านแถวที่ต้องใช้
# ============================================================

_RUN_COLUMNS = """
    r.id, r.from_year_id, r.to_year_id, r.status,
    r.promoted_count, r.graduated_count, r.staff_carried_count,
    r.positions_reset_count, r.unmapped_count, r.error_message,
    r.created_by, r.created_at, r.applied_at, r.updated_at,
    r.plan::text AS plan_text,
    fy.year_be AS from_year_be, fy.name AS from_year_name,
    ty.year_be AS to_year_be,   ty.name AS to_year_name
"""


def _run_row(row: asyncpg.Record) -> Dict[str, Any]:
    """แถว `rollover_runs` → dict ที่ schema ใช้ได้ (`plan` จาก JSONB text → dict)"""
    data = dict(row)
    raw_plan = data.pop("plan_text", None)
    try:
        data["plan"] = json.loads(raw_plan) if raw_plan else {}
    except (TypeError, ValueError):
        # plan ที่อ่านไม่ได้ไม่ควรทำให้ทั้ง endpoint ล้ม — คืน {} แล้วให้ UI แสดงว่าว่าง
        data["plan"] = {}
    data["from_year"] = {
        "id": data["from_year_id"],
        "year_be": data["from_year_be"],
        "name": data["from_year_name"],
    }
    data["to_year"] = {
        "id": data["to_year_id"],
        "year_be": data["to_year_be"],
        "name": data["to_year_name"],
    }
    return data


async def _fetch_year(conn: asyncpg.Connection, year_id: int, *, lock: bool = False) -> dict:
    """อ่านปีการศึกษาที่ **ยังไม่ถูกลบ** — ปีที่ถูกลบใช้เลื่อนชั้นไม่ได้"""
    row = await conn.fetchrow(
        f"""
        SELECT id, year_be, name, is_current FROM academic_years
        WHERE id = $1 AND deleted_at IS NULL
        {'FOR UPDATE' if lock else ''}
        """,
        year_id,
    )
    if not row:
        raise NotFoundError("ไม่พบปีการศึกษานี้ (อาจถูกลบไปแล้ว)")
    return dict(row)


async def _fetch_run(conn: asyncpg.Connection, run_id: int, *, lock: bool = False) -> dict:
    # ⚠️ ต้องมี JOIN สองตัวนี้เสมอ — `_RUN_COLUMNS` อ้าง alias `fy`/`ty` อยู่ในรายการ SELECT
    row = await conn.fetchrow(
        f"""
        SELECT {_RUN_COLUMNS}
        FROM rollover_runs r
        JOIN academic_years fy ON fy.id = r.from_year_id
        JOIN academic_years ty ON ty.id = r.to_year_id
        WHERE r.id = $1
        """
        + (" FOR UPDATE OF r" if lock else ""),
        run_id,
    )
    if not row:
        raise NotFoundError("ไม่พบรอบการเลื่อนชั้นนี้")
    return _run_row(row)


# ============================================================
# 🧮 จำแนกสมาชิกทั้งปี (หัวใจของการ preview **และ** apply)
# ============================================================

async def _classify(conn: asyncpg.Connection, from_year_id: int) -> Dict[str, Any]:
    """อ่านสมาชิก active ทั้งปีต้นทาง แล้วจำแนกเป็น 3 กลุ่ม + หาห้องปลายทางของผู้ที่จะเลื่อน

    ⚠️ **preview กับ apply ใช้ฟังก์ชันนี้ตัวเดียวกันโดยเจตนา** — ถ้าเขียนสองชุด
       สิ่งที่ผู้ใช้เห็นกับการที่เกิดขึ้นจริงจะต่างกันได้ (และจะต่างกันแบบเงียบ ๆ)
       ราคาที่จ่าย: ดึง ~3,000 แถวต่อการเรียก 1 ครั้ง (ไม่กี่มิลลิวินาที) — คุ้ม

    คืน dict:
      `members`   — ทุกแถว active (id, user_id, class_role, room_id, room_code)
      `promote`   — ผู้ที่จะได้แถวใหม่ (`room_id`/`to_room_id` อาจเป็น `None` = ไม่มีห้อง)
      `graduate`  — ผู้จบ (ม.6 ที่ไม่ใช่ staff)
      `staff`     — บุคลากรที่จะถูกยกไป
      `unmapped`  — ห้องที่หาปลายทางไม่ได้ (พร้อมจำนวนคน) — **ห้ามเดา**
      `roomless`  — ผู้ที่จะถูกยกไปโดยไม่มีห้อง
      `code_to_room_id` — `room_code` → `rooms.id` (เฉพาะห้องที่ยังไม่ถูกลบ)
    """
    code_rows = await conn.fetch(
        "SELECT id, room_code FROM rooms WHERE deleted_at IS NULL AND room_code IS NOT NULL"
    )
    code_to_room_id = {r["room_code"]: r["id"] for r in code_rows}

    rows = await conn.fetch(
        """
        SELECT s.id, s.user_id, s.student_id, s.class_role, s.room_id, r.room_code
        FROM students s
        LEFT JOIN rooms r ON r.id = s.room_id
        WHERE s.academic_year_id = $1
          AND s.status = 'active'
          AND s.deleted_at IS NULL
        ORDER BY s.id
        """,
        from_year_id,
    )

    promote: List[dict] = []
    graduate: List[dict] = []
    staff: List[dict] = []
    unmapped_by_room: Dict[str, Dict[str, Any]] = {}
    roomless: List[dict] = []

    for raw in rows:
        member = dict(raw)
        bucket = classify_member(member["class_role"], member["room_code"])
        if bucket == "staff":
            staff.append(member)
            continue
        if bucket == "graduate":
            graduate.append(member)
            continue

        # promote — หาห้องปลายทาง
        if member["room_id"] is None:
            member["to_room_id"] = None
            member["to_room_code"] = None
            roomless.append(member)
            promote.append(member)
            continue

        to_code = target_room_code(member["room_code"])
        to_room_id = code_to_room_id.get(to_code) if to_code else None
        if to_room_id is None:
            key = member["room_code"] or f"(ห้อง id {member['room_id']})"
            entry = unmapped_by_room.setdefault(
                key,
                {
                    "from_room_code": member["room_code"],
                    "from_room_id": member["room_id"],
                    "level": room_head(member["room_code"]),
                    "student_count": 0,
                    "reason": (
                        f"ไม่รู้จักระดับ «{room_head(member['room_code']) or '?'}» "
                        "(รหัสห้องต้องอยู่ในรูป «ม.X/เลข»)"
                        if target_room_code(member["room_code"]) is None
                        else f"ยังไม่มีห้อง «{to_code}» ในระบบ"
                    ),
                },
            )
            entry["student_count"] += 1
            member["to_room_id"] = None
            member["to_room_code"] = to_code
            promote.append(member)
            continue

        member["to_room_id"] = to_room_id
        member["to_room_code"] = to_code
        promote.append(member)

    return {
        "members": [dict(r) for r in rows],
        "promote": promote,
        "graduate": graduate,
        "staff": staff,
        "unmapped": sorted(
            unmapped_by_room.values(),
            key=lambda e: _level_sort_key(e["level"]) + (e["from_room_code"] or "",),
        ),
        "roomless": roomless,
        "code_to_room_id": code_to_room_id,
    }


def _apply_overrides(
    classification: Dict[str, Any], overrides: Dict[str, str]
) -> Tuple[List[Tuple[int, int]], List[dict]]:
    """ใช้ `room_overrides` แก้ห้องที่แมปไม่ได้ → คืน (คู่ `(from_room_id, to_room_id)`, ที่ยังแก้ไม่ได้)

    `overrides` = `{from_room_code: to_room_code}` — ผู้ใช้เลือกเองจากหน้าเว็บ
    ⚠️ ค่าที่ส่งมา **ต้องเป็นห้องที่มีอยู่จริง** — ไม่สร้างห้องใหม่ให้ (คนละเรื่องกับ "เลื่อนชั้น")

    ⚠️ **เขียนผลกลับเข้า `classification` ด้วย** (`to_room_id`/`to_room_code` ของสมาชิกที่แก้แล้ว)
       ไม่ใช่คืนค่าเฉย ๆ เพราะสองสิ่งที่ตามหลังต้องเห็นผลนี้:
         · `_duplicate_student_ids` — จับ "สองห้องยุบเป็นห้องเดียวแล้วเลขซ้ำ" ซึ่ง **เกิดจาก override**
           เท่านั้น ถ้าไม่อัปเดต มันจะตรวจไม่เห็นเคสที่มันมีไว้จับพอดี
         · `_build_plan` ที่ apply เก็บไว้เป็นหลักฐาน — ต้องสะท้อนสิ่งที่ทำจริง ไม่ใช่สถานะก่อนแก้
    """
    code_to_room_id = classification["code_to_room_id"]
    still_unmapped: List[dict] = []
    resolved: Dict[Optional[str], Optional[str]] = {}

    for entry in classification["unmapped"]:
        code = entry["from_room_code"]
        chosen = (overrides.get(code) or "").strip() if code else ""
        if chosen and code_to_room_id.get(chosen) is not None:
            resolved[code] = chosen
        elif chosen:
            still_unmapped.append(
                {**entry, "reason": f"ห้องปลายทาง «{chosen}» ที่เลือกไว้ไม่มีอยู่ในระบบ"}
            )
        else:
            still_unmapped.append(entry)

    for member in classification["promote"]:
        if member["room_id"] is None:
            continue
        chosen = resolved.get(member["room_code"])
        if chosen is not None:
            member["to_room_code"] = chosen
            member["to_room_id"] = code_to_room_id[chosen]

    # เก็บที่ยังแก้ไม่ได้กลับเข้าไป — `_build_plan` จึงรายงานตามจริงทั้ง preview และ apply
    classification["unmapped"] = still_unmapped

    pairs: Dict[int, int] = {}
    for member in classification["promote"]:
        if member["room_id"] is None or member["to_room_id"] is None:
            continue  # ไม่มีห้อง = ยกไปแบบไม่มีห้อง · ยังแมปไม่ได้ = อยู่ใน still_unmapped
        pairs[member["room_id"]] = member["to_room_id"]

    return sorted(pairs.items()), still_unmapped


def _duplicate_student_ids(classification: Dict[str, Any]) -> List[dict]:
    """หา `(ห้องปลายทาง, student_id)` ที่จะซ้ำกัน — จะทำให้ unique index 028 ระเบิดตอน apply

    ⚠️ จำเป็นเฉพาะเมื่อมี `room_overrides` **ยุบสองห้องเป็นห้องเดียว** (เช่น ม.3/13 + ม.3/14 → ม.4/13)
       ถ้าเลขประจำตัวนักเรียนซ้ำกัน (ข้อมูลนำเข้าผิด) ⇒ `UniqueViolationError` กลาง transaction
       ⇒ ต้องจับ **ก่อน** เพื่อให้ได้ 400 ที่บอกว่าซ้ำที่ไหน ไม่ใช่ 500

    `student_id` เป็น `NULL` ไม่นับ (NULL ไม่ชนกันใน unique index)
    """
    seen: Dict[Tuple[int, Optional[str]], dict] = {}
    dups: Dict[Tuple[int, Optional[str]], dict] = {}
    for member in classification["promote"]:
        sid = member.get("student_id")
        if not sid or member["to_room_id"] is None:
            continue
        key = (member["to_room_id"], sid)
        if key in seen:
            dups.setdefault(
                key,
                {
                    "to_room_code": member["to_room_code"],
                    "student_id": sid,
                    "user_ids": [seen[key]["user_id"]],
                },
            )["user_ids"].append(member["user_id"])
        else:
            seen[key] = member
    return list(dups.values())


def _build_plan(
    classification: Dict[str, Any], from_year: dict, to_year: dict
) -> Dict[str, Any]:
    """ประกอบผล preview จากผลการจำแนก — ค่าที่ UI ใช้ตัดสินใจทั้งหมดอยู่ในนี้"""
    promote = classification["promote"]
    graduate = classification["graduate"]
    staff = classification["staff"]
    roomless = classification["roomless"]
    unmapped = classification["unmapped"]

    # --- by_level: เฉพาะคนที่มีห้องและไม่จบ ---
    levels: Dict[str, Dict[str, Any]] = {}
    for member in promote:
        if member["room_id"] is None or member["room_code"] is None:
            continue
        level = room_head(member["room_code"])
        group = levels.setdefault(
            level,
            {
                "level": level,
                "target_level": LEVEL_NEXT.get(level),
                "student_count": 0,
                "_rooms": {},
            },
        )
        group["student_count"] += 1
        room = group["_rooms"].setdefault(
            member["room_code"],
            {
                "from_room_code": member["room_code"],
                "to_room_code": member["to_room_code"],
                "student_count": 0,
                "status": "ok" if member["to_room_id"] is not None else "unmapped",
            },
        )
        room["student_count"] += 1

    by_level = []
    for level in sorted(levels, key=_level_sort_key):
        group = levels[level]
        rooms = sorted(group.pop("_rooms").values(), key=lambda r: r["from_room_code"] or "")
        group["rooms"] = rooms
        group["mapped_rooms"] = sum(1 for r in rooms if r["status"] == "ok")
        group["unmapped_rooms"] = sum(1 for r in rooms if r["status"] != "ok")
        by_level.append(group)

    # --- graduating / ตำแหน่งที่หมดวาระ ---
    graduating_rooms: Dict[str, int] = {}
    for member in graduate:
        code = member["room_code"] or "(ไม่มีห้อง)"
        graduating_rooms[code] = graduating_rooms.get(code, 0) + 1

    promoted_roles = [m["class_role"] for m in promote]
    positions_reset = [r for r in promoted_roles if (r or _ROLE_FALLBACK) in ELECTED_ROOM_ROLES]
    council_lapsing = [
        r for r in promoted_roles if (r or _ROLE_FALLBACK) in SCHOOL_WIDE_ELECTED_ROLES
    ]

    plan: Dict[str, Any] = {
        "from_year": {"id": from_year["id"], "year_be": from_year["year_be"], "name": from_year["name"]},
        "to_year": {"id": to_year["id"], "year_be": to_year["year_be"], "name": to_year["name"]},
        "total_active": len(classification["members"]),
        "promoted": {"count": len(promote)},
        "graduating": {
            "count": len(graduate),
            "rooms": [
                {"room_code": code, "student_count": n}
                for code, n in sorted(graduating_rooms.items())
            ],
        },
        "staff_carried": {"count": len(staff), "by_role": _role_counts([m["class_role"] for m in staff])},
        "positions_reset": {"count": len(positions_reset), "by_role": _role_counts(positions_reset)},
        "council_lapsing": {"count": len(council_lapsing), "by_role": _role_counts(council_lapsing)},
        "roomless": {"count": len(roomless), "by_role": _role_counts([m["class_role"] for m in roomless])},
        "by_level": by_level,
        "unmapped": unmapped,
    }
    plan["blockers"], plan["warnings"] = _blockers_and_warnings(classification, from_year, to_year)
    plan["can_apply"] = not plan["blockers"]
    return plan


def _blockers_and_warnings(
    classification: Dict[str, Any], from_year: dict, to_year: dict
) -> Tuple[List[str], List[str]]:
    """สิ่งที่ "ห้ามกด" กับ "ควรดู" — แยกกันเพราะผลลัพธ์ต่างกัน (ห้ามกด = ไม่มีทางไปต่อ)"""
    blockers: List[str] = []
    warnings: List[str] = []

    if from_year["id"] == to_year["id"]:
        blockers.append("ปีต้นทางกับปีปลายทางเป็นปีเดียวกัน — ต้องเป็นคนละปี")
    if not from_year["is_current"]:
        blockers.append(
            f"ปีต้นทาง «{from_year['name']}» ไม่ใช่ปีปัจจุบัน — "
            "การเลื่อนชั้นต้องเริ่มจากปีที่โรงเรียนกำลังใช้อยู่ "
            "(ถ้าต้องการย้อนทำ ให้ตั้งปีนั้นเป็นปีปัจจุบันก่อน)"
        )
    if not classification["members"]:
        blockers.append(f"ปี «{from_year['name']}» ไม่มีสมาชิกที่ใช้งานอยู่ — ไม่มีอะไรให้เลื่อน")
    unmapped_members = sum(e["student_count"] for e in classification["unmapped"])
    if unmapped_members:
        blockers.append(
            f"มี {unmapped_members} คนใน {len(classification['unmapped'])} ห้องที่หาห้องปลายทางไม่ได้ — "
            "ต้องเลือกห้องปลายทางให้ก่อนจึงจะเลื่อนชั้นได้"
        )

    if classification["roomless"]:
        warnings.append(
            f"มี {len(classification['roomless'])} คนที่ไม่มีห้อง "
            "— จะถูกยกไปปีใหม่โดยยังไม่มีห้อง (ต้องไปใส่ห้องให้ทีหลัง)"
        )

    levels_mismatch = [
        m["room_code"]
        for m in classification["members"]
        if m["room_code"]
        and m["room_id"] is not None
        and room_head(m["room_code"]) == GRADUATING_LEVEL
        and (m["class_role"] or _ROLE_FALLBACK) in STAFF_ROLES
    ]
    if levels_mismatch:
        warnings.append(
            f"มีบุคลากร {len(levels_mismatch)} คนที่สังกัดห้องระดับ ม.6 "
            "— จะถูกยกไปปีใหม่ตามเดิม (ครูไม่จบการศึกษา) ตรวจว่าเป็นความตั้งใจ"
        )

    return blockers, warnings


def _duplicate_blockers(duplicates: List[dict]) -> List[str]:
    """ข้อความ "ห้ามกด" ของเลขประจำตัวที่ซ้ำ (แยกจาก `_blockers_and_warnings` ที่คิดในหน่วยความจำ)

    🔴 **เป็น blocker ไม่ใช่ warning โดยเจตนา** — `apply_rollover` จะ `raise` ทันทีที่เจอเลขซ้ำ
       ⇒ ถ้า preview บอกแค่ "ควรดู" แต่กดแล้วล้ม ผู้ใช้จะไม่เชื่อคำเตือนของระบบอีก
       (บทเรียนเดียวกับ `unmapped`: สิ่งที่ทำให้ apply ล้ม ต้องทำให้ `can_apply=False` ตั้งแต่ preview)

    🔑 **บรรทัดนี้ทำงานได้ก็เพราะ preview รับ `room_overrides`** — เลขซ้ำ *เกิดได้เฉพาะเมื่อ
       override ยุบสองห้องเป็นห้องเดียว* (การแมปอัตโนมัติสลับแค่หัวรหัส ⇒ ไม่มีทางยุบกัน)
       ⇒ ถ้า preview ไม่รับ overrides ฟังก์ชันนี้จะเป็นโค้ดตายที่ไม่มีวันยิง
    """
    out: List[str] = []
    if duplicates:
        detail = "; ".join(
            f"{d['to_room_code']} เลขที่ {d['student_id']} ซ้ำ {len(d['user_ids'])} คน"
            for d in duplicates
        )
        out.append(
            "มีเลขประจำตัวนักเรียนซ้ำกันในห้องปลายทางเดียวกัน — จะล้มกลางทาง ให้แก้ก่อน: "
            f"{detail}"
        )
    return out


# ============================================================
# 👁️ PREVIEW — อ่านล้วน ไม่แตะข้อมูล (เขียนแค่แถวประวัติ PREVIEWED)
# ============================================================

async def preview_rollover(
    pool: asyncpg.Pool,
    user_id: int,
    *,
    from_year_id: int,
    to_year_id: int,
    room_overrides: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """ดูว่าจะเกิดอะไรขึ้น **ก่อน** กดจริง — และบันทึกแผนไว้เป็นหลักฐาน

    เขียน `rollover_runs` แถวสถานะ `PREVIEWED` ⇒ ได้ `run_id` ไว้ส่งกลับตอน `apply`
    (บังคับให้ผู้ใช้เห็นแผนก่อนเสมอ และกัน "ยิง apply ซ้ำด้วยพารามิเตอร์ที่ต่างจากที่ดูไว้")

    ⚠️ preview **ไม่เปลี่ยนข้อมูลสมาชิกเลย** — เรียกซ้ำได้ไม่จำกัด (ได้แถวประวัติเพิ่มขึ้น)

    ⚠️ **`room_overrides` มีผลกับ preview ด้วย** (ไม่ใช่แค่ตอน apply) — ใช้ `_apply_overrides`
       ตัวเดียวกับ apply ⇒ สิ่งที่ผู้ใช้เห็นหลังเลือกห้อง = สิ่งที่ apply จะทำจริงเป๊ะ
       และ `can_apply` สะท้อนสถานะ *หลัง* แก้ห้องแล้ว ไม่ใช่ก่อนแก้
    """
    overrides = {k: v for k, v in (room_overrides or {}).items() if v}

    async with pool.acquire() as conn:
        async with conn.transaction():
            await _gate(conn, user_id)

            from_year = await _fetch_year(conn, from_year_id)
            to_year = await _fetch_year(conn, to_year_id)

            classification = await _classify(conn, from_year_id)
            # 🎯 ใช้ override ก่อนสร้างแผน — `by_level`/`unmapped`/`can_apply` จึงตรงกับที่จะเกิดขึ้น
            #    (`_pairs` ไม่ได้ใช้ที่นี่ — preview ไม่ได้เขียนแถว; ที่ยังแมปไม่ได้ถูกส่งต่อ
            #     ผ่าน `classification["unmapped"]` ให้ `_build_plan` รายงานเป็น blocker อยู่แล้ว)
            _apply_overrides(classification, overrides)
            plan = _build_plan(classification, from_year, to_year)

            # ปีปลายทางต้องว่าง — ถ้ามีคนอยู่แล้ว การเลื่อนชั้นจะทับซ้อนกับของเดิม
            existing = await conn.fetchval(
                """
                SELECT COUNT(*) FROM students
                WHERE academic_year_id = $1 AND deleted_at IS NULL
                """,
                to_year_id,
            )
            if existing:
                plan["blockers"].append(
                    f"ปีปลายทาง «{to_year['name']}» มีสมาชิกอยู่แล้ว {existing} คน — "
                    "การเลื่อนชั้นต้องทำลงปีที่ยังว่าง (ถ้าตั้งใจจะ import ทับ ให้ลบสมาชิกในปีนั้นก่อน)"
                )

            # เลขประจำตัวซ้ำ (เกิดจาก override ยุบห้อง) → ห้ามกดเช่นกัน ไม่ใช่แค่เตือน
            plan["blockers"].extend(_duplicate_blockers(_duplicate_student_ids(classification)))
            plan["can_apply"] = not plan["blockers"]
            plan["room_overrides"] = overrides

            run_id = await conn.fetchval(
                """
                INSERT INTO rollover_runs (
                    from_year_id, to_year_id, status, plan,
                    promoted_count, graduated_count, staff_carried_count,
                    positions_reset_count, unmapped_count, created_by
                ) VALUES ($1, $2, $3, $4::jsonb, $5, $6, $7, $8, $9, $10)
                RETURNING id
                """,
                from_year_id,
                to_year_id,
                STATUS_PREVIEWED,
                json.dumps(plan, default=str),
                plan["promoted"]["count"],
                plan["graduating"]["count"],
                plan["staff_carried"]["count"],
                plan["positions_reset"]["count"],
                sum(e["student_count"] for e in plan["unmapped"]),
                user_id,
            )

            await AuditLogger("rollover_service").log(
                conn=conn,
                action="PREVIEW_ROLLOVER",
                actor_identifier=str(user_id),
                client_source="web",
                user_id=user_id,
                entity_type="rollover_run",
                entity_id=run_id,
                new_values={
                    "from_year": from_year["year_be"],
                    "to_year": to_year["year_be"],
                    "promoted": plan["promoted"]["count"],
                    "graduating": plan["graduating"]["count"],
                    "can_apply": plan["can_apply"],
                },
            )

        return {"run_id": run_id, **plan}


# ============================================================
# ✅ APPLY — เขียนจริง ทั้งหมดใน transaction เดียว
# ============================================================

async def apply_rollover(
    pool: asyncpg.Pool,
    user_id: int,
    *,
    run_id: int,
    room_overrides: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """เลื่อนชั้นทั้งโรงเรียนจริง — **transaction เดียวจบ** (ล้มกลางทาง = ไม่มีอะไรถูกแก้)

    🔒 เปิดด้วย advisory lock ของงานนี้เสมอ (`_APPLY_LOCK_KEY`) ⇒ สองคำขอพร้อมกันเข้าคิวกัน
       คำขอที่แพ้จะตื่นมาเจอ `status='APPLIED'` แล้วได้ `ConflictError` → 409 ตามที่ควรเป็น

    ลำดับ (ห้ามสลับ — เหตุผลอยู่ในคอมเมนต์แต่ละขั้น):
      1. ยก `STAFF_ROLES` ไปปีใหม่ (บทบาท/ห้อง/สิทธิ์เดิม)
      2. สร้างแถวใหม่ของผู้ที่เลื่อนขึ้น (`class_role='student'`)
      3. ปิดแถวเดิมของปีเก่า — ม.6 → `graduated` · ที่เหลือ → `promoted`
      4. 🛡️ ถ้าปีใหม่ไม่เหลือ `is_admin` เลย → ยกเลิกทั้งงาน
      5. ตั้งปีใหม่เป็นปีปัจจุบัน + ชี้ DEFAULT ของ `students.academic_year_id` มาที่ปีใหม่
      6. ปิดรอบเป็น `APPLIED` + audit

    ⚠️ **ต้องสร้างแถว (ขั้น 1–2) ก่อนตั้ง current (ขั้น 5)** — ถ้าสลับ จะได้ปีปัจจุบันที่ว่างเปล่า
       ⇒ รายชื่อทั้งโรงเรียนหายวับในคลิกเดียว (คลาสเดียวกับด่านใน `year_service`)

    ⚠️ **แก้ `room_overrides` ได้เฉพาะห้องที่ preview บอกว่าแมปไม่ได้** — เป็นทางเดียวที่ผู้ใช้
       ระบุห้องปลายทางเอง (เช่น `ม.3/14` → `ม.4/13`) เพราะระบบ **ห้ามเดา** แทนคน
       ค่าที่ส่งมาต้องเป็นห้องที่มีอยู่จริง; ระบบไม่สร้างห้องใหม่ให้
    """
    overrides = {k: v for k, v in (room_overrides or {}).items() if v}

    async with pool.acquire() as conn:
        async with conn.transaction():
            # 🔒 ต้องมาก่อน `_gate` — ดูคำอธิบาย `_APPLY_LOCK_KEY` (กัน deadlock กับขั้นที่ 5)
            await conn.execute("SELECT pg_advisory_xact_lock($1)", _APPLY_LOCK_KEY)

            await _gate(conn, user_id)

            run = await _fetch_run(conn, run_id, lock=True)
            if run["status"] == STATUS_APPLIED:
                raise ConflictError(
                    "รอบการเลื่อนชั้นนี้ถูกใช้ไปแล้ว — ให้ preview ใหม่เพื่อดูสถานะปัจจุบัน "
                    "ก่อนตัดสินใจอีกครั้ง"
                )
            if run["status"] != STATUS_PREVIEWED:
                raise ValidationError(
                    f"รอบการเลื่อนชั้นนี้อยู่ในสถานะ {run['status']} — ใช้ยืนยันไม่ได้"
                )

            from_year_id, to_year_id = run["from_year_id"], run["to_year_id"]

            # 🔒 ล็อกปีสองแถวตามลำดับ id (belt-and-braces — ตัวกันจริงคือ `_APPLY_LOCK_KEY` ข้างบน
            #    ที่บังคับให้คำขอที่สองรอ *ก่อน* จะอ่านตาราง `students` ⇒ ไม่เกิด deadlock)
            await conn.fetch(
                "SELECT id FROM academic_years WHERE id = ANY($1::int[]) ORDER BY id FOR UPDATE",
                [from_year_id, to_year_id],
            )
            from_year = await _fetch_year(conn, from_year_id)
            to_year = await _fetch_year(conn, to_year_id)

            classification = await _classify(conn, from_year_id)
            pairs, still_unmapped = _apply_overrides(classification, overrides)
            if still_unmapped:
                detail = "; ".join(
                    f"{e['from_room_code']} ({e['student_count']} คน): {e['reason']}"
                    for e in still_unmapped
                )
                raise ValidationError(
                    f"ยังมีห้องที่หาปลายทางไม่ได้ — ต้องเลือกห้องปลายทางให้ครบก่อน: {detail}"
                )

            # ปีปลายทางต้องว่าง — ตรวจซ้ำ ณ เวลาที่จะเขียนจริง (มีคน import แทรกได้ระหว่างนั้น)
            existing = await conn.fetchval(
                "SELECT COUNT(*) FROM students WHERE academic_year_id = $1 AND deleted_at IS NULL",
                to_year_id,
            )
            if existing:
                raise ConflictError(
                    f"ปีปลายทาง «{to_year['name']}» มีสมาชิกอยู่แล้ว {existing} คน "
                    "(อาจมีคน import แทรกหลังตอน preview) — ยกเลิกเพื่อไม่ให้ข้อมูลทับกัน"
                )

            duplicates = _duplicate_student_ids(classification)
            if duplicates:
                detail = "; ".join(
                    f"{d['to_room_code']} เลขที่ {d['student_id']} ซ้ำ {len(d['user_ids'])} คน"
                    for d in duplicates
                )
                raise ValidationError(
                    f"เลขประจำตัวนักเรียนซ้ำกันในห้องปลายทางเดียวกัน — แก้ก่อน: {detail}"
                )

            # ---------- 1) ยกบุคลากร ----------
            # ⚠️ `NOT EXISTS` **จำเป็น** ไม่ใช่ของประดับ: บุคลากรที่ `room_id IS NULL`
            #    (admin/ครูสภาในข้อมูลจริง) ไม่ชน unique index 028 เลย ⇒ กันซ้ำด้วย index ไม่ได้
            staff_carried = await conn.fetchval(
                """
                WITH carried AS (
                    INSERT INTO students (
                        room_id, user_id, student_id, student_no, prefix, first_name,
                        last_name, nickname, class_role, staff_level, is_admin,
                        permissions, responsibilities, status, academic_year_id
                    )
                    SELECT
                        s.room_id, s.user_id, s.student_id, s.student_no, s.prefix, s.first_name,
                        s.last_name, s.nickname, s.class_role, s.staff_level, s.is_admin,
                        s.permissions, s.responsibilities, 'active', $2
                    FROM students s
                    WHERE s.academic_year_id = $1
                      AND s.status = 'active'
                      AND s.deleted_at IS NULL
                      AND COALESCE(s.class_role, $4) = ANY($3::text[])
                      AND NOT EXISTS (
                          SELECT 1 FROM students x
                          WHERE x.user_id = s.user_id
                            AND x.academic_year_id = $2
                            AND x.deleted_at IS NULL
                      )
                    RETURNING 1
                )
                SELECT COUNT(*) FROM carried
                """,
                from_year_id,
                to_year_id,
                _STAFF_ROLES_SQL,
                _ROLE_FALLBACK,
            )

            # ---------- 2) สร้างแถวของผู้ที่เลื่อนขึ้น ----------
            # ทุกคนได้ `class_role='student'` + สิทธิ์ของ student (ตำแหน่งเลือกตั้งใหม่ทีหลัง)
            # `student_no` ยกไปเดิมโดยเจตนา — ให้ Excel ปีใหม่ทับ (เลขที่ในห้องใหม่ยังไม่รู้)
            # คนที่ไม่มีห้อง (`room_id IS NULL`) ถูกยกไปด้วย `room_id = NULL` — ไม่ใช่หายไป
            student_permissions = json.dumps(get_role_permissions(_ROLE_FALLBACK), default=str)
            promoted = await conn.fetchval(
                """
                WITH mapping AS (
                    SELECT * FROM unnest($3::int[], $4::int[]) AS m(from_room_id, to_room_id)
                ), inserted AS (
                    INSERT INTO students (
                        room_id, user_id, student_id, student_no, prefix, first_name,
                        last_name, nickname, class_role, staff_level, is_admin,
                        permissions, responsibilities, status, academic_year_id
                    )
                    SELECT
                        m.to_room_id, s.user_id, s.student_id, s.student_no,
                        s.prefix, s.first_name, s.last_name, s.nickname,
                        $6, NULL, FALSE, $5::jsonb, '[]'::jsonb, 'active', $2
                    FROM students s
                    LEFT JOIN rooms r ON r.id = s.room_id
                    LEFT JOIN mapping m ON m.from_room_id = s.room_id
                    WHERE s.academic_year_id = $1
                      AND s.status = 'active'
                      AND s.deleted_at IS NULL
                      AND COALESCE(s.class_role, $7) <> ALL($8::text[])
                      -- จบการศึกษา = ไม่สร้างแถวใหม่ (ห้องระดับ ม.6)
                      AND (s.room_id IS NULL OR r.room_code IS NULL
                           OR split_part(r.room_code, '/', 1) <> $9)
                      -- ห้องที่ต้องมีปลายทาง: ถ้ามีห้อง ต้องมีคู่ใน mapping แล้ว (ตรวจไปแล้วข้างบน)
                      AND (s.room_id IS NULL OR m.to_room_id IS NOT NULL)
                      AND NOT EXISTS (
                          SELECT 1 FROM students x
                          WHERE x.user_id = s.user_id
                            AND x.academic_year_id = $2
                            AND x.deleted_at IS NULL
                      )
                    RETURNING 1
                )
                SELECT COUNT(*) FROM inserted
                """,
                from_year_id,
                to_year_id,
                [p[0] for p in pairs],
                [p[1] for p in pairs],
                student_permissions,
                _ROLE_FALLBACK,
                _ROLE_FALLBACK,
                _STAFF_ROLES_SQL,
                GRADUATING_LEVEL,
            )

            # ---------- 3) ปิดแถวเดิมของปีเก่า ----------
            # 🔑 นี่คือขั้นที่ทำให้ "status='active'" ยังหมายถึง "สมาชิกปีปัจจุบัน" เหมือนเดิม
            #    ⇒ คิวรีเดิมทั้งระบบไม่ต้องแก้ (WHERE status='active' เป็นด่านกันรันซ้ำให้ในตัว)
            # ⚠️ ใช้กติกา "จบ" ชุดเดียวกับ `classify_member()` เป๊ะ — บุคลากรในห้อง ม.6
            #    ถูกยกไปปีใหม่ (เป็น `promoted`) ไม่ใช่จบ ⇒ ตัวเลข `graduated_count` ที่บันทึกไว้
            #    ต้องเท่ากับ `plan.graduating.count` ที่ผู้ใช้เห็นตอน preview (ไม่งั้นหลักฐานขัดกันเอง)
            closed = await conn.fetch(
                """
                WITH target AS (
                    SELECT s.id,
                           (COALESCE(s.class_role, $3) <> ALL($4::text[])
                            AND r.room_code IS NOT NULL
                            AND split_part(r.room_code, '/', 1) = $2) AS graduates
                    FROM students s
                    LEFT JOIN rooms r ON r.id = s.room_id
                    WHERE s.academic_year_id = $1
                      AND s.status = 'active'
                      AND s.deleted_at IS NULL
                )
                UPDATE students s
                SET status = CASE WHEN t.graduates THEN 'graduated' ELSE 'promoted' END,
                    updated_at = NOW()
                FROM target t
                WHERE s.id = t.id
                RETURNING (t.graduates) AS graduates
                """,
                from_year_id,
                GRADUATING_LEVEL,
                _ROLE_FALLBACK,
                _STAFF_ROLES_SQL,
            )
            graduated_count = sum(1 for r in closed if r["graduates"])

            # ---------- 4) 🛡️ ด่านกันล็อกโรงเรียน ----------
            # สิทธิ์ทั้งหมดอ่านจาก `students` ของปีปัจจุบัน ⇒ ปีใหม่ที่ไม่มี is_admin เลย
            # = ไม่มีใครตั้งค่าอะไรได้อีกเลย (ไม่ใช่แค่ "ไม่มีแอดมิน" — คือระบบตาย)
            admins = await conn.fetchval(
                """
                SELECT COUNT(*) FROM students
                WHERE academic_year_id = $1 AND status = 'active' AND deleted_at IS NULL
                  AND is_admin
                """,
                to_year_id,
            )
            if not admins:
                raise ValidationError(
                    f"ยกเลิกการเลื่อนชั้น — ปี «{to_year['name']}» จะไม่มีผู้ดูแลระบบ (`is_admin`) "
                    "เหลืออยู่เลย และสิทธิ์ทั้งระบบอ่านจากตารางนี้ ⇒ จะไม่มีใครตั้งค่าอะไรได้อีก "
                    "(ให้ยกบุคลากรไปก่อน หรือเพิ่มผู้ดูแลให้ปีใหม่)"
                )

            # ---------- 5) ตั้งปีใหม่เป็นปีปัจจุบัน ----------
            # ⚠️ ล้างตัวเก่าก่อนตั้งตัวใหม่เสมอ (index `uq_academic_years_single_current` เป็น
            #    non-deferrable ⇒ สลับสองบรรทัดนี้ = UniqueViolationError)
            # ⚠️ ไม่เรียก `year_service.set_current_year()` — ฟังก์ชันนั้นเปิด transaction
            #    ของตัวเอง ⇒ เรียกจากตรงนี้จะเสีย atomicity ทั้งงาน (ดูหมายเหตุหัวไฟล์)
            await conn.execute(
                """
                UPDATE academic_years
                SET is_current = FALSE, updated_at = NOW()
                WHERE is_current AND deleted_at IS NULL
                """
            )
            await conn.execute(
                "UPDATE academic_years SET is_current = TRUE, updated_at = NOW() WHERE id = $1",
                to_year_id,
            )
            # 🔑 metadata-only (PG 11+): แถวที่สร้างหลังจากนี้ (ลงทะเบียนใหม่/import) ไปลงปีใหม่
            #    ⚠️ `ALTER TABLE` เอา ACCESS EXCLUSIVE lock บน `students` จนจบ transaction
            #       ⇒ request อื่นที่แตะตารางนี้จะรอ ~ไม่กี่วินาที (งานนี้ทำงานไม่บ่อย ยอมรับได้)
            #    ⚠️ ค่าเป็น int จาก DB ⇒ interpolate ได้ปลอดภัย
            await conn.execute(
                f"ALTER TABLE students ALTER COLUMN academic_year_id SET DEFAULT {int(to_year_id)}"
            )

            # ---------- 6) ปิดรอบ + audit ----------
            final_plan = _build_plan(classification, from_year, to_year)
            merged_plan = {
                "preview": run["plan"],
                "applied": final_plan,
                "room_overrides": overrides,
            }
            unmapped_left = sum(e["student_count"] for e in still_unmapped)

            await conn.execute(
                """
                UPDATE rollover_runs
                SET status = $2, plan = $3::jsonb,
                    promoted_count = $4, graduated_count = $5, staff_carried_count = $6,
                    positions_reset_count = $7, unmapped_count = $8,
                    applied_at = NOW(), updated_at = NOW()
                WHERE id = $1
                """,
                run_id,
                STATUS_APPLIED,
                json.dumps(merged_plan, default=str),
                promoted,
                graduated_count,
                staff_carried,
                final_plan["positions_reset"]["count"],
                unmapped_left,
            )

            await AuditLogger("rollover_service").log(
                conn=conn,
                action="APPLY_ROLLOVER",
                actor_identifier=str(user_id),
                client_source="web",
                user_id=user_id,
                entity_type="rollover_run",
                entity_id=run_id,
                old_values={
                    "from_year": from_year["year_be"],
                    "from_year_members_closed": len(closed),
                },
                new_values={
                    "to_year": to_year["year_be"],
                    "to_year_is_current": True,
                    "promoted": promoted,
                    "graduated": graduated_count,
                    "staff_carried": staff_carried,
                    "room_overrides": overrides,
                },
            )

        return {
            "run_id": run_id,
            "from_year": {"id": from_year["id"], "year_be": from_year["year_be"], "name": from_year["name"]},
            "to_year": {"id": to_year["id"], "year_be": to_year["year_be"], "name": to_year["name"]},
            "promoted_count": promoted,
            "graduated_count": graduated_count,
            "staff_carried_count": staff_carried,
            "positions_reset_count": final_plan["positions_reset"]["count"],
            "closed_count": len(closed),
            "room_overrides": overrides,
            "plan": final_plan,
        }


# ============================================================
# 📜 ประวัติรอบ + รายงานกระทบยอด
# ============================================================

async def list_runs(
    pool: asyncpg.Pool,
    user_id: int,
    *,
    limit: int = 20,
    offset: int = 0,
) -> Dict[str, Any]:
    """ประวัติการเลื่อนชั้น (ใหม่สุดก่อน) — ตอบว่า "ใครกด เมื่อไหร่ ผลเป็นยังไง"
    ⚠️ เก็บรายละเอียดเต็มไว้ใน `plan` ⇒ ย้อนดูได้ว่าตอนนั้นระบบคิดว่าจะเกิดอะไรขึ้น
    """
    async with pool.acquire() as conn:
        await _gate(conn, user_id)

        total = await conn.fetchval("SELECT COUNT(*) FROM rollover_runs")
        rows = await conn.fetch(
            f"""
            SELECT {_RUN_COLUMNS}
            FROM rollover_runs r
            JOIN academic_years fy ON fy.id = r.from_year_id
            JOIN academic_years ty ON ty.id = r.to_year_id
            ORDER BY r.id DESC
            LIMIT $1 OFFSET $2
            """,
            limit,
            offset,
        )
    return {"items": [_run_row(r) for r in rows], "total": total or 0}


async def _reconcile(conn: asyncpg.Connection, from_year_id: int, to_year_id: int) -> Dict[str, Any]:
    """กระทบยอดรายชื่อสองปี — ใครหายไป / ใครเพิ่มมา (ตอบข้อ 8 "เด็กจบต้องค้นชื่อเจอ" ได้จริง)

    ⚠️ **ไม่เดาสาเหตุ** — บอกแค่ "มีในปีก่อน ไม่มีในปีใหม่" แล้วให้คนตัดสินว่าเป็น
       ย้ายออก / จบ / ตกหล่น · การเดาจะกลายเป็นข้อมูลผิดที่ไม่มีใครตรวจ
    """
    missing = await conn.fetch(
        """
        SELECT s.user_id, s.student_id, s.first_name, s.last_name, s.class_role, r.room_code
        FROM students s
        LEFT JOIN rooms r ON r.id = s.room_id
        WHERE s.academic_year_id = $1 AND s.deleted_at IS NULL
          AND NOT EXISTS (
              SELECT 1 FROM students x
              WHERE x.user_id = s.user_id
                AND x.academic_year_id = $2
                AND x.deleted_at IS NULL
          )
        ORDER BY r.room_code NULLS LAST, s.student_no NULLS LAST, s.id
        """,
        from_year_id,
        to_year_id,
    )
    added = await conn.fetch(
        """
        SELECT s.user_id, s.student_id, s.first_name, s.last_name, s.class_role, r.room_code
        FROM students s
        LEFT JOIN rooms r ON r.id = s.room_id
        WHERE s.academic_year_id = $2 AND s.deleted_at IS NULL
          AND NOT EXISTS (
              SELECT 1 FROM students x
              WHERE x.user_id = s.user_id
                AND x.academic_year_id = $1
                AND x.deleted_at IS NULL
          )
        ORDER BY r.room_code NULLS LAST, s.student_no NULLS LAST, s.id
        """,
        from_year_id,
        to_year_id,
    )
    return {
        "from_year_id": from_year_id,
        "to_year_id": to_year_id,
        "missing_count": len(missing),
        "added_count": len(added),
        "missing": [dict(r) for r in missing],
        "added": [dict(r) for r in added],
    }


async def reconciliation(
    pool: asyncpg.Pool,
    user_id: int,
    *,
    from_year_id: int,
    to_year_id: int,
) -> Dict[str, Any]:
    """รายงานกระทบยอดรายชื่อระหว่างสองปี (ต้องมีสิทธิ์ระดับโรงเรียน — เห็นรายชื่อทั้งโรงเรียน)"""
    async with pool.acquire() as conn:
        await _gate(conn, user_id)
        await _fetch_year(conn, from_year_id)
        await _fetch_year(conn, to_year_id)
        return await _reconcile(conn, from_year_id, to_year_id)
