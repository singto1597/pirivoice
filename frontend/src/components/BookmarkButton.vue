<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import Swal from 'sweetalert2'
import { createBookmark, deleteBookmark, getBookmarkStatus } from '@/services/bookmark'
import type { BookmarkEntityType } from '@/types/bookmark'

/**
 * 🔖 ปุ่ม "บันทึกไว้อ่านทีหลัง" — ใช้ร่วมกันใน `IssueDetail.vue` และ `BoardDetail.vue`
 *
 * ออกแบบให้ **พังไม่ได้**:
 *  - **optimistic** — เปลี่ยนไอคอนทันที แล้วย้อนกลับถ้า API ล้ม (ผู้ใช้ไม่ต้องรอเน็ต)
 *  - `busy` กันกดรัว — ไม่ให้ POST/DELETE สลับกันมั่วจนสถานะจริงกับไอคอนไม่ตรง
 *  - **ไม่รู้สถานะ = ยังกดได้** และกดแล้วไปทาง "บันทึก" เสมอ เพราะ POST เป็น idempotent
 *    ⇒ ได้ bookmark_id กลับมาจริง (ทาง "ลบ" ต้องมี id จึงจะทำได้ — จึงเลือกทางที่กู้คืนได้)
 *  - ⚠️ ไม่ส่ง `user_id` ไปกับ request — backend เอาจาก JWT เท่านั้น
 */
const props = withDefaults(
  defineProps<{
    entityType: BookmarkEntityType
    entityId: number
    /** `sm` = หัวบอร์ด (ข้างปุ่มซ่อนบอร์ด) · `md` = หัวหน้าเรื่อง */
    size?: 'md' | 'sm'
  }>(),
  { size: 'md' },
)

const emit = defineEmits<{ change: [bookmarked: boolean] }>()

const bookmarked = ref(false)
const bookmarkId = ref<number | null>(null)
const busy = ref(false)

const label = computed(() => (bookmarked.value ? 'เลิกบันทึกไว้' : 'บันทึกไว้อ่านทีหลัง'))

onMounted(load)

async function load() {
  try {
    const s = await getBookmarkStatus(props.entityType, props.entityId)
    bookmarked.value = s.bookmarked
    bookmarkId.value = s.bookmark_id
  } catch {
    // โหลดสถานะไม่ได้ → ปล่อยเป็น "ยังไม่บันทึก" ซึ่งกดแล้วกู้คืนได้ (POST idempotent)
  }
}

async function toggle() {
  if (busy.value) return
  busy.value = true

  const prev = bookmarked.value
  const next = !prev
  bookmarked.value = next // optimistic

  try {
    if (next) {
      const b = await createBookmark(props.entityType, props.entityId)
      bookmarkId.value = b.id
    } else {
      if (bookmarkId.value === null) {
        // ไม่มี id = ลบไม่ได้ (ไม่ควรเกิด) — **อย่าโกหกผู้ใช้ว่าลบแล้ว** ให้ดึงสถานะจริงกลับมา
        bookmarked.value = true
        await load()
        return
      }
      await deleteBookmark(bookmarkId.value)
      bookmarkId.value = null
    }
    emit('change', next)
  } catch (e: unknown) {
    bookmarked.value = prev // ยิงไม่ผ่าน → คืนค่าที่ถูกต้องให้ผู้ใช้เห็น
    Swal.fire({
      icon: 'error',
      title: next ? 'บันทึกไม่สำเร็จ' : 'เลิกบันทึกไม่สำเร็จ',
      text: e instanceof Error ? e.message : 'เกิดข้อผิดพลาด กรุณาลองใหม่',
    })
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <button
    type="button"
    :disabled="busy"
    :aria-pressed="bookmarked"
    :aria-label="label"
    :title="label"
    class="inline-flex shrink-0 items-center justify-center rounded-xl border transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
    :class="[
      size === 'sm' ? 'h-7 w-7 text-[13px]' : 'h-9 w-9 text-base',
      bookmarked
        ? 'border-brand/30 bg-brand/5 text-brand'
        : 'border-stone-200 bg-white text-stone-500 hover:bg-stone-50 hover:text-brand',
    ]"
    @click="toggle"
  >
    <i class="bi" :class="bookmarked ? 'bi-bookmark-fill' : 'bi-bookmark'"></i>
  </button>
</template>
