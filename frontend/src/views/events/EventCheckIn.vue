<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import AppButton from '@/components/ui/AppButton.vue'
import AppSheet from '@/components/ui/AppSheet.vue'
import IconButton from '@/components/ui/IconButton.vue'
import { checkInRegistration, getPublicEvent } from '@/services/event'
import { readQrFrame } from '@/qrReader'
import { SCAN_INTERVAL_MS, checkInBanner, createScanGate } from '@/qrScanner'
import { fmtTime } from '@/datetime'
import { useAppChrome } from '@/composables/useAppChrome'
import type { PublicEvent } from '@/types/event'
import type { ApiError } from '@/services/api'
import { goUnavailable } from '@/router/unavailable'

/**
 * 📷 หน้าสแกนเช็คอินหน้างาน (D2) — **ของสภา** (ต้องมี MANAGE_EVENTS)
 *
 * 🎯 ลำดับความสำคัญของการออกแบบหน้านี้ ต่างจากหน้าอื่นทั้งระบบ:
 *    1. **สภาเห็น "ชื่อคน" ต้องชัดที่สุด** — การสแกนเป็นแค่ทางลัดในการ *หยิบชื่อ*
 *       ส่วนด่านจริงคือสายตาสภาที่เทียบชื่อกับหน้าคนตรงหน้า (ดู `core/check_in_token.py`)
 *       ⇒ ชื่อจึงเป็นตัวใหญ่สุดในหน้า ไม่ใช่ไอคอนติ๊กถูก
 *    2. **ห้ามมี modal บัง** — คิวที่ประตูคือคนยืนรอเป็นแถว ⇒ ใช้แถบในหน้าแทน `Swal.fire`
 *       (ต่างจากทุกหน้าที่เหลือของระบบที่ใช้ Swal) เพราะ Swal ต้องมีคนกดปิดทุกรอบ
 *    3. **กล้องพังต้องไม่ทำให้เช็คอินไม่ได้** — มีช่องกรอกรหัสเสมอ และกล้องที่ถูกปฏิเสธ
 *       สิทธิ์ไม่ใช่ error ที่ต้องแก้ก่อนใช้งาน
 *
 * ⚠️ **ห้ามเทียบเวลาที่นี่** — เวลาที่เช็คอินคือค่าที่ server เขียน (`checked_in_at`)
 *    ไม่ใช่ `new Date()` ของเครื่องสภา
 *
 * ─────────────────────────────────────────────────────────────────────────────
 * 🔄 **รอบ 4 (R4.4) — เปลี่ยนจาก "การ์ดในหน้า" เป็น "กล้องเต็มจอ + แถบผลลัพธ์"**
 *
 * ⚠️ **แผน R4.4 เขียนขัดกันเอง** — บรรทัดหนึ่งสั่ง "ของเดิมไม่ใช้ modal เลย (ถูกต้อง
 *    ตาม skills #16) — **เก็บแนวนี้ไว้**" อีกบรรทัดสั่ง "ผลลัพธ์เป็น `AppSheet` ลอยจากล่าง"
 *    ⇒ เลือก **ไม่ใช้ modal** เพราะเหตุผล 3 ข้อนี้ (และเพราะ skills #16 พูดถึง *ฟอร์ม*
 *    ไม่ใช่ *การแสดงผล* — การอ้างถึง #16 ในแผนจึงไม่ตรงประเด็น):
 *      1. **คิวที่ประตูคือคนยืนรอเป็นแถว** — ทุกวินาทีที่จอถูกบังคือคนที่ยังไม่ได้เข้า
 *      2. **ความสูงคงที่ ⇒ กล้องไม่กระตุก** — แผนต้องการ "กล้องเต็มพื้นที่ด้านบน"
 *         ถ้าแถบโผล่/หาย กล้อง (`flex-1`) จะยืด/หด ⇒ **กรอบเล็งขยับทุกครั้งที่มีคนสแกน**
 *         แล้วสภาต้องเล็งใหม่ทุกรอบ · การจองที่ไว้ถาวรตัดปัญหานี้ที่โครงสร้าง
 *      3. การ "จองที่" ไม่ได้เสียเปล่า — ช่องว่างนั้นคือสถานะ **"พร้อมสแกน"**
 *         ซึ่งเป็น 1 ในสถานะที่แผนต้องการอยู่แล้ว
 *
 * 🔴 **เปลี่ยนจากของเดิม 2 อย่างโดยเจตนา:**
 *    · **ผลลัพธ์เหลือช่องเดียว (ใหม่ทับเก่า)** — ของเดิมมี 2 ช่อง (`banner` + `errorText`)
 *      พร้อมคอมเมนต์ "ห้ามล้าง `banner` ทิ้ง" · แต่เมื่อแถบมีที่เดียว การคงผลของคนก่อนไว้
 *      **ข้าง ๆ** error ของคนปัจจุบันจะทำให้อ่านไม่ออกว่า error เป็นของใคร
 *      (คนที่ยืนอยู่ตรงหน้าหรือคนที่เดินเข้าไปแล้ว?) ⇒ ยึด "ผลของการสแกนครั้งล่าสุด" เสมอ
 *    · **"สำเร็จ" ล้างตัวเองใน 8 วินาที** — ถ้าค้างไว้แล้วบัตรคนถัดไปอ่านไม่ออก
 *      (แสงย้อน/มือสั่น) สภาจะเห็นชื่อคนก่อนหน้าค้างอยู่แล้ว **เข้าใจว่าคนที่ยืนอยู่เช็คอินแล้ว**
 *      = ความผิดพลาดที่แพงที่สุดของหน้านี้ · ส่วน "ซ้ำ"/"ไม่สำเร็จ" **ไม่ล้างเอง**
 *      เพราะต้องมีคนอ่านแล้วตัดสินใจ ⇒ เข้ากับกฎที่ใช้ทั้งโปรเจกต์:
 *      *ผลสำเร็จหายเอง · อะไรที่ต้องมีคนตัดสินใจรอคนกด*
 *
 * 🗂️ **สองโหมด (ไม่ใช่ modal):**
 *    · `scan` — กล้องเต็มจอ + แถบผลลัพธ์ล่าง
 *    · `code` — หน้าเต็มสำหรับกรอกรหัส (skills #16: ฟอร์มที่ผู้ใช้ต้องพิมพ์ ต้องเป็นหน้าเต็ม)
 *    สลับด้วย `⋯` และ **สลับอัตโนมัติเมื่อกล้องถูกปฏิเสธ/ใช้ไม่ได้** — เพราะ "วันที่กล้องพัง
 *    คือวันที่ต้องใช้ทางนี้" (คอมเมนต์เดิม) ⇒ ทางสำรองต้องโผล่เอง ไม่ใช่รอให้ตามหา
 */
