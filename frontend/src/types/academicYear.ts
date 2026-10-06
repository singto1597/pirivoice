// 🎓 ปีการศึกษา (Academic Years) — migration 027
//
// ⚠️ **คนละเรื่องกับ "ภาคเรียน" (`academicTerm.ts`) — อย่าสลับ:**
//   · ภาคเรียน = "ภาคนี้เป็นยังไง" → ใช้กรองสถิติตามช่วงวันที่ (หน้าแรก / สถิติส่วนตัว)
//   · ปีการศึกษา = "ปีนี้ใครอยู่ห้องไหน ตำแหน่งอะไร" → เป็นแกนของ "เลื่อนชั้นทั้งโรงเรียน"
//   1 ปีมี 2 ภาค ⇒ เอามารวมกันไม่ได้ ("สมาชิกผูกกับภาคไหน" ไม่มีความหมาย)
//
// ⚠️ `year_be` เป็น **พ.ศ.** (2569) ไม่ใช่ ค.ศ. (2026) — ระบบนี้แสดง พ.ศ. ทั้งหมด
// ⚠️ "ปีปัจจุบัน" มีได้ตัวเดียวเสมอ (บังคับด้วย DB) — ปีที่ไม่มี = ยังไม่ตั้ง (แต่หลัง migration
//    027 จะมีเสมอ เพราะระบบ seed ปีตั้งต้นไว้)

export interface AcademicYear {
  id: number
  year_be: number // พ.ศ. เช่น 2569 — ⚠️ ไม่ใช่ ค.ศ.
  name: string // เช่น "ปีการศึกษา 2569"
  start_date: string | null // YYYY-MM-DD · null = ยังไม่รู้วันเปิดเทอม (สร้างล่วงหน้าได้)
  end_date: string | null
  is_current: boolean
  /** จำนวนแถวสมาชิก (`students`) ที่ยังไม่ถูกลบในปีนี้ — **ทุกสถานะ** ไม่ใช่แค่ active
   *  ⇒ ปีที่จบไปแล้วยังโชว์จำนวนจริงได้ ไม่ใช่ 0 */
  member_count: number
  created_at: string
  updated_at: string
  deleted_at: string | null // null = ยังไม่ถูกลบ
}

export interface AcademicYearListResponse {
  items: AcademicYear[]
  total: number
  page: number
  page_size: number
  pages: number
}

export interface AcademicYearCreatePayload {
  year_be: number
  /** เว้นว่าง = backend ตั้งให้เป็น "ปีการศึกษา {year_be}" */
  name?: string
  start_date?: string | null
  end_date?: string | null
  is_current?: boolean
}

// PATCH — ส่งเฉพาะฟิลด์ที่จะแก้ (ไม่ส่ง = ไม่แตะ)
// ⚠️ ไม่มี is_current โดยเจตนา — เปลี่ยนปีปัจจุบันต้องเรียก setCurrentYear() เท่านั้น
//    (backend ต้องล้างตัวเก่าก่อนตั้งตัวใหม่ + มีด่าน "ปีว่างตั้งเป็นปัจจุบันไม่ได้")
// ⚠️ `start_date`/`end_date` ส่ง `null` ได้ = "ล้างวันที่" (ต่างจากภาคเรียนที่ null ถูกปฏิเสธ)
//    แต่ `year_be`/`name` ส่ง `null` = 400 (คอลัมน์ NOT NULL)
export interface AcademicYearUpdatePayload {
  year_be?: number
  name?: string
  start_date?: string | null
  end_date?: string | null
}

// แท็บกรองสถานะ — ตรงกับ pattern `status` ของ GET /api/settings/years
export const YEAR_STATUS_TABS: Array<{ value: string; label: string }> = [
  { value: 'current', label: 'ปีปัจจุบัน' },
  { value: 'active', label: 'ทั้งหมด' },
  { value: 'deleted', label: 'ถูกลบ' },
]

// ============================================================
// 🧠 Pure helpers — ทดสอบได้โดยไม่ต้องมี DOM
// ============================================================
// ตาม frontend.md §4: ต้องแยก "ว่าง ≠ พัง ≠ ยังโหลดไม่เสร็จ" ออกจากกันให้ได้
// ⇒ ตรรกะที่ตัดสินว่าจะโชว์อะไร ต้องเป็นฟังก์ชันบริสุทธิ์ ไม่ใช่ if ซ้อนในเทมเพลต

