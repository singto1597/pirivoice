# คู่มือนักพัฒนา

เล่มนี้เป็นแผนที่ของโค้ด PIRIvoice สำหรับผู้ที่จะแก้ระบบต่อ
ทุกบทชี้ไฟล์จริงที่ใช้ตัดสินพฤติกรรม ไม่ใช่สรุปจากความจำ
ถ้าเอกสารกับโค้ดขัดกัน ให้ยึดโค้ด แล้วอ่าน [ข้อขัดแย้งระหว่างเอกสารเดิมกับโค้ด](known-discrepancies.md)

## ใครใช้เล่มนี้

- นักพัฒนาที่เพิ่งเข้าร่วมโปรเจกต์ และต้องรันระบบบนเครื่องตัวเองได้
- ผู้ดูแลระบบเทคนิคที่ต้อง deploy กู้คืน หรือตรวจสุขภาพระบบ
- ผู้ที่ต้องแก้เอกสารเดิมใน `docs/` ให้ตรงกับโค้ด

เล่มนี้ใช้คำเทคนิคภาษาอังกฤษตามที่โค้ดใช้ เช่น `service`, `router`, `pool`, `transaction`
ต่างจากเล่ม 1–3 ที่ใช้ภาษาไทยเป็นหลัก

## อ่านบทไหน

| ถ้าต้องการ... | อ่านบท |
|---|---|
| เข้าใจว่า request วิ่งผ่านชั้นใด และทำไมห้ามเขียน SQL ใน router | [สถาปัตยกรรมภายใน](architecture-internals.md) |
| เพิ่มหรือแก้อุปกรณ์ยืนยันตัวตน สิทธิ์ และขอบเขตข้อมูล | [การยืนยันตัวตนและสิทธิ์](auth-and-rbac.md) |
| รู้ว่าตารางใดมีคอลัมน์ใด และ index ใดห้ามลบ | [โครงสร้างฐานข้อมูล](database-schema.md) |
| เรียก endpoint หรือตรวจว่า endpoint หนึ่งต้องมีสิทธิ์ใด | [API Reference](api-reference.md) |
| เข้าใจคิว import, push, quiet hours และ SSE | [งานเบื้องหลัง การแจ้งเตือน และ push](background-jobs-and-push.md) |
| สร้างหน้าจอใหม่ให้เข้ากับระบบเดิม | [มาตรฐาน UI/UX](ui-ux-design-standards.md) |
| ตรวจว่าการแก้โค้ดผ่านกฎของโปรเจกต์ | [มาตรฐานการเขียนโค้ด](coding-standards-rules.md) |
| รันเทสต์ สร้าง image และ deploy | [การทดสอบและการนำขึ้นระบบ](testing-and-deployment.md) |
| รู้ว่าเอกสารเดิมผิดตรงไหน | [ข้อขัดแย้งระหว่างเอกสารเดิมกับโค้ด](known-discrepancies.md) |

## ก่อนแก้โค้ดอะไรก็ตาม

1. อ่าน [docs/skills.md](../skills.md) ส่วนที่เกี่ยวกับโมดูลนั้น ก่อนลงมือ
2. อ่านกฎชั้นที่กำลังแก้ ใน [docs/rules/](../rules/) และ [docs/system_prompt.md](../system_prompt.md)
3. เปิดไฟล์จริงที่บทนั้นอ้างถึง ไม่ใช่เชื่อข้อความในคู่มือนี้อย่างเดียว
4. รันชุดตรวจตาม [การทดสอบและการนำขึ้นระบบ](testing-and-deployment.md) ให้ครบก่อนคอมมิต

`docs/skills.md` เป็นบันทึกบทเรียนที่เคยแก้มาแล้ว ไม่ใช่คู่มือเริ่มต้น
ถ้าพบพฤติกรรมใหม่ที่คนอื่นจะเจอซ้ำ ให้เพิ่มบันทึกตามรูปแบบในไฟล์นั้น

## แผนที่โค้ดย่อ

