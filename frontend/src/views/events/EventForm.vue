<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'
import Swal from 'sweetalert2'
import { BRAND } from '@/constants/brand'
// ⚠️ v14 ส่งออกเป็น **named export** — `import VueDatePicker from …` (default) จะได้
//    TS2613 "has no default export" ⇒ อย่าเปลี่ยนกลับเป็น default ตามเอกสารเวอร์ชันเก่า
import { VueDatePicker } from '@vuepic/vue-datepicker'
// ⚠️ **CSS ของ picker ต้อง import** — ลืมแล้วอาการคือ "กดเปิดปฏิทินแล้วไม่มีอะไรขึ้น"
//    ซึ่งหน้าตาเหมือนบั๊ก backdrop ของ modal เดิมเป๊ะ ⇒ จะไล่หาสาเหตุผิดที่ไปเป็นชั่วโมง
import '@vuepic/vue-datepicker/dist/main.css'
import { th } from 'date-fns/locale'
import { useAuthStore } from '@/stores/auth'
import { createEvent, getEvent, updateEvent } from '@/services/event'
import { dateToInput, formatThaiDateTimeInput, inputToDate } from '@/datetime'
import {
  EMPTY_EVENT_FORM,
  buildCreate,
  buildPatch,
  categoryOptionsOf,
  formErrorOf,
  isDirty,
  toBaseline,
  toFormValues,
  type EventFormValues,
} from '@/eventForm'
import { STATUS_ICONS, STATUS_LABELS, type Event } from '@/types/event'
import type { ApiError } from '@/services/api'

/**
 * ✍️ สร้าง/แก้ไขกิจกรรม — **หน้าเต็มหน้า ไม่ใช่ modal** (รอบ 4)
 *
 * 🐛 **ทำไมต้องย้าย** — เดิมเป็น modal ที่มีฉากหลังกดปิดได้
 *    (`<div class="absolute inset-0 …" @click="closeModal">`) ⇒ **คลิกพลาดครั้งเดียว
 *    ข้อความที่พิมพ์ไว้หายทั้งหมด โดยไม่มีคำถามยืนยัน** ซึ่งผู้ใช้รายงานว่าโดนมา ~10 รอบ
 *    ⇒ หน้านี้จึงมี "ตาข่ายกันข้อมูลหาย" 3 ชั้น (ดูบล็อกท้ายไฟล์) และ **การนำทางออก
 *    ทุกเส้นทางต้องผ่านคำถาม** — ตรรกะการเทียบว่าอะไรคือ "ยังไม่บันทึก" อยู่ใน
 *    `@/eventForm` (มีเทสต์) ไม่ได้อยู่ในเทมเพลต
 *
 * ⭐ **คอมโพเนนต์เดียวรับ 2 route** (`events/new` · `events/:id/edit`) — 8 ฟิลด์เหมือนกันเป๊ะ
 *    และ `buildCreate`/`buildPatch` ถูกออกแบบให้ใช้ร่วมกันโดยเจตนา ⇒ ถ้าแยกเป็นสองไฟล์
 *    วันหนึ่งจะมีคนแก้ `buildCreate` ที่เดียว ⇒ นิยาม "ยังไม่บันทึก" ของสองหน้าเพี้ยนจากกัน
 *    ⇒ ผู้ใช้หน้าใดหน้าหนึ่งจะเจอกล่องถามทั้งที่ไม่มีอะไรจะเสีย (หรือแย่กว่า: ไม่ถามทั้งที่จะเสีย)
 *
 * ⚠️ **หน้าแก้ไขต้อง refresh ได้จริง** ⇒ เรียก `getEvent(id)` เอง ไม่พึ่ง state ที่ส่งข้ามหน้า
 *    (`GET /api/events/{id}` ถูกเพิ่มในรอบนี้เพื่อเหตุผลนี้ — `/public/{id}` เห็นแค่ที่เผยแพร่แล้ว)
 */
const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const isEdit = computed(() => route.name === 'event-edit')

