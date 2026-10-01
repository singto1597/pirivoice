<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import Swal from 'sweetalert2'
import { BRAND } from '@/constants/brand'
import PaginationBar from '@/components/PaginationBar.vue'
import AppCard from '@/components/ui/AppCard.vue'
import AppButton from '@/components/ui/AppButton.vue'
import AppChip from '@/components/ui/AppChip.vue'
import AppEmptyState from '@/components/ui/AppEmptyState.vue'
import { fmtDateTime, fmtTime } from '@/datetime'
import { checkInRegistration, getEvent, listRegistrations } from '@/services/event'
import {
  REGISTRATION_ICONS,
  REGISTRATION_LABELS,
  STATUS_ICONS,
  STATUS_LABELS,
  type Event,
  type EventRegistration,
  type RegistrationStatus,
} from '@/types/event'
import type { ApiError } from '@/services/api'

/**
 * 👥 รายชื่อผู้สมัคร + เช็คอินมือ — **หน้าเต็มหน้า ไม่ใช่ modal** (รอบ 4)
 *
 * ⭐ **ทำไมต้องเป็นหน้า** — เดิมอยู่ใน modal ที่ฉากหลังกดปิดได้ ⇒ สภากำลังไล่เช็คอินหน้างาน
 *    แล้วนิ้วพลาดโดนฉากหลัง = ปิดทิ้งกลางคัน · และ **เปิดลิงก์ตรงไม่ได้/refresh ไม่ได้**
 *    ซึ่งเป็นสิ่งที่ต้องทำได้จริงเวลาใช้งานหน้างาน (ส่งลิงก์ให้เพื่อนในสภา · รีเฟรชจอ)
 *
 * ⭐ **เลขหน้าเก็บใน URL (`?page=2`)** — refresh แล้วอยู่หน้าเดิม ไม่เด้งกลับหน้า 1
 *    (คิวที่ยาวเกิน 20 คนคือเคสปกติของกิจกรรมจริง ไม่ใช่ของหายาก)
 *    · **ตัวกรองสถานะก็อยู่ใน URL ด้วย (`?status=checked_in`)** เหตุผลเดียวกัน และเพราะ
 *      "ส่งลิงก์คนที่ยังไม่มาให้เพื่อนที่ประตู" เป็นวิธีใช้จริงหน้างาน
 *
 * ⚠️ **หัวเรื่องมาจาก `getEvent(id)` ไม่ใช่ state ที่ส่งข้ามหน้า** — เพราะเปิดตรงได้
 *    และ endpoint ตัวนี้เห็น **ฉบับร่างด้วย** (ต่างจาก `/public/{id}`)
 *
 * 🔴 **ไม่มี `<h1>` และไม่มี eyebrow "Registrations" ในไฟล์นี้** — `<h1>` ของหน้าอยู่ที่
 *    `AppHeader` และ `routeTitles['event-registrations'] = 'รายชื่อผู้สมัคร'` แสดงอยู่แล้ว
 *    · ปุ่มย้อนก็มาจาก `AppHeader` เหมือนกัน (ประกาศที่ `meta.headerBack` ของ route)
 *    ⚠️ และ **ห้ามใส่ `uppercase tracking-*` กับข้อความไทย** — ภาษาไทยไม่มีตัวพิมพ์ใหญ่
 */
const route = useRoute()
const router = useRouter()

const REG_PAGE_SIZE = 20

const eventId = computed<number | null>(() => {
  const n = Number(route.params.id)
  return Number.isInteger(n) && n > 0 ? n : null
})

/**
 * ตัวกรองสถานะ — `'all'` = ไม่ส่ง `status` ไป backend เลย
 *
 * ⭐ **ตัวเลขบนชิปคือ "สรุปตัวเลข" ที่แผน R4.3 ขอ** — ไม่ได้แยกเป็นแถวสถิติต่างหาก
 *    เพราะสองอย่างนี้ตอบคำถามเดียวกัน ("มีกี่คนในแต่ละสถานะ") และการมีทั้งแถวสถิติ
 *    กับแถวชิปที่ตัวเลขตรงกันคือ **ของซ้ำที่ผู้ใช้ต้องอ่านสองรอบ** ซึ่งเป็นโรคที่รอบนี้กำลังแก้
 *    ⇒ รวมเป็นแถวเดียวที่ **แตะแล้วกรองได้** (แบบเดียวกับที่แผนสั่งไว้ให้ Dashboard ใน R4.5)
 *
 * ⚠️ **ป้ายบนชิปใช้ `REGISTRATION_LABELS` ตัวเดียวกับป้ายบนแถวรายชื่อ** — แผนเขียนว่า
 *    "ลงทะเบียน / เข้างานแล้ว / ยังไม่มา" แต่ถ้าชิปเขียน "ยังไม่มา" ขณะที่ทุกแถวเขียน
 *    "ได้ที่นั่ง" สภาาจะไม่แน่ใจว่าสองคำนี้คือสถานะเดียวกันไหม ⇒ **คำที่ตรงกันสำคัญกว่าคำที่แผนเดาไว้**
 *    (การรวบคำศัพท์ทั้งแอปเป็นงานของ R5 อยู่แล้ว)
 */
