<script setup lang="ts">
import { ref, computed } from 'vue'
import Swal from 'sweetalert2'
import { BRAND } from '@/constants/brand'
import { addComment, reportComment, hideComment } from '@/services/board'
import { REPORT_REASON_LABELS, type BoardComment, type ReportReason } from '@/types/board'
import { useAuthStore } from '@/stores/auth'

/**
 * 💬 คอมเมนต์ 1 อัน + รีพลายซ้อน (recursive — อ้างอิงตัวเองด้วยชื่อไฟล์)
 * - แสดง avatar/ชื่อ/เวลา/ข้อความ + ปุ่ม "ตอบกลับ"
 * - reply → เปิดช่องพิมพ์ใต้คอมเมนต์ → addComment(parent_id) → emit refresh ให้ parent โหลดใหม่
 * - 🚩 "แจ้ง" (ทุกคน ยกเว้นคอมเมนต์ตัวเอง) → reportComment — สภานักเรียนตรวจสอบ
 * - 🛡️ "ซ่อน" (สภา/แอดมิน) → hideComment (backend ซ่อนทั้ง subtree + ลด counter) → refresh
 * ความลึกถูกจำกัดฝั่ง backend แล้ว (MAX_DISPLAY_DEPTH) — recursive ปลอดภัย
 */
const props = defineProps<{ boardId: number; comment: BoardComment }>()

const emit = defineEmits<{ refresh: [] }>()

const authStore = useAuthStore()
const replying = ref(false)
const replyBody = ref('')
const posting = ref(false)
const acting = ref(false) // กันกดซ้ำระหว่าง report/hide ทำงาน

const isOwn = computed(() => props.comment.user_id != null && props.comment.user_id === authStore.user?.id)

function fmtTime(iso: string): string {
  return new Date(iso).toLocaleString('th-TH', {
    timeZone: 'Asia/Bangkok',
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  })
}

async function submitReply() {
  const body = replyBody.value.trim()
  if (!body) return
  posting.value = true
  try {
    await addComment(props.boardId, body, props.comment.id)
    replyBody.value = ''
    replying.value = false
    Swal.fire({ icon: 'success', title: 'ตอบกลับแล้ว', timer: 1000, showConfirmButton: false })
    emit('refresh')
  } catch (e) {
    Swal.fire({ icon: 'error', title: 'ตอบกลับไม่สำเร็จ', text: e instanceof Error ? e.message : String(e) })
  } finally {
    posting.value = false
  }
}

// 🚩 แจ้งความไม่เหมาะสม (2 ขั้น: เลือกเหตุผล → รายละเอียดเสริม) — ทุกคนยกเว้นคอมเมนต์ตัวเอง
async function handleReport() {
  if (acting.value || isOwn.value) return
  const { value: reason } = await Swal.fire({
    title: 'แจ้งความไม่เหมาะสม',
    text: 'คอมเมนต์นี้ผิดกฎ/ไม่เหมาะสมอย่างไร?',
    icon: 'question',
    input: 'select',
    inputOptions: REPORT_REASON_LABELS,
    inputPlaceholder: 'เลือกเหตุผล',
    showCancelButton: true,
    confirmButtonText: 'ถัดไป',
    cancelButtonText: 'ยกเลิก',
  })
  if (!reason) return

  const { value: detail, isConfirmed } = await Swal.fire({
    title: 'รายละเอียดเพิ่มเติม',
    input: 'textarea',
    inputPlaceholder: 'อธิบายเพิ่มเติม (ไม่บังคับ)',
    inputAttributes: { maxlength: '500' },
    showCancelButton: true,
    confirmButtonText: 'ส่งรายงาน',
    cancelButtonText: 'ยกเลิก',
  })
  if (!isConfirmed) return

  acting.value = true
  try {
    await reportComment(props.boardId, props.comment.id, {
      reason: reason as ReportReason,
      detail: detail ? String(detail).trim() : undefined,
    })
    Swal.fire({ icon: 'success', title: 'แจ้งแล้ว', text: 'สภานักเรียนจะตรวจสอบให้เร็วที่สุด', timer: 1600, showConfirmButton: false })
  } catch (e) {
    Swal.fire({ icon: 'error', title: 'แจ้งไม่สำเร็จ', text: e instanceof Error ? e.message : String(e) })
  } finally {
    acting.value = false
  }
}

