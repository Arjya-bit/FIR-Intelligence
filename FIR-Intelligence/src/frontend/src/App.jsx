import { useState, useEffect } from 'react';
import { api } from './utils/api';
import Dashboard from './components/Dashboard';
import FIRList from './components/FIRList';
import RepeatOffenders from './components/RepeatOffenders';
import CrimeTrends from './components/CrimeTrends';
import StationSummary from './components/StationSummary';
import NetworkView from './components/NetworkView';
import BobChat from './components/BobChat';
import ReportView from './components/ReportView';

const NAV_ITEMS = [
  { id: 'dashboard', label: 'Dashboard', icon: '📊' },
  { id: 'firs', label: 'FIR Records', icon: '📋' },
  { id: 'offenders', label: 'Repeat Offenders', icon: '🔴' },
  { id: 'trends', label: 'Crime Trends', icon: '📈' },
  { id: 'stations', label: 'Station Analysis', icon: '🏢' },
  { id: 'networks', label: 'Crime Networks', icon: '🕸' },
  { id: 'report', label: 'Intelligence Report', icon: '📝' },
  { id: 'chat', label: 'Bob AI Chat', icon: '🤖' },
];

export default function App() {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [dashboardData, setDashboardData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.getDashboard()
      .then(setDashboardData)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const renderContent = () => {
    if (loading) return <LoadingState />;
    if (error) return <ErrorState error={error} />;

    switch (activeTab) {
      case 'dashboard': return <Dashboard data={dashboardData} />;
      case 'firs': return <FIRList />;
      case 'offenders': return <RepeatOffenders />;
      case 'trends': return <CrimeTrends />;
      case 'stations': return <StationSummary />;
      case 'networks': return <NetworkView />;
      case 'report': return <ReportView />;
      case 'chat': return <BobChat />;
      default: return <Dashboard data={dashboardData} />;
    }
  };

  return (
    <div className="min-h-screen bg-slate-950">
      <header className="glass-card mx-4 mt-4 mb-3 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-blue-600 flex items-center justify-center text-white font-bold text-lg">
            FI
          </div>
          <div>
            <h1 className="text-xl font-bold text-white">FIR Intelligence & Crime Pattern Detector</h1>
            <p className="text-xs text-slate-400">Powered by IBM Bob AI &middot; Track 4: AI & Predictive</p>
          </div>
        </div>
        <div className="flex items-center gap-4">
          <span className="text-xs px-3 py-1 rounded-full bg-green-900/50 text-green-400 border border-green-800">
            System Online
          </span>
          <span className="text-xs text-slate-500">
            {dashboardData ? `${dashboardData.total_firs} FIRs Loaded` : 'Loading...'}
          </span>
        </div>
      </header>

      <div className="flex mx-4 gap-3" style={{ height: 'calc(100vh - 100px)' }}>
        <nav className="glass-card w-56 shrink-0 p-3 overflow-y-auto">
          {NAV_ITEMS.map(item => (
            <button
              key={item.id}
              onClick={() => setActiveTab(item.id)}
              className={`w-full text-left px-3 py-2.5 rounded-lg mb-1 text-sm flex items-center gap-2.5 transition-all ${
                activeTab === item.id
                  ? 'bg-blue-600/20 text-blue-400 border border-blue-500/30'
                  : 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-200 border border-transparent'
              }`}
            >
              <span className="text-base">{item.icon}</span>
              {item.label}
            </button>
          ))}
        </nav>

        <main className="flex-1 overflow-y-auto pb-4">
          {renderContent()}
        </main>
      </div>
    </div>
  );
}

function LoadingState() {
  return (
    <div className="flex items-center justify-center h-96">
      <div className="text-center">
        <div className="w-12 h-12 border-4 border-blue-500 border-t-transparent rounded-full animate-spin mx-auto mb-4"></div>
        <p className="text-slate-400">Analyzing FIR data with IBM Bob AI...</p>
        <p className="text-slate-500 text-sm mt-1">Extracting entities, detecting patterns, classifying crimes</p>
      </div>
    </div>
  );
}

function ErrorState({ error }) {
  return (
    <div className="flex items-center justify-center h-96">
      <div className="glass-card p-8 text-center max-w-md glow-red">
        <div className="text-4xl mb-4">⚠️</div>
        <h3 className="text-lg font-semibold text-red-400 mb-2">Connection Error</h3>
        <p className="text-slate-400 text-sm mb-4">{error}</p>
        <p className="text-slate-500 text-xs">Make sure the backend server is running on port 8000</p>
        <button
          onClick={() => window.location.reload()}
          className="mt-4 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700"
        >
          Retry
        </button>
      </div>
    </div>
  );
}
