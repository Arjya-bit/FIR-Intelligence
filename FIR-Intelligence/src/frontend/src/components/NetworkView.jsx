import { useState, useEffect } from 'react';
import { api } from '../utils/api';

const NETWORK_COLORS = ['#ef4444', '#f59e0b', '#3b82f6', '#8b5cf6', '#22c55e'];

export default function NetworkView() {
  const [networks, setNetworks] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.getNetworks().then(setNetworks).finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="text-slate-400 text-center py-8">Mapping crime networks...</div>;

  return (
    <div className="animate-fade-in space-y-3">
      <div className="glass-card p-4 glow-red">
        <h2 className="text-lg font-semibold text-white mb-1">Crime Network Intelligence</h2>
        <p className="text-xs text-slate-400">
          Cross-FIR pattern analysis identified {networks.length} organized crime networks operating across UP
        </p>
      </div>

      {networks.map((net, i) => (
        <div key={i} className="glass-card p-5" style={{ borderLeft: `3px solid ${NETWORK_COLORS[i % NETWORK_COLORS.length]}` }}>
          <div className="flex items-start justify-between mb-4">
            <div>
              <div className="flex items-center gap-2 mb-1">
                <span className="w-2 h-2 rounded-full animate-pulse" style={{ backgroundColor: NETWORK_COLORS[i % NETWORK_COLORS.length] }}></span>
                <h3 className="font-bold text-lg" style={{ color: NETWORK_COLORS[i % NETWORK_COLORS.length] }}>
                  {net.name}
                </h3>
              </div>
              <p className="text-xs text-slate-400">Active: {net.active_period.start} to {net.active_period.end}</p>
            </div>
            <div className="text-right">
              <div className="text-3xl font-bold text-white">{net.fir_count}</div>
              <div className="text-xs text-slate-500">Linked FIRs</div>
            </div>
          </div>

          <div className="grid grid-cols-3 gap-4 mb-4">
            <div className="bg-slate-900/50 rounded-lg p-3">
              <h4 className="text-xs text-slate-500 mb-1">Districts</h4>
              <div className="flex flex-wrap gap-1">
                {net.districts.map((d, j) => (
                  <span key={j} className="text-xs px-2 py-0.5 rounded bg-blue-900/30 text-blue-300">{d}</span>
                ))}
              </div>
            </div>
            <div className="bg-slate-900/50 rounded-lg p-3">
              <h4 className="text-xs text-slate-500 mb-1">Crime Types</h4>
              <div className="flex flex-wrap gap-1">
                {net.crime_types.map((ct, j) => (
                  <span key={j} className="text-xs px-2 py-0.5 rounded bg-red-900/30 text-red-300">{ct.replace('_', ' ')}</span>
                ))}
              </div>
            </div>
            <div className="bg-slate-900/50 rounded-lg p-3">
              <h4 className="text-xs text-slate-500 mb-1">Linked FIRs</h4>
              <div className="flex flex-wrap gap-1">
                {net.fir_numbers.map((fn, j) => (
                  <span key={j} className="text-xs px-2 py-0.5 rounded bg-slate-800 text-slate-300 font-mono">{fn}</span>
                ))}
              </div>
            </div>
          </div>

          <NetworkGraph network={net} color={NETWORK_COLORS[i % NETWORK_COLORS.length]} />

          <div className="mt-4 bg-slate-900/30 rounded-lg p-3 border border-slate-700/50">
            <h4 className="text-xs font-semibold text-amber-400 mb-1">Intelligence Brief</h4>
            <p className="text-xs text-slate-400">
              {getNetworkBrief(net)}
            </p>
          </div>
        </div>
      ))}
    </div>
  );
}

function NetworkGraph({ network, color }) {
  const w = 500, h = 180;
  const cx = w / 2, cy = h / 2;
  const nodes = [
    { x: cx, y: cy, label: network.name.split(' ')[0], r: 24, isCenter: true },
  ];
  const links = [];

  const firNodes = network.fir_numbers.slice(0, 8);
  firNodes.forEach((fir, i) => {
    const angle = (2 * Math.PI * i) / firNodes.length - Math.PI / 2;
    const radius = 70;
    nodes.push({
      x: cx + radius * Math.cos(angle),
      y: cy + radius * Math.sin(angle),
      label: fir.split('/').pop(),
      r: 14,
      isCenter: false,
    });
    links.push({ from: 0, to: i + 1 });
  });

  return (
    <svg width="100%" viewBox={`0 0 ${w} ${h}`} className="mt-3">
      {links.map((link, i) => (
        <line
          key={i}
          x1={nodes[link.from].x} y1={nodes[link.from].y}
          x2={nodes[link.to].x} y2={nodes[link.to].y}
          stroke={color} strokeOpacity={0.3} strokeWidth={1.5}
        />
      ))}
      {nodes.map((node, i) => (
        <g key={i}>
          <circle
            cx={node.x} cy={node.y} r={node.r}
            fill={node.isCenter ? color : '#1e293b'}
            stroke={color}
            strokeWidth={node.isCenter ? 0 : 1.5}
            opacity={node.isCenter ? 0.9 : 0.8}
          />
          <text
            x={node.x} y={node.y}
            textAnchor="middle" dominantBaseline="central"
            fill={node.isCenter ? '#fff' : '#94a3b8'}
            fontSize={node.isCenter ? 9 : 8}
            fontWeight={node.isCenter ? 'bold' : 'normal'}
          >
            {node.label}
          </text>
        </g>
      ))}
    </svg>
  );
}

function getNetworkBrief(net) {
  const briefs = {
    'Jamtara Cyber Fraud Network': `Inter-state cyber fraud operation using "Vikram Sharma" alias for KYC/investment scams. Targets elderly and middle-class victims across ${net.districts.join(', ')}. Money trail leads to Jamtara/Deoghar, Jharkhand. Estimated total fraud: Rs. 2+ crore. Requires coordinated action with Jharkhand Cyber Cell.`,
    'Bablu Chain Snatching Gang': `Organized snatching gang operating in the Charbagh-Hazratganj corridor of Lucknow. Uses black Pulsar motorcycle (no plates), operates 2100-0000 hours, targets lone pedestrians near railway station. Escalating from snatching to armed robbery and vehicle theft.`,
    'Kanpur Commercial Burglary Ring': `Professional burglary gang targeting commercial establishments across Kanpur. Signature MO: gas cutter on shutters/locks, CCTV DVR removal, white Eeco van, early morning hours (0100-0400). Forensic evidence (tool marks, fingerprints) confirms same gang across all incidents. Estimated loot: Rs. 2+ crore.`,
    'Munna Bhai Extortion Gang': `Cross-district extortion racket operating in Varanasi and Prayagraj. Uses "Munna Bhai" as terror brand. Three-stage escalation: threatening calls, physical assault, arson/robbery on refusal. Expanding territory from tourist areas to new businesses.`,
    'Nepal Border Drug Supply Network': `Drug supply chain from Nepal border through Gorakhpur-Lucknow-Meerut. Multiple nodes arrested but supply chain continues. High-value seizures (15+ kg heroin) indicate major trafficking operation. Cross-border coordination needed.`,
  };
  return briefs[net.name] || `Organized network spanning ${net.districts.join(', ')} with ${net.fir_count} linked incidents.`;
}
