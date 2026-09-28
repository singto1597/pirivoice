<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import Swal from 'sweetalert2'
import { listStudents, listRooms, addStudent, updateStudent } from '@/services/student'
import { RESPONSIBLE_ROLES, CATEGORY_OPTIONS } from '@/types/issue'
import type { Student, Room } from '@/types/student'
import { useAuthStore } from '@/stores/auth'

// 🧑‍💼 หน้า User Management — จัดการกลุ่ม สภานักเรียน / ผู้ช่วยหัวหน้าระดับ / คณะกรรมการห้อง
// หลักการ: Backend บังคับขอบเขตไว้แล้ว (grade scope + hierarchy rank) — หน้านี้กรอง/แสดงผลให้ใช้ง่าย
// - Default filter = ตำแหน่งเดียวกับคนล็อกอิน (ตาม requirement)
// - "เพิ่มผู้ใช้งาน" สำหรับกรณี import Excel ไม่ครบ / เพิ่มเฉพาะคน

const authStore = useAuthStore()

const ROLE_LABELS: Record<string, string> = {
  student: 'นักเรียน',
  class_president: 'หัวหน้าห้อง',
  vice_academic: 'รองวิชาการ',
  vice_discipline: 'รองวินัย',
  vice_activity: 'รองกิจกรรม',
  vice_reception: 'รองปฏิคม',
  level_president: 'ประธานระดับ',
  level_vice_president: 'ผู้ช่วยหัวหน้าระดับ',
  council_member: 'สภานักเรียน',
  council_president: 'ประธานสภา',
}

// กลุ่มตำแหน่งสำหรับ chip กรอง (อิงพีระมิด hierarchy)
const ROLE_GROUPS: { key: string; label: string; roles: string[] }[] = [
  { key: 'council', label: 'สภานักเรียน', roles: ['council_member', 'council_president'] },
  { key: 'level', label: 'หัวหน้าระดับ', roles: ['level_president', 'level_vice_president'] },
  {
    key: 'class_board',
    label: 'คณะกรรมการห้อง',
    roles: [
      'class_president',
      'vice_academic',
      'vice_discipline',
      'vice_activity',
      'vice_reception',
    ],
  },
  { key: 'student', label: 'นักเรียน', roles: ['student'] },
]

// ทุกตำแหน่งที่ UI "ตั้งให้" ได้ (backend ตรวจ hierarchy อีกชั้น ถ้าตั้งเกินก็ 403)
const ALL_SETTABLE_ROLES = [
  'student',
  'class_president',
  'vice_academic',
  'vice_discipline',
  'vice_activity',
  'vice_reception',
  'level_president',
  'level_vice_president',
  'council_member',
  'council_president',
]

const students = ref<Student[]>([])
const rooms = ref<Room[]>([])
const isLoading = ref(true)
const hasError = ref(false)
const search = ref('')
const groupFilter = ref('all')

const isSchoolWide = computed(() => authStore.isAdmin)
const isLevelActor = computed(() =>
  authStore.roles.some((r) => ['level_president', 'level_vice_president'].includes(r.role || '')),
)

// ตำแหน่งที่คนล็อกอินถืออยู่ (ตัวแรก) → หา chip กลุ่มเริ่มต้น = กลุ่มเดียวกับตำแหน่งนั้น
const ownRole = computed(() => authStore.roles[0]?.role || '')
const ownGroupKey = computed(
  () => ROLE_GROUPS.find((g) => g.roles.includes(ownRole.value))?.key || 'all',
)
groupFilter.value = ownGroupKey.value

// ผู้จัดการระดับชั้น (ประธาน/ผู้ช่วยระดับ หรือครู) → จำกัดตัวเลือกห้องตอนเพิ่มผู้ใช้
const manageGrade = computed(() => {
  for (const r of authStore.roles) {
    if (['level_president', 'level_vice_president'].includes(r.role || '') && r.level)
      return r.level
    if (r.role === 'teacher' && r.staff_level) return r.staff_level
  }
  return null
})

