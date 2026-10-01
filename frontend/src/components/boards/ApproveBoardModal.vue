<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import Swal from 'sweetalert2'
import { approveToPublic } from '@/services/issue'
import { DESTINATION_LABELS, type Issue } from '@/types/issue'
import { BOARD_TYPE_LABELS, type PublicBoardType } from '@/types/board'

/**
 * 🏛️ Modal อนุมัติเผยแพร่สาธารณะ (สภานักเรียน/แอดมิน)
 * - board_type ถูก lock ตาม requested_destination ของเรื่อง (vote→vote, talk→talk — backend บังคับ)
 * - vote board → ใส่ตัวเลือกโหวต (อย่างน้อย 2, ไม่ซ้ำ)
 * - talk board → สลับเปิด/ปิดคอมเมนต์ (allow_comments)
 *
 * v-model:open ควบคุมเปิด/ปิด; @approved → คืน board_id ที่สร้าง (parent นำไป navigate)
 */
const props = defineProps<{ issue: Issue | null }>()

const open = defineModel<boolean>('open', { default: false })
const emit = defineEmits<{ approved: [boardId: number] }>()

// ปลายทางที่ขอ (vote/talk เท่านั้นที่เข้ามาถึง modal นี้) — ใช้เป็น board_type ตรง ๆ
// ⚠️ ชนิดเป็น PublicBoardType ไม่ใช่ BoardType — สายอนุมัติสร้าง 'suggestion' ไม่ได้ (E1)
const boardType = computed<PublicBoardType>(() => {
  return props.issue?.requested_destination === 'talk' ? 'talk' : 'vote'
})

const voteChoices = ref<string[]>(['', ''])
const allowComments = ref(true)
const submitting = ref(false)

// เปิด modal → รีเซ็ตฟอร์มทุกครั้ง
watch(
  () => open.value,
  (isOpen) => {
    if (isOpen && props.issue) {
      voteChoices.value = ['', '']
      allowComments.value = true
      submitting.value = false
    }
  },
)

function addChoice() {
  voteChoices.value.push('')
}
function removeChoice(idx: number) {
  if (voteChoices.value.length > 2) voteChoices.value.splice(idx, 1)
}

