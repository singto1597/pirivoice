<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { onBeforeRouteLeave, useRouter } from 'vue-router'
import Swal from 'sweetalert2'
import { createIssue } from '@/services/issue'
import {
  MAIN_CATEGORIES,
  MAIN_CATEGORY_LABELS,
  LEVEL_LABELS,
  subcategoryLabel,
  type Category,
  type Issue,
  type IssueLevel,
  type MainCategory,
  type RequestedDestination,
} from '@/types/issue'
import { useAuthStore } from '@/stores/auth'
import { BRAND } from '@/constants/brand'
import AppCard from '@/components/ui/AppCard.vue'
import AppButton from '@/components/ui/AppButton.vue'
import AppChip from '@/components/ui/AppChip.vue'

/**
 * 📝 ฟอร์มแจ้งเรื่อง — **ตัวช่วยกรอก 3 ขั้น ไม่ใช่แบบฟอร์มยาวหน้าเดียว**
 *
 * ⭐ ของเดิมเป็นฟอร์มหน้าเดียวที่มีหัวข้อ 1.–5. เรียงลงมา และ **หัวข้อ 2 ผูกกับ
 *    `v-if="mainCategory"`** ⇒ ก่อนเลือกหมวดผู้ใช้เห็นเลข **1, 3, 4, 5** (เลขกระโดด)
 *    ซึ่งเป็นบั๊กที่อธิบายได้จากโครงสร้าง ไม่ใช่ความสะเพร่า — ⇒ แก้ที่โครงสร้าง
 *    (stepper 3 ขั้นที่แสดงครบเสมอ) ไม่ใช่เติมเลขให้ต่อกัน
 *
 * ⭐ **ไม่ลดฟีเจอร์แม้แต่ตัวเดียว** — ทุกช่องของเดิมยังอยู่ (`main_category` · `category` ·
 *    `start_level` · `title` · `description` · `is_anonymous` · `requested_destination`)
 *    แค่ย้ายที่อยู่: `is_anonymous` ขึ้นมาจากท้ายฟอร์มไปอยู่ขั้น 2 ซึ่งเป็นที่ที่ผู้ใช้
 *    กำลังตัดสินใจเรื่อง "จะเล่ารายละเอียดแค่ไหน" อยู่แล้ว
 *
 * 🔴 **เป็นหน้าเต็ม ห้ามเป็น modal** (skills #16) — และมีตาข่ายกันข้อมูลหายครบ 3 ชั้น
 *    (guard ของ router · `beforeunload` · ร่างอัตโนมัติใน `sessionStorage`) ตาม skills #17
 *
 * ⚠️ **ส่วนเบี่ยงเบนจากแผนที่ตั้งใจ:** แผนระบุขั้น 2 ว่ามี "รูป/หลักฐาน" ด้วย
 *    แต่ **ระบบนี้ไม่มี endpoint อัปโหลดรูปของเรื่องเลย** (`services/` มีแต่
 *    `uploadStudentExcel`) · `Issue.image_url` มีอยู่จริงแต่ **อ่านได้อย่างเดียว**
 *    ไม่มีทางตั้งค่าจากฝั่งผู้ใช้ ⇒ **ไม่ทำ** ด้วยเหตุผลเดียวกับที่แผนตัด "ส่งออก Excel" ทิ้ง
 *    (ต้องทำ backend ใหม่ = คนละใบงาน) · การใส่ช่องอัปโหลดที่ส่งไม่ได้จริง
 *    แย่กว่าไม่มี เพราะผู้ใช้จะแนบรูปแล้วเชื่อว่าส่งไปแล้ว
 */

const router = useRouter()
const authStore = useAuthStore()

// ── ขั้นตอน ──────────────────────────────────────────────────────────────────

/**
 * 🔴 **3 ขั้น ไม่ใช่ 5 หัวข้อย่อย** — และแสดงครบทั้ง 3 ตลอดเวลา
 *    (ของเดิมหัวข้อ 2 โผล่หลังเลือกหมวด ⇒ เลขกระโดด 1→3)
 */
const STEPS = [
  { n: 1 as const, label: 'ประเภท' },
  { n: 2 as const, label: 'รายละเอียด' },
  { n: 3 as const, label: 'ตรวจสอบ' },
]
const step = ref<1 | 2 | 3>(1)

/** จุดบนสุดของตัวช่วยกรอก — ใช้เลื่อนกลับขึ้นบนเมื่อเปลี่ยนขั้น (ไม่แตะ `<main>` ของ layout) */
const topEl = ref<HTMLElement | null>(null)

/**
 * ⚠️ เปลี่ยนขั้น **ต้องเลื่อนขึ้นบนสุด** ไม่งั้นผู้ใช้ที่เลื่อนอยู่ท้ายขั้น 2
 *    จะกด "ถัดไป" แล้วเห็น *ท้าย* ของขั้น 3 ซึ่งอ่านเหมือนไม่มีอะไรเกิดขึ้น
 *    (และ `scrollIntoView` ที่ element ต้นทาง ปลอดภัยกว่าไปสั่ง `<main>` ของ layout โดยตรง)
 */
