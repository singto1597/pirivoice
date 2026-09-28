/**
 * PWA bootstrap (A1) — ลงทะเบียน service worker + ดัก beforeinstallprompt + ดักเวอร์ชันใหม่
 *
 * เรียกครั้งเดียวจาก `main.ts` (`registerPwa()`)
 *
 * ⚠️ **ลงทะเบียน SW เฉพาะ production** (`import.meta.env.PROD`)
 *    ตอน `npm run dev` ไม่ลง — เพราะ SW จะ cache `index.html` ทับ แล้วการแก้โค้ด
 *    จะไม่เห็นผลจนกว่าจะ hard reload (และจะหาสาเหตุยากมาก)
 *    ⇒ ทดสอบ PWA ให้ใช้ `npm run build && npm run preview` หรือ staging จริง
 *
 * สถานะทั้งหมดเป็น `ref` ที่ export ออกไปให้ `components/InstallPrompt.vue` ผูก —
 * ไม่ใช้ event bus เพราะมีผู้ใช้รายเดียว (InstallPrompt) และต้องรอดู state ตอน mount
 */
import { computed, readonly, ref } from 'vue'

/** Chrome/Edge เท่านั้นที่มี event นี้ — ไม่มีใน TS lib ⇒ ประกาศเอง */
export interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>
}

/** ผู้ใช้เคยกดปิดแบนเนอร์ — จำไว้ ไม่ถามซ้ำ */
const DISMISS_KEY = 'piri_install_dismissed'

/**
 * ติดตั้งสำเร็จแล้ว — **คนละคีย์กับ `DISMISS_KEY` โดยเจตนา**
 *
 * ⚠️ เดิมใช้คีย์เดียวกับ "กดปิดแบนเนอร์" ⇒ ผู้ใช้ที่ติดตั้งแล้ว *ถอนการติดตั้ง*
 *    จะไม่ถูกชวนติดตั้งอีกเลยตลอดไป (`isDismissed()` ยังเป็น true อยู่)
 *    ซึ่งเป็นพฤติกรรมที่ผิด — "ติดตั้งแล้ว" กับ "ไม่อยากติดตั้ง" คนละเรื่องกัน
 */
const INSTALLED_KEY = 'piri_installed'

/** ผู้ใช้ iOS เคยกดปิดคำแนะนำ "แชร์ → เพิ่มไปที่หน้าจอ" */
const IOS_HINT_KEY = 'piri_ios_hint_dismissed'

const deferredPrompt = ref<BeforeInstallPromptEvent | null>(null)
const canInstallState = ref(false)
const updateAvailableState = ref(false)
const standaloneState = ref(false)
const iosSafariState = ref(false)
const iosHintDismissedState = ref(false)
const registration = ref<ServiceWorkerRegistration | null>(null)

/** โหลดแล้วหรือยัง — กันแบนเนอร์กะพริบขึ้นมาแล้วหาย */
const ready = ref(false)

// reload หลังอัปเดต SW — ต้องกันไม่ให้วนซ้ำ (controllerchange ยิงได้หลายครั้ง)
let reloading = false

function readFlag(key: string): boolean {
  try {
    return localStorage.getItem(key) === '1'
  } catch {
    // localStorage ถูกบล็อก (private mode / ตั้งค่าเบราว์เซอร์) — ถือว่ายังไม่ตั้ง
    return false
  }
}

function writeFlag(key: string): void {
  try {
    localStorage.setItem(key, '1')
  } catch {
    // เขียนไม่ได้ก็ไม่เป็นไร — แค่จำข้ามเซสชันไม่ได้
  }
}

function isDismissed(): boolean {
  return readFlag(DISMISS_KEY)
}

function isInstalled(): boolean {
  return readFlag(INSTALLED_KEY)
}

/**
 * iOS/iPadOS **Safari** — ไม่มี `beforeinstallprompt` และไม่มี API ติดตั้งใด ๆ เลย
 * ผู้ใช้ต้องกด แชร์ → "เพิ่มไปที่หน้าจอ" เองเท่านั้น ⇒ ทางเลือกเดียวที่เรามีคือ **สอน**
 *
 * ⚠️ เบราว์เซอร์อื่นบน iOS (Chrome/Firefox/Edge) ติดตั้งไม่ได้เลยแม้จะกดแชร์
 *    ⇒ ต้องเจาะจงเฉพาะ Safari ไม่งั้นจะสอนผิด
 * ⚠️ iPadOS 13+ รายงาน UA เป็น `Macintosh` ⇒ ต้องเช็ค `maxTouchPoints` ประกอบ
 */
