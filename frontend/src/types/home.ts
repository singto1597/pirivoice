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
import { statsAllZero } from '@/types/me'

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

// ─────────────────────────────────────────────────────────────
// 🗜️ "ยุบบล็อกที่ว่าง" — ตารางความจริงของหน้าแรก
//
// ⚠️ **ทำไมต้องแยกออกมาเป็นฟังก์ชันบริสุทธิ์ ไม่เขียน `v-if` ในเทมเพลต:**
//    สามสถานะนี้ — *ว่าง* / *พัง* / *ยังโหลดไม่เสร็จ* — ให้ผลเหมือนกันเป๊ะถ้าเช็คแค่
//    `length === 0` ⇒ เป็น "ตารางความจริง" ที่พลาดง่ายที่สุดของหน้านี้ และซ่อนอยู่ใน
//    เทมเพลตจะทดสอบไม่ได้ (โปรเจกต์นี้ไม่ mount component ในเทสต์ — ดู `checkInCardState()`
//    ใน `types/event.ts` ที่แยกด้วยเหตุผลเดียวกัน)
//
// 🔴 **กับดักที่ทำให้ทั้งชุดนี้จำเป็น — `?? []` กลืน "พัง" ให้กลายเป็น "ว่าง":**
//    `pendingOnMe = home.value?.pending_on_me ?? []` ⇒ ตอน `homeError` ค่าคือ `[]`
//    และ `unreadCount` เป็น 0 และ `loading` เป็น false ⇒ **เงื่อนไข "ว่าง" เป็นจริงทั้งที่
//    API ล่ม** แล้วหน้าแรกจะขึ้นว่า "ไม่มีเรื่องค้างรอคุณ" ทั้งที่ความจริงคือ *เราไม่รู้*
//    ⇒ ทุกฟังก์ชันที่นี่จึงต้องรับ `homeError`/`error` เข้ามาเอง **ไม่พึ่ง `v-if` ที่อื่น**
// ─────────────────────────────────────────────────────────────

/**
 * สถานะของบล็อกในหน้าแรก
 *
 * - `hidden`    — ไม่ต้องแสดงบล็อกนี้เลย
 * - `collapsed` — แสดงเป็น **แถวเดียว** (บล็อกว่างจริง — ผ่านการตรวจแล้ว)
 * - `full`      — แสดงการ์ดเต็ม (มีของ · กำลังโหลด · หรือมี error ให้แสดงในกรอบของการ์ด)
 */
export type HomeBlockState = 'hidden' | 'collapsed' | 'full'

/**
 * "รอฉันตอบ" — บล็อกเดียวในหน้าแรกที่ต้อง **ทั้งสองสัญญาณ** เป็นศูนย์จึงจะยุบได้
 *
 * 🔴 **`unreadCount` ไม่ใช่ตัวเดียวกับ `pendingCount`** — ยอด "รอฉันตอบ" คือ
 *    `current_assignee_id = ฉัน` (ดู `PendingOnMeItem`) ส่วน `issue_received` เป็น
 *    *กลุ่มการแจ้งเตือน* ⇒ คนละชุดกัน · ป้าย badge ที่หัวการ์ดมาจาก `unreadCount`
 *    ⇒ ถ้ายุบทั้งที่ยังมีของยังไม่อ่าน **สิ่งเดียวที่บอกว่ามีของใหม่จะหายไปพร้อมหัวการ์ด**
 *
 * ⚠️ `loading` → `full` โดยเจตนา: หัวการ์ดต้องอยู่เพื่อให้ skeleton มีที่อยู่ในกรอบ
 *    และเรา **ยังไม่รู้** ว่าว่างไหม ⇒ การขึ้น "ไม่มีเรื่องค้าง" ระหว่างโหลดคือการโกหก
 */
export function pendingOnMeBlockState(o: {
  canReceive: boolean
  homeError: boolean
  loading: boolean
  pendingCount: number
  unreadCount: number
}): HomeBlockState {
  if (!o.canReceive || o.homeError) return 'hidden'
  if (o.loading) return 'full'
  return o.pendingCount === 0 && o.unreadCount === 0 ? 'collapsed' : 'full'
}

/**
 * "สรุปเรื่องของฉัน"
 *
 * ⚠️ `summary === null` → `hidden` (ไม่ใช่ `collapsed`) — **fail closed**: ค่า null
 *    แปลว่า *ยังไม่รู้* ไม่ใช่ *ว่าง* ⇒ ห้ามขึ้น "ยังไม่เคยแจ้งเรื่อง" จากข้อมูลที่ไม่มี
 *    (ตามทฤษฎีไม่ถึง เพราะ `!homeError && !loading` แปลว่า `home.value` มีค่าแล้ว
 *     แต่ถ้าวันหนึ่ง `my_issues` กลายเป็น optional สด ๆ ที่นี่จะไม่พัง)
 */
export function myIssuesBlockState(o: {
  homeError: boolean
  loading: boolean
  summary: MyIssueSummary | null
}): HomeBlockState {
  if (o.homeError) return 'hidden'
  if (o.loading) return 'full'
  if (!o.summary) return 'hidden'
  return o.summary.total_issues === 0 ? 'collapsed' : 'full'
}

