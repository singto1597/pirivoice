<!-- eslint-disable vue/multi-word-component-names -- 'SchoolSystemsCard' = ชื่อที่อ่านออกตรงตัว -->
<script setup lang="ts">
/**
 * 🏫 เมนูลัดไประบบอื่นของโรงเรียน (หน้าแรก)
 *
 * **ทำไมต้องมี:** โรงเรียนมีระบบอื่นที่นักเรียนต้องใช้ทุกวันอยู่หลายตัว แต่เดิมไม่มี
 * ทางไปจากในแอปเลย ⇒ ต้องจำ URL เอง หรือไปหาจากเว็บโรงเรียน
 *
 * **ทำไมเป็น "การ์ดนิ่ง" ไม่ยิง API:** สองปลายทางนี้เป็นข้อมูลคงที่ (ดู
 * `constants/schoolSystems.ts`) ⇒ ไม่มี state ไม่มี loading ไม่มี error ให้จัดการ
 * และที่สำคัญคือ **การ์ดนี้ยังขึ้นแม้ API ของ PIRIvoice ล่ม** ซึ่งเป็นสิ่งที่ต้องการ —
 * ปัญหาของระบบเราไม่ควรตัดทางออกไปหาระบบอื่นของโรงเรียน
 *
 * **ตำแหน่ง:** อยู่ *ใต้* ประกาศโรงเรียน ใน `Home.vue` — เจ้าของระบบกำหนดว่า
 * "กดง่าย ไม่อยู่ลึก แต่ไม่อยู่บนเกินจนบังสิ่งสำคัญ" ⇒ จึงไม่แย่งที่กับบล็อกที่ต้อง
 * ลงมือทำ (รอฉันตอบ / โหวต / กิจกรรมใกล้ปิดรับ) ที่ต้องอยู่บนสุดของหน้า
 *
 * ⚠️ **เปิดในแท็บเดิม ไม่มี `target="_blank"`** — เจ้าของระบบสั่งไว้ ("ตอนเปิดบนแอพ
 *    จะได้เนียนไปกับระบบเรา") ⇒ ห้ามเติม `target="_blank"` / `rel="noopener"` กลับ
 *    ด้วยความเคยชิน เพราะการติดตั้งเป็น PWA จะเปิดเป็นหน้าต่างใหม่ที่หลุดจากแอป
 *    ⇒ มือถือจะรู้สึกเหมือนถูกเตะออก และผู้ใช้กดย้อนกลับไม่ได้ตามที่คาด
 *    (มีเทสต์ล็อกไว้ว่าต้องไม่มี `target` — `__tests__/schoolSystems.spec.ts`)
 *
 * ⚠️ **ห้ามใส่ `justify-center` ที่ตัวไทล์** — สองไทล์มีจำนวนบรรทัดชื่อไม่เท่ากัน
 *    ("เว็บโรงเรียน" 1 บรรทัด vs "ระบบดูแลช่วยเหลือนักเรียน" 2 บรรทัด) ⇒ ตัวเตี้ยกว่า
 *    จะถูกจัดกึ่งกลางแล้ว **ไอคอนเยื้องกัน 8-9px** ซึ่งเห็นได้ชัด
 *
 * ⚠️ **และห้ามใส่ `flex-1 items-center` ที่ชื่อ** เพื่อไปจัดชื่อให้อยู่กลางช่องที่เหลือ
 *    (เคยลองแล้วที่ 360dp) — ผลคือไทล์สูงเท่ากันก็จริง แต่ **ชื่อสองไทล์ลอยต่างระดับกัน**
 *    ("เว็บโรงเรียน" จมลงไปอยู่กึ่งกลางช่องว่าง) ซึ่งอ่านเป็น *บั๊กการจัดวาง* ทันที
 *    ⇒ ปล่อยให้ชื่อ **ชิดใต้ไอคอนเสมอ** (`justify-start` + ไม่มี flex-1) ให้ชื่อทั้งสอง
 *    เริ่มที่ระดับเดียวกัน แล้วยอมรับว่าช่องว่างที่เหลือจะไปกองท้ายไทล์ที่ชื่อสั้นกว่า
 *    (ช่องว่างในกรอบเปล่า **สังเกตยากกว่า** ชื่อที่เยื้องกันมาก — ตัดสินจากภาพจริงที่ 360dp
 *    ทั้งสองแบบ ไม่ใช่จากความรู้สึก · บทเรียนอยู่ใน `docs/skills.md`)
 */
import AppCard from '@/components/ui/AppCard.vue'
import { EXTERNAL_NOTICE, SCHOOL_SYSTEMS } from '@/constants/schoolSystems'
</script>

<template>
  <AppCard :padded="false">
    <div class="px-4 py-4">
      <p class="text-center text-xs font-bold text-ink-2">ระบบอื่นของโรงเรียน</p>
      <p class="mt-0.5 text-center text-[12px] font-medium text-ink-3">{{ EXTERNAL_NOTICE }}</p>

      <!-- ไทล์ 2 ช่อง — ความสูงเท่ากันโดยอัตโนมัติ (grid stretch) ⇒ ไม่ต้องล็อกความสูงเอง
           และไม่ต้องมี breakpoint: ที่ 360dp ชื่อยาวสุดตก 2 บรรทัดซึ่งยังอ่านออก
           ⇒ ใช้ 2 คอลัมน์ตลอด ไม่สลับเป็น 1 คอลัมน์ (จะทำให้การ์ดสูงขึ้นโดยไม่จำเป็น)

           ⚠️ `max-w-sm mx-auto` **จำเป็น ไม่ใช่ของประดับ** — คอลัมน์เนื้อหาจริงกว้างถึง
              `max-w-7xl` ลบ sidebar 264px = ~952px ⇒ ถ้าปล่อยให้กริดเต็มความกว้าง
              ไทล์จะกลายเป็น 453×104 (แบนๆ โปร่งๆ อ่านไม่เหมือน "เมนูลัด") และไม่
              "อยู่กลางจอ" ตามที่เจ้าของระบบสั่ง · ที่ 360dp ค่านี้ไม่มีผล
              เพราะพื้นที่จริง (296px) แคบกว่า `max-w-sm` (384px) อยู่แล้ว -->
      <div class="mx-auto mt-3 grid max-w-sm grid-cols-2 gap-3">
        <a
          v-for="s in SCHOOL_SYSTEMS"
          :key="s.key"
          :href="s.url"
          class="flex min-h-[104px] flex-col items-center justify-start gap-2 rounded-control border border-line bg-canvas px-2.5 py-3 text-center transition-colors hover:border-brand/40 hover:bg-brand-tint focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2"
        >
          <span class="flex h-11 w-11 shrink-0 items-center justify-center rounded-control bg-surface text-brand">
            <i class="bi text-xl" :class="s.icon" aria-hidden="true"></i>
          </span>
          <span class="text-[13px] font-bold leading-snug text-ink-1">{{ s.label }}</span>
          <!-- ความหมายของลิงก์ต้องครบโดยไม่พึ่งสี/ไอคอน: บอกด้วยข้อความจริง
               (ทั้ง `hint` ที่อธิบายว่าไประบบไหน และการออกไปเว็บภายนอก) -->
          <span class="sr-only"> — {{ s.hint }} ({{ EXTERNAL_NOTICE }})</span>
        </a>
      </div>
    </div>
  </AppCard>
</template>
