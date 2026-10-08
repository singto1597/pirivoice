<!-- eslint-disable vue/multi-word-component-names -- ชื่อตาม route/spec -->
<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import Swal from 'sweetalert2'
import { BRAND } from '@/constants/brand'
import { fmtDateTime } from '@/datetime'
import AppButton from '@/components/ui/AppButton.vue'
import AppCard from '@/components/ui/AppCard.vue'
import AppEmptyState from '@/components/ui/AppEmptyState.vue'
import { listYears } from '@/services/year'
import { listRooms } from '@/services/student'
import { applyRollover, listRolloverRuns, previewRollover } from '@/services/rollover'
import type { AcademicYear } from '@/types/academicYear'
import type { Room } from '@/types/student'
import type {
  RolloverApplyResult,
  RolloverPreview,
  RolloverRun,
  RolloverUnmappedRoom,
} from '@/types/rollover'
import {
  applyBlockReason,
  applyConfirmText,
  applyResultText,
  cleanOverrides,
  levelGroupTitle,
  overridesDirty,
  rolloverScreenState,
  roomOptions,
} from '@/types/rollover'

/**
 * 🔄 เลื่อนชั้นทั้งโรงเรียน — P4
 *
 * **นี่คือหน้าเดียวในระบบที่ "กดผิดแล้วกู้ไม่ได้"** — `apply` เขียนสมาชิกหลายพันแถว สลับปีปัจจุบัน
 * และ `ALTER TABLE students ... SET DEFAULT` ในทรานแซกชันเดียว ⇒ ถ้าผิดต้อง restore dump
 * ⇒ ทุกอย่างในหน้านี้จึงถูกจัดให้ "ผู้ใช้ต้องเห็นก่อนกด" ไม่ใช่ "กดแล้วค่อยรู้":
 *   · ต้องกด «ดูแผน» ก่อนเสมอ — ปุ่มยืนยันได้ `run_id` มาจาก preview เท่านั้น
 *   · ห้องที่ระบบหาปลายทางไม่ได้ → ให้เลือกเอง ไม่เดา (และ preview ซ้ำได้จนกว่าจะผ่าน)
 *   · `can_apply` / `blockers` มาจาก backend เท่านั้น — **UI ห้ามคิดเองว่าอะไรคือ blocker**
 *     (ชุดเดียวกับที่ `apply_rollover` จะ `raise` ⇒ ปุ่มกดได้แต่กดแล้วล้ม = คำเตือนไม่น่าเชื่อถืออีก)
 *
 * ⚠️ **ทำไม route อยู่ที่ `/students/promote`** — หน้านี้จัดการ *สมาชิก* (ไม่ใช่ตัวปี)
 *    และ path ในโปรเจกต์นี้สะท้อนโฟลเดอร์ของ view มาตลอด (`students/import` → `views/students/`)
 *    ⇒ อยู่ใต้ `students` เพื่อให้ปุ่ม ← กลับไปหน้ารายชื่อได้ตรงกับที่ผู้ใช้เพิ่งมาจาก
 */

// ===== ข้อมูลตั้งต้น =====
const years = ref<AcademicYear[]>([])
const rooms = ref<Room[]>([])
const isLoading = ref(true)
const hasError = ref(false)

const fromYearId = ref('')
const toYearId = ref('')

// ===== ผลลัพธ์ =====
const plan = ref<RolloverPreview | null>(null)
const result = ref<RolloverApplyResult | null>(null)
const overrides = ref<Record<string, string>>({})
/** ค่า `overrides` **ณ วินาทีที่ preview สำเร็จ** — ใช้เทียบว่าผู้ใช้แก้หลังจากนั้นไหม */
const previewedOverrides = ref<Record<string, string>>({})

const isPreviewing = ref(false)
const isApplying = ref(false)

