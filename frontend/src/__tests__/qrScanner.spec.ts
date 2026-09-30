import { describe, it, expect } from 'vitest'
import { SCAN_COOLDOWN_MS, checkInBanner, createScanGate } from '@/qrScanner'
import type { CheckInResult } from '@/types/event'

/**
 * 🔳 ตรรกะของหน้าสแกนเช็คอิน (D2)
 *
 * ⭐ เทสต์ชุดนี้มีไว้กันบั๊กที่ **เกิดแน่นอนถ้าไม่มีด่าน**: กล้องส่งเฟรม 60 ครั้ง/วินาที
 *    และ QR ที่ค้างอยู่ในกรอบให้ค่าเดิมทุกรอบ ⇒ ถ้าปล่อยผ่าน ระบบจะยิงเช็คอิน
 *    ซ้ำ ๆ ต่อบัตรหนึ่งใบ (สภาเห็นชื่อเด้งรัว + audit log ท่วม)
 */

const TOKEN_A = 'PIRI-EVT1:7:42:aaaaaaaaaaaaaaaaaaaaaa'
const TOKEN_B = 'PIRI-EVT1:7:43:bbbbbbbbbbbbbbbbbbbbbb'

describe('createScanGate — กันสแกนซ้ำจากกล้อง', () => {
  it('★ เฟรมรัว ๆ ของบัตรใบเดิม → ผ่านแค่ครั้งเดียว (เฟรมที่เหลือถูกทิ้ง)', () => {
    const gate = createScanGate()
    // จำลอง 10 เฟรมติดกันภายใน 1.5 วินาที (สภาถือกล้องค้างระหว่างคุยกับเด็ก)
    const accepted = Array.from({ length: 10 }, (_, i) => {
      const ok = gate.beginFrame(TOKEN_A, i * 150)
      gate.finish() // คำขอจบไว (ในเทสต์นี้สมมติว่าจบทันที)
      return ok
    })
    expect(accepted.filter(Boolean)).toHaveLength(1)
    expect(accepted[0]).toBe(true)
  })

  it('★ บัตรคนถัดไปผ่านทันที — ไม่ต้องรอ cooldown ของคนก่อนหน้า', () => {
    // คิวที่หน้างานคือยื่นบัตรต่อกันคนละใบ ⇒ ถ้า gate กันด้วย "เวลา" อย่างเดียว
    // คนที่ 2 จะถูกบล็อกทั้งที่เพิ่งมาถึง (บั๊กที่ทำให้คิวหน้าประตูติด)
    const gate = createScanGate()
    expect(gate.beginFrame(TOKEN_A, 0)).toBe(true)
    gate.finish()
    expect(gate.beginFrame(TOKEN_A, 100)).toBe(false) // ใบเดิม ยังไม่พ้น cooldown
    expect(gate.beginFrame(TOKEN_B, 200)).toBe(true) // คนละใบ ผ่านเลย
  })

  it('★ ระหว่างยิงคำขออยู่ เฟรมใหม่ถูกทิ้ง — สแกนครั้งเดียวได้ผลครั้งเดียว', () => {
    const gate = createScanGate()
    expect(gate.beginFrame(TOKEN_A, 0)).toBe(true)
    // ยังไม่เรียก finish() = คำขอยังไม่จบ
    expect(gate.beginFrame(TOKEN_B, 1000)).toBe(false)
    gate.finish()
    expect(gate.beginFrame(TOKEN_B, 1001)).toBe(true)
  })

  it('พ้น cooldown แล้วสแกนใบเดิมซ้ำได้ — การสแกนซ้ำโดยเจตนาต้องได้ผล', () => {
    const gate = createScanGate()
    expect(gate.beginFrame(TOKEN_A, 0)).toBe(true)
    gate.finish()
    expect(gate.beginFrame(TOKEN_A, SCAN_COOLDOWN_MS - 1)).toBe(false)
    expect(gate.beginFrame(TOKEN_A, SCAN_COOLDOWN_MS)).toBe(true)
  })

  it('คำขอที่ล้มเหลวก็ต้องปลดล็อก (finish ใน finally) ไม่ใช่ค้างล็อกทั้งงาน', () => {
    const gate = createScanGate()
    expect(gate.beginFrame(TOKEN_A, 0)).toBe(true)
    gate.finish() // จำลองเส้นทาง error: ผู้เรียกต้องเรียกใน finally
    expect(gate.beginFrame(TOKEN_B, 5000)).toBe(true)
  })

  it('cooldown นับจาก **เวลาที่รับ** ไม่ใช่เวลาที่จบคำขอ', () => {
    // ถ้านับจากตอนจบ คำขอที่ช้า (เน็ตช้า 2 วิ) จะทำให้ cooldown เลื่อนออกไปเรื่อย ๆ
    // ⇒ สภาที่สแกนซ้ำจะรอไม่รู้จบ
    const gate = createScanGate()
    expect(gate.beginFrame(TOKEN_A, 0)).toBe(true)
    gate.finish()
    expect(gate.beginFrame(TOKEN_A, SCAN_COOLDOWN_MS)).toBe(true)
  })

  it('reset() ล้างความจำ — ใช้ตอนกด "สแกนต่อ" ให้ใบเดิมผ่านได้ทันที', () => {
    const gate = createScanGate()
    expect(gate.beginFrame(TOKEN_A, 0)).toBe(true)
    gate.finish()
    expect(gate.beginFrame(TOKEN_A, 10)).toBe(false)
    gate.reset()
    expect(gate.beginFrame(TOKEN_A, 11)).toBe(true)
  })

  describe('beginManual — รหัสที่สภาพิมพ์เอง', () => {
    it('★ ใบเดิมที่เพิ่งสแกนไป ยังพิมพ์ซ้ำได้ทันที (cooldown ของกล้องไม่คุมคน)', () => {
      const gate = createScanGate()
      expect(gate.beginFrame(TOKEN_A, 0)).toBe(true)
      gate.finish()
      // สภาไม่เห็นชื่อรอบแรกเลยพิมพ์รหัสเดิมส่งอีกรอบ — ต้องได้ผล ไม่ใช่เงียบ
      expect(gate.beginManual(TOKEN_A, 100)).toBe(true)
    })

    it('ยังกันการยิงซ้อนระหว่างคำขอค้างอยู่', () => {
      const gate = createScanGate()
      expect(gate.beginManual(TOKEN_A, 0)).toBe(true)
      expect(gate.beginManual(TOKEN_B, 10)).toBe(false) // ยังไม่ finish
      gate.finish()
      expect(gate.beginManual(TOKEN_B, 20)).toBe(true)
    })
  })
})

