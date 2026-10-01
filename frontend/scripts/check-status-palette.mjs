#!/usr/bin/env node
/**
 * 🚫 ด่านกันสี "สำเร็จ" จากพาเลตต์ดิบกลับมา (R5.5)
 *
 * 🔴 **ทำไมต้องมี** — ก่อน R5.5 ทั้งแอปใช้ **emerald 7 เฉด** (`50/100/200/400/500/600/700`)
 *    ปนกันสำหรับความหมายเดียวคือ "สำเร็จ" ⇒ สีของความหมายเดียวถูกนิยาม 7 ที่ในพาเลตต์ของ
 *    Tailwind ซึ่งเราแก้ไม่ได้ · R5.5 ย้ายมาเป็นสเกล `ok-*` ใน `tailwind.config.js`
 *    ⇒ ด่านนี้กันไม่ให้ `bg-emerald-500` กลับมา *ทีละจุด* แบบที่ไม่มีใครสังเกต
 *    (กลไกเดียวกับ `check-brand-colors.mjs` ที่ R5.4 วางไว้)
 *
 * ✅ **สีที่ถูกต้อง** — `text-ok-strong` · `bg-ok-solid` · `bg-ok-bright` · `border-ok-line`
 *    · `bg-ok-tint` · `bg-ok-faint` (ดูตารางเต็มใน `tailwind.config.js`)
 *    ⇒ เรียงเข้ม→อ่อน: strong → solid → bright → focus → line → tint → faint → soft
 *
 * 🔴 **ครอบทั้งตระกูล "เขียว" ไม่ใช่แค่ `emerald`** — เจตนาของ R5.5 คือ *"สีที่แปลว่าสำเร็จ
 *    ต้องมาจากสเกล `ok-*` เท่านั้น"* ⇒ ถ้าดักแค่ `emerald-*` คนถัดไปพิมพ์ `text-green-700`
 *    ก็หลุดด่านได้เลย · `green`/`teal`/`lime` **ไม่มีที่ใช้อยู่ในเรพนี้แม้แต่จุดเดียว**
 *    (ตรวจแล้ว) ⇒ กว้างขึ้นมาโดยไม่มี false positive
 *
 * 🔴 **ด่านนี้ "ตัดคอมเมนต์ทิ้งก่อนตรวจ" โดยเจตนา** — เพราะ `src/constants/status.ts`
 *    มีคอมเมนต์ที่ *อธิบาย* พาเลตต์นี้อยู่จริง ⇒ ด่านที่ฟ้องคอมเมนต์ = ด่านที่คนจะลบทิ้ง
 *    ในสัปดาห์ถัดไป (เหตุผลเดียวกับ `check-brand-colors.mjs`)
 *
 * ⚠️ **ขอบเขตที่จงใจไม่ครอบ — หนี้ที่รู้ตัว**
 *    · `src/views/Landing.vue` — หน้าสาธารณะที่แผน R5 สั่ง **ห้ามแตะ** ⇒ ยกเว้นไว้ทั้งไฟล์
 *      (ยังใช้ emerald ครบทั้ง 7 เฉด) · **ถ้าวันหนึ่งหน้า Landing ถูกจัดใหม่ ต้องลบข้อยกเว้นนี้**
 *    · **`amber-*` (34 จุด / 6 ไฟล์) และ `red-*` (33 จุด)** เป็นปัญหา *ชนิดเดียวกัน*
 *      แต่ยัง **ไม่ได้แก้ในรอบนี้** — `warn`/`danger` ใน `tailwind.config.js` มีแค่
 *      `DEFAULT` + `soft` ไม่พอรับ 6–9 เฉดที่ใช้จริง ⇒ ต้องมีสเกลก่อน แล้วจึงย้าย
 *      ⇒ ยังไม่ใส่ในด่านนี้ **เพราะจะฟ้องทันที 67 จุด** (ด่านที่แดงอยู่แล้ว = ด่านที่ถูกปิด)
 */
import fs from 'node:fs'
import path from 'node:path'

const ROOT = path.resolve(import.meta.dirname, '..')
const TARGETS = ['src']
const EXT = /\.(vue|ts|js|mjs|css)$/
/** ตระกูลเขียวทั้งหมด — "สำเร็จ" ต้องมาจาก `ok-*` เท่านั้น */
const SUCCESS_FAMILY = /\b(?:emerald|green|teal|lime)-\d{2,3}\b/
/** ไฟล์ที่ยกเว้น: หน้าสาธารณะนอกขอบเขตรอบนี้ (เหตุผลอยู่ในหัวไฟล์) */
const EXEMPT = [path.join('src', 'views', 'Landing.vue')]

/**
 * ตัดคอมเมนต์ทุกชนิดออก (block · HTML · line) — คงจำนวนบรรทัดไว้เพื่อให้เลขบรรทัดยังตรง
 * (คัดลอกกลไกเดียวกับ `check-brand-colors.mjs` โดยเจตนา — สองด่านควรอ่านเหมือนกัน)
 */
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
let scanned = 0
for (const f of files) {
  const rel = path.relative(ROOT, f)
  if (EXEMPT.includes(rel)) continue
  scanned++
  const lines = stripComments(fs.readFileSync(f, 'utf8')).split('\n')
  lines.forEach((line, i) => {
    const m = line.match(SUCCESS_FAMILY)
    if (m) hits.push({ file: rel, line: i + 1, cls: m[0], text: line.trim().slice(0, 120) })
  })
}

if (hits.length === 0) {
  console.log(`✅ ไม่มีสี "สำเร็จ" จากพาเลตต์ดิบ (ตรวจ ${scanned} ไฟล์ · ยกเว้น ${EXEMPT.length})`)
  process.exit(0)
}

console.error(`\n🚫 พบสี "สำเร็จ" จากพาเลตต์ดิบ ${hits.length} จุด — ต้องใช้สเกล ok-* แทน\n`)
for (const h of hits) console.error(`   ${h.file}:${h.line}  [${h.cls}]\n      ${h.text}\n`)
console.error('   แก้ (เข้ม → อ่อน):')
console.error('     emerald-700 → ok-strong   emerald-600 → ok-solid    emerald-500 → ok-bright')
console.error('     emerald-400 → ok-focus    emerald-200 → ok-line     emerald-100 → ok-tint')
console.error('     emerald-50  → ok-faint    (ต่อ /opacity ได้ เช่น bg-ok-tint/50)\n')
process.exit(1)
