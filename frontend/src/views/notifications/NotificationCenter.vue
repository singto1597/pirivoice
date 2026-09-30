<script setup lang="ts">
import { computed, ref, watch, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import Swal from 'sweetalert2'
import { listNotifications } from '@/services/notification'
import {
  GROUP_TABS,
  NOTIFICATION_TYPE_ICONS,
  GROUP_DESCRIPTIONS,
  type NotificationItem,
  type NotificationGroup,
} from '@/types/notification'
import {
  UNAVAILABLE_QUERY,
  UNAVAILABLE_TITLE,
  readUnavailable,
  unavailableMessage,
} from '@/router/unavailable'
import { deepLinkTarget } from '@/router/deepLink'
import { useNotificationsStore } from '@/stores/notifications'
import { fmtDayGroup, dayGroupKind, fmtRelative, fmtTime, type DayGroupKind } from '@/datetime'
import PaginationBar from '@/components/PaginationBar.vue'
import AppChip from '@/components/ui/AppChip.vue'
import AppSheet from '@/components/ui/AppSheet.vue'
import AppEmptyState from '@/components/ui/AppEmptyState.vue'
import IconButton from '@/components/ui/IconButton.vue'
import AppGroupHeader from '@/components/layout/AppGroupHeader.vue'

/**
 * 🔔 หน้าแจ้งเตือนกลาง (เข้าได้ทุกคน)
 *
 * ⭐ **จัดใหม่ทั้งหน้าใน R3.2 — เดิม 7 ชิปกรอง + 2 ปุ่ม toggle กินพื้นที่ครึ่งจอแรก**
 *    แล้วตัวกรอง 6 กลุ่มที่ผู้ใช้ส่วนใหญ่ไม่เคยแตะก็ดันเนื้อหาลงไปให้ต้องเลื่อน
 *
 * | ก่อน | หลัง |
 * |---|---|
 * | 7 ชิปกรอง + 2 ปุ่ม toggle | **2 ชิป** (ทั้งหมด · ยังไม่อ่าน) + **`⋯`** |
 * | 6 กลุ่มที่เหลือ | เข้า `⋯` → `AppSheet` (ไม่ใช่ตัดออก — ยังกรองได้ แต่อยู่หลังการกดครั้งเดียว) |
 * | "อ่านทั้งหมด" เป็นปุ่มเด่นคู่ตัวกรอง | ย้ายเข้า `⋯` ⇒ **งานหลักของหน้าคือ "อ่านรายการ"** |
 * | ลิสต์แบนยาว | **จัดกลุ่มตามวัน** + หัวกลุ่ม `sticky` (วันนี้ / เมื่อวาน / วันที่จริง) |
 * | `<div>` เปล่า + `border-dashed` | `AppEmptyState` (ไม่มีเส้นประ) |
 *
 * ⚠️ **ไม่มี `<h1>`/eyebrow ในหน้านี้** — `AppHeader` แสดง "การแจ้งเตือน" (จาก
 *    `routeTitles`) เป็น `<h1>` อยู่แล้ว ⇒ หัวข้อซ้ำ 2 ชั้นคือสิ่งที่ audit ฟ้องทั้งฉบับ
 *
 * 🚪 ปลายทางของหน้าที่ถูกซ่อน/ลบ (บั๊ก #32) → เด้งกลับมาที่นี่พร้อม `?unavailable=`
 */
const route = useRoute()
const router = useRouter()
const notificationsStore = useNotificationsStore()

const items = ref<NotificationItem[]>([])
const total = ref(0)
const isLoading = ref(true)
const error = ref('')
const activeTab = ref<'' | NotificationGroup>('')
const unreadOnly = ref(false)
const page = ref(1)
const pageSize = 15
const sheetOpen = ref(false)

/** กลุ่มที่ผู้ใช้เลือกได้จากแผ่น `⋯` — ตัด `''` (ทั้งหมด) ออกเพราะมีชิปอยู่แล้ว */
const GROUP_OPTIONS = GROUP_TABS.filter((t) => t.value !== '')

/** กลุ่มที่กรองอยู่ (null = ไม่ได้กรองกลุ่ม) — ใช้ทั้งบนชิปและในแผ่น */
const activeGroupTab = computed(() =>
  activeTab.value === '' ? null : (GROUP_TABS.find((t) => t.value === activeTab.value) ?? null),
)

onMounted(async () => {
  // 🚪 เช็คก่อนโหลด — ผู้ใช้ที่เพิ่งถูกเด้งกลับมาควรเห็น "ทำไม" ทันที ไม่ใช่หลังรายการโผล่
  await announceUnavailable()
  await load()
})

/**
 * 🚪 บอกว่าทำไมเพิ่งถูกเด้งกลับมาจากหน้าที่เปิดไม่ได้ (บั๊ก #32)
 *
 * ทางที่ผู้ใช้มาถึงตรงนี้เกือบทั้งหมดคือ **กด notification** หรือ **กด push** ที่ชี้ไป
 * บอร์ด/เรื่องซึ่งถูกซ่อนหรือถูกลบไปแล้ว ⇒ ถ้าเงียบ ๆ แค่โชว์รายการ เขาจะเข้าใจว่า
 * "กดแล้วไม่มีอะไรเกิดขึ้น" หรือ "แอพพาไปผิดที่" ซึ่งแย่กว่าการบอกตรง ๆ
 *
 * ⚠️ **ล้าง query ทิ้งก่อนแสดง Swal** — ถ้าไม่ล้าง การกด refresh หรือปุ่มย้อนกลับ/
 *    เดินหน้าของเบราว์เซอร์จะทำให้ Swal เด้งซ้ำทุกครั้ง (query ยังค้างใน URL)
 *    แล้วอ่านเหมือนแอพมีบั๊ก · ล้างก่อน = พฤติกรรม "แสดงครั้งเดียว" ที่ถูกต้อง
 *
 * ⚠️ ใช้ `readUnavailable()` ที่ **กรองค่าที่รู้จัก** ไม่ใช่รับค่าจาก URL มาตรง ๆ —
 *    query นี้ใครก็ใส่ได้ (`?unavailable=<มั่ว>`) ⇒ ค่าที่ไม่รู้จักต้องเงียบ ไม่ใช่
 *    เอาไปแสดงเป็นข้อความ (ซึ่งจะกลายเป็น "undefined" ให้ผู้ใช้เห็น)
 */
async function announceUnavailable() {
  const kind = readUnavailable(route.query[UNAVAILABLE_QUERY])
  if (!kind) return
  await router.replace({ name: 'notifications' })
  await Swal.fire({
    icon: 'info',
    title: UNAVAILABLE_TITLE,
    text: unavailableMessage(kind),
    confirmButtonText: 'รับทราบ',
  })
}

watch([activeTab, unreadOnly], () => {
  page.value = 1
  load()
})

// ── ตัวกรอง ────────────────────────────────────────────────────────────────
// ⚠️ ทั้งสามตัวเรียก `load()` ทาง `watch` ข้างบน ไม่เรียกเอง — ไม่งั้นกดชิปครั้งเดียว
//    จะยิง request สองครั้ง (ครั้งหนึ่งจาก watcher อีกครั้งจาก handler)

/** "ทั้งหมด" — ล้างทั้งกลุ่มและตัวกรองยังไม่อ่าน (เป็นสถานะตั้งต้น) */
function showAll() {
  activeTab.value = ''
  unreadOnly.value = false
}

function toggleUnreadOnly() {
  unreadOnly.value = !unreadOnly.value
}

/** เลือกกลุ่มจากแผ่น — ปิดแผ่นด้วย เพื่อให้เห็นผลทันทีว่าเลือกอะไรไป */
function pickGroup(value: '' | NotificationGroup) {
  activeTab.value = value
  sheetOpen.value = false
}

/** ล้างเฉพาะกลุ่ม ไม่แตะตัวกรองยังไม่อ่าน (ผู้ใช้ที่กด "ยังไม่อ่าน" ไว้น่าจะอยากคงไว้) */
function clearGroup() {
  activeTab.value = ''
}

function onPageChange(n: number) {
  page.value = n
  load()
}

async function load() {
  isLoading.value = true
  error.value = ''
  try {
    const res = await listNotifications({
      group_type: activeTab.value || undefined,
      unread_only: unreadOnly.value || undefined,
      limit: pageSize,
      offset: (page.value - 1) * pageSize,
    })
    items.value = res.items
    total.value = res.total
    await notificationsStore.fetchCounts() // badge อัปเดตตามจริง
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'โหลดการแจ้งเตือนไม่สำเร็จ'
  } finally {
    isLoading.value = false
  }
}

/**
 * 🗓️ จัดกลุ่มตามวัน — **เทียบ "ป้าย" ของวัน ไม่ใช่คำนวณคีย์แยก**
 *
 * ⭐ ทำไมปลอดภัย: API เรียง `created_at` จากใหม่ไปเก่า **เสมอ** ⇒ รายการของวันเดียวกัน
 *    อยู่ติดกันเป็นช่วงเดียว · เรา **ยุบเฉพาะช่วงที่ติดกัน** ⇒ สองวันที่จะถูกยุบรวมกันได้
 *    ต้องมีป้ายเหมือนกัน *และ* ติดกัน ซึ่งเกิดไม่ได้เพราะ `fmtDayGroup` คืน `วันนี้`/
 *    `เมื่อวาน` อย่างละครั้ง และวันที่จริงมีทั้งวันและเดือน
 *    (ต่างปีแต่ตรงวัน-เดือนกันจะได้สองกลุ่มแยกกัน ซึ่งถูกต้องกว่า — ไม่ยุบข้ามช่องว่าง)
 *
 * ⚠️ ไม่สร้าง "คีย์วันที่" ขึ้นมาเอง (เช่น `YYYY-MM-DD` ในโซนไทย) เพราะจะเป็นการ
 *    แตกตรรกะเขตเวลาไทยออกเป็นที่ที่สอง — `fmtDayGroup` ใช้ `bangkokDayDiff`
 *    ตัวเดียวกับ `fmtRelative` อยู่แล้ว
 */
interface DayGroup {
  kind: DayGroupKind
  label: string
  items: NotificationItem[]
}

const dayGroups = computed<DayGroup[]>(() => {
  // ⚠️ **`now` ตัวเดียวสำหรับทั้งรอบ** — ส่งไปทั้ง `fmtDayGroup` และ `dayGroupKind`
  //    ถ้าปล่อยให้แต่ละตัวเรียก `new Date()` เอง ที่เส้นแบ่งวันป้ายกับชนิดจะไม่ตรงกันได้
  const now = new Date()
  const out: DayGroup[] = []
  for (const n of items.value) {
    const label = fmtDayGroup(n.created_at, now)
    const last = out[out.length - 1]
    if (last && last.label === label) last.items.push(n)
    else out.push({ kind: dayGroupKind(n.created_at, now), label, items: [n] })
  }
  return out
})

/** ข้อความว่างที่ตรงกับตัวกรองจริง — "ไม่มีการแจ้งเตือน" เฉย ๆ ไม่ตอบว่า "แล้วของฉันหายไปไหน" */
const emptyState = computed(() => {
  if (unreadOnly.value && activeGroupTab.value) {
    return {
      icon: 'bi-check2-circle',
      title: `ไม่มีรายการที่ยังไม่อ่านใน${activeGroupTab.value.label}`,
      description: 'กด "ทั้งหมด" เพื่อดูรายการที่อ่านแล้วในกลุ่มนี้',
    }
  }
  if (unreadOnly.value) {
    return {
      icon: 'bi-check2-circle',
      title: 'อ่านครบทุกการแจ้งเตือนแล้ว',
      description: 'เมื่อมีเรื่องใหม่ จะขึ้นที่นี่และมีตัวเลขบนกระดิ่ง',
    }
  }
  if (activeGroupTab.value) {
    return {
      icon: activeGroupTab.value.icon.replace('bi bi-', 'bi-'),
      title: `ยังไม่มีรายการใน${activeGroupTab.value.label}`,
      description: GROUP_DESCRIPTIONS[activeGroupTab.value.value as NotificationGroup],
    }
  }
  return {
    icon: 'bi-bell-slash',
    title: 'ยังไม่มีการแจ้งเตือน',
    description: 'เมื่อมีเรื่องใหม่ บอร์ดใหม่ หรือมีคนตอบกลับ จะขึ้นตรงนี้',
  }
})

function iconFor(n: NotificationItem): string {
  return NOTIFICATION_TYPE_ICONS[n.type] || 'bi bi-bell'
}

/**
 * ⏱️ เวลาท้ายแถว — **หัวกลุ่มบอก "วัน" ไปแล้ว แถวจึงไม่ต้องบอกวันซ้ำ**
 *
 * ⚠️ **ทำไมไม่ใช้ `fmtRelative()` ตรง ๆ อย่างเดียว:** มันคืน **วันที่จริง** เมื่อเกิน 7 วัน
 *    (พฤติกรรมที่ถูกของมัน — "45 วันที่แล้ว" ก็ต้องลบกันในหัวอยู่ดี) ⇒ แถวที่อยู่ใต้หัวกลุ่ม
 *    "21 ก.ย. 2569" จะพิมพ์ **"21 ก.ย. 2569" ซ้ำคำต่อคำ** กับหัวกลุ่มที่อยู่ห่างขึ้นไป 8px
 *    ซึ่งเป็นความซ้ำแบบเดียวกับที่ทั้งรอบนี้กำลังเก็บกวาด ⇒ กลุ่มที่เป็นวันที่จริงให้ใช้
 *    **เวลานาฬิกา** (`fmtTime`) ซึ่ง *เพิ่ม* ข้อมูลแทนการย้ำ
 *
 * 🔴 **รับ `kind` ของหัวกลุ่มเข้ามา ไม่เทียบสตริงไทยและไม่คำนวณซ้ำเอง** —
 *    (1) เทียบ `label === 'วันนี้'` ตรง ๆ จะ **พังเงียบ ๆ** ถ้ามีคนแก้คำใน `fmtDayGroup`
 *        (ไม่ใช่ type error ไม่ใช่เทสต์พัง) ⇒ ใช้ `DayGroupKind` ที่มี type คุม
 *    (2) คำนวณ `dayGroupKind()` ซ้ำที่นี่จะได้ `now` คนละค่ากับหัวกลุ่ม ⇒ ที่เส้นแบ่งวัน
 *        หัวกลุ่มอาจเป็น `วันนี้` ขณะที่แถวตัดสินเป็น `date` แล้วได้ "วันนี้" + เวลานาฬิกา
 *        ซึ่งอ่านไม่ออกว่าของวันไหน · ใช้ค่าที่หัวกลุ่มคำนวณมาแล้ว = ไม่มีทางไม่ตรงกัน
 *
 * ⚠️ `invalid` = วันที่อ่านไม่ได้ ⇒ คืน `''` ไม่ใช่ `fmtTime()` (ซึ่งจะได้ `Invalid Date`)
 */
function rowTime(n: NotificationItem, kind: DayGroupKind): string {
  if (kind === 'today' || kind === 'yesterday') return fmtRelative(n.created_at)
  if (kind === 'invalid') return ''
  return fmtTime(n.created_at)
}

// ✅ mark อ่านรายการเดียว (ไม่ navigate)
// ⚠️ `read()` **กลืน error เองและคืนผลลัพธ์** ⇒ ต้องเช็คค่าที่คืน ไม่ใช่ try/catch
//    (เดิมครอบ try/catch ไว้ แต่ catch ไม่มีทางทำงาน เพราะ read() ไม่ throw
//     ⇒ ผู้ใช้กดแล้วล้มเหลวก็ไม่เห็นอะไรเลย ป้ายยังขึ้นว่าอ่านแล้ว)
async function markOne(n: NotificationItem) {
  if (n.read_at) return
  const ok = await notificationsStore.read({ ids: [n.id] })
  if (!ok) {
    Swal.fire({
      icon: 'error',
      title: 'ไม่สำเร็จ',
      text: 'ทำเครื่องหมายว่าอ่านแล้วไม่สำเร็จ — ลองใหม่อีกครั้ง',
    })
    return
  }
  // ค่านี้เป็น **เครื่องหมายว่าอ่านแล้ว** ไม่ได้เอาไปแสดง ⇒ ไม่ต้องผ่าน `src/datetime.ts`
  // (ทุกที่ที่แสดงเวลาของแถวนี้ใช้ `created_at` ผ่าน `fmtRelative` เท่านั้น)
  n.read_at = new Date().toISOString()
}

// ✅ อ่านทั้งหมด
async function markAll() {
  sheetOpen.value = false
  const { isConfirmed } = await Swal.fire({
    icon: 'question',
    title: 'อ่านทั้งหมด?',
    text: 'จะทำเครื่องหมายว่าได้อ่านทุกการแจ้งเตือน',
    showCancelButton: true,
    confirmButtonText: 'อ่านทั้งหมด',
    cancelButtonText: 'ยกเลิก',
  })
  if (!isConfirmed) return
  // ไม่สำเร็จ = ไม่ reload รายการ (ไม่งั้นป้าย "อ่านแล้ว" จะขึ้นทั้งที่เซิร์ฟเวอร์ไม่ได้บันทึก)
  if (!(await notificationsStore.read({ read_all: true }))) {
    Swal.fire({
      icon: 'error',
      title: 'ไม่สำเร็จ',
      text: 'ทำเครื่องหมายว่าอ่านแล้วไม่สำเร็จ — ลองใหม่อีกครั้ง',
    })
    return
  }
  page.value = 1
  await load()
}

// 🧭 คลิกแถว → mark อ่าน + navigate ไปที่ entity
//
// ⚠️ **"จะไปไหน" ไม่ได้ตัดสินที่นี่** — ยกไปที่ `@/router/deepLink` เพราะปลายทาง
//    ต้องตรงกับ `data.url` ที่ฝั่ง push ส่งมา (`push_service._deep_link_url()`)
//    ซึ่งเป็นคนละภาษา ⇒ ตรรกะต้องอยู่ที่ที่ประกาศตัวว่าเป็นสัญญาร่วม ไม่ใช่ใน SFC
//    (ดูเหตุผลเต็มใน `router/deepLink.ts`) — ที่นี่เหลือแค่ **ผลข้างเคียง** การ mark อ่าน
function go(n: NotificationItem) {
  // 1) mark อ่าน — ขอบเขตต่างกันตามกลุ่ม (เหมือนเดิมทุกกรณี ไม่ได้เปลี่ยน)
  if (n.group_type === 'report') {
    void notificationsStore.read({ group_type: 'report' })
  } else if (n.group_type === 'announcement') {
    // 📢 ประกาศ (E2) ไม่มี entity/board ให้ mark เป็นชุด (ยิง `markOne` เท่านั้น)
    // ⚠️ ต้อง mark **ก่อน** `router.push` ด้านล่าง เพราะบรรทัดนั้น `return` ทันที
    //    ⇒ ถ้าลืมกรณีนี้ แถวประกาศจะนำทางไป Home แต่ **ป้ายยังไม่อ่านค้างตลอดไป**
    //    (badge ไม่ลดทั้งที่ผู้ใช้กดอ่านแล้ว = อาการที่ผู้ใช้ตีความว่า "ระบบพัง")
    void markOne(n)
  } else if (n.entity_type === 'issue' && n.entity_id != null) {
    void notificationsStore.read({ entity_type: 'issue', entity_id: n.entity_id })
  } else if (n.board_id != null) {
    void notificationsStore.read({ board_id: n.board_id })
  }

  // 2) ไปปลายทางของจริง (เรื่อง/บอร์ด/คิวรายงาน)
  const target = deepLinkTarget(n)
  if (target) {
    void router.push(target)
    return
  }

  // ไม่มีปลายทางเฉพาะ = อยู่ที่รายการนี้ต่อ · รายงานที่ไม่มี board_id ถูก mark
  // ทั้งกลุ่มไปแล้วข้างบน ⇒ เหลือแต่กรณีที่ยังไม่ได้ mark อะไรเลย (แถวเดียว)
  if (n.group_type !== 'report') void markOne(n)
}
</script>

<template>
  <div>
    <!--
      🔴 **ไม่มี `<h1>`/eyebrow** — `AppHeader` แสดง "การแจ้งเตือน" เป็น `<h1>` แล้ว
         ⇒ ของเดิมที่มีทั้ง eyebrow "Inbox" และ `<h1>🔔 การแจ้งเตือน</h1>` คือหัวข้อ
         ซ้ำ 2 ชั้นห่างกันไม่กี่พิกเซล ซึ่งเป็นข้อที่ audit ฟ้อง
    -->
    <p class="mb-3 text-sm leading-relaxed text-ink-2">
      <template v-if="notificationsStore.total > 0">
        ยังไม่ได้อ่าน {{ notificationsStore.total }} รายการ
      </template>
      <template v-else>อ่านครบแล้วทุกรายการ</template>
    </p>

    <!--
      🔀 แถวกรอง — **2 ชิป + `⋯`** แทน 7 ชิป + 2 ปุ่ม toggle
      ⚠️ ใช้ `flex-wrap` ไม่ใช่ `chip-row` (แถวเลื่อนแนวนอน) โดยเจตนา — เหลือ 2-3 ชิป
         ซึ่งพอดีจอ 360dp อยู่แล้ว ⇒ การเลื่อนแนวนอนจะกลายเป็นซ่อนของโดยไม่มีเหตุ
         (ถ้าวันหนึ่งมีชิปเกิน 3 ให้เปลี่ยนเป็น `chip-row` ซึ่งมีอยู่ใน `main.css`)
    -->
    <div class="mb-4 flex flex-wrap items-center gap-2">
      <AppChip label="ทั้งหมด" :active="!activeTab && !unreadOnly" @click="showAll" />
      <AppChip
        label="ยังไม่อ่าน"
        :count="notificationsStore.total"
        :active="unreadOnly"
        @click="toggleUnreadOnly"
      />
      <AppChip
        v-if="activeGroupTab"
        :label="activeGroupTab.label"
        :active="true"
        @click="clearGroup"
      />

      <!-- จุดแดงบอกว่ามีตัวกรองกลุ่มทำงานอยู่ ทั้งที่ตัวชิปอยู่นอกจอ/ถูกยุบ -->
      <IconButton
        class="relative ml-auto"
        icon="bi-three-dots"
        label="กรองตามกลุ่ม และอ่านทั้งหมด"
        @click="sheetOpen = true"
      >
        <span
          v-if="activeTab"
          class="absolute top-1 right-1 h-2 w-2 rounded-full bg-brand"
          aria-hidden="true"
        />
      </IconButton>
    </div>

    <!--
      🪟 แผ่นตัวเลือก — เป็น surface ของ "เลือก/ยืนยัน" เท่านั้น (skills #16: ห้ามใส่ฟอร์ม)
      🔴 `AppSheet` `<Teleport to="body">` + `z-[60]` อยู่ในตัวคอมโพเนนต์แล้ว
    -->
    <AppSheet
      v-model="sheetOpen"
      title="กรองตามกลุ่ม"
      description="เลือกกลุ่มที่ต้องการดู หรือทำเครื่องหมายว่าอ่านแล้วทั้งหมด"
    >
      <div class="px-2 pb-2">
        <button
          v-for="tab in GROUP_OPTIONS"
          :key="tab.value"
          type="button"
          class="flex min-h-14 w-full items-center gap-3 rounded-control px-2 text-left transition-colors hover:bg-canvas"
          :class="activeTab === tab.value ? 'bg-brand-tint text-brand' : 'text-ink-1'"
          :aria-pressed="activeTab === tab.value"
          @click="pickGroup(tab.value)"
        >
          <i
            :class="[tab.icon, 'shrink-0 text-xl', activeTab === tab.value ? 'text-brand' : 'text-ink-2']"
            aria-hidden="true"
          />
          <span class="min-w-0 flex-1 truncate text-sm font-semibold">{{ tab.label }}</span>
          <span
            v-if="(notificationsStore.counts[tab.value] ?? 0) > 0"
            class="shrink-0 rounded-full bg-brand px-1.5 py-0.5 text-[11px] font-bold tabular-nums text-white"
          >
            {{ notificationsStore.counts[tab.value] }}
          </span>
          <i
            v-if="activeTab === tab.value"
            class="bi bi-check-lg shrink-0 text-base text-brand"
            aria-hidden="true"
          />
        </button>

        <!--
          "อ่านทั้งหมด" อยู่ท้ายสุดของแผ่น และ **แยกด้วยเส้น** — เป็นการกระทำที่แตะ
          ทั้งบัญชีและย้อนกลับไม่ได้ ⇒ ต้องไม่อยู่ติดกับรายการที่ผู้ใช้กวาดนิ้วผ่าน
        -->
        <template v-if="notificationsStore.total > 0">
          <div class="my-2 border-t border-line" />
          <button
            type="button"
            class="flex min-h-14 w-full items-center gap-3 rounded-control px-2 text-left font-semibold text-brand transition-colors hover:bg-brand-tint"
            @click="markAll"
          >
            <i class="bi bi-check2-all shrink-0 text-xl" aria-hidden="true" />
            <span class="min-w-0 flex-1">อ่านทั้งหมด ({{ notificationsStore.total }})</span>
          </button>
        </template>
      </div>
    </AppSheet>

    <!-- loading skeleton -->
    <div
      v-if="isLoading"
      class="overflow-hidden rounded-card border border-line bg-surface"
      aria-busy="true"
    >
      <div class="divide-y divide-line">
        <div v-for="i in 6" :key="i" class="flex items-start gap-3 p-4">
          <div class="h-10 w-10 shrink-0 animate-pulse rounded-control bg-canvas" />
          <div class="flex-1 space-y-2">
            <div class="h-4 w-1/3 animate-pulse rounded bg-canvas" />
            <div class="h-3 w-2/3 animate-pulse rounded bg-canvas" />
          </div>
        </div>
      </div>
    </div>

    <!-- error — มีทางออกเสมอ (ปุ่มลองใหม่) ไม่ใช่แค่บอกว่าพัง -->
    <AppEmptyState
      v-else-if="error"
      icon="bi-bell-slash"
      title="โหลดการแจ้งเตือนไม่สำเร็จ"
      :description="error"
    >
      <button
        type="button"
        class="inline-flex items-center gap-2 rounded-control bg-brand px-5 py-2.5 text-sm font-bold text-white transition-colors hover:bg-brand-strong"
        @click="load"
      >
        <i class="bi bi-arrow-clockwise" aria-hidden="true" /> ลองใหม่
      </button>
    </AppEmptyState>

    <!-- ว่าง — ข้อความบอกว่าว่าง *เพราะอะไร* ตามตัวกรองที่เปิดอยู่ -->
    <AppEmptyState
      v-else-if="items.length === 0"
      :icon="emptyState.icon"
      :title="emptyState.title"
      :description="emptyState.description"
    />

    <!--
      📋 รายการ — จัดกลุ่มตามวัน (กลุ่มละการ์ด)

      🔴 **หัวกลุ่มต้องเป็น *พี่น้อง* ของการ์ด ไม่ใช่ลูก** — `AppGroupHeader` เป็น `sticky`
         และ `overflow-hidden` บนบรรพบุรุษจะสร้าง scrollport ใหม่ที่ *ไม่มีการเลื่อน*
         ⇒ `sticky` จะหยุดทำงาน **เงียบ ๆ** (กลไกเดียวกับ skills #11 แต่เป็น `overflow-hidden`
         ไม่ใช่ `overflow-x-hidden`) · การ์ดแต่ละใบจึงมี `overflow-hidden` ได้ตามปกติ
         เพราะไม่มีอะไรข้างในต้อง `sticky` แล้ว — และมุมโค้งยังคมอยู่

      ⚠️ `tone="canvas"` เพราะหน้านี้ทั้งหน้าอยู่บน `bg-canvas` (`MainLayout.vue:121`)
         ⇒ พื้นหัวกลุ่มต้องเป็นสีเดียวกับหน้า ไม่ใช่สีการ์ด ไม่งั้นจะดูเหมือนการ์ดที่ถูกตัดครึ่ง

      ⚠️ หัวกลุ่ม `sticky` ใช้ได้เพราะ `<main>` เป็น scroll container จริง
         🔴 **ห้ามเพิ่ม `overflow-x-hidden` ให้ `<main>` หรือ wrapper `max-w-7xl`**
    -->
    <div v-else class="space-y-4">
      <section v-for="(group, gi) in dayGroups" :key="group.label || gi">
        <AppGroupHeader v-if="group.label" :label="group.label" tone="canvas" />

        <div class="overflow-hidden rounded-card border border-line">
          <!--
            ⚠️ **สองปุ่มเป็นพี่น้องกัน ไม่ใช่ปุ่มซ้อนปุ่ม** — `<button>` ซ้อน `<button>` เป็น
               HTML ที่ไม่ถูกต้อง และโปรแกรมอ่านหน้าจอจะสับสนว่ากำลังอยู่ในปุ่มไหน
               ⇒ แถวนี้เป็น `<div>` ที่กดไม่ได้ ข้างในมี (1) ปุ่มเปิดปลายทาง ซึ่งกินพื้นที่
               ที่เหลือทั้งหมด (2) ปุ่มทำเครื่องหมายว่าอ่านแล้ว เฉพาะแถวที่ยังไม่อ่าน
          -->
          <div
            v-for="n in group.items"
            :key="n.id"
            class="flex items-stretch border-t border-line first:border-t-0"
            :class="n.read_at ? 'bg-surface' : 'bg-brand-tint'"
          >
            <button
              type="button"
              class="relative flex min-w-0 flex-1 items-start gap-3 p-4 text-left transition-colors"
              :class="n.read_at ? 'hover:bg-canvas' : 'hover:bg-brand/10'"
              @click="go(n)"
            >
              <!-- จุดยังไม่อ่าน — ไม่พึ่งสีพื้นอย่างเดียว (ผู้ใช้ที่แยกสีไม่ได้ยังเห็นจุด) -->
              <span
                v-if="!n.read_at"
                class="absolute top-1/2 left-2 h-2 w-2 -translate-y-1/2 rounded-full bg-brand"
                aria-hidden="true"
              />
              <span
                class="flex h-10 w-10 shrink-0 items-center justify-center rounded-control"
                :class="n.read_at ? 'bg-canvas text-ink-3' : 'bg-brand/10 text-brand'"
              >
                <i :class="[iconFor(n), 'text-lg']" aria-hidden="true" />
              </span>
              <span class="min-w-0 flex-1">
                <span class="flex items-start justify-between gap-2">
                  <span class="text-sm font-bold leading-snug text-ink-1">{{ n.title }}</span>
                  <!-- เวลาท้ายแถว — ดู `rowTime()` ว่าทำไมต้องขึ้นกับป้ายของหัวกลุ่ม -->
                  <span class="shrink-0 whitespace-nowrap text-[11px] text-ink-3">
                    {{ rowTime(n, group.kind) }}
                  </span>
                </span>
                <span class="mt-0.5 line-clamp-2 block text-sm leading-snug text-ink-2">
                  {{ n.body }}
                </span>
                <span class="mt-1.5 flex items-center gap-2">
                  <span
                    class="rounded-full bg-canvas px-2 py-0.5 text-[11px] font-semibold text-ink-2"
                  >
                    {{ n.actor_name || 'ระบบ' }}
                  </span>
                </span>
              </span>
              <!--
                ♿ สถานะอ่าน/ยังไม่อ่าน — จุดสีกับพื้นอ่อนเป็น `aria-hidden` และสื่อด้วยสายตา
                   เท่านั้น ⇒ ต้องมี *ข้อความจริง* ให้โปรแกรมอ่านหน้าจอ ไม่งั้นผู้ใช้ที่มองไม่เห็น
                   แยกไม่ได้เลยว่าแถวไหนอ่านแล้ว (แถวที่อ่านแล้วต่างกันแค่สีพื้นกับจุดที่ซ่อนอยู่)
              -->
              <span class="sr-only">{{ n.read_at ? 'อ่านแล้ว' : 'ยังไม่อ่าน' }}</span>
            </button>

            <button
              v-if="!n.read_at"
              type="button"
              class="flex w-12 shrink-0 items-center justify-center text-brand transition-colors hover:bg-brand/10 focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-inset focus-visible:outline-none"
              aria-label="ทำเครื่องหมายว่าอ่านแล้ว"
              @click="markOne(n)"
            >
              <i class="bi bi-check2 text-lg" aria-hidden="true" />
            </button>
          </div>
        </div>
      </section>
    </div>

    <PaginationBar
      :total="total"
      :page="page"
      :page-size="pageSize"
      :loading="isLoading"
      @page-change="onPageChange"
    />
  </div>
</template>
