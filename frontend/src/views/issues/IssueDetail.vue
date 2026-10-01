<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import Swal from 'sweetalert2'
import { BRAND } from '@/constants/brand'
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
import { avatarCharOf } from '@/utils/avatar'
import { fmtDateTime } from '@/datetime'
import { useIsDesktop } from '@/composables/useMediaQuery'
import AppCard from '@/components/ui/AppCard.vue'
import AppButton from '@/components/ui/AppButton.vue'
import AppEmptyState from '@/components/ui/AppEmptyState.vue'
import AppSheet from '@/components/ui/AppSheet.vue'
import IconButton from '@/components/ui/IconButton.vue'
import StatusBadge from '@/components/ui/StatusBadge.vue'
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
    title: 'เปลี่ยนผู้รับของเรื่อง',
    html:
      'เรื่องจะถูกส่งไป<span class="font-semibold">' +
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
    Swal.fire({
      icon: 'success',
      title: 'เปลี่ยนปลายทางแล้ว',
      timer: 1200,
      showConfirmButton: false,
    })
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
    if (issue.value)
      void notificationsStore.read({ entity_type: 'issue', entity_id: issue.value.id })
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
  // เฉพาะผู้แจ้งเท่านั้นที่กดยกเลิก (กันส่งผิด) — ผู้ดูแลใช้ปฏิเสธเรื่องแทน
  if (!isReporter.value) return false
  // เรื่องที่ปิดแล้ว ยกเลิกไม่ได้
  if (issue.value.status === 'resolved') return false
  return true
})

