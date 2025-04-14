import { useEffect, useState } from 'react';
import './App.css';

function App() {
  const [data, setData] = useState([]);
  const [filter, setFilter] = useState('today');
  const [customRange, setCustomRange] = useState({ from: '', to: '' });

  useEffect(() => {
    fetch('http://192.168.1.12:8099/api/mffr')
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
      const profit = entry.profit || 0;
      const duration = entry.duration || 0;
      const isBackup = Boolean(entry.was_backup);
      const isCancelled = Boolean(entry.cancelled);

      acc.total.energy += energy;
      acc.total.profit += profit;
      acc.total.duration += duration;
      acc.total.backup += isBackup ? 1 : 0;
      acc.total.cancelled += isCancelled ? 1 : 0;

      if (signal === 'UP') {
        acc.up.energy += energy;
        acc.up.profit += profit;
        acc.up.duration += duration;
        acc.up.count++;
        acc.up.backup += isBackup ? 1 : 0;
        acc.up.cancelled += isCancelled ? 1 : 0;
      } else if (signal === 'DOWN') {
        acc.down.energy += energy;
        acc.down.profit += profit;
        acc.down.duration += duration;
        acc.down.count++;
        acc.down.backup += isBackup ? 1 : 0;
        acc.down.cancelled += isCancelled ? 1 : 0;
      }

      acc.total.count++;
      return acc;
    },
    {
      up: { energy: 0, profit: 0, duration: 0, count: 0, backup: 0, cancelled: 0 },
      down: { energy: 0, profit: 0, duration: 0, count: 0, backup: 0, cancelled: 0 },
      total: { energy: 0, profit: 0, duration: 0, count: 0, backup: 0, cancelled: 0 },
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
    <div style={{ padding: '2rem' }}>
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
      </div>

      <table style={{ width: '100%', marginTop: '1rem', borderCollapse: 'collapse' }}>
        <thead>
          <tr style={{ textAlign: 'left', borderBottom: '2px solid #ddd' }}>
            <th>Date</th>
            <th>Time</th>
            <th>Signal</th>
            <th>Energy (kWh)</th>
            <th>Profit</th>
            <th>MFFR (€/mWh)</th>
            <th>NPS (€/mWh)</th>
            <th>Start</th>
            <th>End</th>
            <th>Duration</th>
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
              <td data-label="Energy (kWh)">{entry.energy_kwh?.toFixed(2)}</td>
              <td data-label="Profit">{entry.profit === null ? '-' : `${entry.profit.toFixed(3)} €`}</td>
              <td data-label="MFFR (€/mWh)">{entry.mffr_price === null ? '-' : entry.mffr_price}</td>
              <td data-label="NPS (€/mWh)">{entry.nordpool_price === null ? '-' : (entry.nordpool_price * 1000).toFixed(2)}</td>
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
              <td data-label="Duration">{entry.duration ?? '-'}</td>
              <td data-label="Backup">{entry.was_backup === undefined ? '-' : entry.was_backup ? 'Yes' : 'No'}</td>
              <td data-label="Cancelled">{entry.cancelled === undefined ? '-' : entry.cancelled ? 'Yes' : 'No'}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h2 style={{ marginTop: '2rem' }}>
        Summary <span style={{ fontSize: '0.8rem', fontWeight: 'normal' }}>({filter.replaceAll('_', ' ')})</span>
      </h2>
      <table style={{ width: '100%', marginTop: '1rem', borderCollapse: 'collapse' }}>
        <thead>
          <tr style={{ textAlign: 'left', borderBottom: '2px solid #ddd' }}>
            <th></th>
            <th>Split</th>
            <th>Count</th>
            <th>Energy (kWh)</th>
            <th>Profit (€)</th>
            <th>Duration</th>
            <th>Backup %</th>
            <th>Cancelled %</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td data-label="Type"><strong>DOWN</strong></td>
            <td>{signalSplit.down}</td>
            <td data-label="Count">{summary.down.count}</td>
            <td data-label="Energy (kWh)">{formatVal(summary.down.energy)}</td>
            <td data-label="Profit (€)">{formatVal(summary.down.profit, 3)}</td>
            <td data-label="Duration">{formatDuration(summary.down.duration)}</td>
            <td data-label="Backup %">{percent(summary.down.backup, summary.down.count)}</td>
            <td data-label="Cancelled %">{percent(summary.down.cancelled, summary.down.count)}</td>
          </tr>
          <tr>
            <td data-label="Type"><strong>UP</strong></td>
            <td>{signalSplit.up}</td>
            <td data-label="Count">{summary.up.count}</td>
            <td data-label="Energy (kWh)">{formatVal(summary.up.energy)}</td>
            <td data-label="Profit (€)">{formatVal(summary.up.profit, 3)}</td>
            <td data-label="Duration">{formatDuration(summary.up.duration)}</td>
            <td data-label="Backup %">{percent(summary.up.backup, summary.up.count)}</td>
            <td data-label="Cancelled %">{percent(summary.up.cancelled, summary.up.count)}</td>
          </tr>
          <tr>
            <td data-label="Type"><strong>Total</strong></td>
            <td></td>
            <td data-label="Count">{summary.total.count}</td>
            <td data-label="Energy (kWh)">{formatVal(summary.total.energy)}</td>
            <td data-label="Profit (€)">{formatVal(summary.total.profit, 3)}</td>
            <td data-label="Duration">{formatDuration(summary.total.duration)}</td>
            <td data-label="Backup %">{percent(summary.total.backup, summary.total.count)}</td>
            <td data-label="Cancelled %">{percent(summary.total.cancelled, summary.total.count)}</td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}

export default App;