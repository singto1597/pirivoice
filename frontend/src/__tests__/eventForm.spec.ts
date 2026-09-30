import { describe, it, expect } from 'vitest'
import {
  EMPTY_EVENT_FORM,
  buildCreate,
  buildPatch,
  categoryOptionsOf,
  formErrorOf,
  isDirty,
  toBaseline,
  toFormValues,
  type EventFormValues,
} from '@/eventForm'
import type { Event } from '@/types/event'

/**
 * 📝 ฟอร์มกิจกรรม — ตรรกะที่ตัดสินว่า "แก้อะไร" และ "ยังไม่บันทึกไหม"
 *
 * ⭐ สองอย่างนี้ต้องเป็น **ตัวเลขตัวเดียวกัน** — ถ้าเพี้ยนจากกัน ผู้ใช้จะเจอกล่อง
 *    "ยังไม่บันทึก ทิ้งไหม" **หลังกดบันทึกสำเร็จ** ซึ่งเป็นบั๊กที่ทำให้ผู้ใช้ไม่กล้ากดอะไรเลย
 *    (และเป็นคลาสเดียวกับที่ทำให้ฟอร์มถูกทิ้งกลางคัน ซึ่งเป็นเหตุผลที่รอบนี้ย้ายเป็นหน้าเต็มหน้า)
 */

function makeEvent(over: Partial<Event> = {}): Event {
  return {
    id: 42,
    title: 'ค่ายวิทยาศาสตร์',
    description: 'รายละเอียด',
    location: 'หอประชุม',
    cover_image_url: null,
    // 02:00Z = 09:00 ไทย — ค่าที่ `toLocalInput` ต้องแปลงถูก
    event_date: '2026-10-15T02:00:00Z',
    registration_deadline: null,
    capacity: 30,
    category: 'academic',
    status: 'published',
    published_at: '2026-10-01T00:00:00Z',
    cancelled_at: null,
    created_at: '2026-09-01T00:00:00Z',
    updated_at: null,
    deleted_at: null,
    created_by: 1,
    updated_by: null,
    created_by_name: 'สภา',
    updated_by_name: null,
    registered_count: 0,
    waitlisted_count: 0,
    ...over,
  }
}

function values(over: Partial<EventFormValues> = {}): EventFormValues {
  return { ...EMPTY_EVENT_FORM, ...over }
}

describe('toBaseline / toFormValues — แถว → ฟอร์ม', () => {
  it('★ แปลงเวลาเป็นโซนไทย (09:00 ไม่ใช่ 02:00)', () => {
    const base = toBaseline(makeEvent())
    expect(base.event_date).toBe('2026-10-15T09:00')
  })

  it('★ `registration_deadline` null → ฟอร์มได้ "" แต่ baseline ได้ null (คนละชนิดโดยเจตนา)', () => {
    // ⚠️ นี่คือจุดที่เคยเป็นบั๊ก: ถ้า `toBaseline` คืน `''` (สตริง) แต่ `buildCreate` คืน `null`
    //    สองข้างจะไม่เท่ากัน ⇒ "เปิดแล้วกดบันทึกทันที" ยิง PATCH เปล่าทุกครั้ง
    //    ⇒ เทสต์นี้ล็อกสัญญาไว้ว่า baseline เป็น *payload* (`null` = สั่งล้าง/ไม่ตั้ง)
    //      ส่วนฟอร์มเป็น *มุมมองผู้ใช้* (`''` = ช่องว่าง)
    expect(toBaseline(makeEvent()).registration_deadline).toBeNull()
    expect(toFormValues(makeEvent()).registration_deadline).toBe('')
  })

  it('`capacity` null → สตริงว่าง · มีค่า → สตริงตัวเลข', () => {
    expect(toFormValues(makeEvent({ capacity: null })).capacity).toBe('')
    expect(toFormValues(makeEvent({ capacity: 30 })).capacity).toBe('30')
  })

  it('★ หมวดที่ backend ใหม่กว่า ต้องคงค่าเดิมไว้ในช่อง (ไม่ถูกแปลงเป็น other)', () => {
    // ถ้าแปลงเป็น other ตั้งแต่เปิดฟอร์ม ผู้ใช้ที่กดบันทึกโดยแก้ช่องอื่นจะ **ลดชั้นข้อมูล**
    const e = makeEvent({ category: 'hackathon' })
    expect(toFormValues(e).category).toBe('hackathon')
    // และ `toBaseline` ต้องได้ `undefined` (ไม่ส่ง) — ดูเทสต์ round-trip ด้านล่าง
    expect(toBaseline(e).category).toBeUndefined()
  })
})

