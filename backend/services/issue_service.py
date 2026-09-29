import asyncpg
import json
from typing import Optional
from datetime import datetime, timedelta, timezone

from core.exceptions import NotFoundError, ForbiddenError, ValidationError, ConflictError
from core.config import settings
from core.categories import is_valid_category, all_main_category_codes
from core.rbac import get_user_grade_scope

# 🔔 Notification writer (อยู่ใน transaction เดียวกับข้อมูลหลัก — ลอกแบบ AuditLogger)
from services.notification_service import (
    notify, notify_bulk, notify_fanout,
    _room_receiver_ids, _council_ids, _level_president_ids,
    _user_display_name, _mask_actor,
)

# 🔼 ลำดับการ Escalate (พีระมิด)
# room (หัวหน้าห้อง+รอง) → level (ประธานระดับ) → council (สภานักเรียน)
LEVEL_ORDER = ["room", "level", "council"]
NEXT_LEVEL = {"room": "level", "level": "council"}

# ตำแหน่งที่รับเรื่องได้ในแต่ละระดับ (role key → ระดับ)
ROLE_LEVEL = {
    "class_president": "room",
    "vice_academic": "room",
    "vice_discipline": "room",
    "vice_activity": "room",
    "vice_reception": "room",
    "level_president": "level",
    "level_vice_president": "level",
    "council_member": "council",
    "council_president": "council",
}

# ระดับ 'student' (นักเรียนธรรมดา) อยู่ต่ำกว่าทุกอย่าง
LEVEL_RANK = {"student": 0, "room": 1, "level": 2, "council": 3}


def _parse_permissions(raw) -> list:
    if not raw:
        return []
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return []
    return list(raw)


def _parse_json(raw, default=None):
    if raw is None:
        return default if default is not None else []
    if isinstance(raw, (list, dict)):
        return raw
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default if default is not None else []


def _escape_like(s: str) -> str:
    """หนี wildcard ของ LIKE/ILIKE (% _ \\) ให้ค้นหาคำที่เป็นตัวอักษรจริง (กัน %/_ กลายเป็น wildcard)
    ใช้คู่กับ `ILIKE ... ESCAPE '\\'` ใน query"""
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


# ============================================================
# 👩‍🏫 Helpers สำหรับครูทั่วไป (level-scoped teacher)
# ============================================================
async def _teacher_scope(conn, user_id: int) -> Optional[str]:
    """คืนระดับชั้นที่ครูทั่วไปรับผิดชอบ (เช่น 'ม.4') หรือ None ถ้าไม่ใช่ครูทั่วไป"""
    row = await conn.fetchrow(
        """
        SELECT staff_level FROM students
        WHERE user_id = $1 AND class_role = 'teacher'
          AND deleted_at IS NULL AND status = 'active'
        ORDER BY id LIMIT 1
        """,
        user_id
    )
    return row["staff_level"] if row and row["staff_level"] else None


async def _room_level(conn, room_id: Optional[int]) -> Optional[str]:
    """คืนระดับชั้น (เช่น 'ม.4') ของห้อง"""
    if not room_id:
        return None
    return await conn.fetchval("SELECT level FROM rooms WHERE id = $1", room_id)


async def _level_room_ids(conn, staff_level: str) -> list:
    """คืน id ห้องทั้งหมดที่อยู่ในระดับชั้นที่กำหนด"""
    rows = await conn.fetch(
        "SELECT id FROM rooms WHERE level = $1 AND deleted_at IS NULL",
        staff_level
    )
    return [r["id"] for r in rows]


async def _can_manage_issue(conn, user_id: int, issue) -> bool:
    """
    เช็คว่า user จัดการเรื่องนี้ได้หรือไม่:
    - ผู้รับเรื่องปัจจุบัน
    - admin (is_admin / SUPER_ADMIN)
    - ครูทั่วไปที่รับผิดชอบระดับชั้นเดียวกับเรื่อง
    """
    if issue["current_assignee_id"] == user_id:
        return True
    if await _is_admin(conn, user_id):
        return True
    teacher_level = await _teacher_scope(conn, user_id)
    if teacher_level:
        room_level = await _room_level(conn, issue["room_id"])
        if room_level == teacher_level:
            return True
    return False


# ============================================================
# 🔍 ความสามารถในการมองเห็น (Pyramid Visibility)
# ============================================================
async def user_level(pool, user_id: int, room_id: Optional[int] = None) -> str:
    """
    คืนระดับสูงสุดที่ user สังกัด (room / level / council)
    - ถ้าระบุ room_id → ดูเฉพาะในห้องนั้น
    - ถ้าไม่ระบุ → ดูทุกตำแหน่งที่ user เป็น (คืนระดับสูงสุด)
    - ครูทั่วไป → คืน "council" (มองเห็นสูงสุด แต่ถูกจำกัดระดับชั้นใน list/get)
    """
    async with pool.acquire() as conn:
        if room_id is not None:
            row = await conn.fetchrow(
                """
                SELECT class_role FROM students
                WHERE user_id = $1 AND room_id = $2 AND deleted_at IS NULL AND status = 'active'
                """,
                user_id, room_id
            )
            role = row["class_role"] if row else None
        else:
            rows = await conn.fetch(
                """
                SELECT class_role FROM students
                WHERE user_id = $1 AND deleted_at IS NULL AND status = 'active'
                """,
                user_id
            )
            roles = [r["class_role"] for r in rows]

            # SUPER_ADMIN มองเห็นทุกอย่าง
            if settings.SUPER_ADMIN_ID and int(user_id) == int(settings.SUPER_ADMIN_ID):
                return "council"

            # admin / ครูสภา / ประธานสภา: มองเห็นทุกอย่าง (เทียบเท่า council สูงสุด)
            if any(r in ("admin", "teacher_council", "council_president") for r in roles):
                return "council"

            # ครูทั่วไป: มองเห็นระดับสูงสุด แต่ scope ถูกจำกัดระดับชั้นที่อื่น
            if "teacher" in roles:
                return "council"

            # หาระดับสูงสุดจากทุกตำแหน่ง (ใช้ LEVEL_RANK รองรับ 'student')
            levels = [ROLE_LEVEL.get(r, "student") for r in roles]
            best = "student"
            for lv in levels:
                if LEVEL_RANK.get(lv, 0) > LEVEL_RANK.get(best, 0):
                    best = lv
            return best

    if not role:
        return "student"
    return ROLE_LEVEL.get(role, "student")


def can_see(level: str, issue_level: str, reporter_id: int, user_id: int, is_anonymous: bool) -> bool:
    """
    กฎการมองเห็น (พีระมิด):
    - ระดับที่สูงกว่า มองเห็นเรื่องของระดับล่างลงมา (มองลงได้)
    - ผู้แจ้งเห็นเรื่องของตัวเองเสมอ (ติดตามสถานะได้ แม้แจ้งแบบ anonymous)
    - anonymity แค่ซ่อนชื่อจากคนอื่น (ระบบรู้ผู้แจ้ง แต่คนอื่นเห็นเป็น "ไม่ระบุชื่อ")
    """
    # ระดับสูงกว่ามองลงได้ทุกเรื่อง
    if LEVEL_RANK.get(level, 0) >= LEVEL_RANK.get(issue_level, 1):
        return True
    # ผู้แจ้งเห็นเรื่องของตัวเองเสมอ (ติดตามสถานะ)
    if reporter_id == user_id:
        return True
    return False


# ============================================================
# 📝 CRUD ปัญหา
# ============================================================
# ปลายทางที่ผู้แจ้งขอได้: normal (เรื่องปกติ) / vote / talk (PIRI Boards)
PUBLIC_DESTINATIONS = ("vote", "talk")
# ชนิด board ที่ **สายอนุมัติของสภา** สร้างได้ (approve_to_public)
# ⚠️ **ไม่รวม 'suggestion' โดยเจตนา (E1)** — ข้อเสนอจากผู้ใช้ไม่ได้มาจาก issue และไม่มีผู้อนุมัติ
#    ⇒ เกิดจาก `board_service.create_suggestion()` ทางตรง ไม่ผ่านไฟล์นี้เลย
#    ⇒ ถ้าเผลอเพิ่ม 'suggestion' เข้ามา `approve_to_public` จะสร้างบอร์ดที่ไม่มี
#      issue ต้นทางและ `approved_by` = NULL ซึ่งขัดกับสัญญาของฟังก์ชันนั้น
PUBLIC_BOARD_TYPES = ("vote", "talk")


