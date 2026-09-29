/**
 * 🧪 `push.ts` (A3 + #44) — 4 กับดักที่ **พังเงียบ** ถ้าไม่มีเทสนี้
 *
 * 1. `Notification.requestPermission()` ต้องเป็น `await` ตัวแรก — iOS ตัด gesture chain
 *    ทิ้งถ้ามี await อื่นคั่น แล้ว **ปฏิเสธโดยไม่มี error** (ผู้ใช้เห็นแค่ "ไม่มีอะไรเกิดขึ้น")
 * 2. `applicationServerKey` ต้องเป็น `Uint8Array` — ส่ง base64 string แล้ว Chrome โยน
 *    แต่ **Safari เงียบ**
 * 3. ตัวช่วยแอพเวอร์ชันใหม่ค้างใน `waiting` ⇒ handler `push` ที่ทำงานจริงเป็นของรุ่นเก่า
 *    (ว่างเปล่า) ⇒ เปิดสำเร็จทุกอย่างแต่ไม่มีการแจ้งเตือนขึ้นเลยตลอดไป
 * 4. **หลัง rotate คีย์ VAPID** เบราว์เซอร์ยังคืน subscription เก่าที่ผูกกับ **คีย์เก่า** ⇒
 *    ปลายทางปฏิเสธทุก push ด้วย 403 ⇒ **การ์ดขึ้น "เปิดอยู่" ตลอดไปโดยไม่มีอะไรมาถึงเลย**
 *    (เงียบที่สุดในสี่ข้อ — ไม่มี error ไม่มี log ฝั่งแอพ) ⇒ `obtainSubscription()` +
 *    `piri_push_key` ใน `localStorage` คือสิ่งที่เทสกลุ่ม K พิสูจน์
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
  describePushError,
  disablePush,
  enablePush,
  pushAvailable,
  pushDeviceCount,
  pushEnabled,
  pushPermission,
  pushReady,
  pushSubscribed,
  pushSubscriptionStale,
  pushSupported,
  refreshPushStatus,
  repairPush,
  resetPushStatus,
  urlBase64ToUint8Array,
} from '@/push'

/**
 * ที่เก็บคีย์ที่ผูกไว้ — **เขียนชื่อซ้ำโดยเจตนา** ไม่ import จาก `push.ts`
 * เพราะมันคือสัญญากับ **เครื่องที่ติดตั้งไปแล้ว**: เปลี่ยนชื่อคีย์นี้ = ทุกเครื่อง
 * จะกลายเป็น "ไม่รู้ว่าผูกกับอะไร" แล้วถูกขอให้เปิดใหม่หนึ่งครั้งโดยไม่จำเป็น
 * ⇒ เทสนี้มีไว้ล็อกชื่อนั้น (ดูคอมเมนต์ `BOUND_KEY_STORAGE` ใน `push.ts`)
 */
const BOUND_KEY_STORAGE = 'piri_push_key'

