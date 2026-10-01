<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { getMyActivity } from '@/services/me'
import { listBookmarks } from '@/services/bookmark'
import {
  ACTIVITY_ICONS,
  ACTIVITY_TABS,
  ACTIVITY_VERBS,
  type ActivityItem,
  type ActivityType,
} from '@/types/me'
import {
  DELETED_SOURCE_LABEL,
  ENTITY_ICONS,
  ENTITY_LABELS,
  ENTITY_TYPES,
  bookmarkPath,
  type Bookmark,
  type BookmarkEntityType,
} from '@/types/bookmark'
import { STATUS_BADGE, statusShort } from '@/constants/status'
import PaginationBar from '@/components/PaginationBar.vue'

/**
 * 🧭 กิจกรรมของฉัน (C1) + บันทึกไว้ (C2) — หน้าเดียวกัน 2 แท็บ
 *
 * ⚠️ **สองแท็บยิงคนละ endpoint และเก็บ state แยกกัน** ⇒ สลับแท็บไม่ทำให้ของอีกแท็บหาย
 *    และไม่มีการโหลดซ้ำโดยไม่จำเป็น (แท็บบันทึกโหลดครั้งแรกตอนกดเข้าไปเท่านั้น)
 * ⚠️ **ไม่กรองตามภาค** (ต่างจากสถิติใน Profile โดยเจตนา) — ที่นี่คือ "ทุกอย่างที่เคยทำ"
 *    แต่ยอดต่อประเภทต้องตรงกับตัวนับของ C3 เสมอ (ดูคอมเมนต์ใน `types/me.ts`)
 */
const PAGE_SIZE = 20

const tab = ref<'activity' | 'bookmarks'>('activity')

// ── แท็บกิจกรรมของฉัน ──
const actItems = ref<ActivityItem[]>([])
const actCounts = ref<Partial<Record<ActivityType, number>>>({})
const actTotal = ref(0)
const actPage = ref(1)
const actType = ref<ActivityType | ''>('')
const actLoading = ref(true)
const actError = ref('')

// ── แท็บบันทึกไว้ ──
const bmItems = ref<Bookmark[]>([])
const bmTotal = ref(0)
const bmPage = ref(1)
const bmEntityType = ref<BookmarkEntityType | ''>('')
const bmLoading = ref(false)
const bmError = ref('')
const bmLoaded = ref(false) // โหลดครั้งแรกตอนเข้าแท็บ (ไม่ยิงตอนmount)

onMounted(loadActivity)

async function loadActivity() {
  actLoading.value = true
  actError.value = ''
  try {
    const res = await getMyActivity({
      activity_type: actType.value || undefined,
      limit: PAGE_SIZE,
      offset: (actPage.value - 1) * PAGE_SIZE,
    })
    actItems.value = res.items
    actTotal.value = res.total
    actCounts.value = res.counts ?? {}
  } catch (e) {
    actError.value = e instanceof Error ? e.message : 'โหลดข้อมูลไม่สำเร็จ'
  } finally {
    actLoading.value = false
  }
}

async function loadBookmarks() {
  bmLoading.value = true
  bmError.value = ''
  try {
    const res = await listBookmarks({
      entity_type: bmEntityType.value || undefined,
      limit: PAGE_SIZE,
      offset: (bmPage.value - 1) * PAGE_SIZE,
    })
    bmItems.value = res.items
    bmTotal.value = res.total
    bmLoaded.value = true
  } catch (e) {
    bmError.value = e instanceof Error ? e.message : 'โหลดข้อมูลไม่สำเร็จ'
  } finally {
    bmLoading.value = false
  }
}

function switchTab(next: 'activity' | 'bookmarks') {
  tab.value = next
  // โหลดครั้งแรกของแท็บบันทึก — หลังจากนั้นไม่ยิงซ้ำจนกว่าจะเปลี่ยนหน้า/ตัวกรอง
  if (next === 'bookmarks' && !bmLoaded.value && !bmLoading.value) loadBookmarks()
}

// เปลี่ยนตัวกรอง → กลับหน้า 1 เสมอ (ไม่งั้นอาจขอหน้าที่ไม่มีอยู่แล้วได้หน้าว่าง)
function pickActivityType(t: ActivityType | '') {
  actType.value = t
  actPage.value = 1
  loadActivity()
}

function pickEntityType(t: BookmarkEntityType | '') {
  bmEntityType.value = t
  bmPage.value = 1
  loadBookmarks()
}

