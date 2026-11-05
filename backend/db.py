# The database layer: stores categories, tasks, recurring templates and sessions in SQLite.
#
# SQLite is a database that lives in ONE file (focusflow.db) and comes with Python (the
# `sqlite3` module), so there is nothing to install or run. A database is like a set of
# tables; each table has columns (fields) and rows (one record each), a bit like an
# array of structs in C++.
#
# We talk to it in SQL, a small language. Examples used below:
#   CREATE TABLE ...   make a table
#   INSERT INTO ...    add a row
#   SELECT ... FROM    read rows
#   UPDATE ... SET     change a row
import datetime
import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "focusflow.db")

# Values of tasks.done
OPEN = 0      # still to do (maybe partly done)
DONE = 1      # reached 100%
SKIPPED = 2   # a recurring task whose day passed without finishing


def connect(path=DB_PATH):
    """Open the database file (it is created if missing) and make sure the tables exist.

    Pass the special path ":memory:" to get a throwaway database for tests.
    """
    conn = sqlite3.connect(path)
    # By default a row comes back as a plain tuple, so you must remember column positions.
    # Row lets us write row["name"] instead of row[1].
    conn.row_factory = sqlite3.Row
    # SQLite ignores "this column must point at a real row elsewhere" unless you ask it to check.
    conn.execute("PRAGMA foreign_keys = ON")
    create_tables(conn)
    return conn


def create_tables(conn):
    # IF NOT EXISTS makes this safe to run every time the program starts.
    # (It does NOT change a table that already exists. If you edit a column here, delete your
    # local focusflow.db so it is rebuilt, or the old layout stays.)
    #
    # categories: the C++ engine only understands numbers, so each category name
    #   ("coding", "gym") gets a number (its id). The id is what we send to the engine.
    #   INTEGER PRIMARY KEY AUTOINCREMENT = SQLite hands out 1, 2, 3... by itself, never reused.
    # recurring: a template for a task that should appear every day ("gym", 45 min).
    #   last_spawned is the date we last made today's copy, so we never make two for one day.
    # tasks: things to do. They persist until percent_done reaches 100, so a half-finished
    #   task simply stays here for the next session. spent_minutes is the total time put in so far.
    #   due_date is text like "2026-11-10", or NULL (= no value) when there is no deadline.
    #   template_id is set when the task is a daily copy made from a recurring template.
    # sessions: one sitting of work = the history the engine learns from.
    #   minutes_spent / percent_gained / finished describe what really happened in the sitting.
    #   actual_minutes is "what the WHOLE task would take at this pace" (see log_session);
    #   that is the number the predictors train on. task_id is NULL for history added directly.
    #   Rows are stored in the order they were added, so ORDER BY id = oldest first.
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS categories (
            id   INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        );
        CREATE TABLE IF NOT EXISTS recurring (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            name            TEXT NOT NULL,
            category_id     INTEGER NOT NULL REFERENCES categories(id),
            guessed_minutes INTEGER NOT NULL CHECK (guessed_minutes > 0),
            priority        INTEGER NOT NULL CHECK (priority BETWEEN 1 AND 5),
            active          INTEGER NOT NULL DEFAULT 1,
            last_spawned    TEXT
        );
        CREATE TABLE IF NOT EXISTS tasks (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            name            TEXT NOT NULL,
            category_id     INTEGER NOT NULL REFERENCES categories(id),
            guessed_minutes INTEGER NOT NULL CHECK (guessed_minutes > 0),
            priority        INTEGER NOT NULL CHECK (priority BETWEEN 1 AND 5),
            due_date        TEXT,
            percent_done    INTEGER NOT NULL DEFAULT 0 CHECK (percent_done BETWEEN 0 AND 100),
            spent_minutes   INTEGER NOT NULL DEFAULT 0,
            done            INTEGER NOT NULL DEFAULT 0,
            template_id     INTEGER REFERENCES recurring(id)
        );
        CREATE TABLE IF NOT EXISTS sessions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id         INTEGER REFERENCES tasks(id),
            category_id     INTEGER NOT NULL REFERENCES categories(id),
            guessed_minutes INTEGER NOT NULL CHECK (guessed_minutes > 0),
            minutes_spent   INTEGER NOT NULL CHECK (minutes_spent > 0),
            percent_gained  INTEGER NOT NULL CHECK (percent_gained BETWEEN 1 AND 100),
            finished        INTEGER NOT NULL,
            actual_minutes  INTEGER NOT NULL CHECK (actual_minutes > 0)
        );
    """)
    conn.commit()


# --- categories -------------------------------------------------------------------------------

def category_id(conn, name):
    """Return the number for a category name, creating the category the first time we see it."""
    name = name.strip().lower()  # "Coding " and "coding" should be the same category
    # The ? is a placeholder: sqlite3 puts the value in safely. NEVER build SQL by gluing
    # strings together with user text, or a user could type SQL commands as a "name" (SQL injection).
    row = conn.execute("SELECT id FROM categories WHERE name = ?", (name,)).fetchone()
    if row is not None:
        return row["id"]
    cursor = conn.execute("INSERT INTO categories (name) VALUES (?)", (name,))
    conn.commit()
    return cursor.lastrowid  # the id SQLite just handed out


# --- tasks ------------------------------------------------------------------------------------

def add_task(conn, name, category, guessed_minutes, priority, due_date=None):
    """Add a task to do. `category` is a name like "coding". Returns the new task's id."""
    cid = category_id(conn, category)
    cursor = conn.execute(
        "INSERT INTO tasks (name, category_id, guessed_minutes, priority, due_date) VALUES (?, ?, ?, ?, ?)",
        (name, cid, guessed_minutes, priority, due_date),
    )
    conn.commit()
    return cursor.lastrowid


