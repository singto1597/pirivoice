<script setup lang="ts">
import { ref, watch } from 'vue'
import Swal from 'sweetalert2'
import { createSuggestion } from '@/services/board'

/**
 * 💡 เสนอไอเดีย/ข้อเสนอแนะ (E1) — ฟอร์มสั้น 2 ช่อง: หัวข้อ + รายละเอียด
 *
 * ต่างจาก `ApproveBoardModal` (ซึ่งเป็นของสภา):
 * - **ไม่มีตัวเลือกโหวต** และไม่มีตัวเลือกประเภทบอร์ด — สร้างได้ชนิดเดียว (`suggestion`)
 *   ⇒ backend ไม่รับ `board_type` จาก client เลย (กันช่องเลี่ยงด่านอนุมัติของสภา)
 * - **ไม่ต้องรออนุมัติ** — ขึ้นบอร์ดสาธารณะทันที (สภาซ่อนย้อนหลังได้ถ้าไม่เหมาะสม)
 * - **ไม่แจ้งเตือนใคร** โดยเจตนา (กัน push storm — ข้อเสนอใครก็กดได้)
 *
 * v-model:open ควบคุมเปิด/ปิด; @created → คืน board_id ที่สร้าง (parent นำไป navigate)
 */
const open = defineModel<boolean>('open', { default: false })
const emit = defineEmits<{ created: [boardId: number] }>()

const title = ref('')
const description = ref('')
const isAnonymous = ref(false)
const submitting = ref(false)

// เปิด modal → รีเซ็ตฟอร์มทุกครั้ง (ไม่ค้างค่าจากครั้งก่อน)
watch(open, (isOpen) => {
  if (isOpen) {
    title.value = ''
    description.value = ''
    isAnonymous.value = false
    submitting.value = false
  }
})

