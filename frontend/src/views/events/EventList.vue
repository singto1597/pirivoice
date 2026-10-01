<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import PaginationBar from '@/components/PaginationBar.vue'
import AppCard from '@/components/ui/AppCard.vue'
import AppChip from '@/components/ui/AppChip.vue'
import AppButton from '@/components/ui/AppButton.vue'
import AppEmptyState from '@/components/ui/AppEmptyState.vue'
import { useAuthStore } from '@/stores/auth'
// 🕐 เวลามาจากโมดูลกลางเท่านั้น — **ห้ามประกาศซ้ำในไฟล์นี้** (เดิมก๊อปอยู่ 4 ไฟล์แล้วเพี้ยนจากกัน
//    ⇒ ลบ `fmtDateTime` ที่เขียนมือในไฟล์นี้ทิ้งในรอบ 4 · ค่าที่ได้เหมือนเดิมเพราะ
//      `src/datetime.ts` ใช้ `Asia/Bangkok` + พ.ศ. ชุดเดียวกัน และมีเทสต์ 17 เคสคุมอยู่)
import { fmtDateTime } from '@/datetime'
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
 * 📅 รายการกิจกรรม (segment "ทั้งหมด") — เห็นเฉพาะที่สภาจะ "เผยแพร่แล้ว"
 *
 * ⚠️ **ห้ามเทียบเวลาที่นี่** — `is_registration_open` มาจาก server (คำนวณใน SQL) เพราะ
 *    นาฬิกาเครื่องผู้ใช้อาจเพี้ยนคนละโซน และกติกา "ปิดรับเมื่อไหร่" เป็นกติกาของ *ระบบ*
 *    ไม่ใช่การแสดงผล (ดู docstring ใน `types/event.ts`)
 *
 * ⚠️ กิจกรรมที่ถูก **ยกเลิก** ยังอยู่ในลิสต์นี้โดยเจตนา (status='cancelled') — การซ่อนไปเลย
 *    ทำให้คนที่เห็นโปสเตอร์แล้วมาหาไม่เจอ · ที่หายไปจริงคือ **ฉบับร่าง** และ **ที่ถูกลบ**
 *    ซึ่ง backend คืน 404 อยู่แล้ว
 *
 * 🔴 **ไม่มี `<h1>` และไม่มี eyebrow ในไฟล์นี้** — `<h1>` ของหน้าอยู่ที่ `AppHeader`
 *    และ `routeTitles.events = 'กิจกรรม'` แสดงอยู่แล้ว (R0.3) ⇒ ชื่อเรื่องซ้ำสองที่
 *    ⚠️ และ **ห้ามใส่ `uppercase tracking-*` กับข้อความไทย** — ภาษาไทยไม่มีตัวพิมพ์ใหญ่
 *
 * ➕ **ปุ่มสร้างกิจกรรมมีสองที่ตามขนาดจอ — ไม่ใช่ของซ้ำกัน** (แบบเดียวกับหน้าบอร์ด R4.1):
 *    · มือถือ → **FAB** (`fab: 'event'` ใน `route.meta` ⇒ `MainLayout` วาดให้เมื่อมีสิทธิ์)
 *    · เดสก์ท็อป → ปุ่มในหัวหน้า เพราะ `AppFab` เป็น `lg:hidden` โดยตัวมันเอง
 */
const PAGE_SIZE = 12

const authStore = useAuthStore()
const canManage = computed(() => authStore.hasPermission('MANAGE_EVENTS'))

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
const emptyTitle = computed(() =>
  category.value ? 'ไม่พบกิจกรรมตามเงื่อนไข' : 'ยังไม่มีกิจกรรมในช่วงนี้',
)

const emptyDescription = computed(() => {
  if (category.value) return `ไม่มีกิจกรรมหมวด "${categoryLabel(category.value)}" ในช่วงเวลาที่เลือก`
  return scope.value === 'past'
    ? 'ยังไม่มีกิจกรรมที่ผ่านไปแล้ว'
    : 'รอสภาประกาศกิจกรรมใหม่ แล้วกลับมาเช็คอีกครั้ง'
})

onMounted(load)

function switchScope(s: EventScope) {
  if (scope.value === s) return
  scope.value = s
  page.value = 1
  load()
}

/**
 * เลือกหมวดจากชิป
 *
 * ⚠️ แยกเป็นเมธอด **ห้ามเขียนเป็น `@click` หลายบรรทัดในเทมเพลต** — `npm run format`
 *    เคยลอก `;` ระหว่างสอง statement ใน inline handler จน build แตก (skills #10)
 */
