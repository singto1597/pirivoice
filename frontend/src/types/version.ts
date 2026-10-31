/** คำตอบของ `GET /api/version` — build ที่ backend กำลังรันอยู่ */
export interface AppVersion {
  version: string
  commit: string
}
