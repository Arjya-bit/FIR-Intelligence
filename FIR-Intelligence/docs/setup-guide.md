# Setup Guide

Complete instructions to run the FIR Intelligence & Crime Pattern Detector on your machine.

## Prerequisites

| Tool | Version | Check Command |
|------|---------|--------------|
| Python | 3.11+ | `python --version` |
| Node.js | 18+ | `node --version` |
| npm | 9+ | `npm --version` |
| pip | 23+ | `pip --version` |
| Git | 2.30+ | `git --version` |

### Optional (for IBM watsonx.ai integration)
- IBM Cloud account with watsonx.ai access
- API key from https://cloud.ibm.com/iam/apikeys
- watsonx.ai project ID

> **Note**: The system works fully without watsonx.ai credentials using a rule-based fallback. The AI features are enhanced when credentials are provided.

## Step 1: Clone the Repository

```bash
git clone https://github.com/<your-username>/bob-ai-hackathon-crimeintel-ai.git
cd bob-ai-hackathon-crimeintel-ai
```

## Step 2: Set Up the Backend

```bash
cd src/backend
```

### Create a virtual environment (recommended)

```bash
python -m venv venv

# On Windows:
venv\Scripts\activate

# On macOS/Linux:
source venv/bin/activate
```

### Install dependencies

```bash
pip install -r requirements.txt
```

### Configure environment variables

```bash
cp ../.env.example .env
```

Edit `.env` with your credentials (optional):

```env
WATSONX_API_KEY=your_api_key_here
WATSONX_PROJECT_ID=your_project_id_here
WATSONX_URL=https://us-south.ml.cloud.ibm.com
```

If you don't have watsonx.ai credentials, leave the defaults — the system will use the rule-based fallback.

### Start the backend server

```bash
python main.py
```

You should see:
```
Loading and analyzing mock FIR data...
Analyzed 25 FIRs, found X repeat offenders
INFO:     Uvicorn running on http://0.0.0.0:8000
```

### Verify backend is running

```bash
curl http://localhost:8000/api/health
```

Expected response:
```json
{"status":"ok","firs_loaded":25}
```

## Step 3: Set Up the Frontend

Open a **new terminal** (keep the backend running):

```bash
cd src/frontend
npm install
npm run dev
```

You should see:
```
VITE v6.x.x  ready in xxx ms
➜  Local:   http://localhost:5173/
```

## Step 4: Open the Dashboard

Open **http://localhost:5173** in your browser.

You should see the FIR Intelligence dashboard with:
- Crime type distribution chart
- District-wise FIR counts
- Monthly crime trends
- Severity distribution
- Identified crime networks

## Step 5: IBM Bob CLI Integration (Optional)

To use the MCP server with IBM Bob CLI:

### Register the MCP server

```bash
bob mcp add fir-intelligence -- python src/mcp_server/server.py
```

### Use in Bob chat

```bash
bob chat
```

Then try commands like:
- "Show me repeat offenders across Lucknow"
- "What crime networks are active?"
- "Generate an intelligence report for Kanpur burglaries"

## Verification Checklist

| Step | Expected Result |
|------|----------------|
| Backend starts | "Analyzed 25 FIRs, found X repeat offenders" |
| `GET /api/health` | `{"status":"ok","firs_loaded":25}` |
| `GET /api/dashboard` | JSON with crime_breakdown, district_breakdown |
| Frontend loads | Dashboard with charts and statistics |
| Click "FIR Records" | 25 FIR cards with entity details |
| Click "Repeat Offenders" | Flagged offenders with risk levels |
| Click "Crime Networks" | 5 identified networks with graphs |
| Click "Bob AI Chat" | Chat interface responds to queries |

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `ModuleNotFoundError` | Run `pip install -r requirements.txt` in the backend directory |
| Backend port 8000 in use | Kill existing process: `lsof -i :8000` then `kill <PID>` |
| Frontend can't reach API | Ensure backend is running on port 8000; check Vite proxy in `vite.config.js` |
| `npm install` fails | Delete `node_modules` and `package-lock.json`, then `npm install` again |
| watsonx.ai auth error | Check API key in `.env`; system falls back to rules if auth fails |
| Charts not loading | Refresh the page; check browser console for errors |
| CORS errors | Backend CORS is set to `*`; ensure both servers are running |
