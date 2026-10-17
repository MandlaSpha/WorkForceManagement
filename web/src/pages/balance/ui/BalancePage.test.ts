import { screen } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import type { WorkloadBalance } from '@/entities/workforce/workload-balance'
import { backend } from '@/test/fake-backend'
import { openScheduling } from '@/test/open-scheduling'

const balance = (over: Partial<WorkloadBalance> = {}): WorkloadBalance => ({
  day: '2026-10-19',
  note: 'These are suggestions. Nobody is moved until a planner changes the roster.',
  queues: [
    {
      queueId: 1,
      queue: 'QueueA',
      requiredSlots: 51,
      scheduledSlots: 17,
      loadRatio: 3,
      state: 'stretched',
    },
    {
      queueId: 2,
      queue: 'QueueB',
      requiredSlots: 17,
      scheduledSlots: 34,
      loadRatio: 0.5,
      state: 'slack',
    },
    {
      queueId: 3,
      queue: 'QueueC',
      requiredSlots: 0,
      scheduledSlots: 0,
      loadRatio: null,
      state: 'unknown',
    },
  ],
  suggestions: [
    {
      employeeId: 11,
      empNo: 'E002',
      employee: 'Bob Agent',
      fromQueueId: 2,
      fromQueue: 'QueueB',
      toQueueId: 1,
      toQueue: 'QueueA',
      slots: 17,
    },
  ],
  ...over,
})

async function open(role = 'planner', over: Partial<WorkloadBalance> = {}) {
  backend.balance = balance(over)
  return openScheduling('/balance', role)
}

describe('workload balance', () => {
  it('names stretched and slack queues in words as well as numbers', async () => {
    // Failure caught: state carried by colour alone, or a queue with no forecast shown as fine.
    await open()
    const a = await screen.findByTestId('queue-QueueA')
    expect(a).toHaveTextContent('300%')
    expect(a).toHaveTextContent('Stretched')
    expect(screen.getByTestId('queue-QueueB')).toHaveTextContent('Slack')
    const c = screen.getByTestId('queue-QueueC')
    expect(c).toHaveTextContent('No forecast')
    expect(c).not.toHaveTextContent('0%')
  })

  it('offers a move as a suggestion and says nothing is moved from here', async () => {
    // Failure caught: a button that reassigns people, or wording that says it was done.
    await open()
    const move = await screen.findByTestId('move-E002')
    expect(move).toHaveTextContent('Move Bob Agent (E002) from QueueB to QueueA')
    expect(move).toHaveTextContent('nothing is moved from here')
    expect(screen.queryByRole('button', { name: /move|apply|assign/i })).not.toBeInTheDocument()
    expect(screen.getByTestId('balance-note')).toHaveTextContent('suggestions')
  })

  it('says so when no move is suggested', async () => {
    await open('lead', { suggestions: [] })
    expect(await screen.findByTestId('no-moves')).toBeVisible()
  })

  it('says so when there are no queues', async () => {
    await open('planner', { queues: [], suggestions: [] })
    expect(await screen.findByTestId('balance-none')).toBeVisible()
  })

  it('shows the API problem if the day cannot be loaded', async () => {
    backend.balance = null
    await openScheduling('/balance', 'planner')
    expect(await screen.findByTestId('balance-error')).toBeVisible()
  })

  it.each(['agent', 'executive', 'customer_ops'])('keeps %s out', async (role) => {
    await open(role)
    expect(
      await screen.findByRole('heading', { name: "You don't have access to this page" }),
    ).toBeVisible()
  })
})
