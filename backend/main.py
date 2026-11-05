# The web API. The browser will send HTTP requests to the functions below.
#
# Vocabulary:
#   HTTP request  = a message from the browser: a METHOD, a URL path, and sometimes data.
#                   GET  = "give me something"      POST = "here is new data, store it"
#   endpoint      = one URL + method pair that we answer, e.g.  POST /tasks
#   JSON          = text format for data, like {"name": "gym", "priority": 3}
#   FastAPI       = a library that lets us write each endpoint as an ordinary Python function.
#                   It reads the request, calls our function, and turns the return value into JSON.
import datetime
import os
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import db
import engine   # loads focusflow.dll once, here, when the server starts
import scoring

app = FastAPI(title="FocusFlow")

# Which database file to use. A variable (not hard-coded inside the functions) so tests can
# point it at a throwaway file.
DB_FILE = db.DB_PATH


def get_conn():
    """Give an endpoint its own database connection, and close it when the request ends.

    `Depends(get_conn)` on an endpoint parameter means "FastAPI, call get_conn first and pass
    me the result". `yield` hands out the connection, then the code after it (the `finally`)
    runs once the endpoint has finished, so we never leak open connections.
    A new connection per request is needed because FastAPI runs requests on different threads
    and a SQLite connection may not be shared between threads.
    """
    conn = db.connect(DB_FILE)
    try:
        yield conn
    finally:
        conn.close()


# --- Request shapes ---------------------------------------------------------------------------
# A "model" describes the data we expect in a request, like a struct plus rules. Each line is
# `field_name: type = rules`. (A `class` is how Python defines a struct-like type; for now treat
# `class X(BaseModel)` as "struct X whose fields are checked automatically".)
# If a request breaks a rule, FastAPI answers with error 422 and never calls our function,
# so bad data (0 minutes, priority 9, a date like "tomorrow") is stopped at the door.
class TaskIn(BaseModel):
    name: str = Field(min_length=1)
    category: str = Field(min_length=1)
    guessed_minutes: int = Field(gt=0)            # gt = greater than
    priority: int = Field(ge=1, le=5)             # ge = greater or equal, le = less or equal
    due_date: Optional[datetime.date] = None      # "2026-11-10" is accepted; anything else is rejected


class RecurringIn(BaseModel):
    name: str = Field(min_length=1)
    category: str = Field(min_length=1)
    guessed_minutes: int = Field(gt=0)
    priority: int = Field(ge=1, le=5)


class SessionIn(BaseModel):
    minutes_spent: int = Field(gt=0)
    percent_gained: int = Field(ge=1, le=100)     # how much of the WHOLE task this sitting finished


class PlanIn(BaseModel):
    minutes: int = Field(gt=0)                    # "I have N minutes"


# --- Endpoints --------------------------------------------------------------------------------
# `@app.post("/tasks")` is a decorator: a line above a function that registers it with FastAPI
# ("when a POST arrives at /tasks, run this function"). It does not change what the function does.

@app.post("/tasks", status_code=201)   # 201 = "Created", the conventional answer to a successful POST
def create_task(task: TaskIn, conn=Depends(get_conn)):
    task_id = db.add_task(conn, task.name, task.category, task.guessed_minutes, task.priority,
                          task.due_date.isoformat() if task.due_date else None)
    return {"id": task_id}


@app.get("/tasks")
def list_tasks(conn=Depends(get_conn)):
    # Make today's copies of the daily tasks first (safe to repeat: it never makes duplicates).
    db.spawn_recurring(conn)

    today = datetime.date.today().isoformat()
    tasks = []
    for row in db.list_open_tasks(conn):
        tasks.append({
            "id": row["id"],
            "name": row["name"],
            "category": row["category"],
            "guessed_minutes": row["guessed_minutes"],
            "priority": row["priority"],
            "due_date": row["due_date"],
            "percent_done": row["percent_done"],
            "spent_minutes": row["spent_minutes"],
            "recurring": row["template_id"] is not None,
            "value": scoring.task_value(row["priority"], row["due_date"], today),
        })
    return tasks


# `{task_id}` in the path is a variable part of the URL: POST /tasks/7/sessions gives task_id = 7.
# FastAPI converts it to an int for us (and answers 422 if it is not a number).
@app.post("/tasks/{task_id}/sessions")
def add_session(task_id: int, session: SessionIn, conn=Depends(get_conn)):
    """Log one sitting: "I worked N minutes and finished P% of this task".
    Below 100% the task stays open for next time, and the sitting is recorded as unfinished."""
    try:
        percent_done, finished = db.log_session(conn, task_id, session.minutes_spent, session.percent_gained)
    except ValueError as e:
        # 404 = "not found". db.log_session only fails here when there is no open task with this id
        # (the numbers were already checked by SessionIn).
        raise HTTPException(status_code=404, detail=str(e))
    return {"task_id": task_id, "percent_done": percent_done, "finished": finished}


