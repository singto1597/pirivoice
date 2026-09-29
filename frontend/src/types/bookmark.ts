// 🔖 บันทึกไว้อ่านทีหลัง (C2) — ชุดส่วนตัวของเจ้าของบัญชีเท่านั้น
// ⚠️ ห้ามส่ง user_id ไปกับ request เด็ดขาด — backend เอาจาก JWT เสมอ

/** ชนิดของสิ่งที่บันทึกได้ — backend validate ด้วย Literal ชุดเดียวกัน */
export type BookmarkEntityType = 'issue' | 'board'

/**
 * ลิสต์ชนิดที่บันทึกได้ — ใช้ใน `v-for` ของปุ่มตัวกรอง
 * (ต้องเป็น array literal ไม่ใช่ `Object.keys()` เพราะ key ที่ได้จาก `Record` จะเป็น `string`
 *  แล้ว index `ENTITY_LABELS[key]` จะไม่ผ่าน type-check แบบ strict)
 */
export const ENTITY_TYPES = ['issue', 'board'] as const satisfies readonly BookmarkEntityType[]

export const ENTITY_LABELS: Record<BookmarkEntityType, string> = {
  issue: 'เรื่อง',
  board: 'PIRI Boards',
}

export const ENTITY_ICONS: Record<BookmarkEntityType, string> = {
  issue: 'bi-file-earmark-text',
  board: 'bi-columns-gap',
}

/** ป้ายกำกับตอนต้นทางถูกลบ — ต้องบอก ไม่ใช่ซ่อนแถวทิ้ง */
export const DELETED_SOURCE_LABEL = 'ต้นทางถูกลบแล้ว'

export interface Bookmark {
  id: number
  entity_type: BookmarkEntityType
  entity_id: number
  /**
   * ชื่อเรื่อง/บอร์ด**จริง**จาก join — ⚠️ **ไม่ถูกแทนด้วย placeholder แม้ต้นทางจะถูกลบ**
   * ⇒ หน้าที่แสดงต้องดู `is_deleted_source` เองแล้วตัดสินใจว่าจะหรี่สี/ตัดลิงก์/ติดป้าย
   * (ดู `DELETED_SOURCE_LABEL` ข้างล่าง) · backend ไม่ลบข้อมูลทิ้งให้ frontend เดาไม่ได้
   */
  title: string
  excerpt: string | null
  created_at: string
  /** ต้นทางถูก soft delete ⇒ **ห้ามลิงก์** (กดไปจะ 404) */
  is_deleted_source: boolean
}

/** สถานะของ entity เดียว — ให้ปุ่มไอคอนรู้ว่าจะวาดติ๊กหรือไม่ */
export interface BookmarkStatus {
  bookmarked: boolean
  /** id ที่ใช้ลบ — null เมื่อยังไม่บันทึก */
  bookmark_id: number | null
}

export interface BookmarkListResponse {
  items: Bookmark[]
  total: number
  page: number
  page_size: number
  pages: number
}

/** ป้ายเส้นทางของ entity — ใช้ทั้งในปุ่มและในลิสต์ ⇒ ประกาศที่เดียว */
export function bookmarkPath(entityType: BookmarkEntityType, entityId: number): string {
  return entityType === 'issue' ? `/app/issues/${entityId}` : `/app/boards/${entityId}`
}
