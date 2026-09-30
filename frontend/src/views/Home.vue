<!-- eslint-disable vue/multi-word-component-names -- 'Home' = หน้า Welcome กลาง (หลังล็อกอิน) -->
<script setup lang="ts">
import { ref, computed, onMounted, nextTick } from 'vue';
import { RouterLink } from 'vue-router';
import { useAuthStore } from '@/stores/auth';
import { useNotificationsStore } from '@/stores/notifications';
import { getHomeSummary } from '@/services/home';
import type { HomeSummary } from '@/types/home';
import { remainingLabel, voteCountLabel } from '@/types/home';
// กติกาที่เกี่ยวกับ "กิจกรรม" อยู่ใน `@/types/event` — การ์ดหน้าแรกเป็นแค่ *ผู้ใช้* ของมัน
// ⇒ `EventDetail.vue` เรียกใช้ตัวเดียวกันได้โดยไม่ต้อง import จากโมดูลของหน้าแรก
import { closingLabel, registrationChip, seatsWarning } from '@/types/event';
import { getDashboardSummary } from '@/services/dashboard';
import type { DashboardSummary } from '@/types/dashboard';
import { listReports } from '@/services/board';
import type { ReportItem } from '@/types/board';
import PersonalStatsCard from '@/components/PersonalStatsCard.vue';
import { STATUS_BADGE, statusShort } from '@/constants/status';

const authStore = useAuthStore();
const notificationsStore = useNotificationsStore();

const rootEl = ref<HTMLElement | null>(null);

// ============ เวลาไทย (Asia/Bangkok) + คำทักทาย ============
const hourBangkok = computed(() =>
  Number(
    new Intl.DateTimeFormat('en-GB', { hour: '2-digit', hour12: false, timeZone: 'Asia/Bangkok' }).format(
      new Date(),
    ),
  ),
);
const dateLabel = computed(() =>
  new Intl.DateTimeFormat('th-TH', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    year: 'numeric',
    timeZone: 'Asia/Bangkok',
  }).format(new Date()),
);
const greeting = computed(() => {
  const h = hourBangkok.value;
  if (h >= 5 && h < 12) return 'สวัสดีตอนเช้า';
  if (h >= 12 && h < 17) return 'สวัสดีตอนบ่าย';
  if (h >= 17 && h < 21) return 'สวัสดีตอนเย็น';
  return 'สวัสดี';
});
const displayName = computed(() => authStore.displayName || 'เพื่อนชาวพิริยาลัย');

const roleLabel = computed(() => {
  const first = authStore.roles[0];
  const map: Record<string, string> = {
    student: 'นักเรียน',
    class_president: 'หัวหน้าห้อง',
    vice_academic: 'รองวิชาการ',
    vice_discipline: 'รองวินัย',
    vice_activity: 'รองกิจกรรม',
    vice_reception: 'รองปฏิคม',
    level_president: 'ประธานระดับ',
    council_member: 'สภานักเรียน',
    council_president: 'ประธานสภา',
    teacher_council: 'ครูสภานักเรียน',
    teacher: 'ครู',
  };
  return first ? map[first.role || ''] || first.role || 'นักเรียน' : 'นักเรียน';
});
const roleLine = computed(() => {
  const first = authStore.roles[0];
  if (!first) return roleLabel.value;
  if (first.room_name) return `${roleLabel.value} · ${first.room_name}`;
  if (first.level) return `${roleLabel.value} · ${first.level}`;
  return roleLabel.value;
});
const avatarChar = computed(() => {
  // ตัวแรกของชื่อจริง (first_name) — ไม่เอาคำนำหน้า/ชื่อเล่น
  const n = authStore.user?.first_name || displayName.value;
  return n ? n.charAt(0).toUpperCase() : 'ส';
});

function formatDate(s: string): string {
  try {
    return new Intl.DateTimeFormat('th-TH', {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
      timeZone: 'Asia/Bangkok',
    }).format(new Date(s));
  } catch {
    return s;
  }
}

// ============ Quick actions (ตามสิทธิ์ — ให้ตรงกับ sidebar เสมอ) ============
interface QuickAction {
  key: string;
  label: string;
  desc: string;
  icon: string;
  to: string;
  badge: number;
  accent: string; // สีพื้น icon tile
  featured?: boolean;
}
const quickActions = computed<QuickAction[]>(() => {
  const acts: QuickAction[] = [];
  if (authStore.hasPermission('VIEW_DASHBOARD')) {
    acts.push({
      key: 'dashboard', label: 'แดชบอร์ด', desc: 'สถิติภาพรวม', icon: 'bi-grid-1x2',
      to: '/app/dashboard', badge: 0, accent: 'bg-stone-100 text-stone-700',
    });
  }
  if (authStore.hasPermission('RECEIVE_ISSUES')) {
    acts.push({
      key: 'received', label: 'เรื่องที่รับ', desc: 'คิวรอจัดการ', icon: 'bi-inbox',
      to: '/app/issues/received', badge: notificationsStore.counts.issue_received || 0,
      accent: 'bg-stone-100 text-stone-700',
    });
  }
  acts.push({
    key: 'boards', label: 'PIRI Boards', desc: 'โหวต + พูดคุย', icon: 'bi-columns-gap',
    to: '/app/boards', badge: notificationsStore.counts.board || 0,
    accent: 'bg-stone-100 text-stone-700',
  });
  acts.push({
    key: 'mine', label: 'เรื่องของฉัน', desc: 'ติดตามสถานะ', icon: 'bi-file-earmark-text',
    to: '/app/issues/mine', badge: 0, accent: 'bg-stone-100 text-stone-700',
  });
  acts.push({
    key: 'new', label: 'แจ้งเรื่องใหม่', desc: 'ส่งเสียงของคุณ', icon: 'bi-plus-circle',
    to: '/app/issues/new', badge: 0, accent: 'bg-[#B91C1C] text-white', featured: true,
  });
  return acts;
});
const canReceive = computed(() => authStore.hasPermission('RECEIVE_ISSUES'));
const isCouncil = computed(() => authStore.isCouncilAuthority);
const canDashboard = computed(() => authStore.hasPermission('VIEW_DASHBOARD'));

// 🔔 unread badge ตามกลุ่ม (guard — counts[x] อาจ undefined)
function unreadCount(key: string): number {
  return notificationsStore.counts[key] || 0;
}

