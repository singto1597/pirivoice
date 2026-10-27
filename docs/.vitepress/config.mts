import { fileURLToPath } from 'node:url'

// ไฟล์นี้อยู่นอก frontend/ จึง import `vitepress` ไม่ได้ (Node จะหา package ไม่เจอ)
// VitePress รับ config เป็น object ธรรมดาได้ โดยไม่ต้องใช้ defineConfig
// คู่มือนี้ถูก build ไปที่ frontend/public/docs แล้วฝังในเว็บหลักที่ path /docs/
const frontendModules = fileURLToPath(new URL('../../frontend/node_modules/', import.meta.url))

export default {
  lang: 'th-TH',
  title: 'PIRIvoice Help Center',
  description: 'ศูนย์ช่วยเหลือและคู่มือการใช้งาน PIRIvoice สำหรับนักเรียน เจ้าหน้าที่ และผู้ดูแลระบบ',
  base: '/docs/',
  outDir: '../frontend/public/docs',

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
    },
  },

  themeConfig: {
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
            { text: 'ภาพรวมเล่ม 1', link: '/1-user-guide/' },
            { text: 'หน้าเว็บสาธารณะ', link: '/1-user-guide/public-landing' },
            { text: 'เริ่มใช้งานและติดตั้งแอป', link: '/1-user-guide/getting-started-pwa' },
            { text: 'การแจ้งเตือนและการตั้งค่า', link: '/1-user-guide/notifications-settings' },
            { text: 'หน้าแรกและเมนูนำทาง', link: '/1-user-guide/home-and-navigation' },
            { text: 'แจ้งเรื่องและติดตามสถานะ', link: '/1-user-guide/issue-reporting-tracking' },
            { text: 'บอร์ดและการโหวต', link: '/1-user-guide/boards-and-voting' },
            { text: 'กิจกรรมและเช็คอิน', link: '/1-user-guide/events-and-checkin' },
            { text: 'โปรไฟล์และกิจกรรมของฉัน', link: '/1-user-guide/profile-and-activity' },
            { text: 'คู่มือการทำงาน', link: '/1-user-guide/playbooks' },
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
          ],
        },
      ],
    },

    outline: { level: [2, 3], label: 'ในหน้านี้' },
    docFooter: { prev: 'บทก่อนหน้า', next: 'บทถัดไป' },
    returnToTopLabel: 'กลับขึ้นด้านบน',
    sidebarMenuLabel: 'เมนู',
    darkModeSwitchLabel: 'ธีม',
    search: { provider: 'local' },
  },
}
