<script setup lang="ts">
import { ref } from 'vue'
import { RouterLink } from 'vue-router'
import { PLAYBOOKS, playbookVolume } from '@/types/playbook'

// ปกที่ไฟล์ยังไม่วางจริง (404) → ใช้ placeholder เรียบ ๆ แทนรูปกากบาท
const failedCovers = ref<Set<string>>(new Set())
function onCoverError(id: string) {
  failedCovers.value = new Set([...failedCovers.value, id])
}
const isCoverBroken = (id: string) => failedCovers.value.has(id)
</script>

<template>
  <div>
    <!-- Editorial header -->
    <div class="mb-6">
      <p class="text-[11px] font-bold uppercase tracking-widest text-brand mb-1.5">
        <i class="bi bi-journal-bookmark-fill mr-1"></i> Student Handbook
      </p>
      <h1 class="text-2xl sm:text-3xl font-bold tracking-tight text-stone-900 leading-tight">คู่มือการทำงาน</h1>
      <p class="text-sm text-stone-500 mt-1.5">คู่มือการทำงาน — คู่มือนักเรียนฉบับ E-book อ่านเลื่อนลงได้ ครอบคลุม 6 หมวดหมู่</p>
    </div>

    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
      <RouterLink
        v-for="pb in PLAYBOOKS"
        :key="pb.id"
        :to="{ name: 'playbook-reader', params: { id: pb.id } }"
        class="page-card overflow-hidden flex flex-col card-hover"
      >
        <!-- 🔖 ปก -->
        <div class="relative aspect-[3/4] bg-stone-100 flex items-center justify-center">
          <img
            v-if="!isCoverBroken(pb.id)"
            :src="pb.coverImage"
            :alt="`ปก ${pb.title}`"
            loading="lazy"
            @error="onCoverError(pb.id)"
            class="absolute inset-0 w-full h-full object-cover"
          />
          <div v-else class="text-center text-stone-400">
            <i class="bi bi-journal-text text-5xl"></i>
            <p class="text-xs font-semibold mt-2">ยังไม่พร้อมใช้งาน</p>
          </div>
          <!-- ป้ายเล่มที่ -->
          <span class="absolute top-3 left-3 px-2 py-1 rounded-full bg-brand text-white text-[11px] font-bold">
            เล่มที่ {{ playbookVolume(pb.id) }}
          </span>
        </div>

        <!-- ข้อมูลเล่ม -->
        <div class="p-4 flex flex-col flex-1">
          <h3 class="font-bold text-stone-900 leading-snug mb-1.5">{{ pb.title }}</h3>
          <p class="text-sm text-stone-500 mb-3 line-clamp-2">{{ pb.description }}</p>

          <div class="mt-auto flex items-center justify-between pt-3 border-t border-stone-200">
            <span class="text-xs text-stone-400 flex items-center gap-1.5">
              <i class="bi bi-file-earmark-text"></i> {{ pb.totalPages }} หน้า
            </span>
            <span class="inline-flex items-center gap-1.5 text-xs font-bold text-brand">
              อ่านเล่มนี้ <i class="bi bi-arrow-right"></i>
            </span>
          </div>
        </div>
      </RouterLink>
    </div>
  </div>
</template>
