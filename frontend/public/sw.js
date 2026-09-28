/* ============================================================================
 * PIRIvoice Service Worker (A1) — **app shell cache เท่านั้น**
 * ============================================================================
 *
 * 🎯 เป้าหมาย: เปิดแอพตอนออฟไลน์แล้วเห็น shell (ไม่จอขาว) + ติดตั้งลงหน้าจอมือถือได้
 *
 * ⛔ **ห้าม cache อะไรก็ตามที่มาจาก `/api`** — SW cache เป็น **per-origin ไม่ใช่
 *    per-session** ⇒ ถ้า cache ไว้ ผู้ใช้คนถัดไปบนเครื่องเดียวกัน (หรือหลัง logout)
 *    จะเห็นข้อมูลของคนก่อนหน้า นี่คือเหตุผลที่รอบนี้ **ไม่** ทำ offline cache
 *    เต็มรูปแบบ (A7 ในแผน) — และเป็นเหตุที่ fetch handler ปล่อย `/api/*` ผ่านลอย ๆ
 *
 * ⛔ cross-origin (Google Fonts, jsdelivr bootstrap-icons) ก็ **ห้าม cache** —
 *    เป็น opaque response เก็บไปก็อ่านค่าไม่ได้/ใช้ตอบ offline ไม่ได้จริง
 *
 * ⚠️ **ห้ามเรียก `self.skipWaiting()` ตอน install** — ตั้งใจให้ SW ใหม่รอในสถานะ
 *    `waiting` แล้วให้ผู้ใช้กดปุ่ม "อัปเดต" เอง (ดู message handler ข้างล่าง)
 *    ไม่งั้นแท็บที่กำลังกรอกเรื่องอยู่จะโดน reload กลางทาง
 */

const SHELL_CACHE = 'piri-shell-v1';

// ไฟล์ที่ต้องมีแน่ ๆ — precache ตอน install
// ⚠️ `addAll` จะล้มทั้งชุดถ้ามีไฟล์ใดไฟล์หนึ่งหาย ⇒ ต้องมั่นใจว่าไฟล์พวกนี้มีจริง
//    (ไอคอน generate ไว้ใน `public/icons/` แล้ว — อย่าลบ)
const SHELL_ASSETS = [
  '/',
  '/index.html',
  '/manifest.json',
  '/logos/school-logo.png',
  '/icons/icon-192.png',
  '/icons/icon-512.png',
  '/icons/icon-512-maskable.png',
  '/icons/apple-touch-icon.png',
];

/** หน้าที่แสดงเมื่อออฟไลน์และ **ไม่มี** shell ใน cache เลย (ครั้งแรกสุด) */
const OFFLINE_HTML = `<!DOCTYPE html>
<html lang="th"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PIRIvoice — ออฟไลน์</title>
<style>
  body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;
       background:#fff;color:#1c1917;font-family:system-ui,-apple-system,"Noto Sans Thai",sans-serif;
       text-align:center;padding:24px}
  .box{max-width:22rem}
  h1{font-size:1.05rem;margin:0 0 .4rem}
  p{font-size:.85rem;color:#78716c;line-height:1.6;margin:0 0 1.25rem}
  button{background:#b91c1c;color:#fff;border:0;border-radius:.75rem;padding:.7rem 1.4rem;
         font-size:.85rem;font-weight:700;font-family:inherit}
</style></head>
<body><div class="box">
  <h1>ตอนนี้ออฟไลน์อยู่</h1>
  <p>เปิดแอพไว้อย่างน้อยหนึ่งครั้งตอนมีเน็ต แล้วครั้งต่อไปจะเปิดได้แม้ไม่มีสัญญาณ</p>
  <button onclick="location.reload()">ลองใหม่</button>
</div></body></html>`;

/**
 * ดึง URL ของ asset ที่ Vite สร้าง (มี content hash) ออกจาก HTML shell
 *
 * ⚠️ **จำเป็นจริง ๆ ไม่ใช่ของแถม** — precache ตอน install รู้แค่ชื่อไฟล์คงที่
 *    แต่ JS/CSS ของแอพชื่อ `/assets/index-<hash>.js` ซึ่งตอนเขียน SW ยังไม่รู้
 *    ⇒ ถ้าไม่ดึงจาก HTML มาตรงนี้ การเปิดแบบออฟไลน์ครั้งแรกจะได้ index.html
 *    แต่ JS 404 → **จอขาว** (ตรงข้ามกับเป้าหมายของงานนี้)
 */
function extractAssets(html) {
  const urls = new Set();
  const re = /["'](\/assets\/[^"']+)["']/g;
  let m;
  while ((m = re.exec(html)) !== null) urls.add(m[1]);
  return [...urls];
}

