# 0005 — Progression mode and load model as orthogonal enums, with legal-combination constraints

A lift's training behaviour was previously governed by three overlapping fields: `tier`
(`sbs`/`t2`/`t3`), `progression` (`weight`/`none`), and `bodyweight_pct` (>0 implicitly marked
"is a bodyweight lift"). The overlap made the progression dispatch logic sprawl across
`advance_lift` / `week_plan` / `derive_state` / `_init_lift_state` as ad-hoc if/else, and gave
pure-bodyweight lifts (no added load, no automatic progression) no first-class home.

We split the concept into two orthogonal enums on the lift: **Progression Mode** (`sbs` /
`linear_t2` / `linear_t3` / `none`) decides how next week's weight/reps change; **Load Model**
(`barbell` / `bodyweight` / `pure_bodyweight`) decides how the working weight is composed from
the stored weight. The engine dispatches on `mode` through a single registry
(`PROGRESSION_REGISTRY[mode]`), and routes all load computation through the existing
`working_weight()` seam (ADR 0004).

## Considered Options

- **Keep `tier`, split only the load model**: smallest change, but leaves the progression
  dispatch scattered and the tier/progression overlap intact — a patch, not a unification.
- **Single flat enum** (`sbs`, `t2`, `t3`, `bw_t2`, `bw_t3`, `bw_none`): simple, but duplicates
  t2/t3 per load model and explodes combinatorially as modes grow.
- **Two orthogonal enums + registry (chosen)**: dispatch collapses to one lookup; adding a mode
  is one handler plus one registry line. Cost is a schema migration and updating every dispatch
  call site.

## Legal Combinations

The two axes are orthogonal in principle but constrained in practice — the meaningless
combinations are rejected at lift create/edit:

| load_model \ mode | sbs | linear_t2 | linear_t3 | none |
|---|---|---|---|---|
| `barbell` | ✅ | ✅ | ✅ | ❌ |
| `bodyweight` | ❌ | ✅ | ✅ | ❌ |
| `pure_bodyweight` | ❌ | ❌ | ❌ | ✅ |

- `none` ↔ `pure_bodyweight` are bound one-to-one: a lift with no added load has no weight to
  progress, and any lift with load must follow some progression. `mode=none` is record-only —
  it appends history and recomputes est1RM but never changes weight or target.
- `sbs` is restricted to `barbell`: TM autoregulation by rep-out delta has no clear meaning
  when added load is pinned to 0. Bodyweight main lifts are out of scope until that semantics
  is defined.

## Consequences

- **Load model is immutable.** Switching a lift's load model would reinterpret every stored
  `history.weight` under a different seam (ADR 0004) and silently corrupt all historical
  est1RM. Changing load model therefore means creating a new lift; only `mode` may be switched,
  and only within the same load-model family (history preserved, est1RM recomputed).
- The old `tier` and `progression` columns are dropped (the `lifts` table is rebuilt on
  migration); `lift_state.tier` is renamed to `mode`. `bodyweight_pct` survives as a pure load
  parameter, no longer a mode marker.
- Pure-bodyweight lifts display their working weight as `bodyweight × bodyweight_pct` through
  the same seam as everything else — no view-layer special-casing. `bodyweight_pct` is
  hand-entered at creation (default 1.0 for pull-up/dip; e.g. ~0.64 for push-up).
