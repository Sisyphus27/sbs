# 0004 — Bodyweight lifts store added weight; working weight derived at a single seam

For bodyweight lifts (`Lift.bodyweight_pct > 0` — Dips, Chin-ups, High Crunch), the stored
`weight` / `start` / `history.weight` fields hold the **added weight** (belt, dumbbell, vest),
not the working weight. The working weight — `added + bodyweight × bodyweight_pct` — is derived
at a single seam `working_weight()` and fed to every engine computation (est1RM, tonnage, T2
reset). The obvious alternative, storing the working weight with bodyweight baked in, was
rejected because it would corrupt historical tonnage/est1RM whenever the user's bodyweight
changes; storing added keeps history stable against bodyweight drift.

## Considered Options

- **Store working weight (bodyweight baked in)**: engine pure functions untouched, but every
  history row bakes in the then-current bodyweight — historical tonnage drifts the moment the
  user's weight changes, and there is no way back without a per-week bodyweight log.
- **Store added + single `working_weight()` seam (chosen)**: history stays stable against
  bodyweight change; the cost is routing every weight-reading call site through the seam.
  The exhaustive call-site inventory is enforced by behavior-guard tests that fail if any raw
  `state.weight` / `history.weight` reaches `estimate_1rm` / tonnage / `t2_next`.

## Consequences

- `estimate_1rm`, tonnage, and `t2_next`'s reset term must receive working weight, never raw
  added weight. The seam is the only allowed translation point; guard tests assert this.
- Editing `bodyweight_pct` retroactively shifts history-derived est1RM (the bodyweight term of
  past sets is recomputed with the new fraction). Accepted: `bodyweight_pct` is a near-constant
  modeling parameter per lift, not a fluctuating input like bodyweight itself, so propagating a
  refinement backward is correct rather than corrupting.
- Bodyweight is held as a single global static value; per-week bodyweight tracking is explicitly
  out of scope. Historical added weights are unaffected, but the bodyweight term applied to them
  always uses the current global value — a known, accepted imprecision.
