<!-- eslint-disable vue/multi-word-component-names -- ชื่อตาม route/spec -->
<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import Swal from 'sweetalert2'
import { fmtDateTime } from '@/datetime'
import AppButton from '@/components/ui/AppButton.vue'
import AppCard from '@/components/ui/AppCard.vue'
import AppEmptyState from '@/components/ui/AppEmptyState.vue'
import StatusBadge from '@/components/ui/StatusBadge.vue'
import { listOrphanedAssignments, reassignIssue } from '@/services/issue'
import type { OrphanCandidate, OrphanedIssue } from '@/types/issue'
import { candidateLabel, orphanedScreenState, reassignConfirmText } from '@/types/issue'

/**
 * 🧯 เรื่องค้างที่ผู้รับหมดวาระ — P5 · ข้อตัดสินใจ #4
 *
 * **ปัญหาที่หน้านี้แก้:** ข้อ #4 บอกว่า "เรื่องค้างคงไว้ ไม่ปิดอัตโนมัติ" — แต่หลังขึ้นปีใหม่
 * `current_assignee_id` ชี้คนที่ **ไม่มีแถว active ในปีนี้แล้ว** ⇒ เรื่องนั้นมีผู้รับแต่ไม่มีใครแตะได้
 * และ `accept_issue` ช่วยไม่ได้ (backend ปฏิเสธถ้ามีผู้รับอยู่แล้ว) ⇒ เรื่องติดตายโดยโครงสร้าง
 *
 * **ประตูสองชั้น (ตรงกับ backend เป๊ะ):** ต้องมี `MANAGE_STUDENTS` **และ** `mode === 'school'`
 * (ครูระดับชั้น/ประธานระดับมีสิทธิ์แรกแต่ไม่ใช่ส่วนกลาง → route gate ต้องมี `requiresCouncil` ด้วย
 * เหมือนหน้า "เลื่อนชั้นนักเรียน")
 */

const items = ref<OrphanedIssue[]>([])
const yearId = ref<number | null>(null)
const isLoading = ref(true)
const hasError = ref(false)

interface Draft {
  toUserId: number | ''
  note: string
  busy: boolean
}

/** สถานะฟอร์มของแต่ละเรื่อง — แยกกันเพื่อให้มอบหมายทีละเรื่องได้โดยไม่บล็อกกัน */
const drafts = reactive<Record<number, Draft>>({})

/**
 * ฟอร์มของเรื่องหนึ่ง — สร้างให้ถ้ายังไม่มี
 *
 * ⚠️ ห้ามเข้าถึง `drafts[item.id]` ตรง ๆ ใน template: `noUncheckedIndexedAccess` ทำให้
 *    type เป็น `Draft | undefined` แล้ว template ต้องใส่ `?.` ทุกจุดจน v-model ใช้ไม่ได้
 */
function draftOf(item: OrphanedIssue): Draft {
  if (!drafts[item.id]) {
    drafts[item.id] = { toUserId: item.candidates[0]?.user_id ?? '', note: '', busy: false }
  }
  return drafts[item.id] as Draft
}

const screen = computed(() =>
  orphanedScreenState({
    isLoading: isLoading.value,
    hasError: hasError.value,
    count: items.value.length,
  }),
)

async function load() {
  isLoading.value = true
  hasError.value = false
  try {
    const res = await listOrphanedAssignments()
    items.value = res.items
    yearId.value = res.year_id
    for (const item of res.items) {
      const prev = drafts[item.id]
      drafts[item.id] = {
        toUserId: prev && prev.toUserId !== '' ? prev.toUserId : (item.candidates[0]?.user_id ?? ''),
        note: prev?.note ?? '',
        busy: false,
      }
    }
  } catch (e) {
    hasError.value = true
    Swal.fire({
      icon: 'error',
      title: 'โหลดรายการไม่สำเร็จ',
      text: typeof e === 'string' ? e : 'ตรวจสอบการเชื่อมต่อแล้วลองอีกครั้ง',
    })
  } finally {
    isLoading.value = false
  }
}
onMounted(load)

function candidateFor(item: OrphanedIssue, userId: number | ''): OrphanCandidate | undefined {
  return item.candidates.find((c) => c.user_id === userId)
}

async function submit(item: OrphanedIssue) {
  const draft = drafts[item.id]
  if (!draft || draft.toUserId === '' || draft.busy) return

  const candidate = candidateFor(item, draft.toUserId)
  if (!candidate) return

  const confirm = await Swal.fire({
    icon: 'warning',
    title: 'มอบหมายเรื่องต่อ',
    text: reassignConfirmText(item, candidate),
    showCancelButton: true,
    confirmButtonText: 'มอบหมาย',
    cancelButtonText: 'ยกเลิก',
  })
  if (!confirm.isConfirmed) return

  draft.busy = true
  try {
    await reassignIssue(item.id, candidate.user_id, draft.note.trim() || undefined)
    // เรื่องที่มอบหมายแล้วหลุดจากรายการนี้ (ผู้รับใหม่ยัง active) ⇒ โหลดใหม่ทั้งชุด
    await load()
    await Swal.fire({ icon: 'success', title: 'มอบหมายสำเร็จ', showConfirmButton: false, timer: 1400 })
  } catch (e) {
    Swal.fire({
      icon: 'error',
      title: 'มอบหมายไม่สำเร็จ',
      text: typeof e === 'string' ? e : 'ไม่มีอะไรถูกแก้ไข — ลองโหลดรายการใหม่',
    })
  } finally {
    draft.busy = false
  }
}
</script>