async def create_issue(
    pool: asyncpg.Pool,
    user_id: int,
    main_category: str,
    category: str,
    title: str,
    description: str,
    is_anonymous: bool = False,
    room_id: Optional[int] = None,
    start_level: str = "room",
    requested_destination: str = "normal",
) -> int:
    """
    สร้างปัญหาใหม่
    - เริ่มต้นที่ระดับ room (หัวหน้าห้อง + รอง) โดยค่า default
    - ถ้าผู้แจ้งเป็นระดับสูง (หัวหน้าห้อง/ประธานระดับ/สภา) สามารถเลือก start_level
      ให้เรื่องไปเริ่มที่ระดับสูงขึ้นได้เลย (เช่น ประธานสภาอยากให้เริ่มที่ council)
    - requested_destination: ปลายทางที่ขอ — 'normal' / 'vote' / 'talk'
      * vote/talk (PIRI Boards) = เรื่องขอเผยแพร่สาธารณะ → **อัตโนมัติตรงไปที่ council**
        (bypass room/level — ไม่เช็คระดับผู้แจ้ง เพราะใครก็ขอโพสต์สาธารณะได้)
        current_level ถูกตั้งเป็น 'council' ให้สภาอนุมัติ/ปัดตก
    - main_category: หมวดหลัก (suggestion/wellbeing/report), category: หมวดย่อยในหมวดหลัก
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            # ตรวจปลายทางที่ขอ
            if requested_destination not in ("normal", "vote", "talk"):
                raise ValidationError(f"ปลายทางที่ขอไม่ถูกต้อง: {requested_destination}")

            # PIRI Boards: vote/talk → เรื่องตรงไปที่สภา (bypass room/level)
            # ผู้แจ้งแค่ "ขอ" เผยแพร่ — ไม่ต้องมีสิทธิ์ระดับสภา (สภาเป็นคนอนุมัติ)
            is_public_request = requested_destination in PUBLIC_DESTINATIONS
            if is_public_request:
                start_level = "council"

            # ตรวจ start_level ถูกต้อง
            if start_level not in LEVEL_ORDER:
                raise ValidationError(f"ระดับเริ่มต้นไม่ถูกต้อง: {start_level}")

            # ✅ ตรวจหมวดหมู่: หมวดย่อยต้องเป็นของหมวดหลักที่ระบุ
            if not is_valid_category(main_category, category):
                raise ValidationError(f"หมวดหมู่ไม่ถูกต้อง: หมวดหลัก '{main_category}' ไม่มีหมวดย่อย '{category}'")

            # ถ้าไม่ระบุห้อง → หาห้องของ user
            if not room_id:
                room_id = await conn.fetchval(
                    """
                    SELECT room_id FROM students
                    WHERE user_id = $1 AND deleted_at IS NULL AND status = 'active'
                    ORDER BY id LIMIT 1
                    """,
                    user_id
                )
                if not room_id:
                    raise ValidationError("ไม่พบห้องของคุณ — กรุณาติดต่อผู้ดูแล")

            # ตรวจว่าห้องมีจริง
            room = await conn.fetchrow(
                "SELECT id, room_name FROM rooms WHERE id = $1 AND deleted_at IS NULL",
                room_id
            )
            if not room:
                raise NotFoundError("ไม่พบห้องเรียน")

            # 🛡️ ผู้แจ้งต้องมีสิทธิ์ในระดับที่เลือกเริ่มต้น (ไม่งั้นนักเรียนธรรมดาส่งขึ้นสภาได้)
            #    — ยกเว้นกรณีขอเผยแพร่สาธารณะ (vote/talk) ซึ่งตั้งให้ตรงไปสภาโดยดีไซน์
            if not is_public_request and start_level != "room":
                my_level = await user_level(pool, user_id, room_id=room_id)
                if LEVEL_RANK.get(my_level, 0) < LEVEL_RANK.get(start_level, 1):
                    raise ForbiddenError(f"คุณมีสิทธิ์แค่ระดับ {my_level} — ไม่สามารถเริ่มที่ระดับ {start_level} ได้")

            reporter_name = None
            if not is_anonymous:
                reporter_name = await conn.fetchval(
                    """
                    SELECT CONCAT_WS(' ', prefix, first_name, last_name)
                    FROM students
                    WHERE user_id = $1 AND room_id = $2 AND deleted_at IS NULL
                    """,
                    user_id, room_id
                )

            issue_id = await conn.fetchval(
                """
                INSERT INTO issues
                    (room_id, main_category, category, title, description,
                     reporter_id, reporter_room_id, reporter_name,
                     current_level, current_assignee_id, status,
                     is_anonymous, requested_destination)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NULL, 'pending', $10, $11)
                RETURNING id
                """,
                room_id, main_category, category, title, description,
                user_id, room_id, reporter_name,
                start_level,
                is_anonymous, requested_destination
            )

            # บันทึก status history (บอกว่าออกที่ระดับไหน)
            if is_public_request:
                note = "สร้างเรื่องใหม่ (ขอเผยแพร่สาธารณะ — ตรงไปที่สภานักเรียน)"
            else:
                note = f"สร้างเรื่องใหม่ (เริ่มต้นที่ระดับ {start_level})"
            await conn.execute(
                """
                INSERT INTO issue_status_history (issue_id, status, changed_by, note)
                VALUES ($1, 'pending', $2, $3)
                """,
                issue_id, user_id, note
            )

            # ถ้า start_level สูงกว่า room → บันทึก escalation เป็นประวัติด้วย
            if start_level != "room":
                esc_reason = (
                    "ผู้แจ้งขอเผยแพร่สาธารณะ (PIRI Boards) — ตรงไปที่สภานักเรียน"
                    if is_public_request else
                    "ผู้แจ้งเลือกเริ่มต้นที่ระดับนี้โดยตรง"
                )
                await conn.execute(
                    """
                    INSERT INTO issue_escalations (issue_id, from_level, to_level, from_assignee_id, reason)
                    VALUES ($1, 'room', $2, $3, $4)
                    """,
                    issue_id, start_level, user_id, esc_reason
                )

            # 🛡️ Audit log (ภายใน transaction เดียว — ตามกฎ backend.md)
            from core.logger import AuditLogger
            await AuditLogger("issue_service").log(
                conn=conn, action="CREATE_ISSUE",
                actor_identifier=str(user_id), client_source="web",
                room_id=room_id, user_id=user_id,
                entity_type="issue", entity_id=issue_id,
                new_values={
                    "title": title, "main_category": main_category,
                    "category": category, "status": "pending",
                    "current_level": start_level, "is_anonymous": is_anonymous,
                    "requested_destination": requested_destination,
                },
            )

            # 🔔 แจ้งเตือนผู้รับเรื่องในระดับนั้น (badge "เรื่องที่รับ") — เรื่อง anonymous ไม่รั่วชื่อ
            actor_name = _mask_actor(reporter_name, is_anonymous)
            if start_level == "room":
                receivers = await _room_receiver_ids(conn, room_id)
            elif start_level == "level":
                receivers = await _level_president_ids(conn, await _room_level(conn, room_id))
            else:  # council (รวมเรื่องขอเผยแพร่สาธารณะ vote/talk — ตรงไปสภา)
                receivers = await _council_ids(conn)
            await notify_bulk(
                conn, receivers,
                group_type="issue_received", type="issue_new",
                title="เรื่องใหม่ในระดับของคุณ",
                body=f'มีเรื่องใหม่ "{title}" จาก {actor_name or "ไม่ระบุชื่อ"}',
                entity_type="issue", entity_id=issue_id,
                actor_id=user_id, actor_name=actor_name,
            )

            return issue_id


async def _has_council_authority(conn, user_id: int) -> bool:
    """ตรวจว่า user มีอำนาจระดับสภา/แอดมิน (อนุมัติเผยแพร่สาธารณะได้):
    - Super Admin / is_admin (แอดมิน)
    - สภานักเรียน (council_member) / ประธานสภา (council_president) / ครูสภา (teacher_council)
    หมายเหตุ: ไม่ใช้ user_level() เพราะครูทั่วไป (teacher) ก็คืน 'council' เพื่อมองเห็นข้อมูล —
    แต่อำนาจอนุมัติต้องมาจากตำแหน่งสภาจริง/แอดมินเท่านั้น"""
    if settings.SUPER_ADMIN_ID and int(user_id) == int(settings.SUPER_ADMIN_ID):
        return True
    rows = await conn.fetch(
        """
        SELECT class_role, is_admin FROM students
        WHERE user_id = $1 AND deleted_at IS NULL AND status = 'active'
        """,
        user_id
    )
    for r in rows:
        if r["is_admin"]:
            return True
        if r["class_role"] in ("council_member", "council_president", "teacher_council"):
            return True
    return False


async def approve_to_public(
    pool: asyncpg.Pool,
    user_id: int,
    issue_id: int,
    board_type: str,
    *,
    vote_choices: Optional[list] = None,
    allow_comments: bool = True,
) -> int:
    """
    🏛️ อนุมัติเรื่องขอเผยแพร่สาธารณะ (PIRI Boards) → สร้าง board จากข้อมูล issue + ปิดเรื่อง

    ข้อกำหนด (ตาม Phase 2):
    - เฉพาะอำนาจระดับสภา/แอดมิน: สภานักเรียน / ประธานสภา / ครูสภา / admin (is_admin/Super Admin)
    - issue ต้องขอปลายทางสาธารณะ (requested_destination != 'normal') — เรื่องธรรมดาอนุมัติเป็น board ไม่ได้
    - board_type ต้องตรงกับที่ผู้แจ้งขอ (vote→vote, talk→talk) กันสร้าง board ผิดประเภท
    - vote board: ต้องมี vote_choices อย่างน้อย 2 ตัวเลือก
    - อนุมัติซ้ำไม่ได้ (published_board_id มีอยู่แล้ว → 409)

    ใน transaction เดียว (ตามกฎ backend.md):
    1. INSERT piri_boards (source_issue_id → ตัวเรื่อง, author = ผู้แจ้งเดิม, approved_by = ผู้ที่อนุมัติ)
    2. vote board → INSERT piri_vote_choices
    3. UPDATE issues: published_board_id = board_id, status = 'resolved', resolved_at = NOW()
    4. INSERT issue_status_history
    5. AuditLogger(action="APPROVE_TO_PUBLIC")

    คืน board_id ที่สร้าง
    """
    # ---- validate ภายนอก transaction (เร็ว + กัน transaction เสีย) ----
    if board_type not in PUBLIC_BOARD_TYPES:
        raise ValidationError(f"ประเภท board ไม่ถูกต้อง: {board_type} (ต้องเป็น talk/vote)")
    if board_type == "vote":
        if not vote_choices or len(vote_choices) < 2:
            raise ValidationError("Board แบบโหวตต้องมีตัวเลือกอย่างน้อย 2 ตัวเลือก")

    async with pool.acquire() as conn:
        async with conn.transaction():
            # 1) อำนาจสภา/แอดมิน
            if not await _has_council_authority(conn, user_id):
                raise ForbiddenError("เฉพาะสภานักเรียน/ประธานสภา/ครูสภา/แอดมินที่อนุมัติเผยแพร่สาธารณะได้")

            # 2) ดึง issue (FOR UPDATE กัน TOCTOU — อนุมัติพร้อมกัน 2 ที่)
            issue = await conn.fetchrow(
                "SELECT * FROM issues WHERE id = $1 AND deleted_at IS NULL FOR UPDATE",
                issue_id
            )
            if not issue:
                raise NotFoundError("ไม่พบเรื่องนี้")

            # 3) ต้องขอปลายทางสาธารณะ
            if issue["requested_destination"] == "normal":
                raise ValidationError("เรื่องนี้ไม่ได้ขอเผยแพร่สาธารณะ — อนุมัติเป็น PIRI Board ไม่ได้")

            # 4) board_type ต้องตรงกับที่ผู้แจ้งขอ
            if board_type != issue["requested_destination"]:
                raise ValidationError(
                    f"เรื่องนี้ขอเผยแพร่แบบ '{issue['requested_destination']}' "
                    f"แต่เลือกอนุมัติเป็น '{board_type}'"
                )

            # 5) อนุมัติซ้ำไม่ได้
            if issue["published_board_id"]:
                raise ConflictError("เรื่องนี้เผยแพร่เป็น PIRI Board ไปแล้ว")

            # 6) สร้าง board จากข้อมูล issue (author = ผู้แจ้งเดิม, approved_by = ผู้ที่อนุมัติ)
            board_id = await conn.fetchval(
                """
                INSERT INTO piri_boards
                    (source_issue_id, board_type, title, description, cover_image_url,
                     author_id, is_anonymous, approved_by, approved_at,
                     status, allow_comments, tags)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW(), 'active', $9, '[]'::jsonb)
                RETURNING id
                """,
                issue_id, board_type, issue["title"], issue["description"],
                issue["image_url"],
                issue["reporter_id"], issue["is_anonymous"],
                user_id, allow_comments
            )

            # 7) vote board → บันทึกตัวเลือก (sort_order = ลำดับใน list)
            if board_type == "vote":
                for i, choice_text in enumerate(vote_choices):
                    await conn.execute(
                        """
                        INSERT INTO piri_vote_choices (board_id, choice_text, sort_order)
                        VALUES ($1, $2, $3)
                        """,
                        board_id, choice_text, i
                    )

            # 8) ปิดเรื่อง + ผูก board
            await conn.execute(
                """
                UPDATE issues
                SET published_board_id = $1, status = 'resolved',
                    resolved_at = NOW(), updated_at = NOW()
                WHERE id = $2
                """,
                board_id, issue_id
            )
            await conn.execute(
                """
                INSERT INTO issue_status_history (issue_id, status, changed_by, note)
                VALUES ($1, 'resolved', $2, $3)
                """,
                issue_id, user_id, f"สภาอนุมัติเผยแพร่เป็น PIRI Board (ประเภท {board_type})"
            )

            # 9) 🛡️ Audit log (ภายใน transaction เดียว — ตามกฎ backend.md)
            from core.logger import AuditLogger
            await AuditLogger("issue_service").log(
                conn=conn, action="APPROVE_TO_PUBLIC",
                actor_identifier=str(user_id), client_source="web",
                room_id=issue["room_id"], user_id=user_id,
                entity_type="piri_board", entity_id=board_id,
                old_values={
                    "status": issue["status"],
                    "published_board_id": issue["published_board_id"],
                    "requested_destination": issue["requested_destination"],
                },
                new_values={
                    "board_type": board_type, "board_id": board_id,
                    "allow_comments": allow_comments,
                    "vote_choices": vote_choices,
                    "status": "resolved", "published_board_id": board_id,
                },
            )

            # 🔔 แจ้งทุกคนว่ามีบอร์ดใหม่ (fan-out — exclude ตัวที่อนุมัติ)
            board_type_label = "โหวต" if board_type == "vote" else "พูดคุย"
            await notify_fanout(
                conn,
                group_type="board", type="board_new",
                title="มีกระทู้ใหม่บน PIRI Boards",
                body=f'"{issue["title"]}" ({board_type_label})',
                entity_type="piri_board", entity_id=board_id, board_id=board_id,
                actor_id=user_id, actor_name=None,
            )

            return board_id


async def change_destination(
    pool: asyncpg.Pool,
    user_id: int,
    issue_id: int,
    requested_destination: str,
) -> None:
    """
    🔁 เปลี่ยนปลายทาง (requested_destination) ของเรื่อง — แก้กรณีผู้แจ้งเลือกผิด เช่น
    ควรเป็น "บอร์ดพูดคุย" แต่แจ้งมาเป็น "ดำเนินการปกติ":
    - 🔐 อำนาจ:
      * สภานักเรียน/แอดมิน (_has_council_authority) เปลี่ยนได้ทุกเรื่อง (ทั้งสองทาง)
      * หัวหน้าห้อง/รอง (RECEIVE_ISSUES ในห้องเรื่อง) เปลี่ยนได้เฉพาะเรื่องที่ยังอยู่ระดับ 'room'
    - 🔄 พฤติกรรม:
      * → 'vote'/'talk' (ปลายทางสาธารณะ): current_level='council' + รีเซ็ต pending
        (เคลียร์ assignee + countdown) → สภานักเรียนรอรับเรื่องอีกที
      * → 'normal': current_level='room' + รีเซ็ต pending → กลับไปหัวหน้าห้อง
      * ระดับไม่เปลี่ยน (เช่น talk→vote ยังอยู่สภา): เปลี่ยนแค่ปลายทาง ไม่รีเซ็ต
    - ⛔ กัน: เรื่องที่เผยแพร่เป็น PIRI Board แล้ว (409), เรื่องที่ปิดแล้ว (409)
    - 🛡️ Audit action="CHANGE_DESTINATION" ใน transaction เดียว
    """
    if requested_destination not in ("normal", "vote", "talk"):
        raise ValidationError(f"ปลายทางไม่ถูกต้อง: {requested_destination}")

    target_level = "council" if requested_destination in ("vote", "talk") else "room"

    async with pool.acquire() as conn:
        async with conn.transaction():
            issue = await conn.fetchrow(
                "SELECT * FROM issues WHERE id = $1 AND deleted_at IS NULL FOR UPDATE",
                issue_id
            )
            if not issue:
                raise NotFoundError("ไม่พบเรื่องนี้")
            if issue["published_board_id"]:
                raise ConflictError("เรื่องนี้เผยแพร่เป็น PIRI Board แล้ว — เปลี่ยนปลายทางไม่ได้")
            if issue["status"] in ("resolved", "cancelled", "rejected"):
                raise ConflictError("เรื่องนี้ถูกปิดแล้ว — เปลี่ยนปลายทางไม่ได้")

            old_destination = issue["requested_destination"]
            if old_destination == requested_destination:
                return  # ไม่มีอะไรเปลี่ยน

            # 🔐 อำนาจ
            if not await _has_council_authority(conn, user_id):
                if issue["current_level"] != "room":
                    raise ForbiddenError("เฉพาะสภานักเรียน/แอดมินที่เปลี่ยนปลายทางเรื่องที่พ้นระดับห้องแล้ว")
                from core.rbac import require_permission
                try:
                    await require_permission(conn, issue["room_id"], user_id, "RECEIVE_ISSUES")
                except ForbiddenError:
                    raise ForbiddenError("คุณไม่ใช่ผู้รับเรื่องในห้องนี้ — เปลี่ยนปลายทางไม่ได้")

            level_changed = target_level != issue["current_level"]

            if level_changed:
                # รีเซ็ตเป็น 'pending' + เคลียร์ผู้รับ/countdown (ส่งไประดับใหม่รอรับเรื่องอีกที)
                await conn.execute(
                    """
                    UPDATE issues
                    SET requested_destination = $1, current_level = $2,
                        current_assignee_id = NULL, status = 'pending',
                        updated_at = NOW()
                    WHERE id = $3
                    """,
                    requested_destination, target_level, issue_id
                )
                # countdown เป็นข้อมูลปฏิบัติการผูกกับผู้รับปัจจุบัน (ตารางไม่มี deleted_at — ออกแบบ
                # ให้ hard delete ได้) — เปลี่ยนไประดับใหม่ → เคลียร์ทิ้ง ระดับใหม่ตั้งเองใหม่ตอนรับเรื่อง
                await conn.execute(
                    """
                    DELETE FROM issue_countdowns
                    WHERE issue_id = $1
                    """,
                    issue_id
                )
            else:
                # ระดับไม่เปลี่ยน (เช่น talk→vote ยังอยู่สภา) — เปลี่ยนแค่ปลายทาง
                await conn.execute(
                    """
                    UPDATE issues
                    SET requested_destination = $1, updated_at = NOW()
                    WHERE id = $2
                    """,
                    requested_destination, issue_id
                )

            new_status = "pending" if level_changed else issue["status"]
            note = (
                f"เปลี่ยนปลายทางจาก '{old_destination}' เป็น '{requested_destination}'"
                f" → ส่ง{'สภานักเรียน' if target_level == 'council' else 'หัวหน้าห้อง'}รับเรื่องอีกครั้ง"
                if level_changed
                else f"เปลี่ยนปลายทางจาก '{old_destination}' เป็น '{requested_destination}'"
            )
            await conn.execute(
                """
                INSERT INTO issue_status_history (issue_id, status, changed_by, note)
                VALUES ($1, $2, $3, $4)
                """,
                issue_id, new_status, user_id, note
            )

            # 🛡️ Audit log (ภายใน transaction เดียว — ตามกฎ backend.md)
            from core.logger import AuditLogger
            await AuditLogger("issue_service").log(
                conn=conn, action="CHANGE_DESTINATION",
                actor_identifier=str(user_id), client_source="web",
                room_id=issue["room_id"], user_id=user_id,
                entity_type="issue", entity_id=issue_id,
                old_values={
                    "requested_destination": old_destination,
                    "current_level": issue["current_level"],
                    "status": issue["status"],
                },
                new_values={
                    "requested_destination": requested_destination,
                    "current_level": target_level,
                    "status": new_status,
                },
            )

            # 🔔 แจ้งผู้แจ้งเรื่องว่าปลายทางเปลี่ยน (badge "เรื่องของฉัน")
            dest_label = {
                "normal": "ดำเนินการปกติ", "vote": "โหวตสาธารณะ", "talk": "บอร์ดพูดคุย",
            }.get(requested_destination, requested_destination)
            if issue["reporter_id"]:
                await notify(
                    conn, user_id=issue["reporter_id"],
                    group_type="issue_mine", type="issue_update",
                    title="อัปเดตสถานะเรื่อง",
                    body=f'เรื่อง "{issue["title"]}" เปลี่ยนปลายทางเป็น "{dest_label}"',
                    entity_type="issue", entity_id=issue_id,
                    actor_id=user_id,
                )
            # ถ้าเปลี่ยนระดับ → แจ้งผู้รับเรื่องในระดับใหม่ด้วย (badge "เรื่องที่รับ")
            if level_changed:
                receivers = (
                    await _council_ids(conn) if target_level == "council"
                    else await _room_receiver_ids(conn, issue["room_id"])
                )
                await notify_bulk(
                    conn, receivers,
                    group_type="issue_received", type="issue_new",
                    title="เรื่องใหม่ในระดับของคุณ",
                    body=f'มีเรื่องใหม่ "{issue["title"]}" (เปลี่ยนปลายทางจาก {old_destination})',
                    entity_type="issue", entity_id=issue_id,
                    actor_id=user_id,
                )


async def update_issue(
    pool: asyncpg.Pool,
    user_id: int,
    issue_id: int,
    *,
    main_category: Optional[str] = None,
    category: Optional[str] = None,
    title: Optional[str] = None,
    description: Optional[str] = None,
    is_anonymous: Optional[bool] = None,
) -> None:
    """
    แก้ไขเรื่องโดยผู้แจ้ง (หรือ admin)
    - แก้ได้เฉพาะตอนสถานะยังไม่ปิด: pending / in_progress / escalated
      (ปิดแล้ว = resolved / cancelled / rejected → ห้ามแก้)
    - PATCH: รับเฉพาะฟิลด์ที่ส่งมา (exclude_unset) — อย่าเขียนทับค่าที่ไม่ได้ส่ง
    - ถ้าเปิดเผยชื่อ (is_anonymous True→False) และ reporter_name ว่าง → re-snapshot จาก students
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            # SELECT ... FOR UPDATE กัน TOCTOU กับ resolve/cancel/accept (ทุกอัน UPDATE แถวนี้)
            issue = await conn.fetchrow(
                "SELECT * FROM issues WHERE id = $1 AND deleted_at IS NULL FOR UPDATE",
                issue_id
            )
            if not issue:
                raise NotFoundError("ไม่พบเรื่องนี้")

            # 1) สิทธิ์: ผู้แจ้งเท่านั้น (+ admin bypass ตาม _is_admin)
            if issue["reporter_id"] != user_id and not await _is_admin(conn, user_id):
                raise ForbiddenError("เฉพาะผู้แจ้งเรื่องเท่านั้นที่แก้ไขเรื่องนี้ได้")

            # 2) สถานะปิด → แก้ไม่ได้
            if issue["status"] in ("resolved", "cancelled", "rejected"):
                raise ValidationError(
                    "เรื่องนี้อยู่ในสถานะปิดแล้ว (แก้ไขเสร็จ/ยกเลิก/ถูกปัดตก) — แก้ไขข้อมูลไม่ได้"
                )

            # 3) เก็บเฉพาะฟิลด์ที่ส่ง
            changed = {}
            if main_category is not None:
                changed["main_category"] = main_category
            if category is not None:
                changed["category"] = category
            if title is not None:
                changed["title"] = title
            if description is not None:
                changed["description"] = description
            if is_anonymous is not None:
                changed["is_anonymous"] = is_anonymous
            if not changed:
                raise ValidationError("ไม่มีข้อมูลที่ต้องการแก้ไข")

            # 4) re-validate หมวดหมู่กับคู่ที่มีผลจริง (อ้างอิง DB ถ้า field นั้นไม่ส่ง)
            eff_main = changed.get("main_category", issue["main_category"])
            eff_cat = changed.get("category", issue["category"])
            if not is_valid_category(eff_main, eff_cat):
                raise ValidationError(
                    f"หมวดหมู่ไม่ถูกต้อง: หมวดหลัก '{eff_main}' ไม่มีหมวดย่อย '{eff_cat}'"
                )

            # 5) dynamic SET — $1 สงวนไว้ WHERE id, field ถัดไปเริ่ม $len+1
            params = [issue_id]
            sets = []
            for key in ("main_category", "category", "title", "description", "is_anonymous"):
                if key in changed:
                    sets.append(f"{key} = ${len(params) + 1}")
                    params.append(changed[key])

            # 6) is_anonymous True→False: re-snapshot reporter_name ถ้ายังว่าง
            #    ใช้ reporter_id/reporter_room_id ของเรื่อง (ไม่ใช่ actor — admin แก้แทนได้)
            new_is_anonymous = changed.get("is_anonymous", issue["is_anonymous"])
            if issue["is_anonymous"] and not new_is_anonymous and not issue["reporter_name"]:
                reporter_room_id = issue["reporter_room_id"] or issue["room_id"]
                reporter_name = await _student_display_name(conn, issue["reporter_id"], reporter_room_id)
                if reporter_name:
                    sets.append(f"reporter_name = ${len(params) + 1}")
                    params.append(reporter_name)
                    changed["reporter_name"] = reporter_name

            sets.append("updated_at = NOW()")
            await conn.execute(
                f"UPDATE issues SET {', '.join(sets)} WHERE id = $1",
                *params
            )

            # 7) บันทึกใน status_history ว่าโดนแก้ (mirror create_issue)
            await conn.execute(
                """
                INSERT INTO issue_status_history (issue_id, status, changed_by, note)
                VALUES ($1, $2, $3, $4)
                """,
                issue_id, issue["status"], user_id, "ผู้แจ้งแก้ไขข้อมูลเรื่อง"
            )

            # 8) audit log ใน transaction เดียวกัน (ตามกฎ backend.md)
            old = {k: issue[k] for k in changed if k != "reporter_name"}
            new = {k: changed[k] for k in old}
            if "reporter_name" in changed:
                old["reporter_name"] = issue["reporter_name"]
                new["reporter_name"] = changed["reporter_name"]
            from core.logger import AuditLogger
            await AuditLogger("issue_service").log(
                conn=conn, action="UPDATE_ISSUE",
                actor_identifier=str(user_id), client_source="web",
                room_id=issue["room_id"], user_id=user_id,
                entity_type="issue", entity_id=issue_id,
                old_values=old, new_values=new,
            )


