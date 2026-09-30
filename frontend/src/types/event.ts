// 📅 ประเภทข้อมูลกิจกรรม (Events) — D1
//
// 🎯 ที่นี่เป็น "แหล่งความจริงเดียว" ของสถานะกิจกรรม — `services/event.ts` และ view ทุกตัว
//    import จากที่นี่ ห้ามประกาศซ้ำที่อื่น (เพิ่มค่าใหม่แล้วจะลืมที่ใดที่หนึ่ง)
//
// ⚠️ ชื่อค่าทุกตัว **ต้องตรงกับ CHECK constraint ฝั่ง backend** (`chk_events_status` /
//    `chk_event_registrations_status` ใน migration 025) — เปลี่ยนที่นี่ที่เดียวไม่พอ

/** สถานะจริงของกิจกรรม (คอลัมน์ `events.status`) */
export type EventStatus = 'draft' | 'published' | 'cancelled'

/** ตัวกรองในหน้ารายการฝั่งผู้จัดการ (ตรงกับ `_STATUS_CONDITIONS` ฝั่ง backend) */
export type EventListStatus = 'live' | 'draft' | 'published' | 'cancelled' | 'deleted' | 'all'

/** ช่วงเวลาของหน้ารายการฝั่งนักเรียน (ตรงกับ `_PUBLIC_SCOPES` ฝั่ง backend) */
export type EventScope = 'upcoming' | 'past' | 'all'

/**
 * หมวดกิจกรรม (D4) — ค่าตายตัวชุดเดียวกับ `chk_events_category` (migration 026)
 *
 * ⚠️ **คีย์เป็นอังกฤษ แต่ป้ายที่ผู้เห็นเป็นไทย** — เก็บคำไทยลง DB แล้ววันหนึ่งจะมีคนพิมพ์
 *    "วิชาการ"/"วิชาการ " (มีเคาะท้าย) /"งานวิชาการ" ปนกัน แล้วการกรองจะพังเงียบ ๆ
 *    (บทเรียนเดียวกับ `board_type` — ดู migration 022)
 *
 * ⚠️ เพิ่มหมวดใหม่ = **ต้องออก migration** ไม่ใช่แก้ `init_db.py` (ซึ่งเป็น mirror)
 *    และต้องแก้ที่นี่ + `CATEGORY_LABELS`/`CATEGORY_ICONS` ให้ครบ
 */
export type EventCategory = 'academic' | 'sports' | 'arts' | 'service' | 'club' | 'meeting' | 'other'

/** สถานะการลงทะเบียนของคนหนึ่งในกิจกรรมหนึ่ง */
export type RegistrationStatus = 'registered' | 'waitlisted' | 'cancelled' | 'checked_in'

/**
 * ลิสต์ค่าไว้ใช้ใน `v-for` ของปุ่มตัวกรอง
 * (ต้องเป็น array literal ไม่ใช่ `Object.keys()` เพราะ key จาก `Record` จะถูก widen เป็น
 *  `string` แล้ว index `STATUS_LABELS[key]` จะไม่ผ่าน type-check แบบ strict —
 *  เหตุผลเดียวกับ `ENTITY_TYPES` ใน `types/bookmark.ts`)
 */
export const EVENT_LIST_STATUSES = [
  'live',
  'draft',
  'published',
  'cancelled',
  'deleted',
  'all',
] as const satisfies readonly EventListStatus[]

export const EVENT_SCOPES = ['upcoming', 'past', 'all'] as const satisfies readonly EventScope[]

/**
 * ลิสต์หมวดสำหรับ `v-for` ของปุ่มกรอง — **เรียงตามที่ผู้ใช้เห็น** ไม่ใช่ตามตัวอักษร
 * (`other` ต้องอยู่ท้ายสุดเสมอ ไม่งั้นมันจะไปแทรกกลางระหว่างหมวดจริง)
 */
export const EVENT_CATEGORIES = [
  'academic',
  'sports',
  'arts',
  'service',
  'club',
  'meeting',
  'other',
] as const satisfies readonly EventCategory[]

export const CATEGORY_LABELS: Record<EventCategory, string> = {
  academic: 'วิชาการ',
  sports: 'กีฬา/นันทนาการ',
  arts: 'ศิลปะ/ดนตรี',
  service: 'จิตอาสา',
  club: 'ชมรม',
  meeting: 'ประชุม/อบรม',
  other: 'อื่น ๆ',
}

