/**
 * 🕐 เวลา — ตัวช่วยกลางของทั้งแอป (เขตเวลาไทยเสมอ)
 *
 * ⚠️ **ทำไมต้องรวมไว้ที่เดียว** — `fmtDateTime` เดิมถูก **ก๊อปซ้ำอยู่ 4 ไฟล์**
 *    (`CommentThread` · `EventDetail` · `MyActivity` · `AuditLogs`) ⇒ วันที่มีคนแก้รูปแบบ
 *    ที่เดียว อีกสามที่เหลือจะไม่ตรงกัน แล้วผู้ใช้จะเห็นวันที่คนละหน้าตาในระบบเดียว
 *    ซึ่งไม่มีเทสต์ไหนจับได้ (ไม่มีเทสต์ไหนเทียบข้ามไฟล์)
 *
 * ⚠️ **ทุกฟังก์ชันในไฟล์นี้ตรึง `Asia/Bangkok`** — ห้ามใช้โซนของเครื่องผู้ใช้ เพราะนาฬิกา
 *    เครื่องผู้ใช้ตั้งผิดได้ และเวลาของ *ระบบ* ไม่ใช่การแสดงผล
 */

/**
 * `YYYY-MM-DDTHH:MM` **ในเขตเวลาไทย** สำหรับ `<input type="datetime-local">`
 *
 * ⚠️ **ห้ามใช้ `toISOString().slice(0,16)`** — ได้เวลา UTC ⇒ พอเปิดฟอร์มแก้ไข ฟิลด์จะโชว์
 *    เวลาที่น้อยไป 7 ชั่วโมง และถ้าผู้ใช้กดบันทึกโดยไม่แตะอะไร ค่าที่ส่งกลับจะเพี้ยนทันที
 *    ⚠️ และ **ห้ามใช้ `new Date(iso)` แบบ date-only** — กิจกรรมเป็น timestamptz จึงใช้ได้
 *    แต่ต้องอ่าน "ชิ้นส่วน" ออกมาในโซน Bangkok ไม่ใช่โซนเครื่องผู้ใช้
 *
 * ⚠️ `hourCycle: 'h23'` **ห้ามถอด** — ค่าเริ่มต้นของ `en-GB` บางรันไทม์คืน `24:00` แทน
 *    `00:00` ⇒ `<input type="datetime-local">` ปฏิเสธค่า `24:00` แล้วช่องจะว่างเปล่า
 *    ซึ่งอ่านไม่ออกเลยว่ามาจากไหน
 *
 * 🔴 **`hourCycle: 'h23'` เป็น "เข็มขัดนิรภัย" ที่เทสต์พิสูจน์ไม่ได้บนเครื่องนี้** —
 *    ทดสอบด้วย mutation แล้ว (ถอดบรรทัดนี้ออก ⇒ เทสต์ทั้งไฟล์ยังเขียว 21/21) เพราะ
 *    Node 22 + full ICU **ให้ `h23` อยู่แล้วโดยปริยาย** ทั้ง `en-GB` และ `th-TH-u-ca-buddhist`
 *    (ไล่เทียบครบ 24 ชั่วโมง ⇒ ต่างกัน 0 ชั่วโมง)
 *    ⇒ **ห้ามลบบรรทัดนี้เพียงเพราะ "เทสต์เขียว"** — มันกันรันไทม์ที่ default เป็น `h24`
 *      (ICU build แบบ small / เบราว์เซอร์บางตัว / Node เวอร์ชันอื่น) ซึ่งเทสต์จะจับได้ *ตอนนั้น*
 *      ไม่ใช่ตอนนี้ · ถ้าย้ายไปรันไทม์ที่ผลต่างจริง เทสต์เคส `23:30` จะกลายเป็นตัวจับทันที
 */
const BKK_PARTS = new Intl.DateTimeFormat('en-GB', {
  timeZone: 'Asia/Bangkok',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  hourCycle: 'h23',
})

export function toLocalInput(iso: string | null): string {
  if (!iso) return ''
  const parts = BKK_PARTS.formatToParts(new Date(iso))
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? ''
  return `${get('year')}-${get('month')}-${get('day')}T${get('hour')}:${get('minute')}`
}

