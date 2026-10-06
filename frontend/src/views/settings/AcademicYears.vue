<!-- eslint-disable vue/multi-word-component-names -- ชื่อตาม route/spec -->
<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import Swal from 'sweetalert2'
import { BRAND, WARN } from '@/constants/brand'
import { fmtDateShort } from '@/datetime'
import AppButton from '@/components/ui/AppButton.vue'
import AppChip from '@/components/ui/AppChip.vue'
import AppEmptyState from '@/components/ui/AppEmptyState.vue'
import { listYears, setCurrentYear, deleteYear, restoreYear } from '@/services/year'
import type { AcademicYear } from '@/types/academicYear'
import {
  YEAR_STATUS_TABS,
  yearScreenState,
  yearCoversToday,
  deleteBlockReason,
  setCurrentConfirmText,
} from '@/types/academicYear'
import PaginationBar from '@/components/PaginationBar.vue'

const router = useRouter()

const PAGE_SIZE = 20

const items = ref<AcademicYear[]>([])
const total = ref(0)
const page = ref(1)
const statusFilter = ref('active')
const isLoading = ref(true)
const hasError = ref(false)

/** สถานะหน้าจอ — ตรรกะอยู่ใน pure helper (types/academicYear.ts) ไม่ใช่ if ซ้อนในเทมเพลต */
const screen = computed(() =>
  yearScreenState({
    isLoading: isLoading.value,
    hasError: hasError.value,
    itemCount: items.value.length,
  }),
)

/**
 * โหลดล้มเหลว **รอบสอง** (มีข้อมูลค้างอยู่แล้ว) — ต่างจากรอบแรก
 * ⚠️ ต้องมีสาขานี้ ไม่งั้น Swal เด้งทับรายการเดิมทุกครั้งที่กดรีเฟรชพลาด
 *    และผู้ใช้ไม่รู้ว่ารายการที่เห็นอยู่เก่าแล้ว — คนละคลาสกับ skills.md
 *    เรื่อง "short-polling กลืน error" ที่ปล่อยให้ค้างเงียบ ๆ
 *
 * ⚠️ แต่ **ต้องไม่ทิ้งรายการเดิม** — ถ้าล้าง `items` ด้วย ผู้ใช้จะเสียทั้งตำแหน่งที่อ่านอยู่
 *    และบริบทว่าก่อนหน้ามีอะไร ⇒ เก็บไว้แล้วแค่ติดป้าย "ข้อมูลรอบก่อน"
 */
const staleError = ref(false)