export const CATEGORY_ICONS: Record<EventCategory, string> = {
  academic: 'bi-mortarboard',
  sports: 'bi-trophy',
  arts: 'bi-palette',
  service: 'bi-heart',
  club: 'bi-people',
  meeting: 'bi-easel',
  other: 'bi-tag',
}

/**
 * มุมมอง "เปิด" ของตารางป้าย — จำเป็นเพราะ **`category` ที่อ่านจาก API เป็น `string` เปล่า
 * ไม่ใช่ `EventCategory`** (output หลวมโดยเจตนา แบบเดียวกับ `status` — backend อาจมีหมวด
 * ใหม่กว่าที่ frontend รู้จัก)
 *
 * ⚠️ ห้ามใช้ `CATEGORY_LABELS[unknownKey]` ตรง ๆ — จะได้ `undefined` แล้วหน้าจอขึ้นช่องว่าง
 *    ซึ่งอ่านไม่ออกว่า "ไม่มีหมวด" หรือ "พัง"
 */
const CATEGORY_LABELS_BY_KEY: Record<string, string | undefined> = CATEGORY_LABELS

/** ป้ายภาษาไทยของหมวด — **คีย์ที่ไม่รู้จักคืนคีย์ดิบ** ดีกว่าเงียบ/ว่าง */
export function categoryLabel(key: string): string {
  return CATEGORY_LABELS_BY_KEY[key] ?? key
}

const CATEGORY_ICONS_BY_KEY: Record<string, string | undefined> = CATEGORY_ICONS

/** ไอคอนของหมวด — คีย์ที่ไม่รู้จักได้ไอคอนกลาง ๆ (ไม่ใช่ค่าว่างที่ทำให้ป้ายยุบหาย) */
export function categoryIcon(key: string): string {
  return CATEGORY_ICONS_BY_KEY[key] ?? 'bi-tag'
}

/**
 * แคบ `string` → `EventCategory` (type guard ของจริง ไม่ใช่ cast)
 *
 * ⚠️ **ห้ามแทนด้วย `as EventCategory`** — ค่าที่ไม่รู้จักจะผ่านด่านไปถึง payload แล้ว backend
 *    ตอบ 422 ซึ่งผู้ใช้เห็นเป็น "บันทึกไม่สำเร็จ" โดยไม่รู้ว่าอะไรผิด · ที่นี่เรา *ตัดสินใจ*
 *    กับค่าที่ไม่รู้จักได้ (ไม่ส่งไปเลย) ซึ่ง cast เปิดทางให้ทำไม่ได้
 */
export function isEventCategory(key: string): key is EventCategory {
  return CATEGORY_LABELS_BY_KEY[key] !== undefined
}

/**
 * ค่าหมวด → ค่าที่ **ส่งไป backend ได้** — คีย์ที่ไม่รู้จัก ⇒ `undefined` (**= ไม่ส่ง**)
 *
 * ⭐ ทำไมต้องเป็นชื่อฟังก์ชัน ไม่ใช่ inline ternary ในสองที่: ค่านี้ถูกใช้ **ทั้งสองข้าง**
 *    ของการเทียบ diff (`buildCreate` กับ `toBaseline`) ⇒ ถ้าข้างหนึ่งแปลงคีย์แปลกเป็นอย่างอื่น
 *    อีกข้างไม่แปลง diff จะ "เห็นว่าต่าง" แล้ว **ยิง PATCH ทับค่าที่ผู้ใช้ไม่ได้แตะ**
 *
 * 🚨 **ห้ามคืน `'other'` แทนคีย์ที่ไม่รู้จัก** — `'other'` เป็นค่าจริงที่มีความหมาย
 *    ("หมวดอื่น ๆ") ไม่ใช่ถังพักของ "ไม่รู้จัก" ⇒ คืนไปเมื่อไรคือ **ลดชั้นข้อมูลโดยผู้ใช้ไม่ได้สั่ง**
 *    และอ่านไม่ออกด้วยว่าถูกเขียนทับ · ฝั่งสร้างกิจกรรมไม่มีปัญหาเพราะ backend ใส่ DEFAULT ให้เอง
 */
export function categoryPayload(value: string): EventCategory | undefined {
  return isEventCategory(value) ? value : undefined
}

export const STATUS_LABELS: Record<EventStatus, string> = {
  draft: 'ฉบับร่าง',
  published: 'เผยแพร่แล้ว',
  cancelled: 'ยกเลิกแล้ว',
}

