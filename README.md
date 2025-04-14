# MFFR Profit Tracker

Track Manual Frequency Restoration Reserve (MFFR) signals, power usage, prices, and profits in near real-time using Home Assistant, a simple FastAPI backend, and a React-based frontend.

## Development Environment Setup

### 1. Clone the Repository
```bash
git clone https://github.com/martinarva/mffr-profit-tracker.git
cd mffr-profit-tracker
```

### 2. Environment Configuration
Copy and edit the environment file:
```bash
cp .env.example .env
```

#### .env example:
```env
TZ=Europe/Tallinn
HA_URL=http://your-ha.local:8123
HA_TOKEN=your_long_token_here
SENSOR_MODE=input_select.battery_mode_selector
SENSOR_POWER=sensor.ss_battery_power
SENSOR_NORDPOOL=sensor.nordpool_kwh_ee_eur_3_10_0
```

#### Home Assistant Sensor Notes:
- `input_select.battery_mode_selector`: Should be set to **"Fusebox Buy"** for DOWN or **"Fusebox Sell"** for UP signals. Any other state means idle.
- `sensor.nordpool_kwh_ee_eur_3_10_0`: Nordpool integration sensor (no VAT/tariffs), price in €/kWh.
- `sensor.ss_battery_power`: Battery power sensor in **watts**.

#### MFFR Price Source:
- Public API: [https://tihend.energy/api/v1/frr](https://tihend.energy/api/v1/frr)

---

## Backend (Python + SQLite)

**Directory: `/backend`**

- `api.py`: FastAPI backend exposing `/api/mffr` to serve data.
- `main.py`: Polls Home Assistant every 10 seconds and writes to database.
- `mffr_price_updater.py`: Checks for entries missing MFFR prices and updates them from the API.
- `profit_calc.py`: Fills in profit fields when all necessary data is available.
- `data/mffr.db`: SQLite database storing all 15-min MFFR records.

---

## Frontend (Vite + React.js)

**Directory: `/frontend`**

- `src/App.jsx`: Main logic and UI implementation.

---

## Installation

```bash
docker compose up --build -d
```

### Access UI:
Open your browser at:
```
http://your-ip:5173/
```

### Logs:
```bash
docker logs -f mffr-profit   # Backend

docker logs -f mffr-ui       # Frontend
```

---

## Contributions
Pull requests are welcome! This is a simple tool meant to help track MFFR-based home battery strategies.

---

**License:** MIT