```
backend/
  main.py             สร้าง pool, init_db, seed, เปิด SSE hub, middleware, mount router
  core/               config · rbac · dependencies · logger · init_db · queues
  routers/            HTTP ชั้นบาง 16 ไฟล์
  services/           business logic + raw SQL 21 ไฟล์
  models/             Pydantic schema 17 ไฟล์
  workers/            ARQ import worker และ push worker
  migrations/         001–029
  tests/              pytest integration tests
frontend/src/
  views/              หน้าจอตามโดเมน
  services/           เรียก API ผ่าน api.ts
  components/ui/      design system
  components/layout/  shell ของแอป
  constants/          nav · roles · status · brand · chart
  composables/        useNavItems · useAppChrome · useIdentity · useMediaQuery
  stores/             Pinia auth และ notifications
  router/             route + guard
```

## คำที่ใช้ในเล่มนี้

| คำ | ความหมายในระบบนี้ |
|---|---|
| `pool` | `asyncpg.Pool` ที่ router ส่งต่อให้ service |
| `conn` | connection ที่ยืมจาก pool ระหว่างคำขอหนึ่ง |
| `scope` | ขอบเขตข้อมูลของผู้ใช้ ได้แก่ `super` `all` `level` `none` `pyramid` |
| `audit action` | รหัสการกระทำที่บันทึกลง `audit_logs` เช่น `UPDATE_STUDENT` |
| outbox | ตาราง `push_outbox` ที่กันแจ้งเตือนหายเมื่อ worker ล่ม |
| soft delete | ตั้ง `deleted_at` แทนการลบแถว |

## แก้ไขปัญหาและคำถามที่พบบ่อย

**ถาม: จะเริ่มอ่านโค้ดจากไฟล์ไหน**
ตอบ: เริ่มที่ `backend/main.py` เพื่อดู lifespan และ router ที่ mount ไว้
จากนั้นเปิด `routers/issue_router.py` คู่กับ `services/issue_service.py` เพราะเป็นเส้นทางที่ครอบคลุมแพตเทิร์นส่วนใหญ่

**ถาม: ทำไมรัน backend บนเครื่องแล้วเชื่อมฐานข้อมูลไม่ได้**
ตอบ: ค่า `DATABASE_URL` อ่านจาก `.env` ที่ root ของโปรเจกต์
ถ้ารันในคอนเทนเนอร์ ให้ใช้ชื่อ service ของฐานข้อมูล ไม่ใช่ `localhost`

**ถาม: จะรู้ได้อย่างไรว่า endpoint ต้องมีสิทธิ์ใด**
ตอบ: เปิด router ของ endpoint นั้น แล้วดูว่าเรียก service ใด จากนั้นเปิด service และหา `require_permission` หรือ `require_permission_anywhere`
ตารางสรุปอยู่ใน [API Reference](api-reference.md) และ [การยืนยันตัวตนและสิทธิ์](auth-and-rbac.md)

**ถาม: แก้เอกสารเดิมใน `docs/` ได้ไหม**
ตอบ: ได้ แต่คู่มือชุดนี้ไม่แก้ไฟล์เดิม
ถ้าเจอข้อความที่ขัดกับโค้ด ให้เพิ่มแถวใน [ข้อขัดแย้งระหว่างเอกสารเดิมกับโค้ด](known-discrepancies.md) พร้อมหลักฐาน แล้วจึงแก้ไฟล์เดิมในรอบแยก

**ถาม: ต้องรันอะไรก่อนคอมมิต**
ตอบ: backend รัน pytest ทั้งชุด ส่วน frontend รัน `type-check` `lint` `test:unit` และ `build` ให้ครบทั้งสี่
รายละเอียดและคำสั่งเต็มอยู่ใน [การทดสอบและการนำขึ้นระบบ](testing-and-deployment.md)

**ถาม: ระบบนี้มี CI หรือไม่**
ตอบ: ไม่มี pipeline อัตโนมัติบน GitHub
ด่านทั้งหมดรันบนเครื่องก่อน push และ deploy ทำด้วยสคริปต์ที่ root ของ repo
