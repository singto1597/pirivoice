<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import { RouterLink } from 'vue-router'
import Swal from 'sweetalert2'
import { BRAND, NEUTRAL } from '@/constants/brand'
import { listReports, resolveReport } from '@/services/board'
import {
  REPORT_REASON_LABELS,
  REPORT_REASONS,
  REPORT_STATUS_LABELS,
  type ReportItem,
  type ReportReason,
  type ReportStatus,
} from '@/types/board'
import { useAuthStore } from '@/stores/auth'
import { useNotificationsStore } from '@/stores/notifications'
import PaginationBar from '@/components/PaginationBar.vue'

/**
 * 🚩 คิวรายงานความไม่เหมาะสม (สภานักเรียน/แอดมิน)
 * - นักเรียนแจ้งคอมเมนต์ไม่เหมาะสม → สภารอจัดการ ไม่ต้องอ่านทุกคอมเมนต์
 * - รายการ open → [ซ่อนคอมเมนต์] (hide — ซ่อน subtree + ลด counter + ปิดรายงานทั้งหมดที่จุดนั้น)
 *                    [ปัดตก] (dismiss — ไม่ซ่อน ปิดรายงานนี้รายการเดียว)
 * - กรอง: status (open/resolved/dismissed), reason (หมวด), q (ค้นหา) + แบ่งหน้า
 */
const authStore = useAuthStore()
const notificationsStore = useNotificationsStore()

const reports = ref<ReportItem[]>([])
const total = ref(0)
const isLoading = ref(true)
const error = ref('')
const statusFilter = ref<'' | ReportStatus>('open') // default: คิวที่รอจัดการ
const reasonFilter = ref<'' | ReportReason>('')
const q = ref('')
const page = ref(1)
const pageSize = 15
const actingId = ref<number | null>(null) // กันกดซ้ำตอน resolve

const STATUS_TABS: Array<{ value: '' | ReportStatus; label: string; icon: string }> = [
  { value: '', label: 'ทั้งหมด', icon: 'bi bi-list-ul' },
  { value: 'open', label: 'รอจัดการ', icon: 'bi bi-hourglass-split' },
  { value: 'resolved', label: 'ซ่อนแล้ว', icon: 'bi bi-eye-slash' },
  { value: 'dismissed', label: 'ปัดตก', icon: 'bi bi-check2-circle' },
]

// ป้ายสถานะ (สีจำกัด: open → cardinal, resolved → emerald, dismissed → stone)
function reportStatusBadge(s: ReportStatus): string {
  if (s === 'open') return 'bg-brand/10 text-brand'
  if (s === 'resolved') return 'bg-emerald-100 text-emerald-700'
  return 'bg-stone-200 text-stone-500'
}

onMounted(load)

// ค้นหา debounce → กลับหน้า 1
let timer: ReturnType<typeof setTimeout> | undefined
watch(q, () => {
  clearTimeout(timer)
  timer = setTimeout(() => {
    page.value = 1
    load()
  }, 300)
})

function switchStatus(s: '' | ReportStatus) {
  statusFilter.value = s
  page.value = 1
  load()
}

function onReasonChange() {
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
    const res = await listReports({
      status: statusFilter.value || undefined,
      reason: reasonFilter.value || undefined,
      q: q.value.trim() || undefined,
      limit: pageSize,
      offset: (page.value - 1) * pageSize,
    })
    reports.value = res.items
    total.value = res.total
    // 🔔 เปิดคิวรายงานแล้ว → mark ว่าเห็นรายงานใหม่แล้ว (badge "จัดการรายงาน" ลด)
    void notificationsStore.read({ group_type: 'report' })
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'โหลดรายงานไม่สำเร็จ'
  } finally {
    isLoading.value = false
  }
}

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleString('th-TH', {
    timeZone: 'Asia/Bangkok',
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  })
}

