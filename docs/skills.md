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
