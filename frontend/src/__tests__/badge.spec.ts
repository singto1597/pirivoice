/**
 * 🧪 `badge.ts` — ตัวเลขบนไอคอนแอพ (A5)
 *
 * **ทำไมต้องมีเทสนี้:** Badging API เป็น API ที่ **หายไปทั้งตัว** บน Safari/iOS และ
 * **reject** บน Chrome ที่ยังไม่ได้ติดตั้งแอพ ⇒ ความล้มเหลวของมันคือ `TypeError` /
 * unhandled rejection ที่โผล่ในคอนโซลดูเหมือน "แอพพัง" ทั้งที่แค่ไม่มี badge
 * · และ **ความล้มเหลวอีกแบบที่เงียบกว่า** คือ badge ค้างเป็นยอดของคนก่อนหน้า
 * (badge เกาะกับไอคอน = ของเครื่อง ไม่ใช่ของบัญชี) ซึ่งไม่มีอาการให้เห็นเลย
 *
 * ⭐ สิ่งที่เทสนี้พิสูจน์ (เรียงตามความสำคัญ):
 *   - `B10` **หลัง `clearBadge()` การกลับมาโฟกัสต้องไม่ปลุกยอดเก่ากลับมา** — นี่คือ
 *     ช่องรั่วข้ามผู้ใช้บนเครื่องที่ใช้ร่วมกัน (ห้องคอม / มือถือโรงเรียน)
 *   - `B9` **กลับมาโฟกัสแล้วเขียนยอดล่าสุดทับทันที** — ระหว่างที่แท็บถูกพัก
 *     service worker เขียนทับตัวเลขด้วย "จุด" ⇒ ถ้าไม่ทับคืน badge ค้างเป็นจุด 30 วิ
 *   - `B5`/`B6` **reject และ throw ต้องไม่หลุดออกไป** — ทั้งคู่เกิดจริงบนเครื่องจริง
 *
 * ⚠️ **ไม่ใช้ `vi.resetModules()` โดยเจตนา** — `badge.ts` ผูก `visibilitychange`
 *    listener ตอน import ⇒ import ใหม่หลายรอบ = listener ซ้อนกันหลายตัวที่ยังชี้
 *    สถานะของโมดูลเก่า แล้ว `mockClear()` จะไม่ช่วยอะไร (ตัวเก่ายิงใส่ spy ตัวใหม่)
 *    ⇒ ใช้ **โมดูลตัวเดียวทั้งไฟล์** แล้วตั้งสถานะผ่าน **API สาธารณะ** ใน `beforeEach`
 *    (`clearBadge()` ตั้งยอดที่จำไว้เป็น 0) — บทเรียนเดียวกับ `pwa.spec.ts`
 *
 * ⚠️ **ไม่ทดสอบ "เตือนครั้งเดียว" ของ `console.debug`** — ธง `warned` เป็น state
 *    ระดับโมดูลที่รีเซ็ตผ่าน API สาธารณะไม่ได้ ⇒ เทสจะผูกกับลำดับการรัน (เปราะ)
 *    แลกกับประโยชน์ที่ไม่คุ้ม: log ซ้ำไม่ใช่ความผิดพลาดที่ผู้ใช้เห็น
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { clearBadge, syncBadge } from '@/badge'

/**
 * ⚠️ **ต้องมี type parameter** (กฎ `require-mock-type-parameters`) — ไม่ใช่แค่เพื่อให้ lint ผ่าน:
 * `vi.fn()` เปล่า ๆ รับอะไรก็ได้ ⇒ `mockResolvedValue('ok')` (ไม่ใช่ Promise) จะผ่านฉลุย
 * แล้วเทสจะเข้ารหัสพฤติกรรมที่เบราว์เซอร์ไม่มีวันทำ โดยไม่มีใครรู้
 *
 * ⚠️ **คืน `Promise<void>` ไม่ใช่ `void`** — Badging API คืน promise จริง (`badge.ts` ต้องมี `.catch`)
 * ส่วนเส้นทางที่ `throw` synchronous ยังเข้ากับ type นี้ได้ (throw ไม่ใช่ค่าที่คืน)
 */
type BadgeMock = ReturnType<typeof vi.fn<() => Promise<void>>>

/** navigator ปลอมที่เทสสร้างเอง — เก็บ spy ไว้ยืนยันว่าเรียกอะไร ด้วยค่าใด */
let setAppBadge: BadgeMock
let clearAppBadge: BadgeMock | undefined
let debugSpy: ReturnType<typeof vi.spyOn>

