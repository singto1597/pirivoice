/**
 * 🧪 R0.0 · "NAV_REGISTRY ต้องสร้างเมนูของวันนี้ได้ครบทุกปลายทาง"
 *
 * **ทำไมต้องมีเทสนี้ตอนที่ยังไม่มีใครอ่าน registry:**
 * `constants/nav.ts` ถูกสร้างมาแทน `menuItems` ใน `MainLayout.vue` (13 แถวเรียงตามเงื่อนไข)
 * แต่ **R0 ยังไม่เปลี่ยน UI** ⇒ ถ้าข้อมูลใน registry ตกหล่นไปแถวหนึ่ง จะไม่มีอาการให้เห็นเลย
 * จนถึง R1 ที่เอา UI เก่าออกพร้อมกัน — แล้วความผิดพลาดนั้นจะโผล่เป็น *"เมนูหาย"*
 * บนเครื่องผู้ใช้จริง ซึ่งเป็นคลาสของบั๊กที่หายากและหายากมากที่จะมีใครแจ้ง
 *
 * ⭐ **สิ่งที่เทสนี้ยึด (เรียงตามความสำคัญ):**
 *   1. **ครบทุกปลายทาง** — ทุกแถวที่วันนี้เข้าถึงได้ ต้องยังเข้าถึงได้ *ผ่านช่องทางที่ประกาศไว้*
 *      (แท็บ / เมนู / segment / FAB) ⇒ จับ "ของหาย" ได้ทุกจุดที่เพิ่มหรือลบรายการในอนาคต
 *   2. **ประตูสิทธิ์ไม่ขยับ** — ปลายทางที่ต้องมีสิทธิ์ ต้องยังต้องมีสิทธิ์ (และกลับกัน)
 *      ⇒ จับ `requiresPermission` ที่เผลอถูกถอด ซึ่ง **มองไม่เห็นจาก UI** เพราะผู้ใช้แค่เห็นเมนูเพิ่ม
 *   3. **badge ของแท็บ "เรื่อง" ไม่บวกสองกลุ่ม** — ข้อที่พังง่ายที่สุดของการย้าย badge
 *      จาก `menuBadge(path)` มาเป็น `badgeGroup` บนตัวรายการ
 *
 * ⚠️ **mock เฉพาะ `useRoute`/`useRouter`** ส่วน Pinia ใช้ของจริง ⇒ `hasPermission` /
 *    `isCouncilAuthority` ที่เทสนี้ยึด เป็นตัวเดียวกับที่แอปใช้จริง ไม่ใช่ของจำลอง
 *    (แยกจาก `routeMeta.spec.ts` ที่ตรวจ `meta` ของ router จริง)
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { reactive } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import type { RouteLocationRaw } from 'vue-router'
import type { AuthUser, UserRoleInfo } from '@/types/auth'
import type { NavKey } from '@/router/meta'

const mocks = vi.hoisted(() => ({
  /**
   * route ปัจจุบัน — เทสสลับ `name` ได้ เพื่อตรวจว่า badge ของแท็บ "เรื่อง"
   * เปลี่ยนตาม segment ที่เปิดอยู่จริง
   */
  route: { current: { name: 'home', path: '/app/home', meta: {} } as Record<string, unknown> },
  resolve: vi.fn<(to: RouteLocationRaw) => { path: string }>(() => ({ path: '/' })),
}))

vi.mock('vue-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('vue-router')>()
  return {
    ...actual,
    useRoute: () => mocks.route.current,
    useRouter: () => ({
      resolve: mocks.resolve,
      push: vi.fn<(to: RouteLocationRaw) => Promise<void>>(),
    }),
  }
})

import { useAuthStore } from '@/stores/auth'
import { useNotificationsStore } from '@/stores/notifications'
import { useNavItems } from '@/composables/useNavItems'
import { NAV_TABS, NAV_GROUPS } from '@/constants/nav'
import type { NavTab } from '@/constants/nav'

