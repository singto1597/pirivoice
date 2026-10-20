// 🗺️ แผนที่เมนูทั้งแอป — **ที่เดียวที่ประกาศว่า "มีอะไรในเมนูบ้าง"**
//
// ⚠️ ไฟล์นี้เป็น **ข้อมูลนิ่ง ไม่ผูกกับ Pinia** โดยเจตนา ⇒ เทสต์ได้โดยไม่ต้อง mount store
//    การกรองสิทธิ์ (hasPermission / isCouncilAuthority) อยู่ที่ `composables/useNavItems.ts`
//
// ⚠️ ป้ายบน bottom nav ต้อง **ไทยล้วน** (เดิมมี "Boards" ปนอยู่ ซึ่งอ่านไม่ออกว่าคืออะไร)
//    และ **ห้ามใช้ `uppercase`/`tracking-*` กับข้อความไทย** — ภาษาไทยไม่มีตัวพิมพ์ใหญ่
//    และการเพิ่ม letter-spacing ทำให้สระ/วรรณยุกต์ลอยห่างจากพยัญชนะ

import type { RouteLocationRaw } from 'vue-router'
import type { NotificationGroup } from '@/types/notification'
import type { NavKey } from '@/router/meta'
import { PLAYBOOKS } from '@/types/playbook'

interface NavItemBase {
  /** id นิ่ง — ใช้เป็น `key` และอ้างในเทสต์ (**ไม่ใช่ path** เพราะ path เปลี่ยนได้) */
  key: string
  label: string
  /** bootstrap-icons base name เช่น 'bi-house-door' (ไม่รวม -fill) */
  icon: string
  /** ไอคอนตอน active — ไม่ระบุ = ใช้ `icon` */
  iconActive?: string
  /** กลุ่ม badge ใน notifications store */
  badgeGroup?: NotificationGroup
  /** แสดงเฉพาะเมื่อมี permission นี้ */
  permission?: string
  /** แสดงเฉพาะเมื่อมีอย่างน้อยหนึ่งในนี้ */
  anyPermission?: string[]
  /** แสดงเฉพาะผู้มีอำนาจระดับสภา */
  councilOnly?: boolean
  /** ซ่อนจากเมนู แต่ยังใช้ resolve ชื่อ/ไอคอนได้ */
  hiddenFromMenu?: boolean
}

/**
 * หนึ่งรายการเมนู — เป็น **discriminated union** ระหว่าง "ไปหน้าใหม่" กับ "ทำ action"
 * ⇒ type-check บังคับว่าต้องมีอย่างใดอย่างหนึ่ง (ไม่มีทางได้แถวที่กดแล้วเงียบ)
 */
export type NavItem = NavItemBase &
  (
    | { to: RouteLocationRaw; action?: never }
    | { action: 'logout'; to?: never }
  )

/** กลุ่มเมนู — ใช้ทั้ง sidebar และหน้า "เพิ่มเติม" (ชุดเดียวกัน) */
export interface NavGroup {
  key: string
  /** หัวกลุ่ม — ไทยล้วน ใช้เป็น sticky header */
  label: string
  icon?: string
  items: NavItem[]
}

/** แท็บล่าง — `key` ต้องเป็น `NavKey` และ `to` ต้องเป็น path ของแท็บนั้น */
export interface NavTab extends NavItemBase {
  key: NavKey
  to: string
  /** ไอคอนตอน active (filled) */
  iconActive: string
}

/**
 * 5 แท็บล่าง — **ลำดับในอาร์เรย์คือลำดับบนแถบ**
 *
 * "แจ้งเรื่อง" **ไม่ใช่แท็บ** — เป็น FAB (ดู `FabKey`) เพราะการแจ้งเรื่องเป็นการ *กระทำ*
 * ไม่ใช่ *สถานที่* และการเป็นแท็บทำให้เมนูมี 6 ช่องซึ่งแน่นเกินไปบนจอ 360dp
 */
