<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import Swal from 'sweetalert2'
import PaginationBar from '@/components/PaginationBar.vue'
// 🕐 เวลามาจากโมดูลกลาง — **ห้ามประกาศซ้ำในไฟล์นี้** (เดิมก๊อปอยู่ 4 ไฟล์แล้วเพี้ยนจากกัน)
import { fmtDateTime, fmtTime, toLocalInput } from '@/datetime'
import {
  cancelEvent,
  checkInRegistration,
  createEvent,
  deleteEvent,
  listEvents,
  listRegistrations,
  publishEvent,
  restoreEvent,
  updateEvent,
} from '@/services/event'
import {
  CATEGORY_LABELS,
  EVENT_CATEGORIES,
  EVENT_LIST_STATUSES,
  LIST_STATUS_LABELS,
  REGISTRATION_ICONS,
  REGISTRATION_LABELS,
  STATUS_ICONS,
  STATUS_LABELS,
  categoryIcon,
  categoryLabel,
  categoryPayload,
  isEventCategory,
  type Event,
  type EventCreate,
  type EventListStatus,
  type EventRegistration,
  type EventUpdate,
} from '@/types/event'

/**
 * 📅 จัดการกิจกรรม (สภา) — สร้าง/แก้/เผยแพร่/ยกเลิก/ลบ/กู้คืน + ดูรายชื่อผู้สมัคร
 *
 * ⚠️ **สถานะ `live` (ค่าเริ่มต้น) = "ทุกอย่างที่ยังไม่ถูกลบ"** ไม่ใช่สถานะจริงของแถว
 *    ⇒ ป้ายจะขึ้น "ทั้งหมด" ไม่ใช่ "live" (ดู `LIST_STATUS_LABELS`)
 *
 * ⚠️ **กิจกรรมที่ `draft` เปิดดูหน้าสาธารณะไม่ได้ (404)** ⇒ ปุ่ม "ดูหน้าสาธารณะ" จึงแสดงเฉพาะ
 *    `published`/`cancelled` เท่านั้น ไม่ใช่ซ่อนเพื่อความสวยงาม แต่เพราะลิงก์จะพาไปเจอ
 *    "เปิดดูไม่ได้" ซึ่งดูเหมือนบั๊กทั้งที่ระบบถูก
 *
 * ⚠️ **`<Teleport to="body">` ที่ modal ทั้งสองใบ จำเป็น ไม่ใช่ stylistic** — modal เรนเดอร์
 *    อยู่ใน stacking context `relative z-10` ของ `.maincol` ⇒ `z-50` ถูกกักที่ชั้น 10
 *    แล้วแพ้ `<nav>` (`fixed z-40`) ที่เป็นพี่น้องกัน ⇒ แถบล่างทับ **และกลืนคลิกปุ่มบันทึก**
 *    (บทเรียนจริงจาก PR #33/§14 — ห้ามถอด)
 */
const router = useRouter()

const PAGE_SIZE = 20
const REG_PAGE_SIZE = 20

const items = ref<Event[]>([])
const total = ref(0)
const page = ref(1)
const statusFilter = ref<EventListStatus>('live')
/**
 * ตัวกรองหมวด (D4) — **`''` = ทุกหมวด** (ไม่ใช่ `'other'` ซึ่งแปลว่า "เฉพาะหมวดอื่น ๆ")
 *
 * ⚠️ เก็บเป็น `string` เปล่าเพราะค่ามาจาก `<select>` (DOM ให้สตริงเสมอ) ⇒ ด่านแคบอยู่ที่
 *    `load()` ด้วย `isEventCategory()` ไม่ใช่ที่ type ของ ref
 *    · แบบเดียวกับ `subcategoryFilter` ใน `ReceivedIssues.vue` (`''` = ทุกหมวดย่อย)
 *
 * ⚠️ **ส่ง `''` ตรง ๆ ไม่ได้** — จะกลายเป็น `category=` ใน querystring ซึ่งไม่ตรง pattern
 *    ฝั่ง backend ⇒ **422** (ไม่ใช่ "ไม่กรอง") · ต้องแปลงเป็น `undefined` เสมอ
 */
const categoryFilter = ref('')
const isLoading = ref(true)
const hasError = ref(false)

/** id ของแถวที่กำลังยิงคำขอ + ชนิดคำขอ — ใช้แสดงสปินเนอร์เฉพาะปุ่มที่กด ไม่ล็อกทั้งตาราง */
const actingId = ref<number | null>(null)
const actingKind = ref<'publish' | 'cancel' | 'delete' | 'restore' | null>(null)

// ── modal สร้าง/แก้ไข ──
const modalOpen = ref(false)
const modalMode = ref<'add' | 'edit'>('add')
const editingId = ref<number | null>(null)
const saving = ref(false)
const saveError = ref('')
/** snapshot ของค่าตั้งต้น (รูปแบบเดียวกับฟอร์ม) — ใช้เทียบว่าผู้ใช้แก้อะไรจริง ⇒ PATCH ส่งแต่ที่ต่าง */
const baseline = ref<EventCreate | null>(null)

const form = ref({
  title: '',
  description: '',
  location: '',
  cover_image_url: '',
  event_date: '',
  registration_deadline: '',
  capacity: '',
  /**
   * ⚠️ ประกาศเป็น **`string` ไม่ใช่ `EventCategory`** โดยเจตนา — ค่ามันมาจาก `<select>` ที่
   *    เราเติมตัวเลือกแปลก ๆ เข้าไปได้ (ดู `categoryOptions`) ⇒ ถ้าประกาศแคบไว้ จะต้อง cast
   *    ตอนอ่านค่า ซึ่งกลบความจริงว่ามันอาจไม่ใช่คีย์ที่รู้จัก
   *    · ด่านจริงอยู่ที่ `buildCreate()` ซึ่งใช้ `isEventCategory()` แคบก่อนส่ง
   */
  category: 'other' as string,
})

