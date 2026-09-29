/**
 * 🏷️ App Badge (A5) — ตัวเลขบนไอคอนแอพ (จุดแดงบนไอคอนที่ติดตั้งไว้)
 *
 * **ทำไมต้องมีโมดูลนี้แทนการเรียก `navigator.setAppBadge()` ตรง ๆ ในสโตร์:**
 * Badging API **ไม่มีอยู่ในทุกเบราว์เซอร์และทุกบริบท** และเมื่อไม่มี มันไม่ได้ "เงียบ" —
 * มันคือ `undefined` ที่เรียกแล้วโยน `TypeError` ถ้าไม่ดัก ⇒ โมดูลนี้รวม 3 เรื่องที่
 * ถ้าต่างคนต่างทำจะไม่ตรงกัน: **การตรวจว่ามี API ไหม · การกลืน error · และการจำค่าล่าสุด**
 *
 * ⚠️ **Badge เป็นของประดับ ไม่ใช่ข้อมูล** — ทุกฟังก์ชันที่นี่ **ไม่โยนและไม่คืน error**
 *    ผู้เรียกจึงไม่ต้อง `try/catch` และห้ามผูกตรรกะธุรกิจไว้กับผลของมัน
 *    (badge ไม่ขึ้น = ผู้ใช้ยังเห็นเลขในแอพครบถ้วน ไม่มีอะไรเสียหาย)
 *
 * ⚠️ **ต้องติดตั้งแอพก่อนจึงจะเห็นจริงบนหลายแพลตฟอร์ม** — Chrome เดสก์ท็อปและ
 *    Android จะปฏิเสธ (reject) ถ้าแอพยังไม่ได้ติดตั้งลงหน้าจอ · Safari/iOS
 *    **ไม่รองรับเลย** (iOS ใช้ badge ผ่าน APNs เท่านั้น ซึ่งอยู่นอกขอบเขตเว็บ)
 *    ⇒ ทั้งสองกรณีคือ "ไม่มี badge" ไม่ใช่ "พัง" ⇒ ต้องกลืน ไม่ใช่รายงานผู้ใช้
 *
 * ⚠️ **ห้ามใช้ `total` จากที่นี่เป็น source of truth** — ยอดจริงอยู่ที่
 *    `getUnreadCounts()` ฝั่งเซิร์ฟเวอร์เสมอ (โมดูลนี้แค่ *แสดง* ค่านั้น)
 *
 * 🔗 คู่กันกับ handler `push` ใน `public/sw.js` — ที่นั่นตั้ง **จุด** (ไม่มีตัวเลขให้ตั้ง
 *    เพราะ SW ไม่รู้ยอดจริง) แล้วแอพเขียนทับด้วย **ตัวเลข** ตอนถูกเปิดขึ้นมา
 */

/**
 * รูปร่างของ API ที่เราจะเรียก — ไม่ใช้ `any` (กฎโปรเจค) และไม่พึ่ง `lib.dom.d.ts`
 * เพราะ TypeScript บางเวอร์ชันยังไม่มีประกาศของ Badging API
 */
interface BadgeNavigator {
  setAppBadge?: (contents?: number) => Promise<void>;
  clearAppBadge?: () => Promise<void>;
}

/**
 * คืน API ถ้าใช้ได้จริง — **ตรวจ `setAppBadge` เป็นตัวตัดสิน** เพราะตัวนั้นขาดไม่ได้
 * (`clearAppBadge` ขาดได้ — มี fallback ดู `clearBadge()`)
 */
function badgeApi(): BadgeNavigator | null {
  if (typeof navigator === 'undefined') return null;
  const nav = navigator as unknown as BadgeNavigator;
  return typeof nav.setAppBadge === 'function' ? nav : null;
}

/** ยอดล่าสุดที่แอพรู้ (`0` = รู้ว่าเป็นศูนย์) — ดู `resync()` ว่าทำไมต้องจำ */
let lastTotal = 0;

/** เตือนครั้งเดียวพอ — ไม่ใช่ error ที่ควรดังทุกครั้ง */
let warned = false;

function note(e: unknown): void {
  if (warned) return;
  warned = true;
  // `debug` ไม่ใช่ `error` — "ยังไม่ได้ติดตั้งแอพ" เป็นภาวะปกติ ไม่ใช่ความผิดพลาด
  // และมีไว้เพื่อตอบคำถาม "ทำไม badge ไม่ขึ้น" ซึ่งเป็นอาการที่หาสาเหตุยากที่สุดของงานนี้
  console.debug('[badge] ตั้งเลขบนไอคอนไม่สำเร็จ — ข้าม (ปกติเกิดเมื่อยังไม่ได้ติดตั้งแอพ)', e);
}

/**
 * เรียก API แล้วกลืนผล — **ห้ามทำให้ผู้เรียกล้มเพราะ badge**
 *
 * ⚠️ ต้องมี `.catch` ที่ promise **และ** `try` รอบการเรียก — เพราะบางเบราว์เซอร์
 *    โยน synchronous (ไม่คืน rejected promise) เมื่อเรียกในบริบทที่ไม่อนุญาต
 *    ⇒ ดักทางเดียวไม่พอ (บทเรียนเดียวกับ `showNotification` ใน `sw.js`)
 */