const screen = computed(() =>
  rolloverScreenState({
    isLoading: isLoading.value,
    hasError: hasError.value,
    // ⚠️ `result` ก็นับเป็น "มีของให้ดูแล้ว" — ไม่งั้นหลัง apply สำเร็จ หน้าจะกลับไปที่
    //    skeleton/idle ทั้งที่เพิ่งมีผลลัพธ์ที่ผู้ใช้ต้องอ่าน (และต้องคัดลอกตัวเลขไปรายงาน)
    hasPlan: plan.value !== null || result.value !== null,
  }),
)

/** ปีที่เลือกได้เป็นปลายทาง — ตัดปีต้นทางออก (backend ก็ปฏิเสธคู่ปีเดียวกันอยู่แล้ว) */
const targetYears = computed(() => years.value.filter((y) => String(y.id) !== fromYearId.value))

/** ตัวเลือกห้องปลายทาง — ทุกห้องที่ระบบรู้จัก (backend ตรวจซ้ำว่า "มีอยู่จริง" อีกชั้น) */
const targetRoomOptions = computed(() => roomOptions(rooms.value))

/** ห้องที่ต้องเลือกปลายทางเอง — ตัดแถวที่ไม่มีรหัสห้องทิ้ง (ใช้เป็น key ไม่ได้) */
const unmappedRows = computed(() =>
  (plan.value?.unmapped ?? []).filter(
    (u): u is RolloverUnmappedRoom & { from_room_code: string } => !!u.from_room_code,
  ),
)

/** แก้ช่องห้องปลายทางหลังจากดูแผนแล้วหรือยัง — ต้องเตือนก่อนกดยืนยัน (ดู overridesDirty) */
const dirty = computed(
  () => plan.value !== null && overridesDirty(previewedOverrides.value, overrides.value),
)

/** เหตุผลที่กด «ยืนยัน» ไม่ได้ — `''` = กดได้ · **ที่เดียวที่ตัดสิน** (ปุ่มอ่านค่านี้เท่านั้น) */
const blockReason = computed(() => {
  if (dirty.value) return 'แก้ห้องปลายทางแล้ว — กด «ดูแผน» อีกครั้งให้ระบบตรวจก่อน'
  return applyBlockReason(plan.value)
})

const canPreview = computed(
  () => !!fromYearId.value && !!toYearId.value && fromYearId.value !== toYearId.value,
)

