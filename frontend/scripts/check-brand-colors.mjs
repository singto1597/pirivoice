#!/usr/bin/env node
/**
 * 🚫 ด่านกันสีแบรนด์ฮาร์ดโค้ดกลับมา (R5.4)
 *
 * 🔴 **ทำไมต้องมี** — ก่อน R0 มี `#B91C1C` / `#991B1B` ฮาร์ดโค้ดเป็น arbitrary value
 *    (`bg-[#B91C1C]`) กระจายอยู่ **634 จุดใน 44 ไฟล์** ⇒ เปลี่ยนสีแบรนด์ทีต้องแก้ 634 ที่
 *    และไม่มีอะไรจับได้ถ้าพิมพ์เพี้ยน (`#B91C1D`) — R0 ย้ายมาที่ token ใน `tailwind.config.js`
 *    แล้ว ด่านนี้คือสิ่งที่กันไม่ให้มันกลับมา *ทีละจุด* แบบที่ไม่มีใครสังเกต
 *
 * ✅ **สีที่ถูกต้อง** — `bg-brand` · `text-brand` · `hover:bg-brand-strong` · `bg-brand/10`
 *    (Tailwind ต่อท้าย `/opacity` ให้เองได้ ⇒ ไม่มีข้ออ้างว่าต้องใช้ hex)
 *
 * 🔴 **ด่านนี้ "ตัดคอมเมนต์ทิ้งก่อนตรวจ" โดยเจตนา** — เพราะมีคอมเมนต์ที่ *อธิบาย* ปัญหานี้อยู่จริง
 *    (`src/constants/chart.ts` เขียนตัวอย่าง `bg-[#B91C1C]` ไว้ในคำอธิบาย)
 *    ด่านที่ฟ้องคอมเมนต์ = ด่านที่คนจะลบทิ้งในสัปดาห์ถัดไป ⇒ ตรวจเฉพาะ *โค้ด* เท่านั้น
 *
 * ⚠️ **ขอบเขตที่จงใจไม่ครอบ** — hex อื่นที่ยังเหลือ (`[#FAFAF9]` · `[#D97706]` · `[#a11717]`)
 *    ไม่ได้อยู่ในด่านนี้ เพราะ 4 ใน 6 จุดอยู่ใน `Landing.vue` / `Login.vue` ซึ่งเป็น **หน้าสาธารณะ
 *    ที่แผน R5 สั่งไม่ให้แตะ** และที่เหลือเป็นงานความสม่ำเสมอของ R5.5
 *    ⇒ ด่านนี้ตั้งใจแคบเพื่อให้ **ไม่มี false positive** (ด่านที่ฟ้องมั่วจะถูกปิด)
 */
import fs from 'node:fs'
import path from 'node:path'

const ROOT = path.resolve(import.meta.dirname, '..')
const TARGETS = ['src', 'index.html']
const EXT = /\.(vue|ts|js|mjs|css|html)$/
const BRAND_HEX = /\[#(?:b91c1c|991b1b)\]/gi

/** ตัดคอมเมนต์ทุกชนิดออก (block · HTML · line) — คงจำนวนบรรทัดไว้เพื่อให้เลขบรรทัดยังตรง */
function stripComments(src) {
  const blank = (s) => s.replace(/[^\n]/g, ' ')
  return src
    .replace(/\/\*[\s\S]*?\*\//g, blank) // /* … */  (CSS + JS)
    .replace(/<!--[\s\S]*?-->/g, blank) // <!-- … -->  (เทมเพลต Vue)
    .replace(/(^|[^:'"`\\])\/\/[^\n]*/gm, (m, p1) => p1 + blank(m.slice(p1.length))) // // … (ยกเว้น http://)
}

const files = []
for (const t of TARGETS) {
  const p = path.join(ROOT, t)
  if (!fs.existsSync(p)) continue
  if (fs.statSync(p).isFile()) {
    files.push(p)
    continue
  }
  ;(function walk(d) {
    for (const e of fs.readdirSync(d, { withFileTypes: true })) {
      const f = path.join(d, e.name)
      if (e.isDirectory()) walk(f)
      else if (EXT.test(e.name)) files.push(f)
    }
  })(p)
}

const hits = []
for (const f of files) {
  const lines = stripComments(fs.readFileSync(f, 'utf8')).split('\n')
  lines.forEach((line, i) => {
    BRAND_HEX.lastIndex = 0
    if (BRAND_HEX.test(line)) {
      hits.push({ file: path.relative(ROOT, f), line: i + 1, text: line.trim().slice(0, 120) })
    }
  })
}

if (hits.length === 0) {
  console.log(`✅ ไม่มีสีแบรนด์ฮาร์ดโค้ด (ตรวจ ${files.length} ไฟล์)`)
  process.exit(0)
}

console.error(`\n🚫 พบสีแบรนด์ฮาร์ดโค้ด ${hits.length} จุด — ต้องใช้ token จาก tailwind.config.js แทน\n`)
for (const h of hits) console.error(`   ${h.file}:${h.line}\n      ${h.text}\n`)
console.error('   แก้: [#B91C1C] → brand · [#991B1B] → brand-strong · (ต่อ /opacity ได้ เช่น bg-brand/10)\n')
process.exit(1)
