<script setup lang="ts">
import { ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { PLAYBOOKS } from '@/types/playbook'

/**
 * เมนู "P.R. Playbooks" ใน sidebar — หัวข้อหลักขยาย/ย่อได้ มีเมนูย่อย 6 เล่ม
 * ใช้ทั้ง desktop sidebar และ mobile drawer (mobile ส่ง close-on-navigate + @navigate)
 */
const props = withDefaults(
  defineProps<{
    /** ปิด drawer หลังคลิกเมนูย่อย (ใช้กับมือถือ) */
    closeOnNavigate?: boolean
  }>(),
  { closeOnNavigate: false },
)

const emit = defineEmits<{ navigate: [] }>()

const route = useRoute()

// เปิดเมนูค้างไว้เมื่ออยู่หน้า /playbooks อยู่แล้ว
const isOpen = ref(route.path.startsWith('/playbooks'))

const parentActive = () => route.path.startsWith('/playbooks')
const isChildActive = (id: string): boolean =>
  route.name === 'playbook-reader' && route.params.id === id

function onChildClick() {
  if (props.closeOnNavigate) emit('navigate')
}
</script>

<template>
  <div>
    <!-- หัวข้อหลัก: คลิก → หน้าหนังสือ, กด chevron → ขยาย/ย่อเมนู -->
    <div
      class="flex items-center rounded-xl transition-all"
      :class="parentActive() ? 'bg-stone-100 text-brand border border-stone-200' : 'text-stone-500 hover:bg-stone-50 hover:text-stone-900'"
    >
      <RouterLink to="/app/playbooks" class="flex-1 flex items-center px-3.5 py-3 text-sm font-semibold min-w-0">
        <i class="bi bi-journal-bookmark-fill text-lg mr-3"></i>
        <span class="truncate">P.R. Playbooks</span>
      </RouterLink>
      <button
        type="button"
        :title="isOpen ? 'ย่อเมนู' : 'ขยายเมนู'"
        :aria-expanded="isOpen"
        class="w-8 h-8 flex items-center justify-center rounded-lg text-stone-400 hover:bg-stone-100 hover:text-stone-700 transition-colors shrink-0 mr-1.5"
        @click="isOpen = !isOpen"
      >
        <i :class="['bi text-xs transition-transform', isOpen ? 'bi-chevron-up' : 'bi-chevron-down']"></i>
      </button>
    </div>

    <!-- เมนูย่อย 6 เล่ม -->
    <Transition name="expand">
      <div
        v-if="isOpen"
        class="mt-1 ml-4 pl-3 border-l-2 space-y-0.5"
        :class="parentActive() ? 'border-brand' : 'border-stone-100'"
      >
        <RouterLink
          v-for="pb in PLAYBOOKS"
          :key="pb.id"
          :to="{ name: 'playbook-reader', params: { id: pb.id } }"
          @click="onChildClick"
          class="flex items-center px-3 py-2 text-[13px] font-medium rounded-lg transition-colors"
          :class="isChildActive(pb.id) ? 'bg-stone-100 text-brand' : 'text-stone-500 hover:bg-stone-100 hover:text-stone-900'"
        >
          <i class="bi bi-book-half text-sm mr-2.5" :class="isChildActive(pb.id) ? 'text-brand' : 'text-stone-400'"></i>
          <span class="truncate">{{ pb.title }}</span>
        </RouterLink>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.expand-enter-active,
.expand-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}
.expand-enter-from,
.expand-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}
</style>
