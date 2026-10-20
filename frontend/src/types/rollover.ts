// 🔄 การเลื่อนชั้นทั้งโรงเรียน (School-wide Rollover) — P4 · `/api/rollover/*`
//
// ⚠️ **คนละเรื่องกับ "ปีการศึกษา" (`academicYear.ts`) และ "ภาคเรียน" (`academicTerm.ts`):**
//   · `academicYear.ts`  = ตั้งค่า/CRUD ปี (สร้าง · แก้ · ตั้งเป็นปัจจุบัน · ลบ)
//   · ไฟล์นี้            = **ลงมือ** เลื่อนเด็กทั้งโรงเรียนเข้าปีใหม่ (เขียนจริงหลายพันแถว)
//   ข้อแตกต่างที่มีผลกับ UI: การ "แก้ปี" ผิดแล้วกดซ้ำได้ ส่วนการ "เลื่อนชั้น" **กดซ้ำไม่ได้**
//   (รอบที่ APPLIED แล้วใช้ซ้ำไม่ได้ — backend คืน 409) ⇒ ทุกปุ่มในหน้านี้ต้องบอกก่อนกด
//
// ⚠️ **`apply` ต้องส่ง `run_id` จาก `preview` เท่านั้น** — ไม่มีทางสั่ง apply ด้วยคู่ปีลอย ๆ
//    โดยเจตนา: ปีคู่ที่เลื่อนถูก "ตรึง" ตั้งแต่ตอน preview ⇒ ผู้ใช้ต้องเห็นแผนก่อนกดจริง
//
// ⚠️ **preview รับ `room_overrides` ได้** (ไม่ใช่แค่ตอน apply) — เลขซ้ำ/ห้องที่ยังแมปไม่ได้
//    ต้องโผล่ *ก่อน* กดปุ่มอันตราย ไม่ใช่ครั้งแรกตอนกดแล้วล้ม (ดู `docs/skills.md`)

import type { Room } from '@/types/student'

export interface RolloverYearRef {
  id: number
  /** ⚠️ พ.ศ. (2569) ไม่ใช่ ค.ศ. (2026) — ระบบนี้แสดง พ.ศ. ทั้งหมด */
  year_be: number
  name: string
}

/** จำนวนคนแยกตามบทบาท — `by_role` ว่าง = กลุ่มนั้นไม่มีใคร (ไม่ใช่ "ไม่รู้") */
export interface RolloverCountByRole {
  count: number
  by_role: Record<string, number>
}

/** หนึ่งห้องในแผน · `status='unmapped'` = ห้องที่ระบบหาปลายทางไม่ได้ ต้องเลือกเอง */
export interface RolloverRoomRow {
  from_room_code: string | null
  to_room_code: string | null
  student_count: number
  status: string
}

/** สรุปต่อระดับชั้น · `target_level=null` = ระบบเลื่อนอัตโนมัติไม่ได้ (ต้องเลือกเอง) */
export interface RolloverLevelGroup {
  level: string | null
  target_level: string | null
  student_count: number
  mapped_rooms: number
  unmapped_rooms: number
  rooms: RolloverRoomRow[]
}

export interface RolloverGraduatingRoom {
  room_code: string | null
  student_count: number
}

/** ผู้จบการศึกษา — แถวเดิมกลายเป็น `graduated` และ **ไม่สร้างแถวใหม่** */
export interface RolloverGraduating {
  count: number
  rooms: RolloverGraduatingRoom[]
}

/** ห้องที่หาปลายทางไม่ได้ — **ต้องแก้ก่อนจึงจะ apply ได้** */
export interface RolloverUnmappedRoom {
  from_room_code: string | null
  from_room_id: number | null
  level: string | null
  student_count: number
  /** เหตุผลจาก backend (ไทย) — เช่น "ไม่มีห้อง «ม.4/14» ในระบบ" */
  reason: string
}

/**
 * แผนการเลื่อนชั้น — รูปเดียวกับ `plan` JSONB ที่ backend เก็บลง `rollover_runs`
 *
 * ⚠️ ค่าที่ตัดสินว่า "กดได้ไหม" มีสองตัวและ **backend เป็นคนตัดสิน**:
 *    `can_apply` (= `blockers.length === 0`) — UI ห้ามคิดเองว่าอะไรเป็น blocker
 */
export interface RolloverPlan {
  from_year: RolloverYearRef
  to_year: RolloverYearRef
  total_active: number
  promoted: RolloverCountByRole
  graduating: RolloverGraduating
  staff_carried: RolloverCountByRole
  positions_reset: RolloverCountByRole
  council_lapsing: RolloverCountByRole
  roomless: RolloverCountByRole
  by_level: RolloverLevelGroup[]
  unmapped: RolloverUnmappedRoom[]
  blockers: string[]
  warnings: string[]
  can_apply: boolean
}

