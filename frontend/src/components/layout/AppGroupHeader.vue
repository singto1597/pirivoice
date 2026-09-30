<script setup lang="ts">
/**
 * 🏷️ หัวกลุ่มเมนู — **ติดขอบบนเมื่อเลื่อน** (`sticky`)
 *
 * ⚠️ `sticky` ใช้ได้เพราะ `<main>` เป็น scroll container จริง (ไม่ใช่ `body`)
 *    🔴 **ห้ามเพิ่ม `overflow-x-hidden` ให้ `<main>` หรือ wrapper `max-w-7xl`**
 *    — `overflow-x: hidden` บนบรรพบุรุษจะทำให้ `sticky` ของลูกหยุดทำงาน *เงียบ ๆ*
 *    (`skills.md` #11 · `PlaybookReader.vue` ก็พึ่ง `sticky` อยู่)
 *
 * ⚠️ พื้นต้อง **ทึบ** ไม่ใช่โปร่ง/เบลอ — ไม่งั้นแถวที่เลื่อนไปข้างหลังจะทะลุขึ้นมาอ่านไม่ออก
 *    ⇒ ต้องเลือก `tone` ให้ตรงกับพื้นที่ที่วาง (หน้า More = `canvas`, sidebar = `surface`)
 *
 * 📐 `px-4` (16px) ตั้งใจให้ตรงกับไอคอนใน `AppNavRow` (พ่อ `px-2` + แถว `px-2` = 16px)
 */
withDefaults(
  defineProps<{
    /** ชื่อกลุ่ม — ไทยล้วน */
    label: string
    /** สีพื้นของพื้นที่ที่วางหัวกลุ่มนี้ — ต้องทึบเสมอ */
    tone?: 'canvas' | 'surface'
  }>(),
  { tone: 'canvas' },
)
</script>

<template>
  <h2
    class="sticky top-0 z-10 px-4 py-2 text-[13px] font-bold text-ink-2"
    :class="tone === 'surface' ? 'bg-surface' : 'bg-canvas'"
  >
    {{ label }}
  </h2>
</template>
