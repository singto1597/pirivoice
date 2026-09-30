import { describe, it, expect } from 'vitest'
import { qrSvgDataUrl, QR_MAX_LENGTH } from '@/qr'
import { readQrFrame } from '@/qrReader'

/**
 * 🔳 ตัวสร้าง/ตัวอ่านคิวอาร์ (D2)
 *
 * ⭐ เทสต์ที่ทรงพลังที่สุดในไฟล์นี้คือ **round-trip**: เอาผลลัพธ์จากตัวสร้าง (`qrcode-generator`)
 *    ไปป้อนให้ตัวอ่าน (`jsQR`) แล้วต้องได้ข้อความเดิมกลับมา — เป็นหลักฐานว่าไลบรารีสองตัว
 *    "ตกลงกันได้" จริง ไม่ใช่ต่างคนต่างถูกตามสเปกของตัวเอง
 *    (สองตัวนี้มาจากคนละเจ้าที่ไม่รู้จักกัน — การที่มันตรงกันคือด่านเดียวที่มีความหมาย)
 *
 * ⚠️ ต้องถอด SVG กลับเป็นเมทริกซ์เอง เพราะ `readQrFrame` กิน `Uint8ClampedArray` ดิบ
 *    (ในเบราว์เซอร์ค่ามาจาก `canvas.getImageData()`) ⇒ ที่นี่วาดเมทริกซ์เป็น RGBA เอง
 */

const CELL = 4
const MARGIN = 4

/**
 * ถอด data URL ของ SVG → ขนาด (หน่วยโมดูล) + ฟังก์ชันบอกว่าโมดูล (r,c) เป็นดำไหม
 *
 * ⚠️ **ผูกกับรูปแบบผลลัพธ์ของ `qrcode-generator` โดยเจตนา** — โมดูลดำทุกตัวถูกรวมเป็น
 *    `<path>` เดียวที่ประกอบจาก subpath หน้าตาเหมือนกันหมด (`M{x},{y}l{cell},0 0,{cell} …z`)
 *    ⇒ ตรวจแล้วกับข้อมูลจริง: 420 subpath = 420 โมดูลดำ · ไม่มี `L` (absolute) เลย
 *    ถ้าวันหน้าไลบรารีเปลี่ยนรูปแบบ เทสต์นี้จะ **พังทันที** ซึ่งเป็นพฤติกรรมที่ต้องการ —
 *    มันกำลังบอกว่า "สิ่งที่เราส่งให้ `<img>` เปลี่ยนไปแล้ว มาดูหน่อย" ไม่ใช่เงียบ ๆ ผ่าน
 *
 * ⚠️ ระยะขอบเป็น **พิกเซล** ไม่ใช่โมดูล (`margin: 4` = ขอบ 4px รอบ ๆ) ⇒ ต้องหารด้วย
 *    `CELL` ก่อนเทียบเป็นพิกัดโมดูล
 */
function parseSvgMatrix(dataUrl: string): {
  moduleCount: number
  isDark: (row: number, col: number) => boolean
} {
  const svg = atob(dataUrl.split(',')[1] ?? '')
  const totalPx = Number(/viewBox="0 0 (\d+) \d+"/.exec(svg)?.[1] ?? '0')
  const moduleCount = (totalPx - MARGIN * 2) / CELL

  const d = /<path d="([^"]+)"/.exec(svg)?.[1] ?? ''
  const dark = new Set<string>()
  for (const m of d.matchAll(/M(\d+),(\d+)l/g)) {
    const x = (Number(m[1]) - MARGIN) / CELL
    const y = (Number(m[2]) - MARGIN) / CELL
    dark.add(`${y},${x}`)
  }
  return { moduleCount, isDark: (r, c) => dark.has(`${r},${c}`) }
}

/**
 * วาดเมทริกซ์เป็น RGBA ในอัตรา `SCALE` พิกเซลต่อ 1 โมดูล
 *
 * ⚠️ **ห้ามใช้ 1 px/โมดูล** — ลองแล้ว: jsQR คืน `null` กับภาพขนาด ~29×29 px
 *    (ตัวหา finder pattern ต้องมีพิกเซลให้พอสร้างเส้น) ทั้งที่ QR นั้นถูกต้อง
 *    ⇒ เทสต์จะพังด้วยเหตุผลของ *ขนาดภาพทดสอบ* ไม่ใช่ของโค้ดที่ทดสอบ
 *    4 px/โมดูลคือภาพระดับที่กล้องมือถือส่งเข้ามาจริงในเฟรม ~640px
 */
const SCALE = 4

