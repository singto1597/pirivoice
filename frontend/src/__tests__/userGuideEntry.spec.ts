/**
 * 🧪 ทางเข้า "คู่มือการใช้งาน" (`/docs/`) จากในแอป
 *
 * **ทำไมต้องมีเทสนี้:** แถวนี้เป็นแถวเดียวในเมนูที่ปลายทาง **ไม่ใช่ route ของ SPA**
 * (เป็นไฟล์ static ของ VitePress ที่เสิร์ฟใต้ `/docs/`) ⇒ ถ้าใครเผลอเปลี่ยนไปใช้ `to`
 * หรือเอา `href` ไปใส่ `RouterLink` สิ่งที่เกิดขึ้นคือ:
 *   · `to: '/docs/'` → ไม่มี route นี้ ⇒ ตก catch-all ⇒ **กดแล้วเด้งออกจากระบบ**
 *     (ผู้ใช้เข้าใจว่า "คู่มือพัง" ไม่ใช่ "ลิงก์ผิด")
 *   · `RouterLink` + `href` → `href` กลายเป็น `[object Object]` หรือลิงก์ที่ resolver ไม่รู้จัก
 * และทั้งสองอาการ **ไม่ทำให้ type-check หรือเทสต์อื่นแดง** ถ้าไม่มีเทสต์นี้
 *
 * ⭐ สิ่งที่ยึด:
 *   1. ปลายทางเป็น path สัมพัทธ์ `/docs/` (ไม่ใช่ absolute URL) ⇒ เปิดต่อจากโดเมนที่ผู้ใช้อยู่
 *   2. เรนเดอร์เป็น `<a href>` จริง ไม่ใช่ `RouterLink`
 *   3. **ไม่มี `target="_blank"`** — เจ้าของระบบสั่งให้เปิดแท็บเดิม (เหตุผลเดียวกับ
 *      `SchoolSystemsCard` · ดู `schoolSystems.spec.ts`)
 *   4. **ไม่มีการกรองสิทธิ์** — คู่มือเปิดให้ทุกบทบาทอ่าน ⇒ ถ้ามีคนเติม `permission`
 *      นักเรียนจะไม่เห็นทางเข้าที่ตัวเองต้องใช้ และจะไม่มีอาการให้จับ
 *   5. ชื่อไอคอนมีอยู่จริงใน bootstrap-icons (คลาสพิมพ์ผิด = ไม่ขึ้นอะไรเลย ไม่ error)
 */
import { describe, expect, it } from 'vitest'
import { createRequire } from 'node:module'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import AppNavRow from '@/components/layout/AppNavRow.vue'
import { NAV_GROUPS } from '@/constants/nav'
import type { NavItem } from '@/constants/nav'

// ⚠️ ห้ามใช้ `import.meta.url` ภายใต้ jsdom (ไม่ใช่ URL ระนาบ file:) — บทเรียนจาก
//    `schoolSystems.spec.ts` / `appEmptyRow.spec.ts` · `createRequire` หาเองได้ทุก cwd
const ICON_CSS_ID = 'bootstrap-icons/font/bootstrap-icons.css'
function resolveIconCss(): string {
  for (const base of [process.cwd(), join(process.cwd(), 'frontend')]) {
    try {
      return createRequire(join(base, 'package.json')).resolve(ICON_CSS_ID)
    } catch {
      // ลองฐานถัดไป (เผื่อรัน vitest จาก root ของ monorepo)
    }
  }
  throw new Error(`ไม่พบ ${ICON_CSS_ID} — เทสต์นี้ต้องรันหลัง \`npm install\` ใน frontend/`)
}

const ICON_CSS = readFileSync(resolveIconCss(), 'utf8')

const general = NAV_GROUPS.find((g) => g.key === 'general')
const guide = general?.items.find((i) => i.key === 'user-guide')

/** router เปล่า ๆ — ใช้พิสูจน์ว่าแถว *ไม่ได้* พึ่ง RouterLink */
function stubRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', name: 'home', component: { template: '<div />' } },
      { path: '/docs/', name: 'docs-route', component: { template: '<div />' } },
    ],
  })
}