async function goStep(n: 1 | 2 | 3) {
  step.value = n
  await nextTick()
  topEl.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

// ── ค่าฟอร์ม ─────────────────────────────────────────────────────────────────

interface IssueFormValues {
  mainCategory: MainCategory | ''
  category: Category | ''
  title: string
  description: string
  isAnonymous: boolean
  startLevel: string
  /**
   * 🔴 **`''` = ยังไม่เลือก — ไม่มีค่าเริ่มต้น** (ต่างจากของเดิมที่ตั้ง `'normal'` ไว้ก่อน)
   *
   * ของเดิมเลือก "ดำเนินการปกติ" ให้ล่วงหน้า ⇒ ผู้ใช้ที่อยากได้บอร์ดโหวตต้อง *สังเกตเห็น*
   * ว่ามีตัวเลือกนี้ แล้วเปลี่ยน — คนที่ไม่อ่านจะได้เรื่องปกติโดยไม่รู้ตัวว่ามีทางเลือกอื่น
   * ⇒ เป็นคำถามที่ระบบตอบแทนผู้ใช้ ซึ่งเป็นข้อที่ audit ฟ้องตรง ๆ
   */
  requestedDestination: RequestedDestination | ''
}

/**
 * ⚠️ ใช้ **ออบเจกต์ก้อนเดียว** (`form`) ไม่ใช่ `ref` แยกทีละช่อง — เพราะ
 *    ร่างอัตโนมัติต้อง serialize ทั้งก้อน และ "สกปรกไหม" ต้องเทียบทั้งก้อน
 *    (แนวเดียวกับ `EventForm.vue` ⇒ อ่านโค้ดสองฟอร์มรู้เรื่องเดียวกัน)
 */
const EMPTY_ISSUE_FORM: IssueFormValues = {
  mainCategory: '',
  category: '',
  title: '',
  description: '',
  isAnonymous: false,
  // ระดับเริ่มต้น — ผู้ใช้ทั่วไปเริ่มที่ห้องเสมอ (ไม่มีตัวเลือกให้เห็น ดู `selectableLevels`)
  startLevel: 'room',
  requestedDestination: '',
}

const form = ref<IssueFormValues>({ ...EMPTY_ISSUE_FORM })
const isLoading = ref(false)

/** สร้างสำเร็จแล้ว — เก็บใบที่ได้มาเพื่อแสดง "หน้าเต็ม" พร้อมเลขเรื่อง */
const created = ref<Issue | null>(null)
/**
 * 🔴 ตั้ง **ก่อน** `router.push`/`clearDraft` เสมอ — ใช้ปลด guard ทุกชั้น
 *    ถ้าลืม: guard จะยิงใส่การนำทางของตัวมันเอง ⇒ ผู้ใช้เห็นกล่อง "ยังไม่บันทึก ทิ้งไหม"
 *    **หลังกดส่งสำเร็จ** ซึ่งอ่านได้ว่า "ส่งไม่ติด" (คลาสเดียวกับบั๊กใน `EventForm.vue`)
 */
const savedOk = ref(false)

// ── ตัวเลือกที่ได้จากค่าที่เลือก ──────────────────────────────────────────────

/**
 * หมวดย่อยที่เลือกได้ พร้อมป้ายไทย
 * ⭐ ใช้ `subcategoryLabel()` ที่มีอยู่แล้วจาก `types/issue` — **ไม่เขียนตารางป้ายซ้ำที่นี่**
 *    (สองที่จะเพี้ยนจากกันวันหนึ่ง แล้วผู้ใช้จะเห็นชื่อหมวดไม่ตรงกันในสองหน้า)
 */
const categoryOptions = computed<Array<{ value: Category; label: string }>>(() => {
  const mc = form.value.mainCategory
  if (!mc) return []
  return (Object.keys(MAIN_CATEGORIES[mc].subcategories) as Category[]).map((c) => ({
    value: c,
    label: subcategoryLabel(mc, c),
  }))
})

/** ข้อความหมวดย่อยที่เลือกอยู่ — ใช้สรุปในขั้น 3 */
const subcategoryText = computed(() => {
  const mc = form.value.mainCategory
  if (!mc || !form.value.category) return ''
  return subcategoryLabel(mc, form.value.category)
})

/**
 * ⚠️ `form.startLevel` เป็น `string` เพราะเก็บลงร่างได้ตรง ๆ ⇒ ต้องมีตัวแปลงก่อนใช้เป็นคีย์
 *    ของ `LEVEL_LABELS` (ไม่งั้นต้อง `as` กระจายในเทมเพลต ซึ่ง type-check จับได้ทีหลัง)
 */
function levelLabel(lv: string): string {
  return LEVEL_LABELS[lv as IssueLevel] ?? lv
}

/** ตัวจัดการที่ต้องทำมากกว่าหนึ่งอย่าง — **ห้ามเขียน inline หลายคำสั่ง** (skills #10) */
function pickMainCategory(key: MainCategory) {
  form.value.mainCategory = key
  // 🔴 เปลี่ยนหมวดหลัก ⇒ หมวดย่อยของหมวดเดิมใช้ไม่ได้แล้ว **ต้องล้าง**
  //    ไม่งั้นส่ง `{main_category:'report', category:'academic'}` ซึ่ง backend จะปฏิเสธ
  form.value.category = ''
}

function pickCategory(c: Category) {
  form.value.category = c
  touch('category')
}

function pickDestination(d: RequestedDestination) {
  form.value.requestedDestination = d
  touch('destination')
}

/** ขอเผยแพร่ (โหวต/พูดคุย) → เรื่องวิ่งตรงไปสภาเพื่อพิจารณา ไม่ผ่านหัวหน้าห้อง */
const wantsPublic = computed(
  () => form.value.requestedDestination !== '' && form.value.requestedDestination !== 'normal',
)

const DESTINATION_OPTIONS: Array<{
  value: RequestedDestination
  label: string
  icon: string
  desc: string
}> = [
  {
    value: 'normal',
    label: 'ดำเนินการปกติ',
    icon: 'bi-check2-circle',
    desc: 'สภานักเรียนรับเรื่องแล้วจัดการตามขั้นตอนปกติ',
  },
  {
    value: 'vote',
    label: 'โหวตสาธารณะ',
    icon: 'bi-bar-chart-fill',
    desc: 'สภาอนุมัติ → เผยแพร่เป็นบอร์ดโหวตให้ทุกคนโหวตได้',
  },
  {
    value: 'talk',
    label: 'พูดคุยสาธารณะ',
    icon: 'bi-chat-dots-fill',
    desc: 'สภาอนุมัติ → เผยแพร่เป็นบอร์ดพูดคุยให้ทุกคนร่วมแสดงความเห็น',
  },
]

/** ไอคอนของหมวดหลัก — เก็บตารางไว้ที่เดียว ไม่กระจาย `v-if` ในเทมเพลต */
const MAIN_CATEGORY_ICONS: Record<MainCategory, string> = {
  suggestion: 'bi-lightbulb',
  wellbeing: 'bi-heart-pulse',
  report: 'bi-exclamation-triangle',
}

// ── ระดับเริ่มต้น ────────────────────────────────────────────────────────────

/**
 * ระดับสูงสุดที่ผู้ใช้มี — ใช้กำหนดว่าเลือกระดับเริ่มต้นได้ถึงไหน
 * ⚠️ ผู้ใช้ทั่วไป (student) ได้ `'student'` ⇒ `selectableLevels` ว่าง ⇒ **ไม่เห็นตัวเลือกนี้เลย**
 *    ซึ่งถูกต้อง: การเลือกระดับเริ่มต้นเป็นความสามารถของคนที่มีตำแหน่งแล้วเท่านั้น
 */
const myLevel = computed(() => {
  const roleLevels: Record<string, string> = {
    class_president: 'room',
    vice_academic: 'room',
    vice_discipline: 'room',
    vice_activity: 'room',
    vice_reception: 'room',
    level_president: 'level',
    council_member: 'council',
    council_president: 'council',
    teacher: 'council',
    teacher_council: 'council',
    admin: 'council',
  }
  const rank = { student: 0, room: 1, level: 2, council: 3 } as const
  let best: keyof typeof rank = 'student'
  for (const r of authStore.roles) {
    const lv = (roleLevels[r.role || ''] || 'student') as keyof typeof rank
    if (rank[lv] > rank[best]) best = lv
  }
  return best
})

const selectableLevels = computed(() => {
  const rank = { student: 0, room: 1, level: 2, council: 3 } as const
  const myRank = rank[myLevel.value]
  return (['room', 'level', 'council'] as const).filter((l) => rank[l] <= myRank)
})

// ── ความถูกต้องของแต่ละขั้น (inline error ไม่ใช่ Swal เรียงกัน 4 ใบ) ──────────

interface FieldErrors {
  category?: string
  title?: string
  description?: string
  destination?: string
}

/**
 * ⭐ ของเดิมใช้ `Swal.fire` 4 ใบเรียงกันตอนกดส่ง (เลือกหมวด → เลือกหมวดย่อย → หัวข้อสั้น →
 *    รายละเอียดสั้น) ⇒ ผู้ใช้แก้ทีละข้อแล้วโดนเด้งใหม่ทุกครั้ง และ **ไม่เห็นว่าช่องไหนผิด**
 *    ⇒ เปลี่ยนเป็น error ใต้ช่อง + ปุ่ม "ถัดไป" ปิดไว้จนกว่าจะครบ
 */
const errors = computed<FieldErrors>(() => {
  const e: FieldErrors = {}
  if (!form.value.category) e.category = 'เลือกหมวดหมู่ย่อยของเรื่องนี้'
  if (form.value.title.trim().length < 3) e.title = 'หัวข้ออย่างน้อย 3 ตัวอักษร'
  if (form.value.description.trim().length < 3) e.description = 'รายละเอียดอย่างน้อย 3 ตัวอักษร'
  if (!form.value.requestedDestination) e.destination = 'เลือกรูปแบบการดำเนินการ'
  return e
})

/** แต่ละขั้นผ่านเกณฑ์หรือยัง — ขั้น 1 นับทั้งหมวดหลักและหมวดย่อย */
const stepValid = computed(() => {
  if (step.value === 1) return Boolean(form.value.mainCategory && form.value.category)
  if (step.value === 2) return !errors.value.title && !errors.value.description
  return !errors.value.destination
})

/**
 * ⚠️ แสดง error **หลังผู้ใช้แตะช่องนั้นแล้ว** (`touched`) หรือ **พยายามไปขั้นถัดไป** (`triedNext`)
 *    ⇒ ไม่ขึ้นแดงทันทีที่เปิดหน้า ซึ่งอ่านเหมือนถูกด่าว่าก่อนทำอะไรผิด
 */
const touched = ref<Record<string, boolean>>({})
const triedNext = ref(false)
const touch = (k: string) => {
  touched.value[k] = true
}
function errorOf(k: keyof FieldErrors): string | undefined {
  return touched.value[k] || triedNext.value ? errors.value[k] : undefined
}

/** บอกว่ายังขาดอะไร — ใช้คู่กับปุ่มที่ถูกปิดไว้ ไม่ปล่อยให้ผู้ใช้เดาเองว่าทำไมกดไม่ได้ */
const nextHint = computed(() => {
  if (step.value === 1) {
    if (!form.value.mainCategory) return 'เลือกหมวดหลักก่อนจึงจะไปต่อได้'
    if (!form.value.category) return 'เลือกหมวดหมู่ย่อยก่อนจึงจะไปต่อได้'
    return ''
  }
  if (step.value === 2) {
    if (errors.value.title) return 'ตั้งหัวข้ออย่างน้อย 3 ตัวอักษร'
    if (errors.value.description) return 'อธิบายรายละเอียดอย่างน้อย 3 ตัวอักษร'
    return ''
  }
  return errors.value.destination ? 'เลือกรูปแบบการดำเนินการก่อนจึงจะส่งได้' : ''
})

function onNext() {
  if (!stepValid.value) {
    triedNext.value = true
    return
  }
  triedNext.value = false
  if (step.value === 1) void goStep(2)
  else if (step.value === 2) void goStep(3)
}

// ── ส่ง ──────────────────────────────────────────────────────────────────────

async function handleSubmit() {
  if (isLoading.value || !stepValid.value) {
    triedNext.value = true
    return
  }
  // 🔴 `mainCategory`/`category`/`requestedDestination` ผ่าน `stepValid` มาแล้ว
  //    แต่ TypeScript ยังไม่รู้ ⇒ เช็คซ้ำแบบแคบ ๆ ตรงนี้แทนการใช้ `!` (โปรเจกต์เปิด strict)
  const mc = form.value.mainCategory
  const cat = form.value.category
  const dest = form.value.requestedDestination
  if (!mc || !cat || !dest) return

  isLoading.value = true
  try {
    const issue = await createIssue({
      main_category: mc,
      category: cat,
      start_level: form.value.startLevel,
      title: form.value.title.trim(),
      description: form.value.description.trim(),
      is_anonymous: form.value.isAnonymous,
      requested_destination: dest,
    })
    // ⚠️ ตั้ง `savedOk` **ก่อน**อย่างอื่น — ปลด guard ทุกชั้นทันทีที่เซิร์ฟเวอร์รับเรื่องแล้ว
    savedOk.value = true
    clearDraft()
    created.value = issue
    await nextTick()
    topEl.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  } catch (e) {
    Swal.fire({
      icon: 'error',
      title: 'แจ้งเรื่องไม่สำเร็จ',
      text: e instanceof Error ? e.message : 'เกิดข้อผิดพลาด กรุณาลองใหม่',
      confirmButtonColor: BRAND,
    })
  } finally {
    isLoading.value = false
  }
}

/**
 * เริ่มใบใหม่ — **ไม่ reload หน้า** เพื่อให้ผู้ใช้ที่แจ้งหลายเรื่องติดกันไม่ต้องรอโหลดแอปใหม่
 * ⚠️ ต้องล้าง `savedOk` ด้วย ไม่งั้นใบใหม่จะไม่มี guard กันข้อมูลหายเลย
 */
function startAnother() {
  created.value = null
  savedOk.value = false
  triedNext.value = false
  touched.value = {}
  form.value = { ...EMPTY_ISSUE_FORM }
  step.value = 1
  void nextTick().then(() => topEl.value?.scrollIntoView({ block: 'start' }))
}

// ── กันข้อมูลหาย ชั้นที่ 3: ร่างอัตโนมัติใน sessionStorage ─────────────────────

const DRAFT_KEY = 'piri_issue_form_draft'
/** ⚠️ เปลี่ยนเมื่อแก้รูปร่างของ `StoredDraft` เท่านั้น — ร่างเวอร์ชันเก่าจะถูกทิ้ง ไม่ใช่ตีความผิด */
const DRAFT_VERSION = 1

interface StoredDraft {
  v: number
  /** epoch ms — ใช้แสดง "บันทึกร่างแล้ว HH:MM" */
  savedAt: number
  form: IssueFormValues
}

/** เวลาที่เขียนร่างล่าสุด — 0 = ยังไม่มีร่าง (ใช้ซ่อนข้อความ "บันทึกร่างแล้ว") */
const draftSavedAt = ref(0)

/** ตรวจรูปร่างก่อนใช้ — `sessionStorage` ถูกเขียนโดยโค้ดเวอร์ชันอื่นได้ (เปิดสองแท็บข้าม deploy) */
function isFormValues(x: unknown): x is IssueFormValues {
  if (typeof x !== 'object' || x === null) return false
  const o = x as Record<string, unknown>
  return (
    typeof o.mainCategory === 'string' &&
    typeof o.category === 'string' &&
    typeof o.title === 'string' &&
    typeof o.description === 'string' &&
    typeof o.isAnonymous === 'boolean' &&
    typeof o.startLevel === 'string' &&
    typeof o.requestedDestination === 'string'
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

const dirty = computed(
  () => JSON.stringify(form.value) !== JSON.stringify(EMPTY_ISSUE_FORM),
)

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
  // ร่างที่ว่างเปล่า (หรือเท่าค่าตั้งต้น) = ไม่มีอะไรให้กู้ — ลบทิ้งเงียบ ๆ
  if (JSON.stringify(d.form) === JSON.stringify(EMPTY_ISSUE_FORM)) {
    clearDraft()
    return
  }
  const res = await Swal.fire({
    icon: 'question',
    title: 'กู้คืนเรื่องที่ยังไม่ได้ส่ง?',
    text: 'พบเรื่องที่พิมพ์ค้างไว้จากรอบก่อน — ต้องการนำกลับมาใส่ฟอร์มหรือไม่',
    showCancelButton: true,
    confirmButtonText: 'กู้คืน',
    cancelButtonText: 'ไม่ต้อง',
    confirmButtonColor: BRAND,
  })
  if (res.isConfirmed) {
    form.value = d.form
    touched.value = {}
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
  if (isLoading.value) return false
  // ⚠️ ออกจากระบบ/หมดอายุ ต้องผ่านได้เสมอ ไม่งั้นผู้ใช้จะติดกับอยู่ในฟอร์ม แล้วเจอ Swal ซ้อน
  if (to.name === 'login' || !authStore.isAuthenticated) return true
  if (!dirty.value) return true

  const res = await Swal.fire({
    icon: 'warning',
    title: 'ยังไม่ได้ส่งเรื่อง',
    text: 'เรื่องที่พิมพ์ไว้จะหายไปหากออกจากหน้านี้',
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
  <!--
    ✅ **หน้าสำเร็จ = หน้าเต็ม ไม่ใช่ Swal** — ของเดิมส่งเสร็จแล้วขึ้นกล่องปิดทันที
       ⇒ **ผู้ใช้ไม่เคยเห็นเลขที่เรื่องของตัวเอง** ทั้งที่เป็นสิ่งที่ต้องใช้ตอนติดตาม/อ้างอิง
  -->
  <div v-if="created" ref="topEl" class="mx-auto flex max-w-2xl flex-col gap-4">
    <AppCard>
      <div class="flex flex-col items-center px-2 py-6 text-center">
        <span
          class="flex h-16 w-16 items-center justify-center rounded-full bg-ok-soft text-ok"
          aria-hidden="true"
        >
          <i class="bi bi-check-lg text-3xl" />
        </span>
        <h2 class="mt-4 text-title-l font-bold text-ink-1">ส่งเรื่องสำเร็จ</h2>
        <p class="mt-1 text-sm leading-relaxed text-ink-2">
          {{
            wantsPublic
              ? 'เรื่องถูกส่งไปยังสภานักเรียนเพื่อพิจารณาเผยแพร่เป็นบอร์ดสาธารณะแล้ว'
              : 'เรื่องถูกส่งไปยังหัวหน้าห้องและรองฝ่ายแล้ว'
          }}
        </p>

        <!-- เลขที่เรื่อง — ตัวเลขเดียวที่ต้องจด จึงให้พื้นที่และขนาดมากกว่าอย่างอื่น -->
        <div class="mt-5 w-full rounded-card border border-line bg-canvas px-4 py-3">
          <p class="text-[13px] font-medium text-ink-2">เลขที่เรื่อง</p>
          <p class="mt-0.5 text-title-l font-bold tabular-nums text-brand">#{{ created.id }}</p>
          <p class="mt-1 line-clamp-2 text-[13px] leading-relaxed text-ink-2">
            {{ created.title }}
          </p>
        </div>

        <div class="mt-5 flex w-full flex-col gap-2 sm:flex-row">
          <!-- ⚠️ ผูกกับ e2e (`piri-boards-flow.spec.ts`) — ใช้เป็นทางไปหน้ารายละเอียดแทน `.swal2-confirm` เดิม -->
          <AppButton
            data-testid="goto-created-issue"
            block
            @click="router.push({ name: 'issue-detail', params: { id: created.id } })"
          >
            <template #icon><i class="bi bi-box-arrow-up-right" /></template>
            ดูเรื่องนี้
          </AppButton>
          <AppButton variant="secondary" block @click="startAnother">
            <template #icon><i class="bi bi-plus-lg" /></template>
            แจ้งเรื่องใหม่
          </AppButton>
        </div>
      </div>
    </AppCard>

    <AppButton variant="text" block @click="router.push({ name: 'my-issues' })">
      ไปที่ "เรื่องของฉัน" เพื่อติดตามสถานะ
    </AppButton>
  </div>

  <div v-else ref="topEl" class="mx-auto flex max-w-2xl flex-col gap-4">
    <!--
      🪜 stepper — **แสดงครบ 3 ขั้นตลอดเวลา**
      ⭐ ของเดิมมีหัวข้อ 1.–5. โดยข้อ 2 ผูกกับ `v-if="mainCategory"` ⇒ ก่อนเลือกหมวด
         ผู้ใช้เห็นเลข **1, 3, 4, 5** · แก้ที่โครงสร้าง: จำนวนขั้นคงที่ไม่ว่าข้อมูลจะกรอกถึงไหน
    -->
    <ol class="flex items-center gap-1.5" aria-label="ขั้นตอนการแจ้งเรื่อง">
      <li v-for="s in STEPS" :key="s.n" class="flex min-w-0 items-center">
        <div
          class="flex min-w-0 items-center gap-2 rounded-control px-2.5 py-2"
          :class="step === s.n ? 'bg-brand-tint' : ''"
          :aria-current="step === s.n ? 'step' : undefined"
          :aria-label="`ขั้นที่ ${s.n} ${s.label}`"
        >
          <span
            class="flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[12px] font-bold"
            :class="
              step > s.n
                ? 'bg-ok text-white'
                : step === s.n
                  ? 'bg-brand text-white'
                  : 'bg-canvas text-ink-3'
            "
            aria-hidden="true"
          >
            <i v-if="step > s.n" class="bi bi-check-lg" />
            <template v-else>{{ s.n }}</template>
          </span>
          <!--
            🔴 **มือถือโชว์ชื่อเฉพาะขั้นที่กำลังทำ** — วัดบน staging 360dp แล้วเจอ "รายละเอียด"
               ถูกตัดเหลือ **"รายละ..."** เพราะ `flex-1` แบ่งสามส่วนเท่ากันแล้ว `truncate`
               ⇒ ขั้นอื่นเหลือแต่วงกลมเลข ซึ่งอ่านออกและ **ไม่ตัดคำ**
               · ชื่อเต็มยังถึง screen reader ผ่าน `aria-label` ของแต่ละขั้น (ด้านบน)
               · ใช้ `whitespace-nowrap` **ไม่ใช่ `truncate`** ⇒ ตัดคำเป็นไปไม่ได้โดยโครงสร้าง
          -->
          <span
            class="text-[13px] font-semibold whitespace-nowrap"
            :class="[step === s.n ? 'text-brand' : 'text-ink-3', step === s.n ? null : 'hidden sm:inline']"
          >
            {{ s.label }}
          </span>
        </div>
      </li>
    </ol>

    <!-- ── ขั้น 1: ประเภท ─────────────────────────────────────────────────── -->
    <AppCard v-if="step === 1">
      <h2 class="text-title-m font-bold text-ink-1">เรื่องนี้เป็นเรื่องแบบไหน</h2>
      <p class="mt-1 text-[13px] leading-relaxed text-ink-2">
        เลือกหมวดหลัก แล้วเลือกหมวดหมู่ย่อยให้ตรงกับเรื่องมากที่สุด
      </p>

      <div class="mt-4 grid grid-cols-1 gap-2 sm:grid-cols-3">
        <button
          v-for="(info, key) in MAIN_CATEGORIES"
          :key="key"
          type="button"
          :data-testid="'cat-' + key"
          class="flex min-h-[72px] items-center gap-3 rounded-card border p-3 text-left transition-colors sm:flex-col sm:justify-center sm:text-center"
          :class="
            form.mainCategory === key
              ? 'border-brand bg-brand-tint'
              : 'border-line bg-surface hover:border-ink-3'
          "
          :aria-pressed="form.mainCategory === key"
          @click="pickMainCategory(key as MainCategory)"
        >
          <i
            :class="[
              'bi',
              MAIN_CATEGORY_ICONS[key as MainCategory],
              'text-xl',
              form.mainCategory === key ? 'text-brand' : 'text-ink-2',
            ]"
            aria-hidden="true"
          />
          <span
            class="text-sm font-semibold leading-snug"
            :class="form.mainCategory === key ? 'text-brand' : 'text-ink-1'"
          >
            {{ info.label }}
          </span>
        </button>
      </div>

      <!-- หมวดย่อย — โผล่หลังเลือกหมวดหลัก (ขั้นยังเป็น 1 ⇒ เลขไม่กระโดด) -->
      <div v-if="form.mainCategory" class="mt-4 border-t border-line pt-4">
        <p class="mb-2 text-[13px] font-semibold text-ink-2">
          หมวดหมู่ย่อยของ "{{ MAIN_CATEGORY_LABELS[form.mainCategory] }}"
        </p>
        <div class="chip-row">
          <AppChip
            v-for="o in categoryOptions"
            :key="o.value"
            :label="o.label"
            :active="form.category === o.value"
            @click="pickCategory(o.value)"
          />
        </div>
        <p v-if="errorOf('category')" class="mt-2 text-[13px] font-medium text-danger">
          {{ errorOf('category') }}
        </p>
      </div>
    </AppCard>

    <!-- ── ขั้น 2: รายละเอียด ─────────────────────────────────────────────── -->
    <AppCard v-else-if="step === 2">
      <h2 class="text-title-m font-bold text-ink-1">เล่าเรื่องให้ละเอียด</h2>
      <p class="mt-1 text-[13px] leading-relaxed text-ink-2">
        ยิ่งบอกสถานที่ เวลา และสิ่งที่เกิดขึ้นชัดเจน เรื่องจะถูกส่งต่อถึงคนที่แก้ได้เร็วขึ้น
      </p>

      <div class="mt-4 space-y-4">
        <div>
          <label for="issue-title" class="mb-1 block text-[13px] font-semibold text-ink-2">
            หัวข้อ
          </label>
          <input
            id="issue-title"
            v-model="form.title"
            type="text"
            data-testid="issue-title"
            class="field"
            placeholder="สรุปสั้น ๆ ว่าเรื่องอะไร"
            maxlength="200"
            :aria-invalid="Boolean(errorOf('title'))"
            @blur="touch('title')"
          />
          <p v-if="errorOf('title')" class="mt-1 text-[13px] font-medium text-danger">
            {{ errorOf('title') }}
          </p>
        </div>

        <div>
          <label for="issue-desc" class="mb-1 block text-[13px] font-semibold text-ink-2">
            รายละเอียด
          </label>
          <textarea
            id="issue-desc"
            v-model="form.description"
            rows="6"
            data-testid="issue-desc"
            class="field"
            placeholder="อธิบายปัญหาหรือความคิดเห็นให้ละเอียด..."
            :aria-invalid="Boolean(errorOf('description'))"
            @blur="touch('description')"
          />
          <p v-if="errorOf('description')" class="mt-1 text-[13px] font-medium text-danger">
            {{ errorOf('description') }}
          </p>
        </div>

        <!--
          🔴 **ย้าย `is_anonymous` มาจากท้ายฟอร์ม (ข้อ 5 เดิม) มาที่นี่**
          ⭐ เพราะเป็นคำถามที่ผูกกับการ "เล่ารายละเอียด" — ผู้ใช้กำลังตัดสินใจอยู่ว่าจะเล่าแค่ไหน
             ⇒ วางไว้ข้างช่องรายละเอียดจึงเป็นที่ที่คำถามนี้ถูกถามจริง

          ⚠️ และ **ต้องบอกให้ตรงว่าไม่ระบุตัวตนครอบคลุมถึงไหน** — `is_anonymous` ซ่อน
             *ชื่อผู้แจ้ง* แต่ `CommentOut.commenter_name` เป็น **ชื่อจริงเสมอ**
             ⇒ ถ้าใบ้น้อยเกินไป ผู้ใช้จะไปคอมเมนต์โดยเชื่อว่าตัวเองนิรนาม
        -->
        <label
          class="flex cursor-pointer items-start gap-3 rounded-control bg-canvas p-3 select-none"
        >
          <input
            v-model="form.isAnonymous"
            type="checkbox"
            class="mt-0.5 h-4 w-4 shrink-0 rounded border-line accent-brand"
          />
          <span class="min-w-0">
            <span class="block text-sm font-semibold text-ink-1">ซ่อนชื่อฉัน (ไม่ระบุตัวตน)</span>
            <span class="mt-0.5 block text-[13px] leading-relaxed text-ink-2">
              ซ่อนชื่อ<b>ผู้แจ้ง</b>จากผู้ที่เปิดเรื่องนี้ —
              แต่คอมเมนต์ใต้เรื่องยังแสดงชื่อจริงของผู้เขียนเสมอ
            </span>
          </span>
        </label>

        <!-- ระดับเริ่มต้น — เห็นเฉพาะผู้ที่มีตำแหน่ง (ดู `selectableLevels`) -->
        <div v-if="selectableLevels.length > 1" class="rounded-control bg-canvas p-3">
          <p class="mb-2 text-[13px] font-semibold text-ink-2">ระดับเริ่มต้นของเรื่อง</p>
          <div class="chip-row">
            <AppChip
              v-for="lv in selectableLevels"
              :key="lv"
              :label="LEVEL_LABELS[lv]"
              :active="form.startLevel === lv"
              @click="form.startLevel = lv"
            />
          </div>
          <p class="mt-2 text-[13px] leading-relaxed text-ink-2">
            เลือกเริ่มที่ระดับสูงขึ้นได้เลย ไม่ต้องแจ้งแล้วส่งต่อทีหลัง
          </p>
        </div>
      </div>
    </AppCard>

    <!-- ── ขั้น 3: ตรวจสอบ + เลือกรูปแบบการดำเนินการ ──────────────────────── -->
    <template v-else>
      <AppCard>
        <h2 class="text-title-m font-bold text-ink-1">ตรวจสอบก่อนส่ง</h2>
        <dl class="mt-4 divide-y divide-line">
          <div class="flex gap-3 py-2.5">
            <dt class="w-24 shrink-0 text-[13px] font-medium text-ink-2">ประเภท</dt>
            <dd class="min-w-0 flex-1 text-sm text-ink-1">
              {{ form.mainCategory ? MAIN_CATEGORY_LABELS[form.mainCategory] : '—' }}
              <span class="text-ink-2"> · {{ subcategoryText || '—' }}</span>
            </dd>
          </div>
          <div class="flex gap-3 py-2.5">
            <dt class="w-24 shrink-0 text-[13px] font-medium text-ink-2">หัวข้อ</dt>
            <dd class="min-w-0 flex-1 font-semibold break-words text-ink-1">
              {{ form.title.trim() || '—' }}
            </dd>
          </div>
          <div class="flex gap-3 py-2.5">
            <dt class="w-24 shrink-0 text-[13px] font-medium text-ink-2">รายละเอียด</dt>
            <dd class="min-w-0 flex-1 whitespace-pre-wrap break-words text-sm text-ink-1">
              {{ form.description.trim() || '—' }}
            </dd>
          </div>
          <div class="flex gap-3 py-2.5">
            <dt class="w-24 shrink-0 text-[13px] font-medium text-ink-2">ผู้แจ้ง</dt>
            <dd class="min-w-0 flex-1 text-sm text-ink-1">
              {{ form.isAnonymous ? 'ไม่ระบุตัวตน (ซ่อนชื่อผู้แจ้ง)' : 'แสดงชื่อจริง' }}
            </dd>
          </div>
          <div v-if="selectableLevels.length > 1" class="flex gap-3 py-2.5">
            <dt class="w-24 shrink-0 text-[13px] font-medium text-ink-2">ระดับเริ่มต้น</dt>
            <dd class="min-w-0 flex-1 text-sm text-ink-1">
              {{ levelLabel(form.startLevel) }}
            </dd>
          </div>
        </dl>

        <div class="mt-2 flex flex-wrap gap-2">
          <AppButton variant="text" size="sm" @click="goStep(1)">
            <template #icon><i class="bi bi-pencil" /></template>
            แก้ประเภท
          </AppButton>
          <AppButton variant="text" size="sm" @click="goStep(2)">
            <template #icon><i class="bi bi-pencil" /></template>
            แก้รายละเอียด
          </AppButton>
        </div>
      </AppCard>

      <!--
        🔴 **ไม่มีค่าเริ่มต้น** — ของเดิมตั้ง `'normal'` ไว้ก่อน ⇒ ผู้ใช้ที่อยากได้บอร์ดโหวต
           ต้องสังเกตเห็นแล้วเปลี่ยนเอง · คนที่ไม่อ่านจะได้เรื่องปกติโดยไม่รู้ว่ามีทางเลือกอื่น
      -->
      <AppCard>
        <h2 class="text-title-m font-bold text-ink-1">ต้องการให้เรื่องนี้ดำเนินการแบบไหน</h2>
        <div class="mt-3 grid grid-cols-1 gap-2">
          <button
            v-for="opt in DESTINATION_OPTIONS"
            :key="opt.value"
            type="button"
            :data-testid="'dest-' + opt.value"
            class="flex items-start gap-3 rounded-card border p-3 text-left transition-colors"
            :class="
              form.requestedDestination === opt.value
                ? 'border-brand bg-brand-tint'
                : 'border-line bg-surface hover:border-ink-3'
            "
            :aria-pressed="form.requestedDestination === opt.value"
            @click="pickDestination(opt.value)"
          >
            <i
              :class="[
                'bi',
                opt.icon,
                'mt-0.5 text-lg',
                form.requestedDestination === opt.value ? 'text-brand' : 'text-ink-2',
              ]"
              aria-hidden="true"
            />
            <span class="min-w-0">
              <span
                class="block text-sm font-semibold"
                :class="form.requestedDestination === opt.value ? 'text-brand' : 'text-ink-1'"
              >
                {{ opt.label }}
              </span>
              <span class="mt-0.5 block text-[13px] leading-relaxed text-ink-2">{{ opt.desc }}</span>
            </span>
          </button>
        </div>
        <p v-if="errorOf('destination')" class="mt-2 text-[13px] font-medium text-danger">
          {{ errorOf('destination') }}
        </p>
        <p
          v-if="wantsPublic"
          class="mt-3 flex gap-2 rounded-control bg-warn-soft p-2.5 text-[13px] leading-relaxed text-ink-1"
        >
          <i class="bi bi-info-circle mt-0.5 shrink-0" aria-hidden="true" />
          <span>
            เรื่องที่ขอเผยแพร่จะถูกส่งตรงไปยัง<b>สภานักเรียน</b>เพื่อพิจารณาอนุมัติเป็นบอร์ดสาธารณะ —
            ถ้าไม่ได้รับอนุมัติ เรื่องจะถูกปิด
          </span>
        </p>
      </AppCard>
    </template>

    <!-- ── แถบนำทางระหว่างขั้น ───────────────────────────────────────────── -->
    <div class="flex flex-col gap-2">
      <p v-if="!stepValid && nextHint" class="text-[13px] font-medium text-ink-2">
        {{ nextHint }}
      </p>
      <div class="flex gap-2">
        <AppButton
          v-if="step > 1"
          variant="secondary"
          @click="goStep((step - 1) as 1 | 2)"
        >
          <template #icon><i class="bi bi-arrow-left" /></template>
          ย้อนกลับ
        </AppButton>

        <AppButton
          v-if="step < 3"
          class="flex-1"
          :disabled="!stepValid"
          @click="onNext"
        >
          ถัดไป
          <template #icon><i class="bi bi-arrow-right" /></template>
        </AppButton>

        <AppButton
          v-else
          data-testid="issue-submit"
          class="flex-1"
          :disabled="!stepValid"
          :loading="isLoading"
          @click="handleSubmit"
        >
          <template #icon><i class="bi bi-send" /></template>
          {{ isLoading ? 'กำลังส่ง...' : 'ส่งเรื่อง' }}
        </AppButton>
      </div>

      <!-- สถานะร่าง — บอกว่ามีอะไรถูกเก็บไว้แล้ว ไม่ต้องเดา -->
      <p v-if="draftSavedAt && dirty" class="text-center text-[12px] text-ink-3">
        <i class="bi bi-cloud-check me-1" aria-hidden="true" />
        บันทึกร่างไว้ในเครื่องนี้แล้ว — กลับมาอีกครั้งกู้คืนได้
      </p>
    </div>
  </div>
</template>
