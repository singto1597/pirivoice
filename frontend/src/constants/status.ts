// สีสถานะ (semantic) — ใช้ร่วมกันทั้งหน้า อย่าให้สีหมวดหลักมาทับ
// แผนภาพสีแบบจำกัด (Editorial & Civic):
//   resolved    → emerald (ปิดเรื่อง/สำเร็จ)
//   in_progress → cardinal tint (กำลังดำเนินการ)
//   escalated   → cardinal ทึบ (ถูกส่งต่อ/เด่นสุด)
//   pending     → stone (รอรับ — muted)
//   cancelled / rejected → stone อ่อน
// ตัวอย่างเดิมเป็นรุ้ง (yellow/blue/orange/green/rose) — ยกเลิกแล้ว กันสีหลักทับ

export const STATUS_DOT: Record<string, string> = {
  pending: 'bg-stone-400',
  in_progress: 'bg-brand',
  escalated: 'bg-brand-strong',
  resolved: 'bg-emerald-500',
  cancelled: 'bg-stone-300',
  rejected: 'bg-stone-500',
};

export const STATUS_BAR: Record<string, string> = {
  pending: 'bg-stone-300',
  in_progress: 'bg-brand',
  escalated: 'bg-brand-strong',
  resolved: 'bg-emerald-500',
  cancelled: 'bg-stone-200',
  rejected: 'bg-stone-300',
};

export const STATUS_BADGE: Record<string, string> = {
  pending: 'bg-stone-100 text-stone-600',
  in_progress: 'bg-brand/10 text-brand',
  escalated: 'bg-brand text-white',
  resolved: 'bg-emerald-100 text-emerald-700',
  cancelled: 'bg-stone-200 text-stone-500',
  rejected: 'bg-stone-100 text-stone-500',
};

// ป้ายสั้น (สำหรับแถวรายการ/ชิป) — แยกจาก STATUS_LABELS ยาวที่ใช้ใน dropdown/filter
export const STATUS_SHORT: Record<string, string> = {
  pending: 'รอรับ',
  in_progress: 'กำลังทำ',
  escalated: 'ส่งต่อ',
  resolved: 'เสร็จแล้ว',
  cancelled: 'ยกเลิก',
  // 🏷️ "ปฏิเสธ" = สภาตรวจแล้วไม่รับเรื่อง (คนละความหมายกับ `dismissed` ของ *รายงาน*
  //    ซึ่งแปลว่า "ตรวจแล้วไม่ดำเนินการกับคอมเมนต์" — ดู `types/board.ts`)
  //    เดิมใช้คำเดียวกันว่า "ปัดตก" ทั้งสองความหมาย ซึ่งเป็นศัพท์ภายในที่ผู้ใช้อ่านไม่ออก
  rejected: 'ปฏิเสธ',
};

export function statusShort(status: string): string {
  return STATUS_SHORT[status] ?? status;
}

/**
 * 🔗 โทเคนใน URL ที่ใช้แทนความหมาย "ทุกสถานะ"
 *
 * ⚠️ **ทำไมไม่ใช้สตริงว่าง** — ในหน้า `ReceivedIssues` ค่า `''` คือ "ทุกสถานะ"
 *    (ดู `STATUS_FILTERS`) แต่ **สตริงว่างใส่ใน query string ไม่ได้** — `?status=`
 *    กลายเป็น "มีคีย์แต่ค่าว่าง" ซึ่งอ่านกลับมาแล้วแยกไม่ออกว่า "ตั้งใจขอทุกสถานะ"
 *    หรือ "ไม่มีคีย์" (ค่าเริ่มต้น = `not_resolved`) ⇒ ลิงก์ที่ตั้งใจขอ *ทุกสถานะ*
 *    จะกลับกลายเป็น *ยังไม่เสร็จ* เงียบ ๆ — ตัวเลขบนการ์ดกับในลิสต์จะไม่ตรงกัน
 *
 * 📌 ตัวนี้เป็น **สัญญาระหว่าง `Dashboard.vue` กับ `ReceivedIssues.vue`** —
 *    แก้ค่าเมื่อไหร่ต้องแก้ทั้งผู้เขียนและผู้อ่านพร้อมกัน
 */
export const STATUS_URL_ALL = 'all';