export const STATUS_ICONS: Record<EventStatus, string> = {
  draft: 'bi-pencil-square',
  published: 'bi-megaphone',
  cancelled: 'bi-x-octagon',
}

/** ป้ายบนปุ่มกรอง — `live` ไม่ใช่สถานะจริงแต่เป็น "ทุกอย่างที่ยังไม่ถูกลบ" */
export const LIST_STATUS_LABELS: Record<EventListStatus, string> = {
  live: 'ทั้งหมด',
  draft: 'ฉบับร่าง',
  published: 'เผยแพร่แล้ว',
  cancelled: 'ยกเลิกแล้ว',
  deleted: 'ถูกลบ',
  all: 'รวมที่ลบ',
}

export const SCOPE_LABELS: Record<EventScope, string> = {
  upcoming: 'กำลังจะมาถึง',
  past: 'ผ่านไปแล้ว',
  all: 'ทั้งหมด',
}

export const REGISTRATION_LABELS: Record<RegistrationStatus, string> = {
  registered: 'ได้ที่นั่ง',
  waitlisted: 'คิวสำรอง',
  cancelled: 'ยกเลิกแล้ว',
  checked_in: 'เช็คอินแล้ว',
}

export const REGISTRATION_ICONS: Record<RegistrationStatus, string> = {
  registered: 'bi-check-circle',
  waitlisted: 'bi-hourglass-split',
  cancelled: 'bi-dash-circle',
  checked_in: 'bi-person-check',
}

// ============ แถวจาก API ============

/**
 * กิจกรรมมุมมองผู้จัดการ — มี id ผู้สร้าง/ผู้แก้ + ชื่อที่ join มาให้
 *
 * ⚠️ `created_by`/`updated_by` เป็น INTEGER เปล่า **ไม่มี FK** ⇒ ชื่อเป็น null ได้
 *    (ผู้ใช้ถูกลบไปแล้ว) ⇒ UI ต้องมีข้อความสำรอง ไม่ใช่ปล่อยว่าง
 */
export interface Event {
  id: number
  title: string
  description: string | null
  location: string | null
  cover_image_url: string | null
  event_date: string
  registration_deadline: string | null
  /** `null` = ไม่จำกัดจำนวน (ไม่ใช่ 0 — `capacity` ต้อง > 0 ถ้ามีค่า) */
  capacity: number | null
  /**
   * หมวดกิจกรรม — **ประกาศเป็น `string` ไม่ใช่ `EventCategory` โดยเจตนา**
   *
   * ⚠️ เหตุผลเดียวกับ `status`: ฝั่ง backend ประกาศ `EventOut.category` เป็น `str` (input เข้ม ·
   *    output หลวม) ⇒ ถ้าที่นี่ประกาศเป็น union แคบ TypeScript จะ **โกหก** ว่าไม่มีทางได้ค่าอื่น
   *    แล้ววันที่ backend เพิ่มหมวดใหม่ หน้าจอจะพังตอน runtime ทั้งที่ type-check ผ่าน
   *    ⇒ ใช้ `categoryLabel()`/`categoryIcon()` ซึ่งมีทางถอยให้คีย์แปลกเสมอ
   */
  category: string
  status: EventStatus
  published_at: string | null
  cancelled_at: string | null
  created_at: string
  updated_at: string | null
  deleted_at: string | null
  created_by: number | null
  updated_by: number | null
  created_by_name: string | null
  updated_by_name: string | null
  registered_count: number
  waitlisted_count: number
}

/**
 * กิจกรรมมุมมองนักเรียน — **ไม่มี** ข้อมูลผู้ดูแล
 *
 * `seats_remaining` = null เมื่อไม่จำกัดจำนวน · `my_registration_status` = null เมื่อ
 * ยังไม่เคยสมัคร **หรือ** เคยยกเลิก (backend แปลง 'cancelled' เป็น null ให้แล้ว ⇒
 * UI แสดงเป็น "ยังไม่ได้สมัคร" ได้ตรง ๆ ไม่ต้องแยกกรณี)
 *
 * ⚠️ `is_registration_open` มาจาก server เสมอ — **ห้ามเทียบเวลาที่ frontend เอง**
 *    นาฬิกาเครื่องผู้ใช้เพี้ยนได้ และกติกาปิดรับเป็นกติกาของระบบ ไม่ใช่การแสดงผล
 */
