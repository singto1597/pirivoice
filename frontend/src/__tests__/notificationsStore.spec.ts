/**
 * 🧪 `stores/notifications.ts` — ส่วนที่ต่อ **stream (SSE) เข้ากับ badge**
 *
 * **ทำไมต้องมีเทสนี้:** งานนี้มีเป้าหมายเดียวคือ *"badge ขยับทันทีโดยไม่ต้องรีเฟรช"*
 * และตัวเชื่อมอยู่ที่ store นี้ ⇒ ถ้าต่อสายผิด จะไม่มีอาการให้เห็นเลย
 * (badge แค่กลับไปช้า 30 วิ = แยกไม่ออกจาก "ยังไม่ deploy")
 *
 * ⭐ สิ่งที่เทสนี้พิสูจน์ (เรียงตามความสำคัญ):
 *   - `S3` **poke ที่ซ้อนกันถูกรวมเป็น fetch เดียว** — fanout ครั้งเดียวยิงหลาย poke
 *     ได้ (ผู้ใช้หลายแท็บ) · ถ้าไม่รวม จะยิงถามยอดถี่เท่าจำนวนแท็บทุกครั้ง
 *   - `S6` **`stopStream()` ต้องยกเลิก poke ที่ค้างอยู่** — ไม่งั้นมี fetch วิ่งออกไป
 *     *หลัง* ผู้ใช้ออกจากระบบแล้ว (= ยิงด้วย token ที่ถูกล้างไปแล้ว + ทำงานเกินอายุ)
 *   - `S2` **snapshot ไม่ต้องยิงถามซ้ำ** — payload คือ `{counts,total}` ครบอยู่แล้ว
 *     (ถ้าเผลอไป fetchCounts() ต่อ จะได้ request เกิน 1 ครั้งต่อการต่อ 1 ครั้ง)
 *
 * ⚠️ mock ทั้งสองโมดูลที่ store พึ่ง (`notification` = API, `notificationStream` = สตรีม)
 *    ⇒ เทสนี้เป็น **unit test ของตรรกะการต่อสาย** ไม่ใช่ integration
 *    (พฤติกรรมจริงของ fetch/SSE อยู่ใน `notificationStream.spec.ts`)
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import type { StreamHandlers } from '@/services/notificationStream'
import type { MarkReadPayload, NotificationGroup, UnreadCounts } from '@/types/notification'

/**
 * ⚠️ ต้องใช้ `vi.hoisted` — `vi.mock` ถูก **ยกขึ้นบนสุดของไฟล์** ก่อน `const` ปกติ
 *    ⇒ ถ้าอ้างตัวแปรที่ประกาศด้วย `const` ข้างล่าง จะได้
 *    `ReferenceError: Cannot access '...' before initialization`
 *
 * ⚠️ **ต้องใส่ type parameter ให้ `vi.fn<...>()` ทุกตัว** (กฎ `require-mock-type-parameters`)
 *    และไม่ใช่แค่เพื่อให้ lint ผ่าน — mock ที่ไม่ระบุ type จะรับอะไรก็ได้ ⇒
 *    `mockResolvedValue({ counts: { board: 4 }, total: 4 })` (ยอดไม่ครบกลุ่ม) จะผ่านฉลุย
 *    ⇒ เทสจะเข้ารหัส payload ที่ server ไม่มีวันส่ง แล้วไม่มีใครรู้
 *    พอระบุ type จริง การโกหกแบบนั้นจะกลายเป็น compile error ทันที
 *    (type เท่านั้นที่อ้างใน `vi.hoisted` ได้ — ถูก erase ตอน compile จึงไม่ชน hoisting)
 */
const mocks = vi.hoisted(() => ({
  getUnreadCounts: vi.fn<() => Promise<UnreadCounts>>(),
  markRead: vi.fn<(payload: MarkReadPayload) => Promise<{ updated: number }>>(),
  openNotificationStream: vi.fn<(handlers: StreamHandlers) => () => void>(),
  close: vi.fn<() => void>(),
  /** handlers ที่ store ส่งเข้ามา — เทสจะได้ "พูดกับสตรีม" จากฝั่ง server จำลอง */
  handlers: { current: null as StreamHandlers | null },
}))

vi.mock('@/services/notification', () => ({
  getUnreadCounts: mocks.getUnreadCounts,
  markRead: mocks.markRead,
}))

vi.mock('@/services/notificationStream', () => ({
  openNotificationStream: mocks.openNotificationStream,
}))

// import **หลัง** vi.mock เท่านั้น (hoisting จัดการให้อยู่แล้ว แต่เขียนให้อ่านง่าย)
import { useNotificationsStore } from '@/stores/notifications'

const POKE_DEBOUNCE_MS = 300

