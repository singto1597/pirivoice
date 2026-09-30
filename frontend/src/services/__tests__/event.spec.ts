import { describe, it, expect, beforeEach, vi } from 'vitest'

// mock axios instance — ทดสอบเฉพาะ service layer ไม่ต้องมี backend จริง
const { getMock, postMock, patchMock, deleteMock } = vi.hoisted(() => ({
  getMock: vi.fn<(url: string, config?: unknown) => Promise<unknown>>(),
  postMock: vi.fn<(url: string, data?: unknown) => Promise<unknown>>(),
  patchMock: vi.fn<(url: string, data?: unknown) => Promise<unknown>>(),
  deleteMock: vi.fn<(url: string, config?: unknown) => Promise<unknown>>(),
}))
vi.mock('@/services/api', () => ({
  default: { get: getMock, post: postMock, patch: patchMock, delete: deleteMock },
}))

import {
  listPublicEvents,
  getPublicEvent,
  getMyRegistration,
  registerForEvent,
  cancelMyRegistration,
  listEvents,
  createEvent,
  updateEvent,
  publishEvent,
  cancelEvent,
  deleteEvent,
  restoreEvent,
  listRegistrations,
} from '@/services/event'
import { seatsLabel, eventPath } from '@/types/event'

describe('event services (D1 — ฝั่งนักเรียน)', () => {
  beforeEach(() => {
    getMock.mockReset()
    postMock.mockReset()
    patchMock.mockReset()
    deleteMock.mockReset()
  })

  it('listPublicEvents → GET /api/events/public พร้อม params และ unwrap envelope', async () => {
    const fakeRes = {
      items: [{ id: 1, title: 'กิจกรรมแรก' }],
      total: 3,
      page: 1,
      page_size: 20,
      pages: 1,
    }
    getMock.mockResolvedValue(fakeRes)

    const result = await listPublicEvents({ scope: 'upcoming' })

    expect(getMock).toHaveBeenCalledWith('/api/events/public', {
      params: { scope: 'upcoming', limit: 20, offset: 0 },
    })
    expect(result).toEqual(fakeRes)
  })

  it('listPublicEvents → ไม่ระบุ scope = ไม่ส่ง params.scope (ให้ backend ใช้ค่า default ของตัวเอง)', async () => {
    getMock.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20, pages: 0 })

    await listPublicEvents()

    // ★ ต้องเป็น `undefined` ไม่ใช่สตริงว่าง — `?scope=` จะชน `pattern=` ฝั่ง backend แล้วได้ 422
    //   ทั้งที่ผู้ใช้แค่เปิดหน้ารายการปกติ
    const [, config] = (getMock.mock.calls[0] ?? []) as [string, { params: Record<string, unknown> }]
    expect(config.params.scope).toBeUndefined()
    expect(config.params.limit).toBe(20)
  })

  it('listPublicEvents → ขนาดหน้า/หน้าเริ่มต้น override ได้', async () => {
    getMock.mockResolvedValue({ items: [], total: 0, page: 3, page_size: 5, pages: 0 })

    await listPublicEvents({ scope: 'past', limit: 5, offset: 10 })

    expect(getMock).toHaveBeenCalledWith('/api/events/public', {
      params: { scope: 'past', limit: 5, offset: 10 },
    })
  })

  it('getPublicEvent → GET /api/events/public/{id}', async () => {
    const fake = { id: 7, title: 'กิจกรรมเจ็ด', is_registration_open: true }
    getMock.mockResolvedValue(fake)

    const result = await getPublicEvent(7)

    expect(getMock).toHaveBeenCalledWith('/api/events/public/7')
    expect(result).toEqual(fake)
  })

  it('getMyRegistration → GET /api/events/{id}/my-registration (200 เสมอ ไม่ใช่ 404)', async () => {
    const fake = { registered: false, registration_id: null, status: null, queue_position: null }
    getMock.mockResolvedValue(fake)

    const result = await getMyRegistration(7)

    expect(getMock).toHaveBeenCalledWith('/api/events/7/my-registration')
    expect(result.registered).toBe(false)
  })

  it('registerForEvent → POST /api/events/{id}/register **ไม่มี body**', async () => {
    postMock.mockResolvedValue({ registered: true, registration_id: 11, status: 'registered', queue_position: null })

    const result = await registerForEvent(7)

    // ★ ต้องเรียกด้วย argument เดียว — ตัวตนมาจาก JWT และ endpoint ไม่รับอะไรเพิ่ม
    //   (ถ้าเผลอส่ง `user_id` ไป body จะกลายเป็นช่องโหว่ทันทีที่ backend เผลอรับ)
    expect(postMock).toHaveBeenCalledWith('/api/events/7/register')
    expect(postMock.mock.calls[0]).toHaveLength(1)
    expect(result.status).toBe('registered')
  })

  it('registerForEvent → ที่นั่งเต็มได้ waitlisted เป็นคำตอบปกติ ไม่ใช่ error', async () => {
    postMock.mockResolvedValue({ registered: true, registration_id: 12, status: 'waitlisted', queue_position: 3 })

    const result = await registerForEvent(7)

    expect(result.status).toBe('waitlisted')
    expect(result.queue_position).toBe(3)
  })

  it('cancelMyRegistration → DELETE /api/events/{id}/register', async () => {
    deleteMock.mockResolvedValue({ registered: false, registration_id: null, status: null, queue_position: null })

    const result = await cancelMyRegistration(7)

    expect(deleteMock).toHaveBeenCalledWith('/api/events/7/register')
    expect(result.registered).toBe(false)
  })
})

