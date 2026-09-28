<!-- eslint-disable vue/multi-word-component-names -- 'InstallPrompt' = ชื่อที่อ่านออกตรงตัว -->
<script setup lang="ts">
/**
 * แบนเนอร์ติดตั้ง PWA + แบนเนอร์ "มีเวอร์ชันใหม่" (A1)
 *
 * วางไว้ใน `MainLayout` (หน้าหลังล็อกอินเท่านั้น — ไม่รบกวนหน้า Landing สาธารณะ)
 *
 * ⚠️ **ไม่เดาจาก user agent** — แสดงเฉพาะเมื่อเบราว์เซอร์ยิง `beforeinstallprompt`
 *    จริง (Chrome/Edge/Android) ส่วน iOS Safari ไม่ยิงเลย ⇒ ผู้ใช้ iOS จะไม่เห็น
 *    ซึ่งถูกต้อง ดีกว่าโชว์ปุ่มที่กดแล้วไม่มีอะไรเกิดขึ้น
 *
 * ⚠️ **ชวนเฉพาะมือถือ/แท็บเล็ต** — เงื่อนไข `(pointer: coarse)` อยู่ใน `pwa.ts` แล้ว
 *    ⇒ คอมโพเนนต์นี้ไม่ต้องรู้เรื่องนั้นเลย · เปิดในคอมจะเงียบสนิทตามที่เจ้าของระบบต้องการ
 *    (ใครอยากติดตั้งในคอม → การ์ด "ติดตั้งแอป" ใน Profile)
 *
 * ⚠️ **ไม่ auto-reload ตอนมีเวอร์ชันใหม่** — ให้ผู้ใช้กดเอง กันตัดกลางทาง
 *    ตอนกำลังกรอกเรื่องอยู่ (เหตุผลเดียวกับที่ sw.js ไม่เรียก skipWaiting เอง)
 */
import { ref } from 'vue'
import Swal from 'sweetalert2'
import {
  applyUpdate,
  dismissInstall,
  dismissIosHint,
  promptInstall,
  showInstallBanner,
  showIosHint,
  showUpdateBanner,
} from '@/pwa'

const isWorking = ref(false)

async function onInstall() {
  if (isWorking.value) return
  isWorking.value = true
  try {
    const outcome = await promptInstall()
    if (outcome === 'accepted') {
      await Swal.fire({
        icon: 'success',
        title: 'ติดตั้งแล้ว',
        text: 'เปิด PIRIvoice ได้จากไอคอนบนหน้าจอเลย',
        confirmButtonColor: '#b91c1c',
      })
    }
    // 'dismissed' = ผู้ใช้ปิดหน้าต่างของเบราว์เซอร์เอง — ไม่ต้องแจ้งอะไร
  } finally {
    isWorking.value = false
  }
}
</script>