export type YearScreenState = 'loading' | 'error' | 'empty' | 'list'

/** สถานะหน้าจอจากข้อมูลที่มี — เรียงตาม "สิ่งที่ผู้ใช้ต้องรู้ก่อน" */
export function yearScreenState(opts: {
  isLoading: boolean
  hasError: boolean
  itemCount: number
}): YearScreenState {
  if (opts.hasError) return 'error'
  // ⚠️ `isLoading` ต้องมาหลัง `hasError` — การโหลดรอบสองที่ล้ม ต้องโชว์ error
  //    ไม่ใช่ค้างที่ skeleton ตลอดกาล
  if (opts.isLoading && opts.itemCount === 0) return 'loading'
  if (opts.itemCount === 0) return 'empty'
  return 'list'
}

/** ปีที่ทับซ้อนกับ "วันนี้" (ใช้ติดป้าย "ปีนี้กำลังเรียนอยู่" ในแท็บทั้งหมด)
 *
 *  ⚠️ เทียบแบบสตริง `YYYY-MM-DD` ตรง ๆ ไม่ผ่าน `new Date()` — string แบบ date-only
 *     ถูกตีความเป็นเที่ยงคืน UTC แล้วเลื่อนเป็นเวลาไทย (+7 ชม.) ⇒ วันที่เพี้ยน
 *  ⚠️ ปีที่ไม่มีวัน (`start_date`/`end_date` เป็น null) ตอบ `false` เสมอ — ไม่เดา
 */
export function yearCoversToday(y: AcademicYear, todayYmd: string): boolean {
  if (!y.start_date || !y.end_date) return false
  return y.start_date <= todayYmd && todayYmd <= y.end_date
}

// ============================================================
// 📝 ฟอร์มปีการศึกษา (หน้าเต็ม) — ค่าที่ผูกกับ input เป็น **สตริง** ทั้งหมด
// ============================================================
// ทำไมไม่ใช้ number | null: `<input v-model>` ให้สตริงเสมอ ⇒ ถ้าประกาศเป็น number
// ต้องมี watcher แปลงกลับไปกลับมา ซึ่งเป็นที่มาของบั๊ก "0 หาย" / "ค่าว่างกลายเป็น NaN"
// ⇒ เก็บดิบ ๆ ตามที่ผู้ใช้พิมพ์ แล้วตรวจ/แปลง **ครั้งเดียวตอน submit** (pure ⇒ เทสได้)

export interface YearFormValues {
  /** พ.ศ. ที่ผู้ใช้พิมพ์ — ตรวจ/แปลงตอน submit */
  year_be: string
  /** เว้นว่าง = ให้ backend ตั้งเป็น "ปีการศึกษา {year_be}" */
  name: string
  /** '' = ไม่ระบุ (backend เก็บเป็น NULL) */
  start_date: string
  end_date: string
}

export const YEAR_BE_MIN = 2400
export const YEAR_BE_MAX = 2700

/** ฟอร์มว่าง — ใช้ทั้งตอน "เพิ่ม" และเป็น baseline ตั้งต้นของตาข่ายกันข้อมูลหาย */
export const EMPTY_YEAR_FORM: YearFormValues = {
  year_be: '',
  name: '',
  start_date: '',
  end_date: '',
}

/** แถวจาก API → ค่าฟอร์ม (แก้ไข) · `null` ของวันกลายเป็น `''` ให้ `<input type="date">` */
export function toYearFormValues(y: AcademicYear): YearFormValues {
  return {
    year_be: String(y.year_be),
    name: y.name,
    start_date: y.start_date ?? '',
    end_date: y.end_date ?? '',
  }
}

/** ตรวจฟอร์ม — คืน `''` = ผ่าน · คืนข้อความ = ห้ามบันทึก พร้อมเหตุผล
 *
 *  ⚠️ ช่วง พ.ศ. ต้องตรงกับ `AcademicYearCreateRequest.year_be` (`ge=2400, le=2700`)
 *     ที่นี่ตรวจซ้ำเพื่อให้ **ปุ่มบันทึกกดไม่ได้ตั้งแต่แรก** ไม่ใช่กดแล้วเด้ง 422
 *  ⚠️ วันที่ **ไม่บังคับ** (ต่างจากภาคเรียน) — ปีที่ยังไม่รู้วันเปิดเทอมต้องสร้างได้
 *     แต่ถ้าใส่มาทั้งคู่ ต้องเรียงถูก
 */
