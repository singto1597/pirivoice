/**
 * 🧪 เมนูลัด "ระบบอื่นของโรงเรียน" (หน้าแรก)
 *
 * **ทำไมต้องมีเทสนี้:** การ์ดนี้เป็น **ทางออกจากแอป** ⇒ พังแล้วพังเงียบที่สุดในบรรดา
 * ฟีเจอร์ทั้งหมด — ไม่มี API ให้ 500 ไม่มี state ให้ undefined ไม่มี error ให้เห็น
 * มีแค่ *ลิงก์ที่กดแล้วไปผิดที่* หรือ *การ์ดที่ขึ้นแต่กดไม่ได้* ซึ่งเทสเดิมทั้งชุด
 * (ที่ทดสอบ service/constant อื่น) จับไม่ได้เลย
 *
 * ⭐ **สิ่งที่เทสนี้ยึด (เรียงตามความสำคัญ):**
 *   1. **ลำดับ `ess` ต้องอยู่แรก** — เจ้าของระบบกำหนดว่าเด็กเข้า "ระบบดูแลช่วยเหลือ
 *      นักเรียน" เป็นอันดับ 1 (ระบบอื่นของโรงเรียนอ้างอิงจากระบบนี้) ⇒ ห้ามมีใคร
 *      เรียงใหม่ตามตัวอักษรหรือตามความยาวชื่อ
 *   2. **URL ต้องเป็น absolute + https + โดเมนที่ถูก** — ไม่ใช่ path ในแอปเรา
 *      และไม่ใช่ `http://` (เบราว์เซอร์จะเตือน "ไม่ปลอดภัย") · ตรวจ `hostname` จริง
 *      ผ่าน `new URL()` ไม่ใช่ `startsWith` (ซึ่งพลาด `https://evil.com/?x=ess.sesa37.go.th`)
 *   3. **ชื่อไอคอนต้องมีอยู่จริงใน bootstrap-icons** — `bi-` ที่พิมพ์ผิดจะ **ไม่ขึ้นอะไรเลย
 *      และไม่ error** (คลาสไม่มีอยู่ = ไม่มี `::before`) ⇒ ต้องเทียบกับ CSS ของไลบรารีจริง
 *   4. **ห้ามมี `target="_blank"`** — เจ้าของระบบสั่งว่าให้เปิดในแท็บเดิม เพราะตอน
 *      ติดตั้งเป็น PWA แล้วกดลิงก์ที่มี `_blank` แอปจะเปิดหน้าต่างใหม่ที่หลุดออกจาก
 *      ตัวแอป · นี่เป็น *การตัดสินใจเชิงผลิตภัณฑ์* ที่คนมาทีหลังมีแนวโน้ม "แก้กลับ"
 *      ด้วยความเคยชิน (ลิงก์นอกมักใส่ `_blank` กันจนเป็นนิสัย) ⇒ ต้องมีเทสต์กันไว้
 *      และ `href` ว่างคือลิงก์ที่กดแล้วไม่มีอะไรเกิดขึ้น ซึ่ง **มองไม่เห็นจาก UI**
 *
 * ⚠️ เทสนี้อ่าน `bootstrap-icons.css` จาก `node_modules` จริง เพื่อไม่ให้รายชื่อไอคอน
 *    ที่เราจำได้กลายเป็นสมมติฐาน — เพิ่มไอคอนใหม่ที่ไม่มีในไลบรารีแล้วเทสจะฟ้องทันที
 *
 * ⚠️ `SCHOOL_SYSTEMS[0]` / `links[i]` ต้องมี `!` เพราะ tsconfig เปิด
 *    `noUncheckedIndexedAccess` (แบบเดียวกับ `eventForm.spec.ts`) — ปลอดภัยเพราะ
 *    เทสต์ข้อ "มี 2 ระบบ" ล็อกจำนวนสมาชิกไว้แล้ว และการล็อกลำดับ/จำนวนคือสิ่งที่เทสนี้ทำ
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { join } from 'node:path'
import { mount } from '@vue/test-utils'
import { EXTERNAL_NOTICE, SCHOOL_SYSTEMS } from '@/constants/schoolSystems'
import SchoolSystemsCard from '@/components/SchoolSystemsCard.vue'

/**
 * ⚠️ **ห้ามใช้ `import.meta.url` หาไฟล์ในเทสต์นี้** — ภายใต้ jsdom มันไม่ใช่ URL
 *    ระนาบ `file:` ⇒ `new URL(..., import.meta.url)` แล้ว `fileURLToPath()` จะโยน
 *    `TypeError: The URL must be of scheme file` (เจอจริงตอนเขียนเทสนี้)
 *    ใช้ `createRequire(...).resolve()` ให้ Node หาเอง ซึ่งถูกต้องทุก cwd
 */
