import { createApp } from 'vue'
import { createPinia } from 'pinia'
import './assets/main.css'

import App from './App.vue'
import router from './router'
import { registerPwa } from './pwa'

const app = createApp(App)

app.use(createPinia())
app.use(router)

app.mount('#app')

// 📱 PWA (A1) — ลงทะเบียน service worker + ดัก beforeinstallprompt
// ⚠️ เรียก **หลัง** mount เพื่อไม่ให้การลงทะเบียน SW แย่ง main thread กับการวาดหน้าจอแรก
//    (ในไฟล์นี้ลงทะเบียนเฉพาะ production — ดูเหตุผลใน src/pwa.ts)
registerPwa()
