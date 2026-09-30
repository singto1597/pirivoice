<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import Swal from 'sweetalert2'
import {
  cancelMyRegistration,
  getMyRegistration,
  getPublicEvent,
  registerForEvent,
} from '@/services/event'
import { checkInCardState, seatsLabel, type MyRegistration, type PublicEvent } from '@/types/event'
import type { ApiError } from '@/services/api'
import { goUnavailable } from '@/router/unavailable'
import QrCode from '@/components/QrCode.vue'

/**
 * 📅 รายละเอียดกิจกรรม (ฝั่งนักเรียน) + ลงทะเบียน / ถอน
 *
 * ⚠️ **ห้ามเทียบเวลาที่นี่เพื่อตัดสินว่าเปิดรับสมัครหรือยัง** — `is_registration_open`
 *    คำนวณใน SQL ฝั่ง server เพราะนาฬิกาเครื่องผู้ใช้อาจเพี้ยนคนละโซน และกติกา "ปิดรับเมื่อไหร่"
 *    เป็นกติกาของ *ระบบ* ไม่ใช่การแสดงผล ⇒ ใช้ค่าที่ server ส่งมาเท่านั้น
 *
 * ⚠️ **สถานะ "ของฉัน" มาจาก `getMyRegistration` ไม่ใช่ `event.my_registration_status`**
 *    ทั้งสองอ่านจากแถวเดียวกัน แต่ตัวหลัง **ไม่มี `queue_position`** ⇒ ถ้าใช้ทั้งคู่จะกลายเป็น
 *    สองแหล่งความจริงที่ไม่มีอะไรรับรองว่าตรงกัน · ตัวที่ถือข้อมูลครบกว่าคือตัวที่ถูกใช้
 *
 * ⚠️ **ลงทะเบียนตอนที่นั่งเต็มไม่ใช่ error** — backend จะคืน `status: 'waitlisted'` มาให้
 *    ⇒ UI ต้องดู `status` ที่คืนมา ไม่ใช่ดูแค่ว่าคำขอสำเร็จ (ไม่งั้นผู้ใช้จะเข้าใจว่าตัวเองได้ที่นั่ง)
 */
const route = useRoute()
const router = useRouter()

const event = ref<PublicEvent | null>(null)
const mine = ref<MyRegistration | null>(null)
const isLoading = ref(true)
const loadError = ref('')
/** กำลังยิงคำขอลงทะเบียน/ถอนอยู่ — กันดับเบิลแท็ป (backend กันซ้ำให้อีกชั้นผ่าน 201/200) */
const acting = ref(false)

const isRegistered = computed(() => mine.value?.registered === true)
const isFull = computed(() => event.value?.seats_remaining === 0)
const seatsText = computed(() => seatsLabel(event.value?.seats_remaining ?? null) ?? 'ไม่จำกัดจำนวน')

/** ลงทะเบียนได้เฉพาะเมื่อ: server บอกว่าเปิดรับ · ยังไม่ถูกยกเลิก · และเรายังไม่ได้ที่นั่ง/คิว */
const canRegister = computed(
  () =>
    !!event.value &&
    !isRegistered.value &&
    event.value.status !== 'cancelled' &&
    event.value.is_registration_open,
)

/**
 * สถานะบัตรเช็คอิน — กติกาทั้งหมดอยู่ใน `checkInCardState()` (ทดสอบแยกได้ที่นั่น)
 * ตรงนี้มีหน้าที่แค่หยิบ object ที่โหลดมาแล้วยัดเข้าไป
 */
const cardState = computed(() => checkInCardState(mine.value, event.value))

/**
 * โทเคนที่จะวาดเป็นคิวอาร์ — มีค่าเฉพาะตอน `cardState === 'qr'`
 * ⚠️ ไม่ใช้ `mine?.check_in_token` ตรง ๆ ในเทมเพลต เพราะ TypeScript ที่นั่นไม่รู้จัก
 *    ความเชื่อมโยงระหว่าง `cardState` กับตัวโทเคน ⇒ ต้องผ่านที่เดียวที่รู้
 */
const qrToken = computed(() =>
  cardState.value === 'qr' ? (mine.value?.check_in_token ?? null) : null,
)

/**
 * @param silent `true` = ไม่สลับเป็น skeleton เต็มหน้า (ใช้ตอนโหลดซ้ำหลังกดปุ่ม)
 *   — การกระพริบทั้งหน้าเป็น skeleton บนหน้าที่ผู้ใช้กำลังอ่านอยู่ ดูเหมือนแอพโหลดใหม่
 *   ทั้งที่เราแค่ต้องการตัวเลขที่นั่งล่าสุด
 */
