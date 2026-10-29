# ADR 0003: Urbanist, self-hosted, as the interface font

Status: Accepted, 29 October 2026

## Context
The interface is being given a warmer, more modern look (large greeting titles, rounded cards, a floating dark sidebar). The type needs one friendly geometric face with good numerals for figures. Until now the font stack named Inter but never shipped it, so the look depended on whatever each machine had.

## Decision
Use **Urbanist** (variable), shipped with the app through the npm package `@fontsource-variable/urbanist`, so no request goes to a font service and nothing about a visitor leaves the deployment (POPIA, offline installs).

## Licence
Urbanist is under the **SIL Open Font Licence 1.1**. It is a font licence, not a software one: it allows use, embedding and redistribution in an app, including a commercial one, provided the licence travels with the font and the font is not sold on its own. It is not on the software allow-list (MIT, BSD, Apache-2.0, ISC, PSF, MPL-2.0, PostgreSQL, LGPL), so this record is the exception the coding standards ask for. No other OFL dependency is added.

## Consequences
- About 60 KB of font data is added to the web bundle; browsers cache it.
- If the licence check is added to CI later, it must allow `OFL-1.1` for fonts only.
- Changing the font later means changing one token (`--font-sans`) and removing the package.
