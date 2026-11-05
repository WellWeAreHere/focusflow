# FocusFlow

A time-budgeted task planner. The user says "I have N minutes"; it picks the best set of tasks that fit.
It also learns how long the user *really* takes versus their own guesses, so plans stay realistic.
This is a resume project for internship applications, so the user must be able to explain every part.

## Working with the user
- 5th-sem student. Knows basic C++ (variables, arrays, loops, functions, structs, vectors). Does NOT yet know
  classes, templates, lambdas, or web frameworks. Explain every new concept the first time it appears, in plain words.
- Teach in small steps. Write plain-style code (structs + functions, no clever one-liners). Add comments that explain *why*.
- `learn/step1.cpp`..`step8.cpp` are the teaching programs that led to the engine. Reuse their style.
- Ask before deleting files (a deletion was declined once). The user runs their own git commits and pushes.
- Be honest about results. The sample data in tests is hand-built, so say so when quoting numbers.

## Architecture
```
Browser (plain HTML/JS)  ->  FastAPI (Python)  ->  C++ engine (focusflow.dll, called with ctypes)
```
- `engine/src/predictors.*`  raw guess, per-category ratio, KNN (weighted, k nearest, distance = category penalty + log-size gap)
- `engine/src/selector.*`    grades every predictor on the newest 30% of history (time order), picks the lowest error; ties keep the simpler one
- `engine/src/planner.*`     0/1 knapsack DP (2D table so the chosen tasks can be recovered)
- `engine/src/c_api.cpp`     `ff_predict` and `ff_plan`: flat arrays only, because Python cannot pass vectors/strings.
                             With fewer than 10 history rows it skips the comparison and uses the category ratio.
- `engine/old/`              earlier class-based version, kept untouched, not built
- Task value (computed in Python, `backend/scoring.py`, not C++): `priority * 10 + urgency`, urgency = `30 / (1 + days_left)`
  (overdue counts as due today, no deadline = 0), so the value rises smoothly as the deadline nears.

## Build and test (PowerShell, from `engine/`)
`.\build.ps1` runs `tests/test_engine.cpp`, then builds `build/focusflow.dll`.
Toolchain: g++ 14 via MSYS2 ucrt64, Python 3.11 (Microsoft Store build), Node. No CMake.
The DLL must be linked with `-static`, otherwise Python fails to load it (it needs `libwinpthread-1.dll`).

## Status
Done: C++ engine with tests, DLL bridge, `backend/` (ctypes wrapper `engine.py`, SQLite `db.py`, `scoring.py`,
FastAPI `main.py`), one-page frontend in `frontend/` (served by FastAPI), 31 API tests in `backend/test_api.py`.
Features beyond the original plan:
- Partial progress: `POST /tasks/{id}/sessions` takes minutes spent and % gained. Below 100% the task stays open;
  the sitting is stored as unfinished. History row = (guessed, spent * 100 / % gained), so the engine is unchanged.
  `/plan` only charges the remaining part of a half-done task.
- Daily recurring tasks: templates in `recurring`; `db.spawn_recurring` makes today's copy lazily (no scheduler)
  whenever tasks are listed or planned. Missed days give one fresh copy; the older unfinished one is marked skipped.
Next, in order:
5. A simulator that generates realistic history, so we can report real numbers (error versus raw guesses).
   The API has no "load history" endpoint; the simulator can call `db.add_session` directly.
6. Benchmark C++ against a Python version, add CI, README with screenshots, update the resume with the measured results.
The frontend layout has not been checked by eye yet (only the API and JS syntax were tested).

Run the app (from `backend/`, after `engine\build.ps1`): `python -m uvicorn main:app --reload`, open http://127.0.0.1:8000.
API tests (from `backend/`): `python -m pytest -q`. The database is `backend/focusflow.db` (gitignored); if the schema in
`db.py` changes, delete that file, because `CREATE TABLE IF NOT EXISTS` does not alter existing tables.

## Gotchas
- `g++ -o OUTPUT INPUT.cpp`: the output name comes after `-o`. Swapping them overwrites the source file (this happened once).
- Git: branch is `main`, remote `origin` is https://github.com/WellWeAreHere/focusflow. `git commit` needs `-m`.
- `C:\proj\taskmanager` is the user's older Python-only version of this idea. Reference only, do not modify.
