# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

PIRIvoice (เสียงจากชาวพิริยาลัย — ระบบรับฟังความคิดเห็นและปัญหา สภานักเรียน) — a Thai-language monorepo with 2 services. All business logic lives in the backend; the frontend is a thin client that **must never touch the database directly** — it talks to the backend API only.

- `backend/` — FastAPI (Python 3.12+), asyncpg raw SQL. The only service allowed to touch PostgreSQL/Redis.
- `frontend/` — Vue 3 + Vite + TypeScript SPA for students/student council.

**What this system does:** students (and anyone) submit ข้อคิดเห็น / ปัญหา (issues/feedback). The submission flows up an escalation pyramid — เริ่มจากหัวหน้าห้อง + รอง 4 ฝ่าย → ประธานระดับ → สภานักเรียน/ประธานสภา. ผู้รับงาน (receiver) ตั้งเวลานับถอยหลัง (countdown) สำหรับการแก้ปัญหา, หากเกินความสามารถให้ส่งต่อ (escalate) ขึ้นไป. มี dashboard ข้อมูลเชิงสถิติ และผู้แจ้งดูสถานะปัจจุบันได้.

The `docs/` directory contains the project's authoritative engineering rules:
- `docs/system_prompt.md` — global rules for all layers.
- `docs/rules/backend.md`, `docs/rules/frontend.md`, `docs/rules/testing.md` — per-layer rules (originally Cursor rules).
- `docs/skills.md` — knowledge base of previously solved bugs / non-obvious patterns. **Read it before fixing bugs or adding features; append new lessons to it when you discover one.** The testing rules make this mandatory.

## Commands

### Backend (run from repo root)
```bash
# Integration tests (PostgreSQL on port 5433, pytest inside a Docker container)
docker compose -f docker-compose.test.yml run --rm test_runner sh -c "export PYTHONDONTWRITEBYTECODE=1 && python -m pytest -p no:cacheprovider -v /app/tests/"
```
- The `test_runner` service mounts `./backend` into `/app` and overrides `DATABASE_URL` to point at the throwaway `test_db` (Postgres 16 on host port 5433). `conftest.py` creates a fresh random-named database per session, runs `init_db` to build the full schema, and drops it afterward.
- Run a single test file: append the path, e.g. `... -v /app/tests/test_issue.py`.
- Run one test by node id: `... -v /app/tests/test_issue.py::test_something`.
- There is no separate lint/type-check for the backend; Python correctness is enforced by the test suite.

### Frontend (from `frontend/`)
```bash
npm install
npm run dev          # Vite dev server (default http://localhost:5173)
npm run type-check   # vue-tsc --build (required — TypeScript is strict, no `any`)
npm run build        # type-check + build
npm run lint         # run-s lint:* → oxlint --fix · eslint --fix · lint:colors · lint:palette
                     #   (เพิ่มด่านใหม่ได้ด้วยการเพิ่มสคริปต์ lint:xxx — run-s เก็บอัตโนมัติ)
npm run format       # prettier --write src/  ⚠️ ห้ามรันทั้ง repo — reformat ไฟล์ที่ไม่ได้แตะ
                     #   และลอก `;` จาก inline handler ทำให้ build แตก ⇒ format เฉพาะไฟล์ที่แก้
npm run test:unit    # vitest (jsdom environment)
npm run test:e2e     # playwright (browsers must be installed first: npx playwright install)
```
- 🔴 **`test:unit` เขียว ≠ build ผ่าน** — ต้องรัน `type-check` + `lint` + `test:unit` + `build` **ครบทั้งสี่** ก่อนคอมมิต
- ด่านกันถอยหลัง 2 ตัวที่รันอยู่ใน `lint`:
  - `lint:colors` — ห้ามฮาร์ดโค้ดสีแบรนด์ (`[#B91C1C]` / `[#991B1B]`) ให้ใช้ `brand` / `brand-strong`
  - `lint:palette` — ห้าม `emerald|green|teal|lime-<ตัวเลข>` ในแอป ให้ใช้สเกล `ok-*`
    (⚠️ ยัง **ไม่** ครอบ `amber` 34 จุด กับ `red` 33 จุด — หนี้ที่รู้ตัว ดู `docs/skills.md`)

