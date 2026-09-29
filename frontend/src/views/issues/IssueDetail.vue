<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import Swal from 'sweetalert2'
import {
  getIssue,
  acceptIssue,
  addStep,
  completeStep,
  escalateIssue,
  resolveIssue,
  updateCountdown,
  cancelIssue,
  changeDestination,
  createComment,
  updateComment,
  deleteComment,
} from '@/services/issue'
import {
  MAIN_CATEGORY_LABELS,
  subcategoryLabel,
  STATUS_LABELS,
  LEVEL_LABELS,
  DESTINATION_LABELS,
  type Issue,
  type RequestedDestination,
} from '@/types/issue'
import type { ApiError } from '@/services/api'
import { goUnavailable } from '@/router/unavailable'
import { useAuthStore } from '@/stores/auth'
import { useNotificationsStore } from '@/stores/notifications'
import { STATUS_BADGE } from '@/constants/status'
import ApproveBoardModal from '@/components/boards/ApproveBoardModal.vue'
import BookmarkButton from '@/components/BookmarkButton.vue'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const notificationsStore = useNotificationsStore()

const issue = ref<Issue | null>(null)
const isLoading = ref(true)
const loadError = ref('') // โหลดข้อมูลไม่สำเร็จ → inline error + retry

const daysInput = ref(3)
const newStepTitle = ref('')
const newStepDetail = ref('')

// 🏛️ สภานักเรียน/แอดมิน อนุมัติเผยแพร่ PIRI Board (เรื่องขอ vote/talk ยังไม่ถูกอนุมัติ/ปิด)
const approveOpen = ref(false)
const canApprove = computed(() => {
  if (!issue.value || !authStore.isCouncilAuthority) return false
  if (issue.value.requested_destination === 'normal') return false
  if (issue.value.published_board_id) return false
  return !['resolved', 'cancelled', 'rejected'].includes(issue.value.status)
})
const publishedBoardId = computed(() => issue.value?.published_board_id ?? null)

function onApproved(boardId: number) {
  router.push({ name: 'board-detail', params: { id: boardId } })
}

// 🔁 เปลี่ยนปลายทาง (แก้แจ้งผิด): สภา/แอดมิน เปลี่ยนได้ทุกเรื่อง; หัวหน้าห้อง/รอง เปลี่ยนได้
// เฉพาะเรื่องที่ยังอยู่ระดับห้องของตัวเอง — กันเรื่องที่เผยแพร่เป็น board แล้ว/ปิดแล้ว
const ROOM_HANDLER_ROLES = [
  'class_president',
  'vice_academic',
  'vice_discipline',
  'vice_activity',
  'vice_reception',
]
const canChangeDestination = computed(() => {
  if (!issue.value || !authStore.user) return false
  if (issue.value.published_board_id) return false
  if (['resolved', 'cancelled', 'rejected'].includes(issue.value.status)) return false
  if (authStore.isCouncilAuthority) return true
  if (issue.value.current_level !== 'room') return false
  return authStore.roles.some(
    (r) =>
      ROOM_HANDLER_ROLES.includes(r.role || '') &&
      r.room_id != null &&
      r.room_id === issue.value?.room_id,
  )
})

async function handleChangeDestination() {
  if (!issue.value) return
  const { value: dest } = await Swal.fire({
    title: 'แก้ไขปลายทางของเรื่อง',
    html: 'เรื่องจะถูกส่งไป<span class="font-semibold">' +
      (issue.value.current_level === 'council' ? 'สภานักเรียน' : 'หัวหน้าห้อง') +
      '</span>เพื่อรับเรื่องอีกครั้ง',
    icon: 'question',
    input: 'select',
    inputOptions: {
      normal: DESTINATION_LABELS.normal,
      vote: DESTINATION_LABELS.vote,
      talk: DESTINATION_LABELS.talk,
    },
    inputValue: issue.value.requested_destination || 'normal',
    showCancelButton: true,
    confirmButtonText: 'ถัดไป',
    cancelButtonText: 'ยกเลิก',
  })
  if (!dest || dest === issue.value.requested_destination) return

  const willGoPublic = dest === 'vote' || dest === 'talk'
  const { isConfirmed } = await Swal.fire({
    icon: 'warning',
    title: 'ยืนยันเปลี่ยนปลายทาง?',
    html:
      'เป็น <b>' +
      DESTINATION_LABELS[dest as RequestedDestination] +
      '</b><br>' +
      (willGoPublic
        ? 'เรื่องจะถูกส่งไปยัง<b>สภานักเรียน</b>เพื่อพิจารณาอนุมัติเป็น PIRI Board'
        : 'เรื่องจะ<b>ถอนคำขอเผยแพร่</b>และกลับไปยังหัวหน้าห้องดำเนินการตามปกติ'),
    showCancelButton: true,
    confirmButtonText: 'เปลี่ยน',
    cancelButtonText: 'ยกเลิก',
  })
  if (!isConfirmed) return

  try {
    await changeDestination(issue.value.id, dest as RequestedDestination)
    Swal.fire({ icon: 'success', title: 'เปลี่ยนปลายทางแล้ว', timer: 1200, showConfirmButton: false })
    load()
  } catch (e) {
    Swal.fire({ icon: 'error', title: 'เปลี่ยนปลายทางไม่สำเร็จ', text: errMsg(e) })
  }
}

