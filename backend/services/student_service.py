import json
import asyncpg
from typing import Optional

from core.exceptions import NotFoundError, ValidationError, ConflictError
from core.rbac import get_role_permissions, get_role_is_admin
from services import auth_service
# 🌟 ต้องรู้ "ปีปัจจุบัน" เพื่อกรองรายชื่อ (migration 027) — `year_service` พึ่งแค่ `core.*`
#    ⇒ ไม่เกิด import วน (ตรวจแล้ว: ไม่มี service ไหนที่ year_service import กลับ)
from services import year_service

# 🧭 แผนที่ตำแหน่งภาษาไทย → role key (ตรงกับ config/roles.json)
ROLE_MAP = {
    "ประธานสภา": "council_president",
    "สภานักเรียน": "council_member",
    "ประธานระดับ": "level_president",
    "ผู้ช่วยหัวหน้าระดับ": "level_vice_president",
    "หัวหน้าห้อง": "class_president",
    "รองวิชาการ": "vice_academic",
    "รองวินัย": "vice_discipline",
    "รองกิจกรรม": "vice_activity",
    "รองปฏิคม": "vice_reception",
    "รอง": "vice_reception",  # fallback
    "ครูสภา": "teacher_council",
    "ครู": "teacher",
    "ครูทั่วไป": "teacher",
    "แอดมิน": "admin",
    "ผู้ดูแลระบบ": "admin",
    "นักเรียน": "student",
    "": "student",
}


def map_role_label(label: str) -> str:
    """แปลงตำแหน่งจากภาษาไทย (ใน Excel) → role key"""
    label = (label or "").strip()
    return ROLE_MAP.get(label, "student")


# ============================================================
# 🎯 หน้าที่รับผิดชอบ (Responsibilities)
# ============================================================
# มีเฉพาะ 2 ตำแหน่งที่ถือ "หน้าที่" ได้ (ตรงกับ Requirement):
# - สภานักเรียน (council_member)
# - ผู้ช่วยหัวหน้าระดับ (level_vice_president)
# ค่า = รหัส category ทั้ง 9 หมวด (academic / reception / ... / grievance)
RESPONSIBLE_ROLES = {"council_member", "level_vice_president"}


def _validate_responsibilities(values, role: str) -> list:
    """
    ตรวจ + ทำความสะอาดค่าหน้าที่ (responsibilities):
    - role ไม่ใช่ RESPONSIBLE_ROLES → ต้องว่างเสมอ (ไม่อนุญาตตั้งหน้าที่กับ role นี้)
    - แต่ละค่าต้องเป็นหมวดย่อยที่ถูกต้อง (จาก config/categories.json) → กันค่าปลอม
    - ตัดซ้ำ (keep order)
    """
    values = list(values or [])
    if role not in RESPONSIBLE_ROLES:
        if values:
            raise ValidationError(
                "ตำแหน่งนี้ไม่รองรับการตั้งหน้าที่รับผิดชอบ (เฉพาะ สภานักเรียน / ผู้ช่วยหัวหน้าระดับ)"
            )
        return []
    from core.categories import all_subcategory_codes
    valid = set(all_subcategory_codes())
    unknown = [v for v in values if v not in valid]
    if unknown:
        raise ValidationError(f"มีหมวดหน้าที่ไม่ถูกต้อง: {', '.join(str(u) for u in unknown)}")
    seen = set()
    out = []
    for v in values:
        if v not in seen:
            seen.add(v)
            out.append(v)
    return out


def _parse_json_list(raw) -> list:
    """แปลง JSONB array → list (รองรับทั้ง str และ list จาก asyncpg)"""
    if not raw:
        return []
    if isinstance(raw, list):
        return list(raw)
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []


async def list_rooms(pool: asyncpg.Pool) -> list:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, room_code, room_name, level, room_number FROM rooms WHERE deleted_at IS NULL ORDER BY room_code"
        )
    return [dict(r) for r in rows]


async def create_room(pool: asyncpg.Pool, room_code: str, room_name: str, level: Optional[str] = None, room_number: Optional[int] = None) -> int:
    async with pool.acquire() as conn:
        async with conn.transaction():
            existing = await conn.fetchval(
                "SELECT id FROM rooms WHERE room_code = $1 AND deleted_at IS NULL",
                room_code
            )
            if existing:
                return existing
            room_id = await conn.fetchval(
                """
                INSERT INTO rooms (room_code, room_name, level, room_number)
                VALUES ($1, $2, $3, $4)
                RETURNING id
                """,
                room_code, room_name, level, room_number
            )
            # 🛡️ Audit log (ทุก create ต้องบันทึก — ตามกฎ backend.md)
            from core.logger import AuditLogger
            await AuditLogger("student_service").log(
                conn=conn, action="CREATE_ROOM",
                actor_identifier="system", client_source="system",
                entity_type="room", entity_id=room_id,
                new_values={
                    "room_code": room_code, "room_name": room_name,
                    "level": level, "room_number": room_number,
                },
                endpoint_or_command="create_room",
            )
            return room_id


