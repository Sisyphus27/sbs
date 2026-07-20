"""Working-weight seam: the single translation point from stored added weight
to the working weight fed to all engine math. See ADR 0004.

Every call site that feeds estimate_1rm / tonnage / t2_next-reset MUST pass
through here — never a raw .weight / .start / history.weight. Enforced by
behavior-guard tests (Task 16).
"""


def working_weight(added: float, bodyweight: float, bodyweight_pct: float) -> float:
    """added + bodyweight × bodyweight_pct.

    bodyweight_pct == 0.0 for an ordinary lift, so this returns ``added``
    unchanged. For a bodyweight lift the bodyweight term is added back in.
    """
    return added + bodyweight * bodyweight_pct
