<!-- eslint-disable vue/multi-word-component-names -- ชื่อตาม route/spec -->
<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import Swal from 'sweetalert2'
import AppCard from '@/components/ui/AppCard.vue'
import AppButton from '@/components/ui/AppButton.vue'
import AppEmptyState from '@/components/ui/AppEmptyState.vue'
import { listYears } from '@/services/year'
import { getReconciliation } from '@/services/rollover'
import type { AcademicYear } from '@/types/academicYear'
import type { Reconciliation, ReconciliationPerson } from '@/types/rollover'
import {
  personName,
  reconciliationScreenState,
  reconcilePickerError,
  defaultReconcilePair,
  reconciliationSummaryText,
} from '@/types/rollover'
import { roleLabel } from '@/constants/roles'

/**
 * 📊 รายงานกระทบยอดรายชื่อระหว่างสองปีการศึกษา (P6)
 *
 * ⭐ ตอบข้อตัดสินใจ #8 "เด็กจบ/ย้ายออกต้องค้นชื่อเจอ" ได้จริง:
 *    ระบบบอกว่า **ใครหายจากปีก่อน** และ **ใครเพิ่มมาในปีใหม่** — แต่ **ไม่เดาสาเหตุ**
 *    (ย้ายออก / จบ / ตกหล่น) เพราะการเดาจะกลายเป็นข้อมูลผิดที่ไม่มีใครตรวจ
 *
 * ⚠️ หน้านี้เป็น read-only ล้วน — ไม่มี mutation ใด ๆ ⇒ กดผิดไม่มีทางทำข้อมูลเสีย
 * ⚠️ backend ต้องผ่านด่านคู่ (MANAGE_STUDENTS + โหมดส่วนกลาง) ⇒ nav ต้องตั้ง councilOnly ด้วย
 */

const years = ref<AcademicYear[]>([])
const fromYearId = ref<number | ''>('')
const toYearId = ref<number | ''>('')
const isLoading = ref(false)
const hasError = ref(false)
const result = ref<Reconciliation | null>(null)
const isYearsLoading = ref(true)

const screen = computed(() =>
  reconciliationScreenState({
    isLoading: isLoading.value,
    hasError: hasError.value,
    hasResult: result.value !== null,
  }),
)

const pickerError = computed(() => reconcilePickerError(years.value.length))

const canSearch = computed(
  () =>
    fromYearId.value !== '' &&
    toYearId.value !== '' &&
    fromYearId.value !== toYearId.value &&
    !isLoading.value,
)

const yearName = computed(() => {
  const m = new Map<number, string>()
  for (const y of years.value) m.set(y.id, y.name || `ปีการศึกษา ${y.year_be}`)
  return m
})

function yearLabel(id: number): string {
  return yearName.value.get(id) ?? `ปี #${id}`
}

async function loadYears() {
  isYearsLoading.value = true
  try {
    const res = await listYears({ status: 'active', limit: 200 })
    years.value = res.items
    const pair = defaultReconcilePair(res.items)
    fromYearId.value = pair.from
    toYearId.value = pair.to
  } catch (e) {
    hasError.value = true
    Swal.fire({
      icon: 'error',
      title: 'โหลดปีการศึกษาไม่สำเร็จ',
      text: errorText(e),
    })
  } finally {
    isYearsLoading.value = false
  }
}

async function search() {
  if (!canSearch.value) return
  isLoading.value = true
  hasError.value = false
  result.value = null
  try {
    result.value = await getReconciliation(fromYearId.value as number, toYearId.value as number)
  } catch (e) {
    hasError.value = true
    Swal.fire({ icon: 'error', title: 'ตรวจกระทบยอดไม่สำเร็จ', text: errorText(e) })
  } finally {
    isLoading.value = false
  }
}

function errorText(e: unknown): string {
  if (typeof e === 'string') return e
  if (e instanceof Error) return e.message
  return 'เกิดข้อผิดพลาดที่ไม่รู้จัก'
}

