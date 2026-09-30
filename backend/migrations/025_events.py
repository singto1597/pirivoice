"""
Migration: 025 — ระบบกิจกรรม (D1): ตาราง events + event_registrations + สิทธิ์ MANAGE_EVENTS
============================================================================================
ภูมิหลัง: D1 = "สภาจัดกิจกรรม เปิดรับสมัคร และมีคิวสำรองอัตโนมัติ"
สเปกต้นทางจัด D1·D2·D3·D4 เป็นชุดเดียวเพราะ **ใช้ตารางชุดเดียวกัน** ⇒ migration นี้
วางสคีมาให้ครบตั้งแต่ต้น เพื่อให้ D2 (QR check-in) และ D4 (หมวดกิจกรรม) ต่อยอดได้
โดยไม่ต้องออก migration ใหม่ถ้าไม่จำเป็น

(ก) `events` — ตัวกิจกรรม
    ⭐ `status` เป็น **สถานะการเผยแพร่** ไม่ใช่การลบ ⇒ แยกจาก `deleted_at` โดยเจตนา
       · draft      = สภาสร้างไว้แต่ยังไม่ประกาศ (นักเรียนมองไม่เห็น)
       · published  = เผยแพร่แล้ว (นักเรียนเห็น + เปิดรับสมัคร)
       · cancelled  = ยกเลิก (ยังเห็นอยู่ แต่อยู่คนละกลุ่มกับ "ฉบับร่าง")
       ⇒ **ต่างจาก announcements ที่ใช้ `retired_at`** — ที่นั่น "ปลดระวาง" เป็นมิติของ
         *เวลา* (ประกาศเก่า) ส่วนที่นี่เป็นมิติของ *การตัดสินใจ* (ยังไม่พร้อม / ยกเลิก)

    ⭐ `published_at` แยกคอลัมน์ ไม่ได้ใช้อ่าน `status` อย่างเดียว:
       ใช้ตอบ "ประกาศไปเมื่อไหร่" และเป็นหลักฐานย้อนหลังแม้ภายหลังจะ `cancelled`
       (ถ้าดูจาก `updated_at` จะเพี้ยนทันทีที่มีคนแก้ชื่อกิจกรรม)

    ⭐ `capacity` = NULL แปลว่า **ไม่จำกัดจำนวน** (ไม่ใช่ 0) — 0 มีความหมายว่า "ปิดรับ"
       ⇒ `CHECK (capacity IS NULL OR capacity > 0)` กัน 0 หลุดเข้ามาโดยไม่ตั้งใจ
       · D1 ไม่มีสถานะ "ปิดรับชั่วคราว" ⇒ ผู้จัดใช้ `cancelled` หรือแก้ capacity แทน

    ⭐ `created_by`/`updated_by` — **ไม่ใส่ FK โดยเจตนา** เหตุผลเดียวกับ migration 014:
       ตารางที่เก็บความจริงย้อนหลังห้าม FK แบบ ON DELETE action ใด ๆ เพราะ
       "ลบผู้ใช้ = หลักฐานหาย" (บทเรียน skills.md) ⇒ เก็บ INTEGER เปล่า + LEFT JOIN เอาตอนอ่าน

(ข) `event_registrations` — ใบสมัคร (รวมคิวสำรอง = D3 ซึ่งอยู่ในรอบเดียวกับ D1)
    ⭐ **unique (event_id, user_id) แบบไม่มี partial predicate** โดยเจตนา:
       การยกเลิก **ไม่ลบแถว** แต่พลิก `status = 'cancelled'` ⇒ สมัครใหม่ = UPDATE แถวเดิม
       กลับมา ⇒ ประวัติ "เคยสมัครแล้วยกเลิก" ไม่หาย และไม่มีแถวขยะงอกทุกครั้งที่กดไปมา
       · ผลที่ตามมา: `registered_at` ถูกเขียนใหม่ทุกครั้งที่สมัครใหม่ = **ต่อคิวใหม่ท้ายสุด**
         (สละสิทธิ์แล้วกลับมา = ต่อท้าย ซึ่งยุติธรรมและอธิบายง่าย)
       · ต่างจาก `piri_votes` ที่ unique เป็น partial (`WHERE deleted_at IS NULL`) เพราะ
         ที่นั่นโหวตซ้ำหลังลบเป็นอีกความหมายหนึ่ง

    ⭐ `checked_in` อยู่ใน CHECK ตั้งแต่ migration นี้แม้ D2 (QR) จะยังไม่ทำ:
       CHECK constraint ที่ลิสต์ค่าตายตัว **แก้ทีหลังต้องออก migration ใหม่**
       (บทเรียน E1/`board_type` ใน §18 ของแผน) ⇒ ใส่ค่าที่สเปกระบุไว้รอล่วงหน้า
       ต้นทุนคือศูนย์ และประหยัด migration หนึ่งใบในรอบหน้า

    ⚠️ **ไม่มี FK ไป `events` แบบ cascade?** — มี `ON DELETE CASCADE` แต่ในทางปฏิบัติ
       ไม่มีโค้ดไหน hard delete กิจกรรม (ใช้ soft delete) ⇒ CASCADE เป็นตาข่ายกัน
       แถวกำพร้าเฉพาะกรณีมีคนลบตรง ๆ ใน DB ซึ่งไม่ควรเกิดขึ้น

(ค) backfill สิทธิ์ `MANAGE_EVENTS`
    กลุ่ม = **ชุดเดียวกับ `MANAGE_SETTINGS`** (ผู้ใช้เลือก 29 ก.ย. 2026): สภาตั้งกิจกรรมได้เอง
    ไม่ต้องรอครู และไม่ต้องเพิ่มบทบาทใหม่
      · `council_president` · `teacher_council` · `admin` — ทั้งสาม `is_admin: true` อยู่แล้ว
        จึงผ่านได้แม้ไม่เติม ; เติมให้ข้อมูลตรงกับความจริงเพื่อให้ UI/introspection ที่อ่าน
        `permissions` ตรง ๆ แสดงถูก (แบบเดียวกับที่ migration 014 ทำกับสามตัวนี้)
    ⚠️ **ไม่รวม `council_member`** — ต่างจาก migration 014 ที่รวม เพราะที่นั่นเป็นสิทธิ์
       "ประกาศ" ส่วนที่นี่เป็นการจัดกิจกรรม ⇒ ยึดตามชุดของ `MANAGE_SETTINGS` ตรง ๆ
       (ถ้าอนาคตต้องการให้กรรมการสภาจัดกิจกรรมได้ → แก้ `roles.json` **และ** ออก migration
        backfill เพิ่ม เพราะ `students.permissions` เป็น snapshot ไม่มี sync ย้อนหลัง)

    ⚠️ `students.permissions` เป็น **snapshot** ที่เขียนเฉพาะตอนสร้าง/เปลี่ยนตำแหน่ง
       (`auth_service.register_user`, `import_service`, `student_service.update_student`,
        `seed_users`) — **ไม่มีกลไก sync จาก roles.json ย้อนหลังเลย**
       ⇒ แก้ `roles.json` เฉย ๆ ผู้ใช้เดิมจะไม่ได้สิทธิ์ **โดยไม่มี error ให้เห็น**
       ⇒ อาการที่จะเจอ: สภาเปิดเมนู "จัดการกิจกรรม" ไม่เห็น แล้วหาสาเหตุไม่ได้
"""
VERSION = "025_events"
DESCRIPTION = "กิจกรรม (D1): ตาราง events + event_registrations + index + backfill สิทธิ์ MANAGE_EVENTS"

