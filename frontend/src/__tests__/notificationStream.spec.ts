/**
 * 🧪 `notificationStream.ts` — ตัวแยก SSE frame + การเชื่อมต่อ
 *
 * **ทำไมต้องมีเทสนี้:** งานนี้ทั้งงานมีเป้าหมายเดียวคือ *"badge ขยับทันทีโดยไม่ต้องรีเฟรช"*
 * ⇒ ถ้ามันพัง **จะไม่มีอาการให้เห็นเลย** — badge แค่กลับไปช้า 30 วิเหมือนก่อนทำ
 *   ซึ่งแยกไม่ออกจาก "ยังไม่ได้ deploy" หรือ "เน็ตช้า" ด้วยตาเปล่า
 *
 * ⭐ เทสที่สำคัญที่สุด 4 ตัว (ที่เหลือเป็นส่วนประกอบ):
 *   - `P2` **frame ถูกตัดครึ่งข้าม chunk** ← จุดที่พังง่ายที่สุดของ SSE ทั้งโปรโตคอล
 *     (บนมือถือ TCP แตก packet บ่อย ⇒ ถ้าพลาดจะได้ "badge ไม่อัปเดตเป็นครั้งคราว"
 *      ที่ทำซ้ำยากที่สุดในบรรดาอาการทั้งหมด)
 *   - `S4` **401 → หยุดถาวร ไม่ retry** (ไม่งั้นวนยิงด้วย token ที่ตายแล้วไม่จบ)
 *   - `S7` **close() ต้อง abort จริง** (ไม่งั้นแท็บเดิมรับ event ของผู้ใช้คนก่อน)
 *   - `S10` **กลับมา visible → ต่อใหม่ทันที** (เบราว์เซอร์มือถือฆ่า connection ของแท็บเบื้องหลัง)
 *
 * ⚠️ jsdom **ไม่มี** `fetch` จริงในความหมายที่เราต้องการ ⇒ stub ทั้งตัว
 *    และ **ไม่ใช้ `ReadableStream` ของ Node** — สร้าง `getReader()` ปลอมที่คืน chunk
 *    ตามลำดับที่กำหนด ⇒ เทสเป็น deterministic ไม่ผูกกับความเร็วของ runtime
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createSseParser, openNotificationStream } from '@/services/notificationStream'
import type { StreamState } from '@/services/notificationStream'
import { api } from '@/services/api'
import type { NotificationGroup, UnreadCounts } from '@/types/notification'

const TOKEN = 'tok-test-123'

/**
 * `UnreadCounts` ที่ **ครบทุกกลุ่ม** — เหมือนที่ server ส่งจริง
 *
 * ⚠️ **ทำไมไม่ผ่อน type เป็น `Partial<...>` เพื่อให้เทสเขียนสั้นลง:**
 *    `UnreadCounts.counts` เป็น `Record<NotificationGroup, number>` เต็มรูป **โดยเจตนา**
 *    เพราะ server zero-fill ทุกกลุ่มเสมอ (`notification_service.get_unread_counts`)
 *    ⇒ payload ที่ขาดกลุ่มคือสิ่งที่ server **ไม่มีวันส่ง** · ถ้าผ่อน type บั๊กจริงอย่าง
 *    "อ่าน `counts.board` ทั้งที่ server ไม่ได้ส่ง `board` มา" จะหลุดผ่านเทสไป production
 *    ⇒ **เทสต้องสร้างให้ครบ ไม่ใช่ผ่อน type**
 *
 * เขียนชื่อกลุ่มตรง ๆ ที่นี่ได้ (ต่างจากโค้ด production ที่ `types/notification.ts`
 * ห้ามประกาศซ้ำ) เพราะ TypeScript **บังคับ** ให้ตรงกัน: เพิ่มกลุ่มใหม่ใน
 * `NotificationGroup` แล้วบรรทัดนี้ compile ไม่ผ่านทันที ⇒ drift เกิดขึ้นไม่ได้
 */
function countsOf(over: Partial<Record<NotificationGroup, number>> = {}): UnreadCounts {
  const counts: Record<NotificationGroup, number> = {
    issue_mine: 0,
    issue_received: 0,
    board: 0,
    report: 0,
    ...over,
  }
  return { counts, total: Object.values(counts).reduce((a, b) => a + b, 0) }
}

