<script setup lang="ts">
import { ref, onMounted, computed } from 'vue';
import { useRouter } from 'vue-router';
import Swal from 'sweetalert2';
import { getMyProfile, updateMyProfile } from '@/services/profile';
import { useAuthStore } from '@/stores/auth';
import AppCard from '@/components/ui/AppCard.vue';
import AppButton from '@/components/ui/AppButton.vue';
import AppEmptyState from '@/components/ui/AppEmptyState.vue';

const router = useRouter();
const authStore = useAuthStore();

const isLoading = ref(true);
const isSaving = ref(false);
const loadError = ref(false);

const editPrefix = ref('');
const editFirstName = ref('');
const editLastName = ref('');
const editNickname = ref('');
const editPhone = ref('');
const editEmail = ref('');

async function loadProfile() {
  isLoading.value = true;
  loadError.value = false;
  try {
    const p = await getMyProfile();
    editPrefix.value = p.prefix || '';
    editFirstName.value = p.first_name || '';
    editLastName.value = p.last_name || '';
    editNickname.value = p.nickname || '';
    editPhone.value = p.phone_number || '';
    editEmail.value = p.email || '';
  } catch (e: unknown) {
    loadError.value = true;
    Swal.fire({ icon: 'error', title: 'โหลดโปรไฟล์ไม่สำเร็จ', text: e instanceof Error ? e.message : 'เกิดข้อผิดพลาด' });
  } finally {
    isLoading.value = false;
  }
}
onMounted(loadProfile);

const canSave = computed(() => editFirstName.value.trim() && editLastName.value.trim());

async function saveProfile() {
  if (!editFirstName.value.trim() || !editLastName.value.trim()) {
    Swal.fire({ icon: 'warning', title: 'กรอกชื่อให้ครบ', text: 'ชื่อ และ นามสกุล จำเป็น' });
    return;
  }
  isSaving.value = true;
  try {
    await updateMyProfile({
      prefix: editPrefix.value.trim() || null,
      first_name: editFirstName.value.trim(),
      last_name: editLastName.value.trim(),
      nickname: editNickname.value.trim() || null,
      phone_number: editPhone.value.trim() || null,
      email: editEmail.value.trim() || null,
    });
    // อัปเดต display name ใน auth store (ชื่อที่ขึ้น sidebar/header)
    await authStore.loadMe();
    Swal.fire({ icon: 'success', title: 'บันทึกโปรไฟล์แล้ว', timer: 1200, showConfirmButton: false });
    router.push({ name: 'profile' });
  } catch (e: unknown) {
    Swal.fire({ icon: 'error', title: 'บันทึกไม่สำเร็จ', text: e instanceof Error ? e.message : 'เกิดข้อผิดพลาด' });
  } finally {
    isSaving.value = false;
  }
}

const goBack = () => router.push({ name: 'profile' });

const inputCls = 'w-full px-3.5 py-2.5 border border-stone-300 rounded-xl text-sm mt-1 bg-white transition focus:ring-2 focus:ring-brand/25 focus:border-brand';
</script>

<template>
  <div class="max-w-2xl mx-auto">
    <!-- Loading skeleton -->
    <div v-if="isLoading" class="space-y-4" aria-busy="true">
      <div class="h-6 w-64 animate-pulse rounded bg-stone-100"></div>
      <div class="space-y-5 rounded-2xl border border-stone-200 bg-white p-6 sm:p-8">
        <div v-for="i in 5" :key="i" class="space-y-2">
          <div class="h-3 w-24 animate-pulse rounded bg-stone-100"></div>
          <div class="h-10 animate-pulse rounded-lg bg-stone-100"></div>
        </div>
      </div>
    </div>

    <!-- Error + retry — 「ไม่มีการ์ดเส้นประ」 (AppEmptyState ไม่มี border-dashed โดยเจตนา) -->
    <AppCard v-else-if="loadError" :padded="false" class="py-4">
      <AppEmptyState
        icon="bi-pencil-square"
        title="ไม่สามารถโหลดข้อมูลโปรไฟล์ได้ในขณะนี้"
        description="ตรวจสอบการเชื่อมต่อแล้วลองอีกครั้ง"
      >
        <AppButton variant="secondary" @click="loadProfile">
          <template #icon><i class="bi bi-arrow-clockwise" aria-hidden="true" /></template>
          ลองใหม่
        </AppButton>
      </AppEmptyState>
    </AppCard>

    <form v-else @submit.prevent="saveProfile" class="space-y-4">
      <!-- 🔴 ไม่มี <h1>/eyebrow/ปุ่มย้อนที่นี่ — `AppHeader` วาดชื่อหน้า (routeTitles) เป็น <h1>
           และปุ่ม ← (จาก `meta.headerBack`) ให้แล้ว (R0.3) ⇒ ของเดิมคือของซ้ำทั้งสามอย่าง -->

      <div class="space-y-5 rounded-2xl border border-stone-200 bg-white p-6 sm:p-8">
        <!-- ชื่อ: คำนำหน้า / ชื่อ / นามสกุล (mobile = 1 คอลัมน์) -->
        <div class="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div>
            <label class="block text-xs font-semibold text-stone-700">คำนำหน้า</label>
            <input v-model="editPrefix" :class="inputCls" placeholder="นาย / นางสาว" />
          </div>
          <div>
            <label class="block text-xs font-semibold text-stone-700">ชื่อ <span class="text-brand">*</span></label>
            <input v-model="editFirstName" :class="inputCls" required />
          </div>
          <div>
            <label class="block text-xs font-semibold text-stone-700">นามสกุล <span class="text-brand">*</span></label>
            <input v-model="editLastName" :class="inputCls" required />
          </div>
        </div>

        <div>
          <label class="block text-xs font-semibold text-stone-700">ชื่อเล่น</label>
          <input v-model="editNickname" :class="inputCls" placeholder="ชื่อที่เพื่อนเรียก" />
        </div>

        <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label class="block text-xs font-semibold text-stone-700">เบอร์โทร</label>
            <input v-model="editPhone" :class="inputCls" type="tel" placeholder="08x-xxx-xxxx" />
          </div>
          <div>
            <label class="block text-xs font-semibold text-stone-700">อีเมล</label>
            <input v-model="editEmail" :class="inputCls" type="email" placeholder="example@mail.com" />
          </div>
        </div>
      </div>

      <!-- ปุ่ม -->
      <div class="flex gap-2 pt-1">
        <button
          type="submit"
          :disabled="isSaving || !canSave"
          class="flex-1 py-3 bg-brand text-white rounded-xl hover:bg-brand-strong disabled:opacity-50 font-semibold transition-colors"
        >
          <i class="bi bi-check-lg mr-1"></i> {{ isSaving ? 'กำลังบันทึก...' : 'บันทึก' }}
        </button>
        <button
          type="button"
          @click="goBack"
          class="px-5 py-3 bg-white border border-stone-200 text-stone-600 rounded-xl hover:bg-stone-50 text-sm font-medium transition"
        >
          ยกเลิก
        </button>
      </div>
    </form>
  </div>
</template>
