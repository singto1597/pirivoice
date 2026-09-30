<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import Swal from 'sweetalert2'
import PaginationBar from '@/components/PaginationBar.vue'
import { fmtDateTime, fmtTime } from '@/datetime'
import { checkInRegistration, getEvent, listRegistrations } from '@/services/event'
import {
  REGISTRATION_ICONS,
  REGISTRATION_LABELS,
  STATUS_ICONS,
  STATUS_LABELS,
  type Event,
  type EventRegistration,
} from '@/types/event'
import type { ApiError } from '@/services/api'

/**
 * 👥 รายชื่อผู้สมัคร + เช็คอินมือ — **หน้าเต็มหน้า ไม่ใช่ modal** (รอบ 4)
 *
 * ⭐ **ทำไมต้องเป็นหน้า** — เดิมอยู่ใน modal ที่ฉากหลังกดปิดได้ ⇒ สภากำลังไล่เช็คอินหน้างาน
 *    แล้วนิ้วพลาดโดนฉากหลัง = ปิดทิ้งกลางคัน · และ **เปิดลิงก์ตรงไม่ได้/refresh ไม่ได้**
 *    ซึ่งเป็นสิ่งที่ต้องทำได้จริงเวลาใช้งานหน้างาน (ส่งลิงก์ให้เพื่อนในสภา · รีเฟรชจอ)
 *
 * ⭐ **เลขหน้าเก็บใน URL (`?page=2`)** — refresh แล้วอยู่หน้าเดิม ไม่เด้งกลับหน้า 1
 *    (คิวที่ยาวเกิน 20 คนคือเคสปกติของกิจกรรมจริง ไม่ใช่ของหายาก)
 *
 * ⚠️ **หัวเรื่องมาจาก `getEvent(id)` ไม่ใช่ state ที่ส่งข้ามหน้า** — เพราะเปิดตรงได้
 *    และ endpoint ตัวนี้เห็น **ฉบับร่างด้วย** (ต่างจาก `/public/{id}`)
 */
const route = useRoute()
const router = useRouter()

const REG_PAGE_SIZE = 20

const eventId = computed<number | null>(() => {
  const n = Number(route.params.id)
  return Number.isInteger(n) && n > 0 ? n : null
})

const event = ref<Event | null>(null)
const regs = ref<EventRegistration[]>([])
const total = ref(0)
/** หน้าปัจจุบัน — ตั้งต้นจาก URL (ดู `setPage`) */
const page = ref(1)
const isLoading = ref(true)
const listLoading = ref(false)
const loadError = ref(false)
/** แยกจาก `loadError` — "ไม่มีกิจกรรมนี้" ไม่ต้องมีปุ่มลองใหม่ (กดแล้วก็ 404 อีก) */
const notFound = ref(false)
const listError = ref('')
/**
 * id ของแถวที่กำลังเช็คอินอยู่ — **เก็บเป็น id ต่อแถว ไม่ใช่ boolean ของทั้งหน้า**
 *
 * ⭐ เก็บ id เพื่อให้ **สปินเนอร์ขึ้นที่แถวที่กดเท่านั้น** — ถ้าใช้ boolean ปุ่มทุกแถวจะหมุนพร้อมกัน
 *    แล้วสภาไม่รู้ว่าแถวไหนกำลังทำงาน (ตอนเลื่อนหารายชื่อในคิวที่ยาว อันนี้สำคัญ)
 *
 * ⚠️ **แต่การล็อกเป็นของทั้งหน้าโดยเจตนา** (`:disabled="actingId !== null"`) — *ไม่ใช่*
 *    การเช็คอินหลายคนพร้อมกัน · เพราะทุกครั้งที่สำเร็จจะ `loadRegistrations()` ใหม่ทั้งชุด
 *    ⇒ สองคำขอที่ทับกันจะโหลดชนกัน แล้วรายชื่อที่ได้อาจเป็นชุดก่อนการเช็คอินอีกคน
 *    (ป้ายสถานะกับความจริงไม่ตรงกันชั่วขณะ ซึ่งสภาจะอ่านว่า "กดไม่ติด")
 *    · ราคาที่จ่ายคือรอ ~200 ms ต่อคน ซึ่งไม่ใช่คอขวดของงานจริง (คอขวดคือคนเดินมาถึงประตู)
 *    · งานที่ต้องเร็วระดับนั้นคือ **หน้าสแกน** ซึ่งทำงานคนละแบบ (ไม่มีรายชื่อให้โหลดซ้ำ)
 */
