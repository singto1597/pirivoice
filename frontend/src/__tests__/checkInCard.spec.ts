import { describe, it, expect } from 'vitest'
import { checkInCardState } from '@/types/event'
import type {
  EventStatus,
  MyRegistration,
  PublicEvent,
  RegistrationStatus,
} from '@/types/event'

/**
 * 🔳 บัตรเช็คอิน (D2) — ตารางความจริงของ "จะโชว์อะไรในหน้า detail"
 *
 * เทสต์นี้ทำงานกับ **ฟังก์ชันบริสุทธิ์** ไม่ได้ mount `EventDetail.vue` ตามแบบที่โปรเจกต์นี้ใช้
 * (ไม่มี component test ที่ไหน mount เลย — เส้นแบ่งคือ "กติกาอยู่นอกเทมเพลต แล้วเทสต์กติกา")
 */

/** `mine` ขั้นต่ำที่ฟังก์ชันใช้จริง — ไม่ต้องประกอบ object เต็ม 15 ฟิลด์ให้รกตา */
function mine(over: {
  check_in_token?: string | null
  status?: RegistrationStatus
} = {}): Pick<MyRegistration, 'check_in_token' | 'status'> {
  return { check_in_token: 'PIRI-EVT1:7:42:abc123', status: 'registered', ...over }
}

function event(status: PublicEvent['status']): Pick<PublicEvent, 'status'> {
  return { status }
}

describe('checkInCardState — ใครได้บัตร', () => {
  it('มีโทเคน + ยังไม่เช็คอิน → โชว์คิวอาร์', () => {
    expect(checkInCardState(mine(), event('published'))).toBe('qr')
  })

  it('★ ไม่มีโทเคน → ไม่มีบัตร (คนในคิวสำรอง)', () => {
    // backend ไม่ส่ง `check_in_token` ให้คนที่ยังไม่มีที่นั่ง ⇒ ฟังก์ชันต้องไม่ไปเดาเองว่า
    // "status เป็น waitlisted งั้นก็ไม่โชว์" — มันดูที่โทเคนเท่านั้น
    expect(checkInCardState(mine({ check_in_token: null, status: 'waitlisted' }), event('published'))).toBe('none')
  })

  it('ยังไม่สมัครเลย (null) → ไม่มีบัตร', () => {
    expect(checkInCardState(null, event('published'))).toBe('none')
  })

  it('★ เช็คอินแล้ว → ตราเช็คอิน ไม่ใช่คิวอาร์', () => {
    // สแกนซ้ำไม่ได้ให้อะไร (backend ไม่เขียนทับเวลาเดิม) ⇒ คิวอาร์ค้างอยู่จะทำให้เข้าใจผิด
    // ว่ายังต้องไปสแกนอีก — สองสภาพนี้แทนกัน ไม่ใช่ซ้อนกัน
    expect(checkInCardState(mine({ status: 'checked_in' }), event('published'))).toBe('checked_in')
  })

  it('★ กิจกรรมถูกยกเลิก → ไม่มีบัตร แม้ยังถือโทเคนอยู่', () => {
    expect(checkInCardState(mine(), event('cancelled'))).toBe('none')
  })

  it('ถูกยกเลิก + เช็คอินแล้วก็ยังไม่มีบัตร', () => {
    expect(checkInCardState(mine({ status: 'checked_in' }), event('cancelled'))).toBe('none')
  })

  it('กิจกรรมยังไม่โหลดเสร็จ (null) แต่มีโทเคน → ยังโชว์คิวอาร์', () => {
    // เกิดจริงตอนยิงสองคำขอขนานกันแล้ว `getMyRegistration` กลับมาก่อน
    // ⇒ อ้าง "โหลดไม่เสร็จ" เป็นเหตุซ่อนบัตรไม่ได้ (บัตรจะกระพริบหาย)
    expect(checkInCardState(mine(), null)).toBe('qr')
  })

  it('สถานะอื่นนอกจาก cancelled ต้องไม่ซ่อนบัตร — เงื่อนไขคือ blocklist ไม่ใช่ whitelist', () => {
    // `satisfies Record<Exclude<EventStatus,'cancelled'>>` ⇒ **เพิ่มสถานะใหม่ใน `EventStatus`
    // แล้วลืมมาเพิ่มที่นี่ = type-check พัง** (ซึ่งเป็นสิ่งที่ต้องการ: ค่าใหม่ต้องถูกตัดสินใจ
    // ว่า "โชว์บัตรหรือไม่" ไม่ใช่ตกลงไปเป็นอย่างใดอย่างหนึ่งโดยไม่มีใครรู้)
    const NON_CANCELLED = { draft: 'draft', published: 'published' } as const satisfies Record<
      Exclude<EventStatus, 'cancelled'>,
      EventStatus
    >

    for (const status of Object.values(NON_CANCELLED)) {
      expect({ status, state: checkInCardState(mine(), event(status)) }).toEqual({
        status,
        state: 'qr',
      })
    }
  })

  it('โทเคนสตริงว่าง = ไม่มีบัตร (ไม่ใช่ "มีโทเคนแต่สั้น")', () => {
    // กันกรณี backend เคยส่ง `""` มา — ค่าที่ falsy ต้องไม่ถูกตีเป็น "มีบัตร"
    // ไม่งั้นจะไปเรียก `qrSvgDataUrl('')` ซึ่งโยน แล้วผู้ใช้เห็นกล่องเตือนแทน QR
    expect(checkInCardState(mine({ check_in_token: '' }), event('published'))).toBe('none')
  })
})
