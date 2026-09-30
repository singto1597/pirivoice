/**
 * 🧪 R0 · `/app/more` **เป็น route จริง ไม่ใช่ catch-all**
 *
 * **ทำไมต้องมีเทสนี้ ทั้งที่ `routeMeta.spec.ts` ก็ snapshot route ครบ 31 ตัวแล้ว:**
 * `routeMeta.spec.ts` อ่าน `router.options.routes` ตรง ๆ ⇒ มันเห็น *ทุก* record ที่ประกาศไว้
 * รวมทั้งตัวที่ **ประกาศแล้วแต่ resolve ไม่ได้** (path ผิด, component import ตาย, ถูก redirect
 * ทับ) ⇒ เทสต์นั้นเขียวได้ทั้งที่ผู้ใช้กดแล้วพัง
 *
 * 🔴 **failure ที่เทสนี้กัน — แย่ที่สุดของ refactor ทั้งงาน:**
 * แถบล่างเป็น `RouterLink` ชี้ path ตรง ๆ · ถ้า `/app/more` **ไม่มี route จริง** มันจะตกไปที่
 * catch-all `/:pathMatch(.*)*` ซึ่ง **นำไปหน้า Login พร้อม `?redirect=/app/more`**
 * ⇒ **"กดเมนู 'เพิ่มเติม' แล้วออกจากระบบ"** — ผู้ใช้ไม่เห็น error ไม่มีข้อความอธิบาย
 * แค่หลุดไปหน้าล็อกอิน · และถ้าล็อกอินค้างอยู่ มันจะเด้งกลับมาที่เดิม *วนไม่จบ*
 *
 * ⚠️ **ทดสอบผ่าน `router.push()` จริง** (ไม่ใช่ `resolve()`) ด้วยเหตุผลเดียวกับ
 *    `redirectRoute.spec.ts`: `resolve()` **ไม่ตาม redirect record** ⇒ เทสต์ที่ใช้ `resolve()`
 *    ผ่านทั้งที่ของพัง · redirect ถูกใช้ตอน *นำทาง* เท่านั้น
 *
 * ⭐ **เทสต์ "ทุกแท็บต้อง resolve ได้" เป็นตัวที่คุ้มที่สุดในไฟล์นี้** — มันไม่ผูกกับ `more`
 *    แต่ครอบ **แท็บที่จะเพิ่มในอนาคต** ด้วย ⇒ ใครก็ตามที่เพิ่มแท็บที่ 6 แล้วลืม route
 *    จะแดงที่นี่ทันที ไม่ต้องรอผู้ใช้กดเจอเอง
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const auth = vi.hoisted(() => ({
  state: {
    authenticated: false,
    user: null as { must_change_password?: boolean } | null,
  },
}))

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({
    get isAuthenticated() {
      return auth.state.authenticated
    },
    get user() {
      return auth.state.user
    },
    get mustChangePassword() {
      return auth.state.user?.must_change_password ?? false
    },
    get isCouncilAuthority() {
      return false
    },
    hasPermission: () => false,
    loadMe: async () => {},
    logout: () => {},
  }),
}))

import router from '@/router'
import { REDIRECT_QUERY } from '@/router/redirect'
import { NAV_TABS, routeTitles } from '@/constants/nav'

/** นำทางจริงแล้วคืน route ที่จบ — redirect/guard ถูกใช้ครบเหมือนผู้ใช้กดเอง */
async function goto(path: string) {
  await router.push(path)
  return router.currentRoute.value
}

beforeEach(async () => {
  auth.state.authenticated = false
  auth.state.user = null
  // เริ่มทุกเทสต์จากหน้า public — ปลายทางของเทสต์ก่อนหน้าไม่ค้างมาทำให้ผลเพี้ยน
  await router.replace('/')
})

