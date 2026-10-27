# การทดสอบและการนำขึ้นระบบ

บทนี้อธิบายวิธีรันชุดทดสอบ สร้าง image และนำระบบขึ้น Docker Swarm
รวมถึงวิธีตรวจว่าการนำขึ้นสำเร็จจริง และวิธีย้อนกลับเมื่อมีปัญหา
ทุกคำสั่งในบทนี้รันจาก root ของ repository ยกเว้นที่ระบุไว้

## ใครใช้บทนี้

นักพัฒนาที่ต้องส่งงานขึ้น staging หรือ production และผู้ดูแลระบบเทคนิคที่ต้องกู้ระบบ
ผู้อ่านต้องเข้าถึงเครื่องที่รัน Docker และมีสิทธิ์ในกลุ่ม `docker`

## ก่อนเริ่ม

- เตรียม `.env` ที่ root ให้ครบ โดยคัดลอกจาก `.env.example`
- ตรวจว่า `git lfs` ติดตั้งอยู่ เพราะไฟล์คู่มือการทำงานถูกเก็บด้วย Git LFS
- ตรวจว่าไม่มีงานค้างใน working tree ก่อนนำขึ้นระบบ เพราะสคริปต์ deploy จะ `reset --hard`
- รู้ว่ากำลังทำกับ environment ใด เพราะ `ENV_NAME` ใน `.env` เป็นตัวกำหนดชื่อ stack ทั้งหมด

## การทดสอบ backend

### สภาพแวดล้อมของชุดทดสอบ

ชุดทดสอบรันใน Docker สอง container คือฐานข้อมูลทดสอบและตัวรัน pytest

| ส่วน | ค่า |
|---|---|
| ฐานข้อมูลทดสอบ | `postgres:16-alpine` ชื่อ container `piri_test_postgres` |
| พอร์ตที่เปิดบนเครื่อง | `5435` |
| ฐานข้อมูลใน container | `test_piri_db` |
| ตัวรัน | image จาก `backend/Dockerfile` ชื่อ `piri_test_runner` |
| โค้ดที่เมาท์ | `./backend` ไปที่ `/app` |
| `PYTHONPATH` | `/app` |

`docker-compose.test.yml` override `DATABASE_URL` ให้ชี้ฐานข้อมูลทดสอบ และตั้งค่า `JWT_SECRET`
กับ `SUPER_ADMIN_ID` เป็นค่าสำหรับทดสอบเท่านั้น ค่าเหล่านี้ไม่ใช่ของจริงและห้ามนำไปใช้บนระบบจริง

### คำสั่งรัน

```bash
docker compose -f docker-compose.test.yml run --rm test_runner \
  sh -c "export PYTHONDONTWRITEBYTECODE=1 && python -m pytest -p no:cacheprovider -v /app/tests/"
```

รันไฟล์เดียวให้ต่อท้ายด้วย path ภายใน container เช่น `/app/tests/test_issues.py`
รันเคสเดียวให้ต่อด้วย `::ชื่อฟังก์ชัน`

ชุดทั้งหมดใช้เวลาประมาณหนึ่งชั่วโมงบนเครื่องนี้
ให้ตั้ง timeout ของคำสั่งให้มากพอ ไม่งั้นจะถูกตัดกลางคันและดูเหมือนเทสต์ล้ม

### สิ่งที่ conftest จัดเตรียมให้

- สร้างฐานข้อมูลชื่อสุ่มใหม่ต่อหนึ่ง session แล้วรัน `init_db` เพื่อสร้าง schema ครบ
- `clean_database` เป็น autouse และ `TRUNCATE` ทุกตารางก่อนทุกเทสต์
- มี fixture `db_pool` สำหรับตรวจฐานข้อมูลโดยตรง
- มี `client` ที่เป็น `TestClient` ครอบแอป FastAPI

ตารางที่ถูกล้างอยู่ใน `_TABLES` ใน `conftest.py`
การเพิ่มตารางใหม่ต้องเพิ่มชื่อที่นั่น ไม่งั้นข้อมูลจะค้างข้ามเทสต์และทำให้เทสต์ล้มแบบสุ่ม

### รูปแบบเทสต์ที่ต้องเขียน

