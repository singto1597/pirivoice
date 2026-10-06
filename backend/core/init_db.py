import asyncpg
import asyncio
import logging
import sys
import os

# 🛠️ ตั้งค่า Path เพื่อให้รันสคริปต์นี้ตรงๆ ได้ผ่าน CLI (สำหรับเรียกใช้ core.config)
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from core.config import settings
except ImportError:
    sys.path.append(os.path.join(os.getcwd(), 'pirivoice-backend'))
    from core.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("API_INIT_DB")

async def init_db(pool: asyncpg.Pool):
    """
    สร้าง Table ทั้งหมดในระบบ PIRIvoice หากยังไม่มี (Schema Setup)
    ฟังก์ชันนี้ถูกเรียกใช้ทั้งจาก main.py (Startup) และ run_setup (Manual CLI)
    """
    try:
        async with pool.acquire() as conn:
            async with conn.transaction():

                # --- 1. ตาราง Users (ศูนย์รวมตัวตน) ---
                await conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    username VARCHAR(100) UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    full_name TEXT,
                    avatar_url TEXT,
                    phone_number TEXT,
                    email TEXT UNIQUE,
                    must_change_password BOOLEAN NOT NULL DEFAULT FALSE,  -- บัญชี seed: บังคับเปลี่ยนรหัสครั้งแรก
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    deleted_at TIMESTAMP DEFAULT NULL
                );
                """)

                # --- 2. ตารางตารางเรียน/ห้องเรียน (rooms) ---
                # room_code เช่น ม.4/1, ม.5/2 ; level เช่น 'ม.4' สำหรับระดับชั้น
                await conn.execute("""
                CREATE TABLE IF NOT EXISTS rooms (
                    id SERIAL PRIMARY KEY,
                    room_code VARCHAR(10) UNIQUE,
                    room_name TEXT NOT NULL,
                    level TEXT,                -- ระดับชั้น เช่น ม.1 ... ม.6
                    room_number INTEGER,       -- ห้องที่ เช่น 1, 2, 3
                    owner_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    deleted_at TIMESTAMP DEFAULT NULL
                );
                """)

                # --- 2.5 academic_years: ปีการศึกษา (migration 027) ---
                #   ⚠️ **ต้องสร้างก่อน `students`** เพราะ students อ้าง FK มาที่ตารางนี้
                #   - "ปี" แยกจาก "ภาคเรียน" (8.7): ภาคเรียนกรองสถิติ · ปีเก็บประวัติสมาชิก
                #   - 1 แถวใน students = สมาชิกของคนหนึ่ง "ในปีหนึ่ง" ⇒ เลื่อนชั้น = สร้างแถวใหม่
                #     ไม่ใช่ UPDATE ทับ ⇒ ประวัติไม่หาย
                #   - ⚠️ **ไม่มี seed ปีที่นี่** โดยเจตนา — migration 027 เป็นเจ้าของการสร้าง
                #     "ปีตั้งต้น" (คำนวณ พ.ศ. จากวันที่จริง + เงื่อนไข พ.ค.) ⇒ มีนิยามเดียว
                #   - ⚠️ `students.academic_year_id` ที่นี่เป็น **nullable ไม่มี default**
                #     ต่างจากสถานะสุดท้ายโดยเจตนา: `NOT NULL DEFAULT <id>` ต้องใช้ค่า literal
                #     ที่รู้ตอน runtime ⇒ migration 027 เป็นคนใส่ให้หลัง backfill
                await conn.execute("""
                CREATE TABLE IF NOT EXISTS academic_years (
                    id SERIAL PRIMARY KEY,
                    year_be INTEGER NOT NULL,          -- พ.ศ. เช่น 2569 (ไม่ใช่ ค.ศ.)
                    name VARCHAR(50) NOT NULL,         -- "ปีการศึกษา 2569"
                    start_date DATE,
                    end_date DATE,
                    is_current BOOLEAN NOT NULL DEFAULT FALSE,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    deleted_at TIMESTAMP WITH TIME ZONE,
                    CONSTRAINT chk_academic_years_range
                        CHECK (end_date IS NULL OR start_date IS NULL OR end_date >= start_date)
                );
                """)

                # --- 3. ตารางนักศึกษา/สมาชิก (students) — มีตำแหน่งในห้องเรียน ---
                # ตำแหน่ง (class_role) เช่น 'class_president', 'vice_academic', ... 'student', 'teacher', 'teacher_council', 'admin'
                # ระดับ (level) ที่ตำแหน่งทำงาน เช่น 'room' (ห้อง) / 'level' (ประธานระดับ) / 'council' (สภา)
                # staff_level: เฉพาะ ครูทั่วไป (teacher) — ระดับชั้นที่รับผิดชอบ เช่น 'ม.4' (เห็น/จัดการได้แค่ระดับนี้)
                await conn.execute("""
                CREATE TABLE IF NOT EXISTS students (
                    id SERIAL PRIMARY KEY,
                    room_id INTEGER REFERENCES rooms(id) ON DELETE CASCADE,
                    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    student_id VARCHAR(10),          -- รหัสนักเรียน/รหัสบุคลากร (เลขประจำตัว)
                    student_no INTEGER,              -- เลขที่ในห้อง (ครู/แอดมิน ไม่มี → NULL)
                    prefix TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    nickname TEXT,
                    class_role TEXT DEFAULT 'student',  -- ตำแหน่ง (แมปกับ config/roles.json)
                    staff_level TEXT,                -- ระดับชั้นที่ครูทั่วไปรับผิดชอบ เช่น 'ม.4'
                    is_admin BOOLEAN DEFAULT FALSE,
                    permissions JSONB DEFAULT '[]'::jsonb,
                    responsibilities JSONB DEFAULT '[]'::jsonb,  -- หน้าที่รับผิดชอบ (ตรงกับ issues.category) — สภา/ผู้ช่วยหัวหน้าระดับ
                    status TEXT DEFAULT 'active',
                    -- 🌟 ปีการศึกษาของสมาชิกแถวนี้ (migration 027) — 1 แถว = 1 คน ใน 1 ปี
                    --   ⚠️ ที่นี่เป็น nullable ไม่มี default — สถานะสุดท้ายเป็น
                    --      `NOT NULL DEFAULT <id ของปีปัจจุบัน>` ซึ่งเป็น **ค่า literal ที่รู้ตอน runtime**
                    --      ⇒ migration 027 เป็นคนใส่ให้หลัง backfill แถวเดิมเข้าปีปัจจุบัน
                    academic_year_id INTEGER REFERENCES academic_years(id) ON DELETE RESTRICT,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    deleted_at TIMESTAMP DEFAULT NULL
                );
                """)

                # --- 4. ตารางปัญหา/ความคิดเห็น (issues) — หัวใจหลักของระบบ ---
                # main_category: หมวดหลัก — 'suggestion' เสนอความคิดเห็น / 'wellbeing' สุขภาวะทางกายและใจ / 'report' แจ้งเหตุ
                # category: หมวดย่อยในหมวดหลัก — แมปกับ config/categories.json
                #   suggestion → academic / reception / activity / discipline / democracy
                #   wellbeing  → physical_health / mental_health
                #   report     → complaint / grievance
                # current_level: ตอนนี้เรื่องอยู่ที่ระดับไหน (room / level / council)
                # status: 'pending' (ยังไม่มีใครรับ) / 'in_progress' / 'resolved' / 'escalated' / 'cancelled' / 'rejected'
                await conn.execute("""
                CREATE TABLE IF NOT EXISTS issues (
                    id SERIAL PRIMARY KEY,
                    room_id INTEGER REFERENCES rooms(id) ON DELETE CASCADE,
                    main_category TEXT NOT NULL DEFAULT 'suggestion',  -- หมวดหลัก (suggestion / wellbeing / report)
                    category TEXT NOT NULL,              -- หมวดย่อย (ตาม config/categories.json)
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    image_url TEXT,
                    reporter_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    reporter_room_id INTEGER REFERENCES rooms(id) ON DELETE SET NULL,
                    reporter_name TEXT,
                    current_level TEXT DEFAULT 'room',   -- ระดับปัจจุบัน: room / level / council
                    current_assignee_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    current_assignee_role TEXT,          -- บทบาทผู้รับปัจจุบัน (class_president, vice_academic, ...)
                    status TEXT DEFAULT 'pending',       -- pending / in_progress / resolved / escalated / cancelled / rejected
                    priority TEXT DEFAULT 'normal',      -- low / normal / high / urgent
                    is_anonymous BOOLEAN DEFAULT FALSE,
                    requested_destination VARCHAR(20) NOT NULL DEFAULT 'normal',  -- ปลายทางที่ผู้แจ้งขอ: normal / vote / talk (PIRI Boards)
                    published_board_id INTEGER,          -- board สาธารณะที่สภาอนุมัติแล้ว (ชี้ piri_boards.id — ตั้งโดย approve_to_public)
                    resolved_at TIMESTAMP WITH TIME ZONE,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    deleted_at TIMESTAMP DEFAULT NULL
                );
                """)

                # --- 5. Escalation history (ประวัติการส่งต่อระหว่างระดับ) ---
                await conn.execute("""
                CREATE TABLE IF NOT EXISTS issue_escalations (
                    id SERIAL PRIMARY KEY,
                    issue_id INTEGER REFERENCES issues(id) ON DELETE CASCADE,
                    from_level TEXT NOT NULL,          -- ระดับเดิม
                    to_level TEXT NOT NULL,            -- ระดับใหม่
                    from_assignee_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    to_assignee_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    reason TEXT,                       -- เหตุผลที่ส่งต่อ
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
                """)

                # --- 5.5 ตาราง status history (ติดตามประวัติสถานะ) ---
                await conn.execute("""
                CREATE TABLE IF NOT EXISTS issue_status_history (
                    id SERIAL PRIMARY KEY,
                    issue_id INTEGER REFERENCES issues(id) ON DELETE CASCADE,
                    status TEXT NOT NULL,
                    changed_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    note TEXT,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
                """)

                # --- 6. ขั้นตอนการดำเนินงาน (steps) — ผู้รับเพิ่มขั้นตอนได้ว่าถึงไหนแล้ว ---
                await conn.execute("""
                CREATE TABLE IF NOT EXISTS issue_steps (
                    id SERIAL PRIMARY KEY,
                    issue_id INTEGER REFERENCES issues(id) ON DELETE CASCADE,
                    step_title TEXT NOT NULL,
                    step_detail TEXT,
                    step_order INTEGER NOT NULL DEFAULT 0,
                    is_completed BOOLEAN DEFAULT FALSE,
                    completed_at TIMESTAMP WITH TIME ZONE,
                    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
                """)

                # --- 7. Countdown (นับถอยหลังงาน) — ผู้รับตั้งเวลาที่จะใช้แก้ปัญหา ---
                # deadline = time ที่รับงาน + estimated_days
                await conn.execute("""
                CREATE TABLE IF NOT EXISTS issue_countdowns (
                    id SERIAL PRIMARY KEY,
                    issue_id INTEGER REFERENCES issues(id) ON DELETE CASCADE,
                    assignee_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    estimated_days INTEGER NOT NULL,   -- ใช้เวลากี่วัน
                    started_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    deadline TIMESTAMP WITH TIME ZONE NOT NULL,
                    is_overdue BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
                """)

                # --- 7.5 ตารางคอมเมนต์ในเรื่อง (issue_comments) — แสดงความคิดเห็นแบบ YouTube ---
                # user_id + commenter_name/commenter_room เป็น snapshot (แบบ reporter_name)
                # → ผู้ใช้ถูกลบแล้วคอมเมนต์ยังอยู่ (ON DELETE SET NULL)
                # updated_at: NULL จนกว่าจะแก้ครั้งแรก ; deleted_at: soft delete
                await conn.execute("""
                CREATE TABLE IF NOT EXISTS issue_comments (
                    id SERIAL PRIMARY KEY,
                    issue_id INTEGER NOT NULL REFERENCES issues(id) ON DELETE CASCADE,
                    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    commenter_name TEXT,
                    commenter_room TEXT,
                    body TEXT NOT NULL,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE,
                    deleted_at TIMESTAMP
                );
                """)

                # --- 7.6 ตาราง PIRI Boards (ระบบสาธารณะ: PIRI Talk + PIRI Vote) ---
                # แยกงานสาธารณะออกจากระบบ issue ส่วนตัว: ต้นเรื่องมาจาก issue ที่ผู้แจ้ง
                # ขอปลายทาง 'vote'/'talk' แล้วสภาอนุมัติ (approve_to_public — Phase 2)
                # ทุกตารางมี created_at / updated_at / deleted_at TIMESTAMPTZ (soft delete บังคับ)
                # --------------------------------------------------------------------
                # piri_boards: โพสต์สาธารณะ
                #   - source_issue_id → issues(id): ย้อนกลับไปเรื่องต้นทาง (issue ถูกลบ → ตัด link, board ยังอยู่)
                #   - board_type: 'talk' (โพสต์+คอมเมนต์) / 'vote' (โหวต)
                #                 / 'suggestion' (E1 — ผู้ใช้เสนอไอเดียเอง ไม่ผ่านด่านสภา)
                #   - author_id: ผู้สร้างต้นเรื่อง (reporter ของ issue) — กันให้เห็นว่าใครเป็นเจ้าของเรื่อง
                #   - status: 'active' / 'closed' (ปิดประเด็น) / 'hidden' (ซ่อนโดย admin)
                #   - tags: JSONB array ของแท็ก (asyncpg คืนเป็น string → ต้อง json.loads ก่อนใช้)
                await conn.execute("""
                CREATE TABLE IF NOT EXISTS piri_boards (
                    id SERIAL PRIMARY KEY,
                    source_issue_id INTEGER REFERENCES issues(id) ON DELETE SET NULL,
                    -- ⚠️ VARCHAR(20) ไม่ใช่ (10): 'suggestion' ยาว 10 พอดีเพดานเดิม ⇒ ไม่มีที่ว่างเลย
                    --    (migration 022 ขยายให้ DB เดิม — ขยาย varchar = metadata-only ไม่ rewrite)
                    board_type VARCHAR(20) NOT NULL DEFAULT 'talk',
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    cover_image_url TEXT,
                    author_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    is_anonymous BOOLEAN NOT NULL DEFAULT FALSE,
                    approved_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    approved_at TIMESTAMP WITH TIME ZONE,
                    view_count INTEGER NOT NULL DEFAULT 0,
                    comment_count INTEGER NOT NULL DEFAULT 0,
                    share_count INTEGER NOT NULL DEFAULT 0,
                    status VARCHAR(20) NOT NULL DEFAULT 'active',
                    allow_comments BOOLEAN NOT NULL DEFAULT TRUE,
                    tags JSONB NOT NULL DEFAULT '[]'::jsonb,
                    closed_at TIMESTAMP WITH TIME ZONE,
                    closed_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    close_reason TEXT,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    deleted_at TIMESTAMP WITH TIME ZONE,
                    CONSTRAINT chk_piri_boards_type CHECK (board_type IN ('talk', 'vote', 'suggestion')),
                    CONSTRAINT chk_piri_boards_status CHECK (status IN ('active', 'closed', 'hidden'))
                );
                """)

                # piri_board_comments: คอมเมนต์ใน board (PIRI Talk) — แบบ threaded
                #   - parent_comment_id: self-referencing FK → reply ต่อคอมเมนต์ (NULL = คอมเมนต์หลัก)
                #   - edit_history: JSONB array ของ {body, edited_at} snapshot (ตอนแก้ไข)
                #   - ip_address / user_agent: เก็บผ่าน request context (ความปลอดภัย/ตรวจสอบ)
                #   - is_hidden_by_admin: ซ่อนคอมเมนต์ไม่เหมาะสม (ยัง soft delete ได้ด้วย deleted_at)
                await conn.execute("""
                CREATE TABLE IF NOT EXISTS piri_board_comments (
                    id SERIAL PRIMARY KEY,
                    board_id INTEGER NOT NULL REFERENCES piri_boards(id) ON DELETE CASCADE,
                    parent_comment_id INTEGER REFERENCES piri_board_comments(id) ON DELETE CASCADE,
                    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    body TEXT NOT NULL,
                    image_url TEXT,
                    is_edited BOOLEAN NOT NULL DEFAULT FALSE,
                    edit_history JSONB NOT NULL DEFAULT '[]'::jsonb,
                    ip_address VARCHAR(45),
                    user_agent TEXT,
                    is_hidden_by_admin BOOLEAN NOT NULL DEFAULT FALSE,
                    hidden_reason TEXT,
                    hidden_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    deleted_at TIMESTAMP WITH TIME ZONE
                );
                """)

                # piri_vote_choices: ตัวเลือกของ board แบบ vote
                await conn.execute("""
                CREATE TABLE IF NOT EXISTS piri_vote_choices (
                    id SERIAL PRIMARY KEY,
                    board_id INTEGER NOT NULL REFERENCES piri_boards(id) ON DELETE CASCADE,
                    choice_text TEXT NOT NULL,
                    description TEXT,
                    image_url TEXT,
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    vote_count INTEGER NOT NULL DEFAULT 0,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    deleted_at TIMESTAMP WITH TIME ZONE
                );
                """)

                # piri_votes: เสียงโหวตของผู้ใช้ — ผู้ใช้คนละ 1 เสียงต่อ board
                # UNIQUE(board_id, user_id) เป็น partial unique index (WHERE deleted_at IS NULL)
                # เพื่อให้ soft delete แล้วกลับมาโหวตใหม่ได้ (เหมือน uq_students_room_student_active)
                await conn.execute("""
                CREATE TABLE IF NOT EXISTS piri_votes (
                    id SERIAL PRIMARY KEY,
                    board_id INTEGER NOT NULL REFERENCES piri_boards(id) ON DELETE CASCADE,
                    choice_id INTEGER NOT NULL REFERENCES piri_vote_choices(id) ON DELETE CASCADE,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    ip_address VARCHAR(45),
                    user_agent TEXT,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    deleted_at TIMESTAMP WITH TIME ZONE
                );
                """)

                # piri_board_reactions: กด react (emoji) ต่อ board / คอมเมนต์
                #   - target_type: 'board' / 'comment' (polymorphic — เช็คค่าใน CHECK)
                #   - target_id: id ของ board/comment ปลายทาง (ไม่มี FK เพราะ polymorphic)
                #   - UNIQUE(target_type, target_id, user_id) partial — ผู้ใช้ react ละ 1 ครั้งต่อ target
                await conn.execute("""
                CREATE TABLE IF NOT EXISTS piri_board_reactions (
                    id SERIAL PRIMARY KEY,
                    target_type VARCHAR(10) NOT NULL,
                    target_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    reaction_type VARCHAR(20) NOT NULL,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    deleted_at TIMESTAMP WITH TIME ZONE,
                    CONSTRAINT chk_piri_reactions_target_type CHECK (target_type IN ('board', 'comment'))
                );
                """)

                # piri_board_reports: แจ้งความไม่เหมาะสมของคอมเมนต์ (Phase 5)
                #   - reason จำกัดหมวด (กลั่นแกล้ง/คำหยาบ/สแปม/เปิดเผยข้อมูล/อื่นๆ) — กันสแปมเหตุผลมั่ว
                #   - status: 'open' (รอสภา/แอดมินจัดการ) / 'resolved' (ซ่อนคอมเมนต์แล้ว) / 'dismissed' (ปัดตก)
                #   - UNIQUE(reporter_id, comment_id) partial → user แจ้งคอมเมนต์เดิมซ้ำไม่ได้ (กันสแปมรายงาน)
                await conn.execute("""
                CREATE TABLE IF NOT EXISTS piri_board_reports (
                    id SERIAL PRIMARY KEY,
                    board_id INTEGER NOT NULL REFERENCES piri_boards(id) ON DELETE CASCADE,
                    comment_id INTEGER NOT NULL REFERENCES piri_board_comments(id) ON DELETE CASCADE,
                    reporter_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    reason VARCHAR(30) NOT NULL,
                    detail TEXT,
                    status VARCHAR(20) NOT NULL DEFAULT 'open',
                    resolved_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    resolved_at TIMESTAMP WITH TIME ZONE,
                    resolution_note TEXT,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    deleted_at TIMESTAMP WITH TIME ZONE,
                    CONSTRAINT chk_piri_report_reason CHECK (reason IN ('bullying', 'profanity', 'spam', 'privacy', 'other')),
                    CONSTRAINT chk_piri_report_status CHECK (status IN ('open', 'resolved', 'dismissed'))
                );
                """)

                # piri_board_views: dedup "การเข้าชม" ต่อ user (Phase 6 — กัน F5 ปั่น view_count)
                #   PRIMARY KEY (board_id, user_id) → user 1 คน นับ view 1 ครั้งต่อ VIEW_DEDUP_WINDOW ต่อ board
                await conn.execute("""
                CREATE TABLE IF NOT EXISTS piri_board_views (
                    board_id INTEGER NOT NULL REFERENCES piri_boards(id) ON DELETE CASCADE,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    viewed_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (board_id, user_id)
                );
                """)

                # --- 8. audit_logs (โครงสร้างเหมือนโปรเจคเก่า) ---
                # 🔒 ทุกคอลัมน์ NOT NULL + DEFAULT — audit log ต้อง "ครบทุกช่อง" ห้ามเว้นว่าง
                #    - "-" = ไม่ทราบค่า/ไม่มีค่า (ดู UNKNOWN ใน core/logger.py)
                #    - {} = ไม่มีข้อมูล old/new (action ประเภทอ่าน)
                #    - -1 = ไม่ระบุห้อง/ไม่รู้จักตัวตน (sentinel — ไม่ต้องมีแถวจริงใน rooms/users)
                #    - execution_time_ms 0 = วัดไม่ได้ (ไม่มี request context)
                # ⚠️ room_id/user_id "ไม่มี FK" โดยเจตนา — audit_logs เป็นบันทึกประวัติที่ต้อง
                #    ตรวจย้อนหลังได้ตลอดไป: FK แบบ CASCADE เคยทำให้ "ลบห้อง → ประวัติหายทั้งห้อง"
                #    และแบบ SET NULL ทำให้ "ลบผู้ใช้ → ไม่รู้ว่าใครทำ" (migration 013 ถอด FK เดิมออก)
                await conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    trace_id VARCHAR(50) NOT NULL DEFAULT '-',
                    room_id INTEGER NOT NULL DEFAULT -1,
                    user_id INTEGER NOT NULL DEFAULT -1,
                    actor_identifier VARCHAR(100) NOT NULL DEFAULT '-',
                    client_source VARCHAR(20) NOT NULL DEFAULT '-',
                    service_name VARCHAR(50) NOT NULL DEFAULT '-',
                    action VARCHAR(50) NOT NULL DEFAULT '-',
                    entity_type VARCHAR(50) NOT NULL DEFAULT '-',
                    entity_id VARCHAR(50) NOT NULL DEFAULT '-',
                    status VARCHAR(20) NOT NULL DEFAULT 'success',
                    error_detail TEXT NOT NULL DEFAULT '-',
                    old_values JSONB NOT NULL DEFAULT '{}'::jsonb,
                    new_values JSONB NOT NULL DEFAULT '{}'::jsonb,
                    endpoint_or_command TEXT NOT NULL DEFAULT '-',
                    ip_address VARCHAR(45) NOT NULL DEFAULT '-',
                    user_agent TEXT NOT NULL DEFAULT '-',
                    execution_time_ms INTEGER NOT NULL DEFAULT 0,
                    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """)

                # --- 8.5 notifications: ระบบแจ้งเตือน + unread badge + read-receipt (Phase 7) ---
                #   - group_type: กลุ่มสำหรับ badge ตามเมนู (issue_mine=เรื่องของฉัน / issue_received=เรื่องที่รับ /
                #     board=PIRI Boards / report=จัดการรายงาน)
                #   - type: เหตุการณ์ (issue_new|issue_update|issue_comment|board_new|board_reply|board_hidden|report_new|report_actioned)
                #   - entity_type/entity_id: จุดปลายทาง (คลิกแล้วไปที่เรื่อง/บอร์ด/รายงาน)
                #   - board_id: denormalize เพื่อ batch mark-read เมื่อเปิด board โดยไม่ต้องรู้ entity_type
                #   - actor_name: snapshot ชื่อผู้ก่อเหตุ (เรื่อง anonymous → 'ไม่ระบุชื่อ')
                #   - read_at: NULL = ยังไม่อ่าน → badge = COUNT(*) WHERE read_at IS NULL GROUP BY group_type
                #   - ทุก insert อยู่ใน transaction เดียวกับข้อมูลหลัก (ลอกแบบ AuditLogger — ตามกฎ backend.md)
                #
                # ⚠️ **ตารางนี้มี trigger สองตัว และไม่มีตัวไหนถูก mirror ที่นี่เลย** (เจตนา):
                #   1. `trg_notifications_push_outbox` → `push_outbox_enqueue()` (Web Push)
                #      อยู่ที่ `migrations/018_push_notifications.py`
                #   2. `trg_notifications_stream` → `notifications_stream_notify()` (SSE badge)
                #      อยู่ที่ `migrations/020_notifications_pg_notify.py`
                #   เหตุผลเดียวกันทั้งคู่: `CREATE OR REPLACE FUNCTION` ที่ copy ไว้สองที่
                #   (ที่นี่ + migration) จะ drift กันได้ง่าย ⇒ **"ตาราง" อยู่ที่นี่ "พฤติกรรม" อยู่ที่ migration**
                #   · สอง trigger อยู่บนตารางเดียวกันได้ ไม่ชนกัน (Postgres ยิงเรียงตามชื่อ) และ
                #     จงใจใช้คนละฟังก์ชัน ไม่ไป `CREATE OR REPLACE` ทับกัน
                await conn.execute("""
                CREATE TABLE IF NOT EXISTS notifications (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    group_type VARCHAR(30) NOT NULL,
                    type VARCHAR(30) NOT NULL,
                    title TEXT NOT NULL,
                    body TEXT NOT NULL,
                    entity_type VARCHAR(30),
                    entity_id INTEGER,
                    board_id INTEGER,
                    actor_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    actor_name TEXT,
                    read_at TIMESTAMP WITH TIME ZONE,
                    -- ⭐ E2 (migration 024): ธงยกเว้น quiet hours **รายแถว**
                    --    ประกาศฉุกเฉิน (priority='urgent') ตั้ง TRUE ⇒ push worker ส่งทะลุทุกด่านเวลา
                    --    ⚠️ DEFAULT FALSE = แถวเดิม/แถวปกติไม่ได้รับยกเว้น (PG 11+ ADD COLUMN
                    --       แบบ constant default ไม่ rewrite ตาราง ⇒ production ได้ค่าโดยไม่ล็อกนาน)
                    bypass_quiet_hours BOOLEAN NOT NULL DEFAULT FALSE,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
                """)

                # --- 8.6 notification_preferences: ปิด/เปิดการแจ้งเตือนรายกลุ่ม (migration 016) ---
                #   - "ไม่มีแถว" = เปิด → เป็นค่าตั้งต้นของทุกคน ไม่ต้อง backfill
                #   - enabled gate **ทั้ง in-app และ push** (push ยังไม่มีในระบบ — ดู A3)
                #   - ชื่อ `enabled` ไม่ใช่ `push_enabled` โดยเจตนา — วันหน้าเพิ่มคอลัมน์ใหม่
                #     ควบคู่ ห้าม rename (ดูเหตุผลเต็มใน migrations/016_*.py)
                #   - ไม่มี CHECK บน group_type ตามแบบตาราง notifications — GROUP_TYPES โตได้
                #     (D1 จะเพิ่ม "event") ⇒ ใช้ regex ที่ชั้น Pydantic/router แทน
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

                # --- 8.7 academic_terms: ภาคเรียน (migration 017) ---
                #   - โรงเรียนถามว่า "ภาคนี้เป็นยังไง" ⇒ ต้องมีช่วงวันที่ให้กรองสถิติ
                #   - **ไม่มีภาคปัจจุบันก็ได้** (ค่าเริ่มต้นของระบบ) ⇒ get_current_term คืน None
                #     แล้วสถิติจะนับทั้งหมด — ไม่ต้อง backfill ภาคเดา ๆ ให้ตัวเลขผิดเงียบ ๆ
                #   - end_date รวมวันสุดท้าย (inclusive) — ระบุชัดเพราะเป็นจุดที่พลาดง่าย
                await conn.execute("""
                CREATE TABLE IF NOT EXISTS academic_terms (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(50) NOT NULL,
                    start_date DATE NOT NULL,
                    end_date DATE NOT NULL,
                    is_current BOOLEAN NOT NULL DEFAULT FALSE,
                    -- 🌟 ปีการศึกษาที่ภาคนี้สังกัด (migration 027) — 1 ปีมี 2 ภาค
                    --   nullable โดยเจตนา: ภาคที่สร้างก่อนมีฟีเจอร์นี้ยังใช้ได้ (ไม่ต้อง backfill)
                    academic_year_id INTEGER REFERENCES academic_years(id),
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    deleted_at TIMESTAMP WITH TIME ZONE,
                    CONSTRAINT chk_academic_terms_range CHECK (end_date >= start_date)
                );
                """)

                # --- 8.75 rollover_runs: ประวัติการเลื่อนชั้นทั้งโรงเรียน (migration 027) ---
                #   เก็บผลของ preview/apply ไว้ตอบคำถาม "เลื่อนชั้นรอบล่าสุดทำอะไรไปบ้าง"
                #   ⚠️ ไม่เข้า ARQ queue (ต่างจาก student_import_jobs) โดยเจตนา — apply เป็น
                #      SQL ล้วน ไม่มี bcrypt/xlsx ⇒ 2-4 วิ · และ queue เป็น max_jobs=1
                #      ⇒ ช่วงสัปดาห์ลงทะเบียน โรงเรียนจะต้องรอหลัง import 30 นาที
                await conn.execute("""
                CREATE TABLE IF NOT EXISTS rollover_runs (
                    id SERIAL PRIMARY KEY,
                    from_year_id INTEGER NOT NULL REFERENCES academic_years(id) ON DELETE RESTRICT,
                    to_year_id   INTEGER NOT NULL REFERENCES academic_years(id) ON DELETE RESTRICT,
                    status TEXT NOT NULL DEFAULT 'PREVIEWED',   -- PREVIEWED / APPLIED / FAILED
                    plan JSONB NOT NULL DEFAULT '{}'::jsonb,
                    promoted_count INTEGER NOT NULL DEFAULT 0,
                    graduated_count INTEGER NOT NULL DEFAULT 0,
                    staff_carried_count INTEGER NOT NULL DEFAULT 0,
                    positions_reset_count INTEGER NOT NULL DEFAULT 0,
                    unmapped_count INTEGER NOT NULL DEFAULT 0,
                    error_message TEXT,
                    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    applied_at TIMESTAMP WITH TIME ZONE,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
                """)

                # --- 8.8 announcements: ประกาศสาธารณะบน Landing Page ---
                #   - priority: normal / high / urgent (urgent = พื้นหลังแดงเข้มบนหน้า Landing)
                #   - link: ลิงก์ปลายทาง (optional) เมื่อคลิกประกาศ
                await conn.execute("""
                CREATE TABLE IF NOT EXISTS announcements (
                    id SERIAL PRIMARY KEY,
                    message TEXT NOT NULL,
                    priority VARCHAR(10) NOT NULL DEFAULT 'normal',
                    link TEXT,
                    -- ผู้ประกาศ/ผู้แก้ล่าสุด — เก็บเป็น id เปล่า ไม่ใส่ FK
                    -- (ตามบทเรียน skills.md: ตารางที่ต้องเก็บความจริงย้อนหลังห้าม FK แบบ ON DELETE
                    --  action ใด ๆ เพราะลบผู้ใช้แล้วหลักฐาน "ใครประกาศ" จะหายไป)
                    -- NULL = ประกาศที่ seed ก่อนมีฟีเจอร์นี้
                    created_by INTEGER,
                    updated_by INTEGER,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    deleted_at TIMESTAMP WITH TIME ZONE,
                    -- "ปลดระวาง" — เอาออกจากหน้า Landing/Home แต่เก็บไว้เป็นประวัติ
                    -- ⭐ ตั้งใจให้เป็นอิสระจาก deleted_at (ไม่ใส่ CHECK บังคับ exclusive)
                    --    ⇒ ปลดระวางแล้วเผลอลบ → กู้คืน → กลับมาเป็น "ปลดระวางแล้ว" ตามเดิม
                    --    ไม่ใช่กลับไปโชว์บนหน้าเว็บ (ดู migration 015)
                    retired_at TIMESTAMP WITH TIME ZONE,
                    CONSTRAINT chk_announcements_priority CHECK (priority IN ('normal', 'high', 'urgent'))
                );
                """)

                # Seed ประกาศเริ่มต้น (เฉพาะฐานข้อมูลใหม่) — idempotent
                announcement_count = await conn.fetchval(
                    "SELECT COUNT(*) FROM announcements"
                )
                if announcement_count == 0:
                    await conn.executemany(
                        """
                        INSERT INTO announcements (message, priority) VALUES ($1, $2)
                        """,
                        [
                            (
                                "ยินดีต้อนรับสู่ PIRIvoice — ส่งเสียงของคุณเพื่อให้โรงเรียนดีขึ้น",
                                "normal",
                            ),
                            (
                                "สภานักเรียนเปิดรับข้อเสนอโครงการใหม่ผ่าน PIRI Vote แล้ว วันนี้โหวตได้เลย!",
                                "high",
                            ),
                        ],
                    )
                    logger.info("📣 Seeded default announcements.")

                # --- 8.9 push_subscriptions: ปลายทาง push ของแต่ละอุปกรณ์ (migration 018 / A3) ---
                #   - ⭐ unique บน `endpoint` **เดี่ยว ๆ** ไม่ใช่ (user_id, endpoint): endpoint
                #     คือ "เบราว์เซอร์เครื่องนี้" ไม่ใช่ "ผู้ใช้คนนี้" — เครื่องเรียนเครื่องเดียว
                #     ถูกใช้หลายคน ถ้า unique เป็นคู่จะเหลือแถวของคนเก่าค้าง ⇒ push ไปหาคนเก่า
                #     = รั่วข้ามผู้ใช้ · `ON CONFLICT (endpoint) DO UPDATE SET user_id = EXCLUDED.user_id`
                #     ยึดเครื่องกับผู้ใช้ที่ล็อกอินอยู่ใหม่ทุกครั้ง (สัญญาณสดชนะความจำ)
                #   - `failure_count` / `last_success_at` มีไว้สำหรับวินิจฉัยเท่านั้น
                #     (ไม่ได้ใช้ตัดสินใจลบ — ตัวตัดสินคือ HTTP 404/410 ซึ่งแม่นกว่า)
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

                # --- 8.10 push_outbox: คิวส่ง push (transactional outbox — migration 018 / A3) ---
                #   - เก็บแค่ `notification_id` ไม่ denormalize ข้อความ: `notifications` ถูก
                #     mark_read เท่านั้น ไม่มีโค้ดไหนลบ ⇒ JOIN ไม่มีทางพลาด + source of truth เดียว
                #   - `next_attempt_at` = เวลาที่จะลองใหม่ (exponential backoff) ·
                #     `processing_at` = ถูก claim ไปแล้ว (worker ตายกลางคันจะกู้คืนตอน startup)
                #   - `processed_at IS NOT NULL` = จบแล้ว ไม่ว่าจะสำเร็จหรือทิ้ง
                #
                # ⚠️ **trigger `trg_notifications_push_outbox` ไม่ได้ mirror มาที่นี่โดยเจตนา**
                #    มันอยู่ใน `migrations/018_push_notifications.py` ที่เดียว — ถ้า copy มาสองที่
                #    sẽ drift กันได้ง่าย (และ init_db ไม่ได้อยู่ใน transaction เดียวกับ migration)
                #    ⇒ ไฟล์นี้มีแค่ "ตาราง" ส่วน "พฤติกรรม" อยู่ที่ migration
                #    📌 ร่างล่าสุดของฟังก์ชันอยู่ที่ `migrations/019_push_outbox_requires_device.py`
                #       (019 ทับ 018 ด้วย `CREATE OR REPLACE` — เพิ่มประตู "ผู้รับต้องมีอุปกรณ์
                #        ก่อนจึงเข้าคิว") ⇒ **อ่าน 019 เป็นหลัก** ถ้าจะแก้เงื่อนไขการเข้าคิวจริง ๆ
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

                # --- 9. ตารางคิวงาน Import นักเรียนจาก Excel (Queue: ARQ Worker) ---
                # status: 'PENDING' (อัปโหลดแล้ว ยังไม่สั่งเริ่ม) / 'QUEUED' (ยิงเข้า Redis แล้ว)
                #         'PROCESSING' (worker กำลังทำงาน) / 'COMPLETED' / 'FAILED'
                # error_logs: JSONB array ของข้อผิดพลาดรายแถว (ข้ามไปแต่ไม่ล้มทั้งไฟล์)
                # file_path: path จริงบน storage (ไม่ expose ผ่าน API) ; file_name: ชื่อไฟล์เดิมสำหรับแสดงผล
                await conn.execute("""
                CREATE TABLE IF NOT EXISTS student_import_jobs (
                    id SERIAL PRIMARY KEY,
                    file_name TEXT NOT NULL,              -- ชื่อไฟล์เดิมที่ผู้ใช้เห็น (แสดงผลใน UI)
                    file_path TEXT NOT NULL,              -- path เก็บไฟล์บน storage (internal)
                    status TEXT NOT NULL DEFAULT 'PENDING',
                    total_rows INTEGER NOT NULL DEFAULT 0,
                    processed_rows INTEGER NOT NULL DEFAULT 0,
                    imported_count INTEGER NOT NULL DEFAULT 0,
                    skipped_count INTEGER NOT NULL DEFAULT 0,
                    error_logs JSONB NOT NULL DEFAULT '[]'::jsonb,
                    error_message TEXT,                   -- ข้อความ error ระดับ job (เช่น อ่านไฟล์ไม่ได้)
                    default_password TEXT,                -- รหัสเริ่มต้น (default = เลขรหัสนักเรียน)
                    allowed_level TEXT,                   -- ครูทั่วไปนำเข้าได้เฉพาะระดับชั้นนี้
                    -- 🌟 ปีการศึกษาของชุดที่กำลังนำเข้า (migration 028) — ไฟล์ Excel ที่ไม่มี
                    --   คอลัมน์ "ปีการศึกษา" จะตกมาอยู่ปีของ job นี้ · nullable โดยเจตนา:
                    --   job เก่าที่ค้างในตารางยังอ่านได้ (fallback = ปีปัจจุบัน) — ไม่ต้อง backfill
                    academic_year_id INTEGER REFERENCES academic_years(id),
                    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    started_at TIMESTAMP WITH TIME ZONE,
                    completed_at TIMESTAMP WITH TIME ZONE,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
                """)
                await conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_student_import_jobs_status
                        ON student_import_jobs(status);
                    CREATE INDEX IF NOT EXISTS idx_student_import_jobs_created_at
                        ON student_import_jobs(created_at);
                """)

                # bookmarks (C2 / migration 021) — "บันทึกไว้อ่านทีหลัง" ของเจ้าของบัญชี
                # ⚠️ **polymorphic** (entity_type + entity_id) ⇒ **ไม่มี FK ไป issues/piri_boards**
                #    FK ของ Postgres ผูกกับตารางเดียว ⇒ ถ้าจะบังคับด้วย FK ต้องแยกเป็น 2 คอลัมน์
                #    nullable ซึ่งทำให้ทุกคิวรีต้องเขียน COALESCE และเพิ่มชนิดใหม่ต้อง ALTER TABLE
                #    ⇒ ความถูกต้องย้ายไปอยู่ที่ bookmark_service.create_bookmark()
                #      (ตรวจว่า entity มีจริงและไม่ถูกลบก่อน insert — มีเทสต์ B3/B4 คุมอยู่)
                # ⚠️ **ไม่มี CHECK บน entity_type โดยเจตนา** — ชุดนี้จะโต (D1 จะเพิ่ม 'event')
                #    ⇒ validate ที่ชั้น Pydantic (`Literal`) ซึ่งตอบ 422 ให้เองโดยไม่ต้อง migrate
                #      (ต่างจาก piri_boards.board_type ที่ CHECK ไว้ก่อนแล้ว ⇒ E1 ต้อง DROP CONSTRAINT
                #       — ดู migration 022)
                # ⚠️ **ไม่มี deleted_at** — เลิกบันทึกคือ DELETE จริง (ไม่ใช่ข้อมูลที่ต้องเก็บประวัติ)
                #    ⇒ unique index จึงเป็นแบบธรรมดา ไม่ใช่ partial แบบ piri_votes
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS bookmarks (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        entity_type VARCHAR(20) NOT NULL,
                        entity_id INTEGER NOT NULL,
                        created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
                    );
                """)

                # --- 9.6 app_settings: ค่าตั้งระดับโรงเรียน (A8 / migration 023) ---
                #   - key/value เป็น **jsonb** ⇒ เพิ่มค่าตั้งใหม่ไม่ต้องออก migration
                #     (เหตุผลเดียวกับที่ notification_preferences/bookmarks ไม่มี CHECK)
                #   - key ปัจจุบันมีตัวเดียว: `quiet_hours` = {"enabled","start","end"}
                #     ⚠️ **ไม่มีแถว = ไม่ปิดกั้นอะไร** (ไม่ต้อง seed — ดู migrations/023_*.py)
                #   - validation อยู่ที่ Pydantic + app_settings_service ไม่ใช่ที่ DB
                #   - updated_by เป็น ON DELETE SET NULL ⇒ ลบผู้ดูแลไม่ทำให้ค่าตั้งโรงเรียนหาย
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS app_settings (
                        key VARCHAR(60) PRIMARY KEY,
                        value JSONB NOT NULL,
                        description TEXT,
                        updated_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
                        created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
                    );
                """)

                # --- 9.7 events / event_registrations: ระบบกิจกรรม (D1 / migration 025) ---
                #   ⚠️ **แหล่งความจริงของ DDL อยู่ที่ migrations/025_events.py** — ที่นี่เป็น
                #      mirror ให้ DB ใหม่ได้ครบในรอบเดียว (ตัว migration จะเป็น no-op เพราะ IF NOT EXISTS)
                #   - `status` = สถานะการเผยแพร่ (draft/published/cancelled) **คนละมิติกับ deleted_at**
                #     ⇒ ต่างจาก announcements ที่ใช้ `retired_at`
                #   - `capacity IS NULL` = ไม่จำกัดจำนวน (0 ไม่ใช่ "ไม่จำกัด" ⇒ มี CHECK กันไว้)
                #   - created_by/updated_by **ไม่ใส่ FK** (เหตุผลเดียวกับ migration 014:
                #     "ลบผู้ใช้ = หลักฐานหาย") ⇒ LEFT JOIN เอาเองตอนอ่าน
                #   - unique (event_id, user_id) **ไม่มี partial predicate** โดยเจตนา —
                #     ยกเลิก = พลิก status ไม่ใช่ลบแถว ⇒ ประวัติการสมัครไม่หาย
                #   - `category` (D4 / migration 026) — **แหล่งความจริงอยู่ที่
                #     migrations/026_event_category.py** · ที่นี่ mirror ให้ DB ใหม่ครบในรอบเดียว
                #     ⚠️ CHECK ที่ลิสต์ค่าตายตัว ⇒ เพิ่มหมวดใหม่ต้องออก migration ใหม่ **และ**
                #        แก้ที่นี่ + `EventCategory` (event_schemas) + `EVENT_CATEGORIES` (FE)
                #     ⚠️ `NOT NULL DEFAULT 'other'` โดยเจตนา — ไม่ปล่อย NULL เพราะจะเกิด
                #        "สามสถานะ" ที่ผู้ใช้แยกไม่ออก ("ไม่ระบุ"/"อื่น ๆ"/ค่าจริง) และการกรอง
                #        ต้องเขียน `IS NULL OR ...` ทุกที่ · 'other' = "อื่น ๆ" ซึ่งเป็นคำตอบจริง
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS events (
                        id SERIAL PRIMARY KEY,
                        title VARCHAR(200) NOT NULL,
                        description TEXT,
                        location VARCHAR(200),
                        cover_image_url VARCHAR(500),
                        event_date TIMESTAMP WITH TIME ZONE NOT NULL,
                        registration_deadline TIMESTAMP WITH TIME ZONE,
                        capacity INTEGER,
                        category VARCHAR(20) NOT NULL DEFAULT 'other',
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
                            CHECK (capacity IS NULL OR capacity > 0),
                        CONSTRAINT chk_events_category
                            CHECK (category IN ('academic', 'sports', 'arts', 'service',
                                                'club', 'meeting', 'other'))
                    );
                """)
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS event_registrations (
                        id SERIAL PRIMARY KEY,
                        event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
                        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        status VARCHAR(20) NOT NULL DEFAULT 'registered',
                        registered_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        cancelled_at TIMESTAMP WITH TIME ZONE,
                        checked_in_at TIMESTAMP WITH TIME ZONE,
                        updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        -- `checked_in` ใส่ไว้รอ D2 (QR) — CHECK ที่ลิสต์ค่าตายตัวแก้ทีหลัง
                        -- ต้องออก migration ใหม่ (บทเรียน board_type ตอน E1) ⇒ ใส่ล่วงหน้าถูกกว่า
                        CONSTRAINT chk_event_registrations_status
                            CHECK (status IN ('registered', 'waitlisted', 'cancelled', 'checked_in'))
                    );
                """)

                # --- 10. ตารางรองรับ dashboard ---
                # (การนับสถิติสามารถ query ตรงจาก issues ได้ แต่ให้มี view/ตารางสรุปไว้ก่อน)

    except Exception as e:
        logger.error(f"❌ Failed to initialize Database: {e}")
        raise e

    # 🚀 รัน migration files (อัปเกรด schema ของ DB เดิม + กันรันซ้ำผ่าน schema_migrations)
    # ⚠️ ต้องรันก่อนสร้าง index — DB เดิมที่ยังไม่มีคอลัมน์ (เช่น issues.main_category จาก
    # migration 001) ถ้าสร้าง index ก่อนจะ crash ด้วย UndefinedColumnError (เจอจริงบน staging:
    # 'column "main_category" does not exist')
    try:
        from core.migrations import run_migrations
        await run_migrations(pool)
    except Exception as e:
        logger.error(f"❌ Failed to run migrations: {e}")
        raise e

    # --- 11. Index เพื่อความเร็ว (รันหลัง migrations — อ้างคอลัมน์ที่ migration อาจเพิ่งเพิ่ม) ---
    try:
        async with pool.acquire() as conn:
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_issues_room_status ON issues(room_id, status);
                CREATE INDEX IF NOT EXISTS idx_issues_reporter ON issues(reporter_id);
                CREATE INDEX IF NOT EXISTS idx_issues_level ON issues(current_level);
                CREATE INDEX IF NOT EXISTS idx_issues_main_category ON issues(main_category);
                CREATE INDEX IF NOT EXISTS idx_issues_category ON issues(category);
                CREATE INDEX IF NOT EXISTS idx_issue_escalations_issue ON issue_escalations(issue_id);
                CREATE INDEX IF NOT EXISTS idx_issue_steps_issue ON issue_steps(issue_id);
                CREATE INDEX IF NOT EXISTS idx_issue_countdowns_issue ON issue_countdowns(issue_id);
                CREATE INDEX IF NOT EXISTS idx_issue_status_history_issue ON issue_status_history(issue_id);
                CREATE INDEX IF NOT EXISTS idx_issue_comments_issue ON issue_comments(issue_id);
                -- PIRI Boards (Phase 1: ตารางสาธารณะ) — feed ตาม status/เวลา + ค้นหา board จาก issue ต้นทาง
                -- 📌 E1 ('suggestion') **ไม่เพิ่ม index** โดยเจตนา: ตัวกรองทุกเส้นทางนำด้วย
                --    `status = 'active'` เสมอ ⇒ `idx_piri_boards_status_created` ใช้ได้อยู่แล้ว
                --    และ `board_type` มี cardinality แค่ 3 ⇒ index เดี่ยวไม่ได้ช่วยอะไร
                --    (ถ้าวันหน้าจำนวนบอร์ดโตจนวัดแล้วช้าจริง ค่อยพิจารณา composite (status, board_type, created_at))
                CREATE INDEX IF NOT EXISTS idx_piri_boards_status_created ON piri_boards(status, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_piri_boards_source_issue ON piri_boards(source_issue_id);
                CREATE INDEX IF NOT EXISTS idx_piri_boards_author ON piri_boards(author_id);
                CREATE INDEX IF NOT EXISTS idx_piri_board_comments_board ON piri_board_comments(board_id);
                CREATE INDEX IF NOT EXISTS idx_piri_board_comments_parent ON piri_board_comments(parent_comment_id);
                CREATE INDEX IF NOT EXISTS idx_piri_board_comments_user ON piri_board_comments(user_id);
                CREATE INDEX IF NOT EXISTS idx_piri_vote_choices_board ON piri_vote_choices(board_id, sort_order);
                CREATE INDEX IF NOT EXISTS idx_piri_votes_board ON piri_votes(board_id);
                CREATE INDEX IF NOT EXISTS idx_piri_votes_choice ON piri_votes(choice_id);
                CREATE INDEX IF NOT EXISTS idx_piri_board_reactions_target ON piri_board_reactions(target_type, target_id);
                CREATE INDEX IF NOT EXISTS idx_piri_board_reactions_user ON piri_board_reactions(user_id);
                -- PIRI Reports (Phase 5) — คิวรายงาน (กรอง status) + ค้นจาก board/comment/reporter
                CREATE INDEX IF NOT EXISTS idx_piri_board_reports_status ON piri_board_reports(status);
                CREATE INDEX IF NOT EXISTS idx_piri_board_reports_board ON piri_board_reports(board_id);
                CREATE INDEX IF NOT EXISTS idx_piri_board_reports_comment ON piri_board_reports(comment_id);
                CREATE INDEX IF NOT EXISTS idx_piri_board_reports_reporter ON piri_board_reports(reporter_id);
                -- ผู้ใช้โหวต/react ได้ 1 ครั้งต่อ target (partial: เฉพาะ row ที่ยัง active)
                -- → soft delete แล้วกลับมาโหวต/react ใหม่ได้ (ไม่ชน index)
                CREATE UNIQUE INDEX IF NOT EXISTS uq_piri_votes_board_user_active
                    ON piri_votes(board_id, user_id)
                    WHERE deleted_at IS NULL;
                CREATE UNIQUE INDEX IF NOT EXISTS uq_piri_board_reactions_target_user_active
                    ON piri_board_reactions(target_type, target_id, user_id)
                    WHERE deleted_at IS NULL;
                -- user แจ้งคอมเมนต์เดิมซ้ำไม่ได้ (partial: เฉพาะรายงานที่ยัง active) — กันสแปมรายงาน
                CREATE UNIQUE INDEX IF NOT EXISTS uq_piri_board_report_user_comment_active
                    ON piri_board_reports(reporter_id, comment_id)
                    WHERE deleted_at IS NULL;
                -- audit_logs โตเร็ว (Phase 3: เก็บทุก action + read) — ต้องมี index ครบ
                CREATE INDEX IF NOT EXISTS idx_audit_logs_action_created ON audit_logs(action, created_at);
                CREATE INDEX IF NOT EXISTS idx_audit_logs_user_id ON audit_logs(user_id);
                CREATE INDEX IF NOT EXISTS idx_audit_logs_entity ON audit_logs(entity_type, entity_id);
                CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs(created_at);
                -- notifications (Phase 7) — unread badge (group by) + รายการล่าสุด + batch mark-read
                CREATE INDEX IF NOT EXISTS idx_notifications_user_unread_group
                    ON notifications(user_id, group_type) WHERE read_at IS NULL;
                CREATE INDEX IF NOT EXISTS idx_notifications_user_created
                    ON notifications(user_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_notifications_board
                    ON notifications(board_id) WHERE board_id IS NOT NULL;
                CREATE INDEX IF NOT EXISTS idx_notifications_entity
                    ON notifications(entity_type, entity_id);
                -- notification_preferences (A2 / migration 016) — ตั้งค่าการแจ้งเตือนรายกลุ่ม
                --   ⚠️ unique index นี้คือสิ่งที่ทำให้ `ON CONFLICT (user_id, group_type)
                --      DO UPDATE` ใน update_preferences() ทำงาน — ลบไม่ได้
                --   ไม่มี index อื่นโดยเจตนา: ≤ 4 แถว/คน และอ่านแบบ point lookup อยู่แล้ว
                CREATE UNIQUE INDEX IF NOT EXISTS uq_notification_prefs_user_group
                    ON notification_preferences(user_id, group_type);
                -- academic_terms (T1 / migration 017) — ภาคเรียน
                --   ⚠️ partial unique index: key คือ is_current แต่กรอง WHERE is_current
                --      ⇒ ใน index มีแต่แถว is_current = TRUE และ key เท่ากันหมด ⇒ บังคับ
                --      "มีภาคปัจจุบันได้ตัวเดียว" ได้ด้วย DB เอง ไม่ต้องพึ่งโค้ด
                --   ⚠️ non-deferrable ⇒ service ต้อง "ล้างตัวเก่าก่อน ตั้งตัวใหม่ทีหลัง"
                --      ใน transaction เดียวกัน (สลับลำดับ = UniqueViolationError)
                CREATE UNIQUE INDEX IF NOT EXISTS uq_academic_terms_single_current
                    ON academic_terms(is_current) WHERE is_current AND deleted_at IS NULL;
                -- คิวรีหลัก = "ภาคที่คลุมวันนี้" / "ภาคตามช่วงวันที่" ⇒ index บนช่วงวัน
                CREATE INDEX IF NOT EXISTS idx_academic_terms_dates
                    ON academic_terms(start_date, end_date);
                -- academic_years (migration 027) — ปีการศึกษา
                --   ทริกเดียวกับ uq_academic_terms_single_current เป๊ะ: "ปีปัจจุบันมีตัวเดียว"
                --   ⚠️ non-deferrable ⇒ set_current_year() ต้องล้างตัวเก่าก่อนตั้งตัวใหม่
                --      (สลับลำดับ = UniqueViolationError) — ดู term_service._clear_current
                CREATE UNIQUE INDEX IF NOT EXISTS uq_academic_years_single_current
                    ON academic_years(is_current) WHERE is_current AND deleted_at IS NULL;
                -- หนึ่ง พ.ศ. มีได้หนึ่งปี · partial เพื่อให้ "ลบแล้วกู้คืน" ทำงาน
                --   (ถ้าเป็น UNIQUE ตรง ๆ การกู้คืนปีที่ซ้ำกับแถวใหม่จะล้มเหลวถาวร)
                CREATE UNIQUE INDEX IF NOT EXISTS uq_academic_years_year_be
                    ON academic_years(year_be) WHERE deleted_at IS NULL;
                -- rollover_runs (migration 027) — คิวรีจริงคือ "ประวัติการเลื่อนชั้นของปีคู่นี้"
                --   ⚠️ ต้องมี `IF NOT EXISTS` + ชื่อ index ตรงกับใน migration 027
                --      ไม่งั้น fresh DB จะได้ index สองตัวคนละชื่อ (init_db สร้าง แล้ว migration
                --      `CREATE INDEX IF NOT EXISTS` ด้วยชื่อเดิม = no-op ⇒ OK แต่ถ้าชื่อไม่ตรงจะซ้ำ)
                CREATE INDEX IF NOT EXISTS idx_rollover_runs_from_to
                    ON rollover_runs(from_year_id, to_year_id);
                -- push_subscriptions / push_outbox (A3 / migration 018) — Web Push
                --   ⚠️ unique บน `endpoint` เดี่ยว ๆ (ไม่ใช่คู่กับ user_id) — ดูเหตุผลยาวใน
                --      migrations/018_*.py: endpoint คือ "เครื่องนี้" ซึ่งเปลี่ยนเจ้าของได้
                --   ⚠️ ลบ index นี้ไม่ได้ — `ON CONFLICT (endpoint) DO UPDATE` พึ่งมันอยู่
                CREATE UNIQUE INDEX IF NOT EXISTS uq_push_subscriptions_endpoint
                    ON push_subscriptions(endpoint);
                CREATE INDEX IF NOT EXISTS idx_push_subscriptions_user
                    ON push_subscriptions(user_id);
                -- กัน trigger ยิงซ้ำแล้วได้ 2 แถวสำหรับ (notification, user) เดียวกัน
                CREATE UNIQUE INDEX IF NOT EXISTS uq_push_outbox_notification_user
                    ON push_outbox(notification_id, user_id);
                -- ⭐ partial index: key = `id` ล้วน (ไม่ใช่ next_attempt_at) เพราะคิวรีจริงคือ
                --    `WHERE processed_at IS NULL ORDER BY id LIMIT n` — ของเข้าก่อนได้ก่อน
                --    และ partial ทำให้ index เล็กลงมากเมื่อของที่ processed แล้วสะสม (retention 7 วัน)
                CREATE INDEX IF NOT EXISTS idx_push_outbox_pending
                    ON push_outbox(id) WHERE processed_at IS NULL;
                -- bookmarks (C2 / migration 021) — "บันทึกไว้อ่านทีหลัง"
                --   ⚠️ unique **ต้องมี `entity_type` อยู่ด้วย** — เรื่อง #7 กับบอร์ด #7 คนละอัน
                --      และ `ON CONFLICT (user_id, entity_type, entity_id)` ใน create_bookmark()
                --      พึ่ง index นี้อยู่ ⇒ ลบไม่ได้
                --   ⚠️ ต่างจาก piri_votes ที่ unique เป็น partial (WHERE deleted_at IS NULL)
                --      เพราะตารางนี้ **ไม่มีการลบแบบ soft** ⇒ unique ธรรมดา
                CREATE UNIQUE INDEX IF NOT EXISTS uq_bookmarks_user_entity
                    ON bookmarks(user_id, entity_type, entity_id);
                -- ตรงกับ ORDER BY ของ list_bookmarks (ล่าสุดก่อน)
                CREATE INDEX IF NOT EXISTS idx_bookmarks_user_created
                    ON bookmarks(user_id, created_at DESC);
                -- ⭐ 2 ตัวนี้ไม่เกี่ยวกับ bookmarks เลย แต่มากับ migration 021 โดยเจตนา:
                --    ทั้ง C3 (`votes_cast` / `issue_comments_posted`) และ C1 (feed) กรองด้วย
                --    `user_id` แต่สองคอลัมน์นี้ **ไม่มี index** (ตรวจ init_db L614-643 แล้ว:
                --    มีแต่ idx_piri_board_comments_user) ⇒ seq scan ทุกครั้งที่เปิดโปรไฟล์/กิจกรรม
                --    ⇒ ปิดช่องนี้พร้อมกันในรอบเดียว ต้นทุนคือ index เล็ก ๆ บนคอลัมน์เดียว
                CREATE INDEX IF NOT EXISTS idx_piri_votes_user ON piri_votes(user_id);
                CREATE INDEX IF NOT EXISTS idx_issue_comments_user ON issue_comments(user_id);

                CREATE INDEX IF NOT EXISTS idx_students_room_no_active
                    ON students(room_id, student_no)
                    WHERE deleted_at IS NULL;
                CREATE INDEX IF NOT EXISTS idx_students_role_active
                    ON students(class_role)
                    WHERE deleted_at IS NULL;
                CREATE INDEX IF NOT EXISTS idx_students_responsibilities
                    ON students USING GIN (responsibilities);
                -- คิวรีหลักหลังมีปีการศึกษา (migration 027) = "สมาชิกของปีนี้ ในห้องนี้"
                --   ⇒ (year, room) พอ · partial ตาม deleted_at ให้ตรงกับที่ทุกคิวรีกรอง
                --   ⚠️ คอลัมน์ `academic_year_id` เกิดจาก migration 027 **ที่รันไปแล้วด้านบน**
                --      (run_migrations อยู่ก่อนบล็อก index นี้) ⇒ บน DB เก่าก็สร้างได้
                CREATE INDEX IF NOT EXISTS idx_students_year_room
                    ON students(academic_year_id, room_id)
                    WHERE deleted_at IS NULL;
                -- กันสร้าง student ซ้ำ (ห้อง, ปี, เลขประจำตัว) — import แบบ ON CONFLICT ใช้ index นี้
                --   🌟 **มีมิติปี** (migration 028 สลับมาจาก `uq_students_room_student_active`
                --      ที่คีย์แค่ `(room_id, student_id)`) — ตัวเก่า **แคบเกินไป**: มันห้ามคนเดิม
                --      มีสองแถวในห้องเดิม "คนละปี" ซึ่งคือสิ่งที่ต้องมีให้ได้หลังขึ้นปีใหม่
                --      ⇒ ถ้าไม่สลับ `apply_rollover` (P4) จะ insert แถวปีใหม่ไม่ได้เลย
                --   🔴 **ต้องตรงกับ migration 028 เสมอ** — บน DB จริง 028 เป็นคนสลับให้
                --      ส่วนที่นี่ทำให้ **fresh DB ได้ index เดียวกัน** · ถ้าแก้ที่เดียว
                --      เทสต์จะผ่าน (fresh DB) ทั้งที่ production พัง หรือกลับกัน
                --   ⚠️ `run_migrations` รัน **ก่อน** บล็อกนี้ ⇒ บน DB จริง 028 DROP ตัวเก่าไปแล้ว
                --      การ `IF NOT EXISTS` ที่นี่จึงเป็น no-op (ไม่ได้สร้างตัวเก่ากลับมา)
                CREATE UNIQUE INDEX IF NOT EXISTS uq_students_room_year_student
                    ON students(room_id, academic_year_id, student_id)
                    WHERE deleted_at IS NULL;

                -- --- D1 ระบบกิจกรรม (migration 025) ---
                CREATE INDEX IF NOT EXISTS idx_events_status_date
                    ON events (status, event_date)
                    WHERE deleted_at IS NULL;
                CREATE INDEX IF NOT EXISTS idx_events_created_by
                    ON events (created_by)
                    WHERE deleted_at IS NULL;
                -- หนึ่งคนสมัครกิจกรรมหนึ่งครั้งได้ใบเดียว — เป็นทั้งด่านกันซ้ำและ index ของ
                -- "ฉันสมัครกิจกรรมนี้หรือยัง" (วิ่งทุกครั้งที่เปิดหน้ารายละเอียด)
                CREATE UNIQUE INDEX IF NOT EXISTS uq_event_registrations_event_user
                    ON event_registrations (event_id, user_id);
                -- เรียงคอลัมน์ตามที่ใช้จริง: นับที่นั่ง (event_id,status) แล้วต่อด้วยหัวคิว
                -- สำรอง (ORDER BY registered_at) ⇒ index เดียวตอบสองคำถาม
                CREATE INDEX IF NOT EXISTS idx_event_registrations_event_status
                    ON event_registrations (event_id, status, registered_at);
                CREATE INDEX IF NOT EXISTS idx_event_registrations_user
                    ON event_registrations (user_id, registered_at DESC);
            """)
    except Exception as e:
        logger.error(f"❌ Failed to create indexes: {e}")
        raise e

    logger.info("✅ PIRIvoice Database Tables & Indexes Initialized Successfully!")

async def run_setup():
    logger.info("🚀 Starting Manual Database Setup...")
    pool = None
    try:
        pool = await asyncpg.create_pool(
            settings.DATABASE_URL,
            min_size=1,
            max_size=5
        )
        if pool:
            await init_db(pool)
            logger.info("✨ Database Setup Process Finished!")
        else:
            logger.error("❌ Could not create database connection pool.")
    except Exception as e:
        logger.error(f"💥 Fatal Error during manual setup: {e}")
    finally:
        if pool:
            await pool.close()
            logger.info("🛑 Database pool closed.")

if __name__ == "__main__":
    if not settings.DATABASE_URL:
        logger.error("❌ DATABASE_URL not found in .env file!")
        sys.exit(1)

    asyncio.run(run_setup())
