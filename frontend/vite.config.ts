import { execSync } from 'node:child_process'
import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import vueJsx from '@vitejs/plugin-vue-jsx'
import vueDevTools from 'vite-plugin-vue-devtools'

/**
 * รหัสของ build นี้ — ใช้ต่อท้าย URL ของ service worker (`/sw.js?v=<id>`)
 *
 * ⚠️ **จำเป็น ไม่ใช่ของประดับ** — Cloudflare แทนที่ `Cache-Control` จาก origin
 *    ด้วย `max-age=14400` ของตัวเอง ⇒ `/sw.js` ตรง ๆ ค้างได้ถึง 4 ชม. แม้ nginx
 *    จะส่ง `no-cache, must-revalidate` (ดู docs/skills.md) การเปลี่ยน URL ทุก build
 *    ทำให้ CDN ไม่มี URL เก่าให้เสิร์ฟ ⇒ SW อัปเดตถึงมือผู้ใช้เสมอ
 */
function buildId(): string {
  try {
    return execSync('git rev-parse --short HEAD', { stdio: ['ignore', 'pipe', 'ignore'] })
      .toString()
      .trim()
  } catch {
    // ไม่มี git (เช่น build จาก tarball) — ใช้นาฬิกาแทน ดีกว่าได้ค่าเดียวกันตลอด
    return String(Date.now())
  }
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    vue(),
    vueJsx(),
    vueDevTools(),
  ],
  define: {
    __BUILD_ID__: JSON.stringify(buildId()),
  },
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    },
  },
  server: {
    // TODO: ใส่ domain ของโปรเจค PIRIvoice เมื่อ deploy (เพิ่มที่ allowedHosts)
  }
})
