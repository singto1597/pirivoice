/**
 * 🧪 `router/deepLink.ts` — "กด notification แล้วไปไหน" (A4)
 *
 * **ทำไมต้องมีเทสนี้:** ปลายทางถูกตัดสิน **สองที่คนละภาษา** — ที่นี่ (ในแอพ) และ
 * `backend/services/push_service.py::_deep_link_url()` (payload ของ push)
 * ⇒ ถ้าไม่ตรงกัน ผู้ใช้จะเจอ **สองพฤติกรรมจาก notification อันเดียวกัน** คือ
 * กดในแอปไปที่หนึ่ง กดจาก push ไปอีกที่หนึ่ง · ทั้งสองทาง "ดูถูก" แยกกัน
 * ⇒ ไม่มี error ไม่มี log และไม่มีใครบ่นเป็นคำที่หาสาเหตุได้
 *
 * ⭐ **ตาราง `DEEP_LINK_CASES` ข้างล่างคือสำเนาของตารางเดียวกันใน
 *    `backend/tests/test_push_outbox.py::_DEEP_LINK_CASES`** — คอลัมน์สุดท้าย
 *    เป็น **path สตริง** ไม่ใช่ชื่อ route โดยเจตนา ⇒ เทียบข้ามภาษาได้ตรง ๆ
 *    (ฝั่ง backend assert สตริงนั้น ฝั่งนี้แปลง route → สตริงเดียวกันแล้ว assert)
 *    **เพิ่มชนิด notification ใหม่ = เพิ่มสองที่** และถ้าลืมที่ใดที่หนึ่ง
 *    ตารางเทสต์ของอีกฝั่งจะยังผ่าน ⇒ ต้องดูสองที่คู่กัน (ระบุไว้ในคอมเมนต์ของทั้งคู่)
 *
 * ⚠️ **ตัวที่ตรึง "ลำดับ" คือ `report_new`** — notification ชนิดนี้พก `board_id`
 *    มาด้วย ถ้าสลับข้อ 1 กับข้อ 3 คำตอบจะกลายเป็น `/app/boards/3` ซึ่งดูสมเหตุสมผล
 *    (มันคือบอร์ดที่ถูกรายงานนั่นแหละ) แต่ผิดเจตนา — ต้องพาสภาฯ ไป **คิวงาน**
 */
import { describe, expect, it } from 'vitest'
import type { NotificationGroup } from '@/types/notification'
import { deepLinkTarget, type DeepLinkSource, type DeepLinkTarget } from '@/router/deepLink'

/**
 * ด่าน compile-time: `Record<NotificationGroup, true>` **บังคับให้ครบทุกสมาชิก**
 * ⇒ วันที่มีคนเพิ่มกลุ่มที่ 5 ใน `NotificationGroup` ไฟล์นี้จะ **ไม่คอมไพล์**
 *   จนกว่าจะมีการระบุว่ากลุ่มนั้นมี notification ชนิดใด และไปที่ไหน
 *
 * (ใช้ `Object.keys` ต่อ ⇒ ตัวแปรนี้ "ถูกใช้" จริง ไม่ใช่ของประดับที่ lint ฟ้อง)
 */
const GROUP_COVERAGE: Record<NotificationGroup, true> = {
  issue_mine: true,
  issue_received: true,
  board: true,
  report: true,
}
const ALL_GROUPS = Object.keys(GROUP_COVERAGE) as NotificationGroup[]

/** แปลง route → path แบบเดียวกับที่ฝั่ง backend สร้าง (ให้เทียบข้ามภาษาได้ตรง ๆ) */
function targetToPath(t: DeepLinkTarget): string {
  if (!t) return '/app/notifications'
  if (t.name === 'board-reports') return '/app/boards/reports'
  if (t.name === 'board-detail') return `/app/boards/${t.params.id}`
  return `/app/issues/${t.params.id}`
}

/**
 * ⭐ ตารางเดียวกับ `_DEEP_LINK_CASES` ฝั่ง backend — **ชนิดจริงทั้ง 9 แบบ**
 * ที่ระบบผลิตได้ (วัดจาก call site ทั้ง 13 จุดใน `backend/services/`)
 *
 * ⚠️ `null` ในคอลัมน์ `board_id` คือ `NULL` ของ SQL จริง ไม่ใช่ "ไม่มีคีย์"
 */
const DEEP_LINK_CASES: ReadonlyArray<
  readonly [string, NotificationGroup, string, number | null, number | null, string]
> = [
  ['issue_update', 'issue_mine', 'issue', 12, null, '/app/issues/12'],
  ['issue_new', 'issue_received', 'issue', 12, null, '/app/issues/12'],
  ['issue_comment', 'issue_mine', 'issue', 12, null, '/app/issues/12'],
  ['issue_comment', 'issue_received', 'issue', 12, null, '/app/issues/12'],
  ['board_reply', 'board', 'piri_board_comment', 55, 3, '/app/boards/3'],
  ['board_new', 'board', 'piri_board', 3, 3, '/app/boards/3'],
  ['board_hidden', 'board', 'piri_board', 3, 3, '/app/boards/3'],
  ['report_new', 'report', 'piri_board_report', 9, 3, '/app/boards/reports'],
  ['report_actioned', 'report', 'piri_board_report', 9, 3, '/app/boards/3'],
]

