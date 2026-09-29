// 🔇 Quiet Hours (A8) — ช่วงเวลาที่โรงเรียนไม่ส่ง push
//
// ⚠️ **คนละเรื่องกับ "ตั้งค่าการแจ้งเตือน" (A2) โดยสิ้นเชิง** — อย่าสับสน:
//    · A2 (`notification_preferences`) = "ฉันขอปิดกลุ่มนี้"  → ของคนคนเดียว  → เงียบทั้ง in-app และ push
//    · A8 (`app_settings.quiet_hours`)  = "โรงเรียนขอความสงบ" → ของทั้งโรงเรียน → **เงียบเฉพาะ push**
//      (แถวใน `notifications` ยังถูกสร้างครบ ⇒ เปิดแอพดูยังเห็นครบ ไม่มีอะไรหาย)
//
// ⚠️ **เขตเวลา `Asia/Bangkok` ตายตัว** — backend ตีความ `start`/`end` เป็นเวลาไทยเสมอ
//    ไม่ใช่เวลาของเครื่องผู้ใช้ ⇒ **ห้ามเอา `new Date()` มาคำนวณ "ตอนนี้อยู่ในช่วงไหม" ที่นี่**
//    คำตอบนั้นเป็นของ backend (`enabled` ที่ได้มาคือค่าที่ตั้งไว้ ไม่ใช่ "กำลังทำงานอยู่ไหม")

export interface QuietHours {
  enabled: boolean
  start: string // "HH:MM" — เขตไทย
  end: string // "HH:MM" — ★ น้อยกว่า start ได้ = ช่วงข้ามเที่ยงคืน (22:00–06:00)
  // ⚠️ null = **โรงเรียนยังไม่เคยตั้งค่านี้** (ยังไม่มีแถวใน app_settings)
  //    ⇒ ค่าที่เห็นเป็น "ค่าเริ่มต้นที่ UI เสนอ" ไม่ใช่ค่าที่ระบบบังคับใช้
  //    ⇒ UI ต้องเขียนกำกับให้ต่างจากกรณี "ตั้งไว้แล้วแต่ปิดสวิตช์" (updated_at มีค่า)
  updated_at: string | null
}

// PUT = full replace ⇒ ส่งครบทั้ง 3 ฟิลด์เสมอ (ไม่มี optional โดยเจตนา)
export interface QuietHoursPayload {
  enabled: boolean
  start: string
  end: string
}

// ค่าที่ UI เริ่มต้นให้เห็นเมื่อโรงเรียนยังไม่เคยตั้ง — **ต้องตรงกับ backend**
// (`app_settings_service.DEFAULT_START/DEFAULT_END`) ไม่งั้นกด "เปิด" ครั้งแรก
// จะได้ช่วงเวลาที่ไม่ตรงกับที่หน้าจอโชว์ไว้
export const QUIET_HOURS_DEFAULT_START = '22:00'
export const QUIET_HOURS_DEFAULT_END = '06:00'

// ทางลัดที่โรงเรียนนี้ใช้จริง — ลดการพิมพ์บนมือถือ (ยังแก้เป็นค่าอื่นได้)
export const QUIET_HOURS_PRESETS: Array<{ label: string; start: string; end: string }> = [
  { label: 'กลางคืน 22:00–06:00', start: '22:00', end: '06:00' },
  { label: 'ดึก 23:00–05:00', start: '23:00', end: '05:00' },
  { label: 'ช่วงสอบ 20:00–07:00', start: '20:00', end: '07:00' },
]
