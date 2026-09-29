import { describe, it, expect, beforeEach, vi } from 'vitest'

// mock axios instance — ทดสอบเฉพาะ service layer ไม่ต้องมี backend จริง
const { getMock, postMock, deleteMock } = vi.hoisted(() => ({
  getMock: vi.fn<(url: string, config?: unknown) => Promise<unknown>>(),
  postMock: vi.fn<(url: string, body?: unknown) => Promise<unknown>>(),
  deleteMock: vi.fn<(url: string) => Promise<unknown>>(),
}))
vi.mock('@/services/api', () => ({
  default: { get: getMock, post: postMock, delete: deleteMock },
}))

import {
  createBookmark,
  deleteBookmark,
  getBookmarkStatus,
  listBookmarks,
} from '@/services/bookmark'
import { ENTITY_ICONS, ENTITY_LABELS, ENTITY_TYPES, bookmarkPath } from '@/types/bookmark'

describe('bookmark service', () => {
  beforeEach(() => {
    getMock.mockReset()
    postMock.mockReset()
    deleteMock.mockReset()
  })

  it('listBookmarks → GET /api/bookmarks และส่งตัวกรองตามที่ขอ', async () => {
    getMock.mockResolvedValue({ items: [], total: 0 })

    await listBookmarks({ entity_type: 'board', limit: 20, offset: 40 })

    expect(getMock).toHaveBeenCalledTimes(1)
    expect(getMock).toHaveBeenCalledWith('/api/bookmarks', {
      params: { entity_type: 'board', limit: 20, offset: 40 },
    })
  })

  it('listBookmarks ไม่ส่ง entity_type เมื่อไม่กรอง (undefined ไม่ควรกลายเป็น string "undefined")', async () => {
    getMock.mockResolvedValue({ items: [], total: 0 })

    await listBookmarks()

    const params = (getMock.mock.calls[0]![1] as { params: Record<string, unknown> }).params
    expect(params.entity_type).toBeUndefined()
  })

  it('getBookmarkStatus → ส่ง entity_type/entity_id ทาง query', async () => {
    getMock.mockResolvedValue({ bookmarked: false, bookmark_id: null })

    await getBookmarkStatus('issue', 5)

    expect(getMock).toHaveBeenCalledWith('/api/bookmarks/status', {
      params: { entity_type: 'issue', entity_id: 5 },
    })
  })

  it('★ createBookmark ส่งเฉพาะ entity_type/entity_id — ไม่มี user_id ติดไปด้วย', async () => {
    postMock.mockResolvedValue({ id: 1 })

    await createBookmark('issue', 5)

    expect(postMock).toHaveBeenCalledTimes(1)
    expect(postMock).toHaveBeenCalledWith('/api/bookmarks', { entity_type: 'issue', entity_id: 5 })

    // ⚠️ ด่านความปลอดภัย: ตัวตนต้องมาจาก JWT ฝั่ง backend เท่านั้น
    const body = postMock.mock.calls[0]?.[1] as Record<string, unknown>
    expect(Object.keys(body).sort()).toEqual(['entity_id', 'entity_type'])
    expect(body).not.toHaveProperty('user_id')
  })

  it('deleteBookmark → DELETE ที่ id ของตัวเอง (ไม่ส่ง user_id ไปด้วย)', async () => {
    deleteMock.mockResolvedValue(undefined)

    await deleteBookmark(11)

    expect(deleteMock).toHaveBeenCalledTimes(1)
    expect(deleteMock).toHaveBeenCalledWith('/api/bookmarks/11')
  })
})

describe('bookmarkPath — เส้นทางต้องตรงกับ route จริงใน router/index.ts', () => {
  it('issue → /app/issues/:id', () => {
    expect(bookmarkPath('issue', 5)).toBe('/app/issues/5')
  })

  it('board → /app/boards/:id', () => {
    expect(bookmarkPath('board', 7)).toBe('/app/boards/7')
  })
})

describe('ENTITY_TYPES — ต้องตรงกับป้าย/ไอคอนที่ประกาศไว้', () => {
  it('ครอบทุกชนิดที่ประกาศใน ENTITY_LABELS และ ENTITY_ICONS', () => {
    // ถ้าเพิ่มชนิดใหม่แล้วลืมเพิ่มใน ENTITY_TYPES ปุ่มตัวกรองจะหายไปเงียบ ๆ
    expect([...ENTITY_TYPES].sort()).toEqual(Object.keys(ENTITY_LABELS).sort())
    expect([...ENTITY_TYPES].sort()).toEqual(Object.keys(ENTITY_ICONS).sort())
  })

  it('ไม่มีชนิดซ้ำ', () => {
    expect(new Set(ENTITY_TYPES).size).toBe(ENTITY_TYPES.length)
  })
})
