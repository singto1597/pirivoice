import { describe, it, expect } from 'vitest'
import {
  isCurrentMember,
  moveConfirmText,
  moveResultText,
  unassignConfirmText,
  unassignResultText,
  wholeRoomConfirmText,
} from '@/types/student'

/**
 * 🔀 ย้ายห้อง / ถอดออกจากห้อง — ข้อความยืนยันและสรุปผล
 *
 * **ทำไมต้องเทสต์:** ทั้งสามฟังก์ชันเป็น *ด่านสุดท้าย* ก่อนเขียนข้อมูลจริง —
 * "ย้ายทั้งห้อง" แตะทุกคนในห้องในคลิกเดียว และ "ถอดออกจากห้อง" ทำให้เด็กหลุดจากห้อง
 * ⇒ ข้อความต้องบอก **จำนวน + ต้นทาง/ปลายทาง + ผลข้างเคียง** ครบ ไม่ใช่คำว่า "แน่ใจไหม"
 */

describe('moveConfirmText', () => {
  it('บอกจำนวนและห้องปลายทางเสมอ', () => {
    const text = moveConfirmText(3, 'ม.1/2')
    expect(text).toContain('3 คน')
    expect(text).toContain('ม.1/2')
    expect(text).toContain('ประวัติ')
  })

  it('ใส่เหตุผลเมื่อมี และไม่ใส่ขีดคั่นลอยเมื่อไม่มี', () => {
    expect(moveConfirmText(1, 'ม.1/2', 'สลับห้อง')).toContain('สลับห้อง')
    expect(moveConfirmText(1, 'ม.1/2', '   ')).not.toContain('บันทึกเหตุผล:')
  })
})

describe('wholeRoomConfirmText', () => {
  it('บอกจำนวน + ห้องต้นทาง + ห้องปลายทาง (กดผิดแล้วกระทบทั้งห้อง)', () => {
    const text = wholeRoomConfirmText(32, 'ม.4/1', 'ม.5/1')
    expect(text).toContain('32 คน')
    expect(text).toContain('ม.4/1')
    expect(text).toContain('ม.5/1')
  })
})

describe('unassignConfirmText', () => {
  it('บอกผลที่ตามมา — เด็กจะอยู่สถานะไม่มีห้อง และต้องอัปไฟล์ใหม่', () => {
    const text = unassignConfirmText(5)
    expect(text).toContain('5 คน')
    expect(text).toContain('ไม่มีห้อง')
    expect(text).toContain('นำเข้าไฟล์')
  })
})

describe('unassignResultText', () => {
  it('ไม่มี "ข้าม" เมื่อถอดได้ครบ', () => {
    const text = unassignResultText({
      unassigned: [{ id: 1, student_id: '1', from_room_id: 1, from_room_code: 'ม.1/1' }],
      skipped: [],
    })
    expect(text).toContain('1 คน')
    expect(text).not.toContain('ข้าม')
  })

  it('แสดงจำนวนที่ถูกข้าม (คนที่ไม่มีห้องอยู่แล้ว) — ไม่ซ่อนผลลัพธ์บางส่วน', () => {
    const text = unassignResultText({
      unassigned: [],
      skipped: [{ id: 1, student_id: '1', reason: 'ไม่มีห้องอยู่แล้ว' }],
    })
    expect(text).toContain('0 คน')
    expect(text).toContain('ข้าม 1 คน')
  })
})

describe('moveResultText', () => {
  it('รายงาน superseded เมื่อมีแถวซ้ำถูกแทนที่', () => {
    const text = moveResultText({
      moved: [{ id: 1, student_id: '1', from_room_id: 1, to_room_id: 2 }],
      skipped: [],
      superseded_ids: [9],
      to_room: { id: 2, room_code: 'ม.1/2' },
    })
    expect(text).toContain('ย้ายสำเร็จ 1 คน')
    expect(text).toContain('ม.1/2')
    expect(text).toContain('1 แถวซ้ำ')
  })
})

describe('isCurrentMember', () => {
  it('แถวซ้ำที่ถูกแทนที่แล้วไม่อยู่ในรายการที่ย้ายได้', () => {
    expect(isCurrentMember({ status: 'superseded' })).toBe(false)
  })

  it('สถานะอื่นของปีนั้นยังย้าย/ถอดได้ (ลิสต์ไม่ใช่ตัวกรองสิทธิ์)', () => {
    for (const status of ['active', 'pending', 'suspended', 'left']) {
      expect(isCurrentMember({ status })).toBe(true)
    }
  })
})
