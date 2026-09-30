/**
 * 🧪 §30 ข้อ 1 — **401 ต้องจำปลายทางไว้** ไม่ใช่ทิ้ง path แล้วเด้งไป `/login` เปล่า ๆ
 *
 * **ทำไมเทสนี้คือตัวสำคัญของ §30 ทั้งหัวข้อ:** เส้นทาง 401 **อยู่นอก router ทั้งหมด**
 *   ผู้ใช้ *มี* token อยู่แล้วแต่มันหมดอายุ ⇒ guard เห็น `isAuthenticated = true` ⇒ **ไม่ยิง**
 *   ⇒ เข้าหน้าเป้าหมายได้ ⇒ พอยิง API ก็ได้ 401 ⇒ ถูกพาออกไปหน้า Login
 *   **โดยไม่มีใครรู้ว่าเขาจะไปไหน** ⇒ ล็อกอินเสร็จตกที่ Home
 *   ⇒ ตรงกับที่ผู้ใช้รายงานเป๊ะ: *"มันจะเด้งไป login แล้วพอ login เสร็จ มันก็จะเข้าหน้า home"*
 *
 * ⚠️ **`api.spec.ts` ไม่ครอบสาขานี้โดยเจตนา** (ดูคอมเมนต์หัวไฟล์นั้น) — เทสนี้จึงแยกออกมา
 *    เพราะต้องคุม `window.location` ทั้งใบ · และเพราะ `api.ts` เก็บ `isRedirectingToLogin`
 *    เป็น **สถานะระดับโมดูล** (latch กันวน) ⇒ ถ้ารวมไว้ไฟล์เดียว เทสต์ตัวแรกจะ latch ค้าง
 *    ให้ตัวถัดไปทั้งหมด ⇒ **ทุกเทสต์ที่นี่โหลดโมดูลใหม่** ผ่าน `loadApi()` เพื่อให้ latch เริ่มที่ `false` เสมอ
 *
 * ⚠️ **ไม่ทดสอบการนำทางจริง** — jsdom ไม่รองรับ navigation (`Not implemented: navigation`)
 *    ⇒ ใช้ `vi.stubGlobal('location', …)` แทน `window.location` ทั้งก้อน แล้วอ่านค่า `href`
 *    ที่โค้ด *ตั้งใจ* จะไป · สิ่งที่ทดสอบคือ **การตัดสินใจ** ไม่ใช่การที่เบราว์เซอร์ไปจริง
 *    (การไปจริงพิสูจน์ได้แค่บน staging — §30.6)
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { AxiosAdapter, InternalAxiosRequestConfig } from 'axios'

type ApiModule = typeof import('@/services/api')
type Api = ApiModule['api']

/** `window.location` ปลอม — เก็บ `href` ที่โค้ดเขียนลงไป */
type FakeLocation = { pathname: string; search: string; href: string }

/**
 * โหลด `api.ts` ใหม่ทั้งโมดูล
 *
 * ⚠️ จำเป็นเพราะ `isRedirectingToLogin` เป็น **สถานะระดับโมดูล** ที่เขียนแล้วไม่รีเซ็ต
 *    (โดยเจตนา — กัน 401 ซ้ำหลายคำขอแล้วเด้งรัว) ⇒ โมดูลที่ import ค้างไว้จะ latch
 *    ติดมาจากเทสต์ก่อนหน้า
 */
async function loadApi(): Promise<ApiModule> {
  vi.resetModules()
  return import('@/services/api')
}

function stubLocation(pathname: string, search = ''): FakeLocation {
  const loc: FakeLocation = { pathname, search, href: '' }
  vi.stubGlobal('location', loc)
  return loc
}

/** แทน adapter ให้ตอบ 401 เสมอ (โครงเดียวกับ `api.spec.ts`) */
function stub401Adapter(): void {
  const adapter: AxiosAdapter = (config: InternalAxiosRequestConfig) =>
    Promise.reject({
      message: 'Request failed with status code 401',
      config,
      response: { status: 401, statusText: '', headers: {}, config, data: { detail: 'หมดอายุ' } },
    })
  api.defaults.adapter = adapter
}

let mod: ApiModule
let api: Api

/** ยิง request ที่จะได้ 401 — คืน `true` ถ้า reject จริง (เทสต์ผิดถ้า resolve) */
async function fire401(): Promise<boolean> {
  try {
    await api.get('/boards/1')
    return false
  } catch {
    return true
  }
}

beforeEach(async () => {
  localStorage.clear()
  mod = await loadApi()
  api = mod.api
})

afterEach(() => {
  vi.unstubAllGlobals()
})

