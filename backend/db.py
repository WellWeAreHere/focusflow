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
DELETED = 3   # removed by the user, but kept because its sittings still teach the planner


def connect(path=DB_PATH):
    """Open the database file (it is created if missing) and make sure the tables exist.

    Pass the special path ":memory:" to get a throwaway database for tests.
    """
    # By default SQLite refuses to let a different thread touch a connection. FastAPI may open the
    # connection in one worker thread and close it in another, so that check would raise an error
    # at the end of requests. It is safe to turn off here: every request gets its OWN connection,
    # used by one thread at a time, and never shared between requests.
    conn = sqlite3.connect(path, check_same_thread=False)
    # By default a row comes back as a plain tuple, so you must remember column positions.
    # Row lets us write row["name"] instead of row[1].
    conn.row_factory = sqlite3.Row
    # SQLite ignores "this column must point at a real row elsewhere" unless you ask it to check.
    conn.execute("PRAGMA foreign_keys = ON")
    create_tables(conn)
    return conn


# The layout of the tables that mention guessed_minutes. TABLE_NAME is swapped in for the real name,
# because the migration below has to build a copy of a table under a temporary name.
# guessed_minutes may be NULL (= the user gave no guess); when it IS given it must be above 0.
RECURRING_SQL = """
    CREATE TABLE IF NOT EXISTS TABLE_NAME (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        name            TEXT NOT NULL,
        category_id     INTEGER NOT NULL REFERENCES categories(id),
        guessed_minutes INTEGER CHECK (guessed_minutes > 0),
        priority        INTEGER NOT NULL CHECK (priority BETWEEN 1 AND 5),
        active          INTEGER NOT NULL DEFAULT 1,
        last_spawned    TEXT
    );
"""
TASKS_SQL = """
    CREATE TABLE IF NOT EXISTS TABLE_NAME (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        name            TEXT NOT NULL,
        category_id     INTEGER NOT NULL REFERENCES categories(id),
        guessed_minutes INTEGER CHECK (guessed_minutes > 0),
        priority        INTEGER NOT NULL CHECK (priority BETWEEN 1 AND 5),
        due_date        TEXT,
        percent_done    INTEGER NOT NULL DEFAULT 0 CHECK (percent_done BETWEEN 0 AND 100),
        spent_minutes   INTEGER NOT NULL DEFAULT 0,
        done            INTEGER NOT NULL DEFAULT 0,
        template_id     INTEGER REFERENCES recurring(id)
    );
"""
SESSIONS_SQL = """
    CREATE TABLE IF NOT EXISTS TABLE_NAME (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id         INTEGER REFERENCES tasks(id),
        category_id     INTEGER NOT NULL REFERENCES categories(id),
        guessed_minutes INTEGER CHECK (guessed_minutes > 0),
        minutes_spent   INTEGER NOT NULL CHECK (minutes_spent > 0),
        percent_gained  INTEGER NOT NULL CHECK (percent_gained BETWEEN 1 AND 100),
        finished        INTEGER NOT NULL,
        actual_minutes  INTEGER NOT NULL CHECK (actual_minutes > 0)
    );
"""


