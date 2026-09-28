/**
 * 🔔 Web Push (A3) — ชั้นที่คุยกับ **เบราว์เซอร์** (PushManager + Notification)
 *
 * แบ่งความรับผิดชอบชัดเจน:
 *   - ไฟล์นี้ = ขอสิทธิ์, subscribe/unsubscribe กับอุปกรณ์นี้, จำสถานะเป็น ref
 *   - `services/notification.ts` = ยิง API ไปบอกเซิร์ฟเวอร์ (ไม่มี logic ของเบราว์เซอร์)
 *   - `components/PushSettingsCard.vue` = แสดงผล 5 สถานะ + เรียกฟังก์ชันในไฟล์นี้
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

/** ผลของการกดเปิด — แยก "ถูกปฏิเสธ" ออกจาก "ยังไม่ตัดสินใจ" ให้ UI พูดถูก */
export type PushEnableResult = 'enabled' | 'denied' | 'dismissed'

/** รอตัวช่วยแอพเวอร์ชันใหม่สลับที่ — นานพอสำหรับเน็ตช้า แต่ไม่ค้างจนผู้ใช้รำคาญ */
const SWAP_TIMEOUT_MS = 5000

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

  // ① ฝั่งเบราว์เซอร์ — ไม่ใช้เน็ต
  try {
    subscribedState.value = (await readLocalSubscription()) !== null
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

    // เครื่องที่เคยเปิดไว้แล้ว: endpoint เดิมถูกใช้ซ้ำได้ ⇒ ไม่ต้อง subscribe ใหม่
    // (เบราว์เซอร์คืน subscription เดิมเสมอถ้ายังไม่ถูก unsubscribe)
    const existing = reg.pushManager ? await reg.pushManager.getSubscription() : null
    const sub =
      existing ??
      (await reg.pushManager.subscribe({
        // ⚠️ Chrome บังคับ `true` — push ที่ไม่แสดงอะไรให้ผู้ใช้จะถูกบล็อก
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(publicKeyState.value),
      }))

    const json = sub.toJSON()
    const p256dh = json.keys?.p256dh
    const auth = json.keys?.auth
    if (!p256dh || !auth) throw new Error('เบราว์เซอร์ไม่ส่งคีย์ของอุปกรณ์มาให้')

    const res = await subscribePush({ endpoint: sub.endpoint, keys: { p256dh, auth } })
    subscribedState.value = true
    deviceCountState.value = res.device_count
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
  } finally {
    busyState.value = false
  }
}

/** ให้การ์ดเรียกหลัง login/logout เพื่อล้างสถานะของคนก่อนหน้าออกจากหน้าจอ */
export function resetPushStatus(): void {
  subscribedState.value = false
  deviceCountState.value = 0
  publicKeyState.value = ''
  enabledState.value = false
  readyState.value = false
  // ⚠️ ต้องล้างด้วย — ถ้างานเปิด/ปิดค้างอยู่ตอนที่ผู้ใช้ออกจากระบบ สวิตช์จะค้าง disabled
  //    ตลอดไป (finally ของงานที่ถูกทิ้งกลางทางไม่ได้รัน) ⇒ กดใหม่ไม่ได้เลยโดยไม่มีอะไรบอก
  busyState.value = false
}
