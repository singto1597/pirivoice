// ประเภทข้อมูลของหน้าแรก (B1) — GET /api/home/summary
//
// 🎯 หน้าแรกยิง **call เดียว** แล้วได้ทุกอย่างที่ทุกคนเห็นเหมือนกัน
//    (ประกาศ · สรุปเรื่องของฉัน · รอฉันตอบ · โหวตที่ยังไม่โหวต · สถิติส่วนตัว)
//    ❌ แดชบอร์ดและคิวรายงาน **ไม่อยู่ในนี้** — เป็น permission-gated และแดชบอร์ดหนัก
//       ⇒ Home ยังยิงสองตัวนั้นแยก เฉพาะคนที่มีสิทธิ์
//
// ⚠️ ฟิลด์ต้องตรงกับ backend/models/home_schemas.py — ที่นี่ไม่ประกาศ type ของ
//    `announcements` / `my_issues` / `stats` ใหม่ แต่ **reuse** ของเดิม
//    (ถ้าประกาศซ้ำ วันหน้า backend เพิ่มฟิลด์แล้วจะลืมแก้ที่ใดที่หนึ่ง)

import type { PublicAnnouncement } from '@/types/announcement'
import type { MyIssueSummary } from '@/types/issue'
import type { PersonalStats } from '@/types/me'

/**
 * เรื่องที่ `current_assignee_id` เป็นฉันและยังไม่จบ — "รอฉันตอบ"
 *
 * ⚠️ เป้าแคบกว่า `GET /api/issues?received=true` โดยเจตนา — ตัวนั้นรวมเรื่องที่ฉัน
 * แค่ไปเกี่ยวข้อง (เป็นผู้แจ้ง / มี countdown ของฉัน) ซึ่งไม่ใช่ "ต้องรอฉันตอบ"
 */
export interface PendingOnMeItem {
  id: number
  title: string
  status: string
  priority: string
  current_level: string
  created_at: string
  room_name: string | null
}

/** บอร์ดโหวตที่ยังเปิดอยู่และฉันยังไม่ได้โหวต */
export interface UnvotedBoardItem {
  id: number
  title: string
  created_at: string
  /** จำนวนโหวตของ **ทั้งบอร์ด** (ไม่ใช่ของฉัน) — ให้เห็นว่าคนอื่นสนใจแค่ไหน */
  vote_count: number
}

export interface HomeSummary {
  /** ⚠️ ไม่ถูกตัด/slice โดยเจตนา — เจ้าของระบบสั่ง "โชว์ทั้งหมดที่ยังไม่ถอดออก" */
  announcements: PublicAnnouncement[]
  my_issues: MyIssueSummary
  pending_on_me: PendingOnMeItem[]
  /** ยอดจริง (ไม่ถูก LIMIT ตัด) — ใช้ขึ้น "และอีก N เรื่อง" */
  pending_on_me_total: number
  unvoted_boards: UnvotedBoardItem[]
  unvoted_boards_total: number
  /** กิจกรรมใกล้ปิดรับ (4.5) — ⚠️ **ไม่กรองตามการสมัครของฉัน** ⇒ มีแถวที่สมัครแล้วปนได้ */
  closing_soon_events: ClosingSoonEventItem[]
  closing_soon_events_total: number
  stats: PersonalStats
}

/**
 * ข้อความ "และอีก N …" — คืน `null` เมื่อไม่มีอะไรเหลือ
 *
 * ทำเป็นฟังก์ชันเพราะต้องใช้ทั้งสองคิว (รอฉันตอบ / โหวตที่ยังไม่โหวต) และต้องคิด
 * จาก `total - shown` เท่านั้น — **ห้ามเทียบ `total` กับ limit ที่ hardcode**
 * เพราะ limit อยู่ฝั่ง backend
 *
 * `noun` ให้แต่ละคิวใช้คำของตัวเอง ("เรื่อง" / "บอร์ด") — ค่าเริ่มต้นคือ "เรื่อง"
 */
export function remainingLabel(total: number, shown: number, noun = 'เรื่อง'): string | null {
  const rest = total - shown
  return rest > 0 ? `และอีก ${rest} ${noun}` : null
}

/**
 * ป้ายไอออนของบอร์ดโหวต — บอก "มีคนโหวตแล้วกี่คน" ให้อ่านออกในบรรทัดเดียว
 */
export function voteCountLabel(count: number): string {
  return count > 0 ? `มีผู้โหวตแล้ว ${count} คน` : 'ยังไม่มีใครโหวต — คุณเป็นคนแรกได้'
}

/**
 * กิจกรรมที่ยังเปิดรับและกำลังจะปิดรับ — "กิจกรรมใกล้ปิดรับ" (4.5)
 *
 * ⭐ `closes_at` มาจาก backend ( = `min(วันจัด, กำหนดปิดรับ)`) **ไม่ใช่**
 *    `registration_deadline` — กิจกรรมที่ไม่ได้ตั้งกำหนดปิดรับจะปิดที่ *วันจัด*
 *    ⇒ ฝั่งจอ **ห้าม** เอา `registration_deadline` มาตัดสินอะไรเอง (ดูคอมเมนต์
 *    ใน `EventPublicOut.closes_at`)
 *
 * ⚠️ ไม่มี `is_registration_open` — backend กรองมาแล้วว่ายังเปิดรับ ⇒ ทุกแถวเป็น `true`
 *    เสมอ การเพิ่มฟิลด์ที่ไม่มีวันเป็นเท็จทำให้คนอ่านโค้ดเขียน `if` กันโดยเปล่าประโยชน์
 *
 * ⚠️ ไม่มี `description` / `cover_image_url` โดยเจตนา — การ์ดนี้เป็นบรรทัดเดียว
 *    ⇒ บรรทัดที่ยาวจะดันความสูงจนการ์ดอื่นเสียทรง
 */
export interface ClosingSoonEventItem {
  id: number
  title: string
  location: string | null
  event_date: string
  closes_at: string
  /**
   * `null` = ไม่จำกัดจำนวน (ไม่ใช่ 0 — 0 แปลว่าเต็ม ⇒ สมัครได้แต่จะได้คิวสำรอง)
   * ⇒ ใช้ `seatsWarning()` จาก `@/types/event` อ่านค่า **ไม่ใช่ `seatsLabel()`**
   *    (ตัวหลังมี threshold ต่างกัน — ดูคอมเมนต์ที่ `seatsWarning`)
   */
  seats_remaining: number | null
  /** 'registered' / 'checked_in' / null — ใช้ตัดสินว่าจอแสดง *ปุ่มสมัคร* หรือ *ป้ายสมัครแล้ว* */
  my_registration_status: string | null
}

