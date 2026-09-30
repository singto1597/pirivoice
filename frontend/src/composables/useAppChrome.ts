// 🪟 อ่าน `route.meta` ที่เดียวแล้วบอก shell ว่าต้องวาดอะไร
//
// ก่อนหน้านี้ `MainLayout.vue` ตัดสินใจเรื่องหัวแถบด้วยการเทียบ `route.path` กับสตริง
// ตรง ๆ (รวมถึง special case `route.path !== '/app/home'` ที่ปิดเลเยอร์กระจกทั้งหน้า)
// ⇒ ย้ายมาที่นี่ แล้ว **หน้าที่ต้องการอะไรให้ประกาศที่ `meta` ของตัวเอง**

import { computed } from 'vue'
import type { RouteLocationRaw } from 'vue-router'
import { useRoute, useRouter } from 'vue-router'
import { NAV_TABS, routeTitles } from '@/constants/nav'
import type { FabKey, NavKey, SegmentGroupId } from '@/router/meta'

export function useAppChrome() {
  const route = useRoute()
  const router = useRouter()

  /** ชื่อบนหัวแถบ — `meta.headerTitle` ชนะ `routeTitles` เสมอ */
  const title = computed(
    () => route.meta.headerTitle ?? routeTitles[(route.name as string) || ''] ?? 'PIRIvoice',
  )

  const navTab = computed<NavKey | null>(() => route.meta.navTab ?? null)

  /**
   * ปลายทางของปุ่ม ←
   *
   * - `headerBack: false` → ไม่มีปุ่ม (หน้าราก)
   * - `headerBack: <target>` → ไปที่นั่น
   * - ไม่ประกาศ → ใช้รากของแท็บที่หน้านี้สังกัด (และไม่มีปุ่มถ้าเป็นแท็บรากอยู่แล้ว)
   *
   * 🔴 **ไม่ใช้ `router.back()`** — ทางเข้าหลักของหน้ารายละเอียดคือ push notification
   *    หรือการสแกน QR ซึ่ง **ไม่มี in-app history** ⇒ `back()` จะเตะผู้ใช้ออกจากแอป
   */
  const backTarget = computed<RouteLocationRaw | null>(() => {
    const declared = route.meta.headerBack
    if (declared === false) return null
    if (declared) return declared

    const tab = navTab.value
    if (!tab || tab === 'home' || tab === 'more') return null
    return NAV_TABS.find((t) => t.key === tab)?.to ?? null
  })

  const showBack = computed(() => backTarget.value !== null)
  const navVisible = computed(() => !route.meta.navHidden)
  const headerVisible = computed(() => !route.meta.headerHidden)
  const segmentGroup = computed<SegmentGroupId | null>(() => route.meta.segmentGroup ?? null)
  const fab = computed<FabKey | null>(() => route.meta.fab ?? null)

  function goBack(): void {
    if (backTarget.value) router.push(backTarget.value)
  }

  return {
    title,
    navTab,
    backTarget,
    showBack,
    navVisible,
    headerVisible,
    segmentGroup,
    fab,
    goBack,
  }
}
