<!-- eslint-disable vue/multi-word-component-names -- ชื่อตาม route/spec -->
<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import Swal from 'sweetalert2'
import { BRAND, WARN } from '@/constants/brand'
import {
  listTerms,
  createTerm,
  updateTerm,
  setCurrentTerm,
  deleteTerm,
  restoreTerm,
} from '@/services/settings'
import type { AcademicTerm, AcademicTermUpdatePayload } from '@/types/academicTerm'
import { TERM_STATUS_TABS } from '@/types/academicTerm'
import PaginationBar from '@/components/PaginationBar.vue'

const PAGE_SIZE = 20

const items = ref<AcademicTerm[]>([])
const total = ref(0)
const page = ref(1)
const statusFilter = ref('active')
const isLoading = ref(true)
const hasError = ref(false)
/** มีข้อมูลค้างอยู่ในลิสต์แล้วหรือยัง — ใช้เลือกแสดง skeleton vs จางรายการเดิมตอนโหลดหน้าใหม่ */
const hasAnyItems = computed(() => items.value.length > 0)

async function load() {
  isLoading.value = true
  hasError.value = false
  try {
    const res = await listTerms({
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
    Swal.fire({ icon: 'error', title: 'โหลดภาคเรียนไม่สำเร็จ', text: errorText(e) })
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

function changeStatus(next: string) {
  if (statusFilter.value === next) return
  statusFilter.value = next
  page.value = 1
  load()
}

function changePage(next: number) {
  page.value = next
  load()
}

// ===== การแสดงวันที่ =====
// ⚠️ backend ส่ง `YYYY-MM-DD` มา (ชนิด date ไม่มีเวลา) — **ห้ามใช้ `new Date(iso)` แล้ว format
//    เพราะ string แบบ date-only ถูกตีความเป็นเที่ยงคืน UTC แล้วเลื่อนเป็นเวลาไทย (+7 ชม.)
//    ⇒ วันที่เพี้ยนได้ถ้าอนาคตมีคนเปลี่ยน timeZone ที่ format ⇒ แยก part เอง ปลอดภัยกว่า
const TH_MONTHS = [
  'ม.ค.', 'ก.พ.', 'มี.ค.', 'เม.ย.', 'พ.ค.', 'มิ.ย.',
  'ก.ค.', 'ส.ค.', 'ก.ย.', 'ต.ค.', 'พ.ย.', 'ธ.ค.',
]

/** แยก 'YYYY-MM-DD' เป็น [ปี, เดือน, วัน] — คืน null ถ้ารูปไม่ตรง */
function parseYmd(iso: string): [number, number, number] | null {
  const parts = iso.split('-')
  if (parts.length !== 3) return null
  const y = Number(parts[0])
  const m = Number(parts[1])
  const d = Number(parts[2])
  if (!Number.isFinite(y) || !Number.isFinite(m) || !Number.isFinite(d)) return null
  return [y, m, d]
}

function fmtDate(iso: string): string {
  const p = parseYmd(iso)
  if (!p) return iso
  return `${p[2]} ${TH_MONTHS[p[1] - 1]} ${p[0] + 543}` // พ.ศ.
}

/** จำนวนวันของภาค — **รวมวันสุดท้าย** (inclusive) ตรงกับความหมายที่ backend ใช้ */
function dayCount(t: AcademicTerm): number {
  const a = parseYmd(t.start_date)
  const b = parseYmd(t.end_date)
  if (!a || !b) return 0
  const ms = Date.UTC(b[0], b[1] - 1, b[2]) - Date.UTC(a[0], a[1] - 1, a[2])
  return Math.round(ms / 86_400_000) + 1
}

/** วันนี้ (เวลาไทย) เป็น 'YYYY-MM-DD' — ใช้ Intl แทนการคำนวณ offset เอง */
function todayBkk(): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Bangkok' }).format(new Date())
}

// ===== Modal เพิ่ม/แก้ไข =====
const modalOpen = ref(false)
const modalMode = ref<'add' | 'edit'>('add')
const editingId = ref<number | null>(null)
const saving = ref(false)
const saveError = ref('')

const form = ref({ name: '', start_date: '', end_date: '', is_current: false })

/** ตรวจฝั่ง client เพื่อให้กดไม่ได้ตั้งแต่แรก — backend ตรวจซ้ำและคืน 400 อยู่ดี */
const formError = computed(() => {
  if (!form.value.name.trim()) return 'กรอกชื่อภาคเรียน'
  if (!form.value.start_date) return 'เลือกวันเริ่มต้น'
  if (!form.value.end_date) return 'เลือกวันสิ้นสุด'
  if (form.value.end_date < form.value.start_date) return 'วันสิ้นสุดต้องไม่ก่อนวันเริ่มต้น'
  return ''
})

function openAdd() {
  modalMode.value = 'add'
  editingId.value = null
  form.value = { name: '', start_date: '', end_date: '', is_current: false }
  saveError.value = ''
  modalOpen.value = true
}

function openEdit(t: AcademicTerm) {
  modalMode.value = 'edit'
  editingId.value = t.id
  form.value = {
    name: t.name,
    start_date: t.start_date,
    end_date: t.end_date,
    is_current: t.is_current,
  }
  saveError.value = ''
  modalOpen.value = true
}

function closeModal() {
  modalOpen.value = false
}

async function save() {
  if (formError.value) return
  saving.value = true
  saveError.value = ''
  try {
    if (modalMode.value === 'add') {
      await createTerm({
        name: form.value.name.trim(),
        start_date: form.value.start_date,
        end_date: form.value.end_date,
        is_current: form.value.is_current,
      })
    } else if (editingId.value !== null) {
      // PATCH ส่งเฉพาะฟิลด์ที่แก้จริง — ⚠️ ไม่ส่ง is_current (backend ไม่รับผ่านทางนี้)
      const payload: AcademicTermUpdatePayload = {}
      const before = items.value.find((t) => t.id === editingId.value)
      const name = form.value.name.trim()
      if (!before || name !== before.name) payload.name = name
      if (!before || form.value.start_date !== before.start_date) {
        payload.start_date = form.value.start_date
      }
      if (!before || form.value.end_date !== before.end_date) {
        payload.end_date = form.value.end_date
      }
      if (Object.keys(payload).length === 0) {
        modalOpen.value = false
        return
      }
      await updateTerm(editingId.value, payload)
    }
    modalOpen.value = false
    Swal.fire({
      icon: 'success',
      title: modalMode.value === 'add' ? 'เพิ่มภาคเรียนแล้ว' : 'บันทึกแล้ว',
      timer: 1200,
      showConfirmButton: false,
    })
    await load()
  } catch (e) {
    // เก็บไว้ในฟอร์ม ไม่ปิด modal — ผู้ใช้จะได้แก้แล้วกดซ้ำได้เลย
    saveError.value = errorText(e)
  } finally {
    saving.value = false
  }
}

// ===== การกระทำต่อแถว =====
const actingId = ref<number | null>(null)
const actingKind = ref<'current' | 'delete' | 'restore' | null>(null)

function busy(t: AcademicTerm, kind: string): boolean {
  return actingId.value === t.id && actingKind.value === kind
}

async function doSetCurrent(t: AcademicTerm) {
  const res = await Swal.fire({
    title: 'ใช้ภาคนี้เป็นภาคปัจจุบัน?',
    text: `สถิติและหน้าแรกจะนับเฉพาะช่วง ${fmtDate(t.start_date)} – ${fmtDate(t.end_date)}`,
    icon: 'question',
    showCancelButton: true,
    confirmButtonText: 'ใช้ภาคนี้',
    confirmButtonColor: BRAND,
    cancelButtonText: 'ยกเลิก',
  })
  if (!res.isConfirmed) return

  actingId.value = t.id
  actingKind.value = 'current'
  try {
    await setCurrentTerm(t.id)
    Swal.fire({
      icon: 'success',
      title: 'ตั้งเป็นภาคปัจจุบันแล้ว',
      timer: 1200,
      showConfirmButton: false,
    })
    await load()
  } catch (e) {
    Swal.fire({ icon: 'error', title: 'ตั้งภาคปัจจุบันไม่สำเร็จ', text: errorText(e) })
  } finally {
    actingId.value = null
    actingKind.value = null
  }
}

async function doDelete(t: AcademicTerm) {
  const res = await Swal.fire({
    title: 'ลบภาคเรียนนี้?',
    text: t.is_current
      ? 'นี่คือภาคปัจจุบันอยู่ — ลบแล้วระบบจะกลับไปนับสถิติ "ทั้งหมด" จนกว่าจะตั้งภาคใหม่'
      : 'ภาคเรียนจะถูกซ่อนจากรายการ (กู้คืนได้ภายหลัง)',
    icon: 'warning',
    showCancelButton: true,
    confirmButtonText: 'ลบภาคเรียน',
    confirmButtonColor: BRAND,
    cancelButtonText: 'ยกเลิก',
  })
  if (!res.isConfirmed) return

  actingId.value = t.id
  actingKind.value = 'delete'
  try {
    await deleteTerm(t.id)
    Swal.fire({ icon: 'success', title: 'ลบแล้ว', timer: 1000, showConfirmButton: false })
    // ลบรายการสุดท้ายของหน้าสุดท้าย → ถอยกลับหนึ่งหน้า
    // ไม่งั้น `load()` คืน 0 รายการ ⇒ หน้าเปลี่ยนเป็น empty state แล้ว **แถบแบ่งหน้าหายไปด้วย**
    // (PaginationBar อยู่ในกิ่ง v-else ของรายการ) ⇒ ภาคเรียนที่เหลืออยู่เข้าถึงไม่ได้เลย
    if (items.value.length === 1 && page.value > 1) page.value -= 1
    await load()
  } catch (e) {
    Swal.fire({ icon: 'error', title: 'ลบไม่สำเร็จ', text: errorText(e) })
  } finally {
    actingId.value = null
    actingKind.value = null
  }
}

async function doRestore(t: AcademicTerm) {
  const res = await Swal.fire({
    title: 'กู้คืนภาคเรียนนี้?',
    text: 'กลับมาเป็นภาคธรรมดา — ต้องกด "ใช้เป็นภาคปัจจุบัน" เองอีกครั้ง',
    icon: 'question',
    showCancelButton: true,
    confirmButtonText: 'กู้คืน',
    confirmButtonColor: WARN,
    cancelButtonText: 'ยกเลิก',
  })
  if (!res.isConfirmed) return

  actingId.value = t.id
  actingKind.value = 'restore'
  try {
    await restoreTerm(t.id)
    Swal.fire({ icon: 'success', title: 'กู้คืนแล้ว', timer: 1000, showConfirmButton: false })
    // กู้คืน = รายการออกจากแท็บ "ถูกลบ" ⇒ เกิดปัญหาเดียวกับ doDelete (ดูคอมเมนต์ที่นั่น)
    if (items.value.length === 1 && page.value > 1) page.value -= 1
    await load()
  } catch (e) {
    Swal.fire({ icon: 'error', title: 'กู้คืนไม่สำเร็จ', text: errorText(e) })
  } finally {
    actingId.value = null
    actingKind.value = null
  }
}

// ===== สรุปว่าวันนี้อยู่ในภาคไหน (เฉพาะแท็บ "ทั้งหมด") =====
function coversToday(t: AcademicTerm): boolean {
  const today = todayBkk()
  return t.start_date <= today && today <= t.end_date
}
</script>

<template>
  <div>
    <!-- 🔴 ไม่มี <h1>/eyebrow ที่นี่ — `AppHeader` แสดงชื่อหน้าจาก `routeTitles` เป็น <h1> ให้แล้ว (R0.3) -->
    <div class="mb-6 flex flex-wrap items-center justify-end gap-3">
      <button
        type="button"
        @click="openAdd"
        class="inline-flex items-center gap-1.5 rounded-xl bg-brand px-4 min-h-11 py-2.5 text-sm font-bold text-white shadow-md transition-all hover:bg-brand-strong hover:shadow-lg active:scale-[0.97]"
      >
        <i class="bi bi-plus-lg"></i> เพิ่มภาคเรียน
      </button>
    </div>

    <!-- แท็บกรองสถานะ -->
    <div class="mb-4 flex flex-wrap items-center gap-2">
      <button
        v-for="t in TERM_STATUS_TABS"
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
        {{ total }} ภาคเรียน
      </span>
    </div>

    <!-- Skeleton ตอนโหลดครั้งแรก -->
    <div v-if="isLoading && !hasAnyItems" class="space-y-3">
      <div v-for="i in 3" :key="i" class="animate-pulse rounded-2xl bg-white p-5 ring-1 ring-stone-100">
        <div class="mb-3 h-4 w-24 rounded bg-stone-200"></div>
        <div class="h-4 w-2/3 rounded bg-stone-100"></div>
      </div>
    </div>

    <!-- Error -->
    <div v-else-if="hasError" class="rounded-2xl bg-red-50 px-5 py-6 text-center ring-1 ring-red-100">
      <i class="bi bi-exclamation-triangle-fill mb-2 block text-2xl text-red-500"></i>
      <p class="text-sm font-semibold text-brand">โหลดภาคเรียนไม่สำเร็จ</p>
      <button
        type="button"
        @click="load"
        class="inline-flex items-center mt-3 rounded-xl bg-white px-4 min-h-11 py-2 text-sm font-semibold text-brand ring-1 ring-red-200 hover:bg-red-100"
      >
        ลองใหม่
      </button>
    </div>

    <!-- ว่าง -->
    <div v-else-if="!hasAnyItems" class="rounded-2xl bg-white px-5 py-12 text-center ring-1 ring-stone-100">
      <i class="bi bi-calendar3 mb-3 block text-3xl text-stone-300"></i>
      <p class="text-sm font-semibold text-stone-600">
        {{ statusFilter === 'deleted' ? 'ไม่มีภาคเรียนที่ถูกลบ' : 'ยังไม่มีภาคเรียน' }}
      </p>
      <p class="mt-1 text-[13px] text-ink-3">
        {{
          statusFilter === 'deleted'
            ? 'ภาคเรียนที่ลบจะมาแสดงที่นี่'
            : statusFilter === 'current'
              ? 'กด "ใช้เป็นภาคปัจจุบัน" ที่ภาคที่ต้องการ'
              : 'กด "เพิ่มภาคเรียน" เพื่อเริ่มกำหนดช่วงวันที่ของภาค'
        }}
      </p>
    </div>

    <!-- รายการ -->
    <div v-else class="space-y-3" :class="isLoading ? 'opacity-60 transition-opacity' : ''">
      <div
        v-for="t in items"
        :key="t.id"
        class="rounded-2xl bg-white p-5 ring-1 transition-shadow hover:shadow-md"
        :class="
          t.deleted_at
            ? 'bg-stone-50/60 ring-stone-200'
            : t.is_current
              ? 'ring-brand/30'
              : 'ring-stone-100'
        "
      >
        <!-- ⚠️ มือถือต้อง "ซ้อน" ไม่ใช่ "วางข้างกัน" (บทเรียน PR #33): ปุ่มเป็น shrink-0
             จึงกินความกว้างตามเนื้อ ส่วนกล่องข้อความเป็น flex-1 (basis 0) ⇒ ถ้าอยู่แถว
             เดียวกันบนจอแคบ ข้อความจะเหลือไม่กี่ px แล้วขึ้นบรรทัดละตัวอักษร -->
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div class="w-full min-w-0 sm:w-auto sm:flex-1">
            <div class="mb-2 flex flex-wrap items-center gap-2">
              <span
                v-if="t.is_current"
                class="inline-flex items-center gap-1.5 rounded-full bg-brand/10 px-2.5 py-1 text-[11px] font-bold text-brand"
              >
                <span class="h-1.5 w-1.5 rounded-full bg-brand"></span> กำลังใช้อยู่
              </span>
              <span
                v-if="t.deleted_at"
                class="rounded-full bg-stone-200 px-2.5 py-1 text-[11px] font-bold text-stone-600"
              >
                ถูกลบแล้ว
              </span>
              <span
                v-else-if="!t.is_current && coversToday(t)"
                class="rounded-full bg-ok-tint px-2.5 py-1 text-[11px] font-bold text-ok-strong ring-1 ring-ok-line"
              >
                <i class="bi bi-calendar-check mr-1"></i>วันนี้อยู่ในช่วงนี้
              </span>
            </div>

            <h2
              class="break-words text-[15px] font-bold leading-snug"
              :class="t.deleted_at ? 'text-stone-500' : 'text-stone-800'"
            >
              {{ t.name }}
            </h2>

            <p class="mt-1.5 text-[13px] text-stone-500">
              <i class="bi bi-calendar-range mr-1"></i>
              {{ fmtDate(t.start_date) }} – {{ fmtDate(t.end_date) }}
              <span class="mx-1.5 text-stone-300">·</span>
              <span class="tabular-nums">{{ dayCount(t) }} วัน</span>
            </p>
          </div>

          <!-- ปุ่มจัดการ — มือถือเต็มความกว้าง + wrap ได้ -->
          <div class="flex w-full flex-wrap items-center gap-1.5 sm:w-auto sm:shrink-0">
            <template v-if="t.deleted_at">
              <button
                type="button"
                :disabled="actingId === t.id"
                @click="doRestore(t)"
                class="inline-flex items-center gap-1.5 rounded-xl bg-ok-solid px-3.5 min-h-11 py-2 text-[13px] font-bold text-white transition-colors hover:bg-ok-strong disabled:opacity-50"
              >
                <i :class="busy(t, 'restore') ? 'bi bi-arrow-repeat animate-spin' : 'bi bi-arrow-counterclockwise'"></i>
                กู้คืน
              </button>
            </template>
            <template v-else>
              <button
                v-if="!t.is_current"
                type="button"
                :disabled="actingId === t.id"
                @click="doSetCurrent(t)"
                class="inline-flex items-center gap-1.5 rounded-xl bg-brand px-3.5 min-h-11 py-2 text-[13px] font-bold text-white transition-colors hover:bg-brand-strong disabled:opacity-50"
              >
                <i :class="busy(t, 'current') ? 'bi bi-arrow-repeat animate-spin' : 'bi bi-check2-circle'"></i>
                ใช้เป็นภาคปัจจุบัน
              </button>
              <button
                type="button"
                :disabled="actingId === t.id"
                @click="openEdit(t)"
                class="inline-flex items-center gap-1.5 rounded-xl bg-white px-3.5 min-h-11 py-2 text-[13px] font-bold text-stone-700 ring-1 ring-stone-200 transition-colors hover:bg-stone-100 disabled:opacity-50"
              >
                <i class="bi bi-pencil-square"></i> แก้ไข
              </button>
              <button
                type="button"
                :disabled="actingId === t.id"
                @click="doDelete(t)"
                class="inline-flex items-center gap-1.5 rounded-xl bg-white px-3.5 min-h-11 py-2 text-[13px] font-bold text-red-600 ring-1 ring-red-200 transition-colors hover:bg-red-50 disabled:opacity-50"
              >
                <i :class="busy(t, 'delete') ? 'bi bi-arrow-repeat animate-spin' : 'bi bi-trash3'"></i>
                ลบ
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

    <!-- ════════════ Modal เพิ่ม/แก้ไขภาคเรียน ════════════ -->
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
            <div class="flex items-center justify-between border-b border-stone-100 px-5 py-4">
              <div>
                <h3 class="text-base font-bold text-stone-900">
                  {{ modalMode === 'add' ? 'เพิ่มภาคเรียน' : 'แก้ไขภาคเรียน' }}
                </h3>
                <p class="mt-0.5 text-xs text-stone-500">
                  {{ modalMode === 'add' ? 'กำหนดช่วงวันที่ของภาค' : 'แก้แล้วมีผลกับการกรองสถิติทันที' }}
                </p>
              </div>
              <button
                type="button"
                @click="closeModal"
                class="rounded-xl p-2 text-ink-3 hover:bg-stone-100"
                aria-label="ปิด"
              >
                <i class="bi bi-x-lg"></i>
              </button>
            </div>

            <div class="custom-scrollbar flex-1 space-y-4 overflow-y-auto px-5 py-4">
              <div>
                <label class="mb-1 block text-xs font-semibold text-stone-500" for="term-name">
                  ชื่อภาคเรียน <span class="text-brand">*</span>
                </label>
                <input
                  id="term-name"
                  v-model="form.name"
                  type="text"
                  maxlength="50"
                  placeholder="เช่น ภาคเรียนที่ 1/2569"
                  class="w-full rounded-xl border border-stone-200 px-3.5 py-2.5 text-sm text-stone-800 outline-none transition-colors focus:border-brand focus:ring-2 focus:ring-brand/10"
                />
              </div>

              <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <div>
                  <label class="mb-1 block text-xs font-semibold text-stone-500" for="term-start">
                    วันเริ่มต้น <span class="text-brand">*</span>
                  </label>
                  <input
                    id="term-start"
                    v-model="form.start_date"
                    type="date"
                    class="w-full rounded-xl border border-stone-200 px-3.5 py-2.5 text-sm text-stone-800 outline-none transition-colors focus:border-brand focus:ring-2 focus:ring-brand/10"
                  />
                </div>
                <div>
                  <label class="mb-1 block text-xs font-semibold text-stone-500" for="term-end">
                    วันสิ้นสุด <span class="text-brand">*</span>
                  </label>
                  <input
                    id="term-end"
                    v-model="form.end_date"
                    type="date"
                    class="w-full rounded-xl border border-stone-200 px-3.5 py-2.5 text-sm text-stone-800 outline-none transition-colors focus:border-brand focus:ring-2 focus:ring-brand/10"
                  />
                </div>
              </div>
              <p class="text-[11px] text-ink-3">
                <i class="bi bi-info-circle mr-1"></i>วันสิ้นสุด <b>รวมวันสุดท้ายด้วย</b> —
                ถ้าภาคจบวันที่ 10 ต.ค. ให้เลือก 10 ต.ค.
              </p>

              <!-- ตั้งเป็นปัจจุบัน — เฉพาะตอนเพิ่ม (ตอนแก้ให้ใช้ปุ่มในรายการ) -->
              <label
                v-if="modalMode === 'add'"
                class="flex cursor-pointer items-start gap-3 rounded-xl border border-stone-200 px-3.5 py-3 transition-colors hover:bg-stone-50"
              >
                <input
                  v-model="form.is_current"
                  type="checkbox"
                  class="mt-0.5 h-4 w-4 shrink-0 accent-brand"
                />
                <span class="min-w-0">
                  <span class="block text-[13px] font-bold text-stone-700">ใช้เป็นภาคปัจจุบัน</span>
                  <span class="mt-0.5 block text-[11px] text-stone-500">
                    ภาคปัจจุบันเดิมจะถูกปลดให้อัตโนมัติ (มีภาคปัจจุบันได้ครั้งละหนึ่ง)
                  </span>
                </span>
              </label>

              <!-- error จาก server (เก็บไว้ในฟอร์ม ไม่ปิด modal) -->
              <div v-if="saveError" class="rounded-xl bg-red-50 px-3.5 py-2.5 text-[13px] text-brand ring-1 ring-red-100">
                <i class="bi bi-exclamation-circle mr-1"></i>{{ saveError }}
              </div>
            </div>

            <div class="flex items-center justify-end gap-2 border-t border-stone-100 px-5 py-4">
              <p v-if="formError" class="mr-auto text-[12px] font-semibold text-amber-600">
                {{ formError }}
              </p>
              <button
                type="button"
                @click="closeModal"
                class="inline-flex items-center rounded-xl bg-white px-4 min-h-11 py-2.5 text-sm font-semibold text-stone-600 ring-1 ring-stone-200 transition-colors hover:bg-stone-100"
              >
                ยกเลิก
              </button>
              <button
                type="button"
                :disabled="saving || !!formError"
                @click="save"
                class="inline-flex items-center gap-1.5 rounded-xl bg-brand px-4 min-h-11 py-2.5 text-sm font-bold text-white transition-colors hover:bg-brand-strong disabled:opacity-50"
              >
                <i :class="saving ? 'bi bi-arrow-repeat animate-spin' : 'bi bi-check-lg'"></i>
                {{ modalMode === 'add' ? 'เพิ่มภาคเรียน' : 'บันทึก' }}
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
