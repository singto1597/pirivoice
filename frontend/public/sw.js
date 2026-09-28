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

// ⚠️ ขึ้นเวอร์ชันเมื่อ **รายการไฟล์หรือวิธี precache เปลี่ยน** — ไม่ใช่ทุก deploy
//    (asset ของแอพมี content hash ในชื่ออยู่แล้ว จึงไม่ต้องพึ่งเวอร์ชันนี้)
//    v2: เปลี่ยนมาใช้ precacheStrict — ของเดิมเคยเก็บ HTML ทับไอคอนได้ (ดูคอมเมนต์ล่าง)
//    v3: ไอคอนเปลี่ยนเป็นโลโก้โรงเรียนล้วน ⇒ ขึ้นเวอร์ชันเพื่อทิ้ง cache เก่า
//        (ถ้าไม่ขึ้น ของเดิมจะค้างใน cache ใต้ URL เดิม แล้วผู้ใช้ที่ติดตั้งไว้จะเห็นไอคอนเก่า)
const SHELL_CACHE = 'piri-shell-v3';

// ไฟล์ที่ต้องมีแน่ ๆ — precache ตอน install
// ⚠️ ถ้าไฟล์ใดหาย จะถูกรายงานใน console (ไม่ทำให้ install ล้มทั้งอัน — ดู precacheStrict)
//    (ไอคอน generate ไว้ใน `public/icons/` แล้ว — อย่าลบ)
// ⚠️ ไอคอนต่อ `?v=` ให้ตรงกับ `manifest.json` เสมอ — `cache.match()` นับ query เป็นส่วนหนึ่ง
//    ของคีย์ ⇒ สอง URL นี้เป็นคนละรายการกัน ใส่ไม่ตรงจะได้ไอคอนเก่าค้างอยู่อีกชุด
const SHELL_ASSETS = [
  '/',
  '/index.html',
  '/manifest.json',
  '/logos/school-logo.png',
  '/icons/icon-192.png?v=3',
  '/icons/icon-512.png?v=3',
  '/icons/icon-512-maskable.png?v=3',
  '/icons/apple-touch-icon.png?v=3',
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

/**
 * precache ที่ **ตรวจเนื้อก่อนเก็บ** — ไม่ใช่ `cache.addAll`
 *
 * ⚠️ **นี่คือบั๊กจริงที่เคยเกิด**: nginx ของโปรเจคนี้ใช้ `try_files $uri /index.html`
 *    ⇒ ทุก path ที่ไม่มีไฟล์จริงจะได้ **HTTP 200 พร้อมเนื้อหา `index.html`** (ไม่ใช่ 404)
 *    ⇒ `cache.addAll` เห็น `res.ok === true` ก็เก็บ **หน้า HTML ไว้ใต้ชื่อไอคอน/JS**
 *    แล้ว `handleStatic` เป็น cache-first ⇒ ของเสียติดอยู่ใน cache **ถาวร**
 *    จนกว่าจะขึ้น `SHELL_CACHE` — อาการที่เห็นคือ "ไอคอน/ไฟล์โหลดไม่ขึ้น" แบบหาสาเหตุยาก
 *    (กรณีจริง: Cloudflare แคช SPA fallback ไว้ที่ `/icons/icon-192.png`)
 *
 * ⇒ ต้องเช็ค `Content-Type` ก่อนเก็บเสมอ: ไฟล์ที่ไม่ใช่ HTML ต้องไม่ได้ `text/html`
 *   และ **ไม่ throw** เมื่อไฟล์ใดหาย — SW ที่ติดตั้งไม่สำเร็จแย่กว่าการขาดไอคอนหนึ่งใบ
 *   (รายงานทาง console แทน ให้เห็นตอน debug)
 */
async function precacheStrict(cache, urls) {
  const failed = [];
  await Promise.all(
    urls.map(async (u) => {
      try {
        const res = await fetch(u, { cache: 'reload' });
        const type = res.headers.get('Content-Type') || '';
        const wantsHtml = u === '/' || u.endsWith('.html');

        if (!res.ok || (!wantsHtml && type.includes('text/html'))) {
          failed.push(`${u} (${res.status} ${type || 'ไม่ระบุ type'})`);
          return;
        }
        await cache.put(u, res);
      } catch (err) {
        failed.push(`${u} (${err})`);
      }
    }),
  );
  if (failed.length) {
    console.warn('[sw] precache ไม่สำเร็จบางไฟล์:', failed.join(', '));
  }
  return failed;
}

// ── install: precache shell + asset ที่ Vite hash ไว้ ──────────────────────
self.addEventListener('install', (event) => {
  event.waitUntil(
    (async () => {
      const cache = await caches.open(SHELL_CACHE);

      // ไฟล์คงที่ — ตรวจเนื้อก่อนเก็บ (ดูเหตุผลใน precacheStrict)
      await precacheStrict(cache, SHELL_ASSETS);

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

/** ของที่เก็บไว้ต้องไม่ใช่หน้า HTML (ดูเหตุผลใน precacheStrict) — กันของเสียที่ค้างจากรุ่นก่อน */
function isUsableAsset(res) {
  return !(res.headers.get('Content-Type') || '').includes('text/html');
}

async function handleStatic(req) {
  const cache = await caches.open(SHELL_CACHE);
  const hit = await cache.match(req);
  if (hit && isUsableAsset(hit)) return hit;

  const fresh = await fetch(req);
  // ⚠️ เก็บเฉพาะ same-origin ok ที่เป็น basic — กัน opaque/redirect หลุดเข้า cache
  if (fresh && fresh.ok && fresh.type === 'basic' && isUsableAsset(fresh)) {
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

// ── push: ข้อความที่เซิร์ฟเวอร์ส่งมา (A3) ────────────────────────────────────
// รูป payload เป็น **สัญญาระหว่าง backend กับไฟล์นี้** — ฝั่งโน้นคือ
// `services/push_service.build_payload()` (pure function มีเทสต์ล็อกไว้)
//   { title, body, tag, data: { url, notification_id, type, entity_type, … } }
// ⚠️ เปลี่ยนชื่อคีย์ที่ฝั่งใดฝั่งหนึ่ง = อีกฝั่งพังเงียบ ๆ (ไม่มี type ให้ compiler จับ)
const DEFAULT_PUSH_URL = '/app/notifications';

self.addEventListener('push', (event) => {
  // ⚠️ `event.data` เป็น **null ได้** (push เปล่า / ผู้ให้บริการส่งสัญญาณไม่มีเนื้อหา)
  //    และ `.json()` **โยน** ถ้าเนื้อหาไม่ใช่ JSON ⇒ ต้องครอบ try/catch ไม่งั้น
  //    handler ตายทั้งอันและผู้ใช้ไม่เห็นอะไรเลยโดยที่เราไม่รู้
  let payload = null;
  try {
    payload = event.data ? event.data.json() : null;
  } catch {
    payload = null;
  }

  // ไม่มีเนื้อหาให้แสดง — จบเงียบ ๆ (ไม่ throw: ปล่อยให้เป็น error ใน console ไม่มีประโยชน์)
  if (!payload || !payload.title) return;

  event.waitUntil(
    self.registration.showNotification(payload.title, {
      body: payload.body || '',
      // ⭐ ใช้ `?v=3` ให้ตรงกับ `SHELL_ASSETS` ด้านบน — `cache.match()` นับ query เป็น
      //    ส่วนหนึ่งของคีย์ ⇒ URL เปล่ากับ URL มี `?v=` เป็นคนละรายการ
      //    และไอคอนที่มี `?v=` ถูก precache ไว้แล้ว ⇒ ทำงานได้ตอนออฟไลน์ด้วย
      //    (URL เปล่าเคยถูก Cloudflare แคชเป็นหน้า HTML ทับไปแล้วรอบหนึ่ง — ดู SHELL_ASSETS)
      icon: '/icons/icon-192.png?v=3',
      // `badge` ใช้เฉพาะ Android (จุดเล็ก ๆ ในแถบสถานะ) — ไม่มี asset ขาวดำในโปรเจค
      // ⇒ ใช้ไอคอนเดียวกัน (Android จะ render เป็นทรงทึบ) ดีกว่าไม่ส่งเลย
      badge: '/icons/icon-192.png?v=3',
      // `tag` = ให้อันใหม่ **แทนที่** อันเก่าของเรื่องเดียวกัน — กันมือถือขึ้นซ้ำ 5 อัน
      //   เวลามีคนตอบรัว ๆ หรือ worker ส่งซ้ำหลัง retry
      tag: payload.tag || undefined,
      data: payload.data || { url: DEFAULT_PUSH_URL },
    }),
  );
});

// ── notificationclick: ผู้ใช้แตะ notification (deep link ของ A4 มาที่นี่) ─────
self.addEventListener('notificationclick', (event) => {
  event.notification.close();

  const raw = (event.notification.data && event.notification.data.url) || DEFAULT_PUSH_URL;
  const target = new URL(raw, self.location.origin);

  // ⚠️ **ต้องเป็น `/app/notifications` ไม่ใช่ `/notifications`** — route เปล่าใน router
  //    เป็น **string redirect** ที่ทำ query หลุด ⇒ deep link ของ A4 (เช่น `?focus=12`)
  //    จะหายไปทั้งอันถ้าชี้ไป `/notifications` — และอาการคือ "กดแล้วไม่ไปไหน" หาสาเหตุยาก
  event.waitUntil(
    (async () => {
      const windows = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
      const sameOrigin = windows.filter((c) => {
        try {
          return new URL(c.url).origin === target.origin;
        } catch {
          return false;
        }
      });

      if (sameOrigin.length) {
        // ⭐ เลือกตัวที่ **อยู่ในการควบคุมของ SW นี้** ก่อน — `client.navigate()` โยน
        //    ถ้า client ไม่อยู่ใต้ scope (เกิดขึ้นได้เพราะ `includeUncontrolled: true`)
        const controlled = sameOrigin.find((c) => c.frameType === 'top-level' && 'navigate' in c);
        const tab = controlled || sameOrigin[0];
        await tab.focus();
        try {
          await tab.navigate(target.href);
        } catch {
          // พาไปไม่ได้ก็ไม่เป็นไร — การโฟกัสแท็บยังมีค่าอยู่ดี (อย่าปล่อยให้ throw
          // ทำให้ waitUntil ล้ม ซึ่งจะทำให้เบราว์เซอร์มองว่า handler ทำงานไม่สำเร็จ)
        }
        return;
      }

      // ไม่มีแท็บของแอพเปิดอยู่เลย → เปิดใหม่
      if (self.clients.openWindow) await self.clients.openWindow(target.href);
    })(),
  );
});
