import api from './api'
import type {
  Reconciliation,
  RolloverApplyResult,
  RolloverPreview,
  RolloverRunListResponse,
} from '@/types/rollover'

// 🔄 การเลื่อนชั้นทั้งโรงเรียน — api interceptor unwrap response.data แล้ว (ดู services/api.ts)
//
// ⚠️ **คนละประตูกับ `/api/settings/years`** (ปีการศึกษา):
//    · `/api/settings/years`  = `MANAGE_SETTINGS` ล้วน
//    · `/api/rollover/*`      = `MANAGE_STUDENTS` **และ** โหมดจัดการระดับโรงเรียน
//      (`get_manage_mode() == 'school'` — ต้องมี `is_admin` ด้วย)
//    ⇒ ประธานระดับชั้น/ครูทั่วไปมี `MANAGE_STUDENTS` แต่ **403 ที่นี่** โดยเจตนา
//      (ครูระดับชั้นต้องเลื่อนทั้งโรงเรียนไม่ได้ — ดู `rollover_service._gate`)

/**
 * ดูแผนการเลื่อนชั้น — **ไม่แก้ข้อมูลสมาชิกเลย** (เรียกซ้ำได้ไม่จำกัด)
 *
 * ⚠️ เขียนแถว `rollover_runs` สถานะ `PREVIEWED` ทุกครั้งที่เรียก (เป็นหลักฐานว่า "ตอนนั้น
 *    ระบบคิดว่าจะเกิดอะไร") ⇒ **อย่าเรียกซ้ำรัว ๆ จาก watcher/computed**
 *
 * ⚠️ `room_overrides` ส่งได้ตั้งแต่ตอนนี้ (ไม่ใช่แค่ตอน apply) — เพื่อให้เห็น *ก่อน* ว่าหลังเลือก
 *    ห้องปลายทางแล้ว `can_apply` เป็นจริงหรือยัง และมีปัญหาอื่นโผล่ไหม (เช่นเลขประจำตัวซ้ำ)
 */
export async function previewRollover(payload: {
  from_year_id: number
  to_year_id: number
  room_overrides?: Record<string, string>
}): Promise<RolloverPreview> {
  return (await api.post('/api/rollover/preview', payload)) as RolloverPreview
}

/**
 * 🔴 **ทำจริง** — เลื่อนทุกคนเข้าปีใหม่ ปิดแถวปีเก่า ตั้งปีใหม่เป็นปีปัจจุบัน
 *
 * ⚠️ ต้องส่ง `run_id` จาก `preview` **รอบล่าสุดที่ผู้ใช้เห็น** — รอบเดิมใช้ซ้ำไม่ได้ (**409**)
 * ⚠️ **409 อีกกรณี**: ปีปลายทางมีสมาชิกแทรกเข้ามาหลัง preview (มีคน import ระหว่างนั้น)
 *    ⇒ ข้อความจาก backend บอกจำนวนคนที่แทรกมา — ส่งต่อทั้งดุ้น ไม่ต้องแปลใหม่
 */
export async function applyRollover(payload: {
  run_id: number
  room_overrides?: Record<string, string>
}): Promise<RolloverApplyResult> {
  return (await api.post('/api/rollover/apply', payload)) as RolloverApplyResult
}

/**
 * ประวัติการเลื่อนชั้น (ใหม่สุดก่อน) — "ใครกด เมื่อไหร่ ผลเป็นยังไง"
 *
 * แต่ละรอบเก็บแผนเต็มไว้ ⇒ ย้อนดูได้ว่าตอนนั้นระบบคิดว่าจะเกิดอะไร
 * (ใช้ตอบ "ทำไมเด็กคนนี้หายไป" ได้โดยไม่ต้องเดา) · จำนวนรอบน้อยมาก ⇒ ไม่แบ่งหน้าแบบ envelope
 */
export async function listRolloverRuns(
  params: { limit?: number; offset?: number } = {},
): Promise<RolloverRunListResponse> {
  return (await api.get('/api/rollover/runs', {
    params: { limit: params.limit ?? 20, offset: params.offset ?? 0 },
  })) as RolloverRunListResponse
}

/**
 * กระทบยอดรายชื่อสองปี — ใครหายจากปีก่อน / ใครเพิ่มมาในปีใหม่
 *
 * ⭐ ตอบข้อกำหนด "เด็กจบต้องค้นชื่อเจอ": ระบบ **บอกว่าใครหาย** แต่ **ไม่เดาสาเหตุ**
 *    (ย้ายออก / จบ / ตกหล่น) เพราะการเดาจะกลายเป็นข้อมูลผิดที่ไม่มีใครตรวจ
 * ⚠️ ยังไม่มีหน้าจอเรียกใช้ใน P4 — หน้าจอ "รายงานตามปี" อยู่ใน P6 (แผนหัวข้อ P6)
 */
export async function getReconciliation(
  fromYearId: number,
  toYearId: number,
): Promise<Reconciliation> {
  return (await api.get('/api/rollover/reconciliation', {
    params: { from_year_id: fromYearId, to_year_id: toYearId },
  })) as Reconciliation
}
