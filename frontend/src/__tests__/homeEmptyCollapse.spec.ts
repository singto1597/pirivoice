/**
 * 🗜️ R6 · "ยุบบล็อกที่ว่าง" หน้าแรก — ตารางความจริงของทั้ง 5 บล็อก
 *
 * **ทำไมเทสต์ฟังก์ชันบริสุทธิ์ ไม่ mount `Home.vue`:**
 * หน้าแรกประกอบจาก 6+ คอมโพเนนต์ที่ยิง 4 API (home / reports / dashboard / notifications)
 * และทุกเส้นต้องมี router + Pinia ⇒ การ mount ทั้งหน้าในเทสต์จะผูกความถูกต้องของ *ตรรกะ*
 * ไว้กับความสมบูรณ์ของ *ฮาร์เนส* — พังเพราะ import ตัวหนึ่งมี side effect ไม่ได้แปลว่า
 * ตรรกะผิด (บทเรียนเดียวกับ `checkInCardState()` ใน `types/event.ts` ที่แยกด้วยเหตุผลนี้
 * และ `types/home.ts` เขียนเงื่อนไขทั้งหมดเป็นฟังก์ชันบริสุทธิ์เพื่อสิ่งนี้โดยตรง)
 *
 * 🔴 **เทสต์ที่คุ้มที่สุดในไฟล์นี้คือ "ห้ามยุบตอนยังไม่ควรยุบ":** ทั้ง 5 บล็อกใช้เงื่อนไข
 *    รูปแบบ `จำนวน === 0` ซึ่ง **ให้ผลเหมือนกันเป๊ะ** ระหว่าง "ว่างจริง" กับ "ยังโหลดไม่เสร็จ"
 *    กับ "โหลดพัง" ⇒ ถ้าเงื่อนไขหลุด `loading`/`error`/`loaded` ไปตัวเดียว ผู้ใช้จะเห็น
 *    "ไม่มีเรื่องค้างรอคุณ" **ตอนเซิร์ฟเวอร์ล่ม** ซึ่งอ่านแล้วเชื่อ 100% และมองไม่เห็นจาก UI
 *    ว่าผิด · เทสต์ทุกข้อที่ชื่อขึ้นต้นด้วย ★ คือเคสนั้น
 */
import { describe, expect, it } from 'vitest'
import {
  dashboardBlockState,
  myIssuesBlockState,
  pendingOnMeBlockState,
  personalStatsBlockState,
  reportQueueBlockState,
} from '@/types/home'
import { STAT_ITEMS, statsAllZero } from '@/types/me'
import type { PersonalStats, StatKey } from '@/types/me'
import type { MyIssueSummary } from '@/types/issue'

/**
 * สร้างสถิติที่ **0 ทุกช่อง** แล้วเปิดให้เติมเฉพาะช่องที่เคสนั้นสนใจ
 *
 * ⚠️ วนจาก `STAT_ITEMS` ไม่ใช่เขียน 6 คีย์เอง — เพิ่มตัวนับที่ 7 แล้วลืมเติมที่นี่
 *    จะได้ออบเจกต์ที่ขาดฟิลด์ ซึ่ง `statsAllZero()` จะอ่านเป็น `undefined !== 0` ⇒
 *    **ทุกเคสกลายเป็น "ไม่ยุบ" พร้อมกันทั้งไฟล์** โดยไม่มีใครรู้ว่าตั้งใจหรือพัง
 *    (การันตีว่าตรงกันจริงด้วย `satisfies` ของ `STAT_ITEMS` + type ของฟังก์ชันนี้)
 */
function stats(over: Partial<Record<StatKey, number>> = {}): PersonalStats {
  const zero = Object.fromEntries(STAT_ITEMS.map((i) => [i.key, 0])) as Record<StatKey, number>
  // `term: null` = ยังไม่ได้ตั้งภาคเรียน ⇒ นับทั้งหมด (ไม่ใช่ "ไม่มีข้อมูล" — ดู `types/me.ts`)
  return { term: null, ...zero, ...over }
}

function summary(total_issues: number): MyIssueSummary {
  return { total_issues, by_status: [], recent: [] }
}

