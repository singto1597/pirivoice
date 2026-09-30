<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import Swal from 'sweetalert2'
import { BRAND } from '@/constants/brand'
import PaginationBar from '@/components/PaginationBar.vue'
// 🕐 เวลามาจากโมดูลกลาง — **ห้ามประกาศซ้ำในไฟล์นี้** (เดิมก๊อปอยู่ 4 ไฟล์แล้วเพี้ยนจากกัน)
import { fmtDateTime } from '@/datetime'
import { cancelEvent, deleteEvent, listEvents, publishEvent, restoreEvent } from '@/services/event'
import {
  CATEGORY_LABELS,
  EVENT_CATEGORIES,
  EVENT_LIST_STATUSES,
  LIST_STATUS_LABELS,
  STATUS_ICONS,
  STATUS_LABELS,
  categoryIcon,
  categoryLabel,
  isEventCategory,
  type Event,
  type EventListStatus,
} from '@/types/event'

/**
 * 📅 จัดการกิจกรรม (สภา) — **รายการเดียว: เผยแพร่/ยกเลิก/ลบ/กู้คืน**
 *
 * ⭐ **ไฟล์นี้ไม่มี modal แล้ว** (รอบ 4) — "สร้าง/แก้ไขกิจกรรม" และ "รายชื่อผู้สมัคร"
 *    ถูกย้ายเป็น **หน้าเต็มหน้า** (`EventForm.vue` · `EventRegistrations.vue`) เพราะ modal
 *    ที่มีฉากหลังกดปิดได้ ทำให้ข้อมูลที่ผู้ใช้พิมพ์ไว้หายทั้งก้อนด้วยการคลิกพลาดครั้งเดียว
 *    ⇒ ที่นี่เหลือแค่ปุ่มที่พาไปหน้าเหล่านั้น (`router.push`) ไม่มี state ของฟอร์มเหลืออยู่เลย
 *
 * ⚠️ **ถ้าจะเพิ่ม modal ในไฟล์นี้ ต้องอ่าน §14 / PR #33 ก่อน** — modal ที่เรนเดอร์ในไฟล์นี้
 *    จะติดอยู่ใน stacking context `relative z-10` ของ `.maincol` ⇒ `z-50` ถูกกักที่ชั้น 10
 *    แล้วแพ้ `<nav>` (`fixed z-40`) ที่เป็นพี่น้องกัน ⇒ แถบล่างทับ **และกลืนคลิกปุ่มยืนยัน**
 *    (ทางแก้คือ `<Teleport to="body">` — **กฎนี้ยังจริง ไม่ได้ถูกยกเลิก** แค่ตอนนี้ไม่มี modal
 *    ให้ใช้มันแล้ว · อย่าลบย่อหน้านี้ทิ้งเพราะคิดว่าไม่มีใครใช้)
 *
 * ⚠️ **สถานะ `live` (ค่าเริ่มต้น) = "ทุกอย่างที่ยังไม่ถูกลบ"** ไม่ใช่สถานะจริงของแถว
 *    ⇒ ป้ายจะขึ้น "ทั้งหมด" ไม่ใช่ "live" (ดู `LIST_STATUS_LABELS`)
 *
 * ⚠️ **กิจกรรมที่ `draft` เปิดดูหน้าสาธารณะไม่ได้ (404)** ⇒ ปุ่ม "ดูหน้าเว็บ" จึงแสดงเฉพาะ
 *    `published`/`cancelled` เท่านั้น ไม่ใช่ซ่อนเพื่อความสวยงาม แต่เพราะลิงก์จะพาไปเจอ
 *    "เปิดดูไม่ได้" ซึ่งดูเหมือนบั๊กทั้งที่ระบบถูก
 */
const router = useRouter()

const PAGE_SIZE = 20

