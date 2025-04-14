import requests
import sqlite_utils
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
import pytz

DB_PATH = "data/mffr.db"
tz = pytz.timezone("Europe/Tallinn")
db = sqlite_utils.Database(DB_PATH)

scheduler = BackgroundScheduler()


def fetch_and_update_mffr_prices():
    db = sqlite_utils.Database(DB_PATH)  # ✅ Create connection inside the thread
    now = datetime.now(tz)
    updated = 0

    try:
        response = requests.get("https://tihend.energy/api/v1/frr")
        response.raise_for_status()
        data = response.json().get("data", [])
    except Exception as e:
        print(f"❌ Failed to fetch MFFR prices: {e}")
        return

    for row in db["slots"].rows_where("mffr_price IS NULL"):
        try:
            slot_start = datetime.fromisoformat(row["timeslot"])

            for entry in data:
                start_str = entry["start"].replace("+0300", "+03:00")
                entry_start = datetime.fromisoformat(start_str)

                if entry_start == slot_start:
                    mfrr_price = entry.get("mfrr_price")
                    if mfrr_price is not None:
                        db["slots"].update(
                            row["timeslot"],
                            {"mffr_price": mfrr_price},
                            alter=True
                        )
                        updated += 1
                        print(f"📡 Set MFFR price {mfrr_price} for slot {row['timeslot']}")
                    break
        except Exception as e:
            print(f"⚠️ Failed to update MFFR price for slot {row['timeslot']}: {e}")

    if updated:
        print(f"✅ Updated {updated} MFFR prices in SQLite DB.")


scheduler.add_job(fetch_and_update_mffr_prices, "interval", minutes=1)
