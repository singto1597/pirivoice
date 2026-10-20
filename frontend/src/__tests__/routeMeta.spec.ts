/**
 * 🧪 R0.0/R0.4 — สัญญา `route.meta` ของทั้งแอป
 *
 * **ทำไมต้องมีเทสนี้:** `menuItems` เดิมใน `MainLayout.vue` กรองสิทธิ์ด้วย `authStore` ตรง ๆ
 * แต่หลัง refactor **ประตูสิทธิ์ถูกย้ายไปอยู่ที่ `meta` ของ route** ซึ่งเป็นที่ที่ *มองไม่เห็น*
 * ⇒ ความผิดพลาดสองแบบที่เทสต์เท่านั้นจับได้:
 *
 *   1. **ถอด `requiresPermission` ออกโดยไม่มีใครรู้** — ผู้ใช้ที่ไม่มีสิทธิ์เห็นเมนูเพิ่มขึ้น
 *      แล้วเจอ 403 กลางทาง (หรือแย่กว่านั้นคือเห็นข้อมูลที่ไม่ควรเห็น)
 *   2. **เพิ่ม `requiresPermission` เข้า route ที่ไม่ควรมี** — ผู้ใช้ที่มีสิทธิ์จริงถูกดีดกลับ
 *      **เงียบ ๆ** โดยไม่มีข้อความ ⇒ หน้าที่ทำงานได้กลับพัง ซึ่งแย่กว่าข้อ 1
 *      ⚠️ `received-issues` คือเคสจริงข้อนี้ — ดู `R0.3.3`
 *
 * ⭐ **สิ่งที่เทสนี้ยึด:**
 *   - **gate ทั้ง 32 route** (snapshot ตรง ๆ) ⇒ เปลี่ยนที่ไหน เทสต์แดงที่นั่น
 *   - `received-issues` **ห้ามมี** `requiresPermission` โดยเจตนา
 *   - **ห้ามประกาศ `navTab`/`fab` ที่ route แม่ `/app`** — `route.meta` เป็นการ merge ของ
 *     ทุก record ที่ match ⇒ ค่าที่แม่จะ **รั่วลงทุกหน้าลูก** แล้วแท็บจะสว่างผิดทั้งแอป
 *   - ทุก route ลูกมี `navTab` (ไม่งั้นแถบล่างไม่รู้จะไฮไลต์อะไร)
 *   - ทุก route มีชื่อไทยใน `routeTitles` (ไม่งั้นหัวแถบขึ้น "PIRIvoice" เฉย ๆ)
 *   - `headerBack` ทุกตัวชี้ไป route ที่ **resolve ได้จริง** (ไม่ใช่ทางตัน)
 */
import { describe, expect, it } from 'vitest'
import type { RouteRecordRaw } from 'vue-router'
import router from '@/router'
import { routeTitles } from '@/constants/nav'

/** ลูกทุกตัวของ `/app` — ต้นทางเดียวของทุกการตรวจในไฟล์นี้ */
function appChildren(): RouteRecordRaw[] {
  const app = router.options.routes.find((r) => r.path === '/app')
  if (!app?.children) throw new Error('ไม่พบ route แม่ "/app" หรือไม่มี children')
  return app.children
}

function nameOfRoute(r: RouteRecordRaw): string {
  if (typeof r.name !== 'string') throw new Error(`route "${r.path}" ไม่มีชื่อที่เป็น string`)
  return r.name
}

/**
 * 🔒 Snapshot ของประตูสิทธิ์ — [requiresAuth, requiresPermission, requiresCouncil]
 *
 * ⚠️ `requiresAuth` ที่เป็น `undefined` ไม่ได้แปลว่า "ไม่ต้องล็อกอิน" — ลูกของ `/app`
 *    สืบทอดจาก route แม่ ⇒ ค่าเหล่านี้คือ *สิ่งที่ประกาศไว้ที่ตัว record* ซึ่งเป็นสิ่งที่
 *    เทสต์นี้ต้องการจับ (การเปลี่ยนที่ตัว record) ไม่ใช่ผลลัพธ์ตอน runtime
 */