type RegFilter = 'all' | RegistrationStatus

const REG_FILTERS: { key: RegFilter; label: string }[] = [
  { key: 'all', label: 'ทุกสถานะ' },
  { key: 'registered', label: REGISTRATION_LABELS.registered },
  { key: 'checked_in', label: REGISTRATION_LABELS.checked_in },
  { key: 'waitlisted', label: REGISTRATION_LABELS.waitlisted },
  { key: 'cancelled', label: REGISTRATION_LABELS.cancelled },
]

/**
 * ชิปที่ **โชว์เสมอแม้ตัวเลขเป็น 0**
 * · `all` กับ `registered` — งานหลักของหน้านี้คือ "ใครยังไม่มา" ⇒ 0 ก็ต้องเห็น (แปลว่ามาครบแล้ว)
 * · `checked_in` — 0 คือข่าวที่ดีและต้องอ่านออกทันที ("ยังไม่มีใครมาถึง")
 * ส่วน `waitlisted`/`cancelled` ที่เป็น 0 คือชิปที่ไม่บอกอะไร ⇒ ซ่อน (ลดของบนจอ = เป้าหมายรอบนี้)
 */
const ALWAYS_VISIBLE: RegFilter[] = ['all', 'registered', 'checked_in']

const event = ref<Event | null>(null)
const regs = ref<EventRegistration[]>([])
const total = ref(0)
/** หน้าปัจจุบัน — ตั้งต้นจาก URL (ดู `syncQuery`) */
const page = ref(1)
/** ตัวกรองปัจจุบัน — ตั้งต้นจาก URL */
const filter = ref<RegFilter>('all')
/** ตัวเลขต่อสถานะ — มาจาก **`total` ของฝั่ง server** ไม่ใช่การนับแถวที่โหลดมา (ดู `loadCounts`) */
const counts = ref<Record<RegFilter, number>>({
  all: 0,
  registered: 0,
  checked_in: 0,
  waitlisted: 0,
  cancelled: 0,
})
const isLoading = ref(true)
const listLoading = ref(false)
const loadError = ref(false)
/** แยกจาก `loadError` — "ไม่มีกิจกรรมนี้" ไม่ต้องมีปุ่มลองใหม่ (กดแล้วก็ 404 อีก) */
const notFound = ref(false)
const listError = ref('')
/**
 * id ของแถวที่กำลังเช็คอินอยู่ — **เก็บเป็น id ต่อแถว ไม่ใช่ boolean ของทั้งหน้า**
 *
 * ⭐ เก็บ id เพื่อให้ **สปินเนอร์ขึ้นที่แถวที่กดเท่านั้น** — ถ้าใช้ boolean ปุ่มทุกแถวจะหมุนพร้อมกัน
 *    แล้วสภาไม่รู้ว่าแถวไหนกำลังทำงาน (ตอนเลื่อนหารายชื่อในคิวที่ยาว อันนี้สำคัญ)
 *
 * ⚠️ **แต่การล็อกเป็นของทั้งหน้าโดยเจตนา** (`:disabled="actingId !== null"`) — *ไม่ใช่*
 *    การเช็คอินหลายคนพร้อมกัน · เพราะทุกครั้งที่สำเร็จจะโหลดรายชื่อใหม่ทั้งชุด
 *    ⇒ สองคำขอที่ทับกันจะโหลดชนกัน แล้วรายชื่อที่ได้อาจเป็นชุดก่อนการเช็คอินอีกคน
 *    (ป้ายสถานะกับความจริงไม่ตรงกันชั่วขณะ ซึ่งสภาจะอ่านว่า "กดไม่ติด")
 *    · ราคาที่จ่ายคือรอ ~200 ms ต่อคน ซึ่งไม่ใช่คอขวดของงานจริง (คอขวดคือคนเดินมาถึงประตู)
 *    · งานที่ต้องเร็วระดับนั้นคือ **หน้าสแกน** ซึ่งทำงานคนละแบบ (ไม่มีรายชื่อให้โหลดซ้ำ)
 */
