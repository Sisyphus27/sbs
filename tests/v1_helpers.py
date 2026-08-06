from webapp import repo


def insert_v1_slot(conn, *, name, mode, day, sort_order, sets,
                   load_model="barbell", slot_id=None, max_seed=None,
                   start_weight=None, lift_kind=None, intensity=None, reps=None,
                   repout=None, increment=None, bodyweight_pct=0.0, tm=None,
                   weight=None, target=None, streak=0, est1rm=None,
                   reseeded_cycle=0):
    exercise_id = conn.execute(
        "INSERT INTO exercise (name, load_model) VALUES (?, ?)",
        (name, load_model),
    ).lastrowid
    columns = [
        "exercise_id", "day", "sort_order", "mode", "lift_kind", "sets",
        "reps", "repout", "intensity", "max_seed", "start_weight",
        "increment", "bodyweight_pct",
    ]
    values = [
        exercise_id, day, sort_order, mode, lift_kind, sets, reps, repout,
        intensity, max_seed, start_weight, increment, bodyweight_pct,
    ]
    if slot_id is not None:
        columns.insert(0, "id")
        values.insert(0, slot_id)
    placeholders = ", ".join("?" for _ in columns)
    inserted_slot_id = conn.execute(
        f"INSERT INTO program_slot ({', '.join(columns)}) VALUES ({placeholders})",
        values,
    ).lastrowid
    conn.execute(
        "INSERT INTO strength_state "
        "(slot_id, mode, tm, weight, target, streak, est1rm, reseeded_cycle) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            inserted_slot_id,
            mode,
            tm,
            weight,
            target,
            streak,
            est1rm,
            reseeded_cycle,
        ),
    )
    return inserted_slot_id


def mirror_legacy_lift(conn, lift_id):
    """Give a legacy test lift the v1 slot/state pair used by migrated routes."""
    lift = repo.get_lift(conn, lift_id)
    state = repo.get_lift_state(conn, lift_id)
    slot_id = insert_v1_slot(
        conn,
        slot_id=lift_id,
        name=lift["name"],
        load_model=lift["load_model"],
        mode=lift["mode"],
        day=lift["day"],
        sort_order=lift["sort_order"],
        sets=lift["sets"],
        max_seed=lift["max"],
        start_weight=lift["start"],
        lift_kind=lift["lift_kind"],
        intensity=lift["intensity"],
        reps=lift["reps"],
        repout=lift["repout"],
        increment=lift["incr"],
        bodyweight_pct=lift["bodyweight_pct"],
        tm=state["tm"],
        weight=state["weight"],
        target=state["target"],
        streak=state["streak"],
        est1rm=state["est1rm"],
        reseeded_cycle=state["reseeded_cycle"],
    )
    conn.commit()
    return slot_id
