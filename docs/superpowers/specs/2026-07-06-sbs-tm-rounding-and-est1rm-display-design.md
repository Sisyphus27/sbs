# SBS TM-Rounding Fix + est1RM Display Rounding — Design

- **Date:** 2026-07-06
- **Status:** Pending user review
- **Trigger:** User finished week 1, saw Day-1 Squat drop to 90 kg after logging 8 reps (target 10) on the last set, and asked whether the SBS calculation is accurate. Also requested est1RM be shown to 2 decimals.

## Context

The SBS main/auxiliary tier auto-adjusts its Training Max (TM) from the AMRAP (last-set) performance each week. The working weight is `round(TM × intensity, rounding)`. The user suspected the progression math was wrong and asked to verify it against the original SBS RTF template (`SBS Programs/Original Templates/SBS Strength Program reps to failure.xlsx`) and the user's filled copy (`SBS RTF filled GZCLP.xlsx`).

## Verification Verdict (research finding)

The progression **delta table is exact** vs the original SBS RTF template. Cross-checked against `Quick Setup` row 6 (main-lift squat) and the `4x` sheet's week-2 TM formula `I4`:

| diff (actual − repout) | xlsx Quick Setup | `engine/_sbs_delta` |
|---|---|---|
| ≤ −2 | −0.05 | −0.05 ✓ |
| −1   | −0.02 | −0.02 ✓ |
|  0   |  0.00 |  0.00 ✓ |
| +1 / +2 / +3 / +4 / +5+ | +0.005 / +0.01 / +0.015 / +0.02 / +0.03 | identical ✓ |

The xlsx TM recurrence is `new_TM = old_TM × (1 + delta)` and the working weight is `MROUND(TM × intensity, rounding)`. Both match the engine's intent.

**User's 90 kg is the correct SBS result.** Week-1 Squat = 95 kg × 8 reps, repout 10 → diff −2 → −5% → TM `135 × 0.95 = 128.25` → week-2 weight `round(128.25 × 0.7, 2.5) = 90`. Missing the rep target by 2 carries a −5 % TM penalty per the SBS rulebook.

## The Bug: TM is rounded to the gym increment every week

`engine/progression.py` `sbs_next` rounds the **TM** to the 2.5 kg quantum each step:

```python
return round_weight(tm * (1 + _sbs_delta(actual - repout)), quantum)
```

The SBS xlsx **does not round the TM** — it keeps TM full-precision and rounds only the displayed working weight. Re-rounding the TM every week discards sub-quantum weekly deltas before they can accumulate, which **stalls upward progression entirely** for any lift whose TM is below ~250 kg.

Simulation, +0.5 %/week (beat target by 1 — the most common outcome), weight rounded to 2.5 throughout:

| week | engine TM | SBS TM | engine weight | SBS weight |
|---|---|---|---|---|
| 1  | 135.0 | 135.0 | 95 | 95 |
| 6  | 135.0 | 137.7 | 95 | 97.5 |
| 21 | 135.0 | 149.9 | 95 | 105 |

The engine's weight is frozen at 95 kg; the SBS-faithful weight climbs in legal 2.5 kg steps to 105 kg. The −5 % case (the user's week 1) moves only because −5 % is large enough to cross a 2.5 boundary by accident; small upward deltas never move.

### Why the gym's 2.5 kg minimum does not fix this

The user pointed out the gym's minimum plate increment is 2.5 kg. That constraint applies to the weight you **load**, not to the TM (which is internal bookkeeping and is never loaded). The `rounding` setting already snaps every loaded weight to the gym increment. The stall happens because the TM that *feeds* next week's weight is frozen — so even though the loaded weight is always a 2.5 multiple, it never gets to increase.

## `rounding` is already the universal gym-increment parameter