const route = useRoute()
const router = useRouter()
const chrome = useAppChrome()
const eventId = Number(route.params.id)

/** ผลของการเช็คอินครั้งล่าสุด — ช่องเดียว (ดูเหตุผลในคอมเมนต์หัวไฟล์) */
type CheckInResult =
  | { kind: 'ok' | 'again'; title: string; name: string; checkedInAt: string | null }
  | { kind: 'error'; title: string; detail: string }

type Mode = 'scan' | 'code'

const event = ref<PublicEvent | null>(null)
const eventError = ref('')

const result = ref<CheckInResult | null>(null)
const busy = ref(false)
const mode = ref<Mode>('scan')
const actionsOpen = ref(false)

/** กล้อง — `unsupported` = เบราว์เซอร์ไม่มี getUserMedia · `denied` = ผู้ใช้ไม่ให้สิทธิ์ */
const videoEl = ref<HTMLVideoElement | null>(null)
const codeInputEl = ref<HTMLInputElement | null>(null)
const cameraState = ref<'idle' | 'starting' | 'live' | 'denied' | 'unsupported'>('idle')
const cameraError = ref('')

const manualToken = ref('')

/** ของที่ไม่ต้อง reactive — เก็บเป็นตัวแปรธรรมดาเพื่อให้ cleanup เข้าถึงได้ แต่ไม่ต้อง re-render */
const gate = createScanGate()
let stream: MediaStream | null = null
let rafId = 0
let canvas: HTMLCanvasElement | null = null
let lastScanAt = 0
/** กัน callback ของ rAF ที่ค้างอยู่ในคิวไม่ให้ทำงานหลัง unmount */
let alive = false
let resultTimer = 0
/**
 * 🔢 เลขรอบของ "ความพยายามเปิดกล้อง" — ตัวตัดสินว่า `await getUserMedia` ที่ค้างอยู่
 *    ยังมีสิทธิ์เขียนสถานะหรือไม่
 *
 * ⚠️ **ห้ามใช้ `mode` ตัดสินแทน** (ซึ่งเป็นสิ่งที่เขียนไว้ตอนแรก และพัง): ปุ่ม
 *    "เปิดกล้องอีกครั้ง" ในโหมดกรอกรหัสเรียก `startCamera` **ขณะที่ `mode` ยังเป็น `'code'`**
 *    ⇒ ถ้าใช้ `mode !== 'scan'` เป็นเงื่อนไขยกเลิก มันจะ **ทิ้งสตรีมที่เพิ่งขอมาทุกครั้ง**
 *    = ปุ่มที่กดแล้วไม่มีอะไรเกิดขึ้นตลอดไป
 */
let cameraAttempt = 0

/**
 * ⏱️ ระยะที่ชื่อคนที่เพิ่งเช็คอินค้างบนจอ
 *
 * สั้นพอที่จะไม่กลายเป็นข้อมูลเก่าที่หลอกสภา แต่ยาวพอให้อ่านชื่อ (2 พยางค์) แล้วเงยหน้า
 * เทียบกับคนตรงหน้าได้ — ถ้าเปลี่ยนค่านี้ ต้องคิดถึง **ทั้งสองด้าน** ไม่ใช่แค่ด้านเดียว
 */
const SUCCESS_HOLD_MS = 8000

