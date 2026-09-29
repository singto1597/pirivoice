import { describe, it, expect, beforeEach, vi } from 'vitest'

// mock axios instance — ทดสอบเฉพาะ service layer ไม่ต้องมี backend จริง
const { getMock, postMock, patchMock, putMock, deleteMock } = vi.hoisted(() => ({
  getMock: vi.fn<(url: string, config?: unknown) => Promise<unknown>>(),
  postMock: vi.fn<(url: string, data?: unknown) => Promise<unknown>>(),
  patchMock: vi.fn<(url: string, data?: unknown) => Promise<unknown>>(),
  putMock: vi.fn<(url: string, data?: unknown) => Promise<unknown>>(),
  deleteMock: vi.fn<(url: string) => Promise<unknown>>(),
}))
vi.mock('@/services/api', () => ({
  default: { get: getMock, post: postMock, patch: patchMock, put: putMock, delete: deleteMock },
}))

import {
  listTerms,
  createTerm,
  updateTerm,
  setCurrentTerm,
  deleteTerm,
  restoreTerm,
  getQuietHours,
  updateQuietHours,
} from '@/services/settings'

/**
 * ⚠️ **reset ทั้ง 5 ตัวที่ระดับไฟล์ ไม่ใช่แยกในแต่ละ `describe`**
 *
 * เดิมแต่ละ `describe` reset คนละชุด (ภาคเรียน = 5 ตัว · A8 = แค่ `get`/`put`) ⇒ เทสต์ในกลุ่ม A8
 * ที่ assert `expect(postMock).not.toHaveBeenCalled()` **เห็นประวัติการเรียกจากเทสต์กลุ่มภาคเรียน**
 * (`restoreTerm` ยิง `POST /api/settings/terms/7/restore` ทิ้งไว้) ⇒ fail ด้วยข้อความที่ชี้ผิดที่
 * ทั้งที่ `updateQuietHours` ไม่ได้ยิง POST เลย
 *
 * ⇒ **เทสต์ที่ assert "ไม่ถูกเรียก" พังทันทีถ้า mock ไม่ถูก reset** และจะพังเฉพาะตอนรันทั้งไฟล์
 *   (รันเดี่ยวผ่าน) — เป็นอาการที่หาเหตุยากที่สุดแบบหนึ่ง ⇒ ให้ reset ที่เดียวคุมทุก `describe`
 */
beforeEach(() => {
  getMock.mockReset()
  postMock.mockReset()
  patchMock.mockReset()
  putMock.mockReset()
  deleteMock.mockReset()
})

describe('settings services (ภาคเรียน)', () => {
  it('listTerms → GET /api/settings/terms พร้อม status/limit/offset', async () => {
    const fakeRes = { items: [{ id: 1, name: 'ภาคเรียนที่ 1/2569' }], total: 1, page: 1, page_size: 50, pages: 1 }
    getMock.mockResolvedValue(fakeRes)

    const result = await listTerms({ status: 'current', limit: 50, offset: 0 })

    expect(getMock).toHaveBeenCalledTimes(1)
    expect(getMock).toHaveBeenCalledWith('/api/settings/terms', {
      params: { status: 'current', limit: 50, offset: 0 },
    })
    expect(result).toEqual(fakeRes)
  })

  it('listTerms default: status ว่างถูกตัดเป็น undefined, limit/offset มีค่าเริ่มต้น', async () => {
    getMock.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 50, pages: 1 })

    await listTerms()

    expect(getMock).toHaveBeenCalledWith('/api/settings/terms', {
      params: { status: undefined, limit: 50, offset: 0 },
    })
  })

  it('createTerm → POST /api/settings/terms ส่งวันเป็น YYYY-MM-DD', async () => {
    const payload = {
      name: 'ภาคเรียนที่ 1/2569',
      start_date: '2026-05-16',
      end_date: '2026-10-10',
      is_current: true,
    }
    postMock.mockResolvedValue({ id: 7, ...payload })

    const result = await createTerm(payload)

    expect(postMock).toHaveBeenCalledWith('/api/settings/terms', payload)
    expect(result).toMatchObject({ id: 7 })
  })

  it('updateTerm → PATCH เฉพาะฟิลด์ที่ส่ง (partial)', async () => {
    patchMock.mockResolvedValue({ id: 7, name: 'ภาคเรียนที่ 2/2569' })

    await updateTerm(7, { name: 'ภาคเรียนที่ 2/2569' })

    // ⚠️ ต้องไม่ส่ง start_date/end_date ติดไปด้วย ไม่งั้นจะกลายเป็น full replace
    expect(patchMock).toHaveBeenCalledWith('/api/settings/terms/7', {
      name: 'ภาคเรียนที่ 2/2569',
    })
  })

  it('setCurrentTerm → POST /{id}/set-current (ไม่ใช่ PATCH)', async () => {
    postMock.mockResolvedValue({ id: 7, is_current: true })

    const result = await setCurrentTerm(7)

    expect(postMock).toHaveBeenCalledWith('/api/settings/terms/7/set-current')
    expect(patchMock).not.toHaveBeenCalled()
    expect(result).toEqual({ id: 7, is_current: true })
  })

  it('deleteTerm → DELETE /{id} (soft delete ฝั่ง backend)', async () => {
    deleteMock.mockResolvedValue({ id: 7, deleted_at: '2026-09-28T00:00:00Z' })

    const result = await deleteTerm(7)

    expect(deleteMock).toHaveBeenCalledWith('/api/settings/terms/7')
    expect(result).toMatchObject({ id: 7 })
  })

  it('restoreTerm → POST /{id}/restore', async () => {
    postMock.mockResolvedValue({ id: 7, deleted_at: null })

    const result = await restoreTerm(7)

    expect(postMock).toHaveBeenCalledWith('/api/settings/terms/7/restore')
    expect(result).toMatchObject({ deleted_at: null })
  })
})

