// Student data models (ตรงกับ backend snake_case)

export interface Student {
  id: number
  room_id: number | null // admin/ครูสภา (school-wide) ไม่ผูกห้อง → null
  room_code?: string | null
  room_name?: string | null
  student_id: string
  student_no: number | null // ครู/แอดมิน ไม่มีเลขที่ → null
  prefix?: string | null
  first_name?: string | null
  last_name?: string | null
  nickname?: string | null
  class_role: string // ตำแหน่ง เช่น class_president, vice_academic, teacher, teacher_council, admin
  staff_level: string | null // (ครูทั่วไป) ระดับชั้นที่รับผิดชอบ เช่น ม.4
  is_admin: boolean
  permissions: string[]
  responsibilities: string[] // หมวดหน้าที่ (เฉพาะ council_member / level_vice_president)
  status: string
}

// เพิ่มผู้ใช้งานแบบ Manual (หน้า User Management) — ตรงกับ StudentCreateRequest ฝั่ง backend
export interface StudentCreatePayload {
  username: string
  password?: string // ไม่ส่ง → ระบบสุ่มรหัสผ่าน + บังคับเปลี่ยนครั้งแรก
  prefix?: string | null
  first_name: string
  last_name: string
  nickname?: string | null
  room_code?: string | null // สภา/แอดมินที่ไม่มีห้องประจำอาจไม่ต้องมี
  class_role: string
  responsibilities?: string[]
}

export interface Room {
  id: number
  room_code: string
  room_name: string
  level?: string | null
  room_number?: number | null
}

// งาน Import นักเรียนจาก Excel แบบ Queue (backend: student_import_jobs)
export type ImportJobStatus =
  | 'PENDING' // อัปโหลดแล้ว ยังไม่สั่งเริ่ม
  | 'QUEUED' // ยิงเข้า Redis แล้ว รอ worker
  | 'PROCESSING' // worker กำลังนำเข้า
  | 'COMPLETED' // เสร็จสิ้น
  | 'FAILED' // ล้มเหลว

export interface ImportJob {
  id: number
  file_name: string
  status: ImportJobStatus
  total_rows: number
  processed_rows: number
  imported_count: number
  skipped_count: number
  error_logs: string[]
  error_message: string | null
  progress_percent: number // 0-100 (backend คำนวณให้แล้ว)
  created_by: number | null
  /** 🌟 P6 — ปีที่ import เข้า · null = ใช้ปีปัจจุบันตอนประมวลผล */
  academic_year_id: number | null
  created_at: string
  started_at: string | null
  completed_at: string | null
}

// ============================================================
// 🔀 P5 — สถานะสมาชิก · ย้ายห้อง · ประวัติรายคน
// ============================================================

/**
 * สถานะแถวสมาชิก — ตรงกับ `StudentStatus` (Literal) ฝั่ง backend
 *
 * ⚠️ `promoted`/`graduated` = แถว **ปีเก่า** ที่ถูกปิดจาก rollover · `superseded` =
 *    แถวซ้ำที่ถูกแทนที่ด้วยการย้ายห้อง ⇒ ทั้งสามค่า **ไม่ใช่ "ใช้งานอยู่"**
 *    หน้าใดที่มีสิทธิ์แก้สถานะต้องไม่เสนอค่าที่ระบบตั้งเอง (ดู `STUDENT_STATUS_LABELS`)
 */
export type StudentStatus =
  | 'active'
  | 'pending'
  | 'suspended'
  | 'promoted'
  | 'graduated'
  | 'transferred_out'
  | 'left'
  | 'superseded'

/** หนึ่งรายการย้ายห้อง — มาจากตาราง `student_moves` */
export interface StudentMove {
  id: number
  from_room_id: number | null
  from_room_code: string | null
  to_room_id: number | null
  to_room_code: string | null
  academic_year_id: number | null
  year_be: number | null
  note: string | null
  moved_by: number | null
  moved_by_name: string | null
  moved_at: string | null
}