// ── modal รายชื่อผู้สมัคร ──
const regOpen = ref(false)
const regEvent = ref<Event | null>(null)
const regs = ref<EventRegistration[]>([])
const regTotal = ref(0)
const regPage = ref(1)
const regLoading = ref(false)
const regError = ref('')
/**
 * id ของแถวที่กำลังเช็คอินอยู่ (D2) — **เก็บเป็น id ต่อแถว ไม่ใช่ boolean ของทั้ง modal**
 *
 * ⭐ เก็บ id เพื่อให้ **สปินเนอร์ขึ้นที่แถวที่กดเท่านั้น** — ถ้าใช้ boolean ปุ่มทุกแถวจะหมุนพร้อมกัน
 *    แล้วสภาไม่รู้ว่าแถวไหนกำลังทำงาน (ตอนเลื่อนหารายชื่อในคิวที่ยาว อันนี้สำคัญ)
 *
 * ⚠️ **แต่การล็อกเป็นของทั้ง modal โดยเจตนา** (`:disabled="regActingId !== null"`) — *ไม่ใช่*
 *    การเช็คอินหลายคนพร้อมกัน · เพราะทุกครั้งที่สำเร็จจะ `loadRegistrations()` ใหม่ทั้งชุด
 *    ⇒ สองคำขอที่ทับกันจะโหลดชนกัน แล้วรายชื่อที่ได้อาจเป็นชุดก่อนการเช็คอินอีกคน
 *    (ป้ายสถานะกับความจริงไม่ตรงกันชั่วขณะ ซึ่งสภาจะอ่านว่า "กดไม่ติด")
 *    · ราคาที่จ่ายคือรอ ~200 ms ต่อคน ซึ่งไม่ใช่คอขวดของงานจริง (คอขวดคือคนเดินมาถึงประตู)
 *    · งานที่ต้องเร็วระดับนั้นคือ **หน้าสแกน** ซึ่งทำงานคนละแบบ (ไม่มีรายชื่อให้โหลดซ้ำ)
 */
const regActingId = ref<number | null>(null)

const isEmpty = computed(() => !isLoading.value && !hasError.value && items.value.length === 0)

/**
 * ข้อความตอนว่าง — **ต้องแยกให้ออกว่า "ไม่มีของ" กับ "ตัวกรองซ่อนอยู่"**
 *
 * ⚠️ ทั้งสองกรณีแสดงผลเหมือนกันเป๊ะ (การ์ด 0 ใบ) แต่ความหมายตรงข้าม: กรณีหลังของ *มีอยู่จริง*
 *    ⇒ ข้อความกลาง ๆ อย่าง "ยังไม่มีกิจกรรมในระบบ" จะทำให้สภาตกใจแล้วไปสร้างซ้ำ
 */
const emptyText = computed(() => {
  if (categoryFilter.value) {
    return `ไม่มีกิจกรรมในหมวด "${categoryLabel(categoryFilter.value)}" ตามตัวกรองที่เลือก`
  }
  return statusFilter.value === 'live' ? 'ยังไม่มีกิจกรรมในระบบ' : 'ไม่มีกิจกรรมในสถานะนี้'
})

const formError = computed(() => {
  if (!form.value.title.trim()) return 'ต้องกรอกชื่อกิจกรรม'
  if (!form.value.event_date) return 'ต้องเลือกวันและเวลาจัดกิจกรรม'
  const cap = form.value.capacity.trim()
  if (cap !== '') {
    const n = Number(cap)
    if (!Number.isInteger(n) || n < 1) return 'จำนวนที่นั่งต้องเป็นจำนวนเต็มตั้งแต่ 1 ขึ้นไป'
  }
  return ''
})

onMounted(load)

function errText(e: unknown): string {
  if (typeof e === 'string') return e
  if (e instanceof Error) return e.message
  return 'เกิดข้อผิดพลาดที่ไม่รู้จัก'
}

async function load() {
  isLoading.value = true
  hasError.value = false
  try {
    const res = await listEvents({
      status: statusFilter.value,
      category: isEventCategory(categoryFilter.value) ? categoryFilter.value : undefined,
      limit: PAGE_SIZE,
      offset: (page.value - 1) * PAGE_SIZE,
    })
    items.value = res.items
    total.value = res.total
    // ⚠️ หน้าที่ว่างเปล่าต้องถอยกลับ ไม่ใช่ปล่อยค้าง — หลังลบ/กู้คืนแถวสุดท้ายของหน้าสุดท้าย
    //    หน้านี้จะไม่มีอะไรเหลือ และ **`<PaginationBar>` หายไปด้วย** เพราะมันอยู่ในกิ่ง
    //    `v-else` ของรายการ ⇒ ถ้าไม่ถอย ผู้ใช้จะไม่มีทางกลับไปดูแถวที่เหลือได้เลย
    //    (วางไว้ที่เดียวตรงนี้แทนการไล่ใส่หลังทุก mutation เพราะครอบทั้งลบ/กู้คืน/สร้าง)
    if (items.value.length === 0 && page.value > 1) {
      page.value -= 1
      await load()
    }
  } catch {
    hasError.value = true
    items.value = []
    total.value = 0
  } finally {
    isLoading.value = false
  }
}

function switchStatus(s: EventListStatus) {
  if (statusFilter.value === s) return
  statusFilter.value = s
  page.value = 1
  load()
}

/** เปลี่ยนหมวด ⇒ กลับไปหน้า 1 เสมอ (ไม่งั้นอาจค้างอยู่หน้า 3 ของผลลัพธ์ชุดใหม่ที่สั้นกว่า) */
function onCategoryChange() {
  page.value = 1
  load()
}

/** ปุ่มในสถานะว่าง — ล้างตัวกรองหมวด **แล้วโหลดใหม่** (ไม่ใช่แค่เคลียร์ค่าแล้วรอ) */
function clearCategoryFilter() {
  categoryFilter.value = ''
  page.value = 1
  load()
}

/**
 * ตัวเลือกใน `<select>` ของฟอร์ม — ปกติคือ `EVENT_CATEGORIES` ทั้งชุด
 *
 * ⭐ **แต่ถ้าหมวดของแถวที่กำลังแก้ไม่ใช่คีย์ที่ frontend รู้จัก** (backend ใหม่กว่า) ต้องเติม
 *    ค่านั้นเข้าไปเป็นตัวเลือก ไม่งั้น `<select>` จะแสดง **ว่าง** แล้วถ้าผู้ใช้กดบันทึก
 *    ค่าจะกลายเป็น `'other'` เงียบ ๆ — คือ **ลดชั้นข้อมูลโดยที่ผู้ใช้ไม่ได้สั่ง**
 *    (และคู่กับ `buildCreate()` ที่ไม่ส่งคีย์แปลกออกไป ⇒ ค่าเดิมใน DB ไม่ถูกแตะ)
 */
const categoryOptions = computed<readonly { value: string; label: string }[]>(() => {
  const known: { value: string; label: string }[] = EVENT_CATEGORIES.map((c) => ({
    value: c,
    label: CATEGORY_LABELS[c],
  }))
  const current = form.value.category
  return isEventCategory(current)
    ? known
    : [{ value: current, label: `${current} (ไม่รู้จัก)` }, ...known]
})

function onPageChange(n: number) {
  page.value = n
  load()
}

function busy(e: Event, kind: 'publish' | 'cancel' | 'delete' | 'restore'): boolean {
  return actingId.value === e.id && actingKind.value === kind
}

