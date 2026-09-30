<!-- eslint-disable vue/multi-word-component-names -- ชื่อตาม route/spec -->
<script setup lang="ts">
/**
 * ⚙️ ตั้งค่า — "เครื่องนี้/บัญชีนี้ จะรับอะไร"
 *
 * ⭐ **แยกออกจาก `Profile.vue` โดยเจตนา** — เดิมไฟล์เดียวบรรจุทั้ง *ตัวตน* (ชื่อ/ห้อง/บทบาท/
 *    สถิติ) และ *การตั้งค่า* (กลุ่มแจ้งเตือน/push/ช่วงเวลาเงียบ/ติดตั้งแอป) ปนกัน
 *    ⇒ ผู้ใช้ที่เปิดมาดู "ฉันเป็นใคร" ต้องเลื่อนผ่านสวิตช์ 5 ตัว และคนที่มาปิดแจ้งเตือน
 *    ต้องเลื่อนผ่านสถิติ ⇒ **หนึ่งหน้า หนึ่งงานหลัก**
 *
 * 🔴 **ไม่มีปุ่ม "ออกจากระบบ" ที่นี่ — และนั่นถูกต้อง** อย่าเพิ่มกลับ
 *    มันย้ายไปอยู่โซนอันตรายล่างสุดของหน้า "เพิ่มเติม" แล้ว (R1) ซึ่งเป็นที่ที่ห่างนิ้วโป้ง
 *    ตามหลักข้อ 5 ของแผน ⇒ ใส่ที่นี่อีก = **ทางเข้า 2 ทางต่อปลายทางเดียว** ซึ่งเป็น
 *    สิ่งที่ทั้ง refactor นี้กำลังเก็บกวาด
 *
 * 🔴 **ไม่มีแถว "ธีม"** — dark mode ถูกเลื่อนออกจากชุดนี้โดยมติ (คำถามข้อ 3)
 *    ⇒ อย่าใส่สวิตช์ที่กดแล้วไม่มีอะไรเกิดขึ้น
 */
import { ref, onMounted, computed } from 'vue'
import Swal from 'sweetalert2'
import { BRAND } from '@/constants/brand'
import { getNotificationPreferences, updateNotificationPreferences } from '@/services/notification'
import { PREFERENCE_GROUPS, GROUP_DESCRIPTIONS, type NotificationGroup } from '@/types/notification'
import PushSettingsCard from '@/components/PushSettingsCard.vue'
import QuietHoursCard from '@/components/QuietHoursCard.vue'
import AppCard from '@/components/ui/AppCard.vue'
import {
  canPromptInstall,
  installDiagnostics,
  installHint,
  installNow,
  isIosSafari,
  isStandalone,
} from '@/pwa'

// ===== 📱 ติดตั้งแอป =====
// ⚠️ การ์ดนี้คือ **ทางกลับมา** ของคนที่เคยกด ✕ ปิดแบนเนอร์ติดตั้งไว้ — แบนเนอร์จำการปิด
//    แล้วไม่ขึ้นอีก ส่วนการ์ดนี้ไม่ผูกกับค่านั้น เพราะการที่ผู้ใช้เปิดมาหาเองคือการเปลี่ยนใจ
const installing = ref(false)

/**
 * แถวข้อมูลวินิจฉัย — แสดงเฉพาะในกิ่ง "ติดตั้งอัตโนมัติไม่ได้"
 *
 * ใช้คำว่า "ใช่/ไม่" ไม่ใช่ true/false เพราะคนที่อ่านเป็นผู้ใช้ทั่วไป ไม่ใช่ช่าง
 * ⚠️ `installDiagnostics` เป็น `computed` ⇒ ค่าจะอัปเดตเองเมื่อสถานะเปลี่ยน
 *    (เช่นผู้ใช้กดปิดแบนเนอร์ระหว่างเปิดหน้านี้อยู่)
 */
const diagRows = computed(() => {
  const d = installDiagnostics.value
  return [
    { label: 'เปิดในโหมดแอพแล้ว', on: d.standalone },
    { label: 'เบราว์เซอร์พร้อมติดตั้ง', on: d.promptReady },
    { label: 'ตัวช่วยแอพทำงาน (SW)', on: d.swRegistered },
    { label: 'เคยกดปิดแบนเนอร์', on: d.dismissed },
    { label: 'เครื่องนี้เคยติดตั้งมาก่อน', on: d.installedBefore },
  ]
})

