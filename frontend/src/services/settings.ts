import api from './api'
import type {
  AcademicTerm,
  AcademicTermListResponse,
  AcademicTermCreatePayload,
  AcademicTermUpdatePayload,
} from '@/types/academicTerm'
import type { QuietHours, QuietHoursPayload } from '@/types/quietHours'

// 📅 Settings API — api interceptor unwrap response.data แล้ว (ดู services/api.ts)
//
// ⚠️ **สิทธิ์ไม่เหมือนกันทั้งไฟล์ — อย่าเหมารวม:**
//    · `/terms` (ทั้งไฟล์นี้ส่วนล่าง) — ทุก endpoint **รวม GET** ต้องมี MANAGE_SETTINGS → ไม่มีสิทธิ์ = 403
//    · `/quiet-hours` — **GET เปิดให้ผู้ใช้ที่ล็อกอินทุกคน** (ไว้ให้นักเรียนดูว่าทำไมมือถือเงียบ)
//      เฉพาะ PUT ที่ต้องมี MANAGE_SETTINGS ⇒ เรียก getQuietHours() ได้จากทุกหน้าจอ

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

// ============================================================
// 🔇 Quiet Hours (A8)
// ============================================================

// อ่านค่าปัจจุบัน — **ไม่ต้องมี MANAGE_SETTINGS** (ผู้ใช้ที่ล็อกอินทุกคนเรียกได้)
export async function getQuietHours(): Promise<QuietHours> {
  return (await api.get('/api/settings/quiet-hours')) as QuietHours
}

// ตั้งค่า — ต้องมี MANAGE_SETTINGS · PUT = full replace ⇒ ส่งครบ 3 ฟิลด์เสมอ
// ⚠️ รูปแบบเวลาผิด หรือ `enabled: true` พร้อม `start === end` ⇒ backend ตอบ **400**
//    (ไม่ใช่ 422) พร้อมข้อความไทย ⇒ api.ts ส่ง `detail` มาเป็น string ให้โชว์ได้ตรง ๆ
export async function updateQuietHours(payload: QuietHoursPayload): Promise<QuietHours> {
  return (await api.put('/api/settings/quiet-hours', payload)) as QuietHours
}
