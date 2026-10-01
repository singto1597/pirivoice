# 🎨 Frontend Rules (Vue 3 + TypeScript)

คุณคือ Lead Frontend Engineer ที่ดูแล PIRIvoice (ระบบรับฟังความคิดเห็นและปัญหาสภานักเรียน) กฎเหล่านี้คือมาตรฐานที่ต้องปฏิบัติตามอย่างเคร่งครัด

## 1. Stack & Core Technologies
- **Framework:** Vue 3 (Composition API พร้อม `<script setup lang="ts">`)
- **Language:** TypeScript อย่างเคร่งครัด (**ห้ามใช้ `any` เด็ดขาด**)
- **State Management:** `Pinia`
- **Styling:** `Tailwind CSS` เท่านั้น (ถอด `DaisyUI` ออกแล้ว — ดู §6)
- **HTTP Client:** `Axios` (ผ่าน `src/services/api.ts`)

## 2. โครงสร้างและการแยก Layer
> ⚠️ เดิมหัวข้อนี้เขียนว่า "4-Layer" (Types / Services / Views / Components) — **ไม่ครบมาตั้งแต่รอบ 5**
> ซึ่งเพิ่ม `components/ui/` `components/layout/` `composables/` `constants/` และ `utils/` เข้ามา

- **Types (`src/types/`):** นิยาม Interface สำหรับ Data Model ทั้งหมด
- **Services (`src/services/`):** 
  - ศูนย์รวม Logic การเรียก API (ห้ามเรียก `api.get/post` ใน View โดยตรง)
  - จัดการข้อมูลก่อนส่งหรือหลังรับจาก Backend
- **Views (`src/views/`):** จัดการ UI Logic, Lifecycle และการแสดงผล
- **Components (`src/components/`):** UI ชิ้นส่วนที่ใช้ซ้ำได้
  - **`ui/` = design system** — `AppCard` · `AppButton` · `AppChip` · `AppTabs` · `AppSheet` ·
    `AppEmptyState` · `IconButton` · `PageHeader` · `StatusBadge`
    ⇒ **ปุ่ม/การ์ด/แท็บ/สถานะว่าง ต้องมาจากที่นี่** ไม่ใช่เขียน utility class ใหม่ในหน้า
    (นี่คือสาเหตุรากของ "สีเส้นปน 3 ค่า มุมปน 4 ค่า" ก่อนรอบ 5)
  - **`layout/` = shell** — `AppHeader` · `AppSidebar` · `AppBottomNav` · `AppTabBar` · `AppFab` ·
    `AppNavRow` · `AppGroupHeader` (ประกอบเข้าด้วยกันที่ `layouts/MainLayout.vue`)
- **Composables (`src/composables/`):** `useNavItems` · `useAppChrome` · `useIdentity` · `useMediaQuery`
- **Constants (`src/constants/`):** `nav` (`NAV_TABS` + `NAV_GROUPS` + `routeTitles`) · `roles` · `status` ·
  `brand` · `chart` · `importStatus`
- **Utils (`src/utils/`):** `avatar` (`avatarChar` — กันบั๊กสระนำ "แอดมิน" → "แ")
- **Layouts (`src/layouts/`):** `MainLayout.vue` ไฟล์เดียว — **ไม่มี `GlobalLayout.vue`**
  (CLAUDE.md เคยเขียนไว้ผิด แก้แล้ว 30 ก.ย. 2026)

## 3. Data Flow & API Standard
- **No Direct DB Access:** ห้ามเชื่อมต่อ Database โดยตรง ต้องผ่าน API ของ Backend เท่านั้น
- **Axios Interceptors:** ใช้ `src/services/api.ts` ซึ่งจัดการ Auth Token และ Error 401/422 ไว้ให้แล้ว
- **Response Handling:** Backend ส่งข้อมูลในรูปแบบ JSON โดย Error จะอยู่ในฟิลด์ `detail`

## 4. UI/UX & Feedback Rules
- **Loading State:** ทุกครั้งที่มีการดึงข้อมูล ต้องมี `const isLoading = ref(true)` และแสดง Spinner หรือ Skeleton Screen
- **Notifications:** การแจ้งเตือน Error/Success/Confirm **ต้องใช้ `SweetAlert2` (`Swal.fire`) เท่านั้น** ห้ามใช้ `alert()` หรือ `toast` อื่นๆ
- **Timezone:** แสดงผลเวลาเป็นภาษาไทย และจัดการให้เป็น `Asia/Bangkok` (UTC+7)