// 🛡️ ซ่อนคอมเมนต์ (สภา/แอดมิน) — ต้องระบุเหตุผล
async function handleHide() {
  if (acting.value) return
  const { value } = await Swal.fire({
    title: 'ซ่อนคอมเมนต์นี้?',
    text: 'คอมเมนต์ + รีพลายทั้งหมดจะถูกซ่อน (ผู้แจ้ง/คนอื่นมองไม่เห็น)',
    icon: 'warning',
    input: 'text',
    inputPlaceholder: 'เหตุผลที่ซ่อน (จำเป็น)',
    inputAttributes: { maxlength: '200' },
    showCancelButton: true,
    confirmButtonText: 'ซ่อนคอมเมนต์',
    confirmButtonColor: BRAND,
    cancelButtonText: 'ยกเลิก',
  })
  if (!value || !String(value).trim()) {
    if (value !== undefined) Swal.fire({ icon: 'warning', title: 'ต้องระบุเหตุผล', text: 'กรุณากรอกเหตุผลที่ซ่อน' })
    return
  }
  acting.value = true
  try {
    await hideComment(props.boardId, props.comment.id, String(value).trim())
    Swal.fire({ icon: 'success', title: 'ซ่อนคอมเมนต์แล้ว', timer: 1200, showConfirmButton: false })
    emit('refresh')
  } catch (e) {
    Swal.fire({ icon: 'error', title: 'ซ่อนไม่สำเร็จ', text: e instanceof Error ? e.message : String(e) })
  } finally {
    acting.value = false
  }
}
</script>

<template>
  <div data-testid="comment-node" class="pl-4 border-l-2 border-stone-100">
    <!-- ตัวคอมเมนต์ -->
    <div class="flex gap-2.5">
      <div
        class="w-8 h-8 rounded-full bg-brand/10 text-brand flex items-center justify-center font-bold text-sm shrink-0"
      >
        {{ (comment.commenter_first_name || comment.commenter_name || '?').charAt(0) }}
      </div>
      <div class="min-w-0 flex-1">
        <div class="flex items-center gap-2 flex-wrap">
          <span class="text-sm font-semibold text-stone-800">{{ comment.commenter_name || 'ไม่ระบุชื่อ' }}</span>
          <span class="text-xs text-stone-400">{{ fmtTime(comment.created_at) }}</span>
          <span v-if="comment.is_edited" class="text-[11px] text-stone-400">· แก้ไขแล้ว</span>
        </div>
        <p class="text-sm text-stone-700 mt-0.5 whitespace-pre-wrap break-words">{{ comment.body }}</p>
        <!-- action: ตอบกลับ / แจ้ง (ทุกคน ยกเว้นตัวเอง) / ซ่อน (สภา/แอดมิน) -->
        <div class="mt-1 flex items-center gap-3 text-xs">
          <button
            type="button"
            data-testid="reply-btn"
            @click="replying = !replying"
            class="text-stone-400 hover:text-brand font-medium flex items-center gap-1"
          >
            <i class="bi bi-reply"></i> ตอบกลับ
          </button>
          <button
            v-if="!isOwn"
            type="button"
            data-testid="report-btn"
            @click="handleReport"
            :disabled="acting"
            class="text-stone-400 hover:text-brand font-medium flex items-center gap-1 disabled:opacity-40"
          >
            <i class="bi bi-flag"></i> แจ้ง
          </button>
          <button
            v-if="authStore.isCouncilAuthority"
            type="button"
            data-testid="hide-btn"
            @click="handleHide"
            :disabled="acting"
            class="text-stone-400 hover:text-brand font-medium flex items-center gap-1 disabled:opacity-40"
          >
            <i class="bi bi-eye-slash"></i> ซ่อน
          </button>
        </div>

        <!-- ช่องตอบกลับ -->
        <div v-if="replying" class="mt-2 flex gap-2">
          <input
            v-model="replyBody"
            type="text"
            placeholder="พิมพ์คำตอบ..."
            maxlength="1000"
            class="flex-1 px-3 py-2 border border-stone-300 rounded-xl text-sm"
            @keyup.enter="submitReply"
          />
          <button
            type="button"
            :disabled="posting || !replyBody.trim()"
            @click="submitReply"
            class="px-3.5 py-2 bg-brand text-white rounded-xl text-sm hover:bg-brand-strong disabled:opacity-50"
          >
            {{ posting ? '...' : 'ตอบ' }}
          </button>
        </div>
      </div>
    </div>

    <!-- รีพลายซ้อน (recursive — self-reference ด้วยชื่อไฟล์) -->
    <div v-if="comment.replies.length" class="mt-3 space-y-3">
      <CommentThread v-for="r in comment.replies" :key="r.id" :board-id="boardId" :comment="r" @refresh="emit('refresh')" />
    </div>
  </div>
</template>
