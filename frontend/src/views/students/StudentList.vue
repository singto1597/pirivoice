<script setup lang="ts">
import { ref, onMounted } from 'vue';
import Swal from 'sweetalert2';
import { listStudents, listRooms, updateStudent } from '@/services/student'
import { roleLabel, STUDENT_ROLE_OPTIONS } from '@/constants/roles';
import type { Student, Room } from '@/types/student';

const students = ref<Student[]>([]);
const rooms = ref<Room[]>([]);
const isLoading = ref(true);
const hasError = ref(false);
const roomFilter = ref<number | ''>('');
const search = ref('');

;

async function load() {
  isLoading.value = true;
  hasError.value = false;
  try {
    [students.value, rooms.value] = await Promise.all([
      listStudents({ room_id: roomFilter.value || undefined, search: search.value || undefined }),
      listRooms(),
    ]);
  } catch (e) {
    const msg = typeof e === 'string' ? e : e instanceof Error ? e.message : 'โหลดข้อมูลไม่สำเร็จ';
    hasError.value = true;
    Swal.fire({ icon: 'error', title: 'โหลดข้อมูลไม่สำเร็จ', text: msg });
  } finally {
    isLoading.value = false;
  }
}
onMounted(load);

async function changeRole(student: Student) {
  const { value } = await Swal.fire({
    icon: 'question',
    title: 'เปลี่ยนตำแหน่ง: ' + (student.first_name || '') + ' ' + (student.last_name || ''),
    input: 'select',
    inputOptions: STUDENT_ROLE_OPTIONS,
    inputValue: student.class_role,
    showCancelButton: true,
    confirmButtonText: 'บันทึก',
    cancelButtonText: 'ยกเลิก',
  });
  if (!value) return;
  try {
    await updateStudent(student.id, { class_role: value });
    Swal.fire({ icon: 'success', title: 'บันทึกแล้ว', timer: 1000, showConfirmButton: false });
    load();
  } catch (e) {
    const msg = typeof e === 'string' ? e : e instanceof Error ? e.message : 'ไม่สำเร็จ';
    Swal.fire({ icon: 'error', title: 'ไม่สำเร็จ', text: msg });
  }
}
</script>

