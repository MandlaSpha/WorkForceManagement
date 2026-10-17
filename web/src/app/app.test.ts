import userEvent from '@testing-library/user-event'
import { screen, waitFor, within } from '@testing-library/vue'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { backend } from '@/test/fake-backend'
import { renderApp } from '@/test/render-app'

const PASSWORD = 'correct-horse-battery'

async function signIn(
  user: ReturnType<typeof userEvent.setup>,
  username: string,
  password = PASSWORD,
) {
  await user.type(screen.getByLabelText('Username'), username)
  await user.type(screen.getByLabelText('Password'), password)
  await user.click(screen.getByRole('button', { name: 'Sign in' }))
}

const sidebar = () => within(screen.getByRole('navigation', { name: 'Main navigation' }))

describe('signing in', () => {
  it('asks anonymous visitors to sign in and remembers the destination', async () => {
    const { router } = await renderApp('/roster')

    expect(await screen.findByRole('heading', { name: 'Workforce Management' })).toBeVisible()
    expect(screen.getByLabelText('Username')).toBeVisible()
    expect(router.currentRoute.value.query.redirect).toBe('/roster')
  })

  it('takes a planner to the dashboard and shows who they are', async () => {
    const user = userEvent.setup()
    const { router } = await renderApp('/login')

    await signIn(user, 'planner')

    expect(await screen.findByRole('heading', { name: 'Dashboard' })).toBeVisible()
    expect(router.currentRoute.value.name).toBe('dashboard')
    const menu = screen.getByRole('button', { name: 'Account menu for Pat Planner' })
    expect(within(menu).getByText('Planner')).toBeVisible()
  })

  it('keeps the account actions in a menu that opens, closes and leads to change password', async () => {
    // Failure caught: Sign out and Change password loose in the top bar again, or a menu that
    // cannot be closed from the keyboard.
    backend.signedIn = { username: 'planner', displayName: 'Pat Planner', role: 'planner' }
    const user = userEvent.setup()
    await renderApp('/employees')
    const trigger = await screen.findByRole('button', { name: /^Account menu/ })
    expect(screen.queryByRole('menuitem', { name: 'Sign out' })).toBeNull()
    expect(trigger).toHaveAttribute('aria-expanded', 'false')

    await user.click(trigger)
    expect(trigger).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByRole('menuitem', { name: 'Change password' })).toBeVisible()
    expect(screen.getByRole('menuitem', { name: 'Sign out' })).toBeVisible()

    await user.keyboard('{Escape}')
    expect(screen.queryByRole('menu')).toBeNull()
    expect(trigger).toHaveFocus()

    await user.click(trigger)
    await user.click(screen.getByRole('heading', { name: 'Employees', level: 1 }))
    expect(screen.queryByRole('menu')).toBeNull()

    await user.click(trigger)
    await user.click(screen.getByRole('menuitem', { name: 'Change password' }))
    expect(await screen.findByRole('heading', { name: 'Change your password' })).toBeVisible()
    expect(screen.queryByRole('menu')).toBeNull()
  })

  it('sends the user where they were going, but only to a same-site address', async () => {
    const user = userEvent.setup()
    const { router } = await renderApp('/login?redirect=/forecast')
    await signIn(user, 'planner')
    await waitFor(() => expect(router.currentRoute.value.name).toBe('forecast'))
  })

  it('ignores an off-site redirect target', async () => {
    const user = userEvent.setup()
    const { router } = await renderApp('/login?redirect=//evil.example')
    await signIn(user, 'planner')
    await waitFor(() => expect(router.currentRoute.value.name).toBe('dashboard'))
  })

  it('says the credentials are wrong without revealing why', async () => {
    const user = userEvent.setup()
    const { router } = await renderApp('/login')

    await signIn(user, 'planner', 'wrong-password')

    expect(await screen.findByRole('alert')).toHaveTextContent('Username or password is incorrect.')
    expect(router.currentRoute.value.name).toBe('login')
  })

  it('treats an unknown user exactly like a wrong password', async () => {
    const user = userEvent.setup()
    await renderApp('/login')

    await signIn(user, 'nobody', 'whatever-password')

    expect(await screen.findByRole('alert')).toHaveTextContent('Username or password is incorrect.')
  })

  it('keeps the button disabled until both fields are filled', async () => {
    const user = userEvent.setup()
    await renderApp('/login')
    const button = screen.getByRole('button', { name: 'Sign in' })
    expect(button).toBeDisabled()

    await user.type(screen.getByLabelText('Username'), 'planner')
    expect(button).toBeDisabled()
    await user.type(screen.getByLabelText('Password'), 'x')
    expect(button).toBeEnabled()
  })

  it('signs in at one click from the demo panel, for either team', async () => {
    // Failure caught: the panel only filling the form, so a demo needs a second click, or a
    // team's accounts missing from the panel.
    vi.stubEnv('VITE_DEMO_LOGINS', '1')
    vi.stubEnv('VITE_DEMO_PASSWORD', 'correct-horse-battery')
    const user = userEvent.setup()
    const { router } = await renderApp('/login')
    const panel = await screen.findByRole('region', { name: 'Demo logins' })
    for (const name of ['lead2', 'agent6', 'agent10', 'agent5']) {
      expect(within(panel).getByText(name)).toBeVisible()
    }
    await user.click(within(panel).getByText('planner'))
    await waitFor(() => expect(router.currentRoute.value.name).not.toBe('login'))
    expect(backend.signedIn?.username).toBe('planner')
  })

  it('hides the demo-login shortcuts unless explicitly enabled', async () => {
    await renderApp('/login')
    expect(screen.queryByText(/Demo logins/)).not.toBeInTheDocument()
  })
})

