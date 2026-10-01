<script setup lang="ts">
/**
 * 🔇 การ์ด "ช่วงเวลาไม่ส่งแจ้งเตือน" (A8) — ค่าตั้งระดับ **โรงเรียน**
 *
 * ⚠️ **คนละเรื่องกับ "การแจ้งเตือน" (A2) ที่อยู่เหนือขึ้นไป — อย่ารวมกัน:**
 *    · A2 การ์ด 4 กลุ่ม = "ฉันขอปิดกลุ่มนี้"  → ของคนคนเดียว → เงียบทั้ง in-app และ push
 *    · การ์ดนี้          = "โรงเรียนขอความสงบ" → ของทั้งโรงเรียน → **เงียบเฉพาะ push**
 *      ⭐ แถวใน `notifications` ยังถูกสร้างครบ ⇒ เปิดแอพดูยังเห็นครบ **ไม่มีอะไรหายไป แค่ไม่มีเสียง**
 *
 * ⚠️ **การ์ดนี้แสดงให้ทุกคนเห็น แต่แก้ได้เฉพาะคนมีสิทธิ์** — ตั้งใจ:
 *    `GET /api/settings/quiet-hours` เปิดให้ผู้ใช้ที่ล็อกอินทุกคน (นักเรียนต้องรู้ว่าทำไมมือถือเงียบ)
 *    เฉพาะ `PUT` ที่ต้องมี `MANAGE_SETTINGS` ⇒ โหมดอ่านอย่างเดียวคือสภาพปกติของนักเรียน
 *    **ไม่ซ่อนการ์ดจากนักเรียน** ไม่งั้นเขาจะเห็น "มือถือเงียบ" โดยไม่มีคำอธิบายอยู่ที่ไหนเลย
 */
import { computed, onMounted, ref } from 'vue'
import Swal from 'sweetalert2'
import { useAuthStore } from '@/stores/auth'
import { getQuietHours, updateQuietHours } from '@/services/settings'
import {
  QUIET_HOURS_DEFAULT_END,
  QUIET_HOURS_DEFAULT_START,
  QUIET_HOURS_PRESETS,
  type QuietHours,
} from '@/types/quietHours'

const authStore = useAuthStore()
const canEdit = computed(() => authStore.hasPermission('MANAGE_SETTINGS'))

const isLoading = ref(true)
const loadError = ref('')
const saving = ref(false)

// ค่าที่โหลดมา (ใช้แสดงผล + เป็นค่าตั้งต้นของฟอร์ม)
const enabled = ref(false)
const start = ref(QUIET_HOURS_DEFAULT_START)
const end = ref(QUIET_HOURS_DEFAULT_END)
// null = โรงเรียนยังไม่เคยตั้ง — ใช้แยก "ค่าเริ่มต้น" ออกจาก "ตั้งไว้แล้วแต่ปิดสวิตช์"
const updatedAt = ref<string | null>(null)

// draft ของฟอร์ม — แยกจากค่าจริง เพื่อ "ยกเลิก" ได้โดยไม่ต้องโหลดซ้ำ
const draftStart = ref(start.value)
const draftEnd = ref(end.value)
const isDirty = computed(() => draftStart.value !== start.value || draftEnd.value !== end.value)

function apply(data: QuietHours) {
  enabled.value = data.enabled
  start.value = data.start
  end.value = data.end
  updatedAt.value = data.updated_at
  draftStart.value = data.start
  draftEnd.value = data.end
}

async function load() {
  isLoading.value = true
  loadError.value = ''
  try {
    apply(await getQuietHours())
  } catch (e: unknown) {
    loadError.value = e instanceof Error ? e.message : 'โหลดค่าไม่สำเร็จ'
  } finally {
    isLoading.value = false
  }
}

/** เปิด/ปิดสวิตช์ — ใช้เวลาจาก draft (ถ้ากำลังแก้อยู่) เพื่อไม่ให้ค่าที่พิมพ์หาย */
async function setEnabled(next: boolean) {
  await save({ enabled: next, start: draftStart.value, end: draftEnd.value })
}

/** บันทึกช่วงเวลาที่แก้ในฟอร์ม (ยังคงสถานะเปิด/ปิดเดิม) */
async function saveWindow() {
  await save({ enabled: enabled.value, start: draftStart.value, end: draftEnd.value })
}

