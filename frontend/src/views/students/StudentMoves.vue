<!-- eslint-disable vue/multi-word-component-names -- ชื่อตาม route/spec -->
<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
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
} from '@/services/student'
import type { Room, Student, StudentHistory } from '@/types/student'
import {
  historyScreenState,
  historyYearLabel,
  moveConfirmText,
  moveLabel,
  moveResultText,
} from '@/types/student'
import { sortRoomCodes } from '@/types/rollover'

/**
 * 🔀 ย้ายห้องนักเรียน + ประวัติรายคน — P5
 *
 * **ทำไมต้องมีหน้าแยก:** การย้ายห้องคือการ `UPDATE students.room_id` ซึ่งเดิม **ลบประวัติ
 * ทิ้งเงียบ ๆ** ⇒ หน้านี้ทำสามอย่างพร้อมกันในทรานแซกชันเดียวของ backend:
 *   1. ย้ายแถวสมาชิกของ **ปีปัจจุบัน** (backend ปฏิเสธแถวปีอื่น — ย้ายข้ามปีไม่ใช่ "ย้ายห้อง")
 *   2. เขียน `student_moves` (ใครย้าย จากไหน ไปไหน ใครสั่ง เพราะอะไร)
 *   3. กันแถว active ซ้อนของคนเดียวกันในปีเดียวกัน (`superseded`)
 *
 * ⚠️ **ข้อจำกัดที่ผู้ใช้ต้องรู้ก่อนกด:** ย้ายได้เฉพาะระดับชั้นของตัวเอง (ครู/ประธานระดับ)
 *    และย้ายได้เฉพาะปีปัจจุบัน — หน้าจอจึงไม่ให้เลือกปี
 */

// ===== ข้อมูลตั้งต้น =====
const students = ref<Student[]>([])
const rooms = ref<Room[]>([])
const isLoading = ref(true)
const hasError = ref(false)
const roomFilter = ref<number | ''>('')
const search = ref('')

