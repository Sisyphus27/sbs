# 0004 — Bodyweight lifts store added weight; working weight derived at a single seam

For bodyweight lifts (`Lift.bodyweight_pct > 0` — Dips, Chin-ups, High Crunch), the stored
`weight` / `start` / `history.weight` fields hold the **added weight** (belt, dumbbell, vest),
not the working weight. The working weight — `added + bodyweight × bodyweight_pct` — is derived
at a single seam `working_weight()` and fed to every engine computation (est1RM, tonnage, T2
reset). The obvious alternative, storing the working weight with bodyweight baked in, was
rejected because it would corrupt historical tonnage/est1RM whenever the user's bodyweight
changes. Stable v1 Training Facts therefore pair the added weight with the training session's
bodyweight and the prescription snapshot's bodyweight percentage.

## Considered Options

- **Store working weight (bodyweight baked in)**: engine pure functions untouched, but every
  history row bakes in the then-current bodyweight — historical tonnage drifts the moment the
  user's weight changes, and the original inputs cannot be recovered.
- **Store added + single `working_weight()` seam (chosen)**: history stays stable against
  bodyweight change when its session and prescription facts are persisted; the cost is routing
  every weight-reading call site through the seam.
  The exhaustive call-site inventory is enforced by behavior-guard tests that fail if any raw
  `state.weight` / `history.weight` reaches `estimate_1rm` / tonnage / `t2_next`.

## Consequences

- `estimate_1rm`, tonnage, and `t2_next`'s reset term must receive working weight, never raw
  added weight. The seam is the only allowed translation point; guard tests assert this.
- V1 historical projections use the immutable `training_session.bodyweight_kg` and
  `progression_event.bodyweight_pct`; later profile or prescription edits do not rewrite them.
- Legacy facts missing either historical input remain unavailable rather than falling back to
  the current profile or prescription.