async def _assert_can_view(conn, pool: asyncpg.Pool, user_id: int, issue_row) -> None:
    """ตรวจว่า user มองเห็นเรื่องนี้ได้ไหม (พีระมิด + อดีตผู้รับ/ผู้เกี่ยวข้อง + ครูระดับชั้น)
    ใช้ร่วมกันระหว่าง get_issue และคอมเมนต์ เพื่อไม่ให้ visibility rule เบน"""
    level = await user_level(pool, user_id)
    involved = await _is_involved(conn, user_id, issue_row)
    visible = can_see(level, issue_row["current_level"], issue_row["reporter_id"], user_id, issue_row["is_anonymous"]) or involved

    # จำกัดระดับชั้น (grade scope): ครูทั่วไป (staff_level) + ประธานระดับ/ผู้ช่วยหัวหน้าระดับ (rooms.level)
    # เห็นได้เฉพาะเรื่องของห้องในระดับชั้นตัวเอง — ยกเว้นเรื่องที่เกี่ยวข้อง/จัดการอยู่
    # (แก้บั๊กเดิม: หัวหน้าระดับเห็นเรื่องทุกชั้นได้ — scope ต้องจำกัดเหมือนครู)
    grade = await get_user_grade_scope(conn, user_id)
    if grade:
        issue_grade = await _room_level(conn, issue_row["room_id"])
        if issue_grade != grade and not involved:
            visible = False

    if not visible:
        raise ForbiddenError("คุณไม่มีสิทธิ์ดูเรื่องนี้")


