"""018 — Web Push: `push_subscriptions` + `push_outbox` + trigger

ภูมิหลัง: จนถึงรอบ 1 การแจ้งเตือนเป็นการ insert แถวลง `notifications` แล้วรอให้
client poll ทุก 30 วินาที (`stores/notifications.ts`) ⇒ ปิดแอพอยู่ = ไม่มีทางรู้
A3 ทำให้ "มีเรื่องใหม่ → เด้งถึงมือถือแม้ปิดแอพ" ผ่าน Web Push (RFC 8030/8291/8292)

⭐ **ทำไมใช้ trigger ไม่แก้ `notify*` ทั้งสามตัว**
   `notify()` / `notify_bulk()` / `notify_fanout()` มี **call site 13 จุด** กระจายใน
   `issue_service` / `board_service` / `board_moderation_service` การไปแก้ทีละจุด
   (หรือให้ทุกตัวคืน recipient list แล้ว insert outbox เอง) แปลว่าแตะโค้ดที่ใช้งานจริง
   อยู่ 16 ที่ เพื่อของที่ "ควรจะอัตโนมัติ"
   ⇒ trigger `AFTER INSERT ON notifications` ได้ผลเหมือนกันโดย
   **ไม่ต้องแก้ `notification_service.py` แม้แต่บรรทัดเดียว และไม่ต้องแก้ call site เลย**
   และคิวรีใหม่ในอนาคตที่ยิง notification เองก็ได้ push อัตโนมัติด้วย
   (migration 016 เตือนปัญหานี้ไว้เองว่า *"ถ้ามีคิวรีใหม่ที่ยิง notification เอง
   โดยไม่ผ่าน notify*…"*)

⭐ **pref gate ไม่ต้องทำซ้ำที่นี่** — `notify*` ทั้งสามตัวกรองคนที่ปิดกลุ่มไว้ *ก่อน*
   insert อยู่แล้ว (`_pref_allows` / `_filter_allowed` / `NOT EXISTS` ใน fanout)
   ⇒ ทุกแถวที่มาถึง trigger ผ่าน gate มาแล้ว = outbox ผ่านด้วย
   **ห้ามใส่ gate ซ้ำใน trigger** — จะกลายเป็นสองที่ที่นิยามคำว่า "ปิด" แล้วเพี้ยนกันวันหลัง

⚠️ **outbox เก็บแค่ `notification_id` ไม่ denormalize ข้อความ**
   `notifications` ถูก `mark_read` เท่านั้น — **ไม่มีโค้ดไหนลบมันเลย** ⇒ JOIN ไม่มีทางพลาด
   · ข้อความมี source of truth เดียว · แถว outbox เหลือ ~40 byte ⇒ fanout 1,000 คนก็ยังเบา

⚠️ **trigger ยิงเฉพาะแถวใหม่** — notification ที่มีอยู่ก่อน migrate ไม่ถูก push (ถูกต้อง
   แล้ว อย่าไป backfill: ผู้ใช้จะได้ push ย้อนหลังเป็นพรวด)

📌 **เบี่ยงจากธรรมเนียมโปรเจคโดยเจตนา:** ปกติ DDL ทุกตัวต้อง mirror ลง `core/init_db.py`
   ด้วย แต่ **trigger + function อยู่ในไฟล์นี้ที่เดียว** — ถ้า mirror จะต้องมี
   `CREATE OR REPLACE FUNCTION` สองที่ซึ่ง drift กันได้ง่าย (และ `init_db` ไม่ได้อยู่ใน
   transaction เดียวกับ migration) ⇒ แทนที่จะ copy ไปใส่ **คอมเมนต์ชี้ที่** ข้างตาราง
   `notifications` ใน `init_db.py`
   ส่วน **2 ตาราง + 3 index mirror ลง `init_db.py` ตามธรรมเนียม** (นั่นคือ DDL ที่อ่านง่าย
   และไม่มีตรรกะ)

⚠️ **`DROP TRIGGER IF EXISTS` ก่อน `CREATE TRIGGER` จำเป็นจริง ๆ**
   `CREATE TRIGGER` ไม่มี `IF NOT EXISTS` และ `CREATE OR REPLACE TRIGGER` มีเฉพาะ
   PostgreSQL 14+ (โปรเจคใช้ 16 แต่ก็ยังเลือกแบบ DROP+CREATE เพื่อความชัด)
   ถ้าลืม ⇒ migrate รอบที่สองพังด้วย "trigger already exists"
   (เส้นทางนี้เกิดจริง: `DROP TABLE` แล้ว `upgrade()` ซ้ำ ในเทสต์ migration)
"""
VERSION = "018_push_notifications"
DESCRIPTION = "push_subscriptions + push_outbox + trigger AFTER INSERT ON notifications"


