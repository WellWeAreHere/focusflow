# API tests. Run from the backend folder:  python -m pytest -q
#
# pytest finds every function named test_* and runs it; a test fails if an `assert` is false
# or the function raises an error. TestClient pretends to be a browser and calls our API
# in-process, so no server needs to be started.
import datetime

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
