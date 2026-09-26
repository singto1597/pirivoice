// ประเภทข้อมูล Audit Log (บันทึกการใช้งาน)
//
// ⚠️ backend บันทึกครบทุกคอลัมน์แล้ว (migration 013 — ห้ามเว้นว่าง) ค่าที่ "ไม่รู้" จะมาเป็น
// sentinel ไม่ใช่ null: '-' = ไม่ทราบ/ไม่มีค่า, {} = ไม่มีการเปลี่ยนแปลงข้อมูล, -1 = ไม่ระบุห้อง/ตัวตน
// (ดู UNKNOWN / EMPTY_JSON / UNRESOLVED_ID ใน backend/core/logger.py)
// คง `| null` ไว้เป็นเกราะกันข้อมูลเก่า/กรณี parse พลาด — UI ให้ใช้ isBlank() ใน AuditLogs.vue ตัดสินใจแสดง

export interface AuditLogEntry {
  id: string;
  trace_id: string | null;
  user_id: number | null;
  // 🏫 room_id = -1 เมื่อไม่ระบุห้อง ; room_name = null เมื่อไม่พบห้องนั้นในตาราง rooms
  room_id: number | null;
  room_name: string | null;
  actor_identifier: string;
  client_source: string;
  service_name: string;
  action: string;
  entity_type: string | null;
  entity_id: string | null;
  status: string; // success / error / partial
  error_detail: string | null;
  old_values: Record<string, unknown> | null;
  new_values: Record<string, unknown> | null;
  endpoint_or_command: string | null;
  ip_address: string | null;
  user_agent: string | null;
  execution_time_ms: number | null;
  created_at: string;
}

export interface AuditLogListResponse {
  items: AuditLogEntry[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface AuditLogFilters {
  action?: string;
  entity_type?: string;
  status?: string;
  q?: string;
  date_from?: string; // YYYY-MM-DD
  date_to?: string; // YYYY-MM-DD
}