<template>
  <!-- มีเวอร์ชันใหม่ → สำคัญกว่าชวนติดตั้ง ⇒ แสดงแทนกัน ไม่ซ้อนกัน -->
  <Transition name="prompt">
    <div
      v-if="showUpdateBanner"
      class="banner-anchor pointer-events-none fixed inset-x-0 z-40 px-3"
    >
      <div
        class="pointer-events-auto mx-auto flex w-full max-w-[440px] items-center gap-3 rounded-2xl border border-stone-200 bg-white px-4 py-3 shadow-lg shadow-stone-900/5"
      >
        <span class="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[#B91C1C]/10 text-[#B91C1C]">
          <i class="bi bi-arrow-repeat text-lg"></i>
        </span>
        <div class="min-w-0 flex-1">
          <p class="text-sm font-bold text-stone-900">มีเวอร์ชันใหม่ของ PIRIvoice</p>
          <p class="mt-0.5 text-[11px] font-medium text-stone-500">อัปเดตเมื่อพร้อม — ระบบจะโหลดหน้าใหม่ให้</p>
        </div>
        <button
          type="button"
          class="shrink-0 rounded-xl bg-[#B91C1C] px-3.5 py-2 text-xs font-bold text-white transition-colors hover:bg-[#991B1B]"
          @click="applyUpdate"
        >
          อัปเดต
        </button>
      </div>
    </div>
  </Transition>

  <Transition name="prompt">
    <div
      v-if="showInstallBanner && !showUpdateBanner"
      class="banner-anchor pointer-events-none fixed inset-x-0 z-40 px-3"
    >
      <div
        class="pointer-events-auto mx-auto flex w-full max-w-[440px] items-center gap-3 rounded-2xl border border-stone-200 bg-white px-4 py-3 shadow-lg shadow-stone-900/5"
      >
        <span class="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[#B91C1C] text-white">
          <i class="bi bi-phone text-lg"></i>
        </span>
        <div class="min-w-0 flex-1">
          <p class="text-sm font-bold text-stone-900">ติดตั้ง PIRIvoice</p>
          <p class="mt-0.5 text-[11px] font-medium text-stone-500">เพิ่มลงหน้าจอ เปิดได้เร็วเหมือนแอพ</p>
        </div>
        <button
          type="button"
          :disabled="isWorking"
          class="shrink-0 rounded-xl bg-[#B91C1C] px-3.5 py-2 text-xs font-bold text-white transition-colors hover:bg-[#991B1B] disabled:opacity-60"
          @click="onInstall"
        >
          <i v-if="isWorking" class="bi bi-arrow-repeat animate-spin"></i>
          <span v-else>ติดตั้ง</span>
        </button>
        <button
          type="button"
          aria-label="ปิด"
          class="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-stone-400 transition-colors hover:bg-stone-100 hover:text-stone-600"
          @click="dismissInstall"
        >
          <i class="bi bi-x-lg text-xs"></i>
        </button>
      </div>
    </div>
  </Transition>

  <!--
    iOS Safari — ไม่มี `beforeinstallprompt` และไม่มี API ติดตั้งใด ๆ เลย
    เบราว์เซอร์ห้ามเว็บติดตั้งแอพเองโดยไม่ให้ผู้ใช้ยืนยัน ⇒ ทางเดียวที่ทำได้คือ **สอน**

    ⚠️ สองการ์ดนี้ไม่มีทางซ้อนกัน — iOS ไม่ยิง `beforeinstallprompt` เลย
       จึงไม่มีทางที่ showInstallBanner จะเป็น true พร้อมกับ showIosHint
  -->
  <Transition name="prompt">
    <div
      v-if="showIosHint && !showUpdateBanner"
      class="banner-anchor pointer-events-none fixed inset-x-0 z-40 px-3"
    >
      <div
        class="pointer-events-auto mx-auto flex w-full max-w-[440px] items-start gap-3 rounded-2xl border border-stone-200 bg-white px-4 py-3 shadow-lg shadow-stone-900/5"
      >
        <span class="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[#B91C1C] text-white">
          <i class="bi bi-phone text-lg"></i>
        </span>
        <div class="min-w-0 flex-1">
          <p class="text-sm font-bold text-stone-900">ติดตั้ง PIRIvoice</p>
          <p class="mt-0.5 text-[11px] font-medium text-stone-500">
            เพิ่มลงหน้าจอ เปิดได้เร็วเหมือนแอพ
          </p>
          <ol class="mt-1.5 space-y-0.5 text-[11px] font-medium text-stone-600">
            <li>
              1. แตะปุ่ม <i class="bi bi-box-arrow-up text-stone-800"></i> แชร์ ที่แถบล่างจอ
            </li>
            <li>2. เลือก “เพิ่มไปที่หน้าจอ”</li>
          </ol>
        </div>
        <button
          type="button"
          aria-label="ปิด"
          class="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-stone-400 transition-colors hover:bg-stone-100 hover:text-stone-600"
          @click="dismissIosHint"
        >
          <i class="bi bi-x-lg text-xs"></i>
        </button>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
/* ⚠️ ใช้ class + media query ไม่ใช่ inline style — เพราะ inline style ชนะ
   `lg:` utility เสมอ (เขียน `lg:bottom-6` ไว้ด้วยกันแล้วจะไม่มีผลเงียบ ๆ)
   มือถือ: ลอยเหนือ bottom tab bar · จอใหญ่: tab bar ซ่อน ⇒ ชิดขอบล่างได้ */
.banner-anchor {
  bottom: calc(env(safe-area-inset-bottom, 0px) + 5.6rem);
}
@media (min-width: 1024px) {
  .banner-anchor {
    bottom: 1.5rem;
  }
}

/* เด้งขึ้นจากขอบล่างแบบนุ่ม ๆ — ไม่ใช่ slide จากนอกจอ (จะดูเหมือนบั๊กบน iOS) */
.prompt-enter-active,
.prompt-leave-active {
  transition:
    opacity 0.25s ease,
    transform 0.25s cubic-bezier(0.175, 0.885, 0.32, 1);
}
.prompt-enter-from,
.prompt-leave-to {
  opacity: 0;
  transform: translateY(0.75rem);
}

/* ♿ เคารพผู้ที่ปิดแอนิเมชัน */
@media (prefers-reduced-motion: reduce) {
  .prompt-enter-active,
  .prompt-leave-active {
    transition: none;
  }
  .prompt-enter-from,
  .prompt-leave-to {
    transform: none;
  }
  .animate-spin {
    animation: none;
  }
}
</style>