async function load(silent = false) {
  if (!silent) isLoading.value = true
  loadError.value = ''
  try {
    const id = Number(route.params.id)
    // ยิงขนานกัน — สองคำขอไม่ขึ้นต่อกัน และการรอทีละตัวทำให้หน้านานเป็นสองเท่า
    const [ev, my] = await Promise.all([getPublicEvent(id), getMyRegistration(id)])
    event.value = ev
    mine.value = my
  } catch (e) {
    // 🚪 404 ของกิจกรรมมีสองทาง: **ฉบับร่าง** (สภายังไม่เผยแพร่) และ **ถูกลบ**
    //    (กิจกรรมที่ "ยกเลิก" ยังเปิดดูได้ — ไม่ใช่ 404) ⇒ ลิงก์ที่ผู้ใช้กดมา (จาก push/QR)
    //    ใช้ต่อไม่ได้ ⇒ พากลับไปที่ที่ไปต่อได้พร้อมบอกสาเหตุ ดีกว่าค้างกับ error ที่กดลองใหม่ก็ได้ 404
    if (e instanceof Error && (e as ApiError).status === 404) {
      await goUnavailable(router, 'event')
      return
    }
    loadError.value = e instanceof Error ? e.message : 'โหลดกิจกรรมไม่สำเร็จ'
  } finally {
    isLoading.value = false
  }
}

onMounted(() => load())

function errText(e: unknown): string {
  return e instanceof Error ? e.message : 'เกิดข้อผิดพลาดที่ไม่รู้จัก'
}

async function handleRegister() {
  if (!event.value || acting.value) return
  acting.value = true
  try {
    const res = await registerForEvent(event.value.id)
    await load(true)
    if (res.status === 'waitlisted') {
      // ที่นั่งเต็ม → ได้คิวสำรอง ⇒ ต้องบอกให้ชัดว่า "ยังไม่ได้ที่นั่ง"
      Swal.fire({
        icon: 'info',
        title: 'ที่นั่งเต็ม — เข้าคิวสำรองแล้ว',
        html:
          `คุณเป็น<b>คิวที่ ${res.queue_position ?? '-'}</b> ของกิจกรรมนี้<br>` +
          '<span class="text-sm text-stone-500">ถ้ามีคนถอน ที่นั่งจะเลื่อนให้คนแรกในคิวอัตโนมัติ</span>',
        confirmButtonText: 'เข้าใจแล้ว',
        confirmButtonColor: '#B91C1C',
      })
    } else {
      Swal.fire({ icon: 'success', title: 'ลงทะเบียนสำเร็จ', timer: 1200, showConfirmButton: false })
    }
  } catch (e) {
    Swal.fire({ icon: 'error', title: 'ลงทะเบียนไม่สำเร็จ', text: errText(e) })
  } finally {
    acting.value = false
  }
}

async function handleCancel() {
  if (!event.value || acting.value) return
  // ผู้ที่ถือ "ที่นั่งจริง" กับการเป็น "คิวสำรอง" เสียอะไรไม่เหมือนกัน ⇒ ถามให้ตรงกรณี
  const hadSeat = mine.value?.status === 'registered' || mine.value?.status === 'checked_in'
  const res = await Swal.fire({
    title: 'ถอนการลงทะเบียน?',
    text: hadSeat
      ? 'ที่นั่งของคุณจะถูกเลื่อนให้คนแรกในคิวสำรองทันที'
      : 'คุณจะออกจากคิวสำรองของกิจกรรมนี้',
    icon: 'warning',
    showCancelButton: true,
    confirmButtonText: 'ถอนการลงทะเบียน',
    confirmButtonColor: '#b91c1c',
    cancelButtonText: 'ไม่ถอน',
  })
  if (!res.isConfirmed) return

  acting.value = true
  try {
    await cancelMyRegistration(event.value.id)
    await load(true)
    Swal.fire({ icon: 'success', title: 'ถอนแล้ว', timer: 1000, showConfirmButton: false })
  } catch (e) {
    Swal.fire({ icon: 'error', title: 'ถอนไม่สำเร็จ', text: errText(e) })
  } finally {
    acting.value = false
  }
}

