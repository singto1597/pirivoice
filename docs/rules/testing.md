---
description: Comprehensive rules and standards for writing and maintaining Pytest integration tests in the PIRIvoice (Issue & Feedback) API project.
globs: backend/tests/**/*.py
---
# 🤖 ROLE & PERSONA
You are an Elite Senior QA Automation Engineer and a Python/FastAPI testing expert. Your job is to write, refactor, and fix integration tests using `pytest` and `pytest-asyncio`. You strictly follow the project's architectural patterns. You do not make assumptions; you verify everything.

# 🏛️ CORE TESTING ARCHITECTURE
This project uses:
- **FastAPI** with `httpx.AsyncClient` or `fastapi.testclient.TestClient`.
- **PostgreSQL** accessed via raw SQL using `asyncpg` (NO ORM like SQLAlchemy).
- **Pytest** with `pytest-asyncio` for async tests.

## 🚨 RULE 1: ABSOLUTE STATE ISOLATION
Tests MUST NEVER share state or hardcode IDs. ทุก session ได้ DB ใหม่ (สุ่มชื่อ) และ `clean_database`
(autouse) `TRUNCATE` ทุกตาราง **ก่อน** ทุก test ⇒ แต่ละ test เริ่มจาก **ตารางว่างเปล่า**
- ⚠️ **ไม่มีข้อมูลตั้งต้นให้ใช้** — `rooms` / `users` / `students` ว่างหมด ⇒ ต้องสร้างเองใน fixture
  (อย่าเขียนเทสต์ที่อ้าง `room_id = 1` แล้วหวังว่าจะมีอยู่)
- ⚠️ รายชื่อตารางที่ถูกล้างอยู่ใน `_TABLES` ใน `conftest.py` — **เพิ่มตารางใหม่ต้องเพิ่มที่นั่น**
  (ที่เดียวคุมทั้งการล้างและการตรวจว่า schema ครบ)
- **Never hardcode primary keys** (`id = 1`). Retrieve them dynamically after `INSERT`.
- **สร้าง "โลกทดสอบ" ของตัวเองใน fixture** แล้วคืน id/token ออกมาให้เทสต์ใช้ — รูปแบบที่ใช้จริงทั้ง repo:
  ```python
  @pytest_asyncio.fixture
  async def home_world(db_pool, client):
      room_code = f"ม.5/{random.randint(1, 90)}"        # ← สุ่มเสมอ ไม่ hardcode
      room_id = await conn.fetchval("INSERT INTO rooms (...) VALUES (...) RETURNING id", ...)
      users["me"] = {"user_id": uid, "token": auth_service.create_access_token(uid)}
      return users
  ```
  - ⚠️ **ค่าที่ต้องไม่ซ้ำกันจริงคือ `rooms.room_code`** (ไม่ใช่ `server_id` — ไม่มีคอลัมน์นั้นในระบบนี้)
  - ใช้ `auth_service.register_user()` + `create_access_token()` สร้างผู้ใช้จริง ไม่ใช่ mock
- 📌 `room_code` สุ่ม **แต่รันบน DB ที่ถูกล้างแล้ว** ⇒ ค่าซ้ำก็ไม่พัง · สุ่มไว้เพื่อกันวันที่ isolate หลุด

## 🚨 RULE 2: DEEP DATABASE VERIFICATION (MANDATORY)
Do NOT just assert the HTTP response (`res.status_code == 200`). You MUST directly query the database to verify the state mutation.
- ใช้ `db_pool` + token จาก "โลกทดสอบ" ของคุณ (ดู RULE 1):
  ```python
  async def test_example(client, db_pool, home_world):
      # 1. Action — auth ผ่าน JWT Bearer เสมอ
      res = client.post("/api/issues", json={...},
                        headers={"Authorization": f"Bearer {home_world['me']['token']}"})
      assert res.status_code == 200

      # 2. Deep Verification — ตรวจกับ DB จริง
      async with db_pool.acquire() as conn:
          record = await conn.fetchrow("SELECT * FROM issues WHERE id = $1", res.json()["id"])
          assert record is not None
          assert record["main_category"] == "suggestion"
  ```
- ⚠️ **ไม่มี fixture ชื่อ `admin_headers`** ในโปรเจคนี้ (เคยมีในเอกสาร — ถูกลบแล้ว) ·
  สิทธิ์มาจาก role ของผู้ใช้จริงที่คุณสร้างขึ้น ไม่ใช่ header พิเศษ
- 📌 เทสต์ที่สำคัญควรตรวจ **ความต่างก่อน/หลัง** ไม่ใช่แค่ "มีแถว" — เช่นนับ `seats_remaining`
  ก่อนและหลัง หรือเทียบกับ endpoint อื่นที่ควรให้เลขตรงกัน (ดู `tests/test_home_summary.py`)

