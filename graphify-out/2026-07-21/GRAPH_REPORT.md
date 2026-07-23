# Graph Report - sbs  (2026-07-20)

## Corpus Check
- 225 files · ~2,466,877 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1859 nodes · 3418 edges · 156 communities (144 shown, 12 thin omitted)
- Extraction: 98% EXTRACTED · 2% INFERRED · 0% AMBIGUOUS · INFERRED: 71 edges (avg confidence: 0.64)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `63de772b`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

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
- SBS/GZCLP 训练 CLI
- plan.py
- 自重动作的工作重量（bodyweight working weight）— Design
- Using Git Worktrees
- Global Constraints
- onboard.md
- Visual Companion Guide
- SKILL.md
- Creation Log: Systematic Debugging Skill
- Code Review Reception
- The Process
- Systematic Debugging
- Testing CLAUDE.md Skills Documentation
- ScheduleRow
- Dispatching Parallel Agents
- Root Cause Tracing
- Persuasion Principles for Skill Design
- Writing Skills
- Testing Skills With Subagents
- SBS 训练 Web App 使用指南
- Writing Plans
- Skill authoring best practices
- SBS/GZCLP 训练 Web App
- Defense-in-Depth Validation
- Verification Before Completion
- Executing Plans
- SKILL.md
- [Analysis Title]
- Returns: "OK" or lists conflicts
- explore.md
- Condition-Based Waiting
- Skill structure
- Instructions_5978dc06.md
- app.py
- helper.js
- Brainstorming Ideas Into Designs
- render-graphs.js
- 00_cold_backup_0756400b.md
- 01_columns_2eef9def.md
- 02_progression_e5ba38e4.md
- 03_formulas_c31113b4.md
- 04_config_bfcc1664.md
- 05_t3_490391ae.md
- 06_t2_0ab331a0.md
- 07_build_all_bb304ea2.md
- 08_final_55612d55.md
- SBS Hypertrophy Template_95ab1477.md
- SBS Hypertrophy Template LF_6f9beaed.md
- SBS Linear Progression LF_90697f52.md
- SBS RTF filled GZCLP_2ec9fad0.md
- SBS Strength Program_fb03e7ae.md
- SBS Strength Program last set RIR_6246e1a0.md
- SBS Strength Program last set RIR LF_acd41427.md
- SBS Strength Program LF_253f813d.md
- SBS Strength Program reps to failure_69cb0914.md
- SBS Strength Program reps to failure LF_6f40804b.md
- working_weight
- SBS Linear Progression_022b317c.md
- stop-server.sh
- REFACTOR Phase: Close Loopholes (Stay Green)
- SBS Novice hypertrophy program_08651acb.md
- migrate_incr.py
- SKILL.md
- Skill Discovery Optimization (SDO)
- Bulletproofing Skills Against Rationalization
- Pressure Test 1: Emergency Production Fix
- Pressure Test 2: Sunk Cost + Exhaustion
- Pressure Test 3: Authority + Social Pressure
- Anti-Patterns
- Testing All Skill Types
- RED-GREEN-REFACTOR for Skills
- VERIFY GREEN: Pressure Testing
- SBS Program Builder_9b627086.md
- codex-tools.md
- Pi Tool Mapping
- Evaluation and iteration
- Checklist for effective Skills
- File Organization
- Skill Types
- Example: TDD Skill Bulletproofing
- dependencies
- start-server.sh
- Antigravity CLI (`agy`) Tool Mapping
- Anti-patterns to avoid
- Recommendations
- graphify
- CLAUDE.md
- spec-document-reviewer-prompt.md
- review-package
- sdd-workspace
- task-brief
- find-polluter.sh
- test-academic.md
- plan-document-reviewer-prompt.md

## God Nodes (most connected - your core abstractions)
1. `connect()` - 105 edges
2. `create_lift()` - 59 edges
3. `Profile` - 44 edges
4. `Lift` - 42 edges
5. `SetEntry` - 41 edges
6. `get_lift_state()` - 37 edges
7. `get_settings()` - 36 edges
8. `init_schema()` - 35 edges
9. `advance_lift()` - 31 edges
10. `get_lift()` - 31 edges

## Surprising Connections (you probably didn't know these)
- `reseed.html (重测 max)` --implements--> `Decision: prompted per-lift skippable TM reseed at 21-week cycle boundary`  [INFERRED]
  webapp/templates/reseed.html → docs/adr/0002-cycle-boundary-reseed.md
- `connect()` --indirect_call--> `e()`  [INFERRED]
  .claude/skills/brainstorming/scripts/helper.js → webapp/static/htmx.min.js
- `test_load_schedule_returns_dataclasses()` --indirect_call--> `ScheduleRow`  [INFERRED]
  tests/test_repo.py → sbs_cli/data/schema.py
- `test_import_pulls_sbs_maxes()` --indirect_call--> `Profile`  [INFERRED]
  tests/test_importer.py → sbs_cli/data/schema.py
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

## Communities (156 total, 12 thin omitted)

### Community 0 - "HTMX vendored min.js"
Cohesion: 0.08
Nodes (102): A(), ae(), ar(), at(), B(), be(), br(), bt() (+94 more)

