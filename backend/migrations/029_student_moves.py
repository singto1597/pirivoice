"""029 — ประวัติการย้ายห้อง "ภายในปีเดียวกัน" (`student_moves`)

**ปัญหาที่แก้:** การย้ายห้องคือ `UPDATE students.room_id` ทับ ⇒ **ห้องเดิมหายไปจากระบบ**
  ไม่มีใครตอบได้ว่า "คนนี้ย้ายมาจากไหน ใครย้าย ให้เหตุผลอะไร" · การเลื่อนชั้น (P4)
  เก็บประวัติได้แล้วเพราะมีแถวต่อปี แต่การย้าย _ในปีเดียวกัน_ ไม่มีแถวให้ดู

**ทำไมเก็บเฉพาะการย้ายในปี ไม่เก็บการเลื่อนชั้นซ้ำ:**
  การเลื่อนชั้นอ่านได้จากแถว `students` ของปีเก่า/ใหม่เองอยู่แล้ว (ห้อง + ตำแหน่ง + สถานะ)
  ⇒ ถ้าบันทึกซ้ำในตารางนี้ ประวัติจะขัดกันเองเมื่อมีคนไปแก้ข้อมูลย้อนหลัง
  หน้าประวัติจึงประกอบ timeline จาก **สองแหล่ง**: `students` (ข้ามปี) + `student_moves` (ในปี)

**FK เป็น `ON DELETE SET NULL` ทุกตัว โดยเจตนา:**
  ประวัตินี้เป็นหลักฐาน "ใครทำอะไร" ⇒ ห้ามหายตามการลบห้อง/ผู้ใช้ (บทเรียนเดียวกับ
  `announcements.created_by` ที่ไม่ใส่ FK) · snapshot `student_id` เก็บไว้ให้อ่านได้
  แม้แถว `students` ต้นทางจะถูกลบถาวรในภายหลัง

**เทียบกับ init_db:** DDL นี้ mirror ไว้ใน `core/init_db.py` (บล็อก 8.8 ก่อน `announcements`)
  ⇒ **ห้ามแก้ที่เดียว** ไม่งั้น fresh DB กับ DB จริงจะได้ schema คนละแบบ
"""
VERSION = "029_student_moves"
DESCRIPTION = "student_moves: ประวัติการย้ายห้องภายในปี (ใครย้าย จากไหน ไปไหน ใครสั่ง)"

import asyncpg


async def upgrade(conn: asyncpg.Connection) -> None:
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS student_moves (
            id SERIAL PRIMARY KEY,
            -- แถวสมาชิกที่ถูกย้าย (1 คน × 1 ปี) — NULL ได้ถ้าแถวนั้นถูกลบถาวรภายหลัง
            student_row_id INTEGER REFERENCES students(id) ON DELETE SET NULL,
            -- คนเดียวข้ามปีได้ ⇒ ผูก user ไม่ใช่แถว เพื่อให้ timeline ต่อกันได้ทั้งชีวิต
            user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            student_id VARCHAR(10),                    -- snapshot กันข้อความอ้างอิงหาย
            from_room_id INTEGER REFERENCES rooms(id) ON DELETE SET NULL,
            to_room_id   INTEGER REFERENCES rooms(id) ON DELETE SET NULL,
            academic_year_id INTEGER REFERENCES academic_years(id),
            note TEXT,
            moved_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
            moved_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # หน้าประวัติรายคน: WHERE user_id = $1 ORDER BY moved_at DESC
    await conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_student_moves_user
            ON student_moves(user_id, moved_at DESC);
    """)
    # รายงานรายปี (P6): "ปีนี้ย้ายกี่คน"
    await conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_student_moves_year
            ON student_moves(academic_year_id, moved_at DESC);
    """)
