# Design: SBS + GZCLP T2/T3 Hybrid Progression for `SBS RTF filled GZCLP.xlsx`

**Date:** 2026-06-25
**Status:** Approved (brainstorming lock) — pending implementation plan
**Base file:** `D:\WorkSpace\sbs\SBS RTF filled GZCLP.xlsx` (SBS RTF template, GZCLP overlay, user data filled)

---

## 1. Goal

Add two GZCLP-style progression tiers to the existing SBS RTF spreadsheet, while leaving the SBS engine (main + auxiliary lifts) completely untouched:

- **Back exercises → GZCLP T2** (currently not wired into the engine at all).
- **Accessories zone → GZCLP T3** (currently a flat "carry weight forward" scaffold).

Result: one sheet where the user can run SBS autoregulation for main/auxiliary lifts and GZCLP tier-based progression for back + accessories, side by side, per day, across the 2x–6x frequency sheets.

## 2. Background — how the current engine works (do not change)

- **Quick Setup** sheet: inputs (1RMs in `D5:D16`, single@8 % in `E5:E16`, rounding in `A2`=2.5), the SBS progression **delta table** (`I6:P15`), and intensity→reps / rep-out **lookup tables** (rows 31–55). Rows 18–26 hold a text-only **back-exercise menu** (Barbell rows, DB rows, Pull-ups, …) — not engine slots.
- **Setup** sheet: 21-week × 12-lift config table. Each lift slot occupies a 12-column block; row 3..14 = 12 lifts; giant nested `IF` lookups resolve intensity → reps/target/sets/deltas from Quick Setup.
- **Day sheets** `2x`..`6x`: each "Day" = a block of rows. For every SBS lift, two rows:
  - **Row 4-style (TM):** autoregulated training max. Next-week TM = prior TM × (1 + delta), delta chosen by how many reps the rep-out set beat/missed its target.
  - **Row 5-style (prescription):** `Weight = MROUND(TM × intensity, $A$2)`, plus reps / rep-out target / sets pulled from Setup.
  - Weekly grid = **7-column blocks** at columns `B, I, P, W, AD, AK, AR, …` (step 7), 21 weeks. Per-block columns: `Weight | Reps/normal set | Rep-out target | Set goal | Reps on last set | Video | Notes`. **The single logged performance signal is "Reps on last set" (offset 4, e.g. F/N/U…).**
- **Accessories zone** in each Day: 3 empty-ish rows that only **carry weight forward** (`I12 = B12`, `P12 = I12`, …). No progression logic.

## 3. Tier mapping (final)

| Tier | Lifts | Progression | Change |
|------|-------|-------------|--------|
| **T1 main** | Squat / Bench / Deadlift / OHP | SBS RTF (existing) | none |
| **Auxiliary** | Front Squat, Paused Squat, Close Grip Bench, Long Pause Bench, RDL, Incline Press | SBS RTF (existing) | none |
| **Back → T2** | Barbell rows, Pull-ups, Pull-downs, etc. | **GZCLP T2 — new** | **build** |
| **Accessories → T3** | arms / small groups / abs | **GZCLP T3 — repurpose zone** | **build** |

**Logging convention (unified, reuses SBS style):** both T2 and T3 log only the **last-set actual reps** per week (the existing "Reps on last set" column). Rationale: under fatigue the last set ≤ earlier sets, so last-set-actual ≥ target implies all sets hit target. No 3-set logging, no rep totals.

## 4. Progression rules

### 4.1 T2 (Back) — GZCLP stateful
- Scheme starts at **3×10**. Per-week "hit" = `last-set-actual ≥ target`.
- **Hit** → `+2.5 kg` next week, **stay** at current scheme.
- **3 consecutive misses** at current scheme → drop scheme (same weight):
  - 10 → 8 → 6.
- **3 consecutive misses at 3×6** → **reset**: weight `× 0.8` (deload), scheme back to **3×10**, fail-streak = 0.
- After reset, the chain repeats. There is no deeper mechanism.
- Fail-streak **resets to 0** on any hit, and **resets to 0** at the moment a tier change/reset is triggered.

