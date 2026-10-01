<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import Swal from 'sweetalert2'
import { BRAND, WARN } from '@/constants/brand'
import { fmtDateTime } from '@/datetime'
import PaginationBar from '@/components/PaginationBar.vue'
import {
  listAnnouncements,
  createAnnouncement,
  updateAnnouncement,
  deleteAnnouncement,
  restoreAnnouncement,
  retireAnnouncement,
  unretireAnnouncement,
} from '@/services/announcement'
import type {
  Announcement,
  AnnouncementPriority,
  AnnouncementStatus,
} from '@/types/announcement'

// 📣 หน้าจัดการประกาศหน้า Landing Page (ต้องมีสิทธิ์ MANAGE_ANNOUNCEMENTS)
// - ลบ = soft delete → ยังเห็นได้เมื่อสลับตัวกรองเป็น "ถูกลบ" แล้วกู้คืนได้
// - ปลดระวาง = เอาออกจากหน้าเว็บเพราะหมดอายุ แต่ **ไม่ใช่การลบ** เก็บไว้เป็นประวัติ
//   (คนละเจตนากับการลบ — ดู doUnretire/confirmRetire ด้านล่าง)
// - ประกาศที่ seed มาก่อนมีฟีเจอร์นี้จะไม่มีชื่อผู้ประกาศ (created_by = null) → แสดง "—" ไม่ใช่พัง

const PAGE_SIZE = 20

const PRIORITY_OPTIONS: { value: AnnouncementPriority; label: string; hint: string }[] = [
  { value: 'normal', label: 'ปกติ', hint: 'สีเทา — ประกาศทั่วไป' },
  { value: 'high', label: 'สำคัญ', hint: 'สีส้ม — ควรอ่าน' },
  { value: 'urgent', label: 'ด่วนมาก', hint: 'สีแดงกะพริบ — ขึ้นบนสุดเสมอ' },
]

const PRIORITY_STYLE: Record<AnnouncementPriority, { dot: string; badge: string; label: string }> = {
  urgent: {
    dot: 'bg-brand animate-pulse',
    badge: 'bg-brand/10 text-brand ring-1 ring-brand/20',
    label: 'ด่วนมาก',
  },
  high: {
    dot: 'bg-[#D97706]',
    badge: 'bg-amber-100 text-amber-700 ring-1 ring-amber-200',
    label: 'สำคัญ',
  },
  normal: {
    dot: 'bg-stone-400',
    badge: 'bg-stone-100 text-stone-600 ring-1 ring-stone-200',
    label: 'ปกติ',
  },
}

const STATUS_TABS: { value: AnnouncementStatus; label: string }[] = [
  { value: 'active', label: 'ใช้งานอยู่' },
  { value: 'retired', label: 'ปลดระวางแล้ว' },
  { value: 'deleted', label: 'ถูกลบ' },
  { value: 'all', label: 'ทั้งหมด' },
]

/** สถานะที่แท้จริงของแถวหนึ่ง — ใช้แยกการแสดงผล 3 ทาง (ไม่ใช่ binary deleted/ไม่ deleted) */
function rowState(a: Announcement): 'active' | 'retired' | 'deleted' {
  if (a.deleted_at) return 'deleted'
  if (a.retired_at) return 'retired'
  return 'active'
}

// ===== ข้อมูล + การโหลด =====
const items = ref<Announcement[]>([])
const total = ref(0)
const page = ref(1)
const statusFilter = ref<AnnouncementStatus>('active')
const isLoading = ref(true)
const hasError = ref(false)

async function load() {
  isLoading.value = true
  hasError.value = false
  try {
    const res = await listAnnouncements({
      status: statusFilter.value,
      limit: PAGE_SIZE,
      offset: (page.value - 1) * PAGE_SIZE,
    })
    items.value = res.items
    total.value = res.total
  } catch (e) {
    hasError.value = true
    items.value = []
    total.value = 0
    Swal.fire({ icon: 'error', title: 'โหลดประกาศไม่สำเร็จ', text: errorText(e) })
  } finally {
    isLoading.value = false
  }
}
onMounted(load)

function errorText(e: unknown): string {
  if (typeof e === 'string') return e
  if (e instanceof Error) return e.message
  return 'เกิดข้อผิดพลาดที่ไม่รู้จัก'
}