async def get_issue(pool: asyncpg.Pool, user_id: int, issue_id: int) -> Optional[dict]:
    """ดึงปัญหาตาม id (ตรวจ visibility)"""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                i.*,
                r.room_name,
                reporter_r.room_name AS reporter_room,
                u.full_name AS assignee_name
            FROM issues i
            JOIN rooms r ON r.id = i.room_id
            LEFT JOIN rooms reporter_r ON reporter_r.id = i.reporter_room_id
            LEFT JOIN users u ON u.id = i.current_assignee_id
            WHERE i.id = $1 AND i.deleted_at IS NULL
            """,
            issue_id
        )
        if not row:
            raise NotFoundError("ไม่พบเรื่องนี้")

        # ตรวจ visibility (พีระมิด + อดีตผู้รับ/ผู้เกี่ยวข้อง)
        await _assert_can_view(conn, pool, user_id, row)

        # ดึงรายละเอียดเสริม
        steps = await conn.fetch(
            "SELECT * FROM issue_steps WHERE issue_id = $1 ORDER BY step_order",
            issue_id
        )
        countdown = await conn.fetchrow(
            "SELECT * FROM issue_countdowns WHERE issue_id = $1 ORDER BY id DESC LIMIT 1",
            issue_id
        )
        escalations = await conn.fetch(
            """
            SELECT e.*, fu.full_name AS from_name, tu.full_name AS to_name
            FROM issue_escalations e
            LEFT JOIN users fu ON fu.id = e.from_assignee_id
            LEFT JOIN users tu ON tu.id = e.to_assignee_id
            WHERE e.issue_id = $1 ORDER BY e.created_at
            """,
            issue_id
        )
        history = await conn.fetch(
            "SELECT * FROM issue_status_history WHERE issue_id = $1 ORDER BY created_at",
            issue_id
        )
        comments = await conn.fetch(
            """
            SELECT * FROM issue_comments
            WHERE issue_id = $1 AND deleted_at IS NULL
            ORDER BY created_at, id
            """,
            issue_id
        )

        result = _issue_to_dict(row, with_details=True)
        result["steps"] = [_step_to_dict(s) for s in steps]
        result["countdown"] = _countdown_to_dict(countdown) if countdown else None
        result["escalations"] = [_esc_to_dict(e) for e in escalations]
        result["status_history"] = [_history_to_dict(h) for h in history]
        result["comments"] = [_comment_to_dict(c) for c in comments]
        return result


async def list_issues(
    pool: asyncpg.Pool,
    user_id: int,
    *,
    only_mine: bool = False,
    received: bool = False,
    status_filter: Optional[str] = None,
    category: Optional[str] = None,
    main_category: Optional[str] = None,
    level_filter: Optional[str] = None,
    levels: Optional[str] = None,
    q: Optional[str] = None,
    sort: str = "desc",
    limit: int = 100,
    offset: int = 0,
) -> dict:
    """
    รายการปัญหา — filter visibility ตามระดับผู้ใช้ + ค้นหา + แบ่งหน้า

    received=True: "เรื่องที่รับ / ระดับฉัน" — เริ่มจากระดับตัวเองพอดี (EXACT LEVEL MATCH):
       room→เฉพาะห้องตัวเองระดับ room, level→เฉพาะระดับชั้นตัวเองระดับ level, council→เฉพาะระดับ council
       ถ้าเลือก `levels` (comma เช่น "room,level") → ขยายดูระดับล่างลงมาตามพีระมิด (มองลงได้เท่านั้น)
       ขอบเขตห้อง/ระดับชั้นของผู้ดูยังบังคับเหมือนเดิม (room→ห้องตัวเอง, level→ชั้นตัวเอง, council→ทั้งโรงเรียน)
    main_category: กรองตามหมวดหลัก (suggestion / wellbeing / report) — ใช้จาก Dashboard
    level_filter: จำกัดให้ดูเฉพาะระดับที่เลือก (room/level/council) — ใช้กับ list ปกติ (received=False)
    levels: ระดับที่อยากดูใน received mode (comma, เช่น "room,level") — เฉพาะ ≤ ระดับตัวเองเท่านั้น;
       ไม่ส่ง = ระดับตัวเองพอดี (พฤติกรรมเดิม)
    q: ค้นหาแบบคำต่อคำ (ILIKE partial match) ในชื่อเรื่อง/คำอธิบาย/ห้อง/ชื่อคน —
       อยู่ในขอบเขต visibility เดียวกับ list ปกติ (ค้นได้เฉพาะที่ตัวเองมองเห็น)
    sort: 'asc' = เก่าไปใหม่, 'desc' (default) = ใหม่ไปเก่า
    คืน {"items": [...], "total": N} — total นับก่อน limit/offset (COUNT(*) OVER())
    """
    level = await user_level(pool, user_id)

    async with pool.acquire() as conn:
        # เช็คว่า user อยู่ในห้องไหนบ้าง
        rooms = await conn.fetch(
            "SELECT room_id FROM students WHERE user_id = $1 AND deleted_at IS NULL AND status = 'active'",
            user_id
        )
        room_ids = [r["room_id"] for r in rooms]

        where = ["i.deleted_at IS NULL"]
        params = []

        # ---- ประยุกต์ use-case ----
        if only_mine:
            # เรื่องที่ฉันแจ้งเท่านั้น (ไม่ต้องสร้าง visible_cond — กัน param เกิน)
            params.append(user_id)
            where.append(f"i.reporter_id = ${len(params)}")
        elif received:
            # 🎯 "เรื่องที่รับ / ระดับฉัน" — EXACT LEVEL MATCH (เรื่องที่อยู่ระดับของตัวเองพอดี)
            # ห้ามดึงเรื่องระดับต่ำกว่าติดมาด้วย (level ของ room/level จะถูกจำกัดด้านล่าง)
            teacher_level = await _teacher_scope(conn, user_id)
            if teacher_level:
                # 👩‍🏫 ครูทั่วไป: คงเดิม — เห็นทุก escalation level ภายในระดับชั้นตัวเอง (staff_level)
                teacher_room_ids = await _level_room_ids(conn, teacher_level)
                if not teacher_room_ids:
                    where.append("1 = 0")
                else:
                    params.append(tuple(teacher_room_ids))
                    pyramid_cond = f"i.room_id = ANY(${len(params)})"
                    params.append(user_id)
                    involved_cond = (
                        f"i.reporter_id = ${len(params)}"
                        f" OR i.current_assignee_id = ${len(params)}"
                        f" OR EXISTS (SELECT 1 FROM issue_escalations e WHERE e.issue_id = i.id AND e.from_assignee_id = ${len(params)})"
                        f" OR EXISTS (SELECT 1 FROM issue_countdowns cd WHERE cd.issue_id = i.id AND cd.assignee_id = ${len(params)})"
                    )
                    where.append(f"({pyramid_cond} OR ({involved_cond}))")
            elif level == "student":
                # นักเรียนไม่มี "เรื่องที่รับ" — ไม่เห็นเรื่องคนอื่น
                where.append("1 = 0")
            else:
                # 🎯 ระดับ room/level/council — เริ่มจากระดับตัวเองพอดี แล้วมองลงได้ตามพีระมิด
                # (student ถูกกรองออกด้านบนแล้ว — ตรงนี้คือ room/level/council เท่านั้น)
                # band = ทุกระดับที่มองเห็น (ตาม LEVEL_RANK); scope_room_ids จำกัดห้องตอนมองระดับล่าง
                band = [lv for lv in LEVEL_ORDER if LEVEL_RANK[lv] <= LEVEL_RANK[level]]
                if levels:
                    # รับเฉพาะที่อยู่ใน band (ตัดระดับที่สูงกว่า/ไม่รู้จักออก) — ถ้าเหลือว่าง = fail-closed
                    req = {lv for lv in levels.split(",") if lv and lv in LEVEL_ORDER} & set(band)
                else:
                    req = {level}  # default = ระดับตัวเองพอดี (EXACT LEVEL MATCH เดิม)
                # ขอบเขตห้องสำหรับระดับ room/level:
                #   room   → เฉพาะห้องของตัวเอง
                #   level  → เฉพาะระดับชั้นของตัวเอง (grade scope) / [] fail-closed
                #   council→ None = ทั้งโรงเรียน (มองระดับล่างได้ทุกห้อง)
                scope_room_ids: Optional[list] = None
                if level == "room":
                    scope_room_ids = room_ids
                elif level == "level":
                    grade = await get_user_grade_scope(conn, user_id)
                    scope_room_ids = await _level_room_ids(conn, grade) if grade else []
                # OR เงื่อนไขรายระดับที่เลือก (ไม่อ้าง `params` เกิน — ใช้ literal สำหรับค่าคงที่ระดับ)
                conds = []
                for lv in LEVEL_ORDER:
                    if lv not in req:
                        continue
                    if lv == "council":
                        conds.append("i.current_level = 'council'")
                    elif scope_room_ids is None:
                        conds.append(f"i.current_level = '{lv}'")
                    elif scope_room_ids:
                        params.append(tuple(scope_room_ids))
                        conds.append(f"(i.current_level = '{lv}' AND i.room_id = ANY(${len(params)}))")
                    # scope_room_ids == [] → ข้าม (fail-closed — มองไม่เห็นห้องใดเลย)
                if not conds:
                    where.append("1 = 0")
                else:
                    where.append("(" + " OR ".join(conds) + ")")
        else:
            # 👩‍🏫 ครูทั่วไป: เห็นเฉพาะเรื่องของระดับชั้นตัวเอง (พีระมิดสูงสุดแต่จำกัดชั้น)
            teacher_level = await _teacher_scope(conn, user_id)
            if teacher_level:
                teacher_room_ids = await _level_room_ids(conn, teacher_level)
                if not teacher_room_ids:
                    # ไม่มีห้องในระดับชั้นที่ดูแล → ไม่เห็นเรื่องใดเลย
                    where.append("1 = 0")
                else:
                    params.append(tuple(teacher_room_ids))
                    pyramid_cond = f"i.room_id = ANY(${len(params)})"
                    # + เรื่องที่เกี่ยวข้อง (เคยรับ/แจ้งเอง) แม้คนละระดับชั้น
                    params.append(user_id)
                    involved_cond = (
                        f"i.reporter_id = ${len(params)}"
                        f" OR i.current_assignee_id = ${len(params)}"
                        f" OR EXISTS (SELECT 1 FROM issue_escalations e WHERE e.issue_id = i.id AND e.from_assignee_id = ${len(params)})"
                        f" OR EXISTS (SELECT 1 FROM issue_countdowns cd WHERE cd.issue_id = i.id AND cd.assignee_id = ${len(params)})"
                    )
                    visible_cond = f"({pyramid_cond} OR ({involved_cond}))"
                    where.append(visible_cond)
            elif level == "student":
                # นักเรียนเห็นเรื่องของตัวเอง (รวม anonymous — ติดตามสถานะได้)
                params.append(user_id)
                visible_cond = f"i.reporter_id = ${len(params)}"
                where.append(visible_cond)
            else:
                # ระดับสูงกว่ามองลงได้ทุกระดับต่ำกว่า (พีระมิด)
                level_num = LEVEL_RANK.get(level, 1)  # 1=room, 2=level, 3=council
                params.append(level_num)
                pyramid_cond = (
                    f"CASE i.current_level WHEN 'room' THEN 1 WHEN 'level' THEN 2 WHEN 'council' THEN 3 ELSE 0 END <= ${len(params)}"
                )
                if room_ids and level == "room":
                    # ห้องของ user (สำหรับเรื่องในระดับ room)
                    params.append(tuple(room_ids))
                    pyramid_cond += f" AND i.room_id = ANY(${len(params)})"
                elif level == "level":
                    # 🛡️ หัวหน้าระดับ/ผู้ช่วย: จำกัดเฉพาะระดับชั้นของตัวเอง (rooms.level)
                    # แก้บั๊กเดิมที่เห็นเรื่องของทุกชั้น — scope เท่ากับ teacher (staff_level) แต่ดึงจากห้องตัวเอง
                    grade = await get_user_grade_scope(conn, user_id)
                    if grade:
                        lvl_room_ids = await _level_room_ids(conn, grade)
                        if lvl_room_ids:
                            params.append(tuple(lvl_room_ids))
                            pyramid_cond += f" AND i.room_id = ANY(${len(params)})"
                        else:
                            pyramid_cond += " AND 1 = 0"
                    else:
                        # หา grade ไม่เจอ → มองเห็นได้เฉพาะเรื่องที่เกี่ยวข้อง (involved) — fail-closed
                        pyramid_cond += " AND 1 = 0"

                # + เรื่องที่ user เกี่ยวข้อง (เคยรับ/อยู่ในห้องผู้แจ้ง) แม้ถูก escalate ขึ้นไปแล้ว
                params.append(user_id)
                involved_cond = (
                    f"i.reporter_id = ${len(params)}"
                    f" OR i.current_assignee_id = ${len(params)}"
                    f" OR EXISTS (SELECT 1 FROM issue_escalations e WHERE e.issue_id = i.id AND e.from_assignee_id = ${len(params)})"
                    f" OR EXISTS (SELECT 1 FROM issue_countdowns cd WHERE cd.issue_id = i.id AND cd.assignee_id = ${len(params)})"
                )
                visible_cond = f"({pyramid_cond} OR ({involved_cond}))"
                where.append(visible_cond)

        # ---- ตัวกรอง ----
        if status_filter:
            # รองรับหลายสถานะคั่นด้วย "," (เช่น "pending,in_progress,escalated")
            # ใช้กับฟิลเตอร์ "ยังไม่เสร็จ" ของหน้า ReceivedIssues — กรองฝั่ง server ไม่ใช่ตัด client
            status_list = [s.strip() for s in status_filter.split(",") if s.strip()]
            if len(status_list) > 1:
                params.append(status_list)
                where.append(f"i.status = ANY(${len(params)}::text[])")
            else:
                params.append(status_filter)
                where.append(f"i.status = ${len(params)}")
        if category:
            # รองรับหลายหมวดคั่นด้วย "," (เช่น "academic,discipline") — ใช้กับหน้า "เรื่องที่รับ ระดับฉัน"
            # ที่กรองตามหน้าที่รับผิดชอบ (responsibilities) ซึ่งอาจมีหลายหมวด
            cat_list = [c.strip() for c in category.split(",") if c.strip()]
            if not cat_list:
                raise ValueError("หมวดหมู่ไม่ถูกต้อง: ต้องระบุอย่างน้อย 1 หมวด")
            if len(cat_list) > 1:
                params.append(cat_list)
                where.append(f"i.category = ANY(${len(params)}::text[])")
            else:
                params.append(cat_list[0])
                where.append(f"i.category = ${len(params)}")
        if main_category:
            # ตรวจหมวดหลัก (กันค่าแปลก → 400 แทน 500)
            if main_category not in all_main_category_codes():
                raise ValueError(f"หมวดหลักไม่ถูกต้อง: {main_category}")
            params.append(main_category)
            where.append(f"i.main_category = ${len(params)}")
        if level_filter:
            # กรองตามระดับปัจจุบันของเรื่อง (ถ้าระบุ) — ต้องอยู่ในระดับที่มองเห็นเท่านั้น
            if level_filter not in LEVEL_ORDER:
                raise ValueError(f"ระดับไม่ถูกต้อง: {level_filter}")
            params.append(level_filter)
            where.append(f"i.current_level = ${len(params)}")

        # ---- 🔍 ค้นหาแบบคำต่อคำ (ILIKE partial match) — ต่อ AFTER visibility กันค้นข้ามระดับ ----
        # ทุกคำ (แยกด้วยช่องว่าง) ต้องเจออย่างน้อย 1 ใน 6 ฟิลด์: ชื่อเรื่อง / คำอธิบาย / ห้อง / ชื่อคน
        # ใช้ $n เดียวซ้ำใน OR ได้ — ทุกตำแหน่งเป็น text จึงปลอดภัยกับ asyncpg
        if q:
            for token in q.split():
                esc = _escape_like(token)
                if not esc:
                    continue
                params.append(f"%{esc}%")
                n = len(params)
                where.append(
                    f"(i.title ILIKE ${n} ESCAPE '\\'"
                    f" OR i.description ILIKE ${n} ESCAPE '\\'"
                    f" OR r.room_name ILIKE ${n} ESCAPE '\\'"
                    f" OR reporter_r.room_name ILIKE ${n} ESCAPE '\\'"
                    f" OR COALESCE(i.reporter_name, '') ILIKE ${n} ESCAPE '\\'"
                    f" OR COALESCE(u.full_name, '') ILIKE ${n} ESCAPE '\\')"
                )

        # เก็บ params ของตัวกรองไว้ก่อน (ไม่รวม limit/offset) — ใช้กับ count query ตอนหน้าว่าง
        filter_params = list(params)

        params.append(limit)
        params.append(offset)
        sql = f"""
            SELECT
                i.id, i.room_id, i.main_category, i.category, i.title, i.description,
                i.image_url, i.reporter_id, i.reporter_name, i.current_level,
                i.current_assignee_id, i.current_assignee_role, i.status, i.priority,
                i.is_anonymous, i.resolved_at, i.created_at, i.updated_at,
                i.requested_destination, i.published_board_id,
                r.room_name,
                reporter_r.room_name AS reporter_room,
                u.full_name AS assignee_name,
                COUNT(*) OVER() AS total_count
            FROM issues i
            JOIN rooms r ON r.id = i.room_id
            LEFT JOIN rooms reporter_r ON reporter_r.id = i.reporter_room_id
            LEFT JOIN users u ON u.id = i.current_assignee_id
            WHERE {' AND '.join(where)}
            ORDER BY i.created_at {'ASC' if sort == 'asc' else 'DESC'}, i.id {'ASC' if sort == 'asc' else 'DESC'}
            LIMIT ${len(params)-1} OFFSET ${len(params)}
        """
        rows = await conn.fetch(sql, *params)

        # total: ปกติได้จาก COUNT(*) OVER() (แถวแรก) — แต่ถ้า offset เลยข้อมูล (rows ว่าง)
        # window function อ่านค่าไม่ได้ → นับแยกด้วย query เดียวกัน (ไม่มี limit/offset)
        if rows:
            total = rows[0]["total_count"]
        else:
            total = await conn.fetchval(
                f"""
                SELECT COUNT(*)
                FROM issues i
                JOIN rooms r ON r.id = i.room_id
                LEFT JOIN rooms reporter_r ON reporter_r.id = i.reporter_room_id
                LEFT JOIN users u ON u.id = i.current_assignee_id
                WHERE {' AND '.join(where)}
                """,
                *filter_params
            )

    return {"items": [_issue_to_dict(r) for r in rows], "total": total}


# ลำดับสถานะมาตรฐาน (zero-fill หน้า Welcome) — เรียงตามชีวิตของเรื่อง
_MY_SUMMARY_STATUS_ORDER = ["pending", "in_progress", "escalated", "rejected", "resolved", "cancelled"]


async def my_issue_summary(pool: asyncpg.Pool, user_id: int) -> dict:
    """
    สรุปเรื่องที่ฉันแจ้ง (ทุกบทบาทใช้ได้ — ทุกคนแจ้งเรื่องได้):
    - total_issues: จำนวนรวม
    - by_status: นับแยกตามสถานะทั้ง 6 (zero-fill) — query GROUP BY + เติม 0 ฝั่ง Python
    - recent: 5 เรื่องล่าสุดของฉัน (เรียง created_at DESC)

    1 query กลุ่ม + 1 query ล่าสุด — แทนการเรียก GET /api/issues?mine=true หลายครั้ง
    """
    async with pool.acquire() as conn:
        status_rows = await conn.fetch(
            """
            SELECT status, COUNT(*)::int AS count
            FROM issues
            WHERE deleted_at IS NULL AND reporter_id = $1
            GROUP BY status
            """,
            user_id,
        )
        counts = {r["status"]: int(r["count"]) for r in status_rows}
        total = sum(counts.values())
        by_status = [
            {"status": st, "count": int(counts.get(st, 0))}
            for st in _MY_SUMMARY_STATUS_ORDER
        ]

        recent_rows = await conn.fetch(
            """
            SELECT
                i.id, i.room_id, i.main_category, i.category, i.title, i.description,
                i.image_url, i.reporter_id, i.reporter_name, i.current_level,
                i.current_assignee_id, i.current_assignee_role, i.status, i.priority,
                i.is_anonymous, i.resolved_at, i.created_at, i.updated_at,
                i.requested_destination, i.published_board_id,
                r.room_name,
                reporter_r.room_name AS reporter_room,
                u.full_name AS assignee_name
            FROM issues i
            JOIN rooms r ON r.id = i.room_id
            LEFT JOIN rooms reporter_r ON reporter_r.id = i.reporter_room_id
            LEFT JOIN users u ON u.id = i.current_assignee_id
            WHERE i.deleted_at IS NULL AND i.reporter_id = $1
            ORDER BY i.created_at DESC, i.id DESC
            LIMIT 5
            """,
            user_id,
        )

    return {
        "total_issues": total,
        "by_status": by_status,
        "recent": [_issue_to_dict(r) for r in recent_rows],
    }


def _issue_to_dict(row, with_details=False) -> dict:
    """แปลงแถว issues → dict ตาม IssueOut shape"""
    d = {
        "id": row["id"],
        "room_id": row["room_id"],
        "room_name": row.get("room_name"),
        "main_category": row["main_category"],
        "category": row["category"],
        "title": row["title"],
        "description": row["description"],
        "image_url": row["image_url"],
        "reporter_id": row["reporter_id"],
        "reporter_name": row["reporter_name"] if not row["is_anonymous"] else None,
        "reporter_room": row.get("reporter_room") if not row["is_anonymous"] else None,
        "current_level": row["current_level"],
        "current_assignee_id": row["current_assignee_id"],
        "current_assignee_role": row["current_assignee_role"],
        "current_assignee_name": row.get("assignee_name"),
        "status": row["status"],
        "priority": row["priority"],
        "is_anonymous": row["is_anonymous"],
        "requested_destination": row.get("requested_destination", "normal"),
        "published_board_id": row.get("published_board_id"),
        "resolved_at": row["resolved_at"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
    if with_details:
        d["steps"] = []
        d["countdown"] = None
        d["escalations"] = []
        d["status_history"] = []
        d["comments"] = []
    return d


# ============================================================
# 👤 รับเรื่อง + Countdown
# ============================================================
async def accept_issue(pool: asyncpg.Pool, user_id: int, issue_id: int, estimated_days: int) -> None:
    """รับเรื่อง + ตั้ง countdown (วันใช้แก้ปัญหา)"""
    async with pool.acquire() as conn:
        async with conn.transaction():
            issue = await conn.fetchrow(
                "SELECT * FROM issues WHERE id = $1 AND deleted_at IS NULL",
                issue_id
            )
            if not issue:
                raise NotFoundError("ไม่พบเรื่องนี้")

            # ตรวจว่า "ระดับสูงกว่าหรือเท่ากัน" กับ current_level (พีระมิดมองลง):
            # - ระดับที่สูงกว่า (ประธานระดับ/สภา/แอดมิน) กดรับแทนหัวหน้าห้องในระดับนั้นได้เลย
            #   ไม่ต้องรอให้หัวหน้าห้องรับก่อน (ความต้องการปี 2026-08-26)
            # - เรื่องระดับ 'room': ถ้าผู้รับมีระดับสูงสุดแค่ 'room' ต้องเป็นสมาชิกห้องของเรื่อง
            # - ครูทั่วไป: scope จำกัดเฉพาะห้องในระดับชั้นตัวเอง (staff_level) — บังคับเสมอ
            my_level = await user_level(pool, user_id, room_id=None)
            can_accept = LEVEL_RANK.get(my_level, 0) >= LEVEL_RANK.get(issue["current_level"], 1)

            # ระดับ 'room' เท่ากัน (หัวหน้าห้อง/รองของห้องอื่น) → ห้ามรับเรื่องห้องอื่น
            if (
                can_accept
                and issue["current_level"] == "room"
                and LEVEL_RANK.get(my_level, 0) == LEVEL_RANK["room"]
            ):
                if not await _user_role_in(conn, user_id, issue["room_id"]):
                    can_accept = False

            # จำกัดระดับชั้น (grade scope): ครูทั่วไป (staff_level) + ประธานระดับ/ผู้ช่วยหัวหน้าระดับ (rooms.level)
            # รับได้เฉพาะเรื่องที่ห้องอยู่ในระดับชั้นตัวเอง (ยกเว้นเรื่องระดับสภา — เดิมรับได้ทุกเรื่อง)
            # (แก้บั๊กเดิม: หัวหน้าระดับรับเรื่องห้องทุกชั้นได้ — ต้องจำกัดเหมือนครู)
            grade = await get_user_grade_scope(conn, user_id)
            if grade and issue["current_level"] != "council":
                issue_room_level = await _room_level(conn, issue["room_id"])
                if issue_room_level != grade:
                    can_accept = False

            if not can_accept:
                raise ForbiddenError("เรื่องนี้ไม่อยู่ในระดับของคุณ")

            # ตรวจว่ายังไม่มีคนรับ
            if issue["current_assignee_id"]:
                raise ValidationError("เรื่องนี้มีผู้รับอยู่แล้ว")

            now = datetime.now(timezone.utc)
            deadline = now + timedelta(days=estimated_days)

            await conn.execute(
                """
                UPDATE issues
                SET current_assignee_id = $1, status = 'in_progress', updated_at = NOW()
                WHERE id = $2
                """,
                user_id, issue_id
            )
            # role ของผู้รับ (ครูที่รับข้ามห้อง → ระบุเป็น role จริง/teacher)
            role = await _user_role_in(conn, user_id, issue["room_id"])
            if not role:
                role = await conn.fetchval(
                    """
                    SELECT class_role FROM students
                    WHERE user_id = $1 AND deleted_at IS NULL AND status = 'active'
                    ORDER BY id LIMIT 1
                    """,
                    user_id
                ) or "teacher"
            await conn.execute(
                "UPDATE issues SET current_assignee_role = $1 WHERE id = $2",
                role, issue_id
            )

            await conn.execute(
                """
                INSERT INTO issue_countdowns (issue_id, assignee_id, estimated_days, deadline)
                VALUES ($1, $2, $3, $4)
                """,
                issue_id, user_id, estimated_days, deadline
            )
            await conn.execute(
                """
                INSERT INTO issue_status_history (issue_id, status, changed_by, note)
                VALUES ($1, 'in_progress', $2, $3)
                """,
                issue_id, user_id, f"รับเรื่อง (ตั้งเวลา {estimated_days} วัน)"
            )

            # 🛡️ Audit log (ภายใน transaction เดียว)
            from core.logger import AuditLogger
            await AuditLogger("issue_service").log(
                conn=conn, action="ACCEPT_ISSUE",
                actor_identifier=str(user_id), client_source="web",
                room_id=issue["room_id"], user_id=user_id,
                entity_type="issue", entity_id=issue_id,
                old_values={"current_assignee_id": None, "status": issue["status"]},
                new_values={
                    "current_assignee_id": user_id, "current_assignee_role": role,
                    "status": "in_progress", "estimated_days": estimated_days,
                },
            )

            # 🔔 แจ้งผู้แจ้งเรื่องว่ารับงานแล้ว (badge "เรื่องของฉัน")
            if issue["reporter_id"]:
                actor_display = await _user_display_name(conn, user_id) or "ผู้รับเรื่อง"
                await notify(
                    conn, user_id=issue["reporter_id"],
                    group_type="issue_mine", type="issue_update",
                    title="อัปเดตสถานะเรื่อง",
                    body=f'เรื่อง "{issue["title"]}" ถูก {actor_display} รับไปดำเนินการแล้ว (ตั้งเวลา {estimated_days} วัน)',
                    entity_type="issue", entity_id=issue_id,
                    actor_id=user_id,
                )


async def update_countdown(pool: asyncpg.Pool, user_id: int, issue_id: int, estimated_days: int) -> None:
    """แก้ไข countdown (ยืดเวลา) — ผู้รับเรื่อง หรือ admin/ครูที่จัดการเรื่องได้"""
    async with pool.acquire() as conn:
        async with conn.transaction():
            cd = await conn.fetchrow(
                """
                SELECT cd.id, cd.issue_id, cd.estimated_days, cd.deadline, i.room_id
                FROM issue_countdowns cd
                JOIN issues i ON i.id = cd.issue_id
                WHERE cd.issue_id = $1 AND cd.assignee_id = $2
                ORDER BY cd.id DESC LIMIT 1
                """,
                issue_id, user_id
            )
            if not cd:
                # ผู้รับเรื่องคนอื่น (admin/ครูระดับชั้นของเรื่อง) → แก้ countdown ล่าสุดได้
                issue = await conn.fetchrow(
                    "SELECT id, room_id FROM issues WHERE id = $1 AND deleted_at IS NULL",
                    issue_id
                )
                if not issue:
                    raise NotFoundError("ไม่พบเรื่องนี้")
                if not await _can_manage_issue(conn, user_id, issue):
                    raise NotFoundError("ไม่พบ countdown ของเรื่องนี้")
                cd = await conn.fetchrow(
                    """
                    SELECT cd.id, cd.estimated_days, cd.deadline, i.room_id
                    FROM issue_countdowns cd
                    JOIN issues i ON i.id = cd.issue_id
                    WHERE cd.issue_id = $1
                    ORDER BY cd.id DESC LIMIT 1
                    """,
                    issue_id
                )
                if not cd:
                    raise NotFoundError("ไม่พบ countdown ของเรื่องนี้")

            now = datetime.now(timezone.utc)
            deadline = now + timedelta(days=estimated_days)
            await conn.execute(
                """
                UPDATE issue_countdowns
                SET estimated_days = $1, deadline = $2
                WHERE id = $3
                """,
                estimated_days, deadline, cd["id"]
            )

            # 🛡️ Audit log (ภายใน transaction เดียว)
            from core.logger import AuditLogger
            await AuditLogger("issue_service").log(
                conn=conn, action="UPDATE_COUNTDOWN",
                actor_identifier=str(user_id), client_source="web",
                room_id=cd["room_id"], user_id=user_id,
                entity_type="issue", entity_id=issue_id,
                old_values={"estimated_days": cd["estimated_days"], "deadline": cd["deadline"]},
                new_values={"estimated_days": estimated_days, "deadline": deadline},
            )


# ============================================================
# 🪜 ขั้นตอนการดำเนินงาน (Steps)
# ============================================================
async def add_step(pool: asyncpg.Pool, user_id: int, issue_id: int, step_title: str, step_detail: Optional[str] = None) -> int:
    """เพิ่มขั้นตอนการดำเนินงาน"""
    async with pool.acquire() as conn:
        async with conn.transaction():
            await _ensure_assignee(conn, user_id, issue_id)
            step_order = await conn.fetchval(
                "SELECT COALESCE(MAX(step_order), 0) + 1 FROM issue_steps WHERE issue_id = $1",
                issue_id
            )
            step_id = await conn.fetchval(
                """
                INSERT INTO issue_steps (issue_id, step_title, step_detail, step_order, created_by)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id
                """,
                issue_id, step_title, step_detail, step_order, user_id
            )

            # 🛡️ Audit log (ภายใน transaction เดียว)
            from core.logger import AuditLogger
            await AuditLogger("issue_service").log(
                conn=conn, action="CREATE_STEP",
                actor_identifier=str(user_id), client_source="web",
                user_id=user_id,
                entity_type="issue_step", entity_id=step_id,
                new_values={"issue_id": issue_id, "step_title": step_title, "step_order": step_order},
            )
            return step_id


async def complete_step(pool: asyncpg.Pool, user_id: int, issue_id: int, step_id: int) -> None:
    """ทำขั้นตอนสำเร็จ"""
    async with pool.acquire() as conn:
        async with conn.transaction():
            await _ensure_assignee(conn, user_id, issue_id)
            step = await conn.fetchrow(
                "SELECT id FROM issue_steps WHERE id = $1 AND issue_id = $2",
                step_id, issue_id
            )
            if not step:
                raise NotFoundError("ไม่พบขั้นตอนนี้")

            await conn.execute(
                """
                UPDATE issue_steps
                SET is_completed = TRUE, completed_at = NOW()
                WHERE id = $1
                """,
                step_id
            )

            # 🛡️ Audit log (ภายใน transaction เดียว)
            from core.logger import AuditLogger
            await AuditLogger("issue_service").log(
                conn=conn, action="UPDATE_STEP",
                actor_identifier=str(user_id), client_source="web",
                user_id=user_id,
                entity_type="issue_step", entity_id=step_id,
                old_values={"is_completed": False},
                new_values={"is_completed": True},
            )


# ============================================================
# 🚀 Escalate (ส่งต่อไประดับบน) + Resolve
# ============================================================
async def escalate_issue(pool: asyncpg.Pool, user_id: int, issue_id: int, reason: Optional[str] = None) -> None:
    """ส่งต่อเรื่องไประดับบน (ถ้าเกินความสามารถ/ไม่ทันเวลา)"""
    async with pool.acquire() as conn:
        async with conn.transaction():
            issue = await conn.fetchrow(
                "SELECT * FROM issues WHERE id = $1 AND deleted_at IS NULL",
                issue_id
            )
            if not issue:
                raise NotFoundError("ไม่พบเรื่องนี้")

            # ต้องเป็นผู้รับปัจจุบัน หรือ admin/ครูที่จัดการเรื่องนี้ได้
            if not await _can_manage_issue(conn, user_id, issue):
                raise ForbiddenError("เฉพาะผู้รับเรื่องหรือ admin ที่จะส่งต่อได้")

            next_level = NEXT_LEVEL.get(issue["current_level"])
            if not next_level:
                raise ValidationError("เรื่องนี้อยู่ระดับสูงสุดแล้ว (สภานักเรียน) — ส่งต่อไม่ได้")

            from_assignee = issue["current_assignee_id"]
            await conn.execute(
                """
                INSERT INTO issue_escalations (issue_id, from_level, to_level, from_assignee_id, reason)
                VALUES ($1, $2, $3, $4, $5)
                """,
                issue_id, issue["current_level"], next_level, from_assignee, reason
            )
            await conn.execute(
                """
                UPDATE issues
                SET current_level = $1, current_assignee_id = NULL, current_assignee_role = NULL,
                    status = 'escalated', updated_at = NOW()
                WHERE id = $2
                """,
                next_level, issue_id
            )
            await conn.execute(
                """
                INSERT INTO issue_status_history (issue_id, status, changed_by, note)
                VALUES ($1, 'escalated', $2, $3)
                """,
                issue_id, user_id, f"ส่งต่อไปยังระดับ {next_level}" + (f": {reason}" if reason else "")
            )

            # 🛡️ Audit log (ภายใน transaction เดียว)
            from core.logger import AuditLogger
            await AuditLogger("issue_service").log(
                conn=conn, action="ESCALATE_ISSUE",
                actor_identifier=str(user_id), client_source="web",
                room_id=issue["room_id"], user_id=user_id,
                entity_type="issue", entity_id=issue_id,
                old_values={
                    "current_level": issue["current_level"], "status": issue["status"],
                    "current_assignee_id": issue["current_assignee_id"],
                },
                new_values={
                    "current_level": next_level, "status": "escalated",
                    "current_assignee_id": None, "reason": reason,
                },
            )

            # 🔔 แจ้งผู้แจ้งเรื่องว่าถูกส่งต่อ + ผู้รับเรื่องในระดับใหม่ (badge ตามกลุ่ม)
            level_label = {
                "room": "หัวหน้าห้อง", "level": "ประธานระดับ", "council": "สภานักเรียน",
            }.get(next_level, next_level)
            if issue["reporter_id"]:
                await notify(
                    conn, user_id=issue["reporter_id"],
                    group_type="issue_mine", type="issue_update",
                    title="อัปเดตสถานะเรื่อง",
                    body=f'เรื่อง "{issue["title"]}" ถูกส่งต่อไปยังระดับ {level_label}',
                    entity_type="issue", entity_id=issue_id,
                    actor_id=user_id,
                )
            if next_level == "level":
                new_receivers = await _level_president_ids(conn, await _room_level(conn, issue["room_id"]))
            else:
                new_receivers = await _council_ids(conn)
            await notify_bulk(
                conn, new_receivers,
                group_type="issue_received", type="issue_new",
                title="เรื่องใหม่ในระดับของคุณ",
                body=f'มีเรื่องใหม่ "{issue["title"]}" (ส่งต่อจากระดับ {issue["current_level"]})',
                entity_type="issue", entity_id=issue_id,
                actor_id=user_id,
            )


async def resolve_issue(pool: asyncpg.Pool, user_id: int, issue_id: int, note: Optional[str] = None) -> None:
    """ปิดเรื่อง (แก้ไขเสร็จ)"""
    async with pool.acquire() as conn:
        async with conn.transaction():
            issue = await conn.fetchrow(
                "SELECT * FROM issues WHERE id = $1 AND deleted_at IS NULL",
                issue_id
            )
            if not issue:
                raise NotFoundError("ไม่พบเรื่องนี้")

            # ผู้รับปัจจุบัน หรือ admin/ครูที่จัดการเรื่องนี้ได้
            if not await _can_manage_issue(conn, user_id, issue):
                raise ForbiddenError("เฉพาะผู้รับเรื่องหรือ admin ที่จะปิดเรื่องได้")

            await conn.execute(
                """
                UPDATE issues
                SET status = 'resolved', resolved_at = NOW(), updated_at = NOW()
                WHERE id = $1
                """,
                issue_id
            )
            await conn.execute(
                """
                INSERT INTO issue_status_history (issue_id, status, changed_by, note)
                VALUES ($1, 'resolved', $2, $3)
                """,
                issue_id, user_id, note or "แก้ไขเสร็จสิ้น"
            )

            # 🛡️ Audit log (ภายใน transaction เดียว)
            from core.logger import AuditLogger
            await AuditLogger("issue_service").log(
                conn=conn, action="RESOLVE_ISSUE",
                actor_identifier=str(user_id), client_source="web",
                room_id=issue["room_id"], user_id=user_id,
                entity_type="issue", entity_id=issue_id,
                old_values={"status": issue["status"]},
                new_values={"status": "resolved", "note": note},
            )

            # 🔔 แจ้งผู้แจ้งเรื่องว่าจัดการเสร็จสิ้น (badge "เรื่องของฉัน")
            if issue["reporter_id"]:
                await notify(
                    conn, user_id=issue["reporter_id"],
                    group_type="issue_mine", type="issue_update",
                    title="อัปเดตสถานะเรื่อง",
                    body=f'เรื่อง "{issue["title"]}" ถูกจัดการเสร็จสิ้นแล้ว',
                    entity_type="issue", entity_id=issue_id,
                    actor_id=user_id,
                )


async def cancel_issue(pool: asyncpg.Pool, user_id: int, issue_id: int, reason: Optional[str] = None) -> str:
    """
    ยกเลิก/ปัดตกเรื่อง
    - ผู้แจ้งกดยกเลิก → status='cancelled' (ถูกยกเลิก)
    - ผู้ดูแล (ผู้รับ/admin/ครูระดับชั้น) กดปัดตก → status='rejected' (ถูกปัดตก) — แยกหมวดจากผู้แจ้งยกเลิก
    คืน status ที่ตั้ง เพื่อให้ router ตอบกลับตรงกับสิ่งที่เกิดขึ้น
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            issue = await conn.fetchrow(
                "SELECT * FROM issues WHERE id = $1 AND deleted_at IS NULL",
                issue_id
            )
            if not issue:
                raise NotFoundError("ไม่พบเรื่องนี้")

            # ตรวจว่าเป็นผู้แจ้ง หรือผู้ดูแลเรื่องนี้ได้ (ผู้รับ/admin/ครูระดับชั้น)
            if issue["reporter_id"] != user_id and not await _can_manage_issue(conn, user_id, issue):
                raise ForbiddenError("เฉพาะผู้แจ้งหรือผู้ดูแลเรื่องนี้เท่านั้นที่ยกเลิก/ปัดตกได้")

            # ถ้าเรื่องเสร็จแล้ว/ปิดแล้ว ยกเลิกไม่ได้
            if issue["status"] in ("resolved",):
                raise ValidationError("เรื่องนี้ปิดไปแล้ว — ยกเลิกไม่ได้")

            # ผู้แจ้ง → ถูกยกเลิก, ผู้ดูแล → ถูกปัดตก
            if issue["reporter_id"] == user_id:
                new_status = "cancelled"
                default_note = "ผู้แจ้งยกเลิกเรื่อง"
            else:
                new_status = "rejected"
                default_note = "ถูกปัดตก"

            await conn.execute(
                """
                UPDATE issues
                SET status = $1, updated_at = NOW()
                WHERE id = $2
                """,
                new_status, issue_id
            )
            note = f"{default_note}" + (f": {reason}" if reason else "")
            await conn.execute(
                """
                INSERT INTO issue_status_history (issue_id, status, changed_by, note)
                VALUES ($1, $2, $3, $4)
                """,
                issue_id, new_status, user_id, note
            )

            # 🛡️ Audit log — แยก action ตามผลจริง: ผู้แจ้งยกเลิก → CANCEL_ISSUE, ผู้ดูแลปัดตก → REJECT_ISSUE
            from core.logger import AuditLogger
            await AuditLogger("issue_service").log(
                conn=conn,
                action="CANCEL_ISSUE" if new_status == "cancelled" else "REJECT_ISSUE",
                actor_identifier=str(user_id), client_source="web",
                room_id=issue["room_id"], user_id=user_id,
                entity_type="issue", entity_id=issue_id,
                old_values={"status": issue["status"]},
                new_values={"status": new_status, "note": note},
            )

            # 🔔 ถ้าผู้ดูแลปัดตก → แจ้งผู้แจ้ง (ผู้แจ้งกดยกเลิกเอง → notify self-guard ตัดทิ้ง)
            if new_status == "rejected" and issue["reporter_id"]:
                await notify(
                    conn, user_id=issue["reporter_id"],
                    group_type="issue_mine", type="issue_update",
                    title="อัปเดตสถานะเรื่อง",
                    body=f'เรื่อง "{issue["title"]}" ถูกปัดตกแล้ว' + (f" (เหตุผล: {reason})" if reason else ""),
                    entity_type="issue", entity_id=issue_id,
                    actor_id=user_id,
                )
            return new_status


