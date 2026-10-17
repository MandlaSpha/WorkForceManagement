import userEvent from '@testing-library/user-event'
import { screen, waitFor, within } from '@testing-library/vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { uploadReport } from '@/entities/call-data'
import { ApiProblem } from '@/shared/api'
import { importReport } from '@/test/call-data-fixtures'
import { backend } from '@/test/fake-backend'
import { renderApp } from '@/test/render-app'

// Only the upload is replaced. The request it makes is checked in entities/call-data/api, because
// the test browser cannot carry a real file through a real network stack.
vi.mock('@/entities/call-data/api/call-data', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  uploadReport: vi.fn(),
}))

const upload = vi.mocked(uploadReport)

const REFUSED = new ApiProblem({
  status: 409,
  code: 'import.duplicate_period',
  title: 'Period already imported',
  detail: 'A file with the same date range and row count was imported before.',
})

/** The server accepts the file: it answers with a report and the file now shows in the list. */
function accepts(report = importReport()) {
  upload.mockImplementation(async () => {
    backend.imports = [report, ...backend.imports]
    return report
  })
}

async function openImports() {
  backend.signedIn = { username: 'planner', displayName: 'Pat Planner', role: 'planner' }
  const user = userEvent.setup()
  await renderApp('/imports')
  const chooser = await screen.findByLabelText('Call detail report (.xlsx)')
  return { user, chooser }
}

const pick = (user: ReturnType<typeof userEvent.setup>, chooser: HTMLElement, name = 'may.xlsx') =>
  user.upload(chooser, new File(['not read by the browser'], name))

const importNow = (user: ReturnType<typeof userEvent.setup>) =>
  user.click(screen.getByRole('button', { name: 'Import report' }))

beforeEach(() => {
  upload.mockReset()
})

describe('importing a report', () => {
  it('cannot be submitted until a file is chosen', async () => {
    const { user, chooser } = await openImports()
    expect(screen.getByRole('button', { name: 'Import report' })).toBeDisabled()

    await pick(user, chooser)

    expect(screen.getByRole('button', { name: 'Import report' })).toBeEnabled()
  })

  it('uploads exactly the file that was chosen, once', async () => {
    accepts()
    const { user, chooser } = await openImports()
    await pick(user, chooser, 'june-export.xlsx')
    await importNow(user)

    await screen.findByTestId('reconciles')
    expect(upload).toHaveBeenCalledTimes(1)
    expect(upload.mock.calls[0]?.[0]).toMatchObject({ name: 'june-export.xlsx' })
  })

  it('shows what was imported and that it reconciles', async () => {
    accepts()
    const { user, chooser } = await openImports()
    await pick(user, chooser)
    await importNow(user)

    expect(await screen.findByTestId('reconciles')).toHaveTextContent(/Reconciles/)
    expect(screen.getByText('Calls added').nextElementSibling).toHaveTextContent(/5\s971/)
    const sheets = within(screen.getByTestId('sheet-report'))
    expect(
      sheets.getByRole('row', { name: /Call Record Report Yes 5\s971 5\s971 None/ }),
    ).toBeVisible()
    expect(
      sheets.getByRole('row', { name: /Call IVR Details No 0 0 .*not in the file/ }),
    ).toBeVisible()
  })

  it('refreshes the list of previous imports without a page reload', async () => {
    accepts()
    const { user, chooser } = await openImports()
    expect(await screen.findByText('Nothing has been imported yet.')).toBeVisible()

    await pick(user, chooser)
    await importNow(user)

    const table = within(await screen.findByRole('table'))
    expect(table.getByText('may.xlsx')).toBeVisible()
  })
})

describe('an import that does not go ahead', () => {
  it('says nothing was imported and why, without a success card', async () => {
    upload.mockRejectedValue(REFUSED)
    const { user, chooser } = await openImports()
    await pick(user, chooser)
    await importNow(user)

    const error = await screen.findByTestId('import-error')
    expect(error).toHaveTextContent(/Nothing was imported/)
    expect(error).toHaveTextContent(/same date range and row count/)
    expect(screen.queryByTestId('reconciles')).toBeNull()
    expect(screen.getByText('Nothing has been imported yet.')).toBeVisible()
  })

  it('does not leak internals when the upload fails for any other reason', async () => {
    upload.mockRejectedValue(new TypeError('Failed to fetch http://10.0.0.5/secret'))
    const { user, chooser } = await openImports()
    await pick(user, chooser)
    await importNow(user)

    const error = await screen.findByTestId('import-error')
    expect(error).toHaveTextContent(/Something went wrong/)
    expect(error).not.toHaveTextContent(/10\.0\.0\.5|Failed to fetch/)
  })

  it('clears the old outcome when another file is chosen', async () => {
    upload.mockRejectedValue(REFUSED)
    const { user, chooser } = await openImports()
    await pick(user, chooser)
    await importNow(user)
    await screen.findByTestId('import-error')

    await pick(user, chooser, 'other.xlsx')

    expect(screen.queryByTestId('import-error')).toBeNull()
  })

  it('never presents a report that does not reconcile as a success', async () => {
    accepts(importReport({ reconciles: false }))
    const { user, chooser } = await openImports()
    await pick(user, chooser)
    await importNow(user)

    expect(await screen.findByTestId('does-not-reconcile')).toHaveTextContent(/Do not rely on them/)
    expect(screen.queryByTestId('reconciles')).toBeNull()
  })
})

describe('what the importer tells the planner about messy rows', () => {
  it('explains skipped rows and kept-with-a-warning calls in plain words, not codes', async () => {
    accepts(
      importReport({
        rowsRejected: 3,
        rejectedSummary: { 'call_type.missing': 3 },
        warnings: { 'queue_wait.negative': 1 },
      }),
    )
    const { user, chooser } = await openImports()
    await pick(user, chooser)
    await importNow(user)

    await screen.findByTestId('reconciles')
    expect(screen.getByText(/3 with no call type \(the row was skipped\)/)).toBeVisible()
    expect(screen.getByText(/1 with a negative queue wait/)).toBeVisible()
    expect(screen.queryByText(/call_type\.missing|queue_wait\.negative/)).toBeNull()
  })

  it('still says something sensible for a reason code it has no wording for yet', async () => {
    accepts(importReport({ warnings: { 'brand_new.code': 2 } }))
    const { user, chooser } = await openImports()
    await pick(user, chooser)
    await importNow(user)

    await waitFor(() =>
      expect(screen.getByText(/2 with a problem the importer reports/)).toBeVisible(),
    )
  })
})
