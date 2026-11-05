# Fills a database with demo data (a simulated user's history plus a few tasks), so you can try the app
# or take screenshots without typing everything in.
# Usage:  python simulator/seed_demo.py demo.db
# Then:   set FOCUSFLOW_DB=demo.db   and start the server as usual.
import datetime
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "backend"))
sys.path.insert(0, HERE)

import db
import simulate

NAMES = ["study", "gym", "coding", "chores"]   # simulate.py numbers the categories 0..3


def main():
    if len(sys.argv) != 2:
        print("usage: python simulator/seed_demo.py <database file>")
        sys.exit(1)
    path = sys.argv[1]
    if os.path.exists(path):
        print("refusing to touch an existing file:", path)
        sys.exit(1)

    rng = random.Random(7)
    user = simulate.make_user(rng, calibrated=False)
    conn = db.connect(path)

    for category, guessed, actual in simulate.make_sessions(rng, user, 80):
        db.add_session(conn, NAMES[category], guessed, actual)

    today = datetime.date.today()

    def due(days):
        return (today + datetime.timedelta(days=days)).isoformat()

    db.add_task(conn, "Finish OS assignment", "study", 90, 4, due(1))
    db.add_task(conn, "Refactor login module", "coding", 120, 3, due(4))
    report = db.add_task(conn, "Write project report", "coding", 60, 5, due(2))
    db.add_task(conn, "Fix failing unit test", "coding", 30, 3)
    db.add_task(conn, "Clean the room", "chores", 25, 2)
    db.add_task(conn, "Revise networks notes", "study", 45, 3, due(7))
    db.add_recurring(conn, "Gym session", "gym", 45, 2)
    db.log_session(conn, report, 25, 40)   # stopped at 40%: stays on the list for next time
    conn.close()
    print("demo data written to", path)


main()
