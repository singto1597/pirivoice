<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import type { RouteLocationRaw } from 'vue-router'

/**
 * 🔲 ปุ่มไอคอนล้วน — บังคับ **`label`** (กลายเป็น `aria-label`) และ **พื้นที่กด ≥ 44dp**
 *
 * 🔴 **`label` เป็น required โดยเจตนา** — ปุ่มที่มีแต่ไอคอนคือปุ่มที่โปรแกรมอ่านหน้าจอ
 *    เรียกได้แค่ว่า "ปุ่ม" ⇒ ผู้ใช้ที่มองไม่เห็นไม่รู้เลยว่ากดแล้วเกิดอะไร
 *    การบังคับที่ระดับ type ทำให้ลืมไม่ได้ (ต่างจาก convention ที่ต้องมีคนรีวิวจับ)
 *
 * 🔴 **ขนาดขั้นต่ำ 44dp** ตามเกณฑ์การแตะบนมือถือ — วันนี้มีปุ่ม `h-9 w-9` (36dp)
 *    กระจายอยู่หลายหน้า ซึ่งเล็กกว่ามาตรฐาน (audit §5)
 */
// ⚠️ **ไม่ตั้ง `inheritAttrs: false`** — ต้องให้ `class` ที่พ่อส่งมา (เช่น `hidden xl:inline-flex`,
//    `relative`) รวมกับคลาสของตัวเองจริง ⇒ ถ้าปิด fallthrough แล้วไม่ `v-bind="$attrs"`
//    คลาสพวกนั้นจะหายเงียบ ๆ (คอมโพเนนต์ดูปกติ แต่ layout ที่พ่อจัดไว้พัง)

const props = withDefaults(
  defineProps<{
    /** bootstrap-icons base name เช่น `'bi-arrow-left'` (ใส่ `bi` ให้อัตโนมัติ) */
    icon: string
    /** ข้อความสำหรับโปรแกรมอ่านหน้าจอ — **ต้องบอกว่ากดแล้วเกิดอะไร** ไม่ใช่ชื่อไอคอน */
    label: string
    /** ใส่ = เรนเดอร์เป็นลิงก์ */
    to?: RouteLocationRaw
    /** `md` = 44dp (ค่าเริ่มต้น) · `lg` = 48dp สำหรับหัวแถบ */
    size?: 'md' | 'lg'
    /** ไฮไลต์ว่ากำลัง active อยู่ (ใช้ในแถบล่าง/แถบ segment) */
    active?: boolean
    /** แดง — สำหรับ action อันตราย (ลบ/ซ่อน) */
    danger?: boolean
    disabled?: boolean
  }>(),
  { size: 'md', active: false, danger: false, disabled: false },
)

const isLink = computed(() => props.to !== undefined)

const SIZE: Record<'md' | 'lg', string> = {
  md: 'h-11 w-11 rounded-control',
  lg: 'h-12 w-12 rounded-control',
}
</script>

<template>
  <component
    :is="isLink && !props.disabled ? RouterLink : 'button'"
    v-bind="
      isLink && !props.disabled
        ? { to: props.to, 'aria-label': props.label }
        : { type: 'button', disabled: props.disabled, 'aria-label': props.label }
    "
    class="inline-flex shrink-0 items-center justify-center transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50"
    :class="[
      SIZE[props.size],
      props.active
        ? 'bg-brand/10 text-brand'
        : props.danger
          ? 'text-ink-2 hover:bg-danger/5 hover:text-danger'
          : 'text-ink-2 hover:bg-canvas hover:text-ink-1',
    ]"
  >
    <i :class="['bi', props.icon, 'text-xl']" aria-hidden="true" />
    <slot />
  </component>
</template>
