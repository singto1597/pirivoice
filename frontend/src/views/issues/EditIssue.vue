<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import Swal from 'sweetalert2'
import { getIssue, updateIssue } from '@/services/issue'
import { MAIN_CATEGORIES, type MainCategory, type Category } from '@/types/issue'
import { useAuthStore } from '@/stores/auth'
import AppCard from '@/components/ui/AppCard.vue'
import AppButton from '@/components/ui/AppButton.vue'
import AppEmptyState from '@/components/ui/AppEmptyState.vue'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()

const issueId = Number(route.params.id)
const mainCategory = ref<MainCategory | ''>('')
const category = ref<Category | ''>('')
const title = ref('')
const description = ref('')
const isAnonymous = ref(false)
const isLoading = ref(true) // โหลดข้อมูลเรื่อง
const isSaving = ref(false) // กำลังบันทึก
const loadError = ref('') // โหลดข้อมูลไม่สำเร็จ → แสดง inline + retry

function errMsg(e: unknown): string {
  return e instanceof Error ? e.message : String(e)
}

// เลือกหมวดหลัก + รีเซ็ตหมวดย่อย (แยกเป็นฟังก์ชัน กัน prettier หั่น inline handler ให้พัง)
function selectMainCategory(key: MainCategory) {
  mainCategory.value = key
  category.value = ''
}

// หมวดหมู่ย่อยตามหมวดหลักที่เลือก (ตรงกับ backend config/categories.json)
const availableCategories = computed<Category[]>(() => {
  if (!mainCategory.value) return []
  return Object.keys(MAIN_CATEGORIES[mainCategory.value].subcategories) as Category[]
})

async function loadIssue() {
  isLoading.value = true
  loadError.value = ''
  try {
    const issue = await getIssue(issueId)

    // ตรวจสิทธิ์: ผู้แจ้ง หรือ admin
    const isReporter = !!authStore.user && issue.reporter_id === authStore.user.id
    if (!isReporter && !authStore.isAdmin) {
      Swal.fire({
        icon: 'error',
        title: 'ไม่มีสิทธิ์แก้ไข',
        text: 'เฉพาะผู้แจ้งเรื่องเท่านั้นที่แก้ไขเรื่องนี้ได้',
      })
      router.replace({ name: 'issue-detail', params: { id: issueId } })
      return
    }
    // เรื่องปิดแล้ว → แก้ไม่ได้ (backend ก็บล็อกอยู่แล้ว — UI กันไว้ก่อน)
    if (['resolved', 'cancelled', 'rejected'].includes(issue.status)) {
      Swal.fire({
        icon: 'warning',
        title: 'เรื่องนี้ปิดแล้ว',
        text: 'ไม่สามารถแก้ไขเรื่องที่ปิดแล้วได้',
      })
      router.replace({ name: 'issue-detail', params: { id: issueId } })
      return
    }

    // prefill ข้อมูลเดิม
    mainCategory.value = issue.main_category
    category.value = issue.category
    title.value = issue.title
    description.value = issue.description
    isAnonymous.value = issue.is_anonymous
  } catch (e) {
    loadError.value = errMsg(e) || 'เกิดข้อผิดพลาด'
  } finally {
    isLoading.value = false
  }
}
onMounted(loadIssue)

async function handleSubmit() {
  if (!mainCategory.value) {
    Swal.fire({
      icon: 'warning',
      title: 'เลือกหมวดหลักก่อน',
      text: 'กรุณาเลือกหมวดหลัก (เสนอความคิดเห็น / สุขภาวะทางกายและใจ / แจ้งเหตุ)',
    })
    return
  }
  if (!category.value) {
    Swal.fire({ icon: 'warning', title: 'เลือกหมวดหมู่ก่อน', text: 'กรุณาเลือกหมวดหมู่ย่อย' })
    return
  }
  if (title.value.trim().length < 3) {
    Swal.fire({
      icon: 'warning',
      title: 'หัวข้อสั้นไป',
      text: 'กรุณากรอกหัวข้ออย่างน้อย 3 ตัวอักษร',
    })
    return
  }
  if (description.value.trim().length < 3) {
    Swal.fire({
      icon: 'warning',
      title: 'รายละเอียดสั้นไป',
      text: 'กรุณากรอกรายละเอียดอย่างน้อย 3 ตัวอักษร',
    })
    return
  }

  isSaving.value = true
  try {
    const updated = await updateIssue(issueId, {
      main_category: mainCategory.value,
      category: category.value,
      title: title.value.trim(),
      description: description.value.trim(),
      is_anonymous: isAnonymous.value,
    })
    Swal.fire({
      icon: 'success',
      title: 'บันทึกการแก้ไขแล้ว',
      text: 'ข้อมูลเรื่องถูกอัปเดตแล้ว',
      confirmButtonText: 'ตกลง',
    }).then(() => {
      router.push({ name: 'issue-detail', params: { id: updated.id } })
    })
  } catch (e) {
    Swal.fire({ icon: 'error', title: 'บันทึกไม่สำเร็จ', text: errMsg(e) || 'เกิดข้อผิดพลาด' })
  } finally {
    isSaving.value = false
  }
}
</script>

