<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import type { NavItem } from '@/constants/nav'
import { BADGE_CAP } from '@/composables/useNavItems'

/**
 * 📋 แถวเมนูหนึ่งแถว (56dp) — **ใช้ร่วมกันทั้ง sidebar และหน้า "เพิ่มเติม"**
 *
 * ⚠️ ทั้งสองที่ต่างกันแค่ `variant` เท่านั้น ⇒ การมีคอมโพเนนต์เดียวคือจุดที่ประหยัดที่สุด
 *    ของ R0 (เดิม sidebar กับ bottom sheet เขียน markup คล้ายกันคนละชุด แล้วเพี้ยนจากกัน)
 *
 * ⚠️ แถวที่เป็น *action* (ออกจากระบบ) ไม่มี `to` ⇒ เรนเดอร์เป็น `<button>` และ
 *    **ส่ง `action` ขึ้นไปให้พ่อจัดการ** ไม่เรียกเอง — เพราะการ logout ต้องพาไปหน้า login
 *    ซึ่งเป็นเรื่องของ shell ไม่ใช่ของแถว
 *
 * 📐 **ระยะขอบตายตัว:** แถวมี `px-2` และพ่อของแถวต้องมี `px-2` รวมเป็น 16px
 *    ⇒ ไอคอนในแถวอยู่ที่ 16px เท่ากับตัวอักษรของ `AppGroupHeader` (`px-4`) พอดี
 *    ⇒ เปลี่ยน padding ที่ใดที่หนึ่งต้องเปลี่ยนอีกที่ให้ตรงกัน (ไม่งั้นหัวกลุ่มเยื้องจากแถว)
 */
const props = withDefaults(
  defineProps<{
    item: NavItem
    /** เลข badge — 0 = ไม่แสดง */
    badge?: number
    active?: boolean
  }>(),
  { badge: 0, active: false },
)

const emit = defineEmits<{ action: [key: string] }>()

const isLink = computed(() => props.item.to !== undefined)
const badgeText = computed(() => (props.badge > BADGE_CAP ? `${BADGE_CAP}+` : String(props.badge)))

/**
 * ⚠️ ต้องเช็ค `props.item.action` ก่อน emit — type เป็น `'logout' | undefined`
 *    (ฝั่ง `to` ของ union มี `action?: never`) และ `noUncheckedIndexedAccess`/strict
 *    ไม่ยอมให้ส่ง `undefined` เข้า emit ที่ประกาศ `[key: string]`
 */
function onClick(): void {
  if (isLink.value) return
  if (props.item.action) emit('action', props.item.action)
}
</script>

<template>
  <component
    :is="isLink ? RouterLink : 'button'"
    v-bind="isLink ? { to: props.item.to } : { type: 'button' }"
    class="flex h-14 w-full items-center gap-3 rounded-control px-2 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand"
    :class="props.active ? 'bg-brand-tint text-brand' : 'text-ink-1 hover:bg-canvas'"
    @click="onClick"
  >
    <i
      :class="['bi', props.item.icon, 'shrink-0 text-xl', props.active ? 'text-brand' : 'text-ink-2']"
      aria-hidden="true"
    />
    <span class="min-w-0 flex-1 truncate text-sm font-semibold">{{ props.item.label }}</span>

    <span
      v-if="props.badge > 0"
      class="shrink-0 rounded-full bg-brand px-1.5 py-0.5 text-[11px] font-bold tabular-nums text-white"
    >
      {{ badgeText }}
    </span>
    <i
      v-if="isLink"
      class="bi bi-chevron-right shrink-0 text-xs text-ink-3"
      aria-hidden="true"
    />
  </component>
</template>