def list_open_tasks(conn):
    """All tasks not finished yet (including half-done ones). JOIN pulls the category name in
    from the categories table. The planner should only schedule the REMAINING part:
    predicted minutes * (100 - percent_done) / 100."""
    rows = conn.execute("""
        SELECT tasks.id, tasks.name, tasks.category_id, categories.name AS category,
               tasks.guessed_minutes, tasks.priority, tasks.due_date,
               tasks.percent_done, tasks.spent_minutes, tasks.template_id
        FROM tasks JOIN categories ON categories.id = tasks.category_id
        WHERE tasks.done = ?
        ORDER BY tasks.id
    """, (OPEN,)).fetchall()
    return rows


def mark_done(conn, task_id):
    """Mark a task fully finished without logging time. Returns False if there was no open task."""
    cursor = conn.execute(
        "UPDATE tasks SET done = ?, percent_done = 100 WHERE id = ? AND done = ?",
        (DONE, task_id, OPEN),
    )
    conn.commit()
    return cursor.rowcount == 1  # rowcount = how many rows the UPDATE changed


# --- sessions ---------------------------------------------------------------------------------

def _insert_session(conn, task_id, cid, guessed, spent, gained, finished):
    # A sitting that finished `gained`% of the task in `spent` minutes suggests the whole
    # task takes spent * 100 / gained at this pace (40 min for 50% -> about 80 min in total).
    # For a plain finished task (gained = 100) this is just `spent`.
    # The percentage is the user's own estimate, so unfinished sittings are noisier data.
    actual = max(1, round(spent * 100 / gained))
    cursor = conn.execute(
        """INSERT INTO sessions
           (task_id, category_id, guessed_minutes, minutes_spent, percent_gained, finished, actual_minutes)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (task_id, cid, guessed, spent, gained, 1 if finished else 0, actual),
    )
    return cursor.lastrowid


def log_session(conn, task_id, minutes_spent, percent_gained):
    """Record a sitting on a task: you worked `minutes_spent` and finished `percent_gained`% of it.

    If that brings the task to 100% it is closed. Otherwise it stays open at its new percentage
    and the session is stored as unfinished ("the time was not enough").
    Raises ValueError for bad input. Returns (new_percent_done, finished).
    """
    if minutes_spent <= 0:
        raise ValueError("minutes_spent must be positive")
    if not 1 <= percent_gained <= 100:
        raise ValueError("percent_gained must be between 1 and 100")

    task = conn.execute("SELECT * FROM tasks WHERE id = ? AND done = ?", (task_id, OPEN)).fetchone()
    if task is None:
        raise ValueError("no open task with that id")

    # You cannot finish more than what is left (a task at 80% can gain at most 20%).
    gained = min(percent_gained, 100 - task["percent_done"])
    new_percent = task["percent_done"] + gained
    finished = new_percent >= 100

    _insert_session(conn, task_id, task["category_id"], task["guessed_minutes"],
                    minutes_spent, gained, finished)
    conn.execute(
        "UPDATE tasks SET percent_done = ?, spent_minutes = spent_minutes + ?, done = ? WHERE id = ?",
        (new_percent, minutes_spent, DONE if finished else OPEN, task_id),
    )
    conn.commit()  # one commit for both writes, so the session and the task never disagree
    return new_percent, finished


def add_session(conn, category, guessed_minutes, actual_minutes):
    """Add a finished piece of history directly, with no task behind it (used to load or
    simulate past data). It counts as a fully finished session."""
    cid = category_id(conn, category)
    session_id = _insert_session(conn, None, cid, guessed_minutes, actual_minutes, 100, True)
    conn.commit()
    return session_id


def history_for_engine(conn):
    """The history in the exact shape engine.predict_minutes wants: (category_id, guessed, actual),
    oldest first. The selector tests on the NEWEST 30%, so the order matters."""
    rows = conn.execute(
        "SELECT category_id, guessed_minutes, actual_minutes FROM sessions ORDER BY id"
    ).fetchall()
    return [(r["category_id"], r["guessed_minutes"], r["actual_minutes"]) for r in rows]


# --- recurring (daily) tasks ------------------------------------------------------------------

def add_recurring(conn, name, category, guessed_minutes, priority):
    """Create a template for a task that should appear every day. Returns the template's id."""
    cid = category_id(conn, category)
    cursor = conn.execute(
        "INSERT INTO recurring (name, category_id, guessed_minutes, priority) VALUES (?, ?, ?, ?)",
        (name, cid, guessed_minutes, priority),
    )
    conn.commit()
    return cursor.lastrowid


def list_recurring(conn):
    """The daily templates that are still active."""
    return conn.execute("""
        SELECT recurring.id, recurring.name, categories.name AS category,
               recurring.guessed_minutes, recurring.priority
        FROM recurring JOIN categories ON categories.id = recurring.category_id
        WHERE recurring.active = 1
        ORDER BY recurring.id
    """).fetchall()


def stop_recurring(conn, template_id):
    """Stop making new daily copies. Copies that already exist are left alone."""
    cursor = conn.execute("UPDATE recurring SET active = 0 WHERE id = ?", (template_id,))
    conn.commit()
    return cursor.rowcount == 1


def spawn_recurring(conn, today=None):
    """Make today's copy of every active daily template. Returns how many copies were made.

    There is no background timer running: instead the API calls this before it lists tasks or
    plans, so the copies exist "automatically" the first time the app is used each day.
    It is safe to call many times a day, because last_spawned stops duplicates.
    `today` is a date text like "2026-11-05" (tests pass one in; normally it is the real date).

    If you skipped days, you get ONE copy for today, not a pile of missed ones. An older unfinished
    copy of the same template is marked SKIPPED (its sessions stay in the history).
    """
    if today is None:
        today = datetime.date.today().isoformat()

    templates = conn.execute(
        "SELECT * FROM recurring WHERE active = 1 AND (last_spawned IS NULL OR last_spawned != ?)",
        (today,),
    ).fetchall()

    for t in templates:
        conn.execute("UPDATE tasks SET done = ? WHERE template_id = ? AND done = ?",
                     (SKIPPED, t["id"], OPEN))
        # The copy is due today, so the planner's urgency bonus applies to it.
        conn.execute(
            """INSERT INTO tasks (name, category_id, guessed_minutes, priority, due_date, template_id)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (t["name"], t["category_id"], t["guessed_minutes"], t["priority"], today, t["id"]),
        )
        conn.execute("UPDATE recurring SET last_spawned = ? WHERE id = ?", (today, t["id"]))
    conn.commit()
    return len(templates)


# Quick check when run directly:  python backend/db.py
if __name__ == "__main__":
    conn = connect(":memory:")  # throwaway database, nothing is written to disk

    # --- partial progress ---
    report = add_task(conn, "write report", "Coding", 60, 3, "2026-11-06")
    print("stop at 50% after 40 min:", log_session(conn, report, 40, 50))
    row = list_open_tasks(conn)[0]
    print("task still open:", row["name"], row["percent_done"], "% done,", row["spent_minutes"], "min spent")
    print("finish the other 50% in 30 min:", log_session(conn, report, 30, 50))
    print("open tasks now:", [r["name"] for r in list_open_tasks(conn)])
    print("history (category, guessed, whole-task actual):", history_for_engine(conn))
    sess = conn.execute("SELECT minutes_spent, percent_gained, finished, actual_minutes FROM sessions").fetchall()
    print("sessions:", [tuple(s) for s in sess])

    for bad in [(report, 10, 10), (999, 10, 10)]:
        try:
            log_session(conn, *bad)
        except ValueError as e:
            print("rejected:", e)

    # --- recurring tasks ---
    gym = add_recurring(conn, "gym", "gym", 45, 2)
    print("day 1 made:", spawn_recurring(conn, "2026-11-05"), "| again same day:", spawn_recurring(conn, "2026-11-05"))
    gym_task = [r for r in list_open_tasks(conn) if r["template_id"] == gym][0]
    log_session(conn, gym_task["id"], 20, 40)          # only got 40% done
    print("day 3 (skipped a day) made:", spawn_recurring(conn, "2026-11-07"))
    print("open gym copies:", [(r["due_date"], r["percent_done"]) for r in list_open_tasks(conn)])
    stop_recurring(conn, gym)
    print("after stopping, day 4 made:", spawn_recurring(conn, "2026-11-08"))

    # --- the old rules still hold ---
    try:
        add_task(conn, "bad", "coding", 0, 3)  # 0 minutes breaks the CHECK rule
    except sqlite3.IntegrityError as e:
        print("rejected bad task:", e)