describe('settings services (ช่วงเวลาไม่ส่งแจ้งเตือน A8)', () => {
  // ⚠️ ไม่มี `beforeEach` ที่นี่โดยเจตนา — ใช้ตัวที่ระดับไฟล์ (ด้านบน) ที่ reset ครบทั้ง 5 mock
  //    การเพิ่ม reset เฉพาะกลุ่มจะทำให้ `postMock`/`patchMock` กลับมาค้างข้ามกลุ่มอีก
  it('getQuietHours → GET /api/settings/quiet-hours (ไม่ส่ง params)', async () => {
    const fake = { enabled: true, start: '22:00', end: '06:00', updated_at: '2026-09-29T10:00:00Z' }
    getMock.mockResolvedValue(fake)

    const result = await getQuietHours()

    expect(getMock).toHaveBeenCalledTimes(1)
    // ⚠️ ไม่มี config เป็นอาร์กิวเมนต์ที่สอง — endpoint นี้ไม่รับ query param ใด ๆ
    expect(getMock).toHaveBeenCalledWith('/api/settings/quiet-hours')
    expect(result).toEqual(fake)
  })

  it('getQuietHours: updated_at = null (โรงเรียนยังไม่เคยตั้ง) ผ่านมาครบ', async () => {
    getMock.mockResolvedValue({ enabled: false, start: '22:00', end: '06:00', updated_at: null })

    const result = await getQuietHours()

    expect(result.updated_at).toBeNull()
    expect(result.enabled).toBe(false)
  })

  it('updateQuietHours → PUT (ไม่ใช่ PATCH/POST) ส่งครบ 3 ฟิลด์', async () => {
    const payload = { enabled: true, start: '22:00', end: '06:00' }
    putMock.mockResolvedValue({ ...payload, updated_at: '2026-09-29T10:00:00Z' })

    const result = await updateQuietHours(payload)

    // ⚠️ PUT = full replace ⇒ ต้องเป็น put ไม่ใช่ patch และต้องส่งครบทั้ง 3 คีย์
    expect(putMock).toHaveBeenCalledWith('/api/settings/quiet-hours', {
      enabled: true,
      start: '22:00',
      end: '06:00',
    })
    expect(patchMock).not.toHaveBeenCalled()
    expect(postMock).not.toHaveBeenCalled()
    expect(result).toMatchObject(payload)
  })

  it('updateQuietHours: ช่วงข้ามเที่ยงคืน (end < start) ถูกส่งตามจริง ไม่ถูกสลับฝั่ง client', async () => {
    putMock.mockResolvedValue({ enabled: true, start: '22:00', end: '06:00', updated_at: null })

    await updateQuietHours({ enabled: true, start: '22:00', end: '06:00' })

    const sent = putMock.mock.calls[0]![1] as { start: string; end: string }
    expect(sent.start).toBe('22:00')
    expect(sent.end).toBe('06:00')
  })

  it('updateQuietHours: ปิดสวิตช์พร้อม start === end ยังส่งได้ (การตรวจเป็นของ backend)', async () => {
    putMock.mockResolvedValue({ enabled: false, start: '00:00', end: '00:00', updated_at: null })

    await updateQuietHours({ enabled: false, start: '00:00', end: '00:00' })

    // ไม่มี pre-check ฝั่ง client โดยเจตนา — "ค่าที่ใช้ได้" มีนิยามเดียวที่ backend
    expect(putMock).toHaveBeenCalledWith('/api/settings/quiet-hours', {
      enabled: false,
      start: '00:00',
      end: '00:00',
    })
  })
})
