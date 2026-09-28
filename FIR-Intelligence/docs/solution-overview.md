# Solution Overview

## Core Mechanism

FIR Intelligence is a **hybrid NLP pipeline** that combines IBM watsonx.ai's Granite language model with deterministic regex-based extraction to robustly process Indian police FIR text. The system works in four stages:

### Stage 1: FIR Ingestion & Classification
Each FIR text is sent to IBM watsonx.ai Granite 3 8B Instruct for crime type classification. The LLM classifies into one of 15 crime categories (robbery, burglary, fraud, drug offense, kidnapping, extortion, cybercrime, murder, assault, arson, etc.). A rule-based fallback using IPC section numbers and crime-specific keywords ensures classification works even without API access.

### Stage 2: Entity Extraction
A hybrid NER pipeline extracts:
- **Accused persons** — Name, aliases, age, father's name, address, identifying marks
- **Victims/Complainants** — Name, age, gender, occupation, address
- **Locations** — Crime scene, police station, district, with geocoordinates
- **Modus Operandi** — Method, weapons, time of day, approach pattern
- **IPC Sections** — All applicable legal sections
- **Stolen property** — Items and monetary values
- **Vehicles and phone numbers** — For investigation cross-referencing

### Stage 3: Cross-FIR Pattern Detection
This is where the real intelligence happens:

1. **Identity Resolution** — Union-find over recorded names and aliases makes offender links transitive. RapidFuzz `token_sort_ratio` (default threshold 82%) proposes candidate matches, but an approximate match is only accepted when corroborated by a shared father's name, alias, police station or district. Aliases never create an identity on their own: nicknames such as "Chhotu" or "Guddu" are shared by thousands of unrelated people, and treating one as an identifier chains the entire corpus into a single false offender.
2. **Alias Resolution** — "Bablu alias Bhura" in one FIR is matched with "Bablu" in another, then with "Bhura" in a third.
3. **MO Fingerprinting** — Crimes sharing the same approach method (e.g., "gas cutter on shutter + white Eeco van + CCTV removal") are linked as potential gang activity.
4. **Network Detection** — Named entities like gang names ("Munna Bhai"), locations (Jamtara), and shared infrastructure (same phone numbers, same money trail) are used to identify organized crime networks.

### Stage 4: Intelligence Generation
The system generates:
- **Repeat offender profiles** with risk levels (LOW → CRITICAL based on incident count and geographic spread)
- **Station-level summaries** with crime breakdown, monthly trends, and risk assessments
- **Crime network intelligence** mapping organized operations across districts
- **Downloadable reports** suitable for SHO/SP briefings

## What Makes It Different

1. **Not just classification** — Most NLP tools stop at labeling. We go from raw text → entities → cross-FIR patterns → actionable intelligence.
2. **Indian police FIR format awareness** — Our extractors understand "S/o", "R/o", "W/o", IPC section formats, Indian naming conventions, and CCTNS FIR structure.
3. **Fuzzy matching, not exact** — Real offenders use aliases, misspell names, and cross jurisdictions. Our system handles this through token-level fuzzy matching.
4. **Genuine IBM Bob integration** — Not a wrapper. The MCP server exposes 8 tools that Bob can call natively, and imports the same analysis modules the API uses, so Bob and the dashboard never disagree about the corpus.
5. **Works without API keys** — The system has a full rule-based fallback, making it runnable anywhere without cloud dependencies.

## User Experience

### For the SHO (Station House Officer)
1. Open the dashboard → see station-level crime breakdown instantly
2. Click "Repeat Offenders" → see who's been flagged across districts
3. Click any offender → see linked FIRs, risk level, MO signature, and intelligence assessment
4. Generate a report → download for briefing

### For the SP (Superintendent of Police)
1. View district-wide trends → identify crime hotspots
2. Review crime networks → see organized operations spanning the district
3. Use Bob AI Chat → ask "Which station needs the most attention?" in natural language
4. Download intelligence report → share with task force

### For the Crime Branch
1. Upload a batch of FIRs → system processes and cross-references
2. View crime networks → see inter-district organized crime
3. Track repeat offenders → prioritize high-risk targets
4. Generate coordinated operation briefs

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Hybrid NLP (LLM + regex) | LLMs are powerful but can hallucinate entity boundaries; regex is precise for structured Indian FIR patterns |
| RapidFuzz over exact matching | Real criminals use aliases and name variations |
| Rule-based fallback | System must work in air-gapped police environments without cloud access |
| MCP server for Bob | Genuine integration, not a name-drop — officers can query intelligence from CLI |
| 25 interconnected mock FIRs | Realistic dataset with deliberate cross-references to demonstrate all detection capabilities |