### Community 1 - "Flask app & cycle index"
Cohesion: 0.09
Nodes (34): Flask, cycle_number(), Which 21-week cycle a program week falls in (1-based)., get_db(), SQLite connection + schema bootstrap., Per-request connection stored in flask.g., Stamp ``reseeded_cycle`` on an sbs lift; if ``new_max`` is given, also set, set_reseed() (+26 more)

### Community 2 - "Excel builder tests"
Cohesion: 0.06
Nodes (60): _assert_t3_zone_shape(), _copy(), A template whose Accessories section is too short must fail loudly., insert_rows must translate same-sheet refs so Day2+ SBS formulas still point at, SBS TM cells must keep their 'Quick Setup'!D{X} cross-sheet refs after build_all, Core invariants for one day sheet's T3 zone after inject_t3_zones., test_handles_concatenate_and_function_names(), test_leaves_below_threshold_alone() (+52 more)

### Community 3 - "21-week schedule defaults"
Cohesion: 0.19
Nodes (20): _sbs(), _t2(), test_actual_tonnage_basic(), test_actual_tonnage_single_set(), test_actual_tonnage_zero_or_none_sets_falls_back_to_3(), test_t2_target_as_of_initial_when_no_prior_history(), test_t2_target_as_of_replays_miss_drop(), test_volume_current_not_logged_returns_none() (+12 more)

### Community 4 - "Skill/agent config metadata"
Cohesion: 0.05
Nodes (38): definition, agents, apiVersion, goal, kind, metadata, orchestration, skills (+30 more)

### Community 5 - "Data schema & state recompute"
Cohesion: 0.14
Nodes (28): In-memory data model., SetEntry, best_1rm(), _est1rm_from_history(), Tie engine rules to lift state; manage history + est1rm + week plan., Re-derive a t2/t3 lift's state by replaying progression from ``lift.start``, Return (working_weight, reps) of the history entry with the highest     estimat, Replay an sbs lift's TM from ``lift.max`` over its history (raw, no rounding), (+20 more)

### Community 6 - "Tier progression engine"
Cohesion: 0.13
Nodes (31): Per-tier progression rules. Pure functions; the spec source of truth., SBS main/aux: next TM from rep-out performance. actual=None -> unchanged., T3 accessories: +incr when last set >= target, else repeat.      Pure arithmet, T2 1-strike cascade: each miss drops one rep level (8 -> 6 -> 4); after `fail`, _sbs_delta(), sbs_next(), t2_next(), T2State (+23 more)

### Community 7 - "Design history & concepts"
Cohesion: 0.10
Nodes (31): SBS/T2/T3 Three-Tier Progression Model, Engine pure function recompute_sbs_tm (raw TM replay from max), Engine pure function recompute_state (t2/t3 history replay), Engine pure function sbs_next (TM autoregulation), sbs_schedule table (21-week main/aux intensity ladder), sbs.db single-file SQLite store (Repository pattern), Engine pure function t2_next (GZCLP T2 state machine), Plan: SBS + GZCLP T2/T3 Hybrid Progression (xlsx) (+23 more)

### Community 8 - "YAML profile/state I/O"
Cohesion: 0.15
Nodes (29): load_profile(), load_state(), profile_from_dict(), profile_to_dict(), YAML load/save for Profile and ProgramState., save_profile(), save_state(), state_from_dict() (+21 more)

### Community 9 - "Advance service & DB tests"
Cohesion: 0.17
Nodes (18): Same exercise on two days is two independent rows; logging by id targets each., _seed(), test_advance_week_handles_duplicate_names_per_day(), test_advance_week_rows_t2_hit_increments(), test_advance_week_runs_engine_and_bumps_week(), test_advance_week_skips_unlogged_lifts(), test_load_schedule_returns_dataclasses(), list_history() (+10 more)

### Community 10 - "Settings routes & autosave"
Cohesion: 0.13
Nodes (24): main(), migrate_from_xlsx(), migrate_from_yaml(), One-shot migration: profile.yaml + state.yaml -> SQLite sbs.db., test_migrate_from_xlsx_sets_sbs_lift_kind(), test_migrate_from_yaml(), test_migrate_refuses_overwrite(), _write_yaml() (+16 more)

### Community 11 - "Lift CRUD routes tests"
Cohesion: 0.12
Nodes (29): test_create_lift_accepts_incr_and_round_trips(), test_create_lift_accepts_lift_kind(), test_create_lift_incr_defaults_null(), _lift(), _t2_lift(), _t2_lift_with_incr(), test_create_lift_via_post(), test_create_rejects_nonpositive_incr() (+21 more)

