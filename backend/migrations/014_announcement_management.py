"""
Migration: 014 — ประกาศ: คอลัมน์ผู้ประกาศ + backfill สิทธิ์ MANAGE_ANNOUNCEMENTS
================================================================================
ภูมิหลัง: ตาราง `announcements` เดิมเขียนได้ทางเดียวคือ seed ตอน init_db
⇒ จะเปิด CRUD ผ่านหน้าเว็บ ต้องเติม 2 อย่างในชั้นสคีมา

(ก) `created_by` / `updated_by` — รู้ว่าใครประกาศ/แก้ล่าสุด
    ⭐ **ไม่ใส่ FK โดยเจตนา** (บทเรียน skills.md:623-629): ตารางที่ต้องเก็บความจริง
       ย้อนหลังห้าม FK แบบ `ON DELETE` action ใด ๆ เพราะ "ลบผู้ใช้ = หลักฐานหาย"
       ⇒ เก็บเป็น INTEGER เปล่า แล้ว LEFT JOIN users เอาเองตอนอ่าน
       (แบบเดียวกับ `audit_logs.user_id` ตั้งแต่ migration 013)
       NULL = ประกาศที่ seed ไว้ก่อนมีฟีเจอร์นี้ (ไม่รู้ว่าใครสร้าง)

(ข) backfill สิทธิ์ `MANAGE_ANNOUNCEMENTS` ให้ผู้ใช้ที่มีอยู่แล้ว
    ⚠️ **นี่คือเหตุผลที่ต้องมี migration ไม่ใช่แก้แค่ config/roles.json:**
       `students.permissions` เป็น "snapshot" ที่ถูกเขียนเฉพาะตอนสร้าง/เปลี่ยนตำแหน่ง
       (`auth_service.register_user`, `import_service`, `student_service.update_student`,
        `seed_users`) — **ไม่มีกลไก sync จาก roles.json ย้อนหลังเลย**
       ⇒ แก้ roles.json เฉย ๆ ผู้ใช้เดิมจะไม่ได้สิทธิ์ **โดยไม่มี error ให้เห็น**
       ⇒ อาการที่จะเจอ: สภานักเรียนล็อกอินแล้วไม่เห็นเมนูจัดการประกาศ แล้วหาสาเหตุไม่ได้

    กลุ่มที่เติม:
      - `council_member` — ตัวจริงของการเพิ่มครั้งนี้ (is_admin=false จึงต้องพึ่ง
        permissions จริง ๆ ไม่มีทาง bypass)
      - `admin` / `teacher_council` / `council_president` — ทั้งสาม is_admin=true
        อยู่แล้ว จึงผ่านได้แม้ไม่เติม ; เติมให้ข้อมูลตรงกับความจริงเพื่อให้
        UI/introspection ที่อ่าน permissions ตรง ๆ แสดงถูก

    เงื่อนไข `NOT ... @>` กันสิทธิ์ซ้ำเมื่อรัน migration ซ้ำ (runner เก็บประวัติใน
    `schema_migrations` อยู่แล้ว แต่ migration ทุกตัวต้องรันซ้ำได้ — ดู core/migrations.py)
"""
VERSION = "014_announcement_management"
DESCRIPTION = "announcements: created_by/updated_by (ไม่ใส่ FK) + backfill สิทธิ์ MANAGE_ANNOUNCEMENTS"

# ตำแหน่งที่จะได้รับสิทธิ์จัดการประกาศ — ต้องตรงกับ backend/config/roles.json
_ROLES_WITH_ANNOUNCEMENT_PERMISSION = (
    "council_member",
    "council_president",
    "teacher_council",
    "admin",
)
_PERMISSION = "MANAGE_ANNOUNCEMENTS"


async def upgrade(conn) -> None:
    # --- (ก) คอลัมน์ผู้ประกาศ (idempotent) ---------------------------------------
    await conn.execute(
        "ALTER TABLE announcements ADD COLUMN IF NOT EXISTS created_by INTEGER"
    )
    await conn.execute(
        "ALTER TABLE announcements ADD COLUMN IF NOT EXISTS updated_by INTEGER"
    )

    # --- (ข) backfill สิทธิ์ ------------------------------------------------------
    #   COALESCE(permissions, '[]') ทุกจุด เพื่อให้แถวที่ permissions เป็น NULL
    #   ยังได้รับสิทธิ์ (ไม่งั้น || กับ NULL = NULL แล้ว UPDATE เงียบ ๆ ไม่เกิดอะไร)
    await conn.execute(
        """
        UPDATE students
        SET permissions = COALESCE(permissions, '[]'::jsonb) || $1::jsonb,
            updated_at = NOW()
        WHERE class_role = ANY($2::text[])
          AND deleted_at IS NULL
          AND NOT (COALESCE(permissions, '[]'::jsonb) @> $1::jsonb)
        """,
        f'["{_PERMISSION}"]',
        list(_ROLES_WITH_ANNOUNCEMENT_PERMISSION),
    )
