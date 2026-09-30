import { test, expect, type Page } from '@playwright/test'
import * as fs from 'node:fs'

/**
 * 🧪 E2E — PIRI Boards Full Flow (Frontend ↔ Backend Seam)
 * ข้อกำหนด: ต้องมี backend รันที่ http://localhost:8000 (ชี้ e2e_piri_db) + seed users
 * (runn ผ่าน backend/scripts/e2e_seed.py → /tmp/e2e_credentials.json)
 *
 * Flow:
 * 1. Vote: นักเรียนแจ้งเรื่องขอโหวต → สภาอนุมัติ (ตั้งตัวเลือก) → นักเรียนเข้าไปโหวต
 * 2. Talk: นักเรียนแจ้งเรื่องขอพูดคุย → สภาอนุมัติ → คอมเมนต์ 2 ฝ่าย →
 *    กด "แจ้ง" (รีพอร์ต) → สภาจัดการผ่านคิว: ปัดตก 1 + ซ่อน 1 → ตรวจ visibility
 */
const API = 'http://localhost:8000'

interface Cred { username: string; password: string; user_id: number; token: string }
let creds: Record<string, Cred> = {}
try {
  creds = JSON.parse(fs.readFileSync('/tmp/e2e_credentials.json', 'utf8'))
} catch {
  /* seed ทำก่อนรัน */
}

// login ผ่าน API → inject token เข้า localStorage (เลี่ยง UI login ช้าตอนสลับบทบาท)
async function loginAs(page: Page, key: string): Promise<void> {
  const c = creds[key]
  expect(c, `credentials สำหรับ ${key} ต้องมี (seed แล้วไหม?)`).toBeTruthy()
  const res = await page.request.post(`${API}/api/auth/login`, {
    data: { username: c.username, password: c.password },
  })
  expect(res.ok(), `login ${key} ต้องสำเร็จ`).toBeTruthy()
  const body = await res.json()
  await page.addInitScript(
    ([tok, uid]) => {
      localStorage.setItem('access_token', tok)
      localStorage.setItem('user_id_str', String(uid))
    },
    [body.access_token as string, body.user.id as number],
  )
}

/**
 * ⚠️ **อัปเดต รอบ 2 (R3.1)** — ฟอร์มแจ้งเรื่องเปลี่ยนจาก "หน้าเดียว 5 หัวข้อ" เป็น
 *    **ตัวช่วยกรอก 3 ขั้น** (ประเภท → รายละเอียด → ตรวจสอบ)
 *
 * ⇒ สามอย่างที่เปลี่ยนและต้องแก้ที่นี่:
 *   1. ช่องกรอกอยู่คนละขั้น ⇒ ต้องกด "ถัดไป" คั่น
 *      (`cat-*` + ชิปหมวดย่อย อยู่ขั้น 1 · `issue-title`/`issue-desc` อยู่ขั้น 2 ·
 *       `dest-*` + `issue-submit` อยู่ขั้น 3)
 *   2. `dest-*` **ไม่ถูกเลือกไว้ก่อนแล้ว** (เดิมตั้ง `'normal'` เป็นค่าเริ่มต้น ซึ่งเป็นบั๊ก
 *      ที่ audit ฟ้อง) ⇒ เทสต์ต้อง **กดเลือกเอง** ซึ่งมันทำอยู่แล้ว — ไม่ต้องแก้
 *   3. **หน้าสำเร็จเป็นหน้าเต็ม ไม่ใช่ `Swal`** ⇒ ไม่มี `.swal2-confirm` ให้กดแล้ว
 *      ต้องกดปุ่ม "ดูเรื่องนี้" (`goto-created-issue`) เพื่อไปหน้ารายละเอียดแทน
 *
 * 🔴 `waitForURL(/\/issues\/\d+$/)` **คงไว้เหมือนเดิม** — ตัวทดสอบส่วนที่เหลือพึ่ง URL นี้
 */
async function submitIssue(page: Page, title: string, dest: 'vote' | 'talk'): Promise<string> {
  await page.goto('/issues/new')

  // ── ขั้น 1: ประเภท ──────────────────────────────────────────────────────
  await page.getByTestId('cat-suggestion').click()
  await page.getByRole('button', { name: 'วิชาการ' }).click()
  await page.getByRole('button', { name: 'ถัดไป' }).click()

  // ── ขั้น 2: รายละเอียด ──────────────────────────────────────────────────
  await page.getByTestId('issue-title').fill(title)
  await page.getByTestId('issue-desc').fill('E2E test — รายละเอียดอัตโนมัติ')
  await page.getByRole('button', { name: 'ถัดไป' }).click()

  // ── ขั้น 3: ตรวจสอบ + ส่ง ───────────────────────────────────────────────
  await page.getByTestId(`dest-${dest}`).click()
  await page.getByTestId('issue-submit').click()

  // หน้าสำเร็จ (เต็มหน้า) → กด "ดูเรื่องนี้" เพื่อไปหน้ารายละเอียด
  await page.getByTestId('goto-created-issue').click()
  await page.waitForURL(/\/issues\/\d+$/)
  return page.url()
}

