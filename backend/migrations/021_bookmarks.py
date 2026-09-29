"""021 — `bookmarks` (บันทึกไว้อ่านทีหลัง) + 2 index ที่ C3/C1 ต้องการ

ภูมิหลัง: C2 ให้ผู้ใช้เก็บเรื่อง/บอร์ดไว้ในชุดส่วนตัว แล้วเปิดดูภายหลังได้
พร้อมกับ C1 (กิจกรรมของฉัน) ที่รวมทุกอย่างที่เคยทำไว้ในหน้าเดียว

⭐ **ทำไมไม่ใส่ FK ไป `issues`/`piri_boards`**
   ตารางนี้เป็น **polymorphic** (`entity_type` + `entity_id` ชี้ได้หลายตาราง)
   FK ของ Postgres ผูกกับตารางเดียว ⇒ ถ้าจะบังคับด้วย FK ต้องแยกเป็น 2 คอลัมน์
   nullable (`issue_id`, `board_id`) ซึ่งจะทำให้ทุกคิวรีต้องเขียน `COALESCE` และ
   เพิ่มชนิดใหม่ (D1 `event`) ต้อง `ALTER TABLE` ทุกครั้ง
   ⇒ **ความถูกต้องย้ายไปอยู่ที่ service** (`bookmark_service.create_bookmark`
   ตรวจว่า entity มีจริงและไม่ถูกลบ ก่อน insert) — มีเทสต์ B3/B4 คุมอยู่

⚠️ **ไม่มี CHECK บน `entity_type` โดยเจตนา** — ตามเหตุผลเดียวกับที่
   `migrations/016_notification_preferences.py` เขียนเตือนไว้เอง: ค่าชุดนี้ **จะโต**
   (D1 จะเพิ่ม `'event'`) ถ้าใส่ CHECK ทุกครั้งที่เพิ่มชนิดต้องออก migration ใหม่
   ⇒ validate ที่ชั้น Pydantic (`Literal`) แทน ซึ่งตอบ 422 ให้เองและไม่ต้อง migrate
   (ต่างจาก `piri_boards.board_type` ที่ CHECK ไว้ก่อนแล้ว ⇒ E1 ต้องไป `DROP CONSTRAINT`)

⭐ **2 index ท้ายไฟล์ไม่เกี่ยวกับ bookmarks เลย แต่มาพร้อมกันโดยเจตนา**
   `piri_votes(user_id)` และ `issue_comments(user_id)` **ยังไม่มี index**
   (ตรวจ `init_db.py` L614-643: มี `idx_piri_board_comments_user` แต่สองตัวนี้ไม่มี)
   ⇒ ทั้ง C3 (`votes_cast`, `issue_comments_posted` — มีอยู่แล้วบน main) และ
   C1 (ที่เพิ่งเขียน) ต้อง **seq scan** ตอนเปิดหน้าโปรไฟล์/กิจกรรม
   ⇒ ใส่ 2 บรรทัดนี้ปิดทั้งสองงานพร้อมกัน ต้นทุนคือ index เล็ก ๆ บนคอลัมน์เดียว

📌 ตรงกับธรรมเนียมโปรเจค: ตาราง + index ถูก **mirror ลง `core/init_db.py`**
   (ที่นั่นไม่มีตรรกะ อ่านง่าย) — ต่างจาก function/trigger ของ 018/020 ที่อยู่ที่เดียว
"""
VERSION = "021_bookmarks"
DESCRIPTION = "bookmarks (บันทึกไว้อ่านทีหลัง) + index user_id ของ piri_votes/issue_comments"


async def upgrade(conn) -> None:
    # ============================================================
    # (ก) ชุดที่บันทึกไว้ — ส่วนตัวของเจ้าของบัญชีเท่านั้น
    # ============================================================
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS bookmarks (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            entity_type VARCHAR(20) NOT NULL,
            entity_id INTEGER NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # ⭐ unique (user_id, entity_type, entity_id) = "อยู่ในชุดแล้วหรือยัง"
    #    ต่างจาก `piri_votes` ที่ unique เป็น **partial** (`WHERE deleted_at IS NULL`)
    #    เพราะโหวตที่ถูกลบต้องกลับมาโหวตใหม่ได้
    #    ⇒ ตารางนี้ **ไม่มีการลบแบบ soft** — เลิกบันทึกคือ DELETE จริง
    #      (ไม่ใช่ข้อมูลที่ต้องเก็บประวัติ + ไม่มีใครอ้างถึง)
    #      ⇒ unique ธรรมดาไม่ต้อง partial
    await conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_bookmarks_user_entity
            ON bookmarks (user_id, entity_type, entity_id);
    """)
    # เรียงตามเวลาที่บันทึกล่าสุดก่อน — ตรงกับ ORDER BY ของ list_bookmarks
    await conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_bookmarks_user_created
            ON bookmarks (user_id, created_at DESC);
    """)

    # ============================================================
    # (ข) Index ที่ขาดอยู่ของตารางเดิม — C1/C3 ใช้ทั้งคู่
    # ============================================================
    await conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_piri_votes_user ON piri_votes(user_id);
    """)
    await conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_issue_comments_user ON issue_comments(user_id);
    """)