async function runAction(e: Event, kind: 'publish' | 'cancel' | 'delete' | 'restore') {
  if (actingId.value !== null) return
  actingId.value = e.id
  actingKind.value = kind
  try {
    if (kind === 'publish') {
      const res = await Swal.fire({
        title: 'เผยแพร่กิจกรรมนี้?',
        html:
          'เมื่อเผยแพร่แล้ว <b>นักเรียนทุกคนจะได้รับการแจ้งเตือน</b><br>' +
          '<span class="text-sm text-stone-500">และแก้ไขกลับเป็นฉบับร่างไม่ได้</span>',
        icon: 'question',
        showCancelButton: true,
        confirmButtonText: 'เผยแพร่เลย',
        confirmButtonColor: '#B91C1C',
        cancelButtonText: 'ยกเลิก',
      })
      if (!res.isConfirmed) return
      await publishEvent(e.id)
      await load()
      Swal.fire({ icon: 'success', title: 'เผยแพร่แล้ว', timer: 1200, showConfirmButton: false })
    } else if (kind === 'cancel') {
      const res = await Swal.fire({
        title: 'ยกเลิกกิจกรรมนี้?',
        html:
          'กิจกรรมจะยังเปิดดูได้ แต่ปิดรับสมัครทันที<br>' +
          `<span class="text-sm text-stone-500">คนแรกในคิวสำรอง${
            e.waitlisted_count > 0 ? ` (${e.waitlisted_count} คน)` : ''
          } จะไม่ถูกเลื่อนขึ้น — การยกเลิกไม่ใช่การลบ</span>`,
        icon: 'warning',
        showCancelButton: true,
        confirmButtonText: 'ยกเลิกกิจกรรม',
        confirmButtonColor: '#B91C1C',
        cancelButtonText: 'ไม่ยกเลิก',
      })
      if (!res.isConfirmed) return
      await cancelEvent(e.id)
      await load()
      Swal.fire({ icon: 'success', title: 'ยกเลิกกิจกรรมแล้ว', timer: 1200, showConfirmButton: false })
    } else if (kind === 'delete') {
      const res = await Swal.fire({
        title: 'ลบกิจกรรมนี้?',
        html:
          `«${e.title}»<br>` +
          `<span class="text-sm text-stone-500">ผู้สมัคร ${e.registered_count} คนจะถูกลบไปด้วย · กู้คืนได้จากตัวกรอง "ถูกลบ"</span>`,
        icon: 'warning',
        showCancelButton: true,
        confirmButtonText: 'ลบกิจกรรม',
        confirmButtonColor: '#b91c1c',
        cancelButtonText: 'ไม่ลบ',
      })
      if (!res.isConfirmed) return
      await deleteEvent(e.id)
      await load()
      Swal.fire({ icon: 'success', title: 'ลบแล้ว', timer: 1000, showConfirmButton: false })
    } else {
      await restoreEvent(e.id)
      await load()
      Swal.fire({ icon: 'success', title: 'กู้คืนแล้ว', timer: 1000, showConfirmButton: false })
    }
  } catch (err) {
    Swal.fire({ icon: 'error', title: 'ดำเนินการไม่สำเร็จ', text: errText(err) })
  } finally {
    actingId.value = null
    actingKind.value = null
  }
}

/** ค่าฟอร์ม → payload สร้าง · ช่องว่างของฟิลด์ที่ไม่บังคับ = `null` (สั่งล้างค่า) ไม่ใช่ `undefined` */
function buildCreate(): EventCreate {
  const cap = form.value.capacity.trim()
  return {
    title: form.value.title.trim(),
    description: form.value.description.trim() || null,
    location: form.value.location.trim() || null,
    cover_image_url: form.value.cover_image_url.trim() || null,
    event_date: form.value.event_date,
    registration_deadline: form.value.registration_deadline || null,
    capacity: cap === '' ? null : Number(cap),
    // คีย์ที่ไม่รู้จัก ⇒ `undefined` = ไม่ส่ง (ดู `categoryPayload`) — ไม่เดาว่าเป็น 'other'
    category: categoryPayload(form.value.category),
  }
}

/** ค่าของแถว → รูปแบบเดียวกับฟอร์ม เพื่อใช้เป็นฐานเทียบว่าผู้ใช้แก้อะไร */
function toBaseline(e: Event): EventCreate {
  return {
    title: e.title,
    description: e.description,
    location: e.location,
    cover_image_url: e.cover_image_url,
    event_date: toLocalInput(e.event_date),
    registration_deadline: toLocalInput(e.registration_deadline),
    capacity: e.capacity,
    // ⚠️ ต้องใช้ `categoryPayload()` ตัวเดียวกับ `buildCreate()` — คีย์แปลกจะได้ `undefined`
    //    **ทั้งสองข้าง** ⇒ diff ไม่เห็นว่าต่าง ⇒ ไม่ยิง PATCH ⇒ ค่าเดิมใน DB ไม่ถูกทับ
    category: categoryPayload(e.category),
  }
}

function openAdd() {
  modalMode.value = 'add'
  editingId.value = null
  baseline.value = null
  saveError.value = ''
  form.value = {
    title: '',
    description: '',
    location: '',
    cover_image_url: '',
    event_date: '',
    registration_deadline: '',
    capacity: '',
    category: 'other',
  }
  modalOpen.value = true
}

function openEdit(e: Event) {
  modalMode.value = 'edit'
  editingId.value = e.id
  const base = toBaseline(e)
  baseline.value = base
  saveError.value = ''
  form.value = {
    title: base.title,
    description: base.description ?? '',
    location: base.location ?? '',
    cover_image_url: base.cover_image_url ?? '',
    event_date: base.event_date,
    registration_deadline: base.registration_deadline ?? '',
    capacity: base.capacity === null ? '' : String(base.capacity),
    // ⚠️ อ่านจาก **แถวจริง** (`e.category`) ไม่ใช่ `base.category` — คีย์แปลกต้องไม่ถูกแปลง
    //    เป็น 'other' ตั้งแต่เปิดฟอร์ม (ดู `categoryOptions` ที่เติมตัวเลือกนั้นให้)
    category: e.category,
  }
  modalOpen.value = true
}

function closeModal() {
  modalOpen.value = false
  saveError.value = ''
}

/**
 * PATCH ส่ง **เฉพาะฟิลด์ที่ต่างจากเดิม** (กฎโปรเจค: `exclude_unset` ฝั่ง backend)
 * ⇒ ไม่เขียนทับคอลัมน์ที่ผู้ใช้ไม่ได้แตะ และ audit log บันทึกแต่ของจริงที่เปลี่ยน
 */
