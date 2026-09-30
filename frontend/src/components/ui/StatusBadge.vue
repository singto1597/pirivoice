<script setup lang="ts">
import { computed } from 'vue'
import { STATUS_BADGE, STATUS_DOT, statusShort } from '@/constants/status'

/**
 * 🏷️ ป้ายสถานะเรื่อง — ครอบ `constants/status.ts` เดิม (ไม่สร้างแผนที่สีชุดใหม่)
 *
 * 🔴 **มีจุดสีนำหน้าข้อความเสมอ** (ค่าเริ่มต้น) — เพราะสถานะที่สื่อด้วย *สีอย่างเดียว*
 *    ผู้ใช้ที่ตาบอดสีอ่านไม่ออก และพิมพ์ขาวดำ/ถ่ายเอกสารก็หายไปด้วย
 *    ⇒ สีเป็นตัวช่วยจำ ข้อความเป็นตัวจริง
 *
 * ⚠️ ป้ายยาว (`STATUS_LABELS`) ใช้ใน dropdown/ตัวกรอง · ป้ายสั้น (`statusShort`)
 *    ใช้ในแถวรายการ — ที่นี่เลือกได้ผ่าน `variant`
 */
const props = withDefaults(
  defineProps<{
    status: string
    /** ทับข้อความที่แสดง (เช่น อยากได้ "เสร็จแล้ว" แทน "ปิด") */
    label?: string
    /** `short` = ป้ายสั้นสำหรับแถวรายการ (ค่าเริ่มต้น) · `full` = ชื่อเต็ม */
    size?: 'short' | 'full'
    /** ซ่อนจุดสี — ใช้เมื่อบริบทอื่นบอกสถานะซ้ำอยู่แล้ว (เช่นอยู่ใต้หัวข้อสถานะนั้น) */
    hideDot?: boolean
  }>(),
  { size: 'short', hideDot: false },
)

const tone = computed(() => STATUS_BADGE[props.status] ?? 'bg-canvas text-ink-2')
const dot = computed(() => STATUS_DOT[props.status] ?? 'bg-ink-3')
const text = computed(() => props.label ?? statusShort(props.status))
</script>

<template>
  <span
    class="inline-flex items-center gap-1.5 rounded-full font-semibold whitespace-nowrap"
    :class="[tone, size === 'full' ? 'px-2.5 py-1 text-[13px]' : 'px-2 py-0.5 text-[11px]']"
  >
    <span v-if="!hideDot" class="h-2 w-2 shrink-0 rounded-full" :class="dot" aria-hidden="true" />
    {{ text }}
  </span>
</template>
