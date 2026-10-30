import { fireEvent, screen, waitFor, within } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import { expectAriaReferencesResolve } from '@/test/aria'
import { backend } from '@/test/fake-backend'
import { openScheduling, seedScheduling } from '@/test/open-scheduling'
import { teamOverview, teamPerson } from '@/test/team-fixtures'

function order(): string[] {
  return screen
    .getAllByTestId(/^card-E/)
    .map((el) => el.getAttribute('data-testid')?.replace('card-', '') ?? '')
}

describe('Team screen', () => {
  it('shows a card per person with a ring, the hours strip and only plain chips', async () => {
    // Failure caught: a score or reason on the wellbeing chip, a made-up number for a missing
    // feed, or a verdict shown by colour alone.
    seedScheduling()
    backend.team = teamOverview()
    await openScheduling('/team', 'lead')

    const alex = await screen.findByTestId('card-E001')
    expect(alex).toHaveTextContent('Alex Agent')
    expect(alex).toHaveTextContent('Permanent · 40 h a week')
    expect(within(alex).getByRole('img', { name: /Adherence this week: 9[45]%/ })).toBeVisible()
    expect(screen.getByTestId('verdict-E001')).toHaveTextContent('On track')
    expect(alex).toHaveTextContent('32 h')
    expect(alex).toHaveTextContent('of 40 h')

    const sam = screen.getByTestId('card-E002')
    expect(screen.getByTestId('verdict-E002')).toHaveTextContent('Below target')
    expect(sam).toHaveTextContent('Leave request')
    expect(sam).toHaveTextContent('Open swap')
    expect(sam).toHaveTextContent('Check in')
    expect(sam).not.toHaveTextContent(/score|risk|overtime|R\s?\d|long_run|days worked/i)

    // No adherence data: the ring says so, there is no zero.
    const kim = screen.getByTestId('card-E003')
    expect(within(kim).getByRole('img', { name: 'Adherence this week: No data' })).toBeVisible()
    expect(screen.getByTestId('verdict-E003')).toHaveTextContent('Adherence not loaded')
    expect(kim).not.toHaveTextContent('0%')
  })

  it('writes the summary sentence with the numbers in bold', async () => {
    seedScheduling()
    backend.team = teamOverview()
    await openScheduling('/team', 'planner')
    const summary = await screen.findByTestId('summary')
    expect(summary).toHaveTextContent(
      '1 of 2 people with adherence data are on track this week; together they are rostered for 90% of contract hours.',
    )
    expect([...summary.querySelectorAll('strong')].map((s) => s.textContent)).toEqual([
      '1',
      '2',
      '90%',
    ])
    expect(screen.getByTestId('caption')).toHaveTextContent('3 people')
  })

  it('starts in employee-number order and sorts only when asked', async () => {
    // Failure caught: the default order ranking people by performance.
    seedScheduling()
    backend.team = teamOverview({
      people: [
        teamPerson({ empNo: 'E003', employeeId: 3, name: 'Cee', adherencePct: 99, onTrack: true }),
        teamPerson({ empNo: 'E001', employeeId: 1, name: 'Aye', adherencePct: 70, onTrack: false }),
        teamPerson({ empNo: 'E002', employeeId: 2, name: 'Bee', adherencePct: 85, onTrack: false }),
      ],
    })
    await openScheduling('/team', 'lead')
    await screen.findByTestId('card-E001')
    expect(order()).toEqual(['E001', 'E002', 'E003'])
    await fireEvent.click(screen.getByRole('tab', { name: 'Adherence' }))
    expect(order()).toEqual(['E003', 'E002', 'E001'])
    await fireEvent.click(screen.getByRole('tab', { name: 'A-Z' }))
    expect(order()).toEqual(['E001', 'E002', 'E003'])
  })

  it('has no aria reference to an id that is not on the page', async () => {
    // Failure caught: the sort tabs pointing aria-controls at panels that do not exist (axe:
    // aria-valid-attr-value).
    seedScheduling()
    backend.team = teamOverview()
    await openScheduling('/team', 'lead')
    await screen.findByTestId('card-E001')
    expectAriaReferencesResolve()
  })

  it('opens a drawer with the persons week and returns focus on close', async () => {
    seedScheduling()
    backend.team = teamOverview()
    await openScheduling('/team', 'lead')
    const card = await screen.findByTestId('card-E002')
    card.focus()
    await fireEvent.click(card)

    const drawer = await screen.findByRole('dialog')
    expect(drawer).toHaveAttribute('aria-modal', 'true')
    expect(within(drawer).getByRole('heading', { name: 'Sam Planner' })).toBeVisible()
    expect(within(drawer).getByText('Shifts this week')).toBeVisible()
    expect(drawer).toHaveTextContent('09:00–17:30')
    expect(drawer).toHaveTextContent('Annual leave')
    expect(drawer).toHaveTextContent('Annual leave: 2026-06-08 to 2026-06-09 (2 days)')
    await waitFor(() => expect(within(drawer).getByRole('button', { name: 'Close' })).toHaveFocus())

    await fireEvent.keyDown(document, { key: 'Escape' })
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(card).toHaveFocus()
  })

  it('says there is no adherence data in the drawer rather than drawing empty bars', async () => {
    seedScheduling()
    backend.team = teamOverview()
    await openScheduling('/team', 'lead')
    await fireEvent.click(await screen.findByTestId('card-E003'))
    expect(await screen.findByTestId('drawer-no-data')).toBeVisible()
  })

  it('offers the team filter to a planner and asks the API for that team', async () => {
    seedScheduling()
    backend.team = teamOverview({ managers: [{ id: 50, name: 'Lee Lead' }] })
    await openScheduling('/team', 'planner')
    const select = await screen.findByLabelText('Team')
    await fireEvent.update(select, '50')
    await waitFor(() =>
      expect(backend.teamQueries.some((q) => q.includes('manager_id=50'))).toBe(true),
    )
  })

  it('has no team filter for a lead', async () => {
    seedScheduling()
    backend.team = teamOverview()
    await openScheduling('/team', 'lead')
    await screen.findByTestId('card-E001')
    expect(screen.queryByLabelText('Team')).toBeNull()
  })

  it('shows a skeleton while loading, then an honest empty state', async () => {
    seedScheduling()
    backend.team = teamOverview({
      people: [],
      summary: {
        headcount: 0,
        withAdherence: 0,
        onTrack: 0,
        rosteredHours: 0,
        contractHours: 0,
        rosteredPct: null,
      },
    })
    await openScheduling('/team', 'lead')
    expect(await screen.findByTestId('team-empty')).toHaveTextContent('Nobody is on this team')
    expect(screen.queryByTestId('team-loading')).toBeNull()
  })

  it('says when no adherence has been loaded at all', async () => {
    seedScheduling()
    backend.team = teamOverview({
      people: [teamPerson({ adherencePct: null, onTrack: null })],
    })
    await openScheduling('/team', 'lead')
    expect(await screen.findByTestId('no-adherence')).toBeVisible()
    expect(screen.getByTestId('summary')).not.toHaveTextContent('0 of')
  })

  it('shows the refusal when the API says no', async () => {
    seedScheduling()
    backend.team = null
    await openScheduling('/team', 'planner')
    expect(await screen.findByTestId('team-error')).toBeVisible()
  })

  it('is not in the menu or reachable for an agent', async () => {
    // Failure caught: colleagues' hours shown to an agent.
    seedScheduling()
    backend.team = teamOverview()
    await openScheduling('/team', 'agent')
    expect(screen.queryByTestId('card-E001')).toBeNull()
    expect(screen.queryByRole('heading', { name: 'Team' })).toBeNull()
  })
})