/**
 * `UnreadCounts` ที่ **ครบทุกกลุ่ม** — เหมือนที่ server ส่งจริง
 *
 * ⚠️ `UnreadCounts.counts` เป็น `Record<NotificationGroup, number>` เต็มรูป **โดยเจตนา**
 *    เพราะ server zero-fill ทุกกลุ่ม (`notification_service.get_unread_counts`)
 *    ⇒ payload ที่ขาดกลุ่มคือสิ่งที่ server ไม่มีวันส่ง · **ห้ามผ่อน type ให้เทสเขียนสั้นลง**
 *    (ผ่อนแล้วบั๊ก "อ่านกลุ่มที่ server ไม่ส่ง" จะหลุดถึง production)
 *
 * เขียนชื่อกลุ่มตรง ๆ ที่นี่ได้เพราะ TypeScript บังคับให้ตรง: เพิ่มกลุ่มใหม่ใน
 * `NotificationGroup` แล้วบรรทัดนี้ compile ไม่ผ่านทันที ⇒ drift เกิดไม่ได้
 */
function countsOf(over: Partial<Record<NotificationGroup, number>> = {}): UnreadCounts {
  const counts: Record<NotificationGroup, number> = {
    issue_mine: 0,
    issue_received: 0,
    board: 0,
    report: 0,
    announcement: 0,
    event: 0,
    ...over,
  }
  return { counts, total: Object.values(counts).reduce((a, b) => a + b, 0) }
}

/** ยิง poke จาก "server" จำลอง เข้า handler ที่ store ลงทะเบียนไว้ */
function poke() {
  mocks.handlers.current?.onPoke()
}

beforeEach(() => {
  setActivePinia(createPinia())
  vi.useFakeTimers()

  mocks.getUnreadCounts.mockReset().mockResolvedValue(countsOf({ board: 4 }))
  mocks.markRead.mockReset().mockResolvedValue({ updated: 1 })
  mocks.close.mockReset()
  mocks.handlers.current = null
  mocks.openNotificationStream.mockReset().mockImplementation((h: StreamHandlers) => {
    mocks.handlers.current = h
    return mocks.close
  })
})

afterEach(() => {
  vi.useRealTimers()
})

