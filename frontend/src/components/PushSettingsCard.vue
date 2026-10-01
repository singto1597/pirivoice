<!-- eslint-disable vue/multi-word-component-names -- ชื่อตาม spec A3 -->
<script setup lang="ts">
/**
 * 🔔 การ์ด "แจ้งเตือนถึงมือถือ" (A3 + #44)
 *
 * แยกเป็นคอมโพเนนต์เพราะ `Profile.vue` ยาวอยู่แล้ว และการ์ดนี้มี **7 สถานะ**
 * ที่ต้องแยกให้ผู้ใช้อ่านออก (ต่างจากการ์ดตั้งค่ากลุ่มใน A2 ที่มีสถานะเดียว)
 *
 * ⚠️ การ์ดนี้เป็น **per-เครื่อง** ไม่ใช่ per-บัญชี — เครื่องเดียวถูกใช้หลายคนได้
 *    (มือถือโรงเรียน) ⇒ สวิตช์นี้ควบคุม "อุปกรณ์นี้" ส่วนจำนวนที่แสดงคือทุกอุปกรณ์
 *    ของบัญชีที่ล็อกอินอยู่ · การยึดเครื่องกับเจ้าของใหม่เกิดตอน subscribe (ดู S3)
 */
import { computed, onMounted, ref } from 'vue'
import Swal from 'sweetalert2'
import { isIosSafari, isStandalone } from '@/pwa'
import {
  describePushError,
  disablePush,
  enablePush,
  pushBusy,
  pushDeviceCount,
  pushEnabled,
  pushPermission,
  pushReady,
  pushSubscribed,
  pushSubscriptionStale,
  pushSupported,
  refreshPushStatus,
  repairPush,
  type PushEnableResult,
} from '@/push'

/**
 * 7 สถานะที่แสดงผล — เรียงตามลำดับความสำคัญ (ตัวที่มาก่อนชนะ)
 *
 * ⚠️ `ios-needs-install` ต้องมาก่อน `blocked` — บน iOS ที่ยังไม่ติดตั้ง
 *    `Notification.permission` อาจเป็น `denied` ค้างจากตอนที่ยังใช้ในแท็บปกติ
 *    ⇒ ถ้าเอา `blocked` มาก่อน จะบอกผู้ใช้ผิด ๆ ว่า "ถูกบล็อก" ทั้งที่แค่ยังไม่ติดตั้ง
 * ⚠️ `blocked` ต้องมาก่อน `stale` — ถ้าเบราว์เซอร์ยังไม่อนุญาต การ "เปิดใหม่" ก็ไม่ช่วยอะไร
 *    ⇒ ต้องให้ผู้ใช้ไปปลดบล็อกก่อน แล้วค่อยกลับมาเจอคำเตือนคีย์ (ถ้ายังค้างอยู่)
 */
type CardState =
  | 'loading'
  | 'unsupported'
  | 'ios-needs-install'
  | 'blocked'
  | 'stale'
  | 'on'
  | 'off'

const state = computed<CardState>(() => {
  if (!pushReady.value) return 'loading'
  if (!pushSupported.value) return 'unsupported'
  if (isIosSafari.value && !isStandalone.value) return 'ios-needs-install'
  if (pushPermission.value === 'denied') return 'blocked'
  if (pushSubscriptionStale.value) return 'stale'
  return pushSubscribed.value ? 'on' : 'off'
})

const busy = computed(() => pushBusy.value)
const toggling = ref(false)

onMounted(() => {
  // ⚠️ ที่นี่คือที่ที่คีย์ public ถูกโหลด — **จำเป็นต่อความถูกต้อง ไม่ใช่แค่ความสวย**
  //    `enablePush()` ห้ามมี `await` ก่อนขอสิทธิ์ (iOS ตัด gesture chain) ⇒ คีย์ต้องพร้อมก่อน
  void refreshPushStatus()
})

/**
 * แจ้งผลการกด "เปิด" — ใช้ร่วมกันทั้งปุ่มเปิดปกติ (④/⑤) และปุ่มซ่อม (③)
 *
 * ⚠️ แยกออกมาโดยเจตนา — ข้อความ success/denied ที่เขียนซ้ำสองที่จะค่อย ๆ เพี้ยนจากกัน
 *    แล้วผู้ใช้จะได้รับคำอธิบายไม่ตรงกันทั้งที่ระบบทำสิ่งเดียวกัน
 * `dismissed` = ผู้ใช้ปิด dialog เอง — ไม่ต้องเด้งอะไรตามไป ซ้ำซาก
 */
async function reportEnableResult(result: PushEnableResult): Promise<void> {
  if (result === 'enabled') {
    await Swal.fire({
      icon: 'success',
      title: 'เปิดการแจ้งเตือนแล้ว',
      text: 'มีเรื่องใหม่หรือกระทู้ใหม่ เดี๋ยวแจ้งให้ทราบแม้ปิดแอปอยู่',
      timer: 2400,
      showConfirmButton: false,
    })
  } else if (result === 'denied') {
    await Swal.fire({
      icon: 'warning',
      title: 'เบราว์เซอร์บล็อกการแจ้งเตือนไว้',
      text: 'เปิดได้ที่ ตั้งค่าเบราว์เซอร์ → การแจ้งเตือน → อนุญาตสำหรับเว็บนี้',
    })
  }
}

