<script setup lang="ts">
/**
 * 💡 เสนอไอเดีย / ข้อเสนอแนะ (E1) — **หน้าเต็ม ไม่ใช่ modal**
 *
 * 🔴 **ทำไมต้องเป็นหน้าเต็ม** — ของเดิมเป็น `QuickSuggestionModal` ซึ่งมีฉากหลังที่
 *    `@click.self` ปิดได้ ⇒ **นิ้วพลาดครั้งเดียว = ข้อความที่พิมพ์ไว้หายทั้งก้อน**
 *    โดยไม่มีคำถามยืนยัน (skills #16 — อาการที่ผู้ใช้รายงานตรง ๆ ว่าโดนมา ~10 รอบ)
 *    · ฟอร์มที่ผู้ใช้ต้อง *พิมพ์* ต้องเป็นหน้าเต็มเสมอ ส่วน modal สงวนไว้ให้งานที่
 *      "ปิดแล้วเสียเปล่าน้อย" (ยืนยัน · เลือกจากรายการ)
 *    ⚠️ การเปลี่ยนเป็นหน้าเต็มทำให้ `AppFab` (ซึ่งเรนเดอร์เป็น `RouterLink` เท่านั้น)
 *       ชี้มาที่นี่ได้ ⇒ นี่คือเหตุผลที่ FAB ของแท็บบอร์ดเกิดขึ้นได้ในรอบนี้
 *
 * 🗂️ ต่างจาก `ApproveBoardModal` (ของสภา) อย่างตั้งใจ:
 *    - **ไม่มีตัวเลือกโหวต** และไม่มีตัวเลือกประเภทบอร์ด — สร้างได้ชนิดเดียว (`suggestion`)
 *      ⇒ backend ไม่รับ `board_type` จาก client เลย (กันช่องเลี่ยงด่านอนุมัติของสภา)
 *      (ยืนยันด้วยเทสต์: `services/__tests__/board.spec.ts` — "ส่งแค่ 3 ฟิลด์ที่อนุญาต")
 *    - **ไม่ต้องรออนุมัติ** — ขึ้นบอร์ดสาธารณะทันที (สภาซ่อนย้อนหลังได้ถ้าไม่เหมาะสม)
 *    - **ไม่แจ้งเตือนใคร** โดยเจตนา (กัน push storm — ข้อเสนอใครก็กดได้)
 *
 * 🔴 **ไม่มี `<h1>`** — `<h1>` ของหน้าอยู่ที่ `AppHeader` (R0.3) และ `routeTitles`
 *    ชี้ `board-new` มาที่ "เสนอไอเดีย" แล้ว ⇒ การใส่ `<h1>` ซ้ำจะได้ชื่อเรื่องสองที่
 */
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { onBeforeRouteLeave, useRouter } from 'vue-router'
import Swal from 'sweetalert2'
import { createSuggestion } from '@/services/board'
import { useAuthStore } from '@/stores/auth'
import { BRAND } from '@/constants/brand'
import AppButton from '@/components/ui/AppButton.vue'
import AppCard from '@/components/ui/AppCard.vue'

const router = useRouter()
const authStore = useAuthStore()

interface SuggestionForm {
  title: string
  description: string
  isAnonymous: boolean
}

const EMPTY_FORM: SuggestionForm = { title: '', description: '', isAnonymous: false }

const form = ref<SuggestionForm>({ ...EMPTY_FORM })
const submitting = ref(false)
/** ช่องที่ผู้ใช้แตะแล้ว — โชว์ error เฉพาะช่องที่ "เคยแตะ" ไม่ใช่ตอนเปิดหน้ามาเจอแดงเต็มไปหมด */
const touched = ref<Record<string, boolean>>({})

/**
 * 🔴 ตั้ง **ก่อน** `router.push` เสมอ — ปลด guard ทุกชั้น
 *    ถ้าตั้ง *หลัง* push guard จะทำงานก่อนแล้วผู้ใช้จะเห็น "ยังไม่ได้ส่ง" **หลังส่งสำเร็จ**
 *    ซึ่งอ่านว่า "ส่งไม่ติด" ⇒ กดซ้ำ (skills: entry `savedOk`)
 */
const savedOk = ref(false)

const titleError = computed(() => {
  const t = form.value.title.trim()
  if (!t) return 'ใส่หัวข้อสักหน่อย เพื่อให้คนอื่นรู้ว่าเรื่องนี้คืออะไร'
  // ตรงกับด่านฝั่ง backend (strip แล้วต้องเหลือ ≥ 3 ตัวอักษร)
  if (t.length < 3) return 'หัวข้อต้องมีอย่างน้อย 3 ตัวอักษร'
  return ''
})

