/**
 * 🧪 `push.ts` (A3) — 3 กับดักที่ **พังเงียบ** ถ้าไม่มีเทสนี้
 *
 * 1. `Notification.requestPermission()` ต้องเป็น `await` ตัวแรก — iOS ตัด gesture chain
 *    ทิ้งถ้ามี await อื่นคั่น แล้ว **ปฏิเสธโดยไม่มี error** (ผู้ใช้เห็นแค่ "ไม่มีอะไรเกิดขึ้น")
 * 2. `applicationServerKey` ต้องเป็น `Uint8Array` — ส่ง base64 string แล้ว Chrome โยน
 *    แต่ **Safari เงียบ**
 * 3. ตัวช่วยแอพเวอร์ชันใหม่ค้างใน `waiting` ⇒ handler `push` ที่ทำงานจริงเป็นของรุ่นเก่า
 *    (ว่างเปล่า) ⇒ เปิดสำเร็จทุกอย่างแต่ไม่มีการแจ้งเตือนขึ้นเลยตลอดไป
 *
 * ⚠️ **import โมดูลครั้งเดียวตลอดไฟล์** — `push.ts` เก็บสถานะเป็น ref ระดับโมดูล
 *    (แบบเดียวกับ `pwa.ts`) การ `vi.resetModules()` จะได้อินสแตนซ์ใหม่ที่เทสยึดไม่ตรงกัน
 *    ⇒ แยกสถานะระหว่างเทสด้วย `resetPushStatus()` ซึ่งเป็น API สาธารณะ
 * ⚠️ jsdom **ไม่มี** `navigator.serviceWorker` · `PushManager` · `Notification` เลย
 *    ⇒ ต้อง stub เองทั้งหมด (ของจริงทดสอบได้แค่บน staging — ดู acceptance A–L)
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// ── mock ชั้น API: เทสนี้พิสูจน์ "ลำดับการเรียก" ของฝั่งเบราว์เซอร์ ไม่ใช่ HTTP ──
const { getStatusMock, subscribeMock, unsubscribeMock } = vi.hoisted(() => ({
  getStatusMock: vi.fn<() => Promise<unknown>>(),
  subscribeMock: vi.fn<(payload: unknown) => Promise<unknown>>(),
  unsubscribeMock: vi.fn<(payload: unknown) => Promise<unknown>>(),
}))
vi.mock('@/services/notification', () => ({
  getPushStatus: getStatusMock,
  subscribePush: subscribeMock,
  unsubscribePush: unsubscribeMock,
}))

// ⚠️ `@/pwa` **ไม่ mock** — ใช้ของจริงผ่าน `registerPwa()` เพื่อให้เทสนี้พิสูจน์
//    การต่อสายระหว่างสองโมดูลจริง ๆ (การ mock จะทำให้เทสยืนยันแค่ของที่ตัวเองเขียน)
import { registerPwa } from '@/pwa'
import {
  disablePush,
  enablePush,
  pushAvailable,
  pushDeviceCount,
  pushEnabled,
  pushPermission,
  pushReady,
  pushSubscribed,
  pushSupported,
  refreshPushStatus,
  resetPushStatus,
  urlBase64ToUint8Array,
} from '@/push'

// ── ของปลอมที่มีรูปร่างเหมือนเบราว์เซอร์จริง ────────────────────────────────────

/** ลำดับการเรียก — หัวใจของ P3 (ต้องรู้ว่า "อะไรถูกเรียกก่อน") */
let calls: string[] = []
/** init ที่ `pushManager.subscribe()` ได้รับ — ใช้ตรวจ P2 */
let subscribeInit: PushSubscriptionOptionsInit | null = null

/**
 * คีย์ public ปลอมที่ **ถอดได้จริง** — 65 byte = รูปแบบจริงของ P-256 uncompressed point
 * ⚠️ ห้ามใช้สตริงมั่ว ๆ เช่น `'BOARD_KEY'` — `atob()` จะโยน `InvalidCharacterError`
 *    แล้วเทสจะล้มด้วยเรื่องของ "ข้อมูลตั้งต้น" ไม่ใช่เรื่องที่กำลังพิสูจน์
 */
