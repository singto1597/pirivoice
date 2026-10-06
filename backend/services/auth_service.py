import json
import bcrypt
import asyncpg
from datetime import datetime, timedelta, timezone
from jose import jwt

from core.config import settings
from core.rbac import get_role_permissions, get_role_is_admin
from core.exceptions import ForbiddenError, NotFoundError, ValidationError, ConflictError
# 🌟 ต้องรู้ "ปีปัจจุบัน" เพื่อไม่ให้ไป UPDATE ทับแถวปีเก่าตอนลงทะเบียน (migration 027)
#    ⚠️ `year_service` พึ่งแค่ `core.*` ⇒ ไม่เกิด import วนกับ auth_service
from services import year_service


def hash_password(password: str) -> str:
    """hash รหัสผ่านด้วย bcrypt"""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    """ตรวจสอบรหัสผ่าน"""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def create_access_token(user_id: int) -> str:
    """สร้าง JWT access token"""
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "user_id": user_id,
        "exp": expire,
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


async def authenticate_user(pool: asyncpg.Pool, username: str, password: str) -> int:
    """ตรวจสอบ username/password — คืน user_id ถ้าถูกต้อง"""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, password_hash FROM users WHERE username = $1 AND deleted_at IS NULL",
            username
        )
        if not row:
            # 🛡️ Audit: login ล้มเหลว (หาชื่อไม่เจอ) — เก็บทุกครั้ง (dashboard นับเฉพาะ status='success')
            from core.logger import AuditLogger
            await AuditLogger("auth_service").log(
                conn=conn, action="login", status="error",
                error_detail="ไม่พบชื่อผู้ใช้นี้ หรือรหัสผ่านไม่ถูกต้อง",
                actor_identifier=username, client_source="web",
                entity_type="user",
                endpoint_or_command="POST /auth/login",
            )
            raise NotFoundError("ไม่พบชื่อผู้ใช้นี้ หรือรหัสผ่านไม่ถูกต้อง")

        if not verify_password(password, row["password_hash"]):
            # 🛡️ Audit: login ล้มเหลว (รหัสผิด) — รู้ user_id แล้ว
            from core.logger import AuditLogger
            await AuditLogger("auth_service").log(
                conn=conn, action="login", status="error",
                error_detail="ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง",
                actor_identifier=username, client_source="web",
                user_id=row["id"], entity_type="user", entity_id=row["id"],
                endpoint_or_command="POST /auth/login",
            )
            raise ForbiddenError("ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง")

        # 🛡️ Audit log: บันทึกการเข้าใช้งาน (dashboard ใช้นับ "การเข้าใช้งาน")
        from core.logger import AuditLogger
        await AuditLogger("auth_service").log(
            conn=conn,
            action="login",
            actor_identifier=username,
            client_source="web",
            user_id=row["id"],
            entity_type="user",
            entity_id=row["id"],
            endpoint_or_command="POST /auth/login",
        )

        return row["id"]


async def change_password(pool: asyncpg.Pool, user_id: int, old_password: str, new_password: str) -> None:
    """เปลี่ยนรหัสผ่าน (ต้องตรวจรหัสเก่าก่อน)"""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT password_hash FROM users WHERE id = $1 AND deleted_at IS NULL",
            user_id
        )
        if not row:
            raise NotFoundError("ไม่พบผู้ใช้")

        if not verify_password(old_password, row["password_hash"]):
            raise ForbiddenError("รหัสผ่านเดิมไม่ถูกต้อง")

        new_hash = hash_password(new_password)
        await conn.execute(
            """
            UPDATE users
            SET password_hash = $1, must_change_password = FALSE, updated_at = NOW()
            WHERE id = $2
            """,
            new_hash, user_id
        )

        # 🛡️ Audit: เปลี่ยนรหัสผ่าน (ไม่เก็บ hash ลง audit — แค่บอกว่าเกิด action นี้)
        from core.logger import AuditLogger
        await AuditLogger("auth_service").log(
            conn=conn, action="CHANGE_PASSWORD",
            actor_identifier=str(user_id), client_source="web",
            user_id=user_id, entity_type="user", entity_id=user_id,
            endpoint_or_command="POST /auth/change-password",
        )


