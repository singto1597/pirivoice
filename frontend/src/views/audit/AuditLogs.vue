<script setup lang="ts">
/**
 * 🔍 บันทึกการใช้งาน — หน้าดูสำหรับผู้ดูแล (VIEW_AUDIT_LOG)
 *
 * ═══════════════════════════════════════════════════════════════════════════
 * หน้านี้ถืออะไรไว้
 * ═══════════════════════════════════════════════════════════════════════════
 *  · รายการ "ใครทำอะไร เมื่อไร จากที่ไหน" จากตาราง `audit_logs`
 *  · ตัวกรอง: ช่วงวันที่ (เวลาไทย) · บริการ · การกระทำ · สถานะ · ชนิดข้อมูล · คำค้น
 *  · เลื่อนหน้าแบบ **keyset** — ใช้ `next_cursor` จาก backend ตรง ๆ ห้ามคำนวณ offset
 *    (ตารางนี้มีแถวใหม่แทรกหัวตลอดเวลา ⇒ offset จะทำให้เห็นซ้ำ/ข้าม)
 *
 * ═══════════════════════════════════════════════════════════════════════════
 * กฎที่ฝังไว้
 * ═══════════════════════════════════════════════════════════════════════════
 *  1. **เปลี่ยนตัวกรอง = เริ่มจากหน้าแรก** (ทิ้ง cursor เสมอ) ไม่งั้นจะได้หน้า 2
 *     ของชุดใหม่ที่ไม่มีหัวต่อ ⇒ `resetAndLoad()` ทุกครั้งที่ตัวกรองเปลี่ยน
 *  2. **คำขอที่เก่ากว่าต้องถูกทิ้ง** — ผู้ใช้เปลี่ยน dropdown รัว ๆ ได้ ใช้ `loadSeq`
 *     กัน response เก่ามาทับชุดใหม่ (ไม่งั้นเห็นข้อมูลของตัวกรองที่ไม่ได้เลือกอยู่)
 *  3. **ข้อความว่างสองแบบ**: ยังไม่มีบันทึกเลย กับ "กรองแล้วไม่เจอ" — ทางออกคนละทาง
 *  4. ค่าที่ละเอียด (IP / User-Agent / old–new values) ซ่อนใต้ `<details>` —
 *     เป็นข้อมูลสำหรับสืบเหตุ ไม่ใช่อ่านประจำวัน
 *  5. 🕐 `fmtDateTimeSec` เป็นตัวเดียวในระบบที่โชว์วินาที (ดูคำเตือนใน `datetime.ts`)
 *     ที่นี่จำเป็น เพราะผู้ดูแลต้องเรียงเหตุการณ์ที่เกิดในนาทีเดียวกัน
 */
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue';
import AppButton from '@/components/ui/AppButton.vue';
import AppEmptyState from '@/components/ui/AppEmptyState.vue';
import IconButton from '@/components/ui/IconButton.vue';
import { getAuditLogOptions, listAuditLogs } from '@/services/audit';
import type { AuditLogItem, AuditLogOptions } from '@/types/audit';
import { fmtDateTimeSec } from '@/datetime';

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

const STATUS_LABELS: Record<string, string> = {
  success: 'สำเร็จ',
  error: 'ผิดพลาด',
  partial: 'บางส่วน',
};

const STATUS_BADGE: Record<string, string> = {
  success: 'bg-ok-tint text-ok-strong',
  error: 'bg-danger-soft text-danger',
  partial: 'bg-canvas text-ink-2',
};

const actionLabel = (action: string): string => ACTION_LABELS[action] ?? action;
const statusLabel = (status: string): string => STATUS_LABELS[status] ?? status;
const statusBadge = (status: string): string => STATUS_BADGE[status] ?? 'bg-canvas text-ink-2';

const messageOf = (err: unknown): string =>
  err instanceof Error && err.message ? err.message : 'เกิดข้อผิดพลาดจากระบบ';

// ── ตัวกรอง ────────────────────────────────────────────────────────────────
// `date_from`/`date_to` เป็น `YYYY-MM-DD` ตาม `<input type="date">` — backend รับ
// เป็น DATE และตีความเป็นวันตามเวลาไทยที่ฝั่งนั้น (ไม่ต้องแปลง TZ ที่หน้า)
const filters = reactive({
  date_from: '',
  date_to: '',
  service_name: '',
  action: '',
  status: '',
  entity_type: '',
  q: '',
});

const hasActiveFilters = computed(() => Object.values(filters).some((value) => value !== ''));