async function save(payload: { enabled: boolean; start: string; end: string }) {
  if (saving.value) return
  saving.value = true
  try {
    apply(await updateQuietHours(payload))
    await Swal.fire({
      icon: 'success',
      title: payload.enabled ? 'บันทึกช่วงเวลาแล้ว' : 'ปิดการพักแจ้งเตือนแล้ว',
      // บอกผลที่เกิดขึ้นจริงกับ *คนอื่น* ด้วย ไม่ใช่แค่ "บันทึกสำเร็จ"
      // — ผู้ดูแลต้องเข้าใจว่าคนทั้งโรงเรียนได้รับผลอย่างไร
      text: payload.enabled
        ? `ระบบจะไม่ส่งแจ้งเตือนถึงมือถือระหว่าง ${payload.start}–${payload.end} น. (ข้อความในแอพยังเข้านะ)`
        : 'ระบบกลับมาส่งแจ้งเตือนตามปกติแล้ว',
      timer: 2600,
      showConfirmButton: false,
    })
  } catch (e: unknown) {
    // ⚠️ backend ตอบ **400** (ไม่ใช่ 422) พร้อมข้อความไทยที่บอกสาเหตุตรง ๆ
    //    (เช่น เวลาเริ่ม = เวลาสิ้นสุด) ⇒ api.ts แนบ `detail` มาใน Error.message แล้ว
    //    ⇒ ไม่ต้องเดาข้อความเองที่นี่ และไม่ต้อง pre-check ฝั่ง client
    //    (การตรวจซ้ำที่นี่จะกลายเป็นนิยามที่สองของ "ค่าที่ใช้ได้" ซึ่งเพี้ยนจาก backend ได้)
    await Swal.fire({
      icon: 'error',
      title: 'บันทึกไม่สำเร็จ',
      text: e instanceof Error ? e.message : 'เกิดข้อผิดพลาด กรุณาลองใหม่',
    })
  } finally {
    saving.value = false
  }
}

function usePreset(p: { start: string; end: string }) {
  draftStart.value = p.start
  draftEnd.value = p.end
}

/** แสดงเวลาอ่านง่าย — "22:00" → "22:00 น." (ไม่แปลงเป็น Date เพราะเป็นเวลาท้องถิ่นไม่ระบุวัน) */
function hhmm(v: string): string {
  return `${v} น.`
}

const statusText = computed(() => {
  if (updatedAt.value === null) return 'ยังไม่ได้ตั้ง — ระบบส่งแจ้งเตือนทุกเวลา'
  return enabled.value ? 'กำลังพักแจ้งเตือนตามช่วงเวลานี้' : 'ปิดอยู่ — ส่งแจ้งเตือนทุกเวลา'
})

onMounted(load)
</script>

