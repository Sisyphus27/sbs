"""CLI entry: init / week / next / show."""
import argparse, os, sys
from .data import io as dio
from .program import initial_state, advance_lift
from .importer import import_profile
from .view.html import render_week_html, parse_log_json
from .view.terminal import render_week_text, render_show_text


def _load(args):
    p = dio.load_profile(args.profile)
    if not os.path.exists(args.state):
        s = initial_state(p); dio.save_state(s, args.state)
    else:
        s = dio.load_state(args.state)
    return p, s


def cmd_init(args):
    p = import_profile(args.from_path, sheet=args.sheet)
    dio.save_profile(p, args.profile)
    s = initial_state(p); dio.save_state(s, args.state)
    print(f"profile -> {args.profile}  ({len(p.lifts)} lifts, {p.days_per_week} days)")
    print(f"state  -> {args.state}")
    print("Edit profile.yaml to taste (day, intensity, reps, repout).")


def cmd_week(args):
    p, s = _load(args)
    out = args.out or f"week-{s.week}.html"
    html = render_week_html(p, s, week=s.week)
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(render_week_text(p, s, week=s.week))
    print(f"\n-> open {out} on your phone, fill last-set reps, tap Export results.")


def cmd_next(args):
    p, s = _load(args)
    with open(args.log, "r", encoding="utf-8") as f:
        log = parse_log_json(f.read())
    logs = log["logs"]
    for l in p.lifts:
        advance_lift(p, l, s.lifts[l.name], logs.get(l.name), week=s.week)
    s.week += 1
    dio.save_state(s, args.state)
    out = args.out or f"week-{s.week}.html"
    html = render_week_html(p, s, week=s.week)
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"advanced to week {s.week} -> {out}")


def cmd_show(args):
    p, s = _load(args)
    print(render_show_text(p, s))


def build_parser():
    ap = argparse.ArgumentParser(prog="sbs")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--profile", default="profile.yaml")
    common.add_argument("--state", default="state.yaml")
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("init", parents=[common])
    a.add_argument("--from", dest="from_path", required=True)
    a.add_argument("--sheet", default="4x")
    a.set_defaults(func=cmd_init)

    a = sub.add_parser("week", parents=[common])
    a.add_argument("--out", default=None)
    a.set_defaults(func=cmd_week)

    a = sub.add_parser("next", parents=[common])
    a.add_argument("log")
    a.add_argument("--out", default=None)
    a.set_defaults(func=cmd_next)

    a = sub.add_parser("show", parents=[common])
    a.set_defaults(func=cmd_show)
    return ap


def run(argv=None):
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    run()