// ─────────────────────────────────────────────────────────────
// 1. รอฉันตอบ — บล็อกเดียวที่ "ว่าง" ต้องจริงทั้งสองสัญญาณ
// ─────────────────────────────────────────────────────────────
describe('pendingOnMeBlockState — รอฉันตอบ', () => {
  /** ค่าตั้งต้น = "ผู้รับเรื่องที่โหลดเสร็จแล้ว และไม่มีอะไรค้าง" */
  const base = {
    canReceive: true,
    homeError: false,
    loading: false,
    pendingCount: 0,
    unreadCount: 0,
  }

  it('ไม่มีค้าง + ไม่มีอะไรยังไม่อ่าน → ยุบ', () => {
    expect(pendingOnMeBlockState(base)).toBe('collapsed')
  })

  it('มีเรื่องค้าง 1 เรื่อง → การ์ดเต็ม', () => {
    expect(pendingOnMeBlockState({ ...base, pendingCount: 1 })).toBe('full')
  })

  it('★ ค้าง 0 แต่ยังมีแจ้งเตือนที่ยังไม่อ่าน → การ์ดเต็ม (badge ต้องไม่หาย)', () => {
    // ยอด "รอฉันตอบ" = `current_assignee_id = ฉัน` · ยอด "ยังไม่อ่าน" = สถานะการอ่าน
    // ⇒ คนละชุดกัน · ถ้ายุบทั้งที่ unread > 0 ป้าย badge ที่หัวการ์ด (ซึ่งเป็น *สิ่งเดียว*
    //    ที่บอกว่ามีของใหม่) จะหายไปพร้อมหัวการ์ด ⇒ ผู้ใช้ไม่รู้ว่ามีของเข้าจนกว่าจะกดเข้าไปดู
    expect(pendingOnMeBlockState({ ...base, unreadCount: 3 })).toBe('full')
  })

  it('★ กำลังโหลด → การ์ดเต็ม (ห้ามประกาศ "ไม่มีค้าง" จากข้อมูลที่ยังไม่มา)', () => {
    expect(pendingOnMeBlockState({ ...base, loading: true })).toBe('full')
  })

  it('★ โหลดพัง (homeError) → ซ่อนทั้งบล็อก (การ์ด error มีอยู่แล้วที่อื่น)', () => {
    // 🔴 กับดักจริง: `pendingOnMe = home.value?.pending_on_me ?? []` ⇒ ตอนพัง ค่าคือ `[]`
    //    และ unread เป็น 0 ⇒ ถ้าไม่เช็ค `homeError` ที่นี่ **เงื่อนไข "ว่าง" จะเป็นจริง**
    //    แล้วหน้าแรกจะขึ้น "ไม่มีเรื่องค้างรอคุณ" ทั้งที่ความจริงคือ *เราไม่รู้*
    expect(pendingOnMeBlockState({ ...base, homeError: true })).toBe('hidden')
  })

  it('★ โหลดพัง + มีของค้างค้างอยู่ใน memory → ยังซ่อน (error ชนะเสมอ)', () => {
    expect(
      pendingOnMeBlockState({ ...base, homeError: true, pendingCount: 4, unreadCount: 2 }),
    ).toBe('hidden')
  })

  it('ไม่มีสิทธิ์รับเรื่อง → ซ่อน แม้โหลดเสร็จและว่าง', () => {
    expect(pendingOnMeBlockState({ ...base, canReceive: false })).toBe('hidden')
  })
})

// ─────────────────────────────────────────────────────────────
// 2. สรุปเรื่องของฉัน
// ─────────────────────────────────────────────────────────────
describe('myIssuesBlockState — สรุปเรื่องของฉัน', () => {
  const base = { homeError: false, loading: false, summary: summary(0) }

  it('ยังไม่เคยแจ้งเรื่อง (0) → ยุบ', () => {
    expect(myIssuesBlockState(base)).toBe('collapsed')
  })

  it('เคยแจ้ง → การ์ดเต็ม', () => {
    expect(myIssuesBlockState({ ...base, summary: summary(7) })).toBe('full')
  })

  it('★ กำลังโหลด → การ์ดเต็ม', () => {
    expect(myIssuesBlockState({ ...base, loading: true })).toBe('full')
  })

  it('★ โหลดพัง → ซ่อน', () => {
    expect(myIssuesBlockState({ ...base, homeError: true })).toBe('hidden')
  })

  it('★ ยังไม่รู้ (`summary === null`) → ซ่อน **ไม่ใช่** ยุบ', () => {
    // fail closed: null แปลว่า *ยังไม่รู้* ไม่ใช่ *ว่าง* ⇒ ห้ามขึ้น "ยังไม่เคยแจ้งเรื่อง"
    // จากข้อมูลที่ไม่มี — และห้ามขึ้นการ์ดเต็มด้วย (จะเรนเดอร์หัวการ์ดลอย ๆ)
    expect(myIssuesBlockState({ ...base, summary: null })).toBe('hidden')
  })
})

