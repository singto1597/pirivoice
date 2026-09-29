/**
 * 🔔 Web Push (A3) — ชั้นที่คุยกับ **เบราว์เซอร์** (PushManager + Notification)
 *
 * แบ่งความรับผิดชอบชัดเจน:
 *   - ไฟล์นี้ = ขอสิทธิ์, subscribe/unsubscribe กับอุปกรณ์นี้, จำสถานะเป็น ref
 *   - `services/notification.ts` = ยิง API ไปบอกเซิร์ฟเวอร์ (ไม่มี logic ของเบราว์เซอร์)
 *   - `components/PushSettingsCard.vue` = แสดงผลตามสถานะ + เรียกฟังก์ชันในไฟล์นี้
 *
 * ⚠️ `sw.js` (ตัวช่วยแอพ) คือคนที่ **แสดง notification จริง** เมื่อ push มาถึง —
 *    ไฟล์นี้แค่ทำให้เซิร์ฟเวอร์รู้ว่า "จะส่งไปที่อุปกรณ์นี้ได้" เท่านั้น
 */
import { computed, readonly, ref } from 'vue'
import { isIosSafari, isStandalone } from '@/pwa'
import { getPushStatus, subscribePush, unsubscribePush } from '@/services/notification'

// ── สถานะระดับโมดูล (singleton — แบบเดียวกับ `pwa.ts`) ─────────────────────────
const supportedState = ref(false)
const permissionState = ref<NotificationPermission>('default')
/** อุปกรณ์ **เครื่องนี้** ลงทะเบียนไว้หรือยัง — ใช้เป็นสวิตช์หลักของการ์ด */
const subscribedState = ref(false)
/** จำนวนอุปกรณ์ที่ผูกกับบัญชีนี้ (ทุกเครื่อง) — มาจากเซิร์ฟเวอร์ */
const deviceCountState = ref(0)
/** เซิร์ฟเวอร์ตั้งคีย์ VAPID แล้วหรือยัง (`false` = ซ่อนการ์ดทั้งใบ) */
const enabledState = ref(false)
/**
 * ⚠️ **คีย์ public ต้องถูกโหลดไว้ล่วงหน้า ห้าม `fetch` ใน `enablePush()`**
 *    เพราะ iOS ตัด "gesture chain" ทิ้งถ้ามี `await` อื่นคั่นก่อน
 *    `Notification.requestPermission()` (หายเงียบ ๆ ไม่มี error) — ดูคอมเมนต์ใน `enablePush()`
 */
const publicKeyState = ref('')
const busyState = ref(false)
const readyState = ref(false)
/**
 * subscription บนเครื่องนี้ผูกกับคีย์ VAPID **คนละตัว** กับที่เซิร์ฟเวอร์ใช้อยู่
 * ⇒ ปลายทางจะปฏิเสธทุก push ที่ส่งไป ⇒ ต้องเปิดใหม่ (ดู `obtainSubscription()`)
 */
const staleState = ref(false)

export const pushSupported = computed(() => supportedState.value)
/**
 * ใช้ได้จริงบนเครื่องนี้ไหม — iOS/iPadOS **บังคับให้ติดตั้งลงหน้าจอก่อน**
 * (Safari บนแท็บธรรมดาไม่มี `PushManager` ให้ใช้เลย) ส่วนเบราว์เซอร์อื่นเปิดใช้ได้ทันที
 */