const query = (cursor?: string) => ({
  date_from: filters.date_from || undefined,
  date_to: filters.date_to || undefined,
  service_name: filters.service_name || undefined,
  action: filters.action || undefined,
  status: filters.status || undefined,
  entity_type: filters.entity_type || undefined,
  q: filters.q.trim() || undefined,
  cursor: cursor || undefined,
});

// ── รายการ + การเลื่อนหน้า ────────────────────────────────────────────────
const items = ref<AuditLogItem[]>([]);
const nextCursor = ref<string | null>(null);
const hasMore = ref(false);
const isLoading = ref(true);
const isLoadingMore = ref(false);
const loadError = ref('');
const loadMoreError = ref('');
const options = ref<AuditLogOptions>({
  service_names: [],
  actions: [],
  statuses: [],
  entity_types: [],
});

/** ลำดับคำขอ — response ของคำขอที่เก่ากว่าต้องถูกทิ้ง (ผู้ใช้เปลี่ยนตัวกรองรัว ๆ ได้) */
let loadSeq = 0;
let qTimer: ReturnType<typeof setTimeout> | null = null;

/** โหลดหน้าแรก (ทิ้งรายการเดิม) — เรียกทุกครั้งที่ตัวกรองเปลี่ยน */
async function resetAndLoad() {
  const seq = ++loadSeq;
  isLoading.value = true;
  loadError.value = '';
  loadMoreError.value = '';
  try {
    const res = await listAuditLogs(query());
    if (seq !== loadSeq) return; // มีคำขอใหม่กว่าออกไปแล้ว
    items.value = res.items;
    nextCursor.value = res.next_cursor;
    hasMore.value = res.has_more;
  } catch (err) {
    if (seq !== loadSeq) return;
    items.value = [];
    nextCursor.value = null;
    hasMore.value = false;
    loadError.value = messageOf(err);
  } finally {
    if (seq === loadSeq) isLoading.value = false;
  }
}

/** ต่อท้ายรายการด้วย `next_cursor` ของ backend — ห้ามคำนวณ offset เอง */
async function loadMore() {
  const cursor = nextCursor.value;
  if (!cursor || isLoadingMore.value || isLoading.value) return;

  const seq = loadSeq;
  isLoadingMore.value = true;
  loadMoreError.value = '';
  try {
    const res = await listAuditLogs(query(cursor));
    if (seq !== loadSeq) return; // ตัวกรองเปลี่ยนระหว่างโหลด — ชุดนี้ไม่ใช้แล้ว
    items.value = [...items.value, ...res.items];
    nextCursor.value = res.next_cursor;
    hasMore.value = res.has_more;
  } catch (err) {
    if (seq !== loadSeq) return;
    loadMoreError.value = messageOf(err);
  } finally {
    if (seq === loadSeq) isLoadingMore.value = false;
  }
}

/** ล้างตัวกรองทั้งหมด — watcher เป็นผู้สั่งโหลดใหม่ (ไม่เรียกซ้ำ เพื่อไม่ยิงสองคำขอ) */
function clearFilters() {
  filters.date_from = '';
  filters.date_to = '';
  filters.service_name = '';
  filters.action = '';
  filters.status = '';
  filters.entity_type = '';
  filters.q = '';
}

/**
 * หน่วงการโหลดใหม่ผ่าน timer ตัวเดียว
 *
 * ⚠️ ต้องตัวเดียว: `clearFilters()` แตะทุกฟิลด์พร้อมกัน ⇒ watcher สองตัวจะยิง
 *   `resetAndLoad()` สองครั้งซ้อน (คำขอที่สองทำให้คำขอแรกถูกทิ้งอยู่ดี — เสียฟรี)
 *   · `delay = 0` สำหรับ dropdown/วันที่ (ต้องตอบสนองทันที) · 300ms สำหรับคำค้น
 */
function scheduleReload(delay: number) {
  if (qTimer) clearTimeout(qTimer);
  qTimer = setTimeout(() => void resetAndLoad(), delay);
}

watch(
  [
    () => filters.date_from,
    () => filters.date_to,
    () => filters.service_name,
    () => filters.action,
    () => filters.status,
    () => filters.entity_type,
  ],
  () => scheduleReload(0),
);

watch(
  () => filters.q,
  () => scheduleReload(300),
);

onBeforeUnmount(() => {
  if (qTimer) clearTimeout(qTimer);
});

onMounted(() => {
  // ตัวเลือกของ dropdown มาจากข้อมูลจริง — ล้มเหลวแล้วไม่ควรทำให้ทั้งหน้าล้มตาม
  void getAuditLogOptions()
    .then((result) => {
      options.value = result;
    })
    .catch(() => {
      // ปล่อยว่าง — ผู้ใช้ยังกรองด้วยคำค้น/วันที่ได้
    });
  void resetAndLoad();
});

