<!-- eslint-disable vue/multi-word-component-names -- ชื่อตาม route/spec -->
<script setup lang="ts">
/**
 * 👤 โปรไฟล์ — "ฉันเป็นใคร" (อ่านเป็นหลัก)
 *
 * ⭐ **แยกออกจาก `Settings.vue` โดยเจตนา** (R3.3) — เดิมไฟล์นี้บรรจุทั้ง *ตัวตน* และ
 *    *การตั้งค่า* ปนกัน ⇒ คนที่เปิดมาดูชื่อ/ห้องตัวเองต้องเลื่อนผ่านสวิตช์ 5 ตัว
 *    หน้าตั้งค่าย้ายไป `/app/settings` แล้ว ⇒ **หนึ่งหน้า หนึ่งงานหลัก**
 *
 * 🔴 **ไม่มีเมนู `⋮` ที่นี่อีกแล้ว — และนั่นคือประเด็นของ R3.3** เดิมมุมขวาบนมี dropdown
 *    ที่บรรจุ *แก้ไขโปรไฟล์ · เปลี่ยนรหัสผ่าน · ออกจากระบบ* ซึ่งเป็น **ทางเข้าชุดที่สอง
 *    ของปลายทางเดียวกัน** กับกลุ่ม "บัญชี" ในหน้า More (R1) — สิ่งที่ผู้ใช้เรียกว่า
 *    "เยอะเกินไป" คือของแบบนี้พอดี
 *
 *    ⚠️ แต่ `profile-edit` และ `profile-password` เป็น `hiddenFromMenu: true` ใน
 *       `constants/nav.ts` ⇒ **ถอด dropdown ทิ้งเฉย ๆ จะทำให้สอง route นั้นไม่มีทางเข้าเลย**
 *       จึงต้องมีที่อยู่ใหม่ครบทั้งคู่ (นี่คือเหตุผลที่ทั้งสองบรรทัดถัดจากนี้มีอยู่):
 *         · "แก้ไขโปรไฟล์"  → ปุ่มเดียวในหน้านี้ (งานหลักของหน้านี้คือ *ดู* แล้ว *แก้*)
 *         · "เปลี่ยนรหัสผ่าน" → **อยู่ที่หน้าตั้งค่า** เพราะเป็นเรื่อง credential/บัญชี
 *           ไม่ใช่ตัวตน ⇒ ไม่ยัดกลับมาที่นี่เพื่อความสมมาตร
 *
 * 🔴 **ห้ามใส่ `<h1>` ในไฟล์นี้** — `<h1>` ของหน้าอยู่ที่ `AppHeader` แล้ว (R0.3)
 *    ⇒ ชื่อผู้ใช้ใช้ `<h2>` ซึ่งเป็น "หัวเรื่องของการ์ด" ใบเดียวกับที่การ์ดอื่นใช้
 */
import { ref, onMounted, computed } from 'vue'
import { getMyProfile, type MyProfile } from '@/services/profile'
import { getMyStats } from '@/services/me'
import type { PersonalStats } from '@/types/me'
import { avatarCharOf } from '@/utils/avatar'
import { roleLabel as roleLabelOf } from '@/constants/roles'
import PersonalStatsCard from '@/components/PersonalStatsCard.vue'
import AppCard from '@/components/ui/AppCard.vue'
import AppButton from '@/components/ui/AppButton.vue'
import AppEmptyState from '@/components/ui/AppEmptyState.vue'

const profile = ref<MyProfile | null>(null)
const isLoading = ref(true)
const hasError = ref(false)

// 🪪 ป้ายตำแหน่งมาจาก `@/constants/roles` ที่เดียว (เดิมคัดลอกไว้ 4 ที่แล้วเลื่อนออกจากกัน)


/**
 * ตัวอักษรใน avatar — ใช้ `avatarCharOf()` จาก `@/utils/avatar` **ไม่ใช่ `charAt(0)`**
 *
 * 🐛 ของเดิมเป็น `name.charAt(0).toUpperCase()` ⇒ "แอดมิน" ได้ **"แ"** ซึ่งเป็น *สระนำหน้า*
 *    ลอย ๆ ที่อ่านไม่ออก (ต้องมีพยัญชนะฐานต่อท้าย) — ผู้ใช้เห็นเป็นตัวอักษรแปลก ๆ
 *    ในวงกลมของตัวเองโดยไม่รู้ว่ามันคือบั๊ก · helper ตัวนี้แก้เรื่องนั้นแล้วและมีเทสต์คุม
 *    ⚠️ และ **อย่าเขียนตรรกะนี้ซ้ำที่นี่** — `useIdentity` (ผู้ใช้ปัจจุบัน) ใช้ตัวเดียวกัน
 *       ⇒ แก้ที่เดียวต้องมีผลทั้งสองที่
 */
