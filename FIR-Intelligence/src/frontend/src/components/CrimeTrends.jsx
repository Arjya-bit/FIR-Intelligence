import { useState, useEffect } from 'react';
import { api } from '../utils/api';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend, AreaChart, Area } from 'recharts';

const COLORS = ['#3b82f6', '#ef4444', '#f59e0b', '#22c55e', '#8b5cf6', '#ec4899', '#06b6d4', '#f97316'];
const CRIME_LABELS = {
  robbery: 'Robbery', burglary: 'Burglary', fraud: 'Fraud', drug_offense: 'Drugs',
  kidnapping: 'Kidnapping', extortion: 'Extortion', cybercrime: 'Cyber',
  assault: 'Assault', murder: 'Murder', arson: 'Arson', dacoity: 'Dacoity', other: 'Other',
};

export default function CrimeTrends() {
  const [trends, setTrends] = useState({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.getTrends().then(setTrends).finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="text-slate-400 text-center py-8">Loading trends...</div>;

  const allCrimeTypes = new Set();
  Object.values(trends).forEach(monthData => {
    Object.keys(monthData).forEach(ct => allCrimeTypes.add(ct));
  });

  const stackedData = Object.entries(trends).map(([month, crimes]) => {
    const row = { month: month.slice(5) };
    allCrimeTypes.forEach(ct => { row[ct] = crimes[ct] || 0; });
    row.total = Object.values(crimes).reduce((s, v) => s + v, 0);
    return row;
  });

  const crimeTypeArray = Array.from(allCrimeTypes);

  const totalByCrime = {};
  Object.values(trends).forEach(monthData => {
    Object.entries(monthData).forEach(([ct, count]) => {
      totalByCrime[ct] = (totalByCrime[ct] || 0) + count;
    });
  });
  const sortedCrimes = Object.entries(totalByCrime).sort((a, b) => b[1] - a[1]);

  const months = Object.keys(trends);
  const firstMonth = months[0] || '';
  const lastMonth = months[months.length - 1] || '';

  const totalFIRs = Object.values(totalByCrime).reduce((s, v) => s + v, 0);
  const avgPerMonth = months.length ? (totalFIRs / months.length).toFixed(1) : 0;

  return (
    <div className="animate-fade-in space-y-3">
      <div className="glass-card p-4">
        <h2 className="text-lg font-semibold text-white mb-1">Crime Trend Analysis</h2>
        <p className="text-xs text-slate-400">Temporal analysis from {firstMonth} to {lastMonth} &middot; {totalFIRs} total FIRs &middot; {avgPerMonth} avg/month</p>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="glass-card p-4 glow-blue">
          <h3 className="text-sm font-semibold text-slate-300 mb-3">Monthly Crime Volume (Stacked)</h3>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={stackedData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis dataKey="month" tick={{ fill: '#94a3b8', fontSize: 11 }} />
              <YAxis tick={{ fill: '#94a3b8', fontSize: 11 }} />
              <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid #475569', borderRadius: '8px', fontSize: '12px' }} />
              <Legend wrapperStyle={{ fontSize: '11px' }} />
              {crimeTypeArray.map((ct, i) => (
                <Bar key={ct} dataKey={ct} stackId="crimes" fill={COLORS[i % COLORS.length]}
                     name={CRIME_LABELS[ct] || ct} />
              ))}
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="glass-card p-4 glow-blue">
          <h3 className="text-sm font-semibold text-slate-300 mb-3">Crime Volume Trend</h3>
          <ResponsiveContainer width="100%" height={300}>
            <AreaChart data={stackedData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis dataKey="month" tick={{ fill: '#94a3b8', fontSize: 11 }} />
              <YAxis tick={{ fill: '#94a3b8', fontSize: 11 }} />
              <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid #475569', borderRadius: '8px', fontSize: '12px' }} />
              <Area type="monotone" dataKey="total" stroke="#3b82f6" fill="#3b82f6" fillOpacity={0.2} strokeWidth={2} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="glass-card p-4">
        <h3 className="text-sm font-semibold text-slate-300 mb-3">Crime Type Ranking</h3>
        <div className="space-y-2">
          {sortedCrimes.map(([ct, count], i) => {
            const pct = totalFIRs > 0 ? (count / totalFIRs * 100) : 0;
            return (
              <div key={ct} className="flex items-center gap-3">
                <span className="text-xs text-slate-500 w-6 text-right">{i + 1}.</span>
                <span className="text-xs text-slate-300 w-24">{CRIME_LABELS[ct] || ct}</span>
                <div className="flex-1 h-5 bg-slate-800 rounded-full overflow-hidden">
                  <div
                    className="h-full rounded-full transition-all duration-500"
                    style={{ width: `${pct}%`, backgroundColor: COLORS[i % COLORS.length] }}
                  />
                </div>
                <span className="text-xs text-white w-8 text-right">{count}</span>
                <span className="text-xs text-slate-500 w-12 text-right">{pct.toFixed(1)}%</span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
