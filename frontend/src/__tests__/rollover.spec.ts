import { describe, it, expect } from 'vitest'
import {
  applyBlockReason,
  applyConfirmText,
  applyResultText,
  cleanOverrides,
  levelGroupTitle,
  missingOverrideRooms,
  overridesDirty,
  personName,
  rolloverScreenState,
  roomOptions,
  sortRoomCodes,
  type RolloverApplyResult,
  type RolloverLevelGroup,
  type RolloverPlan,
  type RolloverPreview,
  type RolloverUnmappedRoom,
} from '@/types/rollover'
import type { Room } from '@/types/student'

/**
 * 🔄 เลื่อนชั้นทั้งโรงเรียน — ตรรกะบริสุทธิ์ที่ตัดสินพฤติกรรมของหน้า PromoteStudents
 *
 * **ทำไมต้องเทสต์ที่นี่ ไม่ใช่ใน `.vue`:** หน้านี้เป็นหน้าเดียวในระบบที่ *กดผิดแล้วกู้ไม่ได้*
 * (เขียนสมาชิกทั้งโรงเรียน + สลับปีปัจจุบันในทรานแซกชันเดียว ⇒ ผิดแล้วต้อง restore dump)
 * ⇒ ตัวตัดสินว่า "กดได้ไหม" และ "ข้อความเตือนว่าอะไร" ต้องเป็นฟังก์ชันที่เทสต์ได้
 *
 * ⚠️ **`applyBlockReason` ต้องตรงกับ `plan.can_apply`/`plan.blockers` ของ backend เสมอ**
 *    (ชุดเดียวกับที่ `apply_rollover` จะ `raise`) — ถ้า UI ว่า "กดได้" แต่ backend ปฏิเสธ
 *    ผู้ใช้จะเลิกเชื่อคำเตือนของระบบ ซึ่งอันตรายกว่าการไม่มีคำเตือนเลย
 */

function makePlan(over: Partial<RolloverPlan> = {}): RolloverPlan {
  return {
    from_year: { id: 1, year_be: 2568, name: 'ปีการศึกษา 2568' },
    to_year: { id: 2, year_be: 2569, name: 'ปีการศึกษา 2569' },
    total_active: 14,
    promoted: { count: 10, by_role: { student: 8, council_member: 2 } },
    graduating: { count: 2, rooms: [{ room_code: 'ม.6/1', student_count: 2 }] },
    staff_carried: { count: 3, by_role: { admin: 1 } },
    positions_reset: { count: 1, by_role: { class_president: 1 } },
    council_lapsing: { count: 2, by_role: { council_member: 2 } },
    roomless: { count: 1, by_role: { council_president: 1 } },
    by_level: [
      {
        level: 'ม.1',
        target_level: 'ม.2',
        student_count: 3,
        mapped_rooms: 1,
        unmapped_rooms: 0,
        rooms: [
          { from_room_code: 'ม.1/1', to_room_code: 'ม.2/1', student_count: 3, status: 'ok' },
        ],
      },
    ],
    unmapped: [],
    blockers: [],
    warnings: [],
    can_apply: true,
    ...over,
  }
}

function makeUnmapped(over: Partial<RolloverUnmappedRoom> = {}): RolloverUnmappedRoom {
  return {
    from_room_code: 'ม.3/14',
    from_room_id: 55,
    level: 'ม.3',
    student_count: 40,
    reason: 'ไม่มีห้อง «ม.4/14» ในระบบ',
    ...over,
  }
}

/** กลุ่มระดับแรกของแผนตัวอย่าง — `noUncheckedIndexedAccess` ทำให้ `by_level[0]` เป็น `| undefined` */
function firstLevel(plan: RolloverPlan): RolloverLevelGroup {
  const g = plan.by_level[0]
  if (!g) throw new Error('แผนตัวอย่างต้องมีอย่างน้อยหนึ่งกลุ่มระดับ')
  return g
}

// ============================================================
// 1. สถานะหน้าจอ — "ยังไม่ได้ดูแผน" ต้องไม่ถูกอ่านเป็น "ไม่มีอะไร"
// ============================================================