function call(fn: () => Promise<void> | undefined): void {
  try {
    void Promise.resolve(fn()).catch(note);
  } catch (e) {
    note(e);
  }
}

/** ล้างเลขบนไอคอน (และจำว่า "ยอดคือศูนย์") */
export function clearBadge(): void {
  lastTotal = 0;
  const nav = badgeApi();
  if (!nav) return;
  // ⚠️ `clearAppBadge` มีคู่กับ `setAppBadge` ตามสเปก แต่ไม่การันตีทุกเบราว์เซอร์
  //    ⇒ ถ้าไม่มี ให้ใช้ `setAppBadge(0)` (สเปกนิยามว่า 0 = ไม่มี badge)
  //    ไม่งั้นจะเหลือ badge ค้างถาวรบนเบราว์เซอร์ที่ไม่มีตัวล้าง — ลบไม่ได้เลยจากเว็บ
  call(() => (nav.clearAppBadge ? nav.clearAppBadge() : nav.setAppBadge?.(0)));
}

/**
 * ตั้งเลขบนไอคอนตามยอดที่ยังไม่อ่าน — เรียกซ้ำได้ ปลอดภัยเสมอ
 *
 * ⚠️ ค่าที่ไม่ใช่จำนวนเต็มบวก (ติดลบ / `NaN` / `Infinity` / ทศนิยม) ถูกปรับเป็น `0`
 *    **ก่อน** ส่งออกไป เพราะ `setAppBadge` ปฏิเสธค่าที่ไม่ใช่จำนวนเต็มที่ไม่ติดลบ
 *    (`TypeError`) ⇒ ปรับที่เดียวตรงนี้ ดีกว่าไปพังเงียบ ๆ ที่ปลายทาง
 */
export function syncBadge(total: number): void {
  const nav = badgeApi();
  if (!nav) return;
  const n = Number.isFinite(total) && total > 0 ? Math.floor(total) : 0;
  lastTotal = n;
  if (n > 0) call(() => nav.setAppBadge?.(n));
  else clearBadge();
}

/**
 * ⭐ **เขียน badge ทับด้วยยอดล่าสุดที่รู้ — โดยไม่ยิงเครือข่าย**
 *
 * **ทำไมต้องมี:** ระหว่างที่แท็บถูกพัก (background) ถ้ามี push เข้ามา **service worker
 * จะเขียนทับตัวเลขด้วย "จุด"** (เพราะ SW ไม่รู้ยอดจริง — ดู `sw.js`) ⇒ พอกลับมาเปิดแท็บ
 * ยอดในสโตร์ **ไม่ได้เปลี่ยน** (ไม่มี poke ไม่มี snapshot) ⇒ ไม่มีอะไรเรียก `syncBadge()`
 * ⇒ **badge ค้างเป็นจุดจนกว่า poll รอบถัดไปจะมาถึง (นานสุด 30 วิ)**
 * ทั้งที่แอพรู้คำตอบอยู่แล้ว ⇒ ที่นี่จึงเขียนทับด้วยค่าที่จำไว้ทันทีตอนกลับมาโฟกัส
 *
 * ⚠️ ห้ามแทนที่ด้วย `fetchCounts()` — นั่นยิงเครือข่ายทุกครั้งที่สลับแท็บ
 *    (และสตรีมมี `visibilitychange` ที่ต่อใหม่ + ส่ง snapshot อยู่แล้ว — ดู
 *    `services/notificationStream.ts`) ⇒ ที่นี่เป็น "ปิดช่องว่าง" ไม่ใช่ "ดึงข้อมูล"
 */
function resync(): void {
  // `document.hidden` — เรียกตอน *กลับมา* เท่านั้น (ตอนซ่อนไม่ต้องทำอะไร)
  if (document.hidden) return;
  const nav = badgeApi();
  if (!nav) return;
  if (lastTotal > 0) call(() => nav.setAppBadge?.(lastTotal));
  // `lastTotal === 0` = "รู้ว่าเป็นศูนย์แล้ว" ⇒ badge ต้องว่าง ไม่ต้องทำอะไร
  // (ถ้ามีจุดจาก push ค้างอยู่ ตอนนี้เราตั้ง 0 ไปแล้วตอน `clearBadge` — แต่ถ้า SW
  //  เพิ่งตั้งจุดหลัง clearBadge ให้ poll/สตรีมเป็นคนแก้ ไม่ใช่เดาที่นี่)
}

// ผูก listener ตอน import (แบบเดียวกับ `pwa.ts`) — ไฟล์นี้ถูก import จากสโตร์
// ซึ่งอยู่ในเส้นทางที่แอพโหลดอยู่แล้ว จึงไม่มีค่าใช้จ่ายเพิ่ม
if (typeof document !== 'undefined') {
  document.addEventListener('visibilitychange', resync);
}
