import { describe, it, expect } from 'vitest'
import {
  CATEGORY_ICONS,
  CATEGORY_LABELS,
  EVENT_CATEGORIES,
  categoryIcon,
  categoryLabel,
  categoryPayload,
  isEventCategory,
} from '@/types/event'

/**
 * 🏷️ หมวดกิจกรรม (D4) — กติกาของคีย์ ↔ ป้าย ↔ payload
 *
 * เทสต์นี้ทำงานกับ **ฟังก์ชันบริสุทธิ์** ไม่ได้ mount `EventManagement.vue` ตามแบบที่โปรเจกต์นี้ใช้
 * (เส้นแบ่งเดียวกับ `checkInCard.spec.ts`: "กติกาย้ายออกมาอยู่นอกเทมเพลต แล้วเทสต์กติกา")
 *
 * ⚠️ ที่ต้องเทสต์จริง ๆ ไม่ใช่ "ป้ายถูกไหม" (อ่านก็รู้) แต่คือ **พฤติกรรมกับคีย์ที่ frontend
 *    ไม่รู้จัก** — backend ประกาศ `EventOut.category` เป็น `str` (หลวมโดยเจตนา) ⇒ วันที่ backend
 *    เพิ่มหมวดใหม่ หน้าจอต้องไม่พัง และ **ต้องไม่เขียนทับค่าเดิมเงียบ ๆ**
 */

/** คีย์ที่ backend อาจส่งมาในอนาคต — ไม่มีใน `EVENT_CATEGORIES` ของวันนี้ */
const UNKNOWN = 'hackathon'

describe('ทะเบียนหมวด — ความครบถ้วน', () => {
  it('ทุกหมวดใน EVENT_CATEGORIES มีป้ายและไอคอน (และไม่มีคีย์ซ้ำ)', () => {
    expect(new Set(EVENT_CATEGORIES).size).toBe(EVENT_CATEGORIES.length)

    for (const c of EVENT_CATEGORIES) {
      // ⚠️ ถ้าลืมเพิ่มป้าย ป้ายจะกลายเป็นคีย์ดิบ (อังกฤษ) หลุดไปให้นักเรียนเห็น
      expect({ c, label: CATEGORY_LABELS[c] }).toEqual({ c, label: expect.any(String) })
      expect(CATEGORY_LABELS[c]).not.toBe(c)
      expect(CATEGORY_LABELS[c].trim()).not.toBe('')
      expect(CATEGORY_ICONS[c]).toMatch(/^bi-/)
    }
  })

  it('★ ไม่มีป้ายที่ไม่มีปุ่มกรอง — ทุกคีย์ใน CATEGORY_LABELS ต้องอยู่ใน EVENT_CATEGORIES', () => {
    // ทิศทางนี้สำคัญ: `Record<EventCategory, string>` บังคับให้ **ป้ายครบ** อยู่แล้ว (type-check)
    // แต่ไม่ได้บังคับว่ามัน **โผล่ใน dropdown** ⇒ หมวดที่มีป้ายแต่ไม่อยู่ใน EVENT_CATEGORIES
    // จะกรองไม่ได้เลย และหาสาเหตุยากมาก ("มีกิจกรรมหมวดนี้ แต่เลือกในตัวกรองไม่เจอ")
    for (const key of Object.keys(CATEGORY_LABELS)) {
      expect(EVENT_CATEGORIES).toContain(key)
    }
  })

  it('`other` อยู่ท้ายสุด — มันคือ "ไม่เข้าพวก" ไม่ใช่หมวดหนึ่งในรายการ', () => {
    // ถ้าไปอยู่กลางลิสต์ ผู้ใช้ต้องกวาดตาผ่าน "อื่น ๆ" เพื่อหาหมวดจริง ⇒ วางท้ายเสมอ
    expect(EVENT_CATEGORIES[EVENT_CATEGORIES.length - 1]).toBe('other')
  })
})