describe('rolloverScreenState', () => {
  it('กำลังโหลดครั้งแรก (ยังไม่มีแผน) → loading', () => {
    expect(rolloverScreenState({ isLoading: true, hasError: false, hasPlan: false })).toBe(
      'loading',
    )
  })

  it('🔴 error ชนะ loading — โหลดรอบสองที่ล้มต้องโชว์ error ไม่ใช่ค้างที่ skeleton', () => {
    expect(rolloverScreenState({ isLoading: true, hasError: true, hasPlan: false })).toBe('error')
    expect(rolloverScreenState({ isLoading: false, hasError: true, hasPlan: true })).toBe('error')
  })

  it('🔴 โหลดเสร็จแต่ยังไม่ได้กดดูแผน → `idle` **ไม่ใช่ `empty`**', () => {
    // `empty` แปลว่า "ไม่มีข้อมูล" ซึ่งอ่านแล้วเหมือนระบบพัง — ที่นี่ความว่างคือสถานะปกติ
    // ของหน้า (ยังไม่ได้กดปุ่ม) ⇒ ต้องได้ปุ่ม «ดูแผน» ไม่ใช่ข้อความว่าง
    expect(rolloverScreenState({ isLoading: false, hasError: false, hasPlan: false })).toBe('idle')
  })

  it('มีแผน → plan (แม้กำลังโหลดแผนใหม่ — ของเดิมยังอ่านได้)', () => {
    expect(rolloverScreenState({ isLoading: false, hasError: false, hasPlan: true })).toBe('plan')
    expect(rolloverScreenState({ isLoading: true, hasError: false, hasPlan: true })).toBe('plan')
  })
})

// ============================================================
// 2. cleanOverrides — ต้องเหมือน _clean_overrides ใน rollover_schemas.py เป๊ะ
// ============================================================

describe('cleanOverrides', () => {
  it('ตัดช่องว่างหัว–ท้ายของทั้งคีย์และค่า', () => {
    expect(cleanOverrides({ '  ม.3/14  ': '  ม.4/13 ' })).toEqual({ 'ม.3/14': 'ม.4/13' })
  })

  it('🔴 ค่าว่าง/ช่องว่างล้วน = "ยังไม่เลือก" → ทิ้งทั้งคู่ (ไม่ใช่ส่งห้องชื่อ "" ไป)', () => {
    expect(cleanOverrides({ 'ม.3/14': '', 'ม.4/9': '   ' })).toEqual({})
  })

  it('คีย์ว่างทิ้งด้วย (เกิดได้ตอนผูก v-model กับค่าที่ยังไม่มี)', () => {
    expect(cleanOverrides({ '': 'ม.4/13', '   ': 'ม.4/13' })).toEqual({})
  })

  it('null / undefined → {} (ผู้เรียกไม่ต้องเช็คก่อน)', () => {
    expect(cleanOverrides(null)).toEqual({})
    expect(cleanOverrides(undefined)).toEqual({})
  })

  it('🛡️ object เปล่าที่ได้คืนมาไม่ใช่ตัวเดิม (แก้แล้วไม่กระเทือนต้นทาง)', () => {
    const src = { 'ม.3/14': 'ม.4/13' }
    const out = cleanOverrides(src)
    out['ม.3/14'] = 'แก้'
    expect(src['ม.3/14']).toBe('ม.4/13')
  })
})

// ============================================================
// 3. overridesDirty — "แผนที่เห็น ยังตรงกับค่าที่จะส่งไหม"
// ============================================================

describe('overridesDirty', () => {
  it('ค่าเดิมเป๊ะ → false', () => {
    expect(overridesDirty({ 'ม.3/14': 'ม.4/13' }, { 'ม.3/14': 'ม.4/13' })).toBe(false)
  })

  it('🔴 ลำดับคีย์ไม่มีความหมาย (object เดียวกันคนละลำดับ → ไม่ถือว่าแก้)', () => {
    expect(overridesDirty({ a: '1', b: '2' }, { b: '2', a: '1' })).toBe(false)
  })

  it('🔴 เปลี่ยนห้องปลายทาง → true (ต้องเตือนให้ดูแผนใหม่)', () => {
    expect(overridesDirty({ 'ม.3/14': 'ม.4/13' }, { 'ม.3/14': 'ม.4/12' })).toBe(true)
  })

  it('🔴 เพิ่มห้องที่เลือกใหม่ → true — คนละสถานะกับตอนที่ backend ตรวจ `can_apply`', () => {
    expect(overridesDirty({ 'ม.3/14': 'ม.4/13' }, { 'ม.3/14': 'ม.4/13', 'ม.4/9': 'ม.5/9' })).toBe(
      true,
    )
  })

  it('🔴 ลบห้องที่เลือกออก → true (กลับไปเป็น "ยังไม่ได้เลือก")', () => {
    expect(overridesDirty({ 'ม.3/14': 'ม.4/13' }, {})).toBe(true)
  })

  it('ช่องว่างทั้งสองฝั่ง = เท่ากัน (ว่างที่ค้างใน v-model ไม่นับเป็นการแก้)', () => {
    expect(overridesDirty({ 'ม.3/14': '' }, {})).toBe(false)
    expect(overridesDirty(null, undefined)).toBe(false)
  })

  it('ตัดช่องว่างก่อนเทียบ (ค่าที่พิมพ์เพิ่มช่องว่างไม่นับเป็นการแก้)', () => {
    expect(overridesDirty({ 'ม.3/14': 'ม.4/13' }, { ' ม.3/14 ': ' ม.4/13 ' })).toBe(false)
  })
})

