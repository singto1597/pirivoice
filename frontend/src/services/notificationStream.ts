import api from './api'
import type { UnreadCounts } from '@/types/notification'

// 📡 Notification stream (SSE) — badge อัปเดตทันทีโดยไม่ต้องรอ poll 30 วิ
//
// ⭐ **ทำไมใช้ `fetch` + `ReadableStream` ไม่ใช่ `EventSource`**
//    `EventSource` **ส่ง header เองไม่ได้** ⇒ ส่ง `Authorization: Bearer` ไม่ได้
//    ทางเลือกที่มีคือยัด token ไปใน query string — ซึ่งแปลว่า **JWT จะไปโผล่ใน
//    access log ของ Cloudflare/Traefik** (และใน Referer ถ้ามีลิงก์หลุด) เป็นการ
//    แลกที่ไม่คุ้มกับโค้ดที่ประหยัดได้ไม่กี่บรรทัด
//    ⇒ ใช้ `fetch` ที่ใส่ header ได้เหมือน request อื่นทุกตัวในโปรเจค
//    ต้นทุนคือต้องเขียน reconnect เอง — ซึ่ง **ต้องเขียนอยู่ดี** เพราะ `EventSource`
//    ต่อใหม่เองแบบไม่บอกอะไรเราเลย (ไม่รู้ว่า "ต่อติดแล้ว" เมื่อไหร่ ⇒ รีเซ็ต backoff ไม่ได้)
//
// ⭐ **ทำไมต้องมี `snapshot`:** การต่อใหม่ไม่รู้ว่าพลาดอะไรไประหว่างที่หลุด
//    ⇒ server ส่งยอดจริงมาให้ก่อนเสมอ · ไม่มีมัน = ผู้ใช้ที่เน็ตกระตุกจะค้างกับยอดเก่า
//    จนกว่า poll รอบถัดไป (กลับไปช้า 30 วิ = จุดที่ตั้งใจจะแก้นั่นเอง)

/** 1 event จากสตรีม — `event` ว่างได้ (SSE ถือเป็น `message`) */
export interface SseFrame {
  event: string
  data: string
}

export interface SseParser {
  /** ป้อน chunk ดิบ คืน frame ที่ "จบแล้ว" ใน chunk นี้ */
  push(chunk: string): SseFrame[]
  reset(): void
}

/**
 * 🚨 **ตัวแยก frame — จุดที่พังง่ายที่สุดของ SSE ทั้งโปรโตคอล**
 *
 * `chunk` ที่อ่านจาก network **ไม่ตรงกับ frame** — 1 frame อาจมาแบบครึ่ง ๆ
 * แล้วที่เหลือมาอีก chunk ⇒ ถ้าเขียน `chunk.split('\n\n')` ตรง ๆ จะ **ทำ frame หาย**
 * ตอนที่ TCP แตก packet (ซึ่งเกิดบ่อยบนมือถือ) ⇒ badge ไม่อัปเดตเป็นครั้งคราว
 * แบบที่ทำซ้ำยากมาก ⇒ ที่นี่เก็บ **เศษที่ยังไม่จบ** ไว้ข้าม chunk (`buf`)
 *
 * สเปกที่ต้องทำตาม (WHATWG HTML §9.2.4 "Server-sent events"):
 *   - frame จบด้วย **บรรทัดว่าง** · ยอมรับทั้ง `\n` และ `\r\n`
 *   - บรรทัดที่ขึ้นต้นด้วย `:` = **comment** → ข้าม (นี่คือ heartbeat ของเรา)
 *   - `field: value` — ถ้ามี space หลัง `:` **ตัดออกหนึ่งตัว** (ไม่ใช่ trim ทั้งหมด)
 *   - `data` หลายบรรทัดใน frame เดียว → ต่อด้วย `\n`
 */
