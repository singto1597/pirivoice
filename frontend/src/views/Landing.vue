<!-- eslint-disable vue/multi-word-component-names -->
<script setup lang="ts">
/**
 * 🏠 Landing.vue — PIRIvoice Homepage
 * สภานักเรียน โรงเรียนพิริยาลัยจังหวัดแพร่
 * 
 * Version: 4.2 (Refined Red Theme + Smooth Logos + Gradient Text)
 * Focus: Authenticity, Human-crafted layout, Typography, Real-time Data.
 */
import { ref, computed, watch, nextTick, onMounted, onBeforeUnmount } from 'vue';
import { useRouter } from 'vue-router';
import api from '@/services/api';

/* ============================================================
 * 📐 TypeScript Interfaces (Public API Contract)
 * ============================================================ */
interface SystemStats {
  total_issues: number;
  resolved_issues: number;
  routed_issues: number;
  resolved_rate_percent: number;
  avg_resolve_hours: number;
  active_talk_threads: number;
  active_votes: number;
}

interface StatTrendPoint {
  date: string;
  count: number;
}

interface ResolvedCase {
  id: string;
  title: string;
  category: string;
  reporter_mask: string;
  resolved_at: string;
  solution_summary: string;
  department_in_charge: string;
  impact_score: number;
  duration_hours?: number;
}

type AnnouncementPriority = 'normal' | 'high' | 'urgent';

interface Announcement {
  id: string;
  message: string;
  priority: AnnouncementPriority;
  link?: string;
}

/* ============================================================
 * 🗂️ State Management
 * ============================================================ */
const router = useRouter();

const stats = ref<SystemStats | null>(null);
const statsTrend = ref<StatTrendPoint[]>([]);
const resolvedCases = ref<ResolvedCase[]>([]);
const announcements = ref<Announcement[]>([]);

const isLoadingStats = ref(true);
const isLoadingTrend = ref(true);
const isLoadingCases = ref(true);
const isLoadingAnnouncements = ref(true);

const hasStatsError = ref(false);
const hasTrendError = ref(false);
const hasCasesError = ref(false);
const hasAnnouncementsError = ref(false);

const isScrolled = ref(false);
const ledgerRef = ref<HTMLElement | null>(null);

/* ============================================================
 * 📡 API Integration
 * ============================================================ */
async function fetchStats() {
  isLoadingStats.value = true;
  hasStatsError.value = false;
  try {
    stats.value = (await api.get('/api/v1/public/stats')) as SystemStats;
  } catch {
    hasStatsError.value = true;
  } finally {
    isLoadingStats.value = false;
  }
}

async function fetchStatsTrend() {
  isLoadingTrend.value = true;
  hasTrendError.value = false;
  try {
    const res = (await api.get('/api/v1/public/stats/trend', { params: { days: 14 } })) as StatTrendPoint[];
    statsTrend.value = Array.isArray(res) ? res : [];
  } catch {
    hasTrendError.value = true;
  } finally {
    isLoadingTrend.value = false;
  }
}

async function fetchResolvedCases() {
  isLoadingCases.value = true;
  hasCasesError.value = false;
  try {
    const res = (await api.get('/api/v1/public/resolved-cases', { params: { limit: 5 } })) as ResolvedCase[];
    resolvedCases.value = Array.isArray(res) ? res : [];
  } catch {
    hasCasesError.value = true;
  } finally {
    isLoadingCases.value = false;
  }
}

async function fetchAnnouncements() {
  isLoadingAnnouncements.value = true;
  hasAnnouncementsError.value = false;
  try {
    const res = (await api.get('/api/v1/public/announcements')) as Announcement[];
    announcements.value = Array.isArray(res) ? res : [];
  } catch {
    hasAnnouncementsError.value = true;
  } finally {
    isLoadingAnnouncements.value = false;
  }
}

/* ============================================================
 * 🛠️ Utilities & Formatters
 * ============================================================ */
const prefersReducedMotion = () => typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

const goLogin = () => router.push({ name: 'login' });
const goStats = () => scrollToId('stats');

function scrollToId(id: string) {
  document.getElementById(id)?.scrollIntoView({
    behavior: prefersReducedMotion() ? 'auto' : 'smooth',
    block: 'start',
  });
}

function formatThaiDate(iso: string): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return new Intl.DateTimeFormat('th-TH', { dateStyle: 'medium' }).format(d);
}

function formatShortDate(iso: string): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return new Intl.DateTimeFormat('th-TH', { day: 'numeric', month: 'short' }).format(d);
}

function formatDuration(hours: number): string {
  const h = hours ?? 0;
  if (h <= 0) return 'ทันที';
  if (h < 1) return `${Math.max(1, Math.round(h * 60))} นาที`;
  if (h < 24) return `${h.toFixed(1).replace(/\.0$/, '')} ชม.`;
  const days = Math.floor(h / 24);
  const rest = Math.round(h % 24);
  return rest ? `${days} วัน ${rest} ชม.` : `${days} วัน`;
}

function reporterInitial(mask: string): string {
  if (!mask) return '?';
  const cleaned = mask.replace(/^นักเรียน\s*/, '').trim();
  return (!cleaned || cleaned.includes('ไม่ประสงค์')) ? '?' : cleaned.charAt(0);
}