async function handleSubmit() {
  // ตรวจฝั่ง client ให้ตรงกับด่านฝั่ง backend (strip แล้วต้องเหลือหัวข้อ ≥ 3 ตัวอักษร)
  const t = title.value.trim()
  const d = description.value.trim()
  if (t.length < 3) {
    Swal.fire({ icon: 'warning', title: 'หัวข้อสั้นไป', text: 'หัวข้อต้องมีอย่างน้อย 3 ตัวอักษร' })
    return
  }
  if (!d) {
    Swal.fire({ icon: 'warning', title: 'ยังไม่ได้ใส่รายละเอียด', text: 'อธิบายข้อเสนอสักเล็กน้อยให้คนอื่นเข้าใจ' })
    return
  }

  submitting.value = true
  try {
    const res = await createSuggestion({ title: t, description: d, is_anonymous: isAnonymous.value })
    Swal.fire({
      icon: 'success',
      title: 'เผยแพร่แล้ว!',
      text: 'ข้อเสนอของคุณขึ้นบอร์ดสาธารณะแล้ว',
      timer: 1500,
      showConfirmButton: false,
    })
    open.value = false
    emit('created', res.id)
  } catch (e) {
    Swal.fire({ icon: 'error', title: 'ส่งไม่สำเร็จ', text: e instanceof Error ? e.message : String(e) })
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <!-- ⚠️ ต้อง Teleport ออกไปที่ <body> — modal นี้เรนเดอร์อยู่ภายใน stacking context
         ของ `.maincol` (`relative z-10` ใน MainLayout) ⇒ z-50 ข้างในถูกกักไว้ที่ชั้น 10
         และแพ้ bottom tab bar (`fixed z-40`) ที่เป็นพี่น้องกัน ⇒ แถบเมนูล่างทับและกลืนคลิก
         ปุ่มส่ง. Teleport ทำให้ modal ไปแข่ง z-index ที่ระดับ root แทน
         (กับดักเดียวกับที่เจอใน AcademicTerms/AnnouncementManagement/UserManagement) -->
  <Teleport to="body">
    <Transition name="modal">
      <div v-if="open" class="fixed inset-0 z-50 flex items-center justify-center p-4" @click.self="open = false">
        <div class="absolute inset-0 bg-stone-900/50"></div>

        <div class="relative w-full max-w-lg bg-white rounded-2xl border border-stone-200 p-5 sm:p-6 max-h-[90vh] overflow-y-auto">
          <div class="flex items-start justify-between gap-3 mb-4">
            <div>
              <p class="text-[11px] font-bold uppercase tracking-widest text-brand mb-1">
                <i class="bi bi-lightbulb-fill mr-1"></i> Quick Suggestion
              </p>
              <h2 class="text-xl font-bold text-stone-900 leading-tight">เสนอไอเดีย</h2>
              <p class="text-sm text-stone-500 mt-1">
                ขึ้นบอร์ดสาธารณะทันที — สภานักเรียนดูได้และซ่อนย้อนหลังได้ถ้าไม่เหมาะสม
              </p>
            </div>
            <button
              type="button"
              data-testid="suggestion-close"
              class="w-8 h-8 flex items-center justify-center rounded-lg text-stone-400 hover:bg-stone-100 hover:text-stone-600"
              @click="open = false"
            >
              <i class="bi bi-x-lg"></i>
            </button>
          </div>

          <div class="mb-4">
            <label class="block text-sm font-medium text-stone-700 mb-1.5" for="suggestion-title">
              หัวข้อ <span class="text-stone-400 font-normal">(อย่างน้อย 3 ตัวอักษร)</span>
            </label>
            <input
              id="suggestion-title"
              v-model="title"
              type="text"
              data-testid="suggestion-title"
              placeholder="เช่น อยากให้มีน้ำดื่มฟรีที่โรงอาหาร"
              maxlength="200"
              class="w-full px-3 py-2.5 border border-stone-300 rounded-xl text-sm bg-white focus:ring-2 focus:ring-brand"
            />
            <p class="text-xs text-stone-400 mt-1 text-right tabular-nums">{{ title.length }}/200</p>
          </div>

          <div class="mb-4">
            <label class="block text-sm font-medium text-stone-700 mb-1.5" for="suggestion-description">
              รายละเอียด
            </label>
            <textarea
              id="suggestion-description"
              v-model="description"
              data-testid="suggestion-description"
              rows="5"
              maxlength="2000"
              placeholder="อธิบายเหตุผลหรือประโยชน์ที่คิดว่าจะได้..."
              class="w-full px-3 py-2.5 border border-stone-300 rounded-xl text-sm bg-white focus:ring-2 focus:ring-brand resize-y"
            ></textarea>
            <p class="text-xs text-stone-400 mt-1 text-right tabular-nums">{{ description.length }}/2000</p>
          </div>

          <label class="flex items-start gap-2 text-sm text-stone-700 cursor-pointer select-none mb-2">
            <input
              v-model="isAnonymous"
              type="checkbox"
              data-testid="suggestion-anonymous"
              class="mt-0.5 w-4 h-4 rounded bg-white border-stone-300 text-brand focus:ring-brand accent-brand"
            />
            <span>
              ไม่แสดงชื่อผู้เสนอ
              <span class="block text-xs text-stone-400">สภานักเรียนยังเห็นว่าใครเสนอ (เพื่อความรับผิดชอบ) แต่คนอื่นไม่เห็น</span>
            </span>
          </label>

          <div class="flex gap-2 pt-2">
            <button
              type="button"
              @click="open = false"
              class="flex-1 py-2.5 rounded-xl bg-stone-100 text-stone-700 hover:bg-stone-200 text-sm font-medium"
            >
              ยกเลิก
            </button>
            <button
              type="button"
              :disabled="submitting"
              data-testid="suggestion-submit"
              @click="handleSubmit"
              class="flex-1 py-2.5 rounded-xl bg-brand text-white hover:bg-brand-strong disabled:opacity-50 text-sm font-medium"
            >
              {{ submitting ? 'กำลังส่ง...' : 'เผยแพร่ข้อเสนอ' }}
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
