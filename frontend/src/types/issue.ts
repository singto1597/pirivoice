// Issue / Feedback data models

export type IssueLevel = 'room' | 'level' | 'council'
// ปลายทางที่ผู้แจ้งขอ (PIRI Boards): 'normal' = ดำเนินการปกติ, 'vote' = เผยแพร่เป็นโหวตสาธารณะ, 'talk' = เผยแพร่เป็นบอร์ดพูดคุยสาธารณะ
export type RequestedDestination = 'normal' | 'vote' | 'talk'
export type IssueStatus =
  | 'pending'
  | 'in_progress'
  | 'resolved'
  | 'escalated'
  | 'cancelled'
  | 'rejected'

// หมวดหลัก 3 หมวด (ตรงกับ backend config/categories.json)
export type MainCategory = 'suggestion' | 'wellbeing' | 'report'
// หมวดย่อยทั้งหมด (แต่ละหมวดย่อยอยู่ใต้หมวดหลักเดียว)
export type Category =
  | 'academic'
  | 'reception'
  | 'activity'
  | 'discipline'
  | 'democracy'
  | 'physical_health'
  | 'mental_health'
  | 'complaint'
  | 'grievance'

export interface IssueStep {
  id: number
  step_title: string
  step_detail: string | null
  step_order: number
  is_completed: boolean
  completed_at: string | null
}

export interface IssueCountdown {
  id: number
  estimated_days: number
  started_at: string
  deadline: string
  is_overdue: boolean
}

export interface Escalation {
  id: number
  from_level: string
  to_level: string
  reason: string | null
  created_at: string
}

export interface StatusHistory {
  id: number
  status: string
  note: string | null
  created_at: string
}

// คอมเมนต์ในเรื่อง (แบบ YouTube) — ชื่อจริง + เวลา + ข้อความ
export interface IssueComment {
  id: number
  user_id: number | null
  commenter_name: string | null
  commenter_room: string | null
  commenter_first_name?: string | null // ชื่อจริง (avatar ใช้ตัวแรกของชื่อ) — fallback commenter_name
  body: string
  created_at: string
  updated_at: string | null
}

// PATCH แก้ไขเรื่อง (ผู้แจ้ง) — ส่งเฉพาะฟิลด์ที่ต้องการแก้
export interface UpdateIssuePayload {
  main_category?: string
  category?: string
  title?: string
  description?: string
  is_anonymous?: boolean
}

// รายการเรื่องแบบแบ่งหน้า (จาก GET /api/issues) — total นับก่อน limit/offset
export interface IssueListResponse {
  items: Issue[]
  total: number
  page: number
  page_size: number
  pages: number
}

// จำนวนเรื่องแยกตามสถานะเดียว (zero-fill — response มีครบทั้ง 6 สถานะ)
export interface IssueStatusCount {
  status: IssueStatus
  count: number
}

// สรุปเรื่องที่ฉันแจ้ง (GET /api/issues/summary — หน้า Home/Welcome)
export interface MyIssueSummary {
  total_issues: number
  by_status: IssueStatusCount[]
  recent: Issue[]
}

export interface Issue {
  id: number
  room_id: number | null
  room_name: string | null
  main_category: MainCategory
  category: Category
  title: string
  description: string
  image_url: string | null
  reporter_id: number | null
  reporter_name: string | null
  reporter_room: string | null
  current_level: IssueLevel
  current_assignee_id: number | null
  current_assignee_role: string | null
  current_assignee_name: string | null
  status: IssueStatus
  priority: string
  is_anonymous: boolean
  // 🆕 ปลายทางที่ผู้แจ้งขอ (PIRI Boards) + board สาธารณะที่สภาอนุมัติแล้ว (ชี้ piri_boards.id)
  requested_destination?: RequestedDestination
  published_board_id?: number | null
  resolved_at: string | null
  created_at: string
  updated_at: string
  steps?: IssueStep[]
  countdown?: IssueCountdown | null
  escalations?: Escalation[]
  status_history?: StatusHistory[]
  comments?: IssueComment[]
}

// ===== Labels (ภาษาไทย) — ตรงกับ backend config/categories.json =====
export interface MainCategoryInfo {
  label: string
  subcategories: Record<string, string>
}

