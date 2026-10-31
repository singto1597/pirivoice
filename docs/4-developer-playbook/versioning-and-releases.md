# เวอร์ชันและการปล่อยงาน

บทนี้ตอบว่าเลขเวอร์ชันของ PIRIvoice หมายถึงอะไร ใคร bump เมื่อไหร่
และปล่อยงานอย่างไรให้ย้อนดูได้

- 🔢 **SemVer แบบปรับให้เข้ากับเว็บแอปที่ deploy เอง** — MAJOR · MINOR · PATCH
- 🏷️ **annotated tag + GitHub Release ทุกเวอร์ชัน** — ไม่ปล่อย tag ลอย
- 🧾 **`CHANGELOG.md` คือแหล่งความจริงของประวัติ** — อ้าง PR ทุกรายการ
- 🔁 **`release.sh` ทำครบ** — ตัด CHANGELOG · sync เลข · commit · tag · push · Release

> ⚠️ ไฟล์นี้อยู่ใน `docs/4-developer-playbook/` ซึ่งถูก `srcExclude` จาก VitePress
> ⇒ **ไม่ขึ้นบนเว็บ `/docs/` สาธารณะ** (ตั้งใจให้เป็นเอกสารภายใน)
> ห้ามลิงก์จากศูนย์ช่วยเหลือหรือคู่มือผู้ใช้

## เลขเวอร์ชันหมายถึงอะไร

| เลข | เปลี่ยนเมื่อ | ตัวอย่างในอดีต |
|---|---|---|
| **MAJOR** | เปลี่ยนโครงสร้างหรือความหมายข้อมูลแบบ breaking — ผู้ดูแลต้องแปลงข้อมูลเดิม หรือวิธีใช้งานเปลี่ยน | `v2.0.0` แกนปีการศึกษา + เลื่อนชั้น (unique index และรูปแบบ Excel เปลี่ยน) |
| **MINOR** | ฟีเจอร์ใหม่ที่ผู้ใช้เห็น หรือ endpoint ใหม่ ที่เข้ากับของเดิมได้ | `v1.16.0` Web Push · `v2.2.0` ศูนย์ช่วยเหลือ |
| **PATCH** | แก้บั๊ก ปรับ UI/ข้อความ ถอดโค้ด อัปเดต dependency หรือเอกสารนักพัฒนา | `v2.1.1` แก้ย้ายกลับห้องเดิม |

**migration ที่เพิ่มคอลัมน์/ตารางเฉย ๆ ไม่นับเป็น MAJOR** — นับเมื่อความหมายของข้อมูล
หรือวิธีใช้งานเปลี่ยนจริง

### หนึ่งเวอร์ชัน = หนึ่งกลุ่มงานที่ coherent

ไม่ใช่หนึ่ง PR และไม่ใช่หนึ่ง commit — `Adjust Landing Page 7` ไม่ควรได้เลขของตัวเอง
ถ้างานยังไม่พร้อม deploy ให้ค้างใน `[Unreleased]` ก่อน

### bump ตอนไหน

ตอนที่กลุ่มงาน **พร้อมขึ้น staging หรือ production** ไม่ใช่ทุกครั้งที่ merge
ถ้า staging นำ production อยู่และต้องรู้ว่า build ไหน ให้ใช้ `-rc.N` (ไม่สร้าง Release)

```bash
./release.sh 2.4.0-rc.1   # tag + Release แบบ prerelease ไม่แตะ CHANGELOG
```

## เลขเวอร์ชันอยู่ที่ไหนบ้าง

| ที่ | ใครเป็นคนใช้ | ใคร sync |
|---|---|---|
| `CHANGELOG.md` | มนุษย์และ GitHub Release notes | `release.sh` |
| `VERSION` (root) | สคริปต์/คนอ่าน | `release.sh` |
| `backend/core/config.py` → `PROJECT_VERSION` | `/api/version` และ `/openapi.json` | `release.sh` |
| `frontend/package.json` + `package-lock.json` | `__APP_VERSION__` ที่ฝังตอน build | `release.sh` (`npm version`) |
| git tag `vX.Y.Z` | `git describe`, GitHub Release | `release.sh` |

> **ทำไม `VERSION` ที่ root ไม่ใช่ค่าที่ backend ใช้** — build context ของ backend คือ
> `docker build ./backend` ⇒ ไฟล์ที่ root ไม่เข้าไปใน image
> ค่าที่รันจริงจึงต้องอยู่ใน `backend/core/config.py`

