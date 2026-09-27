<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import Swal from 'sweetalert2'
import PaginationBar from '@/components/PaginationBar.vue'
import {
  listAnnouncements,
  createAnnouncement,
  updateAnnouncement,
  deleteAnnouncement,
  restoreAnnouncement,
} from '@/services/announcement'
import type {
  Announcement,
  AnnouncementPriority,
  AnnouncementStatus,
} from '@/types/announcement'

// 📣 หน้าจัดการประกาศหน้า Landing Page (ต้องมีสิทธิ์ MANAGE_ANNOUNCEMENTS)
// - ลบ = soft delete → ยังเห็นได้เมื่อสลับตัวกรองเป็น "ถูกลบ" แล้วกู้คืนได้
// - ประกาศที่ seed มาก่อนมีฟีเจอร์นี้จะไม่มีชื่อผู้ประกาศ (created_by = null) → แสดง "—" ไม่ใช่พัง

const PAGE_SIZE = 20

const PRIORITY_OPTIONS: { value: AnnouncementPriority; label: string; hint: string }[] = [
  { value: 'normal', label: 'ปกติ', hint: 'สีเทา — ประกาศทั่วไป' },
  { value: 'high', label: 'สำคัญ', hint: 'สีส้ม — ควรอ่าน' },
  { value: 'urgent', label: 'ด่วนมาก', hint: 'สีแดงกะพริบ — ขึ้นบนสุดเสมอ' },
]

const PRIORITY_STYLE: Record<AnnouncementPriority, { dot: string; badge: string; label: string }> = {
  urgent: {
    dot: 'bg-[#B91C1C] animate-pulse',
    badge: 'bg-[#B91C1C]/10 text-[#B91C1C] ring-1 ring-[#B91C1C]/20',
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
  { value: 'deleted', label: 'ถูกลบ' },
  { value: 'all', label: 'ทั้งหมด' },
]

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

// ===== ลบ / กู้คืน =====
const actingId = ref<number | null>(null)

async function confirmDelete(a: Announcement) {
  const { isConfirmed } = await Swal.fire({
    title: 'ลบประกาศนี้?',
    text: 'ประกาศจะหายจากหน้า Landing Page ทันที (กู้คืนได้ภายหลัง)',
    icon: 'warning',
    showCancelButton: true,
    confirmButtonText: 'ลบประกาศ',
    confirmButtonColor: '#b91c1c',
    cancelButtonText: 'ยกเลิก',
  })
  if (!isConfirmed) return

  actingId.value = a.id
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
  }
}

async function doRestore(a: Announcement) {
  const { isConfirmed } = await Swal.fire({
    title: 'กู้คืนประกาศนี้?',
    text: 'ประกาศจะกลับไปแสดงบนหน้า Landing Page อีกครั้ง',
    icon: 'question',
    showCancelButton: true,
    confirmButtonText: 'กู้คืน',
    confirmButtonColor: '#B91C1C',
    cancelButtonText: 'ยกเลิก',
  })
  if (!isConfirmed) return

  actingId.value = a.id
  try {
    await restoreAnnouncement(a.id)
    Swal.fire({ icon: 'success', title: 'กู้คืนแล้ว', timer: 1200, showConfirmButton: false })
    await load()
  } catch (e) {
    Swal.fire({ icon: 'error', title: 'กู้คืนไม่สำเร็จ', text: errorText(e) })
  } finally {
    actingId.value = null
  }
}

