/**
 * FIR Intelligence dashboard.
 *
 * This is the SOURCE file. The browser loads the precompiled `app.js`;
 * regenerate it after editing with `./scripts/build-ui.sh`.
 */
const {
  useState,
  useEffect,
  useCallback,
  useMemo,
  useRef
} = React;
const {
  PieChart,
  Pie,
  Cell,
  BarChart,
  Bar,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  RadarChart,
  Radar,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis
} = Recharts;
const API = '/api';
const COLORS = ['#5b9bff', '#fb5a75', '#1fc08f', '#f7a53b', '#b49bff', '#3cddf0', '#f887c4', '#fd9c52', '#14b8a6', '#6366f1', '#818cf8', '#e11d48', '#84cc16', '#0ea5e9', '#d946ef'];
const RISK_COLOR = {
  critical: '#fb5a75',
  high: '#fd9c52',
  medium: '#f7a53b',
  low: '#1fc08f'
};
const CHART_TOOLTIP = {
  contentStyle: {
    background: '#151d35',
    border: '1px solid #243058',
    borderRadius: '10px',
    color: '#edf2ff',
    fontSize: '13px',
    boxShadow: '0 8px 24px rgba(0,0,0,.4)'
  },
  itemStyle: {
    color: '#9dafd4'
  },
  labelStyle: {
    color: '#edf2ff'
  }
};

// `String.replace` with a string pattern only swaps the FIRST match, so
// multi-underscore keys were rendering half-formatted.
const label = s => String(s || '').split('_').join(' ');
const titleCase = s => label(s).replace(/\b\w/g, c => c.toUpperCase());

/** fetch + JSON with real error propagation (the old helper returned null on
 *  every failure, so the UI could not tell "empty" from "broken"). */
async function apiGet(path, signal) {
  const res = await fetch(API + path, {
    signal
  });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      if (body.detail) detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail);
    } catch (e) {/* non-JSON error body */}
    throw new Error(detail);
  }
  return res.json();
}
function useApi(path, deps = []) {
  const [state, setState] = useState({
    data: null,
    error: null,
    loading: true
  });
  const [nonce, setNonce] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    setState(s => ({
      ...s,
      loading: true,
      error: null
    }));
    apiGet(path, controller.signal).then(data => {
      if (active) setState({
        data,
        error: null,
        loading: false
      });
    }).catch(err => {
      if (!active || err.name === 'AbortError') return;
      setState({
        data: null,
        error: err.message || 'Request failed',
        loading: false
      });
    });
    return () => {
      active = false;
      controller.abort();
    };
  }, [path, nonce, ...deps]);
  return {
    ...state,
    reload: () => setNonce(n => n + 1)
  };
}
function Spinner({
  label: text = 'Loading'
}) {
  return /*#__PURE__*/React.createElement("div", {
    role: "status",
    "aria-live": "polite",
    style: {
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      gap: 12,
      padding: '70px 0'
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "spinner"
  }), /*#__PURE__*/React.createElement("span", {
    className: "muted"
  }, text, "\u2026"));
}
function ErrorState({
  error,
  onRetry
}) {
  return /*#__PURE__*/React.createElement("div", {
    className: "glass p-5",
    role: "alert",
    style: {
      textAlign: 'center',
      padding: '40px 20px'
    }
  }, /*#__PURE__*/React.createElement("p", {
    style: {
      fontSize: 34,
      marginBottom: 10
    },
    "aria-hidden": "true"
  }, "\u26A0"), /*#__PURE__*/React.createElement("h2", {
    style: {
      fontSize: 17,
      fontWeight: 700,
      marginBottom: 6
    }
  }, "Could not load this view"), /*#__PURE__*/React.createElement("p", {
    className: "muted",
    style: {
      marginBottom: 16
    }
  }, error), onRetry && /*#__PURE__*/React.createElement("button", {
    className: "btn btn-primary",
    onClick: onRetry
  }, "Retry"));
}
function EmptyState({
  title,
  hint,
  action
}) {
  return /*#__PURE__*/React.createElement("div", {
    className: "glass p-5",
    style: {
      textAlign: 'center',
      padding: '46px 20px'
    }
  }, /*#__PURE__*/React.createElement("p", {
    style: {
      fontSize: 30,
      marginBottom: 10
    },
    "aria-hidden": "true"
  }, "\u2205"), /*#__PURE__*/React.createElement("h2", {
    style: {
      fontSize: 16,
      fontWeight: 700,
      marginBottom: 6
    }
  }, title), hint && /*#__PURE__*/React.createElement("p", {
    className: "muted"
  }, hint), action && /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: 16
    }
  }, action));
}

/** One place that decides loading vs error vs empty vs content. Previously each
 *  tab returned a spinner when its list was empty, so a legitimately empty or
 *  failed response span forever. */
function Async({
  state,
  isEmpty,
  empty,
  children
}) {
  if (state.loading) return /*#__PURE__*/React.createElement(Spinner, null);
  if (state.error) return /*#__PURE__*/React.createElement(ErrorState, {
    error: state.error,
    onRetry: state.reload
  });
  if (isEmpty && isEmpty(state.data)) return empty || /*#__PURE__*/React.createElement(EmptyState, {
    title: "Nothing to show"
  });
  return children(state.data);
}
function StatCard({
  label: text,
  value,
  sub,
  color,
  icon
}) {
  return /*#__PURE__*/React.createElement("div", {
    className: "glass p-5"
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'flex-start',
      gap: 10
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement("p", {
    style: {
      color: 'var(--text2)',
      fontSize: 13,
      fontWeight: 600,
      marginBottom: 6
    }
  }, text), /*#__PURE__*/React.createElement("p", {
    style: {
      fontSize: 30,
      fontWeight: 700,
      color,
      lineHeight: 1.1
    }
  }, value), sub && /*#__PURE__*/React.createElement("p", {
    style: {
      fontSize: 12,
      color: 'var(--text3)',
      marginTop: 4
    }
  }, sub)), /*#__PURE__*/React.createElement("div", {
    "aria-hidden": "true",
    style: {
      width: 40,
      height: 40,
      borderRadius: 10,
      background: color + '22',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      fontSize: 19,
      flexShrink: 0
    }
  }, icon)));
}
function SectionCard({
  title,
  subtitle,
  children,
  actions
}) {
  return /*#__PURE__*/React.createElement("section", {
    className: "glass p-5"
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'flex-start',
      gap: 12,
      marginBottom: 14,
      flexWrap: 'wrap'
    }
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("h2", {
    style: {
      fontSize: 15,
      fontWeight: 700
    }
  }, title), subtitle && /*#__PURE__*/React.createElement("p", {
    className: "muted",
    style: {
      marginTop: 2
    }
  }, subtitle)), actions), children);
}