### commit ของ backend มาจากไหน

`/api/version` ตอบ `commit` จาก environment variable `GIT_SHA` ซึ่งถูกส่งเข้า image
เป็น build arg:

```text
pull_all.sh / setup.sh  →  --build-arg GIT_SHA=${IMAGE_TAG}
        ↓
backend/Dockerfile      →  ARG GIT_SHA=unknown · ENV GIT_SHA=${GIT_SHA}
        ↓
core/config.py          →  GIT_SHA: str = "unknown"
        ↓
GET /api/version        →  {"version": "2.3.0", "commit": "fc7d188"}
```

ห้ามอ่าน commit จาก `.git` ใน image เพราะ image ไม่มี `.git`
และห้ามใช้ `__BUILD_ID__` ฝั่ง frontend แทน — build context ของ frontend คือ `./frontend`
ที่ไม่มี `.git` ⇒ ใน Docker มันคืน `Date.now()` ไม่ใช่ SHA

## วิธีปล่อยงาน

### 1. เตรียม `[Unreleased]`

เพิ่มบรรทัดใต้หัวข้อให้ตรงกับหมวด (Added · Changed · Fixed · Removed · Security)
และอ้าง PR ทุกรายการด้วย `(#N)` ถ้างานนั้นไม่มี PR ให้อ้าง commit

```markdown
## [Unreleased]

### Added
- ฟีเจอร์ใหม่ที่ผู้ใช้เห็น (#123)

### Fixed
- บั๊กที่แก้ (#124)
```

### 2. รัน `release.sh`

```bash
git checkout main
git pull --ff-only
./release.sh 2.4.0
```

สคริปต์จะทำตามลำดับนี้ และ **หยุดทันที** ถ้าข้อใดไม่ผ่าน

1. ตรวจว่าอยู่บน `main`, working tree สะอาด, `main` ตรงกับ `origin/main`, tag ยังไม่มี
2. ตรวจว่า `[Unreleased]` มีรายการ (ไม่ว่าง)
3. เปลี่ยนหัวเป็น `## [X.Y.Z] - วันที่ไทย` แล้วเติม `[Unreleased]` ใหม่ + compare link
4. sync เลขเวอร์ชันทั้ง 4 ไฟล์
5. commit `chore(release): vX.Y.Z` (ถ้ามีไฟล์เปลี่ยน)
6. สร้าง annotated tag `vX.Y.Z`, push `main` และ tag
7. `gh release create --verify-tag --latest --notes-file <section ที่ตัดออกมา>`

### 3. deploy

`release.sh` ไม่ deploy เอง — ใช้ `pull_all.sh` ตามปกติ
ชื่อ image ยังเป็น commit hash ไม่ใช่เลข SemVer (ดูหัวข้อถัดไป)

> ⚠️ **ถ้า commit ที่จะดึง มาแก้ `pull_all.sh` เอง — ให้ `git fetch && git reset --hard origin/main`
> ใน clone นั้นก่อน แล้วค่อยรัน `./pull_all.sh`**
> เพราะ `pull_all.sh` เรียก `git reset --hard` อยู่ข้างใน และ bash อ่านไฟล์สคริปต์แบบ
> incremental ⇒ ไฟล์ถูกเปลี่ยนใต้มือ แต่ bash อ่านรอบเดิมต่อจนจบ คำสั่งที่แก้ใหม่
> (เช่น `--build-arg GIT_SHA=...`) **ไม่มีผลเงียบ ๆ** โดย deploy ยังขึ้น `✅` ตามปกติ
> — ดูรายละเอียดใน `docs/skills.md` ("pull_all.sh ที่อัปเดตตัวเองระหว่างรัน")

## ทำไม IMAGE_TAG ยังเป็น commit hash

`pull_all.sh` ตั้ง `IMAGE_TAG=$(git rev-parse --short HEAD)` และ compose ใช้
`pirivoice-${ENV_NAME}-backend:${IMAGE_TAG}`

คงไว้แบบนี้เพราะ:

- `oh_shit.sh` ย้อนกลับได้ด้วยการหา image ของ commit ก่อนหน้า — ผูกกับ hash ตรง ๆ
- ชื่อ image ไม่ต้อง sync กับเลข SemVer ซึ่งอาจ bump หลายครั้งต่อ commit เดียว
- เลข SemVer อยู่ที่ git tag / CHANGELOG / `/api/version` ซึ่งเป็นที่ที่คนหาอยู่แล้ว

