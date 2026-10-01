<script setup lang="ts">
import { RouterLink } from 'vue-router'
import AppGroupHeader from '@/components/layout/AppGroupHeader.vue'
import AppNavRow from '@/components/layout/AppNavRow.vue'
import { useNavItems } from '@/composables/useNavItems'
import { useIdentity } from '@/composables/useIdentity'

/**
 * 🖥️ แถบข้างสำหรับเดสก์ท็อป (`lg` ขึ้นไป) — **อ่านเมนูชุดเดียวกับหน้า "เพิ่มเติม"**
 *
 * ⚠️ เดิม sidebar มี `menuItems` ของตัวเอง และ bottom sheet ก็มีของตัวเอง ⇒ เพิ่มเมนูใหม่
 *    ต้องแก้สองที่ให้ตรงกัน (และเคยไม่ตรงกันจริง) · ตอนนี้อ่าน `menuGroups` ชุดเดียวกัน
 *    ทั้งคู่ ⇒ ต่างกันแค่ *วิธีวาง* ไม่ใช่ *เนื้อหา*
 *
 * ⚠️ เลเยอร์กระจก (`backdrop-blur` + SVG `feDisplacementMap`) ถูกถอดออกทั้งชุด —
 *    เป็นงานภาพหนัก (SVG filter ทั้งหน้าจอ) ที่ทำให้ตัวหนังสือบนการ์ดอ่านยากขึ้น
 *    โดยแลกมากับความ "พรีเมียม" ที่ audit บอกว่าไม่ช่วยให้เข้าใจอะไร
 */
const nav = useNavItems()
const identity = useIdentity()

function onAction(key: string): void {
  if (key === 'logout') nav.logout()
}
</script>

<template>
  <aside
    class="hidden shrink-0 flex-col border-r border-line bg-surface lg:flex lg:w-[264px]"
  >
    <!-- แบรนด์ -->
    <div class="flex shrink-0 items-center gap-2.5 px-4 py-4">
      <RouterLink to="/app/home" class="flex items-center gap-2.5" aria-label="หน้าแรก">
        <img
          src="/logos/school-logo.png"
          alt=""
          class="h-9 w-9 rounded-control object-contain"
        />
        <span class="leading-tight">
          <span class="block text-[15px] font-bold text-ink-1">
            PIRI<span class="text-brand">voice</span>
          </span>
          <span class="block text-[11px] font-medium text-ink-3">เสียงจากชาวพิริยาลัย</span>
        </span>
      </RouterLink>
    </div>

    <!-- เมนู — กลุ่มเดียวกันกับหน้า "เพิ่มเติม" เป๊ะ -->
    <nav class="min-h-0 flex-1 overflow-y-auto overscroll-contain pb-4" aria-label="เมนูหลัก">
      <section v-for="group in nav.menuGroups.value" :key="group.key">
        <AppGroupHeader :label="group.label" tone="surface" />
        <div class="space-y-0.5 px-2">
          <AppNavRow
            v-for="item in group.items"
            :key="item.key"
            :item="item"
            :badge="nav.badgeOf(item)"
            :active="nav.isActive(item)"
            @action="onAction"
          />
        </div>
      </section>
    </nav>

    <!-- บัญชีผู้ใช้ — ตัวตน + ทางออก -->
    <div class="shrink-0 border-t border-line p-3">
      <div class="flex items-center gap-3">
        <RouterLink
          to="/app/profile"
          class="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-brand text-sm font-bold text-white"
          :aria-label="`โปรไฟล์ของ ${identity.displayName.value}`"
        >
          {{ identity.avatarChar.value }}
        </RouterLink>
        <RouterLink to="/app/profile" class="min-w-0 flex-1">
          <p class="truncate text-sm font-bold text-ink-1">{{ identity.displayName.value }}</p>
          <p class="truncate text-[11px] font-medium text-ink-2">{{ identity.roleLine.value }}</p>
        </RouterLink>
        <button
          type="button"
          aria-label="ออกจากระบบ"
          class="flex h-11 w-11 shrink-0 items-center justify-center rounded-control text-ink-2 transition-colors hover:bg-canvas hover:text-brand"
          @click="nav.logout()"
        >
          <i class="bi bi-box-arrow-right text-lg" aria-hidden="true" />
        </button>
      </div>
    </div>
  </aside>
</template>
