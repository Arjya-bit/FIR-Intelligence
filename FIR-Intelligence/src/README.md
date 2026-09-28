# src/

The analysis engine and API live at the **repository root**, not here. This directory holds
the two optional clients that sit on top of them.

```
src/
├── mcp_server/
│   └── server.py     MCP (stdio JSON-RPC) server for the IBM Bob CLI
└── frontend/         Optional Vite + React + Tailwind client
    └── src/
        ├── App.jsx
        ├── utils/api.js        API client + v2 response adapters
        └── components/         Dashboard, FIRList, RepeatOffenders, CrimeTrends,
                                StationSummary, NetworkView, BobChat, ReportView
```

## mcp_server

Imports the root modules directly, so Bob and the web dashboard always report on the same
analysed corpus. Eight tools: `analyze_firs`, `get_repeat_offenders`, `get_station_summary`,
`get_crime_networks`, `search_firs`, `get_fir`, `ask_intelligence`,
`generate_intelligence_report`.

```bash
bob mcp add fir-intelligence -- python src/mcp_server/server.py
```

## frontend

A second, build-based client for the same API. The dashboard that ships by default is the
zero-build one in `static/` — this one exists for development with hot reload and Tailwind.

```bash
cd src/frontend
npm install
npm run dev          # http://localhost:5173, proxies /api to port 8000
```

`utils/api.js` adapts the v2 API to the shape these components expect: it unwraps the
paginated `/firs` envelope and flattens `entities` back to top-level fields.

> There used to be a `src/backend/` here holding a second, diverged copy of every analysis
> module. It was removed — the root modules are canonical.
