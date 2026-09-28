/**
 * FIR Intelligence dashboard.
 *
 * This is the SOURCE file. The browser loads the precompiled `app.js`;
 * regenerate it after editing with `./scripts/build-ui.sh`.
 */
const {useState,useEffect,useCallback,useMemo,useRef} = React;
const {PieChart,Pie,Cell,BarChart,Bar,AreaChart,Area,XAxis,YAxis,CartesianGrid,
       Tooltip,ResponsiveContainer,RadarChart,Radar,PolarGrid,PolarAngleAxis,
       PolarRadiusAxis} = Recharts;

const API = '/api';
const COLORS = ['#5b9bff','#fb5a75','#1fc08f','#f7a53b','#b49bff','#3cddf0','#f887c4',
                '#fd9c52','#14b8a6','#6366f1','#818cf8','#e11d48','#84cc16','#0ea5e9','#d946ef'];
const RISK_COLOR = {critical:'#fb5a75',high:'#fd9c52',medium:'#f7a53b',low:'#1fc08f'};
const CHART_TOOLTIP = {
  contentStyle:{background:'#151d35',border:'1px solid #243058',borderRadius:'10px',
                color:'#edf2ff',fontSize:'13px',boxShadow:'0 8px 24px rgba(0,0,0,.4)'},
  itemStyle:{color:'#9dafd4'},labelStyle:{color:'#edf2ff'},
};

// `String.replace` with a string pattern only swaps the FIRST match, so
// multi-underscore keys were rendering half-formatted.
const label = (s) => String(s || '').split('_').join(' ');
const titleCase = (s) => label(s).replace(/\b\w/g, (c) => c.toUpperCase());

/** fetch + JSON with real error propagation (the old helper returned null on
 *  every failure, so the UI could not tell "empty" from "broken"). */
async function apiGet(path, signal) {
  const res = await fetch(API + path, {signal});
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try { const body = await res.json(); if (body.detail) detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail); }
    catch (e) { /* non-JSON error body */ }
    throw new Error(detail);
  }
  return res.json();
}

/**
 * Consume a server-sent-event stream over fetch.
 *
 * `EventSource` only issues GET requests and cannot send a JSON body, so the
 * chat stream (a POST carrying the question and conversation history) has to be
 * read off the response body and framed by hand.
 */
async function streamSSE(path, {method = 'GET', body, signal, onEvent}) {
  const res = await fetch(API + path, {
    method,
    headers: body ? {'Content-Type':'application/json'} : undefined,
    body: body ? JSON.stringify(body) : undefined,
    signal,
  });
  if (!res.ok || !res.body) throw new Error(`Stream failed: HTTP ${res.status}`);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  for (;;) {
    const {done, value} = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, {stream:true});

    // Frames are separated by a blank line; keep the trailing partial frame.
    const frames = buffer.split('\n\n');
    buffer = frames.pop() ?? '';
    for (const frame of frames) {
      let event = 'message';
      let data = '';
      for (const line of frame.split('\n')) {
        if (line.startsWith('event:')) event = line.slice(6).trim();
        else if (line.startsWith('data:')) data += line.slice(5).trim();
      }
      if (!data) continue;
      try { onEvent(event, JSON.parse(data)); }
      catch (e) { /* keep-alive or partial frame */ }
    }
  }
}

const GREETING = {role:'assistant', greeting:true, content:
  'I am the FIR Intelligence assistant. I answer from the analysed corpus — ' +
  'crime patterns, repeat offenders, criminal networks, station caseloads and ' +
  'individual FIRs.\n\nAsk about a specific FIR number, a named accused, a ' +
  'district, or pick a suggestion.'};

const CHAT_SUGGESTIONS = [
  'What are the top crime patterns?',
  'Who are the repeat offenders?',
  'Which districts have the highest caseload?',
  'Show the organised crime networks',
  'Which FIRs are most severe?',
  'Summarise station activity',
];

/**
 * Streaming chat state. Owned by the app shell so the conversation is shared
 * between the Ask Bob tab and the floating widget, and survives tab switches.
 */
function useChatEngine() {
  const [messages, setMessages] = useState([GREETING]);
  const [busy, setBusy] = useState(false);
  const abortRef = useRef(null);
  // History is read inside an async callback; a ref avoids re-creating `send`
  // on every message and reading a stale list.
  const messagesRef = useRef(messages);
  messagesRef.current = messages;

  const patchLast = useCallback((patch) => {
    setMessages((prev) => {
      const next = prev.slice();
      const last = next[next.length - 1];
      next[next.length - 1] = typeof patch === 'function' ? patch(last) : {...last, ...patch};
      return next;
    });
  }, []);

  const send = useCallback(async (text) => {
    const message = String(text ?? '').trim();
    if (!message || abortRef.current) return;

    const history = messagesRef.current
      .filter((m) => !m.greeting && !m.error && m.content)
      .slice(-8)
      .map((m) => ({role:m.role, content:m.content}));

    setMessages((prev) => [...prev,
      {role:'user', content:message},
      {role:'assistant', content:'', streaming:true}]);
    setBusy(true);

    const controller = new AbortController();
    abortRef.current = controller;
    try {
      await streamSSE('/chat/stream', {
        method:'POST', body:{message, history}, signal:controller.signal,
        onEvent: (event, data) => {
          if (event === 'start') patchLast({source:data.source, model:data.model});
          else if (event === 'delta') patchLast((m) => ({...m, content:m.content + data.text}));
          else if (event === 'fallback') patchLast({fallback:data.reason, content:''});
          else if (event === 'done') patchLast({streaming:false, firs:data.firs_referenced || []});
        },
      });
      patchLast({streaming:false});
    } catch (err) {
      if (err.name === 'AbortError') {
        patchLast((m) => ({...m, streaming:false,
          content:m.content + (m.content ? '\n\n[stopped]' : '[stopped]')}));
      } else {
        patchLast({streaming:false, error:true,
          content:`Could not reach the intelligence service: ${err.message}`});
      }
    } finally {
      abortRef.current = null;
      setBusy(false);
    }
  }, [patchLast]);

  const stop = useCallback(() => abortRef.current?.abort(), []);
  const reset = useCallback(() => { abortRef.current?.abort(); setMessages([GREETING]); }, []);

  return {messages, busy, send, stop, reset};
}

function useApi(path, deps = []) {
  const [state, setState] = useState({data:null, error:null, loading:true});
  const [nonce, setNonce] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    setState((s) => ({...s, loading:true, error:null}));
    apiGet(path, controller.signal)
      .then((data) => { if (active) setState({data, error:null, loading:false}); })
      .catch((err) => {
        if (!active || err.name === 'AbortError') return;
        setState({data:null, error:err.message || 'Request failed', loading:false});
      });
    return () => { active = false; controller.abort(); };
  }, [path, nonce, ...deps]);
  return {...state, reload: () => setNonce((n) => n + 1)};
}

function Spinner({label:text = 'Loading'}) {
  return <div role="status" aria-live="polite" style={{display:'flex',flexDirection:'column',
      alignItems:'center',gap:12,padding:'70px 0'}}>
    <div className="spinner"/><span className="muted">{text}…</span>
  </div>;
}

function ErrorState({error, onRetry}) {
  return <div className="glass p-5" role="alert" style={{textAlign:'center',padding:'40px 20px'}}>
    <p style={{fontSize:34,marginBottom:10}} aria-hidden="true">⚠</p>
    <h2 style={{fontSize:17,fontWeight:700,marginBottom:6}}>Could not load this view</h2>
    <p className="muted" style={{marginBottom:16}}>{error}</p>
    {onRetry && <button className="btn btn-primary" onClick={onRetry}>Retry</button>}
  </div>;
}

function EmptyState({title, hint, action}) {
  return <div className="glass p-5" style={{textAlign:'center',padding:'46px 20px'}}>
    <p style={{fontSize:30,marginBottom:10}} aria-hidden="true">∅</p>
    <h2 style={{fontSize:16,fontWeight:700,marginBottom:6}}>{title}</h2>
    {hint && <p className="muted">{hint}</p>}
    {action && <div style={{marginTop:16}}>{action}</div>}
  </div>;
}

/** One place that decides loading vs error vs empty vs content. Previously each
 *  tab returned a spinner when its list was empty, so a legitimately empty or
 *  failed response span forever. */
function Async({state, isEmpty, empty, children}) {
  if (state.loading) return <Spinner/>;
  if (state.error) return <ErrorState error={state.error} onRetry={state.reload}/>;
  if (isEmpty && isEmpty(state.data)) return empty || <EmptyState title="Nothing to show"/>;
  return children(state.data);
}

function StatCard({label:text, value, sub, color, icon}) {
  return <div className="glass p-5">
    <div style={{display:'flex',justifyContent:'space-between',alignItems:'flex-start',gap:10}}>
      <div style={{minWidth:0}}>
        <p style={{color:'var(--text2)',fontSize:13,fontWeight:600,marginBottom:6}}>{text}</p>
        <p style={{fontSize:30,fontWeight:700,color,lineHeight:1.1}}>{value}</p>
        {sub && <p style={{fontSize:12,color:'var(--text3)',marginTop:4}}>{sub}</p>}
      </div>
      <div aria-hidden="true" style={{width:40,height:40,borderRadius:10,background:color+'22',
        display:'flex',alignItems:'center',justifyContent:'center',fontSize:19,flexShrink:0}}>{icon}</div>
    </div>
  </div>;
}