const items = ref<Event[]>([])
const total = ref(0)
const page = ref(1)
const statusFilter = ref<EventListStatus>('live')
/**
 * ตัวกรองหมวด (D4) — **`''` = ทุกหมวด** (ไม่ใช่ `'other'` ซึ่งแปลว่า "เฉพาะหมวดอื่น ๆ")
 *
 * ⚠️ เก็บเป็น `string` เปล่าเพราะค่ามาจาก `<select>` (DOM ให้สตริงเสมอ) ⇒ ด่านแคบอยู่ที่
 *    `load()` ด้วย `isEventCategory()` ไม่ใช่ที่ type ของ ref
 *    · แบบเดียวกับ `subcategoryFilter` ใน `ReceivedIssues.vue` (`''` = ทุกหมวดย่อย)
 *
 * ⚠️ **ส่ง `''` ตรง ๆ ไม่ได้** — จะกลายเป็น `category=` ใน querystring ซึ่งไม่ตรง pattern
 *    ฝั่ง backend ⇒ **422** (ไม่ใช่ "ไม่กรอง") · ต้องแปลงเป็น `undefined` เสมอ
 */
const categoryFilter = ref('')
const isLoading = ref(true)
const hasError = ref(false)

/** id ของแถวที่กำลังยิงคำขอ + ชนิดคำขอ — ใช้แสดงสปินเนอร์เฉพาะปุ่มที่กด ไม่ล็อกทั้งตาราง */
const actingId = ref<number | null>(null)
const actingKind = ref<'publish' | 'cancel' | 'delete' | 'restore' | null>(null)

const isEmpty = computed(() => !isLoading.value && !hasError.value && items.value.length === 0)

/**
 * ข้อความตอนว่าง — **ต้องแยกให้ออกว่า "ไม่มีของ" กับ "ตัวกรองซ่อนอยู่"**
 *
 * ⚠️ ทั้งสองกรณีแสดงผลเหมือนกันเป๊ะ (การ์ด 0 ใบ) แต่ความหมายตรงข้าม: กรณีหลังของ *มีอยู่จริง*
 *    ⇒ ข้อความกลาง ๆ อย่าง "ยังไม่มีกิจกรรมในระบบ" จะทำให้สภาตกใจแล้วไปสร้างซ้ำ
 */
const emptyText = computed(() => {
  if (categoryFilter.value) {
    return `ไม่มีกิจกรรมในหมวด "${categoryLabel(categoryFilter.value)}" ตามตัวกรองที่เลือก`
  }
  return statusFilter.value === 'live' ? 'ยังไม่มีกิจกรรมในระบบ' : 'ไม่มีกิจกรรมในสถานะนี้'
})

onMounted(load)

function errText(e: unknown): string {
  if (typeof e === 'string') return e
  if (e instanceof Error) return e.message
  return 'เกิดข้อผิดพลาดที่ไม่รู้จัก'
}

async function load() {
  isLoading.value = true
  hasError.value = false
  try {
    const res = await listEvents({
      status: statusFilter.value,
      category: isEventCategory(categoryFilter.value) ? categoryFilter.value : undefined,
      limit: PAGE_SIZE,
      offset: (page.value - 1) * PAGE_SIZE,
    })
    items.value = res.items
    total.value = res.total
    // ⚠️ หน้าที่ว่างเปล่าต้องถอยกลับ ไม่ใช่ปล่อยค้าง — หลังลบ/กู้คืนแถวสุดท้ายของหน้าสุดท้าย
    //    หน้านี้จะไม่มีอะไรเหลือ และ **`<PaginationBar>` หายไปด้วย** เพราะมันอยู่ในกิ่ง
    //    `v-else` ของรายการ ⇒ ถ้าไม่ถอย ผู้ใช้จะไม่มีทางกลับไปดูแถวที่เหลือได้เลย
    //    (วางไว้ที่เดียวตรงนี้แทนการไล่ใส่หลังทุก mutation เพราะครอบทั้งลบ/กู้คืน/สร้าง)
    if (items.value.length === 0 && page.value > 1) {
      page.value -= 1
      await load()
    }
  } catch {
    hasError.value = true
    items.value = []
    total.value = 0
  } finally {
    isLoading.value = false
  }
}

function switchStatus(s: EventListStatus) {
  if (statusFilter.value === s) return
  statusFilter.value = s
  page.value = 1
  load()
}

/** เปลี่ยนหมวด ⇒ กลับไปหน้า 1 เสมอ (ไม่งั้นอาจค้างอยู่หน้า 3 ของผลลัพธ์ชุดใหม่ที่สั้นกว่า) */
function onCategoryChange() {
  page.value = 1
  load()
}

