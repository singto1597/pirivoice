<!-- eslint-disable vue/multi-word-component-names -- ชื่อตาม route/spec -->
<script setup lang="ts">
import { ref, onMounted, computed } from 'vue';
import { useRouter } from 'vue-router';
import Swal from 'sweetalert2';
import { getMyProfile, type MyProfile } from '@/services/profile';
import {
  getNotificationPreferences,
  updateNotificationPreferences,
} from '@/services/notification';
import {
  PREFERENCE_GROUPS,
  GROUP_DESCRIPTIONS,
  type NotificationGroup,
} from '@/types/notification';
import { getMyStats } from '@/services/me';
import type { PersonalStats } from '@/types/me';
import PersonalStatsCard from '@/components/PersonalStatsCard.vue';
import { useAuthStore } from '@/stores/auth';
import {
  canPromptInstall,
  installDiagnostics,
  installHint,
  installNow,
  isIosSafari,
  isStandalone,
} from '@/pwa';

const router = useRouter();
const authStore = useAuthStore();

// ===== 📱 ติดตั้งแอป =====
// ⚠️ การ์ดนี้คือ **ทางกลับมา** ของคนที่เคยกด ✕ ปิดแบนเนอร์ติดตั้งไว้ — แบนเนอร์จำการปิด
//    แล้วไม่ขึ้นอีก ส่วนการ์ดนี้ไม่ผูกกับค่านั้น เพราะการที่ผู้ใช้เปิดมาหาเองคือการเปลี่ยนใจ
const installing = ref(false);

/**
 * แถวข้อมูลวินิจฉัย — แสดงเฉพาะในกิ่ง "ติดตั้งอัตโนมัติไม่ได้"
 *
 * ใช้คำว่า "ใช่/ไม่" ไม่ใช่ true/false เพราะคนที่อ่านเป็นผู้ใช้ทั่วไป ไม่ใช่ช่าง
 * ⚠️ `installDiagnostics` เป็น `computed` ⇒ ค่าจะอัปเดตเองเมื่อสถานะเปลี่ยน
 *    (เช่นผู้ใช้กดปิดแบนเนอร์ระหว่างเปิดหน้านี้อยู่)
 */
const diagRows = computed(() => {
  const d = installDiagnostics.value;
  return [
    { label: 'เปิดในโหมดแอพแล้ว', on: d.standalone },
    { label: 'เบราว์เซอร์พร้อมติดตั้ง', on: d.promptReady },
    { label: 'ตัวช่วยแอพทำงาน (SW)', on: d.swRegistered },
    { label: 'เคยกดปิดแบนเนอร์', on: d.dismissed },
    { label: 'เครื่องนี้เคยติดตั้งมาก่อน', on: d.installedBefore },
  ];
});

async function onInstall() {
  if (installing.value) return;
  installing.value = true;
  try {
    const outcome = await installNow();
    if (outcome === 'accepted') {
      await Swal.fire({
        icon: 'success',
        title: 'ติดตั้งแล้ว',
        text: 'เปิด PIRIvoice ได้จากไอคอนบนหน้าจอเลย',
        confirmButtonColor: '#b91c1c',
      });
    } else if (outcome === 'unavailable') {
      await Swal.fire({
        icon: 'info',
        title: 'เครื่องนี้ติดตั้งอัตโนมัติไม่ได้',
        text: 'เปิดด้วย Chrome แล้วเลือก "ติดตั้งแอป" จากเมนู ⋮ มุมขวาบน',
        confirmButtonColor: '#b91c1c',
      });
    }
  } finally {
    installing.value = false;
  }
}

const profile = ref<MyProfile | null>(null);
const isLoading = ref(true);
const hasError = ref(false);
const menuOpen = ref(false);

const ROLE_LABELS: Record<string, string> = {
  student: 'นักเรียน',
  class_president: 'หัวหน้าห้อง',
  vice_academic: 'รองวิชาการ',
  vice_discipline: 'รองวินัย',
  vice_activity: 'รองกิจกรรม',
  vice_reception: 'รองปฏิคม',
  level_president: 'ประธานระดับ',
  council_member: 'สภานักเรียน',
  council_president: 'ประธานสภา',
  teacher: 'ครู',
  teacher_council: 'ครูสภา',
  admin: 'แอดมิน',
};