const GATES: Record<string, [boolean | undefined, string | undefined, boolean | undefined]> = {
  home: [true, undefined, undefined],
  // 🗂️ แท็บที่ 5 (R1) — หนึ่งในสอง route ที่เพิ่มใหม่ทั้ง refactor · ไม่มี gate เพิ่มโดยเจตนา
  //    (เมนูข้างในกรองสิทธิ์ที่ `useNavItems` อยู่แล้ว ⇒ ไม่ต้องมีประตูสองชั้น)
  more: [true, undefined, undefined],
  dashboard: [true, 'VIEW_DASHBOARD', undefined],
  profile: [undefined, undefined, undefined],
  // ⚙️ R3.3 — หน้าที่ 2 (และตัวสุดท้าย) ที่เพิ่มใหม่ทั้ง refactor
  //    🔴 **ไม่ใส่ gate โดยเจตนา** — หน้านี้เป็น "การตั้งค่าของตัวเอง" ล้วน
  //       (กลุ่มแจ้งเตือน/push ของ *ผู้ใช้คนนั้น*) ซึ่ง backend เอา `user_id` จาก JWT
  //       อยู่แล้ว ⇒ ประตูฝั่ง frontend เป็นได้แค่ UX และ gate ที่ผิดจะดีดผู้ใช้กลับเงียบ ๆ
  //       ⚠️ `academic-terms` (`MANAGE_SETTINGS`) **คนละเรื่องกันโดยสิ้นเชิง** — นั่นคือ
  //          "ตั้งค่า *ของโรงเรียน*" ที่แก้แล้วกระทบทุกคน · อย่าเผลอคัดลอก gate กัน
  settings: [undefined, undefined, undefined],
  'my-activity': [undefined, undefined, undefined],
  'profile-edit': [undefined, undefined, undefined],
  'profile-password': [undefined, undefined, undefined],
  'new-issue': [undefined, undefined, undefined],
  'my-issues': [undefined, undefined, undefined],
  'received-issues': [undefined, undefined, undefined],
  'issue-detail': [undefined, undefined, undefined],
  'issue-edit': [undefined, undefined, undefined],
  boards: [undefined, undefined, undefined],
  'board-reports': [true, undefined, true],
  'board-detail': [undefined, undefined, undefined],
  // 💡 รอบ 4 — หน้าที่ 3 ที่เพิ่มใหม่ทั้ง refactor (ฟอร์มเสนอไอเดีย แทน modal เดิม)
  //    🔴 **ไม่ใส่ gate โดยเจตนา** — ข้อเสนอแนะเปิดให้ทุกคนส่ง ไม่ต้องรอสภาอนุมัติ
  //       ⇒ การใส่ gate ที่นี่ = ดีดผู้ใช้ทั่วไปกลับหน้าแรก *เงียบ ๆ* จากปุ่มที่ควรกดได้
  'board-new': [undefined, undefined, undefined],
  events: [true, undefined, undefined],
  'event-management': [true, 'MANAGE_EVENTS', undefined],
  'event-create': [true, 'MANAGE_EVENTS', undefined],
  'event-detail': [true, undefined, undefined],
  'event-edit': [true, 'MANAGE_EVENTS', undefined],
  'event-registrations': [true, 'MANAGE_EVENTS', undefined],
  'event-check-in': [true, 'MANAGE_EVENTS', undefined],
  playbooks: [true, undefined, undefined],
  'playbook-reader': [true, undefined, undefined],
  notifications: [true, undefined, undefined],
  users: [true, 'MANAGE_STUDENTS', undefined],
  students: [true, 'MANAGE_STUDENTS', undefined],
  'import-students': [true, 'MANAGE_STUDENTS', undefined],
  announcements: [true, 'MANAGE_ANNOUNCEMENTS', undefined],
  'academic-terms': [true, 'MANAGE_SETTINGS', undefined],
  // 🎓 ปีการศึกษา — ใช้ `MANAGE_SETTINGS` **ไม่ใช่ `MANAGE_STUDENTS`** โดยเจตนา:
  //    "เปลี่ยนปีปัจจุบัน" เปลี่ยน DEFAULT ของ `students.academic_year_id` ⇒ สมาชิกที่
  //    สร้างหลังจากนั้นไปอยู่ปีใหม่ทั้งหมด · ครูระดับชั้น (ที่มี `MANAGE_STUDENTS`)
  //    ต้องแตะไม่ได้ — ตรงกับ `PERMISSION` ใน `services/year_service.py`
  'academic-years': [true, 'MANAGE_SETTINGS', undefined],
  // 🔄 เลื่อนชั้นทั้งโรงเรียน — **สองประตูคู่กัน ไม่ใช่ของซ้ำ**:
  //    `MANAGE_STUDENTS` เดี่ยว → ครู/ประธานระดับเห็นแถวแล้ว 403 (backend บังคับโหมด
  //    จัดการระดับโรงเรียน = ต้องมี `is_admin`) · `requiresCouncil` เดี่ยว →
  //    `council_member` เห็นแล้วก็ 403 (ไม่มี MANAGE_STUDENTS)
  //    ⇒ คู่กันให้ผลตรงกับ `rollover_service._gate` ทุกบทบาท
  'promote-students': [true, 'MANAGE_STUDENTS', true],
  'academic-year-new': [true, 'MANAGE_SETTINGS', undefined],
  'academic-year-edit': [true, 'MANAGE_SETTINGS', undefined],
  'audit-logs': [true, 'VIEW_AUDIT_LOG', undefined],
}