// ─────────────────────────────────────────────────────────────────────────────
// 🔐 จำลองผู้ใช้
// ─────────────────────────────────────────────────────────────────────────────

interface Profile {
  permissions?: string[]
  isAdmin?: boolean
  council?: boolean
}

/** เข้าสู่ระบบด้วยโปรไฟล์ที่กำหนด — คืน auth store ให้เทสปรับต่อได้ */
function signIn(opts: Profile = {}) {
  const auth = useAuthStore()
  const councilRole: UserRoleInfo = {
    role: 'council_president',
    room_id: null,
    room_name: null,
    student_no: null,
    first_name: null,
    level: null,
    staff_level: null,
    is_admin: false,
    permissions: [],
    responsibilities: [],
  }
  const user: AuthUser = {
    id: 1,
    username: 'tester',
    full_name: 'ผู้ใช้ทดสอบ',
    first_name: 'ผู้ใช้',
    is_admin: opts.isAdmin ?? false,
    permissions: opts.permissions ?? [],
    must_change_password: false,
    roles: opts.council ? [councilRole] : [],
  }
  auth.user = user
  return auth
}

function tabOf(key: NavKey): NavTab {
  const tab = NAV_TABS.find((t) => t.key === key)
  if (!tab) throw new Error(`ไม่พบแท็บ "${key}" ใน NAV_TABS`)
  return tab
}

/** ชื่อ route ของรายการเมนู — ทุกรายการที่ "ไปหน้าใหม่" ประกาศเป็น `{ name }` เท่านั้น */
function nameOf(to: RouteLocationRaw | undefined): string | null {
  if (!to || typeof to !== 'object' || !('name' in to)) return null
  return typeof to.name === 'string' ? to.name : null
}

/**
 * ย้าย "route ปัจจุบัน" ไปหน้าอื่น
 *
 * 🔴 **ต้อง `reactive` แล้วแก้ฟิลด์ในที่ ไม่ใช่สร้าง object ใหม่** — `useNavItems()`
 *    เรียก `useRoute()` ครั้งเดียวตอน setup แล้ว **ถือ reference ไว้** ⇒ ถ้าเทสสร้าง
 *    object ใหม่ ค่าที่ composable เห็นจะยังเป็นตัวเก่า และ `computed` ก็ไม่มีเหตุให้
 *    คำนวณใหม่ (จะได้ผลของหน้าแรกค้างอยู่ตลอด) = เทสผ่านทั้งที่ของพัง
 */
function goto(name: string, path: string): void {
  const r = mocks.route.current
  r.name = name
  r.path = path
}

beforeEach(() => {
  setActivePinia(createPinia())
  localStorage.clear()
  mocks.route.current = reactive({ name: 'home', path: '/app/home', meta: {} })
  mocks.resolve.mockReturnValue({ path: '/' })
})

// ─────────────────────────────────────────────────────────────────────────────
// 🗺️ fixture = เมนูของ "วันนี้" (MainLayout.vue:163-249) + ปลายทางที่ R1 เพิ่ม
// ─────────────────────────────────────────────────────────────────────────────

/**
 * `reach` = ช่องทางเดียวที่ปลายทางนั้นควรเข้าถึงได้
 *
 * ⚠️ ค่าเหล่านี้คือ **สัญญาของ "ทางเข้าเดียวต่อปลายทาง"** (หลักการข้อ 3 ของ audit)
 *    ⇒ ถ้าวันหนึ่งมีคนเพิ่ม `new-issue` เข้าเมนูด้วย "เผื่อผู้ใช้หาไม่เจอ" เทสนี้จะแดง
 *    ซึ่งเป็นเจตนา — ทางเข้าซ้ำคือสาเหตุรากที่ผู้ใช้บอกว่าแอป "เยอะเกินไป"
 */
type Reach = 'tab' | 'menu' | 'hidden' | 'segment' | 'fab'
type Gate = 'none' | 'council' | { permission: string }

