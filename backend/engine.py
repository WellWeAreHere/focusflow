# Python side of the "bridge": loads focusflow.dll and wraps its two C functions
# in normal-looking Python functions.
#
# ctypes is a module that comes with Python. It can open a DLL and call the
# plain C functions inside it. The catch: C needs to know the exact type of every
# argument (int, double, pointer to an array...), and ctypes cannot guess them.
# So below we tell it the types once, and after that calling is easy.
import ctypes
import os

# Find the DLL relative to this file, so it works no matter where Python is started from.
DLL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "engine", "build", "focusflow.dll")
_dll = ctypes.CDLL(DLL_PATH)

# --- Describe the C functions to ctypes -------------------------------------------------------
# POINTER(c_int) means "address of the first int of an array" (C's `const int*`).
_int_p = ctypes.POINTER(ctypes.c_int)
_double_p = ctypes.POINTER(ctypes.c_double)

# int ff_predict(hist_cat, hist_guessed, hist_actual, n_hist,
#                task_cat, task_guessed, n_tasks,
#                out_minutes, out_model, out_model_len, out_error)
_dll.ff_predict.argtypes = [
    _int_p, _double_p, _double_p, ctypes.c_int,
    _int_p, _double_p, ctypes.c_int,
    _double_p, ctypes.c_char_p, ctypes.c_int, _double_p,
]
_dll.ff_predict.restype = ctypes.c_int

# int ff_plan(minutes, values, n, budget, out_chosen)
_dll.ff_plan.argtypes = [_int_p, _double_p, ctypes.c_int, ctypes.c_int, _int_p]
_dll.ff_plan.restype = ctypes.c_int


# A Python list is not a C array. This builds a C array of `n` ints/doubles from a list.
# (ctypes.c_int * 3) is "the type: array of 3 ints"; calling it with values fills it.
def _int_array(values):
    return (ctypes.c_int * len(values))(*values)


def _double_array(values):
    return (ctypes.c_double * len(values))(*values)


def predict_minutes(history, tasks):
    """Predict the real minutes each new task will take.

    history: list of (category_id, guessed, actual), oldest first.
    tasks:   list of (category_id, guessed).
    Returns (minutes_list, model_name, avg_error). avg_error is None if the
    history was too short to compare predictors.
    """
    n_hist = len(history)
    n_tasks = len(tasks)

    hist_cat = _int_array([h[0] for h in history])
    hist_guessed = _double_array([h[1] for h in history])
    hist_actual = _double_array([h[2] for h in history])
    task_cat = _int_array([t[0] for t in tasks])
    task_guessed = _double_array([t[1] for t in tasks])

    # Empty boxes that C fills in for us ("out" parameters).
    out_minutes = (ctypes.c_double * n_tasks)()
    out_model = ctypes.create_string_buffer(128)  # room for the predictor's name
    out_error = ctypes.c_double()

    # byref(x) passes the address of x, so C can write its answer into it.
    result = _dll.ff_predict(
        hist_cat, hist_guessed, hist_actual, n_hist,
        task_cat, task_guessed, n_tasks,
        out_minutes, out_model, len(out_model), ctypes.byref(out_error),
    )
    if result != 0:
        raise ValueError("ff_predict rejected its arguments")

    error = out_error.value
    if error < 0:  # C uses -1 for "not tested"
        error = None
    return list(out_minutes), out_model.value.decode("utf-8"), error


def make_plan(minutes, values, budget):
    """Pick the best set of tasks that fits in `budget` minutes.

    minutes: whole minutes each task takes. values: how much each task is worth.
    Returns the positions (indexes) of the chosen tasks.
    """
    n = len(minutes)
    out_chosen = (ctypes.c_int * n)()
    count = _dll.ff_plan(_int_array(minutes), _double_array(values), n, budget, out_chosen)
    if count < 0:
        raise ValueError("ff_plan rejected its arguments")
    return list(out_chosen)[:count]


# Quick check when run directly:  python backend/engine.py
if __name__ == "__main__":
    # Plan: 60 minutes. Best is tasks 0 and 2 (30+30 min, value 100+90) rather than task 1 alone.
    print("plan:", make_plan([30, 60, 30], [100, 150, 90], 60))
    # Short history (<10 rows) so it falls back to the category ratio.
    hist = [(0, 30, 45), (0, 20, 30), (1, 60, 60)]
    print("predict:", predict_minutes(hist, [(0, 40), (1, 10)]))