// ===== โหลดข้อมูลตั้งต้น =====
async function load() {
  isLoading.value = true
  hasError.value = false
  try {
    const [yearRes, roomRes] = await Promise.all([listYears({ status: 'active', limit: 100 }), listRooms()])
    years.value = yearRes.items
    rooms.value = roomRes
    // ปีต้นทาง = ปีปัจจุบัน (backend บังคับอยู่แล้ว — ตั้งให้ตรงตั้งแต่แรกดีกว่าให้ไปเจอ blocker)
    const current = yearRes.items.find((y) => y.is_current)
    fromYearId.value = current ? String(current.id) : ''
    // ปีปลายทาง = ปีที่ใหม่ที่สุดที่ไม่ใช่ปีต้นทาง (ปกติคือปีที่เพิ่งสร้างไว้รอ)
    const next = [...yearRes.items]
      .filter((y) => y.id !== current?.id)
      .sort((a, b) => b.year_be - a.year_be)[0]
    toYearId.value = next ? String(next.id) : ''
  } catch (e) {
    hasError.value = true
    years.value = []
    Swal.fire({ icon: 'error', title: 'โหลดข้อมูลไม่สำเร็จ', text: errorText(e) })
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

/**
 * เปลี่ยนปี → ทิ้งแผนและค่าที่เลือกไว้
 *
 * 🔴 **ห้ามเก็บ `overrides` ข้ามคู่ปี** — ห้องที่เลือกไว้ผูกกับ "ห้องที่แมปไม่ได้ของคู่นั้น"
 *    พอเปลี่ยนปี ชุดนั้นไม่มีความหมาย และถ้าค้างอยู่จะถูกส่งไปกับ apply เงียบ ๆ
 */
function onYearChange() {
  plan.value = null
  result.value = null
  overrides.value = {}
  previewedOverrides.value = {}
}

// ===== ขั้นที่ 1: ดูแผน =====
async function doPreview() {
  if (!canPreview.value) return
  isPreviewing.value = true
  try {
    const p = await previewRollover({
      from_year_id: Number(fromYearId.value),
      to_year_id: Number(toYearId.value),
      room_overrides: cleanOverrides(overrides.value),
    })
    plan.value = p
    // 🔑 snapshot ค่าที่ *แผนนี้ตรวจมาจาก* — ไม่ใช่ค่าที่ผู้ใช้กำลังจะส่ง (นั่นคือประเด็นของ dirty)
    previewedOverrides.value = cleanOverrides(overrides.value)
    result.value = null
  } catch (e) {
    // 400/403/404/409 จาก backend มีข้อความไทยที่บอกทางออกอยู่แล้ว ⇒ ส่งต่อทั้งดุ้น
    Swal.fire({ icon: 'error', title: 'ดูแผนไม่สำเร็จ', text: errorText(e) })
  } finally {
    isPreviewing.value = false
  }
}

// ===== ขั้นที่ 2: ทำจริง =====
async function doApply() {
  const p = plan.value
  if (!p || blockReason.value) return

  const confirm = await Swal.fire({
    title: 'ยืนยันเลื่อนชั้นทั้งโรงเรียน?',
    text: applyConfirmText(p),
    icon: 'warning',
    showCancelButton: true,
    confirmButtonText: 'ยืนยัน เลื่อนชั้น',
    confirmButtonColor: BRAND,
    cancelButtonText: 'ยกเลิก',
  })
  if (!confirm.isConfirmed) return

  isApplying.value = true
  try {
    const applied = await applyRollover({
      run_id: p.run_id,
      room_overrides: cleanOverrides(overrides.value),
    })
    result.value = applied
    plan.value = null
    overrides.value = {}
    previewedOverrides.value = {}
    Swal.fire({ icon: 'success', title: 'เลื่อนชั้นเรียบร้อย', text: applyResultText(applied) })
    // ปีปัจจุบันย้ายแล้ว + รอบใหม่โผล่ในประวัติ ⇒ ทั้งสองอย่างต้องโหลดใหม่
    await Promise.all([load(), loadRuns()])
  } catch (e) {
    // ⚠️ 409 = รอบนี้ถูกใช้ไปแล้ว หรือมีคน import แทรกหลัง preview — ข้อความบอกจำนวนคน
    //    ⇒ **ไม่ต้อง preview ใหม่ให้อัตโนมัติ** เพราะผู้ใช้ต้องอ่านก่อนว่ามีอะไรแทรกมา
    Swal.fire({ icon: 'error', title: 'เลื่อนชั้นไม่สำเร็จ', text: errorText(e) })
  } finally {
    isApplying.value = false
  }
}

// ===== ประวัติการเลื่อนชั้น (โหลดเมื่อกางออก — ไม่ยิง API ให้ทุกคนที่เปิดหน้านี้) =====
const runs = ref<RolloverRun[]>([])
const runsLoaded = ref(false)
const runsLoading = ref(false)
const showRuns = ref(false)

async function loadRuns() {
  runsLoading.value = true
  try {
    const res = await listRolloverRuns({ limit: 20 })
    runs.value = res.items
    runsLoaded.value = true
  } catch (e) {
    Swal.fire({ icon: 'error', title: 'โหลดประวัติไม่สำเร็จ', text: errorText(e) })
  } finally {
    runsLoading.value = false
  }
}

async function toggleRuns() {
  showRuns.value = !showRuns.value
  if (showRuns.value && !runsLoaded.value) await loadRuns()
}

/** ป้ายสถานะรอบ — `PREVIEWED` ยังไม่ทำอะไรจริง ⇒ ต้องหน้าตา "ยังไม่เกิด" ไม่ใช่ "สำเร็จ" */
function runLabel(r: RolloverRun): string {
  if (r.status === 'APPLIED') return 'ทำแล้ว'
  if (r.status === 'FAILED') return 'ล้มเหลว'
  return 'ดูแผนไว้'
}

function runTone(r: RolloverRun): string {
  if (r.status === 'APPLIED') return 'bg-ok-tint text-ok-strong'
  if (r.status === 'FAILED') return 'bg-danger-soft text-danger'
  return 'bg-canvas text-ink-2'
}
</script>

<template>
  <div>
    <!-- 🔴 ไม่มี <h1> ที่นี่ — `AppHeader` แสดงชื่อหน้าจาก `routeTitles` เป็น <h1> ให้แล้ว -->

    <!-- โหลดครั้งแรก -->
    <div v-if="screen === 'loading'" class="space-y-3">
      <div
        v-for="i in 2"
        :key="i"
        class="animate-pulse rounded-card border border-line bg-surface p-4"
      >
        <div class="mb-3 h-4 w-32 rounded bg-line"></div>
        <div class="h-10 w-full rounded bg-canvas"></div>
      </div>
    </div>

    <!-- โหลดล้มรอบแรก -->
    <div
      v-else-if="screen === 'error'"
      class="rounded-card border border-line bg-surface px-5 py-8 text-center"
    >
      <i class="bi bi-exclamation-triangle-fill mb-2 block text-2xl text-danger" aria-hidden="true" />
      <p class="text-sm font-semibold text-ink-1">โหลดข้อมูลไม่สำเร็จ</p>
      <div class="mt-3 flex justify-center">
        <AppButton variant="secondary" @click="load">ลองใหม่</AppButton>
      </div>
    </div>

    <template v-else>
      <!-- ===== การ์ดผลลัพธ์ (หลังทำสำเร็จ) ===== -->
      <AppCard v-if="result" class="mb-4">
        <div class="flex flex-wrap items-start gap-3">
          <span
            class="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-ok-tint text-ok-strong"
            aria-hidden="true"
          >
            <i class="bi bi-check2-circle text-xl" />
          </span>
          <div class="min-w-0 flex-1">
            <h2 class="text-[15px] font-bold text-ink-1">เลื่อนชั้นเรียบร้อยแล้ว</h2>
            <p class="mt-1 text-[13px] leading-relaxed text-ink-2">
              {{ applyResultText(result) }}
            </p>
          </div>
        </div>
      </AppCard>

      <!-- ===== เลือกปี ===== -->
      <AppCard class="mb-4">
        <h2 class="mb-1 text-[15px] font-bold text-ink-1">เลือกปีที่จะเลื่อน</h2>
        <p class="mb-4 text-[13px] leading-relaxed text-ink-2">
          ระบบจะยกสมาชิกจากปีต้นทางขึ้นชั้นตามระดับห้อง แล้วตั้งปีปลายทางเป็นปีปัจจุบัน
          — ยังไม่มีการแก้อะไรจนกว่าจะกดยืนยันในขั้นสุดท้าย
        </p>

        <!-- ยังมีปีไม่ครบสองปี ⇒ ต้องสร้างปีใหม่ก่อน (ทางออกชัดเจน ไม่ปล่อยให้เดา) -->
        <div
          v-if="years.length < 2"
          class="rounded-card border border-line bg-canvas px-4 py-5 text-center"
        >
          <p class="text-sm font-semibold text-ink-1">ยังมีปีการศึกษาไม่ถึง 2 ปี</p>
          <p class="mt-1 text-[13px] text-ink-2">
            การเลื่อนชั้นต้องมีปีปลายทางให้ย้ายไป — สร้างปีของเทอมถัดไปก่อน
          </p>
          <div class="mt-3 flex justify-center">
            <AppButton variant="primary" :to="{ name: 'academic-years' }">
              <template #icon><i class="bi bi-mortarboard" aria-hidden="true" /></template>
              ไปหน้าปีการศึกษา
            </AppButton>
          </div>
        </div>

        <div v-else class="grid gap-3 sm:grid-cols-2">
          <label class="block">
            <span class="mb-1.5 block text-[13px] font-semibold text-ink-1">
              ปีต้นทาง <span class="font-normal text-ink-3">(ต้องเป็นปีปัจจุบัน)</span>
            </span>
            <select
              v-model="fromYearId"
              class="w-full rounded-xl border border-line bg-surface px-3 py-2.5 text-sm text-ink-1"
              @change="onYearChange"
            >
              <option value="">— เลือกปี —</option>
              <option v-for="y in years" :key="y.id" :value="String(y.id)">
                {{ y.name }}{{ y.is_current ? ' · ปีปัจจุบัน' : '' }}
                (สมาชิก {{ y.member_count }} คน)
              </option>
            </select>
          </label>

          <label class="block">
            <span class="mb-1.5 block text-[13px] font-semibold text-ink-1">
              ปีปลายทาง <span class="font-normal text-ink-3">(ต้องยังว่าง)</span>
            </span>
            <select
              v-model="toYearId"
              class="w-full rounded-xl border border-line bg-surface px-3 py-2.5 text-sm text-ink-1"
              @change="onYearChange"
            >
              <option value="">— เลือกปี —</option>
              <option v-for="y in targetYears" :key="y.id" :value="String(y.id)">
                {{ y.name }} (สมาชิก {{ y.member_count }} คน)
              </option>
            </select>
          </label>
        </div>

        <div v-if="years.length >= 2" class="mt-4 flex flex-wrap items-center gap-3">
          <AppButton
            variant="primary"
            :loading="isPreviewing"
            :disabled="!canPreview"
            @click="doPreview"
          >
            <template #icon><i class="bi bi-search" aria-hidden="true" /></template>
            {{ plan ? 'ดูแผนอีกครั้ง' : 'ดูแผน' }}
          </AppButton>
          <span v-if="!canPreview" class="text-[12px] text-ink-3">เลือกให้ครบทั้งสองปีก่อน</span>
        </div>
      </AppCard>

      <!-- ===== ยังไม่ได้ดูแผน ===== -->
      <AppCard v-if="screen === 'idle'" muted>
        <AppEmptyState
          icon="bi-arrow-up-circle"
          title="ยังไม่ได้ดูแผน"
          description="เลือกปีแล้วกด «ดูแผน» — ระบบจะยังไม่แก้อะไรจนกว่าจะกดยืนยันในขั้นสุดท้าย"
          compact
        />
      </AppCard>

      <!-- ===== แผน ===== -->
      <template v-if="plan">
        <!-- 🔴 ห้ามกด — แสดงก่อนทุกอย่าง และอ่าน `blockers` ของ backend ตรง ๆ -->
        <div
          v-if="plan.blockers.length"
          class="mb-4 rounded-card border border-danger/30 bg-danger-soft px-4 py-3"
        >
          <p class="mb-1 flex items-center gap-2 text-[13px] font-bold text-danger">
            <i class="bi bi-exclamation-octagon-fill" aria-hidden="true" />
            ต้องแก้ก่อน ({{ plan.blockers.length }} ข้อ)
          </p>
          <ul class="ml-5 list-disc space-y-1 text-[13px] leading-relaxed text-ink-1">
            <li v-for="(b, i) in plan.blockers" :key="i">{{ b }}</li>
          </ul>
        </div>

        <!-- ⚠️ ทำได้ แต่ควรตรวจ — แยกสีจาก blocker ให้ชัด (แดง = ห้ามกด · เหลือง = อ่านก่อนกด) -->
        <div
          v-if="plan.warnings.length"
          class="mb-4 rounded-card border border-warn/30 bg-warn-soft px-4 py-3"
        >
          <p class="mb-1 flex items-center gap-2 text-[13px] font-bold text-warn">
            <i class="bi bi-info-circle-fill" aria-hidden="true" />
            ควรตรวจก่อน ({{ plan.warnings.length }} ข้อ)
          </p>
          <ul class="ml-5 list-disc space-y-1 text-[13px] leading-relaxed text-ink-1">
            <li v-for="(w, i) in plan.warnings" :key="i">{{ w }}</li>
          </ul>
        </div>

        <!-- สรุปตัวเลข -->
        <AppCard class="mb-4">
          <h2 class="mb-3 text-[15px] font-bold text-ink-1">
            {{ plan.from_year.name }} → {{ plan.to_year.name }}
          </h2>
          <div class="grid grid-cols-3 gap-3 text-center">
            <div class="rounded-card bg-canvas px-2 py-3">
              <p class="text-xl font-bold tabular-nums text-ink-1">{{ plan.total_active }}</p>
              <p class="mt-0.5 text-[12px] text-ink-2">สมาชิกปีนี้</p>
            </div>
            <div class="rounded-card bg-brand-tint px-2 py-3">
              <p class="text-xl font-bold tabular-nums text-brand">{{ plan.promoted.count }}</p>
              <p class="mt-0.5 text-[12px] text-brand">เลื่อนขึ้นปีใหม่</p>
            </div>
            <div class="rounded-card bg-canvas px-2 py-3">
              <p class="text-xl font-bold tabular-nums text-ink-1">{{ plan.graduating.count }}</p>
              <p class="mt-0.5 text-[12px] text-ink-2">จบการศึกษา</p>
            </div>
          </div>

          <ul class="mt-3 space-y-1 text-[13px] text-ink-2">
            <li v-if="plan.staff_carried.count">
              <i class="bi bi-person-badge mr-1" aria-hidden="true" />ยกบุคลากรไปปีใหม่
              <span class="tabular-nums">{{ plan.staff_carried.count }}</span> คน
              (ตำแหน่งและสิทธิ์เดิม)
            </li>
            <li v-if="plan.positions_reset.count">
              <i class="bi bi-arrow-counterclockwise mr-1" aria-hidden="true" />ตำแหน่งในห้อง
              (หัวหน้าห้อง/รองฝ่าย) เป็นนักเรียนธรรมดา
              <span class="tabular-nums">{{ plan.positions_reset.count }}</span> คน
              — ต้องแต่งตั้งใหม่หลังรู้รายชื่อ
            </li>
            <li v-if="plan.council_lapsing.count">
              <i class="bi bi-hourglass-split mr-1" aria-hidden="true" />สมาชิกสภานักเรียน
              <span class="tabular-nums">{{ plan.council_lapsing.count }}</span> คน
              — วาระหมด กลายเป็นนักเรียนธรรมดา (ไม่ใช่ตำแหน่งที่ยกตามอัตโนมัติ)
            </li>
            <li v-if="plan.roomless.count">
              <i class="bi bi-question-circle mr-1" aria-hidden="true" />ไม่มีห้อง
              <span class="tabular-nums">{{ plan.roomless.count }}</span> คน
              — ยกไปปีใหม่ทั้งที่ยังไม่มีห้อง
            </li>
          </ul>
        </AppCard>

        <!-- ต้องเลือกห้องปลายทางเอง -->
        <div
          v-if="unmappedRows.length"
          class="mb-4 rounded-card border border-danger/30 bg-danger-soft p-4"
        >
          <h2 class="text-[15px] font-bold text-danger">
            ต้องเลือกห้องปลายทางเอง ({{ unmappedRows.length }} ห้อง)
          </h2>
          <p class="mt-1 text-[13px] leading-relaxed text-ink-1">
            ระบบไม่เดาแทน — เพราะการเดาผิดคือเด็กทั้งห้องไปอยู่ผิดที่โดยไม่มีใครรู้
            เลือกแล้วกด «ดูแผน» อีกครั้งเพื่อให้ระบบตรวจว่ากดได้แล้วจริง
          </p>

          <div
            v-for="u in unmappedRows"
            :key="u.from_room_code"
            class="mt-3 rounded-card border border-line bg-surface px-3 py-3"
          >
            <div class="flex flex-wrap items-baseline gap-2">
              <span class="font-semibold text-ink-1">{{ u.from_room_code }}</span>
              <span class="text-[13px] tabular-nums text-ink-2">{{ u.student_count }} คน</span>
            </div>
            <p class="mt-0.5 text-[12px] text-ink-3">{{ u.reason }}</p>
            <select
              v-model="overrides[u.from_room_code]"
              class="mt-2 w-full rounded-xl border border-line bg-surface px-3 py-2.5 text-sm text-ink-1"
            >
              <option value="">— เลือกห้องปลายทาง —</option>
              <option v-for="o in targetRoomOptions" :key="o.value" :value="o.value">
                {{ o.label }}
              </option>
            </select>
          </div>
        </div>

        <!-- ตารางต่อระดับ -->
        <div class="mb-4 space-y-3">
          <div
            v-for="g in plan.by_level"
            :key="g.level ?? 'unknown'"
            class="rounded-card border border-line bg-surface p-4"
          >
            <div class="mb-2 flex flex-wrap items-baseline justify-between gap-2">
              <h3 class="text-[15px] font-bold text-ink-1">{{ levelGroupTitle(g) }}</h3>
              <span class="text-[13px] text-ink-2">
                <span class="tabular-nums">{{ g.student_count }}</span> คน
              </span>
            </div>
            <ul class="space-y-1.5">
              <li
                v-for="r in g.rooms"
                :key="r.from_room_code ?? ''"
                class="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[13px]"
              >
                <span class="font-semibold text-ink-1">{{ r.from_room_code }}</span>
                <i class="bi bi-arrow-right text-ink-3" aria-hidden="true" />
                <span v-if="r.status === 'ok'" class="text-ink-1">{{ r.to_room_code }}</span>
                <span v-else class="font-semibold text-danger">ยังไม่ได้เลือก</span>
                <span class="ml-auto tabular-nums text-ink-2">{{ r.student_count }} คน</span>
              </li>
            </ul>
          </div>
        </div>

        <!-- ผู้จบการศึกษา -->
        <AppCard v-if="plan.graduating.count" class="mb-4" muted>
          <h3 class="text-[15px] font-bold text-ink-1">
            จบการศึกษา {{ plan.graduating.count }} คน
          </h3>
          <p class="mt-1 text-[13px] leading-relaxed text-ink-2">
            แถวเดิมจะกลายเป็น «จบการศึกษา» และ <strong>ไม่สร้างแถวใหม่</strong> —
            ล็อกอินไม่ได้ แต่ประวัติและเรื่องที่เคยแจ้งยังอยู่ ค้นชื่อเจอได้
          </p>
          <ul class="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[13px] text-ink-2">
            <li v-for="r in plan.graduating.rooms" :key="r.room_code ?? ''">
              {{ r.room_code }} <span class="tabular-nums">{{ r.student_count }}</span>
            </li>
          </ul>
        </AppCard>

        <!-- เตือนว่าแก้ค่าหลังดูแผน -->
        <div
          v-if="dirty"
          class="mb-4 flex flex-wrap items-center gap-3 rounded-card border border-warn/30 bg-warn-soft px-4 py-3"
        >
          <i class="bi bi-arrow-repeat text-warn" aria-hidden="true" />
          <p class="min-w-0 flex-1 text-[13px] font-semibold text-ink-1">
            แก้ห้องปลายทางแล้ว — แผนที่เห็นอยู่ยังไม่รู้จักค่าล่าสุด
          </p>
          <AppButton variant="secondary" size="sm" :loading="isPreviewing" @click="doPreview">
            ดูแผนใหม่
          </AppButton>
        </div>

        <!-- ปุ่มอันตราย -->
        <AppCard>
          <div class="flex flex-wrap items-center gap-3">
            <AppButton
              variant="danger"
              size="lg"
              :loading="isApplying"
              :disabled="!!blockReason"
              :title="blockReason || undefined"
              @click="doApply"
            >
              <template #icon><i class="bi bi-arrow-up-circle" aria-hidden="true" /></template>
              ยืนยันเลื่อนชั้นทั้งโรงเรียน
            </AppButton>
            <p class="min-w-0 flex-1 text-[12px] leading-relaxed text-ink-2">
              {{ blockReason || 'ย้อนกลับเองไม่ได้ — ระบบจะเขียนสมาชิกทั้งโรงเรียนในครั้งเดียว' }}
            </p>
          </div>
        </AppCard>
      </template>

      <!-- ===== ประวัติการเลื่อนชั้น ===== -->
      <div class="mt-6">
        <button
          type="button"
          class="flex w-full items-center gap-2 rounded-card border border-line bg-surface px-4 py-3 text-left"
          :aria-expanded="showRuns"
          @click="toggleRuns"
        >
          <i class="bi bi-clock-history text-ink-2" aria-hidden="true" />
          <span class="min-w-0 flex-1 text-[13px] font-semibold text-ink-1">
            ประวัติการเลื่อนชั้น
          </span>
          <i
            class="bi text-ink-3"
            :class="showRuns ? 'bi-chevron-up' : 'bi-chevron-down'"
            aria-hidden="true"
          />
        </button>

        <div v-if="showRuns" class="mt-3">
          <div v-if="runsLoading" class="space-y-2">
            <div
              v-for="i in 2"
              :key="i"
              class="h-16 animate-pulse rounded-card border border-line bg-surface"
            ></div>
          </div>

          <AppCard v-else-if="runs.length === 0" muted>
            <AppEmptyState
              icon="bi-clock-history"
              title="ยังไม่มีประวัติ"
              description="ทุกรอบที่กด «ดูแผน» จะถูกบันทึกไว้ที่นี่ พร้อมตัวเลขและแผนของตอนนั้น"
              compact
            />
          </AppCard>

          <div v-else class="space-y-2">
            <div
              v-for="r in runs"
              :key="r.id"
              class="rounded-card border border-line bg-surface px-4 py-3"
            >
              <div class="flex flex-wrap items-center gap-2">
                <span
                  class="rounded-full px-2.5 py-0.5 text-[11px] font-bold"
                  :class="runTone(r)"
                >
                  {{ runLabel(r) }}
                </span>
                <span class="text-[13px] font-semibold text-ink-1">
                  {{ r.from_year.name }} → {{ r.to_year.name }}
                </span>
                <span class="ml-auto text-[12px] text-ink-3">
                  {{ fmtDateTime(r.applied_at ?? r.created_at) }}
                </span>
              </div>
              <p class="mt-1 text-[13px] text-ink-2">
                <template v-if="r.status === 'APPLIED'">
                  เลื่อน <span class="tabular-nums">{{ r.promoted_count }}</span> คน ·
                  จบ <span class="tabular-nums">{{ r.graduated_count }}</span> คน ·
                  บุคลากร <span class="tabular-nums">{{ r.staff_carried_count }}</span> คน
                </template>
                <template v-else>ยังไม่ได้ทำจริง — เป็นแผนที่ดูไว้เฉย ๆ</template>
              </p>
              <p v-if="r.error_message" class="mt-1 text-[12px] text-danger">
                {{ r.error_message }}
              </p>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>
