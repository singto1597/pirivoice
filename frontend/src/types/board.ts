// PIRI Boards (PIRI Vote + PIRI Talk + ข้อเสนอแนะ) — data models
// ตรงกับ backend models/board_schemas.py

// 'suggestion' (E1) — ผู้ใช้เสนอไอเดียเอง ขึ้นบอร์ดทันทีโดยไม่ผ่านด่านอนุมัติของสภา
// ⚠️ ค่าทุกตัวต้องอยู่ใน `chk_piri_boards_type` ฝั่ง DB (migration 022) ไม่งั้น INSERT จะล้ม
export type BoardType = 'vote' | 'talk' | 'suggestion'

// ชนิด board ที่ **สายอนุมัติของสภา** สร้างได้ (`approve_to_public`)
// ⚠️ ไม่รวม 'suggestion' โดยเจตนา — ตรงกับ `PUBLIC_BOARD_TYPES` ฝั่ง backend
//    ข้อเสนอจากผู้ใช้ไม่ได้มาจาก issue และไม่มีผู้อนุมัติ ⇒ ใช้ `BoardType` แทนไม่ได้
//    (ถ้าเผลอใช้ BoardType ที่นี่ modal อนุมัติจะส่ง 'suggestion' ไปให้ endpoint ที่ไม่รับ)
export type PublicBoardType = 'vote' | 'talk'

// ตัวเลือกโหวต 1 อัน (มี vote_count เพื่อคำนวณ % บน frontend)
export interface VoteChoice {
  id: number
  choice_text: string
  description: string | null
  image_url: string | null
  sort_order: number
  vote_count: number
}

// คอมเมนต์ใน board — แบบ threaded (replies ซ้อนกัน; ความลึกถูกจำกัดฝั่ง service)
export interface BoardComment {
  id: number
  parent_comment_id: number | null
  user_id: number | null
  commenter_name: string | null
  commenter_first_name?: string | null // ชื่อจริง (avatar ใช้ตัวแรกของชื่อ) — fallback commenter_name
  body: string
  is_edited: boolean
  created_at: string
  updated_at: string | null
  replies: BoardComment[]
}

// การ์ด board ใน feed — ไม่มี pyramid visibility (ข้อมูลสาธารณะ)
export interface BoardSummary {
  id: number
  board_type: BoardType
  title: string
  description: string
  cover_image_url: string | null
  source_issue_id: number | null
  author_id: number | null
  author_name: string | null // null ถ้า board anonymous
  is_anonymous: boolean
  comment_count: number
  view_count: number
  status: string
  tags: string[]
  total_votes: number // เฉพาะ vote board (รวมทุก choice)
  created_at: string
}

// รายละเอียด board — vote: choices + my_vote; talk: comments (threaded)
export interface BoardDetail extends BoardSummary {
  allow_comments: boolean
  my_vote_choice_id: number | null // board ที่ user โหวตแล้ว (ชี้ choice_id) — ใช้ highlight ปุ่ม
  choices: VoteChoice[]
  comments: BoardComment[]
}

// feed แบบแบ่งหน้า (pattern เดียวกับ /issues)
export interface BoardListResponse {
  items: BoardSummary[]
  total: number
  page: number
  page_size: number
  pages: number
}

// ผลการโหวต (POST vote response)
export interface VoteResult {
  status: string
  vote_id: number
  board_id: number
  choice_id: number
  choice_text: string
}

export const BOARD_TYPE_LABELS: Record<BoardType, string> = {
  vote: 'โหวต',
  talk: 'พูดคุย',
  suggestion: 'ข้อเสนอแนะ',
}

export function boardTypeIcon(t: BoardType): string {
  if (t === 'vote') return 'bi bi-bar-chart-fill'
  // ข้อเสนอแนะใช้เลย์เอาต์คอมเมนต์เหมือน talk แต่คนละไอคอน ให้แยกออกด้วยตาได้ในฟีด
  if (t === 'suggestion') return 'bi bi-lightbulb-fill'
  return 'bi bi-chat-dots-fill'
}

// ข้อเสนอแนะเสนอไอเดียได้ — ไม่ใช่บอร์ดโหวต (ตรงกับ VOTABLE_BOARD_TYPES ฝั่ง backend)
export function isVotableBoard(t: BoardType): boolean {
  return t === 'vote'
}

// ป้ายหัวบอร์ดในหน้ารายละเอียด — 'บอร์ดโหวต'/'บอร์ดพูดคุย'/'ข้อเสนอแนะ'
// (คำว่า "บอร์ดข้อเสนอแนะ" อ่านผิดธรรมชาติไทย จึงตัด "บอร์ด" ออกเฉพาะชนิดนี้)
export function boardTypeHeading(t: BoardType): string {
  return t === 'suggestion' ? 'ข้อเสนอแนะ' : `บอร์ด${BOARD_TYPE_LABELS[t]}`
}

// ข้อความ fallback เมื่อไม่รู้ชื่อผู้สร้าง — บอร์ดของสภาสร้างโดยสภา แต่ข้อเสนอสร้างโดยผู้ใช้ทั่วไป
export function boardAuthorFallback(t: BoardType): string {
  return t === 'suggestion' ? 'ผู้ใช้' : 'สภานักเรียน'
}

// ===== Report (แจ้งความไม่เหมาะสม) — ตรงกับ backend piri_board_reports =====
export type ReportReason = 'bullying' | 'profanity' | 'spam' | 'privacy' | 'other'
export type ReportStatus = 'open' | 'resolved' | 'dismissed'

// รายงาน 1 รายการในคิวโมเดอเรชัน (สภา/แอดมิน)
export interface ReportItem {
  id: number
  board_id: number
  board_title: string
  comment_id: number
  comment_body: string
  reporter_id: number | null
  reporter_name: string | null
  reason: ReportReason
  detail: string | null
  status: ReportStatus
  resolved_by: number | null
  resolved_at: string | null
  resolution_note: string | null
  created_at: string
}

export interface ReportListResponse {
  items: ReportItem[]
  total: number
  page: number
  page_size: number
  pages: number
}

export const REPORT_REASONS: ReportReason[] = ['bullying', 'profanity', 'spam', 'privacy', 'other']

export const REPORT_REASON_LABELS: Record<ReportReason, string> = {
  bullying: 'กลั่นแกล้ง/คุกคาม',
  profanity: 'คำหยาบคาย',
  spam: 'สแปม/โฆษณา',
  privacy: 'เปิดเผยข้อมูลส่วนตัว',
  other: 'อื่นๆ',
}

export const REPORT_STATUS_LABELS: Record<ReportStatus, string> = {
  open: 'รอจัดการ',
  resolved: 'ซ่อนแล้ว',
  dismissed: 'ปัดตก',
}