<template>
  <div>
    <!-- 🔴 ไม่มี <h1>/eyebrow ที่นี่ — `AppHeader` แสดงชื่อหน้าจาก `routeTitles` เป็น <h1> ให้แล้ว (R0.3) -->

    <!-- Filters (mobile = แนวตั้งเต็มแถว, sm+ = แนวนอน) -->
    <div class="grid grid-cols-1 gap-2 sm:flex sm:items-center sm:gap-3 mb-5">
      <select v-model="roomFilter" @change="load" class="w-full rounded-xl border border-stone-300 bg-white px-3 py-2.5 text-sm sm:w-auto">
        <option value="">ทุกห้อง</option>
        <option v-for="r in rooms" :key="r.id" :value="r.id">{{ r.room_code }}</option>
      </select>
      <input v-model="search" @keyup.enter="load" type="text" placeholder="ค้นหา รหัสนักเรียน/ชื่อ..."
        class="w-full rounded-xl border border-stone-300 px-3 py-2.5 text-sm sm:flex-1" />
      <button @click="load" class="inline-flex items-center rounded-xl bg-stone-100 px-4 min-h-11 py-2.5 text-sm font-medium hover:bg-stone-200">
        <i class="bi bi-search"></i> ค้นหา
      </button>
    </div>

    <!-- Loading skeleton -->
    <div v-if="isLoading" class="overflow-hidden rounded-2xl border border-stone-200 bg-white" aria-busy="true">
      <div class="divide-y divide-stone-100">
        <div v-for="i in 6" :key="i" class="flex items-center gap-3 p-4">
          <div class="h-11 w-11 shrink-0 animate-pulse rounded-full bg-stone-100"></div>
          <div class="flex-1 space-y-2">
            <div class="h-4 w-1/3 animate-pulse rounded bg-stone-100"></div>
            <div class="h-3 w-1/2 animate-pulse rounded bg-stone-100"></div>
          </div>
          <div class="h-6 w-20 animate-pulse rounded-full bg-stone-100"></div>
        </div>
      </div>
    </div>

    <!-- Error + retry -->
    <div v-else-if="hasError" class="rounded-2xl border-2 border-dashed border-stone-200 bg-white py-16 text-center">
      <i class="bi bi-people mb-3 block text-3xl text-stone-300"></i>
      <p class="text-[15px] font-semibold text-stone-700">ไม่สามารถโหลดรายชื่อนักเรียนได้</p>
      <p class="mt-1 text-sm text-stone-500">ตรวจสอบการเชื่อมต่อแล้วลองอีกครั้ง</p>
      <button
        type="button"
        @click="load"
        class="mt-5 inline-flex items-center gap-2 rounded-lg bg-brand px-5 min-h-11 py-2.5 text-[13px] font-bold text-white transition-colors hover:bg-brand-strong"
      >
        <i class="bi bi-arrow-clockwise"></i> ลองใหม่
      </button>
    </div>

    <div v-else>
      <!-- ===== มือถือ: การ์ดรายการ (อ่านง่าย ไม่เบียดตาราง) ===== -->
      <div class="grid grid-cols-1 gap-3 md:hidden">
        <div
          v-for="s in students"
          :key="s.id"
          class="card-hover flex items-center gap-3 rounded-2xl border border-stone-200 bg-white p-4"
        >
          <div class="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-stone-100 font-bold text-stone-600">
            {{ (s.first_name || 'ส').charAt(0).toUpperCase() }}
          </div>
          <div class="min-w-0 flex-1">
            <p class="truncate font-semibold text-stone-900">
              {{ s.prefix || '' }} {{ s.first_name || '' }} {{ s.last_name || '' }}
            </p>
            <p class="mt-0.5 text-xs text-stone-500">
              <span class="font-mono">{{ s.student_id }}</span>
              <span v-if="s.student_no" class="ml-1.5">เลขที่ {{ s.student_no }}</span>
              <span class="ml-1.5">· {{ s.room_code }}</span>
            </p>
          </div>
          <button @click="changeRole(s)" class="inline-flex min-w-11 shrink-0 items-center justify-center rounded-full px-2.5 min-h-11 py-1 text-xs font-medium"
            :class="s.class_role === 'student' ? 'bg-stone-100 text-stone-600' : 'bg-brand/10 text-brand'">
            {{ roleLabel(s.class_role) }} <i class="bi bi-pencil-square text-[10px]"></i>
          </button>
        </div>
        <div v-if="!students.length" class="rounded-2xl border border-dashed border-stone-200 p-8 text-center text-stone-500">
          <i class="bi bi-people mb-2 block text-3xl text-stone-300"></i>
          ไม่พบนักเรียน
        </div>
      </div>

      <!-- ===== เดสก์ท็อป: ตาราง ===== -->
      <div class="hidden overflow-hidden rounded-2xl border border-stone-200 bg-white md:block">
        <table class="w-full text-sm">
          <thead class="bg-stone-50 text-stone-500">
            <tr>
              <th class="px-4 py-3 text-left font-semibold text-[11px]">เลขที่</th>
              <th class="px-4 py-3 text-left font-semibold text-[11px]">รหัสนักเรียน</th>
              <th class="px-4 py-3 text-left font-semibold text-[11px]">ชื่อ-นามสกุล</th>
              <th class="px-4 py-3 text-left font-semibold text-[11px]">ห้อง</th>
              <th class="px-4 py-3 text-left font-semibold text-[11px]">ตำแหน่ง</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-stone-100">
            <tr v-for="s in students" :key="s.id" class="transition-colors hover:bg-stone-50">
              <td class="px-4 py-2.5 text-stone-500">{{ s.student_no }}</td>
              <td class="px-4 py-2.5 font-mono text-stone-600">{{ s.student_id }}</td>
              <td class="px-4 py-2.5 font-medium text-stone-800">
                {{ s.prefix || '' }} {{ s.first_name || '' }} {{ s.last_name || '' }}
              </td>
              <td class="px-4 py-2.5 text-stone-600">{{ s.room_code }}</td>
              <td class="px-4 py-2.5">
                <button @click="changeRole(s)" class="inline-flex min-w-11 items-center justify-center rounded-full px-2.5 min-h-11 py-1 text-xs font-medium"
                  :class="s.class_role === 'student' ? 'bg-stone-100 text-stone-600' : 'bg-brand/10 text-brand'">
                  {{ roleLabel(s.class_role) }} <i class="bi bi-pencil-square text-[10px]"></i>
                </button>
              </td>
            </tr>
            <tr v-if="!students.length">
              <td colspan="5" class="px-4 py-10 text-center text-stone-500">
                <i class="bi bi-inbox mb-1 block text-2xl text-stone-300"></i>
                ไม่พบนักเรียน
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