/** ปุ่มในสถานะว่าง — ล้างตัวกรองหมวด **แล้วโหลดใหม่** (ไม่ใช่แค่เคลียร์ค่าแล้วรอ) */
function clearCategoryFilter() {
  categoryFilter.value = ''
  page.value = 1
  load()
}

function onPageChange(n: number) {
  page.value = n
  load()
}

function busy(e: Event, kind: 'publish' | 'cancel' | 'delete' | 'restore'): boolean {
  return actingId.value === e.id && actingKind.value === kind
}

async function runAction(e: Event, kind: 'publish' | 'cancel' | 'delete' | 'restore') {
  if (actingId.value !== null) return
  actingId.value = e.id
  actingKind.value = kind
  try {
    if (kind === 'publish') {
      const res = await Swal.fire({
        title: 'เผยแพร่กิจกรรมนี้?',
        html:
          'เมื่อเผยแพร่แล้ว <b>นักเรียนทุกคนจะได้รับการแจ้งเตือน</b><br>' +
          '<span class="text-sm text-stone-500">และแก้ไขกลับเป็นฉบับร่างไม่ได้</span>',
        icon: 'question',
        showCancelButton: true,
        confirmButtonText: 'เผยแพร่เลย',
        confirmButtonColor: BRAND,
        cancelButtonText: 'ยกเลิก',
      })
      if (!res.isConfirmed) return
      await publishEvent(e.id)
      await load()
      Swal.fire({ icon: 'success', title: 'เผยแพร่แล้ว', timer: 1200, showConfirmButton: false })
    } else if (kind === 'cancel') {
      const res = await Swal.fire({
        title: 'ยกเลิกกิจกรรมนี้?',
        html:
          'กิจกรรมจะยังเปิดดูได้ แต่ปิดรับสมัครทันที<br>' +
          `<span class="text-sm text-stone-500">คนแรกในคิวสำรอง${
            e.waitlisted_count > 0 ? ` (${e.waitlisted_count} คน)` : ''
          } จะไม่ถูกเลื่อนขึ้น — การยกเลิกไม่ใช่การลบ</span>`,
        icon: 'warning',
        showCancelButton: true,
        confirmButtonText: 'ยกเลิกกิจกรรม',
        confirmButtonColor: BRAND,
        cancelButtonText: 'ไม่ยกเลิก',
      })
      if (!res.isConfirmed) return
      await cancelEvent(e.id)
      await load()
      Swal.fire({ icon: 'success', title: 'ยกเลิกกิจกรรมแล้ว', timer: 1200, showConfirmButton: false })
    } else if (kind === 'delete') {
      const res = await Swal.fire({
        title: 'ลบกิจกรรมนี้?',
        html:
          `«${e.title}»<br>` +
          `<span class="text-sm text-stone-500">ผู้สมัคร ${e.registered_count} คนจะถูกลบไปด้วย · กู้คืนได้จากตัวกรอง "ถูกลบ"</span>`,
        icon: 'warning',
        showCancelButton: true,
        confirmButtonText: 'ลบกิจกรรม',
        confirmButtonColor: BRAND,
        cancelButtonText: 'ไม่ลบ',
      })
      if (!res.isConfirmed) return
      await deleteEvent(e.id)
      await load()
      Swal.fire({ icon: 'success', title: 'ลบแล้ว', timer: 1000, showConfirmButton: false })
    } else {
      await restoreEvent(e.id)
      await load()
      Swal.fire({ icon: 'success', title: 'กู้คืนแล้ว', timer: 1000, showConfirmButton: false })
    }
  } catch (err) {
    Swal.fire({ icon: 'error', title: 'ดำเนินการไม่สำเร็จ', text: errText(err) })
  } finally {
    actingId.value = null
    actingKind.value = null
  }
}

function capacityText(e: Event): string {
  return e.capacity === null ? 'ไม่จำกัด' : `${e.capacity.toLocaleString('en-US')} ที่นั่ง`
}
</script>

