# Design: SBS/GZCLP Training CLI

**Date:** 2026-06-26
**Status:** Approved (brainstorming lock) — pending implementation plan
**Relationship to prior work:** Supersedes the xlsx-modification approach (`2026-06-25-sbs-gzclp-t2-t3-design.md`). That approach delivered a working engine but mutated the user's spreadsheet cell-by-cell, which proved unmaintainable (4x sheet had real user data that got duplicated/overwritten; cell-level formulas too opaque to inspect or adjust). This design keeps the proven engine logic and moves it into a clean CLI tool with a simple config + HTML interface. The existing `tools/sbs_gzclp/progression.py` (T2/T3, 36 tests) is reused; the xlsx `formulas.py`/`builder.py` are set aside.

---

## 1. Goal

A command-line training program tool that:
- Holds the whole program (SBS main/auxiliary + GZCLP back + accessories) in one place.
- Lets the user configure lifts in a small readable YAML file (no cell formulas).
- Generates a weekly plan as a standalone HTML page with input fields.
- Reads back the user's logged last-set reps (via a JSON exported by the HTML) and auto-progresses every lift for the next week.
- Replaces the spreadsheet entirely for day-to-day use.

## 2. Why CLI + HTML (not spreadsheet, not web app)

The spreadsheet mixes **logic + data + presentation** in cell formulas — every change requires understanding a web of cross-cell refs, and user data is easily overwritten. MVC separation fixes this:

| Layer | Spreadsheet (old) | CLI (new) |
|-------|-------------------|-----------|
| Logic (progression rules) | cell formulas | `progression.py` + `onerm.py` (pure functions, unit-tested) |
| Data (1RMs, logs, state) | cells mixed with formulas | `profile.yaml` (static) + `state.yaml` (dynamic) |
| Presentation (weekly plan) | the sheet itself | generated `week-N.html` (read-only view + input form) |

CLI was chosen over a web app for lightness; the HTML form gives web-style input without running a server. A later `sbs serve` (mini local server) is an explicit upgrade path if JSON-file juggling becomes annoying.

## 3. Engine (pure Python — the spec source of truth)

All logic is pure functions in two modules, unit-tested.

### 3.1 `onerm.py` — estimated 1RM
Average of the three most authoritative formulas (per research consensus + community practice):