async function handleConfirm() {
  if (!props.issue) return

  const cleaned = voteChoices.value.map((c) => c.trim()).filter(Boolean)
  if (boardType.value === 'vote') {
    if (cleaned.length < 2) {
      Swal.fire({ icon: 'warning', title: 'ใส่ตัวเลือกไม่ครบ', text: 'บอร์ดโหวตต้องมีตัวเลือกอย่างน้อย 2 ตัวเลือก' })
      return
    }
    if (new Set(cleaned).size !== cleaned.length) {
      Swal.fire({ icon: 'warning', title: 'ตัวเลือกซ้ำกัน', text: 'กรุณาใส่ตัวเลือกแต่ละอันไม่ซ้ำกัน' })
      return
    }
  }

  submitting.value = true
  try {
    const res = await approveToPublic(props.issue.id, {
      board_type: boardType.value,
      vote_choices: boardType.value === 'vote' ? cleaned : undefined,
      allow_comments: allowComments.value,
    })
    Swal.fire({ icon: 'success', title: 'อนุมัติเผยแพร่แล้ว!', text: 'เรื่องถูกเผยแพร่เป็น PIRI Board แล้ว', timer: 1500, showConfirmButton: false })
    open.value = false
    emit('approved', res.board_id)
  } catch (e) {
    Swal.fire({ icon: 'error', title: 'อนุมัติไม่สำเร็จ', text: e instanceof Error ? e.message : String(e) })
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <!-- ⚠️ ต้อง Teleport ออกไปที่ <body> — modal นี้เรนเดอร์อยู่ภายใน stacking context
         ของ `.maincol` (`relative z-10` ใน MainLayout) ⇒ z-50 ข้างในถูกกักไว้ที่ชั้น 10
         และแพ้ bottom tab bar (`fixed z-40`) ที่เป็นพี่น้องกัน ⇒ แถบเมนูล่างทับและกลืนคลิก
         ปุ่มบันทึก. Teleport ทำให้ modal ไปแข่ง z-index ที่ระดับ root แทน -->
  <Teleport to="body">
    <Transition name="modal">
      <div v-if="open && issue" class="fixed inset-0 z-50 flex items-center justify-center p-4" @click.self="open = false">
        <!-- overlay (ไม่เบลอ — ทึบหม่น stone) -->
        <div class="absolute inset-0 bg-stone-900/50"></div>

        <!-- card -->
        <div class="relative w-full max-w-lg bg-white rounded-2xl border border-stone-200 p-5 sm:p-6 max-h-[90vh] overflow-y-auto">
          <div class="flex items-start justify-between gap-3 mb-4">
            <div>
              <!-- 🔴 ไม่มี eyebrow ภาษาอังกฤษ ("Public Board") — `uppercase tracking-widest`
                   ใช้กับข้อความไทยไม่ได้ (สระ/วรรณยุกต์ลอย) และคำว่า "บอร์ด" เป็นคำที่ glossary
                   กำหนดไว้แล้ว ⇒ ชื่อเรื่องบรรทัดเดียวพอ (R5.2) -->
              <h2 class="text-xl font-bold text-stone-900 leading-tight">
                <i class="bi bi-people-fill mr-1 text-brand"></i> อนุมัติเผยแพร่สาธารณะ
              </h2>
              <p class="text-sm text-stone-500 mt-1">สภานักเรียน/แอดมิน พิจารณาเรื่องนี้เป็น PIRI Board</p>
            </div>
            <button type="button" aria-label="ปิด" class="flex h-11 w-11 items-center justify-center rounded-lg text-ink-3 hover:bg-stone-100 hover:text-stone-600" @click="open = false">
              <i class="bi bi-x-lg"></i>
            </button>
          </div>

          <!-- สรุปเรื่อง -->
          <div class="bg-stone-50 border border-stone-100 rounded-xl p-3 mb-4">
            <p class="text-sm font-semibold text-stone-800 break-words">{{ issue.title }}</p>
            <p class="text-xs text-stone-500 mt-0.5">ประเภทที่ขอ: {{ DESTINATION_LABELS[issue.requested_destination || 'normal'] }}</p>
          </div>

          <!-- ประเภท board (lock ตามที่ผู้แจ้งขอ — backend บังคับให้ตรง) -->
          <div class="mb-4">
            <label class="block text-sm font-medium text-stone-700 mb-1.5">ประเภทบอร์ด</label>
            <div class="inline-flex items-center gap-2 px-3 py-2 rounded-xl text-sm font-semibold bg-stone-100 text-stone-600">
              <i :class="boardType === 'vote' ? 'bi bi-bar-chart-fill' : 'bi bi-chat-dots-fill'"></i>
              {{ BOARD_TYPE_LABELS[boardType] }}
            </div>
          </div>

          <!-- vote board → ตั้งค่าตัวเลือกโหวต -->
          <div v-if="boardType === 'vote'" class="mb-4">
            <label class="block text-sm font-medium text-stone-700 mb-1.5">
              ตัวเลือกโหวต <span class="text-ink-3 font-normal">(อย่างน้อย 2 ตัวเลือก)</span>
            </label>
            <div class="space-y-2">
              <div v-for="(c, idx) in voteChoices" :key="idx" class="flex gap-2">
                <input
                  v-model="voteChoices[idx]"
                  type="text"
                  :data-testid="'choice-input-' + idx"
                  :placeholder="`ตัวเลือกที่ ${idx + 1}`"
                  maxlength="200"
                  class="flex-1 px-3 py-2.5 border border-stone-300 rounded-xl text-sm focus:ring-2 focus:ring-brand"
                />
                <button
                  type="button"
                  :disabled="voteChoices.length <= 2"
                  @click="removeChoice(idx)"
                  title="ลบตัวเลือก"
                  class="flex h-11 w-11 items-center justify-center rounded-xl border border-stone-200 text-ink-3 hover:text-brand hover:border-brand/30 disabled:opacity-30 disabled:cursor-not-allowed"
                >
                  <i class="bi bi-trash"></i>
                </button>
              </div>
            </div>
            <button type="button" @click="addChoice" class="mt-2 text-sm text-brand hover:text-brand-strong font-medium flex items-center gap-1">
              <i class="bi bi-plus-circle"></i> เพิ่มตัวเลือก
            </button>
          </div>

          <!-- talk board → เปิด/ปิดคอมเมนต์ -->
          <div v-else class="mb-4">
            <label class="flex items-center gap-2 text-sm text-stone-700 cursor-pointer select-none">
              <input v-model="allowComments" type="checkbox" class="w-4 h-4 rounded bg-white border-stone-300 text-brand focus:ring-brand accent-brand" />
              เปิดให้คอมเมนต์บนบอร์ดได้
            </label>
            <p class="text-xs text-ink-3 mt-1 ml-6">ปิดถ้าอยากให้เป็นบอร์ดอ่านอย่างเดียว (ไม่ให้คอมเมนต์)</p>
          </div>

          <!-- actions -->
          <div class="flex gap-2 pt-2">
            <button type="button" @click="open = false" class="inline-flex flex-1 items-center justify-center min-h-11 py-2.5 rounded-xl bg-stone-100 text-stone-700 hover:bg-stone-200 text-sm font-medium">
              ยกเลิก
            </button>
            <button
              type="button"
              :disabled="submitting"
              data-testid="approve-confirm"
              @click="handleConfirm"
              class="inline-flex flex-1 items-center justify-center min-h-11 py-2.5 rounded-xl bg-brand text-white hover:bg-brand-strong disabled:opacity-50 text-sm font-medium"
            >
              {{ submitting ? 'กำลังอนุมัติ...' : 'อนุมัติเผยแพร่' }}
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.modal-enter-active, .modal-leave-active { transition: opacity 0.2s ease; }
.modal-enter-from, .modal-leave-to { opacity: 0; }
</style>