// ===== การแสดงผล =====
function fmtDateTime(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('th-TH', {
    timeZone: 'Asia/Bangkok',
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

const hasAnyItems = computed(() => items.value.length > 0)
</script>

<template>
  <div>
    <!-- Editorial page header -->
    <div class="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div>
        <p
          class="mb-2 flex items-center gap-2 text-[11px] font-bold uppercase tracking-widest text-[#B91C1C]"
        >
          <i class="bi bi-megaphone-fill text-[13px]"></i> Announcement Management
        </p>
        <h1 class="text-2xl font-bold tracking-tight text-stone-900 leading-tight sm:text-3xl">
          จัดการประกาศ
        </h1>
        <p class="mt-2 text-sm text-stone-500">
          ประกาศที่เพิ่มที่นี่จะขึ้นบนหน้า Landing Page ทันที — เรียงด่วนมาก → สำคัญ → ปกติ
        </p>
      </div>
      <button
        type="button"
        @click="openAdd"
        class="inline-flex items-center gap-1.5 rounded-xl bg-[#B91C1C] px-4 py-2.5 text-sm font-bold text-white shadow-md transition-all hover:bg-[#991B1B] hover:shadow-lg active:scale-[0.97]"
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
        class="rounded-full px-3.5 py-1.5 text-[13px] font-semibold transition-colors"
        :class="
          statusFilter === t.value
            ? 'bg-stone-900 text-white shadow-sm'
            : 'bg-white text-stone-600 ring-1 ring-stone-200 hover:bg-stone-100'
        "
      >
        {{ t.label }}
      </button>
      <span v-if="!isLoading" class="ml-1 text-[13px] text-stone-400">
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
      <p class="text-sm font-semibold text-red-700">โหลดประกาศไม่สำเร็จ</p>
      <button
        type="button"
        @click="load"
        class="mt-3 rounded-xl bg-white px-4 py-2 text-sm font-semibold text-red-700 ring-1 ring-red-200 hover:bg-red-100"
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
        {{ statusFilter === 'deleted' ? 'ไม่มีประกาศที่ถูกลบ' : 'ยังไม่มีประกาศ' }}
      </p>
      <p class="mt-1 text-[13px] text-stone-400">
        {{
          statusFilter === 'deleted'
            ? 'ประกาศที่ลบจะมาแสดงที่นี่'
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
        :class="a.deleted_at ? 'ring-stone-200 bg-stone-50/60' : 'ring-stone-100'"
      >
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div class="min-w-0 flex-1">
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
              <span class="text-[11px] text-stone-400">{{ fmtDateTime(a.created_at) }}</span>
            </div>

            <p
              class="whitespace-pre-wrap break-words text-[15px] leading-relaxed"
              :class="a.deleted_at ? 'text-stone-500' : 'text-stone-800'"
            >
              {{ a.message }}
            </p>

            <!-- ลิงก์แนบ -->
            <a
              v-if="a.link"
              :href="a.link"
              target="_blank"
              rel="noopener noreferrer"
              class="mt-2 inline-flex max-w-full items-center gap-1.5 truncate text-[13px] font-semibold text-[#B91C1C] hover:underline"
            >
              <i class="bi bi-link-45deg"></i> {{ a.link }}
            </a>

            <!-- ผู้ประกาศ/ผู้แก้ (created_by_name = null ได้ ถ้าเป็นประกาศ seed เก่า หรือผู้ใช้ถูกลบ) -->
            <p class="mt-3 text-[12px] text-stone-400">
              <span>
                <i class="bi bi-person-circle mr-1"></i>
                {{ a.created_by_name || 'ไม่ทราบผู้ประกาศ' }}
              </span>
              <template v-if="a.updated_at && a.updated_at !== a.created_at">
                <span class="mx-1.5">·</span>
                <span>แก้ล่าสุด {{ fmtDateTime(a.updated_at) }}</span>
                <template v-if="a.updated_by_name">
                  <span class="mx-1">โดย {{ a.updated_by_name }}</span>
                </template>
              </template>
            </p>
          </div>

          <!-- ปุ่มจัดการ -->
          <div class="flex shrink-0 items-center gap-1.5">
            <template v-if="a.deleted_at">
              <button
                type="button"
                :disabled="actingId === a.id"
                @click="doRestore(a)"
                class="inline-flex items-center gap-1.5 rounded-xl bg-emerald-600 px-3.5 py-2 text-[13px] font-bold text-white transition-colors hover:bg-emerald-700 disabled:opacity-50"
              >
                <span
                  v-if="actingId === a.id"
                  class="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white/40 border-t-white"
                ></span>
                <i v-else class="bi bi-arrow-counterclockwise"></i>
                กู้คืน
              </button>
            </template>
            <template v-else>
              <button
                type="button"
                @click="openEdit(a)"
                class="inline-flex items-center gap-1.5 rounded-xl px-3.5 py-2 text-[13px] font-semibold text-stone-600 ring-1 ring-stone-200 transition-colors hover:bg-stone-50"
              >
                <i class="bi bi-pencil"></i> แก้ไข
              </button>
              <button
                type="button"
                :disabled="actingId === a.id"
                @click="confirmDelete(a)"
                class="inline-flex items-center gap-1.5 rounded-xl px-3.5 py-2 text-[13px] font-semibold text-[#B91C1C] ring-1 ring-red-200 transition-colors hover:bg-red-50 disabled:opacity-50"
              >
                <span
                  v-if="actingId === a.id"
                  class="h-3.5 w-3.5 animate-spin rounded-full border-2 border-[#B91C1C]/30 border-t-[#B91C1C]"
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
              @click="closeModal"
              class="rounded-xl p-2 text-stone-400 hover:bg-stone-100"
            >
              <i class="bi bi-x-lg"></i>
            </button>
          </div>

          <!-- Body -->
          <div class="custom-scrollbar flex-1 space-y-4 overflow-y-auto px-5 py-4">
            <div>
              <label class="mb-1 block text-xs font-semibold text-stone-500" for="ann-message">
                ข้อความประกาศ <span class="text-[#B91C1C]">*</span>
              </label>
              <textarea
                id="ann-message"
                v-model="form.message"
                rows="4"
                maxlength="1000"
                placeholder="เช่น ปิดโรงยิมชั่วคราววันที่ 30 ก.ย. เนื่องจากซ่อมแซมพื้น"
                class="w-full resize-none rounded-xl border border-stone-200 px-3.5 py-2.5 text-sm text-stone-800 outline-none transition-colors focus:border-[#B91C1C] focus:ring-2 focus:ring-[#B91C1C]/10"
              ></textarea>
              <p class="mt-1 text-right text-[11px] text-stone-400">
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
                  class="flex items-center gap-2 rounded-xl border px-3 py-2.5 text-left transition-colors"
                  :class="
                    form.priority === opt.value
                      ? 'border-[#B91C1C] bg-[#B91C1C]/5'
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
                      :class="form.priority === opt.value ? 'text-[#B91C1C]' : 'text-stone-700'"
                    >
                      {{ opt.label }}
                    </span>
                  </span>
                </button>
              </div>
              <p class="mt-1.5 text-[11px] text-stone-400">
                {{ PRIORITY_OPTIONS.find((o) => o.value === form.priority)?.hint }}
              </p>
            </div>

            <div>
              <label class="mb-1 block text-xs font-semibold text-stone-500" for="ann-link">
                ลิงก์แนบ <span class="text-stone-400">(ไม่บังคับ)</span>
              </label>
              <input
                id="ann-link"
                v-model="form.link"
                type="url"
                maxlength="500"
                placeholder="https://..."
                class="w-full rounded-xl border border-stone-200 px-3.5 py-2.5 text-sm text-stone-800 outline-none transition-colors focus:border-[#B91C1C] focus:ring-2 focus:ring-[#B91C1C]/10"
              />
              <p class="mt-1 text-[11px] text-stone-400">
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
              class="rounded-xl px-4 py-2.5 text-sm font-semibold text-stone-600 transition-colors hover:bg-stone-100 disabled:opacity-50"
            >
              ยกเลิก
            </button>
            <button
              type="button"
              @click="submitForm"
              :disabled="!canSubmit"
              class="inline-flex items-center gap-2 rounded-xl bg-[#B91C1C] px-5 py-2.5 text-sm font-bold text-white shadow-md transition-all hover:bg-[#991B1B] disabled:opacity-60"
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
