<!-- eslint-disable vue/multi-word-component-names -- ชื่อตาม route/spec -->
<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import Swal from 'sweetalert2'
import { fmtDateTime } from '@/datetime'
import AppButton from '@/components/ui/AppButton.vue'
import AppCard from '@/components/ui/AppCard.vue'
import AppEmptyState from '@/components/ui/AppEmptyState.vue'
import AppSheet from '@/components/ui/AppSheet.vue'
import {
  bulkMoveStudents,
  getStudentHistory,
  listRooms,
  listStudents,
  unassignStudents,
} from '@/services/student'
import type { Room, Student, StudentHistory } from '@/types/student'
import {
  historyScreenState,
  historyYearLabel,
  isCurrentMember,
  moveConfirmText,
  moveLabel,
  moveResultText,
  unassignConfirmText,
  unassignResultText,
  wholeRoomConfirmText,
} from '@/types/student'
import { sortRoomCodes } from '@/types/rollover'

/**
 * 🔀 ย้ายห้องนักเรียน + ถอดออกจากห้อง + ประวัติรายคน — P5
 *
 * **ทำไมต้องมีหน้าแยก:** การย้ายห้องคือการ `UPDATE students.room_id` ซึ่งเดิม **ลบประวัติ
 * ทิ้งเงียบ ๆ** ⇒ หน้านี้ทำสามอย่างพร้อมกันในทรานแซกชันเดียวของ backend:
 *   1. ย้ายแถวสมาชิกของ **ปีปัจจุบัน** (backend ปฏิเสธแถวปีอื่น — ย้ายข้ามปีไม่ใช่ "ย้ายห้อง")
 *   2. เขียน `student_moves` (ใครย้าย จากไหน ไปไหน ใครสั่ง เพราะอะไร)
 *   3. กันแถว active ซ้อนของคนเดียวกันในปีเดียวกัน (`superseded`)
 *
 * 🧭 **โครงหน้าจอ (UX 2026-10-24):**
 *   - **ย้ายทั้งห้อง** อยู่บนสุด — งานที่โรงเรียนทำบ่อยที่สุดตอนสลับห้องทั้งระดับ
 *   - **รายชื่อ** เป็นแถวกระชับ (เดิมเป็นการ์ดสูง 2 คอลัมน์ ⇒ เลื่อนยาว)
 *   - **แถบปฏิบัติการติดขอบล่าง** ปรากฏทันทีที่ติ๊กอย่างน้อย 1 คน
 *     🔴 เดิมปุ่มย้ายอยู่ *ใต้รายชื่อทั้งหมด* ⇒ ติ๊กแล้วต้องเลื่อนลงไปสุดจอเพื่อกด
 *     ⚠️ `bottom-0` เฉย ๆ ถูกต้อง — `<main>` เว้นระยะให้ bottom nav อยู่แล้ว
 *        (ดูหลักฐานการวัดจริงใน `IssueDetail.vue` — ห้ามบวก `--app-nav-h` ซ้ำ)
 *
 * ⚠️ **ข้อจำกัดที่ผู้ใช้ต้องรู้ก่อนกด:** ย้าย/ถอดได้เฉพาะระดับชั้นของตัวเอง (ครู/ประธานระดับ)
 *    และเฉพาะปีปัจจุบัน — หน้าจอจึงไม่ให้เลือกปี
 */

// ===== ข้อมูลตั้งต้น =====
const students = ref<Student[]>([])
const rooms = ref<Room[]>([])
const isLoading = ref(true)
const hasError = ref(false)
const roomFilter = ref<number | ''>('')
const search = ref('')

// ===== ฟอร์มย้ายรายคน / ถอดออกจากห้อง (แถบติดล่าง) =====
const selected = ref<Set<number>>(new Set())
const toRoomCode = ref('')
const note = ref('')
const noteOpen = ref(false)
const isMoving = ref(false)
const lastResult = ref('')

// ===== ย้ายทั้งห้อง =====
const wholeSource = ref<number | ''>('')
const wholeTarget = ref('')
const wholeRoster = ref<Student[]>([])
const wholeLoading = ref(false)
const wholeError = ref(false)
const isMovingWhole = ref(false)

