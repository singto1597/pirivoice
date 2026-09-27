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
  listAnnouncements,
  createAnnouncement,
  updateAnnouncement,
  deleteAnnouncement,
  restoreAnnouncement,
} from '@/services/announcement'

describe('announcement services (จัดการประกาศ)', () => {
  beforeEach(() => {
    getMock.mockReset()
    postMock.mockReset()
    patchMock.mockReset()
    deleteMock.mockReset()
  })

  it('listAnnouncements → GET /api/announcements พร้อม limit/offset และ unwrap เป็น envelope', async () => {
    const fakeRes = {
      items: [{ id: 1, message: 'ประกาศ', priority: 'urgent', link: null }],
      total: 1,
      page: 1,
      page_size: 20,
      pages: 1,
    }
    getMock.mockResolvedValue(fakeRes)

    const result = await listAnnouncements({ status: 'active', limit: 20, offset: 0 })

    expect(getMock).toHaveBeenCalledTimes(1)
    expect(getMock).toHaveBeenCalledWith('/api/announcements', {
      params: { status: 'active', limit: 20, offset: 0 },
    })
    expect(result).toEqual(fakeRes)
  })

  it('listAnnouncements default: ไม่ส่ง status (ให้ backend ใช้ default active ของตัวเอง) แต่ส่ง limit/offset', async () => {
    getMock.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20, pages: 1 })

    await listAnnouncements()

    expect(getMock).toHaveBeenCalledWith('/api/announcements', {
      params: { status: undefined, limit: 20, offset: 0 },
    })
  })

  it('createAnnouncement → POST /api/announcements พร้อม payload ครบ', async () => {
    const created = { id: 9, message: 'ใหม่', priority: 'high', link: 'https://example.com' }
    postMock.mockResolvedValue(created)

    const result = await createAnnouncement({
      message: 'ใหม่',
      priority: 'high',
      link: 'https://example.com',
    })

    expect(postMock).toHaveBeenCalledWith('/api/announcements', {
      message: 'ใหม่',
      priority: 'high',
      link: 'https://example.com',
    })
    expect(result).toEqual(created)
  })

  it('updateAnnouncement → PATCH /api/announcements/{id} (ส่งเฉพาะฟิลด์ที่จะแก้)', async () => {
    patchMock.mockResolvedValue({ id: 9, priority: 'urgent' })

    await updateAnnouncement(9, { priority: 'urgent' })

    expect(patchMock).toHaveBeenCalledWith('/api/announcements/9', { priority: 'urgent' })
  })

  it('updateAnnouncement ส่ง link: null = สั่งล้างลิงก์ (ไม่ใช่ไม่ส่ง)', async () => {
    patchMock.mockResolvedValue({ id: 9, link: null })

    await updateAnnouncement(9, { link: null })

    expect(patchMock).toHaveBeenCalledWith('/api/announcements/9', { link: null })
  })

  it('deleteAnnouncement → DELETE /api/announcements/{id} (soft delete)', async () => {
    deleteMock.mockResolvedValue({ id: 9, deleted_at: '2026-09-27T10:00:00+07:00' })

    const result = await deleteAnnouncement(9)

    expect(deleteMock).toHaveBeenCalledWith('/api/announcements/9')
    expect(deleteMock).toHaveBeenCalledTimes(1)
    expect(result).toHaveProperty('deleted_at')
  })

  it('restoreAnnouncement → POST /api/announcements/{id}/restore (ไม่ใช่ PATCH)', async () => {
    postMock.mockResolvedValue({ id: 9, deleted_at: null })

    await restoreAnnouncement(9)

    expect(postMock).toHaveBeenCalledWith('/api/announcements/9/restore')
    // กัน regress: ถ้าเผลอเปลี่ยนไปใช้ PATCH endpoint /restore จะ 405
    expect(patchMock).not.toHaveBeenCalled()
  })
})
