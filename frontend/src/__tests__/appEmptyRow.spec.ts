/**
 * 🧪 `AppEmptyRow` — แถวเดียวที่แทน "บล็อกนี้ว่าง" ในหน้าแรก
 *
 * **ทำไมต้อง mount จริง (ต่างจากเทสต์ตารางความจริงใน `homeEmptyCollapse.spec.ts`):**
 * ที่นั่นตรวจ *การตัดสินใจ* (ยุบหรือไม่) ที่นี่ตรวจ *สิ่งที่เรนเดอร์ออกมา* — และสองอย่างนี้
 * พลาดคนละแบบ · แถวนี้ดูเหมือน `div` ธรรมดาแต่มีรายละเอียดที่ **หายแล้วเงียบทั้งคู่**:
 *   1. **ชื่อไอคอน `bi-*` ที่พิมพ์ผิด ⇒ ไม่ขึ้นอะไรเลย และไม่ error**
 *      (คลาสไม่มีอยู่ = ไม่มี `::before`) ⇒ ต้องเทียบกับ CSS ของไลบรารีจริง
 *   2. **ลิงก์ที่ `to` ไม่ตรงกับ route จริง ⇒ กดแล้วไม่มีอะไรเกิดขึ้น** (หรือตก catch-all
 *      แล้วเด้งออกจากระบบ — บทเรียน `moreRoute.spec.ts`) ⇒ ต้อง resolve ผ่าน router จริง
 *
 * 🔴 **ลิงก์ต้องเป็น `RouterLink` จริง ไม่ใช่ `<a href>` เปล่า ๆ** — ปลายทางที่หน้าแรกส่งมา
 *    เป็น *ออบเจกต์* (`{ name: 'received-issues' }`) ไม่ใช่ path ⇒ ถ้ามีใครเปลี่ยนไปใช้
 *    `<a>` (ดูเหมือนง่ายกว่า) `href` จะกลายเป็น `[object Object]` ซึ่ง **ยังกดได้ปกติ**
 *    แต่พาไปหน้าที่ไม่มีอยู่ · เทสต์ข้อ "href ตรงกับ path จริง" จับเคสนี้
 *
 * ⚠️ เทสต์นี้ใช้ **router ความจำของตัวเอง (memory router)** ไม่ใช่ `@/router` ของแอป
 *    เพราะแอปมี navigation guard ที่ต้องล็อกอิน ⇒ mount จะพาไปหน้า login แทนที่จะเห็นแถว
 *    ส่วนคำถาม "ชื่อ route ที่หน้าแรกส่งมา **มีอยู่จริงในตาราง route ของแอปไหม**"
 *    ถูกปิดด้วยเทสต์ข้อสุดท้ายที่ resolve กับ `@/router` ตัวจริง (ซึ่งไม่มี guard)
 */
