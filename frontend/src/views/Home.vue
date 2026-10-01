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
import StatusBadge from '@/components/ui/StatusBadge.vue';
import AppEmptyState from '@/components/ui/AppEmptyState.vue';
import AppButton from '@/components/ui/AppButton.vue';
import AppCard from '@/components/ui/AppCard.vue';
import { statusShort } from '@/constants/status';
import { useIdentity } from '@/composables/useIdentity';
import { fmtRelative } from '@/datetime';

const authStore = useAuthStore();
const notificationsStore = useNotificationsStore();
// 🪪 ชื่อ/บทบาท — **ห้ามคำนวณซ้ำในไฟล์นี้** ของเดิมมี `displayName`/`roleLabel`/`roleLine`/
//    `avatarChar` ก๊อปไว้ตรงนี้ทั้งชุด ทั้งที่ `useIdentity` มีครบแล้ว ⇒ แก้ที่เดียวไม่ตรงกัน
const identity = useIdentity();

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

// ⚠️ ไม่มี `displayName` / `roleLabel` / `roleLine` / `avatarChar` ในไฟล์นี้แล้ว — ใช้ `identity`
//    (ของเดิมก๊อป `useIdentity` มาทั้งชุด ⇒ แก้ที่เดียวไม่ตรงกัน และ `avatarChar` ที่นี่
//     ยังเป็นเวอร์ชันเก่าที่มีบั๊กสระนำ ซึ่ง `utils/avatar.ts` แก้ไปแล้ว)

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

/**
 * 3 ช่องตัวเลขที่เหลือของแถว "สรุปเรื่องของฉัน" (ช่องแรก = ทั้งหมด เขียนตรงในเทมเพลต)
 *
 * 🔴 **`status` ต้องตรงกับค่าที่หน้า `my-issues` กรองได้** — ปลายทางคือ
 *    `?status=<ค่า>` ⇒ ถ้าพิมพ์ผิด ผู้ใช้จะกดแล้วได้ลิสต์ว่างที่ดูเหมือน "ไม่มีข้อมูล"
 *    ⚠️ `label` มาจาก `statusShort()` **ไม่พิมพ์เอง** — คำว่า "กำลังทำ" ถูกใช้ทั้งแอป
 *       (ลิสต์/ป้าย/ตัวกรอง) ⇒ ถ้าที่นี่เขียน "กำลังดำเนินการ" จะกลายเป็นคำที่สองของสถานะเดียว
 */
const SUMMARY_TILES = [
  { status: 'pending', label: statusShort('pending'), dot: 'bg-ink-3' },
  { status: 'in_progress', label: statusShort('in_progress'), dot: 'bg-brand' },
  { status: 'resolved', label: statusShort('resolved'), dot: 'bg-ok' },
] as const;

/**
 * สถานะที่มีของแต่ **ไม่ใช่ 3 ช่องหลัก** ⇒ โผล่เป็นชิปเฉพาะเมื่อมีจริง
 *
 * ⚠️ ตัดชิป "กำลังดำเนินการ/ส่งต่อรวม N" ของเดิมออก — มันเป็น *ผลรวมที่คำนวณเอง*
 *    ของ 3 สถานะซึ่งตอนนี้กดดูทีละอันได้จากช่องตัวเลขแล้ว ⇒ ชิปนั้นเป็นตัวเลขที่
 *    ไม่ตรงกับอะไรในระบบเลย (ผู้ใช้เห็น "รวม 7" แล้วกดเข้าไปเจอ 7 พอดีซึ่งบังเอิญ)
 */
const otherStatusChips = computed(() =>
  (
    [
      { status: 'escalated', label: 'ส่งต่อ', icon: 'bi-arrow-up-circle', attention: true },
      { status: 'rejected', label: 'ปฏิเสธ', icon: 'bi-x-circle', attention: false },
      { status: 'cancelled', label: 'ยกเลิก', icon: 'bi-x-octagon', attention: false },
    ] as const
  )
    .map((c) => ({ ...c, count: statusMap.value[c.status] ?? 0 }))
    .filter((c) => c.count > 0),
);

/** ไอคอนตาม "ปลายทางที่ผู้ใช้ขอ" — เดิมเป็น ternary ซ้อน 3 ชั้นในเทมเพลต */
const DESTINATION_ICON: Record<string, string> = {
  vote: 'bi-bar-chart',
  talk: 'bi-chat-dots',
};

// ⚠️ ประกาศไม่ถูกตัดด้วยจำนวน (ห้าม slice) — ดูคอมเมนต์ใน template
// 🎨 ความสำคัญไล่ตาม **ลำดับชั้นของสีแบรนด์** (เข้ม → อ่อน) ไม่ใช่สีใหม่คนละความหมาย
//    `ink-3` สำหรับปกติ = จุดเทาที่ "ไม่เรียกร้องความสนใจ" ซึ่งถูกต้องสำหรับประกาศทั่วไป
const annIconColor: Record<string, string> = {
  urgent: 'bg-brand',
  high: 'bg-brand-strong',
  normal: 'bg-ink-3',
};

