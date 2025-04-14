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
        try:
            slot_end = datetime.fromisoformat(row["slot_end"])
            if slot_end > now:
                continue  # skip ongoing slots
        except Exception:
            continue

        direction = row.get("signal")
        energy_kwh = row.get("energy_kwh")
        grid_kwh = row.get("grid_kwh")
        mffr_price = row.get("mffr_price")
        nordpool_price = row.get("nordpool_price")

        if direction is None or energy_kwh is None:
            continue

        profit = None
        update_fields = {}

        # Convert prices to €/kWh
        mffr = mffr_price / 1000 if mffr_price is not None else None
        nps = nordpool_price if nordpool_price is not None else None

        # 🔹 Profit (original logic)
        if mffr is not None and nps is not None:
            if direction == "DOWN":
                profit = (nps - mffr) * energy_kwh * 0.8
            elif direction == "UP":
                profit = (mffr - nps) * energy_kwh * 0.8

            if profit is not None:
                update_fields["profit"] = round(profit, 5)

        # 🔹 DOWN signal breakdown (if all relevant fields are present)
        if direction == "DOWN" and None not in (grid_kwh, mffr, nps):
            ffr_income_per_kwh = nps - mffr
            ffr_income = ffr_income_per_kwh * energy_kwh
            fusebox_fee = ffr_income_per_kwh * 0.2 * energy_kwh
            grid_cost = nps * 1.22 * grid_kwh
            net_total = ffr_income - fusebox_fee - grid_cost
            price_per_kwh = net_total / energy_kwh if energy_kwh else None

            update_fields.update({
                "ffr_income": round(ffr_income, 5),
                "fusebox_fee": round(fusebox_fee, 5),
                "grid_cost": round(grid_cost, 5),
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