function SectionCard({title, subtitle, children, actions}) {
  return <section className="glass p-5">
    <div style={{display:'flex',justifyContent:'space-between',alignItems:'flex-start',
                 gap:12,marginBottom:14,flexWrap:'wrap'}}>
      <div>
        <h2 style={{fontSize:15,fontWeight:700}}>{title}</h2>
        {subtitle && <p className="muted" style={{marginTop:2}}>{subtitle}</p>}
      </div>
      {actions}
    </div>
    {children}
  </section>;
}

// ── Crime type drill-down ──────────────────────────────────────────────────

/** Small labelled bar list — used for districts, stations, sections, MO. */
function MiniBars({rows, keyField, max, color = 'var(--blue)'}) {
  if (!rows?.length) return <p className="muted" style={{fontSize:12}}>Not recorded.</p>;
  const top = max || rows[0].count || 1;
  return <div style={{display:'flex',flexDirection:'column',gap:6}}>
    {rows.map((row, i) =>
      <div key={i} style={{display:'flex',alignItems:'center',gap:10}}>
        <span style={{flex:'0 0 46%',fontSize:12,overflow:'hidden',textOverflow:'ellipsis',
              whiteSpace:'nowrap'}} title={row[keyField]}>{row[keyField]}</span>
        <div style={{flex:1,background:'var(--bg2)',borderRadius:12,height:16,overflow:'hidden'}}>
          <div style={{height:'100%',borderRadius:12,background:color,
               width:`${Math.max((row.count / top) * 100, 8)}%`}}/>
        </div>
        <span style={{flex:'0 0 26px',textAlign:'right',fontSize:12,fontWeight:700}}>{row.count}</span>
      </div>)}
  </div>;
}

/**
 * Everything behind one slice of the crime distribution chart.
 * Fetched on demand rather than shipped with the dashboard payload, which
 * would mean sending every breakdown for every crime type on first load.
 */
function CrimeDrilldown({crimeType, onClose, onOpenFIR}) {
  const state = useApi(`/crime-types/${encodeURIComponent(crimeType)}`);
  const closeRef = useRef(null);
  useEffect(() => { closeRef.current?.focus(); }, [crimeType]);

  return <section className="glass p-5 fade-in" aria-live="polite"
      style={{borderColor:'rgba(91,155,255,.4)'}}>
    <Async state={state}>{(d) => <>
      <div style={{display:'flex',justifyContent:'space-between',alignItems:'flex-start',
           gap:12,flexWrap:'wrap',marginBottom:14}}>
        <div>
          <h2 style={{fontSize:17,fontWeight:700,textTransform:'capitalize'}}>{d.label}</h2>
          <p className="muted">{d.total} FIRs · {d.share_percent}% of the corpus ·
            {' '}{d.date_range.start} → {d.date_range.end}</p>
        </div>
        <button ref={closeRef} className="btn btn-ghost" onClick={onClose}>Close ×</button>
      </div>

      <div className="metric-grid" style={{marginBottom:16}}>
        {[['FIRs', d.total, 'var(--blue)'],
          ['Avg severity', d.avg_severity, 'var(--amber)'],
          ['Peak severity', d.max_severity, 'var(--red)'],
          ['Accused named', d.accused_count, 'var(--purple)'],
          ['Victims', d.victim_count, 'var(--green)'],
          ['Districts', d.districts.length, 'var(--cyan)']].map(([k, v, c]) =>
          <div key={k} style={{padding:10,borderRadius:8,background:'var(--bg2)',textAlign:'center'}}>
            <p className="muted" style={{fontSize:11}}>{k}</p>
            <p style={{fontWeight:700,fontSize:19,color:c}}>{v}</p>
          </div>)}
      </div>

      <div style={{display:'flex',gap:14,flexWrap:'wrap',marginBottom:16}}>
        {['critical','high','medium','low'].map((band) =>
          <span key={band} style={{display:'flex',alignItems:'center',gap:6,fontSize:12,
                color:'var(--text2)'}}>
            <span aria-hidden="true" style={{width:10,height:10,borderRadius:3,
                  background:RISK_COLOR[band]}}/>
            {band}: {d.severity_distribution[band]}
          </span>)}
      </div>

      <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(260px,1fr))',gap:18}}>
        <div>
          <h3 style={{fontSize:13,fontWeight:700,marginBottom:8,color:'var(--cyan)'}}>Districts</h3>
          <MiniBars rows={d.districts.slice(0, 7)} keyField="name" color="var(--cyan)"/>
        </div>
        <div>
          <h3 style={{fontSize:13,fontWeight:700,marginBottom:8,color:'var(--blue)'}}>Stations</h3>
          <MiniBars rows={d.stations.slice(0, 7)} keyField="name" color="var(--blue)"/>
        </div>
        <div>
          <h3 style={{fontSize:13,fontWeight:700,marginBottom:8,color:'var(--purple)'}}>
            Sections invoked</h3>
          <MiniBars rows={d.ipc_sections.slice(0, 7)} keyField="section" color="var(--purple)"/>
        </div>
        <div>
          <h3 style={{fontSize:13,fontWeight:700,marginBottom:8,color:'var(--amber)'}}>
            Modus operandi</h3>
          <MiniBars rows={d.modus_operandi} keyField="method" color="var(--amber)"/>
          {d.weapons.length > 0 && <>
            <h3 style={{fontSize:13,fontWeight:700,margin:'12px 0 8px',color:'var(--red)'}}>
              Weapons</h3>
            <MiniBars rows={d.weapons} keyField="weapon" color="var(--red)"/>
          </>}
        </div>
      </div>

      {Object.keys(d.monthly_trend).length > 1 &&
        <div style={{marginTop:18}}>
          <h3 style={{fontSize:13,fontWeight:700,marginBottom:8}}>Monthly trend</h3>
          <ResponsiveContainer width="100%" height={150}>
            <AreaChart data={Object.entries(d.monthly_trend).map(([m, v]) => ({month:m, count:v}))}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1c2748"/>
              <XAxis dataKey="month" stroke="#9dafd4" tick={{fontSize:10}}/>
              <YAxis stroke="#9dafd4" tick={{fontSize:10}} width={28} allowDecimals={false}/>
              <Tooltip {...CHART_TOOLTIP}/>
              <Area type="monotone" dataKey="count" stroke="#5b9bff"
                    fill="rgba(91,155,255,.18)" strokeWidth={2} isAnimationActive={false}/>
            </AreaChart>
          </ResponsiveContainer>
        </div>}

      {d.repeat_offenders.length > 0 && <div style={{marginTop:18}}>
        <h3 style={{fontSize:13,fontWeight:700,marginBottom:8,color:'var(--red)'}}>
          Repeat offenders in this category</h3>
        <div style={{display:'flex',flexDirection:'column',gap:6}}>
          {d.repeat_offenders.map((o, i) =>
            <div key={i} style={{display:'flex',alignItems:'center',gap:10,flexWrap:'wrap',
                 padding:'8px 10px',borderRadius:8,background:'var(--bg2)'}}>
              <span style={{fontWeight:700,fontSize:13}}>{o.name}</span>
              {o.aliases?.length > 0 &&
                <span className="muted" style={{fontSize:11}}>alias {o.aliases.join(', ')}</span>}
              <span className={`badge badge-${o.risk_level}`}>{o.risk_level}</span>
              <span className="muted" style={{fontSize:11}}>
                {o.linked_firs_in_type.length} of {o.total_incidents} FIRs here ·
                {' '}{o.districts.join(', ')}</span>
            </div>)}
        </div>
      </div>}

      {d.networks.length > 0 && <div style={{marginTop:18}}>
        <h3 style={{fontSize:13,fontWeight:700,marginBottom:8,color:'var(--green)'}}>
          Networks involved</h3>
        <div style={{display:'flex',flexWrap:'wrap',gap:8}}>
          {d.networks.map((n, i) =>
            <span key={i} style={{padding:'6px 12px',borderRadius:10,background:'var(--bg2)',
                  fontSize:12,border:'1px solid var(--border)'}}>
              <strong>{n.name}</strong>
              <span className="muted"> · {n.matching_firs.length} of {n.fir_count} FIRs</span>
            </span>)}
        </div>
      </div>}

      <div style={{marginTop:18}}>
        <h3 style={{fontSize:13,fontWeight:700,marginBottom:8}}>
          Highest-severity FIRs</h3>
        <div style={{display:'flex',flexDirection:'column',gap:6}}>
          {d.top_firs.map((f) =>
            <button key={f.fir_number} className="row-card" style={{padding:'10px 12px'}}
                    onClick={() => onOpenFIR(f.fir_number)}>
              <div style={{display:'flex',justifyContent:'space-between',gap:8,flexWrap:'wrap'}}>
                <span style={{display:'flex',gap:8,alignItems:'center',flexWrap:'wrap'}}>
                  <span style={{fontFamily:'ui-monospace,Menlo,monospace',color:'var(--blue)',
                        fontWeight:700,fontSize:12}}>{f.fir_number}</span>
                  <span className={`badge badge-${f.severity}`}>{f.severity}</span>
                </span>
                <span className="muted" style={{fontSize:11}}>
                  {f.date} · {f.district} · {f.police_station}</span>
              </div>
              <p className="muted clamp-2" style={{marginTop:5,fontSize:12}}>{f.summary}</p>
            </button>)}
        </div>
        <p className="muted" style={{fontSize:11,marginTop:8}}>
          Select an FIR to open it in the FIR Records tab.</p>
      </div>
    </>}</Async>
  </section>;
}

