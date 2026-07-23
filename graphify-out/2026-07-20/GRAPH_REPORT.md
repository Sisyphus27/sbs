# Graph Report - .  (2026-07-20)

## Corpus Check
- 126 files · ~93,585 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 832 nodes · 2319 edges · 42 communities (40 shown, 2 thin omitted)
- Extraction: 97% EXTRACTED · 3% INFERRED · 0% AMBIGUOUS · INFERRED: 64 edges (avg confidence: 0.65)
- Token cost: 6,200 input · 4,100 output

## Community Hubs (Navigation)
- HTMX vendored min.js
- Flask app & cycle index
- Excel builder tests
- 21-week schedule defaults
- Skill/agent config metadata
- Data schema & state recompute
- Tier progression engine
- Design history & concepts
- YAML profile/state I/O
- Advance service & DB tests
- Settings routes & autosave
- Lift CRUD routes tests
- Plan view & tonnage export
- Repository tests
- 1RM estimation formulas
- Program advance & week plan
- CLI entry points
- Tier switch service tests
- Comet change: per-lift incr
- TM recompute migration tests
- Schedule migration tests
- Settings & schedule routes/templates
- Cold-backup xlsx importer
- Week HTML render/parse
- T2/T3 progression params
- Plan/reseed/export endpoints
- Incr column migration tests
- Reseed routes tests
- ADRs 0001/0002: TM rounding & reseed
- Lift CRUD endpoints & row partial
- Init migration tests
- ADR 0003 & verify report
- PlanItem model
- OpenSpec config

## God Nodes (most connected - your core abstractions)
1. `connect()` - 99 edges
2. `create_lift()` - 57 edges
3. `Profile` - 43 edges
4. `Lift` - 41 edges
5. `get_lift_state()` - 37 edges
6. `SetEntry` - 36 edges
7. `get_settings()` - 35 edges
8. `get_lift()` - 31 edges
9. `oe()` - 31 edges
10. `advance_lift()` - 31 edges

## Surprising Connections (you probably didn't know these)
- `reseed.html (重测 max)` --implements--> `Decision: prompted per-lift skippable TM reseed at 21-week cycle boundary`  [INFERRED]
  webapp/templates/reseed.html → docs/adr/0002-cycle-boundary-reseed.md
- `test_migrate_refuses_overwrite()` --calls--> `connect()`  [EXTRACTED]
  tests/test_migrate.py → webapp/db.py
- `test_import_pulls_sbs_maxes()` --indirect_call--> `Profile`  [INFERRED]
  tests/test_importer.py → sbs_cli/data/schema.py
- `test_round_weight_mround()` --calls--> `round_weight()`  [EXTRACTED]
  tests/test_progression.py → sbs_cli/engine/progression.py
- `test_t3_next_signature_has_no_quantum()` --indirect_call--> `t3_next()`  [INFERRED]
  tests/test_progression.py → sbs_cli/engine/progression.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Templates extending base.html layout** — webapp_templates_base, webapp_templates_lifts, webapp_templates_plan, webapp_templates_reseed, webapp_templates_schedule, webapp_templates_settings, webapp_templates_tier_preview [EXTRACTED 1.00]
