import { describe, it, expect, beforeEach, vi } from 'vitest'

// mock axios instance — ทดสอบเฉพาะ service layer ไม่ต้องมี backend จริง
const { getMock } = vi.hoisted(() => ({
  getMock: vi.fn<(url: string, config?: unknown) => Promise<unknown>>(),
}))
vi.mock('@/services/api', () => ({ default: { get: getMock } }))

import { getMyActivity, getMyStats } from '@/services/me'
import {
  ACTIVITY_ICONS,
  ACTIVITY_TABS,
  ACTIVITY_VERBS,
  STAT_ITEMS,
  statsPeriodLabel,
  statsPeriodRange,
} from '@/types/me'
import type { ActivityType, PersonalStats, StatKey } from '@/types/me'

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

describe('getMyActivity (C1)', () => {
  beforeEach(() => {
    getMock.mockReset()
  })

  it('ยิง GET /api/me/activity และส่งตัวกรองตามที่ขอ', async () => {
    getMock.mockResolvedValue({ items: [], total: 0, counts: {} })

    await getMyActivity({ activity_type: 'vote_cast', limit: 20, offset: 20 })

    expect(getMock).toHaveBeenCalledTimes(1)
    expect(getMock).toHaveBeenCalledWith('/api/me/activity', {
      params: { activity_type: 'vote_cast', limit: 20, offset: 20 },
    })
  })

  it('★ ไม่มี filter → ต้องไม่ส่ง activity_type ไป (undefined ต้องไม่กลายเป็น string)', async () => {
    getMock.mockResolvedValue({ items: [], total: 0, counts: {} })

    await getMyActivity()

    const params = (getMock.mock.calls[0]![1] as { params: Record<string, unknown> }).params
    expect(params.activity_type).toBeUndefined()
    // ⚠️ ด่านความปลอดภัย: ตัวตนมาจาก JWT ฝั่ง backend เท่านั้น — ห้ามส่ง user_id
    expect(Object.keys(params)).not.toContain('user_id')
  })
})

describe('ACTIVITY_TABS — ต้องตรงกับป้าย/ไอคอน/คำกริยาที่ประกาศไว้', () => {
  const types = ACTIVITY_TABS.filter((t) => t.value !== '').map((t) => t.value)

  it('มีปุ่ม "ทั้งหมด" เป็นอันแรก และครอบกิจกรรมทั้ง 4 ประเภท', () => {
    expect(ACTIVITY_TABS[0]?.value).toBe('')
    expect(types).toHaveLength(4)
    expect(new Set(types).size).toBe(4)
  })

  it('ทุกประเภทมีไอคอนและคำกริยาครบ (เพิ่มประเภทใหม่แล้วลืมประกาศ = ปุ่มโชว์ไอคอนเปล่า)', () => {
    // เก็บชื่อที่ขาดใส่ array แล้วเทียบทีเดียว ⇒ ตอนพังจะเห็นชื่อที่ขาดในผลลัพธ์
    const missing = types.filter(
      (t) => !ACTIVITY_ICONS[t] || !ACTIVITY_VERBS[t],
    )
    expect(missing).toEqual([])
    expect(Object.keys(ACTIVITY_ICONS).sort()).toEqual([...types].sort())
    expect(Object.keys(ACTIVITY_VERBS).sort()).toEqual([...types].sort())
  })
})

describe('สัญญา C1 ↔ C3 — ยอดต่อประเภทใน feed ต้องเทียบกับตัวนับในสถิติได้', () => {
  /**
   * ⚠️ นี่คือสัญญาที่ `me_schemas.py` เขียนเตือนไว้ และเทสต์ A2 ฝั่ง backend บังคับด้วย
   *    ถ้าวันหนึ่งมีคนเพิ่มประเภทกิจกรรมใหม่โดยไม่เพิ่มตัวนับใน C3 (หรือกลับกัน)
   *    ตัวเลขสองหน้าจะไม่ตรงกันแล้วผู้ใช้จะอ่านว่าเป็นบั๊ก
   */
  const ACTIVITY_TO_STAT: Record<ActivityType, StatKey> = {
    issue_created: 'total_reported',
    vote_cast: 'votes_cast',
    board_comment_posted: 'board_comments_posted',
    issue_comment_posted: 'issue_comments_posted',
  }

  it('ทุกประเภทกิจกรรมต้องมีตัวนับคู่กัน และต้องเป็นตัวนับที่มีอยู่จริง', () => {
    const statKeys = STAT_ITEMS.map((s) => s.key)
    const missing = ACTIVITY_TABS.filter((t) => t.value !== '').filter(
      (t) => !statKeys.includes(ACTIVITY_TO_STAT[t.value as ActivityType]),
    ).map((t) => t.value)
    expect(missing).toEqual([])
  })

  it('ห้าม map สองประเภทไปตัวนับเดียวกัน (ไม่งั้นเทียบเลขกันไม่ได้)', () => {
    const mapped = Object.values(ACTIVITY_TO_STAT)
    expect(new Set(mapped).size).toBe(mapped.length)
  })
})