| ข้อกำหนด | เหตุผล |
|---|---|
| สร้างโลกทดสอบใน fixture | ฐานข้อมูลว่างทุกครั้ง ห้ามอ้าง id คงที่ |
| ตรวจฐานข้อมูลหลังยืนยันสถานะ HTTP | สถานะ 200 ไม่ได้พิสูจน์ว่าเขียนข้อมูลถูก |
| ตรวจก่อนและหลังสำหรับค่าที่เปลี่ยน | เช่นจำนวนที่นั่งคงเหลือ |
| soft delete ต้องตรวจ `deleted_at IS NOT NULL` | แถวยังอยู่โดยเจตนา |
| endpoint ที่กู้คืนได้ต้องตรวจทั้งลบและกู้ | ป้องกันการกู้ที่เขียนผิด |
| ใช้ผู้ใช้จริงแทนการ mock สิทธิ์ | ได้ทดสอบ RBAC ไปด้วย |
| mock เฉพาะการยิงคิวและการส่ง push | สองอย่างนี้เป็นขอบที่ออกนอก process |
| ไม่ mock เวลา | ใช้ระยะห่างเป็นวันหรือชั่วโมงจากเวลาจริง |
| validation และ boundary ใช้ `parametrize` | ลดโค้ดซ้ำและเห็นเคสที่ล้มชัด |

แยก 400 กับ 422 ให้ออก เพราะ 422 มาจาก Pydantic และ 400 มาจาก service
ถ้าเขียน `assert res.status_code in (400, 422)` ให้ถือว่ารู้ว่าทั้งสองด่านทำงาน

### การอ่านผลลัพธ์

- `AssertionError` ที่ฝั่งฐานข้อมูลมักแปลว่า query ในเทสต์ไม่ตรงกับ schema
- 422 มักแปลว่า body ขาดฟิลด์หรือชนิดผิด ไม่ใช่สิทธิ์
- 500 มักแปลว่า constraint ในฐานข้อมูลถูกชน หรือลืม commit transaction
- ถ้าเทสต์ล้มแบบไม่ซ้ำที่ ให้ตรวจว่ามีตารางที่ลืมเพิ่มใน `_TABLES` หรือใช้เวลาจริงในระยะที่แคบเกินไป

## การทดสอบ frontend

### คำสั่งที่ต้องรันครบ

```bash
cd frontend
npm install
npm run type-check
npm run lint
npm run test:unit
npm run build
```

`test:unit` เขียวไม่ได้รับประกันว่า build ผ่าน เพราะ `vue-tsc` เข้มงวดกว่าตัวรันหน่วย
ต้องผ่านทั้งสี่คำสั่งก่อนคอมมิต

`npm run lint` รันทุกสคริปต์ที่ขึ้นต้นด้วย `lint:` ตามลำดับ
ได้แก่ `oxlint` `eslint` `lint:colors` และ `lint:palette`

### เทสต์หน่วยและเทสต์ end-to-end

| ชนิด | คำสั่ง | สภาพแวดล้อม |
|---|---|---|
| หน่วย | `npm run test:unit` | vitest กับ `jsdom` |
| end-to-end | `npm run test:e2e` | Playwright |

Playwright ต้องติดตั้ง browser ก่อนด้วย `npx playwright install`
ค่า `baseURL` มาจาก `E2E_BASE_URL` ถ้าไม่ตั้งจะใช้ `http://localhost:5173` นอก CI
และ `http://localhost:4173` บน CI ซึ่งรัน `npm run preview`

`webServer` ของ Playwright จะสตาร์ท dev server ให้ถ้ายังไม่มี และใช้ตัวที่รันอยู่ซ้ำ

### การจัดรูปแบบ

รัน `npm run format` เฉพาะไฟล์ที่แก้ ไม่ใช่ทั้ง repository
การจัดรูปแบบทั้งก้อนจะแก้ไฟล์ที่ไม่ได้แตะและอาจทำให้ inline handler ในเทมเพลตเสีย

## การนำขึ้นระบบ

### สถาปัตยกรรมที่รันอยู่

| stack | ประกอบด้วย |
|---|---|
| `${ENV_NAME}_infra` | PostgreSQL 16 และ Redis 7 |
| `${ENV_NAME}_app` | backend 3, frontend 3, worker 1, push_worker 1 |
| `global` | Traefik ที่ถือพอร์ต 80 |

Traefik รับคำขอตามชื่อโดเมนใน `API_DOMAIN` และ `WEB_DOMAIN`
backend ฟังพอร์ต 8000 และ frontend ฟังพอร์ต 80 ภายใน container
ทั้งสองอยู่ในเครือข่าย `traefik-public` และเครือข่ายภายใน `app-internal-${ENV_NAME}`

backend และ frontend ตั้ง `order: start-first` และ `parallelism: 1`
จึงเริ่มตัวใหม่ก่อนหยุดตัวเก่าและไม่ทำให้ระบบขาดช่วง
healthcheck ของ backend เรียก `/health` ทุก 10 วินาที

### ลำดับการนำขึ้นครั้งแรก

```bash
docker network create --driver overlay traefik-public
docker network create --driver overlay app-internal-${ENV_NAME}
docker stack deploy -c docker-compose.infra.yml ${ENV_NAME}_infra
docker stack deploy -c docker-compose.app.yml ${ENV_NAME}_app
```