// ─────────────────────────────────────────────────────────────
// 3. สถิติของฉัน (ใช้กติกาเดียวกับ `PersonalStatsCard.vue`)
// ─────────────────────────────────────────────────────────────
describe('personalStatsBlockState — สถิติของฉัน', () => {
  const base = { homeError: false, loading: false, stats: stats() }

  it('0 ทุกช่อง → ยุบ', () => {
    expect(personalStatsBlockState(base)).toBe('collapsed')
  })

  it('มีตัวเลขแม้ช่องเดียว → การ์ดเต็ม', () => {
    expect(personalStatsBlockState({ ...base, stats: stats({ votes_cast: 1 }) })).toBe('full')
    expect(personalStatsBlockState({ ...base, stats: stats({ resolved_count: 2 }) })).toBe('full')
  })

  it('★ กำลังโหลด → การ์ดเต็ม (skeleton ต้องมีที่อยู่)', () => {
    expect(personalStatsBlockState({ ...base, loading: true })).toBe('full')
  })

  it('★ โหลดพัง → ซ่อน', () => {
    expect(personalStatsBlockState({ ...base, homeError: true })).toBe('hidden')
  })

  it('★ ยังไม่รู้ (`stats === null`) → ซ่อน', () => {
    expect(personalStatsBlockState({ ...base, stats: null })).toBe('hidden')
  })
})

describe('statsAllZero — กติกา "0 ทุกช่อง" ที่ใช้ร่วมกับการ์ด', () => {
  it('0 ทุกช่อง → true · มีตัวเดียวที่ไม่ใช่ 0 → false', () => {
    expect(statsAllZero(stats())).toBe(true)
    for (const item of STAT_ITEMS) {
      expect(statsAllZero(stats({ [item.key]: 1 }))).toBe(false)
    }
  })

  it('★ `null` → false (fail closed — "ยังไม่รู้" ไม่ใช่ "ว่าง")', () => {
    // ถ้าข้อนี้กลายเป็น true หน้าแรกจะขึ้น "ยังไม่มีสถิติในช่วงนี้" ทันทีที่ API ล่ม
    expect(statsAllZero(null)).toBe(false)
  })

  it('`term` ไม่ถูกนับเป็นตัวชี้วัด (null ภาค ≠ ไม่มีข้อมูล)', () => {
    expect(STAT_ITEMS.some((i) => (i.key as string) === 'term')).toBe(false)
  })
})

// ─────────────────────────────────────────────────────────────
// 4. คิวจัดการรายงาน (สภา/แอดมิน)
// ─────────────────────────────────────────────────────────────
describe('reportQueueBlockState — คิวจัดการรายงาน', () => {
  const base = {
    isCouncil: true,
    loading: false,
    loaded: true,
    error: false,
    count: 0,
  }

  it('ยิงเสร็จ · ไม่มีของ → ยุบ', () => {
    expect(reportQueueBlockState(base)).toBe('collapsed')
  })

  it('มีของในคิว → การ์ดเต็ม', () => {
    expect(reportQueueBlockState({ ...base, count: 3 })).toBe('full')
  })

  it('★ กำลังโหลด → การ์ดเต็ม', () => {
    expect(reportQueueBlockState({ ...base, loading: true })).toBe('full')
  })

  it('★ โหลดพัง → การ์ดเต็ม (กรอบการ์ดมีที่ให้ปุ่ม "ลองใหม่")', () => {
    expect(reportQueueBlockState({ ...base, error: true })).toBe('full')
  })

  it('★ ยังไม่เคยยิงเลย (`loaded === false`) → ซ่อน ห้ามยุบ', () => {
    // 🔴 เส้นทางจริง: `loadingReports` เริ่มที่ `isCouncil` และ `loadReports()` return ทันที
    //    เมื่อ `!isCouncil` ⇒ ถ้าสิทธิ์เพิ่งกลายเป็นจริง *หลัง* mount (MainLayout เรียก
    //    `loadMe()` ทีหลัง) จะได้ `loading === false` + `reports === []` **ทั้งที่ยังไม่เคย
    //    ถามเซิร์ฟเวอร์** ⇒ ยุบตอนนี้ = ประกาศ "คิวรายงานว่าง" จากอากาศ
    expect(reportQueueBlockState({ ...base, loaded: false })).toBe('hidden')
    expect(reportQueueBlockState({ ...base, loaded: false, count: 0 })).toBe('hidden')
  })

  it('ไม่ใช่สภา → ซ่อน แม้ทุกอย่างจะว่าง', () => {
    expect(reportQueueBlockState({ ...base, isCouncil: false })).toBe('hidden')
  })

  it('★ error ชนะ "ยังไม่เคยยิง" — ต้องไม่ซ่อนจนปุ่มลองใหม่หายไป', () => {
    // ลำดับการเช็คในฟังก์ชัน: error/loading ก่อน `loaded` ⇒ ตอนพังต้องเห็นการ์ด error
    // ไม่ใช่หายเงียบ ๆ (ซึ่งผู้ใช้จะไม่รู้เลยว่าคิวมีปัญหา)
    expect(reportQueueBlockState({ ...base, loaded: false, error: true })).toBe('full')
  })
})