/** คีย์ที่เครื่องนี้บันทึกไว้ว่า subscription ผูกด้วย (ไม่ตั้งค่า = ยังไม่เคยบันทึก) */
function boundKey(): string | null {
  return localStorage.getItem(BOUND_KEY_STORAGE)
}

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
  /** endpoint ที่จะได้เมื่อ subscribe ใหม่ (ต้องต่างจากของเดิม ไม่งั้นชนด่าน endpoint ซ้ำ) */
  freshEndpoint?: string
  /**
   * เบราว์เซอร์ **ไม่ยอมทิ้ง** ของเดิม — `unsubscribe()` คืน `false` แล้ว subscription ยังอยู่
   * (เคสจริงของ Chrome ⇒ `subscribe()` คืน **ตัวเดิม** กลับมา ⇒ #44 ต้องจับได้ ไม่ใช่เขียนคีย์ทับ)
   */
  stubborn?: boolean
  /** เบราว์เซอร์ **โยน** ตอน `unsubscribe()` — ความล้มเหลวอีกโหมดหนึ่ง (ต่างจาก `stubborn`) */
  unsubscribeError?: boolean
  /** ตัวช่วยแอพเวอร์ชันใหม่ค้างรออยู่ (กับดัก #3) */
  waiting?: boolean
  /** controllerchange จะยิงกลับมาหรือไม่ (จำลองเบราว์เซอร์ที่ไม่ยอมสลับ) */
  swapFires?: boolean
  permission?: NotificationPermission
  /** คำตอบจาก `requestPermission()` */
  requestResult?: NotificationPermission
  /** ไม่มี `navigator.serviceWorker` เลย (เช่น http:// ที่ไม่ใช่ localhost) */
  noServiceWorker?: boolean
  /**
   * ให้ `subscribe()` **ล้มด้วย `AbortError: Registration failed - push service error`**
   * จำนวน N ครั้งแรก — จำลองพฤติกรรมจริงของปลายทางหลังเพิ่ง `unsubscribe()` ไปหมาด ๆ
   * (เครื่องที่ **ไม่เคยเปิด** จะไม่เจอเลย — นั่นคือความต่างที่ทำให้บั๊กนี้ดู "เป็นที่เครื่อง")
   */
  subscribeFailures?: number
  /** ให้ `subscribe()` โยน error นี้ **ทุกครั้ง** — ใช้พิสูจน์ว่า error ที่ลองใหม่ไม่ได้ ไม่ถูกลองใหม่ */
  subscribeAlwaysThrows?: { name: string; message: string }
}

function installEnv(opt: EnvOptions = {}) {
  const { waiting = false, swapFires = true, stubborn = false, unsubscribeError = false } = opt
  const freshEndpoint = opt.freshEndpoint ?? 'https://fcm.googleapis.com/fcm/send/fresh'
  /** นับถอยหลังใน `subscribe()` — สถานะของ *การจำลอง* จึงต้องมีชีวิตอยู่ในฟังก์ชันนี้ */
  let failuresLeft = opt.subscribeFailures ?? 0

  /**
   * ⚠️ "เบราว์เซอร์นี้มี subscription อะไรอยู่" ต้อง **เปลี่ยนได้ระหว่างเทส**
   *    ของเดิมเป็น closure ทับค่าคงที่ `opt.subscription` ⇒ จำลอง "เปิดใหม่แล้วได้ตัวใหม่"
   *    ไม่ได้เลย ซึ่งเป็นพฤติกรรมที่ #44 ทั้งงานต้องพึ่ง (ปิดแล้วเปิดใหม่ = endpoint ใหม่จริง)
   */
  let current: FakeSub | null = null

  /** ห่อ `unsubscribe()` ให้สะท้อนกลับมาที่สถานะจำลอง — ของจริงทำแบบนี้เป๊ะ */
  function bindSub(sub: FakeSub): FakeSub {
    sub.unsubscribe = vi.fn<() => Promise<boolean>>(async () => {
      calls.push('browser.unsubscribe')
      if (stubborn) return false // ไม่ยอมทิ้ง — `current` ยังชี้ตัวเดิม
      if (unsubscribeError) throw new Error('nope')
      current = null
      return true
    })
    return sub
  }

  current = opt.subscription ? bindSub(opt.subscription) : null

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
        return current
      }),
      subscribe: vi.fn<(init: PushSubscriptionOptionsInit) => Promise<FakeSub>>(async (init) => {
        calls.push('pushManager.subscribe')
        subscribeInit = init
        // ⚠️ จำลอง "ปลายทางยังไม่พร้อม" — ของจริงเกิดหลังเพิ่ง unsubscribe() ไปหมาด ๆ
        //    ⇒ ต้องนับถอยหลัง ไม่ใช่ล้มทุกครั้ง (ไม่งั้นพิสูจน์ไม่ได้ว่า "ลองใหม่แล้วสำเร็จ")
        if (failuresLeft > 0) {
          failuresLeft -= 1
          throw new DOMException('Registration failed - push service error', 'AbortError')
        }
        if (opt.subscribeAlwaysThrows) {
          throw new DOMException(opt.subscribeAlwaysThrows.message, opt.subscribeAlwaysThrows.name)
        }
        // ⚠️ เบราว์เซอร์จริงคืน subscription **ตัวเดิม** ถ้ายังไม่ถูก unsubscribe สำเร็จ
        //    ⇒ `stubborn` จะได้ endpoint เดิมกลับไปชนด่านใน `obtainSubscription()` (นั่นคือ K5)
        if (!current) current = bindSub(makeSubscription(freshEndpoint))
        return current
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

  return { reg, waitingWorker, notificationStub, getCurrent: () => current }
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
  // ⚠️ **ต้องล้าง `localStorage` เอง** — `resetPushStatus()` จงใจ **ไม่** ล้างคีย์ที่ผูกไว้
  //    (มันเป็นข้อเท็จจริงของ *อุปกรณ์* ไม่ใช่ของบัญชี — ดูคอมเมนต์ใน `push.ts`)
  //    ⇒ ถ้าไม่ล้างตรงนี้ เทสกลุ่ม K จะรั่วคีย์ข้ามกันแล้วผ่าน/ล้มด้วยเหตุผลผิด
  localStorage.clear()
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
  // ⚠️ `restoreAllMocks()` **ไม่คืนเวลาเทียม** — เทสกลุ่ม R ใช้ `useFakeTimers()`
  //    ถ้าลืมคืนตรงนี้ เทสถัดไปจะค้างเพราะ `setTimeout` ไม่เดินเลย (หาเหตุยากมาก)
  vi.useRealTimers()
  delete (navigator as unknown as Record<string, unknown>).serviceWorker
})

