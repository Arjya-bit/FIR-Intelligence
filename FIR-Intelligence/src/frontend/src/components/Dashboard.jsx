import { PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, LineChart, Line, CartesianGrid, Legend } from 'recharts';

const COLORS = ['#3b82f6', '#ef4444', '#f59e0b', '#22c55e', '#8b5cf6', '#ec4899', '#06b6d4', '#f97316', '#14b8a6', '#6366f1'];

const CRIME_LABELS = {
  robbery: 'Robbery', burglary: 'Burglary', fraud: 'Fraud', drug_offense: 'Drug Offense',
  kidnapping: 'Kidnapping', extortion: 'Extortion', cybercrime: 'Cybercrime',
  assault: 'Assault', murder: 'Murder', arson: 'Arson', dacoity: 'Dacoity',
  theft: 'Theft', other: 'Other',
};

export default function Dashboard({ data }) {
  if (!data) return null;

  const crimeData = Object.entries(data.crime_breakdown).map(([key, val]) => ({
    name: CRIME_LABELS[key] || key, value: val,
  })).sort((a, b) => b.value - a.value);

  const districtData = Object.entries(data.district_breakdown).map(([key, val]) => ({
    name: key, value: val,
  })).sort((a, b) => b.value - a.value);

  const trendData = Object.entries(data.monthly_trend).map(([month, count]) => ({
    month: month.slice(5), count,
  }));

  const severityData = Object.entries(data.severity_distribution).map(([key, val]) => ({
    name: key.charAt(0).toUpperCase() + key.slice(1), value: val,
  }));
  const severityColors = { Low: '#22c55e', Medium: '#f59e0b', High: '#f97316', Critical: '#ef4444' };

  return (
    <div className="animate-fade-in space-y-3">
      <div className="grid grid-cols-4 gap-3">
        <StatCard title="Total FIRs" value={data.total_firs} icon="📋" color="blue" />
        <StatCard title="Accused Identified" value={data.total_accused} icon="👤" color="amber" />
        <StatCard title="Repeat Offenders" value={data.repeat_offenders_count} icon="🔴" color="red" pulse />
        <StatCard title="Crime Networks" value={data.crime_networks?.length || 0} icon="🕸" color="purple" />
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="glass-card p-4 glow-blue">
          <h3 className="text-sm font-semibold text-slate-300 mb-3">Crime Type Distribution</h3>
          <ResponsiveContainer width="100%" height={260}>
            <PieChart>
              <Pie data={crimeData} cx="50%" cy="50%" outerRadius={95} innerRadius={55} dataKey="value" label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`} labelLine={false} fontSize={10}>
                {crimeData.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
              </Pie>
              <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid #475569', borderRadius: '8px', fontSize: '12px' }} />
            </PieChart>
          </ResponsiveContainer>
        </div>

        <div className="glass-card p-4 glow-blue">
          <h3 className="text-sm font-semibold text-slate-300 mb-3">District-wise FIR Count</h3>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={districtData} layout="vertical" margin={{ left: 20 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis type="number" tick={{ fill: '#94a3b8', fontSize: 11 }} />
              <YAxis type="category" dataKey="name" tick={{ fill: '#94a3b8', fontSize: 11 }} width={80} />
              <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid #475569', borderRadius: '8px', fontSize: '12px' }} />
              <Bar dataKey="value" fill="#3b82f6" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="glass-card p-4">
          <h3 className="text-sm font-semibold text-slate-300 mb-3">Monthly Crime Trend</h3>
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={trendData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis dataKey="month" tick={{ fill: '#94a3b8', fontSize: 11 }} />
              <YAxis tick={{ fill: '#94a3b8', fontSize: 11 }} />
              <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid #475569', borderRadius: '8px', fontSize: '12px' }} />
              <Line type="monotone" dataKey="count" stroke="#3b82f6" strokeWidth={2} dot={{ fill: '#3b82f6', r: 4 }} activeDot={{ r: 6 }} />
            </LineChart>
          </ResponsiveContainer>
        </div>

        <div className="glass-card p-4">
          <h3 className="text-sm font-semibold text-slate-300 mb-3">Severity Distribution</h3>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={severityData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis dataKey="name" tick={{ fill: '#94a3b8', fontSize: 11 }} />
              <YAxis tick={{ fill: '#94a3b8', fontSize: 11 }} />
              <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid #475569', borderRadius: '8px', fontSize: '12px' }} />
              <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                {severityData.map((entry, i) => <Cell key={i} fill={severityColors[entry.name] || '#64748b'} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {data.crime_networks && data.crime_networks.length > 0 && (
        <div className="glass-card p-4 glow-red">
          <h3 className="text-sm font-semibold text-red-400 mb-3">Identified Crime Networks</h3>
          <div className="grid grid-cols-2 gap-3">
            {data.crime_networks.map((net, i) => (
              <div key={i} className="bg-slate-900/50 rounded-lg p-3 border border-red-900/30">
                <div className="flex items-center gap-2 mb-2">
                  <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse"></span>
                  <span className="font-semibold text-sm text-red-300">{net.name}</span>
                </div>
                <div className="text-xs text-slate-400 space-y-1">
                  <div>FIRs Linked: <span className="text-white">{net.fir_count}</span></div>
                  <div>Districts: <span className="text-white">{net.districts.join(', ')}</span></div>
                  <div>Active: <span className="text-white">{net.active_period.start} to {net.active_period.end}</span></div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function StatCard({ title, value, icon, color, pulse }) {
  const glowClass = `glow-${color}`;
  const colorMap = {
    blue: 'text-blue-400 bg-blue-500/10 border-blue-500/20',
    red: 'text-red-400 bg-red-500/10 border-red-500/20',
    amber: 'text-amber-400 bg-amber-500/10 border-amber-500/20',
    green: 'text-green-400 bg-green-500/10 border-green-500/20',
    purple: 'text-purple-400 bg-purple-500/10 border-purple-500/20',
  };

  return (
    <div className={`glass-card p-4 ${glowClass} ${pulse ? 'pulse-danger' : ''}`}>
      <div className="flex items-center justify-between mb-2">
        <span className="text-2xl">{icon}</span>
        <span className={`text-xs px-2 py-0.5 rounded-full border ${colorMap[color] || ''}`}>
          Live
        </span>
      </div>
      <div className="text-3xl font-bold text-white">{value}</div>
      <div className="text-xs text-slate-400 mt-1">{title}</div>
    </div>
  );
}
