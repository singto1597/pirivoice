<!-- eslint-disable vue/multi-word-component-names -- 'Home' = หน้า Welcome กลาง (หลังล็อกอิน) -->
<script setup lang="ts">
import { ref, computed, onMounted, nextTick } from 'vue';
import { RouterLink } from 'vue-router';
import { useAuthStore } from '@/stores/auth';
import { useNotificationsStore } from '@/stores/notifications';
import { getMyIssueSummary, listIssues } from '@/services/issue';
import type { MyIssueSummary, Issue } from '@/types/issue';
import { getDashboardSummary } from '@/services/dashboard';
import type { DashboardSummary } from '@/types/dashboard';
import { listReports } from '@/services/board';
import type { ReportItem } from '@/types/board';
import { listPublicAnnouncements } from '@/services/public';
import type { Announcement } from '@/services/public';
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
    key: 'playbooks', label: 'P.R. Playbooks', desc: 'คู่มือสภานักเรียน', icon: 'bi-journal-bookmark-fill',
    to: '/app/playbooks', badge: 0, accent: 'bg-stone-100 text-stone-700',
  });
  if (authStore.isCouncilAuthority) {
    acts.push({
      key: 'moderation', label: 'จัดการรายงาน', desc: 'คิวรีวิวคอมเมนต์', icon: 'bi-flag-fill',
      to: '/app/boards/reports', badge: notificationsStore.counts.report || 0,
      accent: 'bg-stone-100 text-stone-700',
    });
  }
  if (authStore.hasPermission('MANAGE_STUDENTS')) {
    acts.push({
      key: 'students', label: 'นักเรียน', desc: 'รายชื่อ + ระดับชั้น', icon: 'bi-people',
      to: '/app/students', badge: 0, accent: 'bg-stone-100 text-stone-700',
    });
  }
  if (authStore.hasPermission('VIEW_AUDIT_LOG')) {
    acts.push({
      key: 'audit', label: 'บันทึกการใช้งาน', desc: 'Audit log', icon: 'bi-clock-history',
      to: '/app/audit-logs', badge: 0, accent: 'bg-stone-100 text-stone-700',
    });
  }
  return acts;
});
const canReceive = computed(() => authStore.hasPermission('RECEIVE_ISSUES'));
const isCouncil = computed(() => authStore.isCouncilAuthority);
const canDashboard = computed(() => authStore.hasPermission('VIEW_DASHBOARD'));

// 🔔 unread badge ตามกลุ่ม (guard — counts[x] อาจ undefined)
function unreadCount(key: string): number {
  return notificationsStore.counts[key] || 0;
}

// ============ My issue summary (GET /api/issues/summary) ============
const summary = ref<MyIssueSummary | null>(null);
const loadingSummary = ref(true);
const summaryError = ref(false);

const statusMap = computed<Record<string, number>>(() => {
  const m: Record<string, number> = {};
  for (const s of summary.value?.by_status ?? []) m[s.status] = s.count;
  return m;
});

async function loadSummary() {
  loadingSummary.value = true;
  summaryError.value = false;
  try {
    summary.value = await getMyIssueSummary();
  } catch {
    summaryError.value = true;
  } finally {
    loadingSummary.value = false;
    void nextTick(() => runCountUps());
  }
}

// ============ Received queue (คนรับเรื่อง) ============
const receivedIssues = ref<Issue[]>([]);
const receivedTotal = ref(0);
const loadingReceived = ref(canReceive.value);
const receivedError = ref(false);

async function loadReceived() {
  if (!canReceive.value) return;
  loadingReceived.value = true;
  receivedError.value = false;
  try {
    // สถานะ "ยังไม่เสร็จ" = pending + in_progress + escalated (server รองรับหลายค่าคั่นด้วย ,)
    const res = await listIssues({ received: true, status: 'pending,in_progress,escalated', limit: 5, sort: 'desc' });
    receivedIssues.value = res.items ?? [];
    receivedTotal.value = res.total ?? 0;
  } catch {
    receivedError.value = true;
  } finally {
    loadingReceived.value = false;
  }
}

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

// ============ ประกาศ (public) ============
const announcements = ref<Announcement[]>([]);
const loadingAnnounce = ref(true);
const announceError = ref(false);

const annIconColor: Record<string, string> = {
  urgent: 'bg-[#B91C1C]',
  high: 'bg-[#991B1B]',
  normal: 'bg-stone-300',
};

async function loadAnnouncements() {
  loadingAnnounce.value = true;
  announceError.value = false;
  try {
    const res = await listPublicAnnouncements();
    announcements.value = Array.isArray(res) ? res : [];
  } catch {
    announceError.value = true;
  } finally {
    loadingAnnounce.value = false;
  }
}