// ── Dashboard ──────────────────────────────────────────────────────────────
function Dashboard({state, onOpenFIR}) {
  const [selectedCrime, setSelectedCrime] = useState(null);
  return <Async state={state}>{(data) => {
    // Keep the raw key alongside the display label so a click can address the
    // API without having to reverse the prettified name.
    const crimeData = Object.entries(data.crime_breakdown || {})
      .map(([key, value]) => ({name: label(key), key, value}))
      .sort((a,b) => b.value - a.value);
    const districtData = Object.entries(data.district_breakdown || {})
      .map(([name, value]) => ({name, value})).sort((a,b) => b.value - a.value);
    const trendData = Object.entries(data.monthly_trend || {}).map(([name, value]) => ({name, value}));
    const sev = data.severity_distribution || {};
    const totalSev = Object.values(sev).reduce((a,b) => a+b, 0) || 1;
    const nets = data.crime_networks || [];

    return <div className="stack fade-in">
      <div className="stat-grid">
        <StatCard label="FIRs Analysed" value={data.total_firs} color="var(--blue)" icon="📋"
                  sub={`${data.total_districts} districts · ${data.total_stations} stations`}/>
        <StatCard label="Accused Identified" value={data.total_accused} color="var(--red)" icon="👤"
                  sub="named across all FIRs"/>
        <StatCard label="Victims Recorded" value={data.total_victims} color="var(--amber)" icon="🛡"
                  sub="complainants + victims"/>
        <StatCard label="Repeat Offenders" value={data.repeat_offenders_count} color="var(--purple)" icon="🔁"
                  sub={`fuzzy name match ≥ ${data.name_match_threshold}%`}/>
      </div>

      <SectionCard title="Severity Distribution"
                   subtitle={`Mean severity ${Number(data.avg_severity || 0).toFixed(1)}/100 across ${data.total_firs} FIRs`}>
        <div style={{display:'flex',borderRadius:8,overflow:'hidden',height:28}}
             role="img" aria-label={['critical','high','medium','low']
               .map((l) => `${l}: ${sev[l] || 0}`).join(', ')}>
          {['critical','high','medium','low'].map((level) => {
            const pct = (sev[level] || 0) / totalSev * 100;
            if (pct <= 0) return null;
            return <div key={level} title={`${level}: ${sev[level]}`}
              style={{width:pct+'%',background:RISK_COLOR[level],display:'flex',alignItems:'center',
                      justifyContent:'center',fontSize:11,fontWeight:700,color:'#0a0e1a'}}>
              {pct > 9 ? `${level.toUpperCase()} ${sev[level]}` : ''}
            </div>;
          })}
        </div>
        <div style={{display:'flex',gap:18,marginTop:10,flexWrap:'wrap'}}>
          {['critical','high','medium','low'].map((l) =>
            <span key={l} style={{display:'flex',alignItems:'center',gap:6,fontSize:12,color:'var(--text2)'}}>
              <span aria-hidden="true" style={{width:10,height:10,borderRadius:3,background:RISK_COLOR[l]}}/>
              {l}: {sev[l] || 0}
            </span>)}
        </div>
      </SectionCard>

      <div className="grid-2">
        <SectionCard title="Crime Type Distribution"
                     subtitle="Select a segment to break that offence down">
          <ResponsiveContainer width="100%" height={280}>
            <PieChart margin={{top:8,right:70,bottom:8,left:70}}>
              <Pie data={crimeData} dataKey="value" nameKey="name" cx="50%" cy="50%"
                   outerRadius={88} innerRadius={52} paddingAngle={2} minAngle={2}
                   label={({name,percent}) => percent > .045 ? `${name} ${(percent*100).toFixed(0)}%` : ''}
                   labelLine={{stroke:'#5b9bff',strokeWidth:1}} isAnimationActive={false}
                   onClick={(slice) => setSelectedCrime(
                     (current) => current === slice.key ? null : slice.key)}
                   style={{cursor:'pointer',outline:'none'}}>
                {crimeData.map((entry, i) =>
                  <Cell key={i} fill={COLORS[i % COLORS.length]}
                        stroke={selectedCrime === entry.key ? '#edf2ff' : undefined}
                        strokeWidth={selectedCrime === entry.key ? 2.5 : 0}
                        fillOpacity={selectedCrime && selectedCrime !== entry.key ? .35 : 1}/>)}
              </Pie>
              <Tooltip {...CHART_TOOLTIP}/>
            </PieChart>
          </ResponsiveContainer>
          {/* A chart click is mouse-only; the same drill-down has to be
              reachable from the keyboard. */}
          <div style={{display:'flex',flexWrap:'wrap',gap:5,marginTop:10}}>
            {crimeData.map((entry, i) =>
              <button key={entry.key} className="chip chip-btn"
                      aria-pressed={selectedCrime === entry.key}
                      onClick={() => setSelectedCrime(
                        selectedCrime === entry.key ? null : entry.key)}
                      style={{borderColor: selectedCrime === entry.key
                                ? COLORS[i % COLORS.length] : 'var(--border)',
                              color: COLORS[i % COLORS.length],
                              background: selectedCrime === entry.key
                                ? COLORS[i % COLORS.length] + '25' : 'transparent'}}>
                {entry.name} {entry.value}
              </button>)}
          </div>
        </SectionCard>
        <SectionCard title="FIRs by District">
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={districtData} margin={{bottom:34}}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1c2748"/>
              <XAxis dataKey="name" stroke="#9dafd4" tick={{fontSize:11}} angle={-35}
                     textAnchor="end" interval={0} height={60}/>
              <YAxis stroke="#9dafd4" allowDecimals={false}/>
              <Tooltip {...CHART_TOOLTIP}/>
              <Bar dataKey="value" radius={[6,6,0,0]} isAnimationActive={false}>
                {districtData.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]}/>)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </SectionCard>
      </div>

      {selectedCrime && <CrimeDrilldown crimeType={selectedCrime}
        onClose={() => setSelectedCrime(null)} onOpenFIR={onOpenFIR}/>}

      <SectionCard title="Monthly Crime Trend">
        <ResponsiveContainer width="100%" height={240}>
          <AreaChart data={trendData}>
            <defs><linearGradient id="trendGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#5b9bff" stopOpacity={.35}/>
              <stop offset="95%" stopColor="#5b9bff" stopOpacity={0}/>
            </linearGradient></defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#1c2748"/>
            <XAxis dataKey="name" stroke="#9dafd4" tick={{fontSize:11}}/>
            <YAxis stroke="#9dafd4" allowDecimals={false}/>
            <Tooltip {...CHART_TOOLTIP}/>
            <Area type="monotone" dataKey="value" stroke="#5b9bff" fill="url(#trendGrad)"
                  strokeWidth={2.5} isAnimationActive={false} name="FIRs"/>
          </AreaChart>
        </ResponsiveContainer>
      </SectionCard>

      <SectionCard title="Crime Networks Detected"
                   subtitle={`${nets.length} clusters linked by shared offenders or shared modus operandi`}>
        {nets.length === 0
          ? <p className="muted">No networks detected in the current corpus.</p>
          : <div className="card-grid">
              {nets.slice(0, 9).map((net, i) =>
                <article key={net.name + i} style={{padding:16,borderRadius:10,
                    background:'rgba(91,155,255,.06)',border:'1px solid rgba(91,155,255,.18)'}}>
                  <div style={{display:'flex',justifyContent:'space-between',gap:8,alignItems:'flex-start'}}>
                    <h3 style={{color:'var(--blue)',fontWeight:700,fontSize:14}}>{net.name}</h3>
                    <span className={`badge badge-${net.risk_level || 'medium'}`}>{net.risk_level}</span>
                  </div>
                  <p className="muted" style={{marginTop:6,fontSize:12}}>
                    {net.fir_count} linked FIRs across {(net.districts || []).join(', ')}
                  </p>
                  <div style={{display:'flex',flexWrap:'wrap',gap:4,marginTop:8}}>
                    {(net.crime_types || []).map((ct, j) =>
                      <span key={j} className="chip" style={{background:'rgba(91,155,255,.14)',color:'var(--blue)'}}>{label(ct)}</span>)}
                  </div>
                </article>)}
            </div>}
      </SectionCard>
    </div>;
  }}</Async>;
}

// ── FIR records ────────────────────────────────────────────────────────────
const PAGE_SIZE = 20;

