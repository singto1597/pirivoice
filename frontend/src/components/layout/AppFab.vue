<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import type { RouteLocationRaw } from 'vue-router'

/**
 * ➕ ปุ่มลอยมุมขวาล่าง — **การกระทำหลักของหน้า** (แจ้งเรื่อง / สร้างกิจกรรม / เพิ่มสมาชิก)
 *
 * 🔴 **ทำไม "แจ้งเรื่อง" เป็น FAB ไม่ใช่แท็บ:** การแจ้งเรื่องเป็นการ *กระทำ* ไม่ใช่ *สถานที่*
 *    การเป็นแท็บทำให้แถบล่างมี 6 ช่อง (แน่นเกินไปบนจอ 360dp) และทำให้ปุ่มที่ผู้ใช้กดบ่อยที่สุด
 *    อยู่ตำแหน่งเดียวกับปุ่มนำทาง — ซึ่งเป็นคนละความหมายกัน
 *
 * ⚠️ **อยู่เหนือแถบล่างเสมอ** — ตำแหน่งคิดจาก `--app-nav-h` ที่ shell ประกาศค่าเดียว
 *    (ไม่ hardcode ความสูงแถบซ้ำในไฟล์นี้ ไม่งั้นแก้ที่หนึ่งแล้วปุ่มไปทับอีกที่)
 *
 * ⚠️ `lg:hidden` — บนเดสก์ท็อปการกระทำหลักอยู่ในหัวแถบ เพราะมีที่พอและไม่บังเนื้อหา
 */
const props = withDefaults(
  defineProps<{
    to: RouteLocationRaw
    /** ข้อความสำหรับโปรแกรมอ่านหน้าจอ — ต้องบอก *ผลของการกด* ไม่ใช่ชื่อไอคอน */
    label: string
    icon?: string
    /** ย่อ/จางเมื่อผู้ใช้เลื่อนลง (ให้เนื้อหากลับมาเต็มจอ) */
    collapsed?: boolean
  }>(),
  { icon: 'bi-plus-lg', collapsed: false },
)

const style = computed(() => ({
  bottom: 'calc(var(--app-nav-h, 0rem) + env(safe-area-inset-bottom, 0px) + 1rem)',
}))
</script>

<template>
  <RouterLink
    :to="props.to"
    :aria-label="props.label"
    :style="style"
    class="absolute right-4 z-30 flex h-14 w-14 items-center justify-center rounded-full bg-brand text-white shadow-fab transition-all duration-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 active:scale-95 lg:hidden"
    :class="props.collapsed ? 'pointer-events-none scale-75 opacity-0' : 'scale-100 opacity-100'"
  >
    <i :class="['bi', props.icon, 'text-2xl']" aria-hidden="true" />
  </RouterLink>
</template>