async def list_students(pool: asyncpg.Pool, room_id: Optional[int] = None, search: Optional[str] = None, level: Optional[str] = None, role: Optional[str] = None, limit: Optional[int] = None, year_id: Optional[int] = None, all_years: bool = False) -> list:
    """
    รายชื่อนักเรียน/สมาชิก
    - level: กรองเฉพาะระดับชั้น (เช่น 'ม.4') — ใช้กับ ครูทั่วไป/ประธานระดับ/ผู้ช่วย ที่เห็นได้แค่ระดับตัวเอง
    - role: กรองเฉพาะตำแหน่ง (เช่น 'council_member') — ใช้กับหน้า User Management (default = role ผู้จัดการ)
    - room_id: กรองเฉพาะห้อง
    - limit: ถ้าระบุ → ตัดจำนวนสูงสุด (ใช้กับกรณีที่ต้องการจำกัดจริงๆ)
      ⚠️ default = None (ไม่ตัด) — หน้า User Management กรองเอง client-side (group/search)
      ต้องได้รายชื่อครบทั้งชุดในขอบเขตตัวเอง เดิม hardcode LIMIT 500 → หน้าเห็นแค่ 500 คนแรก
      (เรียงตาม room_code = ห้อง ม.1 ก่อน) ทั้งที่ทั้งโรงเรียนเกิน 500 คน
    - year_id: ปีการศึกษาที่จะดู **ไม่ระบุ = ปีปัจจุบัน** (migration 027)

    🌟 **ทำไมต้องกรองปี (เพิ่มพร้อม migration 027):**
       ก่อนมีปี ตาราง `students` มีคนละ 1 แถว ⇒ ไม่กรองก็ได้คำตอบที่ถูก
       หลังมีปี คนหนึ่งมี **หลายแถว** (แถวปีเก่า `promoted`/`graduated` + แถวปีใหม่ `active`)
       ⇒ ถ้าไม่กรอง รายชื่อจะ **บวมเป็น N ปี** และมีชื่อเด็กที่จบไปแล้วปนอยู่
       ⚠️ กรองด้วยปี **ไม่ใช่** `status='active'` โดยเจตนา — เพราะฟังก์ชันนี้ต้องคืน
          แถว `pending`/`suspended` ด้วย (มี UI รออนุมัติผูกอยู่) · การกรองปีคุม "รุ่น"
          ส่วนสถานะเป็นเรื่องแยก ⇒ ส่ง `year_id` ของปีเก่ามาก็ดูย้อนหลังได้
    """
    async with pool.acquire() as conn:
        where = ["s.deleted_at IS NULL"]
        params = []

        # 🌟 ค้นข้ามปี (P6 · ข้อตัดสินใจ #8 "เด็กจบต้องค้นชื่อเจอ")
        # ⚠️ บังคับให้มีคำค้น — ไม่งั้นการไม่กรองปีคือการดัมป์รายชื่อทุกปีของทั้งโรงเรียน
        #    (3172 คน × จำนวนปี) ซึ่งทั้งช้าและไม่ใช่สิ่งที่ผู้ใช้ต้องการ
        if all_years:
            if not search or not search.strip():
                raise ValidationError("การค้นข้ามปีต้องระบุคำค้น (ชื่อ/นามสกุล/รหัสนักเรียน)")
            year_id = None  # ไม่กรองปี
        else:
            # 🌟 ปีการศึกษา — อ่านด้วย connection นี้เลย ไม่เปิด acquire ซ้อน (กัน deadlock ของ pool)
            # ⚠️ ถ้าหา "ปีปัจจุบัน" ไม่ได้ (เกิดไม่ได้หลัง 027 — ปีปัจจุบันลบไม่ได้) จะ **ไม่กรองปี**
            #    แล้วถอยไปใช้พฤติกรรมเดิม แทนที่จะคืนลิสต์ว่างเงียบ ๆ ซึ่งอ่านไม่ออกว่าทำไมหาย
            if year_id is None:
                current_year = await year_service.fetch_current_year(conn)
                year_id = current_year["id"] if current_year else None
            if year_id is not None:
                params.append(year_id)
                where.append(f"s.academic_year_id = ${len(params)}")

        if level:
            params.append(level)
            where.append(f"r.level = ${len(params)}")
        if room_id:
            params.append(room_id)
            where.append(f"s.room_id = ${len(params)}")
        if role:
            params.append(role)
            where.append(f"s.class_role = ${len(params)}")
        if search:
            params.append(f"%{search}%")
            where.append(f"(s.first_name ILIKE ${len(params)} OR s.last_name ILIKE ${len(params)} OR s.student_id ILIKE ${len(params)})")

        limit_clause = ""
        if limit is not None:
            params.append(limit)
            limit_clause = f"LIMIT ${len(params)}"

        sql = f"""
            SELECT
                s.id, s.room_id, s.student_id, s.student_no,
                s.prefix, s.first_name, s.last_name, s.nickname,
                s.class_role, s.staff_level, s.is_admin, s.permissions,
                s.responsibilities, s.status,
                r.room_code, r.room_name, r.level
            FROM students s
            LEFT JOIN rooms r ON r.id = s.room_id
            WHERE {' AND '.join(where)}
            ORDER BY r.room_code, s.student_no
            {limit_clause}
        """
        rows = await conn.fetch(sql, *params)
    return [_student_to_dict(r) for r in rows]