// ---------------- เครื่องมือช่วย ----------------

/**
 * `Response` ปลอมที่ส่ง chunk ตามลำดับ
 *
 * `holdOpen: true` = หลังส่ง chunk ครบ **ไม่ปิดสตรีม** (ค้างที่ `read()` ตลอดไป)
 * ใช้เพื่อจำลอง "สตรีมกำลังเปิดอยู่จริง" ซึ่งต่างจาก "server ปิดสตรีม" ที่ต้อง
 * นำไปสู่การต่อใหม่คนละทาง
 */
function fakeResponse({
  status = 200,
  chunks = [] as string[],
  holdOpen = false,
}: { status?: number; chunks?: string[]; holdOpen?: boolean } = {}) {
  let i = 0
  const encoder = new TextEncoder()
  return {
    status,
    ok: status >= 200 && status < 300,
    body: {
      getReader: () => ({
        read: async () => {
          if (i < chunks.length) return { value: encoder.encode(chunks[i++]), done: false }
          if (holdOpen) return new Promise<never>(() => {}) // ค้าง = สตรีมยังเปิด
          return { value: undefined, done: true }
        },
      }),
    },
  } as unknown as Response
}

/** ตอบ `n` ครั้งแรกด้วย response ที่ให้มา แล้วครั้งต่อ ๆ ไปค้างไว้ (กัน retry วนไม่จบ) */
function stubFetch(...responses: (Response | Error)[]) {
  fetchMock.mockReset()
  for (const r of responses) {
    if (r instanceof Error) fetchMock.mockRejectedValueOnce(r)
    else fetchMock.mockResolvedValueOnce(r)
  }
  fetchMock.mockImplementation(() => new Promise<Response>(() => {}))
}

/**
 * ปล่อย microtask ให้ครบสาย `fetch → getReader → read → decode → handler`
 *
 * ⚠️ ใช้ **fake timers** อยู่ ⇒ `await new Promise(r => setTimeout(r, 0))` จะค้าง
 *    (เวลาไม่เดินเอง) ⇒ ต้องไล่ `Promise.resolve()` เอา
 */
async function flush(times = 25) {
  for (let i = 0; i < times; i++) await Promise.resolve()
}

let fetchMock: ReturnType<typeof vi.fn<typeof fetch>>
let close: (() => void) | null = null
let states: StreamState[]

/**
 * เปิดสตรีมแล้วเก็บตัวปิดไว้ให้ `afterEach` เก็บกวาด (ไม่งั้น listener ค้างข้ามเทส)
 *
 * ⚠️ คืน `counter` เป็น **ออบเจ็กต์ที่มีชีวิต** ไม่ใช่ `pokes: number` ที่ก็อปค่าตอน return
 *    — เทสต์อ่านมัน *หลัง* flush ⇒ ถ้าคืนตัวเลขตรง ๆ จะได้ 0 ตลอด (เทสต์ล้มด้วยเหตุผล
 *    ของการทดสอบเอง ไม่ใช่ของโค้ด)
 */
function open(overrides: Partial<Parameters<typeof openNotificationStream>[0]> = {}): {
  snapshots: UnreadCounts[]
  counter: { pokes: number }
} {
  const snapshots: UnreadCounts[] = []
  const counter = { pokes: 0 }
  close = openNotificationStream({
    onSnapshot: (c) => snapshots.push(c),
    onPoke: () => {
      counter.pokes += 1
    },
    onStateChange: (s) => states.push(s),
    ...overrides,
  })
  return { snapshots, counter }
}

beforeEach(() => {
  fetchMock = vi.fn<typeof fetch>()
  vi.stubGlobal('fetch', fetchMock)
  vi.useFakeTimers()
  localStorage.clear()
  localStorage.setItem('access_token', TOKEN)
  states = []
  close = null
})

afterEach(() => {
  close?.()
  close = null
  vi.useRealTimers()
  vi.unstubAllGlobals()
  localStorage.clear()
})

// ============================================================
// 1) createSseParser — ตัวแยก frame (pure function ⇒ เทสตรง ๆ ได้)
// ============================================================