const descError = computed(() =>
  form.value.description.trim() ? '' : 'อธิบายเหตุผลหรือประโยชน์ที่คิดว่าจะได้สักเล็กน้อย',
)

const canSubmit = computed(() => !titleError.value && !descError.value && !submitting.value)

function markTouched(field: string) {
  touched.value = { ...touched.value, [field]: true }
}

async function handleSubmit() {
  // ⚠️ ใช้ inline error ไม่ใช่ Swal — เปิดหน้าเดียวเด้ง 2 กล่องเรียงกันคือสิ่งที่ R3.1 แก้ไปแล้ว
  if (!canSubmit.value) {
    touched.value = { title: true, description: true }
    return
  }

  submitting.value = true
  try {
    const res = await createSuggestion({
      title: form.value.title.trim(),
      description: form.value.description.trim(),
      is_anonymous: form.value.isAnonymous,
    })
    // 🔴 `savedOk` ต้องมาก่อน push — ดูคอมเมนต์ตอนประกาศตัวแปร
    savedOk.value = true
    clearDraft()
    // 🎯 ปลายทาง *คือ* การยืนยัน — ผู้ใช้เห็นข้อเสนอของตัวเองอยู่บนบอร์ดแล้ว
    //    ⇒ ไม่ต้องมี Swal "เผยแพร่แล้ว!" ที่ต้องรอ 1.5 วิก่อนไปไหนได้
    await router.push({ name: 'board-detail', params: { id: res.id } })
  } catch (e) {
    // ⚠️ error จากเซิร์ฟเวอร์ยังใช้ Swal ได้ — เป็นเรื่องที่ผู้ใช้คุมไม่ได้ และไม่ควรหายไปเงียบ ๆ
    Swal.fire({
      icon: 'error',
      title: 'ส่งไม่สำเร็จ',
      text: e instanceof Error ? e.message : String(e),
      confirmButtonColor: BRAND,
    })
  } finally {
    submitting.value = false
  }
}

// ── กันข้อมูลหาย ชั้นที่ 3: ร่างอัตโนมัติใน sessionStorage ─────────────────────

const DRAFT_KEY = 'piri_suggestion_draft'
/** ⚠️ เปลี่ยนเมื่อแก้รูปร่างของ `StoredDraft` เท่านั้น — ร่างเวอร์ชันเก่าจะถูกทิ้ง ไม่ใช่ตีความผิด */
const DRAFT_VERSION = 1

interface StoredDraft {
  v: number
  /** epoch ms — ใช้แสดง "บันทึกร่างแล้ว HH:MM" */
  savedAt: number
  form: SuggestionForm
}

const draftSavedAt = ref(0)

/** ตรวจรูปร่างก่อนใช้ — `sessionStorage` ถูกเขียนโดยโค้ดเวอร์ชันอื่นได้ (เปิดสองแท็บข้าม deploy) */
function isFormValues(x: unknown): x is SuggestionForm {
  if (typeof x !== 'object' || x === null) return false
  const o = x as Record<string, unknown>
  return (
    typeof o.title === 'string' &&
    typeof o.description === 'string' &&
    typeof o.isAnonymous === 'boolean'
  )
}

/**
 * ⚠️ **`try/catch` ทุก read/write** — โหมดส่วนตัวของบางเบราว์เซอร์ "มี" `sessionStorage`
 *    แต่ **โยน error ตอนเขียน** ⇒ ถ้าไม่ดัก ผู้ใช้จะพังตั้งแต่ตัวอักษรแรกที่พิมพ์
 *    ซึ่งดูเหมือน "พิมพ์แล้วหน้าค้าง" ไม่ใช่ "ที่เก็บข้อมูลถูกปิด"
 */
function readDraft(): StoredDraft | null {
  try {
    const raw = sessionStorage.getItem(DRAFT_KEY)
    if (!raw) return null
    const d = JSON.parse(raw) as Partial<StoredDraft> | null
    if (!d || d.v !== DRAFT_VERSION || !isFormValues(d.form)) return null
    return { v: DRAFT_VERSION, savedAt: typeof d.savedAt === 'number' ? d.savedAt : 0, form: d.form }
  } catch {
    return null
  }
}

function writeDraft() {
  try {
    const d: StoredDraft = { v: DRAFT_VERSION, savedAt: Date.now(), form: { ...form.value } }
    sessionStorage.setItem(DRAFT_KEY, JSON.stringify(d))
    draftSavedAt.value = d.savedAt
  } catch {
    /* เก็บไม่ได้ก็แค่ไม่มีร่าง — ต้องไม่ทำให้การพิมพ์พัง */
  }
}

