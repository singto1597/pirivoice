<script setup lang="ts">
import { ref, onMounted, computed, watch } from 'vue';
import { RouterLink, useRoute, useRouter } from 'vue-router';
import { listIssues } from '@/services/issue';
import { MAIN_CATEGORY_LABELS, subcategoryLabel, LEVEL_LABELS, type Issue } from '@/types/issue';
import { statusShort } from '@/constants/status';
import IssueListToolbar from '@/components/IssueListToolbar.vue';
import PaginationBar from '@/components/PaginationBar.vue';
import AppCard from '@/components/ui/AppCard.vue';
import AppChip from '@/components/ui/AppChip.vue';
import AppButton from '@/components/ui/AppButton.vue';
import AppEmptyState from '@/components/ui/AppEmptyState.vue';
import StatusBadge from '@/components/ui/StatusBadge.vue';
import { fmtRelative } from '@/datetime';

const route = useRoute();
const router = useRouter();

const issues = ref<Issue[]>([]);
const total = ref(0); // จำนวนทั้งหมดที่ตรงเงื่อนไข (จาก envelope)
const isLoading = ref(true);
const error = ref('');
const q = ref('');           // คำค้นหา
const sort = ref<'asc' | 'desc'>('desc'); // ใหม่ไปเก่า (default)
const page = ref(1);
const pageSize = 20;

/**
 * 🔴 **ตัวกรองสถานะอ่านจาก URL ไม่ใช่ `ref` ลอย ๆ**
 *
 * ⭐ เพราะหน้าแรก (การ์ด "สรุปเรื่องของฉัน") ลิงก์มากี่ช่องก็ได้ด้วย `?status=pending`
 *    ⇒ ถ้าหน้านี้ไม่รับค่า จะกดจากหน้าแรกแล้วได้ลิสต์ **ไม่กรอง** ซึ่งดูเหมือนลิงก์พัง
 *    และทำให้ตัวเลขบนหน้าแรกกับการ์ดที่กดเข้ามาไม่ตรงกัน
 *
 * ⚠️ และเมื่อ URL เป็นเจ้าของค่า "กดย้อนกลับ" ของเบราว์เซอร์จะย้อนตัวกรองให้ด้วย
 *    ซึ่งเป็นสิ่งที่ผู้ใช้คาดหวังจากลิสต์ที่กรองได้อยู่แล้ว
 */
const statusFilter = ref(typeof route.query.status === 'string' ? route.query.status : '');

/** ตัวเลือกสถานะทั้งหมด — ป้ายมาจาก `statusShort()` ที่เดียว (ไม่พิมพ์คำซ้ำที่นี่) */
const STATUS_FILTERS = [
  { value: '', label: 'ทั้งหมด' },
  { value: 'pending', label: statusShort('pending') },
  { value: 'in_progress', label: statusShort('in_progress') },
  { value: 'escalated', label: statusShort('escalated') },
  { value: 'resolved', label: statusShort('resolved') },
  { value: 'rejected', label: statusShort('rejected') },
  { value: 'cancelled', label: statusShort('cancelled') },
] as const;

const activeFilters = computed(() => (statusFilter.value ? 1 : 0));
const hasAnyFilter = computed(() => Boolean(statusFilter.value || q.value.trim()));

/**
 * ซ่อนแถบเครื่องมือ (ค้นหา + ชิปสถานะ + เรียง) เมื่อ **ไม่มีอะไรให้กรองเลย**
 * — กล่องค้นหาในลิสต์ว่างคือความรกที่ audit ฟ้อง ("ต้องตีความก่อนใช้")
 *
 * 🔴 แต่ **ห้ามซ่อนเมื่อมีตัวกรองค้างอยู่** — ไม่งั้นผู้ใช้ที่กรองจนได้ 0 ผลลัพธ์
 *    จะไม่เหลือทางล้างตัวกรองในหน้าเลย ⇒ ติดอยู่ในลิสต์ว่างถาวร
 */
const showToolbar = computed(
  () => isLoading.value || issues.value.length > 0 || hasAnyFilter.value,
);

onMounted(load);

