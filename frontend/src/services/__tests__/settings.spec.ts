import { describe, it, expect, beforeEach, vi } from 'vitest'

// mock axios instance — ทดสอบเฉพาะ service layer ไม่ต้องมี backend จริง
const { getMock, postMock, patchMock, deleteMock } = vi.hoisted(() => ({
  getMock: vi.fn<(url: string, config?: unknown) => Promise<unknown>>(),
  postMock: vi.fn<(url: string, data?: unknown) => Promise<unknown>>(),
  patchMock: vi.fn<(url: string, data?: unknown) => Promise<unknown>>(),
  deleteMock: vi.fn<(url: string) => Promise<unknown>>(),
}))
vi.mock('@/services/api', () => ({
  default: { get: getMock, post: postMock, patch: patchMock, delete: deleteMock },
}))

import {
  listTerms,
  createTerm,
  updateTerm,
  setCurrentTerm,
  deleteTerm,
  restoreTerm,
} from '@/services/settings'

describe('settings services (ภาคเรียน)', () => {
  beforeEach(() => {
    getMock.mockReset()
    postMock.mockReset()
    patchMock.mockReset()
    deleteMock.mockReset()
  })

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