export const NAV_TABS: NavTab[] = [
  { key: 'home', label: 'หน้าแรก', to: '/app/home', icon: 'bi-house-door', iconActive: 'bi-house-door-fill' },
  { key: 'issues', label: 'เรื่อง', to: '/app/issues/mine', icon: 'bi-file-earmark-text', iconActive: 'bi-file-earmark-text-fill' },
  { key: 'boards', label: 'บอร์ด', to: '/app/boards', icon: 'bi-columns-gap', iconActive: 'bi-columns-gap' },
  { key: 'events', label: 'กิจกรรม', to: '/app/events', icon: 'bi-calendar-event', iconActive: 'bi-calendar-event-fill' },
  { key: 'more', label: 'เพิ่มเติม', to: '/app/more', icon: 'bi-grid-3x3-gap', iconActive: 'bi-grid-3x3-gap-fill' },
]

/**
 * ตัวเลือกหนึ่งตัวในแถบ segment ที่ shell วาดให้
 *
 * ⚠️ `to` เป็น `{ name }` เท่านั้น (ไม่ใช่ `RouteLocationRaw` เต็มรูป) โดยเจตนา —
 *    `useNavItems` ต้องเทียบ `segment.to.name === route.name` เพื่อรู้ว่า segment ไหน active
 *    ⇒ ถ้าเปิดเป็น union เต็มรูป จะต้องแกะ type ทุกครั้ง (`typeof s.to === 'object' && 'name' in s.to && …`)
 *    ซึ่งทั้งยาวและพลาดง่าย · segment ทุกตัวในแอปนี้อยู่กลุ่มเดียวกันจึงไม่ต้องส่ง params อยู่แล้ว
 */
export interface SegmentOption {
  key: string
  label: string
  to: { name: string }
  /** กลุ่ม badge ที่ segment นี้แสดง — ไม่ระบุ = ไม่มี badge */
  badgeGroup?: NotificationGroup
}

/** segment ของแท็บ "เรื่อง" — ทุกตัวมี badgeGroup เสมอ (ต่างจาก "สมาชิก") */
export interface IssueSegmentOption extends SegmentOption {
  badgeGroup: NotificationGroup
}

/**
 * segment ของแท็บ "เรื่อง" — ใช้ทั้งแถบ segment และการคิด badge ของแท็บ
 *
 * 🔴 ประกาศเป็น **non-empty tuple** (`[T, ...T[]]`) ไม่ใช่ `T[]` เพราะ `useNavItems`
 *    อ่าน `ISSUE_SEGMENTS[0]` เป็นค่า default ของ badge และ `noUncheckedIndexedAccess`
 *    ทำให้ `T[]` คืน `T | undefined` ⇒ ต้องใส่ `!` หรือ `?.` กลบทุกจุด
 *    · tuple บอกกับ type system ตรง ๆ ว่า "อาร์เรย์นี้ว่างไม่ได้" ซึ่งเป็นความจริง
 */
export const ISSUE_SEGMENTS: readonly [IssueSegmentOption, ...IssueSegmentOption[]] = [
  { key: 'mine', label: 'ของฉัน', to: { name: 'my-issues' }, badgeGroup: 'issue_mine' },
  { key: 'received', label: 'ที่รับผิดชอบ', to: { name: 'received-issues' }, badgeGroup: 'issue_received' },
]

/** segment ของกลุ่ม "สมาชิก" */
export const MEMBER_SEGMENTS: SegmentOption[] = [
  { key: 'students', label: 'นักเรียน', to: { name: 'students' } },
  { key: 'staff', label: 'เจ้าหน้าที่', to: { name: 'users' } },
]