async def get_user_by_id(pool: asyncpg.Pool, user_id: int) -> asyncpg.Record | None:
    """ดึงข้อมูล user ตาม id (ไม่รวม password_hash)"""
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            """
            SELECT id, username, full_name, must_change_password
            FROM users
            WHERE id = $1 AND deleted_at IS NULL
            """,
            user_id
        )


async def get_user_roles(pool: asyncpg.Pool, user_id: int) -> list:
    """
    ดึงบทบาท/ตำแหน่งของ user จากตาราง students
    (user เป็นนักเรียนในห้องไหน ตำแหน่งอะไร)
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                s.room_id,
                s.student_no,
                s.class_role,
                s.first_name,
                s.staff_level,
                s.is_admin,
                s.permissions,
                s.responsibilities,
                r.room_name,
                r.level
            FROM students s
            LEFT JOIN rooms r ON r.id = s.room_id
            WHERE s.user_id = $1
              AND s.deleted_at IS NULL
              AND s.status = 'active'
              AND (r.id IS NULL OR r.deleted_at IS NULL)
            ORDER BY s.id
            """,
            user_id
        )

    def _parse_json_list(raw) -> list:
        if not raw:
            return []
        if isinstance(raw, list):
            return raw
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return []

    roles = []
    for row in rows:
        perms = _parse_json_list(row["permissions"])
        resp = _parse_json_list(row["responsibilities"])
        roles.append({
            "role": row["class_role"],
            "room_id": row["room_id"],
            "room_name": row["room_name"],
            "student_no": row["student_no"],
            "first_name": row["first_name"],
            "level": row["level"],
            "staff_level": row["staff_level"],
            "is_admin": row["is_admin"],
            "permissions": perms,
            "responsibilities": resp,
        })
    return roles