/** ค่าที่ `document.hidden` จะตอบ (jsdom ให้ false ไว้) */
let hiddenValue = false

/**
 * ติดตั้ง navigator ปลอม — `clear: false` = จำลองเบราว์เซอร์ที่ **ไม่มี `clearAppBadge`**
 * (มีแต่ `setAppBadge`) ซึ่งเป็นกรณีที่ต้องมี fallback `setAppBadge(0)`
 */
function installBadgeApi(opts: { clear?: boolean; setThrows?: boolean; setRejects?: boolean } = {}) {
  const { clear = true, setThrows = false, setRejects = false } = opts
  setAppBadge = vi.fn<() => Promise<void>>(() => {
    if (setThrows) throw new TypeError('setAppBadge โยน synchronous')
    if (setRejects) return Promise.reject(new DOMException('ยังไม่ได้ติดตั้งแอพ', 'NotAllowedError'))
    return Promise.resolve()
  })
  clearAppBadge = clear ? vi.fn<() => Promise<void>>(() => Promise.resolve()) : undefined

  Object.defineProperty(navigator, 'setAppBadge', {
    configurable: true,
    writable: true,
    value: setAppBadge,
  })
  if (clearAppBadge) {
    Object.defineProperty(navigator, 'clearAppBadge', {
      configurable: true,
      writable: true,
      value: clearAppBadge,
    })
  } else {
    // ⚠️ ต้อง `delete` ไม่ใช่ตั้งเป็น undefined เฉย ๆ — `badgeApi()` ตรวจว่าเป็น
    //    "function" ซึ่ง undefined ก็ผ่านด่านนั้นไม่ได้อยู่ดี แต่การลบทิ้งสะท้อน
    //    "ไม่มีคีย์นี้จริง" ได้ตรงกว่า
    delete (navigator as unknown as Record<string, unknown>).clearAppBadge
  }
}

/** จำลอง "ไม่มี Badging API เลย" (Safari / เบราว์เซอร์เก่า) */
function removeBadgeApi() {
  delete (navigator as unknown as Record<string, unknown>).setAppBadge
  delete (navigator as unknown as Record<string, unknown>).clearAppBadge
}

/** ยิง `visibilitychange` ตามที่เบราว์เซอร์ทำ (ยิงทั้งตอนซ่อนและตอนกลับมา) */
function fireVisibility(hidden: boolean) {
  hiddenValue = hidden
  document.dispatchEvent(new Event('visibilitychange'))
}

/** รอให้ promise ที่ `call()` กลืนไว้ได้ทำงานจนจบ (กันสถานะค้างข้ามเทส) */
async function flush() {
  await Promise.resolve()
  await Promise.resolve()
}

beforeEach(() => {
  hiddenValue = false
  Object.defineProperty(document, 'hidden', { configurable: true, get: () => hiddenValue })

  installBadgeApi()
  // ล้างสถานะที่จำไว้ (lastTotal) ผ่าน API สาธารณะ แล้วล้างบันทึกการเรียกทิ้ง
  clearBadge()
  setAppBadge.mockClear()
  clearAppBadge?.mockClear()

  debugSpy = vi.spyOn(console, 'debug').mockImplementation(() => {})
})

afterEach(() => {
  debugSpy.mockRestore()
  removeBadgeApi()
})

