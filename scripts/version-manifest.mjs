#!/usr/bin/env node
/**
 * ตรวจ manifest ของประวัติเวอร์ชัน — รันก่อนออก release หรือก่อน backfill
 *
 *   node scripts/version-manifest.mjs
 *
 *   node scripts/version-manifest.mjs             # ด่านเต็ม (ใช้ใน CI และหลัง tag)
 *   node scripts/version-manifest.mjs --preflight # ก่อน commit/tag — แถว RELEASE ถือว่าชี้ HEAD
 *
 * ตรวจ:
 *   1. manifest มีครบ 6 คอลัมน์, SemVer ถูก, จำนวนแถวตรงกับ tag
 *   2. วันที่เรียงขึ้น และตรงกับวันที่ใน CHANGELOG
 *   3. cut commit มีจริง เป็น ancestor ของ HEAD และตรงกับ commit ที่ tag ชี้
 *   4. ความต่อเนื่อง: cut ของเวอร์ชันก่อนหน้าเป็น ancestor ของเวอร์ชันถัดไป
 *   5. CHANGELOG มีหัวข้อของทุกเวอร์ชัน พร้อมบรรทัด Migration
 *   6. VERSION = PROJECT_VERSION = package.json = package-lock.json (ทั้ง 2 ช่อง)
 *   7. PR ที่ merge แล้วถูกนับใน refs พอดีครั้งเดียว และไม่มีการอ้าง PR ที่ไม่มีจริง
 *
 * โหมด --preflight: แถวสุดท้ายที่ cut=RELEASE ยังไม่มี tag จึง resolve เป็น HEAD
 * และข้ามด่าน "tag ชี้ตรงกับ cut" เฉพาะแถวนั้น — ใช้ให้ release.sh ล้มก่อนแตะ git
 *
 * exit 1 เมื่อเจอข้อผิดพลาด เพื่อให้ใช้เป็นด่านใน CI ได้
 */
import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const manifestPath = join(root, 'scripts/version-manifest.tsv');
const changelogPath = join(root, 'CHANGELOG.md');
const PR_MIN = 1;
const PREFLIGHT = process.argv.includes('--preflight');

const git = (...args) =>
  execFileSync('git', args, { cwd: root, encoding: 'utf8' }).trim();

const errors = [];
const notes = [];
const fail = (msg) => errors.push(msg);

// ---------- 1. อ่าน manifest ----------
const rows = readFileSync(manifestPath, 'utf8')
  .split('\n')
  .filter((l) => l && !l.startsWith('#'))
  .map((line, i) => {
    const cols = line.split('\t');
    if (cols.length !== 6) {
      fail(`manifest แถว ${i + 1}: ต้องมี 6 คอลัมน์ แต่พบ ${cols.length}`);
      return null;
    }
    const [version, date, cut, bump, theme, refs] = cols;
    if (!version || !date || !cut || !bump || !theme || !refs) {
      fail(`manifest แถว ${i + 1}: มีคอลัมน์ว่าง — ${line}`);
      return null;
    }
    return { version, date, cut, bump, theme, refs };
  })
  .filter(Boolean);

const semver = /^\d+\.\d+\.\d+$/;
const dateRe = /^\d{4}-\d{2}-\d{2}$/;
const bumps = new Set(['major', 'minor', 'patch']);

if (rows.length === 0) fail('manifest ไม่มีแถวข้อมูล');
notes.push(`manifest ${rows.length} แถว`);

let prev = null;
for (const r of rows) {
  if (!semver.test(r.version)) fail(`${r.version}: SemVer ไม่ถูกต้อง`);
  if (!dateRe.test(r.date)) fail(`${r.version}: date ต้องเป็น YYYY-MM-DD`);
  if (!bumps.has(r.bump)) fail(`${r.version}: bump ต้องเป็น major/minor/patch`);
  if (prev) {
    if (r.date < prev.date) fail(`${r.version}: วันที่ย้อนหลัง (${r.date} < ${prev.date})`);
    const prevParts = prev.version.split('.').map(Number);
    const curParts = r.version.split('.').map(Number);
    if (r.bump === 'major' && !(curParts[0] > prevParts[0] && curParts[1] === 0 && curParts[2] === 0)) {
      fail(`${r.version}: bump=major แต่เลขไม่ใช่ x.0.0`);
    }
    if (r.bump === 'minor' && !(curParts[0] === prevParts[0] && curParts[1] > prevParts[1] && curParts[2] === 0)) {
      fail(`${r.version}: bump=minor แต่เลขไม่ใช่ x.y.0`);
    }
    if (r.bump === 'patch' && !(curParts[0] === prevParts[0] && curParts[1] === prevParts[1] && curParts[2] === prevParts[2] + 1)) {
      fail(`${r.version}: bump=patch แต่เลขไม่ใช่ x.y.(z+1)`);
    }
  }
  prev = r;
}

