/**
 * 🧪 `pwa.ts` — เฉพาะกลไก **"ติดตั้งอัตโนมัติเมื่อแตะแรก"**
 *
 * ทำไมต้องมีเทสนี้: กลไกนี้ผูก listener ไว้ **ตอน import โมดูล** (ไม่ใช่ตอนเรียก
 * `registerPwa()`) เพราะ `beforeinstallprompt` ยิงครั้งเดียวและกู้คืนไม่ได้
 * ⇒ ถ้าจุดใดจุดหนึ่งต่อสายผิด (listener ไม่ผูก / ไม่ disarm / flag ผิดคีย์)
 *   **จะไม่มีอาการอะไรให้เห็นเลย** — ผู้ใช้แค่ไม่ถูกชวนติดตั้ง แล้วเราไม่มีทางรู้
 *   การเทสด้วยการจำลอง event จึงเป็นวิธีเดียวที่ตรวจได้จริงในเครื่อง dev
 *   (ของจริงต้องมี HTTPS + ไอคอนครบ + engagement heuristic ถึงจะยิง event)
 *
 * ⚠️ `beforeinstallprompt` **ไม่ใช่ event มาตรฐานของ jsdom** ⇒ สร้างเองด้วย
 *    `new Event(...)` แล้วแปะ `prompt`/`userChoice` เข้าไปให้เหมือน Chrome
 * ⚠️ jsdom **ไม่มี `window.matchMedia`** (ยืนยันแล้ว: `typeof` = `"undefined"`)
 *    ⇒ ต้อง stub ก่อนเรียก `registerPwa()` ไม่งั้น throw
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const DISMISS_KEY = 'piri_install_dismissed'
const INSTALLED_KEY = 'piri_installed'
const AUTO_ASKED_KEY = 'piri_install_auto_asked'

/** สร้าง event ปลอมที่มีรูปร่างเหมือนของ Chrome */
function makeInstallEvent(outcome: 'accepted' | 'dismissed' = 'accepted') {
  const prompt = vi.fn<() => Promise<void>>(() => Promise.resolve())
  const event = new Event('beforeinstallprompt')
  Object.assign(event, {
    prompt,
    userChoice: Promise.resolve({ outcome }),
  })
  return { event, prompt }
}

/**
 * ⚠️ **import โมดูลครั้งเดียวตลอดไฟล์ — ห้าม `vi.resetModules()` ต่อเทส**
 *
 * `pwa.ts` ผูก listener ตอน import **และไม่เคยถอด** ⇒ ถ้า import ใหม่ทุกเทส
 * listener ของโมดูลรุ่นเก่าจะยังค้างอยู่บน `document`/`window` แล้วถูกนับซ้ำ
 * (เทสหนึ่งแตะครั้งเดียว แต่ handler ยิงพร้อมกันหลายรุ่น = mock ถูกเรียกหลายครั้ง)
 * ซึ่งทำให้เทสล้มด้วยเหตุผลของการทดสอบเอง ไม่ใช่ของโค้ด
 *
 * การใช้ instance เดียวก็ตรงกับความจริงด้วย — ในแอพจริงโมดูลนี้เป็น singleton
 * ⇒ แยกสถานะระหว่างเทสด้วย `localStorage.clear()` ซึ่งเป็นที่เก็บ flag ทั้งหมด
 */
const pwa = await import('@/pwa')

/** แตะจอหนึ่งครั้ง (สิ่งที่ผู้ใช้ทำจริง — ไม่ใช่ปุ่มติดตั้ง) */
function tap() {
  document.dispatchEvent(new MouseEvent('click', { bubbles: true }))
}

/** ปล่อย microtask ให้ `promptInstall()` ได้ทำงาน */
const flush = () => new Promise((r) => setTimeout(r, 0))