const ICON_CSS_ID = 'bootstrap-icons/font/bootstrap-icons.css'
function resolveIconCss(): string {
  for (const base of [process.cwd(), join(process.cwd(), 'frontend')]) {
    try {
      return createRequire(join(base, 'package.json')).resolve(ICON_CSS_ID)
    } catch {
      // ลองฐานถัดไป (เผื่อรัน vitest จาก root ของ monorepo แทนที่จะเป็น frontend/)
    }
  }
  throw new Error(`ไม่พบ ${ICON_CSS_ID} — เทสต์นี้ต้องรันหลัง \`npm install\` ใน frontend/`)
}

const ICON_CSS = readFileSync(resolveIconCss(), 'utf8')

describe('SCHOOL_SYSTEMS — ข้อมูลปลายทาง', () => {
  it('มี 2 ระบบตามที่เจ้าของระบบกำหนด (ไม่มาก ไม่น้อย)', () => {
    expect(SCHOOL_SYSTEMS).toHaveLength(2)
    expect(SCHOOL_SYSTEMS.map((s) => s.key)).toEqual(['ess', 'school-site'])
  })

  it('⭐ "ระบบดูแลช่วยเหลือนักเรียน" ต้องอยู่ลำดับแรกเสมอ', () => {
    // วันเด็กเข้า ESS ก่อนระบบอื่นทั้งหมด (ระบบอื่นของโรงเรียนอ้างอิงจาก ESS)
    const first = SCHOOL_SYSTEMS[0]!
    expect(first.key).toBe('ess')
    expect(first.label).toContain('ดูแลช่วยเหลือนักเรียน')
  })

  it('ทุกปลายทางเป็น absolute https — ไม่ใช่ path ในแอปเรา และไม่ใช่ http', () => {
    for (const s of SCHOOL_SYSTEMS) {
      expect(s.url.startsWith('https://')).toBe(true)
      const u = new URL(s.url)
      expect(u.protocol).toBe('https:')
      // ต้องไม่ชี้กลับเข้า PIRIvoice เอง (จะทำให้กดแล้ววนอยู่ในแอปเดิม)
      expect(u.hostname).not.toMatch(/pirivoice|prsc-test/)
    }
  })

  it('โดเมน/พาธตรงกับระบบจริงที่ตรวจแล้วว่าตอบ 200', () => {
    const ess = SCHOOL_SYSTEMS[0]!
    const site = SCHOOL_SYSTEMS[1]!
    const essUrl = new URL(ess.url)
    expect(essUrl.hostname).toBe('ess.sesa37.go.th')

    const siteUrl = new URL(site.url)
    expect(siteUrl.hostname).toBe('sites.google.com')
    expect(siteUrl.pathname).toBe('/piriyalai.ac.th/piriyalai/home')
  })

  it('ไม่มี URL ซ้ำ และ key ไม่ซ้ำ (key ถูกใช้เป็น `key` ของ v-for)', () => {
    const urls = SCHOOL_SYSTEMS.map((s) => s.url)
    const keys = SCHOOL_SYSTEMS.map((s) => s.key)
    expect(new Set(urls).size).toBe(urls.length)
    expect(new Set(keys).size).toBe(keys.length)
  })

  it('ทุกช่องที่ UI ต้องใช้ มีค่าและเป็นไทย (label/hint/icon)', () => {
    for (const s of SCHOOL_SYSTEMS) {
      expect(s.label.trim()).not.toBe('')
      expect(s.hint.trim()).not.toBe('')
      // ชื่อปุ่มต้องเป็นไทยล้วน — ข้อความอังกฤษในเมนูไทยคือสิ่งที่ R5 กวาดออกไปแล้ว
      // ⚠️ เขียนเรนจ์เป็น ฀-๿ (Thai block) ไม่ใช่พิมพ์ตัวอักษรไทยลงไป —
      //    ตัวอักษรที่ "ดูคล้าย" กันแต่อยู่คนละโค้ดพอยต์ จะกลายเป็นเรนจ์ที่ผิดแบบเงียบๆ
      const THAI_ONLY = /^[฀-๿\s]+$/
      expect(s.label).toMatch(THAI_ONLY)
      expect(s.hint).toMatch(THAI_ONLY)
    }
  })

  it('⭐ ไอคอนทุกตัวมีอยู่จริงใน bootstrap-icons (คลาสที่พิมพ์ผิด = ไม่ขึ้นอะไรเลย)', () => {
    for (const s of SCHOOL_SYSTEMS) {
      expect(s.icon).toMatch(/^bi-[a-z0-9-]+$/)
      expect(ICON_CSS).toContain(`.${s.icon}::before`)
    }
  })
})

