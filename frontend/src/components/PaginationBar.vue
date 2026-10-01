<script setup lang="ts">
import { computed } from 'vue'

/**
 * แถบแบ่งหน้า — แสดงเมื่อมีมากกว่า 1 หน้า
 * เลขหน้าละเอียดรอบหน้าปัจจุบัน (cur-1, cur, cur+1) + หน้าแรก/หน้าสุดท้าย, คั่นด้วย …
 */
const props = defineProps<{
  total: number
  page: number
  pageSize: number
  loading?: boolean
}>()

const emit = defineEmits<{ pageChange: [page: number] }>()

const pages = computed(() => Math.max(1, Math.ceil(props.total / props.pageSize)))

const items = computed<Array<number | 'ellipsis'>>(() => {
  const p = pages.value
  const cur = props.page
  const candidates = [1, p, cur - 1, cur, cur + 1]
  const sorted = [...new Set(candidates)].filter((n) => n >= 1 && n <= p).sort((a, b) => a - b)
  const out: Array<number | 'ellipsis'> = []
  let prev = 0
  for (const n of sorted) {
    if (n - prev > 1) out.push('ellipsis')
    out.push(n)
    prev = n
  }
  return out
})

function go(n: number) {
  if (n >= 1 && n <= pages.value && n !== props.page) emit('pageChange', n)
}
</script>

<template>
  <nav v-if="pages > 1" class="flex items-center justify-center gap-1.5 mt-6" aria-label="แบ่งหน้า">
    <button
      type="button"
      :disabled="page <= 1 || loading"
      @click="go(page - 1)"
      aria-label="หน้าก่อนหน้า"
      class="flex h-11 w-11 items-center justify-center rounded-xl border text-sm disabled:opacity-40 disabled:cursor-not-allowed"
      :class="page > 1 ? 'border-stone-300 text-stone-600 hover:bg-stone-50' : 'border-stone-100 text-stone-300'"
    >
      <i class="bi bi-chevron-left"></i>
    </button>

    <template v-for="(it, i) in items" :key="`${it}-${i}`">
      <span v-if="it === 'ellipsis'" class="px-0.5 text-ink-3">…</span>
      <button
        v-else
        type="button"
        :disabled="loading"
        @click="go(it)"
        class="flex h-11 min-w-11 items-center justify-center rounded-xl px-2 text-sm font-medium transition"
        :class="
          it === page
            ? 'bg-brand text-white'
            : 'border border-stone-200 text-stone-600 hover:border-brand hover:text-brand'
        "
      >
        {{ it }}
      </button>
    </template>

    <button
      type="button"
      :disabled="page >= pages || loading"
      @click="go(page + 1)"
      aria-label="หน้าถัดไป"
      class="flex h-11 w-11 items-center justify-center rounded-xl border text-sm disabled:opacity-40 disabled:cursor-not-allowed"
      :class="page < pages ? 'border-stone-300 text-stone-600 hover:bg-stone-50' : 'border-stone-100 text-stone-300'"
    >
      <i class="bi bi-chevron-right"></i>
    </button>
  </nav>
</template>
