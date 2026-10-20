import api from './api'
import type {
  Issue,
  IssueComment,
  IssueListResponse,
  IssueStep,
  MyIssueSummary,
  OrphanedAssignments,
  RequestedDestination,
  UpdateIssuePayload,
} from '@/types/issue'
import type { PublicBoardType } from '@/types/board'

// Issue API

export interface CreateIssuePayload {
  main_category: string
  category: string
  title: string
  description: string
  is_anonymous: boolean
  room_id?: number | null
  start_level?: string
  requested_destination?: RequestedDestination
}

// Payload สำหรับอนุมัติเผยแพร่สาธารณะ (สภานักเรียน/แอดมิน) — ตรงกับ backend ApproveToPublicRequest
export interface ApproveToPublicPayload {
  board_type: PublicBoardType
  vote_choices?: string[]
  allow_comments?: boolean
}

export interface ApproveToPublicResult {
  board_id: number
  status: string
}

export type IssueSort = 'asc' | 'desc'

export async function listIssues(params: {
  mine?: boolean
  received?: boolean
  status?: string
  category?: string
  main_category?: string
  level?: string
  levels?: string
  q?: string
  sort?: IssueSort
  limit?: number
  offset?: number
}): Promise<IssueListResponse> {
  return (await api.get('/api/issues', { params })) as IssueListResponse
}

export async function getIssue(id: number): Promise<Issue> {
  return (await api.get(`/api/issues/${id}`)) as Issue
}

// 📊 สรุปเรื่องที่ฉันแจ้ง (หน้า Home/Welcome) — 1 request แทนการเรียก list หลายครั้ง
export async function getMyIssueSummary(): Promise<MyIssueSummary> {
  return (await api.get('/api/issues/summary')) as MyIssueSummary
}

export async function createIssue(payload: CreateIssuePayload): Promise<Issue> {
  return (await api.post('/api/issues', payload)) as Issue
}

export async function updateIssue(id: number, payload: UpdateIssuePayload): Promise<Issue> {
  return (await api.patch(`/api/issues/${id}`, payload)) as Issue
}

// 🔁 เปลี่ยนปลายทางของเรื่อง (หัวหน้าห้อง/สภา แก้แจ้งผิด) — normal/vote/talk
export async function changeDestination(
  id: number,
  requested_destination: RequestedDestination,
): Promise<Issue> {
  return (await api.patch(`/api/issues/${id}/destination`, { requested_destination })) as Issue
}

// 🏛️ สภานักเรียน/แอดมิน อนุมัติเรื่องขอเผยแพร่สาธารณะ → สร้าง PIRI Board + ปิดเรื่อง
export async function approveToPublic(
  id: number,
  payload: ApproveToPublicPayload,
): Promise<ApproveToPublicResult> {
  return (await api.post(`/api/issues/${id}/approve-to-public`, payload)) as ApproveToPublicResult
}

export async function acceptIssue(id: number, estimated_days: number): Promise<void> {
  await api.post(`/api/issues/${id}/accept`, { estimated_days })
}

export async function updateCountdown(id: number, estimated_days: number): Promise<void> {
  await api.patch(`/api/issues/${id}/countdown`, { estimated_days })
}

export async function addStep(
  id: number,
  step_title: string,
  step_detail?: string,
): Promise<IssueStep> {
  return (await api.post(`/api/issues/${id}/steps`, { step_title, step_detail })) as IssueStep
}

export async function completeStep(id: number, stepId: number): Promise<void> {
  await api.patch(`/api/issues/${id}/steps/${stepId}/complete`)
}

export async function escalateIssue(id: number, reason?: string): Promise<void> {
  await api.post(`/api/issues/${id}/escalate`, { reason })
}

export async function resolveIssue(id: number, note?: string): Promise<void> {
  await api.post(`/api/issues/${id}/resolve`, { reason: note })
}

export async function cancelIssue(id: number, reason?: string): Promise<void> {
  await api.post(`/api/issues/${id}/cancel`, { reason })
}

// ===== คอมเมนต์ (แบบ YouTube) =====
export async function createComment(issueId: number, body: string): Promise<IssueComment> {
  return (await api.post(`/api/issues/${issueId}/comments`, { body })) as IssueComment
}

export async function updateComment(
  issueId: number,
  commentId: number,
  body: string,
): Promise<IssueComment> {
  return (await api.patch(`/api/issues/${issueId}/comments/${commentId}`, { body })) as IssueComment
}

export async function deleteComment(issueId: number, commentId: number): Promise<void> {
  await api.delete(`/api/issues/${issueId}/comments/${commentId}`)
}

// ============================================================
// 🔁 P5 — เรื่องค้างที่ผู้รับหมดวาระ (หลังขึ้นปีใหม่)
// ============================================================
//
// ⚠️ สองเส้นทางนี้เป็นของ **ผู้ดูแลระดับโรงเรียนเท่านั้น** — backend ต้องผ่านทั้ง
//    `MANAGE_STUDENTS` และ `get_manage_mode() == 'school'` (ครูระดับชั้น/ประธานระดับ 403)
//    ⇒ หน้า `OrphanedAssignments.vue` ใช้ประตู route คู่เดียวกับหน้า "เลื่อนชั้นนักเรียน"

/** เรื่องที่ยังเปิดอยู่แต่ผู้รับไม่มีแถว active ในปีที่ระบุ (ไม่ระบุ = ปีปัจจุบัน) */
export async function listOrphanedAssignments(yearId?: number): Promise<OrphanedAssignments> {
  return (await api.get('/api/issues/orphaned-assignments', {
    params: yearId ? { year_id: yearId } : undefined,
  })) as OrphanedAssignments
}

/**
 * มอบหมายเรื่องค้างให้ผู้รับคนใหม่ — เขียน `issue_status_history` + แจ้งเตือน + audit
 *
 * ⚠️ ผู้รับใหม่ต้องมีแถว active ในปีปัจจุบัน (backend ตรวจ — หมดวาระแล้วได้ 400)
 * ⚠️ เรื่องที่ปิดแล้วมอบหมายต่อไม่ได้ (400)
 */
export async function reassignIssue(
  issueId: number,
  toUserId: number,
  note?: string,
): Promise<{ status: string; issue_id: number; to_user_id: number; role: string }> {
  return (await api.post(`/api/issues/${issueId}/reassign`, {
    to_user_id: toUserId,
    note: note || undefined,
  })) as { status: string; issue_id: number; to_user_id: number; role: string }
}
