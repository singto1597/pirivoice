import api from './api';
import type { AuditLogOptions, AuditLogPage, AuditLogQuery } from '@/types/audit';

// Audit Log API — ดูประวัติการใช้งาน (ต้องมีสิทธิ์ VIEW_AUDIT_LOG)
//
// ⚠️ ไม่ใช้ cache ของชั้น axios (`noCache`) — บันทึกเป็นข้อมูล "ต้องสด" ทั้งหน้า
//   และการเลื่อนหน้าแบบต่อท้าย (`items = [...items, ...result.items]`) จะขัดกับ
//   stale-while-revalidate ที่ reconcile ทับ response ตัวเดิม

/** หน้าหนึ่งของบันทึก (keyset) — ส่ง `cursor` จาก `next_cursor` ของหน้าถัดไปเท่านั้น */
export async function listAuditLogs(params: AuditLogQuery = {}): Promise<AuditLogPage> {
  const { service_name, action, entity_type, entity_id, status, q, date_from, date_to, limit, cursor } =
    params;
  const res = (await api.get('/api/audit-logs', {
    params: {
      service_name: service_name || undefined,
      action: action || undefined,
      entity_type: entity_type || undefined,
      entity_id: entity_id || undefined,
      status: status || undefined,
      q: q || undefined,
      date_from: date_from || undefined,
      date_to: date_to || undefined,
      // ไม่ส่ง limit = ใช้ค่าเริ่มต้นของ backend (30) — ประกาศไว้ที่เดียว ไม่ต้องซิงก์สองที่
      limit: limit ?? undefined,
      cursor: cursor || undefined,
    },
    noCache: true,
  })) as AuditLogPage;
  return res;
}

/** ค่าที่มีจริงในบันทึก — เติม dropdown ของตัวกรอง (ไม่ต้องเดาจากโค้ด) */
export async function getAuditLogOptions(): Promise<AuditLogOptions> {
  const res = (await api.get('/api/audit-logs/options', { noCache: true })) as AuditLogOptions;
  return res;
}
