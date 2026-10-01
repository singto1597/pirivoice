<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import type { RouteLocationRaw } from 'vue-router'

/**
 * 🏷️ ชิปกรอง — ใช้แทน select/dropdown ที่กินพื้นที่ และแทน `<button>` ที่เขียนมือในหน้า
 * `EventList` / `NotificationCenter` / `MyIssues`
 *
 * ⚠️ **`whitespace-nowrap` + ห้ามตัดบรรทัด** — ชิปที่ตัดคำ 2 บรรทัดจะสูงไม่เท่ากัน
 *    ทำให้แถวเลื่อนแนวนอนกระโดด (ปัญหาจริงในหน้ารายงาน/กิจกรรมวันนี้)
 *    ตัวที่ยาวเกินให้ *เลื่อน* เอา ไม่ใช่ *ตัด*
 *
 * 🎨 ชิปที่เลือก = `bg-brand-tint text-brand` (**ไม่ใช่แดงทึบ**) — เพราะแดงทึบสงวนไว้ให้
 *    "ปุ่มหลัก" ตัวเดียวในหน้า ถ้าชิปกรองทึบแดงเท่าปุ่มหลัก ผู้ใช้จะหาปุ่มหลักไม่เจอ
 */
// ⚠️ **ไม่ตั้ง `inheritAttrs: false`** — ต้องให้ `class` ที่พ่อส่งมา (เช่น `hidden xl:inline-flex`,
//    `relative`) รวมกับคลาสของตัวเองจริง ⇒ ถ้าปิด fallthrough แล้วไม่ `v-bind="$attrs"`
//    คลาสพวกนั้นจะหายเงียบ ๆ (คอมโพเนนต์ดูปกติ แต่ layout ที่พ่อจัดไว้พัง)

const props = withDefaults(
  defineProps<{
    label: string
    active?: boolean
    /** ตัวเลขท้ายชิป (เช่น จำนวนเรื่องในสถานะนั้น) — 0 = ไม่แสดง */
    count?: number
    /** ใส่ = เรนเดอร์เป็นลิงก์ */
    to?: RouteLocationRaw
    disabled?: boolean
  }>(),
  { active: false, disabled: false },
)

const isLink = computed(() => props.to !== undefined && !props.disabled)
</script>

<template>
  <component
    :is="isLink ? RouterLink : 'button'"
    v-bind="
      isLink
        ? { to: props.to }
        : { type: 'button', disabled: props.disabled, 'aria-pressed': props.active }
    "
    class="inline-flex h-11 shrink-0 items-center gap-1.5 rounded-full border px-3.5 text-[13px] font-semibold whitespace-nowrap transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-1 disabled:pointer-events-none disabled:opacity-40"
    :class="
      props.active
        ? 'border-brand/30 bg-brand-tint text-brand'
        : 'border-line bg-surface text-ink-2 hover:border-ink-3 hover:text-ink-1'
    "
  >
    {{ props.label }}
    <span
      v-if="props.count"
      class="rounded-full px-1.5 text-[11px] font-bold tabular-nums"
      :class="props.active ? 'bg-brand/15 text-brand' : 'bg-canvas text-ink-3'"
    >
      {{ props.count > 99 ? '99+' : props.count }}
    </span>
  </component>
</template>
