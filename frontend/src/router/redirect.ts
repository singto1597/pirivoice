/**
 * 🔗 "กลับไปที่ที่ผู้ใช้ตั้งใจจะไป" หลังล็อกอิน — สัญญาระหว่าง guard กับหน้า Login
 *
 * ⚠️ **ทำไมต้องมี** — deep link จาก push (A4) เปิดหน้าที่ต้องล็อกอินก่อนได้จริง:
 *   ผู้ใช้กด notification บนมือถือ ตอนนั้น token หมดอายุ/ยังไม่ล็อกอิน
 *   ⇒ guard เด้งไป `/login` **โดยไม่จำว่าเขาจะไปไหน** ⇒ ล็อกอินเสร็จก็ไปหน้าแรก
 *   ⇒ ผู้ใช้ต้องกลับไปกด notification ซ้ำเอง · push จึง "ไม่พาไปถึงของจริง" ทั้งที่
 *   ฝั่ง backend ส่งปลายทางที่ถูกมาแล้ว — เป็นช่องที่ทำให้ A4 ไม่ครบวง
 *
 * 🔒 **ค่านี้มาจาก URL ⇒ ถือเป็นข้อมูลที่ผู้ใช้ควบคุมได้ 100% — ต้องกรองเสมอ**
 *   ถ้าเอาไป `router.push()` ตรง ๆ จะเป็น **open redirect**: ลิงก์
 *   `/login?redirect=https://evil.example` พาเหยื่อออกนอกแอพหลังล็อกอินสำเร็จ
 *   ซึ่งเป็นรูปแบบฟิชชิงที่เชื่อถือได้มากเพราะต้นทางเป็นโดเมนโรงเรียนจริง
 *
 *   ด่านที่ใช้: **ต้องขึ้นต้นด้วย `/app/`** ⇒ ตัดทิ้งพร้อมกันทั้ง
 *     - `https://…` · `//evil.example` (absolute / protocol-relative)
 *     - `/login` · `/` (path ที่อยู่นอกแอพที่ล็อกอิน)
 *     - `javascript:…` (ต้องมี `/app/` นำหน้าจึงจะผ่าน ซึ่งเป็นไปไม่ได้)
 *   และตัด `\` เพิ่ม เพราะเบราว์เซอร์บางตัวตีความ `/\evil.example` เป็น
 *   protocol-relative เช่นเดียวกับ `//` (เป็น bypass คลาสสิกของด่าน "ต้องขึ้นต้นด้วย /")
 */

/** ชื่อ query parameter ที่ guard ใช้ส่งปลายทางไปให้หน้า Login */
export const REDIRECT_QUERY = 'redirect'

/**
 * แปลงค่าดิบจาก `route.query.redirect` เป็น path ที่ปลอดภัย — **คืน `null` ถ้าไม่ผ่าน**
 *
 * คืน `null` แทนการ "ซ่อม" ค่า: ปลายทางที่ไม่ผ่านด่านไม่มีความหมายที่กู้ได้
 * ⇒ ปลายทางต้องตัดสินใจเองว่าจะทำอะไร (หน้า Login จะไปหน้าแรกตามบทบาท)
 */
export function safeRedirect(raw: unknown): string | null {
  const value = Array.isArray(raw) ? raw[0] : raw
  if (typeof value !== 'string') return null
  if (!value.startsWith('/app/')) return null
  if (value.includes('\\')) return null
  return value
}
