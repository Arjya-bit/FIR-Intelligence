import { useState, useEffect } from 'react';
import { api } from '../utils/api';

const SEVERITY_COLORS = {
  critical: 'bg-red-500/20 text-red-400 border-red-500/30',
  high: 'bg-orange-500/20 text-orange-400 border-orange-500/30',
  medium: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
  low: 'bg-green-500/20 text-green-400 border-green-500/30',
};

function getSeverityLabel(score) {
  if (score >= 80) return 'critical';
  if (score >= 60) return 'high';
  if (score >= 40) return 'medium';
  return 'low';
}

export default function FIRList() {
  const [firs, setFirs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedFIR, setSelectedFIR] = useState(null);
  const [filter, setFilter] = useState({ crime_type: '', district: '' });

  useEffect(() => {
    const params = {};
    if (filter.crime_type) params.crime_type = filter.crime_type;
    if (filter.district) params.district = filter.district;
    api.getFIRs(params).then(setFirs).finally(() => setLoading(false));
  }, [filter]);

  if (loading) return <div className="text-slate-400 text-center py-8">Loading FIR records...</div>;

  return (
    <div className="animate-fade-in">
      <div className="glass-card p-4 mb-3">
        <div className="flex items-center gap-4">
          <h2 className="text-lg font-semibold text-white">FIR Records</h2>
          <select
            className="bg-slate-800 text-slate-300 text-sm border border-slate-600 rounded-lg px-3 py-1.5"
            value={filter.crime_type}
            onChange={e => setFilter(f => ({ ...f, crime_type: e.target.value }))}
          >
            <option value="">All Crime Types</option>
            <option value="robbery">Robbery</option>
            <option value="burglary">Burglary</option>
            <option value="fraud">Fraud</option>
            <option value="drug_offense">Drug Offense</option>
            <option value="kidnapping">Kidnapping</option>
            <option value="extortion">Extortion</option>
            <option value="cybercrime">Cybercrime</option>
            <option value="murder">Murder</option>
            <option value="assault">Assault</option>
          </select>
          <select
            className="bg-slate-800 text-slate-300 text-sm border border-slate-600 rounded-lg px-3 py-1.5"
            value={filter.district}
            onChange={e => setFilter(f => ({ ...f, district: e.target.value }))}
          >
            <option value="">All Districts</option>
            <option value="Lucknow">Lucknow</option>
            <option value="Kanpur">Kanpur</option>
            <option value="Agra">Agra</option>
            <option value="Varanasi">Varanasi</option>
            <option value="Gorakhpur">Gorakhpur</option>
            <option value="Meerut">Meerut</option>
            <option value="Prayagraj">Prayagraj</option>
          </select>
          <span className="text-sm text-slate-500 ml-auto">{firs.length} records</span>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-2">
        {firs.map(fir => (
          <div
            key={fir.fir_number}
            onClick={() => setSelectedFIR(selectedFIR?.fir_number === fir.fir_number ? null : fir)}
            className="glass-card p-4 cursor-pointer hover:border-blue-500/30 transition-all"
          >
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-3">
                <span className="text-sm font-mono font-semibold text-blue-400">{fir.fir_number}</span>
                <span className={`text-xs px-2 py-0.5 rounded-full border ${SEVERITY_COLORS[getSeverityLabel(fir.severity_score)]}`}>
                  {getSeverityLabel(fir.severity_score).toUpperCase()} ({fir.severity_score})
                </span>
                <span className="text-xs px-2 py-0.5 rounded-full bg-slate-700 text-slate-300">
                  {fir.crime_type?.replace('_', ' ').toUpperCase()}
                </span>
              </div>
              <span className="text-xs text-slate-500">{fir.date_filed}</span>
            </div>

            <div className="text-xs text-slate-400 flex gap-4">
              <span>PS: {fir.police_station}</span>
              <span>District: {fir.district}</span>
              <span>IPC: {fir.ipc_sections?.slice(0, 3).join(', ')}</span>
            </div>

            <p className="text-xs text-slate-500 mt-2 line-clamp-1">{fir.summary}</p>

            {selectedFIR?.fir_number === fir.fir_number && (
              <div className="mt-3 pt-3 border-t border-slate-700 space-y-3">
                {fir.accused?.length > 0 && (
                  <div>
                    <h4 className="text-xs font-semibold text-red-400 mb-1">Accused Persons</h4>
                    <div className="flex flex-wrap gap-2">
                      {fir.accused.map((a, i) => (
                        <span key={i} className="text-xs px-2 py-1 rounded bg-red-900/30 text-red-300 border border-red-800/30">
                          {a.name}{a.aliases?.length > 0 ? ` (alias: ${a.aliases.join(', ')})` : ''}{a.age ? `, age ${a.age}` : ''}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {fir.victims?.length > 0 && (
                  <div>
                    <h4 className="text-xs font-semibold text-blue-400 mb-1">Victims / Complainants</h4>
                    <div className="flex flex-wrap gap-2">
                      {fir.victims.map((v, i) => (
                        <span key={i} className="text-xs px-2 py-1 rounded bg-blue-900/30 text-blue-300 border border-blue-800/30">
                          {v.name}{v.age ? `, age ${v.age}` : ''}{v.gender ? ` (${v.gender})` : ''}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {fir.modus_operandi && (
                  <div>
                    <h4 className="text-xs font-semibold text-amber-400 mb-1">Modus Operandi</h4>
                    <p className="text-xs text-slate-400">{fir.modus_operandi.description}</p>
                    {fir.modus_operandi.weapon_used && (
                      <span className="text-xs text-red-400 mt-1 inline-block">Weapon: {fir.modus_operandi.weapon_used}</span>
                    )}
                  </div>
                )}

                {fir.location && (
                  <div>
                    <h4 className="text-xs font-semibold text-green-400 mb-1">Location</h4>
                    <p className="text-xs text-slate-400">{fir.location.place}, {fir.location.district}, {fir.location.state}</p>
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