export interface PublicEvent {
  id: number
  title: string
  description: string | null
  location: string | null
  cover_image_url: string | null
  event_date: string
  registration_deadline: string | null
  capacity: number | null
  /** ดูคำอธิบายที่ `Event.category` — หลวมโดยเจตนา ใช้ `categoryLabel()` อ่าน */
  category: string
  status: EventStatus
  published_at: string | null
  cancelled_at: string | null
  registered_count: number
  waitlisted_count: number
  seats_remaining: number | null
  is_registration_open: boolean
  /**
   * ⏳ เวลาที่ "ปิดรับ" จริง (4.5) = `min(วันจัด, กำหนดปิดรับ)` — คำนวณที่ SQL
   *
   * ⭐ **ต้องอ่านค่านี้ ไม่ใช่ `registration_deadline`** — กิจกรรมที่ไม่ได้ตั้งกำหนด
   *    ปิดรับจะปิดที่ *วันจัด* ⇒ `registration_deadline` เป็น `null` และฝั่งจอที่อ่าน
   *    แต่คอลัมน์นั้นจะสรุปว่า "ไม่มีการปิดรับ" แล้วไม่เตือนทั้งที่เป็นกลุ่มที่พลาดมากที่สุด
   *
   * ℹ️ ไม่เป็น `| null` — `LEAST(event_date, …)` โดยที่ `event_date` เป็น NOT NULL
   *    ⇒ ค่านี้เป็น NULL ไม่ได้ (ดูเหตุผลเต็มใน `EventPublicOut` ฝั่ง backend)
   */
  closes_at: string
  my_registration_status: RegistrationStatus | null
}

/** สถานะการสมัครของ *ฉัน* — ใช้เติมปุ่มในหน้า detail */
export interface MyRegistration {
  registered: boolean
  registration_id: number | null
  status: RegistrationStatus | null
  /** มีค่าเฉพาะตอน `status === 'waitlisted'` — ที่นั่งจริงไม่ต้องบอกลำดับ */
  queue_position: number | null
  /**
   * ข้อความสำหรับวาด **บัตรเช็คอิน** (D2) — `null` เมื่อยังไม่มีที่นั่ง
   *
   * ⚠️ ใช้ค่านี้เป็น **สวิตช์เดียว** ของ "จะโชว์บัตรไหม" — อย่าเทียบ `status` เองอีกรอบ
   *    ฝั่ง backend ตัดสินใจแล้วว่าใครได้บัตร (`_seat_token`) และสองที่จะเพี้ยนจากกันทันที
   *    ที่มีคนแก้กฎ (เช่นเพิ่มสถานะใหม่ที่ก็ควรได้บัตร)
   */
  check_in_token: string | null
  /**
   * เวลาที่เช็คอิน — มีค่า **ก็ต่อเมื่อ** `status === 'checked_in'`
   *
   * ⚠️ อย่าใช้ค่านี้เป็นเงื่อนไขว่า "เช็คอินหรือยัง" — ใช้ `status` · คู่นี้เป็น invariant
   *    ฝั่ง backend (ถอน/สมัครใหม่จะล้างค่านี้ทิ้ง) ⇒ ถ้ามันหลุดจากกันเมื่อไร นั่นคือบั๊ก
   *    ที่ต้องรายงาน ไม่ใช่เรื่องที่ UI ต้องเดาแก้
   */
  checked_in_at: string | null
}

/** ผลของการเช็คอินหนึ่งครั้ง (มุมมองสภา) — D2 */
export interface CheckInResult {
  registration_id: number
  event_id: number
  /** ⚠️ คือ **นักเรียนที่ถูกเช็คอิน** ไม่ใช่สภาที่กด (คนนั้นไม่ปรากฏใน response) */
  user_id: number
  user_name: string | null
  status: RegistrationStatus
  checked_in_at: string | null
  /** `true` = คนนี้เช็คอินไปแล้วก่อนหน้านี้ — **ไม่ใช่ error** (สแกนซ้ำเป็นเรื่องปกติ) */
  already_checked_in: boolean
  /** ทางที่รายการเข้ามา: `qr` = สแกนบัตร · `manual` = สภากดจากรายชื่อ */
  method: 'qr' | 'manual'
}

