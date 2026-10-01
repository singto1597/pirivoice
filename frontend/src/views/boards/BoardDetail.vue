<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import Swal from 'sweetalert2'
import { BRAND } from '@/constants/brand'
import { getBoard, submitVote, addComment, hideBoard } from '@/services/board'
import {
  boardTypeIcon,
  boardTypeHeading,
  boardAuthorFallback,
  type BoardDetail,
} from '@/types/board'
import type { ApiError } from '@/services/api'
import { goUnavailable } from '@/router/unavailable'
import { useAuthStore } from '@/stores/auth'
import { useNotificationsStore } from '@/stores/notifications'
import CommentThread from '@/components/boards/CommentThread.vue'
import BookmarkButton from '@/components/BookmarkButton.vue'

const authStore = useAuthStore()
const notificationsStore = useNotificationsStore()

/**
 * 📄 PIRI Board — รองรับ 2 เลย์เอาต์:
 * - Vote: ตัวเลือกแบบ progress bar + เลือกโหวต (1 เสียง/คน — เปลี่ยนไม่ได้)
 * - Talk: คอมเมนต์แบบ threaded (CommentThread recursive)
 */
const route = useRoute()
const router = useRouter()

const board = ref<BoardDetail | null>(null)
const isLoading = ref(true)
const loadError = ref('')

// ===== Vote =====
const selectedChoice = ref<number | null>(null)
const voting = ref(false)
const myVoted = computed(() => (board.value?.my_vote_choice_id ?? null) !== null)

function choicePercent(c: { vote_count: number }): number {
  const total = board.value?.total_votes ?? 0
  if (total <= 0) return 0
  return Math.round((c.vote_count / total) * 100)
}

async function handleVote() {
  if (!board.value || selectedChoice.value === null || myVoted.value) return
  voting.value = true
  try {
    await submitVote(board.value.id, selectedChoice.value)
    Swal.fire({ icon: 'success', title: 'ส่งเสียงโหวตแล้ว!', timer: 1200, showConfirmButton: false })
    await load()
  } catch (e) {
    Swal.fire({ icon: 'error', title: 'โหวตไม่สำเร็จ', text: e instanceof Error ? e.message : String(e) })
  } finally {
    voting.value = false
  }
}

// ===== Talk =====
const commentBody = ref('')
const postingComment = ref(false)

async function submitComment() {
  if (!board.value || !commentBody.value.trim()) return
  postingComment.value = true
  try {
    await addComment(board.value.id, commentBody.value.trim())
    commentBody.value = ''
    Swal.fire({ icon: 'success', title: 'คอมเมนต์แล้ว', timer: 1000, showConfirmButton: false })
    await load()
  } catch (e) {
    Swal.fire({ icon: 'error', title: 'คอมเมนต์ไม่สำเร็จ', text: e instanceof Error ? e.message : String(e) })
  } finally {
    postingComment.value = false
  }
}

async function load() {
  isLoading.value = true
  loadError.value = ''
  try {
    board.value = await getBoard(Number(route.params.id))
    // รีเซ็ตตัวเลือกที่เลือก (หลังโหวตแล้ว reload — ป้องกัน select ตัวเดิมหลงเหลือ)
    if (board.value?.my_vote_choice_id) selectedChoice.value = null
    // 🔔 เปิดบอร์ดแล้ว → mark notification ของบอร์ดนี้ว่าอ่านแล้ว (badge ลด)
    if (board.value) void notificationsStore.read({ board_id: board.value.id })
  } catch (e) {
    // 🚪 404 = บอร์ด "เปิดดูไม่ได้แล้ว" มีสองทางที่อยู่คนละคอลัมน์ — `deleted_at IS NOT NULL`
    //    (ถูกลบ) และ `status = 'hidden'` (สภาฯ กดซ่อน) · backend ตอบ 404 เหมือนกันทั้งคู่
    //    ⇒ ลิงก์ที่ผู้ใช้กดมา (จาก notification หรือ deep link ของ push) ใช้ต่อไม่ได้
    //    ⇒ พากลับไปที่ที่ไปต่อได้ + บอกสาเหตุ ดีกว่าค้างไว้กับ error ที่กดลองใหม่ก็ได้ 404
    //    (เหตุผลเต็มอยู่ใน `router/unavailable.ts` — **ห้ามแยกสองกรณีนี้ออกจากกัน**)
    if (e instanceof Error && (e as ApiError).status === 404) {
      await goUnavailable(router, 'board')
      return
    }
    loadError.value = e instanceof Error ? e.message : 'โหลดบอร์ดไม่สำเร็จ'
  } finally {
    isLoading.value = false
  }
}

