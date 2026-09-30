# ⚙️ Backend Rules (FastAPI + asyncpg)

คุณคือ Senior Backend Engineer ที่ดูแลระบบ PIRIvoice (ระบบรับฟังความคิดเห็นและปัญหาสภานักเรียน) กฎเหล่านี้คือมาตรฐานที่ต้องปฏิบัติตามอย่างเคร่งครัด

## 1. Stack & Core Technologies
- **Framework:** FastAPI (Python 3.12+)
- **Database:** `asyncpg` สำหรับ PostgreSQL (**ห้ามใช้ ORM/SQLAlchemy เด็ดขาด**)
- **Validation:** `Pydantic` v2 (ใช้ `model_dump()` แทน `dict()`)
- **Logging:** `AuditLogger` (จาก `core.logger`) สำหรับบันทึกพฤติกรรมผู้ใช้

## 2. โครงสร้างและการแยก Layer (Strict MVC-like)
- **Routers (`backend/routers/`):**
  - หน้าที่: รับ Request, จัดการ Dependency Injection, และจัดการ Exception เป็น `HTTPException`
  - **กฎเหล็ก:** ห้ามมี SQL Query หรือ Business Logic ซับซ้อนใน Router
  - **Identity Extraction:** ดึงผู้ใช้ผ่าน **`user_ctx: dict = Depends(get_current_user)`** แล้วอ่าน
    `user_ctx.get("user_id")` โยนเข้า Service เสมอ (`core/dependencies.py`)
    - **ห้ามรับ user id จาก header/body/query ที่ผู้เรียกส่งมาเอง** — ปลอมเป็นใครก็ได้
      (มีเทสต์คุมไว้แล้วใน `tests/test_home_summary.py`: "ไม่รับ `user_id` จาก client")
    - `get_current_user` รับได้สองทาง: **JWT Bearer** (ปกติ → `{"user_id": int}`) และ
      **`X-API-Key`** (system RPC → `{"user_id": None, "is_system": True}`) · คีย์ผิด = **401**
    - ℹ️ `verify_api_key()` มีอยู่ในไฟล์แต่ **ไม่มีใครใช้** — การตรวจคีย์ถูกทำใน `get_current_user`
      แล้ว ⇒ อย่าเอาไป `Depends` ซ้อน (จะได้ 401 สองชั้นโดยไม่มีประโยชน์)
  - **Audit context ไม่ใช่หน้าที่ของ Router** — middleware `audit_context_middleware` (`main.py`)
    ตั้ง context ต่อ request ไว้แล้ว และ `AuditLogger.log()` เรียก `get_audit_context()` เอง
    ⇒ **ห้าม Router ประกอบ context ส่งลงไป** · แบ่งความรับผิดชอบได้แบบนี้:

    | ฟิลด์ | ใครกำหนด |
    |---|---|
    | `ip_address` · `user_agent` · `trace_id` · `endpoint_or_command` · `execution_time_ms` | **อัตโนมัติ** จาก middleware (หรือ `audit_scope()` ใน worker/script) |
    | `room_id` | อัตโนมัติเป็น fallback — ถ้าไม่ส่งมา จะ lookup ห้องของผู้กระทำให้ |
    | `actor_identifier` · `client_source` | **ผู้เรียกต้องส่งเอง** (required) — เช่น `actor_identifier=str(user_id), client_source="web"` |
    | `action` · `entity_type` · `entity_id` · `old_values` · `new_values` | ผู้เรียกต้องส่งเอง (แก่นของ log) |
- **Services (`backend/services/`):**
  - หน้าที่: บรรจุ Business Logic ทั้งหมด, จัดการ Transaction, และเขียน Raw SQL ที่นี่
  - การเรียกใช้: รับ `pool: asyncpg.Pool` มาจาก Dependency Injection
