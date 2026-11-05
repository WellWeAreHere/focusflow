# How much is a task worth to the planner? The knapsack maximises the total of these values.
#
#   value = priority * 10 + urgency
#
# priority is the user's own 1..5 rating, so it contributes 10..50.
# urgency grows smoothly as the deadline gets closer (and is 0 when there is no deadline).
import datetime

# The most urgency a task can get (due today or overdue). 30 is a bit less than the gap
# between priority 1 and priority 4, so urgency can lift a task a few priority levels
# but cannot let a priority-1 task beat a priority-5 one.
URGENCY_MAX = 30


def days_left(due_date, today=None):
    """Whole days from today until the deadline. Negative if it is already overdue.
    Dates are text like "2026-11-10". Raises ValueError if the text is not a date."""
    if today is None:
        today = datetime.date.today().isoformat()
    return (datetime.date.fromisoformat(due_date) - datetime.date.fromisoformat(today)).days


def urgency(due_date, today=None):
    """0 with no deadline; otherwise URGENCY_MAX / (1 + days left).

    due today or overdue -> 30, tomorrow -> 15, in 2 days -> 10, in 5 days -> 5, in 30 days -> about 1.
    It drops fast at first and flattens out: the difference between "today" and "tomorrow"
    matters much more than between "in 20 days" and "in 21 days".
    """
    if due_date is None:
        return 0.0
    left = max(0, days_left(due_date, today))  # overdue counts the same as due today
    return URGENCY_MAX / (1 + left)


def task_value(priority, due_date, today=None):
    return priority * 10 + urgency(due_date, today)


# Quick check when run directly:  python backend/scoring.py
if __name__ == "__main__":
    today = "2026-11-05"
    print("days left -> urgency")
    for d in ["2026-11-01", "2026-11-05", "2026-11-06", "2026-11-07", "2026-11-10", "2026-12-05", None]:
        label = "no deadline" if d is None else str(days_left(d, today)) + " days"
        print(f"  {label:>12} -> {urgency(d, today):5.1f}")

    # Closer deadline must never lower the value.
    values = [task_value(3, "2026-11-%02d" % day, today) for day in range(5, 31)]
    print("never decreases as the deadline nears:", all(a >= b for a, b in zip(values, values[1:])))

    print("priority 3 due today:", task_value(3, "2026-11-05", today),
          "| priority 5 no deadline:", task_value(5, None, today),
          "| priority 3 due in 10 days:", round(task_value(3, "2026-11-15", today), 1))