<template>
  <div>
    <p v-if="yearId && screen === 'ready'" class="mb-4 text-[13px] text-ink-2">
      เรื่องที่ยังเปิดอยู่แต่ผู้รับไม่มีสมาชิกภาพในปีการศึกษานี้ ·
      <span class="font-semibold">{{ items.length }}</span> เรื่อง
    </p>

    <!-- Loading -->
    <div v-if="screen === 'loading'" class="space-y-3" aria-busy="true">
      <div v-for="i in 3" :key="i" class="rounded-2xl border border-stone-200 bg-white p-4">
        <div class="h-4 w-1/2 animate-pulse rounded bg-stone-100"></div>
        <div class="mt-2 h-3 w-2/3 animate-pulse rounded bg-stone-100"></div>
        <div class="mt-4 h-11 animate-pulse rounded-xl bg-stone-100"></div>
      </div>
    </div>

    <!-- Error -->
    <AppCard v-else-if="screen === 'error'" :padded="false" class="py-4">
      <AppEmptyState
        icon="bi-exclamation-triangle"
        title="ไม่สามารถโหลดรายการได้"
        description="ตรวจสอบการเชื่อมต่อแล้วลองอีกครั้ง"
      >
        <AppButton variant="secondary" @click="load">
          <template #icon><i class="bi bi-arrow-clockwise" aria-hidden="true" /></template>
          ลองใหม่
        </AppButton>
      </AppEmptyState>
    </AppCard>

    <!-- ว่าง -->
    <AppCard v-else-if="screen === 'empty'" :padded="false" class="py-4">
      <AppEmptyState
        icon="bi-check2-circle"
        title="ไม่มีเรื่องค้าง"
        description="ทุกเรื่องที่ยังเปิดอยู่มีผู้รับที่มีสมาชิกภาพในปีการศึกษานี้แล้ว"
      />
    </AppCard>

    <!-- รายการ -->
    <div v-else class="space-y-3">
      <AppCard v-for="item in items" :key="item.id">
        <div class="flex items-start justify-between gap-3">
          <div class="min-w-0">
            <p class="truncate font-semibold text-ink-1">{{ item.title }}</p>
            <p class="mt-1 text-xs text-ink-3">
              <span v-if="item.room_code">ห้อง {{ item.room_code }} · </span>
              {{ fmtDateTime(item.created_at) || '—' }}
            </p>
          </div>
          <StatusBadge :status="item.status" />
        </div>

        <div class="mt-3 rounded-xl bg-stone-50 px-3 py-2.5 text-[13px]">
          <p class="text-ink-2">
            ผู้รับเดิม:
            <span class="font-medium text-ink-1">{{ item.assignee_name ?? '—' }}</span>
            <span v-if="item.assignee_old_room_code" class="text-ink-3">
              (เคยอยู่ {{ item.assignee_old_room_code }})</span
            >
          </p>
          <p class="mt-0.5 text-ink-3">หมดสมาชิกภาพในปีนี้แล้ว</p>
        </div>

        <div class="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
          <label class="block">
            <span class="text-[13px] font-medium text-ink-2">ผู้รับใหม่</span>
            <select
              v-model="draftOf(item).toUserId"
              class="mt-1 w-full rounded-xl border border-stone-300 bg-white px-3 py-2.5 text-sm"
            >
              <option value="" disabled>— เลือกผู้รับ —</option>
              <option v-for="c in item.candidates" :key="c.user_id" :value="c.user_id">
                {{ candidateLabel(c) }}
              </option>
            </select>
          </label>
          <label class="block">
            <span class="text-[13px] font-medium text-ink-2">หมายเหตุ (ไม่บังคับ)</span>
            <input
              v-model="draftOf(item).note"
              type="text"
              maxlength="200"
              placeholder="เช่น ส่งต่อให้หัวหน้าห้องคนใหม่"
              class="mt-1 w-full rounded-xl border border-stone-300 px-3 py-2.5 text-sm"
            />
          </label>
        </div>

        <div class="mt-3 flex flex-wrap items-center gap-3">
          <AppButton
            :disabled="draftOf(item).toUserId === '' || draftOf(item).busy"
            :loading="draftOf(item).busy"
            @click="submit(item)"
          >
            <template #icon><i class="bi bi-person-check" aria-hidden="true" /></template>
            มอบหมายต่อ
          </AppButton>
          <span v-if="!item.candidates.length" class="text-[13px] text-ink-3">
            ยังไม่มีผู้ดำรงตำแหน่งเดียวกันในปีนี้ — ต้องแต่งตั้งก่อน
          </span>
        </div>
      </AppCard>
    </div>
  </div>
</template>