// ---------- 2. cut commit + tag ----------
// cut=RELEASE ใช้กับแถวที่ release.sh เพิ่งสร้าง — resolve ผ่าน tag ของแถวนั้น
const resolveCut = (r) => {
  if (r.cut === 'RELEASE') {
    // preflight: แถวที่กำลังจะออกยังไม่มี tag — ถือว่า cut คือ HEAD ปัจจุบัน
    if (PREFLIGHT && r === rows[rows.length - 1]) return git('rev-parse', 'HEAD');
    return git('rev-parse', '--verify', `v${r.version}^{commit}`);
  }
  return git('rev-parse', '--verify', `${r.cut}^{commit}`);
};

for (const [i, r] of rows.entries()) {
  if (r.cut === 'RELEASE' && i !== rows.length - 1) {
    fail(`${r.version}: cut=RELEASE ใช้ได้เฉพาะแถวสุดท้าย`);
  }
  if (r.cut !== 'RELEASE' && !/^[0-9a-f]{7,40}$/.test(r.cut)) {
    fail(`${r.version}: cut ต้องเป็น commit hash หรือ RELEASE`);
  }

  let cutFull;
  try {
    cutFull = resolveCut(r);
  } catch {
    fail(`${r.version}: ไม่พบ ${r.cut === 'RELEASE' ? `tag v${r.version}` : `commit ${r.cut}`}`);
    continue;
  }
  try {
    git('merge-base', '--is-ancestor', cutFull, 'HEAD');
  } catch {
    fail(`${r.version}: ${r.cut} ไม่ได้เป็น ancestor ของ HEAD`);
  }

  if (PREFLIGHT && r.cut === 'RELEASE' && i === rows.length - 1) continue;

  let tagFull;
  try {
    tagFull = git('rev-parse', '--verify', `v${r.version}^{commit}`);
  } catch {
    fail(`${r.version}: ไม่พบ tag v${r.version}`);
    continue;
  }
  if (r.cut !== 'RELEASE' && tagFull !== cutFull) {
    fail(`${r.version}: tag v${r.version} ชี้ ${tagFull.slice(0, 7)} แต่ manifest ระบุ ${r.cut}`);
  }
  if (git('cat-file', '-t', `refs/tags/v${r.version}`) !== 'tag') {
    fail(`${r.version}: tag v${r.version} ต้องเป็น annotated tag (git tag -a)`);
  }
}

// ---------- 3. ความต่อเนื่อง ----------
for (let i = 1; i < rows.length; i++) {
  const a = rows[i - 1];
  const b = rows[i];
  let aFull;
  let bFull;
  try {
    aFull = resolveCut(a);
    bFull = resolveCut(b);
  } catch {
    // cut/tag ที่ resolve ไม่ได้ถูกฟ้องเป็นรายแถวไปแล้ว — อย่าเพิ่ม error ที่ทำให้สับสน
    continue;
  }
  try {
    git('merge-base', '--is-ancestor', aFull, bFull);
  } catch {
    fail(`ความต่อเนื่อง: ${a.version} (${a.cut}) ไม่ใช่ ancestor ของ ${b.version} (${b.cut})`);
  }
}
notes.push(`cut ${rows.length} จุดอยู่จริงและเรียงต่อกัน`);

// ---------- 4. CHANGELOG ----------
const changelog = readFileSync(changelogPath, 'utf8');
const sectionRe = /^## \[([^\]]+)\][^\n]*$/gm;
const heads = [...changelog.matchAll(sectionRe)].map((m) => ({
  version: m[1],
  index: m.index,
}));