// ✅ จัดการรายงาน: action='hide' (ซ่อนคอมเมนต์) / 'dismiss' (ปัดตก)
async function handleResolve(r: ReportItem, action: 'hide' | 'dismiss') {
  if (actingId.value) return
  const isHide = action === 'hide'
  const { value: note, isConfirmed } = await Swal.fire({
    title: isHide ? 'ซ่อนคอมเมนต์นี้?' : 'ปัดตก (ไม่ซ่อน)?',
    html: isHide
      ? 'คอมเมนต์ + รีพลายจะถูก<b>ซ่อนทันที</b> และรายงานอื่นๆ ที่จุดเดียวกันจะถูกปิด'
      : 'ปิดรายงานนี้รายการเดียว — <b>ไม่ซ่อนคอมเมนต์</b>',
    icon: 'warning',
    input: 'text',
    inputPlaceholder: 'หมายเหตุ (ไม่บังคับ)',
    inputAttributes: { maxlength: '500' },
    showCancelButton: true,
    confirmButtonText: isHide ? 'ซ่อนคอมเมนต์' : 'ปัดตก',
    confirmButtonColor: isHide ? BRAND : NEUTRAL,
    cancelButtonText: 'ยกเลิก',
  })
  if (!isConfirmed) return

  actingId.value = r.id
  try {
    await resolveReport(r.id, action, note ? String(note).trim() : undefined)
    Swal.fire({
      icon: 'success',
      title: isHide ? 'ซ่อนคอมเมนต์แล้ว' : 'ปัดตกแล้ว',
      text: isHide ? 'ลดจำนวนคอมเมนต์ + ปิดรายงานที่เกี่ยวข้องแล้ว' : 'คอมเมนต์ยังคงแสดงอยู่',
      timer: 1400,
      showConfirmButton: false,
    })
    load()
  } catch (e) {
    Swal.fire({ icon: 'error', title: 'ไม่สำเร็จ', text: e instanceof Error ? e.message : String(e) })
  } finally {
    actingId.value = null
  }
}
</script>

