import { describe, it, expect, beforeEach, vi } from 'vitest'

// mock axios instance — ทดสอบเฉพาะ service layer ไม่ต้องมี backend จริง
const { getMock } = vi.hoisted(() => ({
  getMock: vi.fn<(url: string, config?: unknown) => Promise<unknown>>(),
}))
vi.mock('@/services/api', () => ({ default: { get: getMock } }))

import { getMyStats } from '@/services/me'
import { STAT_ITEMS, statsPeriodLabel, statsPeriodRange } from '@/types/me'
import type { PersonalStats } from '@/types/me'

const TERM: PersonalStats['term'] = {
  id: 3,
  name: 'ภาคเรียนที่ 1/2569',
  start_date: '2026-05-16',
  end_date: '2026-10-10',
}

describe('me service (สถิติส่วนตัว)', () => {
  beforeEach(() => {
    getMock.mockReset()
  })

  it('getMyStats → GET /api/me/stats และไม่ส่ง user_id ไปกับ request', async () => {
    getMock.mockResolvedValue({ term: null })

    await getMyStats()

    expect(getMock).toHaveBeenCalledTimes(1)
    // ⚠️ ต้องมี arg เดียวเท่านั้น — ถ้าเผลอส่ง params อะไรไปด้วยจะกลายเป็นรั่วตัวตน
    expect(getMock).toHaveBeenCalledWith('/api/me/stats')
  })
})

describe('STAT_ITEMS — ผูกกับคีย์ของ PersonalStats', () => {
  it('มีครบ 6 ตัวนับ และคีย์ไม่ซ้ำกัน', () => {
    expect(STAT_ITEMS).toHaveLength(6)
    expect(new Set(STAT_ITEMS.map((s) => s.key)).size).toBe(6)
  })

  it('ทุกคีย์ที่ประกาศไว้มีอยู่จริงใน response (กันพิมพ์ผิดแล้วได้ undefined)', () => {
    const response = {
      term: null,
      total_reported: 1,
      resolved_count: 2,
      in_progress_count: 3,
      votes_cast: 4,
      board_comments_posted: 5,
      issue_comments_posted: 6,
    }

    // เก็บชื่อคีย์ที่ผิดใส่ array แล้วเทียบทีเดียว ⇒ ตอนพังจะเห็นชื่อคีย์ที่ผิดในผลลัพธ์
    const wrongKeys = STAT_ITEMS.filter(
      (item) => typeof response[item.key] !== 'number',
    ).map((item) => item.key)

    expect(wrongKeys).toEqual([])
  })
})

describe('statsPeriodLabel / statsPeriodRange', () => {
  it('ไม่มีภาค → บอกตรง ๆ ว่าเป็นสถิติทั้งหมด (ไม่ปล่อยให้เข้าใจผิดว่าเป็นตัวเลขของภาค)', () => {
    expect(statsPeriodLabel(null)).toBe('สถิติทั้งหมด (ยังไม่ได้ตั้งภาคเรียน)')
    expect(statsPeriodRange(null)).toBeNull()
  })

  it('มีภาค → ใช้ชื่อภาค และแสดงช่วงวันที่เป็น พ.ศ.', () => {
    expect(statsPeriodLabel(TERM)).toBe('สถิติภาคเรียนที่ 1/2569')
    expect(statsPeriodRange(TERM)).toBe('16 พ.ค. 2569 – 10 ต.ค. 2569')
  })

  it('วันที่ต้องไม่เพี้ยนจาก timezone (16 พ.ค. ต้องเป็น 16 ไม่ใช่ 15)', () => {
    // ⚠️ ถ้าใช้ new Date('2026-05-16') จะกลายเป็นเที่ยงคืน UTC → ไทยเป็น 07:00 ของวันที่ 16
    //    แต่ถ้าเครื่องตั้ง timezone เป็น UTC-x จะเพี้ยนเป็นวันที่ 15 ⇒ เทสนี้กันไว้
    expect(statsPeriodRange(TERM)).toContain('16 พ.ค.')
    expect(statsPeriodRange(TERM)).toContain('10 ต.ค.')
  })
})
