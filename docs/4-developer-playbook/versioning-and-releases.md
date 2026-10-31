# เวอร์ชันและการปล่อยงาน

บทนี้ตอบว่าเลขเวอร์ชันของ PIRIvoice หมายถึงอะไร ใคร bump เมื่อไหร่
ปล่อยงานอย่างไรให้ย้อนดูได้ และถ้าปล่อยแล้วพังจะถอยกลับอย่างไร

- 🔢 **SemVer แบบปรับให้เข้ากับเว็บแอปที่ deploy เอง** — MAJOR · MINOR · PATCH
- 🧾 **`CHANGELOG.md` เขียนเป็นเรื่องเล่า ไม่ใช่รายการ Added/Changed/Fixed**
- 🏷️ **annotated tag + GitHub Release ทุกเวอร์ชัน** — ไม่ปล่อย tag ลอย
- 🔁 **`release.sh` ทำครบ** — ตรวจ · ตัด CHANGELOG · sync เลข · commit · tag · push · Release
- 🧪 **`release.sh --dry-run`** — ตรวจทุกด่านและดู diff โดยไม่แตะ git
- ⏪ **`rollback.sh <image-tag>`** — ถอย image โดยไม่แตะ git
- ✅ **CI + version manifest** — ด่านที่ตอบว่า "ประวัติเวอร์ชันยังเชื่อถือได้ไหม"

> ⚠️ ไฟล์นี้อยู่ใน `docs/4-developer-playbook/` ซึ่งถูก `srcExclude` จาก VitePress
> ⇒ **ไม่ขึ้นบนเว็บ `/docs/` สาธารณะ** (ตั้งใจให้เป็นเอกสารภายใน)
> ห้ามลิงก์จากศูนย์ช่วยเหลือหรือคู่มือผู้ใช้

## เลขเวอร์ชันหมายถึงอะไร

| เลข | เปลี่ยนเมื่อ | ตัวอย่างในอดีต |
|---|---|---|
| **MAJOR** | **"วิธีคิดของระบบ" เปลี่ยน** — ที่มาของความจริงย้ายที่ ความหมายของข้อมูลเปลี่ยน แกนใหม่ที่ทุกอย่างต้องอ้างถึง หรือสถาปัตยกรรมเปลี่ยนแบบที่ของเดิมตีความไม่ได้ | `v2.0.0` นักเรียนกลายเป็น (รหัสนักเรียน, ปีการศึกษา) — จากเดิมเขียนทับได้ เป็นต้องเก็บประวัติ |
| **MINOR** | ฟีเจอร์ใหม่ที่ผู้ใช้เห็น หรือ endpoint ใหม่ ที่เข้ากับของเดิมได้ | `v1.16.0` Web Push · `v2.2.0` ศูนย์ช่วยเหลือ |
| **PATCH** | แก้บั๊ก ปรับ UI/ข้อความ ถอดโค้ด อัปเดต dependency หรือเอกสารนักพัฒนา | `v2.1.1` แก้ย้ายกลับห้องเดิม |

### MAJOR ไม่ต้องรอ breaking API

ถ้ารู้สึกว่า "ต่อจากนี้ระบบคิดต่างจากเดิมแล้ว" ให้ **บวก MAJOR ทันที** ไม่ต้องสะสมไว้รอรอบใหญ่
และไม่ต้องมี breaking change ใน API เพื่ออนุญาตให้ bump

ตัวอย่างที่เข้าเงื่อนไข:

- ย้ายแหล่งความจริง (เช่น สถานะเรื่องเริ่มคำนวณจากตารางใหม่ ไม่ใช่คอลัมน์เดิม)
- เปลี่ยนความหมายของข้อมูลที่มีอยู่ (นักเรียน 1 แถว = 1 คน → 1 คนต่อ 1 ปีการศึกษา)
- เพิ่มแกนที่ทุกอย่างต้องอ้างถึง (ปีการศึกษา ภาคเรียน โครงสร้างโรงเรียน)
- เปลี่ยนวิธีที่ระบบตัดสินใจ (สิทธิ์มาจาก role → มาจาก permission list)

