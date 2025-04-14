import os
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
import requests
import pytz
from sqlite_utils import Database
from sqlite_utils.db import NotFoundError

DB_PATH = "data/mffr.db"
tz = pytz.timezone("Europe/Tallinn")

HA_URL = os.getenv("HA_URL", "http://localhost:8123")
HA_TOKEN = os.getenv("HA_TOKEN")
SENSOR_MODE = os.environ["SENSOR_MODE"]
SENSOR_POWER = os.environ["SENSOR_POWER"]
SENSOR_NORDPOOL = os.environ["SENSOR_NORDPOOL"]

# Setup the schema once (outside scheduler)
init_db = Database(DB_PATH)
init_db["slots"].create({
    "timeslot": str,
    "start": str,
    "end": str,
    "signal": str,
    "energy_kwh": float,
    "mffr_price": float,
    "nordpool_price": float,
    "profit": float,
    "duration_min": int,
    "cancelled": bool,
    "was_backup": bool,
    "slot_end": str
}, pk="timeslot", if_not_exists=True)

last_signal = None
last_logged_signal = None

def get_sensor_state(entity_id):
    url = f"{HA_URL}/api/states/{entity_id}"
    headers = {
        "Authorization": f"Bearer {HA_TOKEN}",
        "Content-Type": "application/json"
    }
    try:
        response = requests.get(url, headers=headers)
        if response.ok:
            return response.json()["state"]
        else:
            print(f"❌ Failed to fetch {entity_id}: {response.status_code}")
            return None
    except Exception as e:
        print(f"❌ Error fetching {entity_id}: {e}")
        return None

def write_current_timeslot():
    global last_signal, last_logged_signal
    db = Database(DB_PATH)  # 🔄 Fresh DB instance for this thread

    now = datetime.now(tz).replace(microsecond=0)
    minute = (now.minute // 15) * 15
    timeslot = now.replace(minute=minute, second=0)
    key = timeslot.isoformat()
    slot_end_time = timeslot + timedelta(minutes=15)

    battery_mode = get_sensor_state(SENSOR_MODE)
    signal = None
    if battery_mode == "Fusebox Buy":
        signal = "DOWN"
    elif battery_mode == "Fusebox Sell":
        signal = "UP"

    if signal != last_logged_signal:
        print(f"🔔 Signal became {signal} at {now.isoformat()}")
        last_logged_signal = signal

    power_str = get_sensor_state(SENSOR_POWER)
    try:
        power = float(power_str)
    except (TypeError, ValueError):
        power = 0.0

    raw_energy_kwh = (power / 1000) * (10 / 3600)
    energy_kwh = round(abs(raw_energy_kwh), 5)

    try:
        row = db["slots"].get(key)
    except NotFoundError:
        row = None

    if signal:
        if row and row["signal"] == signal:
            end_time = datetime.fromisoformat(row["end"])
            finalized = end_time >= slot_end_time

            if not finalized:
                start_time = datetime.fromisoformat(row["start"])
                duration = round((now - start_time).total_seconds() / 60)
                cancelled = now < (slot_end_time - timedelta(seconds=11))
                was_backup = (start_time - timeslot).total_seconds() >= 15

                update_data = {
                    "timeslot": key,
                    "energy_kwh": round(row["energy_kwh"] + energy_kwh, 5),
                    "end": now.isoformat(),
                    "duration_min": duration,
                    "cancelled": cancelled,
                    "was_backup": was_backup,
                    "slot_end": slot_end_time.isoformat()
                }
                db["slots"].update(key, update_data)
        else:
            entry = {
                "timeslot": key,
                "start": now.isoformat(),
                "end": now.isoformat(),
                "signal": signal,
                "energy_kwh": energy_kwh,
                "mffr_price": None,
                "nordpool_price": None,
                "profit": None,
                "duration_min": 0,
                "cancelled": False,
                "was_backup": False,
                "slot_end": slot_end_time.isoformat()
            }
            db["slots"].insert(entry, pk="timeslot", replace=True)

        last_signal = signal

        # Enrich with Nordpool price
        try:
            response = requests.get(
                f"{HA_URL}/api/states/{SENSOR_NORDPOOL}",
                headers={
                    "Authorization": f"Bearer {HA_TOKEN}",
                    "Content-Type": "application/json"
                }
            )
            raw_today = response.json().get("attributes", {}).get("raw_today", [])
            for entry in raw_today:
                start = datetime.fromisoformat(entry["start"])
                end = datetime.fromisoformat(entry["end"])
                if start <= timeslot < end:
                    price = round(entry["value"], 5)
                    try:
                        row = db["slots"].get(key)
                        if row.get("nordpool_price") is None:
                            db["slots"].update(key, {"nordpool_price": price})
                            print(f"📈 Set Nordpool price {price} €/kWh for slot {key}")
                    except NotFoundError:
                        pass
                    break
        except Exception as e:
            print(f"❌ Failed to fetch Nordpool price: {e}")

scheduler = BackgroundScheduler()
scheduler.add_job(write_current_timeslot, 'interval', seconds=10)