<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue';
import Swal from 'sweetalert2';
import { listAuditLogs } from '@/services/audit';
import type { AuditLogEntry } from '@/types/audit';
import { fmtDateTimeSec } from '@/datetime';
import PaginationBar from '@/components/PaginationBar.vue';

// ===== ป้าย action → ภาษาไทย (ให้ตรงกับ backend dashboard_service.ACTION_LABELS) =====
const ACTION_LABELS: Record<string, string> = {
  login: 'เข้าสู่ระบบ',
  CREATE_ISSUE: 'แจ้งเรื่องใหม่',
  UPDATE_ISSUE: 'แก้ไขเรื่อง',
  ACCEPT_ISSUE: 'รับเรื่อง',
  UPDATE_COUNTDOWN: 'ตั้งเวลาแก้',
  CREATE_STEP: 'เพิ่มขั้นตอน',
  UPDATE_STEP: 'ทำขั้นตอนเสร็จ',
  ESCALATE_ISSUE: 'ส่งต่อให้ระดับสูงขึ้น',
  RESOLVE_ISSUE: 'ปิดเรื่อง',
  CANCEL_ISSUE: 'ยกเลิกเรื่อง',
  REJECT_ISSUE: 'ปฏิเสธเรื่อง',
  CREATE_COMMENT: 'คอมเมนต์',
  UPDATE_COMMENT: 'แก้คอมเมนต์',
  DELETE_COMMENT: 'ลบคอมเมนต์',
  CREATE_USER: 'สร้างผู้ใช้',
  CHANGE_PASSWORD: 'เปลี่ยนรหัสผ่าน',
  UPDATE_STUDENT: 'แก้ไขนักเรียน',
  CREATE_ROOM: 'สร้างห้อง',
  UPDATE_PROFILE: 'แก้โปรไฟล์',
  UPLOAD_IMPORT_EXCEL: 'อัปโหลด Excel',
  START_IMPORT_JOB: 'เริ่มนำเข้า',
  PROCESS_IMPORT_JOB: 'กำลังนำเข้า',
  COMPLETE_IMPORT_JOB: 'นำเข้าสำเร็จ',
  FAIL_IMPORT_JOB: 'นำเข้าล้มเหลว',
  RECOVER_IMPORT_JOB: 'กู้คืนงานนำเข้า',
  READ_ME: 'ดูข้อมูลตัวเอง',
  READ_PROFILE: 'ดูโปรไฟล์',
  READ_ISSUES: 'ดูรายการเรื่อง',
  READ_ISSUE: 'ดูรายละเอียดเรื่อง',
  READ_ROOMS: 'ดูห้องเรียน',
  READ_STUDENTS: 'ดูรายชื่อนักเรียน',
  READ_IMPORT_JOBS: 'ดูงานนำเข้า',
  READ_DASHBOARD: 'ดูแดชบอร์ด',
  READ_DASHBOARD_TRAFFIC: 'ดูสถิติการใช้งาน',
  READ_AUDIT_LOGS: 'ดูบันทึกการใช้งาน',
  CREATE_ANNOUNCEMENT: 'สร้างประกาศ',
  UPDATE_ANNOUNCEMENT: 'แก้ไขประกาศ',
  DELETE_ANNOUNCEMENT: 'ลบประกาศ',
  RESTORE_ANNOUNCEMENT: 'กู้คืนประกาศ',
  // ⚠️ map นี้เป็นของหน้าจอ *นี้* โดยเฉพาะ — backend มี ACTION_LABELS ของตัวเองอีกชุด
  //    (`services/dashboard_service.py` ใช้กับแดชบอร์ด) ⇒ เพิ่ม action ใหม่ต้องเติมทั้งคู่
  //    ไม่งั้นหน้าจอใดหน้าจอหนึ่งจะโชว์ชื่อ action ดิบ ๆ ภาษาอังกฤษ
  RETIRE_ANNOUNCEMENT: 'ปลดระวางประกาศ',
  UNRETIRE_ANNOUNCEMENT: 'นำประกาศกลับมาใช้',
  CREATE_ACADEMIC_TERM: 'สร้างภาคเรียน',
  UPDATE_ACADEMIC_TERM: 'แก้ไขภาคเรียน',
  DELETE_ACADEMIC_TERM: 'ลบภาคเรียน',
  RESTORE_ACADEMIC_TERM: 'กู้คืนภาคเรียน',
  SET_CURRENT_TERM: 'ตั้งภาคปัจจุบัน',
  // E1 — ข้อเสนอจากผู้ใช้ (บอร์ดชนิด 'suggestion')
  CREATE_SUGGESTION: 'สร้างข้อเสนอแนะ',
  // A8 — ค่าตั้งระดับโรงเรียน (app_settings)
  UPDATE_QUIET_HOURS: 'ตั้งช่วงเวลาไม่ส่งแจ้งเตือน',
  // D1 — ระบบกิจกรรม (ตาราง events + event_registrations)
  CREATE_EVENT: 'สร้างกิจกรรม',
  UPDATE_EVENT: 'แก้ไขกิจกรรม',
  PUBLISH_EVENT: 'เผยแพร่กิจกรรม',
  CANCEL_EVENT: 'ยกเลิกกิจกรรม',
  DELETE_EVENT: 'ลบกิจกรรม',
  RESTORE_EVENT: 'กู้คืนกิจกรรม',
  REGISTER_EVENT: 'ลงทะเบียนกิจกรรม',
  UNREGISTER_EVENT: 'ถอนการลงทะเบียนกิจกรรม',
  // ⚠️ หนี้ที่มีอยู่ก่อนรอบนี้: action ของ PIRI Boards ตัวอื่น (SUBMIT_VOTE · ADD_COMMENT ·
  //    APPROVE_TO_PUBLIC · HIDE_BOARD · …) ยังไม่มีป้ายทั้งสอง map ⇒ หน้าจอจะโชว์ชื่อดิบ
  //    ไม่ใช่บั๊กที่รอบนี้ก่อ และไม่แก้ในรอบนี้ (นอกขอบเขต E1 — บันทึกไว้ใน PR)
};