async def upgrade(conn) -> None:
    # ============================================================
    # (ก) ปลายทาง push ของแต่ละอุปกรณ์
    # ============================================================
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS push_subscriptions (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            endpoint TEXT NOT NULL,
            p256dh TEXT NOT NULL,
            auth TEXT NOT NULL,
            user_agent TEXT,
            failure_count INTEGER NOT NULL DEFAULT 0,
            last_success_at TIMESTAMP WITH TIME ZONE,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT chk_push_subscriptions_endpoint_len
                CHECK (length(endpoint) BETWEEN 8 AND 1000)
        );
    """)

    # ⭐ unique บน `endpoint` เดี่ยว ๆ ไม่ใช่ (user_id, endpoint) โดยเจตนา:
    #    endpoint = "เบราว์เซอร์เครื่องนี้" ไม่ใช่ "ผู้ใช้คนนี้" — เครื่องเรียนเครื่องเดียว
    #    ถูกใช้หลายคน (logout → login คนใหม่ แล้ว subscribe ใหม่จากเครื่องเดิม)
    #    ถ้า unique เป็นคู่ (user_id, endpoint) จะเหลือแถวของผู้ใช้คนเก่าค้างอยู่
    #    ⇒ push ไปหาคนเก่า = **รั่วข้ามผู้ใช้** (ดูเทสต์ S3)
    #    การใช้ endpoint เดี่ยว + `ON CONFLICT (endpoint) DO UPDATE SET user_id = EXCLUDED.user_id`
    #    ทำให้ "เครื่องนี้เป็นของใคร" ถูกยึดใหม่ทุกครั้งที่ล็อกอิน — สัญญาณสดชนะความจำ
    await conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_push_subscriptions_endpoint
            ON push_subscriptions (endpoint);
    """)
    await conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_push_subscriptions_user
            ON push_subscriptions (user_id);
    """)

    # ============================================================
    # (ข) Transactional outbox
    # ============================================================
    # ทำไมต้องมี outbox ทั้งที่ trigger ก็ยิง push ตรง ๆ ได้:
    #   1. งาน push ต้องออก **นอก** transaction ของ caller (ห้ามถือ connection ระหว่าง
    #      ยิง HTTP ไป Google/Apple ซึ่งใช้เวลาเป็นร้อย ms) — trigger ทำแบบนั้นไม่ได้
    #   2. ต้อง retry ได้เมื่อปลายทางล่ม โดยไม่ต้องมีตาราง state ในหน่วยความจำ
    #      (worker restart = หายหมด)
    #   3. ต้องมีเพดาน: `PUSH_MAX_AGE_MINUTES` กัน push storm หลัง worker ล่มเป็นชั่วโมง
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS push_outbox (
            id BIGSERIAL PRIMARY KEY,
            notification_id INTEGER NOT NULL REFERENCES notifications(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            attempts SMALLINT NOT NULL DEFAULT 0,
            next_attempt_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            processing_at TIMESTAMP WITH TIME ZONE,
            processed_at TIMESTAMP WITH TIME ZONE,
            last_error TEXT,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # กัน trigger ยิงซ้ำแล้วได้ 2 แถวสำหรับ (notification, user) เดียวกัน
    # ⚠️ `AFTER INSERT … FOR EACH ROW` ยิง row ละครั้งตามสัญญา แต่ถ้ามีคนเผลอเพิ่ม
    #    trigger ตัวที่สอง หรือ notification ถูก update แล้วมี trigger อื่น insert ซ้ำ
    #    อาการที่ได้คือ **push ซ้ำสองครั้ง** ซึ่งหาสาเหตุยากมาก ⇒ กันที่ schema ถูกกว่า
    await conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_push_outbox_notification_user
            ON push_outbox (notification_id, user_id);
    """)

    # partial index: key = `id` ล้วน (ไม่ใช่ `next_attempt_at`)
    # เพราะคิวรีจริงคือ `WHERE processed_at IS NULL ORDER BY id LIMIT n` — เรียงตามลำดับ
    # เข้าก่อน อายุ (คิวนี้มีของค้างไม่ถึงวินาทีในสภาวะปกติ) และ partial ทำให้ index เล็กลง
    # มากเมื่อของที่ processed แล้วสะสม (retention 7 วัน)
    await conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_push_outbox_pending
            ON push_outbox (id) WHERE processed_at IS NULL;
    """)

    # ============================================================
    # (ค) Trigger — หัวใจของ A3
    # ============================================================
    await conn.execute("""
        CREATE OR REPLACE FUNCTION push_outbox_enqueue() RETURNS trigger AS $$
        BEGIN
            INSERT INTO push_outbox (notification_id, user_id)
            VALUES (NEW.id, NEW.user_id)
            ON CONFLICT DO NOTHING;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    await conn.execute("DROP TRIGGER IF EXISTS trg_notifications_push_outbox ON notifications;")
    await conn.execute("""
        CREATE TRIGGER trg_notifications_push_outbox
            AFTER INSERT ON notifications
            FOR EACH ROW EXECUTE FUNCTION push_outbox_enqueue();
    """)