describe('ทางเข้า "คู่มือการใช้งาน" — ข้อมูลใน NAV_GROUPS', () => {
  it('อยู่ในกลุ่ม "ทั่วไป" และเป็นแถวที่กดได้', () => {
    expect(general).toBeDefined()
    expect(guide).toBeDefined()
    // กลุ่ม "ทั่วไป" โผล่ทั้งหน้า "เพิ่มเติม" และ sidebar เดสก์ท็อป ⇒ ทางเข้าเดียวครอบสองที่
    expect(guide?.label).toBe('คู่มือการใช้งาน')
    expect(guide?.icon).toBe('bi-book')
    expect((guide as { href?: string } | undefined)?.href).toBe('/docs/')
  })

  it('⭐ ใช้ path สัมพัทธ์ `/docs/` ไม่ใช่ absolute URL (ต้องเปิดต่อจากโดเมนที่ผู้ใช้อยู่)', () => {
    const href = (guide as { href?: string }).href ?? ''
    expect(href.startsWith('/')).toBe(true)
    // absolute URL จะพาออกจากโดเมนของโรงเรียนเสมอ = ผิดเมื่อย้ายโดเมน/ทดสอบ staging
    expect(href).not.toMatch(/^https?:/)
  })

  it('⭐ ไม่มีการกรองสิทธิ์ — ทุกบทบาทต้องเห็น (นักเรียนคือคนที่ต้องการคู่มือที่สุด)', () => {
    expect(guide?.permission).toBeUndefined()
    expect(guide?.anyPermission).toBeUndefined()
    expect(guide?.councilOnly).toBeUndefined()
    // ห้ามซ่อนจากเมนูด้วย — ถ้าซ่อน แถวนี้จะไม่มีทางเข้าเลย
    expect(guide?.hiddenFromMenu).toBeUndefined()
  })

  it('⭐ ชื่อไอคอนมีอยู่จริงใน bootstrap-icons (พิมพ์ผิด = มองไม่เห็น และไม่ error)', () => {
    expect(ICON_CSS).toContain(`.${guide?.icon}::before`)
  })

  it('ลำดับในกลุ่มทั่วไป: กิจกรรมของฉัน · คู่มือการทำงาน · คู่มือการใช้งาน', () => {
    // แถวที่เห็นจริง = ตัด `hiddenFromMenu` ออก (playbook เล่มย่อยทั้ง 6 ถูกซ่อน)
    const visible = (general?.items ?? []).filter((i) => !i.hiddenFromMenu).map((i) => i.key)
    expect(visible).toEqual(['my-activity', 'playbooks-all', 'user-guide'])
  })

  it('key ไม่ซ้ำกับทั้ง registry (key ถูกใช้เป็น v-for key และอ้างในเทสต์)', () => {
    const allKeys = NAV_GROUPS.flatMap((g) => g.items.map((i) => i.key))
    expect(allKeys.filter((k) => k === 'user-guide')).toHaveLength(1)
  })
})

describe('ทางเข้า "คู่มือการใช้งาน" — สิ่งที่เรนเดอร์ออกมา', () => {
  const router = stubRouter()

  it('⭐ เป็น `<a href="/docs/">` ธรรมดา ไม่ใช่ RouterLink', () => {
    const w = mount(AppNavRow, {
      props: { item: guide as NavItem },
      global: { plugins: [router] },
    })
    const a = w.find('a')
    expect(a.exists()).toBe(true)
    expect(a.attributes('href')).toBe('/docs/')
    // ถ้าวันหนึ่งมีคนเปลี่ยนไปใช้ `to` แล้ว router ไม่รู้จัก ⇒ href จะเป็น '/docs/'
    // เหมือนกัน แต่ของจริงคือตก catch-all · ข้อถัดไปจึงตรวจว่า route ไม่ได้ถูกใช้
    expect(w.findComponent({ name: 'RouterLink' }).exists()).toBe(false)
  })

  it('⭐ เปิดในแท็บเดิม — ไม่มี target="_blank" (บน PWA รู้สึกเหมือนถูกเตะออกจากแอป)', () => {
    const w = mount(AppNavRow, {
      props: { item: guide as NavItem },
      global: { plugins: [router] },
    })
    const a = w.find('a')
    expect(a.attributes('target')).toBeUndefined()
    expect(a.attributes('rel')).toBeUndefined()
  })

  it('แสดงชื่อป้ายเต็ม ไม่ถูกตัดคำ และมีลูกศรบอกว่ากดได้', () => {
    const w = mount(AppNavRow, {
      props: { item: guide as NavItem },
      global: { plugins: [router] },
    })
    expect(w.text()).toContain('คู่มือการใช้งาน')
    // ชื่อต้องสั้นพอให้อยู่ในหนึ่งบรรทัดบนจอ 360dp (`truncate`) —
    // เกิน ~16 ตัวอักษรเริ่มขึ้น "...ระบบ" ซึ่งผู้ใช้อ่านเป็นบั๊ก
    expect((guide?.label ?? '').length).toBeLessThanOrEqual(18)
    expect(w.find('.bi-chevron-right').exists()).toBe(true)
  })

  it('ไม่เรนเดอร์เป็น `<button>` และไม่ emit action ตอนกด', async () => {
    const w = mount(AppNavRow, {
      props: { item: guide as NavItem },
      global: { plugins: [router] },
    })
    expect(w.find('button').exists()).toBe(false)
    // ⚠️ jsdom โยน "Not implemented: navigation to another Document" ทุกครั้งที่คลิก `<a>`
    //    จริง (ไม่มีผลกับผลเทสต์ แต่กลบ log ของเทสต์อื่น) ⇒ กัน default ที่ระดับ element
    const el = w.find('a').element
    el.addEventListener('click', (e) => e.preventDefault())
    await w.find('a').trigger('click')
    expect(w.emitted('action')).toBeUndefined()
  })

  it('แถวที่ใช้ `to` ยังเป็น RouterLink ตามเดิม (การเพิ่ม href ไม่กลืนของเดิม)', () => {
    const w = mount(AppNavRow, {
      props: { item: { key: 'home', label: 'หน้าแรก', icon: 'bi-house-door', to: { name: 'home' } } },
      global: { plugins: [router] },
    })
    expect(w.findComponent({ name: 'RouterLink' }).exists()).toBe(true)
    expect(w.find('a').attributes('href')).toBe('/')
  })

  it('แถว action (ออกจากระบบ) ยังเป็น `<button>` และ emit action ตามเดิม', async () => {
    const w = mount(AppNavRow, {
      props: { item: { key: 'logout', label: 'ออกจากระบบ', icon: 'bi-box-arrow-right', action: 'logout' } },
      global: { plugins: [router] },
    })
    expect(w.find('button').exists()).toBe(true)
    await w.find('button').trigger('click')
    expect(w.emitted('action')).toEqual([['logout']])
  })
})