/**
 * รันงานที่มี "ลองซ้ำโดยเว้นจังหวะ" ให้จบ — ด้วย **เวลาเทียม**
 *
 * ⚠️ ของจริงรอรวม ~5.2 วิต่อเคส ⇒ ปล่อยให้รอจริง = suite ช้าลงโดยไม่ได้อะไรเพิ่ม
 * ⚠️ `task.catch(() => {})` ต้องมาก่อน `runAllTimersAsync()` — ถ้าปล่อยให้ promise
 *    reject ระหว่างที่ยังไม่มีใคร `await` Node จะรายงาน unhandled rejection
 */
async function withFakeTimers<T>(run: () => Promise<T>): Promise<T> {
  vi.useFakeTimers()
  try {
    const task = run()
    task.catch(() => {})
    await vi.runAllTimersAsync()
    return await task
  } finally {
    vi.useRealTimers()
  }
}

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

    // ⚠️ เป็น endpoint ของ subscription **ที่สร้างใหม่** (`freshEndpoint`) ไม่ใช่ค่าคงที่ —
    //    เทสนี้เริ่มจากเครื่องที่ยังไม่มี subscription ⇒ `obtainSubscription()` subscribe ให้
    expect(subscribeMock).toHaveBeenCalledWith({
      endpoint: 'https://fcm.googleapis.com/fcm/send/fresh',
      keys: { p256dh: 'AAAA', auth: 'BBBB' },
    })
    expect(pushSubscribed.value).toBe(true)
    expect(pushDeviceCount.value).toBe(2)
  })

  /**
   * ⚠️ #44 เปลี่ยนความหมายของเทสนี้ — ของเดิม (ก่อน #44) ผ่านเพราะ `enablePush()` ใช้
   *    `existing ?? subscribe()` คือ **เชื่อ subscription เดิมเสมอโดยไม่ดูคีย์**
   *    ซึ่งคือตัวบั๊กเอง ⇒ ตอนนี้ "ใช้ของเดิม" เกิดได้เฉพาะเมื่อ **คีย์ตรงกัน** เท่านั้น
   *    ⇒ ต้องตั้งคีย์ที่ผูกไว้ก่อน ไม่งั้นเทสจะผ่านเพราะเส้นทาง "คีย์เก่า ⇒ เปิดใหม่" แทน
   */
  it('เครื่องที่เคยเปิดไว้แล้ว และ **คีย์ยังตรง** → ใช้ subscription เดิม ไม่ subscribe ซ้ำ', async () => {
    localStorage.setItem(BOUND_KEY_STORAGE, FAKE_PUBLIC_KEY)
    const { reg } = await readyEnv({ subscription: makeSubscription() })

    await enablePush()

    expect(reg.pushManager.getSubscription).toHaveBeenCalled()
    expect(reg.pushManager.subscribe).not.toHaveBeenCalled()
    expect(unsubscribeMock).not.toHaveBeenCalled()
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

  it('เบราว์เซอร์ไม่ยอมเลิก (โยน) → ยังถือว่าปิดสำเร็จ (เซิร์ฟเวอร์เลิกส่งแล้ว)', async () => {
    await readyEnv({ subscription: makeSubscription(), unsubscribeError: true })

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

/**
 * #44 — กับดักที่ 4: หลัง rotate คีย์ VAPID แล้ว **การ์ดขึ้น "เปิดอยู่" ตลอดไปโดยไม่มีอะไรมาถึง**
 *
 * ลำดับเหตุ: เบราว์เซอร์ยังคืน subscription เก่า (ผูกคีย์เก่า) → `enablePush()` เดิมเชื่อมัน
 * → POST endpoint เก่าขึ้นเซิร์ฟเวอร์ → FCM ปฏิเสธทุก push ที่เซ็นด้วยคีย์ใหม่ (403)
 * → `_classify` = `permanent` → ทิ้งเงียบ **โดยไม่ลบแถว** (มีแต่ 404/410 ที่ลบ)
 * ⇒ ไม่มี error ไม่มี log ไม่มีอะไรให้เห็นเลยนอกจาก "ไม่มีอะไรเด้ง"
 *
 * กลไกที่ปิดรูนี้: `piri_push_key` ใน `localStorage` = คีย์ที่ subscription ของ **เครื่องนี้**
 * ผูกไว้ ⇒ `obtainSubscription()` เทียบกับคีย์ปัจจุบันก่อนใช้ของเดิมเสมอ
 */
describe('#44 — เครื่องที่ผูกคีย์เก่า (หลัง rotate VAPID)', () => {
  it('★ K1: เครื่องใหม่ (ยังไม่มี subscription) → subscribe แล้ว **บันทึกคีย์ที่ผูกไว้**', async () => {
    const { reg } = await readyEnv()
    expect(boundKey()).toBeNull() // ยังไม่เคยผูก

    await expect(enablePush()).resolves.toBe('enabled')

    expect(reg.pushManager.subscribe).toHaveBeenCalled()
    expect(boundKey()).toBe(FAKE_PUBLIC_KEY)
  })

  it('★ K3: คีย์ไม่ตรง → ทิ้งของเดิม (แจ้งเซิร์ฟเวอร์ก่อน) แล้ว subscribe ใหม่', async () => {
    localStorage.setItem(BOUND_KEY_STORAGE, 'คีย์เก่าที่ถูก rotate ไปแล้ว')
    const { reg } = await readyEnv({
      subscription: makeSubscription('https://fcm.googleapis.com/fcm/send/old'),
    })
    calls = []

    await expect(enablePush()).resolves.toBe('enabled')

    expect(reg.pushManager.subscribe).toHaveBeenCalled()
    // ⚠️ ลำดับ 4 ขั้น: แจ้งเซิร์ฟเวอร์ลบแถวเก่า → เลิกที่เบราว์เซอร์ → subscribe ใหม่ → แจ้งแถวใหม่
    //    ถ้าสลับ "เลิกที่เบราว์เซอร์" มาก่อน API จะเหลือปลายทางตายที่ไม่มีใครลบ (แบบเดียวกับ P6)
    expect(calls.indexOf('api.unsubscribe')).toBeLessThan(calls.indexOf('browser.unsubscribe'))
    expect(calls.indexOf('browser.unsubscribe')).toBeLessThan(calls.indexOf('pushManager.subscribe'))
    expect(calls.indexOf('pushManager.subscribe')).toBeLessThan(calls.indexOf('api.subscribe'))
    // คนละ endpoint จริง — แถวเก่าถูกลบ แถวใหม่ถูกสร้าง
    expect(unsubscribeMock).toHaveBeenCalledWith({
      endpoint: 'https://fcm.googleapis.com/fcm/send/old',
    })
    expect(subscribeMock).toHaveBeenCalledWith({
      endpoint: 'https://fcm.googleapis.com/fcm/send/fresh',
      keys: { p256dh: 'AAAA', auth: 'BBBB' },
    })
    expect(boundKey()).toBe(FAKE_PUBLIC_KEY)
  })

  /**
   * ⚠️ K4 คือเครื่องที่ **เปิด push ไว้ก่อนมีฟีเจอร์นี้** — กลุ่มที่การ rotate ทำพังพอดี
   *    ⇒ `null` ต้องนับเป็น "ไม่รู้ว่าผูกกับอะไร" = เปิดใหม่หนึ่งครั้ง ไม่ใช่ "น่าจะโอเค"
   */
  it('★ K4: มี subscription แต่ **ไม่เคยบันทึกคีย์** → ถือว่าอาจเก่า ⇒ เปิดใหม่หนึ่งครั้ง', async () => {
    const { reg } = await readyEnv({
      subscription: makeSubscription('https://fcm.googleapis.com/fcm/send/legacy'),
    })

    await enablePush()

    expect(reg.pushManager.subscribe).toHaveBeenCalled()
    expect(boundKey()).toBe(FAKE_PUBLIC_KEY)
  })

  /**
   * ⚠️ K5 ป้องกันความล้มเหลวที่แย่กว่าเดิม: ถ้าเขียนคีย์ทับทั้งที่ **ยังใช้ของเก่าอยู่**
   *    คำเตือนจะไม่กลับมาอีกเลย ⇒ ผู้ใช้จะไม่เหลือทางแก้อีกตลอดไป
   */
  it('★ K5: เบราว์เซอร์ไม่ยอมทิ้งของเดิม → โยน error และ **ห้าม** เขียนคีย์ทับ', async () => {
    localStorage.setItem(BOUND_KEY_STORAGE, 'คีย์เก่า')
    await readyEnv({ subscription: makeSubscription(), stubborn: true })

    await expect(enablePush()).rejects.toThrow(/ไม่ยอมทิ้ง/)

    expect(boundKey()).toBe('คีย์เก่า')
    expect(subscribeMock).not.toHaveBeenCalled()
  })

  it('★ K6: คีย์ที่บันทึกไว้ไม่ตรงกับที่เซิร์ฟเวอร์ใช้ → `pushSubscriptionStale` = true', async () => {
    localStorage.setItem(BOUND_KEY_STORAGE, 'คีย์เก่า')

    await readyEnv({ subscription: makeSubscription() })

    expect(pushSubscribed.value).toBe(true) // ← ยังขึ้นว่า "เปิดอยู่" (นั่นคือสิ่งที่ทำให้หลอกตา)
    expect(pushSubscriptionStale.value).toBe(true)
  })

  it('K7: คีย์ตรงกัน → ไม่เตือน', async () => {
    localStorage.setItem(BOUND_KEY_STORAGE, FAKE_PUBLIC_KEY)

    await readyEnv({ subscription: makeSubscription() })

    expect(pushSubscriptionStale.value).toBe(false)
  })

  it('K7b: ไม่มี subscription → ไม่เตือน (ไม่มีอะไรให้ค้าง)', async () => {
    localStorage.setItem(BOUND_KEY_STORAGE, 'คีย์อะไรก็ช่าง')

    await readyEnv({ subscription: null })

    expect(pushSubscriptionStale.value).toBe(false)
  })

  /**
   * ⚠️ K8 — ด่านกัน **การเตือนจากความไม่รู้**: ถ้าโหลดสถานะไม่สำเร็จ (ออฟไลน์) เราไม่รู้ว่า
   *    เซิร์ฟเวอร์ใช้คีย์อะไรอยู่ ⇒ คีย์ที่บันทึกไว้จะ "ดูไม่ตรง" เสมอถ้าเทียบกับค่าว่าง
   *    ⇒ เตือนผิดทุกครั้งที่เน็ตสะดุด = ผู้ใช้เรียนรู้ที่จะมองข้ามคำเตือนนี้ไปตลอด
   */
  it('★ K8: โหลดสถานะไม่สำเร็จ (ไม่รู้คีย์ปัจจุบัน) → **ห้ามเตือน** แม้คีย์จะดูไม่ตรง', async () => {
    localStorage.setItem(BOUND_KEY_STORAGE, 'คีย์เก่า')
    getStatusMock.mockRejectedValue(new Error('offline'))
    installEnv({ subscription: makeSubscription() })
    resetPushStatus()

    await refreshPushStatus()

    expect(pushSubscribed.value).toBe(true) // ยังรู้จากฝั่งเบราว์เซอร์
    expect(pushSubscriptionStale.value).toBe(false)
  })

  it('★ K9: `resetPushStatus()` (login/logout) ล้างคำเตือน แต่ **ไม่ล้างคีย์** — มันเป็นของเครื่อง', async () => {
    localStorage.setItem(BOUND_KEY_STORAGE, 'คีย์เก่า')
    await readyEnv({ subscription: makeSubscription() })
    expect(pushSubscriptionStale.value).toBe(true)

    resetPushStatus()

    expect(pushSubscriptionStale.value).toBe(false)
    // ⚠️ หัวใจ: เครื่องนี้ยังผูกกับคีย์เดิม ⇒ คนถัดไปที่ล็อกอินไม่ต้องเปิดใหม่โดยไม่จำเป็น
    expect(boundKey()).toBe('คีย์เก่า')
  })

  it('★ K10: ซ่อมแล้ว → refresh รอบถัดไปต้องไม่เตือนอีก (ไม่ใช่เตือนค้าง)', async () => {
    localStorage.setItem(BOUND_KEY_STORAGE, 'คีย์เก่า')
    await readyEnv({ subscription: makeSubscription('https://fcm.googleapis.com/fcm/send/old') })
    expect(pushSubscriptionStale.value).toBe(true)

    await expect(repairPush()).resolves.toBe('enabled')
    await refreshPushStatus()

    expect(pushSubscriptionStale.value).toBe(false)
    expect(pushSubscribed.value).toBe(true)
  })

  it('★ K11: `repairPush()` — ยิงแถวเก่าให้ลบ แล้วสร้างแถวใหม่ที่ endpoint ใหม่จริง', async () => {
    localStorage.setItem(BOUND_KEY_STORAGE, 'คีย์เก่า')
    const { getCurrent } = await readyEnv({
      subscription: makeSubscription('https://fcm.googleapis.com/fcm/send/old'),
    })

    await expect(repairPush()).resolves.toBe('enabled')

    expect(unsubscribeMock).toHaveBeenCalledWith({
      endpoint: 'https://fcm.googleapis.com/fcm/send/old',
    })
    expect(subscribeMock).toHaveBeenCalledWith({
      endpoint: 'https://fcm.googleapis.com/fcm/send/fresh',
      keys: { p256dh: 'AAAA', auth: 'BBBB' },
    })
    // ⚠️ ต้องเป็น **คนละ endpoint** — ถ้าเท่ากันแปลว่าเปิดใหม่ไม่ได้จริง (Chrome คืนตัวเดิม)
    expect(getCurrent()?.endpoint).toBe('https://fcm.googleapis.com/fcm/send/fresh')
    expect(boundKey()).toBe(FAKE_PUBLIC_KEY)
  })

  it('K12: หลัง `disablePush()` → คำเตือนหมดเหตุ (ไม่มี subscription แล้ว)', async () => {
    localStorage.setItem(BOUND_KEY_STORAGE, 'คีย์เก่า')
    await readyEnv({ subscription: makeSubscription() })
    expect(pushSubscriptionStale.value).toBe(true)

    await disablePush()

    expect(pushSubscriptionStale.value).toBe(false)
  })
})

// ─────────────────────────────────────────────────────────────────────────────

/**
 * 🧪 `Registration failed - push service error` — บั๊กที่เกิดกับ **เครื่องที่เคยเปิด** เท่านั้น
 *
 * อาการจริงบนมือถือ (29 ก.ย. 2026): การ์ดขึ้นกรอบเหลือง → กด "เปิดใหม่บนเครื่องนี้" →
 * Swal `เปิดการแจ้งเตือนไม่สำเร็จ · Registration failed - push service error` กดกี่ครั้งก็ไม่ได้
 * · **ขณะที่คอมพิวเตอร์ที่ยังไม่เคยกดเปิด เปิดได้ปกติ** ← เบาะแสที่ชี้สาเหตุตรง ๆ
 *
 * สาเหตุ: การซ่อมต้อง `unsubscribe()` (ลบ token ที่ปลายทาง) แล้ว `subscribe()`
 * (ขอ token ใหม่) **ติดกันทันที** ⇒ ปลายทางปฏิเสธคำขอที่สอง · เครื่องใหม่ไม่มี token
 * ให้ลบ จึงไม่เคยเจอ — ตรงกับที่ผู้ใช้รายงานเป๊ะ
 *
 * ⚠️ เทสกลุ่มนี้พิสูจน์ **จำนวนครั้งที่ลอง** ไม่ใช่แค่ "สำเร็จในที่สุด" — ถ้าลบ retry ทิ้ง
 *    R1/R2/R4 จะล้มทันที (นั่นคือด่านที่มีค่าที่สุดของกลุ่มนี้)
 */
describe('#44b — ปลายทางยังไม่พร้อม (push service error) ตอนกดเปิดใหม่', () => {
  it('★ R1: เครื่องที่เคยเปิด — ล้ม 2 ครั้งแรก แล้ว **ครั้งที่ 3 สำเร็จ**', async () => {
    localStorage.setItem(BOUND_KEY_STORAGE, 'คีย์เก่า')
    const { reg } = await readyEnv({
      subscription: makeSubscription('https://fcm.googleapis.com/fcm/send/old'),
      subscribeFailures: 2,
    })

    await expect(withFakeTimers(() => repairPush())).resolves.toBe('enabled')

    // ⚠️ 3 = ล้ม 2 + สำเร็จ 1 · ถ้า retry หายไป จะได้ 1 แล้วเทสนี้ล้ม
    expect(reg.pushManager.subscribe).toHaveBeenCalledTimes(3)
    // สำเร็จแล้วต้องเดินจบเส้นทางเดิมให้ครบ ไม่ใช่แค่ subscribe ผ่าน
    expect(boundKey()).toBe(FAKE_PUBLIC_KEY)
    expect(subscribeMock).toHaveBeenCalledWith({
      endpoint: 'https://fcm.googleapis.com/fcm/send/fresh',
      keys: { p256dh: 'AAAA', auth: 'BBBB' },
    })
  })

  it('★ R2: ล้มทุกครั้ง → โยนตัวเดิมออกไป และลอง **ไม่เกินขอบเขต** (4 ครั้ง)', async () => {
    localStorage.setItem(BOUND_KEY_STORAGE, 'คีย์เก่า')
    const { reg } = await readyEnv({
      subscription: makeSubscription('https://fcm.googleapis.com/fcm/send/old'),
      subscribeFailures: 99,
    })

    await expect(withFakeTimers(() => repairPush())).rejects.toMatchObject({
      name: 'AbortError',
    })

    // ⚠️ ขอบเขตคือ 1 + 3 ดีเลย์ — กัน "ลองไม่รู้จบ" ที่ทำให้ปุ่มดูค้าง
    expect(reg.pushManager.subscribe).toHaveBeenCalledTimes(4)
    // ⚠️ ล้มเหลวแล้ว **ห้ามเขียนคีย์ทับ** — มันคือทางกลับทางเดียวของผู้ใช้ (เหตุผลเดียวกับ K5)
    expect(boundKey()).toBe('คีย์เก่า')
    expect(subscribeMock).not.toHaveBeenCalled()
  })

  it('★ R3: error ที่ลองใหม่ไม่ได้ (`NotAllowedError`) → ยิง **ครั้งเดียว** แล้วโยนทันที', async () => {
    localStorage.setItem(BOUND_KEY_STORAGE, 'คีย์เก่า')
    const { reg } = await readyEnv({
      subscription: makeSubscription('https://fcm.googleapis.com/fcm/send/old'),
      subscribeAlwaysThrows: { name: 'NotAllowedError', message: 'Permission denied' },
    })

    await expect(withFakeTimers(() => repairPush())).rejects.toMatchObject({
      name: 'NotAllowedError',
    })

    // ⚠️ หัวใจของ R3: การลองใหม่ไม่ช่วยอะไรกับ "ผู้ใช้ไม่อนุญาต" — ทำแล้วมีแต่ทำให้
    //    ผู้ใช้ **รอนานขึ้น** เพื่อรอข้อความเดิมที่ควรเห็นทันที
    expect(reg.pushManager.subscribe).toHaveBeenCalledTimes(1)
  })

  it('R4: เครื่องที่ยังไม่เคยเปิดก็ลองใหม่ได้ — ไม่ได้ผูก retry ไว้กับเส้นทางซ่อม', async () => {
    const { reg } = await readyEnv({ subscribeFailures: 1 })

    await expect(withFakeTimers(() => enablePush())).resolves.toBe('enabled')

    expect(reg.pushManager.subscribe).toHaveBeenCalledTimes(2)
    expect(boundKey()).toBe(FAKE_PUBLIC_KEY)
  })
})

/**
 * 🧪 ข้อความ error ที่ผู้ใช้เห็น
 *
 * ⚠️ ต้นเหตุของกลุ่มนี้คือ `AbortError: Registration failed - push service error` ล้วน ๆ
 *    ซึ่งบอกผู้ใช้ว่า "มีอะไรผิด" แต่ไม่บอกว่า **ต้องทำอะไร** ⇒ คนที่เจอจะกดซ้ำแล้วเจอ
 *    ข้อความเดิม จนสรุปว่าแอพพัง (เกิดจริงกับผู้ใช้ 29 ก.ย. 2026)
 */
describe('describePushError — แปล error เป็นคำที่ทำต่อได้', () => {
  it('★ R5: `AbortError` ของ push service → บอกให้ปิด/เปิดเบราว์เซอร์ใหม่หรือเปลี่ยนเน็ต', () => {
    const text = describePushError(
      new DOMException('Registration failed - push service error', 'AbortError'),
    )
    expect(text).toContain('ปิดแล้วเปิดเบราว์เซอร์ใหม่')
    expect(text).toContain('เน็ตอื่น')
    // ⚠️ ต้องไม่หลุดชื่อ exception ดิบออกไปให้ผู้ใช้เห็น
    expect(text).not.toContain('AbortError')
  })

  it('R6: `AbortError` ที่ **ไม่ใช่** เรื่อง push service → ไม่ถูกกล่าวหาว่าเป็นปัญหาปลายทาง', () => {
    const text = describePushError(new DOMException('The operation was aborted.', 'AbortError'))
    expect(text).not.toContain('ปิดแล้วเปิดเบราว์เซอร์ใหม่')
    expect(text).toContain('AbortError') // ตกไปสาขา default ที่บอกชื่อไว้ (ดีกว่าเงียบ)
  })

  it('R7: แต่ละชื่อ exception → คำแนะนำคนละเรื่องกัน (ไม่ใช่ข้อความเดียวใช้ซ้ำ)', () => {
    expect(describePushError(new DOMException('x', 'NotAllowedError'))).toContain(
      'ตั้งค่าเบราว์เซอร์',
    )
    // เคสนี้ต่างจาก AbortError ตรงที่ "กดเปิดใหม่" ไม่ช่วย — ต้องปิดของเดิมให้จบก่อน
    expect(describePushError(new DOMException('x', 'InvalidStateError'))).toContain(
      'ปิดบนเครื่องนี้',
    )
    expect(describePushError(new DOMException('x', 'SecurityError'))).toContain('https')
  })

  it('R8: ข้อความที่ **เราเขียนเอง** ต้องผ่านออกไปตามเดิม (เจาะจงกว่าแผนที่นี้อยู่แล้ว)', () => {
    expect(describePushError(new Error('ตัวช่วยแอพเวอร์ชันใหม่ยังไม่พร้อม — ลองใหม่อีกครั้ง'))).toBe(
      'ตัวช่วยแอพเวอร์ชันใหม่ยังไม่พร้อม — ลองใหม่อีกครั้ง',
    )
  })

  it('R9: สิ่งที่ไม่ใช่ Error เลย → ข้อความกลาง ๆ ไม่ใช่ `undefined`', () => {
    expect(describePushError(null)).toBe('เกิดข้อผิดพลาด กรุณาลองใหม่')
    expect(describePushError('พัง')).toBe('เกิดข้อผิดพลาด กรุณาลองใหม่')
  })
})
