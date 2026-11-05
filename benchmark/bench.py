# Times the C++ engine (called from Python through ctypes, exactly as the web app calls it)
# against the pure-Python port, on the same inputs.
# Run:  python benchmark/bench.py        (writes benchmark/results.md)
#
# What is measured: the full call from Python, including copying lists into C arrays and back.
# That is the honest number for this app, since the app always goes through that bridge.
import os
import random
import statistics
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "backend"))
sys.path.insert(0, HERE)

import engine
import py_engine


def make_history(rng, n):
    ratios = [1.0, 1.4, 0.8, 1.7]
    rows = []
    for _ in range(n):
        c = rng.randrange(4)
        g = rng.randrange(10, 121, 5)
        rows.append((c, g, max(1, round(g * ratios[c] * rng.uniform(0.85, 1.15)))))
    return rows


def median_seconds(function, repeats, *arguments):
    # `*arguments` collects all the extra values passed after `repeats`; `function(*arguments)`
    # then spreads them back out as the call's arguments. So median_seconds(f, 5, a, b) times f(a, b).
    times = []
    for _ in range(repeats):
        start = time.perf_counter()
        function(*arguments)
        times.append(time.perf_counter() - start)
    return statistics.median(times)


def fmt(seconds):
    if seconds < 1e-3:
        return "%.0f us" % (seconds * 1e6)
    return "%.1f ms" % (seconds * 1e3)


def main():
    rng = random.Random(0)
    lines = []
    lines.append("| Operation | Python | C++ via ctypes | Speed-up |")
    lines.append("|---|---|---|---|")

    # Prediction: the selector grades 6 predictors on the newest 30% of history, then predicts 20 tasks.
    tasks = [(rng.randrange(4), rng.randrange(10, 121, 5)) for _ in range(20)]
    for n in [100, 500, 2000]:
        history = make_history(rng, n)
        repeats = 3 if n >= 2000 else 7
        py = median_seconds(py_engine.predict_minutes, repeats, history, tasks)
        cpp = median_seconds(engine.predict_minutes, 21, history, tasks)
        lines.append("| predict, %d history rows, 20 tasks | %s | %s | %.0fx |" % (n, fmt(py), fmt(cpp), py / cpp))

    # Planning: 0/1 knapsack over (tasks x minutes) cells.
    for n_tasks, budget in [(50, 480), (200, 480), (500, 1440)]:
        minutes = [rng.randrange(5, 120) for _ in range(n_tasks)]
        values = [float(rng.randrange(10, 80)) for _ in range(n_tasks)]
        py = median_seconds(py_engine.make_plan, 5, minutes, values, budget)
        cpp = median_seconds(engine.make_plan, 21, minutes, values, budget)
        lines.append("| plan, %d tasks, %d-minute budget | %s | %s | %.0fx |" % (n_tasks, budget, fmt(py), fmt(cpp), py / cpp))

    table = "\n".join(lines)
    print(table)

    with open(os.path.join(HERE, "results.md"), "w", encoding="utf-8") as f:
        f.write("# Benchmark: C++ engine vs pure-Python port\n\n")
        f.write("Median of repeated runs on one machine (Windows 11, Python 3.11, g++ 14 -O2). ")
        f.write("Both versions produce identical answers (see `test_equivalence.py`). ")
        f.write("The C++ column includes the cost of the ctypes bridge. Numbers vary by machine.\n\n")
        f.write(table + "\n")


main()