- **Cycle-boundary TM reseed UI flow (banner → reseed → apply/skip)** — webapp_templates_plan, webapp_templates_reseed, route_reseed_view, route_reseed_apply, route_reseed_skip, concept_cycle_boundary_reseed [INFERRED 0.85]
- **T2/T3 progression rounding decision chain (ADR 0001 → ADR 0003 → spec)** — docs_adr_0001_tm_accumulates_raw, docs_adr_0003_t2t3_progression_snap_grid, openspec_specs_t2t3_progression_spec, concept_rounding_loaded_weights_only, concept_effective_step_grid, concept_per_lift_incr_override [INFERRED 0.85]
- **T2 cascade rule evolution (10->8->6 to 8->6 to 8->6->4 to 1-strike)** — docs_superpowers_specs_2026_06_28_t2_4x8_cascade_redesign_design, docs_superpowers_specs_2026_07_01_start_recompute_design, docs_superpowers_specs_2026_07_06_sbs_weekly_schedule_and_t2_redesign_design, concept_t2_next_function [EXTRACTED 0.95]
- **Engine pure replay functions (history-immutable state derivation)** — concept_recompute_state_function, concept_recompute_sbs_tm_function, concept_t2_next_function, concept_sbs_next_function [INFERRED 0.85]
- **Project ADR trilogy (TM raw / cycle reseed / effective step)** — rationale_adr_0001_tm_raw, rationale_adr_0002_cycle_reseed, rationale_adr_0003_effective_step [INFERRED 0.75]
- **per-lift-t2t3-increment OpenSpec change artifact set** — openspec_changes_archive_2026_07_11_per_lift_t2t3_increment_proposal, openspec_changes_archive_2026_07_11_per_lift_t2t3_increment_design, openspec_changes_archive_2026_07_11_per_lift_t2t3_increment_tasks, openspec_changes_archive_2026_07_11_per_lift_t2t3_increment_specs_t2t3_progression_spec [EXTRACTED 0.95]
- **Comet design-phase handoff chain (context -> brainstorm -> design-context -> design)** — openspec_changes_archive_2026_07_11_per_lift_t2t3_increment__comet_context, openspec_changes_archive_2026_07_11_per_lift_t2t3_increment__comet_handoff_brainstorm_summary, openspec_changes_archive_2026_07_11_per_lift_t2t3_increment__comet_handoff_design_context, openspec_changes_archive_2026_07_11_per_lift_t2t3_increment_design [INFERRED 0.85]
- **Design decision set D1-D5 (per-lift-t2t3-increment)** — decision_per_lift_incr_nullable, decision_t2t3_remove_rounding, decision_eff_incr_engine_boundary, decision_alter_table_migration, decision_ui_tier_conditional [EXTRACTED 0.95]

## Communities (42 total, 2 thin omitted)

### Community 0 - "HTMX vendored min.js"
Cohesion: 0.08
Nodes (102): A(), ae(), ar(), at(), B(), be(), br(), bt() (+94 more)

### Community 1 - "Flask app & cycle index"
Cohesion: 0.05
Nodes (56): Flask, cycle_number(), Which 21-week cycle a program week falls in (1-based)., app(), test_snapshot_copies_db(), test_snapshot_filename_format(), test_cycle_number(), create_app() (+48 more)

### Community 2 - "Excel builder tests"
Cohesion: 0.06
Nodes (60): _assert_t3_zone_shape(), _copy(), A template whose Accessories section is too short must fail loudly., insert_rows must translate same-sheet refs so Day2+ SBS formulas still point at, SBS TM cells must keep their 'Quick Setup'!D{X} cross-sheet refs after build_all, Core invariants for one day sheet's T3 zone after inject_t3_zones., test_handles_concatenate_and_function_names(), test_leaves_below_threshold_alone() (+52 more)

### Community 3 - "21-week schedule defaults"
Cohesion: 0.08
Nodes (34): ScheduleRow, Single source for reset-to-default settings + the standard SBS RTF 21-week ladde, _rows(), lookup_schedule(), Cyclic 1..21 schedule-row index for an absolute program week., Return the ScheduleRow for (kind, schedule_week(program_week)).      Raises Ke, schedule_week(), test_load_schedule_returns_dataclasses() (+26 more)

### Community 4 - "Skill/agent config metadata"
Cohesion: 0.05
Nodes (38): definition, agents, apiVersion, goal, kind, metadata, orchestration, skills (+30 more)

### Community 5 - "Data schema & state recompute"
Cohesion: 0.12
Nodes (28): In-memory data model., SetEntry, best_1rm(), _est1rm_from_history(), Tie engine rules to lift state; manage history + est1rm + week plan., Replay an sbs lift's TM from ``lift.max`` over its history (raw, no rounding),, Return (weight, reps) of the history entry with the highest estimate_1rm, or Non, Re-derive a t2/t3 lift's state by replaying progression from ``lift.start`` (+20 more)

### Community 6 - "Tier progression engine"
Cohesion: 0.13
Nodes (32): Per-tier progression rules. Pure functions; the spec source of truth., SBS main/aux: next TM from rep-out performance. actual=None -> unchanged., T3 accessories: +incr when last set >= target, else repeat.      Pure arithmet, T2 1-strike cascade: each miss drops one rep level (8 -> 6 -> 4); after `fail`, _sbs_delta(), sbs_next(), t2_next(), T2State (+24 more)