test.describe('PIRI Boards full flow (frontend ↔ backend)', () => {
  test('Vote: นักเรียนแจ้ง → สภาอนุมัติตั้งตัวเลือก → นักเรียนโหวต', async ({ page }) => {
    // 1) student ส่งเรื่องขอโหวตผ่านฟอร์ม
    await loginAs(page, 'e2estu')
    const issueUrl = await submitIssue(page, 'E2E ขอโหวตเลือกสถานที่จัดงานกีฬาสี', 'vote')
    await expect(page.getByText('โหวตสาธารณะ').first()).toBeVisible()

    // 2) admin อนุมัติ + ตั้งตัวเลือกโหวตผ่าน modal
    await loginAs(page, 'e2eadm')
    await page.goto(issueUrl)
    await page.getByTestId('approve-public-btn').click()
    await page.getByTestId('choice-input-0').fill('สนามในร่ม')
    await page.getByTestId('choice-input-1').fill('สนามกลางแจ้ง')
    await page.getByTestId('approve-confirm').click()
    await page.waitForURL(/\/boards\/\d+$/)
    const boardUrl = page.url()

    // 3) student เข้า board → เลือกตัวเลือก → โหวต
    await loginAs(page, 'e2estu')
    await page.goto(boardUrl)
    await page.locator('[data-testid^="vote-choice-"]').first().click()
    await page.getByTestId('vote-submit').click()

    // 4) ยืนยันผล: แบนเนอร์ "โหวตแล้ว" + progress bar + ยอด 1 เสียง
    await expect(page.getByTestId('my-vote-banner')).toBeVisible()
    await expect(page.getByText('1 เสียง').first()).toBeVisible()
    await expect(page.locator('.bg-emerald-500')).toBeVisible() // ring/bar ของ choice ที่โหวต
  })

  test('Talk: คอมเมนต์ → รีพอร์ต → สภาจัดการ (ปัดตก + ซ่อน)', async ({ page }) => {
    // 1) student ส่งเรื่องขอพูดคุย
    await loginAs(page, 'e2estu')
    const issueUrl = await submitIssue(page, 'E2E ขอพูดคุยเรื่องห้องน้ำ', 'talk')

    // 2) admin อนุมัติ talk (ไม่มี choice)
    await loginAs(page, 'e2eadm')
    await page.goto(issueUrl)
    await page.getByTestId('approve-public-btn').click()
    await page.getByTestId('approve-confirm').click()
    await page.waitForURL(/\/boards\/\d+$/)
    const boardUrl = page.url()

    // 3) student คอมเมนต์ A
    await loginAs(page, 'e2estu')
    await page.goto(boardUrl)
    await page.getByTestId('comment-input').fill('E2E คอมเมนต์จากนักเรียน')
    await page.getByTestId('comment-submit').click()
    await expect(page.getByText('E2E คอมเมนต์จากนักเรียน')).toBeVisible()

    // 4) council คอมเมนต์ B
    await loginAs(page, 'e2ecou')
    await page.goto(boardUrl)
    await page.getByTestId('comment-input').fill('E2E คอมเมนต์จากสภา')
    await page.getByTestId('comment-submit').click()
    await expect(page.getByText('E2E คอมเมนต์จากสภา')).toBeVisible()

    // 5) student รีพอร์ตคอมเมนต์ B (ของสภา) — เหตุผล bullying
    await loginAs(page, 'e2estu')
    await page.goto(boardUrl)
    const commentB = page.locator('[data-testid="comment-node"]', { hasText: 'E2E คอมเมนต์จากสภา' })
    await commentB.getByTestId('report-btn').click()
    await page.locator('.swal2-select').selectOption('bullying')
    await page.locator('.swal2-confirm').click()
    await page.locator('.swal2-textarea').fill('E2E ทดสอบรีพอร์ตคำหยาบ')
    await page.locator('.swal2-confirm').click()
    await expect(page.getByText('แจ้งแล้ว').first()).toBeVisible()

    // 6) council รีพอร์ตคอมเมนต์ A (ของนักเรียน) — เหตุผล spam
    await loginAs(page, 'e2ecou')
    await page.goto(boardUrl)
    const commentA = page.locator('[data-testid="comment-node"]', { hasText: 'E2E คอมเมนต์จากนักเรียน' })
    await commentA.getByTestId('report-btn').click()
    await page.locator('.swal2-select').selectOption('spam')
    await page.locator('.swal2-confirm').click()
    await page.locator('.swal2-textarea').fill('')
    await page.locator('.swal2-confirm').click()
    await expect(page.getByText('แจ้งแล้ว').first()).toBeVisible()

    // 7) admin เปิดคิวรายงาน → เห็น 2 รายการ open
    await loginAs(page, 'e2eadm')
    await page.goto('/boards/reports')
    const cards = page.locator('[data-testid^="report-card-"]')
    await expect(cards).toHaveCount(2)

    // 8) ปัดตกรายงานคอมเมนต์ A (ไม่ซ่อน — ยังแสดงอยู่)
    await cards.filter({ hasText: 'E2E คอมเมนต์จากนักเรียน' }).getByTestId('dismiss-btn').click()
    await page.locator('.swal2-confirm').click()
    await expect(page.getByText('ปัดตกแล้ว').first()).toBeVisible()

    // 9) ซ่อนรายงานคอมเมนต์ B (ซ่อน subtree — หายจาก board)
    await page
      .locator('[data-testid^="report-card-"]')
      .filter({ hasText: 'E2E คอมเมนต์จากสภา' })
      .getByTestId('hide-btn')
      .click()
    await page.locator('.swal2-confirm').click()
    await expect(page.getByText('ซ่อนคอมเมนต์แล้ว').first()).toBeVisible()

    // 10) ตรวจ final state: A ยังแสดง, B ถูกซ่อน
    await loginAs(page, 'e2estu')
    await page.goto(boardUrl)
    await expect(page.getByText('E2E คอมเมนต์จากนักเรียน')).toBeVisible()
    await expect(page.getByText('E2E คอมเมนต์จากสภา')).toBeHidden()
  })
})