## ข้อควรระวัง

### `oh_shit.sh` กับ commit ของ release

commit ที่ `release.sh` สร้างเปลี่ยนแค่ `CHANGELOG.md` / `VERSION` / เลขเวอร์ชัน
⇒ `git reset --hard HEAD~1` จะย้อนไป commit ที่ **โค้ดเหมือนกันทุกไบต์**
ถ้าต้องย้อนจริง ให้ระบุ commit หรือ tag เองแล้ว deploy image ของ commit นั้น

### tag ผิดแก้ได้ ถ้ายังไม่มีคน fetch

```bash
git tag -d v2.4.0
git push --delete origin v2.4.0
gh release delete v2.4.0 --yes
```

### Release ย้อนหลัง backdate ไม่ได้

`gh release create` ตั้งวันที่สร้างเป็นวันนี้เสมอ ⇒ Release ที่สร้างย้อนหลัง
ต้องเขียนวันที่เดิมไว้ในเนื้อหา (`ย้อนหลัง — ปล่อยจริง <วันที่>`)

### repo เป็น public

`CHANGELOG.md` และ Release notes ห้ามมี IP ภายใน path ของเครื่อง หรือข้อมูลนักเรียน

### LFS กับ source archive

source archive ของ tag เก็บ LFS pointer ไม่ใช่ไฟล์ `.webp`/`.pdf` จริง
เราไม่แนบ asset ใน Release และ `pull_all.sh` ดึง LFS เอง ⇒ ไม่กระทบ deploy

## ประวัติย้อนหลัง

ระบบเริ่มใช้ SemVer อย่างเป็นทางการที่ `v2.3.0` (31 ต.ค. 2026)
เวอร์ชันก่อนหน้าถูกกำหนดย้อนหลัง 35 จุด โดยยึด commit บน `main` และ ancestry
รายละเอียดทั้งหมดอยู่ใน [`CHANGELOG.md`](../../CHANGELOG.md)

## ติดปัญหาตรงไหน? ดูวิธีแก้ตรงนี้เลย

**Q: `release.sh` หยุดที่ "main ไม่ตรงกับ origin/main"?**

👉 **วิธีแก้:** มี commit บน origin ที่เครื่องนี้ยังไม่มี หรือมี commit local ที่ยังไม่ push
ให้ `git pull --ff-only` หรือ push ก่อน แล้วรันใหม่

**Q: `release.sh` หยุดที่ "section [Unreleased] ว่าง"?**

👉 **วิธีแก้:** เพิ่มรายการใต้ `## [Unreleased]` ใน `CHANGELOG.md` ก่อน
สคริปต์ตั้งใจไม่ปล่อย release ที่ไม่มีอะไรให้บันทึก

**Q: `gh release create` ฟ้องว่า tag มีอยู่แล้ว?**

👉 **วิธีแก้:** ตรวจว่า tag นั้นชี้ commit ที่ถูกต้องด้วย `git show vX.Y.Z`
ถ้าผิดให้ลบ tag (ทั้ง local และ remote) แล้วรันใหม่ — อย่าใช้ `--target` ข้าม เพราะจะได้ tag ที่ชี้ผิด

**Q: `/api/version` ตอบ `commit: "unknown"`?**

👉 **วิธีแก้:** image ถูก build โดยไม่ส่ง `GIT_SHA` — ตรวจว่า build ผ่าน `pull_all.sh`
หรือ `setup.sh` (ทั้งสองส่ง `--build-arg GIT_SHA=${IMAGE_TAG}` แล้ว)
ถ้า build มือ ให้เติม `--build-arg GIT_SHA=$(git rev-parse --short HEAD)` เอง

**Q: เว็บแสดงเลขเวอร์ชันไม่ตรงกับ tag?**

👉 **วิธีแก้:** frontend ฝัง `__APP_VERSION__` ตอน build ⇒ ต้อง build image ใหม่
ไม่ใช่ restart และ Cloudflare อาจแคชหน้า — ดู `Cache-Control` ของ `/api/version` ประกอบ

บทที่เกี่ยวข้อง: [การทดสอบและการนำขึ้นระบบ](testing-and-deployment.md) · [มาตรฐานการเขียนโค้ด](coding-standards-rules.md)
