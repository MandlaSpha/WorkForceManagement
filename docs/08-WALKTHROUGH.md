# Walkthrough: what each phase does, and how to see it

Plain-language tour of what is built, in the order it was built. Each section says who uses it,
where to click, what you should see, and the rule behind it. Screens are in the left menu.
Everything here is synthetic or your own imported data; nothing comes from `Files/`.

**Sign in** at the web address shown in the Aspire dashboard (http://localhost:15888). The demo
logins (made by `seed_demo`) are `planner`, `lead`, `agent`, `admin`, `executive`, `customerops`,
all with the demo password. Sign in as different roles to see how the menu and the data change.

**Two teams to try swaps and approvals with.** `lead` (Lee) leads `agent`, `agent2`, `agent3`, `agent4`, `agent5`; `lead2` (Lou) leads `agent6` to `agent10`. All work the Support queue, so any agent can take a swap another posts. Post a swap as `agent2`, take it as `agent3` (Shift swaps > Open requests), then sign in as `lead` and decide it under Approvals; `lead` also sees what the team has posted and nobody has taken. `lead2` sees only their own team. The planner and admin see and decide for both. Leave works the same way: a request from `agent7` reaches `lead2`, not `lead`.

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
4. **Day / Week / Month.** The switch above the chart shows the forecast one day, a Monday-to-Sunday
   week (a daily-totals chart, a table of calls, handling time, people at the peak and agent-hours,
   and a day-by-half-hour grid where a darker cell needs more people) or a calendar month (calls and
   people at the peak per day, the busiest and quietest days marked, and any events that cover a
   day). Click a day anywhere to open it in the Day view. Every view says which version it rests on
   and whether that is live or only a draft, and a day with no forecast says "No forecast" with the
   reason; it is never shown as zero. Public holidays are not recorded yet, so none are marked.
5. **Discard and Archive** (planner or admin, in the Versions table). *Discard* deletes a draft;
   *Archive* withdraws the live forecast so the queue has none (the roster, capacity and dashboard
   then show no forecast for it rather than old numbers) and keeps it as history you can still open.
   Both ask for a reason, which goes into the audit trail.

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
2. **Take** (`lead` is the demo colleague): *Open requests* shows "A colleague on Service Desk wants to swap away D1, Mon 25 May 09:00-17:30", with no name, and only requests where at least one of your own shifts would work (rest, hours, leave, availability, one shift a day). *Take it...* lists exactly those shifts of yours; pick the one you offer in return.
3. **Approve** (`planner`, `admin` or the lead of the team): *Approvals*. Approving exchanges the two shifts on the roster (check the Roster page). Nobody approves a swap they are part of, so the demo lead's swap goes to a planner.

The two people see each other's names once it is matched. With the demo data there are two open requests the demo agent can take, one matched and waiting for approval, and one approved.

## Phase 3: The agent's own pages and availability (SCH-08, ESS-01)

Sign in as `agent`: you land on **My schedule**: the whole month as a Monday-to-Sunday calendar with your published shifts and leave (use the arrows to move between months, *List* for a plain list). Shifts in a week the planner has not published are only counted ("Your planner has pencilled in 2 more shifts for you, but that roster is not final yet"), never shown, because they can still change. Links take you to Leave and Shift swaps.

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

## Phase 8: All seven sheets of the call report (DAT-01)

On **Data import** the report now reads every sheet of the ACD workbook, not only the call list. After the usual "Reconciles" box, the **Sheets in the file** table shows, for each sheet, whether it was read, how many rows were read, how many were kept and any warnings. A sheet the workbook does not contain, or a row that belongs to a call that is not in this file, is a warning, not an error, and the calls import regardless. From the detail sheets only logins, counts, durations, menu labels and the ITSM incident number in a remark are kept; names, phone numbers and free-text remarks are never stored. The figures on the dashboard do not change.

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

**People > Shrinkage.** As `planner`: pick a month. Each team shows the share of its contracted hours spent on approved leave, next to the shrinkage the queues are planned with. Unplanned absence is not measured (there is no attendance feed yet) and the screen says so. As `lead`: only your own team. Agents have no such screen.

**Insight > Peaks & troughs.** Pick a queue and a range with the buttons at the top: Last 7 days, Last 30 days (the default), Last 90 days, or Custom for two dates. The heading carries one plain sentence from the data, for example that Mondays carry the most calls and the busiest half-hour is 10:30. Under it are tiles for the busiest day (highlighted), quietest day, busiest half-hour, the peak-to-trough ratio (busiest half-hour average divided by the quietest open one, shown only when both exist) and days measured. A bar chart shows calls each day with the busiest and quietest days named; a day with no data is an empty slot, never a zero. A second chart shows the average calls in each of the 48 half-hours, with the busiest window and the quietest open half-hours in different colours and closed half-hours left blank. A weekday by half-hour grid shows the pattern of the week, darker meaning busier, with a legend; every cell has a text label for screen readers. Ranked cards list the busiest and quietest days, half-hours and single busiest half-hours with a thin bar and a number; these are call volumes, not people. With no calls in the range you get a plain message instead of charts. On a phone the charts scroll sideways inside their card.

**People > Overtime: worked time, standby and the month.** As `planner`, on an approved request whose day has passed, type the minutes really worked (try more than was approved: the extra is shown and not paid). On the **Standby** tab put someone on standby and, once the day has come, record a call-out. The **Month** tab adds overtime, standby allowances and call-outs and shows what is left of the budget; as `admin` set the standby allowance and the month's budget there. As `lead` you see the standby rota and the worked minutes, never a rand figure.

**Insight > Analytics and Reports.** Analytics shows service, workload and planning figures for a range, each labelled Measured, Modelled or Needs data. Reports lets you schedule an emailed pack (scorecard, or peaks for a queue) daily, weekly or monthly. As `admin` first allow an email domain under Reports; recipients must be on it. In development the emails are written to the API console.

**Operate > Intraday.** Pick a queue and a day. It shows calls and people half-hour by half-hour, how the day is running against the forecast (the rest of the day is re-forecast from the calls so far), the service level so far, and the half-hours still to come where cover falls short, with links to overtime and recommendations. Calls are what has been imported, and the screen says up to when.

**Operate > Roster > Breaks and activities.** Under the roster grid, pick a person, a day they work, what (break, lunch, training...), the time and how long. Coverage on the Planner then counts only the people on the phones, so a training session opens a gap you can see. Planner and admin change them (even in a published week); a lead reads them; the agent sees their own on My schedule.

**Operate > Hiring plan.** As `planner`, make a plan: people employed now, how many leave each month, how fast a new hire gets productive, and the people needed for each of 12 to 18 months. It shows how many to hire and when (a hire is made as many months ahead as the ramp is long), the months that are short, and the months where no hire could have helped in time. As `executive` you read the same plan without any rand figure.

**People > Employees > Anonymise (admin).** For someone who has left, the admin can choose Anonymise next to their row. The screen first lists what would be deleted (logins, availability, notifications, pay record, overtime reasons) and what stays without a name (shifts, leave, overtime and standby), and only enables the button once you have typed the employee number. It refuses if the person still has future shifts or leave, has requests waiting, has not left yet, or is the account you are signed in with. It cannot be undone. Above the table a panel lists people who left more than 60 months ago (`WFM_RETENTION_MONTHS`) so you know whom to review; it never acts by itself.

**People > Attendance.** As `planner` or `admin`, load an agent-state CSV (`login,state,from,to`, local times; the layout is a stand-in until the ACD vendor confirms the real feed) in the panel at the top: it says how many rows were stored, skipped as already held or rejected (with line numbers), and which logins are not linked to a person (never guessed). Pick a queue and a day to see each rostered person's adherence (time available, on a call or in wrap-up over scheduled time, breaks and lunch not counted), late starts, early finishes and out-of-adherence minutes. A person with no state data shows "no data", not 0%. A `lead` sees only their own team; as `agent` you see your own planned-versus-actual day under My schedule, and nobody else's.

**People > Skills and People > Wellbeing.** On Skills, pick an employee to see their certifications, languages and security clearances (an expired one says "expired"); as `planner` or `admin` edit the list and save. "Who holds a credential" lists the people who hold, for example, `language: Afrikaans` today. With a queue chosen, planners and admins also set what the queue requires ("at least 2 Afrikaans speakers on every shift") and see the shifts this week that fall short, as "1 of 2". Wellbeing lists people with a prompt (7 or more days in a row, fewer than two days off in a fortnight, overtime on four or more days, rising unplanned leave) as plain facts, not a score; a `lead` sees only their own team and not themselves, a `planner` or `admin` sees everyone, and an `agent` or `executive` cannot open it.
**Operate > Continuity.** Pick a queue (top bar), a day and what happened. As `planner` or `admin`, name a backup team for the queue and add people to it (remove them or delete the team the same way); every change is in the audit trail. The Mobilise part shows the published roster for that day, how many people the event takes away ("A site fails" removes everyone who can only work in the office; "An outbreak" removes the share you type, whatever their work mode), how many the backups win back and what is still short. Each backup person shows the reason they can or cannot cover: free, rostered on another queue (can cover, but leaves a gap there), on approved leave, unavailable most of the day, or office-only when a site has failed. A `lead` sees the same names read-only; an `executive` sees the numbers and no names.

**On a phone.** Sign in as `agent` on a phone (or a 390px-wide browser window): My schedule opens on the list of days, My availability, Leave and Shift swaps fit the screen with nothing scrolling sideways, the menu button opens the navigation as a drawer that Escape or choosing a page closes, and the account menu stays inside the screen.

**People > Quality.** As `planner` or `admin`, load the quality tool's export (`.csv` or `.xlsx`: `login`, `date`, `score`, and optionally `kind`, `ref`, `csat`, `coaching_due`; a stand-in layout until the tool is named). It says how many results were added, corrected or already held, lists rejected rows by line number and reason, names logins not linked to a person, and names (never stores) any extra column such as comments. The table lists each person's average and latest score, CSAT and coaching due, in employee-number order: there is no ranking and no team average. A `lead` sees only their own team, an `agent` sees only their own results under "My results", and `executive` and customer operations cannot open it.

**Operate > Service desk > Service metrics.** Pick a month to see, per resource pool and in total, tickets closed, mean time to resolve, first-contact resolution, CSAT, NPS and the open backlog with its oldest age, with the people the pool needs beside them. The survey columns (`fcr`, `csat`, `nps`) come in with the work-item file; with no answers a figure shows a dash, not zero. Cost per ticket appears for `planner` and `admin` only (it uses the same pay-based price as Utilisation & cost); customer operations see the rest without any rand figure.

**Operate > Intraday > What can I do?** (planner and admin). Next to each short half-hour: up to five people who could be asked for overtime (skilled on the queue, not working that day, not on leave, within the rest and hours rules, lightest week first), each with an Ask for overtime link that opens the Overtime page with the form already filled in (person, day, the whole short stretch), and, where the person in the short half-hour is in a break or lunch, a one-click Move to a time that keeps the phones covered. A lead sees the alerts but no button.

**Insight > Reports > Investment-board KPI pack.** Schedule it as `executive`, `planner` or `admin` (or customer operations): an emailed workbook with Headline (scorecard figures and where each comes from), By queue, Capacity (the latest hiring plan; absent for customer operations) and Notes. It never holds a rand figure.

**Insight > Utilisation & cost.** Pick a month. As `planner`, `admin` or `lead` you see worked against billable hours for each team, customer and contract, with the target and the gap (short of target is spelled out, not just coloured), and a People table in employee-number order with no ranking. Everything is modelled from the published roster, which the page says; a target marked "assumed" is the 75% default until an admin sets the contract's own (as `admin`, choose the contract below the table, enter a target and optionally a monthly revenue). As `planner` or `admin` a Cost section follows: ordinary and overtime cost for each contract against its revenue, cost per engineer (someone with no salary on file shows "No salary on file", never R0.00) and cost per ticket for each service-desk pool. As `executive` or `customer_ops` you see the three group tables and no named person or rand figure; `agent` has no link.

**Operate > Workload balance.** As `planner`, `admin` or `lead`, pick a day to see each queue's load (what the forecast needs over what the roster puts on the phones): Stretched above 110%, Slack below 80%, "No forecast" where nothing is known. Below it, suggested moves name a person on a slack queue with the skill for a stretched one. They are suggestions only; there is no button that moves anyone, and a lead is offered only their own team.

## Not built yet (so you are not looking for it)

Per-team leave limits, scheduled reports, intraday, adherence, ITSM and Azure AD
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
| **Service Desk**: 12 weeks of calls, 40 staff | The everyday queue. Morning and afternoon peaks, a busy Monday and a quiet Friday, thin weekends. |
| **Billing Support**: 16 staff, weekdays 08:00-17:00 | Month-end pressure. It is **short all week**: the case for seasonal help (see Capacity). |
| **Night Desk**: 8 staff, 18:00-06:00 | Overnight shifts that run past midnight, with the rest rules between them. |
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

**Admin > Audit log.** Only `admin` sees it. The top shows whether the tamper-evident hash chain is intact (a red alert lists the problems if not). Below, filter by who (part of a username, or `system` for background jobs), what (the action), entity, outcome and a date range in South African time, then Search; the list is newest first, 50 a page, with the old and new value of each changed field. "Download these as CSV" takes the filtered list as a file that spreadsheets cannot run as a formula. Nothing on the screen can edit or delete an event. Searching and downloading are themselves recorded as "Audit log searched or viewed" and "Audit log exported", with the kind of filter used but never what you saw: search for those actions to see it. Sign in as `planner` to confirm the menu entry is gone and the address is refused.

## Insight: Call detail (DAT-01)

**Insight > Call detail** adds up the six detail sheets of the call report for the month you pick (the months that have call data). Four parts, each saying what it rests on. **Ring-no-answer by agent** (planner, admin and team lead) lists every ACD login with offers, answered, ring-no-answer count and rate and average ring seconds, mapped to the employee where the login is known; it is in employee-number order, never ranked, with no team average beside a person, and a team lead sees only their own team. **IVR menu and drop-off** shows, per queue, how many calls went through each menu step, how many ended inside the IVR and how many were abandoned after it. **Transfers, holds and mutes** gives counts and average durations per queue and per day. **Incident links** (planner and admin only) lists the ITSM incident numbers found in dispositions, per queue. An executive sees the queue figures only. When a sheet was not in the import the part says **No data**, never zero. Agents and customer operations are refused. The same logins appear in the subject-access export and are replaced by a random token when an employee is anonymised (the preview shows the counts).


## Look and feel: the dashboard hero and charts

The Dashboard opens with the date, a greeting by the time of day in South Africa ("Good morning, Pat", first word of your display name, shown on screen only) and, for planners, one sentence about the week ("3 queues are short this week; Billing Support is the worst") with a bar of covered against short half-hours. The marker shows how far through the week today is, and only appears when the week you are looking at contains today. Queues with no forecast are named under the bar, not counted in it. The big tile is the coverage gap with a small line of the gap on each day. Hover or tab to a bar to see its value. Numbers count up and lines draw in over half a second, unless your system is set to reduce motion, in which case everything appears at once. Service figures have no change arrows, because the system holds one month at a time.
## Sidebar foot and the week calendar

At the bottom of the sidebar you now find **Settings** (click to open Configure, Users and Audit log, for roles that may use them), a thin **coverage bar** for this week (planners, leads and admins only; it appears once a forecast exists), and your **name card**. Click the `...` on the card for Change password and Sign out; on a phone, open the menu button first. On **My work > My schedule**, choose **Week** to see your published shifts on a Monday to Sunday time grid, with a line for the current time today, a tooltip with times and paid hours when you hover or tab to a shift, and a **Week at a glance** card with total paid hours, number of shifts, time by activity and your next three shifts. **List** is the same agenda as before; on a phone only the list is offered.

## Configure, redesigned

Admin > Configure now reads like a settings screen. The tabs (Shifts, Queues, Workforce, Rules) are a pill control at the top right. Each setting is a row in a rounded card: the name and one line of explanation on the left, the field on the right (stacked on a phone). Cards that save as a whole end in a bar that says "All changes saved" or "You have unsaved changes", with Discard and the save button. Shifts are a table: search by code or time, click a column heading to sort, 20 rows at a time with "Show more", and the bin icon asks "Delete D1?" before deleting. A shift people are rostered on cannot be deleted, and the screen says why. Behind the scenes, the development database no longer fills with test shifts and people: the clean-up after each browser-test run now removes them too (see tech spec section 13).
