<!-- eslint-disable vue/multi-word-component-names -- ชื่อตาม route/spec -->
<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'
import Swal from 'sweetalert2'
import { BRAND } from '@/constants/brand'
import AppButton from '@/components/ui/AppButton.vue'
import AppCard from '@/components/ui/AppCard.vue'
import AppEmptyState from '@/components/ui/AppEmptyState.vue'
import { createYear, getYear, updateYear } from '@/services/year'
import type { AcademicYear, AcademicYearUpdatePayload } from '@/types/academicYear'
import {
  EMPTY_YEAR_FORM,
  toYearFormValues,
  yearFormError,
  yearFormToPayload,
  type YearFormValues,
} from '@/types/academicYear'

/**
 * ✍️ สร้าง/แก้ไขปีการศึกษา — **หน้าเต็ม ไม่ใช่แผ่น/โมดัล**
 *
 * 🐛 **ทำไมไม่ใช้โมดัลเหมือนหน้าภาคเรียน** — `docs/skills.md` #16 ห้ามใส่ฟอร์มในแผ่นเลื่อน
 *    ด้วยเหตุผล 3 ข้อที่เกิดจริงบนมือถือ: (1) คีย์บอร์ดดันแผ่นจนไม่เห็นช่องที่กรอก
 *    (2) ปิดแผ่นแล้วข้อมูลหาย (3) ปุ่มย้อนของเบราว์เซอร์ปิดแผ่นแทนที่จะย้อนฟอร์ม
 *    เหตุผลทั้งสามใช้กับโมดัลที่เขียนมือด้วย ⇒ หน้านี้จึงเป็นหน้าเต็ม และ **ไม่ต้องมี
 *    Teleport/z-index workaround** ที่หน้าภาคเรียนต้องมีเพื่อหนี bottom nav เลย
 *
 * ⭐ **คอมโพเนนต์เดียวรับ 2 route** (`settings/years/new` · `settings/years/:id/edit`) —
 *    4 ฟิลด์เหมือนกันเป๊ะ ⇒ ถ้าแยกเป็นสองไฟล์ นิยาม "ยังไม่บันทึก" จะเพี้ยนจากกัน
 *
 * ⚠️ **หน้าแก้ไข refresh ได้จริง** ⇒ เรียก `getYear(id)` เองจาก URL ไม่พึ่ง router state
 *    (`GET /api/settings/years/{id}` ถูกเพิ่มในรอบนี้เพื่อเหตุผลนี้)
 *
 * ⚠️ **`is_current` มีเฉพาะตอนเพิ่ม** — ตอนแก้ต้องกดปุ่มในรายการ (backend ไม่รับ `is_current`
 *    ผ่าน PATCH) เพราะการเปลี่ยนปีปัจจุบันมีด่าน «ปีว่างตั้งเป็นปัจจุบันไม่ได้» + ต้อง
 *    เปลี่ยน DEFAULT ของ `students.academic_year_id` ในทรานแซกชันเดียวกัน
 */
const route = useRoute()
const router = useRouter()

const isEdit = computed(() => route.name === 'academic-year-edit')

/** id จาก URL — `null` เมื่อ path พาเลขที่ใช้ไม่ได้มา (`/settings/years/abc/edit` เข้าไม่ถึง
 *  ผ่านเมนู แต่ guard ไม่ได้กัน ⇒ ต้องมีสาขา "ไม่พบ" ของตัวเองอยู่ดี) */
const yearId = computed<number | null>(() => {
  const n = Number(route.params.id)
  return Number.isInteger(n) && n > 0 ? n : null
})

const form = ref<YearFormValues>({ ...EMPTY_YEAR_FORM })
const isCurrentOnCreate = ref(false)

const isLoading = ref(isEdit.value)
const loadError = ref(false)
const notFound = ref(false)
/** ปีที่โหลดมาถูก soft delete ไปแล้ว — GET คืนแถวจริง แต่ PATCH จะ 404 ⇒ ปิดปุ่มบันทึก */
const isDeleted = ref(false)
/** แถวที่โหลดมา (ใช้โชว์จำนวนสมาชิก + เตือนตอนเปิด `is_current` ตอนสร้าง) */
const loaded = ref<AcademicYear | null>(null)

