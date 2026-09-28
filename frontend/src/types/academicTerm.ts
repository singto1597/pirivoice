// 📅 ภาคเรียน (Academic Terms) — ใช้กรองสถิติส่วนตัว (C3) และ Home summary (B1)
// "ภาคปัจจุบัน" มีได้ตัวเดียวเสมอ (บังคับด้วย DB) — ภาคที่ไม่มี = ยังไม่ได้ตั้ง
// สถานะตั้งต้นของระบบคือ "ไม่มีภาคปัจจุบัน" ⇒ UI ต้องเขียนกำกับว่า "สถิติทั้งหมด"

export interface AcademicTerm {
  id: number
  name: string // เช่น "ภาคเรียนที่ 1/2569"
  start_date: string // YYYY-MM-DD
  end_date: string // YYYY-MM-DD — ★ รวมวันสุดท้าย (inclusive)
  is_current: boolean
  created_at: string
  updated_at: string
  deleted_at: string | null // null = ยังไม่ถูกลบ
}

export interface AcademicTermListResponse {
  items: AcademicTerm[]
  total: number
  page: number
  page_size: number
  pages: number
}

export interface AcademicTermCreatePayload {
  name: string
  start_date: string
  end_date: string
  is_current?: boolean
}

// PATCH — ส่งเฉพาะฟิลด์ที่จะแก้ (ไม่ส่ง = ไม่แตะ)
// ⚠️ ไม่มี is_current โดยเจตนา — เปลี่ยนภาคปัจจุบันต้องเรียก setCurrentTerm() เท่านั้น
//    (backend ต้องล้างตัวเก่าก่อนตั้งตัวใหม่ ⇒ มีทางเดียวที่ทำถูก)
export interface AcademicTermUpdatePayload {
  name?: string
  start_date?: string
  end_date?: string
}

// แท็บกรองสถานะ — ตรงกับ pattern `status` ของ GET /api/settings/terms
// '' = ทั้งหมดที่ยังไม่ถูกลบ (active)
export const TERM_STATUS_TABS: Array<{ value: string; label: string }> = [
  { value: 'current', label: 'ภาคปัจจุบัน' },
  { value: 'active', label: 'ทั้งหมด' },
  { value: 'deleted', label: 'ถูกลบ' },
]
