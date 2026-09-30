<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import PaginationBar from '@/components/PaginationBar.vue'
import { listPublicEvents } from '@/services/event'
import {
  CATEGORY_LABELS,
  EVENT_CATEGORIES,
  EVENT_SCOPES,
  REGISTRATION_ICONS,
  REGISTRATION_LABELS,
  SCOPE_LABELS,
  categoryIcon,
  categoryLabel,
  isEventCategory,
  seatsLabel,
  type EventScope,
  type PublicEvent,
} from '@/types/event'

/**
 * 📅 รายการกิจกรรม (ฝั่งนักเรียน) — เห็นเฉพาะที่สภาจะ "เผยแพร่แล้ว"
 *
 * ⚠️ **ห้ามเทียบเวลาที่นี่** — `is_registration_open` มาจาก server (คำนวณใน SQL) เพราะ
 *    นาฬิกาเครื่องผู้ใช้อาจเพี้ยนคนละโซน และกติกา "ปิดรับเมื่อไหร่" เป็นกติกาของ *ระบบ*
 *    ไม่ใช่การแสดงผล (ดู docstring ใน `types/event.ts`)
 *
 * ⚠️ กิจกรรมที่ถูก **ยกเลิก** ยังอยู่ในลิสต์นี้โดยเจตนา (status='cancelled') — การซ่อนไปเลย
 *    ทำให้คนที่เห็นโปสเตอร์แล้วมาหาไม่เจอ · ที่หายไปจริงคือ **ฉบับร่าง** และ **ที่ถูกลบ**
 *    ซึ่ง backend คืน 404 อยู่แล้ว
 */
const PAGE_SIZE = 12

const events = ref<PublicEvent[]>([])
const total = ref(0)
const page = ref(1)
const scope = ref<EventScope>('upcoming')
/**
 * ตัวกรองหมวด (D4) — **`''` = ทุกหมวด** · เก็บเป็น `string` เพราะค่ามาจาก `<select>`
 * ⚠️ อย่าส่ง `''` ต่อให้ backend — ต้องแปลงเป็น `undefined` (ดู `load()`) ไม่งั้นได้ 422
 */
const category = ref('')
const isLoading = ref(true)
const error = ref('')

const isEmpty = computed(() => !isLoading.value && !error.value && events.value.length === 0)

/**
 * ข้อความตอนว่าง — ต้องแยก "ยังไม่มีกิจกรรม" ออกจาก "ตัวกรองซ่อนอยู่"
 * (การ์ด 0 ใบเหมือนกันเป๊ะ แต่ความหมายตรงข้าม ⇒ ข้อความกลาง ๆ จะทำให้เข้าใจผิดว่ากิจกรรมหาย)
 */
const emptyText = computed(() => {
  if (category.value) return `ยังไม่มีกิจกรรมหมวด "${categoryLabel(category.value)}" ในช่วงนี้`
  return scope.value === 'past' ? 'ยังไม่มีกิจกรรมที่ผ่านไปแล้ว' : 'ยังไม่มีกิจกรรมในเงื่อนไขนี้'
})

onMounted(load)

function switchScope(s: EventScope) {
  if (scope.value === s) return
  scope.value = s
  page.value = 1
  load()
}

function onCategoryChange() {
  page.value = 1
  load()
}

function clearCategory() {
  category.value = ''
  page.value = 1
  load()
}

function onPageChange(n: number) {
  page.value = n
  load()
}

async function load() {
  isLoading.value = true
  error.value = ''
  try {
    const res = await listPublicEvents({
      scope: scope.value,
      category: isEventCategory(category.value) ? category.value : undefined,
      limit: PAGE_SIZE,
      offset: (page.value - 1) * PAGE_SIZE,
    })
    events.value = res.items
    total.value = res.total
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'โหลดรายการกิจกรรมไม่สำเร็จ'
  } finally {
    isLoading.value = false
  }
}

