<script setup lang="ts">
import { computed } from 'vue'
import type { AppTabOption } from './types'

/**
 * 📑 แท็บในหน้า — **สูงสุด 4 ตัว · ไม่มีไอคอน · ห้ามตัดบรรทัด**
 *
 * 🔴 **เกิน 4 ตัวให้ใช้ `AppChip` แถวเลื่อนแทน** ไม่ใช่ยัดลง `AppTabs` —
 *    แท็บ 5–6 ตัวบนจอ 360dp ทำให้ป้ายตกบรรทัดที่สอง (ปัญหาจริงในหน้ารายงาน 4 แท็บ
 *    และหน้ากิจกรรม 6 แท็บวันนี้) ⇒ จำนวนเท่ากันทุกช่อง + `whitespace-nowrap` บังคับโดยโครงสร้าง
 *
 * ⚠️ ไม่มีไอคอนโดยเจตนา — ไอคอนกินความกว้างจนต้องตัดคำ และไม่ได้ช่วยให้เข้าใจมากขึ้น
 *    เมื่อป้ายเป็นภาษาไทยที่อ่านออกอยู่แล้ว
 */
const props = defineProps<{
  tabs: readonly AppTabOption[]
  /** key ของแท็บที่เลือก */
  modelValue: string
}>()

const emit = defineEmits<{ 'update:modelValue': [key: string] }>()

const columns = computed(() => `repeat(${props.tabs.length}, minmax(0, 1fr))`)
</script>

<template>
  <div
    class="grid border-b border-line"
    :style="{ gridTemplateColumns: columns }"
    role="tablist"
  >
    <button
      v-for="tab in props.tabs"
      :key="tab.key"
      type="button"
      role="tab"
      :aria-selected="tab.key === props.modelValue"
      class="-mb-px flex h-11 items-center justify-center gap-1.5 border-b-2 px-2 text-sm font-semibold whitespace-nowrap transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand"
      :class="
        tab.key === props.modelValue
          ? 'border-brand text-brand'
          : 'border-transparent text-ink-2 hover:text-ink-1'
      "
      @click="emit('update:modelValue', tab.key)"
    >
      {{ tab.label }}
      <span
        v-if="tab.badge"
        class="rounded-full px-1.5 text-[11px] font-bold tabular-nums"
        :class="tab.key === props.modelValue ? 'bg-brand/15 text-brand' : 'bg-canvas text-ink-3'"
      >
        {{ tab.badge > 99 ? '99+' : tab.badge }}
      </span>
    </button>
  </div>
</template>
