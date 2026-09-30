import { createRouter, createWebHistory } from 'vue-router'
import { REDIRECT_QUERY } from '@/router/redirect'
import { useAuthStore } from '@/stores/auth'
import MainLayout from '@/layouts/MainLayout.vue'

/**
 * หน้าแรกหลัง login = หน้า Welcome/Home กลางเดียว (ทุกบทบาท)
 * — หน้า Welcome จะปรับเนื้อหา/ทางลัดตามสิทธิ์ของคนนั้นเอง
 *    แดชบอร์ด / เรื่องที่รับ / ฯลฯ ยังเข้าได้จากเมนู sidebar / bottom bar ปกติ
 */
function getHomeRoute(): { name: string } {
  return { name: 'home' }
}

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    // 🏠 Landing page (สาธารณะ) — หน้าแรกของเว็บ
    {
      path: '/',
      name: 'landing',
      component: () => import('@/views/Landing.vue'),
      meta: { requiresAuth: false },
    },
    // 🔁 ลิงก์เก่าของแอป (ก่อนย้ายไป /app) — รีไดเรกต์เข้าที่เดิม กันบุ๊กมาร์ก/ลิงก์เก่าเสีย
    { path: '/dashboard', redirect: '/app/dashboard' },
    { path: '/issues/new', redirect: '/app/issues/new' },
    { path: '/issues/mine', redirect: '/app/issues/mine' },
    { path: '/issues/received', redirect: '/app/issues/received' },
    { path: '/issues/:id/edit', redirect: '/app/issues/:id/edit' },
    { path: '/issues/:id', redirect: '/app/issues/:id' },
    { path: '/boards/reports', redirect: '/app/boards/reports' },
    { path: '/boards/:id', redirect: '/app/boards/:id' },
    { path: '/boards', redirect: '/app/boards' },
    { path: '/playbooks/:id', redirect: '/app/playbooks/:id' },
    { path: '/playbooks', redirect: '/app/playbooks' },
    { path: '/notifications', redirect: '/app/notifications' },
    { path: '/students/import', redirect: '/app/students/import' },
    { path: '/students', redirect: '/app/students' },
    { path: '/audit-logs', redirect: '/app/audit-logs' },
    { path: '/profile/edit', redirect: '/app/profile/edit' },
    { path: '/profile/password', redirect: '/app/profile/password' },
    { path: '/profile', redirect: '/app/profile' },
    {
      path: '/login',
      name: 'login',
      component: () => import('@/views/auth/Login.vue'),
      meta: { requiresAuth: false },
    },
    {
      path: '/app',
      component: MainLayout,
      meta: { requiresAuth: true },
      redirect: () => getHomeRoute(),
      children: [
        {
          path: 'home',
          name: 'home',
          component: () => import('@/views/Home.vue'),
          // 🏠 `headerBack: false` ที่ **แท็บรากทุกตัว** จำเป็น ไม่ใช่ของประดับ —
          //    ถ้าไม่ใส่ `useAppChrome` จะตกไปใช้ fallback "รากของแท็บตัวเอง"
          //    ⇒ ได้ลูกศร ← ที่กดแล้วไปหน้าเดิม (ดู `useAppChrome.ts`)
          meta: { requiresAuth: true, navTab: 'home', headerBack: false, fab: 'issue' },
        },
        {
          // 🗂️ แท็บที่ 5 — **route เดียวที่เพิ่มใหม่ทั้ง refactor** (ดู R0.3.2 ในแผน)
          //    🔴 ต้องลงคอมมิตเดียวกันกับ `AppBottomNav` ที่ชี้มาที่นี่เสมอ —
          //       ถ้าแท็บชี้ไป route ที่ยังไม่มี จะตกไปที่ catch-all ⇒ `login?redirect=/app/more`
          //       = **เมนูที่กดแล้วออกจากระบบ** ซึ่งเป็น failure ที่แย่ที่สุดของงานนี้
          path: 'more',
          name: 'more',
          component: () => import('@/views/More.vue'),
          meta: { requiresAuth: true, navTab: 'more', headerBack: false },
        },
        {
          path: 'dashboard',
          name: 'dashboard',
          component: () => import('@/views/Dashboard.vue'),
          meta: { requiresAuth: true, requiresPermission: 'VIEW_DASHBOARD', navTab: 'more' },
        },
        {
          path: 'profile',
          name: 'profile',
          component: () => import('@/views/Profile.vue'),
          meta: { navTab: 'more' },
        },
        {
          // 🧭 กิจกรรมของฉัน + บันทึกไว้ (C1/C2) — ข้อมูลของตัวเองล้วน ⇒ ไม่ต้องมี permission
          //    (ตัวตนคือสิทธิ์ — backend เอา user_id จาก JWT เท่านั้น)
          path: 'me',
          name: 'my-activity',
          component: () => import('@/views/me/MyActivity.vue'),
          meta: { navTab: 'more' },
        },
        {
          path: 'profile/edit',
          name: 'profile-edit',
          component: () => import('@/views/ProfileEdit.vue'),
          meta: { navTab: 'more', navHidden: true, headerBack: { name: 'profile' } },
        },
        {
          path: 'profile/password',
          name: 'profile-password',
          component: () => import('@/views/ChangePassword.vue'),
          meta: { navTab: 'more', navHidden: true, headerBack: { name: 'profile' } },
        },
        {
          path: 'issues/new',
          name: 'new-issue',
          component: () => import('@/views/issues/NewIssue.vue'),
          // ซ่อนแถบล่างเพราะเป็น **ฟอร์ม** (skills #16) — กันนิ้วโป้งชนปุ่มส่ง
          meta: { navTab: 'issues', navHidden: true, headerBack: { name: 'my-issues' } },
        },
        {
          path: 'issues/mine',
          name: 'my-issues',
          component: () => import('@/views/issues/MyIssues.vue'),
          meta: { navTab: 'issues', segmentGroup: 'issues', headerBack: false, fab: 'issue' },
        },
        {
          path: 'issues/received',
          name: 'received-issues',
          component: () => import('@/views/issues/ReceivedIssues.vue'),
          // 🔴 **ไม่ใส่ `requiresPermission`** โดยเจตนา — `students.permissions` เป็น snapshot
          //    ที่ไม่มีอะไร re-sync ⇒ ผู้มีสิทธิ์จริงแต่ snapshot ตกหล่นจะถูกดีดกลับเงียบ ๆ
          //    ⇒ กรองที่ `useNavItems.segmentsOf()` ซึ่งอ่าน auth store สดแทน (R0.3.3)
          meta: { navTab: 'issues', segmentGroup: 'issues', headerBack: false },
        },
        {
          path: 'issues/:id',
          name: 'issue-detail',
          component: () => import('@/views/issues/IssueDetail.vue'),
          // ⚠️ **ไม่ใส่ `navHidden`** — หน้านี้เป็นปลายทางของ push notification
          //    ⇒ ต้องเหลือทางออกมากกว่าลูกศร ← เดียว และแถบที่ซ่อนอยู่ highlight แท็บแม่ไม่ได้
          meta: { navTab: 'issues', headerBack: { name: 'my-issues' } },
        },
        {
          path: 'issues/:id/edit',
          name: 'issue-edit',
          component: () => import('@/views/issues/EditIssue.vue'),
          // ฟอร์ม ⇒ ซ่อนแถบ · ไม่ประกาศ `headerBack` เพราะปลายทางต้องรู้ `:id`
          // ซึ่ง meta เป็นค่าสถิต ⇒ ปล่อยให้ตกไปที่รากของแท็บ "เรื่อง" แทน
          meta: { navTab: 'issues', navHidden: true },
        },
        {
          path: 'boards',
          name: 'boards',
          component: () => import('@/views/boards/PiriBoards.vue'),
          meta: { navTab: 'boards', headerBack: false },
        },
        {
          path: 'boards/reports',
          name: 'board-reports',
          component: () => import('@/views/boards/ReportModeration.vue'),
          meta: { requiresAuth: true, requiresCouncil: true, navTab: 'more' },
        },
        {
          path: 'boards/:id',
          name: 'board-detail',
          component: () => import('@/views/boards/BoardDetail.vue'),
          meta: { navTab: 'boards', headerBack: { name: 'boards' } },
        },
        // 📅 กิจกรรม (D1) — สองระดับสิทธิ์: นักเรียน (สาธารณะ) กับสภา (จัดการ/ฉบับร่าง)
        //    (ไม่ระบุจำนวนหน้าโดยเจตนา — จำนวนเคยถูกเขียนไว้แล้วล้าสมัยทุกครั้งที่มีหน้าใหม่)
        //    ⚠️ **path 1 ส่วนที่ขึ้นต้นด้วยคำอังกฤษ (`manage`/`new`) ต้องมาก่อน `events/:id`**
        //       — ไม่งั้นคำนั้นถูกจับเป็น `:id` แล้วหน้า detail จะได้ eventId = "new" ⇒ ยิง API ด้วย NaN
        //       (ตอนนี้มีสองคำ: `manage` กับ `new` — เพิ่มคำใหม่ต้องวาง *ก่อน* `events/:id` เสมอ)
        {
          // รายการกิจกรรมที่เผยแพร่แล้ว — นักเรียนทุกคนเห็น (ต้องล็อกอิน แต่ไม่ต้องมี MANAGE_EVENTS)
          path: 'events',
          name: 'events',
          component: () => import('@/views/events/EventList.vue'),
          meta: { requiresAuth: true, navTab: 'events', headerBack: false, fab: 'event' },
        },
        {
          // หน้าจัดการของสภา — ★ permission ตรวจที่ **route meta** ด้วย ไม่ใช่พึ่ง backend อย่างเดียว
          //   (backend ยังตรวจซ้ำใน service เสมอ — อันนี้เพื่อไม่ให้เมนู/หน้าโผล่โดยไม่มีสิทธิ์)
          path: 'events/manage',
          name: 'event-management',
          component: () => import('@/views/events/EventManagement.vue'),
          // 🔁 R4 จะยุบหน้านี้เข้าแท็บ "กิจกรรม" เป็น segment "จัดการ" — ตอนนี้ยังเป็นหน้าของตัวเอง
          //    แต่ประกาศ `navTab: 'events'` ไว้แล้ว เพื่อให้ย้ายแล้วไม่ต้องแก้ meta อีก
          meta: { requiresAuth: true, requiresPermission: 'MANAGE_EVENTS', navTab: 'events', fab: 'event' },
        },
        {
          // ✍️ สร้างกิจกรรม — **หน้าเต็มหน้า ไม่ใช่ modal** (รอบ 4)
          // ⚠️ อยู่ **ก่อน** `events/:id` โดยจำเป็น — "new" จะถูกจับเป็น `:id` ถ้าวางหลัง
          //    (เหตุผลเดียวกับ `events/manage` ข้างบน — ดูคำเตือนที่หัวกลุ่มนี้)
          // ⚠️ `requiresPermission` เหมือน `events/manage` ไม่ใช่แค่ `requiresAuth` — ตัว endpoint
          //    ตรวจ MANAGE_EVENTS อยู่แล้ว แต่ถ้าไม่กันที่ route นักเรียนที่เดา URL จะเปิดฟอร์มได้
          //    แล้วเจอ 403 ตอนกดบันทึก ⇒ "พิมพ์ไปเยอะแล้วเพิ่งบอกว่าไม่มีสิทธิ์" ซึ่งแย่ที่สุด
          path: 'events/new',
          name: 'event-create',
          component: () => import('@/views/events/EventForm.vue'),
          meta: {
            requiresAuth: true,
            requiresPermission: 'MANAGE_EVENTS',
            navTab: 'events',
            navHidden: true,
            headerBack: { name: 'events' },
          },
        },
        {
          path: 'events/:id',
          name: 'event-detail',
          component: () => import('@/views/events/EventDetail.vue'),
          // ปลายทางของ deep link ⇒ เห็นแถบล่าง (เหตุผลเดียวกับ `issue-detail`)
          meta: { requiresAuth: true, navTab: 'events', headerBack: { name: 'events' } },
        },
        {
          // ✏️ แก้ไขกิจกรรม — คอมโพเนนต์เดียวกับหน้าสร้าง (`EventForm.vue`) เพราะ 8 ฟิลด์เหมือนกันเป๊ะ
          //    และ `buildCreate`/`buildPatch` ถูกออกแบบให้ใช้ร่วมกันโดยเจตนา ⇒ ตรรกะ "ยังไม่บันทึก"
          //    มีนิยามเดียว ไม่มีทางที่สองหน้าจะตีความต่างกัน
          // ⚠️ 3 ส่วน ⇒ ไม่ชนกับ `events/:id` (2 ส่วน) · ลำดับสลับกันได้
          path: 'events/:id/edit',
          name: 'event-edit',
          component: () => import('@/views/events/EventForm.vue'),
          meta: {
            requiresAuth: true,
            requiresPermission: 'MANAGE_EVENTS',
            navTab: 'events',
            navHidden: true,
          },
        },
        {
          // 👥 รายชื่อผู้สมัคร + เช็คอินมือ (เดิมเป็น modal ในหน้า `events/manage` — รอบ 4)
          // ⚠️ 3 ส่วน ⇒ ไม่ชนกับ `events/:id` (2 ส่วน) ⇒ ลำดับสลับกันได้
          //    และคนละ literal กับ `events/:id/edit`/`check-in` ⇒ ไม่ชนกันอยู่แล้ว
          path: 'events/:id/registrations',
          name: 'event-registrations',
          component: () => import('@/views/events/EventRegistrations.vue'),
          meta: {
            requiresAuth: true,
            requiresPermission: 'MANAGE_EVENTS',
            navTab: 'events',
            navHidden: true,
          },
        },
        {
          // หน้าสแกนเช็คอินหน้างาน (D2) — **สภาเท่านั้น**
          // ⚠️ ต้องมี `requiresPermission` เหมือน `events/manage` ไม่ใช่แค่ `requiresAuth`:
          //    ตัว endpoint ตรวจ MANAGE_EVENTS อยู่แล้ว แต่ถ้าไม่กันที่ route นักเรียนที่เดา URL
          //    จะเปิดหน้ากล้องขึ้นมาได้ แล้วเจอ 403 ทุกครั้งที่สแกน — ดูเหมือนระบบพังทั้งที่
          //    เป็นเรื่องสิทธิ์ (และไม่มีเหตุผลใดที่นักเรียนต้องเปิดหน้านี้)
          // ⚠️ 3 ส่วน (`events/:id/check-in`) ไม่ชนกับ `events/:id` (2 ส่วน) ที่อยู่ก่อนหน้า
          //    ⇒ ลำดับสลับกันได้ ไม่เหมือนกรณี `events/manage` vs `events/:id`
          path: 'events/:id/check-in',
          name: 'event-check-in',
          component: () => import('@/views/events/EventCheckIn.vue'),
          // กล้องเต็มจอ ⇒ ซ่อนทั้งแถบล่างและหัวแถบ — **ต้องเหลือปุ่มปิดที่มองเห็นได้เสมอ**
          // ไม่งั้นผู้ใช้ที่ปฏิเสธสิทธิ์กล้องจะติดอยู่ในหน้านี้โดยไม่มีทางออก (R4.4)
          meta: {
            requiresAuth: true,
            requiresPermission: 'MANAGE_EVENTS',
            navTab: 'events',
            navHidden: true,
            headerHidden: true,
          },
        },
        {
          path: 'playbooks',
          name: 'playbooks',
          component: () => import('@/views/playbooks/PlaybooksCatalog.vue'),
          meta: { requiresAuth: true, navTab: 'more' },
        },
        {
          path: 'playbooks/:id',
          name: 'playbook-reader',
          component: () => import('@/views/playbooks/PlaybookReader.vue'),
          meta: { requiresAuth: true, navTab: 'more', headerBack: { name: 'playbooks' } },
        },
        {
          path: 'notifications',
          name: 'notifications',
          component: () => import('@/views/notifications/NotificationCenter.vue'),
          // 🔔 เข้าถึงจากกระดิ่งบนหัวแถบ *ทุกหน้า* ⇒ ปลายทางของ ← จึงไม่ใช่ "หน้าที่แล้ว"
          //    (meta เป็นค่าสถิต รู้ไม่ได้) ⇒ ชี้ไปหน้าแรกซึ่งเป็นที่ที่ผู้ใช้รู้จักดีที่สุด
          meta: { requiresAuth: true, navTab: 'more', headerBack: { name: 'home' } },
        },
        {
          path: 'users',
          name: 'users',
          component: () => import('@/views/students/UserManagement.vue'),
          // 👥 "สมาชิก" ไม่ใช่แท็บ — เป็นคู่ segment กับ `students` เข้าจากหน้า "เพิ่มเติม"
          meta: {
            requiresAuth: true,
            requiresPermission: 'MANAGE_STUDENTS',
            navTab: 'more',
            segmentGroup: 'members',
            fab: 'member',
          },
        },
        {
          path: 'students',
          name: 'students',
          component: () => import('@/views/students/StudentList.vue'),
          meta: {
            requiresAuth: true,
            requiresPermission: 'MANAGE_STUDENTS',
            navTab: 'more',
            segmentGroup: 'members',
            fab: 'member',
          },
        },
        {
          path: 'students/import',
          name: 'import-students',
          component: () => import('@/views/students/ImportStudents.vue'),
          // ฟอร์มนำเข้า ⇒ ซ่อนแถบล่าง (แถบ segment ที่ค้างอยู่จะชวนให้กดออกกลางฟอร์ม)
          meta: {
            requiresAuth: true,
            requiresPermission: 'MANAGE_STUDENTS',
            navTab: 'more',
            navHidden: true,
            headerBack: { name: 'students' },
          },
        },
        {
          path: 'announcements',
          name: 'announcements',
          component: () => import('@/views/announcements/AnnouncementManagement.vue'),
          meta: {
            requiresAuth: true,
            requiresPermission: 'MANAGE_ANNOUNCEMENTS',
            navTab: 'more',
          },
        },
        {
          // 📅 ภาคเรียน — ใช้ MANAGE_SETTINGS ที่มีอยู่แล้ว (ไม่ต้อง backfill สิทธิ์)
          path: 'settings/terms',
          name: 'academic-terms',
          component: () => import('@/views/settings/AcademicTerms.vue'),
          meta: { requiresAuth: true, requiresPermission: 'MANAGE_SETTINGS', navTab: 'more' },
        },
        {
          path: 'audit-logs',
          name: 'audit-logs',
          component: () => import('@/views/audit/AuditLogs.vue'),
          meta: { requiresAuth: true, requiresPermission: 'VIEW_AUDIT_LOG', navTab: 'more' },
        },
      ],
    },

    /**
     * 🧭 ทางตัน — path ที่ไม่ตรงกับ route ใดเลย (§30 ข้อ 2)
     *
     * ⚠️ **ทำไมต้องมี** — ก่อนหน้านี้ path ที่ไม่ match จะ **ไม่มี route ถูกเลือกเลย**
     *   ⇒ `to.meta` เป็น `{}` ⇒ `requiresAuth` เป็น `undefined` ⇒ **guard ผ่าน**
     *   ⇒ `<RouterView>` ว่างเปล่า = **จอขาว** · ไม่มี error ไม่มี log ไม่มีอะไรบอกผู้ใช้
     *
     *   เคสจริงที่เจอได้ทันที: `/app/events/7` **ก่อนที่ D1 จะขึ้น** (หรือหลังเปลี่ยนชื่อ route)
     *   ⇒ ผู้ใช้ที่สแกน QR ที่ติดหน้าโรงเรียน / กดลิงก์ใน LINE **เจอจอขาว** ซึ่งแย่กว่า
     *     การถูกพาไปล็อกอินเสียอีก และมันจะดูเหมือน **"QR พัง"** ทั้งที่โค้ด QR ถูกทุกบรรทัด
     *   ⇒ ปลายทางที่ยังไม่มี route ต้อง **เด้งไป login พร้อมจำปลายทาง** เหมือน deep link ปกติ
     *     ⇒ พอ route ขึ้นจริง (deploy รอบถัดไป) ผู้ใช้ที่ล็อกอินค้างอยู่ก็ไปถึงของจริงทันที
     *
     * 🔁 **ทำไมไม่วนลูป** — ปลายทางคือ route ชื่อ `login` ซึ่ง
     *   ① มี path ตายตัว (`/login`) ⇒ ถูก match ด้วย static route ที่ **เฉพาะเจาะจงกว่า** เสมอ
     *     ⇒ ไม่กลับมาที่ catch-all ตัวนี้อีก (catch-all แพ้ทุก route ที่ระบุ path ชัดเจน)
     *   ② ผู้ใช้ที่ล็อกอินอยู่แล้วจะถูก guard พาไป `home` ที่บรรทัด `to.path === '/login'`
     *     ⇒ จบที่หน้าแรก ไม่ใช่จอขาว และไม่วน
     *   ⇒ ทั้งสองเส้นทางมีทางออกเสมอ **ห้ามเปลี่ยนปลายทางนี้เป็น path ที่ไม่มี route รองรับ**
     *
     * ⚠️ **`to.fullPath` เป็นค่าที่ "ใครก็เขียนได้"** (มาจาก URL) — ตัวกรองจริงอยู่ที่
     *   `safeRedirect()` ในหน้า Login ⇒ ที่นี่ส่งต่ออย่างเดียว **ห้ามตัดสินความปลอดภัยเอง**
     */
    {
      path: '/:pathMatch(.*)*',
      name: 'not-found',
      redirect: (to) => ({ name: 'login', query: { [REDIRECT_QUERY]: to.fullPath } }),
    },
  ],
})