/** ผล `POST /rollover/preview` — แผน + `run_id` ที่ต้องส่งกลับตอน apply */
export interface RolloverPreview extends RolloverPlan {
  run_id: number
}

/**
 * ผล `POST /rollover/apply` — ตัวเลขที่ **เกิดขึ้นจริง** (ไม่ใช่ที่ preview ไว้)
 *
 * ⚠️ `plan` ที่นี่เป็น JSONB ก้อนที่ backend เก็บ (`{preview, applied, room_overrides}`)
 *    — **คนละรูปร่างกับ `RolloverPreview`** ⇒ อย่าพิมพ์เป็น `RolloverPlan`
 *    (ของจริงในรอบที่ APPLIED แล้วจะไม่ตรงกับ interface นั้น และจะพังเงียบ ๆ ตอนอ่าน)
 */
export interface RolloverApplyResult {
  run_id: number
  from_year: RolloverYearRef
  to_year: RolloverYearRef
  promoted_count: number
  graduated_count: number
  staff_carried_count: number
  positions_reset_count: number
  closed_count: number
  room_overrides: Record<string, string>
  plan: Record<string, unknown>
}

/** หนึ่งรอบการเลื่อนชั้น (ใช้ทั้งหน้าประวัติ) */
export interface RolloverRun {
  id: number
  from_year_id: number
  to_year_id: number
  /** `PREVIEWED` / `APPLIED` / `FAILED` — ⚠️ ตัวพิมพ์ใหญ่ตามที่ DB เก็บ */
  status: string
  from_year: RolloverYearRef
  to_year: RolloverYearRef
  promoted_count: number
  graduated_count: number
  staff_carried_count: number
  positions_reset_count: number
  unmapped_count: number
  error_message: string | null
  created_by: number | null
  created_at: string | null
  applied_at: string | null
  updated_at: string | null
  plan: Record<string, unknown>
}

export interface RolloverRunListResponse {
  items: RolloverRun[]
  total: number
}

/** หนึ่งคนในรายงานกระทบยอด · `user_id=null` = แถวที่ไม่มีบัญชีผูกอยู่ */
export interface ReconciliationPerson {
  user_id: number | null
  student_id: string | null
  first_name: string | null
  last_name: string | null
  class_role: string | null
  room_code: string | null
}

/**
 * กระทบยอดรายชื่อสองปี — **ไม่เดาสาเหตุ** แค่บอกว่าใครหาย/ใครเพิ่ม
 *
 * `missing` = มีในปีก่อน แต่ไม่มีในปีใหม่ (ย้ายออก / จบ / ตกหล่น — **คนตัดสิน**)
 * `added`   = มีในปีใหม่ แต่ไม่มีในปีก่อน (ย้ายเข้า)
 */
export interface Reconciliation {
  from_year_id: number
  to_year_id: number
  missing_count: number
  added_count: number
  missing: ReconciliationPerson[]
  added: ReconciliationPerson[]
}

// ============================================================
// 🧠 Pure helpers — ทดสอบได้โดยไม่ต้องมี DOM
// ============================================================
// ตาม frontend.md §4: ต้องแยก "ว่าง ≠ พัง ≠ ยังโหลดไม่เสร็จ" ออกจากกันให้ได้
// ⚠️ ไฟล์นี้มี helper เยอะกว่าหน้าอื่นโดยเจตนา — หน้านี้เป็นหน้าเดียวในระบบที่
//    "กดผิดแล้วกู้ไม่ได้" (ต้อง restore dump) ⇒ ตรรกะที่ตัดสินว่ากดได้ไหมต้องมีเทสต์คุม

export type RolloverScreenState = 'loading' | 'error' | 'idle' | 'plan'

/** สถานะหน้าจอจากข้อมูลที่มี — เรียงตาม "สิ่งที่ผู้ใช้ต้องรู้ก่อน" */
export function rolloverScreenState(opts: {
  isLoading: boolean
  hasError: boolean
  hasPlan: boolean
}): RolloverScreenState {
  if (opts.hasError) return 'error'
  // `isLoading` ต้องมาหลัง `hasError` — การโหลดรอบสองที่ล้มต้องโชว์ error
  // ไม่ใช่ค้างที่ skeleton ตลอดกาล (บทเรียนเดียวกับ `yearScreenState`)
  if (opts.isLoading && !opts.hasPlan) return 'loading'
  // 🔴 `idle` **ไม่ใช่** `empty` — "ยังไม่ได้กดดูแผน" ต่างจาก "ปีนี้ไม่มีคน"
  //    ⇒ ต้องโชว์ปุ่ม «ดูแผน» ไม่ใช่ข้อความว่างที่อ่านแล้วเหมือนระบบพัง
  if (!opts.hasPlan) return 'idle'
  return 'plan'
}