/**
 * สตริงฟอร์ม (`YYYY-MM-DDTHH:MM`) → `Date` ใน **โซนของเครื่อง** (local constructor)
 *
 * ⭐ **คู่กับ `dateToInput()` และใช้ local ทั้งคู่โดยเจตนา** — round-trip ไม่เพี้ยนบนเครื่อง
 *    ทุกโซน เพราะขาเข้าตีความเป็น local แล้วขาออกอ่านเป็น local ด้วยตัวเลขชุดเดิม
 *
 * 🚫 **ห้ามเปลี่ยนเป็น `new Date(s)` (ISO parse)** — สตริง `"2026-10-15T09:00"` ที่ไม่มี
 *    tzinfo จะถูกตีเป็น **local** โดยสเปคก็จริง แต่ `"2026-10-15"` (date-only) ถูกตีเป็น
 *    **UTC** ⇒ สองรูปแบบที่ดูเหมือนกันให้ผลต่างกัน 7 ชั่วโมง · และไม่มีใครจับได้จาก type
 *    🚫 **ห้ามใช้ `toISOString()` ในเส้นทางกลับ** — เลื่อน 7 ชม. ทันที
 */
export function inputToDate(value: string): Date | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/.exec(value)
  if (!m) return null
  const [, y, mo, d, h, mi] = m
  const date = new Date(Number(y), Number(mo) - 1, Number(d), Number(h), Number(mi))
  // ⚠️ กันวันที่ที่ "ไม่มีอยู่จริง" (เช่น 31 ก.พ. ซึ่ง JS จะเลื่อนไป 2-3 มี.ค. เงียบ ๆ)
  //    ⇒ ตรวจว่ากลับมาเป็นตัวเลขเดิม ถ้าไม่ใช่ = ค่านั้นไม่ถูกต้อง ให้ผู้เรียกจัดการ
  if (dateToInput(date) !== value) return null
  return date
}