function changeStatus(s: AnnouncementStatus) {
  if (statusFilter.value === s) return
  statusFilter.value = s
  page.value = 1
  void load()
}

function changePage(p: number) {
  page.value = p
  void load()
}

// ===== Modal เพิ่ม/แก้ไข =====
const modalOpen = ref(false)
const modalMode = ref<'add' | 'edit'>('add')
const editingId = ref<number | null>(null)
const saving = ref(false)
const saveError = ref('')

const form = reactive<{ message: string; priority: AnnouncementPriority; link: string }>({
  message: '',
  priority: 'normal',
  link: '',
})

function openAdd() {
  modalMode.value = 'add'
  editingId.value = null
  form.message = ''
  form.priority = 'normal'
  form.link = ''
  saveError.value = ''
  modalOpen.value = true
}

function openEdit(a: Announcement) {
  modalMode.value = 'edit'
  editingId.value = a.id
  form.message = a.message
  form.priority = a.priority
  form.link = a.link ?? ''
  saveError.value = ''
  modalOpen.value = true
}

function closeModal() {
  if (saving.value) return
  modalOpen.value = false
}

const canSubmit = computed(() => form.message.trim().length > 0 && !saving.value)

async function submitForm() {
  const message = form.message.trim()
  if (!message) {
    saveError.value = 'กรอกข้อความประกาศก่อนบันทึก'
    return
  }
  // ลิงก์ว่าง → ส่ง null (สั่งล้างค่า) ไม่ใช่สตริงว่าง
  const link = form.link.trim() || null

  saving.value = true
  saveError.value = ''
  try {
    if (modalMode.value === 'add') {
      await createAnnouncement({ message, priority: form.priority, link })
      Swal.fire({
        icon: 'success',
        title: 'ประกาศแล้ว',
        text: 'ประกาศขึ้นหน้า Landing Page ทันที',
        timer: 1500,
        showConfirmButton: false,
      })
    } else if (editingId.value !== null) {
      await updateAnnouncement(editingId.value, { message, priority: form.priority, link })
      Swal.fire({ icon: 'success', title: 'บันทึกแล้ว', timer: 1000, showConfirmButton: false })
    }
    modalOpen.value = false
    await load()
  } catch (e) {
    // เก็บไว้ในฟอร์ม ไม่ปิด modal — ผู้ใช้จะได้แก้แล้วกดซ้ำได้เลย
    saveError.value = errorText(e)
  } finally {
    saving.value = false
  }
}

// ===== ลบ / กู้คืน / ปลดระวาง =====
//   `actingId` = แถวที่กำลังทำอะไรอยู่ (ใช้ disable ทุกปุ่มของแถวนั้น)
//   `actingKind` = กำลังทำ action ไหน — จำเป็นเพราะแถวที่ใช้งานอยู่มี **สอง** ปุ่มที่
//   เขียน DB ได้ (ปลดระวาง + ลบ) ⇒ ถ้าดูแค่ actingId ทั้งคู่จะหมุนพร้อมกัน
type ActionKind = 'delete' | 'restore' | 'retire' | 'unretire'
const actingId = ref<number | null>(null)
const actingKind = ref<ActionKind | null>(null)

/** ปุ่มนี้กำลังทำงานอยู่หรือเปล่า — ใช้ตัดสินว่าจะโชว์สปินเนอร์ */
function busy(a: Announcement, kind: ActionKind): boolean {
  return actingId.value === a.id && actingKind.value === kind
}

async function confirmDelete(a: Announcement) {
  const { isConfirmed } = await Swal.fire({
    title: 'ลบประกาศนี้?',
    text: 'ประกาศจะหายจากหน้า Landing Page ทันที (กู้คืนได้ภายหลัง)',
    icon: 'warning',
    showCancelButton: true,
    confirmButtonText: 'ลบประกาศ',
    confirmButtonColor: BRAND,
    cancelButtonText: 'ยกเลิก',
  })
  if (!isConfirmed) return

  actingId.value = a.id
  actingKind.value = 'delete'
  try {
    await deleteAnnouncement(a.id)
    Swal.fire({
      icon: 'success',
      title: 'ลบประกาศแล้ว',
      text: 'กู้คืนได้จากตัวกรอง "ถูกลบ"',
      timer: 1800,
      showConfirmButton: false,
    })
    // ลบรายการสุดท้ายของหน้าสุดท้าย → ถอยกลับหนึ่งหน้า ไม่งั้นเจอหน้าว่าง
    if (items.value.length === 1 && page.value > 1) page.value -= 1
    await load()
  } catch (e) {
    Swal.fire({ icon: 'error', title: 'ลบไม่สำเร็จ', text: errorText(e) })
  } finally {
    actingId.value = null
    actingKind.value = null
  }
}

