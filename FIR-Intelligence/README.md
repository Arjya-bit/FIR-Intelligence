# FIR Intelligence & Crime Pattern Detector

**IBM Bob AI Hackathon · NFSU | Track 4: AI & Predictive | Problem Statement 10**

> An NLP intelligence platform that ingests FIR text, classifies crime types, extracts named
> entities, resolves offender identities across jurisdictions, detects organised crime
> networks, and produces station-level intelligence reports.

---

## Team

| Role | Name | Email |
|------|------|-------|
| Lead | Arjya Ghosh | arjya.btmtcs12230@nfsu.ac.in |

## Problem Statement

CCTNS holds 3+ crore digitised FIRs with no NLP layer on top. Serial offenders evade
detection because inter-district FIR connections are never surfaced, and pattern analysis
is entirely manual — officers have no automated way to detect repeat offenders,
cross-reference modus operandi across jurisdictions, or identify organised crime networks
spanning multiple districts.

## Quick start

No database, no API key, no build step:

```bash
pip install -r requirements.txt
python main.py
```

Open <http://localhost:8000>. The service seeds an NCRB-shaped corpus of 100 FIRs, runs the
analysis pipeline, and serves the dashboard. Interactive API docs are at `/docs`.

Optional configuration lives in `.env` (`cp .env.example .env`) — watsonx.ai credentials,
MongoDB, seed size, matching thresholds. **Everything is optional**: with nothing set the
service runs on an in-memory store and answers from the rule-based engine.

## What it does

1. **Ingests** FIR records — the seeded corpus, or your own JSON batch via the *Ingest FIRs*
   tab / `POST /api/upload-firs`.
2. **Classifies** each FIR into one of 15 crime types (watsonx.ai Granite 3, with a keyword
   classifier fallback).
3. **Extracts** accused, victims, locations, weapons, vehicles, IPC sections, phone numbers
   and modus operandi from the narrative text.
4. **Resolves offender identities** across FIRs using union-find over names and aliases, so
   links are transitive.
5. **Detects organised networks** by clustering a weighted co-offending graph.
6. **Reports** station-level trends, hotspots, risk assessments and recommended actions.

### How identity resolution works

Name matching in Indian FIRs is dangerous in two specific ways, and both are handled
explicitly:

- **Nicknames are not identifiers.** "Chhotu", "Guddu" and "Bablu" are shared by thousands
  of unrelated people. An alias can *corroborate* a match but never create one — otherwise a
  single shared nickname chains the whole corpus into one bogus offender.
- **A fuzzy name match alone is not evidence.** An approximate match ("Sunil Yadav" vs
  "Sunny Yadav") must be backed by a shared father's name, alias, police station or
  district before two identities are merged. In a policing context a false link is worse
  than a missed one.

Networks are built by merging the strongest links first with a size cap, not by plain
connected components — single-linkage over a common offence pattern chains unrelated cases
into one meaningless cluster.

Every finding is an automated correlation and is labelled as requiring verification by the
investigating officer.

## Architecture

```
main.py              FastAPI app — routes, lifespan, seeding
database.py          Storage: MongoDB when reachable, in-memory otherwise
nlp_engine.py        Pipeline: classify -> extract -> correlate
entity_extractor.py  Regex NER tuned for Indian FIR conventions (S/o, R/o, IPC)
pattern_detector.py  Identity resolution, station rollups, network clustering
intel_qa.py          Deterministic Q&A and report writing over the analysis
bob_client.py        watsonx.ai client + grounded fallbacks
ncrb_seed.py         NCRB-distribution FIR corpus generator
models.py            Pydantic schemas
static/              Zero-build dashboard (app.jsx source, app.js compiled)
src/mcp_server/      MCP server for IBM Bob CLI
src/frontend/        Optional Vite + Tailwind React client
tests/               pytest suite
```

## API