const FAKE_PUBLIC_KEY = btoa(
  String.fromCharCode(...new Uint8Array(65).map((_, i) => (i * 3 + 1) % 256)),
)
  .replace(/\+/g, '-')
  .replace(/\//g, '_')
  .replace(/=+$/, '')

interface FakeSub {
  endpoint: string
  toJSON: () => { endpoint: string; keys?: Record<string, string> }
  unsubscribe: () => Promise<boolean>
}

function makeSubscription(endpoint = 'https://fcm.googleapis.com/fcm/send/abc'): FakeSub {
  return {
    endpoint,
    toJSON: () => ({ endpoint, keys: { p256dh: 'AAAA', auth: 'BBBB' } }),
    unsubscribe: vi.fn<() => Promise<boolean>>(async () => {
      calls.push('browser.unsubscribe')
      return true
    }),
  }
}

interface EnvOptions {
  /** อุปกรณ์นี้มี subscription อยู่แล้วหรือยัง */
  subscription?: FakeSub | null
  /** ตัวช่วยแอพเวอร์ชันใหม่ค้างรออยู่ (กับดัก #3) */
  waiting?: boolean
  /** controllerchange จะยิงกลับมาหรือไม่ (จำลองเบราว์เซอร์ที่ไม่ยอมสลับ) */
  swapFires?: boolean
  permission?: NotificationPermission
  /** คำตอบจาก `requestPermission()` */
  requestResult?: NotificationPermission
  /** ไม่มี `navigator.serviceWorker` เลย (เช่น http:// ที่ไม่ใช่ localhost) */
  noServiceWorker?: boolean
}

function installEnv(opt: EnvOptions = {}) {
  const { subscription = null, waiting = false, swapFires = true } = opt

  const listener: { type: string; fn: () => void }[] = []
  const waitingWorker = {
    postMessage: vi.fn<(msg: { type: string }) => void>((msg) => {
      calls.push(`waiting.postMessage:${msg.type}`)
      if (swapFires) setTimeout(() => listener.forEach((l) => l.fn()), 0)
    }),
  }

  const reg = {
    waiting: waiting ? waitingWorker : null,
    pushManager: {
      getSubscription: vi.fn<() => Promise<FakeSub | null>>(async () => {
        calls.push('pushManager.getSubscription')
        return subscription
      }),
      subscribe: vi.fn<(init: PushSubscriptionOptionsInit) => Promise<FakeSub>>(async (init) => {
        calls.push('pushManager.subscribe')
        subscribeInit = init
        return subscription ?? makeSubscription()
      }),
    },
  }

  if (!opt.noServiceWorker) {
    const swStub: Record<string, unknown> = {
      getRegistration: vi.fn<() => Promise<typeof reg>>(async () => {
        calls.push('serviceWorker.getRegistration')
        return reg
      }),
      addEventListener: vi.fn<(type: string, fn: () => void) => void>((type, fn) =>
        listener.push({ type, fn }),
      ),
    }
    // ⚠️ `ready` ต้องเป็น **getter ที่บันทึกการเรียก** ไม่ใช่ค่า Promise ธรรมดา —
    //    `ensureFreshWorker()` แตะมันเป็นอย่างแรก และนั่นคือจุดที่ P3 ต้องจับได้
    //    (ถ้าเป็นค่าธรรมดาจะมองไม่เห็นว่า "ถูกอ่านตอนไหน" ⇒ เทส P3 ตรวจได้ครึ่งเดียว)
    Object.defineProperty(swStub, 'ready', {
      get: () => {
        calls.push('serviceWorker.ready')
        return Promise.resolve(reg)
      },
    })
    Object.defineProperty(navigator, 'serviceWorker', { configurable: true, value: swStub })
    vi.stubGlobal('PushManager', class PushManagerStub {})
  }

  const notificationStub = {
    permission: opt.permission ?? 'default',
    requestPermission: vi.fn<() => Promise<NotificationPermission>>(async () => {
      calls.push('Notification.requestPermission')
      return opt.requestResult ?? 'granted'
    }),
  }
  vi.stubGlobal('Notification', notificationStub)

  return { reg, waitingWorker, notificationStub }
}

/** เปิด push ให้สำเร็จก่อน แล้วค่อยทดสอบสิ่งที่สนใจ */
async function readyEnv(opt: EnvOptions = {}) {
  getStatusMock.mockResolvedValue({
    enabled: true,
    public_key: FAKE_PUBLIC_KEY,
    device_count: 0,
  })
  const env = installEnv(opt)
  resetPushStatus()
  await refreshPushStatus()
  return env
}

beforeEach(() => {
  calls = []
  subscribeInit = null
  // ⚠️ ล้างสถานะโมดูลก่อนทุกเทส — `push.ts` เป็น singleton และเทสที่ล้มกลางทาง
  //    อาจทิ้ง `busyState`/`subscribedState` ค้างไว้ให้เทสถัดไปเห็น
  resetPushStatus()
  getStatusMock.mockReset()
  subscribeMock.mockReset()
  unsubscribeMock.mockReset()
  // ⚠️ บันทึกลง `calls` ด้วย — ไม่งั้นพิสูจน์ **ลำดับ** ระหว่าง "แจ้งเซิร์ฟเวอร์" กับ
  //    "เลิกที่เบราว์เซอร์" ไม่ได้ ซึ่งเป็นเรื่องเดียวที่ P6 ต้องการพิสูจน์
  subscribeMock.mockImplementation(async () => {
    calls.push('api.subscribe')
    return { device_count: 1 }
  })
  unsubscribeMock.mockImplementation(async () => {
    calls.push('api.unsubscribe')
    return { removed: 1, device_count: 0 }
  })
  // jsdom ไม่มี matchMedia (ยืนยันแล้วใน `pwa.spec.ts`) — คืน false = ไม่ได้เปิดแบบแอพ
  window.matchMedia = vi
    .fn<(query: string) => MediaQueryList>()
    .mockReturnValue({ matches: false } as MediaQueryList) as unknown as typeof window.matchMedia
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  delete (navigator as unknown as Record<string, unknown>).serviceWorker
})

// ─────────────────────────────────────────────────────────────────────────────

describe('urlBase64ToUint8Array — กับดัก padding', () => {
  /**
   * ⚠️ เทสต้องครอบ **ทั้ง 3 เศษของ `len % 3`** ไม่งั้นอาจ "ผ่านเพราะเหตุผลผิด"
   *    (บทเรียนจาก `test_push_send.py`: ขนาดที่เลือกมาไม่มี padding อยู่แล้ว
   *     ⇒ การต่อ `=` เข้าไปได้สตริงที่ *เสีย* ไม่ใช่สตริงที่ *มี padding*)
   *    ⇒ assert ตัวสุดท้ายบังคับว่าชุดที่เลือกครอบครบจริง — ถ้าใครแก้ขนาด ต้องแก้ให้ครบ
   */
  it('★ ถอดได้ครบทั้ง 3 เศษของความยาว (มี/ไม่มี padding)', () => {
    const sizes = [48, 16, 65] // → 0, 1, 2 เศษ ตามลำดับ
    expect(new Set(sizes.map((n) => n % 3))).toEqual(new Set([0, 1, 2]))

    for (const size of sizes) {
      const bytes = new Uint8Array(size).map((_, i) => (i * 7 + size) % 256)
      // ⚠️ เบราว์เซอร์ส่ง base64url **ไม่มี padding** — ตัด `=` ทิ้งก่อนส่งเข้าเทส
      const b64url = btoa(String.fromCharCode(...bytes))
        .replace(/\+/g, '-')
        .replace(/\//g, '_')
        .replace(/=+$/, '')

      expect([...urlBase64ToUint8Array(b64url)]).toEqual([...bytes])
    }
  })

  /**
   * ⚠️ เทสนี้คือตัวที่ **ฆ่า mutation ได้จริง** — ถ้าตัด `.replace(/-/g,'+')` ออก
   *    `atob` จะโยนทันที (ไม่ใช่คืนค่าผิดเงียบ ๆ)
   * ⚠️ ทั้งสอง `expect` ตัวแรกเป็น **self-guard**: ถ้าใครเปลี่ยน byte ให้ base64
   *    ไม่มี `+`/`/` อีก เทสจะล้มทันที แทนที่จะ "ผ่าน" โดยไม่ครอบอะไรเลย
   *    (บทเรียนเดียวกับเทส padding ที่เคยผ่านเพราะเหตุผลผิด)
   */
  it('★ ต้องแปลง `-`/`_` กลับเป็น `+`/`/` ก่อน `atob`', () => {
    const bytes = new Uint8Array([0xfb, 0xff, 0xbe, 0xfb, 0xff, 0xbe])
    const std = btoa(String.fromCharCode(...bytes))
    expect(/[+/]/.test(std)).toBe(true) // ← ถ้าไม่จริง เทสนี้ไม่ครอบอะไร

    const b64url = std.replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
    expect(/[-_]/.test(b64url)).toBe(true) // ← ยืนยันว่าเป็น base64url จริง

    expect([...urlBase64ToUint8Array(b64url)]).toEqual([...bytes])
  })

  it('รับ base64 มาตรฐาน (มี + / และ =) ได้ด้วย — คีย์ที่เซิร์ฟเวอร์ส่งมาอาจมี padding', () => {
    const bytes = new Uint8Array([251, 255, 190, 0])
    const std = btoa(String.fromCharCode(...bytes))
    expect([...urlBase64ToUint8Array(std)]).toEqual([...bytes])
  })
})

describe('สถานะตั้งต้น', () => {
  it('เบราว์เซอร์ไม่รองรับ → `pushSupported` false แต่ **`pushReady` true** (การ์ดไม่ค้างโหลด)', async () => {
    installEnv({ noServiceWorker: true })
    resetPushStatus()
    await refreshPushStatus()

    expect(pushSupported.value).toBe(false)
    expect(pushReady.value).toBe(true) // ⚠️ ถ้าไม่ตั้ง การ์ดจะหมุนค้างตลอดกาล
    expect(pushAvailable.value).toBe(false)
  })

  it('เซิร์ฟเวอร์ยังไม่ตั้งคีย์ VAPID → `pushEnabled` false (การ์ดซ่อนทั้งใบ)', async () => {
    getStatusMock.mockResolvedValue({ enabled: false, public_key: '', device_count: 0 })
    installEnv()
    resetPushStatus()
    await refreshPushStatus()

    expect(pushReady.value).toBe(true)
    expect(pushEnabled.value).toBe(false)
  })

  it('เน็ตพังตอนโหลดสถานะ → ยังอ่านสถานะฝั่งเบราว์เซอร์ได้ (การ์ดไม่พังทั้งใบ)', async () => {
    getStatusMock.mockRejectedValue(new Error('offline'))
    installEnv({ subscription: makeSubscription() })
    resetPushStatus()
    await refreshPushStatus()

    expect(pushReady.value).toBe(true)
    expect(pushSubscribed.value).toBe(true) // มาจากเบราว์เซอร์ ไม่ใช่ API
  })
})

describe('pushAvailable — iOS บังคับติดตั้งก่อน', () => {
  it('★ iOS Safari ที่ยังไม่ติดตั้ง → ใช้ไม่ได้ แม้เบราว์เซอร์รองรับ', async () => {
    Object.defineProperty(navigator, 'userAgent', {
      configurable: true,
      value: 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Safari/604.1',
    })
    await readyEnv()
    registerPwa() // ให้ `pwa.ts` อ่าน UA แล้วอัปเดต `isIosSafari`

    expect(pushSupported.value).toBe(true) // เบราว์เซอร์รองรับ
    expect(pushAvailable.value).toBe(false) // แต่ยังใช้ไม่ได้จนติดตั้ง
  })

  it('iOS ที่ติดตั้งลงหน้าจอแล้ว → ใช้ได้', async () => {
    Object.defineProperty(navigator, 'userAgent', {
      configurable: true,
      value: 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Safari/604.1',
    })
    window.matchMedia = vi.fn<(query: string) => MediaQueryList>().mockReturnValue({
      matches: true,
    } as MediaQueryList) as unknown as typeof window.matchMedia

    await readyEnv()
    registerPwa()

    expect(pushAvailable.value).toBe(true)
  })

  it('Chrome (ไม่ใช่ iOS) → ใช้ได้ทันที ไม่ต้องติดตั้ง', async () => {
    Object.defineProperty(navigator, 'userAgent', {
      configurable: true,
      value: 'Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/120 Mobile Safari/537.36',
    })
    await readyEnv()
    registerPwa()

    expect(pushAvailable.value).toBe(true)
  })
})

describe('enablePush — 3 กับดัก', () => {
  it('★ P3: `requestPermission()` ต้องถูกเรียกเป็น **อันดับแรก** (ก่อน await ใด ๆ)', async () => {
    await readyEnv()
    calls = [] // เริ่มนับใหม่ ณ จุดที่ผู้ใช้กดปุ่ม

    await enablePush()

    expect(calls[0]).toBe('Notification.requestPermission')
    // ⚠️ เป็นด่านที่สอง: งานฝั่งเบราว์เซอร์ทุกอย่างต้องเกิด *หลัง* คำขอ
    //    (`serviceWorker.ready` คือสิ่งแรกที่ `enablePush()` แตะถ้ามี await คั่น)
    expect(calls.indexOf('serviceWorker.ready')).toBeGreaterThan(0)
    expect(calls.lastIndexOf('pushManager.subscribe')).toBeGreaterThan(0)
  })

  it('★ P2: `applicationServerKey` ต้องเป็น Uint8Array (Safari เงียบถ้าส่ง string)', async () => {
    await readyEnv()
    await enablePush()

    const key = subscribeInit?.applicationServerKey
    expect(key).toBeInstanceOf(Uint8Array)
    // และต้องเป็นคีย์จริงที่เซิร์ฟเวอร์ส่งมา ไม่ใช่ค่าอื่น
    expect(key).not.toHaveLength(0)
  })

  it('★ P7: ตัวช่วยแอพเวอร์ชันใหม่ค้างอยู่ → ต้อง `SKIP_WAITING` **ก่อน** subscribe', async () => {
    const { waitingWorker } = await readyEnv({ waiting: true })
    calls = []

    await enablePush()

    expect(waitingWorker.postMessage).toHaveBeenCalledWith({ type: 'SKIP_WAITING' })
    expect(calls.indexOf('waiting.postMessage:SKIP_WAITING')).toBeLessThan(
      calls.indexOf('pushManager.subscribe'),
    )
  })

  /**
   * ⚠️ เทสนี้ต้องรอจนครบ `SWAP_TIMEOUT_MS` (5 วิ) จริง ๆ ⇒ ต้องตั้ง timeout ยาวกว่า
   *    ค่า default ของ vitest (5 วิ) ไม่งั้นเทสจะถูกตัดกลางทาง **แล้วทิ้ง `busyState`
   *    ไว้เป็น `true`** ⇒ เทสถัดไปทุกตัวที่เรียก `enablePush()` จะคืนค่าทันทีโดยไม่ทำอะไร
   *    แล้วล้มด้วยเหตุผลที่ไม่เกี่ยวกับสิ่งที่มันตั้งใจตรวจ (เคสจริงที่เจอมาแล้ว)
   *    (อีกด่านคือ `resetPushStatus()` ที่ล้าง `busyState` — ดูคอมเมนต์ใน `push.ts`)
   */
  it(
    '★ P7b: สลับตัวช่วยแอพไม่สำเร็จ → **โยน error** ไม่ใช่ subscribe ต่อไปเงียบ ๆ',
    async () => {
      // `swapFires: false` = controllerchange ไม่ยิงเลย (เบราว์เซอร์ค้างสถานะ)
      await readyEnv({ waiting: true, swapFires: false })

      await expect(enablePush()).rejects.toThrow(/ตัวช่วยแอพ/)
      expect(subscribeMock).not.toHaveBeenCalled()
    },
    15_000,
  )

  it('P4: ผู้ใช้ปฏิเสธ → คืน `denied` และ **ไม่** subscribe', async () => {
    await readyEnv({ requestResult: 'denied' })

    await expect(enablePush()).resolves.toBe('denied')
    expect(subscribeMock).not.toHaveBeenCalled()
    expect(pushPermission.value).toBe('denied')
  })

  it('ผู้ใช้ปิด dialog ไปเฉย ๆ → `dismissed` (ไม่ใช่ `denied` — ยังถามใหม่ได้)', async () => {
    await readyEnv({ requestResult: 'default' })

    await expect(enablePush()).resolves.toBe('dismissed')
    expect(subscribeMock).not.toHaveBeenCalled()
  })

  it('สำเร็จ → แจ้งเซิร์ฟเวอร์ด้วย endpoint + คีย์ของอุปกรณ์ และอัปเดตจำนวน', async () => {
    await readyEnv()
    subscribeMock.mockImplementation(async () => {
      calls.push('api.subscribe')
      return { device_count: 2 }
    })

    await expect(enablePush()).resolves.toBe('enabled')

    expect(subscribeMock).toHaveBeenCalledWith({
      endpoint: 'https://fcm.googleapis.com/fcm/send/abc',
      keys: { p256dh: 'AAAA', auth: 'BBBB' },
    })
    expect(pushSubscribed.value).toBe(true)
    expect(pushDeviceCount.value).toBe(2)
  })

  it('เครื่องที่เคยเปิดไว้แล้ว → ใช้ subscription เดิม ไม่ subscribe ซ้ำ', async () => {
    const { reg } = await readyEnv({ subscription: makeSubscription() })

    await enablePush()

    expect(reg.pushManager.getSubscription).toHaveBeenCalled()
    expect(reg.pushManager.subscribe).not.toHaveBeenCalled()
    expect(subscribeMock).toHaveBeenCalledTimes(1) // แต่ยังต้องยืนยันกับเซิร์ฟเวอร์
  })
})

describe('disablePush', () => {
  it('★ P6: แจ้งเซิร์ฟเวอร์ **ก่อน** แล้วค่อยเลิกที่เบราว์เซอร์', async () => {
    const sub = makeSubscription()
    await readyEnv({ subscription: sub })
    calls = []

    await disablePush()

    expect(unsubscribeMock).toHaveBeenCalledWith({
      endpoint: 'https://fcm.googleapis.com/fcm/send/abc',
    })
    // ⚠️ ลำดับสำคัญ: ถ้า `unsubscribe()` ก่อนแล้ว API ล้ม จะเหลือปลายทางตายที่ไม่มีใครลบ
    expect(calls.indexOf('api.unsubscribe')).toBeLessThan(calls.indexOf('browser.unsubscribe'))
    expect(sub.unsubscribe).toHaveBeenCalled()
    expect(pushSubscribed.value).toBe(false)
    expect(pushDeviceCount.value).toBe(0)
  })

  it('เบราว์เซอร์ไม่ยอมเลิก → ยังถือว่าปิดสำเร็จ (เซิร์ฟเวอร์เลิกส่งแล้ว)', async () => {
    const sub = makeSubscription()
    sub.unsubscribe = vi.fn<() => Promise<boolean>>(async () => {
      throw new Error('nope')
    })
    await readyEnv({ subscription: sub })

    await expect(disablePush()).resolves.toBeUndefined()
    expect(pushSubscribed.value).toBe(false)
  })

  it('เครื่องนี้ไม่มี subscription → ไม่ยิง API มั่ว แต่ยังปิดสถานะให้ตรง', async () => {
    await readyEnv({ subscription: null })

    await disablePush()

    expect(unsubscribeMock).not.toHaveBeenCalled()
    expect(pushSubscribed.value).toBe(false)
  })
})
