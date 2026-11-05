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
FastAPI `main.py`), one-page frontend in `frontend/` (served by FastAPI), 42 API tests in `backend/test_api.py`.
Features beyond the original plan:
- Partial progress: `POST /tasks/{id}/sessions` takes minutes spent and % gained. Below 100% the task stays open;
  the sitting is stored as unfinished. History row = (guessed, spent * 100 / % gained), so the engine is unchanged.
  `/plan` only charges the remaining part of a half-done task.
- Spare-minute filling: `backend/fill.py` (Python, after the knapsack). The gap left by the whole tasks gets a slice of the left-out task with the
  best value per minute (percent of the WHOLE task, rounded down; min gap 5 min, min slice 5%). `/plan` returns it as `partial`; the UI shows a
  "part N%" row last in the plan. A slice does not count in `total_value`.
- Daily recurring tasks: templates in `recurring`; `db.spawn_recurring` makes today's copy lazily (no scheduler)
  whenever tasks are listed or planned. Missed days give one fresh copy; the older unfinished one is marked skipped.
Steps 5-6 are done too: `simulator/simulate.py` (simulated users; results in `simulator/results.md`),
`benchmark/` (pure-Python port + timings, checked equal to C++), `.github/workflows/ci.yml` (+ `engine/build.sh` for Linux),
`README.md` with a screenshot in `docs/`. The frontend layout was checked by screenshot (desktop and 500px wide).
Frontend (4 columns): add task + daily tasks | plan form + all tasks (not in plan) | "Today's plan" | "Working on" stopwatch.
Make plan moves the chosen tasks to the plan column; tasks drag between columns 2 and 3 and reorder within the plan, with a blue drop line (HTML5 drag and drop, plus arrow buttons);
one-line task rows; plan kept in localStorage. Stopwatch
(Start/Pause/Resume/Stop/Finish; Stop/Finish then ask "% of the task finished" and POST the session). Timer state is kept in
localStorage; its logic is in `frontend/timer.js`, tested with `node frontend/test_timer.js`. The whole click-through was
verified by driving headless Edge over the DevTools protocol (44 + 14 checks, drag events were synthetic, not a real mouse), but that script is not in the repo.
Quote only the SIMULATED numbers, and say they are simulated. In the control group (already-accurate guessers) FocusFlow does
not help and is slightly worse with under ~40 sessions of history: say that too.
Remaining ideas: show the user's own guess until there is enough history; push and confirm CI is green on GitHub (the Linux
build script was only tried on Windows); put the measured numbers on the resume.

Run the app (from `backend/`, after `engine\build.ps1`): `python -m uvicorn main:app --reload`, open http://127.0.0.1:8000.
API tests (from `backend/`): `python -m pytest -q`. The database is `backend/focusflow.db` (gitignored); if the schema in
`db.py` changes, delete that file, because `CREATE TABLE IF NOT EXISTS` does not alter existing tables.

## Gotchas
- `g++ -o OUTPUT INPUT.cpp`: the output name comes after `-o`. Swapping them overwrites the source file (this happened once).
- Git: branch is `main`, remote `origin` is https://github.com/WellWeAreHere/focusflow. `git commit` needs `-m`.
- `C:\proj\taskmanager` is the user's older Python-only version of this idea. Reference only, do not modify.