**migration ที่เพิ่มคอลัมน์/ตารางเฉย ๆ ไม่นับเป็น MAJOR** — นับเมื่อความหมายของข้อมูล
หรือวิธีใช้งานเปลี่ยนจริง

> ข้อยกเว้นที่บันทึกไว้: `v1.0.0` คือจุด Go-Live (23 ส.ค. 2026) ไม่ใช่การเปลี่ยนวิธีคิด
> ใช้ MAJOR เพื่อบอกว่า "จากนี้คือของจริง" ครั้งเดียว — ตั้งแต่ 1.0.0 เป็นต้นไปใช้กติกาปกติ

### หนึ่งเวอร์ชัน = หนึ่งกลุ่มงานที่ coherent

ไม่ใช่หนึ่ง PR และไม่ใช่หนึ่ง commit — `Adjust Landing Page 7` ไม่ควรได้เลขของตัวเอง
ถ้างานยังไม่พร้อม deploy ให้ค้างใน `[Unreleased]` ก่อน

### bump ตอนไหน

ตอนที่กลุ่มงาน **พร้อมขึ้น staging หรือ production** ไม่ใช่ทุกครั้งที่ merge
ถ้า staging นำ production อยู่และต้องรู้ว่า build ไหน ให้ใช้ `-rc.N`
(rc เป็น preview tag — ไม่แตะ CHANGELOG/VERSION และไม่แย่งป้าย Latest)

```bash
./release.sh 2.4.0-rc.1   # tag + Release แบบ prerelease ไม่แตะ CHANGELOG/VERSION
```

## เลขเวอร์ชันอยู่ที่ไหนบ้าง

| ที่ | ใครเป็นคนใช้ | ใคร sync |
|---|---|---|
| `CHANGELOG.md` | มนุษย์และ GitHub Release notes | `release.sh` |
| `VERSION` (root) | สคริปต์/คนอ่าน | `release.sh` |
| `backend/core/config.py` → `PROJECT_VERSION` | `/api/version` และ `/openapi.json` | `release.sh` |
| `frontend/package.json` + `package-lock.json` | `__APP_VERSION__` ที่ฝังตอน build | `release.sh` (`npm version`) |
| `scripts/version-manifest.tsv` | validator และ CI | `release.sh` |
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

## CHANGELOG เขียนอย่างไร

`CHANGELOG.md` เป็นบันทึกการเดินทางของระบบ ไม่ใช่ changelog เชิงเทคนิค
คนที่อ่านต้องตอบได้ว่า **ตอนนั้นมีปัญหาอะไร ทางเลือกมีอะไร และทำไมเลือกทางนี้**

ทุกเวอร์ชันใช้หกหัวข้อนี้ (ตัดหัวข้อที่ไม่มีเรื่องออกได้ ไม่ต้องยัดให้ครบ):

| หัวข้อ | ตอบอะไร |
|---|---|
| **บริบท ณ ตอนนั้น** | ตอนนั้นมีอะไรแล้ว ขาดอะไร ระบบใหญ่แค่ไหน |
| **สิ่งที่ทำ** | รอบนี้ทำอะไร เล่าเป็นเรื่อง ไม่ใช่ลิสต์ commit |
| **ตัดสินใจเพราะ** | ทางเลือกที่มี และทำไมเลือกทางนี้ |
| **เทคโนโลยีที่เปลี่ยน/ลอง** | เพิ่ม ถอด หรือลองอะไร |
| **พังแล้วแก้อย่างไร** | bug หรือ incident ที่เจอ และแก้ยังไง |
| **บทเรียน** | รอบนั้นสอนอะไร — ทั้งที่ผ่านมาได้ และที่ยังเจ็บอยู่ |