describe('event services (D1 — ฝั่งผู้จัดการ)', () => {
  beforeEach(() => {
    getMock.mockReset()
    postMock.mockReset()
    patchMock.mockReset()
    deleteMock.mockReset()
  })

  it('listEvents → GET /api/events พร้อม params (สถานะ/แบ่งหน้า)', async () => {
    const fake = { items: [{ id: 1, title: 'ร่าง' }], total: 1, page: 1, page_size: 20, pages: 1 }
    getMock.mockResolvedValue(fake)

    const result = await listEvents({ status: 'draft', limit: 20, offset: 0 })

    expect(getMock).toHaveBeenCalledWith('/api/events', {
      params: { status: 'draft', limit: 20, offset: 0 },
    })
    expect(result).toEqual(fake)
  })

  it('listEvents → ไม่ระบุสถานะ = ไม่ส่ง params.status (ให้ backend ใช้ default live)', async () => {
    getMock.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20, pages: 0 })

    await listEvents()

    const [, config] = (getMock.mock.calls[0] ?? []) as [string, { params: Record<string, unknown> }]
    expect(config.params.status).toBeUndefined()
  })

  it('createEvent → POST /api/events ส่งครบ 7 ฟิลด์ และ **ไม่มี `status`**', async () => {
    const fake = { id: 9, title: 'กิจกรรมใหม่', status: 'draft' }
    postMock.mockResolvedValue(fake)

    const result = await createEvent({
      title: 'กิจกรรมใหม่',
      description: 'รายละเอียด',
      location: 'หอประชุม',
      cover_image_url: 'https://example.com/a.jpg',
      event_date: '2026-10-15T09:00',
      registration_deadline: '2026-10-10T23:59',
      capacity: 50,
    })

    const [url, sentBody] = (postMock.mock.calls[0] ?? []) as [string, Record<string, unknown>]
    expect(url).toBe('/api/events')
    // ★ ด่านสำคัญ: `status` **ต้องไม่ถูกส่ง** — การเผยแพร่เป็นการกระทำแยก (`publishEvent`)
    //   ซึ่งเป็นที่เดียวที่ยิงแจ้งเตือน ⇒ ถ้ามีทางส่ง status ตอนสร้าง =
    //   เผยแพร่กิจกรรมโดยไม่มีใครได้รับแจ้งเตือน และจะไม่มีร่องรอยว่าทำไม
    expect(Object.keys(sentBody).sort()).toEqual([
      'capacity',
      'cover_image_url',
      'description',
      'event_date',
      'location',
      'registration_deadline',
      'title',
    ])
    expect(sentBody.status).toBeUndefined()
    // `datetime-local` ส่งสตริงไม่มี tz — backend เติม Asia/Bangkok ให้เอง
    expect(sentBody.event_date).toBe('2026-10-15T09:00')
    expect(result.status).toBe('draft')
  })

  it('createEvent → ส่งแค่ title + event_date ก็ได้ (ที่เหลือไม่มีค่า = ไม่จำกัด/ไม่ระบุ)', async () => {
    postMock.mockResolvedValue({ id: 10, title: 'กิจกรรมสั้น', status: 'draft' })

    await createEvent({ title: 'กิจกรรมสั้น', event_date: '2026-11-01T08:00' })

    const [, sentBody] = (postMock.mock.calls[0] ?? []) as [string, Record<string, unknown>]
    expect(Object.keys(sentBody).sort()).toEqual(['event_date', 'title'])
  })

  it('updateEvent → PATCH /api/events/{id} ส่งเฉพาะฟิลด์ที่จะแก้', async () => {
    patchMock.mockResolvedValue({ id: 9, title: 'แก้แล้ว', status: 'draft' })

    const result = await updateEvent(9, { title: 'แก้แล้ว' })

    expect(patchMock).toHaveBeenCalledWith('/api/events/9', { title: 'แก้แล้ว' })
    expect(result.title).toBe('แก้แล้ว')
  })

  it('updateEvent → ส่ง null ได้ = สั่งล้างค่า (ต่างจาก "ไม่ส่ง" = ไม่แตะ)', async () => {
    patchMock.mockResolvedValue({ id: 9, capacity: null, status: 'draft' })

    await updateEvent(9, { capacity: null, location: null })

    // ★ ต้องเป็น null จริง ไม่ถูกกรองออก — backend ใช้ `exclude_unset` ไม่ใช่ `exclude_none`
    //   ⇒ ถ้า service ฝั่งนี้เผลอ strip null ทิ้ง ผู้ใช้จะ "ลบที่ตั้งไม่ได้" และไม่มี error ให้เห็น
    expect(patchMock).toHaveBeenCalledWith('/api/events/9', { capacity: null, location: null })
  })

  it('updateEvent → ไม่มี status ในเพย์โหลดแม้ type จะยอมให้ส่ง', async () => {
    patchMock.mockResolvedValue({ id: 9, status: 'draft' })

    await updateEvent(9, { title: 'x' })

    const [, sentBody] = (patchMock.mock.calls[0] ?? []) as [string, Record<string, unknown>]
    expect(sentBody.status).toBeUndefined()
  })

  it('publishEvent → POST /api/events/{id}/publish ไม่มี body', async () => {
    postMock.mockResolvedValue({ id: 9, status: 'published', published_at: '2026-09-29T10:00:00Z' })

    const result = await publishEvent(9)

    expect(postMock).toHaveBeenCalledWith('/api/events/9/publish')
    expect(postMock.mock.calls[0]).toHaveLength(1)
    expect(result.status).toBe('published')
  })

  it('cancelEvent → POST /api/events/{id}/cancel', async () => {
    postMock.mockResolvedValue({ id: 9, status: 'cancelled', cancelled_at: '2026-09-29T11:00:00Z' })

    const result = await cancelEvent(9)

    expect(postMock).toHaveBeenCalledWith('/api/events/9/cancel')
    expect(result.status).toBe('cancelled')
  })

  it('deleteEvent → DELETE /api/events/{id} (soft delete — คืนแถวที่ถูกลบ)', async () => {
    deleteMock.mockResolvedValue({ id: 9, status: 'draft', deleted_at: '2026-09-29T12:00:00Z' })

    const result = await deleteEvent(9)

    expect(deleteMock).toHaveBeenCalledWith('/api/events/9')
    expect(result.deleted_at).not.toBeNull()
  })

  it('restoreEvent → POST /api/events/{id}/restore (ไม่แจ้งเตือนซ้ำ)', async () => {
    postMock.mockResolvedValue({ id: 9, status: 'published', deleted_at: null })

    const result = await restoreEvent(9)

    expect(postMock).toHaveBeenCalledWith('/api/events/9/restore')
    expect(result.deleted_at).toBeNull()
  })

  it('listRegistrations → GET /api/events/{id}/registrations (limit เริ่มต้น 50)', async () => {
    const fake = { items: [{ id: 1, user_name: 'สมชาย', status: 'registered' }], total: 1, page: 1, page_size: 50, pages: 1 }
    getMock.mockResolvedValue(fake)

    const result = await listRegistrations(9, { status: 'waitlisted' })

    expect(getMock).toHaveBeenCalledWith('/api/events/9/registrations', {
      params: { status: 'waitlisted', limit: 50, offset: 0 },
    })
    expect(result).toEqual(fake)
  })

  it('listRegistrations → ไม่ระบุสถานะ = ส่ง undefined (ได้ทั้งคิว เรียงตาม registered_at)', async () => {
    getMock.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 50, pages: 0 })

    await listRegistrations(9)

    const [, config] = (getMock.mock.calls[0] ?? []) as [string, { params: Record<string, unknown> }]
    expect(config.params.status).toBeUndefined()
  })
})