interface Fixture {
  /** ชื่อ route ปลายทาง */
  name: string
  /** ช่องทางเดียวที่ควรเข้าถึงได้ */
  reach: Reach
  /** ประตูสิทธิ์ */
  gate: Gate
  /** ที่มาของแถวนี้ (อ้างบรรทัดเดิมใน MainLayout เพื่อตรวจย้อนหลังได้) */
  from: string
}

const MENU_TODAY: Fixture[] = [
  { name: 'home', reach: 'tab', gate: 'none', from: 'MainLayout:165 หน้าแรก' },
  { name: 'dashboard', reach: 'menu', gate: { permission: 'VIEW_DASHBOARD' }, from: 'MainLayout:166' },
  { name: 'new-issue', reach: 'fab', gate: 'none', from: 'MainLayout:169 แจ้งเรื่อง' },
  { name: 'my-issues', reach: 'segment', gate: 'none', from: 'MainLayout:170 เรื่องของฉัน' },
  { name: 'boards', reach: 'tab', gate: 'none', from: 'MainLayout:176 PIRI Boards' },
  { name: 'events', reach: 'tab', gate: 'none', from: 'MainLayout:184 กิจกรรม' },
  {
    name: 'event-management',
    reach: 'menu',
    gate: { permission: 'MANAGE_EVENTS' },
    from: 'MainLayout:190 จัดการกิจกรรม',
  },
  {
    name: 'received-issues',
    reach: 'segment',
    gate: { permission: 'RECEIVE_ISSUES' },
    from: 'MainLayout:198 เรื่องที่รับ / ระดับฉัน',
  },
  { name: 'board-reports', reach: 'menu', gate: 'council', from: 'MainLayout:206 จัดการรายงาน' },
  {
    name: 'users',
    reach: 'menu',
    gate: { permission: 'MANAGE_STUDENTS' },
    from: 'MainLayout:215 จัดการสมาชิก',
  },
  {
    name: 'students',
    reach: 'menu',
    gate: { permission: 'MANAGE_STUDENTS' },
    from: 'MainLayout:216 นักเรียน',
  },
  {
    name: 'import-students',
    reach: 'menu',
    gate: { permission: 'MANAGE_STUDENTS' },
    from: 'MainLayout:217 นำเข้า Excel',
  },
  {
    name: 'announcements',
    reach: 'menu',
    gate: { permission: 'MANAGE_ANNOUNCEMENTS' },
    from: 'MainLayout:224 จัดการประกาศ',
  },
  {
    name: 'academic-terms',
    reach: 'menu',
    gate: { permission: 'MANAGE_SETTINGS' },
    from: 'MainLayout:232 ภาคเรียน',
  },
  {
    name: 'audit-logs',
    reach: 'menu',
    gate: { permission: 'VIEW_AUDIT_LOG' },
    from: 'MainLayout:240 บันทึกการใช้งาน',
  },

  // ── ปลายทางที่ R1 เพิ่มเข้าเมนู (วันนี้เป็น "orphan" หรือไม่มีแถวเลย) ──────────
  { name: 'my-activity', reach: 'menu', gate: 'none', from: 'R1.2 · เดิมเข้าถึงจาก Profile.vue:197 ทางเดียว' },
  { name: 'profile', reach: 'menu', gate: 'none', from: 'R1.2 · เดิมเข้าถึงจากหัว sheet ทางเดียว' },
  { name: 'playbooks', reach: 'menu', gate: 'none', from: 'R1.1 · ยุบ 6 แถวเป็นแถวเดียว' },
  { name: 'profile-edit', reach: 'hidden', gate: 'none', from: 'R1.2 · กลุ่มบัญชี' },
  { name: 'profile-password', reach: 'hidden', gate: 'none', from: 'R1.2 · กลุ่มบัญชี' },
  { name: 'notifications', reach: 'hidden', gate: 'none', from: 'R1.2 · เข้าจากกระดิ่งบนหัวแถบ' },
]

