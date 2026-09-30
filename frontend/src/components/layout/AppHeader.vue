<script setup lang="ts">
import { RouterLink } from 'vue-router'
import IconButton from '@/components/ui/IconButton.vue'
import AppButton from '@/components/ui/AppButton.vue'
import { useAppChrome } from '@/composables/useAppChrome'
import { useIdentity } from '@/composables/useIdentity'
import { BADGE_CAP } from '@/composables/useNavItems'
import { useNotificationsStore } from '@/stores/notifications'

/**
 * 📌 หัวแถบบน — **in-flow ปกติ (`shrink-0`) ไม่ใช่ `sticky`/`absolute`**
 *
 * 🔴 **นี่คือการแก้บั๊กเชิงโครงสร้าง ไม่ใช่การเปลี่ยนสไตล์:**
 *    ของเดิมหัวแถบเป็น `absolute` ลอยทับ แล้ว `<main>` ต้องชดเชยด้วย
 *    `pt-[calc(4rem+env(safe-area-inset-top,0px))]` — **ความสูงถูกเขียนไว้ 2 ที่**
 *    ⇒ วันที่เปลี่ยนความสูงหัวแถบ (64px → 56dp) แล้วลืมแก้ `pt-` จะทับกัน 8px *เงียบ ๆ*
 *    ⇒ พอเป็น in-flow การทับกันเป็นไปไม่ได้โดยโครงสร้าง และเลขวิเศษหายไปทั้งบรรทัด
 *
 * ของที่เสียไป: effect "เนื้อหาไหลใต้แถบโปร่ง" — ซึ่ง audit สั่งให้เอาออกอยู่แล้ว
 * (บน `/app/home` เดิมปิดเลเยอร์พื้นทั้งหมด ⇒ ตัวหนังสือชนเนื้อหา)
 */
const chrome = useAppChrome()
const identity = useIdentity()
const notifications = useNotificationsStore()
</script>

<template>
  <header
    v-if="chrome.headerVisible.value"
    class="shrink-0 border-b border-line bg-surface"
    style="padding-top: env(safe-area-inset-top, 0px)"
  >
    <div class="mx-auto flex h-14 w-full max-w-7xl items-center gap-0.5 px-2 sm:px-3 lg:px-5">
      <!-- ปุ่มย้อน: แบบเดียวทั้งแอป — ไอคอน ← 44dp (เดิมมี 3 แบบต่างกันในแต่ละหน้า) -->
      <IconButton
        v-if="chrome.showBack.value"
        icon="bi-arrow-left"
        label="ย้อนกลับ"
        @click="chrome.goBack()"
      />
      <!--
        ไม่มีปุ่มย้อน (แท็บราก) ⇒ มือถือเห็นโลโก้แทนที่ว่าง
        ⚠️ ต้องห่อด้วย `<template v-else>` ไม่ใช่ใส่ `v-else` สองอันซ้อนกัน —
           `v-else` ต้องมี `v-if`/`v-else-if` นำหน้าเสมอ ตัวที่สองจึงไม่ถูกต้องตาม syntax
        🔴 เดสก์ท็อป **ไม่ต้องมีโลโก้ซ้ำ** เพราะ sidebar มีอยู่แล้ว — แต่ยังต้องกันที่ว่าง
           ไว้ให้ชื่อหน้าเยื้องเท่ากันทุกหน้า (ไม่งั้นหน้าที่ย้อนกลับได้กับหน้าแท็บราก
           จะเริ่มคนละตำแหน่ง)
      -->
      <template v-else>
        <RouterLink
          to="/app/home"
          class="flex h-11 w-11 shrink-0 items-center justify-center lg:hidden"
          aria-label="หน้าแรก"
        >
          <img
            src="/logos/school-logo.png"
            alt=""
            class="h-7 w-7 rounded-lg object-contain"
          />
        </RouterLink>
        <span class="hidden w-2 shrink-0 lg:block" aria-hidden="true" />
      </template>

      <!-- ชื่อหน้า: **ที่เดียวที่บอกว่าหน้านี้คืออะไร** (หน้าในต้องไม่ใส่ <h1> ซ้ำอีก) -->
      <h1 class="min-w-0 flex-1 truncate px-1.5 text-base font-bold text-ink-1">
        {{ chrome.title.value }}
      </h1>

      <!-- การกระทำหลักบนเดสก์ท็อป (มือถือใช้ FAB) -->
      <AppButton
        to="/app/issues/new"
        variant="secondary"
        size="sm"
        class="mr-1 hidden xl:inline-flex"
      >
        <template #icon><i class="bi bi-pencil-square" aria-hidden="true" /></template>
        แจ้งเรื่อง
      </AppButton>

      <IconButton
        to="/app/notifications"
        icon="bi-bell"
        label="การแจ้งเตือน"
        class="relative"
      >
        <span
          v-if="notifications.total > 0"
          class="absolute top-1 right-1 flex h-[18px] min-w-[18px] items-center justify-center rounded-full bg-brand px-1 text-[10px] font-bold tabular-nums text-white"
          aria-hidden="true"
        >
          {{ notifications.total > BADGE_CAP ? `${BADGE_CAP}+` : notifications.total }}
        </span>
      </IconButton>

      <!--
        ⚠️ avatar ยังอยู่ที่หัวแถบใน R0 เพราะหน้า "เพิ่มเติม" (ที่เก็บทางเข้าโปรไฟล์)
           ยังไม่เปิด — จะย้ายออกใน R1 พร้อมกับหน้า More ⇒ ห้ามลบก่อนหน้านั้น
           ไม่งั้นโปรไฟล์จะไม่มีทางเข้าเลย

        📐 `h-11 w-11` (44dp) ไม่ใช่ `h-9` (36dp) — วัดบน staging จริงแล้ว 36dp **เล็กกว่า
           เกณฑ์แตะ 44dp** ที่ R0 ตั้งไว้เอง และมันคือทางเข้าโปรไฟล์ทางเดียวบนมือถือ
           ⇒ ขนาดตรงกับโลโก้ (`h-11 w-11` ด้านซ้าย) ทำให้หัวแถบสมดุลด้วย
           ⚠️ ตัวอักษรยัง `text-[13px]` — โตช้ากว่ากรอบ ไม่งั้นตัวอักษรจะใหญ่เท่าการ์ด
      -->
      <RouterLink
        to="/app/profile"
        class="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-brand text-[13px] font-bold text-white"
        :aria-label="`โปรไฟล์ของ ${identity.displayName.value}`"
      >
        {{ identity.avatarChar.value }}
      </RouterLink>
    </div>
  </header>
</template>
