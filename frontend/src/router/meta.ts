// 🧭 สัญญา `route.meta` ของทั้งแอป — **ที่เดียวที่ประกาศ** แล้วให้ shell อ่าน
//
// เหตุผลที่ต้องมีไฟล์นี้: ก่อนหน้านี้ MainLayout.vue ตัดสินใจเรื่องหัวแถบ/เมนู/
// ปุ่มย้อน ด้วยการเทียบ `route.path` กับสตริงตรง ๆ กระจายอยู่หลายที่ ⇒ เพิ่มหน้าใหม่
// แล้วลืมแก้สักที่ = หน้าใหม่ได้หัวแถบผิดโดยไม่มีใครรู้
//
// ⚠️ **ห้ามประกาศ `navTab` / `fab` ที่ route แม่ `/app`** — `route.meta` เป็นการ merge
//    ของ *ทุก* record ที่ match ⇒ ค่าที่ใส่ที่แม่จะรั่วลงทุกหน้าลูก
//    ที่ route แม่ใส่ได้มีแค่ `requiresAuth: true`

import type { RouteLocationRaw } from 'vue-router'

/** แท็บใน bottom nav — 5 ค่าเท่านั้น ("เพิ่มเติม" เป็นแท็บที่ 5 ไม่ใช่ bottom sheet) */
export type NavKey = 'home' | 'issues' | 'boards' | 'events' | 'more'

/** กลุ่ม segment — route ที่อยู่กลุ่มเดียวกันจะได้แถบ segment ร่วมกันจาก shell */
export type SegmentGroupId = 'issues' | 'members' | 'events'

/**
 * FAB ที่ shell วาดให้ (ไม่ประกาศ = หน้าไหนก็ได้ FAB ของตัวเอง)
 *
 * ⚠️ ทุกตัวต้องชี้ไป **หน้าเต็ม** ได้ — `AppFab` เรนเดอร์เป็น `RouterLink` เท่านั้น
 *    ไม่มีช่องทางส่ง action กลับขึ้นไปสั่งเปิด modal ที่อื่นในแอป
 *    (นี่คือเหตุผลที่ `QuickSuggestionModal` ต้องกลายเป็นหน้า `board-new` ก่อน
 *     จึงจะเพิ่ม `board` เข้ามาที่นี่ได้ — skills #16 บังคับทางเดียวกันอยู่แล้ว)
 */
export type FabKey = 'issue' | 'event' | 'member' | 'board'

export interface AppRouteMeta {
  // ── เดิม (ห้ามเปลี่ยนความหมาย) ──────────────────────────────────────
  requiresAuth?: boolean
  requiresPermission?: string
  requiresCouncil?: boolean

  // ── chrome ใหม่ (shell อ่านที่เดียว) ────────────────────────────────
  /** แท็บที่ต้องไฮไลต์ — ไม่ระบุ = ไม่มีแท็บไหน active */
  navTab?: NavKey
  /** true = ซ่อน bottom nav (ฟอร์ม / สแกนเนอร์ / นำเข้า) — ต้อง unmount ไม่ใช่ซ่อนด้วย CSS */
  navHidden?: boolean
  /**
   * ปลายทางของปุ่ม ← — เป็น **route target ไม่ใช่ `'history'`**
   * เพราะทางเข้าหลักของหน้ารายละเอียดคือ push notification / การสแกน QR
   * ซึ่ง **ไม่มี in-app history** ⇒ `router.back()` จะเตะผู้ใช้ออกจากแอป
   * `false` = หน้าราก ไม่ต้องมีลูกศร
   */
  headerBack?: RouteLocationRaw | false
  /** ทับชื่อหัวแถบ (ไม่ระบุ = ใช้ `routeTitles[route.name]`) */
  headerTitle?: string
  /** ซ่อนหัวแถบทั้งแถบ (สแกนเนอร์เต็มจอ) — ต้องมีปุ่มปิดที่มองเห็นได้เสมอ */
  headerHidden?: boolean
  /** สมาชิกของกลุ่ม segment */
  segmentGroup?: SegmentGroupId
  /** FAB ที่ shell วาด */
  fab?: FabKey
}

declare module 'vue-router' {
  // eslint-disable-next-line @typescript-eslint/no-empty-object-type
  interface RouteMeta extends AppRouteMeta {}
}
