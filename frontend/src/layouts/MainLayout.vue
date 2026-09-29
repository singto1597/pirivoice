<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { RouterView, RouterLink, useRouter, useRoute } from 'vue-router'
import Swal from 'sweetalert2'
import { useAuthStore } from '@/stores/auth'
import { useNotificationsStore } from '@/stores/notifications'
import PlaybookSidebarMenu from '@/components/playbooks/PlaybookSidebarMenu.vue'
import InstallPrompt from '@/components/InstallPrompt.vue'
import { PLAYBOOKS } from '@/types/playbook'

const authStore = useAuthStore()
const notificationsStore = useNotificationsStore()
const router = useRouter()
const route = useRoute()

const isMoreOpen = ref(false)
const scrollEl = ref<HTMLElement | null>(null)

// ปรับ scroll ขึ้นบนสุดทุกครั้งที่เปลี่ยนหน้า (iOS-like push)
watch(
  () => route.path,
  () => nextTick(() => scrollEl.value?.scrollTo({ top: 0 })),
)

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

const displayName = computed(() => authStore.displayName)

// ตัวอักษรตัวแรกของชื่อจริง (first_name) → avatar — ไม่เอาคำนำหน้า/ชื่อเล่น
const avatarChar = computed(() => {
  const name = authStore.user?.first_name || authStore.displayName || ''
  return name ? name.charAt(0).toUpperCase() : 'ส'
})

const roleLabel = computed(() => {
  const first = authStore.roles[0]
  const map: Record<string, string> = {
    student: 'นักเรียน',
    class_president: 'หัวหน้าห้อง',
    vice_academic: 'รองวิชาการ',
    vice_discipline: 'รองวินัย',
    vice_activity: 'รองกิจกรรม',
    vice_reception: 'รองปฏิคม',
    level_president: 'ประธานระดับ',
    level_vice_president: 'ผู้ช่วยหัวหน้าระดับ',
    council_member: 'สภานักเรียน',
    council_president: 'ประธานสภา',
    teacher_council: 'ครูสภานักเรียน',
    teacher: 'ครู',
  }
  return first ? map[first.role || ''] || first.role || 'นักเรียน' : 'นักเรียน'
})

// 📍 ตำแหน่ง/ห้องสำหรับทักทาย
const roleLine = computed(() => {
  const first = authStore.roles[0]
  if (!first) return roleLabel.value
  if (first.room_name) return `${roleLabel.value} · ${first.room_name}`
  if (first.level) return `${roleLabel.value} · ${first.level}`
  return roleLabel.value
})

const routeTitles: Record<string, string> = {
  home: 'หน้าแรก',
  dashboard: 'แดชบอร์ด',
  profile: 'โปรไฟล์',
  'my-activity': 'กิจกรรมของฉัน',
  'profile-edit': 'แก้ไขโปรไฟล์',
  'profile-password': 'เปลี่ยนรหัสผ่าน',
  'new-issue': 'แจ้งเรื่อง',
  'my-issues': 'เรื่องของฉัน',
  'received-issues': 'เรื่องที่รับ / ระดับฉัน',
  'issue-detail': 'รายละเอียดเรื่อง',
  'issue-edit': 'แก้ไขเรื่อง',
  boards: 'PIRI Boards',
  'board-detail': 'PIRI Boards',
  'board-reports': 'จัดการรายงาน',
  playbooks: 'P.R. Playbooks',
  'playbook-reader': 'อ่านหนังสือ',
  notifications: 'การแจ้งเตือน',
  users: 'จัดการสมาชิก',
  students: 'รายชื่อนักเรียน',
  'import-students': 'นำเข้านักเรียน',
  announcements: 'จัดการประกาศ',
  'academic-terms': 'ภาคเรียน',
  'audit-logs': 'บันทึกการใช้งาน',
}
const routeTitle = computed(() => routeTitles[(route.name as string) || ''] || 'PIRIvoice')

