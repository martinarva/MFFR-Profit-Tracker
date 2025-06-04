import requests
import sqlite_utils
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
import pytz
import time
import os

DB_PATH = "data/mffr.db"
LOG_PATH = "logs/mffr_price_fetch_errors.log"
tz = pytz.timezone("Europe/Tallinn")
db = sqlite_utils.Database(DB_PATH)
scheduler = BackgroundScheduler()

# Ensure log folder exists
os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)

def log_error(message):
    with open(LOG_PATH, "a") as f:
        timestamp = datetime.now(tz).isoformat()
        f.write(f"[{timestamp}] {message}\n")

def fetch_and_update_mffr_prices():
    start_time = time.time()
    db = sqlite_utils.Database(DB_PATH)
    updated = 0

    try:
        response = requests.get(
            "https://tihend.energy/api/v1/frr",
            timeout=5,  # ⏱️ Timeout here
            verify=False
        )
        response.raise_for_status()
        raw_data = response.json().get("data", [])
    except Exception as e:
        msg = f"❌ Failed to fetch MFFR prices: {e}"
        print(msg)
        log_error(msg)
        return

    api_data = {}
    for entry in raw_data:
        try:
            entry_start = datetime.fromisoformat(entry["start"].replace("+0300", "+03:00"))
            api_data[entry_start] = entry.get("mfrr_price")
        except Exception as e:
            msg = f"⚠️ Skipping malformed API entry: {e}"
            print(msg)
            log_error(msg)

    for row in db["slots"].rows_where("mffr_price IS NULL"):
        try:
            slot_start = datetime.fromisoformat(row["timeslot"])
            mfrr_price = api_data.get(slot_start)

            if mfrr_price is not None:
                db["slots"].update(
                    row["timeslot"],
                    {"mffr_price": mfrr_price},
                    alter=True
                )
                updated += 1
                print(f"📡 Set MFFR price {mfrr_price} for slot {row['timeslot']}")
        except Exception as e:
            msg = f"⚠️ Failed to update MFFR price for slot {row['timeslot']}: {e}"
            print(msg)
            log_error(msg)

    if updated:
        print(f"✅ Updated {updated} MFFR prices in SQLite DB.")
    print(f"⏱️ Completed in {time.time() - start_time:.2f} seconds.")

scheduler.add_job(
    fetch_and_update_mffr_prices,
    "interval",
    minutes=1,
    max_instances=1,
    coalesce=True
)