ข้อความที่บอกว่า "ตัดสินใจเพราะ…" ต้องมีที่มากำกับ:

- `> ที่มา: …` = มีหลักฐานตรง (PR, commit message, เอกสารหรือบทเรียน ณ ตอนนั้น)
- `> อนุมานจาก diff` = อ่านจากโค้ดและชื่อ commit แล้วสรุปเอง ไม่มีใครพูดแบบนี้ตรง ๆ

**ห้ามแต่งเหตุผลที่ไม่มีหลักฐาน** — ถ้าไม่รู้จริงให้เขียนว่า "อนุมานจาก diff"

### `[Unreleased]` ต้องมีชื่อรุ่น

`release.sh` อ่านชื่อรุ่นจากหัวข้อนี้ ถ้าไม่มีชื่อจะไม่ยอมปล่อย

```markdown
## [Unreleased] — ทำให้ประวัติเชื่อถือได้: SAD, dry-run, rollback, CI

**บริบท ณ ตอนนั้น** — …
**สิ่งที่ทำ** — …
**Migration:** ไม่มี
```

เงื่อนไขที่สคริปต์บังคับ:

1. หัวข้อต้องเป็น `## [Unreleased] — <ชื่อรุ่น>` (ห้ามใช้ `ยังไม่ตัดเวอร์ชัน`)
2. เนื้อหาต้องไม่ว่าง
3. ต้องมีบรรทัด `**Migration:**` (เขียน `ไม่มี` ถ้าไม่มี migration)

หลัง `release.sh` ทำงาน หัวข้อ `[Unreleased]` จะถูกแทนที่ด้วย placeholder
`ยังไม่ตัดเวอร์ชัน` — เขียนชื่อรุ่นใหม่ตอนจะปล่อยครั้งถัดไป

## วิธีปล่อยงาน

### 1. เตรียม `[Unreleased]`

เขียนเนื้อหาให้ครบตามรูปแบบข้างบน และใส่ `**Migration:**` ให้ถูก
(ถ้ามี migration ให้ระบุเลขไฟล์ `00X` และสิ่งที่ต้องทำ)

### 2. ตรวจก่อนด้วย `--dry-run`

```bash
git checkout main
git pull --ff-only
./release.sh 2.4.0 --dry-run
```

dry-run ทำทุกอย่างเหมือนของจริง — ตรวจ repo, ตรวจ manifest, ตัด CHANGELOG,
sync เลขเวอร์ชัน, เพิ่มแถว manifest, รัน preflight — แล้วแสดง `git diff --stat`
กับ notes ที่จะใช้ จากนั้น **คืนไฟล์ทั้งหมดกลับ** และยืนยันว่า working tree สะอาด

ใช้ทุกครั้งที่ยังไม่แน่ใจ โดยเฉพาะหลังแก้ `CHANGELOG.md` หรือ `release.sh` เอง

### 3. ปล่อยจริง

```bash
./release.sh 2.4.0
```

สคริปต์จะทำตามลำดับนี้ และ **หยุดทันที** ถ้าข้อใดไม่ผ่าน:

1. ตรวจว่าอยู่บน `main`, working tree สะอาด, `main` ตรงกับ `origin/main`, tag ยังไม่มี
2. ตรวจว่า `VERSION` ตรงกับ tag ล่าสุด และเลขใหม่เดินทีละขั้น (major/minor/patch)
3. รัน `node scripts/version-manifest.mjs` ตรวจประวัติเดิมทั้ง 36 แถว
4. อ่านชื่อรุ่นและเนื้อหาจาก `[Unreleased]`
5. sync เลขเวอร์ชันทั้ง 4 ไฟล์
6. เพิ่มแถว manifest (`cut=RELEASE`) แล้วรัน **preflight** — ถ้า refs ไม่ครบ จะล้มตรงนี้
   ก่อนแตะ git