/** หนึ่งปีของชีวิตนักเรียน — แถว `students` ของปีนั้น */
export interface StudentHistoryYear {
  student_row_id: number
  academic_year_id: number | null
  year_be: number | null
  room_id: number | null
  room_code: string | null
  level: string | null
  student_no: number | null
  class_role: string
  status: string
}

/** ไทม์ไลน์ประวัติ: ข้ามปี (`years`) + ย้ายในปี (`moves`) */
export interface StudentHistory {
  user_id: number
  student_id: string | null
  full_name: string | null
  years: StudentHistoryYear[]
  moves: StudentMove[]
}

export interface MovedStudent {
  id: number
  student_id: string
  from_room_id: number | null
  to_room_id: number | null
}

export interface SkippedStudent {
  id: number
  student_id: string
  reason: string
}

/** ผล `POST /api/students/bulk-move` — `moved`+`skipped`+`superseded_ids` */
export interface BulkMoveResult {
  moved: MovedStudent[]
  skipped: SkippedStudent[]
  /** แถวซ้ำของคนเดียวกันที่ถูกตั้งเป็น `superseded` (ควรเป็น 0 ในภาวะปกติ) */
  superseded_ids: number[]
  to_room: { id: number; room_code: string }
}

export interface UnassignedStudent {
  id: number
  student_id: string
  from_room_id: number | null
  from_room_code: string | null
}

/** ผล `POST /api/students/unassign-room` — ถอดออกจากห้อง (ไม่มีห้อง = `room_id` NULL) */
export interface UnassignResult {
  unassigned: UnassignedStudent[]
  skipped: SkippedStudent[]
}

// ============================================================
// 🧠 Pure helpers — ตาม frontend.md §4 ("ว่าง ≠ พัง ≠ ยังโหลดไม่เสร็จ")
// ============================================================

/** ป้ายชื่อสถานะสมาชิก — ค่าที่ระบบตั้งเอง (`promoted`/`graduated`/`superseded`) แยกสี */
export const STUDENT_STATUS_LABELS: Record<StudentStatus, string> = {
  active: 'กำลังศึกษา',
  pending: 'รอยืนยัน',
  suspended: 'พักการเรียน',
  promoted: 'เลื่อนชั้นแล้ว (ปีเก่า)',
  graduated: 'จบการศึกษา',
  transferred_out: 'ย้ายออก',
  left: 'ออกกลางคัน',
  superseded: 'ถูกแทนที่ (แถวซ้ำ)',
}

/**
 * แถวนี้เป็น "แถวปัจจุบัน" ที่ย้าย/ถอดได้หรือไม่
 *
 * `superseded` = แถวซ้ำที่ระบบปิดไปแล้วตอนย้ายห้อง (ยังเก็บเป็นประวัติ)
 * ⇒ ถ้าเอาขึ้นรายชื่อ "เลือกแล้วย้าย" จะย้ายประวัติ ไม่ใช่ตัวเด็ก
 * (ลิสต์ backend คืนทุกสถานะของปีนั้นโดยเจตนา — การกรองเป็นหน้าที่ของหน้าจอ)
 */
export function isCurrentMember(s: Pick<Student, 'status'>): boolean {
  return s.status !== 'superseded'
}

/** ข้อความยืนยันก่อนย้ายห้อง — ต้องบอก **จำนวน + ห้องปลายทาง + ผลข้างเคียง** */
export function moveConfirmText(count: number, toRoomCode: string, note?: string | null): string {
  const parts = [`ย้ายนักเรียน ${count} คนไปห้อง «${toRoomCode}»`]
  if (note && note.trim()) parts.push(`บันทึกเหตุผล: ${note.trim()}`)
  parts.push('การย้ายจะถูกบันทึกเป็นประวัติของนักเรียนแต่ละคน')
  return parts.join(' · ')
}