async function doRestore(a: Announcement) {
  const { isConfirmed } = await Swal.fire({
    title: 'กู้คืนประกาศนี้?',
    text: 'ประกาศจะกลับไปแสดงบนหน้า Landing Page อีกครั้ง',
    icon: 'question',
    showCancelButton: true,
    confirmButtonText: 'กู้คืน',
    confirmButtonColor: BRAND,
    cancelButtonText: 'ยกเลิก',
  })
  if (!isConfirmed) return

  actingId.value = a.id
  actingKind.value = 'restore'
  try {
    await restoreAnnouncement(a.id)
    Swal.fire({ icon: 'success', title: 'กู้คืนแล้ว', timer: 1200, showConfirmButton: false })
    await load()
  } catch (e) {
    Swal.fire({ icon: 'error', title: 'กู้คืนไม่สำเร็จ', text: errorText(e) })
  } finally {
    actingId.value = null
    actingKind.value = null
  }
}

// ===== ปลดระวาง / นำกลับมาใช้ =====
//   ตั้งใจให้ข้อความต่างจากการลบชัดเจน — ผู้ใช้ต้องเข้าใจว่า "ของยังอยู่ แค่เลิกใช้"
async function confirmRetire(a: Announcement) {
  const { isConfirmed } = await Swal.fire({
    title: 'ปลดระวางประกาศนี้?',
    text: 'ประกาศจะหายจากหน้า Landing Page แต่ยังเก็บไว้ดูย้อนหลังได้ — ต่างจากการลบนะ',
    icon: 'question',
    showCancelButton: true,
    confirmButtonText: 'ปลดระวาง',
    confirmButtonColor: WARN,
    cancelButtonText: 'ยกเลิก',
  })
  if (!isConfirmed) return

  actingId.value = a.id
  actingKind.value = 'retire'
  try {
    await retireAnnouncement(a.id)
    Swal.fire({
      icon: 'success',
      title: 'ปลดระวางแล้ว',
      text: 'ดูย้อนหลังได้จากตัวกรอง "ปลดระวางแล้ว"',
      timer: 1800,
      showConfirmButton: false,
    })
    // ปลดรายการสุดท้ายของหน้าสุดท้าย → ถอยกลับหนึ่งหน้า ไม่งั้นเจอหน้าว่าง
    if (items.value.length === 1 && page.value > 1) page.value -= 1
    await load()
  } catch (e) {
    Swal.fire({ icon: 'error', title: 'ปลดระวางไม่สำเร็จ', text: errorText(e) })
  } finally {
    actingId.value = null
    actingKind.value = null
  }
}

async function doUnretire(a: Announcement) {
  const { isConfirmed } = await Swal.fire({
    title: 'นำประกาศกลับมาใช้?',
    text: 'ประกาศจะกลับไปแสดงบนหน้า Landing Page อีกครั้ง',
    icon: 'question',
    showCancelButton: true,
    confirmButtonText: 'นำกลับมาใช้',
    confirmButtonColor: WARN,
    cancelButtonText: 'ยกเลิก',
  })
  if (!isConfirmed) return

  actingId.value = a.id
  actingKind.value = 'unretire'
  try {
    await unretireAnnouncement(a.id)
    Swal.fire({
      icon: 'success',
      title: 'นำกลับมาใช้แล้ว',
      timer: 1200,
      showConfirmButton: false,
    })
    await load()
  } catch (e) {
    Swal.fire({ icon: 'error', title: 'นำกลับมาใช้ไม่สำเร็จ', text: errorText(e) })
  } finally {
    actingId.value = null
    actingKind.value = null
  }
}