// ── การแสดงผลรายแถว ────────────────────────────────────────────────────────
/** ป้ายชื่อผู้ทำ: ใช้ชื่อจริงถ้ามี ไม่งั้นแสดงตัวระบุดิบที่บันทึกไว้ */
const actorLabel = (item: AuditLogItem): string => item.actor_name || item.actor_identifier;

/** บรรทัดรอง: identifier ดิบ + ฝั่งที่ยิงมา (web/bot) — โชว์เฉพาะเมื่อมีชื่อจริงให้เทียบ */
const actorDetail = (item: AuditLogItem): string | null =>
  item.actor_name
    ? [item.actor_identifier, item.client_source].filter((part) => !isBlank(part)).join(' · ')
    : null;

/**
 * ค่า sentinel จาก backend = "ไม่มีค่า" — audit_logs บันทึกครบทุกคอลัมน์แล้ว (ไม่เป็น NULL)
 * ความหมาย: '-' = ไม่ทราบ/ไม่มีค่า, '{}' = ไม่มีการเปลี่ยนแปลงข้อมูล
 * (ดู UNKNOWN / EMPTY_JSON ใน backend/core/logger.py)
 */
function isBlank(v: unknown): v is null | undefined | '' {
  return v === null || v === undefined || v === '' || v === '-';
}

/** payload ว่าง = {} (ไม่ใช่ null) → ถือว่า "ไม่มีรายละเอียดให้กาง" */
function isEmptyPayload(v: unknown): boolean {
  if (v === null || v === undefined || v === '' || v === '-') return true;
  if (typeof v === 'string') {
    const s = v.trim();
    return s === '' || s === '-' || s === '{}' || s === 'null';
  }
  if (Array.isArray(v)) return v.length === 0;
  if (typeof v === 'object') return Object.keys(v as Record<string, unknown>).length === 0;
  return false;
}

/** แสดง JSON แบบอ่านได้ แต่ตัดความยาวไม่ให้ท่วมการ์ด */
function prettyJson(value: unknown): string {
  if (isEmptyPayload(value)) return '—';
  try {
    const text = typeof value === 'string' ? value : JSON.stringify(value, null, 2);
    return text.length > 2000 ? `${text.slice(0, 2000)}\n… (ตัดเพื่อแสดงผล)` : text;
  } catch {
    return String(value);
  }
}

/**
 * ชื่อห้องที่ผู้กระทำสังกัด ณ ตอนเกิดเหตุ (audit_logs เก็บ room_id ไว้ ไม่มี FK)
 * - มีชื่อห้อง → โชว์ชื่อ (rooms ยังอยู่ แม้ถูกลบแบบ soft delete)
 * - ไม่มีชื่อแต่มี id → โชว์ #id ไว้ตามรอยต่อได้
 * - room_id = -1 → ไม่ระบุห้อง
 */
function fmtRoom(item: AuditLogItem): string | null {
  if (!isBlank(item.room_name)) return item.room_name;
  if (item.room_id !== null && item.room_id > 0) return `#${item.room_id}`;
  return null;
}

const filterCls =
  'mt-1 w-full rounded-control border border-line bg-surface px-3 py-2 text-sm font-normal text-ink-1';
</script>

