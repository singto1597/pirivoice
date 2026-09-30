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
  status: EventStatus
  published_at: string | null
  cancelled_at: string | null
  registered_count: number
  waitlisted_count: number
  seats_remaining: number | null
  is_registration_open: boolean
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

/** ลิงก์ไปหน้ารายละเอียด — ที่เดียวที่รู้ว่า path คืออะไร (ใช้ทั้งการ์ดและหลังกดลงทะเบียน) */
export function eventPath(eventId: number): string {
  return `/app/events/${eventId}`
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
