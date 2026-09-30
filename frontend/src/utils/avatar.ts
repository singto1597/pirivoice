// 👤 ตัวอักษรสำหรับ avatar — แยกออกมาเป็นฟังก์ชันบริสุทธิ์เพื่อให้เทสต์ได้
//
// 🐛 บั๊กเดิม: `name.charAt(0).toUpperCase()` ให้ **"แ"** สำหรับชื่อ "แอดมิน"
//    เพราะ "แ" เป็น *สระนำหน้า* ที่ต้องคู่กับพยัญชนะที่ตามมาจึงจะอ่านออก
//    ⇒ ผู้ใช้เห็น avatar เป็นสระลอย ๆ ซึ่งดูเหมือนบั๊กการแสดงผล
//
// ⚠️ ใช้ `Array.from()` ไม่ใช่ `charAt()` — ชื่อที่มีอักขระนอกรางวัล (emoji, ตัวอักษร
//    ประกอบ) จะถูกตัดกลางตัวถ้าใช้ index ของ UTF-16 code unit

/** สระนำหน้า — ต้องดึงพยัญชนะที่ตามมาด้วย */
const THAI_LEADING_VOWELS = /[เแโใไ]/

/** วรรณยุกต์/สระบน-ล่าง — ข้ามเมื่อกำลังหาพยัญชนะฐาน */
const THAI_COMBINING = /[ัิ-ฺ็-๎]/

/**
 * ตัวอักษรแรกของชื่อสำหรับแสดงใน avatar
 *
 * - ภาษาไทย: ถ้าเริ่มด้วยสระนำหน้า จะคืน **สระ + พยัญชนะฐาน** (เช่น "แอ")
 * - ภาษาอื่น: คืนตัวอักษรแรกแบบตัวพิมพ์ใหญ่
 * - ชื่อว่าง: คืน `fallback` (ค่าเริ่มต้น "ส" = สภานักเรียน)
 */
export function avatarCharOf(source: string | null | undefined, fallback = 'ส'): string {
  const name = (source ?? '').trim()
  if (!name) return fallback

  const [first, ...rest] = Array.from(name)
  if (!first) return fallback

  let out = ''
  let i = 0

  if (THAI_LEADING_VOWELS.test(first)) {
    out += first
    // ข้ามวรรณยุกต์ที่แทรกอยู่ก่อนพยัญชนะฐาน (เช่น "แ" + "่" + "อ")
    let next = rest[i]
    while (next !== undefined && THAI_COMBINING.test(next)) {
      i += 1
      next = rest[i]
    }
    if (next !== undefined) out += next
  } else {
    out += first
  }

  return out || fallback
}
