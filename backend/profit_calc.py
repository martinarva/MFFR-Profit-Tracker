from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
import pytz
from sqlite_utils import Database

DB_PATH = "data/mffr.db"
tz = pytz.timezone("Europe/Tallinn")

scheduler = BackgroundScheduler()

def run_profit_calculation():
    db = Database(DB_PATH)  # 🔄 Create DB connection inside the thread
    now = datetime.now(tz)
    updated = False

    for row in db["slots"].rows_where("profit IS NULL"):
        try:
            slot_end = datetime.fromisoformat(row["slot_end"])
            if slot_end > now:
                continue  # Skip ongoing slots
        except Exception:
            continue

        if not all(k in row for k in ["signal", "energy_kwh", "mffr_price", "nordpool_price"]):
            continue
        if any(row[k] is None for k in ["signal", "energy_kwh", "mffr_price", "nordpool_price"]):
            continue

        mffr = row["mffr_price"] / 1000  # Convert to €/kWh
        nps = row["nordpool_price"]
        kwh = row["energy_kwh"]
        direction = row["signal"]

        profit = None
        if direction == "DOWN":
            profit = (nps - mffr) * kwh * 0.8
        elif direction == "UP":
            profit = (mffr - nps) * kwh * 0.8

        if profit is not None:
            rounded_profit = round(profit, 5)
            db["slots"].update(
                row["timeslot"], 
                {"profit": rounded_profit},
                alter=True,
            )
            updated = True
            print(f"💰 {direction} | Slot: {row['timeslot']} | Profit: {rounded_profit} €")

    if updated:
        print("✅ Profit values updated in SQLite DB.")

scheduler.add_job(run_profit_calculation, "interval", minutes=1)