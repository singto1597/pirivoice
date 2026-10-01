<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { RouterView, useRouter, useRoute } from 'vue-router'
import type { RouteLocationRaw } from 'vue-router'
import AppHeader from '@/components/layout/AppHeader.vue'
import AppSidebar from '@/components/layout/AppSidebar.vue'
import AppBottomNav from '@/components/layout/AppBottomNav.vue'
import AppTabBar from '@/components/layout/AppTabBar.vue'
import AppFab from '@/components/layout/AppFab.vue'
import InstallPrompt from '@/components/InstallPrompt.vue'
import { useAuthStore } from '@/stores/auth'
import { useNotificationsStore } from '@/stores/notifications'
import { useAppChrome } from '@/composables/useAppChrome'
import type { FabKey } from '@/router/meta'

/**
 * 🧩 shell ของแอปหลังล็อกอิน — **เหลือหน้าที่ "ประกอบ + ส่งต่อข้อมูล" เท่านั้น**
 *
 * เดิมไฟล์นี้ 848 บรรทัด และเป็นเจ้าของ sidebar / หัวแถบ / แถบล่าง / bottom sheet
 * ทั้ง 4 อย่างพร้อมกัน ⇒ แก้ที่หนึ่งกระทบสามที่ · ตอนนี้แยกเป็น `components/layout/*`
 * และไฟล์นี้เหลือแค่การวางโครงกับ lifecycle ของ store
 *
 * 🔴 **หัวแถบเป็น in-flow ไม่ใช่ `absolute`/`sticky`** — ดูเหตุผลเต็มใน `AppHeader.vue`
 *    สรุป: ความสูงหัวแถบเคยถูกเขียนไว้ 2 ที่ (`h-16` + `pt-[calc(4rem+…)]` ที่ `<main>`)
 *    ⇒ วันที่เปลี่ยนความสูงแล้วลืมแก้ `pt-` จะทับกัน 8px *เงียบ ๆ*
 *    ⇒ in-flow ทำให้การทับกันเป็นไปไม่ได้โดยโครงสร้าง
 *
 * 🔴 **`--app-nav-h` เป็นตัวแปรเดียวที่บอกว่า "แถบล่างสูงเท่าไร"** — ทั้ง padding ล่าง
 *    ของ `<main>` และตำแหน่ง FAB อ่านจากตัวแปรนี้ ⇒ ไม่มีเลขวิเศษ 2 ที่ให้เพี้ยนจากกัน
 *    (ค่าต้องตรงกับความสูงจริงใน `AppBottomNav.vue` = 3.5rem)
 */
const authStore = useAuthStore()
const notificationsStore = useNotificationsStore()
const chrome = useAppChrome()
const router = useRouter()
const route = useRoute()

const scrollEl = ref<HTMLElement | null>(null)

// ปรับ scroll ขึ้นบนสุดทุกครั้งที่เปลี่ยนหน้า (iOS-like push)
watch(
  () => route.path,
  () => nextTick(() => scrollEl.value?.scrollTo({ top: 0 })),
)

/**
 * ➕ FAB — การกระทำหลักของหน้าปัจจุบัน
 *
 * ⚠️ ปุ่ม "สร้างกิจกรรม" ต้องเช็คสิทธิ์ **ที่นี่** ไม่ใช่ที่ `route.meta` — เพราะ `fab`
 *    ประกาศที่ `events` ซึ่งทุกคนเข้าได้ แต่การสร้างกิจกรรมเป็นของ `MANAGE_EVENTS`
 *    ⇒ ถ้าไม่กรอง นักเรียนจะเห็นปุ่ม + ที่กดแล้วได้ 403 อย่างเดียว
 */
