import { readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

// ไฟล์นี้อยู่นอก frontend/ จึง import `vitepress` ไม่ได้ (Node จะหา package ไม่เจอ)
// VitePress รับ config เป็น object ธรรมดาได้ โดยไม่ต้องใช้ defineConfig
// คู่มือนี้ถูก build ไปที่ frontend/public/docs แล้วฝังในเว็บหลักที่ path /docs/
const frontendModules = fileURLToPath(new URL('../../frontend/node_modules/', import.meta.url))

/**
 * อ่านขนาดจริงของไฟล์ WebP จาก header (VP8X / VP8L / VP8)
 * ใช้แยก "ภาพแคปมือถือ" (สูงกว่ากว้าง) ออกจาก "ภาพแคปเดสก์ท็อป"
 * เพื่อให้ CSS ย่อเฉพาะภาพแนวตั้ง — ภาพเดสก์ท็อปต้องคงความกว้างไว้ให้อ่านตัวเลขได้
 */
function webpSize(file) {
  let buf
  try {
    buf = readFileSync(file)
  } catch {
    return null
  }
  if (buf.length < 30 || buf.toString('ascii', 0, 4) !== 'RIFF') return null
  let offset = 12
  while (offset + 8 <= buf.length) {
    const tag = buf.toString('ascii', offset, offset + 4)
    const size = buf.readUInt32LE(offset + 4)
    if (tag === 'VP8X') {
      return { width: buf.readUIntLE(offset + 12, 3) + 1, height: buf.readUIntLE(offset + 15, 3) + 1 }
    }
    if (tag === 'VP8L') {
      const bits = buf.readUInt32LE(offset + 9)
      return { width: (bits & 0x3fff) + 1, height: ((bits >> 14) & 0x3fff) + 1 }
    }
    if (tag === 'VP8 ') {
      return {
        width: buf.readUInt16LE(offset + 14) & 0x3fff,
        height: buf.readUInt16LE(offset + 16) & 0x3fff,
      }
    }
    offset += 8 + size + (size % 2)
  }
  return null
}

/** ใส่คลาสตามสัดส่วนภาพ เพื่อให้ custom.css ย่อภาพแคปมือถือได้โดยไม่ต้องแก้ markdown 90 จุด */
function markScreenshotSizes(md) {
  md.core.ruler.push('screenshot_size', (state) => {
    for (const block of state.tokens) {
      if (block.type !== 'inline' || !block.children) continue
      for (const token of block.children) {
        if (token.type !== 'image') continue
        const src = token.attrGet('src')
        if (!src || /^(?:https?:|data:)/i.test(src)) continue
        const base = state.env?.path ? path.dirname(state.env.path) : process.cwd()
        const size = webpSize(path.resolve(base, src))
        if (!size) continue
        // แคปมือถือ ≈ 0.46 (780×1688) · แคปเดสก์ท็อป ≈ 0.90 (1520×1688) และ 1.6 (1280×800)
        // เกณฑ์ 0.75 แยกสองกลุ่มนี้ออกจากกันชัดเจน
        const portrait = size.width / size.height < 0.75
        token.attrJoin('class', portrait ? 'shot shot--tall' : 'shot shot--wide')
      }
    }
  })
}

export default {
  lang: 'th-TH',
  title: 'PIRIvoice Help Center',
  description: 'ศูนย์ช่วยเหลือและคู่มือการใช้งาน PIRIvoice สำหรับนักเรียน เจ้าหน้าที่ และผู้ดูแลระบบ',
  base: '/docs/',
  outDir: '../frontend/public/docs',
  head: [
    ['meta', { name: 'theme-color', content: '#b91c1c' }],
    ['link', { rel: 'icon', href: '/docs/favicon.png' }],
    ['link', { rel: 'preconnect', href: 'https://fonts.googleapis.com' }],
    ['link', { rel: 'preconnect', href: 'https://fonts.gstatic.com', crossorigin: '' }],
    [
      'link',
      {
        rel: 'stylesheet',
        href: 'https://fonts.googleapis.com/css2?family=Anuphan:wght@400;500;600;700;800&family=Noto+Sans+Thai:wght@300;400;500;600;700;800&display=swap',
      },
    ],
  ],

  // เว็บสาธารณะแสดงเฉพาะคู่มือผู้ใช้/เจ้าหน้าที่/ผู้ดูแลระบบ
  // เอกสารวิศวกรรมยังอยู่ใน Git แต่ไม่ถูก build ลง public/docs
  srcExclude: [
    '4-developer-playbook/**',
    'glossary.md',
    'system_prompt.md',
    'scope.md',
    'skills.md',
    'rules/**',
  ],

  // URL แบบไม่มี .html เช่น /docs/1-user-guide/getting-started-pwa
  // nginx ต้องมี fallback `$uri.html` ด้วย (ดู frontend/Dockerfile)
  cleanUrls: true,

  // หน้า Markdown ถูก compile เป็น Vue component ที่ import vue/server-renderer
  // แต่ docs/ ไม่มี node_modules ของตัวเอง จึงชี้ไปที่ frontend/node_modules
  vite: {
    resolve: {
      alias: [
        { find: /^vue\/server-renderer$/, replacement: `${frontendModules}vue/server-renderer/index.mjs` },
        { find: /^vue$/, replacement: `${frontendModules}vue/dist/vue.runtime.esm-bundler.js` },
        {
          find: /^vitepress\/theme$/,
          replacement: `${frontendModules}vitepress/dist/client/theme-default/index.js`,
        },
      ],
    },
  },

  // เอกสารวิศวกรรมเดิมมี `{{ }}` ในตัวอย่างคำสั่ง (เช่น docker --format '{{.Names}}')
  // Vue จะตีความเป็น expression แล้ว build พัง จึง escape เป็น HTML entity ก่อนส่งให้ Vue
  markdown: {
    config(md) {
      const escape = (rule) => (tokens, idx, options, env, self) => {
        const html = rule
          ? rule(tokens, idx, options, env, self)
          : self.renderToken(tokens, idx, options)
        return html.replace(/\{\{/g, '&#123;&#123;')
      }
      md.renderer.rules.text = escape(md.renderer.rules.text)
      md.renderer.rules.code_inline = escape(md.renderer.rules.code_inline)

      markScreenshotSizes(md)
    },
  },

  themeConfig: {
    logo: '/logos/school-logo.png',
    siteTitle: 'PIRIvoice Help Center',

    nav: [
      { text: 'หน้าแรก', link: '/' },
      { text: 'สำหรับนักเรียน', link: '/1-user-guide/' },
      { text: 'สำหรับเจ้าหน้าที่', link: '/2-staff-operations/' },
      { text: 'สำหรับผู้ดูแลระบบ', link: '/3-admin-guide/' },
    ],

    // Sidebar แยกตาม path อย่างเด็ดขาด: แต่ละเล่มเห็นเฉพาะเมนูของตนเอง
    sidebar: {
      '/1-user-guide/': [
        {
          text: 'คู่มือนักเรียน',
          collapsed: false,
          items: [
            { text: 'คู่มือผู้ใช้ PIRIvoice', link: '/1-user-guide/' },
            { text: 'หน้าเว็บสาธารณะ', link: '/1-user-guide/public-landing' },
            { text: 'เข้าสู่ระบบและติดตั้งแอป', link: '/1-user-guide/getting-started-pwa' },
            { text: 'การแจ้งเตือนและการตั้งค่า', link: '/1-user-guide/notifications-settings' },
            { text: 'หน้าแรกและแถบเมนู', link: '/1-user-guide/home-and-navigation' },
            { text: 'แจ้งเรื่องและติดตามสถานะ', link: '/1-user-guide/issue-reporting-tracking' },
            { text: 'บอร์ด การโหวต และไอเดีย', link: '/1-user-guide/boards-and-voting' },
            { text: 'กิจกรรมและคิวอาร์เช็คอิน', link: '/1-user-guide/events-and-checkin' },
            { text: 'โปรไฟล์และประวัติกิจกรรม', link: '/1-user-guide/profile-and-activity' },
            { text: 'คู่มือการทำงาน 6 เล่ม', link: '/1-user-guide/playbooks' },
          ],
        },
      ],

      '/2-staff-operations/': [
        {
          text: 'คู่มือหัวหน้าห้องและสภานักเรียน',
          collapsed: false,
          items: [
            { text: 'ภาพรวมเล่ม 2', link: '/2-staff-operations/' },
            { text: 'ขั้นตอนจัดการเรื่อง', link: '/2-staff-operations/issue-management-sop' },
            { text: 'กิจกรรมและสแกนเช็คอิน', link: '/2-staff-operations/event-management-scanner' },
            { text: 'จัดการประกาศ', link: '/2-staff-operations/announcement-management' },
            { text: 'ตรวจรายงานเนื้อหา', link: '/2-staff-operations/content-moderation' },
            { text: 'ข้อมูลนักเรียนและประวัติ', link: '/2-staff-operations/student-records' },
            { text: 'นำเข้านักเรียนด้วย Excel', link: '/2-staff-operations/student-import' },
            { text: 'ย้ายห้องและถอดออกจากห้อง', link: '/2-staff-operations/student-moves' },
            { text: 'เลื่อนชั้นนักเรียน', link: '/2-staff-operations/student-promotion' },
            {
              text: 'มอบหมายใหม่และกระทบยอด',
              link: '/2-staff-operations/reassignment-and-reconciliation',
            },
          ],
        },
      ],

      '/3-admin-guide/': [
        {
          text: 'คู่มือครูและผู้ดูแลระบบ',
          collapsed: false,
          items: [
            { text: 'ภาพรวมเล่ม 3', link: '/3-admin-guide/' },
            { text: 'ผู้ใช้ บทบาท และสิทธิ์', link: '/3-admin-guide/user-and-role-management' },
            { text: 'บันทึกการใช้งาน', link: '/3-admin-guide/audit-logs-investigation' },
            { text: 'ตั้งค่าระบบ', link: '/3-admin-guide/system-configuration' },
            { text: 'ปีการศึกษาและภาคเรียน', link: '/3-admin-guide/academic-calendar' },
            { text: 'แดชบอร์ดและรายงาน', link: '/3-admin-guide/dashboard-and-reports' },
            { text: 'ภาคผนวกทางเทคนิค', link: '/3-admin-guide/technical-appendix' },
          ],
        },
      ],
    },

    outline: { level: [2, 3], label: 'ในหน้านี้' },
    docFooter: { prev: 'บทก่อนหน้า', next: 'บทถัดไป' },
    returnToTopLabel: 'กลับขึ้นด้านบน',
    sidebarMenuLabel: 'เมนู',
    darkModeSwitchLabel: 'ธีม',
    search: {
      provider: 'local',
      options: {
        translations: {
          button: {
            buttonText: 'ค้นหา',
            buttonAriaLabel: 'ค้นหาในคู่มือ',
          },
          modal: {
            displayDetails: 'แสดงรายละเอียด',
            resetButtonTitle: 'ล้างการค้นหา',
            backButtonTitle: 'ปิดการค้นหา',
            noResultsText: 'ไม่พบผลลัพธ์สำหรับ',
            footer: {
              selectText: 'เลือก',
              selectKeyAriaLabel: 'Enter',
              navigateText: 'เลื่อน',
              navigateUpKeyAriaLabel: 'ลูกศรขึ้น',
              navigateDownKeyAriaLabel: 'ลูกศรลง',
              closeText: 'ปิด',
              closeKeyAriaLabel: 'Esc',
            },
          },
        },
      },
    },

    notFound: {
      title: 'ไม่พบหน้าที่ต้องการ',
      quote: 'ลิงก์อาจถูกย้ายหรือพิมพ์ผิด กลับไปเลือกคู่มือตามบทบาทได้ที่หน้าแรก',
      linkLabel: 'กลับไปหน้าแรก',
      linkText: 'กลับไปหน้าแรก',
    },
  },
}