/**
 * แจ้ง error แบบเดียวกันทั้งสองปุ่ม — ต่างแค่หัวข้อ
 *
 * ⚠️ ข้อความมาจาก `describePushError()` **ไม่ใช่ `e.message` ตรง ๆ** — `DOMException`
 *    ของเบราว์เซอร์บอกแค่ว่าอะไรพัง ไม่บอกว่าต้องทำอะไรต่อ · ผู้ใช้ที่เจอ
 *    `Registration failed - push service error` แล้วกดซ้ำจะเจอข้อความเดิมจนคิดว่าแอพพัง
 */
async function reportError(title: string, e: unknown): Promise<void> {
  await Swal.fire({
    icon: 'error',
    title,
    text: describePushError(e),
  })
}

async function onToggle() {
  if (toggling.value || busy.value) return
  toggling.value = true
  try {
    if (pushSubscribed.value) {
      await disablePush()
      await Swal.fire({
        icon: 'success',
        title: 'ปิดการแจ้งเตือนบนเครื่องนี้แล้ว',
        text: 'ยังเปิดในอุปกรณ์อื่นได้ตามเดิม',
        timer: 2000,
        showConfirmButton: false,
      })
      return
    }

    await reportEnableResult(await enablePush())
  } catch (e: unknown) {
    await reportError('เปิดการแจ้งเตือนไม่สำเร็จ', e)
  } finally {
    toggling.value = false
  }
}

/**
 * ปุ่ม "เปิดใหม่บนเครื่องนี้" ในสถานะ `stale`
 *
 * ⚠️ **ต้องมาจากการกดของผู้ใช้เท่านั้น** (`repairPush()` เรียก `subscribe()` ซึ่ง iOS
 *    ต้องการ gesture) ⇒ **ห้ามย้ายไปเรียกอัตโนมัติตอน `onMounted`** เด็ดขาด
 */
async function onRepair() {
  if (toggling.value || busy.value) return
  toggling.value = true
  try {
    await reportEnableResult(await repairPush())
  } catch (e: unknown) {
    await reportError('ซ่อมการแจ้งเตือนไม่สำเร็จ', e)
  } finally {
    toggling.value = false
  }
}
</script>

