import requests  # Only if you actually need it
import sqlite_utils
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
import pytz
import time
import os

DB_PATH = "data/mffr.db"
LOG_PATH = "logs/mffr_price_fetch_errors.log"
tz = pytz.timezone("Europe/Tallinn")
db = sqlite_utils.Database(DB_PATH)
scheduler = BackgroundScheduler()


def calculate_and_store_baseline(now: datetime):
    """
    Calculate and store a new baseline value based on the current state.
    Only store if the current timeslot is not part of an MFFR signal.
    """
    conn = db.conn
    slot_start = now.replace(minute=(now.minute // 15) * 15, second=0, microsecond=0)

    # Check if there is an MFFR signal during this slot — skip baseline if yes
    row = conn.execute("SELECT signal FROM slots WHERE slot_start = ?", (slot_start.isoformat(),)).fetchone()
    if row and row[0] is not None:
        print(f"[baseline.py] Skipping baseline at {slot_start} due to MFFR signal.")
        return

    # Fetch latest battery power as example baseline metric
    row = conn.execute("SELECT battery_power FROM slots WHERE slot_start = ?", (slot_start.isoformat(),)).fetchone()
    if not row:
        print(f"[baseline.py] No battery_power data for slot {slot_start}")
        return

    battery_power = row[0]

    # Insert or update baseline
    conn.execute(
        "INSERT OR REPLACE INTO baselines (slot_start, battery_power) VALUES (?, ?)",
        (slot_start.isoformat(), battery_power)
    )
    conn.commit()
    print(f"[baseline.py] Baseline stored for {slot_start} = {battery_power:.2f} kW")


def maybe_delete_old_baselines(now: datetime):
    """
    Deletes outdated baselines. Keeps the most recent one and all used in MFFR commands.
    """
    conn = db.conn
    cursor = conn.cursor()

    # Fetch all baselines
    cursor.execute("SELECT slot_start FROM baselines ORDER BY slot_start")
    all_baselines = [datetime.fromisoformat(row[0]) for row in cursor.fetchall()]
    if not all_baselines:
        return

    # Fetch all MFFR signal slots
    cursor.execute("SELECT slot_start FROM slots WHERE signal IS NOT NULL")
    mffr_slots = {datetime.fromisoformat(row[0]) for row in cursor.fetchall()}

    keep = set()
    for i, start in enumerate(all_baselines):
        next_start = start + timedelta(minutes=15)

        # Keep baseline if its next slot or next 3 slots are used in MFFR
        if next_start in mffr_slots or any(ts in mffr_slots for ts in all_baselines[i + 1:i + 4]):
            keep.add(start)

    # Always keep the latest baseline
    keep.add(all_baselines[-1])

    # Delete old baselines not in keep
    to_delete = [ts for ts in all_baselines if ts not in keep and ts < now - timedelta(minutes=15)]
    if to_delete:
        print(f"[baseline.py] Deleting {len(to_delete)} outdated baselines")
        cursor.executemany("DELETE FROM baselines WHERE slot_start = ?", [(ts.isoformat(),) for ts in to_delete])
        conn.commit()


def run():
    now = datetime.now(tz)
    try:
        calculate_and_store_baseline(now)
        maybe_delete_old_baselines(now)
    except Exception as e:
        with open(LOG_PATH, "a") as f:
            f.write(f"[{now.isoformat()}] Error in baseline.py: {e}\n")
        print(f"[baseline.py] Error: {e}")


if __name__ == "__main__":
    run()
    scheduler.add_job(run, "interval", minutes=15, next_run_time=datetime.now(tz))
    scheduler.start()

    try:
        while True:
            time.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()