| Endpoint | Purpose |
|----------|---------|
| `GET /api/health` | Status, storage backend, model in use, corpus size |
| `GET /api/filters` | Filter options for the UI |
| `GET /api/dashboard` | Headline counts, breakdowns, trends, networks |
| `GET /api/firs` | Paginated FIR list — `q`, `crime_type`, `district`, `station`, `severity`, `limit`, `offset` |
| `GET /api/firs/{fir_number}` | Full record plus cross-FIR links |
| `GET /api/repeat-offenders` | Flagged offenders — `risk_level`, `min_incidents` |
| `GET /api/stations` | Station rollups with risk assessments |
| `GET /api/networks` | Detected organised networks |
| `GET /api/trends` | Month-by-crime-type series |
| `GET /api/report` | Intelligence report + metadata |
| `POST /api/chat` | Ask a question about the corpus |
| `POST /api/upload-firs` | Ingest a JSON array of FIRs and re-analyse |

`GET /api/firs` returns `{items, total, limit, offset, has_more}`.

## Configuration

| Variable | Default | Effect |
|----------|---------|--------|
| `WATSONX_API_KEY` / `WATSONX_PROJECT_ID` | unset | Enables watsonx.ai; without them the rule-based engine is used |
| `FIR_STORAGE` | `auto` | `auto` \| `memory` \| `mongodb` (fail if unreachable) |
| `MONGO_URL` | `mongodb://localhost:27017` | Used when Mongo is reachable |
| `FIR_SEED_SIZE` | `100` | FIRs generated on first boot |
| `FIR_NAME_MATCH_THRESHOLD` | `82` | Token-similarity score for candidate name matches |
| `FIR_HOST` / `FIR_PORT` | `127.0.0.1` / `8000` | Bind address (set host to `0.0.0.0` to expose) |
| `FIR_CORS_ORIGINS` | unset | Comma-separated origins; enables credentialed CORS |

See `.env.example` for the full list.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

110 tests cover identity resolution, entity extraction, the storage backend, the
deterministic answerer, and every HTTP endpoint including error paths.

## IBM Bob CLI (MCP)

```bash
bob mcp add fir-intelligence -- python src/mcp_server/server.py
bob chat
```

Eight tools: `analyze_firs`, `get_repeat_offenders`, `get_station_summary`,
`get_crime_networks`, `search_firs`, `get_fir`, `ask_intelligence`,
`generate_intelligence_report`. The server imports the same modules the API uses, so Bob and
the dashboard always describe the same corpus.

## The dashboard

`static/` ships precompiled and with its libraries vendored, so `python main.py` serves a
working dashboard with no npm install and no CDN access — which matters on an isolated
police network. After editing `static/app.jsx`:

```bash
./scripts/build-ui.sh
```

`src/frontend/` is an optional Vite + Tailwind client against the same API
(`npm install && npm run dev`, proxying to port 8000).

## Tech stack

| Component | Technology |
|-----------|-----------|
| AI/NLP | IBM watsonx.ai (Granite 3 8B Instruct), rule-based fallback |
| Agent interface | IBM Bob CLI via MCP |
| Backend | Python 3.11+, FastAPI, Pydantic, RapidFuzz |
| Storage | MongoDB (Motor) — optional, in-memory fallback |
| Dashboard | React 18 + Recharts, precompiled, no build step to run |

## Known limitations

- Offender matching is name-based; no biometric or photograph matching. Two different people
  with the same recorded full name will merge, which is inherent to the available data.
- Entity extraction is tuned to conventional FIR phrasing (`Accused identified as`,
  `Arrested: (1) …`, `S/o`, `R/o`). Free-form narratives extract less.
- Batch analysis, not real-time CCTNS streaming.
- Geographic mapping uses district centroids with jitter, not surveyed coordinates.
- The seeded corpus is generated, not real FIR data.
- No authentication — the API is open. Do not expose it beyond localhost without putting an
  authenticating proxy in front of it.