async function load() {
  isLoading.value = true
  hasError.value = false
  const hadItems = items.value.length > 0
  try {
    const res = await listYears({
      status: statusFilter.value,
      limit: PAGE_SIZE,
      offset: (page.value - 1) * PAGE_SIZE,
    })
    items.value = res.items
    total.value = res.total
    staleError.value = false
  } catch (e) {
    // รอบแรก (ยังไม่มีอะไรโชว์) → แทนที่ทั้งหน้าด้วย error state
    // รอบหลัง → คงรายการเดิมไว้ + ติดป้ายว่าล้าสมัย (ดูเทมเพลต)
    staleError.value = hadItems
    if (!hadItems) {
      hasError.value = true
      items.value = []
      total.value = 0
    }
    Swal.fire({ icon: 'error', title: 'โหลดปีการศึกษาไม่สำเร็จ', text: errorText(e) })
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
// 🔴 **ห้ามเขียน formatter เองที่นี่** — `docs/glossary.md` §6 สั่งให้ใช้ `src/datetime.ts`
//    เท่านั้น และนี่คือรูปแบบ "วันที่ล้วนอ่านเป็นประโยค" ที่ตารางกฎในไฟล์นั้นระบุว่า
//    ต้องใช้ `fmtDateShort` ⇒ ได้ "16 พ.ค. 2569" (พ.ศ. มาเองจาก locale th-TH)
//    ⚠️ ก่อนหน้านี้เรพมี formatter แบบนี้ **ก๊อปกัน 11 ที่ใน 8 ไฟล์ และเพี้ยนกัน 3 แบบ**
//       (R5.5) — ห้ามเริ่มก๊อปใหม่ (ดูคอมเมนต์หัวไฟล์ `datetime.ts`)

/** ช่วงวันของปี — ปีที่ยังไม่ระบุวันเป็นสถานะ **ถูกต้อง** ไม่ใช่ข้อมูลขาด
 *  ⚠️ เขียนเป็น 3 กรณีแยกกัน (ไม่ใช้ `!s && !e` แล้ว cast) เพื่อให้ TypeScript
 *     narrow ได้เองโดยไม่ต้อง `as string` ซึ่งเป็นรอยที่ซ่อนบั๊กจริงไว้ */
function dateRangeText(y: AcademicYear): string {
  const s = y.start_date
  const e = y.end_date
  if (s && e) return `${fmtDateShort(s)} – ${fmtDateShort(e)}`
  if (s) return `เริ่ม ${fmtDateShort(s)} · ยังไม่ระบุวันสิ้นสุด`
  if (e) return `สิ้นสุด ${fmtDateShort(e)} · ยังไม่ระบุวันเริ่มต้น`
  return 'ยังไม่ระบุวันเปิด–ปิดปี'
}

/** วันนี้ (เวลาไทย) เป็น 'YYYY-MM-DD' — ใช้ Intl แทนการคำนวณ offset เอง */
function todayBkk(): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Bangkok' }).format(new Date())
}

// ===== การกระทำต่อแถว =====
const actingId = ref<number | null>(null)
const actingKind = ref<'current' | 'delete' | 'restore' | null>(null)

function busy(y: AcademicYear, kind: string): boolean {
  return actingId.value === y.id && actingKind.value === kind
}

/** ลบไม่ได้ + เหตุผล — ใช้ทั้ง disable ปุ่มและข้อความใต้ปุ่ม (ห้ามกดแล้วเด้ง error) */
function blockReason(y: AcademicYear): string {
  return deleteBlockReason(y)
}

async function doSetCurrent(y: AcademicYear) {
  const res = await Swal.fire({
    title: `ใช้ปี ${y.year_be} เป็นปีปัจจุบัน?`,
    text: setCurrentConfirmText(y),
    icon: 'question',
    showCancelButton: true,
    confirmButtonText: 'ใช้ปีนี้',
    confirmButtonColor: BRAND,
    cancelButtonText: 'ยกเลิก',
  })
  if (!res.isConfirmed) return

  actingId.value = y.id
  actingKind.value = 'current'
  try {
    await setCurrentYear(y.id)
    Swal.fire({
      icon: 'success',
      title: 'ตั้งเป็นปีปัจจุบันแล้ว',
      timer: 1200,
      showConfirmButton: false,
    })
    await load()
  } catch (e) {
    // ⚠️ ด่าน "ปีว่างตั้งเป็นปัจจุบันไม่ได้" เด้งมาที่นี่ — ข้อความยาวและบอกทางออก
    //    อยู่แล้ว ⇒ ส่งต่อทั้งดุ้น ไม่ตัดต่อ (text มี scroll ในตัวถ้ายาว)
    Swal.fire({ icon: 'error', title: 'ตั้งปีปัจจุบันไม่สำเร็จ', text: errorText(e) })
  } finally {
    actingId.value = null
    actingKind.value = null
  }
}

async function doDelete(y: AcademicYear) {
  const res = await Swal.fire({
    title: `ลบปี ${y.year_be}?`,
    text: 'ปีนี้จะถูกซ่อนจากรายการ (กู้คืนได้ภายหลัง) — สมาชิกและประวัติยังอยู่ครบ',
    icon: 'warning',
    showCancelButton: true,
    confirmButtonText: 'ลบปีนี้',
    confirmButtonColor: BRAND,
    cancelButtonText: 'ยกเลิก',
  })
  if (!res.isConfirmed) return

  actingId.value = y.id
  actingKind.value = 'delete'
  try {
    await deleteYear(y.id)
    Swal.fire({ icon: 'success', title: 'ลบแล้ว', timer: 1000, showConfirmButton: false })
    // ลบรายการสุดท้ายของหน้าสุดท้าย → ถอยกลับหนึ่งหน้า ไม่งั้น `load()` คืน 0 รายการ
    // ⇒ หน้าเปลี่ยนเป็น empty state แล้ว **แถบแบ่งหน้าหายไปด้วย** ⇒ ปีที่เหลือเข้าถึงไม่ได้
    if (items.value.length === 1 && page.value > 1) page.value -= 1
    await load()
  } catch (e) {
    Swal.fire({ icon: 'error', title: 'ลบไม่สำเร็จ', text: errorText(e) })
  } finally {
    actingId.value = null
    actingKind.value = null
  }
}

async function doRestore(y: AcademicYear) {
  const res = await Swal.fire({
    title: `กู้คืนปี ${y.year_be}?`,
    text: 'กลับมาเป็นปีธรรมดา — ต้องกด "ใช้เป็นปีปัจจุบัน" เองอีกครั้ง',
    icon: 'question',
    showCancelButton: true,
    confirmButtonText: 'กู้คืน',
    confirmButtonColor: WARN,
    cancelButtonText: 'ยกเลิก',
  })
  if (!res.isConfirmed) return

  actingId.value = y.id
  actingKind.value = 'restore'
  try {
    await restoreYear(y.id)
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
</script>

<template>
  <div>
    <!-- 🔴 ไม่มี <h1>/eyebrow ที่นี่ — `AppHeader` แสดงชื่อหน้าจาก `routeTitles` เป็น <h1> ให้แล้ว -->
    <div class="mb-6 flex flex-wrap items-center justify-end gap-3">
      <!-- ⚠️ ฟอร์มปีการศึกษาเป็น **หน้าเต็ม** ไม่ใช่แผ่น/โมดัล — ตาม skills.md #16
           (คีย์บอร์ดมือถือดันแผ่นจนไม่เห็นช่องกรอก · ปิดแล้วข้อมูลหาย · ปุ่มย้อนปิดแผ่น
           แทนที่จะย้อนฟอร์ม) ⇒ ที่นี่จึงมีแค่ลิงก์ไปหน้า `/settings/years/new` -->
      <AppButton variant="primary" :to="{ name: 'academic-year-new' }">
        <template #icon><i class="bi bi-plus-lg" aria-hidden="true" /></template>
        เพิ่มปีการศึกษา
      </AppButton>
    </div>

    <!-- แท็บกรองสถานะ -->
    <div class="mb-4 flex flex-wrap items-center gap-2">
      <AppChip
        v-for="t in YEAR_STATUS_TABS"
        :key="t.value"
        :label="t.label"
        :active="statusFilter === t.value"
        @click="changeStatus(t.value)"
      />
      <span v-if="!isLoading" class="ml-1 text-[13px] text-ink-3">
        <span class="tabular-nums">{{ total }}</span> ปีการศึกษา
      </span>
    </div>

    <!-- 📌 โหลดรอบสองล้ม — รายการที่เห็นอยู่ **เก่าแล้ว** ต้องบอก ไม่ใช่เงียบ
         (ต่างจากรอบแรกที่แทนที่ทั้งหน้าด้วย error state) -->
    <div
      v-if="staleError && items.length > 0"
      class="mb-3 flex flex-wrap items-center gap-3 rounded-card border border-line bg-canvas px-4 py-3"
    >
      <i class="bi bi-exclamation-triangle-fill text-danger" aria-hidden="true" />
      <p class="min-w-0 flex-1 text-[13px] font-semibold text-ink-1">
        รีเฟรชไม่สำเร็จ — รายการด้านล่างเป็นข้อมูลรอบก่อน
      </p>
      <AppButton variant="secondary" size="sm" @click="load">ลองใหม่</AppButton>
    </div>

    <!-- Skeleton ตอนโหลดครั้งแรก -->
    <div v-if="screen === 'loading'" class="space-y-3">
      <div
        v-for="i in 3"
        :key="i"
        class="animate-pulse rounded-card border border-line bg-surface p-4"
      >
        <div class="mb-3 h-4 w-24 rounded bg-line"></div>
        <div class="h-4 w-2/3 rounded bg-canvas"></div>
      </div>
    </div>

    <!-- Error (รอบแรก — ยังไม่มีอะไรให้โชว์) -->
    <div
      v-else-if="screen === 'error'"
      class="rounded-card border border-line bg-surface px-5 py-8 text-center"
    >
      <i class="bi bi-exclamation-triangle-fill mb-2 block text-2xl text-danger" aria-hidden="true" />
      <p class="text-sm font-semibold text-ink-1">โหลดปีการศึกษาไม่สำเร็จ</p>
      <div class="mt-3 flex justify-center">
        <AppButton variant="secondary" @click="load">ลองใหม่</AppButton>
      </div>
    </div>

    <!-- ว่าง -->
    <div v-else-if="screen === 'empty'" class="rounded-card border border-line bg-surface">
      <AppEmptyState
        icon="bi-mortarboard"
        :title="statusFilter === 'deleted' ? 'ไม่มีปีการศึกษาที่ถูกลบ' : 'ยังไม่มีปีการศึกษา'"
        :description="
          statusFilter === 'deleted'
            ? 'ปีการศึกษาที่ลบจะมาแสดงที่นี่ — กู้คืนได้ตลอด'
            : statusFilter === 'current'
              ? 'ยังไม่ได้ตั้งปีปัจจุบัน — ไปที่แท็บ «ทั้งหมด» แล้วกด «ใช้เป็นปีปัจจุบัน»'
              : 'กด «เพิ่มปีการศึกษา» เพื่อสร้างปีของเทอมถัดไป (สร้างล่วงหน้าได้ ไม่ต้องรู้วันเปิดเทอม)'
        "
      >
        <AppButton
          v-if="statusFilter !== 'deleted'"
          variant="primary"
          :to="{ name: 'academic-year-new' }"
        >
          <template #icon><i class="bi bi-plus-lg" aria-hidden="true" /></template>
          เพิ่มปีการศึกษา
        </AppButton>
      </AppEmptyState>
    </div>

    <!-- รายการ -->
    <div v-else class="space-y-3" :class="isLoading ? 'opacity-60 transition-opacity' : ''">
      <div
        v-for="y in items"
        :key="y.id"
        class="rounded-card border p-4 transition-colors"
        :class="
          y.deleted_at
            ? 'border-line bg-canvas'
            : y.is_current
              ? 'border-brand/30 bg-surface'
              : 'border-line bg-surface'
        "
      >
        <!-- ⚠️ มือถือต้อง "ซ้อน" ไม่ใช่ "วางข้างกัน" (บทเรียน PR #33): ปุ่มเป็น shrink-0
             จึงกินความกว้างตามเนื้อ ส่วนกล่องข้อความเป็น flex-1 (basis 0) ⇒ ถ้าอยู่แถว
             เดียวกันบนจอแคบ ข้อความจะเหลือไม่กี่ px แล้วขึ้นบรรทัดละตัวอักษร -->
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div class="w-full min-w-0 sm:w-auto sm:flex-1">
            <div class="mb-2 flex flex-wrap items-center gap-2">
              <span
                v-if="y.is_current"
                class="inline-flex items-center gap-1.5 rounded-full bg-brand-tint px-2.5 py-1 text-[11px] font-bold text-brand"
              >
                <span class="h-1.5 w-1.5 rounded-full bg-brand" aria-hidden="true" /> ปีปัจจุบัน
              </span>
              <span
                v-if="y.deleted_at"
                class="rounded-full bg-canvas px-2.5 py-1 text-[11px] font-bold text-ink-2"
              >
                ถูกลบแล้ว
              </span>
              <span
                v-else-if="!y.is_current && yearCoversToday(y, todayBkk())"
                class="rounded-full bg-ok-tint px-2.5 py-1 text-[11px] font-bold text-ok-strong ring-1 ring-ok-line"
              >
                <i class="bi bi-calendar-check mr-1" aria-hidden="true" />วันนี้อยู่ในช่วงนี้
              </span>
            </div>

            <h2
              class="break-words text-[15px] font-bold leading-snug"
              :class="y.deleted_at ? 'text-ink-2' : 'text-ink-1'"
            >
              {{ y.name }}
            </h2>

            <p class="mt-1.5 text-[13px] text-ink-2">
              <i class="bi bi-calendar-range mr-1" aria-hidden="true" />
              {{ dateRangeText(y) }}
              <span class="mx-1.5 text-ink-3">·</span>
              <!-- ⚠️ member_count นับ **ทุกสถานะ** ที่ยังไม่ถูกลบ ⇒ ปีที่จบไปแล้วยังโชว์
                   จำนวนจริงได้ ไม่ใช่ 0 (ตั้งใจ — ดูคอมเมนต์ใน types/academicYear.ts) -->
              <span class="tabular-nums">สมาชิก {{ y.member_count }} คน</span>
            </p>

            <!-- เหตุผลที่ลบไม่ได้ — บอก **ก่อน** กด ไม่ใช่ให้กดแล้วเด้ง error -->
            <p v-if="!y.deleted_at && blockReason(y)" class="mt-1.5 text-[12px] text-ink-3">
              <i class="bi bi-info-circle mr-1" aria-hidden="true" />{{ blockReason(y) }}
            </p>
          </div>

          <!-- ปุ่มจัดการ — มือถือเต็มความกว้าง + wrap ได้ -->
          <div class="flex w-full flex-wrap items-center gap-1.5 sm:w-auto sm:shrink-0">
            <template v-if="y.deleted_at">
              <AppButton
                variant="secondary"
                :loading="busy(y, 'restore')"
                :disabled="actingId === y.id"
                @click="doRestore(y)"
              >
                <template #icon>
                  <i class="bi bi-arrow-counterclockwise" aria-hidden="true" />
                </template>
                กู้คืน
              </AppButton>
            </template>
            <template v-else>
              <AppButton
                v-if="!y.is_current"
                variant="primary"
                :loading="busy(y, 'current')"
                :disabled="actingId === y.id"
                @click="doSetCurrent(y)"
              >
                <template #icon><i class="bi bi-check2-circle" aria-hidden="true" /></template>
                ใช้เป็นปีปัจจุบัน
              </AppButton>
              <!-- ⚠️ หน้าแก้ไขเป็น **หน้าเต็ม** ⇒ ส่งไปทั้ง id (ฟอร์มโหลดเองจาก URL)
                   ไม่ใช่ส่ง object ผ่าน router state (F5 แล้วหาย) -->
              <AppButton
                variant="secondary"
                :disabled="actingId === y.id"
                @click="router.push({ name: 'academic-year-edit', params: { id: String(y.id) } })"
              >
                <template #icon><i class="bi bi-pencil-square" aria-hidden="true" /></template>
                แก้ไข
              </AppButton>
              <AppButton
                variant="danger"
                :loading="busy(y, 'delete')"
                :disabled="actingId === y.id || !!blockReason(y)"
                :title="blockReason(y) || undefined"
                @click="doDelete(y)"
              >
                <template #icon><i class="bi bi-trash3" aria-hidden="true" /></template>
                ลบ
              </AppButton>
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
  </div>
</template>
