/**
 * 🧪 `services/queryCache.ts` + interceptor ใน `services/api.ts` — stale-while-revalidate
 *
 * **ทำไมต้องมีเทสนี้:** พฤติกรรม "จำค่าเก่า" ทั้งหมดเกิดจากโค้ด 3 บรรทัดใน `api.ts`
 * (แทน `config.adapter` ตอน hit · `reconcile` ตอน revalidate · คืน proxy ตัวที่เก็บ)
 * ซึ่ง **ถ้าใครเผลอแก้ให้คืน `response.data` ดิบ ๆ ทุกอย่างยังคอมไพล์ผ่านและหน้าจอยัง
 * แสดงผลได้ปกติ** — แต่จะไม่มีวันอัปเดตเบื้องหลังอีก ⇒ เทสนี้ตรึง identity/พฤติกรรมไว้
 *
 * ⚠️ ทดสอบผ่าน adapter จริงของ axios (ไม่เรียก handler ตรง ๆ) เพื่อให้ transform +
 *    interceptor ทำงานเหมือนของจริง
 *
 * ⚠️ cache เป็น **สถานะระดับโมดูล** ⇒ ทุกเทสต์ต้อง `clearQueryCache()` ใน `beforeEach`
 *    ไม่งั้น entry จากเทสต์ก่อนจะกลายเป็น hit ให้เทสต์ถัดไปแบบเงียบ ๆ
 */
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import type { AxiosAdapter, InternalAxiosRequestConfig } from 'axios'
import { api } from '@/services/api'
import { clearQueryCache } from '@/services/queryCache'

interface Page {
  items: { id: number; title: string }[]
  total: number
}

const originalAdapter = api.defaults.adapter

let calls = 0
let payloadFor: (url: string) => unknown = () => ({ ok: true })
/** เทสต์ตั้งค่านี้ก่อนยิง เพื่อให้คำขอ "ถัดไป" ล้มเหลวด้วย status ที่กำหนด */
let failNextStatus: number | null = null

const adapter: AxiosAdapter = (config: InternalAxiosRequestConfig) => {
  calls += 1
  if (failNextStatus !== null) {
    const status = failNextStatus
    failNextStatus = null
    return Promise.reject({
      message: `Request failed with status code ${status}`,
      config,
      response: { status, statusText: '', headers: {}, config, data: { detail: 'x' } },
    })
  }
  return Promise.resolve({
    data: payloadFor(config.url ?? ''),
    status: 200,
    statusText: 'OK',
    headers: {},
    config,
    request: {},
  })
}

/** รอให้ chain ของ revalidate (microtask + adapter promise) จบ */
const flush = () => new Promise((resolve) => setTimeout(resolve, 20))

async function getJson<T>(url: string, options: Record<string, unknown> = {}): Promise<T> {
  return (await api.get(url, options)) as unknown as T
}

beforeEach(() => {
  clearQueryCache()
  localStorage.clear()
  localStorage.setItem('access_token', 'token-a')
  calls = 0
  failNextStatus = null
  payloadFor = () => ({ ok: true })
  api.defaults.adapter = adapter
})

afterEach(() => {
  api.defaults.adapter = originalAdapter
  clearQueryCache()
  localStorage.clear()
})

describe('cache hit + revalidate', () => {
  it('C1: miss คืน proxy ตัวที่ถูกเก็บ — hit ครั้งถัดไปได้ identity เดิม', async () => {
    const first = await getJson<Page>('/api/items')
    const second = await getJson<Page>('/api/items')

    expect(second).toBe(first)
    await flush()
    // 1 = miss แรก · 2 = revalidate ที่ยิงเบื้องหลัง (ครั้งที่สองได้ cache ไปแล้ว)
    expect(calls).toBe(2)
  })

  it('C2: revalidate เงียบ ๆ แล้ว reconcile "ทับในที่" — reference เดิม ค่าใหม่', async () => {
    let round = 0
    payloadFor = () => {
      round += 1
      if (round === 1) return { items: [{ id: 1, title: 'a' }], total: 1 }
      return { items: [{ id: 1, title: 'b' }, { id: 2, title: 'c' }], total: 2 }
    }

    const first = await getJson<Page>('/api/items')
    const firstItem = first.items[0]

    const second = await getJson<Page>('/api/items') // hit → schedule revalidate
    expect(second).toBe(first)
    await flush()

    expect(calls).toBe(2)
    expect(first.total).toBe(2)
    expect(first.items).toHaveLength(2)
    // element เดิมต้องไม่ถูกสร้างใหม่ (view อาจถือ reference ไว้)
    expect(first.items[0]).toBe(firstItem)
    expect(first.items[0]?.title).toBe('b')
  })

  it('C3: cache hit หลายครั้งรัว ๆ → revalidate ครั้งเดียว (dedupe ต่อ key)', async () => {
    await getJson<Page>('/api/items')
    await getJson<Page>('/api/items')
    await getJson<Page>('/api/items')
    await flush()

    expect(calls).toBe(2) // 1 miss + 1 revalidate เท่านั้น
  })

  it('C4: revalidate ล้มด้วย 403/404 → ลบ entry (ของหายแล้ว ห้ามโชว์ค้าง)', async () => {
    await getJson<Page>('/api/items')
    failNextStatus = 404
    await getJson<Page>('/api/items') // hit → revalidate จะ 404
    await flush()

    await getJson<Page>('/api/items') // ต้องเป็น miss อีกครั้ง
    expect(calls).toBe(3)
  })
})

