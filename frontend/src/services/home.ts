import api from './api'
import type { HomeSummary } from '@/types/home'

// Home (B1) — ก้อนเดียวจบของหน้าแรก
//
// ⚠️ ไม่ส่ง `user_id` ไปกับ request เด็ดขาด — backend เอาจาก JWT เท่านั้น
//    (การส่งไปคือช่องให้ดูข้อมูลคนอื่น และ backend ตั้งใจไม่รับอยู่แล้ว)

export async function getHomeSummary(): Promise<HomeSummary> {
  return (await api.get('/api/home/summary')) as HomeSummary
}
