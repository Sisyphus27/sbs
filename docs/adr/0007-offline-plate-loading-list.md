# 0007 — Offline phone export as a plate-loading list: single big number, action directives only, zero JS

The offline phone export (`week_export.html`) was a miniature of the desktop plan view: every
field (mode, est1RM, streak, logged state, working-weight total) rendered at equal weight in
small grey text. On the gym floor this is wrong — the page exists to answer one question,
"this lift, how much weight, how many reps?", read in seconds between sets in bright light.

We decided to rebuild it as a **plate-loading list**: each lift card carries exactly one big
number (the loading weight) and one action-directive line (sets × reps, rep-out target); all
state fields are dropped. The page is pure template + inline CSS, **zero JavaScript**.

## Key decisions (from the grilling session)

- **Action directives stay, state is dropped.** est1RM, streak, logged state, live est1RM
  preview, and the bodyweight working-weight total are post-session review data — they do not
  change a plate on the bar, so they are removed from the offline card. (They remain on the
  desktop plan view.)
- **One big number per lift.** Barbell shows the bar weight; a bodyweight lift shows only the
  added weight (`+15 kg`), NOT the parenthesised working-weight total — two side-by-side numbers
  invite mis-loading under sweaty-glance conditions. A pure-bodyweight lift has no big number.
  Weights render at full precision (`95.0`/`57.5`) because the 2.5 kg rounding-quantum grid
  points must stay visible; never trailing-zero-stripped.
- **Progress-driven day location, not a calendar.** Which Day expands by default is derived from
  logged data, because the offline single file has no reliable real-time clock. The
  lowest-numbered non-full Day expands; a *partial* Day (cut short by fatigue or time) is an owed
  debt, marked ◐ and surfaced first so the lifter can find and finish it later — never treated as
  done, never hidden by collapse. Trained Days collapse with a ✓; all Days stay expandable.
- **No dark mode, no sticky day tabs.** The gym is bright, so the investment goes to light-mode
  contrast and large type instead. Day navigation is a plain `<details>/<summary>` collapse
  list — a sticky tab bar costs vertical space on a narrow phone and pure `#anchor` links do not
  open a closed `<details>` without JS, so tabs were cut to keep the page zero-JS.

## Considered Options

- **Sync the desktop card design (patch)**: keeps visual consistency, but the desktop card is a
  data-entry row, not a gym-floor checklist — consistency here preserves the wrong thing.
  Rejected.
- **Dark mode toggle**: marginal benefit in a bright gym, and a real dark theme needs every
  semantic colour re-tuned, not an inversion filter. Rejected as YAGNI.
- **Sticky day tabs + auto-expand**: nicer for jumping to a specific Day, but requires JS to
  open the collapsed `<details>`, breaking the zero-JS / offline-reliable property. Rejected.

## Consequences

- `week_export.html` stays self-contained and offline-capable (ADR 0006), now with zero JS.
- The template computes the day tri-state in Jinja from the same `logged` data `_by_day`
  already supplies — no new fields, no route/Python changes.
- The mode tag footnote keeps the ADR 0006 rule: only `sbs` is accent-highlighted, others neutral.
