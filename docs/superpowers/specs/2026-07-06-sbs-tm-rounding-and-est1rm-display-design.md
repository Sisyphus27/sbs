# SBS TM-Rounding Fix + est1RM Display Rounding — Design

- **Date:** 2026-07-06
- **Status:** Revised 2026-07-06 after grilling session (decisions folded in; see "Decisions from grilling")
- **Trigger:** User finished week 1, saw Day-1 Squat drop to 90 kg after logging 8 reps (target 10) on the last set, and asked whether the SBS calculation is accurate. Also requested est1RM be shown to 2 decimals, and that the gym's minimum plate increment be a configurable parameter driving rounding.
- **References:** [ADR 0001 — TM accumulates raw](../../adr/0001-tm-accumulates-raw.md) · [CONTEXT.md — glossary](../../../CONTEXT.md)

## Context

The SBS main/auxiliary tier auto-adjusts its Training Max (TM) from the AMRAP (last-set) performance each week. The working weight is `MROUND(TM × intensity, rounding)`. The user suspected the progression math was wrong and asked to verify it against the original SBS RTF template (`SBS Programs/Original Templates/SBS Strength Program reps to failure.xlsx`) and the user's filled copy (`SBS RTF filled GZCLP.xlsx`).

## Verification Verdict (research finding — empirical foundation)

The progression **delta table is exact** vs the original SBS RTF template. Cross-checked against `Quick Setup` row 6 (main-lift squat delta row `I6:P6`) and the `4x` sheet's week-2 TM formula `I4`:

| diff (actual − repout) | xlsx Quick Setup | `engine/_sbs_delta` |
|---|---|---|
| ≤ −2 | −0.05 | −0.05 ✓ |
| −1   | −0.02 | −0.02 ✓ |
|  0   |  0.00 |  0.00 ✓ |
| +1 / +2 / +3 / +4 / +5+ | +0.005 / +0.01 / +0.015 / +0.02 / +0.03 | identical ✓ |

The xlsx TM recurrence (`4x`!`I4`) is `new_TM = old_TM × (1 + delta)` with **no `MROUND`**; the working weight (`4x`!`B5`) is `MROUND(TM × intensity, rounding)`. Both match the engine's intent — except the engine was erroneously rounding the TM.

**User's 90 kg is the correct SBS result.** Week-1 Squat = 95 kg × 8 reps, repout 10 → diff −2 → −5 % → TM `135 × 0.95 = 128.25` → week-2 weight `MROUND(128.25 × 0.7, 2.5) = 90`. Missing the rep target by 2 carries a −5 % TM penalty per the SBS rulebook.

## The Bug: TM is rounded to the gym increment every week

`sbs_cli/engine/progression.py` `sbs_next` rounds the **TM** to the 2.5 kg quantum each step:

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

> **Note on the table:** the exact week-by-week TM figures are illustrative — the precise trajectory depends on which week index is labelled "entering week N". The regression test (Change 2 / Test Plan) therefore asserts the *property* (raw TM, monotonically climbing weight, all legal 2.5 steps) rather than hardcoding these checkpoints.

### Why the gym's 2.5 kg minimum does not fix this

The gym's minimum plate increment is 2.5 kg. That constraint applies to the weight you **load**, not to the TM (which is internal bookkeeping and is never loaded). The `rounding` setting already snaps every loaded weight to the gym increment. The stall happens because the TM that *feeds* next week's weight is frozen — so even though the loaded weight is always a 2.5 multiple, it never gets to increase. See [ADR 0001](../../adr/0001-tm-accumulates-raw.md).

## `rounding` is the universal gym-increment parameter

`rounding` is a global setting (default 2.5, editable in the webapp at `/settings`), applied to **every loaded weight** — verified exhaustive:
- sbs working weight — `sbs_cli/program.py:40,78`, `webapp/routes/plan.py:26`, `webapp/services/preview.py:13`
- T2/T3 increments and resets — `sbs_cli/program.py:51,56,97,106`, `webapp/services/tier.py:18,26,33`

