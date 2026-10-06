import { describe, it, expect } from 'vitest'
import {
  EMPTY_YEAR_FORM,
  YEAR_BE_MAX,
  YEAR_BE_MIN,
  deleteBlockReason,
  setCurrentConfirmText,
  toYearFormValues,
  yearCoversToday,
  yearFormError,
  yearFormToPayload,
  yearScreenState,
  type AcademicYear,
  type YearFormValues,
} from '@/types/academicYear'

/**
 * 🎓 ปีการศึกษา — ตรรกะบริสุทธิ์ 4 กลุ่มที่ตัดสินพฤติกรรมของทั้งหน้าจอ
 *
 * **ทำไมต้องเทสต์ที่นี่ ไม่ใช่ใน `.vue`:** ทั้งสี่ตัวนี้เป็น *การตัดสินใจ* ไม่ใช่ *การวาด*
 *   · `yearScreenState` — "ว่าง ≠ พัง ≠ โหลดไม่เสร็จ" (frontend.md §4)
 *   · `yearCoversToday` — เทียบวันที่แบบสตริง (ห้าม `new Date()`)
 *   · `deleteBlockReason` — เหตุผลที่ห้ามลบ ต้องตรงกับ backend ไม่งั้นปุ่มกดได้แล้วเด้ง error
 *   · `yearFormError` / `yearFormToPayload` — ต้องตรงกับ Field(ge/le) ของ Pydantic
 * ถ้าย้ายเข้าเทมเพลต วันหนึ่งจะไม่มีใครเทสต์ได้เลย และบั๊กจะไปโผล่ตอนผู้ใช้กดจริง
 */

function makeYear(over: Partial<AcademicYear> = {}): AcademicYear {
  return {
    id: 7,
    year_be: 2569,
    name: 'ปีการศึกษา 2569',
    start_date: '2026-05-16',
    end_date: '2027-03-31',
    is_current: false,
    member_count: 0,
    created_at: '2026-05-01T00:00:00Z',
    updated_at: '2026-05-01T00:00:00Z',
    deleted_at: null,
    ...over,
  }
}

// ============================================================
// 1. สถานะหน้าจอ — "ว่าง ≠ พัง ≠ โหลดไม่เสร็จ"
// ============================================================

describe('yearScreenState', () => {
  it('กำลังโหลดครั้งแรก (ยังไม่มีข้อมูล) → loading', () => {
    expect(yearScreenState({ isLoading: true, hasError: false, itemCount: 0 })).toBe('loading')
  })

  it('🔴 error ชนะ loading — โหลดรอบสองที่ล้มต้องโชว์ error ไม่ใช่ค้างที่ skeleton ตลอดกาล', () => {
    expect(yearScreenState({ isLoading: true, hasError: true, itemCount: 0 })).toBe('error')
    expect(yearScreenState({ isLoading: false, hasError: true, itemCount: 5 })).toBe('error')
  })

  it('โหลดเสร็จแล้วไม่มีข้อมูล → empty (ไม่ใช่ error)', () => {
    expect(yearScreenState({ isLoading: false, hasError: false, itemCount: 0 })).toBe('empty')
  })

  it('มีข้อมูล → list (แม้กำลังรีเฟรชอยู่ — ของเดิมยังแสดงได้)', () => {
    expect(yearScreenState({ isLoading: false, hasError: false, itemCount: 1 })).toBe('list')
    expect(yearScreenState({ isLoading: true, hasError: false, itemCount: 3 })).toBe('list')
  })
})

// ============================================================
// 2. "วันนี้อยู่ในช่วงนี้" — เทียบสตริง ไม่ผ่าน Date
// ============================================================

describe('yearCoversToday', () => {
  it('อยู่กลางช่วง → true', () => {
    expect(yearCoversToday(makeYear(), '2026-08-01')).toBe(true)
  })

  it('🔴 หัว–ท้ายช่วง **นับรวม** ทั้งสองข้าง (inclusive)', () => {
    expect(yearCoversToday(makeYear(), '2026-05-16')).toBe(true)
    expect(yearCoversToday(makeYear(), '2027-03-31')).toBe(true)
  })

  it('ก่อน/หลังช่วง → false', () => {
    expect(yearCoversToday(makeYear(), '2026-05-15')).toBe(false)
    expect(yearCoversToday(makeYear(), '2027-04-01')).toBe(false)
  })

  it('🔴 ปีที่ยังไม่ระบุวัน → false เสมอ (ไม่เดา)', () => {
    expect(yearCoversToday(makeYear({ start_date: null }), '2026-08-01')).toBe(false)
    expect(yearCoversToday(makeYear({ end_date: null }), '2026-08-01')).toBe(false)
    expect(yearCoversToday(makeYear({ start_date: null, end_date: null }), '2026-08-01')).toBe(
      false,
    )
  })

  it('🔴 เทียบสตริงตรง ๆ ⇒ ไม่มีปัญหา timezone เลื่อนวัน (เคสที่ new Date() จะพัง)', () => {
    // ปีที่เริ่มและจบวันเดียวกัน — ถ้าใช้ new Date() จะเพี้ยนเพราะ date-only ถูกตีเป็น UTC
    // แล้วเลื่อนเป็นเวลาไทย +7 ชม. ⇒ '2026-05-16' กลายเป็น 16 พ.ค. 07:00 ซึ่งยังตรงโดยบังเอิญ
    // แต่ '2027-03-31' จะกลายเป็น 31 มี.ค. 07:00 ⇒ เทียบกับ '2027-04-01' ยัง false อยู่ดี
    // ⇒ เคสที่พิสูจน์จริงคือ "วันสุดท้ายของช่วงต้องยังนับ" ซึ่งสตริงให้ผลถูกเสมอ
    const oneDay = makeYear({ start_date: '2026-05-16', end_date: '2026-05-16' })
    expect(yearCoversToday(oneDay, '2026-05-16')).toBe(true)
    expect(yearCoversToday(oneDay, '2026-05-17')).toBe(false)
  })
})

