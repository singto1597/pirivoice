import { defineStore } from 'pinia';
import { ref } from 'vue';
import { getUnreadCounts, markRead } from '@/services/notification';
import { openNotificationStream } from '@/services/notificationStream';
import { clearBadge, syncBadge } from '@/badge';
import type { StreamState } from '@/services/notificationStream';
import type { MarkReadPayload, UnreadCounts } from '@/types/notification';

// 🔔 Unread badge state — มี 2 กลไกที่ทำงานคู่กัน (ไม่ใช่แทนกัน)
//
//   1. **stream (SSE)** — อัปเดตทันที (~1 วิ) ตอนเปิดแอพอยู่  ← `startStream()`
//   2. **poll ทุก 30 วิ** — ตาข่ายชั้นสอง                        ← `startPolling()`
//
//   ⭐ **ห้ามลบ poll ทิ้งแม้ stream จะทำงานได้** — stream เป็น "ทำให้เร็วขึ้น"
//      ไม่ใช่ "แหล่งความถูกต้อง" · ถ้า LISTEN ฝั่งเซิร์ฟเวอร์ตาย / proxy ตัด
//      connection / เบราว์เซอร์ระงับแท็บเบื้องหลัง ⇒ poll คือสิ่งที่ทำให้ badge
//      ยัง *ถูกต้อง* (ช้าได้ แต่ไม่ค้าง) · ถ้าลบ poll แล้ว stream มีปัญหาเงียบ ๆ
//      badge จะค้างถาวรโดยไม่มีใครรู้ — ซึ่งเป็นอาการเดิมที่ผู้ใช้บ่นเป๊ะ ๆ

const POLL_INTERVAL_MS = 30_000;
const POLL_FAIL_LIMIT = 3;

// ⏱️ รวมสัญญาณที่ซ้อนกันให้เหลือการถามยอดครั้งเดียว
//   (fanout ครั้งเดียวอาจได้หลาย poke ถ้าผู้ใช้มีหลายแท็บ · และ `mark_read(all)`
//    ก็อาจตามมาด้วย poke อีก ⇒ ไม่ต้องถามซ้ำ ๆ ในเสี้ยววินาที)
const POKE_DEBOUNCE_MS = 300;