function logout() {
  isMoreOpen.value = false
  Swal.fire({
    icon: 'question',
    title: 'ออกจากระบบ?',
    showCancelButton: true,
    confirmButtonText: 'ออกจากระบบ',
    cancelButtonText: 'ยกเลิก',
  }).then((result) => {
    if (result.isConfirmed) {
      authStore.logout()
      router.push({ name: 'login' })
    }
  })
}

function unread(key: string): number {
  return notificationsStore.counts[key] || 0
}

const menuBadge = (path: string): number => {
  const g = {
    '/app/issues/mine': 'issue_mine',
    '/app/issues/received': 'issue_received',
    '/app/boards': 'board',
    '/app/boards/reports': 'report',
  } as Record<string, string>
  const group = g[path]
  return group ? notificationsStore.counts[group] || 0 : 0
}

interface NavItem {
  name: string
  path: string
  icon: string
  badge: number
}

const menuItems = computed<NavItem[]>(() => {
  const items: NavItem[] = []
  items.push({ name: 'หน้าแรก', path: '/app/home', icon: 'bi-house-door-fill', badge: 0 })
  if (authStore.hasPermission('VIEW_DASHBOARD')) {
    items.push({ name: 'แดชบอร์ด', path: '/app/dashboard', icon: 'bi-grid-1x2', badge: 0 })
  }
  items.push({ name: 'แจ้งเรื่อง', path: '/app/issues/new', icon: 'bi-pencil-square', badge: 0 })
  items.push({
    name: 'เรื่องของฉัน',
    path: '/app/issues/mine',
    icon: 'bi-file-earmark-text',
    badge: menuBadge('/app/issues/mine'),
  })
  items.push({
    name: 'PIRI Boards',
    path: '/app/boards',
    icon: 'bi-columns-gap',
    badge: menuBadge('/app/boards'),
  })
  if (authStore.hasPermission('RECEIVE_ISSUES')) {
    items.push({
      name: 'เรื่องที่รับ / ระดับฉัน',
      path: '/app/issues/received',
      icon: 'bi-inbox',
      badge: menuBadge('/app/issues/received'),
    })
  }
  if (authStore.isCouncilAuthority) {
    items.push({
      name: 'จัดการรายงาน',
      path: '/app/boards/reports',
      icon: 'bi-flag-fill',
      badge: menuBadge('/app/boards/reports'),
    })
  }
  if (authStore.hasPermission('MANAGE_STUDENTS')) {
    items.push({ name: 'จัดการสมาชิก', path: '/app/users', icon: 'bi-person-gear', badge: 0 })
    items.push({ name: 'นักเรียน', path: '/app/students', icon: 'bi-people', badge: 0 })
    items.push({
      name: 'นำเข้า Excel',
      path: '/app/students/import',
      icon: 'bi-file-earmark-arrow-up',
      badge: 0,
    })
  }
  if (authStore.hasPermission('MANAGE_ANNOUNCEMENTS')) {
    items.push({
      name: 'จัดการประกาศ',
      path: '/app/announcements',
      icon: 'bi-megaphone-fill',
      badge: 0,
    })
  }
  if (authStore.hasPermission('MANAGE_SETTINGS')) {
    items.push({
      name: 'ภาคเรียน',
      path: '/app/settings/terms',
      icon: 'bi-calendar3-range',
      badge: 0,
    })
  }
  if (authStore.hasPermission('VIEW_AUDIT_LOG')) {
    items.push({
      name: 'บันทึกการใช้งาน',
      path: '/app/audit-logs',
      icon: 'bi-clock-history',
      badge: 0,
    })
  }
  return items
})

const isActive = (path: string): boolean => {
  if (path === '/app/dashboard') return route.path === '/app/dashboard'
  if (path === '/app/home') return route.path === '/app/home'
  if (path === '/app/boards') return route.path === '/app/boards'
  return route.path.startsWith(path)
}

const goHome = () => {
  isMoreOpen.value = false
  router.push({ name: 'home' })
}
</script>