export const pushAvailable = computed(
  () => supportedState.value && (!isIosSafari.value || isStandalone.value),
)
export const pushPermission = readonly(permissionState)
export const pushSubscribed = readonly(subscribedState)
export const pushDeviceCount = readonly(deviceCountState)
/** เซิร์ฟเวอร์พร้อมส่งหรือยัง — `false` = ยังไม่ตั้งคีย์ VAPID ⇒ UI ต้องซ่อนการ์ด */
export const pushEnabled = readonly(enabledState)
export const pushBusy = readonly(busyState)
/** โหลดสถานะรอบแรกเสร็จแล้ว — ใช้กันจอวูบ (แสดง skeleton จนกว่าจะ true) */
export const pushReady = readonly(readyState)
/**
 * ⚠️ `true` = **การแจ้งเตือนของเครื่องนี้พังอยู่** ทั้งที่ทุกอย่างดู "เปิดอยู่"
 *
 * เกิดเมื่อคีย์ VAPID ถูก rotate: subscription เก่ายังอยู่ที่เบราว์เซอร์และยังตอบ
 * `getSubscription()` ได้ แต่ปลายทาง (FCM/APNs) จะปฏิเสธ push ที่เซ็นด้วยคีย์ใหม่
 * ด้วย 403 ⇒ **ไม่มีอาการให้เห็นเลยจากฝั่งแอพ** ⇒ ต้องให้ผู้ใช้กดเปิดใหม่
 * (ปุ่มในการ์ด → `repairPush()`) · ค่านี้เป็น `false` เสมอเมื่อไม่มี subscription
 */
export const pushSubscriptionStale = readonly(staleState)

/** ผลของการกดเปิด — แยก "ถูกปฏิเสธ" ออกจาก "ยังไม่ตัดสินใจ" ให้ UI พูดถูก */
export type PushEnableResult = 'enabled' | 'denied' | 'dismissed'

/** รอตัวช่วยแอพเวอร์ชันใหม่สลับที่ — นานพอสำหรับเน็ตช้า แต่ไม่ค้างจนผู้ใช้รำคาญ */
const SWAP_TIMEOUT_MS = 5000

/**
 * คีย์ public ที่ subscription ของ **เครื่องนี้** ผูกไว้ — บันทึกตอน subscribe
 *
 * ⚠️ **ห้ามเปลี่ยนชื่อคีย์นี้** — เครื่องที่บันทึกไว้แล้วจะกลายเป็น "ไม่รู้ว่าผูกกับอะไร"
 *    ⇒ ของทุกเครื่องจะถูกขอให้เปิดใหม่หนึ่งครั้งโดยไม่จำเป็น
 * ⚠️ เป็นข้อเท็จจริงของ **อุปกรณ์** ไม่ใช่ของบัญชี (เหมือน badge ที่เกาะกับไอคอน)
 *    ⇒ `resetPushStatus()` ตอน login/logout **ห้ามล้าง**
 */
const BOUND_KEY_STORAGE = 'piri_push_key'

/**
 * อ่านคีย์ที่ผูกไว้ — `null` = **ยังไม่เคยบันทึก**
 *
 * ⚠️ `null` ไม่ได้แปลว่า "ผูกกับคีย์อะไรก็ได้" แต่แปลว่า **ตรวจไม่ได้** ⇒ ผู้เรียก
 *    (`obtainSubscription()`) ถือเป็น "ต้องเปิดใหม่" เพราะ subscription ที่บันทึกไว้
 *    ก่อนมีฟีเจอร์นี้ คือกลุ่มที่คีย์อาจถูก rotate ไปแล้วพอดี · เปิดใหม่หนึ่งครั้ง
 *    ถูกกว่าปล่อยให้ push เงียบตลอดไปโดยไม่มีใครรู้
 */
function readBoundKey(): string | null {
  try {
    return localStorage.getItem(BOUND_KEY_STORAGE)
  } catch {
    // localStorage ถูกบล็อก ⇒ ตรวจไม่ได้เช่นกัน (เส้นทางเดียวกันกับ `null`)
    return null
  }
}

/** บันทึกคีย์ที่ subscription ใหม่ผูกไว้ — เขียนไม่ได้ก็ไม่เป็นไร (ครั้งหน้าจะเสนอเปิดใหม่) */
function writeBoundKey(key: string): void {
  try {
    localStorage.setItem(BOUND_KEY_STORAGE, key)
  } catch {
    // ดูคอมเมนต์ข้างบน — ไม่ใช่เหตุให้การเปิดแจ้งเตือนล้มเหลว
  }
}

function detectSupport(): boolean {
  if (typeof window === 'undefined' || typeof navigator === 'undefined') return false
  return (
    'serviceWorker' in navigator && 'PushManager' in window && typeof Notification !== 'undefined'
  )
}