function buildPatch(): EventUpdate {
  const next = buildCreate()
  const base = baseline.value
  const patch: EventUpdate = {}
  if (!base) return next
  if (base.title !== next.title) patch.title = next.title
  if (base.description !== next.description) patch.description = next.description
  if (base.location !== next.location) patch.location = next.location
  if (base.cover_image_url !== next.cover_image_url) patch.cover_image_url = next.cover_image_url
  if (base.event_date !== next.event_date) patch.event_date = next.event_date
  if (base.registration_deadline !== next.registration_deadline) {
    patch.registration_deadline = next.registration_deadline
  }
  if (base.capacity !== next.capacity) patch.capacity = next.capacity
  if (base.category !== next.category) patch.category = next.category
  return patch
}

async function save() {
  if (formError.value || saving.value) return
  const mode = modalMode.value
  const id = editingId.value
  saving.value = true
  saveError.value = ''
  try {
    if (mode === 'add') {
      await createEvent(buildCreate())
    } else {
      const patch = buildPatch()
      // ไม่มีอะไรเปลี่ยน = ไม่ต้องยิง API เลย (ผู้ใช้อาจเปิดฟอร์มแล้วปิดโดยไม่แก้)
      if (id === null || Object.keys(patch).length === 0) {
        closeModal()
        return
      }
      await updateEvent(id, patch)
    }
    closeModal()
    await load()
    Swal.fire({
      icon: 'success',
      title: mode === 'add' ? 'สร้างกิจกรรมแล้ว' : 'บันทึกแล้ว',
      text: mode === 'add' ? 'กิจกรรมถูกสร้างเป็นฉบับร่าง — ยังไม่มีใครเห็น' : undefined,
      timer: mode === 'add' ? 1800 : 1200,
      showConfirmButton: false,
    })
  } catch (e) {
    // ฟอร์มเปิดค้างไว้พร้อมข้อความ — ผู้ใช้ไม่ต้องพิมพ์ใหม่ทั้งหมด
    // (client ตรวจไปชั้นหนึ่งแล้ว แต่ backend ตรวจซ้ำและเป็นผู้ตัดสินจริง)
    saveError.value = errText(e)
  } finally {
    saving.value = false
  }
}

async function openRegistrations(e: Event) {
  regEvent.value = e
  regPage.value = 1
  regOpen.value = true
  await loadRegistrations()
}

async function loadRegistrations() {
  if (!regEvent.value) return
  regLoading.value = true
  regError.value = ''
  try {
    const res = await listRegistrations(regEvent.value.id, {
      limit: REG_PAGE_SIZE,
      offset: (regPage.value - 1) * REG_PAGE_SIZE,
    })
    regs.value = res.items
    regTotal.value = res.total
    if (regs.value.length === 0 && regPage.value > 1) {
      regPage.value -= 1
      await loadRegistrations()
    }
  } catch (e) {
    regError.value = errText(e)
    regs.value = []
    regTotal.value = 0
  } finally {
    regLoading.value = false
  }
}

function onRegPageChange(n: number) {
  regPage.value = n
  loadRegistrations()
}

function closeRegistrations() {
  regOpen.value = false
  regEvent.value = null
  regs.value = []
  regTotal.value = 0
}

/**
 * เช็คอินจากรายชื่อ (D2) — **ทางสำรองที่ต้องมีเสมอ**
 *
 * ใช้เมื่อนักเรียนลืมมือถือ/แบตหมด/กล้องสภาไม่ทำงาน — ซึ่งเกิดทุกงาน และเกิดในวันที่
 * แก้ไขอะไรไม่ได้ ⇒ ปุ่มนี้คือเหตุผลที่ endpoint รับ `registration_id` ได้ด้วย ไม่ใช่แค่โทเคน
 *
 * ⚠️ **`already_checked_in` ไม่ใช่ error** — สแกนซ้ำ/กดซ้ำเป็นเรื่องปกติ ⇒ แสดงเป็นข้อความ
 *    "เช็คอินไปแล้วเมื่อ HH:MM" ไม่ใช่แจ้งเตือนสีแดง (เหตุผลเดียวกับฝั่งหน้าสแกน)
 */
async function handleCheckIn(r: EventRegistration) {
  if (!regEvent.value || regActingId.value !== null) return
  regActingId.value = r.id
  try {
    const res = await checkInRegistration(regEvent.value.id, { registration_id: r.id })
    // โหลดรายชื่อใหม่เพื่อให้ป้ายสถานะ/เวลาเป็นค่าที่ server เขียนจริง ไม่ใช่การเดาที่ frontend
    await loadRegistrations()

    const who = res.user_name ?? `ผู้ใช้ #${res.user_id}`
    const when = res.checked_in_at ? `เมื่อ ${fmtTime(res.checked_in_at)} น.` : ''
    // ⚠️ ใช้ `text:` **ไม่ใช่ `html:`** — `who` คือชื่อที่ผู้ใช้ตั้งเองได้ (หน้า ProfileEdit)
    //    ⇒ ใส่ลง `html` เมื่อไร ชื่ออย่าง `<img src=x onerror=...>` จะรันในเบราว์เซอร์สภา
    //    · SweetAlert2 ใส่ `text` ด้วย `textContent` จึงปลอดภัยโดยธรรมชาติ
    if (res.already_checked_in) {
      await Swal.fire({
        icon: 'info',
        title: 'คนนี้เช็คอินไปแล้ว',
        text: when ? `${who} · ${when} · เวลาเดิม ไม่ได้นับซ้ำ` : who,
        confirmButtonText: 'เข้าใจแล้ว',
        confirmButtonColor: '#B91C1C',
      })
    } else {
      await Swal.fire({
        icon: 'success',
        title: 'เช็คอินสำเร็จ',
        text: when ? `${who} · ${when}` : who,
        timer: 1600,
        showConfirmButton: false,
      })
    }
  } catch (e) {
    await Swal.fire({ icon: 'error', title: 'เช็คอินไม่สำเร็จ', text: errText(e) })
  } finally {
    regActingId.value = null
  }
}

function capacityText(e: Event): string {
  return e.capacity === null ? 'ไม่จำกัด' : `${e.capacity.toLocaleString('en-US')} ที่นั่ง`
}
</script>

