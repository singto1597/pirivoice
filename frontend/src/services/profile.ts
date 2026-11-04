import api from './api';

// 👤 My Profile API

export interface MyProfile {
  id: number;
  student_id: string;
  student_no: number | null;   // ครู/แอดมิน ไม่มีเลขที่ → null
  prefix: string | null;
  first_name: string | null;
  last_name: string | null;
  nickname: string | null;
  class_role: string;
  staff_level: string | null;  // (ครูทั่วไป) ระดับชั้นที่รับผิดชอบ เช่น ม.4
  status: string;
  room_id: number | null;      // admin/ครูสภา (school-wide) → null
  room_code: string | null;
  room_name: string | null;
  level: string | null;
  username: string;
  full_name: string | null;
  phone_number: string | null;
  email: string | null;
}

/**
 * @param options.fresh — ข้าม cache (หน้าแก้ไขโปรไฟล์ต้องได้ค่าล่าสุดก่อนคัดลอกลงฟอร์ม)
 *   หน้าดูโปรไฟล์ใช้ cache ได้
 */
export async function getMyProfile(options: { fresh?: boolean } = {}): Promise<MyProfile> {
  return (await api.get('/api/students/me/profile', { noCache: options.fresh })) as MyProfile;
}

export async function updateMyProfile(data: Partial<MyProfile>): Promise<MyProfile> {
  return (await api.patch('/api/students/me/profile', data)) as MyProfile;
}

export async function changePassword(old_password: string, new_password: string): Promise<void> {
  await api.post('/api/auth/change-password', { old_password, new_password });
}
