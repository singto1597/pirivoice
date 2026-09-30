/**
 * 🧪 R1.5 · ปลายทางของ deep link **resolve ผ่าน router จริงได้ทุกอัน**
 *
 * **ทำไมต้องมี ทั้งที่ `deepLink.spec.ts` ครบ 14 เคสแล้ว:**
 * `deepLink.spec.ts` ตรวจว่า `deepLinkTarget()` คืน **ชื่อ route ที่ถูกต้อง** โดยเทียบกับ
 * *ตารางสตริง* ที่ลอกมาจากฝั่ง backend — มันตอบคำถาม "เราตัดสินใจถูกไหม"
 * แต่ **ไม่เคยถาม router ว่ามี route ชื่อนั้นอยู่จริงหรือเปล่า** ⇒ ช่องว่างที่เทสต์นั้นมองไม่เห็น:
 *
 *   🔴 **มีคนเปลี่ยนชื่อ route** (เช่น `board-detail` → `board`) แล้วแก้เทสต์ฝั่งตรรกะตาม
 *      ⇒ `deepLink.spec.ts` **เขียวทั้งไฟล์** เพราะมันเทียบสตริงกันเองสองฝั่ง
 *      แต่ผู้ใช้กด notification แล้วได้ `not-found` — ซึ่ง **`not-found` ถูกออกแบบให้
 *      พาไป login พร้อม `?redirect=`** ⇒ อาการที่ผู้ใช้เห็นคือ **"กดแจ้งเตือนแล้วออกจากระบบ"**
 *      กลไกเดียวกับ `moreRoute.spec.ts` เป๊ะ ๆ
 *
 * ⭐ **สิ่งที่เทสนี้ยึด — ปิดวงจร 3 ขั้น:** `NotificationItem` → `deepLinkTarget()` →
 *    `router.resolve()` → **path จริง**
 *    ขั้นสุดท้ายคือสิ่งที่ผู้ใช้เห็นในแถบที่อยู่ และเป็นสัญญาเดียวกับที่
 *    `backend/services/push_service.py::_deep_link_url()` สร้างขึ้นเอง
 *    ⇒ ถ้า path ที่ router ผลิตไม่ตรงกับที่ backend ฝังใน push ผู้ใช้จะเจอ
 *    **สองพฤติกรรมจาก notification อันเดียวกัน** (กดในแอปไปที่หนึ่ง กดจาก push ไปอีกที่)
 *
 * ⚠️ **ใช้ `router.resolve()` ไม่ใช่ `router.push()` โดยเจตนา** — `resolve()` ไม่รัน
 *    navigation guard ⇒ **ไม่ต้องมี Pinia / ไม่ต้องล็อกอิน** (ตามที่แผน R1.5 ระบุว่า
 *    เทสนี้ควรมี "ราคาถูก") · และเราต้องการตรวจ *ตาราง route* ไม่ใช่ *ผลของ guard*
 *    ซึ่ง `redirectRoute.spec.ts` ครอบอยู่แล้ว
 */
import { describe, expect, it } from 'vitest'
import router from '@/router'
import { deepLinkTarget } from '@/router/deepLink'
import type { DeepLinkSource, DeepLinkTarget } from '@/router/deepLink'

/** สร้าง source ขั้นต่ำ — ค่าเริ่มต้นคือ "ไม่มีอะไรเลย" แล้วให้แต่ละเคสเติมเฉพาะที่ต้องการ */
function source(over: Partial<DeepLinkSource>): DeepLinkSource {
  return {
    group_type: 'issue_mine',
    type: 'issue_created',
    entity_type: null,
    entity_id: null,
    board_id: null,
    ...over,
  }
}

/**
 * 🔴 **path ที่ปลายทางต้องผลิตออกมาได้** — คอลัมน์นี้คือสัญญาข้ามภาษา
 *
 * ⚠️ เพิ่มชนิด notification ใหม่ = เพิ่มแถวที่นี่ **และ** ที่
 *    `backend/tests/test_push_outbox.py::_DEEP_LINK_CASES` — ถ้าลืมที่ใดที่หนึ่ง
 *    ตารางของอีกฝั่งจะยังผ่าน (ดูคำเตือนเดียวกันใน `deepLink.spec.ts`)
 */