<template>
  <div
    class="relative flex h-screen overflow-hidden bg-[#F5F5F7] font-sans text-stone-900 selection:bg-[#B91C1C]/15 selection:text-[#B91C1C]"
  >
    <!-- 🟢 SVG Filter สำหรับ Liquid Glass Distortion -->
    <svg style="display: none">
      <filter
        id="glass-distortion"
        x="0%"
        y="0%"
        width="100%"
        height="100%"
        filterUnits="objectBoundingBox"
      >
        <feTurbulence
          type="fractalNoise"
          baseFrequency="0.003 0.005"
          numOctaves="1"
          seed="17"
          result="turbulence"
        />
        <feColorMatrix
          type="matrix"
          values="1 0 0 0 0  0 1 0 0 0  0 0 1 0 0  0 0 0 0.1 0"
          in="turbulence"
          result="softTurbulence"
        />
        <feDisplacementMap
          in="SourceGraphic"
          in2="softTurbulence"
          scale="10"
          xChannelSelector="R"
          yChannelSelector="G"
        />
      </filter>
    </svg>

    <!-- ============ Sidebar (Desktop ≥ lg) ============ -->
    <aside class="relative z-30 hidden flex-shrink-0 p-4 lg:block">
      <!-- 🌟 Glass Panel Sidebar -->
      <div
        class="relative flex h-full w-[290px] flex-col overflow-hidden rounded-[1.75rem] shadow-[0_8px_32px_rgba(0,0,0,0.06)] transition-all duration-500"
      >
        <!-- เลเยอร์กระจก -->
        <div
          class="absolute inset-0 z-0 backdrop-blur-2xl"
          style="filter: url(#glass-distortion); isolation: isolate"
        ></div>
        <div class="absolute inset-0 z-10 bg-white/60 supports-[backdrop-filter]:bg-white/40"></div>
        <div
          class="absolute inset-0 z-20 rounded-[1.75rem] shadow-[inset_2px_2px_1px_0_rgba(255,255,255,0.8),inset_-1px_-1px_1px_1px_rgba(255,255,255,0.3)] pointer-events-none"
        ></div>

        <!-- เนื้อหา Sidebar (z-30) -->
        <div class="relative z-30 flex h-full flex-col">
          <!-- Brand -->
          <div class="flex items-center gap-3 px-5 pb-4 pt-6">
            <RouterLink to="/app/home" class="flex items-center gap-2.5 group">
              <div
                class="flex -space-x-2 drop-shadow-md transition-transform duration-300 group-hover:scale-105"
              >
                <img
                  src="/logos/school-logo.png"
                  alt="โลโก้โรงเรียน"
                  class="h-9 w-9 rounded-xl object-contain bg-white/50 backdrop-blur-md"
                />
                <img
                  src="/logos/council-logo.png"
                  alt="โลโก้สภานักเรียน"
                  class="h-9 w-9 rounded-xl object-contain bg-white/50 backdrop-blur-md"
                />
              </div>
              <div class="leading-none">
                <span class="text-[15px] font-bold tracking-tight text-stone-900">
                  PIRI<span class="text-[#B91C1C]">voice</span>
                </span>
                <p class="mt-1 text-[10px] font-medium tracking-wide text-stone-500">
                  เสียงจากชาวพิริยาลัย
                </p>
              </div>
            </RouterLink>
          </div>

          <!-- Nav -->
          <nav class="flex-1 overflow-y-auto px-3 pb-2 custom-scrollbar">
            <p
              class="px-3 pb-2 pt-1 text-[10px] font-bold uppercase tracking-[0.18em] text-stone-400"
            >
              เมนู
            </p>
            <div class="space-y-1">
              <RouterLink
                v-for="item in menuItems"
                :key="item.path"
                :to="item.path"
                class="flex items-center gap-3 rounded-xl px-3.5 py-2.5 text-sm font-semibold transition-all duration-300"
                :class="
                  isActive(item.path)
                    ? 'bg-[#B91C1C] text-white shadow-md'
                    : 'text-stone-600 hover:bg-white/50 hover:shadow-sm hover:text-[#B91C1C]'
                "
              >
                <i :class="['bi', item.icon, 'text-[17px]']"></i>
                <span class="min-w-0 flex-1 truncate">{{ item.name }}</span>
                <span
                  v-if="item.badge > 0"
                  class="min-w-[20px] rounded-full px-1.5 py-0.5 text-center text-[10px] font-bold"
                  :class="
                    isActive(item.path) ? 'bg-white/20 text-white' : 'bg-[#B91C1C] text-white'
                  "
                >
                  {{ item.badge > 99 ? '99+' : item.badge }}
                </span>
              </RouterLink>
            </div>
            <div class="mt-3">
              <PlaybookSidebarMenu />
            </div>
          </nav>

          <!-- User footer -->
          <div class="p-3">
            <div
              class="flex items-center gap-3 rounded-xl bg-white/40 p-3 shadow-[inset_0_1px_4px_rgba(0,0,0,0.02)] backdrop-blur-md border border-white/60"
            >
              <button
                @click="goHome"
                class="h-11 w-11 shrink-0 rounded-xl bg-gradient-to-br from-[#B91C1C] to-[#991B1B] text-sm font-black text-white shadow-sm ring-2 ring-white/50 transition-transform hover:scale-105"
              >
                {{ avatarChar }}
              </button>
              <div
                class="min-w-0 flex-1 text-left cursor-pointer"
                @click="router.push({ name: 'profile' })"
              >
                <p class="truncate text-sm font-bold leading-tight text-stone-800">
                  {{ displayName }}
                </p>
                <p class="mt-0.5 truncate text-[11px] font-semibold text-stone-500">
                  {{ roleLine }}
                </p>
              </div>
              <button
                @click="logout"
                title="ออกจากระบบ"
                class="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl text-stone-500 transition-colors hover:bg-white/60 hover:text-[#B91C1C]"
              >
                <i class="bi bi-box-arrow-right text-lg"></i>
              </button>
            </div>
          </div>
        </div>
      </div>
    </aside>

    <!-- ============ Main Column (เปลี่ยนเป็น relative ให้ Header ลอยทับ) ============ -->
    <div class="relative z-10 flex min-w-0 flex-1 flex-col overflow-hidden">
      <!-- 🌟 Top App Bar (iOS Glass) -->
      <header
        class="absolute top-0 inset-x-0 z-30 shrink-0 transition-all duration-500"
        style="padding-top: env(safe-area-inset-top, 0px)"
      >
        <!-- เลเยอร์กระจก (ซ่อนที่หน้า home หากต้องการ) -->
        <div
          v-if="route.path !== '/app/home'"
          class="absolute inset-0 z-0 backdrop-blur-xl"
          style="filter: url(#glass-distortion); isolation: isolate"
        ></div>
        <div
          v-if="route.path !== '/app/home'"
          class="absolute inset-0 z-10 bg-white/50 supports-[backdrop-filter]:bg-white/30"
        ></div>
        <div
          v-if="route.path !== '/app/home'"
          class="absolute inset-0 z-20 border-b border-white/40 shadow-[0_4px_30px_rgba(0,0,0,0.03)] pointer-events-none"
        ></div>

        <div
          class="relative z-30 mx-auto flex h-16 w-full max-w-7xl items-center gap-3 px-4 lg:px-6"
        >
          <RouterLink
            to="/app/home"
            class="flex shrink-0 items-center gap-2 lg:hidden"
            aria-label="หน้าแรก"
          >
            <span
              class="relative flex h-9 w-9 items-center justify-center overflow-hidden rounded-xl bg-white/60 backdrop-blur-md border border-white/50 p-0.5 shadow-sm"
            >
              <img
                src="/logos/school-logo.png"
                alt="โลโก้โรงเรียน"
                class="h-full w-full object-contain"
              />
            </span>
          </RouterLink>

          <div class="min-w-0 flex-1">
            <h1
              class="truncate text-[15px] font-bold text-stone-900 sm:text-base lg:text-lg drop-shadow-sm"
            >
              {{ routeTitle }}
            </h1>
            <p
              class="hidden truncate text-[10px] font-semibold tracking-wide text-stone-500 sm:block lg:hidden"
            >
              {{ roleLine }}
            </p>
          </div>

          <div class="flex shrink-0 items-center gap-2">
            <RouterLink
              to="/app/issues/new"
              class="hidden items-center gap-1.5 rounded-xl bg-[#B91C1C] px-4 py-2 text-sm font-bold text-white shadow-md transition-all hover:bg-[#991B1B] hover:shadow-lg active:scale-[0.97] xl:flex"
            >
              <i class="bi bi-pencil-square"></i> แจ้งเรื่อง
            </RouterLink>

            <RouterLink
              to="/app/notifications"
              class="relative flex h-10 w-10 items-center justify-center rounded-xl text-stone-600 transition-all hover:bg-white/50 hover:shadow-sm"
            >
              <i class="bi bi-bell text-xl"></i>
              <span
                v-if="notificationsStore.total > 0"
                class="absolute -right-0.5 -top-0.5 flex h-[18px] min-w-[18px] items-center justify-center rounded-full bg-[#B91C1C] px-1 text-[10px] font-bold text-white shadow-sm ring-2 ring-white/80"
              >
                {{ notificationsStore.total > 99 ? '99+' : notificationsStore.total }}
              </span>
            </RouterLink>

            <RouterLink
              to="/app/profile"
              class="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-[#B91C1C] to-[#991B1B] text-sm font-black text-white shadow-md ring-2 ring-white/50 transition-transform hover:scale-105 active:scale-95"
            >
              {{ avatarChar }}
            </RouterLink>
          </div>
        </div>
      </header>

      <!-- Content (ให้ Main มี pt เพื่อดันเนื้อหาลงมาจาก Header ลอย) -->
      <main
        ref="scrollEl"
        class="flex-1 overflow-y-auto overscroll-contain h-full w-full custom-scrollbar pb-[calc(env(safe-area-inset-bottom,0px)+9rem)] lg:pb-8 pt-[calc(4rem+env(safe-area-inset-top,0px))]"
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

    <!-- ============ 🌟 Mobile Bottom Tab Bar (Liquid Glass) ============ -->
    <nav
      class="pointer-events-none fixed inset-x-0 bottom-0 z-40 lg:hidden"
      style="bottom: calc(env(safe-area-inset-bottom, 0px) + 0.6rem)"
      aria-label="เมนูหลัก"
    >
      <div
        class="pointer-events-auto mx-auto w-[calc(100%-1.5rem)] max-w-[440px] relative transition-transform duration-500 hover:scale-[1.01]"
      >
        <!-- เลเยอร์กระจก Bottom Bar -->
        <div
          class="absolute inset-0 z-0 overflow-hidden rounded-[2rem] backdrop-blur-xl supports-[backdrop-filter]:backdrop-blur-2xl"
          style="filter: url(#glass-distortion); isolation: isolate"
        ></div>
        <div class="absolute inset-0 z-10 rounded-[2rem] bg-white/45"></div>
        <div
          class="absolute inset-0 z-20 overflow-hidden rounded-[2rem] shadow-[inset_2px_2px_2px_0_rgba(255,255,255,0.8),inset_-1px_-1px_1px_1px_rgba(255,255,255,0.3),0_10px_40px_rgba(0,0,0,0.1)] pointer-events-none"
        ></div>

        <!-- เนื้อหาปุ่มต่างๆ (z-30) -->
        <div class="relative z-30 flex items-end justify-between px-1.5 pb-1.5 pt-2.5">
          <RouterLink
            to="/app/home"
            class="flex min-w-0 flex-1 flex-col items-center gap-0.5 rounded-2xl px-1 py-1.5 text-[10px] font-bold transition-colors"
            :class="
              route.path === '/app/home'
                ? 'text-[#B91C1C] drop-shadow-sm'
                : 'text-stone-500 hover:text-stone-700'
            "
          >
            <i
              :class="[
                'bi text-xl',
                route.path === '/app/home' ? 'bi-house-door-fill' : 'bi-house-door',
              ]"
            ></i>
            <span class="truncate">หน้าแรก</span>
          </RouterLink>

          <RouterLink
            to="/app/issues/mine"
            class="relative flex min-w-0 flex-1 flex-col items-center gap-0.5 rounded-2xl px-1 py-1.5 text-[10px] font-bold transition-colors"
            :class="
              isActive('/app/issues/mine')
                ? 'text-[#B91C1C] drop-shadow-sm'
                : 'text-stone-500 hover:text-stone-700'
            "
          >
            <span class="relative">
              <i
                :class="[
                  'bi text-xl',
                  isActive('/app/issues/mine')
                    ? 'bi-file-earmark-text-fill'
                    : 'bi-file-earmark-text',
                ]"
              ></i>
              <span
                v-if="unread('issue_mine') > 0"
                class="absolute -right-2.5 -top-1 flex h-4 min-w-[16px] items-center justify-center rounded-full bg-[#B91C1C] px-1 text-[9px] font-bold text-white shadow-sm ring-2 ring-white/60"
              >
                {{ unread('issue_mine') > 99 ? '99+' : unread('issue_mine') }}
              </span>
            </span>
            <span class="truncate">ของฉัน</span>
          </RouterLink>

          <!-- ➕ FAB กลาง -->
          <RouterLink
            to="/app/issues/new"
            class="relative flex min-w-0 flex-1 flex-col items-center gap-1 pb-0.5 text-[9px] font-bold text-[#B91C1C]"
          >
            <span
              class="-mt-5 flex h-11 w-11 items-center justify-center rounded-2xl bg-gradient-to-br from-[#B91C1C] to-[#991B1B] text-lg text-white shadow-[0_8px_16px_rgba(185,28,28,0.3)] ring-[3px] ring-white/50 transition-transform active:scale-95"
            >
              <i class="bi bi-plus-lg drop-shadow-md"></i>
            </span>
            <span class="leading-none drop-shadow-sm">แจ้งเรื่อง</span>
          </RouterLink>

          <RouterLink
            to="/app/boards"
            class="relative flex min-w-0 flex-1 flex-col items-center gap-0.5 rounded-2xl px-1 py-1.5 text-[10px] font-bold transition-colors"
            :class="
              isActive('/app/boards')
                ? 'text-[#B91C1C] drop-shadow-sm'
                : 'text-stone-500 hover:text-stone-700'
            "
          >
            <span class="relative">
              <i class="bi text-xl bi-columns-gap"></i>
              <span
                v-if="unread('board') > 0"
                class="absolute -right-2.5 -top-1 flex h-4 min-w-[16px] items-center justify-center rounded-full bg-[#B91C1C] px-1 text-[9px] font-bold text-white shadow-sm ring-2 ring-white/60"
              >
                {{ unread('board') > 99 ? '99+' : unread('board') }}
              </span>
            </span>
            <span class="truncate">Boards</span>
          </RouterLink>

          <button
            type="button"
            @click="isMoreOpen = true"
            class="flex min-w-0 flex-1 flex-col items-center gap-0.5 rounded-2xl px-1 py-1.5 text-[10px] font-bold transition-colors"
            :class="
              isMoreOpen ? 'text-[#B91C1C] drop-shadow-sm' : 'text-stone-500 hover:text-stone-700'
            "
          >
            <i :class="['bi text-xl', isMoreOpen ? 'bi-x-lg' : 'bi-grid-3x3-gap-fill']"></i>
            <span class="truncate">เพิ่มเติม</span>
          </button>
        </div>
      </div>
    </nav>

    <!-- ============ 🌟 Bottom Sheet (Glass UI) ============ -->
    <Transition name="sheet">
      <div v-if="isMoreOpen" class="fixed inset-0 z-50 lg:hidden">
        <!-- Backdrop -->
        <div
          class="absolute inset-0 bg-stone-900/30 backdrop-blur-sm transition-opacity"
          @click="isMoreOpen = false"
        ></div>

        <!-- Sheet Container (แรปเปอร์หลัก กำหนดเงาและขอบ) -->
        <div
          class="absolute inset-x-0 bottom-0 rounded-t-[2rem] shadow-[0_-10px_40px_rgba(0,0,0,0.15)]"
        >
          <!-- 1. เลเยอร์กระจก (ยึดติดขอบเสมอ ไม่ไหลตามเวลาเลื่อน) -->
          <div
            class="absolute inset-0 z-0 overflow-hidden rounded-t-[2rem] backdrop-blur-3xl bg-white/95 supports-[backdrop-filter]:bg-white/85"
          >
            <div
              class="absolute inset-0 rounded-t-[2rem] shadow-[inset_0_2px_4px_0_rgba(255,255,255,1)] pointer-events-none"
            ></div>
          </div>

          <!-- 2. เนื้อหา Sheet (ทำหน้าที่ Scroll อย่างเดียวอยู่ชั้นบนสุด) -->
          <div class="relative z-20 max-h-[86vh] overflow-y-auto pb-safe custom-scrollbar">
            <!-- Handle -->
            <div class="mx-auto mt-3 h-1.5 w-10 rounded-full bg-stone-300/80 shadow-inner"></div>

            <!-- User header -->
            <div class="flex items-center gap-3 px-6 pb-4 pt-4">
              <button
                @click="isMoreOpen = false; router.push({ name: 'profile' })"
                class="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-[#B91C1C] to-[#991B1B] text-base font-black text-white shadow-md"
              >
                {{ avatarChar }}
              </button>
              <div
                class="min-w-0 flex-1"
                @click="isMoreOpen = false; router.push({ name: 'profile' })"
              >
                <p class="truncate text-base font-bold text-stone-900">{{ displayName }}</p>
                <p class="truncate text-xs font-semibold text-stone-500">{{ roleLine }}</p>
              </div>
              <button
                @click="isMoreOpen = false"
                class="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-black/5 text-stone-600 transition-colors hover:bg-black/10"
              >
                <i class="bi bi-x-lg text-lg"></i>
              </button>
            </div>

            <div class="mx-6 h-px bg-stone-200/50"></div>

            <!-- Menu items -->
            <div class="space-y-1 px-3 py-3">
              <p
                class="px-3 pb-1 pt-1 text-[10px] font-bold uppercase tracking-[0.16em] text-stone-500"
              >
                เมนูทั้งหมด
              </p>
              <button
                v-for="item in menuItems"
                :key="item.path"
                type="button"
                @click="isMoreOpen = false; router.push(item.path)"
                class="flex w-full items-center gap-3 rounded-xl px-3.5 py-3 text-left text-sm font-semibold transition-colors"
                :class="
                  isActive(item.path)
                    ? 'bg-white/60 text-[#B91C1C] shadow-sm'
                    : 'text-stone-700 hover:bg-white/40'
                "
              >
                <i
                  :class="[
                    'bi',
                    item.icon,
                    'text-lg',
                    isActive(item.path) ? 'text-[#B91C1C]' : 'text-stone-400',
                  ]"
                ></i>
                <span class="min-w-0 flex-1 truncate">{{ item.name }}</span>
                <span
                  v-if="item.badge > 0"
                  class="min-w-[20px] rounded-full bg-[#B91C1C] px-1.5 py-0.5 text-center text-[10px] font-bold text-white shadow-sm"
                >
                  {{ item.badge > 99 ? '99+' : item.badge }}
                </span>
                <i class="bi bi-chevron-right text-xs text-stone-300"></i>
              </button>
            </div>

            <!-- 📖 Playbooks -->
            <div class="mx-6 h-px bg-stone-200/50"></div>
            <div class="px-3 py-3">
              <div class="flex items-center justify-between px-3 pb-1">
                <p class="text-[10px] font-bold uppercase tracking-[0.16em] text-stone-500">
                  P.R. Playbooks
                </p>
                <button
                  type="button"
                  class="text-[11px] font-bold text-[#B91C1C]"
                  @click="isMoreOpen = false; router.push({ name: 'playbooks' })"
                >
                  ดูทั้งหมด
                </button>
              </div>
              <div class="space-y-0.5">
                <button
                  v-for="pb in PLAYBOOKS"
                  :key="pb.id"
                  @click="isMoreOpen = false; router.push({ name: 'playbook-reader', params: { id: pb.id } })"
                  class="flex w-full items-center gap-3 rounded-xl px-3 py-2 text-left text-sm font-semibold text-stone-700 transition-colors hover:bg-white/40 hover:text-[#B91C1C]"
                >
                  <span
                    class="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-black/5 text-stone-600"
                    ><i class="bi bi-journal-bookmark text-sm"></i
                  ></span>
                  <span class="truncate">{{ pb.title }}</span>
                </button>
              </div>
            </div>

            <!-- Account -->
            <div class="mx-6 h-px bg-stone-200/50"></div>
            <div class="grid grid-cols-2 gap-2 px-6 py-4">
              <button
                @click="isMoreOpen = false; router.push({ name: 'profile-edit' })"
                class="flex items-center gap-2 rounded-xl bg-white/40 px-3 py-3 text-sm font-semibold text-stone-700 hover:bg-white/60"
              >
                <i class="bi bi-person-badge text-base"></i> แก้ไขโปรไฟล์
              </button>
              <button
                @click="isMoreOpen = false; router.push({ name: 'profile-password' })"
                class="flex items-center gap-2 rounded-xl bg-white/40 px-3 py-3 text-sm font-semibold text-stone-700 hover:bg-white/60"
              >
                <i class="bi bi-key text-base"></i> เปลี่ยนรหัสผ่าน
              </button>
              <button
                @click="logout"
                class="col-span-2 flex w-full items-center justify-center gap-2 rounded-xl bg-stone-800/5 py-3 text-sm font-bold text-[#B91C1C] transition-colors hover:bg-stone-800/10"
              >
                <i class="bi bi-box-arrow-right text-base"></i> ออกจากระบบ
              </button>
            </div>
          </div>
        </div>
      </div>
    </Transition>

    <!-- 📱 แบนเนอร์ติดตั้ง PWA + แจ้งเวอร์ชันใหม่ (A1)
         วางไว้ที่ MainLayout ⇒ ขึ้นเฉพาะหน้าหลังล็อกอิน ไม่รบกวน Landing สาธารณะ -->
    <InstallPrompt />
  </div>
</template>

<style scoped>
/* fade สำหรับ backdrop + slide สำหรับ sheet */
.sheet-enter-active,
.sheet-leave-active {
  transition: opacity 0.3s ease;
}
.sheet-enter-active .absolute.inset-x-0,
.sheet-leave-active .absolute.inset-x-0 {
  transition: transform 0.4s cubic-bezier(0.175, 0.885, 0.32, 1);
}
.sheet-enter-from,
.sheet-leave-to {
  opacity: 0;
}
.sheet-enter-from .absolute.inset-x-0,
.sheet-leave-to .absolute.inset-x-0 {
  transform: translateY(100%);
}

@media (prefers-reduced-motion: reduce) {
  .sheet-enter-active,
  .sheet-leave-active {
    transition: none !important;
  }
}
</style>

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

/* Custom Scrollbar เล็กๆ ซ่อนตัวได้เนียนๆ กับดีไซน์กระจก */
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