describe('createSseParser', () => {
  it('P1 — 1 chunk ที่มี frame จบสมบูรณ์ 1 อัน', () => {
    const p = createSseParser()
    expect(p.push('event: snapshot\ndata: {"total":3}\n\n')).toEqual([
      { event: 'snapshot', data: '{"total":3}' },
    ])
  })

  it('P2 — ★ frame ถูกตัดครึ่งข้าม chunk (หัวใจของงานนี้)', () => {
    const p = createSseParser()
    // chunk แรกยังไม่ลงท้ายด้วยบรรทัดว่าง ⇒ ต้องไม่คืนอะไร
    expect(p.push('event: poke\nda')).toEqual([])
    // chunk ที่สองมาปิด frame
    expect(p.push('ta: {}\n\n')).toEqual([{ event: 'poke', data: '{}' }])
  })

  it('P3 — ★ ตัวอักษรละ chunk (สถานการณ์ที่เลวร้ายที่สุด)', () => {
    const p = createSseParser()
    const raw = 'event: snapshot\ndata: {"counts":{},"total":7}\n\n'
    const frames = raw.split('').flatMap((ch) => p.push(ch))
    expect(frames).toEqual([{ event: 'snapshot', data: '{"counts":{},"total":7}' }])
  })

  it('P4 — 1 chunk ที่มี 2 frame → คืน 2 อันตามลำดับ', () => {
    const p = createSseParser()
    expect(p.push(': ping\n\nevent: poke\ndata: {}\n\n')).toEqual([{ event: 'poke', data: '{}' }])
  })

  it('P5 — heartbeat (`: ping`) ถูกข้าม ไม่กลายเป็น event', () => {
    const p = createSseParser()
    expect(p.push(': ping\n\n')).toEqual([])
    expect(p.push(':any comment\n\n')).toEqual([])
  })

  it('P6 — CRLF ก็ต้องใช้ได้ (WHATWG §9.2.4 ยอมรับทั้ง \\n และ \\r\\n)', () => {
    const p = createSseParser()
    expect(p.push('event: poke\r\ndata: {}\r\n\r\n')).toEqual([{ event: 'poke', data: '{}' }])
  })

  it('P6b — CRLF ที่ถูกตัดกลาง frame (บรรทัดแรกกับที่เหลือคนละ chunk)', () => {
    const p = createSseParser()
    // ⚠️ ห้ามตัดระหว่าง \r กับ \n — parser รวม CRLF เป็น LF **ต่อ chunk**
    //    ⇒ เศษ '\r' ค้างท้าย chunk จะถูกแปลงเป็น '\n' ทันที ซึ่งถูกต้อง
    //    (บรรทัดว่างจะเกิดตอน '\n' ของ chunk ถัดไปมาถึง ⇒ ยังนับ frame ถูก)
    expect(p.push('event: poke\r\n')).toEqual([])
    expect(p.push('data: {}\r\n\r\n')).toEqual([{ event: 'poke', data: '{}' }])
  })

  it('P7 — `data` หลายบรรทัดใน frame เดียวต่อด้วย \\n', () => {
    const p = createSseParser()
    expect(p.push('event: x\ndata: a\ndata: b\n\n')).toEqual([{ event: 'x', data: 'a\nb' }])
  })

  it('P8 — ตัด space หลัง `:` แค่ตัวเดียว (ไม่ใช่ trim ทั้งหมด)', () => {
    const p = createSseParser()
    // หลัง ':' มี 2 space → ต้องเหลือ 1 · ถ้าใช้ `.trim()` จะเหลือ 0 ซึ่งผิดสเปก
    expect(p.push('data:  นำหน้า\n\n')).toEqual([{ event: '', data: ' นำหน้า' }])
  })

  it('P9 — frame ที่ไม่มี data เลย → ไม่คืน (ไม่ใช่ event ที่เราสนใจ)', () => {
    const p = createSseParser()
    expect(p.push('event: ping\n\n')).toEqual([])
    expect(p.push('id: 42\n\n')).toEqual([])
  })

  it('P10 — `reset()` ทิ้งเศษที่ค้างอยู่', () => {
    const p = createSseParser()
    expect(p.push('event: poke\nda')).toEqual([])
    p.reset()
    // เศษเก่าหาย ⇒ chunk นี้ไม่ปิด frame ใด ๆ
    expect(p.push('ta: {}\n\n')).toEqual([])
  })

  it('P11 — `event` ที่ไม่ระบุ → คืน event เป็นสตริงว่าง (ไม่ใช่ undefined)', () => {
    const p = createSseParser()
    expect(p.push('data: hi\n\n')).toEqual([{ event: '', data: 'hi' }])
  })
})

