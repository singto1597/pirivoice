import { defineStore } from 'pinia';
import { ref } from 'vue';
import { getUnreadCounts, markRead } from '@/services/notification';
import type { MarkReadPayload } from '@/types/notification';

// 🔔 Unread badge state — poll ทุก 30 วิ (pattern เดียวกับ ImportStudents.vue)
//   MainLayout เรียก startPolling() → badge บนเมนู + กระดิ่งอัปเดตเอง

const POLL_INTERVAL_MS = 30_000;
const POLL_FAIL_LIMIT = 3;

export const useNotificationsStore = defineStore('notifications', () => {
  const counts = ref<Record<string, number>>({});
  const total = ref(0);

  // ⚠️ **ปล่อย error ออกไปโดยเจตนา — ห้ามกลืนในนี้**
  //    `startPolling()` นับ `failStreak` จาก catch ของ call นี้ ⇒ ถ้ากลืนซะเอง
  //    catch นั้นจะไม่มีวันทำงาน แล้ว `POLL_FAIL_LIMIT` (หยุดหลัง fail 3 ครั้งติด)
  //    ก็เป็นโค้ดตาย ⇒ ยิง `/api/notifications/unread-count` ทุก 30 วิ ตลอดกาล
  //    แม้ backend ล่ม — ผู้ที่ต้องกลืนคือ call site (ดู `read()` กับ `startPolling()`)
  async function fetchCounts() {
    const res = await getUnreadCounts();
    counts.value = res.counts;
    total.value = res.total;
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

  return { counts, total, fetchCounts, read, startPolling, stopPolling };
});