<template>
  <div class="max-w-2xl mx-auto">
    <!-- 🔴 ไม่มี <h1>/eyebrow ที่นี่ — `AppHeader` วาดชื่อหน้า (routeTitles) เป็น <h1> ให้แล้ว (R0.3)
         ปุ่ม ← ก็มาจาก `AppHeader` เช่นกัน (route นี้ไม่ประกาศ `headerBack` ⇒ ตกไปที่รากแท็บ "เรื่อง") -->

    <!-- โหลดข้อมูล: skeleton เนื้อหา -->
    <div v-if="isLoading" class="animate-pulse">
      <div class="rounded-2xl border border-stone-200 bg-white p-6 space-y-5">
        <div class="h-6 w-48 rounded-lg bg-stone-100"></div>
        <div class="grid grid-cols-2 gap-2 sm:grid-cols-3 sm:gap-3">
          <div v-for="n in 6" :key="n" class="h-24 rounded-xl bg-stone-100"></div>
        </div>
        <div class="h-40 rounded-xl bg-stone-100"></div>
        <div class="h-12 rounded-xl bg-stone-100"></div>
      </div>
    </div>

    <!-- โหลดไม่สำเร็จ: inline error + retry — 「ไม่มีการ์ดเส้นประ」 (AppEmptyState ไม่มี border-dashed โดยเจตนา) -->
    <AppCard v-else-if="loadError" :padded="false" class="py-4">
      <AppEmptyState icon="bi-exclamation-triangle" title="โหลดเรื่องนี้ไม่สำเร็จ" :description="loadError">
        <AppButton variant="secondary" @click="loadIssue">
          <template #icon><i class="bi bi-arrow-clockwise" aria-hidden="true" /></template>
          ลองอีกครั้ง
        </AppButton>
      </AppEmptyState>
    </AppCard>

    <template v-else>
      <!-- Step 1: หมวดหลัก -->
      <div class="mb-6">
        <label class="block text-sm font-medium text-stone-700 mb-2">1. เลือกหมวดหลัก</label>
        <div class="grid grid-cols-2 gap-2 sm:grid-cols-3 sm:gap-3">
          <button
            v-for="(info, key) in MAIN_CATEGORIES"
            :key="key"
            type="button"
            @click="selectMainCategory(key as MainCategory)"
            class="p-3 sm:p-4 min-h-[88px] sm:min-h-0 rounded-xl border-2 text-center transition flex flex-col items-center justify-center"
            :class="
              mainCategory === key
                ? 'border-brand bg-red-50 text-brand'
                : 'border-stone-200 hover:border-brand'
            "
          >
            <div class="text-xl sm:text-2xl mb-1">
              <i v-if="key === 'suggestion'" class="bi bi-lightbulb"></i>
              <i v-else-if="key === 'wellbeing'" class="bi bi-heart-pulse"></i>
              <i v-else class="bi bi-exclamation-triangle"></i>
            </div>
            <div class="text-xs sm:text-sm font-medium leading-snug break-words">
              {{ info.label }}
            </div>
          </button>
        </div>
      </div>

      <!-- Step 2: หมวดหมู่ย่อย -->
      <div v-if="mainCategory" class="mb-6">
        <label class="block text-sm font-medium text-stone-700 mb-2">2. เลือกหมวดหมู่</label>
        <div class="flex flex-wrap gap-2">
          <button
            v-for="c in availableCategories"
            :key="c"
            type="button"
            @click="category = c"
            class="inline-flex items-center px-4 min-h-11 py-2 rounded-full border text-sm transition"
            :class="
              category === c
                ? 'bg-brand text-white border-brand'
                : 'border-stone-300 hover:border-brand'
            "
          >
            {{ MAIN_CATEGORIES[mainCategory as MainCategory].subcategories[c] }}
          </button>
        </div>
      </div>

      <!-- Step 3: รายละเอียด -->
      <form @submit.prevent="handleSubmit" class="space-y-4">
        <div>
          <label class="block text-sm font-medium text-stone-700 mb-1">3. หัวข้อ</label>
          <input
            v-model="title"
            type="text"
            class="w-full px-3 py-2 border border-stone-300 rounded-lg"
            placeholder="สรุปสั้นๆ ว่าเรื่องอะไร"
            maxlength="200"
          />
        </div>
        <div>
          <label class="block text-sm font-medium text-stone-700 mb-1">4. รายละเอียด</label>
          <textarea
            v-model="description"
            rows="5"
            class="w-full px-3 py-2 border border-stone-300 rounded-lg"
            placeholder="อธิบายปัญหาหรือความคิดเห็นให้ละเอียด..."
          ></textarea>
        </div>

        <label class="flex items-center gap-2 text-sm text-stone-700 cursor-pointer select-none">
          <input
            v-model="isAnonymous"
            type="checkbox"
            class="w-4 h-4 rounded bg-white border-stone-300 accent-brand"
          />
          <span>ซ่อนชื่อฉัน (แจ้งแบบไม่ระบุชื่อ)</span>
        </label>

        <div class="flex gap-3">
          <button
            type="button"
            @click="router.push({ name: 'issue-detail', params: { id: issueId } })"
            class="px-4 py-3 border border-stone-200 text-stone-700 rounded-xl hover:bg-stone-50 font-medium"
          >
            ยกเลิก
          </button>
          <button
            type="submit"
            :disabled="isSaving"
            class="flex-1 py-3 bg-brand text-white rounded-xl hover:bg-brand-strong disabled:opacity-50 disabled:pointer-events-none font-semibold"
          >
            {{ isSaving ? 'กำลังบันทึก...' : 'บันทึกการแก้ไข' }}
          </button>
        </div>
      </form>
    </template>
  </div>
</template>
