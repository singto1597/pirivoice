import api from './api'
import type { AppVersion } from '@/types/version'

// 🔢 Version API — ใช้แสดงว่า backend ที่กำลังตอบอยู่เป็น build ไหน
// ⚠️ baseURL ของ api instance ไม่มี `/api` นำหน้า → ต้องใส่เองใน path

export async function getVersion(): Promise<AppVersion> {
  return (await api.get('/api/version')) as AppVersion
}