const avatarChar = computed(() => {
  // ตัวแรกของชื่อจริง (first_name) — ไม่เอาคำนำหน้า (prefix)/ชื่อเล่น (nickname)
  const name = profile.value?.first_name || profile.value?.username || '';
  return name ? name.charAt(0).toUpperCase() : 'ส';
});

const fullName = computed(() => {
  const p = profile.value;
  if (!p) return '';
  return [p.prefix, p.first_name, p.last_name].filter(Boolean).join(' ').trim();
});

const roleLabel = computed(() => {
  const r = profile.value?.class_role || '';
  return ROLE_LABELS[r] || r || 'สมาชิก';
});

async function load() {
  isLoading.value = true;
  hasError.value = false;
  try {
    profile.value = await getMyProfile();
  } catch (e: unknown) {
    hasError.value = true;
    Swal.fire({ icon: 'error', title: 'โหลดโปรไฟล์ไม่สำเร็จ', text: e instanceof Error ? e.message : 'เกิดข้อผิดพลาด' });
  } finally {
    isLoading.value = false;
  }
}
onMounted(load);

// ===== ⚙️ ตั้งค่าการแจ้งเตือนรายกลุ่ม (A2) =====
// สร้างคีย์จาก PREFERENCE_GROUPS → ไม่ต้องพิมพ์ชื่อกลุ่มซ้ำในไฟล์นี้
// ค่าตั้งต้น = เปิดหมด (ตรงกับ backend: "ไม่มีแถว = เปิด")
const prefs = ref<Record<string, boolean>>(
  Object.fromEntries(PREFERENCE_GROUPS.map((g) => [g.value, true])),
);
const prefsLoading = ref(true);
const prefsError = ref(false);
const savingGroup = ref<NotificationGroup | null>(null);

// คีย์ที่ไม่มี = เปิด (ตรงกับ backend) — และกัน noUncheckedIndexedAccess ที่ทำให้เป็น boolean|undefined
const isOn = (group: NotificationGroup): boolean => prefs.value[group] ?? true;

async function loadPrefs() {
  prefsLoading.value = true;
  prefsError.value = false;
  try {
    const res = await getNotificationPreferences();
    const next = { ...prefs.value };
    for (const p of res.preferences) next[p.group_type] = p.enabled;
    prefs.value = next;
  } catch {
    // ไม่เด้ง Swal ตอนเปิดหน้า (กวนเกินไป) — โชว์ในตัวการ์ดพร้อมปุ่มลองใหม่แทน
    prefsError.value = true;
  } finally {
    prefsLoading.value = false;
  }
}
onMounted(loadPrefs);

async function toggleGroup(group: NotificationGroup) {
  const next = !isOn(group);

  // ปิดกลุ่ม "เรื่องของฉัน" = เงียบเมื่อเรื่องที่ตัวเองแจ้งมีความเคลื่อนไหว → ถามก่อน
  if (!next && group === 'issue_mine') {
    const res = await Swal.fire({
      icon: 'warning',
      title: 'ปิดการแจ้งเตือนเรื่องของฉัน?',
      text: 'คุณจะไม่รู้เมื่อเรื่องที่คุณแจ้งไว้ถูกตอบกลับ หรือมีการเปลี่ยนสถานะ',
      showCancelButton: true,
      confirmButtonText: 'ปิดการแจ้งเตือน',
      cancelButtonText: 'ยกเลิก',
      confirmButtonColor: '#B91C1C',
    });
    if (!res.isConfirmed) return;
  }

  const prev = isOn(group);
  prefs.value[group] = next; // optimistic — กดแล้วต้องเห็นผลทันที
  savingGroup.value = group;
  try {
    await updateNotificationPreferences([{ group_type: group, enabled: next }]);
  } catch (e: unknown) {
    prefs.value[group] = prev; // ยิงไม่ผ่าน → คืนค่าที่ถูกต้องให้ผู้ใช้เห็น
    Swal.fire({
      icon: 'error',
      title: 'บันทึกไม่สำเร็จ',
      text: e instanceof Error ? e.message : 'เกิดข้อผิดพลาด กรุณาลองใหม่',
    });
  } finally {
    savingGroup.value = null;
  }
}

