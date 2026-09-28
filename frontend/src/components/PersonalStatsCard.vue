<script setup lang="ts">
// 📊 การ์ดสถิติส่วนตัว (C3) — presentational ล้วน
// ข้อมูลมาจากprops เพื่อให้ทั้ง Profile.vue (ยิง /api/me/stats เอง) และ Home.vue
// (ได้มาจาก /api/home/summary) ใช้การ์ดตัวเดียวกัน ⇒ เลขสองหน้าไม่มีทางแสดงต่างกัน
import { computed } from 'vue'
import type { PersonalStats } from '@/types/me'
import { STAT_ITEMS, statsPeriodLabel, statsPeriodRange } from '@/types/me'

const props = defineProps<{
  stats: PersonalStats | null
  loading?: boolean
  error?: boolean
  /** แบบย่อสำหรับ Home — ตัวเลขเล็กลง ไม่มีคำอธิบายใต้หัวข้อ */
  compact?: boolean
}>()

defineEmits<{ retry: [] }>()

/** มีข้อมูลแล้วหรือยัง — ใช้เลือกแสดง skeleton แทนการ์ดว่าง */
const hasData = computed(() => props.stats !== null)

/** 0 ทุกช่อง = ยังไม่มีข้อมูล ⇒ ชวนให้กำลังใจ ไม่ใช่โชว์ตารางเลขศูนย์เรียงกัน */
const allZero = computed(() => {
  const s = props.stats
  if (!s) return false
  return STAT_ITEMS.every((item) => s[item.key] === 0)
})

const periodLabel = computed(() => statsPeriodLabel(props.stats?.term ?? null))
const periodRange = computed(() => statsPeriodRange(props.stats?.term ?? null))

const cardPadding = computed(() => (props.compact ? 'p-5' : 'p-6 sm:p-8'))
const tilePadding = computed(() => (props.compact ? 'px-3 py-3' : 'px-3 py-4'))
const numberSize = computed(() => (props.compact ? 'text-lg' : 'text-2xl'))
</script>

<template>
  <div class="rounded-2xl border border-stone-200 bg-white" :class="cardPadding">
    <div class="mb-5 flex items-center gap-3">
      <span
        class="flex h-10 w-10 items-center justify-center rounded-xl bg-stone-100 text-stone-500"
      >
        <i class="bi bi-graph-up-arrow"></i>
      </span>
      <div class="min-w-0">
        <h2 class="text-lg font-bold text-stone-900">สถิติของฉัน</h2>
        <p class="mt-0.5 text-xs text-stone-500">
          {{ periodLabel }}
          <span v-if="periodRange" class="text-stone-400">· {{ periodRange }}</span>
        </p>
      </div>
    </div>

    <!-- โหลดไม่สำเร็จ: ไม่ปิดกั้นทั้งหน้า แค่การ์ดนี้ -->
    <div
      v-if="error"
      class="rounded-xl border border-dashed border-stone-300 bg-stone-50 px-4 py-6 text-center"
    >
      <i class="bi bi-cloud-slash mb-2 block text-2xl text-stone-400"></i>
      <p class="text-sm font-semibold text-stone-700">โหลดสถิติไม่ได้</p>
      <button
        type="button"
        @click="$emit('retry')"
        class="mt-3 inline-flex items-center gap-2 rounded-lg border border-stone-300 bg-white px-4 py-2 text-[13px] font-bold text-stone-700 transition-colors hover:bg-stone-100"
      >
        <i class="bi bi-arrow-clockwise"></i> ลองใหม่
      </button>
    </div>

    <div v-else-if="loading && !hasData" class="grid grid-cols-2 gap-2 sm:grid-cols-3" aria-busy="true">
      <div v-for="i in 6" :key="i" class="rounded-xl bg-stone-50 px-3 py-4">
        <div class="mb-2 h-3 w-16 animate-pulse rounded bg-stone-200"></div>
        <div class="h-6 w-10 animate-pulse rounded bg-stone-200"></div>
      </div>
    </div>

    <!-- ยังไม่มีข้อมูลเลย — ให้กำลังใจแทนตารางเลขศูนย์ -->
    <div v-else-if="hasData && allZero" class="rounded-xl bg-stone-50 px-4 py-8 text-center">
      <i class="bi bi-stars mb-2 block text-2xl text-stone-300"></i>
      <p class="text-sm font-semibold text-stone-700">ยังไม่มีสถิติในช่วงนี้</p>
      <p class="mt-1 text-xs text-stone-500">
        แจ้งเรื่องแรกของคุณได้เลย — สถิติจะเริ่มนับตั้งแต่นั้น
      </p>
    </div>

    <div v-else-if="hasData" class="grid grid-cols-2 gap-2 sm:grid-cols-3">
      <!-- หัวข้อเป็น h3 เพราะ h2 ของการ์ดอยู่ข้างบนแล้ว -->
      <div
        v-for="item in STAT_ITEMS"
        :key="item.key"
        class="rounded-xl bg-stone-50"
        :class="tilePadding"
      >
        <p class="flex items-center gap-1.5 text-[11px] font-semibold text-stone-500">
          <i :class="item.icon" class="text-stone-400"></i>
          <span class="truncate">{{ item.label }}</span>
        </p>
        <!-- tabular-nums → หลักตรงกันทุกช่อง ตัวเลขกวาดตาง่าย -->
        <p
          class="mt-1 font-bold tabular-nums text-stone-900"
          :class="numberSize"
        >
          {{ stats?.[item.key] ?? 0 }}
        </p>
      </div>
    </div>
  </div>
</template>