const FAB_TARGETS: Record<FabKey, { to: RouteLocationRaw; label: string; icon: string; permission?: string }> = {
  issue: { to: { name: 'new-issue' }, label: 'แจ้งเรื่องใหม่', icon: 'bi-plus-lg' },
  event: {
    to: { name: 'event-create' },
    label: 'สร้างกิจกรรม',
    icon: 'bi-plus-lg',
    permission: 'MANAGE_EVENTS',
  },
  member: {
    to: { name: 'import-students' },
    label: 'นำเข้านักเรียน',
    icon: 'bi-plus-lg',
    permission: 'MANAGE_STUDENTS',
  },
  // ⚠️ **ไม่มี `permission` โดยเจตนา** — ข้อเสนอแนะเปิดให้ทุกคนส่ง (คนอื่นไม่ต้องรอสภา)
  //    ⇒ ต่างจาก `event`/`member` ที่ต้องกรองสิทธิ์ ไม่ใช่ลืมใส่
  //    · ไอคอนหลอดไฟ (ไม่ใช่ `+`) เพราะ "เสนอไอเดีย" ไม่ใช่ "เพิ่มรายการ" — และตรงกับ
  //      `boardTypeIcon('suggestion')` ที่ใช้หลอดไฟอยู่แล้ว ⇒ ผู้ใช้เห็นสัญลักษณ์เดียวกันทั้งแอป
  board: { to: { name: 'board-new' }, label: 'เสนอไอเดีย', icon: 'bi-lightbulb' },
}

const fab = computed(() => {
  const key = chrome.fab.value
  if (!key) return null
  const target = FAB_TARGETS[key]
  if (target.permission && !authStore.hasPermission(target.permission)) return null
  return target
})

/**
 * FAB ย่อเมื่อผู้ใช้ **เลื่อนลง** และกลับมาเมื่อเลื่อนขึ้น
 *
 * ⚠️ ไม่ย่อถาวรเมื่อ "เลื่อนพ้นระยะหนึ่ง" — ปุ่มที่หายไปแล้วไม่กลับมาคือปุ่มที่ผู้ใช้หาไม่เจอ
 *    (โดยเฉพาะ "แจ้งเรื่อง" ซึ่งเป็นงานหลักของแอป) ⇒ ผูกกับ *ทิศทาง* ไม่ใช่ *ตำแหน่ง*
 */
const fabCollapsed = ref(false)

function onScroll(): void {
  const el = scrollEl.value
  if (!el) return
  fabCollapsed.value = el.scrollTop > 96
}

onMounted(async () => {
  if (authStore.isAuthenticated) {
    try {
      await authStore.loadMe()
      // 🔔 badge อัปเดตทันที (SSE) + poll 30 วิ เป็นตาข่ายชั้นสอง — ต้องมี **ทั้งคู่**
      //    (เหตุผลอยู่ในคอมเมนต์หัว stores/notifications.ts — อย่าลบ poll ทิ้ง)
      notificationsStore.startStream()
      notificationsStore.startPolling()
    } catch {
      authStore.logout()
      router.push({ name: 'login' })
    }
  }
})

onBeforeUnmount(() => {
  // ⚠️ ปิด stream ด้วยเสมอ — ไม่งั้นแท็บเดิมยังรับ event ของผู้ใช้คนก่อนต่อ
  //    (และถ้าไม่ปิด ตอน logout/login ใหม่จะมีสตรีมซ้อนกันหลายเส้น)
  notificationsStore.stopStream()
  notificationsStore.stopPolling()
  // 🏷️ ล้างเลขบนไอคอนแอพ — badge เกาะกับ *ไอคอน* (ของเครื่อง) ไม่ใช่ *บัญชี*
  //    ⇒ ออกจากระบบแล้วต้องไม่เหลือยอดค้างของคนก่อนให้คนถัดไปเห็น (A5)
  //    ⚠️ ต้องอยู่ที่นี่ ไม่ใช่ใน `stopPolling()` — เพราะ `stopPolling()` ถูกเรียกจาก
  //    เส้นทาง "poll ล้มติดกัน 3 ครั้ง" ด้วย ซึ่งไม่ใช่การออกจากระบบ
  notificationsStore.resetBadge()
})
</script>