async function onInstall() {
  if (installing.value) return
  installing.value = true
  try {
    const outcome = await installNow()
    if (outcome === 'accepted') {
      await Swal.fire({
        icon: 'success',
        title: 'ติดตั้งแล้ว',
        text: 'เปิด PIRIvoice ได้จากไอคอนบนหน้าจอเลย',
        confirmButtonColor: BRAND,
      })
    } else if (outcome === 'unavailable') {
      await Swal.fire({
        icon: 'info',
        title: 'เครื่องนี้ติดตั้งอัตโนมัติไม่ได้',
        text: 'เปิดด้วย Chrome แล้วเลือก "ติดตั้งแอป" จากเมนู ⋮ มุมขวาบน',
        confirmButtonColor: BRAND,
      })
    }
  } finally {
    installing.value = false
  }
}

// ===== ⚙️ ตั้งค่าการแจ้งเตือนรายกลุ่ม =====
// สร้างคีย์จาก PREFERENCE_GROUPS → ไม่ต้องพิมพ์ชื่อกลุ่มซ้ำในไฟล์นี้
// ค่าตั้งต้น = เปิดหมด (ตรงกับ backend: "ไม่มีแถว = เปิด")
const prefs = ref<Record<string, boolean>>(
  Object.fromEntries(PREFERENCE_GROUPS.map((g) => [g.value, true])),
)
const prefsLoading = ref(true)
const prefsError = ref(false)
const savingGroup = ref<NotificationGroup | null>(null)

// คีย์ที่ไม่มี = เปิด (ตรงกับ backend) — และกัน noUncheckedIndexedAccess ที่ทำให้เป็น boolean|undefined
const isOn = (group: NotificationGroup): boolean => prefs.value[group] ?? true

async function loadPrefs() {
  prefsLoading.value = true
  prefsError.value = false
  try {
    const res = await getNotificationPreferences()
    const next = { ...prefs.value }
    for (const p of res.preferences) next[p.group_type] = p.enabled
    prefs.value = next
  } catch {
    // ไม่เด้ง Swal ตอนเปิดหน้า (กวนเกินไป) — โชว์ในตัวการ์ดพร้อมปุ่มลองใหม่แทน
    prefsError.value = true
  } finally {
    prefsLoading.value = false
  }
}
onMounted(loadPrefs)

async function toggleGroup(group: NotificationGroup) {
  const next = !isOn(group)

  // ปิดกลุ่ม "เรื่องของฉัน" = เงียบเมื่อเรื่องที่ตัวเองแจ้งมีความเคลื่อนไหว → ถามก่อน
  if (!next && group === 'issue_mine') {
    const res = await Swal.fire({
      icon: 'warning',
      title: 'ปิดการแจ้งเตือนเรื่องของฉัน?',
      text: 'คุณจะไม่รู้เมื่อเรื่องที่คุณแจ้งไว้ถูกตอบกลับ หรือมีการเปลี่ยนสถานะ',
      showCancelButton: true,
      confirmButtonText: 'ปิดการแจ้งเตือน',
      cancelButtonText: 'ยกเลิก',
      confirmButtonColor: BRAND,
    })
    if (!res.isConfirmed) return
  }

  const prev = isOn(group)
  prefs.value[group] = next // optimistic — กดแล้วต้องเห็นผลทันที
  savingGroup.value = group
  try {
    await updateNotificationPreferences([{ group_type: group, enabled: next }])
  } catch (e: unknown) {
    prefs.value[group] = prev // ยิงไม่ผ่าน → คืนค่าที่ถูกต้องให้ผู้ใช้เห็น
    Swal.fire({
      icon: 'error',
      title: 'บันทึกไม่สำเร็จ',
      text: e instanceof Error ? e.message : 'เกิดข้อผิดพลาด กรุณาลองใหม่',
    })
  } finally {
    savingGroup.value = null
  }
}
</script>

