<script setup lang="ts">
import { ref, onMounted, computed } from 'vue';
import { RouterLink } from 'vue-router';
import { listIssues } from '@/services/issue';
import { MAIN_CATEGORY_LABELS, subcategoryLabel, STATUS_LABELS, LEVEL_LABELS, type Issue } from '@/types/issue';
import { STATUS_BADGE } from '@/constants/status';
import IssueListToolbar from '@/components/IssueListToolbar.vue';
import PaginationBar from '@/components/PaginationBar.vue';

const issues = ref<Issue[]>([]);
const total = ref(0); // จำนวนทั้งหมดที่ตรงเงื่อนไข (จาก envelope)
const isLoading = ref(true);
const error = ref('');
const q = ref('');           // คำค้นหา
const sort = ref<'asc' | 'desc'>('desc'); // ใหม่ไปเก่า (default)
const page = ref(1);
const pageSize = 20;
const statusFilter = ref('');   // '' = ทุกสถานะ

const activeFilters = computed(() => (statusFilter.value ? 1 : 0));

onMounted(load);

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

// search / sort / filter เปลี่ยน → กลับหน้า 1 แล้วโหลด
function onToolbarChange() {
  page.value = 1;
  load();
}

function onPageChange(n: number) {
  page.value = n;
  load();
}
</script>

<template>
  <div>
    <!-- Editorial page header -->
    <div class="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <p class="mb-2 flex items-center gap-2 text-[11px] font-bold uppercase tracking-widest text-brand">
          <i class="bi bi-file-earmark-text text-[13px]"></i> My Reports
        </p>
        <h1 class="text-2xl sm:text-3xl font-bold tracking-tight text-stone-900 leading-tight">เรื่องของฉัน</h1>
        <p class="mt-2 text-sm text-stone-500">ติดตามสถานะเรื่องที่คุณแจ้ง</p>
      </div>
      <RouterLink to="/app/issues/new" class="btn-gradient text-sm shrink-0">
        <i class="bi bi-plus-lg"></i> แจ้งเรื่องใหม่
      </RouterLink>
    </div>

    <!-- Toolbar: ค้นหา + filter (สถานะ) + เรียงลำดับ + จำนวน -->
    <IssueListToolbar
      v-model:q="q"
      v-model:sort="sort"
      :total="total"
      :count="issues.length"
      :active-filters="activeFilters"
      :loading="isLoading"
      @change="onToolbarChange"
    >
      <template #filters>
        <div>
          <label class="block text-xs font-semibold text-stone-500 mb-1.5">สถานะ</label>
          <select v-model="statusFilter" @change="onToolbarChange"
            class="w-full px-3 py-2 border border-stone-300 rounded-xl text-sm bg-white">
            <option value="">ทุกสถานะ</option>
            <option value="pending">รอรับเรื่อง</option>
            <option value="in_progress">กำลังดำเนินการ</option>
            <option value="escalated">ส่งต่อระดับบน</option>
            <option value="resolved">แก้ไขเสร็จ</option>
            <option value="cancelled">ถูกยกเลิก</option>
            <option value="rejected">ถูกปัดตก</option>
          </select>
        </div>
      </template>
    </IssueListToolbar>

    <!-- โหลดข้อมูล: skeleton รายการ -->
    <div v-if="isLoading" class="animate-pulse rounded-2xl border border-stone-200 bg-white p-5">
      <div class="divide-y divide-stone-100">
        <div v-for="n in 5" :key="n" class="flex items-start gap-3 py-4">
          <div class="h-10 w-10 rounded-full bg-stone-100"></div>
          <div class="flex-1 space-y-2 pt-1">
            <div class="h-3 w-1/3 rounded bg-stone-100"></div>
            <div class="h-3 w-2/3 rounded bg-stone-100"></div>
          </div>
          <div class="h-6 w-16 rounded-full bg-stone-100"></div>
        </div>
      </div>
    </div>

    <!-- โหลดไม่สำเร็จ: inline error + retry -->
    <div
      v-else-if="error"
      class="flex flex-col items-center justify-center rounded-2xl border-2 border-dashed border-stone-200 py-20 text-center"
    >
      <i class="bi bi-wifi-off text-3xl text-stone-400 mb-3"></i>
      <p class="text-stone-600">{{ error }}</p>
      <button
        type="button"
        class="mt-4 rounded-lg bg-brand px-5 py-2 text-[13px] font-bold text-white hover:bg-brand-strong"
        @click="load"
      >
        ลองอีกครั้ง
      </button>
    </div>

    <!-- Empty state -->
    <div
      v-else-if="!issues.length"
      class="flex flex-col items-center justify-center rounded-2xl border-2 border-dashed border-stone-200 bg-white py-16 px-6 text-center"
    >
      <div class="text-4xl mb-2 text-stone-300"><i class="bi bi-inbox"></i></div>
      <p class="text-stone-600">ยังไม่มีเรื่องที่คุณแจ้ง</p>
      <RouterLink to="/app/issues/new" class="inline-block mt-3 text-brand hover:underline font-medium">แจ้งเรื่องแรกของคุณ <i class="bi bi-arrow-right"></i></RouterLink>
    </div>

    <!-- Ledger-style list -->
    <TransitionGroup
      v-else
      name="list"
      tag="div"
      class="rounded-2xl border border-stone-200 overflow-hidden bg-white divide-y divide-stone-200"
    >
      <RouterLink
        v-for="i in issues"
        :key="i.id"
        :to="{ name: 'issue-detail', params: { id: i.id } }"
        class="flex items-start justify-between gap-3 px-5 py-4 hover:bg-stone-50 transition block"
      >
        <div class="flex-1 min-w-0">
          <div class="flex gap-2 mb-1.5">
            <span class="px-2 py-0.5 bg-stone-100 text-stone-600 text-xs rounded-full">{{ MAIN_CATEGORY_LABELS[i.main_category] }}</span>
            <span class="px-2 py-0.5 bg-stone-100 text-stone-600 text-xs rounded-full">{{ subcategoryLabel(i.main_category, i.category) }}</span>
          </div>
          <h3 class="font-semibold text-stone-900 truncate">{{ i.title }}</h3>
          <p class="text-xs text-stone-500 mt-1">ตอนนี้อยู่ที่: {{ LEVEL_LABELS[i.current_level] }}</p>
        </div>
        <div class="text-right shrink-0">
          <span
            class="px-2.5 py-1 text-xs font-medium rounded-full whitespace-nowrap"
            :class="STATUS_BADGE[i.status] || 'bg-stone-100 text-stone-500'"
          >
            {{ STATUS_LABELS[i.status] }}
          </span>
        </div>
      </RouterLink>
    </TransitionGroup>

    <!-- แบ่งหน้า -->
    <PaginationBar :total="total" :page="page" :page-size="pageSize" :loading="isLoading" @page-change="onPageChange" />
  </div>
</template>

<style scoped>
/* list animation */
.list-enter-active, .list-leave-active { transition: all 0.25s ease; }
.list-enter-from { opacity: 0; transform: translateY(10px); }
.list-leave-to { opacity: 0; transform: translateY(-6px); }
</style>