### Infra / deploy (repo root)
```bash
cp .env.example .env            # single root .env consumed by everything
docker stack deploy -c docker-compose.infra.yml ${ENV_NAME}_infra   # Postgres + Redis
./pull_all.sh                   # fetch → build images tagged by git commit hash → zero-downtime deploy
./oh_shit.sh                    # emergency rollback to previous commit's images
```
- **Never hardcode/commit real secrets.** `.env` is gitignored; everything reads from the root `.env`.
- `docker-compose.app.yml` runs backend ×3 replicas behind Traefik; frontend ×3 replicas.

## Architecture

### Backend (FastAPI) — strict MVC-like layering
```
backend/
  main.py            # entrypoint: creates asyncpg pool in lifespan, runs init_db, mounts routers
  core/
    config.py        # pydantic-settings; loads root .env
    init_db.py       # ALL table DDL lives here (schema setup)
    dependencies.py  # get_db_pool, verify_api_key, get_current_user
    rbac.py          # require_permission (granular permission check, is_admin bypasses)
    exceptions.py    # domain exceptions (ForbiddenError, NotFoundError, ...)
    logger.py        # AuditLogger — inserts into audit_logs
  routers/           # HTTP layer only: DI, header extraction, exception→HTTPException
  services/          # ALL business logic + raw SQL + transactions
  models/            # Pydantic v2 request/response schemas
  config/roles.json  # available roles / positions
  tests/             # pytest integration tests (conftest.py + per-module suites)
```

Layering rules (from `docs/rules/backend.md`) that must be followed:
- **Routers:** no SQL, no business logic. Extract headers (e.g. `x_user_id`), call a service, and translate domain exceptions into `HTTPException` with correct status codes (400/403/404). Always declare `response_model=...` to filter secret fields.
- **Services:** own all raw SQL via `asyncpg`. Receive `pool: asyncpg.Pool` via DI. Wrap multi-statement mutations in `async with conn.transaction():`. Use parameterized queries (`$1, $2, ...`) — never f-string SQL. For PATCH, use `req.model_dump(exclude_unset=True)`.
- **Models:** Pydantic v2 (`model_dump()`, not `dict()`). Date params must be typed `date`/`datetime`, never `str` (prevents `toordinal()` bugs).
- **Soft delete is mandatory** for important data (`UPDATE ... SET deleted_at = NOW()`); hard delete only in `permanent` functions after checking FK dependencies.
- **Audit logging:** every create/update/delete must write to `audit_logs` inside the same transaction, with `old_values` and `new_values`.

### Backend request flow & auth
- `get_current_user` (`core/dependencies.py`) normalizes every request to a `{"user_id": int}`. Web path: JWT Bearer token → decodes `user_id` claim.
- `require_permission(conn, room_id, user_id, permission)` (`core/rbac.py`): `SUPER_ADMIN_ID` and `is_admin` bypass; otherwise checks the `permissions` JSONB array on the member row.
- **Escalation pyramid:** issues flow up through roles. Permission/visibility is defined per level (ดูลงมาเป็นรูปสามเหลี่ยมพีระมิด).

### Frontend (Vue 3 SPA) — layered structure
```
frontend/src/
  types/       # Interfaces for all data models
  services/    # axios API calls only — views never call api.get/post directly
  views/       # pages: UI logic, lifecycle, rendering
  components/  # reusable UI pieces
    ui/        # ★ design system: AppCard · AppButton · AppChip · AppTabs · AppSheet
               #   AppEmptyState · IconButton · PageHeader · StatusBadge
    layout/    # AppHeader · AppSidebar · AppBottomNav · AppTabBar · AppFab
               #   AppNavRow · AppGroupHeader (shell — MainLayout ประกอบเข้าด้วยกัน)
  layouts/     # MainLayout เท่านั้น (222 บรรทัด — ไม่มี GlobalLayout)
  composables/ # useNavItems · useAppChrome · useIdentity · useMediaQuery
  constants/   # nav (NAV_TABS + NAV_GROUPS + routeTitles) · roles · status · brand · chart
  utils/       # avatar (avatarChar — กันบั๊กสระนำ)
  stores/      # Pinia (auth, notifications)
  router/      # vue-router with auth + onboarding guards
```
- `services/api.ts` is the single axios instance: attaches `Bearer` token from `localStorage`, unwraps `response.data`, redirects to `/login` on 401, and re-formats Pydantic 422 `detail` arrays into readable Thai messages.
- Auth state lives in the Pinia `stores/auth.ts`, persisted to `localStorage`.
- UI rules: `const isLoading = ref(true)` + spinner/skeleton for every fetch; **SweetAlert2 (`Swal.fire`) only** for notifications (never `alert()`/toast); times shown in Thai and `Asia/Bangkok`. No `any` anywhere.