## 5. Coding Standards
- **Component Naming:** ใช้ `PascalCase` สำหรับชื่อไฟล์ Component
- **Variable Naming:** ใช้ `camelCase` สำหรับตัวแปรและฟังก์ชัน
- **Props/Emits:** ต้องนิยาม Type ให้ชัดเจนด้วย `defineProps<{...}>()` และ `defineEmits<{...}>()`
- **Reactive State:** ใช้ `ref()` เป็นหลักสำหรับ Primitive และ `reactive()` สำหรับ Objects ขนาดใหญ่

## 6. CSS & Theme
- ใช้ Utility Classes ของ Tailwind เป็นหลัก
- 🔴 **`DaisyUI` ถูกถอดออกจากโปรเจกต์แล้ว** (รอบ 5 · คอมมิต 4) — เอกสารฉบับก่อนเขียนว่า
  "ติดตั้งและเปิดใช้อยู่จริง ⇒ ใช้ `btn`/`card`/`badge` ก่อนเขียนสไตล์เอง" ซึ่ง **ตรงข้ามกับความจริง**:
  มันถูกติดตั้งแบบ `themes: false` และ **ไม่มีเทมเพลตไหนใช้คลาสของมันเลยแม้แต่ที่เดียว**
  ⇒ `main.css` **เคยต้อง**ค้ำ `input/select/textarea` ด้วย `!important` เพื่อสู้กับสไตล์ฐานของมัน
  อยู่หลายปี (ถอด `!important` ชุดนั้นออกแล้วตอนถอด daisyUI — ดู `src/assets/main.css`)
  **ห้ามนำกลับเข้ามา** และ **ห้ามเรียกคลาส `btn`/`card`/`badge` ของ DaisyUI**
- ✅ ใช้ **component กลางใน `src/components/ui/`** แทน — `AppCard` · `AppButton` · `AppChip` ·
  `AppTabs` · `AppSheet` · `AppEmptyState` · `IconButton` · `PageHeader` · `StatusBadge`
  ⇒ ปุ่ม/การ์ดที่เขียนเองด้วย utility class โดยไม่ผ่าน component กลาง คือสิ่งที่ทำให้ระบบ
  ไม่สม่ำเสมอ (สีเส้นปน 3 ค่า มุมปน 4 ค่า) — **ให้เพิ่ม variant ที่ component กลางแทนการเขียนใหม่**
- **สี:** ต้องมาจาก token ใน `tailwind.config.js` (`brand` · `line` · `ink` · `ok` · `warn` ·
  `danger` · `canvas` · `surface`) — **ห้ามฮาร์ดโค้ด hex**
  มีด่านกันอยู่ 2 ตัวที่รันใน `npm run lint`: `lint:colors` (`[#B91C1C]` ฯลฯ) และ
  `lint:palette` (ห้าม `emerald|green|teal|lime-<ตัวเลข>` — "สำเร็จ" ต้องมาจาก `ok-*` เท่านั้น)
- **`<style>` / `:style` = ค่าเริ่มต้นคือไม่ใช้** แต่ไม่ใช่ข้อห้ามเด็ดขาด — ของจริงในเรพ
  **17 จาก 64 ไฟล์** มี `<style>` และ **9 ไฟล์** ใช้ `:style` (ส่วนใหญ่เป็นค่าที่คำนวณจากข้อมูล
  เช่นความกว้างแท่งกราฟ ซึ่งเขียนเป็น utility class ไม่ได้)
  > ⚠️ **ตัวเลขนี้เคยเขียนว่า "18 จาก 44 ไฟล์ / 6 ไฟล์"** ซึ่งถูก ณ คอมมิต `16cd8b8`
  > แล้ว **ไม่ถูกอัปเดตอีกเลย** จนรอบ 5 — ตัวเลขในเอกสารที่ไม่มีใครนับใหม่ คือตัวเลขที่จะผิดเสมอ
  > ⇒ **ถ้าจะอ้างจำนวน ให้นับสดแล้วใส่คอมมิตที่วัดกำกับ** หรือไม่ต้องใส่ตัวเลขเลย
  - ✅ เขียน `<style scoped>` ได้เมื่อเป็นสไตล์ที่ Tailwind แสดงไม่ได้จริง ๆ (keyframes,
    `::v-deep`, ค่าที่ผูกกับตัวแปร) — **ใส่ `scoped` เสมอ**
  - ⚠️ อย่าใช้ `<style>` เป็นที่ทิ้งสไตล์ที่เขียนเป็น utility ได้ — และ **อย่าปฏิเสธ PR
    เพราะมี `<style>` เพียงอย่างเดียว** (กฎนี้เป็นค่าเริ่มต้น ไม่ใช่ด่านตรวจ)