# ============================================================
# 🧩 Helpers
# ============================================================
async def _user_role_in(conn, user_id: int, room_id: int) -> Optional[str]:
    """หาตำแหน่งของ user ในห้อง"""
    return await conn.fetchval(
        """
        SELECT class_role FROM students
        WHERE user_id = $1 AND room_id = $2 AND deleted_at IS NULL AND status = 'active'
        """,
        user_id, room_id
    )


async def _student_display_name(conn, user_id: int, room_id: Optional[int]) -> Optional[str]:
    """ชื่อแสดงของ user: prefix+first_name+last_name จาก students (fallback users.full_name)
    — students บางแถว (เช่น register_user/self-signup) มี first/last name ว่าง แต่ full_name อยู่ที่ users"""
    row = await conn.fetchrow(
        """
        SELECT
            NULLIF(TRIM(CONCAT_WS(' ', s.prefix, s.first_name, s.last_name)), '') AS student_name,
            u.full_name
        FROM students s
        JOIN users u ON u.id = s.user_id
        WHERE s.user_id = $1
          AND s.room_id = COALESCE($2, s.room_id)
          AND s.deleted_at IS NULL AND s.status = 'active'
        ORDER BY s.id LIMIT 1
        """,
        user_id, room_id
    )
    if not row:
        return None
    return row["student_name"] or row["full_name"]