router.beforeEach(async (to) => {
  const authStore = useAuthStore()
  const isAuthenticated = authStore.isAuthenticated

  if (to.meta.requiresAuth && !isAuthenticated) {
    // 🔗 จำปลายทางไว้ — deep link จาก push (A4) ที่เปิดตอนยังไม่ล็อกอิน/token หมดอายุ
    //    จะได้กลับไปถึงของจริงหลังล็อกอิน ไม่ต้องให้ผู้ใช้ไปกด notification ซ้ำเอง
    //    ⚠️ ฝั่ง **หน้า Login ต้องกรองค่านี้ก่อนใช้** (`safeRedirect`) เพราะมันมาจาก URL
    //       ⇒ guard แค่ส่งต่อ ไม่ได้แปลว่าปลอดภัย (ดู `router/redirect.ts`)
    return { name: 'login', query: { [REDIRECT_QUERY]: to.fullPath } }
  }

  // โหลด user ให้ชัวร์ก่อนตัดสินใจ redirect/สิทธิ์ — ไม่งั้น getHomeRoute()
  // เห็น permissions ว่าง → redirect ผิดบทบาทตอน refresh หน้า Landing/login
  if (isAuthenticated && !authStore.user) {
    try {
      await authStore.loadMe()
    } catch {
      /* ignore — เหลือ user null → ตกไป route พื้นฐาน (new-issue) */
    }
  }

  if (to.path === '/login' && isAuthenticated) {
    return getHomeRoute()
  }
  // เข้า Landing แล้ว แต่ล็อกอินอยู่แล้ว → ข้ามไปหน้าแรกตามบทบาท
  if (to.name === 'landing' && isAuthenticated) {
    return getHomeRoute()
  }

  if (isAuthenticated) {
    // 🔐 บัญชีที่ระบบสร้างให้ (seed) ยังไม่ได้เปลี่ยนรหัส → บังคับไปหน้าเปลี่ยนรหัสก่อนใช้ระบบ
    //    🔗 **พา `redirect` ผ่านไปด้วย** (§30 ข้อ 3) — ไม่งั้นบัญชีที่เพิ่งเปิดลิงก์ที่แชร์มา
    //       (หรือ deep link จาก push) จะ **ทิ้งปลายทางถาวร** ⇒ เปลี่ยนรหัสเสร็จแล้วต้องหา
    //       ลิงก์เดิมมากดซ้ำเอง ทั้งที่ระบบรู้อยู่แล้วว่าผู้ใช้จะไปไหน
    //    ⚠️ เงื่อนไข `to.name !== 'profile-password'` ต้องคงไว้ ไม่งั้น **วนไม่จบ**
    //       (หน้าเปลี่ยนรหัสจะ redirect ไปหาตัวเองพร้อม `redirect` ที่ชี้มาที่ตัวเอง)
    if (authStore.mustChangePassword && to.name !== 'profile-password') {
      return { name: 'profile-password', query: { [REDIRECT_QUERY]: to.fullPath } }
    }
  }

  // ตรวจ permission ถ้า route ต้องการ
  const needPermission = to.meta.requiresPermission as string | undefined
  if (needPermission && isAuthenticated) {
    if (!authStore.hasPermission(needPermission)) {
      // ไม่มีสิทธิ์ → ไปหน้าแรกที่เข้าได้ตามบทบาท
      return getHomeRoute()
    }
  }

  // หน้าเฉพาะสภานักเรียน/แอดมิน (อำนาจระดับสภา — เช่น คิวรายงาน)
  const requiresCouncil = to.meta.requiresCouncil as boolean | undefined
  if (requiresCouncil && isAuthenticated && !authStore.isCouncilAuthority) {
    return getHomeRoute()
  }

  return true
})

export default router