// ── install: precache shell + asset ที่ Vite hash ไว้ ──────────────────────
self.addEventListener('install', (event) => {
  event.waitUntil(
    (async () => {
      const cache = await caches.open(SHELL_CACHE);

      // ไฟล์คงที่ — ถ้าตัวใดหายให้ล้มแบบเห็นได้ (จะได้รู้ว่าลืม generate ไอคอน)
      await cache.addAll(SHELL_ASSETS);

      // asset ที่ hash ไว้ — ดึงจาก HTML จริง แล้วเก็บแบบ "เท่าที่ได้"
      // (ใช้ allSettled ไม่ใช่ addAll เพราะ asset บางตัวอาจ 404 ในบาง build
      //  — ไม่ควรทำให้ install ล้มทั้งอันเพราะเรื่องนั้น)
      try {
        const res = await fetch('/index.html', { cache: 'reload' });
        if (res.ok) {
          const html = await res.text();
          await Promise.allSettled(extractAssets(html).map((u) => cache.add(u)));
        }
      } catch {
        // เงียบไว้ — install ต้องสำเร็จแม้เน็ตสะดุด
      }
    })(),
  );
});

// ── activate: ลบ cache เวอร์ชันเก่า + เข้าควบคุมแท็บที่เปิดอยู่ทันที ──────────
self.addEventListener('activate', (event) => {
  event.waitUntil(
    (async () => {
      const names = await caches.keys();
      await Promise.all(
        names.filter((n) => n.startsWith('piri-shell-') && n !== SHELL_CACHE).map((n) => caches.delete(n)),
      );
      await self.clients.claim();
    })(),
  );
});

// ── fetch: แยก 3 ทางชัดเจน ────────────────────────────────────────────────
self.addEventListener('fetch', (event) => {
  const req = event.request;

  // อ่านอย่างเดียว ไม่ยุ่งกับ mutation เลย
  if (req.method !== 'GET') return;

  const url = new URL(req.url);

  // ① ⛔ `/api/*` — ปล่อยผ่าน network ล้วน **ห้าม cache เด็ดขาด**
  //    การไม่เรียก respondWith เลย = browser จัดการเองตามปกติ (การันตีดีที่สุด)
  if (url.origin === self.location.origin && url.pathname.startsWith('/api/')) return;

  // ② cross-origin — ไม่แตะ (opaque response เก็บไปก็ไร้ค่า)
  if (url.origin !== self.location.origin) return;

  // ③ navigation — network-first, ออฟไลน์ค่อยตกไปที่ shell
  if (req.mode === 'navigate') {
    event.respondWith(handleNavigate(req));
    return;
  }

  // ④ asset ของแอพ (ชื่อมี content hash ⇒ cache-first ปลอดภัย)
  if (/^\/(assets|icons|logos)\//.test(url.pathname)) {
    event.respondWith(handleStatic(req));
    return;
  }

  // ที่เหลือ (robots.txt, sitemap.xml, playbooks/…) — ปล่อยผ่าน
});

async function handleNavigate(req) {
  try {
    const fresh = await fetch(req);
    // เก็บ HTML shell ล่าสุดไว้ — เฉพาะ response ที่โอเคจริง
    // (ห้ามเก็บ 401/500 ไม่งั้นออฟไลน์แล้วจะได้หน้า error ค้าง)
    if (fresh && fresh.ok) {
      try {
        const cache = await caches.open(SHELL_CACHE);
        await cache.put('/index.html', fresh.clone());
      } catch {
        // cache เขียนไม่ได้ก็ไม่เป็นไร — หน้าต้องขึ้นได้เสมอ
      }
    }
    return fresh;
  } catch {
    const cache = await caches.open(SHELL_CACHE);
    const shell = (await cache.match('/index.html')) || (await cache.match('/'));
    if (shell) return shell;
    return new Response(OFFLINE_HTML, {
      status: 200,
      headers: { 'Content-Type': 'text/html; charset=utf-8' },
    });
  }
}

async function handleStatic(req) {
  const cache = await caches.open(SHELL_CACHE);
  const hit = await cache.match(req);
  if (hit) return hit;

  const fresh = await fetch(req);
  // ⚠️ เก็บเฉพาะ same-origin ok ที่เป็น basic — กัน opaque/redirect หลุดเข้า cache
  if (fresh && fresh.ok && fresh.type === 'basic') {
    try {
      await cache.put(req, fresh.clone());
    } catch {
      // เก็บไม่ได้ก็ยังต้องคืน response ให้หน้าเว็บ
    }
  }
  return fresh;
}

// ── message: ปุ่ม "อัปเดต" จากหน้าเว็บ (ดู src/pwa.ts) ──────────────────────
self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
});

// ── push: ❗ที่ว่างไว้ให้ A3 (Push Notification) มาเติม ───────────────────────
// A3 จะต้อง: อ่าน event.data.json() → self.registration.showNotification(...)
// และเพิ่ม 'notificationclick' handler สำหรับ deep link (A4)
// ⚠️ ตอนนี้ยังไม่มี push subscription (ยังไม่ได้ทำ A3) ⇒ handler นี้ไม่มีทางถูกเรียก
self.addEventListener('push', () => {
  // ยังไม่ทำ — ดูคอมเมนต์ข้างบน
});