async def _is_involved(conn, user_id: int, issue_row) -> bool:
    """
    เช็คว่า user เกี่ยวข้องกับเรื่องนี้ไหม (เพื่อดูได้แม้ระดับต่ำกว่าปัจจุบัน):
    - เคยเป็นผู้รับ (จาก escalations.from_assignee_id หรือ countdown assignee)
    - อยู่ในห้องเดียวกับผู้แจ้ง (สมาชิกห้องนั้น เห็นเรื่องที่ออกจากห้องตัวเอง)
    """
    issue_id = issue_row["id"]

    # 1. เคยเป็นผู้รับมาก่อน (escalations / countdowns)
    prev = await conn.fetchval(
        """
        SELECT 1 FROM issue_escalations
        WHERE issue_id = $1 AND from_assignee_id = $2
        UNION ALL
        SELECT 1 FROM issue_countdowns
        WHERE issue_id = $1 AND assignee_id = $2
        LIMIT 1
        """,
        issue_id, user_id
    )
    if prev:
        return True

    # 2. อยู่ในห้องเดียวกับผู้แจ้ง (สำหรับเรื่องที่ยังระดับ room — สมาชิกห้องเห็นเรื่องของห้องตัวเอง)
    reporter_room = issue_row["reporter_room_id"] or issue_row["room_id"]
    if reporter_room:
        in_same_room = await conn.fetchval(
            """
            SELECT 1 FROM students
            WHERE user_id = $1 AND room_id = $2 AND deleted_at IS NULL AND status = 'active'
            """,
            user_id, reporter_room
        )
        if in_same_room:
            return True

    return False