/**
 * สิ่งที่ส่งไปตอนเช็คอิน — **อย่างใดอย่างหนึ่งเท่านั้น** (backend บังคับด้วย 422)
 *
 * เขียนเป็น union ไม่ใช่ `{ token?: string; registration_id?: number }` โดยเจตนา:
 * แบบหลังยอมให้ส่ง `{}` ผ่าน type-check ได้ แล้วไปพังที่ 422 ซึ่งเป็นความผิดพลาด
 * ที่ TypeScript จับให้ได้ตั้งแต่ตอนคอมไพล์ ⇒ ให้มันจับ
 */
export type CheckInPayload = { token: string } | { registration_id: number }

/** หนึ่งแถวในรายชื่อผู้สมัคร (มุมมองสภา) */
export interface EventRegistration {
  id: number
  event_id: number
  user_id: number
  user_name: string | null
  status: RegistrationStatus
  registered_at: string
  cancelled_at: string | null
  checked_in_at: string | null
}

// ============ payload ที่ส่งไป ============

/**
 * สร้างกิจกรรม — ⚠️ **ไม่มี `status` โดยเจตนา**
 *
 * กิจกรรมเกิดเป็น 'draft' เสมอ และการเผยแพร่เป็นการกระทำแยก (`publishEvent`) ซึ่งเป็น
 * ที่เดียวที่ยิงแจ้งเตือน ⇒ ถ้าเพิ่ม `status` ที่นี่ จะเปิดทางเผยแพร่โดยไม่แจ้งใคร
 *
 * `event_date` ส่งเป็นสตริงจาก `<input type="datetime-local">` (`"2026-10-15T09:00"`)
 * ได้เลย — backend เติมเขตเวลา Asia/Bangkok ให้ถ้าไม่มี tzinfo
 */
export interface EventCreate {
  title: string
  description?: string | null
  location?: string | null
  cover_image_url?: string | null
  event_date: string
  registration_deadline?: string | null
  capacity?: number | null
  /**
   * หมวด (D4) — ไม่ส่ง = backend ใช้ `'other'` ให้ (คอลัมน์ `NOT NULL DEFAULT 'other'`)
   *
   * ⚠️ เป็น **`EventCategory` แคบ** ต่างจากตอนอ่าน (`Event.category` เป็น `string` หลวม)
   *    ⇒ ตอน PATCH ต้องแคบด้วย `isEventCategory()` ก่อนส่ง — ถ้าค่าปัจจุบันใน DB ไม่ใช่คีย์
   *    ที่เรารู้จัก (backend ใหม่กว่า) มันจะกลายเป็น `undefined` ⇒ **ไม่ถูกส่งไป ⇒ ค่าเดิม
   *    ไม่ถูกเขียนทับ** ซึ่งเป็นพฤติกรรมที่ต้องการ (ห้ามลดชั้นข้อมูลเพราะผู้ใช้แก้ช่องอื่น)
   */
  category?: EventCategory
}

/**
 * PATCH — ส่งเฉพาะฟิลด์ที่จะแก้ (ไม่ส่ง = ไม่แตะ · ส่ง `null` = สั่งล้างค่า)
 * ⚠️ ไม่มี `status` ด้วยเหตุผลเดียวกับ `EventCreate`
 */
export type EventUpdate = Partial<EventCreate>

// ============ envelope (เหมือน /api/audit-logs และหน้าจัดการอื่นทุกหน้า) ============

export interface EventListResponse {
  items: Event[]
  total: number
  page: number
  page_size: number
  pages: number
}

export interface PublicEventListResponse {
  items: PublicEvent[]
  total: number
  page: number
  page_size: number
  pages: number
}

export interface EventRegistrationListResponse {
  items: EventRegistration[]
  total: number
  page: number
  page_size: number
  pages: number
}

// ============ UI helper ============

/**
 * "ว่างอีก N ที่" — คืน null เมื่อไม่จำกัดจำนวน เพื่อให้ผู้เรียกเลือกข้อความเองได้
 * (ไม่คืน string ว่าง เพราะ "ไม่จำกัด" กับ "ไม่รู้" ต้องแยกออกจากกัน)
 */
export function seatsLabel(seatsRemaining: number | null): string | null {
  if (seatsRemaining === null) return null
  if (seatsRemaining <= 0) return 'เต็มแล้ว'
  return `ว่างอีก ${seatsRemaining} ที่`
}

