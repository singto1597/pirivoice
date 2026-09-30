/**
 * 📝 ตรรกะบริสุทธิ์ของฟอร์มกิจกรรม — สร้าง/แก้ไข (รอบ 4)
 *
 * ⭐ **ทำไมแยกออกมาจาก `.vue`** — ตรรกะชุดนี้เป็นตัวตัดสินว่า "ผู้ใช้แก้อะไร" ซึ่งมีผลกับ
 *    (ก) สิ่งที่ยิงไป backend และ (ข) คำถาม "ยังไม่บันทึก ทิ้งไหม" ⇒ ถ้าอยู่ในเทมเพลต
 *    จะทดสอบไม่ได้เลย (โปรเจกต์นี้ **ไม่ mount component ในเทสต์**) แล้ววันที่มีคนแก้
 *    `buildCreate` โดยไม่แก้ `toBaseline` ผู้ใช้จะเจอกล่อง "ยังไม่บันทึก" โผล่หลังบันทึกสำเร็จ
 *    ซึ่งเป็นบั๊กที่หาสาเหตุยากมากและ **เทสต์ UI จับไม่ได้**
 *
 * ⚠️ **ไม่ย้ายไป `types/event.ts`** — ไฟล์นั้นไม่มี import แม้แต่ตัวเดียว (type ล้วน ⇒ ถูก
 *    erase ตอน build) และถูก import ต่อโดย `types/notification.ts`/`types/home.ts`
 *    ⇒ ใส่ runtime import เข้าไปจะลากโค้ดจริงเข้าไปในกราฟที่เคยเป็น type ล้วน
 *    (รวมถึง service worker ที่ import `types/notification`)
 */
import { toLocalInput } from '@/datetime'
import {
  CATEGORY_LABELS,
  EVENT_CATEGORIES,
  categoryPayload,
  isEventCategory,
  type Event,
  type EventCreate,
  type EventUpdate,
} from '@/types/event'

/**
 * ค่าดิบในฟอร์ม — **ทุกช่องเป็น `string` โดยเจตนา**
 *
 * ⚠️ `capacity` เป็นสตริงเพราะ `<input>` ให้สตริงเสมอ ⇒ ถ้าเก็บเป็น `number | null` จะต้อง
 *    แปลงไป-กลับทุกครั้งที่ผู้ใช้พิมพ์ แล้วช่วงที่พิมพ์ "1" ระหว่างจะไปเป็น 1 ซึ่ง *ดูเหมือน*
 *    ค่าที่ถูกต้อง ⇒ ตัวเลขที่ผู้ใช้ตั้งใจพิมพ์ "15" จะถูกอ่านเป็น 1 แล้วบันทึกทันทีถ้ามี autosave
 *    · การเก็บสตริงทำให้ "สิ่งที่ผู้ใช้พิมพ์" กับ "สิ่งที่ส่ง" แยกกันชัด ๆ ที่ `buildCreate`
 *
 * ⚠️ `category` เป็น `string` ไม่ใช่ `EventCategory` — ค่ามาจาก `<select>` ที่เราเติมตัวเลือก
 *    แปลก ๆ เข้าไปได้ (ดู `categoryOptionsOf`) ⇒ ถ้าประกาศแคบไว้ จะต้อง cast ตอนอ่านค่า
 *    ซึ่งกลบความจริงว่ามันอาจไม่ใช่คีย์ที่รู้จัก · ด่านจริงอยู่ที่ `buildCreate`
 */
export interface EventFormValues {
  title: string
  description: string
  location: string
  cover_image_url: string
  /** `YYYY-MM-DDTHH:MM` (ค.ศ. จาก date picker) — ค่าที่ส่ง backend ตรง ๆ ไม่มีขั้นตอนแปลง */
  event_date: string
  registration_deadline: string
  capacity: string
  category: string
}

/**
 * ค่าเริ่มต้นของฟอร์ม "สร้างใหม่" — **ไม่ใช่ `null`/`undefined`**
 *
 * ⭐ ใช้เป็น `baseline` ของโหมดสร้างด้วย ⇒ นิยาม "สกปรก" (ดู `isDirty`) กับสิ่งที่ `save()`
 *    ส่ง เป็นตัวเลขตัวเดียวกัน ไม่ต้องมีสาขา `if (mode === 'add')` ในตรรกะกันข้อมูลหาย
 */
export const EMPTY_EVENT_FORM: EventFormValues = {
  title: '',
  description: '',
  location: '',
  cover_image_url: '',
  event_date: '',
  registration_deadline: '',
  capacity: '',
  category: 'other',
}