// ============================================================
// 4. missingOverrideRooms — ป้าย "ยังไม่ได้เลือก" รายแถว
// ============================================================

describe('missingOverrideRooms', () => {
  it('ยังไม่มีแผน → [] (ไม่ throw ตอนหน้าจอวาดครั้งแรก)', () => {
    expect(missingOverrideRooms(null, {})).toEqual([])
  })

  it('ห้องที่เลือกแล้วหายจากรายการ · ที่ยังไม่เลือกอยู่ต่อ', () => {
    const plan = makePlan({
      unmapped: [makeUnmapped(), makeUnmapped({ from_room_code: 'ม.4/9', level: 'ม.4' })],
    })
    const missing = missingOverrideRooms(plan, { 'ม.3/14': 'ม.4/13' })
    expect(missing.map((m) => m.from_room_code)).toEqual(['ม.4/9'])
  })

  it('🔴 ค่าเป็นช่องว่างล้วน **ไม่นับว่าเลือกแล้ว** (ผู้ใช้ลบข้อความออก)', () => {
    const plan = makePlan({ unmapped: [makeUnmapped()] })
    expect(missingOverrideRooms(plan, { 'ม.3/14': '   ' })).toHaveLength(1)
  })

  it('เลือกครบทุกห้อง → []', () => {
    const plan = makePlan({ unmapped: [makeUnmapped()] })
    expect(missingOverrideRooms(plan, { 'ม.3/14': 'ม.4/13' })).toEqual([])
  })
})

// ============================================================
// 5. applyBlockReason — ต้องอ่าน can_apply/blockers ของ backend เท่านั้น
// ============================================================

describe('applyBlockReason', () => {
  it('ยังไม่มีแผน → บอกให้กด «ดูแผน» ก่อน', () => {
    expect(applyBlockReason(null)).toContain('ดูแผน')
  })

  it('แผนที่ผ่านแล้ว → "" (= กดได้)', () => {
    expect(applyBlockReason(makePlan())).toBe('')
  })

  it('🔴 มี blocker → ห้ามกด แม้ `can_apply` จะเป็น true (ไม่เชื่อ field เดียว)', () => {
    // backend ตั้ง can_apply = (blockers.length === 0) เสมอ — เทสต์นี้ล็อกว่า UI
    // ต้องไม่กดผ่านเมื่อ blockers ยังไม่ว่าง แม้ข้อมูลจะขัดกันเอง
    const plan = makePlan({ blockers: ['ปีต้นทางกับปีปลายทางเป็นปีเดียวกัน'], can_apply: true })
    expect(applyBlockReason(plan)).not.toBe('')
  })

  it('🔴 `can_apply=false` โดยไม่มีข้อความ blocker → ยังห้ามกด (ไม่ปล่อยผ่านเพราะอ่านไม่ออก)', () => {
    const plan = makePlan({ can_apply: false })
    expect(applyBlockReason(plan)).not.toBe('')
  })

  it('ข้อความห้ามกดไม่บอกจำนวน blocker เอง — รายการจริงโชว์ในกล่อง «ต้องแก้ก่อน»', () => {
    const plan = makePlan({ blockers: ['ก', 'ข'], can_apply: false })
    expect(applyBlockReason(plan)).toContain('ต้องแก้ก่อน')
  })
})

// ============================================================
// 6. applyConfirmText — ปุ่มอันตรายต้องบอกให้ครบว่ากำลังเกิดอะไร
// ============================================================