def create_tables(conn):
    # IF NOT EXISTS makes this safe to run every time the program starts.
    #
    # categories: the C++ engine only understands numbers, so each category name
    #   ("coding", "gym") gets a number (its id). The id is what we send to the engine.
    #   INTEGER PRIMARY KEY AUTOINCREMENT = SQLite hands out 1, 2, 3... by itself, never reused.
    # recurring: a template for a task that should appear every day ("gym", 45 min).
    #   last_spawned is the date we last made today's copy, so we never make two for one day.
    # tasks: things to do. They persist until percent_done reaches 100, so a half-finished
    #   task simply stays here for the next session. spent_minutes is the total time put in so far.
    #   due_date is text like "2026-11-10", or NULL (= no value) when there is no deadline.
    #   guessed_minutes is NULL when the user did not guess: the planner then uses what it
    #   remembers (see remembered_minutes).
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
    """)
    conn.executescript(RECURRING_SQL.replace("TABLE_NAME", "recurring"))
    conn.executescript(TASKS_SQL.replace("TABLE_NAME", "tasks"))
    conn.executescript(SESSIONS_SQL.replace("TABLE_NAME", "sessions"))
    conn.commit()
    _allow_missing_guess(conn)


def _allow_missing_guess(conn):
    """Upgrade a database made before guesses became optional.

    CREATE TABLE IF NOT EXISTS leaves an old table alone, and SQLite cannot remove NOT NULL from a
    column. So for each old table we build a new one with the current layout, copy the rows over,
    drop the old one and rename the new one. This is the method the SQLite docs recommend.
    Foreign keys are switched off while we do it, otherwise dropping tasks would be refused.
    A database that is already up to date is not touched.
    """
    tables = [("recurring", RECURRING_SQL), ("tasks", TASKS_SQL), ("sessions", SESSIONS_SQL)]
    for name, layout in tables:
        columns = conn.execute("PRAGMA table_info(" + name + ")").fetchall()
        needs_upgrade = False
        for column in columns:
            if column["name"] == "guessed_minutes" and column["notnull"] == 1:
                needs_upgrade = True
        if not needs_upgrade:
            continue
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.executescript(layout.replace("TABLE_NAME", name + "_new"))
        conn.execute("INSERT INTO " + name + "_new SELECT * FROM " + name)
        conn.execute("DROP TABLE " + name)
        conn.execute("ALTER TABLE " + name + "_new RENAME TO " + name)
        conn.commit()
        conn.execute("PRAGMA foreign_keys = ON")


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


def delete_task(conn, task_id):
    """Remove an open task from the list. Returns False if there was no open task with that id.

    If you already worked on it, its sittings stay in the history (the predictor learns from them,
    and a later task with the same name uses them), so the row is only hidden (done = DELETED).
    A task that was never worked on has nothing to remember, so it is really deleted.
    """
    task = conn.execute("SELECT id FROM tasks WHERE id = ? AND done = ?", (task_id, OPEN)).fetchone()
    if task is None:
        return False
    sittings = conn.execute("SELECT COUNT(*) AS n FROM sessions WHERE task_id = ?", (task_id,)).fetchone()["n"]
    if sittings > 0:
        conn.execute("UPDATE tasks SET done = ? WHERE id = ?", (DELETED, task_id))
    else:
        conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    conn.commit()
    return True


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
    oldest first. The selector tests on the NEWEST 30%, so the order matters.
    Sittings on tasks with no guess are left out: the engine learns "guess -> real time", and
    there is no guess to learn from. They are used by remembered_minutes instead."""
    rows = conn.execute(
        "SELECT category_id, guessed_minutes, actual_minutes FROM sessions "
        "WHERE guessed_minutes IS NOT NULL ORDER BY id"
    ).fetchall()
    return [(r["category_id"], r["guessed_minutes"], r["actual_minutes"]) for r in rows]


# --- tasks without a guess -------------------------------------------------------------------

DEFAULT_MINUTES = 30      # used only when there is nothing at all to go on
MEMORY_SITTINGS = 5       # how many of the latest sittings on a same-named task we average


def remembered_minutes(conn, task_name, category_id):
    """How long should a task take when the user gave no guess? Returns (minutes, source).

    1. "remembered": earlier sittings on a task with the SAME NAME (ignoring capitals). We average
       the whole-task time of the latest few, so "gym took 50 min last time" becomes 50.
       (actual_minutes already scales a half-done sitting up to the whole task.)
    2. "category": otherwise the average of the latest sittings in the same category.
    3. "default": otherwise a plain 30 minutes, because we know nothing yet.
    """
    rows = conn.execute(
        """SELECT sessions.actual_minutes FROM sessions
           JOIN tasks ON tasks.id = sessions.task_id
           WHERE lower(trim(tasks.name)) = lower(trim(?))
           ORDER BY sessions.id DESC LIMIT ?""",
        (task_name, MEMORY_SITTINGS),
    ).fetchall()
    if len(rows) > 0:
        return _average(rows), "remembered"

    rows = conn.execute(
        "SELECT actual_minutes FROM sessions WHERE category_id = ? ORDER BY id DESC LIMIT 10",
        (category_id,),
    ).fetchall()
    if len(rows) > 0:
        return _average(rows), "category"

    return DEFAULT_MINUTES, "default"


def _average(rows):
    total = 0
    for row in rows:
        total += row["actual_minutes"]
    return max(1, round(total / len(rows)))


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


def reset_all(conn):
    """Delete EVERYTHING: tasks, daily templates, history and categories, and restart the id counters.

    The order matters: a row that points at another table (sessions -> tasks, tasks -> recurring,
    all -> categories) must go before the row it points at, or the foreign-key check refuses.
    sqlite_sequence is the hidden table where AUTOINCREMENT remembers the last id it gave out.
    """
    conn.execute("DELETE FROM sessions")
    conn.execute("DELETE FROM tasks")
    conn.execute("DELETE FROM recurring")
    conn.execute("DELETE FROM categories")
    conn.execute("DELETE FROM sqlite_sequence")
    conn.commit()


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