<template>
  <div>
    <!-- Editorial header -->
    <div class="mb-6 flex flex-wrap items-start justify-between gap-3">
      <div class="w-full min-w-0 sm:w-auto sm:flex-1">
        <p class="text-[11px] font-bold uppercase tracking-widest text-[#B91C1C] mb-1.5">
          <i class="bi bi-calendar-event mr-1"></i> Events
        </p>
        <h1 class="text-2xl sm:text-3xl font-bold tracking-tight text-stone-900 leading-tight">
          จัดการกิจกรรม
        </h1>
        <p class="text-sm text-stone-500 mt-1.5">
          สร้างกิจกรรม เปิดรับสมัคร และดูรายชื่อผู้เข้าร่วม
        </p>
      </div>
      <button
        type="button"
        data-testid="add-event"
        @click="openAdd"
        class="inline-flex w-full items-center justify-center gap-1.5 rounded-xl bg-[#B91C1C] px-4 py-2.5 text-sm font-bold text-white shadow-md transition-all hover:bg-[#991B1B] hover:shadow-lg active:scale-[0.97] sm:w-auto sm:shrink-0"
      >
        <i class="bi bi-plus-lg"></i> สร้างกิจกรรม
      </button>
    </div>

    <!-- แถบกรองสถานะ -->
    <div class="mb-5 flex flex-wrap items-center gap-2">
      <div class="flex flex-wrap gap-1 rounded-xl bg-stone-100 p-1">
        <button
          v-for="s in EVENT_LIST_STATUSES"
          :key="s"
          type="button"
          @click="switchStatus(s)"
          class="rounded-lg px-3.5 py-2 text-sm font-medium transition"
          :class="
            statusFilter === s
              ? 'border border-stone-200 bg-white text-[#B91C1C]'
              : 'text-stone-500 hover:text-stone-700'
          "
        >
          {{ LIST_STATUS_LABELS[s] }}
        </button>
      </div>

      <!-- ตัวกรองหมวด (D4) — ใช้ <select> ไม่ใช่ชิป เพราะ 7 หมวดจะไปเบียดแถวสถานะจนอ่านไม่ออก -->
      <select
        v-model="categoryFilter"
        aria-label="กรองตามหมวดกิจกรรม"
        data-testid="category-filter"
        class="rounded-xl border border-stone-200 bg-white px-3 py-2 text-sm text-stone-700 outline-none transition-colors focus:border-[#B91C1C] focus:ring-2 focus:ring-[#B91C1C]/10"
        @change="onCategoryChange"
      >
        <option value="">ทุกหมวด</option>
        <option v-for="c in EVENT_CATEGORIES" :key="c" :value="c">
          {{ CATEGORY_LABELS[c] }}
        </option>
      </select>

      <span class="ml-auto text-sm tabular-nums text-stone-400">
        {{ total.toLocaleString('en-US') }} กิจกรรม
      </span>
    </div>

    <!-- โหลด -->
    <div v-if="isLoading" class="space-y-3">
      <div v-for="n in 4" :key="n" class="rounded-2xl bg-white p-5 ring-1 ring-stone-200">
        <div class="mb-3 h-5 w-24 animate-pulse rounded-md bg-stone-100"></div>
        <div class="mb-2 h-5 w-2/3 animate-pulse rounded bg-stone-100"></div>
        <div class="h-4 w-1/2 animate-pulse rounded bg-stone-100"></div>
      </div>
    </div>

    <!-- ผิดพลาด -->
    <div
      v-else-if="hasError"
      class="rounded-2xl border-2 border-dashed border-stone-200 px-6 py-20 text-center"
    >
      <i class="bi bi-wifi-off mb-3 inline-block text-3xl text-stone-300"></i>
      <p class="font-medium text-stone-600">โหลดรายการกิจกรรมไม่สำเร็จ</p>
      <button
        type="button"
        @click="load"
        class="mt-5 inline-flex items-center gap-2 rounded-lg bg-[#B91C1C] px-5 py-2.5 text-sm font-bold text-white transition-colors hover:bg-[#991B1B]"
      >
        <i class="bi bi-arrow-clockwise"></i> ลองอีกครั้ง
      </button>
    </div>

    <!-- ว่าง -->
    <div
      v-else-if="isEmpty"
      class="rounded-2xl border border-dashed border-stone-200 bg-white p-12 text-center text-stone-400"
    >
      <div class="mb-2 text-4xl"><i class="bi bi-calendar-plus"></i></div>
      <p class="text-stone-500">
        {{ emptyText }}
      </p>
      <p v-if="statusFilter === 'live' && !categoryFilter" class="mt-1 text-sm text-stone-400">
        เริ่มจากกด "สร้างกิจกรรม" แล้วเผยแพร่ให้นักเรียนเห็น
      </p>
      <!-- ⚠️ ต้องบอกทางออกเมื่อ "ว่างเพราะตัวกรอง" — ไม่งั้นสภาจะอ่านว่า "กิจกรรมหายไปหมด"
           แล้วไปสร้างซ้ำ ซึ่งเป็นความเสียหายจริง (ไม่ใช่แค่ข้อความไม่สวย) -->
      <button
        v-else-if="categoryFilter"
        type="button"
        data-testid="clear-category-filter"
        class="mt-4 inline-flex items-center gap-2 rounded-lg bg-stone-100 px-4 py-2 text-sm font-semibold text-stone-700 transition-colors hover:bg-stone-200"
        @click="clearCategoryFilter"
      >
        <i class="bi bi-x-lg"></i> ล้างตัวกรองหมวด ({{ categoryLabel(categoryFilter) }})
      </button>
    </div>

    <!-- รายการ -->
    <div v-else class="space-y-3">
      <div v-for="e in items" :key="e.id" class="rounded-2xl bg-white p-5 ring-1 ring-stone-200">
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div class="w-full min-w-0 sm:w-auto sm:flex-1">
            <!-- สถานะ + ตัวเลข -->
            <div class="mb-1.5 flex flex-wrap items-center gap-2">
              <span
                class="inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-[11px] font-semibold"
                :class="{
                  'bg-stone-100 text-stone-600': e.status === 'draft',
                  'bg-emerald-50 text-emerald-700': e.status === 'published',
                  'bg-red-50 text-red-700': e.status === 'cancelled',
                }"
              >
                <i :class="`bi ${STATUS_ICONS[e.status]}`"></i> {{ STATUS_LABELS[e.status] }}
              </span>
              <!-- หมวด (D4) — ใช้ categoryLabel/categoryIcon ไม่ใช่ CATEGORY_LABELS[c] ตรง ๆ
                   เพราะ e.category เป็น string หลวม (backend อาจมีหมวดที่เราไม่รู้จัก) -->
              <span
                class="inline-flex items-center gap-1 rounded-md bg-sky-50 px-2 py-0.5 text-[11px] font-semibold text-sky-700"
              >
                <i :class="`bi ${categoryIcon(e.category)}`"></i> {{ categoryLabel(e.category) }}
              </span>
              <span
                v-if="e.deleted_at"
                class="inline-flex items-center gap-1 rounded-md bg-amber-50 px-2 py-0.5 text-[11px] font-semibold text-amber-700"
              >
                <i class="bi bi-trash3"></i> ถูกลบ
              </span>
              <span class="text-[11px] text-stone-400 tabular-nums">
                สมัคร {{ e.registered_count.toLocaleString('en-US') }} คน
                <template v-if="e.waitlisted_count > 0">
                  · รอคิว {{ e.waitlisted_count.toLocaleString('en-US') }} คน
                </template>
              </span>
            </div>

            <h3 class="font-semibold leading-snug text-stone-900 break-words">{{ e.title }}</h3>

            <div class="mt-1.5 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-stone-500">
              <span><i class="bi bi-clock mr-1"></i>{{ fmtDateTime(e.event_date) }}</span>
              <span v-if="e.location" class="min-w-0 truncate">
                <i class="bi bi-geo-alt mr-1"></i>{{ e.location }}
              </span>
              <span><i class="bi bi-people mr-1"></i>{{ capacityText(e) }}</span>
              <span v-if="e.created_by_name">
                <i class="bi bi-person mr-1"></i>สร้างโดย {{ e.created_by_name }}
              </span>
            </div>
          </div>

          <!-- ปุ่มจัดการ — ห่อ flex-wrap ให้มือถือไม่บีบจนตัวหนังสือขึ้นบรรทัดละตัว -->
          <div class="flex w-full flex-wrap items-center gap-1.5 sm:w-auto sm:shrink-0">
            <!-- เผยแพร่ได้ครั้งเดียว: draft → published -->
            <button
              v-if="e.status === 'draft' && !e.deleted_at"
              type="button"
              :disabled="actingId !== null"
              @click="runAction(e, 'publish')"
              class="rounded-lg bg-[#B91C1C] px-3 py-1.5 text-xs font-bold text-white transition-colors hover:bg-[#991B1B] disabled:opacity-50"
            >
              <i :class="busy(e, 'publish') ? 'bi bi-arrow-repeat animate-spin' : 'bi bi-megaphone'"></i>
              เผยแพร่
            </button>

            <!-- ยกเลิกได้เฉพาะที่เผยแพร่แล้ว -->
            <button
              v-if="e.status === 'published' && !e.deleted_at"
              type="button"
              :disabled="actingId !== null"
              @click="runAction(e, 'cancel')"
              class="rounded-lg bg-white px-3 py-1.5 text-xs font-semibold text-amber-700 ring-1 ring-amber-200 transition-colors hover:bg-amber-50 disabled:opacity-50"
            >
              <i :class="busy(e, 'cancel') ? 'bi bi-arrow-repeat animate-spin' : 'bi bi-x-octagon'"></i>
              ยกเลิก
            </button>

            <button
              v-if="!e.deleted_at"
              type="button"
              :disabled="actingId !== null"
              @click="openEdit(e)"
              class="rounded-lg bg-stone-100 px-3 py-1.5 text-xs font-semibold text-stone-700 transition-colors hover:bg-stone-200 disabled:opacity-50"
            >
              <i class="bi bi-pencil"></i> แก้ไข
            </button>

            <!-- ฉบับร่างยังไม่มีผู้สมัครโดยธรรมชาติ ⇒ ไม่ต้องมีปุ่มนี้ -->
            <button
              v-if="e.status !== 'draft' && !e.deleted_at"
              type="button"
              @click="openRegistrations(e)"
              class="rounded-lg bg-stone-100 px-3 py-1.5 text-xs font-semibold text-stone-700 transition-colors hover:bg-stone-200"
            >
              <i class="bi bi-list-check"></i> ผู้สมัคร
            </button>

            <!-- ⚠️ draft เปิดดูสาธารณะไม่ได้ (404) ⇒ ลิงก์เฉพาะที่เปิดได้จริง -->
            <button
              v-if="e.status !== 'draft' && !e.deleted_at"
              type="button"
              @click="router.push({ name: 'event-detail', params: { id: e.id } })"
              class="rounded-lg bg-stone-100 px-3 py-1.5 text-xs font-semibold text-stone-700 transition-colors hover:bg-stone-200"
            >
              <i class="bi bi-box-arrow-up-right"></i> ดูหน้าเว็บ
            </button>

            <button
              v-if="!e.deleted_at"
              type="button"
              :disabled="actingId !== null"
              @click="runAction(e, 'delete')"
              class="rounded-lg bg-white px-3 py-1.5 text-xs font-semibold text-red-600 ring-1 ring-red-200 transition-colors hover:bg-red-50 disabled:opacity-50"
            >
              <i :class="busy(e, 'delete') ? 'bi bi-arrow-repeat animate-spin' : 'bi bi-trash3'"></i>
              ลบ
            </button>

            <button
              v-else
              type="button"
              :disabled="actingId !== null"
              @click="runAction(e, 'restore')"
              class="rounded-lg bg-white px-3 py-1.5 text-xs font-semibold text-[#B45309] ring-1 ring-amber-200 transition-colors hover:bg-amber-50 disabled:opacity-50"
            >
              <i :class="busy(e, 'restore') ? 'bi bi-arrow-repeat animate-spin' : 'bi bi-arrow-counterclockwise'"></i>
              กู้คืน
            </button>
          </div>
        </div>
      </div>
    </div>

    <PaginationBar
      :total="total"
      :page="page"
      :page-size="PAGE_SIZE"
      :loading="isLoading"
      @page-change="onPageChange"
    />

    <!-- ════════ modal สร้าง/แก้ไข ════════ -->
    <Teleport to="body">
      <Transition name="sheet">
        <div
          v-if="modalOpen"
          class="fixed inset-0 z-50 flex items-end justify-center sm:items-center"
          role="dialog"
          aria-modal="true"
        >
          <div class="absolute inset-0 bg-stone-900/40 backdrop-blur-sm" @click="closeModal"></div>

          <div
            class="relative z-10 mx-auto flex max-h-[92vh] w-full max-w-lg flex-col overflow-hidden rounded-t-[1.5rem] bg-white shadow-2xl sm:rounded-[1.5rem]"
          >
            <div class="flex items-center justify-between border-b border-stone-100 px-5 py-4">
              <h2 class="text-base font-bold text-stone-900">
                {{ modalMode === 'add' ? 'สร้างกิจกรรม' : 'แก้ไขกิจกรรม' }}
              </h2>
              <button
                type="button"
                @click="closeModal"
                class="rounded-lg p-1.5 text-stone-400 transition-colors hover:bg-stone-100 hover:text-stone-600"
                aria-label="ปิด"
              >
                <i class="bi bi-x-lg"></i>
              </button>
            </div>

            <div class="custom-scrollbar flex-1 space-y-4 overflow-y-auto px-5 py-4">
              <div v-if="modalMode === 'add'" class="rounded-xl bg-stone-50 px-3.5 py-3 text-[12px] text-stone-500">
                <i class="bi bi-info-circle mr-1"></i>
                กิจกรรมจะถูกสร้างเป็น <b>ฉบับร่าง</b> — นักเรียนยังไม่เห็นจนกว่าจะกด "เผยแพร่"
              </div>

              <div>
                <label for="ev-title" class="mb-1 block text-xs font-semibold text-stone-500">
                  ชื่อกิจกรรม <span class="text-red-500">*</span>
                </label>
                <input
                  id="ev-title"
                  v-model="form.title"
                  type="text"
                  maxlength="200"
                  placeholder="เช่น กิจกรรมวันวิทยาศาสตร์"
                  class="w-full rounded-xl border border-stone-200 px-3.5 py-2.5 text-sm text-stone-800 outline-none transition-colors focus:border-[#B91C1C] focus:ring-2 focus:ring-[#B91C1C]/10"
                />
              </div>

              <div>
                <label for="ev-desc" class="mb-1 block text-xs font-semibold text-stone-500">
                  รายละเอียด
                </label>
                <textarea
                  id="ev-desc"
                  v-model="form.description"
                  rows="3"
                  placeholder="อธิบายกิจกรรมสั้น ๆ ให้นักเรียนรู้ว่าต้องเตรียมอะไร"
                  class="w-full resize-y rounded-xl border border-stone-200 px-3.5 py-2.5 text-sm text-stone-800 outline-none transition-colors focus:border-[#B91C1C] focus:ring-2 focus:ring-[#B91C1C]/10"
                ></textarea>
              </div>

              <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div>
                  <label for="ev-date" class="mb-1 block text-xs font-semibold text-stone-500">
                    วันและเวลาจัด <span class="text-red-500">*</span>
                  </label>
                  <input
                    id="ev-date"
                    v-model="form.event_date"
                    type="datetime-local"
                    class="w-full rounded-xl border border-stone-200 px-3.5 py-2.5 text-sm text-stone-800 outline-none transition-colors focus:border-[#B91C1C] focus:ring-2 focus:ring-[#B91C1C]/10"
                  />
                </div>
                <div>
                  <label for="ev-deadline" class="mb-1 block text-xs font-semibold text-stone-500">
                    ปิดรับสมัคร
                  </label>
                  <input
                    id="ev-deadline"
                    v-model="form.registration_deadline"
                    type="datetime-local"
                    class="w-full rounded-xl border border-stone-200 px-3.5 py-2.5 text-sm text-stone-800 outline-none transition-colors focus:border-[#B91C1C] focus:ring-2 focus:ring-[#B91C1C]/10"
                  />
                  <p class="mt-1 text-[11px] text-stone-400">เว้นว่างได้ — ระบบจะปิดรับเมื่อถึงเวลาจัด</p>
                </div>
              </div>

              <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div>
                  <label for="ev-capacity" class="mb-1 block text-xs font-semibold text-stone-500">
                    จำนวนที่นั่ง
                  </label>
                  <input
                    id="ev-capacity"
                    v-model="form.capacity"
                    type="number"
                    min="1"
                    step="1"
                    placeholder="เว้นว่าง = ไม่จำกัด"
                    class="w-full rounded-xl border border-stone-200 px-3.5 py-2.5 text-sm text-stone-800 outline-none transition-colors focus:border-[#B91C1C] focus:ring-2 focus:ring-[#B91C1C]/10"
                  />
                  <p class="mt-1 text-[11px] text-stone-400">
                    ที่นั่งเต็มแล้วระบบจะเข้าคิวสำรองให้อัตโนมัติ
                  </p>
                </div>
                <div>
                  <label for="ev-location" class="mb-1 block text-xs font-semibold text-stone-500">
                    สถานที่
                  </label>
                  <input
                    id="ev-location"
                    v-model="form.location"
                    type="text"
                    maxlength="200"
                    placeholder="เช่น หอประชุมพิริยาลัย"
                    class="w-full rounded-xl border border-stone-200 px-3.5 py-2.5 text-sm text-stone-800 outline-none transition-colors focus:border-[#B91C1C] focus:ring-2 focus:ring-[#B91C1C]/10"
                  />
                </div>
              </div>

              <div>
                <label for="ev-category" class="mb-1 block text-xs font-semibold text-stone-500">
                  หมวดกิจกรรม
                </label>
                <select
                  id="ev-category"
                  v-model="form.category"
                  data-testid="form-category"
                  class="w-full rounded-xl border border-stone-200 bg-white px-3.5 py-2.5 text-sm text-stone-800 outline-none transition-colors focus:border-[#B91C1C] focus:ring-2 focus:ring-[#B91C1C]/10"
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
                <label for="ev-cover" class="mb-1 block text-xs font-semibold text-stone-500">
                  ลิงก์ภาพปก
                </label>
                <input
                  id="ev-cover"
                  v-model="form.cover_image_url"
                  type="url"
                  maxlength="500"
                  placeholder="https://…"
                  class="w-full rounded-xl border border-stone-200 px-3.5 py-2.5 text-sm text-stone-800 outline-none transition-colors focus:border-[#B91C1C] focus:ring-2 focus:ring-[#B91C1C]/10"
                />
              </div>

              <img
                v-if="form.cover_image_url"
                :src="form.cover_image_url"
                alt="ตัวอย่างภาพปก"
                class="max-h-32 w-full rounded-xl border border-stone-200 bg-stone-100 object-cover"
              />
            </div>

            <div class="flex items-center justify-end gap-2 border-t border-stone-100 px-5 py-4">
              <span v-if="saveError" class="mr-auto text-[12px] font-semibold text-amber-600">
                {{ saveError }}
              </span>
              <button
                type="button"
                @click="closeModal"
                class="rounded-xl bg-stone-100 px-4 py-2.5 text-sm font-semibold text-stone-700 transition-colors hover:bg-stone-200"
              >
                ยกเลิก
              </button>
              <button
                type="button"
                :disabled="saving || !!formError"
                data-testid="save-event"
                @click="save"
                class="inline-flex items-center gap-1.5 rounded-xl bg-[#B91C1C] px-4 py-2.5 text-sm font-bold text-white shadow-md transition-all hover:bg-[#991B1B] hover:shadow-lg active:scale-[0.97] disabled:opacity-50"
              >
                <i :class="saving ? 'bi bi-arrow-repeat animate-spin' : 'bi bi-check-lg'"></i>
                {{ saving ? 'กำลังบันทึก...' : 'บันทึก' }}
              </button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>

    <!-- ════════ modal รายชื่อผู้สมัคร ════════ -->
    <Teleport to="body">
      <Transition name="sheet">
        <div
          v-if="regOpen"
          class="fixed inset-0 z-50 flex items-end justify-center sm:items-center"
          role="dialog"
          aria-modal="true"
        >
          <div class="absolute inset-0 bg-stone-900/40 backdrop-blur-sm" @click="closeRegistrations"></div>

          <div
            class="relative z-10 mx-auto flex max-h-[92vh] w-full max-w-lg flex-col overflow-hidden rounded-t-[1.5rem] bg-white shadow-2xl sm:rounded-[1.5rem]"
          >
            <div class="flex items-center justify-between border-b border-stone-100 px-5 py-4">
              <div class="min-w-0">
                <h2 class="text-base font-bold text-stone-900">รายชื่อผู้สมัคร</h2>
                <p class="truncate text-[12px] text-stone-400">{{ regEvent?.title }}</p>
              </div>
              <!-- ทางไปหน้าสแกน — อยู่ในหัว modal เพื่อให้เจอตั้งแต่ยังไม่เลื่อนดูรายชื่อ -->
              <RouterLink
                v-if="regEvent"
                :to="`/app/events/${regEvent.id}/check-in`"
                class="mr-1 shrink-0 rounded-lg px-2.5 py-1.5 text-[12px] font-bold text-[#B91C1C] transition-colors hover:bg-red-50"
                data-testid="open-scanner-link"
                @click="closeRegistrations"
              >
                <i class="bi bi-qr-code-scan mr-1"></i>สแกน
              </RouterLink>
              <button
                type="button"
                @click="closeRegistrations"
                class="rounded-lg p-1.5 text-stone-400 transition-colors hover:bg-stone-100 hover:text-stone-600"
                aria-label="ปิด"
              >
                <i class="bi bi-x-lg"></i>
              </button>
            </div>

            <div class="custom-scrollbar flex-1 overflow-y-auto px-5 py-4">
              <div v-if="regLoading" class="space-y-2">
                <div v-for="n in 5" :key="n" class="h-10 animate-pulse rounded-xl bg-stone-100"></div>
              </div>

              <div v-else-if="regError" class="py-10 text-center">
                <p class="text-sm text-stone-600">{{ regError }}</p>
                <button
                  type="button"
                  @click="loadRegistrations"
                  class="mt-4 rounded-lg bg-stone-100 px-4 py-2 text-sm font-semibold text-stone-700 hover:bg-stone-200"
                >
                  <i class="bi bi-arrow-clockwise mr-1"></i> ลองอีกครั้ง
                </button>
              </div>

              <div v-else-if="regs.length === 0" class="py-10 text-center text-stone-400">
                <div class="mb-2 text-3xl"><i class="bi bi-person-dash"></i></div>
                <p class="text-sm text-stone-500">ยังไม่มีใครลงทะเบียนกิจกรรมนี้</p>
              </div>

              <ul v-else class="divide-y divide-stone-100">
                <li v-for="r in regs" :key="r.id" class="flex items-center gap-3 py-2.5">
                  <span class="w-6 shrink-0 text-center text-xs tabular-nums text-stone-400">
                    {{ r.id }}
                  </span>
                  <div class="min-w-0 flex-1">
                    <p class="truncate text-sm font-medium text-stone-800">
                      {{ r.user_name ?? `ผู้ใช้ #${r.user_id}` }}
                    </p>
                    <!-- เช็คอินแล้ว → โชว์ "เวลาที่มาถึง" แทนเวลาสมัคร ซึ่งเป็นข้อมูลที่สภาใช้จริง -->
                    <p v-if="r.status === 'checked_in' && r.checked_in_at" class="text-[11px] text-emerald-600">
                      <i class="bi bi-person-check mr-0.5"></i>เช็คอิน {{ fmtTime(r.checked_in_at) }} น.
                    </p>
                    <p v-else class="text-[11px] text-stone-400">
                      {{ fmtDateTime(r.registered_at) }}
                    </p>
                  </div>
                  <span
                    class="inline-flex shrink-0 items-center gap-1 rounded-md px-2 py-0.5 text-[11px] font-semibold"
                    :class="{
                      'bg-emerald-50 text-emerald-700':
                        r.status === 'registered' || r.status === 'checked_in',
                      'bg-amber-50 text-amber-700': r.status === 'waitlisted',
                      'bg-stone-100 text-stone-500': r.status === 'cancelled',
                    }"
                  >
                    <i :class="`bi ${REGISTRATION_ICONS[r.status]}`"></i>
                    {{ REGISTRATION_LABELS[r.status] }}
                  </span>
                  <!--
                    ปุ่มเช็คอินมือ — เฉพาะแถวที่ "ถือที่นั่งจริงและยังไม่เช็คอิน"
                    ⚠️ ไม่มีให้คิวสำรอง (ยังไม่มีที่นั่งให้เช็คอิน — backend ตอบ 400) และไม่มีให้
                       คนที่เช็คอินแล้ว/ถูกยกเลิก ⇒ ซ่อนปุ่มที่เป็นไปไม่ได้ไว้ตั้งแต่ต้น ดีกว่า
                       ให้กดแล้วเจอ error ที่อธิบายว่าทำไมกดไม่ได้
                  -->
                  <button
                    v-if="r.status === 'registered'"
                    type="button"
                    :disabled="regActingId !== null"
                    class="shrink-0 rounded-lg bg-[#B91C1C] px-2.5 py-1.5 text-[12px] font-bold text-white transition-colors hover:bg-[#991B1B] disabled:opacity-50"
                    :data-testid="`checkin-btn-${r.id}`"
                    @click="handleCheckIn(r)"
                  >
                    <i
                      :class="regActingId === r.id ? 'bi bi-arrow-repeat animate-spin' : 'bi bi-person-check'"
                      class="mr-0.5"
                    ></i>
                    เช็คอิน
                  </button>
                </li>
              </ul>
            </div>

            <div v-if="regTotal > REG_PAGE_SIZE" class="border-t border-stone-100 px-5 py-3">
              <PaginationBar
                :total="regTotal"
                :page="regPage"
                :page-size="REG_PAGE_SIZE"
                :loading="regLoading"
                @page-change="onRegPageChange"
              />
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<style scoped>
.custom-scrollbar::-webkit-scrollbar {
  width: 5px;
}
.custom-scrollbar::-webkit-scrollbar-thumb {
  background-color: rgba(0, 0, 0, 0.12);
  border-radius: 10px;
}

.sheet-enter-active,
.sheet-leave-active {
  transition: opacity 0.25s ease;
}
.sheet-enter-active .relative,
.sheet-leave-active .relative {
  transition: transform 0.3s cubic-bezier(0.175, 0.885, 0.32, 1);
}
.sheet-enter-from,
.sheet-leave-to {
  opacity: 0;
}
.sheet-enter-from .relative,
.sheet-leave-to .relative {
  transform: translateY(24px) scale(0.99);
}
</style>
