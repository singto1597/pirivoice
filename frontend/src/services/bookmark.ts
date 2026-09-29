import api from './api'
import type {
  Bookmark,
  BookmarkEntityType,
  BookmarkListResponse,
  BookmarkStatus,
} from '@/types/bookmark'

// 🔖 Bookmarks API — api interceptor unwrap response.data แล้ว (ดู services/api.ts)
// ⚠️ ห้ามส่ง user_id ไปกับ request เด็ดขาด — backend เอาจาก JWT เสมอ
// ไม่ต้องมี permission พิเศษ — ตัวตนคือสิทธิ์

/** รายการที่ฉันบันทึกไว้ (ล่าสุดก่อน) */
export async function listBookmarks(
  params: { entity_type?: BookmarkEntityType; limit?: number; offset?: number } = {},
): Promise<BookmarkListResponse> {
  return (await api.get('/api/bookmarks', { params })) as BookmarkListResponse
}

/** สถานะของ entity เดียว — ให้ปุ่มไอคอนรู้ว่าจะวาดติ๊กหรือไม่ */
export async function getBookmarkStatus(
  entity_type: BookmarkEntityType,
  entity_id: number,
): Promise<BookmarkStatus> {
  return (await api.get('/api/bookmarks/status', {
    params: { entity_type, entity_id },
  })) as BookmarkStatus
}

/**
 * บันทึก — **idempotent**: กดซ้ำได้ไม่ error (201 = เพิ่งบันทึก · 200 = มีอยู่แล้ว)
 * ⚠️ ห้ามเปลี่ยนเป็น 409 — bookmark คือ "อยู่ในชุดที่บันทึก" ไม่ใช่การลงคะแนน
 *    การกดซ้ำจากเน็ตช้า/ดับเบิลแท็ปต้องไม่ขึ้น error ให้ผู้ใช้เห็น
 */
export async function createBookmark(
  entity_type: BookmarkEntityType,
  entity_id: number,
): Promise<Bookmark> {
  return (await api.post('/api/bookmarks', { entity_type, entity_id })) as Bookmark
}

/** ลบของตัวเอง — 404 ถ้าไม่ใช่ของตัวเอง (ห้ามลบข้ามคน) */
export async function deleteBookmark(bookmarkId: number): Promise<void> {
  await api.delete(`/api/bookmarks/${bookmarkId}`)
}
