import api from './api'
import type {
  BulkMoveResult,
  ImportJob,
  Room,
  Student,
  StudentCreatePayload,
  StudentHistory,
  StudentStatus,
} from '@/types/student'

// Student API

export async function listRooms(): Promise<Room[]> {
  return (await api.get('/api/rooms')) as Room[]
}

export async function listStudents(params?: {
  room_id?: number
  search?: string
  role?: string
  /** ไม่ระบุ = ปีปัจจุบัน (backend กรองปีให้ — ดู `list_students`) */
  year_id?: number
}): Promise<Student[]> {
  return (await api.get('/api/students', { params })) as Student[]
}

// เพิ่มผู้ใช้งานแบบ Manual (หน้า User Management — "เพิ่มผู้ใช้งาน")
export async function addStudent(payload: StudentCreatePayload): Promise<{ student_id: number }> {
  return (await api.post('/api/students', payload)) as { student_id: number }
}

// ===================== Import นักเรียนจาก Excel (Queue) =====================
// Flow: upload (PENDING) → start (QUEUED → worker ประมวลผล) → poll progress

export async function uploadStudentExcel(file: File, defaultPassword = '1234'): Promise<ImportJob> {
  // 1. สร้างกล่อง Form สำหรับใส่ไฟล์เท่านั้น
  const form = new FormData()
  form.append('file', file)

  // 2. ยิง API โดยแยกของ 2 อย่างให้ถูกต้องตามที่ Backend ต้องการ
  return (await api.post('/api/upload-student-excel', form, {
    // แนบไฟล์ไปใน Body พร้อมบังคับ Header
    headers: {
      'Content-Type': 'multipart/form-data',
    },
    // แนบ default_password ไปใน URL Query
    params: {
      default_password: defaultPassword,
    },
  })) as ImportJob
}

export async function startImportJob(jobId: number): Promise<ImportJob> {
  return (await api.post(`/api/start-import-job/${jobId}`)) as ImportJob
}

export async function listImportJobs(): Promise<ImportJob[]> {
  return (await api.get('/api/import-jobs')) as ImportJob[]
}

export async function downloadImportTemplate(): Promise<Blob> {
  // responseType:'blob' สำคัญ — ไฟล์ .xlsx เป็น binary ถ้าไม่ตั้งจะกลายเป็น text ที่เสียหาย
  return (await api.get('/api/import-student-template', { responseType: 'blob' })) as Blob
}

export async function updateStudent(
  studentId: number,
  data: {
    class_role?: string
    status?: StudentStatus
    is_admin?: boolean
    staff_level?: string | null
    responsibilities?: string[]
    // P5 — ข้อมูลตัวตน (แก้ข้อมูลที่กรอกผิด) · ⚠️ `student_id` ไม่แก้ `users.username`
    prefix?: string | null
    first_name?: string | null
    last_name?: string | null
    nickname?: string | null
    student_no?: number
    student_id?: string
  },
): Promise<void> {
  await api.patch(`/api/students/${studentId}`, data)
}

// ============================================================
// 🔀 P5 — ย้ายห้องเป็นกลุ่ม + ประวัติรายคน
// ============================================================

/**
 * ย้ายนักเรียนหลายคนเข้าห้องเดียว **ภายในปีปัจจุบัน**
 *
 * ⚠️ `student_ids` = `students.id` ของแถวสมาชิก (ไม่ใช่ `users.id`) — backend ปฏิเสธ
 *    แถวของปีอื่นด้วย 400 เพราะการย้ายข้ามปีคือ "เลื่อนชั้น/ย้อนหลัง" ไม่ใช่ "ย้ายห้อง"
 * ⚠️ ต้องมี `MANAGE_STUDENTS` และอยู่ในระดับชั้นของทั้งห้องต้นทางและปลายทาง
 */
export async function bulkMoveStudents(payload: {
  student_ids: number[]
  to_room_code: string
  note?: string
}): Promise<BulkMoveResult> {
  return (await api.post('/api/students/bulk-move', payload)) as BulkMoveResult
}

/** ประวัติรายคน — แถวทุกปี (ห้อง/ตำแหน่ง/สถานะ) + การย้ายในปี */
export async function getStudentHistory(studentRowId: number): Promise<StudentHistory> {
  return (await api.get(`/api/students/${studentRowId}/history`)) as StudentHistory
}