# ตำแหน่งที่จะได้รับสิทธิ์จัดการกิจกรรม — ต้องตรงกับ backend/config/roles.json
#   = ชุดเดียวกับที่ถือ MANAGE_SETTINGS (ผู้ใช้เลือก "เหมือน MANAGE_SETTINGS")
_ROLES_WITH_EVENT_PERMISSION = (
    "council_president",
    "teacher_council",
    "admin",
)
_PERMISSION = "MANAGE_EVENTS"


async def upgrade(conn) -> None:
    # --- (ก) ตาราง events --------------------------------------------------------
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS events (
            id SERIAL PRIMARY KEY,
            title VARCHAR(200) NOT NULL,
            description TEXT,
            location VARCHAR(200),
            cover_image_url VARCHAR(500),
            event_date TIMESTAMP WITH TIME ZONE NOT NULL,
            registration_deadline TIMESTAMP WITH TIME ZONE,
            capacity INTEGER,
            status VARCHAR(20) NOT NULL DEFAULT 'draft',
            published_at TIMESTAMP WITH TIME ZONE,
            cancelled_at TIMESTAMP WITH TIME ZONE,
            created_by INTEGER,
            updated_by INTEGER,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            deleted_at TIMESTAMP WITH TIME ZONE,
            CONSTRAINT chk_events_status
                CHECK (status IN ('draft', 'published', 'cancelled')),
            CONSTRAINT chk_events_capacity
                CHECK (capacity IS NULL OR capacity > 0)
        );
        """
    )

    # --- (ข) ตาราง event_registrations -------------------------------------------
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS event_registrations (
            id SERIAL PRIMARY KEY,
            event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            status VARCHAR(20) NOT NULL DEFAULT 'registered',
            registered_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            cancelled_at TIMESTAMP WITH TIME ZONE,
            checked_in_at TIMESTAMP WITH TIME ZONE,
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT chk_event_registrations_status
                CHECK (status IN ('registered', 'waitlisted', 'cancelled', 'checked_in'))
        );
        """
    )

    # --- (ค) index ----------------------------------------------------------------
    # ⚠️ ตารางที่สร้างใน migration ก็ต้องสร้าง index ในนี้ด้วย — init_db.py สร้าง index
    #    ให้เฉพาะความสะดวกของ DB ใหม่ (mirror) ไม่ใช่แหล่งความจริง
    await conn.execute(
        """
        -- ลิสต์กิจกรรมที่นักเรียนเห็น: กรอง status + เรียงตามวันจัด
        CREATE INDEX IF NOT EXISTS idx_events_status_date
            ON events (status, event_date)
            WHERE deleted_at IS NULL;
        -- "กิจกรรมที่ฉันสร้าง" ของสภา
        CREATE INDEX IF NOT EXISTS idx_events_created_by
            ON events (created_by)
            WHERE deleted_at IS NULL;
        -- ⭐ หนึ่งคนสมัครกิจกรรมหนึ่งครั้งได้ใบเดียว ⇒ เป็นทั้งด่านกันซ้ำและ index ของ
        --    "ฉันสมัครกิจกรรมนี้หรือยัง" (คิวรีที่วิ่งทุกครั้งที่เปิดหน้ารายละเอียด)
        CREATE UNIQUE INDEX IF NOT EXISTS uq_event_registrations_event_user
            ON event_registrations (event_id, user_id);
        -- ⭐ (event_id, status, registered_at) เรียงคอลัมน์ตามที่ใช้จริง:
        --    · นับที่นั่ง  = WHERE event_id=? AND status IN (...)      → คอลัมน์ที่ 2
        --    · หัวคิวสำรอง = WHERE event_id=? AND status='waitlisted' ORDER BY registered_at
        --    ⇒ index เดียวตอบได้ทั้งสองคำถาม ไม่ต้องมี index ที่สอง
        CREATE INDEX IF NOT EXISTS idx_event_registrations_event_status
            ON event_registrations (event_id, status, registered_at);
        -- "กิจกรรมของฉัน" — ล่าสุดก่อน
        CREATE INDEX IF NOT EXISTS idx_event_registrations_user
            ON event_registrations (user_id, registered_at DESC);
        """
    )

    # --- (ง) backfill สิทธิ์ --------------------------------------------------------
    #   COALESCE(permissions, '[]') ทุกจุด เพื่อให้แถวที่ permissions เป็น NULL
    #   ยังได้รับสิทธิ์ (ไม่งั้น || กับ NULL = NULL แล้ว UPDATE เงียบ ๆ ไม่เกิดอะไร)
    await conn.execute(
        """
        UPDATE students
        SET permissions = COALESCE(permissions, '[]'::jsonb) || $1::jsonb,
            updated_at = NOW()
        WHERE class_role = ANY($2::text[])
          AND deleted_at IS NULL
          AND NOT (COALESCE(permissions, '[]'::jsonb) @> $1::jsonb)
        """,
        f'["{_PERMISSION}"]',
        list(_ROLES_WITH_EVENT_PERMISSION),
    )