### Community 7 - "Design history & concepts"
Cohesion: 0.10
Nodes (31): SBS/T2/T3 Three-Tier Progression Model, Engine pure function recompute_sbs_tm (raw TM replay from max), Engine pure function recompute_state (t2/t3 history replay), Engine pure function sbs_next (TM autoregulation), sbs_schedule table (21-week main/aux intensity ladder), sbs.db single-file SQLite store (Repository pattern), Engine pure function t2_next (GZCLP T2 state machine), Plan: SBS + GZCLP T2/T3 Hybrid Progression (xlsx) (+23 more)

### Community 8 - "YAML profile/state I/O"
Cohesion: 0.13
Nodes (26): load_profile(), load_state(), profile_from_dict(), profile_to_dict(), YAML load/save for Profile and ProgramState., save_profile(), save_state(), state_from_dict() (+18 more)

### Community 9 - "Advance service & DB tests"
Cohesion: 0.13
Nodes (27): Same exercise on two days is two independent rows; logging by id targets each., Regression: legacy DBs that predate the lifts.incr column (pre-migrate_incr), _seed(), test_advance_week_handles_duplicate_names_per_day(), test_advance_week_rows_t2_hit_increments(), test_advance_week_runs_engine_and_bumps_week(), test_advance_week_skips_unlogged_lifts(), test_lift_from_row_tolerates_missing_incr_column() (+19 more)

### Community 10 - "Settings routes & autosave"
Cohesion: 0.10
Nodes (25): test_get_and_replace_schedule(), test_reset_schedule_restores_defaults(), Daily logging: save per-field (no advance), prefill on reopen, advance consumes, test_autosave_persists_and_prefills_then_advances(), test_reset_t2_fail_restores_default(), test_settings_update(), clear_one_log(), clear_week_logs() (+17 more)

### Community 11 - "Lift CRUD routes tests"
Cohesion: 0.16
Nodes (24): test_init_schema_seeds_schedule(), _lift(), _t2_lift(), _t2_lift_with_incr(), test_create_lift_via_post(), test_create_rejects_nonpositive_incr(), test_create_sbs_does_not_write_incr(), test_create_sbs_persists_lift_kind() (+16 more)

