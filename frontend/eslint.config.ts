import { globalIgnores } from 'eslint/config'
import { defineConfigWithVueTs, vueTsConfigs } from '@vue/eslint-config-typescript'
import pluginVue from 'eslint-plugin-vue'
import pluginPlaywright from 'eslint-plugin-playwright'
import pluginVitest from '@vitest/eslint-plugin'
import pluginOxlint from 'eslint-plugin-oxlint'
import skipFormatting from 'eslint-config-prettier/flat'

// To allow more languages other than `ts` in `.vue` files, uncomment the following lines:
// import { configureVueProject } from '@vue/eslint-config-typescript'
// configureVueProject({ scriptLangs: ['ts', 'tsx'] })
// More info at https://github.com/vuejs/eslint-config-typescript/#advanced-setup

export default defineConfigWithVueTs(
  {
    name: 'app/files-to-lint',
    files: ['**/*.{vue,ts,mts,tsx}'],
  },

  // 📚 `public/docs` คือ **ผลลัพธ์ของ `npm run docs:build`** (VitePress) ไม่ใช่ซอร์สของเรา
  //    ⇒ ถูก `.gitignore` ไว้แล้ว และต้องไม่ถูก lint
  //    ⚠️ ลืมบรรทัดนี้แล้ว `npm run lint` จะ **แดงทันทีหลัง build คู่มือ** เพราะ bundle ของ
  //       VitePress มีคอมโพเนนต์ชื่อ `Content` / `Badge` ที่ผิดกติกา multi-word ของเรา
  //       (เจอจริง 28 ต.ค. 2026 หลัง deploy คู่มือขึ้น staging — อาการดูเหมือนโค้ดเราเสีย)
  globalIgnores(['**/dist/**', '**/dist-ssr/**', '**/coverage/**', '**/public/docs/**', '../docs/.vitepress/**']),

  ...pluginVue.configs['flat/essential'],
  vueTsConfigs.recommended,

  {
    ...pluginPlaywright.configs['flat/recommended'],
    files: ['e2e/**/*.{test,spec}.{js,ts,jsx,tsx}'],
  },

  {
    ...pluginVitest.configs.recommended,
    files: ['src/**/__tests__/*'],
  },

  ...pluginOxlint.buildFromOxlintConfigFile('.oxlintrc.json'),

  skipFormatting,
)
