import { describe, it, expect } from 'vitest'
import {
  dateToInput,
  fmtDateTime,
  fmtTime,
  formatThaiDateTimeInput,
  inputToDate,
  toLocalInput,
} from '@/datetime'

/**
 * 🕐 เวลาในฟอร์มกิจกรรม — จุดที่พังแล้ว "ดูเหมือนระบบทำงานปกติ"
 *
 * ⭐ ทั้งไฟล์นี้มีเป้าหมายเดียว: **พิสูจน์ว่าเราไม่พึ่งโซนเวลาของเครื่องที่รัน**
 *    ⇒ ทุกเคสป้อนค่าคงที่แล้วเทียบกับค่าคงที่ ไม่มีเคสไหนคำนวณค่าคาดหวังด้วย `Date` เอง
 *    (ถ้าคาดหวังด้วย `Date` ในเทสต์ เทสต์จะผ่านตามเครื่องที่โซนเดียวกันเสมอ = ไม่พิสูจน์อะไร)
 *
 * ⚠️ เครื่องรัน CI อยู่โซนไหนก็ได้ — เทสต์ที่เขียนแบบ "เทียบกับ `new Date` ของตัวเอง"
 *    จะผ่านบนเครื่อง dev แล้วล้มบน CI (หรือกลับกัน) โดยหาสาเหตุไม่ได้
 */

describe('toLocalInput — ISO (UTC) → ช่องกรอกในเขตเวลาไทย', () => {
  it('★ +7 ชั่วโมง: 02:00Z ต้องกลายเป็น 09:00 ไม่ใช่ 02:00', () => {
    // นี่คือกับดักที่ `toISOString().slice(0,16)` ตกลงไปเต็ม ๆ — และอาการที่ผู้ใช้เห็นคือ
    // "เปิดฟอร์มแก้ไขแล้วเวลาน้อยไป 7 ชม." ซึ่งดูเหมือนข้อมูลใน DB ผิด ไม่เหมือนบั๊กที่ฟอร์ม
    expect(toLocalInput('2026-10-15T02:00:00Z')).toBe('2026-10-15T09:00')
  })

  it('★ ยังเป็น +7 แม้ ISO ที่ส่งมาเป็น offset อื่น (พิสูจน์ว่าไม่พึ่งโซนเครื่อง)', () => {
    // สามสตริงนี้คือ *เวลาเดียวกัน* คนละวิธีเขียน ⇒ ต้องได้ผลลัพธ์เดียวกันเป๊ะ
    const bangkok = '2026-10-15T09:00'
    expect(toLocalInput('2026-10-15T02:00:00+00:00')).toBe(bangkok)
    expect(toLocalInput('2026-10-15T09:00:00+07:00')).toBe(bangkok)
    // -05:00 ⇒ 14:00 UTC ⇒ 21:00 ไทย
    expect(toLocalInput('2026-10-15T09:00:00-05:00')).toBe('2026-10-15T21:00')
  })

  it('★ ข้ามวัน: 20:00Z ของวันที่ 14 = 03:00 ของวันที่ 15 ตามเวลาไทย', () => {
    // เคสที่ "แก้เฉพาะชั่วโมง" แล้วยังพัง — ต้องเลื่อน *วัน* ด้วย
    // (ตรงข้ามกับฝั่งถอยหลัง: 23:00Z วันที่ 15 = 06:00 วันที่ 16)
    expect(toLocalInput('2026-10-14T20:00:00Z')).toBe('2026-10-15T03:00')
    expect(toLocalInput('2026-10-15T23:00:00Z')).toBe('2026-10-16T06:00')
  })

  it('ค่า null ⇒ สตริงว่าง (ไม่ใช่ "Invalid Date" ที่จะไปโผล่ในช่องกรอก)', () => {
    // `registration_deadline` เป็น null ได้จริงและเป็นกรณีปกติ (ไม่ตั้งกำหนด = ปิดเอาวันจัด)
    expect(toLocalInput(null)).toBe('')
  })

  it('★ 23:30 ต้องเป็น "23:30" ไม่ใช่ "24:30"', () => {
    // กับดัก `hourCycle` — ค่าเริ่มต้นของ `en-GB` บางรันไทม์คืนชั่วโมง 24
    // แล้ว `<input type="datetime-local">` **ปฏิเสธค่า `24:30`** ⇒ ช่องว่างเปล่าเงียบ ๆ
    // ⇒ เปิดฟอร์มแก้ไขกิจกรรมตอน 4 ทุ่มครึ่ง แล้วช่องวันเวลาว่าง (ผู้ใช้เห็นเป็นข้อมูลหาย)
    expect(toLocalInput('2026-10-15T16:30:00Z')).toBe('2026-10-15T23:30')
  })
})

