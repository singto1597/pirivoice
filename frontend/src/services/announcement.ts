import api from './api'
import type {
  Announcement,
  AnnouncementCreate,
  AnnouncementListParams,
  AnnouncementListResponse,
  AnnouncementUpdate,
} from '@/types/announcement'

// Announcement API — จัดการประกาศหน้า Landing Page (ต้องมีสิทธิ์ MANAGE_ANNOUNCEMENTS)
// ฝั่ง public (ไม่ล็อกอิน) ใช้ listPublicAnnouncements() ใน ./public แทน — คนละ endpoint กัน

export async function listAnnouncements(
  params: AnnouncementListParams = {},
): Promise<AnnouncementListResponse> {
  const { status, limit, offset } = params
  const res = (await api.get('/api/announcements', {
    params: {
      // ส่ง status เฉพาะเมื่อระบุ — ให้ backend ใช้ค่า default 'active' ของตัวเอง
      status: status || undefined,
      limit: limit ?? 20,
      offset: offset ?? 0,
    },
  })) as AnnouncementListResponse
  return res
}

export async function createAnnouncement(payload: AnnouncementCreate): Promise<Announcement> {
  return (await api.post('/api/announcements', payload)) as Announcement
}

export async function updateAnnouncement(
  id: number,
  payload: AnnouncementUpdate,
): Promise<Announcement> {
  return (await api.patch(`/api/announcements/${id}`, payload)) as Announcement
}

/** ลบประกาศ (soft delete) — หายจาก Landing Page แต่กู้คืนได้ */
export async function deleteAnnouncement(id: number): Promise<Announcement> {
  return (await api.delete(`/api/announcements/${id}`)) as Announcement
}

export async function restoreAnnouncement(id: number): Promise<Announcement> {
  return (await api.post(`/api/announcements/${id}/restore`)) as Announcement
}

/**
 * ปลดระวาง — เอาออกจาก Landing Page แต่ **ไม่ใช่การลบ** ยังเก็บไว้เป็นประวัติ
 * (ต่างจาก deleteAnnouncement: ตั้งใจเอาออกเพราะหมดอายุ ไม่ปนกับของที่เผลอลบ)
 */
export async function retireAnnouncement(id: number): Promise<Announcement> {
  return (await api.post(`/api/announcements/${id}/retire`)) as Announcement
}

/** นำประกาศที่ปลดระวางกลับมาใช้ — กลับไปแสดงบน Landing Page อีกครั้ง */
export async function unretireAnnouncement(id: number): Promise<Announcement> {
  return (await api.post(`/api/announcements/${id}/unretire`)) as Announcement
}
