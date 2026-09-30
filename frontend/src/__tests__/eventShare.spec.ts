import { describe, it, expect } from 'vitest'
import { eventPath, eventShareUrl } from '@/types/event'

/**
 * 🔗 ลิงก์กิจกรรมสำหรับแชร์ (4.4) — QR บนโปสเตอร์ · ลิงก์ใน LINE
 *
 * ⭐ ที่ต้องเทสต์คือ **"มี origin ติดไปด้วยเสมอ"** ซึ่งเป็นข้อเดียวที่พังแล้วเงียบสนิท:
 *    QR ที่เก็บแค่ `/app/events/7` ยัง *วาดออกมาเป็นรูปที่ถูกต้อง* ทุกพิกเซล
 *    (ดูไม่ออกด้วยตา) แต่กล้องมือถือเปิดไม่ได้เลย ⇒ อาการที่ผู้ใช้รายงานจะเป็น
 *    "QR เสีย" แล้วคนจะไปตามหาบั๊กในไลบรารี QR ซึ่งไม่ผิดอะไรเลย
 */

const ORIGIN = 'https://prsc.example.ac.th'

describe('eventShareUrl — ต้องเป็น URL เต็มเสมอ', () => {
  it('ต่อ origin เข้ากับ path ของกิจกรรม', () => {
    expect(eventShareUrl(7, ORIGIN)).toBe(`${ORIGIN}/app/events/7`)
  })

  it('★ ผลลัพธ์ต้องไม่เท่ากับ eventPath เดี่ยว ๆ — นี่คือกับดักที่ต้องกัน', () => {
    // ถ้ามีคน "ปรับ" ฟังก์ชันให้คืน `eventPath(id)` เฉย ๆ (ดูเหมือนSimplifyที่ innocuous)
    // เทสต์นี้คือสิ่งเดียวที่จับได้ — QR ยังวาดสวย แต่สแกนแล้วไม่มีโดเมน
    const url = eventShareUrl(7, ORIGIN)
    expect(url).not.toBe(eventPath(7))
    expect(url.startsWith(ORIGIN)).toBe(true)
    expect(url).toContain(eventPath(7))
  })

  it('★ ตัด `/` ท้าย origin ทิ้ง — ไม่งั้นได้ `//` กลาง URL', () => {
    // `window.location.origin` ไม่มี `/` ท้ายอยู่แล้ว แต่ผู้เรียกอื่น (หรือ config วันที่ส่ง
    // โดเมนมาจาก env) ส่งมาแบบมี slash ได้ ⇒ `https://x//app/events/7` ทำให้บางเบราว์เซอร์
    // ตีความ path เป็น absolute URL แล้ว 404
    expect(eventShareUrl(7, `${ORIGIN}/`)).toBe(`${ORIGIN}/app/events/7`)
    expect(eventShareUrl(7, `${ORIGIN}///`)).toBe(`${ORIGIN}/app/events/7`)
  })

  it('origin ที่มีพอร์ตต้องคงพอร์ตไว้ (dev server / staging)', () => {
    expect(eventShareUrl(42, 'http://localhost:5173')).toBe('http://localhost:5173/app/events/42')
  })

  it('origin ว่าง ⇒ คืน path เปล่า ๆ ไม่โยน (deployed ผิดที่ต้องเห็นได้ ไม่ใช่หน้าจอพัง)', () => {
    // `new URL(path, '')` จะ **โยน** ในกรณีนี้ — ซึ่งถ้าไม่มี try/catch จะทำให้ทั้งหน้าไม่เรนเดอร์
    // ⇒ เลือกต่อสตริงแทน เพื่อให้ความผิดปรากฏเป็นลิงก์ที่ "อ่านออกว่าผิด" มากกว่าจอขาว
    expect(eventShareUrl(7, '')).toBe('/app/events/7')
  })

  it('id ต่างกันได้ลิงก์ต่างกัน (ไม่มีการ cache/ค่าคงที่หลุด)', () => {
    expect(eventShareUrl(1, ORIGIN)).not.toBe(eventShareUrl(2, ORIGIN))
  })
})
