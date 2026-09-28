/// <reference types="vite/client" />

/**
 * Build id ที่ `vite.config.ts` ฉีดเข้ามา (short git SHA)
 * ใช้ต่อท้าย URL ของ service worker — ดูเหตุผลใน `src/pwa.ts`
 */
declare const __BUILD_ID__: string
