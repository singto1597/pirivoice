<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import { useNavItems } from '@/composables/useNavItems'
import type { NavKey } from '@/router/meta'

/**
 * 📱 แถบนำทางล่าง — **ติดขอบล่างเต็มความกว้าง 5 ช่อง** (เดิมเป็นแคปซูลลอย + FAB กลางยื่นขึ้น)
 *
 * 🔴 **"แจ้งเรื่อง" ไม่ใช่แท็บแล้ว** — เป็น FAB (`AppFab`) เพราะเป็นการ *กระทำ* ไม่ใช่ *สถานที่*
 *    การเป็นแท็บทำให้มี 6 ช่องบนจอ 360dp (ช่องละ 60dp ซึ่งแคบกว่าปลายนิ้วโป้ง)
 *
 * 🔴 **ต้อง `v-if` (unmount) เมื่อซ่อน ไม่ใช่ซ่อนด้วย CSS** — บนฟอร์ม (`meta.navHidden`)
 *    แถบที่ยังอยู่ใน DOM แต่ล่องหน *ยังกลืนคลิก* ⇒ ปุ่มส่งของฟอร์มจะกดไม่ติด
 *    (กลไกเดียวกับ `skills.md` #9) ⇒ พ่อต้อง `v-if` ไม่ใช่ `v-show`/`hidden`
 *
 * ⚠️ ความสูงต้องตรงกับ `--app-nav-h` ที่ `MainLayout` ประกาศ (3.5rem = 56px) — ตัวแปรนั้น
 *    ใช้ทั้งดัน padding ของเนื้อหา และตำแหน่ง FAB ⇒ แก้ที่นี่ต้องแก้ที่นั่น
 */
const nav = useNavItems()

const items = computed(() =>
  nav.tabs.value.map((tab) => ({
    key: tab.key,
    label: tab.label,
    to: tab.to,
    icon: nav.activeTab.value === tab.key ? tab.iconActive : tab.icon,
    badge: nav.tabBadge(tab),
  })),
)

function isCurrent(key: NavKey): boolean {
  return nav.activeTab.value === key
}
</script>

<template>
  <nav
    class="absolute inset-x-0 bottom-0 z-40 border-t border-line bg-surface pb-[env(safe-area-inset-bottom,0px)] lg:hidden"
    aria-label="เมนูหลัก"
  >
    <div class="flex h-14 items-stretch">
      <RouterLink
        v-for="item in items"
        :key="item.key"
        :to="item.to"
        class="flex min-w-0 flex-1 flex-col items-center justify-center gap-0.5 transition-colors"
        :class="isCurrent(item.key) ? 'text-brand' : 'text-ink-3'"
        :aria-current="isCurrent(item.key) ? 'page' : undefined"
      >
        <span class="relative">
          <i :class="['bi', item.icon, 'text-xl']" aria-hidden="true" />
          <span
            v-if="item.badge > 0"
            class="absolute -top-1.5 -right-2.5 flex h-4 min-w-[16px] items-center justify-center rounded-full bg-brand px-1 text-[10px] font-bold tabular-nums text-white"
            aria-hidden="true"
          >
            {{ nav.badgeLabel(item.badge) }}
          </span>
        </span>
        <span class="max-w-full truncate text-[11px] font-semibold">{{ item.label }}</span>
      </RouterLink>
    </div>
  </nav>
</template>