describe('applyConfirmText', () => {
  it('🔴 ต้องบอกจำนวนคน + ปีต้นทาง + ปีปลายทาง + "ย้อนกลับไม่ได้"', () => {
    const text = applyConfirmText(makePlan())
    expect(text).toContain('10') // promoted.count
    expect(text).toContain('ปีการศึกษา 2568') // from
    expect(text).toContain('ปีการศึกษา 2569') // to
    expect(text).toContain('ปีปัจจุบัน') // ผลที่ตามมาที่คนมักลืม
    expect(text).toContain('ย้อนกลับ')
  })

  it('🔴 ต้องบอกว่าปีเก่าถูก *ปิดเป็นประวัติ* ไม่ใช่ลบ (คำถามแรกของทุกคนที่กลัวข้อมูลหาย)', () => {
    expect(applyConfirmText(makePlan())).toContain('ประวัติ')
  })

  it('📌 ไม่พูดถึง "จบการศึกษา" เมื่อไม่มีใครจบ (ข้อความที่ยาวเกินมีแต่ทำให้อ่านข้าม)', () => {
    const plan = makePlan({ graduating: { count: 0, rooms: [] } })
    expect(applyConfirmText(plan)).not.toContain('จบการศึกษา')
  })

  it('พูดถึงบุคลากรเมื่อมี (ข้อเท็จจริงที่ผู้ใช้ต้องรู้ก่อนกด)', () => {
    expect(applyConfirmText(makePlan())).toContain('บุคลากร')
    const none = makePlan({ staff_carried: { count: 0, by_role: {} } })
    expect(applyConfirmText(none)).not.toContain('บุคลากร')
  })
})

// ============================================================
// 7. levelGroupTitle — หัวข้อกลุ่มในตารางต่อระดับ
// ============================================================

describe('levelGroupTitle', () => {
  it('ระดับที่เลื่อนได้ → "ม.1 → ม.2"', () => {
    expect(levelGroupTitle(firstLevel(makePlan()))).toBe('ม.1 → ม.2')
  })

  it('🔴 ระดับที่ระบบไม่รู้จัก → บอกว่า "เลื่อนอัตโนมัติไม่ได้" **ไม่ใช่ "จบการศึกษา"**', () => {
    // ⚠️ คนที่จบถูกตัดออกจาก `by_level` ตั้งแต่ที่ backend ⇒ `target_level=null` ที่นี่
    //    หมายถึง "ระดับแปลก" เสมอ (เช่นห้องพิมพ์ผิด) — เขียนว่า "จบ" จะเป็นการโกหกผู้ใช้
    const g: RolloverLevelGroup = { ...firstLevel(makePlan()), level: 'ม.7', target_level: null }
    const title = levelGroupTitle(g)
    expect(title).toContain('ม.7')
    expect(title).not.toContain('จบ')
    expect(title).toContain('อัตโนมัติ')
  })

  it('level เป็น null → ยังมีหัวข้อที่อ่านออก (ไม่โชว์ "null")', () => {
    const g: RolloverLevelGroup = { ...firstLevel(makePlan()), level: null, target_level: null }
    expect(levelGroupTitle(g)).not.toContain('null')
  })
})

// ============================================================
// 8. sortRoomCodes / roomOptions — เลขห้องต้องเรียงแบบคนอ่าน
// ============================================================

describe('sortRoomCodes', () => {
  it('🔴 "ม.1/2" ต้องมาก่อน "ม.1/10" (เทียบสตริงดิบจะกลับกัน)', () => {
    expect(sortRoomCodes(['ม.1/10', 'ม.1/2'])).toEqual(['ม.1/2', 'ม.1/10'])
  })

  it('เรียงตามระดับก่อน แล้วค่อยเลขห้อง', () => {
    expect(sortRoomCodes(['ม.5/1', 'ม.4/9', 'ม.1/1', 'ม.2/1'])).toEqual([
      'ม.1/1',
      'ม.2/1',
      'ม.4/9',
      'ม.5/1',
    ])
  })

  it('ไม่แก้ค่าต้นทาง (คืนอาร์เรย์ใหม่)', () => {
    const src = ['ม.5/1', 'ม.1/1']
    sortRoomCodes(src)
    expect(src).toEqual(['ม.5/1', 'ม.1/1'])
  })

  it('รหัสที่ไม่มี "/" ต้องไม่ทำให้พัง (ข้อมูลจริงอาจมีห้องพิมพ์ผิด)', () => {
    expect(() => sortRoomCodes(['ม.6', 'ม.1/1'])).not.toThrow()
  })
})