### Community 12 - "Plan view & tonnage export"
Cohesion: 0.09
Nodes (25): A lift with this week's last-set logged renders its tonnage inline., Same name on two days must render each day's own weight (id-keyed, not clobbered, Week 1 -> no last week -> tonnage shows 首次., A lift whose last-set is not yet logged shows no tonnage fragment., Filling the last-set returns live est1RM + tonnage in the same fragment., Clearing the last-set returns 200 with empty body so .save-ok is wiped., Two-week t2: past tonnage uses the replayed target; Δ% renders with arrow + colo, 手机离线导出含与桌面同源的 容量 片段（经 _by_day -> _live_html 接出）。     week 1 -> 首次 标记，不除零。fixtur (+17 more)

### Community 13 - "Repository tests"
Cohesion: 0.14
Nodes (31): recompute 服务经 _lift_from_row(incr) + recompute_state(eff_incr) 自动继承 per-lift inc, _t2(), test_recompute_on_start_change_uses_per_lift_incr(), test_recompute_preserves_est1rm_from_history(), test_recompute_sbs_is_noop(), test_recompute_t2_no_history_sets_weight_to_start(), _fresh(), advance_week must not reset reseeded_cycle to 0 every week (ADR 0002). (+23 more)

### Community 14 - "1RM estimation formulas"
Cohesion: 0.19
Nodes (20): brzycki(), epley(), estimate_1rm(), Estimated 1RM = mean of Epley, Brzycki, Wathan (top-3 authoritative formulas)., Mean of the three formulas. Most accurate at reps <= 10., wathan(), test_brzycki_formula(), test_epley_formula() (+12 more)

### Community 15 - "Program advance & week plan"
Cohesion: 0.13
Nodes (26): Mirror Excel MROUND(w, quantum): round(w/quantum) half-away-from-zero, then * qu, round_weight(), advance_lift(), initial_state(), PlanItem, Apply this week's logged last-set reps; mutate state in place. All knobs from pr, Build the display plan for a given day (or all lifts if day=None)., week_plan() (+18 more)

### Community 16 - "CLI entry points"
Cohesion: 0.17
Nodes (19): build_parser(), cmd_init(), cmd_next(), cmd_show(), cmd_week(), _load(), CLI entry: init / week / next / show., run() (+11 more)

### Community 17 - "Tier switch service tests"
Cohesion: 0.21
Nodes (19): Row, t2 derive：incr=5 的动作，起始重量 snap 到 eff_incr=5 网格，而非全局 rounding=2.5。, D6：tier 切换不触碰 lifts.incr 列。, Regression: on a legacy DB whose lifts table has NO incr column     (pre-migrat, _seed_with_history(), test_apply_switch_preserves_incr(), test_apply_tier_switch_keeps_history_and_writes_state(), test_derive_state_t2_snaps_to_eff_incr() (+11 more)

### Community 18 - "Comet change: per-lift incr"
Cohesion: 0.18
Nodes (17): ADR 0003: each action owns its snap grid (cable stack independent of barbell rounding), Capability: t2t3-progression, D4: one-shot ALTER TABLE migration script (PRAGMA-guarded idempotent), D3: resolve eff_incr at engine boundary, keep progression pure, D1: per-lift incr nullable column, NULL = inherit global, D2: drop rounding snap on t2/t3 hit path (arith step self-quantizes), D5: incr UI only in /lifts editor, tier-conditional rendering, Comet state — per-lift-t2t3-increment (.comet.yaml) (+9 more)

### Community 19 - "TM recompute migration tests"
Cohesion: 0.13
Nodes (22): main(), One-shot migration: bump t2_reset_pct 0.70 -> 0.75 and resync every t2/t3 lift_, main(), One-shot migration: recompute every sbs lift's stored TM by replaying from its, init_schema seeds sbs_schedule from DEFAULT_SCHEDULE exactly once (Task 5)., lifts.lift_kind + lifts.incr and lift_state.reseeded_cycle exist (Task 5 / per-l, test_foreign_keys_enforced(), test_init_schema_creates_tables_and_default_settings() (+14 more)

### Community 20 - "Schedule migration tests"
Cohesion: 0.11
Nodes (32): _add_lift_kind(), _add_reseeded_cycle(), _backfill_lift_kind(), _column_exists(), _ensure_schedule(), main(), Connection, One-shot migration: bring a live ``sbs.db`` from the pre-schedule schema to the (+24 more)

### Community 21 - "Settings & schedule routes/templates"
Cohesion: 0.17
Nodes (13): Known debt: two TM-seeding conventions coexist (lift.max vs est1rm), Flask endpoint lifts.tier_apply, Flask endpoint lifts.view, Flask endpoint plan.view, Flask endpoint schedule.reset, Flask endpoint schedule.save, Flask endpoint settings.reset_field, Flask endpoint settings.update (+5 more)

### Community 22 - "Cold-backup xlsx importer"
Cohesion: 0.33
Nodes (9): import_profile(), _is_formula(), One-time import: cold-backup xlsx -> Profile. Specific to the user's 4x layout., test_import_back_rows_are_t2_with_correct_day(), test_import_days_per_week_matches_sheet(), test_import_does_not_misclassify_next_day_back_row_as_t3(), test_import_pulls_accessories_as_t3(), test_import_pulls_back_rows_as_t2() (+1 more)

### Community 23 - "Week HTML render/parse"
Cohesion: 0.06
Nodes (55): bootstrapPage(), brandMarkup(), broadcast(), browserLauncherForPlatform(), chmodOwnerOnly(), clients, companionUrl(), computeAcceptKey() (+47 more)

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
Cohesion: 0.05
Nodes (38): Common Rationalizations, Debugging Integration, Example: Bug Fix, Final Rule, Good Tests, GREEN - Minimal Code, Overview, Red Flags - STOP and Start Over (+30 more)

### Community 31 - "ADR 0003 & verify report"
Cohesion: 0.60
Nodes (5): Mechanism: each T2/T3 lift snaps derived weights to its own eff_incr grid, Feature: per-lift incr override (lifts.incr) with global fallback, ADR 0003 — T2/T3 progression snaps to per-lift effective-step grid, Verify report — per-lift-t2t3-increment (2026-07-11), t2t3-progression spec (archived main spec)

### Community 32 - "PlanItem model"
Cohesion: 0.07
Nodes (25): Code Reviewer Prompt Template, Example Output, Example, How to Request, Integration with Workflows, Red Flags, Requesting Code Review, When to Request Review (+17 more)

### Community 42 - "SBS/GZCLP 训练 CLI"
Cohesion: 0.07
Nodes (26): 1. 生成当周计划, 2. 打开 HTML 填数据, 3. 导出, 4. 算下周, profile.yaml 配置详解, SBS/GZCLP 训练 CLI, `sbs` — 主项 / 辅助（自调节）, state.yaml（程序管，别手改） (+18 more)

### Community 43 - "plan.py"
Cohesion: 0.10
Nodes (23): test_snapshot_copies_db(), test_snapshot_filename_format(), Daily logging: save per-field (no advance), prefill on reopen, advance consumes, test_autosave_persists_and_prefills_then_advances(), Snapshot the SQLite db before destructive operations., Copy src_db to dest_dir/sbs-w<week>-<ts>.db.bak. Creates dest_dir. Returns dest, snapshot(), clear_one_log() (+15 more)

### Community 44 - "自重动作的工作重量（bodyweight working weight）— Design"
Cohesion: 0.09
Nodes (20): Language, SBS, 0004 — Bodyweight lifts store added weight; working weight derived at a single seam, Consequences, Considered Options, Context, Decision, Goals / Non-Goals (+12 more)

### Community 45 - "Using Git Worktrees"
Cohesion: 0.10
Nodes (20): 1a. Native Worktree Tools (preferred), 1b. Git Worktree Fallback, Assuming directory location, Common Mistakes, Create the Worktree, Directory Selection, Fighting the harness, Overview (+12 more)

### Community 46 - "Global Constraints"
Cohesion: 0.10
Nodes (20): Bodyweight Working-Weight Implementation Plan, Execution Handoff, Global Constraints, Self-Review (run before handoff), Task 10: webapp volume — history branch uses the seam, Task 11: webapp plan view — bodyweight display format + wider layout, Task 12: Lift CRUD — edit bodyweight_pct + progression, Task 13: Global settings — bodyweight field (+12 more)

### Community 47 - "onboard.md"
Cohesion: 0.10
Nodes (19): Codebase Analysis, Graceful Exit Handling, Guardrails, Phase 10: Archive, Phase 11: Recap & Next Steps, Phase 1: Welcome, Phase 2: Task Selection, Phase 3: Explore Demo (+11 more)

### Community 48 - "Visual Companion Guide"
Cohesion: 0.10
Nodes (19): Browser Events Format, Cards (visual designs), Cleaning Up, CSS Classes Available, Design Tips, File Naming, How It Works, Mock elements (wireframe building blocks) (+11 more)

### Community 49 - "SKILL.md"
Cohesion: 0.10
Nodes (19): Codebase Analysis, Graceful Exit Handling, Guardrails, Phase 10: Archive, Phase 11: Recap & Next Steps, Phase 1: Welcome, Phase 2: Task Selection, Phase 3: Explore Demo (+11 more)

### Community 50 - "Creation Log: Systematic Debugging Skill"
Cohesion: 0.10
Nodes (19): Bulletproofing Elements, Creation Log: Systematic Debugging Skill, Enhancement 1: TDD Reference, Extraction Decisions, Final Outcome, Initial Version, Iterations, Key Insight (+11 more)

### Community 51 - "Code Review Reception"
Cohesion: 0.11
Nodes (17): Acknowledging Correct Feedback, Code Review Reception, Common Mistakes, Forbidden Responses, From External Reviewers, From your human partner, GitHub Thread Replies, Gracefully Correcting Your Pushback (+9 more)

### Community 52 - "The Process"
Cohesion: 0.12
Nodes (16): Common Mistakes, Finishing a Development Branch, Option 1: Merge Locally, Option 2: Push and Create PR, Option 3: Keep As-Is, Option 4: Discard, Overview, Quick Reference (+8 more)

### Community 53 - "Systematic Debugging"
Cohesion: 0.12
Nodes (16): Common Rationalizations, Overview, Phase 1: Root Cause Investigation, Phase 2: Pattern Analysis, Phase 3: Hypothesis and Testing, Phase 4: Implementation, Quick Reference, Real-World Impact (+8 more)

### Community 54 - "Testing CLAUDE.md Skills Documentation"
Cohesion: 0.12
Nodes (16): Documentation Variants to Test, Expected Results, Next Steps, NULL (Baseline - no skills doc), Scenario 1: Time Pressure + Confidence, Scenario 2: Sunk Cost + Works Already, Scenario 3: Authority + Speed Bias, Scenario 4: Familiarity + Efficiency (+8 more)

### Community 55 - "ScheduleRow"
Cohesion: 0.19
Nodes (15): ScheduleRow, Single source for reset-to-default settings + the standard SBS RTF 21-week ladde, _rows(), lookup_schedule(), Cyclic 1..21 schedule-row index for an absolute program week., Return the ScheduleRow for (kind, schedule_week(program_week)).      Raises Ke, schedule_week(), test_cycle_number() (+7 more)

### Community 56 - "Dispatching Parallel Agents"
Cohesion: 0.12
Nodes (15): 1. Identify Independent Domains, 2. Create Focused Agent Tasks, 3. Dispatch in Parallel, 4. Review and Integrate, Agent Prompt Structure, Common Mistakes, Dispatching Parallel Agents, Key Benefits (+7 more)

### Community 57 - "Root Cause Tracing"
Cohesion: 0.12
Nodes (15): 1. Observe the Symptom, 2. Find Immediate Cause, 3. Ask: What Called This?, 4. Keep Tracing Up, 5. Find Original Trigger, Adding Stack Traces, Finding Which Test Causes Pollution, Key Principle (+7 more)

### Community 58 - "Persuasion Principles for Skill Design"
Cohesion: 0.12
Nodes (15): 1. Authority, 2. Commitment, 3. Scarcity, 4. Social Proof, 5. Unity, 6. Reciprocity, 7. Liking, Ethical Use (+7 more)

### Community 59 - "Writing Skills"
Cohesion: 0.12
Nodes (16): Code Examples, Common Rationalizations for Skipping Testing, Directory Structure, Discovery Workflow, Flowchart Usage, Match the Form to the Failure, Overview, Skill Creation Checklist (TDD Adapted) (+8 more)

### Community 60 - "Testing Skills With Subagents"
Cohesion: 0.13
Nodes (13): Common Mistakes (Same as TDD), GREEN Phase: Write Minimal Skill (Make It Pass), Meta-Testing (When GREEN Isn't Working), Overview, Quick Reference (TDD Cycle), Real-World Impact, RED Phase: Baseline Testing (Watch It Fail), TDD Mapping for Skill Testing (+5 more)

### Community 61 - "SBS 训练 Web App 使用指南"
Cohesion: 0.14
Nodes (13): SBS 训练 Web App 使用指南, 一、启动, 七、常见问题, 三、每周流程(核心), 二、首次使用:把旧数据迁进来(只需一次), 五、全局参数(`/settings` 页), 八、(可选)打包成 exe, 六、备份 / 回滚 (+5 more)

### Community 62 - "Writing Plans"
Cohesion: 0.15
Nodes (12): Bite-Sized Task Granularity, Execution Handoff, File Structure, No Placeholders, Overview, Plan Document Header, Remember, Scope Check (+4 more)

### Community 63 - "Skill authoring best practices"
Cohesion: 0.15
Nodes (13): Avoid time-sensitive information, Common patterns, Concise is key, Content guidelines, Core principles, Implement feedback loops, Set appropriate degrees of freedom, Skill authoring best practices (+5 more)

### Community 64 - "SBS/GZCLP 训练 Web App"
Cohesion: 0.15
Nodes (12): SBS/GZCLP 训练 Web App, 三层进阶规则, 全局参数(`/settings`), 动作管理(`/lifts`), 启动, 备份 / 回滚, 开发 / 测试, 快速开始 (+4 more)

### Community 65 - "Defense-in-Depth Validation"
Cohesion: 0.17
Nodes (11): Applying the Pattern, Defense-in-Depth Validation, Example from Session, Key Insight, Layer 1: Entry Point Validation, Layer 2: Business Logic Validation, Layer 3: Environment Guards, Layer 4: Debug Instrumentation (+3 more)

### Community 66 - "Verification Before Completion"
Cohesion: 0.17
Nodes (11): Common Failures, Key Patterns, Overview, Rationalization Prevention, Red Flags - STOP, The Bottom Line, The Gate Function, The Iron Law (+3 more)

### Community 67 - "Executing Plans"
Cohesion: 0.18
Nodes (10): Executing Plans, Integration, Overview, Remember, Step 1: Load and Review Plan, Step 2: Execute Tasks, Step 3: Complete Development, The Process (+2 more)

### Community 68 - "SKILL.md"
Cohesion: 0.18
Nodes (10): Check for context, Ending Discovery, Guardrails, Handling Different Entry Points, OpenSpec Awareness, The Stance, What You Don't Have To Do, What You Might Do (+2 more)

### Community 69 - "[Analysis Title]"
Cohesion: 0.18
Nodes (10): Advanced: Skills with executable code, [Analysis Title], [Analysis Title], Executive summary, Executive summary, Key findings, Key findings, Provide utility scripts (+2 more)

### Community 70 - "Returns: "OK" or lists conflicts"
Cohesion: 0.18
Nodes (11): Avoid assuming tools are installed, Create verifiable intermediate outputs, MCP tool references, Next steps, Package dependencies, Returns: "OK" or lists conflicts, Runtime environment, Technical notes (+3 more)

### Community 71 - "explore.md"
Cohesion: 0.20
Nodes (9): Check for context, Ending Discovery, Guardrails, OpenSpec Awareness, The Stance, What You Don't Have To Do, What You Might Do, When a change exists (+1 more)

### Community 72 - "Condition-Based Waiting"
Cohesion: 0.20
Nodes (9): Common Mistakes, Condition-Based Waiting, Core Pattern, Implementation, Overview, Quick Patterns, Real-World Impact, When Arbitrary Timeout IS Correct (+1 more)

### Community 73 - "Skill structure"
Cohesion: 0.20
Nodes (10): Avoid deeply nested references, Naming conventions, Pattern 1: High-level guide with references, Pattern 2: Domain-specific organization, Pattern 3: Conditional details, Progressive disclosure patterns, Skill structure, Structure longer reference files with table of contents (+2 more)

### Community 74 - "Instructions_5978dc06.md"
Cohesion: 0.20
Nodes (9): About the Stronger By Science Programs, Other Thoughts and Suggestions, Program Builder, SBS Hypertrophy Template (normal and LF), SBS Linear Progression, SBS Novice Hypertrophy, SBS Strength Program Last Set Reps To Failure (normal and LF), SBS Strength Program Last Set RIR (normal and LF) (+1 more)

### Community 75 - "app.py"
Cohesion: 0.31
Nodes (6): app(), create_app(), Flask app factory + launch., run(), close_db(), Entry point: python -m webapp  -> starts local server + opens browser. Absolute

### Community 76 - "helper.js"
Cohesion: 0.42
Nodes (7): connect(), nextReconnectDelay(), reloadAfterRecovery(), sessionKey(), setStatus(), showTombstone(), websocketUrl()

### Community 77 - "Brainstorming Ideas Into Designs"
Cohesion: 0.22
Nodes (8): After the Design, Anti-Pattern: "This Is Too Simple To Need A Design", Brainstorming Ideas Into Designs, Checklist, Key Principles, Process Flow, The Process, Visual Companion

### Community 78 - "render-graphs.js"
Cohesion: 0.33
Nodes (8): combineGraphs(), { execSync }, extractDotBlocks(), extractGraphBody(), fs, main(), path, renderToSvg()

### Community 79 - "00_cold_backup_0756400b.md"
Cohesion: 0.22
Nodes (8): Sheet: 2x, Sheet: 3x, Sheet: 4x, Sheet: 5x, Sheet: 6x, Sheet: Quick Setup, Sheet: Setup, Sheet: Untouched

### Community 80 - "01_columns_2eef9def.md"
Cohesion: 0.22
Nodes (8): Sheet: 2x, Sheet: 3x, Sheet: 4x, Sheet: 5x, Sheet: 6x, Sheet: Quick Setup, Sheet: Setup, Sheet: Untouched

### Community 81 - "02_progression_e5ba38e4.md"
Cohesion: 0.22
Nodes (8): Sheet: 2x, Sheet: 3x, Sheet: 4x, Sheet: 5x, Sheet: 6x, Sheet: Quick Setup, Sheet: Setup, Sheet: Untouched

### Community 82 - "03_formulas_c31113b4.md"
Cohesion: 0.22
Nodes (8): Sheet: 2x, Sheet: 3x, Sheet: 4x, Sheet: 5x, Sheet: 6x, Sheet: Quick Setup, Sheet: Setup, Sheet: Untouched

### Community 83 - "04_config_bfcc1664.md"
Cohesion: 0.22
Nodes (8): Sheet: 2x, Sheet: 3x, Sheet: 4x, Sheet: 5x, Sheet: 6x, Sheet: Quick Setup, Sheet: Setup, Sheet: Untouched

### Community 84 - "05_t3_490391ae.md"
Cohesion: 0.22
Nodes (8): Sheet: 2x, Sheet: 3x, Sheet: 4x, Sheet: 5x, Sheet: 6x, Sheet: Quick Setup, Sheet: Setup, Sheet: Untouched

### Community 85 - "06_t2_0ab331a0.md"
Cohesion: 0.22
Nodes (8): Sheet: 2x, Sheet: 3x, Sheet: 4x, Sheet: 5x, Sheet: 6x, Sheet: Quick Setup, Sheet: Setup, Sheet: Untouched

### Community 86 - "07_build_all_bb304ea2.md"
Cohesion: 0.22
Nodes (8): Sheet: 2x, Sheet: 3x, Sheet: 4x, Sheet: 5x, Sheet: 6x, Sheet: Quick Setup, Sheet: Setup, Sheet: Untouched

### Community 87 - "08_final_55612d55.md"
Cohesion: 0.22
Nodes (8): Sheet: 2x, Sheet: 3x, Sheet: 4x, Sheet: 5x, Sheet: 6x, Sheet: Quick Setup, Sheet: Setup, Sheet: Untouched

### Community 88 - "SBS Hypertrophy Template_95ab1477.md"
Cohesion: 0.22
Nodes (8): Sheet: 2x, Sheet: 3x, Sheet: 4x, Sheet: 5x, Sheet: 6x, Sheet: Quick Setup, Sheet: Setup, Sheet: Untouched

### Community 89 - "SBS Hypertrophy Template LF_6f9beaed.md"
Cohesion: 0.22
Nodes (8): Sheet: 3x, Sheet: 4x, Sheet: 5xa, Sheet: 5xb, Sheet: 6x, Sheet: Quick Setup, Sheet: Setup, Sheet: Untouched

### Community 90 - "SBS Linear Progression LF_90697f52.md"
Cohesion: 0.22
Nodes (8): Sheet: 3x, Sheet: 4x, Sheet: 5xa, Sheet: 5xb, Sheet: 6x, Sheet: Quick Setup, Sheet: Setup, Sheet: Untouched

### Community 91 - "SBS RTF filled GZCLP_2ec9fad0.md"
Cohesion: 0.22
Nodes (8): Sheet: 2x, Sheet: 3x, Sheet: 4x, Sheet: 5x, Sheet: 6x, Sheet: Quick Setup, Sheet: Setup, Sheet: Untouched

### Community 92 - "SBS Strength Program_fb03e7ae.md"
Cohesion: 0.22
Nodes (8): Sheet: 2x, Sheet: 3x, Sheet: 4x, Sheet: 5x, Sheet: 6x, Sheet: Quick Setup, Sheet: Setup, Sheet: Untouched

### Community 93 - "SBS Strength Program last set RIR_6246e1a0.md"
Cohesion: 0.22
Nodes (8): Sheet: 2x, Sheet: 3x, Sheet: 4x, Sheet: 5x, Sheet: 6x, Sheet: Quick Setup, Sheet: Setup, Sheet: Untouched

### Community 94 - "SBS Strength Program last set RIR LF_acd41427.md"
Cohesion: 0.22
Nodes (8): Sheet: 3x, Sheet: 4x, Sheet: 5xa, Sheet: 5xb, Sheet: 6x, Sheet: Quick Setup, Sheet: Setup, Sheet: Untouched

### Community 95 - "SBS Strength Program LF_253f813d.md"
Cohesion: 0.22
Nodes (8): Sheet: 3x, Sheet: 4x, Sheet: 5xa, Sheet: 5xb, Sheet: 6x, Sheet: Quick Setup, Sheet: Setup, Sheet: Untouched

### Community 96 - "SBS Strength Program reps to failure_69cb0914.md"
Cohesion: 0.22
Nodes (8): Sheet: 2x, Sheet: 3x, Sheet: 4x, Sheet: 5x, Sheet: 6x, Sheet: Quick Setup, Sheet: Setup, Sheet: Untouched

### Community 97 - "SBS Strength Program reps to failure LF_6f40804b.md"
Cohesion: 0.22
Nodes (8): Sheet: 3x, Sheet: 4x, Sheet: 5xa, Sheet: 5xb, Sheet: 6x, Sheet: Quick Setup, Sheet: Setup, Sheet: Untouched

### Community 98 - "working_weight"
Cohesion: 0.36
Nodes (7): Working-weight seam: the single translation point from stored added weight to th, added + bodyweight × bodyweight_pct.      bodyweight_pct == 0.0 for an ordinary, working_weight(), test_full_bodyweight_zero_added(), test_ordinary_lift_pct_zero_returns_added_unchanged(), test_partial_bodyweight_pushup(), test_weighted_bodyweight_added_plus_bw()

### Community 99 - "SBS Linear Progression_022b317c.md"
Cohesion: 0.25
Nodes (7): Sheet: 3x, Sheet: 4x, Sheet: 5x, Sheet: 6x, Sheet: Quick Setup, Sheet: Setup, Sheet: Untouched

### Community 100 - "stop-server.sh"
Cohesion: 0.43
Nodes (4): command_has_server_id(), is_brainstorm_server(), mark_stopped(), stop-server.sh script

### Community 101 - "REFACTOR Phase: Close Loopholes (Stay Green)"
Cohesion: 0.29
Nodes (7): 1. Explicit Negation in Rules, 2. Entry in Rationalization Table, 3. Red Flag Entry, 4. Update description, Plugging Each Hole, Re-verify After Refactoring, REFACTOR Phase: Close Loopholes (Stay Green)

### Community 102 - "SBS Novice hypertrophy program_08651acb.md"
Cohesion: 0.29
Nodes (6): Sheet: 3x, Sheet: 4x, Sheet: 5x, Sheet: Quick Setup, Sheet: Setup, Sheet: Untouched

### Community 103 - "migrate_incr.py"
Cohesion: 0.43
Nodes (6): _add_incr(), _column_exists(), main(), Connection, One-shot migration: add the nullable ``lifts.incr REAL`` column to a live ``sbs., ``ALTER TABLE lifts ADD COLUMN incr REAL``. Idempotent. Returns True if added.

### Community 105 - "SKILL.md"
Cohesion: 0.33
Nodes (5): Platform Adaptation, Red Flags, Skill Priority, The Rule, User Instructions

### Community 106 - "Skill Discovery Optimization (SDO)"
Cohesion: 0.33
Nodes (6): 1. Rich Description Field, 2. Keyword Coverage, 3. Descriptive Naming, 4. Token Efficiency (Critical), 5. Cross-Referencing Other Skills, Skill Discovery Optimization (SDO)

### Community 107 - "Bulletproofing Skills Against Rationalization"
Cohesion: 0.33
Nodes (6): Address "Spirit vs Letter" Arguments, Build Rationalization Table, Bulletproofing Skills Against Rationalization, Close Every Loophole Explicitly, Create Red Flags List, Update SDO for Violation Symptoms

### Community 108 - "Pressure Test 1: Emergency Production Fix"
Cohesion: 0.40
Nodes (4): Choose A, B, or C, Pressure Test 1: Emergency Production Fix, Scenario, Your Options

### Community 109 - "Pressure Test 2: Sunk Cost + Exhaustion"
Cohesion: 0.40
Nodes (4): Choose A, B, or C, Pressure Test 2: Sunk Cost + Exhaustion, Scenario, Your Options

### Community 110 - "Pressure Test 3: Authority + Social Pressure"
Cohesion: 0.40
Nodes (4): Choose A, B, or C, Pressure Test 3: Authority + Social Pressure, Scenario, Your Options

### Community 111 - "Anti-Patterns"
Cohesion: 0.40
Nodes (5): Anti-Patterns, ❌ Code in Flowcharts, ❌ Generic Labels, ❌ Multi-Language Dilution, ❌ Narrative Example

### Community 112 - "Testing All Skill Types"
Cohesion: 0.40
Nodes (5): Discipline-Enforcing Skills (rules/requirements), Pattern Skills (mental models), Reference Skills (documentation/APIs), Technique Skills (how-to guides), Testing All Skill Types

### Community 113 - "RED-GREEN-REFACTOR for Skills"
Cohesion: 0.40
Nodes (5): GREEN: Write Minimal Skill, Micro-Test Wording Before Full Scenarios, RED-GREEN-REFACTOR for Skills, RED: Write Failing Test (Baseline), REFACTOR: Close Loopholes

### Community 114 - "VERIFY GREEN: Pressure Testing"
Cohesion: 0.40
Nodes (5): Key Elements of Good Scenarios, Pressure Types, Testing Setup, VERIFY GREEN: Pressure Testing, Writing Pressure Scenarios

### Community 115 - "SBS Program Builder_9b627086.md"
Cohesion: 0.40
Nodes (4): Sheet: Program, Sheet: Quick Setup, Sheet: Setup, Sheet: Untouched

### Community 117 - "codex-tools.md"
Cohesion: 0.50
Nodes (3): Codex App Finishing, Environment Detection, Subagent dispatch requires multi-agent support

### Community 118 - "Pi Tool Mapping"
Cohesion: 0.50
Nodes (3): Pi Tool Mapping, Subagents, Task lists

### Community 119 - "Evaluation and iteration"
Cohesion: 0.50
Nodes (4): Build evaluations first, Develop Skills iteratively with the agent, Evaluation and iteration, Observe how agents navigate Skills

### Community 120 - "Checklist for effective Skills"
Cohesion: 0.50
Nodes (4): Checklist for effective Skills, Code and scripts, Core quality, Testing

### Community 121 - "File Organization"
Cohesion: 0.50
Nodes (4): File Organization, Self-Contained Skill, Skill with Heavy Reference, Skill with Reusable Tool

### Community 122 - "Skill Types"
Cohesion: 0.50
Nodes (4): Pattern, Reference, Skill Types, Technique

### Community 123 - "Example: TDD Skill Bulletproofing"
Cohesion: 0.50
Nodes (4): Example: TDD Skill Bulletproofing, Initial Test (Failed), Iteration 1 - Add Counter, Iteration 2 - Add Foundational Principle

### Community 124 - "dependencies"
Cohesion: 0.50
Nodes (3): @fission-ai/openspec, dependencies, @fission-ai/openspec

### Community 127 - "Anti-patterns to avoid"
Cohesion: 0.67
Nodes (3): Anti-patterns to avoid, Avoid offering too many options, Avoid Windows-style paths

### Community 128 - "Recommendations"
Cohesion: 0.67
Nodes (3): Conditional workflow pattern, Examples pattern, Recommendations

## Knowledge Gaps
- **769 isolated node(s):** `crypto`, `http`, `fs`, `path`, `OPCODES` (+764 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **12 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `connect()` connect `Lift CRUD routes tests` to `Flask app & cycle index`, `21-week schedule defaults`, `migrate_incr.py`, `Advance service & DB tests`, `Settings routes & autosave`, `app.py`, `plan.py`, `Repository tests`, `1RM estimation formulas`, `Plan view & tonnage export`, `Tier switch service tests`, `TM recompute migration tests`, `Schedule migration tests`, `Incr column migration tests`, `Reseed routes tests`?**
  _High betweenness centrality (0.016) - this node is a cross-community bridge._
- **Why does `round_weight()` connect `Program advance & week plan` to `Data schema & state recompute`, `Tier progression engine`, `plan.py`, `Tier switch service tests`, `ScheduleRow`?**
  _High betweenness centrality (0.008) - this node is a cross-community bridge._
- **Why does `create_lift()` connect `Repository tests` to `Flask app & cycle index`, `21-week schedule defaults`, `Advance service & DB tests`, `Settings routes & autosave`, `Lift CRUD routes tests`, `plan.py`, `Plan view & tonnage export`, `1RM estimation formulas`, `Tier switch service tests`, `TM recompute migration tests`, `Reseed routes tests`?**
  _High betweenness centrality (0.007) - this node is a cross-community bridge._
- **What connects `crypto`, `http`, `fs` to the rest of the system?**
  _769 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `HTMX vendored min.js` be split into smaller, more focused modules?**
  _Cohesion score 0.0814772510946126 - nodes in this community are weakly interconnected._
- **Should `Flask app & cycle index` be split into smaller, more focused modules?**
  _Cohesion score 0.09176788124156546 - nodes in this community are weakly interconnected._
- **Should `Excel builder tests` be split into smaller, more focused modules?**
  _Cohesion score 0.060153776571687016 - nodes in this community are weakly interconnected._