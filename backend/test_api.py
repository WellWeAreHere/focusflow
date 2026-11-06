# API tests. Run from the backend folder:  python -m pytest -q
#
# pytest finds every function named test_* and runs it; a test fails if an `assert` is false
# or the function raises an error. TestClient pretends to be a browser and calls our API
# in-process, so no server needs to be started.
import datetime
import threading

import pytest
from fastapi.testclient import TestClient

import main


@pytest.fixture
def client(tmp_path, monkeypatch):
    """A fresh, empty database for every test, so tests cannot affect each other.
    (A fixture is a helper pytest runs for you; tests ask for it by naming it as a parameter.)"""
    monkeypatch.setattr(main, "DB_FILE", str(tmp_path / "test.db"))
    return TestClient(main.app)


def make_task(client, **changes):
    body = {"name": "write report", "category": "coding", "guessed_minutes": 60, "priority": 3}
    body.update(changes)
    return client.post("/tasks", json=body)


def test_add_then_list_task(client):
    response = make_task(client, due_date="2026-11-10")
    assert response.status_code == 201
    assert response.json()["id"] == 1

    tasks = client.get("/tasks").json()
    assert len(tasks) == 1
    assert tasks[0]["name"] == "write report"
    assert tasks[0]["category"] == "coding"
    assert tasks[0]["percent_done"] == 0
    assert tasks[0]["due_date"] == "2026-11-10"


def test_list_is_empty_at_start(client):
    assert client.get("/tasks").json() == []


@pytest.mark.parametrize("changes", [
    {"guessed_minutes": 0},          # no zero-minute tasks
    {"guessed_minutes": -5},
    {"priority": 0},
    {"priority": 6},
    {"name": ""},
    {"category": ""},
    {"due_date": "tomorrow"},        # must be a real date
    {"due_date": "2026-13-45"},
])
def test_bad_task_is_rejected(client, changes):
    assert make_task(client, **changes).status_code == 422
    assert client.get("/tasks").json() == []   # and nothing was stored


def test_closer_deadline_has_higher_value(client):
    today = datetime.date.today()
    make_task(client, name="far", due_date=(today + datetime.timedelta(days=20)).isoformat())
    make_task(client, name="near", due_date=(today + datetime.timedelta(days=1)).isoformat())
    make_task(client, name="none")
    by_name = {t["name"]: t["value"] for t in client.get("/tasks").json()}
    assert by_name["near"] > by_name["far"] > by_name["none"]


# --- sessions (partial progress) ---------------------------------------------------------------

def test_partial_session_keeps_task_open(client):
    task_id = make_task(client).json()["id"]
    response = client.post("/tasks/%d/sessions" % task_id, json={"minutes_spent": 40, "percent_gained": 50})
    assert response.status_code == 200
    assert response.json() == {"task_id": task_id, "percent_done": 50, "finished": False}

    task = client.get("/tasks").json()[0]          # still there, remembering its progress
    assert task["percent_done"] == 50
    assert task["spent_minutes"] == 40


def test_finishing_session_closes_task(client):
    task_id = make_task(client).json()["id"]
    client.post("/tasks/%d/sessions" % task_id, json={"minutes_spent": 40, "percent_gained": 50})
    response = client.post("/tasks/%d/sessions" % task_id, json={"minutes_spent": 30, "percent_gained": 50})
    assert response.json()["finished"] is True
    assert client.get("/tasks").json() == []


def test_session_on_missing_task_is_404(client):
    response = client.post("/tasks/999/sessions", json={"minutes_spent": 10, "percent_gained": 10})
    assert response.status_code == 404


@pytest.mark.parametrize("body", [
    {"minutes_spent": 0, "percent_gained": 50},
    {"minutes_spent": 10, "percent_gained": 0},
    {"minutes_spent": 10, "percent_gained": 101},
])
def test_bad_session_is_rejected(client, body):
    task_id = make_task(client).json()["id"]
    assert client.post("/tasks/%d/sessions" % task_id, json=body).status_code == 422


# --- /plan -------------------------------------------------------------------------------------

def days_from_now(n):
    return (datetime.date.today() + datetime.timedelta(days=n)).isoformat()


def add_abc(client):
    """A: priority 3, due today, 40 min -> value 60.  B: priority 5, no deadline, 30 min -> 50.
    C: priority 2, due in 5 days, 30 min -> 25."""
    a = make_task(client, name="A", priority=3, guessed_minutes=40, due_date=days_from_now(0)).json()["id"]
    make_task(client, name="B", priority=5, guessed_minutes=30)
    make_task(client, name="C", priority=2, guessed_minutes=30, due_date=days_from_now(5))
    return a