<template>
  <!--
    ⚠️ ซ่อนทั้งใบเมื่อเซิร์ฟเวอร์ยังไม่ได้ตั้งคีย์ VAPID (`pushEnabled === false`)
    — เป็นสวิตช์ปิดฉุกเฉินฝั่งเซิร์ฟเวอร์ ไม่ใช่ปัญหาของผู้ใช้ ⇒ โชว์ปุ่มที่กดแล้ว
    ไม่มีอะไรเกิดขึ้นจะทำให้เข้าใจผิดว่าแอพพัง · เงื่อนไขนี้ครอบ `pushSupported` ด้วย
    คือ "ซ่อนทั้งใบ" ชนะ "อธิบายว่าทำไมเครื่องนี้ใช้ไม่ได้" (เจตนา — ดูคอมเมนต์ใน types)
  -->
  <div v-if="pushReady && pushEnabled" class="rounded-2xl border border-stone-200 bg-white p-6 sm:p-8">
    <div class="mb-5 flex items-center gap-3">
      <span
        class="flex h-10 w-10 items-center justify-center rounded-xl bg-stone-100 text-stone-500"
      >
        <i class="bi bi-bell"></i>
      </span>
      <div>
        <h2 class="text-lg font-bold text-stone-900">แจ้งเตือนถึงมือถือ</h2>
        <p class="mt-0.5 text-xs text-stone-500">
          มีเรื่องใหม่หรือกระทู้ใหม่ เด้งขึ้นหน้าจอแม้ยังไม่เปิดแอป
        </p>
      </div>
    </div>

    <!-- ① เบราว์เซอร์ไม่รองรับ -->
    <p v-if="state === 'unsupported'" class="text-sm leading-relaxed text-stone-600">
      เบราว์เซอร์นี้ไม่รองรับการแจ้งเตือนแบบ push — ลองเปิดด้วย Chrome หรือ Safari รุ่นใหม่
      (ในแอปของ LINE / Facebook จะใช้ไม่ได้)
    </p>

    <!-- ② iOS ต้องติดตั้งลงหน้าจอก่อน (Safari บนแท็บธรรมดาไม่มี PushManager) -->
    <div v-else-if="state === 'ios-needs-install'" class="text-sm leading-relaxed text-stone-600">
      <p>
        บน iPhone/iPad ต้อง <strong class="font-semibold text-stone-800">ติดตั้ง PIRIvoice
        ลงหน้าจอหลักก่อน</strong> แล้วเปิดจากไอคอนนั้น จึงจะรับการแจ้งเตือนได้
      </p>
      <p class="mt-2 text-xs text-stone-500">
        วิธีติดตั้ง: แตะปุ่มแชร์ <i class="bi bi-box-arrow-up"></i> ด้านล่าง → “เพิ่มไปที่หน้าจอหลัก”
      </p>
    </div>

    <!-- ③ ผู้ใช้บล็อกไว้ที่เบราว์เซอร์ — เราเปิดให้ไม่ได้ ต้องให้เขาไปเปิดเอง -->
    <p v-else-if="state === 'blocked'" class="text-sm leading-relaxed text-stone-600">
      การแจ้งเตือนสำหรับเว็บนี้ <strong class="font-semibold text-stone-800">ถูกบล็อกอยู่</strong>
      — เปิดได้ที่ ตั้งค่าเบราว์เซอร์ → การแจ้งเตือน → อนุญาตสำหรับเว็บนี้ แล้วกลับมาเปิดอีกครั้ง
    </p>

    <!--
      ④ เครื่องนี้ผูกกับคีย์เก่า (เซิร์ฟเวอร์ rotate คีย์ไปแล้ว) — **ดูเหมือนเปิดอยู่แต่ไม่มีอะไรมาถึง**
      เป็นสถานะที่ต้องอธิบายยาวกว่าปกติเพราะผู้ใช้จะไม่เชื่อว่ามันพัง (ทุกอย่างขึ้นว่าเปิดอยู่)
    -->
    <div v-else-if="state === 'stale'" class="rounded-xl bg-amber-50 p-4 ring-1 ring-amber-200">
      <p class="flex items-center gap-2 text-sm font-semibold text-amber-900">
        <i class="bi bi-exclamation-triangle-fill"></i>
        การแจ้งเตือนของเครื่องนี้หยุดทำงาน
      </p>
      <p class="mt-1.5 text-xs leading-relaxed text-amber-800">
        ระบบเปลี่ยนรหัสความปลอดภัยของการแจ้งเตือนไปแล้ว การตั้งค่าเดิมบนเครื่องนี้จึงใช้ไม่ได้อีก
        — แม้จะยังขึ้นว่าเปิดอยู่ ก็จะไม่มีอะไรเด้งขึ้นมา · กด “เปิดใหม่บนเครื่องนี้” เพื่อแก้
      </p>
      <div class="mt-3 flex flex-wrap gap-2">
        <button
          type="button"
          :disabled="toggling || busy"
          class="inline-flex items-center rounded-lg bg-brand px-3 min-h-11 py-2 text-xs font-semibold text-white transition-colors hover:bg-brand-strong focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 disabled:opacity-50"
          @click="onRepair"
        >
          เปิดใหม่บนเครื่องนี้
        </button>
        <button
          type="button"
          :disabled="toggling || busy"
          class="inline-flex items-center rounded-lg border border-stone-300 px-3 min-h-11 py-2 text-xs font-semibold text-stone-700 transition-colors hover:bg-stone-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-stone-400 focus-visible:ring-offset-2 disabled:opacity-50"
          @click="onToggle"
        >
          ปิดบนเครื่องนี้
        </button>
      </div>
    </div>

    <!-- ⑤/⑥ ปกติ — สวิตช์ของ "เครื่องนี้" + จำนวนอุปกรณ์ทั้งบัญชี -->
    <div v-else class="flex items-start gap-4">
      <div class="min-w-0 flex-1">
        <p class="text-sm font-semibold text-stone-800">
          {{ pushSubscribed ? 'เปิดอยู่บนเครื่องนี้' : 'ยังไม่ได้เปิดบนเครื่องนี้' }}
        </p>
        <p class="mt-0.5 text-xs leading-snug text-stone-500">
          <template v-if="pushDeviceCount > 0">
            บัญชีนี้เปิดรับอยู่ {{ pushDeviceCount }} อุปกรณ์
          </template>
          <template v-else> เปิดแล้วจะได้รับแจ้งเตือนแม้ปิดแอป </template>
        </p>
      </div>
      <!-- role="switch" + aria-checked → screen reader อ่านสถานะออก ไม่ต้องเดาจากสี -->
      <button
        type="button"
        role="switch"
        :aria-checked="pushSubscribed"
        aria-label="การแจ้งเตือนบนเครื่องนี้"
        :aria-disabled="toggling || busy"
        class="tap-44 relative mt-1 inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 aria-disabled:opacity-50"
        :class="pushSubscribed ? 'bg-brand' : 'bg-stone-300'"
        @click="onToggle"
      >
        <span
          class="inline-block h-5 w-5 rounded-full bg-white shadow transition-transform motion-reduce:transition-none"
          :class="pushSubscribed ? 'translate-x-[22px]' : 'translate-x-0.5'"
        ></span>
      </button>
    </div>
  </div>
</template>