// ===== ฟอร์มย้าย =====
const selected = ref<Set<number>>(new Set())
const toRoomCode = ref('')
const note = ref('')
const isMoving = ref(false)
const lastResult = ref('')

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
    students.value = list
    rooms.value = roomList
    // คนที่หลุดจากตัวกรองต้องไม่ค้างอยู่ในรายการที่เลือก (ไม่งั้นกดย้ายแล้วเจอ id ที่ไม่เห็น)
    const visible = new Set(list.map((s) => s.id))
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
    <!-- ตัวกรอง -->
    <div class="grid grid-cols-1 gap-2 sm:flex sm:items-center sm:gap-3 mb-5">
      <select
        v-model="roomFilter"
        @change="load"
        class="w-full rounded-xl border border-stone-300 bg-white px-3 py-2.5 text-sm sm:w-auto"
      >
        <option value="">ทุกห้อง</option>
        <option v-for="r in rooms" :key="r.id" :value="r.id">{{ r.room_code }}</option>
      </select>
      <input
        v-model="search"
        @keyup.enter="load"
        type="text"
        placeholder="ค้นหา รหัสนักเรียน/ชื่อ..."
        class="w-full rounded-xl border border-stone-300 px-3 py-2.5 text-sm sm:flex-1"
      />
      <button
        @click="load"
        class="inline-flex items-center rounded-xl bg-stone-100 px-4 min-h-11 py-2.5 text-sm font-medium hover:bg-stone-200"
      >
        <i class="bi bi-search"></i> ค้นหา
      </button>
    </div>

    <!-- Loading -->
    <div
      v-if="isLoading"
      class="overflow-hidden rounded-2xl border border-stone-200 bg-white"
      aria-busy="true"
    >
      <div class="divide-y divide-stone-100">
        <div v-for="i in 6" :key="i" class="flex items-center gap-3 p-4">
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
      <div class="mb-3 flex flex-wrap items-center gap-2 text-sm">
        <span class="text-ink-2">เลือกแล้ว {{ selectedCount }} คน</span>
        <button
          v-if="students.length"
          class="min-h-11 px-2 text-brand font-medium"
          @click="selectAllVisible"
        >
          เลือกทั้งหมดในลิสต์
        </button>
        <button v-if="selectedCount" class="min-h-11 px-2 text-ink-2" @click="clearSelection">
          ล้างที่เลือก
        </button>
      </div>

      <!-- รายชื่อ (การ์ดทุกขนาด — checkbox ต้องกดง่ายบนมือถือ) -->
      <div class="grid grid-cols-1 gap-3 md:grid-cols-2">
        <label
          v-for="s in students"
          :key="s.id"
          class="flex cursor-pointer items-center gap-3 rounded-2xl border bg-white p-4"
          :class="selected.has(s.id) ? 'border-brand ring-1 ring-brand/30' : 'border-stone-200'"
        >
          <input
            type="checkbox"
            class="h-5 w-5 shrink-0 accent-brand"
            :checked="selected.has(s.id)"
            @change="toggle(s.id)"
          />
          <div class="min-w-0 flex-1">
            <p class="truncate font-semibold text-stone-900">{{ studentName(s) }}</p>
            <p class="mt-0.5 text-xs text-stone-500">
              <span class="font-mono">{{ s.student_id }}</span>
              <span v-if="s.student_no" class="ml-1.5">เลขที่ {{ s.student_no }}</span>
              <span class="ml-1.5">· {{ s.room_code ?? 'ไม่มีห้อง' }}</span>
            </p>
          </div>
          <button
            type="button"
            class="min-h-11 shrink-0 rounded-full px-2.5 text-xs font-medium text-brand hover:bg-brand/10"
            @click.prevent="openHistory(s)"
          >
            ประวัติ
          </button>
        </label>

        <div v-if="!students.length" class="rounded-2xl border border-line bg-white md:col-span-2">
          <AppEmptyState
            icon="bi-people"
            title="ไม่พบนักเรียน"
            description="ลองเปลี่ยนห้องหรือคำค้นหา"
            compact
          />
        </div>
      </div>

      <!-- กล่องย้าย -->
      <AppCard class="mt-5">
        <h2 class="font-semibold text-ink-1">ย้ายไปห้องปลายทาง</h2>
        <p class="mt-1 text-[13px] text-ink-2">
          ย้ายได้เฉพาะสมาชิกของปีการศึกษาปัจจุบัน — ระบบจะบันทึกประวัติการย้ายให้ทุกคน
        </p>
        <div class="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
          <label class="block">
            <span class="text-[13px] font-medium text-ink-2">ห้องปลายทาง</span>
            <select
              v-model="toRoomCode"
              class="mt-1 w-full rounded-xl border border-stone-300 bg-white px-3 py-2.5 text-sm"
            >
              <option value="">— เลือกห้อง —</option>
              <option v-for="code in roomChoices" :key="code" :value="code">{{ code }}</option>
            </select>
          </label>
          <label class="block">
            <span class="text-[13px] font-medium text-ink-2">เหตุผล (ไม่บังคับ)</span>
            <input
              v-model="note"
              type="text"
              maxlength="200"
              placeholder="เช่น สลับห้องตามคำสั่งโรงเรียน"
              class="mt-1 w-full rounded-xl border border-stone-300 px-3 py-2.5 text-sm"
            />
          </label>
        </div>
        <div class="mt-4 flex flex-wrap items-center gap-3">
          <AppButton :disabled="!canSubmit" :loading="isMoving" @click="submitMove">
            <template #icon><i class="bi bi-arrow-left-right" aria-hidden="true" /></template>
            ย้าย {{ selectedCount }} คน
          </AppButton>
          <span v-if="!selectedCount" class="text-[13px] text-ink-3">
            เลือกนักเรียนก่อนอย่างน้อย 1 คน
          </span>
          <span v-else-if="!toRoomCode" class="text-[13px] text-ink-3">เลือกห้องปลายทาง</span>
        </div>
        <p v-if="lastResult" class="mt-3 text-[13px] text-ink-2">{{ lastResult }}</p>
      </AppCard>
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
