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
// ⚠️ `import type` เท่านั้น — ถูกลบตอนคอมไพล์ จึง **ไม่สร้างโมดูลอินสแตนซ์ที่สอง**
//    (การ import ของจริงยังเป็น `await import` ข้างล่าง ซึ่งตั้งใจให้เป็นตัวเดียวตลอดไฟล์)
import type { InstallDiagnostics } from '@/pwa'

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

beforeEach(async () => {
  // ⚠️ `deferredPrompt` เป็น state ระดับโมดูล และ **`dismissInstall()` ไม่ได้ล้างมันให้**
  //    (เจตนา — การ์ด "ติดตั้งแอพ" ใน Profile ต้องเรียกใช้ต่อได้หลังผู้ใช้กด ✕)
  //    ⇒ เทสที่ dispatch event แต่ **ไม่ยิง prompt** จะเหลือ event ค้างไปเทสถัดไป
  //    ⇒ ต้องบริโภคทิ้งด้วย API สาธารณะก่อน (`'dismissed'` = ไม่เขียนธงใด ๆ)
  window.dispatchEvent(makeInstallEvent('dismissed').event)
  await pwa.promptInstall()

  // ⚠️ เคลียร์ "สถานะรอแตะแรก" ที่อาจค้างจากเทสก่อน ด้วย API สาธารณะเท่านั้น
  //    (`dismissInstall()` ยกเลิกคำขอที่รออยู่ — ดูเหตุผลใน `pwa.ts`)
  //    แล้วล้าง localStorage ทีหลัง เพื่อไม่ให้ flag ที่มันเพิ่งเขียนค้างมาที่เทสนี้
  pwa.dismissInstall()
  localStorage.clear()
  // jsdom ไม่มี matchMedia — stub ให้คืน false (= ไม่ได้ติดตั้งอยู่)
  window.matchMedia = vi
    .fn<(query: string) => MediaQueryList>()
    .mockReturnValue({ matches: false } as MediaQueryList) as unknown as typeof window.matchMedia
  // ⚠️ `standaloneState` ก็เป็น state ระดับโมดูลเหมือนกัน — ต้องรีเซ็ตทุกเทส
  //    ไม่งั้นเทสที่ตั้ง matchMedia(true) จะทำให้เทสถัดไปเห็น "ติดตั้งแล้ว" ค้างอยู่
  pwa.registerPwa()
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

  /**
   * ⚠️ เทสนี้ **เคยยืนยันว่า "มีธงติดตั้งแล้ว ⇒ ห้ามยิง"** ซึ่งกลายเป็นบั๊ก
   *    — เบราว์เซอร์ **ไม่ยิง `beforeinstallprompt` ให้แอพที่ติดตั้งอยู่แล้ว** ตั้งแต่แรก
   *      ⇒ การเอา `INSTALLED_KEY` มาบล็อกจึงไม่ได้กันอะไร แต่กลับทำให้คนที่
   *        **ถอนแอพแล้ว** ติดตั้งกลับไม่ได้ตลอดไป (ดู describe "ถอนการติดตั้งแล้ว")
   *    ⇒ สิ่งที่ต้องยืนยันจริงคือ "ไม่มี event = ไม่มีอะไรเกิดขึ้น" ไม่ใช่ "ธงบล็อก"
   */
  it('เคยติดตั้งแล้ว → เบราว์เซอร์ไม่ยิง event อยู่แล้ว ⇒ ไม่มีอะไรเกิดขึ้น', async () => {
    localStorage.setItem(INSTALLED_KEY, '1')

    tap()
    await flush()

    expect(pwa.showInstallBanner.value).toBe(false)
    expect(pwa.canPromptInstall.value).toBe(false)
    // ไม่มี event ⇒ ไม่มีอะไรถูกแตะต้อง รวมถึงไม่ไปล้างธงทิ้ง
    expect(localStorage.getItem(INSTALLED_KEY)).toBe('1')
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

describe('ถอนการติดตั้งแล้ว — ต้องติดตั้งกลับได้', () => {
  /**
   * ⚠️ **การถอนแอพไม่ล้าง site data** ⇒ `piri_installed` ค้างอยู่ใน localStorage
   *    ถ้าเอาธงนั้นมาบล็อกการติดตั้ง ผู้ใช้จะ **ไม่มีทางติดตั้งกลับได้อีกเลย**
   *    ทั้งที่เบราว์เซอร์เพิ่งยืนยันว่า "ติดตั้งได้" (มันไม่ยิง event ถ้าติดตั้งอยู่)
   */
  it('★ เบราว์เซอร์ยิง event ใหม่ → ล้างธง "ติดตั้งแล้ว" ที่ค้างอยู่ทิ้ง', async () => {
    localStorage.setItem(INSTALLED_KEY, '1')

    window.dispatchEvent(makeInstallEvent().event)

    expect(localStorage.getItem(INSTALLED_KEY)).toBeNull()
  })

  it('★ คนที่เคยติดตั้ง+ถอน กลับมาเห็นแบนเนอร์อีกครั้ง (เดิมถูกบล็อกถาวร)', async () => {
    // สภาพจริงหลังถอน: เคยถูกถามไปแล้ว (AUTO_ASKED) + ธงติดตั้งยังค้าง
    localStorage.setItem(AUTO_ASKED_KEY, '1')
    localStorage.setItem(INSTALLED_KEY, '1')

    pwa.registerPwa()
    window.dispatchEvent(makeInstallEvent().event)

    expect(pwa.showInstallBanner.value).toBe(true)
  })
})

describe('ติดตั้งเองจากในการ์ด Profile — ทางกลับของคนที่เคยกด ✕', () => {
  it('★ ผู้ที่เคยกด ✕ ปิดไว้ ยังติดตั้งเองได้ และคำสั่งนั้นล้างการปิดทิ้ง', async () => {
    pwa.dismissInstall() // ผู้ใช้กด ✕ ปิดแบนเนอร์
    const { event, prompt } = makeInstallEvent()
    window.dispatchEvent(event)

    expect(pwa.showInstallBanner.value).toBe(false) // แบนเนอร์ไม่ขึ้น (จำการปิดไว้)
    expect(pwa.canPromptInstall.value).toBe(true) // แต่ยังติดตั้งได้

    await pwa.installNow()

    expect(prompt).toHaveBeenCalledTimes(1)
    expect(localStorage.getItem(DISMISS_KEY)).toBeNull()
  })

  it('ไม่มี event จากเบราว์เซอร์ → ติดตั้งเองไม่ได้ (คืน unavailable ไม่ throw)', async () => {
    expect(pwa.canPromptInstall.value).toBe(false)
    await expect(pwa.installNow()).resolves.toBe('unavailable')
  })

  it('กำลังเปิดในโหมดแอพที่ติดตั้งแล้ว → ไม่ต้องติดตั้งซ้ำ', async () => {
    window.matchMedia = vi.fn<(query: string) => MediaQueryList>().mockReturnValue({
      matches: true,
    } as MediaQueryList) as unknown as typeof window.matchMedia

    pwa.registerPwa()
    window.dispatchEvent(makeInstallEvent().event)

    expect(pwa.isStandalone.value).toBe(true)
    expect(pwa.canPromptInstall.value).toBe(false)
  })
})

/**
 * 🔎 ตัววินิจฉัย "ทำไมติดตั้งไม่ได้"
 *
 * ⚠️ `installHintFor()` ถูกแยกเป็นฟังก์ชันบริสุทธิ์เพื่อให้เทส **ป้อนสถานะใดก็ได้** —
 *    ถ้าผูกกับ state ของโมดูลจะทดสอบไม่ได้เลย เพราะ vitest ไม่ลงทะเบียน SW
 *    (`import.meta.env.PROD` เป็น false) ⇒ `swRegistered` เป็น false ตลอด
 *    ⇒ กิ่งหลังจากนั้นแตะไม่ถึง
 */
describe('ตัววินิจฉัยการติดตั้ง', () => {
  /** สถานะตั้งต้น = "ยังไม่ติดตั้ง · ไม่มีอะไรพิเศษ" — เทสแต่ละตัว override เฉพาะที่สนใจ */
  const base: InstallDiagnostics = {
    standalone: false,
    promptReady: false,
    iosSafari: false,
    swRegistered: true,
    dismissed: false,
    autoAsked: false,
    installedBefore: false,
  }
  const hint = (over: Partial<InstallDiagnostics> = {}) =>
    pwa.installHintFor({ ...base, ...over })

  it('★ ได้สัญญาณจากเบราว์เซอร์ → บอกให้กดปุ่มได้เลย', () => {
    expect(hint({ promptReady: true })).toContain('กดปุ่ม')
  })

  it('★ ได้สัญญาณ + เคยกดปิด → ยังต้องบอกให้กดปุ่ม (promptReady ต้องชนะ)', () => {
    // ⚠️ เทสนี้คือหัวใจของลำดับความสำคัญ: ถ้าสลับให้ `dismissed` มาก่อน จะบอกผู้ใช้ว่า
    //    "เคยกดปิดไว้" ทั้งที่ความจริงติดตั้งได้แล้ว ⇒ ชี้ผิดจุด
    const text = hint({ promptReady: true, dismissed: true })
    expect(text).toContain('กดปุ่ม')
    expect(text).not.toContain('เคยกดปิดแบนเนอร์')
  })

  it('Service Worker ไม่ทำงาน → ชี้ที่ตัวช่วยแอพ (สาเหตุที่ลึกกว่าธง)', () => {
    expect(hint({ swRegistered: false, dismissed: true, installedBefore: true })).toContain(
      'Service Worker',
    )
  })

  it('เคยกดปิดแบนเนอร์ → บอกว่าปุ่มด้านบนยังใช้ได้', () => {
    expect(hint({ dismissed: true })).toContain('เคยกดปิดแบนเนอร์ไว้')
  })

  it('★ เคยติดตั้งมาก่อน → ชี้ไปที่ chrome://webapks (เคสจริงที่เจอ)', () => {
    expect(hint({ installedBefore: true })).toContain('chrome://webapks')
  })

  it('ไม่รู้อะไรเลย → บอก 3 สาเหตุที่พบบ่อย ไม่ฟันธงผิด', () => {
    const text = hint()
    expect(text).toContain('LINE/Facebook')
    expect(text).toContain('ยังติดตั้งค้างอยู่')
  })

  it('iOS Safari → สอนปุ่มแชร์ ไม่ใช่บอกว่าเบราว์เซอร์ไม่รองรับ', () => {
    expect(hint({ iosSafari: true })).toContain('แชร์')
  })

  it('เปิดในโหมดแอพอยู่แล้ว → บอกว่าไม่มีอะไรต้องติดตั้ง', () => {
    expect(hint({ standalone: true, promptReady: true })).toContain('โหมดแอพแล้ว')
  })

  it('★ ต่อสายจริง: กด ✕ แล้ว `installDiagnostics` เปลี่ยนตามทันที', async () => {
    // ⚠️ เทสนี้กันบั๊กที่ `readFlag()` ไม่ reactive — ถ้าหน้าจออ่านค่าดิบจาก localStorage
    //    ค่าที่แสดงจะค้างอยู่ที่ตอนโหลดหน้า ผู้ใช้กด ✕ แล้วตัวเลขไม่ขยับ
    expect(pwa.installDiagnostics.value.dismissed).toBe(false)

    pwa.dismissInstall()

    expect(pwa.installDiagnostics.value.dismissed).toBe(true)
    expect(localStorage.getItem(DISMISS_KEY)).toBe('1')
  })
})
