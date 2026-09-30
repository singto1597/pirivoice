<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { getPlaybookById, playbookVolume, PLAYBOOKS } from '@/types/playbook'

const route = useRoute()

// เล่มที่กำลังอ่าน — ใช้ id จาก URL (เล่มใหม่ผ่าน sidebar → route change → computed ใหม่)
const playbook = computed(() => getPlaybookById(String(route.params.id)))

// หมายเลขหน้า [1..totalPages] — จำนวนมาจากไฟล์รูปที่วางจริงใน public/playbooks/volN/
const pageNumbers = computed(() =>
  playbook.value ? Array.from({ length: playbook.value.totalPages }, (_, i) => i + 1) : [],
)

// ชื่อไฟล์หน้าแบบเลข 0 นำหน้าเสมอ: page-01.webp, page-02.webp, …
const pageSrc = (n: number): string =>
  playbook.value ? `${playbook.value.basePath}page-${String(n).padStart(2, '0')}.webp` : ''

// ปก — โหลดแบบ eager (กันกระตุกตอนเข้าหน้า) ใช้เป็นสถานะกำลังโหลด
const coverLoaded = ref(false)

// หน้าที่ไฟล์จริงยังไม่ครบ (404) → ซ่อน + โชว์ placeholder แทนรูปกากบาท
const failedPages = ref<Set<number>>(new Set())
function onPageError(n: number) {
  failedPages.value = new Set([...failedPages.value, n])
}

// เล่มถัดไป (สำหรับการ์ดท้ายเล่ม)
const nextPlaybook = computed(() => {
  if (!playbook.value) return undefined
  const idx = PLAYBOOKS.findIndex((p) => p.id === playbook.value!.id)
  return idx >= 0 ? PLAYBOOKS[idx + 1] : undefined
})

// ⏳ scroll progress — attach กับ scroll container จริง (main ของ MainLayout)
const progress = ref(0)
const scrollParent = ref<HTMLElement | null>(null)
const rootEl = ref<HTMLElement | null>(null)

function getScrollParent(el: HTMLElement | null): HTMLElement | null {
  let node: HTMLElement | null = el
  while (node && node !== document.body) {
    if (/(auto|scroll|overlay)/.test(getComputedStyle(node).overflowY)) return node
    node = node.parentElement
  }
  return null
}

function updateProgress() {
  const sp = scrollParent.value
  if (!sp) return
  const { scrollTop, scrollHeight, clientHeight } = sp
  const max = scrollHeight - clientHeight
  progress.value = max > 0 ? Math.min(100, Math.round((scrollTop / max) * 100)) : 0
}

onMounted(() => {
  scrollParent.value = getScrollParent(rootEl.value)
  scrollParent.value?.addEventListener('scroll', updateProgress, { passive: true })
  updateProgress()
})

onBeforeUnmount(() => {
  scrollParent.value?.removeEventListener('scroll', updateProgress)
})

const volumeLabel = computed(() => (playbook.value ? `เล่มที่ ${playbookVolume(playbook.value.id)}` : ''))
</script>