<template>
  <div>
    <!-- Editorial header -->
    <div class="mb-6 flex flex-wrap items-start justify-between gap-3">
      <div class="w-full min-w-0 sm:w-auto sm:flex-1">
        <p class="text-[11px] font-bold uppercase tracking-widest text-brand mb-1.5">
          <i class="bi bi-calendar-event mr-1"></i> Events
        </p>
        <h1 class="text-2xl sm:text-3xl font-bold tracking-tight text-stone-900 leading-tight">
          จัดการกิจกรรม
        </h1>
        <p class="text-sm text-stone-500 mt-1.5">
          สร้างกิจกรรม เปิดรับสมัคร และดูรายชื่อผู้เข้าร่วม
        </p>
      </div>
      <button
        type="button"
        data-testid="add-event"
        @click="router.push({ name: 'event-create' })"
        class="inline-flex w-full items-center justify-center gap-1.5 rounded-xl bg-brand px-4 py-2.5 text-sm font-bold text-white shadow-md transition-all hover:bg-brand-strong hover:shadow-lg active:scale-[0.97] sm:w-auto sm:shrink-0"
      >
        <i class="bi bi-plus-lg"></i> สร้างกิจกรรม
      </button>
    </div>

    <!-- แถบกรองสถานะ -->
    <div class="mb-5 flex flex-wrap items-center gap-2">
      <div class="flex flex-wrap gap-1 rounded-xl bg-stone-100 p-1">
        <button
          v-for="s in EVENT_LIST_STATUSES"
          :key="s"
          type="button"
          @click="switchStatus(s)"
          class="rounded-lg px-3.5 py-2 text-sm font-medium transition"
          :class="
            statusFilter === s
              ? 'border border-stone-200 bg-white text-brand'
              : 'text-stone-500 hover:text-stone-700'
          "
        >
          {{ LIST_STATUS_LABELS[s] }}
        </button>
      </div>

      <!-- ตัวกรองหมวด (D4) — ใช้ <select> ไม่ใช่ชิป เพราะ 7 หมวดจะไปเบียดแถวสถานะจนอ่านไม่ออก -->
      <select
        v-model="categoryFilter"
        aria-label="กรองตามหมวดกิจกรรม"
        data-testid="category-filter"
        class="rounded-xl border border-stone-200 bg-white px-3 py-2 text-sm text-stone-700 outline-none transition-colors focus:border-brand focus:ring-2 focus:ring-brand/10"
        @change="onCategoryChange"
      >
        <option value="">ทุกหมวด</option>
        <option v-for="c in EVENT_CATEGORIES" :key="c" :value="c">
          {{ CATEGORY_LABELS[c] }}
        </option>
      </select>

      <span class="ml-auto text-sm tabular-nums text-stone-400">
        {{ total.toLocaleString('en-US') }} กิจกรรม
      </span>
    </div>

    <!-- โหลด -->
    <div v-if="isLoading" class="space-y-3">
      <div v-for="n in 4" :key="n" class="rounded-2xl bg-white p-5 ring-1 ring-stone-200">
        <div class="mb-3 h-5 w-24 animate-pulse rounded-md bg-stone-100"></div>
        <div class="mb-2 h-5 w-2/3 animate-pulse rounded bg-stone-100"></div>
        <div class="h-4 w-1/2 animate-pulse rounded bg-stone-100"></div>
      </div>
    </div>

    <!-- ผิดพลาด -->
    <div
      v-else-if="hasError"
      class="rounded-2xl border-2 border-dashed border-stone-200 px-6 py-20 text-center"
    >
      <i class="bi bi-wifi-off mb-3 inline-block text-3xl text-stone-300"></i>
      <p class="font-medium text-stone-600">โหลดรายการกิจกรรมไม่สำเร็จ</p>
      <button
        type="button"
        @click="load"
        class="mt-5 inline-flex items-center gap-2 rounded-lg bg-brand px-5 py-2.5 text-sm font-bold text-white transition-colors hover:bg-brand-strong"
      >
        <i class="bi bi-arrow-clockwise"></i> ลองอีกครั้ง
      </button>
    </div>

    <!-- ว่าง -->
    <div
      v-else-if="isEmpty"
      class="rounded-2xl border border-dashed border-stone-200 bg-white p-12 text-center text-stone-400"
    >
      <div class="mb-2 text-4xl"><i class="bi bi-calendar-plus"></i></div>
      <p class="text-stone-500">
        {{ emptyText }}
      </p>
      <p v-if="statusFilter === 'live' && !categoryFilter" class="mt-1 text-sm text-stone-400">
        เริ่มจากกด "สร้างกิจกรรม" แล้วเผยแพร่ให้นักเรียนเห็น
      </p>
      <!-- ⚠️ ต้องบอกทางออกเมื่อ "ว่างเพราะตัวกรอง" — ไม่งั้นสภาจะอ่านว่า "กิจกรรมหายไปหมด"
           แล้วไปสร้างซ้ำ ซึ่งเป็นความเสียหายจริง (ไม่ใช่แค่ข้อความไม่สวย) -->
      <button
        v-else-if="categoryFilter"
        type="button"
        data-testid="clear-category-filter"
        class="mt-4 inline-flex items-center gap-2 rounded-lg bg-stone-100 px-4 py-2 text-sm font-semibold text-stone-700 transition-colors hover:bg-stone-200"
        @click="clearCategoryFilter"
      >
        <i class="bi bi-x-lg"></i> ล้างตัวกรองหมวด ({{ categoryLabel(categoryFilter) }})
      </button>
    </div>

    <!-- รายการ -->
    <div v-else class="space-y-3">
      <div v-for="e in items" :key="e.id" class="rounded-2xl bg-white p-5 ring-1 ring-stone-200">
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div class="w-full min-w-0 sm:w-auto sm:flex-1">
            <!-- สถานะ + ตัวเลข -->
            <div class="mb-1.5 flex flex-wrap items-center gap-2">
              <span
                class="inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-[11px] font-semibold"
                :class="{
                  'bg-stone-100 text-stone-600': e.status === 'draft',
                  'bg-emerald-50 text-emerald-700': e.status === 'published',
                  'bg-red-50 text-brand': e.status === 'cancelled',
                }"
              >
                <i :class="`bi ${STATUS_ICONS[e.status]}`"></i> {{ STATUS_LABELS[e.status] }}
              </span>
              <!-- หมวด (D4) — ใช้ categoryLabel/categoryIcon ไม่ใช่ CATEGORY_LABELS[c] ตรง ๆ
                   เพราะ e.category เป็น string หลวม (backend อาจมีหมวดที่เราไม่รู้จัก) -->
              <span
                class="inline-flex items-center gap-1 rounded-md bg-sky-50 px-2 py-0.5 text-[11px] font-semibold text-sky-700"
              >
                <i :class="`bi ${categoryIcon(e.category)}`"></i> {{ categoryLabel(e.category) }}
              </span>
              <span
                v-if="e.deleted_at"
                class="inline-flex items-center gap-1 rounded-md bg-amber-50 px-2 py-0.5 text-[11px] font-semibold text-amber-700"
              >
                <i class="bi bi-trash3"></i> ถูกลบ
              </span>
              <span class="text-[11px] text-stone-400 tabular-nums">
                สมัคร {{ e.registered_count.toLocaleString('en-US') }} คน
                <template v-if="e.waitlisted_count > 0">
                  · รอคิว {{ e.waitlisted_count.toLocaleString('en-US') }} คน
                </template>
              </span>
            </div>

            <h3 class="font-semibold leading-snug text-stone-900 break-words">{{ e.title }}</h3>

            <div class="mt-1.5 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-stone-500">
              <span><i class="bi bi-clock mr-1"></i>{{ fmtDateTime(e.event_date) }}</span>
              <span v-if="e.location" class="min-w-0 truncate">
                <i class="bi bi-geo-alt mr-1"></i>{{ e.location }}
              </span>
              <span><i class="bi bi-people mr-1"></i>{{ capacityText(e) }}</span>
              <span v-if="e.created_by_name">
                <i class="bi bi-person mr-1"></i>สร้างโดย {{ e.created_by_name }}
              </span>
            </div>
          </div>

          <!-- ปุ่มจัดการ — ห่อ flex-wrap ให้มือถือไม่บีบจนตัวหนังสือขึ้นบรรทัดละตัว -->
          <div class="flex w-full flex-wrap items-center gap-1.5 sm:w-auto sm:shrink-0">
            <!-- เผยแพร่ได้ครั้งเดียว: draft → published -->
            <button
              v-if="e.status === 'draft' && !e.deleted_at"
              type="button"
              :disabled="actingId !== null"
              @click="runAction(e, 'publish')"
              class="rounded-lg bg-brand px-3 py-1.5 text-xs font-bold text-white transition-colors hover:bg-brand-strong disabled:opacity-50"
            >
              <i :class="busy(e, 'publish') ? 'bi bi-arrow-repeat animate-spin' : 'bi bi-megaphone'"></i>
              เผยแพร่
            </button>

            <!-- ยกเลิกได้เฉพาะที่เผยแพร่แล้ว -->
            <button
              v-if="e.status === 'published' && !e.deleted_at"
              type="button"
              :disabled="actingId !== null"
              @click="runAction(e, 'cancel')"
              class="rounded-lg bg-white px-3 py-1.5 text-xs font-semibold text-amber-700 ring-1 ring-amber-200 transition-colors hover:bg-amber-50 disabled:opacity-50"
            >
              <i :class="busy(e, 'cancel') ? 'bi bi-arrow-repeat animate-spin' : 'bi bi-x-octagon'"></i>
              ยกเลิก
            </button>

            <button
              v-if="!e.deleted_at"
              type="button"
              :disabled="actingId !== null"
              @click="router.push({ name: 'event-edit', params: { id: e.id } })"
              class="rounded-lg bg-stone-100 px-3 py-1.5 text-xs font-semibold text-stone-700 transition-colors hover:bg-stone-200 disabled:opacity-50"
            >
              <i class="bi bi-pencil"></i> แก้ไข
            </button>

            <!-- ฉบับร่างยังไม่มีผู้สมัครโดยธรรมชาติ ⇒ ไม่ต้องมีปุ่มนี้ -->
            <button
              v-if="e.status !== 'draft' && !e.deleted_at"
              type="button"
              @click="router.push({ name: 'event-registrations', params: { id: e.id } })"
              class="rounded-lg bg-stone-100 px-3 py-1.5 text-xs font-semibold text-stone-700 transition-colors hover:bg-stone-200"
            >
              <i class="bi bi-list-check"></i> ผู้สมัคร
            </button>

            <!-- ⚠️ draft เปิดดูสาธารณะไม่ได้ (404) ⇒ ลิงก์เฉพาะที่เปิดได้จริง -->
            <button
              v-if="e.status !== 'draft' && !e.deleted_at"
              type="button"
              @click="router.push({ name: 'event-detail', params: { id: e.id } })"
              class="rounded-lg bg-stone-100 px-3 py-1.5 text-xs font-semibold text-stone-700 transition-colors hover:bg-stone-200"
            >
              <i class="bi bi-box-arrow-up-right"></i> ดูหน้าเว็บ
            </button>

            <button
              v-if="!e.deleted_at"
              type="button"
              :disabled="actingId !== null"
              @click="runAction(e, 'delete')"
              class="rounded-lg bg-white px-3 py-1.5 text-xs font-semibold text-red-600 ring-1 ring-red-200 transition-colors hover:bg-red-50 disabled:opacity-50"
            >
              <i :class="busy(e, 'delete') ? 'bi bi-arrow-repeat animate-spin' : 'bi bi-trash3'"></i>
              ลบ
            </button>

            <button
              v-else
              type="button"
              :disabled="actingId !== null"
              @click="runAction(e, 'restore')"
              class="rounded-lg bg-white px-3 py-1.5 text-xs font-semibold text-[#B45309] ring-1 ring-amber-200 transition-colors hover:bg-amber-50 disabled:opacity-50"
            >
              <i :class="busy(e, 'restore') ? 'bi bi-arrow-repeat animate-spin' : 'bi bi-arrow-counterclockwise'"></i>
              กู้คืน
            </button>
          </div>
        </div>
      </div>
    </div>

    <PaginationBar
      :total="total"
      :page="page"
      :page-size="PAGE_SIZE"
      :loading="isLoading"
      @page-change="onPageChange"
    />
  </div>
</template>