7. commit `chore(release): vX.Y.Z`
8. สร้าง annotated tag `vX.Y.Z`
9. รัน validator ซ้ำแบบเต็ม (ตอนนี้ tag มีแล้ว)
10. push `main` และ tag
11. `gh release create --verify-tag --latest --notes-file <section ที่ตัดออกมา>`

> ถ้าล้มก่อนถึงข้อ 7 สคริปต์จะคืนไฟล์เวอร์ชันทั้งหมดให้อัตโนมัติ
> ⇒ รันใหม่ได้เลยโดยไม่ต้อง `git checkout -- .`

### refs ของเวอร์ชัน

แถว manifest มีคอลัมน์ `refs` ที่บอกว่า PR ไหนอยู่ในรุ่นนี้
ค่าเริ่มต้นสคริปต์ **เดาจาก commit ตั้งแต่ tag ก่อนหน้าถึง HEAD**
(หัว commit ที่ลงท้ายด้วย `(#N)` หรือขึ้นต้นด้วย `Merge pull request #N`)

ถ้า PR ถูก merge ซ้อนเข้า branch อื่น (stacked PR) จะไม่โผล่ใน log ของ `main`
ให้ระบุเอง:

```bash
./release.sh 2.4.0 --refs "PR #111-#112"
```

`refs` ถูกใช้เป็นด่าน: validator บังคับว่า PR ทุกเลขตั้งแต่ `#1` ถึงเลขสูงสุด
ถูกนับ **พอดีครั้งเดียว** ⇒ PR ที่ merge แล้วแต่ไม่ได้ระบุจะทำให้ release ล้ม
(และล้มตอน preflight ไม่ใช่หลังสร้าง tag)

### 4. deploy

`release.sh` ไม่ deploy เอง — ใช้ `pull_all.sh` ตามปกติ
ชื่อ image ยังเป็น commit hash ไม่ใช่เลข SemVer (ดูหัวข้อถัดไป)

> ⚠️ **ถ้า commit ที่จะดึง มาแก้ `pull_all.sh` เอง — ให้ `git fetch && git reset --hard origin/main`
> ใน clone นั้นก่อน แล้วค่อยรัน `./pull_all.sh`**
> เพราะ `pull_all.sh` เรียก `git reset --hard` อยู่ข้างใน และ bash อ่านไฟล์สคริปต์แบบ
> incremental ⇒ ไฟล์ถูกเปลี่ยนใต้มือ แต่ bash อ่านรอบเดิมต่อจนจบ คำสั่งที่แก้ใหม่
> (เช่น `--build-arg GIT_SHA=...`) **ไม่มีผลเงียบ ๆ** โดย deploy ยังขึ้น `✅` ตามปกติ
> — ดูรายละเอียดใน `docs/skills.md` ("pull_all.sh ที่อัปเดตตัวเองระหว่างรัน")

## version manifest และ validator

`scripts/version-manifest.tsv` คือตารางประวัติเวอร์ชันที่เครื่องอ่านได้
หนึ่งแถวต่อหนึ่งเวอร์ชัน เรียงจากเก่าไปใหม่:

```text
version	date	cut	bump	theme	refs
2.3.0	2026-10-31	d3fe36b	minor	SemVer + /api/version	PR #110
2.4.0	2026-10-31	RELEASE	minor	ทำให้ประวัติเชื่อถือได้	PR #111
```

| คอลัมน์ | ความหมาย |
|---|---|
| `version` | SemVer |
| `date` | วันที่ปล่อย (ต้องตรงกับหัวข้อใน `CHANGELOG.md`) |
| `cut` | commit ที่ tag ชี้ — ตัวที่ build image และ deploy จริง |
| `bump` | `major` / `minor` / `patch` — ใช้ตรวจว่าเลขเดินทีละขั้น |
| `theme` | ชื่อรุ่นสั้น ๆ (ตรงกับหัวข้อ `[Unreleased]` ตอนปล่อย) |
| `refs` | `PR #a-#b` หรือ `main` — ห้ามซ้ำ และต้องครบตั้งแต่ `#1` |

