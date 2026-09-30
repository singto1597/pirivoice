<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'

/**
 * 🪟 แผ่นเลื่อนขึ้นจากขอบล่าง — สำหรับ **เลือก / ยืนยัน / เปิดของรอง**
 *
 * 🔴 **`<Teleport to="body">` + `z-[60]` บังคับ ไม่ใช่ตัวเลือก**
 *    bottom nav เป็น `fixed z-40` ⇒ แผ่นที่เรนเดอร์ในตำแหน่งเดิมจะถูกทับ *และกลืนคลิก*
 *    (`skills.md` #9 — เคยเกิดจริงกับโมดัลภาคเรียน: ปุ่มในแผ่นกดไม่ติดทั้งที่มองเห็น)
 *
 * 🔴 **ห้ามใส่ฟอร์มในแผ่นนี้** (`skills.md` #16) — ฟอร์มต้องเป็น *หน้าเต็ม* เสมอ
 *    เพราะ (1) คีย์บอร์ดมือถือจะดันแผ่นจนไม่เห็นช่องที่กรอก (2) ปิดแผ่นแล้วข้อมูลหาย
 *    (3) ปุ่มย้อนของเบราว์เซอร์ปิดแผ่นแทนที่จะย้อนฟอร์ม ⇒ แผ่นนี้เป็น surface
 *    ของ "เลือกจากรายการ" / "ยืนยัน" เท่านั้น
 *
 * 🔴 **หัวเรื่อง sticky** — ของเดิม (`MainLayout.vue` bottom sheet) วาง handle + ชื่อผู้ใช้
 *    + ปุ่มปิดไว้ *ในสกroller* ⇒ เลื่อนลงแล้วหัวหาย ปุ่มปิดหายตาม (audit ข้อ 2.2)
 */
const props = defineProps<{
  /** ผูกกับ `v-model` */
  modelValue: boolean
  /** หัวเรื่อง — ควรมี ถ้าแผ่นไม่มีหัวเรื่อง ผู้ใช้จะไม่รู้ว่ากำลังเลือกอะไรอยู่ */
  title?: string
  description?: string
}>()

const emit = defineEmits<{ 'update:modelValue': [value: boolean] }>()

const panel = ref<HTMLElement | null>(null)
/** เก็บ element ที่โฟกัสอยู่ก่อนเปิด เพื่อคืนโฟกัสกลับเมื่อปิด (a11y) */
let lastFocused: HTMLElement | null = null

const FOCUSABLE =
  'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])'

function close(): void {
  emit('update:modelValue', false)
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape') {
    event.preventDefault()
    close()
    return
  }
  if (event.key !== 'Tab') return

  // ♿ กักโฟกัสไว้ในแผ่น — ไม่งั้น Tab จะหลุดไปกดของที่ซ่อนอยู่หลังฉากมืด
  const root = panel.value
  if (!root) return
  const items = Array.from(root.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(
    (el) => el.offsetParent !== null,
  )
  const first = items[0]
  const last = items[items.length - 1]
  if (!first || !last) return

  const active = document.activeElement
  if (event.shiftKey && (active === first || !root.contains(active))) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && active === last) {
    event.preventDefault()
    first.focus()
  }
}

watch(
  () => props.modelValue,
  async (open) => {
    if (open) {
      lastFocused = document.activeElement as HTMLElement | null
      document.addEventListener('keydown', onKeydown)
      // ล็อกการเลื่อนของหน้าใต้แผ่น — ไม่งั้นเลื่อนแล้วหน้าไหลตามหลังฉากมืด
      document.body.style.overflow = 'hidden'
      await nextTick()
      const root = panel.value
      const target = root?.querySelector<HTMLElement>(FOCUSABLE) ?? root
      target?.focus()
    } else {
      document.removeEventListener('keydown', onKeydown)
      document.body.style.overflow = ''
      lastFocused?.focus()
      lastFocused = null
    }
  },
)

onBeforeUnmount(() => {
  document.removeEventListener('keydown', onKeydown)
  document.body.style.overflow = ''
})
</script>

<template>
  <Teleport to="body">
    <Transition name="sheet">
      <!-- z-[60] = เหนือ bottom nav (z-40) และ InstallPrompt (z-50) -->
      <div v-if="props.modelValue" class="fixed inset-0 z-[60] lg:hidden">
        <button
          type="button"
          class="absolute inset-0 h-full w-full cursor-default bg-ink-1/40"
          aria-label="ปิด"
          tabindex="-1"
          @click="close"
        />

        <div
          ref="panel"
          role="dialog"
          aria-modal="true"
          :aria-label="props.title"
          tabindex="-1"
          class="absolute inset-x-0 bottom-0 flex max-h-[85dvh] flex-col rounded-t-sheet bg-surface shadow-sheet outline-none"
        >
          <!-- หัวเรื่อง sticky — ปุ่มปิดต้องกดได้เสมอไม่ว่าจะเลื่อนไปไกลแค่ไหน -->
          <div class="shrink-0 rounded-t-sheet border-b border-line bg-surface px-4 pt-3 pb-3">
            <div class="mx-auto mb-3 h-1.5 w-10 rounded-full bg-line" aria-hidden="true" />
            <div class="flex items-start gap-3">
              <div class="min-w-0 flex-1">
                <h2 v-if="props.title" class="truncate text-title-m font-bold text-ink-1">
                  {{ props.title }}
                </h2>
                <p v-if="props.description" class="mt-0.5 text-[13px] leading-relaxed text-ink-2">
                  {{ props.description }}
                </p>
              </div>
              <button
                type="button"
                aria-label="ปิด"
                class="-mr-1 -mt-1 flex h-11 w-11 shrink-0 items-center justify-center rounded-control text-ink-2 transition-colors hover:bg-canvas hover:text-ink-1"
                @click="close"
              >
                <i class="bi bi-x-lg text-lg" aria-hidden="true" />
              </button>
            </div>
          </div>

          <!-- เนื้อหา — เลื่อนได้ แต่หัวไม่ไป -->
          <div class="min-h-0 flex-1 overflow-y-auto overscroll-contain px-2 py-2 pb-safe">
            <slot />
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.sheet-enter-active,
.sheet-leave-active {
  transition: opacity 0.25s ease;
}
.sheet-enter-active > div:last-child,
.sheet-leave-active > div:last-child {
  transition: transform 0.3s cubic-bezier(0.175, 0.885, 0.32, 1);
}
.sheet-enter-from,
.sheet-leave-to {
  opacity: 0;
}
.sheet-enter-from > div:last-child,
.sheet-leave-to > div:last-child {
  transform: translateY(100%);
}

@media (prefers-reduced-motion: reduce) {
  .sheet-enter-active,
  .sheet-leave-active,
  .sheet-enter-active > div:last-child,
  .sheet-leave-active > div:last-child {
    transition: none !important;
  }
}
</style>