def _student_to_dict(row) -> dict:
    perms = row["permissions"] or []
    if isinstance(perms, str):
        import json
        try:
            perms = json.loads(perms)
        except json.JSONDecodeError:
            perms = []
    return {
        "id": row["id"],
        "room_id": row["room_id"],
        "room_code": row["room_code"],
        "room_name": row["room_name"],
        "student_id": row["student_id"],
        "student_no": row["student_no"],
        "prefix": row["prefix"],
        "first_name": row["first_name"],
        "last_name": row["last_name"],
        "nickname": row["nickname"],
        "class_role": row["class_role"],
        "staff_level": row.get("staff_level"),
        "is_admin": row["is_admin"],
        "permissions": perms,
        "responsibilities": _parse_json_list(row.get("responsibilities")),
        "status": row["status"],
    }


async def update_student(pool: asyncpg.Pool, student_id: int, *, class_role: Optional[str] = None, status: Optional[str] = None, is_admin: Optional[bool] = None, staff_level: Optional[str] = None, responsibilities: Optional[list] = None, prefix: Optional[str] = None, first_name: Optional[str] = None, last_name: Optional[str] = None, nickname: Optional[str] = None, student_no: Optional[int] = None, student_code: Optional[str] = None, actor_user_id: Optional[int] = None, client_source: str = "web") -> None:
    """
    แก้ไขนักเรียน/สมาชิก
    - เมื่อเปลี่ยน class_role → permissions + is_admin จะถูก recompute จาก config/roles.json เสมอ
    - responsibilities (หน้าที่): เฉพาะ council_member / level_vice_president; role อื่นถูกบังคับให้ว่าง
    - ครูทั่วไป (teacher) ต้องมี staff_level (ระดับชั้นที่ดูแล) — ถ้าไม่ระบุ ดึงจากระดับชั้นของห้อง
    - 🌟 P5: แก้ข้อมูลตัวตนได้ด้วย (prefix/first_name/last_name/nickname/student_no/student_code)
      ⚠️ `student_code` → `students.student_id` **ไม่แตะ `users.username`** โดยเจตนา
         (username เป็นกุญแจล็อกอิน — แก้ตามจะทำให้เด็กเข้าไม่ได้ · ดู schema docstring)
    - บันทึก audit_logs ใน transaction เดียวกัน
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            current = await conn.fetchrow(
                """SELECT id, user_id, room_id, academic_year_id, class_role, status, is_admin,
                          staff_level, responsibilities, prefix, first_name, last_name,
                          nickname, student_no, student_id
                   FROM students WHERE id = $1 AND deleted_at IS NULL""",
                student_id
            )
            if not current:
                raise NotFoundError("ไม่พบนักเรียน")

            new_role = class_role if class_role is not None else current["class_role"]
            new_status = status if status is not None else current["status"]
            new_admin = is_admin if is_admin is not None else current["is_admin"]
            new_staff_level = staff_level if staff_level is not None else current["staff_level"]
            old_resp = _parse_json_list(current["responsibilities"])

            # --- ข้อมูลตัวตน: ไม่ส่ง = ไม่แก้ (PATCH) --------------------------------
            new_prefix = prefix if prefix is not None else current["prefix"]
            new_first = first_name if first_name is not None else current["first_name"]
            new_last = last_name if last_name is not None else current["last_name"]
            new_nick = nickname if nickname is not None else current["nickname"]
            new_no = student_no if student_no is not None else current["student_no"]
            new_code = student_code if student_code is not None else current["student_id"]

            # รหัสนักเรียนซ้ำในห้อง+ปีเดียวกัน → unique index (028) จะโยน UniqueViolation
            # ⇒ ตรวจก่อนเพื่อให้ผู้ใช้เห็นข้อความที่อ่านรู้เรื่อง ไม่ใช่ 500
            if student_code is not None and student_code != current["student_id"]:
                dup = await conn.fetchval(
                    """SELECT 1 FROM students
                       WHERE room_id = $1 AND academic_year_id = $2 AND student_id = $3
                         AND deleted_at IS NULL AND id <> $4""",
                    current["room_id"], current["academic_year_id"], student_code, student_id,
                )
                if dup:
                    raise ValidationError(
                        f"รหัสนักเรียน {student_code} มีอยู่ในห้องนี้แล้ว (ปีเดียวกัน)"
                    )

            # เมื่อ role เปลี่ยน → permissions + is_admin ตาม config/roles.json เสมอ
            role_perms = get_role_permissions(new_role)
            if is_admin is None:
                new_admin = get_role_is_admin(new_role)

            # ครูทั่วไปต้องรู้ระดับชั้นที่ดูแล (ถ้าไม่ระบุ → ใช้ระดับชั้นของห้องตัวเอง)
            if new_role == "teacher" and not new_staff_level:
                new_staff_level = await conn.fetchval(
                    "SELECT level FROM rooms WHERE id = $1", current["room_id"]
                )

            # responsibilities: ถ้าส่งมา → validate + ใช้ค่าใหม่
            # ถ้าไม่ส่งมา แต่ role เปลี่ยนไปเป็น role ที่ไม่มีหน้าที่ → เคลียร์ให้ว่าง
            if responsibilities is not None:
                new_resp = _validate_responsibilities(responsibilities, new_role)
            elif new_role not in RESPONSIBLE_ROLES:
                new_resp = []
            else:
                new_resp = old_resp

            await conn.execute(
                """
                UPDATE students
                SET class_role = $1, status = $2, is_admin = $3, staff_level = $4,
                    permissions = $5, responsibilities = $6, updated_at = NOW(),
                    prefix = $7, first_name = $8, last_name = $9, nickname = $10,
                    student_no = $11, student_id = $12
                WHERE id = $13
                """,
                new_role, new_status, new_admin, new_staff_level,
                json.dumps(role_perms), json.dumps(new_resp),
                new_prefix, new_first, new_last, new_nick, new_no, new_code,
                student_id
            )

            # 🛡️ Audit log (กฎ: ทุก UPDATE ต้องบันทึกใน transaction เดียวกัน)
            from core.logger import AuditLogger
            await AuditLogger("student_service").log(
                conn=conn,
                action="UPDATE_STUDENT",
                actor_identifier=str(actor_user_id) if actor_user_id else "system",
                client_source=client_source,
                user_id=actor_user_id,
                entity_type="student",
                entity_id=student_id,
                old_values={
                    "class_role": current["class_role"],
                    "status": current["status"],
                    "is_admin": current["is_admin"],
                    "staff_level": current["staff_level"],
                    "responsibilities": old_resp,
                    "prefix": current["prefix"],
                    "first_name": current["first_name"],
                    "last_name": current["last_name"],
                    "nickname": current["nickname"],
                    "student_no": current["student_no"],
                    "student_id": current["student_id"],
                },
                new_values={
                    "class_role": new_role,
                    "status": new_status,
                    "is_admin": new_admin,
                    "staff_level": new_staff_level,
                    "responsibilities": new_resp,
                    "prefix": new_prefix,
                    "first_name": new_first,
                    "last_name": new_last,
                    "nickname": new_nick,
                    "student_no": new_no,
                    "student_id": new_code,
                },
            )


# ============================================================
# ➕ เพิ่มผู้ใช้งานแบบ Manual (User Management)
# ============================================================
async def create_student(
    pool: asyncpg.Pool,
    *,
    username: str,
    password: Optional[str] = None,
    prefix: Optional[str] = None,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    nickname: Optional[str] = None,
    student_id: Optional[str] = None,
    student_no: Optional[int] = None,
    room_code: Optional[str] = None,
    class_role: str = "student",
    responsibilities: Optional[list] = None,
    actor_user_id: Optional[int] = None,
    client_source: str = "web",
) -> int:
    """
    เพิ่มผู้ใช้งานใหม่ (หน้า User Management — "เพิ่มผู้ใช้งาน") สำหรับกรณี import Excel ไม่ครบ
    - username ไม่ซ้ำ (ถ้าซ้ำ → ConflictError) — manual add ไม่ใช่ re-import
    - room_code ต้องมีอยู่แล้วในระบบ (เลือกจาก dropdown หน้า UI) — ครู/ประธานระดับ/ผู้ช่วยต้องระบุห้อง
    - responsibilities: เฉพาะ council_member / level_vice_president
    - ถ้าไม่ระบุ password → สุ่มรหัสชั่วคราว + บังคับเปลี่ยนครั้งแรก (must_change_password)
    - permissions/is_admin ตาม config/roles.json; บันทึก audit CREATE_STUDENT
    """
    from core.logger import AuditLogger
    from core.rbac import get_role_info
    import secrets

    username = (username or "").strip()
    if not username:
        raise ValidationError("ต้องระบุ username (รหัสนักเรียน/ผู้ใช้งาน)")
    student_id = (student_id or username).strip()

    # กัน role แปลกปลอม (ต้องตรงกับ config/roles.json)
    if not get_role_info(class_role).get("label"):
        raise ValidationError(f"ตำแหน่งไม่ถูกต้อง: {class_role}")

    # permissions + is_admin ตามตำแหน่ง
    role_perms = get_role_permissions(class_role)
    role_is_admin = get_role_is_admin(class_role)
    # responsibilities: validate ก่อน (role ไม่รองรับ + ค่าไม่ถูกต้อง → error)
    new_resp = _validate_responsibilities(responsibilities, class_role)

    hashed = auth_service.hash_password(password) if password else auth_service.hash_password(secrets.token_urlsafe(12))
    must_change = bool(not password)

    async with pool.acquire() as conn:
        async with conn.transaction():
            # 1. username ต้องไม่ซ้ำ
            dup_user = await conn.fetchval(
                "SELECT id FROM users WHERE username = $1 AND deleted_at IS NULL",
                username
            )
            if dup_user:
                raise ConflictError(f"username '{username}' มีผู้ใช้อยู่แล้วในระบบ")

            # 2. room ตาม room_code (ต้องมีอยู่แล้ว — เลือกจาก dropdown)
            room = None
            if room_code:
                room = await conn.fetchrow(
                    "SELECT id, level, room_code FROM rooms WHERE room_code = $1 AND deleted_at IS NULL",
                    room_code
                )
                if not room:
                    raise NotFoundError(f"ไม่พบห้องเรียน {room_code}")

            # 3. สร้าง user
            full_name = f"{prefix or ''} {first_name or ''} {last_name or ''}".strip()
            user_id = await conn.fetchval(
                """
                INSERT INTO users (username, password_hash, full_name, must_change_password)
                VALUES ($1, $2, $3, $4)
                RETURNING id
                """,
                username, hashed, full_name or None, must_change
            )

            # 4. ตรวจ student เดิมในห้องนั้น (student_id ซ้ำกันในห้อง) → Conflict
            #
            # 🌟 ต้องเจาะจง **"ปีเดียวกัน"** (migration 027) — ไม่งั้นเด็กที่เลื่อนชั้นแล้ว
            #    (มีแถวปีเก่าค้างอยู่คนละแถว) จะถูกหาว่า "ซ้ำ" ทั้งที่คนละปี ⇒ สร้างไม่ได้เลย
            #    ⚠️ ใช้ **ปีปัจจุบัน** ให้ตรงกับ DEFAULT ที่ INSERT ด้านล่างจะได้รับ
            #       (ถ้าสองนี้ไม่ตรงกัน ด่านนี้จะเฝ้าผิดช่องแล้วปล่อยของซ้ำผ่าน)
            #    ⚠️ หาปีไม่เจอ → `academic_year_id = NULL` ไม่มีทางเป็นจริง ⇒ ไม่เจอ dup
            #       ซึ่งปลอดภัยเพราะยังมี unique index `uq_students_room_student_active`
            #       เป็นด่านสุดท้ายอยู่ดี (ด่านนี้เป็น "ข้อความไทยที่อ่านรู้เรื่อง" ไม่ใช่ด่านจริง)
            current_year = await year_service.fetch_current_year(conn)
            dup_year_id = current_year["id"] if current_year else None

            room_id = room["id"] if room else None
            if room_id is not None:
                dup_student = await conn.fetchval(
                    """
                    SELECT id FROM students
                    WHERE room_id = $1 AND student_id = $2 AND deleted_at IS NULL
                      AND academic_year_id = $3
                    """,
                    room_id, student_id, dup_year_id
                )
            else:
                dup_student = await conn.fetchval(
                    """
                    SELECT id FROM students
                    WHERE room_id IS NULL AND student_id = $1 AND deleted_at IS NULL
                      AND academic_year_id = $2
                    """,
                    student_id, dup_year_id
                )
            if dup_student:
                raise ConflictError(f"มีนักเรียนรหัส {student_id} ในระบบนี้อยู่แล้ว")

            # 5. staff_level (ครูทั่วไป = ระดับชั้นของห้อง)
            staff_level = room["level"] if class_role == "teacher" and room else None

            # 6. สร้าง student
            student_row_id = await conn.fetchval(
                """
                INSERT INTO students
                    (room_id, user_id, student_id, student_no,
                     prefix, first_name, last_name, nickname,
                     class_role, staff_level, is_admin, permissions, responsibilities)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                RETURNING id
                """,
                room_id, user_id, student_id, student_no,
                prefix, first_name, last_name, nickname,
                class_role, staff_level, role_is_admin,
                json.dumps(role_perms), json.dumps(new_resp)
            )

            # 🛡️ Audit log (ทุก create ต้องบันทึกใน transaction เดียวกัน)
            await AuditLogger("student_service").log(
                conn=conn,
                action="CREATE_STUDENT",
                actor_identifier=str(actor_user_id) if actor_user_id else "system",
                client_source=client_source,
                user_id=actor_user_id,
                entity_type="student",
                entity_id=student_row_id,
                new_values={
                    "username": username,
                    "student_id": student_id,
                    "room_code": room_code,
                    "class_role": class_role,
                    "staff_level": staff_level,
                    "responsibilities": new_resp,
                    "must_change_password": must_change,
                },
                endpoint_or_command="POST /students",
            )

            return student_row_id


# ============================================================
# 👤 โปรไฟล์ตัวเอง (My Profile)
# ============================================================
async def get_my_profile(pool: asyncpg.Pool, user_id: int) -> dict:
    """ดึงข้อมูลโปรไฟล์ตัวเอง (จาก students + users + room)"""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                s.id, s.student_id, s.student_no, s.prefix, s.first_name, s.last_name,
                s.nickname, s.class_role, s.staff_level, s.status, s.room_id,
                r.room_code, r.room_name, r.level,
                u.username, u.full_name, u.phone_number, u.email
            FROM students s
            JOIN users u ON u.id = s.user_id
            LEFT JOIN rooms r ON r.id = s.room_id
            WHERE s.user_id = $1 AND s.deleted_at IS NULL AND s.status = 'active'
            ORDER BY s.id LIMIT 1
            """,
            user_id
        )
    if not row:
        raise NotFoundError("ไม่พบโปรไฟล์ของคุณ — กรุณาติดต่อผู้ดูแล")

    return dict(row)