const isLive = computed(() => cameraState.value === 'live')
/** กล้องใช้ไม่ได้ด้วยเหตุที่ผู้ใช้แก้เองไม่ได้ในทันที ⇒ โชว์ทางออกให้เห็นชัด */
const cameraBlocked = computed(
  () => cameraState.value === 'denied' || cameraState.value === 'unsupported',
)

/** สีของแถบผลลัพธ์ — มาจาก token เท่านั้น (ห้ามฮาร์ดโค้ดสีสถานะ) */
const BAND_TONE: Record<'ok' | 'again' | 'error', string> = {
  ok: 'bg-ok-soft',
  again: 'bg-warn-soft',
  error: 'bg-danger-soft',
}
const bandTone = computed(() =>
  result.value ? BAND_TONE[result.value.kind] : 'bg-surface',
)

onMounted(async () => {
  alive = true
  void loadEvent()
  // `autoFallback: true` — รอบแรกที่เปิดหน้า ถ้าผู้ใช้ปฏิเสธสิทธิ์ให้พาไปโหมดกรอกรหัสเลย
  // (ไม่ใช่จอดำที่ต้องเดาเองว่าต้องทำอะไรต่อ)
  await startCamera(true)
})

/**
 * ⚠️ **ต้องหยุดกล้องตอนออกจากหน้าเสมอ** — ไฟกล้องค้างคือสัญญาณว่าเว็บยังแอบใช้กล้องอยู่
 *    (ผู้ใช้เห็นแล้วจะปิดทั้งแท็บ) และบนมือถือมันกินแบตต่อเนื่อง
 */
onBeforeUnmount(() => {
  alive = false
  clearTimeout(resultTimer)
  stopCamera()
})

function stopCamera() {
  if (rafId) {
    cancelAnimationFrame(rafId)
    rafId = 0
  }
  // หยุด **ทุก track** ไม่ใช่แค่ปิด element — track ที่ไม่ถูก stop จะค้างอยู่ที่ระดับ OS
  stream?.getTracks().forEach((t) => t.stop())
  stream = null
  if (videoEl.value) videoEl.value.srcObject = null
  cameraState.value = 'idle'
}

async function loadEvent() {
  try {
    event.value = await getPublicEvent(eventId)
  } catch (e) {
    // 🚪 404 = กิจกรรมนี้เปิดดูไม่ได้เลย (ฉบับร่าง/ถูกลบ) ⇒ **เช็คอินก็ทำไม่ได้**
    //    (ไม่มีกิจกรรมให้เช็คอิน) ⇒ พาออกไปที่ที่ไปต่อได้ เหมือน `EventDetail` ทุกประการ
    //    ไม่ใช่โชว์ error ค้างไว้ให้กดสแกนแล้วล้มเหลวซ้ำ ๆ
    if (e instanceof Error && (e as ApiError).status === 404) {
      await goUnavailable(router, 'event')
      return
    }
    // กรณีอื่น (เน็ตสะดุด/500) ยังสแกนต่อได้ — การเช็คอินไม่ได้ขึ้นกับชื่อเรื่อง
    eventError.value = e instanceof Error ? e.message : 'โหลดข้อมูลกิจกรรมไม่สำเร็จ'
  }
}

/**
 * เปิดกล้อง
 *
 * @param autoFallback `true` = ถ้าเปิดไม่ได้ให้พาไปโหมดกรอกรหัสทันที
 *   ⚠️ **ต้องเป็นพารามิเตอร์ ไม่ใช่พฤติกรรมตายตัว** — ปุ่ม "กลับไปสแกน" ในโหมดกรอกรหัส
 *      ใช้ `false` ไม่งั้นเมื่อกล้องยังถูกปฏิเสธอยู่ มันจะเด้งกลับโหมดเดิมทันที
 *      ⇒ **ปุ่มดูเหมือนกดแล้วไม่มีอะไรเกิดขึ้น** (ผู้ใช้จะกดซ้ำแล้วสรุปว่าแอปค้าง)
 */