function actionLabel(action: string): string {
  return ACTION_LABELS[action] ?? action;
}

const STATUS_BADGE: Record<string, string> = {
  success: 'bg-ok-tint text-ok-strong',
  error: 'bg-brand/10 text-brand',
  partial: 'bg-stone-100 text-stone-600',
};

// ===== ข้อมูล + การโหลด =====
const items = ref<AuditLogEntry[]>([]);
const total = ref(0);
const page = ref(1);
const pageSize = 20;
const isLoading = ref(true);
const error = ref('');

// ===== ตัวกรอง =====
const fAction = ref('');
const fStatus = ref('');
const fEntityType = ref('');
const fQ = ref('');
const fDateFrom = ref('');
const fDateTo = ref('');
let qTimer: ReturnType<typeof setTimeout> | null = null;

const pages = computed(() => Math.max(1, Math.ceil(total.value / pageSize)));

async function load() {
  isLoading.value = true;
  error.value = '';
  try {
    const res = await listAuditLogs({
      action: fAction.value || undefined,
      status: fStatus.value || undefined,
      entity_type: fEntityType.value || undefined,
      q: fQ.value || undefined,
      date_from: fDateFrom.value || undefined,
      date_to: fDateTo.value || undefined,
      limit: pageSize,
      offset: (page.value - 1) * pageSize,
    });
    items.value = res.items;
    total.value = res.total;
  } catch (e) {
    const msg = e instanceof Error ? e.message : 'เกิดข้อผิดพลาด';
    error.value = msg;
    Swal.fire({ icon: 'error', title: 'โหลดบันทึกการใช้งานไม่สำเร็จ', text: msg });
  } finally {
    isLoading.value = false;
  }
}

function resetAndLoad() {
  page.value = 1;
  load();
}

// เปลี่ยนฟิลเตอร์ → โหลดหน้า 1 (q เดบานซ์ 300ms กันพิมพ์เร็ว)
watch([fAction, fStatus, fEntityType, fDateFrom, fDateTo], resetAndLoad);
watch(fQ, () => {
  if (qTimer) clearTimeout(qTimer);
  qTimer = setTimeout(resetAndLoad, 300);
});

onMounted(load);

// ===== การแสดงผล =====
// 🕐 `fmtDateTimeSec` มาจาก `@/datetime` (R5.5) — **ตัวเดียวในระบบที่โชว์วินาที**
//    เพราะที่นี่ผู้ดูแลต้องเรียงลำดับเหตุการณ์ที่เกิดในนาทีเดียวกัน (ดูคำเตือนใน `datetime.ts`)