**`cut=RELEASE`** ใช้ได้เฉพาะแถวสุดท้าย แปลว่า "commit ที่ tag ของแถวนี้ชี้"
— จำเป็นเพราะ commit ไม่สามารถบรรจุ hash ของตัวเองได้
validator จะ resolve ผ่าน `v<version>` ให้

รันเองได้ทุกเมื่อ:

```bash
node scripts/version-manifest.mjs             # ด่านเต็ม
node scripts/version-manifest.mjs --preflight # ก่อน tag — แถว RELEASE ถือว่าชี้ HEAD
```

validator ตรวจ:

1. ครบ 6 คอลัมน์, SemVer ถูก, วันที่เรียงขึ้น, bump เดินทีละขั้น
2. `cut` มีจริง เป็น ancestor ของ HEAD และตรงกับ commit ที่ tag ชี้
3. tag ทุกตัวเป็น **annotated tag**
4. ความต่อเนื่อง — cut ของเวอร์ชันก่อนหน้าเป็น ancestor ของเวอร์ชันถัดไป
5. CHANGELOG มีหัวข้อของทุกเวอร์ชัน พร้อมวันที่ตรงกันและบรรทัด `**Migration:**`
6. `VERSION` = `PROJECT_VERSION` = `package.json` = `package-lock.json` (ทั้ง 2 ช่อง)
7. PR ตั้งแต่ `#1` ถึงเลขสูงสุดถูกนับใน refs พอดีครั้งเดียว

## CI gate

`.github/workflows/ci-version.yml` รันบน push และ pull request ที่เข้า `main`

```text
checkout (fetch-depth: 0 + tags)
  → node scripts/version-manifest.mjs
  → bash -n release.sh / rollback.sh / pull_all.sh
```

เป็น CI แบบ **ตรวจประวัติอย่างเดียว** — ไม่ build ไม่ deploy
เพราะ image build บนเครื่อง deploy เอง ด่านนี้มีไว้กัน:

- merge ที่แก้ `VERSION` แต่ลืมแก้ `package.json`
- CHANGELOG กับ tag หลุดจากกัน
- PR ใหม่ที่ merge แล้วแต่ไม่มีใครนับใน manifest

ถ้า CI แดง ให้รัน validator ในเครื่อง — ข้อความ error บอกแถวและเวอร์ชันที่ผิด

## ถอยกลับ: `rollback.sh`

เมื่อ deploy แล้วพัง และอยากกลับ image ชุดก่อน **โดยไม่แก้ git**:

```bash
./rollback.sh --list                  # ดู image tag ที่มีในเครื่อง
./rollback.sh 9fbe3ad --dry-run       # ตรวจว่า image มีจริง จะสลับอะไร
./rollback.sh 9fbe3ad                 # สลับจริง (ถามยืนยัน)
./rollback.sh 9fbe3ad --yes           # ไม่ถาม (ใช้ใน automate)
```

สคริปต์ตรวจว่า image ของ backend/frontend tag นั้นมีอยู่จริง แล้ว
`docker stack deploy` ด้วย `IMAGE_TAG=<tag>` — worker และ push_worker
ใช้ image backend ตามไปด้วยโดยอัตโนมัติ

**rollback.sh ไม่แตะ git เลย** — checkout ยังอยู่ที่เดิม
⇒ ครั้งต่อไปที่รัน `pull_all.sh` ระบบจะ deploy HEAD กลับมา
ถ้าตั้งใจถอยถาวร ต้อง revert commit บน `main` แล้ว deploy ใหม่

> ⚠️ `oh_shit.sh` เป็นสคริปต์รุ่นเก่าที่ `git reset --hard HEAD~1`
> ซึ่งเขียนประวัติ checkout ทิ้งและย้อนได้แค่ "หนึ่ง commit ก่อนหน้า"
> ไม่รู้ว่า image ของ commit นั้นยังอยู่หรือไม่ — **ใช้ `rollback.sh` แทน**

