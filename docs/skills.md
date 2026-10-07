# 🏫 PIRIvoice — Lessons จากพัฒนาระบบรับฟังความคิดเห็นและปัญหา

> ส่วนนี้บันทึกบทเรียนที่เจอจริงระหว่างพัฒนาระบบ PIRIvoice (สภานักเรียน) ตั้งแต่โครงสร้าง → backend → frontend → deploy

### 🛠️ asyncpg AmbiguousParameterError — `$1` ซ้ำใน 2 คอลัมน์คนละ type
- **Context/Problem:** `INSERT INTO rooms (room_code, room_name) VALUES ($1,$1)` → `AmbiguousParameterError: inconsistent types deduced for parameter $1` (VARCHAR vs TEXT) และ `INSERT has more expressions than target columns` เมื่อ parameter count ไม่ตรงคอลัมน์
- **Root Cause:** asyncpg อนุมาน type ของ parameter จากบริบท — ใช้ `$1` ตัวเดียวกับ 2 คอลัมน์ที่ type ต่างกัน (หรือ count ผิด) จะพังทั้งตอน runtime และตอน seed
- **Correct Pattern/Solution:** ใช้ parameter แยกเสมอ `VALUES ($1,$2,$3)`; นับจำนวน `$n` ให้ตรงกับคอลัมน์+values ก่อนรัน; โดยเฉพาะใน `seed_data.py`/script ที่มือเขียน SQL ตรงๆ — อาการเดาได้จาก error `INSERT has more expressions`
- **ขยาย (recursive CTE):** `WITH RECURSIVE chain(...) AS (SELECT 1, $1 UNION ALL SELECT ...)` → `UndefinedFunctionError: operator does not exist: integer = text` — asyncpg อนุมาน type ของ `$1` ใน non-recursive term ไม่ได้ (บริบทยังไม่รู้ column type) → ตอน JOIN `chain.cid` กับ `c.id` เจอ text=integer. **Fix: cast เสมอ `SELECT 1, $1::integer`** ใน non-recursive term ของ recursive CTE (เจอจริง 2026-08-28 ตอนวัด depth ของ comment chain)
- **Date Added:** 2026-08-08

### 🛠️ FastAPI Router + asyncpg — ต้องมี `python-multipart` สำหรับ `UploadFile`/Form
- **Context/Problem:** Import Excel ผ่าน `UploadFile` → RuntimeError: `Form data requires "python-multipart" to be installed` เฉพาะตอน import router ตัวนั้น
- **Root Cause:** FastAPI ติดตั้ง multipart parser ตอน declare `UploadFile` — ถ้า package ไม่มี จะ error ที่ import ไม่ใช่ runtime
- **Correct Pattern/Solution:** เพิ่ม `python-multipart>=0.0.9` ใน `requirements.txt` ตั้งแต่วันแรก (เวลา scaffold โปรเจค FastAPI ใหม่ + file upload ให้ใส่เลย)
- **Date Added:** 2026-08-08

### 🛠️ Frontend API baseURL — ต้องมี `/api` prefix ครบทุก service
- **Context/Problem:** login ผ่าน API ตรง (curl) ได้ แต่หน้าเว็บได้ "Not Found" ทุกบัญชี — backend ประกาศ endpoint `/api/auth/login` แต่ frontend ส่งไป `/auth/login`
- **Root Cause:** สร้าง `services/*.ts` แล้วลืม prefix `/api` (backend ใช้ `prefix="/api"` ใน main.py)
- **Correct Pattern/Solution:** grep ตรวจ `api.get('/` / `api.post('/` ให้ขึ้นต้น `/api/` เสมอ; เมื่อสร้าง service ใหม่ให้ตรวจ 1 ครั้ง — ผูกกับบทเรียนเดิม "ทุก layer ต้องรู้ path prefix"
- **Date Added:** 2026-08-08

### 🛠️ asyncpg `IndeterminateDatatypeError` — parameter เกินใน SQL ที่สร้าง dynamic
- **Context/Problem:** `GET /api/issues?mine=true` → 500 `could not determine data type of parameter $1`; เหตุผล: `list_issues` สร้าง `visible_cond` (เพิ่ม params) เสมอ แม้ `only_mine` ไม่ใช้มัน → มี `$1` เกินใน SQL
- **Root Cause:** สร้าง WHERE condition + params แล้วไม่ใช้ทุกตัว — asyncpg ตี type ไม่ได้เพราะ parameter ไม่อ้างถึง
- **Correct Pattern/Solution:** สร้าง dynamic WHERE + params **พร้อมกันเฉพาะ branch ที่ใช้** (ไม่สร้างล่วงหน้าแล้วทิ้ง); ก่อน `conn.fetch(sql, *params)` ตรวจ `sql.count('$') == len(params)` คร่าวๆ; พอเจอ 500 ดู traceback บรรทัด fetch แล้วไล่ count parameter
- **Date Added:** 2026-08-08

### 🛠️ RBAC — แยก `require_permission` (ระดับห้อง) vs `require_permission_anywhere` (ข้ามห้อง)
- **Context/Problem:** ตอนแรก define `require_permission` ซ้ำใน router (hacky) — ต้องย้ายไป core และแยกความหมาย 2 แบบ
- **Root Cause:** สิทธิ์ระดับโรงเรียน (MANAGE_STUDENTS, VIEW_DASHBOARD) ไม่ผูกกับห้องเดียว — เช็ค `require_permission(conn, room_id, ...)` จะ fail เพราะไม่มี room ที่ตรง
- **Correct Pattern/Solution:**
  1. `core/rbac.py`: `require_permission(conn, room_id, user_id, perm)` — ระดับห้อง (ดู is_admin/permissions ใน students ของห้องนั้น)
  2. `require_permission_anywhere(conn, user_id, perm)` — วนทุก membership ที่ active, is_admin ผ่าน, มี perm ใน role ไหนก็ผ่าน
  3. Router import จาก core เสมอ — **ห้าม** re-define helper ใน router
- **Date Added:** 2026-08-08

### 🛠️ Role → Permissions ต้องมาจาก config/roles.json (ไม่ hardcode ใน DB)
- **Context/Problem:** ตอนแรกทุกคน permissions ว่าง → frontend ซ่อนเมนูไม่ได้ (Dashboard โผล่ให้ทุกคนแม้เด้ง)
- **Root Cause:** register/import/seed ไม่ได้ตั้ง `students.permissions` ตามตำแหน่ง
- **Correct Pattern/Solution:**
  1. `core/rbac.get_role_permissions(role)` อ่าน `config/roles.json` (`roles[role].permissions`) แล้วแคชครั้งแรก
  2. ทุกจุดที่ create/update student (register_user, import Excel, seed) ต้องตั้ง `permissions = json.dumps(get_role_permissions(class_role))`
  3. frontend ใช้ `authStore.hasPermission(...)` + `isAdmin` เพื่อซ่อนเมนู และ router `meta.requiresPermission` guard กันเข้า URL ตรง
- **Date Added:** 2026-08-08

### 🛠️ Pyramid Escalation — visibility "มองลง" ไม่ใช่แค่ระดับตัวเอง
- **Context/Problem:** ตอนแรกหน้า "เรื่องที่รับ" โชว์แค่ระดับตัวเอง; ตาม requirement ระดับสูงควรเห็นทุกระดับล่าง (พีระมิด) + กรองระดับได้
- **Correct Pattern/Solution:**
  1. `LEVEL_RANK = {"student":0,"room":1,"level":2,"council":3}` — student เป็นระดับต่ำสุด (ใช้ `.index()` กับ list ที่ไม่มี student → ValueError)
  2. `can_see(level, issue_level, reporter_id, user_id, is_anonymous)` — ระดับสูง ≥ ระดับเรื่อง = เห็น; ผู้แจ้งเห็นเรื่องตัวเองเสมอ (แม้ anonymous — anonymity ซ่อนชื่อคนอื่น ไม่ใช่ซ่อนจากเจ้าของ)
  3. Query ใช้ `CASE i.current_level WHEN 'room' THEN 1 ...` เปรียบเทียบตัวเลข (ห้ามเปรียบเทียบ string lexicographic)
  4. "เรื่องที่เกี่ยวข้อง" (เคยรับ/escalate จากห้องตัวเอง) ต้องเห็นแม้โดนส่งขึ้นไปแล้ว — เช็คผ่าน `issue_escalations.from_assignee_id` / `issue_countdowns.assignee_id`
- **Date Added:** 2026-08-08

### 🛠️ start_level — ผู้แจ้งระดับสูงเลือกเริ่มต้นเรื่องที่ระดับสูงขึ้นได้
- **Context/Problem:** หัวหน้าห้อง/ประธานระดับ/สภาที่เป็นคนแจ้ง ไม่อยากแจ้งแล้วค่อยกดส่งต่อ — อยากเลือกเริ่มที่ระดับสูงได้เลย
- **Correct Pattern/Solution:**
  1. `create_issue(..., start_level="room")` — default room
  2. Validate: ถ้า start_level != room → เช็ค `user_level(user) >= start_level` ไม่งั้น 403 (นักเรียนส่งขึ้นสภาไม่ได้)
  3. บันทึก `issue_escalations` (from room → start_level) เป็นประวัติด้วย + status_history note "ผู้แจ้งเลือกเริ่มต้นที่ระดับนี้โดยตรง"
  4. frontend: `selectableLevels` (ตั้งแต่ room ถึงระดับตัวเอง) โชว์เฉพาะผู้มีระดับสูงกว่า student
- **Date Added:** 2026-08-08

### 🛠️ รหัสผ่านเริ่มต้น = เลขรหัสนักเรียน (ไม่ใช่ 1234 เหมือนกัน)
- **Context/Problem:** ต้องการให้รหัสเริ่มต้นต่างกันต่อคน = เลขรหัสนักเรียน; หน้า import เดิมมีช่อง "รหัสผ่านเริ่มต้น" ให้กรอก
- **Correct Pattern/Solution:**
  1. import Excel + seed: `initial_password = student_id` (แล้ว hash) — ถ้า default_password ถูก override (ไม่ใช่ 1234) ค่อยใช้ค่านั้น
  2. ลบช่อง "รหัสผ่านเริ่มต้น" ใน UI (ไม่จำเป็น) — hint บอก "รหัสผ่านเริ่มต้น = เลขรหัสนักเรียน"
  3. มี `POST /api/auth/change-password` (ตรวจ old password ด้วย bcrypt verify) ให้เปลี่ยนได้ที่หน้าโปรไฟล์
- **Date Added:** 2026-08-08

### 🛠️ สถานะ `cancelled` — ผู้แจ้งยกเลิกเรื่องได้ (กันส่งผิด)
- **Context/Problem:** ต้องการให้ผู้แจ้งยกเลิกเรื่องที่ส่งผิด/ไม่ต้องการได้
- **Correct Pattern/Solution:**
  1. `cancel_issue(pool, user_id, issue_id, reason)` — ต้องเป็น reporter_id หรือ admin; ถ้า status=resolved ยกเลิกไม่ได้; set status='cancelled' + insert status_history
  2. frontend: `IssueStatus` union ต้องเพิ่ม `'cancelled'` (ไม่งั้น TS `this comparison appears unintentional`) + `STATUS_LABELS` + statusColor
  3. หน้า "เรื่องที่รับ" default filter = "ยังไม่เสร็จ" (ตัด resolved+cancelled) — ใช้ status='not_resolved' pseudo-value แล้ว filter ฝั่ง client
- **Date Added:** 2026-08-08

### 🛠️ MyProfile — GET/PATCH `/students/me/profile` + user/student/room join
- **Context/Problem:** หน้าโปรไฟล์ต้องดู+แก้ไขข้อมูลตัวเอง (prefix/ชื่อ/นามสกุล/ชื่อเล่น/เบอร์/email)
- **Correct Pattern/Solution:**
  1. `get_my_profile`: join students + users + rooms ตาม user_id (LIMIT 1 กันหลายห้อง)
  2. `update_my_profile`: แก้ students (ชื่อ/prefix/nickname) + users (full_name/phone/email) — dynamic SET เฉพาะ field ที่ส่ง; อัปเดต full_name ใหม่ตอนชื่อเปลี่ยน
  3. หลังแก้เสร็จต้อง `authStore.loadMe()` เพื่อ refresh display name ใน sidebar
- **Date Added:** 2026-08-08

### 🛠️ Frontend theme แดง — sed แทนที่สี + แยก semantic สี
- **Context/Problem:** เปลี่ยน theme น้ำเงิน → แดง (โลโก้โรงเรียนแดง); ใช้ sed `s/blue-N/red-N/g` แต่มันทับสีสถานะ (in_progress/escalated กลายเป็นแดงหมด)
- **Correct Pattern/Solution:**
  1. sed แทนที่สีหลักก่อน (blue→red, indigo→rose) — เร็ว แต่ระวังทับ semantic
  2. แล้วแก้ semantic กลับด้วยมือ: `in_progress`=blue, `escalated`=orange, `resolved`=green, `cancelled`=gray; ระดับ: room=emerald, level=amber, council=rose
  3. หลักการ: **สีแบรนด์ (ปุ่ม/head/brand) ใช้ red, สีสถานะแยก semantic** — อย่าให้ปุ่มกับ badge สีเดียวกันหมด
- **Date Added:** 2026-08-08

### 🛠️ Vue Router Transition — ครอบเฉพาะ content ไม่ใช่ทั้ง layout
- **Context/Problem:** animation "บัคๆ" ไม่เห็น fade — ตอนแรกครอบ `<Transition mode="out-in">` ทั้ง `<RouterView />` ใน App.vue → sidebar กระตุก + หน้าเก่าหายก่อนใหม่มา
- **Correct Pattern/Solution:**
  1. App.vue: `<RouterView />` ตรงๆ (เป็นแค่ shell) — อย่าใส่ transition ที่ครอบทั้ง layout
  2. MainLayout: ครอบ `<RouterView v-slot="{ Component }">` ด้วย `<Transition name="page" mode="out-in" appear>` + `<component :key="route.fullPath">` — animate เฉพาะ content, sidebar นิ่ง
  3. CSS: `.page-enter-active { transition: opacity .35s cubic-bezier(.4,0,.2,1), transform .35s }`, `.page-enter-from { opacity:0; transform: translateY(20px) }` — `mode="out-in"` ต้องให้ enter ช้า/leave เร็ว ไม่งั้นรู้สึกหน่วง
  4. `appear` ให้ animate ครั้งแรก (login→หน้าแรก) ด้วย; list ใช้ `<TransitionGroup name="list">`
- **Date Added:** 2026-08-08

### 🛠️ Pytest integration — pattern test_db_url + client ชี้ settings
- **Context/Problem:** ตอนแรก conftest ใช้ `db_pool` session-scoped → event loop mismatch (`Task attached to a different loop`) ตอน async fixtures
- **Correct Pattern/Solution:**
  1. `test_db_url` (session): สร้าง DB สุ่มชื่อ (`test_db_{uuid}`) ผ่าน sys db → `init_db` → yield URL → drop ตอนจบ
  2. `client` (function): เปลี่ยน `settings.DATABASE_URL = test_db_url` ก่อน `with TestClient(app)` แล้วคืนค่า — pydantic-settings v2 assign field ได้
  3. `clean_database` (function autouse): TRUNCATE master tables CASCADE
  4. test functions เป็น `async def` + `@pytest.mark.asyncio` ใช้ fixtures — อย่าใช้ `run_until_complete` กับ sync client ปนกัน
- **Date Added:** 2026-08-08

### 🛠️ Docker test port ชน — ใช้ port ที่ไม่ซ้ำกัน
- **Context/Problem:** `docker-compose.test.yml` ใช้ host port 5433 → ชนกับ `classroom_test_postgres` ของโปรเจคอื่น (Bind for port already allocated)
- **Correct Pattern/Solution:** ใช้ port เฉพาะโปรเจค (5435) + conftest `DATABASE_URL` ชี้ port นั้น; ถ้ารันหลายโปรเจคบนเครื่องเดียว ตรวจ `docker ps` ก่อนเลือก port
- **Date Added:** 2026-08-08

### 🛠️ Migration file — placeholder หมายเลขต้องเลื่อนตาม parameter ที่มาก่อน
- **Context/Problem:** migration 001 (รื้อหมวดหมู่) พังตอนรัน: `InterfaceError: the server expects 5 arguments for this query, 6 were passed` — query มี `$1` (main_category) แล้วใช้ `NOT IN ($1,$2,$3...)` ที่เริ่มหมายเลข `$1` ใหม่ → ซ้ำกับ parameter ตัวแรก + count เกิน
- **Root Cause:** สร้าง placeholder ของ dynamic list ด้วย `f"${i+1}"` โดยไม่นับ parameter ที่ถูก `$1` จองไว้ก่อนหน้าใน query เดียวกัน
- **Correct Pattern/Solution:** เมื่อ query มี parameter มาก่อนแล้ว (เช่น `$1`), placeholder ของ dynamic list ต้องเริ่มที่ `$2` → `f"${i+2}"`; ตรวจเสมอว่า `sql.count('$') == len(params)` ก่อนรัน (บทเรียนเดียวกับ IndeterminateDatatypeError)
- **Date Added:** 2026-08-16

### 🛠️ Role school-wide (admin/ครูสภา) — room_id = NULL ต้องใช้ LEFT JOIN + user_level คืน council
- **Context/Problem:** ครูสภา/แอดมิน ไม่ผูกห้อง (room_id NULL) → (1) `get_user_roles` ใช้ INNER JOIN rooms → role หายจาก login (ไม่มีห้อง); (2) `user_level` ให้ `ROLE_LEVEL.get("teacher_council", "student")` = "student" → มองเห็นแค่เรื่องตัวเองใน list ทั้งที่ต้องเห็นทุกเรื่อง
- **Root Cause:** สมมติว่าทุกคนต้องมีห้อง; role ใหม่ (teacher_council/admin) เป็น school-wide ไม่มี room → join ทิ้ง row + ระดับกลายเป็น student
- **Correct Pattern/Solution:**
  1. `get_user_roles`: เปลี่ยน JOIN rooms → **LEFT JOIN** + `AND (r.id IS NULL OR r.deleted_at IS NULL)` — คนไม่มีห้องยังได้ role
  2. `user_level`: เช็ค `roles` ที่เป็น `admin/teacher_council/council_president` → คืน `"council"` ก่อน (ไม่เข้า ROLE_LEVEL lookup)
  3. Import Excel: admin/ครูสภา = `school_wide = class_role in ("admin","teacher_council")` → room_id=NULL, ครูทั่วไป = staff_level จากระดับชั้นห้อง
  4. `get_access_scope` (core/rbac): scope 'all' สำหรับ is_admin/teacher_council/admin/council_president, scope 'level' สำหรับ teacher (มี staff_level)
- **Date Added:** 2026-08-16

### 🛠️ ครูทั่วไป (teacher) — scope ระดับชั้นแยกจาก permission check
- **Context/Problem:** ครูทั่วไปมี MANAGE_STUDENTS/VIEW_DASHBOARD เหมือน admin (ตาม roles.json) → ต้องเห็น/จัดการได้แค่ระดับชั้นตัวเอง (ครู ม.4 ดูแลแค่ ม.4) แต่การเช็ค permission อย่างเดียวไม่พอ
- **Correct Pattern/Solution:**
  1. `staff_level` (เช่น 'ม.4') บน students — ครูทั่วไปมี, ครูสภา/แอดมินเป็น NULL
  2. แยก 2 ชั้น: `require_permission_anywhere` (มีสิทธิ์ไหม) → `get_access_scope` / `_teacher_scope` (ขอบเขตข้อมูลระดับไหน) — router ผ่าน `level`/`allowed_level` ไป service
  3. `issue_service`: `_teacher_scope` → `_level_room_ids` → list/get/accept จำกัด room level; `_can_manage_issue` ให้ครูระดับชั้นเรื่องจัดการเรื่องได้แม้ไม่ใช่ผู้รับ
  4. `dashboard_service`: ใส่ `level_where = " AND r.level = $1"` ทุก query (JOIN rooms) เมื่อ scope = level
  5. test: สร้างเรื่อง ม.4 + ม.5 → ครู ม.4 เห็น/รับเรื่อง ม.4 ได้, ม.5 ต้อง 403; ครูสภา/แอดมินเห็นทั้งสอง
- **Date Added:** 2026-08-16

### 🛠️ Dashboard scope — ครูที่ยังไม่มี staff_level ต้องเป็น scope 'none' ไม่ใช่ 'pyramid'→'all'
- **Context/Problem:** `get_access_scope` ตอบ 'pyramid' สำหรับทุกคนที่ไม่ใช่ admin/ครูสภา/ครูที่มีระดับชั้น → dashboard แปลง 'pyramid' เป็น 'all' (ทั้งโรงเรียน) เพื่อให้ council_member ดูได้ แต่ครูที่สมัครโดยไม่ระบุห้อง (`staff_level` NULL — register_user ตั้ง None) ตกเงื่อนไขเดียวกัน → เห็นข้อมูลทั้งโรงเรียนทั้งที่ควรเห็นแค่ระดับชั้นตัวเอง (สิทธิ์สูงเกิน)
- **Root Cause:** scope 'pyramid' ใช้ร่วมกันระหว่าง council_member (ดูได้ทั้งโรงเรียนจริง) กับครูที่ยังไม่ตั้งระดับ (ต้องไม่เห็นเลย) — แยกไม่ออกจาก scope ค่าเดียว
- **Correct Pattern/Solution:**
  1. `get_access_scope`: ถ้า role เป็น teacher แต่ `staff_level` ว่าง → คืน `{"scope": "none"}` (แยกจาก 'pyramid'); เช็คก่อนด้วยว่าไม่มี membership อื่นที่ให้ scope สูงกว่า
  2. `dashboard_service`: `_scope_clause('none')` → `" AND 1 = 0"` (ไม่เห็นเรื่อง); `_count_people` ต้องมี branch `scope == "none"` → (0,0) — อย่าลืม helper ตัวรอง (ตอนแรกคิดว่ามีแค่ 2 branch แล้ว test จับได้ว่าจำนวนนักเรียน/ห้องยังรั่ว)
  3. frontend: รองรับ `scope === 'none'` แสดง banner "ยังไม่ได้กำหนดระดับชั้น" แทน "ภาพรวมทั้งโรงเรียน"
- **Date Added:** 2026-08-16

### 🛠️ Deep-DB verify ใน test — ห้าม copy query service ตรงๆ + ต้องสร้าง scenario ที่ทำให้ rule มองเห็นได้
- **Context/Problem:** test overdue ตรวจ DB ด้วย query ที่ copy จาก service แทบทั้งดุ้น (`cd.id = (SELECT MAX(id)...)`) → regression ที่ลบเงื่อนไข "latest countdown เท่านั้น" ออก (นับ countdown ไหนก็ได้ที่เกิน) จะยังผ่านเพราะทุกเรื่องมี countdown แค่ 1 แถว
- **Root Cause:** ตรวจ "ด้วยวิธีเดียวกัน" ไม่ใช่ "ตรวจอิสระ" + ไม่มีข้อมูลที่แยกความต่างของกฎออกมา
- **Correct Pattern/Solution:**
  1. เขียนการตรวจอิสระด้วยรูปแบบที่ต่างกัน เช่น service ใช้ `EXISTS + MAX(id)` → test ใช้ correlated `(SELECT deadline FROM issue_countdowns ... ORDER BY id DESC LIMIT 1) < NOW()`
  2. สร้าง scenario ที่ทำให้กฎ "มองเห็นได้": ให้เรื่องหนึ่งมี countdown 2 แถว — อันเก่าเลยกำหนด + อันใหม่ยังไม่เกิน (ยืดเวลา) → ต้อง NOT overdue; ถ้า implementation นับ "มี countdown ไหนเกินก็ได้" เรื่องนี้จะติดเป็น overdue ให้ test จับได้
  3. trend อย่า assert `trend[-1]['count'] == N` (ข้ามเที่ยงคืน Asia/Bangkok แล้ว flaky — เรื่องที่สร้างก่อนเที่ยงคืนตกไปอยู่วันก่อน) → ใช้ `sum(t['count'] for t in trend) == N`
- **Date Added:** 2026-08-16

### 🛠️ Dashboard หลาย query รวมหมวดเดียว — ตัวเลขระดับบนต้องรวมจาก key set เดียวกับหมวดย่อย
- **Context/Problem:** `total_issues`/`pending/...` คำนวณจาก `by_status_all` ที่รวมทุก row ที่ query คืนมา แต่ `main_categories[].total` + `recent_issues` + `top_subcategories` รวมจากเฉพาะ `category_codes` ใน config → ถ้ามี row ที่ `main_category` อยู่นอก config (หมวดเก่าที่ถูกลบ, ตัด space ผิด, insert ตรง) ตัวเลข top-level กับรายหมวดไม่ตรงกัน (sum ของ pending+... != total)
- **Correct Pattern/Solution:** สร้าง aggregate ทั้งหมดจาก key set เดียวกัน — `total_by_main` และ `by_status_all` ต้อง loop เฉพาะ `category_codes` (`by_main_status.get(mc, {})`) เหมือนกับที่หมวดย่อย/เรื่องล่าสุดทำ; หรือเพิ่ม CHECK constraint ที่ `issues.main_category`
- **Date Added:** 2026-08-16

### 🛠️ `str(None)` ใน Python = `"None"` (truthy!) — ตอนแปลงค่าเซลล์ว่างจาก Excel ต้อง `or ""` เสมอ
- **Context/Problem:** `student_id = str(_get(row, idx, "รหัสนักเรียน")).strip()` — ถ้าเซลล์ว่าง `_get` คืน `None` → `str(None)` = `"None"` ซึ่ง truthy → `if not student_id` ไม่เด้ง → import แถวที่ไม่มีรหัสนักเรียนเข้าไปเป็น user ชื่อ "None" (test จับได้: imported=3 ทั้งที่ควรเป็น 2)
- **Root Cause:** ลืมว่า `str(None)` ไม่ได้คืน string ว่าง; pattern `str(x or "")` ใช้กันในไฟล์เดียวกัน (first_name/nickname) แต่ 2 จุด (student_id, room_code) ใช้ `str(x)` ตรงๆ
- **Correct Pattern/Solution:** ใช้ `str(_get(...) or "").strip()` ทุกจุดที่แปลงค่าที่อาจเป็น `None`; และ error ต่อ row ต้องมีชื่อคอลัมน์ (เช่น "เลขที่ต้องเป็นตัวเลข (ได้ค่า: 'abc')") — ไม่ใช่แค่ `ข้อมูลผิดรูปแบบ/ซ้ำ (...)` ที่ไม่บอกว่า field ไหน
- **Date Added:** 2026-08-16

### 🛠️ asyncpg คืน `jsonb` เป็น **string** — ต้อง `json.loads` ก่อน `list()`
- **Context/Problem:** response ของ `GET /import-jobs` โชว์ `"error_logs":["[","]"]` — `error_logs` เป็นคอลัมน์ `JSONB NOT NULL DEFAULT '[]'::jsonb` แต่ asyncpg คืนค่าเป็น string `"[]"` (ไม่ใช่ list) → `list("[]")` แยกเป็น `['[', ']']`
- **Root Cause:** asyncpg ไม่ parse `jsonb` เป็น Python object ให้อัตโนมัติ (ต้องลง codec เอง); test ที่อ่านเองใช้ `json.loads(job["error_logs"])` เป็นสัญญาณว่า column นี้คืน string
- **Correct Pattern/Solution:** เมื่อจะ `list()` ค่า JSONB ที่ asyncpg คืนมา ให้เช็คก่อน: `if isinstance(raw, str): raw = json.loads(raw)` (wrap try/except → `[]`); แล้วค่อย `list(raw or [])` — ใช้ได้ทั้ง DB จริง (string) และ mock (list)
- **Date Added:** 2026-08-16

### 🛠️ Fixture ที่เรียก `register_user` จะสร้าง user + student row ด้วย — นับ count ต้อง scope ด้วย ID
- **Context/Problem:** test `reimport` assert `users == 1` หลัง import แต่ได้ 2 — `admin_user` fixture เรียก `register_user` ซึ่งสร้างทั้ง user และ student ของ admin → count รวม fixture เข้าไปด้วย
- **Root Cause:** เข้าใจว่า fixture สร้างแค่ "สิทธิ์" แต่จริงๆ สร้าง record จริงในตาราง; test ที่ assert `count(*)` รวม row ของ fixture
- **Correct Pattern/Solution:** assert แบบ scope เฉพาะเป้าหมายเสมอ เช่น `SELECT count(*) FROM users WHERE username = '47001'` / `WHERE student_id IN (...)`, หรือ `JOIN rooms` ให้กรอง row ที่ `room_id IS NULL` ออก (กรณี fixture ระดับโรงเรียน); ระวัง `VARCHAR(10)` ของ `students.student_id` ด้วย — `f"ID{username}"` เกิน 10 ตัว → `StringDataRightTruncationError`
- **Date Added:** 2026-08-16

### 🛠️ Frontend `as` cast — inline `(await api.get()) as X` ผ่าน type-check แต่ `const res = await ...; res as X` เด้ง TS2352
- **Context/Problem:** `npm run type-check` ฟ้อง `TS2352: Conversion of type 'AxiosResponse<...>' to type 'Room[]'` เฉพาะที่เขียน `const res = await api.get(...); return res as Room[]` — แต่ `issue.ts` ที่เขียน `(await api.get(...)) as Issue[]` inline ผ่าน และ test probe (inline) ก็ผ่าน
- **Root Cause:** `services/api.ts` เป็น axios instance ธรรมดา (type ยังเป็น `Promise<AxiosResponse>`) มี interceptor ปลด `response.data` ตอน runtime เท่านั้น; TS เปรียบเทียบ `AxiosResponse` กับ array type ต่างกันตามตำแหน่งการ cast (empirical — โปรเจคนี้ inline cast ผ่านเสมอ)
- **Correct Pattern/Solution:** cast inline ทันทีใน expression: `return (await api.get('/api/rooms')) as Room[];` — อย่า assign ตัวแปรคั่นก่อน cast; `as unknown as X` ก็ใช้ได้เสมอแต่ไม่สวย; ถ้าสงสัยว่าไฟล์อื่นพังไหมให้รัน `npx vue-tsc --noEmit -p tsconfig.app.json` (--build มี incremental cache — ลบ `node_modules/.tmp/tsconfig.app.tsbuildinfo` ก่อนถ้าต้องการ ground truth)
- **Date Added:** 2026-08-16

### 🛠️ ARQ + asyncpg — สถานะ QUEUED อย่า allow restart (กันยิงคิวซ้ำ) + ฝาก recovery ไว้ที่ worker startup
- **Context/Problem:** `RESTARTABLE_STATUS` เริ่มแรกมี QUEUED → กด "เริ่มงาน" 2 ครั้งบน job QUEUED ได้ 200 (enqueue ซ้ำ) — test `start twice → 409` จับได้
- **Root Cause:** ตั้งใจให้ restart ได้กรณี Redis หาย แต่เผลอเปิดช่อง double-enqueue race (worker อาจ claim ไปแล้ว)
- **Correct Pattern/Solution:** `RESTARTABLE_STATUS = {PENDING, FAILED}` เท่านั้น; กรณี job ค้างใน QUEUED ที่ Redis หาย ให้ `recover_stuck_jobs` (worker startup) ครอบ `status IN ('PROCESSING','QUEUED')` + `updated_at < NOW() - INTERVAL '35 minutes'` → reset QUEUED + re-enqueue; claim idempotent ด้วย `FOR UPDATE` + status check ทำให้ re-enqueue ซ้ำปลอดภัย
- **Date Added:** 2026-08-16

### 🛡️ Privilege escalation — อย่าอนุมานสิทธิ์จากค่าใน Excel ที่ uploader ส่งมา
- **Context/Problem:** worker นำเข้านักเรียนจาก Excel กำหนด `school_wide = class_role in ("admin", "teacher_council")` จาก cell "ตำแหน่งในห้องเรียน" ที่ uploader เขียนเอง → ครูระดับชั้น (allowed_level='ม.4') ส่งแถวที่มีตำแหน่ง "แอดมิน"/"ประธานสภา" → worker สร้างบัญชี is_admin=true ที่ควบคุมทั้งโรงเรียนได้ (privilege escalation) — review พบเป็น HIGH
- **Root Cause:** scope ของ uploader (มาจาก DB: `get_access_scope`) กับ role ในแถว Excel (มาจาก input ที่ปลอมแปลงได้) ถูกผสมกัน — ใช้ค่าที่ผู้ใช้ควบคุมเป็นตัวให้สิทธิ์
- **Correct Pattern/Solution:** สิทธิ์ต้องมาจากผู้ควบคุมข้อมูลเสมอ: (1) Router ตรวจ `scope == 'none'` → 403 (ครูที่ยังไม่มีระดับชั้น "นำเข้าทั้งโรงเรียน"); (2) `default_password` รับเฉพาะ `{"", "1234"}` เท่านั้น; (3) ใน `_process_single_row` ถ้า `allowed_level is not None` (uploader ระดับชั้น) → ปฏิเสธ role ใน `SCHOOL_WIDE_ROLES = {"admin","teacher_council","council_president","council_member"}`; สรุปง่าย: **allowed_level is None ⟺ uploader เป็น school-wide** (หลัง reject scope='none') — ใช้ค่าจาก DB ไม่ใช่จากไฟล์
- **Date Added:** 2026-08-17

### 🛠️ Batch insert พังกลางคัน (rollback) — snapshot ตัวนับก่อนลอง + เคลียร์ cache ที่มี phantom ID
- **Context/Problem:** worker ทยอย insert เป็น batch (1 transaction/chunk) แต่มี fallback ทีละแถวเมื่อ `asyncpg.PostgresError` → ตัวนับ `imported/skipped/errors` เพิ่มใน try ก่อน transaction commit → เมื่อ batch rollback ตัวนับยังค้าง (นับซ้ำ: imported=3 ทั้งที่จริง 2) + `ctx.room_cache`/`user_cache` เก็บ room/user id ที่ rollback ไปแล้ว (phantom ID) → fallback + batch ถัดไป insert ผิดที่ — review พบเป็น HIGH (double-count)
- **Root Cause:** ตัวนับเป็น side-effect ระหว่าง transaction ไม่ใช่ผลหลัง commit; cache ไม่รู้ว่า transaction ล้ม
- **Correct Pattern/Solution:** ก่อน `try` ให้ `snapshot = (imported, skipped, len(errors))` → ใน `except PostgresError` คืนค่า snapshot (คืน `imported, skipped` + `del errors[snapshot_len:]`) + `ctx.room_cache.clear()`/`ctx.user_cache.clear()` → แล้วค่อย fallback ทีละแถว; test จับได้โดยส่งแถวที่ทำให้ batch พัง (เช่น `room_code` ยาวเกิน VARCHAR(10) → `StringDataRightTruncationError`) แทรกกลาง chunk แล้ว assert imported ไม่นับซ้ำ
- **Date Added:** 2026-08-17

### 🛠️ Upsert student ให้ atomic ด้วย `ON CONFLICT` — แต่ partial unique index ไม่ชน NULL
- **Context/Problem:** SELECT-แล้ว-INSERT/UPDATE student ไม่อะตอมิก (2 งานชนกันสร้างแถวซ้ำ) → review แนะนำ partial unique index `(room_id, student_id) WHERE deleted_at IS NULL` + `INSERT ... ON CONFLICT (room_id, student_id) WHERE deleted_at IS NULL DO UPDATE` — แต่ Postgres **unique index ไม่ถือว่า NULL เท่ากัน** → แถว school-wide (room_id NULL) จะไม่ conflict และ reimport สร้างซ้ำ
- **Root Cause:** partial unique index บนคอลัมน์ที่อาจเป็น NULL → NULL แต่ละค่าเป็น "ต่างกัน" ในดัชนี
- **Correct Pattern/Solution:** แยก 2 กรณีใน `_process_single_row`: ถ้า `room_id is not None` → `ON CONFLICT ... DO UPDATE`; ถ้า `room_id IS NULL` (school-wide) → คง SELECT-แล้ว-INSERT/UPDATE เดิม (หรือใช้ index แบบ `NULLS NOT DISTINCT` ถ้า PG15+ — แต่กรณีนี้แยก path ง่ายกว่า); เพิ่ม index ใน `init_db` + migration 003 (idempotent: `CREATE UNIQUE INDEX IF NOT EXISTS`); test: reimport แอดมิน (room NULL) 2 รอบ → user/student ต้อง 1 ตัว
- **Date Added:** 2026-08-17

### 🛠️ Scope filter ตอน list/start — อย่าโชว์/เริ่มงานของคนอื่นให้ครูระดับชั้น
- **Context/Problem:** `GET /import-jobs` และ `POST /start-import-job` ตรวจแค่ MANAGE_STUDENTS ไม่กรองตาม access scope → ครู ม.4 เห็นงาน import ทั้งโรงเรียนของแอดมิน และ start งานที่ไม่ได้เป็นระดับตัวเองได้
- **Root Cause:** service รับแค่ `limit`/`job_id` ไม่รู้ scope ของผู้เรียก
- **Correct Pattern/Solution:** Router เรียก `get_access_scope` แล้วส่ง `access_scope`/`access_level` ไปให้ service: list → `WHERE allowed_level = $2` (level), `[]` (none); start → `ForbiddenError` ถ้า `scope=='none'` หรือ `job["allowed_level"] != access_level`; กฎทุกเลเยอร์: **สิทธิ์ของ user มาจาก DB (`get_access_scope`) ไม่ใช่จาก payload**
- **Date Added:** 2026-08-17

### 🛡️ Template ที่มีแถวตัวอย่าง = ช่องสร้าง account จริง — ต้อง guard ที่ชั้น import ไม่ใช่แค่เตือนในข้อความ
- **Context/Problem:** `build_template_xlsx_bytes` ใส่แถวตัวอย่าง (00001, 00002) ลง Sheet ข้อมูล — ครูดาวน์โหลด Template แล้วอัปโหลดทั้งไฟล์ (ไม่ลบแถวตัวอย่าง) → worker สร้าง user/student จริง + room อัตโนมัติ (ม.4/1, ม.4/2) โดย password เดาได้ = เลขรหัส (00001/00001) — review ยืนยันว่าถึงได้ (MEDIUM)
- **Root Cause:** `_process_single_row` ตรวจแค่ `student_id` ไม่ว่าง → แถว placeholder ผ่าน validation ทั้งหมด; ข้อความเตือน "ลบออกก่อนอัปโหลด" ไม่มีผลบังคับ
- **Correct Pattern/Solution:** กันที่ชั้น import: `_process_single_row` ปฏิเสธแถวที่ `student_id.startswith("000")` (คืน per-row error "รหัสขึ้นต้น 000 = แถวตัวอย่าง") — ครอบคลุมทั้ง Template ที่ดาวน์โหลดและไฟล์ที่เขียนมือ; ข้อความใน UI/คำแนะนำให้บอกว่า "ระบบข้ามแถว 000xx อัตโนมัติ" (ไม่ใช่แค่เตือนให้ลบ); **กฎ: สิ่งที่อยู่ในไฟล์ตัวอย่างต้อง import ผ่านไม่ได้เสมอ (defense in depth — อย่าพึ่งคำเตือน)**
- **Date Added:** 2026-08-17

### 🛡️ SweetAlert2 `html` = innerHTML — user data ต้อง escape (self-XSS)
- **Context/Problem:** `Swal.fire({ html: `ไฟล์ <b>${job.file_name}</b> ...` })` — `file_name` เป็นชื่อไฟล์จาก user ที่ backend สะท้อนกลับ verbatim (ไม่ sanitize) → ไฟล์ชื่อ `<img src=x onerror=...>.xlsx` (ถูกกฎหมายใน Linux/Mac) รัน script ตอนโชว์ dialog — review ยืนยัน (LOW, self-XSS เฉพาะคนอัปโหลด)
- **Root Cause:** SweetAlert2 แทรก `html` ผ่าน innerHTML/DOMParser โดยไม่ escape; Vue `{{ }}` escape เอง แต่ `html:` option ไม่
- **Correct Pattern/Solution:** มี helper `escapeHtml(value)` (replace `& < > " '`) ใช้ทุกจุดที่แทรก user data ลง `html:`; ถ้าไม่ต้องใช้ layout → ใช้ `text:` (Swal escape ให้); ใช้ `?? c` คืนค่าเดิมเมื่อ Record lookup ไม่เจอ — **กฎ: user input ทุกค่าที่เข้าออก backend (ชื่อไฟล์, ชื่อนักเรียน...) อย่า interpolate ลง html โดยไม่ escape**
- **Date Added:** 2026-08-17

### 🛠️ `URL.revokeObjectURL` หลัง `link.click()` ทันที — race กับ download async ของ browser
- **Context/Problem:** `handleDownloadTemplate` สร้าง blob URL → `link.click()` → revoke ทันที — browser ดาวน์โหลดแบบ async ถ้า revoke ก่อนจับ reference จะได้ไฟล์ 0 bytes/aborted (Firefox documented bug 1810828; FileSaver.js เลื่อน revoke ~40s) — review พบ
- **Root Cause:** revoke หลัง click ยังเร็วเกิน — `click()` เป็นแค่ "เริ่มต้น" กระบวนการดาวน์โหลด
- **Correct Pattern/Solution:** revoke แบบ defer: `setTimeout(() => URL.revokeObjectURL(url), 1000)` (คลิกยังอยู่ใน user gesture ทันที, revoke ทีหลัง); ถ้าต้องการชัวร์ ตรวจ `blob.size` ก่อนสร้าง URL — **กฎ: revoke blob URL ต้องหน่วงเสมอ ถ้าใช้แล้วทิ้ง**
- **Date Added:** 2026-08-17

### 🛠️ Legacy `.xls` (BIFF/OLE) — openpyxl อ่านไม่ได้ ต้องจำกัด `.xlsx` ทั้ง frontend + backend
- **Context/Problem:** UI ยอมรับ `.xls` (`accept=".xlsx,.xls"`, regex `\.(xlsx|xls)$`) → user เลือกไฟล์ .xls จริง ผ่าน gate → backend `endswith((".xlsx",".xls"))` ผ่าน → `openpyxl.load_workbook` อ่าน BIFF ไม่ได้ → 400 "อ่านไฟล์ Excel ไม่สำเร็จ" ทั้งที่ UI โฆษณาว่ารองรับ — review พบ
- **Root Cause:** เปิดช่อง `.xls` ไว้หลายจุด (frontend regex + accept + backend router) แต่ parser รองรับแค่ OOXML zip (.xlsx/.xlsm)
- **Correct Pattern/Solution:** จำกัด `.xlsx` อย่างเดียวทุกจุดที่จับ ext: regex `/\.xlsx$/i`, `accept=".xlsx"`, backend `endswith(".xlsx")` — **กฎ: อย่าให้ UI โฆษณารูปแบบที่ pipeline อ่านไม่ได้; เช็ค ext เป็นแนวเดียวกันทุกเลเยอร์**
- **Date Added:** 2026-08-17

### 🛠️ Short-polling กลืน error — progress bar ค้างเงียบ + empty state หลอก ต้องมี loadError + กัน poll วน
- **Context/Problem:** poll interval มี `catch {}` ว่าง → network หลุด: bar ค้างที่ 60% ไม่มีข้อความ (runningJobs ยังไม่ว่าง → poll วนไม่มีวันหยุด); `refreshJobs` ก่อนหน้ากลืน error → โชว์ "ยังไม่มีไฟล์ในคิว" ทั้งที่มีไฟล์จริง (ครูเห็นแล้วอัปโหลดซ้ำ = duplicate job) — review ยืนยัน (MEDIUM)
- **Root Cause:** ทุก catch เงียบ ไม่แยก "ไม่มีข้อมูล" กับ "อ่านข้อมูลไม่ได้"; ไม่นับความล้มเหลวต่อเนื่องของ poll
- **Correct Pattern/Solution:**
  1. แยก state: `loadError` (refresh/โหลดครั้งแรกพลาด) vs `isPollError` (poll ติดกันเกิน `POLL_FAIL_LIMIT=3`)
  2. `refreshJobs` สำเร็จ → เคลียร์ error + `pollFailStreak=0`; ไม่มีงานวิ่ง → `stopPolling()`; พลาด → `loadError=true` (เก็บรายการเดิมไว้ ไม่ลบ)
  3. `pollOnce()` แยกเป็น function — สำเร็จ reset streak; พลาด `streak++` แล้ว `isPollError=true` ถ้าเกินลิมิต (**ไม่หยุด poll** — พอ network กลับมา update เอง, แบนเนอร์หายเอง)
  4. Template: `v-else-if="loadError"` → error panel + ปุ่ม "ลองใหม่" (แทน empty state); empty state ต้องโชว์เฉพาะเมื่อ fetch สำเร็จจริงๆ
  - **กฎ: UI ที่มี state "ว่าง" ต้องแยกจาก state "อ่านไม่ได้" เสมอ; loop poll ต้องมีใน-flight guard + นับ failure**
- **Date Added:** 2026-08-17

### 🛠️ เซลล์ Excel ที่เป็นตัวเลข float (40000.0) — `str()` ได้ "40000.0" ต้องตัด `.0` ก่อนใช้เป็น identifier
- **Context/Problem:** import นักเรียนได้ `student_id = "40000.0"` (login ได้ด้วย 40000.0/40000.0) — ไฟล์ .xlsx ที่สร้างจากเครื่องมืออื่น (Excel/Google Sheets/macro) เก็บเลขรหัสเป็น `<v>40000.0</v>` ใน XML → `openpyxl._cast_number` (worksheet/_reader.py) เห็น `.`/`e` → คืน `float` (40000.0) → `str(40000.0)` = `"40000.0"`
- **Root Cause:** เขียน `str(cell or "").strip()` ตรงๆ — ไม่ได้คิดว่า cell เป็น float ที่ลงตัว; (openpyxl เขียน float 40000.0 เองจะ normalize เป็น int ตอน save → `make_xlsx_bytes` ปกติไม่เจอ bug นี้ ต้อง craft XML ให้เก็บ `<v>40000.0</v>` ถึงจะจำลองได้)
- **Correct Pattern/Solution:**
  1. helper `_cell_to_str(value)`: `None → ""`, `float ที่ is_integer() → str(int(value))`, นอกนั้น `str(value).strip()` — ใช้กับ `student_id`/`room_code` (identifier) แทน `str(x or "")`
  2. float ที่มีเศษ (40000.5) อย่า truncate — คืน `str(40000.5)` ตามเดิม (ข้อมูลผิด ปล่อยให้เห็นไม่ใช่ตัดทิ้งเงียบๆ)
  3. test: สร้าง xlsx แล้ว `zipfile` เข้าไปแก้ XML sheet — regex `(<c r="A\d+"...>)(<v>)(\d+)(</v>) → \1\2\3.0\4` เฉพาะคอลัมน์ A (อย่าแทน `<v>` ทั้งหมด — จะพัง shared-string index ของคอลัมน์ string); assert student_id == '40000' + login ผ่าน 40000/40000
  - **กฎ: ค่า identifier ที่อ่านจาก spreadsheet ต้องแปลงผ่าน "cell → string" ที่จัดการ float ลงตัวเสมอ; อย่า `str()` ตรงๆ**
- **Date Added:** 2026-08-17

### 🛠️ init_db ต้องรัน migrations ก่อนสร้าง index — ไม่งั้น DB เก่า crash-loop ตั้งแต่ startup
- **Context/Problem:** staging crash-loop ทุก replica ด้วย `UndefinedColumnError: column "main_category" does not exist` (init_db.py) — deploy schema ใหม่ (รื้อหมวดหมู่ → migration 001 เพิ่ม `issues.main_category`) ลงบน DB เดิม
- **Root Cause:** `init_db` สร้าง table + **index ทั้งหมดใน transaction เดียว** (รวม `idx_issues_main_category ON issues(main_category)`) แล้วค่อยรัน `run_migrations` ทีหลัง → DB เก่าที่ยังไม่มีคอลัมน์ crash ตอน `CREATE INDEX` ก่อน migration จะมีโอกาสเพิ่มคอลัมน์; symptom ที่น่ากลัวคือ API ทุกตัว "Not found" เพราะ backend เริ่มไม่ติด (ถึงมี route ก็รับไม่ได้)
- **Correct Pattern/Solution:** ลำดับใน init_db = `CREATE TABLE IF NOT EXISTS` → `run_migrations` → สร้าง index ที่อ้างคอลัมน์ (แยก index ออกเป็น block หลัง migrations); migration ทุกตัวเขียนให้ idempotent (`ADD COLUMN IF NOT EXISTS` / `CREATE TABLE IF NOT EXISTS` / `CREATE INDEX IF NOT EXISTS`) จึงรันซ้ำบน DB ใหม่ได้ปลอดภัย; **กฎ: คอลัมน์ที่เพิ่มผ่าน migration ต้องมีอยู่ก่อน statement ที่อ้างมัน (index/query) — ตรวจเส้นทาง upgrade DB เดิมด้วยเสมอ ไม่ใช่แค่ fresh install**; test regression: สร้าง DB ทิ้ง → สร้าง `issues` แบบไม่มี `main_category` → รัน `init_db` → assert คอลัมน์ + index ถูกสร้าง
- **Date Added:** 2026-08-17

### 🛠️ Rebrand เปลี่ยนชื่อโปรเจค (PRSC Portal → PIRIvoice) — แยก "ชื่อที่โชว์" กับ "identifier ที่ผูกข้อมูล"
- **Context/Problem:** rebrand โปรเจคครั้งใหญ่ ต้องไล่เปลี่ยนชื่อทุกจุด แต่บางตำแหน่งผูกกับข้อมูลจริง — เปลี่ยนผิดทีเดียว deploy แล้วข้อมูล "หาย" หรือเว็บ CORS พังเงียบๆ
- **Root Cause:** ชื่อเดียวกันซ้ำหลายชั้น (UI string / docs / package name / docker image / volume / DB name / CORS origin) แต่ความเสี่ยงต่างกัน — identifier ที่ persistent (volume ที่ services mount, DB name, domain) ไม่ใช่แค่เครื่องสำอาง
- **Correct Pattern/Solution:**
  1. **เปลี่ยนได้ทันที (ปลอดภัย):** display string ในหน้าเว็บ (index.html title/meta, sidebar, login, FastAPI title/description), docs/comments/docstring, package name (`package.json`+`package-lock.json` ต้องแก้คู่กัน), docker image name (แก้ให้ตรงกันทั้ง `pull_all.sh` + `docker-compose.app.yml` — rollback ยังทำงานเพราะ oh_shit deploy ผ่าน compose), container/DB name ของ test (throwaway), temp prefix
  2. **ผูกกับข้อมูลจริง → ระวัง:** named volume ที่ service mount อยู่ (เปลี่ยนชื่อ = Docker สร้าง volume ใหม่เปล่า ข้อมูลเก่าเหลือเป็น orphan — ถ้าจำเป็นให้ใช้ `external: true` + `name: <ชื่อเดิม>`), DB name ใน .env จริง (ต้อง `ALTER DATABASE` ไม่ใช่แค่แก้ตัวอักษร), CORS origins (โดเมนที่ deploy อยู่ถูกลบ → เว็บเก่าเรียก API ไม่ได้) — rebrand นี้เก็บโดเมนเก่าไว้ช่วงเปลี่ยนผ่าน + เพิ่มโดเมนใหม่ pirivoice.com
  3. **เจอ bug ซ่อนใน infra compose นี้:** services mount `${ENV_NAME}_postgres_data` แต่ `volumes:` section ประกาศ `prsc_staging_*`/`piri_staging_*` (ไม่ได้ถูก mount — dead) → ข้อมูลจริงอยู่ที่ volume ที่ Docker auto-create ชื่อ `staging_postgres_data`/`production_postgres_data` — อย่าเดาว่าข้อมูลอยู่ตามชื่อใน volumes section
  4. **คีย์เวิร์ดค้นหา:** index.html ต้องมี `<meta name="description">` + `<meta name="keywords">` (PIRIvoice / Pirivoice / เสียงจากชาวพิริยาลัย / ระบบรับฟังความคิดเห็นและปัญหา / สภานักเรียน) — และเก็บชื่อเก่าไว้ที่ readme ("เดิมชื่อ PRSC Portal") เพื่อให้ search คำเก่ายังเจอ
- **Date Added:** 2026-08-17

### 🛠️ Seed users (admin/ครูสภา/ประธานสภา) ตอนเปิดระบบครั้งแรก — username ยาว ≠ student_id VARCHAR(10) + bังคับเปลี่ยนรหัสครั้งแรก
- **Context/Problem:** ต้องการสร้างบัญชีผู้ดูแลระบบอัตโนมัติตอน `init_db`/startup ครั้งแรก ด้วย username เดายาก แล้วบังคับเปลี่ยนรหัสตอน login ครั้งแรก — แต่ `students.student_id` เป็น `VARCHAR(10)` (จำกัด 10 ตัว) ขณะที่ `users.username` เป็น `VARCHAR(100)`
- **Root Cause:** เข้าใจผิดว่า username กับ student_id ต้องเป็นค่าเดียวกัน → username ยาวๆ (`piri_admin_9f2k3c` = 17 ตัว) เกิน 10 ตัวของ student_id → INSERT พัง (หรือต้องสั้นจนเดาได้)
- **Correct Pattern/Solution:**
  1. **แยกค่า:** `users.username` (login, VARCHAR 100) = ยาวๆ เดายาก `piri_<role>_<hex6>`; `students.student_id` (identifier, VARCHAR 10) = สั้นๆ แยกกัน เช่น `PADM` + `secrets.token_hex(2).upper()` → แสดงในโปรไฟล์เป็น "รหัสนักเรียน"
  2. **idempotent:** ตรวจก่อน seed ว่า `students.class_role IN ('admin','teacher_council','council_president') AND status='active' AND deleted_at IS NULL` มีแล้วหรือยัง → มีแล้วข้าม (กันสร้างซ้ำตอน restart/test)
  3. **บังคับเปลี่ยนรหัส:** เพิ่มคอลัมน์ `users.must_change_password BOOLEAN DEFAULT FALSE` (migration `ADD COLUMN IF NOT EXISTS` + แก้ `CREATE TABLE` ใน init_db ให้ตรงกัน) → seed ตั้ง TRUE → `change_password` เคลียร์เป็น FALSE → frontend guard redirect ไปหน้าเปลี่ยนรหัส
  4. **Credentials:** เขียนไฟล์ (gitignored) + log ตอน startup; path จาก `settings.SEED_CREDENTIALS_FILE`
  - **กฎ: username (login) กับ student_id (identifier 10 ตัว) ไม่จำเป็นต้องค่าเดียวกัน; ฟีเจอร์ seed/boot ที่ idempotent ต้อง "เช็คมีแล้ว → ข้าม" ไม่ใช่ "INSERT ON CONFLICT" อย่างเดียว** (กรณี role ซ้ำกับ user ต่างกัน)
  - **เทส Gotcha:** `TestClient(app)` เปิด lifespan → seed รันก่อน test body → test ที่เรียก `seed_default_users` เองได้ `{}` (โดน skip) — **อย่าใช้ fixture `client` ใน test seed; สร้าง TestClient เองหลัง seed** (คุมคำสั่ง seed เองได้)
- **Date Added:** 2026-08-18

### 🛠️ Frontend mobile UX — iOS auto-zoom, dropdown โดน overflow-hidden ตัด, ตารางบนจอเล็ก
- **Context/Problem:** ปรับปรุงมือถือเจอ 3 บั๊ก/จุดหักมุม: (1) iOS Safari ซูมจอทุกครั้งที่แตะ input ที่ font < 16px; (2) dropdown เมนูที่วางใน container `overflow-hidden` โดนตัด (render ยาวเกิน parent); (3) ตาราง `<table>` บนจอแคบอ่านไม่รู้เรื่อง
- **Root Cause:** (1) iOS auto-zoom เป็นพฤติกรรมบังคับของช่องกรอกที่ font-size ต่ำกว่า 16px — Tailwind `text-sm` (14px) ตกทุกจุด; (2) CSS overflow clipping ใช้กับ container ที่มี dropdown อยู่ด้านใน; (3) ตารางหลายคอลัมน์ถูกบีบแนวตั้งบนความกว้างแคบ
- **Correct Pattern/Solution:**
  1. **iOS zoom:** ใน `main.css` เพิ่ม `@media (max-width:640px){ input,textarea,select { font-size:16px !important } }` — override `text-sm` เฉพาะมือถือ กัน zoom ทุกครั้งที่แตะ
  2. **Dropdown ถูกตัด:** แยกโครงสร้าง — container ที่ `overflow-hidden` ไว้เฉพาะพื้นหลัง/ลวดลาย (วงกลมตกแต่ง) ส่วนปุ่มเมนู + dropdown ย้ายไปอยู่ใน `<div class="relative">` ครอบนอก (ไม่โดน clip) + จัด z-index (overlay `z-20` ปิดเมนู อยู่ใต้ปุ่มเมนู `z-30`)
  3. **ตารางมือถือ:** dual layout — `md:hidden` = การ์ดรายการ (avatar/ชื่อ/ข้อมูล) + `hidden md:block` = `<table>` เดิมบนเดสก์ท็อป; ฟังก์ชัน action (เช่น เปลี่ยนตำแหน่ง) ใช้ร่วมกันได้
  4. **Filter row:** `grid grid-cols-1 sm:flex sm:flex-wrap` + select `w-full sm:w-auto` → บนมือถือเรียงแนวตั้งเต็มแถว ไม่เบียดกัน
  5. **ชื่อ/ข้อความล้น:** เติม `min-w-0` + `break-words` ที่ element ใน flex/grid (ชื่อคน, หัวข้อ) — กัน flex ตัดหรือกว้างเกินจอ
- **Date Added:** 2026-08-18

### 🛠️ Docker Swarm deploy — top-level volume key ใส่ `${ENV_NAME}` ไม่ได้ + `docker stack deploy` ไม่อ่าน `.env` เอง
- **Context/Problem:** เขียนสคริปต์ตั้งค่าระบบ (setup.sh) ให้ทุกชื่อ (network/stack/volume/image) อ้างอิงจาก `ENV_NAME` ใน `.env` — "เปลี่ยนชื่อแล้วรันใหม่ได้ทันที" — แล้วเจอ 2 กับดักตอนทำให้ compose ใช้ `${ENV_NAME}` ในชื่อ:
  1. ใส่ `${ENV_NAME}_postgres_data` ตรงๆ ใน `volumes:` section (เป็น key) → `docker stack config`/deploy พังด้วย `volumes additional properties '${ENV_NAME}_postgres_data' not allowed` (Compose ไม่ interpolate `${}` ที่ key ของ top-level `volumes` map)
  2. `.env` ใส่ `DATABASE_URL=...@${ENV_NAME}_infra_db:5432/...` แล้วคิดว่า compose/environment จะแทนค่าให้เอง → **`docker stack deploy` (และ `docker stack config`) ไม่อ่านไฟล์ `.env` เพื่อ interpolate** (ต่างจาก `docker compose config` ที่อ่าน) และ `env_file` ก็ส่งค่าดิบไปทั้ง `${...}` → container ได้ host ที่ผิด
- **Root Cause:** (1) compose-go interpolate ค่าใน yaml แต่ key ของ `volumes:` map ไม่ถูก interpolate เหมือนกันหมด → ต้องใช้ "key คงที่ + `name: ${ENV_NAME}_...`"; (2) stack deploy ใช้ shell environment ของ process ที่เรียก (คนที่ export `.env` มาก่อน) ไม่ใช่ `.env` ในโฟลเดอร์เอง
- **Correct Pattern/Solution:**
  1. **Volume ชื่อตาม env:** `volumes:` ใช้ key คงที่ (`postgres_data:`) แล้วตั้ง `name: ${ENV_NAME}_postgres_data` ข้างใต้ (services mount อ้าง key คงที่) — validate ผ่านทั้ง `docker stack config` และ `docker compose config`
  2. **DATABASE_URL/REDIS_URL ตาม env:** ไม่วางใจค่าใน `.env` — ไป override ใน compose `environment:` เช่น `DATABASE_URL=postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${ENV_NAME}_infra_db:5432/${POSTGRES_DB}` (compose interpolate ค่าของตัวเองได้)
  3. **สคริปต์ทุกตัวที่ deploy ต้อง export `.env` ก่อน** `docker stack deploy`: `set -a; . ./.env; set +a` (แทน `export $(grep -v '^#' .env | xargs)` ซึ่งพังถ้ามี trailing comment เช่น `# 30 days`)
  4. **เทสของจริง:** `ENV_NAME=x docker stack config -c <file>` เป็นตัว validate เดียวกับ `stack deploy` — ใช้ตรวจว่าชื่อ interpolate ถูกก่อน deploy; ตรวจว่า `docker stack deploy` รันจาก shell ที่ `.env` ถูก export แล้ว
  - **กฎ: ถ้าอยากได้ "ชื่อทุกอย่างตาม ENV_NAME" — ชื่อที่ dynamic ต้อง interpolate ที่ layer ของ compose (`environment:` / `name:`), ไม่อ้าง `${}` ภายในไฟล์ `.env`; และ deploy ทุกครั้งต้อง export .env ก่อน**
- **Date Added:** 2026-08-18

### 🛠️ CSS stacking — absolute z-auto ทับ in-flow (avatar โดน gradient cover ทับ = หน้าโปรไฟล์ "บัคๆ")
- **Context/Problem:** หน้าโปรไฟล์ (Profile.vue) avatar โดนดึงขึ้นมาซ้อน cover ด้วย `-mt-10 sm:-mt-14` แล้วดู "บัคๆ" — มีแถบคล้ำ/ด่างทับบน avatar ทั้งบน/กลาง/ล่าง ทั้งที่ตั้งใจให้ avatar อยู่หน้าสุด (ตรวจด้วย `document.elementFromPoint` ที่พิกัด avatar → คืน gradient overlay)
- **Root Cause:** ภายในการ์ด `bg-white ... overflow-hidden` มี element ตกแต่งเป็น `absolute` z-auto (วงกลม `bg-white/10` + แถบ `bg-gradient-to-t from-black/10`) อยู่ที่ cover; identity section (avatar+ชื่อ) เป็น in-flow (static) → **ตาม CSS painting order, positioned element (z-auto) วาดทับ in-flow content ที่มาทีหลังใน DOM เสมอ** → gradient/วงกลมจึงทับ avatar ที่ดึงขึ้นมาซ้อน (ยิ่ง gradient `from-black/10` ชัด เพราะเข้มจริง)
- **Correct Pattern/Solution:**
  1. ให้ section ที่ต้องอยู่บนสุดเป็น `relative z-10` (หรือ z บวก) — สร้าง stacking context ของตัวเองให้อยู่เหนือ element ตกแต่ง z-auto: `identity wrapper → <div class="relative z-10 px-4 sm:px-6 ...">` — avatar+ชื่อจะอยู่บนสุดเสมอ โดย gradient/วงกลมยังโชว์บน cover ตรงส่วนที่เหลือ
  2. จัด z-index เมนู ⋮/dropdown ให้สอดคล้องทั้งระบบ: overlay ปิดเมนู `fixed inset-0 z-40` (เหนือ header มือถือ z-30 → แตะที่ไหนก็ปิด; ใต้ dropdown z-50), wrapper เมนู `absolute z-50` — ไล่เลขตาม MainLayout (sidebar z-50, mobile overlay z-40, header z-30)
  3. **วิธีตรวจโดยไม่เห็นภาพ:** playwright `document.elementFromPoint(x,y)` + เปรียบเทียบ `getBoundingClientRect()` ว่าตรงไหนทับกัน แล้วดูว่า element ไหนเป็น topmost (เทียบ class) — หา bug "มี element ทับกัน" ได้แม่นกว่าการเดาจากโค้ด
  - **กฎ: ใน layout ที่ดึง element ด้วย margin ลบ/ซ้อนทับกัน ถ้าเห็นเงา/แถบ/element ตกแต่งวาดทับ content ให้สงสัย painting order ก่อน — element `position` ใดๆ (z-auto) จะทับ in-flow เสมอ ต้องเติม `relative z-*` ที่ content ที่ควรอยู่บนสุด**
- **Date Added:** 2026-08-18

### 🛠️ SPA หลังล็อกอิน — SEO/Google ต้องใส่เนื้อหาแนะนำไว้ที่หน้า Login + meta/JSON-LD ใน index.html
- **Context/Problem:** ทั้งเว็บเป็น SPA ที่ต้องล็อกอินก่อนเข้าถึง → Google ไม่มีหน้าสาธารณะให้ crawl เนื้อหา (dashboard/issues โดน guard หมด) — คำค้น "สภานักเรียน พิริยาลัย" ไม่เจอเว็บ
- **Root Cause:** หน้าเดียวที่เข้าได้ก่อนล็อกอินคือ `/login` ซึ่งเดิมเป็นแค่ฟอร์ม 2 ช่อง ไม่มีข้อความแนะนำ + `index.html` มีแค่ title/description สั้นๆ
- **Correct Pattern/Solution:**
  1. **หน้า login = หน้าแนะนำเว็บไซต์:** แบ่งเป็น 2 แผง (desktop `grid lg:grid-cols-2`) — แผงซ้าย gradient แดง = โลโก้ + "PIRIvoice คืออะไร/ทำอะไร" + จุดเด่น (แจ้งเรื่อง/ไต่ระดับ/นับถอยหลัง/dashboard) + ขั้นตอนทำงาน + คีย์เวิร์ดค้นหา (#tags) + ข้อมูลโรงเรียน/ที่อยู่; แผงขวา = ฟอร์มล็อกอิน (มือถือ `lg:hidden` แผงแนะนำมาก่อน ฟอร์มตาม)
  2. **`index.html` เต็มรูปแบบ:** `title` + `description` + `keywords` (ไทย+อังกฤษ รวมชื่อเก่า PRSC, พรส, piriyalai) + `canonical` + `robots: index,follow` + Open Graph (`og:url/image`) + Twitter Card + `JSON-LD` 2 บล็อก (`WebSite` + `EducationalOrganization` พร้อมที่อยู่) — ใส่ `lang="th"` และ `theme-color` แล้ว
  3. **`public/robots.txt`** (`Allow: /` + `Sitemap:`) + **`sitemap.xml`** (`/` priority 1.0, `/login` 0.8) — ไฟล์ใน `public/` ถูก copy ไป dist อัตโนมัติตอน build
  4. **กฎ: SPA ที่ข้อมูลหลังล็อกอิน — เนื้อหา SEO ที่ Google เห็นคือหน้า login + meta tag; อย่าทิ้งหน้า login ให้เป็นแค่ฟอร์มว่าง**
- **Date Added:** 2026-08-23

### 🛠️ สถานะ `rejected` (ถูกปัดตก) — ผู้ดูแลปัดตกต้องแยกหมวดจากผู้แจ้งยกเลิก (`cancelled`)
- **Context/Problem:** ตอนแรก `cancel_issue` ให้ทั้งผู้แจ้งและผู้ดูแล (ผู้รับ/admin/ครูระดับชั้น — `_can_manage_issue`) ตั้ง status='cancelled' ด้วย note default "ผู้แจ้งยกเลิกเรื่อง" → ครู/หัวหน้าห้องปัดตกเรื่อง ขึ้นไทม์ไลน์เหมือนผู้แจ้งยกเลิก (เข้าใจผิดว่าเป็นผู้แจ้งถอนเรื่องเอง) — requirement: ผู้ดูแลปัดตกต้องเป็นหมวดใหม่ "ถูกปัดตก"
- **Root Cause:** endpoint เดียว `/cancel` รับทั้ง 2 บทบาทแต่ไม่แยกผลตาม actor; ไทม์ไลน์ (IssueDetail) โชว์แค่ `h.note` ไม่โชว์ status
- **Correct Pattern/Solution:**
  1. **backend `cancel_issue`:** ถ้า `reporter_id == user_id` → status='cancelled' + note "ผู้แจ้งยกเลิกเรื่อง"; นอกนั้น (ผ่าน `_can_manage_issue`) → status='rejected' + note "ถูกปัดตก[: เหตุผล]" — แล้ว **คืน status จริง** เพื่อให้ router `return {"status": new_status}` ตรงกับที่เกิดขึ้น
  2. **เพิ่ม status ใหม่ครบทุกจุด:** dashboard `STATUS_LABELS`/`STATUS_ORDER` + summary `by_status_all.get("rejected", 0)` + `DashboardSummary.rejected` (pydantic + frontend interface); frontend `IssueStatus` union + `STATUS_LABELS`/`STATUS_DOT/BAR/BADGE/SHORT` (สี rose ต่างจาก cancelled เทา) + `statusColor` ใน MyIssues/ReceivedIssues + option filter ใน ReceivedIssues
  3. **frontend ปุ่มแยก:** `canCancel` (เฉพาะผู้แจ้ง) = "ยกเลิกเรื่อง" / `canReject` (canManage และไม่ใช่ผู้แจ้ง) = "ปัดตก" — ปุ่มเดียว `v-if="canCancel || canReject"` แล้วป้าย/ข้อความยืนยันตาม `isReporter`; ทั้งคู่เรียก `/cancel` เดิม (backend ตัดสิน status จาก actor)
  4. **ไทม์ไลน์:** เพิ่ม chip สีแสดง `STATUS_LABELS[h.status]` ต่อรายการ status_history — ให้เห็นชัดว่าจุดไหน "ถูกปัดตก" ไม่ต้องเดาจาก note อย่างเดียว
  - **กฎ: ถ้า endpoint หนึ่งรองรับหลายบทบาทที่ควรได้ผลต่างกัน อย่า hardcode status ใน router — ให้ service ตัดสินจาก actor แล้วคืนค่าจริง; เวลาเพิ่ม status ใหม่ ไล่ grep `cancelled` ทั้ง frontend+backend (labels/colors/filter/dashboard/test) ให้ครบก่อน**
- **Date Added:** 2026-08-23

### 🛠️ PATCH แก้ไขเรื่อง + คอมเมนต์ — dynamic SET ต้องจอง `$1` ไว้ WHERE, ชื่อ snapshot ต้อง fallback users.full_name, ตารางใหม่ต้องเข้าครบ 3 ที่
- **Context/Problem:** เพิ่มฟีเจอร์ (ก) ผู้แจ้งแก้ไขเรื่อง (`PATCH /api/issues/{id}`) และ (ข) คอมเมนต์แบบ YouTube (`issue_comments` + CRUD ของตัวเอง) — เจอ 3 จุดที่พังถ้าไม่ระวัง: asyncpg parameter numbering, ชื่อ snapshot ว่าง, และ schema ใหม่หลุดจาก test isolation
- **Root Cause:**
  1. **asyncpg Ambiguous/Indeterminate:** dynamic `UPDATE ... SET` ต้องไม่ reuse `$1` ข้าม type และต้องไม่มี param ค้างที่ไม่ได้ใช้ (มีบทเรียน AmbiguousParameterError/IndeterminateDatatypeError แล้ว) — วิธีคือจอง `$1` ไว้ `WHERE id` แล้ว field แต่ละตัวใช้ `len(params)+1` ก่อน `append`
  2. **`CONCAT_WS(' ', prefix, first_name, last_name)` กับแถวที่ชื่อว่าง:** register_user/self-signup เก็บชื่อไว้ที่ `users.full_name` แต่ `students.first_name/last_name` เป็น `''` → `CONCAT_WS` ได้ `' '` (space) — `NULLIF(..., '')` จับไม่ออกเพราะไม่ใช่ `''` → ต้อง `TRIM` ก่อน `NULLIF` แล้ว fallback `users.full_name`
  3. **ตารางใหม่หลุด test isolation:** เพิ่ม `issue_comments` ใน init_db + migration แต่ลืม conftest `TRUNCATE` → คอมเมนต์รัวข้าม test (deep-DB count ผิดเงียบๆ)
  4. **asyncpg คืน jsonb เป็น string:** เทสที่อ่าน `audit_logs.old_values['title']` ต้อง `json.loads` ก่อน (มีบทเรียนเดิม) — `audit["old_values"]["title"]` = `TypeError: string indices`
- **Correct Pattern/Solution:**
  1. **Dynamic SET:** `params = [issue_id]` → `sets.append(f"col = ${len(params)+1}"); params.append(value)` → สุดท้าย sanity check `sql.count('$') == len(params)`; `updated_at = NOW()` ไม่มี param ไม่กระทบเลข
  2. **ชื่อแสดง:** `NULLIF(TRIM(CONCAT_WS(' ', s.prefix, s.first_name, s.last_name)), '') AS student_name` + `JOIN users u` → ในโค้ด `c["student_name"] or c["full_name"]`; ใช้ `SELECT ... FOR UPDATE` บนแถว issue ตอนเช็คสถานะปิด (กัน TOCTOU กับ resolve/cancel)
  3. **ตารางใหม่ = เข้าครบ 3 ที่:** init_db (`CREATE TABLE IF NOT EXISTS`) + `migrations/00X_*.py` (`CREATE TABLE IF NOT EXISTS` + index) + `conftest.py` TRUNCATE list — สามที่ต้องมีครบ
  4. **authorization:** แก้เรื่อง = `reporter_id == user_id` หรือ admin (`_is_admin`); คอมเมนต์ = ใครเห็นเรื่องได้ (`_assert_can_view` = visibility เดียวกับ `get_issue`) + แก้/ลบเฉพาะ `user_id` ของตัวเอง
  - **กฎ: (1) dynamic PATCH ต้อง `model_dump(exclude_unset=True)` + จอง `$1` WHERE แล้ว field เริ่ม `len(params)+1`; (2) snapshot ชื่อจาก students ต้อง TRIM + fallback users.full_name เพราะ first/last name ว่างได้; (3) schema ใหม่ต้องเข้าทั้ง init_db + migration + conftest TRUNCATE; (4) เทส audit jsonb ต้อง json.loads**
- **Date Added:** 2026-08-26

### 🛠️ รับเรื่อง (accept) — ระดับสูงกว่ากดรับแทนหัวหน้าห้องได้เลย แต่ต้องกัน 2 รั่ว: รับเรื่องห้องอื่น + ครูก้าวข้าม scope
- **Context/Problem:** เดิม `accept_issue` ใช้ `level == current_level` → ประธานระดับ/สภาจะรับเรื่องระดับ room ไม่ได้จนกว่าหัวหน้าห้องจะรับก่อน (ต้องรอไล่ระดับ) — requirement: ผู้ที่อยู่ระดับสูงกว่า (ประธานระดับ/สภา/ประธานสภา/แอดมิน) เห็นเรื่องแล้วอยากรับเลย ให้รับแทนหัวหน้าห้องในระดับนั้นได้
- **Root Cause:** เปรียบเทียบระดับแบบ equality; และเวลาเปลี่ยนเป็น ">= " (LEVEL_RANK) ระวัง 2 รั่วใหม่: (1) หัวหน้าห้องห้อง A (ระดับ room) รับเรื่องห้อง B ได้ (ทั้งที่ควรรับเฉพาะห้องตัวเอง); (2) ครูทั่วไป `user_level` คืน `"council"` → ถ้าไม่ผูก scope จะรับเรื่องทุกห้องทั้งโรงเรียน
- **Correct Pattern/Solution:**
  1. `can_accept = LEVEL_RANK.get(my_level,0) >= LEVEL_RANK.get(current_level,1)` — ระดับสูงกว่าหรือเท่ากันรับได้ (พีระมิดมองลง)
  2. **กันรั่วห้องอื่น:** ถ้า `current_level == 'room'` และ `LEVEL_RANK[my_level] == LEVEL_RANK['room']` (ผู้รับมีระดับสูงสุดแค่ room) → ต้อง `_user_role_in(user, room_id)` (เป็นสมาชิกห้องเรื่อง) ไม่งั้น 403
  3. **กันครูก้าวข้าม scope:** `_teacher_scope` (staff_level) บังคับเสมอ — `issue_room_level != teacher_level` → 403; ยกเว้นเรื่องระดับ `council` (เดิมครูรับได้ทุกเรื่อง — กัน regression)
  4. **frontend** (`canReceive`): admin bypass → rank `>=` → ถ้า `current_level=='room'` และตัวเองระดับ room ตรวจ `authStore.roles.some(r => r.room_id === issue.room_id)`; `getMyLevel()` แผนที่ `council_member/council_president`→council อยู่แล้ว
  5. **test:** เปลี่ยน `test_cannot_accept_wrong_level` (เคย assert 403) → รับได้ 200 + deep-DB verify assignee; เพิ่ม test head รับห้องอื่น 403 + ประธานสภา รับเรื่อง room 200
  - **กฎ: เวลาเปลี่ยน permission จาก equality เป็น "ระดับสูงกว่าก็ได้" ให้ตั้งคำถามเสมอว่า "ระดับเท่ากันแต่อยู่คนละ scope" (ห้องอื่น/ระดับชั้นอื่น) จะรั่วไหม — ต้องมี gate แยกตามข้อมูลจริง (room membership / staff_level) ไม่ใช่แค่ระดับพีระมิด**
- **Date Added:** 2026-08-26

### 🛠️ List แบบแบ่งหน้า — `COUNT(*) OVER()` อ่าน total จากแถวที่ return → หน้าว่าง (offset เลย) ได้ total=0 ผิดต้องนับแยก + ค้นหา ILIKE ต้องหนี wildcard
- **Context/Problem:** Phase 2 เพิ่ม Pagination + Search + Sort ให้ `GET /api/issues` — เจอ 2 กับดัก: (ก) เทส `offset` เลยข้อมูลหน้าแล้ว `total` กลับเป็น 0 ทั้งที่ยังมีเรื่องอยู่; (ข) search คล้ายคำต้องไม่ให้ `%`/`_` กลายเป็น wildcard
- **Root Cause:**
  1. **`COUNT(*) OVER()` กับ LIMIT/OFFSET:** window function นับแถวที่ตรง WHERE ก่อน LIMIT — ได้ total ถูกต้องเฉพาะเมื่อมีแถว return; ถ้า `offset` เลยข้อมูล `rows` ว่าง → อ่านค่า total จากแถวแรกไม่ได้ → ต้องคืน 0 ผิดพลาด
  2. **เทสต์เดิม assert รูปแบบ list ตรงๆ:** เปลี่ยน response จาก `list[IssueOut]` เป็น envelope `{items,total,page,page_size,pages}` → เทสต์ 6 จุดที่ใช้ `res.json()` เป็น list โดยตรง fail (ต้อง `res.json()["items"]`)
  3. **`q` เข้า ILIKE โดยไม่หนี:** `%`/`_`/`\` ในคำค้นกลายเป็น wildcard/escape → `q=%` จับทุกเรื่อง
- **Correct Pattern/Solution:**
  1. **total:** `SELECT ... COUNT(*) OVER() AS total_count` ใส่ใน query หลัก (ได้ total ใน query เดียวเมื่อมีแถว); **ถ้า `rows` ว่าง (offset เลย) → นับแยกด้วย `SELECT COUNT(*) ... WHERE {' AND '.join(where)}` โดยใช้ params เดิมก่อน append limit/offset (`filter_params = list(params)`)**
  2. **search:** `_escape_like(s)` = `s.replace("\\","\\\\").replace("%","\\%").replace("_","\\_")` + `ILIKE $n ESCAPE '\'`; `q.split()` ทุกคำ (AND ระหว่างคำ) OR ข้าม 6 ฟิลด์ (title/description/room/reporter_room/reporter_name/assignee_name) — ต่อ AFTER visibility cond กันค้นข้ามระดับ; reuse `$n` ใน OR ปลอดภัยเพราะทุกตำแหน่งเป็น text
  3. **sort:** `ORDER BY i.created_at {ASC|DESC}, i.id {ASC|DESC}` — เพิ่ม `i.id` รองกันหน้าไม่เสถียร (timestamp ซ้ำกัน); router ใช้ `Query(pattern="^(asc|desc)$")` → ค่าแปลกได้ 422 อัตโนมัติ
  4. **เทสต์:** เปลี่ยนทุกจุดที่ assert list ตรงๆ เป็น `["items"]` พร้อมกัน; เพิ่มเทสต์ search หนี wildcard (`q=%` เจอเฉพาะเรื่องที่มี `%` จริง) + search ไม่รั่วข้ามระดับ (student ค้นแล้วไม่เจอเรื่องคนอื่น) + pagination หน้าเลย (`offset` เกิน → items=[] แต่ total ยังเท่าเดิม)
  - **กฎ: (1) อย่าใช้ `COUNT(*) OVER()` เป็น total แบบลอยๆ เมื่อมี LIMIT/OFFSET — หน้าว่างต้องมี fallback count; (2) เปลี่ยน response shape ของ list ต้องไล่แก้เทสต์ที่ assert list ตรงๆ ทุกจุด; (3) ILIKE search ทุกครั้งต้องหนี `%`/`_`/`\` + `ESCAPE '\'`; (4) เติม `i.id` ใน ORDER BY เสมอเพื่อให้ pagination กำหนดทิศทางได้**
- **Date Added:** 2026-08-26

### 🛠️ Role สายสภา (council_member) ได้ scope 'all' แต่ต้องไม่ใช่ admin — scope แยกจาก permission
- **Context/Problem:** สภานักเรียน (council_member) มี `VIEW_DASHBOARD` แต่ติด error "ยังไม่ได้กำหนดระดับชั้นที่รับผิดชอบ" — `get_access_scope` ให้ scope 'all' เฉพาะ `SCOPE_ALL_ROLES = {admin, teacher_council, council_president}` → council_member ตกไป 'pyramid' → dashboard แมป fail-closed เป็น 'none' (เลข 0 + ข้อความสำหรับครู)
- **Root Cause:** `council_member` เป็น role ระดับโรงเรียน (ยอดพีระมิด — import_service.SCHOOL_WIDE_ROLES มีอยู่แล้ว, ROLE_LEVEL['council_member']='council') แต่ scope ยังไม่รวม → ไม่สอดคล้องกัน
- **Correct Pattern/Solution:**
  1. `get_access_scope`: เพิ่ม branch `if r["class_role"] == "council_member": return {"scope": "all", "level": None, "is_admin": False}` — ได้ scope 'all' **แต่ is_admin=False**
  2. **scope ≠ permission:** ให้ scope 'all' แค่ทำให้เห็นข้อมูลทั้งโรงเรียน — สิทธิ์จัดการ (MANAGE_STUDENTS/VIEW_AUDIT_LOG) ยังถูกกันโดย `require_permission_anywhere` (เช็ค is_admin + permissions แยกต่างหาก) → test ต้องยืนยันทั้ง 2 ด้าน: council_member เรียก `/dashboard/summary` 200 + เห็นเลขทั้งโรงเรียน **และ** เรียก `/students` 403
  3. dashboard_service: `_usage()` ต้องนับเฉพาะ `action='login' AND status='success'` (failed login ที่บันทึกใหม่ status='error' ต้องไม่ปนยอด)
  - **กฎ: เวลาให้ role ใหม่เห็นทั้งโรงเรียน ให้เพิ่ม branch scope 'all' แยก (is_admin=False) แทนการยัดเข้า SCOPE_ALL_ROLES — เพราะ SCOPE_ALL_ROLES คืน is_admin=True ซึ่งอาจไปเปิดสิทธิ์อื่น; และทุกครั้งที่ scope ขยาย ให้ test ทั้ง "เห็นข้อมูลได้" + "สิทธิ์จัดการยังโดนกันอยู่"**
- **Date Added:** 2026-08-27

### 🛠️ Audit เก็บทุก action อย่างละเอียด — request context (contextvar) สำหรับ ip/user_agent + failed login ต้อง status='error' + read audit เป็น best-effort
- **Context/Problem:** ต้องการ audit_logs เก็บ "ทุกอย่าง" (login/read/create/update/delete) แบบละเอียด แต่ service ไม่มี `request` object → จะส่ง ip/user_agent ต้องแก้ signature ทุกฟังก์ชัน; login ล้มเหลวไม่เคยถูกบันทึก; read/GET ไม่มี audit เลย
- **Root Cause:** AuditLogger รับแค่ค่าที่ส่งตรงๆ; บันทึก login เฉพาะตอนสำเร็จ (failure raise ไปก่อน); ไม่มีกลไกบันทึก action ประเภทอ่าน
- **Correct Pattern/Solution:**
  1. **Request context:** ใหม่ `core/request_context.py` — `ContextVar` เก็บ `{ip_address, user_agent, trace_id}`; middleware ใน main.py (`@app.middleware("http")`) ตั้ง context จาก `request.client.host` + `request.headers.get("user-agent")` + `uuid4()` ก่อน `call_next` แล้ว clear หลังจบ → `AuditLogger.log` ดึงจาก context ถ้าไม่ได้ส่งตรงๆ → **service ทุกตัวได้ ip/user_agent/trace อัตโนมัติโดยไม่แก้ signature** (worker/background ที่ไม่ผ่าน HTTP → context ว่าง → None)
  2. **AuditLogger:** เพิ่มคอลัมน์ `user_agent` ใน INSERT (คอลัมน์มีอยู่แต่ไม่เคย insert — จับตารางที่มี column เกินจากที่ logger ใช้)
  3. **Failed login:** ครอบ 2 จุด raise ใน `authenticate_user` → `AuditLogger.log(action="login", status="error", error_detail=..., actor_identifier=username, user_id=...)` (ไม่เจอชื่อ → user_id=None, ผิดรหัส → รู้ user_id) → re-raise; dashboard `_usage()`/traffic ต้อง filter `status='success'`
  4. **Read audit:** ใหม่ `services/audit_service.log_read(pool, user_id, action, entity_type, ...)` เรียกจาก routers หลัง GET สำเร็จ (action='READ_ISSUES'/'READ_DASHBOARD'...) — **best-effort: try/except เงียบ อย่าทำ main flow พัง**
  5. **Index:** audit_logs โตเร็ว → migration `006_audit_logs_indexes` (action,created_at / user_id / entity / created_at) + ใส่ block เดียวกันใน init_db
  6. **เทสต์ Gotcha:** (a) insert audit ตรงๆ อย่า reuse `$1` ข้าม type (INTEGER user_id vs VARCHAR entity_id → AmbiguousParameterError — บทเรียนเดิม); (b) `register_user(pool, username, password, full_name, student_id, room_code, student_no, class_role)` มี `student_no` เป็น positional — ลืมแล้ว class_role ตกไปที่ student_no → `DataError: $4: 'teacher'`
  - **กฎ: (1) ข้อมูล network ของทุก audit เก็บผ่าน request context กลาง ไม่ใช่แก้ signature ทุก service; (2) audit ทุกชนิดมี status/success-error — ตัวนับ "การเข้าใช้งาน" ต้อง filter success; (3) read audit ต้องไม่ทำให้ request หลักพัง (best-effort); (4) ตาราง audit ต้องมี index ที่ตรงกับ query (group by day + filter action) ก่อนจะ "เก็บทุกอย่าง"**
- **Date Added:** 2026-08-27

### 🛠️ สิทธิ์ระดับสภา ≠ `user_level()=='council'` — ครูทั่วไปก็คืน 'council' (เป็นแค่ visibility) ต้องตรวจตำแหน่งจริง
- **Context/Problem:** สร้าง `approve_to_public` (สภาอนุมัติเรื่องขอโพสต์สาธารณะเป็น PIRI Board) — ต้องการเช็ค "อำนาจระดับสภา/แอดมิน" แต่ถ้าใช้ `user_level(pool, user_id) == 'council'` จะ **ครูทั่วไป (teacher) ผ่านด้วย** เพราะ `user_level()` คืน 'council' ให้ทุกคนที่ "มองเห็นข้อมูลทั้งโรงเรียน" (teacher/teacher_council/council_president/admin/council_member) — ครูทั่วไปไม่ได้เป็นสภาแต่จะอนุมัติเรื่องสาธารณะได้ (privilege escalation)
- **Root Cause:** ฟังก์ชันเดียวกันถูกใช้เพื่อ 2 จุดประสงค์ — `user_level` ตั้งใจคืน 'council' สำหรับ *visibility* (ครูเห็นทั้งโรงเรียน) แต่ *authority* (สิทธิ์กระทำ) ต้องดูจากตำแหน่งจริง; ถ้าสลับมาใช้ visibility เป็น permission จะเปิดช่องทันที
- **Correct Pattern/Solution:**
  1. แยก helper `_has_council_authority(conn, user_id)`: Super Admin / `is_admin` ผ่าน, หรือ `class_role IN ('council_member','council_president','teacher_council')` (ตำแหน่งสภาจริง) — **ไม่รวม 'teacher'**
  2. เช็ค authority ด้วย helper นี้เท่านั้นสำหรับ action ที่ต้อง "เป็นสภา"; `user_level()` ใช้สำหรับ filter การมองเห็น/รายการเท่านั้น
  3. `start_level` bypass: เรื่องขอสาธารณะ (vote/talk) ตั้ง `start_level='council'` อัตโนมัติ — ต้อง **ข้าม** เช็ค `user_level >= start_level` (ไม่งั้นนักเรียนขอโหวตไม่ได้) เพราะผู้แจ้งแค่ "ขอ" — สภาเป็นคนอนุมัติทีหลัง
  4. test: council_member (ไม่ใช่ admin) อนุมัติได้ 200 / student อนุมัติ 403 + deep-DB ตรวจไม่มี board ถูกสร้างตอน 403; teacher ควรได้ 403 ด้วย
  - **กฎ: อย่าใช้ฟังก์ชันที่ออกแบบเพื่อ "เห็นข้อมูล" มาอนุมัติ "กระทำการ" — visibility scope กับ authority ต้องเป็นคนละเช็ค; เวลาเปิดฟีเจอร์ที่ "ใครก็ขอได้แต่สภาอนุมัติ" ให้ข้าม level-check ตอนสร้าง แต่บังคับ authority-check ตอนอนุมัติ**
- **Date Added:** 2026-08-28

### 🛠️ Board สาธารณะ (PIRI Boards) — anonymous ต้องซ่อน author_id ด้วย (ไม่ใช่แค่ชื่อ) + Denormalized counter drift เป็น known limitation
- **Context/Problem:** สร้าง PIRI Boards (Phase 3: feed board สาธารณะ + vote + คอมเมนต์) — ผู้แจ้งขอ "anonymous" ตอนสร้าง issue → board ควรไม่ระบุตัวตน; และพึ่ง Denormalized counter (`vote_count`/`comment_count`) สำหรับโชว์ยอด
- **Root Cause/สิ่งที่เจอ:**
  1. **Anonymous รั่ว author_id:** `_board_to_dict()` ซ่อนแค่ `author_name` แต่ยังคืน `author_id` (users.id ลำดับต่อเนื่อง) → ใครก็ตามที่ล็อกอินเทียบ id กับ endpoint อื่น (student/commenter) ได้ = deanonymize — board สาธารณะเห็นทั้งโรงเรียน ยิ่งรั่ววงกว้าง
  2. **Denormalized counter drift:** `submit_vote` เพิ่ม `vote_count` อย่างเดียว, `add_comment` เพิ่ม `comment_count` อย่างเดียว — ไม่มี path ลด; schema ตั้งใจให้ soft-delete vote แล้วโหวตใหม่ได้ (partial unique `uq_piri_votes_board_user_active WHERE deleted_at IS NULL`) แต่ counter เก่าไม่ถูกลด → ยอดลอย
- **Correct Pattern/Solution:**
  1. **anonymous board:** ซ่อน `author_id` + `author_name` เป็น None ทั้งคู่ (ไม่ได้แค่ชื่อ) + test ตรวจ response ทั้ง feed และ detail (`assert detail["author_id"] is None`)
  2. **Counter drift:** ยังไม่มี API soft-delete vote/comment ใน Phase 3 → drift เกิดได้เฉพาะ direct SQL (test) — บันทึกเป็น **known limitation**: ตอนเพิ่ม revoke/delete/moderate ใน Phase หลัง ต้องลด counter ใน transaction เดียว หรือ derive ยอดจาก `COUNT(*) FROM piri_votes WHERE deleted_at IS NULL` แทนการอ่าน counter (กันยอดลอยแบบถาวร)
  3. **ปิดช่อง moderation:** `add_comment` reply ต้องตรวจ `is_hidden_by_admin = FALSE` บน parent ด้วย (ไม่ใช่แค่ `deleted_at IS NULL`) — ไม่งั้น reply ต่อคอมเมนต์ที่แอดมินซ่อนแล้ว โดน `_thread_comments` ย้ายขึ้น root (bypass moderation)
  4. **Defensive (จาก adversarial review):** (a) comment fetch ใส่ `LIMIT 1000`; (b) **Pydantic recursive model ระเบิดได้ — `BoardCommentOut` ซ้อนตัวเอง: reply chain ~256 ชั้น → `BoardDetailOut(**detail)` เกิด `ValidationError: recursion_loop` → HTTP 500** ทุก GET detail; ผู้ใช้ธรรมดาสร้าง chain นี้ได้ (โพสต์ reply ต่อ reply ซ้ำๆ ไม่มี throttle) → DoS จริง → ต้อง (i) พับความลึก tree ที่ส่ง client (`MAX_DISPLAY_DEPTH=8` — reply เกินถูกย้ายใต้บรรพบุรุษที่ยังใต้ลิมิต, ไม่หาย) + (ii) guard ตอนสร้าง reply (`MAX_REPLY_DEPTH=30` — recursive CTE นับความยาว chain ถึง root แล้ว 400) + (iii) parent ที่ soft delete → ลูกขึ้น root ต้องรีเซ็ต `parent_comment_id=None` (กัน frontend เจอ id แขวน); (c) `my_vote_choice_id` ต้อง JOIN choice ที่ยัง active (กันชี้ choice ที่ soft-delete แล้ว)
  - **กฎ: (1) ฟีเจอร์ anonymous ต้องซ่อนทุก field ที่ระบุตัวตนได้ (ไม่ใช่แค่ชื่อ — id ต่อเนื่องก็ระบุตัวได้); (2) ก่อนใช้ denormalized counter ดู schema ว่ามี path soft-delete/revote ไหม — ถ้ามี ต้องมี path ลด counter มิฉะนั้นบันทึกเป็น limitation + ให้ derive จาก base table; (3) moderation flag (is_hidden) ต้องถูกเช็คทุกที่ที่ "อ้างอิง" object ที่ถูก moderate — write side ด้วย ไม่ใช่แค่ read; (4) model Pydantic ที่ซ้อนตัวเอง (recursive) ต้องจำกัดความลึกให้ชัด — ทั้งตอน serialize และตอนสร้างข้อมูลใหม่ ไม่งั้นผู้ใช้ธรรมดา DoS ได้**
- **Date Added:** 2026-08-28

### 🛠️ Board Moderation (Phase 5) — ซ่อนคอมเมนต์ต้องลด counter พร้อมกัน (ทั้ง subtree) + คอลัมน์ `closed_by` ไม่ใช่ `close_by`
- **Context/Problem:** เพิ่ม moderation + report ให้ PIRI Boards — สภาซ่อนคอมเมนต์ไม่เหมาะสม, นักเรียนแจ้งความไม่เหมาะสม (ตาราง `piri_board_reports`), จัดการรายงาน (hide/dismiss); ตอนนี้มี path "ลบ" คอมเมนต์จริง → **counter drift ที่บันทึกเป็น known limitation ใน Phase 3 ต้องแก้**: ทุก hide ต้องลด `comment_count`, ทุก unhide ต้องเพิ่มคืน
- **สิ่งที่เจอ/บทเรียน:**
  1. **ซ่อนทั้ง subtree (ไม่ใช่แค่ตัวเดียว):** ถ้าซ่อนคอมเมนต์หลัก แต่ reply ยังแสดงอยู่ → `_thread_comments` promote ลูกขึ้น root (bypass moderation — reply ที่อ้างอิงคอมเมนต์ไม่เหมาะสมยังลอยอยู่) → ใช้ recursive CTE `WITH RECURSIVE sub(cid) AS (SELECT $1::integer UNION ALL SELECT c.id FROM piri_board_comments c JOIN sub ON c.parent_comment_id = sub.cid WHERE c.deleted_at IS NULL)` หาลูกหลานทั้งหมด แล้ว `UPDATE ... WHERE id = ANY($1::int[])` พร้อมกัน — นับ `hidden_count` จาก data-modifying CTE (`WITH updated AS (UPDATE ... RETURNING id) SELECT COUNT(*) FROM updated`) แล้ว `comment_count = GREATEST(comment_count - $2, 0)` กันติดลบ (drift จากอดีต)
  2. **asyncpg array binding ใช้ได้:** Python list → `ANY($1::int[])` + anchor `$1::integer` ใน recursive CTE (บทเรียน `integer = text` เดิม — cast ทั้งคู่; asyncpg จัดการ list → array ตาม cast context)
  3. **Moderation ซ้ำ → 409:** hide คอมเมนต์ที่ `is_hidden_by_admin=TRUE` อยู่แล้วต้อง ConflictError (กันลด counter ซ้ำ); resolve รายงานที่ `status!='open'` ก็ 409
  4. **จัดการรายงาน (resolve) ใช้ action `hide`/`dismiss`:** hide → เรียก `_hide_comment_subtree` ร่วมกับ endpoint hide ตรง (DRY) + ปิดรายงาน open ทั้งหมดที่จุดนั้น (`UPDATE ... SET status='resolved' WHERE comment_id = ANY($1::int[]) AND status='open'`); dismiss → ปิดเฉพาะรายการนั้น (คอมเมนต์ยังแสดง)
  5. **`GET /boards/reports` ต้องอยู่ก่อน `GET /boards/{board_id}`:** ไม่งั้น 'reports' ถูก match เป็น board_id (int) → 422; และ **ทุก router ที่ดัก domain exception ต้อง wrap try/except — test จับจริงว่า ForbiddenError ที่ไม่ถูกดัก → 500 แทน 403** (list_reports ลืม try/except ตอนแรก)
  6. **คอลัมน์พยายม: `piri_boards.closed_by` (มี d) ไม่ใช่ `close_by`** — schema ใช้ `closed_at/closed_by/close_reason`; เขียน SQL ต้องระวังตัวสะกด (UndefinedColumnError จับได้ตอน test)
  7. **Migration 008 ทำ counter reconcile:** `UPDATE piri_boards SET comment_count = (SELECT COUNT(*) ... WHERE deleted_at IS NULL AND is_hidden_by_admin = FALSE)` + `UPDATE piri_vote_choices SET vote_count = (SELECT COUNT(*) FROM piri_votes WHERE deleted_at IS NULL)` — heal drift เก่าที่เกิดก่อนมี feature hide (ทำใน migration ก่อน feature ใช้งาน)
  8. **Test gotcha:** default reporter ต้องไม่ใช่เจ้าของคอมเมนต์ (self-report → 400) — ใน fixture คอมเมนต์สร้างโดย student → reporter ควรเป็น council/admin; reply ต้องระบุ `parent_id` จริงๆ ถึงจะซ้อน (ลืม = คอมเมนต์หลักไม่ใช่ reply); ตรวจ tree ให้เช็ค `replies` ที่ซ้อน ไม่ใช่แค่ root list
  9. **`view_count` บน `piri_boards` เดิมไม่มี path เพิ่มเลย** (column ตั้งมาแต่ขี้เกียจ) → เพิ่ม increment ใน `get_board_detail` (ไม่ audit — read audit ผ่าน log_read อยู่แล้ว)
- **กฎ: (1) ทุก feature ที่สร้าง/ลบ/ซ่อน object ต้องปรับ denormalized counter ใน transaction เดียว อย่างน้อย `GREATEST(x - n, 0)` กันติดลบ และ unlock path ใหม่ทุกอันต้องมี test "counter == จำนวนจริงหลังครบวงจร"; (2) moderation ต้องจัดการทั้ง subtree (กัน bypass ผ่าน promote reply); (3) route ที่มี path param int กับ literal ก่อนหน้า ระวัง shadowing — literal ต้องลงทะเบียนก่อน; (4) ทุก domain exception ที่ router ดักได้ต้อง wrap จริง — 500 แทน 403 เป็น bug**
- **Date Added:** 2026-08-28

  - **แก้เพิ่ม (หลัง adversarial review 2 — 13 confirmed):**
    1. **unhide ต้องเป็น single comment ไม่ใช่ subtree:** unhide subtree เผลอฟื้นคอมเมนต์ที่แอดมินซ่อนแยกคนละครั้ง (resurrection bug — คอมเมนต์ที่ซ่อนเองกลับมาโผล่ทั้งโรงเรียน) → `_unhide_comment` คืนแค่ตัวที่กด (comment_count +1); อยากคืนทั้งต้น unhide ทีละตัว
    2. **Report ต้องมี cap:** `MAX_OPEN_REPORTS_PER_USER=10` — ไม่มี cap → user enumerate board/comment ใส่รายงานนับพันฝังคิวสภา (unique index กันแค่รายงานซ้ำ comment เดียว)
    3. **Pagination fallback COUNT ต้อง JOIN ให้ตรงกับ where_sql:** `list_reports` ตอน `q` ไม่เจอ → fallback `SELECT COUNT(*) FROM piri_board_reports r WHERE (b.title ILIKE...)` อ้าง alias b/c ที่ไม่มีใน FROM → 500 `missing FROM-clause entry` — fallback ต้อง JOIN b/c ด้วย (บทเรียน: where_sql ที่อ้าง alias ของ join ต้องมี join นั้นใน query count ด้วย)
    4. **hide_board ต้องปิด report open ของบอร์ดด้วย** (กันคิวยังโชว์เนื้อหาบอร์ดที่ซ่อนเป็น 'open')
    5. **`add_comment` → `get_comment` TOCTOU:** moderator ซ่อนคอมเมนต์คั่นระหว่าง add (commit) กับ get (อ่าน) → get_comment filter `is_hidden_by_admin=FALSE` → 404 ทั้งที่ insert ไปแล้ว → client retry = คอมเมนต์ซ้ำ → `get_comment` (ใช้หลัง add เท่านั้น) ไม่ filter hidden
    6. **hide vs reply ที่ insert คั่น (TOCTOU):** re-walk subtree สูงสุด `MAX_HIDE_PASSES=3` รอบ — reply ที่ insert คั่นระหว่างนับกับซ่อนจะถูกซ่อนรอบถัดไป (ยังไม่ atomic 100% แต่แคบลงมาก)
    7. **Test gap ที่ต้องปิด:** plain student แจ้งได้ 200, cross-board report 404, soft-deleted report 404, migration reconcile repair, reason filter + pagination envelope, descendant report auto-close

### 🧯 Rehearsal Migration: correlated subquery reconcile ช้า 100 เท่า → lock ค้าง 2.4 นาที (ต้อง aggregate+JOIN)
- **Context/Problem:** จำลอง Production DB (5k boards / 100k comments / 20k choices / 200k votes) รัน migration 008 reconcile (`UPDATE ... SET comment_count = (SELECT COUNT(*) ...)` แบบ correlated subquery) เพื่อประเมิน lock window ก่อน deploy จริง — พบว่า **vote_count reconcile ใช้เวลา 142.5 วินาที** (correlated subquery รัน 20k ครั้ง ต่างคนละ snapshot + planner เลือก scan) → Postgres ถือ ROW EXCLUSIVE บน piri_vote_choices ตลอด 2.4 นาที → writer ฝั่งนั้นรอค้าง
- **Root Cause:** correlated subquery `SET x = (SELECT COUNT(*) FROM child WHERE child.fk = parent.id)` รัน subquery ต่อ 1 แถวแม่ — O(rows_แม่ × scan) ระดับข้อมูลจริง ระเบิด
- **Correct Pattern/Solution:** เปลี่ยนเป็น **aggregate+JOIN** (อ่านตารางลูกผ่านเดียว + GROUP BY + LEFT JOIN) — ได้ผลลัพธ์เดียวกันแต่เร็ว ~280 เท่า:
  ```sql
  UPDATE piri_boards b
  SET comment_count = COALESCE(cnt.c, 0), updated_at = NOW()
  FROM (
      SELECT pb.id AS bid, agg.c
      FROM piri_boards pb
      LEFT JOIN (
          SELECT board_id, COUNT(*) AS c
          FROM piri_board_comments
          WHERE deleted_at IS NULL AND is_hidden_by_admin = FALSE
          GROUP BY board_id
      ) agg ON agg.board_id = pb.id
  ) cnt
  WHERE cnt.bid = b.id
  ```
  LEFT JOIN ต้องใช้ (ไม่งั้น board ที่ไม่มีคอมเมนต์เลยไม่ถูก zero)
- **ผล rehearsal:** correlated subquery → comment_count 2.5s / vote_count 142.5s; aggregate+JOIN → 0.25s / 0.51s (รวม 762ms) — **lock window จาก 2.4 นาที เหลือ <1 วินาที** ปลอดภัยต่อ deploy จริง
- **กฎ: (1) ก่อนเขียน UPDATE reconcile ระดับ prod ให้ rehearsal บนข้อมูลขนาดจริงก่อนเสมอ (สคริปต์ `backend/scripts/migration_rehearsal.py` มีให้ใช้); (2) ห้าม correlated subquery ใน UPDATE ที่วิ่งทั้งตาราง — ใช้ aggregate+GROUP BY+JOIN; (3) ตารางแม่ที่ต้อง zero ค่าให้ใช้ LEFT JOIN เก็บกรณีไม่มีลูก; (4) lock window ที่ยอมรับได้ ~<1s; ถ้าตารางยักษ์จริงให้แบ่ง batch + NOWAIT**
- **Date Added:** 2026-08-28

### 🛠️ View-count dedup (Phase 6) — กัน F5 ปั่นยอด + asyncpg gotcha: INSERT ใน FROM ของ subquery → SyntaxError
- **Context/Problem:** เดิม `get_board_detail` บวก `view_count+1` ทุกครั้งที่เปิด board (adversarial review จับว่า F5/refresh รัวๆ ปั่นยอดได้) → ต้อง dedup ต่อ user ภายใน window (10 นาที) ผ่านตาราง `piri_board_views (board_id, user_id, viewed_at)` PK (board_id,user_id)
- **Pattern (dedup atomic — ไม่มี TOCTOU ระหว่าง check กับ insert):**
  ```sql
  WITH ins AS (
      INSERT INTO piri_board_views (board_id, user_id, viewed_at)
      VALUES ($1, $2, NOW())
      ON CONFLICT (board_id, user_id)
      DO UPDATE SET viewed_at = NOW()
      WHERE piri_board_views.viewed_at < NOW() - INTERVAL '10 minutes'
      RETURNING 1
  )
  SELECT COUNT(*) FROM ins
  ```
  คืน 1 เฉพาะ "ยังไม่เคยดู" หรือ "เลย window แล้ว" → ถึงจะ +1; ภายใน window (refresh รัวๆ) `WHERE` เท็จ → ไม่คืน row → COUNT 0 → ไม่นับ
- **⚠️ asyncpg/Postgres gotcha:** เขียนเป็น `SELECT COUNT(*) FROM (INSERT ... RETURNING ...) t` **ไม่ได้** — Postgres ห้าม DML ตรงใน FROM ของ subquery → `PostgresSyntaxError: syntax error at or near "INTO"` → GET detail พังทุกตัว → ต้องใช้ **data-modifying CTE** (`WITH ins AS (INSERT ...) SELECT COUNT(*) FROM ins`) เท่านั้น (เป็นบทเรียนเดียวกับ phase3 เรื่อง DML-CTE ที่ใช้ count ได้ แต่เลือกผิดฝั่งวาง)
- **กฎ: ถ้าอยาก "INSERT ที่ไม่ซ้ำแล้วนับว่าแทรก/อัปเดตจริงไหม" ให้ใช้ WITH data-modifying CTE + RETURNING + COUNT(*) — ห้ามวาง INSERT ใน FROM; และ dedup แบบนี้ฟรี (ไม่ต้อง Redis) เพราะเป็น atomic UPSERT ในตารางเดียว**
- **Date Added:** 2026-08-28

### 🛠️ Notifications fan-out (Phase 7) — asyncpg ต้อง numbering placeholder เริ่มที่ `$1` เสมอ
- **Context/Problem:** `notify_fanout` ใช้ `INSERT ... SELECT user_id, $2, $3, ... FROM students` (คอลัมน์ `user_id` มาจาก SELECT ไม่ใช่ parameter) → `IndeterminateDatatypeError: could not determine data type of parameter $1` → POST approve-to-public 500 (จับได้ตอนรันเทสต์ 22 ตัว)
- **Root Cause:** asyncpg numbering parameter เริ่มที่ `$1` เสมอ — SQL ที่อ้าง `$2..$10` แต่ไม่มี `$1` (เพราะ column value ไม่ใช่ param) asyncpg ยังตี `$1` เป็น parameter ตัวแรก → อนุมาน type ไม่ได้
- **Correct Pattern/Solution:** นับ placeholder ให้เริ่มที่ `$1` ใน SQL ทุกครั้ง แม้ column บางตัวมาจาก SELECT:
  ```sql
  INSERT INTO notifications (user_id, group_type, ...)
  SELECT user_id, $1, $2, $3, ...   -- $1 = group_type (param แรก)
  FROM students
  WHERE ... AND ($8::int IS NULL OR user_id <> $8)  -- actor_id = $8, cast ชัด
  ```
- **กฎ: ก่อน `conn.execute/fetch(sql, *params)` ตรวจว่า placeholder เลขขึ้นจาก $1 เรียงต่อเนื่อง และ `count('$') == len(params)`; โดยเฉพาะ SQL แบบ INSERT...SELECT หรือ dynamic WHERE ที่ column มาจาก expression ไม่ใช่ param — นี่เป็นบทเรียนที่เจอซ้ำ (ดูรายการ $1 เกิน + $2 เป็นตัวแรก)**
- **Date Added:** 2026-08-31

### 🛠️ asyncpg `AmbiguousParameterError` — `SELECT DISTINCT` ต้อง cast param ใน select-list ให้ชัด
- **Context/Problem:** `notify_fanout` เพิ่ม `SELECT DISTINCT user_id, $1, $2, ...` เพื่อกัน user หลายห้องได้ board_new ซ้ำ → `AmbiguousParameterError: inconsistent types deduced for parameter $8 (integer versus text)` → approve-to-public 500 (เจอจริงตอนเทสต์ fan-out dedup)
- **Root Cause:** `DISTINCT` ทำให้ asyncpg ตี type ของ select-list parameter ต้อง resolve เอง (ไม่พึ่ง INSERT target column เหมือน `SELECT` ธรรมดา) → param ที่ใช้ทั้งใน select-list และ WHERE (เช่น `$8`) เจอการอนุมานขัดกัน
- **Correct Pattern/Solution:** cast ชัดทุก param ใน select-list: `SELECT DISTINCT user_id, $1::varchar, $2::varchar, $3::text, ..., $6::int, $7::int, $8::int, $9::text` — ไม่เหลือที่ asyncpg ต้องเดา (ดูเพิ่มจากบทเรียนเดิม `$1` ซ้ำ / `$1` เกิน / numbering เริ่ม $1)
- **กฎ: SQL ที่มี DISTINCT/GROUP BY + parameter ใน select-list → cast `::int`/`::text`/`::varchar` ทุก param ทันที (DISTINCT โดยเฉพาะเปราะเรื่อง type inference)**
- **Date Added:** 2026-08-31

### 🛠️ Seed ใน `init_db` — `COUNT()==0` ถูก re-insert ตอน TestClient เปิด app (พังเทสที่คาดจำนวนแถว)
- **Context/Problem:** เพิ่มตาราง `announcements` + seed แบบ "insert ถ้าตารางว่าง" ลงใน `init_db` → เทส `test_public.py` คาด `len(data)==2` แต่ได้ 4 (seed 2 + ของเทส 2) ทั้งที่ `clean_database` truncate แล้ว
- **Root Cause:** `client` fixture เปิด `TestClient(app)` → FastAPI lifespan วิ่ง `init_db` อีกครั้ง → seed เห็น `COUNT()==0` (เพิ่งโดน truncate) → insert seed ใหม่ **หลัง** clean_database → ข้อมูล test ปนกับ seed เสมอ
- **Correct Pattern/Solution:** seed แบบ `if count==0` ใช้ได้กับ prod (idempotent) แต่เทสต้องไม่พึ่ง "ตารางว่าง" — ให้ fixture ของเทสเคลียร์ตารางนั้นเองก่อน insert ข้อมูลของมัน (`DELETE FROM announcements WHERE deleted_at IS NULL` ใน `public_world`) และตัดสินใจเรื่องนี้ตอนออกแบบตารางใหม่: seed ที่วิ่งซ้ำทุก startup + เทสที่มี `client` fixture = ต้องเคลียร์เอง
- **กฎ: เมื่อเขียนเทสที่อ่านตารางที่ `init_db` seed ไว้ ให้ล้างตารางนั้นใน fixture ก่อน insert เสมอ (ห้ามเดา count จาก schema seed); หมายเหตุ — `clean_database` ต้องมีตารางใหม่ใน TRUNCATE list ด้วย**
- **Date Added:** 2026-08-31

### 🛠️ CSS `overflow-x-hidden` บน root wrapper พัง `position: sticky` (Navbar ไม่ติดด้านบนเงียบ ๆ)
- **Context/Problem:** Landing.vue wrap ทั้งหน้าด้วย `<div class="overflow-x-hidden">` เพื่อตัดองค์ประกอบล้นขอบ → header `position: sticky; top: 0` **ไม่ติดขอบจอ** (เลื่อนผ่านแล้วหายไป)
- **Root Cause:** per CSS spec เมื่อ axis หนึ่งเป็น `hidden` และอีก axis เป็น `visible` → `visible` ถูกคอมพิวต์เป็น `auto` → wrapper กลายเป็น **scroll container** → sticky ผูกกับ scrollport ของ wrapper (ไม่ใช่ viewport) แต่ wrapper สูง auto (โตตามเนื้อหา ไม่เคย scroll) → sticky ไม่ทำงาน
- **Correct Pattern/Solution:** ใช้ `overflow-x: clip` แทน `hidden` บน wrapper — `clip` **ไม่** สร้าง scroll container (sticky ยังทำงาน) แต่ตัดภาพล้นขอบเหมือนกัน (Chrome 90+/Firefox 81+/Safari 16+; ตกยุคเก่าได้แค่เลื่อนล้นเล็กน้อย); และโค้ดที่บล็อกล้นจริง ๆ (blob, floating card) ให้ `overflow-hidden` ระดับ section แทน
- **กฎ: ถ้าต้องการตัด overflow แนวนอนโดยไม่พัง sticky → `overflow-x: clip` (ไม่ใช่ hidden); เช็คเสมอว่า element ไหนเป็น scroll container ก่อนใช้ sticky**
- **Date Added:** 2026-09-01

### 🛠️ SVG `preserveAspectRatio="none"` ยืด `circle` เป็นวงรี (จุดสุดท้ายของ sparkline เพี้ยน)
- **Context/Problem:** Sparkline ข้อมูลจริง (Landing stats) ใช้ `svg viewBox="0 0 320 84"` + `preserveAspectRatio="none"` + `w-full h-24` ให้ยืดเต็มความกว้าง → จุดสุดท้าย `<circle r="4">` ถูกยืดเป็นวงรีเมื่อจอสัดส่วนต่างจาก viewBox (hero card กว้าง ~578px → อัตราส่วน 6.0 vs viewBox 3.81)
- **Root Cause:** `vector-effect="non-scaling-stroke"` แก้ stroke ของ polyline แต่ **ไม่แก้ geometry** — circle โดน non-uniform scale เต็ม ๆ (กลายเป็นวงรี + stroke ไม่สม่ำเสมอ)
- **Correct Pattern/Solution:** ลบ `<circle>` ออกจาก SVG → วาง HTML dot (span ทรงกลม fixed-size) ทับบนกรอบ `relative` เดียวกันกับ svg โดยใช้ % จากพิกัด viewBox: `left: last.x/320*100%`, `top: last.y/84*100%` (ข้อมูลที่อยู่ใน scope ของ code เดียวกันจะตรงกับตำแหน่งเสมอ แม้ svg ยืด)
- **กฎ: chart แบบ SVG ที่ใช้ `preserveAspectRatio="none"` (ยืดไม่เท่ากัน) → จุด/ลูกเล่นที่ต้องเป็นวงกลมคงที่ ให้วาดเป็น HTML overlay ที่ % position ไม่ใช่ `<circle>` ใน SVG**
- **Date Added:** 2026-09-01

### 🛠️ Count-up / อนิเมชันหลังโหลดข้อมูล — watch ต้องรอ flag loading ปิดก่อน (element อยู่ใน `v-else` ของ Skeleton)
- **Context/Problem:** Landing stats ใช้ Count-up: `watch(stats, () => nextTick(() => animate(grid)))` → **ไม่เคยวิ่ง** เพราะ Bento Grid อยู่ใน `v-else` (แสดงเมื่อ `!isLoadingStats`) ส่วน `stats` ถูก set ใน try ขณะที่ `isLoadingStats` ยัง true → ณ ตอน watch fire grid ยังไม่ mount → `ref` เป็น null → animate ข้าม
- **Root Cause:** element อยู่ใน branch ที่ถูก conditional render โดยอิง flag loading ที่ถูก set `false` ใน `finally` (หลัง data set เสมอ) → timing ของ `data` กับ `element mount` ไม่พร้อมกัน
- **Correct Pattern/Solution:** watch แบบสองแหล่ง `watch([stats, isLoadingStats], () => { if (!stats || isLoadingStats) return; nextTick(animate) })` → animate เกิดตอน `isLoadingStats` เพิ่ง flip เป็น false (grid mount พอดี); กันไว้ทั้งกรณีโหลดครั้งแรกและ retry
- **กฎ: ถ้าองค์ประกอบถูก conditional render จาก flag loading → อนิเมชันหลังโหลดต้อง watch ทั้ง data + flag (รอ flag = false) ไม่งั้น ref ยัง null**
- **Date Added:** 2026-09-01

### 🛠️ วิธีรัน pytest เมื่อ pypi/network down (DNS ตาย) — ใช้ container ที่มี deps อยู่แล้ว
- **Context/Problem:** `docker compose -f docker-compose.test.yml run --rm test_runner` install pytest ทุกครั้งจาก pypi (`--no-cache-dir`) → host DNS ตาย (`getent hosts pypi.org` ค้าง / curl timeout) → ติดตั้งไม่ได้ ไม่มีทางรันเทส
- **Correct Pattern/Solution:** หา container/image ที่มี pytest + pytest-asyncio + httpx + bcrypt + fastapi อยู่แล้ว แล้วใช้แทน:
  1. `docker ps -a` หา container ที่เคยรันเทส (เช่น `piri_test_runner` ที่ Exited) → `docker start <name>` → deps ยังอยู่ใน writable layer → `docker exec ... python -m pytest`
  2. หรือยืม image ของโปรเจคอื่นที่ติดตั้งครบ (`cm-test-runner:ready`) → `docker run --network <compose-net> -e DATABASE_URL=... -v ./backend:/app -w /app --entrypoint python3 <img> -m pytest`
  - ตรวจว่า container อยู่ net เดียวกับ `test_db` + `DATABASE_URL` ถูกต้องก่อน
- **กฎ: ติดตั้ง pytest ไม่ได้เพราะ network → อย่ารอ pip; หา container/image ที่มี deps ครบแล้ว mount backend เข้าไปแทน (network แค่ตอน first-install เท่านั้น)**
- **Date Added:** 2026-09-01

### 🛠️ `npm run format` (prettier --write src/) — reformat ทั้งโปรเจค + ทำลาย inline event handler แบบหลาย statement
- **Context/Problem:** รัน `npm run format` เพื่อจัด format ไฟล์ feature ที่ตัวเองแก้ → prettier เขียนทับ `src/` ทั้งหมด → reformat ~44 ไฟล์ที่ไม่ได้แตะ (diff ล้นจน review ไม่ไหว) และที่แย่กว่านั้น **พัง build** เงียบ ๆ
- **Root Cause:** repo นี้ยังไม่ prettier-clean (มีการจัดมือ ไม่ตรง rule ของ prettier) → prettier จึง "แก้" ไฟล์อื่นทั้งโปรเจค; และ prettier แปลง inline event handler แบบหลาย statement เช่น `@click="isMoreOpen = false; router.push({ name: 'profile' })"` (ปกติเขียน ;-คั่นบรรทัดเดียว ซึ่ง Vue รองรับ) ให้กลายเป็นแบบหลายบรรทัดโดย**ตัด `;` ทิ้ง**:
  ```html
  @click="
    isMoreOpen = false
    router.push({ name: 'profile' })
  "
  ```
  Vue template compiler แยก statement ไม่ออก → `RolldownError: ... .vue:NNN:NN ... Unexpected token, expected ','` (error ชี้ไปที่บรรทัดของ attribute ได้พอดี)
- **Correct Pattern/Solution:** format เฉพาะไฟล์ที่ตัวเองจะ commit: `npx prettier --write <files>` (ไม่ใช่ทั้ง `src/`); ถ้าโดน reformat collateral ไปแล้ว → `git restore` ไฟล์ที่ไม่เกี่ยวกับ feature ทิ้ง; ซ่อม handler ที่ถูกทำลายโดยใส่ `;` คั่นกลับ (หรือยุบเป็นบรรทัดเดียว) — `:class="..."`/`:style="..."` ที่เป็น multiline ternary ไม่พัง (เป็น expression เดียว จึงไม่ต้องซ่อม); ก่อน build ให้ grep จับ multiline directive ก่อนได้: `grep -rnE '^\s*@(click|submit|change|keyup|input)\.?[a-z.]*="\s*$' src`
- **กฎ: อย่ารัน prettier ทับทั้ง `src/` ใน repo ที่ยังไม่ prettier-clean; event handler แบบหลาย statement ใน Vue ต้องมี `;` คั่นเสมอ (ถ้าจะ format ใช้ `prettier --write` เฉพาะไฟล์)**
- **Date Added:** 2026-09-06

### 🛠️ ตำแหน่งพิเศษ (admin/ครูสภา/ประธานสภา/สภานักเรียน) ถูก seed แบบ room_id NULL — query ที่ `JOIN rooms` จะตัดทิ้งเงียบ ๆ
- **Context/Problem:** หน้า "จัดการสมาชิก" (GET /students) เมื่อ login ด้วยบัญชีตำแหน่งพิเศษที่ไม่ได้สังกัดห้อง (admin / ครูสภา / ประธานสภา) → กลุ่ม "สภานักเรียน" ว่าง, รายชื่อดูเหมือนกรองเหลือแค่ ม.1 ทั้งที่ผู้จัดการนี้ควรเห็นทุกคน (school-wide)
- **Root Cause:** seed_users.py สร้างตำแหน่งพิเศษด้วย `room_id NULL` (ไม่ได้อยู่ในห้องใด — ตรงกับ concept "ไม่ได้สังกัดห้อง"); แต่ `list_students()` ใช้ `JOIN rooms r ON r.id = s.room_id` (INNER) → ทุกแถวที่ `room_id NULL` ถูกตัดออกจากผลลัพธ์ **เงียบ ๆ** ไม่มี error → ผู้จัดการ school-wide จึงมองไม่เห็น/จัดการสมาชิกตำแหน่งพิเศษกลุ่มเดียวกัน (กลุ่มสภาที่ส่วนใหญ่เป็น room-less) เลย และหน้าดูเหมือน "เห็นไม่ครบ/กรองแค่ระดับชั้นเดียว"
- **Correct Pattern/Solution:** เปลี่ยนเป็น `LEFT JOIN rooms r ON r.id = s.room_id` → แถว room-less ยังคืนมา (`room_code/room_name/level = NULL`) เงื่อนไข scope เดิมไม่รั่ว: ผู้จัดการแบบ grade-scoped (teacher/ประธานระดับ) ที่กรอง `r.level = $n` ยังตัด room-less อัตโนมัติ (เพราะ r.level เป็น NULL ไม่ตรง filter) ส่วนผู้จัดการ school-wide (ไม่ส่ง level) จะเห็น room-less ด้วย ด้าน schema ต้องเผื่อ null แล้ว (`StudentOut.room_code: Optional`) และ UI ต้องแสดง `'—'` เมื่อไม่มีห้อง
- **กฎ: ตารางที่ "ตำแหน่งพิเศษ" เก็บด้วย FK เป็น NULL (เช่น room_id) → ถ้าต้องแสดง/จัดการสมาชิกทุกคน ให้ใช้ LEFT JOIN แล้วปล่อยให้ filter ฝั่งคอลัมน์ของตารางอ้างอิง (เช่น r.level) ตัดเอง; INNER JOIN จะกลืนข้อมูล room-less ไปเงียบ ๆ ตรวจโดยนับแถว `WHERE <fk> IS NULL` ว่าควรโผล่ในรายการหรือไม่**
- **Date Added:** 2026-09-06

### 🛠️ `LIMIT` hardcode ในรายชื่อ (500) → หน้า User Management เห็นแค่ "นักเรียน ม.1" ทั้งที่เห็นทั้งโรงเรียน
- **Context/Problem:** หน้า "จัดการสมาชิก" (GET /students) เมื่อ login ด้วยบัญชีครู/Admin ที่ไม่ได้สังกัดห้อง (school-wide) → รายชื่อมา**เพียง 500 คน และเป็นนักเรียน ม.1 ล้วน** ทั้งที่ควรได้ทั้งโรงเรียน ไม่เกี่ยวกับ grade scope
- **Root Cause:** `student_service.list_students()` hardcode `LIMIT 500` (default) และ `ORDER BY r.room_code, s.student_no` → รหัสห้อง ม.1 เรียงก่อน ถ้าโรงเรียนมีนักเรียนเกิน 500 คน คิวรีตัดที่ 500 คนแรกซึ่งเป็นห้อง ม.1 ทั้งหมด → ดูเหมือน "กรองเหลือแค่ ม.1" จริง ๆ คือข้อมูล**ถูกตัด** ฝั่ง frontend `UserManagement.vue` โหลด `listStudents()` ครั้งเดียว (ไม่มี param) แล้วกรอง group/search **ใน memory** → รับมาแค่ 500 ก็เห็นแค่ 500
- **Correct Pattern/Solution:** ปลดล็อก limit — `list_students(..., limit: Optional[int] = None)`; ต่อ LIMIT ลง SQL **เฉพาะเมื่อส่ง limit** (`if limit is not None`) — endpoint รายชื่อ (GET /students) ที่บังคับ `MANAGE_STUDENTS` + grade/hierarchy scope ไว้แล้ว คืนได้ทั้งชุดในขอบเขต (ทั้งโรงเรียน ~2-3 พันคน JSON < 1 MB); ถ้าจะ cap จริง (เช่น dropdown) ให้ส่ง limit อย่างชัดเจน
- **กฎ: endpoint "รายชื่อ" ที่ฝั่ง UI โหลดครั้งเดียวแล้วกรอง client-side → backend ต้องคืนครบทั้งชุด (อย่า hardcode LIMIT เล็ก ๆ เงียบ ๆ); ถ้ามีหน้า/ส่วนที่ต้องการ cap ให้รับ `limit` เป็น param ที่ชัดเจน; อาการ "เห็นแค่กลุ่ม/ชั้นแรก" ที่ข้อมูลเรียงตาม key → ให้นับแถวรวมใน DB เทียบกับจำนวนที่คืน ก่อนสรุปว่าเป็น bug ของ filter**
- **Date Added:** 2026-09-06

### 🛠️ `received=true` เดิม = exact-level match — ติ๊กมองระดับล่างต้องรู้จัก "band ≤ ตัวเอง" + scope ซ้อนทับ
- **Context/Problem:** ต้องการให้คนระดับสูง (room→level→council ตามพีระมิด) กดเลือกดู "เรื่องที่รับ" ของระดับล่างได้ เช่น สภา (council) ขอดูเรื่องระดับห้อง/ระดับชั้นได้ หัวหน้าห้องอยากดูได้เฉพาะของตัวเอง — เดิม `list_issues(received=True)` เป็น exact-level match (branch แยก per ระดับ: council→เฉพาะ council, level→เฉพาะ level ในชั้น, room→เฉพาะ room ในห้อง)
- **Root Cause:** ถ้าเปลี่ยนเป็น "ให้สูงกว่าดูระดับล่างได้" โดยไม่คิดให้ถี่ จะทำพัง backward-compat (default ควรเป็นระดับตัวเองพอดีเหมือนเดิม) และ scope ของระดับล่างยังต้องบังคับ (room→ห้องตัวเอง, level→ชั้นตัวเอง) แม้คนขอดูเป็น council; สิ่งที่ "สูงกว่าดูได้" ไม่ใช่แค่ level แต่เป็น **ระดับที่มี rank ≤ rank(ผู้ดู)** (band) ประกอบกับ scope ห้อง/ชั้นของระดับนั้น
- **Correct Pattern/Solution:** เพิ่ม param `levels` (comma: `room,level,council`) ใช้กับ `received=True` เท่านั้น: `band = [lv for lv in LEVEL_ORDER if LEVEL_RANK[lv] <= LEVEL_RANK[user_level]]`; `req = {user_level}` ถ้าไม่ส่ง (default = เดิมเป๊ะ) / ตัด `levels.split(',')` ด้วย `& band`; scope ต่อระดับ: `council` → `scope=None` (ทั้งโรงเรียน, ไม่ผูกห้อง), `room`/`level` → `scope_room_ids` จากสิทธิ์ตัวเอง (`room_ids` / `_level_room_ids(ชั้น)`) ใส่ `current_level='X' AND room_id = ANY($n)`; `scope == []` → ข้ามเงื่อนไข (fail-closed) ถ้าได้ `conds` ว่าง → `1 = 0`; validate token ไม่อยู่ใน LEVEL_ORDER → 400 ที่ router; ส่ง SQL ผ่าน params list เดียว (index `$len(params)+1`)
- **กฎ: ฟีเจอร์ "ผู้สูงกว่าดูเรื่องระดับล่าง" ต้องแยก 2 มิติ: (1) band ระดับที่มองได้ = rank ≤ rank(ตัวเอง) — มองขึ้นไม่ได้, (2) scope ห้อง/ชั้นของแต่ละระดับล่างยังบังคับเหมือนเดิม (สูงสุด = ยอดพีระมิด → scope None = ทั้งโรงเรียน); default ต้องเทียบเท่าโค้ดเดิมเป๊ะ (ถอยหลังได้) แล้วค่อยยอมรับ param เพิ่ม**
- **Date Added:** 2026-09-06

### 🛠️ Avatar ภาษาไทย: ตัวแรกของ `full_name` = คำนำหน้า (ด.ช./ด.ญ./นาย) ไม่ใช่ชื่อ — ต้องมี `first_name` แยก
- **Context/Problem:** ผู้ใช้ขอให้ avatar (วงกลมตัวอักษร) เป็น "ตัวแรกของชื่อ" ทุกจุด แต่แต่ละหน้ากันคนละแหล่ง: บางที่ `full_name.charAt(0)` (ได้ตัวแรกของคำนำหน้า เช่น ด จาก "ด.ช."), บางที่ชื่อเล่น (nickname), บางที่ชื่อจริง — ไม่สม่ำเสมอ
- **Root Cause:** ชื่อไทยเก็บเป็น `prefix + first_name + last_name` (`CONCAT_WS`) → เอา char แรกของชื่อรวม = คำนำหน้า; และ avatar ถูกคำนวณ inline ซ้ำหลายที่โดยดึงจาก field ต่างกัน; `/auth/me` (UserOut) ไม่เคย expose `first_name` (มีแต่ `full_name`) ส่วนคอมเมนต์ snapshot ชื่อเต็มไว้ (commenter_name) โดยไม่เก็บ first_name แยก
- **Correct Pattern/Solution:** ให้ทุก avatar site ใช้ "ตัวแรกของ `first_name`" โดย backend ต้องส่ง first_name มาด้วย: (1) `get_user_roles` SELECT `s.first_name` → ใส่ใน role dict → `make_user_out` เอา role แรกที่ไม่ว่างเป็น top-level `first_name` (UserOut เพิ่ม field) → header/sidebar ใช้ `user.first_name || full_name || username`; (2) คอมเมนต์ในเรื่อง (`issue_comments`) อ่านด้วย `SELECT *` → ต้อง **denormalize เก็บ `commenter_first_name` ตอน insert** (migration เพิ่ม column; คอมเมนต์เก่าเป็น NULL → frontend fallback `commenter_first_name || commenter_name`); (3) คอมเมนต์ board (`piri_board_comments`) กลับ JOIN `s_comm.first_name` ตอนอ่านทุกครั้งอยู่แล้ว → ไม่ต้อง column แค่เพิ่ม `"commenter_first_name": row.get("first_name")` ใน dict; หน้าโปรไฟล์มี first_name อยู่แล้ว → เปลี่ยนจาก `nickname || first_name` เป็น `first_name`
- **กฎ: ชื่อไทยมีคำนำหน้า → ถ้าต้อง "ตัวแรกของชื่อ" อย่า `full_name.charAt(0)`; backend ต้อง expose `first_name` (ไม่ใช่ประกอบจากชื่อเต็ม); ตารางที่อ่านด้วย `SELECT *` แล้วชื่อถูก snapshot ตอน insert ต้องมีคอลัมน์ first_name แยก (migration) แต่ตารางที่ JOIN ตอนอ่านทุกครั้ง derive จาก JOIN ได้เลยไม่ต้อง column; avatar ทุกจุดควร fallback เป็นสายเดียวกัน `first_name → full_name/commenter_name → username`**
- **Date Added:** 2026-09-06

### 🛠️ audit_logs ว่างเป็นช่อง ๆ — `execution_time_ms` 100% NULL เพราะไม่มีใครวัด, `room_id` 94.7% NULL เพราะ caller ลืมส่ง
- **Context/Problem:** ตรวจ production (18,019 แถว) พบ `execution_time_ms` ว่าง **100%**, `room_id` 94.7%, `entity_id` 42%, `ip_address`/`user_agent` 3.2%, `endpoint_or_command` 1% → audit ดูย้อนหลังได้ไม่ครบ ("ใครทำ ที่ห้องไหน นานแค่ไหน" ตอบไม่ได้)
- **Root Cause:** `AuditLogger.log()` รับทุกคอลัมน์เป็น parameter แต่ **ไม่มีอะไรบังคับว่าต้องส่ง** — ค่าที่ caller ไม่ส่งกลายเป็น NULL เงียบ ๆ: `execution_time_ms` ไม่มี caller ส่งเลยแม้แต่ที่เดียว (34/37 call site ไม่มี), `room_id` มีคนส่ง 13/37, `endpoint_or_command` 9/37 ; และ middleware เดิมตั้ง context แค่ ip/user-agent/trace_id ไม่มี endpoint/เวลาเริ่ม จึงเติมให้ไม่ได้
- **Correct Pattern/Solution:** แก้ 2 ชั้นพร้อมกัน — (1) **ชั้นโค้ด**: `AuditLogger.log()` เติมทุกคอลัมน์เองจาก fallback chain `param → request context → DB → sentinel` (room_id หาจาก `students.room_id`/`rooms.owner_id` ของผู้กระทำ + cache ใน context ต่อ request ⇒ 1 request = 1 query; execution_time_ms = `time.monotonic() - ctx["started_at"]`; endpoint = `METHOD path` จาก middleware) โดย **context ชนะ param** เพราะ path จริงถูกต้องกว่าค่าที่ caller พิมพ์เอง (`"POST /auth/login"` ขาด prefix `/api`); (2) **ชั้นสคีมา**: บังคับ `NOT NULL + DEFAULT` ทุกคอลัมน์ (migration 013) ⇒ call site ใหม่ที่ลืมส่งค่าก็ไม่ทำให้เกิดช่องว่างอีก — ค่า sentinel `'-'` (ไม่ทราบ), `{}` (ไม่มี old/new), `-1` (ไม่ระบุห้อง/ตัวตน), `0` (วัดเวลาไม่ได้) ; **งานที่ไม่ผ่าน HTTP (ARQ worker) ต้องครอบ `with audit_scope(endpoint=...)`** ไม่งั้น context ว่าง = ได้ sentinel (worker ไม่มี middleware)
- **แถม (bug แฝงที่เจอตอนแก้):** FK เดิม `room_id ... ON DELETE CASCADE` = **ลบห้อง 1 ห้อง → ประวัติ audit หายทั้งห้อง** และ `user_id ... ON DELETE SET NULL` = ลบผู้ใช้ → ไม่รู้ว่าใครทำ → migration 013 **ถอด FK ของ 2 คอลัมน์นี้ออก** (audit เป็นบันทึกประวัติ ต้องอยู่ครบตลอดไป — เก็บเป็นเลขแล้ว join เอาเองเมื่อแถวยังอยู่)
- **กฎ: ตาราง audit/ประวัติ ต้องบังคับ NOT NULL ทุกคอลัมน์ที่ DB + เติมค่าใน logger ด้วย fallback chain (param → context → DB → sentinel) อย่าฝากความครบถ้วนไว้กับการที่ caller "ต้องจำส่ง"; คอลัมน์ที่ derive ได้จาก DB (เช่นห้องของผู้กระทำ) ให้ logger หาเองพร้อม cache ต่อ request; ตาราง audit ห้ามใช้ FK แบบ CASCADE/SET NULL — มันลบประวัติทิ้ง**
- **Date Added:** 2026-09-25

### 🛠️ หลัง Traefik + Cloudflare: `request.client.host` และ `X-Forwarded-For` **ใช้ไม่ได้ทั้งคู่** — ต้องอ่าน `CF-Connecting-IP`
- **Context/Problem:** `audit_logs.ip_address` ของ production เป็น `10.0.0.2` เกือบทั้งหมด (ตรวจแล้วไม่มี traffic จากภายนอกเลยทั้งที่ระบบเปิดให้ใช้จริง) → ตามรอย "ใครเข้ามาจากไหน" ไม่ได้ และ security review อ่านผิดว่า "ไม่มีคนนอกเข้าระบบ"
- **Root Cause:** **สองชั้นซ้อนกัน** ไม่ใช่ชั้นเดียว — (1) backend รัน 3 replica อยู่หลัง Traefik → `request.client.host` คือ IP ของ **Traefik** ไม่ใช่ IP ผู้ใช้จริง (TCP connection จบที่ proxy); (2) แต่พอแก้อ่าน `X-Forwarded-For` แล้ว **ยังได้ `10.0.0.2` อยู่ดี** เพราะ (2a) Docker Swarm publish พอร์ตแบบ `PublishMode: ingress` → routing mesh **SNAT source IP ทิ้งตั้งแต่ก่อนถึง Traefik** และ (2b) Traefik v3 ค่า default `forwardedHeaders.insecure=false` → **เมิน XFF ที่ Cloudflare ส่งมา แล้วเขียนทับด้วย peer IP ของตัวเอง** ⇒ XFF ที่ถึง backend เป็นค่าที่ Traefik ใส่เอง ไม่ใช่ของ Cloudflare
- **วิธีพิสูจน์ (ทำแล้ว):** ยิง `curl` ตรงเข้า backend ด้วย `X-Forwarded-For: 203.0.113.9` → บันทึกได้ `203.0.113.9` เป๊ะ = **โค้ดแอปถูก ปัญหาอยู่ที่ infra ข้างหน้า** ; แล้วยิงผ่าน Cloudflare จริง → ได้ `10.0.0.2` ⇒ ยืนยันว่า Traefik ทับ XFF จริง (อย่าไล่หาบั๊กในโค้ดก่อนพิสูจน์ข้อนี้)
- **Correct Pattern/Solution:** อ่าน **`CF-Connecting-IP` ก่อน** (header ที่ Traefik ไม่ยุ่งด้วย จึงรอดมาถึง backend) → แล้วค่อย fallback `X-Forwarded-For` ตัวซ้ายสุด → `X-Real-IP` → `request.client.host`; normalize ก่อนเก็บ (ตัด port, ตัด `::ffff:`, จำกัด 45 ตัวอักษรตาม `VARCHAR(45)`) — ใน helper ตัวเดียว (`_client_ip(request)`) แล้วให้ middleware เรียก ; ทางเลือกฝั่ง infra คือเปิด `forwardedHeaders.trustedIPs` ที่ Traefik แต่ **entrypoint นี้ใช้ร่วมกับทุกเว็บใน stack `global` — แก้แล้วกระทบ production ทั้งเครื่อง** จึงเลือกแก้ฝั่งแอป
- **⚠️ ขอบเขตความเชื่อถือ:** header เหล่านี้ **ปลอมได้** ถ้ามีใครยิงเข้า origin port 80 ตรง ๆ ข้าม Cloudflare → ยัง**ใช้เป็นหลักฐานไม่ได้เต็มร้อย** จนกว่าจะล็อก firewall ของ origin ให้รับเฉพาะ IP range ของ Cloudflare
- **กฎ: อยู่หลัง proxy หลายชั้น (Cloudflare → Swarm ingress → Traefik) ห้ามเดา header — พิสูจน์ทีละชั้นด้วยการยิง header ปลอมตรงเข้า backend; ใช้ `CF-Connecting-IP` เมื่อผ่าน Cloudflare; ถ้าแก้ที่ proxy ไม่ได้/เสี่ยงเกินไป (entrypoint ร่วม) ให้แก้ที่แอป; อาการ "IP เดียวกันหมด/เป็น IP วงใน" = อ่านผิดชั้น (และถ้าแก้ XFF แล้วยังเป็น IP เดิม = ถูก proxy ทับ)**
- **Date Added:** 2026-09-25 · **Updated:** 2026-09-26 (แก้ให้ตรงความจริงหลังพบว่า XFF ใช้ไม่ได้ — เดิมบันทึกไว้ผิด)

### 🛠️ ตาราง audit/ประวัติ ห้าม FK แบบ `ON DELETE CASCADE` / `SET NULL` — มันลบประวัติทิ้ง
- **Context/Problem:** ออกแบบ `audit_logs` ให้ `room_id INTEGER REFERENCES rooms(id) ON DELETE CASCADE` และ `user_id INTEGER REFERENCES users(id) ON DELETE SET NULL` (ดูเหมือน "สะอาด" — ไม่มี orphan) แต่ผลจริงคือ **ลบห้อง 1 ห้อง = ประวัติ audit หายทั้งห้อง** และ **ลบผู้ใช้ = ไม่รู้ว่าใครทำ** ซึ่งทำให้ audit ตรวจย้อนหลังไม่ได้ = ขัดกับวัตถุประสงค์ของตารางเอง
- **Root Cause:** FK constraint บังคับ *ความสมบูรณ์ของข้อมูลปัจจุบัน* แต่ตารางประวัติต้องรักษา *ความจริง ณ เวลาที่เกิดเหตุ* — สองเป้าหมายนี้ขัดกัน ⇒ การผูก FK จากตารางประวัติไปยังตารางที่ถูกลบได้ จึงเลือกได้แค่ "ลบประวัติตาม" หรือ "ทำให้ข้อมูลอ้างอิงหาย" ไม่มีทางเลือกที่ถูก
- **Correct Pattern/Solution:** **ไม่ใส่ FK** บนคอลัมน์อ้างอิงของตารางประวัติ — เก็บเป็นเลข/สตริงล้วน แล้ว JOIN เอาเองตอนอ่าน (`LEFT JOIN rooms r ON r.id = a.room_id` — **LEFT** เพราะแถวที่ไม่มีห้องต้องยังออกมา) ; ค่าที่ "ไม่ระบุ/ไม่รู้จัก" ใช้ sentinel `-1` (คอลัมน์ข้อความใช้ `'-'`); **ห้ามกรอง `r.deleted_at IS NULL` ตอน join ประวัติ** เพราะต้องอ่านชื่อห้องที่ถูกลบไปแล้วได้ (ประวัติต้องตรงกับความจริง ณ ตอนนั้น ไม่ใช่สถานะปัจจุบัน)
- **⚠️ ลำดับใน migration:** ถ้าจะเปลี่ยนจาก "มี FK" เป็น "ใช้ sentinel -1" ต้อง `DROP CONSTRAINT` **ก่อน** UPDATE เติม `-1` เสมอ ไม่งั้น `ForeignKeyViolationError` (และถ้าจะมี sentinel row จริงในตารางปลายทาง ระวัง fixture ที่ TRUNCATE ระหว่างเทสต์จะลบมันทิ้ง → ทางที่ถูกคือถอด FK ไม่ใช่สร้างแถวปลอม)
- **กฎ: ตาราง audit/log/ประวัติ — ห้าม FK ที่มี `ON DELETE` action ใด ๆ บนคอลัมน์อ้างอิง; เก็บ id เปล่า + join เอาเอง; อ่านประวัติต้องไม่กรอง soft-delete ของตารางที่ถูกอ้าง; ถ้าจำเป็นต้องมี FK จริง ๆ ให้ใช้ `ON DELETE RESTRICT`/`NO ACTION` เพื่อบังคับให้คิดก่อนลบ ไม่ใช่ให้ DB ลบประวัติให้เงียบ ๆ**
- **Date Added:** 2026-09-26

### 🛠️ เพิ่ม permission ใหม่ใน `roles.json` ไม่พอ — `students.permissions` เป็น snapshot ที่ไม่มีใคร sync ให้
- **Context/Problem:** เพิ่ม permission `MANAGE_ANNOUNCEMENTS` แล้วเติมใน `config/roles.json` ของ `council_member` เรียบร้อย เทสต์ใหม่ผ่านหมด — แต่ **ผู้ใช้สภานักเรียนที่มีอยู่จริงจะไม่เห็นเมนูเลย** และ **ไม่มี error อะไรโผล่มาให้ตามหา** (ไม่ใช่ 403 — เมนูไม่ขึ้นเลยเพราะ frontend เช็ค `authStore.hasPermission()` จาก `permissions` ที่ยังเป็นชุดเก่า)
- **Root Cause:** `students.permissions` (JSONB array) เป็น **snapshot ที่ถูกเขียนทับเฉพาะตอน register / import Excel / เปลี่ยนตำแหน่ง** (`auth_service.py:204,262` · `import_service.py:485,603` · `student_service.py:228,251,327` · `seed_users.py:101`) — **ไม่มีกลไก reconcile จาก `roles.json` → DB ย้อนหลังเลย** ⇒ `roles.json` มีผลกับ **คนที่สร้างใหม่หลังแก้** เท่านั้น ส่วนคนเดิมถือสำเนาของเวอร์ชันเก่าติดตัวไปตลอด
- **Correct Pattern/Solution:** ทุกครั้งที่เพิ่ม/ลบ permission ใน `roles.json` **ต้องมี migration ที่ backfill `students.permissions` ด้วยเสมอ** — รันในไฟล์ migration (`upgrade(conn)`) พร้อมกับ DDL อื่นของฟีเจอร์นั้น โดยเขียนให้ idempotent และครอบ 3 กรณี: (1) `NOT (COALESCE(permissions,'[]'::jsonb) @> $1::jsonb)` กันเติมซ้ำเมื่อรัน migration ซ้ำ, (2) `COALESCE(permissions, '[]'::jsonb)` เพราะแถวเก่ามี `permissions` เป็น NULL ได้ และ (3) `deleted_at IS NULL` เพื่อไม่ไปปลุกสิทธิ์ของผู้ใช้ที่ถูกลบไปแล้ว ; **เทสต์ migration ต้องเรียก `upgrade()` ตรง ๆ** (ไม่ใช่พึ่ง `init_db`) เพราะ migration รันตอน startup *ก่อน* ที่ผู้ใช้ทดสอบจะถูกสร้าง ⇒ ถ้าเทสต์ผ่านแค่ path ปกติ จะไม่มีทางจับ bug นี้ได้เลย
- **⚠️ กับดักตอนเทสต์:** `init_db` ที่มี `CREATE TABLE IF NOT EXISTS` + คอลัมน์ใหม่ จะทำให้ DB ทดสอบ "มีคอลัมน์พร้อมใช้ตั้งแต่แรก" → เทสต์ migration ที่รัน `upgrade()` จะ no-op แล้วผ่านทั้งที่ไม่ได้พิสูจน์อะไร ⇒ ต้อง **จำลอง DB เก่าก่อน** (`ALTER TABLE ... DROP COLUMN IF EXISTS`) แล้วค่อย `upgrade()` และ assert ว่าคอลัมน์กลับมา + สิทธิ์ถูกเติม
- **กฎ: `roles.json` = แม่แบบสำหรับ *ผู้ใช้ใหม่* เท่านั้น ไม่ใช่แหล่งความจริงของสิทธิ์ปัจจุบัน; เพิ่ม permission ใหม่ = ต้องมี migration backfill เสมอ (idempotent + ครอบ NULL + ข้ามแถวที่ถูกลบ); เทสต์ migration ต้อง simulate สคีมาเก่าและเรียก `upgrade()` ตรง ๆ — การไม่มี error ไม่ได้แปลว่าสิทธิ์ถึงมือผู้ใช้**
- **Date Added:** 2026-09-27

### 🛡️ `<a :href="userData">` = ช่อง XSS — `javascript:` / `data:` ต้องถูกกันตั้งแต่ชั้น schema
- **Context/Problem:** ประกาศบนหน้า Landing Page เดิมมีคอลัมน์ `link` ที่ถูก seed จาก SQL ตรง ๆ (ไม่มีทางเขียนผ่าน UI) พอเปิดให้ผู้ใช้กรอกได้ (`Landing.vue` ผูก `<a :href="a.link">` ตรง ๆ) ช่องนี้กลายเป็น XSS ที่ทำงาน *ทันทีที่คลิก* — `javascript:...` รันใน origin ของเรา และ `data:text/html,...` พาไปหน้าที่เราคุมไม่ได้
- **Root Cause:** Vue escape **ข้อความ** ให้อัตโนมัติ แต่ **ไม่ validate `href`** — attribute ที่เป็น URL รับ scheme อะไรก็ได้ที่ browser รู้จัก (`javascript:`, `data:`, `vbscript:`) ⇒ การ bind ค่าจากผู้ใช้เข้า `href` ต้องถือว่าเป็น "การ inject โค้ด" ไม่ใช่ "การแสดงข้อความ"
- **Correct Pattern/Solution:** validate ที่ **ชั้น Pydantic schema** (ไม่ใช่แค่ frontend เพราะยิง API ตรง ๆ ก็ต้องกันได้ และไม่ใช่แค่ sanitize ตอน render เพราะค่าที่ไม่ดีจะเข้า DB ไปแล้ว): strip → ค่าว่าง/มีแต่ช่องว่าง → `None` (ไม่เก็บสตริงว่าง) → ถ้าไม่ขึ้นต้นด้วย `http://` / `https://` → `ValueError` ⇒ ได้ 422 อัตโนมัติ ; เขียน helper ตัวเดียวใช้ร่วมกันทั้ง Create และ Update schema ; เทสต์แบบ `@pytest.mark.parametrize` ครอบ `javascript:`, `JavaScript:` (ตัวพิมพ์ใหญ่!), `data:`, `ftp:`, path สัมพัทธ์
- **⚠️ อย่าลืมฝั่งอ่านด้วย:** ถ้าแสดงลิงก์เป็นข้อความควรมี `rel="noopener noreferrer"` คู่กับ `target="_blank"` (กัน reverse tabnabbing) และ **`link` ที่ NULL ต้อง render ได้** — `<a href>` ที่ `v-if` ไม่ครอบจะได้ `href=""` ซึ่ง reload หน้าปัจจุบัน
- **กฎ: ทุก attribute ที่เป็น URL และค่ามาจากผู้ใช้ (`href`, `src`, `action`, `formaction`, `xlink:href`) ต้อง validate scheme ที่ชั้น schema ด้วย allowlist (`http`/`https`) ไม่ใช่ denylist; ค่าว่าง normalize เป็น NULL; อย่าพึ่งการ escape ของ template engine กับ attribute ที่เป็น URL**
- **Date Added:** 2026-09-27

### 🛠️ อัป backend ฝ่ายเดียวบน staging = frontend เก่าเจอ endpoint ที่ถูกถอดไปแล้ว (`students/import` → 405)
- **Context/Problem:** deploy backend ใหม่ขึ้น staging โดยยังไม่ rebuild frontend (ตั้งใจอัปฝ่ายเดียว) — `/health` ผ่าน, public endpoint ตอบ 200, เทสต์ครบ ⇒ ดูเหมือนปลอดภัย แต่หน้าที่ "นำเข้านักเรียน" ในเว็บ **กดแล้วพัง** เพราะ frontend ที่เสิร์ฟอยู่เรียก `POST /api/students/import` ซึ่ง backend ใหม่ไม่มีแล้ว (เปลี่ยนเป็น flow รับ job: `POST /api/upload-student-excel` → `POST /api/start-import-job/{job_id}` + `GET /api/import-jobs`)
- **Root Cause:** สองอย่างประกอบกัน — (1) route เก่าถูก **ถอดออกจริง** ไม่ได้เหลือ alias ไว้ (2) พอ path ไม่มีแล้ว มัน **ไม่คืน 404** อย่างที่คาด แต่ `POST /api/students/import` ไปแมตช์กับ `/api/students/{student_id}` ที่มีแต่ `PATCH` ⇒ ได้ **405 Method Not Allowed** ซึ่งอ่านแล้วชวนคิดว่า "ยิงผิด method" ไม่ใช่ "endpoint ถูกถอด" ⇒ เสียเวลาไล่หาผิดที่ ; และ frontend ที่ build แล้วฝัง URL ไว้ตายตัว แก้ทีหลังไม่ได้
- **วิธีตรวจก่อน deploy ฝ่ายเดียว (ทำแล้วได้ผล):** เทียบ **route set** ของ backend ที่รันอยู่กับ path ที่ frontend ที่ *เสิร์ฟจริง* เรียก — ฝั่ง backend: `docker exec <cid> python -c "from main import app; print(sorted({r.path for r in app.routes}))"` ; ฝั่ง frontend **อย่าดูแค่ image tag** ให้ grep ไฟล์ build ใน container: `docker exec <fid> grep -o "students/import" /usr/share/nginx/html/assets/*.js | wc -l` เทียบกับ `grep -o "upload-student-excel" ...` ⇒ รู้ทันทีว่า build ไหนถูกเสิร์ฟ และมันเรียก API ชุดไหน
- **กฎ: staging/production ต้องอัป backend กับ frontend **พร้อมกัน** เสมอ — SPA ฝัง URL ไว้ในไฟล์ build การเปลี่ยน route ฝั่ง backend จึงเป็น breaking change ที่ไม่ error ตอน deploy; ก่อน deploy ฝ่ายเดียวให้เทียบ route set กับ path ที่ build ที่เสิร์ฟจริงเรียก; อาการ "405" จาก path ที่เคยมี = สงสัยว่า endpoint ถูกถอด ไม่ใช่ยิงผิด method**
- **Date Added:** 2026-09-27

### 🔥 migration ที่รันแล้วทำให้ `docker service update --image <เก่า>` **rollback ไม่ได้อีกต่อไป**
- **Context/Problem:** วางแผน rollback ของ staging ว่า "ถ้าพังก็ `docker service update --image prsc-prsc_staging-backend:c219c3c` กลับ" — ดูปลอดภัยเพราะ image เก่ายังอยู่ครบ **แต่ใช้ไม่ได้จริง** หลัง migration รันไปแล้ว: image เก่าจะเขียน `audit_logs` ไม่ผ่าน ⇒ **ทุก mutation ที่มี audit (สร้าง/แก้/ลบ issue, student, ...) ตอบ 500** ทั้งระบบ
- **Root Cause:** migration 013 บังคับ `NOT NULL + DEFAULT` ทุกคอลัมน์ของ `audit_logs` แต่ `core/logger.py` ของ image เก่า **ส่ง NULL มาตรง ๆ** ในหลายคอลัมน์ (`entity_id` เขียนว่า `str(entity_id) if entity_id else None`, `old_values`/`new_values` เป็น `None` เมื่อไม่มีค่า, `room_id`/`user_id`/`error_detail` ส่งผ่าน param ที่ default `None`) ⇒ **DEFAULT ของ Postgres ไม่ช่วย เพราะมันมีผลเฉพาะเมื่อ "ไม่ระบุคอลัมน์" ไม่ใช่เมื่อ "ส่ง NULL มา"** จึงได้ `NotNullViolationError` ; ยิ่งไปกว่านั้น migration 013 **ถอด FK ของ `room_id`/`user_id` ออก** และ 012/013 เพิ่มคอลัมน์อื่น ⇒ ต่อให้แก้ NULL ได้ สคีมาก็ไม่ตรงกับที่โค้ดเก่าคาดอยู่ดี
- **วิธีพิสูจน์แบบไม่ทำลายข้อมูล:** จำลอง INSERT ของโค้ดเก่าใน transaction แล้ว **`await tr.rollback()` เสมอ** (ไม่ commit) — ได้ `NotNullViolationError: null value in column "room_id"` ทันที แล้ว query ซ้ำว่าไม่มีแถวขยะค้าง ; วิธีนี้ตอบคำถาม "rollback ได้ไหม" ได้จริงโดยไม่ต้อง deploy อะไรเลย
- **กฎ: migration ที่รันแล้ว = จุดที่เปลี่ยนเกม — ก่อนจะบอกว่า "rollback ได้" ต้องเช็คว่าโค้ดเก่าเขียนสคีมาใหม่ไหวไหม (โดยเฉพาะคอลัมน์ที่เพิ่งกลายเป็น NOT NULL) ไม่ใช่แค่ "image เก่ายังอยู่"; backfill + NOT NULL + ถอด FK คือการเปลี่ยนสัญญาระหว่างโค้ดกับ DB ที่ image เก่าไม่รู้เรื่อง; ถ้าต้อง rollback จริงต้องถอยสคีมาด้วย (เขียน migration `downgrade` หรือ restore backup) ไม่ใช่แค่สลับ image**
- **Date Added:** 2026-09-27

### 🛠️ image ที่ค้างเก่านานอาจ **ไม่มี `backend/migrations/` เลย** — deploy ครั้งเดียวรัน migration ย้อนหลังยกชุด
- **Context/Problem:** deploy backend ขึ้น staging แล้วพบว่า `schema_migrations` **ทั้ง 14 แถวมี `applied_at` ตรงกันถึงระดับไมโครวินาที** — ถ้าอ่านผ่าน ๆ จะคิดว่า "migration ผมรันแถวเดียว" แต่ความจริงคือ **001–014 รันพร้อมกันทั้งหมด** เพราะ image ที่ staging รันมาตั้งแต่ 9 ส.ค. **ไม่มีโฟลเดอร์ `backend/migrations/`** ⇒ สคีมาถูกสร้างจาก `init_db` เท่านั้นมาตลอด 3 สัปดาห์ และการ deploy นี้เป็นครั้งแรกที่ staging เข้าสู่ระบบ migration
- **Root Cause:** `core/migrations.py` ห่อทั้ง loop ด้วย `conn.transaction()` เดียว และ Postgres `CURRENT_TIMESTAMP` คืน **เวลาเริ่ม transaction** (ไม่ใช่เวลาที่แต่ละ statement รัน) ⇒ migration ที่รันพร้อมกันจึงได้ timestamp เท่ากันเป๊ะ — **นี่คือลายนิ้วมือของ "รันยกชุด" ไม่ใช่ความบังเอิญ** ; และ schema ที่โตด้วย `CREATE TABLE IF NOT EXISTS` จะ **ไม่ยอมรับ ALTER ของ migration** (เพราะตารางมีอยู่แล้ว) ⇒ โค้ดใหม่กับ DB เก่าอยู่ร่วมกันได้เงียบ ๆ จนกว่าจะมี migration วิ่ง
- **วิธีตรวจก่อน deploy (ถูกและเร็ว):** `git ls-tree --name-only <commit ของ image> backend/migrations/` — ว่างเปล่า = image นั้นไม่รู้จัก migration เลย ⇒ **deploy ครั้งนี้จะรัน migration ทั้งหมดที่สะสมมา** ไม่ใช่แค่ตัวใหม่ ; ยืนยันทีหลังด้วย `SELECT version, applied_at FROM schema_migrations` แล้วนับว่าได้ timestamp ไม่ซ้ำกันกี่ค่า
- **กฎ: ก่อน deploy ให้เช็คว่า image ปลายทางมี `backend/migrations/` ไหม และเทียบว่ามีกี่ตัวที่ยังไม่รัน (image เก่านาน = อาจรันย้อนหลังทั้งชุดพร้อมกัน ซึ่งรวม migration ของฟีเจอร์ที่คนอื่น merge ไปแล้ว); `applied_at` ที่เท่ากันทุกแถว = รันใน transaction เดียว ไม่ใช่เรื่องบังเอิญ; อย่าอ่าน `schema_migrations` แค่ "ตัวใหม่รันหรือยัง" ให้ดูว่า **มีอะไรรันไปพร้อมกันบ้าง**
- **Date Added:** 2026-09-27

### 🛠️ VPS production มี clone **สองตัววางข้างกัน** — `prsc_test` = staging, `piri_voice` = production (env คนละชุด)
- **Context/Problem:** ต้องเอา branch ที่ยังไม่ merge ขึ้น `prsc-test.pirivoice.com` เพื่อกดเทสก่อน merge — แต่ถ้าไม่รู้ว่าเครื่องนั้นมี repo หลายชุด และแต่ละชุดผูกกับ stack คนละตัว การ `git checkout` ผิดโฟลเดอร์ = **deploy ทับ production ทันที** (คำสั่งเหมือนกันทุกตัวอักษร ต่างกันแค่ cwd)
- **Root Cause:** เครื่อง production (`vmi3511202`, ssh alias `pirivoice-prod`, user `prscportal`) วาง clone ไว้ข้างกันใต้ `/home/prscportal/prsc_portal/` — `prsc_test/` → `.env` มี `ENV_NAME=pirivoice_staging` (โดเมน `prsc-test.pirivoice.com` + `prsc-api-test.pirivoice.com`) และ `piri_voice/` → `ENV_NAME=pirivoice_production` (โดเมน `www.pirivoice.com` + `api.pirivoice.com`) ⇒ **`pull_all.sh` ตัดสินใจว่าจะ deploy stack ไหนจาก `.env` ใน cwd เท่านั้น** ไม่มี argument ให้ระบุ จึงเป็นการเลือกจาก "โฟลเดอร์ที่ยืนอยู่" ล้วน ๆ ; ยังมี `bytebase/` ปนอยู่ด้วย
- **Correct Pattern/Solution:** ยืนยันตัวตนของ clone **ก่อน** ทุกคำสั่งที่เขียน (อ่าน `ENV_NAME` ใน `.env` แล้วเทียบกับ `docker service ls`) — และเพราะ `pull_all.sh` ใช้ `git reset --hard origin/$CURRENT_BRANCH` **ตัว branch ที่ checkout อยู่คือตัวตัดสินว่าจะ deploy โค้ดไหน** ⇒ การเทส branch ที่ยังไม่ merge ทำได้โดย `git fetch origin <branch>` → `git checkout -B <branch> origin/<branch>` → `./pull_all.sh` ; **หลัง merge แล้วต้องพากลับ `main` + deploy ซ้ำ** ไม่งั้น clone จะค้างอยู่บน branch ที่ใครสักคนลบไปแล้ว (ครั้งถัดไปที่รัน `pull_all.sh` จะ fail เพราะ `origin/<branch>` ไม่มี) ; เช็ค `git status --porcelain` ให้ว่างก่อน `reset --hard` เสมอ ไม่งั้นงานที่ยังไม่ commit ในโฟลเดอร์นั้นหายเงียบ
- **⚠️ production ไม่ถูกกระทบ:** stack แยกกันโดยสมบูรณ์ (`pirivoice_staging_*` vs `pirivoice_production_*`) และ image tag ก็แยกตาม commit ⇒ การ deploy staging **ไม่แตะ production** แต่ต้องตรวจให้แน่ใจว่าไม่ได้ `cd` ผิดโฟลเดอร์ ซึ่งเป็นความผิดพลาดเดียวที่ทำลาย production ได้จากงานนี้
- **กฎ: บน VPS ให้ `grep '^ENV_NAME=' .env` ใน cwd และเทียบกับ `docker service ls` ทุกครั้งก่อนสั่ง deploy — อย่าจำจากชื่อโฟลเดอร์; `pull_all.sh` ผูก branch ↔ โค้ดที่จะ deploy ดังนั้น "เทส branch" = "checkout branch"; และเมื่อ merge เสร็จต้องคืน clone กลับ `main` เสมอ**
- **Date Added:** 2026-09-27

### 🛠️ remote shell ของ production เป็น **fish** — ใช้ `ssh <host> bash -s <<'EOF'` แทนการหนี quote
- **Context/Problem:** คำสั่งอ่าน DB / สำรองข้อมูลบน VPS ล้มด้วย error ที่ชี้ผิดที่ไปเรื่อย ๆ ทั้งที่คำสั่งถูกต้องใน bash: `psql: error: ... role "-d" does not exist` (ตัวแปร `$POSTGRES_USER` กลายเป็นสตริงว่าง), `command substitutions not allowed here`, และ glob `~/ops/deploy/prsc*` ไม่ขยาย ⇒ เสียเวลาไล่หาว่า "คำสั่งผิดตรงไหน" ทั้งที่ตัวคำสั่งถูกต้องใน bash
- **Root Cause:** login shell บนเครื่องนั้นเป็น **fish** (ไม่ใช่ bash) — fish ต่างจาก POSIX shell อย่างมีนัยสำคัญ: **ไม่รองรับ `(...)` แบบ grouping** ในหลายบริบท (ใช้เป็น command substitution เท่านั้น), **ไม่รองรับ `$VAR` ในที่ที่ควร** จนบางบริบทขยายเป็นค่าว่างเงียบ ๆ, ไม่ทำ word splitting, ไม่ขยาย glob ในบางตำแหน่ง และใช้ `and`/`or` แทน `&&`/`||` ⇒ คำสั่งที่ทดสอบใน bash บนเครื่อง dev **ไม่ใช่หลักประกันว่าผ่าน fish** ; อันตรายที่สุดคือกรณี `$VAR` ว่าง: คำสั่ง *รันสำเร็จ* แต่ทำงานผิด (`-U` ตามด้วย `-d` กลายเป็น username)
- **Correct Pattern/Solution:** **ส่งสคริปต์ bash ทั้งก้อนเข้า stdin ของ bash บนปลายทาง** — `ssh <host> bash -s <<'EOF' ... EOF` ⇒ คำสั่งที่ fish เห็นมีแค่ `bash -s` (ปลอดภัย ไม่มี metacharacter) ส่วนโค้ดจริงรันใน bash ได้ syntax ปกติครบ (`$(...)`, `((...))`, glob, `&&`), heredoc แบบ `'EOF'` (quote) กันการขยายฝั่ง local, และค่ายังส่งผ่าน pipe ได้ด้วย (`ssh host bash -s < script.sh`) ; ทางเลือกเมื่อต้องอยู่ใน fish จริง ๆ: ห่อคำสั่งที่อยากให้ตัวแปรถูกขยาย **ใน container** ด้วย single quote — `docker exec <db> sh -c 'psql -U $POSTGRES_USER -d $POSTGRES_DB -c "..."'` ⇒ fish ไม่แตะเพราะอยู่ใน quote และ `sh` ใน container เป็นคนขยาย
- **⚠️ อาการที่ต้องสงสัย fish ทันที:** variable ที่ควรมีค่ากลายเป็นว่าง, `command substitutions not allowed here`, `Unknown command`, glob ที่ไม่ขยาย, `&&` ที่ error — **อย่าเพิ่งแก้คำสั่ง ให้สลับไปใช้ `bash -s` ก่อน** แล้วค่อยดูว่ายังพังไหม ถ้าหาย = ปัญหาอยู่ที่ shell ไม่ใช่คำสั่ง
- **กฎ: ห้ามสมมติว่า remote shell เป็น bash — เช็คด้วย `echo $SHELL` (หรือ `$version` ใน fish) ก่อนเขียนคำสั่งยาว ๆ; งานบนเครื่องที่ shell ไม่ใช่ bash ให้ใช้ `ssh <host> bash -s <<'EOF'` เป็นค่าเริ่มต้น เพราะตัดปัญหา quoting ทั้งหมดในทีเดียว; ตัวแปรสภาพแวดล้อมของ container ให้ขยาย *ใน container* เสมอ (`sh -c '...'`) ไม่ใช่บน host**
- **Date Added:** 2026-09-27

### 🛡️ ตรวจ/สำรอง DB บน production โดย**ไม่ให้ credential หลุดออกมา** — ใช้ env ของ container เอง
- **Context/Problem:** ต้องยืนยันว่า migration ทำงานถูก และต้องสำรอง DB ก่อน deploy — แต่ทั้งสองอย่างต้องใช้ connection string ของ production ซึ่งเป็นความลับ และ **ห้ามพิมพ์ลง transcript** (การอ่าน env ของ service ที่รันอยู่ถูกจัดชั้นว่าเป็นการเปิดเผย credential ⇒ ถูกบล็อกและไม่ควรหาเลี่ยง) ; ในทางกลับกัน ต้องตรวจให้ *ลึก* พอที่จะเชื่อได้จริง ไม่ใช่แค่ `curl /health`
- **Root Cause:** ทางที่ดูตรงไปตรงมา (`docker service inspect ... ContainerSpec.Env`, `docker exec <cid> env`, `cat .env`) **พิมพ์ความลับทั้งชุดออกมา** และ `.env` บน VPS ก็มีรหัสจริง ⇒ ต้องเปลี่ยนวิธีคิดจาก "ดึง credential ออกมาแล้วใช้" เป็น **"ให้คำสั่งไปรันในที่ที่ credential อยู่แล้ว"**
- **Correct Pattern/Solution:** สองรูปแบบที่ใช้ได้จริงและปลอดภัย — (1) **รันสคริปต์ Python เข้าไปใน container ของ backend ผ่าน stdin** แล้วอ่านค่าจาก `settings` ของแอปเอง: `ssh <host> "docker exec -i <backend_cid> python -" < /tmp/check.py` โดยสคริปต์ทำ `from core.config import settings; conn = await asyncpg.connect(settings.DATABASE_URL)` — **connection string ไม่เคยผ่าน transcript**, และสคริปต์เข้าถึงสคีมาจริงได้เต็มที่ (เช็ค `information_schema`, `pg_constraint`, นับแถว) ; (2) **สำรอง DB ให้ container ขยายตัวแปรเอง**: `docker exec <db_cid> sh -c 'pg_dump -U $POSTGRES_USER -d $POSTGRES_DB' | gzip > backup.sql.gz` — `$POSTGRES_USER`/`$POSTGRES_DB` ถูกขยายใน container (มาจาก env ของ postgres) ⇒ ไม่มีรหัสผ่านในคำสั่งเลย และ pipe ออกมาเป็นไฟล์บน host ได้ปกติ ; **ตรวจไฟล์สำรองว่าใช้ได้จริงด้วย** `gzip -t` + `zcat ... | grep -c '^CREATE TABLE'` (นับตารางให้ตรงกับที่ควรได้) — ไฟล์ `pg_dump` ที่ gzip ผ่านแต่ตารางไม่ครบคือกับดักที่เจอบ่อยที่สุด
- **⚠️ `/health` ที่ 200 ไม่ได้แปลว่า DB ถูกแก้ถูก:** สคริปต์ตรวจควรยืนยันถึงระดับข้อมูลจริง (คอลัมน์มีจริงไหม, FK ถูกถอดจริงไหม, สิทธิ์ถูก backfill ให้ *ผู้ใช้จริง* กี่คนจากกี่คน, จำนวนแถวของตารางสำคัญยังเท่าเดิมไหม) — production deploy ที่ผ่านมาใช้เกณฑ์นี้จึงจับได้ว่า backfill ทำงานครบ (`council_member` 21/21 ฯลฯ)
- **กฎ: ห้ามดึง credential ของ production ออกมาที่ transcript ไม่ว่าทางไหน (inspect env / exec env / cat .env) — ให้รันคำสั่ง *ในที่ที่ credential อยู่แล้ว* แทน; ฝั่งแอปใช้ `python -` ผ่าน stdin + `settings` ของแอป, ฝั่ง DB ใช้ `sh -c 'pg_dump -U $POSTGRES_USER ...'`; ทุกครั้งที่สำรองต้อง `gzip -t` และนับ `CREATE TABLE` เพื่อพิสูจน์ว่าไฟล์ใช้กู้ได้จริง**
- **Date Added:** 2026-09-27

### 🛠️ `git lfs pull` ล้มด้วย "Git LFS is not installed for this repository" — ติดตั้งได้**ไม่ต้อง sudo** แต่ต้อง `git lfs install --local` ก่อน
- **Context/Problem:** build frontend บนเครื่องที่ไม่ได้ติดตั้ง git-lfs ไม่ผ่าน — `pull_all.sh` ดึง repo ได้ แต่ไฟล์ใต้ `frontend/public/playbooks/` กลายเป็น **pointer file ข้อความบรรทัดเดียว** (ขนาด 131 bytes) แทนที่จะเป็น WebP จริง ทำให้เว็บเสิร์ฟไฟล์เสีย ; และคำสั่งที่ดูเหมือนจะแก้ได้กลับฟ้อง `Skipping object checkout, Git LFS is not installed for this repository`
- **Root Cause:** สองชั้น — (1) git-lfs เป็นโปรแกรมแยก ไม่ได้มากับ git และ **การ `git lfs pull` ต้องผ่าน `git lfs install` ใน repo นั้นก่อน** (ไม่ใช่แค่มีไบนารีอยู่ใน `$PATH`) มิฉะนั้น git จะไม่รู้จัก filter `lfs` ⇒ checkout ปล่อย pointer ไว้ ; (2) สภาพแวดล้อมที่ไม่มี sudo ทำให้ติดตั้งผ่าน package manager ไม่ได้ ⇒ ดูเหมือนตัน
- **Correct Pattern/Solution:** ติดตั้งแบบ **static binary ลง `~/.local/bin`** จาก GitHub releases ของ git-lfs (ไม่ต้อง sudo, ไม่แตะ system path) แล้ว `git lfs install --local` ใน repo **ก่อน** `git lfs pull` ; วิธีตรวจว่าสำเร็จจริงคือ **ดูขนาดไฟล์ ไม่ใช่ exit code** — `find frontend/public/playbooks -size -1000c` ต้องว่าง (pointer = 131 bytes, ไฟล์จริง = แสนไบต์ถึงหลายร้อย KB) ซึ่งเป็นเกณฑ์เดียวกับที่ `pull_all.sh` ใช้และลองซ้ำได้ถึง 3 รอบ ; ตัว `pull_all.sh` หาไบนารีด้วย `command -v git-lfs` แล้ว fallback ไป `$HOME/.local/bin/git-lfs` ⇒ ติดตั้งที่ `~/.local/bin` คือคำตอบที่สคริปต์รองรับอยู่แล้ว
- **⚠️ อย่าตัดสินจาก "git pull ผ่าน":** repo ที่ใช้ LFS จะ `git pull`/`git reset --hard` สำเร็จเสมอแม้ LFS พัง เพราะ git มอง pointer เป็นไฟล์ข้อความธรรมดา ⇒ **ความเสียหายจะไปโผล่ตอน build/ตอนเปิดเว็บ** (รูปไม่ขึ้น) ไม่ใช่ตอน deploy
- **กฎ: ทุกครั้งที่ deploy ต้องยืนยันว่าไฟล์ LFS เป็นไฟล์จริง (`find <lfs_dir> -size -1000c` ต้องว่าง) ไม่ใช่แค่ดูว่า `git pull` สำเร็จ; เครื่องที่ไม่มี sudo ให้ลง git-lfs เป็น static binary ที่ `~/.local/bin`; และต้อง `git lfs install --local` ใน repo ก่อน `git lfs pull` เสมอ**
- **Date Added:** 2026-09-27

### 🛠️ เพิ่มสถานะที่ 3 ให้ข้อมูลที่ soft-delete อยู่แล้ว — `_STATUS_CONDITIONS` เป็น**จุดเดียว**ที่นิยามคำว่าสถานะ
- **Context/Problem:** เพิ่มสถานะ "ปลดระวาง" ให้ตาราง `announcements` ที่เดิมมีแค่ *ใช้งานอยู่* กับ *ถูกลบ* (`deleted_at`) — ตัวที่เสี่ยงที่สุดไม่ใช่การเขียนคอลัมน์ใหม่ แต่คือ **การเปลี่ยนความหมายของคำว่า `active`**: เดิมแปลว่า `deleted_at IS NULL` ใหม่ต้องเป็น `deleted_at IS NULL AND retired_at IS NULL` ⇒ ทุกคิวรีที่กรองสถานะด้วยตัวเอง (ไม่ผ่าน dict กลาง) จะไม่รู้เรื่องนี้ และ **พังเงียบ** — ประกาศที่ปลดระวางยังโชว์บนหน้าเว็บทั้งที่เทสต์อื่นเขียวหมด
- **Root Cause:** `announcement_service._STATUS_CONDITIONS` เป็น dict ที่ผูก SQL fragment กับชื่อสถานะ และถูกใช้ **ทั้ง** คิวรี `COUNT(*)` และคิวรีหลัก (⇒ total กับ items ไม่มีทางไม่ตรงกัน) แต่การรวมศูนย์นี้ครอบคลุมแค่ฝั่ง admin — **ฝั่ง public (`public_service.get_announcements`) เขียน `WHERE deleted_at IS NULL` เอง** เพราะอยู่คนละ service และไม่รู้จัก dict นั้นเลย ⇒ "จุดเดียวที่นิยามสถานะ" ไม่ได้เป็นจุดเดียวจริง ๆ ในระดับระบบ มีสองที่ที่ต้องแก้พร้อมกันโดยไม่มีอะไรเชื่อม
- **Correct Pattern/Solution:** เมื่อเพิ่มสถานะ ให้ **กวาดหาคิวรีที่แตะตารางนั้นทั้งหมด** ด้วย `grep -rn "FROM <table>\|UPDATE <table>" backend/ --include=*.py` แล้วอ่านทีละอันว่ากรองสถานะเองหรือผ่าน dict กลาง — อย่าดูแค่ไฟล์ service ของโดเมนนั้น ; ตั้งชื่อ dict กลางให้สื่อว่าเป็นแหล่งความจริง (`_STATUS_CONDITIONS` พร้อมคอมเมนต์ "dict นี้คือจุดเดียวที่นิยามคำว่าสถานะ") และ **ใส่คอมเมนต์เตือนที่คิวรีที่กรองเอง** ว่า "กรองเองโดยไม่ผ่าน `_STATUS_CONDITIONS` ⇒ เพิ่มสถานะใหม่ต้องมาเติมที่นี่ด้วย" ; เขียนเทสต์ที่พิสูจน์**พฤติกรรมปลายทาง** ไม่ใช่แค่ HTTP status — `test_retired_hidden_from_public` คือด่านที่จับบั๊กนี้ได้ เพราะยิง endpoint ที่ผู้ใช้เห็นจริง
- **⚠️ บทเรียนที่แพงที่สุดของงานนี้:** `test_list_status_filter` เดิม cross-check `active.total` กับ `COUNT(*) WHERE deleted_at IS NULL` — **ยังผ่านต่อไปแม้ความหมายของ active เปลี่ยน** ถ้าไม่แก้เทสต์ให้ตรงกับนิยามใหม่ (เพิ่มสาขา retired + เปลี่ยน cross-check เป็นสองเงื่อนไข) ⇒ เทสต์ที่เคยเป็นตาข่ายจะกลายเป็นเทสต์ที่ประทับตราผิดให้ของที่พังแล้ว
- **กฎ: ก่อนเพิ่มสถานะ/enum ใหม่ ให้ grep หา *ทุก* ที่ที่ query ตารางนั้นและแยกให้ออกว่าอันไหนกรองเอง อันไหนผ่านตัวกลาง; ตัวกลางต้องมีคอมเมนต์บอกว่าตัวเองเป็นแหล่งความจริง และที่ที่กรองเองต้องมีคอมเมนต์ชี้กลับมาว่าต้องอัปเดตด้วยกัน; และต้องมีเทสต์ที่ยิง endpoint ปลายทาง (public/user-facing) ไม่ใช่แค่เทสต์ service**
- **Date Added:** 2026-09-27

### 🛠️ สองคอลัมน์ timestamp ที่**เป็นอิสระต่อกัน** ทำให้ "กู้คืนไม่สูญเสียสถานะ"
- **Context/Problem:** ประกาศมี `deleted_at` (ถูกลบ) และเพิ่ม `retired_at` (ปลดระวาง) — ทางเลือกที่ดูสะอาดตากว่าคือ **บังคับให้ exclusive กัน** (ใส่ CHECK หรือให้ `delete` ล้าง `retired_at` ทิ้ง) เพราะ "จะเป็นทั้งถูกลบและปลดระวางพร้อมกันได้ยังไง" แต่ผลที่ตามมาคือ **ผู้ใช้ที่ปลดระวางประกาศแล้วเผลอกดลบ → กดกู้คืน → ประกาศโผล่กลับมาบนหน้าเว็บสาธารณะทันที** ทั้งที่เจตนาคือเอาออก
- **Root Cause:** `restore` ทำหน้าที่เดียวคือ "คืนสภาพก่อนถูกลบ" — ถ้า `delete` ล้าง `retired_at` ไปแล้ว ข้อมูลว่าก่อนหน้านี้มันถูกปลดระวางอยู่ **หายไปตั้งแต่ตอนลบ** ไม่ใช่ตอนกู้คืน ⇒ `restore` ไม่มีทางรู้ว่าควรคืนไปสถานะไหน จึงคืนสภาพที่ "มองเห็นได้" เสมอ ; และไม่มี error/สัญญาณอะไรบอกผู้ใช้เลยว่าระบบจำสถานะเดิมไม่ได้
- **Correct Pattern/Solution:** ปล่อยให้สองคอลัมน์ **เป็นอิสระจากกัน** (ไม่ใส่ CHECK บังคับ exclusive) แล้วบังคับกติกาที่ชั้น `WHERE` ของแต่ละคำสั่งแทน — `retire`: `deleted_at IS NULL AND retired_at IS NULL` ; `unretire`: `retired_at IS NOT NULL AND deleted_at IS NULL` ; `delete`/`restore` **ไม่แตะ `retired_at` เลย** ⇒ แถวที่ "ปลดระวาง + ถูกลบ" กลับมาเป็น *ปลดระวางแล้ว* ตามเดิม และการกลับไปโชว์ทำได้ทางเดียวคือ `unretire` ; ผลพลอยได้คือแต่ละแท็บไม่มีแถวโผล่ซ้ำ (แท็บ `retired` กรอง `deleted_at IS NULL` เอง ⇒ แถวที่ลบ+ปลดระวางอยู่แท็บ `deleted` ที่เดียว)
- **⚠️ อย่าล็อกสถานะที่ชั้น constraint:** CHECK/UNIQUE ที่ดูเหมือน "กันข้อมูลเพี้ยน" จะกลายเป็นตัวทำให้กู้คืนข้อมูลไม่ได้และ **บีบให้ต้องเขียนข้อมูลทิ้ง** — กติกาเชิงกระบวนการ (สถานะไหนไปต่อได้) เป็นเรื่องของ `WHERE` ในแต่ละ transition ไม่ใช่ของสคีมา
- **กฎ: เมื่อมีสถานะซ้อนกันหลายมิติ ให้เก็บเป็น timestamp อิสระต่อมิติ + บังคับลำดับการเปลี่ยนสถานะด้วยเงื่อนไขใน `WHERE` ของแต่ละคำสั่ง; ห้ามให้คำสั่งหนึ่งล้างข้อมูลของอีกมิติหนึ่งเพื่อ "ความสะอาด"; และต้องมีเทสต์ที่เดินครบเส้นทาง (retire → delete → restore) แล้วยืนยันว่าสถานะเดิมยังอยู่**
- **Date Added:** 2026-09-27

### 🛠️ endpoint เดียวถูกเรียกโดย **2 หน้า** (คนละชุด type คนละ service) — `/api/v1/public/announcements`
- **Context/Problem:** แก้คิวรี public ของประกาศที่เดียว แต่ตอนทดสอบมือต้องเปิด **สองหน้า** ไม่งั้นตรวจไม่ครบ — และตอนวิเคราะห์ผลกระทบก็ลืมหน้านึงได้ง่ายมาก เพราะในโค้ดมันไม่ปรากฏว่ามีความสัมพันธ์กันเลย
- **Root Cause:** `GET /api/v1/public/announcements` มีผู้เรียกสองรายที่ไม่รู้จักกัน: `Home.vue` ผ่าน `services/public.ts` (ใช้ type `PublicAnnouncement` จาก `types/announcement.ts`) และ **`Landing.vue` ที่ยิง `api.get(...)` ตรง ๆ** พร้อม **ประกาศ `interface Announcement` ของตัวเองซ้ำอีกชุด** (ไม่ import จาก `types/`) ⇒ grep หา "ใครใช้ type นี้" ไม่เจอ Landing.vue และ Landing.vue เอาไปแสดง **สองที่** (hero pill ที่หยิบ `announcements[0]` + แถบวิ่ง marquee)
- **Correct Pattern/Solution:** แก้ที่ **backend ที่เดียวจบ** (คิวรีอยู่ใน `public_service.get_announcements`) ⇒ ทั้งสองหน้าได้ผลพร้อมกันโดยไม่ต้องแตะ frontend เลย ; ตอนสำรวจผลกระทบให้ grep **ที่ URL/endpoint** ไม่ใช่ที่ชื่อ type หรือชื่อฟังก์ชัน — `grep -rn "public/announcements" frontend/src backend/` เห็นผู้บริโภคครบทั้งสองรายในคำสั่งเดียว ; ตอนทดสอบมือต้องเปิดทั้ง `/` (Landing — ดูทั้ง hero pill และ marquee) และ `/app` (Home)
- **กฎ: ก่อนแก้ endpoint ให้ grep ที่ **path ของ endpoint** เสมอ (ไม่ใช่ชื่อ type/ฟังก์ชัน) เพราะหน้าที่ไม่ import type ร่วมกันจะไม่โผล่; ถ้ามีผู้บริโภคมากกว่าหนึ่ง ให้แก้ที่ชั้น backend/คิวรีเป็นหลักเพื่อไม่ให้ต้องแก้ซ้ำหลายที่; และ checklist ทดสอบมือต้องระบุทุกหน้าที่แสดงข้อมูลนั้น รวมถึงตำแหน่งที่แสดงซ้ำภายในหน้าเดียวกัน**
- **Date Added:** 2026-09-27

### 🛠️ label ของ audit action มี **สอง map คนละชั้น** — เพิ่ม action ใหม่ต้องเติมทั้งคู่
- **Context/Problem:** เพิ่ม audit action `RETIRE_ANNOUNCEMENT` / `UNRETIRE_ANNOUNCEMENT` แล้วหน้าจอโชว์ชื่อดิบ ๆ ภาษาอังกฤษ — ทั้งที่ code review ดูแล้ว "ใส่ label ครบแล้ว" เพราะแก้ไปที่เดียว
- **Root Cause:** มี `ACTION_LABELS` สองชุดที่ไม่เกี่ยวข้องกันเลย: `backend/services/dashboard_service.py` (ใช้กับแดชบอร์ดสรุปจำนวน action ผ่าน `_action_label()` ที่บรรทัด ~412) และ `frontend/src/views/audit/AuditLogs.vue` (map ของตัวเอง + helper `actionLabel()` สำหรับหน้ารายการบันทึก) ⇒ ทั้งคู่มี fallback (`?? action` / `if action in ACTION_LABELS`) จึง **ไม่ throw ไม่มี error** แค่แสดง `RETIRE_ANNOUNCEMENT` แทนภาษาไทย — พังแบบเงียบที่สุด
- **Correct Pattern/Solution:** ทุกครั้งที่เพิ่ม action ใหม่ใน `AuditLogger(...).log(action="...")` ให้ grep `ACTION_LABELS` ทั้ง repo (`grep -rn "ACTION_LABELS" backend/ frontend/`) แล้วเติมให้ครบทุกที่ ; ใส่คอมเมนต์ที่ map ฝั่ง frontend ว่า "map นี้เป็นของหน้าจอนี้โดยเฉพาะ — backend มีอีกชุด ต้องเติมทั้งคู่" เพื่อให้คนถัดไปเห็นกับดักจากในโค้ดเอง
- **⚠️ fallback ที่ "ช่วยไม่ให้พัง" คือสิ่งที่ทำให้บั๊กนี้อยู่รอด:** ถ้าไม่มี fallback แล้ว throw ตั้งแต่แรก จะเจอตอนเทสต์ครั้งแรก — การมี fallback ที่แสดงค่าดิบเป็นดีไซน์ที่ถูก (หน้าจอไม่ควรล่มเพราะ label หาย) แต่ **โอนภาระการตรวจจับไปที่คนเขียน** ⇒ ต้องมีวินัย grep ทุกครั้ง
- **กฎ: เพิ่ม audit action ใหม่ = เพิ่ม label ให้ครบ *ทุก* map ที่ grep เจอ (ปัจจุบันมี 2: `dashboard_service.ACTION_LABELS` และ `AuditLogs.vue` ACTION_LABELS); อย่าตัดสินว่า "ครบแล้ว" จากความรู้สึก ให้ grep; และเมื่อมี map หลายชุด ให้ใส่คอมเมนต์ไขว้กันไว้ในโค้ด**
- **Date Added:** 2026-09-27

### 🛠️ การ**จงใจ**ไม่ใส่ LIMIT ใน list ของ public — ฝ่าฝืน `docs/rules/backend.md` ข้อ 3 อย่างรู้ตัว
- **Context/Problem:** กฎข้อ 3 ของ `docs/rules/backend.md` เขียนว่า *"การดึงข้อมูล List ยาวๆ ต้องทำ Pagination หรือใส่ LIMIT ห้ามดึงทั้งตาราง"* — แต่เจ้าของระบบสั่งชัดเจนว่า *"ไม่ต้องกำหนดว่าให้โชว์กี่อัน แต่ให้โชว์ทั้งหมดที่ยังไม่ถอดออก"* ⇒ สองอย่างนี้ขัดกันตรง ๆ และถ้าเงียบ ๆ ฝ่าฝืนกฎ คนถัดไปที่อ่าน code review หรือ refactor จะ **ใส่ LIMIT กลับมาโดยคิดว่ากำลังทำความดี** แล้วฟีเจอร์ก็หาย
- **Root Cause:** กฎที่มีเหตุผลดี (กันหน่วยความจำบวม/timeout) ถูกเขียนเป็นกฎสากลโดยไม่มีช่องระบุข้อยกเว้น ⇒ เมื่อมี Requirement ของเจ้าของระบบที่ขัดกับกฎ กฎจะแพ้ แต่ถ้าไม่มีร่องรอยว่า "แพ้เพราะมีคำสั่ง" การเปลี่ยนแปลงนั้นจะดูเหมือนความสะเพร่า
- **Correct Pattern/Solution:** ยอมรับ **ไม่ใช่เพิกเฉย** — (1) ใส่ docstring ที่คิวรีนั้นอธิบายตรง ๆ ว่าไม่ใส่ LIMIT เพราะอะไร อ้างคำสั่งเจ้าของระบบ และระบุเงื่อนไขที่ต้องกลับมาทบทวน ("ถ้าโตถึงหลักพันต้องกลับมาคุยเรื่อง pagination") (2) เขียนเทสต์ที่ **ตรึงเจตนา** ไว้ — `test_public_announcements_returns_all_active_without_limit` สร้าง 7 แถวแล้ว assert ว่าคืน 7 (ถ้าใครใส่ LIMIT กลับมา เทสต์ฟ้องทันที) (3) ประนีประนอมเฉพาะจุดที่จำเป็น: **ฝั่ง admin ยังมี pagination ครบ** (`limit` 20/หน้า สูงสุด 200) ⇒ จำกัดการฝ่าฝืนไว้ที่ endpoint เดียวที่มีข้อมูลน้อยและควบคุมได้ (4) บันทึกลง skills.md (ที่นี่) เพื่อให้เป็นความรู้ของทีม ไม่ใช่การตัดสินใจส่วนตัวของคนเขียน
- **⚠️ อย่าใช้ "มีเทสต์ครอบแล้ว" เป็นข้ออ้างแทนการอธิบาย:** เทสต์บอกว่า "พฤติกรรมคืออะไร" แต่บอกไม่ได้ว่า "ทำไม" — ถ้าไม่มีคอมเมนต์/บรรทัดในเอกสาร คนที่เจอทีหลังจะลบทั้งเทสต์และ LIMIT พร้อมกัน
- **กฎ: การฝ่าฝืนกฎที่เขียนไว้ต้องทำอย่างเปิดเผย — ใส่คอมเมนต์/docstring อ้างเหตุผลและเงื่อนไขทบทวน + มีเทสต์ตรึงเจตนา + จำกัดขอบเขตให้แคบที่สุด + บันทึกใน skills.md; ห้ามเงียบ ๆ ไม่ใส่ LIMIT แล้วหวังว่าไม่มีใครสังเกต**
- **Date Added:** 2026-09-27

### 🛠️ `flex-1` (basis 0) ที่มีพี่น้องเป็น `shrink-0` = ข้อความถูกบีบเหลือ "บรรทัดละตัวอักษร" บนจอแคบ
- **Context/Problem:** การ์ดประกาศบนมือถือ ข้อความขึ้น **บรรทัดละตัวอักษร** และปุ่มดูถูกบีบ — อาการโผล่ทันทีหลังเพิ่มปุ่มที่ 3 เข้าไปในแถวปุ่ม ทั้งที่ก่อนหน้านั้น (2 ปุ่ม) หน้าจอ "แน่นแต่พออ่านได้" และไม่มีใครรายงานปัญหา
- **Root Cause:** แถวการ์ดเป็น `flex flex-wrap justify-between gap-3` มีลูกสองกล่องที่ **ต่างคนต่างถูกต้องในตัวเอง**: กล่องข้อความ `min-w-0 flex-1` = `flex: 1 1 0%` ⇒ **flex-basis 0** (ขนาดสมมติ *ก่อน* หด = 0) และกล่องปุ่ม `shrink-0` ⇒ หดไม่ได้ ขนาดตามเนื้อ (~265px เมื่อมี 3 ปุ่ม) ⇒ ผลรวมขนาดสมมติยังไม่เกินความกว้างการ์ด `flex-wrap` จึง **ไม่ตัดขึ้นบรรทัดใหม่** แต่พื้นที่ทั้งหมดที่เหลือถูกยกให้กล่อง basis 0 ตามสัดส่วน ⇒ ข้อความเหลือ ~30px จึงตัดคำทุกตัวอักษร
- **⚠️ อาการรุนแรงแบบก้าวกระโดดตามจำนวนของในแถว:** 2 ปุ่ม (~180px) เหลือให้ข้อความ ~120px = "แน่นแต่พออ่านได้" ; 3 ปุ่ม (~265px) เหลือ ~30px = พังทันที ⇒ บั๊กนี้ **ไม่โผล่ตอนเขียน ไม่โผล่ตอนรีวิว** (diff ของปุ่มที่เพิ่มเข้ามาดูปกติทุกบรรทัด) โผล่ตอน **ของในแถวเพิ่มขึ้น** เท่านั้น
- **⚠️ กับดักตอนหาสาเหตุ:** ค้นด้วยคำว่า "บีบ/แคบ/มือถือ" ไม่เจออะไรเลย — ต้องมองที่ **คู่** ของ class คือ `flex-1` ที่หนึ่ง กับ `shrink-0` อีกที่หนึ่ง ซึ่งอยู่คนละบรรทัด ห่างกันเป็นสิบ ๆ บรรทัด
- **Correct Pattern/Solution:** **อย่าหวังให้ `flex-wrap` แก้ปัญหาแทน** — `flex-wrap` ตัดบรรทัดก็ต่อเมื่อผลรวม *ขนาดสมมติ* เกินความกว้าง ซึ่ง **ไม่เกิด** เมื่อมี `basis 0` อยู่ในแถว ⇒ ต้องบังคับโครงสร้างด้วย breakpoint: มือถือให้ทั้งสองกล่อง `w-full` (⇒ คนละบรรทัดแน่นอน) แล้ว `sm:w-auto sm:flex-1` / `sm:w-auto sm:shrink-0` ให้กลับไปวางข้างกันบนจอใหญ่ ; กล่องปุ่มใส่ `flex-wrap` ด้วยเพื่อให้จอแคบมาก (~320px) ปุ่มตัดขึ้นบรรทัดใหม่ได้ ไม่ล้นการ์ด
- **กฎ: ในแถว flex แนวนอนที่มี `shrink-0` อยู่ ห้ามปล่อยให้กล่องข้อความเป็น `flex-1` เฉย ๆ — ต้องมี breakpoint บังคับให้ซ้อนกันบนจอแคบ (`w-full` แล้วค่อย `sm:` กลับไปข้างกัน) หรือกำหนด `flex-basis` ที่ไม่ใช่ 0; และเมื่อเพิ่มหรือลบปุ่มในแถวใด ต้องกลับไปตรวจที่ความกว้าง ~360px ทุกครั้ง ไม่ใช่ดูแค่จอ desktop**
- **Date Added:** 2026-09-27

### 🔥 pool มี connection แค่ 10 ใบ — **ห้ามเรียก service ที่ `acquire()` เอง ขณะถือ connection อยู่** และห้าม `asyncio.gather` ข้ามการ acquire
- **Context/Problem:** เขียน `me_service.get_personal_stats(pool, user_id)` ที่ต้องรู้ด้วยว่า "ภาคปัจจุบัน" คืออะไร ซึ่งมี `term_service.get_current_term(pool)` ให้เรียกอยู่แล้ว ⇒ ทางที่สั้นที่สุดคือเรียกมันตรง ๆ จากในฟังก์ชันที่กำลังถือ connection อยู่ (เปิด connection ไว้ → `fetchval` 6 ตัว → แล้วค่อยเรียก term) · โค้ดแบบนี้ **ผ่านเทสทุกตัว** และทำงานถูกต้องตอนเทสรันทีละเคส ⇒ ไม่มีอะไรฟ้องจนขึ้น production
- **Root Cause:** `backend/main.py:38-41` สร้าง pool ด้วย `min_size=1, max_size=10` ⇒ **ทั้งระบบมี connection 10 ใบ** และทุก request ที่รันพร้อมกันแย่งกันใช้ · `get_current_term(pool)` เรียก `pool.acquire()` เอง ⇒ การเรียกมันขณะถือ connection อยู่ = **ยึด 2 ใบต่อ 1 request** · พอมี request แบบนี้พร้อมกัน 6 ใบ ก็กินครบ 10 ⇒ ใบที่ 11 ต้อง **รอคิว** ซึ่งไม่ error ไม่ timeout ทันที (ขึ้นกับ `command_timeout`) — อาการที่เห็นคือ **"บาง request ค้าง บางทีก็ผ่าน"** ซึ่งแทบจะ debug ไม่ถูกถ้าไม่รู้เรื่อง pool มาก่อน · ถ้าเป็น `asyncio.gather` ที่เรียกหลาย service พร้อมกัน ตัวคูณจะยิ่งสูงขึ้น (1 request = N ใบ) ⇒ อาการเดียวกันนี้จะโผล่ที่ concurrency ต่ำกว่ามาก ; **เทสไม่จับเพราะ fixture ยิงทีละเคส** ⇒ คลาสของบั๊กนี้รอดจาก integration test เสมอ
- **Correct Pattern/Solution:** (1) **แยก 2 เวอร์ชัน**ของทุกฟังก์ชันที่ต้องถูกเรียกซ้อน — เวอร์ชันรับ `pool` (สร้าง connection เอง) กับเวอร์ชันรับ `conn` (caller ส่งมา) ⇒ `term_service` มีทั้ง `get_current_term(pool)` และ `fetch_current_term(conn)` ; ตัวในเรียกเวอร์ชัน `conn` เสมอ (2) ถ้าต้องเรียก **service อื่น** จริง ๆ ให้ `await` **เรียงลำดับ นอก** block ที่ถือ connection — ปล่อย connection ของตัวเองคืน pool ให้หมดก่อน แล้วค่อยเรียกตัวถัดไป (ดูรูปใน `home_service.get_home_summary`) (3) **ห้าม `asyncio.gather` ข้ามการ acquire connection** — connection เดียวกันรัน query พร้อมกันไม่ได้อยู่แล้ว และการ acquire หลายใบพร้อมกันจะยึด pool ตามจำนวน branch (4) เขียน comment อธิบายไว้ในไฟล์ service นั้นเลย เพราะคนอ่านบรรทัด `await term_service.get_current_term(pool)` เดี่ยว ๆ จะไม่เห็นว่ามันผิด
- **กฎ: service ที่รับ `pool` = "เปิด connection เองได้" ⇒ เรียกได้เฉพาะจากชั้น router หรือจากที่ที่ยังไม่ถือ connection; เมื่ออยู่ลึกกว่านั้นให้ใช้เวอร์ชัน `conn` เสมอ**
- **Date Added:** 2026-09-28

### 🔥 `date` เทียบกับ `timestamptz` ตรง ๆ = เพี้ยนตาม TimeZone ของ session — ต้อง `AT TIME ZONE 'Asia/Bangkok'` และ `end_date + 1` เมื่อขอบเขตเป็น inclusive
- **Context/Problem:** สถิติส่วนตัว (C3) ต้องนับเฉพาะช่วง "ภาคเรียน" — `academic_terms.start_date`/`end_date` เป็น `DATE` แต่ `issues.created_at` เป็น `TIMESTAMP WITH TIME ZONE` ⇒ เขียนเงื่อนไขตามสัญชาตญาณว่า `AND i.created_at >= $2::date AND i.created_at < $3::date` **แล้วเทสผ่าน** ถ้าข้อมูลที่ใส่ในเทสอยู่กลางวัน
- **Root Cause:** Postgres cast `date` → `timestamp` **ด้วย TimeZone ของ session** ไม่ใช่ของไทย · container ตั้ง `TZ=UTC` ⇒ `2026-05-16::date` = `2026-05-16 00:00:00+00` = **07:00 น. เวลาไทย** ⇒ เรื่องที่แจ้งตอน 06:00 น. ของวันแรกของภาค **หลุดออกจากสถิติ** และเรื่องที่แจ้ง 06:00 น. ของวันถัดจากวันสุดท้าย **หลุดเข้ามา** — ผิดทั้งสองหัวท้ายโดยที่เทสกลางวันผ่านหมด · ยังมีกับดักที่สองซ้อนอยู่: ถ้าเขียน `< end_date` ตรง ๆ วันสุดท้ายของภาคจะหายไปทั้งวัน เพราะ `end_date` เป็น **inclusive** (คนละธรรมเนียมกับ `created_at < …` ที่ต้อง exclusive)
- **Correct Pattern/Solution:** แปลงเป็น **เที่ยงคืนเวลาไทย** ด้วย `AT TIME ZONE` ทั้งสองข้าง และบวก 1 วันเมื่อขอบเขตเป็น inclusive:
  ```sql
  AND i.created_at >= (($2::date)::timestamp AT TIME ZONE 'Asia/Bangkok')
  AND i.created_at <  ((($3::date + 1)::timestamp) AT TIME ZONE 'Asia/Bangkok')
  ```
  · ตรึงด้วยเทส **3 เคสขอบ**ที่เวลาไทย: `start_date` 00:30 น. (ต้องนับ) · `end_date` 23:30 น. (ต้องนับ) · `end_date + 1` 00:30 น. (ต้องไม่นับ) — เทสที่สร้างข้อมูลกลางวันจะไม่จับบั๊กนี้เลย ; `dashboard_service.py` นิยาม `BKK` ไว้ที่ต้นไฟล์แล้ว ใช้เป็นแบบอย่างได้
- **⚠️ อย่าใช้ `new Date(...)` กับ string `date` ฝั่ง frontend ด้วย:** `new Date('2026-05-16')` ถูกตีความเป็น UTC เที่ยงคืน ⇒ พอ format ในไทย timezone จะกลายเป็นวันที่ 15 ⇒ ฝั่ง FE ให้แยก string เองหรือเติม `T00:00:00+07:00` (ดู `types/me.ts`)
- **Date Added:** 2026-09-28

### 🔥 `nginx` ที่ไม่มี `Cache-Control` เลย ⇒ **`sw.js` ถูก cache แล้วค้างถาวร** — service worker ไม่อัปเดตอีกเลย และหาสาเหตุไม่ได้
- **Context/Problem:** ทำ PWA (A1) แล้วแก้ `sw.js` รอบสอง ปรากฏว่าเบราว์เซอร์ **ไม่ยอมโหลด `sw.js` ใหม่เลย** ทั้งที่ build ใหม่ขึ้น production แล้ว — ลบ cache ในเว็บก็ไม่หาย ต้องไป unregister service worker เองแบบมือเปล่า
- **Root Cause:** `frontend/Dockerfile` สร้าง nginx config inline ด้วย `RUN echo '…' > /etc/nginx/conf.d/default.conf` **โดยไม่มี `add_header Cache-Control` แม้แต่บรรทัดเดียว** ⇒ nginx ใส่แค่ `Last-Modified` + `ETag` ให้ ⇒ เบราว์เซอร์ใช้ **heuristic caching** (ตีความว่าอายุ cache = 10% ของเวลาตั้งแต่ไฟล์ถูกแก้ ล่าสุด) กับไฟล์ที่ path คงที่อย่าง `/sw.js` ⇒ ครั้งแรกที่ cache ก็ค้างเป็นสัปดาห์ · **ต่างจากไฟล์อื่นทั้งหมดในโปรเจกต์** เพราะ `/assets/*` มี content hash ในชื่อไฟล์ (Vite ใส่ให้) ⇒ cache นานแค่ไหนก็ปลอดภัย และ `index.html` ไม่มีใคร cache ยาวเพราะ navigation ยิงผ่าน SW (network-first) อยู่แล้ว ⇒ อาการนี้โผล่ที่ `sw.js` กับ `manifest.json` เท่านั้น ซึ่งเป็น **สองไฟล์ที่ต้องสดที่สุดในระบบ**
- **Correct Pattern/Solution:** ใส่ `location` block เฉพาะสองไฟล์นี้ **ก่อน** `location /` (nginx เลือก longest-prefix match ⇒ `location =` ที่ตรงเป๊ะชนะเสมอ แต่เขียนไว้บนอ่านง่ายกว่า):
  ```nginx
  location = /sw.js        { add_header Cache-Control "no-cache, must-revalidate"; try_files $uri =404; }
  location = /manifest.json { add_header Cache-Control "no-cache"; try_files $uri =404; }
  ```
  · `no-cache` = "เก็บได้ แต่ต้อง revalidate ก่อนใช้" (ไม่ใช่ `no-store`) ⇒ ได้ `304` เมื่อไม่เปลี่ยน ไม่เสีย bandwidth · **`try_files $uri =404` จำเป็น** — ถ้าไม่ใส่ nginx จะตอบ `index.html` แทน `sw.js` เมื่อไฟล์หาย ⇒ เบราว์เซอร์จะได้ HTML มาเป็น JS แล้ว throw `Unexpected token '<'` ซึ่งอ่านไม่ออกว่าเกิดอะไร
- **กฎ: ไฟล์ที่ต้องสดเสมอ (service worker, manifest) ต้องมี `Cache-Control` ระบุชัด ห้ามพึ่ง default ของ nginx; และไฟล์ที่ไม่อยากให้ fallback ไป SPA ต้องมี `=404`**
- **Date Added:** 2026-09-28

### 🛠️ precache ของ service worker: รายการคงที่ **ไม่พอ** — ต้อง parse `index.html` เอา `/assets/*` ที่ Vite ใส่ hash มาด้วย ไม่งั้นออฟไลน์ครั้งแรกจอขาว
- **Context/Problem:** เขียน `sw.js` โดย precache รายการที่รู้ล่วงหน้า (`/`, `/index.html`, `/manifest.json`, ไอคอน, โลโก้) แล้วคิดว่าจบ — ตอนเทสออฟไลน์ **หน้าเว็บขาวสนิท** ทั้งที่ DevTools บอก SW `activated` และ cache ก็มีไฟล์ครบตามรายการ
- **Root Cause:** ตัว HTML ที่ precache ไว้ไม่มีอะไรผิด แต่มัน **อ้างถึงไฟล์ที่ไม่ได้อยู่ใน cache** — Vite แตก bundle แล้วตั้งชื่อแบบมี content hash (`/assets/index-DHUqUxjD.js`, `/assets/index-BigNA-4Q.css`) ซึ่งเปลี่ยนทุกครั้งที่ build และ **ไม่มีทาง hardcode ไว้ใน `sw.js` ได้** ⇒ ตอนออฟไลน์ได้ HTML มาแต่โหลด JS/CSS ไม่ได้ ⇒ Vue ไม่ mount ⇒ `#app` ว่าง = จอขาว · และเพราะ `index.html` เองถูก cache ไว้แล้ว (ไม่ error) จึงดูเหมือน "cache ทำงาน" ทั้งที่ shell ไม่ครบ
- **Correct Pattern/Solution:** ตอน `install` ให้ **ดึง `/index.html` ตัวจริงมาแกะหา URL** แล้ว cache ต่อ:
  ```js
  const html = await (await fetch('/index.html', { cache: 'reload' })).text()
  const urls = [...html.matchAll(/["'](\/assets\/[^"']+)["']/g)].map((m) => m[1])
  await Promise.allSettled(urls.map((u) => cache.add(u)))   // allSettled ไม่ใช่ all — ไฟล์เดียวพังต้องไม่ล้ม install
  ```
  · ใช้ `{ cache: 'reload' }` กันได้ HTML จาก HTTP cache มาแกะ (จะได้ชุด asset เก่า) · ใช้ `Promise.allSettled` + `try/catch` เพราะ `cache.add` throw เมื่อ response ไม่ใช่ 2xx และ **`install` ที่ throw = SW ทั้งตัวติดตั้งไม่สำเร็จ** ⇒ แย่กว่าไม่มี asset · วิธีเทสที่เชื่อได้คือ **`context.setOffline(true)` แล้ว reload จริง** ไม่ใช่ดูว่า SW `activated` (สถานะ activated ไม่ได้แปลว่า shell ครบ — บทเรียนนี้มาจากตรงนั้น)
- **⚠️ ขอบเขตที่ตั้งใจ:** ทำเฉพาะ app shell — `/api/*` **ห้ามเข้า cache เด็ดขาด** เพราะ SW cache เป็น **per-origin ไม่ใช่ per-session** ⇒ เก็บไว้แล้วผู้ใช้คนถัดไปบนเครื่องเดียวกัน (หรือหลัง logout) จะเห็นข้อมูลของคนก่อน ; cross-origin (Google Fonts, jsdelivr) ก็ห้าม cache เพราะเป็น opaque response ที่อ่านค่าไม่ได้
- **Date Added:** 2026-09-28

### 🛠️ service ที่ **ไม่เปิด transaction เอง** (รับ `conn` จาก caller) — การเพิ่ม "ตัวกรอง" เข้าไปต้องรับ `conn` ด้วย ไม่ใช่ `pool`
- **Context/Problem:** เพิ่มการตั้งค่าการแจ้งเตือน (A2) แล้วต้องให้ `notify*` ทั้ง 3 ตัวเคารพค่าที่ผู้ใช้ปิดไว้ — สัญชาตญาณคือเขียน helper `_pref_allows(pool, user_id, group_type)` ตาม service อื่น ๆ
- **Root Cause:** `notification_service.py` เป็นข้อยกเว้นของกฎ transaction ในโปรเจกต์นี้ — `notify()` / `notify_bulk()` / `notify_fanout()` **ไม่เปิด transaction เอง** แต่รับ `conn` จาก caller เพราะถูกเรียกจากใน transaction ของ service อื่น (accept issue, comment, vote, …) ⇒ ถ้า helper เปิด connection ใบใหม่ จะ (1) กิน pool ซ้ำซ้อนตามบทเรียน pool ข้างบน (2) **อ่านคนละ snapshot กับ transaction ที่กำลังเขียน** ⇒ ผู้ใช้ที่เพิ่งปิดการแจ้งเตือนใน request อื่นอาจถูกมองว่ายังเปิดอยู่ (3) ตัวที่แย่ที่สุด: `notify_fanout` เป็น `INSERT … SELECT` ก้อนเดียว ถ้าแยกไปกรองใน Python ต้องดึง user ทั้งโรงเรียนออกมาก่อน
- **Correct Pattern/Solution:** helper รับ `conn` เป็น arg แรก แล้วเรียกด้วย `conn` ที่ caller ถืออยู่ — `_pref_allows(conn, user_id, group_type)` และ `_filter_allowed(conn, user_ids, group_type)` ที่กรองด้วย query เดียว (`WHERE … AND user_id = ANY($2::int[])`) ไม่ใช่ N query ; สำหรับ `notify_fanout` ให้เติมเงื่อนไข **ใน SQL** ไม่ใช่กรองหลัง query:
  ```sql
  AND NOT EXISTS (SELECT 1 FROM notification_preferences p
                  WHERE p.user_id = s.user_id AND p.group_type = $1 AND p.enabled = FALSE)
  ```
  · ⚠️ การเพิ่ม `$1` กลาง SQL ทำให้ **เลข placeholder ของคอลัมน์ที่เหลือต้องเลื่อนทั้งหมด** ⇒ ใส่ `assert sql.count("$") == len(params)` กำกับไว้ (บทเรียนเดิม) ; การอ่านตารางที่ไม่มีใครล็อกอยู่ใน transaction เดียวกันไม่ทำให้เกิด deadlock
- **Date Added:** 2026-09-28

### 🚫 ตรวจ static asset ผ่าน CDN **ก่อน** deploy = poison cache ของตัวเอง — และ `200` จาก nginx `try_files` **ไม่ได้แปลว่าไฟล์มี**
- **Context/Problem:** หลัง deploy staging (image `0e172bd`) ตรวจว่า PWA ขึ้นจริงไหมด้วย `curl -o /dev/null -w '%{http_code}' https://<staging>/sw.js` → ได้ **200** ทั้งที่ก่อน deploy ก็ได้ 200 เหมือนกัน ⇒ สรุปไม่ได้ว่า deploy ผ่านหรือไม่ และเกือบเข้าใจผิดว่าไฟล์ PWA หายจาก image
- **Root Cause:** สองชั้นซ้อนกัน (1) nginx config ของโปรเจกต์นี้เป็น `try_files $uri /index.html` ⇒ **ทุก path ที่ไม่มีไฟล์จริงจะได้ `200` พร้อมเนื้อหา `index.html`** ไม่ใช่ 404 (เป็นพฤติกรรมที่ต้องการสำหรับ SPA router แต่ทำให้ status code ใช้ตรวจ static asset ไม่ได้เลย) (2) การยิง path ที่ยังไม่มีไฟล์ **ก่อน** deploy ทำให้ CDN (Cloudflare) **แคชคำตอบ fallback นั้นไว้** ⇒ พอ deploy เสร็จ ของจริงถูกต้องที่ origin แต่ edge ยังคืน `index.html` เก่าอยู่ ⇒ ได้ผลลวงว่า "ไฟล์หาย" ทั้งที่อยู่ใน image ครบ
- **Correct Pattern/Solution:** ตรวจ static asset ด้วย **`content_type` + `size_download` ไม่ใช่ status code** — ไฟล์จริงต้องได้ `application/javascript` / `image/png` / `application/json` ; ถ้าได้ `text/html` = กำลังดู SPA fallback อยู่ (ไม่ใช่ไฟล์) · และ **อย่า probe path ที่ยังไม่ deploy ผ่าน CDN** — ถ้าจำเป็นต้องรู้ baseline ให้ยิงตรงเข้า origin container (`docker exec <fe>) wget -qO- localhost/sw.js`) หรือยิงผ่าน CDN **หลัง** deploy เท่านั้น · ถ้าเผลอทำแล้ว ให้ยืนยันด้วย cache-buster `?v=$(date +%s)` — ถ้าได้ไฟล์จริงแสดงว่า origin ถูก ปัญหาอยู่ที่ edge cache
- **⚠️ กับดักที่ตามมา:** `try_files $uri /index.html` ทำให้ **ทุก path ที่พิมพ์ผิดก็ได้ 200** ⇒ เวลาหา "ทำไมรูปไม่ขึ้น / ทำไม route 404" ให้ดู `content-type` ก่อนเสมอ ไม่งั้นจะไปไล่หาที่ frontend ทั้งที่พิมพ์ path ผิด
- **Date Added:** 2026-09-28

### 🔥 `add_header Cache-Control "no-cache"` ที่ nginx **ไม่พอเมื่อมี Cloudflare อยู่ข้างหน้า** — CF เขียนทับด้วย `max-age=14400` และเลือกแคชตามนามสกุลไฟล์
- **Context/Problem:** หลัง deploy พบ `sw.js` ถูกเสิร์ฟเป็น `text/html` (fallback) ทั้งที่ origin ถูกต้อง ⇒ ตั้งสมมติฐานว่า nginx cache header ที่เพิ่งใส่ไปไม่ทำงาน ตรวจ `frontend/Dockerfile` บน `main` แล้วพบว่า `location = /sw.js` + `no-cache, must-revalidate` **อยู่ครบและถูกต้อง** — ปัญหาอยู่ที่อื่น
- **Root Cause:** **Cloudflare เป็นชั้นที่ตัดสินใจแคชของจริง** ไม่ใช่ nginx — หลักฐานจาก header ตอบกลับ: `cf-cache-status: HIT` · `age: 223` · **`cache-control: max-age=14400`** ซึ่งเป็นค่าของ CF เอง **ไม่ใช่ `no-cache` ที่ origin ส่งมา** ⇒ CF แทนที่ header ต้นทางด้วยนโยบายแคชของตัวเอง และเลือกแคช **ตามนามสกุลไฟล์**: `.js` และ `.png` ถูกแคช แต่ `.json` ไม่ถูก (`manifest.json` จึงได้ `cf-cache-status: DYNAMIC` และถูกต้องโดยบังเอิญ) · ผลคือ **`sw.js` ค้างได้ถึง 4 ชั่วโมง** — ซึ่งคือความล้มเหลวแบบเดียวกับที่ `location = /sw.js` พยายามป้องกัน (SW ไม่อัปเดต) แค่ย้ายจาก nginx ไปเกิดที่ CF
- **Correct Pattern/Solution:** header ที่ origin **เป็นคำแนะนำ ไม่ใช่คำสั่ง** เมื่อมี CDN ครอบ ⇒ ต้องแก้ที่ชั้น CDN ด้วย อย่างใดอย่างหนึ่ง: (1) **Cache Rule → Bypass cache** สำหรับ path `/sw.js` (และ `/manifest.json`) หรือ (2) เปิด **Origin Cache Control** ให้ CF เชื่อฟัง `Cache-Control` จากต้นทาง (3) ถ้าแตะ CF ไม่ได้ ให้ **เปลี่ยนชื่อไฟล์ทุกครั้งที่ SW เปลี่ยน** (`sw-<hash>.js` แล้ว register จาก `index.html`) ซึ่งเลี่ยงปัญหาได้โดยไม่ต้องพึ่ง CF — วิธีที่ (3) ทนที่สุดเพราะไม่ผูกกับผู้ให้บริการรายใด
- **⚠️ อย่าด่วนสรุปว่า "nginx ไม่ทำงาน":** อาการ "cache header ไม่มีผล" ให้ดู `cf-cache-status` / `age` / `via` **ก่อน** ไล่แก้ config ต้นทาง · และ **purge cache หลัง deploy ทุกครั้งที่แตะ `sw.js`** ไม่งั้นผู้ใช้ที่ติดตั้งไปแล้วจะยังได้ SW เก่า
- **Date Added:** 2026-09-28

### 🔥 `z-index` ที่สูงกว่า **ไม่ชนะ** ถ้าอยู่ใน stacking context ของคนอื่น — modal `z-50` แพ้ bottom bar `z-40` แล้ว**กลืนคลิกปุ่มบันทึก**
- **Context/Problem:** ผู้ใช้รายงานว่า "ตอนเพิ่มภาคเรียน layout มันบัง" — เปิด modal เพิ่มภาคเรียนบนมือถือแล้ว **กดปุ่ม "เพิ่มภาคเรียน" ไม่ติด** ทั้งที่โค้ด modal เป็น `fixed inset-0 z-50` (สูงกว่าแถบเมนูล่างซึ่งเป็น `z-40` ชัด ๆ) และปุ่มก็ไม่มีอะไรdisabled
- **Root Cause:** **stacking context** — `MainLayout.vue` ห่อ `<RouterView>` ไว้ใน `<div class="relative z-10 …">` และ `position: relative` + `z-index: 10` (ที่ไม่ใช่ `auto`) **สร้าง stacking context ใหม่** ⇒ ลูกทุกตัวข้างในถูกจัดลำดับกันเองในชั้นนั้น และ **`z-index` ของลูกไม่มีทางหลุดออกไปแข่งข้างนอกได้** ⇒ modal `z-50` ข้างในถูกกักไว้ที่ชั้น 10 ส่วนแถบเมนูล่างเป็น **พี่น้อง** ของ `.maincol` ที่ชั้น 40 ⇒ แถบทับ modal ทั้งใบ และเพราะชั้นในสุดที่รับแตะคือ `<nav>` (มี `pointer-events-auto` ที่ div ลูก) **คลิกจึงถูกกลืน ไม่ใช่แค่ถูกบัง** · กับดักคือ **การอ่านค่า z-index จากโค้ดไม่ทำให้เห็นบั๊กนี้เลย** — ต้องรู้กติกา stacking context หรือวัดจริง
- **Correct Pattern/Solution:** ครอบ modal ด้วย **`<Teleport to="body">`** ⇒ ออกจาก stacking context ของ layout ไปแข่งที่ระดับ root (และหลุดจาก `overflow-hidden` ของ `.maincol` ด้วย)
  ```vue
  <Teleport to="body">
    <Transition name="sheet">
      <div v-if="modalOpen" class="fixed inset-0 z-50 …">
  ```
  · **สโคปสไตล์ยังทำงาน** — เนื้อหาที่ teleport ยังติด `data-v-*` ของคอมโพเนนต์เดิม ⇒ `.sheet-enter-active` ใช้ได้ปกติ · **`Profile.vue:308` เป็นข้อยกเว้นที่ถูกต้องแล้ว** — overlay โปร่งใสสำหรับปิด dropdown *ควร* อยู่ใต้แถบเมนู เพื่อให้ยังกดเมนูได้ อย่าไป teleport มัน
- **วิธีพิสูจน์ว่าถูกบังหรือแค่ดูเหมือนถูกบัง (ใช้ซ้ำได้ทุกครั้ง):** ยิง hit-test ที่ **จุดกึ่งกลางของปุ่มจริง** — `document.elementFromPoint(cx, cy)` แล้วดูว่าได้ element ที่คาดไหม
  ```js
  const r = btn.getBoundingClientRect()
  document.elementFromPoint(r.left + r.width/2, r.top + r.height/2)  // ได้ <nav> = ถูกบัง
  ```
  วิธีนี้แม่นกว่าการอ่าน CSS และเร็วกว่าเดา — ใช้ Playwright วัดในหน้าเปล่าที่ลอกโครงสร้าง CSS จริงมาก็ได้ผลชัดเจนโดยไม่ต้องล็อกอิน
- **Date Added:** 2026-09-28

### 🚫 `cache.addAll` ใน service worker + nginx `try_files` = **แคชหน้า HTML ทับไอคอน/JS ติดถาวร** — ต้องเช็ค `Content-Type` ก่อนเก็บ
- **Context/Problem:** Cloudflare แคช SPA fallback (`200 text/html`) ไว้ที่ path `/icons/icon-192.png` (ดูบทเรียน CDN ข้างบน) ⇒ พอ SW ติดตั้ง มันดึง path นั้นไป precache แล้วเก็บ **หน้า HTML ไว้ใต้คีย์ของไอคอน** และ `handleStatic` เป็น cache-first ⇒ ไอคอนเสีย **ติดอยู่ใน cache ของผู้ใช้ทุกคนถาวร** แม้ CDN จะหายเป็นปกติแล้ว — อาการที่เห็นคือ "ไอคอนไม่ขึ้น/ไฟล์เพี้ยน" ซึ่งไล่หาสาเหตุยากมาก เพราะต้นทางถูกต้องและ CF ก็ถูกต้องแล้ว
- **Root Cause:** `cache.addAll()` (และ `cache.add()`) **ตัดสินจาก `res.ok` เท่านั้น** ⇒ `200 text/html` จาก `try_files $uri /index.html` ผ่านเกณฑ์ทุกข้อ ทั้งที่เนื้อไม่ใช่ไฟล์ที่ขอ · และเพราะ SW cache เป็น cache-first สำหรับ `/icons/` (path ไม่มี content hash) ของเสียจึงไม่มีวันถูกแทนที่จนกว่าจะขึ้น `SHELL_CACHE`
- **Correct Pattern/Solution:** **ห้ามใช้ `cache.addAll` กับรายการที่ path คงที่** — เขียนตัวช่วยที่ตรวจเนื้อก่อนเก็บ:
  ```js
  const type = res.headers.get('Content-Type') || ''
  const wantsHtml = u === '/' || u.endsWith('.html')
  if (!res.ok || (!wantsHtml && type.includes('text/html'))) return   // ไม่เก็บ
  await cache.put(u, res)
  ```
  · ตรวจ **ทั้งขาเข้าและขาออก** — ตอน `handleStatic` ถ้า `cache.match()` ได้ response ที่เป็น `text/html` ให้ **มองข้ามแล้วไปดึงใหม่** ไม่งั้นของเสียที่ค้างจากรุ่นก่อนจะยังถูกเสิร์ฟอยู่ · **อย่า `throw` เมื่อไฟล์ใดหาย** — `install` ที่ throw = SW ติดตั้งไม่สำเร็จทั้งตัว ซึ่งแย่กว่าการขาดไอคอนหนึ่งใบ ⇒ ใช้ `Promise.allSettled` + `console.warn` รายงานแทน · และ **ขึ้น `SHELL_CACHE`** (`piri-shell-v1` → `v2`) เมื่อแก้กลไก precache เพื่อล้างของเสียที่ค้างในเครื่องผู้ใช้เดิม
- **⚠️ กฎที่กว้างกว่า:** `try_files $uri /index.html` ทำให้ **ทุก path ที่ไม่มีไฟล์จริงตอบ `200` พร้อม HTML** ⇒ โค้ดใดก็ตามที่ตัดสินใจจาก HTTP status ว่ามีไฟล์จริง (curl, health check, precache, `fetch().ok`) **จะเชื่อผิดทุกครั้ง** ให้ดู `Content-Type` เสมอ
- **Date Added:** 2026-09-28

### 🛠️ PWA: `beforeinstallprompt` ยิง**ครั้งเดียวและกู้คืนไม่ได้** — listener ต้องผูกตอน import ไม่ใช่หลัง `app.mount()` · และเบราว์เซอร์ **ห้าม** เว็บติดตั้งแอพเอง
- **Context/Problem:** ผู้ใช้ถามว่า "แก้ให้เพิ่มลงหน้าจออัตโนมัติ" — ปัญหาจริงคือ **ติดตั้งไม่ขึ้นเลย** ตรวจแล้วพบสาเหตุจาก CDN cache (บทเรียนข้างบน) และยังเจอบั๊กในโค้ดอีกชั้น
- **Root Cause:** `pwa.ts` ผูก `window.addEventListener('beforeinstallprompt', …)` ไว้ **ใน `registerPwa()`** ซึ่ง `main.ts` เรียก *หลัง* `app.mount()` ⇒ เกิด **race**: Chrome ประเมิน installability (manifest + SW + ไอคอนครบ) แล้วยิง event ได้ทันทีที่โหลดหน้า ถ้า event ยิงก่อน listener ผูก มัน **หายไปเลย ไม่มี replay** ⇒ ผู้ใช้ไม่เห็นแบนเนอร์ตลอดเซสชันนั้น · อีกสองบั๊กที่เจอพร้อมกัน: (1) `promptInstall()` ใช้ **คีย์เดียว** กับ `dismissInstall()` ⇒ คนที่ติดตั้งแล้วถอนการติดตั้ง **จะไม่ถูกชวนอีกเลยตลอดไป** (2) `showInstallBanner` เช็ค `isDismissed()` แค่ตอน event ยิง ไม่ได้เช็คตอนอ่านค่า
- **Correct Pattern/Solution:** ผูก listener ที่ **ระดับโมดูล** ของไฟล์ที่ `main.ts` import ก่อน `mount()`:
  ```ts
  if (typeof window !== 'undefined') {
    window.addEventListener('beforeinstallprompt', (e) => { e.preventDefault(); … })
  }
  ```
  · **แยกคีย์ `piri_installed` ออกจาก `piri_install_dismissed`** — "ติดตั้งแล้ว" กับ "ไม่อยากติดตั้ง" คนละเรื่อง · **ต่อ `?v=<build-id>` ท้าย URL ของ `sw.js`** (`vite.config.ts` ฉีด `__BUILD_ID__` จาก short git SHA) ⇒ CDN ไม่มี URL เก่าให้เสิร์ฟ เป็นวิธีที่ทนที่สุดและไม่ต้องพึ่ง CF (ตรงกับข้อ (3) ของบทเรียน CDN)
- **⚠️ ข้อจำกัดที่ **บอกผู้ใช้ตรง ๆ** ทุกครั้ง (อย่าสัญญาว่าทำได้):** **เว็บติดตั้งแอพเองโดยไม่ให้ผู้ใช้ยืนยันไม่ได้เลย** — Chrome ต้องเรียก `prompt()` และต้องมี user gesture (ยอมให้เรียกใน handler ของ `beforeinstallprompt` ได้) ส่วน **iOS Safari ไม่มี API ติดตั้งใด ๆ ทั้งสิ้น** และไม่ยิง `beforeinstallprompt` ⇒ ทางเดียวคือสอนให้กด **แชร์ → "เพิ่มไปที่หน้าจอ"** (เฉพาะ Safari — Chrome/Firefox บน iOS ทำไม่ได้เลย) · และ **อย่าเดาจาก user agent ว่า "ติดตั้งได้"** ให้แสดงปุ่มเฉพาะเมื่อได้ event จริง ไม่งั้นจะโชว์ปุ่มที่กดแล้วเงียบ
- **Date Added:** 2026-09-28

### ✋ "ติดตั้งอัตโนมัติ" ทำได้จริงแค่ไหน: `prompt()` ต้องอยู่ใน **user gesture** — แต่ gesture **ไม่จำเป็นต้องเป็นปุ่มติดตั้ง** ("แตะที่ไหนก็ได้" ก็พอ)
- **Context/Problem:** ผู้ใช้สั่งว่า "แก้ให้เพิ่มลงหน้าจออัตโนมัติด้วยนะ เป็นไอคอน" — คำขอนี้ทำตามตรง ๆ ไม่ได้ และถ้าทำตามที่ผู้ใช้พูดแบบไม่ตรวจข้อจำกัด จะได้ปุ่มที่กดแล้วเงียบ
- **Root Cause:** สองข้อจำกัดที่ **แก้ไม่ได้ด้วยโค้ด** และต้องบอกผู้ใช้ตรง ๆ เสมอ:
  1. **เบราว์เซอร์ห้ามเว็บติดตั้งแอพเอง** — Chrome บังคับว่า `BeforeInstallPromptEvent.prompt()` ต้องเรียก **ระหว่าง user gesture** ("must be called during a user gesture") ⇒ dialog เด้งเองตอนโหลดหน้า ทำไม่ได้เลย
  2. **iOS Safari ไม่มี API ติดตั้งใด ๆ** และไม่ยิง `beforeinstallprompt` ⇒ ทางเดียวคือ "แชร์ → เพิ่มไปที่หน้าจอ" (และ **Chrome/Firefox บน iOS ก็ทำไม่ได้เลย** ไม่ใช่แค่ Safari)
- **Correct Pattern/Solution:** ข้อ 1 มีช่องว่างที่ใช้ได้ — **gesture ไม่จำเป็นต้องเป็นการกดปุ่มติดตั้ง** การแตะที่ไหนก็ได้ในหน้าถือเป็น gesture และ Chromium **ไม่ consume** gesture นั้น (แค่ตรวจว่ามี gesture ทำงานอยู่) ⇒ ยิง dialog ตอน **แตะแรกของผู้ใช้** ได้ โดยผู้ใช้ไม่ต้องหาปุ่ม:
  ```ts
  function onFirstGesture() {          // ผูกตอนได้ beforeinstallprompt
    if (!autoPromptArmed) return
    disarmAutoPrompt()                 // ถอด listener ทันที — ยิงครั้งเดียว
    if (!deferredPrompt.value) return
    writeFlag(AUTO_ASKED_KEY)
    void promptInstall()               // ⚠️ ทุกบรรทัดก่อนนี้ต้อง synchronous
  }
  document.addEventListener('click', onFirstGesture, { capture: true })
  document.addEventListener('keydown', onFirstGesture, { capture: true })  // ผู้ใช้คีย์บอร์ด
  ```
  · **ห้ามมี `await` คั่นก่อนเรียก `prompt()`** ไม่งั้น gesture หลุด (บทเรียนเดียวกันกับ `chrome.permissions.request`) — เคสคลาสสิกคือเผลอ `await` อะไรบางอย่างก่อน แล้วปุ่มเงียบโดยไม่มี error
  · **ยิงเองได้ครั้งเดียวตลอดไป** ⇒ ใช้คีย์แยก `piri_install_auto_asked` ไม่งั้นจะยิงซ้ำทุกเซสชัน = การรบกวน · หลังจากนั้นกลับมาเป็นแบนเนอร์ให้กดเอง
  · **ซ่อนแบนเนอร์ระหว่างรอแตะแรก** (`autoAskPending`) — ไม่งั้นผู้ใช้เห็นทั้ง dialog ของเบราว์เซอร์และแบนเนอร์ของเราพร้อมกัน ซึ่งดูเหมือนบั๊ก
  · **`dismissInstall()` ต้องยกเลิกคำขอที่รออยู่ด้วย** — "ไม่เอา" ต้องชนะ "กำลังจะถาม"
- **⚠️ กับดักตอนเทส (เจอจริงในรอบนี้):** กลไกนี้ผูก listener ระดับโมดูลและไม่เคยถอด ⇒
  (1) **อย่า `vi.resetModules()` ต่อเทส** — listener ของโมดูลรุ่นเก่ายังค้างบน `document` แล้วแตะครั้งเดียวยิงพร้อมกันทุกรุ่น (mock ถูกเรียกซ้ำ → เทสล้มด้วยเหตุผลของการทดสอบเอง) ให้ import ครั้งเดียวตลอดไฟล์ (ตรงกับความจริงที่โมดูลเป็น singleton) แล้วแยกสถานะด้วย `localStorage.clear()` + `dismissInstall()`
  (2) **jsdom ไม่มี `window.matchMedia`** (`typeof` = `"undefined"` ⇒ `registerPwa()` throw) ต้อง stub
  (3) **`beforeinstallprompt` ไม่ใช่ event มาตรฐาน** ต้องสร้าง `new Event(...)` แล้วแปะ `prompt`/`userChoice` เอง (ของจริงต้องมี HTTPS + ไอคอนครบ + engagement heuristic ถึงยิง ⇒ จำลองไม่ได้ในเครื่อง dev)
  (4) `typeof someUndeclaredVar` **ไม่มีวัน throw** ⇒ ใช้ `typeof` ตรวจว่ามี API ไหมไม่ได้ ให้ใช้ `try/catch` หรือ `in`
- **Date Added:** 2026-09-28

### 🔁 "ติดตั้งแล้ว" ≠ "ติดตั้งอยู่": การถอนแอพ **ไม่ล้าง site data** ⇒ ธงใน `localStorage` ค้าง แล้วบล็อกการติดตั้งตลอดไป
- **Context/Problem:** ผู้ใช้ถามตรง ๆ ว่า *"ไอที่เช็คว่าติดตั้งหรือไม่ติดตั้งนี้ เช็คยังไงอ่ะ คือเก็บราย user เลยหรอ แล้วถ้ากดถอดการติดตั้ง เราจะทำให้มันกดติดตั้งใหม่ได้ยังไง"* — คำถามนี้ชี้บั๊กจริงที่ยังเหลืออยู่
- **Root Cause:** **ไม่มีอะไรเก็บที่เซิร์ฟเวอร์เลย** (ไม่ผูกกับ user) — สถานะติดตั้งมีสองแหล่ง และมีอันเดียวที่เชื่อได้:
  - **`window.matchMedia('(display-mode: standalone)').matches`** = เบราว์เซอร์บอกเองว่าตอนนี้รันในโหมดแอพ ⇒ **เป็นความจริงสด ๆ และรีเซ็ตเองเมื่อถอนแอพ**
  - **ธงใน `localStorage`** (`piri_installed`) = ความจำของเราเอง ⇒ **การถอนแอพไม่ล้าง site data** ⇒ ธงค้างเป็น `1` ตลอดไป
  ⇒ โค้ดเดิมเอา `isInstalled()` ไป **บล็อก** `canInstallState` และบล็อก `armAutoPrompt()` ⇒ ผู้ใช้ที่ติดตั้ง → ถอน **ไม่มีทางติดตั้งกลับได้อีกเลย**
- **Correct Pattern/Solution:** **`beforeinstallprompt` ที่ยิงมา = เบราว์เซอร์ยืนยันสด ๆ ว่า "ตอนนี้ติดตั้งได้"** (Chrome **ไม่ยิง event นี้ให้แอพที่ติดตั้งอยู่แล้ว**) ⇒ ใช้เป็นจังหวะซ่อมธงให้หายเอง:
  ```ts
  window.addEventListener('beforeinstallprompt', (event) => {
    event.preventDefault()
    deferredPrompt.value = event
    clearFlag(INSTALLED_KEY)          // ★ ซ่อมตัวเอง — หลักฐานสดชนะความจำเก่า
    canInstallState.value = !isDismissed()
    armAutoPrompt()
  })
  ```
  · **อย่าเอา "ติดตั้งแล้ว" ไปเป็นเงื่อนไขบล็อกการติดตั้ง** — มันซ้ำซ้อนกับสิ่งที่เบราว์เซอร์กรองให้แล้ว และกลายเป็นกับดักถาวร ⇒ `armAutoPrompt()` ไม่ต้องเช็ค `isInstalled()` เลย (เป็นโค้ดตาย)
  · **ต้องมีทางกลับเมื่อผู้ใช้กด ✕ ปิดแบนเนอร์เองด้วย** — แบนเนอร์จำการปิดแล้วไม่ขึ้นอีก ⇒ เพิ่มปุ่ม "ติดตั้งเลย" ในการ์ด Profile ที่ **ไม่ผูก `DISMISS_KEY`** และให้ `installNow()` ล้างค่านั้นก่อนเรียก `promptInstall()` ("คำสั่งตรงของผู้ใช้" ชนะ "เคยกดปิด")
  · **เทสที่เคยยืนยันพฤติกรรมเก่าต้องเขียนใหม่ ไม่ใช่ลบ** — เทสเดิมชื่อ *"เคยติดตั้งแล้ว → ไม่ยิงเอง"* ยืนยันบั๊กอยู่ ⇒ เปลี่ยนเป็นยืนยันกติกาใหม่ ("ไม่มี event = ไม่มีอะไรเกิดขึ้น") แล้วคอมเมนต์ว่าทำไม
- **⚠️ กับดักตอนเทส:** `deferredPrompt` เป็น state ระดับโมดูลและ **`dismissInstall()` ไม่ล้างมัน** (เจตนา — การ์ด Profile ต้องใช้ต่อ) ⇒ เทสที่ dispatch event แต่ **ไม่ยิง prompt** จะทิ้ง event ค้างไปเทสถัดไป ⇒ ต้อง **บริโภคทิ้งด้วย API สาธารณะ** ใน `beforeEach` (`dispatchEvent(makeInstallEvent('dismissed').event)` แล้ว `await promptInstall()`) — เช่นเดียวกับ `standaloneState` ที่ต้องรีเซ็ตด้วย `registerPwa()` ทุกเทส
- **Date Added:** 2026-09-28

### 📱 ไอคอนลงหน้าจอ **เองไม่ได้** — เป็นสิทธิ์ของ launcher/OS ไม่ใช่ของเว็บ (และไอคอนแอพควรเป็นโลโก้ล้วน ๆ ไม่ต้องมีวงซ้อน)
- **Context/Problem:** ผู้ใช้รายงาน *"ไม่ใช่ว่ามันติดตั้งไม่ได้นะ แต่ว่า ติดตั้งแล้ว มันไม่ไปโผล่หน้าหลักเฉยๆ ต้องลากไปเอง"* — เป็นคำถามต่อเนื่องจากคำขอเดิม "เพิ่มลงหน้าจออัตโนมัติ เป็นไอคอน"
- **Root Cause:** **ไม่มี Web API ใด ๆ ที่สั่งให้ launcher วางไอคอนบนหน้าจอหลักได้** — การวางไอคอนเป็นการตัดสินใจของ launcher หลังติดตั้ง WebAPK เสร็จ · **การที่ไอคอนไม่อยู่บนหน้าจอ แต่แอพอยู่ใน app drawer = ติดตั้งเป็น WebAPK สำเร็จแล้ว** (ถ้าเป็น shortcut ธรรมดา มันจะอยู่แค่หน้าจอหลัก **และไม่มีใน drawer**) ⇒ อาการนี้มาจาก **ตั้งค่า launcher** ("เพิ่มไอคอนแอพใหม่ไปหน้าจอหลัก" ปิดอยู่) หรือบั๊กของ Android 15 + Chrome บางรุ่น — **ทั้งสองอย่างอยู่นอกเหนือการควบคุมของเว็บ**
- **Correct Pattern/Solution:** สิ่งที่เว็บทำได้มีเท่านี้ และทำครบแล้ว — manifest ถูกต้อง + ไอคอนครบ + service worker ที่มี fetch handler (จำเป็นต่อการได้ **WebAPK** ไม่ใช่ shortcut) + ยิง dialog ตอนแตะแรก · **ที่เหลือต้องบอกผู้ใช้ตรง ๆ ว่าแก้ที่โค้ดไม่ได้** และชี้ทาง: ตั้งค่า launcher → "เพิ่มไอคอนแอพใหม่ไปหน้าจอหลัก" · หาแอพใน **app drawer** แล้วลากออกมา · บางรุ่น **กดค้างที่ไอคอนใน dialog ตอนติดตั้งแล้วลากไปวางเลย**
- **⚠️ อย่าล่อใจ "ทำให้อ่อนลงเป็น shortcut" เพื่อบังคับให้ได้ไอคอน** — shortcut วางบนหน้าจอหลักแน่ก็จริง แต่แลกมาด้วยการเสีย `display: standalone` และไอคอนจะติดตราเบราว์เซอร์ ⇒ ไม่คุ้ม
- **🎨 ไอคอนแอพ: ซ้อนหลายชั้นแล้วดูรก** — ของเดิมเป็น สี่เหลี่ยมแดง → วงกลมขาว → โลโก้โรงเรียน ⇒ ผู้ใช้ทักว่า *"โลโก้โรงเรียนซ้อนขาว ซ้อนแดง อะไรไม่รู้เยอะแยะ"* · โลโก้โรงเรียน (พิริยาลัย) **เป็นวงกลมมีขอบขาว/น้ำเงินในตัวอยู่แล้ว** ⇒ ใส่วงกลมซ้อนเข้าไปอีกจึงซ้ำซ้อน · ทางที่ถูกคือ **ใช้ภาพโลโก้ล้วน** แล้วครอปเฉพาะ 5% ที่เป็นขอบโปร่งใส ส่วน maskable ค่อยเติมพื้นขาว + ย่อโลโก้ลงใน safe zone 80%
  · อัตราส่วนที่ใช้จริง: `any` = โลโก้เต็มกรอบ (โปร่งใส รอบนอก) · `maskable` = พื้นขาว + โลโก้ 76% · `apple-touch-icon` = พื้นขาว + โลโก้ 86% (iOS ไม่รองรับความโปร่งใส — ถ้าปล่อยโปร่งจะกลายเป็นพื้นดำ)
- **Date Added:** 2026-09-28

### 🔁 ลบไอคอนออกจากหน้าจอ **ไม่ใช่** การถอนแอพ — WebAPK ยังลงทะเบียนกับ Chrome อยู่ ⇒ `beforeinstallprompt` ไม่ยิงอีกเลย (และสถานะการติดตั้งเป็น **per-เบราว์เซอร์ ไม่ใช่ per-บัญชี**)
- **Context/Problem:** ผู้ใช้ถามว่า *"ทำไงให้แจ้งเตือนให้ติดตั้งมันโผล่ … นี่สลับบัญชีเข้าไป ก็ยังไม่ขึ้นให้ หรือเป็นเพราะเคยกดติดตั้งในบัญชีแอดมินไปแล้ว ละมันจำ หรอ แต่กุกด uninstall ไปแล้วนะ"* — ขณะที่ฝั่งเซิร์ฟเวอร์ถูกครบแล้ว (manifest · `sw.js` · ไอคอน · `content-type` ถูกทุกตัว)
- **Root Cause:** **สองความเข้าใจผิดที่ต้องแยกให้ออก**
  1. **ไม่มีสถานะการติดตั้งอยู่บนเซิร์ฟเวอร์เลย** — PWA install state อยู่ที่ `localStorage` ของเบราว์เซอร์ (per-origin) + ทะเบียน WebAPK ของ Chrome ⇒ **สลับบัญชี PIRIvoice ไม่มีผลใด ๆ** ต่อการติดตั้ง (คนละเรื่องกับ auth โดยสิ้นเชิง)
  2. **"ลากไอคอนทิ้ง" ≠ "ถอนการติดตั้ง"** — การลบ shortcut บนหน้าจอหลักไม่แตะทะเบียน WebAPK · และ **การถอนแอพก็ไม่ล้าง site data** ⇒ `localStorage` ยังอยู่ ⇒ Chrome ยังถือว่า "ติดตั้งอยู่" ⇒ **ไม่ยิง `beforeinstallprompt`** ⇒ แบนเนอร์/ปุ่มไม่ขึ้นตลอดไป (อาการเดียวกับ [[บทเรียน "ติดตั้งแล้ว ≠ ติดตั้งอยู่"]] แต่คนละสาเหตุ)
- **Correct Pattern/Solution:** ตรวจที่ **`chrome://webapks`** บน Android — **ไม่ใช่หน้าจอหลัก** · ถ้ายังเห็น PIRIvoice อยู่ ให้กด **Uninstall ที่นั่น** แล้วเปิดเว็บใหม่ ⇒ event ยิงทันที (ผู้ใช้ยืนยันเองว่าได้ผล: *"กุลบ มันขึันแล้ว สุดยอด"*)
  · ฝั่งโค้ดมี **การ์ด "ติดตั้งแอป" ใน `Profile.vue`** เป็นเครื่องมือวินิจฉัยในตัว — เห็นปุ่ม "ติดตั้งเลย" = event ยิงแล้ว (ปัญหาอยู่ที่แบนเนอร์) · เห็นข้อความ "เปิดด้วย Chrome แล้วเลือก ⋮" = event ไม่ยิง (ปัญหาอยู่ที่ Chrome/OS)
  · และเมื่อ `beforeinstallprompt` ยิง = **หลักฐานสดว่า installable** ⇒ ใช้โอกาสนั้น **ล้างธง "ติดตั้งแล้ว" ที่ค้าง** (self-healing — ดูบทเรียนก่อนหน้า)
- **Date Added:** 2026-09-28

### 🛠️ migration แบบ **additive ล้วน** (`CREATE TABLE IF NOT EXISTS` + index · ไม่มี `ALTER`/`DROP`) ⇒ **rollback กลับ image เก่าได้** — ต่างจากคำเตือนกว้าง ๆ ว่า "migrate แล้ว rollback ไม่ได้"
- **Context/Problem:** แผน §11 เขียนเตือนไว้กว้าง ๆ ว่า *"migrate แล้วจะ rollback กลับ image เก่าไม่ได้"* ⇒ ทำให้การตัดสินใจ deploy production ช้ากว่าที่ควร ทั้งที่ migration รอบนี้เป็น **การเพิ่มตารางใหม่** เท่านั้น
- **Root Cause:** คำเตือนนั้น **จริงเฉพาะ migration ที่แก้ของเดิม** (`ALTER TABLE … ADD COLUMN NOT NULL` · rename · drop) เพราะ image เก่าไม่รู้จักสคีมาใหม่แล้วอ่าน/เขียนเพี้ยน · แต่ถ้าเป็น **ตาราง/index ใหม่ล้วน** image เก่าแค่ **ไม่รู้จัก** และ**ไม่สนใจ**มัน ⇒ ทำงานต่อได้ปกติ
- **Correct Pattern/Solution:** ก่อน deploy ที่มี migration ให้วัดระดับความเสี่ยงจาก diff จริงเสมอ:
  ```bash
  git diff <old>..<new> -- backend/core/init_db.py | grep -E '^[-+]' | grep -v '^[-+][-+]'
  # ดูบรรทัดที่ "ลบ" — ถ้าที่ลบมีแต่คอมเมนต์ = additive ล้วน
  ```
  · `CREATE TABLE IF NOT EXISTS` + `CREATE INDEX IF NOT EXISTS` = ปลอดภัย · `ALTER`/`DROP` = ต้องคิดหนักและควรมีแผน rollback แยก
  · **ก่อนแตะ production ต้องมี backup ที่ "กู้คืนได้" พิสูจน์แล้ว** ไม่ใช่แค่ไฟล์มีอยู่ — รอบนี้ทำ `pg_dump` แล้ว `pg_restore --list` ยืนยัน **22 ตารางกู้คืนได้** (2,618,043 bytes) ก่อน deploy
- **Date Added:** 2026-09-28

### ✋ cache ที่ถูก poison ไว้ **หายเองได้หลัง deploy รอบใหม่** — อย่าด่วนสรุปว่า "ต้อง purge" และอย่าตีความว่าฟีเจอร์พัง
- **Context/Problem:** หลัง deploy staging รอบก่อน พบ `/sw.js` และ `/icons/icon-192.png` ผ่าน CDN ได้ `200 text/html` (SPA fallback) ทั้งที่ต้นทางถูกต้อง ⇒ บันทึกไว้ว่า *"ต้องให้ผู้ใช้ไปล้างแคชใน CF dashboard หรือรอ ~4 ชม."*
- **Root Cause:** เมื่อ deploy รอบใหม่ nginx มีไฟล์จริงแล้ว ⇒ Cloudflare revalidate กับ origin เห็น `Last-Modified`/`ETag` ใหม่ ⇒ **เขียนทับของเสียเดิมเอง** โดยไม่ต้อง purge
- **Correct Pattern/Solution:** หลัง deploy ทุกครั้ง **ตรวจซ้ำก่อนสรุปว่าเสีย** — อย่าเชื่อบันทึกเก่า:
  ```bash
  curl -sI https://<host>/sw.js | grep -iE 'content-type|cache-control|cf-cache-status|age'
  ```
  รอบนี้ได้ `application/javascript` 14,734b · `cf=REVALIDATED` และไอคอน `image/png` 62,710b · `cf=HIT` ถูกต้องทั้งคู่ **⇒ ไม่ต้อง purge**
  · 🎯 บทเรียนที่สำคัญกว่าคือ **อย่าให้เกิดซ้ำ**: ใส่ `?v=<version>` ให้ static asset ที่ต้องคุมเวอร์ชันเอง (`sw.js` · ไอคอน)
    ⇒ cache key เปลี่ยน ⇒ คำตอบเสียเดิมไม่มีทางถูกหยิบมาใช้ และการ bump เวอร์ชันเป็นการบังคับรีเฟรชในตัว
  · 🚫 **ห้าม probe path ที่ยังไม่ deploy ผ่าน CDN** — นั่นคือวิธี poison cache ของตัวเอง (บทเรียนก่อนหน้า)
- **Date Added:** 2026-09-28

### 🧪 โค้ดที่ต้อง "อธิบายสาเหตุ" ต้องแยกเป็น **ฟังก์ชันบริสุทธิ์** — ไม่งั้นกิ่งที่สำคัญที่สุดเทสไม่ถึงเลย
- **Context/Problem:** `installHint` อธิบายว่าทำไมติดตั้งไม่ได้ (5 สาเหตุที่หน้าตาเหมือนกันแต่วิธีแก้คนละทาง) — ถ้าเขียนเป็น `computed` ที่อ่าน state ของโมดูลตรง ๆ จะ **เทสไม่ได้** เพราะ vitest ไม่ลงทะเบียน service worker (`import.meta.env.PROD` เป็น false) ⇒ `registration.value` เป็น `null` ตลอด ⇒ `swRegistered: false` **ทุกครั้ง** ⇒ กิ่งหลังจากนั้นกลายเป็น **โค้ดตายในเทส**
- **Root Cause:** สถานะที่มาจากสภาพแวดล้อมจริง (SW · `matchMedia` · install event) **ไม่มีทางถูกตั้งค่าได้ใน jsdom** ⇒ `computed` ที่ฝังอยู่จึงผูกติดกับค่าที่เทสควบคุมไม่ได้เลย
- **Correct Pattern/Solution:** แยก **ตรรกะ** ออกจาก **แหล่งข้อมูล**:
  ```ts
  export interface InstallDiagnostics { standalone: boolean; promptReady: boolean; /* … */ }
  export function installHintFor(d: InstallDiagnostics): string { /* ลำดับ if ล้วน */ }
  export const installDiagnostics = computed<InstallDiagnostics>(() => ({ /* อ่าน state จริง */ }))
  export const installHint = computed(() => installHintFor(installDiagnostics.value))
  ```
  ⇒ เทสป้อน `{ ...base, over }` ได้ทุกชุด · และมีเทส **"ต่อสายจริง"** แยกอีกตัวที่ยืนยันว่า `computed` ต่อกับ state จริงอยู่
  · ⚠️ **`import type` ถูกลบตอนคอมไพล์ ⇒ ไม่สร้างโมดูลอินสแตนซ์ที่สอง** — ปลอดภัยที่จะ `import type { InstallDiagnostics } from '@/pwa'` ในไฟล์เทสที่ใช้ `const pwa = await import('@/pwa')` เป็น singleton (ถ้า import แบบมีค่าจะได้คนละอินสแตนซ์ แล้ว state ไม่ตรงกัน)
  · ⚠️ **ลำดับ `if` คือสเปก** — ต้องมีเทสยืนยัน **ลำดับ** เช่น `promptReady` ต้องชนะ `dismissed` ⇒ assert **ทั้งขาบวกและขาลบ** (`toContain('กดปุ่ม')` และ `not.toContain('เคยกดปิดแบนเนอร์')`) ไม่งั้นสลับลำดับแล้วเทสยังผ่าน
- **Date Added:** 2026-09-28

### ⚠️ `localStorage` **ไม่ reactive** — หน้าที่ผูกค่าดิบจาก `readFlag()` จะค้างค่าเดิมไว้จนกว่าจะรีเฟรช
- **Context/Problem:** การ์ดวินิจฉัยใน Profile ต้องโชว์ "เคยกดปิดแบนเนอร์: ใช่" และเปลี่ยน **ทันที** เมื่อผู้ใช้กด ✕ — แต่ `readFlag()` อ่าน `localStorage` ตรง ๆ ⇒ Vue ไม่รู้ว่าค่าเปลี่ยน ⇒ ตัวเลขค้าง
- **Root Cause:** Vue ตามรอยได้แค่ `ref`/`reactive`/`computed` — ฟังก์ชันที่อ่าน `localStorage` ในเทมเพลตจะถูกเรียกใหม่เฉพาะเมื่อ dependency ที่ reactive เปลี่ยน ซึ่งกรณีนี้ **ไม่มีเลย**
- **Correct Pattern/Solution:** เก็บ **`ref` คู่ขนาน** กับค่าที่อยู่ใน `localStorage` แล้วให้ **ฟังก์ชันเขียนตัวเดียว** เป็นทางผ่านบังคับ:
  ```ts
  const dismissedState = ref(false); /* … */
  function setFlag(key: string, on: boolean): void {
    if (on) writeFlag(key); else clearFlag(key)
    if (key === DISMISS_KEY) dismissedState.value = on
    else if (key === AUTO_ASKED_KEY) autoAskedState.value = on
    else if (key === INSTALLED_KEY) installedState.value = on
  }
  ```
  ⇒ **ห้ามเรียก `writeFlag`/`clearFlag` ตรง ๆ อีก** (ไม่งั้นมีทางที่ ref กับ storage ไม่ตรงกัน) · และ `registerPwa()` ต้อง **seed ref ทั้งหมดจาก storage ตอนเริ่ม** ไม่งั้นค่าเริ่มต้นเพี้ยน
  · 🧪 เทสกันบั๊กนี้: กด ✕ → assert `installDiagnostics.value.dismissed` เปลี่ยน **และ** `localStorage` เปลี่ยน
  · 🧪 พิสูจน์แล้วว่ามีค่าจริง: ย้อน `dismissInstall()` ให้เรียก `writeFlag` ตรง ๆ (ตัด ref sync ออก) ⇒ เทสล้ม 1 ตัว
- **Date Added:** 2026-09-28

### 🛠️ เครื่องมือ: `gh pr edit` **พัง** ใน environment นี้ — ใช้ REST API ตรง ๆ แทน
- **Context/Problem:** `gh pr edit 44 --body-file /tmp/pr44_body.md` → **exit 1** พร้อม `GraphQL: Projects (classic) is being deprecated in favor of the new Projects experience…` ⇒ แก้ body ของ PR ไม่ได้เลยด้วยคำสั่งปกติ
- **Root Cause:** `gh pr edit` ยิง GraphQL query ที่ยังอ้าง `projectCards`/`projectItems` แบบ Projects classic ซึ่ง GitHub ปิดไปแล้ว ⇒ command ตายก่อนจะได้เขียนอะไร
- **Correct Pattern/Solution:** ใช้ REST endpoint ตรง ๆ — `gh api` ไม่ผ่าน GraphQL จึงไม่พัง:
  ```bash
  gh api repos/<owner>/<repo>/pulls/<n> -X PATCH -F body=@/tmp/pr_body.md --jq '.body | length'
  ```
  ⇒ `-F` (ไม่ใช่ `-f`) ทำให้อ่านค่าจาก **ไฟล์** ได้ (`@path`) และไม่ต้อง escape ภาษาไทย/backtick
  · ใช้ `--jq` ยืนยันความยาวที่เขียนจริง — **อย่าเชื่อว่า "คำสั่งผ่าน = เนื้อหาถูก"**
  · ⚠️ ฝั่งอ่านก็เลี่ยง `gh pr view --json` ที่อาจดึง field โครงการ — `gh api repos/<o>/<r>/pulls/<n>` ตรง ๆ ปลอดภัยกว่า
- **Date Added:** 2026-09-28

### 🚨 เทสต์ที่ **inject sender ปลอมทุกตัว** = โค้ดส่งจริงไม่เคยถูกรันเลย — ฟังก์ชันที่เสี่ยงที่สุดกลายเป็นจุดบอดที่สุด
- **Context/Problem:** `test_push_outbox.py` มี 16 เทสต์ที่ `monkeypatch` ทับ `_send_one` **ทั้งหมด** (เพื่อไม่ให้ยิง HTTP ออกเน็ต — ถูกต้อง) แต่ผลที่ตามมาคือ **VAPID signing + ECE encryption + การ decode คีย์** ซึ่งเป็นหัวใจของ Web Push **ไม่มีเทสต์ไหนแตะเลยแม้แต่บรรทัดเดียว** และไม่มีสัญญาณเตือนใด ๆ ว่าเป็นเช่นนั้น
- **Root Cause:** การ inject เพื่อแยก "ท่อ" (คิว/retry/status) ออกจาก "ปลายทาง" (การเซ็น+เข้ารหัส) เป็นการออกแบบที่ถูก — แต่ **การแยกออกไม่ได้แปลว่าจะมีคนทดสอบอีกฝั่ง** ⇒ ถ้าไม่มีเทสต์ใบที่สอง มันจะไม่ถูกทดสอบเลยตลอดไป และโค้ดส่วนนั้นจะพังเงียบ ๆ ตอน deploy
- **Correct Pattern/Solution:** ไล่หาจุดบอดด้วยคำสั่งเดียว — **ทุกฟังก์ชันที่ถูก `monkeypatch` ในเทสต์ ต้องมีเทสต์อย่างน้อย 1 ตัวที่รันของจริง**:
  ```bash
  grep -rn "_send_one" backend/tests/   # ถ้าเจอแต่ monkeypatch.setattr ⇒ ยังไม่มีเทสต์จริง
  ```
  แล้วเขียนเทสต์ที่รันของจริง **โดยไม่ออกอินเทอร์เน็ต** — `ThreadingHTTPServer` ผูก `127.0.0.1:0` (ขอ port ว่างจาก OS) เก็บ `{path, headers, body}` แล้วปล่อยผ่าน `_send_one` ทั้งเส้น
  · ⭐ **สิ่งที่ได้เกินคาด:** เทสต์นี้ตรวจ `generate_vapid_keys.py` ไปด้วย — โหลดสคริปต์นั้นด้วย `importlib` แล้วใช้ `_b64url`/`_raw_public` ตัวเดียวกับที่มันจะเขียนลง `.env` ⇒ **พิสูจน์รูปแบบคีย์ที่สคริปต์ผลิตจริง** ไม่ใช่คีย์ที่เทสต์แต่งขึ้นเอง
  · ⚠️ `ThreadingHTTPServer` + `daemon_threads = True` ไม่งั้นเทสต์ค้างตอน teardown
- **Date Added:** 2026-09-28

### 🔐 พิสูจน์ว่า "เข้ารหัสถูก" ได้ทางเดียวคือ **ถอดกลับด้วยคีย์ของคนรับ** — ไม่ใช่ assert ว่าหัวข้อ HTTP หน้าตาถูก
- **Context/Problem:** push payload ถูกเข้ารหัสแบบ ECE (RFC 8188) ก่อนส่ง ⇒ ดูจากภายนอกเห็นแค่ byte ทึบ · จะ assert ว่า `Content-Encoding: aes128gcm` มีอยู่ **ไม่ได้พิสูจน์อะไรเลย** ว่าไบต์ข้างในถอดออกมาเป็นข้อความที่ถูกรหัสถูก
- **Root Cause:** การเข้ารหัสที่ผิด (สลับ `dh`, ลืม `auth_secret`, reuse ephemeral key) จะให้ header ที่ถูกต้องทุกตัวเหมือนกัน ⇒ ตรวจ header = ตรวจสิ่งที่ไม่มีทางผิด
- **Correct Pattern/Solution:** ในเทสต์ สร้างคู่กุญแจฝั่ง "เบราว์เซอร์" ขึ้นมาจริง (`ec.generate_private_key(SECP256R1())` + `os.urandom(16)`) แล้ว **ถอดรหัส body ที่เซิร์ฟเวอร์ส่งมาจริง**:
  ```python
  http_ece.decrypt(body, private_key=browser_priv, auth_secret=raw_auth, version="aes128gcm")
  ```
  · ⭐ **ไม่ต้องส่ง `dh`** — `http_ece.decrypt` จะอ่าน `keyid` จาก header เองมาใช้เป็น ephemeral public key ของผู้ส่ง (โครง body คือ `salt(16) ‖ rs(4) ‖ idlen(1) ‖ keyid`) ⇒ นี่คือ round-trip เต็มวง
  · ⚠️ `auth_secret` ต้องเป็น **bytes ดิบ** (`os.urandom(16)`) ไม่ใช่ base64 — เก็บ raw ไว้คู่กับ base64 ที่ส่งไป
  · และเทสต์ E4 ที่ยืนยันว่า `keyid` **เปลี่ยนทุกครั้ง** ⇒ กันบั๊ก "reuse ephemeral key" ที่ทำให้เข้ารหัสอ่อนลงโดยที่เทสต์อื่นไม่จับ
- **Date Added:** 2026-09-28

### ⚠️ base64url: "สตริงไม่มี padding" กับ "สตริงที่ต่อ `=` เข้าไป" **ไม่ใช่คู่ตรงข้ามกัน** — ต่อ `=` มั่ว ๆ ได้สตริงที่ *เสีย* ไม่ใช่สตริงที่ *มี padding*
- **Context/Problem:** เทสต์ครอบ `_repad()` (เติม padding ให้ base64url จากเบราว์เซอร์ก่อน decode) โดยใช้ `os.urandom(48)` แล้วต่อ `"="` คิดว่าเป็นเคส "มี padding" ⇒ **เทสต์ผ่านทั้งที่ถอด `_repad()` ออกก็ยังผ่าน** (mutation รอด ชี้ว่ามันไม่ได้ทดสอบอะไร)
- **Root Cause:** base64 ของ **48 byte = 64 ตัวอักษรพอดี ไม่ต้องมี padding อยู่แล้ว** ⇒ การต่อ `=` เข้าไปทำให้ได้สตริง *ผิดรูปแบบ* ซึ่ง `urlsafe_b64decode` ก็ยัง decode ผ่าน (มันทน `=` เกิน) ⇒ สองเคสที่ตั้งใจให้ต่างกัน **เหมือนกันจริง ๆ**
- **Correct Pattern/Solution:** padding = `(3 - n % 3) % 3` ⇒ **ขนาดต้องครอบทั้ง 3 เศษของ `len % 3`** ไม่ใช่เลือกตามความรู้สึก:
  | `n % 3` | padding | ตัวอย่างจริง |
  |---|---|---|
  | 2 | `=` 1 ตัว | `p256dh` 65 byte · 32 byte |
  | 1 | `=` 2 ตัว | `auth` 16 byte |
  | 0 | ไม่เติม | 48 byte |
  ```python
  raw = os.urandom(size)
  encoded = base64.urlsafe_b64encode(raw).decode()
  assert (encoded.endswith("=")) != (size % 3 == 0), "ขนาดนี้ไม่ครอบเคส padding ที่ตั้งใจ"
  ```
  · ⭐ **assert ตัวนั้นคือหัวใจ** — ให้เทสต์ **ปฏิเสธตัวเอง** ถ้า parametrize ที่เลือกไม่ครอบเคสจริง (กันคนมาแก้ตัวเลขทีหลังแล้วเทสต์กลายเป็นพิธีกรรมอีก)
  · หลักทั่วไป: เทสต์ที่จับคู่ "แบบ A / แบบ B" ต้องพิสูจน์ก่อนว่า **A ≠ B จริง** ไม่งั้นมันคือเทสต์เดียวกันรันสองรอบ
- **Date Added:** 2026-09-28

### 🔑 `Vapid02.sign()` **validate `sub`/`aud` เอง** ⇒ พิมพ์ `VAPID_SUBJECT` ผิด = push ทุกอันล้มตอน *เซ็น* ก่อนถึงขั้น HTTP
- **Context/Problem:** `VAPID_SUBJECT` ใน `.env` พิมพ์ผิด (ไม่มี `mailto:`) ⇒ **push ทุกครั้งล้ม** ด้วย error ที่โผล่ตอนเซ็น ไม่ใช่ตอนส่ง ⇒ อาการที่เห็นคือ "push ไม่ขึ้นเลย" ซึ่งชี้ไปผิดที่ (ไปหาที่ FCM/เครือข่าย กว่าจะเจอว่าอยู่ใน `.env`)
- **Root Cause:** `py_vapid.Vapid02._base_sign()` ตรวจ claims เองก่อนเซ็น — `sub` ต้องเป็น `mailto:` หรือ URL และ `aud` ต้อง match `^https?://[^/:]+(:\d+)?$` คือ **ห้ามมี path** และ **ต้องมี port ถ้าปลายทางมี**
- **Correct Pattern/Solution:** สร้าง `aud` จาก endpoint เสมอ ห้ามใช้ค่าคงที่:
  ```python
  u = urlparse(sub["endpoint"])
  headers = _vapid.sign({
      "sub": settings.VAPID_SUBJECT,          # mailto:council@… เท่านั้น
      "aud": f"{u.scheme}://{u.netloc}",      # ← origin รวม port ตัด path ทิ้ง
      "exp": int(time.time()) + 12 * 3600,
  })
  ```
  · 🧪 เทสต์ตรวจด้วย `jose.jwt.decode(token, pem, algorithms=["ES256"], audience=f"http://127.0.0.1:{port}")`
  · ⚠️ **`jose.jwt.decode` โยน `JWTClaimsError: Invalid audience` ถ้าไม่ส่ง `audience=`** ⇒ การส่ง `audience=` เข้าไปคือการ **ให้ไลบรารีเป็นคน assert** ดีกว่า decode แล้วมาเทียบเอง (ผิดแล้วเงียบ)
  · และเทสต์ `sub` ที่ผิด → assert ว่า **`push_server.captured == []`** ⇒ พิสูจน์ว่า "ล้มตอนเซ็น" แปลว่า **ไม่มีการยิง HTTP ออกไปเลย** ไม่ใช่ "ยิงไปแล้วโดนปฏิเสธ"
- **Date Added:** 2026-09-28

### 🧪 เทสต์ 401 ที่ "ผ่านเพราะ dependency โยนเอง" **ไม่ได้พิสูจน์ว่าด่านของเรามีอยู่**
- **Context/Problem:** endpoint "ของฉัน" ทุกตัวกันด้วย `_ensure_user()` (โยน 401 เมื่อ `user_id` เป็น `None`) · เทสต์ "ไม่มี header → 401" **ผ่านตลอด** ไม่ว่าจะมี `_ensure_user` หรือไม่ — เพราะมันล้มที่ชั้น `get_current_user` **ก่อน**ถึงบรรทัดของเรา
- **Root Cause:** `get_current_user` โยน 401 เองเมื่อไม่มี auth header เลย **แต่คืน `{"user_id": None}` เงียบ ๆ** เมื่อเรียกด้วย `X-API-Key` (system RPC) ⇒ มีแค่เส้นทางหลังเท่านั้นที่ไปถึงด่านของเรา
- **Correct Pattern/Solution:** ต้องมีเทสต์ที่ยิงด้วย `X-API-Key` แยกต่างหาก — **นั่นคือเทสต์ที่รับน้ำหนัก** (พิสูจน์แล้ว: ถอด `_ensure_user` → เทสต์ `X-API-Key` ล้ม 3/3 · เทสต์ "ไม่มี header" **ยังผ่าน**)
  · ⚠️ **mutation เดียวกันให้ผลไม่เหมือนกันในแต่ละ route** — ถอดด่านออกแล้ว:
    - `subscribe` / `unsubscribe` → เขียน `user_id = NULL` → FK violation → **500** (ดูเหมือนฐานข้อมูลพัง)
    - `status` → **200 พร้อมค่า 0** ซึ่ง **แย่กว่า 500** เพราะดูเหมือนสำเร็จ
  ⇒ **ก่อนเขียนเทสต์ 401 ต้องถามก่อนว่า "401 นี้มาจากโค้ดเราหรือจาก framework"** ถ้าตอบไม่ได้ เทสต์นั้นไม่มีค่า
- **Date Added:** 2026-09-28

### ⚠️ mutation ที่ **ลบไม่ครบ** ทำให้เทสต์ล้มด้วย *เหตุผลผิด* — ต้องอ่านข้อความ assert ไม่ใช่ดูแค่จำนวนที่ล้ม
- **Context/Problem:** mutation ของช่องโหว่ "ลบ endpoint ของคนอื่นได้" คือการถอด `AND user_id = $1` ออกจาก `DELETE` — แต่ทำแล้วล้ม **2 เทสต์** ซึ่งดูเหมือนสำเร็จ ทั้งที่จริงล้มเพราะ **error คนละเรื่อง** (ลบเงื่อนไขออกแล้วไม่ได้ลบ argument ⇒ จำนวน `$` ไม่ตรงกับ params)
- **Root Cause:** mutation ที่ "ครึ่ง ๆ กลาง ๆ" เปลี่ยนทั้ง *พฤติกรรม* และ *รูปแบบโค้ด* พร้อมกัน ⇒ เทสต์ล้มด้วยสาเหตุที่สอง ไม่ใช่สาเหตุที่ตั้งใจ
- **Correct Pattern/Solution:** ทำ mutation ให้ **faithful** (ตัด argument ที่ไม่ใช้ออกด้วย) แล้ว **อ่านข้อความล้มจริง**:
  ```
  AssertionError: B ลบของ A ได้ ⇒ ช่องโหว่
  assert 1 == 0
  ```
  ⇒ หลังแก้: **ล้มตัวเดียว (S4) และ S5 ผ่าน** = ตรงกับที่ออกแบบ
  · 🧪 หลักที่ใช้ตัดสิน mutation ทุกตัว: **(ก)** ล้มเฉพาะเทสต์ที่ควรรับ **(ข)** ข้อความล้มตรงกับกลไกที่ตั้งใจ — ถ้าเข้าเงื่อนไขไม่ครบ ให้ถือว่า mutation ยังไม่ถูกต้อง ไม่ใช่ "เทสต์จับได้แล้ว"
  · 💡 เทคนิคช่วย: เขียนข้อความ assert ให้ **บอกกลไก** ("B ลบของ A ได้ ⇒ ช่องโหว่") ไม่ใช่แค่ "ควรเท่ากับ 0" ⇒ ตอนอ่านผลแล้วแยกออกทันทีว่าโดนของจริงหรือโดนโดยบังเอิญ
- **Date Added:** 2026-09-28

### 🔀 ฟีเจอร์ที่มี **สวิตช์ปิดฉุกเฉิน** (คีย์ว่าง = ปิดทั้งระบบ) ต้องมี fixture "เปิดสวิตช์" — ไม่งั้นเทสต์ทั้งไฟล์กลายเป็นพิธีกรรม
- **Context/Problem:** `VAPID_PUBLIC_KEY=""` เป็นสวิตช์ปิด push โดยไม่ต้อง deploy (เจตนาดี) — แต่ `process_pending` / `get_status` **ออกประตูแรกนั้นก่อนถึงโค้ดที่ต้องการทดสอบ** ⇒ เทสต์ 5 ตัวแรก **ผ่านทั้งที่ไม่ได้ทดสอบอะไรเลย**
- **Root Cause:** ประตู "ปิดทั้งระบบ" อยู่ที่ **ต้น** ฟังก์ชัน ⇒ ทุกอย่างหลังจากนั้นกลายเป็นโค้ดตายในเทสต์ และเทสต์ที่ assert ผลลัพธ์ว่าง ๆ ก็ "ผ่าน" อย่างมีความสุข
- **Correct Pattern/Solution:** ใส่ `autouse` fixture ที่ตั้งค่าให้ฟีเจอร์ **เปิด** และรีเซ็ต cache ระดับโมดูลทั้งสองทาง:
  ```python
  @pytest.fixture(autouse=True)
  def vapid_configured(monkeypatch):
      monkeypatch.setattr(settings, "VAPID_PUBLIC_KEY", "test-public-key")
      monkeypatch.setattr(settings, "VAPID_PRIVATE_KEY", "test-private-key")
      push_service._reset_vapid_cache()          # ← ก่อน
      yield
      push_service._reset_vapid_cache()          # ← และหลัง (กันรั่วไปไฟล์ถัดไป)
  ```
  · ⚠️ **cache ระดับโมดูลต้องมีทาง reset สำหรับเทสต์เสมอ** (`_reset_vapid_cache()`) ไม่งั้น fixture ที่ตั้งค่าใหม่จะไม่มีผลเพราะค่าถูกแคชไว้จากเทสต์ก่อน
  · และต้องมีเทสต์ที่ **จงใจปิดสวิตช์** แยกต่างหาก (S10: `enabled=false` + `public_key=""`) เพื่อยืนยันว่าสวิตช์ยังทำงาน — ไม่ใช่หายไปเพราะ fixture เปิดไว้ตลอด
- **Date Added:** 2026-09-28

### 📉 ตัวนับสถานะที่รวม "จะลองใหม่" กับ "ยอมแพ้แล้ว" ไว้ด้วยกัน = **แดชบอร์ดเขียวทั้งที่ของถูกทิ้ง**
- **Context/Problem:** `process_pending` คืน `stats["retry"]` โดยนับจาก `len(retry_ids)` ก่อนแยกว่ามีแถวไหน **ลองครบเพดานแล้วและถูกปิดเป็น "จบ"** ⇒ แถวที่ push **หายถาวร** ถูกนับรวมในชื่อ "retry" ⇒ คนเฝ้าดูเห็น "กำลังลองใหม่" ทั้งที่ความจริงคือ "ไม่มีวันส่งแล้ว"
- **Root Cause:** ชื่อตัวนับเป็น *ความตั้งใจ* (จะ retry) แต่ค่าที่นับเป็น *สิ่งที่เกิดขึ้น* (ถูกจัดคิวหรือถูกทิ้ง) — สองอย่างนี้เท่ากัน **เฉพาะเมื่อยังไม่ถึงเพดาน**
- **Correct Pattern/Solution:** แยกตัวนับเป็นสองตัวที่ความหมายไม่ทับกัน และ **ให้ `_retry_later()` คืน `(rescheduled, exhausted)`** แทน `None`:
  ```python
  stats["retry"]   = rescheduled   # จะถูกยิงซ้ำจริง
  stats["dropped"] = exhausted     # ลองครบเพดานแล้ว — ของหายถาวร
  ```
  · หลักทั่วไป: ตัวนับสำหรับการเฝ้าระวังต้องตอบคำถาม *"มีอะไรเสียหายถาวรไหม"* ได้ในตัวมันเอง — ถ้าต้องไปไขโค้ดก่อนจึงรู้ว่าตัวเลขนั้นหมายถึงอะไร มันจะไม่มีใครดู
- **Date Added:** 2026-09-28

### 🖥 `beforeinstallprompt` ยิงบน **เดสก์ท็อป** ด้วย — "ติดตั้งได้" ไม่ได้แปลว่า "ควรชวน"
- **Context/Problem:** เจ้าของระบบสั่ง *"เปิดในคอม เบราเซอร์ในคอม ไม่ต้องขอ install มา เปิดผ่านเว็บก็โอเคแล้ว"* — แต่โค้ดเดิมชวนทั้งคอมและมือถือ · คอมเมนต์ในโค้ดเขียนว่า *"ไม่เดาจาก user agent — แสดงเฉพาะเมื่อเบราว์เซอร์ยิง `beforeinstallprompt` จริง"* ซึ่ง **ถูกต้องตามหลักแต่ตอบคำถามผิดข้อ**
- **Root Cause:** **สับสนสองคำถามที่คนละข้อ** — `beforeinstallprompt` ตอบว่า *"เครื่องนี้ติดตั้งได้ไหม"* (Chrome/Edge **เดสก์ท็อปก็ยิง** ไม่ใช่แค่ Android) แต่สิ่งที่ต้องตัดสินคือ *"ควรชวนไหม"* · และมันรบกวนกว่าที่คิดเพราะมี **สองทาง**: แบนเนอร์ของเรา **และ** `prompt()` ที่เรายิงเองตอนแตะแรก ⇒ ผู้ใช้แค่คลิกที่ไหนก็ได้ในเว็บ ก็ได้ dialog ติดตั้งของเบราว์เซอร์เด้งใส่ ทั้งที่ไม่ได้ขอ
- **Correct Pattern/Solution:** แยก "ความสามารถ" ออกจาก "การชวน" แล้ว **gate เฉพาะการชวน**:
  ```ts
  function detectTouchPrimary(): boolean {           // ไม่ใช้ UA — UA ปลอมได้ และ iPadOS รายงานเป็น Macintosh
    return window.matchMedia('(pointer: coarse)').matches   // แล็ปท็อปจอสัมผัสที่มีเมาส์เป็นตัวหลัก = fine (ถูกต้อง)
  }
  ```
  - gate ที่ `showInstallBanner` · `showIosHint` · `armAutoPrompt()` — **เท่านั้น**
  - ⛔ **ห้าม gate `canPromptInstall` / `installNow()`** — การ์ด "ติดตั้งแอป" ใน Profile คือ **ทางกลับที่เจ้าของสั่งไว้เอง** ("ใครจะกดโหลดก็ไปที่หน้าโปรไฟล์") ถ้าเผลอใส่เงื่อนไขมือถือไปด้วย จะกลายเป็น "ติดตั้งไม่ได้เลยในคอม" ซึ่งไม่ใช่สิ่งที่สั่ง ⇒ **มีเทสต์ล็อกเส้นทางนี้ไว้ต่างหาก**
  - ⚠️ `armAutoPrompt()` ต้องอ่านค่า **สด ๆ จาก `matchMedia`** ไม่ใช่จาก `ref` เพราะ handler นี้ผูกตอน *import* และอาจยิงก่อน `registerPwa()` จะได้อ่านค่า
- **กับดักในเทสต์ (เจอจริง):** stub `matchMedia` แบบเดิม `mockReturnValue({matches:false})` **ตอบค่าเดียวทุก query** ⇒ พอเพิ่มคำถาม `(pointer: coarse)` เข้าไป **ทุกเทสต์ในไฟล์กลายเป็น "เดสก์ท็อป" เงียบ ๆ** แล้วแบนเนอร์/การยิงอัตโนมัติไม่ทำงาน = เทสต์ล้มด้วยเหตุผลของการทดสอบเอง ไม่ใช่ของโค้ด ⇒ ต้อง stub ให้ **ตอบตามคำถาม** (`Record<query, boolean>`) และตั้งค่าตั้งต้น = มือถือ เพราะเทสต์ส่วนใหญ่ตรวจเส้นทางนั้น
- **พิสูจน์ว่ามีค่าจริง:** mutation 4 ตัว (ถอด gate ออกจาก `showInstallBanner` / `armAutoPrompt` / `showIosHint` · ใส่ gate ผิดทางที่ `canPromptInstall`) → **ถูกฆ่าครบทั้ง 4** · เทสต์ `pwa.spec.ts` 29 ผ่าน
- **Date Added:** 2026-09-28

### 🚨 คิว FIFO ที่มี **งานที่ทำไม่ได้ปนอยู่** จะท่วมจนของที่ทำได้หมดอายุ — ประตูต้องอยู่ตอน **เข้าคิว** ไม่ใช่ตอน **ออกคิว**
- **Context/Problem:** ผู้ใช้รายงานบน Android ว่า *"แจ้งเตือนแค่ครั้งแรก เมื่อกี้ แต่พอไปสักพัก ไม่แจ้งมาอีกแล้ว"* · วัดบน staging: `push_outbox` มี **3,239 แถว** แต่มีแค่ **9 แถว (0.28%)** ที่ผู้รับมีอุปกรณ์จริง (แถวที่เหลือมาจาก `notify_fanout` ที่ยิงทุกนักเรียน แต่มีแค่ 9 คนที่เคยกดเปิด push) — push ทั้งระบบ **หยุดให้บริการจริง** โดยที่ไม่มี error แม้แต่บรรทัดเดียว
- **Root Cause:** **การไหลของคิวถูกต้องทุกจุด แต่ปริมาณผิด** — worker หยิบตาม `ORDER BY id` (FIFO) ทีละ `PUSH_BATCH_SIZE=100` ⇒ แถวของคนที่มีอุปกรณ์จริงต้องรอคิวประมาณ **40 นาที** กว่าจะถึงหัวคิว · พอถึงหัวคิวมันก็ **เกิน `PUSH_MAX_AGE_MINUTES=15`** ⇒ ถูกทิ้งเป็น `stale` ทั้งหมด ⇒ ของจริงไม่เคยถูกส่งเลยแม้แต่ชิ้นเดียว และเพราะทุกอย่าง "สำเร็จ" (claim ได้ → mark processed) สถิติจึงดูปกติ
  · ⚠️ **นี่ไม่ใช่บั๊กของ retry/stale — ด่าน stale ทำงานถูกต้อง** มันคือสัญญาณว่าคิวมีของที่ *ทำไม่ได้* อยู่ 99.7%
- **Correct Pattern/Solution:** **ย้ายประตูไปไว้ตอน insert** — `migrations/019_push_outbox_requires_device.py` แก้ `push_outbox_enqueue()` ให้เช็คก่อน:
  ```sql
  SELECT EXISTS (SELECT 1 FROM push_subscriptions s WHERE s.user_id = NEW.user_id) INTO has_device;
  IF NOT has_device THEN RETURN NEW; END IF;     -- ไม่มีอุปกรณ์ = ไม่ต้องเข้าคิวเลย
  ```
  - **หลักทั่วไป:** outbox/คิวงานที่ "หยิบแล้วไม่มีอะไรให้ทำ" ต้องกรอง **ที่ทางเข้า** · การกรองที่ทางออกช้ากว่าเสมอ และในคิว FIFO มันไม่ได้แค่ช้า — มัน **ทำให้ของจริงอดตาย**
  - ⛔ **ห้าม backfill** ตอน migrate — คนที่เพิ่งเพิ่มอุปกรณ์ต้อง **ไม่ได้** push ย้อนหลัง (จะกลายเป็น push storm) ⇒ มีเทสต์ `T5c` ล็อกไว้
  - ✅ **in-app ยังต้องได้ notification ปกติ** — ประตูนี้กันแค่ *push* ไม่ใช่การแจ้งเตือน ⇒ `notifications` ยังเพิ่ม 1 แถวเหมือนเดิม (เทสต์ `T5b` assert ว่าตารางหนึ่งได้ 1 อีกตารางได้ 0)
  - ⚠️ `_give_device()` เป็น **ข้อกำหนดของเทสต์ทุกตัวที่หวัง outbox** ตั้งแต่ 019 เป็นต้นไป — เทสต์ที่ลืมจะได้ `0 / 0` **เพราะประตู ไม่ใช่เพราะ logic ที่กำลังตรวจ** (กับดักที่เขียนไว้หัวไฟล์ `test_push_outbox.py` แล้ว)
- **Date Added:** 2026-09-28

### ⏱ ARQ cron มี **lag ที่เสริมตัวเอง** — heartbeat ห่างเกินหน้าต่าง 1 วินาทีเมื่อไหร่ `next_run` จะตามนาฬิกาไม่ทันตลอดไป
- **Context/Problem:** `cron(process_push_outbox, second={0, 20, 40})` ออกแบบไว้ 20 วินาที · **วัดบน staging จริงได้ ~150 วินาที** และมีช่วง **เงียบสนิท 141 วินาที** · จุดที่ยิงได้หลุดกริด `:00/:20/:40` อย่างชัดเจน (= ร่องรอยที่ใช้ตรวจได้) · **ไม่มี error หรือ warning ใด ๆ** ทั้งที่ ARQ ยังทำงานปกติทุกอย่าง
- **Root Cause:** อ่านซอร์ส ARQ **0.28.0** ในอิมเมจจริง — `run_cron()` จะ enqueue รอบหนึ่งก็ต่อเมื่อ heartbeat ตกลงใน**หน้าต่าง 1 วินาที**ก่อนถึง `next_run` (`cron_delay = max(poll_delay_s, 0.5) * 2`) · และเมื่อยิงแล้วมัน **ไล่ `next_run` ไปได้ทีละรอบเท่านั้น — ไม่มี while-loop** ⇒ พอ heartbeat ห่างเกิน 1 วินาที (ซึ่งเกิดตอน worker ตื่นจาก sleep แล้วเจองาน) `next_run` จะตกหลังนาฬิกาจริง แล้ว **แต่ละ heartbeat ไล่ได้ 20 วิ แต่นาฬิกาเดิน 150 วิ ⇒ ห่างขึ้นเรื่อย ๆ ไม่มีวันตามทัน** (self-reinforcing lag)
  · ⇒ **cron ของ ARQ ไม่ใช่ตัวจับจังหวะที่เชื่อได้** สำหรับงานที่ "ผู้ใช้รอผล" — มันเหมาะกับงานวันละครั้ง/ชั่วโมงละครั้ง
- **Correct Pattern/Solution:** **อย่าใช้ cron เป็นตัวกำหนดอัตรา** — เพิ่มลูปของตัวเองในโปรเซส worker:
  ```python
  async def _delivery_loop(ctx):        # ตื่นทุก PUSH_TICK_SECONDS (5 วิ) แล้ว drain() จนเกลี้ยง
      while True:
          await asyncio.sleep(settings.PUSH_TICK_SECONDS)
          try: ...
          except asyncio.CancelledError: raise
          except Exception: logger.exception(...)   # ★ ต้องกว้างแบบนี้ — ลูปห้ามตาย
  ```
  - **cron ยังเก็บไว้ แต่เปลี่ยนบทบาทเป็น "ตาข่ายกันลูปตาย"** ไม่ใช่ตัวจับจังหวะ ⇒ ถ้าลูปในโปรเซสตาย push ก็ยังไม่หยุดสนิท
  - `shutdown()` ต้อง `task.cancel()` + **กลืน `CancelledError` ของตัวเอง** ไม่งั้น ARQ จะ log ว่า shutdown ล้มเหลวทั้งที่จบตามสั่ง
  - ⚠️ `_delivery_loop` รัน **ทุก replica** โดยเจตนา — ปลอดภัยเพราะ `_claim()` ใช้ `FOR UPDATE SKIP LOCKED` (ต่างจาก cron ที่ `unique=True` เป็น default ⇒ มีตัวเดียวทำงาน)
  - **บทเรียนเชิงวิธี:** อาการ "ช้า/กอง/หยุด" ที่ไม่มี error ต้อง **วัดจังหวะจริงจาก log แล้วเทียบกับกริดที่ออกแบบ** — กริด `:00/:20/:40` ที่หลุดคือหลักฐานที่ชี้ตรงไปที่ cron ทันที
- **Date Added:** 2026-09-28

### 🔇 ARQ worker **ไม่ได้เรียก `logging.basicConfig`** ⇒ `logger.info` ถูกทิ้งเงียบ ๆ ทั้งหมด (ตาบอดสนิทโดยไม่รู้ตัว)
- **Context/Problem:** บรรทัด log `📤 push[…]: claimed=… sent=… gone=… retry=… dropped=… skipped=… stale=…` ซึ่งเป็น **ที่เดียวในระบบ** ที่โชว์ว่ามีของถูก *ทิ้งถาวร* **ไม่เคยขึ้นเลยแม้แต่ครั้งเดียว** ตลอดทั้งรอบที่มีบั๊กคิวท่วม ⇒ ไม่มีใครเห็นปัญหาทั้งที่ระบบกำลังพัง
- **Root Cause:** `logging.basicConfig()` ถูกเรียกอยู่ **2 ที่เท่านั้น** คือ `main.py` และ `core/init_db.py` · **worker (`python -m arq workers.push_worker.WorkerSettings`) ไม่ได้ import ทั้งสองไฟล์** ⇒ root logger ไม่มี handler ⇒ Python ใช้ `logging.lastResort` ซึ่งปล่อย **เฉพาะ WARNING ขึ้นไป** ออก stderr และ **`logger.info` ถูกทิ้งโดยไม่มีคำเตือน**
  · ⇒ **ระดับ log ที่ตั้งไว้ในโค้ด (`level=INFO`) ไม่มีความหมายถ้าไม่มี handler** — และนี่คือกับดักที่ "แยกไม่ออกจากการที่ไม่มีอะไรเกิดขึ้นเลย"
- **Correct Pattern/Solution:** **worker ทุกตัวต้องประกาศ `logging.basicConfig` ของตัวเองที่หัวไฟล์** (พร้อมคอมเมนต์กันคนรุ่นหลังลบ):
  ```python
  logging.basicConfig(level=logging.INFO,
      format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
  ```
  - **หลักทั่วไป:** กระบวนการที่รันด้วย entrypoint คนละตัว (`main.py` / `arq` / cron script) **ไม่สืบทอด logging config กัน** — ต้องตั้งใหม่ทุกตัว
  - ⚠️ และบรรทัด log ที่รวม `stale`/`dropped`/`skipped` ไว้ **ห้ามตัดออก** แม้จะดูรก — มันคือบรรทัดเดียวที่ตอบคำถาม *"มีอะไรเสียหายถาวรไหม"* (ดูบทเรียนก่อนหน้าเรื่องตัวนับที่ไม่ควรแยกความหมาย)
  - **วิธีตรวจว่าตาบอดอยู่:** `docker service logs <svc> | grep -c '📤'` = 0 **ทั้งที่มีของไหลผ่าน** ⇒ ให้สงสัย logging ก่อนสงสัย logic
- **Date Added:** 2026-09-28

### 🪜 บันได `if/elif` ที่ **ยุบ 3 ทางเหลือ 2 ทาง** จะกลายเป็น "ทิ้งของเงียบ ๆ" — และตัวนับที่เป็น 0 ก็ไม่ต่างจาก "ไม่มีของเสีย"
- **Context/Problem:** ตอน refactor `push_service.process_pending` ผมเขียนตัวจำแนกผลลัพธ์เป็น
  ```python
  if cls == "ok":        ok_sub_ids.add(sub["id"])
  elif cls != "gone":    failed_sub_ids.add(sub["id"])     # ← 🚨 สาขา gone หายไปทั้งสาขา
  ```
  ⇒ `dead_sub_ids` **ว่างตลอดกาล** ⇒ `stats["gone"] = 0` ตลอดกาล ⇒ subscription ที่ได้ **404/410 ไม่เคยถูกลบ** ⇒ ระบบจะยิงไปหาปลายทางที่ตายแล้ว **ทุกครั้งที่มี notification ใหม่ ตลอดไป** — ไม่มีอาการให้เห็นเลยนอกจาก "เปลือง" เงียบ ๆ
- **Root Cause:** การเข้ารหัสแบบ *negative* (`cls != "gone"` = "ทุกอย่างที่ไม่ใช่ gone") **ดูเหมือนคลุมครบ** แต่ทำให้สาขาที่ต้อง *ทำอะไรบางอย่าง* หายไป · และเพราะ `stats["gone"] = 0` **เป็นค่าที่ถูกต้องของกรณีปกติ** (ยังไม่มีอุปกรณ์ตาย) ความผิดปกติจึงดูเหมือนความปกติ
- **Correct Pattern/Solution:** **เขียน 3 สาขาให้ครบเสมอ** และคอมเมนต์ว่าทำไมต้องมี:
  ```python
  if cls == "ok":        ok_sub_ids.add(sub["id"])
  elif cls == "gone":    dead_sub_ids.add(sub["id"])      # ☠️ ต้องเก็บไว้ "ลบ" ไม่ใช่แค่ปล่อยผ่าน
  else:                  failed_sub_ids.add(sub["id"])
  ```
  - **หลักทั่วไป:** ถ้ามีการกระทำ (side effect) ผูกกับ *แต่ละ* คลาส **ห้ามใช้การเข้ารหัสแบบ negative** — negative เหมาะกับ "ค่าตั้งต้นที่ไม่ต้องทำอะไร" เท่านั้น
  - ⭐ **เทสต์ `T9` จับได้ทันที** (`assert stats["gone"] == 1` แต่ได้ `0`) ⇒ นี่คือตัวอย่างจริงที่พิสูจน์ว่าชุดเทสต์คุมพฤติกรรม *และ* คุมตัวนับ — ถ้าไม่มีเทสต์ที่ assert ตัวนับ ตัวนับก็จะเป็น 0 ต่อไปโดยไม่มีใครรู้
- **Date Added:** 2026-09-28

### 🐘 asyncpg คืน `"char"` เป็น **`bytes` ไม่ใช่ `str`** — `pg_trigger.tgenabled` จึงเทียบกับ `'O'` ไม่ผ่าน
- **Context/Problem:** เทสต์ยืนยันว่า trigger ถูกเปิดใช้งานจริง ล้มด้วย `assert b'O' == 'O'` — ทั้งที่ค่าใน DB คือ `O` (enabled ปกติ) ถูกต้องแล้ว
- **Root Cause:** คอลัมน์ `pg_trigger.tgenabled` มีชนิดเป็น Postgres **`"char"`** (คนละตัวกับ `char(1)`) ซึ่ง **ไม่มี type mapper ใน asyncpg** ⇒ asyncpg คืนค่าดิบเป็น `bytes` ให้ตรง ๆ ⇒ เทียบกับ Python `str` ไม่มีทางเท่ากัน
  · ⇒ **ไม่ใช่ปัญหาเฉพาะ `tgenabled`** — คอลัมน์ชนิด `"char"` ตัวอื่นในระบบก็เป็นเหมือนกัน (เช่น `pg_class.relkind`)
- **Correct Pattern/Solution:** **cast ใน SQL เสมอ** เมื่ออ่านคอลัมน์ชนิด `"char"`:
  ```sql
  SELECT tgenabled::text FROM pg_trigger WHERE tgname = $1
  ```
  - **หลักทั่วไป:** ค่าที่ออกจาก catalog ของ Postgres ไม่ใช่ `str` ทุกตัว — ถ้า assert ด้วยสตริงแล้วได้ `b'…'` **อย่าไป `.decode()` ฝั่ง Python ให้แก้ที่ SQL** (จะได้ type ที่ชัดเจนและใช้ต่อได้ทุกที่)
- **Date Added:** 2026-09-28

### 🧪 เทสต์ที่ **ถอยสคีมากลับ** (DROP แล้ว `upgrade()`) ต้อง **คืนสคีมาเป็นเวอร์ชันล่าสุดก่อนจบ** — ไม่งั้นเทสต์ไฟล์ถัดไปพังด้วยเหตุผลผิด
- **Context/Problem:** เทสต์ mutation ของ migration (พิสูจน์ว่าประตูใหม่มีผลจริง) ต้อง `DROP` ของที่ migration สร้าง **แล้วรันซ้ำ** ⇒ ระหว่างนั้น DB อยู่ในสภาพ "เวอร์ชันเก่า" · แต่ `conftest` สร้าง DB **ครั้งเดียวต่อ session** ⇒ ถ้าเทสต์นั้นคืนสคีมาไม่ครบ **เทสต์ไฟล์อื่นที่รันทีหลังจะเจอสคีมาเก่า** แล้วล้มด้วยข้อความที่ชี้ผิดที่ (เช่น outbox ได้ 0 แถวทั้งที่ควรได้ 1) ⇒ หาสาเหตุยากมากเพราะไฟล์ที่ล้มไม่ใช่ไฟล์ที่ก่อ
- **Root Cause:** เทสต์ถือว่าตัวเอง "ในกล่องปิด" แต่ DB เป็น **resource ที่ใช้ร่วมกันทั้ง session** · และ `conftest.py` **กลืน exception ของ `init_db` แล้ว print เฉย ๆ** ⇒ ความพังของการตั้งสคีมาไม่โผล่เป็น error ที่จุดนั้น
- **Correct Pattern/Solution:**
  - เทสต์ mutation ต้อง **`importlib.import_module("migrations.NNN_…")` แล้ว `await mod.upgrade(conn)` ปิดท้าย** ให้สคีมากลับเป็นล่าสุดเสมอ (ไม่ใช่พึ่ง `init_db` รอบหน้า ซึ่งจะไม่มารัน)
  - ไฟล์ที่ **`DROP` ตารางจริงต้องอยู่ท้ายไฟล์** และ **ห้าม assert ผลข้ามไฟล์**
  - ⚠️ ถ้า migration ใหม่ "ห่อ" พฤติกรรมของ migration เก่า (แบบ 019 ที่เปลี่ยน trigger ของ 018) — เทสต์ของ 018 **ต้อง `upgrade()` 019 ซ้ำก่อน assert** และ **ต้อง `_give_device()`** ไม่งั้นเทสต์เก่าจะล้มทั้งที่โค้ดเก่าถูก
- **Date Added:** 2026-09-28

### 🚫 `docker exec -i` **กลืนสคริปต์ที่ส่งให้ `bash -s` ทาง stdin** — สคริปต์หยุดกลางคันเงียบ ๆ exit code 0
- **Context/Problem:** รันสคริปต์ตรวจ DB บน production VPS ด้วย `docker exec -i … bash -s <<'EOF'` ⇒ สคริปต์ **หยุดที่บรรทัดนั้น** โดยไม่มี error และ **exit code เป็น 0** ⇒ เกือบสรุปว่า "ตรวจผ่าน"
- **Root Cause:** `-i` ต่อ stdin ของ container **เข้ากับ stdin ที่ `bash` กำลังอ่านสคริปต์อยู่** ⇒ docker ตัวหน้าแย่งไบต์ที่เหลือของสคริปต์ไป ⇒ bash เห็นสคริปต์จบ prematurely
- **Correct Pattern/Solution:**
  - **ห้ามใส่ `-i` กับ `docker exec` ในสคริปต์ที่ตัวเองมาทาง stdin** — `psql -c` / `python -c` ไม่ต้องใช้ stdin อยู่แล้ว
  - ทางที่แน่นอนกว่า: `ssh host 'cat > /tmp/x.sh && bash /tmp/x.sh' < local.sh` — bash อ่านจาก **ไฟล์** ไม่ใช่ stdin
  - **ตระกูลเดียวกับบทเรียน fish + `bash -c`:** *อะไรก็ตามที่แย่ง stdin ของสคริปต์ จะพังเงียบ* ⇒ **สคริปต์ที่ครอบหลายบรรทัดต้องมาจากไฟล์ ไม่ใช่ท่อ**
- **Date Added:** 2026-09-28

### 🔍 `docker ps --filter name=A --filter name=B` เป็น **OR ไม่ใช่ AND** (filter คีย์เดียวกันจะ OR กันเอง)
- **Context/Problem:** เขียน `docker ps --filter name=pirivoice_staging --filter name=db` หวังจะได้ container ของ DB ⇒ ได้ **backend** มาแทน (เพราะชื่อมี `pirivoice_staging` อยู่ในตัว) ⇒ `docker exec … psql` ล้มด้วย `exec: "psql": executable file not found in $PATH` ซึ่งชี้ผิดที่ (ชวนให้คิดว่า image ไม่มี psql)
- **Root Cause:** `docker ps --filter` รวมค่าของ **คีย์เดียวกัน** ด้วย **OR** (คีย์ต่างกันจึงเป็น AND) — ต่างจากสัญชาตญาณว่า "ใส่หลายอัน = แคบลง"
- **Correct Pattern/Solution:** **ระบุชื่อ container ให้เต็มบรรทัดเดียว** อย่าอาศัยการ AND filter
  ```bash
  docker ps --filter name=pirivoice_staging_infra_db --format '{{.Names}}'
  ```
  - และเมื่อ `docker exec` บอกว่า *ไม่พบ executable* ให้ **สงสัยว่า exec เข้า container ผิดตัวก่อน** ว่าสงสัย image
- **Date Added:** 2026-09-28

### 🚫 ด่านตรวจที่แยกไม่ออกระหว่าง "**ไม่มีบรรทัด**" กับ "**มีบรรทัดแต่ว่าง**" = ด่านที่หลอกตัวเอง
- **Context/Problem:** สคริปต์ติดตั้งคีย์ลง `.env` เขียนด่านตรวจว่า
  ```bash
  line=$(grep "^$k=" .env); val=${line#*=}; echo "len=${#val}"
  ```
  ได้ `len=0` ⇒ **สรุปผิดว่า ".env มีบรรทัด `VAPID_*` ว่างรออยู่"** · ของจริงคือ **ไม่มีบรรทัดนั้นเลย** (`.env` มาจาก `.env.example` รุ่นก่อนที่มีฟีเจอร์นี้) ⇒ `awk` ไม่มีอะไรให้แทนที่ ⇒ **เขียนไม่ติด** แต่ **จำนวนบรรทัดเท่าเดิม จึงผ่านด่านที่ตั้งไว้** ⇒ เกือบรายงานว่า "ติดตั้งสำเร็จ"
- **Root Cause:** `grep` ที่ไม่เจออะไรให้ **สตริงว่าง** ซึ่งแยกจาก "เจอแต่ค่าว่าง" ไม่ได้ · และด่านที่ตั้งไว้ตรวจ **"จำนวนบรรทัดไม่เปลี่ยน"** ซึ่ง **ผิดโดยตัวมันเอง** — ไฟล์ที่ต่อท้ายถูกต้องจะ *เพิ่ม* บรรทัด
- **Correct Pattern/Solution:**
  - **นับ ไม่ใช่ตีความ:** `grep -c '^KEY=' .env` (ได้ `0` = ไม่มีบรรทัด) แทน `${#val}`
  - **ด่านต้องตรวจ "ค่าที่ควรเป็น" ไม่ใช่ "รูปร่างไฟล์":** เทียบค่าที่ดึงได้ (`pub/prv/sub`) กับค่าที่ตั้งใจเขียน **ตรงทุกตัว** · และใช้ `AFTER >= BEFORE` ไม่ใช่ `==`
  - **อย่าทับของเดิมก่อนด่านผ่าน** — เขียน `/tmp/env.new` ให้ครบ แล้วค่อย `cat > .env` ทีหลัง ⇒ ถ้าด่านไม่ผ่าน ไฟล์เดิมยังอยู่
  - **หลักทั่วไป:** ด่านที่ผ่านได้ทั้งตอนสำเร็จและตอนล้มเหลว **แย่กว่าไม่มีด่าน** เพราะมันสร้างความมั่นใจปลอม — ต้องออกแบบให้ "ทางที่ผิด" ทำคะแนนไม่ได้เลย
- **Date Added:** 2026-09-28

### 🔐 `.env` ที่มี private key ต้องเป็น `600` — และสคริปต์ที่ "คงสิทธิ์เดิม" โดยไม่ดูว่าเดิมคืออะไร จะคงค่าที่ไม่ปลอดภัยไว้
- **Context/Problem:** พบว่า `.env` บน VPS เป็น **`664`** (group/other อ่านได้) มาตั้งแต่แรก และมี `POSTGRES_PASSWORD` + `JWT_SECRET` อยู่แล้ว · พอเพิ่ม `VAPID_PRIVATE_KEY` เข้าไป ความเสียหายเพิ่มขึ้นอีกชั้น (คีย์นั้นเอาไปปลอม push แทนเซิร์ฟเวอร์ได้)
- **Root Cause:** `.env` ถูกสร้างด้วย `cp .env.example .env` ⇒ ได้ `umask` ของ shell ตอนนั้น (มัก 644/664) · และไม่มีใครตรวจ เพราะ *"ก็มันเป็นไฟล์ที่ gitignore ไว้แล้ว"* — **gitignore กันการ commit ไม่ได้กันการอ่านบนเครื่อง**
- **Correct Pattern/Solution:**
  - หลังเขียน `.env`: `chmod 600 .env` · **ตรวจด้วย `stat -c '%a'`** ไม่ใช่ดูด้วยตา
  - สคริปต์ที่ "รักษาสิทธิ์เดิม" ต้อง **ตรวจก่อนว่าเดิมคืออะไร** แล้ว **ปรับให้เข้มขึ้น** ไม่ใช่คัดลอกค่ามาเฉย ๆ
  - ⚠️ **private key ห้ามผ่าน command line** (`docker service update --env-add` จะโผล่ใน `ps`/ประวัติ) — ให้แก้ `.env` แล้ว redeploy ผ่าน `./pull_all.sh` ที่อ่านไฟล์เอง
- **Date Added:** 2026-09-28

### ⚠️ `env_file: .env` ถูกอ่านตอน **`docker stack deploy`** ไม่ใช่ตอน container start — แก้ `.env` แล้วไม่ redeploy = ไม่มีอะไรเปลี่ยน
- **Context/Problem:** แก้ `.env` ใส่คีย์ แล้ว `docker service update --force` / รอ container restart ⇒ ในคอนเทนเนอร์ยังเห็นค่าเก่า (ว่าง) และดูเหมือนโค้ดอ่าน `.env` ไม่ถูก
- **Root Cause:** Docker **อ่าน `env_file` ฝั่ง client ตอน deploy** แล้วฝังค่าที่อ่านได้ลงใน spec ของ service ⇒ ตัวไฟล์บนดิสก์ไม่ถูกอ่านซ้ำเมื่อ container สตาร์ท ⇒ เป็น **snapshot ไม่ใช่ reference** (ต่างจาก bind mount)
- **Correct Pattern/Solution:**
  - **แก้ `.env` แล้วต้อง redeploy เสมอ** (`./pull_all.sh` ซึ่งอ่าน `.env` ให้เอง)
  - **ตรวจให้ถูกจุด — ดูค่าที่ *คอนเทนเนอร์* เห็น ไม่ใช่ค่าที่ *ไฟล์*:** `docker exec … printenv KEY` หรืออ่านผ่าน `settings` ในโปรเซส
  - **หลักทั่วไป:** ตัวแปรสภาพแวดล้อมใน Swarm เป็น *ข้อมูลที่ฝังตอน deploy* — ทุกครั้งที่สงสัยว่าค่าไม่ถึง ให้เริ่มจากคำถาม *"deploy รอบล่าสุดตอนไหน เทียบกับตอนที่แก้ไฟล์"*
- **Date Added:** 2026-09-28

### 📱 `Urgency: high` (RFC 8030 §5.3) — ไม่ใส่ = Android Doze หน่วง push ได้เป็นนาที
- **Context/Problem:** ผู้ใช้บ่นว่า *"มันแจ้งเตือนมาละ แต่มันแจ้งเตือนช้าไปหน่อย"* แม้ฝั่งเซิร์ฟเวอร์จะส่งทันที
- **Root Cause:** push ที่ไม่มีหัวข้อ `Urgency` ถูกจัดเป็น **normal** ⇒ เมื่อมือถือเข้า **Doze mode** (จอดับ นิ่ง ไม่ได้ชาร์จสักพัก) ระบบจะ **รวม push ไว้ส่งตอนเครื่องตื่น** ⇒ ดีเลย์ได้หลายนาทีถึงเป็นชั่วโมง · และอาการนี้ **แยกไม่ออกจาก "เซิร์ฟเวอร์ส่งช้า"** ถ้าดูแค่ log ฝั่งเรา (log จะบอกว่าส่งสำเร็จแล้ว)
- **Root Cause:** push ที่ไม่มีหัวข้อ `Urgency` ถูกจัดเป็น **normal** ⇒ เมื่อมือถือเข้า **Doze mode** (จอดับ นิ่ง ไม่ชาร์จสักพัก) ระบบจะ **รวม push ไว้ส่งตอนเครื่องตื่น** ⇒ ดีเลย์ได้หลายนาทีถึงเป็นชั่วโมง · และอาการนี้ **แยกไม่ออกจาก "เซิร์ฟเวอร์ส่งช้า"** ถ้าดูแค่ log ฝั่งเรา (log จะบอกว่าส่งสำเร็จแล้ว)
  · ⇒ **นี่คือสาเหตุที่การวัด latency ฝั่งเซิร์ฟเวอร์อย่างเดียวสรุปผิด** — ต้องแยก *"ส่งออกแล้ว"* ออกจาก *"ถึงมือแล้ว"*
- **Correct Pattern/Solution:** ใส่หัวข้อ `Urgency` ทุกครั้งที่ส่ง push ของการแจ้งเตือน (ไม่ใช่งาน batch):
  ```python
  headers["Urgency"] = "high"      # RFC 8030 §5.3 — normal | low | very-low
  ```
  - ⚠️ **`high` ไม่ได้แปลว่า bypass Doze** — Android ยังคุมด้วยช่องทาง FCM ของตัวเอง · `high` แค่บอกว่าอย่ารวมมันเข้าคิวตอนตื่น ⇒ **ต้องบอกผู้ใช้ว่ามันช่วยได้มากแต่ไม่รับประกันว่า "ทันที"** (มีพื้นทางกายภาพของ FCM/APNs)
  - **หลักทั่วไป:** มาตรฐาน HTTP สำหรับ push มีช่องให้ผู้ส่ง *จัดชั้นความสำคัญ* — ถ้าไม่ใส่ ระบบจะเดา (และเดาผิดในทางที่ผู้ใช้เจ็บ)

### 📡 `TestClient` ทดสอบ SSE ที่เป็น stream ไม่มีวันจบ **ไม่ได้** — และอาการคือ *ค้าง* ไม่ใช่ *ช้า*
- **Context/Problem:** เขียนเทสต์ `GET /api/notifications/stream` (SSE ที่วน `queue.get()` ตลอดไป) ด้วย `client.stream(...)` ตามธรรมเนียมของโปรเจค ⇒ **ค้างไม่จบ** ไม่มี error ไม่มี timeout ของ pytest · อาการเตือนสัญชาตญาณไปทาง "ช้า/ต้องรอนาน" ทั้งที่ความจริงคือ **deadlock**
- **Root Cause:** `starlette/testclient.py` ทำงานแบบนี้
  ```python
  response_complete = portal.call(anyio.Event)
  portal.call(self.app, scope, receive, send)   # ← บล็อกจนกว่า ASGI app จะ "return"
  ```
  body ถูกสะสมใน `io.BytesIO` แล้วปล่อยออก **หลัง** `more_body=False` เท่านั้น ⇒ generator ที่วนไม่จบ = ไม่มีวัน return = `__enter__` ไม่มีวันคืนค่า · **httpx `ASGITransport` มีกับดักเดียวกันเป๊ะ** (`body_parts.append(body)` แล้ว `await self.app(...)`) ⇒ client มาตรฐาน **ทั้งสองตัว** ใช้กับ SSE ไม่ได้
  · **วิธีแยก "ค้าง" จาก "ช้า":** ดู `wchan` ของทุก thread ใน `/proc/<pid>/task/*/wchan` — ถ้าเป็น `futex_wait_queue` ทั้งหมด **และ** `cpu_ticks` ไม่ขยับเลยในช่วงหลายวินาที = ค้าง (ช้าจริง cpu ต้องขยับบ้าง)
- **Correct Pattern/Solution:** **ขับ ASGI app ตรง ๆ** ด้วย scope/send/receive ที่เราสร้างเอง — รัน `app(...)` เป็น task แล้วอ่าน message จาก `asyncio.Queue` ทีละก้อน
  · **จำลอง disconnect ด้วย `{"type": "http.disconnect"}`** — นี่คือ **เส้นทางจริงของ production** ผ่าน `listen_for_disconnect` ของ Starlette ⇒ task group ถูก cancel ⇒ `async for` ใน body iterator ถูก cancel ⇒ `finally` ของ async generator ทำงานแน่นอน (ใช้พิสูจน์ว่า `hub.unsubscribe()` ถูกเรียกจริงตอน client หาย)
  · ต้องมี fixture ที่ยัด `db_pool` ของเทสต์เข้า `app.state.db_pool` (เท่ากับที่ lifespan ทำ) เพราะ `get_db_pool` คือ `return request.app.state.db_pool`
  · เก็บเป็น `_SseSession` + context manager `open_stream()` ที่ `aclose()` แล้วรายงาน `closed_gracefully` ⇒ เทสต์ SSE อ่าน frame ได้แบบ deterministic ทีละ frame
- **Date Added:** 2026-09-28

### 📡 ASGI ส่ง `status` **ก่อน** `body` เสมอ — รู้ status แล้วไม่ได้แปลว่าอ่าน body ได้
- **Context/Problem:** เทสต์ที่รอ 503 แล้ว `json.loads(s.body_text)` ล้มด้วย `JSONDecodeError: Expecting value: line 1 column 1 (char 0)` — ทั้งที่ status ถูกต้องและ body มีจริง
- **Root Cause:** โปรโตคอล ASGI แยกสอง message: `http.response.start` (มี `status`) **แล้ว** `http.response.body` (มี payload) · ตัวรอของเทสต์หยุดทันทีที่ `status is not None` ⇒ อ่าน body ก่อนที่มันจะมาถึง ⇒ ได้สตริงว่าง
  · อาการหลอกมากเพราะ **status ถูกต้อง** ⇒ ชวนไปหาที่ parser/ที่ router ทั้งที่ปัญหาอยู่ที่ "อ่านเร็วเกินไป 1 message"
- **Correct Pattern/Solution:** ต้องมีธงแยก **`body_complete`** ตั้งจาก `not message.get("more_body", False)` แล้วมีเมธอด `read_body(timeout)` ที่รอธงนั้น — **ห้ามใช้ `status is not None` เป็นเงื่อนไข "พร้อมอ่าน"**
  ```python
  if message["type"] == "http.response.start":
      self.status = message["status"]; return
  chunk = message.get("body", b"")
  if not message.get("more_body", False):
      self.body_complete = True     # ← เงื่อนไขที่ถูก
  ```
- **Date Added:** 2026-09-28

### 🧪 mutation ที่ "ไม่ระเบิด" อาจเป็นเพราะมัน**ไม่ทำงานเลย** ไม่ใช่เพราะเทสต์ไม่มีฟัน
- **Context/Problem:** พิสูจน์ว่าเทสต์หัวใจ (`test_D2_rolled_back_transaction_emits_nothing`) มีฟันจริงด้วยการใส่ mutant ให้ publish ก่อน commit ⇒ **เทสต์ยังผ่าน** ⇒ เกือบสรุปว่า "เทสต์นี้ไร้ฟัน ต้องเขียนใหม่" · ที่จริง **mutant เองต่างหากที่ไม่ได้ทำงาน**
- **Root Cause:** mutant เปิด connection แยกด้วย `settings.DATABASE_URL` — แต่ `conftest.test_db_url` **คืนค่า `DATABASE_URL` เดิมก่อน `yield`**:
  ```python
  settings.DATABASE_URL = new_db_url      # สลับแค่ตอนรัน init_db
  ...
  finally:
      settings.DATABASE_URL = original_db_url   # ← คืนค่า "ก่อน" yield
  yield new_db_url
  ```
  ⇒ **ในตัวเทสต์ `settings.DATABASE_URL` ชี้ฐานข้อมูลเดิม (`test_piri_db`) ไม่ใช่ `test_db_<hex>` ที่ `db_pool` และ listener ใช้** · และ **Postgres NOTIFY แยกตามฐานข้อมูล** ⇒ สัญญาณของ mutant ไปลงที่ที่ไม่มีใครฟัง ⇒ เทสต์ผ่านอย่างถูกต้อง
  · หลักฐานที่ชี้ขาด: listener ได้ `['{"user_id" : 1}']` **ตัวเดียว** และมี **ช่องว่างหน้า `:`** (ฝีมือ `json_build_object` ของ trigger) ไม่ใช่ `{"user_id": 1}` ของ mutant
- **Correct Pattern/Solution:** ก่อนตีความผล mutation **ต้องพิสูจน์ว่า mutant ทำงานจริง** — ไม่ใช่แค่ "แทรกโค้ดติด":
  · ดึง DSN จาก connection ของ caller เอง อย่าใช้ `settings`: `st = conn.get_settings()` แล้วประกอบ `postgresql://{st.user}:{st.password}@{st.host}:{st.port}/{st.database}` (ทำงานได้ทั้ง mutant และเทสต์ที่ต้องเปิด connection ที่สอง — **เป็นข้อเท็จจริงที่ต้องรู้ก่อนเขียนเทสต์ใด ๆ ที่แตะ connection นอก `db_pool`**)
  · ตีความ **"mutant ผ่าน" ให้เป็นข้อสงสัยต่อ mutant ก่อนเสมอ** แล้วหาหลักฐานเชิงประจักษ์ (print ค่าที่ listener ได้จริง) ก่อนจะไปแก้เทสต์
  · **เทสต์เดียวกันนี้ พอ mutant ชี้ฐานข้อมูลถูกตัว → ล้มจริง** ⇒ ฟันมีอยู่ ของเสียคือ mutant
- **Date Added:** 2026-09-28

### ✅ `vitest` เขียวทั้งชุด **แต่ build พัง** — ด่านต้องมี `type-check` + `lint` ไม่ใช่แค่ test runner
- **Context/Problem:** เทสต์ SSE ใหม่ผ่าน `vitest` **145/145** ⇒ เกือบ commit · แต่ `npm run type-check` ล้ม **4 error** และ `npm run lint` ล้ม **4 error** ⇒ และเพราะ `npm run build` = `type-check + vite build` ⇒ **build ของจริงพัง** (ขึ้น staging ไม่ได้)
- **Root Cause:** **`vitest` ไม่ได้ type-check** — มัน transform แล้วรันเลย (esbuild ตัด type ทิ้ง) ⇒ โค้ดที่ type ผิดแต่ runtime ถูก จะผ่าน `vitest` 100% · งานนี้มี 2 กับดักพร้อมกัน: (ก) payload ที่ขาด field ตาม type ที่ประกาศ (ข) `vi.fn()` ที่ไม่ระบุ type parameter
- **Correct Pattern/Solution:** รัน **ครบทั้งสาม** ก่อน commit เสมอ — `npm run type-check && npm run lint && npm run test:unit` (คำสั่งใน §9 ของแผนเขียนไว้ถูกอยู่แล้ว; ที่พลาดคือรันไม่ครบ)
  · ⚠️ **`vi.fn()` เปล่า ๆ คือรูรั่วชนิดเดียวกับ `any`** — mock ที่ไม่ระบุ type จะรับ `mockResolvedValue(...)` อะไรก็ได้ ⇒ ใส่ type จริง (`vi.fn<() => Promise<UnreadCounts>>()`) แล้ว "การโกหก" จะกลายเป็น compile error ทันที · และ **`vi.hoisted` อ้างได้แค่ type** (ถูก erase ตอน compile จึงไม่ชน hoisting)
- **Date Added:** 2026-09-28

### 🔒 อย่า **ผ่อน type** ให้เทสต์คอมไพล์ผ่าน — จงแก้ข้อมูลในเทสต์
- **Context/Problem:** `const counts: UnreadCounts = { counts: { board: 2 }, total: 2 }` ไม่ผ่าน type เพราะ `UnreadCounts.counts` เป็น `Record<NotificationGroup, number>` **เต็มรูป** (ต้องมี 4 กลุ่ม) · ทางที่เร็วที่สุดคือเปลี่ยน type เป็น `Partial<Record<...>>`
- **Root Cause:** type เต็มรูปนั้น **เป็นความจริงของสัญญาณ (contract) ไม่ใช่ความเข้มงวดเกินเหตุ** — `notification_service.get_unread_counts` **zero-fill ทุกกลุ่มเสมอ** (`counts.setdefault(g, 0)` วนทุก `GROUP_TYPES`) ⇒ payload ที่ขาดกลุ่มคือสิ่งที่ server **ไม่มีวันส่ง** · ถ้าผ่อน type บั๊กจริงอย่าง *"อ่าน `counts.board` ทั้งที่ server ไม่ได้ส่ง `board` มา"* จะหลุดผ่านเทสต์ไป production ⇒ **การผ่อน type เพื่อให้เทสต์ผ่าน = ปิดด่านที่เพิ่งสร้าง**
- **Correct Pattern/Solution:** เทสต์ต้องสร้าง payload ให้ **ครบเหมือนของจริง** — เขียน helper ที่ zero-fill:
  ```ts
  function countsOf(over: Partial<Record<NotificationGroup, number>> = {}): UnreadCounts {
    const counts: Record<NotificationGroup, number> = {
      issue_mine: 0, issue_received: 0, board: 0, report: 0, ...over,
    }
    return { counts, total: Object.values(counts).reduce((a, b) => a + b, 0) }
  }
  ```
  · **เขียนชื่อกลุ่มตรง ๆ ที่นี่ได้** (ต่างจากโค้ด production ที่ `types/notification.ts` ห้ามประกาศซ้ำ) เพราะ TypeScript **บังคับ** ให้ตรง: เพิ่มกลุ่มใหม่ใน `NotificationGroup` แล้วบรรทัดนี้ compile ไม่ผ่านทันที ⇒ drift เกิดไม่ได้
  · และ assert **ทั้งก้อน** (`toEqual(snapshot.counts)`) ไม่ใช่แค่กลุ่มที่มีค่า — ยืนยันด้วยว่ากลุ่มที่เป็น 0 ไม่ถูกตัดทิ้ง (ถ้าถูกตัด ตัวเลขบนเมนูจะหายไปเฉย ๆ)
  · หลักทั่วไป: **type ที่ "ดูกวนใจ" ในเทสต์มักกำลังบอกความจริงอยู่ — ฟังมัน**
- **Date Added:** 2026-09-28

### 🚨 บั๊กที่อยู่ใน **สาขา error** เท่านั้น จะรอดจากเทสต์ happy-path ทั้งชุด — ต้องมีเทสต์ที่ **เดินเข้าไปในสาขานั้น**
- **Context/Problem:** `NotificationHub._supervise()` เรียก `await self._sleep_or_stop(lost, delay)` (2 arg) แต่เมธอดถูกเขียนเป็น `async def _sleep_or_stop(self, seconds: float)` (1 arg) ⇒ **`TypeError` ทุกครั้งที่ต่อ LISTEN ไม่สำเร็จ** ⇒ supervisor ตายตั้งแต่ reconnect รอบแรก ⇒ `badge` กลับไปเป็น poll 30 วิ **ตลอดกาลโดยที่ทุกอย่างดูปกติ** — ซึ่งคือความล้มเหลวแบบเงียบชนิดเดียวกับที่โมดูลนี้ถูกสร้างขึ้นมาป้องกันเป๊ะ ๆ
- **Root Cause:** **ไม่มีเทสต์ตัวใดเคยพาโค้ดเข้าไปในสาขา `except` ของ `_open_conn()` เลย** — เทสต์ H1–H8 และ D*/E* ทั้งหมดใช้ DSN ที่ต่อติด (หรือ inject connection ที่สำเร็จ) ⇒ บรรทัดนั้นไม่เคยถูก execute ⇒ 494 เทสต์ผ่านหมดทั้งที่โค้ดมี `TypeError` รออยู่ · และ **`stop()` ทำ `await self._supervisor`** ⇒ ขยะของ task ที่ตายแล้วจะ re-raise ออกมาทำให้ **shutdown ของ lifespan ล้ม** ด้วย (อาการที่สองที่ห่างจากสาเหตุโดยสิ้นเชิง)
- **Correct Pattern/Solution:** เขียนเทสต์ที่ **บังคับให้สาขา error ทำงานจริง** — `test_H9_start_never_raises_on_bad_dsn` ใช้ DSN ที่ชี้ไปพอร์ตปิด (`127.0.0.1:1`) แล้ว `await asyncio.sleep(0.5)` ⇒ mutation คือ "โค้ดเดิม" และมัน **FAILED → ผ่านหลังแก้** (พิสูจน์แล้ว ไม่ใช่การคาดเดา)
  · **สัญญาณเตือนที่ควรสังเกต:** ถ้าเทสต์ทุกตัวของโมดูลหนึ่งต้อง "เตรียมของให้สำเร็จ" ก่อนเสมอ ⇒ สาขาล้มเหลวของโมดูลนั้น **ยังไม่ถูกทดสอบเลย** ให้เพิ่มเทสต์ที่จงใจทำให้ล้ม
  · **วิธีแก้ signature:** รับ `lost: asyncio.Event` เป็น **argument** ไม่ใช่ไปอ่าน `self._conn_lost` ซ้ำเอง — ตามเหตุผลที่ `_supervise()` เขียนกำกับไว้เองว่า *"ต้องใช้ `lost` ให้ครบทุกจุด"* เพราะตัวแปรที่ `assert` ผ่านมาแล้วเท่านั้นที่ type checker รับประกันให้ (อ่าน attribute ซ้ำ = narrowing หายทั้งที่ยังต้องใช้)
- **Date Added:** 2026-09-28

### 🛡️ "การ์ดที่เฝ้าความล้มเหลวแบบเงียบ" **ต้องไม่ตายเงียบเอง** — ใส่ done-callback ให้ task ที่เฝ้า
- **Context/Problem:** supervisor ของ notification stream เป็น task เดียวที่ทั้งโมดูลพึ่งพา · ถ้ามันตายด้วย exception ที่ไม่คาดคิด (แบบข้อข้างบน) จะไม่มีร่องรอยอะไรเลย — ไม่มี error, ไม่มี log, badge แค่กลับไปช้า 30 วิ ⇒ ผู้ใช้รู้สึกว่า *"ต้องรีเฟรช"* อีกครั้ง และคนดูแลระบบไม่มีทางรู้ว่ามีอะไรพัง
- **Root Cause:** task ที่ไม่ได้ถูก `await` จะ **กลืน exception ไว้เงียบ ๆ** (asyncio เก็บไว้ที่ `task.exception()` และ GC ทิ้ง · ได้แค่ warning "Task exception was never retrieved" ที่มักโผล่ตอนปิดโปรเซส ซึ่งสายเกินไป) ⇒ `create_task()` เปล่า ๆ **ไม่ใช่** การเฝ้าที่ปลอดภัย
- **Correct Pattern/Solution:** `self._supervisor.add_done_callback(self._on_supervisor_done)` โดย callback แยก **"ตายตามคำสั่ง"** ออกจาก **"ตายเอง"**:
  ```python
  @staticmethod
  def _on_supervisor_done(task: "asyncio.Task[None]") -> None:
      if task.cancelled():
          return                      # ทางปกติตอน shutdown — ไม่ต้องรายงาน
      exc = task.exception()
      if exc is not None:
          logger.error("… supervisor ตายกลางทาง — badge จะกลับไปเป็น 30 วิ …", exc_info=exc)
  ```
  · `logger.error` ไม่ใช่ `warning` — ระหว่างที่ supervisor ตาย badge จะ **ไม่** ทันที ⇒ "ต้องรู้" ไม่ใช่ "ต้องสงสัย"
  · และ `stop()` ต้องทน supervisor ที่ตายไปก่อนแล้ว: `except asyncio.CancelledError: pass` **แล้วต่อด้วย** `except Exception: logger.debug(...)` ⇒ อย่าให้ขยะของ task ที่ตายไปแล้วไปทำให้ **shutdown ของ lifespan ล้ม** (หลักเดียวกับ `_close_conn()`: ปิดไม่สำเร็จก็ช่างมัน)
- **Date Added:** 2026-09-28

### 🚨 `asyncio.gather(return_exceptions=True)` **ทำกุญแจของงานหาย** — exception ที่กลืนแล้ว "จดว่า retry" แต่ไม่มีเจ้าของ = แถวค้างถาวร
- **Context/Problem:** วัดบน staging หลัง deploy A3 แล้วเจออาการที่ **ไม่มีเทสต์ตัวใดจับได้และผู้ใช้ยังไม่ทันเห็น**:
  ```
  PUSH        - ERROR - ❌ sender โยน exception
                        binascii.Error: Invalid base64-encoded string: number of
                        data characters (1) cannot be 1 more than a multiple of 4
  PUSH_WORKER - INFO  - 📤 push[loop]: claimed=1 sent=0 gone=0 retry=0 dropped=0 skipped=0 stale=0
  ```
  ⇒ `claimed=1` แต่ **ตัวนับทุกตัวเป็น 0** ⇒ แถวนั้นค้าง `processing_at` อยู่ **47+ วินาที** ทั้งที่ `_SEND_TIMEOUT_SECONDS = 10.0` และไม่มีอะไรมาปลดจนกว่าจะ redeploy (ซึ่งจะเรียก `recover_stale_outbox()` บังเอิญกู้ให้)
- **Root Cause:** สองครึ่งที่ต้องมีพร้อมกันถึงจะพัง
  ```python
  async def one(g, sub, payload):              # g = กุญแจที่ผูก outbox_id
      async with sem:
          status = await send(client, sub, payload, ttl=ttl)
      return g, sub, status                    # ← ครึ่งแรก: ถ้า send() โยน บรรทัดนี้ไม่ทำงาน
  outcomes = await asyncio.gather(*tasks, return_exceptions=True)
  for o in outcomes:
      if isinstance(o, BaseException):
          results.append({"outbox_id": None, "cls": "retry"})   # ← ครึ่งหลัง: เดาเอาว่า None
          continue
  ...
  for r in results:
      if r["outbox_id"] is None: continue      # ← "retry" ที่เพิ่งจด ถูกทิ้งตรงนี้
  ```
  `g` **หายไปทั้งก้อน** เพราะ exception แทนที่ tuple ⇒ ฝั่งจับผลไม่มีทางรู้ว่าเป็นของแถวไหน ⇒ เขียน `None` ⇒ แล้ว **ทิ้งมันเงียบ ๆ** ⇒ แถวไม่ถูกจัดประเภทเลย — ไม่จบ ไม่ retry ไม่มีใครรู้ · และเพราะ `_send_one` catch แค่ `httpx.HTTPError` ซึ่ง **ไม่ครอบ `binascii.Error`** จาก `_decode_key()` ⇒ เส้นทาง crypto พังทะลุออกมาได้จริง (ไม่ใช่ทฤษฎี — นี่คือ stack trace จากของจริง)
- **Correct Pattern/Solution:** **จับที่ตัวห่อ task ไม่ใช่ที่ตัวส่ง** — ต้องคง `g`/`sub` ไว้จับผลให้ถูกแถว และต้องครอบ **ทุก** exception:
  ```python
  async def one(g, sub, payload):
      try:
          async with sem:
              status = await send(client, sub, payload, ttl=ttl)
          return g, sub, status
      except Exception as e:                    # ไม่จับ CancelledError (BaseException) — ตั้งใจ
          logger.exception("❌ sender โยน exception (outbox=%s sub=%s host=%s): %s",
                           g["meta"]["outbox_id"], sub["id"],
                           urlparse(sub["endpoint"]).netloc, type(e).__name__)
          return g, sub, None                   # `_classify(None) == "retry"` ⇒ เข้าเส้น retry/เพดาน/dropped ปกติ
  ```
  · **`return g, sub, None` คือหัวใจ** — คืน "สถานะล้มเหลว" ไม่ใช่ "ไม่มีสถานะ" ⇒ ล้มเหลวแบบ**มีตัวนับและมีเจ้าของ** ไม่ใช่แบบเงียบ
  · **และลบ `if r["outbox_id"] is None: continue` ทิ้ง** — มันคือครึ่งหลังของรูนี้ · เปลี่ยนสาขา `BaseException` ที่เหลือให้ **`raise o`** (สิ่งที่เหลือคือ `CancelledError` ซึ่ง *ต้อง* ทะลุผ่าน ไม่ใช่กลืน — กลืนแล้ว lifespan จะรอค้าง) · ถ้ารับมือ exception ที่ไม่รู้ว่าเป็นของแถวไหน **ให้ล้มเสียงดัง** อย่าเดาเป็น `None`
  · **ห้าม log `sub["endpoint"]`** — มันมี token ของอุปกรณ์อยู่ในตัว · `urlparse(...).netloc` พอบอกผู้ให้บริการโดยไม่รั่วความลับ
  · หลักทั่วไป: `return_exceptions=True` **ไม่ใช่การจัดการข้อผิดพลาด** มันแค่ย้ายที่ที่ exception โผล่ — ถ้า task ของคุณมี "กุญแจ" ที่ต้องใช้จับผล (`g` ที่นี่, request id, user id) การปล่อยให้ exception แทน tuple = **ทำกุญแจหาย**
- **Date Added:** 2026-09-29

### 🧪 เทสต์ที่ **ผ่านทั้งก่อนและหลังแก้** = เทสต์ที่ไม่มีฟัน — ต้อง `git stash` โค้ดที่แก้แล้วยืนยันว่า **FAIL ก่อน**
- **Context/Problem:** เขียนเทสต์ regression 3 ตัวสำหรับบั๊กข้างบน แล้ว **ตัวกลาง (`T20b`) ผ่านตั้งแต่ก่อนแก้** ⇒ docstring ที่เขียนว่า *"mutation ที่ต้องทำให้แตก: ถอด try/except → `sent == 0`"* **เป็นข้อความเท็จ** — ถ้าปล่อยไว้ คนอ่านครั้งหน้าจะเชื่อว่ามีด่านตรงนั้น ทั้งที่ไม่มี
- **Root Cause:** เคสที่เขียนไว้คือ *"แถวเดียว 2 อุปกรณ์ — เครื่องหนึ่งโยน เครื่องหนึ่งสำเร็จ"* ซึ่ง **ไม่พังตั้งแต่แรก** เพราะ `results` มีทั้งใบที่เสีย (`outbox_id: None`) และใบที่สำเร็จ (มีเจ้าของ) **ปนกัน** ⇒ การจับกลุ่มตาม outbox ยังได้ผลถูก ⇒ `sent == 1` อยู่แล้ว · เคสที่พังจริงคือ **ทุกอุปกรณ์ของแถวนั้นโยนพร้อมกัน** (ไม่มีใบที่สำเร็จเหลืออยู่เลย ⇒ ไม่มีใครพาเจ้าของกลับมา)
- **Correct Pattern/Solution:** พิสูจน์ความมีฟันด้วย **การย้อนโค้ดจริง ไม่ใช่การอ่าน**:
  ```bash
  git stash push <ไฟล์ที่แก้> -m "mutation: pre-fix"     # ← ไฟล์เทสต์ยังอยู่ในที่เดิม
  docker compose -f docker-compose.test.yml run --rm test_runner \
      sh -c "python -m pytest -q /app/tests/<ไฟล์> -k 'T20'"   # ต้องเห็น FAILED
  git stash pop                                          # คืนโค้ดที่แก้ → ต้อง PASS
  ```
  · ถ้าไม่มีตัวไหน FAIL ⇒ **ยังไม่มีเทสต์สำหรับบั๊กนั้น** ให้เขียนเคสใหม่ (หรือยอมรับว่าเคสเดิมไม่ได้ทดสอบอะไร แล้ว **แก้ docstring ให้ตรงความจริง**)
  · ⚠️ **`git stash` ไฟล์เดียวคือ mutation ที่สมจริงที่สุด** — ได้โค้ดก่อนแก้เป๊ะ ๆ ไม่ต้องเขียน mutant เอง และเก็บไฟล์เทสต์ใหม่ไว้ครบ
  · เคล็ดลับเขียนเคสให้มีฟัน: ถามว่า *"สถานะไหนที่ **หายไปทั้งก้อน**"* ไม่ใช่ *"สถานะไหนที่ผิด"* — บั๊กตระกูล "กุญแจหาย" จะเห็นผลก็ต่อเมื่อ **ไม่มีใบที่ถูกต้องเหลืออยู่ในกลุ่มเลย**
  · และ **ระบุใน docstring ว่าเคสไหน *ไม่ได้* ทดสอบอะไร** โดยเจตนา — ดีกว่าเทสต์ 4 ตัวที่ 1 ตัวหลอกตัวเอง
- **Date Added:** 2026-09-29


### 🔢 สองหน้าที่โชว์ "เลขชุดเดียวกัน" จะเพี้ยนกันเสมอ ถ้าไม่มีเทสต์ที่ **เทียบข้าม endpoint ทีละฟิลด์**
- **Context/Problem:** C3 (`GET /api/me/stats`) โชว์ 6 ตัวเลขในโปรไฟล์/Home อยู่แล้ว · ต่อมา C1 (`GET /api/me/activity`) เพิ่มหน้า "กิจกรรมของฉัน" ที่ต้องโชว์ยอดต่อประเภทด้วย · สเปกต้นทางของ C1 เขียนไว้แค่ **3 แหล่ง** (issue/vote/board_comment) แต่ C3 แยก `issue_comments_posted` ออกมาเป็นฟิลด์ที่ 6 ⇒ ถ้าทำตามสเปกเป๊ะ หน้าสถิติจะบอก "คอมเมนต์ 12" แต่หน้ากิจกรรมจะไม่มีหมวดคอมเมนต์เรื่องให้กดดูเลย ⇒ **ผู้ใช้อ่านเป็นบั๊กทันที** และเป็นบั๊กที่หายากเพราะทั้งสองหน้าก็ "ถูก" ตามสเปกของตัวเอง
- **Root Cause:** ตัวเลขเดียวกันถูกคำนวณจาก **สองคิวรีที่เขียนแยกกัน** (C3 นับด้วย `COUNT(*)` ตรง ๆ · C1 นับด้วย `GROUP BY` บน CTE ที่ `UNION ALL` 4 สาขา) ⇒ ไม่มีอะไรผูกสองที่ไว้ด้วยกัน นอกจากความจำของคนเขียน ⇒ **drift เกิดได้ทันทีที่ใครแก้ฝั่งใดฝั่งหนึ่ง** และวันที่มันเพี้ยน จะไม่มีสัญญาณเตือนใด ๆ (ไม่มี error, ไม่มี type mismatch — แค่เลขไม่ตรง)
- **Correct Pattern/Solution:** ผูกด้วย **เทสต์ที่เรียกทั้งสอง endpoint แล้วเทียบทีละฟิลด์** ไม่ใช่เทียบยอดรวม:
  ```python
  # A2 — เทียบข้าม endpoint ทีละฟิลด์ (ไม่ใช่เทียบ sum)
  stats = client.get("/api/me/stats", …).json()
  act   = client.get("/api/me/activity", …).json()["counts"]
  for act_key, stat_field in COUNT_TO_STAT_FIELD.items():      # ← ตารางแปลงชื่อ อยู่ที่เทสต์
      assert act[act_key] == stats[stat_field], f"{act_key} ไม่ตรงกับ {stat_field}"
  ```
  · **`sum()` ที่เท่ากันไม่ได้แปลว่าถูก** — ถ้าสาขาหนึ่งเกิน 1 แล้วอีกสาขาขาด 1 ผลรวมยังเท่า ⇒ **ต้องเทียบรายฟิลด์**
  · เพิ่ม **drift guard 3 ทาง** ที่บังคับให้ 3 ที่ตรงกันเสมอ: `ACTIVITY_TYPES` (service) · `ActivityCountsOut` (schema) · `COUNT_TO_STAT_FIELD` (เทสต์) ⇒ วันที่เพิ่มประเภทที่ 5 แล้วลืมที่ใดที่หนึ่ง **แตกทันที ไม่เงียบ**
  · **อย่าประกาศยอดเป็น `Dict[str, int]`** — dict เปิดกว้างจนตรวจ drift ไม่ได้ (ลืมเพิ่มคีย์ = ผ่านทุกอย่าง) ⇒ ใช้ Pydantic model ที่ **ประกาศครบทุกฟิลด์** แลกความยืดหยุ่นที่ไม่จำเป็นกับด่านที่จับได้จริง · และต้อง **zero-fill** เสมอ (ประเภทที่ไม่มีข้อมูล = `0` ไม่ใช่หายไปจาก response ไม่งั้นป้ายตัวกรองฝั่ง FE เป็น `undefined`)
- **Date Added:** 2026-09-29

### 🔗 ฟีดที่ต้อง "นับเท่ากับ" ตัวนับอีกหน้า ⇒ `LEFT JOIN` คือข้อบังคับ ไม่ใช่ style
- **Context/Problem:** สาขา `vote_cast` ของฟีด C1 ต้อง join `piri_votes` → `piri_vote_choices` (เอาข้อความตัวเลือก) และ → `piri_boards` (เอาชื่อบอร์ด) · เขียนด้วย `JOIN` ธรรมดาแล้วดูปกติทุกอย่าง
- **Root Cause:** **ตารางที่มี `deleted_at` ของตัวเองจะตัดแถวทิ้งเมื่อใช้ INNER JOIN** — จุดที่พลาดง่ายคือ `piri_vote_choices` มี `deleted_at` **เป็นของตัวเอง** (ต่างจากที่คิดว่ามีแต่ `piri_boards`) ⇒ โหวตที่ตัวเลือกถูก soft-delete จะ **หายจากฟีด** แต่ตัวนับของ C3 ที่นับ `piri_votes` ล้วน ๆ (ไม่ join อะไรเลย) **ยังนับอยู่** ⇒ เลขไม่ตรงกันแบบหาสาเหตุยากมาก เพราะคิวรีทั้งสอง "ถูก" ในตัวเอง
- **Correct Pattern/Solution:** กติกา — **ถ้าคิวรีหนึ่งต้องนับเท่ากับอีกคิวรีที่ไม่มี join เลย การ join ทุกตัวในคิวรีนั้นต้องเป็น `LEFT JOIN` และเงื่อนไข `deleted_at` ต้องอยู่ใน `CASE`/select list ไม่ใช่ใน `ON` หรือ `WHERE`**:
  ```sql
  LEFT JOIN piri_boards pb ON pb.id = v.board_id
  WHERE v.user_id = $1 AND v.deleted_at IS NULL      -- ← กรอง "แถวของฉัน" เท่านั้น
  -- แล้วเอาสถานะการลบไปแสดงเป็นธง ไม่ใช่ไปตัดแถว:
  COALESCE(pb.title, '(ต้นทางถูกลบแล้ว)') AS title,
  (pb.id IS NULL OR pb.deleted_at IS NOT NULL) AS is_deleted_source
  ```
  · **`deleted_at` ไปไว้ใน `ON` ก็ผิด** — `LEFT JOIN … ON pb.id = v.board_id AND pb.deleted_at IS NULL` จะได้ `pb.*` เป็น NULL แล้วแถว "ดูเหมือนถูกลบ" ทั้งที่มันแค่ถูก soft-delete ⇒ แยกไม่ออกระหว่าง "ต้นทางถูกลบ" กับ "join ไม่ติด" ซึ่งเป็นคนละเรื่องกัน (อันแรกต้องโชว์พร้อมธง · อันหลังคือข้อมูลเสีย)
  · **อย่าลืม `deleted_at IS NULL` ที่ตัวแถวเอง** (`v.deleted_at`) — อันนี้ต้องตัดจริง เพราะเป็นแถวของฉันที่ถูกยกเลิก ไม่ใช่ต้นทางที่ถูกซ่อน
  · เขียนเทสต์ที่ **soft-delete ต้นทาง** แล้ว assert ว่าแถวยังอยู่ + `is_deleted_source == true` (ไม่ใช่ assert ว่าแถวหาย) — นี่คือเทสต์ที่จับ INNER JOIN ได้
- **Date Added:** 2026-09-29

### 🔢 `sql.count("$")` ใช้ตรวจจำนวน placeholder **ไม่ได้** เมื่อ `$1` ตัวเดียวถูกใช้ซ้ำหลายที่
- **Context/Problem:** กฎเดิมของโปรเจค (บทเรียนเรื่อง `IndeterminateDatatypeError`) คือ `assert sql.count("$") == len(params)` ก่อน `conn.fetch()` · แต่คิวรี `UNION ALL` 4 สาขาของ C1 ใช้ `$1` (user_id) **สาขาละครั้ง = 4 ครั้ง** ⇒ `sql.count("$")` ได้ 7 ทั้งที่มี params จริง 4 ตัว ⇒ **assert พังทั้งที่โค้ดถูก**
- **Root Cause:** `count("$")` นับ **จำนวนครั้งที่ตัวอักษรปรากฏ** ไม่ได้นับ **จำนวน parameter ที่แตกต่างกัน** — ใช้ได้เฉพาะคิวรีที่แต่ละ placeholder ปรากฏครั้งเดียว (ซึ่งเป็นคิวรีส่วนใหญ่ของโปรเจค จึงไม่มีใครเจอปัญหานี้มาก่อน) · และกับดักคือ **ทางแก้ที่แย่ที่สุดคือลบ assert ออก** — เพราะมันคือด่านที่บอก *สาเหตุ* ก่อนที่ asyncpg จะโยน error ที่อ่านยาก
- **Correct Pattern/Solution:** นับ **placeholder ที่มีเลขสูงสุด** แทน:
  ```python
  def _assert_placeholders(sql: str, params: list) -> None:
      highest = max((int(m) for m in re.findall(r"\$(\d+)", sql)), default=0)
      assert highest == len(params), f"placeholder สูงสุด ${highest} ไม่ตรงกับ params {len(params)} ตัว"
  ```
  · ถูกทั้งสองกรณี — คิวรีที่แต่ละ placeholder ปรากฏครั้งเดียว (ได้ค่าเท่าเดิม) และคิวรีที่มีตัวซ้ำ (ได้ค่าที่ถูก)
  · **ทางเลือกที่ผิด:** "รวบ `$1` ให้เหลือครั้งเดียว" ด้วยการ cross join ตาราง params — ทำให้อ่านยากขึ้นโดยไม่ได้อะไรกลับมา (`$1` ซ้ำ 4 ครั้งใน CTE อ่านชัดกว่าอยู่แล้ว)
  · เขียนคอมเมนต์กำกับไว้ที่ `$1` ว่าซ้ำโดยเจตนา ไม่งั้นคนถัดไปจะนึกว่าเป็นพิมพ์ผิดแล้ว "แก้" ให้พัง
- **Date Added:** 2026-09-29

### 🧩 ตาราง polymorphic (`entity_type` + `entity_id`) — เลือก **ไม่มี FK และไม่มี CHECK** โดยเจตนา แล้วย้ายความถูกต้องไปที่ service
- **Context/Problem:** ตาราง `bookmarks` ต้องชี้ไปได้ทั้ง `issues` และ `piri_boards` ด้วยคอลัมน์คู่เดียว ⇒ FK ของ Postgres ผูกกับ **ตารางเดียว** บังคับด้วย FK ไม่ได้ · และการใส่ `CHECK (entity_type IN ('issue','board'))` ก็ดูเป็นเรื่องดีมีวินัย
- **Root Cause:** ทั้งสองทางล้วนมีต้นทุนที่มองไม่เห็นตอนเขียน: **FK** ทำได้เฉพาะเมื่อแยกเป็น 2 คอลัมน์ nullable (`issue_id`, `board_id`) ซึ่งทำให้ **ทุกคิวรีต้องเขียน `COALESCE`** และเพิ่มชนิดใหม่ (D1 จะเพิ่ม `'event'`) ต้อง `ALTER TABLE` · **CHECK** ทำให้ **ทุกครั้งที่เพิ่มชนิดต้องออก migration ใหม่** ซึ่งเป็นหนี้ที่โปรเจคนี้เจอมาแล้วจริง (`piri_boards.board_type` มี CHECK ไว้ก่อน ⇒ E1 ต้อง `DROP CONSTRAINT` + `ADD CONSTRAINT` ทั้งที่งานคือ "เพิ่มตัวเลือกใน dropdown")
- **Correct Pattern/Solution:** เลือก **ไม่บังคับที่ DB** แล้วย้ายความถูกต้องไปที่ชั้นที่แก้ไขได้โดยไม่ต้อง migrate:
  · **ความถูกต้องของ "ต้นทางมีจริง" → `service`** — `create_bookmark` ตรวจ `SELECT id FROM … WHERE id = $1 AND deleted_at IS NULL` **ก่อน** insert (ไม่พบ = `NotFoundError` → 404) ⇒ ด่านนี้แข็งแรงกว่า FK เพราะ FK ตรวจ "มีแถว" แต่ **ไม่ตรวจ `deleted_at`** ซึ่งเป็นสิ่งที่เราต้องการจริง
  · **ความถูกต้องของ "ชนิดที่รองรับ" → Pydantic `Literal`** — ตอบ 422 ให้เองโดยไม่ต้อง migrate และเป็น whitelist ที่ **กัน SQL injection ที่ชั้น type** ไปด้วย
  · ⚠️ **ห้ามใช้ชื่อตารางจาก input ต่อ f-string** — ใช้ **dict whitelist** ที่ map ชนิด → SQL ที่เขียนไว้ตายตัว:
    ```python
    _EXISTS_SQL = {"issue": "SELECT id FROM issues WHERE id = $1 AND deleted_at IS NULL",
                   "board": "SELECT id FROM piri_boards WHERE id = $1 AND deleted_at IS NULL"}
    ```
    แล้ว `.get(entity_type)` ที่ไม่พบ → `NotFoundError` (ไม่ใช่ `KeyError` → 500) — **นี่คือจุดที่ "ไม่มี CHECK ที่ DB" อาจกลายเป็นช่องโหว่ ถ้าเผลอประกอบชื่อตารางเอง**
  · **เขียนคอมเมนต์ที่ DDL อธิบายว่าทำไมไม่มี FK/CHECK** ไม่งั้นคนถัดไปจะ "เติมให้ครบ" แล้วพัง
- **Date Added:** 2026-09-29

### ➕ `POST` ที่แทน "สมาชิกของชุด" ต้อง **idempotent** (200) ไม่ใช่ 409 — ต่างจาก "หนึ่งเสียง หนึ่งครั้ง"
- **Context/Problem:** bookmark ซ้ำควรตอบอะไร · สเปกต้นทางเสนอ `ConflictError` 409 ตามแบบ `piri_votes` ที่โปรเจคใช้อยู่ ⇒ ทำตามดูสมเหตุสมผลและสอดคล้องของเดิม
- **Root Cause:** **`piri_votes` กับ `bookmarks` มีความหมายต่างกันโดยพื้นฐาน** — การโหวตคือ *เหตุการณ์* ("หนึ่งเสียง") ⇒ ซ้ำ = ผิดจริง ต้องปฏิเสธ · bookmark คือ *สมาชิกภาพของเซต* ("อยู่ในชุดที่บันทึกไว้") ⇒ การกดซ้ำ **ไม่ได้เปลี่ยนอะไร** ⇒ การตอบ error คือการลงโทษผู้ใช้ที่ไม่ทำอะไรผิด และผู้ใช้จะเจอบ่อยด้วย (ดับเบิลแท็ป, เน็ตช้าแล้วกดซ้ำ, เปิด 2 แท็บ) ⇒ กลายเป็น "บั๊ก" ในสายตาผู้ใช้ทันที
- **Correct Pattern/Solution:** ใช้ upsert ใน transaction เดียว แล้ว **รายงานว่าสร้างใหม่หรือมีอยู่แล้ว**:
  ```sql
  INSERT INTO bookmarks (user_id, entity_type, entity_id) VALUES ($1,$2,$3)
  ON CONFLICT (user_id, entity_type, entity_id) DO UPDATE
      SET entity_type = EXCLUDED.entity_type      -- no-op ที่ถูกต้อง (ต้องมี SET จึง RETURNING ได้)
  RETURNING id, …, (xmax = 0) AS created
  ```
  · **`(xmax = 0)`** คือทริกมาตรฐานของ Postgres ที่แยก "แถวใหม่" (`xmax = 0`) จาก "แถวที่ถูก update" (`xmax != 0`) ⇒ router ตอบ **201 ถ้า `created` · 200 ถ้าไม่** โดยไม่ต้องคิวรีเพิ่ม
  · **`DO UPDATE` ที่ set ค่าเดิมทับตัวเอง** เป็นวิธีที่รับประกันว่า `RETURNING` คืนแถวเสมอ (`DO NOTHING` จะคืน **0 แถว** เมื่อชน ⇒ ต้องคิวรีตามอีกครั้ง)
  · **unique index ต้องมีคอลัมน์ครบตาม `ON CONFLICT`** — `uq_..._user_entity (user_id, entity_type, entity_id)` · และ **`entity_type` ต้องอยู่ในคีย์** ไม่งั้นเรื่อง #7 กับบอร์ด #7 จะถือเป็นอันเดียวกัน
- **Date Added:** 2026-09-29

### 📄 Pagination ที่เรียงด้วย `created_at` เฉย ๆ จะได้แถวซ้ำ/แถวหาย — เพราะ `CURRENT_TIMESTAMP` คือ **เวลาเริ่มทรานแซกชัน**
- **Context/Problem:** ฟีด C1 เรียง `ORDER BY created_at DESC` · เทสต์ที่เขียนด้วยข้อมูลคนละทรานแซกชันผ่านปกติทุกอย่าง
- **Root Cause:** `CURRENT_TIMESTAMP` ของ Postgres **ไม่ใช่เวลาที่ statement รัน** แต่เป็น **เวลาที่ทรานแซกชันเริ่ม** ⇒ แถวทั้งหมดที่ insert ในทรานแซกชันเดียวกัน (เช่น คอมเมนต์ 5 อันในลูปเดียว, `executemany`, หรือ seed ในไฟล์เดียว) มี `created_at` **เท่ากันเป๊ะ** ⇒ `ORDER BY created_at` อย่างเดียว **ไม่กำหนดลำดับที่แน่นอน** (แล้วแต่แผน/ลำดับที่ heap คืนมา) ⇒ ระหว่าง `LIMIT/OFFSET` สองหน้าจะเกิด **แถวซ้ำหรือแถวหาย** และจะโผล่เฉพาะกับข้อมูลที่สร้างพร้อมกัน ซึ่งเทสต์ปกติแทบไม่สร้าง
- **Correct Pattern/Solution:** ใส่ **tie-break ที่ไม่ซ้ำ** ต่อท้ายเสมอ — `ORDER BY created_at DESC, activity_type, src_id DESC` (`src_id` = PK ของตารางต้นทาง ⇒ ไม่ซ้ำภายในประเภท · และต้องมี `activity_type` คั่นเพราะ `src_id` **ซ้ำกันได้ข้ามตาราง**) · **ห้ามใช้ `OFFSET` กับคีย์ที่ซ้ำได้โดยไม่มี tie-break**
  · เขียนเทสต์ที่ **จงใจสร้างแถว `created_at` เท่ากันเป๊ะ** (insert หลายแถวใน transaction เดียว) แล้วไล่ทีละหน้า assert ว่า **ไม่มีแถวซ้ำและไม่มีแถวหาย** — ถอด tie-break ออกแล้วต้องแตก
  · `total`/`pages` ก็ต้องมาจากคิวรีเดียวกับที่ใช้กรอง ไม่งั้นเลขหน้าจะไม่ตรงกับจำนวนแถวที่ไล่ได้จริง — และ **คำนวณ `total` จาก `counts` ที่มีอยู่แล้วได้ ไม่ต้อง `COUNT(*)` ซ้ำ** (แต่ต้องรับประกันว่า `total == counts[activity_type]` เมื่อมีการกรอง)
- **Date Added:** 2026-09-29

### 🔤 ตัดข้อความตัวอย่างใน SQL ด้วย `LEFT(body, 160)` — นับ **ตัวอักษร** ไม่ใช่ byte (ปลอดภัยกับภาษาไทย)
- **Context/Problem:** ฟีดต้องโชว์ตัวอย่างคอมเมนต์ 160 ตัวอักษร · ทางที่ดูยืดหยุ่นกว่าคือดึง `body` เต็มมาก่อนแล้วตัดใน Python
- **Root Cause:** ข้อความไทยเป็น UTF-8 หลาย byte ต่อตัวอักษร ⇒ การตัดด้วยความยาว byte (`body[:160]` บน bytes หรือ `content-length`-style) จะ **ตัดกลางตัวอักษร** ได้ตัวอักษรเสียหาย · และการดึง `body` เต็มผ่าน asyncpg เพื่อมาตัดทิ้งคือการขนข้อมูลที่ไม่ได้ใช้ข้ามโปรเซส (ฟีด 20 แถว × คอมเมนต์ยาว = เปล่าเปลืองจริง)
- **Correct Pattern/Solution:** `LEFT(bc.body, 160)` ที่ SQL — **`LEFT()` นับตัวอักษรตาม character semantics** จึงปลอดภัยกับภาษาไทย และไม่ลากข้อความเต็มผ่าน asyncpg
  · เขียนเทสต์ด้วย **ข้อความไทย** (ไม่ใช่ `'a'*200`) แล้ว assert ความยาวเป็นตัวอักษร — `'a'*200` ผ่านทุกทางที่ผิดด้วย เพราะ 1 byte = 1 ตัวอักษร
  · ⚠️ **`LEFT()` คืน `NULL` เมื่อ input เป็น `NULL`** ⇒ ถ้าคอลัมน์ nullable ต้องครอบ `COALESCE` หรือปล่อยให้ schema ประกาศ `Optional[str]` ให้ตรงกัน
- **Date Added:** 2026-09-29

### 🧰 แก้หลายไฟล์พร้อมกันด้วยสคริปต์ที่ **assert ว่า anchor เจอครั้งเดียว** แล้วล้มทันทีถ้าไม่ตรง
- **Context/Problem:** งานรอบหนึ่งต้องแก้ 12 จุดใน 6 ไฟล์ + วางไฟล์ใหม่ 6 ไฟล์ · และงานนี้ห้ามรันพร้อม backend suite เพราะ `docker-compose.test.yml` **bind mount `./backend`** ⇒ แก้ไฟล์กลางเทสต์ = เทสต์พังยกชุด · อีกทั้ง context ของคนทำงานมีจำกัดและถูกตัดกลางทางได้
- **Root Cause:** การแทรกโค้ดด้วยมือ (หรือ `Write` ทั้งไฟล์) มีโหมดพังที่ **เงียบ** — เยื้องผิดหนึ่งช่อง, แทรกซ้ำเพราะทำสองรอบ, หรือ anchor ไปตรงกับที่อื่นที่บังเอิญเหมือนกัน ⇒ โค้ดพังแบบที่อ่านไม่ออกว่ามาจากขั้นไหน · และการพิมพ์ไฟล์เทสต์ขนาด ~35KB ซ้ำคือการเผา context ที่อาจไม่พอ
- **Correct Pattern/Solution:** รวมทุกการแก้เป็น **สคริปต์เดียวที่ล้มเสียงดัง** เก็บ "ข้อความที่ต้องแทรก" ไว้เป็นค่าคงที่ในโมดูล (ไม่พิมพ์ซ้ำตอนติดตั้ง):
  ```python
  def sub_once(text, old, new, what):
      n = text.count(old)
      assert n == 1, f"{what}: เจอ anchor {n} ครั้ง (ต้องเป็น 1) — หยุดก่อนแก้ไฟล์"
      return text.replace(old, new)

  for src_name, dst in COPY:
      assert not dst.exists(), f"⛔ {dst} มีอยู่แล้ว — ไม่ทับ (ตรวจก่อน)"
      shutil.copy2(SRC / src_name, dst)
  ```
  · **`assert count == 1` คือหัวใจ** — `replace` เปล่า ๆ จะแทนที่ **ทุกที่ที่เจอ** เงียบ ๆ · และ 0 ครั้งก็เงียบ (ไฟล์ไม่เปลี่ยน แต่สคริปต์รายงานว่าสำเร็จ)
  · **`assert not dst.exists()`** ทำให้รันซ้ำแล้วไม่ทับของที่แก้ด้วยมือไปแล้ว
  · **`assert` ก่อนหน้าให้ "สิ่งที่ต้องมีอยู่แล้ว"** (เช่น `assert "ACTIVITY_TYPES" not in t`) ⇒ กันแทรกซ้ำ
  · **ด่านตรวจสุดท้ายต้องดู "ผลลัพธ์" ไม่ใช่ "exit code"** — สคริปต์ที่รันจบไม่ได้แปลว่าไฟล์ถูก: ตรวจด้วย `git diff --stat` เทียบกับรายการที่คาดไว้ทีละไฟล์
  · ⚠️ **ตรวจ anchor ด้วย dry-run ก่อนติดตั้งจริง** — `n = text.count(old)` ทั้ง 9 anchor ⇒ เจอ `1` ครบทุกตัวจึงค่อยรัน (ทำแบบนี้แล้วได้ 9/9)
- **Date Added:** 2026-09-29

### 🚪 "เปิดดูไม่ได้" ของสิ่งเดียวอาจมี **หลายแกน อยู่คนละคอลัมน์** — เช็คแกนเดียว = แถวนั้นยังเป็นลิงก์ที่พาไป 404
- **Context/Problem:** ฟีด C1 (`me_service.get_my_activity`) และลิสต์ C2 (`bookmark_service.list_bookmarks`) ตัดสินว่าแถวไหน "ต้นทางหาย" ด้วย `deleted_at IS NOT NULL` แล้วติดธง `is_deleted_source` ให้ FE ตัดลิงก์ · เทสต์ A3/B4/B6 ที่มีอยู่ **ผ่านหมด** · แต่ผู้ใช้ที่โหวตในบอร์ดซึ่งสภากด "ซ่อน" ทีหลัง จะเห็นแถวที่ดูปกติ กดได้ แล้ว **พาไปหน้า 404**
- **Root Cause:** บอร์ดหนึ่งใบ "เปิดดูไม่ได้" ได้ **สองทาง และอยู่คนละคอลัมน์**:
  · `deleted_at IS NOT NULL` — ลบแบบ soft
  · `status = 'hidden'` — สภา/แอดมินกด "ซ่อนบอร์ด" (`board_moderation_service.hide_board`)
  และ `board_service.get_board_detail()` ตอบ **404 ทั้งสองทาง** (`if row["status"] == "hidden": raise NotFoundError("ไม่พบ board นี้")`) ⇒ สัญญาที่ผู้บริโภคเห็นคือ "สองแกนนี้ให้ผลเหมือนกัน" แต่ predicate ที่เขียนไว้รู้จักแกนเดียว
  · **ทำไมเทสต์เดิมจับไม่ได้:** A3/B6 ตั้ง `deleted_at` ด้วย `UPDATE` ตรง ๆ ⇒ **ไม่ได้เดินผ่านเส้นทางที่ผู้ใช้ใช้จริง** (`hideBoard()`) ⇒ เทสต์ที่ "ผ่าน" กำลังยืนยันพฤติกรรมของเส้นทางที่ไม่มีใครใช้ — เป็นกับดักเดียวกับ "เทสต์ที่จำลองสคีมาเก่าไม่เหมือนของจริง"
  · **ภัยเงียบคือ over-fix:** ทางที่ล่อใจที่สุดคือ `status <> 'active'` ซึ่ง **ผิด** — `'closed'` (ปิดประเด็น) ยังเปิดดูได้ (detail ตอบ 200) ⇒ จะไปตัดลิงก์ที่ใช้งานได้จริงทิ้ง
- **Correct Pattern/Solution:** **ลอกรายการ "สภาพที่ทำให้ 404" มาจากตัวที่ตัดสินจริง ไม่ใช่จากความจำ** — เปิด `get_board_detail()` แล้วเขียน predicate ให้ตรงทีละบรรทัด: `(pb.id IS NULL OR pb.deleted_at IS NOT NULL OR pb.status = 'hidden')`
  · **ทุกที่ที่ตัดสิน "ต้นทางเปิดได้ไหม" ต้องใช้ predicate ชุดเดียวกัน** — รอบนี้มี 4 จุด (`me_service` 2 สาขา · `bookmark_service` ทั้ง `CASE` และ `_EXISTS_SQL`)
  · **ใส่คอมเมนต์ที่ตัว predicate ว่าทำไมไม่ใช่ `<> 'active'`** ไม่งั้นคนถัดไปจะ "ย่อให้สั้นลง" แล้วพังเงียบ
  · **เขียนเทสต์คู่กันเสมอ: ตัวบังคับแก้ + ตัวกันแก้เกิน** — ตัวหลัง (`test_closed_board_is_not_flagged_as_deleted`) ต้อง **ผ่านทั้งก่อนและหลังแก้** ถ้ามันล้มแปลว่ากำลัง over-fix · สัญญาณว่าออกแบบถูกคือรันเทสต์ก่อนแก้แล้วได้ **"ล้มเฉพาะตัวที่ควรล้ม"** (รอบนี้ 3 failed / 2 passed)
  · **เจอแกนที่สองแล้วให้กวาดหาผู้บริโภครายอื่นด้วย** — `grep -rn "deleted_at IS NULL" backend/services/` แล้วถามทีละอันว่า "คิวรีนี้รู้จักแกนที่สองไหม" · รอบนี้ `home_service` (`b.status = 'active'`) และ `view_count` (`UPDATE` อยู่ **หลัง** 404 ⇒ ไปไม่ถึง) ปลอดภัยอยู่แล้ว แต่เจอ `NotificationCenter` deep-link ที่ยังเป็นบั๊กจริง ⇒ **บันทึกเป็นงานแยก ไม่แก้เงียบ ๆ ในรอบนี้** (การขยาย scope เองโดยไม่แจ้ง = ความผิดพลาดที่แพงกว่า)
  · ⚠️ **ห้าม fold แกนที่เป็น "สิทธิ์ผู้ดู" เข้ากับ "ถูกลบ"** — `get_issue_detail` มี 404/403 จาก `_assert_can_view` ซึ่งขึ้นกับว่า **ใครดู** ไม่ใช่สภาพของข้อมูล ⇒ ถ้ารวมเข้า `is_deleted_source` ผู้ใช้ที่ไม่มีสิทธิ์จะเห็นแถวถูกหรี่ถาวรทั้งที่ของยังอยู่ · และ issue **ไม่มี** สถานะ "ซ่อน" เลย ⇒ สาขาที่อ้าง `issues` ไม่ต้องแก้ (อย่าเผลอเติมให้ "สมมาตร" เพราะดูคล้ายกัน)

### 🔀 เปลี่ยนชื่อ repo บน GitHub — "ไม่ต้องแก้โค้ด" จริง แต่ต้องแยกให้ออกว่า **อะไรผูกกับชื่อ repo** กับ **อะไรแค่บังเอิญชื่อเหมือน**
- **Context/Problem:** repo ชื่อ `prsc_portal` แต่ระบบชื่อ PIRIvoice ⇒ อยากเปลี่ยนชื่อ repo ให้ตรง · คำถามแรกคือ "ต้องแก้โค้ดมั้ย" ซึ่งตอบได้ด้วยการ**วัด** ไม่ใช่การเดา
- **Root Cause / วิธีตรวจ (3 คำสั่ง ตอบได้ทันที):**
  ```bash
  ls .github/workflows 2>/dev/null            # ① มี CI ที่อ้าง slug ไหม
  grep -rn 'github.com/<owner>/<old-name>' .  # ② มี slug ฝังในโค้ดไหม
  gh api repos/<owner>/<new-name>             # ③ ชื่อใหม่ว่างไหม (404 = ว่าง)
  ```
  ผลจริงรอบนี้: **ไม่มี CI** · **ไม่มี slug ฝัง** (ที่เจอเป็น URL ของบุคคลที่สามใน `eslint.config.ts`/`playwright.config.ts`/`package-lock.json`) · ⇒ **0 บรรทัดที่ต้องแก้**
  · และชั้นแบรนด์เป็น PIRIvoice ครบอยู่แล้ว (`package.json` name · image `pirivoice-${ENV_NAME}-*` · `index.html` · `manifest.json`) ⇒ ชื่อ repo เป็น**ชื่อภายนอก**ที่ไม่ผูกกับโค้ดเลย
- **Correct Pattern/Solution:**
  ```bash
  gh api repos/<owner>/<old> -X PATCH -f name=<new>       # เปลี่ยนชื่อ (ต้องมี scope repo)
  git remote set-url origin git@github.com:<owner>/<new>.git   # แก้ทีละ clone
  ```
  · ★ **GitHub redirect git operation ของ repo ที่เปลี่ยนชื่อให้อัตโนมัติ** (ขึ้นแค่ `remote: This repository moved. Please use the new location` แล้วทำงานต่อสำเร็จ) ⇒ **`pull_all.sh` บน VPS ยัง deploy ได้แม้ remote ยังชี้ชื่อเก่า** — ไม่ใช่เหตุฉุกเฉิน แต่ควรแก้ให้สะอาด
  · ⚠️ **"ชื่อที่โชว์" ต้องแก้ แต่ "identifier ที่ผูกข้อมูล/infra" ห้ามแตะ** (หลักเดียวกับบทเรียน rebrand ก่อนหน้า) — รอบนี้เจอของที่ **ดูเหมือนควรแก้แต่ห้ามแก้ 2 อย่าง**:
    - `backend/main.py` CORS `prsc-test.singto1597.xyz` — **มีคอมเมนต์กำกับไว้เองว่า "โดเมนเก่าช่วงเปลี่ยนผ่าน อย่าลบจนกว่าจะย้าย DNS เสร็จ"** ⇒ การกวาดหา "ชื่อเก่าที่ต้องลบ" แบบไม่อ่านคอมเมนต์ข้าง ๆ = ทำ CORS พัง
    - `scripts/generate_vapid_keys.py` คอมเมนต์ path `~/prsc_portal/...` — **ยังถูกต้อง** เพราะ **ไม่ได้เปลี่ยนชื่อโฟลเดอร์บน VPS** ⇒ ถ้าแก้ให้ "ตรงชื่อระบบ" จะกลายเป็น path ที่ไม่มีอยู่จริง
  · ⛔ **3 อย่างที่ห้ามเปลี่ยนชื่อตาม แม้จะชื่อซ้ำกับ repo** เพราะถูกอ้างจาก**ข้างนอก** ไม่ใช่จากชื่อ repo:
    | ของ | ใครอ้าง |
    |---|---|
    | `~/program_projects/prsc_portal/` (deploy root) | `docker stack deploy` + **cwd ของ tmux session** ที่ agent ทำงานอยู่ |
    | `/home/prscportal/prsc_portal/` + user `prscportal` (VPS) | SSH config + path ที่ `pull_all.sh` รัน (และมี **2 clone วางข้างกัน** ⇒ พลาดแล้วโดน production) |
    | ชื่อ **swarm stack** `prsc_staging` | `docker service ls` + คำสั่ง deploy ทั้งหมด ⇒ เปลี่ยน = สร้าง stack ใหม่แล้วลบเก่า = **มี downtime** |
  · ⇒ **เปลี่ยนชื่อ repo ได้โดยระบบไม่สะดุด** เพราะสามอย่างข้างบนคนละชั้นกับชื่อ repo

- **Date Added:** 2026-09-29

### 🌿 ต้องทำงานอื่นคู่กับ suite ที่ **bind-mount ทรีหลัก** ⇒ ใช้ `git worktree` ไม่ใช่ `git stash`/สลับ branch
- **Context/Problem:** `docker-compose.test.yml` bind mount `./backend` เข้า container ⇒ **ระหว่างที่ suite รันอยู่ แก้ไฟล์ใต้ `backend/` เมื่อไรเทสต์พังยกชุด** และ **สลับ branch ในทรีหลักก็พังเหมือนกัน** (ไฟล์ใต้ mount เปลี่ยนทั้งชุดกลางเทสต์) — แต่บางงาน (เช่น rebrand, งานเอกสาร) ไม่เกี่ยวกันเลยและไม่ควรรอ 40–70 นาที
- **Root Cause:** `git stash` / `git checkout` **แก้ไฟล์ในทรีเดียวกับที่ container มองเห็น** ⇒ ตัวเลือก "สลับไปทำอย่างอื่นแล้วกลับมา" ทั้งหมดใช้ไม่ได้ระหว่างเทสต์รัน · และการรอเปล่า ๆ คือการเผา context ของคนทำงาน (ซึ่งถูกตัดกลางทางได้)
- **Correct Pattern/Solution:** แตก **worktree** — ได้ checkout อีกชุดที่ **ไม่แตะทรีหลักเลย**
  ```bash
  git worktree add /tmp/piri-rebrand -b chore/rebrand          # ฐาน = HEAD ปัจจุบัน
  ln -sfn "$PWD/frontend/node_modules" /tmp/piri-rebrand/frontend/node_modules   # ★ ไม่ต้อง npm install ใหม่
  cd /tmp/piri-rebrand && <แก้ + รันด่านตรวจของงานนั้น>
  git worktree remove /tmp/piri-rebrand                        # ลบ symlink ทิ้ง ไม่ลบ target
  ```
  · ★ **worktree แชร์ `.git` กับทรีหลัก** ⇒ ได้ `origin` remote ที่แก้ล่าสุดแล้วไปด้วย (สำคัญมากเมื่องานนั้นคือ "เปลี่ยน remote") · และ `git fetch` จาก worktree อัปเดต ref ที่ทรีหลักเห็นทันที
  · ⚠️ `frontend/` **ไม่ได้ถูก bind mount** เข้า test container (มีแต่ `./backend`) ⇒ รัน `npm run type-check|lint|test:unit|build` ใน worktree พร้อมกับ suite ได้ไม่มีปัญหา
  · ⚠️ **อย่า `cd` เข้า worktree แล้วลืม** — คำสั่งถัดไปจะไปรันผิดที่ · ตรวจด้วย `git rev-parse --show-toplevel` เมื่อไม่แน่ใจ
  · 📌 ทางเลือกที่ไม่ต้องใช้ worktree: **งานที่แตะแค่ `docs/` · `frontend/` · `~/reports/` ทำในทรีหลักได้เลย** เพราะไม่ถูก mount ⇒ **ก่อนตัดสินใจว่าต้อง worktree ไหม ให้ถามว่า "งานนี้แตะ `backend/` ไหม"** (คำถามเดียวจบ)
- **Date Added:** 2026-09-29

### 🧮 พิสูจน์ว่า merge "ไม่ทำของหาย" ด้วย **multiset ของบรรทัด** ไม่ใช่ความยาวไบต์ — ผลต่างไบต์หลอกได้
- **Context/Problem:** merge conflict ที่แก้ด้วยมือ (แก้บน GitHub) ต้องพิสูจน์ว่า **ของทั้งสองฝั่งอยู่ครบ** ไม่ใช่แค่ "diff ดูสวย" · วิธีที่ล่อใจที่สุดคือเทียบความยาว/ไบต์ ⇒ รอบนี้ได้ `head = 404,830` แต่ `base + deltaA + deltaB = 404,857` คือ **−27 ไบต์** และ `head.startswith(deltaA)` เป็น **False** ⇒ เกือบสรุปว่า merge ผิด
- **Root Cause:** **บรรทัดที่ทั้งสองฝั่งเพิ่มเหมือนกันเป๊ะ ถูกนับครั้งเดียวอย่างถูกต้อง** ⇒ ผลบวกของสอง delta จึงมากกว่าของจริงเสมอเมื่อมีบรรทัดซ้ำ · และ `startswith` พังเพราะการแทรกบรรทัดว่าง/คอมเมนต์กันรอยต่อ ทำให้ "ส่วนหัวของฝั่งหนึ่ง" ไม่ได้อยู่ติดกันเป็นบล็อกเดิมอีก · ⇒ **การวัดผลรวมแบบ "บวกลบ" ใช้กับ merge ไม่ได้ตั้งแต่ต้น** เพราะ merge ไม่ใช่การบวก
- **Correct Pattern/Solution:** เทียบ **เซต/มัลติเซต** ซึ่งเป็นสมบัติที่ merge ต้องรักษาไว้จริง
  ```python
  from collections import Counter
  a, b, m = (Counter(p.read_text(encoding="utf-8").splitlines()) for p in (fa, fb, fm))
  assert not (a - m), "บรรทัดของฝั่ง A หายไป"      # ★ คุณสมบัติที่ต้องเป็นจริง
  assert not (b - m), "บรรทัดของฝั่ง B หายไป"
  # หัวข้อ (heading) ของ merge ต้องเท่ากับยูเนียนของสองฝั่งพอดี
  assert set(headings(m)) == set(headings(a)) | set(headings(b))
  ```
  · **ใช้ `Counter` ไม่ใช่ `set`** — ไฟล์ที่มีบรรทัดซ้ำ (ตาราง/ลิสต์) ต้องนับจำนวนด้วย ไม่ใช่แค่มี/ไม่มี
  · **`git diff --numstat <base> <head>` ที่โชว์ `N 0` (ลบ 0 บรรทัด)** คือหลักฐานเสริมที่อ่านง่ายและคนอื่นตรวจซ้ำได้ — ใช้คู่กัน
  · ⚠️ **`git merge-tree --write-tree A B` merge "commit" ไม่ใช่ working tree** ⇒ การตรวจ conflict **ก่อน commit ไม่มีความหมาย** ต้อง commit แล้วตรวจ `git merge-tree` บน ref จริง
  · ⚠️ **สอง branch ที่ append ต่อท้ายไฟล์เดียวกันจากฐานเดียวกัน = ชนแน่นอนไม่ว่า merge ใบไหนก่อน** (GitHub คำนวณ mergeability กับ base ปัจจุบันเสมอ) ⇒ ถ้ารู้ล่วงหน้า ให้ **เตือนให้ merge ใบที่แตะไฟล์นั้นก่อน** หรือเตรียมแก้ไว้เลย
- **Date Added:** 2026-09-29

### 🎯 "ด่าน delta" ต้องมาจาก **`grep` หาผู้บริโภคของโมดูล** ไม่ใช่จากรายชื่อไฟล์เทสต์ที่เราเขียนเอง
- **Context/Problem:** หลัง rebase ขึ้น base ใหม่ ไม่อยากเสีย 60 นาทีรัน suite ทั้งชุด จึงเลือกรัน "เฉพาะไฟล์ที่กระทบ" — รอบนี้รัน **4 ไฟล์ → 136 passed** แล้วเกือบสรุปว่า "ครบ" · ของจริงต้องรัน **7 ไฟล์ → 203 passed**
- **Root Cause:** รายชื่อ 4 ไฟล์มาจาก **"ไฟล์ที่เราเขียน/แก้ในรอบนี้"** ซึ่งเป็นมุมของ *คนเขียน* ไม่ใช่มุมของ *โค้ดที่เปลี่ยน* · ที่ขาดคือ **ไฟล์เทสต์ของคนอื่นที่ import โมดูลที่เราแก้** — และไม่มีทางเห็นได้จากการอ่านรายชื่อไฟล์ของตัวเอง
- **Correct Pattern/Solution:** สร้างด่านจาก **การค้นหาผู้บริโภค** เสมอ
  ```bash
  # 1) ไฟล์ production ที่เปลี่ยนในช่วง rebase
  git diff --name-only <old-base> <new-base> | grep '\.py$'
  # 2) ใครอ้างถึงโมดูลเหล่านั้น (ทั้ง production และ tests)
  grep -rn 'me_service\|push_service\|bookmark_service' backend/tests/ | cut -d: -f1 | sort -u
  # 3) รวมกับไฟล์ที่เราแตะ แล้วนั่นคือรายชื่อด่าน
  ```
  · รอบนี้ `grep -rn 'push_service'` เปิดเผย `test_push_subscriptions` · `me_service` เปิดเผย `test_me_stats` + `test_home_summary` ⇒ **3 ไฟล์ที่มองไม่เห็นจากมุมคนเขียน**
  · ★ **ยืนยันจำนวนด้วย `--collect-only` ไม่ใช่นับจาก progress line** — progress line ตัดบรรทัดที่ 72 ตัวอักษรและบรรทัดสุดท้ายอาจยังเขียนไม่จบ ⇒ ตัวเลขที่ได้จะคลาดไป 1–2 ตัวแบบหาสาเหตุไม่ได้
    ```bash
    ... --collect-only -q <files> | grep '::' | sed 's/::.*//' | sed 's#.*/##' | sort | uniq -c
    ```
    แล้ว **assert ว่าจำนวนที่ collect ได้ == จำนวนที่ passed** (รอบนี้ 203 == 203, F=0, E=0 ⇒ ไม่มี skip แฝง)
  · 📌 **เมื่อไร "ด่าน delta" พอ และเมื่อไรต้องรันทั้งชุด:** delta **พอ** เมื่อช่วง base→head แตะไฟล์ production จำกัดและ enumerate ผู้บริโภคได้ครบ · **ต้องรันทั้งชุด** เมื่อมีการเปลี่ยนสคีมา/`init_db`/`conftest`/fixture ที่ใช้ร่วมกัน หรือเมื่อ enumerate ไม่ครบ — **"ไม่แน่ใจ" = รันทั้งชุด**
- **Date Added:** 2026-09-29

### 🟢 ด่านที่ "ผ่าน" ทั้งที่ไม่ได้รัน — `cmd | tail` คืน exit code ของ `tail` และ background command รับ cwd ต่อจาก session
- **Context/Problem:** สั่งรันเทสต์เดี่ยวเป็น background task แล้วได้ผลลัพธ์ `open /…/frontend/docker-compose.test.yml: no such file or directory` ต่อท้ายด้วย **`[exited with code 0]`** ⇒ อ่านผ่าน ๆ คือ "ผ่าน" · ของจริงคือ **เทสต์ไม่เคยรันเลย** แต่รายงานว่าสำเร็จ
- **Root Cause:** สองอย่างซ้อนกัน ① **cwd ของ background command = cwd ปัจจุบันของ session** ซึ่งเปลี่ยนไปเป็น `frontend/` ได้จากคำสั่งก่อนหน้า (`cd frontend && …`) ⇒ `docker-compose.test.yml` อยู่ที่ราก repo จึงหาไม่เจอ ② **exit code ของ pipeline = ของคำสั่งสุดท้าย** ⇒ `docker compose … | grep … | tail -40` คืน 0 ของ `tail` เสมอ ไม่ว่า `docker compose` จะล้มหรือหาไฟล์ไม่เจอ
- **Correct Pattern/Solution:**
  ```bash
  cd /abs/path/to/repo && set -o pipefail && cmd 2>&1 | grep -vE '^(INFO|DEBUG)' | tail -60
  ```
  · **`cd` เป็น absolute path ทุกครั้งในคำสั่งที่รันเป็น background** อย่าพึ่ง cwd ของ session — มันเปลี่ยนได้กลางบทสนทนา และคำสั่งที่รันไปแล้วไม่ย้อนกลับมาแก้
  · **`set -o pipefail`** ทำให้ pipeline คืน status ที่ไม่ใช่ 0 ถ้ามีขั้นใดล้ม · ทางเลือกที่ไม่ต้อง pipefail: อ่าน `${PIPESTATUS[0]}`
  · ★ **ด่านที่รายงานผลต้องมีหลักฐานว่า "รันจริง" ไม่ใช่แค่ "exit 0"** — ข้อความที่พิสูจน์ได้คือบรรทัดสรุปของตัวรันเอง (`24 passed in 172.66s`) หรือจำนวนจาก `--collect-only` ⇒ **ถ้า output ไม่มีบรรทัดสรุป ให้ถือว่าไม่ผ่าน ไม่ใช่ผ่าน**
- **Date Added:** 2026-09-29

### ⏱️ pydantic v2 เขียน UTC เป็น `…Z` แต่ `.isoformat()` เขียน `…+00:00` — เทียบ "สตริง" จะพังทั้งที่เป็นเวลาเดียวกัน
- **Context/Problem:** เทสต์ยืนยันว่า `created_at` ที่ API คืนมาตรงกับค่าใน DB (`assert body["created_at"] == row["created_at"].isoformat()`) ⇒ ล้มด้วย `'2026-09-29T08:23:32.590780Z' == '2026-09-29T08:23:32.590780+00:00'` · ตัวเลขเวลาตรงกันทุกหลัก ต่างแค่ตัวแทนของ timezone
- **Root Cause:** pydantic v2 serialize `datetime` ที่เป็น UTC ด้วย suffix **`Z`** ส่วน `datetime.isoformat()` ของ Python ให้ **`+00:00`** ⇒ สตริงไม่เท่ากันแม้เป็น instant เดียวกันเป๊ะ · **ไม่ใช่บั๊กของโปรดักต์** แต่เป็นเทสต์ที่ผูกกับ "รูปแบบ" แทนที่จะผูกกับ "ความหมาย"
- **Correct Pattern/Solution:** แปลงเป็น `datetime` แล้วเทียบ instant · เขียน helper ไว้ใช้ซ้ำ
  ```python
  from datetime import datetime
  def _as_utc(iso: str) -> datetime:            # pydantic v2 → aware datetime
      return datetime.fromisoformat(iso.replace("Z", "+00:00"))
  assert _as_utc(body["created_at"]) == row["created_at"]
  ```
  · `datetime.fromisoformat` อ่าน `Z` ได้ตั้งแต่ Python 3.11 แต่ `replace` ไว้ก็ไม่เสียหาย และทำให้ไม่ผูกกับเวอร์ชัน Python ที่รันเทสต์
  · ⚠️ **อย่าแก้ด้วยการ `replace("Z", "+00:00")` ที่สตริงทั้งสองฝั่งแล้วเทียบกัน** — ได้ผลเหมือนกันแต่วิธีนั้น "ปรับให้สตริงเท่ากัน" ไม่ได้พิสูจน์ว่าเป็น instant เดียวกัน
  · 📌 **เจตนาของเทสต์ต้องคงอยู่** — เทสต์ตัวนี้มีไว้พิสูจน์ว่า `created_at` มาจาก `RETURNING` ของ DB ไม่ใช่ `datetime.now()` ที่ router สร้างเอง ⇒ เทียบ instant **ไม่ได้ทำให้เจตนาอ่อนลง** · ใส่ f-string ของทั้งสองค่าลง AssertionError ด้วย เพื่อให้อ่านออกทันทีว่าเป็นเรื่องรูปแบบหรือเรื่องค่าจริง
- **Date Added:** 2026-09-29

### 🧱 ขยาย union type = สัญญาที่แตกทุกผู้บริโภคที่ "รู้แคบกว่า" — ตั้งชื่อแนวคิดที่แคบกว่า อย่าไปคลายสัญญาของผู้บริโภค
- **Context/Problem:** เพิ่ม `'suggestion'` เข้า `BoardType = 'vote' | 'talk'` ⇒ `vue-tsc` ล้มที่ `ApproveBoardModal.vue` — `Type 'BoardType' is not assignable to type '"vote" | "talk"'` ที่ `approveToPublic({ board_type: boardType.value })` ทั้งที่บรรทัดนั้นไม่ได้ถูกแก้เลย
- **Root Cause:** `BoardType` เป็น **ยูเนียนกลางที่ทุกคนใช้ร่วม** ⇒ พอขยาย มันกลายเป็น "กว้างกว่า" สัญญาของผู้บริโภคบางรายโดยอัตโนมัติ · modal อนุมัติของสภา **สร้างได้แค่ vote/talk** (ตรงกับ `PUBLIC_BOARD_TYPES` ฝั่ง backend ที่ตั้งใจไม่รวม `'suggestion'`) ⇒ คำตอบที่ถูกคือ "แคบกว่านี้" ไม่ใช่ "แก้ให้ผ่าน"
- **Correct Pattern/Solution:** **ตั้งชื่อยูเนียนที่แคบกว่าเป็น type ของตัวเอง** แล้วให้ทั้งสองฝั่งอ้างชื่อนั้น
  ```ts
  export type BoardType = 'vote' | 'talk' | 'suggestion'
  // ชนิด board ที่สายอนุมัติของสภา สร้างได้ — ไม่รวม 'suggestion' โดยเจตนา (ตรงกับ PUBLIC_BOARD_TYPES)
  export type PublicBoardType = 'vote' | 'talk'
  ```
  · แล้ว `ApproveToPublicPayload.board_type: PublicBoardType` · `computed<PublicBoardType>` ใน modal ⇒ **type error หายเพราะสัญญาตรงกันจริง ไม่ใช่เพราะปิดปาก compiler**
  · ⛔ **ทางที่ห้าม:** cast `as 'vote' | 'talk'`, ขยาย `ApproveToPublicPayload` ให้รับ `'suggestion'` (จะยิงไปให้ endpoint ที่ไม่รับ) หรือ `@ts-expect-error` — **ทุกทางทำให้ compiler เงียบ แต่ไม่ทำให้สัญญาตรง**
  · 📌 **สัญญาณว่าเจอของจริง:** type error โผล่ที่ไฟล์ที่เราไม่ได้แก้ ⇒ ก่อนแก้ ให้ถามว่า *"ผู้บริโภครายนี้ควรรู้จักค่ามากขึ้นจริงไหม"* — ถ้าไม่ นั่นคือ type ใหม่ ไม่ใช่ cast ใหม่ · และการแยก type ทำให้กับดักฝั่ง backend ปรากฏตอน compile (`PUBLIC_BOARD_TYPES` มีคู่ตรงข้ามที่ตรวจได้แล้ว)
- **Date Added:** 2026-09-29

### 📏 ค่าใหม่ที่ "พอดีความกว้างเดิม" = ไม่พอ — และ `CHECK` ที่ลิสต์ค่าตายตัวต้อง `DROP`+`ADD` ไม่ใช่แค่แก้ comment
- **Context/Problem:** เพิ่ม `board_type = 'suggestion'` ให้ PIRI Boards · คอลัมน์เป็น `VARCHAR(10)` และ `'suggestion'` **ยาว 10 ตัวอักษรพอดี** ⇒ ดูเหมือน "ใส่ได้" แต่เหลือ headroom **0** · และมี `chk_piri_boards_type CHECK (board_type IN ('talk','vote'))` อยู่ ⇒ ถ้าแก้แค่ comment/ขนาดคอลัมน์ INSERT จะล้มด้วย CheckViolation
- **Root Cause:** สองด่านที่แยกกันและต้องผ่านทั้งคู่ — **ความกว้างคอลัมน์** (ข้อมูลไหลผ่านได้ไหม) และ **CHECK constraint** (ค่าถูกอนุญาตไหม) · ค่าที่พอดีความกว้างเดิมทำให้ด่านแรก "ดูผ่าน" ทั้งที่ความจริงคือไม่มีที่ให้ค่าใดโตอีกเลย · และ CHECK ที่ลิสต์ค่าตายตัวเป็น **ข้อผูกมัดที่ต้องแก้ในฐานข้อมูลจริง** — แก้ comment หรือ `init_db.py` อย่างเดียวไม่พอ เพราะสคีมาที่มีอยู่แล้วไม่เปลี่ยนตาม
- **Correct Pattern/Solution:** migration เดียว แก้ทั้งสองอย่าง เรียงตามลำดับที่ปลอดภัย
  ```sql
  ALTER TABLE piri_boards DROP CONSTRAINT IF EXISTS chk_piri_boards_type;      -- ① ถอดก่อน
  ALTER TABLE piri_boards ALTER COLUMN board_type TYPE VARCHAR(20);            -- ② ขยาย + เผื่อที่
  ALTER TABLE piri_boards ADD CONSTRAINT chk_piri_boards_type
      CHECK (board_type IN ('talk','vote','suggestion'));                      -- ③ ใส่ใหม่
  ```
  · **`DROP CONSTRAINT IF EXISTS` ต้องมาก่อน `ADD`** และต้องมี `IF EXISTS` ไม่งั้นรันรอบสองพัง (เทสต์ idempotency จับได้)
  · **เพิ่มความกว้างเผื่อไว้ ไม่ใช่ให้พอดี** — `VARCHAR(20)` ไม่ได้มีต้นทุนอะไรบน Postgres (เก็บตามความยาวจริง) ⇒ **"พอดีเป๊ะ" คือสัญญาณให้ขยาย ไม่ใช่สัญญาณว่าไม่ต้องแก้**
  · **mirror `init_db.py` ให้ตรงกับสคีมาหลัง migration** (ทั้งความกว้างและรายการใน CHECK) ไม่งั้น DB ใหม่กับ DB เก่าจะต่างกัน
  · ⚠️ **เทสต์ migration ต้องถอยสคีมากลับเป็นเวอร์ชันเก่าจริงก่อน** (`DROP` + `ALTER` กลับเป็น `VARCHAR(10)` + CHECK 2 ค่า) แล้วค่อยเรียก `upgrade()` **สองครั้ง** ⇒ พิสูจน์ทั้ง "แก้สคีมาเก่าได้จริง" และ "idempotent" · **และต้องคืนสคีมาเป็นเวอร์ชันล่าสุดตอนจบ** ไม่งั้นเทสต์ไฟล์ถัดไปพังด้วยเหตุผลผิด (บทเรียน §20.18)
  · 📌 **ต่างจาก polymorphic ที่เลือก "ไม่มี CHECK" โดยเจตนา** — ตารางที่ค่ามีจำกัดและเป็นของระบบเองควรมี CHECK (กันข้อมูลเพี้ยน) · ตารางที่ค่าจะโตจากฟีเจอร์อนาคต (`entity_type` ที่จะรับ `'event'`) ไม่ควรมี ⇒ **ตัดสินที่ "ใครเป็นคนกำหนดค่า — ระบบหรือฟีเจอร์ถัดไป"**
- **Date Added:** 2026-09-29

### 🔍 ตัวตรวจ "ยังรันอยู่ไหม" ที่ exit code 1 แปลว่า "ถามไม่ได้" ไม่ใช่ "ตายแล้ว" — `kill -0` ใน sandbox คืน false completion
- **Context/Problem:** รอ suite ทั้งชุดจบด้วย `until ! kill -0 1522949 2>/dev/null; do sleep 15; done` ⇒ **พิมพ์ว่าเสร็จทันที** ทั้งที่ pytest เพิ่งรันไปได้ ~10 นาทีจาก ~65 นาที ⇒ ถ้าเชื่อ จะ commit ไปทั้งที่ด่านยังไม่ผ่าน (และเข้าไปแก้ไฟล์ใต้ `backend/` ที่ bind-mount อยู่ = พังทั้งรอบ)
- **Root Cause:** `kill -0` **ต้องมีสิทธิ์ส่งสัญญาณ** ไม่ใช่แค่มีโปรเซส · ใน sandbox นี้เรียกแล้วได้ `kill: (1522949) - Operation not permitted` **exit 1** สำหรับโปรเซสที่ยังมีชีวิตและเป็นเจ้าของเดียวกัน ⇒ **exit 1 มีสองความหมายที่แยกไม่ออก** ("ไม่มีโปรเซส" กับ "มีแต่ถามไม่ได้") และ `until ! X` ตีความครั้งแรกเป็น "จบแล้ว" ⇒ **ทิศทางของความผิดพลาดคือรายงานว่า "เสร็จ" ขณะที่งานยังวิ่ง** ซึ่งอันตรายกว่าเงียบเฉย ๆ
- **Correct Pattern/Solution:** ใช้ตัวตรวจที่ **ความหมายของความล้มเหลวไม่กำกวม** — ตรวจ *การมีอยู่* ไม่ใช่ *สิทธิ์*
  ```bash
  until ! test -d /proc/1522949; do sleep 20; done; echo "FINISHED"; date -Is
  ```
  · เทียบข้างกันบน PID เดียวกัน (ยืนยันแล้ว): `kill -0` → **exit 1 "Operation not permitted"** · `ps -p 1522949 -o pid=` → **exit 0** · `test -d /proc/1522949` → **จริง** · `pgrep -f 'python -m pytest'` → **เจอ**
  · 📌 **`/proc/<pid>` และ `ps -p` ต่างจาก `kill -0` ตรงที่มันตอบคำถาม "มีอยู่ไหม" ล้วน ๆ ไม่ปนเรื่องสิทธิ์** ⇒ ใช้เป็นค่าเริ่มต้นสำหรับรอโปรเซสในสภาพแวดล้อมที่ไม่รู้ข้อจำกัด
  · ⚠️ **และถึงตัวตรวจถูก ก็ยังต้องอ่าน "บรรทัดสรุปของตัวรันเอง"** — การที่โปรเซสหายไปบอกแค่ว่าจบ **ไม่ได้บอกว่าผ่าน** (บทเรียน `cmd | tail` ข้างบนคือคู่กันของข้อนี้)
- **Date Added:** 2026-09-29

### 🎯 เป้าเทสต์ที่คำนวณจาก "ผลรันครั้งก่อน + ของใหม่" เปื่อยทันทีที่มี PR อื่น merge คั่น — หักจาก `--collect-only` ของทรีปัจจุบันเสมอ
- **Context/Problem:** ตั้งเป้าด่านก่อน commit ว่า `621 passed` (597 เดิม + 24 ของงานนี้) · รันจริงได้ **624** ⇒ ถ้ายึดเป้าเดิม ตัวเลขที่ "เกินมา 3" จะถูกอ่านเป็นความผิดปกติ และถ้าเผลอเขียนเป้าเป็น 624 ไว้ก่อนก็จะอ่าน 621 ว่า **"ขาด 3 = มีเทสต์ถูก skip เงียบ ๆ"** ทั้งสองทางเป็น false alarm ที่ทำให้เสียเวลาตามหาผี
- **Root Cause:** `597` วัดบนทรีที่ฐาน **`023a09b` ซึ่งอยู่ก่อน `#51`** ⇒ **ไม่รวมเทสต์ที่ `#51` เพิ่ม** ภายหลัง (`test_T20a/T20b/T20c` ใน `test_push_outbox.py`) · สูตร "ผลรันครั้งก่อน + ของที่เราเพิ่ม" **สมมติเงียบ ๆ ว่าไม่มีอะไรอย่างอื่นลงระหว่างนั้น** ซึ่งผิดทุกครั้งที่มี PR อื่น merge คั่น — และจุดที่พลาดคือ **เป้าถูกจำไว้โดยไม่มี commit กำกับ** ⇒ พอจะตรวจก็ไม่รู้ว่าไปเทียบกับอะไร
- **Correct Pattern/Solution:** หักเป้าจาก **ทรีที่จะรันจริง** ไม่ใช่จากความจำ แล้วให้ตัวรันพิสูจน์ตัวเอง
  ```bash
  cd /abs/repo && docker compose -f docker-compose.test.yml run --rm test_runner \
    sh -c "python -m pytest --collect-only -q /app/tests/ | tail -1"     # ← เป้าที่ถูกของทรีนี้
  ```
  · **เขียนกำกับ commit ไว้ข้างทุกตัวเลขที่อ้างอิง** (`597 @ 023a09b`) ⇒ ตรวจย้อนได้ทันทีว่ามีอะไร merge คั่นหรือยัง
  · **`def test_` ไม่เท่ากับจำนวนที่เก็บได้** — `parametrize` ขยายเพิ่ม (งานนี้ 18 `def test_` → **24** collected · C1/C2 60 → 65) ⇒ **นับจาก `--collect-only` เท่านั้น**
  · ★ **assert ว่า `collected == passed`** ⇒ ปิดช่อง "มีเทสต์ถูก skip แล้วตัวเลขยังสวย" ซึ่งเป็นเหตุผลเดียวที่ตัวเลขเป้าจะมีค่า
  · 📌 **ตัวเลขเป้าที่ "เกิน" หรือ "ขาด" ไม่ใช่หลักฐานเสมอไป** — ก่อนสรุปว่ามีอะไรผิด ให้ถามก่อนว่า *"เป้านี้ผูกกับ commit ไหน"* · **ด่านที่ดีต้องบอกได้ว่ามันเทียบกับอะไร ไม่ใช่แค่บอกว่าผ่าน**
- **Date Added:** 2026-09-29

### 🔗 สัญญาที่อยู่คนละภาษา ต้องอยู่ใน "โมดูลที่ประกาศตัวว่าเป็นสัญญา" — และตรึงสองฝั่งด้วยตารางที่เทียบกันได้ตรง ๆ
- **Context/Problem:** A4 Deep Link — ปลายทางเมื่อผู้ใช้กด notification ถูกตัดสิน **สองที่คนละภาษา**: `backend/services/push_service.py::_deep_link_url()` (สร้าง `data.url` ให้ FCM/OS เปิด) และ `NotificationCenter.vue::go()` (กดในแอพ) · ตรรกะฝั่งในแอพเดิมฝังอยู่ใน `go()` ของ SFC ⇒ docstring ฝั่ง backend ต้องชี้มาที่ไฟล์ `.vue` และไม่มีเทสต์ฝั่ง frontend ที่เทียบกับตารางของ backend ได้
- **Root Cause:** สองภาษา "ตกลงกัน" ผ่านข้อความในคอมเมนต์ ไม่มีอะไรบังคับ ⇒ ถ้าไม่ตรงกัน **ทั้งสองฝั่ง "ดูถูก" แยกกัน** ไม่มี error ไม่มี log · อาการที่ผู้ใช้เห็นคือ notification อันเดียวกันให้ผลต่างกัน (กดในแอปไปที่หนึ่ง กดจาก push ไปอีกที่หนึ่ง) ซึ่งไม่มีใครบ่นเป็นคำที่หาสาเหตุได้ · และการวางสัญญาไว้ใน SFC ทำให้ (ก) เทสต์ยากเพราะต้อง mount component (ข) คนอ่านฝั่ง backend ต้องเปิดไฟล์ Vue
- **Correct Pattern/Solution:** ยกการตัดสินออกเป็น **ฟังก์ชันบริสุทธิ์ในโมดูลที่ชื่อบอกว่ามันคือสัญญา** แล้วแยก "ผลข้างเคียง" ออกจาก "ปลายทาง"
  ```ts
  // router/deepLink.ts — โมดูลนี้คือสัญญาร่วมกับ push_service._deep_link_url()
  export function deepLinkTarget(n: DeepLinkSource): DeepLinkTarget   // {name,params} | null
  ```
  · `go()` ใน SFC เหลือแค่ **ผลข้างเคียง** (mark-read) แล้วเรียก `deepLinkTarget(n)` ไป navigate ⇒ SFC กับ pure function แยกกันเทสต์ได้อิสระ
  · **ตรึงสองฝั่งด้วยตารางเดียวกันที่แสดงเป็น "path สตริง" ไม่ใช่ชื่อ route** ⇒ เทียบข้ามภาษาได้ตรง ๆ
  ```py
  _DEEP_LINK_CASES = [("report_new", "report", "piri_board_report", 9, 3, "/app/boards/reports"), …]
  ```
  ```ts
  function targetToPath(t: DeepLinkTarget): string   // แปลง route → สตริงเดียวกับที่ backend สร้าง
  ```
  ฝั่ง backend assert สตริงนั้นตรง ๆ · ฝั่ง frontend แปลง route กลับเป็นสตริงแล้ว assert สตริงเดียวกัน
  · ⚠️ **ลำดับในการตัดสินมีความหมาย** — `report_new` ต้องชนะ `board_id` (ถ้าสลับจะได้ `/app/boards/3` ซึ่ง "ดูสมเหตุสมผล" เพราะเป็นบอร์ดที่ถูกรายงานนั่นแหละ แต่ผิดเจตนา) ⇒ มีเทสต์เฉพาะข้อนี้ทั้งสองฝั่ง (`T21b` / `D4`) และคอมเมนต์ห้ามสลับลำดับกำกับไว้ที่ตัวโค้ด
  · **เพิ่มชนิดใหม่ = เพิ่มสองที่** ⇒ ใช้ `Record<NotificationGroup, true>` เป็นด่าน **compile-time** (ลืม = ไม่คอมไพล์ ไม่ใช่ตกตอนรันบน staging)
  · 📌 `entity_id` เป็น NULL ต้อง **ห้าม** เรนเดอร์ `/app/issues/null` — ตกไปใช้ `board_id` ก่อน แล้วจึงเป็น `null` (เทสต์ `D6`/`T21d`) · และเทียบด้วย `!= null` ไม่ใช่ truthy (`board_id = 0` ต้องไม่ถูกมองว่า "ไม่มี" — เทสต์ `D9`)
- **Date Added:** 2026-09-29

### 🩺 ข้อมูลวินิจฉัยที่ "หายไปหนึ่งชั้น" ทำให้แก้บั๊กไม่ได้ — ตรึงตัวข้อมูลเอง ไม่ใช่ตรึงพฤติกรรมที่พึ่งมัน
- **Context/Problem:** บั๊ก #32 — notification ชี้บอร์ดที่ถูกซ่อนภายหลัง กดแล้วได้ 404 · หน้าเดิม **แยกไม่ออก** ระหว่าง 404 (ถูกซ่อน/ลบ → ควรพากลับหน้ารายการ + บอกสาเหตุ) กับ 500 (เซิร์ฟเวอร์พัง → ควรอยู่หน้าเดิม + ปุ่มลองใหม่) ⇒ ทางแก้ที่ปลายทางจึงมีได้แค่ "เด้งกลับหน้ารวม" ซึ่ง **ผิดสำหรับ 500** · สาเหตุคือ `api.ts` โยน `new Error(detail)` ล้วน — **status หายตั้งแต่ชั้นล่างสุด**
- **Root Cause:** interceptor **ทิ้งข้อมูลวินิจฉัย** ⇒ ทุกชั้นที่อยู่เหนือขึ้นไปสูญเสียความสามารถในการแยกแยะ โดยไม่มีใครรู้ว่าสูญเสีย · โค้ดที่เขียนว่า `catch (e) { Swal.fire(e.message) }` **ดู "จัดการครบแล้ว"** ทั้งที่มันแยกสถานการณ์ไม่ได้เลย
- **Correct Pattern/Solution:** แนบ status กลับไปกับ Error — **เป็นส่วนเพิ่ม ไม่ใช่การเปลี่ยนสัญญา**
  ```ts
  export interface ApiError extends Error { status?: number }
  const apiError = new Error(detail) as ApiError
  apiError.status = error.response.status
  ```
  · ยัง `instanceof Error` จริง และ `.message` เหมือนเดิม ⇒ **ผู้เรียกเดิมทั้งหมดไม่ต้องแก้แม้บรรทัดเดียว**
  · ⚠️ **"ไม่มี response" (เน็ตหลุด/timeout) ต้องเป็น `undefined` ไม่ใช่ `0`/`-1`** — "ไม่มีข้อมูล" ต้องต่างจาก "มีข้อมูลว่าเป็น 0" ไม่งั้นโค้ดที่เขียน `if (!err.status)` จะตีความผิด
  · ⚠️ **เทสต์ต้องตรึง "ตัวข้อมูล" ไม่ใช่ "พฤติกรรมที่พึ่งมัน"** — ถ้าเทสต์แค่ "ผู้ใช้ถูกพากลับหน้ารายการ" แล้ววันหนึ่งมีคนเปลี่ยนชื่อ property เป็น `httpStatus` การพากลับจะหยุดทำงาน **แต่เทสต์ยังผ่าน** (เพราะ `as ApiError` ไม่มีอะไรผูกชื่อ property ไว้) ⇒ ต้องมีเทสต์ที่ assert `status === 404` และ `hasOwnProperty('status')` ผ่าน **adapter จริง** (แทน `api.defaults.adapter` ให้ reject ด้วย object ที่มี `.response`) ไม่ใช่เรียก handler ของ interceptor ตรง ๆ ซึ่งเป็นโครงสร้างภายในที่เปลี่ยนได้
  · 🚩 **สัญญาณของคลาสนี้:** *"แก้บั๊กด้วยบรรทัดเดียว"* และบรรทัดนั้น **ถ้าลบออก ทุกอย่างยังคอมไพล์และเทสต์อื่นยังผ่านทั้งหมด** ⇒ ต้องมีเทสต์ที่ fail เมื่อลบบรรทัดนั้นโดยเฉพาะ — ไม่งั้น "การทำความสะอาด" ในอนาคตจะเอากลับมาพังเงียบ ๆ
- **Date Added:** 2026-09-29

### 🚪 ค่าที่มาจาก URL และถูกใช้ "หลังล็อกอินสำเร็จ" ต้องถูกปฏิเสธ ไม่ใช่ถูกซ่อม
- **Context/Problem:** A4 — deep link ที่เปิดตอนยังไม่ล็อกอิน/token หมดอายุถูกจำไว้ที่ `?redirect=` แล้วนำไป `router.replace(target)` **ทันทีหลังใส่รหัสผ่านถูก** ⇒ `/login?redirect=https://evil.example` กลายเป็นฟิชชิงที่เชื่อถือได้มาก เพราะต้นทางเป็นโดเมนโรงเรียนจริงและเหยื่อเพิ่งพิสูจน์ตัวเองด้วยรหัสผ่าน
- **Root Cause:** ด่าน "ต้องขึ้นต้นด้วย `/`" **ไม่พอ** และ payload ที่ผ่านด่านนั้นได้มีอยู่จริงหลายแบบ: เบราว์เซอร์ตีความ `\` เป็น `/` ⇒ `/\evil.example` และ `\\evil.example` ผ่านแล้วออกนอกแอพ · `//evil.example` เป็น protocol-relative ⇒ ก็ผ่าน "ขึ้นต้นด้วย /" · ⇒ **ต้องรู้ payload แต่ละแบบจึงจะกันได้** และการพยายาม "ซ่อม" (strip scheme, ตัด backslash) สร้างช่องใหม่ที่ต้องคิดต่อไม่จบ
- **Correct Pattern/Solution:** **ปฏิเสธที่ "รูปของค่า" ด้วย allowlist คำนำหน้าแคบ ๆ** ไม่ใช่พยายามตีความ
  ```ts
  if (!value.startsWith('/app/')) return null   // allowlist แคบ — ไม่ใช่ startsWith('/')
  if (value.includes('\\')) return null          // backslash bypass (เบราว์เซอร์ตีความเป็น /)
  ```
  · **"ปฏิเสธ" ไม่ใช่ "ซ่อม"** ⇒ คืน `null` แล้วให้หน้า Login ไปหน้าแรกตามบทบาท ซึ่งเป็นพฤติกรรมเดิมที่ปลอดภัยอยู่แล้ว
  · คำนำหน้าต้องแคบ: `/login`, `/`, `/app` (ไม่มีสแลชปิด), `/application/evil`, `' /app/boards/5'` (มีช่องว่างนำ) ต้องตกทั้งหมด
  · ⚠️ **ค่าจาก URL รูปร่างเป็นอะไรก็ได้** — query ซ้ำทำให้เป็น array, อาจเป็น number/object ⇒ **ห้าม throw** เพราะ throw ที่นี่ = หน้า Login พังทั้งหน้าหลังผู้ใช้ใส่รหัสผ่านถูกแล้ว (worst case)
  · เทสต์ต้องมีทั้ง **payload โจมตีจริง** (absolute, http, protocol-relative, backslash เดี่ยว/คู่, `javascript:`, `data:`) และ **คุณสมบัติเชิงโครงสร้าง** (ผลลัพธ์ที่ผ่านต้องขึ้นต้น `/` เสมอ ไม่ขึ้นต้น `//` ไม่ match scheme) เพื่อกันเคสที่ยังไม่มีใครคิดถึง
  · 📌 **`safeRedirect` อยู่คนละไฟล์กับ guard** โดยเจตนา — guard แค่ *ส่งต่อ* ค่า (`to.fullPath`) ไม่ได้แปลว่าค่าปลอดภัย และคอมเมนต์ต้องเขียนกำกับไว้ทั้งสองที่ ไม่งั้นวันหน้าจะมีคนคิดว่า guard กรองให้แล้ว
- **Date Added:** 2026-09-29

### 🔁 คู่ "ผู้ผลิต–ผู้บริโภค" ที่ผูกกันผ่าน URL ไม่ได้ผูกกันด้วย type — เทสต์ต้องส่งค่าที่ผลิตจริงกลับเข้าผู้บริโภค
- **Context/Problem:** `goUnavailable(router, 'board')` ผลิต `?unavailable=board` แล้ว `readUnavailable()` อ่านค่านั้นกลับมาทำ Swal · ทั้งคู่ใช้ `UnavailableKind` ร่วมกัน ⇒ **ดูเหมือน type รับประกันให้แล้ว**
- **Root Cause:** type รับประกันแค่ *ชนิดของตัวแปร* **ไม่ได้ผูกเส้นทางข้อมูล** — ผู้ผลิตเขียน `query: { unavailable: kind }` ด้วย literal string และผู้บริโภคอ่าน `to.query['unavailable']` ด้วย literal string **ชื่อคีย์ไม่ถูกตรวจโดยใครเลย** ⇒ เปลี่ยนชื่อฝั่งใดฝั่งหนึ่ง อีกฝั่งยังคอมไพล์ผ่าน และอาการคือ "Swal ไม่ขึ้น" ซึ่ง **แยกไม่ออกจาก "ยังไม่ deploy"** หรือ "เน็ตช้า"
- **Correct Pattern/Solution:** เทสต์ที่ **บังคับให้ครบวง โดยอ่านค่าจากสิ่งที่ผู้ผลิตสร้างจริง** ไม่ใช่จากตัวแปรที่ป้อนเข้า
  ```ts
  const { replace, router } = fakeRouter()
  await goUnavailable(router, kind)
  const to = replace.mock.calls[0][0]
  expect(readUnavailable(to.query[UNAVAILABLE_QUERY])).toBe(kind)   // ← อ่านจาก query ที่ผลิตจริง
  ```
  · ⚠️ **ค่าที่มาจาก URL ต้องกรองก่อนใช้ ไม่ใช่ cast** — `?unavailable=<มั่ว>` cast แล้วเอาไปเข้า `Record` จะได้ `undefined` ไปแสดงเป็นข้อความให้ผู้ใช้เห็น ⇒ `readUnavailable` return `null` สำหรับค่าที่ไม่รู้จัก
  · เพิ่มชนิดใหม่: `Record<UnavailableKind, true>` เป็นด่าน **compile-time** + ลูปเทสต์อ่านจาก object นั้น ⇒ ครอบชนิดใหม่อัตโนมัติ
  · 📌 **รูปแบบนี้ใช้ได้ทุกที่ที่สองฝั่งสื่อสารผ่านสตริง** — URL query, `localStorage` key, ชื่อ `postMessage`/event, ชื่อ channel ของ `pg_notify` ⇒ **ถ้าคอมไพเลอร์ไม่รู้จักช่องทางนั้น ก็ต้องมีเทสต์ที่เดินผ่านช่องทางนั้นจริง** ไม่ใช่เทสต์สองฝั่งแยกกัน
- **Date Added:** 2026-09-29

### 🧹 `expect(value, message)` ของ vitest ถูก oxlint ตีเป็น error — และวิธี assert ที่ให้ข้อความ fail ดีกว่า
- **Context/Problem:** `npm run lint` ล้มด้วย `eslint-plugin-jest(valid-expect): Expect takes at most 1 argument` 2 จุดในสเปกใหม่ ทั้งที่ vitest รองรับ argument ที่สองเป็นข้อความ fail (ของ jest ก็รองรับ) · และ `npm run type-check` **ผ่าน** ⇒ เจอตอนรัน `lint` เท่านั้น
- **Root Cause:** oxlint เปิด rule ของ `eslint-plugin-jest` ซึ่ง **ไม่ได้แยก vitest ออกจาก jest** ⇒ รูปที่ vitest รองรับถูกมองเป็นความผิด · ด่าน frontend มี 4 ขั้น (`type-check` · `lint` · `test:unit` · `build`) และ **`type-check` ไม่ครอบ `lint`** ⇒ การรันแค่ `type-check` ให้ความรู้สึกว่า "ผ่านแล้ว"
- **Correct Pattern/Solution:** เปลี่ยนเป็นรูปที่ทั้งคู่พอใจ **และได้ข้อความ fail ที่ดีกว่าเดิม**
  ```ts
  // ❌ expect(covered.has(g), `กลุ่ม ${g} ไม่มีเคส`).toBe(true)   ← ข้อความไม่ขึ้นด้วยซ้ำในเทสต์ที่ fail
  // ✅
  const missing = ALL_GROUPS.filter((g) => !covered.has(g))
  expect(missing).toEqual([])        // fail แล้วเห็นทันทีว่า "กลุ่มไหน" หาย
  ```
  · 📌 **assert เป็น "รายการที่ขาด" ดีกว่า assert เป็น boolean ในลูป** — boolean บอกแค่ว่ามีอะไรผิด ไม่บอกว่าอันไหน ⇒ ต้องไปไล่เอง · หลักเดียวกับที่ใช้กับ `test_push_outbox` (assert *ตัวนับ* `stats["gone"]` ไม่ใช่แค่ "ไม่ throw")
  · ⚠️ **แก้ให้ lint ผ่านต้องรักษาความหมายของเทสต์** — ห้ามลบ assert ทิ้งหรือทำให้อ่อนลงเพียงเพื่อให้ผ่าน lint · ถ้าลบไม่ได้จริง ๆ ให้ใช้ `// oxlint-disable-next-line <rule>` **พร้อมเหตุผล** ไม่ใช่ปิดทั้งไฟล์
  · 📌 **ลำดับ gate ฝั่ง frontend ที่ต้องรันครบ:** `npm run type-check && npm run lint && npm run test:unit && npm run build` — สี่ตัวจับคนละคลาส (`lint` จับได้สิ่งที่ `type-check` ไม่เห็น และกลับกัน)
- **Date Added:** 2026-09-29

### 🌐 "ไฟล์เป็น UTF-8" ไม่เท่ากับ "เบราว์เซอร์อ่านเป็น UTF-8" — ต้องมี *คำประกาศ* ไม่ใช่แค่ไบต์ที่ถูก
- **Context/Problem:** รายงาน HTML 3 ไฟล์ใน `~/reports` แสดงข้อความไทยเป็นตัวขยะทั้งหน้า ทั้งที่ **ไบต์ในไฟล์เป็น UTF-8 ถูกต้องทุกไบต์** (`open(f, encoding="utf-8").read()` ผ่าน ไม่มี `U+FFFD` แม้ตัวเดียว)
- **Root Cause:** การตัดสิน encoding ของเบราว์เซอร์ไล่ตามลำดับ **HTTP header → BOM → `<meta charset>` → เดา** · `reports-browser` (`SimpleHTTPRequestHandler`) ตอบ `Content-type: text/html` **ไม่มี `charset=`** และ 3 ไฟล์นั้น **ไม่มี `<meta charset>`** (และไม่มี `<!doctype>`) ⇒ ตกไปขั้น "เดา" ซึ่งใช้ locale ของเครื่อง (windows-1252) ⇒ **UTF-8 ที่ถูกต้องถูกตีความเป็น Latin-1** · ไฟล์อื่นในโฟลเดอร์เดียวกันมี `<meta charset="utf-8">` จึงรอด ⇒ อาการนี้ **ขึ้นกับไฟล์ ไม่ใช่ขึ้นกับเซิร์ฟเวอร์** และ "ดูที่อื่นก็ปกติดี" จึงไม่ใช่หลักฐานว่าปลอดภัย
- **Correct Pattern/Solution:** ทุกไฟล์ HTML ที่เสิร์ฟเองต้องประกาศเอง **ครบชุดนี้** (เรียงตามนี้):
  ```html
  <!doctype html>
  <html lang="th">
  <head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  ```
  · ⚠️ **`<meta charset>` ต้องอยู่ใน 1024 byte แรก** (spec ให้ parser prescan เฉพาะช่วงนั้น) ⇒ วางบนสุดเสมอ อย่าไปไว้ท้าย `<head>` หลังคอมเมนต์ยาว ๆ · ตรวจด้วย offset จริง: `open(f,'rb').read().find(b'<meta charset="utf-8">')` ต้อง `< 1024`
  · ⚠️ **การเติม head ให้ไฟล์เดิมเปลี่ยนพฤติกรรมการ render 2 อย่างที่มองไม่เห็นจากซอร์ส** — `<!doctype html>` พา **quirks mode → standards mode** (box model เปลี่ยน) และ viewport meta เปลี่ยน **มือถือจาก virtual viewport ~980px → ความกว้างจริง** ⇒ **ต้อง render ดูจริง ไม่ใช่แค่ตรวจว่าแท็กครบ**: `document.compatMode === 'CSS1Compat'` + `document.documentElement.scrollWidth <= window.innerWidth` (ห้ามมี scroll แนวนอน) + `document.characterSet === 'UTF-8'` + นับ `input[data-k]` ว่าเท่าเดิม
  · 📌 **แก้ที่ปลายเหตุ (ไฟล์) หรือที่ต้นเหตุ (`server.py`) ก็ได้ — แต่ต้องรู้ว่ากำลังเลือกอะไร:** การใส่ `charset=utf-8` ใน `Content-type` ของ server แก้ได้ทุกไฟล์รวมของในอนาคต **แต่** ต้อง restart container และ **เงียบ ๆ แก้ให้ไฟล์ที่เผลอเป็น encoding อื่น** ⇒ ทางที่ปลอดภัยคือ **ประกาศที่ไฟล์** (ตัวไฟล์พกความจริงของตัวเองไปทุกที่) แล้วค่อยเสริม header เป็นชั้นสอง
  · 📌 **ตรวจหมู่ ไม่ใช่ตรวจไฟล์:** กวาดทั้งโฟลเดอร์ด้วย `grep -ci '<meta charset'` ทุกไฟล์ — 3 ไฟล์ที่พังเป็นรุ่นเดียวกัน (สคริปต์สร้างเดียวกันตัดหัวทิ้ง) ⇒ **ไฟล์ที่ "เพื่อนพัง" มักพังด้วยกัน** อย่าซ่อมเฉพาะที่ผู้ใช้ชี้
- **Date Added:** 2026-09-29

### 🚫 `docker exec` **ที่ไม่มี** `-i` อ่าน stdin ไม่ได้ — ด้านตรงข้ามของ «`-i` กลืนสคริปต์»
- **Context/Problem:** `docker exec $DB pg_restore --list < dump.pgdump` ⇒ `pg_restore: error: input file is too short (read 0, expected 5)` **ทั้งที่ไฟล์สำรองขนาดถูกต้อง (2.6 MB)** ⇒ อ่านว่ากันว่า "ไฟล์สำรองเสีย" แล้วเกือบไปทำสำรองใหม่ทิ้งของดี
- **Root Cause:** `docker exec` ต่อ stdin ของ client **เฉพาะเมื่อสั่ง `-i`** ⇒ ถ้าไม่มี `-i` shell redirect `< dump` ไปเข้า stdin ของ docker ฝั่ง host ที่ **ไม่มีใครอ่าน** ⇒ ปลายทางเห็น stdin ปิดทันที = อ่านได้ 0 byte · ⚠️ **เป็นด้านตรงข้ามกับบทเรียน `docker exec -i` กลืนสคริปต์ `bash -s`** (หัวข้อก่อนหน้า) — เครื่องมือเดียวกัน บั๊กคนละทิศ ⇒ **ถ้าจำได้แค่ "อย่าใส่ `-i`" จะเจอบั๊กอีกครึ่งทันที**
- **Correct Pattern/Solution:** เลี่ยง stdin **ทั้งสองทิศ** — ใช้ **ไฟล์ + path** เสมอ:
  ```bash
  docker cp dump.pgdump "$DB:/tmp/d.pgdump"
  docker exec "$DB" pg_restore --list /tmp/d.pgdump | grep -c 'TABLE DATA'
  docker exec "$DB" rm -f /tmp/d.pgdump
  ```
  · 📌 **กฎเดียวที่ครอบทั้งสองบทเรียน:** *`docker exec` ที่พึ่ง stdin เป็นทางส่งข้อมูล = เลือกผิดตั้งแต่ต้น* — `-i` แย่ง stdin ของสคริปต์ที่ห่ออยู่ · ไม่มี `-i` ก็อ่านไม่ได้เลย · ทางที่ปลอดภัยคือ **ไฟล์ + path** เท่านั้น
  · 📌 และ **อย่าด่วนสรุปว่าไฟล์เสียจาก error ของเครื่องมือ** — ตรวจขนาด (`stat -c '%s'`) และ `gzip -t` ก่อนตัดสิน
- **Date Added:** 2026-09-29

### 🏷 ชื่อ container ของ Swarm มี suffix `.1.<taskid>` ⇒ `--filter name=X` **ไม่ match** · และด่าน `set -e` ที่ไม่ตาย = เขียนของเสียทิ้งไว้
- **Context/Problem:** `docker exec pirivoice_production_infra_db psql …` ⇒ `Error response from daemon: No such container: …` และ `docker ps --filter name=pirivoice_production_infra_db` ก็ **ไม่เจออะไร** ทั้งที่ container รันอยู่ · อีกอาการที่มาคู่กัน: สคริปต์สำรอง DB ที่ "มี `set -e` แล้ว" **เขียน dump ขนาด 0 byte ทิ้งไว้** โดยไม่ล้ม
- **Root Cause:** task ของ Swarm ตั้งชื่อ container เป็น `<stack>_<service>.1.<taskid>` ⇒ ชื่อสวย ๆ ที่เราคิดว่าเป็น **ไม่มีอยู่จริง** ⇒ `--filter name=X` เป็น **substring match** จึงต้องเจอ `X.` ไม่ใช่ `X` เป๊ะ ๆ · ส่วนด่านที่ไม่ตายมาจาก **คำสั่งที่ "มี `set -e` ครอบ" แต่ตัวคำสั่งเองคืน exit 0** (เช่น `VAR=$(grep … || true)` แล้วใช้ `$VAR` ที่ว่าง) ⇒ `set -e` ไม่ช่วยอะไร
- **Correct Pattern/Solution:**
  ```bash
  set -euo pipefail
  DB=$(docker ps --format '{{.Names}}' | grep -m1 '^pirivoice_production_infra_db\.') || true
  [ -n "$DB" ] || { echo "❌ หา container ไม่เจอ — หยุด"; exit 1; }   # ★ ด่านต้องตายจริง
  ```
  · ⚠️ **ยืนยัน prefix ก่อนใช้ทุกครั้ง** — บน VPS มี **staging วางข้าง production** ⇒ grep พลาดแล้ว **โดนผิดตัว** ซึ่งอันตรายกว่า error (ไม่มีอะไรฟ้อง)
  · ⚠️ **ด่านที่เขียนแล้วต้อง "ลองให้มันล้ม" หนึ่งครั้ง** — ถ้าไม่เคยเห็นมันตาย จะไม่รู้ว่ามันตายได้ · ของที่ถูกเขียนทับก่อนด่านผ่าน = ต้องตามลบเอง (รอบนี้ทิ้ง dump 0 byte ไว้ 1 ไฟล์)
  · 📌 **หลักทั่วไป:** `set -e` **ไม่ใช่ด่าน** — มันแค่ไม่กลืน non-zero · ด่านจริงคือ **เงื่อนไขที่ `exit 1` เอง** และ **คำสั่งที่ผลิตของต้องอยู่หลังด่าน** ไม่ใช่ก่อน
- **Date Added:** 2026-09-29

### 🔑 อย่าเดา `POSTGRES_USER`/`POSTGRES_DB` ข้าม clone — อ่านจาก env ของ container เอง
- **Context/Problem:** คำสั่งที่ใช้ได้บน staging (`psql -U prsc_admin -d piri_db`) **ล้มบน production** ด้วย `FATAL: role "prsc_admin" does not exist` ⇒ ดูเหมือน production "ตั้งค่าผิด" ทั้งที่แค่คนละค่า
- **Root Cause:** สอง clone บน VPS เดียวกันถูกสร้างต่างรุ่น/ต่าง `.env` ⇒ ชื่อ role กับชื่อฐานข้อมูล **ไม่รับประกันว่าเหมือนกัน** · และการจำค่าจาก clone หนึ่งไปใช้อีก clone หนึ่งเป็นนิสัยที่ "เคยได้ผล" มาก่อน
- **Correct Pattern/Solution:** **อ่านจาก container แล้วใช้ตัวแปร โดยไม่ echo ค่า**:
  ```bash
  PGU=$(docker exec "$DB" printenv POSTGRES_USER)
  PGD=$(docker exec "$DB" printenv POSTGRES_DB)
  docker exec "$DB" psql -U "$PGU" -d "$PGD" -c "SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 3;"
  ```
  · 📌 ได้ทั้ง **ความถูกต้อง** และ **ไม่รั่วความลับ** — หลักเดียวกับกฎเดิม *ห้ามดึง credential ออกมาที่ transcript*: ให้คำสั่งไปรัน **ในที่ที่ credential อยู่แล้ว**
  · ⚠️ อย่าแก้ด้วยการ "ลองผิดลองถูก" (`-U postgres` ฯลฯ) — ถ้า role นั้นมีอยู่จริงและมีสิทธิ์ จะกลายเป็น **การเดารหัสผ่าน** ที่ทั้งช้าและเสี่ยง lock
- **Date Added:** 2026-09-29

### ⚠️ "ค่าที่ดูเหมือนคำตอบ" 2 แบบที่ทำให้สรุปผิด — `0` แถวที่ *ถูกต้อง* และ placeholder ที่ *ดูเหมือนค่าจริง*
- **Context/Problem:** (ก) probe trigger ของ `push_outbox` ได้ **0 แถว** ⇒ เกือบสรุปว่า trigger พัง ทั้งที่มันทำงานถูก · (ข) `scripts/generate_vapid_keys.py` พิมพ์ `VAPID_SUBJECT` ตัวอย่างว่า `mailto:<อีเมลจริงของสภา>` ⇒ ถ้าคัดลอกใส่ `.env` ตรง ๆ `Vapid02.sign()` จะ **โยน exception ทุกครั้งที่ส่ง** = push เงียบทั้งระบบโดยไม่มีอะไรบอก
- **Root Cause:** ทั้งคู่คือ **ค่าที่อ่านแล้ว "ดูสมเหตุสมผล" ทั้งในกรณีสำเร็จและกรณีล้มเหลว**
  · (ก) **migration 019 ทำให้ trigger enqueue เฉพาะผู้ใช้ที่มีอุปกรณ์** ⇒ probe ด้วย `user_id` ที่ไม่มีอุปกรณ์ได้ `0` ซึ่งเป็น *คำตอบที่ถูกต้อง* ไม่ใช่ความผิดปกติ — และ `0` ของ "ยังไม่มีอะไรต้องทำ" หน้าตาเหมือน `0` ของ "พัง" เป๊ะ
  · (ข) placeholder ถูกออกแบบให้ **กลมกลืนกับบริบท** (ขึ้นต้น `mailto:` เหมือนของจริง) ⇒ ผ่านสายตา และผ่านด่านที่ตรวจแต่ *รูปร่าง* (`startswith("mailto:")`) — ตัวที่จับได้คือด่านที่ตรวจ **`'@' in sub`** ซึ่งตรวจ *เนื้อ* ของค่าจริง
- **Correct Pattern/Solution:**
  - ⭐ **ประตูที่เพิ่งเพิ่ม ต้องทดสอบทั้ง "เปิด" และ "ปิด"** — probe ต้องมี **สองทาง**: *ไม่มีอุปกรณ์ → `0`* **และ** *มีอุปกรณ์ → `1`* · ผลรอบเดียว **ไม่ใช่หลักฐาน**
  - ⭐ **ก่อนตีความผล probe ให้ถามก่อนว่า "ถ้ามันทำงานถูก แต่ไม่มีอะไรให้ทำ ผลจะหน้าตาเป็นอย่างไร"** — ถ้าตอบไม่ได้ แปลว่ายังออกแบบ probe ไม่ครบ
  - ⭐ **สคริปต์ที่พิมพ์ "ค่าตัวอย่าง" ต้องทำให้มัน *ใช้ไม่ได้*** — ใส่ `<...>` ให้ชัดว่าเป็นที่ว่าง **และ** มีด่านในสคริปต์เอง (`assert '@' in sub`) ⇒ ด่านนั้นไม่ใช่พิธีกรรม แต่เป็นสิ่งที่กัน push ตายทั้งระบบ
  - 📌 **ด่านที่ตรวจ "รูปร่าง" ต้องเสริมด้วยด่านที่ตรวจ "เนื้อ"** — `startswith("mailto:")` ผ่านทั้งของจริงและ placeholder · `'@' in sub` แยกได้
- **Date Added:** 2026-09-29

### 📱 "คีย์ที่อุปกรณ์ผูกอยู่" คือข้อเท็จจริงของ *อุปกรณ์* ไม่ใช่ของ *บัญชี* — เก็บที่เครื่อง ห้ามล้างตอน login/logout
- **Context/Problem:** หลัง **rotate คีย์ VAPID** เบราว์เซอร์ยังคืน subscription **ตัวเดิมที่ผูกกับคีย์เก่า** ⇒ FCM ปฏิเสธทุก push (403 → ถูกจัดเป็น `permanent` → ทิ้งเงียบ ๆ) ⇒ **การ์ดขึ้น "เปิดอยู่" ตลอดไปโดยไม่มีอะไรมาถึงเลย** — เงียบที่สุดในบรรดาบั๊ก push ทั้งหมด (ไม่มี error ไม่มี log ฝั่งแอพ) และ `PushSubscription` **ไม่มีวิธีอ่านคีย์ที่มันผูกอยู่** เลย
- **Root Cause:** การผูกคีย์เกิดที่ **เบราว์เซอร์** (ต่อ origin) ไม่ใช่ที่บัญชีผู้ใช้ · และ `enablePush()` แบบเดิมใช้ `existing ?? subscribe()` = **เชื่อ subscription เดิมเสมอโดยไม่ดูคีย์** ซึ่งคือตัวบั๊กเอง
- **Correct Pattern/Solution:** เก็บ **fingerprint ของ public key ที่ใช้ตอน subscribe** ไว้ที่เครื่อง (`localStorage` คีย์ `piri_push_key`) แล้วเทียบกับคีย์ที่เซิร์ฟเวอร์ใช้อยู่:
  - ⚠️ **เก็บที่ *เครื่อง* ไม่ใช่ที่ *บัญชี*** ⇒ **`resetPushStatus()` ตอน login/logout ต้องล้างคำเตือน แต่ต้อง *ไม่* ล้างคีย์** — คีย์เป็นข้อเท็จจริงของอุปกรณ์ (เครื่องโรงเรียนเครื่องเดียวใช้หลายคน) · ตระกูลเดียวกับบทเรียน *badge ติดกับไอคอน ไม่ใช่กับบัญชี* · และเพราะ production code **จงใจไม่ล้าง** เทสต์จึงต้อง `localStorage.clear()` เองใน `beforeEach` ไม่งั้นค่ารั่วข้ามเทสต์
  - ⚠️ **`null` (ไม่เคยบันทึก) ต้องนับเป็น "เก่า" โดยเจตนา** — เครื่องที่เปิด push **ก่อนมีฟีเจอร์นี้** คือกลุ่มที่การ rotate ทำพังพอดี ⇒ *"ไม่รู้ว่าผูกกับอะไร"* ≠ *"น่าจะโอเค"* ⇒ ขอให้เปิดใหม่หนึ่งครั้ง (ยอมเสียการกดหนึ่งครั้ง ดีกว่าเงียบตลอดไป)
  - ⚠️ **เขียน fingerprint *หลัง* ได้ subscription ที่เชื่อถือได้เท่านั้น** — ถ้าหลัง `unsubscribe()` + `subscribe()` แล้ว **endpoint ยังเป็นตัวเดิม** แปลว่าเบราว์เซอร์ไม่ยอมทิ้งของเก่า (เคสจริงของ Chrome) ⇒ **โยน error ห้ามเขียนทับ** · การเขียนทับทั้งที่ยังใช้ของเก่าอยู่ = **ทำลายทางกลับทางเดียวของผู้ใช้** เพราะคำเตือนจะไม่กลับมาอีกเลยตลอดไป
  - ⚠️ **แยก "ไม่ตรง" ออกจาก "ไม่รู้"** — ถ้าโหลดสถานะไม่สำเร็จ (ออฟไลน์) เราไม่รู้ว่าเซิร์ฟเวอร์ใช้คีย์อะไร ⇒ **ห้ามเตือน** ไม่งั้นคำเตือนจะเด้งทุกครั้งที่เน็ตสะดุด แล้วผู้ใช้จะเรียนรู้ที่จะมองข้ามมันไปตลอด
  - 📌 **ลำดับสถานะของการ์ด:** `ios-needs-install` → `blocked` → **`stale`** → `on`/`off` · `blocked` ต้องมาก่อน `stale` (ถ้าเบราว์เซอร์ยังไม่อนุญาต "เปิดใหม่" ก็ไม่ช่วย) · `stale` ต้องมีปุ่ม **"เปิดใหม่บนเครื่องนี้"** ที่มาจาก **การกดของผู้ใช้เท่านั้น** (iOS ต้องการ gesture — ห้ามเรียกอัตโนมัติตอน `onMounted`)
  - 🧪 **พิสูจน์ว่ามีฟัน:** mutation 3 แบบ ⇒ `3` / `5` / `1` เทสต์ล้มตามลำดับ (เชื่อเดิมเสมอ · ลบ `writeBoundKey` · ข้ามด่าน endpoint ซ้ำ) — **ถอดโค้ดแล้วเทสต์ต้องล้ม ไม่ใช่แค่ผ่าน**
- **Date Added:** 2026-09-29

### 🧪 เทสต์ที่ "ผ่าน" เพราะ mock — 3 กับดักที่ทำให้เทสต์โกหก
- **Context/Problem:** เจอทั้งสามแบบในรอบเดียว · อาการร่วมคือ **"รันไฟล์เดียวผ่าน แต่พอรันทั้งชุดล้ม"** หรือ **"แก้โค้ดจริงแล้วเทสต์ยังผ่าน"**
- **Root Cause:** ทั้งสามแบบมีสาเหตุร่วมกัน — **สถานะจำลองถูกตั้งไว้ที่จุดที่ไม่มีใครเป็นเจ้าของ** (ไฟล์ · type · ลำดับการติดตั้ง) ⇒ เทสต์จึง "ผ่าน" ด้วยสถานะที่ไม่ได้ตั้งใจ
- **Correct Pattern/Solution:**
  - ⚠️ **mock ไม่ถูก reset ระดับไฟล์** — เทสต์ที่ assert `expect(x).not.toHaveBeenCalled()` **ผ่านตอนรันไฟล์เดียว แต่ล้มเมื่อรันทั้งไฟล์** เพราะไฟล์อื่นเรียก mock ไปก่อนแล้ว · การ reset ที่ระดับ `describe` **ไม่พอ** (ต้องมีให้ครบทุก `describe`) ⇒ **reset ทุก mock ใน `beforeEach` ระดับไฟล์** เสมอ
  - ⚠️ **`eslint-plugin-vitest(require-mock-type-parameters)`** — `vi.fn()` ทุกตัวต้องมี type parameter **และ type นั้นต้อง *ถูกต้อง*** ไม่ใช่แค่มี (lint ผ่านแต่เทสต์โกหกได้ ถ้า type กว้างเกิน) · เมื่อ mock หลายตัว ให้alias type กลางไฟล์ (`type BadgeMock = () => Promise<...>`) แล้วใช้ซ้ำ
  - ⚠️ **harness ที่ติดตั้ง *ทีหลัง* จะเขียนทับ mock ที่เทสต์ตั้งไว้ *ก่อนหน้า*** ⇒ เทสต์กลายเป็น **no-op ที่ยัง "ผ่าน"** (เจอจริง: เทสต์ตั้ง `sub.unsubscribe = vi.fn(throw)` ก่อนเรียก harness แล้ว harness ผูก `unsubscribe` ตัวใหม่ทับ ⇒ กลายเป็นเทสต์ที่ทดสอบ **เส้นทางสำเร็จ** แทนเส้นทาง error) ⇒ **ให้ harness เป็นเจ้าของสถานะจำลองทั้งหมด แล้วรับ "โหมดความล้มเหลว" เข้ามาเป็น flag** (`unsubscribeError?: boolean`) — **อย่าให้เทสต์แก้ object เอง**
  - 📌 **สัญญาณเตือนที่ใช้ได้ทั่วไป:** เทสต์ที่ "ไม่เคยล้มเลย" ไม่ว่าจะ mutate โค้ดอย่างไร · และเทสต์ที่สร้างสถานะด้วยการแก้ object ที่ **harness สร้าง** ⇒ ให้สงสัยทันทีว่า **ลำดับการติดตั้ง** กลืนของที่ตั้งไว้
  - 📌 **`localStorage`/module-level state ไม่ถูกล้างด้วย `resetXxx()` ที่จงใจสงวนค่า** ⇒ เมื่อ production code **ตั้งใจไม่ล้าง** เทสต์ต้องล้างเอง ไม่งั้นเทสต์จะผ่าน/ล้มด้วยเหตุผลผิดและหาไม่เจอ
- **Date Added:** 2026-09-29

### 📊 เพิ่มคีย์ใน `stats` = ต้องแก้ **3 ที่** ไม่งั้นตัวนับใหม่ไม่เคยขึ้น log
- **Context/Problem:** เพิ่มตัวนับ `quiet` (A8 quiet hours) เข้า dict ของ worker ⇒ ถ้าแก้ไม่ครบ ตัวนับจะ **ทำงานถูกแต่ไม่มีใครเห็น** หรือ **ยอดรวมผิดแบบไม่มีอาการ**
- **Root Cause:** dict ของตัวนับถูกเขียนไว้ **3 ที่ที่ไม่มีอะไรผูกกัน**: ① `process_pending` สร้าง `stats` (8 คีย์) ② `drain()` มี `total` ที่ต้องมีคีย์ชุดเดียวกัน ③ `workers/push_worker.py::_log_stats` **ระบุชื่อคีย์ทีละตัว** (จงใจ — อ่าน log ง่าย) ⇒ คีย์ใหม่ **ไม่ถูกพิมพ์เลย** จนกว่าจะไปเพิ่มเอง
- **Correct Pattern/Solution:** เวลาเพิ่มคีย์ให้ `grep` **ชื่อคีย์เก่าทุกตัว** (ไม่ใช่ grep ชื่อฟังก์ชัน) แล้วแก้ให้ครบทั้งสามที่ · และ **assert ตัวนับในเทสต์** (`assert stats["quiet"] == 2`) — ตัวนับที่ไม่ถูก assert คือตัวนับที่จะเงียบไปตลอด
  · 📌 **ตระกูลเดียวกับบทเรียน `if/elif` ที่ยุบสาขา `gone` หาย** — *ค่าที่ผิดปกติซึ่ง "ดูเหมือนค่าปกติ" (0) จะไม่มีใครจับได้ ถ้าไม่มีเทสต์ที่ assert ตัวนับนั้น*
  · ⚠️ **ลำดับการ partition มีผลต่อความหมายของตัวนับ** — `no_device` → `stale` → `quiet` ⇒ `quiet` นับเฉพาะแถวที่ *ถ้าไม่ติด quiet hours จะถูกส่งจริง* (ถ้าสลับลำดับ ตัวเลขจะพองด้วยแถวที่ไม่มีอุปกรณ์)
- **Date Added:** 2026-09-29

### 🗳 คำตอบของ `AskUserQuestion` มีความหมาย *สัมพันธ์กับคำถามของมัน* — อย่าย้ายคำตอบข้ามงาน
- **Context/Problem:** คำตอบ *"ขึ้นทันที + ซ่อนย้อนหลังได้"* และ *"ไม่แจ้งใครเลย"* ถูกตอบสำหรับงาน **E1 Quick Suggestion** · ผมเกือบเอาไปใช้กับ **E2 ประกาศฉุกเฉิน** ซึ่งจะ **กลับด้านสเปกของ E2 ทั้งข้อ** (urgent ต้อง bypass quiet hours และ fan out ทันที) — และจะ **ไม่ error** อะไรเลย แค่ทำ spec ผิดเงียบ ๆ
- **Root Cause:** คำตอบถูกเก็บเป็น **ค่าเดี่ยว ๆ** (`"ไม่แจ้งใครเลย"`) โดยไม่มีคำถามกำกับ · เมื่องานสองงานในรอบเดียวกัน **อยู่ในธีมเดียวกัน** (ทั้งคู่เป็นเรื่องการแจ้งเตือน/บอร์ด) ค่าจะดู **ใช้แทนกันได้** ทั้งที่ตอบคนละคำถาม
- **Correct Pattern/Solution:**
  - เก็บคำตอบพร้อม **ข้อความคำถาม** ไม่ใช่แค่ค่า (เช่นในไฟล์แผน: `| # | คำถาม | คำตอบ | ผลต่อแผน |`)
  - ⚠️ **ก่อนเอาคำตอบไปใช้กับงานอื่น ให้ *กลับไปอ่าน payload ของคำถามนั้น* — อย่าจำ** (คำตอบที่จำได้จะมาพร้อมคำถามที่แต่งขึ้นเอง)
  - ⚠️ **งานที่ "ดูใกล้กัน" คือจุดที่สลับง่ายที่สุด** — และการสลับจะไม่ทำให้เทสต์ล้ม เพราะเทสต์เขียนตามความเข้าใจที่ผิดอยู่แล้ว ⇒ ด่านเดียวที่จับได้คือ **อ่านคำถามต้นทางซ้ำ**
  - 📌 ถ้าคำตอบหนึ่งถูกใช้กับสองงานโดยเจตนา ให้ **เขียนไว้ในแผนว่าใช้ร่วมกัน** ไม่ใช่ปล่อยให้เป็นการอนุมาน
- **Date Added:** 2026-09-29

### 🔄 "พังเฉพาะเครื่องที่เคยทำสำเร็จ" = ปัญหาการรอให้เข้าที่ ไม่ใช่สิทธิ์หรือคีย์
- **Context/Problem:** `PushManager.subscribe()` ล้มด้วย `AbortError: Registration failed - push service error` — **เฉพาะมือถือเครื่องที่เคยเปิดการแจ้งเตือนได้ปกติ** ส่วน **คอมพิวเตอร์ที่ไม่เคยกดเปิดเลย เปิดผ่านทันที** · และกรอบเหลือง (สถานะ `stale`) **ตรวจถูกต้องแล้ว** แต่ **กดปุ่มซ่อมแล้วไม่ผ่าน** ⇒ อาการดูเหมือน "คีย์พัง" หรือ "ถูกบล็อก" ทั้งที่ไม่ใช่ทั้งคู่
- **Root Cause:** `obtainSubscription()` ทิ้ง subscription เดิม (`unsubscribe()` = สั่งลบ token ที่ FCM) แล้วขอใหม่ (`subscribe()` = ขอ token ใหม่) **ติดกันทันที** ⇒ ปลายทางยังประมวลผลคำสั่งลบไม่เสร็จ จึงปฏิเสธคำขอที่สอง · เครื่องที่ไม่เคยเปิด **ไม่มี token ให้ลบ** ⇒ ไม่มีการโยก ⇒ ผ่านทันที · **ความต่างไม่ใช่ "เครื่อง" แต่คือ "มีสถานะเดิมค้างอยู่หรือไม่"**
- **Correct Pattern/Solution:**
  - ⭐ **3 หลักฐานที่ชี้ทางนี้ตั้งแต่ต้น** (และถูกมองข้ามได้ง่ายเพราะดูเหมือนปัญหาสิทธิ์): ① **เครื่องใหม่ผ่าน · เครื่องเดิมล้ม** ⇒ ความต่างคือ "มีอะไรให้รื้อหรือไม่" ② **มี `unsubscribe()` ตามด้วย `subscribe()` ติดกัน** ในเส้นทางที่ล้ม ⇒ churn ③ **การ์ดตรวจถูก แต่กดซ่อมไม่ได้** ⇒ ปัญหาอยู่ที่ *การเขียน* ไม่ใช่ *การอ่าน*
  - ⭐ **สัญญาณว่าเป็น "การรอให้เข้าที่" ไม่ใช่ "ค่าที่ผิด":** ถ้าค่าที่ใช้ผิด (คีย์ decode ผิด · public/private ไม่เข้าคู่ · payload เก่าค้างที่ CDN) **ทุกเครื่องจะล้มเท่ากัน** — อาการที่ *เลือกเครื่อง* คือ churn/timing เสมอ
  - ⭐ **การลองใหม่ต้องมีประตูแคบ** — จับเฉพาะ `AbortError` + ข้อความที่ตรง (`/push service|Registration failed/i`) · ประตูกว้าง (`e instanceof DOMException`) จะทำให้เคสที่ **การลองใหม่ไม่ได้ช่วย** (`NotAllowedError` = ถูกบล็อก, `InvalidStateError` = มีของค้าง) **รอนานขึ้นเพื่อรอคำตอบเดิม** ⇒ แย่กว่าไม่ลอง · งบต้องมีขอบเขต (~4 ครั้ง / ~5 วิ) เพราะปลายทางที่ล่มจริง การรอนานกว่านั้นไม่ช่วยและผู้ใช้เห็นปุ่มค้าง
  - ⭐ **ข้อความ error ต้องบอก "ทำอะไรต่อ" ไม่ใช่ "อะไรพัง"** — `Registration failed - push service error` บอกแค่ว่ามีอะไรผิด ⇒ ผู้ใช้กดซ้ำจนคิดว่าแอพพัง · ต้องแปลงเป็นคำสั่งที่ทำได้ (`describePushError()`) · และ **error ที่เราเขียนเองต้องผ่านออกไปตามเดิม** ไม่ถูกแทนที่ด้วยข้อความกลาง ๆ
  - 🧪 **พิสูจน์ด้วย mutation 3 ตัว:** ถอด retry → `R1/R2/R4` ล้ม · ขยายประตู → `R3/R6/R7` ล้ม · ปิดสาขา `DOMException` → `R5/R6/R7` ล้ม · เทสต์ `R2` คือด่านสำคัญ: ปลายทางปฏิเสธตลอด ⇒ `subscribe` ถูกเรียก **4 ครั้งพอดี** และ **คีย์เก่าไม่ถูกเขียนทับ**
  - ⚠️ **กับดัก type:** `noUncheckedIndexedAccess: true` ⇒ `DELAYS[attempt]` เป็น `number | undefined` · `if (delay === undefined) break` **จำเป็นทั้งทาง logic และทาง type** (ไม่ใช่แค่เพื่อความสวย)
- **Date Added:** 2026-09-29

### 🌐 "route จริง" กับ "route มั่ว" ให้ผลเหมือนกัน = ปัญหาที่ **routing** ไม่ใช่ที่แอพ
- **Context/Problem:** ยิง 4 route ที่มีจริงบน production → **404 ทั้งหมด** ⇒ เกือบสรุปว่า "โค้ดไม่ถึง" หรือ "router ไม่ถูก mount" · ตัวที่ช่วยให้รู้ตัวคือ **ยิง route มั่ว (`/api/__nope__`) แล้วได้ 404 เท่ากันเป๊ะ** ⇒ ถ้าแอพตอบ 404 เหมือนกันหมด แปลว่า **คำขอไม่เคยถึงแอพเลย**
- **Root Cause:** ใช้ `-H "Host: prsc.pirivoice.com"` ซึ่งเป็น **โดเมนที่ผมเดาเอง** · Traefik จับ route ด้วย `Host(...)` ⇒ ไม่มี router สำหรับ Host นั้น ⇒ ตอบ 404 ที่หน้า proxy ก่อนถึง backend · **ของจริงคือ `api.pirivoice.com` (API) และ `www.pirivoice.com` (เว็บ)** ซึ่งอ่านจาก `API_DOMAIN`/`WEB_DOMAIN` ใน `.env` ของ clone
- **Correct Pattern/Solution:**
  - ⭐ **ด่านวินิจฉัย:** **"route จริง" และ "route มั่ว" ให้ผลเหมือนกัน = ปัญหาที่ routing** — ถ้าปัญหาอยู่ที่แอพ ของจริงจะให้ `401`/`422` ส่วนของมั่วให้ `404` (ต่างกัน) · **ยิง route มั่วเป็น *กลุ่มควบคุม* ทุกครั้งที่ทดสอบ routing ไม่ใช่แค่ตอนสงสัย**
  - ⭐ **อย่าเดาโดเมน — อ่านจาก `.env` ของ clone นั้นเสมอ** (`API_DOMAIN` · `WEB_DOMAIN`) เพราะ compose ต่อค่าเข้า `traefik.http.routers.<env>_backend.rule=Host(...)` **ไม่ได้ฝังในโค้ด** ⇒ โดเมนต่างกันได้ระหว่าง staging/production และแก้ได้โดยไม่แตะโค้ดเลย
  - 📌 **ร่องรอยที่ใช้แยก:** `401`/`405`/`422` = **ถึงแอพแล้ว** (มี router) · `404` = **ไม่ถึงแอพ** · `405` ที่ route ที่มีจริงแต่ผิด method (เช่นยิง GET ใส่ POST-only) คือ **หลักฐานว่า path มีอยู่จริง** ⇒ ใช้เป็นด่านบวกได้
  - 📌 **`401` ที่ได้จาก route ที่มีจริง = หลักฐานว่ามี route นั้น** — ไม่ต้องมี token ก็ตรวจการมีอยู่ของ endpoint ได้
- **Date Added:** 2026-09-29

### 🔍 อย่าตัดสินความปลอดภัยของ migration จาก **จำนวน** ที่ grep เจอ — ต้องเปิดดูบรรทัดนั้น
- **Context/Problem:** ก่อน deploy migration ขึ้น production ผมสแกน `grep -icE 'DROP|ALTER|DELETE|TRUNCATE|UPDATE '` บน diff ของ migration ⇒ ได้ **3** ⇒ เกือบตีความว่า "มี DDL อันตราย 3 จุด" แล้วหยุด deploy · ของจริงคือ **false positive ทั้ง 3** (2 × `ON DELETE SET NULL` — ตัวหนึ่งอยู่ใน docstring · 1 × `ALTER TABLE notifications ADD COLUMN IF NOT EXISTS … DEFAULT FALSE` ซึ่งเป็น additive)
- **Root Cause:** คำสำคัญที่ใช้ตัดสินอันตราย (`DELETE`, `ALTER`) **เป็นคำเดียวกับที่โผล่ในประโยคปลอดภัย** — `ON DELETE SET NULL` เป็น *นโยบาย FK* ไม่ใช่คำสั่งลบ · และ `ALTER … ADD COLUMN … DEFAULT <ค่าคงที่>` บน **PG 11+ เป็น metadata-only (ไม่ rewrite ตาราง)** ⇒ image เก่าอ่านคอลัมน์ใหม่ข้ามไปได้ ⇒ **rollback ได้**
- **Correct Pattern/Solution:**
  - ⭐ **ตัวเลขนับเป็นเพียง *ตัวชี้ไปดู* ไม่ใช่ *คำตอบ*** — เปิดดูทุกบรรทัดที่ match เสมอ · ถ้าจำนวน > 0 แต่ไม่มีบรรทัดไหนเป็นคำสั่งจริง ⇒ เขียนกำกับไว้ในบันทึกว่า "false positive ทั้งหมด" เพื่อคนถัดไปจะไม่ต้องสืบซ้ำ
  - ⭐ **ด่านที่เชื่อได้กว่าการ grep คำสำคัญ: `git diff --numstat <base> <head>` แล้วดูว่ามีไฟล์ไหน *ลบบรรทัด* บ้าง** — migration ที่ additive ล้วนจะมี `-0` ทุกไฟล์ · การลบบรรทัดในโค้ดเดิมคือที่ที่ของพัง
  - ⭐ **แยกให้ชัดว่า migration แบบไหน rollback ได้:** `CREATE TABLE IF NOT EXISTS` · `ADD COLUMN IF NOT EXISTS … DEFAULT <constant>` · `CREATE INDEX IF NOT EXISTS` ⇒ **ได้** (image เก่าเมินของใหม่) · ส่วน `DROP COLUMN` · `ALTER TYPE` · `DROP CONSTRAINT` ที่โค้ดเก่าพึ่งพา ⇒ **ไม่ได้** ⇒ ต้องสำรอง + ยอมรับ downtime
  - 📌 **`IF NOT EXISTS` / `IF EXISTS` ทุกคำสั่ง = idempotent** ⇒ รันซ้ำได้ และรันพร้อมกันหลาย replica แล้วไม่พัง (แต่ยังไม่ **atomic** — หนี้ที่รู้อยู่)
- **Date Added:** 2026-09-29

### ⏱ `vi.restoreAllMocks()` **ไม่คืนเวลาเทียม** — เทสต์ถัดไปค้างเงียบ ๆ
- **Context/Problem:** เทสต์ที่ใช้ `vi.useFakeTimers()` แล้ว assert การลองใหม่ตามเวลา ⇒ พอเพิ่มเทสต์ที่สองเข้าไปในไฟล์เดียวกัน **เทสต์ตัวถัดไปค้างไม่จบ** (timeout) ทั้งที่ตัวมันเองไม่มีอะไรผิด · และตอนรันไฟล์เดียวผ่าน แต่รันทั้งไฟล์ค้าง ⇒ หาสาเหตุยากมากเพราะจุดที่ค้างไม่ใช่จุดที่ผิด
- **Root Cause:** **`vi.restoreAllMocks()` คืนเฉพาะ spy/mock ไม่คืน `Date`/`setTimeout` ที่ถูกแทนด้วยเวลาเทียม** (vitest 4.1.10) ⇒ พอ `afterEach` คืน mock แต่ **เวลาเทียมยังเดินอยู่** และ **`setTimeout` จริงไม่เคยถูกเรียก** ⇒ promise ที่รอ `sleep()` ไม่มีวัน resolve ⇒ ค้าง
- **Correct Pattern/Solution:**
  - ⭐ **`afterEach` ต้องมี `vi.useRealTimers()` แยกต่างหาก** คู่กับ `vi.restoreAllMocks()` — ทั้งคู่จำเป็นและ **ไม่ได้แทนกัน**
  - ⭐ **ห่อเทสต์ที่ใช้เวลาเทียมด้วย helper ที่คืนเวลาให้เสมอ** (`withFakeTimers(async () => {...})` ที่ `try/finally` เรียก `useRealTimers()`) ⇒ ลืมไม่ได้ และอ่านออกว่าขอบเขตเวลาเทียมคือตรงไหน
  - ⚠️ **promise ที่กำลังจะ reject ต้องมี `catch` ก่อน `await vi.runAllTimersAsync()`** — ไม่งั้นได้ unhandled rejection ที่ไม่บอกตำแหน่ง (`void task.catch(() => {})` แล้วค่อยเดินเวลา)
  - 📌 **สัญญาณวินิจฉัย "เวลาเทียมรั่ว":** เทสต์ค้าง (ไม่ fail) · ค้างที่เทสต์ *ถัดไป* ไม่ใช่ตัวที่ใช้เวลาเทียม · ไฟล์เดียวผ่านแต่ทั้งไฟล์ค้าง ⇒ ให้สงสัยเวลาก่อนตรรกะ
  - 📌 **ตระกูลเดียวกับบทเรียน "สถานะที่ไม่มีใครเป็นเจ้าของ"** — `localStorage` · state ระดับโมดูล · และ **เวลาเทียม** ล้วนเป็นสถานะที่ `restoreAllMocks()` ไม่ได้คืนให้ ⇒ ต้องมีบรรทัดที่คืนมันตรง ๆ
- **Date Added:** 2026-09-29

### 🧮 helper ที่รับ **สองคิวรี** (นับ + ดึงแถว) = ต้องมี **สองชุดพารามิเตอร์** — เลข placeholder ของแต่ละคิวรีเป็นอิสระต่อกัน
- **Context/Problem:** ฟังก์ชัน `_envelope(conn, count_sql, params, rows_sql, params, limit, offset)` รวม "นับ total" กับ "ดึงหน้า" ไว้ในตัวเดียว (แพตเทิร์นที่โปรเจคนี้ใช้ทั่ว) · พอเอามาใช้กับลิสต์ที่ดึงแถวต้องรู้ `user_id` (`rows_sql` มี `$1` = `user_id`) แต่ `count_sql` **ไม่ต้องใช้ `user_id` เลย** ⇒ ส่งลิสต์เดียวกันให้ทั้งคู่ ⇒ `asyncpg.exceptions.InterfaceError: the server expects 0 arguments for this query, 1 was passed` — **ล้มทั้ง 6 เทสต์ที่เรียกผ่าน helper นี้** และข้อความ error ไม่ได้บอกว่าคิวรีไหนเป็นปัญหา
- **Root Cause:** **`$n` ของแต่ละคิวรีเป็น Namespace ของตัวเอง** — `$1` ใน `count_sql` กับ `$1` ใน `rows_sql` **ไม่ใช่พารามิเตอร์ตัวเดียวกัน** และไม่มีอะไรรับประกันว่าทั้งสองคิวรีใช้จำนวน/ลำดับพารามิเตอร์เท่ากัน · การห่อเป็น helper เดียวทำให้ **ข้อสันนิษฐานนั้นถูกซ่อนไว้ใน signature** (`params` ตัวเดียว) ⇒ วันที่คิวรีหนึ่งโตขึ้นแล้วต้องการพารามิเตอร์เพิ่ม อีกคิวรีไม่ต้อง ⇒ พังทันทีและพังแบบกว้าง
- **Correct Pattern/Solution:**
  - **แยกเป็น `count_params` / `rows_params` ใน signature** แล้วส่งต่อแยกกัน:
    ```python
    async def _envelope(conn, *, count_sql: str, count_params: list,
                        rows_sql: str, rows_params: list, limit: int, offset: int) -> dict:
    ```
    ⇒ ทั้งสองฝั่งบังคับให้ผู้เรียก **คิดทีละคิวรี** และแนบ `assert sql.count("$") == len(params)` ได้จริงทั้งคู่
  - 📌 **`assert sql.count("$")` ที่วางไว้ตรงจุดเดียว (ใน helper) จะไม่ทำงาน** เมื่อ helper ถือสองคิวรี — ต้อง assert **ต่อคิวรี** ไม่ใช่ต่อการเรียก
  - ⚠️ **ข้อความ error ชี้ผิดที่เสมอ** (`the server expects 0 arguments` ฟังดูเหมือน "ผู้เรียกลืมส่ง") ⇒ **อ่านว่า "จำนวน args ไม่ตรงกับ *คิวรีใดคิวรีหนึ่ง*" แล้วไปนับ `$n` สูงสุดของแต่ละคิวรี** ไม่ใช่ไปหาว่าลืมส่งตัวไหน
  - 🚩 **สัญญาณของคลาสนี้:** helper ตัวเดียวที่ "ทำสองอย่าง" (นับ + ดึง · insert + select · validate + write) ⇒ **พารามิเตอร์ของสองอย่างจะถูกรวมเป็นชุดเดียวเสมอ** ถ้าไม่แยกเอง
- **Date Added:** 2026-09-29

### 🏷️ `entity_id` — **ชื่อคอลัมน์เดียวกัน แต่คนละชนิดในคนละตาราง** ⇒ ต้อง `str()` ก่อนเขียน audit log
- **Context/Problem:** `audit_logs` ใช้ `entity_type VARCHAR(50)` + **`entity_id VARCHAR(50)`** (มี default `'-'`) · แต่ `notifications.entity_id` เป็น **`INTEGER`** และ `bookmarks.entity_id` ก็ **`INTEGER`** · โค้ดที่ยิง `audit_logs` ด้วย `entity_id=event_id` (int) ⇒ `asyncpg.exceptions.DataError: invalid input for query argument $5: 3 (expected str, got int)` และเทสต์ที่เทียบก็ล้มด้วย `assert ('event' == 'event' and '3' == 3)` *"ทั้งที่ค่าตรงกัน"*
- **Root Cause:** `entity_id` เป็น **คำที่แปลว่า "id ของสิ่งนั้น"** ซึ่งในฐานข้อมูลนี้ถูกทำให้เป็น **สองชนิดที่ต่างกันโดยเจตนา** (audit log เก็บเป็นข้อความเพราะรองรับ entity หลายชนิดรวมถึงชนิดที่ id ไม่ใช่ตัวเลข · ตารางปลายทางเก็บเป็น integer เพราะ FK/join ต้องใช้) ⇒ **การอ่านชื่อคอลัมน์แล้วอนุมานชนิด = กับดัก** และ type checker ฝั่ง Python **ไม่ช่วยเลย** เพราะ asyncpg ตรวจที่ runtime
- **Correct Pattern/Solution:**
  - **`entity_id=str(event_id)` เสมอเมื่อเขียน `audit_logs`** + เขียน comment กำกับที่จุดนั้นว่าทำไม (ไม่งั้นคนอ่านจะ "แก้ให้สะอาด" แล้วพัง)
  - **เทสต์ต้องเทียบ `str(entity_id)`** ไม่ใช่ int — และ **`json.loads()` ก่อนเทียบ `old_values`/`new_values`** เพราะ **JSONB จาก raw asyncpg pool คืนมาเป็น `str`** ไม่ใช่ dict (`AttributeError: 'str' object has no attribute 'keys'`)
  - 📌 **ก่อนเขียนโค้ดที่แตะตารางใหม่ ให้เปิด `init_db.py` ดูชนิดจริงของทุกคอลัมน์ที่จะเขียน** — อย่าเทียบกับตารางที่ "ชื่อคล้ายกัน" (บทเรียนตระกูลเดียวกับ polymorphic `entity_type`/`entity_id` ที่ L1478)
  - 🚩 **สัญญาณของคลาสนี้:** error ที่พูดถึง **"expected X, got Y"** บนคอลัมน์ที่ชื่อคุ้นเคย — ให้สงสัย **ชนิดของคอลัมน์ในตารางนั้น** ก่อนสงสัยว่าโค้ดส่งค่าผิด
- **Date Added:** 2026-09-29

### 🎫 `created` ต้องแปลว่า **"INSERT แถวใหม่"** ไม่ใช่ **"คำสั่งสำเร็จ"** — ไม่งั้น 201/200 จะโกหก
- **Context/Problem:** `register_event()` มีสองเส้นทาง: ผู้ใช้ใหม่ ⇒ `INSERT` · ผู้ใช้ที่เคยยกเลิกแล้วกลับมาสมัครใหม่ ⇒ `UPDATE` แถวเดิม · ฟังก์ชันคืน `(created, payload)` ให้ router แปลงเป็น **201 ถ้า `created`** ไม่งั้น **200** · ตอนแรกผมตั้ง `created = True` ทั้งสองเส้นทาง ⇒ เทสต์ที่คาด 200 ได้ 201 (`assert 201 == 200`)
- **Root Cause:** คำว่า **"สร้าง"** กำกวมระหว่าง *"ทรัพยากรนั้นเกิดขึ้นจากการเรียกครั้งนี้"* กับ *"การเรียกครั้งนี้สำเร็จ"* ⇒ ถ้าอนุมานแบบหลัง **ทุกคำขอที่สำเร็จจะกลายเป็น 201** ซึ่งทำลายความหมายเดียวที่ 201 มี (ใช้แยก "กดซ้ำ/กดต่อ" ออกจาก "เพิ่งเกิด") ⇒ ฝั่ง client ที่ใช้ 201 เพื่อแสดงข้อความ "สมัครสำเร็จ" จะแสดงผิดในเส้นทางที่กลับมาสมัครใหม่
- **Correct Pattern/Solution:**
  - **ตั้งชื่อให้ความกำกวมหายไปตั้งแต่ตัวแปร** — `created` = *"มีแถวใหม่ถูก INSERT"* เขียน comment กำกับที่ `return` ทุกจุด (L806/L902/L914) เพราะนี่คือค่าที่ router ใช้ตัดสิน status
  - **`RETURNING (xmax = 0) AS inserted`** เป็นทางที่ DB บอกเองตรง ๆ · หรือแยกสาขาให้ชัด (`if existing: UPDATE; created = False else: INSERT; created = True`)
  - ⚠️ **อย่าให้ denormalize แบบ "นับก่อน-นับหลัง"** (`count_before != count_after`) — เปราะกับ concurrent request และอ่านไม่ออก
  - 📌 **เทสต์ต้องมีทั้งสองเส้นทาง** — เส้นทาง `INSERT` (201) และเส้นทาง `UPDATE` (200) · ถ้ามีแต่เส้นทางแรก บั๊กนี้จะไม่โผล่เลย (และนี่คือเหตุที่มันรอดมาได้จนเกือบ commit)
- **Date Added:** 2026-09-29

### 🕳 `value in obj` เดินขึ้น **prototype chain** — `?unavailable=constructor` ผ่านด่านไปโผล่เป็น `undefined` บนหน้าจอ
- **Context/Problem:** ฟังก์ชันที่อ่านค่าจาก `route.query` แล้วแปลงเป็นชนิดที่รู้จัก เขียนว่า `if (value in MESSAGES) return value as Kind` ⇒ `?unavailable=constructor` **ผ่านด่าน** เพราะ `'constructor' in {}` เป็น `true` (สืบทอดมาจาก `Object.prototype`) แล้ว `MESSAGES[value]` เป็น `undefined` ⇒ **Swal ขึ้นคำว่า "undefined"** ให้ผู้ใช้เห็น
- **Root Cause:** **`in` ตรวจทั้ง own property และ property ที่สืบทอดมา** (ต่างจาก `Object.hasOwn`/`hasOwnProperty`) ⇒ ทุกคีย์ของ `Object.prototype` (`constructor` · `toString` · `valueOf` · `hasOwnProperty` · `__proto__` · …) ผ่านด่านทั้งหมด · และ **TypeScript ไม่ช่วยเลย** — `value in obj` ไม่ narrow type ให้ และ `Record<K, V>` indexing ที่คีย์มาจาก `string` จะถูกบังคับให้ cast ⇒ **ทั้งด่านและ type ถูกปิดปากพร้อมกัน**
- **Correct Pattern/Solution:**
  - **literal chain** — `if (value === 'board' || value === 'issue' || value === 'event') return value` ⇒ narrow type ให้ฟรี และไม่มีทางรั่ว
  - ทางเลือกที่ปลอดภัยพอ ๆ กัน: `Object.hasOwn(MESSAGES, value)` (ES2022) หรือ `Object.keys(MESSAGES).includes(value)`
  - 📌 **ค่านี้มาจาก URL ที่ใครก็แก้ได้ ⇒ ถือเป็น input ที่ไม่เชื่อถือ** และต้องกรอง — **การ cast คือการเชื่อว่า input** ซึ่งเป็นสิ่งที่ห้ามทำ (ตระกูลเดียวกับ "กรอง ไม่ cast" ของ `safeRedirect`)
  - ⚠️ **เขียนเทสต์ด้วย `'constructor'` และ `'toString'` จริง** ไม่ใช่แค่ comment — เพราะถ้าวันหนึ่งมีคน "ทำให้สั้นลง" เป็น `in` อีก จะมีเทสต์ที่ล้มพร้อมชื่อที่บอกสาเหตุ (ผมเพิ่มสองแถวนี้เข้า `it.each` ของ U2 โดยเจตนา)
  - 🚩 **สัญญาณของคลาสนี้:** โค้ดที่ **"ตรวจว่าคีย์มีอยู่"** ด้วย `in`/indexing บนค่าที่มาจาก **URL · localStorage · postMessage · JSON ภายนอก** ⇒ ตรวจทุกจุด
- **Date Added:** 2026-09-29

### 🕐 `<input type="datetime-local">` ต้องอ่านค่าด้วย **`Intl.DateTimeFormat().formatToParts()`** — `toISOString()` เลื่อน 7 ชั่วโมงและ **ไม่ error**
- **Context/Problem:** ฟอร์มแก้ไขกิจกรรมต้องเติมค่า `event_date` (timestamptz) กลับลง `<input type="datetime-local">` ⇒ เขียน `new Date(iso).toISOString().slice(0, 16)` ซึ่งให้ **เวลา UTC** ⇒ เปิดฟอร์มมาเห็นเวลาน้อยไป **7 ชั่วโมง** และ — อันตรายกว่า — **ถ้าผู้ใช้กดบันทึกโดยไม่แตะฟิลด์นั้นเลย** ค่าที่ส่งกลับจะเพี้ยนทันที 7 ชั่วโมง · **ไม่มี error ไม่มีคำเตือน** และถ้าไม่มีเทสต์เทียบค่าก่อน/หลัง ฟอร์มจะ "บันทึกได้" ทุกครั้ง
- **Root Cause:** `<input type="datetime-local">` มี **ไม่มี** เขตเวลาในค่า — มันคือ *"เวลาตามนาฬิกาบนผนัง"* ของผู้ใช้ ⇒ ต้องป้อนด้วยชิ้นส่วนของ **เขตเวลาที่ระบบใช้ (`Asia/Bangkok`)** · `toISOString()` แปลงเป็น UTC ก่อนเสมอ ⇒ การใช้มันเท่ากับ **สมมติว่าผู้ใช้อยู่ที่ UTC** · และ `toLocaleString()` ก็ใช้ไม่ได้ตรง ๆ เพราะให้สตริงที่รูปแบบไม่คงที่ในแต่ละ ICU
- **Correct Pattern/Solution:**
  ```ts
  const BKK_PARTS = new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Asia/Bangkok',
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
  })
  function toLocalInput(iso: string | null): string {
    if (!iso) return ''
    const parts = BKK_PARTS.formatToParts(new Date(iso))
    const get = (t: string) => parts.find((p) => p.type === t)?.value ?? ''
    return `${get('year')}-${get('month')}-${get('day')}T${get('hour')}:${get('minute')}`
  }
  ```
  · **`hourCycle: 'h23'` จำเป็น** — `en-GB` กับ `hour12: false` อาจให้ `24` แทน `00` ในบางรันไทม์ ⇒ input ปฏิเสธค่าที่ไม่ถูกต้อง **แบบเงียบ** (ค่าในช่องหายไปเฉย ๆ)
  - 🔄 **ปรับปรุง 2026-09-30 (รอบ 4): บรรทัดนี้ "จำเป็น" จริง แต่ *เทสต์พิสูจน์ไม่ได้* บนเครื่องนี้** — ย้ายไป `src/datetime.ts` แล้วตรวจด้วย mutation: **ถอด `hourCycle: 'h23'` ออกทั้ง `BKK_PARTS` และ formatter ของคำอ่าน พ.ศ. ⇒ เทสต์ทั้งไฟล์ยังเขียว 21/21** (ไล่เทียบครบ 24 ชั่วโมง ทั้ง `en-GB` และ `th-TH-u-ca-buddhist` ⇒ Node 22 + full ICU ให้ `h23` อยู่แล้วโดยปริยาย ต่างกัน 0 ชั่วโมง) ⇒ **ยังต้องคงบรรทัดนี้ไว้** เพราะกันรันไทม์ที่ default เป็น `h24` แต่ **คอมเมนต์ในโค้ดที่อ้างว่า "มีเทสต์คุมอยู่" เป็นความเชื่อผิดที่อันตราย** — ดู entry `เทสต์เขียวไม่ได้แปลว่าคุณสมบัติที่คอมเมนต์อ้างถูกคุมอยู่`
  · สร้าง `Intl.DateTimeFormat` **ครั้งเดียวระดับโมดูล** ไม่ใช่ต่อการเรียก (สร้างใหม่ทุกครั้งช้ากว่ามาก)
  - ⚠️ **ใช้ `toLocalInput()` ทั้งตอน *เติมฟอร์ม* และตอน *สร้าง baseline*** เพื่อให้เทียบ diff ได้ (ดูข้อถัดไป)
  - 📌 **การแสดงผลใช้ `toLocaleString('th-TH', { timeZone: 'Asia/Bangkok', … })` ได้ตรง ๆ** เพราะนั่นเป็นการ *แสดง* ไม่ใช่การป้อนกลับ — **สองหน้าที่นี้ต้องใช้คนละวิธี** และนี่คือจุดที่คนมักใช้ตัวเดียวกันแล้วพังข้างหนึ่ง
  - ⚠️ **ต่างจากวันที่ล้วน (date-only)** ที่โปรเจคนี้มีกฎว่า **ห้ามใช้ `new Date()`** (เพราะ parse เป็น UTC เที่ยงคืน) — กิจกรรมเป็น **timestamptz** จึงใช้ `new Date(iso)` ได้ **แต่ยังต้องอ่านชิ้นส่วนในโซน Bangkok**
- **Date Added:** 2026-09-29
- **🔄 ปรับปรุง 2026-09-30 (รอบ 4):**
  - **โค้ดย้ายไป `frontend/src/datetime.ts` แล้ว** — ก่อนหน้านี้ `toLocalInput()` อยู่ใน
    `EventManagement.vue` และ `fmtDateTime()` **ก๊อปซ้ำอยู่ 4 ไฟล์** (`CommentThread` ·
    `EventDetail` · `MyActivity` · `AuditLogs`) ⇒ แก้รูปแบบที่เดียวแล้วอีกสามที่ไม่ตาม
    และไม่มีเทสต์ไหนจับได้ (ไม่มีเทสต์ไหนเทียบข้ามไฟล์) · ตอนนี้ **import จากที่เดียว**
  - **มีเทสต์แล้ว** `frontend/src/__tests__/datetime.spec.ts` (20 เคส) — ทุก assertion เทียบ
    **ค่าคงที่ที่เขียนตายตัว** ไม่ใช่คำนวณด้วย `Date` ⇒ พิสูจน์ว่าไม่พึ่งโซนของเครื่องรันเทสต์
    (ถ้าเทสต์คำนวณค่าที่คาดหมายด้วย `Date` เอง มันจะผ่านทุกโซนรวมทั้งโซนที่โค้ดพัง)
  - ➕ **เพิ่มคู่ใหม่สำหรับ date picker: `inputToDate()` / `dateToInput()`** — ดู entry
    "date picker: local ↔ local" ด้านล่าง · **ทั้งสองคู่ห้ามใช้ `toISOString()` เหมือนกัน**
  - ➕ **`formatThaiDateTimeInput()`** — คำอ่าน พ.ศ. ที่ **ไม่ใช่**ค่าที่ส่ง backend
    (ใช้ `Date.UTC` + `timeZone:'UTC'` โดยเจตนา — ดู entry ของ date picker)

### 📄 PATCH ที่ส่ง **เฉพาะฟิลด์ที่เปลี่ยน** ต้องมี **snapshot ตั้งต้นที่ normalize แล้ว** — ไม่งั้น "ไม่ได้แตะ" จะกลายเป็น "แก้ค่า"
- **Context/Problem:** ฟอร์มแก้ไขต้องส่ง PATCH เฉพาะฟิลด์ที่ผู้ใช้แก้จริง (กฎโปรเจค: backend ใช้ `exclude_unset=True` และ audit log บันทึกเฉพาะของที่เปลี่ยน) · ถ้าเทียบ **ค่าดิบจาก API** กับ **ค่าจากฟอร์ม** ตรง ๆ จะได้ "ต่าง" ทุกครั้งที่ชนิด/รูปแบบไม่ตรงกันเป๊ะ (เช่น `null` กับ `''` · `2026-10-15T02:00:00Z` กับ `2026-10-15T09:00` · `null` กับ `'null'`) ⇒ **PATCH ส่งทุกฟิลด์ทุกครั้งที่กดบันทึก** ⇒ audit log ท่วม และ "เขียนทับคอลัมน์ที่ผู้ใช้ไม่ได้แตะ" กลับมา
- **Root Cause:** สองฝั่งของ diff มาจาก **คนละตัวแทนของข้อมูล** (server JSON vs ค่าฟอร์ม HTML) ซึ่ง **ไม่มีอะไรรับประกันว่าเท่ากันสำหรับค่าที่ "เหมือนกัน"** ⇒ ต้องมีขั้น **แปลงทั้งสองฝั่งให้เป็นตัวแทนเดียวกันก่อนเทียบ** · และ **`baseline` ต้องถูกจับ *ตอนเปิดฟอร์ม* ไม่ใช่ตอนกดบันทึก** — ถ้าจับตอนกดบันทึก มันจะเท่ากับค่าปัจจุบันเสมอ ⇒ diff ว่างตลอด (อีกอาการหนึ่งของบั๊กเดียวกัน)
- **Correct Pattern/Solution:**
  ```ts
  const baseline = ref<EventCreate | null>(null)   // จับตอน openEdit()
  function toBaseline(e: Event): EventCreate {      // ← ผ่าน toLocalInput() ตัวเดียวกับฟอร์ม
    return { …e, event_date: toLocalInput(e.event_date),
                 registration_deadline: toLocalInput(e.registration_deadline) }
  }
  function buildPatch(): EventUpdate {              // เทียบ baseline ↔ ค่าฟอร์มปัจจุบัน
    const next = buildCreate(); const base = baseline.value
    if (!base) return next
    const patch: EventUpdate = {}
    if (base.title !== next.title) patch.title = next.title
    /* …ทีละฟิลด์… */
    return patch
  }
  ```
  · **`Object.keys(patch).length === 0` ⇒ ไม่ยิง API เลย** (ผู้ใช้อาจเปิดฟอร์มแล้วปิดโดยไม่แก้) — และอย่าลืม `closeModal()` ให้ถูก ไม่งั้นฟอร์มค้างเปิดโดยไม่มีอะไรเกิดขึ้น
  · 📌 **`''` กับ `null` ต้องตัดสินให้ชัด** — ในฟอร์มนี้ช่องว่างของฟิลด์ที่ไม่บังคับ = **`null` (สั่งล้างค่า)** ไม่ใช่ `undefined` (ไม่แตะ) ⇒ เขียน helper `buildCreate()` ที่ทำ normalization นี้ **ที่เดียว** แล้วให้ทั้ง "สร้าง" และ "แก้" ใช้ร่วมกัน
  - ⚠️ **`ref` ของ object ที่แก้ทีละฟิลด์ต้องสร้าง object ใหม่** ไม่ใช่ mutate — ไม่งั้น diff จะเทียบ object เดียวกันแล้วได้ "ไม่เปลี่ยน" เสมอ
  - 🚩 **สัญญาณของคลาสนี้:** หน้าจอที่ "บันทึกแล้วดูเหมือนไม่เกิดอะไรขึ้น" · audit log ที่มีทุกฟิลด์ทุกครั้ง · หรือเปิดฟอร์มแล้วกดบันทึกทันที **แล้วค่าที่แสดงเปลี่ยนไปเอง** ⇒ ตรวจ diff และทิศทางของ timezone ก่อน
- **Date Added:** 2026-09-29
- **🔄 ปรับปรุง 2026-09-30 (รอบ 4) — ย้ายตรรกะออกจาก `.vue` และเปลี่ยนนิยามของ `baseline`:**
  - **ตรรกะย้ายไป `frontend/src/eventForm.ts`** (บริสุทธิ์ ไม่มี Vue) พร้อมเทสต์ 37 เคส
    `frontend/src/__tests__/eventForm.spec.ts` ⇒ โปรเจคนี้ **ไม่ mount component ในเทสต์**
    ดังนั้นตรรกะที่อยู่ในเทมเพลต = **ทดสอบไม่ได้เลย** ซึ่งเป็นเหตุผลที่ต้องแยกออกมา
  - ⭐ **`baseline` ไม่เป็น `null` อีกแล้ว** — โหมด "สร้างใหม่" ก็มีฐาน คือ
    `buildCreate(EMPTY_EVENT_FORM)` ⇒ **"สกปรก" กับ "สิ่งที่ `save()` ส่ง" เป็นตัวเลขตัวเดียวกัน**
    ไม่ต้องมีสาขา `if (mode === 'add')` อยู่ในตรรกะกันข้อมูลหาย (สาขานั้นคือที่ที่บั๊กซ่อน)
  - ⭐ **`toBaseline(e)` นิยามเป็น `buildCreate(rowToValues(e))` ไม่ใช่การเขียน object ขึ้นมาใหม่**
    ⇒ สองฝั่งของ diff ผ่านการ normalize ชุดเดียวกัน **โดยโครงสร้าง ไม่ใช่โดยวินัย**
  - 🐛 **บั๊กจริงที่การเขียนซ้ำแบบแยกคีย์ทำ (เจอตอนเขียนเทสต์ ไม่ใช่ตอนใช้):** `toBaseline`
    คืน `registration_deadline: ''` (จาก `toLocalInput(null)`) แต่ `buildCreate` คืน `null`
    ⇒ **เปิดกิจกรรมที่ "ไม่ตั้งกำหนดปิดรับ" แล้วกดบันทึกทันที ยิง `PATCH {registration_deadline: null}`
    ทุกครั้ง** ทั้งที่ไม่มีอะไรเปลี่ยน (เขียนทับด้วยค่าเดิม + audit log เปล่า + `updated_at` ขยับ)
    ⇒ ผู้ใช้ไม่เห็นอาการอะไรเลย แต่ "ประวัติการใช้งาน" เต็มไปด้วยรายการที่ไม่มีอะไรเปลี่ยน
    **และเมื่อมี `isDirty` (รอบ 4) บั๊กเดียวกันนี้จะกลายเป็นกล่อง "ยังไม่บันทึก" ที่โผล่ทั้งที่ไม่มีอะไรจะเสีย**
  - ⭐ **เพิ่ม `isDirty(baseline, values)` = `Object.keys(buildPatch(...)).length > 0`** —
    **นิยาม "ยังไม่บันทึก" มีที่เดียวในระบบ** และเป็นตัวเลขตัวเดียวกับที่ตัดสินใจยิง API พอดี
    ⚠️ **ห้ามเขียนเป็น `JSON.stringify(form) !== JSON.stringify(original)`** — จะนับ
    "พิมพ์แล้วลบออก" และ "เคาะท้ายช่อง" เป็นการแก้ ⇒ กล่องถามโผล่ทั้งที่ไม่มีอะไรจะเสีย
    · เทสต์ที่มีอยู่มีเคส **"`isDirty` ต้องเท่ากับ (patch ไม่ว่าง) ทุกเคส"** โดยเจตนา —
    เพื่อไม่ให้สองนิยามเพี้ยนจากกันในอนาคต

### 🔄 "ถอยกลับหน้าที่แล้วเมื่อแถวสุดท้ายหาย" — วาง **ใน `load()`** ไม่ใช่ไล่ใส่หลังทุก mutation
- **Context/Problem:** หน้ารายการที่แบ่งหน้า: ลบ/กู้คืนแถวสุดท้ายของหน้าสุดท้าย ⇒ หน้านั้นว่างเปล่า · แพตเทิร์นเดิมในโปรเจคคือ **ใส่ guard หลังทุก mutation** (`afterDelete` · `afterRestore` · `afterCreate`) ⇒ ลืมง่ายมาก และเพิ่ม mutation ใหม่ = ต้องจำว่าต้องใส่ · **และที่สำคัญกว่า: ในหน้านี้ `<PaginationBar>` อยู่ในกิ่ง `v-else` ของรายการ** ⇒ พอ items ว่าง ปุ่มเปลี่ยนหน้าหายไปด้วย ⇒ **ผู้ใช้ไม่มีทางกลับไปดูแถวที่เหลือได้เลย** (ไม่ใช่แค่ "เห็นหน้าว่าง")
- **Root Cause:** การ "ถอยกลับ" เป็นคุณสมบัติของ **สถานะที่โหลดมา** (ผลลัพธ์ + เลขหน้า) ไม่ใช่ของ **การกระทำ** ⇒ การผูกไว้กับ action ทำให้มี N จุดที่ต้องจำ · และ component แบ่งหน้าที่ **ซ่อนตัวเองเมื่อไม่มีข้อมูล** จะทำให้ทางออกหายไปพร้อมกับปัญหา
- **Correct Pattern/Solution:**
  ```ts
  async function load() {
    isLoading.value = true; hasError.value = false
    try {
      const res = await listEvents({ … offset: (page.value - 1) * PAGE_SIZE })
      items.value = res.items; total.value = res.total
      // ⚠️ หน้าที่ว่างเปล่าต้องถอยกลับ — วางที่เดียวตรงนี้ครอบทั้งลบ/กู้คืน/สร้าง
      if (items.value.length === 0 && page.value > 1) { page.value -= 1; await load() }
    } catch { hasError.value = true; items.value = []; total.value = 0 }
    finally { isLoading.value = false }
  }
  ```
  · **ห่วงจบแน่นอน** เพราะ `page.value` ลดลงแบบMonotonic ถึง 1 ⇒ เรียกซ้อนได้ไม่เกิน `page - 1` ชั้น
  · 📌 **เรียก `load()` ซ้ำแบบ recursive ได้ที่นี่** เพราะ `finally { isLoading = false }` ของชั้นในทำงานก่อนชั้นนอก ⇒ สถานะ loading จบถูกต้อง
  - ⚠️ **ต้องมีเงื่อนไข `page.value > 1`** ไม่งั้นหน้า 1 ที่ว่างจริง (ยังไม่มีข้อมูลเลย) จะเรียกตัวเองวนไม่จบ
  - 📌 **ทางเลือกที่ชัดกว่า: ย้าย `<PaginationBar>` ออกจากกิ่ง `v-else`** ให้แสดงเสมอเมื่อ `total > 0` ⇒ ผู้ใช้ไม่ต้องพึ่งการถอยอัตโนมัติเลย (ทำทั้งสองอย่างได้ และควรทำ)
  - 🚩 **สัญญาณของคลาสนี้:** หน้าที่มี guard แบบเดียวกันเขียนซ้ำหลายที่ · และ component ที่ "หายไปเมื่อไม่มีข้อมูล" ซึ่งเป็นทางออกของผู้ใช้
- **Date Added:** 2026-09-29

### 🪟 "คลิกพลาดทีเดียว ข้อมูลที่พิมพ์ไว้หายทั้งก้อน" = ฟอร์มอยู่ใน **modal ที่ฉากหลังกดปิดได้**
- **Context/Problem:** ฟอร์ม "สร้าง/แก้ไขกิจกรรม" เป็น modal ที่มี `<div class="absolute inset-0 …" @click="closeModal">` เป็นฉากหลัง ⇒ **คลิกพลาดครั้งเดียว (นิ้วโดนขอบจอบนมือถือ) ปิด modal แล้วทิ้งทุกอย่างที่พิมพ์ไว้ โดยไม่มีคำถามยืนยัน** · ผู้ใช้รายงานว่าโดนมา **~10 รอบ** และต้องพิมพ์ใหม่ทุกครั้ง · อาการที่ผู้ใช้บรรยายคือ *"คลิ๊กอะไรนิดหน่อย แม่งก็ปิดหน้าไปแล้ว ละค่าที่กูพิมพ์ไว้อ่ะ หายหมด"*
- **Root Cause:** modal เป็นที่ที่ **"ออกจากฟอร์ม" กับ "ทิ้งงาน" เป็นการกระทำเดียวกัน** — พื้นที่รอบนอกฟอร์มถูกผูกกับ "ยกเลิก" เงียบ ๆ · ในหน้านี้มี modal สองใบ (ฟอร์มกิจกรรม + รายชื่อผู้สมัคร) และ **ทั้งเรพไม่มี `onBeforeRouteLeave` / `beforeunload` / `confirm` เลยสักจุด** (grep = 0) ⇒ **ไม่มีตาข่ายรองรับแม้แต่ชั้นเดียว** ⇒ "modal ที่กดฉากหลังได้" กลายเป็นกับดักที่ไม่มีทางถอย
- **Correct Pattern/Solution:**
  - **ฟอร์มที่ผู้ใช้ต้อง *พิมพ์* ข้อมูล → หน้าเต็มหน้า (`<RouterView>` ปกติ) เสมอ** · ปุ่ม "ยกเลิก" เป็น *ปุ่มที่ผู้ใช้ต้องตั้งใจกด* ไม่ใช่พื้นที่ที่บังเอิญโดน
  - ใช้ modal เฉพาะงานที่ **"ปิดแล้วเสียเปล่าน้อย"** — ยืนยัน · เลือกจากรายการ · ดูข้อมูลสั้น ๆ
  - ⚠️ หน้าเต็มต้อง **เปิดตรง/refresh ได้จริง** ⇒ ต้องมี endpoint อ่านของตัวเอง (`GET /api/events/{id}`) **อย่าพึ่ง state ที่ส่งข้ามหน้าจอมา** — ไม่งั้น refresh แล้วเจอฟอร์มว่าง ซึ่งเป็นอีกอาการของข้อมูลหาย
  - 📌 **สร้าง 1 คอมโพเนนต์รับ 2 route** (`events/new` · `events/:id/edit`) เมื่อฟิลด์เหมือนกันเป๊ะ — ถ้าแยกสองไฟล์ วันหนึ่งจะมีคนแก้ normalization ที่เดียว ⇒ **นิยาม "ยังไม่บันทึก" ของสองหน้าเพี้ยนจากกัน** (ดู entry `isDirty`)
  - ⚠️ **ถ้าจำเป็นต้องมี modal จริง ๆ** ให้ปิดด้วยปุ่ม/`Esc` **เท่านั้น** อย่าผูกฉากหลังกับ "ทิ้งงาน"
- **Date Added:** 2026-09-30

### 🛡 กันข้อมูลหายต้องมี **3 ชั้น** — guard ชั้นเดียวไม่พอ เพราะผู้ใช้หลุดออกจากหน้าได้หลายทาง
- **Context/Problem:** หลังย้ายฟอร์มเป็นหน้าเต็มหน้า คำถามถัดไปคือ *"แล้วอะไรกันไม่ให้พิมพ์ค้างแล้วปิดทิ้ง"* · การใส่ `onBeforeRouteLeave` อย่างเดียว **มีรูอย่างน้อยสามรูที่ผู้ใช้หลุดไปได้จริง**
- **Root Cause:** การ "ออกจากหน้า" ไม่ได้เดินผ่าน router เส้นเดียว — มี **refresh/ปิดแท็บ** (ไม่ผ่าน router เลย) และ **`api.ts` ที่ `window.location.href = …` ตอน 401 ซึ่ง hard-nav ออกนอก router ทั้งหมด** ⇒ ต้องมีชั้นที่ทำงาน *นอก* กลไกของ router ด้วย และชั้นที่กู้คืนได้จริงเมื่อทุกอย่างล้มเหลว
- **Correct Pattern/Solution:** วางสามชั้นนี้คู่กันเสมอ
  | ชั้น | กลไก | กันเส้นทาง |
  |---|---|---|
  | 1 | `onBeforeRouteLeave` + `Swal.fire` ถาม | ปุ่มยกเลิก · ปุ่มย้อนกลับ · back ของเบราว์เซอร์ · เมนูข้าง · bottom tab |
  | 2 | `beforeunload` (`e.preventDefault()` **และ** `e.returnValue = ''`) | F5 · ปิดแท็บ · **401 hard-nav ที่หลุด router** |
  | 3 | `sessionStorage` autosave + ถาม "กู้คืนไหม" ตอน mount | **ครอบทุกกรณีข้างบน** — ชั้นที่กันถึงราก |
  ```ts
  // 🔴 ต้องเรียกที่ top level ของ <script setup> แบบ sync
  onBeforeRouteLeave(async (to) => {
    if (savedOk.value) return true            // ⚠️ ดู entry savedOk
    if (saving.value) return false            // กำลังบันทึก — อย่าให้ออกกลางคัน
    if (to.name === 'login' || !authStore.isAuthenticated) return true  // ออกจากระบบต้องผ่านได้เสมอ
    if (!dirty.value) return true
    const res = await Swal.fire({ icon: 'warning', title: 'ยังไม่ได้บันทึก', showCancelButton: true, … })
    if (res.isConfirmed) { clearDraft(); return true }
    return false
  })
  onMounted(() => window.addEventListener('beforeunload', onBeforeUnload))
  onBeforeUnmount(() => window.removeEventListener('beforeunload', onBeforeUnload))
  ```
  - 🔴 **`onBeforeRouteLeave` ต้องเรียกที่ top level แบบ sync** — ถ้าไปเรียกใน `onMounted` หลัง `await` **มันจะไม่ถูกผูกเลย** (มีแค่ warning ใน dev ที่คนมักไม่เห็น) ⇒ หน้าที่ "ดูเหมือนป้องกันครบ" แต่ไม่มีตาข่ายจริง
  - ⚠️ **ชั้น 1 ต้องข้ามเมื่อออกจากระบบ** — ไม่งั้น logout ได้ Swal ซ้อนสองอัน และผู้ใช้ **ติดกับอยู่ในฟอร์ม**
  - ⚠️ **ชั้น 3 ต้องมี `mode` + `eventId` ในร่าง** — ไม่งั้นร่างของ "สร้างใหม่" ไปโผล่ใน "แก้ไข #42" แล้วผู้ใช้กดกู้คืน ⇒ **ข้อมูลผิดใบ**
  - 🔴 **`baseline` ตอนกู้คืนต้องมาจากเซิร์ฟเวอร์/`EMPTY` เท่านั้น ห้ามตั้งจากร่างที่กู้คืน** — ไม่งั้น "กู้คืนแล้วกดบันทึก" ได้ patch ว่าง ⇒ **ไม่ยิง API เลย แต่ผู้ใช้เชื่อว่าบันทึกแล้ว** (แย่กว่าไม่มี autosave เพราะความเชื่อผิด ๆ ว่าเสร็จแล้ว)
  - ⚠️ **`try/catch` ทุก read/write ของ `sessionStorage`** — โหมดส่วนตัวบางเบราว์เซอร์ "มี" `sessionStorage` แต่ **โยน error ตอนเขียน** ⇒ ไม่ดักแล้วการพิมพ์รายตัวอักษรจะพัง (แนวเดียวกับ `pwa.ts`)
  - 📌 **`sessionStorage` ไม่ใช่ `localStorage` โดยเจตนา** — ร่างของเมื่อวานไม่ควรโผล่มาเอง · และเก็บร่าง**เฉพาะเมื่อ dirty** + **ลบร่างทันทีเมื่อค่ากลับมาเท่าตั้งต้น** ไม่งั้น "พิมพ์แล้วลบออก" จะทิ้งร่างค้างและรอบหน้าถามกู้คืนทั้งที่ไม่มีอะไรจะกู้
- **Date Added:** 2026-09-30

### 🔴 ตั้ง `savedOk = true` **ก่อน** `router.push` เสมอ — ไม่งั้นผู้ใช้เห็น "ยังไม่บันทึก" **หลังบันทึกสำเร็จ**
- **Context/Problem:** หน้ากันข้อมูลหายใช้ `onBeforeRouteLeave` ถามว่า "ยังไม่บันทึก ทิ้งไหม" · โค้ด `save()` ทำงานถูกทุกบรรทัด — ยิง API สำเร็จ, ล้างร่าง, แล้ว `router.push` กลับหน้ารายการ ⇒ **แต่กล่อง "ยังไม่บันทึก" โผล่ทับหลังกดบันทึกสำเร็จ** ซึ่งผู้ใช้จะอ่านว่า **"บันทึกไม่ติด"** ⇒ กดบันทึกซ้ำ หรือไม่กล้าออกจากหน้าเลย (คือ **คลาสเดียวกับบั๊กที่ทำให้ต้องย้ายฟอร์มเป็นหน้าเต็ม** — อาการ "ข้อมูลที่พิมพ์ไว้กับสิ่งที่ระบบคิดว่าเสร็จแล้วไม่ตรงกัน")
- **Root Cause:** **guard ไม่รู้จักการนำทางที่โค้ดตัวเองเป็นคนสั่ง** — มันเห็นแค่ "กำลังจะออกจากหน้าที่ dirty" ⇒ ยิงคำถามใส่ **การนำทางของตัวเอง** · และลำดับสำคัญ: ถ้าตั้ง `savedOk` *หลัง* `push` guard จะทำงานก่อนแล้ว
- **Correct Pattern/Solution:**
  ```ts
  await updateEvent(id, patch)
  savedOk.value = true      // 🔴 ก่อน push เสมอ — ต้องเป็นบรรทัดแรกหลัง API สำเร็จ
  clearDraft()
  await router.push({ name: 'event-management' })
  ```
  - ⚠️ **ทุกเส้นทางที่ "จบงานสำเร็จ" ต้องตั้ง `savedOk`** — **รวมเส้นทางที่ *ไม่* ยิง API** (patch ว่าง ⇒ บันทึกแล้วแต่ไม่มีอะไรเปลี่ยน) ซึ่งเป็นเส้นทางที่คนลืมบ่อยที่สุด
  - 📌 **เทสต์ UI จับคลาสนี้ไม่ได้** ⇒ ต้อง **กดทดสอบจริงบน staging ข้อ "บันทึกสำเร็จ → ต้องไม่ขึ้นกล่องยังไม่บันทึก"** เป็นข้อบังคับในเช็กลิสต์
  - 🚩 **สัญญาณของคลาสนี้:** ทุกครั้งที่เพิ่ม "guard กั้นการนำทาง" ให้ถามตัวเองว่า **"การนำทางใดที่โค้ดเราสั่งเอง"** แล้วปลดล็อกเส้นทางนั้นให้ครบ
- **Date Added:** 2026-09-30

### 📅 date picker: จับคู่ **local ↔ local** เท่านั้น — และคำอ่าน พ.ศ. เป็น *การแสดง* ไม่ใช่ *ค่าที่ส่ง*
- **Context/Problem:** เปลี่ยน `<input type="datetime-local">` เป็นไลบรารีเลือกวันที่ (`@vuepic/vue-datepicker@14`) · ไลบรารีให้/รับ **`Date` object** ส่วนฟอร์มเก็บ **สตริง** ⇒ ต้องมีสองฟังก์ชันแปลงไป-กลับ · ถ้าเขียนขาไปด้วย `toISOString()` (ซึ่งเป็นวิธีที่คนเขียนบ่อยที่สุด) **เวลาจะเลื่อน 7 ชั่วโมงแบบเงียบ ๆ** — ชนิดเดียวกับบั๊กใน entry `<input type="datetime-local">` แต่โผล่ในเส้นทางใหม่
- **Root Cause:** `Date` คือ *จุดเวลาหนึ่งจุด* ส่วน `"2026-10-15T09:00"` คือ *ตัวเลขบนหน้าปัด* · การแปลงไป-กลับจะเพี้ยนทันทีที่ **ขาเข้าตีความเป็นโซนหนึ่ง แล้วขาออกอ่านเป็นอีกโซนหนึ่ง** ⇒ กฎที่ปลอดภัยคือ **ใช้ local ทั้งคู่** (local constructor เข้า · local getters ออก) ⇒ อ่าน/เขียนตัวเลขชุดเดิมเสมอ **ไม่ว่าเครื่องผู้ใช้จะอยู่โซนไหน**
- **Correct Pattern/Solution:**
  ```ts
  export function inputToDate(value: string): Date | null {
    const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/.exec(value)
    if (!m) return null
    const [, y, mo, d, h, mi] = m
    const date = new Date(Number(y), Number(mo) - 1, Number(d), Number(h), Number(mi))  // local ctor
    if (dateToInput(date) !== value) return null   // 31 ก.พ. ถูก JS เลื่อนไป 2-3 มี.ค. เงียบ ๆ
    return date
  }
  export function dateToInput(date: Date): string {   // local getters — ห้าม toISOString()
    const p = (n: number) => String(n).padStart(2, '0')
    return `${date.getFullYear()}-${p(date.getMonth() + 1)}-${p(date.getDate())}T${p(date.getHours())}:${p(date.getMinutes())}`
  }
  ```
  - 🚫 **ห้ามใช้ `new Date(s)` (ISO parse) ในเส้นทางนี้** — สตริงที่ไม่มี tzinfo ถูกตีเป็น **local** ตามสเปคก็จริง แต่ `"2026-10-15"` (date-only) ถูกตีเป็น **UTC** ⇒ สองรูปแบบที่ดูเหมือนกันให้ผลต่างกัน 7 ชั่วโมง และ **type ไม่ช่วยจับเลย**
  - 🚫 **ห้ามตั้ง `timezone` prop ของ picker** — จะกลายเป็นสองระบบโซนปนกัน (ไลบรารีตีความข้างหนึ่ง เราเขียนอีกข้างหนึ่ง) = **บั๊กเงียบ ไม่มี error**
  - ⚠️ **ต้อง import CSS ของไลบรารี** (`@vuepic/vue-datepicker/dist/main.css`) — ลืมแล้วอาการคือ **"กดเปิดปฏิทินแล้วไม่มีอะไรขึ้น"** ซึ่งหน้าตาเหมือนบั๊กฉากหลังกดปิดของ modal เดิมเป๊ะ ⇒ จะไล่หาสาเหตุผิดที่ไปเป็นชั่วโมง
  - ⚠️ **`@vuepic/vue-datepicker@14` ส่งออกเป็น named export** — `import VueDatePicker from '…'` (default) ได้ `TS2613 has no default export` ⇒ `import { VueDatePicker } from '…'`
  - ⭐ **พ.ศ.: ไลบรารี (date-fns) ไม่รองรับพุทธศักราช** ⇒ ปล่อยช่องเป็น **ค.ศ.** (ตรงกับค่าที่ส่ง backend เป๊ะ ไม่มีขั้นตอนแปลง = ไม่มีที่ให้พลาด) แล้วแสดง **คำอ่าน พ.ศ. ใต้ช่อง**
  - ⚠️ **คำอ่านต้องใช้ `Date.UTC(...)` + `timeZone: 'UTC'`** — เราป้อน *ตัวเลขบนหน้าปัด* เข้าไป ไม่ใช่เวลาจริง ⇒ ถ้าใช้ local แล้วเครื่องอยู่โซนที่มี DST วันที่จะถูกเลื่อน = คำอ่านเพี้ยน · **UTC ไม่มี DST ⇒ ตัวเลขตรงกับที่ป้อนเสมอ**
  - ⚠️ **ระบุ `'th-TH-u-ca-buddhist'` ให้ชัด อย่าพึ่ง default ของ ICU** — บาง build ไม่มีข้อมูลฏิทินพุทธ ⇒ **เงียบ ๆ กลับมาเป็น ค.ศ.** แล้วคำอ่านบอก พ.ศ. ผิดโดยไม่มีอะไรฟ้อง
  - 📌 **เทสต์ต้องเทียบ "ค่าคงที่ที่เขียนตายตัว"** (`'2026-10-15T09:00'`) **ไม่ใช่คำนวณค่าที่คาดหมายด้วย `Date` เอง** — ถ้าคำนวณเอง เทสต์จะผ่านทุกโซน **รวมทั้งโซนที่โค้ดพัง**
- **Date Added:** 2026-09-30

### ✂️ ถอดโค้ดก้อนใหญ่ออกจากไฟล์ด้วยสคริปต์ — ค้น anchor **จากตำแหน่งเริ่ม** เสมอ และตรวจ element ที่ปิด *หลัง* บล็อก
- **Context/Problem:** ถอด modal สองใบ (315 บรรทัด) ออกจาก `EventManagement.vue` ด้วยสคริปต์ Python ที่หา `s.index('</template>')` เป็นจุดสิ้นสุด · ไฟล์มี `</template>` ของ `v-if` อยู่ **ข้างใน** (บรรทัด 684) ซึ่งมาก่อน modal (บรรทัด 792) ⇒ `s[:a] + s[b:]` **คัดลอกทั้งก้อนกลับมาซ้ำ** ไฟล์บวมผิดปกติ (ควรได้ ~816 บรรทัด กลับได้ 898) และ **โค้ดที่ "ลบแล้ว" ยังอยู่ครบ** · รอบถัดไปเจออีกสองจุด: `PAGE_SIZE` ถูกลบไปพร้อม `REG_PAGE_SIZE` (คนละของกัน) และ `</div>` ที่ปิด root ของเทมเพลตอยู่ **หลัง** modal ⇒ ถูกตัดไปด้วย ⇒ build ล้มด้วย `Element is missing end tag` (ซึ่ง `vue-tsc` **ไม่ฟ้อง** — เจอตอน `npm run build` เท่านั้น)
- **Root Cause:** `str.index(x)` หา **ตัวแรกของทั้งสตริง** ไม่ใช่ตัวแรกหลังจุดเริ่ม ⇒ เมื่อ marker สิ้นสุดเป็นแท็กที่ **ซ้อนกันได้** (`</template>` · `</div>` · `}`) การค้นหาแบบไม่มีจุดเริ่มจะได้ตำแหน่งที่ **น้อยกว่า** จุดเริ่ม แล้ว slice จะไม่ลบอะไรแต่ **ทำสำเนา** · และ marker ที่เป็นแท็กปิดจะอยู่ *นอก* บล็อกเสมอถ้าบล็อกนั้นเป็น *ลูกสุดท้าย* ของพ่อ
- **Correct Pattern/Solution:**
  ```python
  def cut(start, end, label):
      global s
      a = s.index(start)
      b = s.index(end, a)        # ⚠️ ค้นจาก a เท่านั้น
      assert b > a, label        # 🔴 assert — ถ้า end อยู่ก่อน start ต้องพังทันที ไม่ใช่เงียบ
      s = s[:a] + s[b:]
  ```
  - 🔴 **`assert b > a` ทุกครั้ง** — ราคาของการพังทันทีคือข้อความ error หนึ่งบรรทัด ราคาของการเงียบคือไฟล์ที่ดูปกติแต่ผิด
  - 🔴 **ตรวจ "ผลลัพธ์" ก่อนเขียนไฟล์**: `print(f'{ก่อน} → {หลัง} บรรทัด')` แล้วเทียบกับที่คาด · **ถ้าจำนวนไม่ลดลงตามที่คิด ให้หยุด**
  - ⚠️ **มองหาแท็กที่ปิด *หลัง* บล็อกนั้นด้วย** (root `</div>` · `</body>` · `}` ปิดฟังก์ชัน) — ตัดถึง "จุดสิ้นสุดที่หาได้" มัก **เลย** หรือ **ขาด** หนึ่งแท็ก
  - 📌 **`git diff --stat` ไม่พอ** — ไฟล์ที่คัดลอกซ้ำจะยัง "diff ผ่าน" · ใช้ **`npm run build`** เป็นด่านสุดท้ายเสมอ เพราะ **`vue-tsc` ตรวจ `TypeScript` ไม่ได้ตรวจความสมดุลของแท็กในเทมเพลต**
  - ✅ **ทางที่ปลอดภัยกว่า:** ตัดด้วย anchor `start`/`end` ที่ **ไม่ซ้อนกันได้** (คอมเมนต์ `<!-- ═══ -->` · docstring) แล้วให้ตัวแก้เองเป็นคนลบแท็กที่เหลือ
- **Date Added:** 2026-09-30

### 🟢 "เทสต์เขียว" ไม่ได้แปลว่า *คุณสมบัติที่คอมเมนต์อ้าง* ถูกคุมอยู่ — ถอดโค้ดออกแล้วลองรันก่อนเชื่อคอมเมนต์
- **Context/Problem:** คอมเมนต์ใน `datetime.ts` เขียนว่า `hourCycle: 'h23'` **ห้ามถอด** และอ้างอิง *"ดู `datetime.spec.ts` เคส `23:30`"* ⇒ อ่านแล้วเชื่อได้เต็มที่ว่ามีเทสต์คุม · **แต่พอถอดบรรทัดนั้นออกจริง เทสต์ทั้งไฟล์ยังเขียว 21/21** ⇒ การอ้างนั้น **ไม่จริงบนเครื่องนี้** · เคส `23:30` มีจริงและผ่านจริง แต่ **ผ่านทั้งตอนมีและตอนไม่มีบรรทัดนั้น** ⇒ มันยืนยัน *ผลลัพธ์* ไม่ได้ยืนยัน *บรรทัดที่อ้างว่าจำเป็น*
- **Root Cause:** **"มีเทสต์ชื่อตรงกับเรื่องนั้น" ≠ "เทสต์ล้มถ้าโค้ดนั้นหายไป"** — เทสต์ยืนยัน *พฤติกรรมที่สังเกตได้* ส่วนคอมเมนต์มักอ้าง *กลไกที่คิดว่าเป็นสาเหตุ* · เมื่อรันไทม์ปัจจุบันให้ผลถูกอยู่แล้วโดยปริยาย (Node 22 + full ICU ให้ `h23` เป็นค่า default) เทสต์จึงเขียวทั้งสองทาง ⇒ **ความเชื่อเรื่อง "มีเทสต์คุม" ทำให้คนต่อไปกล้าลบบรรทัดนั้น** ซึ่งเป็นกับดักเดียวกับ `hr` ที่ไม่มีใครกล้าแตะเพราะ "เดี๋ยวมีเทสต์จับ" ทั้งที่ไม่มี
- **Correct Pattern/Solution:**
  - 🔴 **ทุกครั้งที่คอมเมนต์อ้างว่ามีเทสต์คุม — ต้องพิสูจน์ด้วย mutation ก่อนเขียนประโยคนั้น** (ถอดออก → รัน → ต้องแดง → ใส่กลับ) · ถ้าไม่แดง **ให้เขียนตามจริง** ว่า "เทสต์บนเครื่องนี้จับไม่ได้ แต่ยังต้องคงไว้เพราะกันรันไทม์อื่น"
  - ⚠️ **"จำเป็น" กับ "มีเทสต์คุม" เป็นสองข้ออ้างที่ต่างกันคนละเรื่อง** — ข้อแรกอาจจริง (กัน ICU build แบบ small / เบราว์เซอร์ที่ default เป็น `h24`) โดยที่ข้อหลังเป็นเท็จ ⇒ **อย่าเขียนข้อหลังแทนข้อแรก**
  - 📌 **mutation ที่ "ไม่ถูกจับ" มีค่ามากกว่า mutation ที่ถูกจับ** — อันแรกเปิดช่องที่เราไม่รู้ว่ามี อันหลังแค่ยืนยันสิ่งที่รู้แล้ว ⇒ เวลามีงบจำกัด ให้เลือก mutate **ข้ออ้างในคอมเมนต์** ก่อน ไม่ใช่ mutate โค้ดที่เพิ่งเขียน
  - ✅ **ทางแก้ที่ถูกเมื่อเจอ:** *อย่าลบโค้ดทิ้ง* (โค้ดอาจถูกต้อง — แค่เทสต์พิสูจน์ไม่ได้บนเครื่องนี้) · **แก้คอมเมนต์ให้ตรงความจริง** + บอกว่าเทสต์จะเริ่มจับ *เมื่อไหร่* (เช่น "ตอนย้ายไปรันไทม์ที่ default เป็น `h24`") ⇒ คนอ่านรอบหน้าไม่ต้องมาไล่เองซ้ำ
---

> 📌 **ห้าบทเรียนต่อไปนี้มาจากการปิดรอบ 4 (กลุ่ม D — ระบบกิจกรรม · 30 ก.ย. 2026)**
> สองตัวแรกคือ **วิธีเทสต์ที่โกหก** — เทสต์เขียวทั้งที่ของพัง ซึ่งเป็นคลาสที่อันตรายกว่าเทสต์แดง
> สองตัวถัดมาคือ **กับดักของ vitest 4 / jsdom** ที่ทำให้เสียเวลาไล่หาสาเหตุผิดที่
> ที่เหลือคือ **กับดักของไลบรารี QR** ที่ความเสียหายเงียบและรู้ตัวช้ามาก

### 🧭 `router.resolve()` **ไม่ตาม redirect record** — เทสต์ที่ใช้มันจะเขียวทั้งที่การนำทางพัง
- **Context/Problem:** ต้องพิสูจน์ว่า `/` (หรือ path ที่ไม่มีจริง) ถูกพาไปหน้าปลีกทางที่ถูกต้อง ซึ่งกำหนดด้วย `redirect:` ใน route record · เขียนเทสต์ด้วย `router.resolve('/')` แล้วเช็ค `.name` — **ผ่าน** ⇒ สรุปว่าระบบถูก · พอเปิดเบราว์เซอร์จริง **ไม่ไป**
- **Root Cause:** `resolve()` เป็น **การคำนวณเส้นทาง ไม่ใช่การนำทาง** ⇒ สำหรับ record ที่มี `redirect:` มันคืน `name: 'not-found'` (หรือ match ที่ยัง *ไม่* แก้ redirect) ไม่ใช่ปลายทางจริง · **`redirect` ถูกประมวลผลในขั้นตอน navigation ของ `router.push()` เท่านั้น** ⇒ เทสต์ที่ใช้ `resolve()` กำลังทดสอบสิ่งที่ *ไม่ใช่* กลไกที่ผู้ใช้เจอ
- **Correct Pattern/Solution:**
  ```ts
  // ❌ เขียวตลอดแม้ถอด redirect: ออก
  expect(router.resolve('/').name).toBe('login')

  // ✅ ผ่านกลไกเดียวกับที่ผู้ใช้เจอจริง
  await router.push('/')
  await router.isReady()
  expect(router.currentRoute.value.name).toBe('login')
  ```
  · ⚠️ ต้อง `await router.isReady()` ก่อนอ่าน `currentRoute` ไม่งั้นอ่านค่าก่อนที่ navigation จะจบ (race ที่โผล่เป็นเทสต์ล้มสลับไปมา)
  · 📌 **กติกาทั่วไป: เทสต์ต้องเรียก *กลไก* ไม่ใช่ *แบบจำลอง* ของกลไก** — เมธอดที่ขึ้นต้นด้วย `resolve`/`match`/`can*`/`validate` ล้วนเป็น "คำนวณ" ไม่ใช่ "ทำ" ⇒ ถ้าสิ่งที่ต้องพิสูจน์คือ "แล้วมันเกิดขึ้นจริงไหม" เมธอดกลุ่มนี้ตอบไม่ได้
  - 🚩 **สัญญาณของคลาสนี้:** เทสต์ที่ไม่มี `await` ของ navigation เลย · หรือเทสต์ที่ผ่านแม้คอมเมนต์โค้ดการนำทางออก
- **Date Added:** 2026-09-30

### 🪟 ทดสอบสาขาที่เขียน `window.location` ใน jsdom ได้ — ด้วย `vi.stubGlobal('location', …)`
- **Context/Problem:** โค้ด 401 interceptor เขียน `window.location.href = '/login?…'` ตรง ๆ ⇒ ใน jsdom เจอ `Error: Not implemented: navigation (except hash changes)` และค่าที่อ่านกลับมาไม่ใช่ค่าที่โค้ดเขียน ⇒ เข้าใจผิดว่า "สาขานี้เทสต์ไม่ได้ ต้องรอ staging"
- **Root Cause:** jsdom **ไม่ implement navigation จริง** (โดยเจตนา — มันไม่ควรพา process ไปที่อื่น) และ `window.location` เป็น getter ที่ **เขียนทับไม่ได้ด้วย `= {}`** (silent fail ในโหมดไม่ strict) ⇒ ต้องแทนที่ *คุณสมบัติของ global* ไม่ใช่ตัว global
- **Correct Pattern/Solution:**
  ```ts
  type FakeLocation = { pathname: string; search: string; href: string }

  function stubLocation(pathname: string, search = ''): FakeLocation {
    const loc: FakeLocation = { pathname, search, href: '' }
    vi.stubGlobal('location', loc)   // ไม่ใช่ window.location = … (เงียบ ไม่มีผล)
    return loc
  }
  // …
  afterEach(() => vi.unstubAllGlobals())   // ⚠️ ขาดตัวนี้ = รั่วไปไฟล์ถัดไป
  ```
  · 💡 **โค้ดที่เทสต์ควรอ่าน `location` ผ่าน global เปล่า ๆ** (`location.pathname`) ไม่ใช่ `window.location` — ผูกกับ `window` ตรง ๆ แล้วจะแทนที่ยากขึ้นโดยไม่ได้อะไรกลับมา
  · ⚠️ **สิ่งที่พิสูจน์ได้คือ "การตัดสินใจ" ไม่ใช่ "การไปจริง"** — เทสต์ยืนยันว่าค่าที่โค้ด *ตั้งใจ* จะเขียนถูกต้อง การที่เบราว์เซอร์ไปจริงยังต้องดูที่ staging (§30.6) ⇒ **อย่าเขียนคอมเมนต์ว่า "พิสูจน์การนำทางแล้ว"**
- **Date Added:** 2026-09-30

### 🔁 สถานะระดับโมดูลมีสองแบบที่ต้องการตรงข้ามกันตอนเทสต์ — **latch ต้องรีเซ็ต · listener ห้ามรีเซ็ต**
- **Context/Problem:** บทเรียนก่อนหน้าในไฟล์นี้ (2026-09-28 · PWA install prompt) สอนว่า **"อย่า `vi.resetModules()` ต่อเทส"** · มาถึงรอบนี้ เจอเคสที่ **ต้อง** `vi.resetModules()` ทุกเทส — ถ้าจำกติกาเดิมแบบไม่แยกบริบทจะแก้ผิดทางทั้งสองเคส
- **Root Cause:** สถานะระดับโมดูลไม่ได้มีพฤติกรรมเดียวกัน — ต่างกันที่ **มันผูกกับ *อะไร* นอกโมดูล**:
  | สถานะระดับโมดูล | ตัวอย่าง | ต้องทำตอนเทสต์ |
  |---|---|---|
  | **latch / หน่วยความจำภายใน** (ค่าที่ไม่มีใครอื่นถือ) | `isRedirectingToLogin` (กัน 401 ซ้ำเด้งรัว) | **`vi.resetModules()` + `await import()` ต่อเทส** — ไม่งั้นเทสต์แรก latch ค้างให้ทุกตัวถัดไป |
  | **listener ที่แปะค้างนอกโมดูล** (`document`/`window`) | `onFirstGesture` ของ PWA | **import ครั้งเดียวตลอดไฟล์** — ไม่งั้น listener ทุกรุ่นค้างพร้อมกัน แล้วแตะครั้งเดียวถูกเรียกซ้ำ N ครั้ง เทสต์ล้มด้วยเหตุผลของการทดสอบเอง |
- **Correct Pattern/Solution:**
  ```ts
  async function loadApi(): Promise<ApiModule> {
    vi.resetModules()                 // ← latch เริ่มที่ false เสมอ
    return import('@/services/api')
  }
  beforeEach(async () => { localStorage.clear(); mod = await loadApi(); api = mod.api })
  ```
  · 🔑 **คำถามที่ตอบแล้วรู้ทันทีว่าต้องรีเซ็ตไหม: "โมดูลนี้ *แปะ* อะไรไว้กับวัตถุที่อยู่นอกโมดูลหรือเปล่า?"** — ไม่แปะ = รีเซ็ตได้เสมอ (ปลอดภัยกว่า เพราะทุกเทสต์เริ่มจากศูนย์จริง) · แปะ = ห้ามรีเซ็ต
  · 📌 ถ้าจำเป็นต้องรีเซ็ตทั้งที่โมดูลแปะ listener ทางออกคือ **ถอด listener ตอนรีเซ็ต** (เพิ่ม `dispose()` ให้โมดูล) ไม่ใช่ปล่อยให้ค้าง
  - 🚩 **สัญญาณของคลาสนี้:** เทสต์ที่ผ่านตอนรันเดี่ยวแต่ล้มตอนรันทั้งไฟล์ (หรือกลับกัน) ⇒ สงสัยสถานะระดับโมดูลก่อนเสมอ
- **Date Added:** 2026-09-30

### 🔍 เครื่องมือ probe ใน vitest 4 — `--reporter=basic` ไม่มีแล้ว และ `console.log` ในเทสต์ไม่โผล่
- **Context/Problem:** ต้องรู้ว่า mock ถูกเรียกจริงไหม / ค่าที่ได้กลางทางเป็นอะไร ⇒ ใช้วิธีที่จำมาจาก vitest รุ่นเก่า (`--reporter=basic` · `console.log` ในเทสต์) ⇒ ไม่เห็นอะไรเลยทั้งสองทาง แล้วเข้าใจผิดว่า "โค้ดไม่ทำงาน" ทั้งที่มันทำงาน
- **Root Cause:** (1) vitest 4 **ถอด `basic` reporter ออกแล้ว** ⇒ คำสั่งล้มด้วยข้อความเรื่อง reporter ซึ่งดูเหมือนปัญหาอื่น (2) vitest **ดัก `console.log` ของเทสต์ไปแต่งผลลัพธ์** ⇒ ในโหมดรันเป็นชุดมันไม่โผล่ตามที่คาด
- **Correct Pattern/Solution:** **ใช้ `expect()` เป็นเครื่องมือ probe — เขียนข้อความลงใน "คำถาม" ไม่ใช่ใน log**
  ```ts
  // ชั่วคราว: ทำให้แดงโดยเจตนา แล้วตัวข้อความ error จะบอกค่าจริง
  expect({ calls: mock.mock.calls.length, href: loc.href }).toBe('ดูค่าตรงนี้')
  ```
  · ข้อความที่ vitest พิมพ์ตอนแดงคือ **diff ของค่าจริงกับค่าที่คาด** ⇒ ได้ค่าจริงกลับมาโดยไม่ต้องดิ้นรนกับ reporter
  · 📌 ทางเลือก: `expect(...).toEqual('')` เพื่อดูโครงสร้างทั้งก้อน · หรือ **`expect.hasAssertions()`** เพื่อบังคับว่าเทสต์ที่ไม่มี assert ต้องล้ม (กันเทสต์ที่ "เขียวเพราะไม่ได้ตรวจอะไร")
  · ⚠️ **ลบ probe ทิ้งก่อนคอมมิต** — มันคือ `expect` ที่ตั้งใจให้แดง ซึ่งจะกลายเป็นเทสต์ที่ผิดความหมายถ้าตกค้าง
- **Date Added:** 2026-09-30

### 🔳 `qrcode-generator`: ค่า default **ตัดข้อความไทยทิ้งเงียบ ๆ** และฟังก์ชันแก้ที่มีอยู่ **เฉพาะบิลด์ CJS**
- **Context/Problem:** สร้าง QR จากข้อความ (มีทั้งโทเคน ASCII ล้วน และ URL) ด้วย `qrcode-generator` แล้วดัก UTF-8 ไว้ล่วงหน้า — ทดสอบ round-trip ข้อความไทยแล้ว **ได้ตัวอักษรมั่วกลับมาโดยไม่มี error ใด ๆ**
- **Root Cause:** สองชั้นที่ซ้อนกัน:
  1. **ค่า default ของ `stringToBytes` คือ `charCodeAt(i) & 0xff`** ⇒ ข้อความไทยถูกตัดเหลือ **1 ไบต์/ตัวอักษร** (ทดสอบจริง: `"กิจกรรมปลูกป่า"` → `"4\b##!…"`) · **ไม่มี exception** เพราะทุกอย่างยังเป็นไบต์ที่ "ถูกต้องตามชนิด" ⇒ ความเสียหายเงียบสนิท
  2. **`qrcode.stringToBytesFuncs['UTF-8']` มีอยู่เฉพาะในบิลด์ CJS (`dist/qrcode.js`)** — บิลด์ ESM (`dist/qrcode.mjs`) **ไม่มี `stringToBytesFuncs` เลย** และ Vite/เบราว์เซอร์โหลดตัว ESM (`exports.import`) ⇒ โค้ดที่อ้างถึงมัน **พัง/เงียบในเบราว์เซอร์ทั้งที่ผ่านด้วย `require()` ใน Node** (กับดักที่ทำให้เชื่อผลการทดลองผิด)
- **Correct Pattern/Solution:**
  ```ts
  // ⚠️ ไลบรารีอ่านค่านี้ตอน make() ไม่ใช่ตอน import ⇒ เขียนทับแบบนี้มีผลจริง
  qrcode.stringToBytes = (s: string): number[] => Array.from(new TextEncoder().encode(s))
  ```
  · **เขียน UTF-8 เองด้วย `TextEncoder`** — ได้ผลเหมือนกันทั้งสองบิลด์ และเหลือทางเดียวที่ต้องดูแล (ASCII ก็ไม่กระทบ เพราะ UTF-8 ของ ASCII = ไบต์เดิม ⇒ ไม่มีอะไรแลกมา)
  · 📌 **ต้องมีเทสต์ round-trip ข้อความไทยเสมอ** — มันคือด่านเดียวที่พิสูจน์ว่าการเขียนทับมีผล (ถ้าวันหน้าไลบรารีเปลี่ยนไปอ่านค่าตอน import เทสต์นี้จะจับได้)
  · ⚠️ ความเสียหายของคลาสนี้แพงเป็นพิเศษ: **QR ที่พิมพ์ติดหน้าโรงเรียนแล้วสแกนได้ตัวมั่ว = วันที่ต้องพิมพ์ใหม่ทั้งชุด** ⇒ กันที่จุดเดียว (โมดูลกลาง) ถูกกว่าหวังว่าทุกผู้เรียกจะส่งแต่ ASCII
  - 🚩 **สัญญาณของคลาสนี้:** ไลบรารีที่พึ่ง `Function.prototype.toString`/global monkey-patch และโปรเจกต์ที่มีทั้ง CJS/ESM ⇒ **ผลการทดลองใน Node ไม่ใช่หลักฐานของพฤติกรรมบนเบราว์เซอร์**
- **Date Added:** 2026-09-30

### 📷 `jsQR`: ต้องตรวจขนาดเฟรมเองก่อนเรียก และ `dontInvert` ตัดเวลาต่อเฟรมครึ่งหนึ่ง
- **Context/Problem:** ตัวอ่าน QR จากเฟรมกล้อง — เทสต์และรอบจริงผ่านปกติ แต่มีสาขาที่ข้อมูลสั้นกว่าที่ประกาศไว้ (เฟรมที่ยังไม่พร้อม/ถูกตัด) ซึ่ง **ไม่พัง แต่คืนผลมั่ว**
- **Root Cause:** ไลบรารี **ไม่ได้ตรวจ `data.length` เทียบ `width * height * 4`** ⇒ เมื่อข้อมูลสั้นกว่านั้น มันอ่านเลยขอบเขต ได้ `undefined` แล้วคำนวณต่อ ⇒ **คืนข้อความที่ดูเหมือนจริงแต่ไม่จริง** ซึ่งแย่กว่า throw มาก (ผู้ใช้จะได้รับ "โทเคน" ที่ผิด)
- **Correct Pattern/Solution:**
  ```ts
  if (width <= 0 || height <= 0) return null
  if (data.length < width * height * 4) return null   // ← ด่านที่ไลบรารีไม่มี
  const found = jsQR(data, width, height, { inversionAttempts: 'dontInvert' })
  return found ? found.data : null
  ```
  · **`inversionAttempts: 'dontInvert'`** — ค่า default `attemptBoth` จะลองอ่านภาพกลับสีด้วย = **เวลาต่อเฟรมเป็นสองเท่า** บนมือถือรุ่นเก่า · เราไม่เคยแสดง QR กลับสี (บัตรพื้นขาวเสมอ — SVG มี `<rect fill="white">`) ⇒ จ่ายฟรี · 🔁 ถ้าวันหน้าจะรองรับโหมดมืดเต็มรูปแบบ ค่อยเปิด (พร้อมยอมรับเวลาที่เพิ่ม)
  · ✅ **ผู้เรียกได้ `null` ที่ "เงียบแต่ถูก"** — ตรงกับสัญญาของฟังก์ชัน (ไม่พบ = `null`) ไม่ใช่คืนค่าที่สองความหมายปนกัน
- **Date Added:** 2026-09-30

### 🖼 QR ต้องเป็น **SVG** ไม่ใช่ raster — และ `btoa` ปลอดภัยได้เพราะ SVG ของไลบรารีเป็น ASCII ล้วน
- **Context/Problem:** เลือกรูปแบบภาพของ QR ที่ใช้ทั้งบนจอมือถือ (บัตรเช็คอิน) และ **การพิมพ์ติดหน้าโรงเรียน** (ลิงก์เชิญเข้าร่วม) · `createDataURL()` ของไลบรารีคืน **GIF** ซึ่งดูเหมือนใช้ได้ทันที
- **Root Cause:** ภาพ QR ต้อง **คมทุกขนาด** — raster ที่ถูกขยายจะ **เบลอตรงมุมจุด ซึ่งเป็นส่วนที่ตัวอ่านใช้หาตำแหน่ง (finder pattern)** ⇒ เบลอ = สแกนไม่ติด · และบนจอเล็กที่ถูกย่อก็เสียหายแบบเดียวกัน
- **Correct Pattern/Solution:**
  ```ts
  const svg = qr.createSvgTag({ cellSize: CELL_SIZE, margin: MARGIN, scalable: true })
  return `data:image/svg+xml;base64,${btoa(svg)}`
  ```
  · **`scalable: true`** ⇒ SVG ออกมาเป็น `viewBox` ล้วน ไม่มี width/height ตายตัว ⇒ ยืดหดตาม container โดยไม่ต้องรู้ขนาดล่วงหน้า และคมทุกระดับซูม
  · ⚠️ **`btoa` ใช้ได้เพราะ SVG ที่ไลบรารีสร้างเป็น ASCII ล้วน** — ถ้าวันหน้าฝังข้อความไทย/อีโมจิลงใน SVG ตรง ๆ จะโยน `InvalidCharacterError` ⇒ **ห่อ `try/catch` ที่ *ผู้เรียก* ไม่ใช่ที่ฟังก์ชันนี้** (ฟังก์ชันนี้ควรพังให้เห็น ไม่ใช่กลืนแล้วคืนภาพเปล่า)
  · 📌 **`QR_MAX_LENGTH` เป็น `export const` ให้เทสต์ใช้ค่าจริง** ไม่ใช่คัดลอกเลขไปเขียนซ้ำ — คัดลอกแล้ววันหน้าขยับเพดาน เทสต์จะยังผ่านด้วยเลขเก่า = เทสต์ที่โกหก
- **Date Added:** 2026-09-30

### 🏷 ฟังก์ชันสองตัวชื่อเกือบเหมือนแต่ตอบคนละคำถาม — จับได้เพราะ **อ่านไฟล์ปลายทางก่อน append** เท่านั้น
- **Context/Problem:** ต้องเพิ่มป้ายบอกว่า "ที่นั่งใกล้เต็ม" บนหน้าแรก · ตั้งชื่อช่วยไว้ในใจว่า `seatsLabel` ซึ่ง **มีอยู่แล้ว** ใน `types/event.ts` โดยตอบคำถามว่า *"เหลือกี่ที่"* (`"ว่างอีก 40 ที่"`) · คำถามใหม่คือ *"ควรต้องรีบไหม"* (`"เหลือ 3 ที่สุดท้าย"` / `"เต็มแล้ว"`) — **ถ้าใช้ชื่อเดิม ป้ายจะขึ้น "ว่างอีก 40 ที่" ซึ่งไม่ได้บอกอะไร และทำให้ป้ายจริงไม่มีความหมาย** (ปัญหาคลาสสิกของสัญญาณเตือน: ยิงทุกครั้ง = ไม่มีใครอ่าน)
- **Root Cause:** ชื่อที่บรรยาย *ข้อมูล* (`seatsLabel` = ป้ายของจำนวนที่นั่ง) ไม่ได้บอกว่าฟังก์ชันตอบ *คำถาม* อะไร ⇒ สองคำถามที่ต่างกันมากอยู่ในชื่อเดียวได้อย่างแนบเนียน · และความต่างที่สำคัญคือ **`null`** — `seatsLabel(null)` กับ `seatsWarning(null)` ให้ค่าเดียวกัน (`null`) แต่ **ความหมายต่างกัน**: ตัวแรกแปลว่า "ไม่รู้จำนวน" ตัวหลังแปลว่า "ไม่ต้องเตือน"
- **Correct Pattern/Solution:** **อ่านไฟล์ปลายทางก่อน append ทุกครั้ง** (ไม่ใช่แค่ `grep` ชื่อ เพราะ `grep` เจอชื่อแต่ไม่บอก *ความหมาย*) แล้วตั้งชื่อให้ต่างที่ *คำถาม*:
  | ฟังก์ชัน | ตอบคำถาม | `null` หมายถึง | `0` หมายถึง |
  |---|---|---|---|
  | `seatsLabel` | เหลือกี่ที่ | ไม่รู้จำนวน | "ว่างอีก 0 ที่" |
  | `seatsWarning` | ต้องรีบไหม | ไม่ต้องเตือน (ไม่จำกัด) | **"เต็มแล้ว"** ← ต้องขึ้น ไม่ใช่ซ่อน |
  · ⚠️ **`null` กับ `0` คนละเรื่องเด็ดขาด** — `null` = ไม่จำกัดที่นั่ง · `0` = เต็ม · การยุบรวมสองอย่างนี้เป็น falsy check (`if (!seats)`) เป็นบั๊กที่ผู้ใช้เห็นทันที ("เต็มแล้ว" หายไป) 
  · 📌 คอมเมนต์ในไฟล์ปลายทางควร **ชี้ไปหาอีกตัวหนึ่ง** ("อย่าใช้ `seatsLabel()` ที่นี่") — ไม่งั้นคนถัดไปก็เลือกผิดอยู่ดี
  - 🚩 **สัญญาณของคลาสนี้:** โมดูลที่มี helper ชื่อคล้ายกันตั้งแต่ 2 ตัวขึ้นไป · และฟังก์ชันที่คืน `null` กับค่าที่เป็น falsy ได้ทั้งคู่
- **Date Added:** 2026-09-30

### 🟢 `overflow` ที่ **บรรพบุรุษชั้นใน** ก็ฆ่า `sticky` เหมือนกัน — ไม่ใช่แค่ที่ root wrapper
- **Context/Problem:** หน้า "เพิ่มเติม" (`More.vue`) ต้องมีหัวกลุ่มแบบ `sticky top-0` · ใส่ `overflow-hidden` ที่การ์ดกลุ่มเพื่อให้มุมโค้ง (`rounded-card`) clip ลูกข้างใน ⇒ **หัวกลุ่มไม่ติดขอบบนเลย** วัดบน staging จริง: หัวกลุ่ม "ผู้ดูแล" อยู่ `top=176` ก่อนเลื่อน · เลื่อน `<main>` ลง 400px แล้วได้ `top=-224` (= 176−400) ⇒ ขยับตามเนื้อหาปกติ ไม่ได้ค้างที่ `mainTop=57`
- **Root Cause:** **กลไกเดียวกับ #534 ทุกประการ** แต่เคสนี้ `overflow-hidden` ไม่ได้อยู่ที่ root wrapper — อยู่ที่ **การ์ดที่เป็นบรรพบุรุษ *ในสุด* ของ element ที่ `sticky`** · `overflow != visible` ทำให้ div นั้นกลายเป็น **scroll container** ⇒ `sticky top-0` ไปติดกับ *กล่องที่ไม่มีการเลื่อน* แทนที่จะติดกับ `<main>` ⇒ **sticky กลายเป็น no-op เงียบ ๆ** (ไม่มี error ไม่มีคำเตือน — หน้าที่ดู "ก็ทำงานได้" แค่เลื่อนแล้วหัวหาย)
- **Correct Pattern/Solution:**
  - 🔴 **"ห้าม `overflow` ที่ root wrapper" ไม่ใช่กฎที่ครบ** — กฎที่ครบคือ **`sticky` จะเกาะกับ *scroll container ที่ใกล้ที่สุด*เสมอ** ⇒ ต้องไล่ขึ้นไปจากตัว element เองจนถึง `<main>` และยืนยันว่า **ไม่มีสักชั้นที่ `overflow != visible`**
  - ทางแก้ที่ไม่ต้อง clip อะไรเลย: **ยกความรับผิดชอบมุมโค้งไปที่ตัวหัวเอง** (`rounded-t-card` บนหัวกลุ่ม + `rounded-card` ที่การ์ด) เพราะพื้นหัวทึบ (`bg-surface`) ⇒ ถ้าไม่โค้งมันจะทับมุมโค้งการ์ดเป็นมุมเหลี่ยม · มุมล่างมาจากการ์ดเอง · **ถ้าลูกข้างในพื้นโปร่งทั้งหมด (แถว hover ใช้ `rounded-control` ของตัวเอง) ก็ไม่มีอะไรล้นออกไปให้ต้อง clip ตั้งแต่แรก**
  - 📌 **คอมเมนต์เตือนในคอมโพเนนต์ต้องบอก *กลไก* ไม่ใช่แค่ *ห้าม*** — คอมเมนต์เดิมของ `AppGroupHeader` เตือนแค่ `overflow-x-hidden` ที่ `<main>`/`max-w-7xl` ⇒ ไม่ครอบคลุมเคสที่ทำพังจริง
  - 🔴 **เวลาเทสต์ว่า "sticky ทำงานไหม" อย่า assert แค่ `top == mainTop` ที่ตำแหน่งเดียว** — `sticky` ถูก *จำกัดขอบเขต* ด้วยกล่องของพ่อแม่ ⇒ พอการ์ดนั้นเลื่อนพ้นจอ หัวจะ **ถูกดันขึ้น** ตามขอบล่างของพ่อ (ถูกต้องตามสเปก ไม่ใช่บั๊ก) · ให้วัด **หลายตำแหน่ง** แล้วยืนยันว่ามีช่วงที่ค้างพอดี: ตัวอย่างจริง (การ์ด 276px) — `scrollTop` 120–300 ค้างที่ 57 ✅ แต่ 400 ได้ 41 (ถูกดันออกเพราะการ์ดจบแล้ว) ⇒ **เทสต์ที่วัดจุดเดียวจะรายงานผลผิดทั้งสองทาง**
- **Date Added:** 2026-09-30

### 🔍 probe ของตัวเองก็โกหกได้ — เลือก selector ผิดแล้วรายงาน "บั๊ก" ที่ไม่มีอยู่
- **Context/Problem:** ตรวจหน้า "สมาชิก" บน staging หลังยุบเมนู แล้ว probe รายงานว่า **แถบ segment สูง 0px และ "ไม่พบลิงก์ไป `/app/users` เลย"** ⇒ ดูเหมือนรีเกรสชันร้ายแรง (segment เจ้าหน้าที่เข้าถึงไม่ได้ = ฟีเจอร์หาย) จริง ๆ แถบ **เรนเดอร์ครบ 57px สลับได้ปกติ** — probe หา `document.querySelectorAll('a')` แต่ `AppTabBar` เรนเดอร์เป็น **`<button>`** (สลับด้วย `router.push` ไม่ใช่ `<RouterLink>`) ⇒ ได้เซตว่างแล้วสรุปว่า "ไม่มี"
- **Root Cause:** probe ที่ **ยืนยันด้วย selector เดียว** จะตีความ "หาไม่เจอ" เป็น "ไม่มีอยู่จริง" เสมอ — ทั้งที่ความจริงคือ **selector ผิด** · และการรายงานว่า "เจอบั๊ก" ทั้งที่เกิดจากเครื่องมือตัวเอง **แย่กว่าไม่รายงาน** เพราะทำให้เสียเวลาตามแก้ของที่ไม่ได้พัง และลดความน่าเชื่อถือของข้อค้นพบจริงรอบข้าง
- **Correct Pattern/Solution:**
  - **ยืนยันผลลบด้วยสองมุมมองก่อนเรียกว่าบั๊ก**: ตัวที่ *มีอยู่* (นับ element ทุกชนิดในบริเวณนั้น + วัดขนาด/ตำแหน่ง) และตัวที่ *ผู้ใช้ทำได้จริง* (ลองกด/คลิกจริงแล้วดูว่าเกิดอะไร) — ถ้าการกดได้ผลตามคาด แปลว่า "ไม่พบ" เป็นปัญหาของ probe
  - 🔴 **"มี route/ปุ่มไหม" ให้ทดสอบด้วย *การกระทำ* ไม่ใช่ *การมีอยู่ของ element*:** ถ้า element ที่คาดว่าเป็น `<a>` จริง ๆ เป็น `<button>` การ assert ว่า "มีลิงก์" จะแดงทั้งที่ผู้ใช้กดได้ · ⇒ **กดแล้วตรวจปลายทาง** เป็นหลักฐานที่ตรงกับประสบการณ์ผู้ใช้ที่สุด
  - 📌 **ก่อนสรุปว่า "ของหาย" ให้ถามว่า "ถ้ามันหายจริง ผู้ใช้จะทำอะไรไม่ได้"** แล้วลองทำสิ่งนั้น — ถ้าทำได้ แปลว่ายังไม่หาย
  - ✅ **รูปแบบที่เชื่อถือได้ของ probe UI:** วัด *จำนวน element ทุกชนิด* ที่ไม่ใช่ main/header/aside + วัด `getBoundingClientRect()` + **ลองคลิกจริง** แล้วเทียบ `location.pathname` หลังคลิก — สามอย่างนี้ด้วยกันแทบจะไม่มีทางตีความผิด
- **Date Added:** 2026-09-30

### 🧪 เทสต์ที่ "พิสูจน์ว่าจับได้" ต้องลอง *ทำของให้พัง* ก่อน — ไม่ใช่แค่รันผ่าน
- **Context/Problem:** ต้องเพิ่มเทสต์กันเคส "มีคนเปลี่ยนชื่อ route แล้ว deep link ตก catch-all" · เทสต์ใหม่ผ่านตั้งแต่รันแรก ⇒ **ยังไม่รู้ว่ามันจับได้จริงหรือแค่ผ่านเพราะไม่ตรวจอะไร** — ซึ่งเป็นคลาสเดียวกับ #2219 ("เทสต์เขียวไม่ได้แปลว่าคุณสมบัติที่คอมเมนต์อ้างถูกคุมอยู่")
- **Root Cause:** เทสต์ที่ยังไม่เคยเห็นสถานะพัง ให้ข้อมูลเท่ากับไม่มีเทสต์ — และแย่กว่านั้นคือ **ให้ความมั่นใจปลอม** เพราะคนอ่านจะไม่ตรวจซ้ำ
- **Correct Pattern/Solution:**
  - **mutation test แบบเร็ว:** แก้ของจริงให้พัง *หนึ่งจุด* (เปลี่ยนชื่อ route / คืนค่าเก่า) → รันเทสต์ใหม่ **ต้องแดง** → **ย้อนกลับ** → รันอีกครั้งต้องเขียว
  - ⭐ **ตัวชี้วัดที่คมที่สุดคือ *เทสต์เก่า* ระหว่างที่ของพัง** — ถ้าเทสต์เก่ายังเขียวด้วย แปลว่าเรากำลังปิดช่องว่างจริง (กรณีนี้: `deepLinkRoutes.spec.ts` **แดง 4 ตัว** ขณะที่ `deepLink.spec.ts` **เขียวทั้งไฟล์** ⇒ ยืนยันว่าช่องว่างมีจริง ไม่ใช่แค่เขียนเทสต์ซ้ำ)
  - 🔴 **ตรวจว่า mutation ถูกย้อนแล้วจริง** (`grep -c <ค่าที่แก้>` ต้องได้ 0) — ไม่งั้นของพังค้างอยู่ในคอมมิต
  - ⚠️ **mutation test ยังใช้ *ห้ามตัวเองตั้งกฎผิด* ได้ด้วย** — ตั้ง invariant ว่า "route ใน `segmentGroup` เดียวกันต้องชื่อหน้าเท่ากัน" เขียนเทสต์ → **แดงทันที** เพราะคู่ `issues` ที่มีอยู่เดิมไม่เป็นไปตามกฎนั้น ⇒ กฎที่เพิ่งตั้งเองไม่ใช่กฎของเรพ ⇒ **ถอดเทสต์และคืนค่าเดิม** ดีกว่าไปแก้ของเดิมให้เข้ากฎที่เพิ่งคิดได้
- **Date Added:** 2026-09-30

### 🎭 CSS ที่ "ซ่อน" element ไม่ได้เอามันออกจาก DOM — `data-testid` ซ้ำแล้ว Playwright strict mode ระเบิด
- **Context/Problem:** `IssueDetail.vue` ต้องแสดงปุ่มรองสองหน้าตาต่างกันตามขนาดจอ — มือถืออยู่ในแผ่น `⋯` · เดสก์ท็อปเป็นปุ่มเรียงในแถว ⇒ เขียนเป็นสองบล็อกแล้วซ่อนฝั่งเดสก์ท็อปด้วย `hidden lg:inline-flex` · วัดบน staging จริงที่ 360dp ตอนเปิดแผ่น:
  ```
  data-testid ทั้งหน้า: 2 ["change-dest-btn","change-dest-btn"]
  ```
  ⇒ **`page.getByTestId('change-dest-btn')` จะล้มด้วย strict mode violation ทันทีที่จอเล็กและแผ่นเปิดอยู่**
- **Root Cause:** `hidden` = `display:none` ⇒ **element หายไปจากสายตา แต่ยังอยู่ใน DOM** · **Playwright นับทุกโหนดที่ match selector โดยไม่สนใจว่ามองเห็นไหม** (ต่างจาก locator ที่ resolve แล้วค่อยเช็ค visibility) ⇒ "ซ่อนด้วย CSS" ไม่ใช่การรับประกันว่า "มีชุดเดียว"
  · ยิ่งกว่านั้น **`v-if` บน `AppSheet` ไม่ช่วยอะไรเลยในเคสนี้** — ตัวซ้ำไม่ใช่แผ่น แต่เป็น **แถวเดสก์ท็อปที่ถูกซ่อนด้วย CSS** ซึ่งอยู่ใน DOM ตลอดเวลา
  · และโหนดที่ซ่อนไว้ **ตรวจด้วยตาไม่เจอ** ⇒ เป็นบั๊กที่รอเทสต์ในอนาคตมาตายโดยไม่มีใครรู้สาเหตุ
- **Correct Pattern/Solution:**
  - 🔴 **ถ้าต้องการ "มีชุดเดียวใน DOM" ต้องใช้ `v-if` + รู้ขนาดจอจาก JS ไม่ใช่ CSS** — สร้าง `src/composables/useMediaQuery.ts` (คืน `ref`, อ่าน `mql.matches` **ซิงโครนัสตอน setup** เพื่อไม่ให้เฟรมแรกกระพริบ, `onScopeDispose` ถอด listener, และ **คืน `false` เมื่อไม่มี `matchMedia`** ตามแนวที่ `pwa.ts` ทำอยู่ ⇒ เทสต์ใน jsdom ได้เส้นทางจอเล็กซึ่งปลอดภัยกว่า)
  - ⚠️ **เบรกพอยต์ใน JS ต้องตรงกับ Tailwind** — `useIsDesktop()` = `(min-width: 1024px)` คู่กับ `lg` · ถ้าวันหนึ่ง override `screens` ต้องแก้ทั้งสองที่
  - ✅ **หลักที่ได้:** ใช้ CSS ซ่อนเมื่อ "ความต่างเป็นแค่หน้าตา" · ใช้ `v-if` เมื่อ "ความต่างคือจำนวนโหนด" — อันหลังมีผลกับ **selector ของเทสต์, ลำดับโฟกัส, และการนับ element** ทั้งหมด
  - 📌 **วิธีตรวจที่เร็วและตรง:** `page.locator('[data-testid]').evaluateAll(els => els.map(e => e.dataset.testid))` แล้วดูว่า **มีชื่อซ้ำไหมในทุกสถานะที่เปิดได้** (ปิด/เปิดแผ่น · จอเล็ก/จอใหญ่) — การเช็คแค่สถานะเดียวจะไม่เจอเคสนี้
- **Date Added:** 2026-09-30

### 📐 `sticky bottom-0` วัด "ทับเนื้อหาไหม" จาก bounding box ตอนแถวกำลังเลื่อนผ่าน = false positive
- **Context/Problem:** probe ตรวจแถบปฏิบัติการใน `IssueDetail.vue` รายงานว่า **"แถบทับการ์ดสุดท้าย 62px"** (62 = ความสูงแถบพอดี น่าสงสัย) ⇒ เกือบไปแก้ `bottom` ของแถบที่ถูกต้องอยู่แล้ว · วัดใหม่ด้วย `getBoundingClientRect()` ของทุกการ์ดคู่กับแถบ **ที่ตำแหน่งเลื่อนสุด** ได้: การ์ดสุดท้ายจบที่ `590` · แถบเริ่ม `606` ⇒ **ห่าง 16px ไม่ทับกันเลย**
- **Root Cause:** การวัดผิด 2 ชั้น
  1. `bar.parentElement.children` **มีตัวแถบเองรวมอยู่ด้วย** ⇒ แถบ "ทับตัวเอง" เต็มความสูง = 62px พอดี (ตัวเลขที่ควรสงสัยตั้งแต่แรก)
  2. ถึงกรองตัวเองออกแล้ว **การ์ดที่กำลังเลื่อนผ่านแถบก็ยัง overlap ตามธรรมชาติ** — `sticky` ทำหน้าที่ *ลอยทับเนื้อหา* อยู่แล้ว ⇒ **การ overlap ระหว่างเลื่อนไม่ใช่บั๊ก · บั๊กคือการ overlap ตอนเลื่อนสุด** (ซึ่งแปลว่าเนื้อหาท้ายสุดเอื้อมไม่ถึง)
- **Correct Pattern/Solution:**
  - 🔴 **วัด `sticky` ที่ "ตำแหน่งเลื่อนสุด" เท่านั้น** แล้วถามคำถามเดียว: *องค์ประกอบสุดท้ายของเนื้อหาจบก่อนขอบบนของแถบไหม* (`lastCard.bottom <= bar.top`) — นี่คือเงื่อนไขที่ตรงกับ "ผู้ใช้เอื้อมถึงเนื้อหาครบไหม"
  - ⚠️ **เมื่อตัวเลขที่ได้เท่ากับความสูงของ element ที่กำลังวัดพอดี (62 = bar height) ให้สงสัยว่า element ทับตัวเอง** — เป็นสัญญาณของ selector ที่รวมตัวเองเข้ามา มากกว่าข้อบกพร่องจริง
  - 📌 **ยืนยันด้วยภาพเสมอเมื่อข้อสรุปเป็น "ไม่ทับ"** — เรื่องตำแหน่ง/การทับเป็นเรื่องที่ตาตัดสินได้ตรงกว่าเลขที่คำนวณเอง (เคสนี้ภาพยืนยันตรงกับ rect)
  - 🔗 หลักเดียวกับบทเรียน "probe ของตัวเองก็โกหกได้" — **การวัดที่ผิด ไม่ใช่ข้อบกพร่องของโค้ด** และถ้าบันทึกไม่ดี คนถัดไปจะไป "แก้" ของที่ถูกอยู่แล้ว
- **Date Added:** 2026-09-30

### 🧮 ไลบรารีสร้างปุ่มที่มองไม่เห็นไว้ล่วงหน้า — นับ DOM node ไม่เท่ากับนับสิ่งที่ผู้ใช้เห็น
- **Context/Problem:** ตรวจกล่องยืนยันใน `NewIssue.vue` (ร่างจะหาย) บน staging แล้วอ่านปุ่มในกล่องได้:
  ```
  ["ออกจากหน้านี้", "No", "อยู่ต่อ"]      ← มี "No" โผล่มาเป็นปุ่มที่สาม
  ```
  ⇒ เกือบสรุปว่า "มีปุ่มอังกฤษเกินมาใบหนึ่ง เป็นบั๊ก UX" · พอวัดกล่องจริงกลับได้:
  ```
  swal2-confirm "ออกจากหน้านี้"  visible:true   w:125 h:44
  swal2-deny    "No"             visible:false  w:0   h:0
  swal2-cancel  "อยู่ต่อ"        visible:true   w:74  h:44
  ⇒ จำนวนปุ่มที่มองเห็นจริง = 2
  ```
  และภาพครอปกล่องยืนยันว่ามี 2 ปุ่มไทยตามที่ออกแบบ
- **Root Cause:** **SweetAlert2 สร้าง template ของทุกปุ่มไว้ใน DOM ตั้งแต่แรก** (`confirm`/`deny`/`cancel`/`close`) แล้ว**ซ่อนด้วย `display:none`** ตามแฟล็ก ⇒ `swal2-deny` มีอยู่เสมอแม้ `showDenyButton` เป็น `false` (ค่าตั้งต้น) · **`allTextContents()` / `querySelectorAll().length` ไม่กรอง visibility** ⇒ ได้ปุ่มผีติดมาในผลวัด
  · เป็น **ด้านกลับของบทเรียน "CSS ซ่อนไม่ได้เอาโหนดออกจาก DOM"** — รอบนั้นโหนดที่ซ่อนทำให้ `data-testid` ซ้ำ · รอบนี้โหนดที่ซ่อนทำให้ **ตัวเลขที่นับได้เกินจริง**
- **Correct Pattern/Solution:**
  - 🔴 **กรองด้วย `visible` เสมอเมื่อนับหรืออ่าน element** — ใช้ `getByRole(...)` (Playwright ตัดโหนดที่ไม่อยู่ใน a11y tree ออกให้เอง) แทน `locator('.swal2-actions button')` และถ้าต้องอ่าน DOM ตรง ๆ ให้เช็ค `getComputedStyle(el).display !== 'none'` **บวก** `rect.width > 0` (ต้องทั้งคู่ — `display:none` ให้ rect 0 แต่องค์ประกอบอื่นก็ให้ 0 ได้)
  - ⚠️ **"มีปุ่ม/ข้อความเกินมา" ให้วัดกล่องจริงก่อนสรุป** — ตัวเลข `w:0 h:0` คือหลักฐานตัดสินที่เร็วกว่าไปอ่าน source ของไลบรารี (บทเรียนเดียวกับ "ตัวเลข 62 = ความสูงแถบพอดี ⇒ สงสัย selector")
  - 📌 **ถ้าข้อสรุปคือ "มีของเกิน" ให้ถ่ายภาพกล่องมาดูเลย** — ตัดสินถูก/ผิดได้ในคำตอบเดียว ไม่ต้องเดาจาก source
- **Date Added:** 2026-09-30

### 🖱️ `hover:` ที่ติดมากับ element ทำให้ computed style ไม่ตรงกับคลาสพื้นฐาน
- **Context/Problem:** วัดขอบของตัวเลือกปลายทาง 3 ใบใน `NewIssue.vue` ตอน **"ยังไม่เลือกอะไร"** แล้วพบว่าใบที่สามคำนวณขอบได้ไม่เท่าเพื่อน:
  ```
  dest-normal  border-color: rgb(231,231,234)   ← border-line
  dest-vote    border-color: rgb(231,231,234)   ← border-line
  dest-talk    border-color: rgb(138,143,152)   ← border-ink-3  ← ทำไม?
  ```
  ทั้งสามมี `aria-pressed="false"` และคลาสที่สกัดออกมาได้ข้อความเดียวกัน ⇒ ดูเหมือนบั๊ก CSS เฉพาะตัว (`border-ink-3` ชนะ `border-line` เฉพาะใบนี้) ⇒ **เกือบไปตามหาปัญหา specificity ที่ไม่มีอยู่**
- **Root Cause:** ตัวเลือกที่ยังไม่ถูกเลือกใช้คลาส `hover:border-ink-3` — **ตัวสกัดคลาสตัด prefix `hover:` ทิ้ง** จึงเห็นเป็น `border-ink-3` เหมือนเป็นคลาสพื้นฐาน · และ **`getComputedStyle` คืนค่าที่ *กำลังเป็นอยู่จริง* ณ ขณะนั้น รวม hover ด้วย** ⇒ เมาส์ของ Playwright ไปค้างอยู่บน `dest-talk` (ตำแหน่งChangedไปหลังเปลี่ยนขั้น 3 → layout ขยับ → ใบนั้นมาอยู่ใต้เคอร์เซอร์) ขอบเข้มนั้นคือ **hover ที่ออกแบบไว้** ไม่ใช่บั๊ก
- **Correct Pattern/Solution:**
  - 🔴 **ตัวสกัดคลาสต้องเก็บ prefix ของ variant ไว้ด้วย** — ใช้ `/(?:[\w-]+:)*[\w-]+/` แล้วคง `hover:` ไว้ ไม่ใช่ตัดทิ้ง ไม่งั้น **variant จะปลอมตัวเป็นคลาสพื้นฐาน**
  - ⚠️ **ก่อนสรุปว่า "CSS ขัดกัน" ให้ย้ายเมาส์ออกก่อนวัด** — `await page.mouse.move(0, 0)` (หรือวัดผ่าน `el.matches(':hover')` เพื่อยืนยันว่าโหนดนั้นกำลังถูก hover อยู่จริง) · `getComputedStyle` ไม่แยก "ค่าที่ประกาศ" ออกจาก "ค่าที่เกิดจาก state"
  - ✅ **`aria-pressed` คือแหล่งความจริงที่เชื่อได้กว่าสี** — ทั้งสามใบเป็น `false` ⇒ ไม่มีอะไรถูกเลือกจริง (สอดคล้องกับข้อกำหนด "ห้ามเลือกปลายทางไว้ก่อน" ของ R3.1)
  - 🔗 ต่อจากบทเรียน "probe ของตัวเองก็โกหกได้": **การวัดที่ผิด ≠ ข้อบกพร่องของโค้ด** — เคสนี้เสียเวลาไปกับการหาบั๊ก CSS ที่ไม่มีอยู่จริง
- **Date Added:** 2026-09-30

### 📸 `fullPage: true` ใช้ไม่ได้เมื่อ `<main>` เป็น scroll container (R0.3.1 เปลี่ยน shell)
- **Context/Problem:** ถ่าย screenshot หน้า `/app/settings` ด้วย Playwright (`fullPage: true`) เพื่อตรวจด้วยตา แล้วได้ภาพ **แค่การ์ดใบแรก** ทั้งที่หน้าในการ์ดมี 5 ใบ · ตรวจ DOM พบ `h2` ครบทั้ง 5 (`["การแจ้งเตือน","แจ้งเตือนถึงมือถือ","ช่วงเวลาไม่ส่งแจ้งเตือน","ติดตั้งแอป","บัญชี"]`) ⇒ **เนื้อหาอยู่ครบ แต่ภาพไม่ครบ** ⇒ เกือบสรุปผิดว่า "การ์ดหาย"
  · อาการเดียวกันโผล่กับ `page.evaluate(() => document.documentElement.scrollHeight)` — คืนความสูงแค่หน้าจอเดียว
- **Root Cause:** `fullPage` ของ Playwright วัดความสูงจาก **document** (`documentElement.scrollHeight`) แต่ R0.3.1 ออกแบบ shell ใหม่เป็น
  `<div class="flex h-[100dvh] overflow-hidden"><main class="flex-1 overflow-y-auto">` ⇒ **document สูง = viewport เสมอ** ส่วนที่เลื่อนได้จริงคือ `<main>`
  ⇒ `fullPage` จึงจับได้เท่า viewport · **เป็นราคาที่ต้องจ่ายของการมี app shell ที่ scroll เอง** ซึ่งเป็นดีไซน์ที่ต้องการ
- **Correct Pattern/Solution:**
  - 🔴 **ถ่าย "ทั้งหน้า" ด้วย viewport สูง ๆ แทน `fullPage`** — `await page.setViewportSize({ width, height: 2600 })` แล้วค่อย `screenshot()` (ถอยกลับขนาดจริงทีหลังถ้าต้องดู fold)
    ```js
    const tall = async (name) => {
      await page.setViewportSize({ width, height: 2600 })
      await page.waitForTimeout(700)          // ให้ layout + ฟอนต์ไทย settle
      await page.screenshot({ path: `${OUT}/${name}-full.png` })
      await page.setViewportSize({ width, height })
      await page.screenshot({ path: `${OUT}/${name}.png` })   // ภาพที่ผู้ใช้เห็นจริง
    }
    ```
  - ⚠️ **`scrollHeight`/`fullPage` ที่ "ดูสั้นผิดปกติ" ไม่ใช่หลักฐานว่าเนื้อหาหาย** — ให้นับ element จริง (`locator('h2').allInnerTexts()`) เทียบก่อนสรุป
  - 🔗 ต่อจากบทเรียน "probe ของตัวเองก็โกหกได้" และ "CSS ซ่อนไม่ได้เอาโหนดออกจาก DOM" — **เครื่องมือวัดที่ออกแบบมาสำหรับ scroll container ชนิดหนึ่ง ใช้วัดอีกชนิดไม่ได้** · และเมื่อ shell เปลี่ยน วิธีตรวจก็ต้องเปลี่ยนตาม
- **Date Added:** 2026-09-30

### 🕳️ สตริงว่าง ≠ `null` — `filter(Boolean)` กลืน `''` แล้วชื่อผู้ใช้หายทั้งหน้า
- **Context/Problem:** หน้าโปรไฟล์ (`/app/profile`) แสดง **หัวเรื่องที่ใหญ่ที่สุดของหน้าว่างเปล่า** — การ์ดตัวตนมี avatar + ป้ายบทบาท + ห้อง ครบ แต่ **ไม่มีชื่อ** และกินที่ว่างเป็นแถบใหญ่
  · `GET /api/students/me/profile` ตอบ: `first_name: ""`, `last_name: ""`, `prefix: null` แต่ **`full_name: "E2E e2estu"`**
- **Root Cause:** `fullName` เขียนว่า `[prefix, first_name, last_name].filter(Boolean).join(' ').trim()` ⇒ `filter(Boolean)` ตัด **ทั้ง `null` และสตริงว่าง** ทิ้ง ⇒ ได้ `''`
  · **สตริงว่าง ≠ `null`** — ค่ามาจาก DB เป็น `''` **ไม่ใช่ `NULL`** ⇒ `null`-check ทุกแบบที่เขียนกันตามปกติ **ไม่จับเคสนี้**
    · ⚠️ **แก้ความเข้าใจผิดของตัวเอง (ตรวจซ้ำแล้ว):** คอลัมน์เป็น `first_name TEXT` **nullable ไม่มี default** (`backend/core/init_db.py:74`) ⇒ **backend ไม่ได้เป็นคนใส่ `''`**
    · ต้นตอจริงคือ **`backend/scripts/e2e_seed.py` เขียน `''` ตรง ๆ** · วัดบน staging: `students` ทั้งตาราง **3172 แถว — เป็นสตริงว่างแค่ 3 แถว และเป็นบัญชี `e2e*` ทั้งสามตัว** (อีก 3169 แถวมีชื่อจริง) ⇒ **เคสนี้เกิดกับบัญชีที่ seed เท่านั้นในทางปฏิบัติ**
    · ⇒ **บทเรียนไม่ได้อยู่ที่ "backend ทำอะไร" แต่อยู่ที่ "โค้ดต้องทนสตริงว่างได้"** — เพราะบัญชี seed/dev คือบัญชีที่ใช้ทดสอบทุกครั้ง ⇒ **หน้าที่ดูไม่พังจะพังเฉพาะตอนเทส** ซึ่งเป็นอาการที่หลอกที่สุด
  · และ `users.full_name` ที่มีค่าอยู่แล้ว **ไม่ถูกใช้เลย** ทั้งที่อยู่ใน response เดียวกัน
- **Correct Pattern/Solution:**
  - 🔴 **ค่าที่ "ประกอบจากหลายส่วน" ต้องมี fallback ระดับสุดท้ายเสมอ** — `[..].filter(Boolean).join(' ').trim() || p.full_name || p.username`
  - ⚠️ **`filter(Boolean)` เป็นกับดักเดียวกับ `??`** — `??` จับแค่ `null`/`undefined`, `filter(Boolean)` จับ `''`/`0`/`false` เพิ่ม · ทั้งคู่ตัดสินจากค่าที่ *เป็น* ไม่ใช่จากค่าที่ *ควรจะมาแทน* ⇒ **ต้องมี `||` ต่อท้ายเสมอเมื่อปลายทางเป็นข้อความที่ผู้ใช้ต้องอ่าน**
  - 🔴 **หน้าที่มีคำถามเดียว ("ฉันเป็นใคร") — คำตอบว่างเปล่าคือ failure ที่แย่ที่สุด** และ **ไม่มีเทสต์ไหนจับได้** (ไม่มีเทสต์ที่ render view) ⇒ เจอได้ด้วยตาเท่านั้น
  - 📌 **ไม่ใช่ regression ของรอบนั้น** — computed ตัวเดิมมีมาก่อนแล้ว · **การ rewrite ไฟล์เป็นโอกาสที่ดีที่สุดที่จะเจอบั๊กเดิม** เพราะต้องอ่านทุกบรรทัดอยู่แล้ว
- **Date Added:** 2026-09-30

### 🚪 ถอด "ทางเข้าที่ซ้ำ" ออกแล้ว route ที่ `hiddenFromMenu` กำพร้า — เทสต์ไม่จับ
- **Context/Problem:** R3.3 ถอด dropdown `⋮` (แก้ไขโปรไฟล์ · เปลี่ยนรหัสผ่าน · ออกจากระบบ) ออกจากหน้าโปรไฟล์ เพราะเป็น **ทางเข้าชุดที่สองของปลายทางเดียวกับกลุ่ม "บัญชี" ในหน้า More** ซึ่งเป็นสิ่งที่ผู้ใช้เรียกว่า "เยอะเกินไป" ตรง ๆ
  · แต่ `profile-edit` และ `profile-password` เป็น **`hiddenFromMenu: true`** ใน `constants/nav.ts` ⇒ ถ้าถอดเฉย ๆ **สอง route นั้นจะไม่มีทางเข้าเลยทั้งแอป**
- **Root Cause:** **ไม่มีสัญญาณเตือนไหนจับได้เลย:**
  · `type-check` ไม่จับ — route ยังอยู่ในเรพและ resolve ได้
  · `navRegistry.spec.ts` **ไม่จับ** — fixture `MENU_TODAY` assert ว่าแถวยัง**มีอยู่ในโมเดลเมนู** (`reachableFromMenu()` เทียบกับ `nav.groups`) ซึ่งเป็นความจริงเสมอ · แต่มัน **ไม่ได้บอกว่ามี UI ไหนวาดแถวนั้นจริง** — `hiddenFromMenu` แปลว่า "มีข้อมูล แต่ไม่มีใครวาด" ตั้งแต่ต้น
  · มีเพียง `grep` บนคอมโพเนนต์เท่านั้นที่ตอบได้
- **Correct Pattern/Solution:**
  - 🔴 **ก่อนถอดทางเข้าออก ให้ `grep` ทุก route ที่จะกำพร้า — สำหรับ *แต่ละ* route ที่จะเสียทางเข้า ต้องมีที่อยู่ใหม่ครบ**
    ```bash
    grep -rn "name: 'profile-edit'\|name: 'profile-password'" src/ --include=*.vue
    ```
    ถ้าเหลือ **0 ไฟล์** = route นั้นกำพร้า (route definition เองไม่นับ — ต้องมี `.vue` ที่ `RouterLink`/`push` ไปหา)
  - 📌 **`hiddenFromMenu: true` = "มีทางเข้า แต่ไม่ใช่ทางเข้าในเมนู" ไม่ใช่ "ไม่ต้องมีทางเข้า"** — และเมื่อทางเข้าเดียวถูกถอด ต้องหา **1 ที่ใหม่ต่อ 1 route** (ไม่ใช่ยัดกลับเข้าเมนู ซึ่งจะสร้างปัญหาซ้ำรอยเดิม)
  - ⚠️ **ระวังกลิ่น "ทางเข้าซ้ำ" ที่หลอกตา** — dropdown นั้นซ้ำกับ More *จริง* แต่ `profile-edit`/`profile-password` ใน More เป็น `hiddenFromMenu` ⇒ **ผู้ใช้มองไม่เห็นมัน** ⇒ ที่ถอดไปมีแต่ UI ผู้ใช้เห็น ส่วนที่หายไปคือความสามารถที่ผู้ใช้เข้าถึงไม่ได้ = **ลดฟีเจอร์เงียบ ๆ** ซึ่งแผนนี้ห้ามไว้ชัด
  - ✅ ทางแก้ที่ใช้: `profile-edit` → ปุ่มหลักปุ่มเดียวของหน้าโปรไฟล์ · `profile-password` → การ์ด "บัญชี" หน้าใหม่ `/app/settings` (คนละหน้าที่กับ "ตัวตน")
- **Date Added:** 2026-09-30

### 🎯 `isVisible() === false` **ไม่ได้แปลว่า locator ไม่ match** — และปุ่ม "สร้างใหม่" อยู่ใต้ URL prefix เดียวกับลิสต์
- **Context/Problem:** R4.1 ตรวจหน้ารายการบอร์ดบน staging ด้วยสคริปต์ Playwright · รอบนั้นรายงาน **2 ข้อไม่ผ่าน** และ **ทั้งสองข้อดูเหมือนบั๊กของผลิตภัณฑ์** (การ์ดไม่บอกเวลา relative · การ์ดไม่แสดงชื่อผู้ตั้ง) ⇒ ถ้าเชื่อรายงานตรง ๆ จะเปิดไปแก้ `PiriBoards.vue` ซึ่ง **โค้ดถูกอยู่แล้ว**
- **Root Cause:** ทั้งสองข้อเป็น **false negative ของสคริปต์เอง** คนละสาเหตุ:
  · **ข้อ 1 — prefix ชนกัน:** selector คือ `main a[href^="/app/boards/"]` เพื่อจับการ์ดบอร์ด (`/app/boards/{id}`) แต่ปุ่มเดสก์ท็อป "เสนอไอเดีย" คือ `<a href="/app/boards/new">` ซึ่ง **อยู่ใต้ prefix เดียวกัน** ⇒ `.first()` หยิบ **ปุ่ม** ขึ้นมาแทนการ์ด
  · 🔴 **และนี่คือส่วนที่หลอกที่สุด:** ปุ่มนั้นเป็น `hidden lg:inline-flex` ⇒ ที่ 360dp `isVisible()` คืน **`false`** และสคริปต์เดียวกันก็ assert ผ่านว่า *"ปุ่มเดสก์ท็อปถูกซ่อน ✅"* — **แต่ query locator ยัง match มันอยู่ และ `innerText()` ยังคืนข้อความของมัน** ⇒ **การยืนยันว่า "ซ่อนแล้ว" กับการดึงข้อความจาก element ที่ซ่อน เกิดในรันเดียวกันได้โดยไม่ขัดกันเลย**
  · **ข้อ 2 — regex ไม่ครอบข้อมูลจริง:** เช็คชื่อผู้ตั้งด้วย `/ไม่ระบุชื่อ|สภานักเรียน|ผู้ใช้/` แต่ข้อมูลจริงคือ **`นาย พัฒนพล สุธรรม`** ⇒ ไม่ match (การ์ดแสดงชื่อถูกต้องแล้ว)
- **Correct Pattern/Solution:**
  - 🔴 **query locator (`locator()` · `getByText()` · `count()`) match จาก DOM ไม่สนใจว่า element มองเห็นไหม** — มีแค่ `isVisible()` / `click()` / `fill()` ที่สนใจ ⇒ **`innerText()` บน `display:none` ยังคืนข้อความ** · ถ้าต้องการนับ/อ่าน "สิ่งที่ผู้ใช้เห็น" ให้กรอง `:visible` หรือ **gate ด้วย `isVisible()` ก่อนเสมอ**
  - 🔴 **เมื่อ "รายการ" กับ "ปุ่มสร้างใหม่" อยู่ใต้ path prefix เดียวกัน ต้องตัดปุ่มออกเสมอ:**
    ```js
    // ❌ จับทั้งการ์ดและการ์ดปุ่มสร้าง
    page.locator('main a[href^="/app/boards/"]')
    // ✅ ตัด action ออก
    page.locator('main a[href^="/app/boards/"]:not([href$="/new"])')
    ```
    📌 ที่ปลอดภัยกว่าคือ **อย่าใช้ URL prefix เป็นตัวระบุชนิดของ element** — ใช้ `data-testid` หรือ attribute โครงสร้าง (`article`, `[data-board-card]`) ซึ่งไม่ปนกับ route ของปุ่ม
  - 🔴 **false negative ของสคริปต์ตรวจ มีต้นทุนเท่ากับบั๊กจริง — มันส่งเราไปผิดไฟล์** ⇒ **ก่อนสรุปว่า "ผลิตภัณฑ์พัง" ให้อ่าน selector/regex ของตัวเองซ้ำก่อน** โดยเฉพาะเมื่อ **ข้อที่ผ่านกับข้อที่ไม่ผ่านมาจากบริเวณเดียวกันของหน้า** (นี่คือสัญญาณเตือนที่แรงที่สุด: หน้าจอเดียวจะ "ซ่อนปุ่มสำเร็จ" แต่ "การ์ดพัง" พร้อมกันได้ยาก)
  - ⚠️ **regex ที่ตรวจข้อความไทยต้องมีค่าจริงจากข้อมูล หรือไม่ก็เขียนเป็น "ไม่ว่าง" แทน** — `expect(text.trim().length).toBeGreaterThan(0)` เชื่อถือได้กว่า `/ชื่อ|นาม/` ที่เดาเอา
- **Date Added:** 2026-10-01

### 🎨 สถานะ "โฟกัส" กับ "ผิดพลาด" ใช้แดงคนละเฉด — แยกด้วยตาไม่ออก
- **Context/Problem:** R4.1 เพิ่ม inline validation ให้ฟอร์มเสนอไอเดีย (ขอบ `border-danger` เมื่อผิด) · ฟอร์มนั้นใช้คลาส `.field` ซึ่ง **โฟกัสแล้วขอบเป็น `brand` (แดง) อยู่แล้วตั้งแต่ R0** ⇒ วัด computed style จริงบน staging ได้:

  | สถานะ | ขอบ |
  |---|---|
  | ปกติ | `#E7E7EA` (`line`) |
  | **โฟกัส** | `#B91C1C` (`brand`) + เงา ring |
  | **ผิดพลาด** | `#DC2626` (`danger`) ไม่มี ring |

  สองแถวล่างคือแดงที่ห่างกันไม่กี่องศา ⇒ **ผู้ใช้แยกไม่ออกด้วยสี ว่าช่องที่กำลังพิมพ์อยู่ "ผิด" หรือแค่ "ถูกโฟกัส"**
- **Root Cause:** กฎข้อ 4 ของแผน (*"สีมีความหมายเดียว — แดง = แบรนด์/ปุ่มหลัก"*) ทำให้ **โฟกัสต้องเป็นแดง** เพราะแดงคือสีแบรนด์ · แล้ว `danger` ก็เป็นแดงที่สอง ⇒ บน element เดียวกัน สองสถานะที่ **ความหมายตรงข้ามกัน** ถูกแสดงด้วยสีตระกูลเดียวกัน
- **Correct Pattern/Solution:**
  - ✅ **สิ่งที่ยังทำให้ผ่านเกณฑ์:** WCAG 1.4.1 (Use of Color) **ไม่ถูกทำผิด** เพราะ error มี **ข้อความกำกับ** (`role="alert"`) ไม่ได้สื่อด้วยสีอย่างเดียว ⇒ **ข้อความคือสัญญาณหลัก ขอบเป็นแค่ตัวช่วย** — ห้ามลบข้อความออกแล้วเหลือแต่ขอบแดง
  - 🔴 **อย่าแก้ด้วยการ "ทำให้แดงเข้มขึ้น/อ่อนลง"** — นั่นคือการเพิ่มเฉดแดงที่สามเข้าไปในระบบ ซึ่งเป็นโรคเดิมที่ audit ฟ้อง (634 จุดฮาร์ดโค้ด / แดง 6 ความหมาย) ⇒ จะยิ่งทำให้ปัญหาที่กำลังแก้อยู่แย่ลง
  - 📌 **ทางที่ถูกคือแยกด้วย "รูปร่าง" ไม่ใช่ "เฉดสี"** — ไอคอนหน้าข้อความ · แถบซ้าย · หรือ **เลิกใช้ขอบแดงกับ error ไปเลย** (เหลือข้อความ + ไอคอน) ซึ่งได้ผลเท่ากันและลดจำนวนความหมายของแดงลงหนึ่ง
  - ⏭️ **ยกไปทำใน R5** (รอบ a11y/consistency) ไม่ใช่แก้ `.field` กลางรอบ 4 — เพราะ `.field` ใช้ร่วมทุกฟอร์มในแอป ⇒ แก้ที่นั่น = เปลี่ยนหน้าจอทุกหน้าในคอมมิตที่ไม่ได้ตรวจหน้าเหล่านั้น
  - ⚠️ **บันทึกไว้เพราะ "สีใกล้กัน" เป็นข้อบกพร่องที่มองไม่เห็นตอน review โค้ด และไม่มีเทสต์ไหนจับได้** — ต้องวัด `getComputedStyle().borderColor` เท่านั้นถึงจะเห็น
- **Date Added:** 2026-10-01

### 🗂️ แผนสั่งให้ทำ "ตัวกรอง/segment" ที่ **ไม่มี endpoint รองรับ** — ทางเดียวที่ทำได้คือโกหกผู้ใช้
- **Context/Problem:** แผน R4.2 เขียนว่า `EventList.vue` + `EventManagement.vue` ต้องรวมเป็นหน้าเดียวโดยมี **3 segment: ทั้งหมด / ของฉัน / จัดการ** · สองตัวแรกทำได้ แต่ **"ของฉัน" (กิจกรรมที่ฉันสมัคร) ทำไม่ได้เลย** — และถ้าฝืนทำ ทางเดียวที่เหลืออยู่คือ**กรองฝั่ง client**
- **Root Cause:** ตรวจ 3 แหล่งอิสระแล้วตรงกันหมดว่าไม่มีข้อมูลรองรับ:
  · `backend/services/event_service.py` — `_PUBLIC_SCOPES` มีแค่ `upcoming` / `past` / `all` และ docstring เขียนไว้ชัดว่า **"⚠️ ไม่กรองด้วยสิทธิ์ — นักเรียนทุกคนเห็นกิจกรรมเหมือนกันหมด"** ⇒ ไม่มี scope ที่ผูกกับ `user_id`
  · `frontend/src/types/event.ts` — `EVENT_SCOPES` ตรงกับ backend เป๊ะ (ไม่มีค่าที่ 4)
  · ทางออกอื่นก็ไม่มี: `my-activity` (`/app/me`) มี `ACTIVITY_TABS` แค่ `issue_created` / `vote_cast` / `board_comment_posted` / `issue_comment_posted` — **ไม่มีชนิด "สมัครกิจกรรม"** ⇒ ใช้แทนกันไม่ได้
- **Correct Pattern/Solution:**
  - 🔴 **ตัวกรองที่ทำได้แค่ฝั่ง client บนข้อมูลที่แบ่งหน้า จะ "โกหก" เสมอ** — สมัครกิจกรรมไว้ที่อยู่ในหน้า 2 แต่กรองจาก `items` ของหน้า 1 ⇒ ขึ้น **"ยังไม่สมัครกิจกรรมไหนเลย"** ทั้งที่ความจริงคือสมัครอยู่ · **นี่แย่กว่าไม่มีตัวกรองนั้นเลย** เพราะผู้ใช้จะเชื่อมัน
  - ✅ **สิ่งที่ตอบความต้องการนี้ไปแล้วโดยไม่ต้องมี segment: `my_registration_status` ที่ติดมากับการ์ดทุกใบ** (`ได้ที่นั่ง` / `คิวสำรอง`) ⇒ ผู้ใช้เห็นสถานะของตัวเองได้ทันทีโดยไม่ต้องกรอง — **ตรวจก่อนว่าคำถามของผู้ใช้ถูกตอบไปแล้วหรือยัง ก่อนสร้างกลไกใหม่มาตอบมัน**
  - 🔴 **การถอดรายการที่แผนสั่งออก ต้องเขียนเหตุผลไว้ "ณ ที่ที่คนถัดไปจะไปเพิ่มมันกลับ"** — ไม่ใช่แค่ในคอมมิต (ซึ่งหาไม่เจอ) ⇒ เคสนี้เขียนใน `constants/nav.ts` หัว `EVENT_SEGMENTS`, ในเทสต์ `routeMeta.spec.ts` และในคอมเมนต์บนการ์ด ⇒ ใครจะเพิ่ม segment ที่ 3 กลับจะเจอคำอธิบายก่อน
  - 📌 **การทำ "ของฉัน" ให้ถูกต้อง = งาน backend** (เพิ่ม scope `mine` ที่ `JOIN event_registrations` ด้วย `user_id`) ไม่ใช่การเดาใน UI · ⚠️ ระวังกับดักที่บันทึกไว้แล้วในไฟล์เดียวกัน: helper ที่นับ+ดึงแถวมี **เลข placeholder ของแต่ละคิวรีเป็นอิสระต่อกัน** และ `count_sql` ไม่มี placeholder เลยขณะที่ `rows_sql` สงวน `$1` ไว้
- **Date Added:** 2026-10-01

### 🧪 helper ของเทสต์ที่ **ฮาร์ดโค้ดรายชื่อกลุ่ม** — เพิ่มกลุ่มใหม่แล้ว "เขียวโดยไม่มีใครตรวจ"
- **Context/Problem:** R4.2 ย้าย "จัดการกิจกรรม" จาก **แถวเมนู** (`NAV_GROUPS`) ไปเป็น **segment ของแท็บกิจกรรม** ⇒ `navRegistry.spec.ts` แดงทันทีที่บรรทัด
  `MainLayout:190 จัดการกิจกรรม → event-management (menu) — ควรเห็น` **ซึ่งถูกต้อง** — fixture `MENU_TODAY` คือ *สัญญา* ว่า "ปลายทางละหนึ่งทางเข้า" การเปลี่ยนชนิดของทางเข้าจึงต้องแก้สัญญา ไม่ใช่แก้ให้เทสต์ผ่าน
- **Root Cause:** ตอนแก้ให้ผ่าน พบว่าตัวช่วย `reachableFrom()` ไล่กลุ่มแบบ **เขียนรายชื่อไว้เอง**:
  ```ts
  for (const s of [...nav.segmentsOf('issues'), ...nav.segmentsOf('members')]) names.add(s.to.name)
  ```
  🔴 `SegmentGroupId` เป็น union ที่ **โตได้** (`'issues' | 'members' | 'events'`) แต่ตัวช่วยนี้ **ไม่โตตาม** ⇒ **กลุ่ม `'events'` ที่เพิ่งเพิ่มจะไม่ถูกตรวจเลย** และเทสต์จะ **เขียวทั้งที่ยังไม่ได้ครอบอะไร** — ซึ่งอันตรายกว่าแดง เพราะแดงคือ "ยังไม่เสร็จ" ส่วนเขียวคือ "เชื่อว่าเสร็จแล้ว"
- **Correct Pattern/Solution:**
  - 🔴 **ตัวช่วยที่ต้องไล่ "ทุกตัวในเซต" ห้ามฮาร์ดโค้ดเซตนั้น — ต้องไล่จากแหล่งเดียวกับที่ production ใช้** (ในเคสนี้คือ `nav.segmentsOf(g)` ต่อกลุ่ม) ⇒ ถ้าลิสต์กลุ่มงอก ตัวช่วยงอกตามเอง
  - ✅ **สัญญาณว่ากำลังเจอกับดักนี้: ตัวช่วยมี literal array ที่ "ต้องจำให้ตรง" กับ union/const ที่ประกาศที่อื่น** — สองที่นี้จะเพี้ยนจากกันเงียบ ๆ
  - 📌 **การที่เทสต์ *แดง* ตอนย้ายกลไก คือหลักฐานว่าเทสต์ทำงาน** — `navRegistry.spec.ts` ตัวนี้จับได้ก่อนที่ฟีเจอร์จะถูกถอดโดยไม่มีใครรู้ (ดูบทเรียน "ถอดทางเข้าที่ซ้ำออกแล้ว route ที่ `hiddenFromMenu` กำพร้า — เทสต์ไม่จับ" ซึ่งเป็น **ความล้มเหลวอีกด้านของเทสต์ตัวเดียวกัน**: ตัวนั้นพิสูจน์ว่าเทสต์นี้ *ไม่ครอบ* UI จริง ส่วนตัวนี้พิสูจน์ว่า *ครอบ* เมื่อชนิดของทางเข้าเปลี่ยน)
  - ⚠️ **เมื่อแก้ fixture ให้ตรงความจริงใหม่ ให้ใส่คอมเมนต์ว่าทำไม** (เช่น `reach: 'segment'` พร้อมเหตุผล) ไม่งั้นคนถัดไปจะคิดว่ามันเป็น typo แล้วแก้กลับ
- **Date Added:** 2026-10-01

### 📉 ตรวจหน้ารายการบน staging ที่ข้อมูลเกือบว่าง — "การ์ด 0 ใบ" **ยังไม่ใช่บั๊ก** จนกว่าจะเช็คตัวกรองเริ่มต้น
- **Context/Problem:** R4.2 ตรวจหน้าอีเวนต์บน staging ด้วยสคริปต์ Playwright · รายงาน **3 ข้อไม่ผ่าน** ซึ่งอ่านเผิน ๆ คือ *"หน้ารายการกิจกรรมไม่แสดงการ์ดเลยทั้งของแอดมินและของนักเรียน"* ⇒ **เกือบเปิด `EventList.vue` ไปแก้หน้าที่ทำงานถูกอยู่แล้ว**
- **Root Cause:** ไม่ใช่บั๊ก แต่เป็น **ตัวกรองเริ่มต้นชนกับข้อมูลจริง**:
  · หน้าอีเวนต์เริ่มที่ชิป **"กำลังจะมาถึง"** = `event_date >= NOW()`
  · staging มีกิจกรรมเดียว `2026-10-01 01:30 UTC` (08:30 น. Bangkok) ส่วน `NOW()` = `05:44 UTC` (12:44 น.) ⇒ **ผ่านไปแล้ว 4 ชั่วโมง** ⇒ ลิสต์ว่าง **ถูกต้องตามสเปก**
  · 🔴 **ตัวช่วยชี้ขาดคือ query ตรงไปที่ DB** (`docker exec <db> psql …`) ไม่ใช่การอ่านโค้ด — อ่านโค้ดเท่าไรก็ไม่รู้ว่า "ข้อมูลดิบอยู่ฝั่งไหนของตัวกรอง"
  · **และมี false negative ที่สองซ้อนอยู่ในรันเดียวกัน:** การนับด้วย `a[href^="/app/events/"]` ได้ 1 ขณะที่ตัวกรองที่ตั้งใจใช้ได้ 0 ⇒ ตัวที่โผล่มานั้นคือ **ปุ่ม "สร้างกิจกรรม" เดสก์ท็อป** (`/app/events/new`) ซึ่ง `hidden lg:inline-flex` ⇒ **query locator จับ element ที่ซ่อนอยู่** (บทเรียน R4.1 เรื่องเดิม เกิดซ้ำเพราะ selector ยังใช้ URL prefix เป็นตัวระบุชนิดอีก)
- **Correct Pattern/Solution:**
  - 🔴 **ก่อนประกาศว่าหน้ารายการพัง ให้ตอบ 2 คำถามนี้ก่อน: (1) แถวใน DB มีจริงกี่แถวและค่า *ตัวกรองเริ่มต้น* ของมันเป็นอะไร (2) สคริปต์นับ element ชนิดที่ตั้งใจจริงไหม**
  - 🔴 **การตรวจหน้ารายการที่ข้อมูลน้อย ต้องครอบ *ทั้ง* สถานะว่างและสถานะมีข้อมูล — และต้องเลือก scope ที่ข้อมูลอยู่จริงก่อนนับ** ไม่งั้น "ผ่าน" กับ "ไม่ผ่าน" ไม่ได้วัดอะไรเลย:
    ```js
    await pickScope('ผ่านไปแล้ว')   // ← เลือก scope ที่มีข้อมูลก่อน แล้วค่อยนับ
    ```
  - ✅ **ตัวเลขที่ขัดกันเองในรันเดียว = สัญญาณ false negative ที่แรงที่สุด** (นับได้ 1 แต่กรองแล้วได้ 0 ⇒ ต้องอธิบายให้ได้ว่าตัวที่หายไปคืออะไร · อธิบายไม่ได้ = selector ผิด)
  - 📌 **อย่าใช้ URL prefix เป็นตัวระบุชนิดของ element** — หน้าลิสต์ (`/app/events/{id}`) กับปุ่มสร้าง (`/app/events/new`) อยู่ใต้ prefix เดียวกันเสมอในแอปนี้ ⇒ ตัดออกด้วย `:not([href$="/new"]):not([href$="/manage"])` หรือ بهتر: `data-testid` ที่ไม่ปนกับ route
  - ⚠️ **สคริปต์ตรวจที่เขียนไฟล์ภาพด้วยชื่อเดิมสองที่ → ที่หลังทับที่แรกเงียบ ๆ** ⇒ ตั้งชื่อไฟล์ภาพให้ต่างกัน ไม่งั้นจะดูภาพผิดจังหวะแล้วสรุปผิด
- **Date Added:** 2026-10-01

### 🈲 อักขระต่างภาษาหลุดเข้าไปในคอมเมนต์ไทย — ตาเปล่าอ่านผ่าน แต่ grep ไม่ผ่าน
- **Context/Problem:** R4.2 เขียนคอมเมนต์ไทยใน `constants/nav.ts` แล้วมีอักษรจีนปนเข้าไปกลางประโยค · **รอบแรกแก้แล้วใส่ตัวอื่นเข้าไปแทน (แย่กว่าเดิม)** กว่าจะสะอาดก็ครั้งที่สาม — และเป็นการ **เกิดซ้ำ** ของความผิดชนิดเดียวกัน (เคยเกิดกับข้อความคอมมิตมาก่อน)
- **Root Cause:** ข้อความไทยกับอักษร CJK/Hangul **มีเส้นสายใกล้กันมากในฟอนต์ monospace** และประโยคยังอ่านรู้เรื่องทั้งที่มีตัวแปลกปน ⇒ **การอ่านทวนด้วยตาเป็นด่านที่ไม่ทำงาน** โดยเฉพาะเมื่อตากำลังอ่าน "ความหมาย" ไม่ได้อ่าน "ตัวอักษร"
  · อีกปัจจัย: **การแก้แบบ "แก้จุดที่เห็น" โดยไม่สแกนทั้งไฟล์** ⇒ รอบสองจึงไปวางตัวใหม่ทับ
- **Correct Pattern/Solution:**
  - 🔴 **อย่าใช้ตาเป็นด่านสุดท้ายสำหรับเรื่องนี้ — ใช้ `grep` ก่อนคอมมิต:**
    ```bash
    # จับ "ตัวอักษร" ของภาษาที่สาม — CJK ideograph · Kana · Hangul
    grep -rnP '[\x{3040}-\x{30FF}\x{3400}-\x{4DBF}\x{4E00}-\x{9FFF}\x{AC00}-\x{D7AF}]' src/ docs/
    ```
    ⚠️ **จงใจไม่ใส่ช่วงวรรคตอน CJK (`\x{3000}-\x{303F}`) และ fullwidth forms (`\x{FF00}-\x{FFEF}`) ในคำสั่งนี้** — เพราะ `「」` ถูกใช้เป็นอัญประกาศในคอมเมนต์ของเรพนี้ **อย่างตั้งใจและสม่ำเสมอ** ⇒ ถ้าใส่เข้าไปด้วย คำสั่งจะกลายเป็น **เครื่องผลิต false positive** แล้วคนจะเลิกใช้มัน (บทเรียนเดียวกับ R4.1: false positive ของเครื่องมือตรวจมีต้นทุนเท่ากับบั๊กจริง)
    📌 **`「」` (U+300C/U+300D) เป็น *ตัวเลือกสไตล์* ที่ยังไม่ตรงกับที่อื่นในเรพ (ที่ใช้ `"…"`)** — บันทึกไว้ให้ **R5 (รอบความสม่ำเสมอ) ตัดสิน** ไม่ใช่เรื่องของด่านนี้
  - 🔴 **เมื่อเจอ ให้แก้โดย *เขียนประโยคใหม่ทั้งประโยค* ไม่ใช่ลบตัวอักษรนั้นออก** — เคสนี้ลบแล้วได้ตัวใหม่เพราะสมองยังจำ "ช่องว่าง" เดิมอยู่ ⇒ เขียนใหม่ทั้งช่วงแล้ว grep ซ้ำ
  - ✅ **ของจริงที่จับได้จากคำสั่งนี้: `NewIssue.vue` (เขียนไว้ตั้งแต่ R3.1) มีอักษรจีน `U+88DC` ปนอยู่ในประโยคไทย** — ประโยคเดิมอ่านว่า "(stepper 3 ขั้นที่แสดงครบเสมอ) ไม่ใช่ `U+88DC` เลขให้ต่อกัน" ซึ่งความหมายที่ต้องการคือ **"เติม"** ⇒ หลุดรอด `type-check` / `lint` / `test:unit` / `build` มาหลายรอบ และไม่มีใครเห็นจนกว่าจะ grep · **ของที่ปนมานานขนาดนี้คือหลักฐานว่าตาไม่ใช่ด่าน**
    📌 **เขียนตัวอย่างในเอกสารด้วยรหัส `U+…` ไม่ใช่ตัวอักษรจริง** — ไม่งั้น **คำสั่ง grep ข้างบนจะรายงานเอกสารของตัวเองทุกครั้งที่รัน** แล้วกลายเป็น noise ที่คนจะเริ่มมองข้าม
  - 📌 **สแกนทั้งไฟล์ที่แก้ ไม่ใช่แค่บรรทัดที่เพิ่งเขียน** — ตัวที่หลุดอาจอยู่บรรทัดอื่นที่เขียนไปแล้วในรอบเดียวกัน
  - ⚠️ **ความผิดชนิดนี้รอดทุกด่านอัตโนมัติ** (`type-check` / `lint` / `test:unit` / `build` ไม่มีตัวไหนอ่านความหมายของคอมเมนต์) ⇒ **ถ้าไม่ grep จะรอดไปถึง `main`** และไปโผล่ในเอกสารที่คนอื่นอ่าน
- **Date Added:** 2026-10-01

### 🔴 `ref()` ห่อออบเจกต์ด้วย Proxy ⇒ `result.value === obj` **เป็น false เสมอ** — ตัวจับเวลาที่เทียบตัวตนจึงไม่เคยทำงาน
- **Context/Problem:** R4.4 หน้าสแกนเช็คอินตั้งใจให้ "ผลสำเร็จ" ค้างบนจอ 8 วินาทีแล้วล้างตัวเอง โค้ดอ่านแล้วถูกทุกบรรทัดและ **ผ่าน `type-check` / `lint` / `test:unit` / `build` ครบทั้งสี่ด่าน** แต่บน staging ชื่อคนที่เพิ่งเช็คอิน **ค้างอยู่ตลอดไป**
  · โค้ดที่เป็นปัญหา:
    ```ts
    const result = ref<CheckInResult | null>(null)
    function showResult(next: CheckInResult) {
      clearTimeout(resultTimer)
      result.value = next
      if (next.kind !== 'ok') return
      resultTimer = window.setTimeout(() => {
        if (result.value === next) result.value = null   // ← ไม่มีทางเป็นจริง
      }, SUCCESS_HOLD_MS)
    }
    ```
- **Root Cause:** `ref(obj)` เก็บค่าเป็น **reactive proxy** (`toReactive` → `reactive()`) ไม่ใช่ตัวออบเจกต์ดิบ ⇒ getter `result.value` คืน Proxy ซึ่ง **`!== obj` ตัวที่ส่งเข้าไป** · พิสูจน์ด้วยคำสั่งเดียว:
  ```bash
  node --input-type=module -e "
  import { ref, toRaw } from 'vue'
  const r = ref(null); const o = { a: 1 }; r.value = o
  console.log(r.value === o, toRaw(r.value) === o)   // false true
  "
  ```
  · **ทำไมไม่มีด่านไหนจับได้:** ไม่มีเทสต์ใดในเรพนี้ render view ⇒ พฤติกรรม "ล้างตัวเองตามเวลา" ไม่มีใครทดสอบ · และ `tsc` ไม่เตือนเพราะการเทียบ `A === B` ที่ type ตรงกันเป็นเรื่องถูกต้องทางชนิด — **ผิดทางความหมาย ไม่ผิดทางชนิด**
- **Correct Pattern/Solution:**
  - ✅ **ใช้ "เลขรอบ" แทนการเทียบตัวตน** — รูปแบบเดียวกับ `cameraAttempt` ที่ใช้ตัดสินรอบของ `getUserMedia` ในไฟล์เดียวกัน:
    ```ts
    let resultSeq = 0
    function showResult(next: CheckInResult) {
      clearTimeout(resultTimer)
      const seq = ++resultSeq          // ทำให้ callback เก่าเป็นโมฆะทันที
      result.value = next
      if (next.kind !== 'ok') return
      resultTimer = window.setTimeout(() => {
        if (resultSeq === seq) result.value = null
      }, SUCCESS_HOLD_MS)
    }
    ```
  - 🔁 **ทางเลือกที่ใช้ได้แต่ผูกกับภายในของ Vue กว่า:** `toRaw(result.value) === next` — ถูกต้อง แต่ต้องรู้ว่ามี `toRaw` และต้องจำใส่ทุกจุด ⇒ **เลขรอบอ่านออกกว่าและไม่ต้องพึ่ง internals**
  - 🔍 **`grep -rn '\.value ===' src/` แล้วถามทีละจุดว่า "ฝั่งขวาเป็นออบเจกต์ที่เพิ่งใส่เข้า ref หรือเปล่า"** — เคสที่เทียบกับ **primitive** (`'live'`, `null`, ตัวเลข) ปลอดภัยทั้งหมด ⇒ **ความผิดนี้เกิดเฉพาะเมื่อเทียบกับออบเจกต์** (ในเรพนี้พบจุดเดียว)
  - 📌 **อาการที่ทำให้มันอันตรายกว่า "ปุ่มไม่ทำงาน":** แถบที่ค้างอยู่แสดง **ชื่อคนที่เช็คอินไปแล้ว** ⇒ สภาเห็นชื่อค้างแล้วเชื่อว่าคนที่ยืนอยู่ตรงหน้าเช็คอินแล้วทั้งที่ยังไม่ได้ยื่นบัตร — **ข้อมูลผิดที่ดูเหมือนข้อมูลถูก** ซึ่งแย่กว่าจอว่าง
  - ⚠️ **บทเรียนร่วมกับ R4.4:** 23 ข้อตรวจอัตโนมัติผ่านหมดทั้งที่บั๊กนี้ยังอยู่บนจอ (ข้อที่ครอบพฤติกรรมนี้ถูกเขียนไว้ **ผิดวิธี** — วัดความสูงกล้องในโหมดที่ไม่มีกล้อง) ⇒ **ข้อตรวจที่ผ่านคือข้อตรวจที่อาจไม่ได้ตรวจอะไรเลย** ดูหัวข้อถัดไป
- **Date Added:** 2026-10-01

### 🌐 หน้าเว็บกับ API อยู่ **คนละโดเมน** — ยิง `/api/...` แบบ relative ได้ **200 + `text/html`** ที่อ่านเหมือน "เซิร์ฟเวอร์พัง"
- **Context/Problem:** สคริปต์ตรวจบน staging ยิง `fetch('/api/events/1/my-registration')` จากในหน้าที่ล็อกอินแล้ว ได้ **`200` + `<!DOCTYPE html>`** ⇒ `r.ok` เป็น `true` แล้ว `r.json()` ระเบิดด้วย `SyntaxError: Unexpected token '<', "<!DOCTYPE "... is not valid JSON`
  · อาการนี้ **ชี้ผิดทางโดยสิ้นเชิง** — อ่านเหมือน backend ตอบ HTML / Cloudflare บล็อก / proxy ตั้งค่าผิด ⇒ เสียเวลาไล่ผิดที่
- **Root Cause:** **`VITE_API_BASE_URL` ถูกอบใส่บันเดิลตอน build** (ค่าจริงบน staging คือ `https://prsc-api-test.pirivoice.com` — คนละโฮสต์กับเว็บ) ไม่ได้ใช้ `/api` แบบ same-origin · โดเมนเว็บมี **SPA fallback** ⇒ ตอบ `index.html` สถานะ `200` ให้ **ทุก path ที่ไม่รู้จัก** ⇒ คำขอที่ "ยิงผิดโดเมน" ได้คำตอบที่ดูเหมือนสำเร็จ
  · **สาเหตุที่โทษ Cloudflare ตอนแรกก็มีมูล:** ยิงด้วย `fetch` ของ Node ตรง ๆ ได้ **405 + `text/html` (`server: cloudflare`)** จริง ⇒ แก้ถูกครึ่งเดียว (ย้ายไปยิงในเบราว์เซอร์) แล้วยังเจอ HTML อยู่ เพราะ **สาเหตุที่สองซ้อนอยู่ข้างหลัง**
- **Correct Pattern/Solution:**
  - 🔴 **ดักโดเมนจริงจากทราฟฟิกของแอปเอง อย่าฮาร์ดโค้ด** — ก่อนยิงคำขอแรก ให้ฟัง response แล้วจำ origin:
    ```js
    let origin = ''
    page.on('response', (r) => {
      const u = r.url()
      if (!origin && u.includes('/api/')) origin = new URL(u).origin
    })
    ```
    ⇒ ใช้ได้ทั้ง staging/production โดยไม่ต้องอ่าน `.env` ของเซิร์ฟเวอร์
  - 🔴 **ตรวจ `content-type` ก่อน `r.json()` เสมอ แล้วโยน error ที่บอกสถานะ + เนื้อหาจริง** — อย่าปล่อยให้ `SyntaxError` ของ JSON.parse เป็นข้อความเดียวที่เหลือ:
    ```js
    const ct = r.headers.get('content-type') || ''
    if (!ct.includes('json')) {
      throw new Error(`${p} → HTTP ${r.status} ${ct} · ${(await r.text()).slice(0,120)}`)
    }
    ```
  - 📌 **`200` ไม่ได้แปลว่า "ได้ของที่ต้องการ"** — เมื่อปลายทางเป็น SPA ที่มี fallback · **`r.ok` เชื่อไม่ได้ถ้าไม่ได้ตรวจชนิดของเนื้อหา**
  - ⚠️ **บทเรียนทั่วไป:** เมื่อเครื่องมือ probe รายงานสิ่งที่ "เป็นไปไม่ได้" ให้สงสัย **สมมติฐานของ probe เอง** ก่อนสรุปว่าเซิร์ฟเวอร์พัง (บทเรียนเดียวกับ "probe ของตัวเองก็โกหกได้" ข้างบน)
- **Date Added:** 2026-10-01

### 🔢 "การ์ดที่แตะแล้วกรองได้" คือ **สัญญาเรื่องตัวเลข** ไม่ใช่รายละเอียด UI — ตัวเลขบนการ์ดต้องเท่ากับยอดในลิสต์ปลายทาง ไม่งั้นอย่าทำให้มันกดได้
- **Context/Problem:** งาน R4.5 สั่งว่า "การ์ดสถิติแตะแล้วกรองได้" · endpoint มีครบ (`by_status`, `main_categories`) และฝั่ง UI ก็ผูก `RouterLink` ไป `/app/issues/received?status=…` ได้ในไม่กี่บรรทัด ⇒ **ถ้าทำตามแผนตรง ๆ จะส่งของที่โกหกผู้ใช้ออกไป**
  · วัดจริงบน staging ด้วยบัญชีแอดมิน: การ์ด "เรื่องทั้งหมด" = **34** แต่เปิด `/app/issues/received?status=all` แล้วได้ **5** · การ์ด "รอรับเรื่อง" = **14** แต่ลิสต์ได้ **3-5** ⇒ **การ์ดบอก 34 กดแล้วเจอ 5** — ตัวเลขที่ผู้ใช้เห็นก่อนกดคือคำสัญญา ถ้าปลายทางไม่ตรง คำสัญญาก็เป็นเท็จ
- **Root Cause:** **สองหน้าใช้ "ขอบเขต" คนละนิยาม และไม่มีใครเขียนมันไว้ที่ไหน**
  - `dashboard_service._scope_clause` ใช้ `get_access_scope` ⇒ ขอบเขต = *ห้อง-ชั้นปี* หรือ *ทั้งโรงเรียน* (ขึ้นกับบทบาท)
  - `issue_service.list_issues(received=True)` ⇒ ขอบเขต = **ระดับพีระมิดตรงตัว** (`level == "student"` → `where 1 = 0`) **บวก** เงื่อนไข "เกี่ยวข้องกับฉัน"
  ⇒ ทั้งสองถูกต้องตามหน้าที่ของตัวเอง · **ผิดเฉพาะตอนที่เอาการ์ดของตัวหนึ่งไปชี้ลิสต์ของอีกตัวหนึ่ง**
  · ชั้นที่สองของความผิด: หน้าลิสต์มี **ตัวกรอง "หน้าที่ของฉัน" ที่เปิดเองโดยปริยาย** เมื่อผู้ใช้มี `responsibilities` ⇒ ต่อให้ scope ตรงแล้ว ยอดก็ยังห่างได้อีก (วัดได้ **14 → 3**)
- **Correct Pattern/Solution:**
  - 🔴 **ก่อนผูก `RouterLink` ให้เขียนตัวเลขสองฝั่งลงกระดาษเทียบกันก่อน** — ยิง API จริงทั้งสองเส้นด้วยผู้ใช้จริง **แล้วเทียบทีละสถานะ** ไม่ใช่เทียบแค่ยอดรวม
    ```
    dashboard: total 34 · pending 14 · in_progress 4 · escalated 1 · resolved 13 · cancelled 0 · rejected 2
    list+levels: 34 · 14 · 4 · 1 · 13 · 0 · 2   ← ตรงกันทุกช่อง ⇒ ค่อยผูก
    ```
  - 🔴 **ซ่อมที่ปลายทางด้วยพารามิเตอร์ที่ "ขยายขอบเขต" ไม่ใช่ซ่อมที่การ์ดด้วยการลดตัวเลข** — ในที่นี้คือ `?levels=room,level,council` (ค่าที่ `list_issues` รับอยู่แล้ว) ⇒ **ไม่ต้องแก้ backend เลย** และการ์ดยังคงพูดความจริงทั้งสองหน้า
    · ส่ง `levels` **เฉพาะเมื่อ `scope === 'all'`** (`LEVEL_ORDER.join(',')`) — ผู้ใช้ที่ scope เป็นระดับห้องส่งไปจะยิ่งได้ยอดผิด
  - 🔴 **สตริงว่างใส่ใน query string ไม่ได้** — หน้าลิสต์ใช้ `''` แทน "ทุกสถานะ" (`STATUS_FILTERS`) ⇒ ลิงก์ `?status=` อ่านกลับมาแล้วแยกไม่ออกว่า "ตั้งใจขอทุกสถานะ" หรือ "ไม่มีคีย์" (ค่าเริ่มต้น = `not_resolved`) ⇒ **การ์ด "เรื่องทั้งหมด" จะกลายเป็น "ยังไม่เสร็จ" เงียบ ๆ** · แก้ด้วยโทเคน `STATUS_URL_ALL = 'all'` ที่ประกาศเป็น **สัญญาระหว่างสองไฟล์** (`constants/status.ts`)
  - 🔴 **ปิดตัวกรองที่ "เปิดเองโดยปริยาย" เมื่อมาทางลิงก์** — `respFilterOn` ต้องเริ่มเป็น `false` ถ้ามี `status`/`levels` ติดมา ไม่งั้น **การ์ด 14 → ลิสต์ 3**
  - 🔴 **การ์ดที่ไม่มีปลายทางต้องไม่กดได้ — และต้องบอกว่าทำไม** — "งานเกินเวลา" ไม่มีตัวกรอง `overdue` ใน backend เลย ⇒ ปล่อยเป็น `<div>` ธรรมดา **พร้อมคอมเมนต์ในโค้ดกันคนมา "เติมลิงก์ให้ครบ" ทีหลัง**
  - 📌 **เกณฑ์ปิดงาน:** ทุกการ์ดที่กดได้ ต้องพิสูจน์ **1:1 ต่อทุกสถานะ** บน staging ไม่ใช่แค่การ์ดเดียว
- **Date Added:** 2026-10-01

### 🚪 สาขาที่ **ไม่มีบัญชีทดสอบเข้าไปถึง** = สาขาที่ยังไม่ถูกตรวจ — "เทสต์ผ่าน" ที่นั่นแปลว่า "เทสต์ไม่ได้รันโค้ดนั้น"
- **Context/Problem:** หลังผูกการ์ดกับลิสต์แล้ว เทสต์ 19/19 ผ่านบน `e2eadm` ⇒ เกือบปิดรอบ
  · แต่โค้ดที่เพิ่งเขียนมีสาขาหนึ่งกันไว้เพื่อผู้ใช้ที่มี `responsibilities` — **การ์ด 14 กดแล้วต้องได้ 14 ไม่ใช่ 3** · และ **ไม่มีบัญชี staging ใดเลยที่มี `responsibilities`** เพราะฟิลด์นี้ถูกบังคับว่างสำหรับบทบาทอื่น (`student_service.RESPONSIBLE_ROLES` มีแค่ `council_member` / `level_vice_president` ส่วน `e2eadm` เป็น `council_president`) ⇒ สาขานั้น **ไม่เคยถูกประเมินแม้แต่ครั้งเดียว** ตลอดที่เทสต์เขียว
- **Root Cause:** "ผ่าน" ถูกอ่านว่า "โค้ดถูก" ทั้งที่ความจริงคือ **ข้อตรวจไม่เคยไปถึงโค้ดนั้น** — อาการเดียวกับ R4.3/R4.4 (23 ข้อผ่านขณะบั๊กยังอยู่บนจอ) แต่รากต่างกัน: ครั้งนั้น **ข้อตรวจเขียนผิดวิธี** ครั้งนี้ **ข้อมูลทดสอบไปไม่ถึง**
  · บทเรียนร่วม: **ความครอบคลุมของเทสต์ถูกจำกัดด้วย "สถานะข้อมูล" เท่ากับที่ถูกจำกัดด้วย "คุณภาพของข้อตรวจ"**
- **Correct Pattern/Solution:**
  - 🔴 **ก่อนเชื่อผลเทสต์ ให้ถามว่า "มีข้อมูลแบบไหนที่จะทำให้สาขานี้ทำงาน" แล้วเช็คว่ามีอยู่จริงไหม** — ถ้าไม่มี ⇒ **ข้อตรวจที่เหลืออยู่ไม่มีความหมายกับสาขานั้น**
    ```sql
    -- หาให้เจอก่อนว่าใครเข้าเงื่อนไข อย่าเดา
    SELECT class_role, jsonb_array_length(responsibilities) FROM students WHERE …;
    ```
  - 🔴 **เปิดสาขาด้วยการแก้ข้อมูลชั่วคราวได้ แต่ต้อง (1) บันทึกค่าเดิมก่อน (2) กู้คืนทันทีในสคริปต์เดียวกัน (3) ยืนยันด้วยการวัดซ้ำหลังกู้** — รอบนี้ใช้วิธีนี้พิสูจน์ได้จริง (`council_president`+`[]` → `council_member`+`["academic"]`): เข้าตรง = **3** · กดการ์ด = **14** ⇒ ยืนยันว่าการ์ดที่พูด 14 ไม่ได้โกหก · แล้วกู้คืน + วัดการ์ดกลับมาเป็น `34,14,4,1,13,3`
  - ⚠️ **การแก้ข้อมูลบน staging ที่มีคนอื่นใช้ = ต้องกู้คืนก่อนจบรอบเสมอ** และ **ห้ามแตะ production** — ถ้าสคริปต์ล้มกลางทาง ต้องมีทางกลับ (รอบนี้เขียน `UPDATE` กลับเป็นบรรทัดสุดท้ายของสคริปต์เดียวกัน)
  - 📌 **ค่าเริ่มต้นของหน้าใด ๆ ที่ "มาจากที่อื่น" ต้องถูกวัดจากเส้นทางที่มาจากที่อื่นจริง ๆ** — วัดด้วยการเปิด URL ตรง ๆ ไม่ได้ (นั่นคือสาเหตุที่ R4.4/R4.5 พลาดซ้ำ)
- **Date Added:** 2026-10-01

### 📋 แผนที่เขียนไว้ก่อนอ่านโค้ด จะมีข้อที่ **ไม่ตรงกับความจริง** — เจอแล้วต้องพูดออกมา ไม่ใช่เงียบแล้วทำข้ออื่นต่อ
- **Context/Problem:** R4.5 ในแผนมี 4 ข้อ · ข้อ 2 เขียนว่า *"แท็บ 4 ตัวที่ตัดคำ 2 บรรทัด → `AppTabs` (≤ 4 · ไม่มีไอคอน · ห้ามตัดบรรทัด)"* · ความจริงคือ **`Dashboard.vue` ไม่มีแท็บเลยแม้แต่ตัวเดียว** (ไม่มี `<nav>`, ไม่มีปุ่มสลับมุมมอง) ⇒ เป็นข้อที่ **ทำไม่ได้เพราะไม่มีของให้ทำ**
- **Root Cause:** แผนนี้เขียนจาก **ผลตรวจ UX รวม 17 หน้า** (ไฟล์ audit) แล้วแตกเป็นรอบ — ข้อที่บรรยายอาการได้ถูกต้อง **แต่ผูกผิดไฟล์** ("แท็บที่ตัดคำ 2 บรรทัด" มีจริงในหน้าอื่น เช่นรายงาน/กิจกรรม) ⇒ จุดผิดพลาดจะเกิดตอน*อ่านแผน* ไม่ใช่ตอน*เขียนแผน*
  · อันตรายจริงไม่ใช่การทำข้อนั้นไม่สำเร็จ แต่คือ **การ "ทำข้อนั้นให้สำเร็จ" ด้วยการประดิษฐ์แท็บขึ้นมาใหม่** เพื่อให้ติ๊กถูก — สร้าง UI ที่ไม่มีใครขอ
- **Correct Pattern/Solution:**
  - 🔴 **เปิดไฟล์ปลายทางก่อนเริ่มทุกข้อ** และถ้าไม่เจอสิ่งที่แผนอ้าง ⇒ **รายงานว่า "ข้อนี้ไม่ตรงกับความจริง" พร้อมหลักฐาน** (`grep -c '<nav' src/views/Dashboard.vue` = 0) — **ห้ามเดาว่าแผนหมายถึงอะไรแล้วทำอันนั้น**
  - 🔴 **แยก "ทำแล้ว" ออกจาก "ไม่มีของให้ทำ" ให้ชัดในรายงานปิดรอบ** — ทั้งคู่ไม่ใช่ "ข้าม" แต่อย่างแรกคือความเสี่ยง อีกอย่างคือความจริงที่ไม่ตรงเอกสาร
  - 📌 **บันทึกความคลาดไว้ในไฟล์ที่คนอื่นอ่านเจอ** (รอบนี้คือคอมมิต + รายงาน) — แผนที่ยังเขียนผิดจะหลอกคนถัดไปซ้ำ
- **Date Added:** 2026-10-01

### 🎨 Tailwind ไม่ได้เขียนสี theme ลง CSS เป็น hex — และ **การนับสตริงสีในไฟล์บิลด์ไม่ใช่หลักฐาน** (นับผิดได้สองทาง)
- **Context/Problem:** จะพิสูจน์ว่า "เปลี่ยน `emerald-*` → `ok-*` แล้วสีไม่เปลี่ยน" จึงนับ occurrence ของ hex เดิมใน
  `dist/assets/*.css` ก่อน/หลัง ⇒ **ได้ผลลัพธ์ที่บอกว่ามีของเพิ่มขึ้น** ซึ่งอ่านเหมือน "ทำพัง"
- **Root Cause:** **สองชั้น ซ้อนกัน**
  1. `theme.extend.colors` ถูกปล่อยเป็น **`rgb(R G B/var(--tw-*-opacity))`** ไม่ใช่ hex ⇒ hex ที่นับไม่เคยมีอยู่ตั้งแต่แรก
  2. ตัวที่ใส่ opacity modifier (`border-emerald-100/50`) ถูกปล่อยเป็น **hex 8 หลัก** (`#d1fae580`) ⇒ พอนับ `rgb(R G B` ก็ **ไม่เจอตัวพวกนี้** อีกเช่นกัน
  ⇒ สีเดียวกันถูกเขียนได้ **2 รูปแบบ** ขึ้นกับว่ามี `/opacity` หรือไม่ · และรูปแบบที่ 1 ก็ไม่ใช่ hex อยู่แล้ว ⇒ **ตัวนับแบบสตริงครอบไม่ได้ทั้งสองทางพร้อมกัน**
- **Correct Pattern/Solution:**
  - 🔴 **อย่านับสตริง ให้เทียบ "declaration"** — ดึงกฎจาก CSS ที่มี selector ตรงกับคลาสที่สนใจ แล้วเทียบ *เนื้อใน* ของกฎ ก่อน vs หลัง ⇒ คำตอบเป็น conclusiveness ไม่ใช่การประมาณ
    ```js
    // ต้อง match "บล็อกกฎ" ทั้งก้อนก่อน แล้วค่อยค้นในเนื้อใน — regex ที่บังคับให้ชื่อสีตามหลัง `.` ทันที
    // (เช่น /\.((?:[a-z-]*:)?(?:emerald|ok)[a-z0-9-]*)/) จะได้ 0 match เพราะ selector จริงคือ `.bg-emerald-500`
    ```
  - 🔴 **ยืนยันสองชั้น:** (1) ทุกคลาสที่พบใน `src/` **ต้องมีอยู่จริงใน CSS ที่บิลด์แล้ว** — Tailwind **ทิ้งคลาสที่พิมพ์ผิดเงียบ ๆ** ไม่มี warning ⇒ ถ้าคลาสหายไปจาก CSS แปลว่าพิมพ์ผิด ไม่ใช่ "ไม่มีใครใช้" · (2) คลาสคู่เก่า/ใหม่ต้องได้ declaration **เหมือนกันทุกไบต์**
  - 📌 **ตัวนับที่ให้ผล "มีของเพิ่ม" คือสัญญาณให้หยุดเชื่อตัวนับก่อน** — ก่อนสรุปว่าตัวเองทำพัง ให้ตั้งสมมติฐานว่าวิธีวัดผิด
- **Date Added:** 2026-10-01

### 👁 ข้อตรวจภาพที่ "กวาดทุก property ของทุก element" จะรายงานผลบวกลวงเป็นร้อย — ต้องผูก utility กับ property ที่มันตั้งจริง
- **Context/Problem:** เขียน Playwright ตรวจว่า "สีที่แสดงจริงตรงกับสเกล `ok-*` ไหม" ด้วยการกวาด element ที่มีคลาส `ok-*`
  แล้วอ่าน computed style ของ **ทุก property** ⇒ **ได้ 378 ข้อ "หลุดสเกล"** ทั้งที่สีถูกต้องทั้งหมด
- **Root Cause:** element ที่ถือคลาส `bg-ok-bright` ก็ยังมี `color: rgb(31,35,40)` (สีตัวอักษรที่สืบทอดมา),
  `borderColor: rgb(229,231,235)` (ค่าเริ่มต้น) และ `fill: rgb(0,0,0)` ติดมาด้วย ⇒ **ข้อตรวจไปตัดสิน property ที่คลาสนั้นไม่ได้เป็นคนตั้ง**
  · ต้นเหตุของ "ผลบวกลวง" ไม่ใช่โค้ดแอป แต่คือ **ความเข้าใจผิดว่าคลาสหนึ่งคุมทั้ง element**
- **Correct Pattern/Solution:**
  - 🔴 **ทำตาราง `prefix → property ที่มันตั้งจริง`** แล้วตรวจเฉพาะคู่ของตัวเอง — `bg-ok-`→`backgroundColor` · `text-ok-`→`color` ·
    `border-l-ok-`→`borderLeftColor` · `border-ok-`→4 ด้าน · `ring-ok-`→`boxShadow` · `fill-ok-`→`fill` · **ข้ามคลาสที่มี variant prefix**
  - 🔴 **ตัวกรองชื่อคลาสต้องคิดถึง `-` ที่คั่นอยู่ข้างหน้า** — `/(^|:)ok-/` **ไม่ match `bg-ok-bright`** เพราะ `ok-` ไม่ได้อยู่ต้นสตริงหรือหลัง `:` ⇒ ใช้ `/(?:^|[:-])ok(?:-|$)/`
    (รอบนี้ตัวกรองที่ผิดทำให้รายงาน "0 element" ซึ่งอ่านเหมือน "ไม่มีคลาสนี้ในหน้า" ทั้งที่หน้าเต็มไปด้วยคลาสนั้น)
  - 🔴 **ใส่ตัวเลข "หน้านี้เรนเดอร์จริงกี่ตัวอักษร" ลงในรายงานทุกหน้าด้วย** — ไม่งั้น "ไม่พบคลาส" กับ "หน้าไม่ขึ้น" **อ่านออกมาเหมือนกัน**
- **Date Added:** 2026-10-01

### 🔁 ตัวเลขที่ "เท่ากันเป๊ะ" บนหลายหน้า คือสัญญาณว่าหน้าเหล่านั้น **ไม่ได้เรนเดอร์สิ่งที่คิด** (redirect เงียบ)
- **Context/Problem:** สแกน 21 หน้า แล้วรายงานจำนวนตัวอักษรที่เรนเดอร์ · เห็น `home=1015` `terms=1015` `reports=1015` — **เท่ากันเป๊ะ 3 หน้า**
- **Root Cause:** เดา path ผิด (`/app/academic-terms`, `/app/board-reports`) ⇒ ทั้งคู่ **redirect ไป `/app/home`** ·
  ผลคือ **ตรวจหน้าเดิม 3 ครั้งแล้วรายงานว่า "3 หน้าผ่าน"** — ข้อตรวจที่ดูเหมือนกว้างที่สุดกลับแคบที่สุด
- **Correct Pattern/Solution:**
  - 🔴 **รายงาน URL ที่ลงจริงทุกหน้า เทียบกับ URL ที่ขอ** แล้วติดธงเตือนเมื่อไม่ตรง (`⚠️ landed=…`) — ราคาถูกกว่า `page.url()` เทียบอย่างละเอียด
  - 🔴 **`path` ที่เขียนในสคริปต์ตรวจ ต้องลอกจาก `src/router/index.ts` ไม่ใช่จากชื่อ route ที่เดา** — ชื่อ route กับ path ไม่ได้สะกดเหมือนกัน (`board-reports` อยู่ที่ `/app/boards/reports`)
  - 📌 จำนวนที่เท่ากันเป๊ะระหว่างหน้าต่าง ๆ **แทบไม่เคยเป็นเรื่องบังเอิญ** — ให้สงสัยก่อนดีใจ
- **Date Added:** 2026-10-01

### 🎨 สเกล `ok-*` มี **สองเขียวที่ต่างกันจริง** และมี **สองค่าที่ต่างกันแค่ 1 หน่วย** — อย่า "รวมให้สะอาด" โดยไม่ตรวจก่อน
- **Context/Problem:** หลังตั้ง token `ok` แทน `emerald` มีคำถามว่าจะยุบสเกลให้สั้นลงได้ไหม
- **Root Cause / ข้อเท็จจริงที่ต้องจำ:**
  - `ok` (`#15803D`) กับ `ok-strong` (`#047857`) **เป็นคนละเขียว** — ตัวแรกคือ `emerald-700` ตัวหลังคือ `emerald-700` คนละค่ากับที่ใช้ทำ hover ⇒ **ไม่ใช่ของซ้ำ** การยุบรวมจะเปลี่ยนสีปุ่ม hover ทั้งแอป
  - `ok-faint` (`#ECFDF5` = `emerald-50`) กับ `ok-soft` (`#F0FDF4` = `green-50`) ต่างกันแค่ **R −4 · G 0 · B −1** — ตาเปล่าแยกไม่ออก แต่ `ok-soft` ถูกใช้ใน **10 ไฟล์** ⇒ การ "รวมเข้าด้วยกัน" จะแตะ 10 ไฟล์เพื่อผลที่มองไม่เห็น
  - ลำดับสเกลคือ **strong → solid → bright → focus → line → tint → faint → soft** (เข้ม → อ่อน) ไม่ใช่เรียงตามชื่อ
- **Correct Pattern/Solution:**
  - 🔴 **ก่อนรวมค่าสีที่ "ดูเหมือนกัน" ให้เทียบ hex ทีละคู่ก่อน แล้วนับจำนวนจุดที่ใช้** — ถ้าต่างกันจริงหรือใช้กระจาย ให้ **บันทึกไว้แล้วปล่อย** ดีกว่าแก้ 10 ไฟล์เพื่อความสะอาดที่ไม่มีความหมาย
  - 🔴 **เขียนตาราง token → hex → ชื่อเดิม → หน้าที่ใช้ ไว้ในหัวไฟล์ `tailwind.config.js`** — คนถัดไปจะไม่ต้องรื้อค่านี้อีก
- **Date Added:** 2026-10-01

### ⚠️ หนี้ที่ **รู้ตัวแต่ไม่เก็บ** ต้องถูกเขียนลงเอกสาร ไม่ใช่ปล่อยให้หากันเองเจอ
- **Context/Problem:** รอบนี้ย้ายสี "สำเร็จ" จาก `emerald` → `ok-*` ครบทั้งแอป **แต่พาเลตต์ดิบยังเหลืออีกสองตระกูล**:
  **`amber` 34 จุดใน 6 ไฟล์** และ **`red` 33 จุด** — เป็นปัญหาแบบเดียวกันเป๊ะ แต่ `warn`/`danger` ในธีมมีแค่ `DEFAULT` + `soft` ⇒ ย้ายแล้วจะ **ไม่มีเฉดให้ใช้** ต้องออกแบบสเกลก่อน
- **Root Cause:** ด่านกันถอยหลัง (`lint:palette`) ครอบ **เฉพาะตระกูลเขียว** เพราะถ้าครอบทั้งสามตระกูลจะ **แดง 67 ข้อทันทีที่รันครั้งแรก** ⇒ ด่านที่แดงตลอดคือด่านที่ถูกปิด
- **Correct Pattern/Solution:**
  - 🔴 **ด่านกันถอยหลังที่ครอบ "บางส่วน" ต้องเขียนไว้ในหัวไฟล์ว่าส่วนที่เหลือคืออะไร เพราะอะไร** — ไม่งั้นคนอ่านจะเข้าใจว่าครบแล้ว
  - 🔴 **ห้ามขยายขอบเขตเงียบ ๆ เพื่อให้ด่านเป็นสีเขียว** — งานที่โผล่มาระหว่างทาง (สีที่ไม่ได้อยู่ในแผน) ให้ **รายงานเจ้าของแล้วรอตัดสิน** ไม่ใช่กลืนเข้าขอบเขตเอง
  - 📌 ผลพลอยได้: ด่านที่ครอบทั้งตระกูล (`emerald|green|teal|lime`) กัน `text-green-700` ที่หลุดเข้ามาทีหลังได้ด้วย — **กว้างกว่าที่แผนเขียนไว้หนึ่งขั้นโดยไม่เพิ่มงาน**
- **Date Added:** 2026-10-01

### 📛 ชื่อที่ **แผนเขียนไว้** ≠ ชื่อที่ **โค้ดตั้งจริง** — และเอกสารที่คัดลอกชื่อจากแผนจะผิดตามไปด้วย
- **Context/Problem:** ตอนปิดรอบ 5 เขียนเอกสาร 3 ไฟล์โดยอ้างชื่อ `NAV_REGISTRY` ว่าเป็นที่เก็บเมนู
  (คัดมาจากแผน R0.0 ซึ่งเขียนชื่อนี้ไว้) — ความจริงคือ **ไม่มี export ชื่อนี้อยู่เลยในเรพ**
  ชื่อจริงคือ `NAV_TABS` (`constants/nav.ts:68`) และ `NAV_GROUPS` (`:162`)
  ⇒ คำว่า `NAV_REGISTRY` เหลืออยู่แค่ใน **คอมเมนต์ประวัติของเทสต์** ซึ่งพออ่านผ่าน ๆ จะดูเหมือนชื่อจริง
- **Root Cause:** แผนถูกเขียน **ก่อน** มีโค้ด ⇒ ชื่อในแผนคือ *ความตั้งใจ* ไม่ใช่ *ข้อเท็จจริง*
  · และเมื่อค้นด้วย `grep NAV_REGISTRY` **เจอคอมเมนต์ในเทสต์** ⇒ ได้หลักฐานยืนยันผิด ๆ ว่ามีอยู่จริง
  ⇒ ความผิดพลาดชนิดนี้ **ไม่ถูกจับด้วยการอ่านทวน** เพราะข้อความอ่านลื่นและดูสมเหตุสมผลทั้งหมด
- **Correct Pattern/Solution:**
  - 🔴 **ชื่อ symbol ทุกตัวที่เขียนลงเอกสาร ต้องมาจาก `grep "export const <ชื่อ>"` ในไฟล์จริง ไม่ใช่จากแผน**
    ```bash
    grep -n "^export const\|^export function" frontend/src/constants/nav.ts   # ← ก่อนอ้างชื่อไหนก็ตาม
    ```
  - 🔴 **`grep` เจอชื่อใน "คอมเมนต์" ไม่ใช่หลักฐาน** — ต้องเจอใน **บรรทัดประกาศ** (`export const …`) เท่านั้น
    ⇒ ถ้าคำที่ค้นเจอทุกจุดอยู่ในคอมเมนต์/เทสต์ ให้ถือว่ายังไม่ยืนยัน
  - 📌 วิธีจับเร็ว: ให้ subagent ที่ **ไม่มีบริบทของแผน** ไล่ตรวจเอกสารกับโค้ด — รอบนี้ agent ตัวเดียวจับได้
    10 ข้อใน 7 ไฟล์ รวมข้อนี้ ซึ่งการอ่านทวนด้วยตัวเองมองข้ามไปแล้ว
- **Date Added:** 2026-10-01

### 🔢 ตัวเลขในเอกสารที่ไม่มีใครนับใหม่ = ตัวเลขที่จะผิดแน่นอน (เจอ 4 จุดพร้อมกันในรอบเดียว)
- **Context/Problem:** ไล่ตรวจเอกสาร 7 ไฟล์กับโค้ดจริง เจอตัวเลขที่ล้าสมัย **4 ข้อในการตรวจครั้งเดียว**:
  `18 จาก 44 ไฟล์มี <style>` (จริง: 17 จาก 64) · `response_model 92/94 · ยกเว้น 2 แบบ`
  (จริง: 92/95 · ยกเว้น 3) · `test_events.py มี 26 ช่วง` (จริง: 28) · `Row locking ใช้ใน 4 ไฟล์`
  (จริง: 7) — **ทุกข้อเป็นจริง ณ วันที่เขียน แล้วโค้ดเดินต่อโดยไม่มีใครกลับมาแก้**
- **Root Cause:** ตัวเลขเป็น **คำยืนยันที่ตรวจซ้ำได้ถูกที่สุด** และในขณะเดียวกันก็ **เน่าเร็วที่สุด**
  ⇒ ตัวเลขที่ผูกกับ "สถานะของเรพ" (จำนวนไฟล์/บรรทัด/endpoint) จะผิดทันทีที่มีคนเพิ่มไฟล์
  โดยที่ **ไม่มีสัญญาณเตือนใด ๆ** — ต่างจากชื่อ symbol ที่ `grep` จับได้ทันทีเมื่อค้น
- **Correct Pattern/Solution:**
  - 🔴 **ถ้าจะใส่ตัวเลข ให้ใส่ "วันที่วัด" กำกับเสมอ** และถ้าเป็นตัวเลขที่คนอ่านจะใช้ตัดสินใจ
    (เช่น "ยกเว้นกี่ข้อ") ให้ใส่ **คำสั่งที่ใช้วัด** ไว้ข้าง ๆ ด้วย ⇒ คนถัดไปวัดใหม่ได้ใน 5 วินาที
  - 🔴 **ตัวเลขที่อธิบาย *กฎ*** (เช่น "ยกเว้น 2 แบบ") อันตรายกว่าตัวเลขที่อธิบาย *ขนาด*
    — เพราะคนอ่านจะใช้มัน **ตัดสินว่าเคสของตัวเองเข้าข้อยกเว้นไหม** ⇒ รอบนี้มีคนเพิ่ม `DELETE` 204
    ที่ไม่มี `response_model` แล้ว **เอกสารไม่รู้** ⇒ คนถัดไปจะ "แก้" ให้ใส่ `response_model` บน 204
  - 📌 ทางเลือกที่ปลอดภัยกว่า: **เขียนเงื่อนไข ไม่เขียนจำนวน** ("ทุก route ต้องมี `response_model`
    ยกเว้นที่ไม่มี JSON body: ดาวน์โหลดไฟล์ · SSE · 204") ⇒ ยังจริงตลอดไปโดยไม่ต้องนับ
- **Date Added:** 2026-10-01

### 🧪 เทสต์ e2e ที่ไม่ได้รันระหว่าง refactor = เทสต์ที่จะพังเงียบ ๆ ตอนรันครั้งถัดไป
- **Context/Problem:** ปิดรอบ 5 แล้วรัน `npm run test:e2e` ครั้งแรกของการ refactor ทั้งชุด
  (แผนกำหนดให้รันตั้งแต่ R0 แต่รอบนี้ไม่มี backend ที่ `localhost:8000`) ⇒ เจอ selector ที่ล้าสมัย
  **2 จุดในไฟล์เดียว** และทั้งคู่ **ผ่าน type-check/lint/unit ครบทั้ง 4 ด่าน** เพราะไม่มีด่านไหนอ่าน `e2e/`
  - `.bg-emerald-500` — พาเลตต์ `emerald-*` ถูกถอดออกตั้งแต่ R5.5 (ของจริงคือ `.bg-ok-bright`)
  - `'ปัดตกแล้ว'` — คำว่า "ปัดตก" ถูกห้ามใช้ใน UI ตั้งแต่ R5.1 (ของจริงคือ `'ไม่ดำเนินการแล้ว'`)
- **Root Cause:** `e2e/` เป็น **ผู้บริโภคปลายทาง** ของทั้ง (ก) ชื่อคลาสที่ Tailwind generate
  และ (ข) ข้อความไทยใน UI — ทั้งสองอย่างเป็น *ผลลัพธ์* ของการ refactor ไม่ใช่ *โค้ดที่ถูกแก้*
  ⇒ `grep` ของด่านต่าง ๆ สแกนแค่ `src/` · `vue-tsc` ไม่รู้จัก selector · `vitest` ไม่ render view
  ⇒ **ไม่มีความล้มเหลวใด ๆ ปรากฏจนกว่าจะรัน e2e จริง** ซึ่งต้องมี backend + seed + browser
- **Correct Pattern/Solution:**
  - 🔴 **รัน `test:e2e` ให้ได้ตั้งแต่รอบแรกที่แตะ UI** อย่ารอปิดรอบ — ราคาของการค้นพบตอนปิดรอบ
    คือต้องย้อนไปหาว่ารอบไหนทำให้พัง ซึ่งแพงกว่าการรู้ทันทีหลายเท่า
  - 🔴 **ก่อนรัน e2e ให้ `grep` selector ทุกตัวเทียบกับ `src/` ก่อน** — จับได้ในไม่กี่วินาที:
    ```bash
    # data-testid ทุกตัวที่เทสต์อ้าง
    grep -o "getByTestId('[^']*'" e2e/*.spec.ts | sort -u
    # ชื่อคลาส/ข้อความที่ assert — ตัวที่อ้างสีหรือคำจากพาเลตต์/glossary เสี่ยงที่สุด
    grep -n "locator('\.\|getByText('" e2e/*.spec.ts
    ```
  - ⚠️ **selector ที่อ้าง "สี" หรือ "คำจาก glossary" เน่าบ่อยที่สุด** เพราะสองอย่างนี้
    เป็นสิ่งที่รอบเก็บงาน (R5) **ตั้งใจเปลี่ยน** ⇒ ถ้าเพิ่ม selector ใหม่ ให้ผูกกับ `data-testid`
    ซึ่งเป็นสัญญาที่ตั้งใจสร้าง ไม่ใช่คลาสสีหรือข้อความที่ใครก็แก้ได้
  - 📌 เตรียมสภาพให้รันได้ไว้เป็นคำสั่งเดียว (ดู entry ถัดไปเรื่องพอร์ต/CORS ก่อนรัน)
- **Date Added:** 2026-10-01

### 🌐 รัน dev server คนละพอร์ตกับที่ CORS อนุญาต = แอปเด้งไป `/login` เงียบ ๆ (หน้าตาเหมือนบั๊ก re-render)
- **Context/Problem:** รัน e2e แล้วเจออาการที่อ่านว่าบั๊กหนัก: `getByTestId('cat-suggestion').click()`
  ล้มด้วย `element is not stable` → `element was detached from the DOM, retrying` **วนไม่หยุด**
  จน timeout 60 วินาที — ดูเหมือนหน้า re-render วนเป็นลูป
  ⇒ probe ด้วย `MutationObserver` พบ `added: 1, removed: 0` คือ **ไม่มีลูปเลย**
  แต่ `location.href` กลายเป็น `/login` และ `localStorage.access_token` **ถูกล้าง**
- **Root Cause:** `backend/main.py` ตั้ง `allow_origins` แบบ **ฮาร์ดโค้ด** ไว้แค่
  `http://localhost:5173` · `127.0.0.1:5173` · `0.0.0.0:5173` + โดเมนจริง
  ⇒ การรัน Vite ที่พอร์ตอื่น (เช่น 5199) ทำให้ทุกคำขอ API ถูกเบราว์เซอร์บล็อกที่ CORS
  → axios ไม่ได้ response → `api.ts` ล้าง token + เด้ง `/login` → หน้าที่กำลังทดสอบถูกถอดออก
  ⇒ **อาการที่เห็นไม่มีความเกี่ยวข้องกับสาเหตุเลย** (อ่านว่า render loop ทั้งที่จริงคือ auth redirect)
  ⚠️ และเพราะคำขอถูกบล็อกที่เบราว์เซอร์ **`page.on('response')` ไม่ยิง** ⇒ ดู network ไม่เห็นอะไรผิด
- **Correct Pattern/Solution:**
  - 🔴 **ยึดพอร์ต 5173 ให้ได้** — ถ้าถูกโปรเจคอื่นถือ ให้เช็คก่อนว่ามันยึด *อินเทอร์เฟซไหน*:
    ```bash
    ss -ltnp | grep 5173     # เจอ [::1]:5173 = IPv6 เท่านั้น ⇒ ผูก IPv4 ทับได้
    npx vite --host 127.0.0.1 --port 5173 --strictPort
    ```
    ⇒ `127.0.0.1:5173` อยู่ใน `allow_origins` แล้ว จึงไม่ต้องแก้ CORS ของโปรดักต์เลย
  - 🔴 **`playwright.config.ts` อ่าน `E2E_BASE_URL` ได้** (เพิ่มในรอบนี้) ⇒ ชี้เป้าได้โดยไม่ต้องแก้ไฟล์:
    ```bash
    CI=1 E2E_BASE_URL=http://127.0.0.1:5173 npx playwright test --project=chromium
    ```
  - 🚩 **สัญญาณของคลาสนี้:** element ที่ "resolved ได้แต่ไม่ stable / detached วน" + ไม่มี error ในคอนโซล
    ⇒ **อย่าเพิ่งไปหาบั๊ก re-render** ให้เช็ค `location.href` กับ `localStorage` ก่อนทุกครั้ง
  - ⚠️ `page.on('response')` **ไม่เห็นคำขอที่ถูกบล็อก** — ถ้าสงสัย CORS ให้ฟัง `requestfailed` ด้วย
- **Date Added:** 2026-10-01

### 🧱 กริด 2 ช่องที่ชื่อยาวไม่เท่ากัน — "กึ่งกลางช่องที่เหลือ" ทำให้ชื่อเยื้องกัน ต้องปล่อยให้ "ชิดใต้ไอคอน"
- **Context/Problem:** การ์ดเมนูลัดหน้าแรกมี 2 ไทล์ใน `grid grid-cols-2` ชื่อไทยยาวไม่เท่ากัน
  ("เว็บโรงเรียน" 1 บรรทัด vs "ระบบดูแลช่วยเหลือนักเรียน" 2 บรรทัด) ⇒ ออกแบบครั้งแรกโดยให้ไทล์
  `justify-start` + ที่ชื่อใส่ `flex-1 items-center` เพื่อดันชื่อให้อยู่กึ่งกลาง *ช่องที่เหลือ*
  ⇒ ไอคอนตรงกันก็จริง แต่ **ชื่อสองไทล์ลอยอยู่คนละระดับ** ซึ่งตาอ่านเป็น *บั๊กการจัดวาง* ทันที
  (เห็นชัดในภาพที่ 360dp: ชื่อ "เว็บโรงเรียน" จมลงมาอยู่กึ่งกลางช่องว่าง)
- **Root Cause:** `flex-1` ทำให้ `<span>` ของชื่อ **ยืดเต็มพื้นที่ที่เหลือทั้งสองไทล์เท่ากัน**
  ⇒ กล่องเท่ากันแต่ **ข้อความที่จัดกึ่งกลางในกล่องมีจำนวนบรรทัดไม่เท่ากัน** จึงไปคนละตำแหน่ง
  ⚠️ และวัดด้วย `getBoundingClientRect()` **ไม่เห็นความต่างนี้เลย** (ได้ `t` เท่ากันทั้งคู่
  เพราะกล่องเท่ากัน) ⇒ ถ้าวัดอย่างเดียวจะสรุปผิดว่าทั้งสองแบบเหมือนกัน
- **Correct Pattern/Solution:**
  - 🔴 **ปล่อยให้ชื่อชิดใต้ไอคอนเสมอ** (`justify-start` ที่ไทล์ · ชื่อ **ไม่มี** `flex-1`)
    ⇒ ชื่อทั้งสองเริ่มที่ระดับเดียวกัน (ยืนยันด้วยการวัด: `labels[].t` เท่ากัน = 258 ทั้งคู่)
    แล้วยอมรับว่าช่องว่างที่เหลือไปกองท้ายไทล์ที่ชื่อสั้นกว่า
    — **ช่องว่างในกรอบเปล่าสังเกตยากกว่าชื่อที่เยื้องกันมาก**
  - 🔴 **ห้าม `justify-center` ที่ไทล์** — ไทล์ที่ชื่อสั้นกว่าจะถูกจัดกึ่งกลางทั้งบล็อก
    ⇒ **ไอคอนเยื้องกัน** (~10px) ซึ่งแย่กว่าทั้งสองทาง
  - 🔴 **ตัดสินจากภาพจริงที่ความกว้างจริง ไม่ใช่จากความรู้สึก** — วัด `tiles[].h`, `icons[].t`,
    `labels[].t` ประกอบกัน อย่าดูแค่ค่าเดียว (ดูข้อ ⚠️ ข้างบน)
  - ⚠️ **ต้องใส่ `font-sans` + โหลดฟอนต์ไทยจริงในหน้า preview ด้วย** ไม่งั้นข้อความไทย
    กลายเป็นกล่อง (tofu) แล้ว metrics ผิด → นับจำนวนบรรทัดผิด (เจอจริง: วัดได้ 3 บรรทัด
    ทั้งที่ของจริง 2) · คอนเทนเนอร์นี้ **ไม่มีฟอนต์ไทยติดตั้งเลย** (`fc-list :lang=th` = ว่าง)
    ⇒ preview ต้อง `<link>` Google Fonts ตัวเดียวกับ `index.html`
  - ⚠️ กริดที่ปล่อยเต็มความกว้างจะแบนบนเดสก์ท็อป: คอลัมน์เนื้อหาจริง =
    `max-w-7xl` − sidebar 264px − padding ≈ **952px** ⇒ ไทล์ 2 ช่องจะกลายเป็น 453×104
    (แบนจนไม่เหมือน "เมนูลัด") ต้องครอบ `max-w-sm mx-auto` (384px ⇒ ไทล์ 186px)
- **Date Added:** 2026-10-01

### 🧪 `import.meta.url` ไม่ใช่ URL ระนาบ `file:` ภายใต้ jsdom — หาไฟล์ในเทสต์ต้องใช้ `createRequire().resolve()`
- **Context/Problem:** เขียนเทสต์ที่ต้องอ่าน CSS ของไลบรารีจริงจาก `node_modules`
  (`bootstrap-icons.css`) แล้วใช้สูตรที่จำกันมา:
  `fileURLToPath(new URL('../../node_modules/...', import.meta.url))`
  ⇒ ล้มทันทีทั้งไฟล์: **`TypeError: The URL must be of scheme file`**
- **Root Cause:** ภายใต้ `environment: 'jsdom'` ของ vitest ค่า `import.meta.url` **ไม่ใช่
  `file:///...`** ⇒ พอเอาไปเป็น base ของ `new URL()` จะได้ URL ที่ scheme ไม่ใช่ `file:`
  แล้ว `fileURLToPath()` ปฏิเสธ · อาการคือ **เทสต์ไม่รันเลย (0 test)** ไม่ใช่เทสต์แดง
  ซึ่งอ่านผิดเป็น "เขียนเทสต์ผิด" ได้ง่าย
- **Correct Pattern/Solution:**
  - 🔴 ให้ Node หาไฟล์เอง — ถูกต้องทุก cwd และข้ามเรื่อง scheme ไปเลย:
    ```ts
    import { createRequire } from 'node:module'
    import { join } from 'node:path'
    createRequire(join(process.cwd(), 'package.json')).resolve('bootstrap-icons/font/bootstrap-icons.css')
    ```
  - 🔴 ไล่ลองทีละฐาน (`process.cwd()` แล้วค่อย `process.cwd()/frontend`) เพื่อให้รันได้ทั้งจาก
    `frontend/` และจาก root ของ monorepo — และ **โยน Error ที่บอกวิธีแก้** ("ต้องรันหลัง
    `npm install` ใน frontend/") ไม่ใช่ปล่อยให้ `ENOENT` เปล่า ๆ
  - 🚩 **สัญญาณของคลาสนี้:** `Test Files 1 failed` + **`Tests no tests`** + error ที่บรรทัด
    ระดับโมดูล (ไม่ใช่ใน `it()`) ⇒ ปัญหาอยู่ที่ *การโหลดไฟล์* ไม่ใช่ *ตรรกะของเทสต์*
- **Date Added:** 2026-10-01

### 🧟 "Mutation ที่ดูเหมือนพัง" อาจไม่ใช่ mutation — ตรวจก่อนสรุปว่าเทสต์มีรู
- **Context/Problem:** ทดสอบคุณภาพเทสต์ด้วยการทำโค้ดพัง (mutation) ตามวินัยของโปรเจกต์:
  เปลี่ยนชื่อไอคอน `bi-person-heart` → `bi-person-hearts` เพื่อหวังให้เทสต์
  "ไอคอนต้องมีอยู่จริงใน bootstrap-icons" จับ ⇒ **เทสต์ผ่านทั้ง 13 ข้อ** (เหมือนเทสต์มีรู)
- **Root Cause:** `bi-person-hearts` (**พหูพจน์**) **มีอยู่จริง** ใน bootstrap-icons 1.13.1
  (`content: "\f77b"`) ⇒ นั่นไม่ใช่ mutation แต่คือการเปลี่ยนไปใช้ไอคอนที่ถูกต้องอีกตัว
  ⇒ เกือบไป "แก้เทสต์ที่ไม่ได้พัง" ซึ่งจะทำให้เทสต์อ่อนลงโดยไม่มีเหตุ
- **Correct Pattern/Solution:**
  - 🔴 **ยืนยันก่อนว่า mutation นั้นผิดจริง** ด้วยการเช็คกับต้นทาง เช่น
    `grep -c '\.bi-person-heartt::before' node_modules/bootstrap-icons/font/bootstrap-icons.css`
    → ต้องได้ **0** ก่อน จึงเรียกว่า mutation
  - 🔴 ทางที่ดีกว่าคือ **mutate แบบที่ไม่ต้องเดาชื่อ**: ทำไฟล์ที่อ้างถึง *หายไป*
    (เปลี่ยน path เป็นไฟล์ที่ไม่มี) แล้วดูว่า error message ที่ออกมาช่วยผู้ใช้จริงไหม
  - 🔴 **เทสต์ไอคอนต้องเทียบกับ CSS ของไลบรารีจริง ไม่ใช่รายชื่อที่เราจำได้** — คลาส `bi-`
    ที่พิมพ์ผิดจะ **ไม่ขึ้นอะไรเลยและไม่ error** (ไม่มี `::before` = ไม่มี glyph)
    ⇒ เป็นบั๊กที่มองไม่เห็นจาก UI และไม่มีอะไรฟ้อง
  - ⚠️ **ห้ามใช้ `git checkout -- <file>` คืนไฟล์ที่ยัง untracked** (จะล้มเงียบ ๆ เพราะไม่มี
    อะไรให้ checkout) ⇒ สำรองด้วย `cp` ไป `/tmp` **ก่อน** mutate แล้วคืนด้วย `cp` เสมอ
    (เจอจริง: เทสต์ค้างอยู่ในสภาพที่ถูก mutate แล้วต้องมานั่งซ่อม)
- **Date Added:** 2026-10-01

### 🗜️ "ยุบบล็อกที่ว่าง" — เงื่อนไข `จำนวน === 0` หลอกได้ 3 ทาง และ `?? []` คือทางที่แย่ที่สุด
- **Context/Problem:** หน้าแรกแสดงบล็อก *รอฉันตอบ · สรุปเรื่องของฉัน · สถิติของฉัน · คิวจัดการรายงาน*
  เป็นการ์ดเต็ม (หัวการ์ด + `AppEmptyState` ≈ 250–300dp ต่อบล็อก) **แม้ตอนไม่มีอะไรให้ทำ** ⇒ วัดที่ 360dp
  รวมกัน **1,125dp ≈ 1.8 จอ** ของ "ความว่าง" ที่ไม่มีใครอ่าน · เจ้าของระบบสั่งให้ยุบ
- **Root Cause:** ตรรกะ "ว่างไหม" ถูกเขียนเป็น `v-if` ในเทมเพลตด้วย `list.length === 0` ซึ่ง
  **แยกไม่ออกระหว่าง 3 สถานะที่ให้ผลเหมือนกันเป๊ะ**:
  1. **ว่างจริง** — โหลดเสร็จ ไม่มีอะไร
  2. **ยังโหลดไม่เสร็จ** — `[]` เหมือนกัน
  3. 🔴 **โหลดพัง** — `const x = data?.items ?? []` ⇒ ตอน error ได้ `[]` **และ** `loading=false`
     ⇒ เงื่อนไข "ว่าง" **เป็นจริงทั้งที่ API ล่ม** แล้วจอขึ้น "ไม่มีเรื่องค้างรอคุณ" ซึ่งผู้ใช้อ่านแล้วเชื่อ 100%
     และ **ไม่มีสัญญาณไหนบอกว่าผิด** (ต่างจากกรณี error ปกติที่มีการ์ดแดงขึ้น)
  · แถมอีกสองกับดักที่โผล่ตอนตรวจ: (ก) `loadingReports` ของบล็อกคิว **เป็น `false` ได้โดยไม่เคยยิงเลย**
  (เริ่มที่ `isCouncil`, `loadReports()` `return` ทันทีเมื่อ `!isCouncil` ⇒ สิทธิ์ที่กลายเป็นจริง *หลัง* mount
  จะเจอ "โหลดเสร็จ + ว่าง" จากข้อมูลที่ไม่มีอยู่) (ข) บล็อกแดชบอร์ดมี `v-if` แค่ loading/error/data
  **ไม่มีสาขาสุดท้าย** ⇒ `!loading && !error && !data` ขึ้นหัวการ์ดลอยที่มีปุ่มแต่เนื้อในว่างเปล่า (อ่านเป็น "โหลดค้าง")
- **Correct Pattern/Solution:**
  - 🔴 **แยก "ว่าง/พัง/กำลังโหลด" เป็นฟังก์ชันบริสุทธิ์ที่ทดสอบได้** ไม่ใช่ `v-if` ในเทมเพลต —
    `frontend/src/types/home.ts` คืน `'hidden' | 'collapsed' | 'full'` (แบบเดียวกับ `checkInCardState()`)
    · ทุกฟังก์ชัน **รับ `homeError`/`loading`/`loaded` เข้ามาเอง** ไม่พึ่ง `v-if` ที่อื่นห่าง ๆ
    ⇒ ตารางความจริง 3×5 เขียนเทสต์ได้โดยไม่ต้อง mount view (`homeEmptyCollapse.spec.ts`)
  - 🔴 **`?? []` ห้ามเป็นต้นทางของเงื่อนไข "ว่าง"** — อ่านจากตัวแปร error/loading แทน · `null` = *ยังไม่รู้*
    ต้อง **fail closed** (`statsAllZero(null) === false` ไม่ใช่ `true`)
  - 🔴 **"ว่าง" ที่มีสองสัญญาณ ต้องเช็คทั้งคู่** — "รอฉันตอบ" (`current_assignee_id = ฉัน`) กับ
    "ยังไม่อ่าน" (`issue_received`) เป็น**คนละชุดข้อมูล** · ยุบเมื่อยอดแรกเป็น 0 แต่ยอดหลัง > 0
    ⇒ **ป้าย badge ที่หัวการ์ดหายไปพร้อมสิ่งเดียวที่บอกว่ามีของใหม่**
  - 🔴 **คอมโพเนนต์ที่ใช้ร่วมสองหน้าต้องไม่เก็บกติกาของหน้าใดหน้าหนึ่ง** — `PersonalStatsCard`
    ใช้ทั้ง `Home` (ยุบได้) และ `Profile` (ต้องเห็นกล่อง "ยังไม่มีสถิติ" เต็ม) ⇒ กติกาอยู่ที่ `Home`
    และดึง "*0 ทุกช่อง*" ออกมาเป็น `statsAllZero()` ที่เดียว (ถ้าก๊อปไว้สองที่ วันหน้าจะยุบหน้าเดียว)
  - **ยุบ ≠ ซ่อน** — บล็อก *ของที่ต้องทำ* (โหวต/กิจกรรม/ประกาศ) ซ่อนเมื่อว่าง = ถูกแล้ว
    แต่บล็อก *ของของฉัน* ความว่าง **เป็นข้อมูล** ⇒ เหลือแถว 44dp (`AppEmptyRow`) พร้อมทางออกท้ายแถว
  - ⚠️ **เทสต์ "แถวที่มี `:to` ต้องมี `action-label` ด้วย" ไม่พอ** — ลบ `:to` ออกจาก *แถวใดแถวหนึ่ง*
    แล้วเทสต์ยังเขียว (แถวที่เหลือยังมีคู่ครบ) ⇒ **ต้องล็อกรายตัวว่าแถวไหนต้องมีทางออก/ต้องไม่มี**
    (เจอจริงตอน mutation battery — เคสที่เทสต์ผ่านทั้งที่ของหาย)
  - ⚠️ **`::before` ใน `bootstrap-icons.css` กลายเป็น `:before` หลังบิลด์** (minifier ย่อ)
    ⇒ เทสต์ที่ grep หาไอคอนจาก **ไฟล์บิลด์** ต้องรับทั้งสองแบบ หรืออ่านจาก `node_modules` (แบบที่ทำอยู่)
  - 🚩 **สัญญาณของคลาสนี้:** หน้าที่ยิงหลาย API พร้อมกันแล้วมี "บล็อกว่าง" หลายบล็อก ·
    เห็นคำว่า `?? []` หรือ `|| []` อยู่ใกล้เงื่อนไข empty state · หรือ UI ที่บอก "ไม่มี…" ทั้งที่ไม่มี
    error ให้เห็นเลย
- **Date Added:** 2026-10-02

### 🎬 "ยืนยันบน staging จริง" ต้องมีบัญชีที่ล็อกอินได้ — ไม่มีก็ได้แค่ระดับบันเดิล และ Playwright มีกับดัก 3 ตัวที่ทำให้ "รันไม่จบ" ดูเหมือน "ไม่มีอะไรเกิดขึ้น"
- **Context/Problem:** งานยุบบล็อกว่างตรวจได้แค่ระดับ CSS/บันเดิล (`grep` ในไฟล์ที่ container เสิร์ฟ)
  เพราะเชื่อว่า "ไม่มีบัญชีให้ล็อกอิน staging" ⇒ **ไม่มีใครเห็นเลยว่าของจริงหน้าตาเป็นอย่างไร**
  · พอได้บัญชีมาแล้วก็เจอกับดักต่อเนื่อง: สคริปต์ Playwright **timeout 30s ทุกครั้ง** ที่ `networkidle`
  · ภาพ `fullPage: true` **จับได้แค่จอแรก** · และตัวเฝ้ารอที่ poll ด้วย `ssh` **ไม่ยิง event เลย**
  จน timeout 1 ชม. ทั้งที่ deploy จบไปแล้ว 57 นาที
- **Root Cause:** (ก) บัญชี seed ใน `backend/scripts/e2e_seed.py` **ถูกใช้กับ staging จริงด้วย** ไม่ใช่แค่
  DB ท้องถิ่น — รหัสอยู่ใน `/tmp/e2e_credentials.json` · (ข) หน้าแอปเปิด **SSE ค้างไว้** ⇒ ไม่มี
  `networkidle` ตลอดกาล ⇒ timeout ไม่ใช่ "หน้าโหลดช้า" · (ค) หน้าแรก **เลื่อนใน container ข้างใน**
  ไม่ใช่ `window` ⇒ `fullPage` จับได้เท่าจอ · (ง) ตัวเฝ้ารอที่ poll ผ่าน `ssh` ในบริบท background
  คืนค่าว่างเงียบ ๆ ⇒ เงื่อนไข "จบแล้ว" ไม่เคยเป็นจริง และ **การถูก kill ฝั่ง local ไม่ได้ฆ่า deploy
  บน VPS** (ssh ตาย แต่ `pull_all.sh` เดินต่อจนจบ)
- **Correct Pattern/Solution:**
  - ตรวจ UI บน staging ด้วยบัญชี seed: `POST /api/auth/login` → `addInitScript` ตั้ง
    `localStorage.access_token` + `user_id_str` (แบบเดียวกับ `frontend/e2e/piri-boards-flow.spec.ts`)
    · **อ่านรหัสจากไฟล์ตอนรัน ห้ามพิมพ์ลง log** · สคริปต์ต้องวางใน `frontend/` (ESM resolve จากที่อยู่สคริปต์)
  - ⚠️ `waitUntil: 'domcontentloaded'` + `waitForTimeout` **แทน `networkidle` เสมอ** เมื่อแอปมี SSE
  - ⚠️ ต้องการภาพทั้งหน้า: วน `querySelectorAll('*')` แล้วตั้ง `scrollTop = scrollHeight`
    ให้ทุก element ที่ `scrollHeight > clientHeight + 20`
  - ⚠️ **อย่ารอ deploy ด้วย background task** — เขียน log ลงไฟล์บน VPS แล้ว `ssh … tail` สั้น ๆ
    เป็นระยะ + `pgrep -af pull_all` · ยืนยันผลด้วย `docker service ps <name> --format '{{.CurrentState}} {{.Image}}'`
  - **เกณฑ์ปิดงาน:** พิสูจน์ให้ครบ *ทุกสภาพข้อมูล* — ยุบหมด / ผสม (บางบล็อกมีของ) / ไม่ยุบเลย
    (รอบนี้ใช้ `e2eadm` / `e2ecou` / `e2estu` ครบทั้งสาม)
- **Date Added:** 2026-10-02

### 📮 ARQ worker สองตัวที่ไม่ได้ตั้ง `queue_name` แชร์คิวเดียวกัน — งานหายครึ่งโดยที่ API ตอบ **200** และไม่มี error ที่ไหนเลย
- **Context/Problem:** ระหว่างทดสอบ import บน staging พบว่า job ค้าง `QUEUED` ตลอดกาลเป็นบางครั้ง
  (วัดได้ ~ครึ่งหนึ่ง) · `POST /api/start-import-job/{id}` ตอบ **200**, DB ขึ้น `QUEUED`,
  ครูไม่เห็น error — **แต่งานถูกทิ้งถาวร** · อาการเดียวกันกระทบ push notification ด้วย
  (คนละทิศ: cron ของ push ถูก import worker ทิ้งทุก 20 วินาที)
- **Root Cause:** ARQ ใช้ `arq.constants.default_queue_name` (`'arq:queue'`) **เมื่อ `WorkerSettings`
  ไม่ได้ตั้ง `queue_name`** · `import_worker` กับ `push_worker` ต่างไม่ตั้ง และใช้ `REDIS_URL`
  ตัวเดียวกัน ⇒ ทั้งคู่ฟังคิวเดียวกัน · ARQ ดึงงานจาก Redis list แบบ **atomic** ⇒ งาน 1 ชิ้นไปถึง
  worker **เพียงตัวเดียว** ตัวที่ไม่รู้จักฟังก์ชันนั้นจะ log `function ... not found` แล้ว **ทิ้งงาน**
  · ⚠️ `enqueue_job` **คืน `None` ทั้งตอนสำเร็จและตอนลงคิวที่ไม่มีใครฟัง** ⇒ ความผิดพลาดชนิดนี้
  เงียบสนิท ไม่มีสัญญาณเตือนใด ๆ · `recover_stuck_jobs` ช่วยได้แค่หลัง
  `IMPORT_RECOVERY_STALE_MINUTES` หรือตอน worker restart — **และ re-enqueue ลงคิวที่แข่งขันกันเดิม**
  ⇒ ไม่ใช่ทางแก้
- **หลักฐาน (staging, 7 ต.ค. 2026):**
  - 🧾 **ตัวเลขสรุปจากบรรทัดปิด container** (ชัดที่สุด ไม่ต้องเดาจาก log ยาว):
    import_worker `shutdown on SIGTERM ◆ 6 jobs complete ◆ 1247 failed` ·
    push_worker `547 jobs complete ◆ 0 failed` ⇒ งานที่ตกผิดฝั่งถูกทิ้ง **100%**
    (ไม่ใช่ "บางครั้งพัง" — งานที่ไปถึงผิดตัวไม่มีทางสำเร็จเลย)
  - ⏱️ `not found` ตัวสุดท้ายของ container เก่า = `14:56:40` แล้ว **`shutdown` ที่ `14:56:45`**
    ⇒ บั๊กยังเป็นอยู่จนวินาทีที่ deploy ตัวซ่อม (ไม่ใช่ปัญหาที่หายเองไปแล้ว)
  - **การทดลองตัดสิน:** สเกล `push_worker=0` ⇒ job ที่ค้างอยู่จบใน **0–3 วินาที**
  - ✅ **หลังซ่อม:** container ใหม่ `not found` = **0** · งาน import สำเร็จ **6/6** (0.03–0.40 วิ/งาน)
    ยิง 6 รอบติดกันโดย**ไม่แตะ push_worker** ⇒ ถ้ายังพังอยู่โอกาสรอด 6 รอบ = ~1.6%
  - ✅ Redis มี **สองคิวจริง**: `arq:queue:import:health-check` + `arq:queue:push:health-check`
    (ไม่มี `arq:queue` เดี่ยว ๆ อีก)
  - `docker-compose.app.yml` + `backend/workers/` **ไม่เปลี่ยน** ระหว่าง `8c60b5d` กับ `bfa4d16`
    ⇒ ยืนยันว่าไม่ใช่ผลจากงานที่เพิ่งทำ (บั๊กมีมาก่อน)
- **กับดักตอนอ่านหลักฐาน (ผมพลาดเองรอบแรก):** `docker service logs <svc>` คืน log ของ
  **ทุก task ที่เคยรัน** ไม่ใช่แค่ตัวปัจจุบัน ⇒ ตอน grep เจอ `18:27:48: ... not found` แล้วอ่านว่า
  "เพิ่งเกิด" ทั้งที่มันคือของ **1–2 ต.ค.** (คนละวัน — สังเกตจากบรรทัด `recording health: Oct-02 …`)
  · **วิธีที่ถูก: ดึง task id ปัจจุบันก่อนแล้วกรอง**
  ```bash
  T=$(docker service ps <svc> --format '{{.ID}}' | head -1 | cut -c1-10)   # .Name ให้ 'svc.1' ไม่ใช่ id!
  docker service logs <svc> --since 15m 2>&1 | grep "$T" | grep -c 'not found'
  ```
  · ⚠️ **นาฬิกาใน container เป็น UTC แต่โฮสต์เป็น CEST** ⇒ เวลาใน log กับ `date` ต่างกัน 2 ชม.
  อย่าใช้เทียบกันตรง ๆ · ⚠️ `docker service logs --tail N` บนบริการที่มีประวัติยาว **ช้ามาก**
  (เกิน 120 วิ) ให้ใส่ `--since` จำกัดช่วงแทน
- **Correct Pattern/Solution:**
  - ชื่อคิวเป็น **"คู่ที่ต้องตรงกัน"** ⇒ เก็บที่แหล่งเดียว `core/queues.py` แล้วให้ทั้งสองฝั่ง import
    (service **ห้าม import worker** ตาม layering ⇒ วางไว้ `core/` ไม่ใช่ในไฟล์ worker)
  - ตั้ง `queue_name` ที่ `WorkerSettings` **ทั้งสองตัว** + ผู้ส่งต้องระบุ `_queue_name=` ด้วย
    (`enqueue_job("process_student_import", job_id, _queue_name=IMPORT_QUEUE)`)
  - ℹ️ cron **ไม่ต้อง**ระบุคิวเอง — ARQ ยัดเข้าคิวของ worker ตัวนั้นตาม `queue_name` อยู่แล้ว
  - 🧪 **เทสต์ต้องผูกสองฝั่ง ไม่ใช่เทสต์แค่ว่า "ค่าต่างกัน"** — ผ่านเฉพาะเมื่อผู้ส่งยิงเข้าคิวเดียวกับ
    ที่ผู้รับฟัง (`monkeypatch` `create_arq_redis` เป็น fake ที่ดัก `_queue_name`)
    · ใช้ `getattr(WorkerSettings, "queue_name", default_queue_name)` — เพราะ "ไม่มี attribute"
    กับ "มีแต่ค่าเป็น default" **ให้ผลเหมือนกันเป๊ะในรันไทม์** (ARQ ถอยไปใช้ default เงียบ ๆ)
    ⇒ ถ้าเขียน `Settings.queue_name` ตรง ๆ เทสต์จะพังเป็น `AttributeError` ที่อ่านไม่ออก
  - ✅ **พิสูจน์ว่าเทสต์จับบั๊กได้จริง** — `git stash` เฉพาะไฟล์ที่ซ่อม (ไม่ stash เทสต์) แล้วรันซ้ำ
    ต้องเห็น fail 4 ข้อด้วยข้อความ `assert 'arq:queue' != 'arq:queue'` · **เทสต์ที่ผ่านทั้งโค้ดพัง
    และโค้ดดีไม่มีค่า** — อย่าข้ามขั้นนี้
  - 📌 **บทเรียนทั่วไป:** ผู้บริโภคตั้งแต่ 2 ตัวขึ้นไปที่แชร์คิวเดียว = งานถูกทิ้งแบบสุ่ม
    ถ้าเพิ่ม worker ใหม่ **ต้องตั้ง `queue_name` เสมอ** ไม่ใช่ปล่อย default
- **Date Added:** 2026-10-07

### 💀 `arq:queue:<ชื่อ>:health-check` หายหลัง deploy — **ไม่ใช่**สัญญาณว่า worker พังหรือตั้งคิวผิด

- **Context/Problem:** หลัง deploy ตัวซ่อมคิว ARQ ขึ้น staging แล้ว พบว่า
  `arq:queue:import:health-check` **มี** แต่ `arq:queue:push:health-check` **หายไป**
  (`TTL=-2`) ทั้งที่ worker รันปกติ 1/1 และกิน cron `process_push_outbox` ทุก 20 วิ สำเร็จทุกครั้ง
  ⇒ อ่านเผิน ๆ แล้วสรุปได้ว่า "push_worker ไม่ได้ตั้ง `queue_name`" ซึ่ง **ผิด**
- **Root Cause:** ARQ 0.28.0 `arq/worker.py` มีสองบรรทัดที่ประกอบกันเป็นกับดัก:
  - `record_health()` (บรรทัด 775) **early-return** ถ้า `now_ts - self._last_health_check < health_check_interval`
    (default **3600 วิ**) ⇒ worker ใหม่เขียน key **ครั้งเดียวตอนสตาร์ท** แล้วเงียบไปอีก 1 ชม.
    (`self._last_health_check = 0` ตั้งแต่ `__init__` ⇒ ครั้งแรกเขียนแน่นอน)
  - `close()` (บรรทัด 874) `await self.pool.delete(self.health_check_key)` ⇒ **ลบทิ้งตอนปิดอย่างสุภาพ**

  ⇒ ระหว่าง **rolling update** (worker เก่ากับใหม่ทับกันช่วงสั้น ๆ) ถ้า `close()` ของตัวเก่ามากลบ
  **หลัง** การเขียนครั้งเดียวของตัวใหม่ → key หายไป **นานถึง 1 ชั่วโมง** โดย worker ทำงานปกติ 100%
  อธิบายได้ด้วยเหตุนี้ว่าทำไม worker ตัวหนึ่งมี key อีกตัวไม่มี **ทั้งที่เป็นโค้ดเดียวกัน** (แข่งกันที่จังหวะ)
- **หลักฐานที่ยืนยัน:** `docker service scale ..._push_worker=0` → รอ container หมดจริง (ให้ตัวเก่า
  `close()` จบก่อน ไม่มีใครมาลบทับ) → `scale =1` ⇒ **key โผล่ทันที** TTL 3585
  ⇒ ไม่มีอะไรผิดที่คอนฟิก เป็น race ล้วน ๆ
- **Correct Pattern/Solution:**
  - **อย่าใช้ health-check key เป็นหลักฐานหลัก** ว่า worker อยู่คิวไหน มันเป็นเรื่อง *การเฝ้าติดตาม*
    ไม่ใช่ *การตั้งค่า* · อาการ "key หาย" **ไม่มีความหมายเชิงหน้าที่** (worker ยังทำงานครบ)
  - หลักฐานที่เชื่อได้จริง เรียงจากตรงที่สุด:
    1. **อ่านจากคอนเทนเนอร์ที่รันอยู่** (ผู้รับ — ground truth):
       `docker exec <ctr> python -c "from workers.push_worker import WorkerSettings as S; print(S.queue_name)"`
    2. **ผู้ส่ง:** `grep _queue_name /app/services/import_service.py`
    3. **คิว default ต้องไม่มี:** `redis-cli EXISTS arq:queue` → ต้องเป็น `0`
    4. **พิสูจน์เชิงหน้าที่** (แข็งสุด): ยิงงานจริงแล้วเห็นมันจบ — push = cron ทุก 20 วิ,
       import = นำเข้า Excel แล้วได้ `COMPLETED`
  - ℹ️ `docker exec` **ไม่ส่ง stdin** ถ้าไม่ใส่ `-i` ⇒ `docker exec X python - <<'PY'` จะ **เงียบ ไม่มี output
    และไม่มี error** ⇒ ใช้ `docker cp` + `python /tmp/x.py` แต่ต้อง `-e PYTHONPATH=/app` ด้วย
    (ไม่งั้น `ModuleNotFoundError: No module named 'core'`)
  - ⚠️ กับดักการอ่าน log ซ้ำ: ARQ log **สองบรรทัดต่อหนึ่งเหตุการณ์** (formatter ของตัวเอง +
    stdlib) ⇒ `grep -c 'Starting worker'` ได้ **2** ทั้งที่สตาร์ทครั้งเดียว **อย่าอ่านเป็นรีสตาร์ท**
- **Date Added:** 2026-10-07
