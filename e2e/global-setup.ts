import { mkdirSync, writeFileSync } from 'node:fs'

/**
 * The menu starts with only the current group open, as a person would see it. Most specs click a
 * menu link in some other group, so they start with every group open (what a person who had opened
 * them all would have). The menu's own behaviour is tested by its unit tests and by the specs that
 * clear this.
 */
export const OPEN_MENU_STATE = './.state/open-menu.json'
const GROUPS = ['Home', 'My work', 'Operate', 'People', 'Insight', 'Admin']

export default function globalSetup(): void {
  const origin = new URL(process.env.WFM_BASE_URL ?? 'http://localhost:5173').origin
  mkdirSync('./.state', { recursive: true })
  writeFileSync(
    OPEN_MENU_STATE,
    JSON.stringify({
      cookies: [],
      origins: [
        { origin, localStorage: [{ name: 'wfm.nav.open', value: JSON.stringify(GROUPS) }] },
      ],
    }),
  )
}