/** หน้าที่ซ่อนแถบล่าง — **ฟอร์ม / สแกนเนอร์ / นำเข้า เท่านั้น** (ไม่ใช่หน้ารายละเอียด) */
const NAV_HIDDEN = [
  'new-issue',
  'issue-edit',
  'event-create',
  'event-edit',
  'event-registrations',
  'event-check-in',
  'profile-edit',
  'profile-password',
  'import-students',
  // ✍️ รอบ 4 — ฟอร์มเสนอไอเดีย (แทน `QuickSuggestionModal` ที่กดฉากหลังแล้วทิ้งข้อความ)
  'board-new',
  // 🎓 ปีการศึกษา — ฟอร์มเป็น **หน้าเต็ม** ตาม skills.md #16 (ห้ามใส่ฟอร์มในแผ่นเลื่อน)
  //    ⇒ ไม่มีแถบล่างไฮไลต์ ⇒ ต้อง `navHidden` (หน้ารายการ `academic-years` ยังเห็นแถบปกติ)
  'academic-year-new',
  'academic-year-edit',
]

/** แท็บราก — ต้องมี `headerBack: false` ไม่งั้นได้ลูกศร ← ที่กดแล้วกลับหน้าเดิม */
const TAB_ROOTS = ['home', 'more', 'my-issues', 'boards', 'events']

