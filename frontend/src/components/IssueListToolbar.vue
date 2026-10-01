<script setup lang="ts">
import { ref, watch, onMounted, onBeforeUnmount } from 'vue'

/**
 * แถบเครื่องมือรายการเรื่อง (ใช้ร่วมหน้าเรื่องที่รับ + เรื่องของฉัน):
 * - ช่องค้นหา (debounce 300ms) → emit change
 * - ปุ่ม filter แบบ Icon (YouTube) → dropdown: slot ตัวกรองเฉพาะหน้า + เรียงลำดับ (เก่า/ใหม่)
 * - ข้อความ "แสดง X / Y เรื่อง"
 *
 * q / sort เป็น v-model — parent เป็น owner state ส่วน filter ใน slot เป็น parent ควบคุมเอง
 * @change เกิดเมื่อ search/sort เปลี่ยน → parent ควร reset หน้าเป็น 1 แล้วโหลดใหม่
 */
defineProps<{
  total: number
  count: number
  activeFilters: number // จำนวน filter ที่ active อยู่ (badge บนปุ่ม)
  loading?: boolean
}>()

const q = defineModel<string>('q', { default: '' })
const sort = defineModel<'asc' | 'desc'>('sort', { default: 'desc' })

const emit = defineEmits<{ change: [] }>()

// ===== dropdown filter (click-outside ปิด) =====
const rootEl = ref<HTMLElement | null>(null)
const open = ref(false)
function onClickOutside(e: MouseEvent) {
  if (rootEl.value && !rootEl.value.contains(e.target as Node)) open.value = false
}
onMounted(() => document.addEventListener('click', onClickOutside))
onBeforeUnmount(() => document.removeEventListener('click', onClickOutside))

// ===== debounce search → change (parent reload หน้า 1) =====
let timer: ReturnType<typeof setTimeout> | undefined
watch(q, () => {
  clearTimeout(timer)
  timer = setTimeout(() => emit('change'), 300)
})
watch(sort, () => emit('change'))
</script>

<template>
  <div ref="rootEl" class="flex flex-wrap items-center gap-2">
    <!-- 🔍 ค้นหา -->
    <div class="relative flex-1 min-w-[200px] sm:flex-none sm:w-72">
      <i class="bi bi-search absolute left-3 top-1/2 -translate-y-1/2 text-ink-3 text-sm"></i>
      <input
        v-model="q"
        type="search"
        placeholder="ค้นหาเรื่อง / ห้อง / ชื่อคน..."
        class="w-full pl-9 pr-8 py-2.5 border border-stone-300 rounded-xl text-sm bg-white"
      />
      <button
        v-if="q"
        type="button"
        @click="q = ''"
        title="ล้างคำค้นหา"
        class="absolute right-2.5 top-1/2 -translate-y-1/2 text-ink-3 hover:text-stone-600 text-sm"
      >
        <i class="bi bi-x-circle-fill"></i>
      </button>
    </div>

    <!-- 🎚️ ปุ่ม Filter (Icon แบบ YouTube) -->
    <div class="relative">
      <button
        type="button"
        @click="open = !open"
        :aria-expanded="open"
        title="กรอง / เรียงลำดับ"
        class="relative flex min-w-11 items-center gap-1.5 px-3 h-11 border rounded-xl text-sm transition"
        :class="
          open
            ? 'border-brand bg-red-50 text-brand'
            : 'border-stone-300 bg-white text-stone-600 hover:border-brand hover:text-brand'
        "
      >
        <i class="bi bi-sliders text-base"></i>
        <span class="hidden sm:inline">กรอง</span>
        <span
          v-if="activeFilters > 0"
          class="absolute -top-1.5 -right-1.5 min-w-[18px] h-[18px] px-1 rounded-full bg-brand text-white text-[10px] font-bold flex items-center justify-center"
        >
          {{ activeFilters }}
        </span>
      </button>

      <Transition name="pop">
        <div
          v-if="open"
          class="absolute right-0 top-full mt-2 w-72 sm:w-80 bg-white border border-stone-200 rounded-2xl z-30 p-4"
        >
          <slot name="filters" />

          <!-- เรียงลำดับ -->
          <div class="mt-4 pt-3 border-t border-stone-100">
            <p class="text-xs font-semibold text-stone-500 mb-2">
              <i class="bi bi-arrow-down-up mr-1"></i> เรียงลำดับ
            </p>
            <div class="grid grid-cols-2 gap-1 p-1 bg-stone-100 rounded-xl">
              <button
                type="button"
                @click="sort = 'desc'"
                :class="sort === 'desc' ? 'bg-white border border-stone-200 text-brand' : 'border border-transparent text-stone-500 hover:text-stone-700'"
                class="inline-flex items-center px-3 min-h-11 py-1.5 rounded-lg text-sm font-medium transition"
              >
                ใหม่ไปเก่า
              </button>
              <button
                type="button"
                @click="sort = 'asc'"
                :class="sort === 'asc' ? 'bg-white border border-stone-200 text-brand' : 'border border-transparent text-stone-500 hover:text-stone-700'"
                class="inline-flex items-center px-3 min-h-11 py-1.5 rounded-lg text-sm font-medium transition"
              >
                เก่าไปใหม่
              </button>
            </div>
          </div>
        </div>
      </Transition>
    </div>

    <!-- จำนวนเรื่อง -->
    <span class="text-sm text-ink-3 ml-auto tabular-nums" :class="{ 'opacity-50': loading }">
      {{ count.toLocaleString('en-US') }} / {{ total.toLocaleString('en-US') }} เรื่อง
    </span>
  </div>
</template>

<style scoped>
/* dropdown เปิด/ปิด */
.pop-enter-active,
.pop-leave-active {
  transition: opacity 0.15s ease, transform 0.15s ease;
}
.pop-enter-from,
.pop-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}
</style>