function FIRList({initialQuery}) {
  const [search, setSearch] = useState(initialQuery || '');
  const [query, setQuery] = useState(initialQuery || '');
  const [crimeType, setCrimeType] = useState('');
  const [district, setDistrict] = useState('');
  const [severity, setSeverity] = useState('');
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState(initialQuery || null);

  const filters = useApi('/filters');

  // Arriving from a drill-down: search for that FIR and expand it.
  useEffect(() => {
    if (!initialQuery) return;
    setSearch(initialQuery);
    setQuery(initialQuery);
    setSelected(initialQuery);
    setOffset(0);
  }, [initialQuery]);

  // Debounce so a keystroke does not fire a request per character.
  useEffect(() => {
    const id = setTimeout(() => { setQuery(search); setOffset(0); }, 300);
    return () => clearTimeout(id);
  }, [search]);

  const params = new URLSearchParams({limit:String(PAGE_SIZE), offset:String(offset)});
  if (query) params.set('q', query);
  if (crimeType) params.set('crime_type', crimeType);
  if (district) params.set('district', district);
  if (severity) params.set('severity', severity);
  const list = useApi(`/firs?${params.toString()}`);

  const reset = (setter) => (e) => { setter(e.target.value); setOffset(0); };
  const opts = filters.data || {crime_types:[], districts:[], severities:[]};

  return <div className="stack fade-in">
    <div className="toolbar">
      <div style={{flex:'2 1 260px'}}>
        <label htmlFor="fir-search">Search</label>
        <input id="fir-search" type="search" value={search} style={{width:'100%'}}
               placeholder="FIR number, accused, victim, keyword…"
               onChange={(e) => setSearch(e.target.value)}/>
      </div>
      <div style={{flex:'1 1 150px'}}>
        <label htmlFor="fir-type">Crime type</label>
        <select id="fir-type" value={crimeType} onChange={reset(setCrimeType)} style={{width:'100%'}}>
          <option value="">All types</option>
          {opts.crime_types.map((t) => <option key={t} value={t}>{titleCase(t)}</option>)}
        </select>
      </div>
      <div style={{flex:'1 1 150px'}}>
        <label htmlFor="fir-district">District</label>
        <select id="fir-district" value={district} onChange={reset(setDistrict)} style={{width:'100%'}}>
          <option value="">All districts</option>
          {opts.districts.map((d) => <option key={d} value={d}>{d}</option>)}
        </select>
      </div>
      <div style={{flex:'1 1 130px'}}>
        <label htmlFor="fir-sev">Severity</label>
        <select id="fir-sev" value={severity} onChange={reset(setSeverity)} style={{width:'100%'}}>
          <option value="">Any severity</option>
          {(opts.severities || []).map((s) => <option key={s} value={s}>{titleCase(s)}</option>)}
        </select>
      </div>
    </div>

    <Async state={list}
           isEmpty={(d) => !d.items.length}
           empty={<EmptyState title="No FIRs match these filters"
                    hint="Try clearing the search box or widening the crime type and district filters."
                    action={<button className="btn btn-ghost" onClick={() => {
                      setSearch(''); setCrimeType(''); setDistrict(''); setSeverity(''); setOffset(0);
                    }}>Clear all filters</button>}/>}>
      {(data) => <>
        <p className="muted" aria-live="polite">
          Showing {data.offset + 1}–{data.offset + data.items.length} of {data.total} records
        </p>
        {data.items.map((fir) =>
          <button key={fir.fir_number} className="row-card"
                  aria-expanded={selected === fir.fir_number}
                  onClick={() => setSelected(selected === fir.fir_number ? null : fir.fir_number)}>
            <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',
                         flexWrap:'wrap',gap:8}}>
              <span style={{display:'flex',alignItems:'center',gap:10,flexWrap:'wrap'}}>
                <span style={{fontFamily:'ui-monospace,Menlo,monospace',color:'var(--blue)',fontWeight:700}}>
                  {fir.fir_number}</span>
                <span className={`badge badge-${fir.severity}`}>{fir.severity}</span>
                <span className="chip" style={{background:'var(--card2)',color:'var(--text2)'}}>
                  {label(fir.crime_type)}</span>
              </span>
              <span className="muted">{fir.date} · {fir.district} · {fir.police_station}</span>
            </div>
            <p className="muted clamp-2" style={{marginTop:8}}>{fir.summary}</p>
            {selected === fir.fir_number && <FIRDetail firNumber={fir.fir_number}/>}
          </button>)}

        <nav aria-label="Pagination" style={{display:'flex',gap:10,justifyContent:'center',
             alignItems:'center',paddingTop:6}}>
          <button className="btn btn-ghost" disabled={offset === 0}
                  onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>← Previous</button>
          <span className="muted">Page {Math.floor(offset / PAGE_SIZE) + 1} of{' '}
            {Math.max(1, Math.ceil(data.total / PAGE_SIZE))}</span>
          <button className="btn btn-ghost" disabled={!data.has_more}
                  onClick={() => setOffset(offset + PAGE_SIZE)}>Next →</button>
        </nav>
      </>}
    </Async>
  </div>;
}

/** Full record, fetched on demand — the list only carries a preview. */
function FIRDetail({firNumber}) {
  const detail = useApi(`/firs/${firNumber}`);
  return <div className="fade-in" style={{marginTop:16,paddingTop:16,borderTop:'1px solid var(--border)'}}>
    <Async state={detail}>{(fir) => {
      const ent = fir.entities || {};
      const mo = ent.modus_operandi;
      return <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(230px,1fr))',gap:16}}>
        <div>
          <h4 style={{fontSize:13,fontWeight:700,color:'var(--red)',marginBottom:8}}>
            Accused ({(ent.accused || []).length})</h4>
          {(ent.accused || []).length === 0 && <p className="muted">None named in this FIR.</p>}
          {(ent.accused || []).map((a, i) =>
            <div key={i} style={{marginBottom:8,padding:10,borderRadius:8,background:'var(--bg2)'}}>
              <p style={{fontWeight:700,fontSize:13}}>{a.name}</p>
              {a.aliases?.length > 0 && <p className="muted" style={{fontSize:11}}>alias {a.aliases.join(', ')}</p>}
              {a.age != null && <p className="muted" style={{fontSize:11}}>Age {a.age}{a.gender ? ` · ${a.gender}` : ''}</p>}
              {a.father_name && <p className="muted" style={{fontSize:11}}>S/o {a.father_name}</p>}
              {a.address && <p className="muted" style={{fontSize:11}}>{a.address}</p>}
              {a.id_marks?.length > 0 && <p className="muted" style={{fontSize:11}}>Marks: {a.id_marks.join('; ')}</p>}
            </div>)}
        </div>
        <div>
          <h4 style={{fontSize:13,fontWeight:700,color:'var(--green)',marginBottom:8}}>
            Victims ({(ent.victims || []).length})</h4>
          {(ent.victims || []).map((v, i) =>
            <div key={i} style={{marginBottom:8,padding:10,borderRadius:8,background:'var(--bg2)'}}>
              <p style={{fontWeight:700,fontSize:13}}>{v.name}</p>
              {v.age != null && <p className="muted" style={{fontSize:11}}>Age {v.age}{v.gender ? ` · ${v.gender}` : ''}</p>}
              {v.occupation && <p className="muted" style={{fontSize:11}}>{v.occupation}</p>}
            </div>)}
          {mo && <div style={{marginTop:10}}>
            <h4 style={{fontSize:13,fontWeight:700,color:'var(--amber)',marginBottom:4}}>Modus Operandi</h4>
            <p className="muted">{mo.description || mo.approach_method || '—'}</p>
          </div>}
        </div>
        <div>
          <h4 style={{fontSize:13,fontWeight:700,color:'var(--purple)',marginBottom:8}}>Sections</h4>
          <div style={{display:'flex',flexWrap:'wrap',gap:4,marginBottom:12}}>
            {(ent.ipc_sections || []).map((s, i) =>
              <span key={i} className="chip" style={{background:'rgba(180,155,255,.14)',color:'var(--purple)'}}>{s}</span>)}
            {(ent.ipc_sections || []).length === 0 && <span className="muted">Not recorded</span>}
          </div>
          <h4 style={{fontSize:13,fontWeight:700,color:'var(--cyan)',marginBottom:8}}>
            Linked FIRs ({(fir.related || []).length})</h4>
          {(fir.related || []).length === 0 && <p className="muted">No cross-FIR links found.</p>}
          {(fir.related || []).slice(0, 8).map((r, i) =>
            <p key={i} className="muted" style={{fontSize:11,marginBottom:3}}>
              <span style={{fontFamily:'ui-monospace,Menlo,monospace',color:'var(--blue)'}}>{r.fir_number}</span>
              {' — '}{r.reason}
            </p>)}
        </div>
        <div style={{gridColumn:'1 / -1'}}>
          <h4 style={{fontSize:13,fontWeight:700,marginBottom:6}}>FIR narrative</h4>
          <p className="muted" style={{whiteSpace:'pre-wrap'}}>{fir.text}</p>
        </div>
      </div>;
    }}</Async>
  </div>;
}

// ── Repeat offenders ───────────────────────────────────────────────────────
function RepeatOffenders({threshold}) {
  const [risk, setRisk] = useState('');
  const state = useApi(`/repeat-offenders${risk ? `?risk_level=${risk}` : ''}`);
  return <div className="stack fade-in">
    <div className="toolbar" style={{justifyContent:'space-between'}}>
      <div>
        <h2 style={{fontSize:19,fontWeight:700}}>Flagged Repeat Offenders</h2>
        <p className="muted">Identity resolved by name, alias and locality correlation
          (fuzzy threshold {threshold ?? '—'}%). Approximate name matches require corroborating
          evidence before they are merged.</p>
      </div>
      <div>
        <label htmlFor="ro-risk">Risk level</label>
        <select id="ro-risk" value={risk} onChange={(e) => setRisk(e.target.value)}>
          <option value="">All risk levels</option>
          {['critical','high','medium','low'].map((r) => <option key={r} value={r}>{titleCase(r)}</option>)}
        </select>
      </div>
    </div>
    <Async state={state} isEmpty={(d) => !d.length}
           empty={<EmptyState title="No repeat offenders at this risk level"
                    hint="An accused must appear in at least two distinct FIRs to be flagged."/>}>
      {(offenders) => <>
        <p className="muted" aria-live="polite">{offenders.length} offenders</p>
        {offenders.map((off, i) =>
          <article key={i} className="glass p-5 glow">
            <div style={{display:'flex',justifyContent:'space-between',gap:10,alignItems:'flex-start'}}>
              <div>
                <h3 style={{fontSize:17,fontWeight:700,color:'var(--red)'}}>{off.primary_name}</h3>
                {off.aliases?.length > 0 &&
                  <p className="muted" style={{marginTop:2}}>Aliases: {off.aliases.join(', ')}</p>}
              </div>
              <span className={`badge badge-${off.risk_level}`} style={{fontSize:12,padding:'4px 13px'}}>
                {off.risk_level}</span>
            </div>
            <div className="metric-grid" style={{marginTop:14}}>
              {[['Linked FIRs', off.fir_count, 'var(--blue)'],
                ['Districts', (off.districts || []).length, 'var(--cyan)'],
                ['Offences', (off.crime_types || []).length, 'var(--amber)'],
                ['Confidence', `${Math.round((off.match_confidence || 0) * 100)}%`, 'var(--green)']]
                .map(([k, v, c]) =>
                  <div key={k} style={{padding:10,borderRadius:8,background:'var(--bg2)',textAlign:'center'}}>
                    <p className="muted" style={{fontSize:11}}>{k}</p>
                    <p style={{fontWeight:700,fontSize:19,color:c}}>{v}</p>
                  </div>)}
            </div>
            <p className="muted" style={{marginTop:10,fontSize:12}}>
              Active {off.first_seen} → {off.last_seen} · {(off.districts || []).join(', ')} ·{' '}
              {(off.crime_types || []).map(label).join(', ')}
            </p>
            <div style={{display:'flex',flexWrap:'wrap',gap:4,marginTop:10}}>
              {(off.linked_firs || []).map((f, j) =>
                <span key={j} className="chip" style={{background:'rgba(91,155,255,.1)',color:'var(--blue)',
                  border:'1px solid rgba(91,155,255,.22)'}}>{f}</span>)}
            </div>
            {off.mo_signature && <p className="muted" style={{marginTop:10}}>
              <strong style={{color:'var(--amber)'}}>MO signature:</strong> {off.mo_signature}</p>}
            <p className="muted" style={{marginTop:8,padding:10,borderRadius:8,background:'var(--bg2)',
               borderLeft:'3px solid var(--cyan)'}}>{off.intelligence_assessment}</p>
          </article>)}
      </>}
    </Async>
  </div>;
}