// ตำแหน่งที่ตั้งให้ได้ตามสิทธิ์ของผู้จัดการ (กัน UI เสนอ role ที่ backend จะ 403)
const settableRoles = computed(() => {
  if (isSchoolWide.value) return ALL_SETTABLE_ROLES
  if (isLevelActor.value) {
    // rank 2 → ตั้งได้ถึงระดับ/ห้อง/นักเรียน ไม่รวมสภา (rank 3+)
    return ALL_SETTABLE_ROLES.filter((r) => !['council_member', 'council_president'].includes(r))
  }
  return ALL_SETTABLE_ROLES // ครู: ภายในระดับชั้นของตัวเอง (backend ตรวจ grade)
})

async function load() {
  isLoading.value = true
  hasError.value = false
  try {
    // Backend ตัดกรองขอบเขตมาให้แล้ว (school-wide / เฉพาะระดับชั้น + role ที่ต่ำกว่า/เท่ากัน)
    const [s, r] = await Promise.all([listStudents(), listRooms()])
    students.value = s
    rooms.value = r
  } catch (e) {
    const msg = typeof e === 'string' ? e : e instanceof Error ? e.message : 'โหลดข้อมูลไม่สำเร็จ'
    hasError.value = true
    Swal.fire({ icon: 'error', title: 'โหลดข้อมูลไม่สำเร็จ', text: msg })
  } finally {
    isLoading.value = false
  }
}
onMounted(load)

// นับจำนวนสมาชิกแต่ละกลุ่ม (แสดง badge บน chip)
const groupCounts = computed<Record<string, number>>(() => {
  const counts: Record<string, number> = { council: 0, level: 0, class_board: 0, student: 0 }
  for (const s of students.value) {
    const g = ROLE_GROUPS.find((x) => x.roles.includes(s.class_role))
    if (g) counts[g.key] = (counts[g.key] ?? 0) + 1
  }
  return counts
})

function groupCount(key: string): number {
  return groupCounts.value[key] ?? 0
}

// รายการที่แสดง = ตามกลุ่มที่เลือก + คำค้นหา (กรองฝั่ง client — backend ตัด scope ให้แล้ว)
const visibleStudents = computed(() => {
  let out = students.value
  if (groupFilter.value !== 'all') {
    const g = ROLE_GROUPS.find((x) => x.key === groupFilter.value)
    if (g) out = out.filter((s) => g.roles.includes(s.class_role))
  }
  const t = search.value.trim().toLowerCase()
  if (t) {
    out = out.filter((s) =>
      `${s.first_name || ''} ${s.last_name || ''} ${s.student_id || ''} ${s.nickname || ''}`
        .toLowerCase()
        .includes(t),
    )
  }
  return out
})

function roleLabel(code: string): string {
  return ROLE_LABELS[code] || code
}

// ห้องที่เลือกเพิ่มผู้ใช้ได้: ผู้จัดการระดับชั้นเห็นเฉพาะห้องในระดับตัวเอง
const addableRooms = computed(() => {
  if (!manageGrade.value) return rooms.value
  return rooms.value.filter((r) => r.level === manageGrade.value)
})

function resetForm() {
  return {
    studentId: null as number | null,
    username: '',
    password: '',
    prefix: '',
    first_name: '',
    last_name: '',
    nickname: '',
    room_code: '',
    class_role: 'student',
    responsibilities: [] as string[],
  }
}
const modalOpen = ref(false)
const modalMode = ref<'add' | 'edit'>('add')
const form = reactive(resetForm())
const saving = ref(false)
const saveError = ref('')

