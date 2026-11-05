# A simulator: invents users whose real task times follow known patterns, then measures how much
# FocusFlow's predictions and plans improve on trusting the user's own guesses.
# Run:  python simulator/simulate.py        (writes simulator/results.md)
#
# IMPORTANT: everything here is SIMULATED. The patterns below are assumptions I chose (they are
# written out in results.md). The numbers show the engine learns patterns that exist; they do not
# prove how real people behave.
import datetime
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "backend"))

import engine
import scoring

NUM_USERS = 30
TRAIN_POOL = 160                       # sessions of history available per user
TEST_SIZE = 100                        # fresh sessions the predictors never saw
HISTORY_SIZES = [5, 10, 20, 40, 80, 160]
SCENARIOS_PER_USER = 200               # random "I have N minutes" situations per user
NOISE = 0.15                           # random day-to-day wobble (15%)

STUDY, GYM, CODING, CHORES = 0, 1, 2, 3
CATEGORY_WEIGHTS = [3, 1, 4, 2]        # how often each category shows up
TODAY = datetime.date(2026, 1, 1)


# ---------- the invented users ----------

def base_ratio(category, guessed):
    """How much longer than the guess a task really takes (1.0 = the guess is right)."""
    if category == STUDY:
        return 1.4                     # always underestimated by 40%
    if category == GYM:
        return 0.95                    # about right
    if category == CHORES:
        return 0.8                     # overestimated
    # Coding: short tasks are fine, long ones overrun a lot (the "size matters" pattern).
    if guessed <= 30:
        return 1.05
    if guessed >= 90:
        return 1.7
    return 1.05 + (1.7 - 1.05) * (guessed - 30) / 60


def make_user(rng, calibrated):
    # Each person differs a bit: their category ratios are scaled by 0.85..1.15.
    scales = [rng.uniform(0.85, 1.15) for _ in range(4)]
    return {"calibrated": calibrated, "scales": scales}


def real_minutes(rng, user, category, guessed):
    ratio = 1.0
    if not user["calibrated"]:
        ratio = base_ratio(category, guessed) * user["scales"][category]
    return max(1, round(guessed * ratio * rng.lognormvariate(0, NOISE)))


def make_sessions(rng, user, count):
    sessions = []
    for _ in range(count):
        category = rng.choices(range(4), weights=CATEGORY_WEIGHTS)[0]
        guessed = rng.randrange(10, 121, 5)
        sessions.append((category, guessed, real_minutes(rng, user, category, guessed)))
    return sessions


def mean(values):
    return sum(values) / len(values)


# ---------- experiment A: how wrong are the predicted minutes? ----------

def prediction_experiment(rng, user, results):
    pool = make_sessions(rng, user, TRAIN_POOL)
    test = make_sessions(rng, user, TEST_SIZE)
    test_tasks = [(c, g) for c, g, _ in test]

    raw_error = mean([abs(g - a) for _, g, a in test])
    for size in HISTORY_SIZES:
        predicted, model, _ = engine.predict_minutes(pool[:size], test_tasks)
        error = mean([abs(p - t[2]) for p, t in zip(predicted, test)])
        results["error"][size].append(error)
        results["raw_error"][size].append(raw_error)
        if size == TRAIN_POOL:
            results["models"][model] = results["models"].get(model, 0) + 1
    return pool


# ---------- experiment B: do the plans survive contact with reality? ----------

def plan_value(chosen, values, real, budget):
    """You work through the plan, most valuable first. A task only counts if it finishes
    before the time runs out; after the first one that does not fit, you are out of time."""
    order = sorted(chosen, key=values.__getitem__, reverse=True)
    used = 0
    done = 0.0
    for i in order:
        if used + real[i] > budget:
            break
        used = used + real[i]
        done = done + values[i]
    return done