describe('inputToDate / dateToInput — round-trip ในโซนเครื่อง', () => {
  const cases = [
    '2026-10-15T09:00',
    '2026-01-01T00:00',
    '2026-12-31T23:59',
    '2027-02-28T12:34', // วันที่ที่ leap-year logic พลาดได้ง่าย
  ]

  it.each(cases)('★ ไป-กลับแล้วได้ค่าเดิมเป๊ะ: %s', (value) => {
    // ⭐ นี่คือเทสต์ที่คุ้มที่สุดในไฟล์ — `inputToDate` ใช้ local constructor และ `dateToInput`
    //    ใช้ local getters ⇒ ไม่ว่าจะรันบนโซนไหน ผลลัพธ์ต้องเป็นตัวเลขชุดเดิม
    //    ถ้ามีใครเปลี่ยนฝั่งใดฝั่งหนึ่งไปใช้ `toISOString()`/`new Date(iso)` เทสต์นี้ล้มทันที
    expect(dateToInput(inputToDate(value)!)).toBe(value)
  })

  it('★ ค่าที่ได้ต้องเป็น local ไม่ใช่ UTC — เทียบกับ component ของ Date ตรง ๆ', () => {
    // ถ้าใช้ `new Date('2026-10-15T09:00')` (ISO parse) บนเครื่องโซน UTC ค่าจะได้ 09:00
    // เหมือนกัน ⇒ เทสต์ข้างบนไม่จับ · เคสนี้จับด้วยการยืนยันว่า *ตัวเลข local* ตรงกับ input
    const d = inputToDate('2026-10-15T09:00')!
    expect(d.getFullYear()).toBe(2026)
    expect(d.getMonth()).toBe(9) // ตุลาคม = index 9
    expect(d.getDate()).toBe(15)
    expect(d.getHours()).toBe(9)
    expect(d.getMinutes()).toBe(0)
  })

  it('รูปแบบที่ไม่ใช่ YYYY-MM-DDTHH:MM ⇒ null (ไม่ใช่ Invalid Date)', () => {
    for (const bad of ['', '2026-10-15', '15/10/2026 09:00', '2026-10-15T09', 'เมื่อวาน']) {
      expect(inputToDate(bad)).toBeNull()
    }
  })

  it('★ 31 ก.พ. (วันที่ไม่มีอยู่จริง) ⇒ null ไม่ใช่ 3 มี.ค.', () => {
    // `new Date(2026, 1, 31)` **ไม่โยน** — มันเลื่อนไป 3 มี.ค. เงียบ ๆ
    // ⇒ ถ้าไม่ดัก ผู้ใช้พิมพ์/วางวันที่ผิดแล้วระบบบันทึกเป็นเดือนอื่นให้โดยไม่มีใครรู้
    expect(inputToDate('2026-02-31T09:00')).toBeNull()
    expect(inputToDate('2026-02-30T09:00')).toBeNull()
    // แต่ 29 ก.พ. ปีอธิกสุรทินต้องใช้ได้
    expect(inputToDate('2028-02-29T09:00')).not.toBeNull()
  })
})

