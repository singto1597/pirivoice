/**
 * 🪪 ชื่อไทยของตำแหน่ง (class_role) — **ที่เดียวในเรพ**
 *
 * 🔴 **ทำไมต้องรวม** — ก่อนหน้านี้มีแผนที่นี้ **4 ชุดที่คัดลอกกันมา** และเลื่อนออกจากกันแล้ว:
 *
 * | รหัส | StudentList | Profile | UserManagement | useIdentity |
 * |---|---|---|---|---|
 * | `level_vice_president` | ✗ | ✗ | ✓ | ✓ |
 * | `teacher_council` | ✗ | ✓ ("ครูสภา") | ✗ | ✓ ("ครูสภานักเรียน") |
 * | `teacher` | ✗ | ✓ | ✗ | ✓ |
 * | `admin` | ✗ | ✓ ("แอดมิน") | ✗ | ✗ |
 *
 * ⇒ ที่ที่ไม่มีรหัสจะตกไปที่ `|| code` แล้วโชว์ **"admin" / "level_vice_president"
 *   เป็นภาษาอังกฤษดิบ ๆ** ซึ่งเป็นข้อที่ audit ฟ้องตรง ๆ ("Role ภาษาอังกฤษ 'admin' ใต้ชื่อ")
 *   และที่ที่มี กลับใช้ **คนละคำ** สำหรับรหัสเดียวกัน ("ครูสภา" vs "ครูสภานักเรียน")
 *
 * ⚠️ **แหล่งความจริงของ *รหัส* คือ `backend/config/roles.json`** — เพิ่มตำแหน่งใหม่ที่นั้น
 *    แล้วต้องเพิ่มป้ายที่นี่ด้วย (ไม่มีกลไกอัตโนมัติจับ เพราะคนละภาษา)
 */

/**
 * รหัสตำแหน่ง → ชื่อไทยที่ผู้ใช้อ่านออก
 *
 * 📌 ป้าย `admin` ใช้ **"ผู้ดูแลระบบ"** ไม่ใช่ "แอดมิน" (audit §6: หลีกเลี่ยงทับศัพท์
 *    ที่ผู้ใช้บางกลุ่มอ่านไม่ออก) · ส่วน `teacher_council` ใช้คำที่สื่อกว้างกว่า
 *    ("ครูสภานักเรียน") แทน "ครูสภา" ที่กำกวมว่าเป็น *สภา* ไม่ใช่ *คน*
 */
export const ROLE_LABELS: Record<string, string> = {
  student: 'นักเรียน',
  class_president: 'หัวหน้าห้อง',
  vice_academic: 'รองวิชาการ',
  vice_discipline: 'รองวินัย',
  vice_activity: 'รองกิจกรรม',
  vice_reception: 'รองปฏิคม',
  level_president: 'ประธานระดับ',
  level_vice_president: 'ผู้ช่วยหัวหน้าระดับ',
  council_member: 'สภานักเรียน',
  council_president: 'ประธานสภา',
  teacher_council: 'ครูสภานักเรียน',
  teacher: 'ครู',
  admin: 'ผู้ดูแลระบบ',
}

/**
 * ป้ายของรหัสตำแหน่ง — คืน **รหัสเดิม** เมื่อไม่รู้จัก
 *
 * ⚠️ การคืนรหัสเดิมโดยเจตนา (ไม่คืน `"—"`) — ถ้า backend เพิ่มตำแหน่งใหม่แล้วฝั่งเว็บ
 *    ยังไม่รู้จัก ผู้ดูแลจะเห็นรหัสจริงและรายงานได้ ดีกว่าเห็นขีดที่ไล่หาต้นตอไม่ได้
 */
export function roleLabel(code: string | null | undefined): string {
  if (!code) return ''
  return ROLE_LABELS[code] ?? code
}

/**
 * ตำแหน่งที่ **กำหนดให้นักเรียนในสารบบได้** — ใช้เป็นตัวเลือกในหน้าจัดการนักเรียน
 *
 * 📌 **ไม่ใช่รายการเดียวกับ `ROLE_LABELS`** — `ROLE_LABELS` มี `admin` ไว้ *แสดงผล*
 *    เพราะมีคนที่ถือตำแหน่งนั้นจริง แต่ไม่ควรเป็นตัวเลือกใน dropdown ของ "แก้ไขข้อมูลนักเรียน"
 *    ⇒ แยกสองแนวคิดออกจากกัน (แสดง vs กำหนดได้) ซึ่งเป็นเหตุผลที่เมื่อก่อนแผนที่เดียวใช้ทั้งสองงานไม่ได้
 *
 * 🐛 เดิม dropdown ของ `StudentList.vue` **ขาด `level_vice_president`** ⇒ ผู้ดูแล
 *    ตั้ง "ผู้ช่วยหัวหน้าระดับ" จากหน้าจอไม่ได้เลย ทั้งที่ backend (`config/roles.json`)
 *    รับตำแหน่งนี้มาตั้งแต่ต้น
 */
export const STUDENT_ROLE_CODES = [
  'student',
  'class_president',
  'vice_academic',
  'vice_discipline',
  'vice_activity',
  'vice_reception',
  'level_president',
  'level_vice_president',
  'council_member',
  'council_president',
] as const

/** ตัวเลือกสำหรับ `<select>` / SweetAlert `inputOptions` — สร้างจาก `STUDENT_ROLE_CODES` */
export const STUDENT_ROLE_OPTIONS: Record<string, string> = Object.fromEntries(
  STUDENT_ROLE_CODES.map((code) => [code, ROLE_LABELS[code] ?? code]),
)