async function load() {
  isLoading.value = true
  loadError.value = ''
  try {
    issue.value = await getIssue(Number(route.params.id))
    // 🔔 เปิดเรื่องแล้ว → mark notification ของเรื่องนี้ว่าอ่านแล้ว (badge ลด)
    if (issue.value) void notificationsStore.read({ entity_type: 'issue', entity_id: issue.value.id })
  } catch (e) {
    // 🚪 404 = เรื่องนี้เปิดดูไม่ได้แล้ว (ถูกลบ หรือถูกสภากดซ่อน) — backend ตอบ 404 เหมือนกัน
    //    ⚠️ เช็ค **ก่อน** เงื่อนไข `!issue.value` เพราะ 404 เป็นสถานะสุดท้าย —
    //    refreshing หน้าเดิมที่เพิ่งถูกลบจะไม่มีทางสำเร็จ ⇒ ต้องพาออก ไม่ใช่เก็บหน้าเดิมไว้
    if (e instanceof Error && (e as ApiError).status === 404) {
      await goUnavailable(router, 'issue')
      return
    }
    // มีข้อมูลเดิมอยู่แล้ว (กำลัง refresh) → เก็บหน้าเดิมไว้ ไม่ฟ้อง error
    if (!issue.value) loadError.value = errMsg(e) || 'เกิดข้อผิดพลาด'
  } finally {
    isLoading.value = false
  }
}
onMounted(load)

const canReceive = computed(() => {
  if (!issue.value || !authStore.user) return false
  if (issue.value.current_assignee_id) return false
  if (issue.value.status !== 'pending' && issue.value.status !== 'escalated') return false
  // แอดมินรับเรื่องได้ทุกเรื่อง
  if (authStore.isAdmin) return true
  // ระดับของผู้ใช้ (สูงสุด) ต้องสูงกว่าหรือเท่ากับระดับเรื่อง → รับแทนหัวหน้าห้องในระดับนั้นได้เลย
  const rank = { student: 0, room: 1, level: 2, council: 3 }
  const myRank = rank[getMyLevel() as keyof typeof rank] ?? 0
  const issueRank = rank[issue.value.current_level] ?? 1
  if (myRank < issueRank) return false
  // เรื่องระดับ 'room' และตัวเองระดับ 'room' → ต้องเป็นสมาชิกห้องของเรื่อง (รับแทนได้เฉพาะระดับที่สูงกว่า)
  if (issue.value.current_level === 'room' && myRank === 1) {
    return authStore.roles.some((r) => r.room_id != null && r.room_id === issue.value?.room_id)
  }
  return true
})

const canManage = computed(() => {
  if (!issue.value || !authStore.user) return false
  return issue.value.current_assignee_id === authStore.user.id || authStore.isAdmin
})

const canEscalate = computed(() => {
  if (!canManage.value) return false
  if (issue.value?.current_level === 'council') return false
  return issue.value?.status === 'in_progress'
})

const isReporter = computed(
  () => !!issue.value && !!authStore.user && issue.value.reporter_id === authStore.user.id,
)

const canCancel = computed(() => {
  if (!issue.value || !authStore.user) return false
  // เฉพาะผู้แจ้งเท่านั้นที่กดยกเลิก (กันส่งผิด) — ผู้ดูแลใช้ปัดตกแทน
  if (!isReporter.value) return false
  // เรื่องที่ปิดแล้ว ยกเลิกไม่ได้
  if (issue.value.status === 'resolved') return false
  return true
})

// ผู้ดูแล (ผู้รับ/admin) ปัดตกเรื่อง — ต่างจากผู้แจ้งยกเลิก (backend แยกเป็น status 'rejected')
const canReject = computed(() => {
  if (!issue.value || !authStore.user) return false
  if (isReporter.value) return false
  if (!canManage.value) return false
  // เรื่องที่ปิดแล้ว ปัดตกไม่ได้
  if (issue.value.status === 'resolved') return false
  return true
})

