from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import main  # Contains scheduler and logic
import profit_calc
import mffr_price_updater  # ✅ NEW
from sqlite_utils import Database

app = FastAPI()
DB_FILE = "data/mffr.db"

# Allow frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/mffr")
def get_mffr_data():
    db = Database(DB_FILE)  # Open new DB connection in this thread
    if "slots" not in db.table_names():
        return {}

    rows = db["slots"].rows
    return {row["timeslot"]: row for row in rows}

@app.on_event("startup")
def start_all_schedulers():
    print("✅ Starting all schedulers from FastAPI")

    # Initial tasks
    main.write_current_timeslot()
    profit_calc.run_profit_calculation()
    mffr_price_updater.fetch_and_update_mffr_prices()  # ✅ Initial run

    if not main.scheduler.running:
        print("▶️ Starting main scheduler")
        main.scheduler.start()

    if not profit_calc.scheduler.running:
        print("▶️ Starting profit scheduler")
        profit_calc.scheduler.start()

    if not mffr_price_updater.scheduler.running:
        print("▶️ Starting MFFR price scheduler")
        mffr_price_updater.scheduler.start()