function clearDraft() {
  try {
    sessionStorage.removeItem(DRAFT_KEY)
    draftSavedAt.value = 0
  } catch {
    /* ไม่เป็นไร */
  }
}

const dirty = computed(() => JSON.stringify(form.value) !== JSON.stringify(EMPTY_FORM))

/**
 * บันทึกร่างทุกครั้งที่ฟอร์มเปลี่ยน — **เงียบ ไม่มี Swal**
 * ⚠️ ลบร่างทันทีเมื่อค่ากลับมาเท่าตั้งต้น — ไม่งั้น "พิมพ์แล้วลบออก" จะทิ้งร่างค้างไว้
 *    แล้วรอบหน้าผู้ใช้จะถูกถามกู้คืนทั้งที่ไม่มีอะไรจะกู้
 */
watch(
  form,
  () => {
    if (savedOk.value) return
    if (!dirty.value) {
      clearDraft()
      return
    }
    writeDraft()
  },
  { deep: true },
)

async function offerDraftRestore() {
  const d = readDraft()
  if (!d || !isFormValues(d.form)) return
  if (JSON.stringify(d.form) === JSON.stringify(EMPTY_FORM)) {
    clearDraft()
    return
  }
  const res = await Swal.fire({
    icon: 'question',
    title: 'กู้คืนข้อเสนอที่ยังไม่ได้ส่ง?',
    text: 'พบข้อความที่พิมพ์ค้างไว้จากรอบก่อน — ต้องการนำกลับมาใส่ฟอร์มหรือไม่',
    showCancelButton: true,
    confirmButtonText: 'กู้คืน',
    cancelButtonText: 'ไม่ต้อง',
    confirmButtonColor: BRAND,
  })
  if (res.isConfirmed) {
    form.value = d.form
  } else {
    clearDraft()
  }
}

onMounted(offerDraftRestore)

// ── กันข้อมูลหาย ชั้นที่ 1: ออกจากหน้า (guard ของ router) ─────────────────────

/**
 * 🔴 **ต้องเรียกที่ top level ของ `<script setup>` แบบ sync** — ถ้าไปเรียกใน `onMounted`
 *    หลัง `await` ตัว guard จะ **ไม่ถูกผูกเลย** (มีแค่ warning ใน dev ที่คนมักไม่เห็น)
 */
onBeforeRouteLeave(async (to) => {
  if (savedOk.value) return true
  // กำลังส่งอยู่ — อย่าให้ออกกลางคันแล้วต้องมาเดาว่าส่งติดไหม
  if (submitting.value) return false
  // ⚠️ ออกจากระบบ/หมดอายุ ต้องผ่านได้เสมอ ไม่งั้นผู้ใช้จะติดกับอยู่ในฟอร์ม แล้วเจอ Swal ซ้อน
  if (to.name === 'login' || !authStore.isAuthenticated) return true
  if (!dirty.value) return true

  const res = await Swal.fire({
    icon: 'warning',
    title: 'ยังไม่ได้เผยแพร่',
    text: 'ข้อความที่พิมพ์ไว้จะหายไปหากออกจากหน้านี้',
    showCancelButton: true,
    confirmButtonText: 'ออกจากหน้านี้',
    cancelButtonText: 'อยู่ต่อ',
    confirmButtonColor: BRAND,
    // ⚠️ ไม่ใส่ `reverseButtons` — ปุ่มยืนยันคือ "ทิ้งข้อมูล" ต้องไม่ถูกวางที่ตำแหน่งที่นิ้วกดเล่น
  })
  if (res.isConfirmed) {
    clearDraft()
    return true
  }
  return false
})

// ── กันข้อมูลหาย ชั้นที่ 2: ปิดแท็บ/refresh (หลุด router ทั้งหมด) ─────────────

function onBeforeUnload(e: BeforeUnloadEvent) {
  if (savedOk.value || !dirty.value) return
  // เบราว์เซอร์ใหม่ใช้ `preventDefault()` + `returnValue` — ต้องตั้งทั้งคู่ ไม่ใช่เพราะซ้ำซ้อน
  e.preventDefault()
  e.returnValue = ''
}

onMounted(() => window.addEventListener('beforeunload', onBeforeUnload))
onBeforeUnmount(() => window.removeEventListener('beforeunload', onBeforeUnload))
</script>

