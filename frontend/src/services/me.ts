import api from './api'
import type { PersonalStats } from '@/types/me'

// 📊 Me API — api interceptor unwrap response.data แล้ว (ดู services/api.ts)
// ไม่ต้องมี permission พิเศษ — ตัวตนคือสิทธิ์ (user_id มาจาก JWT ฝั่ง backend เสมอ)
// ⚠️ ห้ามส่ง user_id ไปกับ request เด็ดขาด

/** สถิติส่วนตัว 6 ตัวเลข — กรองตามภาคปัจจุบัน (ถ้ายังไม่ตั้งภาค = นับทั้งหมด) */
export async function getMyStats(): Promise<PersonalStats> {
  return (await api.get('/api/me/stats')) as PersonalStats
}