// ============ Home summary (GET /api/home/summary) ============
// ⭐ 1 call ได้ทุกอย่างที่ทุกคนเห็นเหมือนกัน: ประกาศ · สรุปเรื่องของฉัน ·
//    รอฉันตอบ · โหวตที่ยังไม่โหวต · สถิติส่วนตัว (เดิมยิง 3 ตัวแยกกัน)
// ❌ แดชบอร์ด + คิวรายงาน ยังยิงแยกโดยเจตนา — เป็น permission-gated
//    และแดชบอร์ดรัน aggregate หนักทั้งโรงเรียน (ย้ายเข้ามาจะทำให้ Home ช้าลงทุกคน)
const home = ref<HomeSummary | null>(null);
const loadingHome = ref(true);
const homeError = ref(false);

async function loadHome() {
  loadingHome.value = true;
  homeError.value = false;
  try {
    home.value = await getHomeSummary();
  } catch {
    homeError.value = true;
    // ล้างของเก่าทิ้ง — ไม่งั้นกด "ลองใหม่" แล้วพัง จะเห็นข้อมูลค้างของรอบก่อนปนกับ error
    home.value = null;
  } finally {
    loadingHome.value = false;
    void nextTick(() => runCountUps());
  }
}

const summary = computed(() => home.value?.my_issues ?? null);
const announcements = computed(() => home.value?.announcements ?? []);
const pendingOnMe = computed(() => home.value?.pending_on_me ?? []);
const pendingTotal = computed(() => home.value?.pending_on_me_total ?? 0);
const unvotedBoards = computed(() => home.value?.unvoted_boards ?? []);
const unvotedTotal = computed(() => home.value?.unvoted_boards_total ?? 0);
const stats = computed(() => home.value?.stats ?? null);

// "และอีก N …" — คิดจาก total จริงที่ backend ส่งมา ไม่ใช่เทียบกับ limit ที่ hardcode
const pendingRestLabel = computed(() =>
  remainingLabel(pendingTotal.value, pendingOnMe.value.length),
);
const unvotedRestLabel = computed(() =>
  remainingLabel(unvotedTotal.value, unvotedBoards.value.length, 'บอร์ด'),
);

// ⏳ กิจกรรมใกล้ปิดรับ (4.5)
const closingSoon = computed(() => home.value?.closing_soon_events ?? []);
const closingSoonTotal = computed(() => home.value?.closing_soon_events_total ?? 0);
const closingSoonRestLabel = computed(() =>
  remainingLabel(closingSoonTotal.value, closingSoon.value.length, 'กิจกรรม'),
);

const statusMap = computed<Record<string, number>>(() => {
  const m: Record<string, number> = {};
  for (const s of summary.value?.by_status ?? []) m[s.status] = s.count;
  return m;
});

// ============ Moderation queue (สภา/แอดมิน) ============
const reports = ref<ReportItem[]>([]);
const reportsTotal = ref(0);
const loadingReports = ref(isCouncil.value);
const reportsError = ref(false);

async function loadReports() {
  if (!isCouncil.value) return;
  loadingReports.value = true;
  reportsError.value = false;
  try {
    const res = await listReports({ status: 'open', limit: 5 });
    reports.value = res.items ?? [];
    reportsTotal.value = res.total ?? 0;
  } catch {
    reportsError.value = true;
  } finally {
    loadingReports.value = false;
  }
}

// ============ Dashboard stats strip (VIEW_DASHBOARD) ============
const dash = ref<DashboardSummary | null>(null);
const loadingDash = ref(canDashboard.value);
const dashError = ref(false);

async function loadDash() {
  if (!canDashboard.value) return;
  loadingDash.value = true;
  dashError.value = false;
  try {
    dash.value = await getDashboardSummary();
  } catch {
    dashError.value = true;
  } finally {
    loadingDash.value = false;
  }
}

onMounted(() => {
  void loadHome();
  void loadReports();
  void loadDash();
});

// ============ Count-up (ตัวเลขวิ่งเมื่อโหลดเสร็จ) ============
function animateNumber(el: HTMLElement) {
  if (el.dataset.done === '1') return;
  const target = Number(el.dataset.count || '0');
  const decimals = Number(el.dataset.decimals || '0');
  const duration = 750;
  const start = performance.now();
  const fmt = new Intl.NumberFormat('th-TH');
  const tick = (now: number) => {
    const p = Math.min(1, (now - start) / duration);
    const eased = 1 - Math.pow(1 - p, 3);
    const val = target * eased;
    el.textContent = decimals > 0 ? val.toFixed(decimals) : fmt.format(Math.round(val));
    if (p < 1) requestAnimationFrame(tick);
    else el.dataset.done = '1';
  };
  requestAnimationFrame(tick);
}
function runCountUps() {
  rootEl.value?.querySelectorAll<HTMLElement>('[data-count]').forEach(animateNumber);
}

const hasActiveIssues = computed(() => {
  const t = statusMap.value;
  return (t['pending'] ?? 0) + (t['in_progress'] ?? 0) + (t['escalated'] ?? 0);
});

// ⚠️ ประกาศไม่ถูกตัดด้วยจำนวน (ห้าม slice) — ดูคอมเมนต์ใน template
const annIconColor: Record<string, string> = {
  urgent: 'bg-[#B91C1C]',
  high: 'bg-[#991B1B]',
  normal: 'bg-stone-300',
};
</script>

