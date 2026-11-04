import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import * as authService from '@/services/auth'
import { clearQueryCache } from '@/services/queryCache'
import type { AuthUser } from '@/types/auth'

// จัดการ Session/Auth state

export const useAuthStore = defineStore('auth', () => {
  const accessToken = ref<string | null>(localStorage.getItem('access_token'))
  const user = ref<AuthUser | null>(null)

  const isAuthenticated = computed(() => !!accessToken.value)

  // ชื่อย่อ/สิทธิ์
  const displayName = computed(() => user.value?.full_name || user.value?.username || '')
  const roles = computed(() => user.value?.roles || [])
  const isAdmin = computed(() => user.value?.is_admin ?? false)
  // 🏛️ มีอำนาจระดับสภา/แอดมิน (อนุมัติเผยแพร่ PIRI Board ได้) — ตรงกับ backend _has_council_authority
  const isCouncilAuthority = computed(
    () =>
      isAdmin.value ||
      roles.value.some((r) =>
        ['council_member', 'council_president', 'teacher_council'].includes(r.role || ''),
      ),
  )
  const permissions = computed(() => user.value?.permissions || [])
  // หมวดหน้าที่รวมของทุก role (council_member / level_vice_president) — dedup keep order
  const responsibilities = computed(() => {
    const seen = new Set<string>()
    const out: string[] = []
    for (const r of roles.value) {
      for (const code of r.responsibilities || []) {
        if (!seen.has(code)) {
          seen.add(code)
          out.push(code)
        }
      }
    }
    return out
  })
  // บัญชีที่ระบบสร้างให้ (seed) → ต้องบังคับเปลี่ยนรหัสก่อนเข้าใช้งาน
  const mustChangePassword = computed(() => user.value?.must_change_password ?? false)

  function setToken(token: string) {
    accessToken.value = token
    localStorage.setItem('access_token', token)
  }

  function setUser(u: AuthUser) {
    user.value = u
    localStorage.setItem('user_id_str', String(u.id))
  }

  async function login(username: string, password: string): Promise<AuthUser> {
    const res = await authService.login(username, password)
    // กันข้ามบัญชี: cache ผูก token อยู่แล้ว แต่ล้างชัด ๆ อีกชั้นก่อนสลับตัวตน
    clearQueryCache()
    setToken(res.access_token)
    setUser(res.user)
    return res.user
  }

  async function loadMe() {
    if (!accessToken.value) return null
    const me = await authService.fetchMe()
    setUser(me)
    return me
  }

  // เคลียร์ flag บังคับเปลี่ยนรหัสฝั่ง client (หลังเปลี่ยนสำเร็จ — กัน redirect วน)
  function markPasswordChanged() {
    if (user.value) user.value.must_change_password = false
  }

  function hasPermission(perm: string): boolean {
    if (isAdmin.value) return true
    return permissions.value.includes(perm)
  }

  function logout() {
    clearQueryCache()
    accessToken.value = null
    user.value = null
    localStorage.removeItem('access_token')
    localStorage.removeItem('user_id_str')
  }

  return {
    accessToken,
    user,
    isAuthenticated,
    displayName,
    roles,
    isAdmin,
    isCouncilAuthority,
    permissions,
    responsibilities,
    mustChangePassword,
    setToken,
    setUser,
    login,
    loadMe,
    markPasswordChanged,
    hasPermission,
    logout,
  }
})