def planning_experiment(rng, user, history, results):
    for _ in range(SCENARIOS_PER_USER):
        tasks = []
        for _ in range(8):
            category = rng.choices(range(4), weights=CATEGORY_WEIGHTS)[0]
            tasks.append((category, rng.randrange(15, 91, 5)))
        guessed = [g for _, g in tasks]
        budget = round(0.5 * sum(guessed))   # room for about half of everything

        values = []
        for _ in tasks:
            priority = rng.randrange(1, 6)
            days = rng.choice([None, None, 0, 1, 2, 5, 10])
            due = None if days is None else (TODAY + datetime.timedelta(days=days)).isoformat()
            values.append(scoring.task_value(priority, due, TODAY.isoformat()))
        real = [real_minutes(rng, user, c, g) for c, g in tasks]   # what will REALLY happen

        predicted, _, _ = engine.predict_minutes(history, tasks)
        plans = {
            "guess": engine.make_plan(guessed, values, budget),
            "focusflow": engine.make_plan([max(1, round(p)) for p in predicted], values, budget),
            "oracle": engine.make_plan(real, values, budget),    # cheating: knows the real times
        }
        for name in plans:
            chosen = plans[name]
            results["value"][name].append(plan_value(chosen, values, real, budget))
            results["overrun"][name].append(1 if sum([real[i] for i in chosen]) > budget else 0)


# ---------- run everything ----------

def run_population(calibrated):
    results = {
        "error": {s: [] for s in HISTORY_SIZES},
        "raw_error": {s: [] for s in HISTORY_SIZES},
        "models": {},
        "value": {"guess": [], "focusflow": [], "oracle": []},
        "overrun": {"guess": [], "focusflow": [], "oracle": []},
    }
    for seed in range(NUM_USERS):
        rng = random.Random(seed + (1000 if calibrated else 0))
        user = make_user(rng, calibrated)
        pool = prediction_experiment(rng, user, results)
        planning_experiment(rng, user, pool, results)
    return results


def report(title, results):
    lines = ["## " + title, ""]
    lines.append("**Prediction error** (average minutes off, on %d unseen tasks per user, %d users)" % (TEST_SIZE, NUM_USERS))
    lines.append("")
    lines.append("| Sessions of history | Your own guess | FocusFlow | Improvement |")
    lines.append("|---|---|---|---|")
    for size in HISTORY_SIZES:
        raw = mean(results["raw_error"][size])
        ours = mean(results["error"][size])
        lines.append("| %d%s | %.1f min | %.1f min | %.0f%% |" % (
            size, " (too few: uses category ratio)" if size < 10 else "", raw, ours, 100 * (raw - ours) / raw))
    lines.append("")

    lines.append("**Predictor chosen by the selector** (at %d sessions of history)" % TRAIN_POOL)
    lines.append("")
    for name in sorted(results["models"], key=results["models"].get, reverse=True):
        lines.append("- %s: %d of %d users" % (name, results["models"][name], NUM_USERS))
    lines.append("")

    lines.append("**Plans** (%d random situations per user, 8 tasks, time for about half of them; %d users)" % (SCENARIOS_PER_USER, NUM_USERS))
    lines.append("")
    lines.append("| Plan built from | Value actually completed | Share of the best possible | Plan overran the time |")
    lines.append("|---|---|---|---|")
    best = mean(results["value"]["oracle"])
    for name, label in [("guess", "your own guesses"), ("focusflow", "FocusFlow predictions"),
                        ("oracle", "the real times (impossible in practice)")]:
        lines.append("| %s | %.1f | %.0f%% | %.0f%% of the time |" % (
            label, mean(results["value"][name]), 100 * mean(results["value"][name]) / best,
            100 * mean(results["overrun"][name])))
    lines.append("")
    return lines


def main():
    out = ["# Simulation results", ""]
    out.append("All numbers come from **simulated** users (fixed random seeds, so the run is repeatable). "
               "The patterns are my assumptions, not measurements of real people:")
    out.append("")
    out.append("- study tasks really take 1.4x the guess; gym 0.95x; chores 0.8x;")
    out.append("- coding tasks guessed at 30 min or less take 1.05x, at 90 min or more 1.7x (in between: a straight line);")
    out.append("- each user scales those ratios by a random 0.85-1.15, and every task has +/-15% random wobble;")
    out.append("- the \"calibrated\" group guesses perfectly on average (ratio 1.0): a check that FocusFlow does no harm.")
    out.append("")
    out.append("The coding pattern (size matters) is one the KNN predictor is built to catch, so the simulation "
               "favours it. Treat the size of the gain as 'what is possible when such a pattern exists'.")
    out.append("")

    out.extend(report("Users who misjudge their time", run_population(False)))
    out.extend(report("Control: users whose guesses are already accurate", run_population(True)))

    text = "\n".join(out) + "\n"
    print(text)
    with open(os.path.join(HERE, "results.md"), "w", encoding="utf-8") as f:
        f.write(text)


if __name__ == "__main__":   # only when run directly, not when imported by seed_demo.py
    main()
