import userEvent from '@testing-library/user-event'
import { screen, waitFor, within } from '@testing-library/vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { QualityImportReport, QualityPerson, QualityTeam } from '@/entities/workforce/quality'
import { uploadQuality } from '@/entities/workforce/quality'
import { backend } from '@/test/fake-backend'
import { openScheduling, seedScheduling } from '@/test/open-scheduling'

vi.mock('@/entities/workforce/quality/api/quality', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  uploadQuality: vi.fn(),
}))
const upload = vi.mocked(uploadQuality)

const summary = {
  evaluations: 2,
  averageScorePct: 85,
  latestScorePct: 90,
  latestOn: '2026-05-18',
  csatCount: 2,
  csatAverage: 4.5,
  coachingDue: '2026-05-20',
  coachingIsDue: true,
}
const team: QualityTeam = {
  days: 90,
  asOf: '2026-05-25',
  people: [{ employeeId: 10, empNo: 'E001', employee: 'Alex Agent', ...summary }],
}
const person: QualityPerson = {
  employeeId: 10,
  empNo: 'E001',
  employee: 'Alex Agent',
  days: 90,
  ...summary,
  results: [
    {
      evaluatedOn: '2026-05-18',
      kind: 'call',
      ref: 'c2',
      scorePct: 90,
      csat: 5,
      coachingDue: null,
    },
  ],
}
const report = (over: Partial<QualityImportReport> = {}): QualityImportReport => ({
  id: 1,
  fileName: 'q.csv',
  rowsRead: 3,
  rowsCreated: 2,
  rowsUpdated: 0,
  rowsUnchanged: 0,
  rowsRejected: 1,
  rowsUnmapped: 0,
  errors: [{ row: 3, reason: 'The score must be a number from 0 to 100.' }],
  ignoredColumns: ['comment'],
  unmappedLogins: [],
  unmappedLoginCount: 0,
  ...over,
})

beforeEach(() => {
  upload.mockReset()
  seedScheduling()
  backend.qualityTeam = team
  backend.qualityPeople = { 10: person }
})

describe('quality', () => {
  it('shows a lead their team as plain figures with no rank', async () => {
    // Failure caught: a league table, or a Due flag shown by colour alone.
    await openScheduling('/quality', 'lead')
    const row = await screen.findByTestId('row-E001')
    expect(row).toHaveTextContent('85.0%')
    expect(row).toHaveTextContent('Due (2026-05-20)')
    expect(screen.getByTestId('how-it-works')).toHaveTextContent('no ranking')
    expect(screen.queryByText(/rank #|position|league/i)).toBeNull()
    expect(screen.queryByLabelText('Quality results (.csv or .xlsx)')).toBeNull()
  })

  it('opens one person from the team table', async () => {
    const user = userEvent.setup()
    await openScheduling('/quality', 'planner')
    await user.click(await screen.findByRole('button', { name: /Alex Agent/ }))
    const detail = await screen.findByTestId('person-detail')
    expect(await within(detail).findByText('2026-05-18')).toBeVisible()
  })

  it('imports a file and reports rejected rows and ignored columns', async () => {
    const user = userEvent.setup()
    upload.mockResolvedValue(report())
    await openScheduling('/quality', 'planner')
    const chooser = await screen.findByLabelText('Quality results (.csv or .xlsx)')
    await user.upload(chooser, new File(['x'], 'q.csv'))
    await user.click(screen.getByRole('button', { name: 'Import results' }))
    expect(await screen.findByTestId('quality-done')).toHaveTextContent('2 added')
    expect(screen.getByTestId('row-errors')).toHaveTextContent('Line 3')
    expect(screen.getByTestId('ignored')).toHaveTextContent('comment')
    await waitFor(() => expect(upload).toHaveBeenCalledTimes(1))
  })

  it('gives an agent only their own results and no team table', async () => {
    // Failure caught: peers or the team table shown to an agent.
    backend.qualityTeam = null
    backend.myQuality = person
    await openScheduling('/quality', 'agent')
    expect(await screen.findByTestId('mine-average')).toHaveTextContent('85.0%')
    expect(screen.queryByTestId('team-table')).toBeNull()
    expect(screen.queryByLabelText('Quality results (.csv or .xlsx)')).toBeNull()
  })

  it('is closed to an executive', async () => {
    await openScheduling('/quality', 'executive')
    expect(screen.queryByTestId('how-it-works')).toBeNull()
  })
})