/** id จาก URL — `null` เมื่อ path พาเลขที่ใช้ไม่ได้มา (เช่น `/events/abc/edit` เข้าไม่ถึงแต่กันไว้) */
const eventId = computed<number | null>(() => {
  const n = Number(route.params.id)
  return Number.isInteger(n) && n > 0 ? n : null
})

const isLoading = ref(true)
const loadError = ref(false)
/** แยกจาก `loadError` โดยเจตนา — "ไม่มีกิจกรรมนี้" ต้องไม่ชวนให้กด "ลองใหม่" (กดแล้วก็ 404 อีก) */
const notFound = ref(false)
const saving = ref(false)
const saveError = ref('')
const event = ref<Event | null>(null)

const form = ref<EventFormValues>({ ...EMPTY_EVENT_FORM })
/**
 * ค่าตั้งต้นที่ normalize แล้ว — ใช้เป็นฐานเทียบ "ผู้ใช้แก้อะไร"
 *
 * ⚠️ **ไม่ใช่ `null`** (ต่างจากเวอร์ชัน modal) — โหมดสร้างก็มีฐาน คือ `buildCreate(EMPTY_EVENT_FORM)`
 *    ⇒ "สกปรก" กับ "สิ่งที่ `save()` ส่ง" คิดจากตัวเลขตัวเดียวกัน ไม่ต้องมีสาขา `if (mode === 'add')`
 *    อยู่ในตรรกะกันข้อมูลหาย
 */
const baseline = ref(buildCreate(EMPTY_EVENT_FORM))

/** กิจกรรมที่ถูกลบ (soft delete) — ดูได้แต่แก้ไม่ได้ เพราะ `PATCH` มี `deleted_at IS NULL` */
const isDeleted = computed(() => event.value?.deleted_at != null)

/**
 * 🔴 `savedOk` — **ต้องตั้งเป็น `true` ก่อน `router.push` เสมอ**
 *
 * ถ้าลืม: guard `onBeforeRouteLeave` จะยิงใส่ **การนำทางของตัวมันเอง** ⇒ ผู้ใช้เห็นกล่อง
 * "ยังไม่บันทึก ทิ้งไหม" **หลังกดบันทึกสำเร็จ** ซึ่งอ่านได้ความว่า "บันทึกไม่ติด"
 * ⇒ ผู้ใช้กดบันทึกซ้ำ/ไม่กล้าออกจากหน้า (เป็นคลาสเดียวกับบั๊กที่ทำให้รอบนี้ต้องย้ายเป็นหน้าเต็ม)
 */
const savedOk = ref(false)

const dirty = computed(() => isDirty(baseline.value, form.value))
const formError = computed(() => formErrorOf(form.value))
const categoryOptions = computed(() => categoryOptionsOf(form.value.category))

// ── วันที่ ────────────────────────────────────────────────────────────────────
//
// ⭐ ฟอร์มเก็บเป็น **สตริง `YYYY-MM-DDTHH:MM`** ตลอด ไม่เก็บ `Date`
//    ⇒ autosave ลง sessionStorage ได้ตรง ๆ และ round-trip ไม่เพี้ยน
// ⭐ picker แปลงด้วย `inputToDate`/`dateToInput` ซึ่งเป็น **local ↔ local คู่กัน**
//    🚫 ห้ามตั้ง `timezone` prop ของ picker — จะกลายเป็นสองระบบโซนปนกัน (บั๊กเงียบ ไม่มี error)
const eventDateModel = computed<Date | null>({
  get: () => inputToDate(form.value.event_date),
  set: (d) => {
    form.value.event_date = d ? dateToInput(d) : ''
  },
})

const deadlineModel = computed<Date | null>({
  get: () => inputToDate(form.value.registration_deadline),
  set: (d) => {
    form.value.registration_deadline = d ? dateToInput(d) : ''
  },
})

