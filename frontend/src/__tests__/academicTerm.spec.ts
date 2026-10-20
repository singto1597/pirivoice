import { describe, it, expect } from 'vitest'
import { termYearLabel } from '@/types/academicTerm'

/**
 * 🗓️ ป้ายชื่อปีของการศึกษาในรายการภาคเรียน (P6)
 *
 * **ทำไมต้องมีเทสต์:** `academic_year_id` เป็น nullable โดยเจตนา (คอลัมน์มีตั้งแต่
 * migration 027) ⇒ ภาคเรียนเก่าที่ไม่มีปีจะยังอยู่ในฐานข้อมูลจริง ⇒ UI ต้อง **พูดได้**
 * ว่าภาคนี้ "ไม่ผูกปี" ไม่ใช่โชว์ช่องว่าง (ผู้ใช้อ่านว่าข้อมูลหาย)
 *
 * ⚠️ ชื่อปีที่หาไม่เจอ (ปีถูกลบ/ยังโหลดไม่เสร็จ) ต้อง fallback เป็นรหัส ไม่ใช่ `undefined`
 *    — ไม่งั้นป้ายจะขึ้นคำว่า "undefined" บนหน้าจอจริง
 */

describe('termYearLabel', () => {
  it('ผูกปีอยู่และรู้ชื่อ → คืนชื่อปี', () => {
    const years = new Map<number, string>([[2, 'ปีการศึกษา 2569']])
    expect(termYearLabel({ academic_year_id: 2 }, years)).toBe('ปีการศึกษา 2569')
  })

  it('ไม่ผูกปี (null) → บอกตรง ๆ ว่า "ไม่ผูกปี" ไม่ใช่ช่องว่าง', () => {
    expect(termYearLabel({ academic_year_id: null }, new Map())).toBe('ไม่ผูกปี')
  })

  it('ผูกปีแต่หาไม่เจอ → fallback รหัส (ห้ามขึ้น undefined)', () => {
    const label = termYearLabel({ academic_year_id: 7 }, new Map())
    expect(label).toContain('7')
    expect(label).not.toContain('undefined')
  })

  it('map ว่างกับ null ยังต่างกัน — ป้ายต้องแยกสองกรณีนี้ได้', () => {
    const empty = new Map<number, string>()
    expect(termYearLabel({ academic_year_id: null }, empty)).not.toBe(
      termYearLabel({ academic_year_id: 1 }, empty),
    )
  })
})