const actingId = ref<number | null>(null)

/** กิจกรรมถูกลบ (soft delete) — `getEvent` คืน 200 แต่ `list_registrations` จะ 404 */
const isDeleted = computed(() => event.value?.deleted_at != null)

function errText(e: unknown): string {
  if (typeof e === 'string') return e
  if (e instanceof Error) return e.message
  return 'เกิดข้อผิดพลาด กรุณาลองใหม่'
}

// ── เลขหน้า ↔ URL ────────────────────────────────────────────────────────────

/** อ่าน `?page=` ตอน mount — ค่าที่ใช้ไม่ได้ (0, -1, "abc", อาร์เรย์จาก `?page=1&page=2`) ถือเป็นหน้า 1 */
function pageFromQuery(): number {
  const raw = route.query.page
  const n = Number(Array.isArray(raw) ? raw[0] : raw)
  return Number.isInteger(n) && n > 0 ? n : 1
}

/**
 * ตั้งหน้า + เขียนลง URL
 *
 * ⚠️ **`replace` ไม่ใช่ `push`** — กด "หน้าถัดไป" สามครั้งไม่ควรต้องกด back สามครั้ง
 *    เพื่อออกจากหน้านี้ (แต่ยังต้องอยู่ใน URL เพื่อให้ refresh แล้วอยู่หน้าเดิม)
 * ⚠️ หน้า 1 **ลบ `page` ออกจาก query** ไม่ใช่เขียน `page=1` — ไม่งั้นจะเกิดทั้ง
 *    `/registrations` และ `/registrations?page=1` ที่เป็นหน้าเดียวกัน (ลิงก์ซ้ำโดยไม่มีเหตุ)
 */
function setPage(n: number) {
  page.value = n
  void router.replace({ query: { ...route.query, page: n === 1 ? undefined : String(n) } })
}

// ── การโหลด ──────────────────────────────────────────────────────────────────

async function load() {
  isLoading.value = true
  loadError.value = false
  notFound.value = false
  setPage(pageFromQuery())

  const id = eventId.value
  if (id === null) {
    notFound.value = true
    isLoading.value = false
    return
  }

  try {
    event.value = await getEvent(id)
  } catch (e) {
    if ((e as ApiError)?.status === 404) notFound.value = true
    else loadError.value = true
    isLoading.value = false
    return
  }
  isLoading.value = false

  // ⚠️ กิจกรรมที่ถูกลบ: หัวเรื่องยังแสดงได้ แต่ `list_registrations` **คืน 404 แน่นอน**
  //    (service ตรวจ `deleted_at IS NULL`) ⇒ ไม่เรียกเลย ดีกว่าเรียกแล้วเอา 404 ที่รู้สาเหตุอยู่แล้ว
  //    มาแสดงเป็น "โหลดรายชื่อไม่สำเร็จ" ซึ่งชวนให้สภากด "ลองอีกครั้ง" วนไปเปล่า ๆ
  if (isDeleted.value) return

  await loadRegistrations()
}

onMounted(load)

async function loadRegistrations() {
  listLoading.value = true
  listError.value = ''
  try {
    await fetchPage()
  } finally {
    listLoading.value = false
  }
}

async function fetchPage() {
  const id = eventId.value
  if (id === null) return
  try {
    const res = await listRegistrations(id, {
      limit: REG_PAGE_SIZE,
      offset: (page.value - 1) * REG_PAGE_SIZE,
    })
    regs.value = res.items
    total.value = res.total
    // หน้าสุดท้ายหายไปเพราะมีคนถอน/ถูกยกเลิก ⇒ ถอยกลับหนึ่งหน้า **และแก้ URL ให้ตรง**
    // (ถ้าไม่แก้ ผู้ใช้ที่ refresh จะกลับมาที่หน้าว่างอีกครั้งไม่จบ)
    if (regs.value.length === 0 && page.value > 1) {
      setPage(page.value - 1)
      await fetchPage()
    }
  } catch (e) {
    listError.value = errText(e)
    regs.value = []
    total.value = 0
  }
}

