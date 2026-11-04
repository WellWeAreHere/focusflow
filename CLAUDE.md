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
- Task value (computed in Python, not C++): `priority * 10 + urgency`, urgency = 20 if due in <=1 day, 10 if <=3, else 0.

## Build and test (PowerShell, from `engine/`)
`.\build.ps1` runs `tests/test_engine.cpp`, then builds `build/focusflow.dll`.
Toolchain: g++ 14 via MSYS2 ucrt64, Python 3.11 (Microsoft Store build), Node. No CMake.
The DLL must be linked with `-static`, otherwise Python fails to load it (it needs `libwinpthread-1.dll`).

## Status
Done: C++ engine with tests, DLL bridge (smoke-tested from Python with ctypes), pushed to GitHub.
Next, in order:
1. `backend/engine.py`: ctypes wrapper (`predict_minutes`, `make_plan`) around the DLL.
2. SQLite: `tasks` and `sessions` (finished work: category, guessed, actual) tables.
3. FastAPI endpoints: add/list tasks, log a session, `POST /plan` with the minutes available. API tests.
4. One-page frontend (plain HTML + JS): add task, log a session, enter minutes, see the plan with reasons.
5. A simulator that generates realistic history, so we can report real numbers (error versus raw guesses).
6. Benchmark C++ against a Python version, add CI, README with screenshots, update the resume with the measured results.
Possible upgrade: split long tasks into chunks so partial work can be planned.

## Gotchas
- `g++ -o OUTPUT INPUT.cpp`: the output name comes after `-o`. Swapping them overwrites the source file (this happened once).
- Git: branch is `main`, remote `origin` is https://github.com/WellWeAreHere/focusflow. `git commit` needs `-m`.
- `C:\proj\taskmanager` is the user's older Python-only version of this idea. Reference only, do not modify.