/**
 * ค่าฟอร์ม → payload สร้าง · ช่องว่างของฟิลด์ที่ไม่บังคับ = `null` (สั่งล้างค่า) ไม่ใช่ `undefined`
 *
 * ⚠️ **`''` → `null` ไม่ใช่ `undefined`** — สองอันนี้ความหมายต่างกันที่ backend:
 *    `null` = "ล้างคอลัมน์นี้" · ไม่ส่งมา = "ไม่แตะ" (`exclude_unset`) ⇒ ถ้าเผลอส่ง
 *    `undefined` ตอนผู้ใช้ลบข้อความในช่องออก ค่าเดิมจะ **ไม่ถูกลบ** แล้วผู้ใช้จะเห็นข้อความ
 *    เดิมกลับมาหลังบันทึก ซึ่งอ่านไม่ออกว่าใครผิด
 */
export function buildCreate(values: EventFormValues): EventCreate {
  const cap = values.capacity.trim()
  return {
    title: values.title.trim(),
    description: values.description.trim() || null,
    location: values.location.trim() || null,
    cover_image_url: values.cover_image_url.trim() || null,
    event_date: values.event_date,
    registration_deadline: values.registration_deadline || null,
    capacity: cap === '' ? null : Number(cap),
    // คีย์ที่ไม่รู้จัก ⇒ `undefined` = ไม่ส่ง (ดู `categoryPayload`) — ไม่เดาว่าเป็น 'other'
    category: categoryPayload(values.category),
  }
}

/**
 * แถว → ค่าฟอร์ม (สิ่งที่ผู้ใช้เห็นในช่องกรอก) — ฟังก์ชันดิบ ยังไม่ normalize
 *
 * ⚠️ `category` อ่านจาก **แถวจริง** (`e.category`) ไม่ใช่ค่าที่ normalize แล้ว — คีย์แปลก
 *    ต้องไม่ถูกแปลงเป็น 'other' ตั้งแต่เปิดฟอร์ม (ดู `categoryOptionsOf` ที่เติมตัวเลือกนั้นให้)
 */
function rowToValues(e: Event): EventFormValues {
  return {
    title: e.title,
    description: e.description ?? '',
    location: e.location ?? '',
    cover_image_url: e.cover_image_url ?? '',
    event_date: toLocalInput(e.event_date),
    registration_deadline: toLocalInput(e.registration_deadline),
    capacity: e.capacity === null ? '' : String(e.capacity),
    category: e.category,
  }
}

/** แถว → ค่าฟอร์ม (มุมมองของผู้ใช้ — `EventFormValues` ไม่ใช่ payload) */
export function toFormValues(e: Event): EventFormValues {
  return rowToValues(e)
}

/**
 * ★ ค่าของแถว → **payload ที่ normalize แล้ว** ใช้เป็นฐานเทียบว่าผู้ใช้แก้อะไร
 *
 * ⭐ **นิยามคือ `buildCreate(rowToValues(e))` ไม่ใช่การเขียน object ขึ้นมาใหม่** — โดยเจตนา
 *    ⇒ ทั้งสองข้างของ diff ผ่านการ normalize ชุดเดียวกัน **โดยโครงสร้าง** ไม่ใช่โดยวินัย
 *    ⇒ ไม่มีทางที่วันหนึ่งมีคนแก้ `buildCreate` (เช่นเพิ่มการ trim ช่องใหม่) แล้ว `toBaseline`
 *    ไม่ตาม — ซึ่งจะทำให้ "เปิดฟอร์มแล้วกดบันทึกทันที" **ยิง PATCH เปล่า** และกล่อง
 *    "ยังไม่บันทึก" โผล่ทั้งที่ไม่มีอะไรจะเสีย
 *
 * 🐛 **บั๊กที่การเขียนซ้ำแบบแยกคีย์เคยทำให้เกิด (เจอตอนเขียนเทสต์รอบนี้):**
 *    `toBaseline` คืน `registration_deadline: ''` (จาก `toLocalInput(null)`) แต่ `buildCreate`
 *    คืน `null` ⇒ สองค่าไม่เท่ากัน ⇒ **เปิดกิจกรรมที่ "ไม่ตั้งกำหนดปิดรับ" แล้วกดบันทึกทันที
 *    ยิง PATCH `{registration_deadline: null}` เสมอ** ทั้งที่ไม่มีอะไรเปลี่ยน
 *    (เขียนทับด้วยค่าเดิม + audit log เปล่า + `updated_at` ขยับโดยไม่มีเหตุ)
 *    ⇒ ผู้ใช้เห็น "แก้แล้วไม่บันทึก" ไม่ได้ แต่เห็น "ประวัติการใช้งาน" เต็มไปด้วยรายการเปล่า
 */
export function toBaseline(e: Event): EventCreate {
  return buildCreate(rowToValues(e))
}

/**
 * PATCH ส่ง **เฉพาะฟิลด์ที่ต่างจากเดิม** (กฎโปรเจค: `exclude_unset` ฝั่ง backend)
 * ⇒ ไม่เขียนทับคอลัมน์ที่ผู้ใช้ไม่ได้แตะ และ audit log บันทึกแต่ของจริงที่เปลี่ยน
 *
 * ⚠️ **เทียบจากค่าที่ normalize แล้วทั้งสองข้าง** ไม่ใช่ค่าดิบในฟอร์ม — `'  x  '` กับ `'x'`
 *    ต้องถือว่าเท่ากัน (เพราะ `buildCreate` trim ให้) ไม่งั้นผู้ใช้ที่เผลอเคาะท้ายช่องเดียว
 *    จะยิง PATCH ทั้งที่ไม่มีอะไรเปลี่ยน แล้ว audit log จะเต็มไปด้วยรายการเปล่า
 */