/**
 * segment ของแท็บ "กิจกรรม" (รอบ 4)
 *
 * 🔴 **มีสองตัว ไม่ใช่สาม — "ของฉัน" ถูกถอดออกโดยเจตนา เพราะสร้างไม่ได้จริง**
 *    แผน R4.2 เขียนไว้สามตัว (ทั้งหมด / ของฉัน / จัดการ) แต่ตรวจแล้วพบว่า
 *    **ไม่มีแหล่งข้อมูลรองรับ "ของฉัน" เลย**:
 *      · `GET /api/events/public` รับแค่ `scope` (upcoming/past/all) · `category` · `limit` · `offset`
 *      · `event_service._PUBLIC_SCOPES` มีสามค่าเดียวกันนี้ และ service เขียนเตือนไว้เองว่า
 *        **"ไม่กรองด้วยสิทธิ์ — นักเรียนทุกคนเห็นกิจกรรมเหมือนกันหมด"** (`user_id` ถูกส่งเข้าไป
 *        เพื่อติด `my_registration_status` ให้ *แต่ละแถว* เท่านั้น ไม่ใช่เพื่อกรอง)
 *      · ไม่มี endpoint "กิจกรรมที่ฉันสมัคร" ทั้งแบบรายการและแบบนับ
 *    ⇒ ทางเลือกที่มีคือ (ก) กรองฝั่ง client เฉพาะหน้าที่โหลดมา — **ห้าม** เพราะพอมี pagination
 *       มันจะขึ้น "ยังไม่สมัครกิจกรรมไหนเลย" ทั้งที่ของจริงอยู่หน้า 2 = UI ที่โกหกผู้ใช้
 *       (ข) เพิ่ม scope ใหม่ที่ backend — เกินขอบเขต R4.2 และชนกับดักที่ service เขียนเตือนไว้
 *       เรื่องจำนวน placeholder ระหว่าง `count_sql` กับ `rows_sql`
 *    ⇒ **เลือกถอดออกแล้วบอกเหตุ** · สิ่งที่ผู้ใช้ยังได้อยู่คือ `my_registration_status`
 *      บนการ์ดทุกใบ ("ได้ที่นั่ง" / "คิวสำรอง") ซึ่งตอบคำถามนั้นได้โดยไม่ต้องมีตัวกรอง
 *      · ถ้าจะทำจริงต้องเพิ่ม scope `mine` ที่ backend พร้อมเทสต์ — แยกเป็นงานต่างหาก
 *
 * ⚠️ "จัดการ" ต้อง **กรองด้วยสิทธิ์ที่ `useNavItems`** (ไม่ใช่ที่ route) — เหตุผลเดียวกับ
 *    `received-issues` (R0.3.3): `students.permissions` เป็น snapshot ที่ไม่มีอะไร re-sync
 *    ⇒ gate ที่ route จะดีดผู้ใช้ที่มีสิทธิ์จริงกลับแบบเงียบ ๆ
 *    ✅ และ `AppTabBar` ซ่อนตัวเองเมื่อเหลือตัวเลือกเดียว ⇒ นักเรียนทั่วไปไม่เห็นแถบนี้เลย
 */
export const EVENT_SEGMENTS: SegmentOption[] = [
  { key: 'public', label: 'ทั้งหมด', to: { name: 'events' } },
  { key: 'manage', label: 'จัดการ', to: { name: 'event-management' } },
]

/** แถวคู่มือการทำงาน — สร้างจากข้อมูลจริง ไม่ hardcode จำนวน (มี 6 เล่ม) */
const playbookItems: NavItem[] = [
  { key: 'playbooks-all', label: 'คู่มือการทำงาน', icon: 'bi-journal-bookmark', to: { name: 'playbooks' } },
  ...PLAYBOOKS.map((pb) => ({
    key: `playbook-${pb.id}`,
    label: pb.title,
    icon: 'bi-journal-text',
    to: { name: 'playbook-reader', params: { id: pb.id } },
    hiddenFromMenu: true,
  })),
]

/**
 * กลุ่มเมนูทั้งหมด — sidebar และหน้า "เพิ่มเติม" อ่านชุดเดียวกัน
 *
 * ⚠️ ลำดับกลุ่ม = ลำดับที่ผู้ใช้เห็น · กลุ่มที่ไม่มีแถวเหลือหลังกรองสิทธิ์จะถูกซ่อนทั้งกลุ่ม
 */