function gatePasses(gate: Gate, profile: Profile): boolean {
  if (gate === 'none') return true
  if (gate === 'council') return Boolean(profile.council || profile.isAdmin)
  const list = profile.permissions ?? []
  return profile.isAdmin === true || list.includes(gate.permission)
}

/** ชื่อ route ทั้งหมดที่ nav model เปิดให้เข้าถึง (ไม่นับแท็บ ซึ่งตรวจแยก) */
function reachableFrom(nav: ReturnType<typeof useNavItems>, reach: Reach): Set<string> {
  const names = new Set<string>()

  if (reach === 'menu' || reach === 'hidden') {
    const groups = reach === 'menu' ? nav.menuGroups.value : nav.groups.value
    for (const item of groups.flatMap((g) => g.items)) {
      const n = nameOf(item.to)
      if (n) names.add(n)
    }
  }
  if (reach === 'segment') {
    for (const s of [...nav.segmentsOf('issues'), ...nav.segmentsOf('members')]) names.add(s.to.name)
  }
  if (reach === 'tab') {
    for (const t of nav.tabs.value) names.add(t.key)
  }
  // 'fab' ไม่ควรอยู่ใน nav model เลย — คืนเซตว่างเพื่อให้การยืนยันข้างล่างเป็น "ต้องไม่พบ"
  return names
}

// ─────────────────────────────────────────────────────────────────────────────
describe('R0.0 · registry ครอบเมนูของวันนี้ครบทุกปลายทาง', () => {
  it('ปลายทางที่ต้องมีสิทธิ์ ยังต้องมีสิทธิ์ — และที่ไม่มี ต้องไม่ถูกกัน', () => {
    // โปรไฟล์ที่ "มีทุกอย่าง" ⇒ ต้องเห็นครบ, โปรไฟล์นักเรียนเปล่า ⇒ ต้องไม่เห็นของที่ต้องมีสิทธิ์
    const full: Profile = {
      permissions: [
        'VIEW_DASHBOARD',
        'MANAGE_EVENTS',
        'RECEIVE_ISSUES',
        'MANAGE_STUDENTS',
        'MANAGE_ANNOUNCEMENTS',
        'MANAGE_SETTINGS',
        'VIEW_AUDIT_LOG',
      ],
      council: true,
    }

    for (const profile of [full, {} as Profile]) {
      signIn(profile)
      const nav = useNavItems()

      /** แถวที่ช่องทางไม่ตรงกับที่ประกาศ (ควรเห็นแต่ไม่เห็น / ไม่ควรเห็นแต่กลับเห็น) */
      const misplaced: string[] = []
      /** ปลายทางที่เป็น FAB แต่กลับโผล่บนเมนู = ทางเข้าซ้ำ */
      const duplicated: string[] = []

      for (const row of MENU_TODAY) {
        const key = row.reach === 'tab' ? tabKeyOf(row.name) : row.name
        const inModel = reachableFrom(nav, row.reach).has(key)

        if (row.reach === 'fab') {
          // 🚨 FAB **ไม่ใช่รายการเมนู** ⇒ ต้องไม่ปรากฏใน nav model เลย
          //    (ช่องทางของมันคือ `meta.fab` ซึ่งตรวจใน `routeMeta.spec.ts`)
          if (inModel) duplicated.push(`${row.from} → ${row.name}`)
          continue
        }

        if (inModel !== gatePasses(row.gate, profile)) {
          misplaced.push(`${row.from} → ${row.name} (${row.reach}) — ควร${inModel ? 'ซ่อน' : 'เห็น'}`)
        }
      }

      expect(misplaced).toEqual([])
      expect(duplicated).toEqual([])
    }
  })

  it('FAB ไม่เป็นทางเข้าซ้ำ — "แจ้งเรื่อง" ต้องไม่อยู่ในเมนู/แท็บเลย', () => {
    signIn()
    const nav = useNavItems()

    const everywhere = new Set<string>()
    for (const item of nav.groups.value.flatMap((g) => g.items)) {
      const n = nameOf(item.to)
      if (n) everywhere.add(n)
    }
    for (const t of nav.tabs.value) everywhere.add(t.to)

    // 🚨 ถ้าบรรทัดนี้แดง แปลว่ามีคนเพิ่ม "แจ้งเรื่อง" กลับเข้าเมนู ⇒ ทางเข้าซ้ำเกิดขึ้นแล้ว
    expect(everywhere.has('new-issue')).toBe(false)
    expect([...everywhere].some((p) => p.includes('issues/new'))).toBe(false)
  })

  it('กลุ่มที่ไม่มีแถวเหลือหลังกรองสิทธิ์ ต้องถูกตัดออกทั้งกลุ่ม (ไม่เหลือหัวกลุ่มลอย)', () => {
    signIn() // นักเรียนเปล่า — ไม่มีสิทธิ์อะไรเลย
    const nav = useNavItems()

    expect(nav.groups.value.length).toBeGreaterThan(0)

    // กลุ่มที่โผล่มาทั้งที่ไม่มีแถวเหลือ = หัวกลุ่มลอยที่กดอะไรไม่ได้
    const empty = nav.groups.value.filter((g) => g.items.length === 0).map((g) => g.key)
    expect(empty).toEqual([])

    // กลุ่ม "ผู้ดูแล" ต้องหายไปทั้งกลุ่มสำหรับนักเรียน
    expect(nav.groups.value.some((g) => g.key === 'admin')).toBe(false)
  })

  it('`hiddenFromMenu` อยู่ใน groups แต่ไม่ใช่ menuGroups', () => {
    signIn({ permissions: ['RECEIVE_ISSUES'] })
    const nav = useNavItems()

    const inGroups = nav.groups.value.flatMap((g) => g.items).map((i) => i.key)
    const inMenu = nav.menuGroups.value.flatMap((g) => g.items).map((i) => i.key)

    expect(inGroups).toContain('notifications')
    expect(inMenu).not.toContain('notifications')
  })
})