async function startCamera(autoFallback: boolean) {
  // กันดับเบิลคลิก: สถานะเป็น ref (เปลี่ยนทันที) แต่ DOM อัปเดตช้ากว่า
  // ⇒ คลิกรัว ๆ ในจังหวะเดียวกันจะเรียก getUserMedia ซ้อน แล้ว `stream` ตัวเก่าจะค้างไม่ถูก stop
  // (ไฟกล้องติดค้างโดยไม่มีใครอ้างถึง) — ประตูนี้ปิดช่องนั้น
  if (cameraState.value === 'starting') return

  if (!navigator.mediaDevices?.getUserMedia) {
    // เกิดจริงบน http:// (ไม่ใช่ localhost) — `getUserMedia` ต้องมี secure context
    cameraState.value = 'unsupported'
    cameraError.value = 'เบราว์เซอร์นี้ไม่รองรับกล้อง หรือหน้านี้ไม่ได้เปิดผ่าน https'
    if (autoFallback) mode.value = 'code'
    return
  }

  const attempt = ++cameraAttempt
  cameraState.value = 'starting'
  cameraError.value = ''
  try {
    const acquired = await navigator.mediaDevices.getUserMedia({
      // `ideal` ไม่ใช่ `exact` — เครื่องที่ไม่มีกล้องหลังต้องยังใช้กล้องหน้าได้
      // (สแกนบัตรด้วยกล้องหน้าก็ได้ แค่ต้องยื่นบัตรให้ห่างหน่อย) ดีกว่าไม่ได้กล้องเลย
      video: { facingMode: { ideal: 'environment' } },
      audio: false,
    })
    // ผู้ใช้ออกจากหน้าไประหว่างที่เบราว์เซอร์กำลังถามสิทธิ์ (หรือกด "กรอกรหัสเอง" ทับ)
    // ⇒ ปิดทันทีไม่งั้นกล้องค้างทำงานอยู่เบื้องหลังฟอร์ม
    // 🔴 **ด่านนี้ต้องมาก่อน `stream = acquired` เสมอ** — ถ้าผูกก่อนแล้วรอบนี้ถูกยกเลิก
    //    สตรีมจะค้างอยู่ในตัวแปร `stream` โดยที่ `stopCamera()` ของรอบใหม่ไปหยุด **ตัวอื่น**
    //    ⇒ ไฟกล้องติดค้างโดยไม่มีใครอ้างถึง (อาการที่ผู้ใช้ตีความว่า "เว็บแอบดูอยู่")
    if (!alive || attempt !== cameraAttempt) {
      acquired.getTracks().forEach((t) => t.stop())
      return
    }
    stream = acquired

    // 🎥 **ต้องสลับไปโหมดสแกนก่อน แล้วรอ DOM วาด `<video>`** — ปุ่ม "เปิดกล้องอีกครั้ง"
    //    ในโหมดกรอกรหัสเรียกมาถึงตรงนี้ขณะที่ `<video>` ยังไม่ถูกสร้าง ⇒ ถ้าไม่รอ
    //    `videoEl` เป็น `null` แล้วกล้องจะขึ้นสถานะ `live` **โดยไม่มีภาพ** = จอดำที่ดู
    //    เหมือนกล้องพัง ซึ่งเป็นอาการที่ผู้ใช้แก้ไม่ถูก (และจะโทษว่าแอปพัง)
    mode.value = 'scan'
    await nextTick()
    if (!alive || attempt !== cameraAttempt) {
      acquired.getTracks().forEach((t) => t.stop())
      stream = null
      return
    }
    if (videoEl.value) {
      videoEl.value.srcObject = acquired
      // `play()` อาจ reject ถ้าผู้ใช้ยังไม่ได้ interact — ไม่ใช่เรื่องคอขวด เพราะ
      // `autoplay muted playsinline` ที่ element จะเล่นให้เองอยู่แล้ว
      await videoEl.value.play().catch(() => undefined)
    }
    cameraState.value = 'live'
    rafId = requestAnimationFrame(tick)
  } catch (e) {
    // รอบที่ถูกยกเลิกไปแล้วต้องไม่เขียนทับสถานะของรอบใหม่
    if (!alive || attempt !== cameraAttempt) return
    cameraState.value = 'denied'
    cameraError.value =
      e instanceof Error && e.name === 'NotAllowedError'
        ? 'ยังไม่ได้อนุญาตให้ใช้กล้อง — กด "เปิดกล้องอีกครั้ง" แล้วเลือก "อนุญาต" หรือใช้ช่องกรอกรหัสแทน'
        : 'เปิดกล้องไม่สำเร็จ — ใช้ช่องกรอกรหัสแทนได้'
    if (autoFallback) mode.value = 'code'
  }
}

/**
 * ⚠️ **ปิดกล้องเมื่อออกจากโหมดสแกน** — ไม่มีเหตุให้กล้องทำงานอยู่เบื้องหลังฟอร์ม
 *    (ไฟกล้องค้าง = ผู้ใช้คิดว่าเว็บแอบดูอยู่ และกินแบตเปล่า ๆ ระหว่างพิมพ์)
 */
function enterCodeMode() {
  // ยกเลิกรอบที่กำลังขอสิทธิ์อยู่ — เบราว์เซอร์ถามสิทธิ์ค้างไว้ได้นานนับนาที
  // ถ้าไม่ยกเลิก ผู้ใช้ที่กด "กรอกรหัสเอง" ระหว่างนั้นจะโดนกล้องเด้งกลับมาเปิดเอง
  cameraAttempt++
  if (cameraState.value === 'live' || cameraState.value === 'starting') stopCamera()
  mode.value = 'code'
}

/** ปุ่ม "กลับไปสแกน" ในโหมดกรอกรหัส — ไม่ auto-fallback (ดูเหตุผลใน `startCamera`) */
function enterScanMode() {
  mode.value = 'scan'
  void startCamera(false)
}

function retryCamera() {
  void startCamera(false)
}

function openCodeMode() {
  actionsOpen.value = false
  enterCodeMode()
}

function openCameraRetry() {
  actionsOpen.value = false
  retryCamera()
}

