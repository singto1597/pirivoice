<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { listBoards } from '@/services/board'
import { BOARD_TYPE_LABELS, boardTypeIcon, type BoardSummary, type BoardType } from '@/types/board'
import PaginationBar from '@/components/PaginationBar.vue'
import QuickSuggestionModal from '@/components/boards/QuickSuggestionModal.vue'

/**
 * 📋 PIRI Boards — feed สาธารณะ (PIRI Vote + PIRI Talk + ข้อเสนอแนะ)
 * กรองตามประเภท (ทั้งหมด/โหวต/พูดคุย/ข้อเสนอแนะ) + ค้นหา + แบ่งหน้า
 * + ปุ่ม "เสนอไอเดีย" (E1) — ผู้ใช้ทั่วไปสร้างบอร์ดข้อเสนอได้เองโดยไม่ผ่านสภา
 *
 * ⚠️ ชนิดที่เพิ่มเข้ามาต้องกรองได้ทาง `?board_type=` ซึ่ง backend จำกัดด้วย
 *    `Query(pattern="^(vote|talk|suggestion)$")` ⇒ ค่าที่นี่ต้องเป็นหนึ่งในสามเท่านั้น
 */
const router = useRouter()
const boards = ref<BoardSummary[]>([])
const total = ref(0)
const isLoading = ref(true)
const error = ref('')
const typeFilter = ref<'' | BoardType>('') // '' = ทั้งหมด
const q = ref('')
const page = ref(1)
const pageSize = 12
const showSuggestionModal = ref(false)

// แท็บกรองประเภท
const TABS: Array<{ value: '' | BoardType; label: string; icon: string }> = [
  { value: '', label: 'ทั้งหมด', icon: 'bi bi-grid' },
  { value: 'vote', label: 'โหวต', icon: 'bi bi-bar-chart-fill' },
  { value: 'talk', label: 'พูดคุย', icon: 'bi bi-chat-dots-fill' },
  { value: 'suggestion', label: 'ข้อเสนอแนะ', icon: 'bi bi-lightbulb-fill' },
]

onMounted(load)

// สร้างข้อเสนอสำเร็จ → พาไปหน้า detail ของบอร์ดที่เพิ่งสร้าง (ตรงกับที่ ApproveBoardModal ทำ)
function onSuggestionCreated(boardId: number) {
  router.push({ name: 'board-detail', params: { id: boardId } })
}

// ค้นหา (debounce 300ms) → กลับหน้า 1
let timer: ReturnType<typeof setTimeout> | undefined
watch(q, () => {
  clearTimeout(timer)
  timer = setTimeout(() => {
    page.value = 1
    load()
  }, 300)
})

function switchType(t: '' | BoardType) {
  typeFilter.value = t
  page.value = 1
  load()
}

function onPageChange(n: number) {
  page.value = n
  load()
}

async function load() {
  isLoading.value = true
  error.value = ''
  try {
    const res = await listBoards({
      board_type: typeFilter.value || undefined,
      q: q.value.trim() || undefined,
      limit: pageSize,
      offset: (page.value - 1) * pageSize,
    })
    boards.value = res.items
    total.value = res.total
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'โหลดข้อมูลไม่สำเร็จ'
  } finally {
    isLoading.value = false
  }
}

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString('th-TH', {
    timeZone: 'Asia/Bangkok',
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  })
}
</script>