// ผู้แจ้ง (หรือ admin) แก้ไขเรื่องได้ จนกว่าจะปิด — ตรงกับกฎ backend
const canEditIssue = computed(() => {
  if (!issue.value || !authStore.user) return false
  if (!isReporter.value && !authStore.isAdmin) return false
  return !['resolved', 'cancelled', 'rejected'].includes(issue.value.status)
})

const newComment = ref('')

function errMsg(e: unknown): string {
  return e instanceof Error ? e.message : String(e)
}

async function handleAddComment() {
  if (!issue.value || !newComment.value.trim()) return
  try {
    await createComment(issue.value.id, newComment.value.trim())
    newComment.value = ''
    load()
  } catch (e) {
    Swal.fire({ icon: 'error', title: 'ส่งคอมเมนต์ไม่สำเร็จ', text: errMsg(e) })
  }
}

async function handleEditComment(commentId: number, currentBody: string) {
  if (!issue.value) return
  const { value } = await Swal.fire({
    icon: 'question',
    title: 'แก้ไขคอมเมนต์',
    input: 'textarea',
    inputValue: currentBody,
    inputAttributes: { maxlength: '1000' },
    showCancelButton: true,
    confirmButtonText: 'บันทึก',
    cancelButtonText: 'ยกเลิก',
  })
  if (!value || !String(value).trim()) return
  try {
    await updateComment(issue.value.id, commentId, String(value).trim())
    load()
  } catch (e) {
    Swal.fire({ icon: 'error', title: 'ไม่สำเร็จ', text: errMsg(e) })
  }
}

async function handleDeleteComment(commentId: number) {
  if (!issue.value) return
  const { isConfirmed } = await Swal.fire({
    icon: 'warning',
    title: 'ลบคอมเมนต์นี้?',
    text: 'คอมเมนต์ของคุณจะถูกลบ',
    showCancelButton: true,
    confirmButtonText: 'ลบ',
    confirmButtonColor: '#B91C1C',
    cancelButtonText: 'ยกเลิก',
  })
  if (!isConfirmed) return
  try {
    await deleteComment(issue.value.id, commentId)
    load()
  } catch (e) {
    Swal.fire({ icon: 'error', title: 'ลบไม่สำเร็จ', text: errMsg(e) })
  }
}

function getMyLevel(): string {
  // ระดับสูงสุดจาก roles
  const roleLevels: Record<string, string> = {
    class_president: 'room',
    vice_academic: 'room',
    vice_discipline: 'room',
    vice_activity: 'room',
    vice_reception: 'room',
    level_president: 'level',
    council_member: 'council',
    council_president: 'council',
  }
  let best = 'student'
  for (const r of authStore.roles) {
    const lv = roleLevels[r.role || ''] || 'student'
    const rank = { student: 0, room: 1, level: 2, council: 3 }
    if (rank[lv as keyof typeof rank] > rank[best as keyof typeof rank]) best = lv
  }
  return best
}

async function handleAccept() {
  if (!issue.value) return
  const { value } = await Swal.fire({
    icon: 'question',
    title: 'รับเรื่องนี้?',
    html: 'ตั้งเวลา (วัน) ที่คิดว่าจะใช้แก้ปัญหา',
    input: 'number',
    inputValue: daysInput.value,
    inputAttributes: { min: '1', max: '365' },
    showCancelButton: true,
    confirmButtonText: 'รับเรื่อง',
    cancelButtonText: 'ยกเลิก',
  })
  if (!value) return

  try {
    await acceptIssue(issue.value.id, Number(value))
    Swal.fire({
      icon: 'success',
      title: 'รับเรื่องแล้ว!',
      text: `ตั้งเวลา ${value} วัน`,
      timer: 1500,
      showConfirmButton: false,
    })
    load()
  } catch (e) {
    Swal.fire({ icon: 'error', title: 'ไม่สำเร็จ', text: errMsg(e) })
  }
}

async function handleAddStep() {
  if (!issue.value || !newStepTitle.value.trim()) return
  try {
    await addStep(
      issue.value.id,
      newStepTitle.value.trim(),
      newStepDetail.value.trim() || undefined,
    )
    newStepTitle.value = ''
    newStepDetail.value = ''
    Swal.fire({ icon: 'success', title: 'เพิ่มขั้นตอนแล้ว', timer: 1000, showConfirmButton: false })
    load()
  } catch (e) {
    Swal.fire({ icon: 'error', title: 'ไม่สำเร็จ', text: errMsg(e) })
  }
}

async function handleCompleteStep(stepId: number) {
  if (!issue.value) return
  try {
    await completeStep(issue.value.id, stepId)
    load()
  } catch (e) {
    Swal.fire({ icon: 'error', title: 'ไม่สำเร็จ', text: errMsg(e) })
  }
}

