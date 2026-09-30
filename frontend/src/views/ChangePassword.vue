<script setup lang="ts">
import { ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import Swal from 'sweetalert2';
import { changePassword } from '@/services/profile';
import { useAuthStore } from '@/stores/auth';
import { REDIRECT_QUERY, safeRedirect } from '@/router/redirect';

const router = useRouter();
const route = useRoute();
const authStore = useAuthStore();

const oldPass = ref('');
const newPass = ref('');
const confirmPass = ref('');
const isSaving = ref(false);

// โดนบังคับเปลี่ยนรหัส (บัญชีที่ระบบสร้างให้ ตอนเปิดระบบครั้งแรก)
const isForced = authStore.mustChangePassword;

// หน้าแรกตามบทบาท (เหมือน Login)
function homeRouteName(): string {
  if (authStore.hasPermission('VIEW_DASHBOARD')) return 'dashboard';
  if (authStore.hasPermission('RECEIVE_ISSUES')) return 'received-issues';
  return 'new-issue';
}

async function submit() {
  if (!oldPass.value || !newPass.value || !confirmPass.value) {
    Swal.fire({ icon: 'warning', title: 'กรอกให้ครบ', text: 'กรอกรหัสผ่านเดิม, ใหม่, ยืนยัน' });
    return;
  }
  if (newPass.value.length < 4) {
    Swal.fire({ icon: 'warning', title: 'รหัสสั้นไป', text: 'รหัสผ่านใหม่อย่างน้อย 4 ตัว' });
    return;
  }
  if (newPass.value !== confirmPass.value) {
    Swal.fire({ icon: 'warning', title: 'รหัสผ่านใหม่ไม่ตรงกัน', text: 'ยืนยันรหัสผ่านให้ตรงกับรหัสใหม่' });
    return;
  }

  isSaving.value = true;
  try {
    await changePassword(oldPass.value, newPass.value);
    oldPass.value = newPass.value = confirmPass.value = '';
    // อัปเดต flag (must_change_password → false) — เคลียร์ local ก่อน กัน redirect วน
    authStore.markPasswordChanged();
    try { await authStore.loadMe(); } catch { /* ignore */ }
    Swal.fire({
      icon: 'success',
      title: 'เปลี่ยนรหัสผ่านสำเร็จ!',
      text: 'ครั้งหน้าใช้รหัสใหม่ในการเข้าสู่ระบบ',
      timer: 1500,
      showConfirmButton: false,
    }).then(() => {
      // 🔗 ปลายทางที่ตั้งใจไว้ตั้งแต่ก่อนล็อกอิน (§30 ข้อ 3) — ถูกส่งต่อมาทาง `?redirect=`
      //    ทั้งจากหน้า Login และจาก guard (`mustChangePassword`)
      //    ⚠️ **เปลี่ยนรหัสเสร็จแล้วเท่านั้นจึงใช้ค่านี้** ⇒ ไม่ขัดเจตนาเดิมที่ห้ามไปที่อื่นก่อน
      //       เปลี่ยนรหัส (ตอนนั้น guard จะเด้งกลับมาอยู่ดี)
      //    ⚠️ `safeRedirect()` กรองซ้ำเสมอ — ค่ามาจาก URL ที่ใครก็เขียนได้ (ด่านเดิม ห้ามผ่อน)
      const target = safeRedirect(route.query[REDIRECT_QUERY]);
      if (target) router.replace(target);
      else router.push({ name: homeRouteName() });
    });
  } catch (e: unknown) {
    Swal.fire({ icon: 'error', title: 'เปลี่ยนรหัสไม่สำเร็จ', text: e instanceof Error ? e.message : 'เกิดข้อผิดพลาด' });
  } finally {
    isSaving.value = false;
  }
}

const goBack = () => router.push({ name: 'profile' });

const inputCls = 'w-full px-3.5 py-2.5 border border-stone-300 rounded-xl text-sm mt-1 bg-white transition focus:ring-2 focus:ring-brand/25 focus:border-brand';
</script>

<template>
  <div class="max-w-2xl mx-auto">
    <form @submit.prevent="submit" class="space-y-4">
      <!-- Header -->
      <div class="flex items-start gap-3">
        <button type="button" @click="goBack" aria-label="กลับไปหน้าโปรไฟล์" class="w-9 h-9 rounded-xl bg-white border border-stone-200 text-stone-500 hover:text-brand hover:border-brand/30 hover:bg-brand/5 flex items-center justify-center transition shrink-0 mt-1">
          <i class="bi bi-arrow-left text-lg"></i>
        </button>
        <div>
          <p class="text-[11px] font-bold text-stone-400 mb-1">การจัดการบัญชี</p>
          <h1 class="text-2xl sm:text-3xl font-bold text-stone-900 leading-tight"><i class="bi bi-shield-lock mr-1 text-brand"></i> เปลี่ยนรหัสผ่าน</h1>
          <p class="text-sm text-stone-500 mt-1">ตั้งรหัสผ่านใหม่เพื่อความปลอดภัย</p>
        </div>
      </div>

      <!-- บังคับเปลี่ยนครั้งแรก -->
      <div v-if="isForced" class="flex gap-3 rounded-2xl border border-brand/20 bg-brand/10 p-4 text-sm text-brand">
        <i class="bi bi-shield-exclamation text-xl shrink-0"></i>
        <div>
          <p class="font-bold">บัญชีนี้เป็นบัญชีเริ่มต้นของระบบ</p>
          <p class="text-brand/70 mt-0.5">กรุณาเปลี่ยนรหัสผ่านก่อนใช้งาน เพื่อป้องกันผู้อื่นเข้าถึง</p>
        </div>
      </div>

      <div class="space-y-5 rounded-2xl border border-stone-200 bg-white p-6 sm:p-8">
        <div>
          <label class="block text-xs font-semibold text-stone-700">รหัสผ่านเดิม</label>
          <input v-model="oldPass" type="password" :class="inputCls" placeholder="••••••" autocomplete="current-password" />
        </div>
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label class="block text-xs font-semibold text-stone-700">รหัสผ่านใหม่</label>
            <input v-model="newPass" type="password" :class="inputCls" placeholder="อย่างน้อย 4 ตัว" autocomplete="new-password" />
          </div>
          <div>
            <label class="block text-xs font-semibold text-stone-700">ยืนยันรหัสผ่านใหม่</label>
            <input v-model="confirmPass" type="password" :class="inputCls" placeholder="พิมพ์ซ้ำอีกครั้ง" autocomplete="new-password" />
          </div>
        </div>
      </div>

      <button
        type="submit"
        :disabled="isSaving"
        class="w-full py-3 bg-brand text-white rounded-xl hover:bg-brand-strong disabled:opacity-50 font-semibold transition-colors"
      >
        <i class="bi bi-key mr-1"></i> {{ isSaving ? 'กำลังเปลี่ยน...' : 'เปลี่ยนรหัสผ่าน' }}
      </button>
    </form>
  </div>
</template>
