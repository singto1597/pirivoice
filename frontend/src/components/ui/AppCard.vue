<script setup lang="ts">
/**
 * 🃏 การ์ดมาตรฐาน — พื้นขาว · เส้นขอบ 1px · มุม 16px · **ไม่มีเงา**
 *
 * เงาถูกถอดออกโดยเจตนา (ทิศทาง Editorial & Civic) — ลำดับชั้นเกิดจาก *ช่องว่าง*
 * และ *เส้น* ไม่ใช่จากเงาฟุ้ง · ถ้าต้องการให้การ์ดเด่น ให้ใช้ `interactive` (hover เปลี่ยนเส้น)
 * ไม่ใช่เพิ่มเงา
 *
 * ก่อนหน้านี้ทุกหน้าเขียน `bg-white rounded-2xl border border-stone-200` เอง
 * ⇒ สีเส้นปนกัน 3 ค่า (stone-100/200/300) และมุมปนกัน 4 ค่า ⇒ รวมมาที่นี่
 */
withDefaults(
  defineProps<{
    /** ใส่ padding 16dp ให้ในตัว — ปิดเมื่อการ์ดมีรูป/แผนที่ที่ต้องชนขอบ */
    padded?: boolean
    /** มีhover/focus ให้รู้ว่ากดได้ (การ์ดที่เป็นลิงก์) — ยังไม่ใส่เงา */
    interactive?: boolean
    /** พื้นเทาอ่อนแทนขาว — สำหรับการ์ดรอง/บล็อกสรุปที่ไม่ใช่เนื้อหาหลัก */
    muted?: boolean
  }>(),
  { padded: true, interactive: false, muted: false },
)
</script>

<template>
  <div
    class="rounded-card border border-line transition-colors"
    :class="[
      muted ? 'bg-canvas' : 'bg-surface',
      padded && 'p-4',
      interactive && 'hover:border-brand/40 focus-within:border-brand/40',
    ]"
  >
    <slot />
  </div>
</template>