<template>
  <div class="rounded-2xl border border-stone-200 bg-white p-6 sm:p-8">
    <div class="mb-5 flex items-center gap-3">
      <span class="flex h-10 w-10 items-center justify-center rounded-xl bg-stone-100 text-stone-500">
        <i class="bi bi-moon-stars"></i>
      </span>
      <div>
        <h2 class="text-lg font-bold text-stone-900">ช่วงเวลาไม่ส่งแจ้งเตือน</h2>
        <p class="mt-0.5 text-xs text-stone-500">
          ตั้งไว้ระดับโรงเรียน — ใช้ตอนสอบ กลางคืน หรือช่วงประชุมทั้งโรงเรียน
        </p>
      </div>
    </div>

    <!-- ⓪ กำลังโหลด -->
    <div v-if="isLoading" class="space-y-3" aria-hidden="true">
      <div class="h-4 w-40 animate-pulse rounded bg-stone-100 motion-reduce:animate-none"></div>
      <div class="h-10 w-full animate-pulse rounded-xl bg-stone-100 motion-reduce:animate-none"></div>
    </div>

    <!-- ① โหลดไม่ได้ (เน็ต/เซิร์ฟเวอร์) — ต้องมีทางลองใหม่ ไม่ใช่เงียบ -->
    <div v-else-if="loadError" class="text-sm text-stone-600">
      <p>{{ loadError }}</p>
      <button
        type="button"
        class="inline-flex items-center mt-3 rounded-lg border border-stone-300 px-3 min-h-11 py-1.5 text-xs font-semibold text-stone-700 hover:bg-stone-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
        @click="load"
      >
        ลองอีกครั้ง
      </button>
    </div>

    <template v-else>
      <!-- ② สถานะปัจจุบัน — อ่านให้ออกในบรรทัดเดียว -->
      <div class="mb-4 flex items-start gap-4">
        <div class="min-w-0 flex-1">
          <p class="text-sm font-semibold text-stone-800">{{ statusText }}</p>
          <p v-if="updatedAt !== null" class="mt-0.5 text-xs text-stone-500">
            ช่วงที่ตั้งไว้ {{ hhmm(start) }} – {{ hhmm(end) }}
            <span v-if="start > end">(ข้ามคืน)</span>
          </p>
          <p v-else class="mt-0.5 text-xs text-stone-500">
            ค่าเริ่มต้นที่แนะนำ {{ hhmm(QUIET_HOURS_DEFAULT_START) }} –
            {{ hhmm(QUIET_HOURS_DEFAULT_END) }} (ยังไม่มีผลจนกว่าจะเปิดสวิตช์)
          </p>
        </div>
        <button
          v-if="canEdit"
          type="button"
          role="switch"
          :aria-checked="enabled"
          :aria-label="enabled ? 'ปิดการพักแจ้งเตือน' : 'เปิดการพักแจ้งเตือน'"
          :disabled="saving"
          class="tap-44 relative mt-1 inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 disabled:opacity-50"
          :class="enabled ? 'bg-brand' : 'bg-stone-300'"
          @click="setEnabled(!enabled)"
        >
          <span
            class="inline-block h-5 w-5 rounded-full bg-white shadow transition-transform motion-reduce:transition-none"
            :class="enabled ? 'translate-x-[22px]' : 'translate-x-0.5'"
          ></span>
        </button>
      </div>

      <!-- ③ ฟอร์ม — เฉพาะคนมีสิทธิ์ · คนอื่นอ่านค่าจากข้อความข้างบนพอ -->
      <div v-if="canEdit" class="border-t border-stone-100 pt-4">
        <div class="flex flex-wrap items-end gap-3">
          <label class="flex flex-col gap-1 text-xs font-semibold text-stone-600">
            เริ่ม
            <input
              v-model="draftStart"
              type="time"
              :disabled="saving"
              class="rounded-xl border border-stone-300 px-3 py-2 text-sm font-normal text-stone-800 focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand disabled:opacity-50"
            />
          </label>
          <label class="flex flex-col gap-1 text-xs font-semibold text-stone-600">
            สิ้นสุด
            <input
              v-model="draftEnd"
              type="time"
              :disabled="saving"
              class="rounded-xl border border-stone-300 px-3 py-2 text-sm font-normal text-stone-800 focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand disabled:opacity-50"
            />
          </label>
          <button
            type="button"
            :disabled="saving || !isDirty"
            class="inline-flex items-center rounded-xl bg-brand px-4 min-h-11 py-2 text-sm font-semibold text-white hover:bg-[#a11717] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 disabled:opacity-40"
            @click="saveWindow"
          >
            บันทึกช่วงเวลา
          </button>
        </div>

        <!-- ทางลัด — ลดการพิมพ์บนมือถือ (ค่าที่ใช้จริงบ่อยที่สุดอยู่แรก) -->
        <div class="mt-3 flex flex-wrap gap-2">
          <button
            v-for="p in QUIET_HOURS_PRESETS"
            :key="p.label"
            type="button"
            :disabled="saving"
            class="inline-flex items-center rounded-full border border-stone-300 px-3 min-h-11 py-1 text-xs font-medium text-stone-600 hover:bg-stone-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:opacity-50"
            @click="usePreset(p)"
          >
            {{ p.label }}
          </button>
        </div>

        <p class="mt-3 text-xs leading-relaxed text-stone-500">
          ข้อความในแอพจะยังเข้าครบทุกฉบับ — ช่วงนี้ปิดเฉพาะเสียง/การเด้งขึ้นหน้าจอ
          · เวลาที่น้อยกว่าเวลาเริ่มหมายถึงข้ามคืน (เช่น 22:00–06:00)
        </p>
      </div>

      <!-- ④ โหมดอ่านอย่างเดียว (นักเรียน) — บอกให้ชัดว่าใครแก้ได้ ไม่ปล่อยให้เดา -->
      <p v-else class="border-t border-stone-100 pt-4 text-xs leading-relaxed text-stone-500">
        ค่านี้ตั้งโดยสภานักเรียน — ถ้าต้องการปรับช่วงเวลา กรุณาแจ้งสภานักเรียน
      </p>
    </template>
  </div>
</template>