function openAdd() {
  modalMode.value = 'add'
  Object.assign(form, resetForm())
  // Default ตำแหน่ง = ตำแหน่งเดียวกับคนล็อกอิน (ถ้าตั้งได้) — สะดวกกรอกซ้ำ ๆ
  form.class_role = settableRoles.value.includes(ownRole.value) ? ownRole.value : 'student'
  saveError.value = ''
  modalOpen.value = true
}

function openEdit(s: Student) {
  modalMode.value = 'edit'
  Object.assign(form, resetForm())
  form.studentId = s.id
  form.first_name = s.first_name || ''
  form.last_name = s.last_name || ''
  form.class_role = s.class_role
  form.responsibilities = [...(s.responsibilities || [])]
  saveError.value = ''
  modalOpen.value = true
}

const canHaveResponsibilities = computed(() =>
  RESPONSIBLE_ROLES.includes(form.class_role as (typeof RESPONSIBLE_ROLES)[number]),
)

// สลับเอา/เอาหน้าที่ออก (ตรวจสอบว่าเป็นหมวดที่ถูกต้อง = CATEGORY_OPTIONS)
function toggleResponsibility(code: string) {
  const idx = form.responsibilities.indexOf(code)
  if (idx >= 0) form.responsibilities.splice(idx, 1)
  else form.responsibilities.push(code)
}

function closeModal() {
  if (saving.value) return
  modalOpen.value = false
}

async function submitForm() {
  saveError.value = ''
  const resp = canHaveResponsibilities.value ? [...form.responsibilities] : undefined

  if (modalMode.value === 'add') {
    if (!form.username.trim()) return (saveError.value = 'กรุณากรอกรหัสนักเรียน / Username')
    if (!form.first_name.trim() || !form.last_name.trim())
      return (saveError.value = 'กรุณากรอกชื่อและนามสกุล')
    if (!form.room_code) return (saveError.value = 'กรุณาเลือกห้อง')
  }

  saving.value = true
  try {
    if (modalMode.value === 'add') {
      await addStudent({
        username: form.username.trim(),
        password: form.password.trim() || undefined,
        prefix: form.prefix.trim() || undefined,
        first_name: form.first_name.trim(),
        last_name: form.last_name.trim(),
        nickname: form.nickname.trim() || undefined,
        room_code: form.room_code,
        class_role: form.class_role,
        responsibilities: resp,
      })
      Swal.fire({
        icon: 'success',
        title: 'เพิ่มผู้ใช้งานแล้ว',
        text: `${roleLabel(form.class_role)} · ${form.first_name} ${form.last_name}`,
        timer: 1500,
        showConfirmButton: false,
      })
    } else if (form.studentId) {
      const data: { class_role: string; responsibilities?: string[] } = {
        class_role: form.class_role,
      }
      if (canHaveResponsibilities.value) data.responsibilities = resp
      await updateStudent(form.studentId, data)
      Swal.fire({ icon: 'success', title: 'บันทึกแล้ว', timer: 1000, showConfirmButton: false })
    }
    modalOpen.value = false
    await load()
  } catch (e) {
    saveError.value = typeof e === 'string' ? e : e instanceof Error ? e.message : 'บันทึกไม่สำเร็จ'
  } finally {
    saving.value = false
  }
}

// คำนำหน้าแบบสั้น (เลือกได้ ไม่บังคับ)
const PREFIX_OPTIONS = ['นาย', 'นางสาว', 'เด็กชาย', 'เด็กหญิง', 'นาง']

const editMeta = computed(() => {
  const sid = form.studentId
  if (!sid) return null
  const s = students.value.find((x) => x.id === sid)
  if (!s) return null
  return { room: s.room_code || '—' }
})
</script>