<template>
  <div class="mx-auto max-w-3xl space-y-4 pb-4">
    <!--
      ⚠️ **หน้านี้ไม่ใช้ `AppGroupHeader`** — ต่างจากหน้า More และหน้าการแจ้งเตือน
         เพราะการ์ดที่นำมาประกอบ (`PushSettingsCard` · `QuietHoursCard`) **มีหัวเรื่อง
         และกรอบของการ์ดมาเองในตัว** ⇒ ถ้าใส่หัวกลุ่มครอบอีกชั้น ผู้ใช้จะเห็นชื่อเรื่อง
         สองอันติดกันที่สื่อความเดียวกัน ("ช่วงเวลาไม่รบกวน" ทับ "ช่วงเวลาไม่ส่งแจ้งเตือน")
         ⇒ บล็อกของเราเองจึงทำตามแบบเดียวกัน (การ์ดมีหัวเรื่องในตัว) เพื่อให้ทั้งหน้าเป็นชุดเดียว
         ⚠️ สองการ์ดนั้นยังใช้ `stone-*`/`rounded-2xl` อยู่ (ยังไม่ย้ายมา token) — เป็นงาน
            ของ R5 "ความสม่ำเสมอทั้งแอป" ไม่ใช่ของรอบนี้ · ห้ามลอกสไตล์เก่ามาใช้กับของใหม่
    -->
    <!-- ===== ⚙️ รับเรื่องอะไร ===== -->
    <AppCard :padded="false" class="p-5 sm:p-6">
      <div class="mb-5 flex items-center gap-3">
        <span
          class="flex h-10 w-10 shrink-0 items-center justify-center rounded-control bg-canvas text-ink-2"
          aria-hidden="true"
        >
          <i class="bi bi-bell" />
        </span>
        <div class="min-w-0">
          <h2 class="text-lg font-bold text-ink-1">การแจ้งเตือน</h2>
          <p class="mt-0.5 text-xs text-ink-2">
            เลือกว่าจะรับเรื่องอะไร — ปิดแล้วเรื่องนั้นจะไม่ขึ้นทั้งในแอพและการแจ้งเตือน
          </p>
        </div>
      </div>

      <!-- โหลดไม่สำเร็จ: ไม่ปิดกั้นทั้งหน้า แค่บล็อกนี้ -->
      <div v-if="prefsError" class="rounded-control bg-canvas px-4 py-6 text-center">
        <i class="bi bi-cloud-slash mb-2 block text-2xl text-ink-3" aria-hidden="true" />
        <p class="text-sm font-semibold text-ink-1">โหลดการตั้งค่าไม่ได้</p>
        <p class="mt-1 text-[13px] text-ink-2">ตรวจสอบการเชื่อมต่อแล้วลองอีกครั้ง</p>
        <button
          type="button"
          class="mt-3 inline-flex h-11 items-center gap-2 rounded-control border border-line bg-surface px-4 text-[13px] font-bold text-ink-1 transition-colors hover:bg-canvas focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
          @click="loadPrefs"
        >
          <i class="bi bi-arrow-clockwise" aria-hidden="true" /> ลองใหม่
        </button>
      </div>

      <div v-else-if="prefsLoading" class="space-y-4" aria-busy="true">
        <div v-for="i in 5" :key="i" class="flex items-center gap-3">
          <div class="h-9 w-9 shrink-0 animate-pulse rounded-control bg-canvas" />
          <div class="flex-1 space-y-2">
            <div class="h-4 w-28 animate-pulse rounded bg-canvas" />
            <div class="h-3 w-44 animate-pulse rounded bg-canvas" />
          </div>
          <div class="h-6 w-11 shrink-0 animate-pulse rounded-full bg-canvas" />
        </div>
      </div>

      <div v-else class="divide-y divide-line">
        <div
          v-for="g in PREFERENCE_GROUPS"
          :key="g.value"
          class="flex items-start gap-3 py-3.5 first:pt-0 last:pb-0"
        >
          <span
            class="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-control bg-canvas text-ink-2"
            aria-hidden="true"
          >
            <i :class="g.icon" />
          </span>
          <div class="min-w-0 flex-1">
            <p class="text-sm font-semibold text-ink-1">{{ g.label }}</p>
            <p class="mt-0.5 text-xs leading-snug text-ink-2">{{ GROUP_DESCRIPTIONS[g.value] }}</p>
          </div>
          <!-- role="switch" + aria-checked → screen reader อ่านสถานะออก ไม่ต้องเดาจากสี -->
          <button
            type="button"
            role="switch"
            :aria-checked="isOn(g.value)"
            :aria-label="`${isOn(g.value) ? 'ปิด' : 'เปิด'}การแจ้งเตือน ${g.label}`"
            :disabled="savingGroup === g.value"
            class="relative mt-1 inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:outline-none disabled:opacity-50"
            :class="isOn(g.value) ? 'bg-brand' : 'bg-ink-3/40'"
            @click="toggleGroup(g.value)"
          >
            <span
              class="inline-block h-5 w-5 rounded-full bg-white shadow transition-transform motion-reduce:transition-none"
              :class="isOn(g.value) ? 'translate-x-[22px]' : 'translate-x-0.5'"
            />
          </button>
        </div>

        <!--
          📢 ประกาศฉุกเฉิน — **แถวอ่านอย่างเดียว ไม่มีสวิตช์**
          ⚠️ เดิมกลุ่มนี้ไม่โชว์ในหน้าตั้งค่าเลย ⇒ ผู้ใช้ที่ปิดทุกกลุ่มแล้วยังเห็นประกาศเด้ง
             ต้องเดาเองว่าทำไม ⇒ แถวนี้ตอบคำถามนั้น
          🔴 **ห้ามใส่สวิตช์ที่นี่** — backend รับ pattern แค่ 5 กลุ่ม ⇒ กดแล้วได้ 422
             และโดยเจตนาแล้ว: ประกาศฉุกเฉิน (น้ำท่วม/ไฟดับ/งดเรียน) ที่ปิดได้ = ประกาศที่ล้มเหลว
             (ดูคอมเมนต์ `PREFERENCE_GROUP_VALUES` ใน `types/notification.ts`)
        -->
        <div class="flex items-start gap-3 py-3.5 last:pb-0">
          <span
            class="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-control bg-canvas text-ink-3"
            aria-hidden="true"
          >
            <i class="bi bi-megaphone" />
          </span>
          <div class="min-w-0 flex-1">
            <p class="flex items-center gap-1.5 text-sm font-semibold text-ink-1">
              ประกาศฉุกเฉิน
              <i class="bi bi-lock-fill text-[11px] text-ink-3" aria-hidden="true" />
            </p>
            <p class="mt-0.5 text-xs leading-snug text-ink-2">
              {{ GROUP_DESCRIPTIONS.announcement }}
            </p>
          </div>
          <span class="mt-1.5 shrink-0 text-xs font-semibold text-ink-3">ปิดไม่ได้</span>
        </div>
      </div>
    </AppCard>

    <!-- ===== 🔔 ถึงมือถือเครื่องนี้ ===== -->
    <!-- ⚠️ ต่อจากการ์ดด้านบนโดยเจตนา — สองการ์ดนี้เป็นเรื่องเดียวกันคนละชั้น:
         การ์ดบน = "รับเรื่องอะไร" (ทั้ง in-app และ push) · การ์ดนี้ = "เครื่องนี้รับไหม" -->
    <PushSettingsCard />

    <!-- ===== 🔇 ช่วงเวลาไม่ส่งแจ้งเตือน ===== -->
    <!-- ⚠️ แสดงให้ทุกคนเห็น แต่แก้ได้เฉพาะผู้มี MANAGE_SETTINGS — ห้ามซ่อนจากนักเรียน
         (นักเรียนต้องรู้ว่าทำไมมือถือเงียบ ดูคอมเมนต์หัวไฟล์ QuietHoursCard.vue) -->
    <QuietHoursCard />

    <!-- ===== 📱 ติดตั้งแอป ===== -->
    <!-- ซ่อนเมื่อเปิดในโหมดแอพที่ติดตั้งแล้ว — ไม่มีอะไรให้ติดตั้งอีก -->
    <AppCard v-if="!isStandalone" :padded="false" class="p-5 sm:p-6">
      <div class="mb-5 flex items-center gap-3">
        <span
          class="flex h-10 w-10 shrink-0 items-center justify-center rounded-control bg-canvas text-ink-2"
          aria-hidden="true"
        >
          <i class="bi bi-phone" />
        </span>
        <div class="min-w-0">
          <h2 class="text-lg font-bold text-ink-1">ติดตั้งแอป</h2>
          <p class="mt-0.5 text-xs text-ink-2">
            เพิ่ม PIRIvoice ลงหน้าจอ เปิดได้เร็วเหมือนแอพ ไม่ต้องพิมพ์ที่อยู่เว็บอีก
          </p>
        </div>
      </div>

      <div class="flex items-start gap-3">
        <div class="min-w-0 flex-1">
          <p v-if="canPromptInstall" class="text-sm font-semibold text-ink-1">
            เครื่องนี้ติดตั้งได้เลย
          </p>
          <template v-else-if="isIosSafari">
            <p class="text-sm font-semibold text-ink-1">iPhone / iPad ต้องติดตั้งเอง</p>
            <ol class="mt-1.5 space-y-0.5 text-xs font-medium text-ink-2">
              <li>
                1. แตะปุ่ม <i class="bi bi-box-arrow-up text-ink-1" aria-hidden="true" /> แชร์
                ที่แถบล่างจอ
              </li>
              <li>2. เลือก “เพิ่มไปที่หน้าจอ”</li>
            </ol>
          </template>
          <template v-else>
            <p class="text-sm font-semibold text-ink-1">เครื่องนี้ติดตั้งอัตโนมัติไม่ได้</p>
            <!-- เบราว์เซอร์ในแอพอื่น (LINE/Facebook) ไม่มีเมนูติดตั้ง ⇒ ต้องบอกให้เปิด Chrome จริง -->
            <p class="mt-1.5 text-xs font-medium text-ink-2">
              เปิดหน้านี้ด้วย <b>Chrome</b> แล้วเลือก “ติดตั้งแอป” จากเมนู
              <i class="bi bi-three-dots-vertical" aria-hidden="true" /> มุมขวาบน
            </p>
            <!-- 🔎 วินิจฉัย: อาการ "ไม่เห็นแบนเนอร์" เกิดได้จาก 5 สาเหตุที่หน้าตาเหมือนกัน
                 และแก้คนละทาง ⇒ โชว์ค่าจริงเฉพาะตอนที่ติดตั้งไม่ได้ (คนที่ติดตั้งได้ไม่เห็นความยุ่งเหยิงนี้) -->
            <p class="mt-2.5 text-xs text-ink-3">{{ installHint }}</p>
            <details class="mt-1.5">
              <summary class="cursor-pointer text-[11px] font-semibold text-ink-3 hover:text-ink-2">
                รายละเอียดทางเทคนิค
              </summary>
              <dl class="mt-2 grid grid-cols-[1fr_auto] gap-x-4 gap-y-1 text-[11px] text-ink-3">
                <template v-for="row in diagRows" :key="row.label">
                  <dt>{{ row.label }}</dt>
                  <dd :class="row.on ? 'font-semibold text-ink-1' : ''">
                    {{ row.on ? 'ใช่' : 'ไม่' }}
                  </dd>
                </template>
              </dl>
            </details>
          </template>
        </div>

        <button
          v-if="canPromptInstall"
          type="button"
          :disabled="installing"
          class="h-11 shrink-0 rounded-control bg-brand px-4 text-xs font-bold text-white transition-colors hover:bg-brand-strong disabled:opacity-60"
          @click="onInstall"
        >
          <i v-if="installing" class="bi bi-arrow-repeat animate-spin" aria-hidden="true" />
          <span v-else>ติดตั้งเลย</span>
        </button>
      </div>
    </AppCard>

    <!-- ===== 🔑 บัญชี ===== -->
    <!--
      🔴 **แถวนี้จำเป็น ไม่ใช่ของแถม** — `profile-password` เป็น `hiddenFromMenu: true`
         ใน `constants/nav.ts` และ **ทางเข้าเดิมของมันคือ dropdown `⋮` ในหน้าโปรไฟล์
         ซึ่ง R3.3 ถอดออก** (เพราะเป็นทางเข้าซ้ำกับกลุ่ม "บัญชี" ของหน้า More)
         ⇒ ถ้าไม่ย้ายมาไว้ที่นี่ **route นั้นจะไม่มีทางเข้าเลยทั้งแอป**
         ⚠️ ตรวจซ้ำไม่ได้ด้วย type-check และไม่มีเทสต์ไหนจับ — เป็น "ของหายที่มองไม่เห็น"
      ⚠️ **ไม่มียกเลิก/ออกจากระบบที่นี่** — อยู่โซนอันตรายของหน้า More ที่ห่างนิ้วโป้งกว่า
    -->
    <AppCard :padded="false" class="p-5 sm:p-6">
      <h2 class="mb-1 text-sm font-bold text-ink-1">บัญชี</h2>
      <p class="mb-3 text-xs text-ink-2">เรื่องความปลอดภัยของบัญชีคุณ</p>
      <RouterLink
        :to="{ name: 'profile-password' }"
        class="flex min-h-11 items-center gap-3 rounded-control px-1 focus-visible:ring-2 focus-visible:ring-brand focus-visible:outline-none"
      >
        <span
          class="flex h-9 w-9 shrink-0 items-center justify-center rounded-control bg-canvas text-ink-2"
          aria-hidden="true"
        >
          <i class="bi bi-key" />
        </span>
        <span class="min-w-0 flex-1 text-sm font-semibold text-ink-1">เปลี่ยนรหัสผ่าน</span>
        <i class="bi bi-chevron-right shrink-0 text-ink-3" aria-hidden="true" />
      </RouterLink>
    </AppCard>
  </div>
</template>