// ผู้ดูแล (ผู้รับ/admin) ปฏิเสธเรื่อง — ต่างจากผู้แจ้งยกเลิก (backend แยกเป็น status 'rejected')
const canReject = computed(() => {
  if (!issue.value || !authStore.user) return false
  if (isReporter.value) return false
  if (!canManage.value) return false
  // เรื่องที่ปิดแล้ว ปฏิเสธไม่ได้
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
    confirmButtonColor: BRAND,
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
    title: reporterCancel ? 'ยกเลิกเรื่องนี้?' : 'ปฏิเสธเรื่องนี้?',
    text: reporterCancel
      ? 'กันส่งผิดหรือไม่ต้องการแล้ว — เมื่อยกเลิกแล้วจะกู้คืนไม่ได้'
      : 'ผู้ดูแลกำลังปฏิเสธเรื่องนี้ — หลังปฏิเสธแล้วจะกู้คืนไม่ได้',
    input: 'text',
    inputPlaceholder: 'เหตุผล (ไม่บังคับ)',
    showCancelButton: true,
    confirmButtonText: reporterCancel ? 'ยกเลิกเรื่อง' : 'ปฏิเสธเรื่อง',
    confirmButtonColor: BRAND,
    cancelButtonText: 'กลับไป',
  })
  if (value === undefined) return

  try {
    await cancelIssue(issue.value.id, value || undefined)
    Swal.fire({
      icon: 'success',
      title: reporterCancel ? 'ยกเลิกเรื่องแล้ว' : 'ปฏิเสธเรื่องแล้ว',
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

/**
 * 🎯 **แถบปฏิบัติการ — ปุ่มเดียวต่อหนึ่ง "งานที่รออยู่จริง"**
 *
 * ⭐ ของเดิมมีปุ่มเต็มความกว้าง **9 ปุ่ม** เรียงเท่ากันหมด (`:577-651`) ⇒ ผู้ใช้ต้องอ่านทั้งหน้า
 *    เพื่อหาว่า "ตกลงฉันต้องกดอะไร" ซึ่งเป็นข้อที่ audit ฟ้องตรง ๆ
 *
 * ⇒ แยกเป็น **1 ปุ่มหลัก** (อยู่ในแถบปักล่าง — โซนนิ้วโป้ง) + ที่เหลือใน `⋯`
 *    · นิยามปุ่มรองเป็น **ข้อมูลชุดเดียว** (`secondaryActions`) แล้วให้ทั้งแถบเดสก์ท็อป
 *      และแผ่นมือถือ `v-for` จากตัวเดียวกัน ⇒ เพิ่ม/ถอดปุ่มในอนาคตแก้ที่เดียว
 *      ไม่มีทางที่สองที่จะไม่ตรงกัน
 *    · **กรองสิทธิ์ตอนสร้างรายการ ไม่ใช่ `disabled`** — เมนูที่กดไม่ได้คือความรกที่ audit ฟ้อง
 *      (หลักการ "ไม่ใส่เมนูที่ผู้ใช้ไม่มีสิทธิ์")
 */
interface ActionItem {
  key: string
  label: string
  icon: string
  /** ผูกกับ e2e ที่มีอยู่ (`piri-boards-flow.spec.ts`) — ห้ามถอด */
  testid?: string
  danger?: boolean
  run: () => void
}

const moreOpen = ref(false)

/**
 * 🔴 **ต้องรู้ขนาดจอ ไม่ใช่แค่ซ่อนด้วย CSS** — ดูเหตุผลเต็มในคอมเมนต์ของ `useMediaQuery.ts`
 *    (สรุป: CSS ซ่อนแต่โหนดยังอยู่ใน DOM ⇒ `data-testid` ซ้ำ ⇒ Playwright strict mode ระเบิด)
 */
const isDesktop = useIsDesktop()

/**
 * 🔴 **`canApprove` มาก่อน `canReceive`** — ทั้งคู่จริงพร้อมกันได้ (แอดมิน/สภารับเรื่องได้ทุกเรื่อง)
 *    แต่เรื่องที่ขอ `vote`/`talk` และยังไม่ถูกอนุมัติ "งานที่รออยู่จริง" คือการอนุมัติ
 *    ไม่ใช่การรับเข้าไปดำเนินการเอง ⇒ ถ้าให้ `canReceive` ชนะ ผู้ใช้อบรมจะต้องไปงมปุ่มอนุมัติใน `⋯`
 *    ทั้งที่มันคือขั้นถัดไปของเรื่องนั้น
 *
 * ⚠️ **แผนเดิมเขียนว่า `กำลังดำเนินการ` → "อัปเดตความคืบหน้า"** ซึ่งในระบบนี้ **ไม่มี endpoint นั้น**
 *    ⇒ ใช้ "เพิ่มความคืบหน้า" ที่เลื่อน+โฟกัสช่องเพิ่มขั้นตอนแทน (เป็นการกระทำจริง ไม่ใช่ปุ่มหลอก)
 *    และ **ไม่ยก "ปิดเรื่อง" ขึ้นมาเป็นปุ่มหลัก** เพราะการปิดเป็นทางตันที่กดพลาดแล้วกู้ยาก
 *    ⇒ อยู่ล่างใน `⋯` ตามหลัก "ปุ่มอันตรายนอกโซนนิ้วโป้ง"
 */
const primaryAction = computed<ActionItem | null>(() => {
  if (!issue.value) return null
  if (canApprove.value) {
    return {
      key: 'approve',
      label: 'อนุมัติเผยแพร่สาธารณะ',
      icon: 'bi-people-fill',
      testid: 'approve-public-btn',
      run: () => {
        approveOpen.value = true
      },
    }
  }
  if (canReceive.value) {
    return {
      key: 'receive',
      label: 'รับเรื่อง + ตั้งเวลา',
      icon: 'bi-hand-thumbs-up',
      run: handleAccept,
    }
  }
  if (canManage.value && issue.value.status === 'in_progress') {
    return {
      key: 'progress',
      label: 'เพิ่มความคืบหน้า',
      icon: 'bi-plus-circle',
      run: focusStepComposer,
    }
  }
  return null
})

const secondaryActions = computed<ActionItem[]>(() => {
  const i = issue.value
  if (!i) return []
  const list: ActionItem[] = []

  if (canEditIssue.value) {
    list.push({
      key: 'edit',
      label: 'แก้ไขเรื่อง',
      icon: 'bi-pencil-square',
      run: () => router.push({ name: 'issue-edit', params: { id: i.id } }),
    })
  }
  if (canChangeDestination.value) {
    list.push({
      key: 'destination',
      label: 'เปลี่ยนผู้รับ',
      icon: 'bi-arrow-repeat',
      testid: 'change-dest-btn',
      run: handleChangeDestination,
    })
  }
  // 🔴 ดึงออกเป็นตัวแปรก่อน — `publishedBoardId.value` เป็น `number | null` และโปรเจกต์นี้เปิด
  //    `noUncheckedIndexedAccess` ⇒ การใช้ `!` ในเทมเพลต/คอมโพเนนต์เป็นทางที่ type-check จับได้ทีหลัง
  const bid = publishedBoardId.value
  if (bid !== null) {
    list.push({
      key: 'board',
      label: 'ดู PIRI Board สาธารณะ',
      icon: 'bi-box-arrow-up-right',
      testid: 'board-link',
      run: () => router.push({ name: 'board-detail', params: { id: bid } }),
    })
  }
  if (canManage.value && canEscalate.value) {
    list.push({
      key: 'escalate',
      label: 'ส่งต่อไประดับบน',
      icon: 'bi-arrow-up-circle',
      run: handleEscalate,
    })
  }
  if (canManage.value && i.status === 'in_progress') {
    list.push({
      key: 'resolve',
      label: 'ปิดเรื่อง (เสร็จแล้ว)',
      icon: 'bi-check2-circle',
      run: handleResolve,
    })
  }
  if (canManage.value && i.countdown && i.status === 'in_progress') {
    list.push({
      key: 'extend',
      label: 'ยืดเวลา',
      icon: 'bi-clock-history',
      run: handleExtendCountdown,
    })
  }
  if (canCancel.value || canReject.value) {
    list.push({
      key: 'cancel',
      label: isReporter.value ? 'ยกเลิกเรื่อง' : 'ปฏิเสธเรื่อง',
      icon: 'bi-x-circle',
      danger: true,
      run: handleCancel,
    })
  }
  return list
})

/** ปิดแผ่นก่อนเสมอ — ไม่งั้น Swal ที่เด้งขึ้นจะซ้อนกับแผ่นที่ยังเปิดอยู่ */
function runSecondary(a: ActionItem) {
  moreOpen.value = false
  a.run()
}

/** อินพุต "เพิ่มขั้นตอน" — เป้าของปุ่มหลักตอนสถานะเป็น `กำลังดำเนินการ` */
const stepTitleInput = ref<HTMLInputElement | null>(null)
function focusStepComposer() {
  const el = stepTitleInput.value
  if (!el) return
  el.scrollIntoView({ behavior: 'smooth', block: 'center' })
  // ⚠️ `preventScroll` — ไม่งั้นเบราว์เซอร์จะกระโดดอีกรอบหลัง `scrollIntoView` ที่ตั้งใจทำความนุ่ม
  el.focus({ preventScroll: true })
}

/** ตัวนับความคืบหน้า — "2/5" บอกได้ทันทีว่าเรื่องนี้เดินไปถึงไหนโดยไม่ต้องอ่านทีละบรรทัด */
const completedSteps = computed(() => issue.value?.steps?.filter((s) => s.is_completed).length ?? 0)

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
  <div v-if="isLoading" class="mx-auto max-w-3xl animate-pulse space-y-4">
    <AppCard>
      <div class="h-3 w-32 rounded bg-canvas"></div>
      <div class="mt-3 flex gap-2">
        <div class="h-6 w-24 rounded-full bg-canvas"></div>
        <div class="h-6 w-20 rounded-full bg-canvas"></div>
      </div>
    </AppCard>
    <AppCard>
      <div class="h-3 w-24 rounded bg-canvas"></div>
      <div class="mt-3 h-6 w-3/4 rounded-lg bg-canvas"></div>
      <div class="mt-4 h-4 w-full rounded bg-canvas"></div>
      <div class="mt-2 h-4 w-2/3 rounded bg-canvas"></div>
    </AppCard>
  </div>

  <!-- โหลดไม่สำเร็จ — `AppEmptyState` (ไม่มีกรอบเส้นประแล้ว) + ทางออกคือปุ่มลองใหม่ -->
  <div v-else-if="loadError" class="mx-auto max-w-3xl">
    <AppCard>
      <AppEmptyState icon="bi-wifi-off" title="เปิดเรื่องนี้ไม่ได้" :description="loadError">
        <AppButton variant="secondary" size="sm" @click="load">
          <template #icon><i class="bi bi-arrow-clockwise" /></template>
          ลองอีกครั้ง
        </AppButton>
      </AppEmptyState>
    </AppCard>
  </div>

  <div v-else-if="issue" class="mx-auto flex max-w-3xl flex-col gap-4">
    <!-- ① สถานะ + SLA — "ตอนนี้เรื่องนี้อยู่ไหน" ต้องตอบได้ก่อนอย่างอื่น -->
    <AppCard>
      <div class="flex items-start justify-between gap-3">
        <div class="min-w-0">
          <p class="text-[13px] font-medium text-ink-3">สถานะปัจจุบัน</p>
          <div class="mt-2 flex flex-wrap items-center gap-2">
            <StatusBadge :status="issue.status" :label="STATUS_LABELS[issue.status]" size="full" />
            <span
              class="inline-flex items-center gap-1.5 rounded-full bg-canvas px-2.5 py-1 text-[13px] font-semibold text-ink-2"
            >
              <i class="bi bi-diagram-3" aria-hidden="true" />
              {{ LEVEL_LABELS[issue.current_level] }}
            </span>
            <!-- 🔁 ปลายทางที่ผู้แจ้งขอ — สำคัญพอจะอยู่การ์ดสถานะ ไม่ใช่ไปกองกับชิปหมวด -->
            <span
              v-if="issue.requested_destination && issue.requested_destination !== 'normal'"
              class="inline-flex items-center gap-1.5 rounded-full bg-brand-tint px-2.5 py-1 text-[13px] font-semibold text-brand"
            >
              <i class="bi bi-send" aria-hidden="true" />
              {{ DESTINATION_LABELS[issue.requested_destination] }}
            </span>
          </div>
        </div>
        <!-- 🔖 บันทึกไว้อ่านทีหลัง (C2) — อยู่การ์ดหัวเรื่อง ไม่ใช่แถบปุ่มด้านล่าง -->
        <BookmarkButton entity-type="issue" :entity-id="issue.id" />
      </div>

      <!-- ⏳ SLA — คงแถบสีซ้ายแบบเดิมไว้ (ของดีที่มีอยู่แล้ว) แต่ผูกสีกับ token ของสถานะ -->
      <div
        v-if="issue.countdown"
        class="mt-4 flex items-center justify-between gap-3 rounded-control border-l-4 p-3.5"
        :class="
          issue.countdown.is_overdue ? 'border-l-danger bg-danger-soft' : 'border-l-brand bg-canvas'
        "
      >
        <div class="flex min-w-0 items-center gap-2.5">
          <i
            class="bi bi-hourglass-split text-lg"
            :class="issue.countdown.is_overdue ? 'text-danger' : 'text-brand'"
            aria-hidden="true"
          />
          <div class="min-w-0">
            <p class="text-[13px] font-semibold text-ink-1">กำหนดแก้ไข</p>
            <p class="text-[13px] text-ink-2">
              ตั้งไว้ {{ issue.countdown.estimated_days }} วัน · ถึง
              {{ fmtDateTime(issue.countdown.deadline) }}
            </p>
          </div>
        </div>
        <p
          class="shrink-0 font-display text-title-m font-bold"
          :class="issue.countdown.is_overdue ? 'text-danger' : 'text-brand'"
        >
          {{ issue.countdown.is_overdue ? 'เกินเวลา!' : countdownLabel(issue.countdown.deadline) }}
        </p>
      </div>
    </AppCard>

    <!-- ② เรื่องที่แจ้ง -->
    <AppCard>
      <!-- 🏷️ เหลือ 2 ชิป (หมวดหลักเป็น *คำนำหน้า* ของหมวดย่อยที่อ่านออกได้เอง) — ระดับย้ายไปการ์ดสถานะ -->
      <p class="text-[11px] font-medium text-ink-3">
        {{ MAIN_CATEGORY_LABELS[issue.main_category] }} ·
        {{ subcategoryLabel(issue.main_category, issue.category) }}
      </p>
      <!-- ⚠️ `<h2>` ไม่ใช่ `<h1>` — `<h1>` ของหน้าอยู่ที่ `AppHeader` แล้ว (R0.3.1) -->
      <h2 class="mt-1.5 text-title-l font-bold leading-snug break-words text-ink-1">
        {{ issue.title }}
      </h2>
      <p class="mt-3 whitespace-pre-wrap text-body text-ink-1">{{ issue.description }}</p>
      <img
        v-if="issue.image_url"
        :src="issue.image_url"
        alt="ภาพประกอบที่แนบมากับเรื่อง"
        class="mt-3 max-h-80 w-full rounded-control border border-line object-cover"
      />
    </AppCard>

    <!-- ③ ขั้นตอนการดำเนินงาน -->
    <AppCard>
      <div class="flex items-center justify-between gap-3">
        <h2 class="text-base font-bold text-ink-1">ขั้นตอนการดำเนินงาน</h2>
        <span v-if="issue.steps && issue.steps.length" class="text-[13px] font-medium text-ink-3">
          {{ completedSteps }}/{{ issue.steps.length }}
        </span>
      </div>

      <ul v-if="issue.steps && issue.steps.length" class="mt-1 divide-y divide-line">
        <li v-for="s in issue.steps" :key="s.id" class="flex items-start gap-3 py-3">
          <!-- ปุ่มทำเครื่องหมาย — ต้องมี aria-label เพราะปุ่มที่มีแต่ไอคอนอ่านไม่ออก -->
          <button
            v-if="canManage && !s.is_completed"
            type="button"
            class="tap-44 mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full border-2 border-line text-ink-3 transition-colors hover:border-brand hover:text-brand"
            :aria-label="`ทำเครื่องหมายว่าขั้นตอน “${s.step_title}” เสร็จแล้ว`"
            @click="handleCompleteStep(s.id)"
          >
            <i class="bi bi-check text-sm" aria-hidden="true" />
          </button>
          <span
            v-else
            class="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full"
            :class="s.is_completed ? 'bg-ok text-white' : 'bg-canvas'"
            aria-hidden="true"
          >
            <i v-if="s.is_completed" class="bi bi-check text-sm" />
          </span>
          <div class="min-w-0 flex-1">
            <p
              class="text-sm font-medium"
              :class="s.is_completed ? 'text-ink-3 line-through' : 'text-ink-1'"
            >
              {{ s.step_title }}
            </p>
            <p v-if="s.step_detail" class="mt-0.5 text-[13px] text-ink-2">{{ s.step_detail }}</p>
          </div>
        </li>
      </ul>
      <p v-else class="mt-2 text-[13px] text-ink-3">ยังไม่มีขั้นตอนการดำเนินงาน</p>

      <div v-if="canManage" class="mt-3 grid gap-2 border-t border-line pt-3 sm:grid-cols-2">
        <input
          ref="stepTitleInput"
          v-model="newStepTitle"
          type="text"
          placeholder="เพิ่มขั้นตอน..."
          class="field"
          @keyup.enter="handleAddStep"
        />
        <input
          v-model="newStepDetail"
          type="text"
          placeholder="รายละเอียด (ไม่บังคับ)"
          class="field"
          @keyup.enter="handleAddStep"
        />
        <AppButton
          variant="secondary"
          size="sm"
          class="sm:col-span-2 sm:justify-self-start"
          :disabled="!newStepTitle.trim()"
          @click="handleAddStep"
        >
          <template #icon><i class="bi bi-plus-lg" /></template>
          เพิ่มขั้นตอน
        </AppButton>
      </div>
    </AppCard>

    <!-- ④ ประวัติการดำเนินงาน (ไทม์ไลน์) — มาก่อนคอมเมนต์ เพราะเป็น "เรื่อง" ไม่ใช่ "บทสนทนา" -->
    <AppCard>
      <h2 class="text-base font-bold text-ink-1">ประวัติการดำเนินงาน</h2>
      <div
        v-if="issue.status_history && issue.status_history.length"
        class="relative mt-3 space-y-4 border-l-2 border-line pl-5"
      >
        <div v-for="h in issue.status_history" :key="h.id" class="relative">
          <span
            class="absolute -left-[25px] top-1.5 h-3 w-3 rounded-full bg-brand"
            aria-hidden="true"
          />
          <StatusBadge :status="h.status" :label="STATUS_LABELS[h.status]" size="full" />
          <p v-if="h.note" class="mt-1.5 text-sm text-ink-1">{{ h.note }}</p>
          <p class="mt-0.5 text-caption text-ink-3">{{ fmtDateTime(h.created_at) }}</p>
        </div>
      </div>
      <p v-else class="mt-2 text-[13px] text-ink-3">ไม่มีประวัติ</p>
    </AppCard>

    <!-- ⑤ คอมเมนต์ -->
    <AppCard>
      <div class="flex items-center justify-between gap-3">
        <h2 class="text-base font-bold text-ink-1">คอมเมนต์</h2>
        <span
          v-if="issue.comments && issue.comments.length"
          class="text-[13px] font-medium text-ink-3"
        >
          {{ issue.comments.length }}
        </span>
      </div>

      <div v-if="issue.comments && issue.comments.length" class="mt-1 divide-y divide-line">
        <div v-for="c in issue.comments" :key="c.id" class="py-3.5 first:pt-3 last:pb-0">
          <div class="flex items-center justify-between gap-2">
            <div class="flex min-w-0 items-center gap-2.5">
              <span
                class="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-canvas text-sm font-bold text-ink-2"
                aria-hidden="true"
              >
                {{ avatarCharOf(c.commenter_name || c.commenter_first_name) }}
              </span>
              <div class="min-w-0">
                <p class="truncate text-sm font-medium text-ink-1">
                  {{ c.commenter_name || 'ไม่ระบุชื่อ' }}
                  <span v-if="c.commenter_room" class="text-[11px] font-normal text-ink-3">
                    ({{ c.commenter_room }})
                  </span>
                </p>
                <p class="text-[11px] text-ink-3">
                  {{ fmtDateTime(c.created_at) }}
                  <span v-if="c.updated_at">· แก้ไข {{ fmtDateTime(c.updated_at) }}</span>
                </p>
              </div>
            </div>
            <!-- แก้/ลบได้เฉพาะคอมเมนต์ของตัวเอง — `IconButton` บังคับ `label` (a11y) -->
            <div v-if="c.user_id === authStore.user?.id" class="flex shrink-0 gap-0.5">
              <IconButton
                icon="bi-pencil"
                label="แก้ไขคอมเมนต์นี้"
                @click="handleEditComment(c.id, c.body)"
              />
              <IconButton
                icon="bi-trash"
                label="ลบคอมเมนต์นี้"
                danger
                @click="handleDeleteComment(c.id)"
              />
            </div>
          </div>
          <p class="mt-2 whitespace-pre-wrap break-words text-sm text-ink-1">{{ c.body }}</p>
        </div>
      </div>
      <p v-else class="mt-2 text-[13px] text-ink-3">
        ยังไม่มีคอมเมนต์ — เป็นคนแรกที่รับทราบเรื่องนี้
      </p>

      <!-- ช่องพิมพ์คอมเมนต์ -->
      <div class="mt-3 flex gap-2 border-t border-line pt-3">
        <input
          v-model="newComment"
          type="text"
          placeholder="พิมพ์คอมเมนต์..."
          class="field"
          maxlength="1000"
          @keyup.enter="handleAddComment"
        />
        <AppButton :disabled="!newComment.trim()" @click="handleAddComment">
          <template #icon><i class="bi bi-send" /></template>
          ส่ง
        </AppButton>
      </div>
    </AppCard>

    <!-- ⑥ ข้อมูลผู้แจ้ง — งาน "อ่านประกอบ" ⇒ ไว้ท้ายสุด และพื้นเทาเพื่อลดน้ำหนัก -->
    <AppCard muted>
      <h2 class="text-base font-bold text-ink-1">ข้อมูลผู้แจ้ง</h2>
      <dl class="mt-2 space-y-1.5 text-sm">
        <div class="flex gap-2">
          <dt class="w-20 shrink-0 text-ink-3">ผู้แจ้ง</dt>
          <dd class="min-w-0 break-words text-ink-1">
            {{ issue.reporter_name || 'ไม่ระบุชื่อ' }}
            <span v-if="issue.reporter_room" class="text-ink-3">({{ issue.reporter_room }})</span>
          </dd>
        </div>
        <div v-if="issue.room_name" class="flex gap-2">
          <dt class="w-20 shrink-0 text-ink-3">ห้อง</dt>
          <dd class="min-w-0 break-words text-ink-1">{{ issue.room_name }}</dd>
        </div>
        <div class="flex gap-2">
          <dt class="w-20 shrink-0 text-ink-3">แจ้งเมื่อ</dt>
          <dd class="text-ink-1">{{ fmtDateTime(issue.created_at) }}</dd>
        </div>
        <div v-if="issue.current_assignee_name" class="flex gap-2">
          <dt class="w-20 shrink-0 text-ink-3">ผู้รับผิดชอบ</dt>
          <dd class="min-w-0 break-words text-ink-1">
            {{ issue.current_assignee_name }}
            <span v-if="issue.current_assignee_role" class="text-ink-3">
              ({{ issue.current_assignee_role }})
            </span>
          </dd>
        </div>
      </dl>

      <!--
        🔴 **ห้ามสัญญาเกินจริงเรื่องนิรนาม** — `is_anonymous` ซ่อนชื่อ *ผู้แจ้ง* แต่ชื่อผู้เขียน
           คอมเมนต์เป็น **ชื่อจริงเสมอ** (`CommentOut.commenter_name`) ⇒ ถ้าโชว์แค่ป้าย
           "ไม่ระบุตัวตน" เฉย ๆ ผู้ใช้จะเข้าใจว่าคลุมทั้งหน้า แล้วไปคอมเมนต์โดยคิดว่าตัวเองนิรนาม
      -->
      <p
        v-if="issue.is_anonymous"
        class="mt-3 flex gap-2 rounded-control bg-warn-soft p-2.5 text-[13px] leading-relaxed text-ink-1"
      >
        <i class="bi bi-incognito mt-0.5 shrink-0" aria-hidden="true" />
        <span>
          เรื่องนี้แจ้งแบบ <b>ไม่ระบุตัวตน</b> — ซ่อนชื่อผู้แจ้งเท่านั้น ส่วน<b
            >คอมเมนต์ยังแสดงชื่อจริงของผู้เขียนเสมอ</b
          >
        </span>
      </p>
    </AppCard>

    <!--
      ⚑ แถบปฏิบัติการ — มือถือปักขอบล่าง (โซนนิ้วโป้ง) · เดสก์ท็อปเป็นแถวบนสุดแบบเดิม
        ⭐ **ปุ่มถูกนิยามครั้งเดียว** (`primaryAction` / `secondaryActions`) แล้วให้ทั้งแถบนี้
          และแผ่น `⋯` เรนเดอร์จากตัวเดียวกัน ⇒ ไม่มีทางที่สองชุดจะให้สิทธิ์ไม่ตรงกัน
          ⇒ จึงเลื่อนตำแหน่งด้วย `order` ไม่ใช่เรนเดอร์สองก้อน

        🔴 **`bottom-0` เฉย ๆ ถูกต้องแล้ว — ห้ามเปลี่ยนไปบวก `--app-nav-h`**
           「วัดจริงแล้ว (Chromium · จอ 360×740)」:
             · `bottom-0`                    → แถบอยู่เหนือ bottom nav **16px** · ปักอยู่นิ่ง · ไม่ทับการ์ดสุดท้าย
             · `bottom: calc(nav + safe + .5rem)` → อยู่เหนือ nav **80px** และ **ทับการ์ดสุดท้าย 48px**
           เพราะ `<main>` มี `pb-[calc(var(--app-nav-h)+safe+1rem)]` อยู่แล้ว ⇒ Chromium คิดขอบเขต
           `sticky` จาก **content box** ของ scroll container ⇒ ระยะที่ `<main>` เว้นไว้ให้แถบล่าง
           ถูกนับเป็นระยะปักไปในตัว · การบวกซ้ำจึงดันแถบลอยสูงเกินและไปทับเนื้อหา

        ⚠️ แถบต้องเป็น **ลูกคนสุดท้ายที่จะเข้าลำดับการไหล** (อยู่ก่อน `AppSheet`/`ApproveBoardModal`
           ที่ `Teleport`/`fixed` จึงไม่กินที่) — ถ้าย้ายไปไว้บนสุดของบล็อก แถบจะถูกดึงขึ้นทับการ์ด
           เหนือมัน ณ ตำแหน่งเลื่อนสุด (ตรรกะเดียวกับที่วัดได้ข้างบน)
    -->
    <div
      v-if="primaryAction || secondaryActions.length"
      class="bottom-0 sticky z-30 lg:static lg:order-first"
    >
      <div class="flex flex-wrap items-center gap-2 rounded-card border border-line bg-surface p-2">
        <AppButton
          v-if="primaryAction"
          :data-testid="primaryAction.testid"
          class="grow lg:grow-0"
          @click="primaryAction.run()"
        >
          <template #icon><i :class="['bi', primaryAction.icon]" /></template>
          {{ primaryAction.label }}
        </AppButton>

        <!--
          🔴 **สลับด้วย `v-if` ไม่ใช่ `lg:hidden`** — วัดบน staging แล้วเจอของจริง:
             ถ้าใช้ CSS ซ่อน โหนด**ยังอยู่ใน DOM ทั้งสองชุด** ⇒ พอเปิดแผ่นที่จอ 360dp
             จะมี `data-testid="change-dest-btn"` **2 ตัว** (แผ่น 1 + แถวเดสก์ท็อปที่ถูกซ่อน 1)
             ⇒ Playwright strict mode **นับทุกโหนดที่ match ไม่สนใจว่ามองเห็นไหม** ⇒ เทสต์ที่จะเขียน
             อนาคตระเบิดด้วย "resolved to 2 elements" โดยหาสาเหตุยากมาก
             ⇒ ใช้ `useIsDesktop()` คุมให้ **มีชุดเดียวใน DOM เสมอ** (พิสูจน์ได้ ไม่ต้องเชื่อ CSS)
             「ตรวจซ้ำหลังแก้: `data-testid` ทั้งหน้า = 1 ตัวต่อปุ่ม ✅」
        -->
        <IconButton
          v-if="secondaryActions.length && !isDesktop"
          class="ml-auto"
          icon="bi-three-dots"
          label="ตัวเลือกอื่น"
          @click="moreOpen = true"
        />

        <!-- 🖥️ เดสก์ท็อป: ปุ่มรองเรียงในแถวเดียวกัน (แผ่น `AppSheet` เป็น surface ของมือถือ) -->
        <template v-if="isDesktop">
          <AppButton
            v-for="a in secondaryActions"
            :key="a.key"
            :data-testid="a.testid"
            :variant="a.danger ? 'danger' : 'secondary'"
            size="sm"
            @click="a.run()"
          >
            <template #icon><i :class="['bi', a.icon]" /></template>
            {{ a.label }}
          </AppButton>
        </template>
      </div>
    </div>

    <!-- 📱 แผ่นตัวเลือกอื่น — `AppSheet` ใช้ `<Teleport to="body">` + `z-[60]` อยู่ในตัวแล้ว -->
    <AppSheet
      v-model="moreOpen"
      title="ตัวเลือกอื่น"
      :description="`เรื่อง #${issue.id} · ${issue.title}`"
    >
      <button
        v-for="a in secondaryActions"
        :key="a.key"
        type="button"
        :data-testid="a.testid"
        class="flex min-h-[44px] w-full items-center gap-3 rounded-control px-3 py-3 text-left transition-colors hover:bg-canvas"
        :class="a.danger ? 'text-danger' : 'text-ink-1'"
        @click="runSecondary(a)"
      >
        <i
          :class="['bi', a.icon, 'text-lg', a.danger ? 'text-danger' : 'text-ink-2']"
          aria-hidden="true"
        />
        <span class="text-sm font-medium">{{ a.label }}</span>
      </button>
    </AppSheet>

    <!-- 🏛️ Modal อนุมัติเผยแพร่ PIRI Board -->
    <ApproveBoardModal :issue="issue" v-model:open="approveOpen" @approved="onApproved" />
  </div>
</template>
