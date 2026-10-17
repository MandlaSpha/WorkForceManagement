import userEvent from '@testing-library/user-event'
import { screen, waitFor, within } from '@testing-library/vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type {
  AttendanceDay,
  AttendancePerson,
  StateImportReport,
} from '@/entities/workforce/attendance'
import { uploadStates } from '@/entities/workforce/attendance'
import { ApiProblem } from '@/shared/api'
import { backend } from '@/test/fake-backend'
import { openScheduling, seedScheduling } from '@/test/open-scheduling'

// Only the upload is replaced; the request it makes is checked in the entity's own test.
vi.mock('@/entities/workforce/attendance/api/attendance', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  uploadStates: vi.fn(),
}))
const upload = vi.mocked(uploadStates)

beforeEach(() => {
  upload.mockReset()
})

const figures = {
  hasData: true,
  scheduledMin: 480,
  inAdherenceMin: 420,
  outOfAdherenceMin: 60,
  adherencePct: 87.5,
  lateStartMin: 0,
  earlyFinishMin: 0,
  exceptions: ['out_of_adherence'],
}

const person = (over: Partial<AttendancePerson> = {}): AttendancePerson => ({
  employeeId: 10,
  empNo: 'E001',
  employee: 'Ann Agent',
  shiftCode: 'D1',
  ...figures,
  ...over,
})

const day = (over: Partial<AttendanceDay> = {}): AttendanceDay => ({
  queue: 'QueueA',
  day: '2031-03-03',
  teamAdherencePct: 87.5,
  withData: 1,
  withoutData: 1,
  people: [
    person(),
    person({
      employeeId: 11,
      empNo: 'E002',
      employee: 'Bob Agent',
      hasData: false,
      adherencePct: null,
      exceptions: [],
      inAdherenceMin: 0,
      outOfAdherenceMin: 0,
    }),
  ],
  ...over,
})

const report = (over: Partial<StateImportReport> = {}): StateImportReport => ({
  id: 1,
  fileName: 'states.csv',
  rowsRead: 5,
  rowsInserted: 3,
  rowsDuplicate: 1,
  rowsRejected: 1,
  rowsUnmapped: 0,
  errors: [{ row: 4, reason: 'state is not one of the known states' }],
  unmappedLogins: [],
  unmappedLoginCount: 0,
  ...over,
})

async function open(role = 'planner', over: Partial<AttendanceDay> = {}) {
  seedScheduling()
  backend.adherence = day(over)
  return openScheduling('/attendance', role)
}

async function openImport() {
  await open('planner')
  const user = userEvent.setup()
  const chooser = await screen.findByLabelText('Agent-state file (.csv)')
  return { user, chooser }
}

describe('attendance', () => {
  it('shows each person with their adherence and exceptions', async () => {
    // Failure caught: exceptions hidden, or the team figure counting people with no data.
    await open()
    const row = await screen.findByTestId('row-E001')
    expect(row).toHaveTextContent('87.5%')
    expect(within(row).getByText('Below adherence target')).toBeVisible()
    expect(screen.getByTestId('team-adherence')).toHaveTextContent('87.5%')
    expect(screen.getByTestId('with-data')).toHaveTextContent('1')
  })

  it('says "no data" for a person with no agent-state rows instead of 0%', async () => {
    // Failure caught: a feed that has not been loaded presented as a no-show.
    await open()
    const row = await screen.findByTestId('row-E002')
    expect(row).toHaveTextContent('No agent-state data for this shift')
    expect(row).not.toHaveTextContent('0.0%')
  })

  it('says so when nobody is rostered', async () => {
    await open('planner', { people: [], withData: 0, withoutData: 0, teamAdherencePct: null })
    expect(await screen.findByTestId('nobody')).toBeVisible()
    expect(screen.getByTestId('team-adherence')).toHaveTextContent('-')
  })

  it('shows the API problem if the day cannot be loaded', async () => {
    seedScheduling()
    backend.adherence = null
    await openScheduling('/attendance', 'planner')
    expect(await screen.findByTestId('attendance-error')).toBeVisible()
  })

  it('lets a planner load a state file and reports what was kept, skipped and unmapped', async () => {
    // Failure caught: unmapped logins or rejected rows silently dropped without telling anyone.
    upload.mockResolvedValue(report({ unmappedLogins: ['ghost'], unmappedLoginCount: 1 }))
    const { user, chooser } = await openImport()
    await user.upload(chooser, new File(['x'], 'states.csv'))
    await user.click(screen.getByRole('button', { name: 'Import states' }))
    expect(await screen.findByTestId('states-done')).toHaveTextContent('3 of 5 rows stored')
    expect(screen.getByTestId('unmapped')).toHaveTextContent('ghost')
    expect(screen.getByTestId('row-errors')).toHaveTextContent(
      'Line 4: state is not one of the known states',
    )
    expect(upload).toHaveBeenCalledTimes(1)
    expect(upload.mock.calls[0]?.[0]).toMatchObject({ name: 'states.csv' })
  })

  it('shows a refused file plainly', async () => {
    upload.mockRejectedValue(
      new ApiProblem({
        status: 422,
        code: 'attendance.bad_header',
        title: 'Attendance import refused',
        detail: 'The first line must name the columns.',
      }),
    )
    const { user, chooser } = await openImport()
    await user.upload(chooser, new File(['x'], 'bad.csv'))
    await user.click(screen.getByRole('button', { name: 'Import states' }))
    const error = await screen.findByTestId('states-error')
    expect(error).toHaveTextContent('Nothing was imported')
    expect(error).toHaveTextContent('The first line must name the columns.')
  })

  it('gives a lead the day but no import panel', async () => {
    // Failure caught: the import panel offered to a role the API refuses.
    await open('lead')
    expect(await screen.findByTestId('row-E001')).toBeVisible()
    await waitFor(() =>
      expect(screen.queryByLabelText('Agent-state file (.csv)')).not.toBeInTheDocument(),
    )
  })

  it.each(['agent', 'executive', 'customer_ops'])('keeps %s out', async (role) => {
    await open(role)
    expect(
      await screen.findByRole('heading', { name: "You don't have access to this page" }),
    ).toBeVisible()
  })
})
