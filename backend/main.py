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

# Entities (from .env)
SENSOR_MODE = os.environ["SENSOR_MODE"]               # input_select.battery_mode_selector
SENSOR_GRID = os.environ["SENSOR_GRID"]               # sensor.ss_grid_power (W, +import / -export)
SENSOR_NORDPOOL = os.environ["SENSOR_NORDPOOL"]       # nordpool price (€/kWh)
SENSOR_BASELINE = os.environ.get("SENSOR_BASELINE")   # sensor.mffr_battery_baseline (W) - optional
SENSOR_MFFR_POWER = os.environ["SENSOR_MFFR_POWER"]   # sensor.mffr_power (W, absolute & baseline-adjusted)

# --- DB schema bootstrap ---
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

# Add extra columns if they don't exist
required_columns = {
    "grid_cost": float,
    "ffr_income": float,
    "fusebox_fee": float,
    "net_total": float,
    "price_per_kwh": float,
    "grid_kwh": float,   # legacy safety
    "baseline_w": float  # snapshot of HA baseline per slot (optional)
}
for column, col_type in required_columns.items():
    if column not in init_db["slots"].columns_dict:
        print(f"🛠️  Adding missing column '{column}' to 'slots' table")
        init_db["slots"].add_column(column, col_type)
# ✅ Ensure index on timeslot for fast range queries
init_db["slots"].create_index(["timeslot"], if_not_exists=True)

last_signal = None
last_logged_signal = None

def get_sensor_state(entity_id: str):
    """Fetch state string from Home Assistant; normalize transient values."""
    url = f"{HA_URL}/api/states/{entity_id}"
    headers = {"Authorization": f"Bearer {HA_TOKEN}", "Content-Type": "application/json"}
    try:
        resp = requests.get(url, headers=headers, timeout=5)
        if not resp.ok:
            print(f"❌ Failed to fetch {entity_id}: {resp.status_code}")
            return None
        state = resp.json().get("state")
        return None if state in ("unknown", "unavailable", None) else state
    except Exception as e:
        print(f"❌ Error fetching {entity_id}: {e}")
        return None

def write_current_timeslot():
    """Every 10s: during active FFR signals, accumulate energy & grid kWh into the current 15‑min slot."""
    global last_signal, last_logged_signal
    db = Database(DB_PATH)

    now = datetime.now(tz).replace(microsecond=0)
    minute = (now.minute // 15) * 15
    timeslot = now.replace(minute=minute, second=0)
    key = timeslot.isoformat()
    slot_end_time = timeslot + timedelta(minutes=15)

    # Determine signal from battery mode
    battery_mode = get_sensor_state(SENSOR_MODE)
    signal = "DOWN" if battery_mode == "Fusebox Buy" else "UP" if battery_mode == "Fusebox Sell" else None

    if signal != last_logged_signal:
        print(f"🔔 Signal became {signal} at {now.isoformat()}")
        last_logged_signal = signal

    # Only record when there is an active FFR signal
    if not signal:
        return

    # MFFR absolute (baseline-adjusted) power → 10s energy
    mffr_power_w = 0.0
    s = get_sensor_state(SENSOR_MFFR_POWER)
    if s is not None:
        try:
            mffr_power_w = float(s)
        except ValueError:
            pass
    energy_kwh = round((mffr_power_w / 1000.0) * (10.0 / 3600.0), 5)

    # Grid power sample → 10s energy (signed: +import / -export)
    grid_power_w = 0.0
    gs = get_sensor_state(SENSOR_GRID)
    if gs is not None:
        try:
            grid_power_w = float(gs)
        except ValueError:
            pass
    grid_kwh = round((grid_power_w / 1000.0) * (10.0 / 3600.0), 5)

    # Optional: snapshot the current baseline W for this slot
    baseline_w = None
    if SENSOR_BASELINE:
        bs = get_sensor_state(SENSOR_BASELINE)
        if bs is not None:
            try:
                baseline_w = float(bs)
            except ValueError:
                baseline_w = None

    # Upsert into the current slot
    try:
        row = db["slots"].get(key)
    except NotFoundError:
        row = None

    if row and row["signal"] == signal:
        end_time = datetime.fromisoformat(row["end"])
        if end_time < slot_end_time:
            start_time = datetime.fromisoformat(row["start"])
            duration = round((now - start_time).total_seconds() / 60)
            cancelled = now < (slot_end_time - timedelta(seconds=11))
            was_backup = (start_time - timeslot).total_seconds() >= 15

            update_data = {
                "timeslot": key,
                "energy_kwh": round((row["energy_kwh"] or 0) + energy_kwh, 5),
                "grid_kwh": round((row.get("grid_kwh", 0.0) or 0) + grid_kwh, 5),
                "end": now.isoformat(),
                "duration_min": duration,
                "cancelled": cancelled,
                "was_backup": was_backup,
                "slot_end": slot_end_time.isoformat(),
            }
            if baseline_w is not None and (row.get("baseline_w") is None):
                update_data["baseline_w"] = baseline_w

            db["slots"].update(key, update_data)
    else:
        # Guard against sub‑2s blips right at slot boundary
        if (now - timeslot).total_seconds() < 2:
            print(f"⏱️ Skipped creating 1s slot at {key} due to short signal duration.")
            return

        # Suppress duplicate 0‑min slot immediately after a full slot with same signal
        try:
            prev_slot_time = timeslot - timedelta(minutes=15)
            previous = db["slots"].get(prev_slot_time.isoformat())
            previous_end = datetime.fromisoformat(previous["end"])
            if previous["signal"] == signal and abs((now - previous_end).total_seconds()) < 5:
                print(f"🧹 Suppressed 0‑min slot at {key} after full slot at {prev_slot_time}")
                return
        except NotFoundError:
            pass

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
            "slot_end": slot_end_time.isoformat(),
            "baseline_w": baseline_w,
        }
        db["slots"].insert(entry, pk="timeslot", replace=True)

    # Enrich with Nordpool price once per slot
    try:
        resp = requests.get(
            f"{HA_URL}/api/states/{SENSOR_NORDPOOL}",
            headers={"Authorization": f"Bearer {HA_TOKEN}", "Content-Type": "application/json"},
            timeout=5,
        )
        raw_today = resp.json().get("attributes", {}).get("raw_today", [])
        for p in raw_today:
            start = datetime.fromisoformat(p["start"])
            end = datetime.fromisoformat(p["end"])
            if start <= timeslot < end:
                price = round(p["value"], 5)
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

# Scheduler is started by FastAPI (api.py) on app startup
scheduler = BackgroundScheduler()
scheduler.add_job(write_current_timeslot, 'interval', seconds=10)