<template>
  <div v-if="playbook" ref="rootEl">
    <!-- ⏳ แถบความคืบหน้าการอ่าน (ติดกับ header — ไม่งงกับ mobile header ของ layout) -->
    <header class="sticky top-0 z-40 bg-white border-b border-stone-200">
      <div class="max-w-3xl mx-auto px-3 sm:px-4 py-3 flex items-center gap-3">
        <RouterLink
          to="/playbooks"
          class="btn-ghost-ui !py-2 !px-2.5 shrink-0"
          title="กลับไปหน้าคู่มือ"
        >
          <i class="bi bi-arrow-left text-base"></i>
        </RouterLink>
        <div class="min-w-0 flex-1">
          <p class="text-[10px] sm:text-[11px] text-stone-500 font-bold uppercase tracking-widest leading-none mb-1">
            {{ volumeLabel }} · P.R. Playbooks
          </p>
          <h1 class="text-sm sm:text-base font-bold text-stone-900 truncate leading-tight">{{ playbook.title }}</h1>
        </div>
        <a :href="playbook.pdfUrl" download class="btn-gradient !py-2 !px-3 sm:!px-4 text-xs sm:text-sm shrink-0">
          <i class="bi bi-file-earmark-pdf text-sm sm:text-base"></i>
          <span class="hidden sm:inline">ดาวน์โหลด PDF ต้นฉบับ</span>
          <span class="sm:hidden">ดาวน์โหลด</span>
        </a>
      </div>
      <div class="h-0.5 bg-stone-100">
        <div
          class="h-full bg-brand transition-[width] duration-150 ease-out"
          :style="{ width: `${progress}%` }"
        ></div>
      </div>
    </header>

    <!-- เนื้อหาหนังสือ (Webtoon reader — เลื่อนลงเรื่อย ๆ) -->
    <div class="max-w-3xl mx-auto px-3 sm:px-4 py-5 sm:py-7">
      <!-- 🔖 ปก -->
      <div class="relative mb-4 sm:mb-6 bg-stone-100 rounded-2xl overflow-hidden border border-stone-200">
        <img
          :src="playbook.coverImage"
          :alt="`ปก ${playbook.title}`"
          class="w-full h-auto object-cover"
          @load="coverLoaded = true"
        />
        <div v-if="!coverLoaded" class="absolute inset-0 flex items-center justify-center">
          <div class="animate-spin w-8 h-8 border-4 border-brand border-t-transparent rounded-full"></div>
        </div>
      </div>

      <!-- 📄 หน้าทั้งหมด ต่อกันลงมาแนวตั้ง กลางจอ (flex-col, items-center)
           ใช้ v-for ตาม totalPages + ชื่อไฟล์เลข 0 นำหน้า + lazy load -->
      <div class="flex flex-col items-center gap-2 sm:gap-3">
        <template v-for="n in pageNumbers" :key="n">
          <img
            v-if="!failedPages.has(n)"
            :src="pageSrc(n)"
            :alt="`${playbook.title} — หน้า ${n}`"
            loading="lazy"
            @error="onPageError(n)"
            class="w-full max-w-3xl h-auto rounded-xl bg-stone-50"
          />
        </template>
      </div>

      <!-- หน้าที่ไฟล์ไม่ครบ -->
      <div v-if="failedPages.size > 0" class="mt-4 rounded-xl bg-brand/10 border border-brand/20 px-4 py-3 text-center">
        <p class="text-sm text-brand">
          <i class="bi bi-exclamation-triangle mr-1.5"></i>
          หน้ายังมาไม่ครบตามที่ระบุ ({{ failedPages.size }} หน้า) — รอผู้ดูแลอัปเดตไฟล์ก่อน
        </p>
      </div>

      <!-- 🏁 สิ้นสุดเล่ม -->
      <div class="mt-8 flex items-center justify-center gap-3 text-stone-400">
        <div class="h-px w-14 sm:w-20 bg-stone-200"></div>
        <span class="text-xs font-semibold tracking-widest">จบเล่ม</span>
        <div class="h-px w-14 sm:w-20 bg-stone-200"></div>
      </div>

      <!-- เล่มถัดไป -->
      <RouterLink
        v-if="nextPlaybook"
        :to="{ name: 'playbook-reader', params: { id: nextPlaybook.id } }"
        class="mt-4 page-card p-4 flex items-center gap-4 card-hover"
      >
        <div class="w-12 h-16 rounded-lg overflow-hidden border border-stone-200 bg-stone-100 shrink-0">
          <img :src="nextPlaybook.coverImage" :alt="`ปก ${nextPlaybook.title}`" loading="lazy" class="w-full h-full object-cover" />
        </div>
        <div class="min-w-0 flex-1">
          <p class="text-[10px] text-brand font-bold uppercase tracking-widest mb-0.5">อ่านเล่มถัดไป</p>
          <p class="font-semibold text-stone-800 truncate">{{ nextPlaybook.title }}</p>
        </div>
        <i class="bi bi-arrow-right text-xl text-brand shrink-0"></i>
      </RouterLink>

      <!-- กลับขึ้นบน -->
      <div class="mt-6 text-center">
        <button
          type="button"
          class="btn-ghost-ui !py-2 !px-3 text-xs"
          @click="scrollParent?.scrollTo({ top: 0, behavior: 'smooth' })"
        >
          <i class="bi bi-arrow-up mr-1"></i> กลับขึ้นบน
        </button>
      </div>
    </div>
  </div>

  <!-- 404 เล่มไม่พบ -->
  <div v-else class="text-center py-20">
    <div class="text-5xl mb-4"><i class="bi bi-journal-x text-stone-300"></i></div>
    <h1 class="text-lg font-bold text-stone-700 mb-2">ไม่พบเล่มที่ระบุ</h1>
    <p class="text-sm text-stone-400 mb-6">ลิงก์นี้อาจไม่ถูกต้อง หรือเล่มถูกนำออกจากคู่มือแล้ว</p>
    <RouterLink to="/playbooks" class="btn-gradient">กลับไปหน้าคู่มือ</RouterLink>
  </div>
</template>