onMounted(() => {
  void loadSummary();
  void loadReceived();
  void loadReports();
  void loadDash();
  void loadAnnouncements();
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

    <!-- ============ ประกาศโรงเรียน ============ -->
    <section v-if="announceError" class="flex flex-col items-center justify-center rounded-2xl border-2 border-dashed border-stone-200 bg-white px-5 py-10 text-center">
      <p class="text-sm font-semibold text-stone-700"><i class="bi bi-wifi-off mr-2"></i>โหลดประกาศไม่สำเร็จ</p>
      <button type="button" @click="loadAnnouncements" class="mt-3 inline-flex items-center gap-1.5 rounded-lg bg-stone-900 px-4 py-2 text-xs font-bold text-white transition-colors hover:bg-stone-800">
        <i class="bi bi-arrow-clockwise"></i> ลองใหม่
      </button>
    </section>

    <section v-else-if="!loadingAnnounce && announcements.length > 0" class="rounded-2xl border border-stone-200 bg-white px-5 py-4">
      <div class="flex items-start gap-3">
        <span class="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-stone-100 text-stone-600">
          <i class="bi bi-megaphone"></i>
        </span>
        <div class="min-w-0 space-y-2">
          <p class="text-xs font-bold uppercase tracking-wider text-stone-500">ประกาศโรงเรียน</p>
          <div v-for="a in announcements.slice(0, 3)" :key="a.id" class="flex items-start gap-2.5">
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
    <section class="overflow-hidden rounded-2xl border border-stone-200 bg-white">
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
      <div v-if="loadingSummary" class="px-6 pb-6 pt-3">
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

      <!-- Error -->
      <div v-else-if="summaryError" class="px-6 pb-6 pt-3">
        <div class="flex flex-col items-center justify-center gap-3 rounded-2xl border-2 border-dashed border-stone-200 bg-white px-6 py-12 text-center">
          <span class="flex h-11 w-11 items-center justify-center rounded-2xl bg-stone-100 text-stone-400">
            <i class="bi bi-wifi-off text-lg"></i>
          </span>
          <p class="text-sm font-semibold text-stone-700">โหลดข้อมูลไม่สำเร็จ</p>
          <button
            type="button"
            @click="loadSummary"
            class="inline-flex items-center gap-1.5 rounded-xl bg-stone-900 px-4 py-2 text-xs font-bold text-white transition-colors hover:bg-stone-800"
          >
            <i class="bi bi-arrow-clockwise"></i> ลองใหม่
          </button>
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

    <!-- ============ เรื่องที่รอจัดการ (คนรับเรื่อง) ============ -->
    <section v-if="canReceive" class="overflow-hidden rounded-2xl border border-stone-200 bg-white">
      <div class="flex items-center justify-between gap-3 px-6 pb-1 pt-6">
        <div class="flex items-center gap-3">
          <span class="relative flex h-10 w-10 items-center justify-center rounded-xl bg-[#B91C1C] text-white">
            <i class="bi bi-inbox text-lg"></i>
            <span
              v-if="unreadCount('issue_received') > 0"
              class="absolute -right-1.5 -top-1.5 flex h-5 min-w-[20px] items-center justify-center rounded-full bg-white px-1 text-[10px] font-bold text-[#B91C1C] ring-1 ring-stone-200"
            >
              {{ unreadCount('issue_received') > 99 ? '99+' : unreadCount('issue_received') }}
            </span>
          </span>
          <div>
            <h2 class="text-base font-bold tracking-tight text-stone-900 sm:text-lg">เรื่องที่รอจัดการ</h2>
            <p class="text-[11px] font-medium text-stone-400 sm:text-xs">ในระดับความรับผิดชอบของคุณ</p>
          </div>
        </div>
        <RouterLink
          to="/app/issues/received"
          class="flex shrink-0 items-center gap-1 rounded-xl px-3 py-2 text-xs font-bold text-[#B91C1C] transition-colors hover:bg-stone-100"
        >
          ทั้งหมด {{ receivedTotal > 0 ? `(${receivedTotal})` : '' }} <i class="bi bi-arrow-right"></i>
        </RouterLink>
      </div>

      <div class="px-6 pb-6 pt-3">
        <!-- Skeleton -->
        <div v-if="loadingReceived" class="space-y-2">
          <div v-for="n in 3" :key="n" class="h-14 animate-pulse rounded-2xl bg-stone-100"></div>
        </div>
        <!-- Error -->
        <div v-else-if="receivedError" class="flex flex-col items-center justify-center rounded-2xl border-2 border-dashed border-stone-200 bg-white px-5 py-10 text-center">
          <p class="text-sm font-semibold text-stone-700">โหลดคิวไม่สำเร็จ</p>
          <button type="button" @click="loadReceived" class="mt-3 inline-flex items-center gap-1.5 rounded-lg bg-stone-900 px-4 py-2 text-xs font-bold text-white transition-colors hover:bg-stone-800">
            <i class="bi bi-arrow-clockwise"></i> ลองใหม่
          </button>
        </div>
        <!-- Empty -->
        <div v-else-if="receivedIssues.length === 0" class="rounded-2xl border border-dashed border-stone-200 px-5 py-8 text-center">
          <p class="text-sm font-bold text-stone-500">🎉 ไม่มีเรื่องค้างรอคุณอยู่</p>
          <p class="mt-1 text-xs text-stone-400">เมื่อมีเรื่องถูกส่งมาถึงระดับคุณ จะขึ้นที่นี่</p>
        </div>
        <!-- List -->
        <div v-else class="space-y-1">
          <RouterLink
            v-for="it in receivedIssues"
            :key="it.id"
            :to="{ name: 'issue-detail', params: { id: it.id } }"
            class="group flex items-center gap-3 rounded-xl px-3.5 py-3 transition-colors hover:bg-stone-50"
          >
            <span
              class="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl text-xs font-bold"
              :class="it.priority === 'high' ? 'bg-[#B91C1C]/10 text-[#B91C1C]' : it.priority === 'urgent' ? 'bg-[#991B1B] text-white' : 'bg-stone-100 text-stone-500'"
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