const actingId = ref<number | null>(null)

/** กิจกรรมถูกลบ (soft delete) — `getEvent` คืน 200 แต่ `list_registrations` จะ 404 */
const isDeleted = computed(() => event.value?.deleted_at != null)

/** ชิปที่ควรเห็น — ตัวที่ active ต้องอยู่เสมอ ไม่งั้นผู้ใช้ติดอยู่ในตัวกรองที่มองไม่เห็นทางออก */
const visibleFilters = computed(() =>
  REG_FILTERS.filter(
    (f) => ALWAYS_VISIBLE.includes(f.key) || counts.value[f.key] > 0 || filter.value === f.key,
  ),
)

/** จำนวนที่โชว์บนชิป — `AppChip` ซ่อนเองเมื่อเป็น 0 */
function countOf(key: RegFilter): number {
  return counts.value[key]
}

function errText(e: unknown): string {
  if (typeof e === 'string') return e
  if (e instanceof Error) return e.message
  return 'เกิดข้อผิดพลาด กรุณาลองใหม่'
}

// ── ค่าจาก URL ───────────────────────────────────────────────────────────────

/**
 * แคบ `string` จาก query → `RegFilter` (type guard ของจริง ไม่ใช่ cast)
 *
 * ⚠️ **ห้ามใช้ `as RegFilter`** — `?status=อะไรก็ได้` จากลิงก์ที่คนพิมพ์เองจะผ่านด่านไปถึง
 *    `filter` แล้วถูกส่งต่อเป็น `status` ให้ backend ซึ่งตอบ 422 (หรือแย่กว่านั้นคือกรองผิด)
 *    · ค่าที่ไม่รู้จักต้อง **ตกกลับเป็น `'all'` เงียบ ๆ** ไม่ใช่พังทั้งหน้า
 */
function asRegFilter(v: string): RegFilter | null {
  const hit = REG_FILTERS.find((f) => f.key === v)
  return hit ? hit.key : null
}

/** อ่าน `?page=` — ค่าที่ใช้ไม่ได้ (0, -1, "abc", อาร์เรย์จาก `?page=1&page=2`) ถือเป็นหน้า 1 */
function pageFromQuery(): number {
  const raw = route.query.page
  const n = Number(Array.isArray(raw) ? raw[0] : raw)
  return Number.isInteger(n) && n > 0 ? n : 1
}

function filterFromQuery(): RegFilter {
  const raw = route.query.status
  const v = Array.isArray(raw) ? raw[0] : raw
  return (typeof v === 'string' ? asRegFilter(v) : null) ?? 'all'
}

// ── เขียนค่ากลับลง URL ────────────────────────────────────────────────────────

/**
 * เขียนทั้ง `status` และ `page` ลง URL พร้อมกัน
 *
 * ⚠️ **`replace` ไม่ใช่ `push`** — กด "หน้าถัดไป" สามครั้งไม่ควรต้องกด back สามครั้ง
 *    เพื่อออกจากหน้านี้ (แต่ยังต้องอยู่ใน URL เพื่อให้ refresh แล้วอยู่หน้าเดิม)
 * ⚠️ ค่าเริ่มต้น **ลบ key ออกจาก query** ไม่ใช่เขียน `page=1`/`status=all` — ไม่งั้นจะเกิดทั้ง
 *    `/registrations` และ `/registrations?page=1&status=all` ที่เป็นหน้าเดียวกัน (ลิงก์ซ้ำไม่มีเหตุ)
 */
function syncQuery() {
  void router.replace({
    query: {
      ...route.query,
      status: filter.value === 'all' ? undefined : filter.value,
      page: page.value === 1 ? undefined : String(page.value),
    },
  })
}

// ── การโหลด ──────────────────────────────────────────────────────────────────