// ── Dashboard ──────────────────────────────────────────────────────────────
function Dashboard({
  state
}) {
  return /*#__PURE__*/React.createElement(Async, {
    state: state
  }, data => {
    const crimeData = Object.entries(data.crime_breakdown || {}).map(([name, value]) => ({
      name: label(name),
      value
    })).sort((a, b) => b.value - a.value);
    const districtData = Object.entries(data.district_breakdown || {}).map(([name, value]) => ({
      name,
      value
    })).sort((a, b) => b.value - a.value);
    const trendData = Object.entries(data.monthly_trend || {}).map(([name, value]) => ({
      name,
      value
    }));
    const sev = data.severity_distribution || {};
    const totalSev = Object.values(sev).reduce((a, b) => a + b, 0) || 1;
    const nets = data.crime_networks || [];
    return /*#__PURE__*/React.createElement("div", {
      className: "stack fade-in"
    }, /*#__PURE__*/React.createElement("div", {
      className: "stat-grid"
    }, /*#__PURE__*/React.createElement(StatCard, {
      label: "FIRs Analysed",
      value: data.total_firs,
      color: "var(--blue)",
      icon: "\uD83D\uDCCB",
      sub: `${data.total_districts} districts · ${data.total_stations} stations`
    }), /*#__PURE__*/React.createElement(StatCard, {
      label: "Accused Identified",
      value: data.total_accused,
      color: "var(--red)",
      icon: "\uD83D\uDC64",
      sub: "named across all FIRs"
    }), /*#__PURE__*/React.createElement(StatCard, {
      label: "Victims Recorded",
      value: data.total_victims,
      color: "var(--amber)",
      icon: "\uD83D\uDEE1",
      sub: "complainants + victims"
    }), /*#__PURE__*/React.createElement(StatCard, {
      label: "Repeat Offenders",
      value: data.repeat_offenders_count,
      color: "var(--purple)",
      icon: "\uD83D\uDD01",
      sub: `fuzzy name match ≥ ${data.name_match_threshold}%`
    })), /*#__PURE__*/React.createElement(SectionCard, {
      title: "Severity Distribution",
      subtitle: `Mean severity ${Number(data.avg_severity || 0).toFixed(1)}/100 across ${data.total_firs} FIRs`
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        display: 'flex',
        borderRadius: 8,
        overflow: 'hidden',
        height: 28
      },
      role: "img",
      "aria-label": ['critical', 'high', 'medium', 'low'].map(l => `${l}: ${sev[l] || 0}`).join(', ')
    }, ['critical', 'high', 'medium', 'low'].map(level => {
      const pct = (sev[level] || 0) / totalSev * 100;
      if (pct <= 0) return null;
      return /*#__PURE__*/React.createElement("div", {
        key: level,
        title: `${level}: ${sev[level]}`,
        style: {
          width: pct + '%',
          background: RISK_COLOR[level],
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: 11,
          fontWeight: 700,
          color: '#0a0e1a'
        }
      }, pct > 9 ? `${level.toUpperCase()} ${sev[level]}` : '');
    })), /*#__PURE__*/React.createElement("div", {
      style: {
        display: 'flex',
        gap: 18,
        marginTop: 10,
        flexWrap: 'wrap'
      }
    }, ['critical', 'high', 'medium', 'low'].map(l => /*#__PURE__*/React.createElement("span", {
      key: l,
      style: {
        display: 'flex',
        alignItems: 'center',
        gap: 6,
        fontSize: 12,
        color: 'var(--text2)'
      }
    }, /*#__PURE__*/React.createElement("span", {
      "aria-hidden": "true",
      style: {
        width: 10,
        height: 10,
        borderRadius: 3,
        background: RISK_COLOR[l]
      }
    }), l, ": ", sev[l] || 0)))), /*#__PURE__*/React.createElement("div", {
      className: "grid-2"
    }, /*#__PURE__*/React.createElement(SectionCard, {
      title: "Crime Type Distribution"
    }, /*#__PURE__*/React.createElement(ResponsiveContainer, {
      width: "100%",
      height: 280
    }, /*#__PURE__*/React.createElement(PieChart, {
      margin: {
        top: 8,
        right: 70,
        bottom: 8,
        left: 70
      }
    }, /*#__PURE__*/React.createElement(Pie, {
      data: crimeData,
      dataKey: "value",
      nameKey: "name",
      cx: "50%",
      cy: "50%",
      outerRadius: 88,
      innerRadius: 52,
      paddingAngle: 2,
      minAngle: 2,
      label: ({
        name,
        percent
      }) => percent > .045 ? `${name} ${(percent * 100).toFixed(0)}%` : '',
      labelLine: {
        stroke: '#5b9bff',
        strokeWidth: 1
      },
      isAnimationActive: false
    }, crimeData.map((_, i) => /*#__PURE__*/React.createElement(Cell, {
      key: i,
      fill: COLORS[i % COLORS.length]
    }))), /*#__PURE__*/React.createElement(Tooltip, CHART_TOOLTIP)))), /*#__PURE__*/React.createElement(SectionCard, {
      title: "FIRs by District"
    }, /*#__PURE__*/React.createElement(ResponsiveContainer, {
      width: "100%",
      height: 280
    }, /*#__PURE__*/React.createElement(BarChart, {
      data: districtData,
      margin: {
        bottom: 34
      }
    }, /*#__PURE__*/React.createElement(CartesianGrid, {
      strokeDasharray: "3 3",
      stroke: "#1c2748"
    }), /*#__PURE__*/React.createElement(XAxis, {
      dataKey: "name",
      stroke: "#9dafd4",
      tick: {
        fontSize: 11
      },
      angle: -35,
      textAnchor: "end",
      interval: 0,
      height: 60
    }), /*#__PURE__*/React.createElement(YAxis, {
      stroke: "#9dafd4",
      allowDecimals: false
    }), /*#__PURE__*/React.createElement(Tooltip, CHART_TOOLTIP), /*#__PURE__*/React.createElement(Bar, {
      dataKey: "value",
      radius: [6, 6, 0, 0],
      isAnimationActive: false
    }, districtData.map((_, i) => /*#__PURE__*/React.createElement(Cell, {
      key: i,
      fill: COLORS[i % COLORS.length]
    }))))))), /*#__PURE__*/React.createElement(SectionCard, {
      title: "Monthly Crime Trend"
    }, /*#__PURE__*/React.createElement(ResponsiveContainer, {
      width: "100%",
      height: 240
    }, /*#__PURE__*/React.createElement(AreaChart, {
      data: trendData
    }, /*#__PURE__*/React.createElement("defs", null, /*#__PURE__*/React.createElement("linearGradient", {
      id: "trendGrad",
      x1: "0",
      y1: "0",
      x2: "0",
      y2: "1"
    }, /*#__PURE__*/React.createElement("stop", {
      offset: "5%",
      stopColor: "#5b9bff",
      stopOpacity: .35
    }), /*#__PURE__*/React.createElement("stop", {
      offset: "95%",
      stopColor: "#5b9bff",
      stopOpacity: 0
    }))), /*#__PURE__*/React.createElement(CartesianGrid, {
      strokeDasharray: "3 3",
      stroke: "#1c2748"
    }), /*#__PURE__*/React.createElement(XAxis, {
      dataKey: "name",
      stroke: "#9dafd4",
      tick: {
        fontSize: 11
      }
    }), /*#__PURE__*/React.createElement(YAxis, {
      stroke: "#9dafd4",
      allowDecimals: false
    }), /*#__PURE__*/React.createElement(Tooltip, CHART_TOOLTIP), /*#__PURE__*/React.createElement(Area, {
      type: "monotone",
      dataKey: "value",
      stroke: "#5b9bff",
      fill: "url(#trendGrad)",
      strokeWidth: 2.5,
      isAnimationActive: false,
      name: "FIRs"
    })))), /*#__PURE__*/React.createElement(SectionCard, {
      title: "Crime Networks Detected",
      subtitle: `${nets.length} clusters linked by shared offenders or shared modus operandi`
    }, nets.length === 0 ? /*#__PURE__*/React.createElement("p", {
      className: "muted"
    }, "No networks detected in the current corpus.") : /*#__PURE__*/React.createElement("div", {
      className: "card-grid"
    }, nets.slice(0, 9).map((net, i) => /*#__PURE__*/React.createElement("article", {
      key: net.name + i,
      style: {
        padding: 16,
        borderRadius: 10,
        background: 'rgba(91,155,255,.06)',
        border: '1px solid rgba(91,155,255,.18)'
      }
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        display: 'flex',
        justifyContent: 'space-between',
        gap: 8,
        alignItems: 'flex-start'
      }
    }, /*#__PURE__*/React.createElement("h3", {
      style: {
        color: 'var(--blue)',
        fontWeight: 700,
        fontSize: 14
      }
    }, net.name), /*#__PURE__*/React.createElement("span", {
      className: `badge badge-${net.risk_level || 'medium'}`
    }, net.risk_level)), /*#__PURE__*/React.createElement("p", {
      className: "muted",
      style: {
        marginTop: 6,
        fontSize: 12
      }
    }, net.fir_count, " linked FIRs across ", (net.districts || []).join(', ')), /*#__PURE__*/React.createElement("div", {
      style: {
        display: 'flex',
        flexWrap: 'wrap',
        gap: 4,
        marginTop: 8
      }
    }, (net.crime_types || []).map((ct, j) => /*#__PURE__*/React.createElement("span", {
      key: j,
      className: "chip",
      style: {
        background: 'rgba(91,155,255,.14)',
        color: 'var(--blue)'
      }
    }, label(ct)))))))));
  });
}

