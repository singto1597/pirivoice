import json
import os
from typing import Optional

import asyncpg
from core.exceptions import ForbiddenError
from core.config import settings

# 💡 รายการสิทธิ์ทั้งหมดของระบบ PIRIvoice
# (ตำแหน่ง/ระดับ จะแมปกับ permissions ผ่าน config/roles.json)
AVAILABLE_PERMISSIONS = [
    "SUBMIT_ISSUE",          # นักเรียนทุกคนแจ้งปัญหา/ความคิดเห็นได้
    "VIEW_OWN_ISSUES",       # เห็นเฉพาะเรื่องของตัวเอง
    "RECEIVE_ISSUES",        # รับเรื่อง (หัวหน้าห้อง + รอง)
    "MANAGE_ISSUE_STEPS",    # เพิ่มขั้นตอนการดำเนินงาน
    "SET_COUNTDOWN",         # ตั้งเวลานับถอยหลังงาน
    "ESCALATE_ISSUE",        # ส่งต่อเรื่องไประดับบน
    "VIEW_LEVEL_PYRAMID",    # เห็นเรื่องของระดับล่างลงมา (มองลงเป็นพีระมิด)
    "MANAGE_STUDENTS",       # จัดการนักเรียน (import Excel)
    "VIEW_DASHBOARD",        # ดู dashboard/รายงาน
    "MANAGE_SETTINGS",       # ตั้งค่าระบบ
    "VIEW_AUDIT_LOG",        # ดูบันทึกการใช้งาน (audit_logs) — admin/ครูสภา/ประธานสภา
    "MANAGE_ANNOUNCEMENTS",  # จัดการประกาศหน้า Landing Page — admin/ครูสภา/ประธานสภา/สภานักเรียน
]

# 🎯 บทบาทที่เห็น/จัดการข้อมูลทั้งโรงเรียน (สิทธิ์เทียบเท่า is_admin)
SCOPE_ALL_ROLES = {"admin", "teacher_council", "council_president"}
# 🎯 บทบาทที่จำกัดเฉพาะระดับชั้น (เช่น ครู ม.4 ดูแลแค่ ม.4)
SCOPE_LEVEL_ROLES = {"teacher"}

async def require_member(conn: asyncpg.Connection, room_id: int, user_id: int):
    """เช็คว่า user เป็นสมาชิก active ของห้อง/ระดับนี้หรือไม่ (กัน cross-level data leak)."""
    if settings.SUPER_ADMIN_ID and int(user_id) == int(settings.SUPER_ADMIN_ID):
        return True

    row = await conn.fetchval(
        "SELECT 1 FROM students WHERE room_id = $1 AND user_id = $2 AND status = 'active' AND deleted_at IS NULL",
        room_id, int(user_id)
    )
    if not row:
        raise ForbiddenError("คุณไม่ได้เป็นสมาชิกที่ใช้งานอยู่ในระดับนี้")

    return True

async def require_permission(conn: asyncpg.Connection, room_id: int, user_id: int, required_permission: str):
    """
    Granular RBAC (ระดับห้อง): SUPER_ADMIN_ID และ is_admin ผ่านฉลุย
    ไม่งั้นเช็คจาก JSONB array `permissions` บนตาราง students ของห้องนั้น
    """
    # 1. Super Admin (God Mode ระดับ Server)
    if settings.SUPER_ADMIN_ID and int(user_id) == int(settings.SUPER_ADMIN_ID):
        return True

    # 2. Query ค่า is_admin + permissions จากตาราง students
    row = await conn.fetchrow(
        """
        SELECT is_admin, permissions, status
        FROM students
        WHERE room_id = $1 AND user_id = $2 AND deleted_at IS NULL
        """,
        room_id, int(user_id)
    )

    if not row:
        raise ForbiddenError("Access Denied: ไม่พบข้อมูลของคุณในระดับนี้")

    if row['status'] != 'active':
        raise ForbiddenError("Access Denied: บัญชีของคุณในระดับนี้ยังไม่ได้รับการอนุมัติ หรือถูกระงับ")

    # 3. God Mode ของระดับ: is_admin ข้ามการเช็คสิทธิ์ย่อย
    if row['is_admin']:
        return True

    # 4. เช็คสิทธิ์ย่อยจาก permissions (JSONB array)
    user_permissions = _parse_permissions(row['permissions'])

    if required_permission not in user_permissions:
        raise ForbiddenError(f"Access Denied: คุณไม่มีสิทธิ์ '{required_permission}'")

    return True


