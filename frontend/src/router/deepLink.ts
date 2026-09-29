/**
 * 🔗 "กด notification แล้วไปไหน" — **ที่เดียวที่ตัดสิน** ทั้งในแอพและจาก push (A4)
 *
 * ⚠️ **ทำไมต้องแยกออกมาเป็นโมดูล ไม่เขียนใน `NotificationCenter.vue`:**
 *   การตัดสินนี้ถูกทำ **สองที่คนละภาษา** —
 *     1. ในแอพ  → `NotificationCenter.vue` เรียกฟังก์ชันนี้
 *     2. จาก push → `backend/services/push_service.py::_deep_link_url()` ใส่ `data.url`
 *        ที่ `sw.js` เอาไปเปิด
 *   ⇒ ถ้าสองที่ตอบไม่ตรงกัน ผู้ใช้จะเจอ **สองพฤติกรรมจาก notification อันเดียวกัน**:
 *     กดในแอปไปที่หนึ่ง กดจาก push ไปอีกที่หนึ่ง — ซึ่งหาสาเหตุยากมาก เพราะแยกกันดู
 *     ทั้งสองทาง "ถูก" ทั้งคู่
 *   ⇒ ตรรกะจึงต้องอยู่ในไฟล์ที่ **อ่านออกว่าเป็นสัญญา** ไม่ใช่ฝังใน `go()` ของ SFC
 *     (เดิมซ่อนอยู่ที่นั่น และคอมเมนต์ฝั่ง backend ต้องชี้มาที่ไฟล์ `.vue` ซึ่งเปราะ)
 *
 * 📌 **ฝั่ง backend ล็อกลำดับไว้ด้วยเทสต์ `test_T21a`–`test_T21g`** — ที่นี่ล็อกด้วย
 *   `deepLink.spec.ts` ตารางเดียวกัน ⇒ **แก้ข้างหนึ่งต้องแก้ทั้งสอง** และตารางเทสต์
 *   คือที่ที่จะฟ้องเมื่อมีคนลืม
 */

import type { NotificationGroup } from '@/types/notification'

/** ฟิลด์ขั้นต่ำที่ใช้ตัดสิน — `NotificationItem` มีครบอยู่แล้วโดยโครงสร้าง */
export interface DeepLinkSource {
  group_type: NotificationGroup
  type: string
  entity_type: string | null
  entity_id: number | null
  board_id: number | null
}

/**
 * ปลายทางที่ต้องไป — `null` = **ไม่ต้องไปไหน** (อยู่ที่รายการแจ้งเตือนต่อ)
 *
 * ⚠️ `null` กับ `{ name: 'notifications' }` ให้ผลเหมือนกันในทางปฏิบัติ แต่ `null`
 *   สื่อเจตนาที่ถูกกว่า: "ไม่มีปลายทางเฉพาะ" ไม่ใช่ "ปลายทางคือหน้านี้" ⇒ ผู้เรียก
 *   ไม่ต้อง `push` ทับเส้นทางปัจจุบัน (ซึ่งจะสร้าง history entry ที่กดย้อนกลับแล้ว
 *   ดูเหมือนค้าง) และยังเรียก `markOne()` ต่อได้ตามพฤติกรรมเดิม
 */
export type DeepLinkTarget =
  | { name: 'board-reports' }
  | { name: 'board-detail'; params: { id: number } }
  | { name: 'issue-detail'; params: { id: number } }
  | null

/**
 * แปลง notification → ปลายทาง — **ฟังก์ชันบริสุทธิ์** (เทสง่าย ไม่ต้องมี router/DB)
 *
 * ลำดับ 4 ขั้น — **ลำดับมีความหมาย ห้ามสลับ** (ตรงกับ `_deep_link_url()` ฝั่ง backend):
 *
 *   1. กลุ่ม `report` + ชนิด `report_new` → **คิวรายงาน** (`/app/boards/reports`)
 *      ★ ต้องมาก่อนข้อ 3 เพราะ notification นี้พก `board_id` มาด้วย — ถ้าตกไปข้อ 3
 *      จะพาสภาฯ ไปที่ตัวบอร์ด แทนที่จะพาไป "คิวที่ต้องลงมือ" ซึ่งเป็นเหตุผลที่แจ้ง
 *      และเหตุผลเดียวกันนี้ทำให้ `report_new` **ไม่ควร**มีปุ่มให้ผู้แจ้งทั่วไปกด
 *      (notification ชนิดนี้ส่งถึงสภาฯ เท่านั้น)
 *   2. กลุ่ม `report` ชนิดอื่น ที่มี `board_id` → **บอร์ดนั้น**
 *      (`report_actioned` ส่งถึง *ผู้แจ้ง* ซึ่งอาจเป็นนักเรียน — ต้องไปดูบอร์ด
 *       ไม่ใช่คิวของสภา)
 *   3. `entity_type === 'issue'` + `entity_id` → **หน้ารายละเอียดเรื่อง**
 *   4. มี `board_id` → **หน้าบอร์ด**
 *
 * ไม่เข้าเงื่อนไขใด → `null` (อยู่ที่รายการแจ้งเตือน ซึ่งเป็นที่ที่ผู้ใช้กดมา
 * และเป็นที่เดียวที่ยัง "ต่อได้" — ปลอดภัยเสมอ)
 *
 * ⚠️ **ห้ามปล่อย `entity_id` เป็น `null` ลงใน path** — `entity_type === 'issue'`
 *   ที่ `entity_id` เป็น NULL ต้องตกไปข้อ 4 ไม่ใช่สร้าง `/app/issues/null`
 *   (ฝั่ง backend กันด้วยเทสต์ `test_T21d` — ที่นี่กันด้วย `entity_id != null`)
 */
export function deepLinkTarget(n: DeepLinkSource): DeepLinkTarget {
  if (n.group_type === 'report') {
    if (n.type === 'report_new') return { name: 'board-reports' }
    if (n.board_id != null) return { name: 'board-detail', params: { id: n.board_id } }
    return null
  }

  if (n.entity_type === 'issue' && n.entity_id != null) {
    return { name: 'issue-detail', params: { id: n.entity_id } }
  }

  if (n.board_id != null) {
    return { name: 'board-detail', params: { id: n.board_id } }
  }

  return null
}