The user's ask — "make the minimum plate increment a configurable parameter that drives rounding" — is therefore already satisfied functionally. This design **does** pull the cosmetic/UX follow-ups into scope (Change 6): relabel the field and link the `incr` input's spinner step to `rounding`. The internal name `rounding` (DB column, schema, all call sites) is unchanged.

## Goals

1. Make SBS TM accumulation faithful to the SBS RTF xlsx (fix the progression stall).
2. Show est1RM to 2 decimals on every display surface.
3. Correct the existing rounded-wrong TMs already stored in `sbs.db`.
4. (In scope per grilling) Relabel the gym-increment setting and link the `incr` spinner to it.

## Non-Goals

- Changing the delta table, the e1RM formulas, or any T2/T3 progression logic.
- Altering history rows (immutable facts — see Change 5 reasoning).
- Introducing weekly intensity waves (the program intentionally uses fixed per-lift intensity).
- Renaming the internal `rounding` symbol (DB column / schema / code) — display label only.
- **Follow-ups explicitly deferred** (see "Out of Scope / Follow-ups"): unifying the tier-switch TM seed; live max-edit recompute.

## Design

### Change 1 — `sbs_next` keeps TM full-precision

`sbs_cli/engine/progression.py`:

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
    See ADR 0001.
    """
    if actual is None:
        return tm
    return tm * (1 + _sbs_delta(actual - repout))
```

The `quantum` parameter is removed. The sole non-test caller is `sbs_cli/program.py:48`:

```python
state.tm = sbs_next(state.tm, lift.repout, actual_reps, quantum=profile.rounding)
```

→ drop the `quantum=...` argument. `round_weight` is still used for the working weight (`week_plan`, `routes/plan.py`) — unchanged. `t3_next` and `t2_next` **keep** their `quantum` parameter (they progress loaded weights); the asymmetry is intentional and reflects the loaded-vs-bookkeeping distinction.

### Change 2 — Update `sbs_next` unit tests

Two test files encode rounded TMs and must flip.

`tests/test_progression.py`:

| test | actual | delta | old expected | new expected |
|---|---|---|---|---|
| `test_sbs_hit_keeps_tm` | 8 | 0 % | 100 | 100 (same) |
| `test_sbs_beat_adds_pct` | 11 | +1.5 % | 102.5 | **101.5** |
| `test_sbs_miss_drops_pct` | 6 | −5 % | 95 | 95 (same) |
| `test_sbs_beat_5_plus_caps_at_3pct` | 14 | +3 % | 102.5 | **103.0** |
| `test_sbs_no_log_keeps_tm` | None | — | 100 | 100 (same) |
| `test_sbs_miss_by_1_drops_2pct` | 7 | −2 % | 97.5 | **98.0** |

`tests/test_program.py:38-39` (added during grilling — spec v1 missed this):

```python
# TM progressed: beat repout 8 by 3 -> +1.5% -> 100*1.015=101.5 (raw, no MROUND)
assert s.lifts["Squat"].tm == 101.5   # was 102.5
```

`round_weight` tests are untouched. `test_io.py:21` and `test_schema.py:18` hardcode `tm=137.5`/`135` as fixed round-trip data (not computed by `sbs_next`) — untouched.

### Change 3 — est1RM to 2 decimals on every display surface

| file:line | before | after |
|---|---|---|
| `webapp/templates/plan.html:18` | `{{ it.est1rm if it.est1rm is not none else '—' }}` | `{{ "%.2f"\|format(it.est1rm) if it.est1rm is not none else '—' }}` |
| `webapp/templates/week_export.html:32` | `{{ it.est1rm if ... }}` | `"%.2f"\|format(...)` |
| `webapp/templates/week_export.html:35` | `"%.1f"\|format(it.live)` | `"%.2f"\|format(it.live)` |
| `webapp/templates/tier_preview.html:9` | `{{ preview.est1rm if ... }}` | `"%.2f"\|format(...)` |
| `webapp/routes/plan.py:78` *(added in grilling — spec v1 missed the delta)* | `{p["delta"]:.1f}` | `{p["delta"]:.2f}` |
| `webapp/routes/plan.py:79` | `f'≈{p["est1rm"]:.1f} {delta_html}'` | `:.2f` |
| `sbs_cli/view/terminal.py:13` | `{it.est1rm:.1f}` | `:.2f` |
| `sbs_cli/view/terminal.py:30` | `{ls.est1rm:.1f}` | `:.2f` |
| `sbs_cli/view/templates/week.html.j2:26` | `"%.1f"\|format(it.est1rm)` | `"%.2f"\|format(...)` |

`plan.py:78` is the est1RM *delta* (`live − best`); it is shown adjacent to the 2-decimal est1RM at `plan.py:79`, so it must match precision. est1RM stays full-precision in storage (`lift_state.est1rm` REAL); rounding is display-only.

> **Note (informational, non-blocking):** est1RM is the mean of Epley/Brzycki/Wathan; at reps ≈ 8 the three formulas disagree by ~±1.7 kg, so 2-decimal display carries false absolute precision. The 2nd decimal is retained because the *same* formula mean is used consistently, so it captures sub-0.1 kg trend drift that 1-decimal would round away. User explicitly requested 2 decimals.

### Change 4 — TM display rounding in CLI `show`

`sbs_cli/view/terminal.py:32` *(spec v1 cited line 30; corrected — :30 is the est1RM line, :32 is the TM line)*:

```python
lines.append(f"{l.name:18} TM {ls.tm}  hist {hist}{est}")
```

→ `f"... TM {ls.tm:.1f} ..."`. TM is now a full-precision float internally; round it to 1 decimal only for the text view. (TM is never loaded, so it is not rounded to the gym increment.) The webapp's only TM display, `tier_preview.html:11` (an editable `<input>` seeded with the derived TM), is left unchanged — it already shows a raw value today (`est1rm`) and is part of the deferred tier-switch follow-up island.

### Change 5 — One-time DB recompute of stored sbs TMs (service-layer, max-replay)

**Engine** — add a pure sibling to `recompute_state` in `sbs_cli/program.py`:

```python
def recompute_sbs_tm(lift: Lift, history: List[SetEntry]) -> float:
    """Replay an sbs lift's TM from lift.max over its history (raw, no rounding).
    History rows are immutable facts; only their reps drive the replay.
    No Profile needed: sbs_next post-fix takes only (tm, repout, actual)."""
    tm = lift.max
    for h in sorted(history, key=lambda x: x.week):
        tm = sbs_next(tm, lift.repout, h.reps)
    return tm
```

**Service** — add an I/O wrapper in `webapp/services/recompute.py`, mirroring `recompute_on_start_change` (engine stays pure, service owns repo I/O):

```python
def recompute_sbs_tm(conn: sqlite3.Connection, lift_id: int) -> Optional[float]:
    """Replay an sbs lift's TM from its max over history and write the corrected tm.
    Returns the recomputed TM, or None for non-sbs lifts (no-op). est1rm untouched."""
    lift_row = repo.get_lift(conn, lift_id)
    if lift_row["tier"] != "sbs":
        return None
    history = [SetEntry(week=h["week"], weight=h["weight"], reps=h["reps"])
               for h in repo.list_history(conn, lift_id)]
    lift = advance_service._lift_from_row(lift_row)
    tm = _recompute_sbs_tm_engine(lift, history)   # the pure fn, imported aliased
    st = repo.get_lift_state(conn, lift_id)
    repo.save_lift_state(conn, lift_id, tier="sbs", tm=tm, weight=None,
                         target=None, streak=0, est1rm=st["est1rm"])
    return tm
```

**Migration** — `migrate_sbs_tm.py` mirrors `migrate_recompute.py` (back up `sbs.db` → iterate sbs lifts → call the service). Unlike `migrate_recompute`, it touches no settings:

```python
def main(db_path: str = "sbs.db", backup_dir: str = "backups") -> None:
    # back up db (existing backup.py convention), then:
    conn = db.connect(db_path)
    try:
        db.init_schema(conn)
        n = 0
        for row in repo.list_lifts(conn):
            if row["tier"] == "sbs" and recompute_service.recompute_sbs_tm(conn, row["id"]) is not None:
                n += 1
    finally:
        conn.close()
```

**Decision Q1=A′ — replay from `lift.max`, no guard.** This is xlsx-faithful: in the xlsx, editing `Max` recomputes every downstream TM from that `Max`. A guard that skipped lifts whose rounded replay mismatched the stored TM would skip exactly the lifts xlsx semantics say to recompute — anti-faithful — so no guard. Idempotent: replaying the same history always yields the same raw TM. est1RM is untouched: it is derived from the *actual lifted* history weights (immutable facts), so the bug never corrupted it (see "Verification note" below).

Example corrections after running (Squat week-1 history = 95 kg × 8, repout 10):
- Squat: `127.5` → **`128.25`** (135 × 0.95; `round_weight(128.25, 2.5)` was `127.5`)

> **Verification note (subtle, resolved):** the buggy rounded TM could, on some weeks, prescribe a working weight one quantum off from the faithful value, and that weight was logged to history. This does *not* corrupt est1RM: history records what was *actually lifted* (immutable fact), and est1RM estimates from actual performance. The bug affected what was *prescribed*, not the *estimate's* correctness. est1RM is therefore left untouched by the migration.

### Change 6 — (new, from grilling) Settings UX: relabel + spinner linkage

`webapp/templates/settings.html`:

| line | before | after |
|---|---|---|
| 6 | `<label>rounding (kg): <input type="number" step="0.5" name="rounding" ...>` | `<label>最小变动 (kg): <input type="number" step="0.5" name="rounding" ...>` |
| 8 | `<label>incr (kg): <input type="number" step="0.5" name="incr" ...>` | `<input type="number" step="{{ s.rounding }}" name="incr" ...>` |

- The `rounding` field's display label is localized to `最小变动 (kg)`; its `step` stays `0.5` so users can set any common quantum (0.5 / 1.0 / 1.25 / 2.5). `step="{{ s.rounding }}"` would be wrong here — from 2.5 it could only jump to 5.0 / 0.
- The `incr` field (a weight increment) gets `step="{{ s.rounding }}"` so its spinner snaps to legal gym multiples. Functional behavior is unchanged (`t2_next` already snaps via `round_weight(weight + incr, quantum)`); this is pure UX.
- Internal name `rounding` is unchanged everywhere (DB column `settings.rounding`, `Profile.rounding`, all call sites).
- `t2_reset_pct` (step 0.05), `t2_fail`, `t3_target` keep their natural steps — unrelated to the rounding quantum.

## Test Plan

- **Unit (`tests/test_progression.py`)**: the 3 `sbs_next` expectations flip to raw values (Change 2).
- **Unit (`tests/test_program.py`)**: `test_advance_sbs_appends_history_and_updates_est1rm` tm assertion flips `102.5 → 101.5` (Change 2); **add** `test_sbs_tm_raw_accumulation_unfreezes_weight` — the regression test (Decision Q2):
  ```python
  def test_sbs_tm_raw_accumulation_unfreezes_weight():
      # beat repout by 1 each week -> +0.5%/week, the stall case
      p = Profile(lifts=[Lift(name="Squat", tier="sbs", day=1, max=135,
                              intensity=0.7, reps=4, repout=8, sets=3)])
      s = initial_state(p); lift = p.lift("Squat")
      weights = []
      for week in range(1, 9):
          advance_lift(p, lift, s.lifts["Squat"], actual_reps=9, week=week)
          weights.append(week_plan(p, s, day=1)[0].weight)
      assert s.lifts["Squat"].tm % 2.5 != 0          # (a) TM stays raw
      assert weights[-1] > weights[0]                # (b) weight climbs -- stall fixed
      assert all(w % 2.5 == 0 for w in weights)      # (c) all legal 2.5 steps
  ```
  The test asserts the *property*, not hardcoded week checkpoints (the spec's illustrative week-6/21 numbers are off-by-one in indexing and must not be locked in).
- **Migration test (`tests/test_migrate_sbs_tm.py`, new)** — mirror `test_migrate_recompute.py`: seed `sbs.db` with a rounded TM + history, run the migration, assert TM equals the raw replay and est1RM is unchanged; assert a backup was created.
- **Display tests (Decision Q7 = Add)**: augment `test_terminal.py:18`, `test_html.py:20`, `test_routes_plan.py:56` with a 2-decimal assertion (e.g. regex `\d+\.\d{2}` on the rendered output) so the 2-decimal est1RM rendering is locked against regression.
- Run full suite: `conda run -n sbs python -m pytest tests/ -v`.

## Risks / Edge Cases

- **Stored TM becomes a long float** (e.g. `128.8875` after several weeks). Mitigated by Change 4 (display rounding). The number is never loaded.
- **Migration touches the live DB.** Mitigated by backing up `sbs.db` first; idempotent max-replay; only the `tm` column written; est1RM untouched.
- **Calling sites passing `quantum=`.** Only `sbs_cli/program.py:48`; grep confirms no others outside tests.
- **Tests encoding the bug.** Four assertions (3 in `test_progression.py`, 1 in `test_program.py:39`) flip to raw values — they are the bug captured, not regressions.
- **Two TM-seeding conventions now coexist** (engine/migration: `lift.max`; tier-switch-into-sbs: `est1rm`). A lift switched into sbs via the webapp, then touched by the migration, will have its est1rm-seeded TM overwritten by a max-replay. Accepted; unification is a follow-up (ADR 0001 Consequences).
- **No guard on edited `max`.** Deliberate (A′). Editing an sbs lift's `max` does not currently recompute its TM — a separate, pre-existing gap vs the xlsx, recorded as a follow-up.

## Decisions from grilling

| # | Decision |
|---|---|
| Q1 | **A′** — migration replays TM from `lift.max`, no guard (xlsx-faithful). tier-switch est1rm-seed + live max-edit recompute deferred. |
| Q2 | Regression test asserts raw TM + climbing weight + all-legal-2.5-steps; no hardcoded trajectory checkpoints. |
| Q3 | **P** — pure `recompute_sbs_tm` in `program.py` + I/O wrapper in `webapp/services/recompute.py`; migration calls the service (mirrors `migrate_recompute.py`). Forward value: the max-edit follow-up can reuse the wrapper. |
| Q4 | CLI `show` TM rounded to 1 decimal (`terminal.py:32`); `tier_preview` TM input left unchanged (already raw today; part of deferred tier-switch island). |
| Q5 | **Now** — relabel setting `最小变动 (kg)`; `incr` spinner `step="{{ s.rounding }}"`; `rounding` spinner keeps `step="0.5"`; internal name unchanged. |
| Q6 | Create `CONTEXT.md` + `docs/adr/0001-tm-accumulates-raw.md`; update this spec. |
| Q7 | Add 2-decimal assertions to the three display tests. |
| F1 | `plan.py:78` delta joins the `:.2f` flip list (spec v1 missed it). |
| F2 | Change 4 line citation corrected `terminal.py:30 → 32`. |
| F3 | `test_io.py:21` / `test_schema.py:18` left untouched (fixed round-trip data). |
| — | `test_program.py:39` joins Change 2 flip list (`102.5 → 101.5`). |

## Out of Scope / Follow-ups

- **Unify the tier-switch-into-sbs TM seed** (`webapp/services/tier.py:21`, currently `tm = est1rm`) with the engine's `max`-replay. A lift switched into sbs currently gets an est1rm-derived TM; the migration would overwrite it. Resolving this means picking one canonical seed.
- **Live `max`-edit recompute for sbs.** `webapp/services/recompute.py:recompute_on_start_change` returns `None` for sbs; editing an sbs lift's `max` leaves its TM stale, diverging from the xlsx (where editing `Max` live-recomputes all TMs). The new `recompute_sbs_tm` service wrapper is positioned to serve this when wired into the lift edit route.
- **Weekly intensity progression** (fixed per-lift intensity is intentional).
- **T2/T3 / e1RM formula changes.**
- **Re-validating against the Hypertrophy or RIR template variants** (only RTF was requested).