```
Epley:   1RM = w * (1 + reps/30)
Brzycki: 1RM = w * 36 / (37 - reps)
Wathan:  1RM = w * 100 / (48.8 + 53.8 * exp(-0.075 * reps))

estimate_1rm(weight, reps) = mean(epley, brzycki, wathan)
```
- Valid with best accuracy at reps ≤ 10 (±5%); degrades above ~10 reps but acceptable for estimation.
- Sources: [PMC 1RM prediction study](https://pmc.ncbi.nlm.nih.gov/articles/PMC9465738/), [Symmetric Strength (uses Wathan)](https://symmetricstrength.com/calculator/one_rep_max), [All Things Gym (side-by-side, average)](https://allthingsgym.com/rep-max-calculator/), [r/powerlifting consensus](https://www.reddit.com/r/powerlifting/comments/sup61v/ever_wondered_how_the_different_1rm_formulae/).

### 3.2 `progression.py` — progression rules per tier
Each lift belongs to one of three tiers. The engine takes the lift's current state + this week's logged last-set reps and returns next week's state.

**SBS tier (main + auxiliary lifts) — autoregulated TM:**
- State: `tm` (training max), plus static `intensity`, `reps`, `repout` (rep-out target), `sets`.
- Weekly working weight = `round(tm * intensity, quantum)`.
- Delta table (beats/misses the rep-out target):
  - miss by 2+ → −5% | miss by 1 → −2% | hit → 0% | beat 1 → +0.5% | beat 2 → +1% | beat 3 → +1.5% | beat 4 → +2% | beat 5+ → +3%
- Next TM = `tm * (1 + delta(actual − repout))`. No log → TM unchanged.
- (These deltas are the user's existing SBS RTF values, ported verbatim from the spreadsheet's Quick Setup `I6:P6`.)
- **Simplification vs the sheet:** `intensity`/`reps`/`repout` are fixed per lift in `profile.yaml`. The spreadsheet's 21-week intensity wave is dropped (YAGNI). A future `scheme: [...]` per-lift list could restore weekly variation if wanted.

**T2 tier (back) — GZCLP stateful, reset via est1RM:**
- State: `target` (10/8/6), `streak` (consecutive misses at current target), `weight`.
- Hit (`last_set >= target`) → weight + `incr`, target unchanged, streak 0.
- Miss, `streak+1 < fail` (fail=3) → streak+1, same weight/target.
- 3rd miss at 10 → target 8, same weight, streak 0.
- 3rd miss at 8 → target 6, same weight, streak 0.
- 3rd miss at 6 → **reset**: `weight = round(0.70 * estimate_1rm(best_set_weight, best_set_reps), quantum)`, target 10, streak 0.
  - `best_set` = the (weight, reps) pair from this lift's history that yields the highest `estimate_1rm`.
- No log → state unchanged.

**T3 tier (accessories) — simple threshold:**
- State: `weight`. Static `target = 15`, `sets = 3`.
- Hit (`last_set >= 15`) → weight + `incr`. Miss → repeat. No log → repeat.

`progression.py` already implements T2/T3 (with the old ×0.8 reset). The reset branch is changed to take `est1rm` (from `onerm.py`) and use `0.70 * est1rm`. New `t2_next` signature gains an `est1rm` parameter. SBS-tier is new (a `sbs_next(tm, intensity, actual, repout, deltas)` function).

## 4. Data model

### 4.1 `profile.yaml` (static, user-editable)
```yaml
rounding: 2.5          # MROUND quantum (kg)
days_per_week: 4
incr: 2.5              # weekly increment for T2/T3 (kg)
t2_reset_pct: 0.70     # reset weight = pct * est1RM
t2_fail: 3             # consecutive misses to trigger tier change
t3_target: 15

lifts:
  # SBS main/aux
  - {name: Squat,        tier: sbs, max: 135, intensity: 0.75, reps: 4, repout: 8, sets: 3, day: 1}
  - {name: Bench Press,  tier: sbs, max: 120, intensity: 0.75, reps: 4, repout: 8, sets: 3, day: 2}
  - {name: Deadlift,     tier: sbs, max: 145, intensity: 0.80, reps: 3, repout: 6, sets: 3, day: 3}
  - {name: OHP,          tier: sbs, max: 73,  intensity: 0.75, reps: 4, repout: 8, sets: 3, day: 4}
  # GZCLP T2 (back)
  - {name: Barbell rows, tier: t2,  start: 85, day: 1}
  - {name: DB rows,      tier: t2,  start: 65, day: 2}
  - {name: Pull-downs,   tier: t2,  start: 45, day: 3}
  - {name: Chin-ups,     tier: t2,  start: 20, day: 4}   # BW + added
  # GZCLP T3 (accessories)
  - {name: Leg Extension, tier: t3, start: 40, day: 1}
  - {name: Face Pull,     tier: t3, start: 30, day: 2}
  # ... etc
```
- `sbs` lifts use `max` (1RM) as initial TM. `t2`/`t3` use `start` (working weight).
- Each lift assigned to a `day` (1..days_per_week).

### 4.2 `state.yaml` (dynamic, tool-managed)
```yaml
week: 3
lifts:
  Squat:
    tier: sbs
    tm: 137.5
    est1rm: 158.3          # from best logged set
    history: [{week: 1, weight: 102.5, reps: 8}, {week: 2, weight: 105, reps: 10}, ...]
  Barbell rows:
    tier: t2
    weight: 87.5
    target: 10
    streak: 0
    est1rm: 110.0
    best_set: {weight: 85, reps: 9}
    history: [...]
  Leg Extension:
    tier: t3
    weight: 42.5
    est1rm: 62.0
    history: [...]
```
- `history` is an append-only list of `{week, weight, last_set_reps}`.
- `est1rm` recomputed each log from the best set (max `estimate_1rm` over history).
- T2 also stores `best_set` for the reset calculation.

## 5. CLI commands

Entry point: `sbs` (a Python console script, run via `conda run -n tamp python -m sbs_cli ...` during dev).

- **`sbs init --from <xlsx>`** — read the user's existing 4x sheet (from `backup/00_cold_backup.xlsx`) and emit `profile.yaml`:
  - Pull SBS 1RMs from Quick Setup `D5:D16`.
  - Pull back-lift names + weights from the hand-entered back rows (Barbell rows 85, DB rows 65, Pull-downs 45, Chin-ups BW) → T2 entries.
  - Pull accessory names + weights from the Accessories rows (Leg Extension 40, etc.) → T3 entries.
  - Days/week inferred from sheet (4 for 4x). User edits the generated file to taste.
- **`sbs week [N]`** — generate `week-N.html` for the current week (or specified), and print the plan to the terminal. If `state.yaml` is fresh (week 1), TMs = profile maxes, T2/T3 weights = starts.
- **`sbs next <log.json>`** — read the exported log, apply `progression` to every lift, append history, update `state.yaml`, bump week, generate `week-(N+1).html`.
- **`sbs show`** — terminal summary: per-lift current TM/weight/target/streak + est1RM + recent history.

## 6. HTML week page

`week-N.html` — a single standalone file (inline CSS + JS, no external deps), opens in any browser/phone offline.

Per-day sections; each lift is a row:
```
Squat (sbs)        | est1RM 158.3 kg
  102.5 kg × 4 × 3   | rep-out target 8 | last set reps: [ 9  ]   ← <input type="number">
Barbell rows (t2)  | est1RM 110.0 kg | target 3×10, streak 0
  85 kg × 10 × 3     | last set reps: [    ]   ← <input>
Leg Extension (t3) | est1RM 62.0 kg
  40 kg × 15+ × 3    | last set reps: [    ]   ← <input>
```
Footer: a **"Export results"** button. Its inline JS collects every `<input>` (keyed by lift name) into an object and triggers download of `week-N-log.json`:
```json
{"week": 3, "logs": {"Squat": 9, "Barbell rows": 12, "Leg Extension": 15}}
```
(Missing/blank inputs are treated as "no log" for that lift — progression carries it forward unchanged.)

## 7. Scope

- Whole program: SBS main/aux + GZCLP T2 + T3, all in the CLI. The spreadsheet is no longer used for day-to-day training.
- Engine logic is ported/reused from the verified `progression.py` (T2/T3) + new SBS-tier + new `onerm.py`.
- User's real data preserved via `sbs init` from the cold backup.

## 8. Verification

- **Unit tests** per engine layer:
  - `onerm.py`: known (weight, reps) → exact Epley/Brzycki/Wathan values + mean; edge cases (reps=1 → ≈weight, high reps).
  - `progression.py` SBS tier: each delta branch (miss 2+/miss 1/hit/beat 1..5); no-log carry.
  - `progression.py` T2: hit, miss<3, 10→8, 8→6, 6→reset(0.70×est1rm); no-log carry. (Existing T2 tests updated for the new reset rule.)
  - `progression.py` T3: hit +incr, miss repeat, no-log repeat.
- **End-to-end test**: `sbs init` on a fixture → `sbs week` produces week-1.html → synthesize a `week-1-log.json` with sample reps → `sbs next` → assert `state.yaml` and `week-2.html` reflect correct progression (e.g., Squat beat repout by 3 → TM ×1.015; Barbell rows hit → +2.5; T2 at 3×6 + 3rd miss → reset to 0.70 × est1rm(best); Leg Extension ≥15 → +2.5).
- **HTML round-trip test**: parse a generated `week-N.html`, confirm every lift has an `<input>`; feed a log JSON back through `sbs next` and confirm the parser reads all values.

## 9. Out of scope (YAGNI / future)

- `sbs serve` mini local server (upgrade path from JSON round-trip).
- Charts/trends in HTML (est1RM over time) — candidate follow-up.
- Volume totals, fatigue tracking, deload weeks beyond the T2 reset.
- Multi-user, cloud sync.
- Reading/writing xlsx (the whole point is to leave Excel).
