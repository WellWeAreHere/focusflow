# Proves the Python port gives the same answers as the C++ engine, so the speed comparison is fair.
# Run from the benchmark folder:  python -m pytest -q
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))

import engine        # the C++ engine, through ctypes
import py_engine     # the Python port


def random_history(rng, n):
    return [(rng.randrange(4), rng.randrange(10, 121, 5), 0) for _ in range(n)]


def with_actuals(rng, rows):
    # Real time = guess times a ratio that depends on the category, plus noise, rounded to whole minutes.
    ratios = [1.0, 1.4, 0.8, 1.7]
    return [(c, g, max(1, round(g * ratios[c] * rng.uniform(0.85, 1.15)))) for c, g, _ in rows]


def test_predictions_match():
    rng = random.Random(1)
    for n in [0, 3, 9, 10, 11, 25, 60, 150]:
        history = with_actuals(rng, random_history(rng, n))
        tasks = [(rng.randrange(5), rng.randrange(5, 130, 5)) for _ in range(12)]   # category 4 is unseen

        cpp_minutes, cpp_model, cpp_error = engine.predict_minutes(history, tasks)
        py_minutes, py_model, py_error = py_engine.predict_minutes(history, tasks)

        assert cpp_model == py_model, "history size %d" % n
        if cpp_error is None:
            assert py_error is None
        else:
            assert abs(cpp_error - py_error) < 1e-9
        for a, b in zip(cpp_minutes, py_minutes):
            assert abs(a - b) < 1e-9


def test_plans_match():
    rng = random.Random(2)
    for _ in range(200):
        n = rng.randrange(0, 15)
        minutes = [rng.randrange(1, 90) for _ in range(n)]
        values = [float(rng.randrange(10, 80)) for _ in range(n)]
        budget = rng.randrange(1, 300)
        assert engine.make_plan(minutes, values, budget) == py_engine.make_plan(minutes, values, budget)