Confirmed: `rounding` is a global setting (default 2.5), editable in the webapp at `/settings` (`templates/settings.html`), and applied to every loaded weight:
- SBS working weight — `routes/plan.py:26`, `services/preview.py:13`
- T2/T3 weights and T2 reset — via `quantum=settings["rounding"]` in `services/tier.py:18` and the progression functions

So "make the gym increment a general parameter" is already satisfied. It is **out of scope** to rename it; an optional future polish is relabeling the UI field from `rounding (kg)` to something like `最小加重 (kg)`. This design leaves the name alone.

## Goals

1. Make SBS TM accumulation faithful to the SBS RTF xlsx (fix the progression stall).
2. Show est1RM to 2 decimals on every surface.
3. Correct the existing rounded-wrong TMs already stored in `sbs.db`.

## Non-Goals

- Renaming `rounding` or restructuring settings.
- Changing the delta table, the e1RM formulas, or any T2/T3 logic.
- Altering history rows (immutable).
- Introducing weekly intensity waves (the program intentionally uses fixed per-lift intensity).

## Design

### Change 1 — `sbs_next` keeps TM full-precision

`engine/progression.py`:

```python
def sbs_next(tm: float, repout: int, actual, quantum: float = 2.5) -> float:
    """SBS main/aux: next TM from rep-out performance. actual=None -> unchanged."""
    if actual is None:
        return tm
    return round_weight(tm * (1 + _sbs_delta(actual - repout)), quantum)
```

becomes

```python
def sbs_next(tm: float, repout: int, actual) -> float:
    """SBS main/aux: next TM from rep-out performance. actual=None -> unchanged.

    TM is kept full-precision to match the SBS RTF xlsx (which rounds only the
    working weight, not the TM). Rounding the TM here stalls upward progression
    because sub-quantum weekly deltas are discarded before they accumulate.
    The working weight is rounded to the gym increment in week_plan / the webapp.
    """
    if actual is None:
        return tm
    return tm * (1 + _sbs_delta(actual - repout))
```

The `quantum` parameter is removed. Sole non-test caller is `program.py:48`:

```python
state.tm = sbs_next(state.tm, lift.repout, actual_reps, quantum=profile.rounding)
```

→ drop the `quantum=...` argument. `round_weight` is still used for the working weight (`week_plan`, `routes/plan.py`) — unchanged.

### Change 2 — Update `sbs_next` unit tests

`tests/test_progression.py`. Expected TMs become the raw (unrounded) values:

| test | actual | delta | old expected | new expected |
|---|---|---|---|---|
| `test_sbs_hit_keeps_tm` | 8 | 0 % | 100 | 100 (same) |
| `test_sbs_beat_adds_pct` | 11 | +1.5 % | 102.5 | **101.5** |
| `test_sbs_miss_drops_pct` | 6 | −5 % | 95 | 95 (same) |
| `test_sbs_beat_5_plus_caps_at_3pct` | 14 | +3 % | 102.5 | **103.0** |
| `test_sbs_no_log_keeps_tm` | None | — | 100 | 100 (same) |
| `test_sbs_miss_by_1_drops_2pct` | 7 | −2 % | 97.5 | **98.0** |

`round_weight` tests are untouched.

### Change 3 — est1RM to 2 decimals on every display surface

| file:line | before | after |
|---|---|---|
| `webapp/templates/plan.html:18` | `{{ it.est1rm if it.est1rm is not none else '—' }}` | `{{ "%.2f"\|format(it.est1rm) if it.est1rm is not none else '—' }}` |
| `webapp/templates/week_export.html:32` | `{{ it.est1rm if ... }}` | `"%.2f"\|format(...)` |
| `webapp/templates/week_export.html:35` | `"%.1f"\|format(it.live)` | `"%.2f"\|format(it.live)` |
| `webapp/templates/tier_preview.html:9` | `{{ preview.est1rm if ... }}` | `"%.2f"\|format(...)` |
| `webapp/routes/plan.py:79` | `f'≈{p["est1rm"]:.1f} {delta_html}'` | `:.2f` |
| `sbs_cli/view/terminal.py:13` | `{it.est1rm:.1f}` | `:.2f` |
| `sbs_cli/view/terminal.py:30` | `{ls.est1rm:.1f}` | `:.2f` |
| `sbs_cli/view/templates/week.html.j2:26` | `"%.1f"\|format(it.est1rm)` | `"%.2f"\|format(...)` |

