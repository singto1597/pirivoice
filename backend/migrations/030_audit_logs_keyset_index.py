"""030 — index ให้หน้าดู audit_logs เรียงแบบ keyset (`created_at DESC, id DESC`)

**ปัญหาที่แก้:** หน้า "บันทึกการใช้งาน" เลิกใช้ OFFSET แล้ว (ตารางนี้มีแถวใหม่แทรกหัว
ตลอดเวลา ⇒ offset ทำให้หน้าถัดไปเห็นซ้ำ/ข้าม) เปลี่ยนมาใช้ keyset:

    WHERE (a.created_at, a.id) < ($1::timestamptz, $2::uuid)
    ORDER BY a.created_at DESC, a.id DESC
    LIMIT 31

**ทำไมต้องเป็น composite ตามลำดับนั้นเป๊ะ:** index ที่มีอยู่มีแค่ `(created_at)`
เดี่ยว ๆ ซึ่งใช้ตัดแถวซ้ำไม่ได้ (แถวที่ `created_at` เท่ากันหลายแถวจะถูกตัดทั้งกลุ่ม
หรือไม่ถูกตัดเลย) · composite `(created_at DESC, id DESC)` ทำให้ Postgres เดิน index
จากบนลงล่างตามลำดับที่ query ต้องการ แล้วหยุดเมื่อครบ LIMIT ⇒ ไม่ต้อง sort ทั้งตาราง

**ทำไม `DESC` ทั้งคู่:** query เรียงใหม่→เก่า ⇒ ใช้ index ได้ตรง ๆ แบบ index-only walk
(สร้างเป็น ASC ก็ใช้ได้ผ่าน backward scan แต่ DESC ทำให้ตรงเจตนาและอ่านง่ายกว่า)

**เทียบกับ init_db:** mirror ไว้ใน `core/init_db.py` (บล็อก index ของ audit_logs)
⇒ **ห้ามแก้ที่เดียว** ไม่งั้น fresh DB กับ DB จริงได้ index คนละแบบ
"""
VERSION = "030_audit_logs_keyset_index"
DESCRIPTION = "audit_logs: composite index (created_at DESC, id DESC) สำหรับ keyset pagination"

import asyncpg


async def upgrade(conn: asyncpg.Connection) -> None:
    await conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_audit_logs_created_id
            ON audit_logs (created_at DESC, id DESC)
    """)
