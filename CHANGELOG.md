# Changelog

ความเปลี่ยนแปลงทั้งหมดของ PIRIvoice (ระบบรับฟังความคิดเห็นและปัญหา สภานักเรียน)

รูปแบบตาม [Keep a Changelog](https://keepachangelog.com/th/1.1.0/)
และเลขเวอร์ชันตาม [Semantic Versioning](https://semver.org/lang/th/)

- **MAJOR** — เปลี่ยนโครงสร้างหรือความหมายข้อมูลแบบ breaking
- **MINOR** — ฟีเจอร์ใหม่ที่ผู้ใช้เห็น หรือ endpoint ใหม่ที่เข้ากับของเดิมได้
- **PATCH** — แก้บั๊ก ปรับ UI/ข้อความ ถอดโค้ด หรือแก้เอกสารนักพัฒนา

ทุกรายการอ้างถึง pull request ด้วย `(#N)` ยกเว้นเวอร์ชันที่ทำงานบน `main` ตรง
ซึ่งจะอ้าง commit แทน

## [Unreleased]

### Changed

- บันทึกกับดัก "สคริปต์อ่านไฟล์เดิมระหว่างรัน" ลง `docs/skills.md` กับเอกสาร versioning —
  ถ้า commit ที่ deploy แก้ `pull_all.sh` เอง ต้อง pull ก่อนเรียกสคริปต์ ไม่งั้น build arg
  ใหม่ (เช่น `GIT_SHA`) ไม่มีผลและ deploy ยังขึ้น `✅` (#111)

## [2.3.0] - 2026-10-31
### Added

- `GET /api/version` คืน `{"version": "...", "commit": "..."}` ของ backend ที่กำลังรัน (#110)
  โดยอ่าน commit จาก build arg `GIT_SHA` ไม่ใช่จาก `.git` ที่ไม่มีใน image
- แสดงเลขเวอร์ชันของแอปและ backend ไว้ท้ายหน้าตั้งค่า (#110)

### Changed

- เริ่มใช้ SemVer + `CHANGELOG.md` + git tag + GitHub Release เป็นมาตรฐานการปล่อยงาน (#110)
- `pull_all.sh` และ `setup.sh` ส่ง `GIT_SHA=${IMAGE_TAG}` เป็น build arg ตอน build backend (#110)
  (ชื่อ image ยังเป็น commit hash เหมือนเดิม)

### Added (เครื่องมือและเอกสาร)

- `release.sh <X.Y.Z>` — ตัด `[Unreleased]` ในไฟล์นี้เป็นเวอร์ชันใหม่, sync เลขเวอร์ชัน (#110)
  ทุกไฟล์, สร้าง annotated tag, push และสร้าง GitHub Release
- ไฟล์ `VERSION` ที่ root ของ repository (#110)
- บทความ `docs/4-developer-playbook/versioning-and-releases.md` (#110)

**Migration:** ไม่มี

## [2.2.0] - 2026-10-28

### Added

- ชุดคู่มือระบบ PIRIvoice 4 เล่ม แยกตามบทบาท ผู้ใช้ · เจ้าหน้าที่ · ผู้ดูแล · นักพัฒนา (#93)
- ฝังคู่มือบนเว็บที่ `/docs/` ด้วย VitePress และลบเลขนำหน้าชื่อภาพ (#94)
- ศูนย์ช่วยเหลือ PIRIvoice แยกคู่มือตามบทบาท (#97)
- ทางเข้า "คู่มือการใช้งาน" ในเมนูกลุ่มทั่วไป ชี้ไปเว็บ `/docs/` (#106)
- เขียนเล่ม 1 ใหม่ 10 บท พร้อมภาพประกอบและวงปุ่ม (#100)

### Changed

- ปรับหน้าตาคู่มือให้ตรงกับภาษาภาพของ PIRIvoice (#98)
- จัดหน้าเล่ม 1 ใหม่ให้สแกนง่ายใน 3 วินาที + เกลาสำนวนเป็นภาษารุ่นพี่ (#101)
- เกลาคำ "ระบบจะ" ที่ใช้ซ้ำให้อ่านลื่นขึ้น (#102)
- ปรับเล่ม 2–4 ให้เป็นมาตรฐานเดียวกับเล่ม 1 (#103)
- ใส่ภาพประกอบทุกขั้นตอนในทั้ง 3 เล่ม (#104)
- ย่อภาพหน้าจอให้เห็นทั้งภาพในจอเดียว (#107)
- ถอดศัพท์เทคนิคออกจากเล่ม 2 + เพิ่มภาคผนวกทางเทคนิค + เปลี่ยนป้ายเป็น "เปลี่ยนปลายทางเรื่อง" (#108)
- แคปใหม่ 2 ภาพที่ติดป้าย "เปลี่ยนผู้รับ" เดิม (#109)

### Fixed

- nginx เสิร์ฟคู่มือ `/docs/` ไม่ให้ตกไปที่ SPA (#95)
- service worker ไม่ให้หน้า `/docs/` ทับ app shell (#96)
- หน้า 404 ภาษาไทยบน staging (#99)
- เปลี่ยนชื่อไฟล์ภาพทางลัดหน้าแรก แก้ภาพแตกจาก cache (#105)

**Migration:** ไม่มี

## [2.1.1] - 2026-10-24

### Fixed

- `moved[].id` หลังย้ายกลับห้องเดิมชี้แถวที่ยัง active ไม่ใช่แถวประวัติ
  ทำให้เหลือศูนย์แถว active ในผลลัพธ์ (#92)

**Migration:** ไม่มี

## [2.1.0] - 2026-10-24

### Added

- ย้ายนักเรียนทั้งห้องพร้อมกันได้ในครั้งเดียว (#91)
- ปุ่มถอดนักเรียนออกจากห้อง โดยไม่ย้ายไปห้องอื่น (#91)

### Changed

- แถบปฏิบัติการย้ายห้องติดด้านล่าง ใช้แทนกล่องฟอร์มกลางจอ (#91)

**Migration:** ไม่มี

## [2.0.0] - 2026-10-21

### Added

- แกน "ปีการศึกษา" ระดับฐานข้อมูล + หน้าจัดการปีการศึกษา (P1) (#83)
- คอลัมน์ "ปีการศึกษา" ในไฟล์ Excel นำเข้า + unique index ของนักเรียนเพิ่มมิติปี (P3) (#85)
- เอนจินเลื่อนชั้นทั้งโรงเรียน + หน้า "เลื่อนชั้นนักเรียน" (P4) (#88)
- ย้ายห้อง + ประวัติการย้าย + มอบหมายเรื่องค้างอัตโนมัติ (P5) (#89)
- ผูกภาคเรียนกับปีการศึกษา + รายงานกระทบยอด + ค้นข้ามปี (P6) (#90)

### Fixed

- เส้นทาง "อ่าน" 7 จุดที่พังเงียบหลังขึ้นปีใหม่ + เทสต์ล็อกไว้ (P2) (#84)
- แยกคิว ARQ ของ import กับ push — เดิมแชร์คิวเดียวกันทำให้งานหายครึ่งโดย API ยังตอบ 200 (#86)

### Changed

- เอกสาร health-check ของ worker หลัง deploy — หายชั่วคราวเพราะ race ไม่ใช่ worker พัง (#87)

**Migration:** 027–029

## [1.24.0] - 2026-10-03

### Added

- เมนูลัดไประบบอื่นของโรงเรียน 2 ปลายทางบนหน้าแรก (#80)

### Changed

- ยุบบล็อกที่ว่างเหลือแถวเดียวจาก 1,125dp เหลือ 260dp (#81)
- เอกสารหลักฐานจาก staging จริงครบ 3 สภาพข้อมูล (#82)

**Migration:** ไม่มี

## [1.23.0] - 2026-10-01

เวอร์ชันนี้ทำงานบน `main` ตรง ไม่มี pull request

### Added

- ฟอร์มเสนอไอเดียเป็นหน้าเต็ม + FAB หลอดไฟ
- หน้าสแกนเช็คอินกิจกรรมเป็นกล้องเต็มจอ + แถบผลลัพธ์ที่จองที่ไว้
- การ์ดสถิติแดชบอร์ดแตะเพื่อกรองได้ + สีกราฟจาก token

### Changed

- จัดหน้า PIRI Boards ใหม่ — ตัดหัวซ้ำ + ชิปกรอง + การ์ดบรรทัดเดียว
- รวมหน้า "ทั้งหมด/จัดการ" ของกิจกรรมเป็นหน้าเดียว + แถวละ 1 ปุ่ม + เมนู ⋯
- หน้ารายชื่อผู้สมัครกิจกรรม — สรุปตัวเลขรวมกับชิปกรอง + ปุ่มย้อนถูกปลายทาง
- คำศัพท์ชุดเดียวทั้งแอป + รวมแผนที่ตำแหน่ง 4 ชุดเป็น 1
- ตัดหัวซ้ำ/ปุ่มย้อนซ้ำ 17 ไฟล์ + eyebrow อังกฤษตัวสุดท้าย
- รวมวันที่/เวลา 11 ก็อปใน 9 ไฟล์เข้าที่เดียว
- ย้ายสี "สำเร็จ" จาก emerald 7 เฉด → สเกล `ok-*` + ด่านกันกลับมา
- ถอดเส้นประออกจาก empty/error state 15 ไฟล์ → `AppEmptyState`
- ถอด daisyUI ออก + เพิ่มด่านกันสีแบรนด์ฮาร์ดโค้ด
- โฟกัสริงกลาง + `ink-3` ผ่าน AA + พื้นที่กด 44dp ทั้งแอป

### Fixed

- อักษรจีนหลุดในคอมเมนต์ของ `NewIssue.vue`
- แถบผล "เช็คอินสำเร็จ" ล้างตัวเองจริงใน 8 วินาที
- ปุ่ม action ในการ์ดคอมเมนต์และปุ่มล้าง datepicker เล็กกว่า 44dp
- ของล้นจอนอก 2 จุดที่ความกว้าง 360dp
- selector ที่เน่าไป 2 จุดจากการรัน e2e ครั้งแรก

**Migration:** ไม่มี

## [1.22.0] - 2026-10-01

### Added

- ฟอร์มแจ้งเรื่องเป็นตัวช่วยกรอก 3 ขั้น (R3.1) (#72)

### Changed

- หน้าแรก · หน้ารวมเรื่อง · รายละเอียดเรื่อง เปลี่ยนจากหน้าต้อนรับเป็น "งานของวันนี้" (#70)
- หน้าแจ้งเตือน 7 ชิป → 2 ชิป + จัดกลุ่มตามวัน (#74)
- แยกโปรไฟล์ออกจากหน้าตั้งค่า (#77)

### Fixed

- 2 ข้อที่เจอจากการตรวจตาและวัดจริงบน staging (#71)
- ชื่อขั้นใน stepper ถูกตัดเป็น "รายละ..." บนจอ 360dp (#73)
- แถวไม่ย้ำวันที่ที่หัวกลุ่มบอกไปแล้ว (#75)
- แถวในกลุ่ม "เมื่อวาน" เลิกย้ำคำเดียวกับหัวกลุ่ม (#76)
- ชื่อในหน้าโปรไฟล์ว่างเปล่าเมื่อไม่มี `first_name`/`last_name` (#78)

### Changed (เอกสาร)

- 3 บทเรียนรอบ 3 + แก้ข้อความที่อ้างกลไกผิด (#79)

**Migration:** ไม่มี

## [1.21.0] - 2026-10-01

### Changed

- R0 — design system + app shell ใหม่ (#65)
- รอบ 1 — ปรับ IA และเมนู รวมทางเข้าซ้ำ 3 → 1 + เทสต์กัน deep link ตก catch-all (#67)
- แก้ความเข้าใจผิดเรื่องชื่อหัวแถบของคู่ segment (#68)

### Fixed

- หัวกลุ่ม sticky ตาย + avatar เล็กกว่า 44dp ที่เจอตอนตรวจ staging (#66)

### Changed (เอกสาร)

- บทเรียนรอบ 0–1 สี่ข้อ (#69)

**Migration:** ไม่มี

## [1.20.0] - 2026-09-30

### Added

- ระบบกิจกรรม (D1) — สร้าง/เผยแพร่ · รับสมัคร + คิวสำรอง · แจ้งเตือนกลุ่ม event (#59)
- ระบบกิจกรรมรอบ D2 · D3 · D4 · 4.4 · 4.5 · A7 (#61)
- จำปลายทางไว้แล้วพาไปหลังล็อกอิน (#60)

### Changed

- popup ทั้งสองใบของระบบกิจกรรม → หน้าเต็มหน้า + date picker (#64)

### Fixed

- หนี้เอกสาร 3 รายการ — conftest กลืน exception · §8 ไม่ตรงสคีมา · ghost rules (#63)

### Changed (เอกสาร)

- 4 บทเรียนปิดรอบ #57 (#58) และ 8 บทเรียนปิดรอบ 4 (#62)

**Migration:** 025–026

## [1.19.0] - 2026-09-29

### Added

- Deep Link (A4) — กดแจ้งเตือนแล้วไปถึงเรื่อง/บอร์ดจริง (#55)
- Badge API (A5) · Quiet Hours (A8) · ประกาศฉุกเฉิน (E2) (#56)

### Fixed

- "เปิดใหม่บนเครื่องนี้" ล้มด้วย push service error เพราะปลายทางปฏิเสธหลังเพิ่ง unsubscribe (#57)
- ผูก subscription ใหม่หลังผู้ใช้เปลี่ยนเครื่อง (#56)

**Migration:** 023–024

## [1.18.0] - 2026-09-29

### Added

- กิจกรรมของฉัน (C1) + บันทึกไว้ (C2) (#53)
- ข้อเสนอแนะ (E1) — `board_type` `suggestion` + ฟอร์มสั้นจากผู้ใช้ทั่วไป (#54)

### Fixed

- บอร์ดที่ถูกซ่อนยังแสดงในรายการ (#53)

### Changed

- เปลี่ยนชื่อ repository เป็น `pirivoice` และเก็บชื่อ PRSC เดิมไว้เป็นประวัติ (#52)

**Migration:** 021–022

## [1.17.0] - 2026-09-29

### Added

- Badge ในแอปขยับทันทีด้วย Postgres `LISTEN/NOTIFY` + SSE (#50)

### Fixed

- sender exception ทำให้แถว outbox ค้างถาวร — จับที่ตัวห่อ task ไม่ใช่ตัวส่ง (#51)

**Migration:** 020

## [1.16.0] - 2026-09-29

### Added

- Web Push (A3) — แจ้งเตือนเด้งถึงมือถือแม้ปิดแอป ด้วย transactional outbox (#47)

### Fixed

- เพิ่ม `Urgency` header แก้ push มาช้า/กองทีเดียว (#48)
- คิวท่วมด้วยงานที่ทำไม่ได้ทำให้ของจริงถูกทิ้งเป็น stale — เพิ่มประตูที่ trigger และลูปส่งของตัวเอง (#49)

**Migration:** 018–019

## [1.15.0] - 2026-09-28

### Added

- ภาคเรียน (`academic_terms`) + หน้าจัดการ (#37)
- สถิติส่วนตัว 6 ตัวเลข กรองตามภาคเรียน (C3) (#38)
- หน้าแรกก้อนเดียวจบ + "รอฉันตอบ" + "โหวตที่ยังไม่โหวต" (B1) (#39)
- PWA ติดตั้งลงหน้าจอได้ + cache เฉพาะ app shell (A1) (#40)
- ตัววินิจฉัย "ทำไมติดตั้งไม่ได้" (#45)

### Fixed

- modal ถูกแถบเมนูล่างบัง · PWA ติดตั้งไม่ได้เพราะ CDN แคช HTML · ติดตั้งอัตโนมัติเมื่อแตะแรก (#44)
- เดสก์ท็อปไม่ต้องชวนติดตั้งแอป — เหลือชวนเฉพาะมือถือ (#46)

### Changed

- รวมงานที่ตกค้างจาก stack branch (#37–#40) กลับเข้า `main` (#42)

### Changed (เอกสาร)

- บทเรียนจากรอบที่ 1 — pool · เขตเวลา · nginx cache · SW precache · gate (#41)
- 2 บทเรียนจาก deploy staging — CDN cache + วิธีตรวจ static asset (#43)

> PR #37–#40 ถูก merge เข้า stack branch ก่อน แล้วจึงนำเข้า `main` ผ่าน #42
> ทั้งสี่รายการจึงปรากฏครั้งแรกในเวอร์ชันนี้

**Migration:** 017

## [1.14.0] - 2026-09-28

### Added

- ตั้งค่าการแจ้งเตือนรายกลุ่ม ปิด/เปิดได้ 4 กลุ่ม (#36)

### Changed (เอกสาร)

- บทเรียน `flex-1` (basis 0) + `shrink-0` กับข้อความบรรทัดละตัวบนจอแคบ (#34)
- ขอบเขตงานเพิ่ม PWA · ตั้งค่าการแจ้งเตือน · สถิติ · ภาคเรียน + แยก "Mobile App" ออกจาก "PWA" (#35)

**Migration:** 016

## [1.13.0] - 2026-09-28

### Added

- จัดการประกาศ (CRUD) + สิทธิ์ `MANAGE_ANNOUNCEMENTS` (#29)
- สถานะ "ปลดระวาง" ของประกาศ + หน้าแรกโชว์ประกาศทั้งหมด (#32)

### Changed

- ย้ายประกาศโรงเรียนขึ้นบนสุด + เมนูลัดก่อนสรุปเรื่องของฉัน (#31)

### Fixed

- มือถือตัวหนังสือขึ้นบรรทัดละตัวเพราะการ์ดประกาศถูกปุ่มบีบ (#33)

### Changed (เอกสาร)

- บทเรียนจากการ deploy staging — 405 จาก endpoint ที่ถอด · rollback ที่ใช้ไม่ได้ · migration รันยกชุด (#30)

**Migration:** 014–015

## [1.12.0] - 2026-09-26

เวอร์ชันนี้ทำงานบน `main` ตรง ไม่มี pull request

### Added

- หน้าบันทึกการใช้งานโชว์ห้อง ด้วย `LEFT JOIN rooms`

### Fixed

- `audit_logs` บันทึกครบทุกคอลัมน์ ไม่เว้นว่าง
- อ่าน `CF-Connecting-IP` ก่อน `X-Forwarded-For` — เดิมได้ `10.0.0.2` ทุกแถว

**Migration:** 013

## [1.11.0] - 2026-09-08

### Added

- ผู้ช่วยหัวหน้าระดับ + responsibilities + หน้า User Management (#25)
- เรื่องที่รับเลือกติ๊กระดับตามพีระมิด + avatar ใช้ตัวแรกของชื่อ (#28)

### Fixed

- แสดงสมาชิกตำแหน่งพิเศษที่ไม่ได้สังกัดห้อง (`room_id` เป็น NULL) (#26)
- ปลดล็อก `LIMIT 500` — ผู้จัดการ school-wide เห็นสมาชิกครบทั้งโรงเรียน (#27)

**Migration:** 011–012

## [1.10.0] - 2026-09-05

### Changed

- รวมทุกหน้าอยู่ใต้ Editorial & Civic design system (#24)

**Migration:** ไม่มี

## [1.9.0] - 2026-09-02

### Added

- `GET /api/issues/summary` — สรุปเรื่องที่ฉันแจ้ง (total + `by_status` 6 สถานะ + recent 5) สำหรับหน้า Home
- iOS-style app shell + หน้า Welcome/Home ที่ทุกบทบาทเข้าหน้าแรกกลาง (#22)

### Fixed

- ปรับโทนทุกหน้าสู่แบรนด์เดียว + แก้ responsive + เคลียร์ lint debt (#22)
- bottom bar ไม่ทับเนื้อหา + FAB เล็กลง + โทน iOS กลมกลืนทุกหน้า (#23)

**Migration:** ไม่มี

## [1.8.0] - 2026-09-02

เวอร์ชันนี้ทำงานบน `main` ตรง ไม่มี pull request

### Added

- Landing Page พร้อม Public API stats
- ปรับ Landing Page ตาม UX/UI feedback — navbar login · pyramid tier · mockup z-index · login-only page

### Fixed

- ปุ่ม login บนมือถือเป็นไอคอนกล่องเล็ก และแสดงข้อความตั้งแต่ `sm` ขึ้นไป

**Migration:** ไม่มี

## [1.7.0] - 2026-08-31

### Added

- P.R. Playbook — คู่มือสภานักเรียน E-book 6 เล่มแบบ Vertical Reader (#21)

**Migration:** ไม่มี

## [1.6.0] - 2026-08-31

### Added

- ระบบแจ้งเตือน + Unread Badge + Read-Receipts (Phase 7) (#20)

**Migration:** 010

## [1.5.0] - 2026-08-29

### Added

- PIRI Boards — ระบบโหวต + พูดคุยสาธารณะ 6 Phase พร้อม E2E และ moderation (#18)
- แก้ไขปลายทางของเรื่อง (`change_destination`) — หัวหน้าห้อง/สภาปรับ normal/vote/talk (#19)

**Migration:** 007–009

## [1.4.0] - 2026-08-27

### Added

- Dashboard สภานักเรียน + กราฟ Traffic + Audit Log เก็บทุก action (Phase 3) (#17)

**Migration:** 006

## [1.3.0] - 2026-08-27

### Added

- ระดับสูงกว่า (ประธานระดับ/สภา/แอดมิน) กดรับเรื่องแทนหัวหน้าห้องได้เลย (#16)

**Migration:** ไม่มี

## [1.2.0] - 2026-08-26

### Added

- ผู้แจ้งแก้ไขเรื่องได้ + คอมเมนต์แบบ YouTube (#14)
- หน้ารายการเรื่อง — pagination + ค้นหาแบบคำต่อคำ + ปุ่มกรอง/เรียงลำดับ (Phase 2) (#15)

**Migration:** 005

## [1.1.0] - 2026-08-23

### Added

- สถานะ "ถูกปัดตก" (rejected) — ผู้ดูแลปัดตกแยกจากผู้แจ้งยกเลิก (#13)

**Migration:** ไม่มี

## [1.0.0] - 2026-08-23

★ **Go-Live production**

เวอร์ชันนี้ทำงานบน `main` ตรง ไม่มี pull request

### Added

- favicon และไอคอนแอป

### Changed

- ปรับหน้า login หลายรอบจนเข้าที่
- ปรับฟอนต์ให้อ่านง่ายขึ้น

**Migration:** ไม่มี

## [0.6.0] - 2026-08-18

### Added

- สคริปต์เริ่มระบบปุ่มเดียวจบ (`setup.sh`) + Traefik ตัวกลาง 1 เครื่อง 1 อัน (#11)
- seed users admin/ครูสภาอัตโนมัติ (#9)
- `sitemap.xml` สำหรับ Google Search (#12)

### Changed

- ปรับ UX/UI มือถือ + รีดีไซน์โปรไฟล์แบบ Facebook (#9)
- หน้าโปรไฟล์ — ชื่ออยู่บนพื้นขาวอ่านง่ายเสมอ + การ์ดเดียว cover/ตัวตน (#10)

### Changed (เอกสาร)

- เอกสาร admin credentials และวิธีรีเซ็ตระบบใน readme (#10)

**Migration:** 004

## [0.5.0] - 2026-08-17

### Changed

- Rebrand PRSC Portal → PIRIvoice (เสียงจากชาวพิริยาลัย) + SEO keywords (#8)

**Migration:** ไม่มี

## [0.4.0] - 2026-08-17

### Added

- นำเข้านักเรียนจาก Excel แบบ queue ผ่าน ARQ Worker + ปิดช่องโหว่จาก review (#4)
- หน้าเว็บนำเข้านักเรียนจาก Excel — template + queue list + progress bar (#5)

### Fixed

- `init_db` รัน migrations ก่อนสร้าง index แก้ backend crash-loop บน staging + UX หน้า import (#6)
- import Excel ตัด `.0` ของรหัสนักเรียนที่เก็บเป็น float (`40000.0` → `40000`) (#7)

**Migration:** 003

## [0.3.0] - 2026-08-17

### Added

- Dashboard 3 หมวดหลัก + แก้ scope ครู + ทดสอบ 20/20 (#2)
- Dashboard แสดงข้อมูลละเอียด + ตัวกรองหมวดย่อย (#3)

**Migration:** ไม่มี

## [0.2.0] - 2026-08-16

### Changed

- รื้อหมวดหมู่เป็น 3 หมวดหลัก + RBAC ครูสภา/แอดมิน/ครูทั่วไปแบบ level-scoped (#1)

**Migration:** 001–002

## [0.1.0] - 2026-08-08

เวอร์ชันนี้ทำงานบน `main` ตรง ไม่มี pull request

### Added

- ตั้งโครง monorepo — backend FastAPI + frontend Vue 3 + Docker Compose
- ตั้งค่า `.env` และ build context ของ frontend/backend
- ตั้งโดเมนและ reverse proxy
- เตรียมนำเข้านักเรียนจาก Excel
- แก้บั๊ก add students

**Migration:** ไม่มี

[Unreleased]: https://github.com/singto1597/pirivoice/compare/v2.3.0...HEAD
[2.3.0]: https://github.com/singto1597/pirivoice/compare/v2.2.0...v2.3.0
[2.2.0]: https://github.com/singto1597/pirivoice/compare/v2.1.1...v2.2.0
[2.1.1]: https://github.com/singto1597/pirivoice/compare/v2.1.0...v2.1.1
[2.1.0]: https://github.com/singto1597/pirivoice/compare/v2.0.0...v2.1.0
[2.0.0]: https://github.com/singto1597/pirivoice/compare/v1.24.0...v2.0.0
[1.24.0]: https://github.com/singto1597/pirivoice/compare/v1.23.0...v1.24.0
[1.23.0]: https://github.com/singto1597/pirivoice/compare/v1.22.0...v1.23.0
[1.22.0]: https://github.com/singto1597/pirivoice/compare/v1.21.0...v1.22.0
[1.21.0]: https://github.com/singto1597/pirivoice/compare/v1.20.0...v1.21.0
[1.20.0]: https://github.com/singto1597/pirivoice/compare/v1.19.0...v1.20.0
[1.19.0]: https://github.com/singto1597/pirivoice/compare/v1.18.0...v1.19.0
[1.18.0]: https://github.com/singto1597/pirivoice/compare/v1.17.0...v1.18.0
[1.17.0]: https://github.com/singto1597/pirivoice/compare/v1.16.0...v1.17.0
[1.16.0]: https://github.com/singto1597/pirivoice/compare/v1.15.0...v1.16.0
[1.15.0]: https://github.com/singto1597/pirivoice/compare/v1.14.0...v1.15.0
[1.14.0]: https://github.com/singto1597/pirivoice/compare/v1.13.0...v1.14.0
[1.13.0]: https://github.com/singto1597/pirivoice/compare/v1.12.0...v1.13.0
[1.12.0]: https://github.com/singto1597/pirivoice/compare/v1.11.0...v1.12.0
[1.11.0]: https://github.com/singto1597/pirivoice/compare/v1.10.0...v1.11.0
[1.10.0]: https://github.com/singto1597/pirivoice/compare/v1.9.0...v1.10.0
[1.9.0]: https://github.com/singto1597/pirivoice/compare/v1.8.0...v1.9.0
[1.8.0]: https://github.com/singto1597/pirivoice/compare/v1.7.0...v1.8.0
[1.7.0]: https://github.com/singto1597/pirivoice/compare/v1.6.0...v1.7.0
[1.6.0]: https://github.com/singto1597/pirivoice/compare/v1.5.0...v1.6.0
[1.5.0]: https://github.com/singto1597/pirivoice/compare/v1.4.0...v1.5.0
[1.4.0]: https://github.com/singto1597/pirivoice/compare/v1.3.0...v1.4.0
[1.3.0]: https://github.com/singto1597/pirivoice/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/singto1597/pirivoice/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/singto1597/pirivoice/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/singto1597/pirivoice/compare/v0.6.0...v1.0.0
[0.6.0]: https://github.com/singto1597/pirivoice/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/singto1597/pirivoice/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/singto1597/pirivoice/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/singto1597/pirivoice/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/singto1597/pirivoice/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/singto1597/pirivoice/releases/tag/v0.1.0