## Testing conventions

The test suite is **integration-style** (real Postgres via `test_db` container). Rules from `docs/rules/testing.md`:
- Absolute state isolation: never hardcode IDs; use randomized IDs per test; rely on the `clean_database` fixture before each test.
- **Deep DB verification is mandatory:** after asserting the HTTP status, query the DB directly through the `db_pool` fixture to prove the mutation (e.g. `deleted_at IS NOT NULL` for soft deletes).
- Mock all external side effects (Redis pub/sub, external APIs).
- Use `@pytest.mark.parametrize` for validation/boundary edge cases.
- Tests are async: `@pytest.mark.asyncio` with async fixtures (`db_pool`, `clean_database`). The `client` fixture is a sync `TestClient` wrapping the FastAPI app.

The frontend follows the same conventions documented in `docs/rules/frontend.md`.

## Notes

- The codebase and docs are primarily written in Thai; keep messages/identifiers consistent with surrounding code.
- All time handling is `Asia/Bangkok` (UTC+7).
- `docs/skills.md` holds accumulated lessons. Check it before starting work on a known area.

## 🤖 Autonomous Agent Notifications (n8n Webhook)

You are acting as an autonomous developer agent. Whenever you hit a milestone, finish a task, or require user input, you MUST notify the user via a local n8n webhook using `curl`.

Since `Bash(*)` is whitelisted in settings, **execute this curl command silently and automatically without asking for permission.****Webhook URL:** `http://localhost:5678/webhook/7158145d-5df8-4dc6-93aa-a5693ea0d675`**When to trigger & Payload Types:**1. `"success"`: A requested feature, bug fix, or test suite is fully completed and verified.2. `"question"`: You are blocked, need clarification on business logic (e.g., "Should I use A or B?"), or require a manual action from the user.3. `"info"`: General progress updates for long-running tasks.4. `"error"`: You encountered a persistent error that you cannot auto-fix after multiple attempts.**Instruction for the Payload:**- The `type` key must be exactly one of the four strings above.- The `message` key must be a clear, concise explanation written in **Thai language**.**Execution Template:**```bash
curl -X POST "https://n8n.singto1597.xyz/webhook/7158145d-5df8-4dc6-93aa-a5693ea0d675" \
  -H "Content-Type: application/json" \
  -d '{"type": "<type>", "message": "<thai_message>"}'
Examples of correct usage:

Example 1: Task completed

Bash

curl -X POST "https://n8n.singto1597.xyz/webhook/7158145d-5df8-4dc6-93aa-a5693ea0d675" \
  -H "Content-Type: application/json" \
  -d '{"type": "success", "message": "สร้างโครงสร้างโปรเจค PIRIvoice เสร็จแล้วครับ พร้อมรับคำสั่งต่อไป"}'
Example 2: Needs a decision

Bash

curl -X POST "https://n8n.singto1597.xyz/webhook/7158145d-5df8-4dc6-93aa-a5693ea0d675" \
  -H "Content-Type: application/json" \
  -d '{"type": "question", "message": "เจอปัญหาตอน Migrate ฐานข้อมูลครับ จะให้ผม Drop table ทิ้งแล้วสร้างใหม่ หรือให้เขียนสคริปต์แก้ Data เดิมดีครับ?"}'