// ─────────────────────────────────────────────────────────────────────────────
describe('R0.0 · badge', () => {
  it('badge ของแท็บ "เรื่อง" ตาม segment ที่เปิด — และ **ไม่บวกสองกลุ่มเข้าด้วยกัน**', () => {
    signIn({ permissions: ['RECEIVE_ISSUES'] })
    const store = useNotificationsStore()
    store.counts = { issue_mine: 3, issue_received: 5, board: 2, event: 4, report: 1 }
    store.total = 15

    const nav = useNavItems()
    const issues = tabOf('issues')

    goto('my-issues', '/app/issues/mine')
    expect(nav.tabBadge(issues)).toBe(3)

    goto('received-issues', '/app/issues/received')
    expect(nav.tabBadge(issues)).toBe(5)

    // อยู่นอกแท็บ "เรื่อง" ⇒ ใช้ segment เริ่มต้น (ของฉัน)
    goto('home', '/app/home')
    expect(nav.tabBadge(issues)).toBe(3)

    // 🚨 8 = 3 + 5 คือผลรวมที่ผู้ใช้อ่านไม่ออกและไม่มีทางตรงกับจำนวนเรื่องในหน้าไหนเลย
    expect(nav.tabBadge(issues)).not.toBe(8)
  })

  it('แท็บ "เพิ่มเติม" เห็นยอดที่ยังไม่ถูกโชว์บนแท็บอื่น (ไม่นับซ้ำ)', () => {
    signIn({ permissions: ['RECEIVE_ISSUES'] })
    const store = useNotificationsStore()
    store.counts = { issue_mine: 3, issue_received: 5, board: 2, event: 4, report: 1 }
    store.total = 15

    const nav = useNavItems()
    goto('my-issues', '/app/issues/mine')

    // 15 − (3 ที่แท็บเรื่อง + 2 บอร์ด + 4 กิจกรรม) = 6
    expect(nav.tabBadge(tabOf('more'))).toBe(6)
  })

  it('badge ของ "ตรวจรายงาน" มาจากกลุ่ม `report` (เดิมคือ menuBadge(\'/app/boards/reports\'))', () => {
    signIn({ council: true })
    const store = useNotificationsStore()
    store.counts = { report: 7 }

    const nav = useNavItems()
    const item = nav.groups.value.flatMap((g) => g.items).find((i) => i.key === 'board-reports')

    expect(item).toBeDefined()
    expect(item?.badgeGroup).toBe('report')
    expect(nav.badgeOf(item!)).toBe(7)
  })

  it('badgeLabel ตัดที่ 99+ และไม่ตัดก่อนนั้น', () => {
    signIn()
    const nav = useNavItems()

    expect(nav.badgeLabel(1)).toBe('1')
    expect(nav.badgeLabel(99)).toBe('99')
    expect(nav.badgeLabel(100)).toBe('99+')
  })
})