describe('ประตูสิทธิ์ (snapshot)', () => {
  it('ครบทั้ง 37 route และตรงกับที่ประกาศไว้ทุกตัว', () => {
    const children = appChildren()
    expect(children).toHaveLength(37)

    const actual: Record<string, [boolean | undefined, string | undefined, boolean | undefined]> =
      {}
    for (const child of children) {
      const m = child.meta ?? {}
      actual[nameOfRoute(child)] = [m.requiresAuth, m.requiresPermission, m.requiresCouncil]
    }

    expect(actual).toEqual(GATES)
  })

  it('🔴 `received-issues` ต้อง **ไม่มี** `requiresPermission` (R0.3.3)', () => {
    const child = appChildren().find((r) => r.name === 'received-issues')
    expect(child).toBeDefined()

    // `students.permissions` เป็น snapshot column ที่ไม่มีอะไร re-sync ⇒ ถ้า gate ที่ route
    // ผู้ใช้ที่มีสิทธิ์รับเรื่องจริงแต่ snapshot ตกหล่นจะถูกดีดกลับ *เงียบ ๆ* = หน้าที่ทำงานได้กลับพัง
    // ⇒ การกรองอยู่ที่ `useNavItems.segmentsOf()` ซึ่งอ่าน auth store สดแทน
    expect(child?.meta?.requiresPermission).toBeUndefined()
    expect(child?.meta?.requiresCouncil).toBeUndefined()
  })

  it('ไม่มี route ไหนได้ `requiresPermission` ที่ไม่ใช่รหัสที่ระบบรู้จัก', () => {
    const known = new Set(
      Object.values(GATES)
        .map(([, perm]) => perm)
        .filter((p): p is string => Boolean(p)),
    )
    const unknown = appChildren()
      .map((c) => ({ route: nameOfRoute(c), perm: c.meta?.requiresPermission }))
      .filter((x) => x.perm !== undefined && !known.has(x.perm))
      .map((x) => `${x.route} → "${x.perm}"`)

    expect(unknown).toEqual([])
  })
})