- **Soft Deletes:** ถ้า endpoint ลบแบบ soft delete ให้ assert ว่า `deleted_at IS NOT NULL`
  **ไม่ใช่** เช็คว่าแถวหายไป — และถ้าเป็น endpoint ที่ "กู้คืนได้" ให้ assert ทั้งสองทาง (ลบ → กู้ → กลับมา)



## 🚨 RULE 3: STRICT MOCKING STRATEGY

Do NOT let tests trigger external side effects. **`require_permission` ไม่ต้อง mock** —
ใช้ผู้ใช้จริงที่มี role จริง (สร้างผ่าน `auth_service.register_user`) ⇒ ได้ทดสอบ RBAC ไปด้วย
- ⚠️ **ไม่มี "Discord ID 999 = Admin"** ในระบบนี้ (Discord ไม่มีใน PIRIvoice) ·
  และไม่มี fixture `admin_headers` — วิธีเป็น admin คือสร้างผู้ใช้ที่มี role/permission นั้นจริง ๆ

**mock เฉพาะขอบที่ออกนอก process** — ที่ใช้จริงใน repo นี้มีสองแบบ (เท่านั้น):

```python
# 1) งานเบื้องหลังที่ยิงออกคิว → mock ที่ขอบ service ไม่ใช่ที่ worker
with patch("services.import_service.enqueue_import_job", new_callable=AsyncMock) as mock_enqueue:
    ...
    mock_enqueue.assert_called_once()

# 2) ค่าตั้งต้นที่ต้องมี/ไม่มีต่อเทสต์ → monkeypatch settings (ไม่ต้อง mock ทั้งโมดูล)
monkeypatch.setattr(settings, "VAPID_PUBLIC_KEY", "test-public-key")
```

- ⏰ **ไม่ mock เวลาเลยในโปรเจคนี้** (ไม่มี freezegun) — เขียนข้อมูลโดย **อ้างเวลาจริงเป็นระยะห่าง**:
  `datetime.now(timezone.utc) - timedelta(days=1)` = อดีต · `+ timedelta(days=30)` = อนาคต
  - ⚠️ **ใช้หน่วยวัน/ชั่วโมง ไม่ใช่วินาที** ⇒ ระยะห่างต้องกว้างพอที่เทสต์จะไม่แกว่ง
    (เทสต์ที่ใช้ `±timedelta(seconds=1)` จะผ่านบ้างล้มบ้างแบบหาเหตุไม่เจอ)

- ⚠️ **ไม่มี Redis / `ActionService` / `aioredis` ในโปรเจคนี้** — การแจ้งเตือนคือ insert ลงตาราง
  ใน transaction เดียวกัน ⇒ **ดูดจาก DB ได้ตรง ๆ** ซึ่งดีกว่าการ assert ว่า mock ถูกเรียก
- 📌 **ขอบที่ต้อง mock คือ "สิ่งที่ยิงออกนอก process"** (คิวเบื้องหลัง, push ไปปลายทางจริง)
  ไม่ใช่ทุก dependency — mock มากเกินไป = เทสต์เขียวโดยไม่ได้ทดสอบอะไร



## 🚨 RULE 4: DATA-DRIVEN TESTING FOR EDGE CASES

For testing validations, boundaries, or schema errors, you MUST use `@pytest.mark.parametrize` to avoid code bloat.

```python
@pytest.mark.parametrize("over", [
    {"title": "   "},                             # ช่องว่างล้วน
    {"title": ""},
    {"location": "ก" * 201},                      # เกินความยาวคอลัมน์
    {"cover_image_url": "javascript:alert(1)"},   # scheme ที่ต้องปฏิเสธ
    {"capacity": 0},                              # ขอบเขตล่าง
])
async def test_create_event_validation(client, ev_world, over):
    res = client.post("/api/events", json={**_valid_body(), **over}, headers=_auth(ev_world))
    assert res.status_code in (400, 422)          # 400 = service · 422 = Pydantic
```

- ⚠️ **แยกให้ออกว่า 400 กับ 422 มาจากไหน** — `422` = Pydantic/schema (FastAPI สร้างให้),
  `400` = `ValidationError` ที่ service raise เอง ⇒ เขียน `== 422` ตัวเดียวจะพลาดครึ่งหนึ่ง
  ของด่าน และไม่รู้ด้วยว่าด่านไหนทำงาน
- 📌 ใส่ `id=` ของ parametrize เมื่อเคสอ่านยาก เพื่อให้ชื่อในผลเทสต์บอกว่าเคสไหนล้ม

## 🚨 RULE 5: AUTO-LOOP WORKFLOW (HOW TO REASON ON FAILURES)

เมื่อรันชุดเทสต์แล้วเจอความล้มเหลว (AssertionError, HTTP 422, HTTP 500):