const saving = ref(false)
const saveError = ref('')
/** บันทึกสำเร็จแล้ว — ปลดตาข่ายกันข้อมูลหายก่อนนำทางออก (ไม่งั้น Swal ถามซ้ำ) */
const saved = ref(false)

/** baseline สำหรับเทียบ "ยังไม่บันทึก" — ไม่ใช่ `EMPTY_YEAR_FORM` ตรง ๆ เพราะต้อง copy */
const baseline = ref<YearFormValues>({ ...EMPTY_YEAR_FORM })

async function load() {
  isLoading.value = true
  loadError.value = false
  notFound.value = false
  isDeleted.value = false
  try {
    if (yearId.value === null) {
      notFound.value = true
      loaded.value = null
      return
    }
    const y = await getYear(yearId.value)
    loaded.value = y
    isDeleted.value = y.deleted_at !== null
    form.value = toYearFormValues(y)
    baseline.value = { ...form.value }
  } catch (e) {
    // 404 ของ backend ("ไม่พบปีการศึกษานี้") แยกจาก error เครือข่าย — คนละทางออกให้ผู้ใช้
    if (isNotFound(e)) {
      notFound.value = true
    } else {
      loadError.value = true
    }
  } finally {
    isLoading.value = false
  }
}

/** ตรวจว่า error คือ 404 — `services/api.ts` แปลงเป็น Error ที่มีข้อความไทย ไม่มี status
 *  ⇒ ดูจาก `status` ถ้ามี ไม่งั้นเทียบข้อความ (ข้อความมาจาก backend จุดเดียว) */
function isNotFound(e: unknown): boolean {
  if (e && typeof e === 'object' && 'status' in e && (e as { status?: number }).status === 404) {
    return true
  }
  return errorText(e).includes('ไม่พบปีการศึกษา')
}

onMounted(() => {
  window.addEventListener('beforeunload', onBeforeUnload)
  if (isEdit.value) load()
})

const formError = computed(() => yearFormError(form.value))

/** ยังไม่บันทึกและมีอะไรให้เสีย — ตรรกะนี้เป็นตัวตัดสินว่าจะถามผู้ใช้ไหม (ดู onBeforeRouteLeave)
 *  ⚠️ ปิดการถามเมื่อ: กำลังโหลด / โหลดพัง / ไม่พบแถว / ถูกลบแล้ว / บันทึกไปแล้ว
 *     — ทั้งหมดคือกรณีที่ "ข้อมูลในฟอร์ม" ไม่ใช่สิ่งที่ผู้ใช้ตั้งใจกรอก */
const isDirty = computed(() => {
  if (isLoading.value || loadError.value || notFound.value || isDeleted.value || saved.value) {
    return false
  }
  const b = baseline.value
  const f = form.value
  if (isCurrentOnCreate.value) return true
  return (
    b.year_be !== f.year_be ||
    b.name !== f.name ||
    b.start_date !== f.start_date ||
    b.end_date !== f.end_date
  )
})

function errorText(e: unknown): string {
  if (typeof e === 'string') return e
  if (e instanceof Error) return e.message
  return 'เกิดข้อผิดพลาดที่ไม่รู้จัก'
}

function onBeforeUnload(e: BeforeUnloadEvent) {
  if (!isDirty.value) return
  e.preventDefault()
}
onBeforeUnmount(() => window.removeEventListener('beforeunload', onBeforeUnload))

// 🕸️ ตาข่ายกันข้อมูลหาย — การนำทางออกทุกเส้นทางต้องผ่านคำถาม (ยกเว้นตอนบันทึกสำเร็จ)
onBeforeRouteLeave(async () => {
  if (!isDirty.value) return true
  const res = await Swal.fire({
    title: 'ยังไม่ได้บันทึก',
    text: 'ข้อมูลที่กรอกไว้จะหายไปถ้าออกตอนนี้',
    icon: 'warning',
    showCancelButton: true,
    confirmButtonText: 'ออกโดยไม่บันทึก',
    confirmButtonColor: BRAND,
    cancelButtonText: 'อยู่ต่อ',
  })
  return res.isConfirmed
})

function goBack() {
  router.push({ name: 'academic-years' })
}

