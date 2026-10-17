import userEvent from '@testing-library/user-event'
import { screen, waitFor } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import { backend } from '@/test/fake-backend'
import { openScheduling, seedScheduling } from '@/test/open-scheduling'

import { useContextStore } from './store'

describe('the top-bar queue picker', () => {
  it('is filled from the API and selects the first queue', async () => {
    seedScheduling()
    const view = await openScheduling('/planner')

    const picker = (await screen.findByLabelText('Queue')) as HTMLSelectElement
    await waitFor(() => expect(picker).toHaveValue('1'))
    expect(useContextStore(view.pinia).queueNumber).toBe(1)
    expect(screen.getByRole('option', { name: 'QueueA' })).toBeInTheDocument()
  })

  it('is not even requested for an agent, who has no queues to pick from', async () => {
    seedScheduling()
    await openScheduling('/', 'agent')
    await screen.findByText('My availability') // the signed-in shell has rendered

    expect(backend.requests.filter((r) => r.path === '/api/v1/telephony/queues')).toEqual([])
  })

  it("is emptied on sign-out so the next person never sees the last person's queues", async () => {
    seedScheduling()
    const user = userEvent.setup()
    const view = await openScheduling('/planner')
    await waitFor(() => expect(useContextStore(view.pinia).queues).toHaveLength(1))

    await user.click(await screen.findByRole('button', { name: /^Account menu/ }))
    await user.click(await screen.findByRole('menuitem', { name: 'Sign out' }))

    await waitFor(() => expect(useContextStore(view.pinia).queues).toEqual([]))
    expect(useContextStore(view.pinia).queueNumber).toBeNull()
    // Let the sign-in page it redirects to finish loading before the test ends.
    await screen.findByLabelText('Username')
  })
})
