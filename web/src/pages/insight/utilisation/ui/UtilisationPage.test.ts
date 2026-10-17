import userEvent from '@testing-library/user-event'
import { screen, waitFor, within } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import type {
  CostReport,
  UtilisationGroup,
  UtilisationReport,
} from '@/entities/workforce/utilisation'
import { backend } from '@/test/fake-backend'
import { openScheduling } from '@/test/open-scheduling'

const group = (over: Partial<UtilisationGroup> = {}): UtilisationGroup => ({
  key: '1',
  name: 'Support',
  customer: 'Acme',
  contractId: 1,
  targetIsDefault: false,
  workedMin: 960,
  billableMin: 720,
  utilisationPct: 75,
  targetPct: 80,
  gapPct: -5,
  ...over,
})

const report = (over: Partial<UtilisationReport> = {}): UtilisationReport => ({
  month: '2026-10-01',
  basis: 'modelled',
  teams: [group({ key: '0', name: 'Team L001', customer: null, contractId: null })],
  customers: [group({ key: '7', name: 'Acme', customer: null, contractId: null })],
  contracts: [group()],
  people: [
    {
      employeeId: 10,
      empNo: 'E001',
      employee: 'Ann Agent',
      workedMin: 480,
      billableMin: 480,
      utilisationPct: 100,
      targetPct: null,
      gapPct: null,
    },
  ],
  ...over,
})

const costs = (over: Partial<CostReport> = {}): CostReport => ({
  month: '2026-10-01',
  basis: 'modelled',
  blendedHourlyRands: 115.5,
  engineersWithoutSalary: 1,
  engineers: [
    {
      employeeId: 10,
      empNo: 'E001',
      employee: 'Ann Agent',
      workedMin: 480,
      ordinaryRands: 923.1,
      overtimeRands: 300,
      totalRands: 1223.1,
      overtimeMissing: 0,
    },
    {
      employeeId: 11,
      empNo: 'E002',
      employee: 'Bob Agent',
      workedMin: 480,
      ordinaryRands: null,
      overtimeRands: 0,
      totalRands: null,
      overtimeMissing: 0,
    },
  ],
  contracts: [
    {
      contractId: 1,
      name: 'Support',
      customer: 'Acme',
      workedMin: 480,
      ordinaryRands: 923.1,
      overtimeRands: 300,
      totalRands: 1223.1,
      revenueRands: 10000,
      costPctOfRevenue: 12.2,
      overtimePctOfRevenue: 3,
      incomplete: false,
    },
  ],
  pools: [
    {
      pool: 'Desk',
      closed: 3,
      estimated: 2,
      effortMin: 90,
      costRands: 173.25,
      perTicketRands: 86.63,
    },
  ],
  ...over,
})

async function open(role: string, data: Partial<UtilisationReport> = {}) {
  backend.utilisation = report(data)
  backend.costs = ['planner', 'admin'].includes(role) ? costs() : null
  return openScheduling('/utilisation', role)
}

