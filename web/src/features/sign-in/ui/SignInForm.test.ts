import userEvent from '@testing-library/user-event'
import { render, screen, waitFor } from '@testing-library/vue'
import { createPinia } from 'pinia'
import { describe, expect, it } from 'vitest'

import { backend } from '@/test/fake-backend'

import type { SignInProvider } from '../model/providers'
import SignInForm from './SignInForm.vue'

const local: SignInProvider = {
  id: 'local',
  kind: 'local',
  label: 'Username and password',
  flow: 'credentials',
  startUrl: null,
  restricted: false,
}
const entra: SignInProvider = {
  id: 'entra',
  kind: 'oidc',
  label: 'Microsoft',
  flow: 'redirect',
  startUrl: '/api/v1/auth/sso/entra/start',
  restricted: false,
}
const okta: SignInProvider = {
  ...entra,
  id: 'okta',
  label: 'Okta',
  startUrl: '/api/v1/auth/sso/okta/start',
}
const corp: SignInProvider = { ...local, id: 'corp', kind: 'ldap', label: 'Company directory' }

function mount(props: Record<string, unknown>) {
  return render(SignInForm, { props, global: { plugins: [createPinia()] } })
}

describe('which sign-in methods are shown', () => {
  it('local only: the familiar form and nothing else', () => {
    mount({ providers: [local] })

    expect(screen.getByLabelText('Username')).toBeVisible()
    expect(screen.getByLabelText('Password')).toBeVisible()
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Sign in with')).not.toBeInTheDocument()
  })

  it('offers each SSO provider as a link to its start address', () => {
    mount({ providers: [local, entra, okta] })

    const microsoft = screen.getByRole('link', { name: 'Sign in with Microsoft' })
    expect(microsoft).toHaveAttribute('href', '/api/v1/auth/sso/entra/start?next=%2F')
    expect(screen.getByRole('link', { name: 'Sign in with Okta' })).toBeVisible()
  })

  it('keeps the password form next to SSO, separated by "or"', () => {
    mount({ providers: [local, entra] })

    expect(screen.getByText('or')).toBeVisible()
    expect(screen.getByLabelText('Username')).toBeVisible()
  })

  it('SSO only: no password form at all', () => {
    mount({ providers: [entra] })

    expect(screen.queryByLabelText('Username')).not.toBeInTheDocument()
    expect(screen.queryByText('or')).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Sign in with Microsoft' })).toBeVisible()
  })
})

describe('where SSO sends the user afterwards', () => {
  it('passes a same-site destination on, encoded', () => {
    mount({ providers: [entra], next: '/roster?week=2026-08-17' })
    expect(screen.getByRole('link', { name: 'Sign in with Microsoft' })).toHaveAttribute(
      'href',
      '/api/v1/auth/sso/entra/start?next=%2Froster%3Fweek%3D2026-08-17',
    )
  })

  it.each(['https://evil.example/phish', '//evil.example', 'javascript:alert(1)'])(
    'never passes %s to the server',
    (evil) => {
      mount({ providers: [entra], next: evil })
      expect(screen.getByRole('link', { name: 'Sign in with Microsoft' })).toHaveAttribute(
        'href',
        '/api/v1/auth/sso/entra/start?next=%2F',
      )
    },
  )
})

describe('choosing between username-and-password providers', () => {
  it('shows the first provider as selected instead of an empty box', () => {
    mount({ providers: [local, corp] })
    expect(screen.getByLabelText('Sign in with')).toHaveValue('local')
  })

  it('asks which one when there are several, and tells the server', async () => {
    const user = userEvent.setup()
    const { emitted } = mount({ providers: [local, corp] })

    await user.selectOptions(screen.getByLabelText('Sign in with'), 'corp')
    await user.type(screen.getByLabelText('Username'), 'agent')
    await user.type(screen.getByLabelText('Password'), 'correct-horse-battery')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    await waitFor(() => expect(emitted().signedIn).toHaveLength(1))
    expect(backend.lastProvider).toBe('corp')
  })

  it('uses the only provider without asking', async () => {
    const user = userEvent.setup()
    mount({ providers: [local] })

    await user.type(screen.getByLabelText('Username'), 'agent')
    await user.type(screen.getByLabelText('Password'), 'correct-horse-battery')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    await waitFor(() => expect(backend.lastProvider).toBe('local'))
  })
})

describe('emergency access when local accounts are restricted to administrators', () => {
  const breakGlass: SignInProvider = { ...local, restricted: true }

  it('hides the password form until someone asks for emergency access', async () => {
    const user = userEvent.setup()
    mount({ providers: [breakGlass, entra] })

    expect(screen.queryByLabelText('Username')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Emergency administrator sign-in' }))

    expect(screen.getByLabelText('Username')).toBeVisible()
    expect(screen.getByText(/Emergency access for administrators/)).toBeVisible()
  })

  it('signs in as a local account when used', async () => {
    const user = userEvent.setup()
    const { emitted } = mount({ providers: [breakGlass, entra] })

    await user.click(screen.getByRole('button', { name: 'Emergency administrator sign-in' }))
    await user.type(screen.getByLabelText('Username'), 'admin')
    await user.type(screen.getByLabelText('Password'), 'correct-horse-battery')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    await waitFor(() => expect(emitted().signedIn).toHaveLength(1))
    expect(backend.lastProvider).toBe('local')
  })
})

describe('errors', () => {
  it.each(['sso_failed', 'state_mismatch', 'anything-at-all'])(
    'shows one generic message for ?error=%s and never the code itself',
    (code) => {
      mount({ providers: [entra], ssoError: code })

      const banner = screen.getByRole('alert')
      expect(banner).toHaveTextContent("Signing in with your organisation account didn't work")
      expect(banner).not.toHaveTextContent(code)
    },
  )

  it('shows nothing when there is no error', () => {
    mount({ providers: [entra] })
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('says a sign-in method is unavailable without naming the cause', async () => {
    const { http, HttpResponse } = await import('msw')
    const { server } = await import('@/test/server')
    server.use(
      http.post('*/api/v1/auth/login', () =>
        HttpResponse.json(
          { code: 'auth.provider_unavailable', title: 'Sign-in unavailable', status: 503 },
          { status: 503 },
        ),
      ),
    )
    const user = userEvent.setup()
    mount({ providers: [corp] })

    await user.type(screen.getByLabelText('Username'), 'x')
    await user.type(screen.getByLabelText('Password'), 'y')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('unavailable right now')
  })
})
