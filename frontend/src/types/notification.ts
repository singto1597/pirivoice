// 🔔 ระบบแจ้งเตือน (Notifications) — badge ตามเมนู + หน้าแจ้งเตือนกลาง
// group_type ตรงกับ backend: badge "เรื่องของฉัน" / "เรื่องที่รับ" / PIRI Boards / จัดการรายงาน

export type NotificationGroup = 'issue_mine' | 'issue_received' | 'board' | 'report'

export interface NotificationItem {
  id: number
  group_type: NotificationGroup
  type: string // issue_new | issue_update | issue_comment | board_new | board_reply | board_hidden | report_new | report_actioned
  title: string
  body: string
  entity_type: string | null // issue | piri_board | piri_board_comment | piri_board_report
  entity_id: number | null
  board_id: number | null
  actor_id: number | null
  actor_name: string | null
  read_at: string | null // null = ยังไม่อ่าน
  created_at: string
}

export interface NotificationListResponse {
  items: NotificationItem[]
  total: number
  page: number
  page_size: number
  pages: number
}

export interface UnreadCounts {
  counts: Record<NotificationGroup, number>
  total: number
}

export interface MarkReadPayload {
  ids?: number[]
  group_type?: NotificationGroup
  entity_type?: string
  entity_id?: number
  board_id?: number
  read_all?: boolean
}

// Tab ของหน้าแจ้งเตือน — '' = ทั้งหมด
export const GROUP_TABS: Array<{ value: '' | NotificationGroup; label: string; icon: string }> = [
  { value: '', label: 'ทั้งหมด', icon: 'bi bi-list-ul' },
  { value: 'issue_mine', label: 'เรื่องของฉัน', icon: 'bi bi-file-earmark-text' },
  { value: 'issue_received', label: 'เรื่องที่รับ', icon: 'bi bi-inbox' },
  { value: 'board', label: 'PIRI Boards', icon: 'bi bi-columns-gap' },
  { value: 'report', label: 'จัดการรายงาน', icon: 'bi bi-flag-fill' },
]

// ⚙️ ตั้งค่าการแจ้งเตือนรายกลุ่ม
export interface NotificationPreference {
  group_type: NotificationGroup
  enabled: boolean
}

export interface NotificationPreferencesResponse {
  preferences: NotificationPreference[]
}

// กลุ่มที่ผู้ใช้ตั้งค่าได้ = GROUP_TABS ตัด '' (แท็บ "ทั้งหมด" ซึ่งไม่ใช่กลุ่มจริง) ออก
// ⚠️ ห้ามประกาศชื่อ/ไอคอนกลุ่มซ้ำที่ใหม่ — ยืมจาก GROUP_TABS ข้างบนเสมอ
//    เพิ่มกลุ่มใหม่ที่ backend แล้ว UI จะได้แถวใหม่เองโดยไม่ต้องแก้ไฟล์นี้
export const PREFERENCE_GROUPS = GROUP_TABS.filter(
  (t): t is { value: NotificationGroup; label: string; icon: string } => t.value !== '',
)

// คำอธิบายว่าแต่ละกลุ่มคืออะไร — จำเป็น เพราะชื่อกลุ่มสั้น ๆ ทำให้ผู้ใช้ไม่กล้ากดปิด
export const GROUP_DESCRIPTIONS: Record<NotificationGroup, string> = {
  issue_mine: 'เมื่อเรื่องที่คุณแจ้งไว้ถูกตอบกลับ หรือสถานะเปลี่ยน',
  issue_received: 'เมื่อมีเรื่องส่งมาถึงคุณในฐานะผู้รับผิดชอบ',
  board: 'เมื่อมีกระทู้ใหม่ ความคิดเห็นใหม่ หรือผลโหว้ใน PIRI Boards',
  report: 'เมื่อมีคนรายงานเนื้อหา และเมื่อผลการตรวจสอบออก',
}

// ไอคอน per type (ใช้หน้าแจ้งเตือน)
export const NOTIFICATION_TYPE_ICONS: Record<string, string> = {
  issue_new: 'bi bi-inbox',
  issue_update: 'bi bi-arrow-repeat',
  issue_comment: 'bi bi-chat-dots',
  board_new: 'bi bi-columns-gap',
  board_reply: 'bi bi-reply',
  board_hidden: 'bi bi-eye-slash',
  report_new: 'bi bi-flag-fill',
  report_actioned: 'bi bi-check2-circle',
}