// ============================================================
// 2) openNotificationStream — การเชื่อมต่อ
// ============================================================

describe('openNotificationStream', () => {
  it('S1 — ส่ง Bearer token ทาง header และ **ไม่** เอา token ไปไว้ใน URL', () => {
    stubFetch(fakeResponse({ holdOpen: true }))
    open()

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    // ⭐ token ต้องไม่โผล่ใน URL — นี่คือเหตุผลทั้งหมดที่เลือก fetch แทน EventSource
    //    (query string จะไปอยู่ใน access log ของ Cloudflare/Traefik)
    expect(url).not.toContain(TOKEN)
    expect(url.endsWith('/api/notifications/stream')).toBe(true)
    expect((init.headers as Record<string, string>).Authorization).toBe(`Bearer ${TOKEN}`)
    expect(init.signal).toBeInstanceOf(AbortSignal)
  })

  it('S2 — `snapshot` → `onSnapshot` ได้ `{counts,total}` ที่ parse แล้ว', async () => {
    const counts = countsOf({ board: 2 })
    stubFetch(fakeResponse({ chunks: [`event: snapshot\ndata: ${JSON.stringify(counts)}\n\n`], holdOpen: true }))
    const { snapshots } = open()
    await flush()

    expect(snapshots).toEqual([counts])
  })

  it('S3 — `poke` → `onPoke` (ไม่พาข้อมูลมา โดยเจตนา)', async () => {
    stubFetch(fakeResponse({ chunks: ['event: poke\ndata: {}\n\n'], holdOpen: true }))
    const s = open()
    await flush()

    expect(s.counter.pokes).toBe(1)
    expect(s.snapshots).toEqual([])
  })

  it('S3b — frame ที่ถูกตัดกลางทางในสตรีมจริง ต้องยังถึง handler', async () => {
    const counts = countsOf({ report: 1 })
    stubFetch(
      fakeResponse({
        chunks: ['event: snap', `shot\ndata: ${JSON.stringify(counts)}\n`, '\n'],
        holdOpen: true,
      }),
    )
    const { snapshots } = open()
    await flush()

    expect(snapshots).toEqual([counts])
  })

  it('S4 — ★ 401 → หยุดถาวร **ไม่ retry** (retry ด้วย token เดิมจะได้ 401 ทุกครั้ง)', async () => {
    stubFetch(fakeResponse({ status: 401 }))
    open()
    await flush()

    expect(fetchMock).toHaveBeenCalledTimes(1)
    // ปล่อยเวลาไปไกลเกิน backoff สูงสุด (30 วิ) — ต้องยังไม่ยิงซ้ำ
    await vi.advanceTimersByTimeAsync(60_000)
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(states[states.length - 1]).toBe('stopped')
  })

  it('S5 — 503 → **ไม่** หยุดถาวร แต่ retry ตาม backoff (เพดานมีวันว่าง)', async () => {
    stubFetch(fakeResponse({ status: 503 }))
    open()
    await flush()
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(states[states.length - 1]).toBe('reconnecting')

    await vi.advanceTimersByTimeAsync(1_000) // backoff ตัวแรก = 1 วิ
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('S6 — ไม่มี token → ไม่ยิง fetch เลย และหยุดทันที', async () => {
    localStorage.clear()
    open()
    await flush()

    expect(fetchMock).not.toHaveBeenCalled()
    expect(states).toEqual(['stopped'])
  })

  it('S7 — ★ `close()` ต้อง abort จริง + ไปสถานะ stopped + ไม่ต่อใหม่', async () => {
    stubFetch(fakeResponse({ holdOpen: true }))
    open()
    await flush()
    expect(fetchMock).toHaveBeenCalledTimes(1)

    // แกะเป็น tuple แบบเดียวกับ S1/S10 — `mock.calls[0][1]` ตรง ๆ ไม่ผ่าน type check
    // (`noUncheckedIndexedAccess` มองว่าอาจเป็น undefined) และการ `as` ที่ตัว index
    // ไม่ช่วย เพราะปัญหาอยู่ที่ตัว index ไม่ใช่ตัว type ปลายทาง
    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    const signal = init.signal as AbortSignal
    expect(signal.aborted).toBe(false)

    close?.()
    expect(signal.aborted).toBe(true)
    expect(states[states.length - 1]).toBe('stopped')

    await vi.advanceTimersByTimeAsync(60_000)
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('S8 — ★ snapshot JSON เพี้ยน → ไม่ throw และไม่เรียก `onSnapshot` (สตรีมต้องไม่ตาย)', async () => {
    stubFetch(fakeResponse({ chunks: ['event: snapshot\ndata: {ไม่ใช่ json\n\n'], holdOpen: true }))
    const { snapshots } = open()
    await flush()

    expect(snapshots).toEqual([])
    // ⭐ ยังต่ออยู่ — ไม่ได้ถูก tear down เพราะ frame เพี้ยนหนึ่งอัน
    await vi.advanceTimersByTimeAsync(60_000)
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('S9 — server ปิดสตรีม → ต่อใหม่ได้ และ **รีเซ็ต backoff** เมื่อต่อติด', async () => {
    stubFetch(
      fakeResponse({ chunks: [], holdOpen: false }), // จบทันที = server ปิด
      fakeResponse({ holdOpen: true }), // รอบสองต่อติดค้างไว้
    )
    open()
    await flush()
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(states[states.length - 1]).toBe('reconnecting')

    await vi.advanceTimersByTimeAsync(1_000)
    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(states[states.length - 1]).toBe('open')
  })

  it('S9b — ล้มเหลวซ้ำ → backoff **เพิ่มขึ้น** (1 → 2 → 4 วิ ไม่ใช่ 1 วิทุกครั้ง)', async () => {
    stubFetch(
      fakeResponse({ status: 500 }),
      fakeResponse({ status: 500 }),
      fakeResponse({ status: 500 }),
      fakeResponse({ status: 500 }),
    )
    open()
    await flush()

    await vi.advanceTimersByTimeAsync(1_000)
    expect(fetchMock).toHaveBeenCalledTimes(2)

    // ⭐ ช่วง 1 วิถัดไป **ต้องไม่ยิง** — เพราะ backoff รอบนี้คือ 2 วิ
    await vi.advanceTimersByTimeAsync(1_000)
    expect(fetchMock).toHaveBeenCalledTimes(2)

    await vi.advanceTimersByTimeAsync(1_000)
    expect(fetchMock).toHaveBeenCalledTimes(3)
  })

  it('S10 — ★ กลับมา visible → ต่อใหม่ทันที ไม่ต้องรอ timer (มือถือฆ่า connection ของแท็บเบื้องหลัง)', async () => {
    stubFetch(fakeResponse({ chunks: [] }), fakeResponse({ holdOpen: true }))
    open()
    await flush()
    expect(fetchMock).toHaveBeenCalledTimes(1)
    // ตอนนี้มี timer ของ backoff ค้างอยู่ (1 วิ) — ยังไม่ทันยิง

    document.dispatchEvent(new Event('visibilitychange'))
    await flush()

    // ⭐ ต้องยิงทันทีโดย **ไม่ได้ advance เวลาเลย**
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('S11 — `visibilitychange` ตอนที่ยังต่ออยู่ → ไม่ยิงซ้ำ (ไม่มีสตรีมซ้อน)', async () => {
    stubFetch(fakeResponse({ holdOpen: true }))
    open()
    await flush()
    expect(fetchMock).toHaveBeenCalledTimes(1)

    document.dispatchEvent(new Event('visibilitychange'))
    await flush()

    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('S12 — ยิงไปที่ base URL เดียวกับ `api` (ไม่ประกาศซ้ำสองที่)', async () => {
    stubFetch(fakeResponse({ holdOpen: true }))
    open()

    const [url] = fetchMock.mock.calls[0] as unknown as [string]
    const base = (api.defaults.baseURL || '').replace(/\/+$/, '')
    expect(url).toBe(`${base}/api/notifications/stream`)
  })

  it('S13 — `close()` เรียกซ้ำได้ และหลังปิดแล้ว visibilitychange ไม่ทำอะไร', async () => {
    stubFetch(fakeResponse({ holdOpen: true }))
    open()
    await flush()

    close?.()
    close?.()
    document.dispatchEvent(new Event('visibilitychange'))
    await flush()

    expect(fetchMock).toHaveBeenCalledTimes(1)
  })
})