// ============================================================
// 3. ลบได้ไหม — เหตุผลต้องตรงกับ delete_year ใน backend
// ============================================================

describe('deleteBlockReason', () => {
  it('ปีธรรมดาที่ไม่มีสมาชิก → ลบได้', () => {
    expect(deleteBlockReason(makeYear())).toBe('')
  })

  it('🔴 ปีปัจจุบันลบไม่ได้ — ต้องบอกว่าทำอะไรก่อน', () => {
    const reason = deleteBlockReason(makeYear({ is_current: true }))
    expect(reason).not.toBe('')
    expect(reason).toContain('ปีปัจจุบัน')
  })

  it('🔴 ปีที่มีสมาชิกอยู่ลบไม่ได้ — และข้อความต้องบอกจำนวนจริง', () => {
    const reason = deleteBlockReason(makeYear({ member_count: 412 }))
    expect(reason).not.toBe('')
    expect(reason).toContain('412')
  })

  it('🔴 ปีปัจจุบัน **ชนะ** เงื่อนไขสมาชิก — บอกเรื่องที่ต้องทำก่อน (ตั้งปีอื่นเป็นปัจจุบัน)', () => {
    // ทั้งสองเงื่อนไขจริงพร้อมกัน ⇒ ต้องได้เหตุผลของ "ปีปัจจุบัน" เพราะนั่นคือด่านแรกที่ backend ตรวจ
    const reason = deleteBlockReason(makeYear({ is_current: true, member_count: 412 }))
    expect(reason).toContain('ปีปัจจุบัน')
    expect(reason).not.toContain('412')
  })

  it('ปีที่ถูกลบแล้ว + ไม่มีสมาชิก → ไม่มีเหตุผลห้าม (แต่ปุ่มลบไม่โชว์อยู่แล้ว)', () => {
    expect(deleteBlockReason(makeYear({ deleted_at: '2026-06-01T00:00:00Z' }))).toBe('')
  })
})

// ============================================================
// 4. ข้อความยืนยันการตั้งปีปัจจุบัน
// ============================================================

describe('setCurrentConfirmText', () => {
  it('🔴 ปีที่มีสมาชิก — ต้องบอกจำนวน และต้องบอกว่ากระทบ DEFAULT ของสมาชิกใหม่', () => {
    const text = setCurrentConfirmText(makeYear({ member_count: 88 }))
    expect(text).toContain('88')
    // หัวใจของข้อความ: การเปลี่ยนปีปัจจุบันไม่ใช่แค่เปลี่ยนป้ายชื่อ
    expect(text).toContain('สร้างใหม่')
  })

  it('ปีว่าง — เตือนล่วงหน้าว่าระบบจะปฏิเสธถ้าปีอื่นยังมีคน', () => {
    const text = setCurrentConfirmText(makeYear({ member_count: 0 }))
    expect(text).toContain('ไม่ยอมให้')
  })
})

// ============================================================
// 5. ฟอร์ม — ตรวจค่า + แปลงเป็น payload
// ============================================================

function form(over: Partial<YearFormValues> = {}): YearFormValues {
  return { year_be: '2569', name: '', start_date: '', end_date: '', ...over }
}

