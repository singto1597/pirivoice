/**
 * 🧪 `router/unavailable.ts` — "เนื้อหาที่ลิงก์ชี้ไปเปิดดูไม่ได้แล้ว" (บั๊ก #32 / A4)
 *
 * **ทำไมต้องมีเทสนี้:** ผู้ใช้ที่มาถึงเส้นนี้เกือบทั้งหมด **กด notification หรือกด push**
 * ซึ่งเป็นลิงก์ที่ระบบสร้างเอง ⇒ เขาไม่ได้ตั้งใจเปิดหน้าที่ตายแล้ว และ **ไม่มีทางรู้ได้เลย**
 * ว่าทำไมกดแล้วไม่มีอะไรเกิดขึ้น · ถ้าจุดใดจุดหนึ่งในสามจุดต่อสายผิด
 * (หน้าที่เจอ 404 ไม่เรียก · หน้าที่แสดงอ่านค่าผิดคีย์ · ข้อความไม่มี)
 * ผลลัพธ์คือ **ความเงียบ** — ซึ่งแยกไม่ออกจาก "ยังไม่ deploy" หรือ "เน็ตช้า"
 *
 * ⭐ **สิ่งที่เทสนี้พิสูจน์เพิ่มจาก "ฟังก์ชันทำงาน":** `goUnavailable()` กับ
 * `readUnavailable()` เป็น **คู่ผู้ผลิต–ผู้บริโภคที่ผูกกันผ่าน URL** ไม่ใช่ผ่านการเรียก
 * ฟังก์ชัน ⇒ type ไม่เชื่อมให้ · เทส `U4` จึง **ส่งค่าที่ `goUnavailable` ผลิตจริง
 * กลับเข้า `readUnavailable`** แล้วบังคับให้ครบวง — เพิ่มชนิดใหม่แล้วลืมฝั่งใดฝั่งหนึ่ง
 * จะตกที่เทสนี้ ไม่ใช่ไปโผล่เป็น Swal ที่ไม่ขึ้นบน staging
 *
 * ⚠️ **ต้องกรองค่าที่รู้จัก ไม่ใช่ cast** — query นี้ใครก็ใส่ได้ (`?unavailable=<มั่ว>`)
 *   ถ้า cast แล้วเอาไปเข้า `Record` จะได้ `undefined` ไปแสดงเป็นข้อความให้ผู้ใช้เห็น
 */
import { describe, expect, it, vi } from 'vitest'
import type { Router } from 'vue-router'
import {
  UNAVAILABLE_QUERY,
  UNAVAILABLE_TITLE,
  goUnavailable,
  readUnavailable,
  unavailableMessage,
  type UnavailableKind,
} from '@/router/unavailable'

/**
 * ด่าน compile-time: ถ้าเพิ่มสมาชิกใน `UnavailableKind` แล้วไม่เพิ่มที่นี่
 * ไฟล์นี้จะ **ไม่คอมไพล์** ⇒ บังคับให้มีข้อความของชนิดใหม่ก่อน merge
 * (และเทส `U4` ข้างล่างจะวนทุกตัวอัตโนมัติ เพราะอ่านจาก object นี้)
 */
const KIND_COVERAGE: Record<UnavailableKind, true> = { board: true, issue: true }
const ALL_KINDS = Object.keys(KIND_COVERAGE) as UnavailableKind[]

/** Router ปลอม — เก็บ argument ที่ `replace` ถูกเรียกด้วย */
function fakeRouter() {
  const replace = vi.fn<(to: unknown) => Promise<void>>(() => Promise.resolve())
  return { replace, router: { replace } as unknown as Router }
}

describe('readUnavailable — กรองค่าจาก URL', () => {
  it.each(ALL_KINDS)('U1: %s ผ่านได้', (kind) => {
    expect(readUnavailable(kind)).toBe(kind)
  })

  it.each([
    ['ไม่รู้จัก', 'playbook'],
    ['สตริงว่าง', ''],
    ['ตัวพิมพ์ใหญ่', 'BOARD'],
    ['มีช่องว่าง', ' board'],
    ['ตัวเลข', 7],
    ['บูลีน', true],
    ['อ็อบเจ็กต์', { kind: 'board' }],
    ['undefined', undefined],
    ['null', null],
  ])('U2: %s → null (ต้องไม่โยน exception)', (_label, raw) => {
    expect(readUnavailable(raw)).toBeNull()
  })

  it('U3: อาร์เรย์ (query ซ้ำ) → ใช้ค่าตัวแรก', () => {
    expect(readUnavailable(['board', 'issue'])).toBe('board')
    // ตัวแรกไม่รู้จัก → null ทั้งที่ตัวที่สองใช้ได้ (จงใจ: "ตัวแรกคือสิ่งที่ผู้ใช้เห็น")
    expect(readUnavailable(['bogus', 'issue'])).toBeNull()
    expect(readUnavailable([])).toBeNull()
  })
})

