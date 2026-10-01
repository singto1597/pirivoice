import { describe, it, expect } from 'vitest'
import {
  dateToInput,
  fmtDateTime,
  fmtDateTimeSec,
  fmtDateShort,
  fmtDayGroup,
  fmtDayTime,
  dayGroupKind,
  fmtRelative,
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

describe('fmtDayTime / fmtDateTimeSec — สองรูปแบบที่ R5.5 รวมเข้ามา', () => {
  it('★ fmtDayTime มีวันและเวลา แต่ **ไม่มีปี** (ปีซ้ำกับบริบทที่โชว์อยู่แล้ว)', () => {
    // เทียบกับสตริงคงที่ ไม่คำนวณค่าคาดหวังด้วย `Date` ในเทสต์ — ตามกฎหัวไฟล์
    expect(fmtDayTime('2026-10-15T02:00:00Z')).toBe('15 ต.ค. 09:00')
    expect(fmtDayTime('2026-10-15T02:00:00Z')).not.toContain('2569')
  })

  it('★ fmtDateTimeSec มีวินาที — ตัวเดียวในระบบที่ทำ (ใช้กับบันทึกการใช้งาน)', () => {
    expect(fmtDateTimeSec('2026-10-15T02:00:25Z')).toBe('15 ต.ค. 2569 09:00:25')
  })

  it('★ fmtDateTimeSec ต่างจาก fmtDateTime *เฉพาะ* วินาที — ไม่ใช่วันที่คนละรูปแบบ', () => {
    // 🔴 เทสต์นี้กันการแก้ `day:` ในตัวใดตัวหนึ่งโดยไม่แก้อีกตัว — ซึ่งจะทำให้ "บันทึกการใช้งาน"
    //    กับหน้าอื่นโชว์วันที่คนละหน้าตา (อาการเดียวกับที่ R5.5 กำลังเก็บกวาด)
    const base = fmtDateTime('2026-10-15T02:00:25Z')
    const withSec = fmtDateTimeSec('2026-10-15T02:00:25Z')
    expect(withSec.startsWith(base)).toBe(true)
    expect(withSec).not.toBe(base)
  })

  it('★ วันที่หลักเดียว: `fmtDateShort` ไม่มีศูนย์นำ แต่ตัวที่มีเวลา **มี** (กฎเดียวทั้งแอป)', () => {
    // 🔴 ดูเหมือนไม่สม่ำเสมอ แต่เป็นกฎที่เขียนไว้ในหัว `datetime.ts` โดยเจตนา:
    //    วันที่ล้วนอ่านเป็นประโยค · วันที่+เวลาอยู่ในคอลัมน์ที่ต้องตรงหลักกัน
    //    ⇒ เทสต์นี้ล็อกกฎไว้ กันคน "แก้ให้สม่ำเสมอ" แล้วทำตารางทั้งแอปเลื่อน
    expect(fmtDateShort('2026-10-01T02:00:00Z')).toBe('1 ต.ค. 2569')
    expect(fmtDayTime('2026-10-01T02:00:00Z')).toBe('01 ต.ค. 09:00')
    expect(fmtDateTime('2026-10-01T02:00:00Z')).toBe('01 ต.ค. 2569 09:00')
  })

  it('★ ไม่พึ่งโซนเครื่อง — offset ต่างกันที่หมายถึงเวลาเดียวกันให้ผลเท่ากัน', () => {
    expect(fmtDayTime('2026-10-15T02:00:00Z')).toBe(fmtDayTime('2026-10-15T09:00:00+07:00'))
    expect(fmtDateTimeSec('2026-10-15T02:00:00Z')).toBe(fmtDateTimeSec('2026-10-15T09:00:00+07:00'))
  })
})

describe('🔴 ค่าที่ใช้ไม่ได้ ⇒ สตริงว่าง — กฎเดียวกันทั้งไฟล์', () => {
  // ⭐ R5.5: ทุกฟังก์ชันแสดงผลผ่านประตูเดียว (`toDate`) ⇒ สัญญาเดียวกันหมด
  //
  // 🔴 **ทำไมต้องมีบล็อกนี้แยก** — ก่อน R5.5 ฟังก์ชันพวกนี้เรียก `new Date(iso)` ตรง ๆ
  //    ⇒ `new Date(null)` ได้ **1 ม.ค. 1970** ซึ่ง `toLocaleString` พิมพ์ออกมาสวย ๆ ว่า
  //    "01 ม.ค. 1970 07:00" — ดูเหมือนข้อมูลจริงจนไม่มีใครเอะใจ และ **ไม่มี type error**
  //    เพราะ `null` ถูกส่งเข้า `iso: string` ได้ก็ต่อเมื่อผู้เรียกประกาศ type หลวม
  //    ⇒ เทสต์นี้คือสิ่งเดียวที่กันไม่ให้มันกลับมา

  const BAD: Array<string | null | undefined> = ['', null, undefined, 'ไม่ใช่วันที่']

  it('ทุกฟังก์ชันคืนสตริงว่าง — ไม่ใช่ "Invalid Date" และไม่ใช่ปี 1970', () => {
    for (const bad of BAD) {
      expect(fmtDateTime(bad)).toBe('')
      expect(fmtDateTimeSec(bad)).toBe('')
      expect(fmtDateShort(bad)).toBe('')
      expect(fmtDayTime(bad)).toBe('')
      expect(fmtTime(bad)).toBe('')
    }
  })

  it('★ `null` ต้อง **ไม่** กลายเป็น 1 ม.ค. 1970 — กับดักที่ type จับไม่ได้', () => {
    expect(fmtDateTime(null)).not.toContain('1970')
    expect(fmtDateShort(null)).not.toContain('1970')
  })

  it('ฟังก์ชันนับแบบสัมพัทธ์ก็คืนสตริงว่าง (ค่าเริ่มต้นเดิมของมัน)', () => {
    for (const bad of BAD) {
      expect(fmtRelative(bad)).toBe('')
      expect(fmtDayGroup(bad)).toBe('')
      expect(dayGroupKind(bad)).toBe('invalid')
    }
  })

  it('★ ค่าที่ *ถูกต้อง* ยังผ่านปกติ — การ์ดนี้ไม่ได้ทำให้ทุกอย่างว่าง', () => {
    // กันการแก้ที่ "ปิดประตูหนี" — เช่น `toDate` ที่คืน `null` ตลอด
    expect(fmtDateTime('2026-10-15T02:00:00Z')).not.toBe('')
    expect(fmtDayTime('2026-10-15T02:00:00Z')).not.toBe('')
  })
})

describe('fmtRelative — "ผ่านมาเท่าไร" สำหรับลิสต์ที่ต้องกวาดตา', () => {
  // ⚠️ ทุกเคสป้อน `now` เป็น **ค่าคงที่** (ไม่เรียก `new Date()` ในเทสต์)
  //    ⇒ เทสต์นี้พิสูจน์ตรรกะจริง ไม่ใช่แค่ "เครื่องนี้โซนเดียวกันจึงผ่าน"
  const NOW = new Date('2026-10-15T09:00:00+07:00') // 09:00 น. ไทย

  it('★ "เมื่อวาน" ต้องหมายถึงเมื่อวานตามปฏิทินไทย ไม่ใช่ 24–48 ชม.ที่แล้ว', () => {
    // 23:00 เมื่อวาน ห่างแค่ 10 ชม. แต่เป็น *คนละวัน* ซึ่งเป็นสิ่งที่ผู้ใช้อ่าน
    expect(fmtRelative('2026-10-14T23:00:00+07:00', NOW)).toBe('เมื่อวาน')
    // 10:00 เมื่อวาน ห่าง 23 ชม. ⇒ ต้องเป็น "เมื่อวาน" ไม่ใช่ "23 ชั่วโมงที่แล้ว"
    expect(fmtRelative('2026-10-14T10:00:00+07:00', NOW)).toBe('เมื่อวาน')
  })

  it('★ ของเมื่อวาน 23:00 เปิดดูตอน 01:00 → "เมื่อวาน" (ไม่ใช่ "2 ชั่วโมงที่แล้ว")', () => {
    // 🔴 นี่คือความต่างระหว่าง "เทียบวันที่" กับ "หารด้วย 86400000"
    //    ห่างกันแค่ 2 ชม. แต่เป็นคนละวัน ⇒ ผู้ใช้ที่เปิดลิสต์ตอนตี 1 ต้องเห็น "เมื่อวาน"
    //    ไม่ใช่ "2 ชั่วโมงที่แล้ว" ซึ่งอ่านแล้วเหมือนเพิ่งเกิด ทั้งที่เป็นของเมื่อวาน
    const lateNight = new Date('2026-10-15T01:00:00+07:00')
    expect(fmtRelative('2026-10-14T23:00:00+07:00', lateNight)).toBe('เมื่อวาน')
  })

  it('★ 23 ชม. ที่ยังเป็นวันเดียวกัน → นับเป็นชั่วโมงจริง', () => {
    // เส้นแบ่งอีกด้าน: อยู่ในวันเดียวกันทั้งคู่ ⇒ ต้องนับชั่วโมง ไม่ใช่ตัดเป็น "เมื่อวาน"
    const late = new Date('2026-10-15T23:30:00+07:00')
    expect(fmtRelative('2026-10-15T00:30:00+07:00', late)).toBe('23 ชั่วโมงที่แล้ว')
    expect(fmtRelative('2026-10-15T22:30:00+07:00', late)).toBe('1 ชั่วโมงที่แล้ว')
  })

  it('นาที / ชั่วโมง ภายในวันเดียวกัน', () => {
    expect(fmtRelative('2026-10-15T08:59:30+07:00', NOW)).toBe('เมื่อสักครู่')
    expect(fmtRelative('2026-10-15T08:55:00+07:00', NOW)).toBe('5 นาทีที่แล้ว')
    expect(fmtRelative('2026-10-15T08:00:00+07:00', NOW)).toBe('1 ชั่วโมงที่แล้ว')
    expect(fmtRelative('2026-10-15T06:30:00+07:00', NOW)).toBe('2 ชั่วโมงที่แล้ว')
  })

  it('★ 7 วันคือเส้นแบ่ง — 6 วันยังนับ 7 วันเปลี่ยนเป็นวันที่จริง', () => {
    expect(fmtRelative('2026-10-09T09:00:00+07:00', NOW)).toBe('6 วันที่แล้ว')
    // 8 ต.ค. = 7 วัน ⇒ ต้องเป็นวันที่จริง ไม่ใช่ "7 วันที่แล้ว"
    const seven = fmtRelative('2026-10-08T09:00:00+07:00', NOW)
    expect(seven).not.toContain('วันที่แล้ว')
    expect(seven).toContain('2569') // พ.ศ.
  })

  it('★ อนาคตเล็กน้อย (นาฬิกาเครื่องผู้ใช้เพี้ยน) → "เมื่อสักครู่" ไม่ใช่ค่าติดลบ', () => {
    expect(fmtRelative('2026-10-15T09:05:00+07:00', NOW)).toBe('เมื่อสักครู่')
    expect(fmtRelative('2026-10-16T09:00:00+07:00', NOW)).not.toMatch(/-/)
  })

  it('★ ไม่พึ่งโซนเครื่อง — offset ต่างกันที่หมายถึงเวลาเดียวกันให้ผลเท่ากัน', () => {
    expect(fmtRelative('2026-10-15T02:00:00Z', NOW)).toBe(fmtRelative('2026-10-15T09:00:00+07:00', NOW))
  })

  it('ค่าที่ใช้ไม่ได้คืนสตริงว่าง (ไม่ใช่ "Invalid Date" บนจอ)', () => {
    expect(fmtRelative('', NOW)).toBe('')
    expect(fmtRelative('ไม่ใช่วันที่', NOW)).toBe('')
  })
})

describe('fmtDateShort — วันที่ล้วน พ.ศ.', () => {
  it('ไม่มีเวลา และเป็นปี พ.ศ.', () => {
    const s = fmtDateShort('2026-10-15T02:00:00Z')
    expect(s).toContain('2569')
    expect(s).not.toContain(':')
  })

  it('★ ตรึง Asia/Bangkok — 20:00Z ของวันที่ 14 ต้องเป็นวันที่ 15', () => {
    expect(fmtDateShort('2026-10-14T20:00:00Z')).toBe(fmtDateShort('2026-10-15T03:00:00Z'))
  })
})

describe('fmtDayGroup — ป้ายหัวกลุ่มของลิสต์ที่จัดกลุ่มตามวัน', () => {
  // 15 ต.ค. 2026 09:00 น. ไทย — ค่าเดียวกับชุด `fmtRelative` ด้านบน
  const NOW = new Date('2026-10-15T09:00:00+07:00')

  it('วันเดียวกัน = "วันนี้"', () => {
    expect(fmtDayGroup('2026-10-15T09:00:00+07:00', NOW)).toBe('วันนี้')
    expect(fmtDayGroup('2026-10-15T00:00:01+07:00', NOW)).toBe('วันนี้')
    expect(fmtDayGroup('2026-10-15T23:59:59+07:00', NOW)).toBe('วันนี้')
  })

  it('วันก่อนหน้าหนึ่งวัน = "เมื่อวาน"', () => {
    expect(fmtDayGroup('2026-10-14T23:59:00+07:00', NOW)).toBe('เมื่อวาน')
    expect(fmtDayGroup('2026-10-14T00:00:01+07:00', NOW)).toBe('เมื่อวาน')
  })

  it('★ เส้นแบ่งวันคือ *ปฏิทินไทย* ไม่ใช่ 24 ชั่วโมง', () => {
    // 23:00 เมื่อวาน ห่างจาก 09:00 วันนี้แค่ 10 ชม. แต่ต้องเป็น "เมื่อวาน"
    expect(fmtDayGroup('2026-10-14T23:00:00+07:00', NOW)).toBe('เมื่อวาน')
    // 00:30 วันนี้ ห่างแค่ 8.5 ชม. และต้องเป็น "วันนี้"
    expect(fmtDayGroup('2026-10-15T00:30:00+07:00', NOW)).toBe('วันนี้')
  })

  it('เก่ากว่าเมื่อวาน = วันที่จริง (พ.ศ.) ไม่ใช่ "N วันที่แล้ว"', () => {
    const s = fmtDayGroup('2026-10-13T09:00:00+07:00', NOW)
    expect(s).not.toContain('วันที่แล้ว')
    expect(s).toContain('2569')
    // ⚠️ หัวกลุ่มต้อง *ไม่ซ้ำ* กับป้ายวันนี้/เมื่อวาน ไม่งั้นอัดกลุ่มด้วยสตริงไม่ได้
    expect(['วันนี้', 'เมื่อวาน']).not.toContain(s)
  })

  it('★ ไม่พึ่งโซนเครื่อง — offset ต่างกันที่หมายถึงเวลาเดียวกันให้ผลเท่ากัน', () => {
    expect(fmtDayGroup('2026-10-15T02:00:00Z', NOW)).toBe(fmtDayGroup('2026-10-15T09:00:00+07:00', NOW))
    // 20:00Z ของวันที่ 14 = 03:00 วันที่ 15 ตามเวลาไทย ⇒ ต้องเป็น "วันนี้" ไม่ใช่ "เมื่อวาน"
    expect(fmtDayGroup('2026-10-14T20:00:00Z', NOW)).toBe('วันนี้')
  })

  it('ค่าที่ใช้ไม่ได้คืนสตริงว่าง (ให้ผู้เรียกข้ามไป ไม่ใช่โชว์หัวกลุ่มเปล่า)', () => {
    expect(fmtDayGroup('', NOW)).toBe('')
    expect(fmtDayGroup('ไม่ใช่วันที่', NOW)).toBe('')
  })

  it('★ อัดกลุ่มได้จริง — ทุกวันที่มีค่าต่างกัน จึงไม่มีสองกลุ่มถูกยุบรวม', () => {
    const days = ['2026-10-15', '2026-10-14', '2026-10-13', '2026-10-12']
    const labels = days.map((d) => fmtDayGroup(`${d}T09:00:00+07:00`, NOW))
    expect(new Set(labels).size).toBe(labels.length)
  })
})

describe('dayGroupKind — ชนิดของกลุ่มวัน (สัญญาที่ NotificationCenter พึ่ง)', () => {
  const NOW = new Date('2026-10-15T09:00:00+07:00')

  it('คืนชนิดตรงกับป้ายที่ fmtDayGroup แสดง — ทั้งสองต้องไม่มีทางไม่ตรงกัน', () => {
    const cases: Array<[string, string, string]> = [
      ['2026-10-15T09:00:00+07:00', 'today', 'วันนี้'],
      ['2026-10-14T23:59:00+07:00', 'yesterday', 'เมื่อวาน'],
      ['2026-10-13T09:00:00+07:00', 'date', '13 ต.ค. 2569'],
    ]
    for (const [iso, kind, label] of cases) {
      expect(dayGroupKind(iso, NOW)).toBe(kind)
      expect(fmtDayGroup(iso, NOW)).toBe(label)
    }
  })

  it('★ "เมื่อวาน" ต้องเป็น yesterday ตามปฏิทินไทย ไม่ใช่ตาม 24 ชั่วโมง', () => {
    // 14 ต.ค. 23:00 → ห่างจาก 15 ต.ค. 09:00 แค่ 10 ชม. แต่เป็น "เมื่อวาน" ตามปฏิทิน
    expect(dayGroupKind('2026-10-14T23:00:00+07:00', NOW)).toBe('yesterday')
    // 15 ต.ค. 00:30 → ห่าง 8.5 ชม. เท่านั้น และเป็น "วันนี้"
    expect(dayGroupKind('2026-10-15T00:30:00+07:00', NOW)).toBe('today')
  })

  it('🔴 วันที่อ่านไม่ได้ = invalid ไม่ใช่ date — ไม่งั้นแถวจะพิมพ์ "Invalid Date"', () => {
    // เจตนา: `invalid` ต้อง *แยก* จาก `date` เพราะ NotificationCenter ใช้ค่านี้ตัดสินว่า
    // จะแสดงผลเป็นเวลานาฬิกาหรือไม่ ⇒ ถ้ายุบรวมกัน fmtTime('') จะได้ "Invalid Date"
    expect(dayGroupKind('', NOW)).toBe('invalid')
    expect(dayGroupKind('ไม่ใช่วันที่', NOW)).toBe('invalid')
    expect(dayGroupKind('2026-10-13T09:00:00+07:00', NOW)).not.toBe('invalid')
  })
})
