<script setup lang="ts">
import { ref, onMounted, computed, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { listIssues } from '@/services/issue'
import {
  MAIN_CATEGORIES,
  MAIN_CATEGORY_LABELS,
  subcategoryLabel,
  LEVEL_LABELS,
  LEVEL_ORDER,
  DESTINATION_LABELS,
  categoryLabel,
  userPyramidLevel,
  type Issue,
  type IssueLevel,
  type MainCategory,
} from '@/types/issue'
import { statusShort } from '@/constants/status'
import { useAuthStore } from '@/stores/auth'
import IssueListToolbar from '@/components/IssueListToolbar.vue'
import PaginationBar from '@/components/PaginationBar.vue'
import ApproveBoardModal from '@/components/boards/ApproveBoardModal.vue'
import PageHeader from '@/components/ui/PageHeader.vue'
import AppCard from '@/components/ui/AppCard.vue'
import AppChip from '@/components/ui/AppChip.vue'
import AppButton from '@/components/ui/AppButton.vue'
import AppEmptyState from '@/components/ui/AppEmptyState.vue'
import StatusBadge from '@/components/ui/StatusBadge.vue'
import { fmtRelative } from '@/datetime'

const authStore = useAuthStore()
const route = useRoute()
const router = useRouter()
const issues = ref<Issue[]>([])
const total = ref(0) // จำนวนทั้งหมดที่ตรงเงื่อนไข (จาก envelope)
const isLoading = ref(true)
const error = ref('')
// 🏛️ อนุมัติเผยแพร่ PIRI Board (สภานักเรียน/แอดมิน) — modal ตั้งค่าตัวเลือกโหวต/คอมเมนต์
const approveTarget = ref<Issue | null>(null)
const approveOpen = ref(false)

// สภานักเรียน/แอดมิน อนุมัติเรื่องที่ขอเผยแพร่ (vote/talk) และยังไม่ถูกอนุมัติ/ปิด
function canApprove(i: Issue): boolean {
  if (!authStore.isCouncilAuthority) return false
  if (i.requested_destination === 'normal') return false
  if (i.published_board_id) return false
  return !['resolved', 'cancelled', 'rejected'].includes(i.status)
}

function openApprove(i: Issue) {
  approveTarget.value = i
  approveOpen.value = true
}

function onApproved(boardId: number) {
  router.push({ name: 'board-detail', params: { id: boardId } })
}
const q = ref('') // คำค้นหา
const sort = ref<'asc' | 'desc'>('desc') // ใหม่ไปเก่า (default)
const page = ref(1)
const pageSize = 20
const statusFilter = ref('not_resolved') // default: ซ่อนเรื่องที่เสร็จแล้ว (ดูเฉพาะยังไม่เสร็จ)
const mainCategoryFilter = ref('') // '' = ทุกหมวด, suggestion/wellbeing/report
const subcategoryFilter = ref('') // '' = ทุกหมวดย่อย, academic/physical_health/...

// สถานะ "ยังไม่เสร็จ" = pending + in_progress + escalated (ให้ server กรอง — กันหน้าว่างตอน 100 เรื่องแรกเสร็จหมด)
const NOT_RESOLVED_STATUSES = 'pending,in_progress,escalated'

// 🧭 ระดับที่อยากดู (มองลงตามพีระมิด) — เฉพาะผู้ที่มีระดับ (teacher/student ไม่มี → ซ่อนกล่อง)
// ระดับตัวเอง = ระดับสูงสุดจาก roles; selectable = ตั้งแต่ระดับตัวเองลงล่าง (room→[room], level→[room,level], council→[room,level,council])
const myLevel = computed<IssueLevel | ''>(() => userPyramidLevel(authStore.roles))
const selectableLevels = computed<IssueLevel[]>(() => {
  if (!myLevel.value) return []
  return LEVEL_ORDER.slice(0, LEVEL_ORDER.indexOf(myLevel.value) + 1)
})
const hasLevelChoice = computed(() => selectableLevels.value.length > 1)
// ระดับที่ติ๊กอยู่ — default = ระดับตัวเองเท่านั้น (ดูเฉพาะเรื่องระดับตัวเอง เหมือนเดิม)
const levelSelections = ref<IssueLevel[]>([])
watch(
  myLevel,
  (lv) => {
    levelSelections.value = lv ? [lv] : []
  },
  { immediate: true },
)
// ตัวกรองระดับ "ต่างจากค่าเริ่มต้น" → นับเป็น active filter (badge)
const levelsChanged = computed(() => {
  if (!hasLevelChoice.value || !myLevel.value) return false
  const def = [myLevel.value]
  return (
    levelSelections.value.length !== def.length ||
    levelSelections.value.some((x, i) => x !== def[i])
  )
})
function toggleLevel(lv: IssueLevel) {
  levelSelections.value = levelSelections.value.includes(lv)
    ? levelSelections.value.filter((x) => x !== lv)
    : [...levelSelections.value, lv]
  page.value = 1
  load()
}

// จำนวนตัวกรองที่ active (badge บนปุ่ม filter) — ไม่นับ default 'not_resolved' และตัวกรองหน้าที่
const activeFilters = computed(
  () =>
    (statusFilter.value !== 'not_resolved' ? 1 : 0) +
    (mainCategoryFilter.value ? 1 : 0) +
    (subcategoryFilter.value ? 1 : 0) +
    (levelsChanged.value ? 1 : 0),
)

/**
 * 🏷️ ชิปสถานะ — แทน `<select>` ที่ต้องกดเปิดดูทีละครั้ง
 *
 * ⚠️ `not_resolved` เป็น **ค่าเริ่มต้นของหน้านี้** ไม่ใช่สถานะจริงในฐานข้อมูล — มันคือ
 *    "ส่ง 3 สถานะให้ server กรอง" (ดู `NOT_RESOLVED_STATUSES`) ⇒ ต้องมีชิปของตัวเอง
 *    ไม่ใช่ให้ผู้ใช้ติ๊ก 3 อัน
 * ⚠️ ป้ายทุกตัวมาจาก `statusShort()` / `STATUS_LABELS` ที่เดียว — ห้ามพิมพ์คำสถานะซ้ำที่นี่
 */
const STATUS_FILTERS = [
  { value: 'not_resolved', label: 'ยังไม่เสร็จ' },
  { value: '', label: 'ทุกสถานะ' },
  { value: 'pending', label: statusShort('pending') },
  { value: 'in_progress', label: statusShort('in_progress') },
  { value: 'escalated', label: statusShort('escalated') },
  { value: 'resolved', label: statusShort('resolved') },
  { value: 'rejected', label: statusShort('rejected') },
  { value: 'cancelled', label: statusShort('cancelled') },
] as const

/** ผู้ใช้ล้าง/เปลี่ยนตัวกรองจนไม่เหลือเงื่อนไขเริ่มต้นแล้วหรือยัง (ใช้ตัดสินข้อความ+ปุ่มของ empty state) */
const hasAnyFilter = computed(() => activeFilters.value > 0 || Boolean(q.value.trim()))

/**
 * ซ่อนแถบเครื่องมือเมื่อ **ไม่มีอะไรให้กรองเลย** — กล่องค้นหาในลิสต์ว่างคือความรกที่ audit ฟ้อง
 *
 * 🔴 แต่ **ห้ามซ่อนเมื่อมีตัวกรองค้างอยู่** — ไม่งั้นผู้ใช้ที่กรองจนได้ 0 ผลลัพธ์
 *    จะไม่เหลือทางล้างตัวกรองในหน้าเลย ⇒ ติดอยู่ในลิสต์ว่างถาวร
 */
const showToolbar = computed(
  () => isLoading.value || issues.value.length > 0 || hasAnyFilter.value,
)

/** ล้างตัวกรองทั้งหมดกลับค่าเริ่มต้นของหน้านี้ — ทางออกของ empty state */
function clearFilters() {
  q.value = ''
  statusFilter.value = 'not_resolved'
  mainCategoryFilter.value = ''
  subcategoryFilter.value = ''
  levelSelections.value = myLevel.value ? [myLevel.value] : []
  const query = { ...route.query }
  delete query.category
  delete query.main_category
  void router.replace({ query })
  page.value = 1
  load()
}

// ⭐ หมวดหน้าที่ที่ฉันรับผิดชอบ (จาก /auth/me) — council_member / level_vice_president เท่านั้น
// Backend บังคับ exact-level ผ่าน received=true อยู่แล้ว — ตัวกรองนี้แค่ "หมวด" ไม่ได้ขยายขอบเขตระดับ
const myResponsibilities = computed(() => authStore.responsibilities || [])
const hasResponsibilities = computed(() => myResponsibilities.value.length > 0)

// หาหมวดหลักของหมวดย่อย (แต่ละหมวดย่อยอยู่ใต้หมวดหลักเดียว)
function mainOfCategory(cat: string): string {
  for (const mc of Object.keys(MAIN_CATEGORIES) as MainCategory[]) {
    if (MAIN_CATEGORIES[mc].subcategories[cat]) return mc
  }
  return ''
}

// ตั้งค่าเริ่มต้นจาก URL (คลิกจาก Dashboard → มาเจอหมวด/หมวดย่อยนั้นเลย)
const initMainCat = typeof route.query.main_category === 'string' ? route.query.main_category : ''
const initCat = typeof route.query.category === 'string' ? route.query.category : ''

// URL มีแค่ ?category= (ไม่มี main_category) → หาหมวดหลักให้เอง เพื่อให้ dropdown ตรงกัน
const effectiveMain = initMainCat || mainOfCategory(initCat)
if (effectiveMain) mainCategoryFilter.value = effectiveMain

// หมวดย่อยต้อง belong กับหมวดหลักที่เลือก → ถ้าไม่ (เช่น แก้ URL มือ) ให้ตัดทิ้ง เหมือนที่ watch ทำ
if (initCat && mainOfCategory(initCat) === effectiveMain) {
  subcategoryFilter.value = initCat
}

// Default: กรองตามหน้าที่อัตโนมัติ (ยกเว้นกดเข้ามาจากลิงก์ที่ระบุหมวดเจาะจง — ให้เกียรติ URL
// เช่น คลิกจาก Dashboard มาเจอหมวดนั้นเลย ไม่ถูกหน้าที่แทรกแซง)
const respFilterOn = ref(hasResponsibilities.value && !(Boolean(effectiveMain) || Boolean(initCat)))

// สลับ "กรองตามหน้าที่ของฉัน" เปิด/ปิด
// - เปิด : ส่งหมวด = หน้าที่รวมกัน (comma) — เห็นเฉพาะเรื่องตรงหน้าที่
// - ปิด : "แสดงทั้งหมดในระดับของฉัน" — เห็นทุกหมวดในระดับตัวเอง (backend ยังบังคับ exact-level)
// ทั้ง 2 ทิศ เคลียร์ตัวกรองหมวด manual + URL เพื่อไม่ให้ state ค้าง/ตีกัน (load ใช้ path ของ resp)
function toggleResponsibilityFilter(on: boolean) {
  if (respFilterOn.value === on) return
  respFilterOn.value = on
  subcategoryFilter.value = ''
  mainCategoryFilter.value = ''
  const query = { ...route.query }
  delete query.category
  delete query.main_category
  router.replace({ query })
  page.value = 1
  load()
}

// หมวดย่อยที่เลือกได้ (ตามหมวดหลักที่เลือกอยู่)
const availableSubcategories = computed(() => {
  if (!mainCategoryFilter.value) return []
  const info = MAIN_CATEGORIES[mainCategoryFilter.value as MainCategory]
  if (!info) return []
  return Object.entries(info.subcategories).map(([value, label]) => ({ value, label }))
})

// URL เป็น source of truth: แก้ URL เอง / back-forward → ปรับ filter ตาม URL (กลับหน้า 1)
watch(
  () => [route.query.main_category, route.query.category],
  ([mc, cat]) => {
    const mainV = typeof mc === 'string' ? mc : ''
    const catV = typeof cat === 'string' ? cat : ''
    // มีหมวดระบุใน URL (กดมาจากที่อื่น/แชร์ลิงก์) → ปิดตัวกรองหน้าที่อัตโนมัติ ให้เกียรติ URL
    if ((mainV || catV) && respFilterOn.value) {
      respFilterOn.value = false
    }
    const mainChanged = mainV !== mainCategoryFilter.value
    const catChanged = catV !== subcategoryFilter.value
    if (mainChanged || catChanged) {
      // หมวดย่อยต้อง belong กับหมวดหลักที่เลือก → ถ้าไม่ (เช่น แก้ URL มือ) ให้ตัดทิ้ง
      let validCat = ''
      if (mainV && catV) {
        validCat = mainOfCategory(catV) === mainV ? catV : ''
      }
      mainCategoryFilter.value = mainV
      subcategoryFilter.value = validCat
      page.value = 1
      load()
    }
  },
)

// เลือกหมวดจาก dropdown → เขียนกลับไปที่ URL (refresh/แชร์ URL แล้วได้ข้อมูลตรงกัน)
function onMainCategoryChange() {
  // เปลี่ยนหมวดหลัก → หมวดย่อยเดิมอยู่คนละหมวด → เคลียร์
  subcategoryFilter.value = ''
  const query = { ...route.query }
  if (mainCategoryFilter.value) {
    query.main_category = mainCategoryFilter.value
  } else {
    delete query.main_category
  }
  delete query.category
  router.replace({ query })
  page.value = 1
  load()
}

function onSubcategoryChange() {
  const query = { ...route.query }
  if (subcategoryFilter.value) {
    query.category = subcategoryFilter.value
  } else {
    delete query.category
  }
  router.replace({ query })
  page.value = 1
  load()
}

// เปลี่ยน filter ฝั่ง dropdown (ระดับ/สถานะ) → กลับหน้า 1 แล้วโหลด
function onFilterChange() {
  page.value = 1
  load()
}

/**
 * กดชิปสถานะ
 *
 * ⚠️ แยกเป็นเมธอด **ไม่เขียนหลายประโยคใน `@click` ของเทมเพลต** — `prettier` จะลอก `;`
 *    ระหว่างประโยคออก (skills #10) แล้วเทมเพลตที่คอมไพล์แล้วกลายเป็นนิพจน์เดียวที่พัง
 */
function onStatusChip(value: string) {
  statusFilter.value = value
  onFilterChange()
}

// search / sort เปลี่ยน (จาก Toolbar) → กลับหน้า 1 แล้วโหลด
function onToolbarChange() {
  page.value = 1
  load()
}

// เปลี่ยนหน้า (จาก Pagination)
function onPageChange(n: number) {
  page.value = n
  load()
}

// ตัวเลือกหมวดหลัก (จาก types/issue.ts)
const mainCategoryOptions = [
  { value: 'suggestion', label: MAIN_CATEGORY_LABELS.suggestion },
  { value: 'wellbeing', label: MAIN_CATEGORY_LABELS.wellbeing },
  { value: 'report', label: MAIN_CATEGORY_LABELS.report },
]

onMounted(load)

async function load() {
  isLoading.value = true
  error.value = ''
  try {
    // 🧭 ระดับที่อยากดู: เลือกได้เฉพาะระดับ ≤ ระดับตัวเอง (ระดับที่สูงกว่ามองลงดูระดับล่างได้)
    // ไม่เลือกเลย → ไม่เห็นเรื่องใด (server ไม่มีค่า "none" — default คือระดับตัวเอง)
    if (hasLevelChoice.value && levelSelections.value.length === 0) {
      issues.value = []
      total.value = 0
      return
    }
    const levelsParam = hasLevelChoice.value ? levelSelections.value.join(',') : undefined
    // "not_resolved" = ส่งสถานะที่ยังไม่เสร็จให้ server กรอง (ไม่โหลดทุกสถานะแล้วตัด client)
    const raw = statusFilter.value === 'not_resolved'
    // หมวดที่ใช้กรอง: ปกติ = ตัวกรอง manual; ถ้าเปิด "กรองตามหน้าที่" → ใช้หมวดหน้าที่รวม (comma)
    // ⚠️ ไม่ส่ง main_category คู่กับหมวดหลายค่า เพราะหน้าที่ลากข้าม 3 หมวดหลัก — ปล่อยให้ backend กรอง category ตรง ๆ
    const mainCat =
      respFilterOn.value && hasResponsibilities.value
        ? undefined
        : mainCategoryFilter.value || undefined
    const cat =
      respFilterOn.value && hasResponsibilities.value
        ? myResponsibilities.value.join(',')
        : subcategoryFilter.value || undefined
    const res = await listIssues({
      received: true,
      status: raw ? NOT_RESOLVED_STATUSES : statusFilter.value || undefined,
      main_category: mainCat,
      category: cat,
      levels: levelsParam,
      q: q.value.trim() || undefined,
      sort: sort.value,
      limit: pageSize,
      offset: (page.value - 1) * pageSize,
    })
    issues.value = res.items
    total.value = res.total
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'โหลดข้อมูลไม่สำเร็จ'
  } finally {
    isLoading.value = false
  }
}
</script>

<template>
  <div>
    <PageHeader title="เรื่องที่รับ / ระดับฉัน" description="เรื่องที่รอคุณและทีมรับผิดชอบดำเนินการ" />

    <!-- ⭐ ตัวกรองตามหน้าที่ (เฉพาะ council_member / level_vice_president ที่มีหน้าที่รับผิดชอบ)
         เป็นการกรอง "หมวด" เท่านั้น — ขอบเขตระดับยังเป็น exact-level จาก backend (received=true) เสมอ -->
    <div
      v-if="hasResponsibilities"
      class="mb-3 flex flex-wrap items-center gap-x-3 gap-y-2 rounded-card border border-line bg-surface px-4 py-3"
    >
      <span class="flex items-center gap-1.5 text-[13px] font-bold text-ink-1">
        <i :class="['bi', respFilterOn ? 'bi-funnel-fill' : 'bi-funnel', 'text-brand']"></i>
        กรองตามหน้าที่ของฉัน
      </span>

      <!-- เปิดอยู่ → แสดงหมวดที่รับผิดชอบ + ปุ่ม "แสดงทั้งหมด" -->
      <template v-if="respFilterOn">
        <span
          v-for="code in myResponsibilities"
          :key="code"
          class="rounded-full bg-brand-tint px-2.5 py-0.5 text-[11px] font-semibold text-brand"
        >
          {{ categoryLabel(code) }}
        </span>
        <AppButton
          variant="text"
          size="sm"
          class="ml-auto"
          @click="toggleResponsibilityFilter(false)"
        >
          <template #icon><i class="bi bi-x-lg" /></template>
          แสดงทั้งหมดในระดับของฉัน
        </AppButton>
      </template>

      <!-- ปิดอยู่ → ชวนกรองเฉพาะเรื่องในหน้าที่ -->
      <AppButton
        v-else
        variant="secondary"
        size="sm"
        class="ml-auto"
        @click="toggleResponsibilityFilter(true)"
      >
        <template #icon><i class="bi bi-funnel-fill" /></template>
        กรองเฉพาะเรื่องในหน้าที่ของฉัน
      </AppButton>
    </div>

    <!-- เครื่องมือ + ชิปสถานะ — ซ่อนทั้งแถบเมื่อไม่มีอะไรให้กรอง (ดู `showToolbar`) -->
    <div v-if="showToolbar" class="mb-3 space-y-3">
      <IssueListToolbar
        v-model:q="q"
        v-model:sort="sort"
        :total="total"
        :count="issues.length"
        :active-filters="activeFilters"
        :loading="isLoading"
        @change="onToolbarChange"
      >
        <template #filters>
          <div class="space-y-3">
            <div>
              <label class="mb-1.5 block text-xs font-semibold text-ink-2">หมวดหลัก</label>
              <select
                v-model="mainCategoryFilter"
                @change="onMainCategoryChange"
                :disabled="respFilterOn && hasResponsibilities"
                class="field"
              >
                <option value="">
                  {{ respFilterOn && hasResponsibilities ? 'กรองตามหน้าที่อยู่' : 'ทุกหมวดหลัก' }}
                </option>
                <option v-for="mc in mainCategoryOptions" :key="mc.value" :value="mc.value">
                  {{ mc.label }}
                </option>
              </select>
            </div>
            <div>
              <label class="mb-1.5 block text-xs font-semibold text-ink-2">หมวดย่อย</label>
              <select
                v-model="subcategoryFilter"
                @change="onSubcategoryChange"
                :disabled="(respFilterOn && hasResponsibilities) || !mainCategoryFilter"
                class="field"
              >
                <option value="">
                  {{
                    respFilterOn && hasResponsibilities
                      ? 'ใช้หน้าที่ด้านบน'
                      : mainCategoryFilter
                        ? 'ทุกหมวดย่อย'
                        : 'เลือกหมวดหลักก่อน'
                  }}
                </option>
                <option v-for="sc in availableSubcategories" :key="sc.value" :value="sc.value">
                  {{ sc.label }}
                </option>
              </select>
            </div>
            <!-- 🧭 ระดับที่อยากดู (ติ๊กได้ — ผู้ระดับสูงมองลงตามพีระมิด; default = ระดับตัวเอง)
                 ⚠️ ยังเป็น checkbox ไม่ใช่ชิป เพราะ **เลือกได้หลายระดับพร้อมกัน** ซึ่งชิป
                    (เลือกอันเดียว) สื่อผิด — ใช้ชิปเฉพาะที่เลือกได้ทีละค่า -->
            <div v-if="hasLevelChoice">
              <label class="mb-1.5 block text-xs font-semibold text-ink-2">ระดับที่อยากดู</label>
              <div class="space-y-1.5">
                <label
                  v-for="lv in selectableLevels"
                  :key="lv"
                  class="flex cursor-pointer select-none items-center gap-2 text-sm text-ink-1"
                >
                  <input
                    type="checkbox"
                    :checked="levelSelections.includes(lv)"
                    @change="toggleLevel(lv)"
                    class="h-4 w-4 rounded border-line accent-brand"
                  />
                  <span>{{ LEVEL_LABELS[lv] }}</span>
                  <span
                    v-if="lv === myLevel"
                    class="rounded-full bg-brand-tint px-1.5 py-px text-[10px] font-semibold text-brand"
                  >
                    ระดับฉัน
                  </span>
                </label>
              </div>
              <p v-if="levelSelections.length === 0" class="mt-1.5 text-[11px] text-ink-3">
                ยังไม่เลือกระดับ → จะไม่เห็นเรื่องใด (ติ๊กอย่างน้อย 1 ระดับเพื่อดู)
              </p>
              <p v-else class="mt-1.5 text-[11px] text-ink-3">
                ระดับที่สูงกว่ามองลงดูระดับล่างได้ (ตามพีระมิด)
              </p>
            </div>
          </div>
        </template>
      </IssueListToolbar>

      <!-- 🏷️ ชิปสถานะ — เลื่อนแนวนอน ไม่ตัดบรรทัด -->
      <div class="chip-row">
        <AppChip
          v-for="f in STATUS_FILTERS"
          :key="f.value"
          :label="f.label"
          :active="statusFilter === f.value"
          @click="onStatusChip(f.value)"
        />
      </div>
    </div>

    <!-- โหลดข้อมูล: skeleton รายการ -->
    <AppCard v-if="isLoading">
      <div class="animate-pulse divide-y divide-line">
        <div v-for="n in 5" :key="n" class="flex items-start gap-3 py-4">
          <div class="h-10 w-10 rounded-full bg-canvas"></div>
          <div class="flex-1 space-y-2 pt-1">
            <div class="h-3 w-1/3 rounded bg-canvas"></div>
            <div class="h-3 w-2/3 rounded bg-canvas"></div>
          </div>
          <div class="h-6 w-16 rounded-full bg-canvas"></div>
        </div>
      </div>
    </AppCard>

    <!-- โหลดไม่สำเร็จ -->
    <AppCard v-else-if="error">
      <AppEmptyState icon="bi-wifi-off" title="โหลดรายการเรื่องไม่สำเร็จ" :description="error">
        <AppButton variant="secondary" size="sm" @click="load">
          <template #icon><i class="bi bi-arrow-clockwise" /></template>
          ลองอีกครั้ง
        </AppButton>
      </AppEmptyState>
    </AppCard>

    <!-- ว่างเพราะ **กรองแล้วไม่เหลือ** — ต้องมีทางล้างตัวกรอง ไม่ใช่บอกแค่ "ไม่พบ" -->
    <AppCard v-else-if="!issues.length && hasAnyFilter">
      <AppEmptyState
        icon="bi-search"
        title="ไม่พบเรื่องในเงื่อนไขที่เลือก"
        description="ลองลดตัวกรองลง หรือกลับไปดูเรื่องที่ยังไม่เสร็จทั้งหมด"
      >
        <AppButton variant="secondary" size="sm" @click="clearFilters"> ล้างตัวกรอง </AppButton>
      </AppEmptyState>
    </AppCard>

    <!-- ว่างเพราะ **ไม่มีเรื่องค้างในระดับที่เลือก** — คนละความหมายกับ "กรองไม่เจอ" -->
    <AppCard v-else-if="!issues.length">
      <AppEmptyState
        icon="bi-check2-circle"
        title="ไม่มีเรื่องค้างอยู่ที่ระดับนี้"
        description="เมื่อมีเรื่องส่งมาถึงระดับที่คุณเลือก จะขึ้นที่นี่"
      />
    </AppCard>

    <!-- รายการ -->
    <AppCard v-else :padded="false">
      <TransitionGroup name="list" tag="div" class="divide-y divide-line">
        <!-- ⚠️ การ์ดเป็น `<div>` ที่มี **RouterLink ครอบเฉพาะเนื้อหา** ไม่ใช่ครอบทั้งแถว —
             ของเดิมเอา `<button>` (อนุมัติเผยแพร่) ไว้ *ใน* `<a>` ซึ่งเป็น HTML ที่ไม่ถูกต้อง
             และทำให้ปุ่มซ้อนปุ่ม ⇒ แยกออกมาเป็นพี่น้องกัน -->
        <div
          v-for="i in issues"
          :key="i.id"
          class="flex items-start gap-3 px-4 py-3.5 transition-colors hover:bg-canvas"
        >
          <RouterLink
            :to="{ name: 'issue-detail', params: { id: i.id } }"
            class="flex min-w-0 flex-1 flex-col gap-1.5"
          >
            <p class="truncate text-[11px] font-medium text-ink-3">
              {{ MAIN_CATEGORY_LABELS[i.main_category] }} ·
              {{ subcategoryLabel(i.main_category, i.category) }}
              <template v-if="i.requested_destination && i.requested_destination !== 'normal'">
                · {{ DESTINATION_LABELS[i.requested_destination] }}
              </template>
            </p>
            <h3 class="line-clamp-2 font-semibold leading-snug text-ink-1">{{ i.title }}</h3>
            <div class="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] font-medium text-ink-3">
              <span>{{ LEVEL_LABELS[i.current_level] }}</span>
              <span><i class="bi bi-building mr-1"></i>{{ i.room_name }}</span>
              <span v-if="i.reporter_name"
                ><i class="bi bi-person mr-1"></i>{{ i.reporter_name }}</span
              >
              <span v-else><i class="bi bi-eye-slash mr-1"></i>ไม่ระบุชื่อ</span>
              <span v-if="i.current_assignee_name"
                ><i class="bi bi-person-badge mr-1"></i>{{ i.current_assignee_name }}</span
              >
              <span>{{ fmtRelative(i.created_at) }}</span>
            </div>
          </RouterLink>

          <div class="flex shrink-0 flex-col items-end gap-2 pt-0.5">
            <StatusBadge :status="i.status" />
            <AppButton
              v-if="canApprove(i)"
              variant="secondary"
              size="sm"
              @click="openApprove(i)"
            >
              อนุมัติเผยแพร่
            </AppButton>
          </div>
        </div>
      </TransitionGroup>
    </AppCard>

    <!-- แบ่งหน้า -->
    <PaginationBar
      :total="total"
      :page="page"
      :page-size="pageSize"
      :loading="isLoading"
      @page-change="onPageChange"
    />

    <!-- 🏛️ Modal อนุมัติเผยแพร่ PIRI Board -->
    <ApproveBoardModal :issue="approveTarget" v-model:open="approveOpen" @approved="onApproved" />
  </div>
</template>

<style scoped>
/* list animation */
.list-enter-active,
.list-leave-active {
  transition: all 0.25s ease;
}
.list-enter-from {
  opacity: 0;
  transform: translateY(10px);
}
.list-leave-to {
  opacity: 0;
  transform: translateY(-6px);
}
</style>