function matrixToRgba(isDark: (r: number, c: number) => boolean, n: number) {
  const px = n * SCALE
  const data = new Uint8ClampedArray(px * px * 4)
  for (let r = 0; r < px; r++) {
    for (let c = 0; c < px; c++) {
      const v = isDark(Math.floor(r / SCALE), Math.floor(c / SCALE)) ? 0 : 255
      const i = (r * px + c) * 4
      data[i] = data[i + 1] = data[i + 2] = v
      data[i + 3] = 255
    }
  }
  return { data, px }
}

describe('qrSvgDataUrl — ตัวสร้าง', () => {
  it('คืน data URL ของ SVG ที่มี xmlns และ viewBox ครบ', () => {
    const url = qrSvgDataUrl('PIRI-EVT1:7:42:abc123')
    expect(url.startsWith('data:image/svg+xml;base64,')).toBe(true)

    const svg = atob(url.split(',')[1] ?? '')
    expect(svg).toContain('xmlns="http://www.w3.org/2000/svg"')
    expect(svg).toMatch(/viewBox="0 0 \d+ \d+"/)
  })

  it('★ ข้อความต่างกัน → รูปต่างกัน · ข้อความเดิม → รูปเดิมเป๊ะ', () => {
    // determinism สำคัญเพราะ QR ถูกวาดใหม่ทุกครั้งที่ component re-render
    // ⇒ ถ้าไม่คงที่ รูปจะกระพริบเปลี่ยนทุกวินาที และผู้ใช้ที่แคปเจอร์ไว้จะสแกนไม่ได้
    expect(qrSvgDataUrl('ท:1')).toBe(qrSvgDataUrl('ท:1'))
    expect(qrSvgDataUrl('ท:1')).not.toBe(qrSvgDataUrl('ท:2'))
  })

  it('ข้อความว่าง → โยน (ไม่คืน QR เปล่าที่สแกนไม่ติด)', () => {
    expect(() => qrSvgDataUrl('')).toThrow('ไม่มีข้อมูลให้สร้างคิวอาร์')
  })

  it(`ข้อความยาวเกิน ${QR_MAX_LENGTH} → โยน`, () => {
    expect(() => qrSvgDataUrl('a'.repeat(QR_MAX_LENGTH + 1))).toThrow('ยาวเกิน')
  })
})

describe('readQrFrame ↔ qrSvgDataUrl — round-trip', () => {
  it.each([
    ['โทเคนเช็คอินจริง', 'PIRI-EVT1:12:3456:AbCdEfGhIjKlMnOpQrStUv'],
    ['ลิงก์กิจกรรม (4.4)', 'https://prsc-test.singto1597.xyz/app/events/42'],
    ['★ ข้อความไทย', 'กิจกรรมปลูกป่า ครั้งที่ 3'],
    ['อีโมจิ', '🎉 งานเปิดบ้าน'],
    ['สตริงสั้น', 'x'],
  ])('%s: เข้ารหัสแล้วถอดกลับได้ข้อความเดิม', (_label, text) => {
    const { moduleCount, isDark } = parseSvgMatrix(qrSvgDataUrl(text))
    const n = moduleCount + MARGIN * 2

    // เติม quiet zone รอบนอก (สเปก QR บังคับ) ก่อนป้อนให้ตัวอ่าน
    const inked = (r: number, c: number) =>
      r >= MARGIN && c >= MARGIN && r < MARGIN + moduleCount && c < MARGIN + moduleCount
        ? isDark(r - MARGIN, c - MARGIN)
        : false

    const { data, px } = matrixToRgba(inked, n)
    expect(readQrFrame(data, px, px)).toBe(text)
  })

  it('เฟรมที่ไม่ใช่ QR เลย → null (ไม่ใช่ throw)', () => {
    // กล้องหันไปโดนกำแพงเป็นเรื่องปกติของหน้าสแกน ⇒ ต้องได้ null เงียบ ๆ แล้ววนเฟรมต่อไป
    // ไม่ใช่โยนจนหน้าจอเด้ง error ใส่ผู้ใช้ทุกเฟรม
    const n = 40
    const blank = new Uint8ClampedArray(n * n * 4).fill(255)
    expect(readQrFrame(blank, n, n)).toBeNull()
  })

  it('ข้อมูลสั้นกว่าที่ประกาศ (width*height*4) → null ไม่ใช่ throw', () => {
    // `getImageData` ที่ได้ array มาไม่ครบคือสัญญาณว่าอะไรผิด แต่ทางที่ปลอดภัยคือข้ามเฟรมนั้น
    expect(readQrFrame(new Uint8ClampedArray(4), 10, 10)).toBeNull()
  })
})
