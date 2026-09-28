# Setup Guide

## Prerequisites

- **Python 3.11+** (required — the code uses `X | Y` type syntax and `str.removesuffix`)
- Node.js 18+ — only if you want to rebuild the dashboard or run the optional Vite client
- An IBM Cloud account with watsonx.ai access — optional

Nothing else. No database server, no API key, no build step.

## Step 1: Clone

```bash
git clone https://github.com/Arjya-bit/FIR-Intelligence.git
cd FIR-Intelligence
```

## Step 2: Install and run

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install -r requirements.txt
python main.py
```

Expected output:

```
==============================================================
  FIR Intelligence & Crime Pattern Detector
  NLP + cross-FIR correlation for CCTNS-style records
==============================================================
Storage: in-memory fallback — MongoDB at mongodb://localhost:27017 unavailable
Seeding corpus with 100 NCRB-based FIR records...
Seeded 100 FIR records

Running NLP analysis...
Analysed 100 FIRs — 28 repeat offenders, 14 networks
Language model: rule-based (no credentials)
Storage: in-memory

Dashboard: http://localhost:8000
API docs:  http://localhost:8000/docs
```

The exact offender and network counts vary with the generated corpus.

Open <http://localhost:8000>.

## Step 3 (optional): Configure

```bash
cp .env.example .env
```

Every setting is optional.

### watsonx.ai

```env
WATSONX_API_KEY=your-key
WATSONX_PROJECT_ID=your-project-id
WATSONX_URL=https://us-south.ml.cloud.ibm.com
```

Get these from IBM Cloud → watsonx.ai → your project → **Manage → General** (project ID) and
**IAM → API keys** (key).

Without them the service classifies with a keyword engine and answers questions and reports
deterministically from the analysed corpus. `/api/health` reports which is active.

### MongoDB

```env
FIR_STORAGE=auto                   # auto | memory | mongodb
MONGO_URL=mongodb://localhost:27017
MONGO_DB=fir_intelligence
```

`auto` uses MongoDB when it answers a ping within `MONGO_TIMEOUT_MS`, otherwise it falls
back to the in-memory store and says so at startup. Use `mongodb` to make an unreachable
server a hard failure instead, or `memory` to skip the probe.

With Docker:

```bash
docker run -d -p 27017:27017 --name fir-mongo mongo:7
```

### Exposing the service

The server binds to `127.0.0.1` by default. To reach it from another machine:

```env
FIR_HOST=0.0.0.0
```

There is no authentication — put an authenticating reverse proxy in front of it before
exposing it anywhere real.

## Step 4 (optional): The Vite client

`static/` already contains a working dashboard. The React client in `src/frontend` is an
alternative with hot reload:

```bash
cd src/frontend
npm install
npm run dev          # http://localhost:5173, proxies /api to port 8000
```

## Step 5 (optional): IBM Bob CLI

```bash
bob mcp add fir-intelligence -- python src/mcp_server/server.py
bob chat
```

Then ask Bob things like "who are the repeat offenders?" or "show me the crime networks".

## Running the tests

```bash
pip install -r requirements-dev.txt
pytest
```

## Rebuilding the dashboard

`static/app.js` is compiled from `static/app.jsx`, and `static/vendor/` holds the React and
Recharts bundles. After editing the source:

```bash
./scripts/build-ui.sh
```

Shipping it precompiled means the browser never downloads or runs Babel, and the dashboard
works with no CDN access.

## Troubleshooting

| Symptom | Cause and fix |
|---------|---------------|
| `ResolutionImpossible` on install | Old pins. `requirements.txt` needs `motor==3.7.0`; motor 3.6.x caps `pymongo<4.10`. |
| `Address already in use` | Another process holds port 8000. Set `FIR_PORT`, or stop it. |
| "Dashboard assets could not load" | `static/vendor/` is missing or empty. Run `./scripts/build-ui.sh`. |
| Startup says "in-memory fallback" | No MongoDB reachable. Expected, and fine — data just does not persist across restarts. |
| `/api/*` returns 503 | Startup analysis has not finished. Wait a few seconds. |
| Blank charts, `/api/dashboard` 200 | Stale `static/app.js`. Run `./scripts/build-ui.sh`. |
| watsonx.ai 401 after ~1 hour | Fixed: IAM tokens now refresh before expiry. Ensure you are on the current `bob_client.py`. |

## Verifying the install

```bash
curl -s localhost:8000/api/health
curl -s "localhost:8000/api/firs?limit=1"
curl -s -X POST localhost:8000/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"Who are the repeat offenders?"}'
```
