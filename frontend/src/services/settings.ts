import api from './api'
import type {
  AcademicTerm,
  AcademicTermListResponse,
  AcademicTermCreatePayload,
  AcademicTermUpdatePayload,
} from '@/types/academicTerm'

// 📅 Settings API — api interceptor unwrap response.data แล้ว (ดู services/api.ts)
// ทุก endpoint ต้องมีสิทธิ์ MANAGE_SETTINGS (รวม GET) — ไม่มีสิทธิ์ = 403

// status: 'current' | 'active' | 'deleted' | 'all'
export async function listTerms(params: {
  status?: string
  limit?: number
  offset?: number
} = {}): Promise<AcademicTermListResponse> {
  return (await api.get('/api/settings/terms', {
    params: {
      status: params.status || undefined,
      limit: params.limit ?? 50,
      offset: params.offset ?? 0,
    },
  })) as AcademicTermListResponse
}

export async function createTerm(payload: AcademicTermCreatePayload): Promise<AcademicTerm> {
  return (await api.post('/api/settings/terms', payload)) as AcademicTerm
}

// PATCH — ส่งเฉพาะฟิลด์ที่จะแก้ (ห้ามส่ง is_current — ใช้ setCurrentTerm)
export async function updateTerm(
  termId: number,
  payload: AcademicTermUpdatePayload,
): Promise<AcademicTerm> {
  return (await api.patch(`/api/settings/terms/${termId}`, payload)) as AcademicTerm
}

// ตั้งเป็นภาคปัจจุบัน — backend ปลดตัวเก่าให้เองในทรานแซกชันเดียว
export async function setCurrentTerm(termId: number): Promise<AcademicTerm> {
  return (await api.post(`/api/settings/terms/${termId}/set-current`)) as AcademicTerm
}

// ลบ = soft delete · ถ้าเป็นภาคปัจจุบันอยู่ จะหลุดจากตำแหน่งนั้นด้วย
export async function deleteTerm(termId: number): Promise<AcademicTerm> {
  return (await api.delete(`/api/settings/terms/${termId}`)) as AcademicTerm
}

// กู้คืน — กลับมาเป็นภาคธรรมดา (ต้องกดตั้งเป็นปัจจุบันเองอีกครั้ง)
export async function restoreTerm(termId: number): Promise<AcademicTerm> {
  return (await api.post(`/api/settings/terms/${termId}/restore`)) as AcademicTerm
}
