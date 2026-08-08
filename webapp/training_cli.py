"""CLI adapter for the SQLite draft-set command."""

import argparse
from datetime import date, datetime, timezone

from . import repo
from .backup import make_snapshot_before_advance
from .db import connect
from .services.training import TrainingInputError, finalize_week, save_draft_set


def _iso_date(raw: str) -> str:
    try:
        return date.fromisoformat(raw).isoformat()
    except ValueError as error:
        raise argparse.ArgumentTypeError("date must use YYYY-MM-DD") from error


def cmd_save_set(args) -> None:
    conn = connect(args.db)
    try:
        metadata = {
            name: getattr(args, name)
            for name in ("training_date", "bodyweight_kg")
            if hasattr(args, name)
        }
        save_draft_set(
            conn,
            expected_week=args.expected_week,
            slot_id=args.slot_id,
            set_number=args.set_number,
            actual_added_weight=args.actual_added_weight,
            reps=args.reps,
            warmup=args.warmup,
            drives_progression=args.drives_progression,
            e1rm_qualified=args.e1rm_qualified,
            **metadata,
        )
    except TrainingInputError as error:
        raise SystemExit(str(error)) from error
    finally:
        conn.close()
    print(
        f"saved week {args.expected_week} slot {args.slot_id} "
        f"set {args.set_number}"
    )


def cmd_finalize_week(args) -> None:
    conn = connect(args.db)
    try:
        if repo.get_settings(conn)["week"] != args.expected_week:
            raise SystemExit("stale week")
        snapshot_before_advance = make_snapshot_before_advance(
            args.db,
            dest_dir=args.backup_dir,
            week=args.expected_week,
            timestamp=lambda: datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S"),
        )

        new_week = finalize_week(
            conn,
            expected_week=args.expected_week,
            before_advance=snapshot_before_advance,
        )
    except TrainingInputError as error:
        raise SystemExit(str(error)) from error
    finally:
        conn.close()
    print(f"finalized week {args.expected_week} to week {new_week}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m webapp.training_cli")
    subparsers = parser.add_subparsers(dest="command", required=True)
    save_set_parser = subparsers.add_parser("save-set")
    save_set_parser.add_argument("--db", required=True)
    save_set_parser.add_argument("--expected-week", required=True, type=int)
    save_set_parser.add_argument("--slot-id", required=True, type=int)
    save_set_parser.add_argument("--set-number", required=True, type=int)
    save_set_parser.add_argument("--actual-added-weight", required=True, type=float)
    save_set_parser.add_argument("--reps", required=True, type=int)
    save_set_parser.add_argument("--warmup", action="store_true")
    save_set_parser.add_argument("--drives-progression", action="store_true")
    save_set_parser.add_argument("--e1rm-qualified", action="store_true")

    training_date = save_set_parser.add_mutually_exclusive_group()
    training_date.add_argument(
        "--training-date", type=_iso_date, default=argparse.SUPPRESS
    )
    training_date.add_argument(
        "--clear-training-date",
        action="store_const",
        const=None,
        dest="training_date",
        default=argparse.SUPPRESS,
    )
    bodyweight = save_set_parser.add_mutually_exclusive_group()
    bodyweight.add_argument(
        "--bodyweight-kg", type=float, default=argparse.SUPPRESS
    )
    bodyweight.add_argument(
        "--clear-bodyweight",
        action="store_const",
        const=None,
        dest="bodyweight_kg",
        default=argparse.SUPPRESS,
    )
    save_set_parser.set_defaults(func=cmd_save_set)

    finalize_parser = subparsers.add_parser("finalize-week")
    finalize_parser.add_argument("--db", required=True)
    finalize_parser.add_argument("--backup-dir", required=True)
    finalize_parser.add_argument("--expected-week", required=True, type=int)
    finalize_parser.set_defaults(func=cmd_finalize_week)
    return parser


def run(argv=None) -> None:
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    run()
