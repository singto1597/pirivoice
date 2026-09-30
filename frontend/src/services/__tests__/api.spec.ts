/**
 * 🧪 `services/api.ts` — **`status` ต้องรอดผ่าน interceptor** (รากของบั๊ก #32 / A4)
 *
 * **ทำไมต้องมีเทสนี้:** การแก้บั๊ก #32 ทั้งหมดแขวนอยู่บนบรรทัดเดียว —
 * `apiError.status = error.response.status` — เพราะหน้าที่เจอ 404 ตัดสินใจด้วย
 * `(e as ApiError).status === 404` ⇒ ถ้ามีคน "ทำความสะอาด" `api.ts` แล้วเปลี่ยนกลับไป
 * เป็น `new Error(detail)` ธรรมดา **ทุกอย่างยังคอมไพล์ผ่าน เทสต์อื่นยังผ่าน**
 * แต่ผู้ใช้ที่กด notification ที่ชี้บอร์ดซึ่งถูกซ่อนจะ **ค้างอยู่หน้า error** อีกครั้ง
 * โดยไม่มีสัญญาณอะไรเลย (นี่คือความล้มเหลวแบบเดียวกับที่เทสนี้เกิดมาป้องกัน)
 *
 * ⭐ **สิ่งที่ต้องแยกออกจากกันให้ได้** (ทั้งสามแบบมาถึงหน้าเป็น "Error" เหมือนกันหมด):
 *   - `404` — บอร์ด/เรื่องถูกซ่อนหรือถูกลบ → **ต้องพากลับหน้ารายการ + บอกสาเหตุ**
 *   - `500` — เซิร์ฟเวอร์พัง → **ต้องอยู่หน้าเดิม + ปุ่มลองใหม่** (พากลับ = ซ่อนปัญหา)
 *   - เน็ตหลุด (ไม่มี response) — `status` ต้องเป็น `undefined` ไม่ใช่ 0/-1
 *
 * ⚠️ **ทดสอบผ่าน adapter จริง ไม่ใช่เรียก handler ตรง ๆ** — `interceptors.response.handlers`
 *    เป็นโครงสร้างภายในที่เปลี่ยนได้between เวอร์ชัน · การแทน adapter ทำให้ route
 *    ทั้งเส้น (transform → interceptor → caller) ทำงานเหมือนของจริง
 *
 * ⚠️ **ไม่ทดสอบ 401 ในไฟล์นี้** — สาขานั้นเขียน `window.location` (jsdom ไม่รองรับ navigation)
 *    ซึ่งต้องคุมทั้งใบ ⇒ แยกไปที่ `apiRedirect.spec.ts` พร้อมเหตุผลว่าทำไมต้องแยก
 *    (สำคัญ: `isRedirectingToLogin` เป็นสถานะระดับโมดูล ⇒ ต้องโหลดโมดูลใหม่ต่อเทสต์)
 */
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import type { AxiosAdapter, InternalAxiosRequestConfig } from 'axios'
import { api, type ApiError } from '@/services/api'

const originalAdapter = api.defaults.adapter

/**
 * แทน adapter ให้ตอบ (หรือล้มเหลว) ตามที่กำหนด
 *
 * ⚠️ ตอบด้วย **อ็อบเจ็กต์เปล่า** ไม่ใช่ `AxiosError` จริง — axios ตรวจแค่ว่ามี `.response`
 *    ก็พอสำหรับสาขาที่เราทดสอบ (ดู `dispatchRequest` → `onAdapterRejection`)
 */
function stubAdapter(outcome: {
  status: number
  data?: unknown
} | null) {
  const adapter: AxiosAdapter = (config: InternalAxiosRequestConfig) => {
    if (outcome === null) {
      return Promise.reject({ message: 'Network Error', config })
    }
    return Promise.reject({
      message: `Request failed with status code ${outcome.status}`,
      config,
      response: {
        status: outcome.status,
        statusText: '',
        headers: {},
        config,
        data: outcome.data,
      },
    })
  }
  api.defaults.adapter = adapter
}