async def require_permission_anywhere(conn: asyncpg.Connection, user_id: int, required_permission: str):
    """
    Granular RBAC (ข้ามทุกห้อง): เช็คว่า user มีสิทธิ์ permission ในห้อง/ตำแหน่งใดก็ได้
    ใช้สำหรับสิทธิ์ระดับโรงเรียน เช่น MANAGE_STUDENTS, VIEW_DASHBOARD, MANAGE_SETTINGS

    ⚠️ หมายเหตุ: ผ่านแล้วยังต้องเช็ค "ขอบเขตข้อมูล" (scope) ด้วย —
    ครูทั่วไป (teacher) มี MANAGE_STUDENTS/VIEW_DASHBOARD เหมือนกัน แต่ถูกจำกัดเฉพาะระดับชั้น
    """
    # 1. Super Admin (God Mode ระดับ Server)
    if settings.SUPER_ADMIN_ID and int(user_id) == int(settings.SUPER_ADMIN_ID):
        return True

    # 2. ดึงทุก membership ที่ active ของ user
    rows = await conn.fetch(
        """
        SELECT is_admin, permissions, status
        FROM students
        WHERE user_id = $1 AND deleted_at IS NULL
        """,
        int(user_id)
    )

    if not rows:
        raise ForbiddenError("Access Denied: ไม่พบข้อมูลของคุณ")

    for row in rows:
        if row['status'] != 'active':
            continue
        # is_admin ผ่านฉลุย
        if row['is_admin']:
            return True
        perms = _parse_permissions(row['permissions'])
        if required_permission in perms:
            return True

    raise ForbiddenError(f"Access Denied: คุณไม่มีสิทธิ์ '{required_permission}'")


