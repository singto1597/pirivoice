<!-- eslint-disable vue/multi-word-component-names -- ชื่อตาม route/spec -->
<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { RouterLink } from 'vue-router';
import Swal from 'sweetalert2';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  ArcElement,
  Tooltip,
  Legend,
  Filler,
} from 'chart.js';
import { Line, Bar, Doughnut } from 'vue-chartjs';
import {
  getDashboardSummary,
  getDashboardTraffic,
  type DashboardSummary,
  type MainCategoryDashboard,
  type DashboardTraffic,
} from '@/services/dashboard';
import StatusStackedBar from '@/components/StatusStackedBar.vue';
import { STATUS_DOT, STATUS_BADGE, statusShort } from '@/constants/status';

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, BarElement, ArcElement, Tooltip, Legend, Filler);

// ===== ข้อมูล + การโหลด =====
const data = ref<DashboardSummary | null>(null);
const isLoading = ref(true);
const error = ref('');
const lastUpdated = ref<string | null>(null);

// ===== Traffic (สถิติการเข้าใช้งาน 30 วัน) — เฉพาะ scope 'all' =====
const traffic = ref<DashboardTraffic | null>(null);
const isLoadingTraffic = ref(false);
const trafficError = ref('');

async function loadTraffic() {
  if (!data.value || data.value.scope !== 'all') return;
  isLoadingTraffic.value = true;
  trafficError.value = '';
  try {
    traffic.value = await getDashboardTraffic();
  } catch (e) {
    const msg = e instanceof Error ? e.message : 'เกิดข้อผิดพลาด';
    trafficError.value = msg;
    Swal.fire({ icon: 'error', title: 'โหลดสถิติการใช้งานไม่สำเร็จ', text: msg });
  } finally {
    isLoadingTraffic.value = false;
  }
}

async function loadDashboard() {
  isLoading.value = true;
  error.value = '';
  try {
    data.value = await getDashboardSummary();
    lastUpdated.value = new Date().toISOString();
    await loadTraffic(); // โหลดกราฟการเข้าใช้งาน (เฉพาะ scope 'all')
  } catch (e) {
    const msg = e instanceof Error ? e.message : 'เกิดข้อผิดพลาด';
    error.value = msg;
    Swal.fire({
      icon: 'error',
      title: data.value ? 'รีเฟรชไม่สำเร็จ' : 'ไม่สามารถโหลด Dashboard',
      text: msg,
    });
  } finally {
    isLoading.value = false;
  }
}

onMounted(loadDashboard);

// ===== 🎨 ธีมสีของ 3 หมวดหลัก (accent — ไม่ทับสีสถานะ semantic) =====
interface CategoryTheme {
  icon: string;
  iconBg: string;
  countColor: string;
  barColor: string;
  headerBg: string;
  rowHover: string;
  leaderHighlight: string; // bg+ring ของแถวอันดับ 1
  chevron: string;
}

const CATEGORY_THEMES: Record<string, CategoryTheme> = {
  suggestion: {
    icon: 'bi-lightbulb',
    iconBg: 'bg-stone-900',
    countColor: 'text-stone-900',
    barColor: 'bg-stone-700',
    headerBg: 'bg-stone-50 border-b border-stone-200',
    rowHover: 'hover:bg-stone-50',
    leaderHighlight: 'bg-stone-100 ring-1 ring-stone-200',
    chevron: 'group-hover:text-stone-700',
  },
  wellbeing: {
    icon: 'bi-heart-pulse',
    iconBg: 'bg-stone-500',
    countColor: 'text-stone-600',
    barColor: 'bg-stone-400',
    headerBg: 'bg-stone-50 border-b border-stone-200',
    rowHover: 'hover:bg-stone-50',
    leaderHighlight: 'bg-stone-100 ring-1 ring-stone-200',
    chevron: 'group-hover:text-stone-600',
  },
  report: {
    icon: 'bi-megaphone',
    iconBg: 'bg-brand',
    countColor: 'text-brand',
    barColor: 'bg-brand',
    headerBg: 'bg-brand/5 border-b border-brand/10',
    rowHover: 'hover:bg-brand/5',
    leaderHighlight: 'bg-brand/10 ring-1 ring-brand/20',
    chevron: 'group-hover:text-brand',
  },
};