est1RM stays full-precision in storage (`lift_state.est1rm` REAL); rounding is display-only so no precision is lost.

### Change 4 — TM display rounding in CLI `show`

`sbs_cli/view/terminal.py:30`: `f"... TM {ls.tm} ..."` → `f"... TM {ls.tm:.1f} ..."`. TM is now a full-precision float internally; round it to 1 decimal only for the text view. (TM is never loaded, so it is not rounded to the gym increment.)

### Change 5 — One-time DB recompute of stored sbs TMs

Add a sibling to `recompute_state` in `program.py`:

```python
def recompute_sbs_tm(lift: Lift, history: List[SetEntry]) -> float:
    """Replay an sbs lift's TM from lift.max over its history (raw, no rounding).
    History rows are immutable facts; only their reps drive the replay."""
    tm = lift.max
    for h in sorted(history, key=lambda x: x.week):
        tm = sbs_next(tm, lift.repout, h.reps)
    return tm
```

A one-shot migration script `migrate_sbs_tm.py` (mirrors the existing `migrate_recompute.py` pattern) iterates every sbs lift in `sbs.db`, loads its history via `repo`, computes `recompute_sbs_tm`, and writes the corrected `tm` back to `lift_state`. est1RM is untouched (it is derived from history and was never affected by the TM-rounding bug). Backs up `sbs.db` first (existing `backup.py` convention).

Example corrections after running (Squat week-1 history = 95 kg × 8, repout 10):
- Squat: 127.5 → **128.25**
- Deadlift, OHP, Front Squat, etc.: each replayed from its `max`; any whose TM was rounded under the old bug is corrected.

The migration is **idempotent**: replaying the same history always yields the same raw TM.

## Test Plan

- Unit (`tests/test_progression.py`): the 3 sbs_next expectations above flip to raw values; all other tests unchanged.
- Unit (`tests/test_program.py`): add `test_recompute_sbs_tm_replays_from_max` — seed a 2-week history, assert raw replayed TM (e.g. max 100, beat-by-3 then hit → `100 × 1.015 × 1.0 = 101.5`).
- Migration test (`tests/test_migrate_sbs_tm.py`, new): seed `sbs.db` with a rounded TM + history, run the migration, assert TM equals `recompute_sbs_tm(...)` and est1RM unchanged. Backs up DB.
- Display: existing tests (`test_terminal.py:18`, `test_html.py:20`, `test_routes_plan.py:56`) check presence of the markers and still pass; optionally add an assertion that est1RM renders with 2 decimals.
- Regression check: re-run the 21-week +0.5 %/week simulation in a test to prove the engine's weight now advances (95 → 97.5 → … → 105), locking the stall fix in.
- Run full suite: `conda run -n sbs python -m pytest tests/ -v`.

## Risks / Edge Cases

- **Stored TM becomes a long float** (e.g. `128.8875` after several weeks). Mitigated by Change 4 (display rounding). The number is never loaded.
- **Migration touches the live DB.** Mitigated by backing up `sbs.db` first; idempotent replay; only `tm` column written.
- **Calling sites passing `quantum=`.** Only `program.py:48`; grep confirms no others outside tests.
- **Tests encoding the bug.** Three tests assert rounded TMs and must be updated as part of the same change — they are not regressions, they are the bug captured.

## Out of Scope

- Renaming `rounding` / settings UI relabel (future polish only).
- Weekly intensity progression (fixed per-lift intensity is intentional).
- T2/T3 / e1RM formula changes.
- Re-validating against the Hypertrophy or RIR template variants (only RTF was requested).