export const useNotificationsStore = defineStore('notifications', () => {
  const counts = ref<Record<string, number>>({});
  const total = ref(0);
  // 📡 สถานะสตรีม — ใช้เพื่อวินิจฉัย ("ทำไม badge ไม่ขยับ") ไม่มีตรรกะตัดสินใจจากค่านี้
  const streamState = ref<StreamState>('stopped');

  // ⭐ **ทางเดียวที่ยอดจะเปลี่ยน** — ทั้ง `fetchCounts()` (ถามเอง) และ `applySnapshot()`
  //    (สตรีมส่งมา) ต้องผ่านที่นี่ ⇒ badge บนไอคอนแอพ (A5) ไม่มีทางหลุด sync
  //    ⚠️ ถ้ามีคนเพิ่มทางที่สามแล้วเขียน `total.value = …` ตรง ๆ badge จะค้าง
  //    โดยไม่มีอะไรฟ้อง (ไม่ใช่ type error ไม่ใช่เทสต์พัง) — ที่นี่คือจุดเดียวที่ถูก
  function applyCounts(next: UnreadCounts) {
    counts.value = next.counts;
    total.value = next.total;
    syncBadge(next.total);
  }

  // ⚠️ **ปล่อย error ออกไปโดยเจตนา — ห้ามกลืนในนี้**
  //    `startPolling()` นับ `failStreak` จาก catch ของ call นี้ ⇒ ถ้ากลืนซะเอง
  //    catch นั้นจะไม่มีวันทำงาน แล้ว `POLL_FAIL_LIMIT` (หยุดหลัง fail 3 ครั้งติด)
  //    ก็เป็นโค้ดตาย ⇒ ยิง `/api/notifications/unread-count` ทุก 30 วิ ตลอดกาล
  //    แม้ backend ล่ม — ผู้ที่ต้องกลืนคือ call site (ดู `read()` กับ `startPolling()`)
  async function fetchCounts() {
    applyCounts(await getUnreadCounts());
  }

  // mark อ่าน แล้ว refetch ทันที (badge ลดทันทีไม่ต้องรอ poll รอบหน้า)
  // กลืน error เอง → caller ใช้ `void read(...)` ได้ปลอดภัย (ไม่เกิด unhandled rejection)
  // คืน `true/false` ให้ caller ที่อยากรู้ผล (เช่น NotificationCenter ที่ต้องเด้ง Swal)
  // — ต้องคืนค่า ไม่ใช่ throw เพราะมี caller 6 จุดที่เรียกแบบ `void read(...)`
  async function read(payload: MarkReadPayload): Promise<boolean> {
    let ok = true;
    try {
      await markRead(payload);
    } catch {
      // best-effort: badge จะอัปเดตเองตอน poll รอบหน้า
      ok = false;
    }
    try {
      await fetchCounts();
    } catch {
      // นับ badge ไม่ได้ก็ไม่ควรทำให้ mark-read ที่สำเร็จแล้วดูเหมือนล้มเหลว
    }
    return ok;
  }

  // ---- polling ----
  let timer: number | null = null;
  let inFlight = false;
  let failStreak = 0;

  function startPolling() {
    if (timer !== null) return;
    // รอบแรกพลาดได้ — ยังไม่นับ failStreak ให้ interval เป็นคนนับ (กัน unhandled rejection)
    void fetchCounts().catch(() => {});
    timer = window.setInterval(async () => {
      if (inFlight) return;
      inFlight = true;
      try {
        await fetchCounts();
        failStreak = 0;
      } catch {
        failStreak += 1;
        if (failStreak >= POLL_FAIL_LIMIT) stopPolling();
      } finally {
        inFlight = false;
      }
    }, POLL_INTERVAL_MS);
  }

  function stopPolling() {
    if (timer !== null) {
      window.clearInterval(timer);
      timer = null;
    }
  }

  // ---- stream (SSE) ----

  /** ใช้ยอดที่ server ส่งมาตรง ๆ — ไม่ต้องยิงถามซ้ำ (payload คือ `{counts,total}` เป๊ะ) */
  function applySnapshot(snapshot: UnreadCounts) {
    applyCounts(snapshot);
  }

  /**
   * 🏷️ ล้างยอดและ **ลบเลขบนไอคอนแอพ** — เรียกตอนออกจากระบบเท่านั้น
   *
   * **ทำไมต้องลบ:** badge เกาะกับ **ไอคอน** ซึ่งเป็นของ *เครื่อง* ไม่ใช่ของ *บัญชี* —
   * เครื่องเดียวกันมีหลายคนใช้ (ห้องคอม / มือถือโรงเรียน) ⇒ ถ้าไม่ลบ คนถัดไปที่มอง
   * หน้าจอจะเห็น "มี 7 เรื่องค้าง" ของคนก่อนหน้า ทั้งที่ยังไม่ทันล็อกอินด้วยซ้ำ
   * (หลักเดียวกับที่ `sw.js` ห้าม cache `/api/*` และที่ `api.ts` ล้าง token ตอน 401)
   */
  function resetBadge() {
    counts.value = {};
    total.value = 0;
    clearBadge();
  }

  let pokeTimer: number | null = null;

  // รวม poke ที่ซ้อนกัน: ตัวแรกตั้งเวลา ตัวถัดมาที่ตกในช่วงเดียวกันถูกกลืนไปเลย
  // (ไม่ใช่ debounce แบบเลื่อนเวลา — poke แรกต้องไม่ถูกเลื่อนออกไปเรื่อย ๆ)
  function onPoke() {
    if (pokeTimer !== null) return;
    pokeTimer = window.setTimeout(() => {
      pokeTimer = null;
      // กลืน error: ถ้าถามไม่ได้ เดี๋ยว poll รอบถัดไปเก็บให้ (ไม่ควรทำให้ stream ตาย)
      void fetchCounts().catch(() => {});
    }, POKE_DEBOUNCE_MS);
  }

  // ตัวปิดสตรีม (คืนจาก openNotificationStream) — null = ยังไม่เปิด
  let closeStream: (() => void) | null = null;

  function startStream() {
    if (closeStream) return; // idempotent — เรียกซ้ำได้ (MainLayout อาจ mount หลายรอบ)
    closeStream = openNotificationStream({
      onSnapshot: applySnapshot,
      onPoke,
      onStateChange: (s) => {
        streamState.value = s;
      },
    });
  }

  function stopStream() {
    if (closeStream) {
      closeStream();
      closeStream = null;
    }
    streamState.value = 'stopped';
    if (pokeTimer !== null) {
      window.clearTimeout(pokeTimer);
      pokeTimer = null;
    }
  }

  return {
    counts, total, streamState,
    fetchCounts, read, resetBadge,
    startPolling, stopPolling,
    startStream, stopStream,
  };
});