// 🛡️ สภา/แอดมิน ซ่อน board ทั้งบอร์ด (หลุดจากฟีด + detail 404) — ต้องระบุเหตุผล
const hidingBoard = ref(false)
async function handleHideBoard() {
  if (!board.value || hidingBoard.value) return
  const { value } = await Swal.fire({
    title: 'ซ่อนบอร์ดนี้?',
    text: 'บอร์ดจะหายจากฟีดและรายละเอียดทันที (ผู้ใช้ทั่วไปมองไม่เห็น)',
    icon: 'warning',
    input: 'text',
    inputPlaceholder: 'เหตุผลที่ซ่อน (จำเป็น)',
    inputAttributes: { maxlength: '200' },
    showCancelButton: true,
    confirmButtonText: 'ซ่อนบอร์ด',
    confirmButtonColor: BRAND,
    cancelButtonText: 'ยกเลิก',
  })
  if (!value || !String(value).trim()) {
    if (value !== undefined) Swal.fire({ icon: 'warning', title: 'ต้องระบุเหตุผล', text: 'กรุณากรอกเหตุผลที่ซ่อน' })
    return
  }
  hidingBoard.value = true
  try {
    await hideBoard(board.value.id, String(value).trim())
    Swal.fire({ icon: 'success', title: 'ซ่อนบอร์ดแล้ว', text: 'ย้ายกลับไปยังฟีด PIRI Boards', timer: 1500, showConfirmButton: false }).then(() => {
      router.push({ name: 'boards' })
    })
  } catch (e) {
    Swal.fire({ icon: 'error', title: 'ซ่อนไม่สำเร็จ', text: e instanceof Error ? e.message : String(e) })
  } finally {
    hidingBoard.value = false
  }
}

onMounted(load)

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString('th-TH', {
    timeZone: 'Asia/Bangkok',
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  })
}

// คอมเมนต์ root (parent_comment_id = null) — backend ส่ง tree ที่ roots อยู่ระดับบน
const rootComments = computed(() => board.value?.comments ?? [])
</script>