async function save() {
  if (formError.value) return
  saving.value = true
  saveError.value = ''
  try {
    if (!isEdit.value) {
      await createYear({
        ...yearFormToPayload(form.value),
        is_current: isCurrentOnCreate.value,
      })
    } else if (yearId.value !== null) {
      // PATCH ส่งเฉพาะฟิลด์ที่แก้จริง — ไม่งั้นจะไปทับค่าที่คนอื่นเพิ่งแก้
      const payload: AcademicYearUpdatePayload = {}
      const f = form.value
      const b = baseline.value
      if (f.year_be.trim() !== b.year_be.trim()) payload.year_be = Number(f.year_be.trim())
      if (f.name.trim() !== b.name.trim()) payload.name = f.name.trim()
      if (f.start_date !== b.start_date) payload.start_date = f.start_date || null
      if (f.end_date !== b.end_date) payload.end_date = f.end_date || null
      if (Object.keys(payload).length === 0) {
        // ไม่มีอะไรเปลี่ยน = ไม่ต้องยิง API (และไม่ต้องรายงานว่า "บันทึกแล้ว" ทั้งที่ไม่มีอะไรเกิด)
        saved.value = true
        goBack()
        return
      }
      await updateYear(yearId.value, payload)
    }
    saved.value = true
    await Swal.fire({
      icon: 'success',
      title: isEdit.value ? 'บันทึกแล้ว' : 'เพิ่มปีการศึกษาแล้ว',
      // ตอนสร้าง: เตือนว่ายัง **ไม่ใช่** ปีปัจจุบัน ถ้าผู้ใช้ไม่ได้ติ๊ก
      text:
        !isEdit.value && !isCurrentOnCreate.value
          ? 'ปีนี้ยังไม่ใช่ปีปัจจุบัน — กด «ใช้เป็นปีปัจจุบัน» ในรายการเมื่อพร้อม'
          : undefined,
      timer: isEdit.value ? 1200 : 1800,
      showConfirmButton: false,
    })
    goBack()
  } catch (e) {
    // เก็บไว้ในฟอร์ม ไม่นำทางออก — ผู้ใช้จะได้แก้แล้วกดซ้ำได้เลย
    // ⚠️ ด่าน «ปีว่างตั้งเป็นปัจจุบันไม่ได้» + «ปี พ.ศ. ซ้ำ» เด้งมาที่นี่ ข้อความไทยบอกทางออกอยู่แล้ว
    saveError.value = errorText(e)
  } finally {
    saving.value = false
  }
}

const inputCls =
  'mt-1 block w-full rounded-control border border-line bg-surface px-3.5 py-2.5 text-sm text-ink-1 outline-none transition-colors placeholder:text-ink-3 focus:border-brand focus:ring-2 focus:ring-brand/10'
</script>