async function handleEscalate() {
  if (!issue.value) return
  const { value } = await Swal.fire({
    icon: 'warning',
    title: 'ส่งต่อเรื่องนี้ไประดับบน?',
    text: 'ถ้าเกินความสามารถหรือไม่ทันเวลา',
    input: 'text',
    inputPlaceholder: 'เหตุผล (ไม่บังคับ)',
    showCancelButton: true,
    confirmButtonText: 'ส่งต่อ',
    cancelButtonText: 'ยกเลิก',
  })
  if (value === undefined) return

  try {
    await escalateIssue(issue.value.id, value || undefined)
    Swal.fire({
      icon: 'success',
      title: 'ส่งต่อแล้ว!',
      text: `ส่งต่อไปยังระดับบน`,
      timer: 1500,
      showConfirmButton: false,
    })
    load()
  } catch (e) {
    Swal.fire({ icon: 'error', title: 'ไม่สำเร็จ', text: errMsg(e) })
  }
}

async function handleResolve() {
  if (!issue.value) return
  const { value } = await Swal.fire({
    icon: 'success',
    title: 'ปิดเรื่องนี้?',
    text: 'ยืนยันว่าแก้ไขเสร็จสิ้น',
    input: 'text',
    inputPlaceholder: 'สรุปผลการแก้ไข (ไม่บังคับ)',
    showCancelButton: true,
    confirmButtonText: 'ปิดเรื่อง',
    cancelButtonText: 'ยกเลิก',
  })
  if (value === undefined) return

  try {
    await resolveIssue(issue.value.id, value || undefined)
    Swal.fire({ icon: 'success', title: 'ปิดเรื่องแล้ว!', timer: 1500, showConfirmButton: false })
    load()
  } catch (e) {
    Swal.fire({ icon: 'error', title: 'ไม่สำเร็จ', text: errMsg(e) })
  }
}

async function handleCancel() {
  if (!issue.value) return
  const reporterCancel = isReporter.value
  const { value } = await Swal.fire({
    icon: 'warning',
    title: reporterCancel ? 'ยกเลิกเรื่องนี้?' : 'ปัดตกเรื่องนี้?',
    text: reporterCancel
      ? 'กันส่งผิดหรือไม่ต้องการแล้ว — เมื่อยกเลิกแล้วจะกู้คืนไม่ได้'
      : 'ผู้ดูแลกำลังปัดตกเรื่องนี้ — หลังปัดตกแล้วจะกู้คืนไม่ได้',
    input: 'text',
    inputPlaceholder: 'เหตุผล (ไม่บังคับ)',
    showCancelButton: true,
    confirmButtonText: reporterCancel ? 'ยกเลิกเรื่อง' : 'ปัดตก',
    confirmButtonColor: '#B91C1C',
    cancelButtonText: 'กลับไป',
  })
  if (value === undefined) return

  try {
    await cancelIssue(issue.value.id, value || undefined)
    Swal.fire({
      icon: 'success',
      title: reporterCancel ? 'ยกเลิกเรื่องแล้ว' : 'ปัดตกเรื่องแล้ว',
      timer: 1500,
      showConfirmButton: false,
    })
    load()
  } catch (e) {
    Swal.fire({ icon: 'error', title: 'ไม่สำเร็จ', text: errMsg(e) })
  }
}

async function handleExtendCountdown() {
  if (!issue.value) return
  const { value } = await Swal.fire({
    icon: 'question',
    title: 'ยืดเวลาการแก้ปัญหา',
    input: 'number',
    inputValue: issue.value.countdown?.estimated_days || 3,
    inputAttributes: { min: '1', max: '365' },
    showCancelButton: true,
    confirmButtonText: 'ยืดเวลา',
    cancelButtonText: 'ยกเลิก',
  })
  if (!value) return
  try {
    await updateCountdown(issue.value.id, Number(value))
    Swal.fire({ icon: 'success', title: 'ยืดเวลาแล้ว', timer: 1500, showConfirmButton: false })
    load()
  } catch (e) {
    Swal.fire({ icon: 'error', title: 'ไม่สำเร็จ', text: errMsg(e) })
  }
}

