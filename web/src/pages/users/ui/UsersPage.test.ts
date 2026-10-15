import userEvent from '@testing-library/user-event'
import { screen, waitFor, within } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import type { AdminUser } from '@/entities/user-admin'
import { backend } from '@/test/fake-backend'
import { openScheduling, seedScheduling } from '@/test/open-scheduling'
import { employeeOf } from '@/test/scheduling-fixtures'

const account = (over: Partial<AdminUser> = {}): AdminUser => ({
  id: 2,
  username: 'amy',
  name: 'Amy Agent',
  role: 'agent',
  roleFromDirectory: false,
  active: true,
  locked: false,
  hasPassword: true,
  mustChangePassword: false,
  employee: null,
  lastLogin: null,
  ...over,
})

async function open(users: AdminUser[] = [account()]) {
  seedScheduling()
  backend.users = [
    account({ id: 1, username: 'admin', name: 'Ash Admin', role: 'admin' }),
    ...users,
  ]
  return openScheduling('/users', 'admin')
}

describe('the user list', () => {
  it('shows each account with its role and state', async () => {
    await open([
      account({ id: 3, username: 'ben', name: 'Ben Locked', locked: true }),
      account({ id: 4, username: 'cat', name: 'Cat Off', active: false }),
      account({ id: 5, username: 'sso', name: 'Sam Sso', hasPassword: false }),
    ])
    expect(await screen.findByTestId('user-ben')).toHaveTextContent('Locked')
    expect(screen.getByTestId('user-cat')).toHaveTextContent('Switched off')
    expect(screen.getByTestId('user-sso')).toHaveTextContent('signs in through the provider')
  })

  it('gives the admin no way to change their own role or switch off their own account', async () => {
    await open()
    const own = await screen.findByTestId('user-admin')
    // Failure caught: an admin locking themselves out of the only admin screen.
    expect(within(own).queryByRole('combobox', { name: /Role of/ })).toBeNull()
    expect(within(own).queryByRole('button', { name: /Switch off/ })).toBeNull()
    expect(within(own).getByText('your own role')).toBeVisible()
  })

  it('shows a role from the identity provider as fixed, with the reason', async () => {
    await open([account({ id: 6, username: 'dir', roleFromDirectory: true })])
    const row = await screen.findByTestId('user-dir')
    expect(within(row).queryByRole('combobox', { name: /Role of/ })).toBeNull()
    expect(row).toHaveTextContent("set by the identity provider's groups")
  })
})

describe('adding a user', () => {
  it('sends the details with the CSRF token and says the person must change the password', async () => {
    const user = userEvent.setup()
    await open([])
    const form = await screen.findByRole('form', { name: 'Add a user' })
    await user.type(within(form).getByLabelText('Username'), 'newbie')
    await user.type(within(form).getByLabelText('First name'), 'New')
    await user.type(within(form).getByLabelText('Last name'), 'Person')
    await user.selectOptions(within(form).getByLabelText('Role'), 'Team lead')
    await user.type(within(form).getByLabelText('Temporary password'), 'correct-horse-battery')
    await user.click(within(form).getByRole('button', { name: 'Add user' }))

    await waitFor(() => expect(backend.writes).toHaveLength(1))
    expect(backend.writes[0]).toEqual({
      method: 'POST',
      path: '/api/v1/users',
      body: {
        username: 'newbie',
        firstName: 'New',
        lastName: 'Person',
        role: 'lead',
        password: 'correct-horse-battery',
      },
      csrf: 'test-csrf-token',
    })
    expect(await screen.findByTestId('create-result')).toHaveTextContent(
      /will be asked to change it/,
    )
    expect(await screen.findByTestId('user-newbie')).toBeVisible()
    // The temporary password is cleared from the form once it has been sent.
    expect(within(form).getByLabelText('Temporary password')).toHaveValue('')
  })

  it('shows why a user was refused, such as a weak password', async () => {
    const user = userEvent.setup()
    await open([])
    backend.nextProblem = {
      status: 422,
      code: 'password.too_weak',
      title: 'User change refused',
      detail: 'This password is too short. It must contain at least 12 characters.',
    }
    const form = await screen.findByRole('form', { name: 'Add a user' })
    await user.type(within(form).getByLabelText('Username'), 'newbie')
    await user.type(within(form).getByLabelText('Temporary password'), 'short')
    await user.click(within(form).getByRole('button', { name: 'Add user' }))
    expect(await screen.findByTestId('create-error')).toHaveTextContent(/at least 12 characters/)
  })
})