### Community 12 - "Plan view & tonnage export"
Cohesion: 0.09
Nodes (26): A lift with this week's last-set logged renders its tonnage inline., Same name on two days must render each day's own weight (id-keyed, not clobbered, Week 1 -> no last week -> tonnage shows 首次., A lift whose last-set is not yet logged shows no tonnage fragment., Filling the last-set returns live est1RM + tonnage in the same fragment., Clearing the last-set returns 200 with empty body so .save-ok is wiped., Two-week t2: past tonnage uses the replayed target; Δ% renders with arrow + colo, 手机离线导出含与桌面同源的 容量 片段（经 _by_day -> _live_html 接出）。     week 1 -> 首次 标记，不除零。fixtur (+18 more)

### Community 13 - "Repository tests"
Cohesion: 0.19
Nodes (25): _fresh(), Same exercise on different days = two independent rows (keyed by id, not name)., test_append_history_and_list(), test_create_lift_accepts_incr_and_round_trips(), test_create_lift_accepts_lift_kind(), test_create_lift_allows_duplicate_name_different_day(), test_create_lift_incr_defaults_null(), test_create_lift_sbs_returns_id_and_inits_state() (+17 more)

### Community 14 - "1RM estimation formulas"
Cohesion: 0.17
Nodes (22): brzycki(), epley(), estimate_1rm(), Estimated 1RM = mean of Epley, Brzycki, Wathan (top-3 authoritative formulas)., Mean of the three formulas. Most accurate at reps <= 10., wathan(), test_brzycki_formula(), test_epley_formula() (+14 more)

### Community 15 - "Program advance & week plan"
Cohesion: 0.24
Nodes (23): Profile, Mirror Excel MROUND(w, quantum): round(w/quantum) half-away-from-zero, then * qu, round_weight(), advance_lift(), initial_state(), Apply this week's logged last-set reps; mutate state in place. All knobs from pr, Build the display plan for a given day (or all lifts if day=None)., week_plan() (+15 more)

### Community 16 - "CLI entry points"
Cohesion: 0.20
Nodes (16): build_parser(), cmd_init(), cmd_next(), cmd_show(), cmd_week(), _load(), CLI entry: init / week / next / show., run() (+8 more)

### Community 17 - "Tier switch service tests"
Cohesion: 0.21
Nodes (19): Row, t2 derive：incr=5 的动作，起始重量 snap 到 eff_incr=5 网格，而非全局 rounding=2.5。, D6：tier 切换不触碰 lifts.incr 列。, Regression: on a legacy DB whose lifts table has NO incr column     (pre-migrat, _seed_with_history(), test_apply_switch_preserves_incr(), test_apply_tier_switch_keeps_history_and_writes_state(), test_derive_state_t2_snaps_to_eff_incr() (+11 more)

### Community 18 - "Comet change: per-lift incr"
Cohesion: 0.18
Nodes (17): ADR 0003: each action owns its snap grid (cable stack independent of barbell rounding), Capability: t2t3-progression, D4: one-shot ALTER TABLE migration script (PRAGMA-guarded idempotent), D3: resolve eff_incr at engine boundary, keep progression pure, D1: per-lift incr nullable column, NULL = inherit global, D2: drop rounding snap on t2/t3 hit path (arith step self-quantizes), D5: incr UI only in /lifts editor, tier-conditional rendering, Comet state — per-lift-t2t3-increment (.comet.yaml) (+9 more)

### Community 19 - "TM recompute migration tests"
Cohesion: 0.21
Nodes (12): _seed(), test_migrate_bumps_reset_pct_and_syncs_weight(), test_migrate_creates_backup(), _seed(), test_migrate_creates_backup(), test_migrate_is_idempotent(), test_migrate_replays_sbs_tm_raw_from_max(), test_migrate_skips_non_sbs_lifts() (+4 more)

### Community 20 - "Schedule migration tests"
Cohesion: 0.22
Nodes (13): _build_legacy_db(), Tests for the one-shot `migrate_schedule` migration.  The helper `_build_legac, Spot-check week-1 main + week-7 aux (deload) values to confirm the seed is DEFAU, One logged miss under the new 1-strike rule drops target 8 -> 6., Create a legacy (pre-Task 1/5/6) schema + seed two lifts.      Returns (squat_, Re-running must not error, must not duplicate schedule rows, must converge, test_migrate_adds_reseeded_cycle_column_with_default_0(), test_migrate_backfills_squat_lift_kind_main() (+5 more)

### Community 21 - "Settings & schedule routes/templates"
Cohesion: 0.17
Nodes (13): Known debt: two TM-seeding conventions coexist (lift.max vs est1rm), Flask endpoint lifts.tier_apply, Flask endpoint lifts.view, Flask endpoint plan.view, Flask endpoint schedule.reset, Flask endpoint schedule.save, Flask endpoint settings.reset_field, Flask endpoint settings.update (+5 more)

### Community 22 - "Cold-backup xlsx importer"
Cohesion: 0.33
Nodes (9): import_profile(), _is_formula(), One-time import: cold-backup xlsx -> Profile. Specific to the user's 4x layout., test_import_back_rows_are_t2_with_correct_day(), test_import_days_per_week_matches_sheet(), test_import_does_not_misclassify_next_day_back_row_as_t3(), test_import_pulls_accessories_as_t3(), test_import_pulls_back_rows_as_t2() (+1 more)

### Community 23 - "Week HTML render/parse"
Cohesion: 0.35
Nodes (9): parse_log_json(), Render week-N.html (form + JS export) and parse exported log JSON., Parse a week-N-log.json. Returns {week: int, logs: {lift_name: reps}}., render_week_html(), _profile(), test_parse_log_json_reads_filled_values_ignores_blanks(), test_render_html_est1rm_two_decimals(), test_render_html_has_input_per_lift_and_export_button() (+1 more)

### Community 24 - "T2/T3 progression params"
Cohesion: 0.29
Nodes (9): Pure-Python encoding of the GZCLP T2 state machine and T3 rule.  These functio, Return (next_target, next_streak, next_weight) for T2 (Back).      Scheme tier, Return next weight for T3 (Accessories): +incr if last_set >= target., Mirror Excel MROUND(w, quantum): round w/quantum half-away-from-zero, then * qua, round_weight(), t2_next(), T2Params, t3_next() (+1 more)

### Community 25 - "Plan/reseed/export endpoints"
Cohesion: 0.22
Nodes (9): Flask endpoint plan.export_week, Flask endpoint plan.save_log (htmx autosave), Flask endpoint plan.submit, Flask endpoint reseed.apply, Flask endpoint reseed.skip, Flask endpoint reseed.view, plan.html (本周计划 live view), reseed.html (重测 max) (+1 more)

### Community 26 - "Incr column migration tests"
Cohesion: 0.52
Nodes (6): _has_incr(), _legacy_db(), Build a lifts table WITHOUT the incr column, mirroring a pre-migration DB., test_migrate_adds_incr_column(), test_migrate_idempotent_on_already_migrated(), test_migrate_idempotent_on_fresh_schema()

### Community 27 - "Reseed routes tests"
Cohesion: 0.52
Nodes (6): _seed_squat_at(), test_plan_banner_lists_due_reseed(), test_reseed_apply_sets_max_and_tm(), test_reseed_due_at_cycle_2_week_22(), test_reseed_not_due_in_cycle_1(), test_reseed_skip_keeps_tm_advances_cycle()

### Community 28 - "ADRs 0001/0002: TM rounding & reseed"
Cohesion: 0.33
Nodes (6): Decision: prompted per-lift skippable TM reseed at 21-week cycle boundary, Decision: rounding quantum applies ONLY to loaded (sbs/T2/T3) weights, not TM, Decision: TM is bookkeeping, accumulates raw float, never rounded, North star: cell-by-cell faithfulness to SBS RTF xlsx template, ADR 0001 — TM accumulates raw; rounding only on loaded weights, ADR 0002 — Cycle-boundary TM reseed: prompt, per-lift, skippable

### Community 29 - "Lift CRUD endpoints & row partial"
Cohesion: 0.33
Nodes (6): Flask endpoint lifts.delete (htmx), Flask endpoint lifts.edit (htmx inline), Flask endpoint lifts.new, Flask endpoint lifts.tier_preview, _lift_row.html (lift row partial), lifts.html (动作管理)

### Community 30 - "Init migration tests"
Cohesion: 0.47
Nodes (5): test_migrate_from_xlsx_sets_sbs_lift_kind(), test_migrate_from_yaml(), test_migrate_refuses_overwrite(), _write_yaml(), list_lifts()

### Community 31 - "ADR 0003 & verify report"
Cohesion: 0.60
Nodes (5): Mechanism: each T2/T3 lift snaps derived weights to its own eff_incr grid, Feature: per-lift incr override (lifts.incr) with global fallback, ADR 0003 — T2/T3 progression snaps to per-lift effective-step grid, Verify report — per-lift-t2t3-increment (2026-07-11), t2t3-progression spec (archived main spec)

## Knowledge Gaps
- **58 isolated node(s):** `agents`, `apiVersion`, `inputs`, `outputs`, `statement` (+53 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **2 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `connect()` connect `Lift CRUD routes tests` to `Flask app & cycle index`, `21-week schedule defaults`, `Advance service & DB tests`, `Settings routes & autosave`, `Plan view & tonnage export`, `Repository tests`, `1RM estimation formulas`, `Tier switch service tests`, `TM recompute migration tests`, `Schedule migration tests`, `Incr column migration tests`, `Reseed routes tests`, `Init migration tests`?**
  _High betweenness centrality (0.076) - this node is a cross-community bridge._
- **Why does `SetEntry` connect `Data schema & state recompute` to `21-week schedule defaults`, `YAML profile/state I/O`, `Advance service & DB tests`, `1RM estimation formulas`, `Program advance & week plan`, `Tier switch service tests`?**
  _High betweenness centrality (0.027) - this node is a cross-community bridge._
- **Why does `advance_lift()` connect `Program advance & week plan` to `21-week schedule defaults`, `Data schema & state recompute`, `Tier progression engine`, `YAML profile/state I/O`, `Advance service & DB tests`, `CLI entry points`, `Week HTML render/parse`?**
  _High betweenness centrality (0.024) - this node is a cross-community bridge._
- **What connects `agents`, `apiVersion`, `inputs` to the rest of the system?**
  _58 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `HTMX vendored min.js` be split into smaller, more focused modules?**
  _Cohesion score 0.0814772510946126 - nodes in this community are weakly interconnected._
- **Should `Flask app & cycle index` be split into smaller, more focused modules?**
  _Cohesion score 0.05267778753292362 - nodes in this community are weakly interconnected._
- **Should `Excel builder tests` be split into smaller, more focused modules?**
  _Cohesion score 0.060153776571687016 - nodes in this community are weakly interconnected._