describe('chrome — shell อ่านจาก meta ที่เดียว', () => {
  it('🔴 route แม่ `/app` **ห้าม** ประกาศ navTab/fab (จะรั่วลงทุกหน้าลูก)', () => {
    const app = router.options.routes.find((r) => r.path === '/app')
    expect(app?.meta?.navTab).toBeUndefined()
    expect(app?.meta?.fab).toBeUndefined()
    expect(app?.meta?.segmentGroup).toBeUndefined()
    expect(app?.meta?.navHidden).toBeUndefined()
    expect(app?.meta?.headerBack).toBeUndefined()
    // ที่แม่ใส่ได้มีอย่างเดียว
    expect(app?.meta?.requiresAuth).toBe(true)
  })

  it('ทุก route ลูกประกาศ `navTab`', () => {
    const missing = appChildren()
      .filter((c) => c.meta?.navTab === undefined)
      .map(nameOfRoute)
    expect(missing).toEqual([])
  })

  it('`navHidden` มีเฉพาะฟอร์ม/สแกน/นำเข้า — หน้ารายละเอียดต้องเห็นแถบ', () => {
    const hidden = appChildren()
      .filter((r) => r.meta?.navHidden === true)
      .map(nameOfRoute)
      .sort()

    expect(hidden).toEqual([...NAV_HIDDEN].sort())

    // ⚠️ ปลายทางของ push notification ต้องเหลือทางออกมากกว่าลูกศร ← เดียว
    //    และแถบที่ซ่อนอยู่ไฮไลต์แท็บแม่ไม่ได้ ⇒ ขัดกับ "หน้าย่อยต้องสว่างที่แท็บแม่"
    const detailHidden = ['issue-detail', 'event-detail', 'board-detail'].filter(
      (name) => appChildren().find((r) => r.name === name)?.meta?.navHidden === true,
    )
    expect(detailHidden).toEqual([])
  })

  it('`headerHidden` มีเฉพาะสแกนเนอร์เต็มจอ', () => {
    const hidden = appChildren()
      .filter((r) => r.meta?.headerHidden === true)
      .map(nameOfRoute)

    expect(hidden).toEqual(['event-check-in'])
  })

  it('แท็บรากทุกตัวมี `headerBack: false`', () => {
    // ถ้าไม่ประกาศ `useAppChrome` จะตกไปใช้ fallback "รากของแท็บตัวเอง"
    // ⇒ ได้ลูกศร ← ที่กดแล้วกลับไปหน้าเดิม (ดู `useAppChrome.ts`)
    const missing = TAB_ROOTS.filter(
      (name) => appChildren().find((r) => r.name === name)?.meta?.headerBack !== false,
    )
    expect(missing).toEqual([])
  })

  it('`headerBack` ที่เป็น route target ทุกตัว resolve ได้จริง (ไม่มีทางตัน)', () => {
    const targets = appChildren()
      .map((r) => ({ from: nameOfRoute(r), back: r.meta?.headerBack }))
      .filter((x): x is { from: string; back: { name: string } } =>
        Boolean(x.back && typeof x.back === 'object'),
      )

    expect(targets.length).toBeGreaterThan(0)

    const dead = targets
      .filter((t) => router.resolve(t.back).name !== t.back.name)
      .map((t) => `${t.from} → ${t.back.name}`)
    expect(dead).toEqual([])

    // ⚠️ ห้ามใช้ `'history'`/`router.back()` หรือ path ดิบ — ทางเข้าหลักของหน้ารายละเอียด
    //    คือ push notification และการสแกน QR ซึ่ง **ไม่มี in-app history**
    //    ⇒ `back()` จะเตะผู้ใช้ออกจากแอป · สัญญาคือ "route target ที่มีชื่อ" หรือ `false`
    //    (แท็บรากใช้ `false` = ตั้งใจไม่มีลูกศร ไม่ใช่ค่าที่ผิดสัญญา)
    const notNamed = appChildren()
      .filter((c) => {
        const back = c.meta?.headerBack
        return back !== undefined && back !== false && typeof back !== 'object'
      })
      .map(nameOfRoute)
    expect(notNamed).toEqual([])
  })

  it('คู่ segment ประกาศตรงกันทั้งสองฝั่ง', () => {
    const byGroup: Record<string, string[]> = {}
    for (const child of appChildren()) {
      const g = child.meta?.segmentGroup
      if (!g) continue
      byGroup[g] = [...(byGroup[g] ?? []), nameOfRoute(child)].sort()
    }

    expect(byGroup).toEqual({
      issues: ['my-issues', 'received-issues'],
      members: ['students', 'users'],
      // 📅 รอบ 4 — "ทั้งหมด / จัดการ" รวมเป็นหน้าเดียว (path เดิมทั้งคู่ ไม่มี route แม่ + redirect)
      //    ⚠️ แผน R4.2 เขียนไว้สามตัวรวม "ของฉัน" — **ถอดออกโดยเจตนา** เพราะไม่มีแหล่งข้อมูล
      //       (เหตุผลเต็มอยู่ใน `constants/nav.ts` หัว `EVENT_SEGMENTS`) ⇒ ถ้ามีใครเพิ่ม
      //       segment ที่สองกลับเข้ามาโดยไม่มี endpoint รองรับ เทสต์นี้จะเตือนที่บรรทัดนี้
      events: ['event-management', 'events'],
    })
  })

  it('`fab` ประกาศเฉพาะหน้าที่มีปุ่มลอย', () => {
    const fabs: Record<string, string[]> = {}
    for (const child of appChildren()) {
      const f = child.meta?.fab
      if (!f) continue
      fabs[f] = [...(fabs[f] ?? []), nameOfRoute(child)].sort()
    }

    expect(fabs).toEqual({
      issue: ['home', 'my-issues'],
      event: ['event-management', 'events'],
      member: ['students', 'users'],
      // ➕ รอบ 4 — "เสนอไอเดีย" บนแท็บบอร์ด (ไม่มี permission ⇒ ทุกคนเห็น)
      board: ['boards'],
    })
  })
})

describe('ชื่อหน้า', () => {
  it('ทุก route ลูกมีชื่อใน `routeTitles` — ไม่มีหน้าไหนขึ้น "PIRIvoice" เฉย ๆ', () => {
    const missing = appChildren()
      .map(nameOfRoute)
      .filter((n) => !routeTitles[n])
    expect(missing).toEqual([])
  })

  it('ชื่อหน้าต้องไม่มีอักขระละตินนำ (คำอังกฤษที่ผู้ใช้อ่านไม่ออกว่าคืออะไร)', () => {
    const latin = appChildren()
      .map(nameOfRoute)
      .filter((n) => /^[A-Za-z]/.test(routeTitles[n] ?? ''))
    expect(latin).toEqual([])
  })
})