describe('formatThaiDateTimeInput — คำอ่าน พ.ศ. ใต้ช่อง', () => {
  it('★ ต้องเป็น พ.ศ. (2569) ไม่ใช่ ค.ศ. (2026)', () => {
    const text = formatThaiDateTimeInput('2026-10-15T09:00')
    expect(text).toContain('2569')
    expect(text).not.toContain('2026')
  })

  it('★ ต้องมีวันและเดือนไทย และเวลาที่ตรงกับค่าที่กรอก', () => {
    const text = formatThaiDateTimeInput('2026-10-15T09:00')
    expect(text).toContain('15')
    expect(text).toContain('ตุลาคม')
    expect(text).toContain('09:00')
  })

  it('★ เวลาในคำอ่านต้องไม่ถูกเลื่อน 7 ชม. (ค่าที่กรอกคือค่าที่อ่าน)', () => {
    // กับดักคลาสเดียวกับ `toLocalInput` — ถ้าเผลอใช้ `new Date(value)` แล้วอ่านแบบ UTC
    // คำอ่านจะบอก 02:00 ทั้งที่ช่องกรอกว่า 09:00 ⇒ ผู้ใช้เชื่อคำอ่านแล้วกดบันทึกผิด
    expect(formatThaiDateTimeInput('2026-10-15T09:00')).toContain('09:00')
    expect(formatThaiDateTimeInput('2026-10-15T09:00')).not.toContain('02:00')
  })

  it('★ ปีใหม่ต้องเลื่อน พ.ศ. ถูกต้อง (1 ม.ค. 2027 → 2570)', () => {
    // เคสที่พลาดได้ง่ายถ้าเขียน "บวก 543 ที่ปี" แบบไม่ดูเดือน — แต่ที่จริงจับกับปีของวันที่นั้น
    expect(formatThaiDateTimeInput('2027-01-01T00:00')).toContain('2570')
    expect(formatThaiDateTimeInput('2026-12-31T23:59')).toContain('2569')
  })

  it('★ กลางคืนต้องอ่านเป็น 00:xx / 23:xx (ไม่ใช่ 24:xx)', () => {
    // ⚠️ เคสปีใหม่ข้างบนแตะ 00:00 กับ 23:59 แล้ว แต่ **ตรวจแค่ปี** ⇒ เพิ่มเคสนี้ให้ตรึง *ชั่วโมง*
    //    ที่ขอบเที่ยงคืน ซึ่งเป็นค่าที่ผู้ใช้เห็นในคำอ่านโดยตรง
    //
    // ⚠️ **เทสต์นี้ไม่จับการถอด `hourCycle: 'h23'` ออก บนเครื่องนี้** — ตรวจด้วย mutation แล้ว
    //    ยังเขียว เพราะ Node 22 + full ICU ให้ `h23` โดยปริยายอยู่แล้ว ⇒ ตัวที่กันจริงคือ
    //    บรรทัดในไฟล์ impl (ดูคอมเมนต์ที่ `BKK_PARTS`) · เทสต์นี้จะทำหน้าที่จับ *ทันที*
    //    ที่ย้ายไปรันไทม์ซึ่ง default เป็น `h24`
    expect(formatThaiDateTimeInput('2026-10-15T00:30')).toContain('00:30')
    expect(formatThaiDateTimeInput('2026-10-15T00:30')).not.toContain('24:30')
    expect(formatThaiDateTimeInput('2026-10-15T23:30')).toContain('23:30')
  })

  it('ค่าที่ไม่ถูกต้อง ⇒ สตริงว่าง (ไม่ใช่ "Invalid Date" บนหน้าจอ)', () => {
    expect(formatThaiDateTimeInput('')).toBe('')
    expect(formatThaiDateTimeInput('2026-02-31T09:00')).toBe('')
  })
})

describe('fmtDateTime / fmtTime — ค่าที่แสดงในรายการ', () => {
  it('ตรึง Asia/Bangkok: 02:00Z → 09:00 น.', () => {
    expect(fmtDateTime('2026-10-15T02:00:00Z')).toContain('09:00')
    expect(fmtTime('2026-10-15T02:00:00Z')).toContain('09:00')
  })

  it('★ ไม่พึ่งโซนเครื่อง — offset ต่างกันที่หมายถึงเวลาเดียวกันให้ผลเท่ากัน', () => {
    expect(fmtDateTime('2026-10-15T02:00:00Z')).toBe(fmtDateTime('2026-10-15T09:00:00+07:00'))
    expect(fmtTime('2026-10-15T02:00:00Z')).toBe(fmtTime('2026-10-15T09:00:00+07:00'))
  })

  it('fmtTime คืนแค่ HH:MM (ไม่มีวันที่) — ใช้ในตรา "เช็คอินแล้ว"', () => {
    expect(fmtTime('2026-10-15T02:00:00Z')).not.toContain('2026')
  })
})