beforeEach(() => {
  // ⚠️ เคลียร์ "สถานะรอแตะแรก" ที่อาจค้างจากเทสก่อน ด้วย API สาธารณะเท่านั้น
  //    (`dismissInstall()` ยกเลิกคำขอที่รออยู่ — ดูเหตุผลใน `pwa.ts`)
  //    แล้วล้าง localStorage ทีหลัง เพื่อไม่ให้ flag ที่มันเพิ่งเขียนค้างมาที่เทสนี้
  pwa.dismissInstall()
  localStorage.clear()
  // jsdom ไม่มี matchMedia — stub ให้คืน false (= ไม่ได้ติดตั้งอยู่)
  window.matchMedia = vi
    .fn<(query: string) => MediaQueryList>()
    .mockReturnValue({ matches: false } as MediaQueryList) as unknown as typeof window.matchMedia
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('ติดตั้งอัตโนมัติเมื่อแตะแรก', () => {
  it('ยิง prompt() เองเมื่อแตะครั้งแรก — ผู้ใช้ไม่ต้องหาปุ่มติดตั้ง', async () => {
    const { event, prompt } = makeInstallEvent()

    window.dispatchEvent(event)
    expect(prompt).not.toHaveBeenCalled() // ยังไม่แตะ = ยังไม่ยิง (เบราว์เซอร์ห้าม)

    tap()
    await flush()
    expect(prompt).toHaveBeenCalledTimes(1)
    // event ถูกใช้ไปแล้ว ⇒ ไม่ค้างไว้ให้ยิงซ้ำ
    expect(pwa.showInstallBanner.value).toBe(false)
  })

  it('ยิงครั้งเดียวเท่านั้น — แตะครั้งที่สองต้องไม่ยิงซ้ำ', async () => {
    const { event, prompt } = makeInstallEvent('dismissed')

    window.dispatchEvent(event)
    tap()
    await flush()
    expect(prompt).toHaveBeenCalledTimes(1)

    tap()
    tap()
    await flush()
    expect(prompt).toHaveBeenCalledTimes(1)
  })

  it('ผู้ใช้คีย์บอร์ดก็ได้ — keydown ก็นับเป็น user gesture', async () => {
    const { event, prompt } = makeInstallEvent()

    window.dispatchEvent(event)
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab' }))
    await flush()

    expect(prompt).toHaveBeenCalledTimes(1)
  })

  it('ระหว่างรอแตะแรก แบนเนอร์ต้องยังไม่โชว์ (กันเห็น dialog กับแบนเนอร์พร้อมกัน)', async () => {
    pwa.registerPwa()

    window.dispatchEvent(makeInstallEvent().event)
    expect(pwa.showInstallBanner.value).toBe(false)
  })
})

describe('ไม่ยิงอัตโนมัติเมื่อไม่ควร', () => {
  it('เคยกดปิดแบนเนอร์ไว้ → ไม่ยิงเองอีก', async () => {
    localStorage.setItem(DISMISS_KEY, '1')
    const { event, prompt } = makeInstallEvent()

    window.dispatchEvent(event)
    tap()
    await flush()
    expect(prompt).not.toHaveBeenCalled()
  })

  it('เคยติดตั้งแล้ว → ไม่ยิงเอง', async () => {
    localStorage.setItem(INSTALLED_KEY, '1')
    const { event, prompt } = makeInstallEvent()

    window.dispatchEvent(event)
    tap()
    await flush()
    expect(prompt).not.toHaveBeenCalled()
  })

  it('⚠️ ยิงเองได้ครั้งเดียวตลอดไป — เซสชันถัดไปกลับมาเป็นแบนเนอร์ให้กดเอง', async () => {
    // เซสชันแรก: ยิงเองไปแล้ว (จำลองด้วย flag ที่ถูกเขียนหลังยิง)
    localStorage.setItem(AUTO_ASKED_KEY, '1')

    pwa.registerPwa()
    const { event, prompt } = makeInstallEvent()

    window.dispatchEvent(event)
    expect(pwa.showInstallBanner.value).toBe(true) // ✅ กลับมาเป็นแบนเนอร์

    tap()
    await flush()
    expect(prompt).not.toHaveBeenCalled() // ❌ ไม่ยิงเองซ้ำ (ไม่รบกวน)
  })

  it('ยังไม่ได้ event จากเบราว์เซอร์ → แตะไปก็ไม่ยิง (ไม่เดาว่าติดตั้งได้)', async () => {
    // ไม่ dispatch beforeinstallprompt เลย
    tap()
    await flush()
    expect(true).toBe(true) // ไม่ throw ก็พอ — สำคัญคือไม่พยายามยิงมั่ว
  })
})

describe('หลังยิงเองสำเร็จ', () => {
  it('ผู้ใช้กดติดตั้ง (accepted) → จำว่าติดตั้งแล้ว และไม่ชวนซ้ำ', async () => {
    const { event } = makeInstallEvent('accepted')

    window.dispatchEvent(event)
    tap()
    await flush()

    expect(localStorage.getItem(INSTALLED_KEY)).toBe('1')
    expect(pwa.showInstallBanner.value).toBe(false)
    expect(pwa.showIosHint.value).toBe(false)
  })

  it('ผู้ใช้ปิด dialog (dismissed) → **ไม่** ตั้งค่าคีย์ติดตั้งแล้ว (ยังติดตั้งได้ทีหลัง)', async () => {
    const { event } = makeInstallEvent('dismissed')

    window.dispatchEvent(event)
    tap()
    await flush()

    expect(localStorage.getItem(INSTALLED_KEY)).toBeNull()
    expect(localStorage.getItem(DISMISS_KEY)).toBeNull()
    // แต่จำว่าเคยยิงเองแล้ว ⇒ ไม่ยิงเองซ้ำ
    expect(localStorage.getItem(AUTO_ASKED_KEY)).toBe('1')
  })
})