function pickCategory(c: string) {
  category.value = c
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

/** ป้ายจำนวนที่นั่ง — `seatsLabel` คืน null เมื่อไม่จำกัด ⇒ ที่นี่เลือกข้อความเอง */
function seatsText(e: PublicEvent): string {
  return seatsLabel(e.seats_remaining) ?? 'ไม่จำกัดจำนวน'
}

/** ที่นั่งเต็ม (และยังไม่ถูกยกเลิก) — ใช้เน้นด้วยสีแดง */
function isFull(e: PublicEvent): boolean {
  return e.seats_remaining === 0 && e.status !== 'cancelled'
}
</script>

<template>
  <div class="mx-auto max-w-5xl space-y-4 pb-4">
    <div class="flex items-start justify-between gap-4">
      <!-- ⚠️ ไม่มี `<h1>`/eyebrow — `AppHeader` แสดง "กิจกรรม" ให้แล้ว (R0.3) -->
      <p class="text-sm text-ink-2">กิจกรรมที่สภานักเรียนประกาศให้ทั้งโรงเรียน</p>
      <!-- ➕ เดสก์ท็อปเท่านั้น — มือถือได้ FAB `+` แทน (ปุ่มเดียวกันสองที่ = ของซ้ำ) -->
      <AppButton
        v-if="canManage"
        data-testid="add-event"
        class="hidden lg:inline-flex"
        :to="{ name: 'event-create' }"
      >
        <template #icon><i class="bi bi-plus-lg" aria-hidden="true" /></template>
        สร้างกิจกรรม
      </AppButton>
    </div>

    <!-- 🏷️ ช่วงเวลา + หมวด — เป็นชิปที่เลื่อนแนวนอนได้ ไม่ตัดบรรทัด
         ⚠️ เดิมหมวดเป็น `<select>` · เปลี่ยนเป็นชิปได้เพราะ 7 หมวดอยู่ในแถวที่เลื่อนได้
         และผู้ใช้เห็นตัวเลือกทั้งหมดในพริบตาเดียว ไม่ต้องกดเปิดดรอปดาวน์ -->
    <div class="chip-row">
      <AppChip
        v-for="s in EVENT_SCOPES"
        :key="s"
        :label="SCOPE_LABELS[s]"
        :active="scope === s"
        @click="switchScope(s)"
      />
      <span class="mx-0.5 h-6 w-px shrink-0 self-center bg-line" aria-hidden="true" />
      <AppChip label="ทุกหมวด" :active="category === ''" @click="clearCategory" />
      <!-- ⚠️ ชิปทุกตัวมี **ชื่อไทยของตัวเอง** ⇒ ตัวเลือกที่ทนที่สุดคือ role+ชื่อ ไม่ใช่ testid
           (ไม่ใส่ `data-testid` ซ้ำกัน 7 ตัว ซึ่งทำให้ selector ไม่ unique โดยไม่มีใครรู้) -->
      <AppChip
        v-for="c in EVENT_CATEGORIES"
        :key="c"
        :label="CATEGORY_LABELS[c]"
        :active="category === c"
        @click="pickCategory(c)"
      />
    </div>

    <p class="text-sm text-ink-3 tabular-nums">
      {{ total.toLocaleString('en-US') }} กิจกรรม
    </p>

    <!-- โหลด: skeleton การ์ด -->
    <div v-if="isLoading" class="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
      <AppCard v-for="n in 6" :key="n" class="animate-pulse">
        <div class="mb-3 h-5 w-20 rounded bg-canvas"></div>
        <div class="mb-2 h-5 w-3/4 rounded bg-canvas"></div>
        <div class="mb-1.5 h-4 w-full rounded bg-canvas"></div>
        <div class="h-4 w-5/6 rounded bg-canvas"></div>
      </AppCard>
    </div>

    <!-- ผิดพลาด — 「ไม่มีการ์ดเส้นประ」 (AppEmptyState ไม่มี border-dashed โดยเจตนา) -->
    <AppCard v-else-if="error" :padded="false" class="py-4">
      <AppEmptyState icon="bi-wifi-off" title="โหลดกิจกรรมไม่สำเร็จ" :description="error">
        <AppButton variant="secondary" @click="load">
          <template #icon><i class="bi bi-arrow-clockwise" aria-hidden="true" /></template>
          ลองใหม่
        </AppButton>
      </AppEmptyState>
    </AppCard>

    <!-- ว่าง — แยก "ยังไม่มีของ" กับ "กรองแล้วไม่เจอ" (คนละสาเหตุ คนละทางออก) -->
    <AppCard v-else-if="isEmpty" :padded="false" class="py-4">
      <AppEmptyState
        icon="bi-calendar-x"
        :title="emptyTitle"
        :description="emptyDescription"
      >
        <AppButton
          v-if="category"
          variant="secondary"
          data-testid="clear-public-category-filter"
          @click="clearCategory"
        >
          <template #icon><i class="bi bi-x-circle" aria-hidden="true" /></template>
          ล้างตัวกรองหมวด
        </AppButton>
      </AppEmptyState>
    </AppCard>

    <div v-else class="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
      <!-- ⚠️ การ์ดทั้งใบเป็นทางเข้าเดียว ⇒ `AppCard interactive` + `<RouterLink>` เป็น *ลูก* -->
      <AppCard v-for="e in events" :key="e.id" :padded="false" interactive>
        <RouterLink
          :to="{ name: 'event-detail', params: { id: e.id } }"
          class="flex h-full flex-col rounded-card focus-visible:ring-2 focus-visible:ring-brand focus-visible:outline-none"
        >
          <img
            v-if="e.cover_image_url"
            :src="e.cover_image_url"
            :alt="e.title"
            class="h-32 w-full rounded-t-card bg-canvas object-cover"
            loading="lazy"
          />

          <div class="flex flex-1 flex-col p-4">
            <div class="mb-2 flex items-center justify-between gap-2">
              <!-- สถานะที่ฉันสมัคร — แสดงเฉพาะเมื่อมีจริง (ไม่สมัคร/ยกเลิก = null จาก backend)
                   ⭐ นี่คือคำตอบของ "กิจกรรมที่ฉันสมัคร" โดยไม่ต้องมีตัวกรองแยก —
                      ดูเหตุผลที่ไม่มี segment "ของฉัน" ใน `constants/nav.ts` -->
              <span
                v-if="e.my_registration_status"
                class="inline-flex items-center gap-1 rounded-md bg-ok-soft px-2 py-0.5 text-[11px] font-semibold text-ok"
                :class="e.my_registration_status === 'waitlisted' && 'bg-warn-soft text-warn'"
              >
                <i :class="REGISTRATION_ICONS[e.my_registration_status]" aria-hidden="true" />
                {{ REGISTRATION_LABELS[e.my_registration_status] }}
              </span>
              <span v-else class="text-[11px] text-ink-3">—</span>

              <span
                v-if="e.status === 'cancelled'"
                class="inline-flex shrink-0 items-center gap-1 rounded-md bg-danger-soft px-2 py-0.5 text-[11px] font-semibold text-danger"
              >
                <i class="bi bi-x-octagon" aria-hidden="true" /> ยกเลิกแล้ว
              </span>
              <span
                v-else-if="e.is_registration_open"
                class="shrink-0 text-[11px] font-semibold text-ok"
              >
                เปิดรับสมัคร
              </span>
              <span v-else class="shrink-0 text-[11px] text-ink-3">ปิดรับสมัครแล้ว</span>
            </div>

            <h3 class="mb-1 line-clamp-2 leading-snug font-semibold text-ink-1">{{ e.title }}</h3>
            <p v-if="e.description" class="mb-2 line-clamp-2 text-sm text-ink-2">
              {{ e.description }}
            </p>

            <span
              class="mb-3 inline-flex w-fit items-center gap-1 rounded-md bg-canvas px-2 py-0.5 text-[11px] font-semibold text-ink-2"
            >
              <i :class="`bi ${categoryIcon(e.category)}`" aria-hidden="true" />
              {{ categoryLabel(e.category) }}
            </span>

            <div class="mt-auto space-y-1.5 border-t border-line pt-2 text-xs text-ink-2">
              <div><i class="bi bi-clock mr-1" aria-hidden="true" />{{ fmtDateTime(e.event_date) }}</div>
              <div v-if="e.location" class="truncate">
                <i class="bi bi-geo-alt mr-1" aria-hidden="true" />{{ e.location }}
              </div>
              <div class="flex items-center justify-between gap-2">
                <span :class="isFull(e) ? 'font-semibold text-danger' : ''">
                  <i class="bi bi-people mr-1" aria-hidden="true" />{{ seatsText(e) }}
                </span>
                <span class="shrink-0 tabular-nums">
                  {{ e.registered_count.toLocaleString('en-US') }} คน
                </span>
              </div>
            </div>
          </div>
        </RouterLink>
      </AppCard>
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
