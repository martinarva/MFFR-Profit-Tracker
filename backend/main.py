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
SENSOR_GRID = os.environ["SENSOR_GRID"]
SENSOR_NORDPOOL = os.environ["SENSOR_NORDPOOL"]

# Setup the schema once (outside scheduler)
init_db = Database(DB_PATH)
init_db["slots"].create({
    "timeslot": str,
    "start": str,
    "end": str,
    "signal": str,
    "energy_kwh": float,
    "grid_kwh": float,
    "mffr_price": float,
    "nordpool_price": float,
    "profit": float,
    "duration_min": int,
    "cancelled": bool,
    "was_backup": bool,
    "slot_end": str
}, pk="timeslot", if_not_exists=True)

# Ensure new financial columns exist (safe for existing dbs)
required_columns = {
    "grid_cost": float,
    "ffr_income": float,
    "fusebox_fee": float,
    "net_total": float,
    "price_per_kwh": float,
    "grid_kwh": float,
}

for column, col_type in required_columns.items():
    if column not in init_db["slots"].columns_dict:
        print(f"🛠️  Adding missing column '{column}' to 'slots' table")
        init_db["slots"].add_column(column, col_type)

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

    grid_str = get_sensor_state(SENSOR_GRID)
    try:
        grid_power = float(grid_str)
    except (TypeError, ValueError):
        grid_power = 0.0

    raw_grid_energy_kwh = (grid_power / 1000) * (10 / 3600)
    grid_kwh = round(raw_grid_energy_kwh, 5)

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
                    "grid_kwh": round(row.get("grid_kwh", 0.0) + grid_kwh, 5),
                    "end": now.isoformat(),
                    "duration_min": duration,
                    "cancelled": cancelled,
                    "was_backup": was_backup,
                    "slot_end": slot_end_time.isoformat()
                }
                db["slots"].update(key, update_data)
        else:
            # Prevent false slot creation if signal was active for less than 2 seconds
            if (now - timeslot).total_seconds() < 2:
                print(f"⏱️ Skipped creating 1s slot at {key} due to short signal duration.")
                return

            entry = {
                "timeslot": key,
                "start": now.isoformat(),
                "end": now.isoformat(),
                "signal": signal,
                "energy_kwh": energy_kwh,
                "grid_kwh": grid_kwh,
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