const DEFAULT_THEME: CategoryTheme = {
  icon: 'bi-collection',
  iconBg: 'bg-stone-700',
  countColor: 'text-stone-700',
  barColor: 'bg-stone-600',
  headerBg: 'bg-stone-50 border-b border-stone-200',
  rowHover: 'hover:bg-stone-50',
  leaderHighlight: 'bg-stone-100 ring-1 ring-stone-200',
  chevron: 'group-hover:text-stone-700',
};

function themeFor(code: string): CategoryTheme {
  return CATEGORY_THEMES[code] ?? DEFAULT_THEME;
}

// ===== 🎛️ KPI (6 ตัว เน้น "อะไรเยอะที่สุด/อะไรค้าง") =====
const statCards = computed(() => [
  { label: 'เรื่องทั้งหมด', value: data.value?.total_issues ?? 0, dot: 'bg-stone-500' },
  { label: 'รอรับเรื่อง', value: data.value?.pending ?? 0, dot: 'bg-stone-400' },
  { label: 'กำลังดำเนินการ', value: data.value?.in_progress ?? 0, dot: 'bg-brand' },
  { label: 'ส่งต่อระดับบน', value: data.value?.escalated ?? 0, dot: 'bg-brand-strong' },
  { label: 'แก้ไขเสร็จ', value: data.value?.resolved ?? 0, dot: 'bg-emerald-500' },
  { label: 'งานเกินเวลา', value: data.value?.overdue ?? 0, dot: 'bg-brand', alert: true },
]);

// ===== 🧮 ตัวช่วยตัวเลข/เปอร์เซ็นต์ =====
function fmtNum(n: number): string {
  return n.toLocaleString('en-US'); // ตัวเลขอาหรับ + คอมมา (กันไทย ๑๒๓ ที่อ่านยากใน data)
}

function percent(part: number, total: number): number {
  if (!total) return 0;
  return Math.round((part / total) * 100);
}

// แท่งสัดส่วนเทียบกับ max ในหมวด (อันดับ 1 เต็มรางเสมอ → เปรียบเทียบ "ใครใหญ่สุด" ได้ทันที)
function shareWidth(part: number, max: number): number {
  if (!max || !part) return 0;
  return Math.max(8, Math.min(100, Math.round((part / max) * 100)));
}

function maxSubCount(cat: MainCategoryDashboard): number {
  // หา max จริงๆ จากทุกหมวดย่อย (รวม "อื่นๆ" ที่ต่อท้าย) — ไม่ใช้ index 0 เฉยๆ
  // เพราะกรณีเรื่องทั้งหมดไปอยู่ _other → index 0 เป็นหมวดจริงที่ count=0
  return Math.max(0, ...cat.subcategories.map((s) => s.count));
}

function resolvedRate(cat: MainCategoryDashboard): number {
  const resolved = cat.by_status.find((s) => s.status === 'resolved')?.count ?? 0;
  return percent(resolved, cat.total);
}

// ===== 🏅 อันดับหมวดย่อย =====
function rankEmoji(n: number): string {
  return ['🥇', '🥈', '🥉'][n - 1] ?? '';
}

function rankCircle(idx: number): string {
  if (idx === 0) return 'bg-stone-200';
  if (idx === 1) return 'bg-stone-100';
  if (idx === 2) return 'bg-stone-50';
  return 'bg-transparent';
}

// ===== 🕐 เวลาไทย Asia/Bangkok =====
function fmtDateTime(iso: string | null): string {
  if (!iso) return '-';
  return new Date(iso).toLocaleString('th-TH', {
    timeZone: 'Asia/Bangkok',
    day: 'numeric', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  });
}

function fmtDate(iso: string | null): string {
  if (!iso) return '-';
  return new Date(iso).toLocaleString('th-TH', {
    timeZone: 'Asia/Bangkok',
    day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit',
  });
}

function fmtDay(iso: string): string {
  const d = new Date(iso + 'T00:00:00Z');
  return d.toLocaleDateString('th-TH', { timeZone: 'UTC', day: 'numeric', month: 'short' });
}

// ===== 📈 Trend chart (7 วัน) =====
const trendChart = computed(() => ({
  labels: (data.value?.trend || []).map((t) => fmtDay(t.date)),
  datasets: [
    {
      label: 'จำนวนเรื่อง/วัน',
      data: (data.value?.trend || []).map((t) => t.count),
      borderColor: '#B91C1C',
      backgroundColor: 'rgba(185,28,28,0.10)',
      fill: true,
      tension: 0.3,
      pointBackgroundColor: '#B91C1C',
    },
  ],
}));

const chartOptions = { responsive: true, maintainAspectRatio: false };

