"""024 — `notifications.bypass_quiet_hours` (E2: ประกาศฉุกเฉินต้องทะลุ quiet hours)

ภูมิหลัง: A8 ปิด push ทั้งระบบตามช่วงเวลาได้ (migration 023 + `app_settings.quiet_hours`)
แต่ประกาศ **ฉุกเฉิน** (priority = 'urgent') มีความหมายก็ต่อเมื่อมันทะลุทุกด่าน
⇒ ต้องมีธง **รายแถว** ที่บอกว่า "แจ้งเตือนแถวนี้ได้รับการยกเว้น"

⭐ **ทำไมเป็นคอลัมน์บน `notifications` ไม่ใช่ตาราง/คอลัมน์แยก**
   `push_outbox` **ไม่ denormalize ข้อความ** โดยเจตนา (ดู 018 — JOIN `notifications` ทุกครั้ง)
   ⇒ ด่าน quiet hours ที่อยู่ใน push worker อ่านค่าจาก `notifications` ได้ตรง ๆ
     ด้วยคิวรีเดิมที่ JOIN อยู่แล้ว · ไม่ต้องเพิ่ม JOIN ใหม่และไม่ต้องมีที่เก็บที่สอง

⚠️ **`DEFAULT FALSE` + `NOT NULL` — ปลอดภัยกับตารางที่มีข้อมูลอยู่แล้ว**
   PG 11+ ทำ `ADD COLUMN … DEFAULT <constant>` แบบ **ไม่ rewrite ตาราง** (เก็บค่า default
   ไว้ใน catalog) ⇒ ตาราง `notifications` บน production (266 แถว) ได้ค่า FALSE ทันที
   โดยไม่ล็อกตารางนาน · และ **image เก่าอ่านคอลัมน์ใหม่นี้ได้** (แค่ไม่รู้จัก)
   ⇒ rollback กลับ image ก่อนหน้าได้ ต่างจาก migration ที่ "ลบคอลัมน์"

🔄 **คู่กันกับ `migrations/023_app_settings.py`** — 023 คือ "ประตูที่ปิดได้", 024 คือ "กุญแจของฉุกเฉิน"
   ทั้งคู่ไม่มีผลใด ๆ จนกว่าจะมีคนกดตั้งค่า/enabled หรือประกาศ urgent จริง
   ⇒ deploy เปล่า ๆ = ระบบทำงานเหมือนก่อน merge ทุกประการ

📌 mirror ลง `core/init_db.py` แล้ว (ใน CREATE TABLE `notifications` ที่มีอยู่)
"""

VERSION = "024_announcement_bypass"
DESCRIPTION = "notifications.bypass_quiet_hours: ธงยกเว้น quiet hours สำหรับประกาศฉุกเฉิน (E2)"


async def upgrade(conn) -> None:
    # `IF NOT EXISTS` = idempotent (migration ทุกตัวต้องรันซ้ำได้ — ดู core/migrations.py)
    await conn.execute("""
        ALTER TABLE notifications
            ADD COLUMN IF NOT EXISTS bypass_quiet_hours BOOLEAN NOT NULL DEFAULT FALSE;
    """)

    # ⚠️ **ไม่มี index โดยเจตนา** — คอลัมน์นี้ถูกอ่านเป็น *ส่วนหนึ่งของแถวที่ JOIN ได้อยู่แล้ว*
    #    (push worker โหลด payload ทั้งแถวอยู่แล้ว) ⇒ ไม่มีคิวรีใดกรองด้วยคอลัมน์นี้เดี่ยว ๆ
    #    ⇒ index จะเป็นภาระตอน INSERT (ทุก notification) โดยไม่ได้อะไรกลับมา
