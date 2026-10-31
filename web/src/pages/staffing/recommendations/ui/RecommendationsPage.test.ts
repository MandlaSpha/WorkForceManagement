import userEvent from '@testing-library/user-event'
import { screen, waitFor, within } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import type { Flex, Recommendation } from '@/entities/scheduling'
import { backend } from '@/test/fake-backend'
import { openScheduling, seedScheduling } from '@/test/open-scheduling'

const rec = (over: Partial<Recommendation> = {}): Recommendation => ({
  kind: 'add',
  employeeId: 7,
  employee: 'Sam Planner',
  day: '2026-05-27',
  templateId: 2,
  shift: 'D1',
  replaces: null,
  closes: 17,
  addsOver: 0,
  text: 'Add Sam Planner to D1 on Wed 27 May: closes 17 half-hours short.',
  ...over,
})

async function open(role = 'planner', items: Recommendation[] = [rec()]) {
  seedScheduling()
  backend.recommendations = items
  return openScheduling('/recommendations', role)
}

describe('recommendations', () => {
  it('lists the fixes in the order given, each as a sentence, with the gap that is open', async () => {
    await open('planner', [
      rec(),
      rec({
        kind: 'change',
        employeeId: 8,
        templateId: 1,
        replaces: 'D1',
        shift: 'E1',
        closes: 4,
        addsOver: 2,
        text: 'Change Alex Agent from D1 to E1 on Wed 27 May: closes 4 half-hours short.',
      }),
    ])
    const list = await screen.findByRole('list', { name: 'Recommendations' })
    const items = within(list).getAllByRole('listitem')
    expect(items).toHaveLength(2)
    expect(items[0]).toHaveTextContent('Add Sam Planner to D1 on Wed 27 May: closes 17')
    expect(items[1]).toHaveTextContent('2 half-hours would then have one person too many')
    expect(await screen.findByTestId('rec-gap')).toHaveTextContent('Half-hours short this week')
  })

  it('applies exactly the suggestion shown, with the CSRF token, and it leaves the list', async () => {
    // Failure caught: applying a different suggestion than the one clicked, or without the token.
    const user = userEvent.setup()
    await open('planner', [
      rec(),
      rec({ employeeId: 8, templateId: 1, shift: 'E1', text: 'Second' }),
    ])
    const first = await screen.findByTestId('rec-0')
    await user.click(within(first).getByRole('button', { name: 'Apply' }))
    await waitFor(() => expect(backend.writes).toHaveLength(1))
    expect(backend.writes[0]).toEqual({
      method: 'POST',
      path: '/api/v1/scheduling/recommendations/apply',
      body: {
        queueId: 1,
        weekStart: '2026-05-25',
        employeeId: 7,
        day: '2026-05-27',
        templateId: 2,
      },
      csrf: 'test-csrf-token',
    })
    await waitFor(() => expect(screen.queryByText(/Add Sam Planner/)).toBeNull())
    expect(screen.getByText('Second')).toBeVisible()
  })

  it('says why a suggestion could not be applied and leaves it there', async () => {
    const user = userEvent.setup()
    await open()
    backend.nextProblem = {
      status: 409,
      code: 'recommendation.stale',
      title: 'Suggestion refused',
      detail: 'That suggestion no longer applies: the roster has changed.',
    }
    await user.click(await screen.findByRole('button', { name: 'Apply' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('no longer applies')
    expect(screen.getByText(/Add Sam Planner/)).toBeVisible()
  })

  it('says so when there is nothing to suggest', async () => {
    await open('planner', [])
    expect(await screen.findByTestId('rec-none')).toBeVisible()
  })
})

const borrow = (over: Partial<Flex> = {}): Flex => ({
  employeeId: 9,
  employee: 'Bo Flex',
  fromQueue: 'QueueB',
  day: '2026-05-27',
  shift: 'D1',
  closes: 6,
  addsOver: 0,
  text: 'Borrow Bo Flex (D1) from QueueB on Wed 27 May: closes 6 half-hours short.',
  ...over,
})

describe('borrowing from other queues (SCH-09)', () => {
  it('lists the people another queue can spare, each with where they come from', async () => {
    seedScheduling()
    backend.flex = [borrow()]
    await openScheduling('/recommendations', 'planner')
    const list = await screen.findByRole('list', { name: 'People to borrow' })
    const item = within(list).getByTestId('flex-0')
    expect(item).toHaveTextContent('From QueueB')
    expect(item).toHaveTextContent('Borrow Bo Flex (D1) from QueueB on Wed 27 May')
    expect(item).toHaveTextContent('closes 6')
  })

  it('borrows exactly the person shown, with the CSRF token, and they leave the list', async () => {
    // Failure caught: moving a different person or day than the one clicked.
    const user = userEvent.setup()
    seedScheduling()
    backend.flex = [borrow(), borrow({ employeeId: 10, employee: 'Cy Other', text: 'Second' })]
    await openScheduling('/recommendations', 'planner')
    await user.click(await screen.findByRole('button', { name: 'Borrow Bo Flex from QueueB' }))
    await waitFor(() => expect(backend.writes).toHaveLength(1))
    expect(backend.writes[0]).toEqual({
      method: 'POST',
      path: '/api/v1/scheduling/flex/apply',
      body: { queueId: 1, weekStart: '2026-05-25', employeeId: 9, day: '2026-05-27' },
      csrf: 'test-csrf-token',
    })
    await waitFor(() => expect(screen.queryByText(/Borrow Bo Flex/)).toBeNull())
    expect(screen.getByText('Second')).toBeVisible()
  })

  it('says why a borrow was refused and keeps the suggestion', async () => {
    const user = userEvent.setup()
    seedScheduling()
    backend.flex = [borrow()]
    await openScheduling('/recommendations', 'planner')
    backend.nextProblem = {
      status: 409,
      code: 'flex.stale',
      title: 'Suggestion refused',
      detail: 'That suggestion no longer applies: the rosters have changed.',
    }
    await user.click(await screen.findByRole('button', { name: 'Borrow Bo Flex from QueueB' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('no longer applies')
    expect(screen.getByText(/Borrow Bo Flex/)).toBeVisible()
  })

  it('says a published week is locked instead of showing an error', async () => {
    seedScheduling()
    backend.plan = { ...backend.plan!, rosterStatus: 'published' }
    await openScheduling('/recommendations', 'planner')
    expect(await screen.findByTestId('rec-published')).toHaveTextContent('published')
    expect(screen.queryByTestId('flex-section')).toBeNull()
  })

  it('says so when nobody can be spared', async () => {
    seedScheduling()
    await openScheduling('/recommendations', 'planner')
    expect(await screen.findByTestId('flex-none')).toBeVisible()
  })
})

describe('who sees what', () => {
  it.each(['lead', 'agent', 'executive', 'customer_ops'])('keeps %s out', async (role) => {
    await open(role)
    expect(
      await screen.findByRole('heading', { name: "You don't have access to this page" }),
    ).toBeVisible()
  })
})