describe('checkInBanner', () => {
  function result(over: Partial<CheckInResult> = {}): CheckInResult {
    return {
      registration_id: 42,
      event_id: 7,
      user_id: 99,
      user_name: 'สมชาย ใจดี',
      status: 'checked_in',
      checked_in_at: '2026-10-15T02:00:00Z',
      already_checked_in: false,
      method: 'qr',
      ...over,
    }
  }

  it('เช็คอินใหม่ → tone ok + ชื่อคน', () => {
    const b = checkInBanner(result())
    expect(b.tone).toBe('ok')
    expect(b.name).toBe('สมชาย ใจดี')
    expect(b.checkedInAt).toBe('2026-10-15T02:00:00Z')
  })

  it('★ already_checked_in → tone again (ไม่ใช่ error) แต่ยังโชว์ชื่อ', () => {
    // สภาต้องแยกออกว่า "เพิ่งนับให้" หรือ "นับไปแล้ว" — สองอันนี้ต่างกันที่การตัดสินใจ
    // ว่าจะปล่อยคนเข้าไหม ไม่ใช่แค่สีสวย ๆ
    const b = checkInBanner(result({ already_checked_in: true }))
    expect(b.tone).toBe('again')
    expect(b.name).toBe('สมชาย ใจดี')
    expect(b.title).not.toBe(checkInBanner(result()).title)
  })

  it('★ ไม่มีชื่อ (ผู้ใช้ถูกลบ) → ต้องมีข้อความสำรอง ไม่ใช่ช่องว่าง', () => {
    const b = checkInBanner(result({ user_name: null }))
    expect(b.name).toBe('ผู้ใช้ #99')
    expect(b.name.trim()).not.toBe('')
  })

  it('ไม่มีเวลา (ข้อมูลเก่า/ผิดปกติ) → null ไม่ใช่สตริงว่าง', () => {
    expect(checkInBanner(result({ checked_in_at: null })).checkedInAt).toBeNull()
  })
})
