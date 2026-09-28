"""
Migration: 016 — ตาราง `notification_preferences` (ตั้งค่าการแจ้งเตือนรายกลุ่ม)
================================================================================
ภูมิหลัง: `notifications` เป็นการ insert แถวลง DB ล้วน ๆ — ผู้ใช้ **ปิด noise ไม่ได้เลย**
ทุกครั้งที่มีเรื่องใหม่/คอมเมนต์ใหม่/โหวตใหม่ ระบบยิงแจ้งเตือนเข้ากลุ่มทั้ง 4
(`issue_mine` / `issue_received` / `board` / `report`) โดยไม่มีทางเลือก
ผลคือคนที่อยู่หลายกลุ่ม (เช่นสภา) ถูกสแปมจนเลิกอ่าน badge

(ก) `notification_preferences` — เก็บ "ผู้ใช้คนนี้ปิดกลุ่มไหนไว้"
    ⭐ **"ไม่มีแถว" = เปิด** — เป็นค่าตั้งต้นของทุกคนโดยไม่ต้อง backfill
       ⇒ ต่างจาก migration 014 (`announcement_management`) ที่ต้องเติม permission
       ให้ผู้ใช้เดิม เพราะที่นี่ "ไม่มีแถว" ให้ความหมายว่า "เปิด" อยู่แล้ว

    ⭐ **ชื่อคอลัมน์คือ `enabled` ไม่ใช่ `push_enabled`** โดยเจตนา
       ค่านี้ gate **ทั้ง in-app และ push** (ตามที่ผู้ใช้ออกแบบไว้)
       ถ้าเรียก `push_enabled` จะเป็นการโกหก เพราะตอนนี้ยังไม่มี push ในระบบเลย
       → เมื่อทำ A3 (push) / A8 (quiet hours) ให้ **เพิ่มคอลัมน์ใหม่** ควบคู่ไป
         (เช่น `push_enabled`) **ห้าม rename `enabled`** เพราะจะทำให้ความหมายของ
         แถวเดิมเปลี่ยนไปทั้งตาราง

    ⚠️ **`group_type` ไม่มี CHECK constraint โดยเจตนา**
       ตามแบบตารางพี่น้อง `notifications` (init_db.py) ที่ก็ไม่มี CHECK และใช้
       regex ที่ชั้น Pydantic/router แทน (`GROUP_TYPE_PATTERN`)
       เหตุผล: `GROUP_TYPES` จะโตขึ้นเรื่อย ๆ (D1 จะเพิ่ม `"event"`) — ถ้าใส่ CHECK
       ทุกครั้งที่เพิ่มกลุ่มต้องออก migration ใหม่เพื่อแก้ constraint ทั้งที่ไม่มีข้อมูลเปลี่ยน

    ⚠️ **`_pref_allows()` / `_filter_allowed()` ใน `services/notification_service.py`
       คือจุดเดียวที่นิยามคำว่า "ปิด"** — ถ้ามีคิวรีใหม่ที่ยิง notification เองโดยไม่ผ่าน
       `notify*` ทั้งสามตัว ต้องเติม `NOT EXISTS (… enabled = FALSE)` เองด้วย
       ไม่งั้นคนที่ปิดไว้จะยังได้รับแจ้งเตือนทั้งที่เทสต์อื่นเขียวหมด
       (บทเรียนเดียวกับ `retired_at` ใน migration 015)

⭐ **ทำไมไม่เพิ่ม index อื่นนอกจาก unique:** ตารางนี้มี ≤ 4 แถวต่อผู้ใช้ และถูกอ่าน
   แบบ point lookup (`user_id = $1 AND group_type = $2`) อยู่แล้ว ⇒ unique index
   ตัวเดียวพอ ทำ index เพิ่มมีแต่ทำให้ write ช้าลงเปล่า ๆ
"""
VERSION = "016_notification_preferences"
DESCRIPTION = "notification_preferences: ปิด/เปิดการแจ้งเตือนรายกลุ่ม (ไม่มีแถว = เปิด)"


async def upgrade(conn) -> None:
    # --- (ก) ตารางค่าตั้งค่าการแจ้งเตือน (idempotent — migration ทุกตัวต้องรันซ้ำได้) ---
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS notification_preferences (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            group_type VARCHAR(30) NOT NULL,
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # --- (ข) unique (user_id, group_type) — จำเป็นต่อ `ON CONFLICT … DO UPDATE` -------
    # ถ้าไม่มี index นี้ upsert ใน `update_preferences()` จะ raise
    # "there is no unique or exclusion constraint matching the ON CONFLICT specification"
    await conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_notification_prefs_user_group
            ON notification_preferences (user_id, group_type);
    """)