async def get_access_scope(conn: asyncpg.Connection, user_id: int) -> dict:
    """
    🎯 วิเคราะห์ "ขอบเขตการเข้าถึงข้อมูล" ของ user (ใช้ประกอบ require_permission_anywhere)

    คืนค่า: {"scope": str, "level": Optional[str], "is_admin": bool}
      - scope='super'  : SUPER_ADMIN_ID — เห็นทุกอย่างทั้งระบบ
      - scope='all'    : admin / ครูสภา (teacher_council) / ประธานสภา / สภานักเรียน (council_member) — เห็นทุกอย่าง
      - scope='level'  : ครูทั่วไป (teacher) — เห็นเฉพาะระดับชั้น (staff_level เช่น 'ม.4')
      - scope='none'   : ครูทั่วไปที่ยังไม่มี staff_level — ไม่มีขอบเขตข้อมูล (ห้ามมองทั้งโรงเรียน)
      - scope='pyramid': ปกติ — มองตามพีระมิด (ใช้กับเรื่อง/issue เท่านั้น)

    ตัวอย่าง: ครู ม.4 → {"scope": "level", "level": "ม.4"}
    """
    # 1. Super Admin
    if settings.SUPER_ADMIN_ID and int(user_id) == int(settings.SUPER_ADMIN_ID):
        return {"scope": "super", "level": None, "is_admin": True}

    # 2. ดึงทุก membership ที่ active
    rows = await conn.fetch(
        """
        SELECT class_role, is_admin, staff_level, status
        FROM students
        WHERE user_id = $1 AND deleted_at IS NULL
        """,
        int(user_id)
    )
    if not rows:
        return {"scope": "pyramid", "level": None, "is_admin": False}

    is_admin = any(r["is_admin"] and r["status"] == "active" for r in rows)

    # ⚠️ ครูทั่วไปที่ยังไม่ได้ระบุ staff_level → scope='none' (ไม่มีขอบเขตข้อมูล)
    # เดิมจะตกไปเป็น 'pyramid' ซึ่ง dashboard แปลงเป็น 'all' → ครูที่ไม่มีระดับชั้นจะเห็นทั้งโรงเรียน (ข้อมูลรั่ว)
    has_teacher_no_level = False

    for r in rows:
        if r["status"] != "active":
            continue
        # scope 'all': is_admin หรือ role ที่เห็นทั้งโรงเรียน
        if r["is_admin"] or r["class_role"] in SCOPE_ALL_ROLES:
            return {"scope": "all", "level": None, "is_admin": True}
        # 🆕 scope 'all' สำหรับ สภานักเรียน (council_member) — ยอดพีระมิด เห็นทั้งโรงเรียน
        # แต่ไม่ใช่ admin (is_admin=False — ไม่ได้สิทธิ์จัดการ/import/audit ที่ require_permission_anywhere กันไว้)
        if r["class_role"] == "council_member":
            return {"scope": "all", "level": None, "is_admin": False}
        # scope 'level': ครูทั่วไป (ต้องมี staff_level ระบุระดับชั้น)
        if r["class_role"] in SCOPE_LEVEL_ROLES:
            if r["staff_level"]:
                return {"scope": "level", "level": r["staff_level"], "is_admin": False}
            has_teacher_no_level = True

    if has_teacher_no_level:
        return {"scope": "none", "level": None, "is_admin": is_admin}

    return {"scope": "pyramid", "level": None, "is_admin": is_admin}


# ตำแหน่งที่ "ขอบเขตระดับชั้น" (grade) กำหนดให้ต้องเห็น/จัดการได้แค่ระดับชั้นของตัวเอง
# - teacher: ระดับชั้นที่รับผิดชอบ (staff_level)
# - level_president / level_vice_president: ระดับชั้นของห้องตัวเอง (rooms.level)
GRADE_SCOPED_ROLES = {
    "level_president", "level_vice_president",
}


# 🧭 ลำดับชั้นการจัดการ (hierarchy) สำหรับหน้า User Management — ใครจัดการ/แก้ไขใครได้บ้าง
# ตัวเลขสูง = จัดการได้มากกว่า (จัดการคนที่ rank ≤ ตัวเองได้)
# โดยยึดตามพีระมิด: ประธานสภา > สภานักเรียน > หัวหน้าระดับ = ผู้ช่วยหัวหน้าระดับ > คณะกรรมการห้อง > นักเรียน
MANAGE_RANK = {
    "student": 0,
    # คณะกรรมการห้อง (หัวหน้าห้อง + รอง 4 ฝ่าย)
    "class_president": 1,
    "vice_academic": 1,
    "vice_discipline": 1,
    "vice_activity": 1,
    "vice_reception": 1,
    # ประธานระดับ / ผู้ช่วยหัวหน้าระดับ
    "level_president": 2,
    "level_vice_president": 2,
    # สภานักเรียน
    "council_member": 3,
    "council_president": 4,
}
# บทบาทระดับสูงที่ดูแลทั้งโรงเรียน (bypass rank/grade — มี MANAGE_STUDENTS เต็มรูปแบบ)
SCHOOL_WIDE_MANAGE_ROLES = {"admin", "teacher_council", "council_president"}


