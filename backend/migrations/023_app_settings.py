"""023 — `app_settings` (ค่าตั้งระดับโรงเรียน แบบ key/value jsonb)

ภูมิหลัง (A8 Quiet Hours): ตอนนี้ `push_outbox` ยิงทุกแจ้งเตือนออกทันทีไม่ว่าเวลากี่โมง
โรงเรียนอยาก "ปิด push ทั้งระบบช่วงสอบ" หรือ "ไม่ให้มีเสียงตอนกลางคืน" ได้
⇒ ต้องมีที่เก็บค่าตั้ง **ระดับโรงเรียน** (ไม่ใช่รายผู้ใช้) ที่สภาแก้เองได้โดยไม่ต้อง deploy

⭐ **ทำไม `jsonb` ไม่ใช่คอลัมน์แยก (`quiet_start` / `quiet_end` / `quiet_enabled`)**
   1. ตารางนี้เป็นที่วางของทุกอย่างที่เป็น "ค่าตั้งของระบบ" ไม่ใช่แค่ quiet hours
      ⇒ วันหน้าจะมี `push_muted_types` (ดู §20.14 ข้อ 7 ของแผน), `home_banner`, …
      ถ้าใช้คอลัมน์แยก ทุกค่าตั้งใหม่ = 1 migration
   2. รูปร่างของ quiet hours **จะโต** (เช่น เพิ่ม "ยกเว้นวันเสาร์-อาทิตย์", "ช่วงที่สอง")
      ⇒ JSONB รับได้โดยไม่ต้อง migrate — **เหตุผลเดียวกับที่ `notification_preferences`
      และ `bookmarks` จงใจไม่ใส่ CHECK constraint** (ดู 016 L21-25 · 021 L14-18)
   3. Validation ย้ายไปอยู่ที่ **Pydantic + service** ซึ่งตอบ 400 พร้อมข้อความไทย
      และมีเทสต์คุมอยู่ (`test_quiet_hours.py`) — ไม่ใช่ที่ DB

⚠️ **ไม่มี CHECK บน `key` และไม่มี FK ไปไหน** — `key` เป็น PK (varchar) จึง unique อยู่แล้ว
   ส่วนความหมายของแต่ละ key อยู่ใน service ไม่ใช่ในสคีมา

⭐ **"ไม่มีแถว" = ไม่ปิดกั้นอะไร** — เป็นหลักเดียวกับ A2 (`notification_preferences`:
   "ไม่มีแถว = เปิดรับ") ⇒ ปรัชญาคือ **ค่าตั้งต้นต้องเป็นการไม่ปิดกั้น** ไม่ใช่การปิดกั้น
   ⇒ migration นี้ **ไม่ seed แถว `quiet_hours`** ให้เอง · แถวจะเกิดเมื่อมีคนกดบันทึกครั้งแรก
     (seed ไปก็มีแต่ความเสี่ยง: ถ้า seed แล้ววันหน้าอยากเปลี่ยนค่าเริ่มต้น ต้อง migrate แถวที่ seed ไว้ทิ้ง)

⚠️ **`updated_by` เป็น `ON DELETE SET NULL` ไม่ใช่ CASCADE** — การลบบัญชีผู้ดูแล
   **ต้องไม่ทำให้ค่าตั้งของโรงเรียนหายไป** (คนลาออก ≠ โรงเรียนเลิกใช้ quiet hours)

📌 ตรงกับธรรมเนียมโปรเจค: ตารางถูก **mirror ลง `core/init_db.py`** ด้วย (ที่นั่นไม่มี index
   เพิ่ม เพราะ PK เป็น index อยู่แล้ว) — ต่างจาก function/trigger ของ 018/020 ที่อยู่ที่เดียว
"""
VERSION = "023_app_settings"
DESCRIPTION = "app_settings: ค่าตั้งระดับโรงเรียนแบบ key/value jsonb (A8 quiet hours)"


async def upgrade(conn) -> None:
    # ============================================================
    # ค่าตั้งของระบบ — key/value ล้วน ไม่มีความหมายฝังในสคีมา
    # ============================================================
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS app_settings (
            key VARCHAR(60) PRIMARY KEY,
            value JSONB NOT NULL,
            description TEXT,
            updated_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # ⚠️ **ไม่มี index เพิ่มโดยเจตนา** — PK บน `key` เป็น index อยู่แล้ว และการอ่าน
    #    ทั้งหมดเป็นการ point lookup (`WHERE key = $1`) ⇒ index อื่นมีแต่ทำให้ write ช้าลง
    #    (เหตุผลเดียวกับ `notification_preferences` ใน 016 L33-35)