export const MAIN_CATEGORIES: Record<MainCategory, MainCategoryInfo> = {
  suggestion: {
    label: 'เสนอความคิดเห็น',
    subcategories: {
      academic: 'วิชาการ',
      reception: 'ปฏิคม',
      activity: 'กิจกรรม',
      discipline: 'วินัย',
      democracy: 'ประชาธิปไตย',
    },
  },
  wellbeing: {
    label: 'สุขภาวะทางกายและใจ',
    subcategories: {
      physical_health: 'สุขภาวะทางกาย',
      mental_health: 'สุขภาวะทางใจ',
    },
  },
  report: {
    label: 'แจ้งเหตุ',
    subcategories: {
      complaint: 'ร้องทุกข์',
      grievance: 'ร้องเรียน',
    },
  },
}

export const MAIN_CATEGORY_LABELS: Record<MainCategory, string> = {
  suggestion: 'เสนอความคิดเห็น',
  wellbeing: 'สุขภาวะทางกายและใจ',
  report: 'แจ้งเหตุ',
}

export function subcategoryLabel(main_category: MainCategory, category: string): string {
  return MAIN_CATEGORIES[main_category]?.subcategories[category] ?? category
}

// หมวดย่อยทั้ง 9 เป็น list แบน (value + label + หมวดหลัก) — ใช้เลือก "หน้าที่" (responsibilities)
// ที่หน้า User Management / กรองเรื่องตามหน้าที่ (เหมือน backend core.categories.all_subcategory_codes())
export interface CategoryOption {
  value: string
  label: string
  main: MainCategory
}

export const CATEGORY_OPTIONS: CategoryOption[] = (
  Object.keys(MAIN_CATEGORIES) as MainCategory[]
).flatMap((mc) =>
  Object.entries(MAIN_CATEGORIES[mc].subcategories).map(([value, label]) => ({
    value,
    label,
    main: mc,
  })),
)

// role ที่ถือ "หน้าที่" ได้ (ตรงกับ backend student_service.RESPONSIBLE_ROLES)
export const RESPONSIBLE_ROLES = ['council_member', 'level_vice_president']

export function categoryLabel(code: string): string {
  return CATEGORY_OPTIONS.find((c) => c.value === code)?.label ?? code
}

export function categoryMain(code: string): MainCategory | '' {
  return CATEGORY_OPTIONS.find((c) => c.value === code)?.main ?? ''
}

export const STATUS_LABELS: Record<string, string> = {
  pending: 'รอรับเรื่อง',
  in_progress: 'กำลังดำเนินการ',
  resolved: 'แก้ไขเสร็จ',
  escalated: 'ส่งต่อให้ระดับสูงขึ้น',
  cancelled: 'ถูกยกเลิก',
  rejected: 'ถูกปฏิเสธ',
}

export const LEVEL_LABELS: Record<IssueLevel, string> = {
  room: 'หัวหน้าห้อง / รองฝ่าย',
  level: 'ประธานระดับ',
  council: 'สภานักเรียน',
}

// ลำดับพีระมิด (room → level → council) — ใช้เทียบ rank ระดับสูงมองลงได้
export const LEVEL_ORDER: IssueLevel[] = ['room', 'level', 'council']

// บทบาท → ระดับในพีระมิด (mirror backend ROLE_LEVEL + school-wide roles)
// - ครูทั่วไป (teacher) ไม่ได้ map → ไม่มีระดับพีระมิด (จัดการแยกฝั่ง backend ตาม staff_level)
// - admin / ครูสภา / ประธานสภา / สภานักเรียน = ยอดพีระมิด (council)
export const ROLE_TO_LEVEL: Record<string, IssueLevel> = {
  class_president: 'room',
  vice_academic: 'room',
  vice_discipline: 'room',
  vice_activity: 'room',
  vice_reception: 'room',
  level_president: 'level',
  level_vice_president: 'level',
  council_member: 'council',
  council_president: 'council',
  teacher_council: 'council',
  admin: 'council',
}

// ระดับในพีระมิดของผู้ใช้ (สูงสุดจากทุก role) หรือ '' ถ้าไม่มีระดับ (เช่น นักเรียน/ครูทั่วไป)
export function userPyramidLevel(roles: { role: string | null }[]): IssueLevel | '' {
  let best: IssueLevel | '' = ''
  for (const r of roles) {
    if (!r.role) continue
    const lv = ROLE_TO_LEVEL[r.role]
    if (!lv) continue
    if (!best || LEVEL_ORDER.indexOf(lv) > LEVEL_ORDER.indexOf(best)) best = lv
  }
  return best
}

// รูปแบบที่ผู้แจ้งขอ (PIRI Boards) — ตรงกับ backend requested_destination
export const DESTINATION_LABELS: Record<RequestedDestination, string> = {
  normal: 'ดำเนินการปกติ',
  vote: 'โหวตสาธารณะ',
  talk: 'พูดคุยสาธารณะ',
}
