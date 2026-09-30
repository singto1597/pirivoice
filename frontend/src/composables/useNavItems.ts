// 🧭 แหล่งเดียวของเมนูทั้งแอป — bottom nav, sidebar และหน้า "เพิ่มเติม" อ่านจากที่นี่
//
// เดิม `MainLayout.vue` มี `menuItems` + `menuBadge(path)` + `isActive(path)` อยู่ในไฟล์เดียว
// ซึ่งพอเพิ่มหน้าใหม่ต้องแก้ 3 ที่ให้ตรงกัน ⇒ ย้ายมาไว้ที่นี่ที่เดียว
//
// ⚠️ การกรองสิทธิ์อยู่ **ที่นี่** ไม่ใช่ที่ route guard — `students.permissions`
//    เป็น snapshot column ที่ไม่มีอะไร re-sync ⇒ ถ้าไป gate ที่ route ผู้ใช้ที่มีสิทธิ์จริง
//    แต่ snapshot ตกหล่นจะถูกดีดกลับแบบเงียบ ๆ (ดู `docs/skills.md`)

import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import Swal from 'sweetalert2'
import { useAuthStore } from '@/stores/auth'
import { useNotificationsStore } from '@/stores/notifications'
import { NAV_GROUPS, NAV_TABS, ISSUE_SEGMENTS, MEMBER_SEGMENTS } from '@/constants/nav'
import type { NavGroup, NavItem, NavTab, SegmentOption } from '@/constants/nav'
import type { NavKey, SegmentGroupId } from '@/router/meta'

/** เพดานเลข badge — เท่าเดิมกับที่ MainLayout ใช้อยู่ */
export const BADGE_CAP = 99

export function useNavItems() {
  const authStore = useAuthStore()
  const notificationsStore = useNotificationsStore()
  const route = useRoute()
  const router = useRouter()

  /** แถวนี้ควรแสดงกับผู้ใช้คนนี้ไหม */
  function isVisible(item: NavItem): boolean {
    if (item.councilOnly && !authStore.isCouncilAuthority) return false
    if (item.permission && !authStore.hasPermission(item.permission)) return false
    if (item.anyPermission?.length && !item.anyPermission.some((p) => authStore.hasPermission(p))) {
      return false
    }
    return true
  }

  /** เลข badge ของแถวนี้ (0 = ไม่แสดง) */
  function badgeOf(item: NavItem): number {
    if (!item.badgeGroup) return 0
    return notificationsStore.counts[item.badgeGroup] || 0
  }

  const activeTab = computed<NavKey | null>(() => route.meta.navTab ?? null)

  /**
   * badge ของแท็บ "เรื่อง"
   *
   * 🚨 **ห้ามบวก `issue_mine + issue_received`** — จะได้เลขที่ผู้ใช้อ่านไม่ออก
   *    (และมักเป็นผลรวมที่ไม่มีทางตรงกับจำนวนเรื่องจริงในหน้าไหนเลย)
   *    ⇒ ใช้ยอดของ segment ที่กำลังเปิดอยู่ ถ้าไม่ได้อยู่แท็บนี้ก็ใช้ segment เริ่มต้น
   */
  const issueTabBadge = computed(() => {
    const activeSegment = ISSUE_SEGMENTS.find((s) => s.to.name === route.name)
    const group = activeSegment?.badgeGroup ?? ISSUE_SEGMENTS[0].badgeGroup
    return notificationsStore.counts[group] || 0
  })

  const tabs = computed<NavTab[]>(() =>
    NAV_TABS.map((tab) =>
      tab.key === 'issues' ? ({ ...tab, badgeGroup: undefined } as NavTab) : tab,
    ),
  )

  /** เลขที่ควรแสดงบนแท็บ (แยกจาก `badgeOf` เพราะแท็บ "เรื่อง" มีตรรกะของตัวเอง) */
  function tabBadge(tab: NavTab): number {
    if (tab.key === 'issues') return issueTabBadge.value
    if (tab.key === 'boards') return notificationsStore.counts.board || 0
    if (tab.key === 'events') return notificationsStore.counts.event || 0
    if (tab.key === 'more') {
      // "เพิ่มเติม" ต้องเห็นยอดรวมได้ เพราะของที่ต้องจัดการซ่อนอยู่ข้างใน
      // หักกลุ่มที่โชว์บนแท็บอื่นแล้วออก เพื่อไม่ให้นับซ้ำจนผู้ใช้สับสน
      const shown = issueTabBadge.value + (notificationsStore.counts.board || 0) + (notificationsStore.counts.event || 0)
      return Math.max(0, (notificationsStore.total || 0) - shown)
    }
    return 0
  }

  /** กลุ่มทั้งหมดหลังกรองสิทธิ์ — **กลุ่มที่ไม่มีแถวเหลือจะถูกตัดออกทั้งกลุ่ม** */
  const groups = computed<NavGroup[]>(() =>
    NAV_GROUPS.map((g) => ({ ...g, items: g.items.filter(isVisible) })).filter(
      (g) => g.items.length > 0,
    ),
  )

  /** กลุ่มที่พร้อมวาดเป็นเมนู (ตัด `hiddenFromMenu` ออก) */
  const menuGroups = computed<NavGroup[]>(() =>
    groups.value
      .map((g) => ({ ...g, items: g.items.filter((i) => !i.hiddenFromMenu) }))
      .filter((g) => g.items.length > 0),
  )

  /** segment ที่ผู้ใช้มีสิทธิ์เห็น — ใช้ทั้งแถบ segment และการซ่อนแถบเมื่อเหลือตัวเดียว */
  function segmentsOf(group: SegmentGroupId): readonly SegmentOption[] {
    if (group === 'issues') {
      // ⚠️ กรองด้วยสิทธิ์ *ที่เมนู* ไม่ใช่ที่ route (ดูคอมเมนต์หัวไฟล์)
      return authStore.hasPermission('RECEIVE_ISSUES') ? ISSUE_SEGMENTS : ISSUE_SEGMENTS.slice(0, 1)
    }
    return MEMBER_SEGMENTS.filter(() => authStore.hasPermission('MANAGE_STUDENTS'))
  }

  /** ป้าย "99+" — ที่เดียวที่ตัดสินรูปแบบ */
  function badgeLabel(n: number): string {
    return n > BADGE_CAP ? `${BADGE_CAP}+` : String(n)
  }

  /** แถวนี้เป็นหน้าปัจจุบันอยู่ไหม */
  function isActive(item: NavItem): boolean {
    if (!item.to) return false
    const target = router.resolve(item.to)
    // หน้าที่มี `navTab` ให้ตัดสินด้วยแท็บก่อน ⇒ หน้าย่อย (เช่น issue-detail)
    // สว่างที่แท็บแม่ ไม่ใช่ที่แถวของตัวเอง
    return route.path === target.path || route.path.startsWith(`${target.path}/`)
  }

  /** ออกจากระบบ — ย้ายมาจาก `MainLayout.vue` เพราะทั้ง sidebar และหน้า More ต้องเรียกได้ */
  function logout(): void {
    Swal.fire({
      icon: 'question',
      title: 'ออกจากระบบ?',
      showCancelButton: true,
      confirmButtonText: 'ออกจากระบบ',
      cancelButtonText: 'ยกเลิก',
    }).then((result) => {
      if (result.isConfirmed) {
        authStore.logout()
        router.push({ name: 'login' })
      }
    })
  }

  return {
    tabs,
    groups,
    menuGroups,
    activeTab,
    badgeOf,
    tabBadge,
    badgeLabel,
    segmentsOf,
    isActive,
    isVisible,
    logout,
  }
}