function onActPage(n: number) {
  actPage.value = n
  loadActivity()
}

function onBmPage(n: number) {
  bmPage.value = n
  loadBookmarks()
}

function fmtTime(iso: string): string {
  return new Date(iso).toLocaleString('th-TH', {
    timeZone: 'Asia/Bangkok',
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  })
}

/** ป้ายกำกับของ `meta` — **ความหมายขึ้นกับประเภทกิจกรรม** (ดูคอมเมนต์ใน types/me.ts) */
function metaText(a: ActivityItem): string | null {
  if (a.meta === null) return null
  return a.activity_type === 'issue_created' ? statusShort(a.meta) : `เลือก “${a.meta}”`
}

function metaClass(a: ActivityItem): string {
  return a.activity_type === 'issue_created'
    ? (STATUS_BADGE[a.meta ?? ''] ?? 'bg-stone-100 text-stone-500')
    : 'bg-stone-100 text-stone-600'
}
</script>

<template>
  <div>
    <!-- 🔴 ไม่มี <h1>/eyebrow ที่นี่ — `AppHeader` แสดงชื่อหน้าจาก `routeTitles` เป็น <h1> ให้แล้ว (R0.3) -->

    <!-- แท็บหลัก -->
    <div class="mb-5 flex flex-wrap gap-2">
      <button
        type="button"
        :aria-pressed="tab === 'activity'"
        class="inline-flex items-center rounded-xl border px-4 min-h-11 py-2 text-sm font-bold transition-all"
        :class="tab === 'activity'
          ? 'border-brand bg-brand text-white'
          : 'border-stone-200 bg-white text-stone-600 hover:bg-stone-50'"
        @click="switchTab('activity')"
      >
        <i class="bi bi-clock-history mr-1.5"></i> กิจกรรมของฉัน
      </button>
      <button
        type="button"
        :aria-pressed="tab === 'bookmarks'"
        class="inline-flex items-center rounded-xl border px-4 min-h-11 py-2 text-sm font-bold transition-all"
        :class="tab === 'bookmarks'
          ? 'border-brand bg-brand text-white'
          : 'border-stone-200 bg-white text-stone-600 hover:bg-stone-50'"
        @click="switchTab('bookmarks')"
      >
        <i class="bi bi-bookmark mr-1.5"></i> บันทึกไว้
      </button>
    </div>

    <!-- ══════════ แท็บ 1: กิจกรรมของฉัน ══════════ -->
    <template v-if="tab === 'activity'">
      <!-- ตัวกรองตามประเภท (ป้ายตัวเลขมาจาก counts ของทั้งชุด ไม่ใช่ของหน้าปัจจุบัน) -->
      <div class="mb-4 flex flex-wrap gap-2">
        <button
          v-for="t in ACTIVITY_TABS"
          :key="t.value || 'all'"
          type="button"
          :aria-pressed="actType === t.value"
          class="inline-flex items-center rounded-xl border px-3 min-h-11 py-1.5 text-[13px] font-semibold transition-all"
          :class="actType === t.value
            ? 'border-brand bg-brand text-white'
            : 'border-stone-200 bg-white text-stone-600 hover:bg-stone-50'"
          @click="pickActivityType(t.value)"
        >
          <i :class="[t.icon, 'mr-1']"></i> {{ t.label }}
          <span
            v-if="t.value && (actCounts[t.value] ?? 0) > 0"
            class="ml-1.5 rounded-full px-1.5 py-0.5 text-[11px] font-bold"
            :class="actType === t.value ? 'bg-white/25' : 'bg-brand/10 text-brand'"
          >
            {{ actCounts[t.value] ?? 0 }}
          </span>
        </button>
      </div>

      <!-- loading skeleton -->
      <div v-if="actLoading" class="animate-pulse rounded-2xl border border-stone-200 bg-white p-5">
        <div class="divide-y divide-stone-100">
          <div v-for="n in 5" :key="n" class="flex items-start gap-3 py-4">
            <div class="h-9 w-9 rounded-xl bg-stone-100"></div>
            <div class="flex-1 space-y-2 pt-1">
              <div class="h-3 w-1/3 rounded bg-stone-100"></div>
              <div class="h-3 w-2/3 rounded bg-stone-100"></div>
            </div>
            <div class="h-3 w-20 rounded bg-stone-100"></div>
          </div>
        </div>
      </div>

      <!-- โหลดไม่สำเร็จ -->
      <div
        v-else-if="actError"
        class="flex flex-col items-center justify-center rounded-2xl border-2 border-dashed border-stone-200 py-20 text-center"
      >
        <i class="bi bi-wifi-off mb-3 text-3xl text-ink-3"></i>
        <p class="text-stone-600">{{ actError }}</p>
        <button
          type="button"
          class="inline-flex items-center mt-4 rounded-lg bg-brand px-5 min-h-11 py-2 text-[13px] font-bold text-white hover:bg-brand-strong"
          @click="loadActivity"
        >
          ลองอีกครั้ง
        </button>
      </div>

      <!-- ว่าง -->
      <div
        v-else-if="!actItems.length"
        class="flex flex-col items-center justify-center rounded-2xl border-2 border-dashed border-stone-200 bg-white px-6 py-16 text-center"
      >
        <div class="mb-2 text-4xl text-stone-300"><i class="bi bi-clock-history"></i></div>
        <p class="text-stone-600">
          {{ actType ? 'ไม่มีกิจกรรมประเภทนี้' : 'ยังไม่มีกิจกรรม' }}
        </p>
        <RouterLink
          v-if="!actType"
          to="/app/issues/new"
          class="mt-3 inline-block font-medium text-brand hover:underline"
        >
          เริ่มจากการแจ้งเรื่องแรก <i class="bi bi-arrow-right"></i>
        </RouterLink>
      </div>

      <!-- ledger -->
      <TransitionGroup
        v-else
        name="list"
        tag="div"
        class="overflow-hidden rounded-2xl border border-stone-200 bg-white divide-y divide-stone-200"
      >
        <component
          v-for="a in actItems"
          :key="`${a.activity_type}-${a.src_id}`"
          :is="a.is_deleted_source ? 'div' : RouterLink"
          :to="a.is_deleted_source ? undefined : bookmarkPath(a.entity_type, a.entity_id)"
          class="flex items-start gap-3 px-5 py-4 transition"
          :class="a.is_deleted_source ? 'opacity-70' : 'block hover:bg-stone-50'"
        >
          <div class="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-stone-100 text-stone-500">
            <i class="bi" :class="ACTIVITY_ICONS[a.activity_type]"></i>
          </div>
          <div class="min-w-0 flex-1">
            <div class="mb-1 flex flex-wrap items-center gap-2">
              <span class="text-[11px] font-bold text-ink-3">
                {{ ACTIVITY_VERBS[a.activity_type] }}
              </span>
              <span
                v-if="a.meta !== null"
                class="rounded-full px-2 py-0.5 text-[11px] font-medium"
                :class="metaClass(a)"
              >
                {{ metaText(a) }}
              </span>
              <span
                v-if="a.is_deleted_source"
                class="rounded-full bg-stone-200 px-2 py-0.5 text-[11px] font-medium text-stone-500"
              >
                {{ DELETED_SOURCE_LABEL }}
              </span>
            </div>
            <h3 class="truncate font-semibold text-stone-900">{{ a.title }}</h3>
            <p v-if="a.excerpt" class="mt-1 line-clamp-2 text-xs leading-relaxed text-stone-500">
              {{ a.excerpt }}
            </p>
          </div>
          <span class="shrink-0 text-xs tabular-nums text-ink-3">{{ fmtTime(a.created_at) }}</span>
        </component>
      </TransitionGroup>

      <PaginationBar
        :total="actTotal"
        :page="actPage"
        :page-size="PAGE_SIZE"
        :loading="actLoading"
        @page-change="onActPage"
      />
    </template>

    <!-- ══════════ แท็บ 2: บันทึกไว้ ══════════ -->
    <template v-else>
      <div class="mb-4 flex flex-wrap gap-2">
        <button
          type="button"
          :aria-pressed="bmEntityType === ''"
          class="inline-flex items-center rounded-xl border px-3 min-h-11 py-1.5 text-[13px] font-semibold transition-all"
          :class="bmEntityType === ''
            ? 'border-brand bg-brand text-white'
            : 'border-stone-200 bg-white text-stone-600 hover:bg-stone-50'"
          @click="pickEntityType('')"
        >
          <i class="bi bi-collection mr-1"></i> ทั้งหมด
        </button>
        <button
          v-for="key in ENTITY_TYPES"
          :key="key"
          type="button"
          :aria-pressed="bmEntityType === key"
          class="inline-flex items-center rounded-xl border px-3 min-h-11 py-1.5 text-[13px] font-semibold transition-all"
          :class="bmEntityType === key
            ? 'border-brand bg-brand text-white'
            : 'border-stone-200 bg-white text-stone-600 hover:bg-stone-50'"
          @click="pickEntityType(key)"
        >
          <i :class="[ENTITY_ICONS[key], 'mr-1']"></i> {{ ENTITY_LABELS[key] }}
        </button>
      </div>

      <div v-if="bmLoading" class="animate-pulse rounded-2xl border border-stone-200 bg-white p-5">
        <div class="divide-y divide-stone-100">
          <div v-for="n in 5" :key="n" class="flex items-start gap-3 py-4">
            <div class="h-9 w-9 rounded-xl bg-stone-100"></div>
            <div class="flex-1 space-y-2 pt-1">
              <div class="h-3 w-1/4 rounded bg-stone-100"></div>
              <div class="h-3 w-2/3 rounded bg-stone-100"></div>
            </div>
            <div class="h-3 w-20 rounded bg-stone-100"></div>
          </div>
        </div>
      </div>

      <div
        v-else-if="bmError"
        class="flex flex-col items-center justify-center rounded-2xl border-2 border-dashed border-stone-200 py-20 text-center"
      >
        <i class="bi bi-wifi-off mb-3 text-3xl text-ink-3"></i>
        <p class="text-stone-600">{{ bmError }}</p>
        <button
          type="button"
          class="inline-flex items-center mt-4 rounded-lg bg-brand px-5 min-h-11 py-2 text-[13px] font-bold text-white hover:bg-brand-strong"
          @click="loadBookmarks"
        >
          ลองอีกครั้ง
        </button>
      </div>

      <div
        v-else-if="!bmItems.length"
        class="flex flex-col items-center justify-center rounded-2xl border-2 border-dashed border-stone-200 bg-white px-6 py-16 text-center"
      >
        <div class="mb-2 text-4xl text-stone-300"><i class="bi bi-bookmark"></i></div>
        <p class="text-stone-600">ยังไม่มีเรื่องที่บันทึกไว้</p>
        <p class="mt-2 text-xs text-stone-500">
          กดไอคอน <i class="bi bi-bookmark"></i> ที่หัวเรื่องหรือหัวบอร์ด เพื่อเก็บไว้ดูทีหลัง
        </p>
      </div>

      <TransitionGroup
        v-else
        name="list"
        tag="div"
        class="overflow-hidden rounded-2xl border border-stone-200 bg-white divide-y divide-stone-200"
      >
        <component
          v-for="b in bmItems"
          :key="b.id"
          :is="b.is_deleted_source ? 'div' : RouterLink"
          :to="b.is_deleted_source ? undefined : bookmarkPath(b.entity_type, b.entity_id)"
          class="flex items-start gap-3 px-5 py-4 transition"
          :class="b.is_deleted_source ? 'opacity-70' : 'block hover:bg-stone-50'"
        >
          <div class="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-stone-100 text-stone-500">
            <i class="bi" :class="ENTITY_ICONS[b.entity_type]"></i>
          </div>
          <div class="min-w-0 flex-1">
            <div class="mb-1 flex flex-wrap items-center gap-2">
              <span
                class="rounded-full bg-stone-100 px-2 py-0.5 text-[11px] font-medium text-stone-600"
              >
                {{ ENTITY_LABELS[b.entity_type] }}
              </span>
              <span
                v-if="b.is_deleted_source"
                class="rounded-full bg-stone-200 px-2 py-0.5 text-[11px] font-medium text-stone-500"
              >
                {{ DELETED_SOURCE_LABEL }}
              </span>
            </div>
            <h3 class="truncate font-semibold text-stone-900">{{ b.title }}</h3>
            <p v-if="b.excerpt" class="mt-1 line-clamp-2 text-xs leading-relaxed text-stone-500">
              {{ b.excerpt }}
            </p>
          </div>
          <span class="shrink-0 text-xs tabular-nums text-ink-3">{{ fmtTime(b.created_at) }}</span>
        </component>
      </TransitionGroup>

      <PaginationBar
        :total="bmTotal"
        :page="bmPage"
        :page-size="PAGE_SIZE"
        :loading="bmLoading"
        @page-change="onBmPage"
      />
    </template>
  </div>
</template>

<style scoped>
/* list animation */
.list-enter-active,
.list-leave-active {
  transition: all 0.25s ease;
}
.list-enter-from {
  opacity: 0;
  transform: translateY(10px);
}
.list-leave-to {
  opacity: 0;
  transform: translateY(-6px);
}
</style>
