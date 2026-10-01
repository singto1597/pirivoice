<!-- eslint-disable vue/multi-word-component-names -- ชื่อ Login ตาม spec (หน้าล็อกอิน) -->
<script setup lang="ts">
import { ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import Swal from 'sweetalert2';
import { useAuthStore } from '@/stores/auth';
import { REDIRECT_QUERY, safeRedirect } from '@/router/redirect';

const authStore = useAuthStore();
const router = useRouter();
const route = useRoute();

const username = ref('');
const password = ref('');
const isLoading = ref(false);
const showPassword = ref(false);

// ฟังก์ชันหา Route ปลายทางหลัง login — ทุกบทบาทเข้าหน้า Welcome/Home
// (หน้า Welcome ปรับเนื้อหาตามสิทธิ์ของแต่ละคนเอง)
function homeRouteName(): string {
  return 'home';
}

async function handleLogin() {
  if (!username.value || !password.value) {
    Swal.fire({ icon: 'warning', title: 'ข้อมูลไม่ครบถ้วน', text: 'กรุณากรอกรหัสนักเรียนและรหัสผ่าน' });
    return;
  }

  isLoading.value = true;
  try {
    await authStore.login(username.value.trim(), password.value);

    // 🔗 ปลายทางที่ผู้ใช้ตั้งใจจะไป (deep link จาก push — A4 / ลิงก์ที่แชร์มา) ถ้ามีและ **ผ่านด่าน**
    //    ⚠️ `safeRedirect()` คือด่านกัน open redirect — ห้ามเอา `route.query.redirect`
    //       ไป `push()` ตรง ๆ (เหตุผลเต็มอยู่ใน `router/redirect.ts`)
    //    ⚠️ คำนวณ **ก่อน** แยกเส้นทาง เพราะ **ทั้งสองเส้นทางต้องใช้ค่านี้**
    //       (เดิมคำนวณหลัง `mustChangePassword` ⇒ เส้นนั้นทิ้งปลายทางไปเปล่า ๆ — §30 ข้อ 3)
    const target = safeRedirect(route.query[REDIRECT_QUERY]);

    if (authStore.mustChangePassword) {
      // บัญชี seed ต้องเปลี่ยนรหัสผ่านก่อนใช้ระบบอะไรทั้งนั้น ⇒ พาไปหน้าที่ตั้งใจทันทีไม่ได้
      // (โดน guard `mustChangePassword` เด้งกลับมาอยู่ดี)
      // ⚠️ **แต่ต้องไม่ทิ้งปลายทาง** — บัญชีที่เพิ่งถูกส่งลิงก์ที่แชร์มาจะไปไม่ถึงเลย
      //    แม้หลังเปลี่ยนรหัสแล้ว ⇒ ส่ง `redirect` ต่อไปให้ `ChangePassword.vue` กระโดดต่อเอง
      //    (ปลายทางจะถูกใช้ **หลัง** เปลี่ยนรหัสสำเร็จเท่านั้น ⇒ ไม่ขัดเจตนาเดิมของ guard)
      Swal.fire({
        icon: 'info',
        title: 'ตั้งรหัสผ่านใหม่',
        text: 'เพื่อความปลอดภัย บัญชีนี้ต้องเปลี่ยนรหัสผ่านก่อนใช้งาน',
        timer: 2000,
        showConfirmButton: false,
      });
      router.push({
        name: 'profile-password',
        query: target ? { [REDIRECT_QUERY]: target } : {},
      });
      return;
    }

    Swal.fire({ icon: 'success', title: 'เข้าสู่ระบบสำเร็จ!', text: 'ยินดีต้อนรับสู่ PIRIvoice', timer: 1200, showConfirmButton: false });

    // ⚠️ ใช้ `replace` ไม่ใช่ `push` — ไม่งั้นกด "ย้อนกลับ" จะเจอหน้า login อีกครั้ง
    //    ทั้งที่เพิ่งล็อกอินสำเร็จ (วนกลับมาที่เดิมที่ผู้ใช้เพิ่งผ่านไปแล้ว)
    router.replace(target ?? { name: homeRouteName() });
  } catch (e) {
    const msg =
      typeof e === 'string'
        ? e
        : e instanceof Error
          ? e.message
          : 'รหัสนักเรียนหรือรหัสผ่านไม่ถูกต้อง';
    Swal.fire({ icon: 'error', title: 'เข้าสู่ระบบไม่สำเร็จ', text: msg });
  } finally {
    isLoading.value = false;
  }
}
</script>

<template>
  <div class="relative flex min-h-screen flex-col overflow-x-clip bg-[#FAFAF9] font-sans text-stone-900 selection:bg-brand/15 selection:text-brand">
    <!-- เส้นกริดจุด "กระดาษ" (เดียวกับ Landing hero) -->
    <div class="pointer-events-none absolute inset-0 bg-[radial-gradient(#e7e5e4_1px,transparent_1px)] [background-size:16px_16px] opacity-50"></div>

    <!-- ⚡ Navbar: Minimalist -->
    <header class="relative z-10 mx-auto flex w-full max-w-7xl items-center justify-between px-6 py-6 lg:px-8 animate-fade-in">
      <div class="flex items-center gap-4">
        <div class="flex items-center gap-3">
          <img src="/logos/school-logo.png" alt="ตราโรงเรียนพิริยาลัยจังหวัดแพร่" class="h-10 w-auto object-contain" />
          <span class="h-6 w-px bg-stone-300"></span>
          <img src="/logos/council-logo.png" alt="ตราสภานักเรียน" class="h-10 w-auto object-contain" />
        </div>
        <router-link to="/" class="flex flex-col items-start leading-none">
          <span class="text-lg font-bold tracking-tight text-stone-900">PIRI<span class="text-brand">voice</span></span>
          <span class="mt-1 hidden text-[10px] font-semibold uppercase tracking-[0.18em] text-ink-3 sm:block">Student Council</span>
        </router-link>
      </div>
      <div class="hidden md:block">
        <span class="rounded-full border border-stone-200 bg-white px-4 py-1.5 text-xs font-semibold text-stone-500">🏫 เสียงจากชาวพิริยาลัย</span>
      </div>
    </header>

    <!-- 🔐 ส่วนกลาง: เฉพาะการเข้าสู่ระบบ -->
    <main class="relative z-10 flex flex-1 items-center justify-center px-6 py-10">
      <div class="w-full max-w-[420px] animate-slide-up-fade">
        <div class="rounded-3xl border border-stone-200 bg-white p-8 sm:p-10">
          <div class="mb-8 text-center">
            <p class="mb-3 text-[11px] font-bold uppercase tracking-widest text-brand">Student Council · PIRIvoice</p>
            <h2 class="text-3xl font-bold text-stone-900">เข้าสู่ระบบ</h2>
            <p class="mt-2 text-sm text-stone-500">ลงชื่อเข้าใช้ด้วยรหัสนักเรียน / บุคลากร</p>
          </div>

          <form @submit.prevent="handleLogin" class="space-y-5">
            <!-- กลุ่มรหัสนักเรียน -->
            <div class="group">
              <label class="mb-1.5 block text-sm font-semibold text-stone-700 transition-colors group-focus-within:text-brand">รหัสนักเรียน</label>
              <div class="relative">
                <i class="bi bi-person absolute left-4 top-1/2 -translate-y-1/2 text-lg text-ink-3 transition-colors group-focus-within:text-brand"></i>
                <input
                  v-model="username"
                  type="text"
                  autocomplete="username"
                  class="w-full rounded-xl border border-stone-200 bg-white py-3.5 pl-11 pr-4 text-sm outline-none transition-colors focus:border-brand focus:ring-[3px] focus:ring-brand/20 sm:text-base"
                  placeholder="เช่น 41001"
                  :disabled="isLoading"
                />
              </div>
            </div>

            <!-- กลุ่มรหัสผ่าน -->
            <div class="group">
              <label class="mb-1.5 block text-sm font-semibold text-stone-700 transition-colors group-focus-within:text-brand">รหัสผ่าน</label>
              <div class="relative">
                <i class="bi bi-lock absolute left-4 top-1/2 -translate-y-1/2 text-lg text-ink-3 transition-colors group-focus-within:text-brand"></i>
                <input
                  v-model="password"
                  :type="showPassword ? 'text' : 'password'"
                  autocomplete="current-password"
                  class="w-full rounded-xl border border-stone-200 bg-white py-3.5 pl-11 pr-12 text-sm outline-none transition-colors focus:border-brand focus:ring-[3px] focus:ring-brand/20 sm:text-base"
                  placeholder="••••••••"
                  :disabled="isLoading"
                />
                <button
                  type="button"
                  @click="showPassword = !showPassword"
                  class="absolute right-2 top-1/2 flex h-11 w-11 -translate-y-1/2 items-center justify-center rounded-lg text-ink-3 transition-colors hover:bg-stone-100 hover:text-stone-600"
                  :aria-label="showPassword ? 'ซ่อนรหัสผ่าน' : 'แสดงรหัสผ่าน'"
                >
                  <i :class="showPassword ? 'bi bi-eye-slash' : 'bi bi-eye'"></i>
                </button>
              </div>
            </div>

            <!-- ปุ่ม Submit (flat cardinal) -->
            <button
              type="submit"
              :disabled="isLoading"
              class="mt-4 flex w-full items-center justify-center rounded-xl bg-brand py-3.5 text-base font-bold text-white transition-colors hover:bg-brand-strong focus:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-70"
            >
              <i v-if="!isLoading" class="bi bi-arrow-right-circle mr-2 text-lg"></i>
              <i v-else class="bi bi-arrow-repeat mr-2 animate-spin text-lg"></i>
              {{ isLoading ? 'กำลังตรวจสอบ...' : 'เข้าสู่ระบบเลย' }}
            </button>
          </form>

          <!-- Note box: รหัสผ่านเริ่มต้น -->
          <div class="mt-6 border-l-2 border-l-brand border border-stone-200 bg-stone-50 p-4">
            <div class="flex items-start gap-3">
              <i class="bi bi-info-circle-fill mt-0.5 text-brand"></i>
              <p class="text-[12px] leading-relaxed text-stone-600">
                <strong class="mb-0.5 block font-bold text-stone-800">รหัสผ่านเริ่มต้น</strong>
                สำหรับนักเรียนและบุคลากร รหัสผ่านตั้งต้นคือ
                <code class="rounded border border-stone-200 bg-white px-1.5 py-0.5 font-mono text-brand">รหัสนักเรียน/บุคลากร</code>
                ของท่าน
              </p>
            </div>
          </div>
        </div>
      </div>
    </main>

    <!-- Footer -->
    <footer class="relative z-10 border-t border-stone-200 bg-white py-8 text-center">
      <div class="flex flex-col items-center justify-center gap-2">
        <p class="text-sm font-medium text-stone-500">
          คณะกรรมการสภานักเรียน · <span class="font-bold text-stone-700">โรงเรียนพิริยาลัยจังหวัดแพร่</span>
        </p>
        <div class="flex flex-col items-center gap-2 text-xs font-medium text-ink-3 sm:flex-row">
          <span>© 2026 PIRIvoice. สงวนลิขสิทธิ์</span>
          <span class="hidden text-stone-300 sm:inline-block">•</span>
          <div class="flex items-center gap-1.5">
            <span>พัฒนาโดย</span>
            <a
              href="https://www.singto1597.xyz/"
              target="_blank"
              rel="noopener noreferrer"
              class="inline-flex items-center rounded-md border border-stone-200 bg-stone-100 px-2.5 min-h-11 py-1 font-semibold text-stone-600 transition-colors hover:border-brand/40 hover:bg-brand/5 hover:text-brand"
            >
              นายพัฒนพล สุธรรม
            </a>
          </div>
        </div>
      </div>
    </footer>
  </div>
</template>

<style scoped>
/* Animations — เรียบ สั้น ไม่มีลูกบอลเรืองแสง */
@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

@keyframes slideUpFade {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.animate-fade-in {
  animation: fadeIn 0.8s ease-out forwards;
}

.animate-slide-up-fade {
  opacity: 0;
  animation: slideUpFade 0.8s cubic-bezier(0.16, 1, 0.3, 1) forwards;
}

/* ลบลูกศรใน input type number */
input[type="number"]::-webkit-inner-spin-button,
input[type="number"]::-webkit-outer-spin-button {
  -webkit-appearance: none;
  margin: 0;
}

/* 🔤 Keyboard focus ตามธีม */
input:focus-visible,
button:focus-visible,
a:focus-visible {
  outline: 2px solid rgba(185, 28, 28, 0.55);
  outline-offset: 2px;
}

/* ♿ เคารพผู้ที่ปิดแอนิเมชัน */
@media (prefers-reduced-motion: reduce) {
  .animate-slide-up-fade,
  .animate-fade-in {
    animation: none !important;
  }
  .animate-slide-up-fade,
  .animate-fade-in {
    opacity: 1 !important;
  }
}
</style>