describe('การแยก entry', () => {
  it('C5: `noCache: true` → ยิงจริงทุกครั้งและไม่แตะ cache', async () => {
    await getJson('/api/live', { noCache: true })
    await getJson('/api/live', { noCache: true })
    expect(calls).toBe(2)

    // ต้องไม่มี entry หลงเหลือจากคำขอ noCache
    await getJson('/api/live')
    expect(calls).toBe(3)
  })

  it('C6: params ต่างกัน = คนละ entry · ลำดับคีย์ต่างกัน = entry เดียวกัน', async () => {
    const pageOne = await getJson<Page>('/api/list', { params: { page: 1 } })
    const pageTwo = await getJson<Page>('/api/list', { params: { page: 2 } })
    expect(calls).toBe(2)
    expect(pageTwo).not.toBe(pageOne)

    await getJson('/api/list', { params: { a: 1, b: 2 } })
    await getJson('/api/list', { params: { b: 2, a: 1 } })
    await flush()
    // 3 miss + 1 revalidate ของคู่หลัง (hit ⇒ ยิงเบื้องหลังเสมอ)
    expect(calls).toBe(4)
  })

  it('C7: token ต่างกัน = คนละ entry (กันเห็นข้อมูลข้ามบัญชี)', async () => {
    const asA = await getJson<Page>('/api/items')
    localStorage.setItem('access_token', 'token-b')
    const asB = await getJson<Page>('/api/items')

    expect(calls).toBe(2)
    expect(asB).not.toBe(asA)
  })

  it('C8: `responseType: blob` ไม่ถูก cache', async () => {
    await api.get('/api/download', { responseType: 'blob' })
    await api.get('/api/download', { responseType: 'blob' })
    expect(calls).toBe(2)
  })
})

describe('mutation → invalidate ตาม resource', () => {
  it('C9: POST /api/issues/... ล้าง cache ของ issues แต่ไม่แตะ boards', async () => {
    const issues = await getJson<Page>('/api/issues', { params: { status: 'open' } })
    const boards = await getJson<Page>('/api/boards')

    await api.post('/api/issues/3/resolve')

    // issues ต้องเป็น miss (ไปเอาใหม่) ส่วน boards ยัง hit
    const issuesAgain = await getJson<Page>('/api/issues', { params: { status: 'open' } })
    const boardsAgain = await getJson<Page>('/api/boards')
    await flush()

    expect(issuesAgain).not.toBe(issues)
    expect(boardsAgain).toBe(boards)
    // issues miss ×2 + boards miss ×1 + POST ×1 + revalidate ของ boards (hit)
    expect(calls).toBe(5)
  })

  it('C10: เทียบ segment เต็ม — /api/issues-extra ไม่ถูกล้างโดย /api/issues', async () => {
    const extra = await getJson<Page>('/api/issues-extra')

    await api.post('/api/issues/1/resolve')

    const extraAgain = await getJson<Page>('/api/issues-extra')
    await flush()
    expect(extraAgain).toBe(extra)
    // miss แรก + POST + revalidate ของ extra (hit) — ไม่มีการยิงซ้ำเพราะ invalidation
    expect(calls).toBe(3)
  })
})

describe('LRU', () => {
  it('C11: เกิน 50 entry → entry เก่าสุดถูก evict', async () => {
    for (let i = 0; i < 51; i += 1) {
      await getJson(`/api/list/${i}`)
    }
    expect(calls).toBe(51)

    await getJson('/api/list/0')
    expect(calls).toBe(52) // ถูก evict ไปแล้ว ⇒ ต้องยิงใหม่
  })
})

describe('clearQueryCache', () => {
  it('C12: ล้างแล้วคำขอถัดไปเป็น miss', async () => {
    await getJson<Page>('/api/items')
    clearQueryCache()
    await getJson<Page>('/api/items')
    expect(calls).toBe(2)
  })
})