/**
 * base64url → `Uint8Array` — **จำเป็น ไม่ใช่ของแถม**
 *
 * ⚠️ `applicationServerKey` รับได้เฉพาะ `BufferSource` — ส่ง base64 string ตรง ๆ
 *    แล้ว **Chrome โยน `InvalidCharacterError` แต่ Safari เงียบ** ⇒ ถ้าไม่แปลง
 *    จะได้บั๊กที่เกิดเฉพาะบางเครื่องและไม่มีข้อความอะไรบอกเลย
 *
 * ⚠️ **สิ่งที่จำเป็นจริง ๆ คือการแทน `-`/`_` กลับเป็น `+`/`/`** — `atob` ไม่รู้จัก
 *    อักขระสองตัวนี้ (เบราว์เซอร์ส่งคีย์มาแบบ base64url เสมอ)
 *
 * 📌 **ไม่ต้องเติม `=`** — ตรวจกับสเปกแล้ว (WHATWG forgiving-base64 ที่ `atob`
 *    ใช้จริง): padding เป็นทางเลือก มีผลแค่ความยาว `% 4 === 1` ซึ่ง **ไม่เกิดขึ้นกับ
 *    base64 ที่ถูกต้อง** ⇒ เติมไปก็เป็นบรรทัดที่พิสูจน์ด้วยเทสไม่ได้ (mutation รอด)
 *    ⇒ ตัดทิ้ง ดีกว่าทิ้งโค้ดที่ไม่มีใครตรวจ (ดู `push.spec.ts` เคสที่ล็อกพฤติกรรมนี้ไว้)
 */
export function urlBase64ToUint8Array(base64: string): Uint8Array<ArrayBuffer> {
  const raw = atob(base64.replace(/-/g, '+').replace(/_/g, '/'))
  // ⚠️ ต้องสร้างจาก `ArrayBuffer` ตรง ๆ ไม่ใช่ `new Uint8Array(len)` — TS 6 ให้ชนิด
  //    `Uint8Array<ArrayBufferLike>` กับแบบหลัง ซึ่ง **ไม่ตรงกับ `BufferSource`**
  //    ที่ `applicationServerKey` ต้องการ (มันรับ `ArrayBufferView<ArrayBuffer>` เท่านั้น)
  //    ⇒ ถ้าใช้แบบสั้น จะ **คอมไพล์ไม่ผ่าน** ทั้งที่รันได้จริง — จับได้ด้วย `vue-tsc`
  const out = new Uint8Array(new ArrayBuffer(raw.length))
  for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i)
  return out
}

/**
 * ⭐ กับดักอันตรายที่สุดของ A3: **ตัวช่วยแอพเวอร์ชันใหม่ค้างในสถานะ `waiting`**
 *
 * `sw.js` **จงใจไม่เรียก `skipWaiting()` เอง** (กันแท็บที่กำลังกรอกเรื่องอยู่โดน reload
 * กลางทาง — ดูคอมเมนต์หัวไฟล์ `sw.js`) ⇒ ถ้าผู้ใช้เปิดแท็บ PIRIvoice ค้างไว้ตอน deploy
 * ตัวช่วยแอพ**รุ่นเก่าที่ยังไม่มี handler `push`** จะยังเป็นตัวที่ควบคุมหน้าอยู่
 * ⇒ push ที่มาถึงจะเข้า handler ว่างเปล่า ⇒ **"เปิดการแจ้งเตือนแล้วแต่ไม่มีอะไรขึ้น"**
 *    ซึ่งหาสาเหตุยากมาก เพราะทุกอย่างดูเหมือนสำเร็จหมด
 *
 * ⇒ ต้องสลับให้เสร็จ**ก่อน** subscribe
 */
