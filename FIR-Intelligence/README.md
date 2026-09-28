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

Optional configuration lives in `.env` (`cp .env.example .env`). **Everything is
optional**: with nothing set, the service runs on an in-memory store and answers from the
deterministic engine.

### Enabling the AI assistant

The assistant and the intelligence report use **Z.ai (GLM)**:

```bash
cp .env.example .env
# then set:
ZAI_API_KEY=your-key-from-https://z.ai
LLM_MODEL=glm-4.6
```

Restart, and `/api/health` reports `"ai_enabled": true`. Answers then stream token by
token. The endpoint is OpenAI-compatible, so `LLM_BASE_URL` can point at any compatible
service (mainland China: `https://open.bigmodel.cn/api/paas/v4`).

Without a key nothing breaks: the assistant answers from the analysed corpus instead, and
says so. Replies are never canned — see *Grounding* below.

## The assistant

- **Floating widget** on every tab (bottom-right), plus a full **Ask Bob** tab. One
  conversation, shared between them, preserved across tab switches.
- **Streams** replies token by token over SSE, with a stop control.
- **Multi-turn** — follow-ups like "and in Agra?" resolve against the previous turn.
- **Attributed** — each reply states which engine produced it, so a computed fallback is
  never passed off as a model answer.

### Grounding

Every question is answered from the corpus twice over. The detection pipeline computes the
answer first; that computed answer, plus a digest of corpus facts, is handed to the model as
authoritative context, and the system prompt forbids inventing an FIR number, name, district
or figure. If the model is unreachable the computed answer is returned directly, labelled.

This matters for a policing tool: a hallucinated offender is worse than "not in the data".

## The intelligence report

Regenerated live on every request — the corpus changes as FIRs are ingested, so a cached
report is stale the moment someone uploads a batch. Text streams in as the model writes it.

Focus the briefing (repeat offenders, organised networks, resourcing, severity triage,
cyber & fraud, narcotics) and the analysis and recommendations re-weight accordingly. The
computed analysis is always returned alongside the prose, so you can see what the narrative
was derived from.

## Drill-down

Selecting a segment of the crime distribution chart (or its keyboard-accessible chip below)
opens a breakdown of that offence: severity spread, districts, stations, sections invoked,
modus operandi, weapons, monthly trend, the repeat offenders and networks involved, and the
highest-severity FIRs. Selecting an FIR opens it in the FIR Records tab.

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
| `GET /api/report` | Intelligence report + metadata — `focus` optional |
| `GET /api/report/stream` | The same, streamed live over SSE |
| `GET /api/crime-types/{type}` | Full breakdown of one crime type (chart drill-down) |
| `POST /api/chat` | Ask a question about the corpus |
| `POST /api/chat/stream` | The same, streamed token by token over SSE |
| `POST /api/upload-firs` | Ingest a JSON array of FIRs and re-analyse |

`GET /api/firs` returns `{items, total, limit, offset, has_more}`.

## Configuration

| Variable | Default | Effect |
|----------|---------|--------|
| `ZAI_API_KEY` | unset | Enables the Z.ai assistant and AI report generation |
| `LLM_BASE_URL` | `https://api.z.ai/api/paas/v4` | Any OpenAI-compatible endpoint |
| `LLM_MODEL` | `glm-4.6` | Model id |
| `LLM_THINKING` | `false` | GLM-4.5+ reasoning mode (slower) |
| `WATSONX_API_KEY` / `WATSONX_PROJECT_ID` | unset | Secondary provider; also used for crime classification |
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

146 tests cover identity resolution, entity extraction, the storage backend, the
deterministic answerer, the LLM client (request shape, streaming, every failure mode,
prompt grounding), the SSE endpoints, the crime drill-down, and every HTTP endpoint
including error paths.

To exercise the LLM paths without a key or outbound network access, a development stub of
an OpenAI-compatible endpoint is included:

```bash
python scripts/mock_llm_server.py &
LLM_BASE_URL=http://127.0.0.1:8899/v1 ZAI_API_KEY=dev-key python main.py
```

`MOCK_LLM_FAIL=500` makes it fail, so the fallback path can be checked too.

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
| Assistant & reports | Z.ai GLM (OpenAI-compatible, streamed), watsonx.ai secondary, deterministic fallback |
| Crime classification | IBM watsonx.ai (Granite 3 8B Instruct), keyword fallback |
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
- Model answers are constrained by grounding and a strict system prompt, but no LLM is
  guaranteed faithful. Every finding is labelled as an automated correlation requiring
  verification, and the computed analysis is always available beside the prose.