export function buildPatch(baseline: EventCreate, next: EventCreate): EventUpdate {
  const patch: EventUpdate = {}
  if (baseline.title !== next.title) patch.title = next.title
  if (baseline.description !== next.description) patch.description = next.description
  if (baseline.location !== next.location) patch.location = next.location
  if (baseline.cover_image_url !== next.cover_image_url) patch.cover_image_url = next.cover_image_url
  if (baseline.event_date !== next.event_date) patch.event_date = next.event_date
  if (baseline.registration_deadline !== next.registration_deadline) {
    patch.registration_deadline = next.registration_deadline
  }
  if (baseline.capacity !== next.capacity) patch.capacity = next.capacity
  if (baseline.category !== next.category) patch.category = next.category
  return patch
}

/**
 * ★ นิยาม "ยังไม่บันทึก" — **มีที่เดียวในระบบ**
 *
 * คิดจากตัวแทนที่ normalize แล้ว (`buildCreate`) เทียบกับ `baseline` ⇒ เป็นตัวเลขตัวเดียวกับ
 * ที่ `buildPatch` ใช้ตัดสินใจยิง API พอดี
 *
 * ⚠️ **ห้ามเขียนเป็น `JSON.stringify(form) !== JSON.stringify(original)`** — จะนับว่า
 *    "พิมพ์แล้วลบออก" เป็นการแก้ และจะนับเคาะท้ายว่าเป็นการแก้ ⇒ กล่อง "ยังไม่บันทึก" โผล่
 *    ทั้งที่กดบันทึกแล้วระบบจะไม่ยิงอะไรเลย (ผู้ใช้เห็นกล่องถามทั้งที่ไม่มีอะไรจะเสีย)
 */
export function isDirty(baseline: EventCreate, values: EventFormValues): boolean {
  return Object.keys(buildPatch(baseline, buildCreate(values))).length > 0
}

/**
 * ด่านฝั่ง client — ตรวจสิ่งที่ *รู้ได้โดยไม่ต้องถามเซิร์ฟเวอร์* เท่านั้น
 *
 * ⚠️ **ไม่ใช่ด่านจริง** — backend ตรวจซ้ำและเป็นผู้ตัดสิน (`registration_deadline` ต้องไม่หลัง
 *    `event_date` เป็นกติกาที่นี่ไม่ตรวจ เพราะต้องเทียบสองช่องแล้วอธิบายยาว ซึ่งทำได้ดีกว่า
 *    ที่ backend ด้วยข้อความจาก server เอง) · ที่นี่มีไว้เพื่อ **ไม่ให้ผู้ใช้กดบันทึกแล้วรอเฉย ๆ**
 *    เพื่อเจอ error ทั้งที่ช่องที่ขาดมองเห็นได้ด้วยตา
 */
export function formErrorOf(values: EventFormValues): string {
  if (!values.title.trim()) return 'ต้องกรอกชื่อกิจกรรม'
  if (!values.event_date) return 'ต้องเลือกวันและเวลาจัดกิจกรรม'
  const cap = values.capacity.trim()
  if (cap !== '') {
    const n = Number(cap)
    if (!Number.isInteger(n) || n < 1) return 'จำนวนที่นั่งต้องเป็นจำนวนเต็มตั้งแต่ 1 ขึ้นไป'
  }
  return ''
}

/**
 * ตัวเลือกใน `<select>` ของฟอร์ม — ปกติคือ `EVENT_CATEGORIES` ทั้งชุด
 *
 * ⭐ **แต่ถ้าหมวดของแถวที่กำลังแก้ไม่ใช่คีย์ที่ frontend รู้จัก** (backend ใหม่กว่า) ต้องเติม
 *    ค่านั้นเข้าไปเป็นตัวเลือก ไม่งั้น `<select>` จะแสดง **ว่าง** แล้วถ้าผู้ใช้กดบันทึก
 *    ค่าจะกลายเป็น `'other'` เงียบ ๆ — คือ **ลดชั้นข้อมูลโดยที่ผู้ใช้ไม่ได้สั่ง**
 *    (และคู่กับ `buildCreate()` ที่ไม่ส่งคีย์แปลกออกไป ⇒ ค่าเดิมใน DB ไม่ถูกแตะ)
 */
export function categoryOptionsOf(
  current: string,
): readonly { value: string; label: string }[] {
  const known = EVENT_CATEGORIES.map((c) => ({ value: c, label: CATEGORY_LABELS[c] }))
  return isEventCategory(current)
    ? known
    : [{ value: current, label: `${current} (ไม่รู้จัก)` }, ...known]
}
