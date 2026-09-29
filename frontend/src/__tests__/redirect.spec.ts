/**
 * 🧪 `router/redirect.ts` — ด่านกัน **open redirect** ของ deep link (A4)
 *
 * **ทำไมเทสนี้สำคัญกว่าที่ชื่อไฟล์บอก:** ค่าที่ถูกกรองคือ `?redirect=` ซึ่งมาจาก URL
 * ⇒ **ผู้ใช้ควบคุมได้ 100%** · และมันถูกใช้ *หลังล็อกอินสำเร็จ* ⇒ ถ้าด่านรั่ว
 * ลิงก์ `/login?redirect=https://evil.example` จะพาเหยื่อออกนอกแอพ **ทันทีหลังใส่
 * รหัสผ่านถูก** ซึ่งเป็นฟิชชิงที่เชื่อถือได้มากเพราะต้นทางเป็นโดเมนโรงเรียนจริง
 *
 * ⚠️ **ด่านนี้ต้อง "ปฏิเสธ" ไม่ใช่ "ซ่อม"** — ค่าที่ไม่ผ่านไม่มีความหมายที่กู้ได้
 *   การพยายามตัดแต่ง (เช่น strip scheme) จะสร้างช่องใหม่ที่ต้องคิดต่อ
 *   ⇒ คืน `null` แล้วให้หน้า Login ไปหน้าแรกตามบทบาท (พฤติกรรมเดิมที่ปลอดภัย)
 *
 * 📌 เคสทั้งหมดข้างล่างเป็น **payload ที่ใช้โจมตีจริง** ไม่ใช่ตัวอย่างสมมติ —
 *   โดยเฉพาะ `/\evil.example` และ `\\evil.example` ซึ่งเป็น bypass คลาสสิก
 *   ของด่าน "ต้องขึ้นต้นด้วย /" (เบราว์เซอร์ตีความ `\` เป็น `/`)
 */
import { describe, expect, it } from 'vitest'
import { REDIRECT_QUERY, safeRedirect } from '@/router/redirect'

describe('safeRedirect — ค่าที่ต้อง "ผ่าน"', () => {
  it.each([
    '/app/boards/5',
    '/app/issues/12',
    '/app/notifications',
    '/app/home',
    '/app/boards/reports',
    '/app/issues/12?tab=comments', // query ต้องรอด (path ภายในแอพ)
  ])('R1: %s ผ่านได้', (value) => {
    expect(safeRedirect(value)).toBe(value)
  })

  it('R2: query string ตามมาด้วยต้องไม่ถูกตัดทิ้ง', () => {
    // ถ้าตัด query ทิ้ง ผู้ใช้จะถึงหน้าปลายทางแต่ **ไม่ถึงแท็บ/ตัวกรองที่ตั้งใจ**
    // = deep link "เกือบถูก" ซึ่งดูเหมือนบั๊กของปลายทาง ไม่ใช่ของด่านนี้
    const v = '/app/issues/12?tab=comments&from=push'
    expect(safeRedirect(v)).toBe(v)
  })

  it('R3: อาร์เรย์ (query ซ้ำ) → ใช้ค่าตัวแรก', () => {
    // `?redirect=/app/a&redirect=/app/b` ทำให้ vue-router คืน array
    expect(safeRedirect(['/app/boards/5', '/app/boards/9'])).toBe('/app/boards/5')
  })

  it('R4: ชื่อ query parameter ที่ guard กับหน้า Login ใช้ร่วมกัน', () => {
    // ⚠️ สองฝั่งอ้างค่าคงที่ตัวเดียวกัน ⇒ ถ้ามีคนเปลี่ยนเป็น literal ที่ใดที่หนึ่ง
    //    deep link จะ "เงียบ" (ล็อกอินเสร็จไปหน้าแรกเฉย ๆ) โดยไม่มี error
    expect(REDIRECT_QUERY).toBe('redirect')
  })
})

describe('safeRedirect — payload ที่ต้อง "ถูกปฏิเสธ"', () => {
  it.each([
    ['absolute URL', 'https://evil.example/phish'],
    ['http (ไม่ใช่ https)', 'http://evil.example'],
    ['protocol-relative', '//evil.example'],
    ['protocol-relative 3 สแลช', '///evil.example'],
    ['แบ็กสแลชนำ (bypass คลาสสิก)', '/\\evil.example'],
    ['แบ็กสแลชคู่', '\\\\evil.example'],
    ['javascript:', 'javascript:alert(1)'],
    ['data:', 'data:text/html,<script>alert(1)</script>'],
    ['path นอกแอพ', '/login'],
    ['ราก', '/'],
    ['/app เฉย ๆ ไม่มีสแลชปิด', '/app'],
    ['คำนำหน้าที่คล้ายกัน', '/application/evil'],
    ['ขึ้นต้นด้วยช่องว่าง', ' /app/boards/5'],
    ['ตัวพิมพ์ใหญ่', '/APP/boards/5'],
  ])('R5: %s ถูกปฏิเสธ → null', (_label, value) => {
    expect(safeRedirect(value)).toBeNull()
  })

  it.each([
    ['undefined', undefined],
    ['null', null],
    ['number', 42],
    ['object', { toString: () => '/app/boards/5' }],
    ['boolean', true],
    ['อาร์เรย์ที่มีแต่ค่าที่ไม่ผ่าน', ['/login', 'https://evil.example']],
    ['อาร์เรย์ว่าง', []],
  ])('R6: %s → null (ไม่โยน exception)', (_label, value) => {
    // ค่านี้มาจาก URL ⇒ รูปร่างเป็นอะไรก็ได้ · throw ที่นี่ = หน้า Login พังทั้งหน้า
    // หลังผู้ใช้ใส่รหัสผ่านถูกแล้ว (อาการ worst case)
    expect(safeRedirect(value)).toBeNull()
  })

  it('R7: ค่าที่ผ่านต้องเป็น path ภายใน origin เสมอ — ไม่มี scheme และไม่ขึ้นต้น //', () => {
    // คุณสมบัติเชิงโครงสร้าง (ไม่ผูกกับรายการ payload) — กันเคสที่ยังไม่มีใครคิดถึง
    for (const candidate of ['/app/a', '/app/a?b=c', '/app/a#d']) {
      const out = safeRedirect(candidate)
      expect(out).not.toBeNull()
      expect(out?.startsWith('/')).toBe(true)
      expect(out?.startsWith('//')).toBe(false)
      expect(out).not.toMatch(/^[a-z][a-z0-9+.-]*:/i)
    }
  })
})
