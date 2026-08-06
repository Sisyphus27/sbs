# 0010 — Defer UX polish on the live webapp: single-user local tool, current UI is 够用; only the submit double-click correctness bug is in scope

Issue #18 surveyed five UX axes on the redesigned local webapp (ADR 0006): HTMX-ifying the
remaining full-page-refresh flows, adding load/disabled indicators, dark mode, accessibility,
and mobile responsiveness. A `/grilling` session walked the dependency tree and established the
usage context first, which collapsed most of the list.

## Usage context (this is what the decision hangs on)

- **Live webapp runs on `localhost`** — desktop, one user (the developer/athlete). Core actions
  (log last-set reps, *提交并算下周*, edit settings/schedule/reseed) all happen here.
- **`localhost` is unreachable from a phone**, so the live webapp is never opened on mobile.
- **The phone surface is `week_export.html`** (ADR 0007): a self-contained offline static page,
  read-only "plate-loading cheat sheet" for the gym. It already uses cards (not tables),
  `viewport`, `max-width: 680px`, per-day `<details>` with `first_open` auto-opening today, and
  symbol+color tri-state marks.

## Decision: defer all five UX axes

| Axis | Verdict | Reason |
|------|---------|--------|
| HTMX-ify重流 (`plan.submit`, settings/schedule/reseed) | Defer | After *提交并算下周* the entire page content changes (new week's plan), so partial refresh saves almost nothing. The other flows already give `flash` feedback; localhost redirect flicker is millisecond. Cargo-cult, not felt pain. |
| Load/disabled indicators (autosave) | Defer | `save-ok` text fragment already confirms each autosave. Single desktop user, no confusion. |
| Dark mode | Defer | Single-user preference, no beneficiary pressure. `app.css` and `week_export.html` each declare their own `:root` tokens (the export must stay self-contained) — adding dark to both creates a manual sync burden with no payoff, since the live app is never used in the dark. |
| Accessibility (skip-link, `aria-*`, labels) | Defer | Single desktop user, no third-party user benefits. Export tri-state is already symbol+color (`✓`/`◐`), not color-only. |
| Mobile (<900px table overflow) | Defer | The overflow finding is about the live webapp's `.table` (e.g. schedule) — which is desktop-only and never opened on phone. The only phone surface (`week_export.html`) is already mobile-adequate. |

## The one exception: a correctness bug, not UX

`plan.submit` (`webapp/routes/plan.py:50-78`) is **non-idempotent and its button has no disable**.
A double-click fires two POSTs: the second reads the already-bumped `week`, re-saves the
browser-resubmitted form values into the new week, and advances again — **two weeks jumped in
one click, logs misaligned**. That is data corruption, not polish, so it is tracked and fixed
separately as a bug. The fix is **client-side button disable** (the page already depends on
htmx, so JS is guaranteed on); a server-side nonce guard was rejected as YAGNI for a
single-user local tool whose only threat vector is a same-page double-click.

### Correctness amendment

[正确性：周推进非原子 + 服务端无幂等（在 ADR 0009 之上收尾）](https://github.com/Sisyphus27/sbs/issues/29)
later established that the client guard does not cover stale tabs, retries, or concurrent
requests. The rendered absolute program week is therefore also submitted as `expected_week`:
the server conditionally claims that week before either autosaving or advancing and rejects a
stale request with HTTP 409. This supersedes only the server-guard rejection above; the UX
deferrals in this ADR are unchanged.

## Triggers that send us back here

Reopen UX polish only when one of these becomes true (measured/specific, not hunch):

- **A second human user appears** (the tool stops being single-user) — a11y/dark/mobile gain real
  beneficiaries.
- **The live webapp starts being used on a phone** (e.g. exposed over LAN / tailscale) — mobile
  layout and dark mode on the live app start mattering.
- **A specific surface causes repeated, nameable friction** in actual weekly use — then fix that
  surface, not the whole list.

Dark mode specifically becomes cheap the moment it's wanted: a single `@media
(prefers-color-scheme: dark)` block per stylesheet, no token refactor — but only then.

## Considered Options

- **Polish all five now (defensive)**: satisfies a UI-best-practices checklist, but every axis
  lacks a beneficiary at current usage. Adds CSS/template surface to maintain for zero felt
  benefit. Rejected as cargo-cult.
- **Do dark mode only**: still no beneficiary, and pays the dual-token sync cost. Rejected.
- **Polish `week_export.html` further**: already adequate for its read-only gym role; no specific
  gap named. Rejected.
- **Defer all, record triggers, split out the correctness bug (chosen)**: zero UX churn now; an
  objective re-entry condition replaces reliance on discomfort; the one real defect is fixed on
  its own merits.

## Consequences

- No CSS or template changes for UX polish. `app.css` and `week_export.html` stay as-is.
- `plan.submit` keeps the client-side disable for immediate feedback; `expected_week` is the
  server-side correctness boundary for both autosave and advance.
- The trigger list above is the contract: future UX work must cite a real beneficiary or named
  friction, not a checklist.
- If usage stays personal/single-user (the stated redesign goal, ADR 0006), none of these triggers
  is expected to fire — in which case the correct amount of UX polish was zero.