def names(plan):
    return sorted(p["name"] for p in plan["plan"])


def test_plan_with_no_tasks(client):
    response = client.post("/plan", json={"minutes": 60})
    assert response.status_code == 200
    assert response.json()["plan"] == []


def test_plan_maximises_total_value_not_just_top_task(client):
    add_abc(client)
    plan = client.post("/plan", json={"minutes": 60}).json()
    assert names(plan) == ["B", "C"]               # 75 beats taking A alone (60)
    assert plan["total_value"] == 75
    assert plan["minutes_used"] <= 60
    assert [t["name"] for t in plan["left_out"]] == ["A"]


def test_plan_never_exceeds_budget(client):
    add_abc(client)
    for budget in [1, 29, 30, 45, 60, 100, 200]:
        assert client.post("/plan", json={"minutes": budget}).json()["minutes_used"] <= budget


def test_half_done_task_costs_only_what_is_left(client):
    a = add_abc(client)
    # 20 min for 50% of A: the pace says A takes 40 in total, so 20 are left.
    client.post("/tasks/%d/sessions" % a, json={"minutes_spent": 20, "percent_gained": 50})
    plan = client.post("/plan", json={"minutes": 60}).json()
    assert names(plan) == ["A", "B"]               # A (20 left) + B (30) = 110
    a_entry = [p for p in plan["plan"] if p["name"] == "A"][0]
    assert a_entry["predicted_minutes"] == 20
    assert "remaining 50%" in a_entry["reason"]


def test_plan_learns_that_user_is_slower_than_guessed(client):
    # Twelve past coding sessions where the real time was always double the guess.
    conn = main.db.connect(main.DB_FILE)
    for guess in [10, 20, 30, 40, 15, 25, 35, 45, 12, 22, 32, 42]:
        main.db.add_session(conn, "coding", guess, guess * 2)
    conn.close()

    make_task(client, name="slow one", category="coding", guessed_minutes=30, priority=3)
    fits_if_guess_were_true = client.post("/plan", json={"minutes": 45}).json()
    assert fits_if_guess_were_true["plan"] == []   # really needs ~60, so 45 is not enough
    assert fits_if_guess_were_true["model"] == "category ratio"
    assert fits_if_guess_were_true["avg_error"] is not None

    plan = client.post("/plan", json={"minutes": 60}).json()
    assert plan["plan"][0]["predicted_minutes"] == 60


def test_bad_plan_request_is_rejected(client):
    assert client.post("/plan", json={"minutes": 0}).status_code == 422


# --- recurring (daily) tasks -------------------------------------------------------------------

def make_recurring(client, **changes):
    body = {"name": "gym", "category": "gym", "guessed_minutes": 45, "priority": 2}
    body.update(changes)
    return client.post("/recurring", json=body)


def test_recurring_task_appears_today_without_duplicates(client):
    assert make_recurring(client).status_code == 201
    for _ in range(3):                             # listing many times must not pile up copies
        tasks = client.get("/tasks").json()
    assert len(tasks) == 1
    assert tasks[0]["name"] == "gym"
    assert tasks[0]["recurring"] is True
    assert tasks[0]["due_date"] == datetime.date.today().isoformat()


def test_recurring_copy_can_be_worked_on_like_any_task(client):
    make_recurring(client)
    task_id = client.get("/tasks").json()[0]["id"]
    client.post("/tasks/%d/sessions" % task_id, json={"minutes_spent": 20, "percent_gained": 40})
    assert client.get("/tasks").json()[0]["percent_done"] == 40


def test_next_day_makes_a_fresh_copy_and_skips_the_old_one(client):
    make_recurring(client)
    client.get("/tasks")
    conn = main.db.connect(main.DB_FILE)
    yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    conn.execute("UPDATE recurring SET last_spawned = ?", (yesterday,))   # pretend it ran yesterday
    conn.commit()
    conn.close()

    tasks = client.get("/tasks").json()
    assert len(tasks) == 1                         # one copy for today, the old one is skipped
    assert tasks[0]["percent_done"] == 0


def test_stopped_recurring_task_stops_spawning(client):
    template_id = make_recurring(client).json()["id"]
    assert [r["name"] for r in client.get("/recurring").json()] == ["gym"]
    assert client.post("/recurring/%d/stop" % template_id).status_code == 200
    assert client.get("/recurring").json() == []

    conn = main.db.connect(main.DB_FILE)
    conn.execute("UPDATE recurring SET last_spawned = '2000-01-01'")      # pretend a new day began
    conn.commit()
    conn.close()
    names_today = [t["name"] for t in client.get("/tasks").json()]
    assert names_today.count("gym") == 1           # only the copy made before stopping