// ===== ประวัติ =====
const historyOpen = ref(false)
const history = ref<StudentHistory | null>(null)
const historyLoading = ref(false)
const historyError = ref(false)
const historyTitle = ref('')

const selectedCount = computed(() => selected.value.size)
const canSubmit = computed(
  () => selectedCount.value > 0 && toRoomCode.value !== '' && !isMoving.value,
)

const roomChoices = computed(() => sortRoomCodes(rooms.value.map((r) => r.room_code)))
const wholeSourceCode = computed(
  () => rooms.value.find((r) => r.id === wholeSource.value)?.room_code ?? '',
)
const canMoveWholeRoom = computed(
  () =>
    wholeSource.value !== '' &&
    wholeTarget.value !== '' &&
    wholeTarget.value !== wholeSourceCode.value &&
    wholeRoster.value.length > 0 &&
    !isMovingWhole.value,
)
/** จำนวนที่เลือกซึ่ง *มีห้อง* — คนที่ไม่มีห้องแล้วจะถูก backend ข้ามตอนกดถอด */
const selectedWithRoom = computed(
  () => students.value.filter((s) => selected.value.has(s.id) && s.room_id !== null).length,
)

/** รายชื่อที่แสดง = ปีปัจจุบัน (backend default) + ตัวกรองห้อง/คำค้น */
async function load() {
  isLoading.value = true
  hasError.value = false
  try {
    const [list, roomList] = await Promise.all([
      listStudents({
        room_id: roomFilter.value || undefined,
        search: search.value || undefined,
      }),
      listRooms(),
    ])
    // ⚠️ backend คืน **ทุกสถานะ** ของปีนั้น (รวมแถวซ้ำ `superseded`) — หน้าจอที่ให้
    //    "เลือกแล้วย้าย" ต้องเห็นเฉพาะแถวปัจจุบัน ไม่งั้นจะย้ายประวัติแทนตัวเด็ก
    students.value = list.filter(isCurrentMember)
    rooms.value = roomList
    // คนที่หลุดจากตัวกรองต้องไม่ค้างอยู่ในรายการที่เลือก (ไม่งั้นกดย้ายแล้วเจอ id ที่ไม่เห็น)
    const visible = new Set(students.value.map((s) => s.id))
    selected.value = new Set([...selected.value].filter((id) => visible.has(id)))
  } catch (e) {
    hasError.value = true
    Swal.fire({
      icon: 'error',
      title: 'โหลดรายชื่อไม่สำเร็จ',
      text: typeof e === 'string' ? e : 'ตรวจสอบการเชื่อมต่อแล้วลองอีกครั้ง',
    })
  } finally {
    isLoading.value = false
  }
}
onMounted(load)

/** รายชื่อ *ทั้งห้อง* ของห้องต้นทาง — ต้องดึงแยกจาก `students` เพราะลิสต์นั้นมีตัวกรอง */
async function loadWholeRoster() {
  if (wholeSource.value === '') {
    wholeRoster.value = []
    wholeError.value = false
    return
  }
  wholeLoading.value = true
  wholeError.value = false
  try {
    // "ทั้งห้อง" ต้องนับเฉพาะแถวปัจจุบัน — แถว `superseded` ไม่ใช่คนที่ต้องย้าย
    const list = await listStudents({ room_id: Number(wholeSource.value) })
    wholeRoster.value = list.filter(isCurrentMember)
  } catch {
    wholeRoster.value = []
    wholeError.value = true
  } finally {
    wholeLoading.value = false
  }
}

watch(wholeSource, () => {
  wholeTarget.value = ''
  void loadWholeRoster()
})