### 4.2 T3 (Accessories) — simple
- **3×15+**, last set AMRAP.
- **Hit** (`last-set-actual ≥ 15`) → `+2.5 kg` next week.
- **Miss** → repeat same weight.
- (Supersedes the earlier "total reps ≥ 25" idea: with last-set-only logging, the trigger is last-set ≥ target.)

## 5. Data safety

1. **Cold backup first:** copy `SBS RTF filled GZCLP.xlsx` → `SBS RTF filled GZCLP_T3_backup.xlsx` in the same folder.
2. **Edit scope is strictly:**
   - The new **Back (T2) zone** (new rows inserted per day),
   - The existing **Accessories zone** rows (formulas rewritten),
   - A new **config region in Quick Setup**.
3. **Untouched:** all T1/Aux formulas, the user's 1RMs (`D5:D16`), the SBS delta/lookup tables, and any training log already entered.
4. Writes via **openpyxl**, preserving existing styles, number formats, merged cells, conditional formats. After writing, reload and dump formulas to diff against this spec.

## 6. Quick Setup additions

Append a labeled region **"T2/T3 Config"** in an empty area of Quick Setup (avoid rows 1–16, 18–26, 30–69; place at ~row 75+; final rows fixed at build time and recorded here).

**Global parameters (define as named ranges):**

| Name | Value | Meaning |
|------|-------|---------|
| `T2_incr` | 2.5 | T2 weekly increment (kg) |
| `T2_reset` | 0.8 | T2 deload multiplier on full reset |
| `T2_fail` | 3 | consecutive fails to trigger tier change |
| `T3_target` | 15 | T3 target reps (last set) |
| `T3_incr` | 2.5 | T3 weekly increment (kg) |

Rounding reuses `'Quick Setup'!$A$2` (= 2.5) for all `MROUND`.

**T2 (Back) slots** — one row per slot, fields: `Name (dropdown from rows 18–26 menu or free text) | Starting weight | Assigned day`.
Default count: **2 per day** (e.g. horizontal pull + vertical pull). Adjustable.

**T3 (Accessories) slots** — one row per slot, fields: `Name | Starting weight | Assigned day`.
Default count: **3 per day**. Adjustable.

Slot→day assignment tells the day sheets which Quick Setup slot each T2/T3 row reads.

## 7. Day-sheet layout per Day

Within each Day block on `2x`/`3x`/`4x`/`5x`/`6x`, after the existing SBS T1/Aux lifts and before/over the Accessories zone:

```
[existing SBS T1 + Auxiliary lifts]            ← untouched
Back (T2) — NEW zone, 2 rows per back lift:
    state row : Name | per week [ Weight | Target(10/8/6) | FailStreak ]
    log row   :        per week [ Reps on last set (ACTUAL) | Notes ]
Accessories (T3) — REPURPOSED zone, 1 row per acc lift:
    row       : Name | per week [ Weight | Target=15 | Reps on last set (ACTUAL) | Notes ]
```

- Weekly 7-column blocks aligned to the **same grid as SBS** (`B, I, P, W, AD, …`, step 7) so weeks line up visually across the whole Day.
- Inserting the Back zone shifts the old Accessories rows down. Since Accessories formulas are being rewritten anyway, this is safe; just re-pin references.
- Within a T2/T3 block, the columns used (by 0-based offset from the block-start column `S`):
  - offset 0 → Weight
  - offset 1 → Target reps
  - offset 2 → FailStreak (T2 state row only)
  - offset 4 → Reps on last set (ACTUAL)
  - offset 6 → Notes

## 8. Formulas

Notation: `S` = block-start column for the current week; `S+7` = next week's block-start. `R` = the lift's state row; `R+1` = its log row. Column letters shown are the week-1 (B-block) example.

### 8.1 T2 — state machine (2 rows per lift)

**Week 1 (seed, column B):** manual / from Quick Setup.
```
B{R}  (Weight)     = <Quick Setup T2 slot starting weight>
C{R}  (Target)     = 10
D{R}  (FailStreak) = 0
F{R+1}(Last-set)   = (blank — user logs after session)
```

