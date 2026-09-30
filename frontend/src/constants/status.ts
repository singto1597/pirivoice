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
  rejected: 'ปัดตก',
};

export function statusShort(status: string): string {
  return STATUS_SHORT[status] ?? status;
}
