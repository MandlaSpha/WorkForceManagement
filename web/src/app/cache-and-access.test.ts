import userEvent from '@testing-library/user-event'
import { screen, waitFor, within } from '@testing-library/vue'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'

import { kpiSummary } from '@/test/call-data-fixtures'
import { backend } from '@/test/fake-backend'
import { renderApp } from '@/test/render-app'
import { server } from '@/test/server'

function signedInAs(role: string) {
  backend.signedIn = { username: role, displayName: `Test ${role}`, role }
}

function withData() {
  backend.months = ['2026-05']
  backend.kpisByMonth = { '2026-05': kpiSummary() }
}

describe("one person's figures never reach the next person on the same browser", () => {
  it('empties the cache when the person signs out', async () => {
    withData()
    signedInAs('planner')
    const user = userEvent.setup()
    const { queryClient } = await renderApp('/')
    await screen.findByTestId('tile-offered')
    expect(queryClient.getQueryCache().getAll().length).toBeGreaterThan(0)

    await user.click(await screen.findByRole('button', { name: 'Sign out' }))

    await waitFor(() => expect(queryClient.getQueryCache().getAll()).toHaveLength(0))
  })

  it('empties the cache when the session expires under them', async () => {
    withData()
    signedInAs('planner')
    const { queryClient, router } = await renderApp('/')
    await screen.findByTestId('tile-offered')

    // The server ends the session: the next call is a 401, which signs the app out.
    backend.signedIn = null
    server.use(
      http.get('*/api/v1/telephony/months', () =>
        HttpResponse.json(
          { title: 'Not authenticated', status: 401, code: 'auth.required' },
          { status: 401 },
        ),
      ),
    )
    await queryClient.refetchQueries({ queryKey: ['call-data', 'months'] })

    await waitFor(() => expect(router.currentRoute.value.name).toBe('login'))
    await waitFor(() => expect(queryClient.getQueryCache().getAll()).toHaveLength(0))
  })
})

describe('only planners and admins reach the data import', () => {
  it.each(['planner', 'admin'])(
    'shows %s the Data import link and opens the screen',
    async (role) => {
      signedInAs(role)
      await renderApp('/')

      const nav = within(await screen.findByRole('navigation', { name: 'Main navigation' }))
      expect(nav.getByRole('link', { name: 'Data import' })).toHaveAttribute('href', '/imports')
    },
  )

  it.each(['lead', 'executive', 'customer_ops', 'agent'])(
    'hides the link from %s and refuses the address even when typed in',
    async (role) => {
      signedInAs(role)
      const { router } = await renderApp('/imports')

      expect(
        await screen.findByRole('heading', { name: "You don't have access to this page" }),
      ).toBeVisible()
      expect(router.currentRoute.value.name).toBe('forbidden')
      expect(screen.queryByRole('link', { name: 'Data import' })).toBeNull()
    },
  )
})