export function createSseParser(): SseParser {
  let buf = ''
  return {
    push(chunk: string): SseFrame[] {
      // รวม CRLF/CR เป็น LF ก่อน — ทำที่นี่ที่เดียว ทำให้ตรรกะข้างล่างคิดแค่ '\n'
      buf += chunk.replace(/\r\n/g, '\n').replace(/\r/g, '\n')
      const parts = buf.split('\n\n')
      // ⭐ ชิ้นสุดท้ายยังไม่จบ (ไม่ลงท้ายด้วยบรรทัดว่าง) → เก็บไว้รอ chunk ถัดไป
      //    `pop()` คืน `undefined` เมื่อ array ว่าง — กันด้วย `?? ''`
      buf = parts.pop() ?? ''
      const frames: SseFrame[] = []
      for (const part of parts) {
        const frame = parseFrame(part)
        if (frame) frames.push(frame)
      }
      return frames
    },
    reset() {
      buf = ''
    },
  }
}

function parseFrame(raw: string): SseFrame | null {
  let event = ''
  const dataLines: string[] = []
  for (const line of raw.split('\n')) {
    // บรรทัดว่าง = ตัวคั่น (ไม่ควรเหลือมาถึงนี่) · `:` = comment (heartbeat `: ping`)
    if (!line || line.startsWith(':')) continue
    const idx = line.indexOf(':')
    const field = idx === -1 ? line : line.slice(0, idx)
    let value = idx === -1 ? '' : line.slice(idx + 1)
    if (value.startsWith(' ')) value = value.slice(1)
    if (field === 'event') event = value
    else if (field === 'data') dataLines.push(value)
  }
  // ไม่มี `data` เลย = ไม่ใช่ event ที่เราสนใจ (เช่น heartbeat ที่เรียงบรรทัดผิด)
  if (dataLines.length === 0) return null
  return { event, data: dataLines.join('\n') }
}

// ---------------- การเชื่อมต่อ ----------------

export type StreamState = 'connecting' | 'open' | 'reconnecting' | 'stopped'

export interface StreamHandlers {
  /** ยอดจริง ณ ตอนต่อ — ใช้แทนค่าที่มีอยู่ได้เลย (server ส่ง `{counts,total}` มาตรง ๆ) */
  onSnapshot: (counts: UnreadCounts) => void
  /** "มีอะไรใหม่ — ไปถามยอดเอง" (ไม่มีข้อมูลมาในตัวโดยเจตนา) */
  onPoke: () => void
  onStateChange?: (state: StreamState) => void
}

// backoff: 1 → 2 → 4 → 8 → 15 → 30 วิ (แล้วคาไว้ที่ 30)
const BACKOFF_MS = [1000, 2000, 4000, 8000, 15_000, 30_000]

/** base URL จาก `api` ตัวเดียวกันเสมอ — กันสองที่จะไม่ตรงกันวันหลัง */
function streamUrl(): string {
  const base = (api.defaults.baseURL || 'http://localhost:8000').replace(/\/+$/, '')
  return `${base}/api/notifications/stream`
}

function getToken(): string | null {
  return localStorage.getItem('access_token')
}

/**
 * เปิดสตรีมค้างไว้ — คืนฟังก์ชันสำหรับปิด
 *
 * ⚠️ **ต้องเรียกปิดตอน unmount/logout เสมอ** ไม่งั้นแท็บเดิมยังรับ event ของ
 *    ผู้ใช้คนก่อนต่อ (อาการเดียวกับบทเรียน WebAPK/site data ที่เจอในรอบ 1.5)
 */