/**
 * ⚠️ **คำเตือนเรื่องที่นั่งสำหรับ *การ์ดที่ต้องเตือนเท่านั้น*** — คืน `null` เมื่อไม่ใช่เรื่องด่วน
 *
 * 🚨 **ห้ามใช้ `seatsLabel()` แทนกัน** — สองตัวนี้ตอบคำถามคนละข้อ:
 *
 *    | ฟังก์ชัน | คำถาม | `remaining = 12` |
 *    |---|---|---|
 *    | `seatsLabel` | "เหลือกี่ที่?" | `'ว่างอีก 12 ที่'` |
 *    | `seatsWarning` | "ต้องรีบไหม?" | `null` (ไม่ต้องเตือน) |
 *
 *    ⇒ สลับกันเมื่อไหร่ บล็อก "ใกล้ปิดรับ" จะเต็มไปด้วยป้าย "ว่างอีก 40 ที่" ที่ไม่ได้บอกอะไร
 *      และเมื่อทุกแถวมีป้าย ป้ายก็ไม่มีความหมายอีกต่อไป (ปัญหาคลาสสิกของสัญญาณเตือน)
 *
 * ⚠️ `null` (ไม่จำกัดจำนวน) กับ `0` (เต็ม) คนละเรื่อง — `null` ต้องไม่มีป้าย ส่วน `0`
 *    ต้องขึ้น "เต็มแล้ว" **ไม่ใช่ซ่อน** เพราะกิจกรรมที่เต็มแล้วยัง "ไม่ปิดรับ" (สมัครได้
 *    แต่จะได้คิวสำรอง) ซึ่งเป็นข้อมูลที่คนอ่านต้องรู้ก่อนกด
 */
export function seatsWarning(seatsRemaining: number | null): string | null {
  if (seatsRemaining === null) return null
  if (seatsRemaining <= 0) return 'เต็มแล้ว — สมัครได้แต่จะได้คิวสำรอง'
  if (seatsRemaining <= 3) return `เหลืออีก ${seatsRemaining} ที่`
  return null
}

/**
 * จำนวนมิลลิวินาทีของเขตเวลาไทย — ใช้แปลง instant เป็น "วันตามปฏิทินไทย" (4.5)
 *
 * ⚠️ ต้องเป็นค่าคงที่บวก ไม่ใช่ `toLocaleString` — เพราะเราต้องการ *ดัชนีวัน* มาลบกัน
 *    ไม่ใช่ข้อความ ⇒ วิธีนี้ไม่ขึ้นกับ locale ของเบราว์เซอร์ (นักเรียนบางคนตั้งเครื่องเป็น
 *    EN/US ซึ่ง `th-TH` จะถูกเมิน) และ**ไม่ขึ้นกับ timezone เครื่อง** เพราะบวก offset เอง
 */
const BKK_OFFSET_MS = 7 * 60 * 60 * 1000
const DAY_MS = 24 * 60 * 60 * 1000

/** ดัชนีวันตามปฏิทินไทย (จำนวนวันนับจาก epoch) — ใช้ลบกันเพื่อหาผลต่าง "วัน" */
function bangkokDayIndex(d: Date): number {
  return Math.floor((d.getTime() + BKK_OFFSET_MS) / DAY_MS)
}

/**
 * ป้ายบอกว่าอีกนานแค่ไหนจะปิดรับ (4.5)
 * — "ปิดรับวันนี้ · เหลืออีก 3 ชม." / "ปิดรับพรุ่งนี้" / "ปิดรับในอีก 5 วัน"
 *
 * ⭐ **นับเป็น "วันตามปฏิทินไทย" ไม่ใช่ `diff / 24 ชม."** — ต่างกันจริง: กิจกรรมที่ปิด
 *    วันพรุ่งนี้ 01:00 น. กับตอนนี้ 23:00 น. ห่างกันแค่ 2 ชั่วโมง แต่นักเรียนอ่านว่า
 *    "พรุ่งนี้" ทันทีที่เที่ยงคืนผ่านไป ⇒ ถ้าใช้ 24-ชม. จะขึ้น "ปิดรับวันนี้" ทั้งคืน
 *    ซึ่งทำให้คนที่เปิดอ่านตอนดึกเข้าใจผิดว่าหมดเขตไปแล้ว
 *
 * ⚠️ รับ `closes_at` จาก backend (= `min(วันจัด, กำหนดปิดรับ)`) **ห้ามคำนวณเองที่นี่** —
 *    กิจกรรมที่ไม่ได้ตั้งกำหนดปิดรับจะปิดที่ *วันจัด* ซึ่งเป็นกลุ่มที่พลาดมากที่สุด
 *    เพราะไม่มี deadline ให้เห็น (ดูคอมเมนต์ใน `EventPublicOut.closes_at` ฝั่ง backend)
 *
 * ⚠️ `now` รับเข้ามาได้เพื่อให้เทสต์กำหนดเวลาเองได้ (ค่าเริ่มต้น = เวลาจริง)
 *    **ห้ามเรียก `new Date()` ข้างใน** ไม่งั้นเทสต์จะผูกกับเวลาที่รันและล้มแบบสุ่ม
 */