interface Case {
  /** อธิบายว่าเคสนี้คือ *สาขาที่เท่าไร* ของ `deepLinkTarget()` (ลำดับในคอมเมนต์หัวฟังก์ชัน) */
  branch: string
  input: DeepLinkSource
  /** path ที่ต้องได้หลังผ่าน router — `null` = ต้องไม่ต้องไปไหน */
  path: string | null
}

const CASES: Case[] = [
  // 1️⃣ กลุ่ม report + ชนิด report_new → คิวรายงาน (ต้องชนะ board_id ที่พกมาด้วย)
  {
    branch: '1 · report_new → คิวรายงาน',
    input: source({ group_type: 'report', type: 'report_new', entity_type: 'board', entity_id: 7, board_id: 7 }),
    path: '/app/boards/reports',
  },
  // 2️⃣ กลุ่ม report ชนิดอื่น ที่มี board_id → ตัวบอร์ด (ผู้แจ้งต้องไปดูบอร์ด ไม่ใช่คิวของสภา)
  {
    branch: '2 · report_actioned → ตัวบอร์ด',
    input: source({ group_type: 'report', type: 'report_actioned', board_id: 12 }),
    path: '/app/boards/12',
  },
  // 3️⃣ กลุ่ม announcement → Home (ที่ที่ประกาศถูกแสดงทั้งก้อน)
  {
    branch: '3 · ประกาศ → Home',
    input: source({ group_type: 'announcement', type: 'announcement_new', entity_type: 'announcement', entity_id: 3 }),
    path: '/app/home',
  },
  // 4️⃣ กลุ่ม event → ตัวกิจกรรม (ต้องชนะ board_id ถ้ามีมาด้วย)
  {
    branch: '4 · กิจกรรม → ตัวกิจกรรม',
    input: source({ group_type: 'event', type: 'event_new', entity_type: 'event', entity_id: 21, board_id: 21 }),
    path: '/app/events/21',
  },
  // 5️⃣ entity_type = issue + entity_id → หน้ารายละเอียดเรื่อง
  {
    branch: '5 · เรื่อง → รายละเอียดเรื่อง',
    input: source({ entity_type: 'issue', entity_id: 55 }),
    path: '/app/issues/55',
  },
  // 6️⃣ เหลือแค่ board_id → หน้าบอร์ด
  {
    branch: '6 · board_id เดี่ยว → หน้าบอร์ด',
    input: source({ group_type: 'board', type: 'board_comment', board_id: 4 }),
    path: '/app/boards/4',
  },
  // 🚪 ทางออกที่ต้องไม่สร้าง path พัง — ไม่เข้าเงื่อนไขใด → `null` (อยู่ที่รายการต่อ)
  {
    branch: '∅ ไม่มีอะไรชี้ → null',
    input: source({ type: 'unknown_kind' }),
    path: null,
  },
  // ⚠️ entity_type=issue แต่ entity_id เป็น NULL — ห้ามกลายเป็น `/app/issues/null`
  {
    branch: '∅ issue ที่ไม่มี id → null',
    input: source({ entity_type: 'issue', entity_id: null }),
    path: null,
  },
  // ⚠️ กิจกรรมที่ entity_id เป็น NULL → **ลิสต์กิจกรรม** ไม่ใช่ null และไม่ใช่ /app/events/null
  {
    branch: '4′ กิจกรรมที่ไม่มี id → ลิสต์กิจกรรม',
    input: source({ group_type: 'event', type: 'event_new', entity_type: 'event', entity_id: null }),
    path: '/app/events',
  },
]

/**
 * resolve เป้าหมาย → ชื่อ route + path จริง
 *
 * ⚠️ **คืนค่าออกมา ไม่ assert ในนี้** — เทสต์ต้องรวบรวม *ทุก* เคสที่พังแล้วรายงานทีเดียว
 *    (และ `expect` ที่มีข้อความอธิบายเป็นอาร์กิวเมนต์ที่ 2 ถูก oxlint ห้าม)
 */
