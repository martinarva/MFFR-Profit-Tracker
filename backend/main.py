# main.py
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
SENSOR_POWER = os.environ["SENSOR_POWER"]             # sensor.ss_battery_power (W)

# --- DB schema bootstrap ---
init_db = Database(DB_PATH)
try:
    init_db.conn.execute("PRAGMA journal_mode=WAL;")
    init_db.conn.execute("PRAGMA synchronous=NORMAL;")
    init_db.conn.execute("PRAGMA busy_timeout=5000;")
except Exception as e:
    print(f"⚙️ PRAGMA setup failed: {e}")

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

required_columns = {
    "grid_cost": float,
    "ffr_income": float,
    "fusebox_fee": float,
    "net_total": float,
    "price_per_kwh": float,
    "grid_kwh": float,     # legacy safety
    "baseline_w": float    # snapshot of baseline per slot
}
for column, col_type in required_columns.items():
    if column not in init_db["slots"].columns_dict:
        print(f"🛠️  Adding missing column '{column}' to 'slots' table")
        init_db["slots"].add_column(column, col_type)

init_db["slots"].create_index(["timeslot"], if_not_exists=True)
init_db["slots"].create_index(["duration_min", "end"], if_not_exists=True)

last_logged_signal = None

def _with_busy_timeout(db: Database, ms: int = 5000):
    try:
        db.conn.execute(f"PRAGMA busy_timeout={ms};")
    except Exception:
        pass

def get_sensor_state(entity_id: str):
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

def get_latest_baseline_w() -> float:
    try:
        db = Database(DB_PATH)
        row = db["baseline_state"].get("latest")
        return float(row["baseline_w"])
    except Exception:
        return 0.0  # Default fallback if not available

def cleanup_zero_min_rows():
    db = Database(DB_PATH)
    _with_busy_timeout(db)
    try:
        cutoff = (datetime.now(tz) - timedelta(minutes=2)).isoformat()
        with db.conn:
            db.conn.execute(
                "DELETE FROM slots WHERE duration_min = 0 AND end < ?",
                (cutoff,)
            )
    except Exception as e:
        if "locked" in str(e).lower():
            print("🧹 Cleanup skipped (database locked).")
        else:
            print(f"🧹 Scheduled cleanup failed: {e}")

def write_current_timeslot():
    global last_logged_signal
    db = Database(DB_PATH)
    _with_busy_timeout(db)

    now = datetime.now(tz).replace(microsecond=0)
    minute = (now.minute // 15) * 15
    timeslot = now.replace(minute=minute, second=0)
    key = timeslot.isoformat()
    slot_end_time = timeslot + timedelta(minutes=15)

    def mode_to_signal(mode: str | None) -> str | None:
        if not mode:
            return None
        m = mode.strip().lower()
        if m in {"fusebox buy", "kratt buy"}:
            return "DOWN"
        if m in {"fusebox sell", "kratt sell"}:
            return "UP"
        return None

    battery_mode = get_sensor_state(SENSOR_MODE)
    signal = mode_to_signal(battery_mode)

    if signal != last_logged_signal:
        print(f"🔔 Signal became {signal} at {now.isoformat()}")
        last_logged_signal = signal

    if not signal:
        return

    # Calculate mffr_power_w = abs(battery_power - baseline)
    try:
        battery_power_w = float(get_sensor_state(SENSOR_POWER))
        baseline_w = get_latest_baseline_w()
        if baseline_w is not None:
            mffr_power_w = abs(battery_power_w - baseline_w)
        else:
            mffr_power_w = 0.0
    except Exception:
        mffr_power_w = 0.0

    energy_kwh = round((mffr_power_w / 1000.0) * (10.0 / 3600.0), 5)

    grid_power_w = 0.0
    gs = get_sensor_state(SENSOR_GRID)
    if gs is not None:
        try:
            grid_power_w = float(gs)
        except ValueError:
            pass
    grid_kwh = round((grid_power_w / 1000.0) * (10.0 / 3600.0), 5)

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
        if (now - timeslot).total_seconds() < 5:
            return

        try:
            prev_slot_time = timeslot - timedelta(minutes=15)
            previous = db["slots"].get(prev_slot_time.isoformat())
            previous_end = datetime.fromisoformat(previous["end"])
            if previous["signal"] == signal and abs((now - previous_end).total_seconds()) <= 7:
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

    try:
        resp = requests.get(
            f"{HA_URL}/api/states/{SENSOR_NORDPOOL}",
            headers={"Authorization": f"Bearer {HA_TOKEN}", "Content-Type": "application/json"},
            timeout=5,
        )
        attrs = resp.json().get("attributes", {}) if resp.ok else {}
        raw_today = attrs.get("raw_today", []) or []
        raw_tomorrow = attrs.get("raw_tomorrow", []) or []
        for p in (raw_today + raw_tomorrow):
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

# Scheduler is started by FastAPI (api.py)
scheduler = BackgroundScheduler()
scheduler.add_job(write_current_timeslot, 'interval', seconds=10, max_instances=1, coalesce=True)
scheduler.add_job(cleanup_zero_min_rows, 'interval', minutes=1, max_instances=1, coalesce=True)