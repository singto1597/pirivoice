import api from './api'
import type {
  CheckInPayload,
  CheckInResult,
  Event,
  EventCategory,
  EventCreate,
  EventListResponse,
  EventListStatus,
  EventRegistrationListResponse,
  EventScope,
  EventUpdate,
  MyRegistration,
  PublicEvent,
  PublicEventListResponse,
  RegistrationStatus,
} from '@/types/event'

// 📅 Events API — D1
//
// ⚠️ สองมุมมองอยู่ในไฟล์นี้โดยเจตนา (backend ก็รวมไว้ไฟล์เดียวเหมือนกัน):
//    • ฝั่งนักเรียน (/api/events/public*, /api/events/{id}/register) — **ไม่ต้องมีสิทธิ์พิเศษ**
//      ต่างกันแค่ `my_registration_status` ซึ่งมาจาก JWT ⇒ ต้องล็อกอิน แต่ไม่ต้องมี MANAGE_EVENTS
//    • ฝั่งผู้จัดการ (/api/events, publish, cancel, …) — backend ตรวจ MANAGE_EVENTS ใน service
//      ⇒ frontend **ไม่ต้องส่งอะไรเกี่ยวกับสิทธิ์ไปเลย** (ตัวตนคือสิทธิ์)
//
// ⚠️ ห้ามส่ง user_id ไปกับ request เด็ดขาด — backend เอาจาก JWT เสมอ

// ============ ฝั่งนักเรียน ============

export async function listPublicEvents(
  params: {
    scope?: EventScope
    /** หมวด (D4) — ไม่ส่ง = ทุกหมวด (⚠️ ต่างจาก `category: 'other'` ที่แปลว่า "เฉพาะอื่น ๆ") */
    category?: EventCategory
    limit?: number
    offset?: number
  } = {},
): Promise<PublicEventListResponse> {
  const { scope, category, limit, offset } = params
  return (await api.get('/api/events/public', {
    params: {
      // ส่ง scope เฉพาะเมื่อระบุ — ให้ backend ใช้ค่า default 'upcoming' ของตัวเอง
      scope: scope || undefined,
      // ⚠️ **`undefined` = ทุกหมวด** ไม่ใช่ค่าเริ่มต้นอย่าง `'other'` ⇒ ห้ามใส่ `?? 'other'`
      //    (จะกลายเป็น "กรองเอาแต่หมวดอื่น ๆ" ซึ่งไม่มีใครขอ และหาสาเหตุยากมาก)
      category: category || undefined,
      limit: limit ?? 20,
      offset: offset ?? 0,
    },
  })) as PublicEventListResponse
}

export async function getPublicEvent(eventId: number): Promise<PublicEvent> {
  return (await api.get(`/api/events/public/${eventId}`)) as PublicEvent
}

/**
 * สถานะการสมัครของฉัน — คืน 200 พร้อม `registered: false` เสมอเมื่อยังไม่สมัคร
 * (ไม่ใช่ 404 ⇒ ไม่ต้อง try/catch เพื่อแยก "ยังไม่สมัคร" ออกจาก "ไม่มีกิจกรรมนี้")
 */
export async function getMyRegistration(eventId: number): Promise<MyRegistration> {
  return (await api.get(`/api/events/${eventId}/my-registration`)) as MyRegistration
}

/**
 * ลงทะเบียน — ที่นั่งเต็มจะได้ `status: 'waitlisted'` **โดยไม่เป็น error**
 * ⇒ UI ต้องดู `status` ที่คืนมา ไม่ใช่ดูแค่ว่าคำขอสำเร็จ
 */
export async function registerForEvent(eventId: number): Promise<MyRegistration> {
  return (await api.post(`/api/events/${eventId}/register`)) as MyRegistration
}

/** ถอนการลงทะเบียนตัวเอง — backend จะเลื่อนคิวถัดไปขึ้นมาแทนให้ทันทีถ้าเราถือที่นั่งจริง */
export async function cancelMyRegistration(eventId: number): Promise<MyRegistration> {
  return (await api.delete(`/api/events/${eventId}/register`)) as MyRegistration
}

// ============ ฝั่งผู้จัดการ (ต้องมี MANAGE_EVENTS) ============