describe('categoryLabel / categoryIcon — ต้องไม่คืนค่าว่างกับคีย์แปลก', () => {
  it('คีย์ที่รู้จัก → ป้ายไทย และไอคอนจริง', () => {
    expect(categoryLabel('sports')).toBe('กีฬา/นันทนาการ')
    expect(categoryIcon('sports')).toBe('bi-trophy')
  })

  it('★ คีย์ที่ไม่รู้จัก → คืน **คีย์ดิบ** ไม่ใช่ "" และไม่ใช่ undefined', () => {
    // 🚨 อาการที่เทสต์นี้กัน: ป้ายขึ้นเป็นช่องว่างในหน้าจอ แล้วอ่านไม่ออกว่า "ไม่มีหมวด"
    //    หรือ "ระบบพัง" · การเห็นคำว่า `hackathon` บนจออย่างน้อยก็บอกความจริงว่าเกิดอะไร
    expect(categoryLabel(UNKNOWN)).toBe(UNKNOWN)
    expect(categoryIcon(UNKNOWN)).toBe('bi-tag')
  })

  it('สตริงว่างก็ไม่ทำให้ป้ายยุบหาย (ไอคอนยังต้องมี)', () => {
    expect(categoryIcon('')).toBe('bi-tag')
  })
})

describe('isEventCategory — ด่านแคบชนิด', () => {
  it('จริงสำหรับคีย์ที่รู้จักทุกตัว', () => {
    for (const c of EVENT_CATEGORIES) expect(isEventCategory(c)).toBe(true)
  })

  it('เท็จสำหรับคีย์แปลก · สตริงว่าง · และตัวพิมพ์ใหญ่', () => {
    expect(isEventCategory(UNKNOWN)).toBe(false)
    expect(isEventCategory('')).toBe(false)
    // ⚠️ ค่ามาจาก DB/querystring ⇒ ต้องไม่ใจดีกับตัวพิมพ์ · 'OTHER' ไม่ใช่ 'other'
    expect(isEventCategory('OTHER')).toBe(false)
  })
})

describe('★ categoryPayload — ห้ามประดิษฐ์ค่าแทนคีย์ที่ไม่รู้จัก', () => {
  it('คีย์ที่รู้จักผ่านไปทั้งดุ้น', () => {
    expect(categoryPayload('arts')).toBe('arts')
  })

  it('`other` ผ่านไปด้วย — มันคือ **ค่าจริง** ไม่ใช่ถังพักของ "ไม่รู้จัก"', () => {
    // 🚨 นี่คือเส้นแบ่งทั้งหมดของ D4: ถ้า `categoryPayload` คืน 'other' แทนคีย์แปลก
    //    เทสต์ข้อนี้จะยังผ่าน แต่ข้อถัดไปจะพัง — เก็บทั้งคู่ไว้ด้วยกัน
    expect(categoryPayload('other')).toBe('other')
  })

  it('★ คีย์ที่ไม่รู้จัก → `undefined` (ไม่ส่ง) **ไม่ใช่ `other`**', () => {
    expect(categoryPayload(UNKNOWN)).toBeUndefined()
    expect(categoryPayload('')).toBeUndefined()
  })

  it('★ สองข้างของการเทียบ diff ได้ค่าเดียวกัน ⇒ PATCH ไม่มีฟิลด์หมวด ⇒ ค่าเดิมไม่ถูกทับ', () => {
    // จำลองสิ่งที่ `buildPatch()` ทำ: `buildCreate()` (จากฟอร์ม) เทียบกับ `toBaseline()` (จากแถว)
    // ทั้งคู่ผ่าน `categoryPayload()` ตัวเดียวกัน ⇒ คีย์แปลกจาก DB ไม่กลายเป็น "เปลี่ยน"
    const fromRow = categoryPayload(UNKNOWN)
    const fromForm = categoryPayload(UNKNOWN)
    expect(fromRow === fromForm).toBe(true)

    // และถ้าผู้ใช้ **เลือกเองว่า "อื่น ๆ"** นั่นคือการตัดสินใจจริง ⇒ ต้องถูกส่ง (ต่างจาก undefined)
    const chosen = categoryPayload('other')
    expect(chosen === fromRow).toBe(false)
  })
})
