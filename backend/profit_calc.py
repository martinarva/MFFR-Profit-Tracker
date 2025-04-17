from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
import pytz
from sqlite_utils import Database

DB_PATH = "data/mffr.db"
tz = pytz.timezone("Europe/Tallinn")

scheduler = BackgroundScheduler()


def run_profit_calculation():
    db = Database(DB_PATH)
    now = datetime.now(tz)
    updated = False

    for row in db["slots"].rows_where("profit IS NULL OR net_total IS NULL"):
    #for row in db["slots"].rows:
        try:
            slot_end = datetime.fromisoformat(row["slot_end"])
            if slot_end > now:
                continue  # Skip ongoing slots
        except Exception:
            continue

        direction = row.get("signal")
        energy_kwh = row.get("energy_kwh")
        grid_kwh = row.get("grid_kwh")
        mffr = row.get("mffr_price")
        nps = row.get("nordpool_price")

        if direction is None or energy_kwh is None:
            continue

        update_fields = {}

        # 🔹 DOWN = charging battery from grid or PV
        if direction == "DOWN" and None not in (grid_kwh, mffr, nps):
            profit = (nps - mffr / 1000) * energy_kwh * 0.8
            fusebox_fee = profit / 4
            grid_cost = nps * 1.22 * grid_kwh
            net_total = profit - fusebox_fee - grid_cost
            price_per_kwh = net_total / grid_kwh if grid_kwh and grid_kwh > 0 else None

            update_fields.update({
                "profit": round(profit, 5),
                "fusebox_fee": round(fusebox_fee, 5),
                "grid_cost": round(grid_cost, 5),
                "net_total": round(net_total, 5),
                "price_per_kwh": round(price_per_kwh, 5) if price_per_kwh is not None else None,
            })

        # 🔹 UP = discharging battery (possibly selling to grid)
        elif direction == "UP" and None not in (grid_kwh, mffr, nps):
            profit = (mffr / 1000 - nps) * energy_kwh * 0.8
            fusebox_fee = profit / 4
            grid_income = nps * grid_kwh  # grid_kwh is negative for export
            net_total = profit + grid_income * -1
            price_per_kwh = net_total / energy_kwh if energy_kwh else None

            update_fields.update({
                "profit": round(profit, 5),
                "fusebox_fee": round(fusebox_fee, 5),
                "grid_cost": round(grid_income, 5),  # legacy name
                "net_total": round(net_total, 5),
                "price_per_kwh": round(price_per_kwh, 5) if price_per_kwh is not None else None,
            })

        if update_fields:
            db["slots"].update(row["timeslot"], update_fields, alter=True)
            updated = True
            print(f"📊 Updated slot {row['timeslot']} → {update_fields}")

    if updated:
        print("✅ Profit + financial breakdown updated.")

scheduler.add_job(run_profit_calculation, "interval", minutes=1)