import { describe, it, expect } from 'vitest'
import {
  historyScreenState,
  historyYearLabel,
  moveConfirmText,
  moveLabel,
  moveResultText,
  STUDENT_STATUS_LABELS,
  type BulkMoveResult,
  type StudentHistoryYear,
  type StudentMove,
} from '@/types/student'
import {
  candidateLabel,
  orphanedScreenState,
  reassignConfirmText,
  type OrphanCandidate,
  type OrphanedIssue,
} from '@/types/issue'

/**
 * 🔀 P5 — ตรรกะบริสุทธิ์ของ "ย้ายห้อง" และ "เรื่องค้างที่ผู้รับหมดวาระ"
 *
 * **ทำไมต้องเทสต์:** สองหน้านี้เป็น *การเขียน* ที่ผู้ใช้กดแล้วย้อนกลับยาก
 * (ย้ายห้อง ⇒ แถวเก่าถูก supersede · มอบหมาย ⇒ เรื่องย้ายมือ) และข้อความยืนยัน
 * คือสิ่งเดียวที่ผู้ใช้เห็นก่อนกด ⇒ ถ้าข้อความปด/ขาดข้อมูล ผู้ใช้จะกดผิดโดยไม่รู้ตัว
 *
 * ⚠️ `moveConfirmText` ต้องบอก **จำนวน + ห้องปลายทาง** เสมอ — เป็นด่านสุดท้ายก่อนเขียน DB
 */

function makeResult(over: Partial<BulkMoveResult> = {}): BulkMoveResult {
  return {
    moved: [{ id: 1, student_id: 'S1', from_room_id: 10, to_room_id: 20 }],
    skipped: [],
    superseded_ids: [],
    to_room: { id: 20, room_code: 'ม.1/2' },
    ...over,
  }
}

function makeYear(over: Partial<StudentHistoryYear> = {}): StudentHistoryYear {
  return {
    student_row_id: 1,
    academic_year_id: 1,
    year_be: 2569,
    room_id: 10,
    room_code: 'ม.5/1',
    level: 'ม.5',
    student_no: 12,
    class_role: 'student',
    status: 'active',
    ...over,
  }
}

function makeMove(over: Partial<StudentMove> = {}): StudentMove {
  return {
    id: 1,
    from_room_id: 10,
    from_room_code: 'ม.1/1',
    to_room_id: 11,
    to_room_code: 'ม.1/2',
    academic_year_id: 1,
    year_be: 2569,
    note: null,
    moved_by: 5,
    moved_by_name: 'ครูทดสอบ',
    moved_at: '2026-10-20T11:00:00+07:00',
    ...over,
  }
}

function makeIssue(over: Partial<OrphanedIssue> = {}): OrphanedIssue {
  return {
    id: 7,
    title: 'ไฟห้องน้ำเสีย',
    status: 'pending',
    current_level: 'room',
    room_id: 10,
    room_code: 'ม.1/1',
    assignee_id: 3,
    assignee_name: 'หัวหน้าห้องคนเก่า',
    assignee_role: 'class_president',
    assignee_old_room_code: 'ม.1/1',
    reporter_id: 4,
    created_at: '2026-09-01T09:00:00+07:00',
    candidates: [],
    ...over,
  }
}

function makeCandidate(over: Partial<OrphanCandidate> = {}): OrphanCandidate {
  return {
    user_id: 9,
    full_name: 'สมชาย ใจดี',
    class_role: 'class_president',
    room_code: 'ม.1/1',
    ...over,
  }
}

// ─────────────────────────────────────────────────────────────────────────────
describe('moveConfirmText — ด่านสุดท้ายก่อนเขียน DB', () => {
  it('บอกจำนวนและห้องปลายทางครบ', () => {
    const text = moveConfirmText(3, 'ม.1/2')
    expect(text).toContain('3 คน')
    expect(text).toContain('«ม.1/2»')
    // ต้องเตือนว่ามีผลข้างเคียง (เขียนประวัติ) ไม่ใช่แค่ "ย้าย?"
    expect(text).toContain('ประวัติ')
  })

  it('ใส่เหตุผลเมื่อมี และไม่ใส่เมื่อว่าง/ช่องว่างล้วน', () => {
    expect(moveConfirmText(1, 'ม.1/2', 'สลับตามคำสั่ง')).toContain('สลับตามคำสั่ง')
    const blank = moveConfirmText(1, 'ม.1/2', '   ')
    expect(blank).not.toContain('บันทึกเหตุผล')
    expect(moveConfirmText(1, 'ม.1/2', null)).not.toContain('บันทึกเหตุผล')
  })
})

