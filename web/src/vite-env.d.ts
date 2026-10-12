/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** "1" shows the demo-login shortcut panel (development only). */
  readonly VITE_DEMO_LOGINS?: string
  /** Password of the synthetic demo accounts; set in a local .env, never committed. */
  readonly VITE_DEMO_PASSWORD?: string
}