<template>
  <div class="mx-auto max-w-2xl">
    <!-- Loading skeleton -->
    <div v-if="isLoading" class="space-y-4" aria-busy="true">
      <div class="h-6 w-56 animate-pulse rounded bg-canvas"></div>
      <div class="space-y-5 rounded-card border border-line bg-surface p-6 sm:p-8">
        <div v-for="i in 4" :key="i" class="space-y-2">
          <div class="h-3 w-24 animate-pulse rounded bg-canvas"></div>
          <div class="h-10 animate-pulse rounded-control bg-canvas"></div>
        </div>
      </div>
    </div>

    <!-- ไม่พบปีนี้ -->
    <AppCard v-else-if="notFound" :padded="false" class="py-4">
      <AppEmptyState
        icon="bi-mortarboard"
        title="ไม่พบปีการศึกษานี้"
        description="อาจถูกลบถาวรไปแล้ว หรือลิงก์ไม่ถูกต้อง"
      >
        <AppButton variant="secondary" @click="goBack">
          <template #icon><i class="bi bi-arrow-left" aria-hidden="true" /></template>
          กลับหน้าปีการศึกษา
        </AppButton>
      </AppEmptyState>
    </AppCard>

    <!-- โหลดพัง -->
    <AppCard v-else-if="loadError" :padded="false" class="py-4">
      <AppEmptyState
        icon="bi-plugin"
        title="โหลดข้อมูลปีการศึกษาไม่สำเร็จ"
        description="ตรวจสอบการเชื่อมต่อแล้วลองอีกครั้ง"
      >
        <AppButton variant="secondary" @click="load">
          <template #icon><i class="bi bi-arrow-clockwise" aria-hidden="true" /></template>
          ลองใหม่
        </AppButton>
      </AppEmptyState>
    </AppCard>

    <form v-else @submit.prevent="save" class="space-y-4">
      <!-- 🔴 ไม่มี <h1> ที่นี่ — `AppHeader` วาดชื่อหน้าจาก `routeTitles` เป็น <h1> ให้แล้ว
           ที่เหลือคือ *ชื่อปีที่กำลังแก้* ซึ่งเป็นเนื้อหา ไม่ใช่ชื่อหน้า -->
      <p v-if="isEdit && loaded" class="truncate text-sm text-ink-2">
        <i class="bi bi-mortarboard mr-1 text-ink-3" aria-hidden="true" />{{ loaded.name }}
      </p>

      <!-- ถูกลบแล้ว (soft delete) — GET คืนแถวตามจริง แต่ PATCH จะ 404 ⇒ ปิดปุ่มบันทึกไว้ก่อน -->
      <div
        v-if="isDeleted"
        class="flex items-start gap-2.5 rounded-card border border-line bg-canvas px-4 py-3.5"
      >
        <i class="bi bi-trash3 mt-0.5 text-danger" aria-hidden="true" />
        <div class="text-[13px] text-ink-1">
          <p class="font-bold">ปีนี้ถูกลบแล้ว — แก้ไขไม่ได้จนกว่าจะกู้คืน</p>
          <p class="mt-0.5 text-ink-2">
            กลับไปหน้ารายการ แล้วกด «กู้คืน» ในปีนี้ก่อน
          </p>
        </div>
      </div>

      <!-- ตอนสร้าง: ยังไม่ติ๊ก "เป็นปีปัจจุบัน" (ค่าตั้งต้น) — บอกให้ชัดว่าไม่ใช่ของที่ลืม -->
      <div
        v-else-if="!isEdit"
        class="rounded-card bg-canvas px-4 py-3 text-[12px] leading-relaxed text-ink-2"
      >
        <i class="bi bi-info-circle mr-1" aria-hidden="true" />
        ปีใหม่จะถูกสร้างเป็น <b>ปีธรรมดา</b> — รายชื่อทั้งโรงเรียนยังชี้ปีเดิมอยู่
        จนกว่าจะนำเข้ารายชื่อปีใหม่แล้วกด «ใช้เป็นปีปัจจุบัน»
      </div>

      <div class="space-y-5 rounded-card border border-line bg-surface p-6 sm:p-8">
        <!-- พ.ศ. — หัวใจของแถวนี้ -->
        <div>
          <label for="year-be" class="block text-xs font-semibold text-ink-2">
            ปีการศึกษา (พ.ศ.) <span class="text-brand">*</span>
          </label>
          <input
            id="year-be"
            v-model="form.year_be"
            type="text"
            inputmode="numeric"
            maxlength="4"
            placeholder="เช่น 2569"
            :class="inputCls"
          />
          <!-- ⚠️ ต้องย้ำว่า พ.ศ. ไม่ใช่ ค.ศ. — ระบบนี้แสดง พ.ศ. ทั้งหมด แต่คนมักพิมพ์ 2026
               ซึ่งจะผ่านช่วง 2400–2700 ไม่ได้ (ดักไว้แล้ว) ⇒ คำใบ้ต้องมาก่อน ไม่ใช่หลัง -->
          <p class="mt-1 text-[11px] text-ink-3">
            ใส่เป็น <b>พุทธศักราช</b> เช่น 2569 (ไม่ใช่ ค.ศ. 2026) — ช่วงที่รับคือ 2400–2700
          </p>
        </div>

        <div>
          <label for="year-name" class="block text-xs font-semibold text-ink-2">
            ชื่อที่แสดง
          </label>
          <input
            id="year-name"
            v-model="form.name"
            type="text"
            maxlength="50"
            :placeholder="form.year_be ? `ปีการศึกษา ${form.year_be}` : 'เว้นว่าง = ปีการศึกษา {พ.ศ.}'"
            :class="inputCls"
          />
          <p class="mt-1 text-[11px] text-ink-3">
            เว้นว่างได้ — ระบบจะตั้งเป็น «ปีการศึกษา {{ form.year_be || '…' }}» ให้เอง
          </p>
        </div>

        <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <label for="year-start" class="block text-xs font-semibold text-ink-2">
              วันเปิดปี
            </label>
            <input id="year-start" v-model="form.start_date" type="date" :class="inputCls" />
          </div>
          <div>
            <label for="year-end" class="block text-xs font-semibold text-ink-2">
              วันสิ้นสุดปี
            </label>
            <input id="year-end" v-model="form.end_date" type="date" :class="inputCls" />
          </div>
        </div>
        <!-- ⚠️ วันที่ **ไม่บังคับ** ต่างจากภาคเรียน — ปีที่ยังไม่รู้กำหนดเปิดเทอมต้องสร้างได้
             (ใช้ติดป้าย "วันนี้อยู่ในช่วงนี้" เท่านั้น ไม่กระทบการกรองสมาชิก) -->
        <p class="text-[11px] text-ink-3">
          <i class="bi bi-info-circle mr-1" aria-hidden="true" />
          ไม่บังคับ — เว้นว่างได้ถ้ายังไม่รู้กำหนด (วันที่ใช้แค่ติดป้าย «วันนี้อยู่ในช่วงนี้»)
          · วันสิ้นสุด<b>รวมวันสุดท้ายด้วย</b>
        </p>

        <!-- ตั้งเป็นปีปัจจุบัน — เฉพาะตอนเพิ่ม (ตอนแก้ให้ใช้ปุ่มในรายการ) -->
        <label
          v-if="!isEdit"
          class="flex cursor-pointer items-start gap-3 rounded-card border border-line px-3.5 py-3 transition-colors hover:bg-canvas"
        >
          <input v-model="isCurrentOnCreate" type="checkbox" class="mt-0.5 h-4 w-4 shrink-0 accent-brand" />
          <span class="min-w-0">
            <span class="block text-[13px] font-bold text-ink-1">ใช้เป็นปีปัจจุบันทันที</span>
            <span class="mt-0.5 block text-[11px] leading-relaxed text-ink-2">
              ⚠️ ทำได้เฉพาะเมื่อ<b>ปีนี้มีสมาชิกอยู่แล้ว</b> หรือโรงเรียนยังไม่มีสมาชิกเลย —
              ถ้าปีอื่นยังมีคนอยู่ ระบบจะปฏิเสธ (กันรายชื่อทั้งโรงเรียนหายในคลิกเดียว)
            </span>
          </span>
        </label>

        <!-- สรุปว่ากำลังแก้ปีอะไร (โหมดแก้ไข) -->
        <div v-if="isEdit && loaded" class="rounded-card bg-canvas px-3.5 py-3 text-[12px] text-ink-2">
          <p>
            ปีนี้มีสมาชิก <b class="tabular-nums">{{ loaded.member_count }}</b> คน
            <span v-if="loaded.is_current" class="text-brand">· เป็นปีปัจจุบันอยู่</span>
          </p>
          <p class="mt-1">
            <i class="bi bi-exclamation-circle mr-1" aria-hidden="true" />แก้ «ปีการศึกษา (พ.ศ.)»
            มีผลกับชื่อปีและตัวเลขที่ใช้อ้างอิง — ถ้าแค่จะเปลี่ยนชื่อที่แสดง ให้แก้ «ชื่อที่แสดง» แทน
          </p>
        </div>

        <!-- error จาก server (เก็บไว้ในฟอร์ม ไม่นำทางออก) -->
        <div
          v-if="saveError"
          class="rounded-card border border-line bg-canvas px-3.5 py-2.5 text-[13px] text-danger"
        >
          <i class="bi bi-exclamation-circle mr-1" aria-hidden="true" />{{ saveError }}
        </div>
      </div>

      <div class="flex flex-wrap items-center justify-end gap-2">
        <p v-if="formError" class="mr-auto text-[12px] font-semibold text-ink-2">
          {{ formError }}
        </p>
        <AppButton variant="secondary" @click="goBack">ยกเลิก</AppButton>
        <AppButton
          type="submit"
          variant="primary"
          :loading="saving"
          :disabled="!!formError || isDeleted"
        >
          <template #icon><i class="bi bi-check-lg" aria-hidden="true" /></template>
          {{ isEdit ? 'บันทึก' : 'เพิ่มปีการศึกษา' }}
        </AppButton>
      </div>
    </form>
  </div>
</template>
