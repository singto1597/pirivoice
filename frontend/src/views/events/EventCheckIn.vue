<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { checkInRegistration, getPublicEvent } from '@/services/event'
import { readQrFrame } from '@/qrReader'
import {
  SCAN_INTERVAL_MS,
  checkInBanner,
  createScanGate,
  type CheckInBanner,
} from '@/qrScanner'
import type { PublicEvent } from '@/types/event'
import type { ApiError } from '@/services/api'
import { goUnavailable } from '@/router/unavailable'

/**
 * 📷 หน้าสแกนเช็คอินหน้างาน (D2) — **ของสภา** (ต้องมี MANAGE_EVENTS)
 *
 * 🎯 ลำดับความสำคัญของการออกแบบหน้า�นี้ ต่างจากหน้าอื่นทั้งระบบ:
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
 */

const route = useRoute()
const router = useRouter()
const eventId = Number(route.params.id)

const event = ref<PublicEvent | null>(null)
const eventError = ref('')

/** ผลของ **การเช็คอินครั้งล่าสุด** — ค้างไว้บนจอให้สภาอ่านจนกว่าจะสแกนคนถัดไป */
const banner = ref<CheckInBanner | null>(null)
/** ข้อความ error ของครั้งล่าสุด (คนละช่องกับ banner เพราะไม่ได้แปลว่ามีคนถูกเช็คอิน) */
const errorText = ref('')
const busy = ref(false)

/** กล้อง — `unsupported` = เบราว์เซอร์ไม่มี getUserMedia · `denied` = ผู้ใช้ไม่ให้สิทธิ์ */
const videoEl = ref<HTMLVideoElement | null>(null)
const cameraState = ref<'idle' | 'starting' | 'live' | 'denied' | 'unsupported'>('idle')
const cameraError = ref('')

const manualToken = ref('')

/** ของที่ไม่ต้อง reactive — เก็บเป็น ref เพื่อให้ cleanup เข้าถึงได้ แต่ไม่ต้อง re-render */
const gate = createScanGate()
let stream: MediaStream | null = null
let rafId = 0
let canvas: HTMLCanvasElement | null = null
let lastScanAt = 0
/** กัน callback ของ rAF ที่ค้างอยู่ในคิวไม่ให้ทำงานหลัง unmount */
let alive = false

const isLive = computed(() => cameraState.value === 'live')

/** ข้อความที่สภาต้องอ่าน — `HH:MM` เพราะเช็คอินเกิดวันงานเสมอ (วันที่ซ้ำกับหัวเรื่อง) */
function fmtTime(iso: string): string {
  return new Date(iso).toLocaleTimeString('th-TH', {
    timeZone: 'Asia/Bangkok',
    hour: '2-digit',
    minute: '2-digit',
  })
}

onMounted(async () => {
  alive = true
  void loadEvent()
  await startCamera()
})

/**
 * ⚠️ **ต้องหยุดกล้องตอนออกจากหน้าเสมอ** — ไฟกล้องค้างคือสัญญาณว่าเว็บยังแอบใช้กล้องอยู่
 *    (ผู้ใช้เห็นแล้วจะปิดทั้งแท็บ) และบนมือถือมันกินแบตต่อเนื่อง
 */