function personMeta(p: ReconciliationPerson): string {
  const parts: string[] = []
  if (p.room_code) parts.push(`ห้อง ${p.room_code}`)
  if (p.student_id) parts.push(`รหัส ${p.student_id}`)
  if (p.class_role) parts.push(roleLabel(p.class_role))
  return parts.join(' · ') || 'ไม่มีข้อมูลห้อง/รหัส'
}

onMounted(loadYears)
</script>

<template>
  <div>
    <!-- 🔴 ไม่มี <h1> — AppHeader แสดงชื่อหน้าจาก routeTitles ให้แล้ว -->
    <AppCard class="mb-5">
      <p class="mb-4 text-[13px] text-ink-2">
        เลือกสองปีการศึกษาเพื่อดูว่า
        <b class="text-ink-1">ใครหายจากปีก่อน</b> และ
        <b class="text-ink-1">ใครเพิ่มมาในปีใหม่</b> — ระบบบอกเฉพาะส่วนต่าง
        ไม่เดาสาเหตุ (ย้ายออก/จบ/ตกหล่น) ให้ผู้ใช้ตัดสินเอง
      </p>

      <div v-if="isYearsLoading" class="grid grid-cols-1 gap-3 sm:grid-cols-2" aria-busy="true">
        <div v-for="i in 2" :key="i" class="h-11 animate-pulse rounded-xl bg-line"></div>
      </div>

      <AppEmptyState
        v-else-if="pickerError"
        icon="bi-calendar-plus"
        title="ยังเปรียบเทียบไม่ได้"
        :description="pickerError"
        compact
      />

      <div v-else class="grid grid-cols-1 gap-3 sm:grid-cols-[1fr_auto_1fr_auto] sm:items-end">
        <label class="block">
          <span class="mb-1 block text-xs font-semibold text-ink-3">ปีก่อน</span>
          <select
            v-model="fromYearId"
            class="w-full rounded-xl border border-line bg-surface px-3 min-h-11 py-2 text-sm text-ink-1 outline-none focus:border-brand focus:ring-2 focus:ring-brand/10"
          >
            <option v-for="y in years" :key="y.id" :value="y.id">
              {{ y.name || `ปีการศึกษา ${y.year_be}` }}
            </option>
          </select>
        </label>
        <span class="hidden pb-3 text-ink-3 sm:block" aria-hidden="true">→</span>
        <label class="block">
          <span class="mb-1 block text-xs font-semibold text-ink-3">ปีหลัง</span>
          <select
            v-model="toYearId"
            class="w-full rounded-xl border border-line bg-surface px-3 min-h-11 py-2 text-sm text-ink-1 outline-none focus:border-brand focus:ring-2 focus:ring-brand/10"
          >
            <option v-for="y in years" :key="y.id" :value="y.id">
              {{ y.name || `ปีการศึกษา ${y.year_be}` }}
            </option>
          </select>
        </label>
        <AppButton
          variant="primary"
          :disabled="!canSearch"
          :loading="isLoading"
          @click="search"
        >
          <template #icon><i class="bi bi-search" aria-hidden="true" /></template>
          ตรวจกระทบยอด
        </AppButton>
      </div>
      <p v-if="!pickerError && fromYearId === toYearId" class="mt-2 text-[12px] font-semibold text-amber-600">
        เลือกสองปีให้ต่างกันก่อน
      </p>
    </AppCard>

    <!-- ยังไม่กด -->
    <AppCard v-if="screen === 'idle'" :padded="false">
      <AppEmptyState
        icon="bi-clipboard-data"
        title="ยังไม่มีผลกระทบยอด"
        description="เลือกปีก่อนและปีหลัง แล้วกด “ตรวจกระทบยอด”"
        compact
      />
    </AppCard>

    <!-- กำลังโหลด -->
    <div v-else-if="screen === 'loading'" class="space-y-3" aria-busy="true">
      <div v-for="i in 3" :key="i" class="animate-pulse rounded-card border border-line bg-surface p-5">
        <div class="mb-3 h-4 w-32 rounded bg-line"></div>
        <div class="h-3 w-2/3 rounded bg-line"></div>
      </div>
    </div>

    <!-- error -->
    <AppCard v-else-if="screen === 'error'" :padded="false">
      <AppEmptyState
        icon="bi-exclamation-triangle"
        title="ตรวจกระทบยอดไม่สำเร็จ"
        description="ลองอีกครั้ง — ถ้ายังไม่หาย ตรวจสอบการเชื่อมต่อกับระบบ"
        compact
      >
        <AppButton variant="secondary" size="sm" @click="search">ลองใหม่</AppButton>
      </AppEmptyState>
    </AppCard>

    <!-- ผล -->
    <template v-else-if="result">
      <div class="mb-4 rounded-card border border-line bg-canvas px-4 py-3 text-[13px] font-semibold text-ink-1">
        <i class="bi bi-clipboard-check mr-1 text-brand" aria-hidden="true"></i>
        {{ yearLabel(result.from_year_id) }} → {{ yearLabel(result.to_year_id) }}
        <span class="mx-1.5 text-ink-3">·</span>
        {{ reconciliationSummaryText(result) }}
      </div>

      <div class="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <!-- หายจากปีใหม่ -->
        <AppCard :padded="false">
          <div class="border-b border-line px-4 py-3">
            <h2 class="text-sm font-bold text-ink-1">
              <i class="bi bi-person-dash mr-1 text-danger" aria-hidden="true"></i>
              หายจากปีใหม่
              <span class="ml-1 text-ink-3">({{ result.missing_count }})</span>
            </h2>
            <p class="mt-0.5 text-[12px] text-ink-3">มีชื่อในปีก่อน แต่ไม่มีในปีใหม่</p>
          </div>
          <div v-if="result.missing.length === 0" class="px-4 py-6 text-center text-[13px] text-ink-3">
            ไม่มีใครหาย — รายชื่อครบทั้งสองปี
          </div>
          <ul v-else class="divide-y divide-line">
            <li v-for="p in result.missing" :key="`m-${p.user_id ?? p.student_id}`" class="px-4 py-3">
              <div class="text-sm font-semibold text-ink-1">{{ personName(p) }}</div>
              <div class="mt-0.5 text-[12px] text-ink-3">{{ personMeta(p) }}</div>
            </li>
          </ul>
        </AppCard>

        <!-- เพิ่มเข้ามา -->
        <AppCard :padded="false">
          <div class="border-b border-line px-4 py-3">
            <h2 class="text-sm font-bold text-ink-1">
              <i class="bi bi-person-plus mr-1 text-ok-strong" aria-hidden="true"></i>
              เพิ่มเข้ามา
              <span class="ml-1 text-ink-3">({{ result.added_count }})</span>
            </h2>
            <p class="mt-0.5 text-[12px] text-ink-3">มีชื่อในปีใหม่ แต่ไม่มีในปีก่อน</p>
          </div>
          <div v-if="result.added.length === 0" class="px-4 py-6 text-center text-[13px] text-ink-3">
            ไม่มีคนใหม่ — ไม่มีชื่อแปลกปลอมในปีใหม่
          </div>
          <ul v-else class="divide-y divide-line">
            <li v-for="p in result.added" :key="`a-${p.user_id ?? p.student_id}`" class="px-4 py-3">
              <div class="text-sm font-semibold text-ink-1">{{ personName(p) }}</div>
              <div class="mt-0.5 text-[12px] text-ink-3">{{ personMeta(p) }}</div>
            </li>
          </ul>
        </AppCard>
      </div>

      <p class="mt-4 text-[12px] text-ink-3">
        <i class="bi bi-info-circle mr-1"></i>
        “หาย” ไม่ได้แปลว่าตกหล่นเสมอ — เด็ก ม.6 ที่จบจะอยู่กลุ่มนี้ด้วย
        ตรวจรายชื่อที่คาดว่าจบแล้วก่อนสรุปว่าเป็นข้อมูลตกหล่น
      </p>
    </template>
  </div>
</template>
