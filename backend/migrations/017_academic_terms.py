"""017 — ตาราง `academic_terms` (ภาคเรียน)

ทำไมต้องมีตารางจริง ไม่ใช่ key-value / .env:
  โรงเรียนถามคำถามว่า "ภาคนี้เป็นยังไง" ⇒ ต้องกรองสถิติตามช่วงวันที่ของภาค
  และต้อง **ดูย้อนหลังได้** (ภาคที่แล้วเป็นยังไง) ⇒ เก็บเป็นแถวมีประวัติ
  ต่างจาก `is_current` ที่เป็น "สถานะตอนนี้" ซึ่งเปลี่ยนได้ตลอด

"ภาคปัจจุบัน" มีได้ตัวเดียว — บังคับด้วย **partial unique index** ไม่ใช่ด้วยโค้ด:
    CREATE UNIQUE INDEX uq_academic_terms_single_current
        ON academic_terms (is_current) WHERE is_current AND deleted_at IS NULL
  ทริก: key ของ index คือ `is_current` แต่กรอง `WHERE is_current` ⇒ ใน index
  มีแต่แถวที่ is_current = TRUE และ key ทุกตัวเท่ากัน (TRUE) ⇒ unique เหลือได้ตัวเดียว
  ⚠️ index เป็น **non-deferrable** ⇒ ใน service ต้อง "ล้างตัวเก่าก่อน แล้วค่อยตั้งตัวใหม่"
     ใน transaction เดียวกัน ถ้าตั้งก่อนล้างจะชนกันเอง (UniqueViolationError)

`end_date` เป็น **inclusive** (รวมวันสุดท้าย) — ระบุไว้ชัดเพราะเป็นจุดที่พลาดง่าย
เวลากรองต้องใช้ `< end_date + 1 วัน` ไม่ใช่ `<= end_date` (ดู me_service)

ไม่มี backfill: โรงเรียนยังไม่เคยตั้งภาค ⇒ ระบบต้องอยู่ได้โดยไม่มีภาคปัจจุบัน
(`get_current_term` คืน None → สถิติทั้งหมด) นั่นคือสถานะตั้งต้นที่ถูกต้อง
ไม่ใช่ "สร้างภาคเดา ๆ ให้" ซึ่งจะทำให้ตัวเลขผิดอย่างเงียบ ๆ
"""
VERSION = "017_academic_terms"
DESCRIPTION = "academic_terms: ภาคเรียน (มีภาคปัจจุบันได้ตัวเดียว + end_date รวมวันสุดท้าย)"


async def upgrade(conn) -> None:
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS academic_terms (
            id SERIAL PRIMARY KEY,
            name VARCHAR(50) NOT NULL,
            start_date DATE NOT NULL,
            end_date DATE NOT NULL,
            is_current BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            deleted_at TIMESTAMP WITH TIME ZONE,
            CONSTRAINT chk_academic_terms_range CHECK (end_date >= start_date)
        );
    """)

    # มีภาคปัจจุบันได้ตัวเดียว (ดูคำอธิบายทริกด้านบน)
    await conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_academic_terms_single_current
            ON academic_terms (is_current) WHERE is_current AND deleted_at IS NULL;
    """)

    # คิวรีหลักคือ "ภาคที่คลุมวันนี้" และ "ภาคตามช่วงวันที่" ⇒ index บนช่วงวันพอ
    await conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_academic_terms_dates
            ON academic_terms (start_date, end_date);
    """)