async def _is_admin(conn, user_id: int) -> bool:
    """เช็คว่า user เป็น admin (ในห้องใดก็ได้) หรือ Super Admin"""
    if settings.SUPER_ADMIN_ID and int(user_id) == int(settings.SUPER_ADMIN_ID):
        return True
    row = await conn.fetchrow(
        "SELECT is_admin FROM students WHERE user_id = $1 AND deleted_at IS NULL AND status = 'active'",
        user_id
    )
    return bool(row and row["is_admin"])


async def _ensure_assignee(conn, user_id: int, issue_id: int) -> None:
    """ตรวจว่า user จัดการเรื่องนี้ได้ (ผู้รับปัจจุบัน / admin / ครูระดับชั้นของเรื่อง)"""
    issue = await conn.fetchrow(
        "SELECT current_assignee_id FROM issues WHERE id = $1 AND deleted_at IS NULL",
        issue_id
    )
    if not issue:
        raise NotFoundError("ไม่พบเรื่องนี้")
    if not await _can_manage_issue(conn, user_id, issue):
        raise ForbiddenError("เฉพาะผู้รับเรื่องเท่านั้นที่จัดการขั้นตอนนี้ได้")


# ============================================================
# 💬 คอมเมนต์ (แบบ YouTube) — เพิ่ม/แก้/ลบของตัวเอง
# ============================================================
async def add_comment(pool: asyncpg.Pool, user_id: int, issue_id: int, body: str) -> int:
    """เพิ่มคอมเมนต์ — ต้องมองเห็นเรื่องได้ (visibility เดียวกับ get_issue)
    ชื่อจริง/ห้องของผู้เขียนเป็น snapshot ตอนสร้าง (เสมอ แม้เรื่อง anonymous)"""
    async with pool.acquire() as conn:
        async with conn.transaction():
            issue = await conn.fetchrow(
                "SELECT * FROM issues WHERE id = $1 AND deleted_at IS NULL",
                issue_id
            )
            if not issue:
                raise NotFoundError("ไม่พบเรื่องนี้")
            await _assert_can_view(conn, pool, user_id, issue)

            # snapshot ชื่อจริง/ห้องของผู้เขียน (ใช้ primary row ถ้ามีหลายห้อง)
            c = await conn.fetchrow(
                """
                SELECT
                    NULLIF(TRIM(CONCAT_WS(' ', s.prefix, s.first_name, s.last_name)), '') AS student_name,
                    s.first_name,
                    u.full_name,
                    r.room_name
                FROM students s
                JOIN users u ON u.id = s.user_id
                LEFT JOIN rooms r ON r.id = s.room_id
                WHERE s.user_id = $1 AND s.deleted_at IS NULL AND s.status = 'active'
                ORDER BY s.id LIMIT 1
                """,
                user_id
            )
            commenter_name = (c["student_name"] or c["full_name"]) if c else None
            commenter_room = c["room_name"] if c else None
            # ชื่อจริง (first_name) แยกเก็บ — avatar ใช้ตัวแรกของชื่อ (ไม่ใช่ prefix/ชื่อเล่น)
            commenter_first_name = c["first_name"].strip() if (c and c["first_name"]) else None

            comment_id = await conn.fetchval(
                """
                INSERT INTO issue_comments
                    (issue_id, user_id, commenter_name, commenter_room, commenter_first_name, body)
                VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING id
                """,
                issue_id, user_id,
                commenter_name, commenter_room, commenter_first_name,
                body
            )

            from core.logger import AuditLogger
            await AuditLogger("issue_service").log(
                conn=conn, action="CREATE_COMMENT",
                actor_identifier=str(user_id), client_source="web",
                room_id=issue["room_id"], user_id=user_id,
                entity_type="issue_comment", entity_id=comment_id,
                new_values={"body": body},
            )

            # 🔔 แจ้งผู้แจ้งเรื่อง + ผู้รับเรื่องว่ามีคอมเมนต์ใหม่ (badge "เรื่องของฉัน"/"เรื่องที่รับ")
            comment_actor_name = commenter_name or await _user_display_name(conn, user_id) or "ผู้ใช้"
            # 🛡️ เรื่อง anonymous + ผู้คอมเมนต์เป็นผู้แจ้งเอง → อย่าให้ชื่อผู้แจ้งรั่วผ่าน notification
            # (adversarial review: ถ้าไม่มาสก์ สภาที่รับงานเห็นชื่อจริงผู้แจ้งจาก notification ทันที
            # แม้เรื่องจะ anonymous)
            if issue["is_anonymous"] and issue["reporter_id"] == user_id:
                comment_actor_name = "ไม่ระบุชื่อ"
            if issue["reporter_id"]:
                await notify(
                    conn, user_id=issue["reporter_id"],
                    group_type="issue_mine", type="issue_comment",
                    title="มีความคิดเห็นใหม่",
                    body=f'{comment_actor_name} คอมเมนต์ในเรื่อง "{issue["title"]}"',
                    entity_type="issue", entity_id=issue_id,
                    actor_id=user_id, actor_name=comment_actor_name,
                )
            if issue["current_assignee_id"]:
                await notify(
                    conn, user_id=issue["current_assignee_id"],
                    group_type="issue_received", type="issue_comment",
                    title="มีความคิดเห็นใหม่",
                    body=f'{comment_actor_name} คอมเมนต์ในเรื่อง "{issue["title"]}"',
                    entity_type="issue", entity_id=issue_id,
                    actor_id=user_id, actor_name=comment_actor_name,
                )
            return comment_id