describe('notifications store — stream (SSE)', () => {
  it('S1 — `startStream()` เปิดสตรีมพร้อม handler ครบทั้งสาม', () => {
    const store = useNotificationsStore()
    store.startStream()

    expect(mocks.openNotificationStream).toHaveBeenCalledTimes(1)
    const h = mocks.handlers.current
    expect(typeof h?.onSnapshot).toBe('function')
    expect(typeof h?.onPoke).toBe('function')
    expect(typeof h?.onStateChange).toBe('function')
  })

  it('S2 — snapshot ถูกใช้ตรง ๆ **ไม่ยิงถามซ้ำ** (payload มี `{counts,total}` ครบ)', () => {
    const store = useNotificationsStore()
    store.startStream()

    const snapshot = countsOf({ report: 2, board: 1 })
    mocks.handlers.current?.onSnapshot(snapshot)

    // เทียบทั้งก้อน ไม่ใช่แค่สองกลุ่มที่มีค่า — ยืนยันด้วยว่ากลุ่มที่เป็น 0 ไม่ถูกตัดทิ้ง
    // (server ส่งมาครบ ⇒ store ต้องเก็บครบ ไม่งั้นตัวเลขบนเมนูจะหายไปเฉย ๆ)
    expect(store.counts).toEqual(snapshot.counts)
    expect(store.total).toBe(3)
    // ⭐ 0 ครั้ง — ถ้าที่นี่เป็น 1 แปลว่าเรายิงถามยอดที่เพิ่งได้มาแล้ว (เสียเปล่าทุกครั้งที่ต่อ)
    expect(mocks.getUnreadCounts).not.toHaveBeenCalled()
  })

  it('S3 — ★ poke 3 ครั้งในหน้าต่างเดียว → ยิงถามยอด **ครั้งเดียว**', async () => {
    const store = useNotificationsStore()
    store.startStream()

    poke()
    poke()
    poke()
    // ยังไม่ถึงกำหนด — ต้องยังไม่ยิง
    expect(mocks.getUnreadCounts).not.toHaveBeenCalled()

    await vi.advanceTimersByTimeAsync(POKE_DEBOUNCE_MS)
    expect(mocks.getUnreadCounts).toHaveBeenCalledTimes(1)
    expect(store.total).toBe(4)
  })

  it('S4 — poke รอบใหม่หลังพ้นหน้าต่าง → ยิงอีกครั้ง (ไม่ใช่รวมตลอดไป)', async () => {
    const store = useNotificationsStore()
    store.startStream()

    poke()
    await vi.advanceTimersByTimeAsync(POKE_DEBOUNCE_MS)
    expect(mocks.getUnreadCounts).toHaveBeenCalledTimes(1)

    poke()
    await vi.advanceTimersByTimeAsync(POKE_DEBOUNCE_MS)
    expect(mocks.getUnreadCounts).toHaveBeenCalledTimes(2)
  })

  it('S5 — poke ต้อง **ไม่เลื่อนเวลา** ของ poke แรก (coalesce ไม่ใช่ debounce)', async () => {
    const store = useNotificationsStore()
    store.startStream()

    poke()
    // ไล่ poke ทุก 100ms — ถ้าเป็น debounce แบบเลื่อนเวลา จะไม่มีวันยิงสักที
    for (let i = 0; i < 5; i++) {
      await vi.advanceTimersByTimeAsync(100)
      poke()
    }
    await vi.advanceTimersByTimeAsync(POKE_DEBOUNCE_MS)

    expect(mocks.getUnreadCounts).toHaveBeenCalled()
  })

  it('S6 — ★ `stopStream()` ยกเลิก poke ที่ค้างอยู่ (ต้องไม่มี fetch หลังออกจากระบบ)', async () => {
    const store = useNotificationsStore()
    store.startStream()
    poke()

    store.stopStream()
    await vi.advanceTimersByTimeAsync(POKE_DEBOUNCE_MS * 10)

    expect(mocks.close).toHaveBeenCalledTimes(1)
    // ⭐ 0 ครั้ง — poke ที่ค้างถูก `clearTimeout` ทิ้งไปพร้อมสตรีม
    expect(mocks.getUnreadCounts).not.toHaveBeenCalled()
    expect(store.streamState).toBe('stopped')
  })

  it('S7 — `startStream()` ซ้ำ → เปิดสตรีมเส้นเดียว (idempotent)', () => {
    const store = useNotificationsStore()
    store.startStream()
    store.startStream()
    store.startStream()

    expect(mocks.openNotificationStream).toHaveBeenCalledTimes(1)
  })

  it('S8 — หลัง `stopStream()` แล้ว `startStream()` ใหม่ → เปิดได้อีก (ไม่ค้างสถานะปิด)', () => {
    const store = useNotificationsStore()
    store.startStream()
    store.stopStream()
    store.startStream()

    expect(mocks.openNotificationStream).toHaveBeenCalledTimes(2)
  })

  it('S9 — `streamState` สะท้อนสถานะจริงที่สตรีมรายงาน', () => {
    const store = useNotificationsStore()
    store.startStream()
    expect(store.streamState).toBe('stopped') // ค่าเริ่มต้นก่อนสตรีมรายงาน

    mocks.handlers.current?.onStateChange?.('connecting')
    expect(store.streamState).toBe('connecting')

    mocks.handlers.current?.onStateChange?.('open')
    expect(store.streamState).toBe('open')

    mocks.handlers.current?.onStateChange?.('reconnecting')
    expect(store.streamState).toBe('reconnecting')
  })

  it('S10 — ถามยอดไม่สำเร็จ → กลืน ไม่ทำให้สตรีมตาย และไม่เกิด unhandled rejection', async () => {
    mocks.getUnreadCounts.mockRejectedValue(new Error('network'))
    const store = useNotificationsStore()
    store.startStream()

    poke()
    // ⚠️ vitest ล้มเทสเมื่อมี unhandled rejection ⇒ การที่เทสนี้ผ่านคือคำยืนยันว่า
    //    `.catch()` ใน `onPoke` ทำงาน (ยอดจะถูกเก็บให้เองใน poll รอบถัดไป)
    await vi.advanceTimersByTimeAsync(POKE_DEBOUNCE_MS)
    expect(mocks.getUnreadCounts).toHaveBeenCalledTimes(1)
    // ⭐ สตรีม **ไม่** ถูกปิดเพราะถามยอดพลาด — `close` คือของที่ `openNotificationStream`
    //    คืนมา ⇒ ถ้าถูกเรียก = store ตัดสินใจทิ้งสตรีม (ซึ่งผิด: เน็ตกระตุกครั้งเดียว
    //    ไม่ควรทำให้ badge หยุดอัปเดตไปตลอด)
    expect(mocks.close).not.toHaveBeenCalled()

    // และ poke ถัดไปยังทำงานได้ = สตรีมยังมีชีวิตจริง
    mocks.getUnreadCounts.mockResolvedValue(countsOf({ board: 1 }))
    poke()
    await vi.advanceTimersByTimeAsync(POKE_DEBOUNCE_MS)
    expect(mocks.getUnreadCounts).toHaveBeenCalledTimes(2)
    expect(store.total).toBe(1)
  })

  it('S11 — poll 30 วิ ยังทำงานอยู่คู่กับ stream (ตาข่ายชั้นสองห้ามถอด)', async () => {
    const store = useNotificationsStore()
    store.startStream()
    store.startPolling()

    // รอบแรกยิงทันที (void) — ให้เวลาหนึ่ง tick
    await vi.advanceTimersByTimeAsync(0)
    expect(mocks.getUnreadCounts).toHaveBeenCalled()

    mocks.getUnreadCounts.mockClear()
    await vi.advanceTimersByTimeAsync(30_000)
    expect(mocks.getUnreadCounts).toHaveBeenCalledTimes(1)

    store.stopPolling()
  })
})
