"""022 — เปิด `board_type = 'suggestion'` (E1 Quick Suggestion)

ภูมิหลัง: E1 ให้ผู้ใช้ทั่วไป **เสนอไอเดียได้เองโดยไม่ต้องผ่านสภาอนุมัติ** — คนละทางกับ
board `talk`/`vote` ที่เกิดจาก `issue_service.approve_to_public()` เท่านั้น (มีด่านสภา)
⇒ ต้องมีชนิดที่สามใน `piri_boards.board_type`

⭐ **ทำไมต้องออก migration แทนที่จะแก้ `init_db.py` เฉย ๆ**
   `init_db.py` L233 มี `CONSTRAINT chk_piri_boards_type CHECK (board_type IN ('talk','vote'))`
   ซึ่ง **ถูกสร้างไปแล้วบน DB จริงทั้ง staging และ production** ⇒ แก้ DDL ในไฟล์ไม่ทำให้
   constraint บนเครื่องที่รันอยู่เปลี่ยนตาม (ต่างจาก `notification_preferences`/`bookmarks`
   ที่ **จงใจไม่มี CHECK** ⇒ เพิ่มค่าใหม่ไม่ต้อง migrate — ดูหมายเหตุใน migration 016/021)
   · บทเรียนเดียวกับ §18 ของแผน: "ตารางที่มี CHECK ไว้ก่อน = เพิ่มค่าใหม่ต้อง DROP CONSTRAINT"

⚠️ **ลำดับ 3 คำสั่งห้ามสลับ**
   1. `DROP CONSTRAINT IF EXISTS` — ★ ต้องมี `IF EXISTS` เพราะ `ADD CONSTRAINT` **ไม่**
      idempotent ⇒ รันซ้ำต้องไม่พัง (ด่าน `test_init_db_upgrade` + `test_quick_suggestion::M1`
      รัน `upgrade()` สองครั้ง)
   2. `ALTER COLUMN ... TYPE VARCHAR(20)` — ขยายก่อน **ไม่ใช่หลัง** เพราะ `ADD CONSTRAINT`
      ต้องประเมินค่าใหม่กับทุกแถว ถ้าคอลัมน์ยังแคบจะไม่มีปัญหาในทางทฤษฎี (ทุกแถวเดิมสั้นกว่า 10)
      แต่การเรียงแบบนี้ทำให้อ่านลำดับเหตุผลได้ตรง: "เปิดที่ว่าง → ใส่ของ → ล็อกด้วยด่าน"
   3. `ADD CONSTRAINT` — ประเมินกับทุกแถวเดิม (ทั้งหมดเป็น `talk`/`vote` ⇒ ผ่าน)

⭐ **ทำไม `VARCHAR(20)` ไม่ใช่ `VARCHAR(10)`**
   `'suggestion'` ยาว **10 ตัวอักษรพอดี** กับเพดานเดิม ⇒ ไม่มีที่ว่างเหลือเลยสำหรับชนิดที่ 4
   (D1/D4 จะเพิ่มพวกกิจกรรม) ⇒ ขยายเป็น 20 ตั้งแต่รอบนี้
   · **การขยาย varchar ใน Postgres เป็น metadata-only** (ไม่ rewrite ตาราง, ไม่ lock ยาว)
     เมื่อชนิดใหม่กว้างกว่าเดิมและไม่มี index บนคอลัมน์นี้ ⇒ **ฟรี**
   · และเป็นคำขอตรงของผู้ใช้: *"รองรับการขยายในอนาคต"*

📌 **mirror ลง `core/init_db.py` แล้ว** (ทั้ง `VARCHAR(20)` และ CHECK ใหม่) — DB ใหม่ที่สร้าง
   จาก `init_db` จะได้สคีมาเดียวกันโดยไม่ต้องพึ่ง migration นี้ · ทั้งสองทางบรรจบที่สคีมาเดียวกัน
   (init_db สร้างตาราง → migration 022 รันทับ → ผลลัพธ์เท่ากับ init_db รุ่นใหม่ตรง ๆ)

⚠️ **ไม่แตะข้อมูลเดิมเลย** — ไม่มี `UPDATE` ในไฟล์นี้ · `status` เริ่มต้นคือ `'active'`
   ซึ่งเป็นค่า default ของคอลัมน์อยู่แล้ว (E1 ตั้งใจให้ **ขึ้นทันที** ตามที่ผู้ใช้เลือก
   "ขึ้นทันที + ซ่อนย้อนหลังได้" ⇒ ไม่ต้องมีสถานะ 'pending' ในสคีมา และไม่ต้องขยาย
   `chk_piri_boards_status`) ⇒ **rollback กลับ image เก่าได้** (image เก่าไม่รู้จัก
   `'suggestion'` แต่ก็ไม่เคยสร้างแถวชนิดนั้น — แถวที่ผู้ใช้สร้างไว้จะไม่ถูกแตะ)
"""
VERSION = "022_board_type_suggestion"
DESCRIPTION = "piri_boards.board_type: เปิดค่า 'suggestion' (E1) + ขยายเป็น VARCHAR(20)"


async def upgrade(conn) -> None:
    # ============================================================
    # 1) ถอดด่านเดิมออก — ต้องมาก่อน ไม่งั้น "insert ค่าใหม่แล้วค่อยล็อก" ทำไม่ได้
    #    และเพราะ `ADD CONSTRAINT` รันซ้ำไม่ได้ ⇒ `IF EXISTS` คือสิ่งที่ทำให้ไฟล์นี้ idempotent
    # ============================================================
    await conn.execute("""
        ALTER TABLE piri_boards
            DROP CONSTRAINT IF EXISTS chk_piri_boards_type;
    """)

    # ============================================================
    # 2) ขยายที่ว่าง — metadata-only, ไม่ rewrite ตาราง
    # ============================================================
    await conn.execute("""
        ALTER TABLE piri_boards
            ALTER COLUMN board_type TYPE VARCHAR(20);
    """)

    # ============================================================
    # 3) ล็อกด้วยด่านใหม่ — 3 ค่า
    #    ⚠️ `board_type` ยังเป็น NOT NULL DEFAULT 'talk' ตามเดิม (ไม่แตะ)
    #       ⇒ ถ้า E1 ลืมส่ง board_type แถวจะกลายเป็น 'talk' เงียบ ๆ
    #         ซึ่งเป็นเหตุผลที่ router E1 ส่งค่าคงที่เป็น literal จาก service ไม่พึ่ง default
    # ============================================================
    await conn.execute("""
        ALTER TABLE piri_boards
            ADD CONSTRAINT chk_piri_boards_type
            CHECK (board_type IN ('talk', 'vote', 'suggestion'));
    """)
