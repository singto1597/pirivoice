// ประเภทข้อมูล Audit Log (บันทึกการใช้งาน)
//
// ⚠️ backend บันทึกครบทุกคอลัมน์แล้ว (migration 013 — ห้ามเว้นว่าง) ค่าที่ "ไม่รู้" จะมาเป็น
// sentinel ไม่ใช่ null: '-' = ไม่ทราบ/ไม่มีค่า, {} = ไม่มีการเปลี่ยนแปลงข้อมูล, -1 = ไม่ระบุห้อง/ตัวตน
// (ดู UNKNOWN / EMPTY_JSON / UNRESOLVED_ID ใน backend/core/logger.py)
// คง `| null` ไว้เป็นเกราะกันข้อมูลเก่า/กรณี parse พลาด — UI ให้ใช้ helper ใน AuditLogs.vue ตัดสินใจแสดง

export interface AuditLogItem {
  id: string;
  trace_id: string | null;
  user_id: number | null;
  // 🏫 room_id = -1 เมื่อไม่ระบุห้อง ; room_name = null เมื่อไม่พบห้องนั้นในตาราง rooms
  room_id: number | null;
  room_name: string | null;
  /** สิ่งที่ผู้กระทำพิมพ์ตอนล็อกอิน/ยิง API — ไม่ใช่ id เสมอไป */
  actor_identifier: string;
  /** ชื่อจากตาราง users (null ถ้าผู้ใช้ถูกลบ/ไม่รู้จัก เช่น login ที่หาชื่อไม่เจอ) */
  actor_name: string | null;
  client_source: string;
  service_name: string;
  action: string;
  entity_type: string | null;
  entity_id: string | null;
  status: string; // success / error / partial
  error_detail: string | null;
  // ⚠️ jsonb คืนได้ทั้ง object และ array (audit บางจุดเก็บ list) ⇒ `unknown` ไม่ใช่ Record
  old_values: unknown;
  new_values: unknown;
  endpoint_or_command: string | null;
  ip_address: string | null;
  user_agent: string | null;
  execution_time_ms: number | null;
  created_at: string;
}

/**
 * หน้าหนึ่งของบันทึก — แบบ **keyset** (ไม่มี total/page/offset)
 *
 * ⚠️ `audit_logs` มีแถวใหม่แทรกหัวตลอดเวลา ⇒ `OFFSET` ทำให้หน้าถัดไปเห็นซ้ำ/ข้าม
 * ส่ง `next_cursor` กลับมาเป็น `cursor` ของคำขอถัดไปเท่านั้น **ห้ามคำนวณเอง**
 */
export interface AuditLogPage {
  items: AuditLogItem[];
  /** null = หมดแล้ว */
  next_cursor: string | null;
  has_more: boolean;
}

/** ค่าที่มีจริงในบันทึก 90 วันล่าสุด — เติม dropdown (เรียงแล้ว ไม่ซ้ำ ไม่มี sentinel '-') */
export interface AuditLogOptions {
  service_names: string[];
  actions: string[];
  statuses: string[];
  entity_types: string[];
}

export interface AuditLogFilters {
  service_name?: string;
  action?: string;
  entity_type?: string;
  entity_id?: string;
  status?: string;
  q?: string;
  date_from?: string; // YYYY-MM-DD (ตีความเป็นวันตามเวลาไทยที่ backend)
  date_to?: string; // YYYY-MM-DD
}

export interface AuditLogQuery extends AuditLogFilters {
  /** next_cursor จากหน้าถัดไป — ส่งกลับมาตรง ๆ ห้ามคำนวณ */
  cursor?: string;
  limit?: number;
}