<template>
  <div>
    <!-- Editorial page header -->
    <div class="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div>
        <p
          class="mb-2 flex items-center gap-2 text-[11px] font-bold uppercase tracking-widest text-[#B91C1C]"
        >
          <i class="bi bi-person-gear text-[13px]"></i> User Management
        </p>
        <h1 class="text-2xl font-bold tracking-tight text-stone-900 leading-tight sm:text-3xl">
          จัดการสมาชิก
        </h1>
        <p class="mt-2 text-sm text-stone-500">
          จัดการกลุ่ม สภานักเรียน · หัวหน้าระดับ · คณะกรรมการห้อง — ตามลำดับชั้น (มองลงได้เท่านั้น)
        </p>
      </div>
      <button
        type="button"
        @click="openAdd"
        class="inline-flex items-center gap-1.5 rounded-xl bg-[#B91C1C] px-4 py-2.5 text-sm font-bold text-white shadow-md transition-all hover:bg-[#991B1B] hover:shadow-lg active:scale-[0.97]"
      >
        <i class="bi bi-person-plus-fill"></i> เพิ่มผู้ใช้งาน
      </button>
    </div>

    <!-- Chip กรองกลุ่มตำแหน่ง (default = กลุ่มเดียวกับคนล็อกอิน) -->
    <div class="mb-4 flex flex-wrap items-center gap-2">
      <button
        type="button"
        @click="groupFilter = 'all'"
        class="rounded-full px-3.5 py-1.5 text-[13px] font-semibold transition-colors"
        :class="
          groupFilter === 'all'
            ? 'bg-stone-900 text-white shadow-sm'
            : 'bg-white text-stone-600 ring-1 ring-stone-200 hover:bg-stone-100'
        "
      >
        ทุกคน <span class="opacity-60">({{ students.length }})</span>
      </button>
      <button
        v-for="g in ROLE_GROUPS"
        :key="g.key"
        type="button"
        @click="groupFilter = g.key"
        class="rounded-full px-3.5 py-1.5 text-[13px] font-semibold transition-colors"
        :class="
          groupFilter === g.key
            ? 'bg-[#B91C1C] text-white shadow-sm'
            : 'bg-white text-stone-600 ring-1 ring-stone-200 hover:bg-stone-100'
        "
      >
        {{ g.label }}
        <span
          v-if="groupCount(g.key) > 0"
          :class="groupFilter === g.key ? 'opacity-70' : 'text-stone-400'"
        >
          ({{ groupCount(g.key) }})
        </span>
      </button>
    </div>

    <!-- ค้นหา -->
    <div class="mb-4">
      <input
        v-model="search"
        type="text"
        placeholder="ค้นหา รหัสนักเรียน / ชื่อ / นามสกุล..."
        class="w-full rounded-xl border border-stone-300 bg-white px-3.5 py-2.5 text-sm outline-none transition focus:border-[#B91C1C] focus:ring-2 focus:ring-[#B91C1C]/20 sm:max-w-sm"
      />
    </div>

    <!-- Loading skeleton -->
    <div
      v-if="isLoading"
      class="overflow-hidden rounded-2xl border border-stone-200 bg-white"
      aria-busy="true"
    >
      <div class="divide-y divide-stone-100">
        <div v-for="i in 6" :key="i" class="flex items-center gap-3 p-4">
          <div class="h-11 w-11 shrink-0 animate-pulse rounded-full bg-stone-100"></div>
          <div class="flex-1 space-y-2">
            <div class="h-4 w-1/3 animate-pulse rounded bg-stone-100"></div>
            <div class="h-3 w-1/2 animate-pulse rounded bg-stone-100"></div>
          </div>
        </div>
      </div>
    </div>

    <!-- Error + retry -->
    <div
      v-else-if="hasError"
      class="rounded-2xl border-2 border-dashed border-stone-200 bg-white py-16 text-center"
    >
      <i class="bi bi-people mb-3 block text-3xl text-stone-300"></i>
      <p class="text-[15px] font-semibold text-stone-700">ไม่สามารถโหลดสมาชิกได้</p>
      <button
        type="button"
        @click="load"
        class="mt-5 inline-flex items-center gap-2 rounded-lg bg-[#B91C1C] px-5 py-2.5 text-[13px] font-bold text-white transition-colors hover:bg-[#991B1B]"
      >
        <i class="bi bi-arrow-clockwise"></i> ลองใหม่
      </button>
    </div>

    <div v-else>
      <!-- กลุ่มที่เลือกยังว่าง (เช่น ระดับตัวเองยังไม่มีสภา) -->
      <div
        v-if="!visibleStudents.length"
        class="rounded-2xl border border-dashed border-stone-200 bg-white py-16 text-center"
      >
        <i class="bi bi-people mb-2 block text-3xl text-stone-300"></i>
        <p class="text-stone-600">ไม่พบสมาชิกในกลุ่มนี้</p>
      </div>

      <!-- มีข้อมูล → แสดงทั้งการ์ดมือถือ + ตารางเดสก์ท็อป -->
      <template v-else>
        <!-- Mobile: การ์ด -->
        <div class="grid gap-3 md:hidden">
          <div
            v-for="s in visibleStudents"
            :key="s.id"
            class="flex items-center gap-3 rounded-2xl border border-stone-200 bg-white p-4"
          >
            <div
              class="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-stone-100 font-bold text-stone-600"
            >
              {{ (s.first_name || 'ส').charAt(0).toUpperCase() }}
            </div>
            <div class="min-w-0 flex-1">
              <p class="truncate font-semibold text-stone-900">
                {{ s.prefix || '' }} {{ s.first_name || '' }} {{ s.last_name || '' }}
              </p>
              <p class="mt-0.5 truncate text-xs text-stone-500">
                <span class="font-mono">{{ s.student_id }}</span>
                <span v-if="s.room_code" class="ml-1.5">· {{ s.room_code }}</span>
              </p>
              <div class="mt-1.5 flex flex-wrap gap-1">
                <span
                  class="rounded-full px-2 py-0.5 text-[11px] font-medium"
                  :class="
                    s.class_role === 'student'
                      ? 'bg-stone-100 text-stone-600'
                      : 'bg-[#B91C1C]/10 text-[#B91C1C]'
                  "
                >
                  {{ roleLabel(s.class_role) }}
                </span>
                <span
                  v-for="code in s.responsibilities || []"
                  :key="code"
                  class="rounded-full bg-stone-100 px-2 py-0.5 text-[11px] text-stone-500"
                >
                  {{ CATEGORY_OPTIONS.find((c) => c.value === code)?.label || code }}
                </span>
              </div>
            </div>
            <button
              type="button"
              @click="openEdit(s)"
              class="shrink-0 rounded-xl p-2.5 text-stone-400 transition-colors hover:bg-stone-100 hover:text-[#B91C1C]"
              :title="'แก้ไข: ' + (s.first_name || '')"
            >
              <i class="bi bi-pencil-square text-lg"></i>
            </button>
          </div>
        </div>

        <!-- Desktop: ตาราง -->
        <div class="hidden overflow-hidden rounded-2xl border border-stone-200 bg-white md:block">
          <table class="w-full text-sm">
            <thead class="bg-stone-50 text-stone-500">
              <tr>
                <th class="px-4 py-3 text-left font-semibold uppercase tracking-wider text-[11px]">
                  รหัสนักเรียน
                </th>
                <th class="px-4 py-3 text-left font-semibold uppercase tracking-wider text-[11px]">
                  ชื่อ-นามสกุล
                </th>
                <th class="px-4 py-3 text-left font-semibold uppercase tracking-wider text-[11px]">
                  ห้อง
                </th>
                <th class="px-4 py-3 text-left font-semibold uppercase tracking-wider text-[11px]">
                  ตำแหน่ง / หน้าที่
                </th>
                <th
                  class="px-4 py-3 text-right font-semibold uppercase tracking-wider text-[11px]"
                ></th>
              </tr>
            </thead>
            <tbody class="divide-y divide-stone-100">
              <tr
                v-for="s in visibleStudents"
                :key="s.id"
                class="transition-colors hover:bg-stone-50"
              >
                <td class="px-4 py-2.5 font-mono text-stone-600">{{ s.student_id }}</td>
                <td class="px-4 py-2.5 font-medium text-stone-800">
                  {{ s.prefix || '' }} {{ s.first_name || '' }} {{ s.last_name || '' }}
                </td>
                <td class="px-4 py-2.5 text-stone-600">{{ s.room_code || '—' }}</td>
                <td class="px-4 py-2.5">
                  <div class="flex flex-wrap items-center gap-1.5">
                    <span
                      class="rounded-full px-2.5 py-0.5 text-xs font-medium"
                      :class="
                        s.class_role === 'student'
                          ? 'bg-stone-100 text-stone-600'
                          : 'bg-[#B91C1C]/10 text-[#B91C1C]'
                      "
                    >
                      {{ roleLabel(s.class_role) }}
                    </span>
                    <span
                      v-for="code in s.responsibilities || []"
                      :key="code"
                      class="rounded-full bg-stone-100 px-2 py-0.5 text-[11px] text-stone-500"
                    >
                      {{ CATEGORY_OPTIONS.find((c) => c.value === code)?.label || code }}
                    </span>
                  </div>
                </td>
                <td class="px-4 py-2.5 text-right">
                  <button
                    type="button"
                    @click="openEdit(s)"
                    class="rounded-lg px-2.5 py-1.5 text-xs font-semibold text-[#B91C1C] transition-colors hover:bg-[#B91C1C]/10"
                  >
                    <i class="bi bi-pencil-square mr-1"></i> แก้ไข
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>
    </div>

    <!-- ════════════ Modal เพิ่ม/แก้ไขผู้ใช้งาน ════════════ -->
    <!-- ⚠️ ต้อง Teleport ออกไปที่ <body> — modal นี้เรนเดอร์อยู่ภายใน stacking context
         ของ `.maincol` (`relative z-10` ใน MainLayout) ⇒ z-50 ข้างในถูกกักไว้ที่ชั้น 10
         และแพ้ bottom tab bar (`fixed z-40`) ที่เป็นพี่น้องกัน ⇒ แถบเมนูล่างทับและกลืนคลิก
         ปุ่มบันทึก. Teleport ทำให้ modal ไปแข่ง z-index ที่ระดับ root แทน -->
    <Teleport to="body">
      <Transition name="sheet">
        <div
          v-if="modalOpen"
          class="fixed inset-0 z-50 flex items-end justify-center sm:items-center"
        >
          <div class="absolute inset-0 bg-stone-900/40 backdrop-blur-sm" @click="closeModal"></div>
          <div
            class="relative z-10 mx-auto flex max-h-[92vh] w-full max-w-lg flex-col overflow-hidden rounded-t-[1.5rem] bg-white shadow-2xl sm:rounded-[1.5rem]"
          >
            <!-- Header -->
            <div class="flex items-center justify-between border-b border-stone-100 px-5 py-4">
              <div>
                <h3 class="text-base font-bold text-stone-900">
                  {{ modalMode === 'add' ? 'เพิ่มผู้ใช้งาน' : 'แก้ไขสมาชิก' }}
                </h3>
                <p v-if="editMeta" class="mt-0.5 text-xs text-stone-500">
                  {{ form.first_name }} {{ form.last_name }} · ห้อง {{ editMeta.room }}
                </p>
              </div>
              <button
                type="button"
                @click="closeModal"
                class="rounded-xl p-2 text-stone-400 hover:bg-stone-100"
              >
                <i class="bi bi-x-lg"></i>
              </button>
            </div>

            <!-- Body -->
            <div class="flex-1 space-y-4 overflow-y-auto px-5 py-4 custom-scrollbar">
              <template v-if="modalMode === 'add'">
                <div>
                  <label class="mb-1 block text-xs font-semibold text-stone-500"
                    >รหัสนักเรียน / Username *</label
                  >
                  <input
                    v-model="form.username"
                    type="text"
                    placeholder="เช่น 12345"
                    class="w-full rounded-xl border border-stone-300 px-3 py-2.5 text-sm outline-none focus:border-[#B91C1C] focus:ring-2 focus:ring-[#B91C1C]/20"
                  />
                </div>
                <div>
                  <label class="mb-1 block text-xs font-semibold text-stone-500"
                    >รหัสผ่านเริ่มต้น
                    <span class="text-stone-400"
                      >(ไม่กรอก = สุ่ม + บังคับเปลี่ยนครั้งแรก)</span
                    ></label
                  >
                  <input
                    v-model="form.password"
                    type="text"
                    placeholder="ปล่อยว่างได้"
                    class="w-full rounded-xl border border-stone-300 px-3 py-2.5 text-sm outline-none focus:border-[#B91C1C] focus:ring-2 focus:ring-[#B91C1C]/20"
                  />
                </div>
                <div>
                  <label class="mb-1 block text-xs font-semibold text-stone-500">คำนำหน้า</label>
                  <div class="flex flex-wrap gap-1.5">
                    <button
                      v-for="p in PREFIX_OPTIONS"
                      :key="p"
                      type="button"
                      @click="form.prefix = form.prefix === p ? '' : p"
                      class="rounded-full px-3 py-1 text-xs font-medium transition-colors"
                      :class="
                        form.prefix === p
                          ? 'bg-stone-900 text-white'
                          : 'bg-stone-100 text-stone-600 hover:bg-stone-200'
                      "
                    >
                      {{ p }}
                    </button>
                  </div>
                </div>
                <div class="grid grid-cols-2 gap-3">
                  <div>
                    <label class="mb-1 block text-xs font-semibold text-stone-500">ชื่อ *</label>
                    <input
                      v-model="form.first_name"
                      type="text"
                      class="w-full rounded-xl border border-stone-300 px-3 py-2.5 text-sm outline-none focus:border-[#B91C1C] focus:ring-2 focus:ring-[#B91C1C]/20"
                    />
                  </div>
                  <div>
                    <label class="mb-1 block text-xs font-semibold text-stone-500">นามสกุล *</label>
                    <input
                      v-model="form.last_name"
                      type="text"
                      class="w-full rounded-xl border border-stone-300 px-3 py-2.5 text-sm outline-none focus:border-[#B91C1C] focus:ring-2 focus:ring-[#B91C1C]/20"
                    />
                  </div>
                </div>
                <div>
                  <label class="mb-1 block text-xs font-semibold text-stone-500"
                    >ชื่อเล่น <span class="text-stone-400">(ไม่บังคับ)</span></label
                  >
                  <input
                    v-model="form.nickname"
                    type="text"
                    class="w-full rounded-xl border border-stone-300 px-3 py-2.5 text-sm outline-none focus:border-[#B91C1C] focus:ring-2 focus:ring-[#B91C1C]/20"
                  />
                </div>
                <div>
                  <label class="mb-1 block text-xs font-semibold text-stone-500">ห้อง *</label>
                  <select
                    v-model="form.room_code"
                    class="w-full rounded-xl border border-stone-300 bg-white px-3 py-2.5 text-sm outline-none focus:border-[#B91C1C]"
                  >
                    <option value="">— เลือกห้อง —</option>
                    <option v-for="r in addableRooms" :key="r.id" :value="r.room_code">
                      {{ r.room_code }}{{ r.level ? ' (' + r.level + ')' : '' }}
                    </option>
                  </select>
                </div>
              </template>

              <div>
                <label class="mb-1 block text-xs font-semibold text-stone-500">ตำแหน่ง</label>
                <select
                  v-model="form.class_role"
                  class="w-full rounded-xl border border-stone-300 bg-white px-3 py-2.5 text-sm outline-none focus:border-[#B91C1C]"
                >
                  <option v-for="r in settableRoles" :key="r" :value="r">{{ roleLabel(r) }}</option>
                </select>
              </div>

              <!-- หน้าที่ — เฉพาะ role ที่รับผิดชอบหมวดได้ -->
              <div v-if="canHaveResponsibilities">
                <p class="mb-1 text-xs font-semibold text-stone-500">
                  หน้าที่ที่รับผิดชอบ <span class="text-stone-400">(เลือกได้หลายหมวด)</span>
                </p>
                <div class="grid grid-cols-1 gap-1.5 sm:grid-cols-2">
                  <button
                    v-for="opt in CATEGORY_OPTIONS"
                    :key="opt.value"
                    type="button"
                    @click="toggleResponsibility(opt.value)"
                    class="flex items-center gap-2 rounded-xl border px-3 py-2 text-left text-[13px] font-medium transition-colors"
                    :class="
                      form.responsibilities.includes(opt.value)
                        ? 'border-[#B91C1C] bg-[#B91C1C]/5 text-[#B91C1C]'
                        : 'border-stone-200 text-stone-600 hover:bg-stone-50'
                    "
                  >
                    <i
                      :class="[
                        'bi',
                        form.responsibilities.includes(opt.value)
                          ? 'bi-check-square-fill'
                          : 'bi-square',
                        'text-sm',
                      ]"
                    ></i>
                    {{ opt.label }}
                  </button>
                </div>
              </div>
              <p v-else class="rounded-xl bg-stone-50 px-3 py-2.5 text-xs text-stone-500">
                ตำแหน่งนี้ไม่มีหมวดหน้าที่ (เฉพาะ สภานักเรียน / ผู้ช่วยหัวหน้าระดับ เท่านั้น)
              </p>

              <p
                v-if="saveError"
                class="rounded-xl bg-red-50 px-3 py-2.5 text-[13px] font-medium text-red-600"
              >
                <i class="bi bi-exclamation-circle mr-1"></i> {{ saveError }}
              </p>
            </div>

            <!-- Footer -->
            <div class="flex items-center justify-end gap-2 border-t border-stone-100 px-5 py-3.5">
              <button
                type="button"
                @click="closeModal"
                :disabled="saving"
                class="rounded-xl px-4 py-2.5 text-sm font-semibold text-stone-600 transition-colors hover:bg-stone-100 disabled:opacity-50"
              >
                ยกเลิก
              </button>
              <button
                type="button"
                @click="submitForm"
                :disabled="saving"
                class="inline-flex items-center gap-2 rounded-xl bg-[#B91C1C] px-5 py-2.5 text-sm font-bold text-white shadow-md transition-all hover:bg-[#991B1B] disabled:opacity-60"
              >
                <span
                  v-if="saving"
                  class="h-4 w-4 animate-spin rounded-full border-2 border-white/40 border-t-white"
                ></span>
                <i v-else class="bi bi-check-lg"></i>
                {{ saving ? 'กำลังบันทึก…' : modalMode === 'add' ? 'เพิ่มผู้ใช้งาน' : 'บันทึก' }}
              </button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<style scoped>
.custom-scrollbar::-webkit-scrollbar {
  width: 5px;
}
.custom-scrollbar::-webkit-scrollbar-thumb {
  background-color: rgba(0, 0, 0, 0.12);
  border-radius: 10px;
}
.sheet-enter-active,
.sheet-leave-active {
  transition: opacity 0.25s ease;
}
.sheet-enter-active .relative,
.sheet-leave-active .relative {
  transition: transform 0.3s cubic-bezier(0.175, 0.885, 0.32, 1);
}
.sheet-enter-from,
.sheet-leave-to {
  opacity: 0;
}
.sheet-enter-from .relative,
.sheet-leave-to .relative {
  transform: translateY(24px) scale(0.99);
}
</style>