- **Models (`backend/models/`):**
  - ใช้ Pydantic Models สำหรับ Request และ Response
  - **Date Params:** ตัวแปรรับค่าวันที่ต้องใช้ Type `date` หรือ `datetime` เท่านั้น ห้ามใช้ `str` ป้องกันบั๊ก `toordinal()`
  - ใน Router ต้องบังคับใส่ `response_model=...` ทุกครั้ง เพื่อกรองฟิลด์ลับออกก่อนส่งหา Client
    (ทั้ง repo ใส่ครบ 92/94 endpoint) — **ข้อยกเว้นมีแค่ 2 แบบ** ที่ไม่ใช่ JSON ก้อนเดียว:
    - **ดาวน์โหลดไฟล์** — `GET /api/import-student-template` คืน `Response` ที่มี attachment
    - **SSE stream** — `GET /api/notifications/stream` คืน `StreamingResponse`
    ⇒ เพิ่ม endpoint ที่ไม่ใช่ JSON ให้ **เขียนคอมเมนต์กำกับว่าทำไมไม่มี `response_model`**
    ไม่งั้นจะดูเหมือนลืม (และคนต่อไปจะ "แก้" ให้โดยไม่รู้ว่าพัง)

## 3. Database & SQL Standard (asyncpg Best Practices)
- **Raw SQL Only:** ใช้ Parameterized Query (`$1, $2, ...`) ป้องกัน SQL Injection เสมอ
- **Transaction:** ถ้ามี Mutation ต่อเนื่อง (Insert/Update หลายตาราง) ต้องครอบด้วย `async with conn.transaction():` เสมอ
- **Dynamic Updates (PATCH):** ใช้ `req.model_dump(exclude_unset=True)` เอาเฉพาะฟิลด์ที่ส่งมาไปอัปเดต ป้องกันค่า None ทับของเดิม
- **Row Locking (ป้องกัน Race Condition):** เมื่อมี **อ่าน-แล้ว-เขียน** ที่แข่งกันได้ (นับที่นั่ง,
  ตรวจโควตา, เลื่อนคิว) ต้อง `SELECT ... FOR UPDATE` ภายใน transaction เดียวกันเสมอ
  - ใช้จริงใน `services/issue_service.py` · `event_service.py` · `announcement_service.py` ·
    `import_service.py` · `push_outbox` — **ไม่มี** การเงิน/สต๊อกในระบบนี้
  - ⚠️ รูปแบบที่ถูกคือ `FOR UPDATE` **บวกกับเงื่อนไขสถานะใน `WHERE`** (ดู §4) — ล็อกอย่างเดียว
    ไม่กันสถานะเปลี่ยนไปมาระหว่างสองคำขอ
- **Data Limits:** การดึงข้อมูล List ยาวๆ ต้องทำ Pagination หรือใส่ `LIMIT` ห้ามดึงทั้งตาราง
  - ตัวช่วยกลางคือ `_envelope(conn, *, count_sql, count_params, rows_sql, rows_params, limit, offset)`
    — **`count_params` กับ `rows_params` เป็นคนละลิสต์** และ `LIMIT/OFFSET` ต้องเป็น `$len(rows_params)+1` / `+2`
  - ⚠️ ถ้าฝั่ง `rows_sql` ต้องใช้ `$1` (เช่น `user_id`) ให้บวกเลข placeholder ของฝั่ง count แยกกัน
    — "สองสำเนาของเงื่อนไขเดียวกัน" เลขไม่เท่ากันเป็นเรื่องปกติ

## 4. Deletion & Audit Logging (กฎเหล็ก)
- **Soft Delete = ค่าเริ่มต้น:** ข้อมูลโดเมนที่ผู้ใช้สร้าง (เรื่อง/กระดาน/ความเห็น/กิจกรรม/ผู้ใช้/ประกาศ)
  ใช้ `UPDATE ... SET deleted_at = NOW()` เสมอ และ **ทุก query ที่อ่านต้องมี `deleted_at IS NULL`**
  - ⚠️ ลืมเงื่อนไขนี้ที่ใดที่หนึ่ง = ข้อมูลที่ลบแล้วโผล่กลับมา (เทสต์มักไม่จับ เพราะเส้นทางปกติไม่เห็น)