describe('changing a user', () => {
  it('changes a role with a PUT', async () => {
    const user = userEvent.setup()
    await open()
    await user.selectOptions(await screen.findByLabelText('Role of amy'), 'Planner')
    await waitFor(() => expect(backend.writes).toHaveLength(1))
    expect(backend.writes[0]).toMatchObject({
      method: 'PUT',
      path: '/api/v1/users/2/role',
      body: { role: 'planner' },
      csrf: 'test-csrf-token',
    })
  })

  it('switches an account off and on again', async () => {
    const user = userEvent.setup()
    await open()
    await user.click(await screen.findByRole('button', { name: 'Switch off amy' }))
    await waitFor(() => expect(backend.writes[0]?.body).toEqual({ active: false }))
    await user.click(await screen.findByRole('button', { name: 'Switch on amy' }))
    await waitFor(() => expect(backend.writes[1]?.body).toEqual({ active: true }))
  })

  it('offers unlock only for a locked account', async () => {
    const user = userEvent.setup()
    await open([account({ id: 3, username: 'ben', locked: true })])
    expect(screen.queryByRole('button', { name: 'Unlock amy' })).toBeNull()
    await user.click(await screen.findByRole('button', { name: 'Unlock ben' }))
    await waitFor(() =>
      expect(backend.writes[0]).toMatchObject({ method: 'POST', path: '/api/v1/users/3/unlock' }),
    )
  })

  it('sets a new temporary password, and offers none for an account that signs in elsewhere', async () => {
    const user = userEvent.setup()
    await open([account(), account({ id: 5, username: 'sso', hasPassword: false })])
    await screen.findByTestId('user-sso')
    expect(screen.queryByRole('button', { name: /new temporary password for sso/ })).toBeNull()
    await user.click(await screen.findByRole('button', { name: /new temporary password for amy/ }))
    await user.type(screen.getByLabelText('Temporary password for amy'), 'another-long-passphrase')
    await user.click(screen.getByRole('button', { name: 'Set' }))
    await waitFor(() => expect(backend.writes).toHaveLength(1))
    expect(backend.writes[0]).toMatchObject({
      path: '/api/v1/users/2/password',
      body: { password: 'another-long-passphrase' },
    })
    await waitFor(() =>
      expect(screen.getByTestId('user-amy')).toHaveTextContent('must choose a password'),
    )
  })

  it('shows why a change was refused', async () => {
    const user = userEvent.setup()
    await open()
    backend.nextProblem = {
      status: 409,
      code: 'user.role_from_directory',
      title: 'User change refused',
      detail: 'This role comes from the identity provider.',
    }
    await user.selectOptions(await screen.findByLabelText('Role of amy'), 'Planner')
    expect(await screen.findByRole('alert')).toHaveTextContent(/identity provider/)
  })
})

describe('linking a login to an employee', () => {
  it('lists only employees without a login and links the one chosen', async () => {
    const user = userEvent.setup()
    await open()
    backend.employees = [
      employeeOf({ id: 10, empNo: 'E001', name: 'Alex Agent' }),
      employeeOf({ id: 11, empNo: 'E002', name: 'Taken Already', hasLogin: true }),
    ]
    const row = await screen.findByTestId('user-amy')
    const pick = await within(row).findByLabelText('Employee for amy')
    await waitFor(() => expect(within(pick).getAllByRole('option')).toHaveLength(2))
    // Failure caught: offering someone who already has a login (one login, one employee).
    expect(within(pick).queryByRole('option', { name: /Taken Already/ })).toBeNull()
    await user.selectOptions(pick, '10')
    await user.click(within(row).getByRole('button', { name: /Link amy/ }))

    await waitFor(() => expect(backend.writes).toHaveLength(1))
    expect(backend.writes[0]).toEqual({
      method: 'PUT',
      path: '/api/v1/scheduling/employees/10/login',
      body: { userId: 2 },
      csrf: 'test-csrf-token',
    })
  })

  it('shows the linked employee and unlinks with a null', async () => {
    const user = userEvent.setup()
    await open([account({ employee: 'E001' })])
    backend.employees = [employeeOf({ id: 10, empNo: 'E001', name: 'Alex Agent', hasLogin: true })]
    const row = await screen.findByTestId('user-amy')
    expect(await within(row).findByText(/Alex Agent/)).toBeVisible()
    await user.click(within(row).getByRole('button', { name: /Unlink amy/ }))
    await waitFor(() => expect(backend.writes[0]?.body).toEqual({ userId: null }))
  })
})

describe('who may open it', () => {
  it.each(['agent', 'planner', 'lead', 'executive'])('keeps %s out', async (role) => {
    seedScheduling()
    await openScheduling('/users', role)
    expect(
      await screen.findByRole('heading', { name: "You don't have access to this page" }),
    ).toBeVisible()
  })
})