function fmtDate(iso: string | null): string {
  if (!iso) return '-'
  const d = new Date(iso)
  return d.toLocaleString('th-TH', {
    timeZone: 'Asia/Bangkok',
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

/**
 * ป้าย "เหลืออีกกี่วัน" — **ต้องคำนวณจาก `deadline` ไม่ใช่ `estimated_days`**
 *
 * ⚠️ บั๊กเดิม: ส่ง `estimated_days` (ค่าตั้งต้นที่ตั้งครั้งเดียวแล้วไม่เปลี่ยน) เข้ามา
 *    ⇒ การ์ดโชว์ "ตั้งไว้ 7 วัน" คู่กับ "เหลือ 7 วัน" พร้อมกันตลอดไป แล้วกระโดดเป็น
 *    "เกินเวลา!" เฉย ๆ โดยไม่มีคำเตือนตอนใกล้ครบกำหนด — ผู้รับเรื่องจึงไม่รู้ตัว
 *    (หลักฐานยืนยันว่าเป็นบั๊ก: backend validate `estimated_days` เป็น `ge=1`
 *     ⇒ กิ่ง `days <= 0` เดิมเป็น dead code ที่ไม่มีทางถูกเรียก)
 *
 * ปัดขึ้น (`ceil`) ให้ตรงกับที่คนอ่านเข้าใจ: เหลือ 6.9 วัน = "เหลือ 7 วัน"
 * ส่วนสถานะ "เกินเวลา" ยังใช้ `is_overdue` จากเซิร์ฟเวอร์เป็นหลัก — ไม่พึ่งนาฬิกาเครื่องผู้ใช้
 */
function countdownLabel(deadline: string): string {
  const days = Math.ceil((new Date(deadline).getTime() - Date.now()) / 86_400_000)
  if (days <= 0) return 'หมดเวลา'
  if (days === 1) return 'เหลือ 1 วัน'
  return `เหลือ ${days} วัน`
}
</script>

<template>
  <!-- โหลดข้อมูล: skeleton เนื้อหา -->
  <div v-if="isLoading" class="max-w-3xl mx-auto space-y-5 animate-pulse">
    <div class="rounded-2xl border border-stone-200 bg-white p-5 space-y-4">
      <div class="h-3 w-40 rounded bg-stone-100"></div>
      <div class="flex gap-2">
        <div class="h-6 w-20 rounded-full bg-stone-100"></div>
        <div class="h-6 w-24 rounded-full bg-stone-100"></div>
      </div>
      <div class="h-8 w-3/4 rounded-lg bg-stone-100"></div>
      <div class="h-3 w-48 rounded bg-stone-100"></div>
      <div class="h-4 w-full rounded bg-stone-100"></div>
      <div class="h-4 w-2/3 rounded bg-stone-100"></div>
    </div>
    <div class="rounded-2xl border border-stone-200 bg-white p-5 space-y-3">
      <div class="h-5 w-44 rounded bg-stone-100"></div>
      <div v-for="n in 3" :key="n" class="h-12 rounded-lg bg-stone-100"></div>
    </div>
  </div>

  <!-- โหลดไม่สำเร็จ: inline error + retry -->
  <div
    v-else-if="loadError"
    class="max-w-3xl mx-auto flex flex-col items-center justify-center rounded-2xl border-2 border-dashed border-stone-200 py-20 text-center"
  >
    <i class="bi bi-exclamation-triangle text-3xl text-stone-400 mb-3"></i>
    <p class="text-stone-600 px-6">{{ loadError }}</p>
    <button
      type="button"
      class="mt-4 rounded-lg bg-[#B91C1C] px-5 py-2 text-[13px] font-bold text-white hover:bg-[#991B1B]"
      @click="load"
    >
      ลองอีกครั้ง
    </button>
  </div>

  <div v-else-if="issue" class="max-w-3xl mx-auto space-y-5">
    <!-- Header -->
    <div class="rounded-2xl border border-stone-200 bg-white p-5">
      <p class="mb-3 flex items-center gap-2 text-[11px] font-bold uppercase tracking-widest text-[#B91C1C]">
        <i class="bi bi-folder2-open text-[12px]"></i> Issue Dossier
      </p>
      <div class="flex items-start justify-between gap-3">
        <div class="min-w-0">
          <div class="flex flex-wrap gap-2 mb-2">
            <span class="px-2.5 py-0.5 bg-stone-100 text-stone-600 text-xs rounded-full">
              {{ MAIN_CATEGORY_LABELS[issue.main_category] }}
            </span>
            <span class="px-2.5 py-0.5 bg-stone-100 text-stone-600 text-xs rounded-full">
              {{ subcategoryLabel(issue.main_category, issue.category) }}
            </span>
            <span class="px-2.5 py-0.5 bg-stone-100 text-stone-600 text-xs rounded-full">
              {{ LEVEL_LABELS[issue.current_level] }}
            </span>
            <span
              v-if="issue.requested_destination && issue.requested_destination !== 'normal'"
              class="px-2.5 py-0.5 bg-stone-100 text-stone-600 text-xs rounded-full"
            >
              {{ DESTINATION_LABELS[issue.requested_destination] }}
            </span>
          </div>
          <h1 class="text-2xl sm:text-3xl font-bold tracking-tight text-stone-900 leading-snug break-words">
            {{ issue.title }}
          </h1>
          <p class="text-stone-500 text-sm mt-1 break-words">
            โดย {{ issue.reporter_name || 'ไม่ระบุชื่อ' }}
            {{ issue.reporter_room ? `(${issue.reporter_room})` : '' }}
          </p>
        </div>
        <div class="flex shrink-0 items-center gap-2">
          <span
            class="px-3 py-1 text-sm font-medium rounded-full whitespace-nowrap"
            :class="STATUS_BADGE[issue.status] || 'bg-stone-100 text-stone-500'"
          >
            {{ STATUS_LABELS[issue.status] }}
          </span>
          <!-- 🔖 บันทึกไว้อ่านทีหลัง (C2) — อยู่ในการ์ดหัวเรื่อง ไม่ใช่แถบปุ่มด้านล่าง -->
          <BookmarkButton entity-type="issue" :entity-id="issue.id" />
        </div>
      </div>
      <p class="text-stone-700 mt-4 whitespace-pre-wrap">{{ issue.description }}</p>
      <p class="text-xs text-stone-400 mt-3">
        แจ้งเมื่อ {{ fmtDate(issue.created_at) }} · ห้อง {{ issue.room_name }}
      </p>
    </div>

    <!-- Actions (mobile = ปุ่มเต็มแถว, กดง่าย) -->
    <div
      v-if="canReceive || canManage || canEditIssue"
      class="grid grid-cols-1 sm:flex sm:flex-wrap gap-2"
    >
      <button
        v-if="canEditIssue"
        @click="router.push({ name: 'issue-edit', params: { id: issue.id } })"
        class="px-4 py-2.5 bg-white border border-stone-200 text-stone-700 rounded-xl hover:bg-stone-50 text-sm font-medium"
      >
        <i class="bi bi-pencil-square mr-1"></i> แก้ไขเรื่อง
      </button>
      <button
        v-if="canReceive"
        @click="handleAccept"
        class="px-4 py-2.5 bg-[#B91C1C] text-white rounded-xl hover:bg-[#991B1B] text-sm font-medium"
      >
        <i class="bi bi-hand-thumbs-up mr-1"></i> รับเรื่อง + ตั้งเวลา
      </button>
      <!-- 🏛️ สภานักเรียน/แอดมิน อนุมัติเผยแพร่เป็น PIRI Board -->
      <button
        v-if="canApprove"
        @click="approveOpen = true"
        data-testid="approve-public-btn"
        class="px-4 py-2.5 bg-[#B91C1C] text-white rounded-xl hover:bg-[#991B1B] text-sm font-medium"
      >
        <i class="bi bi-people-fill mr-1"></i> อนุมัติเผยแพร่สาธารณะ
      </button>
      <!-- 🔁 หัวหน้าห้อง/สภา แก้ไขปลายทาง (แจ้งผิด) — normal/vote/talk -->
      <button
        v-if="canChangeDestination"
        @click="handleChangeDestination"
        data-testid="change-dest-btn"
        class="px-4 py-2.5 bg-[#B91C1C] text-white rounded-xl hover:bg-[#991B1B] text-sm font-medium"
      >
        <i class="bi bi-arrow-repeat mr-1"></i> แก้ไขปลายทาง
      </button>
      <!-- เรื่องที่เผยแพร่เป็น board แล้ว → ลิงก์ไปชม -->
      <button
        v-if="publishedBoardId"
        @click="router.push({ name: 'board-detail', params: { id: publishedBoardId } })"
        data-testid="board-link"
        class="px-4 py-2.5 bg-emerald-600 text-white rounded-xl hover:bg-emerald-700 text-sm font-medium"
      >
        <i class="bi bi-box-arrow-up-right mr-1"></i> ดู PIRI Board สาธารณะ
      </button>
      <button
        v-if="canManage && canEscalate"
        @click="handleEscalate"
        class="px-4 py-2.5 bg-[#B91C1C] text-white rounded-xl hover:bg-[#991B1B] text-sm font-medium"
      >
        <i class="bi bi-arrow-up-circle mr-1"></i> ส่งต่อไประดับบน
      </button>
      <button
        v-if="canManage && issue.status === 'in_progress'"
        @click="handleResolve"
        class="px-4 py-2.5 bg-emerald-600 text-white rounded-xl hover:bg-emerald-700 text-sm font-medium"
      >
        <i class="bi bi-check2-circle mr-1"></i> ปิดเรื่อง (เสร็จแล้ว)
      </button>
      <button
        v-if="canManage && issue.countdown && issue.status === 'in_progress'"
        @click="handleExtendCountdown"
        class="px-4 py-2.5 bg-white border border-stone-200 text-stone-700 rounded-xl hover:bg-stone-50 text-sm font-medium"
      >
        <i class="bi bi-clock-history mr-1"></i> ยืดเวลา
      </button>
      <!-- ยกเลิก (ผู้แจ้ง — กันส่งผิด) / ปัดตก (ผู้ดูแล) -->
      <button
        v-if="canCancel || canReject"
        @click="handleCancel"
        class="px-4 py-2.5 bg-white border border-stone-200 text-stone-700 rounded-xl hover:bg-stone-50 text-sm font-medium"
      >
        <i class="bi bi-x-circle mr-1"></i> {{ isReporter ? 'ยกเลิกเรื่อง' : 'ปัดตก' }}
      </button>
    </div>

    <!-- Countdown -->
    <div
      v-if="issue.countdown"
      class="bg-white rounded-2xl border border-stone-200 border-l-4 border-l-[#B91C1C] p-5"
    >
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-2">
          <i class="bi bi-hourglass-split text-xl text-[#B91C1C]"></i>
          <div>
            <p class="text-sm font-medium text-stone-700">การนับถอยหลัง</p>
            <p class="text-xs text-stone-500">
              ตั้งไว้ {{ issue.countdown.estimated_days }} วัน · ถึง
              {{ fmtDate(issue.countdown.deadline) }}
            </p>
          </div>
        </div>
        <div class="text-lg font-bold font-display text-[#B91C1C]">
          {{
            issue.countdown.is_overdue
              ? 'เกินเวลา!'
              : countdownLabel(issue.countdown.deadline)
          }}
        </div>
      </div>
    </div>

    <!-- Steps -->
    <div class="rounded-2xl border border-stone-200 bg-white p-5">
      <h2 class="text-lg font-bold text-stone-900 mb-3">
        <i class="bi bi-diagram-3 mr-1"></i> ขั้นตอนการดำเนินงาน
      </h2>
      <div v-if="issue.steps && issue.steps.length" class="divide-y divide-stone-100">
        <div
          v-for="s in issue.steps"
          :key="s.id"
          class="flex items-center gap-3 py-3"
          :class="s.is_completed ? 'opacity-70' : ''"
        >
          <button
            v-if="canManage && !s.is_completed"
            @click="handleCompleteStep(s.id)"
            class="w-6 h-6 rounded-full border-2 border-stone-300 hover:border-[#B91C1C] hover:bg-stone-50 flex items-center justify-center text-xs transition"
            title="ทำขั้นตอนนี้สำเร็จ"
          >
            <i class="bi bi-check text-[#B91C1C]"></i>
          </button>
          <div
            v-else
            class="w-6 h-6 rounded-full flex items-center justify-center"
            :class="s.is_completed ? 'bg-emerald-500 text-white' : 'bg-stone-200'"
          >
            <i v-if="s.is_completed" class="bi bi-check text-xs"></i>
          </div>
          <div class="flex-1 min-w-0">
            <p
              class="text-sm font-medium"
              :class="s.is_completed ? 'text-stone-500 line-through' : 'text-stone-800'"
            >
              {{ s.step_title }}
            </p>
            <p v-if="s.step_detail" class="text-xs text-stone-500">{{ s.step_detail }}</p>
          </div>
        </div>
      </div>
      <p v-else class="text-sm text-stone-400">ยังไม่มีขั้นตอนการดำเนินงาน</p>

      <div v-if="canManage" class="mt-4 pt-4 border-t border-stone-100 grid grid-cols-1 sm:flex gap-2">
        <input
          v-model="newStepTitle"
          type="text"
          placeholder="เพิ่มขั้นตอน..."
          class="w-full sm:flex-1 px-3 py-2.5 border border-stone-300 rounded-lg text-sm bg-white"
          @keyup.enter="handleAddStep"
        />
        <input
          v-model="newStepDetail"
          type="text"
          placeholder="รายละเอียด (ไม่บังคับ)"
          class="w-full sm:w-48 px-3 py-2.5 border border-stone-300 rounded-lg text-sm bg-white"
          @keyup.enter="handleAddStep"
        />
        <button
          @click="handleAddStep"
          class="px-4 py-2.5 bg-white border border-stone-200 text-stone-600 rounded-lg text-sm hover:bg-stone-50"
        >
          <i class="bi bi-plus-lg"></i>
        </button>
      </div>
    </div>

    <!-- Comments (แบบ YouTube — ชื่อ + เวลา + ข้อความ) -->
    <div class="rounded-2xl border border-stone-200 bg-white p-5">
      <h2 class="text-lg font-bold text-stone-900 mb-3">
        <i class="bi bi-chat-left-text mr-1"></i> คอมเมนต์
        <span v-if="issue.comments?.length" class="text-sm font-normal text-stone-400"
          >({{ issue.comments.length }})</span
        >
      </h2>

      <div v-if="issue.comments && issue.comments.length" class="divide-y divide-stone-100">
        <div
          v-for="c in issue.comments"
          :key="c.id"
          class="py-4 first:pt-0 last:pb-0"
        >
          <div class="flex items-center justify-between gap-2">
            <div class="flex items-center gap-2 min-w-0">
              <div
                class="w-8 h-8 rounded-full bg-stone-100 text-stone-700 flex items-center justify-center font-bold text-sm shrink-0"
              >
                {{ (c.commenter_first_name || c.commenter_name || '?').charAt(0) }}
              </div>
              <div class="min-w-0">
                <p class="text-sm font-medium text-stone-800 truncate">
                  {{ c.commenter_name || 'ไม่ระบุชื่อ' }}
                  <span v-if="c.commenter_room" class="text-xs text-stone-400 font-normal"
                    >({{ c.commenter_room }})</span
                  >
                </p>
                <p class="text-xs text-stone-400">
                  {{ fmtDate(c.created_at) }}
                  <span v-if="c.updated_at">· แก้ไข {{ fmtDate(c.updated_at) }}</span>
                </p>
              </div>
            </div>
            <!-- แก้/ลบได้เฉพาะคอมเมนต์ของตัวเอง -->
            <div v-if="c.user_id === authStore.user?.id" class="flex gap-1 shrink-0">
              <button
                @click="handleEditComment(c.id, c.body)"
                title="แก้ไขคอมเมนต์"
                class="w-8 h-8 rounded-lg hover:bg-stone-100 text-stone-500 text-sm"
              >
                <i class="bi bi-pencil"></i>
              </button>
              <button
                @click="handleDeleteComment(c.id)"
                title="ลบคอมเมนต์"
                class="w-8 h-8 rounded-lg hover:bg-red-50 text-[#B91C1C] text-sm"
              >
                <i class="bi bi-trash"></i>
              </button>
            </div>
          </div>
          <p class="text-sm text-stone-700 mt-2 whitespace-pre-wrap break-words">{{ c.body }}</p>
        </div>
      </div>
      <p v-else class="text-sm text-stone-400">ยังไม่มีคอมเมนต์ — เป็นคนแรกที่รับทราบเรื่องนี้</p>

      <!-- ช่องพิมพ์คอมเมนต์ -->
      <div class="mt-4 flex gap-2">
        <input
          v-model="newComment"
          type="text"
          placeholder="พิมพ์คอมเมนต์..."
          class="flex-1 px-3 py-2.5 border border-stone-300 rounded-lg text-sm bg-white"
          maxlength="1000"
          @keyup.enter="handleAddComment"
        />
        <button
          @click="handleAddComment"
          class="px-4 py-2.5 bg-[#B91C1C] text-white rounded-lg text-sm hover:bg-[#991B1B] disabled:opacity-50 disabled:pointer-events-none"
          :disabled="!newComment.trim()"
        >
          <i class="bi bi-send mr-1"></i> ส่ง
        </button>
      </div>
    </div>

    <!-- Timeline -->
    <div class="rounded-2xl border border-stone-200 bg-white p-5">
      <h2 class="text-lg font-bold text-stone-900 mb-3">
        <i class="bi bi-clock-history mr-1"></i> ประวัติการดำเนินงาน
      </h2>
      <div
        v-if="issue.status_history && issue.status_history.length"
        class="relative pl-5 border-l-2 border-stone-200 space-y-4"
      >
        <div v-for="h in issue.status_history" :key="h.id" class="relative">
          <div class="absolute -left-[25px] top-1 w-3 h-3 rounded-full bg-[#B91C1C]"></div>
          <span
            class="px-2 py-0.5 text-[11px] font-medium rounded-full"
            :class="STATUS_BADGE[h.status] || 'bg-stone-100 text-stone-500'"
          >
            {{ STATUS_LABELS[h.status] || h.status }}
          </span>
          <p class="text-sm text-stone-700 mt-1">{{ h.note }}</p>
          <p class="text-xs text-stone-400">{{ fmtDate(h.created_at) }}</p>
        </div>
      </div>
      <p v-else class="text-sm text-stone-400">ไม่มีประวัติ</p>
    </div>

    <!-- 🏛️ Modal อนุมัติเผยแพร่ PIRI Board -->
    <ApproveBoardModal :issue="issue" v-model:open="approveOpen" @approved="onApproved" />
  </div>
</template>
