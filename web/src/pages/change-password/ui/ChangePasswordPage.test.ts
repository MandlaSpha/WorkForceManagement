import userEvent from '@testing-library/user-event'
import { screen, waitFor, within } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import { backend } from '@/test/fake-backend'
import { openScheduling, seedScheduling } from '@/test/open-scheduling'
import { renderApp } from '@/test/render-app'

async function openAs(role: string, mustChange: boolean, path = '/') {
  seedScheduling()
  const view = await openScheduling(path, role)
  backend.signedIn = {
    username: role,
    displayName: `Test ${role}`,
    role,
    mustChangePassword: mustChange,
  }
  return view
}

async function signedInWithTemporaryPassword(path: string) {
  seedScheduling()
  backend.signedIn = {
    username: 'amy',
    displayName: 'Amy Agent',
    role: 'agent',
    mustChangePassword: true,
  }
  document.cookie = 'csrftoken=test-csrf-token'
  return renderApp(path)
}

describe('a temporary password', () => {
  it.each(['/my-schedule', '/leave', '/shift-swaps'])(
    'sends the person to change it before %s opens',
    async (path) => {
      // Failure caught: using the app on a password an admin knows.
      const view = await signedInWithTemporaryPassword(path)
      expect(await screen.findByRole('form', { name: 'Change your password' })).toBeVisible()
      expect(view.router.currentRoute.value.name).toBe('change-password')
      expect(screen.getByTestId('forced-notice')).toHaveTextContent(/temporary password/)
    },
  )

  it('lets them in once it has been changed', async () => {
    const user = userEvent.setup()
    const view = await signedInWithTemporaryPassword('/my-schedule')
    const form = await screen.findByRole('form', { name: 'Change your password' })
    await user.type(within(form).getByLabelText('Your current password'), 'temp-password-123')
    await user.type(within(form).getByLabelText('New password'), 'a-much-better-passphrase')
    await user.type(within(form).getByLabelText('New password again'), 'a-much-better-passphrase')
    await user.click(within(form).getByRole('button', { name: 'Change password' }))

    await waitFor(() => expect(backend.writes).toHaveLength(1))
    expect(backend.writes[0]).toEqual({
      method: 'POST',
      path: '/api/v1/auth/change-password',
      body: { current: 'temp-password-123', new: 'a-much-better-passphrase' },
      csrf: 'test-csrf-token',
    })
    await waitFor(() => expect(view.router.currentRoute.value.path).toBe('/my-schedule'))
  })
})

describe('the form', () => {
  it('will not send two new passwords that differ, and says so', async () => {
    const user = userEvent.setup()
    await signedInWithTemporaryPassword('/my-schedule')
    const form = await screen.findByRole('form', { name: 'Change your password' })
    await user.type(within(form).getByLabelText('Your current password'), 'old')
    await user.type(within(form).getByLabelText('New password'), 'one-long-passphrase')
    await user.type(within(form).getByLabelText('New password again'), 'another-long-passphrase')
    expect(await screen.findByTestId('mismatch')).toBeVisible()
    expect(within(form).getByRole('button', { name: 'Change password' })).toBeDisabled()
    expect(backend.writes).toHaveLength(0)
  })

  it('shows why it was refused', async () => {
    const user = userEvent.setup()
    await signedInWithTemporaryPassword('/my-schedule')
    backend.nextProblem = {
      status: 422,
      code: 'password.wrong',
      title: 'User change refused',
      detail: 'That is not your current password.',
    }
    const form = await screen.findByRole('form', { name: 'Change your password' })
    await user.type(within(form).getByLabelText('Your current password'), 'wrong')
    await user.type(within(form).getByLabelText('New password'), 'a-much-better-passphrase')
    await user.type(within(form).getByLabelText('New password again'), 'a-much-better-passphrase')
    await user.click(within(form).getByRole('button', { name: 'Change password' }))
    expect(await screen.findByTestId('change-error')).toHaveTextContent(/not your current password/)
  })
})

describe('a normal password', () => {
  it('does not send anyone to the change page', async () => {
    const view = await openAs('agent', false, '/my-schedule')
    expect(view.router.currentRoute.value.path).toBe('/my-schedule')
  })
})