/** ยิง request แล้วคืน error ที่ผู้เรียกจะได้จริง (ต้องเป็น Error เสมอ) */
async function catchError(): Promise<ApiError> {
  try {
    await api.get('/boards/1')
  } catch (e) {
    return e as ApiError
  }
  throw new Error('ต้อง reject แต่กลับ resolve — เทสผิด ไม่ใช่โค้ดผิด')
}

beforeEach(() => {
  localStorage.clear()
})

afterEach(() => {
  api.defaults.adapter = originalAdapter
})

describe('ApiError — status ต้องรอดถึงผู้เรียก', () => {
  it('A1: 404 → `status === 404` และ `instanceof Error` ยังเป็นจริง', async () => {
    stubAdapter({ status: 404, data: { detail: 'ไม่พบบอร์ด' } })
    const err = await catchError()

    // ยังเป็น Error จริง ⇒ ผู้เรียกเดิม (`e instanceof Error ? e.message : ...`) ไม่พัง
    expect(err).toBeInstanceOf(Error)
    expect(err.status).toBe(404)
  })

  it('A2: 500 → `status === 500` (แยกจาก 404 ได้ — หัวใจของเรื่องนี้)', async () => {
    stubAdapter({ status: 500, data: { detail: 'เซิร์ฟเวอร์ขัดข้อง' } })
    expect((await catchError()).status).toBe(500)
  })

  it('A3: 422 → ข้อความถูกแปลงเป็นภาษาไทย และ status ยังอยู่', async () => {
    stubAdapter({
      status: 422,
      data: { detail: [{ loc: ['body', 'title'], msg: 'field required' }] },
    })
    const err = await catchError()
    expect(err.status).toBe(422)
    expect(err.message).toContain('title')
    expect(err.message).toContain('field required')
  })

  it('A4: ⭐ เน็ตหลุด (ไม่มี response) → `status` เป็น `undefined` ไม่ใช่ 0/-1', async () => {
    // ⚠️ ถ้าใส่ 0 หรือ -1 "กันไว้เฉย ๆ" ⇒ ด่าน `status === 404` จะ false ตามที่ควรก็จริง
    //    แต่โค้ดที่เขียนว่า `if (!err.status)` หรือ `if (err.status === undefined)`
    //    จะตีความผิด ⇒ ปล่อยเป็น undefined เท่านั้น (ไม่มีข้อมูล = ไม่มีข้อมูล)
    stubAdapter(null)
    const err = await catchError()
    expect(err.status).toBeUndefined()
    expect(err).toBeInstanceOf(Error)
    expect(err.message).toContain('ไม่สามารถเชื่อมต่อกับ Backend ได้')
  })

  it('A5: `detail` ที่ไม่มีใน body → ใช้ข้อความ default แต่ status ยังถูกต้อง', async () => {
    stubAdapter({ status: 404, data: {} })
    const err = await catchError()
    expect(err.status).toBe(404)
    expect(err.message.length).toBeGreaterThan(0)
  })

  it('A6: ชื่อ property ต้องเป็น `status` จริง — หน้าที่เจอ 404 อ่านคีย์นี้ตรง ๆ', async () => {
    // ⚠️ เทสนี้ดูซ้ำซากโดยเจตนา: `BoardDetail.vue`/`IssueDetail.vue` ใช้
    //    `(e as ApiError).status === 404` ซึ่ง **ไม่มีอะไรผูกให้** ถ้ามีคนเปลี่ยนชื่อ
    //    property (เช่นเป็น `httpStatus`) TS จะไม่ฟ้องในฝั่งที่ cast ⇒ ต้องมีเทสตรึงชื่อ
    stubAdapter({ status: 404, data: { detail: 'x' } })
    const err = await catchError()
    expect(Object.prototype.hasOwnProperty.call(err, 'status')).toBe(true)
  })
})