for (const r of rows) {
  const i = heads.findIndex((h) => h.version === r.version);
  if (i === -1) {
    fail(`CHANGELOG: ไม่พบหัวข้อ ## [${r.version}]`);
    continue;
  }
  const start = heads[i].index;
  const end = i + 1 < heads.length ? heads[i + 1].index : changelog.length;
  const body = changelog.slice(start, end);
  const headLine = body.split('\n')[0];
  if (!headLine.includes(`— ${r.date}`)) {
    fail(`CHANGELOG ${r.version}: หัวข้อต้องมีวันที่ ${r.date} (พบ: ${headLine.trim()})`);
  }
  if (!/\*\*Migration:\*\*/.test(body)) {
    fail(`CHANGELOG ${r.version}: ไม่มีบรรทัด **Migration:**`);
  }
}
if (!/^## \[Unreleased\]/m.test(changelog)) fail('CHANGELOG: ไม่มีหัวข้อ [Unreleased]');
notes.push(`CHANGELOG ${heads.length} หัวข้อ (รวม Unreleased)`);

// ---------- 5. ไฟล์เลขเวอร์ชัน ----------
const latest = rows[rows.length - 1].version;
const versionFile = readFileSync(join(root, 'VERSION'), 'utf8').trim();
const config = readFileSync(join(root, 'backend/core/config.py'), 'utf8');
const configMatch = config.match(/PROJECT_VERSION\s*:\s*str\s*=\s*"([^"]+)"/);
const pkg = JSON.parse(readFileSync(join(root, 'frontend/package.json'), 'utf8'));
const lock = JSON.parse(readFileSync(join(root, 'frontend/package-lock.json'), 'utf8'));

if (versionFile !== latest) fail(`VERSION = ${versionFile} แต่ manifest ใหม่สุดคือ ${latest}`);
if (!configMatch) fail('backend/core/config.py: ไม่พบ PROJECT_VERSION');
else if (configMatch[1] !== latest) fail(`PROJECT_VERSION = ${configMatch[1]} แต่ manifest ใหม่สุดคือ ${latest}`);
if (pkg.version !== latest) fail(`frontend/package.json version = ${pkg.version} แต่ manifest ใหม่สุดคือ ${latest}`);
if (lock.version !== latest) fail(`frontend/package-lock.json version = ${lock.version} แต่ manifest ใหม่สุดคือ ${latest}`);
if (lock.packages?.['']?.version !== latest) {
  fail(`frontend/package-lock.json packages[""].version = ${lock.packages?.['']?.version} แต่ manifest ใหม่สุดคือ ${latest}`);
}
notes.push(`เลขเวอร์ชันตรงกันทั้ง 4 ไฟล์: ${latest}`);

// ---------- 6. PR coverage ----------
const seen = new Map();
for (const r of rows) {
  for (const m of r.refs.matchAll(/PR #(\d+)(?:\s*-\s*#?(\d+))?/g)) {
    const from = Number(m[1]);
    const to = m[2] ? Number(m[2]) : from;
    if (from < PR_MIN) fail(`${r.version}: PR #${from} ต่ำกว่า ${PR_MIN}`);
    if (from > to) fail(`${r.version}: ช่วง PR #${from}-#${to} กลับด้าน`);
    for (let n = from; n <= to; n++) {
      if (seen.has(n)) fail(`PR #${n} ถูกนับซ้ำใน ${seen.get(n)} และ ${r.version}`);
      else seen.set(n, r.version);
    }
  }
}
const maxPr = seen.size ? Math.max(...seen.keys()) : 0;
for (let n = PR_MIN; n <= maxPr; n++) {
  if (!seen.has(n)) fail(`PR #${n} ไม่ถูกนับใน manifest`);
}
notes.push(maxPr ? `PR #${PR_MIN}-#${maxPr} ถูกนับครบพอดีครั้งเดียว` : 'ยังไม่มี PR ใน manifest');

// ---------- สรุป ----------
for (const n of notes) console.log(`✔ ${n}`);
if (errors.length) {
  console.error(`\n✖ พบ ${errors.length} ปัญหา:`);
  for (const e of errors) console.error(`  - ${e}`);
  process.exit(1);
}
console.log('\n✅ version manifest ผ่านทุกด่าน');