// 🎨 ความสำคัญของเรื่อง → ไทล์ไอคอน (ดูเหตุผลในเทมเพลตของ "รอฉันตอบ")
const PRIORITY_TILE: Record<string, string> = {
  urgent: 'bg-brand-strong text-white',
  high: 'bg-brand/10 text-brand',
  normal: 'bg-canvas text-ink-2',
};

/** เพดาน badge — เลข 3 หลักทำให้วงกลมบวมจนชนขอบไอคอน */
function badgeLabel(n: number): string {
  return n > 99 ? '99+' : String(n);
}

/**
 * ไอคอนของ "ปลายทางที่ผู้ใช้ขอ" — คืนค่าเริ่มต้นเมื่อไม่มี/ไม่รู้จัก
 *
 * ⚠️ เขียนเป็นฟังก์ชัน **ไม่ใช่ `DESTINATION_ICON[dest]` ในเทมเพลต** — `requested_destination`
 *    เป็น nullable และโปรเจกต์นี้เปิด `noUncheckedIndexedAccess` ⇒ การ index ด้วยคีย์ที่อาจ
 *    เป็น `undefined` **ไม่ผ่าน type-check** (ไม่ใช่แค่เตือน) — และต่อให้ผ่าน มันจะได้
 *    `undefined` ไปประกอบเป็นคลาส `bi undefined` เงียบ ๆ
 */
function destinationIcon(dest: string | null | undefined): string {
  return (dest && DESTINATION_ICON[dest]) || 'bi-file-earmark-text';
}
</script>