/**
 * "สถิติของฉัน"
 *
 * ⚠️ การ์ดนี้ **ใช้ร่วมกับ `Profile.vue`** ⇒ ยุบทิ้งได้เฉพาะที่หน้าแรก การตัดสินจึงอยู่ที่นี่
 *    ไม่ใช่ในตัวคอมโพเนนต์ (Profile ต้องคงกล่อง "ยังไม่มีสถิติในช่วงนี้" เต็มรูปแบบ)
 * ⚠️ ข้อความของแถวต้องผูกกับ **ภาคเรียน** ("ในช่วงนี้") ไม่ใช่ "ยังไม่เคยแจ้งเรื่อง" —
 *    `total_reported` นับตามภาค แต่ `my_issues.total_issues` นับตลอดชีพ ⇒ นักเรียนที่แจ้ง
 *    20 เรื่องภาคที่แล้วและ 0 ภาคนี้ จะเห็นบล็อกบนพูดว่า "20 เรื่อง" และบล็อกล่างพูดว่า
 *    "ยังไม่เคยแจ้ง" ซึ่งขัดกันเองต่อหน้าต่อตา
 */
export function personalStatsBlockState(o: {
  homeError: boolean
  loading: boolean
  stats: PersonalStats | null
}): HomeBlockState {
  if (o.homeError) return 'hidden'
  if (o.loading) return 'full'
  if (!o.stats) return 'hidden'
  return statsAllZero(o.stats) ? 'collapsed' : 'full'
}

/**
 * "คิวจัดการรายงาน" (สภา/แอดมิน)
 *
 * 🔴 **ต้องมี `loaded` แยกจาก `loading`** — `loadingReports` เริ่มที่ `isCouncil` และ
 *    `loadReports()` **return ทันทีโดยไม่ยิง** เมื่อ `!isCouncil` ⇒ ถ้าสิทธิ์เพิ่งกลายเป็นจริง
 *    *หลัง* mount (เส้นทางจริง: `MainLayout` เรียก `loadMe()` ทีหลัง และ guard ตอนนำทาง
 *    กลืน error ไว้) จะได้ `loading === false`, `reports === []` ⇒ เงื่อนไข "ว่าง" เป็นจริง
 *    **ทั้งที่ยังไม่เคยถามเซิร์ฟเวอร์เลย** ⇒ `loaded` บังคับว่าต้องยิงสำเร็จรอบหนึ่งก่อน
 *
 * ⚠️ **ทำไมไม่ต้องดู `total` ประกอบ** — `Home.vue` เรียก `listReports({ status: 'open',
 *    limit: 5 })` **โดยไม่ส่ง `offset`** ⇒ `items` คือหน้าแรกของคำสั่งเดียวกับที่ได้ `total`
 *    ⇒ หน้าแรกว่างก็ต่อเมื่อ `total === 0` พอดี · การเช็ค `total` ซ้ำจึงเป็นสาขาที่ไปไม่ถึง
 *    (ซึ่งแย่กว่าไม่มี เพราะอ่านเหมือนมีเหตุผล)
 *    🔴 **ถ้าวันหน้าเพิ่ม paging (ส่ง `offset`) ต้องกลับมาใส่ `total === 0` ที่นี่** —
 *       ตอนนั้น "หน้าแรกว่าง" กับ "ไม่มีของเลย" จะไม่ใช่เรื่องเดียวกันอีก
 */
export function reportQueueBlockState(o: {
  isCouncil: boolean
  loading: boolean
  loaded: boolean
  error: boolean
  count: number
}): HomeBlockState {
  if (!o.isCouncil) return 'hidden'
  if (o.error || o.loading) return 'full'
  if (!o.loaded) return 'hidden'
  return o.count === 0 ? 'collapsed' : 'full'
}

/**
 * "ภาพรวมทั้งโรงเรียน" (VIEW_DASHBOARD)
 *
 * 🔴 **บล็อกนี้เดิมไม่มีสาขาสุดท้าย** — `v-if` มีแค่ `loadingDash` / `dashError` / `dash`
 *    ⇒ เมื่อ `!loading && !error && !dash` การ์ดจะขึ้น **หัวการ์ดลอย ๆ ที่มีไทล์ + `<h2>` +
 *    ปุ่ม "เปิดแดชบอร์ด" แต่เนื้อในว่างเปล่า** ซึ่งเป็น "ที่ว่าง" ที่แย่กว่าการ์ดว่างปกติ
 *    เพราะดูเหมือนโหลดค้าง · เกิดได้จากเส้นทางเดียวกับ `reportQueueBlockState` (สิทธิ์มา
 *    หลัง mount) ⇒ ที่นี่ตอบ `hidden` แทนการเดาว่าว่าง
 */
export function dashboardBlockState(o: {
  canDashboard: boolean
  loading: boolean
  error: boolean
  hasData: boolean
}): HomeBlockState {
  if (!o.canDashboard) return 'hidden'
  if (o.loading || o.error) return 'full'
  return o.hasData ? 'full' : 'hidden'
}