<template>
  <!-- โหลด: skeleton เนื้อหา -->
  <div v-if="isLoading" class="max-w-3xl mx-auto space-y-5">
    <div class="page-card p-5 space-y-3">
      <div class="flex items-center justify-between">
        <div class="h-5 w-24 bg-stone-100 animate-pulse rounded-md"></div>
        <div class="h-3 w-20 bg-stone-100 animate-pulse rounded"></div>
      </div>
      <div class="h-6 w-3/4 bg-stone-100 animate-pulse rounded"></div>
      <div class="h-4 w-1/2 bg-stone-100 animate-pulse rounded"></div>
      <div class="h-20 w-full bg-stone-100 animate-pulse rounded"></div>
    </div>
    <div class="page-card p-5 space-y-3">
      <div class="h-5 w-24 bg-stone-100 animate-pulse rounded"></div>
      <div class="h-14 w-full bg-stone-100 animate-pulse rounded-xl"></div>
      <div class="h-14 w-full bg-stone-100 animate-pulse rounded-xl"></div>
      <div class="h-14 w-full bg-stone-100 animate-pulse rounded-xl"></div>
      <div class="h-11 w-full bg-stone-100 animate-pulse rounded-xl"></div>
    </div>
  </div>

  <!-- ข้อผิดพลาด -->
  <div v-else-if="loadError" class="max-w-3xl mx-auto border-2 border-dashed border-stone-200 rounded-2xl py-20 px-6 text-center">
    <div class="text-4xl text-stone-300 mb-3"><i class="bi bi-file-earmark-x"></i></div>
    <p class="text-stone-600 font-medium">{{ loadError }}</p>
    <div class="mt-5 flex flex-wrap items-center justify-center gap-3">
      <button @click="load" class="inline-flex items-center px-5 min-h-11 py-2.5 bg-brand text-white rounded-xl text-sm font-bold hover:bg-brand-strong">
        <i class="bi bi-arrow-clockwise mr-1"></i> ลองอีกครั้ง
      </button>
      <button @click="router.push({ name: 'boards' })" class="inline-flex items-center px-5 min-h-11 py-2.5 bg-stone-100 text-stone-700 rounded-xl text-sm font-medium hover:bg-stone-200">
        กลับไป PIRI Boards
      </button>
    </div>
  </div>

  <div v-else-if="board" class="max-w-3xl mx-auto space-y-5">
    <!-- 🔴 ไม่มีปุ่มย้อนที่นี่ — `AppHeader` วาดปุ่ม ← (จาก `meta.headerBack` = `boards`) ให้แล้ว (R0.3) -->

    <!-- Header -->
    <div class="page-card p-5">
      <div class="flex items-center justify-between gap-3 mb-2">
        <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-stone-100 text-stone-600 text-[11px] font-semibold">
          <i :class="boardTypeIcon(board.board_type)"></i> {{ boardTypeHeading(board.board_type) }}
        </span>
        <div class="flex items-center gap-2">
          <span class="text-xs text-ink-3">{{ fmtDate(board.created_at) }}</span>
          <!-- 🔖 บันทึกไว้อ่านทีหลัง (C2) -->
          <BookmarkButton entity-type="board" :entity-id="board.id" size="sm" />
          <button
            v-if="authStore.isCouncilAuthority"
            type="button"
            @click="handleHideBoard"
            :disabled="hidingBoard"
            data-testid="hide-board-btn"
            class="inline-flex items-center px-2.5 min-h-11 py-1 text-[11px] font-medium rounded-lg border border-brand/25 text-brand hover:bg-brand/5 disabled:opacity-40"
            title="ซ่อนบอร์ดนี้ (สภา/แอดมิน)"
          >
            <i class="bi bi-eye-slash mr-1"></i> ซ่อนบอร์ด
          </button>
        </div>
      </div>
      <!-- ⚠️ `<h2>` ไม่ใช่ `<h1>` — `<h1>` ของหน้าอยู่ที่ `AppHeader` แล้ว (R0.3.1) -->
      <h2 class="text-lg sm:text-xl font-bold text-stone-900 leading-snug break-words">{{ board.title }}</h2>
      <p class="text-stone-500 text-sm mt-1">
        โดย {{ board.is_anonymous ? 'ไม่ระบุชื่อ' : board.author_name || boardAuthorFallback(board.board_type) }}
      </p>
      <p class="text-stone-700 mt-3 whitespace-pre-wrap break-words">{{ board.description }}</p>
      <div v-if="board.tags.length" class="flex flex-wrap gap-1.5 mt-3">
        <span v-for="tag in board.tags" :key="tag" class="px-2 py-0.5 bg-stone-100 text-stone-600 text-[11px] rounded-full">#{{ tag }}</span>
      </div>
    </div>

    <!-- ===================== Vote layout ===================== -->
    <div v-if="board.board_type === 'vote'" class="page-card p-5">
      <div class="flex items-center justify-between mb-1">
        <h2 class="text-lg font-bold text-stone-900"><i class="bi bi-bar-chart-fill mr-1 text-stone-500"></i> โหวต</h2>
        <span class="text-sm text-stone-500 font-display tabular-nums">{{ board.total_votes.toLocaleString('en-US') }} เสียง</span>
      </div>

      <!-- แบนเนอร์: โหวตแล้ว → เปลี่ยนตัวเลือกไม่ได้ -->
      <div v-if="myVoted" data-testid="my-vote-banner" class="mb-4 px-3 py-2 bg-emerald-50 border border-emerald-200 text-emerald-700 text-sm rounded-xl">
        <i class="bi bi-check-circle-fill mr-1"></i> คุณส่งเสียงโหวตแล้ว — แต่ละคนโหวตได้ 1 ครั้ง
      </div>

      <div class="space-y-3">
        <button
          v-for="c in board.choices"
          :key="c.id"
          type="button"
          :data-testid="'vote-choice-' + c.id"
          :disabled="myVoted"
          @click="selectedChoice = c.id"
          class="w-full text-left p-4 rounded-xl border-2 transition"
          :class="[
            !myVoted && selectedChoice === c.id
              ? 'border-brand bg-brand/5'
              : 'border-stone-200 hover:border-stone-300',
            board.my_vote_choice_id === c.id ? 'ring-2 ring-emerald-400 border-emerald-400' : '',
            myVoted ? 'cursor-default' : 'cursor-pointer',
          ]"
        >
          <div class="flex items-center justify-between gap-3 mb-2">
            <span class="font-semibold text-stone-900 text-sm sm:text-base flex items-center gap-2">
              <span v-if="board.my_vote_choice_id === c.id" class="text-emerald-600"><i class="bi bi-check-circle-fill"></i></span>
              {{ c.choice_text }}
            </span>
            <span class="text-sm text-stone-500 font-display tabular-nums whitespace-nowrap">
              {{ c.vote_count.toLocaleString('en-US') }} เสียง · {{ choicePercent(c) }}%
            </span>
          </div>
          <!-- progress bar -->
          <div class="h-2.5 bg-stone-100 rounded-full overflow-hidden">
            <div
              class="h-full rounded-full transition-all duration-500"
              :class="board.my_vote_choice_id === c.id ? 'bg-emerald-500' : 'bg-brand'"
              :style="{ width: choicePercent(c) + '%' }"
            ></div>
          </div>
        </button>
      </div>

      <p v-if="!board.choices.length" class="text-sm text-ink-3 py-2">ยังไม่มีตัวเลือกโหวต</p>

      <button
        v-if="!myVoted"
        type="button"
        :disabled="selectedChoice === null || voting"
        data-testid="vote-submit"
        @click="handleVote"
        class="mt-4 w-full py-3 bg-brand text-white rounded-xl hover:bg-brand-strong disabled:opacity-50 font-medium"
      >
        {{ voting ? 'กำลังส่งเสียง...' : selectedChoice === null ? 'เลือกตัวเลือกก่อนโหวต' : 'ส่งเสียงโหวต' }}
      </button>
    </div>

    <!-- ===================== Talk layout ===================== -->
    <div v-else class="page-card p-5">
      <h2 class="text-lg font-bold text-stone-900 mb-4">
        <i class="bi bi-chat-left-text mr-1 text-stone-500"></i> พูดคุย
        <span v-if="rootComments.length" class="text-sm font-normal text-ink-3">({{ board.comment_count }})</span>
      </h2>

      <!-- ปิดคอมเมนต์ -->
      <div v-if="!board.allow_comments" class="mb-4 px-3 py-2 bg-stone-100 text-stone-600 text-sm rounded-xl">
        <i class="bi bi-lock mr-1"></i> บอร์ดนี้ปิดคอมเมนต์ (อ่านอย่างเดียว)
      </div>

      <!-- ช่องคอมเมนต์ root -->
      <div v-if="board.allow_comments" class="flex gap-2 mb-5">
        <input
          v-model="commentBody"
          type="text"
          data-testid="comment-input"
          placeholder="ร่วมแสดงความเห็น..."
          maxlength="1000"
          class="flex-1 px-3 py-2.5 border border-stone-300 rounded-xl text-sm focus:ring-2 focus:ring-brand"
          @keyup.enter="submitComment"
        />
        <button
          type="button"
          :disabled="postingComment || !commentBody.trim()"
          data-testid="comment-submit"
          @click="submitComment"
          class="inline-flex items-center px-4 min-h-11 py-2.5 bg-brand text-white rounded-xl text-sm hover:bg-brand-strong disabled:opacity-50"
        >
          {{ postingComment ? '...' : 'ส่ง' }}
        </button>
      </div>

      <!-- กระทู้คอมเมนต์ (threaded) -->
      <div v-if="rootComments.length" class="space-y-4">
        <CommentThread v-for="c in rootComments" :key="c.id" :board-id="board.id" :comment="c" @refresh="load" />
      </div>
      <p v-else-if="board.allow_comments" class="text-sm text-ink-3 py-2">ยังไม่มีความเห็น — เป็นคนแรกที่ร่วมพูดคุย</p>
    </div>
  </div>
</template>