// ===== การแสดงผล =====
// 🕐 `fmtDateTime` มาจาก `@/datetime` (R5.5) — ของเดิมในไฟล์นี้คืน `'—'` เมื่อไม่มีค่า
//    ⚠️ ทุกจุดเรียกอยู่ใน `v-if` ที่การันตีว่าไม่ null อยู่แล้ว ⇒ ไม่ต้องเติม `|| '—'` ที่นี่

const hasAnyItems = computed(() => items.value.length > 0)
</script>

<template>
  <div>
    <!-- 🔴 ไม่มี <h1>/eyebrow ที่นี่ — `AppHeader` แสดงชื่อหน้าจาก `routeTitles` เป็น <h1> ให้แล้ว (R0.3) -->
    <div class="mb-6 flex flex-wrap items-end justify-between gap-3">
      <p class="text-sm text-stone-500">
        ประกาศที่เพิ่มที่นี่จะขึ้นบนหน้า Landing Page ทันที — เรียงด่วนมาก → สำคัญ → ปกติ
      </p>
      <button
        type="button"
        @click="openAdd"
        class="inline-flex items-center gap-1.5 rounded-xl bg-brand px-4 min-h-11 py-2.5 text-sm font-bold text-white shadow-md transition-all hover:bg-brand-strong hover:shadow-lg active:scale-[0.97]"
      >
        <i class="bi bi-plus-lg"></i> เพิ่มประกาศ
      </button>
    </div>

    <!-- แท็บกรองสถานะ -->
    <div class="mb-4 flex flex-wrap items-center gap-2">
      <button
        v-for="t in STATUS_TABS"
        :key="t.value"
        type="button"
        @click="changeStatus(t.value)"
        class="inline-flex items-center rounded-full px-3.5 min-h-11 py-1.5 text-[13px] font-semibold transition-colors"
        :class="
          statusFilter === t.value
            ? 'bg-stone-900 text-white shadow-sm'
            : 'bg-white text-stone-600 ring-1 ring-stone-200 hover:bg-stone-100'
        "
      >
        {{ t.label }}
      </button>
      <span v-if="!isLoading" class="ml-1 text-[13px] text-ink-3">
        {{ total }} รายการ
      </span>
    </div>

    <!-- Skeleton ตอนโหลดครั้งแรก -->
    <div v-if="isLoading && !hasAnyItems" class="space-y-3">
      <div v-for="i in 3" :key="i" class="animate-pulse rounded-2xl bg-white p-5 ring-1 ring-stone-100">
        <div class="mb-3 h-4 w-24 rounded bg-stone-200"></div>
        <div class="h-4 w-3/4 rounded bg-stone-100"></div>
      </div>
    </div>

    <!-- Error -->
    <div
      v-else-if="hasError"
      class="rounded-2xl bg-red-50 px-5 py-6 text-center ring-1 ring-red-100"
    >
      <i class="bi bi-exclamation-triangle-fill mb-2 block text-2xl text-red-500"></i>
      <p class="text-sm font-semibold text-brand">โหลดประกาศไม่สำเร็จ</p>
      <button
        type="button"
        @click="load"
        class="inline-flex items-center mt-3 rounded-xl bg-white px-4 min-h-11 py-2 text-sm font-semibold text-brand ring-1 ring-red-200 hover:bg-red-100"
      >
        ลองใหม่
      </button>
    </div>

    <!-- ว่าง -->
    <div
      v-else-if="!hasAnyItems"
      class="rounded-2xl bg-white px-5 py-12 text-center ring-1 ring-stone-100"
    >
      <i class="bi bi-megaphone mb-3 block text-3xl text-stone-300"></i>
      <p class="text-sm font-semibold text-stone-600">
        {{
          statusFilter === 'deleted'
            ? 'ไม่มีประกาศที่ถูกลบ'
            : statusFilter === 'retired'
              ? 'ไม่มีประกาศที่ปลดระวาง'
              : 'ยังไม่มีประกาศ'
        }}
      </p>
      <p class="mt-1 text-[13px] text-ink-3">
        {{
          statusFilter === 'deleted'
            ? 'ประกาศที่ลบจะมาแสดงที่นี่'
            : statusFilter === 'retired'
              ? 'ประกาศที่ปลดระวางแล้วจะมาแสดงที่นี่'
              : 'กด "เพิ่มประกาศ" เพื่อขึ้นประกาศบนหน้า Landing Page'
        }}
      </p>
    </div>

    <!-- รายการประกาศ -->
    <div v-else class="space-y-3" :class="isLoading ? 'opacity-60 transition-opacity' : ''">
      <div
        v-for="a in items"
        :key="a.id"
        class="rounded-2xl bg-white p-5 ring-1 transition-shadow hover:shadow-md"
        :class="
          rowState(a) === 'deleted'
            ? 'ring-stone-200 bg-stone-50/60'
            : rowState(a) === 'retired'
              ? 'ring-amber-200 bg-amber-50/40'
              : 'ring-stone-100'
        "
      >
        <!-- ⚠️ มือถือต้อง "ซ้อน" ไม่ใช่ "วางข้างกัน": ปุ่มเป็น shrink-0 (หดไม่ได้) จึงกิน
             ความกว้างตามเนื้อ ส่วนกล่องข้อความเป็น flex-1 (basis 0) ⇒ ถ้าปล่อยให้อยู่แถว
             เดียวกันบนจอแคบ ข้อความจะเหลือกว้างไม่กี่ px แล้วขึ้น "บรรทัดละตัวอักษร"
             ทางแก้: มือถือให้ทั้งสองกล่องเต็มความกว้าง (w-full) ⇒ flex-wrap พาไปคนละบรรทัด
             จอ sm ขึ้นไปค่อยกลับไปวางข้างกันแบบเดิม -->
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div class="w-full min-w-0 sm:w-auto sm:flex-1">
            <!-- ป้าย priority + เวลา -->
            <div class="mb-2 flex flex-wrap items-center gap-2">
              <span
                class="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-bold"
                :class="PRIORITY_STYLE[a.priority].badge"
              >
                <span
                  class="h-1.5 w-1.5 rounded-full"
                  :class="PRIORITY_STYLE[a.priority].dot"
                ></span>
                {{ PRIORITY_STYLE[a.priority].label }}
              </span>
              <span v-if="a.deleted_at" class="rounded-full bg-stone-200 px-2.5 py-1 text-[11px] font-bold text-stone-600">
                ถูกลบแล้ว
              </span>
              <!-- ปลดระวาง = สถานะแยกจากการลบ — โชว์ป้ายเฉพาะเมื่อยังไม่ถูกลบ
                   (แถวที่ "ปลดระวาง + ถูกลบ" อยู่แท็บถูกลบ ⇒ ป้าย "ถูกลบแล้ว" คุมความหมายอยู่แล้ว) -->
              <span
                v-else-if="a.retired_at"
                class="rounded-full bg-amber-100 px-2.5 py-1 text-[11px] font-bold text-amber-700 ring-1 ring-amber-200"
              >
                <i class="bi bi-archive mr-1"></i>ปลดระวางแล้ว
              </span>
              <span class="text-[11px] text-ink-3">{{ fmtDateTime(a.created_at) }}</span>
            </div>

            <p
              class="whitespace-pre-wrap break-words text-[15px] leading-relaxed"
              :class="rowState(a) === 'active' ? 'text-stone-800' : 'text-stone-500'"
            >
              {{ a.message }}
            </p>

            <!-- ลิงก์แนบ -->
            <a
              v-if="a.link"
              :href="a.link"
              target="_blank"
              rel="noopener noreferrer"
              class="mt-2 inline-flex max-w-full items-center gap-1.5 truncate text-[13px] font-semibold text-brand hover:underline"
            >
              <i class="bi bi-link-45deg"></i> {{ a.link }}
            </a>

            <!-- ผู้ประกาศ/ผู้แก้ (created_by_name = null ได้ ถ้าเป็นประกาศ seed เก่า หรือผู้ใช้ถูกลบ) -->
            <p class="mt-3 text-[12px] text-ink-3">
              <span>
                <i class="bi bi-person-circle mr-1"></i>
                {{ a.created_by_name || 'ไม่ทราบผู้ประกาศ' }}
              </span>
              <!-- ⚠️ !a.retired_at จำเป็น: การปลดระวางก็เซ็ต updated_at ⇒ ถ้าไม่กัน
                   แถวที่เพิ่งปลดระวางจะโชว์ "แก้ล่าสุด <เวลาเดียวกับที่ปลดระวาง>" ซึ่งอ่านแล้ว
                   เข้าใจผิดว่าเนื้อหาถูกแก้ (จริง ๆ แก้ไม่ได้ด้วยซ้ำ — PATCH ถูกบล็อก) -->
              <template v-if="a.updated_at && a.updated_at !== a.created_at && !a.retired_at">
                <span class="mx-1.5">·</span>
                <span>แก้ล่าสุด {{ fmtDateTime(a.updated_at) }}</span>
                <template v-if="a.updated_by_name">
                  <span class="mx-1">โดย {{ a.updated_by_name }}</span>
                </template>
              </template>
              <!-- เวลาที่ปลดระวาง — บอกว่า "เอาออกเมื่อไร" ซึ่งเป็นข้อมูลที่การลบไม่มี -->
              <template v-if="a.retired_at">
                <span class="mx-1.5">·</span>
                <span class="text-amber-600">
                  <i class="bi bi-archive mr-1"></i>ปลดระวางเมื่อ {{ fmtDateTime(a.retired_at) }}
                </span>
              </template>
            </p>
          </div>

          <!-- ปุ่มจัดการ — มือถือเต็มความกว้าง + wrap ได้ (3 ปุ่ม: แก้ไข/ปลดระวาง/ลบ)
               ส่วน sm ขึ้นไปค่อยหดตามเนื้อและไม่ให้หด (shrink-0) -->
          <div class="flex w-full flex-wrap items-center gap-1.5 sm:w-auto sm:shrink-0">
            <template v-if="a.deleted_at">
              <button
                type="button"
                :disabled="actingId === a.id"
                @click="doRestore(a)"
                class="inline-flex items-center gap-1.5 rounded-xl bg-ok-solid px-3.5 min-h-11 py-2 text-[13px] font-bold text-white transition-colors hover:bg-ok-strong disabled:opacity-50"
              >
                <span
                  v-if="busy(a, 'restore')"
                  class="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white/40 border-t-white"
                ></span>
                <i v-else class="bi bi-arrow-counterclockwise"></i>
                กู้คืน
              </button>
            </template>

            <!-- ปลดระวางแล้ว: แก้ไม่ได้ (ต้องนำกลับมาใช้ก่อน) — ลบได้ตามปกติ -->
            <template v-else-if="a.retired_at">
              <button
                type="button"
                :disabled="actingId === a.id"
                @click="doUnretire(a)"
                class="inline-flex items-center gap-1.5 rounded-xl bg-amber-600 px-3.5 min-h-11 py-2 text-[13px] font-bold text-white transition-colors hover:bg-amber-700 disabled:opacity-50"
              >
                <span
                  v-if="busy(a, 'unretire')"
                  class="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white/40 border-t-white"
                ></span>
                <i v-else class="bi bi-arrow-up-circle"></i>
                นำกลับมาใช้
              </button>
              <button
                type="button"
                :disabled="actingId === a.id"
                @click="confirmDelete(a)"
                class="inline-flex items-center gap-1.5 rounded-xl px-3.5 min-h-11 py-2 text-[13px] font-semibold text-brand ring-1 ring-red-200 transition-colors hover:bg-red-50 disabled:opacity-50"
              >
                <span
                  v-if="busy(a, 'delete')"
                  class="h-3.5 w-3.5 animate-spin rounded-full border-2 border-brand/30 border-t-brand"
                ></span>
                <i v-else class="bi bi-trash3"></i> ลบ
              </button>
            </template>

            <template v-else>
              <button
                type="button"
                @click="openEdit(a)"
                class="inline-flex items-center gap-1.5 rounded-xl px-3.5 min-h-11 py-2 text-[13px] font-semibold text-stone-600 ring-1 ring-stone-200 transition-colors hover:bg-stone-50"
              >
                <i class="bi bi-pencil"></i> แก้ไข
              </button>
              <!-- ปลดระวาง — ปุ่มโทน amber ต่างจาก "ลบ" ที่เป็นแดง เพื่อไม่ให้สับสนว่าเป็นการลบ -->
              <button
                type="button"
                :disabled="actingId === a.id"
                @click="confirmRetire(a)"
                class="inline-flex items-center gap-1.5 rounded-xl px-3.5 min-h-11 py-2 text-[13px] font-semibold text-amber-700 ring-1 ring-amber-200 transition-colors hover:bg-amber-50 disabled:opacity-50"
              >
                <span
                  v-if="busy(a, 'retire')"
                  class="h-3.5 w-3.5 animate-spin rounded-full border-2 border-amber-600/30 border-t-amber-600"
                ></span>
                <i v-else class="bi bi-archive"></i> ปลดระวาง
              </button>
              <button
                type="button"
                :disabled="actingId === a.id"
                @click="confirmDelete(a)"
                class="inline-flex items-center gap-1.5 rounded-xl px-3.5 min-h-11 py-2 text-[13px] font-semibold text-brand ring-1 ring-red-200 transition-colors hover:bg-red-50 disabled:opacity-50"
              >
                <span
                  v-if="busy(a, 'delete')"
                  class="h-3.5 w-3.5 animate-spin rounded-full border-2 border-brand/30 border-t-brand"
                ></span>
                <i v-else class="bi bi-trash3"></i> ลบ
              </button>
            </template>
          </div>
        </div>
      </div>

      <PaginationBar
        :total="total"
        :page="page"
        :page-size="PAGE_SIZE"
        :loading="isLoading"
        @page-change="changePage"
      />
    </div>

    <!-- ════════════ Modal เพิ่ม/แก้ไขประกาศ ════════════ -->
    <!-- ⚠️ ต้อง Teleport ออกไปที่ <body> — modal นี้เรนเดอร์อยู่ภายใน stacking context
         ของ `.maincol` (`relative z-10` ใน MainLayout) ⇒ z-50 ข้างในถูกกักไว้ที่ชั้น 10
         และแพ้ bottom tab bar (`fixed z-40`) ที่เป็นพี่น้องกัน ⇒ แถบเมนูล่างทับและกลืนคลิก
         ปุ่มบันทึก. Teleport ทำให้ modal ไปแข่ง z-index ที่ระดับ root แทน -->
    <Teleport to="body">
      <Transition name="sheet">
        <div v-if="modalOpen" class="fixed inset-0 z-50 flex items-end justify-center sm:items-center">
          <div class="absolute inset-0 bg-stone-900/40 backdrop-blur-sm" @click="closeModal"></div>
          <div
            class="relative z-10 mx-auto flex max-h-[92vh] w-full max-w-lg flex-col overflow-hidden rounded-t-[1.5rem] bg-white shadow-2xl sm:rounded-[1.5rem]"
          >
            <!-- Header -->
            <div class="flex items-center justify-between border-b border-stone-100 px-5 py-4">
              <div>
                <h3 class="text-base font-bold text-stone-900">
                  {{ modalMode === 'add' ? 'เพิ่มประกาศ' : 'แก้ไขประกาศ' }}
                </h3>
                <p class="mt-0.5 text-xs text-stone-500">
                  {{ modalMode === 'add' ? 'จะขึ้นบน Landing Page ทันที' : 'แก้แล้วมีผลทันที' }}
                </p>
              </div>
              <button
                type="button"
                aria-label="ปิดหน้าต่าง"
                @click="closeModal"
                class="rounded-xl p-2 text-ink-3 hover:bg-stone-100"
              >
                <i class="bi bi-x-lg"></i>
              </button>
            </div>

            <!-- Body -->
            <div class="custom-scrollbar flex-1 space-y-4 overflow-y-auto px-5 py-4">
              <div>
                <label class="mb-1 block text-xs font-semibold text-stone-500" for="ann-message">
                  ข้อความประกาศ <span class="text-brand">*</span>
                </label>
                <textarea
                  id="ann-message"
                  v-model="form.message"
                  rows="4"
                  maxlength="1000"
                  placeholder="เช่น เข้าแถวหน้าชั้นเรียน เพราะฝนตก วันที่ 30 ก.ย."
                  class="w-full resize-none rounded-xl border border-stone-200 px-3.5 py-2.5 text-sm text-stone-800 outline-none transition-colors focus:border-brand focus:ring-2 focus:ring-brand/10"
                ></textarea>
                <p class="mt-1 text-right text-[11px] text-ink-3">
                  {{ form.message.length }}/1000
                </p>
              </div>

              <div>
                <p class="mb-1 text-xs font-semibold text-stone-500">ความสำคัญ</p>
                <div class="grid grid-cols-1 gap-1.5 sm:grid-cols-3">
                  <button
                    v-for="opt in PRIORITY_OPTIONS"
                    :key="opt.value"
                    type="button"
                    @click="form.priority = opt.value"
                    class="flex items-center gap-2 rounded-xl border px-3 min-h-11 py-2.5 text-left transition-colors"
                    :class="
                      form.priority === opt.value
                        ? 'border-brand bg-brand/5'
                        : 'border-stone-200 hover:bg-stone-50'
                    "
                  >
                    <span
                      class="h-2 w-2 shrink-0 rounded-full"
                      :class="PRIORITY_STYLE[opt.value].dot"
                    ></span>
                    <span class="min-w-0">
                      <span
                        class="block text-[13px] font-bold"
                        :class="form.priority === opt.value ? 'text-brand' : 'text-stone-700'"
                      >
                        {{ opt.label }}
                      </span>
                    </span>
                  </button>
                </div>
                <p class="mt-1.5 text-[11px] text-ink-3">
                  {{ PRIORITY_OPTIONS.find((o) => o.value === form.priority)?.hint }}
                </p>
              </div>

              <div>
                <label class="mb-1 block text-xs font-semibold text-stone-500" for="ann-link">
                  ลิงก์แนบ <span class="text-ink-3">(ไม่บังคับ)</span>
                </label>
                <input
                  id="ann-link"
                  v-model="form.link"
                  type="url"
                  maxlength="500"
                  placeholder="https://..."
                  class="w-full rounded-xl border border-stone-200 px-3.5 py-2.5 text-sm text-stone-800 outline-none transition-colors focus:border-brand focus:ring-2 focus:ring-brand/10"
                />
                <p class="mt-1 text-[11px] text-ink-3">
                  ต้องขึ้นต้นด้วย http:// หรือ https:// เท่านั้น — เว้นว่าง = ไม่มีลิงก์
                </p>
              </div>

              <p
                v-if="saveError"
                class="whitespace-pre-line rounded-xl bg-red-50 px-3 py-2.5 text-[13px] font-medium text-red-600"
              >
                <i class="bi bi-exclamation-circle mr-1"></i> {{ saveError }}
              </p>
            </div>

            <!-- Footer -->
            <div class="flex items-center justify-end gap-2 border-t border-stone-100 px-5 py-3.5">
              <button
                type="button"
                @click="closeModal"
                :disabled="saving"
                class="inline-flex items-center rounded-xl px-4 min-h-11 py-2.5 text-sm font-semibold text-stone-600 transition-colors hover:bg-stone-100 disabled:opacity-50"
              >
                ยกเลิก
              </button>
              <button
                type="button"
                @click="submitForm"
                :disabled="!canSubmit"
                class="inline-flex items-center gap-2 rounded-xl bg-brand px-5 min-h-11 py-2.5 text-sm font-bold text-white shadow-md transition-all hover:bg-brand-strong disabled:opacity-60"
              >
                <span
                  v-if="saving"
                  class="h-4 w-4 animate-spin rounded-full border-2 border-white/40 border-t-white"
                ></span>
                <i v-else class="bi bi-check-lg"></i>
                {{ saving ? 'กำลังบันทึก…' : modalMode === 'add' ? 'ประกาศ' : 'บันทึก' }}
              </button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<style scoped>
.custom-scrollbar::-webkit-scrollbar {
  width: 5px;
}
.custom-scrollbar::-webkit-scrollbar-thumb {
  background-color: rgba(0, 0, 0, 0.12);
  border-radius: 10px;
}
.sheet-enter-active,
.sheet-leave-active {
  transition: opacity 0.25s ease;
}
.sheet-enter-active .relative,
.sheet-leave-active .relative {
  transition: transform 0.3s cubic-bezier(0.175, 0.885, 0.32, 1);
}
.sheet-enter-from,
.sheet-leave-to {
  opacity: 0;
}
.sheet-enter-from .relative,
.sheet-leave-to .relative {
  transform: translateY(24px) scale(0.99);
}
</style>
