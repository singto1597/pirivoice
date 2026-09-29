import api from './api'
import type { ActivityResponse, ActivityType, PersonalStats } from '@/types/me'

// 📊 Me API — api interceptor unwrap response.data แล้ว (ดู services/api.ts)
// ไม่ต้องมี permission พิเศษ — ตัวตนคือสิทธิ์ (user_id มาจาก JWT ฝั่ง backend เสมอ)
// ⚠️ ห้ามส่ง user_id ไปกับ request เด็ดขาด

/** สถิติส่วนตัว 6 ตัวเลข — กรองตามภาคปัจจุบัน (ถ้ายังไม่ตั้งภาค = นับทั้งหมด) */
export async function getMyStats(): Promise<PersonalStats> {
  return (await api.get('/api/me/stats')) as PersonalStats
}

/**
 * กิจกรรมของฉัน (C1) — timeline ทุกอย่างที่เคยทำ **ไม่กรองตามภาค** (ต่างจากสถิติโดยเจตนา)
 * `counts` ที่ได้กลับมาเป็นยอดทั้งชุดเสมอ (ไม่สนใจ `activity_type`) ⇒ ใช้ทำป้ายตัวกรองได้
 */
export async function getMyActivity(
  params: { activity_type?: ActivityType; limit?: number; offset?: number } = {},
): Promise<ActivityResponse> {
  return (await api.get('/api/me/activity', { params })) as ActivityResponse
}