export function yearFormError(v: YearFormValues): string {
  const raw = v.year_be.trim()
  if (!raw) return 'กรอกปีการศึกษา (พ.ศ.)'
  if (!/^\d+$/.test(raw)) return 'ปีการศึกษาเป็นตัวเลขเท่านั้น เช่น 2569'
  const be = Number(raw)
  if (be < YEAR_BE_MIN || be > YEAR_BE_MAX) {
    return `ปีการศึกษาต้องอยู่ระหว่าง ${YEAR_BE_MIN}–${YEAR_BE_MAX} (พ.ศ.)`
  }
  if (v.name.trim().length > 50) return 'ชื่อยาวเกิน 50 ตัวอักษร'
  if (v.start_date && v.end_date && v.end_date < v.start_date) {
    return 'วันสิ้นสุดต้องไม่ก่อนวันเริ่มต้น'
  }
  return ''
}

/** แปลงค่าฟอร์ม → payload ที่ส่ง backend · `''` ของวันที่กลายเป็น `null` (= ไม่ระบุ) */
export function yearFormToPayload(v: YearFormValues): {
  year_be: number
  name?: string
  start_date: string | null
  end_date: string | null
} {
  const name = v.name.trim()
  return {
    year_be: Number(v.year_be.trim()),
    // ไม่ส่ง `name` เลยเมื่อว่าง — ให้ backend ตั้ง default เอง (ไม่ใช่กรอกช่องว่างไปทับ)
    ...(name ? { name } : {}),
    start_date: v.start_date || null,
    end_date: v.end_date || null,
  }
}

/** ลบปีนี้ได้ไหม — คืน `''` = ได้ · คืนข้อความ = **ห้ามลบ พร้อมเหตุผล**
 *
 *  ⚠️ กฎสองข้อนี้ **backend บังคับอยู่แล้ว** (คืน 400 พร้อมข้อความไทย) — ที่นี่ทำซ้ำ
 *     โดยเจตนา เพราะปุ่มที่กดได้แล้วเด้ง error คือประสบการณ์ที่แย่ที่สุด:
 *     ผู้ใช้ต้องรู้ *ก่อน* กด ว่าเรื่องนี้ทำไม่ได้และทำไม
 *  ⚠️ **ต้องตรงกับ `delete_year` ใน `services/year_service.py` เสมอ** — ถ้าแก้ที่นั่น
 *     ต้องแก้ที่นี่ (จริง ๆ คือ "เหตุผล" ต่างหากที่ต้องตรง ไม่ใช่แค่ "ได้/ไม่ได้")
 */
export function deleteBlockReason(y: AcademicYear): string {
  if (y.is_current) {
    return 'นี่คือปีปัจจุบัน — ต้องตั้งปีอื่นเป็นปีปัจจุบันก่อนจึงจะลบได้'
  }
  if (y.member_count > 0) {
    return `ยังมีสมาชิก ${y.member_count} คนในปีนี้ — ย้ายหรือนำออกให้หมดก่อน`
  }
  return ''
}

/** ข้อความยืนยันก่อนกด "ใช้เป็นปีปัจจุบัน" — เตือนให้ชัดว่ากระทบอะไร
 *
 *  ⚠️ การเปลี่ยนปีปัจจุบัน **ไม่ใช่แค่เปลี่ยนป้ายชื่อ** — มันเปลี่ยน DEFAULT ของ
 *     `students.academic_year_id` ด้วย ⇒ สมาชิกที่สร้างหลังจากนี้ (การลงทะเบียนใหม่)
 *     จะไปอยู่ปีใหม่ทันที ⇒ ข้อความต้องบอกเรื่องนี้ ไม่ใช่แค่ "ยืนยัน?"
 */
export function setCurrentConfirmText(y: AcademicYear): string {
  const members = y.member_count
  if (members === 0) {
    return 'ปีนี้ยังไม่มีสมาชิก — ระบบจะไม่ยอมให้ตั้งเป็นปีปัจจุบัน ถ้าปีอื่นยังมีคนอยู่'
  }
  return (
    `รายชื่อนักเรียน สถิติ และหน้าแรกจะนับเฉพาะสมาชิก ${members} คนในปี ${y.year_be} ` +
    'และสมาชิกที่สร้างใหม่จะไปอยู่ปีนี้โดยอัตโนมัติ'
  )
}