// ── FIR records ────────────────────────────────────────────────────────────
const PAGE_SIZE = 20;
function FIRList() {
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');
  const [crimeType, setCrimeType] = useState('');
  const [district, setDistrict] = useState('');
  const [severity, setSeverity] = useState('');
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState(null);
  const filters = useApi('/filters');

  // Debounce so a keystroke does not fire a request per character.
  useEffect(() => {
    const id = setTimeout(() => {
      setQuery(search);
      setOffset(0);
    }, 300);
    return () => clearTimeout(id);
  }, [search]);
  const params = new URLSearchParams({
    limit: String(PAGE_SIZE),
    offset: String(offset)
  });
  if (query) params.set('q', query);
  if (crimeType) params.set('crime_type', crimeType);
  if (district) params.set('district', district);
  if (severity) params.set('severity', severity);
  const list = useApi(`/firs?${params.toString()}`);
  const reset = setter => e => {
    setter(e.target.value);
    setOffset(0);
  };
  const opts = filters.data || {
    crime_types: [],
    districts: [],
    severities: []
  };
  return /*#__PURE__*/React.createElement("div", {
    className: "stack fade-in"
  }, /*#__PURE__*/React.createElement("div", {
    className: "toolbar"
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      flex: '2 1 260px'
    }
  }, /*#__PURE__*/React.createElement("label", {
    htmlFor: "fir-search"
  }, "Search"), /*#__PURE__*/React.createElement("input", {
    id: "fir-search",
    type: "search",
    value: search,
    style: {
      width: '100%'
    },
    placeholder: "FIR number, accused, victim, keyword\u2026",
    onChange: e => setSearch(e.target.value)
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: '1 1 150px'
    }
  }, /*#__PURE__*/React.createElement("label", {
    htmlFor: "fir-type"
  }, "Crime type"), /*#__PURE__*/React.createElement("select", {
    id: "fir-type",
    value: crimeType,
    onChange: reset(setCrimeType),
    style: {
      width: '100%'
    }
  }, /*#__PURE__*/React.createElement("option", {
    value: ""
  }, "All types"), opts.crime_types.map(t => /*#__PURE__*/React.createElement("option", {
    key: t,
    value: t
  }, titleCase(t))))), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: '1 1 150px'
    }
  }, /*#__PURE__*/React.createElement("label", {
    htmlFor: "fir-district"
  }, "District"), /*#__PURE__*/React.createElement("select", {
    id: "fir-district",
    value: district,
    onChange: reset(setDistrict),
    style: {
      width: '100%'
    }
  }, /*#__PURE__*/React.createElement("option", {
    value: ""
  }, "All districts"), opts.districts.map(d => /*#__PURE__*/React.createElement("option", {
    key: d,
    value: d
  }, d)))), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: '1 1 130px'
    }
  }, /*#__PURE__*/React.createElement("label", {
    htmlFor: "fir-sev"
  }, "Severity"), /*#__PURE__*/React.createElement("select", {
    id: "fir-sev",
    value: severity,
    onChange: reset(setSeverity),
    style: {
      width: '100%'
    }
  }, /*#__PURE__*/React.createElement("option", {
    value: ""
  }, "Any severity"), (opts.severities || []).map(s => /*#__PURE__*/React.createElement("option", {
    key: s,
    value: s
  }, titleCase(s)))))), /*#__PURE__*/React.createElement(Async, {
    state: list,
    isEmpty: d => !d.items.length,
    empty: /*#__PURE__*/React.createElement(EmptyState, {
      title: "No FIRs match these filters",
      hint: "Try clearing the search box or widening the crime type and district filters.",
      action: /*#__PURE__*/React.createElement("button", {
        className: "btn btn-ghost",
        onClick: () => {
          setSearch('');
          setCrimeType('');
          setDistrict('');
          setSeverity('');
          setOffset(0);
        }
      }, "Clear all filters")
    })
  }, data => /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("p", {
    className: "muted",
    "aria-live": "polite"
  }, "Showing ", data.offset + 1, "\u2013", data.offset + data.items.length, " of ", data.total, " records"), data.items.map(fir => /*#__PURE__*/React.createElement("button", {
    key: fir.fir_number,
    className: "row-card",
    "aria-expanded": selected === fir.fir_number,
    onClick: () => setSelected(selected === fir.fir_number ? null : fir.fir_number)
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'center',
      flexWrap: 'wrap',
      gap: 8
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 10,
      flexWrap: 'wrap'
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'ui-monospace,Menlo,monospace',
      color: 'var(--blue)',
      fontWeight: 700
    }
  }, fir.fir_number), /*#__PURE__*/React.createElement("span", {
    className: `badge badge-${fir.severity}`
  }, fir.severity), /*#__PURE__*/React.createElement("span", {
    className: "chip",
    style: {
      background: 'var(--card2)',
      color: 'var(--text2)'
    }
  }, label(fir.crime_type))), /*#__PURE__*/React.createElement("span", {
    className: "muted"
  }, fir.date, " \xB7 ", fir.district, " \xB7 ", fir.police_station)), /*#__PURE__*/React.createElement("p", {
    className: "muted clamp-2",
    style: {
      marginTop: 8
    }
  }, fir.summary), selected === fir.fir_number && /*#__PURE__*/React.createElement(FIRDetail, {
    firNumber: fir.fir_number
  }))), /*#__PURE__*/React.createElement("nav", {
    "aria-label": "Pagination",
    style: {
      display: 'flex',
      gap: 10,
      justifyContent: 'center',
      alignItems: 'center',
      paddingTop: 6
    }
  }, /*#__PURE__*/React.createElement("button", {
    className: "btn btn-ghost",
    disabled: offset === 0,
    onClick: () => setOffset(Math.max(0, offset - PAGE_SIZE))
  }, "\u2190 Previous"), /*#__PURE__*/React.createElement("span", {
    className: "muted"
  }, "Page ", Math.floor(offset / PAGE_SIZE) + 1, " of", ' ', Math.max(1, Math.ceil(data.total / PAGE_SIZE))), /*#__PURE__*/React.createElement("button", {
    className: "btn btn-ghost",
    disabled: !data.has_more,
    onClick: () => setOffset(offset + PAGE_SIZE)
  }, "Next \u2192")))));
}

/** Full record, fetched on demand — the list only carries a preview. */
function FIRDetail({
  firNumber
}) {
  const detail = useApi(`/firs/${firNumber}`);
  return /*#__PURE__*/React.createElement("div", {
    className: "fade-in",
    style: {
      marginTop: 16,
      paddingTop: 16,
      borderTop: '1px solid var(--border)'
    }
  }, /*#__PURE__*/React.createElement(Async, {
    state: detail
  }, fir => {
    const ent = fir.entities || {};
    const mo = ent.modus_operandi;
    return /*#__PURE__*/React.createElement("div", {
      style: {
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit,minmax(230px,1fr))',
        gap: 16
      }
    }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("h4", {
      style: {
        fontSize: 13,
        fontWeight: 700,
        color: 'var(--red)',
        marginBottom: 8
      }
    }, "Accused (", (ent.accused || []).length, ")"), (ent.accused || []).length === 0 && /*#__PURE__*/React.createElement("p", {
      className: "muted"
    }, "None named in this FIR."), (ent.accused || []).map((a, i) => /*#__PURE__*/React.createElement("div", {
      key: i,
      style: {
        marginBottom: 8,
        padding: 10,
        borderRadius: 8,
        background: 'var(--bg2)'
      }
    }, /*#__PURE__*/React.createElement("p", {
      style: {
        fontWeight: 700,
        fontSize: 13
      }
    }, a.name), a.aliases?.length > 0 && /*#__PURE__*/React.createElement("p", {
      className: "muted",
      style: {
        fontSize: 11
      }
    }, "alias ", a.aliases.join(', ')), a.age != null && /*#__PURE__*/React.createElement("p", {
      className: "muted",
      style: {
        fontSize: 11
      }
    }, "Age ", a.age, a.gender ? ` · ${a.gender}` : ''), a.father_name && /*#__PURE__*/React.createElement("p", {
      className: "muted",
      style: {
        fontSize: 11
      }
    }, "S/o ", a.father_name), a.address && /*#__PURE__*/React.createElement("p", {
      className: "muted",
      style: {
        fontSize: 11
      }
    }, a.address), a.id_marks?.length > 0 && /*#__PURE__*/React.createElement("p", {
      className: "muted",
      style: {
        fontSize: 11
      }
    }, "Marks: ", a.id_marks.join('; '))))), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("h4", {
      style: {
        fontSize: 13,
        fontWeight: 700,
        color: 'var(--green)',
        marginBottom: 8
      }
    }, "Victims (", (ent.victims || []).length, ")"), (ent.victims || []).map((v, i) => /*#__PURE__*/React.createElement("div", {
      key: i,
      style: {
        marginBottom: 8,
        padding: 10,
        borderRadius: 8,
        background: 'var(--bg2)'
      }
    }, /*#__PURE__*/React.createElement("p", {
      style: {
        fontWeight: 700,
        fontSize: 13
      }
    }, v.name), v.age != null && /*#__PURE__*/React.createElement("p", {
      className: "muted",
      style: {
        fontSize: 11
      }
    }, "Age ", v.age, v.gender ? ` · ${v.gender}` : ''), v.occupation && /*#__PURE__*/React.createElement("p", {
      className: "muted",
      style: {
        fontSize: 11
      }
    }, v.occupation))), mo && /*#__PURE__*/React.createElement("div", {
      style: {
        marginTop: 10
      }
    }, /*#__PURE__*/React.createElement("h4", {
      style: {
        fontSize: 13,
        fontWeight: 700,
        color: 'var(--amber)',
        marginBottom: 4
      }
    }, "Modus Operandi"), /*#__PURE__*/React.createElement("p", {
      className: "muted"
    }, mo.description || mo.approach_method || '—'))), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("h4", {
      style: {
        fontSize: 13,
        fontWeight: 700,
        color: 'var(--purple)',
        marginBottom: 8
      }
    }, "Sections"), /*#__PURE__*/React.createElement("div", {
      style: {
        display: 'flex',
        flexWrap: 'wrap',
        gap: 4,
        marginBottom: 12
      }
    }, (ent.ipc_sections || []).map((s, i) => /*#__PURE__*/React.createElement("span", {
      key: i,
      className: "chip",
      style: {
        background: 'rgba(180,155,255,.14)',
        color: 'var(--purple)'
      }
    }, s)), (ent.ipc_sections || []).length === 0 && /*#__PURE__*/React.createElement("span", {
      className: "muted"
    }, "Not recorded")), /*#__PURE__*/React.createElement("h4", {
      style: {
        fontSize: 13,
        fontWeight: 700,
        color: 'var(--cyan)',
        marginBottom: 8
      }
    }, "Linked FIRs (", (fir.related || []).length, ")"), (fir.related || []).length === 0 && /*#__PURE__*/React.createElement("p", {
      className: "muted"
    }, "No cross-FIR links found."), (fir.related || []).slice(0, 8).map((r, i) => /*#__PURE__*/React.createElement("p", {
      key: i,
      className: "muted",
      style: {
        fontSize: 11,
        marginBottom: 3
      }
    }, /*#__PURE__*/React.createElement("span", {
      style: {
        fontFamily: 'ui-monospace,Menlo,monospace',
        color: 'var(--blue)'
      }
    }, r.fir_number), ' — ', r.reason))), /*#__PURE__*/React.createElement("div", {
      style: {
        gridColumn: '1 / -1'
      }
    }, /*#__PURE__*/React.createElement("h4", {
      style: {
        fontSize: 13,
        fontWeight: 700,
        marginBottom: 6
      }
    }, "FIR narrative"), /*#__PURE__*/React.createElement("p", {
      className: "muted",
      style: {
        whiteSpace: 'pre-wrap'
      }
    }, fir.text)));
  }));
}

