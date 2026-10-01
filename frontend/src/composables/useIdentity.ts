// 🪪 ตัวตนของผู้ใช้ที่ล็อกอิน — ชื่อ/บทบาท/ตัวอักษร avatar
//
// แยกออกจาก `MainLayout.vue` เพราะ **หน้าแรกและหน้า "เพิ่มเติม" ใช้ทั้งคู่**
// (เดิม copy กันอยู่ 2 ที่ ⇒ แก้ที่หนึ่งแล้วอีกที่ไม่ตาม)

import { computed } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { avatarCharOf } from '@/utils/avatar'
import { ROLE_LABELS } from '@/constants/roles'

export function useIdentity() {
  const authStore = useAuthStore()

  const displayName = computed(() => authStore.displayName)

  // ตัวอักษรตัวแรกของชื่อจริง (first_name) → avatar — ไม่เอาคำนำหน้า/ชื่อเล่น
  const avatarChar = computed(() =>
    avatarCharOf(authStore.user?.first_name || authStore.displayName),
  )

  const roleLabel = computed(() => {
    const first = authStore.roles[0]
    if (!first) return 'นักเรียน'
    return ROLE_LABELS[first.role || ''] || first.role || 'นักเรียน'
  })

  // 📍 ตำแหน่ง/ห้องสำหรับทักทาย
  const roleLine = computed(() => {
    const first = authStore.roles[0]
    if (!first) return roleLabel.value
    if (first.room_name) return `${roleLabel.value} · ${first.room_name}`
    if (first.level) return `${roleLabel.value} · ${first.level}`
    return roleLabel.value
  })

  return { displayName, avatarChar, roleLabel, roleLine }
}
