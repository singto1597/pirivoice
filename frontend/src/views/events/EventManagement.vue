<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import Swal from 'sweetalert2'
import { BRAND } from '@/constants/brand'
import PaginationBar from '@/components/PaginationBar.vue'
import AppCard from '@/components/ui/AppCard.vue'
import AppChip from '@/components/ui/AppChip.vue'
import AppButton from '@/components/ui/AppButton.vue'
import AppEmptyState from '@/components/ui/AppEmptyState.vue'
import AppSheet from '@/components/ui/AppSheet.vue'
import IconButton from '@/components/ui/IconButton.vue'
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
 * 📅 จัดการกิจกรรม (สภา) — segment "จัดการ" ของแท็บกิจกรรม
 *
 * ⭐ **ไฟล์นี้ไม่มี modal แล้ว** (รอบ 4) — "สร้าง/แก้ไขกิจกรรม" และ "รายชื่อผู้สมัคร"
 *    ถูกย้ายเป็น **หน้าเต็มหน้า** (`EventForm.vue` · `EventRegistrations.vue`) เพราะ modal
 *    ที่มีฉากหลังกดปิดได้ ทำให้ข้อมูลที่ผู้ใช้พิมพ์ไว้หายทั้งก้อนด้วยการคลิกพลาดครั้งเดียว
 *    ⇒ ที่นี่เหลือแค่ปุ่มที่พาไปหน้าเหล่านั้น (`router.push`) ไม่มี state ของฟอร์มเหลืออยู่เลย
 *
 * ⚠️ **ถ้าจะเพิ่ม modal ในไฟล์นี้ ต้องอ่าน §14 / PR #33 ก่อน** — modal ที่เรนเดอร์ในไฟล์นี้
 *    จะติดอยู่ใน stacking context `relative z-10` ของ `.maincol` ⇒ `z-50` ถูกกักที่ชั้น 10
 *    แล้วแพ้ `<nav>` (`fixed z-40`) ที่เป็นพี่น้องกัน ⇒ แถบล่างทับ **และกลืนคลิกปุ่มยืนยัน**
 *    (ทางแก้คือ `<Teleport to="body">` — **กฎนี้ยังจริง ไม่ได้ถูกยกเลิก** · `AppSheet`
 *    ที่ใช้อยู่ในไฟล์นี้ทำ `Teleport to="body"` ให้แล้ว ⇒ ถ้าจะเขียน overlay เอง ต้องทำเอง)
 *    ⚠️ `AppSheet` เป็น **surface ของ "เลือก/ยืนยัน" เท่านั้น — ห้ามใส่ฟอร์ม** (skills #16)
 *
 * ⚠️ **สถานะ `live` (ค่าเริ่มต้น) = "ทุกอย่างที่ยังไม่ถูกลบ"** ไม่ใช่สถานะจริงของแถว
 *    ⇒ ป้ายจะขึ้น "ทั้งหมด" ไม่ใช่ "live" (ดู `LIST_STATUS_LABELS`)
 *
 * ⚠️ **กิจกรรมที่ `draft` เปิดดูหน้าสาธารณะไม่ได้ (404)** ⇒เมนู "ดูหน้าเว็บ" จึงแสดงเฉพาะ
 *    `published`/`cancelled` เท่านั้น ไม่ใช่ซ่อนเพื่อความสวยงาม แต่เพราะลิงก์จะพาไปเจอ
 *    "เปิดดูไม่ได้" ซึ่งดูเหมือนบั๊กทั้งที่ระบบถูก
 *
 * 🎯 **แถวละ 1 ปุ่มหลัก + `⋯`** (รอบ 4) — เดิมแถวหนึ่งมีได้ถึง **6 ปุ่ม** เรียงเท่ากันหมด
 *    ⇒ สภาต้องอ่านทุกปุ่มเพื่อหาปุ่มที่ต้องการ และปุ่มอันตราย (ลบ) อยู่ห่างกันแค่ 8px
 *    จากปุ่มที่กดบ่อยที่สุด · ตอนนี้ปุ่มหลัก = งานของสถานะนั้น และที่เหลืออยู่ใน `⋯`
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
 * ⚠️ เก็บเป็น `string` เปล่าเพราะค่ามาจากชิป ⇒ ด่านแคบอยู่ที่ `load()` ด้วย
 *    `isEventCategory()` ไม่ใช่ที่ type ของ ref
 *    · แบบเดียวกับ `subcategoryFilter` ใน `ReceivedIssues.vue` (`''` = ทุกหมวดย่อย)
 *
 * ⚠️ **ส่ง `''` ตรง ๆ ไม่ได้** — จะกลายเป็น `category=` ใน querystring ซึ่งไม่ตรง pattern
 *    ฝั่ง backend ⇒ **422** (ไม่ใช่ "ไม่กรอง") · ต้องแปลงเป็น `undefined` เสมอ
 */
const categoryFilter = ref('')
const isLoading = ref(true)
const hasError = ref(false)

/**
 * id ของแถวที่กำลังยิงคำขอ — ใช้แสดงสปินเนอร์เฉพาะแถวที่กด ไม่ล็อกทั้งตาราง
 *
 * ⚠️ รอบ 4 ถอด `actingKind` ออก: พอเหลือปุ่มหลักปุ่มเดียวต่อแถว "แถวไหนกำลังทำงาน"
 *    ก็ระบุได้ครบแล้ว ⇒ ตัวแปรที่เขียนแต่ไม่มีใครอ่านคือ state ที่ไม่มีวันถูกทดสอบ
 */
const actingId = ref<number | null>(null)

/** แถวที่เปิด `⋯` อยู่ — เก็บ *id* ไม่ใช่ตัว object เพื่อให้แถวที่โหลดใหม่แล้วยังชี้ถูก */
const menuForId = ref<number | null>(null)

const isEmpty = computed(() => !isLoading.value && !hasError.value && items.value.length === 0)

/** แถวที่กำลังเปิดเมนูอยู่ (null = ไม่มี) */
const menuEvent = computed(() => items.value.find((e) => e.id === menuForId.value) ?? null)

/**
 * ข้อความตอนว่าง — **ต้องแยกให้ออกว่า "ไม่มีของ" กับ "ตัวกรองซ่อนอยู่"**
 *
 * ⚠️ ทั้งสองกรณีแสดงผลเหมือนกันเป๊ะ (การ์ด 0 ใบ) แต่ความหมายตรงข้าม: กรณีหลังของ *มีอยู่จริง*
 *    ⇒ ข้อความกลาง ๆ อย่าง "ยังไม่มีกิจกรรมในระบบ" จะทำให้สภาตกใจแล้วไปสร้างซ้ำ
 */
const emptyTitle = computed(() =>
  categoryFilter.value ? 'ไม่พบกิจกรรมตามเงื่อนไข' : 'ยังไม่มีกิจกรรมในระบบ',
)

const emptyDescription = computed(() =>
  categoryFilter.value
    ? `ไม่มีกิจกรรมในหมวด "${categoryLabel(categoryFilter.value)}" ตามตัวกรองที่เลือก`
    : 'เริ่มจากกด "สร้างกิจกรรม" แล้วเผยแพร่ให้นักเรียนเห็น',
)

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

/**
 * เลือกหมวดจากชิป ⇒ กลับไปหน้า 1 เสมอ (ไม่งั้นอาจค้างอยู่หน้า 3 ของผลลัพธ์ชุดใหม่ที่สั้นกว่า)
 * ⚠️ แยกเป็นเมธอด — ห้ามเขียน `@click` หลายบรรทัดในเทมเพลต (skills #10)
 */
function pickCategory(c: string) {
  categoryFilter.value = c
  page.value = 1
  load()
}

function onPageChange(n: number) {
  page.value = n
  load()
}

/** แถวนี้กำลังยิงคำขออยู่ไหม — ใช้กับปุ่มหลักของแถว (แถวเดียวทำได้ทีละอย่าง) */
function isBusy(e: Event): boolean {
  return actingId.value === e.id
}

// ─────────────────────────────────────────────────────────────────────────────
// 1 ปุ่มหลัก + ⋯  —  ตารางตัดสินว่าแถวไหนได้อะไร
// ─────────────────────────────────────────────────────────────────────────────

/** สิ่งที่กดได้จากแถวหนึ่ง — `mutate` = ต้องยืนยันก่อน · `go` = ไปหน้าเต็ม */
type RowAction =
  | 'publish'
  | 'cancel'
  | 'delete'
  | 'restore'
  | 'edit'
  | 'registrations'
  | 'checkin'
  | 'view'

const ACTION_LABELS: Record<RowAction, string> = {
  publish: 'เผยแพร่',
  cancel: 'ยกเลิกกิจกรรม',
  delete: 'ลบกิจกรรม',
  restore: 'กู้คืน',
  edit: 'แก้ไข',
  registrations: 'รายชื่อผู้สมัคร',
  checkin: 'สแกนเช็คอิน',
  view: 'ดูหน้าเว็บ',
}

const ACTION_ICONS: Record<RowAction, string> = {
  publish: 'bi-megaphone',
  cancel: 'bi-x-octagon',
  delete: 'bi-trash3',
  restore: 'bi-arrow-counterclockwise',
  edit: 'bi-pencil',
  registrations: 'bi-list-check',
  checkin: 'bi-qr-code-scan',
  view: 'bi-box-arrow-up-right',
}

const MUTATING: RowAction[] = ['publish', 'cancel', 'delete', 'restore']

/**
 * ปุ่มหลักของแถว — **งานของสถานะนั้น ไม่ใช่ปุ่มที่อันตรายที่สุด**
 * · ถูกลบ → "กู้คืน" (เป็นสิ่งเดียวที่ทำได้ และเป็นทางออก ไม่ใช่ทางตัน)
 * · ฉบับร่าง → "เผยแพร่" (ร่างที่ยังไม่เผยแพร่ไม่ใช่กิจกรรม ⇒ งานหลักคือทำให้มันเกิด)
 * · อื่น ๆ → "รายชื่อผู้สมัคร" (งานที่สภาทำบ่อยที่สุดหลังเผยแพร่ — ดูว่าใครมา)
 */
function primaryOf(e: Event): RowAction {
  if (e.deleted_at) return 'restore'
  if (e.status === 'draft') return 'publish'
  return 'registrations'
}

/**
 * ที่เหลือใน `⋯` — **ไม่ใส่เมนูที่ผู้ใช้ไม่มีสิทธิ์/ใช้ไม่ได้** (ไม่ใช่ disabled)
 * ตัวที่ซ้ำกับปุ่มหลักถูกตัดออก เพราะรายการที่ซ้ำกันสองที่ทำให้ผู้ใช้สงสัยว่าต่างกันยังไง
 */
function menuOf(e: Event): RowAction[] {
  const primary = primaryOf(e)
  const all: RowAction[] = e.deleted_at
    ? ['restore']
    : e.status === 'draft'
      ? // ฉบับร่างยังไม่มีผู้สมัครโดยธรรมชาติ ⇒ ไม่มี "ผู้สมัคร"/"เช็คอิน"
        // และเปิดดูสาธารณะไม่ได้ (404) ⇒ ไม่มี "ดูหน้าเว็บ"
        ['publish', 'edit', 'delete']
      : ['registrations', 'checkin', 'edit', 'view', 'cancel', 'delete']
  return all.filter((a) => a !== primary)
}

/** รายการใน `⋯` ของแถวที่เปิดอยู่ — computed เพื่อไม่ต้องให้เทมเพลต narrow `Event | null` เอง */
const menuActions = computed<RowAction[]>(() =>
  menuEvent.value ? menuOf(menuEvent.value) : [],
)

function runRow(e: Event, action: RowAction) {
  menuForId.value = null
  if (MUTATING.includes(action)) {
    void runAction(e, action as 'publish' | 'cancel' | 'delete' | 'restore')
    return
  }
  if (action === 'edit') router.push({ name: 'event-edit', params: { id: e.id } })
  else if (action === 'registrations') router.push({ name: 'event-registrations', params: { id: e.id } })
  else if (action === 'checkin') router.push({ name: 'event-check-in', params: { id: e.id } })
  else if (action === 'view') router.push({ name: 'event-detail', params: { id: e.id } })
}

/**
 * ปุ่มใน `⋯` — อ่านแถวที่เปิดอยู่จาก `menuForId` เอง แทนการรับ `Event` จากเทมเพลต
 * ⚠️ เพราะในเทมเพลต `menuEvent` เป็น `Event | null` และการ narrow ผ่าน `v-if` **ไม่รอด**
 *    เมื่อส่งเข้า arrow function ของ `@click` ⇒ `vue-tsc` จะฟ้อง (strict, ไม่มี `any`)
 */
function runMenuAction(action: RowAction) {
  const e = menuEvent.value
  if (!e) return
  runRow(e, action)
}

async function runAction(e: Event, kind: 'publish' | 'cancel' | 'delete' | 'restore') {
  if (actingId.value !== null) return
  actingId.value = e.id
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
  }
}

