"""019 — ประตูที่ 1 ของ outbox: ผู้รับต้องมีอุปกรณ์จริงก่อนจึงเข้าคิว

ภูมิหลัง (วัดจาก staging จริง 28 ก.ย. 2026):
    `push_outbox` มี **3,239 แถว** แต่เป็นของผู้ใช้ที่มีอุปกรณ์จริงเพียง **9 แถว (0.28%)**
    อีก **3,230 แถว** เป็นของผู้ที่ไม่มี `push_subscriptions` เลย ⇒ งานที่ทำไม่ได้แต่กินโควตา
    `PUSH_BATCH_SIZE=100` ทุกรอบ และเพราะคิวเป็น FIFO ตาม `id` งานจริงจึงถูกดันไปท้ายคิว
    ⇒ ถึงหัวคิวก็นาน ~40 นาที ⇒ ถูกทิ้งด้วย `PUSH_MAX_AGE_MINUTES=15`

    อาการที่ผู้ใช้เห็น: **"แจ้งเตือนแค่ครั้งแรก แล้วไม่แจ้งอีก"** (ครั้งแรกที่มาถึงคือแถวที่เข้า
    คิวก่อนที่ fanout จะท่วม) และ **"แจ้งเตือนช้าไปหน่อย"**

⭐ **ทำไมกรองที่ trigger ไม่ใช่ที่ `_claim`**
   ทางเลือกคือกรองตอน claim (`NOT EXISTS` ในคิวรี claim) แต่แถวขยะจะ **ค้างในตารางตลอดไป**
   เพราะไม่มีใคร mark processed ให้ ⇒ index `idx_push_outbox_pending` บวมด้วยของที่ไม่มีวันจบ
   ⇒ กรองที่ประตูทางเข้า: ของที่ทำไม่ได้ **ไม่เข้าเลย** · 3,230 แถวกลายเป็น 0 ตั้งแต่แรก

⭐ **ทำไมไม่ backfill ให้คนที่เพิ่งเปิด push**
   notification เก่าที่ค้างอยู่ **ไม่ควร** ถูกส่งย้อนหลังตอนผู้ใช้เพิ่งลงทะเบียนอุปกรณ์ —
   จะกลายเป็น push storm ทันทีที่คนเปิดใช้งาน (คืออาการที่กำลังแก้อยู่)
   · in-app ยังเห็นครบอยู่แล้ว (ตาราง `notifications` ไม่ได้แตะ) ⇒ push เป็นช่องทาง
   "เดี๋ยวนี้" ไม่ใช่ช่องทางย้อนหลัง

⚠️ **ยังไม่ลบแถวขยะที่มีอยู่เดิมในไฟล์นี้โดยเจตนา** — migration นี้เป็น DDL ล้วน
   (rollback-safe · ไม่มี data mutation ที่ทำให้ผลลัพธ์ไม่คาดคิด) ส่วนแถวเดิมจะถูกเก็บกวาด
   เองโดย drain loop ในรอบถัดไปในไม่กี่วินาที (`_load_payloads` คืน `subs = []` ⇒ `skipped`)

⚠️ **ไม่แตะ pref gate ของ A2** — `notify*` ทั้งสามตัวกรองคนที่ปิดกลุ่มไว้ก่อน insert แล้ว
   ประตูนี้เป็นคนละชั้น (มีปลายทางไหม) ไม่ใช่ (ยอมรับกลุ่มนี้ไหม) ⇒ **ห้ามรวมสองชั้นเข้าด้วยกัน**

📌 **ที่อยู่ของฟังก์ชัน:** `push_outbox_enqueue()` ถูกนิยามที่ `migrations/018` ที่เดียว
   (ไม่ mirror ลง `init_db.py` — ดูเหตุผลใน 018) ⇒ ที่นี่ใช้ `CREATE OR REPLACE FUNCTION`
   ทับตัวเดิม ⇒ **idempotent โดยธรรมชาติ** รันซ้ำกี่ครั้งก็ได้ผลเดิม
   และไม่ต้อง `DROP TRIGGER` เพราะตัว trigger ไม่เปลี่ยน — เปลี่ยนแค่ตัวฟังก์ชันที่มันเรียก
"""
VERSION = "019_push_outbox_requires_device"
DESCRIPTION = "outbox: ไม่ enqueue ให้ผู้ใช้ที่ไม่มีอุปกรณ์ (ประตูที่ 1 — กันคิวท่วมด้วยงานที่ทำไม่ได้)"


async def upgrade(conn) -> None:
    await conn.execute("""
        CREATE OR REPLACE FUNCTION push_outbox_enqueue() RETURNS trigger AS $$
        DECLARE
            has_device boolean;
        BEGIN
            -- ★ ประตูที่ 1: ผู้รับต้องมีอุปกรณ์ที่ลงทะเบียนไว้จริง (migration 019)
            --    ใช้ index `idx_push_subscriptions_user` ⇒ เป็น index lookup ไม่ใช่ seq scan
            SELECT EXISTS (
                SELECT 1 FROM push_subscriptions s WHERE s.user_id = NEW.user_id
            ) INTO has_device;

            IF NOT has_device THEN
                -- ไม่มีปลายทาง = ไม่เข้าคิว · in-app ยังได้ปกติ (แถวใน `notifications` ถูก insert แล้ว)
                RETURN NEW;
            END IF;

            -- ⬇️ ประตูถัดไปในอนาคตต่อที่นี่ (เช่น A8 quiet hours · PUSH_MUTED_TYPES)
            --    เงื่อนไขที่เหมาะกับที่นี่คือ "ตัดสินจากข้อมูลใน DB ก่อนเข้าคิว" เท่านั้น
            --    ถ้าเป็นการตัดสินใจตอนส่ง (เช่น อ่าน env/config) ให้ไปอยู่ใน push_service

            INSERT INTO push_outbox (notification_id, user_id)
            VALUES (NEW.id, NEW.user_id)
            ON CONFLICT DO NOTHING;   -- กัน trigger ซ้ำ/ยิงสองรอบ — อาการ "push ซ้ำ" หาสาเหตุยากมาก
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
