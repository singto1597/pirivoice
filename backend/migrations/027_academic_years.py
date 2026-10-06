"""027 — ปีการศึกษา (`academic_years`) + `students.academic_year_id`

**ทำไมต้องมี "ปี" แยกจาก "ภาคเรียน" (`academic_terms`):**
  ทั้งสองตอบคนละคำถาม —
    · ภาคเรียน = "ภาคนี้เป็นยังไง" → ใช้ **กรองสถิติตามช่วงวันที่** (me_service / home)
    · ปีการศึกษา = "ปี 2569 ใครอยู่ห้องไหน ตำแหน่งอะไร" → ใช้ **เก็บประวัติสมาชิก** และ
      เป็นแกนของ "เลื่อนชั้นทั้งโรงเรียน"
  เอามารวมกันไม่ได้เพราะ 1 ปีมี 2 ภาค ⇒ "สมาชิกผูกกับภาคไหน" กำกวมตั้งแต่ต้น

**ทำไมไม่สร้าง "ห้องใหม่ทุกปี" (`ม.4/1 ปี 2569`):**
  "ม.4/1" คือห้องเรียนที่มีอยู่จริงในหลักสูตร — สิ่งที่เปลี่ยนทุกปีคือ *คน* ไม่ใช่ห้อง
  ⇒ มิติปีต้องอยู่ที่ "สมาชิก" (`students`) ไม่ใช่ที่ "ห้อง" (`rooms`)
  ⇒ `rooms` ไม่ถูกแตะเลยใน migration นี้ และ `GET /api/rooms` ไม่ต้องแก้

**โมเดล:** 1 แถวใน `students` = สมาชิกของคนหนึ่ง **ในปีหนึ่ง**
  ⇒ เลื่อนชั้น = สร้างแถวใหม่ของปีใหม่ + ปิดแถวเก่าเป็น `status='promoted'`/`'graduated'`
    (ไม่ใช่ UPDATE ทับ ⇒ **ประวัติไม่หาย**)

**ทริกที่ทำให้ขอบเขตเล็ก:** ทุกคิวรีสมาชิกในระบบกรอง `status='active'` อยู่แล้ว
  ⇒ `status='active' AND deleted_at IS NULL` ยังหมายถึง "สมาชิกปีปัจจุบัน" เหมือนเดิม
  ⇒ `require_permission_anywhere` / `get_access_scope` / notification fan-out /
    issue pyramid / board joins **ไม่ต้องแก้** (ดู docs/skills.md ที่บันทึกไว้ท้ายรอบ)

**ทำไม `academic_year_id` ต้องเป็น `NOT NULL DEFAULT <literal id>` ไม่ปล่อย nullable:**
  `NULL` **ไม่ชนกัน** ใน unique index ⇒ ทุกครั้งที่ insert โดยไม่ระบุปีจะสร้างแถวซ้ำเงียบ ๆ
  (กับดักเดียวกับที่บันทึกไว้ที่ `import_service.py` กรณี `room_id IS NULL`)
  และ DEFAULT แบบ literal ทำให้ **image เก่ายังเขียนแถวที่ถูกต้องได้** ระหว่างช่วง
  mixed-version ⇒ 027 จึง deploy เดี่ยวได้และ rollback ด้วย image เก่าได้ทันที
  (ต่างจาก 028 ที่สลับ unique index — ต้องออกพร้อมโค้ด import ที่รู้จักปี)

**ทำไม migration นี้ additive ล้วน:** CREATE TABLE / ADD COLUMN / CREATE INDEX /
  UPDATE backfill / SET DEFAULT — ไม่มี DROP หรือ rename ⇒ DB เก่า + image เก่า
  ทำงานต่อได้ทั้งคู่ (ตรวจด้วย `git diff --numstat` ต้องได้ `-0` ทุกไฟล์)
"""
VERSION = "027_academic_years"
DESCRIPTION = "academic_years: ปีการศึกษา (ปีปัจจุบันมีได้ตัวเดียว) + students.academic_year_id + rollover_runs"

import asyncpg


# ปีการศึกษาไทยเริ่มประมาณเดือน พ.ค. ⇒ ก่อน พ.ค. ยังนับเป็นปีการศึกษาก่อนหน้า
# ใช้ NOW() ที่ Asia/Bangkok (ไม่ใช่ UTC) ไม่งั้นช่วง 00:00–07:00 ของ 1 พ.ค. จะคำนวณปีผิด
_YEAR_BE_SQL = """
    (EXTRACT(YEAR FROM (NOW() AT TIME ZONE 'Asia/Bangkok'))
     - CASE WHEN EXTRACT(MONTH FROM (NOW() AT TIME ZONE 'Asia/Bangkok')) >= 5 THEN 0 ELSE 1 END)::int + 543
"""