/**
 * props ที่ใช้ร่วมกันของ picker ทั้งสองช่อง — **ที่เดียว**
 *
 * ⚠️ เขียนซ้ำสองที่จะเพี้ยนจากกันวันหนึ่ง (เช่นแก้ `format` ช่องเดียว) แล้วผู้ใช้จะเห็น
 *    วันที่คนละหน้าตาในฟอร์มเดียว ซึ่งดูไม่ออกว่าอันไหนถูก
 */
const pickerProps = {
  locale: th,
  format: 'dd/MM/yyyy HH:mm',
  is24: true,
  autoApply: true,
  enableTimePicker: true,
  /** ปิด validation ของไลบรารี — เราใช้ `formErrorOf` เป็นผู้ตัดสินเดียว ไม่ให้มีสองเสียง */
  state: false,
  /** ปฏิทินลอยอยู่เหนือการ์ด (default teleport ไป body) ⇒ ไม่ถูก `overflow` ของการ์ดตัด */
  teleport: true,
}

// ── การโหลด ──────────────────────────────────────────────────────────────────

async function load() {
  isLoading.value = true
  loadError.value = false
  notFound.value = false

  if (!isEdit.value) {
    // โหมดสร้าง — ไม่มีอะไรให้โหลด แต่ยังต้องมี baseline (ดูคอมเมนต์ของ `baseline`)
    event.value = null
    form.value = { ...EMPTY_EVENT_FORM }
    baseline.value = buildCreate(EMPTY_EVENT_FORM)
    isLoading.value = false
    await offerDraftRestore()
    return
  }

  try {
    const id = eventId.value
    if (id === null) {
      notFound.value = true
      return
    }
    const row = await getEvent(id)
    event.value = row
    form.value = toFormValues(row)
    baseline.value = toBaseline(row)
  } catch (e) {
    // ⚠️ 404 → "ไม่มีกิจกรรมนี้" (ไม่มีปุ่มลองใหม่) · อย่างอื่น → error ทั่วไป (มีปุ่มลองใหม่)
    //    ⚠️ endpoint นี้ **ไม่คืน 404 สำหรับใบที่ถูกลบ** — นั่นมาถึงเป็น 200 + `deleted_at`
    //       แล้วถูกจับด้วยการ์ด `isDeleted` ⇒ อย่าเอา 404 มาแทนความหมายนั้น
    if ((e as ApiError)?.status === 404) notFound.value = true
    else loadError.value = true
  } finally {
    isLoading.value = false
  }

  if (!notFound.value && !loadError.value) await offerDraftRestore()
}

onMounted(load)

// ── กันข้อมูลหาย ชั้นที่ 3: ร่างอัตโนมัติใน sessionStorage ─────────────────────

const DRAFT_KEY = 'piri_event_form_draft'
/** ⚠️ เปลี่ยนเมื่อแก้รูปร่างของ `StoredDraft` เท่านั้น — ร่างเวอร์ชันเก่าจะถูกทิ้ง ไม่ใช่ตีความผิด */
const DRAFT_VERSION = 1

interface StoredDraft {
  v: number
  /** ⚠️ **ต้องมี** — ไม่งั้นร่างของ "สร้างใหม่" จะไปโผล่ใน "แก้ไข #42" แล้วผู้ใช้กดกู้คืน */
  mode: 'add' | 'edit'
  eventId: number | null
  /** epoch ms — ใช้แค่แสดงผล/ดีบั๊ก ไม่ได้ใช้ตัดสินอะไร */
  savedAt: number
  form: EventFormValues
}

/** ตรวจรูปร่างก่อนใช้ — sessionStorage ถูกเขียนโดยโค้ดเวอร์ชันอื่นได้ (ผู้ใช้เปิดสองแท็บข้าม deploy) */
function isFormValues(x: unknown): x is EventFormValues {
  if (typeof x !== 'object' || x === null) return false
  const o = x as Record<string, unknown>
  return (Object.keys(EMPTY_EVENT_FORM) as (keyof EventFormValues)[]).every(
    (k) => typeof o[k] === 'string',
  )
}

