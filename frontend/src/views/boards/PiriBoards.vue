<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { listBoards } from '@/services/board'
import { BOARD_TYPE_LABELS, boardTypeIcon, type BoardSummary, type BoardType } from '@/types/board'
import PaginationBar from '@/components/PaginationBar.vue'
import QuickSuggestionModal from '@/components/boards/QuickSuggestionModal.vue'
import AppCard from '@/components/ui/AppCard.vue'
import AppChip from '@/components/ui/AppChip.vue'
import AppButton from '@/components/ui/AppButton.vue'
import AppEmptyState from '@/components/ui/AppEmptyState.vue'
import { fmtRelative } from '@/datetime'

/**
 * 📋 PIRI Boards — รายการบอร์ดสาธารณะ (PIRI Vote + PIRI Talk + ข้อเสนอแนะ)
 *
 * ⚠️ ชนิดที่กรองได้ต้องเป็นหนึ่งในสามนี้เท่านั้น — backend จำกัดด้วย
 *    `Query(pattern="^(vote|talk|suggestion)$")` ⇒ เพิ่มชนิดใหม่ต้องแก้ backend ก่อน
 *
 * 🔴 **ไม่มี `<h1>` และไม่มี eyebrow ในไฟล์นี้** — `<h1>` ของหน้าอยู่ที่ `AppHeader`
 *    (R0.3) และ `routeTitles.boards = 'บอร์ด'` แสดงอยู่แล้ว ⇒ ชื่อเรื่องซ้ำสองที่
 *    ⚠️ และ **ห้ามใส่ `uppercase tracking-*` กับข้อความไทย** — ภาษาไทยไม่มีตัวพิมพ์ใหญ่
 *    และ letter-spacing ทำให้สระ/วรรณยุกต์ลอยห่างจากพยัญชนะ
 *
 * 🚧 **ยังไม่มี FAB สร้างข้อเสนอในรอบนี้โดยเจตนา** — `AppFab` เรนเดอร์เป็น `RouterLink`
 *    และถูกวางที่ `MainLayout` ⇒ การเปิด modal จาก shell ต้องมีช่องทางส่ง action ข้าม
 *    คอมโพเนนต์ ซึ่งยังไม่มีในสถาปัตยกรรมนี้ · ทางที่ถูกคือทำ `QuickSuggestionModal`
 *    เป็น **หน้าเต็ม** (`/app/boards/new` ตามแบบ `event-create`) แล้วให้ FAB ชี้ไปที่นั่น
 *    (skills #16: ฟอร์มต้องเป็นหน้าเต็ม) ⇒ เป็นงานคอมมิตถัดไป ไม่ใช่ยัดมาปนกับอันนี้
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

/** ตัวกรองประเภท — **ไม่มีไอคอน** (ชิปมีที่จำกัด และป้ายไทยอ่านออกอยู่แล้ว) */
const TYPE_FILTERS: Array<{ value: '' | BoardType; label: string }> = [
  { value: '', label: 'ทั้งหมด' },
  { value: 'vote', label: 'โหวต' },
  { value: 'talk', label: 'พูดคุย' },
  { value: 'suggestion', label: 'ข้อเสนอแนะ' },
]

/** มีตัวกรอง/คำค้นค้างอยู่ไหม — ใช้เลือกข้อความของ empty state */
const isFiltered = ref(false)

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

function clearFilters() {
  q.value = ''
  typeFilter.value = ''
  page.value = 1
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
    isFiltered.value = Boolean(typeFilter.value || q.value.trim())
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'โหลดข้อมูลไม่สำเร็จ'
  } finally {
    isLoading.value = false
  }
}
</script>