**Next week (block at S+7), given current block at S:**
```
# Helper (inline in formulas): hit = (last-set-actual at S+4,R+1) >= (target at S+1,R)
#                                logged = (last-set-actual at S+4,R+1) <> ""

(S+1){R}  Target:
  = IF((S+4){R+1}="", (S+1){R},
     IF((S+4){R+1} >= (S+1){R}, (S+1){R},                       // hit → stay
        IF((S+2){R}+1 >= T2_fail,                               // 3rd consecutive miss
           IF((S+1){R}=10, 8, IF((S+1){R}=8, 6, 10)),           // 10→8, 8→6, 6→reset→10
           (S+1){R})))                                          // miss <3 → stay

(S+2){R}  FailStreak:
  = IF((S+4){R+1}="", (S+2){R},
     IF((S+4){R+1} >= (S+1){R}, 0,                              // hit → reset
        IF((S+2){R}+1 >= T2_fail, 0,                            // tier change triggered → reset at new tier
           (S+2){R}+1)))                                        // accumulate

(S){R}→(S+7){R}  Weight:
  = IF((S+4){R+1}="", (S){R},
     IF((S+4){R+1} >= (S+1){R}, MROUND((S){R}+T2_incr, 'Quick Setup'!$A$2),   // hit → +2.5
        IF(AND((S+2){R}+1 >= T2_fail, (S+1){R}=6),                          // 6 & 3rd miss → RESET
           MROUND((S){R}*T2_reset, 'Quick Setup'!$A$2),
           (S){R})))                                                          // tier drop or <3 → same weight
```

Key behaviors encoded:
- Hit at any tier → `+2.5`, scheme unchanged, streak 0.
- Miss, streak < 3 → same weight, same scheme, streak +1.
- 3rd miss at 10 → scheme 8, same weight, streak 0.
- 3rd miss at 8 → scheme 6, same weight, streak 0.
- 3rd miss at 6 → weight `×0.8`, scheme 10, streak 0 (full reset).
- No log yet → carry everything forward unchanged.

State is carried explicitly per week (Target, FailStreak columns) → no leftward history scan; each cell depends only on the immediately prior week + this week's log.

### 8.2 T3 — simple (1 row per lift)

**Week 1 (seed, column B):**
```
B{R} (Weight) = <Quick Setup T3 slot starting weight>
C{R} (Target) = T3_target   (15)
F{R} (Last-set)= (blank — user logs)
```

**Next week (block at S+7):**
```
(S+7){R}  Weight:
  = IF((S+4){R}="", (S){R},
     IF((S+4){R} >= T3_target, MROUND((S){R}+T3_incr, 'Quick Setup'!$A$2), (S){R}))
```
(`last-set ≥ 15 → +2.5`, else repeat; no log → repeat.)

## 9. Replication across frequency sheets

- `2x` (2 days), `3x` (3), `4x` (4), `5x`/`5xa`/`5xb`, `6x` (6): each Day block gets the T2 zone + T3 zone per §7.
- T2 slot count per day = 2, T3 = 3 (default; adjustable per Quick Setup assignment).
- Build one Day's T2/T3 block as a template, then replicate per Day and per frequency sheet, re-pinning the Quick Setup slot references and the row anchors.

## 10. Verification

1. **Formula rewrite check:** after writing, reload with openpyxl and dump T2/T3 formulas; diff against §8.
2. **T2 manual trace** (3 scenarios):
   - Hit at 10 → weight +2.5, stays 10, streak 0.
   - 3 misses at 10 → scheme 8, same weight, streak 0.
   - 3 misses at 6 → weight ×0.8, scheme 10, streak 0.
3. **T3 manual trace:** last-set 16 → +2.5; last-set 12 → repeat; blank → repeat.
4. **Open in Excel/LibreOffice:** no `#REF!`/`#VALUE!`; styles, merged cells, conditional formats intact; SBS T1/Aux cells unchanged.
5. **User acceptance:** user fills 2 real weeks of T2 + T3 and confirms progression matches expectation.

## 11. Out of scope (YAGNI)

- Per-lift SBS/Linear/GZCLP **mode switch** on T1/Auxiliary lifts (they stay SBS). Add later only if a specific lift needs it.
- Refactoring the existing SBS engine or the Setup 21-week table.
- Volume totals, e1RM estimation, plate math, charts, localization. (Candidate follow-ups.)
- Touching the other 12 template files in `SBS Programs\` — they are pristine references; the change is local to the main file.