def test_stopping_missing_recurring_is_404(client):
    assert client.post("/recurring/999/stop").status_code == 404


def test_bad_recurring_is_rejected(client):
    assert make_recurring(client, guessed_minutes=0).status_code == 422
    assert make_recurring(client, priority=7).status_code == 422


# --- the web page ------------------------------------------------------------------------------

def test_page_and_its_files_are_served(client):
    page = client.get("/")
    assert page.status_code == 200
    assert "FocusFlow" in page.text
    assert client.get("/app.js").status_code == 200
    assert client.get("/style.css").status_code == 200


def test_api_routes_still_win_over_the_page(client):
    assert client.get("/tasks").json() == []       # JSON from the API, not the static files


# --- regression: FastAPI may open and close a connection on different threads ------------------

def test_connection_can_be_closed_from_another_thread(tmp_path):
    conn = main.db.connect(str(tmp_path / "threads.db"))
    errors = []

    def close_it():
        try:
            conn.close()
        except Exception as error:
            errors.append(error)

    worker = threading.Thread(target=close_it)
    worker.start()
    worker.join()
    assert errors == []


# --- filling spare minutes with a slice of a task that did not fit -----------------------------

import fill


def candidate(index, remaining, full, value, percent_done=0):
    return {"index": index, "remaining": remaining, "full": full, "percent_done": percent_done, "value": value}


def test_fill_picks_the_best_value_per_minute():
    # Both need 40 minutes, 20 are spare; the second is worth more per minute.
    chosen = fill.pick_partial([candidate(0, 40, 40.0, 30), candidate(1, 40, 40.0, 50)], 20)
    assert chosen == {"index": 1, "percent": 50, "minutes": 20}


def test_fill_rounds_the_percentage_down_so_it_never_overfills():
    chosen = fill.pick_partial([candidate(0, 30, 30.0, 40)], 20)   # 20/30 = 66.6%
    assert chosen["percent"] == 66
    assert chosen["minutes"] <= 20


def test_fill_percent_is_of_the_whole_task_not_of_what_is_left():
    # Half done: 40 of 80 minutes left, 20 spare. 20 minutes is 25% of the WHOLE task.
    chosen = fill.pick_partial([candidate(0, 40, 80.0, 30, percent_done=50)], 20)
    assert chosen["percent"] == 25


def test_fill_skips_tiny_gaps_and_tiny_slices():
    assert fill.pick_partial([candidate(0, 40, 40.0, 30)], 4) is None        # gap under 5 minutes
    assert fill.pick_partial([candidate(0, 300, 300.0, 30)], 10) is None     # 10/300 = 3%: not worth it
    assert fill.pick_partial([], 30) is None                                 # nothing left out


def test_fill_falls_back_to_a_task_that_gives_a_big_enough_slice():
    big = candidate(0, 600, 600.0, 300)     # best value per minute (0.5), but 20/600 = 3% is too small a slice
    small = candidate(1, 40, 40.0, 10)      # worth less per minute (0.25), yet the only one that gives a useful slice
    assert fill.pick_partial([big, small], 20)["index"] == 1


def test_plan_fills_the_spare_minutes_with_part_of_a_task(client):
    make_task(client, name="A", priority=5, guessed_minutes=40)    # value 50
    make_task(client, name="B", priority=3, guessed_minutes=40)    # value 30, does not fit next to A
    plan = client.post("/plan", json={"minutes": 60}).json()
    assert names(plan) == ["A"]
    assert plan["minutes_used"] == 40
    assert plan["partial"]["name"] == "B"
    assert plan["partial"]["minutes"] == 20                        # exactly the 20 spare minutes
    assert plan["partial"]["percent"] == 50                        # half of a 40-minute task
    assert plan["left_out"] == []                                  # B moved out of "left out"
    assert plan["total_value"] == 50                               # a slice is not counted as finished value


def test_plan_has_no_slice_when_the_gap_is_too_small(client):
    make_task(client, name="A", priority=5, guessed_minutes=40)
    make_task(client, name="B", priority=3, guessed_minutes=40)
    plan = client.post("/plan", json={"minutes": 43}).json()       # only 3 spare minutes
    assert plan["partial"] is None
    assert [t["name"] for t in plan["left_out"]] == ["B"]


def test_plan_has_no_slice_when_everything_fits(client):
    make_task(client, name="A", priority=5, guessed_minutes=20)
    make_task(client, name="B", priority=3, guessed_minutes=20)
    plan = client.post("/plan", json={"minutes": 90}).json()
    assert plan["partial"] is None
    assert plan["left_out"] == []