<template>
  <div>
    <!-- Editorial header -->
    <div class="flex flex-wrap items-end justify-between gap-3 mb-6">
      <div>
        <p class="text-[11px] font-bold uppercase tracking-widest text-brand mb-1.5">
          <i class="bi bi-flag-fill mr-1"></i> Moderation Queue
        </p>
        <h1 class="text-2xl sm:text-3xl font-bold tracking-tight text-stone-900 leading-tight">จัดการรายงาน</h1>
        <p class="text-sm text-stone-500 mt-1.5">คอมเมนต์ที่นักเรียนแจ้งความไม่เหมาะสม — สภานักเรียน/แอดมินตรวจสอบ</p>
      </div>
    </div>

    <!-- ไม่มีสิทธิ์ (กันผ่าน URL ตรง) -->
    <div v-if="!authStore.isCouncilAuthority" class="border border-stone-200 rounded-2xl bg-white p-12 text-center text-stone-400">
      <div class="text-4xl mb-2"><i class="bi bi-shield-lock"></i></div>
      <p class="text-stone-500">เฉพาะสภานักเรียน/แอดมินที่เข้าถึงหน้านี้ได้</p>
    </div>

    <template v-else>
      <!-- แถบกรอง + ค้นหา -->
      <div class="flex flex-wrap items-center gap-2 mb-5">
        <div class="flex gap-1 p-1 bg-stone-100 rounded-xl">
          <button
            v-for="t in STATUS_TABS"
            :key="t.value"
            type="button"
            @click="switchStatus(t.value)"
            class="px-3 py-2 rounded-lg text-sm font-medium transition flex items-center gap-1.5"
            :class="statusFilter === t.value ? 'bg-white border border-stone-200 text-brand' : 'text-stone-500 hover:text-stone-700'"
          >
            <i :class="t.icon"></i> {{ t.label }}
          </button>
        </div>

        <select v-model="reasonFilter" @change="onReasonChange"
          class="px-3 py-2.5 border border-stone-300 rounded-xl text-sm bg-white text-stone-600">
          <option value="">ทุกเหตุผล</option>
          <option v-for="r in REPORT_REASONS" :key="r" :value="r">{{ REPORT_REASON_LABELS[r] }}</option>
        </select>

        <div class="relative flex-1 min-w-[180px] sm:flex-none sm:w-64">
          <i class="bi bi-search absolute left-3 top-1/2 -translate-y-1/2 text-stone-400 text-sm"></i>
          <input
            v-model="q"
            type="search"
            placeholder="ค้นหา: ชื่อบอร์ด / คอมเมนต์..."
            class="w-full pl-9 pr-3 py-2.5 border border-stone-300 rounded-xl text-sm bg-white focus:ring-2 focus:ring-brand"
          />
        </div>

        <span class="text-sm text-stone-400 ml-auto tabular-nums">{{ total.toLocaleString('en-US') }} รายการ</span>
      </div>

      <!-- โหลด: skeleton รายการ -->
      <div v-if="isLoading" class="space-y-3">
        <div v-for="n in 5" :key="n" class="page-card p-4 border-l-4 border-l-stone-100 space-y-3">
          <div class="flex items-center gap-2">
            <div class="h-4 w-40 bg-stone-100 animate-pulse rounded"></div>
            <div class="h-4 w-16 bg-stone-100 animate-pulse rounded-full"></div>
            <div class="h-4 w-14 bg-stone-100 animate-pulse rounded-full"></div>
          </div>
          <div class="h-10 w-full bg-stone-100 animate-pulse rounded-lg"></div>
          <div class="h-3 w-1/3 bg-stone-100 animate-pulse rounded"></div>
        </div>
      </div>

      <!-- ข้อผิดพลาด -->
      <div v-else-if="error" class="border-2 border-dashed border-stone-200 rounded-2xl py-20 px-6 text-center">
        <i class="bi bi-wifi-off text-3xl text-stone-300 mb-3 inline-block"></i>
        <p class="text-stone-600 font-medium">{{ error }}</p>
        <button
          type="button"
          @click="load"
          class="mt-5 inline-flex items-center gap-2 rounded-lg bg-brand px-5 py-2.5 text-sm font-bold text-white hover:bg-brand-strong transition-colors"
        >
          <i class="bi bi-arrow-clockwise"></i> ลองอีกครั้ง
        </button>
      </div>

      <!-- ว่าง -->
      <div v-else-if="!reports.length" class="border border-dashed border-stone-200 rounded-2xl bg-white p-12 text-center text-stone-400">
        <div class="text-4xl mb-2"><i class="bi bi-flag"></i></div>
        <p v-if="statusFilter === 'open'" class="text-stone-500">ไม่มีรายงานค้าง — นักเรียนยังไม่แจ้ง หรือสภาจัดการหมดแล้ว</p>
        <p v-else class="text-stone-500">ไม่พบรายงานในเงื่อนไขนี้</p>
      </div>

      <div v-else class="space-y-3">
        <div
          v-for="r in reports"
          :key="r.id"
          :data-testid="'report-card-' + r.id"
          class="page-card p-4 border-l-4"
          :class="r.status === 'open' ? 'border-l-brand' : r.status === 'resolved' ? 'border-l-emerald-500' : 'border-l-stone-200'"
        >
          <div class="flex flex-wrap items-center gap-2 mb-2">
            <RouterLink
              :to="{ name: 'board-detail', params: { id: r.board_id } }"
              class="text-xs font-semibold text-stone-600 hover:text-brand hover:underline flex items-center gap-1"
            >
              <i class="bi bi-chat-dots"></i> {{ r.board_title }}
            </RouterLink>
            <span class="px-2 py-0.5 bg-stone-100 text-stone-600 text-[11px] rounded-full font-medium">
              {{ REPORT_REASON_LABELS[r.reason] }}
            </span>
            <span class="px-2 py-0.5 text-[11px] rounded-full font-medium" :class="reportStatusBadge(r.status)">
              {{ REPORT_STATUS_LABELS[r.status] }}
            </span>
          </div>

          <p class="text-sm text-stone-700 bg-stone-50 rounded-lg px-3 py-2.5 whitespace-pre-wrap break-words">
            “{{ r.comment_body }}”
          </p>

          <div class="flex flex-wrap items-center justify-between gap-2 mt-2.5">
            <p class="text-xs text-stone-400">
              แจ้งโดย {{ r.reporter_name || 'ไม่ระบุชื่อ' }} · {{ fmtDate(r.created_at) }}
              <span v-if="r.detail" class="block text-stone-500 mt-0.5"><i class="bi bi-info-circle mr-1"></i>{{ r.detail }}</span>
            </p>

            <!-- ปุ่มจัดการ (เฉพาะ open) -->
            <div v-if="r.status === 'open'" class="flex gap-2 shrink-0">
              <button
                type="button"
                :disabled="actingId === r.id"
                data-testid="dismiss-btn"
                @click="handleResolve(r, 'dismiss')"
                class="px-3 py-1.5 text-xs font-medium rounded-lg bg-stone-100 text-stone-600 hover:bg-stone-200 disabled:opacity-40"
              >
                <i class="bi bi-check2-circle mr-1"></i> ปัดตก
              </button>
              <button
                type="button"
                :disabled="actingId === r.id"
                data-testid="hide-btn"
                @click="handleResolve(r, 'hide')"
                class="px-3 py-1.5 text-xs font-medium rounded-lg bg-brand text-white hover:bg-brand-strong disabled:opacity-40"
              >
                <i class="bi bi-eye-slash mr-1"></i> ซ่อนคอมเมนต์
              </button>
            </div>
            <p v-else-if="r.resolution_note" class="text-xs text-stone-400 shrink-0">
              <i class="bi bi-journal-check mr-1"></i>{{ r.resolution_note }}
            </p>
          </div>
        </div>
      </div>

      <PaginationBar :total="total" :page="page" :page-size="pageSize" :loading="isLoading" @page-change="onPageChange" />
    </template>
  </div>
</template>
