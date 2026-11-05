# Uses up the spare minutes of a plan.
#
# The knapsack (planner.cpp) only picks WHOLE tasks. It usually leaves some minutes over, because the
# tasks that were left out do not fit in the gap. Since a task can be worked on in pieces (partial
# progress), we can fill the gap with a slice of one of them: "do about 40% of this task".
#
# This is a plain greedy step on top of the knapsack, so it lives in Python, not in the C++ engine.

MIN_SLICE_MINUTES = 5   # a gap shorter than this is not worth starting anything in
MIN_SLICE_PERCENT = 5   # a slice smaller than this share of a task is not worth suggesting


def pick_partial(candidates, spare_minutes):
    """Choose which left-out task to work on in the spare minutes, and how much of it.

    candidates: one dict per task that was NOT chosen, with
        "index"        position of the task in the planner's lists
        "remaining"    minutes the rest of the task is expected to take
        "full"         expected minutes of the WHOLE task (float)
        "percent_done" share of the whole task already finished (0..99)
        "value"        how much the task is worth
    spare_minutes: whole minutes left after the chosen tasks.

    Returns None, or {"index", "minutes", "percent"}, where percent is the share of the WHOLE task
    to aim for (the same unit the "% finished" boxes use) and minutes is how long that takes.
    """
    if spare_minutes < MIN_SLICE_MINUTES:
        return None

    best = None
    best_density = -1.0
    for c in candidates:
        # How much of the whole task fits in the gap (rounded DOWN, so we never promise more than fits).
        left_percent = 100 - c["percent_done"]
        percent = min(left_percent, int(100 * spare_minutes / c["full"]))
        if percent < MIN_SLICE_PERCENT:
            continue
        # Best value per minute of work first: that is the most worthwhile way to spend the gap.
        density = c["value"] / c["remaining"]
        if density > best_density:   # strictly greater, so on a tie the earlier task wins
            best_density = density
            best = {"index": c["index"], "percent": percent,
                    "minutes": min(spare_minutes, max(1, round(c["full"] * percent / 100)))}
    return best