## ทำไม IMAGE_TAG ยังเป็น commit hash

`pull_all.sh` ตั้ง `IMAGE_TAG=$(git rev-parse --short HEAD)` และ compose ใช้
`pirivoice-${ENV_NAME}-backend:${IMAGE_TAG}`

คงไว้แบบนี้เพราะ:

- `rollback.sh` ระบุ image ได้ตรง ๆ ด้วย hash — ไม่ต้องเดาว่า SemVer ไหนตรงกับ build ไหน
- ชื่อ image ไม่ต้อง sync กับเลข SemVer ซึ่งอาจ bump หลายครั้งต่อ commit เดียว
- เลข SemVer อยู่ที่ git tag / CHANGELOG / `/api/version` ซึ่งเป็นที่ที่คนหาอยู่แล้ว

## ข้อควรระวัง

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
เวอร์ชันก่อนหน้า 35 จุดถูกกำหนดย้อนหลังในวันเดียวกัน โดยยึด commit บน `main`
และ ancestry — cut commit ของทุกเวอร์ชันอยู่ใน `scripts/version-manifest.tsv`
รายละเอียดทั้งหมดอยู่ใน [`CHANGELOG.md`](../../CHANGELOG.md)

## ติดปัญหาตรงไหน? ดูวิธีแก้ตรงนี้เลย

**Q: `release.sh` หยุดที่ "main ไม่ตรงกับ origin/main"?**

👉 **วิธีแก้:** มี commit บน origin ที่เครื่องนี้ยังไม่มี หรือมี commit local ที่ยังไม่ push
ให้ `git pull --ff-only` หรือ push ก่อน แล้วรันใหม่

**Q: `release.sh` หยุดที่ "section [Unreleased] ว่าง" หรือ "ยังไม่มีชื่อรุ่น"?**

👉 **วิธีแก้:** เขียนหัวข้อ `## [Unreleased] — <ชื่อรุ่น>` และเพิ่มเนื้อหา
พร้อมบรรทัด `**Migration:**` ก่อน สคริปต์ตั้งใจไม่ปล่อย release ที่ไม่มีอะไรให้บันทึก

**Q: preflight ฟ้อง "PR #N ไม่ถูกนับใน manifest"?**

👉 **วิธีแก้:** มี PR ที่ merge แล้วแต่ refs ไม่ครอบ — ส่ง `--refs` ให้ครบ
เช่น `./release.sh 2.4.0 --refs "PR #111-#113"` แล้วรัน dry-run ซ้ำ
ถ้าเป็น PR ที่ merge ซ้อนเข้า branch อื่น (ไม่ปรากฏใน log ของ main) ก็ต้องระบุเอง

**Q: validator ฟ้อง "tag vX ชี้ ... แต่ manifest ระบุ ..."?**

👉 **วิธีแก้:** แถว manifest กับ tag ไม่ตรงกัน — ตรวจ `git show vX.Y.Z`
ถ้า tag ชี้ผิดให้ลบ tag (ทั้ง local และ remote) แล้วสร้างใหม่ให้ชี้ cut commit
ห้ามแก้ manifest ให้ตาม tag ที่ผิด

**Q: `rollback.sh` ฟ้อง "ไม่พบ image ... tag นี้ไม่เคย build บนเครื่องนี้"?**

👉 **วิธีแก้:** rollback ได้เฉพาะ image ที่ยังอยู่ในเครื่อง (หรือ registry ที่ตั้งไว้)
ดูรายการด้วย `./rollback.sh --list` — ถ้า image ถูก prune ไปแล้ว ให้ deploy
commit เก่าผ่าน `pull_all.sh` แทน (checkout commit นั้นแล้วรัน)

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