describe('roomOptions', () => {
  it('แปลง Room[] → ตัวเลือกที่เรียงแล้ว (value === label เพราะผู้ใช้พิมพ์รหัสห้องกัน)', () => {
    const rooms: Room[] = [
      { id: 2, room_code: 'ม.1/10', room_name: 'ม.1/10' },
      { id: 1, room_code: 'ม.1/2', room_name: 'ม.1/2' },
    ]
    expect(roomOptions(rooms)).toEqual([
      { value: 'ม.1/2', label: 'ม.1/2' },
      { value: 'ม.1/10', label: 'ม.1/10' },
    ])
  })

  it('ไม่มีห้องเลย → [] (หน้าจอยังวาดได้ แต่เลือกปลายทางไม่ได้ ⇒ ยังมี blocker คุมอยู่)', () => {
    expect(roomOptions([])).toEqual([])
  })
})

// ============================================================
// 9. ข้อความหลังทำสำเร็จ + ชื่อคนในรายงานกระทบยอด
// ============================================================

describe('applyResultText', () => {
  const result: RolloverApplyResult = {
    run_id: 9,
    from_year: { id: 1, year_be: 2568, name: 'ปีการศึกษา 2568' },
    to_year: { id: 2, year_be: 2569, name: 'ปีการศึกษา 2569' },
    promoted_count: 10,
    graduated_count: 2,
    staff_carried_count: 3,
    positions_reset_count: 1,
    closed_count: 15,
    room_overrides: {},
    plan: {},
  }

  it('🔴 ใช้ตัวเลขที่ **เกิดขึ้นจริง** จาก response ไม่ใช่ค่าที่ preview ไว้', () => {
    const text = applyResultText(result)
    expect(text).toContain('10')
    expect(text).toContain('2')
    expect(text).toContain('15') // closed_count — แถวปีเก่าที่ถูกปิด
  })

  it('🔴 ต้องบอกว่าปีไหนกลายเป็นปีปัจจุบัน — เป็นผลที่ผู้ใช้ต้องรู้ทันที', () => {
    expect(applyResultText(result)).toContain('ปีการศึกษา 2569')
    expect(applyResultText(result)).toContain('ปีปัจจุบัน')
  })

  it('ไม่พูดถึงส่วนที่เป็น 0 (เช่นโรงเรียนที่ไม่มีใครจบ)', () => {
    const text = applyResultText({ ...result, graduated_count: 0, staff_carried_count: 0 })
    expect(text).not.toContain('จบ')
    expect(text).not.toContain('บุคลากร')
  })
})

describe('personName', () => {
  it('มีชื่อ+นามสกุล → ต่อด้วยช่องว่าง', () => {
    expect(
      personName({
        user_id: 1,
        student_id: '12345',
        first_name: 'สมชาย',
        last_name: 'ใจดี',
        class_role: 'student',
        room_code: 'ม.5/1',
      }),
    ).toBe('สมชาย ใจดี')
  })

  it('มีแค่ชื่อ → ไม่มีช่องว่างเกิน', () => {
    expect(
      personName({
        user_id: 1,
        student_id: null,
        first_name: 'สมชาย',
        last_name: null,
        class_role: null,
        room_code: null,
      }),
    ).toBe('สมชาย')
  })

  it('🔴 ไม่มีชื่อเลย → ยังต้องอ่านออกว่าเป็นใคร (ใช้รหัสนักเรียน) ไม่ใช่ช่องว่างเปล่า', () => {
    const name = personName({
      user_id: null,
      student_id: '99999',
      first_name: null,
      last_name: null,
      class_role: null,
      room_code: null,
    })
    expect(name).toContain('99999')
    expect(name.trim()).not.toBe('')
  })

  it('ชื่อเป็นช่องว่างล้วน → ถือว่าไม่มีชื่อ', () => {
    const name = personName({
      user_id: null,
      student_id: '1',
      first_name: '   ',
      last_name: '',
      class_role: null,
      room_code: null,
    })
    expect(name).toContain('รหัส')
  })
})

// ============================================================
// 10. รูปร่างของ type — `RolloverPreview` ต้องเป็น plan + run_id เท่านั้น
// ============================================================

describe('RolloverPreview', () => {
  it('มีทุกคีย์ของ plan บวก `run_id` (ถ้า backend เพิ่มคีย์ที่ UI ไม่รู้ type-check จะจับ)', () => {
    const preview: RolloverPreview = { ...makePlan(), run_id: 3 }
    expect(preview.run_id).toBe(3)
    expect(preview.can_apply).toBe(true)
  })
})