<template>
  <div
    class="relative flex h-[100dvh] overflow-hidden bg-canvas font-sans text-ink-1 selection:bg-brand/15 selection:text-brand"
    :style="{ '--app-nav-h': chrome.navVisible.value ? '3.5rem' : '0rem' }"
  >
    <AppSidebar />

    <!--
      🔴 คอลัมน์เนื้อหา — `min-w-0` จำเป็น ไม่ใช่ของประดับ: flex item มีค่าเริ่มต้น
         `min-width: auto` ⇒ ตาราง/โค้ดยาว ๆ จะดันคอลัมน์ให้กว้างเกินจอแทนที่จะ scroll ในตัวเอง
    -->
    <div class="relative z-10 flex min-w-0 flex-1 flex-col overflow-hidden">
      <AppHeader />
      <AppTabBar v-if="chrome.segmentGroup.value" :group="chrome.segmentGroup.value" />

      <!--
        🔴 **ห้ามเพิ่ม `overflow-x-hidden` ที่นี่หรือที่ wrapper `max-w-7xl`** —
           `overflow-x: hidden` บนบรรพบุรุษจะทำให้ `position: sticky` ของลูกหยุดทำงาน
           *เงียบ ๆ* (`skills.md` #11) ⇒ `AppGroupHeader` และ `PlaybookReader.vue` พึ่ง `sticky` อยู่
      -->
      <main
        ref="scrollEl"
        class="flex-1 overflow-y-auto overscroll-contain pb-[calc(var(--app-nav-h)+env(safe-area-inset-bottom,0px)+1rem)] lg:pb-8"
        @scroll.passive="onScroll"
      >
        <div class="mx-auto w-full max-w-7xl px-4 pt-4 sm:px-6 lg:px-8">
          <RouterView v-slot="{ Component }">
            <Transition name="page" mode="out-in" appear>
              <component :is="Component" :key="route.fullPath" />
            </Transition>
          </RouterView>
        </div>
      </main>
    </div>

    <AppFab
      v-if="fab"
      :to="fab.to"
      :label="fab.label"
      :icon="fab.icon"
      :collapsed="fabCollapsed"
    />

    <!--
      🔴 **`v-if` ไม่ใช่ `v-show`/`hidden`** — แถบที่ยังอยู่ใน DOM แต่ล่องหน *ยังกลืนคลิก*
         ⇒ ปุ่มส่งของฟอร์ม (`navHidden: true`) จะกดไม่ติด (กลไกเดียวกับ `skills.md` #9)
    -->
    <AppBottomNav v-if="chrome.navVisible.value" />

    <!-- 📱 แบนเนอร์ติดตั้ง PWA + แจ้งเวอร์ชันใหม่ (A1)
         วางไว้ที่ MainLayout ⇒ ขึ้นเฉพาะหน้าหลังล็อกอิน ไม่รบกวน Landing สาธารณะ -->
    <InstallPrompt />
  </div>
</template>

<style>
/* Page Transition นุ่มๆ */
.page-enter-active {
  transition:
    opacity 0.4s cubic-bezier(0.4, 0, 0.2, 1),
    transform 0.4s cubic-bezier(0.4, 0, 0.2, 1);
}
.page-leave-active {
  transition: opacity 0.2s ease;
}
.page-enter-from {
  opacity: 0;
  transform: translateY(16px) scale(0.99);
}
.page-leave-to {
  opacity: 0;
}

/* ♿ เคารพผู้ที่ปิดแอนิเมชัน */
@media (prefers-reduced-motion: reduce) {
  .page-enter-active,
  .page-leave-active {
    transition: none;
  }
  .page-enter-from {
    transform: none;
  }
}

/* Custom Scrollbar เล็กๆ — ซ่อนบนอุปกรณ์สัมผัส (ดู `main.css`) */
.custom-scrollbar::-webkit-scrollbar {
  width: 5px;
}
.custom-scrollbar::-webkit-scrollbar-track {
  background: transparent;
}
.custom-scrollbar::-webkit-scrollbar-thumb {
  background-color: rgba(0, 0, 0, 0.1);
  border-radius: 10px;
}
.custom-scrollbar:hover::-webkit-scrollbar-thumb {
  background-color: rgba(0, 0, 0, 0.2);
}
</style>