async function ensureFreshWorker(): Promise<ServiceWorkerRegistration> {
  const reg = await navigator.serviceWorker.ready
  const waiting = reg.waiting
  if (!waiting) return reg

  const swapped = new Promise<boolean>((resolve) => {
    navigator.serviceWorker.addEventListener('controllerchange', () => resolve(true), {
      once: true,
    })
    setTimeout(() => resolve(false), SWAP_TIMEOUT_MS)
  })

  waiting.postMessage({ type: 'SKIP_WAITING' })

  // ⚠️ หมดเวลาแล้ว **ต้องโยน ไม่ใช่ไปต่อ** — การ subscribe สำเร็จทั้งที่ตัวช่วยแอพ
  //    ยังเป็นรุ่นเก่า คือความล้มเหลวแบบเงียบที่แย่ที่สุด: ผู้ใช้เห็น "เปิดอยู่ 1 อุปกรณ์"
  //    แล้วไม่ได้รับอะไรเลยตลอดไป · โยน error ให้ผู้ใช้กดลองใหม่ตรงไปตรงมากว่า
  if (!(await swapped)) {
    throw new Error('ตัวช่วยแอพเวอร์ชันใหม่ยังไม่พร้อม — ลองใหม่อีกครั้ง')
  }
  return reg
}

/** อ่านสถานะ subscription ของ **เครื่องนี้** โดยไม่แตะเน็ต */
async function readLocalSubscription(): Promise<PushSubscription | null> {
  // ⚠️ ใช้ `getRegistration()` **ไม่ใช่** `ready` — ในโหมด dev ไม่มีการลงทะเบียน SW
  //    (`registerPwa()` ข้ามไปถ้าไม่ใช่ PROD) ⇒ `ready` จะ **ไม่ resolve เลย**
  //    แล้วการ์ดจะค้างอยู่ในสถานะโหลดตลอดกาลโดยไม่มี error ให้เห็น
  const reg = await navigator.serviceWorker.getRegistration()
  if (!reg || !reg.pushManager) return null
  return (await reg.pushManager.getSubscription()) ?? null
}

/**
 * ทิ้ง subscription ที่ผูกกับคีย์เก่า — **แจ้งเซิร์ฟเวอร์ก่อน แล้วค่อยลืมที่เบราว์เซอร์**
 * (ลำดับเดียวกับ `disablePush()` และด้วยเหตุผลเดียวกัน — ดูคอมเมนต์ที่นั่น)
 *
 * ⚠️ ความล้มเหลวของ `unsubscribePush()` **ถูกกลืนโดยเจตนา** — แถวที่ค้างจะถูกจัดเป็น
 *    `permanent` (403 จากคีย์ที่ไม่ตรง) แล้วทิ้งไปในคิว ⇒ ไม่ใช่ปลายทางที่ดูเหมือนยังมีชีวิต
 *    · ถ้าบล็อกการซ่อมไว้รอ API ผู้ใช้จะซ่อมไม่ได้เลยตอนเน็ตมีปัญหา = แย่กว่าปล่อยแถวขยะไว้
 */
async function discardSubscription(sub: PushSubscription): Promise<void> {
  try {
    const res = await unsubscribePush({ endpoint: sub.endpoint })
    deviceCountState.value = res.device_count
  } catch {
    // ดูคอมเมนต์ข้างบน
  }
  try {
    await sub.unsubscribe()
  } catch {
    // `false` ของสเปกกำกวม ("เลิกแล้ว" กับ "ไม่พบ") ⇒ ด่านจริงคือเทียบ endpoint ข้างล่าง
  }
}

/**
 * ⭐ หัวใจของงานนี้ — ขอ subscription ที่ **ผูกกับคีย์ปัจจุบันจริง**
 *
 * ปัญหา: หลัง rotate คีย์ VAPID เบราว์เซอร์ยังคืน subscription เก่าจาก `getSubscription()`
 * (ซึ่งผูกกับ **คีย์เก่า**) ⇒ ถ้าใช้ตัวเดิม ปลายทางจะปฏิเสธทุก push ด้วย 403 และ
 * **ไม่มีอาการให้เห็นเลยจากฝั่งแอพ** — ผู้ใช้เห็น "เปิดอยู่บนเครื่องนี้" ตลอดไปโดยไม่ได้อะไร
 * ⇒ ต้องเทียบ "คีย์ที่ subscription นี้ผูกไว้" กับ "คีย์ที่เซิร์ฟเวอร์ใช้อยู่"
 *
 * ⚠️ `readBoundKey() === null` (ยังไม่เคยบันทึก) นับเป็น **ต้องเปิดใหม่** — subscription ที่
 *    บันทึกไว้ก่อนมีฟีเจอร์นี้คือกลุ่มที่คีย์อาจถูก rotate ไปแล้วพอดี · เสียค่า re-subscribe
 *    หนึ่งครั้ง ถูกกว่าปล่อยให้ push เงียบตลอดไปโดยไม่มีใครรู้
 * ⚠️ **ด่าน endpoint ซ้ำ** — Chrome คืน subscription ตัวเดิมเมื่อ `unsubscribe()` ไม่มีผล
 *    ⇒ ถ้าเขียนคีย์ลงไปเลย จะประกาศว่า "ซ่อมแล้ว" ทั้งที่ยังผูกคีย์เก่าอยู่ และคำเตือน
 *    จะไม่กลับมาอีกเลย · โยน error ให้ผู้ใช้ปิด-เปิดใหม่ตรง ๆ ดีกว่าเงียบ
 */