const goEdit = () => { menuOpen.value = false; router.push({ name: 'profile-edit' }); };
const goPassword = () => { menuOpen.value = false; router.push({ name: 'profile-password' }); };

function logout() {
  menuOpen.value = false;
  Swal.fire({
    icon: 'question',
    title: 'ออกจากระบบ?',
    showCancelButton: true,
    confirmButtonText: 'ออกจากระบบ',
    cancelButtonText: 'ยกเลิก',
  }).then((result) => {
    if (result.isConfirmed) {
      authStore.logout();
      router.push({ name: 'login' });
    }
  });
}

// แถวข้อมูลส่วนตัว (icon + label + value) — กันเบียด/ตัดคำบนจอเล็ก
const infoRows = computed(() => {
  const p = profile.value;
  if (!p) return [];
  const rows: { icon: string; label: string; value: string }[] = [
    { icon: 'bi-person-badge', label: 'รหัสนักเรียน', value: p.student_id },
    { icon: 'bi-hash', label: 'เลขที่', value: p.student_no ? String(p.student_no) : '-' },
    { icon: 'bi-emoji-smile', label: 'ชื่อเล่น', value: p.nickname || '-' },
    { icon: 'bi-telephone', label: 'เบอร์โทร', value: p.phone_number || '-' },
    { icon: 'bi-envelope', label: 'อีเมล', value: p.email || '-' },
    { icon: 'bi-door-closed', label: 'ห้องเรียน', value: p.room_code ? `${p.room_code}${p.level ? ` (${p.level})` : ''}` : '-' },
  ];
  // ชื่อผู้ใช้ (login) — แสดงเฉพาะเมื่อต่างจากรหัสนักเรียน (เช่น admin/ครู ที่ใช้ username ยาว)
  if (p.username && p.username !== p.student_id) {
    rows.push({ icon: 'bi-person-vcard', label: 'ชื่อผู้ใช้', value: p.username });
  }
  return rows;
});

// ===== 📊 สถิติของฉัน (C3) =====
// โหลดแยกจากการ์ดอื่นโดยเจตนา — ถ้า /api/me/stats ล่ม ผู้ใช้ยังเห็นโปรไฟล์และการตั้งค่าได้
const stats = ref<PersonalStats | null>(null);
const statsLoading = ref(true);
const statsError = ref(false);

async function loadStats() {
  statsLoading.value = true;
  statsError.value = false;
  try {
    stats.value = await getMyStats();
  } catch {
    // ไม่เด้ง Swal — การ์ดมีปุ่ม "ลองใหม่" ของตัวเองอยู่แล้ว
    statsError.value = true;
  } finally {
    statsLoading.value = false;
  }
}
onMounted(loadStats);
</script>