import { describe, expect, it } from 'vitest'
import { existsSync, readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { join } from 'node:path'
import { mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import type { RouteLocationRaw } from 'vue-router'
import AppEmptyRow from '@/components/ui/AppEmptyRow.vue'
import appRouter from '@/router'

/** ไอคอนทุกตัวที่ `Home.vue` ส่งให้แถวนี้ — ต้องมีจริงในไลบรารี (พิมพ์ผิด = มองไม่เห็น) */
const ICONS_USED_IN_HOME = ['bi-check2-circle', 'bi-megaphone', 'bi-stars']

const ICON_CSS_ID = 'bootstrap-icons/font/bootstrap-icons.css'

/**
 * ⚠️ **ห้ามใช้ `import.meta.url`** — ภายใต้ jsdom ไม่ใช่ URL ระนาบ `file:` ⇒
 *    `fileURLToPath()` โยน `TypeError: The URL must be of scheme file`
 *    (กับดักเดิมที่ `schoolSystems.spec.ts` บันทึกไว้) · ใช้ `createRequire` ให้ Node หาเอง
 */
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

const ROUTES = [
  { path: '/', name: 'home', component: { template: '<div />' } },
  { path: '/received', name: 'received-issues', component: { template: '<div />' } },
  { path: '/new', name: 'new-issue', component: { template: '<div />' } },
]

/** mount กับ router จริงขนาดจิ๋ว — ต้อง `isReady()` ก่อน ไม่งั้น `RouterLink` ยัง resolve ไม่ได้ */
async function mountRow(props: {
  title: string
  icon?: string
  tone?: 'ok' | 'neutral'
  to?: RouteLocationRaw
  actionLabel?: string
  context?: string
}) {
  const router = createRouter({ history: createMemoryHistory(), routes: ROUTES })
  await router.push('/')
  await router.isReady()
  const wrapper = mount(AppEmptyRow, { props, global: { plugins: [router] } })
  return { wrapper, router }
}

describe('AppEmptyRow — เนื้อหาของแถว', () => {
  it('ขึ้นข้อความที่ส่งมา และไม่มีอะไรเกินนั้น', async () => {
    const { wrapper } = await mountRow({ title: 'คิวรายงานว่าง' })
    expect(wrapper.text()).toContain('คิวรายงานว่าง')
  })

  it('ไอคอนถูกซ่อนจากโปรแกรมอ่านหน้าจอ (ข้อความข้าง ๆ คือตัวสื่อความหมาย)', async () => {
    const { wrapper } = await mountRow({ title: 'ไม่มีเรื่องค้างรอคุณ', tone: 'ok' })
    const icon = wrapper.find('i')
    expect(icon.attributes('aria-hidden')).toBe('true')
  })

  it('⭐ ไอคอนทุกตัวที่หน้าแรกใช้ มีอยู่จริงใน bootstrap-icons', () => {
    for (const name of ICONS_USED_IN_HOME) {
      expect(name).toMatch(/^bi-[a-z0-9-]+$/)
      expect(ICON_CSS).toContain(`.${name}::before`)
    }
  })

  it('ไอคอนที่ส่งมาถูกใส่เป็นคลาสจริง ไม่ใช่ชื่อลอย ๆ', async () => {
    const { wrapper } = await mountRow({ title: 'ยังไม่เคยแจ้งเรื่อง', icon: 'bi-megaphone' })
    expect(wrapper.find('i').classes()).toContain('bi-megaphone')
  })

  it('ค่าเริ่มต้นคือ `bi-check2-circle` (ใช้เมื่อไม่ได้ระบุ)', async () => {
    const { wrapper } = await mountRow({ title: 'คิวรายงานว่าง' })
    expect(wrapper.find('i').classes()).toContain('bi-check2-circle')
  })

  it('⭐ พื้นที่กดของแถวต้องถึง 44dp (`min-h-11`)', async () => {
    // แถวนี้เตี้ยกว่า empty state เดิมมาก — ถ้าไม่มี `min-h-11` จะเหลือ ~28dp
    // ซึ่งต่ำกว่าเกณฑ์แตะของโปรเจกต์ (กฎเดียวกับที่ `AppButton.size="sm"` ต้องถ่างด้วย `after:`)
    const { wrapper } = await mountRow({ title: 'คิวรายงานว่าง' })
    expect(wrapper.find('div').classes()).toContain('min-h-11')
  })
})

describe('AppEmptyRow — สี (tone)', () => {
  it('`tone="ok"` → เขียว = "ตรวจแล้วเรียบร้อย"', async () => {
    const { wrapper } = await mountRow({ title: 'ไม่มีเรื่องค้างรอคุณ', tone: 'ok' })
    expect(wrapper.find('i').classes()).toContain('text-ok')
  })

  it('⭐ ไม่ส่ง `tone` → เทา **ไม่ใช่เขียว** ("ยังไม่ได้ทำ X" ไม่ใช่ความสำเร็จ)', async () => {
    // ถ้าค่าเริ่มต้นกลายเป็นเขียว "ยังไม่เคยแจ้งเรื่อง" จะขึ้นเครื่องหมายถูกสีเขียว
    // ซึ่งอ่านตรงข้ามกับความหมาย
    const { wrapper } = await mountRow({ title: 'ยังไม่เคยแจ้งเรื่อง' })
    expect(wrapper.find('i').classes()).toContain('text-ink-3')
    expect(wrapper.find('i').classes()).not.toContain('text-ok')
  })
})

describe('AppEmptyRow — ลิงก์ทางออก', () => {
  it('ไม่มี `to` → ไม่มีลิงก์เลย (ความว่างที่ไม่มีอะไรให้ทำต่อ)', async () => {
    const { wrapper } = await mountRow({ title: 'คิวรายงานว่าง' })
    expect(wrapper.find('a').exists()).toBe(false)
  })

  it('⭐ มี `to` → ได้ `<a>` ที่ `href` เป็น path จริง (ไม่ใช่ `[object Object]`)', async () => {
    const { wrapper } = await mountRow({
      title: 'ไม่มีเรื่องค้างรอคุณ',
      to: { name: 'received-issues' },
      actionLabel: 'คิวทั้งหมด',
    })
    const link = wrapper.find('a')
    expect(link.exists()).toBe(true)
    expect(link.attributes('href')).toBe('/received')
    expect(link.text()).toContain('คิวทั้งหมด')
  })

  it('`actionLabel` ขึ้นบนลิงก์ ไม่ใช่บนตัวแถว', async () => {
    const { wrapper } = await mountRow({
      title: 'ยังไม่เคยแจ้งเรื่อง',
      to: { name: 'new-issue' },
      actionLabel: 'แจ้งเรื่อง',
    })
    expect(wrapper.find('a').text()).toContain('แจ้งเรื่อง')
    expect(wrapper.find('p').text()).toBe('ยังไม่เคยแจ้งเรื่อง')
  })

  it('⭐ `context` ถูกซ่อนด้วย `sr-only` (บอกปลายทางโดยไม่เพิ่มคำบนจอ)', async () => {
    // ลิงก์อย่าง "คิวทั้งหมด" ที่ลอยเดี่ยว อ่านนอกบริบทแล้วไม่รู้ว่าของบล็อกไหน
    const { wrapper } = await mountRow({
      title: 'ไม่มีเรื่องค้างรอคุณ',
      to: { name: 'received-issues' },
      actionLabel: 'คิวทั้งหมด',
      context: 'รอฉันตอบ',
    })
    const sr = wrapper.find('a .sr-only')
    expect(sr.exists()).toBe(true)
    expect(sr.text()).toContain('รอฉันตอบ')
  })

  it('ไม่ส่ง `context` → ไม่มี `sr-only` เปล่า ๆ ค้างอยู่ใน DOM', async () => {
    const { wrapper } = await mountRow({
      title: 'ยังไม่เคยแจ้งเรื่อง',
      to: { name: 'new-issue' },
      actionLabel: 'แจ้งเรื่อง',
    })
    expect(wrapper.find('a .sr-only').exists()).toBe(false)
  })
})

describe('⭐ wiring ใน Home.vue — คุณสมบัติที่เทสต์ระดับคอมโพเนนต์มองไม่เห็น', () => {
  /**
   * อ่าน **ซอร์สของ `Home.vue`** มาตรวจ *คุณสมบัติ* (ไม่ใช่ markup เป๊ะ ๆ)
   *
   * ⚠️ **ทำไมต้องเป็นเทสต์แบบนี้:** เทสต์ข้างบน mount `AppEmptyRow` เอง ⇒ มันพิสูจน์ว่า
   *    "แถวเรนเดอร์ถูกถ้าได้รับ prop ที่ถูก" แต่ **ไม่ได้พิสูจน์ว่าหน้าแรกส่ง prop ที่ถูก** —
   *    พิมพ์ชื่อไอคอนผิดใน `Home.vue` หรือลบ `:to` ออก จะ **เขียวทั้งไฟล์** และผู้ใช้เห็น
   *    ไอคอนหาย/ลิงก์หายโดยไม่มี error ที่ไหนเลย (`bi-` ที่ไม่มีอยู่ = ไม่มี `::before`)
   *    ⇒ ตรวจเท่าที่ตรวจได้จากซอร์ส แล้วที่เหลือ (หน้าตาจริง) ปล่อยให้การวัดด้วย Playwright
   *      บน staging เป็นคนยืนยัน
   */
  const HOME_VUE = readFileSync(
    (() => {
      for (const base of [process.cwd(), join(process.cwd(), 'frontend')]) {
        const p = join(base, 'src/views/Home.vue')
        if (existsSync(p)) return p
      }
      throw new Error('ไม่พบ src/views/Home.vue')
    })(),
    'utf8',
  )

  /** ทุก `<AppEmptyRow … />` ในไฟล์ — attribute ในการใช้จริงไม่มี `>` อยู่ในค่า */
  const rows = [...HOME_VUE.matchAll(/<AppEmptyRow\b[^>]*\/>/g)].map((m) => m[0])

  it('มีแถวเดียวต่อบล็อกที่ตกลงกันไว้ (ถ้าจะเพิ่ม/ลด ต้องตั้งใจแก้เทสต์นี้ด้วย)', () => {
    // บล็อกที่เจ้าของระบบเลือกให้ยุบ: รอฉันตอบ · สรุปเรื่องของฉัน · สถิติของฉัน · คิวรายงาน
    // (แดชบอร์ด **ซ่อน** ไม่ใช่ยุบ ⇒ ไม่มีแถว — ดู `dashboardBlockState()`)
    expect(rows).toHaveLength(4)
  })

  it('⭐ ไอคอนทุกตัวที่ `Home.vue` ส่งมา มีอยู่จริงใน bootstrap-icons', () => {
    const icons = rows.map((r) => /\bicon="([^"]+)"/.exec(r)?.[1]).filter(Boolean)
    expect(icons).toHaveLength(4)
    for (const icon of icons) {
      expect(icon).toMatch(/^bi-[a-z0-9-]+$/)
      expect(ICON_CSS).toContain(`.${icon}::before`)
    }
  })

  it('ทุกแถวมี `title` (ข้อความที่บอกว่า "ว่างเพราะอะไร")', () => {
    for (const r of rows) expect(r).toMatch(/\btitle="/)
  })

  /**
   * แถวไหน **ต้อง** มีทางออก และแถวไหน **ต้องไม่มี** — ล็อกรายตัว ไม่ใช่ล็อกเฉพาะ "แถวที่บังเอิญมี"
   *
   * ⚠️ เทสต์แบบ "แถวที่มี `:to` ต้องมี `action-label` ด้วย" **ไม่พอ** — ถ้ามีคนลบ `:to`
   *    ออกจากแถวใดแถวหนึ่ง เงื่อนไขนั้นยังจริงกับแถวที่เหลือ ⇒ เขียวทั้งที่ผู้ใช้เสียทางออกไปแล้ว
   *    (เจอจริงตอนรัน mutation: ลบ `:to` ออกจาก "ยังไม่เคยแจ้งเรื่อง" แล้วเทสต์ยังผ่าน)
   */
  const MUST_HAVE_EXIT: Record<string, string> = {
    // ทางออกของ "รอฉันตอบ" — ปุ่มที่หัวการ์ดเดิมถูกถอดไปพร้อมหัวการ์ด
    ไม่มีเรื่องค้างรอคุณ: 'คิวทั้งหมด',
    // ★ คำเชิญ**เดียวในแอป**สำหรับคนที่ยังไม่เคยแจ้ง ⇒ ห้ามหาย (ย้ายจากปุ่มกลางการ์ดมาที่นี่)
    ยังไม่เคยแจ้งเรื่อง: 'แจ้งเรื่อง',
  }
  const MUST_NOT_HAVE_EXIT = [
    // คิวว่าง = ไม่เหลืออะไรให้ไปจัดการ ⇒ ลิงก์ไปหน้าคิวว่างแย่กว่าไม่มีลิงก์
    'คิวรายงานว่าง',
    // ความว่างที่ไม่มีอะไรให้ทำต่อ (สถิติจะเริ่มนับเองเมื่อมีเรื่องแรก)
    'ยังไม่มีสถิติในช่วงนี้',
  ]

  // ⚠️ แถวที่หาไม่เจอจะได้ค่า `''` ⇒ ข้อ assertion ล่างฟ้องพร้อมข้อความ "received string: ''"
  //    และเทสต์ข้อถัดไป ("ทุกแถวถูกจัดอยู่ในสองกลุ่มครบ") ฟ้องชื่อที่ขาดตรง ๆ อยู่แล้ว
  function rowWithTitle(title: string): string {
    return rows.find((r) => new RegExp(`\\btitle="${title}"`).test(r)) ?? ''
  }

  it('⭐ แถวที่ต้องมีทางออก มีทั้ง `:to` และ `action-label` ตรงตามที่ตกลง', () => {
    for (const [title, actionLabel] of Object.entries(MUST_HAVE_EXIT)) {
      const row = rowWithTitle(title)
      expect(row).not.toBe('') // แถวต้องมีอยู่จริง (ชื่อครบถูกล็อกไว้ในเทสต์ข้อถัดไป)
      expect(row).toContain(':to=')
      expect(row).toContain(`action-label="${actionLabel}"`)
    }
  })

  it('⭐ แถวที่ไม่ต้องมีทางออก ต้องไม่มี `:to` เลย', () => {
    for (const title of MUST_NOT_HAVE_EXIT) {
      const row = rowWithTitle(title)
      expect(row).not.toBe('') // ⚠️ จำเป็น: `''` จะผ่าน `not.toContain` ไปด้วย
      expect(row).not.toContain(':to=')
    }
  })

  it('ทุกแถวถูกจัดอยู่ในสองกลุ่มข้างบนครบ (ไม่มีแถวที่ไม่มีใครตรวจ)', () => {
    const known = [...Object.keys(MUST_HAVE_EXIT), ...MUST_NOT_HAVE_EXIT].sort()
    const actual = rows
      .map((r) => /\btitle="([^"]+)"/.exec(r)?.[1])
      .filter((t): t is string => Boolean(t))
      .sort()
    expect(actual).toEqual(known)
  })
})

describe('⭐ ปลายทางที่หน้าแรกส่งมา ต้องมีอยู่จริงในตาราง route ของแอป', () => {
  it('`received-issues` และ `new-issue` resolve ได้', () => {
    // 🔴 ชื่อ route ที่พิมพ์ผิดจะ **ไม่ error** — `RouterLink` จะเรนเดอร์ `<a>` ที่ไม่มี href
    //    หรือตก catch-all ⇒ "กดแล้วไม่มีอะไรเกิดขึ้น" ซึ่งเทสต์ระดับคอมโพเนนต์ (ที่ใช้ router
    //    จำลองของตัวเอง) มองไม่เห็น · ที่นี่จึงต้อง resolve กับ **router ตัวจริงของแอป**
    for (const name of ['received-issues', 'new-issue', 'my-issues', 'board-reports']) {
      const r = appRouter.resolve({ name })
      expect(r.name).toBe(name)
      expect(r.path.startsWith('/')).toBe(true)
    }
  })
})