onBeforeUnmount(() => {
  alive = false
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

async function startCamera() {
  // กันดับเบิลคลิกที่ปุ่ม "เปิดกล้อง": สถานะเป็น ref (เปลี่ยนทันที) แต่ DOM อัปเดตช้ากว่า
  // ⇒ คลิกรัว ๆ ในจังหวะเดียวกันจะเรียก getUserMedia ซ้อน แล้ว `stream` ตัวเก่าจะค้างไม่ถูก stop
  // (ไฟกล้องติดค้างโดยไม่มีใครอ้างถึง) — ประตูนี้ปิดช่องนั้น
  if (cameraState.value === 'starting') return

  if (!navigator.mediaDevices?.getUserMedia) {
    // เกิดจริงบน http:// (ไม่ใช่ localhost) — `getUserMedia` ต้องมี secure context
    cameraState.value = 'unsupported'
    cameraError.value = 'เบราว์เซอร์นี้ไม่รองรับกล้อง หรือหน้านี้ไม่ได้เปิดผ่าน https'
    return
  }

  cameraState.value = 'starting'
  cameraError.value = ''
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      // `ideal` ไม่ใช่ `exact` — เครื่องที่ไม่มีกล้องหลังต้องยังใช้กล้องหน้าได้
      // (สแกนบัตรด้วยกล้องหน้าก็ได้ แค่ต้องยื่นบัตรให้ห่างหน่อย) ดีกว่าไม่ได้กล้องเลย
      video: { facingMode: { ideal: 'environment' } },
      audio: false,
    })
    if (!alive) {
      // ผู้ใช้ออกจากหน้าไประหว่างที่เบราว์เซอร์กำลังถามสิทธิ์ ⇒ ปิดทันทีไม่งั้นกล้องค้าง
      stream.getTracks().forEach((t) => t.stop())
      stream = null
      return
    }
    if (videoEl.value) {
      videoEl.value.srcObject = stream
      // `play()` อาจ reject ถ้าผู้ใช้ยังไม่ได้ interact — ไม่ใช่เรื่องคอขวด เพราะ
      // `autoplay muted playsinline` ที่ element จะเล่นให้เองอยู่แล้ว
      await videoEl.value.play().catch(() => undefined)
    }
    cameraState.value = 'live'
    rafId = requestAnimationFrame(tick)
  } catch (e) {
    cameraState.value = 'denied'
    cameraError.value =
      e instanceof Error && e.name === 'NotAllowedError'
        ? 'ยังไม่ได้อนุญาตให้ใช้กล้อง — อนุญาตแล้วกด "เปิดกล้อง" อีกครั้ง หรือใช้ช่องกรอกรหัสด้านล่าง'
        : 'เปิดกล้องไม่สำเร็จ — ใช้ช่องกรอกรหัสด้านล่างแทนได้'
  }
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
function grabFrame(video: HTMLVideoElement): { data: Uint8ClampedArray; width: number; height: number } | null {
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

/**
 * ส่งโทเคนไปเช็คอิน — **ประตูกันซ้ำอยู่ที่นี่ที่เดียว** ใช้ร่วมกันทั้งกล้องและช่องกรอก
 *
 * @param from `'frame'` = อ่านได้จากกล้อง (มี cooldown) · `'manual'` = สภาพิมพ์เอง (ไม่มี)
 */
async function submit(token: string, from: 'frame' | 'manual') {
  const now = performance.now()
  const allowed =
    from === 'frame' ? gate.beginFrame(token, now) : gate.beginManual(token, now)
  // เฟรมที่ถูกทิ้งไม่ต้องบอกอะไร (เป็นเรื่องปกติของวิดีโอ) — แต่การพิมพ์ที่ถูกทิ้งต้องบอก
  if (!allowed) {
    if (from === 'manual') errorText.value = 'กำลังดำเนินการอยู่ — รอสักครู่แล้วลองใหม่'
    return
  }

  busy.value = true
  errorText.value = ''
  try {
    const res = await checkInRegistration(eventId, { token })
    banner.value = checkInBanner(res)
    if (from === 'manual') manualToken.value = ''
  } catch (e) {
    // ⚠️ ห้ามล้าง `banner` ทิ้ง — ผลของคนก่อนหน้ายังเป็นข้อมูลที่สภาอาจยังไม่ทันอ่าน
    //    error ของคนปัจจุบันแสดงแยกกันคนละแถบ
    errorText.value = e instanceof Error ? e.message : 'เช็คอินไม่สำเร็จ'
  } finally {
    busy.value = false
    gate.finish()
  }
}

/** ปุ่ม "สแกนต่อ" — ล้างผลของคนก่อนแล้วเปิดประตูให้บัตรใบเดิมผ่านได้ทันที */
function resetBanner() {
  banner.value = null
  errorText.value = ''
  gate.reset()
}
</script>

<template>
  <div class="max-w-2xl mx-auto">
    <!-- หัวเรื่อง -->
    <div class="mb-5">
      <RouterLink
        :to="`/app/events/${eventId}`"
        class="text-sm text-stone-500 hover:text-stone-700"
      >
        <i class="bi bi-arrow-left mr-1"></i>กลับไปหน้ากิจกรรม
      </RouterLink>
      <p class="mt-2 text-[11px] font-bold uppercase tracking-widest text-brand">
        <i class="bi bi-qr-code-scan mr-1"></i> Check-in
      </p>
      <h1 class="text-xl sm:text-2xl font-bold text-stone-900 leading-tight">
        สแกนเช็คอิน
      </h1>
      <p v-if="event" class="text-sm text-stone-500 mt-1">{{ event.title }}</p>
      <p v-else-if="eventError" class="text-sm text-amber-700 mt-1">
        <i class="bi bi-exclamation-triangle mr-1"></i>{{ eventError }}
      </p>
    </div>

    <!-- ════════ แถบผลลัพธ์ ════════ -->
    <!-- อยู่บนสุดของเนื้อหา เพื่อให้ต่ำแหน่งเดิมทุกครั้ง ⇒ สภาไม่ต้องกวาดสายหา -->
    <div
      v-if="banner"
      class="mb-4 rounded-2xl px-5 py-4 border-2"
      :class="banner.tone === 'ok'
        ? 'bg-emerald-50 border-emerald-300'
        : 'bg-amber-50 border-amber-300'"
      data-testid="checkin-banner"
    >
      <p
        class="text-xs font-bold"
        :class="banner.tone === 'ok' ? 'text-emerald-700' : 'text-amber-800'"
      >
        <i :class="banner.tone === 'ok' ? 'bi bi-check-circle-fill' : 'bi bi-info-circle-fill'" class="mr-1"></i>
        {{ banner.title }}
      </p>
      <!-- ⭐ ชื่อ = ตัวใหญ่สุดในหน้า เพราะสภาต้องอ่านแล้วเทียบกับหน้าคนตรงหน้า -->
      <p class="mt-1 text-2xl sm:text-3xl font-bold text-stone-900 break-words" data-testid="banner-name">
        {{ banner.name }}
      </p>
      <p v-if="banner.checkedInAt" class="mt-0.5 text-sm text-stone-600">
        เมื่อ {{ fmtTime(banner.checkedInAt) }} น.
        <span v-if="banner.tone === 'again'" class="text-amber-700">· เวลาเดิม ไม่ได้นับซ้ำ</span>
      </p>
      <button
        type="button"
        class="mt-3 w-full py-2 bg-white ring-1 ring-stone-300 text-stone-700 rounded-xl text-sm font-bold hover:bg-stone-50 transition-colors"
        data-testid="next-person-btn"
        @click="resetBanner"
      >
        <i class="bi bi-arrow-repeat mr-1"></i>คนถัดไป
      </button>
    </div>

    <!-- error ของครั้งล่าสุด — คนละแถบกับผลสำเร็จ เพราะ "ไม่มีใครถูกเช็คอิน" -->
    <div
      v-if="errorText"
      class="mb-4 rounded-2xl bg-red-50 border border-red-200 px-4 py-3"
      data-testid="checkin-error"
    >
      <p class="text-sm font-bold text-brand">
        <i class="bi bi-x-octagon-fill mr-1"></i>เช็คอินไม่สำเร็จ
      </p>
      <p class="mt-0.5 text-sm text-red-600">{{ errorText }}</p>
    </div>

    <!-- ════════ กล้อง ════════ -->
    <div class="page-card p-4">
      <div class="relative rounded-xl overflow-hidden bg-stone-900 aspect-[4/3]">
        <!-- `muted` + `playsinline` จำเป็นสำหรับ iOS: ถ้าไม่มี วิดีโอจะเด้งเป็น fullscreen
             และ autoplay จะถูกบล็อก -->
        <video
          ref="videoEl"
          class="w-full h-full object-cover"
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
          <div class="w-2/3 aspect-square border-2 border-white/70 rounded-2xl"></div>
        </div>

        <div
          v-if="!isLive"
          class="absolute inset-0 flex flex-col items-center justify-center gap-2 px-6 text-center"
        >
          <i
            class="bi text-3xl text-stone-400"
            :class="cameraState === 'starting' ? 'bi-arrow-repeat animate-spin' : 'bi-camera-video-off'"
          ></i>
          <p class="text-sm text-stone-300">
            {{ cameraState === 'starting' ? 'กำลังเปิดกล้อง...' : 'กล้องยังไม่ทำงาน' }}
          </p>
          <p v-if="cameraError" class="text-[12px] text-stone-400">{{ cameraError }}</p>
          <button
            v-if="cameraState === 'denied'"
            type="button"
            class="mt-1 px-4 py-2 bg-white text-stone-800 rounded-xl text-sm font-bold hover:bg-stone-100"
            data-testid="retry-camera-btn"
            @click="startCamera"
          >
            <i class="bi bi-arrow-clockwise mr-1"></i>เปิดกล้อง
          </button>
        </div>
      </div>

      <p class="mt-2.5 text-[12px] text-stone-400">
        <i class="bi bi-info-circle mr-1"></i>ยื่นบัตรเช็คอินของนักเรียนให้อยู่ในกรอบ —
        ชื่อจะขึ้นเองเมื่ออ่านได้
      </p>
    </div>

    <!-- ════════ ทางสำรอง: กรอกรหัส ════════ -->
    <!-- ไม่ซ่อนในเมนูพับ เพราะวันที่กล้องพังคือวันที่ต้องใช้ทางนี้ — และต้องหาเจอทันที -->
    <div class="page-card p-4 mt-4">
      <p class="text-sm font-bold text-stone-800">
        <i class="bi bi-keyboard mr-1 text-stone-500"></i>กรอกรหัสเช็คอิน
      </p>
      <p class="mt-0.5 text-[12px] text-stone-500">
        ใช้เมื่อกล้องใช้ไม่ได้ — นักเรียนอ่านรหัสใต้คิวอาร์บนจอตัวเองให้ฟัง
      </p>
      <form class="mt-2.5 flex flex-col sm:flex-row gap-2" @submit.prevent="submit(manualToken, 'manual')">
        <input
          v-model.trim="manualToken"
          type="text"
          inputmode="text"
          autocomplete="off"
          autocapitalize="off"
          spellcheck="false"
          placeholder="PIRI-EVT1:..."
          class="flex-1 px-3.5 py-2.5 rounded-xl border border-stone-300 font-mono text-sm focus:outline-none focus:ring-2 focus:ring-brand/30 focus:border-brand"
          data-testid="manual-token-input"
        />
        <button
          type="submit"
          :disabled="busy || !manualToken"
          class="px-5 py-2.5 bg-brand text-white rounded-xl font-bold hover:bg-brand-strong disabled:opacity-50 transition-colors"
          data-testid="manual-submit-btn"
        >
          <i :class="busy ? 'bi bi-arrow-repeat animate-spin' : 'bi bi-check2'" class="mr-1"></i>
          เช็คอิน
        </button>
      </form>
    </div>

    <!-- ทางสำรองอีกชั้น: เช็คอินจากรายชื่อ (ไม่ต้องมีรหัสเลย) -->
    <p class="mt-4 text-[12px] text-stone-400 text-center">
      ถ้านักเรียนลืมมือถือ — เช็คอินจาก<b>รายชื่อผู้สมัคร</b>ได้ที่
      <RouterLink to="/app/events/manage" class="text-brand hover:underline">หน้าจัดการกิจกรรม</RouterLink>
    </p>
  </div>
</template>