async function load() {
  isLoading.value = true
  loadError.value = false
  notFound.value = false
  page.value = pageFromQuery()
  filter.value = filterFromQuery()

  const id = eventId.value
  if (id === null) {
    notFound.value = true
    isLoading.value = false
    return
  }

  try {
    event.value = await getEvent(id)
  } catch (e) {
    if ((e as ApiError)?.status === 404) notFound.value = true
    else loadError.value = true
    isLoading.value = false
    return
  }
  isLoading.value = false

  // ⚠️ กิจกรรมที่ถูกลบ: หัวเรื่องยังแสดงได้ แต่ `list_registrations` **คืน 404 แน่นอน**
  //    (service ตรวจ `deleted_at IS NULL`) ⇒ ไม่เรียกเลย ดีกว่าเรียกแล้วเอา 404 ที่รู้สาเหตุอยู่แล้ว
  //    มาแสดงเป็น "โหลดรายชื่อไม่สำเร็จ" ซึ่งชวนให้สภากด "ลองอีกครั้ง" วนไปเปล่า ๆ
  if (isDeleted.value) return

  await Promise.all([loadCounts(), loadRegistrations()])
}

onMounted(load)

/**
 * ตัวเลขต่อสถานะ — **ต้องถาม server ทีละสถานะ ห้ามนับจาก `regs` ที่โหลดมา**
 *
 * 🔴 **ทำไมห้ามนับเอง:** `regs` คือ *หน้าปัจจุบัน* (20 แถวจากทั้งหมด) ⇒ การนับจากมันจะได้
 *    "เข้างานแล้ว 7" ที่จริงคือ "เข้างานแล้ว 7 *ใน 20 แถวนี้*" ซึ่ง **ผู้ใช้อ่านว่า 7 คนทั้งงาน**
 *    ⇒ ตัวเลขจะเปลี่ยนไปตามหน้าที่เปิดดู · **ตัวเลขที่ผิดแบบเงียบ ๆ แย่กว่าไม่มีตัวเลข**
 *    (บทเรียนเดียวกับที่ R4.2 ตัด segment "ของฉัน" ทิ้ง)
 *
 * 📌 **ทางที่ประหยัดกว่า:** `_envelope` ของ `list_registrations` คืน `total` ที่เป็น
 *    `COUNT(*)` ของ `where` จริง ⇒ เรียก `limit: 1` แล้วอ่าน `total` = ได้ COUNT มาหนึ่งตัว
 *    โดยไม่ต้องขนแถวมา · ยิงพร้อมกัน 5 ตัว (Promise.all) ครั้งเดียวตอนเปิดหน้า
 *    ⚠️ ไม่ยิงใหม่ตอนเปลี่ยนหน้า/เปลี่ยนตัวกรอง — ตัวเลขไม่เปลี่ยนตามสองอย่างนั้น
 *    ⏭️ ทางที่ดีกว่าอีกคือให้ backend คืน `checked_in_count` มาจาก LATERAL ที่นับอยู่แล้ว
 *       (เป็นงาน backend แยก ไม่ได้ทำในรอบนี้ — ดูเหตุผลเดียวกับ "ส่งออก Excel")
 */
async function loadCounts() {
  const id = eventId.value
  if (id === null) return
  try {
    const res = await Promise.all(
      REG_FILTERS.map((f) =>
        listRegistrations(id, { status: f.key === 'all' ? undefined : f.key, limit: 1 }),
      ),
    )
    REG_FILTERS.forEach((f, i) => {
      counts.value[f.key] = res[i]?.total ?? 0
    })
  } catch {
    // ⚠️ **ตัวเลขสรุปเป็นของช่วยอ่าน ไม่ใช่เนื้อหาหลัก** ⇒ ล้มแล้วห้ามทำให้ทั้งหน้าพัง
    //    ปล่อยเป็น 0 (ชิปจะไม่โชว์ตัวเลข) แล้วรายชื่อที่เหลือยังใช้งานได้เต็มที่
  }
}

async function loadRegistrations() {
  listLoading.value = true
  listError.value = ''
  try {
    await fetchPage()
  } finally {
    listLoading.value = false
  }
}