describe('🔴 `/app/more` ต้องเป็น route จริง', () => {
  it('M1: ยังไม่ล็อกอิน · เปิด `/app/more` → ไป login **พร้อมจำปลายทาง** (ไม่ใช่ตก catch-all เงียบ ๆ)', async () => {
    const route = await goto('/app/more')

    expect(route.name).toBe('login')
    // ⚠️ ข้อนี้แยก "route จริงที่ guard กัน" ออกจาก "catch-all" ไม่ได้ด้วยตัวมันเอง (ทั้งคู่ได้ค่านี้)
    //    ⇒ ตัวแยกจริงคือ M3 ด้านล่าง · ที่นี่ตรึงพฤติกรรมที่ผู้ใช้เห็นไว้เท่านั้น
    expect(route.query[REDIRECT_QUERY]).toBe('/app/more')
  })

  it('M2: ล็อกอินอยู่แล้ว · เปิด `/app/more` → ถึงหน้า "เพิ่มเติม" จริง', async () => {
    auth.state.authenticated = true
    auth.state.user = {}

    const route = await goto('/app/more')

    expect(route.name).toBe('more')
    expect(route.matched.some((r) => r.name === 'more')).toBe(true)
  })

  it('★ M3: `/app/more` **ไม่ใช่ catch-all** — record ที่ match ต้องไม่ใช่ `not-found`', () => {
    const resolved = router.resolve('/app/more')

    expect(resolved.name).toBe('more')
    expect(resolved.matched.some((r) => r.name === 'not-found')).toBe(false)
    expect(resolved.meta.requiresAuth).toBe(true)
  })

  it('★ M4: component ของหน้านี้ **โหลดได้จริง** — ไม่ใช่ typo ใน path ที่เพิ่งจะพังตอนผู้ใช้เปิด', async () => {
    // dynamic import เดียวกับที่ router ใช้ ⇒ จับ path ที่พิมพ์ผิด ซึ่ง `type-check` จับไม่ได้
    // เพราะ `component: () => import('@/views/More.vue')` เป็น string ที่ resolve ตอน runtime
    const mod = await import('@/views/More.vue')

    expect(mod.default).toBeTruthy()
  })
})

describe('🔴 ทุกแท็บในแถบล่างต้อง resolve เป็น route จริง (กัน "กดแท็บแล้วออกจากระบบ")', () => {
  it('★ T1: `NAV_TABS` ทุกตัวชี้ไป route ที่มีอยู่จริง — ไม่มีตัวไหนตก catch-all', () => {
    const broken = NAV_TABS.filter((tab) => {
      const resolved = router.resolve(tab.to)
      return resolved.name === 'not-found' || resolved.name === undefined
    }).map((tab) => `${tab.key} → ${tab.to} (ได้ "${String(router.resolve(tab.to).name)}")`)

    expect(broken).toEqual([])
  })

  it('T2: แท็บ "เพิ่มเติม" เป็นแท็บจริงในแถบล่าง (ไม่ใช่หน้าที่ไม่มีทางเข้า)', () => {
    const more = NAV_TABS.find((t) => t.key === 'more')

    expect(more).toBeDefined()
    expect(more?.to).toBe('/app/more')
    expect(more?.label).not.toMatch(/[A-Za-z]/)
  })

  it('T3: ชื่อหน้าของ `/app/more` เป็นไทย และ meta ตรงสัญญาของแท็บราก', () => {
    const meta = router.resolve('/app/more').meta

    expect(routeTitles['more']).toBeTruthy()
    expect(routeTitles['more']).not.toMatch(/^[A-Za-z]/)
    // แท็บราก: ไม่มีลูกศร ← · ไม่ซ่อนแถบล่าง (ไม่งั้นแท็บที่ active จะไฮไลต์ตัวเองไม่ได้)
    expect(meta.navTab).toBe('more')
    expect(meta.headerBack).toBe(false)
    expect(meta.navHidden).toBeUndefined()
    expect(meta.headerHidden).toBeUndefined()
  })
})