/** ตัดคู่ที่ค่าเป็นค่าว่างทิ้ง — **ทำซ้ำกับ `_clean_overrides` ใน `rollover_schemas.py` เป๊ะ**
 *
 *  ⚠️ ช่องว่างใน UI แปลว่า "ยังไม่เลือก" ไม่ใช่ห้องชื่อ '' ⇒ backend ตัดทิ้งอยู่แล้ว
 *     ที่นี่ตัดก่อนเพื่อให้ `overridesDirty()` เทียบของจริง ไม่ใช่เทียบกับค่าว่างที่ค้างอยู่
 */
export function cleanOverrides(overrides: Record<string, string> | null | undefined): Record<
  string,
  string
> {
  const out: Record<string, string> = {}
  for (const [key, value] of Object.entries(overrides ?? {})) {
    const k = (key ?? '').trim()
    const v = (value ?? '').trim()
    if (k && v) out[k] = v
  }
  return out
}

/** `overrides` ถูกแก้หลังจากดูแผนครั้งล่าสุดไหม
 *
 *  🔴 **ต้องเตือน ไม่ใช่ปล่อยผ่าน** — backend ตรวจ `can_apply` จากแผนที่ *preview ไว้*
 *     แต่ค่าที่ส่งตอน apply คือค่าที่อยู่ในฟอร์ม ⇒ ถ้าผู้ใช้แก้ช่องแล้วกดยืนยันเลย
 *     เขาจะยืนยันบนแผนที่ไม่เคยเห็น (และถ้าแก้เป็นห้องที่ทำให้เลขซ้ำ จะได้ 400 กลางทาง)
 *  ⇒ หน้าเว็บใช้ฟังก์ชันนี้ตัดสินว่าจะโชว์ป้าย "กด «ดูแผน» อีกครั้ง" ไหม
 */
export function overridesDirty(
  previewed: Record<string, string> | null | undefined,
  current: Record<string, string> | null | undefined,
): boolean {
  const a = cleanOverrides(previewed)
  const b = cleanOverrides(current)
  const ka = Object.keys(a)
  const kb = Object.keys(b)
  if (ka.length !== kb.length) return true
  return ka.some((k) => a[k] !== b[k])
}

/** ห้องที่ **ยังไม่ได้เลือก** ห้องปลายทาง (ใช้ทำป้ายแดงรายแถวในตาราง) */
export function missingOverrideRooms(
  plan: RolloverPlan | null,
  overrides: Record<string, string>,
): RolloverUnmappedRoom[] {
  if (!plan) return []
  const chosen = cleanOverrides(overrides)
  return plan.unmapped.filter((u) => !u.from_room_code || !chosen[u.from_room_code])
}

/** เหตุผลที่ยังกด «ยืนยันเลื่อนชั้น» ไม่ได้ — `''` = กดได้
 *
 *  ⚠️ **ห้ามคิดเองว่าอะไรคือ blocker** — อ่าน `plan.blockers` / `plan.can_apply`
 *     ที่ backend คิดมาแล้วเท่านั้น (มันคือชุดเดียวกับที่ `apply_rollover` จะ `raise`
 *     ⇒ ถ้า UI คิดต่าง ผู้ใช้จะเจอ "ปุ่มกดได้แต่กดแล้วล้ม" ซึ่งทำลายความเชื่อถือในคำเตือน)
 */
export function applyBlockReason(plan: RolloverPlan | null): string {
  if (!plan) return 'กด «ดูแผน» เพื่อตรวจรายชื่อก่อน'
  if (plan.blockers.length > 0) return 'ยังมีข้อที่ต้องแก้ก่อน — ดูรายการ «ต้องแก้ก่อน» ด้านบน'
  if (!plan.can_apply) return 'แผนนี้ยังกดไม่ได้ — กด «ดูแผน» ใหม่อีกครั้ง'
  return ''
}