// 🔗 URL เปลี่ยน (กดชิป / กดย้อนกลับ / เปิดลิงก์จากหน้าแรก) → กลับหน้า 1 แล้วโหลดใหม่
watch(
  () => route.query.status,
  (s) => {
    statusFilter.value = typeof s === 'string' ? s : '';
    page.value = 1;
    load();
  },
);

async function load() {
  isLoading.value = true;
  error.value = '';
  try {
    const res = await listIssues({
      mine: true,
      status: statusFilter.value || undefined,
      q: q.value.trim() || undefined,
      sort: sort.value,
      limit: pageSize,
      offset: (page.value - 1) * pageSize,
    });
    issues.value = res.items;
    total.value = res.total;
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'โหลดข้อมูลไม่สำเร็จ';
  } finally {
    isLoading.value = false;
  }
}

// search / sort เปลี่ยน → กลับหน้า 1 แล้วโหลด
function onToolbarChange() {
  page.value = 1;
  load();
}

function onPageChange(n: number) {
  page.value = n;
  load();
}

/** ล้างตัวกรองทั้งหมด — ใช้เป็นทางออกของ empty state ตอนกรองจนไม่เหลืออะไร */
function clearFilters() {
  q.value = '';
  // 🔴 `statusFilter` มาจาก URL ⇒ **ต้องล้างที่ URL** ไม่งั้นค่าจะถูก watcher
  //    เขียนทับกลับจาก query เดิมทันทีที่รอบถัดไปทำงาน
  if (route.query.status !== undefined) {
    void router.replace({ query: {} });
  } else {
    page.value = 1;
    load();
  }
}
</script>