<template>
  <div>
    <!-- Editorial header -->
    <div class="mb-6">
      <p class="text-[11px] font-bold uppercase tracking-widest text-[#B91C1C] mb-1.5">
        <i class="bi bi-columns-gap mr-1"></i> Public Forum
      </p>
      <h1 class="text-2xl sm:text-3xl font-bold tracking-tight text-stone-900 leading-tight">PIRI Boards</h1>
      <p class="text-sm text-stone-500 mt-1.5">
        โหวต + พูดคุยสาธารณะ ที่สภานักเรียนอนุมัติแล้ว · ข้อเสนอแนะจากทุกคน
      </p>
    </div>

    <!-- ปุ่มเสนอไอเดีย (E1) — ทุกคนที่ล็อกอินกดได้ ขึ้นบอร์ดทันที ไม่ต้องรอสภา -->
    <button
      type="button"
      data-testid="open-suggestion"
      @click="showSuggestionModal = true"
      class="mb-5 w-full sm:w-auto inline-flex items-center justify-center gap-2 rounded-xl bg-[#B91C1C] px-5 py-3 text-sm font-bold text-white hover:bg-[#991B1B] transition-colors"
    >
      <i class="bi bi-lightbulb"></i> เสนอไอเดีย
    </button>

    <!-- แถบกรอง + ค้นหา -->
    <div class="flex flex-wrap items-center gap-2 mb-5">
      <div class="flex gap-1 p-1 bg-stone-100 rounded-xl">
        <button
          v-for="t in TABS"
          :key="t.value"
          type="button"
          @click="switchType(t.value)"
          class="px-3.5 py-2 rounded-lg text-sm font-medium transition flex items-center gap-1.5"
          :class="typeFilter === t.value ? 'bg-white border border-stone-200 text-[#B91C1C]' : 'text-stone-500 hover:text-stone-700'"
        >
          <i :class="t.icon"></i> {{ t.label }}
        </button>
      </div>

      <div class="relative flex-1 min-w-[180px] sm:flex-none sm:w-72">
        <i class="bi bi-search absolute left-3 top-1/2 -translate-y-1/2 text-stone-400 text-sm"></i>
        <input
          v-model="q"
          type="search"
          placeholder="ค้นหาบอร์ด..."
          class="w-full pl-9 pr-3 py-2.5 border border-stone-300 rounded-xl text-sm bg-white focus:ring-2 focus:ring-[#B91C1C]"
        />
      </div>

      <span class="text-sm text-stone-400 ml-auto tabular-nums">{{ total.toLocaleString('en-US') }} บอร์ด</span>
    </div>

    <!-- โหลด: skeleton การ์ด -->
    <div v-if="isLoading" class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
      <div v-for="n in 6" :key="n" class="page-card p-5 flex flex-col gap-3">
        <div class="flex items-center justify-between">
          <div class="h-5 w-16 bg-stone-100 animate-pulse rounded-md"></div>
          <div class="h-3 w-14 bg-stone-100 animate-pulse rounded"></div>
        </div>
        <div class="h-5 w-3/4 bg-stone-100 animate-pulse rounded"></div>
        <div class="h-4 w-full bg-stone-100 animate-pulse rounded"></div>
        <div class="h-4 w-5/6 bg-stone-100 animate-pulse rounded"></div>
        <div class="h-4 w-full bg-stone-100 animate-pulse rounded mt-auto"></div>
      </div>
    </div>

    <!-- ข้อผิดพลาด -->
    <div v-else-if="error" class="border-2 border-dashed border-stone-200 rounded-2xl py-20 px-6 text-center">
      <i class="bi bi-wifi-off text-3xl text-stone-300 mb-3 inline-block"></i>
      <p class="text-stone-600 font-medium">{{ error }}</p>
      <button
        type="button"
        @click="load"
        class="mt-5 inline-flex items-center gap-2 rounded-lg bg-[#B91C1C] px-5 py-2.5 text-sm font-bold text-white hover:bg-[#991B1B] transition-colors"
      >
        <i class="bi bi-arrow-clockwise"></i> ลองอีกครั้ง
      </button>
    </div>

    <!-- ว่าง -->
    <div v-else-if="!boards.length" class="border border-dashed border-stone-200 rounded-2xl bg-white p-12 text-center text-stone-400">
      <div class="text-4xl mb-2"><i class="bi bi-columns-gap"></i></div>
      <p class="text-stone-500">ยังไม่มีบอร์ดในเงื่อนไขนี้</p>
    </div>

    <div v-else class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
      <RouterLink
        v-for="b in boards"
        :key="b.id"
        :to="{ name: 'board-detail', params: { id: b.id } }"
        class="page-card card-hover p-5 flex flex-col"
      >
        <div class="flex items-center justify-between mb-2">
          <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-stone-100 text-stone-600 text-[11px] font-semibold">
            <i :class="boardTypeIcon(b.board_type)"></i> {{ BOARD_TYPE_LABELS[b.board_type] }}
          </span>
          <span class="text-xs text-stone-400">{{ fmtDate(b.created_at) }}</span>
        </div>

        <h3 class="font-semibold text-stone-900 leading-snug mb-1 line-clamp-2">{{ b.title }}</h3>
        <p class="text-sm text-stone-500 mb-3 line-clamp-2">{{ b.description }}</p>

        <div class="mt-auto">
          <div v-if="b.tags.length" class="flex flex-wrap gap-1.5 mb-3">
            <span v-for="tag in b.tags.slice(0, 4)" :key="tag" class="px-2 py-0.5 bg-stone-100 text-stone-600 text-[11px] rounded-full">
              #{{ tag }}
            </span>
          </div>
          <div class="flex items-center justify-between text-xs text-stone-500 pt-2 border-t border-stone-200">
            <span class="truncate">
              <i class="bi bi-person mr-1"></i>
              {{ b.is_anonymous ? 'ไม่ระบุชื่อ' : b.author_name || 'สภานักเรียน' }}
            </span>
            <span class="flex items-center gap-3 shrink-0 ml-2">
              <span v-if="b.board_type === 'vote'"><i class="bi bi-bar-chart mr-1"></i>{{ b.total_votes.toLocaleString('en-US') }}</span>
              <span v-else><i class="bi bi-chat-left-text mr-1"></i>{{ b.comment_count.toLocaleString('en-US') }}</span>
            </span>
          </div>
        </div>
      </RouterLink>
    </div>

    <PaginationBar :total="total" :page="page" :page-size="pageSize" :loading="isLoading" @page-change="onPageChange" />

    <QuickSuggestionModal v-model:open="showSuggestionModal" @created="onSuggestionCreated" />
  </div>
</template>