// ─────────────────────────────────────────────────────────────
// 5. แดชบอร์ด (เดิมไม่มีสาขาสุดท้าย ⇒ หัวการ์ดลอย)
// ─────────────────────────────────────────────────────────────
describe('dashboardBlockState — ภาพรวมทั้งโรงเรียน', () => {
  const base = { canDashboard: true, loading: false, error: false, hasData: true }

  it('มีข้อมูล → การ์ดเต็ม', () => {
    expect(dashboardBlockState(base)).toBe('full')
  })

  it('★ ไม่มีข้อมูล (`dash === null`) → ซ่อน **ไม่ใช่** การ์ดหัวลอย', () => {
    // 🔴 ของเดิม `v-if` มีแค่ loading / error / dash ⇒ เมื่อทั้งสามเป็นเท็จ การ์ดจะขึ้น
    //    หัวการ์ด + ปุ่ม "เปิดแดชบอร์ด" **แต่เนื้อในว่างเปล่า** ซึ่งอ่านเป็น "โหลดค้าง"
    expect(dashboardBlockState({ ...base, hasData: false })).toBe('hidden')
  })

  it('กำลังโหลด → การ์ดเต็ม (skeleton ต้องมีที่อยู่)', () => {
    expect(dashboardBlockState({ ...base, loading: true, hasData: false })).toBe('full')
  })

  it('โหลดพัง → การ์ดเต็ม (กรอบการ์ดมีที่ให้ปุ่ม "ลองใหม่")', () => {
    expect(dashboardBlockState({ ...base, error: true, hasData: false })).toBe('full')
  })

  it('ไม่มีสิทธิ์ → ซ่อน', () => {
    expect(dashboardBlockState({ ...base, canDashboard: false })).toBe('hidden')
  })
})

// ─────────────────────────────────────────────────────────────
// 6. กติการ่วมของทั้งชุด
// ─────────────────────────────────────────────────────────────
describe('กติการ่วม — ทุกบล็อกต้องไม่ประกาศ "ว่าง" จากสถานะที่ยังไม่รู้', () => {
  it('★ ไม่มีฟังก์ชันไหนคืน `collapsed` ขณะกำลังโหลด', () => {
    const loading = [
      pendingOnMeBlockState({
        canReceive: true,
        homeError: false,
        loading: true,
        pendingCount: 0,
        unreadCount: 0,
      }),
      myIssuesBlockState({ homeError: false, loading: true, summary: summary(0) }),
      personalStatsBlockState({ homeError: false, loading: true, stats: stats() }),
      reportQueueBlockState({
        isCouncil: true,
        loading: true,
        loaded: false,
        error: false,
        count: 0,
      }),
      dashboardBlockState({ canDashboard: true, loading: true, error: false, hasData: false }),
    ]
    expect(loading).not.toContain('collapsed')
  })

  it('★ ไม่มีฟังก์ชันไหนคืน `collapsed` ตอนพัง', () => {
    const errored = [
      pendingOnMeBlockState({
        canReceive: true,
        homeError: true,
        loading: false,
        pendingCount: 0,
        unreadCount: 0,
      }),
      myIssuesBlockState({ homeError: true, loading: false, summary: summary(0) }),
      personalStatsBlockState({ homeError: true, loading: false, stats: stats() }),
      reportQueueBlockState({
        isCouncil: true,
        loading: false,
        loaded: true,
        error: true,
        count: 0,
      }),
      dashboardBlockState({ canDashboard: true, loading: false, error: true, hasData: false }),
    ]
    expect(errored).not.toContain('collapsed')
  })

  it('★ ทุกฟังก์ชันคืนได้แค่ 3 สถานะที่ประกาศไว้ (ไม่มีการพิมพ์ผิดหลุดเป็น string อื่น)', () => {
    const all = [
      pendingOnMeBlockState({
        canReceive: true,
        homeError: false,
        loading: false,
        pendingCount: 0,
        unreadCount: 0,
      }),
      myIssuesBlockState({ homeError: false, loading: false, summary: summary(1) }),
      personalStatsBlockState({ homeError: false, loading: false, stats: stats() }),
      reportQueueBlockState({
        isCouncil: true,
        loading: false,
        loaded: true,
        error: false,
        count: 2,
      }),
      dashboardBlockState({ canDashboard: true, loading: false, error: false, hasData: true }),
    ]
    for (const s of all) expect(['hidden', 'collapsed', 'full']).toContain(s)
  })
})