function resolveOf(target: DeepLinkTarget): { name: string | undefined; path: string | null } {
  if (target === null) return { name: undefined, path: null }
  const resolved = router.resolve(target)
  return { name: typeof resolved.name === 'string' ? resolved.name : undefined, path: resolved.path }
}

describe('R1.5 · deep link ทุกสาขาต้อง resolve เป็น route จริง', () => {
  it('★ G1: ทุกสาขาของ `deepLinkTarget()` → path ที่ router ผลิตได้ตรงตามสัญญา', () => {
    const wrong = CASES.map((c) => ({ c, got: resolveOf(deepLinkTarget(c.input)) }))
      .filter(({ c, got }) => got.name === 'not-found' || got.path !== c.path)
      .map(({ c, got }) => `${c.branch} — ควรได้ ${String(c.path)} แต่ได้ ${String(got.path)} (route: ${String(got.name)})`)

    expect(wrong).toEqual([])
  })

  it('★ G2: **ไม่มีสาขาใดตกไป catch-all** — `not-found` คือ "กดแจ้งเตือนแล้วออกจากระบบ"', () => {
    const broken = CASES.filter((c) => {
      const target = deepLinkTarget(c.input)
      if (target === null) return false
      return router.resolve(target).name === 'not-found'
    }).map((c) => c.branch)

    expect(broken).toEqual([])
  })

  it('G3: เป้าหมาย literal ทั้ง 6 รูปแบบ resolve ได้ (ไม่ผูกกับตรรกะของ notification)', () => {
    // ⚠️ `DeepLinkTarget` เป็น union ปิด ⇒ ถ้ามีคนเพิ่มสมาชิกใหม่แล้วลืมเพิ่มที่นี่
    //    `type-check` จะ **ไม่ฟ้อง** (เพราะเทสต์ยังคอมไพล์ได้) แต่ G1 จะฟ้องเมื่อมีเคสใช้มัน
    //    ⇒ ที่นี่เขียนครบทั้ง 6 เพื่อให้ "รายการปลายทางที่ระบบรู้จัก" ปรากฏที่เดียว
    const literals: DeepLinkTarget[] = [
      { name: 'home' },
      { name: 'events' },
      { name: 'event-detail', params: { id: 1 } },
      { name: 'issue-detail', params: { id: 1 } },
      { name: 'board-detail', params: { id: 1 } },
      { name: 'board-reports' },
    ]

    const broken = literals
      .filter((t) => t !== null && router.resolve(t).name === 'not-found')
      .map((t) => JSON.stringify(t))

    expect(broken).toEqual([])
  })

  it('G4: `id` ถูกส่งผ่านเป็น param จริง ไม่ถูกกลืนหายตอน resolve', () => {
    // 🔴 `params: { id }` ที่พิมพ์ผิดเป็น `params: { issueId }` จะ resolve "สำเร็จ"
    //    แต่ได้ path `/app/issues/undefined` ซึ่ง **ไม่ตก catch-all** (match `:id` ได้)
    //    ⇒ G1 จับได้ก็ต่อเมื่อ path ไม่ตรง — ข้อนี้จับ *กลไก* ตรง ๆ ว่า id ถึงปลายทาง
    const t = deepLinkTarget(source({ entity_type: 'issue', entity_id: 4242 }))
    expect(t).not.toBeNull()
    if (t === null) return

    const resolved = router.resolve(t)
    expect(resolved.params.id).toBe('4242')
    expect(resolved.path).not.toMatch(/undefined|null|NaN/)
  })

  it('G5: `/app` เป็นรากของทุกปลายทาง (ไม่มีอันไหนหลุดออกนอก shell)', () => {
    // ⚠️ ปลายทางที่อยู่นอก `/app` แปลว่าไม่มีหัวแถบ/แถบล่าง ⇒ ผู้ใช้ติดอยู่ในหน้านั้น
    const outside = CASES.map((c) => resolveOf(deepLinkTarget(c.input)).path)
      .filter((p): p is string => p !== null)
      .filter((p) => !p.startsWith('/app/'))

    expect(outside).toEqual([])
  })
})
