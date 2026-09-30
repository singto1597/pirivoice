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
          meta: { requiresAuth: true },
        },
        {
          path: 'dashboard',
          name: 'dashboard',
          component: () => import('@/views/Dashboard.vue'),
          meta: { requiresAuth: true, requiresPermission: 'VIEW_DASHBOARD' },
        },
        {
          path: 'profile',
          name: 'profile',
          component: () => import('@/views/Profile.vue'),
        },
        {
          // 🧭 กิจกรรมของฉัน + บันทึกไว้ (C1/C2) — ข้อมูลของตัวเองล้วน ⇒ ไม่ต้องมี permission
          //    (ตัวตนคือสิทธิ์ — backend เอา user_id จาก JWT เท่านั้น)
          path: 'me',
          name: 'my-activity',
          component: () => import('@/views/me/MyActivity.vue'),
        },
        {
          path: 'profile/edit',
          name: 'profile-edit',
          component: () => import('@/views/ProfileEdit.vue'),
        },
        {
          path: 'profile/password',
          name: 'profile-password',
          component: () => import('@/views/ChangePassword.vue'),
        },
        {
          path: 'issues/new',
          name: 'new-issue',
          component: () => import('@/views/issues/NewIssue.vue'),
        },
        {
          path: 'issues/mine',
          name: 'my-issues',
          component: () => import('@/views/issues/MyIssues.vue'),
        },
        {
          path: 'issues/received',
          name: 'received-issues',
          component: () => import('@/views/issues/ReceivedIssues.vue'),
        },
        {
          path: 'issues/:id',
          name: 'issue-detail',
          component: () => import('@/views/issues/IssueDetail.vue'),
        },
        {
          path: 'issues/:id/edit',
          name: 'issue-edit',
          component: () => import('@/views/issues/EditIssue.vue'),
        },
        {
          path: 'boards',
          name: 'boards',
          component: () => import('@/views/boards/PiriBoards.vue'),
        },
        {
          path: 'boards/reports',
          name: 'board-reports',
          component: () => import('@/views/boards/ReportModeration.vue'),
          meta: { requiresAuth: true, requiresCouncil: true },
        },
        {
          path: 'boards/:id',
          name: 'board-detail',
          component: () => import('@/views/boards/BoardDetail.vue'),
        },
        // 📅 กิจกรรม (D1) — สามหน้า สองระดับสิทธิ์
        //    ⚠️ `events/manage` **ต้องมาก่อน** `events/:id` — ไม่งั้น "manage" ถูกจับเป็น `:id`
        //       แล้วหน้า detail จะได้ eventId = "manage" ⇒ ยิง API ด้วย NaN
        {
          // รายการกิจกรรมที่เผยแพร่แล้ว — นักเรียนทุกคนเห็น (ต้องล็อกอิน แต่ไม่ต้องมี MANAGE_EVENTS)
          path: 'events',
          name: 'events',
          component: () => import('@/views/events/EventList.vue'),
          meta: { requiresAuth: true },
        },
        {
          // หน้าจัดการของสภา — ★ permission ตรวจที่ **route meta** ด้วย ไม่ใช่พึ่ง backend อย่างเดียว
          //   (backend ยังตรวจซ้ำใน service เสมอ — อันนี้เพื่อไม่ให้เมนู/หน้าโผล่โดยไม่มีสิทธิ์)
          path: 'events/manage',
          name: 'event-management',
          component: () => import('@/views/events/EventManagement.vue'),
          meta: { requiresAuth: true, requiresPermission: 'MANAGE_EVENTS' },
        },
        {
          path: 'events/:id',
          name: 'event-detail',
          component: () => import('@/views/events/EventDetail.vue'),
          meta: { requiresAuth: true },
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
          meta: { requiresAuth: true, requiresPermission: 'MANAGE_EVENTS' },
        },
        {
          path: 'playbooks',
          name: 'playbooks',
          component: () => import('@/views/playbooks/PlaybooksCatalog.vue'),
          meta: { requiresAuth: true },
        },
        {
          path: 'playbooks/:id',
          name: 'playbook-reader',
          component: () => import('@/views/playbooks/PlaybookReader.vue'),
          meta: { requiresAuth: true },
        },
        {
          path: 'notifications',
          name: 'notifications',
          component: () => import('@/views/notifications/NotificationCenter.vue'),
          meta: { requiresAuth: true },
        },
        {
          path: 'users',
          name: 'users',
          component: () => import('@/views/students/UserManagement.vue'),
          meta: { requiresAuth: true, requiresPermission: 'MANAGE_STUDENTS' },
        },
        {
          path: 'students',
          name: 'students',
          component: () => import('@/views/students/StudentList.vue'),
          meta: { requiresAuth: true, requiresPermission: 'MANAGE_STUDENTS' },
        },
        {
          path: 'students/import',
          name: 'import-students',
          component: () => import('@/views/students/ImportStudents.vue'),
          meta: { requiresAuth: true, requiresPermission: 'MANAGE_STUDENTS' },
        },
        {
          path: 'announcements',
          name: 'announcements',
          component: () => import('@/views/announcements/AnnouncementManagement.vue'),
          meta: { requiresAuth: true, requiresPermission: 'MANAGE_ANNOUNCEMENTS' },
        },
        {
          // 📅 ภาคเรียน — ใช้ MANAGE_SETTINGS ที่มีอยู่แล้ว (ไม่ต้อง backfill สิทธิ์)
          path: 'settings/terms',
          name: 'academic-terms',
          component: () => import('@/views/settings/AcademicTerms.vue'),
          meta: { requiresAuth: true, requiresPermission: 'MANAGE_SETTINGS' },
        },
        {
          path: 'audit-logs',
          name: 'audit-logs',
          component: () => import('@/views/audit/AuditLogs.vue'),
          meta: { requiresAuth: true, requiresPermission: 'VIEW_AUDIT_LOG' },
        },
      ],
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
    if (authStore.mustChangePassword && to.name !== 'profile-password') {
      return { name: 'profile-password' }
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
