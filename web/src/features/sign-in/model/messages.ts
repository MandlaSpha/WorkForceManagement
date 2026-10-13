import { ApiProblem } from '@/shared/api'

/** Plain-language sign-in errors. The server answers generically on purpose, so the UI must
 * never hint whether the username exists or the account is locked. */
export function signInErrorMessage(error: unknown): string {
  if (error instanceof ApiProblem) {
    if (error.code === 'auth.invalid_credentials') return 'Username or password is incorrect.'
    if (error.code === 'auth.csrf') return 'This page has expired. Reload it and try again.'
    if (error.code === 'auth.provider_unavailable') {
      return 'This sign-in method is unavailable right now. Try another one or contact your administrator.'
    }
    return 'Something went wrong signing you in. Please try again.'
  }
  return 'Cannot reach the server. Check your connection and try again.'
}

/**
 * The message for `?error=...` on the login page after an SSO round trip. Every SSO failure maps
 * to the same words: the real reason is in the audit trail, and showing it here could help someone
 * probe which accounts or tenants exist.
 */
export function ssoErrorMessage(code: unknown): string {
  if (typeof code !== 'string' || code === '') return ''
  return "Signing in with your organisation account didn't work. Try again, or contact your administrator."
}
