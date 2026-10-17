import userEvent from '@testing-library/user-event'
import { screen, waitFor, within } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import type { BackupTeam, Mobilise } from '@/entities/workforce/continuity'
import { backend } from '@/test/fake-backend'
import { openScheduling, seedScheduling } from '@/test/open-scheduling'

const person = (empNo: string, name: string, workMode = 'remote') => ({
  employeeId: Number(empNo.slice(1)) + 100,
  empNo,
  employee: name,
  workMode,
  remoteCapable: workMode !== 'office',
})

const team = (over: Partial<BackupTeam> = {}): BackupTeam => ({
  id: 7,
  queueId: 1,
  queue: 'QueueA',
  name: 'Alpha',
  memberCount: 2,
  members: [person('B1', 'Bea Backup', 'hybrid'), person('B2', 'Bo Backup', 'office')],
  ...over,
})

const answer = (over: Partial<Mobilise> = {}): Mobilise => ({
  queue: 'QueueA',
  day: '2031-03-03',
  scenario: 'site',
  lostPct: 30,
  rosteredByMode: { office: 2, remote: 1 },
  impact: {
    rostered: 3,
    lost: 2,
    remaining: 1,
    recovered: 1,
    coveredAfter: 2,
    shortfall: 1,
    coveragePct: 66.7,
  },
  byStatus: { free: 1, needs_office: 1 },
  usableDistinct: 1,
  teams: [
    {
      teamId: 7,
      name: 'Alpha',
      memberCount: 2,
      usableCount: 1,
      candidates: [
        { ...person('B1', 'Bea Backup', 'hybrid'), status: 'free', usable: true },
        { ...person('B2', 'Bo Backup', 'office'), status: 'needs_office', usable: false },
      ],
    },
  ],
  ...over,
})

async function open(role = 'planner', mobilise: Mobilise | null = answer()) {
  seedScheduling()
  backend.backupTeams = [team()]
  backend.mobilise = mobilise
  return openScheduling('/continuity', role)
}

describe('continuity', () => {
  it('shows the roster impact and who can and cannot cover, with the reason', async () => {
    // Failure caught: an office-only person offered as cover for a failed site, or the gap hidden.
    await open()
    expect(await screen.findByTestId('lost')).toHaveTextContent('2')
    expect(screen.getByTestId('recovered')).toHaveTextContent('1')
    expect(screen.getByTestId('after')).toHaveTextContent('66.7%')
    expect(screen.getByTestId('shortfall')).toHaveTextContent('(1)')
    const ok = screen.getByTestId('cand-B1')
    expect(ok).toHaveTextContent('Free to cover')
    expect(ok).toHaveTextContent('Hybrid')
    expect(screen.getByTestId('cand-B2')).toHaveTextContent('Works from the office only')
  })

  it('asks again with the outbreak share when the scenario changes', async () => {
    await open()
    const user = userEvent.setup()
    await screen.findByTestId('lost')
    await user.selectOptions(screen.getByLabelText('What happened'), 'outbreak')
    const share = await screen.findByLabelText('Share of the roster lost (%)')
    await user.clear(share)
    await user.type(share, '50')
    await waitFor(() =>
      expect(backend.mobiliseQueries.at(-1)).toMatchObject({
        scenario: 'outbreak',
        lost_pct: '50',
      }),
    )
  })

  it('says so when no backup team is named', async () => {
    await open('planner', answer({ teams: [] }))
    expect(await screen.findByTestId('no-cover')).toBeVisible()
  })

  it('shows the API problem if the cover cannot be worked out', async () => {
    await open('planner', null)
    expect(await screen.findByTestId('mobilise-error')).toBeVisible()
  })

  it('lets a planner create a team, and sends the write with the CSRF token', async () => {
    await open()
    const user = userEvent.setup()
    await user.type(await screen.findByLabelText('New team name'), 'Beta')
    await user.click(screen.getByRole('button', { name: 'Create team' }))
    expect(await screen.findByTestId('team-Beta')).toBeVisible()
    expect(backend.writes.at(-1)).toMatchObject({
      method: 'POST',
      path: '/api/v1/continuity/teams',
      body: { queueId: 1, name: 'Beta' },
      csrf: 'test-csrf-token',
    })
  })

  it('lets a planner add and remove a person', async () => {
    await open()
    const user = userEvent.setup()
    const panel = await screen.findByTestId('team-Alpha')
    await within(panel).findByRole('option', { name: /Alex Agent/ })
    await user.selectOptions(within(panel).getByLabelText('Add a person to Alpha'), '10')
    await user.click(within(panel).getByRole('button', { name: 'Add' }))
    const remove = await within(panel).findByRole('button', {
      name: 'Remove Alex Agent from Alpha',
    })
    await user.click(remove)
    await waitFor(() => expect(remove).not.toBeInTheDocument())
  })

  it('shows the API refusal of a duplicate team plainly', async () => {
    await open()
    backend.nextProblem = {
      status: 409,
      code: 'continuity.name_taken',
      title: 'Backup team refused',
      detail: 'That queue already has a team of that name.',
    }
    const user = userEvent.setup()
    await user.type(await screen.findByLabelText('New team name'), 'Alpha')
    await user.click(screen.getByRole('button', { name: 'Create team' }))
    expect(await screen.findByTestId('teams-error')).toHaveTextContent('already has a team')
  })

  it('gives a lead the answer but no editing', async () => {
    // Failure caught: write controls offered to a role the API refuses.
    await open('lead')
    expect(await screen.findByTestId('cand-B1')).toBeVisible()
    expect(screen.queryByLabelText('New team name')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^Delete team/ })).not.toBeInTheDocument()
  })

  it('gives an executive the numbers without names', async () => {
    await open(
      'executive',
      answer({
        teams: [{ teamId: 7, name: 'Alpha', memberCount: 2, usableCount: 1, candidates: [] }],
      }),
    )
    expect(await screen.findByTestId('lost')).toHaveTextContent('2')
    expect(screen.queryByText(/Bea Backup/)).not.toBeInTheDocument()
    expect(
      screen.getAllByText(/Names are shown to planners, admins and team leads only/),
    ).toHaveLength(1)
  })

  it.each(['agent', 'customer_ops'])('keeps %s out', async (role) => {
    await open(role)
    expect(
      await screen.findByRole('heading', { name: "You don't have access to this page" }),
    ).toBeVisible()
  })
})
