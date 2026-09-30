<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useNavItems } from '@/composables/useNavItems'
import type { SegmentGroupId } from '@/router/meta'
import type { NotificationGroup } from '@/types/notification'

/**
 * 🔀 แถบ segment ใต้หัวแถบ — ใช้กับหน้าที่ "รวมสองมุมมองไว้หน้าเดียว"
 * (เรื่อง: ของฉัน / ที่รับผิดชอบ · สมาชิก: นักเรียน / เจ้าหน้าที่)
 *
 * 🔴 **ซ่อนตัวเองเมื่อเหลือตัวเลือกเดียว** — ผู้ใช้ที่ไม่มีสิทธิ์รับเรื่องจะไม่เห็น
 *    แถบที่มีปุ่มเดียวตาย ๆ (ปุ่มเดียวที่กดอยู่แล้ว = ที่ว่างที่เสียไปเปล่า)
 *    นี่คือผลพลอยได้ที่ทำให้ **ไม่ต้องไป gate ที่ route** (ดู `R0.3.3` ในแผน)
 *
 * 🔴 **สลับ segment ต้องล้าง query** — หน้า `ReceivedIssues` เก็บตัวกรองหมวดไว้ใน
 *    `route.query` ⇒ ถ้าไม่ล้าง ตัวกรองของหน้าหนึ่งจะติดไปอีกหน้าหนึ่งแบบเงียบ ๆ
 *    (`?main_category=…` ค้างอยู่ใน URL แล้วหน้าที่ไม่รู้จักคีย์นั้นก็เมินไป)
 */
const props = defineProps<{ group: SegmentGroupId }>()

const route = useRoute()
const router = useRouter()
const nav = useNavItems()

const options = computed(() => nav.segmentsOf(props.group))

function badgeOf(group: NotificationGroup | undefined): number {
  return group ? nav.badgeForGroup(group) : 0
}

function select(to: { name: string }): void {
  if (route.name === to.name) return
  router.push({ name: to.name, query: {} })
}
</script>

<template>
  <div v-if="options.length > 1" class="shrink-0 border-b border-line bg-surface px-4 py-2">
    <div class="flex gap-1 rounded-control bg-canvas p-0.5">
      <button
        v-for="option in options"
        :key="option.key"
        type="button"
        :aria-current="route.name === option.to.name ? 'page' : undefined"
        class="flex h-9 flex-1 items-center justify-center gap-1.5 rounded-[10px] text-[13px] font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
        :class="
          route.name === option.to.name
            ? 'bg-surface text-brand ring-1 ring-line'
            : 'text-ink-2 hover:text-ink-1'
        "
        @click="select(option.to)"
      >
        {{ option.label }}
        <span
          v-if="badgeOf(option.badgeGroup) > 0"
          class="rounded-full bg-brand px-1.5 text-[11px] font-bold tabular-nums text-white"
        >
          {{ nav.badgeLabel(badgeOf(option.badgeGroup)) }}
        </span>
      </button>
    </div>
  </div>
</template>
