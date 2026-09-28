# Architecture

## System Architecture Diagram

```mermaid
graph TD
    subgraph "User Interfaces"
        A[Officer / Analyst] -->|Web Browser| B[React Dashboard]
        A -->|Terminal| C[IBM Bob CLI]
    end

    subgraph "Frontend - React + Recharts, precompiled"
        B --> D[Dashboard View]
        B --> E[FIR Records View]
        B --> F[Repeat Offenders View]
        B --> G[Crime Trends View]
        B --> H[Station Analysis View]
        B --> I[Network Intelligence View]
        B --> J[Bob AI Chat Interface]
        B --> K[Intelligence Report View]
        B --> K2[FIR Ingestion View]
    end

    subgraph "API Layer"
        D & E & F & G & H & I & J & K & K2 -->|REST API| L[FastAPI Server :8000]
        C -->|MCP Protocol stdio| M[MCP Server]
    end

    subgraph "NLP Engine"
        L --> N[Crime Classifier]
        L --> O[Entity Extractor]
        L --> P[Pattern Detector]
        L --> Q[Report Generator]
        M --> N & O & P & Q
    end

    subgraph "AI Backend"
        N -->|classify_crime| R[IBM watsonx.ai Granite 3 8B]
        O -->|extract_entities_llm| R
        Q -->|generate_report| R
        N -.->|fallback| S[Keyword Classifier]
        Q -.->|fallback| S2[Deterministic Report Builder - intel_qa]
        O -->|hybrid| T[Regex + Pattern Extraction]
    end

    subgraph "Pattern Detection Engine"
        P --> U[Candidate Matcher - RapidFuzz]
        U --> V[Corroboration Check - alias / father / station / district]
        V --> W[Union-Find Identity Resolution]
        W --> X[Weighted Co-offending Graph]
        X --> X2[Capped Greedy Clustering - networks]
    end

    subgraph "Data Layer"
        Y[(MongoDB)] -.->|when reachable| L
        Y2[(In-Memory Store)] -->|fallback| L
        Y3[NCRB Corpus Generator] --> Y & Y2
        Y3 --> M
        L --> Z[Analysis Cache]
    end
```

## Component Table

| Component | Technology | Responsibility |
|-----------|-----------|----------------|
| React Dashboard | React 18, Vite, Tailwind CSS, Recharts | Interactive visualization of crime intelligence |
| FastAPI Server | Python 3.11, FastAPI, Pydantic | REST API serving processed FIR data and analytics |
| MCP Server | Python, MCP Protocol (stdio) | IBM Bob CLI integration with 6 intelligence tools |
| Crime Classifier | IBM watsonx.ai Granite 3 + fallback rules | Categorizes FIRs into 15 crime types |
| Entity Extractor | Hybrid: watsonx.ai + regex patterns | Extracts accused, victims, locations, MO, IPC sections |
| Pattern Detector | RapidFuzz, custom algorithms | Cross-FIR matching, repeat offender detection, network identification |
| Report Generator | watsonx.ai Granite 3 + templates | Generates station-level summaries and intelligence reports |
| FIR Data Store | MongoDB when reachable, in-memory fallback | 100 generated NCRB-distribution FIRs across 13 UP districts |

## Data Flow

1. FIR Text Input (JSON batch)
2. Crime Classification (watsonx.ai -> crime_type)
3. Entity Extraction (accused, victims, locations, MO, IPC sections)
4. Severity Scoring (base crime score + modifiers)
5. Cross-FIR Pattern Detection (fuzzy matching, alias resolution, MO fingerprinting)
6. Output Generation (repeat offenders, station summaries, crime networks, reports)

## Security Notes

- No real PII - all FIR data is realistic but fictional (mock data)
- .env with watsonx.ai credentials is gitignored
- CORS configured for local development
- No data persisted to disk - all analysis is in-memory