const expanded = ref<Set<string>>(new Set());

function toggleExpand(id: string) {
  const next = new Set(expanded.value);
  if (next.has(id)) next.delete(id);
  else next.add(id);
  expanded.value = next;
}

/**
 * ค่า sentinel จาก backend = "ไม่มีค่า" — audit_logs บันทึกครบทุกคอลัมน์แล้ว (ไม่เป็น NULL)
 * ความหมาย: '-' = ไม่ทราบ/ไม่มีค่า, '{}' = ไม่มีการเปลี่ยนแปลงข้อมูล
 * (ดู UNKNOWN / EMPTY_JSON ใน backend/core/logger.py)
 */
function isBlank(v: unknown): boolean {
  return v === null || v === undefined || v === '' || v === '-';
}

/** payload ว่าง = {} (ไม่ใช่ null แล้ว) → ถือว่า "ไม่มีรายละเอียดให้กาง" */
function isEmptyPayload(v: Record<string, unknown> | string | null): boolean {
  if (v === null || v === undefined || v === '' || v === '-') return true; // เช็คตรง ๆ ให้ TS narrow type
  if (typeof v === 'string') {
    const s = v.trim();
    return s === '' || s === '-' || s === '{}' || s === 'null';
  }
  return Object.keys(v).length === 0;
}

function hasPayload(e: AuditLogEntry): boolean {
  return !isEmptyPayload(e.new_values) || !isEmptyPayload(e.old_values) || !isBlank(e.error_detail);
}

function fmtPayload(v: Record<string, unknown> | string | null): string {
  if (isEmptyPayload(v)) return '-';
  try {
    return typeof v === 'string' ? v : JSON.stringify(v, null, 2);
  } catch {
    return String(v);
  }
}

function statusBadge(s: string): string {
  return STATUS_BADGE[s] ?? 'bg-stone-100 text-stone-600';
}

/**
 * ชื่อห้องที่ผู้กระทำสังกัด ณ ตอนเกิดเหตุ (audit_logs เก็บ room_id ไว้ ไม่มี FK)
 * - มีชื่อห้อง → โชว์ชื่อ (rooms ยังอยู่ แม้ถูกลบแบบ soft delete)
 * - ไม่มีชื่อแต่มี id → โชว์ #id ไว้ตามรอยต่อได้
 * - room_id = -1 → ไม่ระบุห้อง
 */
function fmtRoom(e: AuditLogEntry): string {
  if (!isBlank(e.room_name)) return e.room_name as string;
  if (e.room_id !== null && e.room_id !== undefined && e.room_id > 0) return `#${e.room_id}`;
  return '-';
}

/** มีห้องจริงหรือไม่ — ใช้ตัดสินสี (sentinel '-' ต้องจางกว่า) */
function hasRoom(e: AuditLogEntry): boolean {
  return !isBlank(e.room_name) || (e.room_id !== null && e.room_id !== undefined && e.room_id > 0);
}

const hasData = computed(() => items.value.length > 0);

const filterCls = 'w-full rounded-lg border border-stone-300 bg-white px-3 py-2 text-sm transition';
</script>