async def register_user(
    pool: asyncpg.Pool,
    username: str,
    password: str,
    full_name: str,
    student_id: str,
    room_code: str,
    student_no: int,
    class_role: str = "student",
) -> int:
    """
    Register นักเรียนใหม่ (ใช้ตอน Import Excel หรือสมัครเอง)
    - ถ้า students มีอยู่แล้ว (student_id + room) → ผูก user เข้ากับ student เดิม
    - ถ้ายังไม่มี student → สร้าง student ใหม่ (กับ room)
    """
    hashed = hash_password(password)
    # permissions + is_admin ตามตำแหน่ง (จาก config/roles.json)
    role_perms = get_role_permissions(class_role)
    role_is_admin = get_role_is_admin(class_role)

    async with pool.acquire() as conn:
        async with conn.transaction():
            # 1. หา room ตาม room_code (admin/ครูสภา อาจไม่ระบุห้อง → ไม่ผูกห้อง)
            room = None
            if room_code:
                room = await conn.fetchrow(
                    "SELECT id, level FROM rooms WHERE room_code = $1 AND deleted_at IS NULL",
                    room_code
                )
                if not room:
                    raise NotFoundError(f"ไม่พบห้องเรียน {room_code}")

            # ครูทั่วไป → staff_level = ระดับชั้นของห้อง
            staff_level = room["level"] if class_role == "teacher" and room else None

            # 2. สร้าง user (หรือหาเดิม)
            user = await conn.fetchrow(
                "SELECT id FROM users WHERE username = $1 AND deleted_at IS NULL",
                username
            )
            if user:
                user_id = user["id"]
            else:
                user_id = await conn.fetchval(
                    """
                    INSERT INTO users (username, password_hash, full_name)
                    VALUES ($1, $2, $3)
                    RETURNING id
                    """,
                    username, hashed, full_name
                )

            # 3. หา/สร้าง student (ผูกกับ user_id)
            #
            # 🔴 **ต้องเจาะจง "ปีเดียวกัน" (migration 027) — ที่นี่ร้ายกว่าจุดอื่น เพราะสาขา
            #    "เจอแถวเดิม" ไม่ได้ INSERT แต่ `UPDATE` ทับ** ⇒ ถ้าไม่กรองปี เด็กที่เลื่อนชั้น
            #    แล้ว (มีแต่แถวปีเก่า `status='promoted'`) จะถูกจับมา **ปลุกเป็นสมาชิกปัจจุบัน
            #    ของปีเก่า** — ได้สิทธิ์จากแถวปีเก่า และ **ไม่มีแถว active ในปีใหม่เลย**
            #    ⇒ เพิ่มตัวกรองปี = กันบั๊ก resurrection ไม่ใช่แค่กัน duplicate
            #    ⚠️ หาปีไม่เจอ → ไม่เจอแถวเดิม → INSERT แถวใหม่ (ได้ DEFAULT ของคอลัมน์)
            #       ซึ่งเป็นทางที่ปลอดภัยกว่า "ไป UPDATE แถวปีเก่า" อย่างชัดเจน
            current_year = await year_service.fetch_current_year(conn)
            reg_year_id = current_year["id"] if current_year else None

            room_id = room["id"] if room else None
            if room_id is not None:
                student = await conn.fetchrow(
                    """
                    SELECT id FROM students
                    WHERE room_id = $1 AND student_id = $2 AND deleted_at IS NULL
                      AND academic_year_id = $3
                    """,
                    room_id, student_id, reg_year_id
                )
            else:
                student = await conn.fetchrow(
                    """
                    SELECT id FROM students
                    WHERE room_id IS NULL AND student_id = $1 AND deleted_at IS NULL
                      AND academic_year_id = $2
                    """,
                    student_id, reg_year_id
                )
            if student:
                # อัปเดต user_id + ตำแหน่ง + permissions + staff_level + is_admin
                await conn.execute(
                    """
                    UPDATE students
                    SET user_id = $1, class_role = $2, permissions = $3,
                        staff_level = $4, is_admin = $5
                    WHERE id = $6
                    """,
                    user_id, class_role, json.dumps(role_perms),
                    staff_level, role_is_admin, student["id"]
                )
            else:
                await conn.execute(
                    """
                    INSERT INTO students
                        (room_id, user_id, student_id, student_no, first_name, last_name,
                         class_role, staff_level, is_admin, permissions)
                    VALUES ($1, $2, $3, $4, '', '', $5, $6, $7, $8)
                    """,
                    room_id, user_id, student_id, student_no,
                    class_role, staff_level, role_is_admin, json.dumps(role_perms)
                )

            # 🛡️ Audit: สร้างผู้ใช้ (ทุก create ต้องบันทึก — ตามกฎ backend.md)
            from core.logger import AuditLogger
            await AuditLogger("auth_service").log(
                conn=conn, action="CREATE_USER",
                actor_identifier=str(user_id), client_source="web",
                user_id=user_id, entity_type="user", entity_id=user_id,
                new_values={
                    "username": username, "full_name": full_name,
                    "student_id": student_id, "class_role": class_role,
                },
                endpoint_or_command="register_user",
            )

            return user_id


def make_user_out(user_record, roles: list) -> dict:
    """แปลง user + roles ให้เป็น response shape (UserOut)"""
    # หา is_admin จาก roles ไหนก็ได้
    is_admin = any(r.get("is_admin") for r in roles)
    # รวม permissions ทั้งหมด
    permissions = sorted({p for r in roles for p in r.get("permissions", [])})
    # ชื่อจริง (first_name) ตัวแรกจาก roles ที่ไม่ว่าง — avatar ใช้ตัวแรกของชื่อ
    first_name = next((r.get("first_name") for r in roles if r.get("first_name")), None)

    return {
        "id": user_record["id"],
        "username": user_record["username"],
        "full_name": user_record["full_name"],
        "first_name": first_name,
        "is_admin": is_admin,
        "permissions": permissions,
        "must_change_password": bool(user_record.get("must_change_password")),
        "roles": [
            {
                "role": r["role"],
                "room_id": r["room_id"],
                "room_name": r["room_name"],
                "student_no": r["student_no"],
                "first_name": r.get("first_name"),
                "level": r["level"],
                "staff_level": r.get("staff_level"),
                "is_admin": r.get("is_admin", False),
                "permissions": r.get("permissions", []),
                "responsibilities": r.get("responsibilities", []),
            }
            for r in roles
        ],
    }
