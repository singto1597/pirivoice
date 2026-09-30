<script setup lang="ts">
import { computed } from 'vue'

/**
 * 📰 หัวเรื่องในหน้า — **`<h2>` เป็นค่าเริ่มต้น**
 *
 * 🔴 **นี่คือกลไกที่ลบ `<h1>` ซ้ำได้ ~22 จุดโดยไม่เสีย semantics ของ heading**
 *    ปัญหาวันนี้: ทุกหน้าใส่ `<h1>` ชื่อหน้า ทั้งที่ `AppHeader` ก็แสดงชื่อเดียวกันอยู่แล้ว
 *    ⇒ ผู้ใช้เห็นชื่อหน้าสองครั้งห่างกัน 40px และโปรแกรมอ่านหน้าจออ่านซ้ำ
 *    ⇒ ลำดับ heading ที่ถูกต้องคือ `h1` = ชื่อหน้า (อยู่ที่ `AppHeader`) แล้วหน้าใช้ `h2`
 *
 * ⚠️ `level: 1` สงวนไว้ให้หน้าที่ **ซ่อนหัวแถบ** (`meta.headerHidden` เช่น สแกนเนอร์เต็มจอ)
 *    ซึ่งชื่อหน้าจะไม่ปรากฏที่อื่นเลย ⇒ ถ้าหน้านั้นยังไม่มี `h1` เอกสารจะไม่มีหัวเรื่อง
 *
 * ⚠️ `eyebrow` เป็น **opt-in** (เดิมทุกหน้าใส่คำอังกฤษตัวพิมพ์ใหญ่ตัวจิ๋วเหนือหัวข้อ
 *    เช่น `STUDENT VOICE`, `PIRI BOARDS`) — คำพวกนั้นไม่ช่วยให้เข้าใจอะไร และ
 *    การ `uppercase` + `tracking-widest` กับข้อความไทยทำให้สระ/วรรณยุกต์ลอยห่างจากพยัญชนะ
 */
const props = withDefaults(
  defineProps<{
    title: string
    /** คำอธิบายใต้หัวเรื่อง — ใช้เมื่อชื่อหน้าอย่างเดียวไม่พอ */
    description?: string
    /** ป้ายเล็กเหนือหัวเรื่อง — **ไม่ใส่จะดีกว่า** ใส่เฉพาะเมื่อเพิ่มข้อมูลจริง */
    eyebrow?: string
    /** 1 = หน้าที่ซ่อนหัวแถบ (ดูคำอธิบายข้างบน) · ค่าเริ่มต้น 2 */
    level?: 1 | 2
  }>(),
  { level: 2 },
)

const tag = computed(() => `h${props.level}`)
</script>

<template>
  <div class="mb-4">
    <p v-if="props.eyebrow" class="text-[13px] font-semibold text-ink-2">{{ props.eyebrow }}</p>
    <component
      :is="tag"
      class="text-title-l font-bold text-ink-1"
      :class="props.eyebrow && 'mt-0.5'"
    >
      {{ props.title }}
    </component>
    <p v-if="props.description" class="mt-1 text-sm leading-relaxed text-ink-2">
      {{ props.description }}
    </p>
    <div v-if="$slots.actions" class="mt-3 flex flex-wrap items-center gap-2">
      <slot name="actions" />
    </div>
  </div>
</template>