# A "recurring" task is a template. Each day one real task is made from it (see db.spawn_recurring).
@app.post("/recurring", status_code=201)
def create_recurring(template: RecurringIn, conn=Depends(get_conn)):
    template_id = db.add_recurring(conn, template.name, template.category,
                                   template.guessed_minutes, template.priority)
    db.spawn_recurring(conn)   # so today's copy exists right away, not only from tomorrow
    return {"id": template_id}


@app.get("/recurring")
def list_recurring(conn=Depends(get_conn)):
    return [dict(row) for row in db.list_recurring(conn)]   # dict(row) turns a database row into a plain dict


# This is a POST, not a DELETE, because nothing is deleted: the template is switched off and
# the copies already made (and their history) stay.
@app.post("/recurring/{template_id}/stop")
def stop_recurring(template_id: int, conn=Depends(get_conn)):
    if not db.stop_recurring(conn, template_id):
        raise HTTPException(status_code=404, detail="no recurring task with that id")
    return {"id": template_id, "active": False}


def due_text(due_date, today):
    """'due today', 'due in 3 days', ... for the reasons shown to the user."""
    if due_date is None:
        return "no deadline"
    left = scoring.days_left(due_date, today)
    if left < 0:
        return "overdue"
    if left == 0:
        return "due today"
    return "due in %d day%s" % (left, "" if left == 1 else "s")


@app.post("/plan")
def create_plan(request: PlanIn, conn=Depends(get_conn)):
    """The main feature: "I have N minutes" -> the best set of tasks that fit, with reasons."""
    db.spawn_recurring(conn)
    today = datetime.date.today().isoformat()
    tasks = db.list_open_tasks(conn)

    # 1. Predict how long each task will REALLY take (C++ selector + predictors).
    history = db.history_for_engine(conn)
    task_inputs = [(t["category_id"], t["guessed_minutes"]) for t in tasks]
    try:
        predicted_full, model, avg_error = engine.predict_minutes(history, task_inputs)

        # 2. Cost and value of each task for the knapsack. Only the REMAINING part of a
        #    half-done task costs time. Round to whole minutes (the table has one column per
        #    minute), but never 0, or the task would be free and always chosen.
        minutes = []
        values = []
        for t, full in zip(tasks, predicted_full):
            remaining = full * (100 - t["percent_done"]) / 100
            minutes.append(max(1, round(remaining)))
            values.append(scoring.task_value(t["priority"], t["due_date"], today))

        # 3. Pick the best set that fits (C++ knapsack).
        chosen = engine.make_plan(minutes, values, request.minutes)
    except ValueError as e:   # the DLL rejected its arguments: our bug, not the user's
        raise HTTPException(status_code=500, detail=str(e))

    # 4. Build the answer. The knapsack returns positions; look the tasks up again.
    chosen_set = set(chosen)
    plan = []
    left_out = []
    for i, t in enumerate(tasks):
        if i not in chosen_set:
            left_out.append({"id": t["id"], "name": t["name"], "predicted_minutes": minutes[i], "value": values[i]})
            continue
        reason = "priority %d, %s; expected %d min" % (t["priority"], due_text(t["due_date"], today), minutes[i])
        if t["percent_done"] > 0:
            reason += " for the remaining %d%%" % (100 - t["percent_done"])
        reason += " (you guessed %d min for the whole task)" % t["guessed_minutes"]
        plan.append({
            "id": t["id"],
            "name": t["name"],
            "category": t["category"],
            "guessed_minutes": t["guessed_minutes"],
            "predicted_minutes": minutes[i],
            "percent_done": t["percent_done"],
            "value": values[i],
            "reason": reason,
        })
    plan.sort(key=lambda p: p["value"], reverse=True)   # most valuable first

    return {
        "minutes_available": request.minutes,
        "minutes_used": sum(p["predicted_minutes"] for p in plan),
        "total_value": sum(p["value"] for p in plan),
        "model": model,           # which predictor the selector trusted
        "avg_error": avg_error,   # its average error in minutes, or None if history was too short
        "plan": plan,
        "left_out": left_out,
    }


# --- The web page -----------------------------------------------------------------------------
# Serve the files in ../frontend (index.html, style.css, app.js) from the same server, so the
# page and the API live at one address and the browser needs no special permission to call us.
# This goes LAST: a mount at "/" matches every path, so the API routes above must be checked first.
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend")
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
