# 0006 — Presentation-layer-only UI redesign: server-rendered Jinja + HTMX, single accent, sidebar IA

The webapp's non-plan pages (动作管理, 全局参数, 进度表) were chaotic: styles were a single
inline `<style>` block plus scattered per-template inline styles, the nav exposed only 3 of 5
routes (进度表 and 重测 were orphaned), and the lift list embedded a ~10-input edit form per
row that wrapped and misaligned.

We decided to **rebuild the presentation layer only** — every template plus a new
`static/app.css` — and leave the backend (`routes/`, `repo.py`, `services/`, engine) untouched.
The information architecture moves to a **left sidebar** with three groups (训练 / 动作 / 配置),
and the lift list becomes **read-only rows that expand in place** to edit.

## Why presentation-layer-only

The backend is clean and well-tested; the chaos was purely visual and structural. Touching the
engine or routes would risk regressions for zero UX gain. The only backend additions are two
read-only GET endpoints (`/lifts/<id>/row`, `/lifts/<id>/edit`) to serve HTMX partials, plus a
context processor that injects the legal-combination map (single-sourcing `is_legal_combo` to
the client) and the pending-reseed count.

## Considered Options

- **Patch styles in place**: smallest diff, but leaves the orphan-route IA problem and the
  per-row edit-form density unsolved — a patch, not a fix. Rejected.
- **Adopt a component framework / SPA (React, Vue)**: richer interactions, but adds a build
  step and JS tooling the project deliberately avoids; the owner is an algorithms researcher,
  not a web developer, and the app is a personal tool. Rejected.
- **Server-rendered Jinja + HTMX, hand-rolled CSS (chosen)**: keeps zero-build, keeps HTMX's
  partial-refresh model already in use, and a single design-token stylesheet gives the
  consistency the inline styles lacked. Fits the "personal tool, algorithmic aesthetic" goal.

## Key decisions (from the grilling session)

- **Single accent** (deep blue) reserved for primary actions, current-nav, and focus; NOT for
  destructive (red) or tonnage-delta (green/red) colours, and no per-mode colour-coding (only
  `sbs` is accent-highlighted).
- **Expand-in-place editing**: list rows are read-only; clicking 编辑 expands that row to a form
  via HTMX. Validation failure **keeps the edit state** and echoes the erroneous values (never
  discards user input by reverting to read-only). 取消 re-fetches the read-only row.
- **换 mode stays a dedicated page** (it recomputes est1RM and previews TM — a confirmation flow
  that deserves focus, not an inline cell).
- **Confirmation discipline**: destructive + one-click actions (lift delete, schedule
  reset-to-default) get a native confirm; actions that require input or are re-promptable
  (reseed apply/skip) do not.
- **settings ↺-default buttons are per-field independent forms** — resetting one field must not
  submit or discard the main form's unsaved edits.
- **Legal-combination map is server-injected JSON** (from `is_legal_combo`), not a client-side
  hardcoded copy — one source of truth for the ADR 0005 constraint table.
- **Numbers in columns use a monospace font** (alignment); numbers in prose stay in the body
  font. System font stack throughout — no self-hosted web fonts.

## Consequences

- All styles centralise in `webapp/static/app.css` (CSS custom-property tokens); templates keep
  no inline `<style>` except the self-contained offline `week_export.html`, which only syncs
  token *values* to stay offline-capable.
- `week_export.html` remains standalone (no external CSS, no nav) for offline phone viewing.
- Sidebar highlights via `request.blueprint`; 重测 shows a pending-count badge, which requires
  the due-lifts query on every page (context processor) — negligible for a local single-user app.
- Existing `tests/test_routes_*.py` should stay green (template variable names preserved); the
  two new GET partial endpoints need a few render tests.