describe('★ buildPatch — "เปิดฟอร์มแล้วกดบันทึกทันที ต้องไม่ยิง PATCH"', () => {
  it.each([
    ['แถวปกติ', makeEvent()],
    ['capacity = null (ไม่จำกัด)', makeEvent({ capacity: null })],
    ['ไม่ตั้ง deadline', makeEvent({ registration_deadline: null })],
    ['มี deadline', makeEvent({ registration_deadline: '2026-10-10T02:00:00Z' })],
    ['หมวดแปลกจาก backend ใหม่กว่า', makeEvent({ category: 'hackathon' })],
    ['description = null', makeEvent({ description: null })],
    ['ฉบับร่าง', makeEvent({ status: 'draft', published_at: null })],
  ])('%s → patch ว่าง', (_label, event) => {
    const base = toBaseline(event)
    const next = buildCreate(toFormValues(event))
    expect(buildPatch(base, next)).toEqual({})
  })

  it('★ เคาะท้าย/ช่องว่างหัวท้าย ไม่นับว่าเปลี่ยน (trim ก่อนเทียบ)', () => {
    // ถ้าไม่ trim ผู้ใช้ที่เผลอเคาะท้ายช่องเดียวจะยิง PATCH เปล่า แล้ว audit log จะเต็มไปด้วย
    // รายการที่ไม่มีอะไรเปลี่ยน — และกล่อง "ยังไม่บันทึก" จะโผล่ทั้งที่ไม่มีอะไรจะเสีย
    const base = toBaseline(makeEvent())
    const next = buildCreate(values({ ...toFormValues(makeEvent()), title: '  ค่ายวิทยาศาสตร์  ' }))
    expect(buildPatch(base, next)).toEqual({})
  })

  it('★ หมวดแปลก round-trip ผ่านทั้งสองข้าง ⇒ ไม่ถือว่าเปลี่ยน', () => {
    const e = makeEvent({ category: 'hackathon' })
    const base = toBaseline(e)
    const next = buildCreate(toFormValues(e))
    // ทั้งคู่ต้องเป็น `undefined` — ไม่ใช่ข้างหนึ่ง 'other'
    expect(base.category).toBeUndefined()
    expect(next.category).toBeUndefined()
    expect(buildPatch(base, next)).toEqual({})
  })

  it('แก้ชื่อ → patch มีแค่ title', () => {
    const base = toBaseline(makeEvent())
    const next = buildCreate({ ...toFormValues(makeEvent()), title: 'ค่ายวิทยาศาสตร์ 2' })
    expect(buildPatch(base, next)).toEqual({ title: 'ค่ายวิทยาศาสตร์ 2' })
  })

  it('★ ลบข้อความในช่องออก → patch มีคีย์นั้นเป็น null (สั่งล้าง ไม่ใช่ไม่แตะ)', () => {
    // `undefined` = "ไม่แตะ" ⇒ ค่าเดิมจะไม่ถูกลบ แล้วผู้ใช้เห็นข้อความเดิมกลับมาหลังบันทึก
    const base = toBaseline(makeEvent())
    const next = buildCreate({ ...toFormValues(makeEvent()), description: '' })
    expect(buildPatch(base, next)).toEqual({ description: null })
    expect('description' in buildPatch(base, next)).toBe(true)
  })

  it('capacity: "5" → 5 · "" → null (คนละความหมาย)', () => {
    const base = toBaseline(makeEvent({ capacity: 30 }))
    expect(buildPatch(base, buildCreate({ ...toFormValues(makeEvent()), capacity: '5' }))).toEqual({
      capacity: 5,
    })
    expect(buildPatch(base, buildCreate({ ...toFormValues(makeEvent()), capacity: '' }))).toEqual({
      capacity: null,
    })
  })

  it('เปลี่ยนหมวดเป็นคีย์ที่รู้จัก → ส่งไป', () => {
    const base = toBaseline(makeEvent())
    const next = buildCreate({ ...toFormValues(makeEvent()), category: 'sports' })
    expect(buildPatch(base, next)).toEqual({ category: 'sports' })
  })
})

