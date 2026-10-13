import fsd from '@feature-sliced/steiger-plugin'
import { defineConfig } from 'steiger'

// Feature-Sliced Design layer rules (code architecture section 5): a layer imports only from
// layers below it; slices on one layer do not import each other; cross-slice imports go through
// the slice's public index.ts.
export default defineConfig([
  ...fsd.configs.recommended,
  {
    // Slices are created ahead of the phases that reuse them (sign-out and the pickers will be
    // used from more than one widget), so "only one reference" would be a false alarm for now.
    files: ['./src/**'],
    //
    // Entity slices are named for the thing they are ("session", "call-data"), not forced into
    // plurals, and feature slices are verb phrases ("sign-in"), so the plural/singular check
    // would only push renames with no benefit.
    rules: { 'fsd/insignificant-slice': 'off', 'fsd/inconsistent-naming': 'off' },
  },
])