/**
 * กิจกรรมมี **วันและเวลา** (timestamptz) ต่างจากบอร์ด/ประกาศที่เป็นวันที่ล้วน
 * ⇒ ใช้ `toLocaleString` กับ ISO ที่มี tz ได้ตรง ๆ (ไม่ใช่ `date-only` ที่ห้ามใช้ `new Date`)
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

/** ป้ายจำนวนที่นั่ง — `seatsLabel` คืน null เมื่อไม่จำกัด ⇒ ที่นี่เลือกข้อความเอง */
function seatsText(e: PublicEvent): string {
  return seatsLabel(e.seats_remaining) ?? 'ไม่จำกัดจำนวน'
}
</script>

<template>
  <div>
    <!-- Editorial header -->
    <div class="mb-6">
      <p class="text-[11px] font-bold uppercase tracking-widest text-[#B91C1C] mb-1.5">
        <i class="bi bi-calendar-event mr-1"></i> Activities
      </p>
      <h1 class="text-2xl sm:text-3xl font-bold tracking-tight text-stone-900 leading-tight">กิจกรรม</h1>
      <p class="text-sm text-stone-500 mt-1.5">กิจกรรมที่สภานักเรียนประกาศให้ทั้งโรงเรียน</p>
    </div>

    <!-- แถบกรองช่วงเวลา -->
    <div class="flex flex-wrap items-center gap-2 mb-5">
      <div class="flex gap-1 p-1 bg-stone-100 rounded-xl">
        <button
          v-for="s in EVENT_SCOPES"
          :key="s"
          type="button"
          @click="switchScope(s)"
          class="px-3.5 py-2 rounded-lg text-sm font-medium transition"
          :class="scope === s ? 'bg-white border border-stone-200 text-[#B91C1C]' : 'text-stone-500 hover:text-stone-700'"
        >
          {{ SCOPE_LABELS[s] }}
        </button>
      </div>
      <!-- ตัวกรองหมวด (D4) — <select> เพราะ 7 หมวดจะเบียดแถวช่วงเวลาจนอ่านไม่ออกบนมือถือ -->
      <select
        v-model="category"
        aria-label="กรองตามหมวดกิจกรรม"
        data-testid="public-category-filter"
        class="rounded-xl border border-stone-200 bg-white px-3 py-2 text-sm text-stone-600 outline-none transition-colors focus:border-[#B91C1C] focus:ring-2 focus:ring-[#B91C1C]/10"
        @change="onCategoryChange"
      >
        <option value="">ทุกหมวด</option>
        <option v-for="c in EVENT_CATEGORIES" :key="c" :value="c">{{ CATEGORY_LABELS[c] }}</option>
      </select>

      <span class="text-sm text-stone-400 ml-auto tabular-nums">
        {{ total.toLocaleString('en-US') }} กิจกรรม
      </span>
    </div>

    <!-- โหลด: skeleton -->
    <div v-if="isLoading" class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
      <div v-for="n in 6" :key="n" class="page-card p-5 flex flex-col gap-3">
        <div class="h-5 w-20 bg-stone-100 animate-pulse rounded-md"></div>
        <div class="h-5 w-3/4 bg-stone-100 animate-pulse rounded"></div>
        <div class="h-4 w-full bg-stone-100 animate-pulse rounded"></div>
        <div class="h-4 w-5/6 bg-stone-100 animate-pulse rounded"></div>
        <div class="h-4 w-full bg-stone-100 animate-pulse rounded mt-auto"></div>
      </div>
    </div>

    <!-- ผิดพลาด -->
    <div v-else-if="error" class="border-2 border-dashed border-stone-200 rounded-2xl py-20 px-6 text-center">
      <i class="bi bi-wifi-off text-3xl text-stone-300 mb-3 inline-block"></i>
      <p class="text-stone-600 font-medium">{{ error }}</p>
      <button
        type="button"
        @click="load"
        class="mt-5 inline-flex items-center gap-2 rounded-lg bg-[#B91C1C] px-5 py-2.5 text-sm font-bold text-white hover:bg-[#991B1B] transition-colors"
      >
        <i class="bi bi-arrow-clockwise"></i> ลองอีกครั้ง
      </button>
    </div>

    <!-- ว่าง -->
    <div v-else-if="isEmpty" class="border border-dashed border-stone-200 rounded-2xl bg-white p-12 text-center text-stone-400">
      <div class="text-4xl mb-2"><i class="bi bi-calendar-x"></i></div>
      <p class="text-stone-500">{{ emptyText }}</p>
      <p v-if="scope === 'upcoming' && !category" class="text-sm text-stone-400 mt-1">
        รอสภาประกาศกิจกรรมใหม่ แล้วกลับมาเช็คอีกครั้ง
      </p>
      <!-- บอกทางออกเมื่อ "ว่างเพราะตัวกรอง" — นักเรียนที่เห็นจอว่างจะเลิกหาทันทีถ้าไม่มีปุ่มนี้ -->
      <button
        v-else-if="category"
        type="button"
        data-testid="clear-public-category-filter"
        class="mt-4 inline-flex items-center gap-2 rounded-lg bg-stone-100 px-4 py-2 text-sm font-semibold text-stone-700 transition-colors hover:bg-stone-200"
        @click="clearCategory"
      >
        <i class="bi bi-x-lg"></i> ล้างตัวกรองหมวด
      </button>
    </div>

    <div v-else class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
      <RouterLink
        v-for="e in events"
        :key="e.id"
        :to="{ name: 'event-detail', params: { id: e.id } }"
        class="page-card card-hover flex flex-col overflow-hidden"
      >
        <img
          v-if="e.cover_image_url"
          :src="e.cover_image_url"
          :alt="e.title"
          class="w-full h-36 object-cover bg-stone-100"
          loading="lazy"
        />

        <div class="p-5 flex flex-col flex-1">
          <div class="flex items-center justify-between gap-2 mb-2">
            <!-- สถานะที่ฉันสมัคร — แสดงเฉพาะเมื่อมีจริง (ไม่สมัคร/ยกเลิก = null จาก backend) -->
            <span
              v-if="e.my_registration_status"
              class="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] font-semibold"
              :class="e.my_registration_status === 'waitlisted'
                ? 'bg-amber-50 text-amber-700'
                : 'bg-emerald-50 text-emerald-700'"
            >
              <i :class="REGISTRATION_ICONS[e.my_registration_status]"></i>
              {{ REGISTRATION_LABELS[e.my_registration_status] }}
            </span>
            <span v-else class="text-[11px] text-stone-300">—</span>

            <span
              v-if="e.status === 'cancelled'"
              class="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-red-50 text-red-700 text-[11px] font-semibold"
            >
              <i class="bi bi-x-octagon"></i> ยกเลิกแล้ว
            </span>
            <span v-else-if="e.is_registration_open" class="text-[11px] font-semibold text-emerald-600">
              เปิดรับสมัคร
            </span>
            <span v-else class="text-[11px] text-stone-400">ปิดรับสมัครแล้ว</span>
          </div>

          <h3 class="font-semibold text-stone-900 leading-snug mb-1 line-clamp-2">{{ e.title }}</h3>
          <p v-if="e.description" class="text-sm text-stone-500 mb-2 line-clamp-2">{{ e.description }}</p>

          <span
            class="mb-3 inline-flex w-fit items-center gap-1 rounded-md bg-sky-50 px-2 py-0.5 text-[11px] font-semibold text-sky-700"
          >
            <i :class="`bi ${categoryIcon(e.category)}`"></i> {{ categoryLabel(e.category) }}
          </span>

          <div class="mt-auto pt-2 border-t border-stone-200 space-y-1.5 text-xs text-stone-500">
            <div>
              <i class="bi bi-clock mr-1"></i>{{ fmtDateTime(e.event_date) }}
            </div>
            <div v-if="e.location" class="truncate">
              <i class="bi bi-geo-alt mr-1"></i>{{ e.location }}
            </div>
            <div class="flex items-center justify-between gap-2">
              <span
                :class="e.seats_remaining === 0 && e.status !== 'cancelled' ? 'text-red-600 font-semibold' : ''"
              >
                <i class="bi bi-people mr-1"></i>{{ seatsText(e) }}
              </span>
              <span class="shrink-0 tabular-nums">{{ e.registered_count.toLocaleString('en-US') }} คน</span>
            </div>
          </div>
        </div>
      </RouterLink>
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
