// 📊 สถิติส่วนตัว (C3) — ข้อมูลของเจ้าของบัญชีเท่านั้น
// ⚠️ `term` เป็น null ได้เสมอ = ยังไม่ได้ตั้งภาคเรียน ⇒ **นับทั้งหมด**
//    ห้ามตีความ null ว่า "0" หรือ "ไม่มีข้อมูล" เด็ดขาด — UI ต้องเขียนกำกับให้ชัด

export interface PersonalStatsTerm {
  id: number
  name: string
  start_date: string // YYYY-MM-DD
  end_date: string // YYYY-MM-DD — ★ รวมวันสุดท้าย (inclusive)
}

export interface PersonalStats {
  term: PersonalStatsTerm | null
  total_reported: number
  resolved_count: number
  in_progress_count: number
  votes_cast: number
  board_comments_posted: number
  issue_comments_posted: number
}

/** คีย์ของ 6 ตัวนับ (ตัด `term` ออก) — ใช้ผูกกับ STAT_ITEMS ให้ type ตรงกันบังคับ */
export type StatKey = Exclude<keyof PersonalStats, 'term'>

// ⚠️ ห้ามใช้ `new Date('2026-05-16')` กับ string แบบ date-only — มันถูกตีความเป็นเที่ยงคืน
//    UTC แล้วเลื่อนเป็นเวลาไทย (+7 ชม.) ⇒ แยก part เองปลอดภัยกว่า (บทเรียนเดียวกับ T1)
const TH_MONTHS_SHORT = [
  'ม.ค.', 'ก.พ.', 'มี.ค.', 'เม.ย.', 'พ.ค.', 'มิ.ย.',
  'ก.ค.', 'ส.ค.', 'ก.ย.', 'ต.ค.', 'พ.ย.', 'ธ.ค.',
]

// ป้ายกำกับ + ไอคอนของแต่ละตัวนับ — **ประกาศที่เดียว**
// Profile.vue และ Home.vue ใช้ชุดเดียวกัน ⇒ เลขสองหน้าไม่มีทางตีความต่างกัน
// (`satisfies` บังคับว่า key ต้องเป็น StatKey จริง และต้องครบทุกตัว)
export const STAT_ITEMS = [
  { key: 'total_reported', label: 'เรื่องที่แจ้ง', icon: 'bi-megaphone' },
  { key: 'resolved_count', label: 'ปิดแล้ว', icon: 'bi-check2-circle' },
  { key: 'in_progress_count', label: 'กำลังดำเนินการ', icon: 'bi-hourglass-split' },
  { key: 'votes_cast', label: 'โหวต', icon: 'bi-hand-thumbs-up' },
  { key: 'board_comments_posted', label: 'คอมเมนต์บอร์ด', icon: 'bi-chat-square-text' },
  { key: 'issue_comments_posted', label: 'คอมเมนต์เรื่อง', icon: 'bi-chat-left-text' },
] as const satisfies ReadonlyArray<{ key: StatKey; label: string; icon: string }>

/** หัวข้อการ์ด — บอกตรง ๆ ว่าตัวเลขชุดนี้ครอบช่วงไหน */
export function statsPeriodLabel(term: PersonalStatsTerm | null): string {
  return term ? `สถิติ${term.name}` : 'สถิติทั้งหมด (ยังไม่ได้ตั้งภาคเรียน)'
}

/** ช่วงวันที่แบบไทย ย่อ — '16 พ.ค. 2569 – 10 ต.ค. 2569' */
export function statsPeriodRange(term: PersonalStatsTerm | null): string | null {
  if (!term) return null
  const fmt = (iso: string): string => {
    const parts = iso.split('-')
    const y = Number(parts[0])
    const m = Number(parts[1])
    const d = Number(parts[2])
    if (!Number.isFinite(y) || !Number.isFinite(m) || !Number.isFinite(d)) return iso
    return `${d} ${TH_MONTHS_SHORT[m - 1]} ${y + 543}`
  }
  return `${fmt(term.start_date)} – ${fmt(term.end_date)}`
}