async function obtainSubscription(reg: ServiceWorkerRegistration): Promise<PushSubscription> {
  const key = publicKeyState.value
  const existing = reg.pushManager ? await reg.pushManager.getSubscription() : null

  // คีย์ที่บันทึกไว้ตรงกับคีย์ปัจจุบัน = ยังใช้ได้ ⇒ ไม่แตะ (กัน churn ทุกครั้งที่กดเปิด)
  if (existing && readBoundKey() === key) return existing

  if (existing) await discardSubscription(existing)

  const fresh = await reg.pushManager.subscribe({
    // ⚠️ Chrome บังคับ `true` — push ที่ไม่แสดงอะไรให้ผู้ใช้จะถูกบล็อก
    userVisibleOnly: true,
    applicationServerKey: urlBase64ToUint8Array(key),
  })

  if (existing && fresh.endpoint === existing.endpoint) {
    throw new Error('เบราว์เซอร์ไม่ยอมทิ้งการแจ้งเตือนเดิม — ลองปิดแล้วเปิดใหม่อีกครั้ง')
  }

  // ⚠️ บันทึก **ก่อน** POST — การผูกเป็นข้อเท็จจริงฝั่งเบราว์เซอร์ · ถ้า POST ล้มแล้วต้อง
  //    เปิดใหม่ซ้ำทั้งที่ subscription ถูกต้องอยู่แล้ว = ลงโทษผู้ใช้ฟรี ๆ ตอนเน็ตสะดุด
  writeBoundKey(key)
  return fresh
}

/**
 * โหลดสถานะทั้งหมด — **ต้องเรียกตอน `onMounted` ของการ์ด**
 *
 * ⚠️ เรียกที่นี่ที่เดียวคือเหตุผลที่ `enablePush()` ไม่ต้องยิงเน็ตก่อนขอสิทธิ์ (ดูคอมเมนต์ข้างล่าง)
 * ⚠️ เน็ตพังก็ยังต้องได้สถานะฝั่งเบราว์เซอร์ ⇒ สองบล็อกแยกกัน ไม่ให้ล้มทั้งคู่
 */