afterEach(() => {
  vi.unstubAllEnvs()
})

describe('what each role sees in the sidebar', () => {
  it('planner: planning screens, no admin screens', async () => {
    backend.signedIn = { username: 'planner', displayName: 'Pat Planner', role: 'planner' }
    await renderApp('/')

    expect(await sidebar().findByRole('link', { name: 'Planner' })).toBeVisible()
    expect(sidebar().getByRole('link', { name: 'Roster' })).toBeVisible()
    expect(sidebar().queryByRole('link', { name: 'Configure' })).not.toBeInTheDocument()
    expect(sidebar().queryByRole('link', { name: 'Audit log' })).not.toBeInTheDocument()
    expect(sidebar().queryByRole('link', { name: 'My schedule' })).not.toBeInTheDocument()
  })

  it('agent: only their own screens', async () => {
    backend.signedIn = { username: 'agent', displayName: 'Alex Agent', role: 'agent' }
    await renderApp('/')

    expect(await sidebar().findByRole('link', { name: 'My schedule' })).toBeVisible()
    expect(sidebar().getByRole('link', { name: 'Leave' })).toBeVisible()
    for (const hidden of ['Planner', 'Roster', 'Overtime', 'Configure', 'Dashboard']) {
      expect(sidebar().queryByRole('link', { name: hidden })).not.toBeInTheDocument()
    }
  })

  it('admin: everything including configuration and the audit log', async () => {
    backend.signedIn = { username: 'admin', displayName: 'Ash Admin', role: 'admin' }
    await renderApp('/')

    expect(await sidebar().findByRole('link', { name: 'Configure' })).toBeVisible()
    expect(sidebar().getByRole('link', { name: 'Audit log' })).toBeVisible()
  })

  it('shows an agent a forbidden page, not planning data, for a typed-in address', async () => {
    backend.signedIn = { username: 'agent', displayName: 'Alex Agent', role: 'agent' }
    await renderApp('/planner')

    expect(
      await screen.findByRole('heading', { name: "You don't have access to this page" }),
    ).toBeVisible()
  })
})

