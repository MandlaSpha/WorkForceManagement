# Walkthrough: what each phase does, and how to see it

Plain-language tour of what is built, in the order it was built. Each section says who uses it,
where to click, what you should see, and the rule behind it. Screens are in the left menu.
Everything here is synthetic or your own imported data; nothing comes from `Files/`.

**Sign in** at the web address shown in the Aspire dashboard (http://localhost:15888). The demo
logins (made by `seed_demo`) are `planner`, `lead`, `agent`, `admin`, `executive`, `customerops`,
all with the demo password. Sign in as different roles to see how the menu and the data change.

## The idea in one paragraph

Call volumes come in (imported from the telephony reports). The system **forecasts** how many calls
and how long they will take, works out **how many people each half hour needs**, lets a planner
build a **roster** against that, shows where it is **short or over-staffed**, and now lets staff
**ask for leave** that flows back into the roster. Every change is written to a tamper-evident
**audit trail**. Which screens exist depends on the customer's **feature switches**.

## Phase 0-1: Foundations (no screen of their own)

| Piece | What it gives you | See it |
|---|---|---|
| Roles and sign-in | Six roles; each sees only what it may. Out-of-scope records answer "not found". | Sign in as `agent`, then `executive`: different menus. Open a URL you may not see: "You don't have access". |
| Audit trail | Who did what, when. Chained hashes so editing or deleting a row is detected. | Admin, **Audit log**. Do anything, then find it here. |
| Feature switches | VMK turns modules on or off per customer; a switched-off module disappears and its API refuses. | Admin, **Configure**. |
| Data import | Reads the telephony call-detail workbook into half-hour call volumes and handling times. | **Data import**: upload a workbook, see rows read and rows refused with reasons. |
| Engine | The maths (Erlang C staffing, shrinkage, service level), pure code with hand-worked tests. | Not a screen; it drives every number below. |

## Phase 1: Forecast

**Who:** planner. **Screen:** Forecast.
1. Pick a queue. The chart shows past volume and the forecast ahead.
2. Tabs: forecast, **accuracy** (how close past forecasts were, per day), **Calibration** (tune how
   much history to trust; it suggests a multiplier that removes bias), **Events** (a promotion or
   outage that should lift or lower volume).
3. The system uses the Prophet model only when it beats the simple baseline in a back-test,
   otherwise it falls back. The screen says which one it used.

Why it matters: the forecast is the demand that every staffing number rests on.

## Phase 2: Roster and coverage

**Who:** planner builds, lead reads, agent sees their own.
1. **Roster**: pick a week, assign people to shift patterns. The chart shows required vs rostered
   people per half hour: red where short, blue where over.
2. The roster refuses rule breaks with a reason (rest hours between shifts, too many days in a row,
   person on approved leave).
3. **Publish** a week to make it visible to staff. Changing a published week is audited.

## Phase 2: Capacity, scenarios, dashboard, service desk

- **Capacity:** the permanent 100 plus seasonal 250 against required hours, with overflow shown.
  Try a scenario ("what if volume is 15% higher") and see the gap change without touching the
  real roster.
- **Dashboard:** coverage per queue and a plain "needs attention" list (rule-based, no AI).
- **Service desk:** workload for ticket-style work by resource pool, based on effort, not calls.

## Phase 3: Leave and approvals (newest)

**Agent** (`agent`):
1. **Leave**: balances per kind ("11 of 15 days left"; unpaid shows "no limit").
2. Ask for leave: kind and dates. It tells you how many *working* days were counted (weekends and
   South African public holidays excluded). There is no reason field on purpose, so medical detail
   is never stored.
3. Cancel a waiting request, or approved leave that has not finished.

**Lead / planner** (`lead`):
1. **Leave > Approvals**: waiting requests.
2. **Show coverage impact** first: shifts and hours given up, half-hours that become short.
   Looking decides nothing.
3. Approve or reject. You cannot decide your own request.
4. Approval removes that person's shifts on those days; the Roster then shows the gap and refuses
   to rota them. Cancelling approved leave puts shifts back where the person is still free and
   tells you how many could not go back.

**Admin:** **Leave > Entitlements** sets days per year. Defaults are South African (BCEA) and are
marked "not confirmed" until saved.

Five-minute demo script: agent asks for Mon-Tue leave; sign in as lead; open impact; approve; open
the Roster for that week and see the shifts gone; sign in as agent and cancel.

## Phase 3: Shift swaps (SWP-01)

Privacy first: an agent never sees another agent's name or schedule. A swap is a *request on a board*.

1. **Post** (`agent`): *Shift swaps > Post a swap request*. Pick one of your coming shifts and post it. Nobody is named.
2. **Take** (`lead` is the demo colleague): *Open requests* shows "A colleague on Demo Support wants to swap away D1, Mon 25 May 09:00-17:30", with no name, and only requests where at least one of your own shifts would work (rest, hours, leave, availability, one shift a day). *Take it...* lists exactly those shifts of yours; pick the one you offer in return.
3. **Approve** (`planner`, `admin` or the lead of the team): *Approvals*. Approving exchanges the two shifts on the roster (check the Roster page). Nobody approves a swap they are part of, so the demo lead's swap goes to a planner.

The two people see each other's names once it is matched. With the demo data there are two open requests the demo agent can take, one matched and waiting for approval, and one approved.

## Phase 3: The agent's own pages and availability (SCH-08, ESS-01)

Sign in as `agent`: you land on **My schedule**: the whole month as a Monday-to-Sunday calendar with your published shifts and leave (use the arrows to move between months, *List* for a plain list). Shifts in a week the planner has not published are only counted ("2 shifts are not published yet"), never shown, because they can still change. Links take you to Leave and Shift swaps.

**My availability**: declare a weekly time you *cannot work* (the roster will refuse a shift covering it, and so will a swap) or would *rather work* (a wish the planner can see). Declaring nothing tells the planner nothing; it does not mean you are free. The demo agent never works Sundays and would rather finish early on Fridays; the demo part-timers cannot work Thursday or Friday, and the demo roster respects it.

## Phase 3: Teams and leave rules (LV-04)

**Teams.** On *Employees*, each person has a **Manager** (a lead, planner or admin who has a login). A lead sees and decides leave, swaps and availability only for their own team: sign in as `lead` and you see the demo Support team's requests, nobody else's. Planners and admins decide for everybody. In the demo data the demo lead leads the whole Support team.

**Leave rules** (as `admin`): *Leave > Rules*.
- **Blackout periods**: days when leave that can wait cannot be asked for. Add one, then ask for leave inside it as `agent`: it is refused and names the period. Sick and family leave are never refused.
- **Away at once**: the most people who may be on approved leave the same day. Set it to 1, approve one request as `lead`, then try to approve another for the same day: refused with the day and the limit.
Everyone who takes leave sees the coming blackouts and the limit on their *Leave* page, so a refusal is never a surprise.

## Phase 3.5: Notifications

The **bell** in the top bar (every role). Try: as `agent` ask for leave; as `lead` the bell shows "Leave is waiting for your decision"; approve it; as `agent` the bell shows "Your ... leave request for ... was approved." Publishing a roster tells everyone on it; a swap being taken tells the poster (not by whom) and asks the lead. Messages never name another person or give a reason. Email comes later behind the same call.

## Phase 3.5: Users and passwords

As `admin`, **Admin > Users**.
- **Add a user**: username, name, role and a temporary password. The person signs in with it and is made to choose their own before anything else opens.
- **Change a role**, **switch an account off or on**, **unlock** a locked account, give a **new temporary password**. You cannot change your own role or switch yourself off. A role that comes from the identity provider's groups is shown as fixed.
- **Link a login to an employee**: the account then sees that employee's schedule, leave and swaps. One login, one employee. Everyone can change their own password from the top bar (*Password*).

## Phase 3.5: Employee import and ACD logins

As `planner` or `admin`, **Employees > Import employees**. Pick a CSV or Excel file (needed: *Employee No* and *Name*; the screen lists the optional columns), press **Check the file**: it tells you how many would be added, updated or are already up to date, names any rows that would be skipped and why ("2 with a contract that is not permanent or seasonal"), and lists columns it will ignore. Nothing has changed yet. Press **Import these** to do it. Run the same file again and everyone is "already up to date". A blank cell never erases anything. Hours left blank are shown as **Default**.

Below the import, **ACD logins nobody owns yet** lists logins found on imported call data. Choose the person and press *Tie*; one person can have several logins.

## Phase 3.5: Customers and contracts

**Operate > Contracts.** As `admin`: add a customer, then a contract that holds queues to a promise ("80% in 20 s"). Saving it writes that target onto the queues, so the staffing numbers follow the contract. Everyone who reads it (planner, lead, executive, customer operations) sees, per contract, the **promise**, the service level **measured** over the last 28 days of calls, how **this week** looks against the forecast, and whether the contract is **at risk** with the reasons in words. A missing figure (no calls, no forecast) is shown as missing, never as zero. In the demo data *Claims line* (the Billing queue, short of people all week) is at risk; *Member support* is not.

## Phase 4: Compliance rules

**Admin > Configure > Rules.** As `admin`: see the rules in force (built-in 11 h rest, 6 days in a row, no weekly cap), choose a start day and change them. Loosening below the statutory minimum saves but warns. Then, as `planner`, try to roster someone against the new rule on a day after it starts: the roster refuses with the rule's number in the message. Days before the start day are unaffected.

**Operate > Roster > Auto-schedule** (planner or admin, week not published). Click it: a preview says how many shifts it would add, the half-hours short before and after, and lists them. Nothing is written yet. "Apply these shifts" puts each one in through the normal roster checks; the roster and the planner heatmap update at once. Existing shifts are never changed, and running it again adds nothing. Try it as `lead`: the button is not there and the API refuses.

**Operate > Recommendations** (planner or admin). With a queue and week chosen, the screen shows the half-hours short and a ranked list of single fixes, each a sentence ("Add Pat to D1 on Mon 25 May: closes 17 half-hours short"). Apply one: the roster takes the shift through the normal checks, and the gap and the list recalculate at once. Applying a suggestion twice, or one that is no longer on the list, is refused.

**People > Overtime.** As `planner`: ask for two hours of overtime for somebody on a future day; the roster rules still hold (it is refused over leave, on top of a shift, or without the rest between days), and the cost shows in rands, worked out at the rates in Configure > Rules. As `admin`: on the **Pay** tab put a salary on file (it is never shown again), then approve the request: the price is kept as approved. As `lead`: you can ask for your own team and cancel, but see no rands. As `agent`: there is no overtime screen; you are told the day and outcome in the bell.

## Not built yet (so you are not looking for it)

Per-team leave limits, standby and overtime reconciliation, scheduled reports, intraday, adherence, ITSM and Azure AD
integration. The menu lists some of these as placeholders.

## Loading the demo data

Everything below needs data. `seed_demo_data` fills an empty development database with an
invented contact centre (no real data anywhere). In order:

1. `just dev`, then in the Aspire dashboard (http://localhost:15888) press **Start** on the
   `seed-demo-data` resource. It runs once and refuses to run twice or outside development.
   (Or: `uv run python manage.py seed_demo_data` in `api/`, with the database settings set.)
2. It takes about 30 seconds and prints each step.

### What you get, and the real-life story each part tells

| Data | Real-life situation it shows |
|---|---|
| **Demo Support**: 12 weeks of calls, 40 staff | The everyday queue. Morning and afternoon peaks, a busy Monday and a quiet Friday, thin weekends. |
| **Demo Billing**: 16 staff, weekdays 08:00-17:00 | Month-end pressure. It is **short all week**: the case for seasonal help (see Capacity). |
| **Demo Night Desk**: 8 staff, 18:00-06:00 | Overnight shifts that run past midnight, with the rest rules between them. |
| Public holidays in the history | Volume dips on holidays; the forecast does not treat them as normal days. |
| One **outage day** (about double the calls, many dropped) | A bad day inside the history. Look at Accuracy: the forecast cannot predict it. |
| One day with **no rows** (the recorder was down) | "No data" is not the same as "no calls". The forecast skips it rather than learning zero. |
| Two events: month-end billing run (+30%), SMS campaign (+20%) | Known reasons for demand to change; forecasts after them include the lift. |
| Forecasts for 4 weeks, published | The demand every roster is measured against. |
| **This week and next** rostered and published | Real rosters with contract hours, rest rules and part-timers. |
| **Next Monday** deliberately short, **next Thursday** over-staffed | Open the Roster and Dashboard: red on Monday morning, blue on Thursday. |
| The week after: a **draft**; the fourth week: **not started** | The planner's work in progress, and what is still to do. |
| 4 part-timers, 6 seasonal staff (contract ends in 75 days), 2 who cover two queues | Contract types, seasonal end dates, and why one person cannot be on two queues the same day. |
| Leave: approved, waiting (two), rejected, cancelled, already taken | Every state. The approved one is already **off the roster**; the waiting one over the short Monday shows a real coverage cost in the impact panel. |
| Service desk: 270 tickets in two pools, some overdue, some closed | Backlog and workload by effort. |
| `agent` login | The demo agent is on the Support roster and can ask for leave. |

Staff names are made from word lists and numbered `DEMO-nnn`. The numbers are repeatable: the
generator is seeded, so two fresh databases look the same.

## Known gaps in the demo

- Accuracy figures come from invented data, so they say nothing about the real queues.
- Billing's shortfall is a result of the data (14 people, month-end load), not a bug; use it to
  demonstrate Capacity and What-if.
- The Data import screen is empty: the history was written directly, not imported from a file.
  Import your own workbook there to show that screen.