export async function refreshPushStatus(): Promise<void> {
  supportedState.value = detectSupport()
  permissionState.value =
    typeof Notification !== 'undefined' ? Notification.permission : 'default'

  if (!supportedState.value) {
    readyState.value = true
    return
  }

  // ⚠️ เริ่มรอบใหม่ = ยังไม่มีหลักฐานว่าค้าง ⇒ ล้างก่อน แล้วค่อยตั้งใหม่หลังข้อ ③
  //    (ถ้าไม่ล้าง การ์ดจะค้างเตือนทั้งที่ผู้ใช้เพิ่งซ่อมไปแล้ว)
  staleState.value = false

  // ① ฝั่งเบราว์เซอร์ — ไม่ใช้เน็ต
  let hasSubscription = false
  try {
    hasSubscription = (await readLocalSubscription()) !== null
    subscribedState.value = hasSubscription
  } catch {
    subscribedState.value = false
  }

  // ② ฝั่งเซิร์ฟเวอร์ — ล้มเหลวได้ (ออฟไลน์) โดยไม่ทำให้การ์ดพังทั้งใบ
  //    (ค่า public key คือของที่ต้องได้จากที่นี่ — ถ้าพลาด ปุ่มเปิดจะบอกให้ลองใหม่)
  try {
    const status = await getPushStatus()
    enabledState.value = status.enabled
    publicKeyState.value = status.public_key
    deviceCountState.value = status.device_count
  } catch {
    // คงค่าเดิมไว้ — การ์ดจะโชว์ปุ่มตามสถานะที่รู้อยู่แล้ว
  }

  // ③ คีย์ไม่ตรง = push ของเครื่องนี้ตายเงียบ — ต้องอยู่ **หลัง** ② เพราะต้องรู้คีย์ปัจจุบันก่อน
  //    ⚠️ `publicKeyState.value !== ''` — ถ้าโหลดสถานะไม่สำเร็จ (ออฟไลน์/ยังไม่เคยโหลด)
  //       เรา **ไม่รู้** คีย์ที่เซิร์ฟเวอร์ใช้อยู่ ⇒ ห้ามเตือนจากความไม่รู้
  staleState.value =
    hasSubscription &&
    publicKeyState.value !== '' &&
    readBoundKey() !== publicKeyState.value

  readyState.value = true
}

/**
 * ผู้ใช้กด "เปิดการแจ้งเตือนบนเครื่องนี้"
 *
 * ⚠️⚠️ **`Notification.requestPermission()` ต้องเป็น `await` ตัวแรกของฟังก์ชัน**
 *    iOS ตัด "gesture chain" ทิ้งถ้ามี `await` อื่นคั่นก่อน (เช่นยิง fetch เอาคีย์)
 *    ⇒ คำขอจะถูกปฏิเสธ **เงียบ ๆ** โดยไม่มี error · นี่คือเหตุที่คีย์ถูกโหลดไว้
 *    ล่วงหน้าใน `refreshPushStatus()` แล้ว ⇒ ห้ามเพิ่มอะไรก่อนบรรทัดนั้นเด็ดขาด
 */
export async function enablePush(): Promise<PushEnableResult> {
  if (busyState.value) return 'dismissed'
  if (!publicKeyState.value) {
    throw new Error('ยังโหลดข้อมูลการแจ้งเตือนไม่เสร็จ — ลองใหม่อีกครั้ง')
  }

  busyState.value = true
  try {
    const permission = await Notification.requestPermission()
    permissionState.value = permission
    if (permission !== 'granted') {
      // `default` = ผู้ใช้ปิด dialog ไปเฉย ๆ (ยังไม่ปฏิเสธ) — ไม่ใช่ error
      return permission === 'denied' ? 'denied' : 'dismissed'
    }

    const reg = await ensureFreshWorker()

    // ⚠️ ไม่ใช่ `existing ?? subscribe()` แบบเดิม — ต้อง **ตรวจว่าคีย์ตรงกัน** ก่อนใช้ของเดิม
    //    ไม่งั้น subscription ที่ผูกกับคีย์เก่าจะถูกใช้ซ้ำตลอดไปโดยไม่มีใครรู้ (ดู `obtainSubscription`)
    const sub = await obtainSubscription(reg)

    const json = sub.toJSON()
    const p256dh = json.keys?.p256dh
    const auth = json.keys?.auth
    if (!p256dh || !auth) throw new Error('เบราว์เซอร์ไม่ส่งคีย์ของอุปกรณ์มาให้')

    const res = await subscribePush({ endpoint: sub.endpoint, keys: { p256dh, auth } })
    subscribedState.value = true
    deviceCountState.value = res.device_count
    // เปิดใหม่สำเร็จ = คีย์ตรงกันแน่นอน ⇒ คำเตือน "ต้องเปิดใหม่" หมดเหตุ
    staleState.value = false
    return 'enabled'
  } finally {
    busyState.value = false
  }
}