<template>
  <div>
    <!-- 🔴 ไม่มี <h1>/eyebrow ที่นี่ — `AppHeader` แสดงชื่อหน้าจาก `routeTitles` เป็น <h1> ให้แล้ว (R0.3) -->
    <!-- คำอธิบาย + ปุ่มส่งออก -->
    <div class="flex flex-wrap items-center justify-between gap-3 mb-5">
      <p class="text-xs text-stone-500">ประวัติทุกการกระทำในระบบ (เข้าสู่ระบบ / เพิ่ม / ดึงข้อมูล / แก้ไข / ลบ)</p>
      <button
        type="button"
        @click="load"
        :disabled="isLoading"
        title="รีเฟรช"
        class="flex h-11 w-11 items-center justify-center rounded-xl border border-stone-200 bg-white text-stone-500 transition hover:border-brand/30 hover:bg-brand/5 hover:text-brand disabled:opacity-50"
      >
        <i class="bi bi-arrow-clockwise" :class="{ 'animate-spin': isLoading }"></i>
      </button>
    </div>

    <!-- ตัวกรอง -->
    <div class="mb-4 rounded-2xl border border-stone-200 bg-white p-4">
      <div class="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-6">
        <div>
          <label class="mb-1 block text-xs font-semibold text-stone-500">Action</label>
          <input
            v-model="fAction"
            type="text"
            placeholder="เช่น login, CREATE_ISSUE"
            :class="filterCls"
          />
        </div>
        <div>
          <label class="mb-1 block text-xs font-semibold text-stone-500">สถานะ</label>
          <select v-model="fStatus" :class="filterCls">
            <option value="">ทั้งหมด</option>
            <option value="success">สำเร็จ</option>
            <option value="error">ผิดพลาด</option>
            <option value="partial">บางส่วน</option>
          </select>
        </div>
        <div>
          <label class="mb-1 block text-xs font-semibold text-stone-500">ชนิดข้อมูล</label>
          <input
            v-model="fEntityType"
            type="text"
            placeholder="เช่น issue, user"
            :class="filterCls"
          />
        </div>
        <div>
          <label class="mb-1 block text-xs font-semibold text-stone-500">ค้นหา (ผู้ใช้/error)</label>
          <input v-model="fQ" type="text" placeholder="ชื่อผู้ใช้ / ข้อความ" :class="filterCls" />
        </div>
        <div>
          <label class="mb-1 block text-xs font-semibold text-stone-500">จากวันที่</label>
          <input v-model="fDateFrom" type="date" :class="filterCls" />
        </div>
        <div>
          <label class="mb-1 block text-xs font-semibold text-stone-500">ถึงวันที่</label>
          <input v-model="fDateTo" type="date" :class="filterCls" />
        </div>
      </div>
    </div>

    <!-- Loading skeleton -->
    <div v-if="isLoading && !hasData" class="overflow-hidden rounded-2xl border border-stone-200 bg-white" aria-busy="true">
      <div class="space-y-3 p-4">
        <div v-for="i in 6" :key="i" class="flex items-center gap-3">
          <div class="h-8 w-8 animate-pulse rounded-lg bg-stone-100"></div>
          <div class="flex-1 space-y-1.5">
            <div class="h-3 w-1/3 animate-pulse rounded bg-stone-100"></div>
            <div class="h-3 w-1/2 animate-pulse rounded bg-stone-100"></div>
          </div>
        </div>
      </div>
    </div>

    <!-- Error -->
    <div v-else-if="error && !hasData" class="rounded-2xl border-2 border-dashed border-stone-200 bg-white p-12 text-center">
      <div class="mb-3 text-3xl text-stone-300"><i class="bi bi-exclamation-triangle"></i></div>
      <h2 class="mb-1 text-lg font-bold text-stone-800">โหลดข้อมูลไม่สำเร็จ</h2>
      <p class="mx-auto mb-5 max-w-md text-sm text-stone-500">{{ error }}</p>
      <button
        type="button"
        @click="load"
        class="inline-flex items-center gap-1.5 rounded-xl bg-brand px-5 min-h-11 py-2.5 text-sm font-medium text-white transition hover:bg-brand-strong"
      >
        <i class="bi bi-arrow-clockwise mr-1"></i> ลองใหม่
      </button>
    </div>

    <!-- Empty -->
    <div v-else-if="!isLoading && !hasData" class="rounded-2xl border-2 border-dashed border-stone-200 bg-white p-12 text-center">
      <div class="mb-3 text-3xl text-stone-300"><i class="bi bi-inbox"></i></div>
      <p class="text-sm text-stone-500">ยังไม่มีบันทึกการใช้งานตามเงื่อนไขนี้</p>
    </div>

    <!-- ตาราง -->
    <div v-else class="overflow-hidden rounded-2xl border border-stone-200 bg-white">
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead class="bg-stone-50">
            <tr class="text-left text-[11px] text-stone-500">
              <th class="px-4 py-3 font-semibold">เวลา</th>
              <th class="px-4 py-3 font-semibold">ผู้ใช้</th>
              <th class="px-4 py-3 font-semibold">ห้อง</th>
              <th class="px-4 py-3 font-semibold">การกระทำ</th>
              <th class="px-4 py-3 font-semibold">ข้อมูล</th>
              <th class="px-4 py-3 font-semibold">สถานะ</th>
              <th class="px-4 py-3 font-semibold">IP</th>
              <th class="px-4 py-3 font-semibold"></th>
            </tr>
          </thead>
          <tbody class="divide-y divide-stone-100">
            <template v-for="e in items" :key="e.id">
              <tr class="transition-colors hover:bg-stone-50">
                <td class="whitespace-nowrap px-4 py-2.5 text-stone-500 tabular-nums">{{ fmtDateTimeSec(e.created_at) }}</td>
                <td class="px-4 py-2.5">
                  <span class="font-medium text-stone-700">{{ e.actor_identifier }}</span>
                  <span v-if="!isBlank(e.ip_address)" class="block text-[11px] text-ink-3 tabular-nums">{{ e.ip_address }}</span>
                </td>
                <td class="whitespace-nowrap px-4 py-2.5">
                  <span v-if="hasRoom(e)" class="text-stone-600">{{ fmtRoom(e) }}</span>
                  <span v-else class="text-stone-300">-</span>
                </td>
                <td class="px-4 py-2.5">
                  <span class="inline-flex items-center gap-1.5">
                    <span class="font-medium text-stone-800">{{ actionLabel(e.action) }}</span>
                    <span class="font-mono text-[11px] text-ink-3">{{ e.action }}</span>
                  </span>
                  <span v-if="!isBlank(e.endpoint_or_command)" class="block font-mono text-[11px] text-ink-3">{{ e.endpoint_or_command }}</span>
                </td>
                <td class="px-4 py-2.5 text-stone-500">
                  <template v-if="!isBlank(e.entity_type)">
                    <span class="text-ink-3">{{ e.entity_type }}</span>
                    <span v-if="!isBlank(e.entity_id)" class="font-mono text-stone-600">#{{ e.entity_id }}</span>
                  </template>
                  <span v-else class="text-stone-300">-</span>
                </td>
                <td class="px-4 py-2.5">
                  <span class="rounded-full px-2 py-0.5 text-[11px] font-medium" :class="statusBadge(e.status)">
                    {{ e.status }}
                  </span>
                </td>
                <td class="px-4 py-2.5 font-mono text-xs text-stone-500">{{ isBlank(e.ip_address) ? '-' : e.ip_address }}</td>
                <td class="px-4 py-2.5 text-right">
                  <button
                    v-if="hasPayload(e)"
                    type="button"
                    @click="toggleExpand(e.id)"
                    class="inline-flex h-11 w-11 items-center justify-center rounded-lg text-ink-3 transition hover:bg-brand/5 hover:text-brand"
                    :title="expanded.has(e.id) ? 'ย่อรายละเอียด' : 'ดูรายละเอียด'"
                  >
                    <i class="bi" :class="expanded.has(e.id) ? 'bi-chevron-up' : 'bi-chevron-down'"></i>
                  </button>
                </td>
              </tr>
              <!-- รายละเอียดเก่า/ใหม่ (expand) -->
              <tr v-if="expanded.has(e.id)" class="bg-stone-50/60">
                <td colspan="8" class="px-4 py-3">
                  <div class="grid gap-3 lg:grid-cols-2">
                    <div>
                      <p class="mb-1 text-xs font-semibold text-stone-500">ค่าเดิม (old_values)</p>
                      <pre class="overflow-x-auto rounded-lg border border-stone-200 bg-white p-2.5 text-[11px] text-stone-600">{{ fmtPayload(e.old_values) }}</pre>
                    </div>
                    <div>
                      <p class="mb-1 text-xs font-semibold text-stone-500">ค่าใหม่ (new_values)</p>
                      <pre class="overflow-x-auto rounded-lg border border-stone-200 bg-white p-2.5 text-[11px] text-stone-600">{{ fmtPayload(e.new_values) }}</pre>
                    </div>
                    <div v-if="!isBlank(e.error_detail)" class="lg:col-span-2">
                      <p class="mb-1 text-xs font-semibold text-brand">ข้อผิดพลาด</p>
                      <pre class="overflow-x-auto rounded-lg border border-brand/15 bg-brand/5 p-2.5 text-[11px] text-brand">{{ e.error_detail }}</pre>
                    </div>
                  </div>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>

      <div class="flex items-center justify-between px-4 py-3 text-xs text-ink-3">
        <span>แสดง {{ items.length }} จาก {{ total }} รายการ</span>
        <span v-if="pages > 1">หน้า {{ page }} / {{ pages }}</span>
      </div>
    </div>

    <PaginationBar :total="total" :page="page" :page-size="pageSize" :loading="isLoading" @page-change="page = $event; load()" />
  </div>
</template>