function detectIosSafari(): boolean {
  if (typeof navigator === 'undefined') return false
  const ua = navigator.userAgent
  const isIos = /iPad|iPhone|iPod/.test(ua) || (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1)
  const isOtherBrowser = /CriOS|FxiOS|EdgiOS|OPiOS/.test(ua)
  return isIos && !isOtherBrowser
}

// ── ผูก listener ตอน import — **ไม่ใช่** ตอนเรียก `registerPwa()` ────────────────
//
// ⚠️ `beforeinstallprompt` ยิง **ครั้งเดียวต่อการโหลดหน้า และกู้คืนไม่ได้** — ถ้า
//    listener ยังไม่ผูกตอนที่มันยิง event จะหายถาวร ⇒ ผู้ใช้ไม่เห็นแบนเนอร์ทั้งเซสชัน
//    เดิมผูกไว้ใน `registerPwa()` ซึ่ง `main.ts` เรียก **หลัง** `app.mount()` ⇒
//    แพ้การแข่งกับ Chrome ได้จริง (Chrome ตัดสิน installability แล้วยิงเร็วมาก)
//    โมดูลนี้ถูก import ที่บรรทัดบนของ `main.ts` ⇒ ผูกตรงนี้ = เร็วที่สุดเท่าที่ทำได้
if (typeof window !== 'undefined') {
  window.addEventListener('beforeinstallprompt', (event) => {
    // ห้ามเบราว์เซอร์โชว์แบนเนอร์ของตัวเอง — เราคุมจังหวะเอง
    event.preventDefault()
    deferredPrompt.value = event as unknown as BeforeInstallPromptEvent
    canInstallState.value = !isDismissed() && !isInstalled()
  })

  window.addEventListener('appinstalled', () => {
    deferredPrompt.value = null
    canInstallState.value = false
    standaloneState.value = true
    writeFlag(INSTALLED_KEY)
  })
}

/** ควรแสดงแบนเนอร์ชวนติดตั้งไหม */
export const showInstallBanner = computed(
  () => ready.value && canInstallState.value && !standaloneState.value,
)

export const showUpdateBanner = computed(() => ready.value && updateAvailableState.value)

/**
 * ควรแสดงคำแนะนำติดตั้งแบบ iOS ไหม (แชร์ → เพิ่มไปที่หน้าจอ)
 *
 * iOS ไม่มี event ให้ดัก ⇒ ถ้าไม่แสดงอะไรเลย ผู้ใช้ iOS จะไม่มีทางรู้ว่าติดตั้งได้
 * ⇒ ใช้ช่องเดียวกับแบนเนอร์ติดตั้ง (สองอย่างนี้ไม่มีทางเกิดพร้อมกัน เพราะ iOS
 *    ไม่ยิง `beforeinstallprompt` เลย)
 */
export const showIosHint = computed(
  () =>
    ready.value &&
    iosSafariState.value &&
    !iosHintDismissedState.value &&
    !standaloneState.value &&
    !isInstalled(),
)

/**
 * URL ของ service worker — ต่อ `?v=<build>` ทุก build
 *
 * ⚠️ **จำเป็น ไม่ใช่ความสวยงาม** — Cloudflare แทนที่ `Cache-Control` จาก origin
 *    ด้วย `max-age=14400` ของตัวเอง ⇒ `/sw.js` ตรง ๆ ค้างได้ถึง 4 ชม. แม้ nginx
 *    จะส่ง `no-cache, must-revalidate` มาแล้ว (ดู docs/skills.md)
 *    การเปลี่ยน URL ทุก build ทำให้ CDN ไม่มี URL เก่าให้เสิร์ฟ ⇒ อัปเดตถึงมือเสมอ
 *
 * (`typeof` กัน ReferenceError เผื่อรันในบริบทที่ `define` ไม่ถูกฉีด เช่น vitest)
 */