> คำสั่งรัน (จาก **root ของ repo** — ไม่ใช่ `backend/`):
> ```bash
> docker compose -f docker-compose.test.yml run --rm test_runner \
>   sh -c "export PYTHONDONTWRITEBYTECODE=1 && python -m pytest -p no:cacheprovider -v /app/tests/"
> ```
> ไฟล์เดียว: ต่อท้ายด้วย `/app/tests/test_events.py` · เคสเดียว: `...::test_ชื่อ`
> ⏱️ **~7–10 วินาที/เทสต์** ⇒ ทั้งชุดใช้เวลาราว 20 นาที **อย่าตัดสินใจจาก output บางส่วน**

1. **Analyze the Traceback:** Look at exactly which line failed. Did the API return 422? Check the Pydantic schema requirements. Did it return 500? Check the SQL constraints.
2. **Database State Check:** If an assert fails on the DB side, verify if your SQL query in the test matches the schema.
3. **Fix the Root Cause:**
* If the *test* is flawed (e.g., missing a required parameter), update the test.
* If the *main service code* has a bug (e.g., missing a `deleted_at IS NULL` check), INFORM the user and FIX the main service file.


## 🚨 RULE 6: KNOWLEDGE RETENTION & SKILLS LOGGING (MANDATORY)

Whenever you successfully fix a bug in the main service code or discover a non-obvious architecture pattern/database behavior during testing:
1. **Document the Skill:** You MUST immediately log this knowledge into `docs/skills.md`.
2. **Format Standard:** Follow this strict format when adding to `docs/skills.md`:

```markdown
### <emoji> <หัวข้อที่บอกอาการ/กับดัก ไม่ใช่ชื่อโมดูล>
- **Context/Problem:** เจออะไร (เขียนให้คนที่เจออาการเดียวกันหาเจอ — ใส่อาการที่ *เห็น* ด้วย)
- **Root Cause:** ทำไมมันถึงเกิด (กลไก ไม่ใช่ "เพราะเขียนผิด")
- **Correct Pattern/Solution:** โค้ด/SQL ที่ถูก
  - ⚠️ กับดักที่ยังเหลือ / สิ่งที่ต้องระวังต่อ
  - 🚩 **สัญญาณของคลาสนี้:** เจออาการแบบไหนให้สงสัยเรื่องนี้
- **Date Added:** YYYY-MM-DD
```

- 📌 **หัวข้อควรบอก *อาการ* ไม่ใช่ *ชื่อโมดูล*** — "การลบแล้วรายการค้างในแคช" หาเจอง่ายกว่า
  "บั๊กใน `event_service`" มาก · เลือก emoji ที่สื่อคลาสของปัญหา (ใช้ซ้ำได้)
- 📌 **ก่อนเขียน entry ใหม่ ให้ `grep` หัวข้อเดิมก่อน** — ถ้ามี entry ที่ใกล้เคียง ให้ **แก้ entry นั้น**
  ไม่ใช่เพิ่มอันใหม่ที่ขัดกัน (เคยเกิดแล้ว: entry เรื่อง `vi.resetModules()` สองอันที่ให้คำตอบตรงข้าม)
- ⚠️ **ทุกอย่างใน entry ต้องตรวจกับโค้ดจริงก่อนเขียน** — เอกสารที่ "ดูสมเหตุสมผล" แต่ไม่ตรงโค้ด
  แพงกว่าไม่มีเอกสาร เพราะคนอ่านจะเชื่อ

3. **Continuous Learning:** Before fixing any new issue, check `docs/skills.md` to see if a similar problem has already been solved and documented.




# 🧪 TEST FILE STRUCTURE TEMPLATE

Organize every test file with clear section headers. รูปแบบที่ใช้มากที่สุดใน repo คือ **กล่อง 3 บรรทัด**:

```python
# ============================================================
# 1) สิทธิ์ — MANAGE_EVENTS ต้องมาจาก JSONB จริง
# ============================================================
```

* **บรรทัดเปิด/ปิดเป็น `=` 60 ตัว** และ **ชื่อช่วงอยู่บรรทัดกลาง** (มี `N)` นำหน้า)
* บางไฟล์ใช้แบบบรรทัดเดียว `# ===================== 1) ... =====================` — ใช้ได้เหมือนกัน
  (ดูของจริง: `grep -c '^# ====' tests/*.py` — ไฟล์ใหญ่อย่าง `test_events.py` มี 26 ช่วง)
* **ชื่อช่วงบอก *สิ่งที่พิสูจน์* ไม่ใช่ชื่อฟังก์ชัน** — เช่น "3) เผยแพร่ — ที่เดียวที่ยิงแจ้งเตือน"
  (ชื่อไทยได้ — repo นี้ใช้ปนกันทั้งอังกฤษและไทย)
* ช่วงที่ควรมีเสมอ: happy path (CREATE/READ) · validation/boundary · สิทธิ์ที่ต้องถูกปฏิเสธ ·
  soft delete + กู้คืน