const avatarChar = computed(() =>
  avatarCharOf(profile.value?.first_name || profile.value?.username),
)

/**
 * ชื่อที่แสดง — ประกอบจาก prefix/first_name/last_name เป็นหลัก
 *
 * 🔴 **ห้ามตัด fallback `full_name` ทิ้ง** — `first_name`/`last_name` เป็น `''` (ไม่ใช่ `null`)
 *    สำหรับผู้ใช้ที่ยังไม่เคยแก้โปรไฟล์ ⇒ `[..].filter(Boolean).join(' ')` ได้ **สตริงว่าง**
 *    แล้วหัวเรื่องที่ใหญ่ที่สุดของหน้านี้จะ **ว่างเปล่า** — หน้าที่มีคำถามเดียวว่า "ฉันเป็นใคร"
 *    ตอบไม่ได้ · `users.full_name` มีค่าอยู่แล้วและ backend ส่งมาใน `MyProfileOut.full_name`
 *    (เจอจริงบน staging: บัญชีที่ seed ตรงเข้า DB ผ่าน `first_name=''` ทั้งคู่)
 *    ⚠️ และไม่ใช่ regression ของ R3.3 — เวอร์ชันก่อนหน้าก็เขียนแบบเดียวกัน
 */
const fullName = computed(() => {
  const p = profile.value
  if (!p) return ''
  return (
    [p.prefix, p.first_name, p.last_name].filter(Boolean).join(' ').trim() ||
    p.full_name ||
    p.username
  )
})

const roleLabel = computed(() => {
  const r = profile.value?.class_role || ''
  return roleLabelOf(r) || 'สมาชิก'
})

async function load() {
  isLoading.value = true
  hasError.value = false
  try {
    profile.value = await getMyProfile()
  } catch {
    // ⚠️ ไม่เด้ง Swal ที่นี่ — กล่อง error ในการ์ดมีปุ่ม "ลองใหม่" ของตัวเองอยู่แล้ว
    //    การเด้งทั้ง Swal และกล่อง = บอกผู้ใช้สองครั้งเรื่องเดียวกัน
    hasError.value = true
  } finally {
    isLoading.value = false
  }
}
onMounted(load)

// แถวข้อมูลส่วนตัว (icon + label + value) — กันเบียด/ตัดคำบนจอเล็ก
const infoRows = computed(() => {
  const p = profile.value
  if (!p) return []
  const rows: { icon: string; label: string; value: string }[] = [
    { icon: 'bi-person-badge', label: 'รหัสนักเรียน', value: p.student_id },
    { icon: 'bi-hash', label: 'เลขที่', value: p.student_no ? String(p.student_no) : '-' },
    { icon: 'bi-emoji-smile', label: 'ชื่อเล่น', value: p.nickname || '-' },
    { icon: 'bi-telephone', label: 'เบอร์โทร', value: p.phone_number || '-' },
    { icon: 'bi-envelope', label: 'อีเมล', value: p.email || '-' },
    {
      icon: 'bi-door-closed',
      label: 'ห้องเรียน',
      value: p.room_code ? `${p.room_code}${p.level ? ` (${p.level})` : ''}` : '-',
    },
  ]
  // ชื่อผู้ใช้ (login) — แสดงเฉพาะเมื่อต่างจากรหัสนักเรียน (เช่น admin/ครู ที่ใช้ username ยาว)
  if (p.username && p.username !== p.student_id) {
    rows.push({ icon: 'bi-person-vcard', label: 'ชื่อผู้ใช้', value: p.username })
  }
  return rows
})

// ===== 📊 สถิติของฉัน (C3) =====
// โหลดแยกจากการ์ดอื่นโดยเจตนา — ถ้า /api/me/stats ล่ม ผู้ใช้ยังเห็นโปรไฟล์ได้
const stats = ref<PersonalStats | null>(null)
const statsLoading = ref(true)
const statsError = ref(false)

