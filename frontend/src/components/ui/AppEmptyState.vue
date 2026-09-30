<script setup lang="ts">
/**
 * 🫙 หน้าว่าง — แทน `<p>ยังไม่มี…</p>` ที่เขียนมือกระจาย ~25 จุด
 *
 * 🔴 **ไม่มีกรอบเส้นประ** โดยเจตนา (ต่างจากของเดิมที่ใช้ `border-2 border-dashed`) —
 *    เส้นประอ่านว่า "ยังไม่ได้ทำ / เป็นแบบร่าง / ลากไฟล์มาวาง" ซึ่งเป็นความรู้สึกแบบ
 *    wireframe ที่ audit ฟ้องทั้งฉบับ ⇒ ใช้พื้นเทาอ่อน + ไอคอนแทน
 *
 * ⚠️ **ต้องมีทางออกเสมอ** — เพิ่มปุ่มผ่าน slot ได้ (และควรใส่เมื่อผู้ใช้ *ทำอะไรได้*
 *    กับความว่างนั้น) · ถ้าไม่มีปุ่มเลย อย่างน้อยข้อความต้องบอกว่าต้องไปทำอะไรที่ไหน
 */
withDefaults(
  defineProps<{
    /** bootstrap-icons base name เช่น `'bi-inbox'` */
    icon?: string
    /** บรรทัดเดียว บอกว่า "ว่างเพราะอะไร" */
    title: string
    /** ทางออก — บอกว่า "แล้วต้องทำยังไง" */
    description?: string
    /** ย่อขนาดสำหรับกล่องเล็กในหน้า (เช่น ลิสต์ย่อยที่ว่าง) */
    compact?: boolean
  }>(),
  { icon: 'bi-inbox', compact: false },
)
</script>

<template>
  <div class="flex flex-col items-center text-center" :class="compact ? 'px-4 py-6' : 'px-6 py-12'">
    <span
      class="flex items-center justify-center rounded-full bg-canvas text-ink-3"
      :class="compact ? 'h-12 w-12' : 'h-16 w-16'"
      aria-hidden="true"
    >
      <i :class="['bi', icon, compact ? 'text-2xl' : 'text-3xl']" />
    </span>
    <p class="mt-3 font-semibold text-ink-1" :class="compact ? 'text-sm' : 'text-body'">
      {{ title }}
    </p>
    <p v-if="description" class="mt-1 max-w-xs text-[13px] leading-relaxed text-ink-2">
      {{ description }}
    </p>
    <div v-if="$slots.default" class="mt-4">
      <slot />
    </div>
  </div>
</template>