export function openNotificationStream(handlers: StreamHandlers): () => void {
  let stopped = false
  let connected = false
  let retry = 0
  let controller: AbortController | null = null
  let timer: number | null = null

  const setState = (s: StreamState) => handlers.onStateChange?.(s)

  function clearTimer() {
    if (timer !== null) {
      window.clearTimeout(timer)
      timer = null
    }
  }

  function scheduleRetry() {
    if (stopped) return
    const delay = BACKOFF_MS[Math.min(retry, BACKOFF_MS.length - 1)]
    retry += 1
    setState('reconnecting')
    clearTimer()
    timer = window.setTimeout(() => {
      timer = null
      void connect()
    }, delay)
  }

  async function connect(): Promise<void> {
    if (stopped) return

    const token = getToken()
    if (!token) {
      // ยังไม่ล็อกอิน — ไม่ต้องยิงให้ได้ 401 (และไม่ต้อง retry)
      setState('stopped')
      stopped = true
      return
    }

    controller = new AbortController()
    setState(retry === 0 ? 'connecting' : 'reconnecting')

    try {
      const res = await fetch(streamUrl(), {
        method: 'GET',
        headers: { Accept: 'text/event-stream', Authorization: `Bearer ${token}` },
        signal: controller.signal,
        cache: 'no-store',
      })

      // 401 = token หมดอายุ/ถูกเพิกถอน → **หยุดถาวร ไม่ retry**
      //   เพราะ retry ด้วย token เดิมจะได้ 401 ทุกครั้ง (วนไม่จบ)
      //   ปล่อยให้ poll 30 วิ เป็นตัวจัดการ: มันยิงผ่าน axios ⇒ interceptor เห็น 401
      //   แล้วล้าง session + พาไปหน้า login ตามกลไกเดิม
      if (res.status === 401) {
        stopped = true
        setState('stopped')
        return
      }

      // 503 = เซิร์ฟเวอร์เต็ม (ผู้รับสตรีมเกินเพดาน) — **ไม่หยุดถาวร** เพราะมีวันว่าง
      //   ⇒ ตกไป scheduleRetry ตามปกติ (เพดาน backoff 30 วิ = ลองใหม่พอ ๆ กับ poll)
      if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`)

      // ✅ ต่อติดจริง — รีเซ็ต backoff **หลัง** ได้ response ไม่ใช่หลัง fetch สำเร็จ
      //    (fetch สำเร็จได้แม้ได้ 401/503)
      retry = 0
      connected = true
      setState('open')

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      const parser = createSseParser()

      while (!stopped) {
        const { value, done } = await reader.read()
        if (done) break // server ปิดสตรีม (ปกติคือ shutdown) → ต่อใหม่
        for (const frame of parser.push(decoder.decode(value, { stream: true }))) {
          if (frame.event === 'snapshot') {
            try {
              handlers.onSnapshot(JSON.parse(frame.data) as UnreadCounts)
            } catch {
              // frame เพี้ยน = ข้าม ไม่ให้สตรีมตายทั้งเส้น (ยอดจะมาถึงใน poll ถัดไป)
            }
          } else if (frame.event === 'poke') {
            handlers.onPoke()
          }
        }
      }
    } catch (e) {
      // AbortError = เราสั่งปิดเอง (close() หรือ reconnect) ไม่ใช่ความผิดพลาด
      if (stopped || (e as Error)?.name === 'AbortError') return
    }

    connected = false
    if (stopped) return
    scheduleRetry()
  }

  // 🔔 ตาข่ายชั้นสองของมือถือ: เบราว์เซอร์ **ระงับ connection ของแท็บที่อยู่เบื้องหลัง**
  //    (ล็อกจอ / สลับแอพ) ⇒ กลับมาเปิดใหม่แล้วสตรีมตายไปแล้ว ถ้ารอ backoff ปกติ
  //    ผู้ใช้จะไม่เห็น badge ขยับจนถึงรอบถัดไป (และถ้า backoff ค้างที่ 30 วิ ก็ช้าอีก)
  //    ⇒ พอแท็บกลับมา visible ให้ **ต่อใหม่ทันที** ไม่ต้องรอ timer
  function onVisible() {
    if (stopped || document.visibilityState !== 'visible') return
    if (connected) return
    retry = 0 // เริ่มนับ backoff ใหม่ — การที่เครื่องหลับไม่ควรถูกนับเป็น "ล้มเหลวซ้ำ"
    clearTimer()
    void connect()
  }
  document.addEventListener('visibilitychange', onVisible)

  void connect()

  return function close() {
    stopped = true
    clearTimer()
    controller?.abort()
    controller = null
    document.removeEventListener('visibilitychange', onVisible)
    setState('stopped')
  }
}