// ===== ตัวช่วยใน types/event =====
// ไม่มี type error ถ้าค่าเหล่านี้ผิด — แต่ผู้ใช้จะเห็นข้อความผิดบนการ์ดกิจกรรมทันที
describe('event type helpers', () => {
  it('seatsLabel → null = "ไม่จำกัด" (คืน null ไม่ใช่สตริงว่าง ให้ผู้เรียกเลือกข้อความเอง)', () => {
    expect(seatsLabel(null)).toBeNull()
  })

  it('seatsLabel → 0 = เต็มแล้ว (ไม่ใช่ "ว่างอีก 0 ที่")', () => {
    expect(seatsLabel(0)).toBe('เต็มแล้ว')
    expect(seatsLabel(-1)).toBe('เต็มแล้ว')
  })

  it('seatsLabel → ตัวเลขบวกบอกจำนวนจริง', () => {
    expect(seatsLabel(5)).toBe('ว่างอีก 5 ที่')
    expect(seatsLabel(1)).toBe('ว่างอีก 1 ที่')
  })

  it('eventPath → ลิงก์ไปหน้า detail ต้องอยู่ใต้ /app (ไม่ใช่ path ที่ router ทำ query หลุด)', () => {
    expect(eventPath(7)).toBe('/app/events/7')
  })
})