async function loadStats() {
  statsLoading.value = true
  statsError.value = false
  try {
    stats.value = await getMyStats()
  } catch {
    // ไม่เด้ง Swal — การ์ดมีปุ่ม "ลองใหม่" ของตัวเองอยู่แล้ว
    statsError.value = true
  } finally {
    statsLoading.value = false
  }
}
onMounted(loadStats)
</script>

<template>
  <div class="mx-auto max-w-3xl space-y-4 pb-4">
    <!-- Loading skeleton -->
    <div v-if="isLoading" class="space-y-4" aria-busy="true">
      <AppCard :padded="false">
        <div class="h-28 animate-pulse rounded-t-card bg-canvas sm:h-36"></div>
        <div class="px-5 py-6 sm:px-8">
          <div class="flex items-center gap-4">
            <div class="h-16 w-16 animate-pulse rounded-card bg-canvas sm:h-20 sm:w-20"></div>
            <div class="flex-1 space-y-2.5">
              <div class="h-5 w-52 animate-pulse rounded bg-canvas"></div>
              <div class="h-4 w-32 animate-pulse rounded bg-canvas"></div>
            </div>
          </div>
        </div>
      </AppCard>
      <AppCard :padded="false" class="p-6 sm:p-8">
        <div class="mb-6 h-5 w-28 animate-pulse rounded bg-canvas"></div>
        <div class="grid gap-x-8 gap-y-5 sm:grid-cols-2">
          <div v-for="i in 6" :key="i" class="flex items-center gap-3">
            <div class="h-9 w-9 animate-pulse rounded-control bg-canvas"></div>
            <div class="flex-1 space-y-2">
              <div class="h-3 w-20 animate-pulse rounded bg-canvas"></div>
              <div class="h-4 w-32 animate-pulse rounded bg-canvas"></div>
            </div>
          </div>
        </div>
      </AppCard>
    </div>

    <!-- Error + retry — 「ไม่มีการ์ดเส้นประ」 (R0: empty state ห้ามใช้ border-dashed) -->
    <AppCard v-else-if="hasError" :padded="false" class="py-4">
      <AppEmptyState
        icon="bi-person-exclamation"
        title="ไม่สามารถโหลดโปรไฟล์ได้ในขณะนี้"
        description="ตรวจสอบการเชื่อมต่อแล้วลองอีกครั้ง"
      >
        <AppButton variant="secondary" @click="load">
          <template #icon><i class="bi bi-arrow-clockwise" aria-hidden="true" /></template>
          ลองใหม่
        </AppButton>
      </AppEmptyState>
    </AppCard>

    <template v-else-if="profile">
      <!-- ===== การ์ดหลัก: ตัวตน ===== -->
      <AppCard :padded="false">
        <!-- แถบพื้นหลังบาง ๆ ให้ avatar มีที่ยืน — ไม่ใช่ภาพ ไม่ใช่ gradient (R0: สงบ) -->
        <div class="h-24 rounded-t-card border-b border-line bg-canvas sm:h-28"></div>

        <div class="px-4 pb-5 sm:px-6 sm:pb-6">
          <div class="flex items-start gap-3 sm:gap-4">
            <!-- avatar: `-mt` อย่างเดียว เพื่อให้ทับแถบพื้น โดยไม่ดึงชื่อขึ้นไปด้วย -->
            <div class="-mt-10 shrink-0 sm:-mt-12">
              <div
                class="flex h-16 w-16 items-center justify-center rounded-card bg-brand text-2xl font-bold text-white ring-2 ring-surface sm:h-20 sm:w-20 sm:text-3xl"
              >
                {{ avatarChar }}
              </div>
            </div>
            <!-- ชื่อ + ป้าย: `pt` ชัดเจน ⇒ อยู่ใต้แถบพื้น บนพื้นขาว อ่านง่ายเสมอ -->
            <div class="min-w-0 flex-1 pt-3 sm:pt-4">
              <h2 class="text-2xl leading-snug font-bold break-words text-ink-1">{{ fullName }}</h2>
              <div class="mt-2.5 flex flex-wrap gap-1.5">
                <span class="rounded-full bg-brand/10 px-2.5 py-1 text-xs font-semibold text-brand">
                  <i class="bi bi-mortarboard mr-1" aria-hidden="true" />{{ roleLabel }}
                </span>
                <span
                  v-if="profile.staff_level"
                  class="rounded-full bg-canvas px-2.5 py-1 text-xs font-semibold text-ink-2"
                >
                  <i class="bi bi-clipboard-check mr-1" aria-hidden="true" />ระดับ
                  {{ profile.staff_level }}
                </span>
                <span
                  v-if="profile.room_code"
                  class="rounded-full bg-canvas px-2.5 py-1 text-xs font-medium text-ink-2"
                >
                  <i class="bi bi-door-closed mr-1" aria-hidden="true" />{{ profile.room_code }}
                </span>
              </div>
            </div>
          </div>
        </div>
      </AppCard>

      <!-- ===== ข้อมูลส่วนตัว ===== -->
      <AppCard :padded="false" class="p-6 sm:p-8">
        <div class="mb-5 flex items-center gap-3">
          <span
            class="flex h-10 w-10 shrink-0 items-center justify-center rounded-control bg-canvas text-ink-2"
            aria-hidden="true"
          >
            <i class="bi bi-person-lines-fill" />
          </span>
          <div class="min-w-0">
            <h2 class="text-lg font-bold text-ink-1">ข้อมูลส่วนตัว</h2>
            <p class="mt-0.5 text-xs text-ink-2">ข้อมูลและช่องทางการติดต่อของคุณ</p>
          </div>
        </div>
        <div class="grid gap-x-6 gap-y-3 sm:grid-cols-2">
          <div
            v-for="row in infoRows"
            :key="row.label"
            class="flex min-w-0 items-center gap-3 py-1.5"
          >
            <span
              class="flex h-9 w-9 shrink-0 items-center justify-center rounded-control bg-canvas text-ink-2"
              aria-hidden="true"
            >
              <i :class="['bi', row.icon]" />
            </span>
            <div class="min-w-0">
              <p class="text-[11px] leading-tight font-medium text-ink-2">{{ row.label }}</p>
              <p class="text-sm leading-snug font-semibold break-words text-ink-1">
                {{ row.value }}
              </p>
            </div>
          </div>
        </div>
      </AppCard>

      <!-- ===== 📊 สถิติของฉัน (C3) ===== -->
      <PersonalStatsCard
        :stats="stats"
        :loading="statsLoading"
        :error="statsError"
        @retry="loadStats"
      />

      <!-- ===== 🧭 กิจกรรมของฉัน + บันทึกไว้ (C1/C2) ===== -->
      <!-- ⚠️ การ์ดทั้งใบเป็นทางเข้าเดียว ⇒ ใช้ `AppCard interactive` ไม่ใช่ปุ่มซ้อนในปุ่ม -->
      <AppCard :padded="false" interactive class="p-6 sm:p-8">
        <RouterLink
          :to="{ name: 'my-activity' }"
          class="flex items-center justify-between gap-3 rounded-control focus-visible:ring-2 focus-visible:ring-brand focus-visible:outline-none"
        >
          <div class="flex min-w-0 items-center gap-3">
            <span
              class="flex h-10 w-10 shrink-0 items-center justify-center rounded-control bg-canvas text-ink-2"
              aria-hidden="true"
            >
              <i class="bi bi-clock-history" />
            </span>
            <div class="min-w-0">
              <h2 class="text-lg font-bold text-ink-1">กิจกรรมของฉัน</h2>
              <p class="mt-1 text-sm text-ink-2">
                ทุกอย่างที่คุณเคยแจ้ง โหวต และแสดงความคิดเห็น · พร้อมเรื่องที่บันทึกไว้
              </p>
            </div>
          </div>
          <i class="bi bi-chevron-right shrink-0 text-ink-3" aria-hidden="true" />
        </RouterLink>
      </AppCard>

      <!-- 🎯 งานหลักของหน้านี้ — ปุ่มเดียว อยู่ล่างสุดของเนื้อหา (โซนนิ้วโป้งบนมือถือ) -->
      <AppButton variant="secondary" block :to="{ name: 'profile-edit' }">
        <template #icon><i class="bi bi-pencil-square" aria-hidden="true" /></template>
        แก้ไขโปรไฟล์
      </AppButton>
    </template>
  </div>
</template>