// ── Crime trends ───────────────────────────────────────────────────────────
function CrimeTrends({state}) {
  return <Async state={state}>{(data) => {
    const trendData = Object.entries(data.monthly_trend || {}).map(([name, value]) => ({name, value}));
    const ranking = Object.entries(data.crime_breakdown || {}).sort((a,b) => b[1] - a[1]);
    const maxCrime = ranking.length ? ranking[0][1] : 1;
    const radarData = ranking.slice(0, 8).map(([type, count]) => ({subject: label(type), A: count}));
    const districtData = Object.entries(data.district_breakdown || {})
      .map(([name, value]) => ({name, value})).sort((a,b) => b.value - a.value);

    return <div className="stack fade-in">
      <div className="grid-2">
        <SectionCard title="Crime Trend Over Time">
          <ResponsiveContainer width="100%" height={280}>
            <AreaChart data={trendData}>
              <defs><linearGradient id="tg2" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#5b9bff" stopOpacity={.35}/>
                <stop offset="95%" stopColor="#5b9bff" stopOpacity={0}/>
              </linearGradient></defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#1c2748"/>
              <XAxis dataKey="name" stroke="#9dafd4" tick={{fontSize:11}}/>
              <YAxis stroke="#9dafd4" allowDecimals={false}/>
              <Tooltip {...CHART_TOOLTIP}/>
              <Area type="monotone" dataKey="value" stroke="#5b9bff" fill="url(#tg2)"
                    strokeWidth={2.5} isAnimationActive={false} name="FIRs"/>
            </AreaChart>
          </ResponsiveContainer>
        </SectionCard>
        <SectionCard title="Crime Radar Profile">
          <ResponsiveContainer width="100%" height={280}>
            <RadarChart data={radarData}>
              <PolarGrid stroke="#1c2748"/>
              <PolarAngleAxis dataKey="subject" stroke="#9dafd4" tick={{fontSize:11}}/>
              <PolarRadiusAxis stroke="#1c2748" tick={{fontSize:10,fill:'#7387b0'}}/>
              <Radar name="FIRs" dataKey="A" stroke="#5b9bff" fill="rgba(91,155,255,.25)"
                     strokeWidth={2} isAnimationActive={false}/>
              <Tooltip {...CHART_TOOLTIP}/>
            </RadarChart>
          </ResponsiveContainer>
        </SectionCard>
      </div>

      <SectionCard title="Crime Type Ranking">
        <div className="stack" style={{gap:10}}>
          {ranking.map(([type, count], i) =>
            <div key={type} style={{display:'flex',alignItems:'center',gap:12}}>
              <span style={{width:28,textAlign:'center',fontWeight:700,color:COLORS[i % COLORS.length]}}>
                #{i+1}</span>
              <span style={{width:118,fontSize:13,textTransform:'capitalize',flexShrink:0}}>{label(type)}</span>
              <div style={{flex:1,background:'var(--bg2)',borderRadius:20,height:24,overflow:'hidden',minWidth:60}}>
                <div style={{height:'100%',borderRadius:20,display:'flex',alignItems:'center',
                    paddingLeft:10,fontSize:12,fontWeight:700,color:'#0a0e1a',
                    width:`${Math.max((count / maxCrime) * 100, 12)}%`,
                    background:`linear-gradient(90deg,${COLORS[i % COLORS.length]},${COLORS[i % COLORS.length]}aa)`}}>
                  {count}
                </div>
              </div>
            </div>)}
        </div>
      </SectionCard>

      <SectionCard title="District Crime Comparison">
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={districtData} margin={{bottom:40}}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1c2748"/>
            <XAxis dataKey="name" stroke="#9dafd4" tick={{fontSize:11}} angle={-35}
                   textAnchor="end" interval={0} height={70}/>
            <YAxis stroke="#9dafd4" allowDecimals={false}/>
            <Tooltip {...CHART_TOOLTIP}/>
            <Bar dataKey="value" radius={[6,6,0,0]} isAnimationActive={false} name="FIRs">
              {districtData.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]}/>)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </SectionCard>
    </div>;
  }}</Async>;
}

// ── Stations ───────────────────────────────────────────────────────────────
function StationSummary() {
  const [filter, setFilter] = useState('');
  const state = useApi('/stations');
  return <div className="stack fade-in">
    <div className="toolbar" style={{justifyContent:'space-between'}}>
      <h2 style={{fontSize:19,fontWeight:700}}>Station-Level Analysis</h2>
      <div style={{flex:'0 1 280px'}}>
        <label htmlFor="station-search">Filter stations</label>
        <input id="station-search" type="search" value={filter} style={{width:'100%'}}
               placeholder="Station or district…" onChange={(e) => setFilter(e.target.value)}/>
      </div>
    </div>
    <Async state={state} isEmpty={(d) => !d.length}
           empty={<EmptyState title="No station data available"/>}>
      {(all) => {
        const needle = filter.trim().toLowerCase();
        const stations = needle
          ? all.filter((s) => s.station_name.toLowerCase().includes(needle) ||
                              s.district.toLowerCase().includes(needle))
          : all;
        if (!stations.length) {
          return <EmptyState title={`No station matches “${filter}”`}
                   hint="Try a district name such as Lucknow or Kanpur Nagar."/>;
        }
        return <>
          <p className="muted" aria-live="polite">{stations.length} of {all.length} stations</p>
          {stations.map((st, i) =>
            <article key={i} className="glass p-5">
              <div style={{display:'flex',justifyContent:'space-between',gap:10,
                           alignItems:'flex-start',marginBottom:12}}>
                <div>
                  <h3 style={{fontSize:16,fontWeight:700}}>{st.station_name}</h3>
                  <p className="muted">{st.district} · {st.total_firs} FIRs ·
                    {' '}{st.repeat_offenders_count} repeat offenders</p>
                </div>
                <span className={`badge badge-${st.risk_level}`}>{st.risk_level}</span>
              </div>
              <div className="metric-grid" style={{marginBottom:12}}>
                {Object.entries(st.crime_breakdown || {}).map(([type, count]) =>
                  <div key={type} style={{padding:8,borderRadius:8,background:'var(--bg2)',textAlign:'center'}}>
                    <p className="muted" style={{fontSize:10,textTransform:'capitalize'}}>{label(type)}</p>
                    <p style={{fontWeight:700,color:'var(--blue)',fontSize:16}}>{count}</p>
                  </div>)}
              </div>
              {Object.keys(st.monthly_trend || {}).length > 1 &&
                <ResponsiveContainer width="100%" height={90}>
                  <AreaChart data={Object.entries(st.monthly_trend).map(([m, v]) => ({month:m, count:v}))}>
                    <XAxis dataKey="month" stroke="#7387b0" tick={{fontSize:9}}/>
                    <YAxis stroke="#7387b0" tick={{fontSize:9}} width={24} allowDecimals={false}/>
                    <Tooltip {...CHART_TOOLTIP}/>
                    <Area type="monotone" dataKey="count" stroke="#5b9bff"
                          fill="rgba(91,155,255,.15)" strokeWidth={1.5} isAnimationActive={false}/>
                  </AreaChart>
                </ResponsiveContainer>}
              {st.hotspot_areas?.length > 0 && <p className="muted" style={{marginTop:8}}>
                Hotspots: <span style={{color:'var(--amber)'}}>{st.hotspot_areas.join(', ')}</span></p>}
              <p className="muted" style={{marginTop:6,padding:8,borderRadius:6,background:'var(--bg2)'}}>
                {st.assessment}</p>
            </article>)}
        </>;
      }}
    </Async>
  </div>;
}