// ── Repeat offenders ───────────────────────────────────────────────────────
function RepeatOffenders({
  threshold
}) {
  const [risk, setRisk] = useState('');
  const state = useApi(`/repeat-offenders${risk ? `?risk_level=${risk}` : ''}`);
  return /*#__PURE__*/React.createElement("div", {
    className: "stack fade-in"
  }, /*#__PURE__*/React.createElement("div", {
    className: "toolbar",
    style: {
      justifyContent: 'space-between'
    }
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("h2", {
    style: {
      fontSize: 19,
      fontWeight: 700
    }
  }, "Flagged Repeat Offenders"), /*#__PURE__*/React.createElement("p", {
    className: "muted"
  }, "Identity resolved by name, alias and locality correlation (fuzzy threshold ", threshold ?? '—', "%). Approximate name matches require corroborating evidence before they are merged.")), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("label", {
    htmlFor: "ro-risk"
  }, "Risk level"), /*#__PURE__*/React.createElement("select", {
    id: "ro-risk",
    value: risk,
    onChange: e => setRisk(e.target.value)
  }, /*#__PURE__*/React.createElement("option", {
    value: ""
  }, "All risk levels"), ['critical', 'high', 'medium', 'low'].map(r => /*#__PURE__*/React.createElement("option", {
    key: r,
    value: r
  }, titleCase(r)))))), /*#__PURE__*/React.createElement(Async, {
    state: state,
    isEmpty: d => !d.length,
    empty: /*#__PURE__*/React.createElement(EmptyState, {
      title: "No repeat offenders at this risk level",
      hint: "An accused must appear in at least two distinct FIRs to be flagged."
    })
  }, offenders => /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("p", {
    className: "muted",
    "aria-live": "polite"
  }, offenders.length, " offenders"), offenders.map((off, i) => /*#__PURE__*/React.createElement("article", {
    key: i,
    className: "glass p-5 glow"
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      justifyContent: 'space-between',
      gap: 10,
      alignItems: 'flex-start'
    }
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("h3", {
    style: {
      fontSize: 17,
      fontWeight: 700,
      color: 'var(--red)'
    }
  }, off.primary_name), off.aliases?.length > 0 && /*#__PURE__*/React.createElement("p", {
    className: "muted",
    style: {
      marginTop: 2
    }
  }, "Aliases: ", off.aliases.join(', '))), /*#__PURE__*/React.createElement("span", {
    className: `badge badge-${off.risk_level}`,
    style: {
      fontSize: 12,
      padding: '4px 13px'
    }
  }, off.risk_level)), /*#__PURE__*/React.createElement("div", {
    className: "metric-grid",
    style: {
      marginTop: 14
    }
  }, [['Linked FIRs', off.fir_count, 'var(--blue)'], ['Districts', (off.districts || []).length, 'var(--cyan)'], ['Offences', (off.crime_types || []).length, 'var(--amber)'], ['Confidence', `${Math.round((off.match_confidence || 0) * 100)}%`, 'var(--green)']].map(([k, v, c]) => /*#__PURE__*/React.createElement("div", {
    key: k,
    style: {
      padding: 10,
      borderRadius: 8,
      background: 'var(--bg2)',
      textAlign: 'center'
    }
  }, /*#__PURE__*/React.createElement("p", {
    className: "muted",
    style: {
      fontSize: 11
    }
  }, k), /*#__PURE__*/React.createElement("p", {
    style: {
      fontWeight: 700,
      fontSize: 19,
      color: c
    }
  }, v)))), /*#__PURE__*/React.createElement("p", {
    className: "muted",
    style: {
      marginTop: 10,
      fontSize: 12
    }
  }, "Active ", off.first_seen, " \u2192 ", off.last_seen, " \xB7 ", (off.districts || []).join(', '), " \xB7", ' ', (off.crime_types || []).map(label).join(', ')), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexWrap: 'wrap',
      gap: 4,
      marginTop: 10
    }
  }, (off.linked_firs || []).map((f, j) => /*#__PURE__*/React.createElement("span", {
    key: j,
    className: "chip",
    style: {
      background: 'rgba(91,155,255,.1)',
      color: 'var(--blue)',
      border: '1px solid rgba(91,155,255,.22)'
    }
  }, f))), off.mo_signature && /*#__PURE__*/React.createElement("p", {
    className: "muted",
    style: {
      marginTop: 10
    }
  }, /*#__PURE__*/React.createElement("strong", {
    style: {
      color: 'var(--amber)'
    }
  }, "MO signature:"), " ", off.mo_signature), /*#__PURE__*/React.createElement("p", {
    className: "muted",
    style: {
      marginTop: 8,
      padding: 10,
      borderRadius: 8,
      background: 'var(--bg2)',
      borderLeft: '3px solid var(--cyan)'
    }
  }, off.intelligence_assessment))))));
}

