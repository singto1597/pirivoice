<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from 'vue';
import Swal from 'sweetalert2';
import {
  uploadStudentExcel,
  startImportJob,
  listImportJobs,
  downloadImportTemplate,
} from '@/services/student';
import type { ImportJob, ImportJobStatus } from '@/types/student';
import {
  IMPORT_STATUS_LABELS,
  isImportJobRunning,
} from '@/constants/importStatus';

// Short polling — ดึงสถานะงานจาก API ทุกๆ 2.5 วิ (ผู้ใช้ไม่ต้องรอลุ้นหน้าเว็บค้าง)
const POLL_INTERVAL_MS = 2500;

const file = ref<File | null>(null);
const isUploading = ref(false);
const isDownloadingTemplate = ref(false);
const isStartingJobId = ref<number | null>(null);
const isRefreshing = ref(false);

// รายการงานใน Queue List (ใหม่สุดก่อนจาก backend)
const jobs = ref<ImportJob[]>([]);
const isJobsLoading = ref(true);
// โหลดครั้งแรก/รีเฟรชพลาด (network ติดขัด) — ห้ามโชว์ "ยังไม่มีไฟล์" หลอกครู (อาจมีไฟล์ในคิวจริง)
const loadError = ref(false);
// poll ติดกันเกินลิมิต — โชว์แบนเนอร์บอก user ว่าเชื่อมต่อไม่แน่นอน (ไม่ปิด poll — พอ network กลับมา update เอง)
const isPollError = ref(false);

// ป้ายสถานะ / หลอดความคืบหน้า (daisyUI badge-* เดิม → stone/cardinal/emerald แบบ Civic)
const jobBadgeCls: Record<ImportJobStatus, string> = {
  PENDING: 'bg-stone-100 text-stone-600',
  QUEUED: 'bg-brand/10 text-brand',
  PROCESSING: 'bg-brand/10 text-brand',
  COMPLETED: 'bg-emerald-100 text-emerald-700',
  FAILED: 'bg-brand/10 text-brand',
};

const barFillCls: Record<ImportJobStatus, string> = {
  PENDING: 'bg-stone-300',
  QUEUED: 'bg-brand',
  PROCESSING: 'bg-brand',
  COMPLETED: 'bg-emerald-600',
  FAILED: 'bg-stone-400',
};

const barTextCls: Record<ImportJobStatus, string> = {
  PENDING: 'text-stone-500',
  QUEUED: 'text-brand',
  PROCESSING: 'text-brand',
  COMPLETED: 'text-emerald-700',
  FAILED: 'text-stone-600',
};

// Polling — กัน poll ซ้อน: ใน-flight guard กัน request ค้างซ้อนกันคิว
const POLL_FAIL_LIMIT = 3;
let pollTimer: number | null = null;
let pollInFlight = false;
let pollFailStreak = 0;

// จำนวนงานที่กำลังทำงาน (QUEUED/PROCESSING) — โชว์ indicator + ใช้ตัดสินใจ poll ต่อไป
const runningJobs = computed(() => jobs.value.filter((j) => isImportJobRunning(j.status)));

function errorMessage(e: unknown): string {
  return e instanceof Error ? e.message : 'เกิดข้อผิดพลาดจาก API';
}