/**
 * ผู้ใช้กด "ปิดบนเครื่องนี้"
 *
 * ⚠️ ลำดับคือ **แจ้งเซิร์ฟเวอร์ก่อน แล้วค่อย `unsubscribe()`** — ถ้าสลับกันแล้วเน็ตหลุด
 *    เบราว์เซอร์จะลืม subscription ไปแล้วทั้งที่ DB ยังมีแถวค้าง ⇒ ปลายทางตายที่ไม่มีใครลบ
 *    (ต้องรอ push รอบถัดไปได้ 410 ซึ่งอาจไม่เกิดขึ้นอีกเลย)
 *    ส่วนกรณีกลับกัน (API สำเร็จแต่ `unsubscribe()` ล้ม) ไม่มีอันตราย — เบราว์เซอร์ยังมี
 *    subscription อยู่แต่เซิร์ฟเวอร์ไม่ส่งไปแล้ว และการเปิดใหม่จะผูกกลับให้เอง
 */
export async function disablePush(): Promise<void> {
  if (busyState.value) return
  busyState.value = true
  try {
    const sub = await readLocalSubscription()
    if (sub) {
      const res = await unsubscribePush({ endpoint: sub.endpoint })
      deviceCountState.value = res.device_count
      try {
        await sub.unsubscribe()
      } catch {
        // เบราว์เซอร์ไม่ยอมเลิก — เซิร์ฟเวอร์เลิกส่งให้แล้วจึงไม่เป็นปัญหา
      }
    }
    subscribedState.value = false
    // ไม่มี subscription = ไม่มีอะไรให้ "ค้าง" ⇒ ต้องล้าง ไม่งั้นการ์ดจะยังเตือนให้ซ่อม
    // ทั้งที่ผู้ใช้เพิ่งปิดการแจ้งเตือนบนเครื่องนี้ไป
    staleState.value = false
  } finally {
    busyState.value = false
  }
}

/**
 * ซ่อมการแจ้งเตือนของเครื่องนี้ — ปิดให้จบแล้วเปิดใหม่
 *
 * ⚠️ **ต้องถูกเรียกจาก user gesture เท่านั้น** — iOS ต้องการ gesture สำหรับ `subscribe()`
 *    และการเขียน endpoint ใหม่โดยที่ผู้ใช้ไม่ได้สั่งคือสิ่งที่ผิด
 *    ⇒ **ห้ามเรียกอัตโนมัติตอนโหลดหน้า** (ต่างจาก `refreshPushStatus()` ที่เรียกได้เสรี)
 * ⚠️ ประกอบจาก `disablePush()` + `enablePush()` (สองเส้นทางที่เทสต์แล้ว) แทนการเขียนใหม่
 *    ⇒ ได้ทั้ง subscription ใหม่ที่เบราว์เซอร์ **และ** แถวใหม่ที่เซิร์ฟเวอร์ · ด่าน endpoint ซ้ำ
 *    ใน `obtainSubscription()` ยังทำงานกับเส้นทางนี้ด้วย
 */
export async function repairPush(): Promise<PushEnableResult> {
  await disablePush()
  return enablePush()
}

/** ให้การ์ดเรียกหลัง login/logout เพื่อล้างสถานะของคนก่อนหน้าออกจากหน้าจอ */
export function resetPushStatus(): void {
  subscribedState.value = false
  deviceCountState.value = 0
  publicKeyState.value = ''
  enabledState.value = false
  readyState.value = false
  // ⚠️ ล้างคำเตือน แต่ **ห้ามล้างคีย์ที่บันทึกไว้** — มันเป็นข้อเท็จจริงของ *อุปกรณ์* นี้
  //    ไม่ใช่ของบัญชี (เหมือน badge ที่เกาะกับไอคอน) ⇒ คนถัดไปที่ล็อกอินบนเครื่องเดิม
  //    ยังใช้ subscription เดียวกันได้ และไม่ถูกขอให้เปิดใหม่โดยไม่จำเป็น
  staleState.value = false
  // ⚠️ ต้องล้างด้วย — ถ้างานเปิด/ปิดค้างอยู่ตอนที่ผู้ใช้ออกจากระบบ สวิตช์จะค้าง disabled
  //    ตลอดไป (finally ของงานที่ถูกทิ้งกลางทางไม่ได้รัน) ⇒ กดใหม่ไม่ได้เลยโดยไม่มีอะไรบอก
  busyState.value = false
}