describe('top bar', () => {
  it('shows honest empty pickers until sites and queues exist', async () => {
    backend.signedIn = { username: 'planner', displayName: 'Pat Planner', role: 'planner' }
    await renderApp('/planner')

    expect(await screen.findByRole('option', { name: 'No sites yet' })).toBeInTheDocument()
    expect(screen.getByLabelText('Site')).toBeDisabled()
    expect(screen.getByLabelText('Queue')).toBeDisabled()
  })

  it('hides site and queue pickers from agents', async () => {
    backend.signedIn = { username: 'agent', displayName: 'Alex Agent', role: 'agent' }
    await renderApp('/planner')

    await screen.findByRole('link', { name: 'My schedule' })
    expect(screen.queryByLabelText('Site')).not.toBeInTheDocument()
  })

  it('shows only the pickers the open screen reads', async () => {
    // Failure caught: a week stepper on every screen, including ones it does nothing for.
    backend.signedIn = { username: 'planner', displayName: 'Pat Planner', role: 'planner' }
    await renderApp('/employees')
    await screen.findByRole('link', { name: 'Employees' })
    expect(screen.queryByRole('group', { name: 'Week' })).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Queue')).not.toBeInTheDocument()
  })

  it('shows the queue but no week on a screen that reads only the queue', async () => {
    backend.signedIn = { username: 'planner', displayName: 'Pat Planner', role: 'planner' }
    await renderApp('/peaks')
    expect(await screen.findByLabelText('Queue')).toBeVisible()
    expect(screen.queryByRole('group', { name: 'Week' })).not.toBeInTheDocument()
  })

  it('moves the week with the stepper', async () => {
    backend.signedIn = { username: 'planner', displayName: 'Pat Planner', role: 'planner' }
    const user = userEvent.setup()
    await renderApp('/')

    const group = within(await screen.findByRole('group', { name: 'Week' }))
    const before = group.getByText(/–/).textContent
    await user.click(group.getByRole('button', { name: 'Next week' }))
    const after = group.getByText(/–/).textContent
    await user.click(group.getByRole('button', { name: 'Previous week' }))

    expect(after).not.toBe(before)
    expect(group.getByText(/–/).textContent).toBe(before)
  })

  it('switches to dark mode and remembers it', async () => {
    backend.signedIn = { username: 'planner', displayName: 'Pat Planner', role: 'planner' }
    const user = userEvent.setup()
    await renderApp('/')

    await user.click(await screen.findByRole('button', { name: 'Switch to dark mode' }))

    expect(document.documentElement).toHaveClass('dark')
    expect(localStorage.getItem('wfm.theme')).toBe('dark')
    expect(screen.getByRole('button', { name: 'Switch to light mode' })).toBeVisible()
  })

  it('signs out and returns to the login page', async () => {
    backend.signedIn = { username: 'planner', displayName: 'Pat Planner', role: 'planner' }
    const user = userEvent.setup()
    const { router } = await renderApp('/')

    await user.click(await screen.findByRole('button', { name: /^Account menu/ }))
    await user.click(await screen.findByRole('menuitem', { name: 'Sign out' }))

    await waitFor(() => expect(router.currentRoute.value.name).toBe('login'))
    expect(backend.signedIn).toBeNull()
  })
})

describe('honest empty states', () => {
  it('shows the dashboard with no invented figures before any data is imported', async () => {
    backend.signedIn = { username: 'planner', displayName: 'Pat Planner', role: 'planner' }
    await renderApp('/')

    expect(await screen.findByRole('status')).toHaveTextContent(/There is no call data to show yet/)
  })
})

describe('sign-in methods on the login page', () => {
  const entra = {
    id: 'entra',
    kind: 'oidc',
    label: 'Microsoft',
    flow: 'redirect' as const,
    startUrl: '/api/v1/auth/sso/entra/start',
    restricted: false,
  }

  it('offers SSO next to the password form, carrying the page the user wanted', async () => {
    backend.providers = [...backend.providers, entra]
    await renderApp('/login?redirect=/roster')

    const link = await screen.findByRole('link', { name: 'Sign in with Microsoft' })
    expect(link).toHaveAttribute('href', '/api/v1/auth/sso/entra/start?next=%2Froster')
    expect(screen.getByLabelText('Username')).toBeVisible()
  })

  it('shows one generic message after a failed SSO round trip', async () => {
    backend.providers = [...backend.providers, entra]
    await renderApp('/login?error=sso_failed')

    expect(await screen.findByRole('alert')).toHaveTextContent(
      "Signing in with your organisation account didn't work",
    )
  })

  it('still signs in with the password form when SSO is also offered', async () => {
    backend.providers = [...backend.providers, entra]
    const user = userEvent.setup()
    const { router } = await renderApp('/login')
    await screen.findByRole('link', { name: 'Sign in with Microsoft' })

    await signIn(user, 'planner')

    await waitFor(() => expect(router.currentRoute.value.name).toBe('dashboard'))
  })
})

describe('which sidebar entry is highlighted', () => {
  it('marks only the screen the user is on, and never the dashboard everywhere', async () => {
    backend.signedIn = { username: 'planner', displayName: 'Pat Planner', role: 'planner' }
    await renderApp('/roster')

    const roster = await sidebar().findByRole('link', { name: 'Roster' })
    expect(roster).toHaveAttribute('aria-current', 'page')
    expect(sidebar().getByRole('link', { name: 'Dashboard' })).not.toHaveAttribute('aria-current')
    expect(sidebar().getByRole('link', { name: 'Forecast' })).not.toHaveAttribute('aria-current')
  })

  it('marks the dashboard on the dashboard', async () => {
    backend.signedIn = { username: 'planner', displayName: 'Pat Planner', role: 'planner' }
    await renderApp('/')

    expect(await sidebar().findByRole('link', { name: 'Dashboard' })).toHaveAttribute(
      'aria-current',
      'page',
    )
  })
})