// ─────────────────────────────────────────────────────────────────────────────
describe('R0.0 · สิทธิ์ของ segment (R0.3.3)', () => {
  it('ไม่มี RECEIVE_ISSUES ⇒ "ที่รับผิดชอบ" หาย ⇒ เหลือตัวเดียว (แถบ segment ซ่อนตัวเองได้)', () => {
    signIn()
    const nav = useNavItems()

    expect(nav.segmentsOf('issues').map((s) => s.to.name)).toEqual(['my-issues'])
  })

  it('มี RECEIVE_ISSUES ⇒ เห็นทั้งสอง segment เรียงตามที่ประกาศ', () => {
    signIn({ permissions: ['RECEIVE_ISSUES'] })
    const nav = useNavItems()

    expect(nav.segmentsOf('issues').map((s) => s.to.name)).toEqual(['my-issues', 'received-issues'])
  })

  it('segment "สมาชิก" ต้องว่างเปล่าเมื่อไม่มี MANAGE_STUDENTS', () => {
    signIn()
    expect(useNavItems().segmentsOf('members')).toHaveLength(0)

    signIn({ permissions: ['MANAGE_STUDENTS'] })
    expect(useNavItems().segmentsOf('members').map((s) => s.to.name)).toEqual([
      'students',
      'users',
    ])
  })
})

// ─────────────────────────────────────────────────────────────────────────────
describe('R0.0 · รูปร่างของแท็บล่าง', () => {
  it('มี 5 แท็บ · ป้ายไทยล้วน · path ตรงกับที่ประกาศ', () => {
    expect(NAV_TABS.map((t) => t.key)).toEqual(['home', 'issues', 'boards', 'events', 'more'])
    expect(NAV_TABS.map((t) => t.to)).toEqual([
      '/app/home',
      '/app/issues/mine',
      '/app/boards',
      '/app/events',
      '/app/more',
    ])

    // ⚠️ ป้ายอังกฤษปนในแถบไทยอ่านไม่ออกว่าคืออะไร (audit ติ "Boards")
    const notThai = NAV_TABS.filter((t) => !/^[ก-๛\s]+$/.test(t.label)).map((t) => t.key)
    expect(notThai).toEqual([])
  })

  it('ทุกรายการในเมนูมีคีย์ไม่ซ้ำ (ใช้เป็น `key` ของ v-for)', () => {
    const keys = NAV_GROUPS.flatMap((g) => g.items.map((i) => i.key))
    expect(keys.filter((k, i) => keys.indexOf(k) !== i)).toEqual([])

    const groupKeys = NAV_GROUPS.map((g) => g.key)
    expect(groupKeys.filter((k, i) => groupKeys.indexOf(k) !== i)).toEqual([])
  })
})

/** แท็บไหนรองรับปลายทางนั้น (ใช้แทนการเทียบ path ของ fixture) */
function tabKeyOf(routeName: string): string {
  const map: Record<string, NavKey> = {
    home: 'home',
    boards: 'boards',
    events: 'events',
  }
  return map[routeName] ?? routeName
}
