"""
Migration: 013 — audit_logs ครบทุกคอลัมน์ (ห้ามเว้นว่าง)
=========================================================
ปัญหา: audit_logs ปล่อยคอลัมน์เป็น NULL ได้ ⇒ ข้อมูลที่ตรวจย้อนหลังไม่ครบ
       (พบจริงบน production 18,019 แถว: execution_time_ms ว่าง 100%,
        room_id ว่าง 94.7%, entity_id ว่าง 42%, ip/user_agent ว่าง 3.2%)
แก้ 2 ชั้น:
  1. ชั้นโค้ด — `core/logger.py` เติมทุกคอลัมน์จาก request context / DB / ค่า sentinel
  2. ชั้นสคีมา (ไฟล์นี้) — บังคับ NOT NULL + DEFAULT ทุกคอลัมน์ ⇒ ต่อให้อนาคตมี
     call site ใหม่ที่ลืมส่งค่ามา DB ก็ไม่ยอมให้เว้นว่าง

ค่า sentinel (อ่านออกว่า "ไม่รู้" ไม่ใช่ปล่อยว่าง):
  - '-'  = ไม่ทราบค่า/ไม่มีค่า            (คอลัมน์ข้อความ)
  - {}   = ไม่มีข้อมูล old/new             (คอลัมน์ JSONB — action ประเภทอ่าน)
  - -1   = ไม่ระบุห้อง/ไม่รู้จักตัวตน      (room_id / user_id)
  - 0    = วัด execution_time_ms ไม่ได้    (ไม่มี request context)

⭐ ถอด FK ของ room_id/user_id ออก: audit_logs เป็นบันทึกประวัติ ต้องอยู่ครบตลอดไป
   - เดิม room_id FK เป็น ON DELETE CASCADE → "ลบห้อง 1 ห้อง = ประวัติหายทั้งห้อง"
   - เดิม user_id FK เป็น ON DELETE SET NULL → "ลบผู้ใช้ = ไม่รู้ว่าใครทำ"
   ทั้งสองแบบทำให้ audit ตรวจย้อนหลังไม่ได้ ซึ่งขัดกับวัตถุประสงค์ของตาราง
   ⇒ เก็บเป็นเลขเฉย ๆ (join เอาเองเมื่อแถวยังอยู่) ; -1 = ไม่ระบุ

หมายเหตุการ backfill ข้อมูลเก่า:
  - room_id: กู้คืนจากตาราง students ได้จริง (ห้องที่ผู้กระทำสังกัด) — ข้อมูลจริง ไม่ใช่ sentinel
  - คอลัมน์อื่นที่ว่างอยู่: เติม sentinel เพราะค่าย้อนหลังกู้คืนไม่ได้แล้ว
    (เช่น execution_time_ms ของ request ที่จบไปแล้ว — วัดใหม่ไม่ได้)
"""
VERSION = "013_audit_logs_completeness"
DESCRIPTION = "audit_logs: ถอด FK + backfill + NOT NULL/DEFAULT ทุกคอลัมน์ (ห้ามเว้นว่าง)"

# 🧩 ค่า sentinel
UNSPECIFIED_ID = -1

# คอลัมน์ข้อความที่ต้องไม่ว่าง (ชื่อคอลัมน์มาจากโค้ดเท่านั้น — ไม่มี user input)
_TEXT_COLUMNS = [
    "trace_id", "actor_identifier", "client_source", "service_name", "action",
    "entity_type", "entity_id", "error_detail", "endpoint_or_command",
    "ip_address", "user_agent",
]


async def upgrade(conn) -> None:
    # --- 0) ถอด FK ของ room_id/user_id ก่อน (ดูเหตุผลใน docstring) -------------------
    #   ⚠️ ต้องถอดก่อนเติม sentinel -1 เพราะ FK เดิมยังบังคับให้ room_id ต้องมีแถวจริง
    await conn.execute("ALTER TABLE audit_logs DROP CONSTRAINT IF EXISTS audit_logs_room_id_fkey")
    await conn.execute("ALTER TABLE audit_logs DROP CONSTRAINT IF EXISTS audit_logs_user_id_fkey")

    # --- 1) กู้คืน room_id ของแถวเก่าจากห้องที่ผู้กระทำสังกัด (ข้อมูลจริง) ------------
    await conn.execute(
        """
        UPDATE audit_logs a
        SET room_id = s.room_id
        FROM (
            SELECT DISTINCT ON (user_id) user_id, room_id
            FROM students
            WHERE deleted_at IS NULL AND room_id IS NOT NULL
            ORDER BY user_id, (status = 'active') DESC, id
        ) s
        WHERE a.user_id = s.user_id AND a.room_id IS NULL
        """
    )

    # --- 2) เติมค่าที่เหลือ (กู้คืนไม่ได้ → sentinel) --------------------------------
    await conn.execute("UPDATE audit_logs SET room_id = $1 WHERE room_id IS NULL", UNSPECIFIED_ID)
    await conn.execute("UPDATE audit_logs SET user_id = $1 WHERE user_id IS NULL", UNSPECIFIED_ID)

    # ⚠️ เติมทีละคอลัมน์ด้วย COALESCE(NULLIF(x,''), '-') — ห้ามเขียนเป็น
    #    `SET a='-', b='-', ... WHERE a IS NULL OR a='' OR b IS NULL OR ...` เด็ดขาด
    #    เพราะแถวที่ "คอลัมน์หนึ่งว่าง" จะถูก WHERE จับ แล้วทับค่าจริงของคอลัมน์อื่นเป็น '-' หมด
    #    (bug นี้ถูกจับได้ด้วย tests/test_audit_logs_migration.py — actor_identifier หายเรียบ)
    set_clause = ", ".join(f"{c} = COALESCE(NULLIF({c}, ''), '-')" for c in _TEXT_COLUMNS)
    await conn.execute(f"UPDATE audit_logs SET {set_clause}")

    await conn.execute("UPDATE audit_logs SET status = 'success' WHERE status IS NULL OR status = ''")
    await conn.execute("UPDATE audit_logs SET created_at = NOW() WHERE created_at IS NULL")
    await conn.execute("UPDATE audit_logs SET execution_time_ms = 0 WHERE execution_time_ms IS NULL")
    await conn.execute(
        "UPDATE audit_logs SET old_values = '{}'::jsonb WHERE old_values IS NULL OR old_values = 'null'::jsonb"
    )
    await conn.execute(
        "UPDATE audit_logs SET new_values = '{}'::jsonb WHERE new_values IS NULL OR new_values = 'null'::jsonb"
    )

    # --- 3) บังคับ NOT NULL + DEFAULT ทุกคอลัมน์ -------------------------------------
    defaults = {
        "room_id": str(UNSPECIFIED_ID),
        "user_id": str(UNSPECIFIED_ID),
        "trace_id": "'-'",
        "actor_identifier": "'-'",
        "client_source": "'-'",
        "service_name": "'-'",
        "action": "'-'",
        "entity_type": "'-'",
        "entity_id": "'-'",
        "status": "'success'",
        "error_detail": "'-'",
        "endpoint_or_command": "'-'",
        "ip_address": "'-'",
        "user_agent": "'-'",
        "execution_time_ms": "0",
        "created_at": "CURRENT_TIMESTAMP",
        "old_values": "'{}'::jsonb",
        "new_values": "'{}'::jsonb",
    }
    for column, default in defaults.items():
        await conn.execute(f"ALTER TABLE audit_logs ALTER COLUMN {column} SET DEFAULT {default}")
        await conn.execute(f"ALTER TABLE audit_logs ALTER COLUMN {column} SET NOT NULL")