def test_whole_tasks_plus_slice_never_exceed_the_time(client):
    add_abc(client)
    for budget in [5, 12, 29, 31, 45, 59, 61, 100]:
        plan = client.post("/plan", json={"minutes": budget}).json()
        slice_minutes = plan["partial"]["minutes"] if plan["partial"] else 0
        assert plan["minutes_used"] + slice_minutes <= budget, budget
        if plan["partial"]:
            assert plan["partial"]["id"] not in [p["id"] for p in plan["plan"]]


def test_plan_with_nothing_fitting_whole_still_suggests_a_slice(client):
    make_task(client, name="long", priority=3, guessed_minutes=120)
    plan = client.post("/plan", json={"minutes": 30}).json()
    assert plan["plan"] == []
    assert plan["partial"]["percent"] == 25                        # 30 of 120 minutes


# --- tasks without a guessed time -------------------------------------------------------------

def make_unguessed(client, **changes):
    body = {"name": "gym", "category": "health", "priority": 3}
    body.update(changes)
    return client.post("/tasks", json=body)


def planned(client, minutes=300):
    return client.post("/plan", json={"minutes": minutes}).json()


def test_task_without_guess_is_accepted(client):
    assert make_unguessed(client).status_code == 201
    task = client.get("/tasks").json()[0]
    assert task["guessed_minutes"] is None
    assert task["estimate_source"] == "default"      # nothing known yet
    assert task["shown_minutes"] == 30


def test_zero_guess_is_still_rejected(client):
    assert make_unguessed(client, guessed_minutes=0).status_code == 422


def test_second_time_uses_the_time_it_took_before(client):
    first = make_unguessed(client).json()["id"]
    client.post("/tasks/%d/sessions" % first, json={"minutes_spent": 50, "percent_gained": 100})

    make_unguessed(client)                           # same name, still no guess
    plan = planned(client)
    item = plan["plan"][0]
    assert item["predicted_minutes"] == 50
    assert item["estimate_source"] == "remembered"
    assert "last time" in item["reason"]


def test_memory_ignores_capitals_and_averages_recent_sittings(client):
    for spent in (40, 60):
        task_id = make_unguessed(client, name="Gym").json()["id"]
        client.post("/tasks/%d/sessions" % task_id, json={"minutes_spent": spent, "percent_gained": 100})
    make_unguessed(client, name="  gym ")
    assert planned(client)["plan"][0]["predicted_minutes"] == 50


def test_half_done_sitting_is_scaled_to_the_whole_task(client):
    task_id = make_unguessed(client, name="essay").json()["id"]
    client.post("/tasks/%d/sessions" % task_id, json={"minutes_spent": 30, "percent_gained": 50})
    client.post("/tasks/%d/sessions" % task_id, json={"minutes_spent": 30, "percent_gained": 50})
    make_unguessed(client, name="essay")
    assert planned(client)["plan"][0]["predicted_minutes"] == 60


def test_new_name_falls_back_to_category_average(client):
    task_id = make_unguessed(client, name="gym").json()["id"]
    client.post("/tasks/%d/sessions" % task_id, json={"minutes_spent": 40, "percent_gained": 100})
    make_unguessed(client, name="yoga")              # new name, same category "health"
    item = planned(client)["plan"][0]
    assert item["estimate_source"] == "category"
    assert item["predicted_minutes"] == 40


def test_unguessed_sittings_do_not_enter_the_engine_history(client):
    import db
    task_id = make_unguessed(client).json()["id"]
    client.post("/tasks/%d/sessions" % task_id, json={"minutes_spent": 50, "percent_gained": 100})
    conn = db.connect(main.DB_FILE)
    assert db.history_for_engine(conn) == []
    conn.close()


def test_guessed_and_unguessed_tasks_plan_together(client):
    make_task(client, name="report", guessed_minutes=45)
    make_unguessed(client, name="gym")
    plan = planned(client)
    sources = {p["name"]: p["estimate_source"] for p in plan["plan"]}
    assert sources == {"report": "guess", "gym": "default"}


def test_daily_task_without_guess_learns_from_yesterday(client):
    import db
    client.post("/recurring", json={"name": "gym", "category": "health", "priority": 2})
    task = client.get("/tasks").json()[0]
    client.post("/tasks/%d/sessions" % task["id"], json={"minutes_spent": 35, "percent_gained": 100})
    conn = db.connect(main.DB_FILE)
    db.spawn_recurring(conn, "2999-01-01")           # pretend a new day began
    conn.close()
    assert planned(client)["plan"][0]["predicted_minutes"] == 35


