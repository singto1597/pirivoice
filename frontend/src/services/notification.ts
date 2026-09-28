import api from './api'
import type {
  NotificationGroup,
  NotificationListResponse,
  UnreadCounts,
  MarkReadPayload,
  NotificationPreference,
  NotificationPreferencesResponse,
} from '@/types/notification'

// 🔔 Notification API — api interceptor unwrap response.data แล้ว (ดู services/api.ts)

export async function listNotifications(params: {
  group_type?: NotificationGroup
  unread_only?: boolean
  limit?: number
  offset?: number
} = {}): Promise<NotificationListResponse> {
  return (await api.get('/api/notifications', {
    params: {
      group_type: params.group_type || undefined,
      unread_only: params.unread_only || undefined,
      limit: params.limit ?? 50,
      offset: params.offset ?? 0,
    },
  })) as NotificationListResponse
}

export async function getUnreadCounts(): Promise<UnreadCounts> {
  return (await api.get('/api/notifications/unread-count')) as UnreadCounts
}

export async function markRead(payload: MarkReadPayload): Promise<{ updated: number }> {
  return (await api.post('/api/notifications/read', payload)) as { updated: number }
}

// ⚙️ ตั้งค่าการแจ้งเตือนรายกลุ่ม — server คืนครบทุกกลุ่มเสมอ (ไม่ต้อง zero-fill ฝั่งนี้)

export async function getNotificationPreferences(): Promise<NotificationPreferencesResponse> {
  return (await api.get('/api/notifications/preferences')) as NotificationPreferencesResponse
}

// PUT ไม่ใช่ PATCH — ส่ง "สถานะที่ต้องการ" ของกลุ่มที่แก้ และ endpoint idempotent
// ส่งเฉพาะกลุ่มที่เปลี่ยนก็ได้ (server เป็น partial update) — UI ส่งทีละกลุ่มตอนกด toggle
export async function updateNotificationPreferences(
  preferences: NotificationPreference[],
): Promise<NotificationPreferencesResponse> {
  return (await api.put('/api/notifications/preferences', {
    preferences,
  })) as NotificationPreferencesResponse
}