/** `Date` → `YYYY-MM-DDTHH:MM` โดยอ่านด้วย **local getters** (คู่กับ `inputToDate`) */
export function dateToInput(date: Date): string {
  const p = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${p(date.getMonth() + 1)}-${p(date.getDate())}T${p(date.getHours())}:${p(date.getMinutes())}`
}

/**
 * คำอ่านภาษาไทยของค่าฟอร์ม — **"15 ตุลาคม 2569 09:00 น."**
 *
 * ⭐ ทำไมไม่ให้ date picker โชว์ พ.ศ. เลย: ไลบรารีที่ใช้ (`@vuepic/vue-datepicker` + `date-fns`)
 *    **ไม่รองรับพุทธศักราช** ⇒ ทางเดียวที่ทำได้คือปล่อย ค.ศ. ในช่อง แล้วอ่านเป็น พ.ศ. ใต้ช่อง
 *    ⇒ ได้ทั้ง "ค่าที่ตรงกับที่ส่ง backend เป๊ะ" (ไม่มีขั้นตอนแปลง = ไม่มีที่ให้พลาด)
 *    และ "อ่านออก" สำหรับผู้ใช้ไทย
 *
 * ⚠️ **ต้องใช้ `Date.UTC` ไม่ใช่ `new Date(...)`** — เราป้อนตัวเลขจากสตริงเข้าไป ค่าเหล่านี้
 *    เป็น "ตัวเลขบนหน้าปัด" ไม่ใช่เวลาจริง ⇒ ถ้าใช้ local แล้วเครื่องอยู่โซนที่มี DST
 *    วันที่ 31 มี.ค. 03:00 อาจไม่มีอยู่จริงแล้วถูกเลื่อนเป็น 04:00 ⇒ คำอ่านเพี้ยน
 *    UTC ไม่มี DST ⇒ ตัวเลขที่ได้ตรงกับที่ป้อนเสมอ
 *
 * ⚠️ ระบุ `'th-TH-u-ca-buddhist'` **ให้ชัด** — อย่าพึ่ง default ของ ICU เพราะ default ขึ้นกับ
 *    build ของ Node/เบราว์เซอร์ (บางที่ไม่มีข้อมูลฏิทินพุทธ ⇒ เงียบ ๆ กลับมาเป็น ค.ศ.)
 *    แล้วคำอ่านจะบอก พ.ศ. ผิดโดยไม่มีอะไรฟ้อง
 */
export function formatThaiDateTimeInput(value: string): string {
  const date = inputToDate(value)
  if (!date) return ''
  const parts = new Date(
    Date.UTC(
      date.getFullYear(),
      date.getMonth(),
      date.getDate(),
      date.getHours(),
      date.getMinutes(),
    ),
  )
  return new Intl.DateTimeFormat('th-TH-u-ca-buddhist', {
    timeZone: 'UTC',
    day: 'numeric',
    month: 'long',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    // ⚠️ เช่นเดียวกับ `BKK_PARTS` — บรรทัดนี้พิสูจน์ด้วยเทสต์บนเครื่องนี้ไม่ได้
    //    (ถอดออกแล้วยังเขียว) แต่กันรันไทม์ที่ default เป็น `h24` ⇒ อย่าลบ
    hourCycle: 'h23',
  }).format(parts)
}

/** วันและเวลาจัดกิจกรรม — timestamptz จึงใช้ `new Date(iso)` ได้ตรง ๆ */
export function fmtDateTime(iso: string): string {
  return new Date(iso).toLocaleString('th-TH', {
    timeZone: 'Asia/Bangkok',
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

/** เวลาสั้น ๆ (`HH:MM`) สำหรับตรา "เช็คอินแล้ว" — เช็คอินเกิดวันงานเสมอ วันที่จึงซ้ำกับหัวข้อ */
export function fmtTime(iso: string): string {
  return new Date(iso).toLocaleTimeString('th-TH', {
    timeZone: 'Asia/Bangkok',
    hour: '2-digit',
    minute: '2-digit',
  })
}

/** วันที่ล้วน (`30 ก.ย. 2569`) — พ.ศ. · ไม่มีเวลา ⇒ ใช้ในบรรทัดที่เวลาที่แน่นอนไม่ช่วยอะไร */
export function fmtDateShort(iso: string): string {
  return new Date(iso).toLocaleDateString('th-TH', {
    timeZone: 'Asia/Bangkok',
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  })
}

/** ปี/เดือน/วัน **ในเขตเวลาไทย** — ใช้คิด "ต่างกันกี่วัน" โดยไม่พึ่งโซนเครื่องที่รัน */
function bangkokYmd(d: Date): [number, number, number] {
  const parts = BKK_PARTS.formatToParts(d)
  const get = (t: string) => Number(parts.find((p) => p.type === t)?.value ?? 0)
  return [get('year'), get('month'), get('day')]
}

/**
 * ต่างกันกี่ **วันตามปฏิทินไทย** — `เมื่อวาน` ต้องหมายถึง "เมื่อวาน" ไม่ใช่ "24–48 ชม.ที่แล้ว"
 *
 * ⚠️ ห้ามคิดจาก `(a - b) / 86400000` — 23:00 กับ 01:00 ของวันถัดไปห่างกันแค่ 2 ชม.
 *    แต่เป็นคนละวันตามปฏิทิน ซึ่งเป็นสิ่งที่ผู้ใช้อ่าน ⇒ ต้องเทียบ **วันที่** ไม่ใช่ระยะเวลา
 *    และต้องอ่านวันที่ในโซน Bangkok ไม่ใช่โซนเครื่อง (VPS อยู่นอกไทยได้)
 */
function bangkokDayDiff(from: Date, to: Date): number {
  const [fy, fm, fd] = bangkokYmd(from)
  const [ty, tm, td] = bangkokYmd(to)
  // `Date.UTC` ใช้เป็น "ถังพัก" ให้ลบกันได้โดยไม่มี DST/โซนเข้ามาเกี่ยว (ทุกค่าเป็น UTC หมด)
  return Math.round((Date.UTC(ty, tm - 1, td) - Date.UTC(fy, fm - 1, fd)) / 86_400_000)
}

/**
 * เวลาแบบ "ผ่านมาเท่าไร" — `เมื่อสักครู่` · `5 นาทีที่แล้ว` · `3 ชั่วโมงที่แล้ว` ·
 * `เมื่อวาน` · `3 วันที่แล้ว` → เกิน 7 วันคืน **วันที่จริง** (ดู `fmtDateShort`)
 *
 * ⭐ **ทำไมต้องมี:** ในลิสต์ที่ผู้ใช้ต้องกวาดตาหา "อันไหนใหม่" วันที่เต็ม (`30 ก.ย. 2569 14:32`)
 *    บังคับให้อ่านและลบกันในหัวทุกแถว — "3 วันที่แล้ว" ตอบคำถามนั้นทันที
 *    ⚠️ แต่ **ต้องเปลี่ยนเป็นวันที่จริงเมื่อเก่าพอ** — "45 วันที่แล้ว" ก็ต้องลบกันในหัวอยู่ดี
 *       และยิ่งนานยิ่งอ่านยาก ⇒ ตัดที่ 7 วันซึ่งเป็นจุดที่การนับถอยหลังเลิกมีประโยชน์
 *
 * 🔴 `now` **เป็นพารามิเตอร์ ไม่เรียก `new Date()` ข้างใน** — ไม่งั้นเทสต์ต้องคำนวณค่า
 *    คาดหวังด้วย `new Date()` ของตัวเอง ซึ่งจะผ่านเสมอไม่ว่าจะยืนยันอะไร (ดูหัวไฟล์ของ
 *    `datetime.spec.ts`) ⇒ ผู้เรียกจริงส่งค่าว่างได้ แต่เทสต์ป้อนเวลาคงที่ได้
 *
 * ⚠️ **อนาคตเล็กน้อยคืน `เมื่อสักครู่` ไม่ใช่ค่าติดลบ** — `created_at` ที่ใหม่กว่านาฬิกาเครื่อง
 *    ผู้ใช้เกิดได้จริง (นาฬิกาเครื่องเพี้ยน/เขตเวลาผิด) และ `-3 นาทีที่แล้ว` อ่านแล้วเหมือนบั๊ก
 *    ⇒ ตรรกะเดียวกับที่ `closingLabel()` ใน `types/event.ts` ต้องรับมือ
 */
export function fmtRelative(iso: string, now: Date = new Date()): string {
  const then = new Date(iso)
  if (Number.isNaN(then.getTime())) return ''

  const diffMs = now.getTime() - then.getTime()
  if (diffMs < 60_000) return 'เมื่อสักครู่' // รวมอนาคตอันใกล้และนาฬิกาเครื่องเพี้ยน

  const dayDiff = bangkokDayDiff(then, now)
  if (dayDiff >= 1) {
    if (dayDiff === 1) return 'เมื่อวาน'
    if (dayDiff < 7) return `${dayDiff} วันที่แล้ว`
    return fmtDateShort(iso)
  }

  // ถึงตรงนี้แปลว่าเป็น **วันเดียวกันตามปฏิทินไทย** แล้ว (`dayDiff === 0`) ⇒ นับเป็นชั่วโมงได้ตรง
  // ⚠️ แต่มันไม่เท่ากับ "ห่างกันไม่ถึง 24 ชม." — ของเมื่อวาน 23:00 เปิดดูตอน 01:00 ได้ `dayDiff = 1`
  //    แล้วถูกจับเป็น `เมื่อวาน` ตั้งแต่บล็อกข้างบน ซึ่งเป็นสิ่งที่ผู้ใช้อ่านถูกอยู่แล้ว
  const minutes = Math.floor(diffMs / 60_000)
  if (minutes < 60) return `${minutes} นาทีที่แล้ว`
  return `${Math.floor(minutes / 60)} ชั่วโมงที่แล้ว`
}

/**
 * 🗓️ ป้ายหัวกลุ่มของลิสต์ที่จัดกลุ่มตามวัน — `วันนี้` · `เมื่อวาน` · แล้วแต่วันที่จริง
 *
 * ⭐ **ทำไมต้องมี:** ลิสต์ที่ยาวเป็นแถบเดียว (แจ้งเตือน 15 แถว/หน้า) บังคับให้ผู้ใช้
 *    อ่าน *เวลาของทุกแถว* เพื่อเดาว่าอะไรใหม่ — หัวกลุ่มตอบคำถามนั้นครั้งเดียวต่อกลุ่ม
 *    และทำให้ "เมื่อวาน" กลายเป็นที่ที่กวาดตาไปหาได้ทันที
 *
 * ⚠️ **ใช้ `bangkokDayDiff` ตัวเดียวกับ `fmtRelative`** ⇒ คำว่า "เมื่อวาน" ในแอพนี้
 *    หมายถึง **เมื่อวานตามปฏิทินไทย** ทั้งสองที่ ไม่ใช่ "24–48 ชม.ที่แล้ว"
 *    ถ้าแยกตรรกะไปเขียนใหม่ที่นี่ วันหนึ่งสองที่จะไม่ตรงกันแล้วผู้ใช้เห็น "เมื่อวาน"
 *    ในหัวกลุ่มแต่ "2 วันที่แล้ว" ในแถวใต้มัน
 *
 * 🔴 **ค่าที่คืนใช้อัดกลุ่มได้** — ผู้เรียกที่ต้องแบ่งลิสต์เป็นก้อนสามารถเทียบสตริงนี้
 *    ตรง ๆ ได้ **เฉพาะกับรายการที่เรียงต่อกัน** (ดูคอมเมนต์ใน `NotificationCenter.vue`
 *    ว่าทำไมการเทียบแบบนั้นปลอดภัย) · ค่าที่ไม่ซ้ำกันข้ามวันเพราะ `fmtDateShort`
 *    มีทั้งวันและเดือน
 *
 * คืน `''` เมื่อวันที่อ่านไม่ได้ — ให้ผู้เรียก **ข้าม** ไป ไม่ใช่โชว์หัวกลุ่มเปล่า
 */
export function fmtDayGroup(iso: string, now: Date = new Date()): string {
  switch (dayGroupKind(iso, now)) {
    case 'today':
      return 'วันนี้'
    case 'yesterday':
      return 'เมื่อวาน'
    case 'date':
      return fmtDateShort(iso)
    default:
      return ''
  }
}

/**
 * 🏷️ **ชนิด** ของกลุ่มวัน — ใช้เมื่อผู้เรียกต้อง *ตัดสินใจ* จากชนิด ไม่ใช่แสดงป้าย
 *
 * ⭐ **ทำไมต้องแยกออกมาจาก `fmtDayGroup`:** `NotificationCenter.vue` ต้องรู้ว่าแถวควรโชว์
 *    "เวลาสัมพัทธ์" หรือ "เวลานาฬิกา" ซึ่งขึ้นกับว่าหัวกลุ่มเป็น `วันนี้`/`เมื่อวาน` หรือ
 *    วันที่จริง · ถ้ามันเทียบ **สตริงไทย** (`label === 'วันนี้'`) ตรง ๆ แล้วมีคนแก้คำใน
 *    `fmtDayGroup` เป็นอย่างอื่น (หรือแก้เป็น "เมื่อวานนี้") ตรรกะนั้นจะ **เงียบ ๆ ตกไปที่
 *    วันที่จริง** โดยไม่มีอะไรฟ้อง — ไม่ใช่ type error ไม่ใช่เทสต์พัง
 *    ⇒ ที่นี่คืนค่าที่ **เทียบได้แบบมี type คุม** (`DayGroupKind`) ⇒ แก้คำที่เดียวไม่มีผล
 *
 * ⚠️ **`now` ต้องเป็นค่าเดียวกันกับที่ส่งให้ `fmtDayGroup`** ถ้าผู้เรียกเรียกทั้งสอง
 *    ฟังก์ชันโดยไม่ส่ง `now` มันจะเรียก `new Date()` คนละครั้ง ⇒ ที่เส้นแบ่งวัน (เที่ยงคืน)
 *    ป้ายกับชนิดอาจไม่ตรงกันได้ · ในทางปฏิบัติห่างกันไม่ถึงมิลลิวินาที แต่ผู้เรียกที่ต้องการ
 *    ความถูกต้อง (เช่น computed ที่วนทั้งลิสต์) **ควรสร้าง `now` ตัวเดียวแล้วส่งไปทั้งคู่**
 *
 * ⚠️ `'invalid'` แยกออกมา ไม่ได้ยุบรวมกับ `'date'` — วันที่อ่านไม่ได้ต้องได้ *สตริงว่าง*
 *    ไม่ใช่ `fmtDateShort()` ที่จะพิมพ์ "Invalid Date" ให้ผู้ใช้เห็น
 */
export type DayGroupKind = 'today' | 'yesterday' | 'date' | 'invalid'

export function dayGroupKind(iso: string, now: Date = new Date()): DayGroupKind {
  const then = new Date(iso)
  if (Number.isNaN(then.getTime())) return 'invalid'

  const dayDiff = bangkokDayDiff(then, now)
  if (dayDiff === 0) return 'today'
  if (dayDiff === 1) return 'yesterday'
  return 'date'
}
