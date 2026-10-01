<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import type { RouteLocationRaw } from 'vue-router'

/**
 * 🔘 ปุ่มมาตรฐานของระบบ — แทน `.btn-gradient` / `.btn-ghost-ui` และปุ่ม ad-hoc อีก ~80 จุด
 *
 * ⚠️ **สร้างบน `.btn-gradient` เดิม ไม่ใช่บน daisyUI** (`btn btn-primary`) ตามที่
 *    `docs/rules/frontend.md` §6 เขียนไว้ — เพราะ daisyUI ติดตั้งแบบ `themes: false`
 *    และ **ไม่มีเทมเพลตไหนใช้คลาสมันเลย** (ตรวจแล้ว) ⇒ การสร้างบน `btn`
 *    = ลากระบบสีชุดที่สองเข้ามาแข่งกับพาเลตต์ stone/cardinal ที่ `main.css` ต้องค้ำด้วย
 *    `!important` อยู่แล้ว · เอกสาร §6 จะถูกแก้ให้ตรงความจริงใน R5
 *
 * 🎨 `danger` = **ข้อความแดงล้วน ไม่มีขอบแดง** — ปุ่มอันตรายต้อง *หายาก* ไม่ใช่ *ตะโกน*
 *    (ปุ่ม outline แดงเต็มหน้าอ่านว่า "อันตราย" พร้อมกันหมด ⇒ ไม่มีความหมายอะไรเหลือ)
 */
// ⚠️ **ไม่ตั้ง `inheritAttrs: false`** — ต้องให้ `class` ที่พ่อส่งมา (เช่น `hidden xl:inline-flex`,
//    `relative`) รวมกับคลาสของตัวเองจริง ⇒ ถ้าปิด fallthrough แล้วไม่ `v-bind="$attrs"`
//    คลาสพวกนั้นจะหายเงียบ ๆ (คอมโพเนนต์ดูปกติ แต่ layout ที่พ่อจัดไว้พัง)

const props = withDefaults(
  defineProps<{
    /**
     * `light` = ปุ่มบน **พื้นเข้ม** (แถบทับกล้องในหน้าสแกนเช็คอิน)
     *
     * 🔴 **ต้องเป็น variant ไม่ใช่ส่ง `class="text-white"`** — ค่าประกอบสีของ Tailwind
     *    ตัดสินกันที่ **ลำดับในสไตล์ชีต** ไม่ใช่ลำดับในแอตทริบิวต์ `class` และสีที่
     *    `extend` เข้าไป (`brand`) ถูกสร้าง **หลัง** สีพื้นฐาน (`white`) เสมอ
     *    ⇒ `class="text-white"` บน `variant="text"` จะได้ตัวอักษร **แดงบนวิดีโอเข้ม** ทุกครั้ง
     */
    variant?: 'primary' | 'secondary' | 'text' | 'danger' | 'light'
    size?: 'sm' | 'md' | 'lg'
    /** กำลังโหลด — ปุ่มจม + ขึ้นวงกลมหมุน + กันกดซ้ำ */
    loading?: boolean
    disabled?: boolean
    /** กินความกว้างเต็มพื้นที่พ่อ */
    block?: boolean
    /** ใส่ = เรนเดอร์เป็นลิงก์ (ได้ `<a>` จริง ⇒ เปิดแท็บใหม่/กดขวาได้) */
    to?: RouteLocationRaw
    /** ปุ่มในฟอร์ม — ค่าเริ่มต้น `button` เพื่อไม่ให้ submit ฟอร์มโดยไม่ตั้งใจ */
    type?: 'button' | 'submit' | 'reset'
  }>(),
  { variant: 'primary', size: 'md', loading: false, disabled: false, block: false, type: 'button' },
)

const isLink = computed(() => props.to !== undefined)
const isDisabled = computed(() => props.disabled || props.loading)

/** ลิงก์ที่ถูกปิดต้องไม่มี `href` — `<a>` ไม่รู้จัก `disabled` จึงยังกดได้ถ้ายังมีปลายทาง */
const linkTo = computed<RouteLocationRaw | undefined>(() =>
  isDisabled.value ? undefined : props.to,
)

const SIZE: Record<'sm' | 'md' | 'lg', string> = {
  // ⚠️ `sm` สูง 36px (ต่ำกว่าเกณฑ์ 44dp) ⇒ ใช้ `after:` ถ่าง *พื้นที่กด* ออก ±4px
  //    ให้ได้ 44px โดยไม่ทำให้ปุ่มดูใหญ่ — สำหรับ toolbar ที่แถวมี padding ของตัวเองอยู่แล้ว
  sm: "h-9 px-3 text-[13px] rounded-control after:absolute after:inset-x-0 after:-inset-y-1 after:content-['']",
  md: 'h-11 px-4 text-sm rounded-control', // 44px
  lg: 'h-12 px-5 text-body rounded-control',
}

const VARIANT: Record<'primary' | 'secondary' | 'text' | 'danger' | 'light', string> = {
  primary: 'bg-brand text-white hover:bg-brand-strong',
  secondary: 'bg-surface text-ink-1 border border-line hover:bg-canvas',
  text: 'text-brand hover:bg-brand/5',
  danger: 'text-danger hover:bg-danger/5',
  light: 'text-white/90 hover:bg-white/10 hover:text-white',
}
</script>

<template>
  <component
    :is="isLink ? RouterLink : 'button'"
    v-bind="isLink ? { to: linkTo } : { type: props.type, disabled: isDisabled }"
    :aria-busy="props.loading || undefined"
    :aria-disabled="isLink && isDisabled ? 'true' : undefined"
    class="relative inline-flex shrink-0 items-center justify-center gap-1.5 font-semibold whitespace-nowrap transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50"
    :class="[
      SIZE[props.size],
      VARIANT[props.variant],
      props.block && 'w-full',
      // ลิงก์ที่ถูกปิดต้องกดไม่ได้ด้วย — `pointer-events-none` ไม่พอถ้ายังมี href
      isLink && isDisabled && 'pointer-events-none opacity-50',
    ]"
  >
    <i v-if="props.loading" class="bi bi-arrow-repeat animate-spin text-base" aria-hidden="true" />
    <slot v-else name="icon" />
    <slot />
  </component>
</template>