describe('yearFormError', () => {
  it('ฟอร์มต่ำสุดที่ใช้ได้ (มีแค่ พ.ศ.) → ผ่าน — วันที่และชื่อไม่บังคับ', () => {
    expect(yearFormError(form())).toBe('')
  })

  it('ไม่กรอก พ.ศ. → ไม่ผ่าน', () => {
    expect(yearFormError(form({ year_be: '' }))).not.toBe('')
    expect(yearFormError(form({ year_be: '   ' }))).not.toBe('')
  })

  it('🔴 พ.ศ. ต้องเป็นตัวเลขล้วน — "2569.5" / "สองหกเก้า" / "2,569" ไม่ผ่าน', () => {
    expect(yearFormError(form({ year_be: '2569.5' }))).not.toBe('')
    expect(yearFormError(form({ year_be: 'สองหกเก้า' }))).not.toBe('')
    expect(yearFormError(form({ year_be: '2,569' }))).not.toBe('')
    expect(yearFormError(form({ year_be: '-2569' }))).not.toBe('')
  })

  it(`🔴 ช่วง พ.ศ. ปิดหัว–ท้าย (${YEAR_BE_MIN}–${YEAR_BE_MAX}) — ตรงกับ ge/le ของ Pydantic`, () => {
    expect(yearFormError(form({ year_be: String(YEAR_BE_MIN) }))).toBe('')
    expect(yearFormError(form({ year_be: String(YEAR_BE_MAX) }))).toBe('')
    expect(yearFormError(form({ year_be: String(YEAR_BE_MIN - 1) }))).not.toBe('')
    expect(yearFormError(form({ year_be: String(YEAR_BE_MAX + 1) }))).not.toBe('')
  })

  it('🔴 ดัก ค.ศ. ที่คนมักพิมพ์ — 2026 ต้องไม่ผ่าน (พร้อมบอกให้ใช้ พ.ศ.)', () => {
    const msg = yearFormError(form({ year_be: '2026' }))
    expect(msg).not.toBe('')
    expect(msg).toContain('2400')
  })

  it('ชื่อยาวเกิน 50 → ไม่ผ่าน · 50 พอดี → ผ่าน', () => {
    expect(yearFormError(form({ name: 'ก'.repeat(50) }))).toBe('')
    expect(yearFormError(form({ name: 'ก'.repeat(51) }))).not.toBe('')
  })

  it('วันสิ้นสุดก่อนวันเริ่มต้น → ไม่ผ่าน · เท่ากัน (ปีวันเดียว) → ผ่าน', () => {
    const bad = form({ start_date: '2026-05-16', end_date: '2026-05-15' })
    expect(yearFormError(bad)).not.toBe('')
    const same = form({ start_date: '2026-05-16', end_date: '2026-05-16' })
    expect(yearFormError(same)).toBe('')
  })

  it('🔴 ระบุวันเดียวก็ผ่าน (ต่างจากภาคเรียนที่บังคับทั้งคู่)', () => {
    expect(yearFormError(form({ start_date: '2026-05-16' }))).toBe('')
    expect(yearFormError(form({ end_date: '2027-03-31' }))).toBe('')
  })

  it('ตัดช่องว่างหัว–ท้ายก่อนตรวจ', () => {
    expect(yearFormError(form({ year_be: '  2569  ' }))).toBe('')
  })
})

describe('yearFormToPayload', () => {
  it('แปลง พ.ศ. เป็น number และวันที่ว่างเป็น null', () => {
    expect(yearFormToPayload(form())).toEqual({
      year_be: 2569,
      start_date: null,
      end_date: null,
    })
  })

  it('🔴 ชื่อว่าง = **ไม่ส่งคีย์ `name` เลย** — ให้ backend ตั้ง default เอง (ไม่ใช่ส่ง "" ไปทับ)', () => {
    const payload = yearFormToPayload(form({ name: '   ' }))
    expect('name' in payload).toBe(false)
    expect(payload.year_be).toBe(2569)
  })

  it('ชื่อที่ไม่ว่างถูกตัดช่องว่างและส่งไป', () => {
    expect(yearFormToPayload(form({ name: '  ปี 2569  ' })).name).toBe('ปี 2569')
  })

  it('วันที่ที่กรอกถูกส่งเป็นสตริง YYYY-MM-DD ตามเดิม', () => {
    const payload = yearFormToPayload(
      form({ start_date: '2026-05-16', end_date: '2027-03-31' }),
    )
    expect(payload.start_date).toBe('2026-05-16')
    expect(payload.end_date).toBe('2027-03-31')
  })
})

describe('toYearFormValues', () => {
  it('แถวจาก API → ค่าฟอร์ม (ตัวเลขเป็นสตริง, null เป็นสตริงว่าง)', () => {
    expect(toYearFormValues(makeYear())).toEqual({
      year_be: '2569',
      name: 'ปีการศึกษา 2569',
      start_date: '2026-05-16',
      end_date: '2027-03-31',
    })
  })

  it('🔴 วันที่ null → "" (ไม่ใช่ "null" ซึ่งจะทำให้ <input type="date"> ขึ้นค่าว่างผิด)', () => {
    const v = toYearFormValues(makeYear({ start_date: null, end_date: null }))
    expect(v.start_date).toBe('')
    expect(v.end_date).toBe('')
  })

  it('🔁 round-trip: toYearFormValues → yearFormToPayload ได้ค่าเดิมกลับมา', () => {
    const y = makeYear({ name: 'ปี 2569' })
    const payload = yearFormToPayload(toYearFormValues(y))
    expect(payload).toEqual({
      year_be: 2569,
      name: 'ปี 2569',
      start_date: '2026-05-16',
      end_date: '2027-03-31',
    })
  })

  it('EMPTY_YEAR_FORM ผ่านการตรวจไม่ได้ (กันการส่งฟอร์มว่าง)', () => {
    expect(yearFormError(EMPTY_YEAR_FORM)).not.toBe('')
  })
})
