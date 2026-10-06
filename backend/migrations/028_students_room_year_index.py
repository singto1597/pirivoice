"""028 — สลับ unique index ของ `students` ให้มีมิติปี + ผูกปีเข้ากับงาน import

**ปัญหาที่แก้:** index เดิม `uq_students_room_student_active (room_id, student_id)`
  **ไม่มีมิติปี** ⇒ มันห้ามคนเดิมมีสองแถวในห้องเดิม "คนละปี" ซึ่งเป็นสิ่งที่เราต้องการให้มีได้
  ⇒ ถ้าไม่สลับ **`apply_rollover` (P4) จะ insert แถวของปีใหม่ไม่ได้เลย** (UniqueViolation)
     เพราะแถวปีใหม่คือ (ห้องเดิม, รหัสเดิม) — ต่างกันแค่ปี

🔴 **migration นี้ "ไม่ additive" — ต้องออกพร้อมโค้ดที่รู้จักปีเท่านั้น:**
  หลัง DROP แล้ว **`ON CONFLICT (room_id, student_id)` ของ image เก่าจะใช้ไม่ได้อีก**
  (ไม่มี arbiter ที่เข้าเงื่อนไข ⇒ PostgreSQL โยน "there is no unique or exclusion
  constraint matching the ON CONFLICT specification") ⇒ **เส้นทาง import ของ image เก่าพัง**
  ⇒ แยกจาก 027 โดยเจตนา: 027 additive ล้วน deploy เดี่ยวได้ · **028 = deploy พร้อมโค้ด import ใหม่**
  ⇒ **rollback plan คือ "restore dump" ไม่ใช่ `oh_shit.sh`** (reverse migration ทำได้แค่
     *ก่อน* ที่จะมีแถวปีที่สองในห้องเดียวกัน — ซึ่งครูสร้างได้ทันทีหลัง deploy)
  ⇒ **ต้องถ่าย dump ใหม่ก่อน deploy**

✅ **ทำไมสลับได้อย่างปลอดภัยกับข้อมูลเดิม:** index ใหม่ **อ่อนกว่า** เดิม (เพิ่มคอลัมน์เข้าไป
  ในคีย์ ⇒ แถวชุดเดิมที่ผ่านของเดิม ย่อมผ่านของใหม่เสมอ) ⇒ ไม่มีทางที่ CREATE UNIQUE INDEX
  จะล้มเพราะข้อมูลเดิมขัดแย้ง · แถวที่ `student_id IS NULL` ยังไม่ชนกันทั้งสองแบบ (NULL ≠ NULL)

**ทำไม `student_import_jobs.academic_year_id` ต้องมี:** งาน import ต้องรู้ว่า "กำลังนำเข้า
  ชุดรายชื่อของปีไหน" ⇒ ไฟล์ Excel ที่ไม่มีคอลัมน์ `ปีการศึกษา` จะใช้ปีของ job นี้
  (ช่องว่างในเซลล์ = ใช้ปีของ job — ไม่ใช่ "เดาปีปัจจุบัน" ซึ่งจะผิดถ้ากำลัง import ย้อนหลัง)
  nullable โดยเจตนา: job เก่าที่ค้างอยู่ในตารางยังอ่านได้ (fallback = ปีปัจจุบัน)

**เทียบกับ init_db:** DDL ที่นี่ถูก mirror ไว้ใน `core/init_db.py` ทั้งสองจุด
  (`uq_students_room_year_student` ในบล็อก index · คอลัมน์ในตาราง `student_import_jobs`)
  ⇒ **ห้ามแก้ที่เดียว** ไม่งั้น fresh DB (ที่ init_db สร้าง) กับ DB จริง (ที่ 028 แก้)
  จะได้ schema คนละแบบ แล้วเทสต์จะผ่านทั้งที่ production พัง
"""
VERSION = "028_students_room_year_index"
DESCRIPTION = "students: สลับ unique index เป็น (room_id, academic_year_id, student_id) + student_import_jobs.academic_year_id"

import asyncpg


async def upgrade(conn: asyncpg.Connection) -> None:
    # --- 1. สลับ unique index ให้มีมิติปี ---------------------------------------
    # ⚠️ ลำดับสำคัญ: DROP ก่อน CREATE เสมอ — ถ้าปล่อยให้มีสองตัวพร้อมกัน แถวปีใหม่จะยัง
    #    ถูกบล็อกด้วยตัวเก่า (สร้าง index ใหม่สำเร็จแต่ไม่ได้ผลอะไร — หลอกตัวเองว่าย้ายแล้ว)
    await conn.execute("DROP INDEX IF EXISTS uq_students_room_student_active")

    await conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_students_room_year_student
            ON students(room_id, academic_year_id, student_id)
            WHERE deleted_at IS NULL;
    """)

    # --- 2. ผูกปีเข้ากับงาน import ----------------------------------------------
    await conn.execute("""
        ALTER TABLE student_import_jobs
            ADD COLUMN IF NOT EXISTS academic_year_id INTEGER
                REFERENCES academic_years(id);
    """)