/** ข้อความยืนยันก่อนกดปุ่มอันตราย — **ต้องบอกให้ครบว่ากำลังจะเกิดอะไรขึ้น**
 *
 *  ⚠️ ปุ่มนี้คือปุ่มเดียวในระบบที่ "กดผิดแล้วต้องกู้ dump" ⇒ ข้อความต้องบอกทั้ง
 *     (ก) ใครถูกย้ายกี่คน (ข) จากปีไหนไปปีไหน (ค) ปีเก่าถูกปิด (ง) ปีใหม่กลายเป็นปีปัจจุบัน
 *     ไม่ใช่แค่ "ยืนยัน?" — คำถามลอย ๆ ไม่ช่วยให้ใครตัดสินใจถูก
 */
export function applyConfirmText(plan: RolloverPlan): string {
  const parts = [
    `ยกนักเรียน ${plan.promoted.count} คนขึ้นปี «${plan.to_year.name}»`,
  ]
  if (plan.graduating.count > 0) parts.push(`จบการศึกษา ${plan.graduating.count} คน (ไม่สร้างแถวใหม่)`)
  if (plan.staff_carried.count > 0) parts.push(`ยกบุคลากร ${plan.staff_carried.count} คนไปปีใหม่`)
  parts.push(`ปิดแถวสมาชิกปี «${plan.from_year.name}» ทั้งหมดไว้เป็นประวัติ`)
  parts.push(`และตั้ง «${plan.to_year.name}» เป็นปีปัจจุบัน`)
  return `${parts.join(' · ')} — ย้อนกลับเองไม่ได้`
}

/** หัวข้อกลุ่มระดับชั้น — `ม.1 → ม.2` · `ม.6 …` ไม่มีทางเกิด (คน ม.6 ถูกแยกไป `graduating`) */
export function levelGroupTitle(g: RolloverLevelGroup): string {
  const level = g.level ?? '(ไม่ทราบระดับ)'
  if (g.target_level) return `${level} → ${g.target_level}`
  // ระดับที่ไม่อยู่ใน LEVEL_NEXT (เช่นห้องพิมพ์ผิด) ⇒ ห้องทุกห้องในกลุ่มนี้เป็น unmapped
  // ⚠️ ไม่ใช่ "จบการศึกษา" — คนที่จบถูกตัดออกจาก `by_level` ตั้งแต่ที่ backend แล้ว
  return `${level} — ระบบเลื่อนอัตโนมัติไม่ได้`
}

/** รหัสห้องเรียงตามระดับแล้วเลขห้อง — `ม.1/1, ม.1/2, …, ม.6/9`
 *
 *  ⚠️ เรียงด้วย `localeCompare` แบบ numeric ต่อ **segment** ไม่ใช่เทียบสตริงดิบ
 *     (ถ้าเทียบดิบ `ม.1/10` จะมาก่อน `ม.1/2` ซึ่งอ่านแล้วเหมือนข้อมูลพัง)
 */
export function sortRoomCodes(codes: string[]): string[] {
  return [...codes].sort((a, b) => {
    const [la, na] = a.split('/')
    const [lb, nb] = b.split('/')
    const byLevel = (la ?? '').localeCompare(lb ?? '', 'th', { numeric: true })
    if (byLevel !== 0) return byLevel
    return (na ?? '').localeCompare(nb ?? '', 'th', { numeric: true })
  })
}

/** ตัวเลือกลูกศรสำหรับช่อง "ห้องปลายทาง" — ทุกห้องที่ระบบรู้จัก (backend ตรวจซ้ำอีกชั้น) */
export function roomOptions(rooms: Room[]): Array<{ value: string; label: string }> {
  return sortRoomCodes(rooms.map((r) => r.room_code)).map((code) => ({ value: code, label: code }))
}

/** สรุปบรรทัดเดียวหลังทำสำเร็จ — ใช้ทั้งใน Swal และการ์ดผลลัพธ์ */
export function applyResultText(r: RolloverApplyResult): string {
  const parts = [`เลื่อนขึ้นปีใหม่ ${r.promoted_count} คน`]
  if (r.graduated_count > 0) parts.push(`จบ ${r.graduated_count} คน`)
  if (r.staff_carried_count > 0) parts.push(`บุคลากร ${r.staff_carried_count} คน`)
  parts.push(`ปิดแถวปีเก่า ${r.closed_count} แถว`)
  return `${parts.join(' · ')} — ปี «${r.to_year.name}» เป็นปีปัจจุบันแล้ว`
}

/** ชื่อ-นามสกุลของคนในรายงานกระทบยอด — ไม่มีชื่อเลยต้องไม่โชว์ช่องว่างเปล่า */
export function personName(p: ReconciliationPerson): string {
  const name = [p.first_name, p.last_name].filter(Boolean).join(' ').trim()
  return name || `(ไม่มีชื่อในระบบ · รหัส ${p.student_id ?? '-'})`
}
