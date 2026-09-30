// 🔳 QR — **อ่าน** (decode) คิวอาร์จากเฟรมภาพ
//
// ⚠️ **ไฟล์นี้แยกจาก `qr.ts` โดยเจตนา — อย่ารวมกลับ** (เหตุผลด้านขนาดอยู่ใน `qr.ts`)
//    `jsqr` หนัก 257 kB ดิบ ⇒ มีแต่หน้าสแกนของสภา (`EventCheckIn.vue`) ที่ควรโหลด
//    ถ้าใครเผลอ `import { readQrFrame } from '@/qr'` ที่เดิม จะทำให้ chunk ใหญ่กลับไป
//    ติดหน้า `EventDetail` ของนักเรียนทุกคน
//
// 📦 `jsqr` (Apache-2.0) — **zero dependency**
//
// ⚠️ **ห้ามแตะ DOM ในไฟล์นี้** — รับ `Uint8ClampedArray` เข้า คืนสตริง/`null` ออก
//    ⇒ เทสต์ได้ใน jsdom โดยไม่ต้องมีกล้อง (การดึงเฟรมจาก `<video>` เป็นหน้าที่ของผู้เรียก)

import jsQR from 'jsqr'

/**
 * อ่าน QR จาก **เฟรมภาพ** (RGBA) — คืนข้อความที่อ่านได้ หรือ `null` ถ้าไม่พบ
 *
 * รับ `Uint8ClampedArray` แบบเดียวกับที่ `ImageData.data` เป็น ⇒ ผู้เรียกสกัดเฟรมจาก
 * `<video>` ผ่าน canvas แล้วส่งเข้ามา (หรือจะสร้างเองในเทสต์ก็ได้ — ไม่ต้องมีกล้อง)
 *
 * ⚠️ `inversionAttempts: 'dontInvert'` โดยเจตนา — ค่า default (`attemptBoth`) จะลองอ่าน
 *    ภาพกลับสีด้วย ซึ่ง **เปลืองเวลาเป็นสองเท่าต่อเฟรม** บนมือถือรุ่นเก่า และในทางปฏิบัติ
 *    เราไม่เคยแสดง QR แบบกลับสี (บัตรของเราพื้นขาวเสมอ — SVG มี `<rect fill="white">`)
 *    ⇒ ถ้าวันหน้าจะรองรับโหมดมืดเต็มรูปแบบ ค่อยเปิดค่านี้ (พร้อมยอมจ่ายเวลาที่เพิ่ม)
 */
export function readQrFrame(
  data: Uint8ClampedArray,
  width: number,
  height: number,
): string | null {
  if (width <= 0 || height <= 0) return null
  // ตรวจความยาวก่อนเรียกไลบรารี — ถ้าข้อมูลสั้นกว่าที่ประกาศ ตัวอ่านจะอ่านเลยขอบเขต
  // (undefined) แล้วคืนผลมั่ว ๆ แทนที่จะพัง ⇒ ตรวจเองจะได้ผลที่ "เงียบแต่ถูก"
  if (data.length < width * height * 4) return null

  const found = jsQR(data, width, height, { inversionAttempts: 'dontInvert' })
  return found ? found.data : null
}