ครั้งแรกให้ build image ก่อน deploy มิฉะนั้น Swarm จะดึง tag ที่ไม่มีอยู่
การนำขึ้นปกติใช้ `pull_all.sh` ซึ่งทำครบทุกขั้น

### สิ่งที่ `pull_all.sh` ทำ

1. โหลด `.env` และหยุดถ้าไม่พบ
2. อ่านชื่อ branch ปัจจุบัน
3. `git fetch origin` แล้ว `git reset --hard origin/<branch>` ทำให้ working tree เท่ากับ remote
4. เรียก `git lfs pull` สูงสุดสามรอบ แล้วตรวจว่าไม่มีไฟล์ใน `frontend/public/playbooks` ที่ยังเป็น pointer
5. หยุดทันทีถ้ายังมี pointer เพราะ image จะได้ไฟล์ชี้แทนรูปจริง
6. ตั้ง `IMAGE_TAG` เป็น commit ย่อ 7 หลัก
7. build image backend
8. build image frontend แบบ `--no-cache` พร้อม build arg `VITE_API_BASE_URL`
9. `docker stack deploy -c docker-compose.app.yml ${ENV_NAME}_app`

ขั้นที่ 3 เป็นเหตุที่ห้ามมีงานค้างที่ยังไม่ commit บนเครื่องที่รันสคริปต์

frontend ต้อง build ใหม่ทุกครั้งเพราะตัวแปร `VITE_*` ถูกฝังตอน build
การแก้ `VITE_API_BASE_URL` ใน `.env` จึงต้อง deploy ใหม่ ไม่ใช่ restart

### การย้อนกลับ

`oh_shit.sh` ถอยโค้ดกลับหนึ่ง commit แล้ว deploy image ของ commit นั้น

```bash
git log --oneline -3
./oh_shit.sh
```

ข้อจำกัดที่ต้องรู้ก่อนใช้

- สคริปต์ทำ `git reset --hard HEAD~1` ซึ่งทิ้งงานที่ยังไม่ commit
- ต้องมี image ของ commit ก่อนหน้าอยู่ในเครื่อง ถ้าลบ image ไปแล้วจะย้อนไม่ได้
- การย้อนโค้ดไม่ย้อนข้อมูลในฐานข้อมูล ถ้า migration ใหม่แก้ schema การย้อนอาจทำให้ backend เก่าอ่านข้อมูลไม่ได้

ถ้าต้องย้อนมากกว่าหนึ่ง commit ให้ `git reset --hard <commit>` เองแล้ว deploy stack ด้วย tag นั้น
อย่ารัน `oh_shit.sh` ซ้ำหลายรอบโดยไม่ตรวจว่าอยู่ที่ commit ใด

### การตรวจหลังนำขึ้น

1. เรียก `/health` ของโดเมน API และต้องได้ `{"status":"ok","database":"connected"}`
2. `docker service ls` ต้องเห็นทุก service เป็น `1/1` หรือ `3/3` ตามจำนวน replica
3. `docker service ps <service> --no-trunc` ต้องไม่มี task ที่ restart ซ้ำ
4. `docker service logs <service>` ต้องไม่มี traceback และต้องเห็นข้อความว่า `init_db` ทำงานจบ
5. ล็อกอินด้วยบัญชีทดสอบและเปิดหน้าแรก ตรวจว่าข้อมูลโหลดได้
6. ตรวจว่าหน้าที่ใช้ worker ทำงาน เช่นนำเข้าไฟล์ตัวอย่างบน local ไม่ใช่บนข้อมูลจริง

## ระบบทำอะไรเบื้องหลัง

- `init_db` ทำงานทุกครั้งที่ backend เริ่ม และรัน migration ที่ยังไม่ถูกบันทึกใน `schema_migrations`
- backend ทุก replica รัน `init_db` พร้อมกันได้เพราะคำสั่งเป็น idempotent
- image ถูกติด tag ด้วย commit ย่อ จึงย้อนกลับได้เมื่อ image ยังอยู่
- service worker ใช้ cache ชื่อ `piri-shell-v3` และไม่แคช path ที่ขึ้นต้นด้วย `/api/`
- service worker ใหม่จะรอจนแท็บเดิมถูกปิดก่อนเข้าทำงาน จึงไม่เรียก `skipWaiting` ตอนติดตั้ง
- Traefik เลือก backend ตามชื่อโดเมน ไม่ได้ใช้ path นำหน้า

## ข้อจำกัดและข้อควรระวัง

