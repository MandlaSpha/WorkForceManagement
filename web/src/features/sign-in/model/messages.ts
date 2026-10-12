import { ApiProblem } from '@/shared/api'

/** Plain-language sign-in errors. The server answers generically on purpose, so the UI must
 * never hint whether the username exists or the account is locked. */
export function signInErrorMessage(error: unknown): string {
  if (error instanceof ApiProblem) {
    if (error.code === 'auth.invalid_credentials') return 'Username or password is incorrect.'
    if (error.code === 'auth.csrf') return 'This page has expired. Reload it and try again.'
    return 'Something went wrong signing you in. Please try again.'
  }
  return 'Cannot reach the server. Check your connection and try again.'
}
