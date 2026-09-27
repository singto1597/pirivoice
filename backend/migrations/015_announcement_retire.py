"""
Migration: 015 — ประกาศ: คอลัมน์ `retired_at` (สถานะ "ปลดระวาง")
================================================================================
ภูมิหลัง: ตาราง `announcements` มีแค่ 2 สถานะคือ *ใช้งานอยู่* กับ *ถูกลบ*
(`deleted_at`) ⇒ ปุ่มเดียวที่ผู้ใช้เห็นคือ "ลบ" ซึ่งสื่อว่าเป็นการลบถาวร
ทำให้สภานักเรียนไม่กล้าเอาประกาศที่หมดอายุออก เพราะกลัวว่าประวัติจะหาย

(ก) `retired_at` — เพิ่มสถานะที่ 3 "ปลดระวางแล้ว"
    ⭐ **ไม่ใส่ FK และไม่ใส่ CHECK constraint โดยเจตนา**
       - ไม่มี FK: ไม่มีอะไรให้อ้างถึง (เป็น timestamp เปล่า) ต่างจาก created_by/updated_by
         ที่งด FK เพราะเหตุผลเรื่องหลักฐานย้อนหลัง (ดู migration 014)
       - ไม่มี CHECK บังคับ exclusivity กับ `deleted_at` **เพราะต้องการให้สองคอลัมน์
         เป็นอิสระต่อกัน** ⇒ "ปลดระวางแล้วเผลอลบ → กู้คืน" จะกลับมาเป็น *ปลดระวางแล้ว*
         ตามเดิม ไม่ใช่กลับไปโชว์บนหน้าเว็บทั้งที่ตั้งใจเอาออกไปแล้ว
         ถ้าบังคับ exclusive แล้วให้ `delete` ล้าง `retired_at` ทิ้ง = ข้อมูลหายเงียบ ๆ
         (ดู `docs/skills.md` หัวข้อ restore-ไม่สูญเสียสถานะ)

    ความหมายของแต่ละค่า:
      retired_at IS NULL     AND deleted_at IS NULL  → ใช้งานอยู่   (แสดงบน Landing/Home)
      retired_at IS NOT NULL AND deleted_at IS NULL  → ปลดระวางแล้ว (ไม่แสดง แต่เก็บไว้)
      deleted_at IS NOT NULL                         → ถูกลบ        (ไม่แสดง)

    ⚠️ **`_STATUS_CONDITIONS` ใน `services/announcement_service.py` คือจุดเดียวที่นิยาม
       คำว่าสถานะ** — คิวรีที่กรองเองโดยไม่ผ่าน dict นั้น (เช่น
       `services/public_service.get_announcements`) ต้องเติม `retired_at IS NULL` เองด้วย
       ไม่งั้นประกาศที่ปลดระวางจะยังโชว์บนหน้า Landing ทั้งที่เทสต์อื่นเขียวหมด

⭐ **ทำไมไม่เพิ่ม index:** ตารางนี้มีหลักหน่วยถึงหลักสิบแถว การสร้าง index ไม่ช่วยอะไร
   และทำให้ write ช้าลงเปล่า ๆ ; ถ้าวันหนึ่งประกาศโตถึงหลักพันค่อยกลับมาพิจารณา
"""
VERSION = "015_announcement_retire"
DESCRIPTION = "announcements: retired_at (ปลดระวาง — เอาออกจากหน้าเว็บแต่เก็บเป็นประวัติ)"


async def upgrade(conn) -> None:
    # --- (ก) คอลัมน์ปลดระวาง (idempotent — migration ทุกตัวต้องรันซ้ำได้) -----------
    await conn.execute(
        "ALTER TABLE announcements "
        "ADD COLUMN IF NOT EXISTS retired_at TIMESTAMP WITH TIME ZONE"
    )
