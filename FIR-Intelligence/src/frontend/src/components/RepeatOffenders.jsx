import { useState, useEffect } from 'react';
import { api } from '../utils/api';

const RISK_STYLES = {
  critical: { bg: 'bg-red-500/20', text: 'text-red-400', border: 'border-red-500/30', dot: 'bg-red-500' },
  high: { bg: 'bg-orange-500/20', text: 'text-orange-400', border: 'border-orange-500/30', dot: 'bg-orange-500' },
  medium: { bg: 'bg-yellow-500/20', text: 'text-yellow-400', border: 'border-yellow-500/30', dot: 'bg-yellow-500' },
  low: { bg: 'bg-green-500/20', text: 'text-green-400', border: 'border-green-500/30', dot: 'bg-green-500' },
};

export default function RepeatOffenders() {
  const [offenders, setOffenders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState(null);

  useEffect(() => {
    api.getRepeatOffenders().then(setOffenders).finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="text-slate-400 text-center py-8">Detecting repeat offenders...</div>;

  return (
    <div className="animate-fade-in">
      <div className="glass-card p-4 mb-3 glow-red">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold text-white">Flagged Repeat Offenders</h2>
            <p className="text-xs text-slate-400 mt-1">Cross-FIR entity matching with fuzzy name resolution and MO fingerprinting</p>
          </div>
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse"></span>
            <span className="text-sm text-red-400 font-semibold">{offenders.length} Flagged</span>
          </div>
        </div>
      </div>

      <div className="space-y-3">
        {offenders.map((ro, i) => {
          const style = RISK_STYLES[ro.risk_level] || RISK_STYLES.low;
          const isExpanded = expanded === i;

          return (
            <div
              key={i}
              className={`glass-card p-4 cursor-pointer transition-all ${isExpanded ? 'border-red-500/40' : ''}`}
              onClick={() => setExpanded(isExpanded ? null : i)}
            >
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-3">
                  <div className={`w-10 h-10 rounded-full flex items-center justify-center text-lg font-bold ${style.bg} ${style.text}`}>
                    {ro.name.charAt(0)}
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-white">{ro.name}</span>
                      <span className={`text-xs px-2 py-0.5 rounded-full border ${style.bg} ${style.text} ${style.border}`}>
                        {ro.risk_level.toUpperCase()}
                      </span>
                    </div>
                    {ro.aliases.length > 0 && (
                      <p className="text-xs text-slate-500 mt-0.5">
                        Aliases: {ro.aliases.join(', ')}
                      </p>
                    )}
                  </div>
                </div>

                <div className="text-right">
                  <div className="text-2xl font-bold text-white">{ro.total_incidents}</div>
                  <div className="text-xs text-slate-500">Linked FIRs</div>
                </div>
              </div>

              <div className="mt-3 flex gap-4 text-xs text-slate-400">
                <span>Confidence: <span className="text-white">{(ro.confidence_score * 100).toFixed(0)}%</span></span>
                <span>Districts: <span className="text-white">{ro.districts.join(', ')}</span></span>
                <span>Crimes: <span className="text-white">{ro.crime_types.join(', ')}</span></span>
              </div>

              {ro.mo_signature && (
                <div className="mt-2 text-xs text-amber-400/80">
                  MO Signature: {ro.mo_signature}
                </div>
              )}

              {isExpanded && (
                <div className="mt-4 pt-3 border-t border-slate-700 space-y-3">
                  <div>
                    <h4 className="text-xs font-semibold text-blue-400 mb-2">Linked FIR Numbers</h4>
                    <div className="flex flex-wrap gap-2">
                      {ro.linked_firs.map((fir, j) => (
                        <span key={j} className="text-xs px-2 py-1 rounded bg-blue-900/30 text-blue-300 font-mono border border-blue-800/30">
                          {fir}
                        </span>
                      ))}
                    </div>
                  </div>

                  <div>
                    <h4 className="text-xs font-semibold text-green-400 mb-2">Police Stations Involved</h4>
                    <div className="flex flex-wrap gap-2">
                      {ro.stations.map((st, j) => (
                        <span key={j} className="text-xs px-2 py-1 rounded bg-green-900/30 text-green-300 border border-green-800/30">
                          {st}
                        </span>
                      ))}
                    </div>
                  </div>

                  <div className="flex gap-4 text-xs text-slate-400">
                    <span>First seen: <span className="text-white">{ro.first_seen || 'N/A'}</span></span>
                    <span>Last seen: <span className="text-white">{ro.last_seen || 'N/A'}</span></span>
                  </div>

                  <div className="bg-red-950/30 rounded-lg p-3 border border-red-900/30">
                    <h4 className="text-xs font-semibold text-red-400 mb-1">Intelligence Assessment</h4>
                    <p className="text-xs text-slate-400">
                      {ro.risk_level === 'critical' && `CRITICAL THREAT: ${ro.name} is a serial offender operating across ${ro.districts.length} districts with ${ro.total_incidents} confirmed incidents. Immediate inter-district coordination required.`}
                      {ro.risk_level === 'high' && `HIGH RISK: ${ro.name} shows persistent criminal behavior across ${ro.stations.length} police stations. Enhanced surveillance and coordinated operations recommended.`}
                      {ro.risk_level === 'medium' && `MEDIUM RISK: ${ro.name} has been linked to ${ro.total_incidents} FIRs. Pattern monitoring and intelligence sharing across districts advised.`}
                      {ro.risk_level === 'low' && `MONITORING: ${ro.name} has preliminary linkages to ${ro.total_incidents} FIRs. Continued monitoring recommended.`}
                    </p>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