/**
 * วนอ่านเฟรม — **ไม่ประมวลผลทุกเฟรม** (ดู `SCAN_INTERVAL_MS`) เพราะ `jsQR` หนักพอที่จะ
 * ทำให้มือถือร้อนถ้าทำ 60 ครั้ง/วินาที ทั้งที่เฟรมใน 1/60 วินาทีไม่ต่างกันเลย
 */
function tick(now: number) {
  if (!alive) return
  rafId = requestAnimationFrame(tick)

  if (now - lastScanAt < SCAN_INTERVAL_MS) return
  const video = videoEl.value
  if (!video || video.readyState < video.HAVE_CURRENT_DATA) return
  lastScanAt = now

  const frame = grabFrame(video)
  if (!frame) return

  const token = readQrFrame(frame.data, frame.width, frame.height)
  // เฟรมส่วนใหญ่ไม่มี QR อยู่ในนั้น — `null` คือผลปกติ ไม่ใช่ error
  if (token) void submit(token, 'frame')
}

/**
 * ดึงเฟรมปัจจุบันเป็น RGBA
 *
 * ⚠️ **ย่อขนาดก่อนอ่าน** — กล้อง 1080p ให้ภาพ ~2 ล้านพิกเซล ซึ่ง `jsQR` ใช้เวลาเป็นสิบเท่า
 *    ของภาพ 640px โดยความแม่นยำไม่ดีขึ้น (QR บนบัตรกินพื้นที่ไม่กี่ร้อยพิกเซล)
 *    ⇒ 640 คือจุดที่ทั้งเร็วและยังอ่านบัตรได้สบาย
 */
function grabFrame(
  video: HTMLVideoElement,
): { data: Uint8ClampedArray; width: number; height: number } | null {
  const vw = video.videoWidth
  const vh = video.videoHeight
  if (!vw || !vh) return null

  const width = Math.min(640, vw)
  const height = Math.round((vh * width) / vw)

  canvas ??= document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  const ctx = canvas.getContext('2d', { willReadFrequently: true })
  if (!ctx) return null

  ctx.drawImage(video, 0, 0, width, height)
  return { data: ctx.getImageData(0, 0, width, height).data, width, height }
}

/** แสดงผลลัพธ์ใหม่ + ตั้งเวลาล้างตัวเองถ้าเป็นผลสำเร็จ (ดู `SUCCESS_HOLD_MS`) */
function showResult(next: CheckInResult) {
  clearTimeout(resultTimer)
  result.value = next
  if (next.kind !== 'ok') return
  resultTimer = window.setTimeout(() => {
    // ล้างเฉพาะเมื่อยังเป็นผลเดิม — ถ้าสแกนคนใหม่ไปแล้ว ห้ามลบของใหม่ทิ้ง
    // (เทียบตัวตนของออบเจกต์ ไม่ใช่เทียบเนื้อความ — ผลใหม่ที่เหมือนกันเป๊ะต้องไม่ถูกลบ)
    if (result.value === next) result.value = null
  }, SUCCESS_HOLD_MS)
}

/**
 * ส่งโทเคนไปเช็คอิน — **ประตูกันซ้ำอยู่ที่นี่ที่เดียว** ใช้ร่วมกันทั้งกล้องและช่องกรอก
 *
 * @param from `'frame'` = อ่านได้จากกล้อง (มี cooldown) · `'manual'` = สภาพิมพ์เอง (ไม่มี)
 */
async function submit(token: string, from: 'frame' | 'manual') {
  const now = performance.now()
  const allowed = from === 'frame' ? gate.beginFrame(token, now) : gate.beginManual(token, now)
  // เฟรมที่ถูกทิ้งไม่ต้องบอกอะไร (เป็นเรื่องปกติของวิดีโอ) — แต่การพิมพ์ที่ถูกทิ้งต้องบอก
  if (!allowed) {
    if (from === 'manual') {
      showResult({
        kind: 'error',
        title: 'กรุณารอสักครู่',
        detail: 'กำลังดำเนินการอยู่ — ลองใหม่อีกครั้ง',
      })
    }
    return
  }

  busy.value = true
  try {
    const res = await checkInRegistration(eventId, { token })
    const banner = checkInBanner(res)
    showResult({
      kind: banner.tone,
      title: banner.title,
      name: banner.name,
      checkedInAt: banner.checkedInAt,
    })
    if (from === 'manual') {
      manualToken.value = ''
      // ปิดคีย์บอร์ดก่อน — ไม่งั้นบนมือถือแถบผลลัพธ์ (ล่างจอ) ถูกคีย์บอร์ดบัง
      // แล้วสภาจะไม่เห็นว่าคนที่เพิ่งกรอกรหัสไปเช็คอินสำเร็จหรือไม่
      codeInputEl.value?.blur()
    }
  } catch (e) {
    const status = (e as ApiError).status
    showResult({
      kind: 'error',
      // 404 = บัตรไม่ตรงกับงานนี้ (backend ยังมี 404 "ไม่พบกิจกรรมนี้" อีกกรณี แต่กิจกรรม
      // ที่ถูกลบจะถูกดักที่ `loadEvent` แล้วพาออกไปก่อนถึงตรงนี้)
      title: status === 404 ? 'ไม่พบรหัสนี้' : 'เช็คอินไม่สำเร็จ',
      // ข้อความจาก server แยก "ถูกยกเลิกแล้ว" / "อยู่ในคิวสำรอง" / "เป็นของกิจกรรมอื่น"
      // ออกจากกันอยู่แล้ว ⇒ **ห้ามแทนที่ด้วยข้อความกลาง ๆ** สภาหน้างานต้องรู้ว่าต้องทำอะไรต่อ
      detail: e instanceof Error ? e.message : 'เช็คอินไม่สำเร็จ',
    })
  } finally {
    busy.value = false
    gate.finish()
  }
}

