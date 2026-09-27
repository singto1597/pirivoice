// ประเภทข้อมูลประกาศ (Announcement) — หน้า Landing Page + หน้าจัดการ
//
// 🎯 ที่นี่เป็น "แหล่งความจริงเดียว" ของ AnnouncementPriority
//    (services/public.ts import ไปใช้ต่อ — ห้ามประกาศซ้ำที่อื่น ไม่งั้นเพิ่มระดับใหม่แล้วจะลืมที่ใดที่หนึ่ง)

export type AnnouncementPriority = 'normal' | 'high' | 'urgent'

/** สถานะที่กรองในหน้ารายการฝั่งผู้ดูแล (ตรงกับ backend _STATUS_CONDITIONS) */
export type AnnouncementStatus = 'active' | 'deleted' | 'all'

/** ประกาศสำหรับหน้า public (Landing) — ดู public_schemas.py (ห้ามมีข้อมูลผู้ประกาศ) */
export interface PublicAnnouncement {
  id: number
  message: string
  priority: AnnouncementPriority
  link?: string | null
}

/** ประกาศสำหรับหน้า admin — มีข้อมูลผู้ประกาศ/ผู้แก้ + เวลาที่ลบ (จาก announcement_schemas.py) */
export interface Announcement {
  id: number
  message: string
  priority: AnnouncementPriority
  link: string | null
  created_at: string
  updated_at: string | null
  deleted_at: string | null
  // 🔎 created_by/updated_by เป็น id เปล่า ไม่มี FK ฝั่ง DB ⇒ ชื่ออาจเป็น null ได้
  //    (ประกาศที่ seed ไว้ก่อนมีฟีเจอร์นี้ หรือผู้ใช้ถูกลบไปแล้ว)
  created_by: number | null
  updated_by: number | null
  created_by_name: string | null
  updated_by_name: string | null
}

export interface AnnouncementCreate {
  message: string
  priority: AnnouncementPriority
  link?: string | null
}

/** PATCH — ส่งเฉพาะฟิลด์ที่จะแก้ (ไม่ส่ง = ไม่แตะ) ; ส่ง null = สั่งล้างค่า */
export interface AnnouncementUpdate {
  message?: string
  priority?: AnnouncementPriority
  link?: string | null
}

export interface AnnouncementListResponse {
  items: Announcement[]
  total: number
  page: number
  page_size: number
  pages: number
}

export interface AnnouncementListParams {
  status?: AnnouncementStatus
  limit?: number
  offset?: number
}