def test_old_database_is_upgraded_and_keeps_its_rows(tmp_path):
    import sqlite3
    import db
    path = str(tmp_path / "old.db")
    old = sqlite3.connect(path)
    old.executescript("""
        CREATE TABLE categories (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE);
        CREATE TABLE recurring (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
            category_id INTEGER NOT NULL, guessed_minutes INTEGER NOT NULL, priority INTEGER NOT NULL,
            active INTEGER NOT NULL DEFAULT 1, last_spawned TEXT);
        CREATE TABLE tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
            category_id INTEGER NOT NULL REFERENCES categories(id), guessed_minutes INTEGER NOT NULL,
            priority INTEGER NOT NULL, due_date TEXT, percent_done INTEGER NOT NULL DEFAULT 0,
            spent_minutes INTEGER NOT NULL DEFAULT 0, done INTEGER NOT NULL DEFAULT 0, template_id INTEGER);
        CREATE TABLE sessions (id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER REFERENCES tasks(id), category_id INTEGER NOT NULL,
            guessed_minutes INTEGER NOT NULL, minutes_spent INTEGER NOT NULL,
            percent_gained INTEGER NOT NULL, finished INTEGER NOT NULL, actual_minutes INTEGER NOT NULL);
        INSERT INTO categories (name) VALUES ('coding');
        INSERT INTO tasks (name, category_id, guessed_minutes, priority) VALUES ('old task', 1, 60, 3);
        INSERT INTO sessions (task_id, category_id, guessed_minutes, minutes_spent, percent_gained, finished, actual_minutes)
            VALUES (1, 1, 60, 80, 100, 1, 80);
    """)
    old.commit()
    old.close()

    conn = db.connect(path)                          # opening it upgrades it
    assert conn.execute("SELECT name FROM tasks").fetchone()["name"] == "old task"
    assert db.history_for_engine(conn) == [(1, 60, 80)]
    db.add_task(conn, "no guess", "coding", None, 3)  # NULL is now allowed
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    conn.close()


# --- reset ------------------------------------------------------------------------------------

def test_reset_erases_everything_and_restarts_ids(client):
    task_id = make_task(client).json()["id"]
    client.post("/tasks/%d/sessions" % task_id, json={"minutes_spent": 50, "percent_gained": 100})
    client.post("/recurring", json={"name": "gym", "category": "health", "guessed_minutes": 30, "priority": 2})
    make_unguessed(client, name="read")

    assert client.post("/reset", json={"confirm": True}).status_code == 200

    assert client.get("/tasks").json() == []
    assert client.get("/recurring").json() == []
    assert make_task(client).json()["id"] == 1            # numbering starts again
    # the history is gone too: a plan now has no model to report
    assert client.post("/plan", json={"minutes": 60}).json()["avg_error"] is None


def test_reset_needs_explicit_confirmation(client):
    make_task(client)
    assert client.post("/reset", json={"confirm": False}).status_code == 400
    assert client.post("/reset", json={}).status_code == 422
    assert len(client.get("/tasks").json()) == 1          # nothing was erased


# --- deleting a task --------------------------------------------------------------------------

def test_delete_untouched_task_removes_it(client):
    task_id = make_task(client).json()["id"]
    assert client.delete("/tasks/%d" % task_id).status_code == 200
    assert client.get("/tasks").json() == []


def test_delete_unknown_task_is_404(client):
    assert client.delete("/tasks/999").status_code == 404
    task_id = make_task(client).json()["id"]
    client.delete("/tasks/%d" % task_id)
    assert client.delete("/tasks/%d" % task_id).status_code == 404     # already gone


def test_deleted_task_still_teaches_the_planner(client):
    # work on "gym" (no guess) for 50 min, delete it, then add "gym" again
    task_id = make_unguessed(client).json()["id"]
    client.post("/tasks/%d/sessions" % task_id, json={"minutes_spent": 50, "percent_gained": 40})
    assert client.delete("/tasks/%d" % task_id).status_code == 200
    assert client.get("/tasks").json() == []                            # hidden from the list

    make_unguessed(client)
    item = planned(client)["plan"][0]
    assert item["estimate_source"] == "remembered"                      # 50 min for 40% -> 125 min whole
    assert item["predicted_minutes"] == 125


def test_cannot_log_time_on_a_deleted_task(client):
    task_id = make_task(client).json()["id"]
    client.post("/tasks/%d/sessions" % task_id, json={"minutes_spent": 10, "percent_gained": 10})
    client.delete("/tasks/%d" % task_id)
    response = client.post("/tasks/%d/sessions" % task_id, json={"minutes_spent": 10, "percent_gained": 10})
    assert response.status_code == 404