export async function listEvents(
  params: {
    status?: EventListStatus
    /** หมวด (D4) — ไม่ส่ง = ทุกหมวด (เหมือนฝั่ง public) */
    category?: EventCategory
    limit?: number
    offset?: number
  } = {},
): Promise<EventListResponse> {
  const { status, category, limit, offset } = params
  return (await api.get('/api/events', {
    params: {
      status: status || undefined,
      category: category || undefined,
      limit: limit ?? 20,
      offset: offset ?? 0,
    },
  })) as EventListResponse
}

/** สร้างกิจกรรม — เกิดเป็น **ฉบับร่าง** เสมอ และยังไม่แจ้งเตือนใคร (ดู `EventCreate`) */
export async function createEvent(payload: EventCreate): Promise<Event> {
  return (await api.post('/api/events', payload)) as Event
}

export async function updateEvent(eventId: number, payload: EventUpdate): Promise<Event> {
  return (await api.patch(`/api/events/${eventId}`, payload)) as Event
}

/**
 * เผยแพร่ — **ที่นี่ที่เดียวที่ยิงแจ้งเตือนหาทุกคน**
 * ⚠️ เผยแพร่ได้ครั้งเดียว (ร่าง → เผยแพร่) · ร่างที่วันจัดผ่านไปแล้วจะได้ 400 พร้อมบอกทางออก
 */
export async function publishEvent(eventId: number): Promise<Event> {
  return (await api.post(`/api/events/${eventId}/publish`)) as Event
}

/** ยกเลิกกิจกรรมที่เผยแพร่แล้ว — แจ้งผู้สมัครทุกคน แต่ **ไม่เลื่อนคิว** */
export async function cancelEvent(eventId: number): Promise<Event> {
  return (await api.post(`/api/events/${eventId}/cancel`)) as Event
}

/** ลบกิจกรรม (soft delete) — หายจากรายการแต่กู้คืนได้ */
export async function deleteEvent(eventId: number): Promise<Event> {
  return (await api.delete(`/api/events/${eventId}`)) as Event
}

/** กู้คืนกิจกรรมที่ถูกลบ — **ไม่แจ้งเตือนซ้ำ** (คนที่เคยได้รับแล้วจะได้สองครั้งถ้าแจ้ง) */
export async function restoreEvent(eventId: number): Promise<Event> {
  return (await api.post(`/api/events/${eventId}/restore`)) as Event
}

/**
 * รายชื่อผู้สมัครของกิจกรรมหนึ่ง — เรียงตามคิวจริง (ได้ที่นั่งก่อน แล้วค่อยคิวสำรอง)
 * ⚠️ กิจกรรมที่ไม่มี/ถูกลบ = 404 (**ไม่ใช่ลิสต์ว่าง**) — "ไม่มีกิจกรรม" กับ "ไม่มีคนสมัคร"
 *    เป็นคนละคำตอบ และลิสต์ว่างจะกลืนความต่างนั้นหายไป
 */
export async function listRegistrations(
  eventId: number,
  params: { status?: RegistrationStatus; limit?: number; offset?: number } = {},
): Promise<EventRegistrationListResponse> {
  const { status, limit, offset } = params
  return (await api.get(`/api/events/${eventId}/registrations`, {
    params: {
      status: status || undefined,
      limit: limit ?? 50,
      offset: offset ?? 0,
    },
  })) as EventRegistrationListResponse
}

/**
 * เช็คอินผู้เข้าร่วม (D2) — สแกนบัตร (`token`) หรือกดมือ (`registration_id`)
 *
 * ⚠️ **สแกนซ้ำไม่ error** — ได้ 200 พร้อม `already_checked_in: true` เสมอ
 *    ⇒ ผู้เรียกต้องเช็คค่านี้ถ้าต้องการข้อความที่ต่างกัน ไม่ใช่ดูแค่ว่าคำขอสำเร็จ
 *    (เหตุผลเดียวกับ `registerForEvent` ที่ต้องดู `status` ไม่ใช่ดูแค่ success)
 */
export async function checkInRegistration(
  eventId: number,
  payload: CheckInPayload,
): Promise<CheckInResult> {
  return (await api.post(`/api/events/${eventId}/check-in`, payload)) as CheckInResult
}