export function closingLabel(closesAt: string, now: Date = new Date()): string {
  const closes = new Date(closesAt)
  // วันที่เพี้ยน (ค่าที่ backend ส่งมาอ่านไม่ได้) → ไม่โยน — ป้ายที่ว่างเปล่าดีกว่าจอขาว
  if (Number.isNaN(closes.getTime())) return ''

  const diffMs = closes.getTime() - now.getTime()
  if (diffMs <= 0) return 'ปิดรับแล้ว'

  const dayDiff = bangkokDayIndex(closes) - bangkokDayIndex(now)
  if (dayDiff <= 0) {
    // ยังไม่ข้ามวันตามปฏิทิน ⇒ ปัดลง (บอก "4 ชม." ตอนเหลือ 3.5 จะทำให้คนเลื่อนไปทำอย่างอื่น)
    // แต่ไม่ต่ำกว่า 1 — "เหลืออีก 0 ชม." อ่านแล้วเหมือนหมดเขตแล้วทั้งที่ยังสมัครได้
    const hours = Math.max(1, Math.floor(diffMs / (60 * 60 * 1000)))
    return `ปิดรับวันนี้ · เหลืออีก ${hours} ชม.`
  }
  if (dayDiff === 1) return 'ปิดรับพรุ่งนี้'
  return `ปิดรับในอีก ${dayDiff} วัน`
}

/**
 * ป้าย "ฉันเกี่ยวข้องกับกิจกรรมนี้แล้วหรือยัง" (4.5) — คืน `null` = ยังไม่สมัคร
 *
 * ⭐ **คืน `null` ไม่ใช่ `''`** โดยเจตนา — `null` มีความหมายว่า "ยังไม่สมัคร ⇒ จอต้อง
 *    แสดง *ปุ่มสมัคร*" ส่วน `''` จะทำให้เทมเพลตต้องเขียน `v-if="x !== ''"` ซึ่งเป็น
 *    กติกาที่ซ่อนอยู่ในเทมเพลต (ย้ายออกมาเทสต์ไม่ได้ ตาม docs/rules/frontend.md)
 *
 * ⚠️ `'cancelled'` **ไม่ต้องมีเคส** — backend แปลงเป็น `null` ให้แล้วใน `_public_row()`
 *    เพราะ "ยกเลิกแล้ว" กับ "ยังไม่เคยสมัคร" ต้องเห็นเหมือนกัน (ทั้งคู่ = สมัครใหม่ได้)
 *    ⇒ ถ้าเผลอเพิ่มเคส 'cancelled' ที่นี่ จะไม่มีวันทำงาน และทำให้คนอ่านเข้าใจผิด
 *      ว่ามีทางที่ค่านั้นหลุดมาถึง
 *
 * ⚠️ `'waitlisted'` **ต้องมีป้าย ≠ "สมัครแล้ว"** — คนที่อยู่ในคิวสำรองยังไม่มีที่นั่ง
 *    ⇒ การขึ้น "สมัครแล้ว" จะทำให้เขาไม่ไปดูว่าตัวเองได้ที่นั่งหรือยัง
 */
export function registrationChip(status: string | null): string | null {
  if (status === 'checked_in') return 'เช็คอินแล้ว'
  if (status === 'registered') return 'สมัครแล้ว'
  if (status === 'waitlisted') return 'อยู่ในคิวสำรอง'
  return null
}

/** ลิงก์ไปหน้ารายละเอียด — ที่เดียวที่รู้ว่า path คืออะไร (ใช้ทั้งการ์ดและหลังกดลงทะเบียน) */
export function eventPath(eventId: number): string {
  return `/app/events/${eventId}`
}

