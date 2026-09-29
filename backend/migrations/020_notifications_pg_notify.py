"""020 — `pg_notify` ตอนมี notification ใหม่ ⇒ badge ในแอพอัปเดตทันที (SSE)

ภูมิหลัง: ตั้งแต่รอบ 1 การแจ้งเตือนในแอพอัปเดตด้วย **poll ทุก 30 วินาที**
(`stores/notifications.ts` `POLL_INTERVAL_MS`) ⇒ คนที่เปิดแอพอยู่จะเห็น badge ช้าได้ถึง 30 วิ
และรู้สึกว่า "ต้องรีเฟรช" · A3 (push) แก้คนละปัญหากัน — A3 คือ "ปิดแอพอยู่ก็ยังเด้ง"
ส่วนไฟล์นี้คือ "เปิดแอพอยู่ แล้ว badge ต้องขยับทันที"

⭐ **ทำไม `pg_notify` ไม่ใช่ publish จาก Python (หรือ Redis)**
   `notify()` / `notify_bulk()` / `notify_fanout()` **รับ `conn` จาก caller และไม่เปิด
   transaction เอง** (สัญญาที่ `notification_service.py` เขียนไว้ชัด) ⇒ ถ้าไป publish
   ในนั้น จะ publish **ก่อน** commit ⇒ ผู้ใช้อาจเห็น badge เพิ่มของแจ้งเตือนที่
   **ถูก rollback ไปแล้ว** (badge เพิ่มแล้วไม่ลด — อาการที่หาสาเหตุยากมาก)
   `pg_notify()` มีคุณสมบัติตรงนี้ **ฟรี**: คิว NOTIFY ถูกส่ง **ตอน COMMIT เท่านั้น**
   ⇒ rollback = ไม่มี event · และไม่ต้องแก้ `notification_service.py` แม้แต่บรรทัดเดียว

   เทียบกับ Redis pub/sub: ต้องไปเติม publish เองทุก call site (13 จุด) และจัดการ
   "publish หลัง commit" เอง — ได้ semantics เดียวกันด้วยงานมากกว่าหลายเท่า
   (`redis` มีอยู่แล้วใน requirements แต่ไม่ได้ทำให้เรื่องนี้ถูกต้องขึ้น)

⚠️ **payload มีแค่ `user_id` — ห้ามใส่ title/body/group_type**
   1. **ความปลอดภัย** — payload วิ่งผ่านทุกโปรเซสที่ LISTEN ⇒ ถ้าเผลอส่งเนื้อหา
      ข้อความ แล้วมีบั๊กตรงการกรองผู้รับ = **ข้อความรั่วข้ามผู้ใช้**
      เลข `user_id` ตัวเดียวรั่วได้อย่างมากคือ "มีคนได้แจ้งเตือน" ซึ่งไม่มีประโยชน์กับใคร
   2. **ขนาด** — `pg_notify` จำกัด 8,000 byte · `notify_fanout` ยิงถึง 1,000 คน
      = 1,000 ข้อความต่อครั้ง ⇒ payload ต้องเล็กที่สุดเท่าที่จะเป็นไปได้
   ⇒ ฝั่ง client **ไม่ใช้ payload เป็นข้อมูล** แต่ใช้เป็น "สัญญาณให้ไปถามยอดจริง"
      (source of truth เดียว = `notifications` ใน DB ผ่าน `get_unread_counts`)

⚠️ **trigger ยิงเฉพาะ INSERT ไม่ใช่ UPDATE**
   `mark_read` เป็น UPDATE ⇒ ถ้าดักด้วยจะได้ multi-tab sync ของ "อ่านแล้ว" ด้วย
   (แท็บ A กดอ่าน → แท็บ B badge ลดทันที) · **ยังไม่ทำรอบนี้โดยเจตนา:**
   `mark_read(all_=True)` แตะได้หลายร้อยแถวในคำสั่งเดียว ⇒ จะได้ `pg_notify`
   หลายร้อยข้อความต่อการกดหนึ่งครั้ง เพื่อของที่ poll 30 วิครอบคลุมอยู่แล้ว
   ⇒ ถ้าจะทำวันหลัง ควรใช้ **statement-level trigger** (`FOR EACH STATEMENT` +
   `REFERENCING NEW TABLE`) ยิงครั้งเดียวต่อคำสั่ง ไม่ใช่ต่อแถว — บันทึกไว้เป็นทางเลือก

📌 **ทำไมไม่ต่อกับ `push_outbox_enqueue()` (migration 018)**
   ฟังก์ชันนั้นถูก **migration 019 แก้ทับ** (`CREATE OR REPLACE`) เพื่อเพิ่มประตู
   "ต้องมีอุปกรณ์ก่อน" · ถ้าไฟล์นี้ไป `CREATE OR REPLACE` ฟังก์ชันเดียวกัน
   แล้ว **อันที่ merge ทีหลังจะลบงานของอันแรกทิ้งเงียบ ๆ** (ไม่มี error — ผลคือ
   push หรือ badge อย่างใดอย่างหนึ่งหยุดทำงานโดยไม่มีร่องรอย)
   ⇒ แยก **ฟังก์ชัน + trigger ของตัวเอง** ⇒ สอง PR เรียงลำดับแบบไหนก็ถูกต้อง
   (Postgres ยอมให้มีหลาย trigger บนตารางเดียวได้ — ยิงเรียงตามชื่อ)

📌 **เบี่ยงจากธรรมเนียมโปรเจคโดยเจตนา (แบบเดียวกับ 018):** ไฟล์นี้มีแต่
   function + trigger **ไม่มีตาราง/index** ⇒ **ไม่ต้อง mirror ลง `core/init_db.py`**
   (ถ้า mirror จะมี `CREATE OR REPLACE FUNCTION` สองที่ที่ drift กันได้)
   แทนที่ด้วยคอมเมนต์ชี้ที่ใน `init_db.py` ข้างตาราง `notifications`
"""
VERSION = "020_notifications_pg_notify"
DESCRIPTION = "trigger AFTER INSERT ON notifications → pg_notify('piri_notifications') สำหรับ SSE"


async def upgrade(conn) -> None:
    # ============================================================
    # Function — ยิงสัญญาณตอน notification ใหม่ถูก insert
    # ============================================================
    # ⚠️ `PERFORM` ไม่ใช่ `SELECT` — ใน plpgsql ถ้าเขียน `SELECT pg_notify(...)` เฉย ๆ
    #    จะ error "query has no destination for result data" เพราะ pg_notify คืน void
    await conn.execute("""
        CREATE OR REPLACE FUNCTION notifications_stream_notify() RETURNS trigger AS $$
        BEGIN
            PERFORM pg_notify(
                'piri_notifications',
                json_build_object('user_id', NEW.user_id)::text
            );
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
    """)

    # ============================================================
    # Trigger
    # ============================================================
    # ⚠️ `DROP TRIGGER IF EXISTS` ก่อน `CREATE TRIGGER` จำเป็นจริง ๆ —
    #    `CREATE TRIGGER` ไม่มี `IF NOT EXISTS` ⇒ ถ้าลืม migrate รอบที่สองจะพัง
    #    ด้วย "trigger already exists" (เส้นทางนี้เกิดจริง: `DROP TABLE` แล้ว
    #    `upgrade()` ซ้ำ ในเทสต์ migration)
    await conn.execute("DROP TRIGGER IF EXISTS trg_notifications_stream ON notifications;")
    await conn.execute("""
        CREATE TRIGGER trg_notifications_stream
            AFTER INSERT ON notifications
            FOR EACH ROW EXECUTE FUNCTION notifications_stream_notify();
    """)
