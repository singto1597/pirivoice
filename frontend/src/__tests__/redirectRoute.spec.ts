/**
 * 🧪 §30 ข้อ 2 · ข้อ 3 — สองเส้นทางที่ **`safeRedirect` แก้ให้ไม่ได้** เพราะปัญหาเกิด *ก่อน* ถึงหน้า Login
 *
 * **ข้อ 2 — ทางตัน (path ที่ไม่มี route):** `router/index.ts` เดิมไม่มี catch-all
 *   ⇒ path ที่ไม่ match อะไรเลยจะ **ไม่มี route ถูกเลือก** ⇒ `to.meta` เป็น `{}`
 *   ⇒ `requiresAuth` เป็น `undefined` ⇒ **guard ผ่าน** ⇒ `<RouterView>` ว่างเปล่า = **จอขาว**
 *   ไม่มี error ไม่มี log · เคสจริง: `/app/events/{id}` จาก QR ที่ติดหน้าโรงเรียน
 *   **ก่อนที่ route นั้นจะขึ้น** ⇒ ผู้สแกนเห็นจอขาว ซึ่งแย่กว่าถูกพาไปล็อกอินเสียอีก
 *   และมันจะดูเหมือน **"QR พัง"** ทั้งที่โค้ด QR ถูกทุกบรรทัด
 *
 * **ข้อ 3 — บัญชีที่ต้องเปลี่ยนรหัส:** guard ต้อง **พา `redirect` ผ่านขั้นเปลี่ยนรหัสไปด้วย**
 *   ไม่งั้นบัญชีที่เพิ่งเปิดลิงก์ที่แชร์มาจะ **ทิ้งปลายทางถาวร** — เปลี่ยนรหัสเสร็จก็ยังต้อง
 *   หาลิงก์เดิมมากดซ้ำเอง ทั้งที่ระบบรู้อยู่แล้วว่าผู้ใช้จะไปไหน
 *
 * ⚠️ **ทดสอบผ่าน `router.push()` จริง ไม่ใช่ `router.resolve()`** — `resolve()` **ไม่ตาม
 *    redirect record** (คืน record ปลายทางเป็น `not-found` เฉย ๆ) ⇒ เทสต์ที่ใช้ `resolve()`
 *    จะ **ผ่านทั้งที่ของพัง** หรือแดงทั้งที่ของดี · redirect ถูกใช้ตอน *นำทาง* เท่านั้น
 *
 * ⚠️ **mock `@/stores/auth` ทั้งก้อน** — guard อ่านสถานะจาก store และเทสต์นี้ต้องบังคับ
 *    สถานะได้ทุกแบบ (ยังไม่ล็อกอิน / ล็อกอินแล้ว / ต้องเปลี่ยนรหัส) โดยไม่ต้องมี Pinia
 *    หรือ localStorage จริง · `mustChangePassword` ผูกกับ `user.must_change_password`
 *    ตาม store จริง ⇒ เทสต์ "เปลี่ยนรหัสสำเร็จ" ทำได้แค่ล้าง `must_change_password`
 *
 * 📌 เคสของ `safeRedirect` เอง (payload โจมตี) อยู่ที่ `redirect.spec.ts` — คนละชั้นกัน
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const auth = vi.hoisted(() => ({
  state: {
    authenticated: false,
    user: null as { must_change_password?: boolean } | null,
  },
}))

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({
    get isAuthenticated() {
      return auth.state.authenticated
    },
    get user() {
      return auth.state.user
    },
    get mustChangePassword() {
      return auth.state.user?.must_change_password ?? false
    },
    get isCouncilAuthority() {
      return false
    },
    hasPermission: () => false,
    loadMe: async () => {},
    logout: () => {},
  }),
}))

import router from '@/router'
import { REDIRECT_QUERY, safeRedirect } from '@/router/redirect'

/** ล็อกอินอยู่แล้ว (ไม่ต้องเปลี่ยนรหัส) */
function login(user: { must_change_password?: boolean } = {}): void {
  auth.state.authenticated = true
  auth.state.user = user
}

/** นำทางจริงแล้วคืน route ที่จบ — redirect/guard ถูกใช้ครบเหมือนผู้ใช้กดเอง */
async function goto(path: string) {
  await router.push(path)
  return router.currentRoute.value
}

beforeEach(async () => {
  auth.state.authenticated = false
  auth.state.user = null
  // เริ่มทุกเทสต์จากหน้า public — ปลายทางของเทสต์ก่อนหน้าไม่ค้างมาทำให้ผลเพี้ยน
  await router.replace('/')
})