<template>
  <div class="mx-auto max-w-5xl space-y-4 pb-4">
    <!-- คำอธิบายหน้าอยู่ที่ `AppHeader` แล้ว ⇒ เหลือบรรทัดเดียวที่บอกว่า "ที่นี่มีอะไร" -->
    <p class="text-sm text-ink-2">
      โหวต + พูดคุยสาธารณะที่สภานักเรียนอนุมัติแล้ว · ข้อเสนอแนะจากทุกคน
    </p>

    <!-- 💡 เสนอไอเดีย — งานหลักของหน้านี้ ⇒ อยู่บนสุดและเต็มความกว้างบนมือถือ
         ⚠️ `data-testid` คงไว้ — เป็น hook ที่อ้างอิงได้ และการย้ายปุ่มไม่ควรทำ hook หาย -->
    <AppButton
      data-testid="open-suggestion"
      block
      class="sm:w-auto"
      @click="showSuggestionModal = true"
    >
      <template #icon><i class="bi bi-lightbulb" aria-hidden="true" /></template>
      เสนอไอเดีย
    </AppButton>

    <!-- 🏷️ ชิปกรองประเภท — เลื่อนแนวนอน ไม่ตัดบรรทัด (`.chip-row` มีอยู่ใน main.css) -->
    <div class="chip-row">
      <AppChip
        v-for="t in TYPE_FILTERS"
        :key="t.value"
        :label="t.label"
        :active="typeFilter === t.value"
        @click="switchType(t.value)"
      />
    </div>

    <!-- ค้นหา + จำนวน -->
    <div class="flex items-center gap-3">
      <div class="relative min-w-0 flex-1 sm:max-w-xs">
        <i
          class="bi bi-search absolute top-1/2 left-3 -translate-y-1/2 text-sm text-ink-3"
          aria-hidden="true"
        />
        <input
          v-model="q"
          type="search"
          aria-label="ค้นหาบอร์ด"
          placeholder="ค้นหาบอร์ด..."
          class="w-full rounded-control border border-line bg-surface py-2.5 pr-3 pl-9 text-sm text-ink-1 focus-visible:ring-2 focus-visible:ring-brand focus-visible:outline-none"
        />
      </div>
      <span class="shrink-0 text-sm text-ink-3 tabular-nums">
        {{ total.toLocaleString('en-US') }} บอร์ด
      </span>
    </div>

    <!-- โหลด: skeleton การ์ด -->
    <div v-if="isLoading" class="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
      <AppCard v-for="n in 6" :key="n" class="animate-pulse">
        <div class="mb-3 flex items-center justify-between">
          <div class="h-5 w-16 rounded bg-canvas"></div>
          <div class="h-3 w-14 rounded bg-canvas"></div>
        </div>
        <div class="mb-2 h-5 w-3/4 rounded bg-canvas"></div>
        <div class="mb-1.5 h-4 w-full rounded bg-canvas"></div>
        <div class="h-4 w-5/6 rounded bg-canvas"></div>
      </AppCard>
    </div>

    <!-- ผิดพลาด — 「ไม่มีการ์ดเส้นประ」 (R0: empty state ห้ามใช้ border-dashed) -->
    <AppCard v-else-if="error" :padded="false" class="py-4">
      <AppEmptyState icon="bi-wifi-off" title="โหลดบอร์ดไม่สำเร็จ" :description="error">
        <AppButton variant="secondary" @click="load">
          <template #icon><i class="bi bi-arrow-clockwise" aria-hidden="true" /></template>
          ลองใหม่
        </AppButton>
      </AppEmptyState>
    </AppCard>

    <!-- ว่าง — แยกข้อความตาม "ยังไม่มีของ" กับ "กรองแล้วไม่เจอ" (คนละสาเหตุ คนละทางออก) -->
    <AppCard v-else-if="!boards.length" :padded="false" class="py-4">
      <AppEmptyState
        icon="bi-columns-gap"
        :title="isFiltered ? 'ไม่พบบอร์ดที่ตรงกับเงื่อนไข' : 'ยังไม่มีบอร์ดในระบบ'"
        :description="
          isFiltered
            ? 'ลองล้างคำค้นหรือเลือกประเภทอื่น'
            : 'เมื่อสภานักเรียนอนุมัติเรื่องที่ขอเปิดโหวต/พูดคุย บอร์ดจะมาแสดงที่นี่'
        "
      >
        <AppButton v-if="isFiltered" variant="secondary" @click="clearFilters">
          <template #icon><i class="bi bi-x-circle" aria-hidden="true" /></template>
          ล้างตัวกรอง
        </AppButton>
      </AppEmptyState>
    </AppCard>

    <div v-else class="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
      <!-- ⚠️ ทั้งการ์ดเป็นทางเข้าเดียว ⇒ `AppCard interactive` + `<RouterLink>` เป็น *ลูก*
           ไม่ใช่ปุ่มซ้อนปุ่ม (HTML ไม่รองรับ `<button>` ซ้อน `<button>`) -->
      <AppCard v-for="b in boards" :key="b.id" :padded="false" interactive>
        <RouterLink
          :to="{ name: 'board-detail', params: { id: b.id } }"
          class="flex h-full flex-col rounded-card p-4 focus-visible:ring-2 focus-visible:ring-brand focus-visible:outline-none sm:p-5"
        >
          <div class="mb-2 flex items-center justify-between gap-2">
            <span
              class="inline-flex items-center gap-1 rounded-md bg-canvas px-2 py-0.5 text-[11px] font-semibold text-ink-2"
            >
              <i :class="boardTypeIcon(b.board_type)" aria-hidden="true" />
              {{ BOARD_TYPE_LABELS[b.board_type] }}
            </span>
            <span class="shrink-0 text-xs text-ink-3">{{ fmtRelative(b.created_at) }}</span>
          </div>

          <h3 class="mb-1 line-clamp-2 leading-snug font-semibold text-ink-1">{{ b.title }}</h3>
          <p class="mb-3 line-clamp-2 text-sm text-ink-2">{{ b.description }}</p>

          <div class="mt-auto">
            <div v-if="b.tags.length" class="mb-3 flex flex-wrap gap-1.5">
              <span
                v-for="tag in b.tags.slice(0, 4)"
                :key="tag"
                class="rounded-full bg-canvas px-2 py-0.5 text-[11px] text-ink-2"
              >
                #{{ tag }}
              </span>
            </div>
            <div
              class="flex items-center justify-between gap-2 border-t border-line pt-2 text-xs text-ink-2"
            >
              <span class="truncate">
                <i class="bi bi-person mr-1" aria-hidden="true" />
                {{ b.is_anonymous ? 'ไม่ระบุชื่อ' : b.author_name || 'สภานักเรียน' }}
              </span>
              <span class="flex shrink-0 items-center gap-3">
                <span v-if="b.board_type === 'vote'">
                  <i class="bi bi-bar-chart mr-1" aria-hidden="true" />{{
                    b.total_votes.toLocaleString('en-US')
                  }}
                </span>
                <span v-else>
                  <i class="bi bi-chat-left-text mr-1" aria-hidden="true" />{{
                    b.comment_count.toLocaleString('en-US')
                  }}
                </span>
              </span>
            </div>
          </div>
        </RouterLink>
      </AppCard>
    </div>

    <PaginationBar
      :total="total"
      :page="page"
      :page-size="pageSize"
      :loading="isLoading"
      @page-change="onPageChange"
    />

    <QuickSuggestionModal v-model:open="showSuggestionModal" @created="onSuggestionCreated" />
  </div>
</template>