describe('SchoolSystemsCard — DOM ที่เรนเดอร์จริง', () => {
  const wrapper = mount(SchoolSystemsCard)
  const links = wrapper.findAll('a')

  it('เรนเดอร์ลิงก์เท่ากับจำนวนระบบใน registry (ไม่มีอันเกิน/อันหาย)', () => {
    expect(links).toHaveLength(SCHOOL_SYSTEMS.length)
  })

  it('ทุกไทล์มี href ครบ และกดแล้วไปปลายทางจริง', () => {
    SCHOOL_SYSTEMS.forEach((s, i) => {
      const a = links[i]!
      expect(a.attributes('href')).toBe(s.url)
      expect(a.attributes('href')).not.toBe('')
    })
  })

  it('⭐ ทุกไทล์เปิดในแท็บเดิม — ต้องไม่มี target="_blank" เลย', () => {
    // เจ้าของระบบสั่งไว้: "คลิกเปิด ไม่ต้องเปิดหน้าต่างใหม่ ไม่ต้องใส่ blank
    // เพราะตอนเปิดบนแอพ จะได้เนียนไปกับระบบเรา"
    for (const a of links) {
      expect(a.attributes('target')).toBeUndefined()
    }
    // ถ้าวันหนึ่งมีคนเติม `_blank` กลับ (นิสัยปกติของลิงก์นอกแอป) เทสต์นี้จะฟ้อง
    // พร้อมเหตุผล — และห้ามเติม `rel="noopener"` กลับด้วย เพราะไม่มีความหมาย
    // เมื่อไม่มี `_blank` (มีแต่จะทำให้เข้าใจผิดว่ายังเปิดแท็บใหม่)
    expect(links.some((a) => a.attributes('target') === '_blank')).toBe(false)
  })

  it('ไทล์เรียงตามลำดับเดียวกับ registry', () => {
    expect(links.map((a) => a.attributes('href'))).toEqual(SCHOOL_SYSTEMS.map((s) => s.url))
  })

  it('ผู้ใช้รู้ล่วงหน้าว่าจะออกไปเว็บภายนอก และรู้ว่าไทล์นั้นพาไปไหน', () => {
    // ข้อความนี้ต้องอยู่ใน DOM จริง (sr-only) ไม่ใช่แค่ในคอมเมนต์
    const text = wrapper.text()
    expect(text).toContain(EXTERNAL_NOTICE)
    for (const s of SCHOOL_SYSTEMS) {
      expect(text).toContain(s.label)
      expect(text).toContain(s.hint)
    }
  })

  it('ข้อความบอกผู้ใช้ต้องไม่พูดว่า "แท็บใหม่" (จะกลายเป็นคำโกหกทันที)', () => {
    // ผูกคำกับพฤติกรรม: ไม่มี `_blank` ⇒ ห้ามมีข้อความสัญญาว่าจะเปิดแท็บใหม่
    expect(EXTERNAL_NOTICE).not.toContain('แท็บใหม่')
    expect(wrapper.text()).not.toContain('แท็บใหม่')
  })

  it('ไอคอนถูกส่งเป็นคลาสจริง และถูกซ่อนจาก screen reader (มีชื่อปุ่มแล้ว)', () => {
    const icons = wrapper.findAll('a i')
    expect(icons).toHaveLength(SCHOOL_SYSTEMS.length)
    SCHOOL_SYSTEMS.forEach((s, idx) => {
      const i = icons[idx]!
      expect(i.classes()).toContain(s.icon)
      // ข้อความบอกปลายทางอยู่ใน <span class="sr-only"> แล้ว ⇒ ไอคอนไม่ต้องถูกอ่านซ้ำ
      expect(i.attributes('aria-hidden')).toBe('true')
    })
  })

  it('ไม่ผูกกับ API — การ์ดนี้ต้องขึ้นได้แม้ระบบล่ม', () => {
    // กันการเผลอเติม `v-if="!homeError"` / fetch เข้ามาในอนาคต: ถ้ามีลิงก์ครบ
    // โดยไม่มี prop/state ใดๆ แปลว่าเป็นข้อมูลนิ่งจริง
    expect(wrapper.props()).toEqual({})
    expect(links.length).toBeGreaterThan(0)
  })
})
