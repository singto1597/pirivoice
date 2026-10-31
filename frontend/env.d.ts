/// <reference types="vite/client" />

/**
 * Build id ที่ `vite.config.ts` ฉีดเข้ามา (short git SHA)
 * ใช้ต่อท้าย URL ของ service worker — ดูเหตุผลใน `src/pwa.ts`
 */
declare const __BUILD_ID__: string

/**
 * เลขเวอร์ชัน SemVer ของแอป ที่ `vite.config.ts` อ่านจาก `package.json`
 * ⚠️ ต้องอ่านใส่ const ที่ top-level ของ `<script setup>` ก่อนใช้ใน template —
 *    ถ้าเขียน `__APP_VERSION__` ใน template ตรง ๆ Vue จะคอมไพล์เป็น
 *    `_ctx.__APP_VERSION__` แล้ว Vite define แทนที่กลาง member expression
 */
declare const __APP_VERSION__: string