// ===== 📊 กราฟการเข้าใช้งาน (30 วัน) =====
const trafficLoginsChart = computed(() => ({
  labels: (traffic.value?.daily_logins || []).map((t) => fmtDay(t.date)),
  datasets: [
    {
      label: 'ผู้เข้าใช้/วัน',
      data: (traffic.value?.daily_logins || []).map((t) => t.count),
      borderColor: '#57534E',
      backgroundColor: 'rgba(87,83,78,0.10)',
      fill: true,
      tension: 0.3,
      pointBackgroundColor: '#57534E',
    },
  ],
}));

const trafficActionsChart = computed(() => ({
  labels: (traffic.value?.daily_actions || []).map((t) => fmtDay(t.date)),
  datasets: [
    {
      label: 'กิจกรรม/วัน',
      data: (traffic.value?.daily_actions || []).map((t) => t.count),
      backgroundColor: 'rgba(185,28,28,0.75)',
      borderRadius: 4,
    },
  ],
}));

const trafficBreakdownChart = computed(() => ({
  labels: (traffic.value?.action_breakdown || []).map((a) => a.label),
  datasets: [
    {
      label: 'การใช้งาน',
      data: (traffic.value?.action_breakdown || []).map((a) => a.count),
      backgroundColor: [
        '#1C1917', '#57534E', '#D6D3D1', '#B91C1C', '#991B1B',
        '#44403C', '#A8A29E',
      ],
      borderWidth: 1,
    },
  ],
}));

const trafficTotalActions = computed(() =>
  (traffic.value?.action_breakdown || []).reduce((sum, a) => sum + a.count, 0),
);

const hasTrafficData = computed(
  () =>
    (traffic.value?.total_logins ?? 0) + (traffic.value?.failed_logins ?? 0) + trafficTotalActions.value > 0,
);
</script>