describe('badge — การตั้งค่า', () => {
  it('B1: ไม่มี Badging API เลย → เรียกได้ไม่โยน และไม่แตะอะไร', () => {
    removeBadgeApi()
    expect(() => syncBadge(5)).not.toThrow()
    expect(() => clearBadge()).not.toThrow()
    expect(setAppBadge).not.toHaveBeenCalled()
  })

  it('B2: ยอดมากกว่า 0 → `setAppBadge(ยอด)` และไม่ล้าง', () => {
    syncBadge(5)
    expect(setAppBadge).toHaveBeenCalledWith(5)
    expect(clearAppBadge).not.toHaveBeenCalled()
  })

  it('B3: ยอดเป็น 0 → ใช้ `clearAppBadge()` ไม่ใช่ `setAppBadge(0)`', () => {
    // ⚠️ สเปกนิยาม `setAppBadge(0)` ว่าเท่ากับการล้างก็จริง แต่ **การมีตัวล้างแยก**
    //    คือสิ่งที่เบราว์เซอร์ใช้ตัดสิน "ไม่มี badge" ⇒ ใช้ตัวที่ตั้งใจไว้สำหรับงานนี้
    syncBadge(0)
    expect(clearAppBadge).toHaveBeenCalledTimes(1)
    expect(setAppBadge).not.toHaveBeenCalled()
  })

  it.each([
    [-3, 'ติดลบ'],
    [Number.NaN, 'NaN'],
    [Number.POSITIVE_INFINITY, 'Infinity'],
    [0.4, 'ทศนิยมที่ยังไม่ถึง 1'],
  ])('B4: ยอด %s (%s) → ถือเป็น 0 (ล้าง) ไม่ส่งค่าที่สเปกปฏิเสธออกไป', (value) => {
    syncBadge(value)
    expect(clearAppBadge).toHaveBeenCalledTimes(1)
    expect(setAppBadge).not.toHaveBeenCalled()
  })

  it('B5: `setAppBadge` reject (ยังไม่ติดตั้งแอพ) → ไม่โยนออก และไม่เหลือ unhandled rejection', async () => {
    installBadgeApi({ setRejects: true })
    expect(() => syncBadge(3)).not.toThrow()
    await flush()
    // vitest ล้มเทสนี้เองถ้ามี unhandled rejection หลุดออกมา ⇒ การ flush คือคำยืนยัน
    expect(debugSpy).toHaveBeenCalled()
  })

  it('B6: `setAppBadge` โยน synchronous → ไม่โยนออก (ต้องมีทั้ง try และ .catch)', async () => {
    // ⚠️ เบราว์เซอร์บางตัวโยนทันที (ไม่คืน rejected promise) เมื่อเรียกในบริบทที่ไม่อนุญาต
    //    ⇒ ดักแค่ `.catch()` ไม่พอ
    installBadgeApi({ setThrows: true })
    expect(() => syncBadge(3)).not.toThrow()
    await flush()
  })

  it('B7: ไม่มี `clearAppBadge` → ถอยไปใช้ `setAppBadge(0)` ไม่ปล่อยให้ badge ค้าง', () => {
    installBadgeApi({ clear: false })
    syncBadge(0)
    expect(setAppBadge).toHaveBeenCalledWith(0)
  })

  it('B8: syncBadge ไม่ยิงเครือข่าย — ยอดต้องมาจากสโตร์เท่านั้น', () => {
    // ⚠️ ถ้ามีคนเผลอให้โมดูลนี้ไปถามยอดเอง (เช่นเรียก `getUnreadCounts`) จะกลายเป็น
    //    "แหล่งความถูกต้องที่สอง" ที่ไม่ผ่านสโตร์ ⇒ badge กับตัวเลขในแอพไม่ตรงกันได้
    const fetchSpy = vi.spyOn(globalThis, 'fetch')
    syncBadge(42)
    expect(fetchSpy).not.toHaveBeenCalled()
    fetchSpy.mockRestore()
  })
})

describe('badge — การกลับมาโฟกัส (visibilitychange)', () => {
  it('B9: ★ กลับมาโฟกัส → เขียนยอดล่าสุดทับทันที (แทน "จุด" ที่ service worker ตั้งไว้)', () => {
    syncBadge(7)
    setAppBadge.mockClear()

    // ระหว่างที่ซ่อนอยู่ service worker เขียนทับด้วยจุด (เราไม่รู้จากฝั่งนี้)
    fireVisibility(true)
    // ⚠️ ขณะซ่อนต้องไม่ทำอะไร — ตัวเลขบนไอคอนตอนผู้ใช้ไม่มองไม่มีความหมาย
    //    และจะเป็นการเขียนทับจุดที่ SW เพิ่งตั้งโดยไม่มีเหตุ
    expect(setAppBadge).not.toHaveBeenCalled()

    // กลับมาโฟกัส → ต้องทับด้วยยอดที่แอพรู้ (ไม่ต้องรอ poll 30 วิ)
    fireVisibility(false)
    expect(setAppBadge).toHaveBeenCalledWith(7)
  })

  it('B10: ★ หลัง `clearBadge()` (ออกจากระบบ) → กลับมาโฟกัสต้อง **ไม่** ปลุกยอดเก่ากลับมา', () => {
    syncBadge(9)
    clearBadge()
    setAppBadge.mockClear()

    fireVisibility(false)

    // ยอดของคนก่อนหน้าต้องไม่โผล่กลับให้คนถัดไปที่มองหน้าจอเห็น
    expect(setAppBadge).not.toHaveBeenCalled()
  })

  it('B11: ยังไม่เคยตั้งยอดเลย → กลับมาโฟกัสไม่ตั้งอะไร (ไม่เดา)', () => {
    setAppBadge.mockClear()
    fireVisibility(true)
    fireVisibility(false)
    expect(setAppBadge).not.toHaveBeenCalled()
  })
})
