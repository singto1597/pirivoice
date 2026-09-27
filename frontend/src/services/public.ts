import api from './api'
import type { PublicAnnouncement } from '@/types/announcement'

// Public API (prefix /api/v1) — ประกาศโรงเรียน หน้า Home/Welcome
// (Landing เรียกตรงผ่าน api instance — เก็บไว้ที่ service ให้ authed views ใช้ตามกฎ)

// ⚠️ นิยามไว้ที่ types/announcement.ts ที่เดียว — re-export ให้โค้ดเดิม import ที่นี่ได้เหมือนเดิม
//    (ห้ามประกาศซ้ำ ไม่งั้นเพิ่มระดับใหม่แล้วจะลืมแก้ที่ใดที่หนึ่ง)
export type { PublicAnnouncement as Announcement, AnnouncementPriority } from '@/types/announcement'

export async function listPublicAnnouncements(): Promise<PublicAnnouncement[]> {
  return (await api.get('/api/v1/public/announcements')) as PublicAnnouncement[]
}