<template>
  <div>
    <!-- ===== Header ===== -->
    <div class="flex flex-wrap items-center justify-between gap-3 mb-5">
      <div>
        <p class="text-[11px] font-bold text-brand"><i class="bi bi-bar-chart mr-1"></i> ระบบสถิติ</p>
        <h1 class="mt-0.5 text-2xl font-bold text-stone-900 leading-tight sm:text-3xl">แดชบอร์ด</h1>
        <p v-if="lastUpdated" class="text-xs text-stone-400 mt-1.5">
          อัปเดตล่าสุด <span class="font-medium text-stone-500">{{ fmtDateTime(lastUpdated) }}</span>
        </p>
      </div>
      <div class="flex items-center gap-2">
        <div v-if="data && data.scope === 'level'"
          class="flex items-center gap-2 px-3.5 py-1.5 rounded-xl bg-stone-100 border border-stone-200 text-stone-700 text-sm">
          <i class="bi bi-funnel"></i>
          กำลังแสดงสถิติเฉพาะระดับชั้น <b class="ml-0.5">{{ data.scope_label }}</b>
        </div>
        <div v-else-if="data && data.scope === 'none'"
          class="flex items-center gap-2 px-3.5 py-1.5 rounded-xl bg-brand/5 border border-brand/20 text-brand-strong text-sm">
          <i class="bi bi-exclamation-triangle"></i>
          ยังไม่ได้กำหนดระดับชั้นที่รับผิดชอบ
        </div>
        <div v-else-if="data" class="px-3.5 py-1.5 rounded-xl bg-stone-100 text-stone-600 text-sm">
          <i class="bi bi-globe2 mr-1"></i> ภาพรวมทั้งโรงเรียน
        </div>
        <button
          type="button"
          @click="loadDashboard"
          :disabled="isLoading"
          title="รีเฟรชข้อมูล"
          class="w-9 h-9 rounded-xl bg-white border border-stone-200 text-stone-500 hover:text-brand hover:border-brand/40 flex items-center justify-center transition disabled:opacity-50"
        >
          <i class="bi bi-arrow-clockwise" :class="{ 'animate-spin': isLoading }"></i>
        </button>
      </div>
    </div>

    <!-- ===== Loading: skeleton จำลองโครงสร้างจริง (กัน layout shift) ===== -->
    <div v-if="isLoading && !data" class="space-y-6">
      <div class="overflow-hidden rounded-2xl border border-stone-200 bg-white">
        <div class="grid grid-cols-2 gap-px bg-stone-200 sm:grid-cols-3 xl:grid-cols-6">
          <div v-for="i in 6" :key="i" class="bg-white p-5">
            <div class="mb-2 h-2 w-2 animate-pulse rounded-full bg-stone-200"></div>
            <div class="mb-1 h-7 w-16 animate-pulse rounded bg-stone-200"></div>
            <div class="h-3 w-20 animate-pulse rounded bg-stone-200"></div>
          </div>
        </div>
        <div class="px-5 pb-5">
          <div class="mb-2 h-2 animate-pulse rounded-full bg-stone-200"></div>
          <div class="h-3 w-64 animate-pulse rounded bg-stone-200"></div>
        </div>
      </div>
      <div v-for="i in 3" :key="i" class="rounded-2xl border border-stone-200 bg-white p-5">
        <div class="mb-4 flex items-center gap-3">
          <div class="h-11 w-11 animate-pulse rounded-xl bg-stone-200"></div>
          <div class="flex-1 space-y-1.5">
            <div class="h-4 w-40 animate-pulse rounded bg-stone-200"></div>
            <div class="h-3 w-64 animate-pulse rounded bg-stone-200"></div>
          </div>
        </div>
        <div class="grid gap-4 lg:grid-cols-3">
          <div class="space-y-2.5 lg:col-span-2">
            <div v-for="j in 3" :key="j" class="h-16 animate-pulse rounded-xl bg-stone-100"></div>
          </div>
          <div class="space-y-2.5">
            <div v-for="j in 3" :key="j" class="h-9 animate-pulse rounded-xl bg-stone-100"></div>
          </div>
        </div>
      </div>
    </div>

    <!-- ===== Error ครั้งแรก (ไม่มีข้อมูล) ===== -->
    <div v-else-if="error && !data" class="flex flex-col items-center justify-center rounded-2xl border-2 border-dashed border-stone-200 bg-white px-6 py-16 text-center">
      <div class="mb-3 text-4xl text-stone-300"><i class="bi bi-exclamation-triangle"></i></div>
      <h2 class="mb-1 text-lg font-bold text-stone-700">ไม่สามารถโหลดข้อมูล Dashboard</h2>
      <p class="mb-5 max-w-md text-sm text-stone-500 mx-auto">{{ error }}</p>
      <button
        type="button"
        @click="loadDashboard"
        class="inline-flex items-center gap-1.5 rounded-xl bg-stone-900 px-5 py-2.5 text-sm font-bold text-white transition-colors hover:bg-stone-800"
      >
        <i class="bi bi-arrow-clockwise"></i> ลองใหม่
      </button>
    </div>

    <!-- ===== scope 'none': ครูยังไม่ตั้งระดับชั้น → แนะนำแทนเลข 0 ===== -->
    <div v-else-if="data && data.scope === 'none'" class="rounded-2xl border border-stone-200 bg-white p-12 text-center">
      <div class="mb-3 text-5xl text-stone-300"><i class="bi bi-person-gear"></i></div>
      <h2 class="mb-2 text-lg font-bold text-stone-800">ยังไม่ได้กำหนดระดับชั้นที่รับผิดชอบ</h2>
      <p class="mx-auto max-w-md text-sm text-stone-500">
        ครูยังไม่ระบุระดับชั้น (เช่น ม.4 / ม.5) จึงยังไม่เห็นข้อมูลสถิติ
        <br />กรุณาติดต่อผู้ดูแลระบบเพื่อตั้งค่าระดับชั้นในบัญชีของคุณ
      </p>
    </div>

    <div v-else-if="data" class="space-y-6">
      <!-- ===== KPI band: 6 ตัว + แถบสัดส่วนสถานะรวมทั้งระบบ ===== -->
      <div class="overflow-hidden rounded-2xl border border-stone-200 bg-white">
        <div class="grid grid-cols-2 gap-px bg-stone-200 sm:grid-cols-3 xl:grid-cols-6">
          <div
            v-for="s in statCards"
            :key="s.label"
            class="bg-white p-4 sm:p-5"
            :class="s.alert ? 'bg-brand/5' : ''"
          >
            <div class="mb-1 flex items-center gap-1.5">
              <span class="h-2 w-2 shrink-0 rounded-full" :class="s.dot"></span>
              <span class="truncate text-xs text-stone-500">{{ s.label }}</span>
            </div>
            <p class="font-display text-2xl font-bold text-stone-900 tabular-nums" :class="s.alert ? 'text-brand-strong' : ''">
              {{ fmtNum(s.value) }}
            </p>
          </div>
        </div>
        <div class="px-4 py-4 sm:px-5">
          <StatusStackedBar :stats="data.by_status" :total="data.total_issues" heightClass="h-2" />
          <div class="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-stone-500">
            <span v-for="s in data.by_status" :key="s.status" class="inline-flex items-center gap-1.5">
              <span class="h-2.5 w-2.5 rounded-full" :class="STATUS_DOT[s.status] ?? 'bg-stone-300'"></span>
              {{ s.label }}
              <b class="text-stone-700 tabular-nums">{{ fmtNum(s.count) }}</b>
            </span>
          </div>
        </div>
      </div>

      <!-- ===== 3 หมวดหลัก — แยกการ์ดชัดเจน ===== -->
      <section
        v-for="cat in data.main_categories"
        :key="cat.code"
        class="rounded-2xl border border-stone-200 bg-white overflow-hidden"
      >
        <!-- Header band (ทั้งแถวคลิก → ดูทั้งหมดในหมวด) -->
        <RouterLink
          :to="{ name: 'received-issues', query: { main_category: cat.code } }"
          class="flex items-center justify-between gap-3 px-5 py-4 transition group"
          :class="themeFor(cat.code).headerBg"
        >
          <div class="flex items-center gap-3 min-w-0">
            <div
              class="w-11 h-11 rounded-xl flex items-center justify-center text-xl text-white shrink-0"
              :class="themeFor(cat.code).iconBg"
            >
              <i class="bi" :class="themeFor(cat.code).icon"></i>
            </div>
            <div class="min-w-0">
              <h2 class="text-lg font-bold text-stone-900 flex flex-wrap items-center gap-2">
                {{ cat.label }}
                <span
                  v-if="cat.overdue > 0"
                  class="inline-flex items-center gap-1 px-2 py-0.5 text-[11px] font-semibold rounded-full bg-brand/10 text-brand"
                  title="งานที่เกินกำหนดเวลาในหมวดนี้"
                >
                  <i class="bi bi-alarm"></i> เกินเวลา {{ fmtNum(cat.overdue) }}
                </span>
              </h2>
              <p class="text-xs text-stone-500 truncate mt-0.5">{{ cat.description }}</p>
            </div>
          </div>
          <div class="text-right shrink-0">
            <p class="font-display text-3xl font-bold leading-none tabular-nums" :class="themeFor(cat.code).countColor">
              {{ fmtNum(cat.total) }}
            </p>
            <p class="text-[11px] text-stone-500 mt-1 inline-flex items-center gap-1">
              เรื่อง · เสร็จ {{ resolvedRate(cat) }}%
              <span class="text-brand font-medium group-hover:underline inline-flex items-center gap-0.5">
                ดูทั้งหมด <i class="bi bi-arrow-right"></i>
              </span>
            </p>
          </div>
        </RouterLink>

        <!-- แถบสถานะภายในหมวด (progress รวม) -->
        <div class="px-5 pt-3">
          <StatusStackedBar :stats="cat.by_status" :total="cat.total" heightClass="h-1.5" />
          <div class="flex flex-wrap gap-x-3 gap-y-1 mt-1.5 text-[11px] text-stone-500">
            <span v-for="s in cat.by_status" :key="s.status" class="inline-flex items-center gap-1">
              <span class="w-2 h-2 rounded-full" :class="STATUS_DOT[s.status] ?? 'bg-stone-300'"></span>
              {{ statusShort(s.status) }} <b class="text-stone-700 tabular-nums">{{ fmtNum(s.count) }}</b>
            </span>
          </div>
        </div>

        <!-- Body: leaderboard หมวดย่อย (2/3) + เรื่องล่าสุด (1/3) -->
        <div class="p-5 grid lg:grid-cols-3 gap-6">
          <div class="lg:col-span-2 min-w-0">
            <h3 class="text-sm font-semibold text-stone-700 mb-2.5">
              <i class="bi bi-trophy mr-1" :class="themeFor(cat.code).countColor"></i>
              หมวดย่อยที่แจ้งมากที่สุด
            </h3>
            <div v-if="cat.total > 0" class="space-y-1.5">
              <template v-for="(sc, idx) in cat.subcategories" :key="sc.category">
                <!-- แถวหมวดย่อย → คลิกดูเรื่องในหมวดนั้น (deep-link) -->
                <RouterLink
                  v-if="sc.category !== '_other'"
                  :to="{ name: 'received-issues', query: { main_category: cat.code, category: sc.category } }"
                  class="group flex flex-wrap items-center gap-3 rounded-xl p-3 transition focus-visible:ring-2 focus-visible:ring-brand focus-visible:outline-none"
                  :class="idx === 0 ? themeFor(cat.code).leaderHighlight : themeFor(cat.code).rowHover"
                >
                  <span
                    class="w-8 h-8 rounded-full flex items-center justify-center shrink-0"
                    :class="rankCircle(idx)"
                  >
                    <span v-if="idx < 3" class="text-base" role="img" :aria-label="`อันดับ ${idx + 1}`">
                      {{ rankEmoji(idx + 1) }}
                    </span>
                    <span v-else class="text-sm font-bold text-stone-400" :aria-label="`อันดับ ${idx + 1}`">
                      {{ idx + 1 }}
                    </span>
                  </span>

                  <div class="flex-1 min-w-0">
                    <div class="flex items-center justify-between gap-2">
                      <p class="font-semibold text-stone-800 truncate">{{ sc.label }}</p>
                      <span class="text-lg font-bold text-stone-900 shrink-0 tabular-nums">{{ fmtNum(sc.count) }}</span>
                    </div>
                    <p class="text-[11px] text-stone-400 truncate">{{ sc.description }}</p>
                    <div class="mt-1.5 flex items-center gap-2">
                      <div class="flex-1 h-1.5 bg-stone-100 rounded-full overflow-hidden">
                        <div
                          class="h-full rounded-full transition-all"
                          :class="themeFor(cat.code).barColor"
                          :style="{ width: shareWidth(sc.count, maxSubCount(cat)) + '%' }"
                        ></div>
                      </div>
                      <span class="text-[11px] text-stone-400 shrink-0 tabular-nums">
                        {{ percent(sc.count, cat.total) }}%
                      </span>
                    </div>
                    <div class="mt-1.5 flex flex-wrap gap-x-2.5 gap-y-1">
                      <span
                        v-for="s in sc.by_status.filter((x) => x.count > 0)"
                        :key="s.status"
                        class="inline-flex items-center gap-1 text-[11px] text-stone-500"
                        :title="`${s.label}: ${s.count} เรื่อง`"
                      >
                        <span class="w-2 h-2 rounded-full" :class="STATUS_DOT[s.status] ?? 'bg-stone-300'"></span>
                        {{ statusShort(s.status) }} <b class="text-stone-600 tabular-nums">{{ fmtNum(s.count) }}</b>
                      </span>
                      <span v-if="!sc.by_status.some((x) => x.count > 0)" class="text-[11px] text-stone-400">
                        ยังไม่มีเรื่อง
                      </span>
                    </div>
                  </div>

                  <i class="bi bi-chevron-right text-stone-300 shrink-0 transition" :class="themeFor(cat.code).chevron"></i>
                </RouterLink>

                <!-- หมวดย่อยนอกระบบ (อื่นๆ) → ไม่คลิก เน้นๆ ให้เห็นว่าไม่ใช่หมวดใน config -->
                <div v-else class="flex flex-wrap items-center gap-3 rounded-xl p-3 opacity-80">
                  <span class="w-8 h-8 rounded-full flex items-center justify-center shrink-0 text-sm font-bold text-stone-400"
                    :aria-label="`อันดับ ${idx + 1}`">{{ idx + 1 }}</span>
                  <div class="flex-1 min-w-0">
                    <div class="flex items-center justify-between gap-2">
                      <p class="font-semibold text-stone-500 truncate">{{ sc.label }}</p>
                      <span class="text-lg font-bold text-stone-500 shrink-0 tabular-nums">{{ fmtNum(sc.count) }}</span>
                    </div>
                    <p class="text-[11px] text-stone-400 truncate">{{ sc.description }}</p>
                  </div>
                </div>
              </template>
            </div>
            <p v-else class="text-sm text-stone-400 py-8 text-center">
              <i class="bi bi-inbox mr-1"></i> ยังไม่มีเรื่องในหมวดนี้
            </p>
          </div>

          <!-- เรื่องล่าสุด → คลิกเข้าไปดูผลลัพธ์/ติดตามงาน -->
          <div class="lg:col-span-1 min-w-0">
            <div class="flex items-center justify-between mb-2">
              <h3 class="text-sm font-semibold text-stone-700">
                <i class="bi bi-clock-history mr-1"></i> เรื่องล่าสุด
              </h3>
            </div>
            <div v-if="cat.recent_issues.length" class="space-y-1">
              <RouterLink
                v-for="r in cat.recent_issues"
                :key="r.id"
                :to="{ name: 'issue-detail', params: { id: r.id } }"
                class="flex items-center gap-2.5 p-2 rounded-xl hover:bg-stone-50 transition group focus-visible:ring-2 focus-visible:ring-brand focus-visible:outline-none"
              >
                <span class="w-2 h-2 rounded-full shrink-0" :class="STATUS_DOT[r.status] ?? 'bg-stone-300'"></span>
                <div class="flex-1 min-w-0">
                  <p class="text-sm text-stone-800 truncate group-hover:text-stone-900">{{ r.title }}</p>
                  <p class="text-[11px] text-stone-400 truncate">
                    {{ r.category_label }} · {{ r.room_name || 'ไม่ระบุห้อง' }} · {{ fmtDate(r.created_at) }}
                  </p>
                </div>
                <span
                  class="px-2 py-0.5 text-[11px] font-medium rounded-full shrink-0"
                  :class="STATUS_BADGE[r.status] ?? 'bg-stone-100 text-stone-600'"
                >
                  {{ statusShort(r.status) }}
                </span>
              </RouterLink>
            </div>
            <p v-else class="text-sm text-stone-400 py-4 text-center">ยังไม่มีเรื่องล่าสุด</p>
          </div>
        </div>
      </section>

      <!-- ===== การเข้าใช้งาน (30 วัน) — เฉพาะบทบาทระดับโรงเรียน (scope 'all') ===== -->
      <section v-if="data.scope === 'all'" class="rounded-2xl border border-stone-200 bg-white overflow-hidden">
        <div class="flex items-center justify-between gap-3 px-5 py-4 border-b border-stone-100">
          <h3 class="font-semibold text-stone-800">
            <i class="bi bi-activity mr-1 text-brand"></i> การเข้าใช้งาน (30 วัน)
          </h3>
          <button
            type="button"
            @click="loadTraffic"
            :disabled="isLoadingTraffic"
            title="รีเฟรชสถิติการใช้งาน"
            class="w-8 h-8 rounded-lg bg-stone-100 text-stone-500 hover:text-brand hover:bg-brand/5 flex items-center justify-center transition disabled:opacity-50"
          >
            <i class="bi bi-arrow-clockwise" :class="{ 'animate-spin': isLoadingTraffic }"></i>
          </button>
        </div>

        <!-- Traffic loading skeleton -->
        <div v-if="isLoadingTraffic && !traffic" class="p-5 space-y-4">
          <div class="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div v-for="i in 3" :key="i" class="h-16 bg-stone-100 animate-pulse rounded-xl"></div>
          </div>
          <div class="grid lg:grid-cols-3 gap-4">
            <div v-for="i in 3" :key="'c' + i" class="h-56 bg-stone-100 animate-pulse rounded-xl"></div>
          </div>
        </div>

        <!-- Traffic error -->
        <div v-else-if="trafficError" class="p-5">
          <div class="flex flex-col items-center justify-center rounded-2xl border-2 border-dashed border-stone-200 bg-white px-6 py-12 text-center">
            <p class="text-sm font-semibold text-stone-700"><i class="bi bi-exclamation-triangle mr-1"></i> โหลดสถิติการใช้งานไม่สำเร็จ</p>
            <p class="mt-1 max-w-sm text-xs text-stone-500">{{ trafficError }}</p>
            <button
              type="button"
              @click="loadTraffic"
              class="mt-4 inline-flex items-center gap-1.5 rounded-lg bg-stone-900 px-4 py-2 text-xs font-bold text-white transition-colors hover:bg-stone-800"
            >
              <i class="bi bi-arrow-clockwise"></i> ลองใหม่
            </button>
          </div>
        </div>

        <!-- Traffic ไม่มีข้อมูล -->
        <div v-else-if="traffic && !hasTrafficData" class="p-5 text-center">
          <i class="bi bi-person-check text-3xl text-stone-300"></i>
          <p class="text-sm text-stone-500 mt-2">ยังไม่มีข้อมูลการใช้งาน — ระบบจะเริ่มเก็บสถิติตั้งแต่วันนี้</p>
        </div>

        <!-- Traffic charts -->
        <div v-else-if="traffic" class="p-5 space-y-4">
          <div class="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div class="bg-stone-50 rounded-xl p-4">
              <p class="font-display text-2xl font-bold text-stone-900 tabular-nums">{{ fmtNum(traffic.total_logins) }}</p>
              <p class="text-xs text-stone-500"><i class="bi bi-box-arrow-in-right mr-1"></i> เข้าสู่ระบบสะสม</p>
            </div>
            <div class="bg-stone-50 rounded-xl p-4">
              <p class="font-display text-2xl font-bold text-stone-900 tabular-nums">{{ fmtNum(traffic.unique_users) }}</p>
              <p class="text-xs text-stone-500"><i class="bi bi-people mr-1"></i> ผู้ใช้ที่ใช้งาน</p>
            </div>
            <div class="bg-stone-50 rounded-xl p-4">
              <p class="font-display text-2xl font-bold text-stone-900 tabular-nums">{{ fmtNum(traffic.failed_logins) }}</p>
              <p class="text-xs text-stone-500"><i class="bi bi-x-circle mr-1"></i> ล็อกอินล้มเหลว</p>
            </div>
          </div>

          <div class="grid lg:grid-cols-3 gap-4">
            <div>
              <h4 class="text-sm font-semibold text-stone-700 mb-2"><i class="bi bi-box-arrow-in-right mr-1 text-stone-600"></i> ผู้เข้าใช้ต่อวัน</h4>
              <div class="h-56"><Line :data="trafficLoginsChart" :options="chartOptions" /></div>
            </div>
            <div>
              <h4 class="text-sm font-semibold text-stone-700 mb-2"><i class="bi bi-lightning-charge mr-1 text-brand"></i> กิจกรรมทั้งระบบต่อวัน</h4>
              <div class="h-56"><Bar :data="trafficActionsChart" :options="chartOptions" /></div>
            </div>
            <div>
              <h4 class="text-sm font-semibold text-stone-700 mb-2"><i class="bi bi-pie-chart mr-1 text-stone-600"></i> สัดส่วนการใช้งาน</h4>
              <div class="h-56"><Doughnut :data="trafficBreakdownChart" :options="chartOptions" /></div>
            </div>
          </div>
        </div>
      </section>

      <!-- ===== ภาพรวมเสริม: แนวโน้ม + สถิติระบบ ===== -->
      <div class="grid lg:grid-cols-3 gap-4">
        <div class="lg:col-span-2 rounded-2xl border border-stone-200 bg-white p-4 sm:p-5">
          <h3 class="font-semibold text-stone-800 mb-3"><i class="bi bi-graph-up mr-1"></i> แนวโน้มเรื่องที่แจ้ง (7 วัน)</h3>
          <div class="h-64"><Line :data="trendChart" :options="chartOptions" /></div>
        </div>

        <div class="rounded-2xl border border-stone-200 bg-white p-4 sm:p-5">
          <h3 class="font-semibold text-stone-800 mb-3"><i class="bi bi-building mr-1"></i> สถิติระบบ</h3>
          <div class="grid grid-cols-2 gap-3">
            <div class="bg-stone-50 rounded-xl p-3">
              <p class="font-display text-2xl font-bold text-stone-900 tabular-nums">{{ fmtNum(data.total_students) }}</p>
              <p class="text-xs text-stone-500"><i class="bi bi-people mr-1"></i> นักเรียนในระบบ</p>
            </div>
            <div class="bg-stone-50 rounded-xl p-3">
              <p class="font-display text-2xl font-bold text-stone-900 tabular-nums">{{ fmtNum(data.total_rooms) }}</p>
              <p class="text-xs text-stone-500"><i class="bi bi-door-closed mr-1"></i> ห้องเรียน</p>
            </div>
          </div>
          <div class="mt-3 pt-3 border-t border-stone-100">
            <div class="flex items-center justify-between">
              <p class="font-display text-2xl font-bold text-stone-900 tabular-nums">{{ fmtNum(data.usage_count) }}</p>
              <span class="text-xs text-stone-400">ครั้ง (ยอดสะสม)</span>
            </div>
            <p class="text-xs text-stone-500 mt-1 mb-2"><i class="bi bi-person-check mr-1"></i> การเข้าใช้งานล่าสุด</p>
            <div v-if="data.recent_logins.length" class="space-y-1.5">
              <div
                v-for="(lg, idx) in data.recent_logins.slice(0, 5)"
                :key="idx"
                class="flex items-center justify-between text-xs"
              >
                <span class="text-stone-600 truncate">{{ lg.actor }}</span>
                <span class="text-stone-400 ml-2 shrink-0">{{ fmtDate(lg.at) }}</span>
              </div>
            </div>
            <p v-else class="text-sm text-stone-400 py-2">ยังไม่มีข้อมูลการเข้าใช้งาน</p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