async def update_my_profile(pool: asyncpg.Pool, user_id: int, *, prefix=None, first_name=None, last_name=None, nickname=None, phone_number=None, email=None) -> None:
    """แก้ไขโปรไฟล์ตัวเอง (เฉพาะฟิลด์ที่ส่งมา)"""
    async with pool.acquire() as conn:
        async with conn.transaction():
            # หา student ของ user
            student = await conn.fetchrow(
                """
                SELECT id FROM students
                WHERE user_id = $1 AND deleted_at IS NULL AND status = 'active'
                ORDER BY id LIMIT 1
                """,
                user_id
            )
            if not student:
                raise NotFoundError("ไม่พบโปรไฟล์ของคุณ")

            # เก็บค่าเดิม → ใหม่ สำหรับ audit
            old = await conn.fetchrow(
                "SELECT prefix, first_name, last_name, nickname FROM students WHERE id = $1",
                student["id"]
            )

            # ตั้งค่าใหม่ (เฉพาะที่ส่งมา)
            new_prefix = prefix if prefix is not None else old["prefix"]
            new_first = first_name if first_name is not None else old["first_name"]
            new_last = last_name if last_name is not None else old["last_name"]
            new_nick = nickname if nickname is not None else old["nickname"]

            await conn.execute(
                """
                UPDATE students
                SET prefix = $1, first_name = $2, last_name = $3, nickname = $4,
                    updated_at = NOW()
                WHERE id = $5
                """,
                new_prefix, new_first, new_last, new_nick, student["id"]
            )

            # อัปเดต users (full_name, phone, email)
            user_fields = []
            user_params = [user_id]
            if first_name is not None or last_name is not None:
                full_name = f"{new_prefix or ''} {new_first or ''} {new_last or ''}".strip()
                user_fields.append("full_name = $%d" % (len(user_params) + 1))
                user_params.append(full_name)
            if phone_number is not None:
                user_fields.append("phone_number = $%d" % (len(user_params) + 1))
                user_params.append(phone_number)
            if email is not None:
                user_fields.append("email = $%d" % (len(user_params) + 1))
                user_params.append(email)

            if user_fields:
                await conn.execute(
                    f"UPDATE users SET {', '.join(user_fields)}, updated_at = NOW() WHERE id = $1",
                    *user_params
                )

            # 🛡️ Audit log (ทุก UPDATE ต้องบันทึกใน transaction เดียวกัน)
            from core.logger import AuditLogger
            await AuditLogger("student_service").log(
                conn=conn, action="UPDATE_PROFILE",
                actor_identifier=str(user_id), client_source="web",
                user_id=user_id, entity_type="user", entity_id=user_id,
                old_values={
                    "prefix": old["prefix"], "first_name": old["first_name"],
                    "last_name": old["last_name"], "nickname": old["nickname"],
                    "phone_number": None, "email": None,
                },
                new_values={
                    "prefix": new_prefix, "first_name": new_first,
                    "last_name": new_last, "nickname": new_nick,
                    "phone_number": phone_number, "email": email,
                },
                endpoint_or_command="PATCH /students/me/profile",
            )