// ── Networks ───────────────────────────────────────────────────────────────
function NetworkView() {
  const state = useApi('/networks');
  return <div className="stack fade-in">
    <Async state={state} isEmpty={(d) => !d.length}
           empty={<EmptyState title="No organised networks detected"
                    hint="A network needs at least two FIRs linked by a shared offender identity or a distinctive shared modus operandi."/>}>
      {(networks) => <>
        <div>
          <h2 style={{fontSize:19,fontWeight:700}}>Crime Network Intelligence</h2>
          <p className="muted">Cross-FIR correlation identified {networks.length} clusters.
            Clusters are grown from the strongest links first and capped, so a common
            offence pattern cannot chain unrelated cases into one false network.</p>
        </div>
        {networks.map((net, i) => {
          const c = COLORS[i % COLORS.length];
          const members = net.key_members || [];
          const firs = net.fir_numbers || [];
          const shown = firs.slice(0, 10);
          const extra = firs.length - shown.length;
          const cx = 300, cy = 112, orbX = 132, orbY = 84;
          return <article key={i} className="glass p-5 glow" style={{borderColor:c+'45'}}>
            <div style={{display:'flex',justifyContent:'space-between',gap:10,
                         alignItems:'flex-start',flexWrap:'wrap'}}>
              <h3 style={{fontSize:17,fontWeight:700,color:c}}>{net.name}</h3>
              <span style={{display:'flex',gap:8,alignItems:'center'}}>
                <span className={`badge badge-${net.risk_level || 'medium'}`}>{net.risk_level}</span>
                <span className="chip" style={{background:c+'22',color:c,fontWeight:700}}>
                  {net.fir_count} FIRs</span>
              </span>
            </div>
            <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(200px,1fr))',
                         gap:14,marginTop:14}}>
              <div style={{padding:14,borderRadius:10,background:'var(--bg2)'}}>
                <p className="muted" style={{fontSize:11,marginBottom:6}}>Linked FIRs</p>
                <div style={{display:'flex',flexWrap:'wrap',gap:4}}>
                  {firs.map((f, j) => <span key={j} className="chip"
                    style={{background:c+'1f',color:c}}>{f}</span>)}
                </div>
              </div>
              <div style={{padding:14,borderRadius:10,background:'var(--bg2)'}}>
                <p className="muted" style={{fontSize:11,marginBottom:6}}>Districts &amp; offences</p>
                <p style={{fontSize:13}}>{(net.districts || []).join(', ')}</p>
                <div style={{display:'flex',flexWrap:'wrap',gap:4,marginTop:6}}>
                  {(net.crime_types || []).map((ct, j) => <span key={j} className="chip"
                    style={{background:'var(--card2)',color:'var(--text2)'}}>{label(ct)}</span>)}
                </div>
                <p className="muted" style={{fontSize:11,marginTop:8}}>
                  Linked by: {(net.link_basis || ['correlation']).join(', ')}</p>
              </div>
              <div style={{padding:14,borderRadius:10,background:'var(--bg2)'}}>
                <p className="muted" style={{fontSize:11,marginBottom:6}}>
                  Active {net.active_period?.start} → {net.active_period?.end}</p>
                {members.length > 0 ? <>
                  <p className="muted" style={{fontSize:11,marginBottom:4}}>Key members</p>
                  {members.slice(0, 5).map((m, j) =>
                    <p key={j} style={{fontSize:13,color:'var(--red)'}}>{m}</p>)}
                </> : <p className="muted" style={{fontSize:12}}>No accused named — linked on MO.</p>}
              </div>
            </div>
            {net.intelligence_brief && <p className="muted" style={{marginTop:12,padding:12,
              borderRadius:8,background:'var(--bg2)',borderLeft:`3px solid ${c}`}}>
              {net.intelligence_brief}</p>}

            <figure style={{marginTop:16,borderRadius:10,background:'var(--bg)',padding:16}}>
              <figcaption className="sr-only">
                Network graph: {net.name} with {firs.length} linked FIRs.
              </figcaption>
              {/* CSS custom properties do NOT resolve inside SVG presentation
                  attributes (fill="var(--card)"), which rendered every node
                  black-on-black. They must go through the style object. */}
              <svg width="100%" height="240" viewBox="0 0 600 240" role="img"
                   aria-label={`${net.name}: ${firs.length} linked FIRs`}>
                <defs><filter id={`glow-${i}`}>
                  <feGaussianBlur stdDeviation="3" result="blur"/>
                  <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
                </filter></defs>
                {shown.map((fir, j) => {
                  const angle = (j / shown.length) * Math.PI * 2 - Math.PI / 2;
                  const x = cx + Math.cos(angle) * orbX;
                  const y = cy + Math.sin(angle) * orbY;
                  return <g key={j}>
                    <line x1={cx} y1={cy} x2={x} y2={y} stroke={c} strokeOpacity={.35}
                          strokeWidth="1.5" strokeDasharray="5 3"/>
                    <circle cx={x} cy={y} r="23" style={{fill:'#151d35'}} stroke={c}
                            strokeOpacity={.7} strokeWidth="1.5"/>
                    <text x={x} y={y+4} textAnchor="middle" style={{fill:'#edf2ff'}}
                          fontSize="9" fontWeight="600">{fir.split('/').slice(-2).join('/')}</text>
                  </g>;
                })}
                <circle cx={cx} cy={cy} r="44" fill={c} fillOpacity={.16} stroke={c}
                        strokeWidth="2.5" filter={`url(#glow-${i})`}/>
                <text x={cx} y={cy-8} textAnchor="middle" style={{fill:c}} fontSize="10" fontWeight="bold">
                  {net.name.length > 22 ? net.name.slice(0, 20) + '…' : net.name}</text>
                <text x={cx} y={cy+7} textAnchor="middle" style={{fill:'#9dafd4'}} fontSize="9">
                  {net.fir_count} FIRs</text>
                {extra > 0 && <text x={cx} y={cy+20} textAnchor="middle" style={{fill:'#7387b0'}}
                  fontSize="8">+{extra} more</text>}
              </svg>
            </figure>
          </article>;
        })}
      </>}
    </Async>
  </div>;
}

// ── Chat ───────────────────────────────────────────────────────────────────

/** One message bubble. Shared by the full tab and the floating widget. */
function ChatBubble({message, compact}) {
  const isUser = message.role === 'user';
  return <div style={{display:'flex',justifyContent:isUser ? 'flex-end' : 'flex-start'}}>
    <div className="chat-bubble" style={{maxWidth: compact ? '90%' : '72%',
        padding: compact ? '10px 13px' : '12px 16px',
        borderRadius: isUser ? '16px 16px 4px 16px' : '16px 16px 16px 4px',
        background: isUser ? 'var(--blue2)' : 'var(--card)',
        border: message.error ? '1px solid rgba(251,90,117,.5)' : '1px solid var(--border)'}}>
      <p className="sr-only">{isUser ? 'You said' : 'Assistant said'}</p>
      {message.fallback && <p style={{fontSize:11,color:'var(--amber)',marginBottom:6}}>
        Model unavailable — showing the computed analysis instead.</p>}
      <pre style={{fontSize: compact ? 12.5 : 13,whiteSpace:'pre-wrap',wordBreak:'break-word',
           fontFamily:'inherit',margin:0,lineHeight:1.55,
           color: message.error ? 'var(--red)' : 'inherit'}}>{message.content}
        {message.streaming && <span className="caret" aria-hidden="true">▍</span>}</pre>
      {!isUser && !message.streaming && message.source && !message.greeting &&
        <p style={{fontSize:10,color:'var(--text3)',marginTop:8}}>
          {message.source}{message.model ? ` · ${message.model}` : ''}</p>}
    </div>
  </div>;
}

function ChatComposer({chat, inputRef, compact}) {
  const [input, setInput] = useState('');
  const submit = (e) => {
    e.preventDefault();
    const text = input.trim();
    if (!text || chat.busy) return;
    setInput('');
    chat.send(text);
  };
  return <form style={{display:'flex',gap:8}} onSubmit={submit}>
    <label className="sr-only" htmlFor={compact ? 'dock-input' : 'chat-input'}>
      Ask about the FIR corpus</label>
    <input id={compact ? 'dock-input' : 'chat-input'} ref={inputRef} type="text"
           value={input} onChange={(e) => setInput(e.target.value)} style={{flex:1,minWidth:0}}
           placeholder={compact ? 'Ask about the corpus…'
                                : 'Ask about offenders, networks, districts or an FIR number…'}/>
    {chat.busy
      ? <button type="button" className="btn btn-ghost" onClick={chat.stop}>Stop</button>
      : <button type="submit" className="btn btn-primary" disabled={!input.trim()}
                style={{paddingLeft: compact ? 16 : 24, paddingRight: compact ? 16 : 24}}>
          Send</button>}
  </form>;
}

function ChatTranscript({chat, compact}) {
  const endRef = useRef(null);
  useEffect(() => { endRef.current?.scrollIntoView({behavior:'smooth', block:'end'}); },
            [chat.messages, chat.busy]);
  return <div role="log" aria-live="polite" aria-label="Conversation"
       style={{flex:1,overflowY:'auto',display:'flex',flexDirection:'column',
               gap:10,marginBottom:12,paddingRight:6}}>
    {chat.messages.map((m, i) => <ChatBubble key={i} message={m} compact={compact}/>)}
    {chat.busy && !chat.messages[chat.messages.length - 1]?.content &&
      <div style={{display:'flex',gap:8,alignItems:'center',padding:'6px 4px'}}>
        <div className="spinner" style={{width:16,height:16,borderWidth:2}}/>
        <span className="muted" style={{fontSize:12}}>Analysing the corpus…</span>
      </div>}
    <div ref={endRef}/>
  </div>;
}