// 🛡️ ชื่อไฟล์มาจาก user (backend สะท้อนกลับ verbatim) — ต้อง escape ก่อนใส่ใน html ของ Swal
// (SweetAlert2 แทรก html ผ่าน innerHTML → ไฟล์ชื่อ <img onerror=...> ที่ถูกกฎหมายใน Linux/Mac กลายเป็น XSS ได้)
function escapeHtml(value: string): string {
  const chars: Record<string, string> = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
  return value.replace(/[&<>"']/g, (c) => chars[c] ?? c);
}

function onFileChange(e: Event) {
  const input = e.target as HTMLInputElement;
  file.value = input.files?.[0] || null;
  // รีเซ็ตค่า input หลังอ่าน — ให้เลือกไฟล์เดิมซ้ำได้อีก (change event จะไม่ยิงถ้าค่าไม่เปลี่ยน)
  input.value = '';
}

// ===================== ดาวน์โหลด Template =====================
async function handleDownloadTemplate() {
  isDownloadingTemplate.value = true;
  try {
    const blob = await downloadImportTemplate();
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'student_import_template.xlsx';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    // revoke ช้าๆ — browser ดาวน์โหลดแบบ async ถ้า revoke ทันทีบางตัว (เช่น Firefox) จะได้ไฟล์ 0 bytes
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (e) {
    Swal.fire({ icon: 'error', title: 'ดาวน์โหลดไม่สำเร็จ', text: errorMessage(e) });
  } finally {
    isDownloadingTemplate.value = false;
  }
}

// ===================== อัปโหลด → เข้า Queue ทันที =====================
async function handleUpload() {
  if (!file.value) {
    Swal.fire({ icon: 'warning', title: 'เลือกไฟล์ก่อน', text: 'กรุณาเลือกไฟล์ Excel (.xlsx)' });
    return;
  }
  // เฉพาะ .xlsx — legacy .xls (BIFF) อ่านด้วย openpyxl ไม่ได้ (รับแล้วก็ 400) กันเลยตั้งแต่หน้าเว็บ
  if (!/\.xlsx$/i.test(file.value.name)) {
    Swal.fire({ icon: 'warning', title: 'ไฟล์ไม่ถูกต้อง', text: 'กรุณาใช้ไฟล์ .xlsx' });
    return;
  }

  isUploading.value = true;
  try {
    const job = await uploadStudentExcel(file.value);
    file.value = null;
    await refreshJobs();
    Swal.fire({
      icon: 'success',
      title: 'อัปโหลดเข้า Queue แล้ว!',
      // escapeHtml ชื่อไฟล์ (มาจาก user) กัน XSS — Swal ใช้ innerHTML
      html: `ไฟล์ <b>${escapeHtml(job.file_name)}</b> พบข้อมูล <b>${job.total_rows}</b> แถว<br>กดปุ่ม <b>"เริ่มเดี๋ยวนี้"</b> ใน Queue List ด้านล่างเพื่อสั่งให้ระบบทำงาน`,
    });
  } catch (e) {
    Swal.fire({ icon: 'error', title: 'อัปโหลดไม่สำเร็จ', text: errorMessage(e) });
  } finally {
    isUploading.value = false;
  }
}

// ===================== กดเริ่มงาน (เริ่มเดี๋ยวนี้ / ลองใหม่) =====================
async function handleStart(jobId: number) {
  isStartingJobId.value = jobId;
  try {
    const job = await startImportJob(jobId);
    await refreshJobs();
    if (job.status === 'QUEUED') {
      Swal.fire({
        icon: 'success',
        title: 'เริ่มงานแล้ว!',
        text: 'ระบบกำลังนำเข้านักเรียนเบื้องหลัง — ดูความคืบหน้า (หลอดเปอร์เซ็นต์) ใน Queue List',
        timer: 2500,
        showConfirmButton: false,
      });
    }
  } catch (e) {
    Swal.fire({ icon: 'error', title: 'เริ่มงานไม่สำเร็จ', text: errorMessage(e) });
  } finally {
    isStartingJobId.value = null;
  }
}

// ===================== ดึง Queue List + Short Polling =====================
async function refreshJobs(showSpinner = false) {
  if (showSpinner) isRefreshing.value = true;
  try {
    jobs.value = await listImportJobs();
    loadError.value = false;
    pollFailStreak = 0;
    isPollError.value = false;
    // มีงานกำลังทำงาน/รอ worker → เริ่ม poll; ไม่มี → หยุด (ประหยัด request)
    if (runningJobs.value.length) startPolling();
    else stopPolling();
  } catch {
    // ยังเก็บรายการเดิมไว้ — แค่ปักธงพลาด (กันโชว์ "ไม่มีไฟล์" หลอก + เปิดให้ user กดลองใหม่ได้)
    loadError.value = true;
  } finally {
    isJobsLoading.value = false;
    if (showSpinner) isRefreshing.value = false;
  }
}

async function pollOnce() {
  try {
    jobs.value = await listImportJobs();
    pollFailStreak = 0;
    isPollError.value = false;
    // ไม่มีงานที่กำลังทำงานแล้ว → หยุด poll (ประหยัด request)
    if (!runningJobs.value.length) stopPolling();
  } catch {
    // error ชั่วคราว (network หลุด) — นับต่อเนื่อง ถ้าติดกันเกินลิมิต โชว์แบนเนอร์เตือน
    // (ไม่หยุด poll ถาวร — พอ network กลับมา รอบถัดไปจะ update + ปิดแบนเนอร์เอง)
    pollFailStreak += 1;
    if (pollFailStreak >= POLL_FAIL_LIMIT) isPollError.value = true;
  }
}

function startPolling() {
  if (pollTimer !== null) return;
  pollTimer = window.setInterval(async () => {
    // ใน-flight guard — ถ้ารอบก่อนยังไม่เสร็จ (network ช้า) ข้ามรอบ กัน poll ซ้อน
    if (pollInFlight) return;
    pollInFlight = true;
    try {
      await pollOnce();
    } finally {
      pollInFlight = false;
    }
  }, POLL_INTERVAL_MS);
}

function stopPolling() {
  if (pollTimer !== null) {
    window.clearInterval(pollTimer);
    pollTimer = null;
  }
}

onMounted(refreshJobs);
onBeforeUnmount(stopPolling);
</script>

<template>
  <div class="max-w-5xl mx-auto">
    <!-- 🔴 ไม่มี <h1>/eyebrow ที่นี่ — `AppHeader` แสดงชื่อหน้าจาก `routeTitles` เป็น <h1> ให้แล้ว (R0.3) -->
    <!-- ปุ่มดาวน์โหลด Template -->
    <div class="flex flex-wrap items-center justify-end gap-3 mb-5">
      <button
        @click="handleDownloadTemplate"
        :disabled="isDownloadingTemplate"
        class="inline-flex items-center gap-1.5 rounded-xl border border-stone-200 bg-white px-4 py-2 text-sm font-medium text-stone-600 transition hover:bg-stone-50 hover:text-stone-800 disabled:opacity-50"
      >
        <span v-if="isDownloadingTemplate" class="h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent"></span>
        <i v-else class="bi bi-file-earmark-excel"></i>
        ดาวน์โหลดตัวอย่างไฟล์ (Template)
      </button>
    </div>

    <!-- รูปแบบไฟล์ — อธิบายชัดเจนว่าคอลัมน์ต้องเป๊ะ -->
    <div class="mb-5 rounded-2xl border border-stone-200 bg-white p-5 text-sm sm:p-6">
      <p class="mb-3 font-semibold text-stone-900">
        <i class="bi bi-info-circle mr-1.5 text-brand"></i>
        ไฟล์ต้องมีคอลัมน์และข้อมูลในลักษณะนี้ ระบบถึงจะอ่านได้แน่นอน — <span class="underline">คอลัมน์ต้องเป๊ะ</span>
        (ห้ามเพิ่ม / ลบ / เปลี่ยนชื่อ / ซ้ำ):
      </p>
      <div class="overflow-x-auto rounded-xl border border-stone-200">
        <table class="w-full text-xs">
          <thead>
            <tr class="bg-stone-50 text-left text-stone-500">
              <th class="px-3 py-2 font-semibold">คอลัมน์</th>
              <th class="px-3 py-2 font-semibold">จำเป็น</th>
              <th class="px-3 py-2 font-semibold">ตัวอย่าง</th>
              <th class="min-w-[200px] px-3 py-2 font-semibold">คำอธิบาย</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-stone-100">
            <tr>
              <td class="px-3 py-2 font-mono text-stone-700">รหัสนักเรียน</td><td class="px-3 py-2 text-stone-600">✅ ต้องมี</td><td class="px-3 py-2 font-mono text-stone-700">47001</td>
              <td class="px-3 py-2 text-stone-600">เลขประจำตัว (ใช้เป็น username + รหัสผ่านเริ่มต้น)</td>
            </tr>
            <tr>
              <td class="px-3 py-2 font-mono text-stone-700">ห้องเรียน</td><td class="px-3 py-2 text-stone-600">✅ ต้องมี</td><td class="px-3 py-2 font-mono text-stone-700">ม.4/1</td>
              <td class="px-3 py-2 text-stone-600">ระบบสร้างห้องอัตโนมัติถ้ายังไม่มี</td>
            </tr>
            <tr>
              <td class="px-3 py-2 font-mono text-stone-700">เลขที่</td><td class="px-3 py-2 text-stone-600">✅ ต้องมี</td><td class="px-3 py-2 font-mono text-stone-700">1</td>
              <td class="px-3 py-2 text-stone-600">ตัวเลข (1, 2, 3 ...)</td>
            </tr>
            <tr>
              <td class="px-3 py-2 font-mono text-stone-700">คำนำหน้า</td><td class="px-3 py-2 text-stone-600">เว้นได้</td><td class="px-3 py-2 font-mono text-stone-700">นาย / นางสาว</td><td class="px-3 py-2 text-stone-600">—</td>
            </tr>
            <tr>
              <td class="px-3 py-2 font-mono text-stone-700">ชื่อ</td><td class="px-3 py-2 text-stone-600">แนะนำ</td><td class="px-3 py-2 font-mono text-stone-700">สมชาย</td>
              <td class="px-3 py-2 text-stone-600">ห้ามเว้นทั้ง ชื่อ + นามสกุล</td>
            </tr>
            <tr>
              <td class="px-3 py-2 font-mono text-stone-700">นามสกุล</td><td class="px-3 py-2 text-stone-600">แนะนำ</td><td class="px-3 py-2 font-mono text-stone-700">ใจดี</td><td class="px-3 py-2 text-stone-600">—</td>
            </tr>
            <tr>
              <td class="px-3 py-2 font-mono text-stone-700">ชื่อเล่น</td><td class="px-3 py-2 text-stone-600">เว้นได้</td><td class="px-3 py-2 font-mono text-stone-700">ชาย</td><td class="px-3 py-2 text-stone-600">—</td>
            </tr>
            <tr>
              <td class="px-3 py-2 font-mono text-stone-700">ตำแหน่งในห้องเรียน</td><td class="px-3 py-2 text-stone-600">เว้นได้</td><td class="px-3 py-2 font-mono text-stone-700">หัวหน้าห้อง</td>
              <td class="px-3 py-2 text-stone-600">เว้นว่าง = นักเรียนธรรมดา</td>
            </tr>
          </tbody>
        </table>
      </div>
      <ul class="mt-3 space-y-1 text-xs text-stone-600">
        <li>
          • <b class="text-stone-700">ตำแหน่ง</b> ที่รองรับ: หัวหน้าห้อง, รองวิชาการ, รองวินัย, รองกิจกรรม, รองปฏิคม,
          ประธานระดับ, สภานักเรียน, ประธานสภา, ครู, ครูสภา, แอดมิน
        </li>
        <li>• <b class="text-stone-700">ห้องเรียน</b> รูปแบบ: ม.4/1 (ระดับ/ห้อง)</li>
        <li>• 🔑 รหัสผ่านเริ่มต้น = เลขรหัสนักเรียน (เช่น 47001 → เข้าระบบด้วย 47001/47001)</li>
        <li>• ⚠️ ไฟล์ตัวอย่างมีแถวตัวอย่าง (00001, 00002) — ระบบจะ<b class="text-stone-700">ข้ามแถวที่รหัสขึ้นต้น 000</b> อัตโนมัติ
          (ลบออกก่อนอัปโหลดก็ได้เพื่อความเรียบร้อย)</li>
      </ul>
    </div>

    <!-- ขั้นตอนที่ 1: อัปโหลดเข้า Queue -->
    <div class="space-y-4 rounded-2xl border border-stone-200 bg-white p-5 sm:p-6">
      <div>
        <label class="mb-2 block text-sm font-semibold text-stone-700">
          1. เลือกไฟล์ Excel <span class="font-normal text-stone-400">(.xlsx)</span>
        </label>
        <div class="flex flex-wrap items-center gap-2">
          <input
            type="file"
            accept=".xlsx"
            @change="onFileChange"
            class="min-w-[200px] flex-1 text-sm file:mr-3 file:rounded-lg file:border-0 file:bg-brand file:px-4 file:py-2 file:text-white hover:file:bg-brand-strong"
          />
          <!-- แสดงชื่อไฟล์ที่เลือก — custom file input ซ่อนข้อความ "No file chosen" ของ browser -->
          <span
            v-if="file"
            class="inline-flex max-w-full items-center gap-1.5 rounded-lg border border-stone-200 bg-stone-50 px-2.5 py-1.5 text-sm text-stone-700"
            :title="file.name"
          >
            <i class="bi bi-file-earmark-excel text-brand"></i>
            <span class="max-w-[260px] truncate">{{ file.name }}</span>
            <button type="button" class="text-stone-400 transition hover:text-brand" title="ล้างไฟล์ที่เลือก" @click="file = null">
              <i class="bi bi-x-lg"></i>
            </button>
          </span>
          <span v-else class="text-xs text-stone-400">ยังไม่ได้เลือกไฟล์ (.xlsx)</span>
        </div>
      </div>
      <button
        @click="handleUpload"
        :disabled="isUploading"
        class="w-full rounded-lg bg-brand py-3 font-medium text-white transition hover:bg-brand-strong disabled:opacity-50"
      >
        <span v-if="isUploading" class="mr-1 inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent align-[-2px]"></span>
        {{ isUploading ? 'กำลังตรวจสอบและอัปโหลดเข้า Queue...' : 'อัปโหลดเข้า Queue' }}
      </button>
      <p class="text-xs text-stone-400">
        <i class="bi bi-arrow-clockwise mr-1"></i>
        อัปโหลดเสร็จ ไฟล์จะถูกส่งเข้า <b class="text-stone-600">Queue</b> ทันที — ไม่ต้องค้างหน้านี้รอ
        จากนั้นกด <b class="text-stone-600">"เริ่มเดี๋ยวนี้"</b> ใน Queue List เพื่อสั่งให้ระบบทำงานเบื้องหลัง
      </p>
    </div>

    <!-- ขั้นตอนที่ 2: Queue List + Progress Bar -->
    <div class="mt-5 rounded-2xl border border-stone-200 bg-white p-5 sm:p-6">
      <div class="mb-4 flex flex-wrap items-center justify-between gap-2">
        <h2 class="text-lg font-bold text-stone-900">
          <i class="bi bi-list-ul mr-1 text-brand"></i> Queue List — คิวนำเข้านักเรียน
          <span v-if="jobs.length" class="ml-1 text-sm font-normal text-stone-400">({{ jobs.length }})</span>
        </h2>
        <div class="flex items-center gap-2">
          <span v-if="runningJobs.length" class="inline-flex items-center gap-1.5 rounded-full bg-brand/10 px-2.5 py-1 text-xs font-semibold text-brand">
            <span class="h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent"></span>
            กำลังทำงาน {{ runningJobs.length }} งาน
          </span>
          <button
            @click="refreshJobs(true)"
            :disabled="isRefreshing"
            class="inline-flex items-center gap-1.5 rounded-lg border border-stone-200 bg-white px-3 py-1.5 text-xs font-medium text-stone-600 transition hover:bg-stone-50 hover:text-stone-800 disabled:opacity-50"
          >
            <span v-if="isRefreshing" class="h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent"></span>
            <i v-else class="bi bi-arrow-clockwise"></i>
            รีเฟรช
          </button>
        </div>
      </div>

      <!-- poll ติดขัดต่อเนื่อง → บอก user ว่าระบบยังพยายามเชื่อมต่อ (bar ไม่ได้ค้างเงียบๆ) -->
      <div
        v-if="isPollError"
        class="mb-3 flex flex-wrap items-center gap-2 rounded-xl border border-brand/20 bg-brand/5 px-3 py-2.5 text-sm text-stone-700"
        role="alert"
      >
        <i class="bi bi-wifi-off mr-1 text-brand"></i>
        เชื่อมต่อกับระบบไม่เสถียร — สถานะอาจไม่ทันสมัย ระบบกำลังลองเชื่อมต่อใหม่ทุก
        {{ POLL_INTERVAL_MS / 1000 }} วินาที
        <button
          @click="refreshJobs(true)"
          :disabled="isRefreshing"
          class="ml-auto inline-flex items-center gap-1.5 rounded-lg border border-brand/20 bg-white px-3 py-1 text-xs font-bold text-brand transition hover:bg-brand/5 disabled:opacity-50"
        >
          <span v-if="isRefreshing" class="h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent"></span>
          <i v-else class="bi bi-arrow-clockwise"></i>
          ลองใหม่
        </button>
      </div>

      <!-- โหลดครั้งแรก/รีเฟรช → skeleton -->
      <div v-if="isJobsLoading" class="overflow-hidden rounded-xl border border-stone-200" aria-busy="true">
        <div class="divide-y divide-stone-100 bg-white">
          <div v-for="i in 4" :key="i" class="flex items-center gap-4 p-4">
            <div class="flex-1 space-y-2">
              <div class="h-4 w-1/3 animate-pulse rounded bg-stone-100"></div>
              <div class="h-3 w-1/2 animate-pulse rounded bg-stone-100"></div>
            </div>
            <div class="h-6 w-24 animate-pulse rounded-full bg-stone-100"></div>
            <div class="hidden h-4 w-28 animate-pulse rounded bg-stone-100 sm:block"></div>
          </div>
        </div>
      </div>

      <!-- โหลดพลาด (ไม่ใช่ "ไม่มีไฟล์") — โชว์ error + ปุ่มลองใหม่ กันครูเห็น "ไม่มีไฟล์" แล้วอัปโหลดซ้ำซ้อน -->
      <div v-else-if="loadError" class="rounded-xl border-2 border-dashed border-stone-200 bg-white py-12 text-center" role="alert">
        <i class="bi bi-wifi-off mb-2 block text-3xl text-stone-300"></i>
        <p class="text-sm font-semibold text-stone-700">ไม่สามารถโหลด Queue List ได้</p>
        <p class="mt-1 text-xs text-stone-500">ตรวจสอบการเชื่อมต่อกับระบบแล้วลองอีกครั้ง</p>
        <button
          @click="refreshJobs(true)"
          :disabled="isRefreshing"
          class="mt-4 inline-flex items-center gap-1.5 rounded-lg bg-brand px-4 py-2 text-xs font-bold text-white transition hover:bg-brand-strong disabled:opacity-50"
        >
          <span v-if="isRefreshing" class="h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent"></span>
          <i v-else class="bi bi-arrow-clockwise"></i>
          ลองใหม่
        </button>
      </div>

      <div v-else-if="jobs.length === 0" class="py-10 text-center text-sm text-stone-500">
        <i class="bi bi-inbox mb-2 block text-3xl text-stone-300"></i>
        ยังไม่มีไฟล์ในคิว — อัปโหลดไฟล์ด้านบนก่อน
      </div>

      <div v-else class="overflow-x-auto rounded-xl border border-stone-200">
        <table class="w-full text-sm">
          <thead>
            <tr class="bg-stone-50 text-left text-[11px] text-stone-500">
              <th class="px-4 py-3 font-semibold">ไฟล์</th>
              <th class="px-4 py-3 font-semibold">สถานะ</th>
              <th class="min-w-[220px] px-4 py-3 font-semibold">ความคืบหน้า</th>
              <th class="px-4 py-3 font-semibold">นำเข้า / ข้าม</th>
              <th class="px-4 py-3 text-right font-semibold">จัดการ</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-stone-100 bg-white">
            <template v-for="job in jobs" :key="job.id">
              <tr class="align-middle">
                <td class="px-4 py-3 font-medium text-stone-800">
                  {{ job.file_name }}
                  <div class="text-xs text-stone-400">
                    {{ new Date(job.created_at).toLocaleString('th-TH', { timeZone: 'Asia/Bangkok' }) }}
                  </div>
                </td>
                <td class="px-4 py-3">
                  <span class="inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold" :class="jobBadgeCls[job.status]">
                    {{ IMPORT_STATUS_LABELS[job.status] }}
                  </span>
                  <!-- error_message โชว์เฉพาะ FAILED — กัน error เก่าค้างเมื่อลองใหม่แล้วสำเร็จ -->
                  <div v-if="job.status === 'FAILED' && job.error_message" class="mt-1 max-w-[180px] text-xs text-brand">
                    {{ job.error_message }}
                  </div>
                </td>
                <td class="px-4 py-3">
                  <!-- หลอดเปอร์เซ็นต์: เติมตาม progress_percent, เขียวเต็มหลอดเมื่อเสร็จ -->
                  <div class="flex items-center gap-2">
                    <div class="relative h-5 min-w-[130px] flex-1 overflow-hidden rounded-full border border-stone-200 bg-stone-100">
                      <div
                        class="absolute inset-y-0 left-0 rounded-full transition-all duration-500 ease-out"
                        :class="[barFillCls[job.status], isImportJobRunning(job.status) ? 'animate-pulse' : '']"
                        :style="{ width: job.progress_percent + '%' }"
                      ></div>
                      <span
                        v-if="job.status === 'COMPLETED'"
                        class="absolute inset-0 flex items-center justify-center text-[11px] font-bold text-white"
                      >
                        <i class="bi bi-check-lg mr-0.5"></i> เสร็จสิ้น
                      </span>
                    </div>
                    <span class="shrink-0 font-display text-sm font-bold tabular-nums" :class="barTextCls[job.status]">
                      {{ job.progress_percent }}%
                    </span>
                  </div>
                  <div class="mt-1 text-xs text-stone-500">
                    {{ job.processed_rows }}/{{ job.total_rows }} แถว
                  </div>
                </td>
                <td class="whitespace-nowrap px-4 py-3 text-sm text-stone-600">
                  <span class="font-semibold text-emerald-700">{{ job.imported_count }}</span>
                  /
                  <span class="font-semibold text-stone-500">{{ job.skipped_count }}</span>
                </td>
                <td class="px-4 py-3 text-right">
                  <!-- รอเริ่มงาน → ปุ่มเริ่มเดี๋ยวนี้ -->
                  <button
                    v-if="job.status === 'PENDING'"
                    @click="handleStart(job.id)"
                    :disabled="isStartingJobId !== null"
                    class="inline-flex items-center gap-1.5 rounded-lg bg-brand px-3.5 py-2 text-xs font-semibold text-white transition hover:bg-brand-strong disabled:opacity-50"
                  >
                    <span v-if="isStartingJobId === job.id" class="h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent"></span>
                    <i v-else class="bi bi-play-fill"></i>
                    เริ่มเดี๋ยวนี้
                  </button>
                  <!-- ล้มเหลว → ลองใหม่ -->
                  <button
                    v-else-if="job.status === 'FAILED'"
                    @click="handleStart(job.id)"
                    :disabled="isStartingJobId !== null"
                    class="inline-flex items-center gap-1.5 rounded-lg border border-brand/30 bg-white px-3.5 py-2 text-xs font-semibold text-brand transition hover:bg-brand/5 disabled:opacity-50"
                  >
                    <span v-if="isStartingJobId === job.id" class="h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent"></span>
                    <i v-else class="bi bi-arrow-counterclockwise"></i>
                    ลองใหม่
                  </button>
                  <!-- กำลังทำงาน/รอ worker → spinner -->
                  <span v-else-if="isImportJobRunning(job.status)" class="inline-flex items-center gap-1.5 text-xs font-medium text-brand">
                    <span class="h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent"></span> ทำงานอยู่
                  </span>
                  <span v-else class="text-xs text-stone-400">—</span>
                </td>
              </tr>
              <!-- error_logs รายแถว (แถวที่ข้อมูลผิด/ถูกข้าม) -->
              <tr v-if="job.error_logs.length" :key="'err-' + job.id" class="border-t-0">
                <td colspan="5" class="px-4 py-2">
                  <details class="rounded-xl border border-brand/15 bg-brand/5 p-3 text-xs">
                    <summary class="cursor-pointer font-semibold text-brand">
                      {{ job.file_name }} — ข้อผิดพลาด {{ job.error_logs.length }} รายการ
                    </summary>
                    <ul class="mt-2 max-h-40 list-disc space-y-1 pl-4 text-brand/90">
                      <li v-for="(e, idx) in job.error_logs" :key="idx">{{ e }}</li>
                    </ul>
                  </details>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
