import api from './api'
import type {
  BoardComment,
  BoardDetail,
  BoardListResponse,
  BoardType,
  ReportItem,
  ReportListResponse,
  ReportReason,
  VoteResult,
} from '@/types/board'

// PIRI Boards API (feed โหวต/พูดคุยสาธารณะ) — view ห้ามเรียก api.* ตรง ๆ ต้องผ่าน services นี้

export async function listBoards(params: {
  board_type?: BoardType
  q?: string
  limit?: number
  offset?: number
}): Promise<BoardListResponse> {
  return (await api.get('/api/boards', { params })) as BoardListResponse
}

export async function getBoard(id: number): Promise<BoardDetail> {
  return (await api.get(`/api/boards/${id}`)) as BoardDetail
}

// ===== E1: เสนอไอเดีย (ผู้ใช้ทั่วไป — ขึ้นบอร์ดทันที ไม่ผ่านด่านสภา) =====
export interface SuggestionPayload {
  title: string
  description: string
  is_anonymous?: boolean
}

// ผลที่ได้ — **ไม่ใช่ BoardDetail** โดยเจตนา: backend ไม่คืนรายละเอียดเต็มเพราะ
// `GET /boards/{id}` มีผลข้างเคียงคือ view_count += 1 (ผู้สร้างไม่ควรนับวิวให้ตัวเอง)
export interface SuggestionCreated {
  id: number
  board_type: BoardType
  title: string
  created_at: string
}

export async function createSuggestion(payload: SuggestionPayload): Promise<SuggestionCreated> {
  // ⚠️ ส่งแค่ 3 ฟิลด์นี้ — `board_type`/`user_id` ถูกตัดทิ้งฝั่ง backend อยู่แล้ว
  //    (endpoint สร้างได้ชนิดเดียว และเจ้าของคือผู้ถือ token)
  return (await api.post('/api/boards/suggestions', {
    title: payload.title,
    description: payload.description,
    is_anonymous: payload.is_anonymous ?? false,
  })) as SuggestionCreated
}

export async function submitVote(boardId: number, choice_id: number): Promise<VoteResult> {
  return (await api.post(`/api/boards/${boardId}/vote`, { choice_id })) as VoteResult
}

export async function addComment(
  boardId: number,
  body: string,
  parent_id?: number | null,
): Promise<BoardComment> {
  return (await api.post(`/api/boards/${boardId}/comments`, {
    body,
    parent_id: parent_id ?? null,
  })) as BoardComment
}

// ===== Report (แจ้งความไม่เหมาะสม — ทุกคน) =====
export interface ReportPayload {
  reason: ReportReason
  detail?: string
}

export async function reportComment(
  boardId: number,
  commentId: number,
  payload: ReportPayload,
): Promise<{ id: number; status: string }> {
  return (await api.post(
    `/api/boards/${boardId}/comments/${commentId}/report`,
    payload,
  )) as { id: number; status: string }
}

// ===== Moderation (สภา/แอดมิน) =====
export async function hideComment(
  boardId: number,
  commentId: number,
  reason: string,
): Promise<{ status: string; hidden_count: number }> {
  return (await api.post(`/api/boards/${boardId}/comments/${commentId}/hide`, { reason })) as {
    status: string
    hidden_count: number
  }
}

export async function unhideComment(
  boardId: number,
  commentId: number,
): Promise<{ status: string }> {
  return (await api.post(`/api/boards/${boardId}/comments/${commentId}/unhide`)) as {
    status: string
  }
}

export async function hideBoard(
  boardId: number,
  reason: string,
): Promise<{ status: string; board_id: number }> {
  return (await api.post(`/api/boards/${boardId}/hide`, { reason })) as {
    status: string
    board_id: number
  }
}

export async function unhideBoard(boardId: number): Promise<{ status: string; board_id: number }> {
  return (await api.post(`/api/boards/${boardId}/unhide`)) as { status: string; board_id: number }
}

// ===== คิวรายงาน (สภา/แอดมิน) =====
export async function listReports(params: {
  status?: ReportItem['status']
  reason?: ReportReason
  q?: string
  limit?: number
  offset?: number
}): Promise<ReportListResponse> {
  return (await api.get('/api/boards/reports', { params })) as ReportListResponse
}

export async function resolveReport(
  reportId: number,
  action: 'hide' | 'dismiss',
  note?: string,
): Promise<{ report_id: number; status: string; hidden_count?: number }> {
  return (await api.post(`/api/boards/reports/${reportId}/resolve`, {
    action,
    note: note || undefined,
  })) as { report_id: number; status: string; hidden_count?: number }
}
