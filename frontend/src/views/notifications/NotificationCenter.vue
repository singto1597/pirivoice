<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import Swal from 'sweetalert2'
import { listNotifications } from '@/services/notification'
import { GROUP_TABS, NOTIFICATION_TYPE_ICONS, type NotificationItem, type NotificationGroup } from '@/types/notification'
import {
  UNAVAILABLE_QUERY,
  UNAVAILABLE_TITLE,
  readUnavailable,
  unavailableMessage,
} from '@/router/unavailable'
import { deepLinkTarget } from '@/router/deepLink'
import { useNotificationsStore } from '@/stores/notifications'
import PaginationBar from '@/components/PaginationBar.vue'

/**
 * 🔔 หน้าแจ้งเตือนกลาง (เข้าได้ทุกคน) — badge messenger style
 * - แท็บ: ทั้งหมด / เรื่องของฉัน / เรื่องที่รับ / PIRI Boards / จัดการรายงาน / ประกาศฉุกเฉิน
 * - แถวยังไม่อ่านไฮไลต์แดงอ่อน + ปุ่ม mark-read รายการ
 * - "อ่านทั้งหมด" เคลียร์ทุกกลุ่ม
 * - คลิกแถว → ไปที่เรื่อง/บอร์ด/รายงานที่เกี่ยวข้อง (แล้ว mark อ่าน)
 * - 🚪 ปลายทางของหน้าที่ถูกซ่อน/ลบ (บั๊ก #32) → เด้งกลับมาที่นี่พร้อม `?unavailable=`
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

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleString('th-TH', {
    timeZone: 'Asia/Bangkok',
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function iconFor(n: NotificationItem): string {
  return NOTIFICATION_TYPE_ICONS[n.type] || 'bi bi-bell'
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
  n.read_at = new Date().toISOString()
}

// ✅ อ่านทั้งหมด
async function markAll() {
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
    <div class="flex flex-wrap items-start justify-between gap-3 mb-5">
      <div>
        <p class="mb-1 text-[11px] font-bold uppercase tracking-widest text-stone-400">Inbox</p>
        <h1 class="text-2xl font-bold tracking-tight text-stone-900 leading-tight sm:text-3xl">
          <i class="bi bi-bell-fill mr-1 text-[#B91C1C]"></i> การแจ้งเตือน
        </h1>
        <p class="mt-1 text-sm text-stone-500">
          เรื่องที่ยังไม่ได้อ่าน {{ notificationsStore.total > 0 ? `(${notificationsStore.total})` : '' }}
        </p>
      </div>
      <div class="flex items-center gap-2">
        <button
          @click="unreadOnly = !unreadOnly"
          class="rounded-xl border px-3 py-2 text-sm font-semibold transition-colors"
          :class="unreadOnly ? 'bg-[#B91C1C] text-white border-[#B91C1C]' : 'bg-white text-stone-600 border-stone-200 hover:bg-stone-50'"
        >
          <i class="bi bi-envelope mr-1"></i> ยังไม่อ่าน
        </button>
        <button
          v-if="notificationsStore.total > 0"
          @click="markAll"
          class="rounded-xl border border-[#B91C1C]/20 bg-white px-3 py-2 text-sm font-bold text-[#B91C1C] transition-colors hover:bg-[#B91C1C]/5"
        >
          <i class="bi bi-check2-all mr-1"></i> อ่านทั้งหมด
        </button>
      </div>
    </div>

    <!-- แท็บกลุ่ม -->
    <div class="mb-4 flex flex-wrap gap-2">
      <button
        v-for="tab in GROUP_TABS"
        :key="tab.value"
        @click="activeTab = tab.value"
        class="rounded-xl border px-4 py-2 text-sm font-bold transition-all"
        :class="activeTab === tab.value
          ? 'bg-[#B91C1C] text-white border-[#B91C1C]'
          : 'bg-white text-stone-600 border-stone-200 hover:bg-stone-50'"
      >
        <i :class="[tab.icon, 'mr-1.5']"></i> {{ tab.label }}
        <span v-if="tab.value && (notificationsStore.counts[tab.value] ?? 0) > 0"
          class="ml-1.5 rounded-full px-1.5 py-0.5 text-[11px] font-bold"
          :class="activeTab === tab.value ? 'bg-white/25' : 'bg-[#B91C1C]/10 text-[#B91C1C]'">
          {{ notificationsStore.counts[tab.value] ?? 0 }}
        </span>
      </button>
    </div>

    <!-- loading skeleton -->
    <div v-if="isLoading" class="overflow-hidden rounded-2xl border border-stone-200 bg-white" aria-busy="true">
      <div class="divide-y divide-stone-100">
        <div v-for="i in 6" :key="i" class="flex items-start gap-3 p-4">
          <div class="h-10 w-10 shrink-0 animate-pulse rounded-xl bg-stone-100"></div>
          <div class="flex-1 space-y-2">
            <div class="h-4 w-1/3 animate-pulse rounded bg-stone-100"></div>
            <div class="h-3 w-2/3 animate-pulse rounded bg-stone-100"></div>
          </div>
        </div>
      </div>
    </div>

    <!-- error -->
    <div v-else-if="error" class="rounded-2xl border-2 border-dashed border-stone-200 bg-white py-16 text-center">
      <i class="bi bi-bell-slash mb-3 block text-3xl text-stone-300"></i>
      <p class="text-[15px] font-semibold text-stone-700">ไม่สามารถโหลดการแจ้งเตือนได้ในขณะนี้</p>
      <p class="mx-auto mt-1 max-w-md text-sm text-stone-500">{{ error }}</p>
      <button
        type="button"
        @click="load"
        class="mt-5 inline-flex items-center gap-2 rounded-lg bg-[#B91C1C] px-5 py-2.5 text-[13px] font-bold text-white transition-colors hover:bg-[#991B1B]"
      >
        <i class="bi bi-arrow-clockwise"></i> ลองใหม่
      </button>
    </div>

    <!-- ว่าง -->
    <div v-else-if="items.length === 0" class="rounded-2xl border-2 border-dashed border-stone-200 bg-white p-12 text-center text-stone-500">
      <div class="mb-2 text-4xl"><i class="bi bi-bell-slash text-stone-300"></i></div>
      <p class="font-semibold">ไม่มีการแจ้งเตือน</p>
      <p class="text-sm">เมื่อมีเรื่องใหม่/บอร์ดใหม่/คอมเมนต์ตอบกลับ จะขึ้นตรงนี้</p>
    </div>

    <!-- รายการ -->
    <div v-else class="overflow-hidden rounded-2xl border border-stone-200 bg-white">
      <div class="divide-y divide-stone-200">
        <div
          v-for="n in items"
          :key="n.id"
          class="relative flex cursor-pointer items-start gap-3 p-4 transition-colors"
          :class="n.read_at ? 'hover:bg-stone-50' : 'bg-[#B91C1C]/5 hover:bg-[#B91C1C]/10'"
          @click="go(n)"
        >
          <span v-if="!n.read_at" class="absolute left-2 top-1/2 h-2 w-2 -translate-y-1/2 rounded-full bg-[#B91C1C]" aria-hidden="true"></span>
          <div class="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl"
            :class="n.read_at ? 'bg-stone-100 text-stone-400' : 'bg-[#B91C1C]/10 text-[#B91C1C]'">
            <i :class="[iconFor(n), 'text-lg']"></i>
          </div>
          <div class="min-w-0 flex-1">
            <div class="flex items-start justify-between gap-2">
              <p class="text-sm font-bold leading-snug text-stone-900">{{ n.title }}</p>
              <span class="shrink-0 whitespace-nowrap text-[11px] text-stone-400">{{ fmtDate(n.created_at) }}</span>
            </div>
            <p class="mt-0.5 line-clamp-2 text-sm leading-snug text-stone-500">{{ n.body }}</p>
            <div class="mt-1.5 flex items-center gap-2">
              <span class="rounded-full bg-stone-100 px-2 py-0.5 text-[11px] font-semibold text-stone-500">{{ n.actor_name || 'ระบบ' }}</span>
            </div>
          </div>
          <button
            v-if="!n.read_at"
            @click.stop="markOne(n)"
            class="shrink-0 rounded-lg px-2.5 py-1.5 text-[11px] font-bold text-[#B91C1C] transition-colors hover:bg-[#B91C1C]/5"
            title="ทำเครื่องหมายว่าอ่านแล้ว"
          >
            อ่านแล้ว
          </button>
        </div>
      </div>
    </div>

    <PaginationBar :total="total" :page="page" :page-size="pageSize" :loading="isLoading" @page-change="onPageChange" />
  </div>
</template>