<template>
  <div>
    <!-- 🔴 ไม่มี <h1>/eyebrow ที่นี่ — `AppHeader` แสดงชื่อหน้าจาก `routeTitles` เป็น <h1> ให้แล้ว -->
    <div class="mb-4 flex flex-wrap items-center justify-between gap-3">
      <p class="text-xs text-ink-2">
        ประวัติทุกการกระทำในระบบ (เข้าสู่ระบบ / เพิ่ม / ดึงข้อมูล / แก้ไข / ลบ)
      </p>
      <IconButton
        icon="bi-arrow-clockwise"
        label="รีเฟรชบันทึกการใช้งาน"
        :disabled="isLoading"
        @click="resetAndLoad"
      />
    </div>

    <!-- ── ตัวกรอง ────────────────────────────────────────────────────────── -->
    <section class="rounded-card border border-line bg-surface p-4" aria-label="ตัวกรอง">
      <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <label class="block text-xs font-bold text-ink-2">
          ตั้งแต่
          <input v-model="filters.date_from" type="date" :class="filterCls" />
        </label>
        <label class="block text-xs font-bold text-ink-2">
          ถึง
          <input v-model="filters.date_to" type="date" :class="filterCls" />
        </label>
        <label class="block text-xs font-bold text-ink-2">
          คำค้น
          <input
            v-model="filters.q"
            type="search"
            placeholder="ผู้ทำ / endpoint / รหัส entity / ข้อผิดพลาด"
            :class="filterCls"
          />
        </label>
        <label class="block text-xs font-bold text-ink-2">
          บริการ
          <select v-model="filters.service_name" :class="filterCls">
            <option value="">ทั้งหมด</option>
            <option v-for="name in options.service_names" :key="name" :value="name">
              {{ name }}
            </option>
          </select>
        </label>
        <label class="block text-xs font-bold text-ink-2">
          การกระทำ
          <select v-model="filters.action" :class="filterCls">
            <option value="">ทั้งหมด</option>
            <option v-for="name in options.actions" :key="name" :value="name">
              {{ actionLabel(name) }} ({{ name }})
            </option>
          </select>
        </label>
        <label class="block text-xs font-bold text-ink-2">
          สถานะ
          <select v-model="filters.status" :class="filterCls">
            <option value="">ทั้งหมด</option>
            <option v-for="name in options.statuses" :key="name" :value="name">
              {{ statusLabel(name) }}
            </option>
          </select>
        </label>
        <label class="block text-xs font-bold text-ink-2">
          ชนิดข้อมูล
          <select v-model="filters.entity_type" :class="filterCls">
            <option value="">ทั้งหมด</option>
            <option v-for="name in options.entity_types" :key="name" :value="name">
              {{ name }}
            </option>
          </select>
        </label>
      </div>
      <div v-if="hasActiveFilters" class="mt-3">
        <AppButton variant="text" size="sm" @click="clearFilters">ล้างตัวกรอง</AppButton>
      </div>
    </section>

    <!-- ── สถานะการโหลด ───────────────────────────────────────────────────── -->
    <div
      v-if="isLoading && items.length === 0"
      class="mt-4 space-y-2.5"
      aria-busy="true"
      aria-label="กำลังโหลดบันทึกการใช้งาน"
    >
      <div
        v-for="i in 4"
        :key="i"
        class="rounded-card border border-line bg-surface p-4"
      >
        <div class="h-3 w-1/3 animate-pulse rounded bg-canvas"></div>
        <div class="mt-2 h-3 w-1/2 animate-pulse rounded bg-canvas"></div>
      </div>
    </div>

    <div
      v-else-if="loadError"
      class="mt-4 rounded-card border border-line bg-surface py-4"
    >
      <AppEmptyState
        icon="bi-exclamation-triangle"
        title="โหลดบันทึกการใช้งานไม่สำเร็จ"
        :description="loadError"
      >
        <AppButton variant="secondary" @click="resetAndLoad">ลองใหม่</AppButton>
      </AppEmptyState>
    </div>

    <!-- ยังไม่มีบันทึกเลย กับ "กรองแล้วไม่เจอ" เป็นคนละเรื่อง -->
    <div
      v-else-if="items.length === 0 && hasActiveFilters"
      class="mt-4 rounded-card border border-line bg-surface py-4"
    >
      <AppEmptyState
        icon="bi-funnel"
        title="ไม่พบบันทึกที่ตรงกับตัวกรอง"
        description="ลองขยายช่วงวันที่ หรือล้างตัวกรอง"
      >
        <AppButton variant="secondary" @click="clearFilters">ล้างตัวกรอง</AppButton>
      </AppEmptyState>
    </div>

    <div
      v-else-if="items.length === 0"
      class="mt-4 rounded-card border border-line bg-surface py-4"
    >
      <AppEmptyState
        icon="bi-journal-text"
        title="ยังไม่มีบันทึกการใช้งาน"
        description="บันทึกจะเริ่มมีเมื่อมีการเข้าสู่ระบบหรือแก้ไขข้อมูลผ่านระบบ"
      />
    </div>

    <!-- ── รายการ ─────────────────────────────────────────────────────────── -->
    <template v-else>
      <ul class="mt-4 space-y-2.5">
        <li v-for="item in items" :key="item.id" class="rounded-card border border-line bg-surface p-4">
          <div class="flex flex-wrap items-start justify-between gap-2">
            <div class="min-w-0">
              <p class="flex flex-wrap items-center gap-1.5 text-sm font-bold text-ink-1">
                <span class="break-words">{{ actorLabel(item) }}</span>
                <span
                  class="rounded-full bg-canvas px-2 py-0.5 text-[11px] font-semibold text-ink-2"
                  :title="item.action"
                >
                  {{ actionLabel(item.action) }}
                </span>
                <span
                  v-if="!isBlank(item.status) && item.status !== 'success'"
                  class="rounded-full px-2 py-0.5 text-[11px] font-semibold"
                  :class="statusBadge(item.status)"
                >
                  {{ statusLabel(item.status) }}
                </span>
              </p>
              <p class="mt-0.5 break-words text-xs text-ink-3">
                {{ item.service_name }}
                <template v-if="!isBlank(item.entity_type)">
                  · {{ item.entity_type
                  }}<template v-if="!isBlank(item.entity_id)"> #{{ item.entity_id }}</template>
                </template>
                <template v-if="!isBlank(item.endpoint_or_command)">
                  · {{ item.endpoint_or_command }}
                </template>
              </p>
            </div>
            <time class="shrink-0 text-xs text-ink-3 tabular-nums" :datetime="item.created_at">
              {{ fmtDateTimeSec(item.created_at) }}
            </time>
          </div>

          <p v-if="actorDetail(item)" class="mt-1 break-words text-xs text-ink-3">
            {{ actorDetail(item) }}
          </p>

          <p
            v-if="!isBlank(item.error_detail)"
            class="mt-2 rounded-control bg-danger-soft px-3 py-2 text-xs text-danger"
          >
            {{ item.error_detail }}
          </p>

          <!-- รายละเอียดเชิงสืบเหตุ — ซ่อนไว้เป็นค่าเริ่มต้น -->
          <details class="mt-2">
            <summary class="cursor-pointer text-xs font-bold text-brand">รายละเอียด</summary>
            <dl class="mt-2 space-y-1 text-xs text-ink-2">
              <div v-if="!isBlank(item.ip_address)" class="flex gap-2">
                <dt class="w-24 shrink-0 text-ink-3">IP</dt>
                <dd class="break-all">{{ item.ip_address }}</dd>
              </div>
              <div v-if="!isBlank(item.user_agent)" class="flex gap-2">
                <dt class="w-24 shrink-0 text-ink-3">อุปกรณ์</dt>
                <dd class="break-all">{{ item.user_agent }}</dd>
              </div>
              <div v-if="fmtRoom(item)" class="flex gap-2">
                <dt class="w-24 shrink-0 text-ink-3">ห้อง</dt>
                <dd>{{ fmtRoom(item) }}</dd>
              </div>
              <div v-if="item.execution_time_ms !== null" class="flex gap-2">
                <dt class="w-24 shrink-0 text-ink-3">เวลาทำงาน</dt>
                <dd class="tabular-nums">{{ item.execution_time_ms }} ms</dd>
              </div>
              <div class="flex gap-2">
                <dt class="w-24 shrink-0 text-ink-3">รหัสการทำ</dt>
                <dd class="font-mono break-all">{{ item.action }}</dd>
              </div>
              <div v-if="!isBlank(item.trace_id)" class="flex gap-2">
                <dt class="w-24 shrink-0 text-ink-3">Trace ID</dt>
                <dd class="font-mono break-all">{{ item.trace_id }}</dd>
              </div>
            </dl>
            <div class="mt-2 grid gap-2 sm:grid-cols-2">
              <div v-if="!isEmptyPayload(item.old_values)">
                <p class="text-xs font-bold text-ink-3">ก่อนแก้</p>
                <pre
                  class="mt-1 max-h-56 overflow-auto rounded-control bg-canvas p-2 text-xs leading-relaxed"
                  v-text="prettyJson(item.old_values)"
                ></pre>
              </div>
              <div v-if="!isEmptyPayload(item.new_values)">
                <p class="text-xs font-bold text-ink-3">หลังแก้</p>
                <pre
                  class="mt-1 max-h-56 overflow-auto rounded-control bg-canvas p-2 text-xs leading-relaxed"
                  v-text="prettyJson(item.new_values)"
                ></pre>
              </div>
            </div>
          </details>
        </li>
      </ul>

      <div v-if="loadMoreError" class="mt-3 rounded-card border border-line bg-surface py-4">
        <AppEmptyState
          icon="bi-exclamation-triangle"
          title="โหลดหน้าถัดไปไม่สำเร็จ"
          :description="loadMoreError"
        >
          <AppButton variant="secondary" @click="loadMore">ลองใหม่</AppButton>
        </AppEmptyState>
      </div>

      <div v-if="hasMore" class="mt-4 flex justify-center">
        <AppButton variant="secondary" :loading="isLoadingMore" @click="loadMore">
          โหลดเพิ่ม
        </AppButton>
      </div>
      <p v-else class="mt-4 text-center text-xs text-ink-3">แสดงครบทั้งหมดแล้ว</p>
    </template>
  </div>
</template>
