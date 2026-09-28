import { useState, useEffect } from 'react';
import { api } from '../utils/api';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';

export default function StationSummary() {
  const [stations, setStations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedStation, setSelectedStation] = useState(null);

  useEffect(() => {
    api.getStations().then(setStations).finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="text-slate-400 text-center py-8">Loading station data...</div>;

  const riskColor = (risk) => {
    if (risk?.startsWith('HIGH')) return 'text-red-400 bg-red-500/10 border-red-500/20';
    if (risk?.startsWith('MEDIUM')) return 'text-yellow-400 bg-yellow-500/10 border-yellow-500/20';
    return 'text-green-400 bg-green-500/10 border-green-500/20';
  };

  return (
    <div className="animate-fade-in space-y-3">
      <div className="glass-card p-4">
        <h2 className="text-lg font-semibold text-white mb-1">Station-Level Analysis</h2>
        <p className="text-xs text-slate-400">{stations.length} police stations analyzed across UP</p>
      </div>

      <div className="grid grid-cols-2 gap-3">
        {stations.map((st, i) => (
          <div
            key={i}
            onClick={() => setSelectedStation(selectedStation === i ? null : i)}
            className={`glass-card p-4 cursor-pointer transition-all ${selectedStation === i ? 'border-blue-500/40 glow-blue' : 'hover:border-slate-600'}`}
          >
            <div className="flex items-center justify-between mb-3">
              <div>
                <h3 className="font-semibold text-white text-sm">{st.station_name}</h3>
                <p className="text-xs text-slate-500">{st.district}</p>
              </div>
              <div className="text-right">
                <div className="text-2xl font-bold text-white">{st.total_firs}</div>
                <div className="text-xs text-slate-500">FIRs</div>
              </div>
            </div>

            <div className="flex items-center gap-2 mb-3">
              <span className={`text-xs px-2 py-0.5 rounded-full border ${riskColor(st.risk_assessment)}`}>
                {st.risk_assessment?.split(' - ')[0]}
              </span>
              <span className="text-xs text-slate-400">
                Top: <span className="text-white">{st.top_crime?.replace('_', ' ')}</span>
              </span>
              {st.repeat_offenders_count > 0 && (
                <span className="text-xs px-2 py-0.5 rounded-full bg-red-500/10 text-red-400 border border-red-500/20">
                  {st.repeat_offenders_count} repeat offender{st.repeat_offenders_count > 1 ? 's' : ''}
                </span>
              )}
            </div>

            <div className="flex flex-wrap gap-1 mb-3">
              {Object.entries(st.crime_breakdown || {}).map(([ct, count]) => (
                <span key={ct} className="text-xs px-2 py-0.5 rounded bg-slate-800 text-slate-400">
                  {ct.replace('_', ' ')}: {count}
                </span>
              ))}
            </div>

            {selectedStation === i && (
              <div className="mt-3 pt-3 border-t border-slate-700 space-y-3">
                {Object.keys(st.monthly_trend || {}).length > 0 && (
                  <div>
                    <h4 className="text-xs font-semibold text-blue-400 mb-2">Monthly Trend</h4>
                    <ResponsiveContainer width="100%" height={150}>
                      <BarChart data={Object.entries(st.monthly_trend).map(([m, c]) => ({ month: m.slice(5), count: c }))}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                        <XAxis dataKey="month" tick={{ fill: '#94a3b8', fontSize: 10 }} />
                        <YAxis tick={{ fill: '#94a3b8', fontSize: 10 }} />
                        <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid #475569', borderRadius: '8px', fontSize: '11px' }} />
                        <Bar dataKey="count" fill="#3b82f6" radius={[3, 3, 0, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                )}

                {st.hotspot_areas?.length > 0 && (
                  <div>
                    <h4 className="text-xs font-semibold text-amber-400 mb-1">Hotspot Areas</h4>
                    <div className="flex flex-wrap gap-1">
                      {st.hotspot_areas.map((area, j) => (
                        <span key={j} className="text-xs px-2 py-0.5 rounded bg-amber-900/20 text-amber-400 border border-amber-800/20">
                          {area}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                <div className="bg-slate-900/50 rounded-lg p-3">
                  <h4 className="text-xs font-semibold text-slate-300 mb-1">Risk Assessment</h4>
                  <p className="text-xs text-slate-400">{st.risk_assessment}</p>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
