# Source Code

## Structure

```
src/
├── backend/          # Python FastAPI server + NLP engine
│   ├── main.py       # FastAPI application entry point
│   ├── bob_client.py # IBM watsonx.ai / Bob integration
│   ├── nlp_engine.py # FIR processing pipeline orchestrator
│   ├── entity_extractor.py  # Named entity extraction (hybrid NLP + regex)
│   ├── pattern_detector.py  # Cross-FIR pattern detection & repeat offender matching
│   ├── models.py     # Pydantic data models
│   ├── requirements.txt
│   └── data/
│       └── mock_firs.json   # 25 realistic FIR samples across 7 UP districts
│
├── frontend/         # React dashboard
│   ├── src/
│   │   ├── App.jsx   # Main app with tab navigation
│   │   └── components/
│   │       ├── Dashboard.jsx       # Overview with charts
│   │       ├── FIRList.jsx         # FIR records with entity details
│   │       ├── RepeatOffenders.jsx # Flagged repeat offenders
│   │       ├── CrimeTrends.jsx     # Temporal trend analysis
│   │       ├── StationSummary.jsx  # Station-level analysis
│   │       ├── NetworkView.jsx     # Crime network intelligence
│   │       ├── BobChat.jsx         # Bob AI chat interface
│   │       └── ReportView.jsx      # Intelligence report
│   └── ...
│
├── mcp_server/       # MCP server for IBM Bob CLI integration
│   └── server.py     # 6 tools exposed via Model Context Protocol
│
└── .env.example      # Environment variable template
```

## Key Components

- **backend/bob_client.py** — IBM watsonx.ai integration with Granite 3 8B Instruct model and rule-based fallback
- **backend/entity_extractor.py** — Hybrid NER using regex patterns tuned for Indian FIR format (S/o, R/o, IPC sections, etc.)
- **backend/pattern_detector.py** — Cross-FIR correlation using RapidFuzz fuzzy matching + crime network detection
- **mcp_server/server.py** — MCP server providing analyze_firs, get_repeat_offenders, get_station_summary, get_crime_networks, search_firs, and generate_intelligence_report tools for Bob CLI