// ── Crime trends ───────────────────────────────────────────────────────────
function CrimeTrends({
  state
}) {
  return /*#__PURE__*/React.createElement(Async, {
    state: state
  }, data => {
    const trendData = Object.entries(data.monthly_trend || {}).map(([name, value]) => ({
      name,
      value
    }));
    const ranking = Object.entries(data.crime_breakdown || {}).sort((a, b) => b[1] - a[1]);
    const maxCrime = ranking.length ? ranking[0][1] : 1;
    const radarData = ranking.slice(0, 8).map(([type, count]) => ({
      subject: label(type),
      A: count
    }));
    const districtData = Object.entries(data.district_breakdown || {}).map(([name, value]) => ({
      name,
      value
    })).sort((a, b) => b.value - a.value);
    return /*#__PURE__*/React.createElement("div", {
      className: "stack fade-in"
    }, /*#__PURE__*/React.createElement("div", {
      className: "grid-2"
    }, /*#__PURE__*/React.createElement(SectionCard, {
      title: "Crime Trend Over Time"
    }, /*#__PURE__*/React.createElement(ResponsiveContainer, {
      width: "100%",
      height: 280
    }, /*#__PURE__*/React.createElement(AreaChart, {
      data: trendData
    }, /*#__PURE__*/React.createElement("defs", null, /*#__PURE__*/React.createElement("linearGradient", {
      id: "tg2",
      x1: "0",
      y1: "0",
      x2: "0",
      y2: "1"
    }, /*#__PURE__*/React.createElement("stop", {
      offset: "5%",
      stopColor: "#5b9bff",
      stopOpacity: .35
    }), /*#__PURE__*/React.createElement("stop", {
      offset: "95%",
      stopColor: "#5b9bff",
      stopOpacity: 0
    }))), /*#__PURE__*/React.createElement(CartesianGrid, {
      strokeDasharray: "3 3",
      stroke: "#1c2748"
    }), /*#__PURE__*/React.createElement(XAxis, {
      dataKey: "name",
      stroke: "#9dafd4",
      tick: {
        fontSize: 11
      }
    }), /*#__PURE__*/React.createElement(YAxis, {
      stroke: "#9dafd4",
      allowDecimals: false
    }), /*#__PURE__*/React.createElement(Tooltip, CHART_TOOLTIP), /*#__PURE__*/React.createElement(Area, {
      type: "monotone",
      dataKey: "value",
      stroke: "#5b9bff",
      fill: "url(#tg2)",
      strokeWidth: 2.5,
      isAnimationActive: false,
      name: "FIRs"
    })))), /*#__PURE__*/React.createElement(SectionCard, {
      title: "Crime Radar Profile"
    }, /*#__PURE__*/React.createElement(ResponsiveContainer, {
      width: "100%",
      height: 280
    }, /*#__PURE__*/React.createElement(RadarChart, {
      data: radarData
    }, /*#__PURE__*/React.createElement(PolarGrid, {
      stroke: "#1c2748"
    }), /*#__PURE__*/React.createElement(PolarAngleAxis, {
      dataKey: "subject",
      stroke: "#9dafd4",
      tick: {
        fontSize: 11
      }
    }), /*#__PURE__*/React.createElement(PolarRadiusAxis, {
      stroke: "#1c2748",
      tick: {
        fontSize: 10,
        fill: '#7387b0'
      }
    }), /*#__PURE__*/React.createElement(Radar, {
      name: "FIRs",
      dataKey: "A",
      stroke: "#5b9bff",
      fill: "rgba(91,155,255,.25)",
      strokeWidth: 2,
      isAnimationActive: false
    }), /*#__PURE__*/React.createElement(Tooltip, CHART_TOOLTIP))))), /*#__PURE__*/React.createElement(SectionCard, {
      title: "Crime Type Ranking"
    }, /*#__PURE__*/React.createElement("div", {
      className: "stack",
      style: {
        gap: 10
      }
    }, ranking.map(([type, count], i) => /*#__PURE__*/React.createElement("div", {
      key: type,
      style: {
        display: 'flex',
        alignItems: 'center',
        gap: 12
      }
    }, /*#__PURE__*/React.createElement("span", {
      style: {
        width: 28,
        textAlign: 'center',
        fontWeight: 700,
        color: COLORS[i % COLORS.length]
      }
    }, "#", i + 1), /*#__PURE__*/React.createElement("span", {
      style: {
        width: 118,
        fontSize: 13,
        textTransform: 'capitalize',
        flexShrink: 0
      }
    }, label(type)), /*#__PURE__*/React.createElement("div", {
      style: {
        flex: 1,
        background: 'var(--bg2)',
        borderRadius: 20,
        height: 24,
        overflow: 'hidden',
        minWidth: 60
      }
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        height: '100%',
        borderRadius: 20,
        display: 'flex',
        alignItems: 'center',
        paddingLeft: 10,
        fontSize: 12,
        fontWeight: 700,
        color: '#0a0e1a',
        width: `${Math.max(count / maxCrime * 100, 12)}%`,
        background: `linear-gradient(90deg,${COLORS[i % COLORS.length]},${COLORS[i % COLORS.length]}aa)`
      }
    }, count)))))), /*#__PURE__*/React.createElement(SectionCard, {
      title: "District Crime Comparison"
    }, /*#__PURE__*/React.createElement(ResponsiveContainer, {
      width: "100%",
      height: 300
    }, /*#__PURE__*/React.createElement(BarChart, {
      data: districtData,
      margin: {
        bottom: 40
      }
    }, /*#__PURE__*/React.createElement(CartesianGrid, {
      strokeDasharray: "3 3",
      stroke: "#1c2748"
    }), /*#__PURE__*/React.createElement(XAxis, {
      dataKey: "name",
      stroke: "#9dafd4",
      tick: {
        fontSize: 11
      },
      angle: -35,
      textAnchor: "end",
      interval: 0,
      height: 70
    }), /*#__PURE__*/React.createElement(YAxis, {
      stroke: "#9dafd4",
      allowDecimals: false
    }), /*#__PURE__*/React.createElement(Tooltip, CHART_TOOLTIP), /*#__PURE__*/React.createElement(Bar, {
      dataKey: "value",
      radius: [6, 6, 0, 0],
      isAnimationActive: false,
      name: "FIRs"
    }, districtData.map((_, i) => /*#__PURE__*/React.createElement(Cell, {
      key: i,
      fill: COLORS[i % COLORS.length]
    })))))));
  });
}

// ── Stations ───────────────────────────────────────────────────────────────
function StationSummary() {
  const [filter, setFilter] = useState('');
  const state = useApi('/stations');
  return /*#__PURE__*/React.createElement("div", {
    className: "stack fade-in"
  }, /*#__PURE__*/React.createElement("div", {
    className: "toolbar",
    style: {
      justifyContent: 'space-between'
    }
  }, /*#__PURE__*/React.createElement("h2", {
    style: {
      fontSize: 19,
      fontWeight: 700
    }
  }, "Station-Level Analysis"), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: '0 1 280px'
    }
  }, /*#__PURE__*/React.createElement("label", {
    htmlFor: "station-search"
  }, "Filter stations"), /*#__PURE__*/React.createElement("input", {
    id: "station-search",
    type: "search",
    value: filter,
    style: {
      width: '100%'
    },
    placeholder: "Station or district\u2026",
    onChange: e => setFilter(e.target.value)
  }))), /*#__PURE__*/React.createElement(Async, {
    state: state,
    isEmpty: d => !d.length,
    empty: /*#__PURE__*/React.createElement(EmptyState, {
      title: "No station data available"
    })
  }, all => {
    const needle = filter.trim().toLowerCase();
    const stations = needle ? all.filter(s => s.station_name.toLowerCase().includes(needle) || s.district.toLowerCase().includes(needle)) : all;
    if (!stations.length) {
      return /*#__PURE__*/React.createElement(EmptyState, {
        title: `No station matches “${filter}”`,
        hint: "Try a district name such as Lucknow or Kanpur Nagar."
      });
    }
    return /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("p", {
      className: "muted",
      "aria-live": "polite"
    }, stations.length, " of ", all.length, " stations"), stations.map((st, i) => /*#__PURE__*/React.createElement("article", {
      key: i,
      className: "glass p-5"
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        display: 'flex',
        justifyContent: 'space-between',
        gap: 10,
        alignItems: 'flex-start',
        marginBottom: 12
      }
    }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("h3", {
      style: {
        fontSize: 16,
        fontWeight: 700
      }
    }, st.station_name), /*#__PURE__*/React.createElement("p", {
      className: "muted"
    }, st.district, " \xB7 ", st.total_firs, " FIRs \xB7", ' ', st.repeat_offenders_count, " repeat offenders")), /*#__PURE__*/React.createElement("span", {
      className: `badge badge-${st.risk_level}`
    }, st.risk_level)), /*#__PURE__*/React.createElement("div", {
      className: "metric-grid",
      style: {
        marginBottom: 12
      }
    }, Object.entries(st.crime_breakdown || {}).map(([type, count]) => /*#__PURE__*/React.createElement("div", {
      key: type,
      style: {
        padding: 8,
        borderRadius: 8,
        background: 'var(--bg2)',
        textAlign: 'center'
      }
    }, /*#__PURE__*/React.createElement("p", {
      className: "muted",
      style: {
        fontSize: 10,
        textTransform: 'capitalize'
      }
    }, label(type)), /*#__PURE__*/React.createElement("p", {
      style: {
        fontWeight: 700,
        color: 'var(--blue)',
        fontSize: 16
      }
    }, count)))), Object.keys(st.monthly_trend || {}).length > 1 && /*#__PURE__*/React.createElement(ResponsiveContainer, {
      width: "100%",
      height: 90
    }, /*#__PURE__*/React.createElement(AreaChart, {
      data: Object.entries(st.monthly_trend).map(([m, v]) => ({
        month: m,
        count: v
      }))
    }, /*#__PURE__*/React.createElement(XAxis, {
      dataKey: "month",
      stroke: "#7387b0",
      tick: {
        fontSize: 9
      }
    }), /*#__PURE__*/React.createElement(YAxis, {
      stroke: "#7387b0",
      tick: {
        fontSize: 9
      },
      width: 24,
      allowDecimals: false
    }), /*#__PURE__*/React.createElement(Tooltip, CHART_TOOLTIP), /*#__PURE__*/React.createElement(Area, {
      type: "monotone",
      dataKey: "count",
      stroke: "#5b9bff",
      fill: "rgba(91,155,255,.15)",
      strokeWidth: 1.5,
      isAnimationActive: false
    }))), st.hotspot_areas?.length > 0 && /*#__PURE__*/React.createElement("p", {
      className: "muted",
      style: {
        marginTop: 8
      }
    }, "Hotspots: ", /*#__PURE__*/React.createElement("span", {
      style: {
        color: 'var(--amber)'
      }
    }, st.hotspot_areas.join(', '))), /*#__PURE__*/React.createElement("p", {
      className: "muted",
      style: {
        marginTop: 6,
        padding: 8,
        borderRadius: 6,
        background: 'var(--bg2)'
      }
    }, st.assessment))));
  }));
}