# ============================================================
# 🔀 ย้ายห้องเป็นกลุ่ม (P5) — เขียน `student_moves` + audit ใน transaction เดียว
# ============================================================
async def bulk_move_students(
    pool: asyncpg.Pool,
    *,
    actor_user_id: int,
    student_ids: list[int],
    to_room_code: str,
    note: Optional[str] = None,
    manage_mode: Optional[dict] = None,
    client_source: str = "web",
) -> dict:
    """ย้ายแถวสมาชิกหลายคนเข้าห้องเดียว **ภายในปีปัจจุบันเท่านั้น**

    `manage_mode` = ผลของ `get_manage_mode()` (router คำนวณมาให้ — service ไม่ควรถือ
    logic สิทธิ์ซ้ำ) · `mode == 'school'` ย้ายได้ทุกห้อง · ครู/ประธานระดับย้ายได้เฉพาะ
    ระดับชั้นของตัวเอง **ทั้งห้องต้นทางและปลายทาง**

    🛡️ **กันแถว active ซ้อน** (บทเรียนเดียวกับ `import_service`): ถ้ามีแถวอื่นของ
    นักเรียนคนเดียวกันในปีเดียวกันที่ยัง active อยู่ห้องอื่น → ตั้ง `superseded`
    (ทำ *หลัง* ย้ายแล้ว จึงไม่แตะแถวที่เพิ่งย้าย) · กรณีที่ห้องปลายทางมีแถวของคนนี้อยู่แล้ว
    จะชน unique index (028) ⇒ แถวนั้นชนะ แถวที่เลือกมาถูก `superseded` แทน
    (ประวัติการย้ายยังถูกบันทึกครบ)
    """
    if not student_ids:
        raise ValidationError("ต้องเลือกนักเรียนอย่างน้อย 1 คน")

    from core.logger import AuditLogger

    async with pool.acquire() as conn:
        async with conn.transaction():
            current_year = await year_service.fetch_current_year(conn)
            if not current_year:
                raise ValidationError("ยังไม่มีปีการศึกษาปัจจุบัน — ตั้งปีก่อนย้ายห้อง")

            target = await conn.fetchrow(
                "SELECT id, room_code, level FROM rooms WHERE room_code = $1 AND deleted_at IS NULL",
                to_room_code,
            )
            if not target:
                raise NotFoundError(f"ไม่พบห้อง {to_room_code}")

            rows = await conn.fetch(
                """SELECT s.id, s.user_id, s.room_id, s.student_id, s.student_no,
                          s.academic_year_id, s.class_role, r.level
                   FROM students s
                   LEFT JOIN rooms r ON r.id = s.room_id
                   WHERE s.id = ANY($1::int[]) AND s.deleted_at IS NULL
                   FOR UPDATE OF s""",
                list(student_ids),
            )
            found = {r["id"] for r in rows}
            missing = [sid for sid in student_ids if sid not in found]
            if missing:
                raise NotFoundError(f"ไม่พบแถวสมาชิก id: {missing}")

            # --- ขอบเขตปี: ย้ายข้ามปี = เลื่อนชั้น/ย้อนหลัง ไม่ใช่ "ย้ายห้อง" ---
            wrong_year = [r["id"] for r in rows if r["academic_year_id"] != current_year["id"]]
            if wrong_year:
                raise ValidationError(
                    "ย้ายได้เฉพาะสมาชิกของปีปัจจุบัน (แถว id: "
                    + ", ".join(str(i) for i in wrong_year)
                    + ")"
                )

            # --- ขอบเขตสิทธิ์: ครู/ประธานระดับได้เฉพาะระดับของตัวเอง ---
            mode = (manage_mode or {}).get("mode")
            grade = (manage_mode or {}).get("grade")
            if mode != "school":
                if not grade:
                    raise ValidationError("คุณไม่มีขอบเขตระดับชั้น — ย้ายห้องไม่ได้")
                if target["level"] != grade:
                    raise ValidationError(f"คุณย้ายได้เฉพาะห้องในระดับ {grade}")
                bad = [r["id"] for r in rows if r["level"] != grade]
                if bad:
                    raise ValidationError(
                        f"มีนักเรียนนอกระดับ {grade} อยู่ในรายการ (แถว id: "
                        + ", ".join(str(i) for i in bad)
                        + ")"
                    )

            moved: list[dict] = []
            skipped: list[dict] = []
            superseded: list[int] = []

            for r in rows:
                if r["room_id"] == target["id"]:
                    skipped.append({"id": r["id"], "student_id": r["student_id"], "reason": "อยู่ในห้องนี้แล้ว"})
                    continue

                # ห้องปลายทางมีแถวของนักเรียนคนนี้ในปีเดียวกันอยู่แล้ว → แถวนั้นชนะ
                # (หลีกเลี่ยง UniqueViolation ของ index 028 — ประวัติการย้ายยังบันทึก)
                exists_target = await conn.fetchval(
                    """SELECT 1 FROM students
                       WHERE room_id = $1 AND academic_year_id = $2 AND student_id = $3
                         AND deleted_at IS NULL AND id <> $4""",
                    target["id"], r["academic_year_id"], r["student_id"], r["id"],
                )
                if exists_target:
                    await conn.execute(
                        "UPDATE students SET status = 'superseded', updated_at = NOW() WHERE id = $1",
                        r["id"],
                    )
                    superseded.append(r["id"])
                else:
                    await conn.execute(
                        "UPDATE students SET room_id = $1, updated_at = NOW() WHERE id = $2",
                        target["id"], r["id"],
                    )

                # 🛡️ กัน active ซ้อน — แตะเฉพาะแถวห้องอื่นของคนเดียวกันในปีเดียวกัน
                #    (แถวที่เพิ่งย้ายอยู่ใน target แล้ว จึงไม่ถูกแตะ)
                dup_ids = await conn.fetch(
                    """UPDATE students SET status = 'superseded', updated_at = NOW()
                       WHERE academic_year_id = $1 AND student_id = $2 AND deleted_at IS NULL
                         AND status = 'active' AND room_id IS NOT NULL AND room_id <> $3
                       RETURNING id""",
                    r["academic_year_id"], r["student_id"], target["id"],
                )
                superseded.extend(d["id"] for d in dup_ids)

                await conn.execute(
                    """INSERT INTO student_moves
                           (student_row_id, user_id, student_id, from_room_id, to_room_id,
                            academic_year_id, note, moved_by)
                       VALUES ($1, $2, $3, $4, $5, $6, $7, $8)""",
                    r["id"], r["user_id"], r["student_id"], r["room_id"], target["id"],
                    r["academic_year_id"], note, actor_user_id,
                )
                moved.append({
                    "id": r["id"],
                    "student_id": r["student_id"],
                    "from_room_id": r["room_id"],
                    "to_room_id": target["id"],
                })

            await AuditLogger("student_service").log(
                conn=conn,
                action="MOVE_STUDENTS",
                actor_identifier=str(actor_user_id),
                client_source=client_source,
                user_id=actor_user_id,
                entity_type="student",
                entity_id=None,
                old_values={"moved": moved, "to_room_code": to_room_code},
                new_values={"note": note, "superseded_ids": superseded},
                endpoint_or_command="POST /students/bulk-move",
            )

            return {
                "moved": moved,
                "skipped": skipped,
                "superseded_ids": superseded,
                "to_room": {"id": target["id"], "room_code": target["room_code"]},
            }