describe('moveResultText — ต้องไม่ซ่อนความล้มเหลวบางส่วน', () => {
  it('ย้ายล้วน ไม่พูดถึงการข้าม', () => {
    const text = moveResultText(makeResult())
    expect(text).toContain('«ม.1/2»')
    expect(text).not.toContain('ข้าม')
    expect(text).not.toContain('แถวซ้ำ')
  })

  it('มีคนถูกข้าม → ต้องบอกจำนวน', () => {
    const text = moveResultText(
      makeResult({ skipped: [{ id: 2, student_id: 'S2', reason: 'already_in_room' }] }),
    )
    expect(text).toContain('ข้าม 1 คน')
  })

  it('มีแถวซ้ำถูก supersede → ต้องบอก (ไม่ปิดเงียบ)', () => {
    const text = moveResultText(makeResult({ superseded_ids: [5, 6] }))
    expect(text).toContain('2 แถวซ้ำ')
  })
})

describe('historyYearLabel / moveLabel — ห้องที่หายไปต้องอ่านรู้เรื่อง', () => {
  it('มีครบ: ปี · ห้อง · เลขที่', () => {
    expect(historyYearLabel(makeYear())).toBe('ปี 2569 · ม.5/1 · เลขที่ 12')
  })

  it('ไม่มีปี/ห้อง/เลขที่ ต้องไม่มี "null" หลุดออกจอ', () => {
    const label = historyYearLabel(makeYear({ year_be: null, room_code: null, student_no: null }))
    expect(label).not.toMatch(/null|undefined/)
    expect(label).toContain('ไม่ทราบปี')
    expect(label).toContain('ไม่มีห้อง')
  })

  it('moveLabel ใช้ "ไม่มีห้อง" แทน null ทั้งสองฝั่ง', () => {
    expect(moveLabel(makeMove())).toBe('ม.1/1 → ม.1/2')
    expect(moveLabel(makeMove({ from_room_code: null }))).toBe('ไม่มีห้อง → ม.1/2')
    expect(moveLabel(makeMove({ from_room_code: null, to_room_code: null }))).toBe(
      'ไม่มีห้อง → ไม่มีห้อง',
    )
  })
})

describe('historyScreenState — error มาก่อน loading', () => {
  it('ลำดับความสำคัญ: error → loading → empty → ready', () => {
    expect(historyScreenState({ isLoading: true, hasError: true, hasData: false })).toBe('error')
    expect(historyScreenState({ isLoading: true, hasError: false, hasData: false })).toBe('loading')
    expect(historyScreenState({ isLoading: false, hasError: false, hasData: false })).toBe('empty')
    expect(historyScreenState({ isLoading: false, hasError: false, hasData: true })).toBe('ready')
  })
})

describe('สถานะสมาชิก — ป้ายครบทุกค่าที่ backend รับ', () => {
  it('ไม่มีป้ายไหนตกหล่น (Record บังคับครบทุก key ตั้งแต่ compile-time)', () => {
    expect(Object.keys(STUDENT_STATUS_LABELS).sort()).toEqual(
      [
        'active',
        'pending',
        'suspended',
        'promoted',
        'graduated',
        'transferred_out',
        'left',
        'superseded',
      ].sort(),
    )
    expect(Object.values(STUDENT_STATUS_LABELS).every((v) => v.trim().length > 0)).toBe(true)
  })
})

// ─────────────────────────────────────────────────────────────────────────────
describe('candidateLabel / reassignConfirmText', () => {
  it('มีห้อง → "ชื่อ · ห้อง"', () => {
    expect(candidateLabel(makeCandidate())).toBe('สมชาย ใจดี · ม.1/1')
  })

  it('ไม่มีห้อง (คนระดับโรงเรียน) → เอาแค่ชื่อ ไม่มี "· null"', () => {
    const label = candidateLabel(makeCandidate({ room_code: null }))
    expect(label).toBe('สมชาย ใจดี')
    expect(label).not.toContain('·')
  })

  it('ชื่อว่าง → ใช้ "ผู้ใช้ #id" ไม่ใช่ช่องว่างเปล่า (ห้องยังต่อท้ายตามปกติ)', () => {
    expect(candidateLabel(makeCandidate({ full_name: '  ', room_code: null }))).toBe('ผู้ใช้ #9')
    expect(candidateLabel(makeCandidate({ full_name: null, room_code: null }))).toBe('ผู้ใช้ #9')
    expect(candidateLabel(makeCandidate({ full_name: '  ' }))).toBe('ผู้ใช้ #9 · ม.1/1')
  })

  it('ข้อความยืนยันบอกทั้งชื่อเรื่องและผู้รับใหม่', () => {
    const text = reassignConfirmText(makeIssue(), makeCandidate())
    expect(text).toContain('ไฟห้องน้ำเสีย')
    expect(text).toContain('สมชาย ใจดี')
  })
})

describe('orphanedScreenState — error มาก่อน loading (เหมือนกันทั้งแอป)', () => {
  it('ลำดับ: error → loading → empty → ready', () => {
    expect(orphanedScreenState({ isLoading: true, hasError: true, count: 0 })).toBe('error')
    expect(orphanedScreenState({ isLoading: true, hasError: false, count: 0 })).toBe('loading')
    expect(orphanedScreenState({ isLoading: false, hasError: false, count: 0 })).toBe('empty')
    expect(orphanedScreenState({ isLoading: false, hasError: false, count: 3 })).toBe('ready')
  })
})