/**
 * ⚠️ **`try/catch` ทุก read/write** — โหมดส่วนตัวของบางเบราว์เซอร์ "มี" `sessionStorage`
 *    แต่ **โยน error ตอนเขียน** (quota/ปิด storage) ⇒ ถ้าไม่ดัก ผู้ใช้จะพังตั้งแต่ตัวอักษรแรก
 *    ที่พิมพ์ ซึ่งดูเหมือน "พิมพ์แล้วหน้าค้าง" ไม่ใช่ "ที่เก็บข้อมูลถูกปิด" (แนวเดียวกับ `pwa.ts`)
 */
function readDraft(): StoredDraft | null {
  try {
    const raw = sessionStorage.getItem(DRAFT_KEY)
    if (!raw) return null
    const d = JSON.parse(raw) as Partial<StoredDraft> | null
    if (!d || d.v !== DRAFT_VERSION) return null
    if (d.mode !== 'add' && d.mode !== 'edit') return null
    if (!isFormValues(d.form)) return null
    return {
      v: DRAFT_VERSION,
      mode: d.mode,
      eventId: typeof d.eventId === 'number' ? d.eventId : null,
      savedAt: typeof d.savedAt === 'number' ? d.savedAt : 0,
      form: d.form,
    }
  } catch {
    return null
  }
}

function writeDraft(values: EventFormValues) {
  try {
    const d: StoredDraft = {
      v: DRAFT_VERSION,
      mode: isEdit.value ? 'edit' : 'add',
      eventId: eventId.value,
      savedAt: Date.now(),
      form: { ...values },
    }
    sessionStorage.setItem(DRAFT_KEY, JSON.stringify(d))
  } catch {
    /* เก็บไม่ได้ก็แค่ไม่มีร่าง — ต้องไม่ทำให้การพิมพ์พัง */
  }
}

function clearDraft() {
  try {
    sessionStorage.removeItem(DRAFT_KEY)
  } catch {
    /* ไม่เป็นไร */
  }
}

/**
 * ร่างนี้เป็นของหน้าปัจจุบันจริงไหม — เทียบ **ทั้ง `mode` และ `eventId`**
 * ⚠️ โหมดสร้างไม่ต้องเทียบ `eventId` (ไม่มี) แต่โหมดแก้ต้องเทียบ — ไม่งั้นร่างของ #42
 *    ไปโผล่ตอนเปิด #99 ซึ่งผู้ใช้อาจกดกู้คืนแล้วบันทึกข้อมูลผิดใบ
 */
function draftBelongsToThisPage(d: StoredDraft): boolean {
  if (d.mode !== (isEdit.value ? 'edit' : 'add')) return false
  return isEdit.value ? d.eventId === eventId.value : true
}

/**
 * ⚠️ เรียก **หลัง** โหลดข้อมูลจริงเสร็จแล้วเท่านั้น — และ **ห้ามแตะ `baseline`**
 *
 * 🔴 ถ้าตั้ง `baseline` จากร่างที่กู้คืน "กู้คืนแล้วกดบันทึก" จะได้ patch ว่าง ⇒ **ไม่ยิง API เลย**
 *    แต่ผู้ใช้เชื่อว่าบันทึกแล้ว (แย่กว่าไม่กู้คืนเลย เพราะความเชื่อผิด ๆ ว่าเสร็จแล้ว)
 *    ⇒ `baseline` มาจากเซิร์ฟเวอร์ (โหมดแก้) หรือ `EMPTY` (โหมดสร้าง) เท่านั้น
 */