export const NAV_GROUPS: NavGroup[] = [
  {
    key: 'admin',
    label: 'ผู้ดูแล',
    icon: 'bi-shield-check',
    items: [
      { key: 'dashboard', label: 'แดชบอร์ด', icon: 'bi-grid-1x2', to: { name: 'dashboard' }, permission: 'VIEW_DASHBOARD' },
      // 🏷️ ป้ายแถวเมนู = ชื่อหน้า = `routeTitles['board-reports']` = "จัดการรายงาน"
      //    (เดิมแถวนี้เขียน "ตรวจรายงาน" ขณะที่หัวหน้าเขียน "จัดการรายงาน" ⇒ ปลายทางเดียวมีสองชื่อ)
      { key: 'board-reports', label: 'จัดการรายงาน', icon: 'bi-flag', to: { name: 'board-reports' }, badgeGroup: 'report', councilOnly: true },
      // 📅 **ซ่อนจากเมนูตั้งแต่รอบ 4** — ปลายทางนี้กลายเป็น *segment "จัดการ"* ของแท็บ "กิจกรรม"
      //    ⇒ ถ้าปล่อยแถวไว้ จะมีสองทางเข้าไปที่เดียวกัน ซึ่งขัดหลัก "ทางเข้าเดียวต่อปลายทาง"
      //    ⚠️ ซ่อนแถว ไม่ใช่ลบ `permission` — `isVisible()` ยังต้องกรองอยู่ เพราะ
      //       `useNavItems.segmentsOf('events')` อ่านสิทธิ์ตัวเดียวกันนี้เพื่อตัดสินว่าโชว์ segment ไหม
      { key: 'event-management', label: 'จัดการกิจกรรม', icon: 'bi-calendar-plus', to: { name: 'event-management' }, permission: 'MANAGE_EVENTS', hiddenFromMenu: true },
      {
        // 👥 **แถวเดียวของ "สมาชิก"** — ปลายทาง `students` ซึ่งมี `segmentGroup: 'members'`
        //    ⇒ สลับ นักเรียน / เจ้าหน้าที่ ได้ในหน้าเดียว โดยไม่ต้องมีเมนู 2 แถว
        //    (เดิมมี 3 แถวไปที่เดียวกัน: "จัดการสมาชิก" + "นักเรียน" + "นำเข้า Excel"
        //     ซึ่งเป็นตัวอย่างของปัญหาที่ audit ฟ้องว่าแอป "เยอะเกินไป" ตรง ๆ)
        key: 'members',
        label: 'สมาชิก',
        icon: 'bi-people',
        to: { name: 'students' },
        permission: 'MANAGE_STUDENTS',
      },
      // ซ่อนจากเมนู — เป็น *segment* ของหน้า "สมาชิก" กับ *FAB* ของหน้านั้น ไม่ใช่ทางเข้าแยก
      { key: 'users', label: 'เจ้าหน้าที่', icon: 'bi-person-gear', to: { name: 'users' }, permission: 'MANAGE_STUDENTS', hiddenFromMenu: true },
      { key: 'import-students', label: 'นำเข้านักเรียน', icon: 'bi-file-earmark-arrow-up', to: { name: 'import-students' }, permission: 'MANAGE_STUDENTS', hiddenFromMenu: true },
    ],
  },
  {
    key: 'school',
    label: 'โรงเรียน',
    icon: 'bi-buildings',
    items: [
      { key: 'announcements', label: 'จัดการประกาศ', icon: 'bi-megaphone', to: { name: 'announcements' }, permission: 'MANAGE_ANNOUNCEMENTS' },
      // ⚠️ ลำดับ: ปีการศึกษามาก่อนภาคเรียน — **ใหญ่ → เล็ก** (1 ปีมี 2 ภาค) และตรงกับ
      //    ลำดับที่ต้องทำจริงตอนขึ้นปีใหม่ (สร้างปี → นำเข้ารายชื่อ → ตั้งเป็นปัจจุบัน)
      //    ⇒ สองแถวนี้อยู่ติดกันโดยเจตนา; ความหมายต่างกันคนละชั้น — ดู `docs/glossary.md` §1.1
      { key: 'academic-years', label: 'ปีการศึกษา', icon: 'bi-mortarboard', to: { name: 'academic-years' }, permission: 'MANAGE_SETTINGS' },
      {
        // 🔄 อยู่ติดกับ "ปีการศึกษา" โดยเจตนา — เป็นขั้นถัดไปของงานเดียวกัน
        //    (สร้างปีใหม่ → เลื่อนชั้น → นำเข้ารายชื่อ → ตั้งตำแหน่ง) ไม่ใช่เรื่องของ "สมาชิก"
        //    ⚠️ สิทธิ์เป็น **`councilOnly` + `MANAGE_STUDENTS` คู่กัน** ซึ่งต่างจากแถวอื่นในแอป:
        //       · `MANAGE_STUDENTS` เดี่ยว → ครู/ประธานระดับเห็นแถว แล้ว **403** จาก backend
        //         (`rollover_service._gate` บังคับโหมดจัดการระดับโรงเรียน ⇒ ต้องมี `is_admin`)
        //       · `councilOnly` เดี่ยว → `council_member` เห็นแถว แล้วก็ **403** (ไม่มี MANAGE_STUDENTS)
        //       ⇒ ประกาศคู่กันจึงได้ผลตรงกับประตูจริงทุกบทบาทพอดี (ดู `__tests__/navRegistry.spec.ts`
        //         gate แบบ `{ council: true, permission: … }`) — อย่าถอดตัวใดตัวหนึ่งออก
        key: 'promote-students',
        label: 'เลื่อนชั้นนักเรียน',
        icon: 'bi-arrow-up-circle',
        to: { name: 'promote-students' },
        councilOnly: true,
        permission: 'MANAGE_STUDENTS',
      },
      { key: 'academic-terms', label: 'ภาคเรียน', icon: 'bi-calendar3-range', to: { name: 'academic-terms' }, permission: 'MANAGE_SETTINGS' },
      // ⚠️ ไม่มีแถว "รายชื่อนักเรียน" ที่นี่ — ถูกรวมเข้าแถว "สมาชิก" ในกลุ่มผู้ดูแลแล้ว (R1)
      { key: 'audit-logs', label: 'บันทึกการใช้งาน', icon: 'bi-clock-history', to: { name: 'audit-logs' }, permission: 'VIEW_AUDIT_LOG' },
    ],
  },
  {
    key: 'general',
    label: 'ทั่วไป',
    icon: 'bi-compass',
    items: [
      { key: 'my-activity', label: 'กิจกรรมของฉัน', icon: 'bi-activity', to: { name: 'my-activity' } },
      { key: 'notifications', label: 'การแจ้งเตือน', icon: 'bi-bell', to: { name: 'notifications' }, hiddenFromMenu: true },
      ...playbookItems,
    ],
  },
  {
    key: 'account',
    label: 'บัญชี',
    icon: 'bi-person-circle',
    items: [
      { key: 'profile', label: 'โปรไฟล์', icon: 'bi-person-circle', to: { name: 'profile' } },
      // ⚙️ ตั้งค่า — ทางเข้าเดียวของ `/app/settings` (R3.3)
      //    🔴 แถวนี้ **และ** ปุ่ม "แก้ไขโปรไฟล์" ในหน้าโปรไฟล์ (Profile.vue) **และ** แถว
      //       "เปลี่ยนรหัสผ่าน" ในหน้าตั้งค่า คือของสามชิ้นที่ *แทน* dropdown `⋮` เดิม
      //       ถอดชิ้นใดชิ้นหนึ่งออก = มี route ที่ไม่มีทางเข้าเลย (ดูคอมเมนต์หัว Profile.vue)
      { key: 'settings', label: 'ตั้งค่า', icon: 'bi-sliders', to: { name: 'settings' } },
      { key: 'profile-edit', label: 'แก้ไขโปรไฟล์', icon: 'bi-person-badge', to: { name: 'profile-edit' }, hiddenFromMenu: true },
      { key: 'profile-password', label: 'เปลี่ยนรหัสผ่าน', icon: 'bi-key', to: { name: 'profile-password' }, hiddenFromMenu: true },
      { key: 'logout', label: 'ออกจากระบบ', icon: 'bi-box-arrow-right', action: 'logout' },
    ],
  },
]