/** สรุปผลหลังย้ายสำเร็จ — บอกทั้งที่ย้ายได้และที่ถูกข้าม (ไม่ซ่อนความล้มเหลวบางส่วน) */
export function moveResultText(r: BulkMoveResult): string {
  const parts = [`ย้ายสำเร็จ ${r.moved.length} คนไป «${r.to_room.room_code}»`]
  if (r.skipped.length > 0) parts.push(`ข้าม ${r.skipped.length} คน (อยู่ในห้องนี้แล้ว)`)
  if (r.superseded_ids.length > 0) parts.push(`มี ${r.superseded_ids.length} แถวซ้ำถูกแทนที่`)
  return parts.join(' · ')
}

/** ข้อความยืนยัน "ย้ายทั้งห้อง" — ต้องบอก **จำนวน + ห้องต้นทาง + ห้องปลายทาง** */
export function wholeRoomConfirmText(
  count: number,
  fromRoomCode: string,
  toRoomCode: string,
): string {
  return (
    `ย้ายนักเรียนทั้งห้อง «${fromRoomCode}» จำนวน ${count} คนไป «${toRoomCode}»` +
    ' · การย้ายจะถูกบันทึกเป็นประวัติของนักเรียนแต่ละคน'
  )
}

/**
 * ข้อความยืนยัน "ถอดออกจากห้อง" — ต้องอธิบาย **ผลที่ตามมา** ไม่ใช่แค่คำว่า "แน่ใจไหม"
 * (ผู้ใช้ต้องรู้ว่าเด็กจะไปอยู่ในสถานะ "ไม่มีห้อง" และต้องอัปไฟล์ใหม่/ย้ายกลับ)
 */
export function unassignConfirmText(count: number): string {
  return (
    `ถอดนักเรียน ${count} คนออกจากห้อง — ทั้ง ${count} คนจะอยู่สถานะ «ไม่มีห้อง» ` +
    '· ประวัติการย้ายยังถูกบันทึก · ใช้เมื่อต้องการเคลียร์ห้องแล้วนำเข้าไฟล์รายชื่อชุดใหม่'
  )
}

/** สรุปผลหลังถอดออกจากห้อง — แยก "ถอดแล้ว" กับ "ข้าม" ให้เห็นชัด */
export function unassignResultText(r: UnassignResult): string {
  const parts = [`ถอดออกจากห้องแล้ว ${r.unassigned.length} คน`]
  if (r.skipped.length > 0) parts.push(`ข้าม ${r.skipped.length} คน (ไม่มีห้องอยู่แล้ว)`)
  return parts.join(' · ')
}

/** บรรทัดสรุปหนึ่งปีในไทม์ไลน์: `"2569 · ม.5/1 · เลขที่ 12"` (ปีที่ไม่มีข้อมูล = ไม่แสดงช่องว่าง) */
export function historyYearLabel(y: StudentHistoryYear): string {
  const year = y.year_be ? `ปี ${y.year_be}` : 'ไม่ทราบปี'
  const room = y.room_code ?? 'ไม่มีห้อง'
  const no = y.student_no ? ` · เลขที่ ${y.student_no}` : ''
  return `${year} · ${room}${no}`
}

/** บรรทัดการย้าย: `"ม.1/1 → ม.1/2"` — ห้องที่ถูกลบไปแล้วต้องอ่านรู้เรื่อง ไม่ใช่ `null` */
export function moveLabel(m: StudentMove): string {
  return `${m.from_room_code ?? 'ไม่มีห้อง'} → ${m.to_room_code ?? 'ไม่มีห้อง'}`
}

export type HistoryScreenState = 'loading' | 'error' | 'empty' | 'ready'

/**
 * สถานะของแผ่นประวัติ — `error` มาก่อน `loading` โดยเจตนา (การโหลดรอบสองที่ล้ม
 * ต้องโชว์ error ไม่ใช่ค้าง skeleton ตลอดกาล)
 */
export function historyScreenState(opts: {
  isLoading: boolean
  hasError: boolean
  hasData: boolean
}): HistoryScreenState {
  if (opts.hasError) return 'error'
  if (opts.isLoading) return 'loading'
  if (!opts.hasData) return 'empty'
  return 'ready'
}