function submitManual() {
  if (!manualToken.value || busy.value) return
  void submit(manualToken.value, 'manual')
}

/** ปุ่ม "คนถัดไป" — ล้างผลของคนก่อนแล้วเปิดประตูให้บัตรใบเดิมผ่านได้ทันที */
function clearResult() {
  clearTimeout(resultTimer)
  result.value = null
  gate.reset()
}

/**
 * 🔴 **ต้องมีปลายทางสำรองเสมอ** — ถ้าอาศัย `chrome.backTarget` เฉย ๆ แล้ววันหนึ่งมีคนตั้ง
 *    `headerBack: false` ที่ route นี้ ปุ่มปิดจะกลายเป็นปุ่มที่กดแล้วไม่มีอะไรเกิดขึ้น
 *    = **ติดอยู่ในหน้ากล้องโดยไม่มีทางออก** ซึ่งเป็นสิ่งที่คอมเมนต์ใน `router/index.ts` เตือนไว้
 */
function close() {
  void router.push(chrome.backTarget.value ?? { name: 'event-management' })
}
</script>

<template>
  <!--
    🔒 `fixed inset-0` = กล้องเต็มจอจริง — ต้องหลุดออกจาก padding ของ `MainLayout`
       (`px-4 pt-4` + `pb-[calc(var(--app-nav-h)+…)]`) ไม่งั้นกล้องจะถูกรัดเป็นกล่อง
    📐 `z-30` — เหนือเนื้อหา shell (`z-10`) แต่ **ใต้** `AppSheet` (`z-[60]`) และติดตั้ง PWA
       (`z-40` · ซึ่งถูกซ่อนบนหน้านี้แล้ว ดู `InstallPrompt.vue`)
  -->
  <div class="fixed inset-0 z-30 flex flex-col bg-ink-1" data-testid="checkin-screen">
    <!-- ════════════════ พื้นที่หลัก: กล้อง หรือ ฟอร์ม ════════════════ -->
    <div class="relative min-h-0 flex-1">
      <!-- ──────────── โหมดสแกน ──────────── -->
      <template v-if="mode === 'scan'">
        <!-- `muted` + `playsinline` จำเป็นสำหรับ iOS: ถ้าไม่มี วิดีโอจะเด้งเป็น fullscreen
             และ autoplay จะถูกบล็อก -->
        <video
          ref="videoEl"
          class="h-full w-full object-cover"
          playsinline
          muted
          autoplay
          data-testid="scanner-video"
        ></video>

        <!-- กรอบเล็ง — บอกใบ้ว่าต้องวางบัตรตรงไหน (ไม่มีผลกับการอ่านจริง) -->
        <div
          v-if="isLive"
          class="pointer-events-none absolute inset-0 flex items-center justify-center"
        >
          <div class="aspect-square w-2/3 max-w-[16rem] rounded-2xl border-2 border-white/70"></div>
        </div>

        <!-- แถบบน — ทึบไล่ลงมาเพื่อให้ไอคอนขาวอ่านออกไม่ว่าภาพกล้องจะสว่างแค่ไหน -->
        <div class="absolute inset-x-0 top-0 bg-gradient-to-b from-black/70 to-transparent pb-8">
          <div class="pt-safe flex items-center gap-1 px-2">
            <IconButton
              icon="bi-x-lg"
              label="ปิดหน้าสแกน"
              tone="light"
              data-testid="close-checkin-btn"
              @click="close"
            />
            <div class="min-w-0 flex-1 text-center">
              <p class="truncate text-[15px] font-bold text-white">สแกนเช็คอิน</p>
              <p class="truncate text-caption text-white/70">
                {{ event?.title ?? eventError ?? 'กำลังโหลดกิจกรรม…' }}
              </p>
            </div>
            <IconButton
              icon="bi-three-dots"
              label="ตัวเลือกเพิ่มเติม"
              tone="light"
              data-testid="scan-actions-btn"
              @click="actionsOpen = true"
            />
          </div>
        </div>

        <!-- กล้องยังไม่ทำงาน — บอกเหตุผล + ทางออก (ไม่ใช่จอดำ) -->
        <div
          v-if="!isLive"
          class="absolute inset-0 flex flex-col items-center justify-center gap-3 px-8 text-center"
        >
          <i
            class="bi text-4xl text-white/60"
            :class="
              cameraState === 'starting' ? 'bi-arrow-repeat animate-spin' : 'bi-camera-video-off'
            "
          ></i>
          <p class="text-[15px] font-bold text-white">
            {{ cameraState === 'starting' ? 'กำลังเปิดกล้อง…' : 'กล้องยังไม่ทำงาน' }}
          </p>
          <p v-if="cameraError" class="text-caption text-white/70">{{ cameraError }}</p>
          <div v-if="cameraState === 'denied'" class="mt-1 flex flex-col gap-2 sm:flex-row">
            <AppButton
              variant="secondary"
              data-testid="retry-camera-btn"
              @click="retryCamera"
            >
              เปิดกล้องอีกครั้ง
            </AppButton>
            <AppButton variant="light" @click="enterCodeMode">กรอกรหัสแทน</AppButton>
          </div>
        </div>
      </template>

      <!-- ──────────── โหมดกรอกรหัส (หน้าเต็ม — ไม่ใช่ modal, skills #16) ──────────── -->
      <div v-else class="flex h-full flex-col bg-canvas">
        <header class="pt-safe flex shrink-0 items-center gap-1 border-b border-line bg-surface px-2">
          <IconButton
            icon="bi-arrow-left"
            label="กลับไปสแกน"
            data-testid="code-mode-back"
            @click="enterScanMode"
          />
          <h1 class="min-w-0 flex-1 truncate text-center text-[15px] font-bold text-ink-1">
            กรอกรหัสเช็คอิน
          </h1>
          <IconButton
            icon="bi-x-lg"
            label="ปิดหน้าสแกน"
            data-testid="close-checkin-btn-code"
            @click="close"
          />
        </header>

        <div class="min-h-0 flex-1 overflow-y-auto px-4 py-4">
          <div class="mx-auto w-full max-w-2xl">
            <!-- กล้องใช้ไม่ได้ → บอกตรง ๆ พร้อมทางกลับ (auto-switch มาที่นี่แล้ว) -->
            <div
              v-if="cameraBlocked"
              class="mb-4 rounded-card border border-warn/30 bg-warn-soft p-4"
              data-testid="camera-blocked"
            >
              <p class="text-sm font-bold text-warn">
                <i class="bi bi-camera-video-off mr-1"></i>ใช้กล้องไม่ได้
              </p>
              <p class="mt-0.5 text-caption text-ink-2">{{ cameraError }}</p>
              <AppButton
                variant="secondary"
                size="sm"
                class="mt-3"
                data-testid="retry-camera-btn-code"
                @click="retryCamera"
              >
                <template #icon><i class="bi bi-arrow-clockwise"></i></template>
                เปิดกล้องอีกครั้ง
              </AppButton>
            </div>

            <form
              class="rounded-card border border-line bg-surface p-4"
              @submit.prevent="submitManual"
            >
              <p class="text-sm font-bold text-ink-1">
                <i class="bi bi-keyboard mr-1 text-ink-2"></i>รหัสเช็คอิน
              </p>
              <p class="mt-0.5 text-caption text-ink-2">
                ใช้เมื่อกล้องใช้ไม่ได้ — ให้นักเรียนอ่านรหัสใต้คิวอาร์บนจอตัวเอง
              </p>
              <input
                ref="codeInputEl"
                v-model.trim="manualToken"
                type="text"
                inputmode="text"
                autocomplete="off"
                autocapitalize="off"
                spellcheck="false"
                placeholder="PIRI-EVT1:…"
                class="field mt-3 font-mono"
                data-testid="manual-token-input"
              />
              <AppButton
                type="submit"
                block
                class="mt-3"
                :loading="busy"
                :disabled="!manualToken"
                data-testid="manual-submit-btn"
              >
                <template #icon><i class="bi bi-check2"></i></template>
                เช็คอิน
              </AppButton>
            </form>

            <!-- ทางสำรองอีกชั้น: เช็คอินจากรายชื่อ (ไม่ต้องมีรหัสเลย) -->
            <p class="mt-4 text-caption text-ink-3">
              ถ้านักเรียนลืมมือถือ — เช็คอินจาก<b>รายชื่อผู้สมัคร</b>ได้ที่
              <RouterLink
                :to="{ name: 'event-registrations', params: { id: eventId } }"
                class="font-semibold text-brand hover:underline"
              >
                หน้ารายชื่อผู้สมัคร
              </RouterLink>
            </p>
          </div>
        </div>
      </div>
    </div>

    <!--
      ════════════════ แถบผลลัพธ์ — จองที่ถาวร ════════════════

      🔴 **ห้ามเปลี่ยนเป็น `AppSheet`/`Swal`** — ดูเหตุผล 3 ข้อในคอมเมนต์หัวไฟล์
         (คิว · กล้องกระตุก · "พร้อมสแกน" คือสถานะ ไม่ใช่ที่ว่าง)

      📐 **ความสูงคงที่** ⇒ กล้องไม่ยืด/หด ⇒ กรอบเล็งอยู่ที่เดิมทุกครั้ง
         ⇒ สภาไม่ต้องกวาดสายหาและไม่ต้องเล็งใหม่
    -->
    <div
      class="flex min-h-[6.5rem] shrink-0 flex-col justify-center border-t border-line px-4 py-3"
      :class="bandTone"
    >
      <div class="mx-auto flex w-full max-w-2xl items-center gap-3">
        <!-- 1) กำลังตรวจ -->
        <template v-if="busy">
          <i class="bi bi-arrow-repeat animate-spin shrink-0 text-2xl text-brand"></i>
          <p class="text-[15px] font-bold text-ink-1" data-testid="checkin-busy">กำลังตรวจ…</p>
        </template>

        <!-- 2) ยังไม่มีผล — สถานะ "พร้อมสแกน" -->
        <template v-else-if="!result">
          <i class="bi bi-qr-code-scan shrink-0 text-2xl text-ink-3"></i>
          <div class="min-w-0" data-testid="checkin-ready">
            <p class="text-[15px] font-bold text-ink-1">พร้อมสแกน</p>
            <p class="text-caption text-ink-2">
              ยื่นบัตรเช็คอินให้อยู่ในกรอบ — ชื่อจะขึ้นเองเมื่ออ่านได้
            </p>
          </div>
        </template>

        <!-- 3) สำเร็จ (เขียว) / ซ้ำ (เหลือง) -->
        <template v-else-if="result.kind !== 'error'">
          <i
            class="bi shrink-0 text-3xl"
            :class="
              result.kind === 'ok'
                ? 'bi-check-circle-fill text-ok'
                : 'bi-info-circle-fill text-warn'
            "
          ></i>
          <div class="min-w-0 flex-1" data-testid="checkin-banner">
            <p
              class="text-caption font-bold"
              :class="result.kind === 'ok' ? 'text-ok' : 'text-warn'"
            >
              {{ result.title }}<span v-if="result.kind === 'again'"> · ไม่ได้นับซ้ำ</span>
            </p>
            <!-- ⭐ ชื่อ = ตัวใหญ่สุดในหน้า เพราะสภาต้องอ่านแล้วเทียบกับหน้าคนตรงหน้า -->
            <p
              class="truncate text-2xl font-bold text-ink-1"
              data-testid="banner-name"
            >
              {{ result.name }}
            </p>
            <p v-if="result.checkedInAt" class="text-caption text-ink-2">
              เมื่อ {{ fmtTime(result.checkedInAt) }} น.
            </p>
          </div>
          <AppButton
            variant="secondary"
            size="sm"
            class="shrink-0"
            data-testid="next-person-btn"
            @click="clearResult"
          >
            คนถัดไป
          </AppButton>
        </template>

        <!-- 4) ไม่สำเร็จ / ไม่พบรหัส (แดง) -->
        <template v-else>
          <i class="bi bi-x-octagon-fill shrink-0 text-3xl text-danger"></i>
          <div class="min-w-0 flex-1" data-testid="checkin-error">
            <p class="text-caption font-bold text-danger">{{ result.title }}</p>
            <p class="text-[15px] font-semibold text-ink-1">{{ result.detail }}</p>
          </div>
          <AppButton
            variant="secondary"
            size="sm"
            class="shrink-0"
            data-testid="next-person-btn"
            @click="clearResult"
          >
            ลองใหม่
          </AppButton>
        </template>
      </div>
    </div>

    <!-- ════════════════ ⋯ ตัวเลือกเพิ่มเติม ════════════════ -->
    <!-- เป็น surface สำหรับ "เลือก" เท่านั้น ไม่มีฟอร์ม (skills #16) -->
    <AppSheet
      v-model="actionsOpen"
      title="ตัวเลือกเพิ่มเติม"
      description="เช็คอินได้แม้กล้องใช้ไม่ได้"
    >
      <button type="button" class="checkin-action" data-testid="action-code" @click="openCodeMode">
        <i class="bi bi-keyboard text-xl text-ink-2"></i>
        <span class="flex-1 text-left">กรอกรหัสเช็คอิน</span>
        <i class="bi bi-chevron-right text-ink-3"></i>
      </button>

      <RouterLink
        :to="{ name: 'event-registrations', params: { id: eventId } }"
        class="checkin-action"
        data-testid="action-roster"
      >
        <i class="bi bi-people text-xl text-ink-2"></i>
        <span class="flex-1 text-left">เช็คอินจากรายชื่อผู้สมัคร</span>
        <i class="bi bi-chevron-right text-ink-3"></i>
      </RouterLink>

      <button
        v-if="!isLive"
        type="button"
        class="checkin-action"
        data-testid="action-camera-retry"
        @click="openCameraRetry"
      >
        <i class="bi bi-arrow-clockwise text-xl text-ink-2"></i>
        <span class="flex-1 text-left">เปิดกล้องอีกครั้ง</span>
        <i class="bi bi-chevron-right text-ink-3"></i>
      </button>
    </AppSheet>
  </div>
</template>

<style scoped>
/* แถวใน `⋯` — สูง 48dp (เกินเกณฑ์ 44dp) และกินเต็มความกว้างการ์ด */
.checkin-action {
  @apply flex w-full items-center gap-3 rounded-control px-3 py-3 text-[15px] font-semibold text-ink-1 transition-colors hover:bg-canvas;
}
</style>
