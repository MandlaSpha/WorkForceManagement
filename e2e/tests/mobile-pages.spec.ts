import { expect, test, type Page } from '@playwright/test'

import { openAccountMenu, PASSWORD, signIn, signOut } from './helpers'

/**
 * MOB-01: the agent and lead pages work at phone width. Runs in the `mobile` project (a Pixel 7,
 * 412px wide) because of the tag in the title. The test of "usable" is concrete: the page never
 * scrolls sideways, the controls a person needs are reachable, and a finger can hit them.
 */
test.beforeAll(() => {
  if (!PASSWORD) throw new Error('Set WFM_DEMO_PASSWORD to the demo account password.')
})

const MIN_TAP_PX = 40

async function expectNoSidewaysScroll(page: Page): Promise<void> {
  const overflow = await page.evaluate(() => ({
    page: document.documentElement.scrollWidth - document.documentElement.clientWidth,
    body: document.body.scrollWidth - document.documentElement.clientWidth,
  }))
  expect(overflow.page, 'the page scrolls sideways').toBeLessThanOrEqual(0)
  expect(overflow.body, 'the body is wider than the window').toBeLessThanOrEqual(0)
}

async function expectBigEnough(page: Page, name: string | RegExp): Promise<void> {
  const box = await page.getByRole('button', { name }).first().boundingBox()
  expect(box, `no button named ${String(name)}`).not.toBeNull()
  expect(box?.height ?? 0).toBeGreaterThanOrEqual(MIN_TAP_PX)
  expect(box?.width ?? 0).toBeGreaterThanOrEqual(MIN_TAP_PX)
}

const nav = (page: Page) => page.getByRole('navigation', { name: 'Main navigation' })

test.describe('the agent on a phone @mobile', () => {
  test('schedule, availability, leave and swaps fit the screen', async ({ page }) => {
    await signIn(page, 'agent')

    await expect(page).toHaveURL(/\/my-schedule$/)
    // A phone starts on the list of days; the month grid is one tap away.
    await expect(page.getByRole('button', { name: 'List' })).toHaveAttribute('aria-pressed', 'true')
    await expectNoSidewaysScroll(page)

    for (const path of ['/my-availability', '/leave', '/shift-swaps']) {
      await page.goto(path)
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
      await expect(page.getByText(/^Loading/)).toHaveCount(0)
      await expectNoSidewaysScroll(page)
    }
  })

  test('the menu and account buttons are big enough to hit', async ({ page }) => {
    await signIn(page, 'agent')
    await expectBigEnough(page, 'Open navigation')
    await page.getByRole('button', { name: 'Open navigation' }).click() // the account card is in the drawer
    await expectBigEnough(page, /^Account menu/)
  })

  test('the drawer opens, takes the agent to a page, closes on Escape and stays out of the tab order', async ({
    page,
  }) => {
    await signIn(page, 'agent')

    // Closed: its links are not reachable by keyboard or screen reader.
    await expect(nav(page).getByRole('link', { name: 'Leave' })).toHaveCount(0)

    await page.getByRole('button', { name: 'Open navigation' }).click()
    await expect(nav(page).getByRole('link', { name: 'Leave' })).toBeInViewport({ ratio: 1 })
    await page.keyboard.press('Escape')
    await expect(page.getByRole('button', { name: 'Open navigation' })).toHaveAttribute(
      'aria-expanded',
      'false',
    )

    await page.getByRole('button', { name: 'Open navigation' }).click()
    await nav(page).getByRole('link', { name: 'Shift swaps' }).click()
    await expect(page).toHaveURL(/\/shift-swaps$/)
    await expect(page.getByRole('button', { name: 'Open navigation' })).toHaveAttribute(
      'aria-expanded',
      'false',
    )
  })

  test('the account menu opens inside the screen and signs out', async ({ page }) => {
    await signIn(page, 'agent')
    await openAccountMenu(page)
    const menu = page.getByRole('menu', { name: 'Account' })
    await expect(menu).toBeInViewport({ ratio: 1 })
    await expectNoSidewaysScroll(page)
    await page.keyboard.press('Escape')
    await expect(menu).toHaveCount(0)
    await signOut(page)
  })
})

test.describe('the team lead on a phone @mobile', () => {
  test('the lead pages fit the screen', async ({ page }) => {
    await signIn(page, 'lead')
    for (const path of ['/leave', '/shift-swaps', '/attendance']) {
      await page.goto(path)
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
      await expectNoSidewaysScroll(page)
    }
  })
})