// ── Networks ───────────────────────────────────────────────────────────────
function NetworkView() {
  const state = useApi('/networks');
  return /*#__PURE__*/React.createElement("div", {
    className: "stack fade-in"
  }, /*#__PURE__*/React.createElement(Async, {
    state: state,
    isEmpty: d => !d.length,
    empty: /*#__PURE__*/React.createElement(EmptyState, {
      title: "No organised networks detected",
      hint: "A network needs at least two FIRs linked by a shared offender identity or a distinctive shared modus operandi."
    })
  }, networks => /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("h2", {
    style: {
      fontSize: 19,
      fontWeight: 700
    }
  }, "Crime Network Intelligence"), /*#__PURE__*/React.createElement("p", {
    className: "muted"
  }, "Cross-FIR correlation identified ", networks.length, " clusters. Clusters are grown from the strongest links first and capped, so a common offence pattern cannot chain unrelated cases into one false network.")), networks.map((net, i) => {
    const c = COLORS[i % COLORS.length];
    const members = net.key_members || [];
    const firs = net.fir_numbers || [];
    const shown = firs.slice(0, 10);
    const extra = firs.length - shown.length;
    const cx = 300,
      cy = 112,
      orbX = 132,
      orbY = 84;
    return /*#__PURE__*/React.createElement("article", {
      key: i,
      className: "glass p-5 glow",
      style: {
        borderColor: c + '45'
      }
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        display: 'flex',
        justifyContent: 'space-between',
        gap: 10,
        alignItems: 'flex-start',
        flexWrap: 'wrap'
      }
    }, /*#__PURE__*/React.createElement("h3", {
      style: {
        fontSize: 17,
        fontWeight: 700,
        color: c
      }
    }, net.name), /*#__PURE__*/React.createElement("span", {
      style: {
        display: 'flex',
        gap: 8,
        alignItems: 'center'
      }
    }, /*#__PURE__*/React.createElement("span", {
      className: `badge badge-${net.risk_level || 'medium'}`
    }, net.risk_level), /*#__PURE__*/React.createElement("span", {
      className: "chip",
      style: {
        background: c + '22',
        color: c,
        fontWeight: 700
      }
    }, net.fir_count, " FIRs"))), /*#__PURE__*/React.createElement("div", {
      style: {
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit,minmax(200px,1fr))',
        gap: 14,
        marginTop: 14
      }
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        padding: 14,
        borderRadius: 10,
        background: 'var(--bg2)'
      }
    }, /*#__PURE__*/React.createElement("p", {
      className: "muted",
      style: {
        fontSize: 11,
        marginBottom: 6
      }
    }, "Linked FIRs"), /*#__PURE__*/React.createElement("div", {
      style: {
        display: 'flex',
        flexWrap: 'wrap',
        gap: 4
      }
    }, firs.map((f, j) => /*#__PURE__*/React.createElement("span", {
      key: j,
      className: "chip",
      style: {
        background: c + '1f',
        color: c
      }
    }, f)))), /*#__PURE__*/React.createElement("div", {
      style: {
        padding: 14,
        borderRadius: 10,
        background: 'var(--bg2)'
      }
    }, /*#__PURE__*/React.createElement("p", {
      className: "muted",
      style: {
        fontSize: 11,
        marginBottom: 6
      }
    }, "Districts & offences"), /*#__PURE__*/React.createElement("p", {
      style: {
        fontSize: 13
      }
    }, (net.districts || []).join(', ')), /*#__PURE__*/React.createElement("div", {
      style: {
        display: 'flex',
        flexWrap: 'wrap',
        gap: 4,
        marginTop: 6
      }
    }, (net.crime_types || []).map((ct, j) => /*#__PURE__*/React.createElement("span", {
      key: j,
      className: "chip",
      style: {
        background: 'var(--card2)',
        color: 'var(--text2)'
      }
    }, label(ct)))), /*#__PURE__*/React.createElement("p", {
      className: "muted",
      style: {
        fontSize: 11,
        marginTop: 8
      }
    }, "Linked by: ", (net.link_basis || ['correlation']).join(', '))), /*#__PURE__*/React.createElement("div", {
      style: {
        padding: 14,
        borderRadius: 10,
        background: 'var(--bg2)'
      }
    }, /*#__PURE__*/React.createElement("p", {
      className: "muted",
      style: {
        fontSize: 11,
        marginBottom: 6
      }
    }, "Active ", net.active_period?.start, " \u2192 ", net.active_period?.end), members.length > 0 ? /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("p", {
      className: "muted",
      style: {
        fontSize: 11,
        marginBottom: 4
      }
    }, "Key members"), members.slice(0, 5).map((m, j) => /*#__PURE__*/React.createElement("p", {
      key: j,
      style: {
        fontSize: 13,
        color: 'var(--red)'
      }
    }, m))) : /*#__PURE__*/React.createElement("p", {
      className: "muted",
      style: {
        fontSize: 12
      }
    }, "No accused named \u2014 linked on MO."))), net.intelligence_brief && /*#__PURE__*/React.createElement("p", {
      className: "muted",
      style: {
        marginTop: 12,
        padding: 12,
        borderRadius: 8,
        background: 'var(--bg2)',
        borderLeft: `3px solid ${c}`
      }
    }, net.intelligence_brief), /*#__PURE__*/React.createElement("figure", {
      style: {
        marginTop: 16,
        borderRadius: 10,
        background: 'var(--bg)',
        padding: 16
      }
    }, /*#__PURE__*/React.createElement("figcaption", {
      className: "sr-only"
    }, "Network graph: ", net.name, " with ", firs.length, " linked FIRs."), /*#__PURE__*/React.createElement("svg", {
      width: "100%",
      height: "240",
      viewBox: "0 0 600 240",
      role: "img",
      "aria-label": `${net.name}: ${firs.length} linked FIRs`
    }, /*#__PURE__*/React.createElement("defs", null, /*#__PURE__*/React.createElement("filter", {
      id: `glow-${i}`
    }, /*#__PURE__*/React.createElement("feGaussianBlur", {
      stdDeviation: "3",
      result: "blur"
    }), /*#__PURE__*/React.createElement("feMerge", null, /*#__PURE__*/React.createElement("feMergeNode", {
      in: "blur"
    }), /*#__PURE__*/React.createElement("feMergeNode", {
      in: "SourceGraphic"
    })))), shown.map((fir, j) => {
      const angle = j / shown.length * Math.PI * 2 - Math.PI / 2;
      const x = cx + Math.cos(angle) * orbX;
      const y = cy + Math.sin(angle) * orbY;
      return /*#__PURE__*/React.createElement("g", {
        key: j
      }, /*#__PURE__*/React.createElement("line", {
        x1: cx,
        y1: cy,
        x2: x,
        y2: y,
        stroke: c,
        strokeOpacity: .35,
        strokeWidth: "1.5",
        strokeDasharray: "5 3"
      }), /*#__PURE__*/React.createElement("circle", {
        cx: x,
        cy: y,
        r: "23",
        style: {
          fill: '#151d35'
        },
        stroke: c,
        strokeOpacity: .7,
        strokeWidth: "1.5"
      }), /*#__PURE__*/React.createElement("text", {
        x: x,
        y: y + 4,
        textAnchor: "middle",
        style: {
          fill: '#edf2ff'
        },
        fontSize: "9",
        fontWeight: "600"
      }, fir.split('/').slice(-2).join('/')));
    }), /*#__PURE__*/React.createElement("circle", {
      cx: cx,
      cy: cy,
      r: "44",
      fill: c,
      fillOpacity: .16,
      stroke: c,
      strokeWidth: "2.5",
      filter: `url(#glow-${i})`
    }), /*#__PURE__*/React.createElement("text", {
      x: cx,
      y: cy - 8,
      textAnchor: "middle",
      style: {
        fill: c
      },
      fontSize: "10",
      fontWeight: "bold"
    }, net.name.length > 22 ? net.name.slice(0, 20) + '…' : net.name), /*#__PURE__*/React.createElement("text", {
      x: cx,
      y: cy + 7,
      textAnchor: "middle",
      style: {
        fill: '#9dafd4'
      },
      fontSize: "9"
    }, net.fir_count, " FIRs"), extra > 0 && /*#__PURE__*/React.createElement("text", {
      x: cx,
      y: cy + 20,
      textAnchor: "middle",
      style: {
        fill: '#7387b0'
      },
      fontSize: "8"
    }, "+", extra, " more"))));
  }))));
}