async def upgrade(conn: asyncpg.Connection) -> None:
    # --- 1. ปีการศึกษา ---
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS academic_years (
            id SERIAL PRIMARY KEY,
            year_be INTEGER NOT NULL,          -- พ.ศ. เช่น 2569 (ไม่ใช่ ค.ศ.)
            name VARCHAR(50) NOT NULL,         -- "ปีการศึกษา 2569"
            start_date DATE,                   -- ไม่บังคับ — ปีที่ยังไม่รู้วันเปิดเทอมก็สร้างได้
            end_date DATE,
            is_current BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            deleted_at TIMESTAMP WITH TIME ZONE,
            CONSTRAINT chk_academic_years_range
                CHECK (end_date IS NULL OR start_date IS NULL OR end_date >= start_date)
        );
    """)

    # "ปีปัจจุบันมีได้ตัวเดียว" — ทริกเดียวกับ uq_academic_terms_single_current (migration 017):
    # key ของ index คือ is_current แต่กรอง WHERE is_current ⇒ ใน index มีแต่แถวค่า TRUE
    # ⇒ unique เหลือได้ตัวเดียว
    # ⚠️ non-deferrable ⇒ service ต้อง "ล้างตัวเก่าก่อน แล้วค่อยตั้งตัวใหม่" ใน transaction เดียว
    await conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_academic_years_single_current
            ON academic_years (is_current) WHERE is_current AND deleted_at IS NULL;
    """)

    # หนึ่งปี พ.ศ. มีได้หนึ่งแถว — partial (WHERE deleted_at IS NULL) เพื่อให้
    # "ลบแล้วกู้คืน" ได้ ต่างจาก rooms.room_code ที่ UNIQUE ตรง ๆ แล้วกู้คืนไม่ได้ถ้าซ้ำ
    await conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_academic_years_year_be
            ON academic_years (year_be) WHERE deleted_at IS NULL;
    """)

    # --- 2. ประวัติการเลื่อนชั้น (audit artifact ของ preview/apply) ---
    # ต่างจาก student_import_jobs: apply เป็น SQL ล้วน ไม่มี bcrypt/xlsx ⇒ ไม่ต้องเข้า ARQ queue
    # (queue เป็น max_jobs=1 ⇒ ช่วงสัปดาห์ลงทะเบียน โรงเรียนจะรอหลัง import 30 นาที)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS rollover_runs (
            id SERIAL PRIMARY KEY,
            from_year_id INTEGER NOT NULL REFERENCES academic_years(id) ON DELETE RESTRICT,
            to_year_id   INTEGER NOT NULL REFERENCES academic_years(id) ON DELETE RESTRICT,
            status TEXT NOT NULL DEFAULT 'PREVIEWED',   -- PREVIEWED / APPLIED / FAILED
            plan JSONB NOT NULL DEFAULT '{}'::jsonb,    -- snapshot ของ preview ตอนกดยืนยัน
            promoted_count INTEGER NOT NULL DEFAULT 0,
            graduated_count INTEGER NOT NULL DEFAULT 0,
            staff_carried_count INTEGER NOT NULL DEFAULT 0,
            positions_reset_count INTEGER NOT NULL DEFAULT 0,
            unmapped_count INTEGER NOT NULL DEFAULT 0,
            error_message TEXT,
            created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            applied_at TIMESTAMP WITH TIME ZONE,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
    """)
    await conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_rollover_runs_from_to
            ON rollover_runs(from_year_id, to_year_id);
    """)

    # --- 3. ปีตั้งต้น ---
    # ⚠️ สร้างปีให้เฉพาะเมื่อ "ยังไม่มีปีเลย" — เป็นปีที่โรงเรียนกำลังเรียนอยู่จริง
    #    ห้ามข้ามปีไปสร้างปีถัดไปให้ เพราะจะไม่มีใคร active อยู่ ⇒ โรงเรียนล็อกตัวเอง
    await conn.execute(f"""
        INSERT INTO academic_years (year_be, name, is_current)
        SELECT {_YEAR_BE_SQL}, 'ปีการศึกษา ' || ({_YEAR_BE_SQL})::text, TRUE
        WHERE NOT EXISTS (SELECT 1 FROM academic_years WHERE deleted_at IS NULL);
    """)

    # --- 4. คอลัมน์ปีของ "สมาชิก" ---
    # nullable ก่อน ⇒ ADD COLUMN บนตารางที่มีข้อมูลอยู่เป็น metadata-only (PG 11+) ไม่ rewrite
    await conn.execute("""
        ALTER TABLE students ADD COLUMN IF NOT EXISTS academic_year_id INTEGER
            REFERENCES academic_years(id) ON DELETE RESTRICT;
    """)

    # ทุกแถวที่มีอยู่เดิม = สมาชิกของปีปัจจุบัน (นี่คือ backfill ที่ถูก — ไม่ใช่ "เดาปี")
    await conn.execute("""
        UPDATE students
        SET academic_year_id = (
            SELECT id FROM academic_years WHERE is_current AND deleted_at IS NULL LIMIT 1
        )
        WHERE academic_year_id IS NULL;
    """)

    # NOT NULL + DEFAULT <literal> — ต้อง backfill ให้เสร็จก่อน ไม่งั้น SET NOT NULL จะล้ม
    # ⚠️ DEFAULT ต้องเป็นค่า literal ไม่ใช่ subquery ⇒ อ่าน id มาก่อนแล้ว interpolate
    #    (ค่าเป็น int จาก fetchval ⇒ ปลอดภัยจากการ inject)
    current_year_id = await conn.fetchval(
        "SELECT id FROM academic_years WHERE is_current AND deleted_at IS NULL LIMIT 1"
    )
    if current_year_id is not None:
        await conn.execute(
            f"ALTER TABLE students ALTER COLUMN academic_year_id SET DEFAULT {int(current_year_id)}"
        )
    await conn.execute("ALTER TABLE students ALTER COLUMN academic_year_id SET NOT NULL")

    # --- 5. ผูกภาคเรียนเข้าปี (ข้อ 6 ของแผน) ---
    # nullable โดยเจตนา — ภาคเรียนที่สร้างไว้ก่อนมีฟีเจอร์นี้ยังใช้ได้ปกติ (ไม่ต้อง backfill)
    await conn.execute("""
        ALTER TABLE academic_terms ADD COLUMN IF NOT EXISTS academic_year_id INTEGER
            REFERENCES academic_years(id);
    """)

    # --- 6. index ต่อปี ---
    # คิวรีหลักหลังมีปี = "สมาชิกของปีนี้ ในห้องนี้" ⇒ (year, room) พอ
    await conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_students_year_room
            ON students(academic_year_id, room_id) WHERE deleted_at IS NULL;
    """)