describe('คู่ผู้ผลิต–ผู้บริโภค (goUnavailable → readUnavailable)', () => {
  it('U4: ⭐ ทุกชนิดที่ `goUnavailable` ผลิตได้ ต้องอ่านกลับได้ครบวง', async () => {
    for (const kind of ALL_KINDS) {
      const { replace, router } = fakeRouter()
      await goUnavailable(router, kind)

      expect(replace).toHaveBeenCalledTimes(1)
      const to = replace.mock.calls[0]?.[0] as {
        name: string
        query: Record<string, unknown>
      }

      expect(to.name).toBe('notifications')
      // อ่านค่ากลับจาก query ที่ผลิตจริง — ไม่ใช่จากตัวแปร `kind` ที่ป้อนเข้าไป
      expect(readUnavailable(to.query[UNAVAILABLE_QUERY])).toBe(kind)
      // และต้องมีข้อความจริงสำหรับชนิดนั้น (ไม่ใช่ undefined)
      expect(unavailableMessage(kind).length).toBeGreaterThan(0)
    }
  })

  it('U5: ใช้ `replace` ไม่ใช่ `push` — และไม่ได้แตะ method อื่นของ router', async () => {
    // ⚠️ ถ้าใช้ `push` ปุ่มย้อนกลับจะพากลับไปที่ลิงก์ที่ตายแล้ว → เด้งกลับมาใหม่ = วนลูป
    //    (บนมือถือที่ไม่มีปุ่ม back ของเบราว์เซอร์ อาการนี้สับสนที่สุด)
    const { replace, router } = fakeRouter()
    await goUnavailable(router, 'board')
    expect(replace).toHaveBeenCalledTimes(1)
    expect(replace.mock.calls[0]?.[0]).toEqual({
      name: 'notifications',
      query: { [UNAVAILABLE_QUERY]: 'board' },
    })
  })

  it('U6: `await` ได้จริง — คืน Promise ที่ resolve หลัง replace เสร็จ', async () => {
    // ผู้เรียก (`BoardDetail`/`IssueDetail`) `await goUnavailable(...)` แล้ว `return`
    // จาก catch ⇒ ถ้าไม่ await ต่อ การโหลดรอบถัดไปอาจวิ่งทับก่อน navigate เสร็จ
    let resolved = false
    const replace = vi.fn<(to: unknown) => Promise<void>>(() => {
      return Promise.resolve().then(() => {
        resolved = true
      })
    })
    await goUnavailable({ replace } as unknown as Router, 'issue')
    expect(resolved).toBe(true)
  })
})

describe('ข้อความและค่าคงที่', () => {
  it('U7: ข้อความของแต่ละชนิดต้องไม่ว่างและไม่ซ้ำกัน', () => {
    const messages = ALL_KINDS.map((k) => unavailableMessage(k))
    for (const m of messages) expect(m.trim().length).toBeGreaterThan(0)
    expect(new Set(messages).size).toBe(messages.length)
  })

  it('U8: ข้อความต้องบอก "ซ่อนหรือถูกลบ" ทั้งคู่ — ผู้ใช้แยกสองกรณีไม่ได้', () => {
    // ⚠️ "เปิดดูไม่ได้" มีสองทางที่อยู่คนละคอลัมน์ (`deleted_at` กับ `status='hidden'`)
    //    และ API ตอบ 404 เหมือนกัน ⇒ ข้อความที่บอก רק "ถูกลบ" จะทำให้ผู้ใช้ที่แค่ถูกซ่อน
    //    เข้าใจผิดว่าข้อมูลหายไปแล้ว (คนละความรู้สึกกับ "สภาฯ ซ่อนไว้")
    for (const k of ALL_KINDS) {
      expect(unavailableMessage(k)).toContain('ซ่อน')
      expect(unavailableMessage(k)).toContain('ลบ')
    }
  })

  it('U9: ค่าคงที่ที่ผูกกับ URL/UI ต้องไม่เปลี่ยนโดยไม่ตั้งใจ', () => {
    expect(UNAVAILABLE_QUERY).toBe('unavailable')
    expect(UNAVAILABLE_TITLE.length).toBeGreaterThan(0)
  })
})