function onPageChange(n: number) {
  if (n === page.value) return
  setPage(n)
  loadRegistrations()
}

/**
 * เช็คอินจากรายชื่อ (D2) — **ทางสำรองที่ต้องมีเสมอ**
 *
 * ใช้เมื่อนักเรียนลืมมือถือ/แบตหมด/กล้องสภาไม่ทำงาน — ซึ่งเกิดทุกงาน และเกิดในวันที่
 * แก้ไขอะไรไม่ได้ ⇒ ปุ่มนี้คือเหตุผลที่ endpoint รับ `registration_id` ได้ด้วย ไม่ใช่แค่โทเคน
 *
 * ⚠️ **`already_checked_in` ไม่ใช่ error** — สแกนซ้ำ/กดซ้ำเป็นเรื่องปกติ ⇒ แสดงเป็นข้อความ
 *    "เช็คอินไปแล้วเมื่อ HH:MM" ไม่ใช่แจ้งเตือนสีแดง (เหตุผลเดียวกับฝั่งหน้าสแกน)
 */
async function handleCheckIn(r: EventRegistration) {
  const id = eventId.value
  if (id === null || actingId.value !== null) return
  actingId.value = r.id
  try {
    const res = await checkInRegistration(id, { registration_id: r.id })
    // โหลดรายชื่อใหม่เพื่อให้ป้ายสถานะ/เวลาเป็นค่าที่ server เขียนจริง ไม่ใช่การเดาที่ frontend
    await loadRegistrations()

    const who = res.user_name ?? `ผู้ใช้ #${res.user_id}`
    const when = res.checked_in_at ? `เมื่อ ${fmtTime(res.checked_in_at)} น.` : ''
    // ⚠️ ใช้ `text:` **ไม่ใช่ `html:`** — `who` คือชื่อที่ผู้ใช้ตั้งเองได้ (หน้า ProfileEdit)
    //    ⇒ ใส่ลง `html` เมื่อไร ชื่ออย่าง `<img src=x onerror=...>` จะรันในเบราว์เซอร์สภา
    //    · SweetAlert2 ใส่ `text` ด้วย `textContent` จึงปลอดภัยโดยธรรมชาติ
    if (res.already_checked_in) {
      await Swal.fire({
        icon: 'info',
        title: 'คนนี้เช็คอินไปแล้ว',
        text: when ? `${who} · ${when} · เวลาเดิม ไม่ได้นับซ้ำ` : who,
        confirmButtonText: 'เข้าใจแล้ว',
        confirmButtonColor: '#B91C1C',
      })
    } else {
      await Swal.fire({
        icon: 'success',
        title: 'เช็คอินสำเร็จ',
        text: when ? `${who} · ${when}` : who,
        timer: 1600,
        showConfirmButton: false,
      })
    }
  } catch (e) {
    await Swal.fire({ icon: 'error', title: 'เช็คอินไม่สำเร็จ', text: errText(e) })
  } finally {
    actingId.value = null
  }
}

const goBack = () => router.push({ name: 'event-management' })
</script>

