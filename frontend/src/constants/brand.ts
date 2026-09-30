// 🎨 สีแบรนด์สำหรับโค้ด TypeScript (CSS ใช้ token ใน `tailwind.config.js` แทน)
//
// **ทำไมต้องมีไฟล์นี้:** SweetAlert2 รับสีเป็น *ค่า string* ไม่ใช่คลาส Tailwind
// ⇒ ก่อนหน้านี้ `confirmButtonColor: '#b91c1c'` ถูกพิมพ์ซ้ำ 24 จุดใน 16 ไฟล์
// (มีทั้ง `#b91c1c` และ `#B91C1C` ปนกัน) ⇒ แก้สีแบรนด์ทีต้องไล่ 24 ที่ และพิมพ์ผิดแล้วไม่มีใครจับ
//
// 🔴 **ค่าต้องตรงกับ `theme.extend.colors.brand` ใน `tailwind.config.js` เสมอ**
//    ถ้าเปลี่ยนสีแบรนด์ ต้องแก้ทั้งสองที่ (Tailwind อ่าน CSS จาก JS, TS อ่านจากไฟล์นี้
//    ⇒ รวมเป็นที่เดียวไม่ได้โดยไม่เพิ่ม dependency)

/** แดงคาร์ดินัล — สีแบรนด์หลัก (Tailwind: `brand`) */
export const BRAND = '#B91C1C'

/** แดงคาร์ดินัลเข้ม — hover/active (Tailwind: `brand-strong`) */
export const BRAND_STRONG = '#991B1B'

/** เทากลาง stone-500 — ใช้เป็นสีปุ่มรองใน Swal (Tailwind: `stone-500`) */
export const NEUTRAL = '#78716C'

/** ส้มอิฐ — ปุ่มยืนยันของ action ที่ "เตือน" ไม่ใช่ "อันตราย" (Tailwind: `warn`) */
export const WARN = '#B45309'
