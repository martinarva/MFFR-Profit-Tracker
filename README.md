**MFFR Profit Tracker**
=======================

Track Manual Frequency Restoration Reserve (MFFR) signals, power usage, prices, and profits in near real-time using Home Assistant, a simple FastAPI backend, and a React-based frontend.

* * * * *

**Development Environment Setup**
---------------------------------

### **1\. Clone the Repository**

```
git clone https://github.com/martinarva/mffr-profit-tracker.git
cd mffr-profit-tracker
```

### **2\. Environment Configuration**

Copy and edit the environment file:

```
cp .env.example .env
```

#### **.env example:**

```
TZ=Europe/Tallinn
HA_URL=http://your-ha.local:8123
HA_TOKEN=your_long_token_here
SENSOR_MODE=input_select.battery_mode_selector
SENSOR_POWER=sensor.ss_battery_power
SENSOR_GRID=sensor.ss_grid_power
SENSOR_NORDPOOL=sensor.nordpool_kwh_ee_eur_3_10_0
```

#### **Home Assistant Sensor Notes:**

-   input_select.battery_mode_selector: Should be set to **"Fusebox Buy"** for DOWN or **"Fusebox Sell"** for UP signals. Any other state means idle.

-   sensor.nordpool_kwh_ee_eur_3_10_0: Nordpool integration sensor (no VAT/tariffs), price in €/kWh.

-   sensor.ss_battery_power: Battery power sensor in **watts**. Negative = charging, positive = discharging.

-   sensor.ss_grid_power: Grid power sensor in **watts**. Negative = exporting to grid, positive = importing from grid.

* * * * *

**Baseline Tracking (NEW)**
---------------------------

A new background service baseline.py has been added:

-   Runs every 10 seconds.

-   Accumulates **battery power** during idle (no MFFR signal) periods.

-   At the end of each 15-minute slot, calculates and stores the **average baseline power**.

-   Deletes old baseline data on startup to avoid stale values.

This baseline is used by main.py to calculate **MFFR power**:

```
MFFR Power (W) = abs(battery_power - baseline)
```

This ensures we only measure the portion of battery power that deviates from normal operation during an MFFR signal.

✅ No need to configure SENSOR_BASELINE or SENSOR_MFFR_POWER anymore --- these are now fully handled internally.

* * * * *

**Backend (Python + SQLite)**
-----------------------------

**Directory: /backend**

-   api.py: FastAPI backend exposing /api/mffr to serve data.

-   main.py: Polls Home Assistant every 10 seconds and writes MFFR signal data to the database.

-   baseline.py: Tracks normal battery power usage during idle periods and stores average power per slot.

-   mffr_price_updater.py: Fills in missing MFFR prices from the public API.

-   profit_calc.py: Calculates profit when all required fields are present.

-   data/mffr.db: SQLite database storing all 15-min MFFR records.

* * * * *

**Frontend (Vite + React.js)**
------------------------------

**Directory: /frontend**

-   src/App.jsx: Main logic and UI implementation.

* * * * *

**Installation**
----------------

```
docker compose up --build -d
```

### **Access UI:**

Open your browser at:

```
http://your-ip:5173/
```

### **Logs:**

```
docker logs -f mffr-profit   # Backend

docker logs -f mffr-ui       # Frontend
```

* * * * *

**Contributions**
-----------------

Pull requests are welcome! This is a simple tool meant to help track MFFR-based home battery strategies.

* * * * *

**License:** MIT
