# Gijima WFM — UI Specification (from the reference video)

Derived from `Files/VID-20260917-WA0001.mp4` (111 s screen recording of the reference app, logged in as Planner) and DECK screenshots.

## Global layout
- **Login**: centred card on a light background; Gijima logo, "Workforce Management / TECHNOLOGY PEOPLE"; username + password, blue "Sign in" button. Below: "Demo logins · click to fill" — `planner` (full scheduling), `lead` (approvals & QA), `agent` (own schedule & leave), `admin` (everything). Footer tagline.
- **Thin brand-blue bar** across the very top of every page.
- **Left sidebar** (~250 px, white, collapsible on mobile): logo + product name, grouped nav with line icons:
  - HOME — Dashboard *(the reference also has Copilot — parked, not built; requirements §3.12)*
  - OPERATE — Planner, Intraday, Roster, Forecast, Recommendations, Capacity, Scheduling, Service desk
  - PEOPLE — Leave, Shift swaps, Employees, Overtime, Attendance
  - INSIGHT — Analytics, Calibration, Reports
  - ADMIN — Configure
  - Footer note: "The interval engine is the spine. Coverage · Requirement · Variance @ 30-min".
  - Active item: light blue fill + left accent bar.
- **Top bar**: SITE select, QUEUE select (global filters), week stepper `‹ 17 Aug – 23 Aug ›`, notifications bell, dark-mode toggle, user chip (initials, name, role, menu).
- **Page header**: small uppercase eyebrow (e.g. OVERVIEW, • LIVE · RETENTIONS), title, one-line explanatory subtitle that says what the page does in plain words; primary actions top-right.
- **KPI tiles**: row of white rounded cards; uppercase label, big number coloured by status (red = bad, amber = warning, green = good, neutral), small caption; coloured left border on status tiles.
- **Tabs**: segmented pill group under the header (e.g. Plan | Hiring | Versions | Assumptions).
- **Tables**: uppercase muted headers, generous row height, status pills (`pending`, `published`, `Draft`, `Critical`, `unavailable`, `preferred`).
- **Loading**: skeleton bars. **Warnings**: amber callout boxes ("Before you act on these numbers").
- Typography: Inter-style sans; primary colour deep blue (#1E4FA0-ish), danger red, success green, over-staffed cyan.

## Screens

| Screen | Content |
|---|---|
| Dashboard | 7 KPI tiles (Coverage gap, Understaffed, Service level, Occupancy, Headcount, Pending approvals, Roster status); "Coverage & service by queue" table (Queue, Gap, Under, SL, Worst Δ — worst first, row click → Planner); "Week trend" combo chart (pink bars = gap per day, blue line = SL %); right column "Needs attention" (Critical pills + Resolve → buttons that deep-link to the Planner or Leave screen) and "Recent activity" feed |
| Planner | Actions: Auto-schedule week (primary), toggle Week heatmap / Day interval chart. KPIs: Under-staffed intervals (164 of 336 (49%)), Coverage gap (614 scheduled · 1098 required), Worst interval (−7 at 10:30, 5/12 on), Service-level risk (High). Variance heatmap: rows = 30-min intervals 06:00→, columns = Mon–Sun with dates, cells = signed variance number, diverging legend UNDER (deep red) → green → OVER (cyan); click a day header to drill in |
| Roster | Subtitle explains click-to-assign. Actions: Export CSV (the reference's AI "Assistant" button is parked). Card "Weekly roster — N agents skilled on <queue>", Draft pill + Publish button. Legend: Early (<09:00) amber, Day (09:00–13:00) blue, Late (from 13:00) purple, Leave, Off, Break/activity. Grid rows: agent name + `RET005 · FT · 6d 48h`; columns: day with "7 on" count; cells: shift code chips (E1, D1, D2, L1, P1, P2) or "+" |
| Forecast | Run forecast button + date picker. Area chart: contacts per 30-min (shaded) with requirement line (red, right axis). Tabs: Versions (Label, Intervals, Created, Status=published), Events, Revisions. **Built:** the run form and the selected forecast's chart stay above the tabs; tabs are Versions (archived versions are the revisions), Events, What if (scenarios) and Accuracy; only the open tab loads its data; the open tab is in the address (`?tab=events`) so a link or a reload lands on it; arrow keys, Home and End move between tabs (shared `TabBar`, also used by Configure) |
| Recommendations | Date picker; KPIs Under-staffed intervals, Coverage gap; coverage chart (bars coloured under/met/over + requirement curve "Required (Erlang C + shrinkage)"); "Recommended actions — ranked by variance reduction. Skills, leave, one-shift-per-day and 11h rest are respected" with Apply buttons |
| Capacity | Tabs Plan / Hiring / Versions / Assumptions. KPIs: Peak required FTE, Worst net FTE, Hires required, Plan cost (R). Amber warnings emitted by the planner. "Period by period" table: Period, Required, Incumbent, Attrition, Cohorts, Available, Net, Hires, Cost |
| Scheduling (depth) | (Built as separate screens: My availability, Overtime > Standby, Continuity; there is no "Scheduling" menu entry.) Reference tabs: Availability / Cross-queue flexing / Standby rota / Rotations. KPIs: People with a statement, Windows declared, Preference profiles. Explainer: no window ≠ available. Table: Employee, Kind (unavailable/preferred pill), When (Every Mon), Window, Reason |
| Leave | "Approval writes the leave into the schedule and updates coverage. Cancelling reverses both." Pending approvals table: Agent, Type, Dates, Duration, Cost (hours), Status, Decision, Approve / Reject |
| Overtime | "Authorise premium pay, run the standby rota and reconcile… Every figure is priced by the engine." Tabs Approvals / Requests / Standby / Call-outs / Pay & budgets |
| Attendance | "What happened against what was planned for <last completed week>". Tabs Variance / Timesheets / Exceptions / Clock events |
| Analytics & scenario planning | Payroll CSV button. KPIs: Service level (modelled · Erlang C), Occupancy, Shrinkage, Cost/contact (R), Forecast accuracy, Coverage gap. Info banner when nothing is measured. "Service level & cost trend" combo chart. Scenario planning section (perturb inputs, compare cost vs service) |
| Configure | Tabs Shifts / Queues / Skills / Scorecards / Adherence / Activity / Reference data. Shift templates: inline form (Code, start, end, minutes, Add shift) + chips `D1 · 09:00–17:30`, `D2 · 09:30–18:00`, `E1 · 07:00–15:30`, `L1 · 12:30–21:00`, `P1 · 10:00–14:00`, `P2 · 16:00–20:00` |
| Copilot (PARKED — not built) | Chat panel. Always shows "Answering as <name> (<role>)". Answers cite the screen/rows they came from; refusals are a standard card ("I can't share that for your role"); proposed changes appear as a confirm card that opens the normal action. No history shared between users |
| Not shown in detail (in nav) | Intraday, Service desk, Shift swaps, Employees, Calibration, Reports — design follows the same patterns; Employees per DECK slide 7 (greyed columns for defaulted fields) |

## Principles carried from the reference
1. Every page subtitle says in plain words what the page does and what an action will change.
2. Every number says whether it is measured or modelled and what it rests on.
3. Empty is honest: when a feed is missing the screen says so rather than inventing data.
4. Changes recalculate live — assigning a shift, approving leave or applying a recommendation updates coverage immediately.