<template>
  <div ref="rootEl" class="space-y-5 pb-2 sm:space-y-6">
    <!-- ============ Hero greeting ============ -->
    <section class="relative overflow-hidden rounded-2xl border border-stone-200 bg-white p-6 sm:p-8">
      <!-- ลายจุดพื้น (Editorial dot-grid) -->
      <div class="pointer-events-none absolute inset-0 bg-[radial-gradient(#e7e5e4_1px,transparent_1px)] [background-size:16px_16px] opacity-40"></div>

      <div class="relative flex flex-col gap-6 md:flex-row md:items-center md:justify-between">
        <!-- ทักทาย -->
        <div class="min-w-0">
          <div class="flex items-center gap-4">
            <span class="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl bg-[#B91C1C] text-lg font-bold text-white sm:h-16 sm:w-16">
              {{ avatarChar }}
            </span>
            <div>
              <p class="text-[11px] font-bold uppercase tracking-widest text-[#B91C1C]">{{ greeting }} 👋</p>
              <h1 class="mt-1 truncate text-2xl font-bold tracking-tight text-stone-900 sm:text-3xl">
                {{ displayName }}
              </h1>
              <p class="mt-0.5 text-xs font-semibold text-stone-500">
                {{ roleLine }}
              </p>
            </div>
          </div>
          <p class="mt-4 flex items-center gap-1.5 text-xs font-medium text-stone-500 sm:text-sm">
            <i class="bi bi-calendar3 text-[#B91C1C]"></i>
            {{ dateLabel }}
          </p>
        </div>

        <!-- CTA -->
        <div class="flex flex-col gap-2.5">
          <RouterLink
            to="/app/issues/new"
            class="inline-flex items-center justify-center gap-2 rounded-xl bg-[#B91C1C] px-6 py-3 text-sm font-semibold text-white transition-colors hover:bg-[#991B1B] active:scale-[0.97] sm:text-base"
          >
            <i class="bi bi-plus-lg text-lg"></i>
            แจ้งเรื่อง / ความคิดเห็น
          </RouterLink>
          <RouterLink
            to="/app/issues/mine"
            class="inline-flex items-center justify-center gap-2 rounded-xl border border-stone-200 bg-white px-6 py-3 text-sm font-semibold text-stone-700 transition-colors hover:bg-stone-50 active:scale-[0.97]"
          >
            <i class="bi bi-file-earmark-text"></i>
            ดูเรื่องของฉัน
          </RouterLink>
        </div>
      </div>
    </section>

    <!-- ============ โหลดหน้าแรกไม่สำเร็จ ============
         ⚠️ ประกาศ/สรุปเรื่องของฉัน/รอฉันตอบ/โหวต/สถิติ มาจาก **call เดียว**
            ⇒ ล้มพร้อมกันทั้งหมด · แสดงใบเดียวที่บนสุด ไม่กระจาย error ซ้ำ 5 ที่
            (คิวรายงานกับแดชบอร์ดเป็น call แยก ⇒ มี error ของตัวเองอยู่แล้ว) -->
    <section
      v-if="homeError"
      class="flex flex-col items-center justify-center gap-3 rounded-2xl border-2 border-dashed border-stone-200 bg-white px-6 py-12 text-center"
    >
      <span class="flex h-11 w-11 items-center justify-center rounded-2xl bg-stone-100 text-stone-400">
        <i class="bi bi-wifi-off text-lg"></i>
      </span>
      <div>
        <p class="text-sm font-semibold text-stone-700">โหลดข้อมูลหน้าแรกไม่สำเร็จ</p>
        <p class="mt-1 text-xs text-stone-400">ประกาศ สรุปเรื่องของคุณ และสถิติ ยังโหลดไม่ได้</p>
      </div>
      <button
        type="button"
        @click="loadHome"
        class="inline-flex items-center gap-1.5 rounded-xl bg-stone-900 px-4 py-2 text-xs font-bold text-white transition-colors hover:bg-stone-800"
      >
        <i class="bi bi-arrow-clockwise"></i> ลองใหม่
      </button>
    </section>

    <!-- ============ ประกาศโรงเรียน ============
         ⭐ โชว์ **ทั้งหมด** ที่ยังใช้งานอยู่ — ไม่มี slice()/เพดานจำนวนโดยเจตนา
            (เจ้าของระบบสั่งว่า "ไม่ต้องกำหนดว่าให้โชว์กี่อัน ให้โชว์ทั้งหมดที่ยังไม่ถอดออก")
            backend กรอง `deleted_at IS NULL AND retired_at IS NULL` มาให้แล้ว
            ⇒ ที่นี่ไม่ต้องกรอง/ตัดอะไรอีก และ **ห้าม slice** แม้จะอยากให้สั้นลง
            (endpoint/ข้อมูลชุดเดียวกันนี้ถูกใช้โดย Landing.vue ด้วย) -->
    <section v-else-if="announcements.length > 0" class="rounded-2xl border border-stone-200 bg-white px-5 py-4">
      <div class="flex items-start gap-3">
        <span class="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-stone-100 text-stone-600">
          <i class="bi bi-megaphone"></i>
        </span>
        <div class="min-w-0 space-y-2">
          <p class="text-xs font-bold uppercase tracking-wider text-stone-500">ประกาศโรงเรียน</p>
          <div v-for="a in announcements" :key="a.id" class="flex items-start gap-2.5">
            <span class="mt-1.5 h-2 w-2 shrink-0 rounded-full" :class="annIconColor[a.priority] || 'bg-stone-300'"></span>
            <p class="text-sm font-medium leading-relaxed text-stone-700">{{ a.message }}</p>
          </div>
        </div>
      </div>
    </section>

    <!-- ============ ทางลัดไปเมนูต่าง ๆ (ตามสิทธิ์) ============ -->
    <section v-if="quickActions.length > 0">
      <div class="grid grid-cols-2 gap-3 sm:grid-cols-3 sm:gap-4 xl:grid-cols-4">
        <RouterLink
          v-for="a in quickActions"
          :key="a.key"
          :to="a.to"
          class="group relative flex flex-col items-start gap-3 rounded-2xl border border-stone-200 bg-white p-4 transition-colors hover:border-stone-300 hover:bg-stone-50 active:scale-[0.98] sm:p-5"
        >
          <span class="flex h-12 w-12 items-center justify-center rounded-xl text-xl" :class="a.accent">
            <i :class="['bi', a.icon]"></i>
          </span>
          <div class="min-w-0">
            <p class="truncate text-sm font-bold text-stone-800 sm:text-[15px]">{{ a.label }}</p>
            <p class="mt-0.5 truncate text-[11px] font-medium text-stone-400">{{ a.desc }}</p>
          </div>
          <span
            v-if="a.badge > 0"
            class="absolute right-3 top-3 flex h-5 min-w-[20px] items-center justify-center rounded-full bg-[#B91C1C] px-1.5 text-[10px] font-bold text-white"
          >
            {{ a.badge > 99 ? '99+' : a.badge }}
          </span>
        </RouterLink>
      </div>
    </section>

    <!-- ============ My-issue summary (ทุกคน) ============ -->
    <section v-if="!homeError" class="overflow-hidden rounded-2xl border border-stone-200 bg-white">
      <!-- Header -->
      <div class="flex items-center justify-between gap-3 px-6 pb-1 pt-6">
        <div class="flex items-center gap-3">
          <span class="flex h-10 w-10 items-center justify-center rounded-xl bg-stone-100 text-stone-600">
            <i class="bi bi-stack text-lg"></i>
          </span>
          <div>
            <h2 class="text-base font-bold tracking-tight text-stone-900 sm:text-lg">สรุปเรื่องของฉัน</h2>
            <p class="text-[11px] font-medium text-stone-400 sm:text-xs">ติดตามสถานะเรื่องที่คุณแจ้งไว้</p>
          </div>
        </div>
        <RouterLink
          to="/app/issues/mine"
          class="hidden shrink-0 items-center gap-1 rounded-xl px-3 py-2 text-xs font-bold text-[#B91C1C] transition-colors hover:bg-stone-100 sm:flex"
        >
          ดูทั้งหมด <i class="bi bi-arrow-right"></i>
        </RouterLink>
      </div>

      <!-- Skeleton -->
      <div v-if="loadingHome" class="px-6 pb-6 pt-3">
        <div class="flex flex-wrap items-center gap-3">
          <div class="h-14 w-14 animate-pulse rounded-2xl bg-stone-100"></div>
          <div class="space-y-2">
            <div class="h-4 w-40 animate-pulse rounded-lg bg-stone-100"></div>
            <div class="h-3 w-24 animate-pulse rounded-lg bg-stone-100"></div>
          </div>
        </div>
        <div class="mt-5 grid grid-cols-2 gap-px overflow-hidden rounded-2xl border border-stone-200 bg-stone-200 sm:grid-cols-4">
          <div v-for="n in 4" :key="n" class="bg-white p-5">
            <div class="h-9 animate-pulse rounded-xl bg-stone-100"></div>
          </div>
        </div>
      </div>

      <!-- Empty: ยังไม่เคยแจ้ง -->
      <div v-else-if="summary && summary.total_issues === 0" class="px-6 pb-7 pt-2">
        <div class="flex flex-col items-center gap-4 rounded-2xl border-2 border-dashed border-stone-200 bg-white px-6 py-12 text-center">
          <span class="flex h-14 w-14 items-center justify-center rounded-2xl bg-stone-100 text-2xl text-stone-400">
            <i class="bi bi-megaphone"></i>
          </span>
          <div>
            <p class="text-base font-bold text-stone-800">ยังไม่เคยแจ้งเรื่องเลย</p>
            <p class="mx-auto mt-1 max-w-sm text-xs leading-relaxed text-stone-500 sm:text-sm">
              เจอปัญหาหรือมีข้อเสนอแนะ? แจ้งเข้ามาได้เลย หัวหน้าห้องและสภานักเรียนจะช่วยติดตามให้
            </p>
          </div>
          <RouterLink
            to="/app/issues/new"
            class="inline-flex items-center gap-2 rounded-xl bg-[#B91C1C] px-6 py-3 text-sm font-semibold text-white transition-colors hover:bg-[#991B1B] active:scale-[0.97]"
          >
            <i class="bi bi-plus-lg"></i> แจ้งเรื่องแรกเลย
          </RouterLink>
        </div>
      </div>

      <!-- Loaded with data -->
      <div v-else-if="summary" class="px-6 pb-6 pt-3">
        <!-- ตัวเลขหลัก (ledger) -->
        <div class="grid grid-cols-2 gap-px overflow-hidden rounded-2xl border border-stone-200 bg-stone-200 sm:grid-cols-4">
          <div class="bg-white p-4 sm:p-5">
            <p class="text-[10px] font-bold uppercase tracking-wider text-stone-500">แจ้งไปทั้งหมด</p>
            <p class="mt-1 font-display text-2xl font-bold leading-none text-stone-900 sm:text-3xl" :data-count="summary.total_issues">0</p>
          </div>

          <div class="bg-white p-4 sm:p-5">
            <p class="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wider text-stone-500">
              <span class="h-1.5 w-1.5 rounded-full bg-stone-400"></span> รอรับเรื่อง
            </p>
            <p class="mt-1 font-display text-2xl font-bold leading-none text-stone-900 sm:text-3xl" :data-count="statusMap['pending'] ?? 0">0</p>
          </div>

          <div class="bg-white p-4 sm:p-5">
            <p class="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wider text-stone-500">
              <span class="h-1.5 w-1.5 rounded-full bg-[#B91C1C]"></span> กำลังดำเนินการ
            </p>
            <p class="mt-1 font-display text-2xl font-bold leading-none text-stone-900 sm:text-3xl" :data-count="statusMap['in_progress'] ?? 0">0</p>
          </div>

          <div class="bg-white p-4 sm:p-5">
            <p class="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wider text-stone-500">
              <span class="h-1.5 w-1.5 rounded-full bg-emerald-500"></span> เสร็จแล้ว
            </p>
            <p class="mt-1 font-display text-2xl font-bold leading-none text-stone-900 sm:text-3xl" :data-count="statusMap['resolved'] ?? 0">0</p>
          </div>
        </div>

        <!-- ชิปสถานะอื่น + ทางลัด -->
        <div class="mt-4 flex flex-wrap items-center gap-2">
          <RouterLink
            v-if="(statusMap['escalated'] ?? 0) > 0"
            :to="{ name: 'my-issues', query: { status: 'escalated' } }"
            class="inline-flex items-center gap-1.5 rounded-full bg-[#B91C1C]/10 px-3 py-1.5 text-[11px] font-bold text-[#B91C1C] ring-1 ring-[#B91C1C]/20 transition-colors hover:bg-[#B91C1C]/15"
          >
            <i class="bi bi-arrow-up-circle text-xs"></i> ส่งต่อระดับบน {{ statusMap['escalated'] }}
          </RouterLink>
          <RouterLink
            v-if="hasActiveIssues > 0"
            :to="{ name: 'my-issues', query: { status: 'pending,in_progress,escalated' } }"
            class="inline-flex items-center gap-1.5 rounded-full bg-stone-100 px-3 py-1.5 text-[11px] font-bold text-stone-600 ring-1 ring-stone-200 transition-colors hover:bg-stone-200"
          >
            <i class="bi bi-lightning-charge text-xs text-stone-500"></i> กำลังดำเนินการ/ส่งต่อรวม {{ hasActiveIssues }}
          </RouterLink>
          <RouterLink
            v-if="(statusMap['rejected'] ?? 0) > 0"
            :to="{ name: 'my-issues', query: { status: 'rejected' } }"
            class="inline-flex items-center gap-1.5 rounded-full bg-stone-100 px-3 py-1.5 text-[11px] font-bold text-stone-600 ring-1 ring-stone-200 transition-colors hover:bg-stone-200"
          >
            <i class="bi bi-x-circle text-xs"></i> ปัดตก {{ statusMap['rejected'] }}
          </RouterLink>
          <RouterLink
            v-if="(statusMap['cancelled'] ?? 0) > 0"
            :to="{ name: 'my-issues', query: { status: 'cancelled' } }"
            class="inline-flex items-center gap-1.5 rounded-full bg-stone-100 px-3 py-1.5 text-[11px] font-bold text-stone-500 ring-1 ring-stone-200 transition-colors hover:bg-stone-200"
          >
            <i class="bi bi-x-octagon text-xs"></i> ยกเลิก {{ statusMap['cancelled'] }}
          </RouterLink>
          <RouterLink
            to="/app/issues/mine"
            class="ml-auto inline-flex items-center gap-1 rounded-xl px-3 py-2 text-xs font-bold text-[#B91C1C] transition-colors hover:bg-stone-100 sm:hidden"
          >
            ดูทั้งหมด <i class="bi bi-arrow-right"></i>
          </RouterLink>
        </div>

        <!-- ล่าสุด 2 เรื่อง -->
        <div v-if="summary.recent.length > 0" class="mt-4 border-t border-stone-200 pt-4">
          <p class="mb-2 flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-stone-500">
            <i class="bi bi-clock-history"></i> เรื่องล่าสุด
          </p>
          <div class="space-y-1">
            <RouterLink
              v-for="it in summary.recent.slice(0, 2)"
              :key="it.id"
              :to="{ name: 'issue-detail', params: { id: it.id } }"
              class="group flex items-center gap-3 rounded-xl px-3.5 py-3 transition-colors hover:bg-stone-50"
            >
              <span class="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-stone-100 text-stone-600">
                <i :class="['bi', it.requested_destination === 'vote' ? 'bi-bar-chart' : it.requested_destination === 'talk' ? 'bi-chat-dots' : 'bi-file-earmark-text']"></i>
              </span>
              <span class="min-w-0 flex-1">
                <span class="block truncate text-sm font-semibold text-stone-800 group-hover:text-[#B91C1C]">{{ it.title }}</span>
                <span class="text-[11px] font-medium text-stone-400">{{ formatDate(it.created_at) }}</span>
              </span>
              <span
                class="shrink-0 rounded-full px-2.5 py-1 text-[10px] font-bold"
                :class="STATUS_BADGE[it.status] || 'bg-stone-100 text-stone-500'"
              >
                {{ statusShort(it.status) }}
              </span>
            </RouterLink>
          </div>
        </div>
      </div>
    </section>

    <!-- ============ สถิติของฉัน (C3) ============
         ใช้การ์ดตัวเดียวกับ Profile.vue — ข้อมูลมาจาก home summary ไม่ต้องยิงซ้ำ
         ⚠️ ไม่ต้องใส่หัวข้อเอง การ์ดมีหัวข้อ + ช่วงภาค (พ.ศ.) ในตัวแล้ว -->
    <PersonalStatsCard
      v-if="!homeError"
      :stats="stats"
      :loading="loadingHome"
      compact
    />

    <!-- ============ รอฉันตอบ (คนรับเรื่อง) ============
         แทนบล็อก "เรื่องที่รอจัดการ" เดิม — เป้าแคบกว่าโดยเจตนา:
         `current_assignee_id = ฉัน` เท่านั้น (เดิมใช้ received=true ซึ่งกว้างกว่ามาก
         รวมเรื่องที่ฉันแค่เป็นผู้แจ้ง/มี countdown ของฉัน ⇒ ไม่ใช่ "รอฉันตอบ")
         ⚠️ ไม่พิมพ์ยอดไว้ข้างลิงก์ "คิวทั้งหมด" — ยอดนี้เป็นเป้าแคบ
            ไม่เท่ากับที่หน้าคิว (`/app/issues/received`) แสดง ⇒ ใส่ไปจะดูเหมือนบั๊ก
            (ขึ้นยอดจริงไว้ในตัวบล็อกแทน) -->
    <section v-if="!homeError && canReceive" class="overflow-hidden rounded-2xl border border-stone-200 bg-white">
      <div class="flex items-center justify-between gap-3 px-6 pb-1 pt-6">
        <div class="flex items-center gap-3">
          <span class="relative flex h-10 w-10 items-center justify-center rounded-xl bg-[#B91C1C] text-white">
            <i class="bi bi-reply-all text-lg"></i>
            <span
              v-if="unreadCount('issue_received') > 0"
              class="absolute -right-1.5 -top-1.5 flex h-5 min-w-[20px] items-center justify-center rounded-full bg-white px-1 text-[10px] font-bold text-[#B91C1C] ring-1 ring-stone-200"
            >
              {{ unreadCount('issue_received') > 99 ? '99+' : unreadCount('issue_received') }}
            </span>
          </span>
          <div>
            <h2 class="text-base font-bold tracking-tight text-stone-900 sm:text-lg">รอฉันตอบ</h2>
            <p class="text-[11px] font-medium text-stone-400 sm:text-xs">เรื่องที่ค้างอยู่ที่คุณและยังไม่ปิด</p>
          </div>
        </div>
        <RouterLink
          to="/app/issues/received"
          class="flex shrink-0 items-center gap-1 rounded-xl px-3 py-2 text-xs font-bold text-[#B91C1C] transition-colors hover:bg-stone-100"
        >
          คิวทั้งหมด <i class="bi bi-arrow-right"></i>
        </RouterLink>
      </div>

      <div class="px-6 pb-6 pt-3">
        <!-- Skeleton -->
        <div v-if="loadingHome" class="space-y-2">
          <div v-for="n in 3" :key="n" class="h-14 animate-pulse rounded-2xl bg-stone-100"></div>
        </div>
        <!-- Empty -->
        <div v-else-if="pendingOnMe.length === 0" class="rounded-2xl border border-dashed border-stone-200 px-5 py-8 text-center">
          <p class="text-sm font-bold text-stone-500">🎉 ไม่มีเรื่องค้างรอคุณอยู่</p>
          <p class="mt-1 text-xs text-stone-400">เมื่อมีเรื่องถูกส่งมาถึงระดับคุณ จะขึ้นที่นี่</p>
        </div>
        <!-- List -->
        <div v-else class="space-y-1">
          <RouterLink
            v-for="it in pendingOnMe"
            :key="it.id"
            :to="{ name: 'issue-detail', params: { id: it.id } }"
            class="group flex items-center gap-3 rounded-xl px-3.5 py-3 transition-colors hover:bg-stone-50"
          >
            <span
              class="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl text-xs font-bold"
              :class="it.priority === 'urgent' ? 'bg-[#991B1B] text-white' : it.priority === 'high' ? 'bg-[#B91C1C]/10 text-[#B91C1C]' : 'bg-stone-100 text-stone-500'"
            >
              <i class="bi bi-exclamation-lg"></i>
            </span>
            <span class="min-w-0 flex-1">
              <span class="block truncate text-sm font-semibold text-stone-800 group-hover:text-[#B91C1C]">{{ it.title }}</span>
              <span class="flex items-center gap-1.5 text-[11px] font-medium text-stone-400">
                <i class="bi bi-geo-alt"></i> {{ it.room_name || '—' }}
                <span class="text-stone-300">•</span> {{ formatDate(it.created_at) }}
              </span>
            </span>
            <span
              class="shrink-0 rounded-full px-2.5 py-1 text-[10px] font-bold"
              :class="STATUS_BADGE[it.status] || 'bg-stone-100 text-stone-500'"
            >
              {{ statusShort(it.status) }}
            </span>
            <i class="bi bi-chevron-right text-xs text-stone-300 transition-transform group-hover:translate-x-0.5"></i>
          </RouterLink>

          <p v-if="pendingRestLabel" class="pt-2 text-center text-[11px] font-semibold text-stone-400">
            {{ pendingRestLabel }} — <RouterLink to="/app/issues/received" class="text-[#B91C1C] hover:underline">ดูในคิวทั้งหมด</RouterLink>
          </p>
        </div>
      </div>
    </section>

    <!-- ============ โหวตที่ยังไม่โหวต (ทุกคน) ============
         ⭐ เป็น "สิ่งที่ทำให้กลับมาเปิดซ้ำ" คู่กับ "รอฉันตอบ"
         แสดงเฉพาะเมื่อ **มีของให้ทำ** (หรือกำลังโหลด) — โหวตครบทุกบอร์ดแล้วบล็อกหายไปเอง
         ไม่ต้องมี empty state ให้รกตา -->
    <section
      v-if="!homeError && (loadingHome || unvotedBoards.length > 0)"
      class="overflow-hidden rounded-2xl border border-stone-200 bg-white"
    >
      <div class="flex items-center justify-between gap-3 px-6 pb-1 pt-6">
        <div class="flex items-center gap-3">
          <span class="flex h-10 w-10 items-center justify-center rounded-xl bg-stone-100 text-stone-600">
            <i class="bi bi-bar-chart-steps text-lg"></i>
          </span>
          <div>
            <h2 class="text-base font-bold tracking-tight text-stone-900 sm:text-lg">โหวตที่ยังไม่โหวต</h2>
            <p class="text-[11px] font-medium text-stone-400 sm:text-xs">บอร์ดที่ยังเปิดอยู่ และคุณยังไม่ได้ออกเสียง</p>
          </div>
        </div>
        <RouterLink
          to="/app/boards"
          class="flex shrink-0 items-center gap-1 rounded-xl px-3 py-2 text-xs font-bold text-[#B91C1C] transition-colors hover:bg-stone-100"
        >
          PIRI Boards <i class="bi bi-arrow-right"></i>
        </RouterLink>
      </div>

      <div class="px-6 pb-6 pt-3">
        <div v-if="loadingHome" class="space-y-2">
          <div v-for="n in 2" :key="n" class="h-14 animate-pulse rounded-2xl bg-stone-100"></div>
        </div>
        <div v-else class="space-y-1">
          <RouterLink
            v-for="b in unvotedBoards"
            :key="b.id"
            :to="{ name: 'board-detail', params: { id: b.id } }"
            class="group flex items-center gap-3 rounded-xl px-3.5 py-3 transition-colors hover:bg-stone-50"
          >
            <span class="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-[#B91C1C]/10 text-[#B91C1C]">
              <i class="bi bi-hand-thumbs-up"></i>
            </span>
            <span class="min-w-0 flex-1">
              <span class="block truncate text-sm font-semibold text-stone-800 group-hover:text-[#B91C1C]">{{ b.title }}</span>
              <span class="flex items-center gap-1.5 text-[11px] font-medium text-stone-400">
                <i class="bi bi-people"></i> {{ voteCountLabel(b.vote_count) }}
                <span class="text-stone-300">•</span> {{ formatDate(b.created_at) }}
              </span>
            </span>
            <span class="hidden shrink-0 rounded-full bg-stone-100 px-2.5 py-1 text-[10px] font-bold text-stone-600 sm:inline">
              ไปโหวต
            </span>
            <i class="bi bi-chevron-right text-xs text-stone-300 transition-transform group-hover:translate-x-0.5"></i>
          </RouterLink>

          <p v-if="unvotedRestLabel" class="pt-2 text-center text-[11px] font-semibold text-stone-400">
            {{ unvotedRestLabel }} — <RouterLink to="/app/boards" class="text-[#B91C1C] hover:underline">ดูใน PIRI Boards</RouterLink>
          </p>
        </div>
      </div>
    </section>

    <!-- ============ ⏳ กิจกรรมใกล้ปิดรับ (4.5) ============
         ⭐ แสดงเฉพาะเมื่อ **มีของ** (หรือกำลังโหลด) — กติกาเดียวกับบล็อก "โหวตที่ยังไม่โหวต"
         ข้างบน ⇒ ไม่มี empty state ให้รกตา · การที่บล็อกโผล่ขึ้นมาเอง *คือ* การเตือน

         ⚠️ `closes_at` มาจาก backend = min(วันจัด, กำหนดปิดรับ) — **ห้าม** เอา
            `registration_deadline` มาคิดเองที่นี่ (กิจกรรมที่ไม่ตั้งกำหนดจะปิดที่วันจัด
            ซึ่งเป็นกลุ่มที่พลาดมากที่สุด เพราะไม่มี deadline ให้เห็น)
         ⚠️ แถวที่ฉันสมัครแล้ว **ยังต้องอยู่ในบล็อกนี้** — "สมัครแล้ว" ≠ "เรียบร้อย"
            สิ่งที่ต่างคือปุ่ม (ป้าย "สมัครแล้ว" แทน "ดูรายละเอียด") ไม่ใช่การมีอยู่ของแถว -->
    <section
      v-if="!homeError && (loadingHome || closingSoon.length > 0)"
      class="overflow-hidden rounded-2xl border border-stone-200 bg-white"
      data-testid="closing-soon-card"
    >
      <div class="flex items-center justify-between gap-3 px-6 pb-1 pt-6">
        <div class="flex items-center gap-3">
          <span class="flex h-10 w-10 items-center justify-center rounded-xl bg-amber-50 text-amber-700">
            <i class="bi bi-hourglass-split text-lg"></i>
          </span>
          <div>
            <h2 class="text-base font-bold tracking-tight text-stone-900 sm:text-lg">กิจกรรมใกล้ปิดรับ</h2>
            <!-- ⚠️ ใช้ "ยังไม่ปิดรับ" ไม่ใช่ "ยังสมัครได้อยู่" — กิจกรรมที่เต็มแล้วก็อยู่ในบล็อกนี้
                 (สมัครได้แต่จะได้คิวสำรอง) ⇒ คำเดิมจะขัดกับป้าย "เต็มแล้ว" ในแถวเดียวกัน -->
            <p class="text-[11px] font-medium text-stone-400 sm:text-xs">ยังไม่ปิดรับ — เหลือเวลาอีกไม่มาก</p>
          </div>
        </div>
        <RouterLink
          to="/app/events"
          class="flex shrink-0 items-center gap-1 rounded-xl px-3 py-2 text-xs font-bold text-[#B91C1C] transition-colors hover:bg-stone-100"
        >
          กิจกรรมทั้งหมด <i class="bi bi-arrow-right"></i>
        </RouterLink>
      </div>

      <div class="px-6 pb-6 pt-3">
        <div v-if="loadingHome" class="space-y-2">
          <div v-for="n in 2" :key="n" class="h-14 animate-pulse rounded-2xl bg-stone-100"></div>
        </div>
        <div v-else class="space-y-1">
          <RouterLink
            v-for="ev in closingSoon"
            :key="ev.id"
            :to="{ name: 'event-detail', params: { id: ev.id } }"
            class="group flex items-center gap-3 rounded-xl px-3.5 py-3 transition-colors hover:bg-stone-50"
          >
            <span class="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-amber-50 text-amber-700">
              <i class="bi bi-calendar-event"></i>
            </span>
            <span class="min-w-0 flex-1">
              <span class="block truncate text-sm font-semibold text-stone-800 group-hover:text-[#B91C1C]">{{ ev.title }}</span>
              <span class="flex flex-wrap items-center gap-1.5 text-[11px] font-medium text-stone-400">
                <!-- ป้ายเวลาปิดรับ — หัวใจของการ์ดนี้ จึงใช้สี amber ให้ต่างจากบรรทัดอื่น -->
                <span class="font-bold text-amber-700">{{ closingLabel(ev.closes_at) }}</span>
                <template v-if="ev.location">
                  <span class="text-stone-300">•</span>
                  <span class="inline-flex items-center gap-1"><i class="bi bi-geo-alt"></i> {{ ev.location }}</span>
                </template>
                <!-- `seatsWarning` คืน null เมื่อ **ไม่จำกัดจำนวน หรือยังเหลือเยอะ** ⇒ ไม่มีป้ายโผล่
                     (⚠️ ไม่ใช่ `seatsLabel` — ตัวนั้นตอบ "เหลือกี่ที่" ซึ่งจะขึ้น "ว่างอีก 40 ที่"
                      ที่ไม่ได้บอกอะไร และทำให้ป้ายที่มีอยู่จริงไม่มีความหมาย) -->
                <template v-if="seatsWarning(ev.seats_remaining)">
                  <span class="text-stone-300">•</span>
                  <span class="font-semibold text-stone-500">{{ seatsWarning(ev.seats_remaining) }}</span>
                </template>
              </span>
            </span>
            <!-- `registrationChip` คืน null = ยังไม่สมัคร ⇒ แสดงป้ายเชิญชวนให้กด -->
            <span
              v-if="registrationChip(ev.my_registration_status)"
              class="shrink-0 rounded-full bg-emerald-50 px-2.5 py-1 text-[10px] font-bold text-emerald-700"
            >
              {{ registrationChip(ev.my_registration_status) }}
            </span>
            <span
              v-else
              class="hidden shrink-0 rounded-full bg-[#B91C1C]/10 px-2.5 py-1 text-[10px] font-bold text-[#B91C1C] sm:inline"
            >
              ดูรายละเอียด
            </span>
            <i class="bi bi-chevron-right text-xs text-stone-300 transition-transform group-hover:translate-x-0.5"></i>
          </RouterLink>

          <p v-if="closingSoonRestLabel" class="pt-2 text-center text-[11px] font-semibold text-stone-400">
            {{ closingSoonRestLabel }} — <RouterLink to="/app/events" class="text-[#B91C1C] hover:underline">ดูกิจกรรมทั้งหมด</RouterLink>
          </p>
        </div>
      </div>
    </section>

    <!-- ============ คิวรายงาน (สภา/แอดมิน) ============ -->
    <section v-if="isCouncil" class="overflow-hidden rounded-2xl border border-stone-200 bg-white">
      <div class="flex items-center justify-between gap-3 px-6 pb-1 pt-6">
        <div class="flex items-center gap-3">
          <span class="flex h-10 w-10 items-center justify-center rounded-xl bg-stone-100 text-stone-600">
            <i class="bi bi-flag-fill text-lg"></i>
          </span>
          <div>
            <h2 class="text-base font-bold tracking-tight text-stone-900 sm:text-lg">คิวจัดการรายงาน</h2>
            <p class="text-[11px] font-medium text-stone-400 sm:text-xs">คอมเมนต์ที่ถูกรายงานว่าน่าไม่เหมาะสม</p>
          </div>
        </div>
        <RouterLink
          to="/app/boards/reports"
          class="flex shrink-0 items-center gap-1 rounded-xl px-3 py-2 text-xs font-bold text-[#B91C1C] transition-colors hover:bg-stone-100"
        >
          ไปจัดการ <i class="bi bi-arrow-right"></i>
        </RouterLink>
      </div>

      <div class="px-6 pb-6 pt-3">
        <div v-if="loadingReports" class="space-y-2">
          <div v-for="n in 3" :key="n" class="h-12 animate-pulse rounded-2xl bg-stone-100"></div>
        </div>
        <div v-else-if="reportsError" class="flex flex-col items-center justify-center rounded-2xl border-2 border-dashed border-stone-200 bg-white px-5 py-10 text-center">
          <p class="text-sm font-semibold text-stone-700">โหลดคิวรายงานไม่สำเร็จ</p>
          <button type="button" @click="loadReports" class="mt-3 inline-flex items-center gap-1.5 rounded-lg bg-stone-900 px-4 py-2 text-xs font-bold text-white transition-colors hover:bg-stone-800">
            <i class="bi bi-arrow-clockwise"></i> ลองใหม่
          </button>
        </div>
        <div v-else-if="reports.length === 0" class="rounded-2xl border border-dashed border-stone-200 px-5 py-8 text-center">
          <p class="text-sm font-bold text-stone-500">✅ คิวรายงานว่าง</p>
          <p class="mt-1 text-xs text-stone-400">ไม่มีคอมเมนต์ที่รอรีวิว</p>
        </div>
        <div v-else class="space-y-1">
          <RouterLink
            v-for="r in reports.slice(0, 3)"
            :key="r.id"
            :to="{ name: 'board-reports' }"
            class="group flex items-start gap-3 rounded-xl px-3.5 py-3 transition-colors hover:bg-stone-50"
          >
            <span class="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-stone-100 text-stone-600">
              <i class="bi bi-flag text-sm"></i>
            </span>
            <span class="min-w-0 flex-1">
              <span class="block truncate text-sm font-semibold text-stone-800 group-hover:text-[#B91C1C]">{{ r.board_title }}</span>
              <span class="mt-0.5 block truncate text-[11px] text-stone-400">“{{ r.comment_body }}”</span>
            </span>
            <span v-if="reportsTotal > 3" class="shrink-0 rounded-full bg-[#B91C1C] px-2 py-0.5 text-[10px] font-bold text-white">+{{ reportsTotal - 3 }}</span>
          </RouterLink>
        </div>
      </div>
    </section>

    <!-- ============ สถิติ (VIEW_DASHBOARD) ============ -->
    <section v-if="canDashboard" class="overflow-hidden rounded-2xl border border-stone-200 bg-white">
      <div class="px-6 py-5">
        <div class="flex items-center justify-between gap-3">
          <div class="flex items-center gap-3">
            <span class="flex h-10 w-10 items-center justify-center rounded-xl bg-[#B91C1C] text-white">
              <i class="bi bi-graph-up text-lg"></i>
            </span>
            <div>
              <h2 class="text-sm font-bold tracking-tight text-stone-900 sm:text-base">ภาพรวม {{
                dash?.scope_label ? `ระดับ ${dash.scope_label}` : 'ทั้งโรงเรียน'
              }}</h2>
              <p class="text-[11px] font-medium text-stone-400">จากแดชบอร์ด — ข้อมูลอัปเดตเรียลไทม์</p>
            </div>
          </div>
          <RouterLink to="/app/dashboard" class="hidden shrink-0 items-center gap-1 rounded-xl px-3 py-2 text-xs font-bold text-[#B91C1C] transition-colors hover:bg-stone-100 sm:flex">
            เปิดแดชบอร์ด <i class="bi bi-arrow-right"></i>
          </RouterLink>
        </div>

        <div v-if="loadingDash" class="mt-4 grid grid-cols-2 gap-px overflow-hidden rounded-2xl border border-stone-200 bg-stone-200 sm:grid-cols-4">
          <div v-for="n in 4" :key="n" class="bg-white p-5">
            <div class="h-10 animate-pulse rounded-xl bg-stone-100"></div>
          </div>
        </div>
        <div v-else-if="dashError" class="mt-4 flex flex-col items-center justify-center rounded-2xl border-2 border-dashed border-stone-200 bg-white px-5 py-10 text-center">
          <p class="text-sm font-semibold text-stone-700">โหลดสถิติภาพรวมไม่สำเร็จ</p>
          <button type="button" @click="loadDash" class="mt-3 inline-flex items-center gap-1.5 rounded-lg bg-stone-900 px-4 py-2 text-xs font-bold text-white transition-colors hover:bg-stone-800">
            <i class="bi bi-arrow-clockwise"></i> ลองใหม่
          </button>
        </div>
        <div v-else-if="dash" class="mt-4 grid grid-cols-2 gap-px overflow-hidden rounded-2xl border border-stone-200 bg-stone-200 sm:grid-cols-4">
          <div class="bg-white p-4 sm:p-5">
            <p class="text-[10px] font-bold uppercase tracking-wider text-stone-500">เรื่องทั้งหมด</p>
            <p class="mt-1 font-display text-2xl font-bold leading-none text-stone-900">{{ dash.total_issues }}</p>
          </div>
          <div class="bg-[#B91C1C]/5 p-4 sm:p-5">
            <p class="text-[10px] font-bold uppercase tracking-wider text-[#B91C1C]">ค้าง/เลยกำหนด</p>
            <p class="mt-1 font-display text-2xl font-bold leading-none text-[#991B1B]">{{ dash.overdue }}</p>
          </div>
          <div class="bg-white p-4 sm:p-5">
            <p class="text-[10px] font-bold uppercase tracking-wider text-stone-500">กำลังดำเนินการ</p>
            <p class="mt-1 font-display text-2xl font-bold leading-none text-stone-900">{{ dash.in_progress }}</p>
          </div>
          <div class="bg-white p-4 sm:p-5">
            <p class="text-[10px] font-bold uppercase tracking-wider text-stone-500">เสร็จแล้ว</p>
            <p class="mt-1 font-display text-2xl font-bold leading-none text-stone-900">{{ dash.resolved }}</p>
          </div>
        </div>
      </div>
    </section>

  </div>
</template>

<style scoped>
/* ♿ Keyboard focus ตามธีม */
a:focus-visible,
button:focus-visible {
  outline: 2px solid rgba(185, 28, 28, 0.65);
  outline-offset: 2px;
}

/* ♿ เคารพผู้ที่ปิดแอนิเมชัน */
@media (prefers-reduced-motion: reduce) {
  [data-count] {
    animation: none !important;
  }
}
</style>
