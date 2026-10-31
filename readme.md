# 🏫 PIRIvoice — ระบบรับฟังความคิดเห็นและปัญหา (เสียงจากชาวพิริยาลัย)

> **PIRIvoice** (Pirivoice / เสียงจากชาวพิริยาลัย) — ระบบรับฟังความคิดเห็นและปัญหาสภานักเรียน พิริยาลัย (เดิมชื่อ PRSC Portal)

ระบบรับฟังความคิดเห็น/ปัญหา (Issue & Feedback Portal) ที่นักเรียนแจ้งเรื่องเข้ามา แล้วไต่ระดับการแก้ไขเป็นขั้นตามสายงาน (Escalation Pyramid):
**หัวหน้าห้อง + รอง 4 ฝ่าย → ประธานระดับ → สภานักเรียน/ประธานสภา**

ออกแบบด้วยสถาปัตยกรรม **Microservices & Monorepo** รองรับการ Deploy ด้วย Docker Swarm และ Traefik

เวอร์ชันปัจจุบันดูที่ [`VERSION`](VERSION) · ประวัติทุกเวอร์ชันอยู่ที่ [`CHANGELOG.md`](CHANGELOG.md)
(รูปแบบ [SemVer](https://semver.org/lang/th/) — ปล่อยงานด้วย `./release.sh X.Y.Z`)

## 📂 โครงสร้างโปรเจกต์ (Monorepo Architecture)

- `backend/` : FastAPI (Python 3.12+ / asyncpg) - จัดการ Database, Business Logic และ API กลาง
- `frontend/` : Vue.js + Vite + TypeScript - หน้าเว็บสำหรับนักเรียนและสภานักเรียน
- `docs/`    : กฎ engineering rules + Scope ของโปรเจกต์
- `setup.sh` : **สคริปต์เริ่มต้นระบบปุ่มเดียวจบ** — สร้าง Swarm + Networks + ตรวจ Traefik + DB + Deploy แอป
- `setup_traefik.sh` : ติดตั้ง **Traefik Proxy ตัวกลาง (ครั้งเดียวต่อเครื่อง — 1 เครื่อง 1 อัน)**
- `docker-compose.infra.yml` : ไฟล์รันฐานข้อมูล (PostgreSQL & Redis)
- `docker-compose.proxy.yml` : ไฟล์รัน Traefik Reverse Proxy (ติดตั้งครั้งเดียวต่อเครื่อง)
- `docker-compose.app.yml` : ไฟล์รันตัวแอปพลิเคชัน (Backend, Frontend, Worker)

## 🏗️ สถาปัตยกรรมเซิร์ฟเวอร์ (Infrastructure)

ระบบนี้ใช้ **Docker Swarm** ในการทำ Cluster และใช้ **Traefik** เป็น Reverse Proxy / Load Balancer ทำให้เราสามารถ:
1. แยกระบบ `Staging` และ `Production` ออกจากกันอย่างเด็ดขาดบนเซิร์ฟเวอร์เดียว
2. อัปเดตโค้ดแบบ **Zero Downtime** (เว็บไม่ล่มระหว่างรอโหลดคอนเทนเนอร์ใหม่)
3. รัน API และ Web ซ้อนกันหลาย Replicas เพื่อรองรับโหลดที่มากขึ้น

---

## 🚀 วิธีติดตั้งและใช้งาน (Getting Started)

### 1. โคลนโปรเจกต์
```bash
git clone <repo-url> pirivoice
cd pirivoice
```

### 2. ตั้งค่า Environment Variables

คัดลอกไฟล์ `.env.example` มาสร้างเป็นไฟล์ `.env` ที่โฟลเดอร์นอกสุดของโปรเจกต์ (Root Directory) **เพียงไฟล์เดียวเท่านั้น**:

```bash
cp .env.example .env
nano .env
```

*(ระบบทั้งหมดจะดึงค่าคอนฟิกจากไฟล์ตัวแม่ไฟล์นี้โดยอัตโนมัติ)*

ค่าสำคัญที่ต้องแก้:

| ตัวแปร | ความหมาย | ตัวอย่าง |
|---|---|---|
| `ENV_NAME` | ชื่อ environment — ใช้ตั้งชื่อ network / stack / volume / image ทั้งหมด | `staging`, `production` |
| `API_DOMAIN` | domain ของ API (Traefik route ไป backend) | `api.pirivoice.com` |
| `WEB_DOMAIN` | domain ของเว็บ (Traefik route ไป frontend) | `app.pirivoice.com` |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | ชื่อผู้ใช้ / รหัส / ชื่อฐานข้อมูล | `piri` / ... / `piri_db` |
| `VITE_API_BASE_URL` | URL ที่หน้าเว็บใช้เรียก API (ต้องตรงกับ `API_DOMAIN` + โปรโตคอล) | `https://api.pirivoice.com` |

> 💡 เปลี่ยนชื่อ environment (เช่น อยากได้ `production` เพิ่ม) แค่แก้ **`ENV_NAME` ตัวเดียว** แล้วรัน `./setup.sh` ใหม่ — สคริปต์จัดการสร้าง network/stack/volume/image ชุดใหม่ให้เองทั้งหมด (ทุก environment แชร์ Traefik ตัวกลางตัวเดียวกัน)

### 3. ติดตั้ง Traefik Proxy (ครั้งเดียวต่อเครื่อง)

ระบบนี้ใช้ **Traefik เป็น reverse proxy ตัวกลาง — 1 เครื่อง 1 อัน** ติดตั้งครั้งเดียวต่อเครื่อง แล้วรันระบบนี้กี่ตัว / กี่ environment หรือโปรเจคอื่นๆ ก็แชร์ตัวเดียวกันได้:

```bash
chmod +x setup_traefik.sh
./setup_traefik.sh
```

*(เครื่องไหนติดตั้ง Traefik ไว้แล้ว / มีระบบอื่นรันอยู่แล้ว ข้ามขั้นนี้ได้เลย)*

### 4. รันระบบ — ปุ่มเดียวจบ (คำสั่งเดียวทุกอย่าง)

รันสคริปต์ **`setup.sh`** — มันเตรียมทุกอย่างให้ครบ แล้วปล่อย services ให้คุยกันได้ทันที (ถ้าเครื่องยังไม่มี Traefik สคริปต์จะเตือนให้ติดตั้งก่อน):

```bash
chmod +x setup.sh
./setup.sh
```

**`setup.sh` ทำอะไรบ้าง (อัตโนมัติ):**

| ขั้น | สิ่งที่ทำ | ชื่อ (สร้างจาก `.env`) |
|---|---|---|
| 1 | เปิด Docker Swarm (ถ้ายังไม่เคยเปิด) | — |
| 2 | สร้าง Docker Networks | `app-internal-${ENV_NAME}`, `traefik-public`, `db-management` |
| 3 | ตรวจ **Traefik** Proxy (ติดตั้งครั้งเดียวต่อเครื่อง) | ใช้ตัวกลางที่เครื่องมีอยู่ |
| 4 | Deploy **Infrastructure** (PostgreSQL + Redis) | stack `${ENV_NAME}_infra` |
| 5 | Build Docker Image (tag = commit) + Deploy **แอป** | stack `${ENV_NAME}_app` (backend ×3 / frontend ×3 / worker ×1) |

เมื่อจบ backend / frontend / worker จะเข้าถึง Postgres & Redis ผ่าน network ภายใน `app-internal-${ENV_NAME}` ทันที และเว็บ / API เข้าถึงจากภายนอกผ่าน Traefik ตัวกลางที่พอร์ต 80 (ตาม `WEB_DOMAIN` / `API_DOMAIN`)

**ตัวเลือกเพิ่มเติม:**
```bash
./setup.sh --no-build   # ข้าม build ใช้ image ที่มีอยู่ (เร็วขึ้น ตอน rerun)
./setup.sh --help       # ดูวิธีใช้
```

> **ครั้งถัดไป:** อัปเดตโค้ดใหม่ให้ใช้ `./pull_all.sh` (ดึงโค้ด → build → deploy แบบ Zero Downtime) — `setup.sh` ใช้ตอนตั้งค่าระบบ/เปลี่ยน environment

### 5. อยากรันทีละขั้นเอง? (ไม่ใช้ setup.sh)

ถ้าอยากคุมทีละคำสั่งเอง ตามนี้ (สมมติว่าติดตั้ง Traefik ตัวกลางแล้ว — หัวข้อ 3):

```bash
# 5.1 เปิดโหมด Swarm + สร้าง network ที่ต้องใช้
docker swarm init
docker network create --driver=overlay app-internal-${ENV_NAME}
docker network create --driver=overlay traefik-public
docker network create --driver=overlay db-management

# 5.2 รัน Infrastructure (ฐานข้อมูล)
# โหลดตัวแปรสภาพแวดล้อมชั่วคราว (หรือ export จาก .env ด้วยมือ)
set -a; . ./.env; set +a
docker stack deploy -c docker-compose.infra.yml ${ENV_NAME}_infra

# 5.3 Deploy แอปพลิเคชัน (build + deploy)
./pull_all.sh
```

---

## 🛡️ Traefik Reverse Proxy

ระบบใช้ **Traefik** เป็น reverse proxy / load balancer **ตัวกลาง 1 เครื่อง 1 อัน** — ติดตั้งครั้งเดียวต่อเครื่อง แล้วทุกระบบ (รันระบบนี้กี่ environment ก็ได้ หรือโปรเจคอื่นๆ) แชร์ตัวเดียวกันผ่าน network `traefik-public` ฟังพอร์ต 80 (และ 443 ถ้าเปิด HTTPS) แล้ว route ทราฟฟิกไปยัง services ใน Swarm ที่ติด label `traefik.enable=true`

### ติดตั้งครั้งเดียวต่อเครื่อง

```bash
chmod +x setup_traefik.sh
./setup_traefik.sh              # เปิด Swarm + สร้าง traefik-public + deploy เป็น stack global_proxy
./setup_traefik.sh --remove     # ถอด Traefik ออกจากเครื่อง (ถ้าต้องการ)
```

- **ไฟล์ config:** `docker-compose.proxy.yml` — แก้แล้วรัน `./setup_traefik.sh` ใหม่เพื่อ apply
- ระบบอื่น / environment อื่น จะใช้ Traefik ตัวนี้ได้เลย เพียงแค่ต่อ network `traefik-public` + ติด label `traefik.enable=true` (setup.sh ของโปรเจคนี้ทำให้อัตโนมัติ)

### เส้นทาง (Routing)

- **Backend** → `Host(${API_DOMAIN})` → พอร์ต 8000
- **Frontend** → `Host(${WEB_DOMAIN})` → พอร์ต 80
- ต้องให้ DNS ของ `API_DOMAIN` / `WEB_DOMAIN` ชี้มาที่ IP ของเซิร์ฟเวอร์ จึงจะเข้าเว็บ/API จากภายนอกได้

### 🔐 เปิด HTTPS (Let's Encrypt)

ค่าเริ่มต้น Traefik รันแบบ HTTP (พอร์ต 80) เพื่อให้ติดตั้งได้ทันที ถ้าต้องการ HTTPS ให้ทำตามนี้:

1. ตั้ง DNS ของ `API_DOMAIN` / `WEB_DOMAIN` ชี้มาที่เซิร์ฟเวอร์ (ต้อง reachable จากอินเทอร์เน็ต)
2. ตั้ง `ACME_EMAIL` ใน `.env` (อีเมลรับแจ้งเตือน certificate)
3. แก้ `docker-compose.proxy.yml` — ยกเลิก comment บล็อก HTTPS (เปิด `entrypoints.websecure`, certificates resolver Let's Encrypt) และเปิดพอร์ต `443:443`
4. รัน `./setup_traefik.sh` ใหม่ เพื่อ apply config ใหม่ให้ Traefik
5. แก้ `VITE_API_BASE_URL` ใน `.env` ให้เป็น `https://api.<domain>` แล้วรัน `./setup.sh` ใหม่ (rebuild frontend ให้ชี้ https)

> 💡 ถ้าโดเมนอยู่หลัง Cloudflare (เปิด proxy) ให้ใช้ DNS-01 challenge แทน HTTP-01 — มีตัวอย่าง comment ไว้ในไฟล์แล้ว

---

## 🚨 การกู้ภัยฉุกเฉิน (Rollback)

### วิธีที่ 1: สลับคอนเทนเนอร์ทันที (Hot Rollback - ไวที่สุด)
```bash
docker service rollback staging_app_backend
# หรือ
docker service rollback staging_app_frontend
```

### วิธีที่ 2: ถอยหลังเต็มรูปแบบ (Full Rollback Script)
```bash
chmod +x oh_shit.sh
./oh_shit.sh
```

---

## 🧪 การเทส

### คำสั่งที่ใช้ในการเทส
```
docker compose -f docker-compose.test.yml run --rm test_runner sh -c "export PYTHONDONTWRITEBYTECODE=1 && python -m pytest -p no:cacheprovider -v /app/tests/"
```

---

## 🧪 การรันเพื่อพัฒนา (Local Dev)

```bash
# 1. เตรียม environment
cp .env.example .env   # แล้วแก้ DATABASE_URL, JWT_SECRET, API_KEY, SUPER_ADMIN_ID

# 2. รัน Postgres (Docker)
docker run -d --name piri_dev_db -e POSTGRES_USER=piri -e POSTGRES_PASSWORD=piri_dev_pw -e POSTGRES_DB=piri_dev -p 5434:5432 postgres:16-alpine

# 3. Backend
cd backend
./venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload

# 4. Seed ข้อมูลตัวอย่าง (สำหรับนำเสนอ)
cd backend
DATABASE_URL=postgresql://piri:piri_dev_pw@localhost:5434/piri_dev ./venv/bin/python -m scripts.seed_data

# 5. Frontend
cd frontend
npm run dev
```

## 🔑 บัญชีตัวอย่าง (รหัสผ่าน: 1234 ทุกบัญชี)

| บัญชี | ตำแหน่ง | เห็นอะไร |
|---|---|---|
| `41001` | หัวหน้าห้อง ม.4/1 | เรื่องระดับห้อง |
| `41002` | รองวิชาการ | เรื่องระดับห้อง |
| `99401` | ประธานระดับ ม.4 | เรื่องระดับ (escalate มา) |
| `99001` | ประธานสภา (Admin) | ทุกเรื่อง + Dashboard |
| `41006` | นักเรียน ม.4/1 | เรื่องของตัวเอง |

---

## 👥 บัญชีผู้ดูแลระบบอัตโนมัติ (สร้างตอนเปิดระบบครั้งแรก)

เมื่อ **backend สตาร์ทครั้งแรก** ระบบจะสร้างบัญชีผู้ดูแลระบบให้อัตโนมัติ 3 บัญชี:
**แอดมิน** (`admin`), **ครูสภา** (`teacher_council`), **ประธานสภา** (`council_president`)

- Username เป็นแบบสุ่มที่เดายาก (เช่น `piri_admin_9f2k3c`) — นักเรียนเดาไม่ออก
- รหัสผ่านชั่วคราวสุ่ม 12 ตัว — **ระบบบังคับให้เปลี่ยนรหัสเมื่อ login ครั้งแรก**
- สร้างเฉพาะเมื่อยังไม่มีผู้ใช้ตำแหน่งเหล่านี้ในระบบ (idempotent — restart ซ้ำไม่สร้างเพิ่ม)

### 🔑 วิธีดู username / รหัสผ่านชั่วคราว

**วิธีที่ 1 — ดูจาก log ของ backend (แนะนำใน Docker Swarm):**
```bash
# ตัวอย่าง stack ชื่อ staging_app → เปลี่ยนตาม ENV_NAME
docker service logs staging_app_backend | grep "username"
# หรือดูข้อความสรุปทั้งบล็อก
docker service logs staging_app_backend | grep -A2 "สร้างบัญชีผู้ดูแลระบบ"
```

**วิธีที่ 2 — อ่านจากไฟล์ที่ระบบเขียนไว้ให้:**
```bash
# ระบบเขียนไฟล์ไว้ที่โฟลเดอร์ที่รัน backend
cat default_admin_credentials.txt
```
- ใน dev = โฟลเดอร์ที่รัน `uvicorn`; ใน Docker = โฟลเดอร์ทำงานของ container
- กำหนด path เองได้ผ่าน `SEED_CREDENTIALS_FILE` ใน `.env` (ไฟล์นี้ถูก gitignore แล้ว)

**การใช้งานครั้งแรก:** login ด้วย username + รหัสชั่วคราว → ระบบบังคับเปลี่ยนรหัสผ่านก่อนใช้งาน
→ หลังเปลี่ยนครบแล้วควรลบไฟล์ credentials ทิ้ง

> ⚠️ ถ้าลบ admin/ครูสภาออกจากระบบ แล้ว restart backend → ระบบจะสร้างบัญชีใหม่พร้อม credentials ใหม่

---

## 🧹 การรีเซ็ตระบบ (ล้างข้อมูล เริ่มต้นใหม่)

ล้างฐานข้อมูลทั้งหมด (นักเรียน / เรื่อง / ประวัติ) แล้วให้ระบบสร้าง schema + บัญชี admin ใหม่

```bash
# 0. โหลด environment (ตามชื่อ ENV_NAME ใน .env เช่น staging / production)
set -a; . ./.env; set +a

# 1. หยุดแอป + infra
docker stack rm ${ENV_NAME}_app
docker stack rm ${ENV_NAME}_infra

# 2. ลบ volume ฐานข้อมูล (⚠️ ข้อมูลทั้งหมดจะหายถาวร!)
docker volume rm ${ENV_NAME}_postgres_data

# 3. Deploy ใหม่ — init_db สร้าง schema ใหม่ + สร้างบัญชี admin/ครูสภาใหม่
docker stack deploy -c docker-compose.infra.yml ${ENV_NAME}_infra
./pull_all.sh

# 4. ดู credentials ใหม่ (ต่างจากรอบก่อนเสมอ)
docker service logs ${ENV_NAME}_app_backend | grep "username"
```

**หลังจากรีเซ็ตแล้ว ต้องทำอะไรต่อ:**
- นำเข้านักเรียนอีกครั้งผ่านหน้าเว็บ (เมนู "นำเข้า Excel") — หรือรัน seed ข้อมูลตัวอย่างสำหรับนำเสนอ:
  ```bash
  cd backend
  DATABASE_URL=postgresql://... ./venv/bin/python -m scripts.seed_data
  ```
- ตรวจสอบบัญชี admin ใหม่จาก log/ไฟล์ แล้วเปลี่ยนรหัสตอน login ครั้งแรก

> 💡 อยากเช็คว่าลบ volume สำเร็จไหม: `docker volume ls | grep ${ENV_NAME}_postgres`
> volume ที่ใช้จริงคือ `${ENV_NAME}_postgres_data` (ตามที่ mount ใน `docker-compose.infra.yml`)

---

## 🧪 เทส Backend

```bash
docker compose -f docker-compose.test.yml run --rm test_runner sh -c "export PYTHONDONTWRITEBYTECODE=1 && python -m pytest -p no:cacheprovider -v /app/tests/"
```

## 📐 ขอบเขตงาน (Scope)

ดูไฟล์ `docs/scope.md` สำหรับรายละเอียด In Scope / Out of Scope ของเวอร์ชันนี้