/**
 * ชื่อหน้าสำหรับหัวแถบ — ย้ายมาจาก `MainLayout.vue` (เดิมเป็น object ในไฟล์ layout)
 * ⚠️ หน้าที่ไม่มีชื่อในนี้จะได้ชื่อแอปแทน ⇒ **เพิ่ม route ใหม่แล้วต้องเพิ่มที่นี่ด้วย**
 */
export const routeTitles: Record<string, string> = {
  home: 'หน้าแรก',
  more: 'เพิ่มเติม',
  dashboard: 'แดชบอร์ด',
  profile: 'โปรไฟล์',
  settings: 'ตั้งค่า',
  'my-activity': 'กิจกรรมของฉัน',
  'profile-edit': 'แก้ไขโปรไฟล์',
  'profile-password': 'เปลี่ยนรหัสผ่าน',
  'new-issue': 'แจ้งเรื่อง',
  'my-issues': 'เรื่องของฉัน',
  'received-issues': 'เรื่องที่รับผิดชอบ',
  'issue-detail': 'รายละเอียดเรื่อง',
  'issue-edit': 'แก้ไขเรื่อง',
  boards: 'บอร์ด',
  'board-detail': 'บอร์ด',
  // 💡 ฟอร์มเสนอไอเดีย — หน้าเต็ม ไม่ใช่ modal อีกแล้ว (รอบ 4)
  //    ตั้งชื่อตาม *การกระทำ* ("เสนอไอเดีย") ไม่ใช่ *ชนิดของ object* ("สร้างบอร์ด")
  //    เพราะผู้ใช้คิดว่า "ฉันอยากเสนออะไรสักอย่าง" ไม่ได้คิดว่า "ฉันอยากสร้างบอร์ด"
  'board-new': 'เสนอไอเดีย',
  'board-reports': 'จัดการรายงาน',
  events: 'กิจกรรม',
  'event-detail': 'รายละเอียดกิจกรรม',
  'event-management': 'จัดการกิจกรรม',
  // ✍️ สร้าง/แก้ไข/รายชื่อผู้สมัคร — **หน้าเต็มหน้า** ไม่ใช่ modal อีกแล้ว (รอบ 4)
  //    ถ้าไม่เพิ่มที่นี่ แถบหัวจะขึ้น "PIRIvoice" เฉย ๆ ซึ่งดูเหมือนหลุดออกจากระบบกิจกรรม
  'event-create': 'สร้างกิจกรรม',
  'event-edit': 'แก้ไขกิจกรรม',
  'event-registrations': 'รายชื่อผู้สมัคร',
  'event-check-in': 'สแกนเช็คอิน',
  playbooks: 'คู่มือการทำงาน',
  'playbook-reader': 'อ่านหนังสือ',
  notifications: 'การแจ้งเตือน',
  // ⚠️ **ชื่อหัวแถบ = ชื่อ "สิ่งที่กำลังดูอยู่" ไม่ใช่ชื่อกลุ่มเมนู** — ทั้งคู่ของ segment
  //    ตั้งชื่อตาม *ลิสต์* ของตัวเอง (`นักเรียน` / `เจ้าหน้าที่`) ตรงกับคู่ `issues`
  //    ที่ใช้ `ของฉัน` / `ที่รับผิดชอบ` มาตั้งแต่ต้น
  //    ⇒ แถวเมนูที่พามาที่นี่ชื่อ "สมาชิก" (ชื่อ *กลุ่ม*) ซึ่งไม่ขัดกันเพราะ
  //      ผู้ใช้ไม่เห็นเมนูกับหัวแถบพร้อมกัน (คนละจอ)
  //    · และจำเป็นเมื่อแถบ segment **หดเหลือตัวเดียว** (ไม่มีสิทธิ์รับเรื่อง/จัดการสมาชิก)
  //      ⇒ ถ้าหัวแถบเป็นชื่อกลุ่มเฉย ๆ จะไม่มีอะไรบอกว่ากำลังดูลิสต์ไหน
  users: 'เจ้าหน้าที่',
  students: 'รายชื่อนักเรียน',
  'import-students': 'นำเข้านักเรียน',
  announcements: 'จัดการประกาศ',
  'academic-terms': 'ภาคเรียน',
  'academic-years': 'ปีการศึกษา',
  // ⚠️ ต้องตรงกับ `label` ของแถวเมนู — ปลายทางเดียวมีสองชื่อทำให้ผู้ใช้คิดว่าคนละหน้า
  //    (บทเรียนเดียวกับ `board-reports` ที่เคยเป็น "ตรวจรายงาน" บนเมนู / "จัดการรายงาน" บนหัวแถบ)
  'promote-students': 'เลื่อนชั้นนักเรียน',
  // ⚠️ สองอันนี้ `navHidden` (ไม่โชว์ในเมนู) แต่ **ต้องมี routeTitles** — ไม่งั้น `<h1>`
  //    บนหัวหน้าจะว่าง แล้วผู้ใช้ไม่รู้ว่ากำลังทำอะไรอยู่
  'academic-year-new': 'เพิ่มปีการศึกษา',
  'academic-year-edit': 'แก้ไขปีการศึกษา',
  'audit-logs': 'บันทึกการใช้งาน',
}