describe('§30 ข้อ 2 — path ที่ไม่มี route ต้องไม่จบที่ "จอขาว"', () => {
  it('C1: ยังไม่ล็อกอิน · เปิด path ที่ไม่มี route → ไป login **พร้อมจำปลายทาง**', async () => {
    const route = await goto('/app/does-not-exist/7')

    expect(route.name).toBe('login')
    expect(route.query[REDIRECT_QUERY]).toBe('/app/does-not-exist/7')
  })

  it('★ C2: เคส QR — `/app/events/7` ตอนยังไม่ล็อกอิน → ไป Login พร้อมจำปลายทางไว้', async () => {
    const route = await goto('/app/events/7')

    expect(route.name).toBe('login')
    // ⚠️ ค่านี้ต้องเป็น fullPath ของ **กิจกรรมนั้น** ไม่ใช่ `/app/events` หรือ `/login` เปล่า ๆ
    //    ⇒ ใช้ได้ทั้งก่อน D1 ขึ้น (ผ่าน catch-all) และหลังขึ้นแล้ว (ผ่าน `requiresAuth`)
    expect(route.query[REDIRECT_QUERY]).toBe('/app/events/7')
  })

  it('C3: path นอกแอพที่ไม่มี route → ไป login พร้อมจำไว้ แล้วให้ **หน้า Login** เป็นคนกรองทิ้ง', async () => {
    const route = await goto('/totally-unknown')

    expect(route.name).toBe('login')
    expect(route.query[REDIRECT_QUERY]).toBe('/totally-unknown')
    // guard ส่งต่ออย่างเดียว — ไม่ตัดสินความปลอดภัยเอง (ด่านจริงคือ safeRedirect)
    expect(safeRedirect(route.query[REDIRECT_QUERY])).toBeNull()
  })

  it('C4: ล็อกอินอยู่แล้ว · เปิด path ที่ไม่มี route → หน้าแรก (ไม่วน ไม่จอขาว)', async () => {
    login()
    const route = await goto('/app/does-not-exist/7')

    expect(route.name).toBe('home')
  })

  it('C5: ปลายทางของทางตันต้องมี route จริง — ไม่ใช่ทางตันซ้อนทางตัน', () => {
    const login_ = router.resolve({ name: 'login' })

    expect(login_.path).toBe('/login')
    expect(login_.matched.some((r) => r.name === 'not-found')).toBe(false)
  })
})

describe('§30 ข้อ 3 — บัญชีที่ต้องเปลี่ยนรหัสต้องไม่ทิ้งปลายทาง', () => {
  it('M1: เปิดลิงก์ที่แชร์มา → ถูกพาไปเปลี่ยนรหัส **พร้อมปลายทาง**', async () => {
    login({ must_change_password: true })
    const route = await goto('/app/boards/5')

    expect(route.name).toBe('profile-password')
    expect(route.query[REDIRECT_QUERY]).toBe('/app/boards/5')
  })

  it('M2: `redirect` ที่ชี้มาที่หน้าเปลี่ยนรหัสเอง ต้องไม่ทำให้วนกลับหาตัวเอง', async () => {
    login({ must_change_password: true })
    const route = await goto('/app/profile/password')

    expect(route.name).toBe('profile-password')
    expect(route.query[REDIRECT_QUERY]).toBeUndefined()
  })

  it('★ M3: สัญญาปลายทางครบวง — ค่าที่ guard ส่งต่อ ใช้ต่อได้จริงหลังเปลี่ยนรหัสสำเร็จ', async () => {
    login({ must_change_password: true })
    const atPasswordPage = await goto('/app/boards/5')
    const target = safeRedirect(atPasswordPage.query[REDIRECT_QUERY])

    expect(target).toBe('/app/boards/5')

    // = สิ่งที่ `ChangePassword.vue` ทำหลังเปลี่ยนรหัสสำเร็จ: store ถูกอัปเดต + กระโดดไปปลายทาง
    auth.state.user = {}
    const end = await goto(target as string)

    expect(end.name).toBe('board-detail')
    expect(end.params.id).toBe('5')
  })

  it('M4: ปลายทางที่ไม่ผ่านด่าน → ไม่ถูกพาไป ตกที่หน้าแรกแทน (ด่านเดิมต้องยังกัน)', async () => {
    login({ must_change_password: true })
    const route = await goto('/app/profile/password?redirect=https://evil.example')

    expect(safeRedirect(route.query[REDIRECT_QUERY])).toBeNull()
  })
})

describe('ของเดิมที่ต้องไม่พัง (pin พฤติกรรมก่อน §30)', () => {
  it('B1: ไม่เคยล็อกอิน · เปิด `/app/boards/5` → login พร้อมจำปลายทาง', async () => {
    const route = await goto('/app/boards/5')

    expect(route.name).toBe('login')
    expect(route.query[REDIRECT_QUERY]).toBe('/app/boards/5')
  })

  it('B2: ล็อกอินอยู่แล้ว · เข้า `/login` → หน้าแรก (ไม่ค้างที่ฟอร์มล็อกอิน)', async () => {
    login()
    const route = await goto('/login')

    expect(route.name).toBe('home')
  })
})