async function offerDraftRestore() {
  const d = readDraft()
  if (!d || !draftBelongsToThisPage(d)) return
  // ร่างที่เท่ากับค่าตั้งต้นอยู่แล้ว = ไม่มีอะไรให้กู้ — ลบทิ้งเงียบ ๆ ไม่ต้องรบกวนผู้ใช้
  if (!isDirty(baseline.value, d.form)) {
    clearDraft()
    return
  }

  const res = await Swal.fire({
    icon: 'question',
    title: 'กู้คืนข้อมูลที่ยังไม่ได้บันทึก?',
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

/**
 * บันทึกร่างทุกครั้งที่ฟอร์มเปลี่ยน — **เงียบ ไม่มี Swal** (คนละเรื่องกับตอน "กู้คืน")
 * ⚠️ ลบร่างทันทีเมื่อค่ากลับมาเท่าตั้งต้น — ไม่งั้น "พิมพ์แล้วลบออก" จะทิ้งร่างค้างไว้
 *    แล้วรอบหน้าผู้ใช้จะถูกถามกู้คืนทั้งที่ไม่มีอะไรจะกู้
 */
watch(
  [form, isLoading],
  () => {
    if (isLoading.value || savedOk.value) return
    if (!dirty.value) {
      clearDraft()
      return
    }
    writeDraft(form.value)
  },
  { deep: true },
)

// ── กันข้อมูลหาย ชั้นที่ 1: ออกจากหน้า (guard ของ router) ─────────────────────

/**
 * 🔴 **ต้องเรียกที่ top level ของ `<script setup>` แบบ sync** — ถ้าไปเรียกใน `onMounted`
 *    หลัง `await` ตัว guard จะ **ไม่ถูกผูกเลย** (มีแค่ warning ใน dev ที่คนมักไม่เห็น)
 *    ⇒ หน้าที่ดูเหมือนป้องกันครบ แต่ไม่มีตาข่ายจริงแม้ชั้นเดียว
 */
onBeforeRouteLeave(async (to) => {
  if (savedOk.value) return true
  // กำลังบันทึกอยู่ — อย่าให้ออกกลางคันแล้วต้องมาเดาว่าบันทึกติดไหม (ไม่ต้องถามด้วย)
  if (saving.value) return false
  // ⚠️ ออกจากระบบ/หมดอายุ ต้องผ่านได้เสมอ ไม่งั้นผู้ใช้จะติดกับอยู่ในฟอร์ม และเจอ Swal ซ้อน
  //    (401 ที่ `api.ts` hard-nav ก็ไม่ผ่าน guard นี้อยู่แล้ว — ชั้นที่ 2 ดักไว้)
  if (to.name === 'login' || !authStore.isAuthenticated) return true
  if (!dirty.value) return true

  const res = await Swal.fire({
    icon: 'warning',
    title: 'ยังไม่ได้บันทึก',
    text: 'ข้อมูลที่แก้ไว้จะหายไปหากออกจากหน้านี้',
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

// ── บันทึก ───────────────────────────────────────────────────────────────────

function errText(e: unknown): string {
  if (typeof e === 'string') return e
  if (e instanceof Error) return e.message
  return 'เกิดข้อผิดพลาด กรุณาลองใหม่'
}

const goBack = () => router.push({ name: 'event-management' })

async function save() {
  if (saving.value || isDeleted.value) return
  // ด่านฝั่ง client — ไม่ให้ผู้ใช้รอเฉย ๆ เพื่อเจอ error ที่มองเห็นได้ด้วยตา (backend ยังเป็นผู้ตัดสิน)
  const invalid = formError.value
  if (invalid) {
    await Swal.fire({ icon: 'warning', title: 'ยังบันทึกไม่ได้', text: invalid })
    return
  }

  saving.value = true
  saveError.value = ''
  try {
    if (isEdit.value) {
      const id = eventId.value
      if (id === null) return
      const patch = buildPatch(baseline.value, buildCreate(form.value))
      if (Object.keys(patch).length === 0) {
        // ไม่มีอะไรเปลี่ยน = **ไม่ยิง API เลย** (ผู้ใช้อาจเปิดหน้าแล้วกดบันทึกโดยไม่ได้แก้)
        // ⚠️ ต้องตั้ง `savedOk` ที่นี่ด้วย ไม่ใช่แค่เส้นทางที่ยิง API สำเร็จ
        savedOk.value = true
        clearDraft()
        await router.push({ name: 'event-management' })
        return
      }
      await updateEvent(id, patch)
    } else {
      await createEvent(buildCreate(form.value))
    }

    savedOk.value = true // 🔴 ก่อน push เสมอ — ดูคอมเมนต์ของ `savedOk`
    clearDraft()
    await Swal.fire({
      icon: 'success',
      title: isEdit.value ? 'บันทึกแล้ว' : 'สร้างกิจกรรมแล้ว',
      text: isEdit.value ? undefined : 'กิจกรรมถูกสร้างเป็นฉบับร่าง — ยังไม่มีใครเห็นจนกว่าจะกด "เผยแพร่"',
      timer: isEdit.value ? 1200 : 1800,
      showConfirmButton: false,
    })
    await router.push({ name: 'event-management' })
  } catch (e) {
    // ฟอร์มยังอยู่ครบ — ผู้ใช้ไม่ต้องพิมพ์ใหม่ทั้งหมด (เหตุผลเดียวกับที่ย้ายมาเป็นหน้าเต็ม)
    saveError.value = errText(e)
  } finally {
    saving.value = false
  }
}

const inputCls =
  'mt-1 w-full px-3.5 py-2.5 border border-stone-300 rounded-xl text-sm bg-white transition focus:ring-2 focus:ring-brand/25 focus:border-brand'
</script>

<template>
  <div class="max-w-2xl mx-auto">
    <!-- Loading skeleton -->
    <div v-if="isLoading" class="space-y-4" aria-busy="true">
      <div class="h-6 w-64 animate-pulse rounded bg-stone-100"></div>
      <div class="space-y-5 rounded-2xl border border-stone-200 bg-white p-6 sm:p-8">
        <div v-for="i in 6" :key="i" class="space-y-2">
          <div class="h-3 w-24 animate-pulse rounded bg-stone-100"></div>
          <div class="h-10 animate-pulse rounded-lg bg-stone-100"></div>
        </div>
      </div>
    </div>

    <!-- ไม่มีกิจกรรมนี้ -->
    <div
      v-else-if="notFound"
      class="rounded-2xl border-2 border-dashed border-stone-200 bg-white py-16 text-center"
    >
      <i class="bi bi-calendar-x mb-3 block text-3xl text-stone-400"></i>
      <p class="text-[15px] font-semibold text-stone-700">ไม่พบกิจกรรมนี้</p>
      <p class="mt-1 text-sm text-stone-500">อาจถูกลบถาวรไปแล้ว หรือลิงก์ไม่ถูกต้อง</p>
      <button
        type="button"
        @click="goBack"
        class="mt-5 inline-flex items-center gap-2 rounded-lg bg-brand px-5 py-2.5 text-[13px] font-bold text-white transition-colors hover:bg-brand-strong"
      >
        <i class="bi bi-arrow-left"></i> กลับหน้าจัดการกิจกรรม
      </button>
    </div>

    <!-- Error + retry -->
    <div
      v-else-if="loadError"
      class="rounded-2xl border-2 border-dashed border-stone-200 bg-white py-16 text-center"
    >
      <i class="bi bi-plugin mb-3 block text-3xl text-stone-400"></i>
      <p class="text-[15px] font-semibold text-stone-700">โหลดข้อมูลกิจกรรมไม่สำเร็จ</p>
      <p class="mt-1 text-sm text-stone-500">ตรวจสอบการเชื่อมต่อแล้วลองอีกครั้ง</p>
      <button
        type="button"
        @click="load"
        class="mt-5 inline-flex items-center gap-2 rounded-lg bg-brand px-5 py-2.5 text-[13px] font-bold text-white transition-colors hover:bg-brand-strong"
      >
        <i class="bi bi-arrow-clockwise"></i> ลองใหม่
      </button>
    </div>

    <form v-else @submit.prevent="save" class="space-y-4">
      <!-- 🔴 ไม่มี <h1>/eyebrow ที่นี่ — `AppHeader` วาดชื่อหน้า (routeTitles) เป็น <h1> ให้แล้ว (R0.3)
           ที่เหลือคือ *ชื่อกิจกรรมที่กำลังแก้* ซึ่งเป็นเนื้อหา ไม่ใช่ชื่อหน้า -->
      <p v-if="isEdit && event" class="truncate text-sm text-stone-500">
        <i class="bi bi-calendar-event mr-1 text-stone-400"></i>{{ event.title }}
      </p>

      <!-- ถูกลบแล้ว (soft delete) — GET คืนแถวตามจริง แต่ PATCH จะ 404 ⇒ ปิดปุ่มบันทึกไว้ก่อน -->
      <div
        v-if="isDeleted"
        class="flex items-start gap-2.5 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3.5"
      >
        <i class="bi bi-trash3 mt-0.5 text-amber-600"></i>
        <div class="text-[13px] text-amber-800">
          <p class="font-bold">กิจกรรมนี้ถูกลบแล้ว — แก้ไขไม่ได้จนกว่าจะกู้คืน</p>
          <p class="mt-0.5 text-amber-700">
            กลับไปหน้าการจัดการกิจกรรม แล้วกด "กู้คืน" ในรายการก่อน
          </p>
        </div>
      </div>

      <!-- สถานะปัจจุบัน (โหมดแก้ไข) — การแก้ไขใบที่เผยแพร่แล้วมีผลกับคนที่เห็นอยู่ -->
      <div
        v-else-if="isEdit && event"
        class="flex items-center gap-2 rounded-2xl bg-stone-50 px-4 py-3 text-[12px] text-stone-600"
      >
        <i :class="STATUS_ICONS[event.status]"></i>
        สถานะ: <b>{{ STATUS_LABELS[event.status] }}</b>
        <span v-if="event.status === 'published'" class="text-stone-400">
          · แก้แล้วมีผลกับนักเรียนที่เห็นอยู่ทันที
        </span>
      </div>

      <div
        v-else
        class="rounded-2xl bg-stone-50 px-4 py-3 text-[12px] text-stone-500"
      >
        <i class="bi bi-info-circle mr-1"></i>
        กิจกรรมจะถูกสร้างเป็น <b>ฉบับร่าง</b> — นักเรียนยังไม่เห็นจนกว่าจะกด "เผยแพร่"
      </div>

      <!-- ฟิลด์ -->
      <div class="space-y-5 rounded-2xl border border-stone-200 bg-white p-6 sm:p-8">
        <div>
          <label for="ev-title" class="block text-xs font-semibold text-stone-700">
            ชื่อกิจกรรม <span class="text-brand">*</span>
          </label>
          <input
            id="ev-title"
            v-model="form.title"
            type="text"
            maxlength="200"
            placeholder="เช่น กิจกรรมวันวิทยาศาสตร์"
            :class="inputCls"
          />
        </div>

        <div>
          <label for="ev-desc" class="block text-xs font-semibold text-stone-700">รายละเอียด</label>
          <textarea
            id="ev-desc"
            v-model="form.description"
            rows="3"
            placeholder="อธิบายกิจกรรมสั้น ๆ ให้นักเรียนรู้ว่าต้องเตรียมอะไร"
            :class="inputCls + ' resize-y'"
          ></textarea>
        </div>

        <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <label for="ev-date" class="block text-xs font-semibold text-stone-700">
              วันและเวลาจัด <span class="text-brand">*</span>
            </label>
            <VueDatePicker
              id="ev-date"
              v-model="eventDateModel"
              v-bind="pickerProps"
              placeholder="วว/ดด/ปปปป ชช:นน"
              :clearable="false"
              class="mt-1"
            />
            <!-- คำอ่าน พ.ศ. — picker ไม่รองรับพุทธศักราช (date-fns) ⇒ ช่องเป็น ค.ศ. แล้วอ่านเป็นไทยใต้ช่อง -->
            <p class="mt-1 text-[11px] text-stone-400">
              {{ formatThaiDateTimeInput(form.event_date) || 'ยังไม่ได้เลือก' }}
            </p>
          </div>
          <div>
            <label for="ev-deadline" class="block text-xs font-semibold text-stone-700">
              ปิดรับสมัคร
            </label>
            <VueDatePicker
              id="ev-deadline"
              v-model="deadlineModel"
              v-bind="pickerProps"
              placeholder="วว/ดด/ปปปป ชช:นน"
              class="mt-1"
            />
            <p class="mt-1 text-[11px] text-stone-400">
              {{
                form.registration_deadline
                  ? formatThaiDateTimeInput(form.registration_deadline)
                  : 'เว้นว่างได้ — ระบบจะปิดรับเมื่อถึงเวลาจัด'
              }}
            </p>
          </div>
        </div>

        <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <label for="ev-capacity" class="block text-xs font-semibold text-stone-700">
              จำนวนที่นั่ง
            </label>
            <input
              id="ev-capacity"
              v-model="form.capacity"
              type="number"
              min="1"
              step="1"
              placeholder="เว้นว่าง = ไม่จำกัด"
              :class="inputCls"
            />
            <p class="mt-1 text-[11px] text-stone-400">
              ที่นั่งเต็มแล้วระบบจะเข้าคิวสำรองให้อัตโนมัติ
            </p>
          </div>
          <div>
            <label for="ev-location" class="block text-xs font-semibold text-stone-700">สถานที่</label>
            <input
              id="ev-location"
              v-model="form.location"
              type="text"
              maxlength="200"
              placeholder="เช่น หอประชุมพิริยาลัย"
              :class="inputCls"
            />
          </div>
        </div>

        <div>
          <label for="ev-category" class="block text-xs font-semibold text-stone-700">
            หมวดกิจกรรม
          </label>
          <select
            id="ev-category"
            v-model="form.category"
            data-testid="form-category"
            :class="inputCls"
          >
            <option v-for="o in categoryOptions" :key="o.value" :value="o.value">
              {{ o.label }}
            </option>
          </select>
          <p class="mt-1 text-[11px] text-stone-400">
            ใช้กรองในรายการกิจกรรม — ไม่กระทบใครที่สมัครไว้แล้ว
          </p>
        </div>

        <div>
          <label for="ev-cover" class="block text-xs font-semibold text-stone-700">ลิงก์ภาพปก</label>
          <input
            id="ev-cover"
            v-model="form.cover_image_url"
            type="url"
            maxlength="500"
            placeholder="https://…"
            :class="inputCls"
          />
          <img
            v-if="form.cover_image_url"
            :src="form.cover_image_url"
            alt="ตัวอย่างภาพปก"
            class="mt-2 max-h-32 w-full rounded-xl border border-stone-200 bg-stone-100 object-cover"
          />
        </div>
      </div>

      <!-- ปุ่ม -->
      <div class="flex items-center gap-2">
        <span v-if="saveError" class="mr-auto text-[12px] font-semibold text-amber-600">
          {{ saveError }}
        </span>
        <button
          type="submit"
          :disabled="saving || isDeleted || !!formError"
          data-testid="save-event"
          class="flex-1 rounded-xl bg-brand px-4 py-3 text-sm font-bold text-white shadow-md transition-all hover:bg-brand-strong hover:shadow-lg active:scale-[0.99] disabled:opacity-50"
        >
          <i :class="saving ? 'bi bi-arrow-repeat animate-spin' : 'bi bi-check-lg'" class="mr-1"></i>
          {{ saving ? 'กำลังบันทึก...' : 'บันทึก' }}
        </button>
        <button
          type="button"
          @click="goBack"
          class="rounded-xl border border-stone-200 bg-white px-5 py-3 text-sm font-medium text-stone-600 transition hover:bg-stone-50"
        >
          ยกเลิก
        </button>
      </div>
    </form>
  </div>
</template>
