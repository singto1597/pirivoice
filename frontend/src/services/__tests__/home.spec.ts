import { describe, it, expect, beforeEach, vi } from 'vitest'

// mock axios instance — ทดสอบเฉพาะ service layer ไม่ต้องมี backend จริง
const { getMock } = vi.hoisted(() => ({
  getMock: vi.fn<(url: string, config?: unknown) => Promise<unknown>>(),
}))
vi.mock('@/services/api', () => ({ default: { get: getMock } }))

import { getHomeSummary } from '@/services/home'
import { remainingLabel, voteCountLabel } from '@/types/home'

describe('home service (หน้าแรก)', () => {
  beforeEach(() => {
    getMock.mockReset()
  })

  it('getHomeSummary → GET /api/home/summary และไม่ส่ง user_id ไปกับ request', async () => {
    getMock.mockResolvedValue({})

    await getHomeSummary()

    expect(getMock).toHaveBeenCalledTimes(1)
    // ⚠️ ต้องมี arg เดียวเท่านั้น — เผลอส่ง params เมื่อไหร่คือช่องดูข้อมูลคนอื่น
    expect(getMock).toHaveBeenCalledWith('/api/home/summary')
  })
})

describe('remainingLabel — "และอีก N เรื่อง"', () => {
  it('ไม่มีอะไรเหลือ → null (ไม่ต้องแสดงบรรทัดเปล่า)', () => {
    expect(remainingLabel(5, 5)).toBeNull()
    expect(remainingLabel(3, 5)).toBeNull() // total น้อยกว่า shown = ไม่มีอะไรเหลือ
    expect(remainingLabel(0, 0)).toBeNull()
  })

  it('เหลือ → บอกจำนวนที่เหลือจริง', () => {
    expect(remainingLabel(9, 5)).toBe('และอีก 4 เรื่อง')
    expect(remainingLabel(6, 5)).toBe('และอีก 1 เรื่อง')
  })

  it('เปลี่ยนคำนามได้ — คิวบอร์ดใช้ "บอร์ด" ไม่ใช่ "เรื่อง"', () => {
    expect(remainingLabel(9, 5, 'บอร์ด')).toBe('และอีก 4 บอร์ด')
  })
})

describe('voteCountLabel', () => {
  it('ยังไม่มีโหวต → ชวนเป็นคนแรก (ไม่ใช่ "0 คน" ที่อ่านแล้วหงอย)', () => {
    expect(voteCountLabel(0)).toBe('ยังไม่มีใครโหวต — คุณเป็นคนแรกได้')
  })

  it('มีโหวตแล้ว → บอกจำนวน', () => {
    expect(voteCountLabel(7)).toBe('มีผู้โหวตแล้ว 7 คน')
  })
})