async def get_user_grade_scope(conn: asyncpg.Connection, user_id: int) -> Optional[str]:
    """
    ระดับชั้น (grade) ที่ user ถูกจำกัดให้เห็น/จัดการได้เฉพาะห้องในระดับนั้น
    เช่น 'ม.4' — หรือ None ถ้า user ไม่ได้ถูกจำกัดระดับชั้น (school-wide / student / council)

    - ครูทั่วไป (teacher) → students.staff_level
    - หัวหน้าระดับ / ผู้ช่วยหัวหน้าระดับ (level_president / level_vice_president)
      → rooms.level ของห้องที่ตำแหน่งนั้นสังกัด (ผ่าน students.room_id)
    - admin / ครูสภา / ประธานสภา / สภานักเรียน / นักเรียน → None (school-wide หรือไม่ผูก grade)
    """
    if settings.SUPER_ADMIN_ID and int(user_id) == int(settings.SUPER_ADMIN_ID):
        return None

    # 1. ครูทั่วไป — staff_level ระบุระดับชั้นที่รับผิดชอบไว้แล้ว
    row = await conn.fetchrow(
        """
        SELECT staff_level FROM students
        WHERE user_id = $1 AND class_role = 'teacher'
          AND deleted_at IS NULL AND status = 'active'
          AND staff_level IS NOT NULL
        ORDER BY id LIMIT 1
        """,
        int(user_id)
    )
    if row and row["staff_level"]:
        return row["staff_level"]

    # 2. หัวหน้าระดับ / ผู้ช่วยหัวหน้าระดับ — ระดับชั้นของห้องตัวเอง (rooms.level)
    row = await conn.fetchrow(
        """
        SELECT r.level FROM students s
        JOIN rooms r ON r.id = s.room_id
        WHERE s.user_id = $1
          AND s.class_role IN ('level_president', 'level_vice_president')
          AND s.deleted_at IS NULL AND s.status = 'active'
          AND r.deleted_at IS NULL AND r.level IS NOT NULL
        ORDER BY s.id LIMIT 1
        """,
        int(user_id)
    )
    if row and row["level"]:
        return row["level"]

    return None


def _parse_permissions(raw_perms) -> list:
    """แปลง permissions JSONB → list (รองรับทั้ง str และ list จาก asyncpg)"""
    if not raw_perms:
        return []
    if isinstance(raw_perms, str):
        try:
            return json.loads(raw_perms)
        except json.JSONDecodeError:
            return []
    return list(raw_perms)


# 🧭 แคช roles (อ่านจาก config/roles.json ครั้งเดียว)
_ROLE_CACHE = None


def _load_roles() -> dict:
    """โหลด config/roles.json (แคชครั้งแรก)"""
    global _ROLE_CACHE
    if _ROLE_CACHE is None:
        roles_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "roles.json")
        try:
            with open(roles_path, encoding="utf-8") as f:
                data = json.load(f)
            _ROLE_CACHE = data.get("roles", {})
        except Exception:
            _ROLE_CACHE = {}
    return _ROLE_CACHE


def get_role_info(role: str) -> dict:
    """
    คืน dict ข้อมูล role ทั้งหมดจาก config/roles.json:
      {"label": ..., "is_admin": bool, "permissions": [...]}
    (ถ้า role ไม่มี → คืน dict ว่าง)
    """
    role_data = _load_roles().get(role, {})
    return {
        "label": role_data.get("label", role),
        "is_admin": bool(role_data.get("is_admin", False)),
        "permissions": list(role_data.get("permissions", [])),
    }


def get_role_permissions(role: str) -> list:
    """
    คืน list permissions ของ role (จาก config/roles.json)
    ใช้ตอน register/import/seed เพื่อให้ students.permissions มีค่าตามตำแหน่งจริง
    (ทำให้ frontend รู้ว่าซ่อน/โชว์เมนูไหน)
    """
    return get_role_info(role)["permissions"]


def get_role_is_admin(role: str) -> bool:
    """คืนว่า role เป็น admin (is_admin) หรือไม่ — ใช้ตอน register/import ตั้งค่า students.is_admin"""
    return get_role_info(role)["is_admin"]
