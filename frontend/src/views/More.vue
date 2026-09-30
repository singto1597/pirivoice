<!-- eslint-disable vue/multi-word-component-names -- 'More' = หน้า "เพิ่มเติม" ตามชื่อแท็บที่ผู้ใช้เห็น -->
<script setup lang="ts">
import { computed } from 'vue'
import AppGroupHeader from '@/components/layout/AppGroupHeader.vue'
import AppNavRow from '@/components/layout/AppNavRow.vue'
import { useNavItems } from '@/composables/useNavItems'
import { useIdentity } from '@/composables/useIdentity'
import type { NavItem } from '@/constants/nav'

/**
 * 🗂️ หน้า "เพิ่มเติม" — **ทดแทน bottom sheet 21 แถวที่ทุกแถวน้ำหนักเท่ากัน**
 *
 * 🔴 **ทำไมต้องเป็นหน้าเต็ม ไม่ใช่ sheet:** sheet เดิม (①) หัวไม่ sticky ⇒ เลื่อนลงแล้ว
 *    ปุ่มปิดหายไป (②) 21 แถวเรียงแบน ⇒ หาไม่เจอว่าอะไรอยู่หมวดไหน (③) ปุ่ม "ออกจากระบบ"
 *    อยู่ติดกับ "แก้ไขโปรไฟล์" ⇒ กดพลาดแล้วหลุดจากระบบ
 *    ⇒ หน้านี้ตอบทั้งสามข้อ: หัวกลุ่ม sticky · จัดกลุ่ม 4 กลุ่ม · ปุ่มอันตรายแยกไปล่างสุด
 *
 * ⚠️ **เมนูอ่านจาก `useNavItems().menuGroups` ชุดเดียวกับ sidebar** — ไม่มีลิสต์ที่สอง
 *    ที่ต้องคอย sync (ของเดิม sidebar กับ sheet มีคนละลิสต์ ⇒ เคยไม่ตรงกันจริง)
 *
 * ⚠️ **กลุ่มที่ไม่มีแถวเหลือหลังกรองสิทธิ์จะถูกตัดออกทั้งกลุ่ม** (อยู่ใน `useNavItems`)
 *    ⇒ ไม่มีหัวกลุ่มลอย ๆ ที่ไม่มีอะไรอยู่ใต้มัน
 */
const nav = useNavItems()
const identity = useIdentity()

/** แถวที่เป็น *การกระทำ* (ออกจากระบบ) แยกออกจากลิสต์ แล้วไปอยู่โซนอันตรายล่างสุด */
function isAction(item: NavItem): boolean {
  return item.action !== undefined
}

const groups = computed(() =>
  nav.menuGroups.value.map((g) => ({ ...g, items: g.items.filter((i) => !isAction(i)) })),
)

/** ปุ่มอันตราย — เก็บเป็นอาร์เรย์เพราะ `noUncheckedIndexedAccess` ทำให้ `[0]` เป็น optional */
const dangerItems = computed(() =>
  nav.menuGroups.value.flatMap((g) => g.items.filter(isAction)),
)

function onAction(key: string): void {
  if (key === 'logout') nav.logout()
}

/** ปุ่มอันตราย — `item.action` เป็น `'logout' | undefined` ⇒ ต้องเช็คก่อนส่งต่อ */
function onDanger(item: NavItem): void {
  if (item.action) onAction(item.action)
}
</script>

<template>
  <div class="space-y-5 pb-4">
    <!-- ตัวตน — ทางเข้าโปรไฟล์ที่ไม่ต้องผ่านเมนู -->
    <RouterLink
      to="/app/profile"
      class="flex items-center gap-3 rounded-card border border-line bg-surface p-4 transition-colors hover:border-ink-3/40"
    >
      <span
        class="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-brand text-base font-bold text-white"
        aria-hidden="true"
      >
        {{ identity.avatarChar.value }}
      </span>
      <span class="min-w-0 flex-1">
        <span class="block truncate text-base font-bold text-ink-1">
          {{ identity.displayName.value }}
        </span>
        <span class="block truncate text-[13px] font-medium text-ink-2">
          {{ identity.roleLine.value }}
        </span>
      </span>
      <i class="bi bi-chevron-right shrink-0 text-xs text-ink-3" aria-hidden="true" />
    </RouterLink>

    <!--
      กลุ่มเมนู — หัวกลุ่ม sticky ติดขอบบนของ <main>

      🔴 **ห้ามใส่ `overflow-hidden` ที่การ์ดนี้** — มันจะทำให้ `sticky` ของหัวกลุ่ม
         หยุดทำงาน *เงียบ ๆ* เพราะ `overflow != visible` ทำให้ div นี้กลายเป็น scroll container
         ⇒ หัวกลุ่มไปติดกับ "กล่องที่ไม่มีการเลื่อน" แทนที่จะติดกับ `<main>`
         (กลไกเดียวกับ `skills.md` #11 ทุกประการ — ตรวจเจอจริงบน staging: เลื่อน 400px
         แล้วหัวกลุ่มขยับ -400px ตามเนื้อหา ไม่ได้ค้างที่ขอบบน)

      ⚠️ แต่การ์ดยังต้องมุมโค้ง ⇒ ย้ายความรับผิดชอบไปที่ `rounded-t-card` บนหัวกลุ่ม
         (พื้นหัวกลุ่มทึบ `bg-surface` ⇒ ถ้าไม่โค้ง มันจะทับมุมโค้งของการ์ดเป็นมุมเหลี่ยม)
         ส่วนมุมล่างได้จาก `rounded-card` ของการ์ดเอง — ลูกข้างในพื้นโปร่งทั้งหมด
         (แถว hover ใช้ `rounded-control` ของตัวเอง) ⇒ ไม่มีอะไรล้นออกไปให้ต้อง clip
    -->
    <div
      v-for="group in groups"
      :key="group.key"
      class="-mx-4 rounded-card border border-line bg-surface sm:mx-0"
    >
      <AppGroupHeader :label="group.label" tone="surface" class="rounded-t-card" />
      <div class="space-y-0.5 px-2 pb-2">
        <AppNavRow
          v-for="item in group.items"
          :key="item.key"
          :item="item"
          :badge="nav.badgeOf(item)"
          :active="nav.isActive(item)"
          @action="onAction"
        />
      </div>
    </div>

    <!--
      ⚠️ โซนอันตราย — **แยกออกจากเมนูหลักโดยตั้งใจ** และอยู่ล่างสุด
         ⇒ ห่างจากโซนนิ้วโป้ง (ผู้ใช้ต้องตั้งใจเลื่อนลงมา) และไม่มีอะไรอยู่ข้าง ๆ ให้กดพลาด
    -->
    <div v-if="dangerItems.length" class="space-y-2 pt-2">
      <button
        v-for="item in dangerItems"
        :key="item.key"
        type="button"
        class="flex h-12 w-full items-center justify-center gap-2 rounded-control border border-line bg-surface text-sm font-bold text-danger transition-colors hover:bg-danger/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-danger"
        @click="onDanger(item)"
      >
        <i :class="['bi', item.icon]" aria-hidden="true" />
        {{ item.label }}
      </button>
    </div>
  </div>
</template>
