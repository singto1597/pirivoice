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

const deferredPrompt = ref<BeforeInstallPromptEvent | null>(null)
const canInstallState = ref(false)
const updateAvailableState = ref(false)
const standaloneState = ref(false)
const registration = ref<ServiceWorkerRegistration | null>(null)

/** โหลดแล้วหรือยัง — กันแบนเนอร์กะพริบขึ้นมาแล้วหาย */
const ready = ref(false)

// reload หลังอัปเดต SW — ต้องกันไม่ให้วนซ้ำ (controllerchange ยิงได้หลายครั้ง)
let reloading = false

function isDismissed(): boolean {
  try {
    return localStorage.getItem(DISMISS_KEY) === '1'
  } catch {
    // localStorage ถูกบล็อก (private mode / ตั้งค่าเบราว์เซอร์) — ถือว่ายังไม่ปิด
    return false
  }
}

/** ควรแสดงแบนเนอร์ชวนติดตั้งไหม */
export const showInstallBanner = computed(
  () => ready.value && canInstallState.value && !standaloneState.value,
)

export const showUpdateBanner = computed(() => ready.value && updateAvailableState.value)

export function registerPwa(): void {
  if (typeof window === 'undefined') return

  standaloneState.value = window.matchMedia('(display-mode: standalone)').matches

  // ── ชวนติดตั้ง ────────────────────────────────────────────────────────────
  // ⚠️ แสดง **เฉพาะเมื่อได้ event จริง** — ห้ามเดาจาก user agent
  //    (iOS Safari ไม่ยิง event นี้เลย ⇒ ผู้ใช้ iOS จะไม่เห็นแบนเนอร์ ซึ่งถูกต้อง
  //     ดีกว่าโชว์ปุ่มที่กดแล้วไม่มีอะไรเกิดขึ้น)
  window.addEventListener('beforeinstallprompt', (event) => {
    // ห้ามเบราว์เซอร์โชว์แบนเนอร์ของตัวเอง — เราคุมจังหวะเอง
    event.preventDefault()
    deferredPrompt.value = event as unknown as BeforeInstallPromptEvent
    canInstallState.value = !isDismissed()
  })

  window.addEventListener('appinstalled', () => {
    deferredPrompt.value = null
    canInstallState.value = false
    standaloneState.value = true
  })

  // ── service worker ────────────────────────────────────────────────────────
  if (import.meta.env.PROD && 'serviceWorker' in navigator) {
    navigator.serviceWorker
      .register('/sw.js')
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

  // ติดตั้งแล้วไม่ต้องถามอีก — ถ้าปัดออก (dismissed) ยังถามได้ใหม่ในเซสชันหน้า
  if (outcome === 'accepted') dismissInstall()

  return outcome
}

/** ผู้ใช้กดปิดแบนเนอร์ — จำไว้ ไม่ถามซ้ำอีก */
export function dismissInstall(): void {
  try {
    localStorage.setItem(DISMISS_KEY, '1')
  } catch {
    // เขียนไม่ได้ก็ไม่เป็นไร — แค่จำข้ามเซสชันไม่ได้
  }
  canInstallState.value = false
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