// ── Bob chat ───────────────────────────────────────────────────────────────
const GREETING = {
  role: 'assistant',
  content: 'I am the FIR Intelligence assistant. I answer from the analysed corpus only — ' + 'crime patterns, repeat offenders, criminal networks, station caseloads and ' + 'individual FIRs.\n\nAsk about a specific FIR number, a named accused, a district, ' + 'or pick a suggestion below.'
};
function BobChat() {
  const [messages, setMessages] = useState([GREETING]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const endRef = useRef(null);
  const inputRef = useRef(null);
  const suggestions = ['What are the top crime patterns?', 'Who are the repeat offenders?', 'Which districts have the highest caseload?', 'Show the organised crime networks', 'Which FIRs are most severe?', 'Summarise station activity'];
  useEffect(() => {
    endRef.current?.scrollIntoView({
      behavior: 'smooth',
      block: 'end'
    });
  }, [messages, busy]);
  const send = useCallback(async text => {
    const message = (text ?? input).trim();
    if (!message || busy) return;
    setMessages(prev => [...prev, {
      role: 'user',
      content: message
    }]);
    setInput('');
    setBusy(true);
    try {
      const res = await fetch(API + '/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          message
        })
      });
      if (!res.ok) throw new Error(`Server returned ${res.status}`);
      const data = await res.json();
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: data.response || 'No answer returned.',
        firs: data.firs_referenced || []
      }]);
    } catch (err) {
      setMessages(prev => [...prev, {
        role: 'assistant',
        error: true,
        content: `Could not reach the intelligence service: ${err.message}`
      }]);
    } finally {
      setBusy(false);
      inputRef.current?.focus();
    }
  }, [input, busy]);
  return /*#__PURE__*/React.createElement("div", {
    className: "fade-in",
    style: {
      display: 'flex',
      flexDirection: 'column',
      height: 'calc(100vh - 230px)',
      minHeight: 420
    }
  }, /*#__PURE__*/React.createElement("div", {
    role: "log",
    "aria-live": "polite",
    "aria-label": "Conversation",
    style: {
      flex: 1,
      overflowY: 'auto',
      display: 'flex',
      flexDirection: 'column',
      gap: 10,
      marginBottom: 14,
      paddingRight: 6
    }
  }, messages.map((m, i) => /*#__PURE__*/React.createElement("div", {
    key: i,
    style: {
      display: 'flex',
      justifyContent: m.role === 'user' ? 'flex-end' : 'flex-start'
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "chat-bubble",
    style: {
      maxWidth: '72%',
      padding: '12px 16px',
      borderRadius: m.role === 'user' ? '16px 16px 4px 16px' : '16px 16px 16px 4px',
      background: m.role === 'user' ? 'var(--blue2)' : 'var(--card)',
      border: m.error ? '1px solid rgba(251,90,117,.5)' : '1px solid var(--border)'
    }
  }, /*#__PURE__*/React.createElement("p", {
    className: "sr-only"
  }, m.role === 'user' ? 'You said' : 'Assistant said'), /*#__PURE__*/React.createElement("pre", {
    style: {
      fontSize: 13,
      whiteSpace: 'pre-wrap',
      wordBreak: 'break-word',
      fontFamily: 'inherit',
      margin: 0,
      lineHeight: 1.55,
      color: m.error ? 'var(--red)' : 'inherit'
    }
  }, m.content)))), busy && /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: 8,
      alignItems: 'center',
      padding: '10px 4px'
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "spinner",
    style: {
      width: 18,
      height: 18,
      borderWidth: 2
    }
  }), /*#__PURE__*/React.createElement("span", {
    className: "muted"
  }, "Analysing the corpus\u2026")), /*#__PURE__*/React.createElement("div", {
    ref: endRef
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexWrap: 'wrap',
      gap: 6,
      marginBottom: 10
    }
  }, suggestions.map((s, i) => /*#__PURE__*/React.createElement("button", {
    key: i,
    onClick: () => send(s),
    disabled: busy,
    className: "btn btn-ghost",
    style: {
      fontSize: 12,
      padding: '6px 12px',
      borderRadius: 20
    }
  }, s))), /*#__PURE__*/React.createElement("form", {
    style: {
      display: 'flex',
      gap: 10
    },
    onSubmit: e => {
      e.preventDefault();
      send();
    }
  }, /*#__PURE__*/React.createElement("label", {
    className: "sr-only",
    htmlFor: "chat-input"
  }, "Ask about the FIR corpus"), /*#__PURE__*/React.createElement("input", {
    id: "chat-input",
    ref: inputRef,
    type: "text",
    value: input,
    disabled: busy,
    onChange: e => setInput(e.target.value),
    style: {
      flex: 1
    },
    placeholder: "Ask about offenders, networks, districts or an FIR number\u2026"
  }), /*#__PURE__*/React.createElement("button", {
    type: "submit",
    className: "btn btn-primary",
    disabled: busy || !input.trim(),
    style: {
      paddingLeft: 24,
      paddingRight: 24
    }
  }, "Send")));
}

// ── Report ─────────────────────────────────────────────────────────────────
function ReportView() {
  const state = useApi('/report');
  const download = useCallback(report => {
    const blob = new Blob([report], {
      type: 'text/plain;charset=utf-8'
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `FIR-Intelligence-Report-${new Date().toISOString().slice(0, 10)}.txt`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    // The previous build never released the object URL, leaking the whole
    // report into memory on every download.
    URL.revokeObjectURL(url);
  }, []);
  return /*#__PURE__*/React.createElement(Async, {
    state: state
  }, data => {
    const meta = data.metadata || {};
    return /*#__PURE__*/React.createElement("div", {
      className: "stack fade-in"
    }, /*#__PURE__*/React.createElement("div", {
      className: "toolbar",
      style: {
        justifyContent: 'space-between'
      }
    }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("h2", {
      style: {
        fontSize: 19,
        fontWeight: 700
      }
    }, "Intelligence Report"), /*#__PURE__*/React.createElement("p", {
      className: "muted"
    }, "Source: ", data.source, " \xB7 generated ", new Date(data.generated_at).toLocaleString())), /*#__PURE__*/React.createElement("div", {
      style: {
        display: 'flex',
        gap: 8
      },
      className: "no-print"
    }, /*#__PURE__*/React.createElement("button", {
      className: "btn btn-ghost",
      onClick: () => window.print()
    }, "Print"), /*#__PURE__*/React.createElement("button", {
      className: "btn btn-primary",
      onClick: () => download(data.report)
    }, "Download .txt"))), /*#__PURE__*/React.createElement("div", {
      className: "metric-grid"
    }, [['FIRs Analysed', meta.total_firs, 'var(--blue)'], ['Repeat Offenders', meta.repeat_offender_count, 'var(--red)'], ['Districts', (meta.districts || []).length, 'var(--green)'], ['Networks', (meta.patterns || []).length, 'var(--amber)']].map(([k, v, c]) => /*#__PURE__*/React.createElement("div", {
      key: k,
      className: "glass",
      style: {
        padding: 12,
        textAlign: 'center'
      }
    }, /*#__PURE__*/React.createElement("p", {
      className: "muted",
      style: {
        fontSize: 11
      }
    }, k), /*#__PURE__*/React.createElement("p", {
      style: {
        fontWeight: 700,
        fontSize: 20,
        color: c
      }
    }, v)))), /*#__PURE__*/React.createElement("div", {
      className: "glass p-5"
    }, /*#__PURE__*/React.createElement("pre", {
      style: {
        whiteSpace: 'pre-wrap',
        wordBreak: 'break-word',
        fontSize: 13,
        lineHeight: 1.7,
        fontFamily: 'inherit',
        color: 'var(--text2)'
      }
    }, data.report)));
  });
}

// ── Upload ─────────────────────────────────────────────────────────────────
function UploadPanel({
  onIngested
}) {
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const submit = async e => {
    e.preventDefault();
    if (!file) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const body = new FormData();
      body.append('file', file);
      const res = await fetch(API + '/upload-firs', {
        method: 'POST',
        body
      });
      const data = await res.json();
      if (!res.ok) {
        const detail = data.detail;
        throw new Error(typeof detail === 'string' ? detail : detail?.message ? `${detail.message}: ${(detail.errors || []).map(x => `#${x.index} ${x.error}`).join('; ')}` : `Upload failed (${res.status})`);
      }
      setResult(data);
      onIngested?.();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };
  return /*#__PURE__*/React.createElement("div", {
    className: "stack fade-in"
  }, /*#__PURE__*/React.createElement(SectionCard, {
    title: "Ingest FIR records",
    subtitle: "Upload a JSON array of FIR records. Each needs at least fir_number and raw_text; everything else is inferred by the NLP pipeline."
  }, /*#__PURE__*/React.createElement("form", {
    onSubmit: submit,
    className: "toolbar"
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      flex: '1 1 280px'
    }
  }, /*#__PURE__*/React.createElement("label", {
    htmlFor: "upload-file"
  }, "FIR batch (.json)"), /*#__PURE__*/React.createElement("input", {
    id: "upload-file",
    type: "file",
    accept: "application/json,.json",
    style: {
      width: '100%'
    },
    onChange: e => {
      setFile(e.target.files?.[0] || null);
      setResult(null);
      setError(null);
    }
  })), /*#__PURE__*/React.createElement("button", {
    type: "submit",
    className: "btn btn-primary",
    disabled: !file || busy
  }, busy ? 'Analysing…' : 'Upload & analyse')), /*#__PURE__*/React.createElement("details", {
    style: {
      marginTop: 14
    }
  }, /*#__PURE__*/React.createElement("summary", {
    style: {
      cursor: 'pointer',
      color: 'var(--blue)',
      fontSize: 13
    }
  }, "Expected format"), /*#__PURE__*/React.createElement("pre", {
    style: {
      marginTop: 8,
      padding: 12,
      borderRadius: 8,
      background: 'var(--bg2)',
      fontSize: 12,
      overflowX: 'auto',
      color: 'var(--text2)'
    }
  }, `[
  {
    "fir_number": "FIR/2025/LU/001",
    "date_filed": "2025-03-04",
    "police_station": "Hazratganj PS",
    "district": "Lucknow",
    "raw_text": "Complainant states that two bike-borne persons snatched ..."
  }
]`))), error && /*#__PURE__*/React.createElement(ErrorState, {
    error: error
  }), result && /*#__PURE__*/React.createElement(SectionCard, {
    title: "Ingestion complete"
  }, /*#__PURE__*/React.createElement("div", {
    className: "metric-grid"
  }, [['Accepted', result.accepted, 'var(--green)'], ['Rejected', result.rejected, 'var(--red)'], ['Corpus size', result.total_firs, 'var(--blue)'], ['Repeat offenders', result.repeat_offenders_found, 'var(--purple)'], ['Networks', result.networks_found, 'var(--amber)']].map(([k, v, c]) => /*#__PURE__*/React.createElement("div", {
    key: k,
    style: {
      padding: 10,
      borderRadius: 8,
      background: 'var(--bg2)',
      textAlign: 'center'
    }
  }, /*#__PURE__*/React.createElement("p", {
    className: "muted",
    style: {
      fontSize: 11
    }
  }, k), /*#__PURE__*/React.createElement("p", {
    style: {
      fontWeight: 700,
      fontSize: 19,
      color: c
    }
  }, v)))), (result.errors || []).length > 0 && /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: 12
    }
  }, /*#__PURE__*/React.createElement("p", {
    className: "muted",
    style: {
      marginBottom: 6
    }
  }, "Rejected records:"), result.errors.map((e, i) => /*#__PURE__*/React.createElement("p", {
    key: i,
    className: "muted",
    style: {
      fontSize: 12
    }
  }, "index ", e.index, ": ", e.error)))));
}

