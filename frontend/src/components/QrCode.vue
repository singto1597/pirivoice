<script setup lang="ts">
import { computed } from 'vue'
import { qrSvgDataUrl } from '@/qr'

/**
 * 🔳 แสดงคิวอาร์โค้ดจากข้อความ — ใช้ร่วมกันทั้ง **บัตรเช็คอิน** (D2) และ **ลิงก์เชิญ** (4.4)
 *
 * ⚠️ **คอมโพเนนต์นี้ไม่รู้จักความหมายของข้อความ** — ไม่รู้ว่าเป็นโทเคนหรือ URL และไม่สนใจ
 *    ⇒ ที่ที่รู้คือ view ที่เรียกใช้ (ถ้าใส่ความหมายของบัตรเช็คอินลงที่นี่ วันหน้าจะมีคน
 *    เอาไปใช้กับลิงก์แล้วได้ alt/ข้อความผิดโดยไม่มีใครรู้)
 *
 * ⚠️ **`v-html` ไม่ถูกใช้เลยโดยเจตนา** — SVG ถูกห่อเป็น data URL แล้วใส่ใน `src` ของ `<img>`
 *    ⇒ ต่อให้ข้อความที่ส่งมามี `<script>` (ซึ่งเป็นไปไม่ได้เพราะเราสร้าง QR เอง แต่กันไว้)
 *    มันก็ถูกเข้ารหัสเป็นพิกเซล ไม่มีทางถูกตีความเป็น markup
 */
const props = withDefaults(
  defineProps<{
    /** ข้อความที่จะฝังใน QR */
    value: string
    /** ขนาดที่แสดง (px) — เป็น *พิกเซลบนจอ* ไม่เกี่ยวกับขนาดข้อมูล */
    size?: number
    /** คำอธิบายภาพสำหรับ screen reader — บอกว่า QR นี้คืออะไร ไม่ใช่ "คิวอาร์โค้ด" ลอย ๆ */
    alt?: string
  }>(),
  { size: 220, alt: 'คิวอาร์โค้ด' },
)

/**
 * ⚠️ **ห่อ try/catch เพราะ `qrSvgDataUrl` โยนได้** (ข้อมูลว่าง/ยาวเกิน/อักขระที่ `btoa` ไม่รับ)
 *    ⇒ ถ้าไม่ห่อ การโยนใน `computed` จะทำให้ **ทั้งหน้าไม่เรนเดอร์** (Vue ยุบ component)
 *    ซึ่งแย่กว่าการที่ QR หายไปหนึ่งรูปมาก — ผู้เรียกทุกที่มีข้อความสำรองให้ใช้อยู่แล้ว
 */
const src = computed<string | null>(() => {
  try {
    return qrSvgDataUrl(props.value)
  } catch {
    return null
  }
})
</script>

<template>
  <img
    v-if="src"
    :src="src"
    :alt="alt"
    :width="size"
    :height="size"
    class="rounded-xl border border-stone-200 bg-white"
    data-testid="qr-code"
  />
  <!-- วาดไม่สำเร็จ — บอกตรง ๆ ดีกว่าเว้นที่ว่างแล้วให้ผู้ใช้เดาว่าพังหรือยังโหลดไม่เสร็จ -->
  <p
    v-else
    class="rounded-xl border border-dashed border-amber-300 bg-amber-50 px-3 py-6 text-center text-xs text-amber-800"
  >
    <i class="bi bi-exclamation-triangle mr-1"></i>แสดงคิวอาร์ไม่ได้ — ใช้รหัสด้านล่างแทน
  </p>
</template>