<template>
  <div>
    <!--
      🔴 **ไม่ใส่ชื่อหน้าซ้ำ** — `AppHeader` แสดง "เรื่องของฉัน" เป็น `<h1>` อยู่แล้ว
         「วัดบน staging 360dp: ของเดิมโชว์ "เรื่องของฉัน" สองครั้งห่างกัน ~40px」
         ซึ่งเป็นข้อที่ audit ฟ้องตรง ๆ ("ทุกหน้าใส่ป้ายบอกที่ซ้ำ") ⇒ เหลือแค่บรรทัดนำ
         ที่ **เพิ่มข้อมูลจริง** (ชื่อหน้าอย่างเดียวไม่บอกว่าหน้านี้ทำอะไรได้)

      ⚠️ ตัด `<h2>` ออกแล้ว **ไม่เสียลำดับ heading** — `h1` อยู่ที่ `AppHeader`
         ส่วนการ์ดในหน้าใช้ `h3` อยู่แล้ว ⇒ โครงเอกสารยังเป็น h1 → h3 ซึ่งอ่านได้
    -->
    <p class="mb-4 text-sm leading-relaxed text-ink-2">ติดตามสถานะเรื่องที่คุณแจ้ง</p>

    <!-- แถบเครื่องมือ — ซ่อนทั้งแถบเมื่อไม่มีอะไรให้กรอง (ดู `showToolbar`) -->
    <div v-if="showToolbar" class="mb-3 space-y-3">
      <IssueListToolbar
        v-model:q="q"
        v-model:sort="sort"
        :total="total"
        :count="issues.length"
        :active-filters="activeFilters"
        :loading="isLoading"
        @change="onToolbarChange"
      />

      <!-- 🏷️ ชิปสถานะ — เลื่อนแนวนอน ไม่ตัดบรรทัด (ของเดิมเป็น `<select>` ที่ต้องกดเปิดดู) -->
      <div class="chip-row">
        <AppChip
          v-for="f in STATUS_FILTERS"
          :key="f.value"
          :label="f.label"
          :active="statusFilter === f.value"
          :to="{ name: 'my-issues', query: f.value ? { status: f.value } : {} }"
        />
      </div>
    </div>

    <!-- โหลดข้อมูล: skeleton รายการ -->
    <AppCard v-if="isLoading">
      <div class="animate-pulse divide-y divide-line">
        <div v-for="n in 5" :key="n" class="flex items-start gap-3 py-4">
          <div class="h-10 w-10 rounded-full bg-canvas"></div>
          <div class="flex-1 space-y-2 pt-1">
            <div class="h-3 w-1/3 rounded bg-canvas"></div>
            <div class="h-3 w-2/3 rounded bg-canvas"></div>
          </div>
          <div class="h-6 w-16 rounded-full bg-canvas"></div>
        </div>
      </div>
    </AppCard>

    <!-- โหลดไม่สำเร็จ -->
    <AppCard v-else-if="error">
      <AppEmptyState
        icon="bi-wifi-off"
        title="โหลดรายการเรื่องไม่สำเร็จ"
        :description="error"
      >
        <AppButton variant="secondary" size="sm" @click="load">
          <template #icon><i class="bi bi-arrow-clockwise" /></template>
          ลองอีกครั้ง
        </AppButton>
      </AppEmptyState>
    </AppCard>

    <!-- ว่างเพราะ **กรองแล้วไม่เหลือ** — ต้องมีทางล้างตัวกรอง ไม่ใช่บอกแค่ "ไม่พบ" -->
    <AppCard v-else-if="!issues.length && hasAnyFilter">
      <AppEmptyState
        icon="bi-search"
        title="ไม่พบเรื่องในเงื่อนไขที่เลือก"
        description="ลองล้างตัวกรองหรือเปลี่ยนคำค้นหา แล้วดูใหม่"
      >
        <AppButton variant="secondary" size="sm" @click="clearFilters">
          ล้างตัวกรอง
        </AppButton>
      </AppEmptyState>
    </AppCard>

    <!-- ว่างเพราะ **ยังไม่เคยแจ้งเลย** — ต่างจากข้างบนคนละความหมาย ⇒ คนละข้อความ + คนละปุ่ม -->
    <AppCard v-else-if="!issues.length">
      <AppEmptyState
        icon="bi-megaphone"
        title="ยังไม่มีเรื่องที่คุณแจ้ง"
        description="เจอปัญหาหรือมีข้อเสนอแนะ? แจ้งเข้ามาได้เลย ติดตามสถานะได้จากหน้านี้"
      >
        <AppButton :to="{ name: 'new-issue' }">
          <template #icon><i class="bi bi-plus-lg" /></template>
          แจ้งเรื่องแรกของคุณ
        </AppButton>
      </AppEmptyState>
    </AppCard>

    <!-- รายการ -->
    <AppCard v-else :padded="false">
      <TransitionGroup name="list" tag="div" class="divide-y divide-line">
        <RouterLink
          v-for="i in issues"
          :key="i.id"
          :to="{ name: 'issue-detail', params: { id: i.id } }"
          class="flex items-start justify-between gap-3 px-4 py-3.5 transition-colors hover:bg-canvas"
        >
          <div class="flex min-w-0 flex-1 flex-col gap-1.5">
            <!-- หมวด — ของเดิมมี 2 ชิป + ชิปแยกหมวดย่อย ⇒ เหลือบรรทัดเดียว
                 (หมวดหลักเป็น *คำนำหน้า* ของหมวดย่อยที่อ่านออกได้เอง) -->
            <p class="truncate text-[11px] font-medium text-ink-3">
              {{ MAIN_CATEGORY_LABELS[i.main_category] }} ·
              {{ subcategoryLabel(i.main_category, i.category) }}
            </p>
            <h3 class="line-clamp-2 font-semibold leading-snug text-ink-1">{{ i.title }}</h3>
            <p class="flex items-center gap-1.5 text-[11px] font-medium text-ink-3">
              <i class="bi bi-diagram-3"></i> {{ LEVEL_LABELS[i.current_level] }}
              <span aria-hidden="true">•</span>
              {{ fmtRelative(i.created_at) }}
            </p>
          </div>
          <div class="shrink-0 pt-0.5">
            <StatusBadge :status="i.status" />
          </div>
        </RouterLink>
      </TransitionGroup>
    </AppCard>

    <!-- แบ่งหน้า -->
    <PaginationBar
      :total="total"
      :page="page"
      :page-size="pageSize"
      :loading="isLoading"
      @page-change="onPageChange"
    />
  </div>
</template>

<style scoped>
/* list animation */
.list-enter-active,
.list-leave-active {
  transition: all 0.25s ease;
}
.list-enter-from {
  opacity: 0;
  transform: translateY(10px);
}
.list-leave-to {
  opacity: 0;
  transform: translateY(-6px);
}
</style>