function toggle(id: number) {
  const next = new Set(selected.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  selected.value = next
}

function selectAllVisible() {
  selected.value = new Set(students.value.map((s) => s.id))
}

function clearSelection() {
  selected.value = new Set()
}

async function submitMove() {
  if (!canSubmit.value) return
  const count = selectedCount.value
  const target = toRoomCode.value

  const confirm = await Swal.fire({
    icon: 'warning',
    title: `ย้าย ${count} คนไปห้อง «${target}»`,
    text: moveConfirmText(count, target, note.value),
    showCancelButton: true,
    confirmButtonText: 'ย้ายเลย',
    cancelButtonText: 'ยกเลิก',
  })
  if (!confirm.isConfirmed) return

  isMoving.value = true
  try {
    const result = await bulkMoveStudents({
      student_ids: [...selected.value],
      to_room_code: target,
      note: note.value.trim() || undefined,
    })
    lastResult.value = moveResultText(result)
    selected.value = new Set()
    note.value = ''
    noteOpen.value = false
    await load()
    await Swal.fire({ icon: 'success', title: 'ย้ายสำเร็จ', text: lastResult.value })
  } catch (e) {
    Swal.fire({
      icon: 'error',
      title: 'ย้ายไม่สำเร็จ',
      text: typeof e === 'string' ? e : 'ไม่มีการเปลี่ยนแปลงใด ๆ ถูกบันทึก',
    })
  } finally {
    isMoving.value = false
  }
}

/** ย้าย **ทุกคน** ในห้องต้นทางพร้อมกัน — ใช้ `bulk-move` เดิม ⇒ ประวัติรายคนครบเหมือนเดิม */
async function submitWholeRoomMove() {
  if (!canMoveWholeRoom.value) return
  const from = wholeSourceCode.value
  const to = wholeTarget.value
  const count = wholeRoster.value.length

  const confirm = await Swal.fire({
    icon: 'warning',
    title: `ย้ายทั้งห้อง «${from}» (${count} คน)`,
    text: wholeRoomConfirmText(count, from, to),
    showCancelButton: true,
    confirmButtonText: 'ย้ายทั้งห้อง',
    cancelButtonText: 'ยกเลิก',
  })
  if (!confirm.isConfirmed) return

  isMovingWhole.value = true
  try {
    const result = await bulkMoveStudents({
      student_ids: wholeRoster.value.map((s) => s.id),
      to_room_code: to,
      note: note.value.trim() || undefined,
    })
    lastResult.value = moveResultText(result)
    selected.value = new Set()
    await Promise.all([load(), loadWholeRoster()])
    await Swal.fire({ icon: 'success', title: 'ย้ายทั้งห้องสำเร็จ', text: lastResult.value })
  } catch (e) {
    Swal.fire({
      icon: 'error',
      title: 'ย้ายทั้งห้องไม่สำเร็จ',
      text: typeof e === 'string' ? e : 'ไม่มีการเปลี่ยนแปลงใด ๆ ถูกบันทึก',
    })
  } finally {
    isMovingWhole.value = false
  }
}

/**
 * ถอดคนที่เลือกออกจากห้อง (`room_id = NULL`) — ใช้เมื่อต้อง "เคลียร์ห้อง" ก่อนอัปไฟล์ใหม่
 * ⚠️ บทบาทระดับโรงเรียน/ครู ไม่ถูกรีเซ็ต (backend จัดการ) — หน้าจอแค่ยืนยันจำนวน
 */
async function unassignSelected() {
  const count = selectedWithRoom.value
  if (!selectedCount.value || isMoving.value) return
  if (!count) {
    await Swal.fire({
      icon: 'info',
      title: 'ไม่มีใครมีห้องให้ถอด',
      text: 'คนที่เลือกอยู่ในสถานะ «ไม่มีห้อง» อยู่แล้ว',
    })
    return
  }

  const confirm = await Swal.fire({
    icon: 'warning',
    title: `ถอด ${count} คนออกจากห้อง`,
    text: unassignConfirmText(count),
    showCancelButton: true,
    confirmButtonText: 'ถอดออกจากห้อง',
    cancelButtonText: 'ยกเลิก',
  })
  if (!confirm.isConfirmed) return

  isMoving.value = true
  try {
    const result = await unassignStudents({
      student_ids: [...selected.value],
      note: note.value.trim() || undefined,
    })
    lastResult.value = unassignResultText(result)
    selected.value = new Set()
    note.value = ''
    noteOpen.value = false
    await load()
    await Swal.fire({ icon: 'success', title: 'ถอดออกจากห้องแล้ว', text: lastResult.value })
  } catch (e) {
    Swal.fire({
      icon: 'error',
      title: 'ถอดออกจากห้องไม่สำเร็จ',
      text: typeof e === 'string' ? e : 'ไม่มีการเปลี่ยนแปลงใด ๆ ถูกบันทึก',
    })
  } finally {
    isMoving.value = false
  }
}

async function openHistory(s: Student) {
  historyTitle.value = `${s.prefix ?? ''} ${s.first_name ?? ''} ${s.last_name ?? ''}`.trim()
  history.value = null
  historyError.value = false
  historyLoading.value = true
  historyOpen.value = true
  try {
    history.value = await getStudentHistory(s.id)
  } catch {
    historyError.value = true
  } finally {
    historyLoading.value = false
  }
}

const historyScreen = computed(() =>
  historyScreenState({
    isLoading: historyLoading.value,
    hasError: historyError.value,
    hasData: history.value !== null,
  }),
)

function studentName(s: Student): string {
  return `${s.prefix ?? ''} ${s.first_name ?? ''} ${s.last_name ?? ''}`.trim() || s.student_id
}
</script>

<template>
  <div>
    <!-- 🏫 ย้ายทั้งห้อง (งานที่ทำบ่อยตอนสลับห้องทั้งระดับ) -->
    <AppCard class="mb-4">
      <h2 class="font-semibold text-ink-1">ย้ายทั้งห้อง</h2>
      <p class="mt-1 text-[13px] text-ink-2">
        ย้ายทุกคนในห้องต้นทางไปห้องปลายทางพร้อมกัน — ระบบบันทึกประวัติรายคนให้ครบเหมือนการย้ายทีละคน
      </p>
      <div class="mt-3 grid grid-cols-1 items-end gap-3 sm:grid-cols-[1fr_auto_1fr]">
        <label class="block">
          <span class="text-[13px] font-medium text-ink-2">ห้องต้นทาง</span>
          <select v-model="wholeSource" class="field mt-1">
            <option value="">— เลือกห้อง —</option>
            <option v-for="r in rooms" :key="r.id" :value="r.id">{{ r.room_code }}</option>
          </select>
        </label>
        <i
          class="bi bi-arrow-right hidden pb-3 text-lg text-ink-3 sm:block"
          aria-hidden="true"
        ></i>
        <label class="block">
          <span class="text-[13px] font-medium text-ink-2">ห้องปลายทาง</span>
          <select v-model="wholeTarget" class="field mt-1" :disabled="!wholeSource">
            <option value="">— เลือกห้อง —</option>
            <option
              v-for="code in roomChoices"
              :key="code"
              :value="code"
              :disabled="code === wholeSourceCode"
            >
              {{ code }}
            </option>
          </select>
        </label>
      </div>
      <div class="mt-3 flex flex-wrap items-center gap-3">
        <AppButton
          :disabled="!canMoveWholeRoom"
          :loading="isMovingWhole"
          @click="submitWholeRoomMove"
        >
          <template #icon><i class="bi bi-arrow-left-right" aria-hidden="true" /></template>
          ย้ายทั้งห้อง
        </AppButton>
        <span class="text-[13px] text-ink-3">
          <template v-if="!wholeSource">เลือกห้องต้นทางก่อน</template>
          <template v-else-if="wholeLoading">กำลังนับจำนวนนักเรียน…</template>
          <template v-else-if="wholeError">โหลดรายชื่อห้องไม่สำเร็จ</template>
          <template v-else>
            ห้อง «{{ wholeSourceCode }}» มี {{ wholeRoster.length }} คน
            <template v-if="!wholeTarget"> · เลือกห้องปลายทางเพื่อย้าย</template>
          </template>
        </span>
      </div>
    </AppCard>

    <!-- ตัวกรองรายชื่อ -->
    <div class="mb-4 grid grid-cols-1 gap-2 sm:flex sm:items-center sm:gap-3">
      <select v-model="roomFilter" class="field sm:w-auto" @change="load">
        <option value="">ทุกห้อง</option>
        <option v-for="r in rooms" :key="r.id" :value="r.id">{{ r.room_code }}</option>
      </select>
      <input
        v-model="search"
        type="text"
        placeholder="ค้นหา รหัสนักเรียน/ชื่อ..."
        class="field sm:flex-1"
        @keyup.enter="load"
      />
      <AppButton variant="secondary" @click="load">
        <template #icon><i class="bi bi-search" aria-hidden="true" /></template>
        ค้นหา
      </AppButton>
    </div>

    <!-- Loading -->
    <div
      v-if="isLoading"
      class="overflow-hidden rounded-card border border-line bg-surface"
      aria-busy="true"
    >
      <div class="divide-y divide-line">
        <div v-for="i in 6" :key="i" class="flex min-h-14 items-center gap-3 px-3 py-2.5">
          <div class="h-5 w-5 shrink-0 animate-pulse rounded bg-stone-100"></div>
          <div class="flex-1 space-y-2">
            <div class="h-4 w-1/3 animate-pulse rounded bg-stone-100"></div>
            <div class="h-3 w-1/2 animate-pulse rounded bg-stone-100"></div>
          </div>
        </div>
      </div>
    </div>

    <!-- Error -->
    <AppCard v-else-if="hasError" :padded="false" class="py-4">
      <AppEmptyState
        icon="bi-people"
        title="ไม่สามารถโหลดรายชื่อได้"
        description="ตรวจสอบการเชื่อมต่อแล้วลองอีกครั้ง"
      >
        <AppButton variant="secondary" @click="load">
          <template #icon><i class="bi bi-arrow-clockwise" aria-hidden="true" /></template>
          ลองใหม่
        </AppButton>
      </AppEmptyState>
    </AppCard>

    <template v-else>
      <!-- แถบเลือกทั้งหมด -->
      <div class="mb-2 flex flex-wrap items-center gap-2 text-sm">
        <span class="text-ink-2">{{ students.length }} คนในรายการ</span>
        <button
          v-if="students.length"
          class="min-h-11 px-2 font-medium text-brand"
          @click="selectAllVisible"
        >
          เลือกทั้งหมด
        </button>
        <button v-if="selectedCount" class="min-h-11 px-2 text-ink-2" @click="clearSelection">
          ล้างที่เลือก
        </button>
      </div>

      <!-- รายชื่อแบบแถวกระชับ — ติ๊กง่ายบนมือถือ (พื้นที่กดสูง ≥ 56dp) -->
      <div class="overflow-hidden rounded-card border border-line bg-surface">
        <ul v-if="students.length" class="divide-y divide-line">
          <li v-for="s in students" :key="s.id">
            <label
              class="flex min-h-14 cursor-pointer items-center gap-3 px-3 py-2.5 transition-colors"
              :class="selected.has(s.id) ? 'bg-brand/5' : 'hover:bg-canvas'"
            >
              <input
                type="checkbox"
                class="h-5 w-5 shrink-0 accent-brand"
                :checked="selected.has(s.id)"
                @change="toggle(s.id)"
              />
              <div class="min-w-0 flex-1">
                <p class="truncate text-sm font-semibold text-ink-1">{{ studentName(s) }}</p>
                <p class="mt-0.5 truncate text-xs text-ink-3">
                  <span class="font-mono">{{ s.student_id }}</span>
                  <span v-if="s.student_no"> · เลขที่ {{ s.student_no }}</span>
                  <span> · {{ s.room_code ?? 'ไม่มีห้อง' }}</span>
                </p>
              </div>
              <span
                v-if="!s.room_id"
                class="shrink-0 rounded-full bg-warn-soft px-2 py-0.5 text-[11px] font-semibold text-warn"
              >
                ไม่มีห้อง
              </span>
              <button
                type="button"
                class="min-h-11 shrink-0 rounded-full px-2.5 text-xs font-medium text-brand hover:bg-brand/10"
                @click.prevent="openHistory(s)"
              >
                ประวัติ
              </button>
            </label>
          </li>
        </ul>

        <AppEmptyState
          v-else
          icon="bi-people"
          title="ไม่พบนักเรียน"
          description="ลองเปลี่ยนห้องหรือคำค้นหา"
          compact
        />
      </div>

      <p v-if="lastResult" class="mt-3 text-[13px] text-ink-2">{{ lastResult }}</p>

      <!--
        ⚑ แถบปฏิบัติการติดขอบล่าง — ปรากฏเมื่อเลือกอย่างน้อย 1 คน
          🔴 ต้องเป็น **ลูกคนสุดท้ายที่เข้าลำดับการไหล** (ก่อน `AppSheet` ที่ Teleport)
          ⚠️ `bottom-0` เฉย ๆ — `<main>` เว้นระยะให้ bottom nav อยู่แล้ว (อย่าบวกซ้ำ)
      -->
      <div v-if="selectedCount" class="bottom-0 sticky z-30 mt-4">
        <div class="rounded-card border border-line bg-surface p-2.5">
          <div class="flex flex-wrap items-center gap-x-3">
            <span class="text-[13px] font-semibold text-ink-1">
              เลือกแล้ว {{ selectedCount }} คน
            </span>
            <button class="min-h-11 px-1 text-[13px] text-ink-2 underline" @click="clearSelection">
              ล้าง
            </button>
            <span class="grow"></span>
            <button
              class="min-h-11 px-1 text-[13px] font-medium text-brand"
              @click="noteOpen = !noteOpen"
            >
              {{ noteOpen ? 'ซ่อนเหตุผล' : '+ เหตุผล' }}
            </button>
          </div>

          <div class="mt-1.5 flex items-center gap-2">
            <select
              v-model="toRoomCode"
              class="field min-w-0 flex-1"
              aria-label="ห้องปลายทาง"
            >
              <option value="">— ห้องปลายทาง —</option>
              <option v-for="code in roomChoices" :key="code" :value="code">{{ code }}</option>
            </select>
            <AppButton :disabled="!canSubmit" :loading="isMoving" @click="submitMove">
              ย้าย
            </AppButton>
            <AppButton variant="danger" :disabled="isMoving" @click="unassignSelected">
              ถอดห้อง
            </AppButton>
          </div>

          <input
            v-if="noteOpen"
            v-model="note"
            type="text"
            maxlength="200"
            placeholder="เหตุผล (ไม่บังคับ) เช่น สลับห้องตามคำสั่งโรงเรียน"
            class="field mt-1.5"
          />
        </div>
      </div>
    </template>

    <!-- 🧾 ประวัติรายคน -->
    <AppSheet v-model="historyOpen" :title="`ประวัติ · ${historyTitle}`">
      <div v-if="historyScreen === 'loading'" class="space-y-2" aria-busy="true">
        <div v-for="i in 3" :key="i" class="h-12 animate-pulse rounded-xl bg-stone-100"></div>
      </div>

      <AppEmptyState
        v-else-if="historyScreen === 'error'"
        icon="bi-exclamation-triangle"
        title="โหลดประวัติไม่สำเร็จ"
        description="ปิดแผ่นนี้แล้วลองอีกครั้ง"
        compact
      />

      <AppEmptyState
        v-else-if="historyScreen === 'empty'"
        icon="bi-clock-history"
        title="ยังไม่มีประวัติ"
        compact
      />

      <div v-else-if="history" class="space-y-5">
        <section>
          <h3 class="text-[13px] font-semibold text-ink-2">รายปี</h3>
          <ul class="mt-2 divide-y divide-line rounded-xl border border-line">
            <li
              v-for="y in history.years"
              :key="y.student_row_id"
              class="flex items-center justify-between gap-3 px-3 py-2.5 text-sm"
            >
              <span class="text-ink-1">{{ historyYearLabel(y) }}</span>
              <span class="text-xs text-ink-3">{{ y.status }}</span>
            </li>
          </ul>
        </section>

        <section>
          <h3 class="text-[13px] font-semibold text-ink-2">การย้ายห้อง</h3>
          <p v-if="!history.moves.length" class="mt-2 text-[13px] text-ink-3">
            ไม่มีการย้ายห้องในระบบ
          </p>
          <ul v-else class="mt-2 divide-y divide-line rounded-xl border border-line">
            <li v-for="m in history.moves" :key="m.id" class="px-3 py-2.5 text-sm">
              <p class="text-ink-1">{{ moveLabel(m) }}</p>
              <p class="mt-0.5 text-xs text-ink-3">
                {{ m.year_be ? `ปี ${m.year_be} · ` : '' }}{{ fmtDateTime(m.moved_at) || '—' }}
                <span v-if="m.moved_by_name"> · โดย {{ m.moved_by_name }}</span>
              </p>
              <p v-if="m.note" class="mt-1 text-[13px] text-ink-2">«{{ m.note }}»</p>
            </li>
          </ul>
        </section>
      </div>
    </AppSheet>
  </div>
</template>
