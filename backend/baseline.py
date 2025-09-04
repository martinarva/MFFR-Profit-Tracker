# backend/baseline.py
import os
from datetime import datetime
import pytz
import requests
from apscheduler.schedulers.background import BackgroundScheduler
from sqlite_utils import Database

DB_PATH = "data/mffr.db"
tz = pytz.timezone("Europe/Tallinn")

HA_URL   = os.getenv("HA_URL", "http://localhost:8123")
HA_TOKEN = os.getenv("HA_TOKEN")

SENSOR_MODE  = os.environ["SENSOR_MODE"]
SENSOR_POWER = os.environ["SENSOR_POWER"]

def dlog(msg: str):
    print(f"[baseline] {datetime.now(tz).isoformat()}  {msg}")

def _open_db() -> Database:
    db = Database(DB_PATH)
    try:
        db.conn.execute("PRAGMA journal_mode=WAL;")
        db.conn.execute("PRAGMA synchronous=NORMAL;")
        db.conn.execute("PRAGMA busy_timeout=5000;")
    except Exception:
        pass
    return db

def _ensure_schema():
    db = _open_db()
    try:
        db["baseline_state"].create({
            "key": str,
            "baseline_w": float,
            "computed_for_slot": str,
            "energy_Wh": float,
            "updated_at": str
        }, pk="key", if_not_exists=True)
    finally:
        try:
            db.conn.close()
        except Exception:
            pass

_ensure_schema()

def reset_baseline_table():
    try:
        db = Database(DB_PATH)
        db["baseline_state"].delete_where("1=1")
        db.conn.commit()
        print("🧹 Cleared baseline_state on startup")
    except Exception as e:
        print(f"❌ Failed to clear baseline_state: {e}")

reset_baseline_table()

_prev_t = None
_prev_p = None
accum_Wh = 0.0
saw_mffr = False
current_slot = None

def _mode_to_signal(mode: str | None):
    if not mode:
        return None
    m = mode.strip().lower()
    if m in {"fusebox buy", "kratt buy"}:
        return "DOWN"
    if m in {"fusebox sell", "kratt sell"}:
        return "UP"
    return None

def _slot_anchor(dt: datetime):
    return dt.replace(minute=(dt.minute // 15) * 15, second=0, microsecond=0)

def _ha_state(entity_id: str):
    try:
        r = requests.get(
            f"{HA_URL}/api/states/{entity_id}",
            headers={"Authorization": f"Bearer {HA_TOKEN}", "Content-Type": "application/json"},
            timeout=5
        )
        if not r.ok:
            return None
        s = r.json().get("state")
        return None if s in ("unknown", "unavailable", None) else s
    except Exception:
        return None

def tick():
    global _prev_t, _prev_p, accum_Wh, saw_mffr, current_slot
    now = datetime.now(tz)
    slot = _slot_anchor(now)

    if current_slot is None:
        current_slot = slot

    if slot > current_slot:
        EPS = 1e-6
        if abs(accum_Wh) > EPS and not saw_mffr:
            avg_w = round((accum_Wh * 3600.0) / 900.0, 2)
            try:
                db = _open_db()
                with db.conn:
                    db["baseline_state"].upsert({
                        "key": "latest",
                        "baseline_w": avg_w,
                        "computed_for_slot": current_slot.isoformat(),
                        "energy_Wh": round(accum_Wh, 3),
                        "updated_at": now.isoformat()
                    }, pk="key")
                dlog(f"Updated baseline: {avg_w} W (slot {current_slot.isoformat()}, energy {accum_Wh:.3f} Wh)")
            except Exception:
                pass
            finally:
                try:
                    db.conn.close()
                except Exception:
                    pass

        current_slot = slot
        _prev_t = None
        _prev_p = None
        accum_Wh = 0.0
        saw_mffr = False

    p = _ha_state(SENSOR_POWER)
    if p is not None:
        try:
            p = float(p)
        except ValueError:
            p = None

    mode = _ha_state(SENSOR_MODE)
    sig = _mode_to_signal(mode)
    if sig and not saw_mffr:
        saw_mffr = True

    if p is not None:
        if _prev_t is not None and _prev_p is not None:
            dt_s = (now - _prev_t).total_seconds()
            if dt_s > 0:
                dE = (_prev_p * dt_s) / 3600.0
                accum_Wh += dE
        _prev_t = now
        _prev_p = p

scheduler = BackgroundScheduler()
scheduler.add_job(tick, "interval", seconds=10, max_instances=1, coalesce=True)

if __name__ == "__main__":
    print("▶️ baseline service started")
    scheduler.start()
    import time
    while True:
        time.sleep(3600)