<template>
  <div class="max-w-2xl mx-auto">
    <!-- Loading skeleton (หัวเรื่อง) -->
    <div v-if="isLoading" class="space-y-4" aria-busy="true">
      <div class="h-6 w-64 animate-pulse rounded bg-stone-100"></div>
      <div class="space-y-2 rounded-2xl border border-stone-200 bg-white p-6">
        <div v-for="n in 5" :key="n" class="h-10 animate-pulse rounded-xl bg-stone-100"></div>
      </div>
    </div>

    <!-- ไม่มีกิจกรรมนี้ -->
    <div
      v-else-if="notFound"
      class="rounded-2xl border-2 border-dashed border-stone-200 bg-white py-16 text-center"
    >
      <i class="bi bi-calendar-x mb-3 block text-3xl text-stone-400"></i>
      <p class="text-[15px] font-semibold text-stone-700">ไม่พบกิจกรรมนี้</p>
      <p class="mt-1 text-sm text-stone-500">อาจถูกลบถาวรไปแล้ว หรือลิงก์ไม่ถูกต้อง</p>
      <button
        type="button"
        @click="goBack"
        class="mt-5 inline-flex items-center gap-2 rounded-lg bg-[#B91C1C] px-5 py-2.5 text-[13px] font-bold text-white transition-colors hover:bg-[#991B1B]"
      >
        <i class="bi bi-arrow-left"></i> กลับหน้าจัดการกิจกรรม
      </button>
    </div>

    <!-- Error + retry -->
    <div
      v-else-if="loadError"
      class="rounded-2xl border-2 border-dashed border-stone-200 bg-white py-16 text-center"
    >
      <i class="bi bi-people mb-3 block text-3xl text-stone-400"></i>
      <p class="text-[15px] font-semibold text-stone-700">โหลดข้อมูลกิจกรรมไม่สำเร็จ</p>
      <p class="mt-1 text-sm text-stone-500">ตรวจสอบการเชื่อมต่อแล้วลองอีกครั้ง</p>
      <button
        type="button"
        @click="load"
        class="mt-5 inline-flex items-center gap-2 rounded-lg bg-[#B91C1C] px-5 py-2.5 text-[13px] font-bold text-white transition-colors hover:bg-[#991B1B]"
      >
        <i class="bi bi-arrow-clockwise"></i> ลองใหม่
      </button>
    </div>

    <div v-else class="space-y-4">
      <!-- หัวเรื่อง + ทางไปหน้าสแกน -->
      <div class="flex items-start gap-3">
        <button
          type="button"
          @click="goBack"
          aria-label="กลับหน้าจัดการกิจกรรม"
          class="mt-1 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-stone-200 bg-white text-stone-500 transition hover:border-[#B91C1C]/30 hover:bg-[#B91C1C]/5 hover:text-[#B91C1C]"
        >
          <i class="bi bi-arrow-left text-lg"></i>
        </button>
        <div class="min-w-0 flex-1">
          <p class="mb-1 text-[11px] font-bold uppercase tracking-widest text-[#B91C1C]">
            <i class="bi bi-people mr-1"></i> Registrations
          </p>
          <h1 class="text-2xl font-bold leading-tight tracking-tight text-stone-900 sm:text-3xl">
            รายชื่อผู้สมัคร
          </h1>
          <p class="mt-1 truncate text-sm text-stone-500">{{ event?.title }}</p>
        </div>
        <!-- ทางไปหน้าสแกน — อยู่ในหัวเรื่องเพื่อให้เจอตั้งแต่ยังไม่เลื่อนดูรายชื่อ -->
        <RouterLink
          v-if="event"
          :to="{ name: 'event-check-in', params: { id: event.id } }"
          class="mt-1 shrink-0 rounded-xl border border-[#B91C1C]/30 bg-white px-3 py-2 text-[12px] font-bold text-[#B91C1C] transition-colors hover:bg-red-50"
          data-testid="open-scanner-link"
        >
          <i class="bi bi-qr-code-scan mr-1"></i>สแกน
        </RouterLink>
      </div>

      <!-- ถูกลบแล้ว — `list_registrations` จะ 404 จึงไม่เรียกเลย (ดูคอมเมนต์ใน `load`) -->
      <div
        v-if="isDeleted"
        class="flex items-start gap-2.5 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3.5"
      >
        <i class="bi bi-trash3 mt-0.5 text-amber-600"></i>
        <div class="text-[13px] text-amber-800">
          <p class="font-bold">กิจกรรมนี้ถูกลบแล้ว — ดูรายชื่อไม่ได้จนกว่าจะกู้คืน</p>
          <p class="mt-0.5 text-amber-700">
            กลับไปหน้าการจัดการกิจกรรม แล้วกด "กู้คืน" ในรายการก่อน
          </p>
        </div>
      </div>

      <div v-else class="rounded-2xl border border-stone-200 bg-white">
        <div class="flex items-center justify-between border-b border-stone-100 px-5 py-3">
          <p class="text-[12px] font-semibold text-stone-500">
            <i :class="STATUS_ICONS[event?.status ?? 'draft']" class="mr-1"></i>
            {{ event ? STATUS_LABELS[event.status] : '' }}
          </p>
          <p v-if="!listLoading && total > 0" class="text-[12px] text-stone-400">
            ทั้งหมด {{ total.toLocaleString('en-US') }} คน
          </p>
        </div>

        <div class="px-5 py-4">
          <div v-if="listLoading" class="space-y-2">
            <div v-for="n in 5" :key="n" class="h-10 animate-pulse rounded-xl bg-stone-100"></div>
          </div>

          <div v-else-if="listError" class="py-10 text-center">
            <p class="text-sm text-stone-600">{{ listError }}</p>
            <button
              type="button"
              @click="loadRegistrations"
              class="mt-4 rounded-lg bg-stone-100 px-4 py-2 text-sm font-semibold text-stone-700 hover:bg-stone-200"
            >
              <i class="bi bi-arrow-clockwise mr-1"></i> ลองอีกครั้ง
            </button>
          </div>

          <div v-else-if="regs.length === 0" class="py-10 text-center text-stone-400">
            <div class="mb-2 text-3xl"><i class="bi bi-person-dash"></i></div>
            <p class="text-sm text-stone-500">ยังไม่มีใครลงทะเบียนกิจกรรมนี้</p>
          </div>

          <ul v-else class="divide-y divide-stone-100">
            <li v-for="r in regs" :key="r.id" class="flex items-center gap-3 py-2.5">
              <span class="w-6 shrink-0 text-center text-xs tabular-nums text-stone-400">
                {{ r.id }}
              </span>
              <div class="min-w-0 flex-1">
                <p class="truncate text-sm font-medium text-stone-800">
                  {{ r.user_name ?? `ผู้ใช้ #${r.user_id}` }}
                </p>
                <!-- เช็คอินแล้ว → โชว์ "เวลาที่มาถึง" แทนเวลาสมัคร ซึ่งเป็นข้อมูลที่สภาใช้จริง -->
                <p
                  v-if="r.status === 'checked_in' && r.checked_in_at"
                  class="text-[11px] text-emerald-600"
                >
                  <i class="bi bi-person-check mr-0.5"></i>เช็คอิน {{ fmtTime(r.checked_in_at) }} น.
                </p>
                <p v-else class="text-[11px] text-stone-400">
                  {{ fmtDateTime(r.registered_at) }}
                </p>
              </div>
              <span
                class="inline-flex shrink-0 items-center gap-1 rounded-md px-2 py-0.5 text-[11px] font-semibold"
                :class="{
                  'bg-emerald-50 text-emerald-700':
                    r.status === 'registered' || r.status === 'checked_in',
                  'bg-amber-50 text-amber-700': r.status === 'waitlisted',
                  'bg-stone-100 text-stone-500': r.status === 'cancelled',
                }"
              >
                <i :class="`bi ${REGISTRATION_ICONS[r.status]}`"></i>
                {{ REGISTRATION_LABELS[r.status] }}
              </span>
              <!--
                ปุ่มเช็คอินมือ — เฉพาะแถวที่ "ถือที่นั่งจริงและยังไม่เช็คอิน"
                ⚠️ ไม่มีให้คิวสำรอง (ยังไม่มีที่นั่งให้เช็คอิน — backend ตอบ 400) และไม่มีให้
                   คนที่เช็คอินแล้ว/ถูกยกเลิก ⇒ ซ่อนปุ่มที่เป็นไปไม่ได้ไว้ตั้งแต่ต้น ดีกว่า
                   ให้กดแล้วเจอ error ที่อธิบายว่าทำไมกดไม่ได้
              -->
              <button
                v-if="r.status === 'registered'"
                type="button"
                :disabled="actingId !== null"
                class="shrink-0 rounded-lg bg-[#B91C1C] px-2.5 py-1.5 text-[12px] font-bold text-white transition-colors hover:bg-[#991B1B] disabled:opacity-50"
                :data-testid="`checkin-btn-${r.id}`"
                @click="handleCheckIn(r)"
              >
                <i
                  :class="actingId === r.id ? 'bi bi-arrow-repeat animate-spin' : 'bi bi-person-check'"
                  class="mr-0.5"
                ></i>
                เช็คอิน
              </button>
            </li>
          </ul>
        </div>

        <div v-if="total > REG_PAGE_SIZE" class="border-t border-stone-100 px-5 py-3">
          <PaginationBar
            :total="total"
            :page="page"
            :page-size="REG_PAGE_SIZE"
            :loading="listLoading"
            @page-change="onPageChange"
          />
        </div>
      </div>
    </div>
  </div>
</template>