async function fetchPage() {
  const id = eventId.value
  if (id === null) return
  try {
    const res = await listRegistrations(id, {
      status: filter.value === 'all' ? undefined : filter.value,
      limit: REG_PAGE_SIZE,
      offset: (page.value - 1) * REG_PAGE_SIZE,
    })
    regs.value = res.items
    total.value = res.total
    // หน้าสุดท้ายหายไปเพราะมีคนถอน/ถูกยกเลิก ⇒ ถอยกลับหนึ่งหน้า **และแก้ URL ให้ตรง**
    // (ถ้าไม่แก้ ผู้ใช้ที่ refresh จะกลับมาที่หน้าว่างอีกครั้งไม่จบ)
    if (regs.value.length === 0 && page.value > 1) {
      page.value -= 1
      syncQuery()
      await fetchPage()
    }
  } catch (e) {
    listError.value = errText(e)
    regs.value = []
    total.value = 0
  }
}

function onPageChange(n: number) {
  if (n === page.value) return
  page.value = n
  syncQuery()
  loadRegistrations()
}

/**
 * เปลี่ยนตัวกรองสถานะ
 *
 * ⚠️ แยกเป็นเมธอด **ห้ามเขียนเป็น `@click` หลายบรรทัดในเทมเพลต** — `npm run format`
 *    เคยลอก `;` ระหว่างสอง statement ใน inline handler จน build แตก (skills #10)
 */
function pickFilter(f: RegFilter) {
  if (f === filter.value) return
  filter.value = f
  page.value = 1 // เปลี่ยนชุดข้อมูล = กลับหน้า 1 เสมอ (หน้า 3 ของตัวกรองใหม่อาจไม่มีอยู่)
  syncQuery()
  loadRegistrations()
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
  const id = eventId.value
  if (id === null || actingId.value !== null) return
  actingId.value = r.id
  try {
    const res = await checkInRegistration(id, { registration_id: r.id })
    // โหลดใหม่ทั้งรายชื่อ **และตัวเลข** — การเช็คอินทำให้คนย้ายจาก "ได้ที่นั่ง" ไป "เช็คอินแล้ว"
    // ⇒ ถ้าโหลดแต่รายชื่อ ตัวเลขบนชิปจะค้างที่ค่าเก่าแล้วขัดกับแถวที่เพิ่งเปลี่ยน (ผู้ใช้เห็นทันที)
    await Promise.all([loadCounts(), loadRegistrations()])

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
        confirmButtonColor: BRAND,
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
    actingId.value = null
  }
}

/** ปุ่มในสถานะว่าง/ผิดพลาด — ปุ่มลูกศรบนหัวแถบมาจาก `AppHeader` แล้ว (ดู `meta.headerBack`) */
const goBack = () => router.push({ name: 'event-management' })

/** "ว่างเพราะไม่มีใครสมัคร" กับ "ว่างเพราะตัวกรอง" คนละสาเหตุ คนละทางออก */
const isEmptyByFilter = computed(() => filter.value !== 'all')
</script>

