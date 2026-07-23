"""One-shot migration: profile.yaml + state.yaml -> SQLite sbs.db."""
import argparse
import os
import sys

from sbs_cli.data import io as dio
from webapp import db, repo


def seed(conn, p):
    """Apply a Profile to an already-open DB: settings + lifts.

    Writes the global settings row (rounding/incr/etc. + bodyweight) and
    creates one row per lift with its initial per-row state. Idempotent only
    against a fresh schema — does not clear existing rows. Returns the
    ordered list of lift ids matching ``p.lifts`` order so callers applying
    legacy state can address rows by index.
    """
    repo.update_settings(
        conn, days_per_week=p.days_per_week, rounding=p.rounding,
        incr=p.incr, t2_reset_pct=p.t2_reset_pct, t2_fail=p.t2_fail, t3_target=p.t3_target,
        bodyweight=p.bodyweight,
    )
    lids = []
    for i, l in enumerate(p.lifts):
        lid = repo.create_lift(
            conn, name=l.name, load_model=l.load_model, mode=l.mode,
            day=l.day, sort_order=i, sets=l.sets,
            max=l.max, intensity=l.intensity, reps=l.reps, repout=l.repout, start=l.start,
            lift_kind=l.lift_kind, incr=l.incr,
            bodyweight_pct=l.bodyweight_pct)
        lids.append(lid)
    return lids


def migrate_from_yaml(db_path: str, profile_path: str, state_path: str, *, force: bool = False) -> None:
    if os.path.exists(db_path) and not force:
        sys.exit(f"refusing to overwrite existing {db_path} (pass --force)")
    if not os.path.exists(profile_path):
        sys.exit(f"profile not found: {profile_path}")
    if not os.path.exists(state_path):
        sys.exit(f"state not found: {state_path}")

    p = dio.load_profile(profile_path)
    s = dio.load_state(state_path)
    conn = db.connect(db_path)
    db.init_schema(conn)
    lids = seed(conn, p)
    repo.update_settings(conn, week=s.week)
    # Pass 2: apply YAML state. The old state.yaml is name-keyed, so for a name
    # shared by multiple rows (e.g. Face Pull on day 2 + day 4) assign the YAML
    # state to the single row whose configured start/max matches the YAML value;
    # other same-name rows keep their initial state from pass 1.
    by_name = {}
    for i, l in enumerate(p.lifts):
        by_name.setdefault(l.name, []).append(i)
    for name, idxs in by_name.items():
        ls = s.lifts.get(name)
        if ls is None:
            continue
        target_i = idxs[0]
        if len(idxs) > 1:
            for i in idxs:
                l = p.lifts[i]
                if l.mode == "sbs" and ls.tm is not None and l.max == ls.tm:
                    target_i = i
                    break
                if l.mode in ("linear_t2", "linear_t3") and ls.weight is not None and l.start == ls.weight:
                    target_i = i
                    break
        lid = lids[target_i]
        repo.save_lift_state(conn, lid, mode=ls.mode, tm=ls.tm, weight=ls.weight,
                             target=ls.target, streak=ls.streak, est1rm=ls.est1rm)
        for h in ls.history:
            repo.append_history(conn, lid, week=h.week, weight=h.weight, reps=h.reps)
    conn.close()
    print(f"migrated {len(p.lifts)} lifts, week {s.week} -> {db_path}")


def migrate_from_xlsx(db_path: str, xlsx_path: str, *, force: bool = False) -> None:
    from sbs_cli.importer import import_profile
    if os.path.exists(db_path) and not force:
        sys.exit(f"refusing to overwrite existing {db_path} (pass --force)")
    p = import_profile(xlsx_path)
    conn = db.connect(db_path)
    db.init_schema(conn)
    seed(conn, p)
    repo.update_settings(conn, week=1)
    conn.close()
    print(f"imported {len(p.lifts)} lifts from xlsx -> {db_path}")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="migrate")
    ap.add_argument("--db", default="sbs.db")
    ap.add_argument("--profile", default="profile.yaml")
    ap.add_argument("--state", default="state.yaml")
    ap.add_argument("--from-xlsx", dest="xlsx", default=None)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    if a.xlsx:
        migrate_from_xlsx(a.db, a.xlsx, force=a.force)
    else:
        migrate_from_yaml(a.db, a.profile, a.state, force=a.force)


if __name__ == "__main__":
    main()
