# api.py
import os
from typing import Optional
from datetime import datetime

import pytz
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlite_utils import Database

import main
import profit_calc
import mffr_price_updater

app = FastAPI()
DB_FILE = "data/mffr.db"

# ❌ remove the global connection:
# db = Database(DB_FILE)

LOCAL_TZ = pytz.timezone(os.getenv("TZ", "Europe/Tallinn"))

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def _normalize_to_local_iso(ts: Optional[str]) -> Optional[str]:
    if not ts:
        return None
    try:
        s = ts.strip().replace(" ", "T").replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = LOCAL_TZ.localize(dt)
    return dt.astimezone(LOCAL_TZ).isoformat()

@app.get("/api/mffr")
def get_mffr_data(
    from_ts: Optional[str] = Query(None, alias="from"),
    to_ts:   Optional[str] = Query(None, alias="to"),
    limit:   int = Query(1000, ge=1, le=50000),
):
    # ✅ fresh handle per request/thread
    _db = Database(DB_FILE)

    if "slots" not in _db.table_names():
        return {}

    nf = _normalize_to_local_iso(from_ts)
    nt = _normalize_to_local_iso(to_ts)

    where = []
    params = []
    if nf:
        where.append("timeslot >= ?")
        params.append(nf)
    if nt:
        where.append("timeslot <= ?")
        params.append(nt)
    where_clause = " AND ".join(where) if where else "1=1"

    try:
        rows = list(
            _db["slots"].rows_where(
                where_clause,
                where_args=params,          # ← correct keyword
                order_by="timeslot desc",
                limit=None if (nf or nt) else limit,
            )
        )
    except Exception as e:
        print(f"DB query failed: where='{where_clause}' args={params} err={e}")
        raise

    return {row["timeslot"]: row for row in rows}

@app.on_event("startup")
def start_all_schedulers():
    print("✅ Starting all schedulers from FastAPI")
    main.write_current_timeslot()
    profit_calc.run_profit_calculation()
    mffr_price_updater.fetch_and_update_mffr_prices()
    if not main.scheduler.running:
        main.scheduler.start()
    if not profit_calc.scheduler.running:
        profit_calc.scheduler.start()
    if not mffr_price_updater.scheduler.running:
        mffr_price_updater.scheduler.start()