// ─────────────────────────────────────────────────────────────────────────────
// ตัวสร้าง URL — ตรรกะทั้งหมดของการจำปลายทางอยู่ที่ฟังก์ชันเดียวนี้
// ─────────────────────────────────────────────────────────────────────────────

describe('loginUrlRemembering — ปลายทางที่เขียนลง Location', () => {
  it('L1: path ในแอพ + search → ฝัง **ทั้งคู่** ไว้ใน `redirect` (encode แล้ว)', async () => {
    const url = mod.loginUrlRemembering('/app/boards/5', '?tab=comments')

    expect(url).toBe(`/login?redirect=${encodeURIComponent('/app/boards/5?tab=comments')}`)
    // ⚠️ ข้อที่ผู้ใช้จะรู้สึกได้: ตัด `search` ทิ้ง = ไปถึงหน้าปลายทางแต่ **ไม่ถึงแท็บที่ตั้งใจ**
    expect(decodeURIComponent(url.slice(url.indexOf('redirect=') + 'redirect='.length))).toBe(
      '/app/boards/5?tab=comments'
    )
  })

  it('L2: query ที่ตามมาเป็นของ `redirect` ทั้งก้อน — ไม่หลุดออกมาปนกับ query ของ `/login`', async () => {
    const url = mod.loginUrlRemembering('/app/x', '?a=1&b=2')
    const query = url.slice(url.indexOf('?') + 1)

    expect(query.startsWith('redirect=')).toBe(true)
    // ถ้าไม่ encode: `&b=2` จะกลายเป็น query ของหน้า Login เอง = ค่าปลอมที่หน้า Login ต้องมาไล่กรอง
    expect(query).not.toContain('&')
    expect(query.slice('redirect='.length)).not.toContain('?')
  })

  it('L3: path ที่ไม่ใช่ `/app/` → `/login` เปล่า ๆ — **ไม่เขียนค่าที่ตัวเองไม่ได้ตรวจ**', async () => {
    for (const path of ['', '/', '/login', '/landing', 'https://evil.example']) {
      expect(mod.loginUrlRemembering(path, '')).toBe('/login')
    }
  })

  it('L4: `\\` → `/login` เปล่า ๆ (bypass คลาสสิกของด่าน "ต้องขึ้นต้นด้วย /")', async () => {
    expect(mod.loginUrlRemembering('/app/\\evil.example', '')).toBe('/login')
    expect(mod.loginUrlRemembering('/\\evil.example', '')).toBe('/login')
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// การต่อสายใน interceptor — ตัวสร้าง URL ข้างบนถูกเรียกใช้จริงหรือไม่
// ─────────────────────────────────────────────────────────────────────────────

describe('interceptor 401 — ปลายทางที่ถูกเขียนจริงตอน token หมดอายุ', () => {
  it('L5: ★ token หมดอายุกลางหน้า `/app/boards/5?tab=comments` → `/login?redirect=…`', async () => {
    const loc = stubLocation('/app/boards/5', '?tab=comments')
    stub401Adapter()

    expect(await fire401()).toBe(true)
    expect(loc.href).toBe(`/login?redirect=${encodeURIComponent('/app/boards/5?tab=comments')}`)
  })

  it('L6: 401 บนหน้า public (`/`) → `/login` เปล่า ๆ ตามพฤติกรรมเดิม', async () => {
    const loc = stubLocation('/', '')
    stub401Adapter()

    await fire401()
    expect(loc.href).toBe('/login')
  })

  it('L7: อยู่ที่ `/login` แล้ว → ไม่เขียนทับ (กันวนกลับมาที่เดิม)', async () => {
    const loc = stubLocation('/login', '')
    stub401Adapter()

    await fire401()
    expect(loc.href).toBe('')
  })

  it('L8: 401 ซ้ำตัวที่สองไม่เด้งอีก (latch) — หลายคำขอพร้อมกันต้องพาออกครั้งเดียว', async () => {
    const loc = stubLocation('/app/boards/5', '')
    stub401Adapter()

    await fire401()
    expect(loc.href).toBe(`/login?redirect=${encodeURIComponent('/app/boards/5')}`)

    loc.href = ''
    await fire401()
    expect(loc.href).toBe('')
  })

  it('L9: 401 ต้องเคลียร์ token + user_id_str ทิ้ง (ไม่ใช่แค่ token)', async () => {
    stubLocation('/app/boards/5', '')
    stub401Adapter()
    localStorage.setItem('access_token', 't')
    localStorage.setItem('user_id_str', '7')

    await fire401()
    expect(localStorage.getItem('access_token')).toBeNull()
    expect(localStorage.getItem('user_id_str')).toBeNull()
  })
})
