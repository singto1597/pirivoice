import { describe, it, expect, beforeEach, vi } from 'vitest'

// mock axios instance — ทดสอบเฉพาะ service layer ไม่ต้องมี backend จริง
const { getMock, postMock, putMock } = vi.hoisted(() => ({
  getMock: vi.fn<(url: string, config?: unknown) => Promise<unknown>>(),
  postMock: vi.fn<(url: string, data?: unknown) => Promise<unknown>>(),
  putMock: vi.fn<(url: string, data?: unknown) => Promise<unknown>>(),
}))
vi.mock('@/services/api', () => ({
  default: { get: getMock, post: postMock, put: putMock },
}))

import {
  listNotifications,
  getUnreadCounts,
  markRead,
  getNotificationPreferences,
  updateNotificationPreferences,
} from '@/services/notification'

describe('notification services (รายการ/นับ/อ่านแล้ว)', () => {
  beforeEach(() => {
    getMock.mockReset()
    postMock.mockReset()
    putMock.mockReset()
  })

  it('listNotifications → GET /api/notifications พร้อม params และ unwrap เป็น envelope', async () => {
    const fakeRes = {
      items: [{ id: 1, group_type: 'issue_mine', title: 'อัปเดต', read_at: null }],
      total: 1,
      page: 1,
      page_size: 50,
      pages: 1,
    }
    getMock.mockResolvedValue(fakeRes)

    const result = await listNotifications({ group_type: 'issue_mine', unread_only: true, limit: 50, offset: 0 })

    expect(getMock).toHaveBeenCalledTimes(1)
    expect(getMock).toHaveBeenCalledWith('/api/notifications', {
      params: { group_type: 'issue_mine', unread_only: true, limit: 50, offset: 0 },
    })
    expect(result).toEqual(fakeRes)
  })

  it('listNotifications default: ไม่ส่ง param ว่าง (undefined ถูกตัด)', async () => {
    getMock.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 50, pages: 0 })

    await listNotifications()

    expect(getMock).toHaveBeenCalledWith('/api/notifications', {
      params: { group_type: undefined, unread_only: undefined, limit: 50, offset: 0 },
    })
  })

  it('getUnreadCounts → GET /api/notifications/unread-count', async () => {
    const fakeRes = { counts: { issue_mine: 1, issue_received: 0, board: 3, report: 0 }, total: 4 }
    getMock.mockResolvedValue(fakeRes)

    const result = await getUnreadCounts()

    expect(getMock).toHaveBeenCalledWith('/api/notifications/unread-count')
    expect(result).toEqual(fakeRes)
  })

  it('markRead({ ids }) → POST /api/notifications/read ส่ง ids', async () => {
    postMock.mockResolvedValue({ updated: 2 })

    const result = await markRead({ ids: [1, 2] })

    expect(postMock).toHaveBeenCalledWith('/api/notifications/read', { ids: [1, 2] })
    expect(result).toEqual({ updated: 2 })
  })

  it('markRead({ board_id }) → POST พร้อม board_id', async () => {
    postMock.mockResolvedValue({ updated: 1 })

    const result = await markRead({ board_id: 7 })

    expect(postMock).toHaveBeenCalledWith('/api/notifications/read', { board_id: 7 })
    expect(result).toEqual({ updated: 1 })
  })

  it('markRead({ read_all: true }) → POST พร้อม read_all', async () => {
    postMock.mockResolvedValue({ updated: 5 })

    const result = await markRead({ read_all: true })

    expect(postMock).toHaveBeenCalledWith('/api/notifications/read', { read_all: true })
    expect(result).toEqual({ updated: 5 })
  })
})

describe('notification preferences (ตั้งค่ารายกลุ่ม)', () => {
  beforeEach(() => {
    getMock.mockReset()
    postMock.mockReset()
    putMock.mockReset()
  })

  it('getNotificationPreferences → GET /api/notifications/preferences', async () => {
    const fakeRes = {
      preferences: [
        { group_type: 'issue_mine', enabled: true },
        { group_type: 'issue_received', enabled: true },
        { group_type: 'board', enabled: false },
        { group_type: 'report', enabled: true },
      ],
    }
    getMock.mockResolvedValue(fakeRes)

    const result = await getNotificationPreferences()

    expect(getMock).toHaveBeenCalledTimes(1)
    expect(getMock).toHaveBeenCalledWith('/api/notifications/preferences')
    expect(result).toEqual(fakeRes)
  })

  it('updateNotificationPreferences → PUT พร้อมซอง { preferences }', async () => {
    const fakeRes = { preferences: [{ group_type: 'board', enabled: false }] }
    putMock.mockResolvedValue(fakeRes)

    const result = await updateNotificationPreferences([{ group_type: 'board', enabled: false }])

    // ⚠️ ต้องห่อด้วย key `preferences` ให้ตรงกับ UpdateNotificationPreferencesRequest
    expect(putMock).toHaveBeenCalledWith('/api/notifications/preferences', {
      preferences: [{ group_type: 'board', enabled: false }],
    })
    expect(result).toEqual(fakeRes)
  })

  it('updateNotificationPreferences ส่งได้หลายกลุ่มในคำขอเดียว', async () => {
    putMock.mockResolvedValue({ preferences: [] })

    await updateNotificationPreferences([
      { group_type: 'issue_mine', enabled: false },
      { group_type: 'report', enabled: false },
    ])

    expect(putMock).toHaveBeenCalledWith('/api/notifications/preferences', {
      preferences: [
        { group_type: 'issue_mine', enabled: false },
        { group_type: 'report', enabled: false },
      ],
    })
  })

  it('ใช้ PUT ไม่ใช่ PATCH/POST (endpoint idempotent — ส่งซ้ำผลเท่าเดิม)', async () => {
    putMock.mockResolvedValue({ preferences: [] })

    await updateNotificationPreferences([{ group_type: 'board', enabled: true }])

    expect(putMock).toHaveBeenCalledTimes(1)
    expect(postMock).not.toHaveBeenCalled()
  })
})