function source(
  type: string,
  group_type: NotificationGroup,
  entity_type: string,
  entity_id: number | null,
  board_id: number | null,
): DeepLinkSource {
  return { group_type, type, entity_type, entity_id, board_id }
}

describe('deepLinkTarget — ปลายทางของทุกชนิด notification จริง', () => {
  it.each(DEEP_LINK_CASES)(
    'D1: %s (%s) → %s',
    (type, group, entityType, entityId, boardId, expected) => {
      expect(targetToPath(deepLinkTarget(source(type, group, entityType, entityId, boardId)))).toBe(
        expected,
      )
    },
  )

  it.each(DEEP_LINK_CASES)(
    'D2: %s — ปลายทางต้องอยู่ในแอพเสมอ (ขึ้นต้น /app/ ไม่มี // ไม่มี null หลุด)',
    (type, group, entityType, entityId, boardId) => {
      const path = targetToPath(deepLinkTarget(source(type, group, entityType, entityId, boardId)))
      expect(path.startsWith('/app/')).toBe(true)
      // protocol-relative URL พาออกนอกแอพได้ (open redirect) — กันตั้งแต่ต้นทาง
      expect(path).not.toContain('//')
      expect(path).not.toContain('null')
      expect(path).not.toContain('undefined')
    },
  )

  it('D3: ทุกกลุ่มใน NotificationGroup มีเคสอยู่ในตาราง', () => {
    const covered = new Set(DEEP_LINK_CASES.map((c) => c[1]))
    // ⚠️ assert เป็น "รายการที่ขาด" ไม่ใช่ `expect(...).toBe(true)` ในลูป — เพราะเวลา fail
    //    ข้อความจะบอกทันทีว่ากลุ่มไหนหาย (เทสต์ที่ fail แล้วต้องรู้ว่าต้องแก้อะไร)
    const missing = ALL_GROUPS.filter((g) => !covered.has(g))
    expect(missing).toEqual([])
  })
})

describe('deepLinkTarget — กับดักที่ทำให้ "ดูเหมือนถูก"', () => {
  it('D4: 🚨 report_new ต้องชนะ board_id — ห้ามตกไปที่ตัวบอร์ด', () => {
    const path = targetToPath(
      deepLinkTarget(source('report_new', 'report', 'piri_board_report', 9, 3)),
    )
    expect(path).toBe('/app/boards/reports')
    // ตกไปที่บอร์ด = อาการของลำดับที่สลับ (ข้อ 1 กับข้อ 3) — assert แยกเพื่อให้ข้อความ fail ชี้ตรง
    expect(path).not.toBe('/app/boards/3')
  })

  it('D5: report ชนิดอื่นที่ไม่มี board_id → null (อยู่ที่รายการ ไม่สร้าง path พัง)', () => {
    expect(deepLinkTarget(source('report_actioned', 'report', 'piri_board_report', 9, null))).toBe(
      null,
    )
  })

  it('D6: 🚨 entity_type=issue แต่ entity_id เป็น NULL → ห้ามสร้าง /app/issues/null', () => {
    // ต้องตกไปใช้ board_id ก่อน แล้วจึงเป็น null
    expect(
      targetToPath(deepLinkTarget(source('issue_update', 'issue_mine', 'issue', null, 7))),
    ).toBe('/app/boards/7')
    expect(deepLinkTarget(source('issue_update', 'issue_mine', 'issue', null, null))).toBe(null)
  })

  it('D7: row ที่ไม่รู้จัก/ว่างเปล่า → null และไม่โยน exception', () => {
    // ⚠️ ฟังก์ชันนี้ถูกเรียกในเส้นทางของผู้ใช้กดแถว — exception ที่นี่ = กดแล้วเงียบ
    expect(deepLinkTarget(source('', 'board', '', null, null))).toBe(null)
    expect(deepLinkTarget(source('board_new', 'board', 'piri_board', 3, null))).toBe(null)
  })

  it('D8: entity_type อื่นที่ไม่ใช่ issue แต่มี board_id → ไปบอร์ด (ไม่ใช่เรื่อง)', () => {
    // เช่น `piri_board_comment` / `piri_board_report`
    expect(
      targetToPath(deepLinkTarget(source('board_reply', 'board', 'piri_board_comment', 55, 3))),
    ).toBe('/app/boards/3')
  })

  it('D9: board_id = 0 ต้องไม่ถูกมองว่า "ไม่มี" (ใช้ != null ไม่ใช่ truthy)', () => {
    // ⚠️ กับดักคลาสสิก: `if (n.board_id)` จะทิ้ง id ที่เป็น 0 — และ 0 ผ่าน CHECK ของ
    //    SERIAL ได้ในทางทฤษฎี ⇒ เทสต์นี้ล็อกไว้ว่าต้องเทียบกับ null เท่านั้น
    expect(targetToPath(deepLinkTarget(source('board_new', 'board', 'piri_board', 0, 0)))).toBe(
      '/app/boards/0',
    )
  })
})