function BobChat({chat}) {
  const inputRef = useRef(null);
  return <div className="fade-in" style={{display:'flex',flexDirection:'column',
      height:'calc(100vh - 240px)',minHeight:420}}>
    <ChatTranscript chat={chat}/>
    <div style={{display:'flex',flexWrap:'wrap',gap:6,marginBottom:10,alignItems:'center'}}>
      {CHAT_SUGGESTIONS.map((s, i) =>
        <button key={i} onClick={() => chat.send(s)} disabled={chat.busy} className="btn btn-ghost"
                style={{fontSize:12,padding:'6px 12px',borderRadius:20}}>{s}</button>)}
      {chat.messages.length > 1 &&
        <button onClick={chat.reset} className="btn btn-ghost"
                style={{fontSize:12,padding:'6px 12px',borderRadius:20,marginLeft:'auto'}}>
          Clear</button>}
    </div>
    <ChatComposer chat={chat} inputRef={inputRef}/>
  </div>;
}

/** Floating assistant, reachable from every tab without losing the thread. */
function ChatDock({chat, hidden}) {
  const [open, setOpen] = useState(false);
  const [unread, setUnread] = useState(false);
  const inputRef = useRef(null);
  const panelRef = useRef(null);
  const lastSeen = useRef(chat.messages.length);

  // Badge the launcher when a reply lands while the panel is closed.
  useEffect(() => {
    if (open) { lastSeen.current = chat.messages.length; setUnread(false); }
    else if (chat.messages.length > lastSeen.current) setUnread(true);
  }, [chat.messages, open]);

  useEffect(() => {
    if (!open) return;
    inputRef.current?.focus();
    const onKey = (e) => { if (e.key === 'Escape') setOpen(false); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open]);

  if (hidden) return null;

  return <>
    {open && <section ref={panelRef} className="chat-dock glass fade-in" role="dialog"
        aria-label="FIR Intelligence assistant" aria-modal="false">
      <header style={{display:'flex',alignItems:'center',justifyContent:'space-between',
          gap:8,padding:'12px 14px',borderBottom:'1px solid var(--border)'}}>
        <div style={{minWidth:0}}>
          <h2 style={{fontSize:14,fontWeight:700}}>Intelligence Assistant</h2>
          <p className="muted" style={{fontSize:11}}>Grounded in the analysed corpus</p>
        </div>
        <div style={{display:'flex',gap:4,flexShrink:0}}>
          <button className="btn btn-ghost" onClick={chat.reset} title="Clear conversation"
                  style={{padding:'4px 10px',fontSize:12}}>Clear</button>
          <button className="btn btn-ghost" onClick={() => setOpen(false)}
                  aria-label="Close assistant" style={{padding:'4px 11px',fontSize:15,lineHeight:1}}>×</button>
        </div>
      </header>

      <div style={{flex:1,display:'flex',flexDirection:'column',padding:'12px 14px',minHeight:0}}>
        <ChatTranscript chat={chat} compact/>
        {chat.messages.length <= 1 &&
          <div style={{display:'flex',flexWrap:'wrap',gap:5,marginBottom:10}}>
            {CHAT_SUGGESTIONS.slice(0, 3).map((s, i) =>
              <button key={i} onClick={() => chat.send(s)} disabled={chat.busy}
                      className="btn btn-ghost"
                      style={{fontSize:11,padding:'5px 10px',borderRadius:20}}>{s}</button>)}
          </div>}
        <ChatComposer chat={chat} inputRef={inputRef} compact/>
      </div>
    </section>}

    <button className="chat-fab" onClick={() => setOpen((v) => !v)}
            aria-expanded={open} aria-haspopup="dialog"
            aria-label={open ? 'Close intelligence assistant' : 'Open intelligence assistant'}>
      <span aria-hidden="true" style={{fontSize:22,lineHeight:1}}>{open ? '×' : '🤖'}</span>
      {unread && !open && <span className="fab-dot" aria-hidden="true"/>}
      {unread && !open && <span className="sr-only">New reply available</span>}
    </button>
  </>;
}

// ── Report ─────────────────────────────────────────────────────────────────
const REPORT_FOCUS = [
  {value:'', label:'Full briefing'},
  {value:'repeat offenders and their cross-district movement', label:'Repeat offenders'},
  {value:'organised crime networks and their structure', label:'Organised networks'},
  {value:'district and station resourcing priorities', label:'Resourcing'},
  {value:'the most severe and time-critical cases', label:'Severity triage'},
  {value:'cyber and financial crime', label:'Cyber & fraud'},
  {value:'narcotics and the supply chain', label:'Narcotics'},
];

/**
 * The report is generated live on every run rather than served from a cache:
 * the corpus changes as FIRs are ingested, so a stored report is stale the
 * moment someone uploads a batch. Text streams in as the model writes it.
 */
function ReportView() {
  const [focus, setFocus] = useState('');
  const [report, setReport] = useState('');
  const [meta, setMeta] = useState(null);
  const [status, setStatus] = useState(null);
  const [fallback, setFallback] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [finishedAt, setFinishedAt] = useState(null);
  const abortRef = useRef(null);

  const generate = useCallback(async (focusValue) => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setBusy(true); setError(null); setFallback(null); setReport(''); setFinishedAt(null);
    try {
      await streamSSE(`/report/stream?focus=${encodeURIComponent(focusValue || '')}`, {
        signal: controller.signal,
        onEvent: (event, data) => {
          if (event === 'start') { setStatus(data); setMeta(data.metadata || null); }
          else if (event === 'delta') setReport((prev) => prev + data.text);
          else if (event === 'fallback') setFallback(data.reason);
        },
      });
      setFinishedAt(new Date());
    } catch (err) {
      if (err.name !== 'AbortError') setError(err.message);
    } finally {
      if (abortRef.current === controller) abortRef.current = null;
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    generate('');
    return () => abortRef.current?.abort();
  }, [generate]);

  const download = useCallback((ext) => {
    const header = `FIR INTELLIGENCE REPORT\nGenerated: ${new Date().toISOString()}\n` +
      `Source: ${status?.source || 'analysis'}${status?.model ? ` (${status.model})` : ''}\n` +
      `${focus ? `Focus: ${focus}\n` : ''}\n`;
    const blob = new Blob([header + report], {type:'text/plain;charset=utf-8'});
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `FIR-Intelligence-Report-${new Date().toISOString().slice(0,10)}.${ext}`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    // Release the object URL — not doing so leaks the whole report per download.
    URL.revokeObjectURL(url);
  }, [report, status, focus]);

  return <div className="stack fade-in">
    <div className="toolbar" style={{justifyContent:'space-between'}}>
      <div>
        <h2 style={{fontSize:19,fontWeight:700}}>Intelligence Report</h2>
        <p className="muted">
          {busy ? 'Generating live from the current corpus…'
                : status ? <>Source: {status.source}{status.model ? ` · ${status.model}` : ''}
                    {finishedAt ? ` · generated ${finishedAt.toLocaleTimeString()}` : ''}</>
                : 'Preparing…'}
        </p>
      </div>
      <div style={{display:'flex',gap:8,flexWrap:'wrap'}} className="no-print">
        <div>
          <label className="sr-only" htmlFor="report-focus">Report focus</label>
          <select id="report-focus" value={focus} disabled={busy}
                  onChange={(e) => { setFocus(e.target.value); generate(e.target.value); }}>
            {REPORT_FOCUS.map((f) => <option key={f.label} value={f.value}>{f.label}</option>)}
          </select>
        </div>
        {busy
          ? <button className="btn btn-ghost" onClick={() => abortRef.current?.abort()}>Stop</button>
          : <button className="btn btn-ghost" onClick={() => generate(focus)}>Regenerate</button>}
        <button className="btn btn-ghost" onClick={() => window.print()} disabled={!report}>Print</button>
        <button className="btn btn-primary" onClick={() => download('txt')} disabled={!report || busy}>
          Download</button>
      </div>
    </div>

    {meta && <div className="metric-grid">
      {[['FIRs Analysed', meta.total_firs, 'var(--blue)'],
        ['Repeat Offenders', meta.repeat_offender_count, 'var(--red)'],
        ['Districts', (meta.districts || []).length, 'var(--green)'],
        ['Networks', (meta.patterns || []).length, 'var(--amber)'],
        ['Stations', meta.stations_analysed, 'var(--cyan)']].map(([k, v, c]) =>
        <div key={k} className="glass" style={{padding:12,textAlign:'center'}}>
          <p className="muted" style={{fontSize:11}}>{k}</p>
          <p style={{fontWeight:700,fontSize:20,color:c}}>{v}</p>
        </div>)}
    </div>}

    {fallback && <div className="glass p-5" role="status"
        style={{borderColor:'rgba(247,165,59,.45)'}}>
      <p style={{fontSize:13,color:'var(--amber)',fontWeight:600}}>
        Model unavailable — showing the report computed directly from the analysis.</p>
      <p className="muted" style={{fontSize:12,marginTop:4}}>{fallback}</p>
    </div>}

    {error && <ErrorState error={error} onRetry={() => generate(focus)}/>}

    {!report && busy && <Spinner label="Analysing the corpus"/>}

    {report && <div className="glass p-5">
      <pre aria-live="polite" style={{whiteSpace:'pre-wrap',wordBreak:'break-word',fontSize:13,
           lineHeight:1.7,fontFamily:'inherit',color:'var(--text2)'}}>{report}
        {busy && <span className="caret" aria-hidden="true">▍</span>}</pre>
    </div>}

    {report && !busy && <p className="muted" style={{fontSize:11}}>
      Findings are automated correlations and require verification by the investigating officer.
    </p>}
  </div>;
}

// ── Upload ─────────────────────────────────────────────────────────────────
function UploadPanel({onIngested}) {
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const submit = async (e) => {
    e.preventDefault();
    if (!file) return;
    setBusy(true); setError(null); setResult(null);
    try {
      const body = new FormData();
      body.append('file', file);
      const res = await fetch(API + '/upload-firs', {method:'POST', body});
      const data = await res.json();
      if (!res.ok) {
        const detail = data.detail;
        throw new Error(typeof detail === 'string' ? detail
          : detail?.message ? `${detail.message}: ${(detail.errors || [])
              .map((x) => `#${x.index} ${x.error}`).join('; ')}`
          : `Upload failed (${res.status})`);
      }
      setResult(data);
      onIngested?.();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return <div className="stack fade-in">
    <SectionCard title="Ingest FIR records"
      subtitle="Upload a JSON array of FIR records. Each needs at least fir_number and raw_text; everything else is inferred by the NLP pipeline.">
      <form onSubmit={submit} className="toolbar">
        <div style={{flex:'1 1 280px'}}>
          <label htmlFor="upload-file">FIR batch (.json)</label>
          <input id="upload-file" type="file" accept="application/json,.json"
                 style={{width:'100%'}}
                 onChange={(e) => { setFile(e.target.files?.[0] || null); setResult(null); setError(null); }}/>
        </div>
        <button type="submit" className="btn btn-primary" disabled={!file || busy}>
          {busy ? 'Analysing…' : 'Upload & analyse'}</button>
      </form>

      <details style={{marginTop:14}}>
        <summary style={{cursor:'pointer',color:'var(--blue)',fontSize:13}}>Expected format</summary>
        <pre style={{marginTop:8,padding:12,borderRadius:8,background:'var(--bg2)',fontSize:12,
             overflowX:'auto',color:'var(--text2)'}}>{`[
  {
    "fir_number": "FIR/2025/LU/001",
    "date_filed": "2025-03-04",
    "police_station": "Hazratganj PS",
    "district": "Lucknow",
    "raw_text": "Complainant states that two bike-borne persons snatched ..."
  }
]`}</pre>
      </details>
    </SectionCard>

    {error && <ErrorState error={error}/>}
    {result && <SectionCard title="Ingestion complete">
      <div className="metric-grid">
        {[['Accepted', result.accepted, 'var(--green)'],
          ['Rejected', result.rejected, 'var(--red)'],
          ['Corpus size', result.total_firs, 'var(--blue)'],
          ['Repeat offenders', result.repeat_offenders_found, 'var(--purple)'],
          ['Networks', result.networks_found, 'var(--amber)']].map(([k, v, c]) =>
          <div key={k} style={{padding:10,borderRadius:8,background:'var(--bg2)',textAlign:'center'}}>
            <p className="muted" style={{fontSize:11}}>{k}</p>
            <p style={{fontWeight:700,fontSize:19,color:c}}>{v}</p>
          </div>)}
      </div>
      {(result.errors || []).length > 0 && <div style={{marginTop:12}}>
        <p className="muted" style={{marginBottom:6}}>Rejected records:</p>
        {result.errors.map((e, i) =>
          <p key={i} className="muted" style={{fontSize:12}}>index {e.index}: {e.error}</p>)}
      </div>}
    </SectionCard>}
  </div>;
}

// ── App shell ──────────────────────────────────────────────────────────────
const TABS = [
  {id:'dashboard', label:'Dashboard', icon:'📊'},
  {id:'firs', label:'FIR Records', icon:'📋'},
  {id:'offenders', label:'Repeat Offenders', icon:'🔁'},
  {id:'trends', label:'Crime Trends', icon:'📈'},
  {id:'stations', label:'Station Analysis', icon:'🏛'},
  {id:'networks', label:'Crime Networks', icon:'🕸'},
  {id:'chat', label:'Ask Bob', icon:'🤖'},
  {id:'report', label:'Intel Report', icon:'📄'},
  {id:'upload', label:'Ingest FIRs', icon:'⬆'},
];

function App() {
  // Deep-linkable tabs: the old build reset to the dashboard on every reload
  // and offered no way to share a view.
  const [tab, setTab] = useState(() =>
    TABS.some((t) => t.id === window.location.hash.slice(1))
      ? window.location.hash.slice(1) : 'dashboard');
  const dashboard = useApi('/dashboard');
  const health = useApi('/health');
  const tabRefs = useRef({});
  // Owned here so the thread is the same whether the officer uses the tab or
  // the floating dock, and survives switching between them.
  const chat = useChatEngine();
  const [focusFIR, setFocusFIR] = useState(null);

  useEffect(() => {
    const onHash = () => {
      const id = window.location.hash.slice(1);
      if (TABS.some((t) => t.id === id)) setTab(id);
    };
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  const select = (id) => { setTab(id); window.location.hash = id; };

  /** Jump from a drill-down straight to that FIR in the records tab. */
  const openFIR = useCallback((firNumber) => {
    setFocusFIR(firNumber);
    setTab('firs');
    window.location.hash = 'firs';
  }, []);

  // Arrow-key navigation, as expected of an ARIA tablist.
  const onTabKey = (e) => {
    const i = TABS.findIndex((t) => t.id === tab);
    let next = null;
    if (e.key === 'ArrowRight') next = TABS[(i + 1) % TABS.length];
    else if (e.key === 'ArrowLeft') next = TABS[(i - 1 + TABS.length) % TABS.length];
    else if (e.key === 'Home') next = TABS[0];
    else if (e.key === 'End') next = TABS[TABS.length - 1];
    if (next) { e.preventDefault(); select(next.id); tabRefs.current[next.id]?.focus(); }
  };

  const status = health.data;
  const online = !health.error && status?.status === 'ok';

  return <div style={{minHeight:'100vh',display:'flex',flexDirection:'column'}}>
    <header style={{background:'var(--bg2)',borderBottom:'1px solid var(--border)',
                    position:'sticky',top:0,zIndex:50}}>
      <div className="shell" style={{padding:'12px 20px',display:'flex',alignItems:'center',
           justifyContent:'space-between',gap:12}}>
        <div style={{display:'flex',alignItems:'center',gap:14,minWidth:0}}>
          <div aria-hidden="true" style={{width:42,height:42,borderRadius:10,flexShrink:0,
              background:'linear-gradient(135deg,#2563eb,#5b9bff)',display:'flex',
              alignItems:'center',justifyContent:'center',fontSize:17,fontWeight:800,color:'#fff'}}>FI</div>
          <div style={{minWidth:0}}>
            <h1 style={{fontSize:17,fontWeight:700}}>FIR Intelligence System</h1>
            <p className="muted header-sub" style={{fontSize:11}}>
              NLP entity extraction · cross-FIR correlation · repeat offender detection</p>
          </div>
        </div>
        <div className="header-meta" style={{display:'flex',alignItems:'center',gap:14,flexShrink:0}}>
          <span title={status ? `Storage: ${status.storage} · Model: ${status.language_model}` : ''}
                style={{padding:'4px 12px',borderRadius:20,fontSize:11,fontWeight:700,
                  background: online ? 'rgba(31,192,143,.14)' : 'rgba(251,90,117,.14)',
                  color: online ? 'var(--green)' : 'var(--red)',
                  border: `1px solid ${online ? 'rgba(31,192,143,.3)' : 'rgba(251,90,117,.3)'}`}}>
            ● {health.loading ? 'CONNECTING' : online ? 'LIVE' : 'OFFLINE'}
          </span>
          {status && <span className="muted header-stats" style={{fontSize:11}}>
            {status.firs_analyzed} FIRs · {status.language_model}
          </span>}
        </div>
      </div>
    </header>

    <nav className="shell" style={{padding:'12px 20px'}} aria-label="Sections">
      <div role="tablist" aria-label="Dashboard sections" onKeyDown={onTabKey}
           style={{display:'flex',gap:6,overflowX:'auto',paddingBottom:4}}>
        {TABS.map((t) =>
          <button key={t.id} role="tab" id={`tab-${t.id}`} className="tab"
                  ref={(el) => { tabRefs.current[t.id] = el; }}
                  aria-selected={tab === t.id} aria-controls={`panel-${t.id}`}
                  tabIndex={tab === t.id ? 0 : -1} onClick={() => select(t.id)}>
            <span aria-hidden="true" style={{marginRight:6}}>{t.icon}</span>{t.label}
          </button>)}
      </div>
    </nav>

    <main id="main" className="shell" style={{padding:'0 20px 40px',flex:1}}>
      <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`} tabIndex={-1}>
      {tab === 'dashboard' && <Dashboard state={dashboard} onOpenFIR={openFIR}/>}
      {tab === 'firs' && <FIRList initialQuery={focusFIR}/>}
      {tab === 'offenders' && <RepeatOffenders threshold={dashboard.data?.name_match_threshold}/>}
      {tab === 'trends' && <CrimeTrends state={dashboard}/>}
      {tab === 'stations' && <StationSummary/>}
      {tab === 'networks' && <NetworkView/>}
      {tab === 'chat' && <BobChat chat={chat}/>}
      {tab === 'report' && <ReportView/>}
      {tab === 'upload' && <UploadPanel onIngested={() => { dashboard.reload(); health.reload(); }}/>}
      </div>
    </main>

    <footer style={{borderTop:'1px solid var(--border)',padding:'16px 20px',
            textAlign:'center',fontSize:11,color:'var(--text3)'}}>
      FIR Intelligence &amp; Crime Pattern Detector · FastAPI + React + Recharts ·
      findings are automated correlations and require verification by the investigating officer
    </footer>

    {/* Hidden on the chat tab, where the full conversation is already on screen. */}
    <ChatDock chat={chat} hidden={tab === 'chat'}/>
  </div>;
}

ReactDOM.createRoot(document.getElementById('root')).render(<App/>);