async def _get_own_comment(conn, user_id: int, issue_id: int, comment_id: int):
    """ดึงคอมเมนต์ที่ยังไม่ถูกลบ + ตรวจว่าเป็นของ user เอง (แก้/ลบได้เฉพาะของตัวเอง)"""
    comment = await conn.fetchrow(
        """
        SELECT * FROM issue_comments
        WHERE id = $1 AND issue_id = $2 AND deleted_at IS NULL
        """,
        comment_id, issue_id
    )
    if not comment:
        raise NotFoundError("ไม่พบคอมเมนต์นี้")
    if comment["user_id"] != user_id:
        raise ForbiddenError("เฉพาะผู้เขียนคอมเมนต์เท่านั้นที่แก้ไข/ลบได้")
    return comment


async def update_comment(
    pool: asyncpg.Pool, user_id: int, issue_id: int, comment_id: int, body: str
) -> None:
    """แก้คอมเมนต์ของตัวเอง"""
    async with pool.acquire() as conn:
        async with conn.transaction():
            issue = await conn.fetchrow(
                "SELECT * FROM issues WHERE id = $1 AND deleted_at IS NULL",
                issue_id
            )
            if not issue:
                raise NotFoundError("ไม่พบเรื่องนี้")
            await _assert_can_view(conn, pool, user_id, issue)
            comment = await _get_own_comment(conn, user_id, issue_id, comment_id)

            await conn.execute(
                "UPDATE issue_comments SET body = $1, updated_at = NOW() WHERE id = $2",
                body, comment_id
            )

            from core.logger import AuditLogger
            await AuditLogger("issue_service").log(
                conn=conn, action="UPDATE_COMMENT",
                actor_identifier=str(user_id), client_source="web",
                room_id=issue["room_id"], user_id=user_id,
                entity_type="issue_comment", entity_id=comment_id,
                old_values={"body": comment["body"]},
                new_values={"body": body},
            )


async def delete_comment(
    pool: asyncpg.Pool, user_id: int, issue_id: int, comment_id: int
) -> None:
    """soft delete คอมเมนต์ของตัวเอง (row ยังอยู่ deleted_at = NOW())"""
    async with pool.acquire() as conn:
        async with conn.transaction():
            issue = await conn.fetchrow(
                "SELECT * FROM issues WHERE id = $1 AND deleted_at IS NULL",
                issue_id
            )
            if not issue:
                raise NotFoundError("ไม่พบเรื่องนี้")
            await _assert_can_view(conn, pool, user_id, issue)
            comment = await _get_own_comment(conn, user_id, issue_id, comment_id)

            deleted_id = await conn.fetchval(
                """
                UPDATE issue_comments
                SET deleted_at = NOW()
                WHERE id = $1 AND issue_id = $2 AND deleted_at IS NULL
                RETURNING id
                """,
                comment_id, issue_id
            )
            if deleted_id is None:
                raise NotFoundError("ไม่พบคอมเมนต์นี้")

            from core.logger import AuditLogger
            await AuditLogger("issue_service").log(
                conn=conn, action="DELETE_COMMENT",
                actor_identifier=str(user_id), client_source="web",
                room_id=issue["room_id"], user_id=user_id,
                entity_type="issue_comment", entity_id=comment_id,
                old_values={"body": comment["body"], "commenter_name": comment["commenter_name"]},
            )


async def get_comment(pool: asyncpg.Pool, user_id: int, issue_id: int, comment_id: int) -> dict:
    """ดึงคอมเมนต์เดี่ยว (ตรวจ visibility + ยังไม่ถูกลบ) สำหรับตอบ API"""
    async with pool.acquire() as conn:
        issue = await conn.fetchrow(
            "SELECT * FROM issues WHERE id = $1 AND deleted_at IS NULL",
            issue_id
        )
        if not issue:
            raise NotFoundError("ไม่พบเรื่องนี้")
        await _assert_can_view(conn, pool, user_id, issue)
        row = await conn.fetchrow(
            """
            SELECT * FROM issue_comments
            WHERE id = $1 AND issue_id = $2 AND deleted_at IS NULL
            """,
            comment_id, issue_id
        )
        if not row:
            raise NotFoundError("ไม่พบคอมเมนต์นี้")
        return _comment_to_dict(row)


# ============================================================
# 🔄 แปลงผลลัพธ์
# ============================================================
def _step_to_dict(row) -> dict:
    return {
        "id": row["id"],
        "step_title": row["step_title"],
        "step_detail": row["step_detail"],
        "step_order": row["step_order"],
        "is_completed": row["is_completed"],
        "completed_at": row["completed_at"],
    }


def _countdown_to_dict(row) -> dict:
    now = datetime.now(timezone.utc)
    return {
        "id": row["id"],
        "estimated_days": row["estimated_days"],
        "started_at": row["started_at"],
        "deadline": row["deadline"],
        "is_overdue": bool(row["deadline"] < now),
    }


def _esc_to_dict(row) -> dict:
    return {
        "id": row["id"],
        "from_level": row["from_level"],
        "to_level": row["to_level"],
        "reason": row["reason"],
        "created_at": row["created_at"],
    }


def _history_to_dict(row) -> dict:
    return {
        "id": row["id"],
        "status": row["status"],
        "note": row["note"],
        "created_at": row["created_at"],
    }


def _comment_to_dict(row) -> dict:
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "commenter_name": row["commenter_name"],
        "commenter_room": row["commenter_room"],
        # avatar ใช้ตัวแรกของชื่อ — fallback: .get กันคอลัมน์ยังไม่มา (row เก่า/DB ยังไม่ migrate)
        "commenter_first_name": row.get("commenter_first_name"),
        "body": row["body"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