<template>
  <div class="mx-auto max-w-2xl space-y-4 pb-4">
    <p class="text-sm text-ink-2">
      ข้อเสนอของคุณขึ้นบอร์ดสาธารณะทันที · สภานักเรียนดูได้ และซ่อนย้อนหลังได้ถ้าไม่เหมาะสม
    </p>

    <AppCard>
      <!-- หัวข้อ -->
      <div class="mb-5">
        <label for="suggestion-title" class="mb-1.5 block text-sm font-semibold text-ink-1">
          หัวข้อ <span class="font-normal text-ink-3">(อย่างน้อย 3 ตัวอักษร)</span>
        </label>
        <input
          id="suggestion-title"
          v-model="form.title"
          type="text"
          data-testid="suggestion-title"
          placeholder="เช่น อยากให้มีน้ำดื่มฟรีที่โรงอาหาร"
          maxlength="200"
          class="field"
          :class="touched.title && titleError && 'border-danger focus:ring-danger/20'"
          :aria-invalid="touched.title && !!titleError"
          aria-describedby="suggestion-title-help"
          @blur="markTouched('title')"
        />
        <div class="mt-1 flex items-start justify-between gap-3">
          <!-- ⚠️ จองที่ไว้เสมอ (`min-h`) ⇒ ข้อความ error โผล่มาแล้วเลย์เอาต์ไม่กระโดด -->
          <p
            v-if="touched.title && titleError"
            class="min-h-[1.125rem] text-xs text-danger"
            role="alert"
          >
            {{ titleError }}
          </p>
          <span v-else id="suggestion-title-help" class="min-h-[1.125rem]"></span>
          <span class="shrink-0 text-xs text-ink-3 tabular-nums">{{ form.title.length }}/200</span>
        </div>
      </div>

      <!-- รายละเอียด -->
      <div class="mb-5">
        <label for="suggestion-description" class="mb-1.5 block text-sm font-semibold text-ink-1">
          รายละเอียด
        </label>
        <textarea
          id="suggestion-description"
          v-model="form.description"
          data-testid="suggestion-description"
          rows="6"
          maxlength="2000"
          placeholder="อธิบายเหตุผลหรือประโยชน์ที่คิดว่าจะได้..."
          class="field resize-y"
          :class="touched.description && descError && 'border-danger focus:ring-danger/20'"
          :aria-invalid="touched.description && !!descError"
          @blur="markTouched('description')"
        ></textarea>
        <div class="mt-1 flex items-start justify-between gap-3">
          <p
            v-if="touched.description && descError"
            class="min-h-[1.125rem] text-xs text-danger"
            role="alert"
          >
            {{ descError }}
          </p>
          <span v-else class="min-h-[1.125rem]"></span>
          <span class="shrink-0 text-xs text-ink-3 tabular-nums">
            {{ form.description.length }}/2000
          </span>
        </div>
      </div>

      <!-- ไม่ระบุตัวตน -->
      <label
        class="flex cursor-pointer items-start gap-3 rounded-control bg-canvas p-3 select-none"
      >
        <input
          v-model="form.isAnonymous"
          type="checkbox"
          data-testid="suggestion-anonymous"
          class="mt-0.5 h-4 w-4 shrink-0 rounded border-line accent-brand"
        />
        <span class="text-sm text-ink-1">
          ไม่แสดงชื่อผู้เสนอ
          <!-- ⚠️ ห้ามสัญญาเกินจริง — ครอบคลุมแค่ "ชื่อที่แสดงบนบอร์ด" ไม่ใช่ความลับ -->
          <span class="mt-1 block text-xs leading-relaxed text-ink-2">
            คนอื่นจะไม่เห็นชื่อคุณบนบอร์ดนี้ · สภานักเรียนยังเห็นว่าใครเสนอ เพื่อความรับผิดชอบ
          </span>
        </span>
      </label>
    </AppCard>

    <!-- สถานะร่าง — เงียบ ๆ บรรทัดเดียว -->
    <p v-if="draftSavedAt && dirty" class="text-center text-xs text-ink-3">
      <i class="bi bi-cloud-check mr-1" aria-hidden="true" />
      บันทึกร่างไว้แล้วในเครื่องนี้ — กลับมาใหม่ยังกู้คืนได้
    </p>

    <!-- 🎯 งานหลักของหน้า — ปุ่มเดียว อยู่ล่างสุด (โซนนิ้วโป้ง) -->
    <AppButton
      block
      size="lg"
      :loading="submitting"
      :disabled="!canSubmit"
      data-testid="suggestion-submit"
      @click="handleSubmit"
    >
      <template #icon><i class="bi bi-send" aria-hidden="true" /></template>
      เผยแพร่ข้อเสนอ
    </AppButton>
  </div>
</template>