<template>
  <div class="mx-auto max-w-2xl space-y-4 pb-4">
    <!-- ⏳ โหลด -->
    <div v-if="isLoading" class="space-y-4" aria-busy="true">
      <div class="h-12 w-full animate-pulse rounded-card bg-canvas"></div>
      <AppCard>
        <div v-for="n in 5" :key="n" class="mb-2 h-10 animate-pulse rounded-control bg-canvas"></div>
      </AppCard>
    </div>

    <!-- 🚫 ไม่มีกิจกรรมนี้ -->
    <AppCard v-else-if="notFound" :padded="false" class="py-4">
      <AppEmptyState
        icon="bi-calendar-x"
        title="ไม่พบกิจกรรมนี้"
        description="อาจถูกลบถาวรไปแล้ว หรือลิงก์ไม่ถูกต้อง"
      >
        <AppButton variant="secondary" @click="goBack">
          <template #icon><i class="bi bi-arrow-left" aria-hidden="true" /></template>
          กลับหน้าจัดการกิจกรรม
        </AppButton>
      </AppEmptyState>
    </AppCard>

    <!-- ⚠️ โหลดไม่ได้ -->
    <AppCard v-else-if="loadError" :padded="false" class="py-4">
      <AppEmptyState
        icon="bi-wifi-off"
        title="โหลดข้อมูลกิจกรรมไม่สำเร็จ"
        description="ตรวจสอบการเชื่อมต่อแล้วลองอีกครั้ง"
      >
        <AppButton variant="secondary" @click="load">
          <template #icon><i class="bi bi-arrow-clockwise" aria-hidden="true" /></template>
          ลองใหม่
        </AppButton>
      </AppEmptyState>
    </AppCard>

    <div v-else class="space-y-4">
      <!-- 📌 หัวเรื่องกิจกรรม + ทางไปหน้าสแกน
           ⚠️ ไม่มี `<h1>` — `AppHeader` แสดง "รายชื่อผู้สมัคร" ให้แล้ว (routeTitles) -->
      <div class="flex items-start justify-between gap-3">
        <div class="min-w-0">
          <p class="truncate text-body font-semibold text-ink-1">{{ event?.title }}</p>
          <p class="mt-0.5 flex items-center gap-1 text-xs text-ink-3">
            <i :class="`bi ${STATUS_ICONS[event?.status ?? 'draft']}`" aria-hidden="true" />
            {{ event ? STATUS_LABELS[event.status] : '' }}
            <template v-if="event?.capacity != null">
              · รับ {{ event.capacity.toLocaleString('en-US') }} ที่
            </template>
          </p>
        </div>
        <!-- ทางไปหน้าสแกน — อยู่หัวหน้าเพื่อให้เจอตั้งแต่ยังไม่เลื่อนดูรายชื่อ -->
        <AppButton
          v-if="event"
          variant="secondary"
          size="sm"
          :to="{ name: 'event-check-in', params: { id: event.id } }"
          data-testid="open-scanner-link"
        >
          <template #icon><i class="bi bi-qr-code-scan" aria-hidden="true" /></template>
          สแกน
        </AppButton>
      </div>

      <!-- 🗑️ ถูกลบแล้ว — `list_registrations` จะ 404 จึงไม่เรียกเลย (ดูคอมเมนต์ใน `load`) -->
      <AppCard v-if="isDeleted" muted>
        <div class="flex items-start gap-2.5">
          <i class="bi bi-trash3 mt-0.5 text-warn" aria-hidden="true" />
          <div class="text-[13px]">
            <p class="font-semibold text-ink-1">กิจกรรมนี้ถูกลบแล้ว — ดูรายชื่อไม่ได้จนกว่าจะกู้คืน</p>
            <p class="mt-0.5 text-ink-2">
              กลับไปหน้าการจัดการกิจกรรม แล้วกด "กู้คืน" ในรายการก่อน
            </p>
          </div>
        </div>
      </AppCard>

      <template v-else>
        <!-- 🔢 สรุปตัวเลข + ตัวกรอง — **แถวเดียว** (แตะตัวเลขเพื่อกรอง · แตะซ้ำ/กด "ทุกสถานะ" เพื่อล้าง)
             ⚠️ ชิปทุกตัวมีชื่อไทยของตัวเอง ⇒ ตัวเลือกที่ทนที่สุดคือ role+ชื่อ ไม่ใช่ testid -->
        <div class="chip-row">
          <AppChip
            v-for="f in visibleFilters"
            :key="f.key"
            :label="f.label"
            :count="countOf(f.key)"
            :active="filter === f.key"
            @click="pickFilter(f.key)"
          />
        </div>

        <AppCard :padded="false">
          <div class="flex items-center justify-between border-b border-line px-4 py-3">
            <p class="text-xs font-semibold text-ink-2">
              {{ filter === 'all' ? 'ทุกสถานะ' : REGISTRATION_LABELS[filter] }}
            </p>
            <p v-if="!listLoading" class="text-xs tabular-nums text-ink-3">
              {{ total.toLocaleString('en-US') }} คน
            </p>
          </div>

          <div class="px-4 py-3">
            <div v-if="listLoading" class="space-y-2" aria-busy="true">
              <div v-for="n in 5" :key="n" class="h-10 animate-pulse rounded-control bg-canvas"></div>
            </div>

            <!-- ⚠️ ไม่มีเส้นประ — `AppEmptyState` ไม่ใช้ `border-dashed` โดยเจตนา (R0) -->
            <AppEmptyState
              v-else-if="listError"
              icon="bi-wifi-off"
              title="โหลดรายชื่อไม่สำเร็จ"
              :description="listError"
              compact
            >
              <AppButton variant="secondary" size="sm" @click="loadRegistrations">
                <template #icon><i class="bi bi-arrow-clockwise" aria-hidden="true" /></template>
                ลองอีกครั้ง
              </AppButton>
            </AppEmptyState>

            <!-- ว่างสองแบบ คนละสาเหตุ: "ยังไม่มีใครสมัคร" กับ "ตัวกรองนี้ไม่มีใครอยู่" -->
            <AppEmptyState
              v-else-if="regs.length === 0"
              :icon="isEmptyByFilter ? 'bi-funnel' : 'bi-person-dash'"
              :title="isEmptyByFilter ? 'ไม่มีใครในสถานะนี้' : 'ยังไม่มีใครลงทะเบียนกิจกรรมนี้'"
              :description="
                isEmptyByFilter
                  ? 'ลองดูสถานะอื่น หรือกลับไปดูทุกสถานะ'
                  : 'เมื่อมีคนสมัคร รายชื่อจะขึ้นที่นี่'
              "
              compact
            >
              <AppButton
                v-if="isEmptyByFilter"
                variant="secondary"
                size="sm"
                data-testid="clear-reg-filter"
                @click="pickFilter('all')"
              >
                <template #icon><i class="bi bi-x-circle" aria-hidden="true" /></template>
                ดูทุกสถานะ
              </AppButton>
            </AppEmptyState>

            <ul v-else class="divide-y divide-line">
              <li v-for="r in regs" :key="r.id" class="flex items-center gap-3 py-2.5">
                <span class="w-7 shrink-0 text-center text-xs tabular-nums text-ink-3">
                  {{ r.id }}
                </span>
                <div class="min-w-0 flex-1">
                  <p class="truncate text-body font-medium text-ink-1">
                    {{ r.user_name ?? `ผู้ใช้ #${r.user_id}` }}
                  </p>
                  <!-- เช็คอินแล้ว → โชว์ "เวลาที่มาถึง" แทนเวลาสมัคร ซึ่งเป็นข้อมูลที่สภาใช้จริง -->
                  <p
                    v-if="r.status === 'checked_in' && r.checked_in_at"
                    class="text-[11px] text-ok"
                  >
                    <i class="bi bi-person-check mr-0.5" aria-hidden="true" />เช็คอิน
                    {{ fmtTime(r.checked_in_at) }} น.
                  </p>
                  <p v-else class="text-[11px] text-ink-3">
                    {{ fmtDateTime(r.registered_at) }}
                  </p>
                </div>
                <span
                  class="inline-flex shrink-0 items-center gap-1 rounded-md px-2 py-0.5 text-[11px] font-semibold"
                  :class="{
                    'bg-ok-soft text-ok':
                      r.status === 'registered' || r.status === 'checked_in',
                    'bg-warn-soft text-warn': r.status === 'waitlisted',
                    'bg-canvas text-ink-3': r.status === 'cancelled',
                  }"
                >
                  <i :class="`bi ${REGISTRATION_ICONS[r.status]}`" aria-hidden="true" />
                  {{ REGISTRATION_LABELS[r.status] }}
                </span>
                <!--
                  ปุ่มเช็คอินมือ — เฉพาะแถวที่ "ถือที่นั่งจริงและยังไม่เช็คอิน"
                  ⚠️ ไม่มีให้คิวสำรอง (ยังไม่มีที่นั่งให้เช็คอิน — backend ตอบ 400) และไม่มีให้
                     คนที่เช็คอินแล้ว/ถูกยกเลิก ⇒ ซ่อนปุ่มที่เป็นไปไม่ได้ไว้ตั้งแต่ต้น ดีกว่า
                     ให้กดแล้วเจอ error ที่อธิบายว่าทำไมกดไม่ได้
                -->
                <AppButton
                  v-if="r.status === 'registered'"
                  size="sm"
                  :loading="actingId === r.id"
                  :disabled="actingId !== null"
                  :data-testid="`checkin-btn-${r.id}`"
                  @click="handleCheckIn(r)"
                >
                  <template #icon><i class="bi bi-person-check" aria-hidden="true" /></template>
                  เช็คอิน
                </AppButton>
              </li>
            </ul>
          </div>
        </AppCard>

        <!-- ⚠️ `PaginationBar` อยู่นอกการ์ด (มี `mt-6` ของตัวเอง) — แบบเดียวกับ `EventList`/`MyIssues`
             และมันซ่อนตัวเองเมื่อมีหน้าเดียว ⇒ ไม่ต้องเช็ค `total > PAGE_SIZE` เอง -->
        <PaginationBar
          :total="total"
          :page="page"
          :page-size="REG_PAGE_SIZE"
          :loading="listLoading"
          @page-change="onPageChange"
        />
      </template>
    </div>
  </div>
</template>