// ── App shell ──────────────────────────────────────────────────────────────
const TABS = [{
  id: 'dashboard',
  label: 'Dashboard',
  icon: '📊'
}, {
  id: 'firs',
  label: 'FIR Records',
  icon: '📋'
}, {
  id: 'offenders',
  label: 'Repeat Offenders',
  icon: '🔁'
}, {
  id: 'trends',
  label: 'Crime Trends',
  icon: '📈'
}, {
  id: 'stations',
  label: 'Station Analysis',
  icon: '🏛'
}, {
  id: 'networks',
  label: 'Crime Networks',
  icon: '🕸'
}, {
  id: 'chat',
  label: 'Ask Bob',
  icon: '🤖'
}, {
  id: 'report',
  label: 'Intel Report',
  icon: '📄'
}, {
  id: 'upload',
  label: 'Ingest FIRs',
  icon: '⬆'
}];
function App() {
  // Deep-linkable tabs: the old build reset to the dashboard on every reload
  // and offered no way to share a view.
  const [tab, setTab] = useState(() => TABS.some(t => t.id === window.location.hash.slice(1)) ? window.location.hash.slice(1) : 'dashboard');
  const dashboard = useApi('/dashboard');
  const health = useApi('/health');
  const tabRefs = useRef({});
  useEffect(() => {
    const onHash = () => {
      const id = window.location.hash.slice(1);
      if (TABS.some(t => t.id === id)) setTab(id);
    };
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);
  const select = id => {
    setTab(id);
    window.location.hash = id;
  };

  // Arrow-key navigation, as expected of an ARIA tablist.
  const onTabKey = e => {
    const i = TABS.findIndex(t => t.id === tab);
    let next = null;
    if (e.key === 'ArrowRight') next = TABS[(i + 1) % TABS.length];else if (e.key === 'ArrowLeft') next = TABS[(i - 1 + TABS.length) % TABS.length];else if (e.key === 'Home') next = TABS[0];else if (e.key === 'End') next = TABS[TABS.length - 1];
    if (next) {
      e.preventDefault();
      select(next.id);
      tabRefs.current[next.id]?.focus();
    }
  };
  const status = health.data;
  const online = !health.error && status?.status === 'ok';
  return /*#__PURE__*/React.createElement("div", {
    style: {
      minHeight: '100vh',
      display: 'flex',
      flexDirection: 'column'
    }
  }, /*#__PURE__*/React.createElement("header", {
    style: {
      background: 'var(--bg2)',
      borderBottom: '1px solid var(--border)',
      position: 'sticky',
      top: 0,
      zIndex: 50
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "shell",
    style: {
      padding: '12px 20px',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      gap: 12
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 14,
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement("div", {
    "aria-hidden": "true",
    style: {
      width: 42,
      height: 42,
      borderRadius: 10,
      flexShrink: 0,
      background: 'linear-gradient(135deg,#2563eb,#5b9bff)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      fontSize: 17,
      fontWeight: 800,
      color: '#fff'
    }
  }, "FI"), /*#__PURE__*/React.createElement("div", {
    style: {
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement("h1", {
    style: {
      fontSize: 17,
      fontWeight: 700
    }
  }, "FIR Intelligence System"), /*#__PURE__*/React.createElement("p", {
    className: "muted header-sub",
    style: {
      fontSize: 11
    }
  }, "NLP entity extraction \xB7 cross-FIR correlation \xB7 repeat offender detection"))), /*#__PURE__*/React.createElement("div", {
    className: "header-meta",
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 14,
      flexShrink: 0
    }
  }, /*#__PURE__*/React.createElement("span", {
    title: status ? `Storage: ${status.storage} · Model: ${status.language_model}` : '',
    style: {
      padding: '4px 12px',
      borderRadius: 20,
      fontSize: 11,
      fontWeight: 700,
      background: online ? 'rgba(31,192,143,.14)' : 'rgba(251,90,117,.14)',
      color: online ? 'var(--green)' : 'var(--red)',
      border: `1px solid ${online ? 'rgba(31,192,143,.3)' : 'rgba(251,90,117,.3)'}`
    }
  }, "\u25CF ", health.loading ? 'CONNECTING' : online ? 'LIVE' : 'OFFLINE'), status && /*#__PURE__*/React.createElement("span", {
    className: "muted header-stats",
    style: {
      fontSize: 11
    }
  }, status.firs_analyzed, " FIRs \xB7 ", status.language_model)))), /*#__PURE__*/React.createElement("nav", {
    className: "shell",
    style: {
      padding: '12px 20px'
    },
    "aria-label": "Sections"
  }, /*#__PURE__*/React.createElement("div", {
    role: "tablist",
    "aria-label": "Dashboard sections",
    onKeyDown: onTabKey,
    style: {
      display: 'flex',
      gap: 6,
      overflowX: 'auto',
      paddingBottom: 4
    }
  }, TABS.map(t => /*#__PURE__*/React.createElement("button", {
    key: t.id,
    role: "tab",
    id: `tab-${t.id}`,
    className: "tab",
    ref: el => {
      tabRefs.current[t.id] = el;
    },
    "aria-selected": tab === t.id,
    "aria-controls": `panel-${t.id}`,
    tabIndex: tab === t.id ? 0 : -1,
    onClick: () => select(t.id)
  }, /*#__PURE__*/React.createElement("span", {
    "aria-hidden": "true",
    style: {
      marginRight: 6
    }
  }, t.icon), t.label)))), /*#__PURE__*/React.createElement("main", {
    id: "main",
    className: "shell",
    style: {
      padding: '0 20px 40px',
      flex: 1
    }
  }, /*#__PURE__*/React.createElement("div", {
    role: "tabpanel",
    id: `panel-${tab}`,
    "aria-labelledby": `tab-${tab}`,
    tabIndex: -1
  }, tab === 'dashboard' && /*#__PURE__*/React.createElement(Dashboard, {
    state: dashboard
  }), tab === 'firs' && /*#__PURE__*/React.createElement(FIRList, null), tab === 'offenders' && /*#__PURE__*/React.createElement(RepeatOffenders, {
    threshold: dashboard.data?.name_match_threshold
  }), tab === 'trends' && /*#__PURE__*/React.createElement(CrimeTrends, {
    state: dashboard
  }), tab === 'stations' && /*#__PURE__*/React.createElement(StationSummary, null), tab === 'networks' && /*#__PURE__*/React.createElement(NetworkView, null), tab === 'chat' && /*#__PURE__*/React.createElement(BobChat, null), tab === 'report' && /*#__PURE__*/React.createElement(ReportView, null), tab === 'upload' && /*#__PURE__*/React.createElement(UploadPanel, {
    onIngested: () => {
      dashboard.reload();
      health.reload();
    }
  }))), /*#__PURE__*/React.createElement("footer", {
    style: {
      borderTop: '1px solid var(--border)',
      padding: '16px 20px',
      textAlign: 'center',
      fontSize: 11,
      color: 'var(--text3)'
    }
  }, "FIR Intelligence & Crime Pattern Detector \xB7 FastAPI + React + Recharts \xB7 findings are automated correlations and require verification by the investigating officer"));
}
ReactDOM.createRoot(document.getElementById('root')).render(/*#__PURE__*/React.createElement(App, null));
