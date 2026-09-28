# FIR Intelligence & Crime Pattern Detector

**IBM Bob AI Hackathon · NFSU | Track 4: AI & Predictive | Problem Statement 10**

> A Bob-powered NLP intelligence tool that ingests FIR text samples, categorizes crime types, extracts named entities, detects repeat offenders, and generates station-level crime intelligence reports.

---

## Team

| Role | Name | Email |
|------|------|-------|
| Lead | Arjya Ghosh | arjya.btmtcs12230@nfsu.ac.in |

## Problem Statement

UP Police's CCTNS system holds **3+ crore digitized FIRs** with no NLP layer. Serial offenders like the Jamtara gang evaded detection for years because inter-district FIR connections were never surfaced. Pattern analysis is **entirely manual** — officers have no automated way to detect repeat offenders, cross-reference modus operandi across jurisdictions, or identify organized crime networks spanning multiple districts.

## Solution

A full-stack NLP intelligence platform powered by **IBM Bob AI** and **watsonx.ai Granite models** that:

1. **Ingests** batch FIR text samples (25 realistic FIRs across 7 UP districts)
2. **Classifies** each FIR by crime type using IBM watsonx.ai Granite 3
3. **Extracts** named entities — accused persons, victims, locations, weapons, vehicles, IPC sections, and modus operandi patterns
4. **Detects** repeat offenders through fuzzy name matching, alias resolution, and MO fingerprinting
5. **Identifies** organized crime networks (Jamtara cyber fraud, Bablu snatching gang, Kanpur burglary ring, Munna Bhai extortion racket, Nepal border drug supply chain)
6. **Generates** station-level crime trend summaries with risk assessments and actionable intelligence reports

## Key Features

- **Hybrid NLP Pipeline** — IBM watsonx.ai LLM + deterministic regex extraction for robust entity recognition
- **Cross-FIR Pattern Detection** — Fuzzy name matching (RapidFuzz) + MO fingerprinting identifies repeat offenders across districts
- **5 Crime Networks Detected** — Automated cross-FIR correlation surfaces organized crime operations
- **Interactive Dashboard** — React-based UI with crime charts, network graphs, offender profiles, and station analysis
- **Bob AI Chat** — Natural language querying of the entire FIR intelligence database
- **MCP Server** — 6 tools exposed for genuine IBM Bob CLI integration via Model Context Protocol
- **Intelligence Reports** — Downloadable crime trend summaries with recommended enforcement actions

## Tech Stack

| Component | Technology |
|-----------|-----------|
| AI/NLP | IBM watsonx.ai (Granite 3 8B Instruct) |
| Agent Interface | IBM Bob CLI via MCP |
| Backend | Python, FastAPI, RapidFuzz, Pydantic |
| Frontend | React 18, Vite, Tailwind CSS, Recharts |
| Data Processing | Pandas, scikit-learn, NetworkX |

## How to Run

### Prerequisites
- Python 3.11+
- Node.js 18+
- IBM Cloud account with watsonx.ai access (optional — works with rule-based fallback)

### Backend
```bash
cd src/backend
pip install -r requirements.txt
cp ../.env.example .env  # Edit with your watsonx.ai credentials (optional)
python main.py
```

### Frontend
```bash
cd src/frontend
npm install
npm run dev
```

### Bob CLI (MCP Server)
```bash
bob mcp add fir-intelligence -- python src/mcp_server/server.py
bob chat  # Then use FIR intelligence tools
```

Open http://localhost:5173 for the dashboard.

See [docs/setup-guide.md](docs/setup-guide.md) for detailed instructions.

## Demo

- **Video**: See `demo/demo-video-link.txt`
- **Live Demo**: See `demo/live-demo-url.txt`
- **Screenshots**: See `demo/screenshots/`

## Known Limitations

- Entity extraction accuracy varies with non-standard FIR formats
- Repeat offender matching is name-based (no biometric/photo matching)
- Batch-mode analysis (not real-time CCTNS streaming)
- Geographic mapping uses district centroids
- Falls back to rule-based processing without watsonx.ai credentials

## What We're Most Proud Of

1. **The 5 interconnected crime networks** — our 25 FIRs form a realistic web of cross-district criminal activity, and the system correctly identifies all 5 organized networks purely from NLP analysis
2. **The MCP server** — genuine IBM Bob integration where Bob can query FIR intelligence, not just a wrapper
3. **The repeat offender detection** — fuzzy matching + alias resolution catches offenders who use different names across districts (e.g., "Bablu alias Bhura" matched across 4 Lucknow FIRs)