/**
 * กิจกรรมมี **วันและเวลา** (timestamptz) ต่างจากบอร์ด/ประกาศที่เป็นวันที่ล้วน
 * ⇒ ใช้ `toLocaleString` กับ ISO ที่มี tz ได้ตรง ๆ (ไม่ใช่ date-only ที่ห้ามใช้ `new Date`)
 */
function fmtDateTime(iso: string): string {
  return new Date(iso).toLocaleString('th-TH', {
    timeZone: 'Asia/Bangkok',
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

/**
 * เวลาสั้น ๆ (`HH:MM`) — ใช้กับตรา "เช็คอินแล้ว" ซึ่งเกิด **วันงานเสมอ**
 * ⇒ วันที่ซ้ำกับ `event_date` ที่โชว์อยู่ข้างบนอยู่แล้ว ใส่วันที่ลงไปมีแต่ทำให้อ่านยาก
 */
function fmtTime(iso: string): string {
  return new Date(iso).toLocaleTimeString('th-TH', {
    timeZone: 'Asia/Bangkok',
    hour: '2-digit',
    minute: '2-digit',
  })
}
</script>

<template>
  <!-- โหลด: skeleton -->
  <div v-if="isLoading" class="max-w-3xl mx-auto space-y-5">
    <div class="page-card p-5 space-y-3">
      <div class="h-5 w-24 bg-stone-100 animate-pulse rounded-md"></div>
      <div class="h-6 w-3/4 bg-stone-100 animate-pulse rounded"></div>
      <div class="h-4 w-1/2 bg-stone-100 animate-pulse rounded"></div>
      <div class="h-20 w-full bg-stone-100 animate-pulse rounded"></div>
    </div>
    <div class="page-card p-5 space-y-3">
      <div class="h-11 w-full bg-stone-100 animate-pulse rounded-xl"></div>
    </div>
  </div>

  <!-- ผิดพลาด -->
  <div
    v-else-if="loadError"
    class="max-w-3xl mx-auto border-2 border-dashed border-stone-200 rounded-2xl py-20 px-6 text-center"
  >
    <div class="text-4xl text-stone-300 mb-3"><i class="bi bi-calendar-x"></i></div>
    <p class="text-stone-600 font-medium">{{ loadError }}</p>
    <div class="mt-5 flex flex-wrap items-center justify-center gap-3">
      <button
        type="button"
        @click="load()"
        class="px-5 py-2.5 bg-[#B91C1C] text-white rounded-xl text-sm font-bold hover:bg-[#991B1B]"
      >
        <i class="bi bi-arrow-clockwise mr-1"></i> ลองอีกครั้ง
      </button>
      <button
        type="button"
        @click="router.push({ name: 'events' })"
        class="px-5 py-2.5 bg-stone-100 text-stone-700 rounded-xl text-sm font-medium hover:bg-stone-200"
      >
        กลับไปหน้ากิจกรรม
      </button>
    </div>
  </div>

  <div v-else-if="event" class="max-w-3xl mx-auto space-y-5">
    <!-- ปุ่มกลับ -->
    <button
      type="button"
      @click="router.push({ name: 'events' })"
      class="flex items-center gap-1 text-sm text-stone-500 hover:text-[#B91C1C] font-medium"
    >
      <i class="bi bi-arrow-left"></i> กิจกรรมทั้งหมด
    </button>

    <!-- ปก -->
    <img
      v-if="event.cover_image_url"
      :src="event.cover_image_url"
      :alt="event.title"
      class="w-full max-h-64 object-cover rounded-2xl border border-stone-200 bg-stone-100"
      loading="lazy"
    />

    <!-- หัวกิจกรรม -->
    <div class="page-card p-5">
      <div class="flex flex-wrap items-center gap-2 mb-2">
        <span
          v-if="event.status === 'cancelled'"
          class="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-red-50 text-red-700 text-[11px] font-semibold"
        >
          <i class="bi bi-x-octagon"></i> ยกเลิกแล้ว
        </span>
        <span v-else-if="event.is_registration_open" class="text-[11px] font-semibold text-emerald-600">
          <i class="bi bi-door-open mr-1"></i>เปิดรับสมัคร
        </span>
        <span v-else class="text-[11px] text-stone-400">
          <i class="bi bi-lock mr-1"></i>ปิดรับสมัครแล้ว
        </span>
        <span v-if="isFull && event.status !== 'cancelled'" class="text-[11px] font-semibold text-red-600">
          · ที่นั่งเต็ม
        </span>
      </div>

      <h1 class="text-xl sm:text-2xl font-bold text-stone-900 leading-snug break-words">
        {{ event.title }}
      </h1>

      <div class="mt-3 space-y-1.5 text-sm text-stone-600">
        <div>
          <i class="bi bi-clock mr-1.5 text-stone-400"></i>{{ fmtDateTime(event.event_date) }}
        </div>
        <div v-if="event.location">
          <i class="bi bi-geo-alt mr-1.5 text-stone-400"></i>{{ event.location }}
        </div>
        <div v-if="event.registration_deadline">
          <i class="bi bi-hourglass-split mr-1.5 text-stone-400"></i>
          ปิดรับสมัคร {{ fmtDateTime(event.registration_deadline) }}
        </div>
      </div>

      <p v-if="event.description" class="mt-4 text-stone-700 whitespace-pre-wrap break-words">
        {{ event.description }}
      </p>
    </div>

    <!-- จำนวนที่นั่ง -->
    <div class="page-card p-5">
      <h2 class="text-base font-bold text-stone-900 mb-3">
        <i class="bi bi-people mr-1 text-stone-500"></i> การลงทะเบียน
      </h2>
      <div class="grid grid-cols-2 sm:grid-cols-3 gap-3">
        <div class="rounded-xl bg-stone-50 px-3.5 py-3">
          <p class="text-[11px] font-semibold text-stone-500">ที่นั่ง</p>
          <p class="mt-0.5 text-sm font-bold tabular-nums" :class="isFull ? 'text-red-600' : 'text-stone-800'">
            {{ seatsText }}
          </p>
        </div>
        <div class="rounded-xl bg-stone-50 px-3.5 py-3">
          <p class="text-[11px] font-semibold text-stone-500">ลงทะเบียนแล้ว</p>
          <p class="mt-0.5 text-sm font-bold text-stone-800 tabular-nums">
            {{ event.registered_count.toLocaleString('en-US') }} คน
          </p>
        </div>
        <div class="rounded-xl bg-stone-50 px-3.5 py-3">
          <p class="text-[11px] font-semibold text-stone-500">คิวสำรอง</p>
          <p class="mt-0.5 text-sm font-bold text-stone-800 tabular-nums">
            {{ event.waitlisted_count.toLocaleString('en-US') }} คน
          </p>
        </div>
      </div>
      <p
        v-if="event.capacity !== null"
        class="mt-2.5 text-[11px] text-stone-400"
      >
        <i class="bi bi-info-circle mr-1"></i>รับทั้งหมด {{ event.capacity.toLocaleString('en-US') }} ที่นั่ง
        · ที่นั่งเต็มแล้วระบบจะเข้าคิวสำรองให้อัตโนมัติ
      </p>
    </div>

    <!-- ════════ สถานะของฉัน + ปุ่ม ════════ -->
    <div class="page-card p-5">
      <!-- ยกเลิกกิจกรรม — บอกก่อนปุ่มอื่น เพื่อไม่ให้ผู้ใช้สงสัยว่าทำไมกดไม่ได้ -->
      <div
        v-if="event.status === 'cancelled'"
        class="mb-4 px-3.5 py-3 bg-red-50 border border-red-100 text-red-700 text-sm rounded-xl"
      >
        <i class="bi bi-x-octagon-fill mr-1"></i>
        กิจกรรมนี้ถูกยกเลิกแล้ว — การลงทะเบียนปิดโดยอัตโนมัติ
      </div>

      <!-- สถานะปัจจุบัน -->
      <div
        v-if="mine?.status === 'registered' || mine?.status === 'checked_in'"
        class="mb-4 px-3.5 py-3 bg-emerald-50 border border-emerald-200 text-emerald-700 text-sm rounded-xl"
      >
        <i class="bi bi-check-circle-fill mr-1"></i>
        {{ mine.status === 'checked_in' ? 'คุณเข้าร่วมกิจกรรมนี้แล้ว (เช็คอินแล้ว)' : 'คุณได้ที่นั่งของกิจกรรมนี้แล้ว' }}
      </div>
      <div
        v-else-if="mine?.status === 'waitlisted'"
        class="mb-4 px-3.5 py-3 bg-amber-50 border border-amber-200 text-amber-800 text-sm rounded-xl"
      >
        <i class="bi bi-hourglass-split mr-1"></i>
        คุณอยู่ใน<b>คิวสำรอง</b> — เป็นคิวที่
        <b class="tabular-nums">{{ mine.queue_position ?? '-' }}</b>
        <span class="block mt-0.5 text-[12px] text-amber-700">
          ที่นั่งเต็มชั่วคราว · ถ้ามีคนถอน ระบบจะเลื่อนที่นั่งให้คนแรกในคิวอัตโนมัติ
        </span>
      </div>

      <!-- ════════ บัตรเช็คอิน (D2) ════════ -->
      <!--
        QR = สิ่งที่นักเรียน "ถือ" ไปหน้างาน · ตราเขียว = ผ่านไปแล้ว
        ⇒ สองสภาพนี้แทนกัน ไม่ใช่ซ้อนกัน (สแกนซ้ำได้แต่ไม่มีประโยชน์ — คนเช็คอินแล้ว
        ต้องไม่เห็น QR อีก เพราะการแสกนซ้ำไม่ได้ให้อะไรและทำให้เข้าใจผิดว่ายังต้องสแกน)
      -->
      <div
        v-if="cardState !== 'none'"
        class="mb-4 rounded-2xl border border-stone-200 bg-stone-50 px-4 py-5 text-center"
        data-testid="checkin-card"
      >
        <template v-if="cardState === 'checked_in'">
          <p class="text-4xl leading-none">✅</p>
          <p class="mt-2 text-base font-bold text-emerald-700" data-testid="checked-in-stamp">
            เช็คอินแล้ว
          </p>
          <p v-if="mine?.checked_in_at" class="mt-0.5 text-sm text-stone-500">
            เมื่อ {{ fmtTime(mine.checked_in_at) }} น.
          </p>
        </template>

        <template v-else-if="qrToken">
          <p class="text-sm font-bold text-stone-800">บัตรเช็คอินของคุณ</p>
          <p class="mt-0.5 text-[12px] text-stone-500">แสดงคิวอาร์นี้ให้สภาสแกนที่หน้างาน</p>
          <div class="mt-3 flex justify-center">
            <QrCode :value="qrToken" :size="200" alt="คิวอาร์เช็คอินกิจกรรมนี้" />
          </div>
          <!--
            รหัสตัวอักษรใต้คิวอาร์ — ปลายทางของข้อความ "ใช้รหัสด้านล่างแทน" ใน `QrCode.vue`
            ⚠️ ไม่ใช่ความลับ (ไม่มีอะไรเสียหายถ้าคนอื่นเห็น — ตัวกันการปลอมคือลายเซ็น
               ไม่ใช่การปิดบังรหัส) ⇒ โชว์ตลอด ไม่ใช่ซ่อนรอให้ QR พังก่อน
          -->
          <p class="mt-3 text-[11px] text-stone-400">หรืออ่านรหัสนี้ให้สภาพิมพ์</p>
          <p
            class="mt-1 select-all break-all font-mono text-[11px] text-stone-600"
            data-testid="checkin-token"
          >
            {{ qrToken }}
          </p>
        </template>
      </div>

      <!-- ปุ่มหลัก -->
      <button
        v-if="canRegister"
        type="button"
        :disabled="acting"
        data-testid="register-btn"
        @click="handleRegister"
        class="w-full py-3 bg-[#B91C1C] text-white rounded-xl font-bold hover:bg-[#991B1B] disabled:opacity-50 transition-colors"
      >
        <i :class="acting ? 'bi bi-arrow-repeat animate-spin' : 'bi bi-check2-circle'" class="mr-1"></i>
        {{ acting ? 'กำลังดำเนินการ...' : isFull ? 'เข้าคิวสำรอง' : 'ลงทะเบียนเข้าร่วม' }}
      </button>

      <button
        v-else-if="isRegistered"
        type="button"
        :disabled="acting"
        data-testid="cancel-registration-btn"
        @click="handleCancel"
        class="w-full py-3 bg-white text-red-600 ring-1 ring-red-200 rounded-xl font-bold hover:bg-red-50 disabled:opacity-50 transition-colors"
      >
        <i :class="acting ? 'bi bi-arrow-repeat animate-spin' : 'bi bi-x-circle'" class="mr-1"></i>
        {{ acting ? 'กำลังดำเนินการ...' : 'ถอนการลงทะเบียน' }}
      </button>

      <p
        v-else-if="event.status !== 'cancelled'"
        class="py-3 text-center text-sm text-stone-400"
      >
        <i class="bi bi-lock mr-1"></i>ปิดรับสมัครแล้ว
      </p>
    </div>
  </div>
</template>
