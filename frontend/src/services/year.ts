import api from './api'
import type {
  AcademicYear,
  AcademicYearListResponse,
  AcademicYearCreatePayload,
  AcademicYearUpdatePayload,
} from '@/types/academicYear'

// 🎓 ปีการศึกษา API — api interceptor unwrap response.data แล้ว (ดู services/api.ts)
//
// ⚠️ **ทุก endpoint (รวม GET) ต้องมี `MANAGE_SETTINGS`** — เหมือน `/api/settings/terms`
//    และ **ต่างจาก** `/quiet-hours` ที่ GET เปิดให้ทุกคน
// ⚠️ เป็น **คนละโดเมน** กับ `/api/settings/terms` (ภาคเรียน) — ดูเหตุผลที่ types/academicYear.ts

// status: 'current' | 'active' | 'deleted' | 'all'
export async function listYears(params: {
  status?: string
  limit?: number
  offset?: number
} = {}): Promise<AcademicYearListResponse> {
  return (await api.get('/api/settings/years', {
    params: {
      status: params.status || undefined,
      limit: params.limit ?? 50,
      offset: params.offset ?? 0,
    },
  })) as AcademicYearListResponse
}

// ปีเดี่ยว — ให้ **หน้าแก้ไขแบบเต็มหน้า** โหลดเองจาก URL (`/settings/years/:id/edit`)
// ⚠️ คืนปีที่ถูกลบด้วย — ต้องเช็ค `deleted_at` เองก่อนเปิดฟอร์ม (ดู deleteBlockReason)
export async function getYear(yearId: number): Promise<AcademicYear> {
  return (await api.get(`/api/settings/years/${yearId}`)) as AcademicYear
}

// ⚠️ `is_current: true` จะได้ **400** ถ้าปียังไม่มีสมาชิกและปีอื่นยังมีคนอยู่
//    (ด่านกัน "รายชื่อทั้งโรงเรียนหายในคลิกเดียว") — ข้อความไทยมาจาก backend ตรง ๆ
export async function createYear(payload: AcademicYearCreatePayload): Promise<AcademicYear> {
  return (await api.post('/api/settings/years', payload)) as AcademicYear
}

// PATCH — ส่งเฉพาะฟิลด์ที่จะแก้ (ห้ามส่ง is_current — ใช้ setCurrentYear)
export async function updateYear(
  yearId: number,
  payload: AcademicYearUpdatePayload,
): Promise<AcademicYear> {
  return (await api.patch(`/api/settings/years/${yearId}`, payload)) as AcademicYear
}

// ตั้งเป็นปีปัจจุบัน — backend ปลดปีเดิมให้เองในทรานแซกชันเดียว **และเปลี่ยน DEFAULT
// ของ students.academic_year_id** ⇒ สมาชิกที่สร้างหลังจากนี้ไปอยู่ปีใหม่
export async function setCurrentYear(yearId: number): Promise<AcademicYear> {
  return (await api.post(`/api/settings/years/${yearId}/set-current`)) as AcademicYear
}

// ลบ = soft delete · ⚠️ ลบปีปัจจุบันไม่ได้ และลบปีที่ยังมีสมาชิกไม่ได้ (400 + ข้อความไทย)
export async function deleteYear(yearId: number): Promise<AcademicYear> {
  return (await api.delete(`/api/settings/years/${yearId}`)) as AcademicYear
}

// กู้คืน — กลับมาเป็นปีธรรมดา (ต้องกดตั้งเป็นปัจจุบันเองอีกครั้ง)
// ⚠️ ถ้ามีปี พ.ศ. เดียวกันถูกสร้างใหม่ระหว่างนั้น → 400 พร้อมบอกทางออก
export async function restoreYear(yearId: number): Promise<AcademicYear> {
  return (await api.post(`/api/settings/years/${yearId}/restore`)) as AcademicYear
}
