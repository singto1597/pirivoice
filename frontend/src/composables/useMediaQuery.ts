import { onScopeDispose, ref, type Ref } from 'vue'

/**
 * 🖥️/📱 ติดตาม media query แบบ **รีแอกทีฟ** — ใช้เมื่อ "จำนวนโหนดใน DOM" ต้องต่างกันจริง ๆ
 * ตามขนาดจอ ไม่ใช่แค่ซ่อนด้วย CSS
 *
 * 🔴 **ทำไมต้องมี — บทเรียนจากการวัดบน staging (R2.3)**
 *    แถบปฏิบัติการใน `IssueDetail.vue` ต้องแสดงปุ่มรอง **สองหน้าตา** ต่างกัน:
 *    มือถืออยู่ในแผ่น `⋯` · เดสก์ท็อปเป็นปุ่มเรียงในแถว
 *    ถ้าทำด้วย CSS (`hidden lg:inline-flex`) โหนด**ยังอยู่ใน DOM ทั้งคู่**
 *    ⇒ ตอนเปิดแผ่นที่จอเล็กจะมี `data-testid` **ซ้ำกัน 2 ตัว**
 *    ⇒ Playwright นับ **ทุกโหนดที่ match ไม่สนใจว่ามองเห็นไหม** (strict mode)
 *    ⇒ `getByTestId('board-link')` ระเบิดด้วย "resolved to 2 elements"
 *
 *    ⇒ ใช้ `v-if` คู่กับคอมโพเซเบิลนี้แทน ⇒ **รับประกันว่ามีชุดเดียวใน DOM เสมอ**
 *      ซึ่งเป็นค่าคงที่ที่พิสูจน์ได้ ไม่ใช่ข้อสันนิษฐานเรื่อง CSS
 *
 * ⚠️ **เบรกพอยต์ต้องตรงกับ Tailwind** — `lg` = `64rem` = 1024px (ดู `tailwind.config.js`
 *    ที่ไม่ได้ override `screens`) ⇒ ถ้าวันหนึ่งแก้ `screens` ต้องแก้สตริงที่เรียกมาด้วย
 *
 * ⚠️ คืน `false` เมื่อไม่มี `matchMedia` (jsdom ในเทสต์ยูนิตไม่มี) — ตรงกับแนวที่ `pwa.ts` ใช้อยู่
 *    ⇒ เทสต์ที่ render วิวนี้จะได้เส้นทาง "จอเล็ก" ซึ่งเป็นค่าตั้งต้นที่ปลอดภัยกว่า
 *      (ไม่มีปุ่มเดสก์ท็อปลอยมาให้กดในเทสต์ที่ไม่ได้ตั้งใจทดสอบมัน)
 */
export function useMediaQuery(query: string): Ref<boolean> {
  const matches = ref(false)

  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return matches

  const mql = window.matchMedia(query)
  // อ่านค่าตั้งต้น **แบบซิงโครนัส** ไม่รอ event แรก — ไม่งั้นเฟรมแรกจะเรนเดอร์ผิดฝั่งแล้วกระพริบ
  matches.value = mql.matches

  const onChange = (e: MediaQueryListEvent) => {
    matches.value = e.matches
  }
  mql.addEventListener('change', onChange)
  onScopeDispose(() => mql.removeEventListener('change', onChange))

  return matches
}

/** เดสก์ท็อปตามนิยามของ Tailwind `lg` (≥ 1024px) — ใช้คู่กับคลาส `lg:*` ได้ตรงกัน */
export function useIsDesktop(): Ref<boolean> {
  return useMediaQuery('(min-width: 1024px)')
}