function formatStatValue(v: number, decimals = 0): string {
  return new Intl.NumberFormat('th-TH', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(v ?? 0);
}

const THAI_DIGITS = ['๐', '๑', '๒', '๓', '๔', '๕', '๖', '๗', '๘', '๙'];
function toThaiNumerals(n: number | string): string {
  return String(n).split('').map(ch => (/[0-9]/.test(ch) ? THAI_DIGITS[Number(ch)] : ch)).join('');
}

/* ============================================================
 * 🎞️ Animations (Count-up)
 * ============================================================ */
function animateStatNumbers(container: HTMLElement) {
  const els = container.querySelectorAll<HTMLElement>('[data-target]');
  if (prefersReducedMotion()) {
    els.forEach(el => {
      el.textContent = formatStatValue(parseFloat(el.dataset.target || '0'), parseInt(el.dataset.decimals || '0', 10));
    });
    return;
  }
  els.forEach(el => {
    const target = parseFloat(el.dataset.target || '0');
    const decimals = parseInt(el.dataset.decimals || '0', 10);
    const duration = 1200;
    const start = performance.now();
    const step = (now: number) => {
      const p = Math.min((now - start) / duration, 1);
      const eased = 1 - Math.pow(1 - p, 4); // easeOutQuart
      el.textContent = formatStatValue(target * eased, decimals);
      if (p < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  });
}

/* ============================================================
 * 📊 Computed Data
 * ============================================================ */
const ledgerStats = computed(() => {
  const s = stats.value;
  if (!s) return [];
  return [
    { key: 'total', label: 'เรื่องส่งเข้ามาทั้งหมด', target: s.total_issues, decimals: 0, suffix: ' เรื่อง' },
    { key: 'routed', label: 'อยู่ระหว่างดำเนินการ', target: s.routed_issues, decimals: 0, suffix: ' เรื่อง' },
    { key: 'resolved', label: 'ดำเนินการเสร็จสิ้น', target: s.resolved_issues, decimals: 0, suffix: ' เรื่อง' },
    { key: 'rate', label: 'อัตราการปิดเรื่อง', target: s.resolved_rate_percent, decimals: 0, suffix: '%' },
    { key: 'avg', label: 'เวลาเฉลี่ยต่อเคส', target: s.avg_resolve_hours, decimals: 1, suffix: ' ชม.' },
  ];
});

// Sparkline SVG Calculator (Safe Type-Check Array Access)
const SPARK_W = 400;
const SPARK_H = 100;
const SPARK_PAD = 8;

const sparkTrend = computed(() => {
  const pts = statsTrend.value;
  if (!pts || pts.length < 2) return null;
  const max = Math.max(...pts.map(p => p.count), 1);
  const stepX = (SPARK_W - SPARK_PAD * 2) / (pts.length - 1);
  
  const coords = pts.map((p, i) => ({
    x: SPARK_PAD + i * stepX,
    y: SPARK_H - SPARK_PAD - (p.count / max) * (SPARK_H - SPARK_PAD * 2),
  }));
  
  const line = coords.map(c => `${c.x.toFixed(1)},${c.y.toFixed(1)}`).join(' ');
  const area = `${SPARK_PAD},${SPARK_H} ${line} ${(SPARK_W - SPARK_PAD).toFixed(1)},${SPARK_H}`;
  
  // Safe extraction for TypeScript strict mode
  const firstPt = pts[0];
  const lastPt = pts[pts.length - 1];
  const lastCoord = coords[coords.length - 1];

  if (!firstPt || !lastPt || !lastCoord) return null;

  return {
    line, area,
    last: lastCoord,
    total: pts.reduce((acc, p) => acc + p.count, 0),
    days: pts.length,
    startDate: firstPt.date,
    endDate: lastPt.date,
  };
});

const sparkDot = computed(() => {
  const t = sparkTrend.value;
  // Type-safety before accessing object properties
  if (!t || !t.last) return null;
  return { left: (t.last.x / SPARK_W) * 100, top: (t.last.y / SPARK_H) * 100 };
});

/* ============================================================
 * 📣 Annotations & Announcements
 * ============================================================ */
const heroAnnouncement = computed(() => announcements.value[0] ?? null);

function priorityDot(p: AnnouncementPriority) {
  if (p === 'urgent') return 'bg-brand animate-pulse';
  if (p === 'high') return 'bg-[#D97706]';
  return 'bg-stone-400';
}
const marqueeDuration = computed(() => `${Math.max(25, announcements.value.length * 10)}s`);

/* ============================================================
 * 💡 Impact / Cases
 * ============================================================ */
const featuredCase = computed(() => [...resolvedCases.value].sort((a, b) => b.impact_score - a.impact_score)[0] ?? null);
const latestCase = computed(() => resolvedCases.value[0] ?? null);
const recentCases = computed(() => resolvedCases.value.filter(c => c.id !== featuredCase.value?.id).slice(0, 3));

/* ============================================================
 * 🪜 Static Data
 * ============================================================ */
const navLinks = [
  { label: 'ภาพรวมตัวเลข', id: 'stats' },
  { label: 'ขั้นตอนการทำงาน', id: 'flow' },
  { label: 'ผลลัพธ์การแก้ไข', id: 'impact' },
  { label: 'เครือข่ายเสียง', id: 'ecosystem' },
];

const workflowSteps = [
  { title: 'รับเรื่องเข้าระบบ', desc: 'นักเรียนแจ้งเรื่องหรือข้อเสนอแนะผ่านแพลตฟอร์มได้ตลอด 24 ชั่วโมง โดยสามารถเลือกปกปิดตัวตนเพื่อความสบายใจ' },
  { title: 'กลั่นกรองระดับห้อง', desc: 'หัวหน้าห้องและผู้แทนฝ่าย เป็นด่านแรกในการรับรู้ปัญหาและบริหารจัดการเบื้องต้นภายในขอบเขตของห้องเรียน' },
  { title: 'ส่งต่อระดับสายชั้น', desc: 'หากเป็นประเด็นที่มีผลกระทบวงกว้าง หรือเกินอำนาจการตัดสินใจระดับห้อง ระบบจะยกระดับเรื่องส่งต่อให้ประธานระดับชั้น' },
  { title: 'พิจารณาโดยสภานักเรียน', desc: 'สภานักเรียนรับช่วงต่อสำหรับวาระสำคัญ เพื่อประสานงานกับคณะผู้บริหารและครู พร้อมติดตามจนกว่าจะปิดกระบวนการ' },
];

/* ============================================================
 * 🔄 Lifecycle
 * ============================================================ */
function onWindowScroll() { isScrolled.value = window.scrollY > 20; }
const thaiYear = computed(() => toThaiNumerals(new Date().getFullYear() + 543));

onMounted(() => {
  fetchStats();
  fetchStatsTrend();
  fetchResolvedCases();
  fetchAnnouncements();
  window.addEventListener('scroll', onWindowScroll, { passive: true });
});
onBeforeUnmount(() => window.removeEventListener('scroll', onWindowScroll));

watch([stats, isLoadingStats], () => {
  if (!stats.value || isLoadingStats.value) return;
  nextTick(() => ledgerRef.value && animateStatNumbers(ledgerRef.value));
});
</script>

<template>
  <div class="piri-landing relative min-h-screen overflow-x-clip bg-[#FAFAF9] text-stone-900 selection:bg-brand/15 selection:text-brand">
    
    <!-- ============================================= -->
    <!-- 🏛️ 1. Header Navigation -->
    <!-- ============================================= -->
    <header
      class="fixed left-0 right-0 top-0 z-50 transition-all duration-400"
      :class="isScrolled ? 'border-b border-stone-200 bg-white' : 'border-transparent bg-transparent'"
    >
      <nav class="mx-auto flex h-[76px] max-w-7xl items-center justify-between px-5 sm:px-6 lg:px-8">
        
        <!-- Brand (Fix Logos rendering smoothly) -->
        <button type="button" class="group flex items-center gap-3.5 focus-visible:outline-none" @click="scrollToId('hero')">
          <div class="flex items-center gap-3">
            <img src="/logos/school-logo.png" alt="ตราโรงเรียนพิริยาลัยจังหวัดแพร่" class="h-[38px] w-auto object-contain drop-shadow-sm transition-transform group-hover:scale-105" />
            <span class="h-6 w-px bg-stone-300"></span>
            <img src="/logos/council-logo.png" alt="ตราสภานักเรียน" class="h-[38px] w-auto object-contain drop-shadow-sm transition-transform group-hover:scale-105" />
          </div>
          <div class="flex flex-col items-start leading-none text-left">
            <span class="text-[17px] font-bold tracking-tight text-stone-900">PIRI<span class="text-brand">voice</span></span>
            <span class="mt-1 hidden text-[11px] font-medium tracking-wide text-stone-500 sm:block">สภานักเรียน โรงเรียนพิริยาลัยจังหวัดแพร่</span>
          </div>
        </button>

        <!-- Links -->
        <div class="hidden items-center gap-8 lg:flex">
          <button
            v-for="link in navLinks" :key="link.id" type="button"
            class="group relative py-1 text-[14px] font-medium text-stone-500 transition-colors hover:text-stone-900 focus-visible:outline-none"
            @click="scrollToId(link.id)"
          >
            {{ link.label }}
            <span class="absolute -bottom-1 left-0 right-0 h-[2px] origin-left scale-x-0 bg-brand transition-transform duration-300 group-hover:scale-x-100 rounded-full"></span>
          </button>
        </div>

        <!-- CTA -->
        <button
          type="button"
          class="inline-flex items-center gap-2.5 rounded-lg bg-stone-900 px-5 py-2.5 text-[13.5px] font-semibold text-white shadow-sm transition-all hover:bg-brand hover:shadow-md active:scale-95 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2"
          @click="goLogin"
        >
          เข้าสู่ระบบ
          <i class="bi bi-arrow-right text-[12px] opacity-80"></i>
        </button>
      </nav>
    </header>

    <main class="pt-[76px]">

      <!-- ============================================= -->
      <!-- 📢 2. Hero Section (Editorial Layout) -->
      <!-- ============================================= -->
      <section id="hero" class="relative pb-24 pt-16 lg:pb-32 lg:pt-24">
        <!-- Abstract background texture -->
        <div class="absolute inset-0 -z-10 bg-[radial-gradient(#e5e7eb_1px,transparent_1px)] [background-size:16px_16px] opacity-40"></div>
        
        <div class="mx-auto max-w-7xl px-5 sm:px-6 lg:px-8">
          <div class="grid items-center gap-16 lg:grid-cols-[1.1fr_0.9fr]">
            
            <!-- Left: Copy & Typography -->
            <div class="hero-in max-w-2xl">
              
              <!-- Live Announcement Pill -->
              <div class="mb-8 min-h-[32px]">
                <div v-if="isLoadingAnnouncements" class="h-7 w-64 animate-pulse rounded-full bg-stone-200/80"></div>
                <button
                  v-else-if="heroAnnouncement" type="button"
                  class="group inline-flex items-center gap-2.5 rounded-full border border-stone-200 bg-white px-3 py-1.5 text-left text-[13px] font-medium text-stone-600 shadow-sm transition-all hover:border-stone-300 hover:shadow"
                  @click="scrollToId('announce')"
                >
                  <span class="flex h-2 w-2 shrink-0 items-center justify-center rounded-full" :class="priorityDot(heroAnnouncement.priority)"></span>
                  <span class="truncate max-w-[250px] sm:max-w-sm">ประกาศ: {{ heroAnnouncement.message }}</span>
                  <i class="bi bi-arrow-right-short shrink-0 text-[16px] text-stone-400 group-hover:text-stone-700"></i>
                </button>
              </div>

              <!-- Main Headline -->
              <h1 class="leading-[1.2] tracking-tight text-stone-900">
                <span class="mb-4 block text-xl font-semibold text-stone-500 sm:text-2xl">ศูนย์กลางรับฟังเสียงนักเรียน</span>
                <span class="block text-[2.75rem] font-bold sm:text-6xl lg:text-[4.2rem]">
                  <span class="block">
                    ทุกเสียง<span class="text-brand">มีความหมาย</span>
                  </span>
                  <span class="block">
                    ทุกเสียง<span class="text-brand">พาพิริยาลัย</span>
                  </span>
                  <span class="relative inline-block">
                    ก้าวไปด้วยกัน
                    <span class="absolute -bottom-2 left-0 right-0 h-3 bg-brand/10 -skew-x-12"></span>
                  </span>
                </span>
              </h1>

              <p class="mt-8 max-w-lg text-[16px] leading-relaxed text-stone-600 sm:text-[17px]">
                แพลตฟอร์มรับแจ้งเรื่องและข้อเสนอแนะอย่างเป็นทางการ ส่งตรงถึงผู้รับผิดชอบตามสายงานแบบเรียลไทม์ โปร่งใส ตรวจสอบได้ และรับรองความปลอดภัยในการปกปิดตัวตน
              </p>

              <!-- Actions -->
              <div class="mt-10 flex flex-wrap items-center gap-4">
                <button
                  type="button"
                  class="inline-flex items-center gap-2.5 rounded-xl bg-brand px-7 py-3.5 text-[15px] font-semibold text-white shadow-lg shadow-brand/25 transition-all hover:bg-brand-strong hover:shadow-xl hover:-translate-y-0.5 active:scale-95"
                  @click="goLogin"
                >
                  <i class="bi bi-pencil-square text-lg"></i>
                  แจ้งเรื่องเลย
                </button>
                <button
                  type="button"
                  class="inline-flex items-center gap-2.5 rounded-xl border-2 border-stone-200 bg-white px-7 py-3.5 text-[15px] font-semibold text-stone-700 transition-all hover:border-stone-300 active:scale-95"
                  @click="goStats"
                >
                  ดูรายงานสถิติ
                </button>
              </div>
            </div>

            <!-- Right: Paper Collage (Editorial aesthetic) -->
            <div class="hero-in relative hidden h-[480px] lg:block" style="animation-delay: 150ms">
              
              <!-- Card 1: Top Announcement -->
              <div
                class="settle absolute left-4 top-8 z-10 w-[320px] rounded-2xl border border-stone-200 bg-white p-6"
                style="--rot: -4deg; animation-delay: 0.2s;"
              >
                <div class="mb-3 flex items-center gap-2">
                  <i class="bi bi-megaphone text-stone-400"></i>
                  <p class="text-[12px] font-bold uppercase tracking-wider text-stone-400">อัปเดตล่าสุด</p>
                </div>
                <template v-if="isLoadingAnnouncements">
                  <div class="space-y-2">
                    <div class="h-4 w-full animate-pulse rounded bg-stone-100"></div>
                    <div class="h-4 w-3/4 animate-pulse rounded bg-stone-100"></div>
                  </div>
                </template>
                <p v-else-if="heroAnnouncement" class="text-[15px] font-medium leading-relaxed text-stone-800">
                  {{ heroAnnouncement.message }}
                </p>
                <p v-else class="text-[14px] text-stone-500 italic">ยังไม่มีประกาศในขณะนี้</p>
              </div>

              <!-- Card 2: Recent Resolved Case -->
              <div
                class="settle absolute right-0 top-[200px] z-20 w-[340px] rounded-2xl border border-stone-200 bg-[#FAFAF9] p-6"
                style="--rot: 3deg; animation-delay: 0.35s;"
              >
                <div class="mb-3 flex items-center gap-2">
                  <span class="flex h-5 w-5 items-center justify-center rounded-full bg-emerald-100 text-[10px] text-emerald-700"><i class="bi bi-check-lg"></i></span>
                  <p class="text-[12px] font-bold uppercase tracking-wider text-stone-400">เพิ่งดำเนินการสำเร็จ</p>
                </div>
                <template v-if="isLoadingCases">
                  <div class="space-y-2">
                    <div class="h-4 w-full animate-pulse rounded bg-stone-200/60"></div>
                    <div class="h-4 w-2/3 animate-pulse rounded bg-stone-200/60"></div>
                  </div>
                </template>
                <template v-else-if="latestCase">
                  <p class="line-clamp-2 text-[15px] font-semibold leading-snug text-stone-900">"{{ latestCase.title }}"</p>
                  <p class="mt-3 text-[13px] font-medium text-stone-500"><i class="bi bi-building mr-1.5 opacity-70"></i>{{ latestCase.department_in_charge }}</p>
                </template>
                <p v-else class="text-[14px] text-stone-500 italic">รอการประมวลผลเคสแรก</p>
              </div>

              <!-- Graphic 3: The Rubber Stamp (Total Issues) -->
              <div
                v-if="!isLoadingStats && stats"
                class="settle absolute bottom-6 left-[30%] z-30 flex h-32 w-32 flex-col items-center justify-center rounded-full border-[3px] border-brand bg-transparent text-center mix-blend-multiply"
                style="--rot: -15deg; animation-delay: 0.5s;"
              >
                <div class="absolute inset-1.5 rounded-full border-[1.5px] border-brand/60"></div>
                <span class="text-3xl font-black tabular-nums text-brand">{{ formatStatValue(stats.total_issues) }}</span>
                <span class="mt-0.5 text-[10.5px] font-bold tracking-wide text-brand leading-tight">เรื่องที่แจ้ง<br>เข้ามา</span>
              </div>
            </div>

          </div>
        </div>
      </section>

      <!-- ============================================= -->
      <!-- 📜 3. Bulletin Ticker -->
      <!-- ============================================= -->
      <div id="announce" class="mx-auto max-w-7xl px-5 sm:px-6 lg:px-8 -mt-6 relative z-10">
        <div class="flex h-14 items-center overflow-hidden rounded-xl border border-stone-200 bg-white shadow-sm">
          
          <div v-if="isLoadingAnnouncements" class="flex w-full items-center px-5">
            <div class="h-3 w-64 animate-pulse rounded bg-stone-100"></div>
          </div>
          <div v-else-if="hasAnnouncementsError" class="flex w-full items-center justify-between px-5">
            <span class="text-[13.5px] font-medium text-stone-500"><i class="bi bi-wifi-off mr-2"></i>ระบบเชื่อมต่อประกาศขัดข้อง</span>
            <button type="button" class="text-[12.5px] font-bold text-stone-600 hover:text-stone-900" @click="fetchAnnouncements">ลองเชื่อมต่อใหม่</button>
          </div>
          
          <template v-else-if="announcements.length > 0">
            <!-- Label -->
            <div class="flex h-full shrink-0 items-center justify-center border-r border-stone-100 bg-stone-50 px-5 text-[12.5px] font-bold tracking-widest text-stone-500 uppercase">
              <i class="bi bi-pin-angle-fill mr-2 text-stone-400"></i> กระดานข่าว
            </div>
            <!-- Marquee -->
            <div class="mask-edges relative h-full flex-1 overflow-hidden bg-white">
              <div class="marquee-track flex h-full items-center whitespace-nowrap" :style="{ animationDuration: marqueeDuration }">
                <div v-for="copy in 2" :key="copy" class="flex items-center" :aria-hidden="copy === 2">
                  <template v-for="a in announcements" :key="a.id">
                    <span class="mx-6 flex items-center gap-2.5">
                      <span class="h-1.5 w-1.5 rounded-full" :class="priorityDot(a.priority)"></span>
                      <a v-if="a.link" :href="a.link" target="_blank" rel="noopener" tabindex="-1" class="text-[14.5px] font-medium text-stone-600 transition-colors hover:text-brand">
                        {{ a.message }} <i class="bi bi-arrow-up-right text-[10px] ml-0.5 opacity-50"></i>
                      </a>
                      <span v-else class="text-[14.5px] font-medium text-stone-600">{{ a.message }}</span>
                    </span>
                  </template>
                </div>
              </div>
            </div>
          </template>
          
          <div v-else class="px-5 text-[14px] font-medium text-stone-500">ยังไม่มีประกาศใหม่ในขณะนี้</div>
        </div>
      </div>

      <!-- ============================================= -->
      <!-- 📉 4. The Ledger (Live Stats) -->
      <!-- ============================================= -->
      <section id="stats" class="py-20 lg:py-32">
        <div class="mx-auto max-w-7xl px-5 sm:px-6 lg:px-8">
          
          <!-- Section Header -->
          <div class="mb-12 max-w-2xl">
            <div class="mb-4 inline-flex items-center gap-2 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-[11px] font-bold tracking-widest text-emerald-700 uppercase">
              <span class="relative flex h-2 w-2">
                <span class="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75"></span>
                <span class="relative inline-flex h-2 w-2 rounded-full bg-emerald-500"></span>
              </span>
              Real-time Database Sync
            </div>
            <h2 class="text-3xl font-bold tracking-tight text-stone-900 sm:text-4xl">รายงานสถิติสถานะปัจจุบัน</h2>
            <p class="mt-4 text-[16px] leading-relaxed text-stone-600">ตัวเลขทั้งหมดประมวลผลจากฐานข้อมูลจริงของระบบโดยอัตโนมัติ เพื่อสร้างความโปร่งใสในทุกกระบวนการทำงาน</p>
          </div>

          <!-- Loading / Error -->
          <div v-if="isLoadingStats" class="h-72 w-full animate-pulse rounded-2xl border border-stone-200 bg-stone-100/50"></div>
          <div v-else-if="hasStatsError" class="flex flex-col items-center justify-center rounded-2xl border-2 border-dashed border-stone-200 bg-stone-50 py-20 text-center">
            <i class="bi bi-database-exclamation text-3xl text-stone-400 mb-3"></i>
            <p class="text-[15px] font-semibold text-stone-700">ไม่สามารถดึงข้อมูลสถิติได้ในขณะนี้</p>
            <button type="button" class="mt-4 rounded-lg bg-stone-900 px-5 py-2 text-[13px] font-bold text-white hover:bg-stone-800 transition-colors" @click="fetchStats">ดึงข้อมูลอีกครั้ง</button>
          </div>

          <!-- Data Grid (Ledger Style) -->
          <template v-else>
            <!-- 1px borders trick using grid gap and background color -->
            <div ref="ledgerRef" class="grid overflow-hidden rounded-2xl border border-stone-200 bg-stone-200 sm:grid-cols-2 lg:grid-cols-5 gap-px shadow-sm">
              <div v-for="card in ledgerStats" :key="card.key" class="bg-white p-6 transition-colors hover:bg-stone-50/50">
                <p class="mb-3 text-[12.5px] font-semibold uppercase tracking-wide text-stone-500">{{ card.label }}</p>
                <div class="flex items-baseline gap-1.5">
                  <span class="text-4xl font-bold tracking-tight text-stone-900 tabular-nums" :data-target="card.target" :data-decimals="card.decimals">
                    {{ formatStatValue(card.target, card.decimals) }}
                  </span>
                  <span class="text-[14px] font-semibold text-stone-400">{{ card.suffix }}</span>
                </div>
              </div>
            </div>

            <!-- Trend Graphic -->
            <div class="mt-6 rounded-2xl border border-stone-200 bg-white p-6 shadow-sm sm:p-8">
              <div v-if="isLoadingTrend" class="h-32 w-full animate-pulse rounded-xl bg-stone-50"></div>
              <div v-else-if="hasTrendError" class="flex items-center justify-between py-10">
                <span class="text-[14px] font-medium text-stone-500"><i class="bi bi-exclamation-triangle mr-2"></i>ข้อมูลแนวโน้มขัดข้อง</span>
                <button type="button" class="text-[13px] font-bold text-stone-700 underline decoration-stone-300 underline-offset-4 hover:text-stone-900" @click="fetchStatsTrend">ลองใหม่</button>
              </div>
              <template v-else-if="sparkTrend && sparkDot">
                <div class="mb-6 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
                  <div>
                    <h3 class="text-[15px] font-bold text-stone-900">ปริมาณการแจ้งเรื่องที่เข้าสู่ระบบ</h3>
                    <p class="text-[12px] font-medium text-stone-500 mt-0.5">ภาพรวมในช่วง {{ sparkTrend.days }} วันย้อนหลัง</p>
                  </div>
                  <div class="inline-flex items-center gap-2 rounded-lg bg-stone-50 px-3 py-1.5 border border-stone-100">
                    <span class="text-[11px] font-bold uppercase tracking-widest text-stone-400">Total</span>
                    <span class="text-[16px] font-black tabular-nums text-stone-900">{{ formatStatValue(sparkTrend.total) }}</span>
                  </div>
                </div>
                
                <!-- Custom SVG Sparkline -->
                <div class="relative h-32 w-full">
                  <svg viewBox="0 0 400 100" class="h-full w-full overflow-visible" preserveAspectRatio="none">
                    <defs>
                      <linearGradient id="trendGradient" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stop-color="#B91C1C" stop-opacity="0.15"></stop>
                        <stop offset="100%" stop-color="#B91C1C" stop-opacity="0"></stop>
                      </linearGradient>
                    </defs>
                    <polygon :points="sparkTrend.area" fill="url(#trendGradient)"></polygon>
                    <polyline :points="sparkTrend.line" fill="none" stroke="#B91C1C" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" vector-effect="non-scaling-stroke"></polyline>
                  </svg>
                  <!-- The live dot indicator -->
                  <span
                    class="absolute h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-brand ring-4 ring-white shadow-sm"
                    :style="{ left: sparkDot.left + '%', top: sparkDot.top + '%' }"
                  ></span>
                </div>
                
                <!-- X-Axis Labels -->
                <div class="mt-4 flex justify-between border-t border-stone-100 pt-3 text-[11.5px] font-bold uppercase tracking-wider text-stone-400">
                  <span>{{ formatShortDate(sparkTrend.startDate) }}</span>
                  <span>{{ formatShortDate(sparkTrend.endDate) }}</span>
                </div>
              </template>
              <div v-else class="py-12 text-center text-[14px] font-medium text-stone-500">ข้อมูลแนวโน้มยังไม่เพียงพอสำหรับการวิเคราะห์</div>
            </div>
          </template>

        </div>
      </section>

      <!-- ============================================= -->
      <!-- 🛤️ 5. Workflow (The Process) -->
      <!-- ============================================= -->
      <section id="flow" class="border-t border-stone-200 bg-white py-20 lg:py-32">
        <div class="mx-auto max-w-7xl px-5 sm:px-6 lg:px-8">
          
          <div class="mb-16 max-w-2xl">
            <h2 class="text-[12px] font-bold uppercase tracking-widest text-brand mb-2">Escalation Protocol</h2>
            <h3 class="text-3xl font-bold tracking-tight text-stone-900 sm:text-4xl">กลไกการส่งต่ออย่างเป็นระบบ</h3>
            <p class="mt-4 text-[16px] leading-relaxed text-stone-600">ทุกเสียงถูกออกแบบให้มีผู้ดูแลที่ชัดเจน ระบบจะทำการยกระดับเรื่องขึ้นไปตามสายงานโดยอัตโนมัติ เพื่อให้มั่นใจว่าจะไม่ถูกเพิกเฉย</p>
          </div>

          <div class="relative mx-auto max-w-3xl">
            <!-- The connecting dashed line -->
            <div class="absolute bottom-6 left-[23px] top-6 w-px border-l-2 border-dashed border-stone-200 sm:left-[27px]"></div>
            
            <div class="flex flex-col gap-12">
              <div v-for="(step, i) in workflowSteps" :key="step.title" class="group relative flex gap-6 sm:gap-8">
                <!-- Step Number (Stamp) -->
                <div class="relative z-10 flex h-12 w-12 shrink-0 items-center justify-center rounded-full border-2 border-stone-200 bg-white text-[18px] font-bold text-stone-400 transition-colors duration-300 group-hover:border-brand group-hover:text-brand sm:h-14 sm:w-14 sm:text-[20px]">
                  {{ toThaiNumerals(i + 1) }}
                </div>
                <!-- Content -->
                <div class="pt-2 sm:pt-3">
                  <h4 class="text-[17px] font-bold text-stone-900">{{ step.title }}</h4>
                  <p class="mt-2 text-[14.5px] leading-relaxed text-stone-600">{{ step.desc }}</p>
                </div>
              </div>
            </div>
          </div>
          
        </div>
      </section>

      <!-- ============================================= -->
      <!-- 💼 6. Impact (The Dossier) -->
      <!-- ============================================= -->
      <section id="impact" class="border-t border-stone-200 bg-[#FAFAFA] py-20 lg:py-32">
        <div class="mx-auto max-w-7xl px-5 sm:px-6 lg:px-8">
          
          <div class="mb-14 max-w-2xl">
            <h2 class="text-[12px] font-bold uppercase tracking-widest text-stone-500 mb-2">Track Record</h2>
            <h3 class="text-3xl font-bold tracking-tight text-stone-900 sm:text-4xl">ผลลัพธ์ที่เกิดขึ้นจริง</h3>
            <p class="mt-4 text-[16px] leading-relaxed text-stone-600">แฟ้มข้อมูลสรุปเรื่องที่ผ่านกระบวนการจัดการจนเสร็จสิ้นสมบูรณ์ นี่คือข้อพิสูจน์ว่าทุกเสียงสร้างการเปลี่ยนแปลงได้</p>
          </div>

          <div v-if="isLoadingCases" class="h-[450px] w-full animate-pulse rounded-2xl border border-stone-200 bg-white"></div>
          
          <div v-else-if="hasCasesError" class="flex flex-col items-center justify-center rounded-2xl border-2 border-dashed border-stone-300 bg-white py-24 text-center">
            <p class="text-[15px] font-semibold text-stone-600">ไม่สามารถโหลดแฟ้มข้อมูลได้</p>
            <button type="button" class="mt-4 rounded-lg bg-stone-900 px-5 py-2.5 text-[13px] font-bold text-white hover:bg-stone-800" @click="fetchResolvedCases">ลองใหม่</button>
          </div>

          <div v-else-if="!featuredCase" class="flex flex-col items-center justify-center rounded-2xl border-2 border-dashed border-stone-200 bg-white py-32 text-center">
            <i class="bi bi-folder2-open text-4xl text-stone-300 mb-4"></i>
            <p class="text-[16px] font-bold text-stone-700">อยู่ระหว่างดำเนินการเคสแรก</p>
            <p class="mt-2 text-[14px] text-stone-500">แฟ้มสรุปผลลัพธ์จะปรากฏที่นี่เมื่อกระบวนการเสร็จสิ้น</p>
          </div>

          <div v-else class="grid gap-8 lg:grid-cols-[1fr_320px]">
            <!-- Main Dossier (Featured Case) -->
            <div class="relative overflow-hidden rounded-2xl border border-stone-200 bg-white shadow-sm">
              <!-- Dossier Meta -->
              <div class="flex items-center justify-between border-b border-stone-100 bg-stone-50/50 px-6 py-4 sm:px-8">
                <span class="inline-flex items-center gap-2 text-[12px] font-bold uppercase tracking-wider text-stone-500">
                  <i class="bi bi-tag-fill text-[10px]"></i> {{ featuredCase.category }}
                </span>
                <span class="text-[12.5px] font-medium text-stone-500">
                  <i class="bi bi-calendar3 mr-1.5 opacity-70"></i> {{ formatThaiDate(featuredCase.resolved_at) }}
                </span>
              </div>
              
              <!-- Before / After Grid -->
              <div class="grid md:grid-cols-2">
                <!-- Left: Issue -->
                <div class="border-b border-stone-100 p-6 sm:p-8 md:border-b-0 md:border-r">
                  <p class="mb-4 text-[12px] font-bold uppercase tracking-widest text-brand">ประเด็นที่รับแจ้ง</p>
                  <p class="text-[18px] font-bold leading-snug text-stone-900">“{{ featuredCase.title }}”</p>
                  <div class="mt-6 inline-flex items-center gap-2 rounded-lg border border-stone-100 bg-stone-50 px-3 py-2 text-[12.5px] font-medium text-stone-600">
                    <i class="bi bi-person-fill text-stone-400"></i> แจ้งโดย {{ featuredCase.reporter_mask }}
                  </div>
                </div>
                
                <!-- Right: Resolution -->
                <div class="relative bg-emerald-50/30 p-6 sm:p-8">
                  <!-- Rubber Stamp Effect -->
                  <div class="absolute right-6 top-6 flex h-[72px] w-[72px] rotate-[-12deg] flex-col items-center justify-center rounded-full border-[2.5px] border-emerald-600/80 bg-transparent text-center mix-blend-multiply opacity-80 select-none">
                    <span class="text-[11px] font-black leading-tight text-emerald-700 tracking-wider">จัดการ<br />แล้ว</span>
                  </div>
                  
                  <p class="mb-4 text-[12px] font-bold uppercase tracking-widest text-emerald-700">ผลการดำเนินการ</p>
                  <p class="max-w-[85%] text-[15px] leading-relaxed text-stone-700">{{ featuredCase.solution_summary }}</p>
                  
                  <div class="mt-8 flex flex-wrap gap-x-8 gap-y-4 border-t border-emerald-100/50 pt-5">
                    <div>
                      <p class="mb-1 text-[10.5px] font-bold uppercase tracking-wider text-stone-400">หน่วยงานที่รับผิดชอบ</p>
                      <p class="text-[13.5px] font-semibold text-stone-800">{{ featuredCase.department_in_charge }}</p>
                    </div>
                    <div v-if="featuredCase.duration_hours">
                      <p class="mb-1 text-[10.5px] font-bold uppercase tracking-wider text-stone-400">ระยะเวลาดำเนินการ</p>
                      <p class="text-[13.5px] font-semibold text-stone-800">{{ formatDuration(featuredCase.duration_hours) }}</p>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <!-- Sidebar: Recent Cases -->
            <div class="flex flex-col gap-4">
              <h4 class="text-[12px] font-bold uppercase tracking-widest text-stone-500 px-1">แฟ้มข้อมูลอื่นๆ ล่าสุด</h4>
              <div v-for="c in recentCases" :key="c.id" class="group flex cursor-default flex-col gap-2 rounded-xl border border-stone-200 bg-white p-5 transition-colors hover:border-stone-300">
                <div class="flex items-start gap-3">
                  <div class="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-stone-100 text-[12px] font-bold text-stone-600">
                    {{ reporterInitial(c.reporter_mask) }}
                  </div>
                  <div class="min-w-0 flex-1 pt-0.5">
                    <p class="line-clamp-2 text-[14px] font-bold leading-snug text-stone-800 group-hover:text-brand transition-colors">{{ c.title }}</p>
                    <p class="mt-1.5 truncate text-[12px] font-medium text-stone-500">{{ c.department_in_charge }}</p>
                  </div>
                </div>
              </div>
              <div v-if="recentCases.length === 0" class="rounded-xl border border-dashed border-stone-200 p-6 text-center text-[13px] font-medium text-stone-500">
                ยังไม่มีข้อมูลเพิ่มเติม
              </div>
            </div>
          </div>
          
        </div>
      </section>

      <!-- ============================================= -->
      <!-- 🌐 7. Ecosystem (PIRI Talk & Vote) -->
      <!-- ============================================= -->
      <section id="ecosystem" class="relative bg-stone-950 py-24 text-white lg:py-32 overflow-hidden">
        <!-- Subtle noise/grid texture for dark mode -->
        <div class="absolute inset-0 bg-[radial-gradient(circle_at_1px_1px,rgba(255,255,255,0.05)_1px,transparent_0)] bg-[size:24px_24px]"></div>
        
        <div class="relative mx-auto max-w-7xl px-5 sm:px-6 lg:px-8">
          <div class="grid gap-16 lg:grid-cols-[1fr_1fr] items-center">
            
            <div class="max-w-xl">
              <div class="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1 text-[11px] font-bold tracking-widest text-stone-300 uppercase mb-6">
                <i class="bi bi-box-seam"></i> ระบบนิเวศน์ PIRIvoice
              </div>
              <!-- Added Gradient Text here! -->
              <h2 class="text-3xl font-bold tracking-tight sm:text-5xl leading-[1.25]">
                มากกว่าการแจ้งเรื่อง<br>
                <span class="relative inline-block text-stone-100">
                  คือพื้นที่ของทุกความเห็น
                  <span class="absolute -bottom-1 left-0 right-0 h-2 bg-brand/60 -skew-x-12"></span>
                </span>
              </h2>
              <p class="mt-6 text-[16px] leading-relaxed text-stone-400">
                เราเตรียมพื้นที่สำหรับบทสนทนาที่เปิดกว้างและการลงมติร่วมกัน เพื่อขับเคลื่อนนโยบายโรงเรียนด้วยกระบวนการประชาธิปไตย
              </p>
            </div>

            <div class="grid gap-5 sm:grid-cols-2">
              <!-- PIRI Talk -->
              <div class="rounded-2xl border border-stone-800 bg-stone-900 p-6 sm:p-8 transition-colors hover:bg-stone-900">
                <div class="mb-4 inline-flex h-10 w-10 items-center justify-center rounded-xl bg-stone-800 text-stone-300">
                  <i class="bi bi-chat-text text-lg"></i>
                </div>
                <h3 class="text-[17px] font-bold text-white">PIRI Talk</h3>
                <p class="mt-2 text-[14px] leading-relaxed text-stone-400">กระดานสนทนาสาธารณะ แลกเปลี่ยนความคิดเห็นภายใต้การดูแลของสภานักเรียน</p>
                <div class="mt-6 border-t border-stone-800 pt-5 flex items-baseline gap-2">
                  <span v-if="!isLoadingStats && stats" class="text-3xl font-bold tabular-nums text-white">{{ formatStatValue(stats.active_talk_threads) }}</span>
                  <span v-else class="inline-block h-8 w-12 animate-pulse rounded bg-stone-800"></span>
                  <span class="text-[12px] font-medium text-stone-500 uppercase tracking-widest">Active Threads</span>
                </div>
              </div>
              
              <!-- PIRI Vote -->
              <div class="rounded-2xl border border-stone-800 bg-stone-900 p-6 sm:p-8 transition-colors hover:bg-stone-900">
                <div class="mb-4 inline-flex h-10 w-10 items-center justify-center rounded-xl bg-stone-800 text-stone-300">
                  <i class="bi bi-bar-chart-steps text-lg"></i>
                </div>
                <h3 class="text-[17px] font-bold text-white">PIRI Vote</h3>
                <p class="mt-2 text-[14px] leading-relaxed text-stone-400">ระบบลงคะแนนเสียงเพื่อหาฉันทามติ นำมติส่วนใหญ่ไปประกอบการตัดสินใจจริง</p>
                <div class="mt-6 border-t border-stone-800 pt-5 flex items-baseline gap-2">
                  <span v-if="!isLoadingStats && stats" class="text-3xl font-bold tabular-nums text-white">{{ formatStatValue(stats.active_votes) }}</span>
                  <span v-else class="inline-block h-8 w-12 animate-pulse rounded bg-stone-800"></span>
                  <span class="text-[12px] font-medium text-stone-500 uppercase tracking-widest">Active Polls</span>
                </div>
              </div>
            </div>
            
          </div>
        </div>
      </section>

      <!-- ============================================= -->
      <!-- 🎯 8. Final Call to Action -->
      <!-- ============================================= -->
      <section class="bg-white py-24 sm:py-32">
        <div class="mx-auto max-w-3xl px-5 text-center">
          <h2 class="text-3xl font-black tracking-tight text-stone-900 sm:text-4xl lg:text-5xl leading-tight">
            ทุกเสียงมีความหมาย<br class="hidden sm:block" />
            ทุกเสียงพาพิริยาลัย ก้าวไปด้วยกัน
          </h2>
          <p class="mx-auto mt-6 max-w-xl text-[16.5px] leading-relaxed text-stone-600">
            ลงชื่อเข้าใช้ด้วยรหัสนักเรียน ของโรงเรียน เพื่อใช้สิทธิ์ของนักเรียนเพื่อแจ้งเรื่อง (สามารถตั้งค่าการแจ้งเรื่องแบบไม่ประสงค์ออกนามได้ในระบบ)
          </p>
          <button
            type="button"
            class="mt-10 inline-flex items-center gap-2.5 rounded-xl bg-brand px-9 py-4 text-[16px] font-bold text-white shadow-lg shadow-brand/20 transition-all hover:bg-brand-strong hover:shadow-xl hover:-translate-y-0.5 active:scale-95"
            @click="goLogin"
          >
            ล็อกอินเข้าระบบ
            <i class="bi bi-arrow-right"></i>
          </button>
        </div>
      </section>

    </main>

    <!-- ============================================= -->
    <!-- 🏛️ 9. Footer -->
    <!-- ============================================= -->
    <footer class="border-t border-stone-200 bg-stone-100 pb-10 pt-16">
      <div class="mx-auto max-w-7xl px-5 sm:px-6 lg:px-8">
        
        <div class="mb-12 flex flex-col items-center justify-between gap-8 md:flex-row md:items-end">
          <div class="flex items-center gap-4">
            <!-- Clean Footer Logos without background blocks or mix-blend -->
            <img src="/logos/school-logo.png" alt="" class="h-11 w-auto object-contain opacity-60 grayscale transition-all hover:grayscale-0 hover:opacity-100" />
            <span class="h-8 w-[1.5px] bg-stone-300"></span>
            <img src="/logos/council-logo.png" alt="" class="h-11 w-auto object-contain opacity-60 grayscale transition-all hover:grayscale-0 hover:opacity-100" />
            <div class="ml-1 flex flex-col justify-center">
              <span class="text-[16px] font-bold text-stone-800">PIRI<span class="text-stone-500">voice</span></span>
              <span class="mt-0.5 text-[11px] font-semibold uppercase tracking-widest text-stone-400">Student Council</span>
            </div>
          </div>
          
          <div class="flex items-center gap-6 text-[13.5px] font-semibold text-stone-500">
            <button type="button" class="hover:text-stone-900 transition-colors" @click="goLogin">เข้าสู่ระบบ</button>
            <button type="button" class="hover:text-stone-900 transition-colors" @click="goStats">รายงานสถิติ</button>
            <a href="mailto:contact@piriyalai.ac.th" class="hover:text-stone-900 transition-colors">ติดต่อสภานักเรียน</a>
          </div>
        </div>
        
        <div class="flex flex-col items-center justify-between gap-4 border-t border-stone-200 pt-8 text-[12.5px] font-medium text-stone-500 md:flex-row">
          <p>สงวนลิขสิทธิ์ © {{ thaiYear }} แพลตฟอร์มรับฟังเสียงนักเรียน โรงเรียนพิริยาลัยจังหวัดแพร่</p>
          <a href="https://www.singto1597.xyz/" target="_blank" rel="noopener noreferrer" class="group flex items-center gap-1.5 transition-colors hover:text-stone-900">
            <i class="bi bi-code-square text-stone-400 group-hover:text-stone-900"></i>
            Architected by <span class="font-bold">นายพัฒนพล สุธรรม</span>
          </a>
        </div>
        
      </div>
    </footer>
  </div>
</template>

<style scoped>
/* Typography Base */
@import url('https://fonts.googleapis.com/css2?family=Anuphan:wght@400;500;600;700;800&display=swap');

.piri-landing {
  font-family: 'Anuphan', ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
}

/* Base Animations */
@keyframes heroIn {
  from { opacity: 0; transform: translateY(16px); }
  to { opacity: 1; transform: translateY(0); }
}
.hero-in {
  opacity: 0;
  animation: heroIn 0.8s cubic-bezier(0.16, 1, 0.3, 1) forwards;
}

@keyframes settleIn {
  from { opacity: 0; transform: translateY(20px) rotate(0deg); }
  to { opacity: 1; transform: translateY(0) rotate(var(--rot, 0deg)); }
}
.settle {
  opacity: 0;
  transform: rotate(var(--rot, 0deg));
  animation: settleIn 0.9s cubic-bezier(0.2, 0.8, 0.2, 1) forwards;
}

@keyframes marquee {
  from { transform: translateX(0); }
  to { transform: translateX(-50%); }
}
.marquee-track {
  width: max-content;
  animation: marquee linear infinite;
}
.marquee-track:hover {
  animation-play-state: paused;
}
.mask-edges {
  mask-image: linear-gradient(to right, transparent, black 5%, black 95%, transparent);
}

/* Accessibility */
@media (prefers-reduced-motion: reduce) {
  .hero-in,
  .settle {
    animation: none !important;
    opacity: 1 !important;
    transform: none !important;
  }
  .marquee-track {
    animation: none !important;
  }
  .animate-pulse,
  .animate-ping {
    animation: none !important;
  }
}
</style>