<template>
  <div ref="rootEl" class="space-y-5 pb-2 sm:space-y-6">
    <!-- ============ ทักทาย — บรรทัดเดียว ============
         🔴 **ของเดิมคือการ์ด hero สูง ~280dp** (avatar 64dp + eyebrow "Student Voice" +
            `<h1>` ชื่อผู้ใช้ ขนาด 3xl + บทบาท + วันที่ + ปุ่ม CTA 2 ปุ่ม) ซึ่งกินพื้นที่
            เกือบครึ่งจอบน 360dp เพื่อบอกข้อมูลที่ผู้ใช้รู้อยู่แล้ว (ชื่อตัวเอง)
            ⇒ เหลือ **หนึ่งบรรทัด** ที่ยังบอก "ระบบรู้จักฉัน" โดยไม่ต้องเลื่อนผ่าน

         ⚠️ สิ่งที่ **ตัดออกเพราะซ้ำที่อื่น** ไม่ใช่เพราะไม่มีประโยชน์:
            · avatar → `AppHeader`/sidebar มีอยู่แล้ว (R1 ถอดออกจากหัวแถบโดยเจตนาเดียวกัน)
            · ชื่อ + บทบาทเต็ม → หน้า "เพิ่มเติม" › บัญชี (การ์ดตัวตน) และ sidebar
            · `<h1>` → `AppHeader` แสดงชื่อหน้าแล้ว ⇒ `<h1>` ที่นี่เป็น heading ซ้ำ
            · ปุ่ม "แจ้งเรื่อง" → **FAB `+`** ของ shell (R0) ซึ่งลอยอยู่เหนือจอนี้ตลอด
            · ปุ่ม "ดูเรื่องของฉัน" → แท็บ "เรื่อง" ในแถบล่าง ซึ่งมองเห็นตลอดเวลา
            · ทางลัด 5 ไทล์ → เมนู "เพิ่มเติม" ทั้งชุด (ซ้ำ 100% ⇒ ผิดหลัก "ทางเข้าเดียวต่อปลายทาง")
         ✅ **คงไว้**: คำทักทายตามช่วงเวลา + วันที่ไทย (พ.ศ.) ซึ่งไม่มีที่อื่นในแอปแสดง -->
    <header class="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
      <p class="text-body font-semibold text-ink-1">
        {{ greeting }}, {{ identity.displayName.value }}
      </p>
      <p class="text-[13px] font-medium text-ink-3">{{ dateLabel }}</p>
    </header>

    <!-- ============ โหลดหน้าแรกไม่สำเร็จ ============
         ⚠️ ประกาศ/สรุปเรื่องของฉัน/รอฉันตอบ/โหวต/สถิติ มาจาก **call เดียว**
            ⇒ ล้มพร้อมกันทั้งหมด · แสดงใบเดียวที่บนสุด ไม่กระจาย error ซ้ำ 5 ที่
            (คิวรายงานกับแดชบอร์ดเป็น call แยก ⇒ มี error ของตัวเองอยู่แล้ว) -->
    <AppCard v-if="homeError">
      <AppEmptyState
        icon="bi-wifi-off"
        title="โหลดข้อมูลหน้าแรกไม่สำเร็จ"
        description="ประกาศ สรุปเรื่องของคุณ และสถิติ ยังโหลดไม่ได้"
      >
        <AppButton variant="secondary" size="sm" @click="loadHome">
          <template #icon><i class="bi bi-arrow-clockwise" /></template>
          ลองใหม่
        </AppButton>
      </AppEmptyState>
    </AppCard>

    <!-- ============ รอฉันตอบ (คนรับเรื่อง) ============
         แทนบล็อก "เรื่องที่รอจัดการ" เดิม — เป้าแคบกว่าโดยเจตนา:
         `current_assignee_id = ฉัน` เท่านั้น (เดิมใช้ received=true ซึ่งกว้างกว่ามาก
         รวมเรื่องที่ฉันแค่เป็นผู้แจ้ง/มี countdown ของฉัน ⇒ ไม่ใช่ "รอฉันตอบ")
         ⚠️ ไม่พิมพ์ยอดไว้ข้างลิงก์ "คิวทั้งหมด" — ยอดนี้เป็นเป้าแคบ
            ไม่เท่ากับที่หน้าคิว (`/app/issues/received`) แสดง ⇒ ใส่ไปจะดูเหมือนบั๊ก
            (ขึ้นยอดจริงไว้ในตัวบล็อกแทน) -->
    <AppCard v-if="!homeError && canReceive" :padded="false">
      <div class="flex items-center justify-between gap-3 px-4 pb-1 pt-4">
        <div class="flex items-center gap-3">
          <span class="relative flex h-10 w-10 items-center justify-center rounded-xl bg-brand text-white">
            <i class="bi bi-reply-all text-lg"></i>
            <span
              v-if="unreadCount('issue_received') > 0"
              class="absolute -right-1.5 -top-1.5 flex h-5 min-w-[20px] items-center justify-center rounded-full bg-surface px-1 text-[10px] font-bold text-brand ring-1 ring-line"
            >
              {{ badgeLabel(unreadCount('issue_received')) }}
            </span>
          </span>
          <div>
            <h2 class="text-base font-bold text-ink-1">รอฉันตอบ</h2>
            <p class="text-[13px] font-medium text-ink-3">เรื่องที่ค้างอยู่ที่คุณและยังไม่ปิด</p>
          </div>
        </div>
        <AppButton variant="text" size="sm" :to="{ name: 'received-issues' }">
          คิวทั้งหมด <i class="bi bi-arrow-right"></i>
        </AppButton>
      </div>

      <div class="px-4 pb-4 pt-3">
        <!-- Skeleton -->
        <div v-if="loadingHome" class="space-y-2">
          <div v-for="n in 3" :key="n" class="h-14 animate-pulse rounded-card bg-canvas"></div>
        </div>
        <!-- Empty -->
        <AppEmptyState
          v-else-if="pendingOnMe.length === 0"
          compact
          icon="bi-check2-circle"
          title="ไม่มีเรื่องค้างรอคุณอยู่"
          description="เมื่อมีเรื่องถูกส่งมาถึงระดับคุณ จะขึ้นที่นี่"
        />
        <!-- List -->
        <div v-else class="space-y-1">
          <RouterLink
            v-for="it in pendingOnMe"
            :key="it.id"
            :to="{ name: 'issue-detail', params: { id: it.id } }"
            class="group flex items-center gap-3 rounded-control px-2.5 min-h-11 py-2.5 transition-colors hover:bg-canvas"
          >
            <!-- ⚠️ ความสำคัญสื่อด้วย **น้ำหนักสี** (เข้ม/กลาง/อ่อน) ไม่ใช่สีใหม่ —
                 `urgent` เป็นแดงทึบ `high` เป็นแดงอ่อน `normal` เป็นกลาง ⇒ เรียงลำดับ
                 ได้ด้วยตาก่อนอ่านตัวอักษร และไม่เพิ่มความหมายที่ 7 ให้สีแดง -->
            <span
              class="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl"
              :class="PRIORITY_TILE[it.priority ?? ''] || 'bg-canvas text-ink-2'"
            >
              <i class="bi bi-exclamation-lg"></i>
            </span>
            <span class="min-w-0 flex-1">
              <span class="block truncate text-sm font-semibold text-ink-1 group-hover:text-brand">{{ it.title }}</span>
              <span class="flex items-center gap-1.5 text-[11px] font-medium text-ink-3">
                <i class="bi bi-geo-alt"></i> {{ it.room_name || '—' }}
                <span class="text-ink-3">•</span> {{ fmtRelative(it.created_at) }}
              </span>
            </span>
            <StatusBadge :status="it.status" />
            <i class="bi bi-chevron-right text-xs text-ink-3 transition-transform group-hover:translate-x-0.5"></i>
          </RouterLink>

          <p v-if="pendingRestLabel" class="pt-2 text-center text-[11px] font-semibold text-ink-3">
            {{ pendingRestLabel }} — <RouterLink to="/app/issues/received" class="text-brand hover:underline">ดูในคิวทั้งหมด</RouterLink>
          </p>
        </div>
      </div>
    </AppCard>

    <!-- ============ โหวตที่ยังไม่โหวต (ทุกคน) ============
         ⭐ เป็น "สิ่งที่ทำให้กลับมาเปิดซ้ำ" คู่กับ "รอฉันตอบ"
         แสดงเฉพาะเมื่อ **มีของให้ทำ** (หรือกำลังโหลด) — โหวตครบทุกบอร์ดแล้วบล็อกหายไปเอง
         ไม่ต้องมี empty state ให้รกตา -->
    <AppCard v-if="!homeError && (loadingHome || unvotedBoards.length > 0)" :padded="false">
      <div class="flex items-center justify-between gap-3 px-4 pb-1 pt-4">
        <div class="flex items-center gap-3">
          <span class="flex h-10 w-10 items-center justify-center rounded-xl bg-canvas text-ink-2">
            <i class="bi bi-bar-chart-steps text-lg"></i>
          </span>
          <div>
            <h2 class="text-base font-bold text-ink-1">โหวตที่ยังไม่โหวต</h2>
            <p class="text-[13px] font-medium text-ink-3">บอร์ดที่ยังเปิดอยู่ และคุณยังไม่ได้ออกเสียง</p>
          </div>
        </div>
        <AppButton variant="text" size="sm" :to="{ name: 'boards' }">
          บอร์ด <i class="bi bi-arrow-right"></i>
        </AppButton>
      </div>

      <div class="px-4 pb-4 pt-3">
        <div v-if="loadingHome" class="space-y-2">
          <div v-for="n in 2" :key="n" class="h-14 animate-pulse rounded-card bg-canvas"></div>
        </div>
        <div v-else class="space-y-1">
          <RouterLink
            v-for="b in unvotedBoards"
            :key="b.id"
            :to="{ name: 'board-detail', params: { id: b.id } }"
            class="group flex items-center gap-3 rounded-control px-2.5 min-h-11 py-2.5 transition-colors hover:bg-canvas"
          >
            <span class="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-brand/10 text-brand">
              <i class="bi bi-hand-thumbs-up"></i>
            </span>
            <span class="min-w-0 flex-1">
              <span class="block truncate text-sm font-semibold text-ink-1 group-hover:text-brand">{{ b.title }}</span>
              <span class="flex items-center gap-1.5 text-[11px] font-medium text-ink-3">
                <i class="bi bi-people"></i> {{ voteCountLabel(b.vote_count) }}
                <span class="text-ink-3">•</span> {{ fmtRelative(b.created_at) }}
              </span>
            </span>
            <span class="hidden shrink-0 rounded-full bg-brand/10 px-2.5 py-1 text-[11px] font-bold text-brand sm:inline">
              ไปโหวต
            </span>
            <i class="bi bi-chevron-right text-xs text-ink-3 transition-transform group-hover:translate-x-0.5"></i>
          </RouterLink>

          <p v-if="unvotedRestLabel" class="pt-2 text-center text-[11px] font-semibold text-ink-3">
            {{ unvotedRestLabel }} — <RouterLink to="/app/boards" class="text-brand hover:underline">ดูในบอร์ด</RouterLink>
          </p>
        </div>
      </div>
    </AppCard>

    <!-- ============ ⏳ กิจกรรมใกล้ปิดรับ (4.5) ============
         ⭐ แสดงเฉพาะเมื่อ **มีของ** (หรือกำลังโหลด) — กติกาเดียวกับบล็อก "โหวตที่ยังไม่โหวต"
         ข้างบน ⇒ ไม่มี empty state ให้รกตา · การที่บล็อกโผล่ขึ้นมาเอง *คือ* การเตือน

         ⚠️ `closes_at` มาจาก backend = min(วันจัด, กำหนดปิดรับ) — **ห้าม** เอา
            `registration_deadline` มาคิดเองที่นี่ (กิจกรรมที่ไม่ตั้งกำหนดจะปิดที่วันจัด
            ซึ่งเป็นกลุ่มที่พลาดมากที่สุด เพราะไม่มี deadline ให้เห็น)
         ⚠️ แถวที่ฉันสมัครแล้ว **ยังต้องอยู่ในบล็อกนี้** — "สมัครแล้ว" ≠ "เรียบร้อย"
            สิ่งที่ต่างคือปุ่ม (ป้าย "สมัครแล้ว" แทน "ดูรายละเอียด") ไม่ใช่การมีอยู่ของแถว -->
    <AppCard
      v-if="!homeError && (loadingHome || closingSoon.length > 0)"
      :padded="false"
      data-testid="closing-soon-card"
    >
      <div class="flex items-center justify-between gap-3 px-4 pb-1 pt-4">
        <div class="flex items-center gap-3">
          <span class="flex h-10 w-10 items-center justify-center rounded-xl bg-warn-soft text-warn">
            <i class="bi bi-hourglass-split text-lg"></i>
          </span>
          <div>
            <h2 class="text-base font-bold text-ink-1">กิจกรรมใกล้ปิดรับ</h2>
            <!-- ⚠️ ใช้ "ยังไม่ปิดรับ" ไม่ใช่ "ยังสมัครได้อยู่" — กิจกรรมที่เต็มแล้วก็อยู่ในบล็อกนี้
                 (สมัครได้แต่จะได้คิวสำรอง) ⇒ คำเดิมจะขัดกับป้าย "เต็มแล้ว" ในแถวเดียวกัน -->
            <p class="text-[13px] font-medium text-ink-3">ยังไม่ปิดรับ — เหลือเวลาอีกไม่มาก</p>
          </div>
        </div>
        <AppButton variant="text" size="sm" :to="{ name: 'events' }">
          ทั้งหมด <i class="bi bi-arrow-right"></i>
        </AppButton>
      </div>

      <div class="px-4 pb-4 pt-3">
        <div v-if="loadingHome" class="space-y-2">
          <div v-for="n in 2" :key="n" class="h-14 animate-pulse rounded-card bg-canvas"></div>
        </div>
        <div v-else class="space-y-1">
          <RouterLink
            v-for="ev in closingSoon"
            :key="ev.id"
            :to="{ name: 'event-detail', params: { id: ev.id } }"
            class="group flex items-center gap-3 rounded-control px-2.5 min-h-11 py-2.5 transition-colors hover:bg-canvas"
          >
            <span class="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-warn-soft text-warn">
              <i class="bi bi-calendar-event"></i>
            </span>
            <span class="min-w-0 flex-1">
              <span class="block truncate text-sm font-semibold text-ink-1 group-hover:text-brand">{{ ev.title }}</span>
              <span class="flex flex-wrap items-center gap-1.5 text-[11px] font-medium text-ink-3">
                <!-- ป้ายเวลาปิดรับ — หัวใจของการ์ดนี้ จึงใช้สี warn ให้ต่างจากบรรทัดอื่น -->
                <span class="font-bold text-warn">{{ closingLabel(ev.closes_at) }}</span>
                <template v-if="ev.location">
                  <span class="text-ink-3">•</span>
                  <span class="inline-flex items-center gap-1"><i class="bi bi-geo-alt"></i> {{ ev.location }}</span>
                </template>
                <!-- `seatsWarning` คืน null เมื่อ **ไม่จำกัดจำนวน หรือยังเหลือเยอะ** ⇒ ไม่มีป้ายโผล่
                     (⚠️ ไม่ใช่ `seatsLabel` — ตัวนั้นตอบ "เหลือกี่ที่" ซึ่งจะขึ้น "ว่างอีก 40 ที่"
                      ที่ไม่ได้บอกอะไร และทำให้ป้ายที่มีอยู่จริงไม่มีความหมาย) -->
                <template v-if="seatsWarning(ev.seats_remaining)">
                  <span class="text-ink-3">•</span>
                  <span class="font-semibold text-ink-2">{{ seatsWarning(ev.seats_remaining) }}</span>
                </template>
              </span>
            </span>
            <!-- `registrationChip` คืน null = ยังไม่สมัคร ⇒ แสดงป้ายเชิญชวนให้กด -->
            <span
              v-if="registrationChip(ev.my_registration_status)"
              class="shrink-0 rounded-full bg-ok-soft px-2.5 py-1 text-[11px] font-bold text-ok"
            >
              {{ registrationChip(ev.my_registration_status) }}
            </span>
            <span
              v-else
              class="hidden shrink-0 rounded-full bg-brand/10 px-2.5 py-1 text-[11px] font-bold text-brand sm:inline"
            >
              ดูรายละเอียด
            </span>
            <i class="bi bi-chevron-right text-xs text-ink-3 transition-transform group-hover:translate-x-0.5"></i>
          </RouterLink>

          <p v-if="closingSoonRestLabel" class="pt-2 text-center text-[11px] font-semibold text-ink-3">
            {{ closingSoonRestLabel }} — <RouterLink to="/app/events" class="text-brand hover:underline">ดูกิจกรรมทั้งหมด</RouterLink>
          </p>
        </div>
      </div>
    </AppCard>

    <!-- ============ ประกาศโรงเรียน ============
         ⭐ โชว์ **ทั้งหมด** ที่ยังใช้งานอยู่ — ไม่มี slice()/เพดานจำนวนโดยเจตนา
            (เจ้าของระบบสั่งว่า "ไม่ต้องกำหนดว่าให้โชว์กี่อัน ให้โชว์ทั้งหมดที่ยังไม่ถอดออก")
            backend กรอง `deleted_at IS NULL AND retired_at IS NULL` มาให้แล้ว
            ⇒ ที่นี่ไม่ต้องกรอง/ตัดอะไรอีก และ **ห้าม slice** แม้จะอยากให้สั้นลง
            (endpoint/ข้อมูลชุดเดียวกันนี้ถูกใช้โดย Landing.vue ด้วย)

         ⚠️ อยู่ **หลัง** บล็อกที่ต้องลงมือทำ (รอฉันตอบ/โหวต/กิจกรรมใกล้ปิดรับ) โดยเจตนา —
            ประกาศเป็น *ข้อมูลที่ต้องอ่าน* ไม่ใช่ *งานที่ต้องทำ* ⇒ ถ้าอยู่บนสุด มันจะดัน
            ของที่ต้องกดให้ตกจอบน 360dp ซึ่งเป็นอาการที่ audit ฟ้องว่า "ต้องตีความก่อนใช้" -->
    <AppCard v-if="!homeError && announcements.length > 0" :padded="false">
      <div class="flex items-start gap-3 px-4 py-3.5">
        <span class="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-canvas text-ink-2">
          <i class="bi bi-megaphone"></i>
        </span>
        <div class="min-w-0 space-y-2">
          <p class="text-xs font-bold text-ink-2">ประกาศโรงเรียน</p>
          <div v-for="a in announcements" :key="a.id" class="flex items-start gap-2.5">
            <span class="mt-1.5 h-2 w-2 shrink-0 rounded-full" :class="annIconColor[a.priority] || 'bg-ink-3'"></span>
            <p class="text-sm font-medium leading-relaxed text-ink-1">{{ a.message }}</p>
          </div>
        </div>
      </div>
    </AppCard>

    <!-- ============ My-issue summary (ทุกคน) ============
         ⚠️ อยู่ **หลัง** บล็อกที่ต้องลงมือทำโดยเจตนา (ของเดิมอยู่อันดับ 3 รองจาก
            การ์ดต้อนรับกับทางลัด ⇒ ต้องเลื่อนผ่านสถิติของตัวเองก่อนถึง "รอฉันตอบ"
            ซึ่งเป็นสิ่งเดียวในหน้านี้ที่ต้อง *ทำ*) -->
    <AppCard v-if="!homeError" :padded="false">
      <!-- Header -->
      <div class="flex items-center justify-between gap-3 px-4 pb-1 pt-4">
        <div class="flex items-center gap-3">
          <span class="flex h-10 w-10 items-center justify-center rounded-xl bg-canvas text-ink-2">
            <i class="bi bi-stack text-lg"></i>
          </span>
          <div>
            <h2 class="text-base font-bold text-ink-1">สรุปเรื่องของฉัน</h2>
            <p class="text-[13px] font-medium text-ink-3">ติดตามสถานะเรื่องที่คุณแจ้งไว้</p>
          </div>
        </div>
        <!-- ⚠️ ของเดิมมีลิงก์นี้ **สองอัน** (`sm:flex` + `sm:hidden`) เพื่อย้ายตำแหน่ง
             ตามขนาดจอ ⇒ DOM มีปุ่มเดียวกันสองที่ และต้องแก้ให้ตรงกันทุกครั้ง
             ⇒ เหลืออันเดียวที่ใช้ได้ทุกขนาด -->
        <AppButton variant="text" size="sm" :to="{ name: 'my-issues' }">
          ดูทั้งหมด <i class="bi bi-arrow-right"></i>
        </AppButton>
      </div>

      <!-- Skeleton -->
      <div v-if="loadingHome" class="grid grid-cols-4 gap-1 px-4 pb-5 pt-3">
        <div v-for="n in 4" :key="n" class="space-y-1.5 rounded-control px-2 py-2">
          <div class="h-6 animate-pulse rounded-lg bg-canvas"></div>
          <div class="h-3 w-10 animate-pulse rounded bg-canvas"></div>
        </div>
      </div>

      <!-- Empty: ยังไม่เคยแจ้ง -->
      <AppEmptyState
        v-else-if="summary && summary.total_issues === 0"
        icon="bi-megaphone"
        title="ยังไม่เคยแจ้งเรื่องเลย"
        description="เจอปัญหาหรือมีข้อเสนอแนะ? แจ้งเข้ามาได้เลย หัวหน้าห้องและสภานักเรียนจะช่วยติดตามให้"
      >
        <AppButton :to="{ name: 'new-issue' }">
          <template #icon><i class="bi bi-plus-lg" /></template>
          แจ้งเรื่องแรกเลย
        </AppButton>
      </AppEmptyState>

      <!-- Loaded with data -->
      <div v-else-if="summary" class="px-4 pb-4 pt-3">
        <!-- ตัวเลขหลัก — **ไม่มีกรอบ** และแตะได้ทุกช่อง
             🔴 ของเดิมเป็นตาราง `gap-px` บนพื้นเทา + เส้นรอบ ⇒ เส้นและช่องว่างของกรอบ
                กินพื้นที่พอ ๆ กับตัวเลข และบอกใบ้ว่า "อ่านอย่างเดียว" ทั้งที่ผู้ใช้
                อยากกดดูรายการที่กรองแล้วต่อทันที (มี `?status=` รองรับอยู่แล้ว) -->
        <div class="grid grid-cols-4 gap-1">
          <RouterLink
            :to="{ name: 'my-issues' }"
            class="inline-flex items-center rounded-control px-2 min-h-11 py-2 transition-colors hover:bg-canvas focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
          >
            <p
              class="font-display text-xl font-bold leading-none tabular-nums text-ink-1 sm:text-2xl"
              :data-count="summary.total_issues"
            >0</p>
            <p class="mt-1.5 truncate text-[11px] font-semibold text-ink-3">ทั้งหมด</p>
          </RouterLink>

          <RouterLink
            v-for="tile in SUMMARY_TILES"
            :key="tile.status"
            :to="{ name: 'my-issues', query: { status: tile.status } }"
            class="inline-flex items-center rounded-control px-2 min-h-11 py-2 transition-colors hover:bg-canvas focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
          >
            <p
              class="font-display text-xl font-bold leading-none tabular-nums text-ink-1 sm:text-2xl"
              :data-count="statusMap[tile.status] ?? 0"
            >0</p>
            <p class="mt-1.5 flex items-center gap-1 truncate text-[11px] font-semibold text-ink-3">
              <!-- จุดสีเป็น *ตัวช่วยจำ* ไม่ใช่ตัวสื่อความหมาย — ข้อความข้าง ๆ คือตัวจริง
                   (ผู้ใช้ที่ตาบอดสีอ่าน "รอรับ" ได้เหมือนกัน) -->
              <span class="h-1.5 w-1.5 shrink-0 rounded-full" :class="tile.dot" aria-hidden="true"></span>
              {{ tile.label }}
            </p>
          </RouterLink>
        </div>

        <!-- สถานะที่เหลือ — โผล่ **เฉพาะเมื่อมีของ** ไม่ใช่แถบที่โชว์ตลอด
             (ทั้งสามอย่างนี้เป็นสถานะที่ผู้ใช้ส่วนใหญ่มี 0 ⇒ การที่มันโผล่มาเองคือการเตือน) -->
        <div v-if="otherStatusChips.length > 0" class="mt-3 flex flex-wrap items-center gap-2">
          <RouterLink
            v-for="c in otherStatusChips"
            :key="c.status"
            :to="{ name: 'my-issues', query: { status: c.status } }"
            class="inline-flex items-center gap-1.5 rounded-full px-3 min-h-11 py-1.5 text-[11px] font-bold transition-colors"
            :class="
              c.attention
                ? 'bg-brand-tint text-brand hover:bg-brand/15'
                : 'bg-canvas text-ink-2 hover:bg-line'
            "
          >
            <i :class="['bi', c.icon, 'text-xs']"></i> {{ c.label }} {{ c.count }}
          </RouterLink>
        </div>

        <!-- ล่าสุด 2 เรื่อง -->
        <div v-if="summary.recent.length > 0" class="mt-4 border-t border-line pt-4">
          <p class="mb-2 flex items-center gap-1.5 text-[11px] font-bold text-ink-2">
            <i class="bi bi-clock-history"></i> เรื่องล่าสุด
          </p>
          <div class="space-y-1">
            <RouterLink
              v-for="it in summary.recent.slice(0, 2)"
              :key="it.id"
              :to="{ name: 'issue-detail', params: { id: it.id } }"
              class="group flex items-center gap-3 rounded-control px-2.5 min-h-11 py-2.5 transition-colors hover:bg-canvas"
            >
              <span class="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-canvas text-ink-2">
                <i :class="['bi', destinationIcon(it.requested_destination)]"></i>
              </span>
              <span class="min-w-0 flex-1">
                <span class="block truncate text-sm font-semibold text-ink-1 group-hover:text-brand">{{ it.title }}</span>
                <span class="text-[11px] font-medium text-ink-3">{{ fmtRelative(it.created_at) }}</span>
              </span>
              <StatusBadge :status="it.status" />
            </RouterLink>
          </div>
        </div>
      </div>
    </AppCard>

    <!-- ============ สถิติของฉัน (C3) ============
         ใช้การ์ดตัวเดียวกับ Profile.vue — ข้อมูลมาจาก home summary ไม่ต้องยิงซ้ำ
         ⚠️ ไม่ต้องใส่หัวข้อเอง การ์ดมีหัวข้อ + ช่วงภาค (พ.ศ.) ในตัวแล้ว -->
    <PersonalStatsCard
      v-if="!homeError"
      :stats="stats"
      :loading="loadingHome"
      compact
    />

    <!-- ============ คิวรายงาน (สภา/แอดมิน) ============ -->
    <AppCard v-if="isCouncil" :padded="false">
      <div class="flex items-center justify-between gap-3 px-4 pb-1 pt-4">
        <div class="flex items-center gap-3">
          <span class="flex h-10 w-10 items-center justify-center rounded-xl bg-canvas text-ink-2">
            <i class="bi bi-flag-fill text-lg"></i>
          </span>
          <div>
            <h2 class="text-base font-bold text-ink-1">คิวจัดการรายงาน</h2>
            <p class="text-[13px] font-medium text-ink-3">คอมเมนต์ที่ถูกรายงานว่าน่าไม่เหมาะสม</p>
          </div>
        </div>
        <AppButton variant="text" size="sm" :to="{ name: 'board-reports' }">
          ไปจัดการ <i class="bi bi-arrow-right"></i>
        </AppButton>
      </div>

      <div class="px-4 pb-4 pt-3">
        <div v-if="loadingReports" class="space-y-2">
          <div v-for="n in 3" :key="n" class="h-12 animate-pulse rounded-card bg-canvas"></div>
        </div>
        <AppEmptyState
          v-else-if="reportsError"
          compact
          icon="bi-wifi-off"
          title="โหลดคิวรายงานไม่สำเร็จ"
          description="คิวคอมเมนต์ที่ถูกรายงานยังโหลดไม่ได้"
        >
          <AppButton variant="secondary" size="sm" @click="loadReports">
            <template #icon><i class="bi bi-arrow-clockwise" /></template>
            ลองใหม่
          </AppButton>
        </AppEmptyState>
        <AppEmptyState
          v-else-if="reports.length === 0"
          compact
          icon="bi-check2-circle"
          title="คิวรายงานว่าง"
          description="ไม่มีคอมเมนต์ที่รอรีวิว"
        />
        <div v-else class="space-y-1">
          <RouterLink
            v-for="r in reports.slice(0, 3)"
            :key="r.id"
            :to="{ name: 'board-reports' }"
            class="group flex items-start gap-3 rounded-control px-2.5 min-h-11 py-2.5 transition-colors hover:bg-canvas"
          >
            <span class="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-canvas text-ink-2">
              <i class="bi bi-flag text-sm"></i>
            </span>
            <span class="min-w-0 flex-1">
              <span class="block truncate text-sm font-semibold text-ink-1 group-hover:text-brand">{{ r.board_title }}</span>
              <span class="mt-0.5 block truncate text-[11px] text-ink-3">“{{ r.comment_body }}”</span>
            </span>
            <span v-if="reportsTotal > 3" class="shrink-0 rounded-full bg-brand px-2 py-0.5 text-[11px] font-bold text-white">+{{ reportsTotal - 3 }}</span>
          </RouterLink>
        </div>
      </div>
    </AppCard>

    <!-- ============ สถิติ (VIEW_DASHBOARD) ============ -->
    <AppCard v-if="canDashboard" :padded="false">
      <div class="px-4 py-4">
        <div class="flex items-center justify-between gap-3">
          <div class="flex items-center gap-3">
            <span class="flex h-10 w-10 items-center justify-center rounded-xl bg-brand text-white">
              <i class="bi bi-graph-up text-lg"></i>
            </span>
            <div>
              <h2 class="text-base font-bold text-ink-1">ภาพรวม {{
                dash?.scope_label ? `ระดับ ${dash.scope_label}` : 'ทั้งโรงเรียน'
              }}</h2>
              <p class="text-[13px] font-medium text-ink-3">จากแดชบอร์ด — ข้อมูลอัปเดตเรียลไทม์</p>
            </div>
          </div>
          <AppButton variant="text" size="sm" :to="{ name: 'dashboard' }" class="hidden sm:inline-flex">
            เปิดแดชบอร์ด <i class="bi bi-arrow-right"></i>
          </AppButton>
        </div>

        <!-- ⚠️ ตารางแบบ `gap-px` + พื้นเทา (เส้นตารางปลอม) ของเดิมถูกถอดออก —
             มันคือ "เส้นทุกช่อง" ซึ่งเป็นอาการเดียวกับที่ audit ฟ้องเรื่องความรก
             ⇒ ใช้ช่องว่าง + ตัวเลขขนาดใหญ่สร้างลำดับแทน (แบบเดียวกับสรุปเรื่องของฉัน) -->
        <div v-if="loadingDash" class="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
          <div v-for="n in 4" :key="n" class="rounded-control bg-canvas p-4">
            <div class="h-10 animate-pulse rounded-xl bg-line"></div>
          </div>
        </div>
        <AppEmptyState
          v-else-if="dashError"
          compact
          icon="bi-wifi-off"
          title="โหลดสถิติภาพรวมไม่สำเร็จ"
          description="ตัวเลขสรุปทั้งโรงเรียนยังโหลดไม่ได้"
        >
          <AppButton variant="secondary" size="sm" @click="loadDash">
            <template #icon><i class="bi bi-arrow-clockwise" /></template>
            ลองใหม่
          </AppButton>
        </AppEmptyState>
        <div v-else-if="dash" class="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
          <div class="rounded-control bg-canvas p-3.5">
            <p class="text-[11px] font-semibold text-ink-3">เรื่องทั้งหมด</p>
            <p class="mt-1 font-display text-2xl font-bold leading-none text-ink-1">{{ dash.total_issues }}</p>
          </div>
          <div class="rounded-control bg-brand-tint p-3.5">
            <p class="text-[11px] font-semibold text-brand">ค้าง/เลยกำหนด</p>
            <p class="mt-1 font-display text-2xl font-bold leading-none text-brand-strong">{{ dash.overdue }}</p>
          </div>
          <div class="rounded-control bg-canvas p-3.5">
            <p class="text-[11px] font-semibold text-ink-3">กำลังดำเนินการ</p>
            <p class="mt-1 font-display text-2xl font-bold leading-none text-ink-1">{{ dash.in_progress }}</p>
          </div>
          <div class="rounded-control bg-canvas p-3.5">
            <p class="text-[11px] font-semibold text-ink-3">เสร็จแล้ว</p>
            <p class="mt-1 font-display text-2xl font-bold leading-none text-ink-1">{{ dash.resolved }}</p>
          </div>
        </div>
      </div>
    </AppCard>

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