<template>
  <div class="max-w-3xl mx-auto">
    <!-- Loading skeleton -->
    <div v-if="isLoading" class="space-y-4" aria-busy="true">
      <div class="overflow-hidden rounded-2xl border border-stone-200 bg-white">
        <div class="h-28 sm:h-36 animate-pulse bg-stone-100"></div>
        <div class="px-5 py-6 sm:px-8">
          <div class="flex items-center gap-4">
            <div class="h-16 w-16 rounded-2xl animate-pulse bg-stone-100 sm:h-20 sm:w-20"></div>
            <div class="flex-1 space-y-2.5">
              <div class="h-5 w-52 animate-pulse rounded bg-stone-100"></div>
              <div class="h-4 w-32 animate-pulse rounded bg-stone-100"></div>
            </div>
          </div>
        </div>
      </div>
      <div class="rounded-2xl border border-stone-200 bg-white p-6 sm:p-8">
        <div class="mb-6 h-5 w-28 animate-pulse rounded bg-stone-100"></div>
        <div class="grid gap-x-8 gap-y-5 sm:grid-cols-2">
          <div v-for="i in 6" :key="i" class="flex items-center gap-3">
            <div class="h-9 w-9 animate-pulse rounded-xl bg-stone-100"></div>
            <div class="flex-1 space-y-2">
              <div class="h-3 w-20 animate-pulse rounded bg-stone-100"></div>
              <div class="h-4 w-32 animate-pulse rounded bg-stone-100"></div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Error + retry -->
    <div v-else-if="hasError" class="rounded-2xl border-2 border-dashed border-stone-200 bg-white py-16 text-center">
      <i class="bi bi-person-exclamation mb-3 block text-3xl text-stone-400"></i>
      <p class="text-[15px] font-semibold text-stone-700">ไม่สามารถโหลดโปรไฟล์ได้ในขณะนี้</p>
      <p class="mt-1 text-sm text-stone-500">ตรวจสอบการเชื่อมต่อแล้วลองอีกครั้ง</p>
      <button
        type="button"
        @click="load"
        class="mt-5 inline-flex items-center gap-2 rounded-lg bg-[#B91C1C] px-5 py-2.5 text-[13px] font-bold text-white transition-colors hover:bg-[#991B1B]"
      >
        <i class="bi bi-arrow-clockwise"></i> ลองใหม่
      </button>
    </div>

    <div v-else-if="profile" class="space-y-4">
      <!-- ===== การ์ดหลัก: cover + ตัวตน (avatar ทับ cover เฉพาะตัว, ชื่ออยู่บนพื้นขาวเสมอ) ===== -->
      <div class="relative">
        <div class="overflow-hidden rounded-2xl border border-stone-200 bg-white">
          <!-- Cover banner (พื้นหินเรียบ + hairline) -->
          <div class="h-28 border-b border-stone-200 bg-stone-100 sm:h-36"></div>

          <!-- ตัวตน: relative z-10 → avatar/ชื่อวาดอยู่บนสุด เหนือ cover -->
          <div class="relative z-10 px-4 pb-5 sm:px-6 sm:pb-6">
            <div class="flex items-start gap-3 sm:gap-4">
              <!-- avatar: มี -mt เท่านั้น เพื่อให้ทับ cover มุมซ้าย (ไม่ดึงชื่อขึ้นด้วย) -->
              <div class="-mt-10 shrink-0 sm:-mt-14">
                <div class="flex h-16 w-16 items-center justify-center rounded-2xl bg-[#B91C1C] text-2xl font-bold text-white ring-2 ring-stone-200 sm:h-24 sm:w-24 sm:rounded-3xl sm:text-4xl">
                  {{ avatarChar }}
                </div>
              </div>
              <!-- ชื่อ + ตำแหน่ง: pt ชัดเจน → อยู่ใต้ cover บนพื้นขาว อ่านง่ายเสมอ -->
              <div class="min-w-0 flex-1 pt-3 sm:pt-5">
                <h1 class="text-2xl font-bold tracking-tight text-stone-900 break-words leading-snug sm:text-3xl">{{ fullName }}</h1>
                <div class="flex flex-wrap gap-1.5 mt-2.5">
                  <span class="px-2.5 py-1 bg-[#B91C1C]/10 text-[#B91C1C] text-xs font-semibold rounded-full">
                    <i class="bi bi-mortarboard mr-1"></i>{{ roleLabel }}
                  </span>
                  <span v-if="profile.staff_level" class="px-2.5 py-1 bg-stone-100 text-stone-600 text-xs font-semibold rounded-full">
                    <i class="bi bi-clipboard-check mr-1"></i>ระดับ {{ profile.staff_level }}
                  </span>
                  <span v-if="profile.room_code" class="px-2.5 py-1 bg-stone-100 text-stone-600 text-xs font-medium rounded-full">
                    <i class="bi bi-door-closed mr-1"></i>{{ profile.room_code }}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- เมนู ⋮ (อยู่ข้างนอก overflow-hidden → dropdown ไม่ถูกตัด) -->
        <div class="absolute right-3 top-3 z-50">
          <button
            @click="menuOpen = !menuOpen"
            aria-label="เมนูโปรไฟล์"
            class="flex h-9 w-9 items-center justify-center rounded-full bg-stone-200/90 text-stone-700 transition hover:bg-stone-300"
            :class="{ 'bg-stone-300': menuOpen }"
          >
            <i class="bi bi-three-dots-vertical text-lg"></i>
          </button>

          <transition name="fade-up">
            <div v-if="menuOpen" class="absolute right-0 top-11 z-50 w-56 rounded-2xl border border-stone-200 bg-white py-2 shadow-lg shadow-stone-900/5">
              <div class="mb-1 border-b border-stone-100 px-4 py-1.5">
                <p class="text-[10px] font-bold text-stone-400 uppercase tracking-widest">การจัดการบัญชี</p>
              </div>
              <button @click="goEdit" class="flex w-full items-center gap-3 px-4 py-2.5 text-left text-sm font-semibold text-stone-700 transition-colors hover:bg-stone-100 hover:text-[#B91C1C]">
                <i class="bi bi-pencil-square text-lg"></i> แก้ไขโปรไฟล์
              </button>
              <button @click="goPassword" class="flex w-full items-center gap-3 px-4 py-2.5 text-left text-sm font-semibold text-stone-700 transition-colors hover:bg-stone-100 hover:text-[#B91C1C]">
                <i class="bi bi-shield-lock text-lg"></i> เปลี่ยนรหัสผ่าน
              </button>
              <div class="my-1 h-px bg-stone-200"></div>
              <button @click="logout" class="flex w-full items-center gap-3 px-4 py-2.5 text-left text-sm font-bold text-[#B91C1C] transition-colors hover:bg-[#B91C1C]/5 hover:text-[#991B1B]">
                <i class="bi bi-box-arrow-right text-lg"></i> ออกจากระบบ
              </button>
            </div>
          </transition>
        </div>

        <!-- Overlay ปิดเมนู: z-40 → อยู่ใต้ dropdown (z-50) แต่เหนือ header มือถือ (z-30) → แตะที่ไหนก็ปิดได้ -->
        <div v-if="menuOpen" class="fixed inset-0 z-40" @click="menuOpen = false"></div>
      </div>

      <!-- ===== ข้อมูลส่วนตัว ===== -->
      <div class="rounded-2xl border border-stone-200 bg-white p-6 sm:p-8">
        <div class="mb-5 flex items-center gap-3">
          <span class="flex h-10 w-10 items-center justify-center rounded-xl bg-stone-100 text-stone-500">
            <i class="bi bi-person-lines-fill"></i>
          </span>
          <div>
            <h2 class="text-lg font-bold text-stone-900">ข้อมูลส่วนตัว</h2>
            <p class="text-xs text-stone-500 mt-0.5">ข้อมูลและช่องทางการติดต่อของคุณ</p>
          </div>
        </div>
        <div class="grid gap-x-6 gap-y-3 sm:grid-cols-2">
          <div
            v-for="row in infoRows"
            :key="row.label"
            class="flex items-center gap-3 py-1.5 min-w-0"
          >
            <span class="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-stone-100 text-stone-500">
              <i :class="['bi', row.icon]"></i>
            </span>
            <div class="min-w-0">
              <p class="text-[11px] text-stone-500 font-medium leading-tight">{{ row.label }}</p>
              <p class="text-sm text-stone-800 font-semibold break-words leading-snug">{{ row.value }}</p>
            </div>
          </div>
        </div>
      </div>

      <!-- ===== ⚙️ การแจ้งเตือน ===== -->
      <div class="rounded-2xl border border-stone-200 bg-white p-6 sm:p-8">
        <div class="mb-5 flex items-center gap-3">
          <span class="flex h-10 w-10 items-center justify-center rounded-xl bg-stone-100 text-stone-500">
            <i class="bi bi-bell"></i>
          </span>
          <div>
            <h2 class="text-lg font-bold text-stone-900">การแจ้งเตือน</h2>
            <p class="text-xs text-stone-500 mt-0.5">
              เลือกว่าจะรับเรื่องอะไร — ปิดแล้วเรื่องนั้นจะไม่ขึ้นทั้งในแอพและการแจ้งเตือน
            </p>
          </div>
        </div>

        <!-- โหลดไม่สำเร็จ: ไม่ปิดกั้นทั้งหน้า แค่การ์ดนี้ -->
        <div v-if="prefsError" class="rounded-xl border border-dashed border-stone-300 bg-stone-50 px-4 py-6 text-center">
          <i class="bi bi-cloud-slash mb-2 block text-2xl text-stone-400"></i>
          <p class="text-sm font-semibold text-stone-700">โหลดการตั้งค่าไม่ได้</p>
          <button
            type="button"
            @click="loadPrefs"
            class="mt-3 inline-flex items-center gap-2 rounded-lg border border-stone-300 bg-white px-4 py-2 text-[13px] font-bold text-stone-700 transition-colors hover:bg-stone-100"
          >
            <i class="bi bi-arrow-clockwise"></i> ลองใหม่
          </button>
        </div>

        <div v-else-if="prefsLoading" class="space-y-4" aria-busy="true">
          <div v-for="i in 4" :key="i" class="flex items-center gap-3">
            <div class="h-9 w-9 shrink-0 animate-pulse rounded-xl bg-stone-100"></div>
            <div class="flex-1 space-y-2">
              <div class="h-4 w-28 animate-pulse rounded bg-stone-100"></div>
              <div class="h-3 w-44 animate-pulse rounded bg-stone-100"></div>
            </div>
            <div class="h-6 w-11 shrink-0 animate-pulse rounded-full bg-stone-100"></div>
          </div>
        </div>

        <div v-else class="divide-y divide-stone-100">
          <div
            v-for="g in PREFERENCE_GROUPS"
            :key="g.value"
            class="flex items-start gap-3 py-3.5 first:pt-0 last:pb-0"
          >
            <span class="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-stone-100 text-stone-500">
              <i :class="g.icon"></i>
            </span>
            <div class="min-w-0 flex-1">
              <p class="text-sm font-semibold text-stone-800">{{ g.label }}</p>
              <p class="mt-0.5 text-xs leading-snug text-stone-500">{{ GROUP_DESCRIPTIONS[g.value] }}</p>
            </div>
            <!-- role="switch" + aria-checked → screen reader อ่านสถานะออก ไม่ต้องเดาจากสี -->
            <button
              type="button"
              role="switch"
              :aria-checked="isOn(g.value)"
              :aria-label="`${isOn(g.value) ? 'ปิด' : 'เปิด'}การแจ้งเตือน ${g.label}`"
              :disabled="savingGroup === g.value"
              @click="toggleGroup(g.value)"
              class="relative mt-1 inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#B91C1C] focus-visible:ring-offset-2 disabled:opacity-50"
              :class="isOn(g.value) ? 'bg-[#B91C1C]' : 'bg-stone-300'"
            >
              <span
                class="inline-block h-5 w-5 rounded-full bg-white shadow transition-transform motion-reduce:transition-none"
                :class="isOn(g.value) ? 'translate-x-[22px]' : 'translate-x-0.5'"
              ></span>
            </button>
          </div>
        </div>
      </div>

      <!-- ===== 📱 ติดตั้งแอป ===== -->
      <!-- ซ่อนเมื่อเปิดในโหมดแอพที่ติดตั้งแล้ว — ไม่มีอะไรให้ติดตั้งอีก -->
      <div v-if="!isStandalone" class="rounded-2xl border border-stone-200 bg-white p-6 sm:p-8">
        <div class="mb-5 flex items-center gap-3">
          <span class="flex h-10 w-10 items-center justify-center rounded-xl bg-stone-100 text-stone-500">
            <i class="bi bi-phone"></i>
          </span>
          <div>
            <h2 class="text-lg font-bold text-stone-900">ติดตั้งแอป</h2>
            <p class="text-xs text-stone-500 mt-0.5">
              เพิ่ม PIRIvoice ลงหน้าจอ เปิดได้เร็วเหมือนแอพ ไม่ต้องพิมพ์ที่อยู่เว็บอีก
            </p>
          </div>
        </div>

        <div class="flex items-start gap-3">
          <div class="min-w-0 flex-1">
            <p v-if="canPromptInstall" class="text-sm font-semibold text-stone-800">
              เครื่องนี้ติดตั้งได้เลย
            </p>
            <template v-else-if="isIosSafari">
              <p class="text-sm font-semibold text-stone-800">iPhone / iPad ต้องติดตั้งเอง</p>
              <ol class="mt-1.5 space-y-0.5 text-xs font-medium text-stone-600">
                <li>1. แตะปุ่ม <i class="bi bi-box-arrow-up text-stone-800"></i> แชร์ ที่แถบล่างจอ</li>
                <li>2. เลือก “เพิ่มไปที่หน้าจอ”</li>
              </ol>
            </template>
            <template v-else>
              <p class="text-sm font-semibold text-stone-800">เครื่องนี้ติดตั้งอัตโนมัติไม่ได้</p>
              <!-- เบราว์เซอร์ในแอพอื่น (LINE/Facebook) ไม่มีเมนูติดตั้ง ⇒ ต้องบอกให้เปิด Chrome จริง -->
              <p class="mt-1.5 text-xs font-medium text-stone-600">
                เปิดหน้านี้ด้วย <b>Chrome</b> แล้วเลือก “ติดตั้งแอป” จากเมนู
                <i class="bi bi-three-dots-vertical"></i> มุมขวาบน
              </p>
              <!-- 🔎 วินิจฉัย: อาการ "ไม่เห็นแบนเนอร์" เกิดได้จาก 5 สาเหตุที่หน้าตาเหมือนกัน
                   และแก้คนละทาง ⇒ โชว์ค่าจริงเฉพาะตอนที่ติดตั้งไม่ได้ (คนที่ติดตั้งได้ไม่เห็นความยุ่งเหยิงนี้) -->
              <p class="mt-2.5 text-xs text-stone-500">{{ installHint }}</p>
              <details class="mt-1.5">
                <summary class="cursor-pointer text-[11px] font-semibold text-stone-400 hover:text-stone-600">
                  รายละเอียดทางเทคนิค
                </summary>
                <dl class="mt-2 grid grid-cols-[1fr_auto] gap-x-4 gap-y-1 text-[11px] text-stone-500">
                  <template v-for="row in diagRows" :key="row.label">
                    <dt>{{ row.label }}</dt>
                    <dd :class="row.on ? 'font-semibold text-stone-700' : ''">
                      {{ row.on ? 'ใช่' : 'ไม่' }}
                    </dd>
                  </template>
                </dl>
              </details>
            </template>
          </div>

          <button
            v-if="canPromptInstall"
            type="button"
            :disabled="installing"
            @click="onInstall"
            class="shrink-0 rounded-xl bg-[#B91C1C] px-4 py-2.5 text-xs font-bold text-white transition-colors hover:bg-[#991B1B] disabled:opacity-60"
          >
            <i v-if="installing" class="bi bi-arrow-repeat animate-spin"></i>
            <span v-else>ติดตั้งเลย</span>
          </button>
        </div>
      </div>

      <!-- ===== 📊 สถิติของฉัน (C3) ===== -->
      <PersonalStatsCard
        :stats="stats"
        :loading="statsLoading"
        :error="statsError"
        @retry="loadStats"
      />

      <p class="text-center text-[11px] text-stone-400 pb-4">
        แก้ไขโปรไฟล์หรือเปลี่ยนรหัสผ่านได้จากเมนู <i class="bi bi-three-dots-vertical"></i> มุมขวาบน
      </p>
    </div>
  </div>
</template>

<style scoped>
.fade-up-enter-active, .fade-up-leave-active { transition: all 0.18s ease; }
.fade-up-enter-from, .fade-up-leave-to { opacity: 0; transform: translateY(6px) scale(0.98); }
</style>