function capacityText(e: Event): string {
  return e.capacity === null ? 'ไม่จำกัด' : `${e.capacity.toLocaleString('en-US')} ที่นั่ง`
}
</script>

<template>
  <div class="mx-auto max-w-5xl space-y-4 pb-4">
    <div class="flex items-start justify-between gap-4">
      <!-- ⚠️ ไม่มี `<h1>`/eyebrow — `AppHeader` แสดง "จัดการกิจกรรม" ให้แล้ว (routeTitles) -->
      <p class="text-sm text-ink-2">
        สร้างกิจกรรม เปิดรับสมัคร และดูรายชื่อผู้เข้าร่วม
      </p>
      <!-- ➕ เดสก์ท็อปเท่านั้น — มือถือได้ FAB `+` (`fab: 'event'`) -->
      <AppButton
        data-testid="add-event"
        class="hidden lg:inline-flex"
        :to="{ name: 'event-create' }"
      >
        <template #icon><i class="bi bi-plus-lg" aria-hidden="true" /></template>
        สร้างกิจกรรม
      </AppButton>
    </div>

    <!-- 🏷️ สถานะ + หมวด เป็นชิปเลื่อนแนวนอน (เดิมเป็นกลุ่มปุ่มที่ตัดบรรทัดบนมือถือ) -->
    <div class="chip-row">
      <AppChip
        v-for="s in EVENT_LIST_STATUSES"
        :key="s"
        :label="LIST_STATUS_LABELS[s]"
        :active="statusFilter === s"
        @click="switchStatus(s)"
      />
      <span class="mx-0.5 h-6 w-px shrink-0 self-center bg-line" aria-hidden="true" />
      <AppChip label="ทุกหมวด" :active="categoryFilter === ''" @click="pickCategory('')" />
      <AppChip
        v-for="c in EVENT_CATEGORIES"
        :key="c"
        :label="CATEGORY_LABELS[c]"
        :active="categoryFilter === c"
        @click="pickCategory(c)"
      />
    </div>

    <p class="text-sm text-ink-3 tabular-nums">{{ total.toLocaleString('en-US') }} กิจกรรม</p>

    <!-- โหลด: skeleton -->
    <div v-if="isLoading" class="space-y-3">
      <AppCard v-for="n in 4" :key="n" class="animate-pulse">
        <div class="mb-3 h-5 w-24 rounded bg-canvas"></div>
        <div class="mb-2 h-5 w-2/3 rounded bg-canvas"></div>
        <div class="h-4 w-1/2 rounded bg-canvas"></div>
      </AppCard>
    </div>

    <!-- ผิดพลาด -->
    <AppCard v-else-if="hasError" :padded="false" class="py-4">
      <AppEmptyState
        icon="bi-wifi-off"
        title="โหลดรายการกิจกรรมไม่สำเร็จ"
        description="อาจเป็นเพราะการเชื่อมต่อขัดข้อง ลองใหม่อีกครั้งได้เลย"
      >
        <AppButton variant="secondary" @click="load">
          <template #icon><i class="bi bi-arrow-clockwise" aria-hidden="true" /></template>
          ลองใหม่
        </AppButton>
      </AppEmptyState>
    </AppCard>

    <!-- ว่าง — บอกทางออกเมื่อ "ว่างเพราะตัวกรอง" ไม่งั้นสภาจะอ่านว่า "กิจกรรมหายไปหมด"
         แล้วไปสร้างซ้ำ ซึ่งเป็นความเสียหายจริง (ไม่ใช่แค่ข้อความไม่สวย) -->
    <AppCard v-else-if="isEmpty" :padded="false" class="py-4">
      <AppEmptyState
        icon="bi-calendar-plus"
        :title="emptyTitle"
        :description="emptyDescription"
      >
        <AppButton v-if="categoryFilter" variant="secondary" @click="pickCategory('')">
          <template #icon><i class="bi bi-x-circle" aria-hidden="true" /></template>
          ล้างตัวกรองหมวด
        </AppButton>
        <AppButton v-else :to="{ name: 'event-create' }">
          <template #icon><i class="bi bi-plus-lg" aria-hidden="true" /></template>
          สร้างกิจกรรม
        </AppButton>
      </AppEmptyState>
    </AppCard>

    <!-- รายการ -->
    <div v-else class="space-y-3">
      <AppCard v-for="e in items" :key="e.id">
        <div class="flex items-start justify-between gap-3">
          <div class="min-w-0 flex-1">
            <!-- สถานะ + ตัวเลข -->
            <div class="mb-1.5 flex flex-wrap items-center gap-2">
              <span
                class="inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-[11px] font-semibold"
                :class="{
                  'bg-canvas text-ink-2': e.status === 'draft',
                  'bg-ok-soft text-ok': e.status === 'published',
                  'bg-danger-soft text-danger': e.status === 'cancelled',
                }"
              >
                <i :class="`bi ${STATUS_ICONS[e.status]}`" aria-hidden="true" />
                {{ STATUS_LABELS[e.status] }}
              </span>
              <!-- หมวด (D4) — ใช้ categoryLabel/categoryIcon ไม่ใช่ CATEGORY_LABELS[c] ตรง ๆ
                   เพราะ e.category เป็น string หลวม (backend อาจมีหมวดที่เราไม่รู้จัก) -->
              <span
                class="inline-flex items-center gap-1 rounded-md bg-canvas px-2 py-0.5 text-[11px] font-semibold text-ink-2"
              >
                <i :class="`bi ${categoryIcon(e.category)}`" aria-hidden="true" />
                {{ categoryLabel(e.category) }}
              </span>
              <span
                v-if="e.deleted_at"
                class="inline-flex items-center gap-1 rounded-md bg-warn-soft px-2 py-0.5 text-[11px] font-semibold text-warn"
              >
                <i class="bi bi-trash3" aria-hidden="true" /> ถูกลบ
              </span>
              <span class="text-[11px] text-ink-3 tabular-nums">
                สมัคร {{ e.registered_count.toLocaleString('en-US') }} คน
                <template v-if="e.waitlisted_count > 0">
                  · รอคิว {{ e.waitlisted_count.toLocaleString('en-US') }} คน
                </template>
              </span>
            </div>

            <h3 class="font-semibold leading-snug break-words text-ink-1">{{ e.title }}</h3>

            <div class="mt-1.5 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-ink-2">
              <span><i class="bi bi-clock mr-1" aria-hidden="true" />{{ fmtDateTime(e.event_date) }}</span>
              <span v-if="e.location" class="min-w-0 truncate">
                <i class="bi bi-geo-alt mr-1" aria-hidden="true" />{{ e.location }}
              </span>
              <span><i class="bi bi-people mr-1" aria-hidden="true" />{{ capacityText(e) }}</span>
              <span v-if="e.created_by_name">
                <i class="bi bi-person mr-1" aria-hidden="true" />สร้างโดย {{ e.created_by_name }}
              </span>
            </div>
          </div>

          <!-- 🎯 1 ปุ่มหลัก + ⋯ — ปุ่มอันตราย (ลบ) ไม่ได้อยู่ข้างปุ่มที่กดบ่อยที่สุดอีกแล้ว -->
          <div class="flex shrink-0 items-center gap-1">
            <AppButton
              size="sm"
              :loading="isBusy(e)"
              :disabled="actingId !== null"
              :data-testid="`event-primary-${e.id}`"
              @click="runRow(e, primaryOf(e))"
            >
              <template #icon>
                <i :class="`bi ${ACTION_ICONS[primaryOf(e)]}`" aria-hidden="true" />
              </template>
              {{ ACTION_LABELS[primaryOf(e)] }}
            </AppButton>

            <IconButton
              v-if="menuOf(e).length"
              icon="bi-three-dots"
              :label="`ตัวเลือกอื่นของ ${e.title}`"
              :data-testid="`event-menu-${e.id}`"
              @click="menuForId = e.id"
            />
          </div>
        </div>
      </AppCard>
    </div>

    <PaginationBar
      :total="total"
      :page="page"
      :page-size="PAGE_SIZE"
      :loading="isLoading"
      @page-change="onPageChange"
    />

    <!-- 🪟 ⋯ — `AppSheet` ทำ `<Teleport to="body">` ให้แล้ว (skills #9)
         ⚠️ เป็น surface ของ "เลือก/ยืนยัน" เท่านั้น — ไม่มีฟอร์มในนี้ (skills #16) -->
    <AppSheet
      :model-value="menuForId !== null"
      :title="menuEvent?.title"
      description="เลือกสิ่งที่ต้องการทำกับกิจกรรมนี้"
      @update:model-value="menuForId = null"
    >
      <div v-if="menuActions.length" class="pb-2">
        <!-- ⚠️ ไม่มี "ลบ" อยู่ชิดปุ่มที่กดบ่อย — และปุ่มอันตรายเป็น *ข้อความแดงล้วน*
             ไม่ใช่ปุ่ม outline แดง (ทั้งหน้าจะอ่านว่า "อันตราย" พร้อมกันหมด) -->
        <button
          v-for="a in menuActions"
          :key="a"
          type="button"
          class="flex w-full items-center gap-3 rounded-control px-3 py-3 text-left text-body transition-colors hover:bg-canvas focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
          :class="a === 'delete' ? 'text-danger' : 'text-ink-1'"
          :data-testid="`event-action-${a}`"
          @click="runMenuAction(a)"
        >
          <i
            :class="`bi ${ACTION_ICONS[a]} text-lg ${a === 'delete' ? 'text-danger' : 'text-ink-2'}`"
            aria-hidden="true"
          />
          <span class="font-medium">{{ ACTION_LABELS[a] }}</span>
        </button>
      </div>
    </AppSheet>
  </div>
</template>