const SW_URL = `/sw.js?v=${typeof __BUILD_ID__ === 'string' ? __BUILD_ID__ : 'dev'}`

export function registerPwa(): void {
  if (typeof window === 'undefined') return

  standaloneState.value = window.matchMedia('(display-mode: standalone)').matches
  iosSafariState.value = detectIosSafari()
  iosHintDismissedState.value = readFlag(IOS_HINT_KEY)

  // ── service worker ────────────────────────────────────────────────────────
  if (import.meta.env.PROD && 'serviceWorker' in navigator) {
    navigator.serviceWorker
      .register(SW_URL)
      .then((reg) => {
        registration.value = reg
        watchForUpdate(reg)
      })
      .catch(() => {
        // ลงทะเบียนไม่ได้ (เช่น เบราว์เซอร์รุ่นเก่า/โหมดส่วนตัว) — เว็บยังใช้ได้ปกติ
      })
  }

  ready.value = true
}

/** ดักว่า SW ใหม่รออยู่ในสถานะ `waiting` */
function watchForUpdate(reg: ServiceWorkerRegistration): void {
  // เปิดแท็บซ้ำตอนมีเวอร์ชันใหม่ค้างอยู่แล้ว
  if (reg.waiting && navigator.serviceWorker.controller) updateAvailableState.value = true

  reg.addEventListener('updatefound', () => {
    const installing = reg.installing
    if (!installing) return

    installing.addEventListener('statechange', () => {
      // `installed` + มี controller อยู่แล้ว = เป็น **เวอร์ชันใหม่**
      // (ถ้าไม่มี controller = การติดตั้งครั้งแรก ไม่ต้องบอกให้อัปเดต)
      if (installing.state === 'installed' && navigator.serviceWorker.controller) {
        updateAvailableState.value = true
      }
    })
  })
}

/** ผู้ใช้กด "ติดตั้ง" — คืนผลลัพธ์ไว้ให้ UI ตัดสินใจต่อ */
export async function promptInstall(): Promise<'accepted' | 'dismissed' | 'unavailable'> {
  const event = deferredPrompt.value
  if (!event) return 'unavailable'

  await event.prompt()
  const { outcome } = await event.userChoice

  // event ใช้ได้ครั้งเดียว — ต้องทิ้งเสมอไม่ว่าผลจะเป็นอะไร
  deferredPrompt.value = null
  canInstallState.value = false

  // ⚠️ ติดตั้งสำเร็จ ≠ ไม่อยากติดตั้ง — ต้องจำคนละคีย์ (ถ้าปัดออก = ยังถามใหม่ได้
  //    ในเซสชันหน้า เพราะเบราว์เซอร์จะยิง `beforeinstallprompt` ให้ใหม่)
  if (outcome === 'accepted') writeFlag(INSTALLED_KEY)

  return outcome
}

/** ผู้ใช้กดปิดแบนเนอร์ — จำไว้ ไม่ถามซ้ำอีก */
export function dismissInstall(): void {
  writeFlag(DISMISS_KEY)
  canInstallState.value = false
}

/** ผู้ใช้ iOS กดปิดคำแนะนำ — จำไว้ ไม่รบกวนซ้ำ */
export function dismissIosHint(): void {
  writeFlag(IOS_HINT_KEY)
  iosHintDismissedState.value = true
}

/**
 * ผู้ใช้กด "อัปเดต" — สั่ง SW ที่รออยู่ให้ข้ามไป แล้ว reload **ครั้งเดียว**
 *
 * ⚠️ ไม่ auto-reload เอง — ผู้ใช้อาจกำลังกรอกเรื่องอยู่ การตัดกลางทางคือการทำร้าย
 *    ข้อมูลที่เขาเพิ่งพิมพ์
 */
export function applyUpdate(): void {
  const reg = registration.value
  const waiting = reg?.waiting

  if (!waiting) {
    window.location.reload()
    return
  }

  navigator.serviceWorker.addEventListener('controllerchange', () => {
    if (reloading) return
    reloading = true
    window.location.reload()
  })

  waiting.postMessage({ type: 'SKIP_WAITING' })
}

export const pwaReady = readonly(ready)