# ============================================================
# 🧾 ประวัติรายคน (P5) — timeline จาก 2 แหล่ง: ข้ามปี (students) + ย้ายในปี (student_moves)
# ============================================================
async def get_student_history(pool: asyncpg.Pool, student_row_id: int) -> dict:
    """ประวัติของสมาชิก `student_row_id` — ผูกด้วย `user_id` จึงเห็นทุกปี

    ⚠️ ไม่กรอง `status` — ประวัตินี้ต้องเห็น `promoted`/`graduated` ด้วย ซึ่งเป็น
       หัวใจของข้อตัดสินใจ "เด็กจบต้องค้นชื่อเจอ" (P6 จะต่อ UI เข้ากับฟังก์ชันนี้)
    """
    async with pool.acquire() as conn:
        root = await conn.fetchrow(
            """SELECT s.id, s.user_id, s.student_id, u.full_name
               FROM students s LEFT JOIN users u ON u.id = s.user_id
               WHERE s.id = $1 AND s.deleted_at IS NULL""",
            student_row_id,
        )
        if not root:
            raise NotFoundError("ไม่พบนักเรียน")
        if root["user_id"] is None:
            raise ValidationError("แถวนี้ไม่ผูกกับผู้ใช้ — ดูประวัติข้ามปีไม่ได้")

        years = await conn.fetch(
            """SELECT s.id AS student_row_id, s.academic_year_id, y.year_be,
                      s.room_id, r.room_code, r.level, s.student_no,
                      s.class_role, s.status
               FROM students s
               LEFT JOIN academic_years y ON y.id = s.academic_year_id
               LEFT JOIN rooms r ON r.id = s.room_id
               WHERE s.user_id = $1 AND s.deleted_at IS NULL
               ORDER BY y.year_be DESC NULLS LAST, s.id DESC""",
            root["user_id"],
        )
        moves = await conn.fetch(
            """SELECT m.id, m.from_room_id, fr.room_code AS from_room_code,
                      m.to_room_id, tr.room_code AS to_room_code,
                      m.academic_year_id, y.year_be, m.note, m.moved_by,
                      u.full_name AS moved_by_name, m.moved_at
               FROM student_moves m
               LEFT JOIN rooms fr ON fr.id = m.from_room_id
               LEFT JOIN rooms tr ON tr.id = m.to_room_id
               LEFT JOIN academic_years y ON y.id = m.academic_year_id
               LEFT JOIN users u ON u.id = m.moved_by
               WHERE m.user_id = $1
               ORDER BY m.moved_at DESC, m.id DESC""",
            root["user_id"],
        )

    return {
        "user_id": root["user_id"],
        "student_id": root["student_id"],
        "full_name": root["full_name"],
        "years": [dict(r) for r in years],
        "moves": [dict(r) for r in moves],
    }