- ไม่มี CI บน GitHub ด่านทั้งหมดรันบนเครื่องก่อน push
- `pull_all.sh` เขียนทับ working tree ด้วย `reset --hard`
- `oh_shit.sh` ย้อนได้ครั้งละหนึ่ง commit และย้อนโค้ดเท่านั้น ไม่ย้อนฐานข้อมูล
- `docker image prune -a` จะลบ image ที่ใช้ย้อนกลับได้
- ชุดทดสอบ backend ใช้เวลานานและต้องมีทรัพยากรเพียงพอ
- ระบบไม่มี environment สำหรับทดสอบแยกจาก staging และ production
- ผู้ใช้ที่เปิดแอปค้างไว้อาจเห็นหน้าจอเวอร์ชันเก่าจนกว่าจะปิดแท็บทั้งหมด เพราะ service worker รอจังหวะเปลี่ยน
- ห้ามรัน migration ที่ลบหรือเปลี่ยนชนิดคอลัมน์โดยไม่ตรวจข้อมูลจริงก่อน

## แก้ไขปัญหาและคำถามที่พบบ่อย

**ถาม: รันชุดทดสอบแล้วค้างนานผิดปกติ**
ตอบ: ชุดนี้มีจำนวนเทสต์มากและใช้ฐานข้อมูลจริง
ให้ตั้ง timeout ยาวพอและรันเบื้องหลัง แล้วอ่าน output จากไฟล์
อย่าตัดสินใจจาก output บางส่วนที่เห็นระหว่างรัน

**ถาม: เทสต์ล้มเฉพาะบางครั้งและผ่านเมื่อรันใหม่**
ตอบ: ตรวจสามอย่าง
หนึ่ง มีตารางที่ลืมเพิ่มใน `_TABLES` ทำให้ข้อมูลค้าง
สอง ใช้ระยะเวลาที่แคบเกินไป เช่นหน่วยวินาที
สาม มีการพึ่งลำดับของแถวโดยไม่มี `ORDER BY`

**ถาม: ต่อฐานข้อมูลทดสอบที่พอร์ต 5433 ไม่ได้**
ตอบ: ชุดทดสอบนี้เปิดพอร์ต `5435` ไม่ใช่ `5433`
ถ้าต้องต่อจากเครื่อง ให้ใช้ `localhost:5435` และฐานข้อมูล `test_piri_db`

**ถาม: deploy แล้วหน้าจอยังเป็นเวอร์ชันเก่า**
ตอบ: ตรวจสามอย่าง
หนึ่ง image tag ของ frontend ตรงกับ commit ล่าสุดหรือไม่
สอง service worker รอจนแท็บเดิมปิด ถ้าผู้ใช้เปิดค้างไว้จะยังเห็นของเก่า
สาม ตรวจว่า build ใช้ `VITE_API_BASE_URL` ที่ถูกต้อง เพราะค่านี้ฝังตอน build

**ถาม: `pull_all.sh` หยุดที่ขั้น Git LFS**
ตอบ: แปลว่าไฟล์ใน `frontend/public/playbooks` ยังเป็น pointer
ตรวจเน็ตและ DNS แล้วรันใหม่ สคริปต์ลองเองสามรอบและหยุดเพื่อไม่ให้ deploy รูปที่ใช้ไม่ได้

**ถาม: deploy แล้ว backend restart วน**
ตอบ: ตรวจ `docker service logs` ของ backend
สาเหตุที่พบบ่อยคือ `DATABASE_URL` ชี้ผิด ฐานข้อมูลยังไม่ขึ้น หรือ migration ล้ม
ถ้าเป็นเพราะ commit ใหม่ ให้ย้อนด้วย `oh_shit.sh` แล้วตรวจบน staging ก่อน

**ถาม: ย้อนกลับแล้วระบบยังพัง**
ตอบ: สคริปต์ย้อนโค้ดแต่ไม่ย้อนฐานข้อมูล
ถ้า commit ที่ผิดรัน migration ไว้ ต้องตรวจ schema เทียบกับ `init_db.py` และเขียน migration ที่แก้ย้อนกลับ
ห้ามแก้ตารางจริงด้วยมือโดยไม่มี backup

**ถาม: `/health` ตอบ `disconnected`**
ตอบ: backend ยังทำงานแต่ต่อฐานข้อมูลไม่ได้
ตรวจว่า stack infra ทำงานอยู่ ตรวจชื่อ service ใน `DATABASE_URL` ว่าตรงกับ `${ENV_NAME}_infra_db`
และตรวจว่าเครือข่าย `app-internal-${ENV_NAME}` มีอยู่จริง

บทที่เกี่ยวข้อง: [สถาปัตยกรรมภายใน](architecture-internals.md) · [มาตรฐานการเขียนโค้ด](coding-standards-rules.md) · [งานเบื้องหลัง การแจ้งเตือน และ push](background-jobs-and-push.md) · [คู่มือผู้ดูแลระบบ](../3-admin-guide/index.md)