/**
 * URL **เต็ม** ของกิจกรรม สำหรับเอาออกนอกแอพ (QR บนโปสเตอร์ · ลิงก์ใน LINE) — 4.4
 *
 * 🚨 **ต้องเป็น URL เต็มที่มี origin เสมอ ห้ามเอา `eventPath()` ไปฝัง QR ตรง ๆ** —
 *    QR ที่เก็บแค่ `/app/events/7` นั้น **มือถือสแกนแล้วเปิดไม่ได้เลย** เพราะไม่มีโดเมน
 *    ⇒ กล้องจะขึ้นว่า "ไม่พบข้อมูล" หรือค้นหา `app/events/7` บน Google
 *    · อาการจะดูเหมือน "QR พัง" ทั้งที่โค้ด QR ถูกทุกบรรทัด และหาสาเหตุยากมาก
 *
 * ⚠️ **รับ `origin` เข้ามา ไม่เรียก `window.location` เอง** — เพื่อให้เป็นฟังก์ชันบริสุทธิ์ที่
 *    เทสต์ได้ (โปรเจกต์นี้ไม่ mount component) และเผื่อวันที่ต้องสร้างลิงก์ให้โดเมนอื่น
 *
 * ⚠️ เดิมใช้ `new URL(path, origin)` แล้ว แต่เปลี่ยนเป็นต่อสตริงเพราะ:
 *    `new URL` **โยน** เมื่อ origin ไม่ใช่ URL ที่ถูกต้อง ⇒ ต้องมี try/catch ในเทมเพลต
 *    ทั้งที่ทางเดียวที่จะได้ origin แปลกคือ deployed ผิดที่ ซึ่งการต่อสตริงให้ผลที่อ่านออกกว่า
 *    (`"".concat('/app/events/7')` = `/app/events/7` ที่ยัง *เห็น* ว่าผิด) ไม่ใช่หน้าจอพัง
 *
 * @param origin `window.location.origin` ของผู้ใช้ปัจจุบัน — ตัด `/` ท้ายทิ้งก่อนต่อ
 */
export function eventShareUrl(eventId: number, origin: string): string {
  return `${origin.replace(/\/+$/, '')}${eventPath(eventId)}`
}

/**
 * สถานะของ **บัตรเช็คอิน** ที่จะแสดงในหน้า detail (D2)
 *
 * | ค่า | หน้าจอ |
 * |---|---|
 * | `qr` | วาดคิวอาร์ + รหัสตัวอักษร |
 * | `checked_in` | ตรา "เช็คอินแล้ว HH:MM" — **ไม่มีคิวอาร์** |
 * | `none` | ไม่มีบล็อกบัตรเลย |
 *
 * ⚠️ **`checked_in` ต้องไม่โชว์คิวอาร์** — การสแกนซ้ำไม่ได้ให้อะไร (backend ตอบ
 *    `already_checked_in` แล้วไม่เขียนทับเวลาเดิม) และการเห็นคิวอาร์ค้างอยู่ทำให้เข้าใจผิด
 *    ว่ายังต้องไปสแกนอีก ⇒ สองสภาพนี้ **แทนกัน ไม่ใช่ซ้อนกัน**
 *
 * ⚠️ **`check_in_token` เป็นตัวตัดสินหลักว่า "มีบัตรไหม"** ไม่ใช่การเทียบ `status` เอง
 *    เพราะฝั่ง backend เป็นคนออกบัตร (`_seat_token`) ⇒ ที่นี่ไม่ต้องรู้กฎนั้นซ้ำ
 *    ส่วนเงื่อนไข `event.status === 'cancelled'` เป็นเรื่อง **การแสดงผลล้วน ๆ**:
 *    กิจกรรมที่ถูกยกเลิกแล้วไม่ควรเหลือบัตรค้างให้ผู้ใช้งง ทั้งที่ป้ายแดง "ถูกยกเลิก"
 *    อยู่ข้างบนอยู่แล้ว (ตัว endpoint ยังยอมให้สภาเช็คอินย้อนหลังได้ตามเดิม)
 *
 * แยกออกมาเป็นฟังก์ชันบริสุทธิ์เพราะเป็น "ตารางความจริง" 4 ช่องที่พลาดง่าย
 * และซ่อนอยู่ในเทมเพลตจะทดสอบไม่ได้ (โปรเจกต์นี้ไม่ mount component ในเทสต์)
 */
export function checkInCardState(
  mine: Pick<MyRegistration, 'check_in_token' | 'status'> | null,
  event: Pick<PublicEvent, 'status'> | null,
): 'none' | 'qr' | 'checked_in' {
  if (!mine?.check_in_token) return 'none'
  if (event?.status === 'cancelled') return 'none'
  return mine.status === 'checked_in' ? 'checked_in' : 'qr'
}