describe('utilisation', () => {
  it('shows worked against billable hours with the target and the gap', async () => {
    // Failure caught: a short contract shown without its gap, or a gap shown by colour alone.
    await open('planner')
    const row = await screen.findByTestId('contract-1')
    expect(row).toHaveTextContent('16.0')
    expect(row).toHaveTextContent('12.0')
    expect(row).toHaveTextContent('75.0%')
    expect(row).toHaveTextContent('80.0%')
    expect(row).toHaveTextContent('-5.0 pts (short)')
    expect(screen.getByTestId('team-0')).toBeVisible()
    expect(screen.getByTestId('customer-7')).toBeVisible()
    expect(screen.getByTestId('modelled-note')).toHaveTextContent(
      'Modelled from the published roster',
    )
  })

  it('marks a target that is only an assumption', async () => {
    await open('planner', { contracts: [group({ targetIsDefault: true })] })
    expect(await screen.findByTestId('contract-1')).toHaveTextContent('(assumed)')
  })

  it('shows a dash, not 0%, when nothing is known', async () => {
    await open('planner', {
      contracts: [group({ utilisationPct: null, targetPct: null, gapPct: null })],
    })
    const row = await screen.findByTestId('contract-1')
    expect(row).not.toHaveTextContent('0.0%')
  })

  it('lists people in the order given and shows no rank', async () => {
    // Failure caught: a league table of named people.
    await open('lead')
    const row = await screen.findByTestId('person-E001')
    expect(row).toHaveTextContent('Ann Agent')
    expect(screen.getByText(/not a ranking/)).toBeVisible()
    expect(screen.queryByText(/rank(?!ing)/i)).not.toBeInTheDocument()
  })

  it.each(['executive', 'customer_ops'])(
    'gives %s the groups and no named person',
    async (role) => {
      await open(role, { people: [] })
      expect(await screen.findByTestId('contract-1')).toBeVisible()
      expect(screen.queryByTestId('person-E001')).not.toBeInTheDocument()
      expect(screen.queryByTestId('cost-panel')).not.toBeInTheDocument()
    },
  )

  it('asks the month it shows and shows the empty state honestly', async () => {
    await open('planner', { teams: [], customers: [], contracts: [], people: [] })
    expect(await screen.findByTestId('utilisation-none')).toBeVisible()
    expect(backend.utilisationQueries[0]).toMatch(/^\d{4}-\d{2}-01$/)
  })

  it('shows the API problem if the report cannot be loaded', async () => {
    backend.utilisation = null
    await openScheduling('/utilisation', 'planner')
    expect(await screen.findByTestId('utilisation-error')).toBeVisible()
  })

  it('shows cost, overtime against revenue and says who has no salary', async () => {
    // Failure caught: an engineer with no salary shown as costing R0.
    await open('planner')
    const panel = await screen.findByTestId('cost-panel')
    const contract = within(panel).getByTestId('cost-1')
    expect(contract).toHaveTextContent('R1 223.10')
    expect(contract).toHaveTextContent('3.0%')
    expect(within(panel).getByTestId('engineer-E002')).toHaveTextContent('No salary on file')
    // The ordinary-pay cell is a dash: nothing is priced, so nothing is claimed.
    expect(
      within(within(panel).getByTestId('engineer-E002')).getAllByRole('cell')[1],
    ).toHaveTextContent(/^-$/)
    expect(within(panel).getByTestId('no-salary')).toHaveTextContent('1 engineer(s)')
    expect(within(panel).getByTestId('pool-Desk')).toHaveTextContent('R86.63')
  })

  it('does not even ask for pay figures when the role may not see them', async () => {
    await open('lead')
    await screen.findByTestId('contract-1')
    expect(screen.queryByTestId('cost-panel')).not.toBeInTheDocument()
    expect(screen.queryByText(/R\d/)).not.toBeInTheDocument()
  })

  it('lets only the admin set the terms, and sends them', async () => {
    // Failure caught: the form offered to a planner, or the target sent as text.
    await open('planner')
    await screen.findByTestId('contract-1')
    expect(screen.queryByLabelText('Contract to set terms for')).not.toBeInTheDocument()
  })

  it('sends the target and revenue when the admin saves', async () => {
    await open('admin')
    const user = userEvent.setup()
    await user.selectOptions(await screen.findByLabelText('Contract to set terms for'), '1')
    const target = await screen.findByLabelText('Utilisation target (%)')
    await user.clear(target)
    await user.type(target, '65')
    await user.type(screen.getByLabelText('Monthly revenue (rands, optional)'), '20000')
    await user.click(screen.getByRole('button', { name: 'Save terms' }))
    expect(await screen.findByTestId('terms-saved')).toBeVisible()
    const write = backend.writes.find((w) => w.path.endsWith('/contracts/1/terms'))
    expect(write?.method).toBe('PUT')
    expect(write?.body).toEqual({ utilisationTargetPct: 65, monthlyRevenueRands: 20000 })
  })

  it('refuses a target out of range before sending', async () => {
    await open('admin')
    const user = userEvent.setup()
    await user.selectOptions(await screen.findByLabelText('Contract to set terms for'), '1')
    const target = await screen.findByLabelText('Utilisation target (%)')
    await user.clear(target)
    await user.type(target, '150')
    await user.click(screen.getByRole('button', { name: 'Save terms' }))
    expect(await screen.findByText('A target is above 0 and at most 100.')).toBeVisible()
    expect(backend.writes).toHaveLength(0)
  })

  it('shows a refused save plainly', async () => {
    await open('admin')
    backend.nextProblem = {
      status: 422,
      code: 'utilisation.target_invalid',
      title: 'Invalid request',
      detail: 'The utilisation target is above 0 and at most 100%.',
    }
    const user = userEvent.setup()
    await user.selectOptions(await screen.findByLabelText('Contract to set terms for'), '1')
    await user.click(await screen.findByRole('button', { name: 'Save terms' }))
    const error = await screen.findByTestId('terms-error')
    expect(error).toHaveTextContent('Nothing was saved')
  })

  it('keeps an agent out', async () => {
    await openScheduling('/utilisation', 'agent')
    expect(
      await screen.findByRole('heading', { name: "You don't have access to this page" }),
    ).toBeVisible()
    await waitFor(() => expect(backend.utilisationQueries).toHaveLength(0))
  })
})