- **Hard Delete (`DELETE FROM`) อนุญาตเฉพาะแถวที่เป็นของชั่วคราว/junction** ที่ soft delete ไม่มีความหมาย:
  `push_subscriptions` (ปิดรับแจ้งเตือน) · `bookmarks` (กดยกเลิกบุ๊กมาร์ก) · `push_outbox` (ตัดของเก่า) ·
  `issue_countdowns` (ลบเพื่อตั้งใหม่) — ทุกตัวมี `WHERE` แคบและผูกกับเจ้าของ (`... AND user_id = $N`)
  - ⚠️ **ไม่มีฟังก์ชันชื่อ `permanent` ในระบบนี้** — อย่าไปหา และอย่าสร้างขึ้นมาโดยไม่จำเป็น
- **Audit Logs:** ทุก Action ที่เปลี่ยนสถานะข้อมูล (CREATE, UPDATE, DELETE) **ต้อง** เรียก
  `await AuditLogger("<ชื่อ service>").log(conn=conn, action=..., actor_identifier=..., client_source=..., ...)`
  **ภายใน Transaction เดียวกับข้อมูลหลัก** พร้อม `old_values` / `new_values` ให้ครบ
  (รูปแบบจริงดู `services/issue_service.py`)
  - ⚠️ **เขียนนอก transaction = audit หายได้** เมื่อข้อมูลหลัก rollback แต่ log อยู่ต่อ
  - ⚠️ ชื่อ logger คือ **`AuditLogger`** ไม่ใช่ `service_logger`

## 5. Security & Error Handling
- **ตัวตนมาจาก token เท่านั้น** — **ห้ามเชื่อ user id / role / room ที่ Client ส่งมาใน body, query หรือ header**
  - **"God Mode" ที่มีจริง** คือ `require_permission(conn, room_id, user_id, permission)` ใน `core/rbac.py`:
    `SUPER_ADMIN_ID` และ `is_admin` ข้ามการเช็คสิทธิ์ย่อย — แต่ **ตัวตนยังมาจาก JWT เหมือนเดิม**
    ไม่ใช่จากค่าที่ client อ้าง ⇒ admin ไม่สามารถ "สวมรอยเป็นผู้ใช้คนอื่น" ได้
  - ทาง system-to-system คือ `X-API-Key` → `{"user_id": None, "is_system": True}` = **ผู้กระทำที่ไม่ใช่คน**
    (สำหรับ script/automation) ⇒ ไม่ได้ให้สิทธิ์เป็นผู้ใช้คนใดคนหนึ่ง
  - ⚠️ บรรทัดที่เขียนว่า "ส่ง `x_discord_id` มาแล้วเชื่อใจ" **เคยอยู่ในไฟล์นี้และถูกลบแล้ว** —
    มันคือช่องโหว่ถ้าทำตาม (Discord ไม่มีในระบบนี้ตั้งแต่แรก)
- **Error in Service:** raise exception เฉพาะทางจาก `core.exceptions` —
  `NotFoundError` · `ForbiddenError` · `ValidationError` · `ConflictError` · `ServiceUnavailableError`
  - ⚠️ **ไม่มี `StudentNotFoundError`** ในระบบนี้ (ชื่อนั้นมาจากโปรเจคเก่า)
- **Error in Router:** แปลงเป็น `HTTPException` ให้ตรงความหมาย — นี่คือ mapping ที่ใช้จริงทั้ง repo:

  | Domain exception | HTTP |
  |---|---|
  | `NotFoundError` | **404** |
  | `ForbiddenError` | **403** |
  | `ValidationError` | **400** |
  | `ConflictError` | **409** |
  | `ServiceUnavailableError` | **503** |

  - ⚠️ **`ValidationError` ของ service = 400 แต่ของ Pydantic/FastAPI = 422** — คนละตัว อย่าสลับ
    (422 ไม่ต้องเขียน `except` เอง เพราะ FastAPI สร้างให้ และ `api.ts` แปลงเป็นข้อความไทยแล้ว)

## 6. Coding Standards
- **Naming:** ใช้ `snake_case` สำหรับตัวแปร/ฟังก์ชัน, `PascalCase` สำหรับ Classes
- **Type Hinting:** ต้องระบุ Type Hint ให้ครบถ้วนทั้ง Parameter และ Return Type
- **Bangkok Time:** การจัดการเวลาให้ยึดตาม `Asia/Bangkok` (UTC+7) เสมอ