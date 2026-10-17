import { fireEvent, screen, waitFor } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import type { CallDetail } from '@/entities/call-data'
import { backend } from '@/test/fake-backend'
import { openScheduling, seedScheduling } from '@/test/open-scheduling'

const ALL = { ring: true, ivr: true, transfers: true, holds: true, mutes: true, incidents: true }

const report = (over: Partial<CallDetail> = {}): CallDetail => ({
  month: '2031-03',
  sheets: ALL,
  scope: 'all',
  agentsAllowed: true,
  incidentsAllowed: true,
  agents: [
    {
      login: 'Agent010',
      employeeNumber: 'E010',
      employeeName: 'Mia Team',
      offers: 4,
      answered: 3,
      ringNoAnswer: 1,
      ringNoAnswerPct: '25.0',
      avgRingS: '12.5',
    },
    {
      login: 'Agent999',
      employeeNumber: null,
      employeeName: null,
      offers: 2,
      answered: 2,
      ringNoAnswer: 0,
      ringNoAnswerPct: '0.0',
      avgRingS: null,
    },
  ],
  ivr: [
    {
      queue: 'Support',
      calls: 10,
      reachedQueue: 7,
      endedInIvr: 3,
      abandonedAfterIvr: 2,
      steps: [{ step: 1, digit: '1', activity: 'Support menu', calls: 10, endedHere: 3 }],
    },
  ],
  eventsByQueue: [
    {
      queue: 'Support',
      day: null,
      transfers: 2,
      avgTransferS: '60.0',
      avgTransferAnswerS: '4.0',
      holds: 0,
      avgHoldS: null,
      mutes: 1,
      avgMuteS: '10.0',
    },
  ],
  eventsByDay: [
    {
      queue: 'Support',
      day: '2031-03-03',
      transfers: 2,
      avgTransferS: '60.0',
      avgTransferAnswerS: '4.0',
      holds: 0,
      avgHoldS: null,
      mutes: 1,
      avgMuteS: '10.0',
    },
  ],
  incidents: [{ queue: 'Support', callsWithIncident: 2, incidents: ['INC000000000101'] }],
  ...over,
})

async function open(role = 'planner', detail: CallDetail | null = report()) {
  seedScheduling()
  backend.months = ['2031-02', '2031-03']
  backend.callDetail = detail
  return openScheduling('/call-detail', role)
}

describe('call detail', () => {
  it('shows ring-no-answer per login, IVR drop-off, events and incident links', async () => {
    await open()
    const table = await screen.findByTestId('ring-table')
    expect(table).toHaveTextContent('E010 Mia Team')
    expect(table).toHaveTextContent('25.0%')
    expect(table).toHaveTextContent('Not mapped')
    expect(screen.getByTestId('ivr-Support')).toHaveTextContent(
      '10 calls through the IVR: 7 reached the queue, 3 ended in the IVR, 2 abandoned',
    )
    expect(screen.getByTestId('events-queue')).toHaveTextContent('Support')
    expect(screen.getByTestId('incidents-Support')).toHaveTextContent('INC000000000101')
  })

  it('shows a dash for an unknown average and a real 0 for a real zero', async () => {
    // Failure caught: an unknown average ring shown as 0.0 s, or a zero count shown as blank.
    await open()
    const table = await screen.findByTestId('ring-table')
    expect(table).toHaveTextContent('—')
    expect(screen.getByTestId('events-queue')).toHaveTextContent(/Support\s*2\s*60.0 s\s*0\s*—/)
  })

  it('says "No data" for a sheet that was not in the import, never zero', async () => {
    // Failure caught: "0 transfers" and an empty IVR table when the sheets were never imported.
    await open(
      'planner',
      report({
        sheets: { ...ALL, ring: false, ivr: false, incidents: false },
        agents: null,
        ivr: null,
        incidents: null,
        eventsByQueue: [
          {
            queue: 'Support',
            day: null,
            transfers: null,
            avgTransferS: null,
            avgTransferAnswerS: null,
            holds: 3,
            avgHoldS: '20.0',
            mutes: null,
            avgMuteS: null,
          },
        ],
        eventsByDay: [],
      }),
    )
    expect(await screen.findByTestId('ring-nodata')).toHaveTextContent('No data')
    expect(screen.getByTestId('ivr-nodata')).toBeVisible()
    expect(screen.getByTestId('incidents-nodata')).toBeVisible()
    expect(screen.getByTestId('events-queue')).toHaveTextContent(/Support\s*No data\s*—\s*3/)
  })

  it('shows an executive no per-agent rows and no incident numbers', async () => {
    // Failure caught: aggregate-only roles shown a per-agent table or ticket numbers.
    await open(
      'executive',
      report({
        scope: 'aggregate',
        agentsAllowed: false,
        incidentsAllowed: false,
        agents: null,
        incidents: null,
      }),
    )
    expect(await screen.findByTestId('ring-hidden')).toBeVisible()
    expect(screen.queryByTestId('ring-table')).toBeNull()
    expect(screen.queryByText(/INC000000000101/)).toBeNull()
    expect(screen.getByTestId('ivr-Support')).toBeVisible()
  })

  it('says a lead sees only their own team', async () => {
    await open('lead', report({ scope: 'team', incidentsAllowed: false, incidents: null }))
    expect(await screen.findByText(/Only agents in your own team are listed/)).toBeVisible()
  })

  it('never ranks: the page has no rank column or team average', async () => {
    // Failure caught: a league table creeping into the agent list.
    await open()
    const table = await screen.findByTestId('ring-table')
    expect(table).not.toHaveTextContent(/rank|team average|position/i)
  })

  it('asks for the month chosen', async () => {
    await open()
    await screen.findByTestId('ring-table')
    expect(backend.callDetailQueries.at(-1)).toBe('2031-03')
    await fireEvent.update(screen.getByLabelText('Month'), '2031-02')
    await waitFor(() => expect(backend.callDetailQueries.at(-1)).toBe('2031-02'))
  })

  it('keeps an agent out', async () => {
    await open('agent')
    expect(
      await screen.findByRole('heading', { name: "You don't have access to this page" }),
    ).toBeVisible()
  })

  it('keeps customer operations out', async () => {
    await open('customer_ops')
    expect(
      await screen.findByRole('heading', { name: "You don't have access to this page" }),
    ).toBeVisible()
  })
})