describe('★ isDirty — ต้องตรงกับ buildPatch เสมอ (ตัวเลขตัวเดียวกัน)', () => {
  it('เปิดฟอร์มแล้วยังไม่แตะ → ไม่สกปรก', () => {
    const e = makeEvent()
    expect(isDirty(toBaseline(e), toFormValues(e))).toBe(false)
  })

  it('โหมดสร้างใหม่ (baseline = EMPTY) → ยังไม่สกปรก', () => {
    expect(isDirty(buildCreate(EMPTY_EVENT_FORM), EMPTY_EVENT_FORM)).toBe(false)
  })

  it('แก้จริง → สกปรก', () => {
    const e = makeEvent()
    expect(isDirty(toBaseline(e), { ...toFormValues(e), title: 'ใหม่' })).toBe(true)
  })

  it('★ พิมพ์แล้วลบออก (กลับค่าเดิม) → ไม่สกปรก', () => {
    // เคสที่ `JSON.stringify(form) !== JSON.stringify(original)` ตอบผิด — ผู้ใช้จะเจอกล่อง
    // ถามทั้งที่กดบันทึกแล้วระบบไม่ยิงอะไรเลย
    const e = makeEvent()
    const v = toFormValues(e)
    expect(isDirty(toBaseline(e), { ...v, title: 'แก้ชั่วคราว' })).toBe(true)
    expect(isDirty(toBaseline(e), { ...v, title: v.title })).toBe(false)
  })

  it('★ isDirty ต้องเท่ากับ (patch ไม่ว่าง) ทุกเคส — นิยามต้องไม่มีทางเพี้ยนจากกัน', () => {
    const e = makeEvent()
    const base = toBaseline(e)
    const cases: EventFormValues[] = [
      toFormValues(e),
      { ...toFormValues(e), title: '  ' },
      { ...toFormValues(e), description: '' },
      { ...toFormValues(e), capacity: '0' },
      { ...toFormValues(e), category: 'hackathon' },
      { ...toFormValues(e), category: 'other' },
    ]
    for (const v of cases) {
      expect(isDirty(base, v)).toBe(Object.keys(buildPatch(base, buildCreate(v))).length > 0)
    }
  })
})

describe('formErrorOf — ด่านฝั่ง client (ไม่ใช่ด่านจริง)', () => {
  it('ไม่มีข้อความ ⇒ ผ่าน', () => {
    expect(formErrorOf(values({ title: 'ก', event_date: '2026-10-15T09:00' }))).toBe('')
  })

  it.each([
    ['ชื่อว่าง', { title: '' }, 'ต้องกรอกชื่อกิจกรรม'],
    ['ชื่อมีแต่ช่องว่าง', { title: '   ' }, 'ต้องกรอกชื่อกิจกรรม'],
    ['ยังไม่เลือกวัน', { event_date: '' }, 'ต้องเลือกวันและเวลาจัดกิจกรรม'],
  ])('%s → ข้อความ', (_l, over, msg) => {
    expect(
      formErrorOf(values({ title: 'ก', event_date: '2026-10-15T09:00', ...over })),
    ).toBe(msg)
  })

  it.each(['0', '-1', '1.5', 'abc'])('capacity "%s" ⇒ ปฏิเสธ', (capacity) => {
    expect(
      formErrorOf(values({ title: 'ก', event_date: '2026-10-15T09:00', capacity })),
    ).not.toBe('')
  })

  it.each(['1', '30', '999', '1e3'])('capacity "%s" ⇒ ผ่าน', (capacity) => {
    // `1e3` ผ่านโดยเจตนา — `<input type="number">` ยอมรับรูปวิทยาศาสตร์ได้ และ 1e3 = 1000
    // ที่นั่งซึ่งเป็นจำนวนเต็มที่ถูกต้อง ⇒ การปฏิเสธมันจะเป็นการห้ามสิ่งที่ถูกต้อง
    expect(formErrorOf(values({ title: 'ก', event_date: '2026-10-15T09:00', capacity }))).toBe('')
  })

  it('capacity ว่าง = ไม่จำกัด ⇒ ผ่าน', () => {
    expect(formErrorOf(values({ title: 'ก', event_date: '2026-10-15T09:00', capacity: '  ' }))).toBe('')
  })
})

describe('categoryOptionsOf — ต้องไม่ทำให้ค่าที่มีอยู่หายไปจาก dropdown', () => {
  it('หมวดที่รู้จัก ⇒ ได้ลิสต์มาตรฐาน ไม่มีตัวแปลก', () => {
    const opts = categoryOptionsOf('academic')
    expect(opts.map((o) => o.value)).not.toContain('hackathon')
    expect(opts[0]!.value).toBe('academic') // ลำดับตาม EVENT_CATEGORIES
  })

  it('★ หมวดที่ไม่รู้จัก ⇒ ต้องเป็นตัวเลือกแรก และต้องอยู่ในลิสต์', () => {
    // ถ้าไม่เติม `<select>` จะแสดงว่าง แล้วกดบันทึก = กลายเป็น 'other' เงียบ ๆ
    const opts = categoryOptionsOf('hackathon')
    expect(opts[0]).toEqual({ value: 'hackathon', label: 'hackathon (ไม่รู้จัก)' })
    expect(opts.map((o) => o.value)).toContain('hackathon')
    // และต้องยังมีตัวเลือกมาตรฐานครบ (ไม่ใช่แทนที่ทั้งลิสต์)
    expect(opts.length).toBeGreaterThan(1)
  })
})
