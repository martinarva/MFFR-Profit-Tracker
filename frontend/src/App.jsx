import { useEffect, useState } from 'react';
import './App.css';

function App() {
  const [darkMode, setDarkMode] = useState(false);
  const [data, setData] = useState([]);
  const [filter, setFilter] = useState('today');
  const [customRange, setCustomRange] = useState({ from: '', to: '' });
  const safeFixed = (val, digits = 3, suffix = '€') =>
    typeof val === 'number' ? `${val.toFixed(digits)} ${suffix}` : '-';
  useEffect(() => {
    fetch('/api/mffr')
      .then((res) => res.json())
      .then((json) => {
        const enriched = Object.entries(json).map(([timeslot, entry]) => {
          const start = new Date(entry.start);
          const end = new Date(entry.end);
          const slotStart = new Date(timeslot);
          const slotEnd = new Date(slotStart);
          slotEnd.setMinutes(slotEnd.getMinutes() + 15);
  
          // Recalculate only if not provided
          const duration =
            entry.duration_min ?? Math.round((end - start) / 60000);
          const was_backup =
            entry.was_backup ??
            (start.getMinutes() % 15 !== 0 || start.getSeconds() > 10);
          const cancelled =
            entry.cancelled ??
            end.getTime() < slotEnd.getTime() - 11000; // 11 sec buffer
  
          const slot_end = entry.slot_end ?? slotEnd.toISOString();
  
          return {
            timeslot,
            ...entry,
            duration,
            slot_end,
            was_backup,
            cancelled,
            slot_date: slotStart.toLocaleDateString('et-EE'),
            slot_time: slotStart.toLocaleTimeString([], {
              hour: '2-digit',
              minute: '2-digit',
              hour12: false,
            }),
            slotStart,
          };
        });
        setData(enriched.reverse());
      });
  }, []);

  const now = new Date();
  const startOf = (unit) => {
    const d = new Date(now);
    if (unit === 'day') return new Date(d.setHours(0, 0, 0, 0));
    if (unit === 'week') {
      const day = d.getDay() || 7;
      d.setHours(0, 0, 0, 0);
      d.setDate(d.getDate() - day + 1);
      return d;
    }
    if (unit === 'month') return new Date(d.getFullYear(), d.getMonth(), 1);
  };

  const endOf = (unit) => {
    const d = new Date(now);
    if (unit === 'day') return new Date(d.setHours(23, 59, 59, 999));
    if (unit === 'week') {
      const start = startOf('week');
      return new Date(start.getFullYear(), start.getMonth(), start.getDate() + 6, 23, 59, 59, 999);
    }
    if (unit === 'month') return new Date(d.getFullYear(), d.getMonth() + 1, 0, 23, 59, 59, 999);
  };

  const getFilterRange = () => {
    switch (filter) {
      case 'today':
        return [startOf('day'), endOf('day')];
      case 'yesterday':
        const y = new Date(now);
        y.setDate(y.getDate() - 1);
        return [new Date(y.setHours(0, 0, 0, 0)), new Date(y.setHours(23, 59, 59, 999))];
      case 'this_week':
        return [startOf('week'), endOf('week')];
      case 'last_week':
        const sw = startOf('week');
        sw.setDate(sw.getDate() - 7);
        const ew = new Date(sw);
        ew.setDate(ew.getDate() + 6);
        return [sw, new Date(ew.setHours(23, 59, 59, 999))];
      case 'this_month':
        return [startOf('month'), endOf('month')];
      case 'last_month':
        const lm = new Date(now.getFullYear(), now.getMonth() - 1, 1);
        return [lm, new Date(now.getFullYear(), now.getMonth(), 0, 23, 59, 59, 999)];
      case 'custom':
        return [new Date(customRange.from), new Date(customRange.to)];
      default:
        return [null, null];
    }
  };

  const [from, to] = getFilterRange();
  const filteredData = data.filter((entry) => {
    if (!from || !to) return true;
    return entry.slotStart >= from && entry.slotStart <= to;
  });

  const summary = filteredData.reduce(
    (acc, entry) => {
      const signal = entry.signal;
      const energy = entry.energy_kwh || 0;
      const gridEnergy = entry.grid_kwh || 0;
      const profit = entry.profit || 0;
      const duration = entry.duration || 0;
      const isBackup = Boolean(entry.was_backup);
      const isCancelled = Boolean(entry.cancelled);
  
      const gridCost = entry.grid_cost || 0;
      const fuseboxFee = entry.fusebox_fee || 0;
      const ffrIncome = entry.ffr_income || 0;
      const netTotal = entry.net_total || 0;
      const pricePerKwh = typeof entry.price_per_kwh === 'number' ? entry.price_per_kwh : null;
  
      // Track totals
      acc.total.energy += energy;
      acc.total.grid_energy += gridEnergy;
      acc.total.profit += profit;
      acc.total.duration += duration;
      acc.total.backup += isBackup ? 1 : 0;
      acc.total.cancelled += isCancelled ? 1 : 0;
      acc.total.grid += gridCost;
      acc.total.fusebox += fuseboxFee;
      acc.total.ffr += ffrIncome;
      acc.total.net += netTotal;
      if (pricePerKwh !== null) {
        acc.total.priceSum += pricePerKwh;
        acc.total.priceCount += 1;
      }
  
      if (signal === 'UP') {
        acc.up.energy += energy;
        acc.up.grid_energy += gridEnergy;
        acc.up.profit += profit;
        acc.up.duration += duration;
        acc.up.count++;
        acc.up.backup += isBackup ? 1 : 0;
        acc.up.cancelled += isCancelled ? 1 : 0;
        acc.up.grid += gridCost;
        acc.up.fusebox += fuseboxFee;
        acc.up.ffr += ffrIncome;
        acc.up.net += netTotal;
        if (pricePerKwh !== null) {
          acc.up.priceSum += pricePerKwh;
          acc.up.priceCount += 1;
        }
      } else if (signal === 'DOWN') {
        acc.down.energy += energy;
        acc.down.grid_energy += gridEnergy;
        acc.down.profit += profit;
        acc.down.duration += duration;
        acc.down.count++;
        acc.down.backup += isBackup ? 1 : 0;
        acc.down.cancelled += isCancelled ? 1 : 0;
        acc.down.grid += gridCost;
        acc.down.fusebox += fuseboxFee;
        acc.down.ffr += ffrIncome;
        acc.down.net += netTotal;
        if (pricePerKwh !== null) {
          acc.down.priceSum += pricePerKwh;
          acc.down.priceCount += 1;
        }
      }
  
      acc.total.count++;
      return acc;
    },
    {
      up: {
        energy: 0, grid_energy: 0, profit: 0, duration: 0, count: 0,
        backup: 0, cancelled: 0, grid: 0, fusebox: 0, ffr: 0, net: 0, priceSum: 0, priceCount: 0
      },
      down: {
        energy: 0, grid_energy: 0, profit: 0, duration: 0, count: 0,
        backup: 0, cancelled: 0, grid: 0, fusebox: 0, ffr: 0, net: 0, priceSum: 0, priceCount: 0
      },
      total: {
        energy: 0, grid_energy: 0, profit: 0, duration: 0, count: 0,
        backup: 0, cancelled: 0, grid: 0, fusebox: 0, ffr: 0, net: 0, priceSum: 0, priceCount: 0
      },
    }
  );



  const formatVal = (val, digits = 2) => (val ? val.toFixed(digits) : '-');
  const percent = (count, total) => (total ? `${Math.round((count / total) * 100)}%` : '-');
  const formatDuration = (minutes) => {
    if (!minutes) return '-';
    const h = Math.floor(minutes / 60);
    const m = minutes % 60;
    return `${h}h ${m}min`;
  };

  const signalSplit = {
    up: percent(summary.up.count, summary.total.count),
    down: percent(summary.down.count, summary.total.count),
  };

  return (
    <div className={darkMode ? 'dark' : 'light'} style={{ padding: '2rem' }}>
      <h1 style={{ fontSize: '2rem', fontWeight: 'bold' }}>MFFR Profit Tracker</h1>

      <div style={{ marginBottom: '1rem' }}>
        <label>Filter:&nbsp;</label>
        <select value={filter} onChange={(e) => setFilter(e.target.value)}>
          <option value="all">All</option>
          <option value="today">Today</option>
          <option value="yesterday">Yesterday</option>
          <option value="this_week">This Week</option>
          <option value="last_week">Last Week</option>
          <option value="this_month">This Month</option>
          <option value="last_month">Last Month</option>
          <option value="custom">Custom Range</option>
        </select>
        {filter === 'custom' && (
          <>
            <input
              type="date"
              value={customRange.from}
              onChange={(e) => setCustomRange({ ...customRange, from: e.target.value })}
              style={{ marginLeft: '1rem' }}
            />
            <input
              type="date"
              value={customRange.to}
              onChange={(e) => setCustomRange({ ...customRange, to: e.target.value })}
              style={{ marginLeft: '0.5rem' }}
            />
          </>
        )}

        <button
          onClick={() => setDarkMode(!darkMode)}
          style={{
            marginLeft: '1rem',
            padding: '0.25rem 0.5rem',
            backgroundColor: darkMode ? '#eee' : '#333',
            color: darkMode ? '#000' : '#fff',
            border: '1px solid #888',
            borderRadius: '4px',
            cursor: 'pointer'
          }}
        >
          {darkMode ? 'Light Mode' : 'Dark Mode'}
        </button>
      </div>
      <h2 style={{ marginTop: '2rem' }}>
        Summary <span style={{ fontSize: '0.8rem', fontWeight: 'normal' }}>({filter.replaceAll('_', ' ')})</span>
      </h2>
      <table style={{ width: '100%', marginTop: '1rem', borderCollapse: 'collapse' }}>
        <thead>
        <tr style={{ textAlign: 'left', borderBottom: '2px solid #ddd' }}>
          <th></th>
          <th>Split</th>
          <th>Count</th>
          <th>Duration</th>
          <th>Battery (kWh)</th>
          <th>Grid (kWh)</th>
          <th>MFFR</th>
          <th>NPS</th>
          <th>Net</th>
          <th>Average</th>
          <th>Backup %</th>
          <th>Cancelled %</th>
        </tr>
        </thead>
        <tbody>
        <tr>
          <td><strong>DOWN</strong></td>
          <td data-label="Signal Split">{signalSplit.down}</td>
          <td data-label="Count">{summary.down.count}</td>
          <td data-label="Duration">{formatDuration(summary.down.duration)}</td>
          <td data-label="Battery">{formatVal(summary.down.energy)} kWh</td>
          <td data-label="Grid">{formatVal(summary.down.grid_energy)} kWh</td>
          <td data-label="MFFR" style={{ color: summary.down.profit >= 0 ? 'green' : 'red' }}>{formatVal(summary.down.profit, 2)} €</td>
          <td data-label="NPS" style={{ color: summary.down.grid * -1 >= 0 ? 'green' : 'red' }}>{formatVal(summary.down.grid * -1, 2)} €</td>
          <td data-label="Net" style={{ color: summary.down.net >= 0 ? 'green' : 'red' }}>{formatVal(summary.down.net, 2)} €</td>
          <td data-label="Average" style={{ color: summary.down.net >= 0 ? 'green' : 'red' }}>
            {summary.down.grid_energy ? Math.round(summary.down.net / summary.down.grid_energy * 1000) : '-'} €/MWh
          </td>
          <td data-label="Backup (%)"> {percent(summary.down.backup, summary.down.count)}</td>
          <td data-label="Cancelled (%)"> {percent(summary.down.cancelled, summary.down.count)}</td>
        </tr>
        <tr>
          <td><strong>UP</strong></td>
          <td data-label="Signal Split">{signalSplit.up}</td>
          <td data-label="Count">{summary.up.count}</td>
          <td data-label="Duration">{formatDuration(summary.up.duration)}</td>
          <td data-label="Battery">{formatVal(summary.up.energy)} kWh</td>
          <td data-label="Grid">{formatVal(summary.up.grid_energy)} kWh</td>
          <td data-label="MFFR" style={{ color: summary.up.profit >= 0 ? 'green' : 'red' }}>{formatVal(summary.up.profit, 2)} €</td>
          <td data-label="NPS" style={{ color: summary.up.grid * -1 >= 0 ? 'green' : 'red' }}>{formatVal(summary.up.grid * -1, 2)} €</td>
          <td data-label="Net" style={{ color: summary.up.net >= 0 ? 'green' : 'red' }}>{formatVal(summary.up.net, 2)} €</td>
          <td data-label="Average" style={{ color: summary.up.net >= 0 ? 'green' : 'red' }}>
            {summary.up.energy ? Math.round(summary.up.net / summary.up.energy * 1000) : '-'} €/MWh
          </td>
          <td data-label="Backup (%)"> {percent(summary.up.backup, summary.up.count)}</td>
          <td data-label="Cancelled (%)"> {percent(summary.up.cancelled, summary.up.count)}</td>
        </tr>
        <tr>
          <td><strong>Total</strong></td>
          <td></td>
          <td data-label="Count">{summary.total.count}</td>
          <td data-label="Duration">{formatDuration(summary.total.duration)}</td>
          <td data-label="Battery">{formatVal(summary.total.energy)} kWh</td>
          <td data-label="Grid">{formatVal(summary.total.grid_energy)} kWh</td>
          <td data-label="MFFR" style={{ color: summary.total.profit >= 0 ? 'green' : 'red' }}>{formatVal(summary.total.profit, 2)} €</td>
          <td data-label="NPS" style={{ color: summary.total.grid * -1 >= 0 ? 'green' : 'red' }}>{formatVal(summary.total.grid * -1, 2)} €</td>
          <td data-label="Net" style={{ color: summary.total.net >= 0 ? 'green' : 'red' }}>{formatVal(summary.total.net, 2)} €</td>
          <td></td>
          <td data-label="Backup (%)"> {percent(summary.total.backup, summary.total.count)}</td>
          <td data-label="Cancelled (%)"> {percent(summary.total.cancelled, summary.total.count)}</td>
        </tr>
        </tbody>
      </table>
      <table style={{ width: '100%', marginTop: '1rem', borderCollapse: 'collapse' }}>
        <thead>
          <tr style={{ textAlign: 'left', borderBottom: '2px solid #ddd' }}>
            <th>Date</th>
            <th>Time</th>
            <th>Signal</th>
            <th>Duration</th>
            <th>Battery (kWh)</th>
            <th>Grid (kWh)</th>
            <th>NPS €</th>
            <th>MFFR €</th>
            <th>Net</th>
            <th>€/MWh</th>
            <th>MFFR (€/MWh)</th>
            <th>NPS (€/MWh)</th>
            <th>Start</th>
            <th>End</th>            
            <th>Backup</th>
            <th>Cancelled</th>
          </tr>
        </thead>
        <tbody>
          {filteredData.map((entry, idx) => (
            <tr key={idx}>
              <td data-label="Date">{entry.slot_date}</td>
              <td data-label="Time">{entry.slot_time}</td>
              <td data-label="Signal" style={{ color: entry.signal === 'UP' ? 'green' : 'red', fontWeight: 'bold' }}>
                {entry.signal}
              </td>
              <td data-label="Duration">{entry.duration ?? '-'}</td>
              <td data-label="Battery (kWh)">{entry.energy_kwh?.toFixed(2)}</td>
              <td data-label="Grid (kWh)">{entry.grid_kwh?.toFixed(2)}</td>
              <td data-label="NPS (€)" style={{ color: entry.grid_cost * -1 >= 0 ? 'green' : 'red' }}>{safeFixed(entry.grid_cost * -1, 2)}</td>  
              <td data-label="MFFR (€)" style={{ color: entry.profit >= 0 ? 'green' : 'red' }}>
                {entry.profit === null ? '-' : `${entry.profit.toFixed(2)} €`}
              </td>
              <td data-label="Net (€)" style={{ color: entry.net_total >= 0 ? 'green' : 'red' }}>
                {safeFixed(entry.net_total, 2)}
              </td>
              <td data-label="€/MWh" style={{ color: entry.price_per_kwh >= 0 ? 'green' : 'red' }}>
                {typeof entry.price_per_kwh === 'number'
                  ? `${(entry.price_per_kwh * 1000).toFixed(2)}`
                  : '-'}
              </td>
              <td data-label="MFFR (€/MWh)">{entry.mffr_price === null ? '-' : entry.mffr_price}</td>
              <td data-label="NPS (€/MWh)">{entry.nordpool_price === null ? '-' : (entry.nordpool_price * 1000).toFixed(2)}</td>
              <td data-label="Start">
                {new Date(entry.start).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false })}
              </td>
              <td data-label="End">
                {(() => {
                  const endDate = new Date(entry.end);
                  if (endDate.getSeconds() > 0 || endDate.getMilliseconds() > 0) {
                    endDate.setMinutes(endDate.getMinutes() + 1);
                  }
                  endDate.setSeconds(0);
                  endDate.setMilliseconds(0);
                  return endDate.toLocaleTimeString([], {
                    hour: '2-digit',
                    minute: '2-digit',
                    hour12: false,
                  });
                })()}
              </td>
              <td data-label="Backup">{entry.was_backup === undefined ? '-' : entry.was_backup ? 'Yes' : 'No'}</td>
              <td data-label="Cancelled">{entry.cancelled === undefined ? '-' : entry.cancelled ? 'Yes' : 'No'}</td>        
            </tr>
          ))}
        </tbody>
      </table>

    </div>
  );
}

export default App;