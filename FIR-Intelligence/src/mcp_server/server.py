"""MCP server exposing FIR intelligence tools over stdio.

IBM Bob (or any MCP client) can call these tools to query the same analysis the
web dashboard serves. It imports the modules at the repository root — the
canonical implementation — rather than a private copy, so the assistant and the
dashboard can never disagree about the corpus.

Run directly for a JSON-RPC stdio server:

    python src/mcp_server/server.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

# The analysis modules live at the repository root.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import intel_qa  # noqa: E402
from models import AnalysisResult  # noqa: E402
from nlp_engine import analyze_fir_batch, get_analysis_context  # noqa: E402
from pattern_detector import detect_crime_networks  # noqa: E402

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "fir-intelligence-server", "version": "2.1.0"}

#: The corpus the dashboard serves, analysed once at startup.
analysis_cache: AnalysisResult | None = None
networks_cache: list[dict] = []


async def initialize() -> AnalysisResult:
    """Load and analyse the seeded corpus."""
    global analysis_cache, networks_cache

    from ncrb_seed import generate_ncrb_dataset

    dataset = generate_ncrb_dataset(100)
    for doc in dataset:
        doc.pop("_source", None)
        doc.pop("_network", None)

    analysis_cache = await analyze_fir_batch(dataset)
    networks_cache = detect_crime_networks(analysis_cache.fir_records)
    return analysis_cache


async def _ensure_ready() -> AnalysisResult:
    if analysis_cache is None:
        await initialize()
    return analysis_cache


TOOLS = [
    {
        "name": "analyze_firs",
        "description": (
            "Analyse a batch of raw FIR texts: classify the crime type, extract "
            "accused, victims, location, IPC sections and modus operandi, and "
            "report the entities found. Does not modify the loaded corpus."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "fir_texts": {
                    "type": "array", "items": {"type": "string"},
                    "description": "FIR narrative texts to analyse",
                }
            },
            "required": ["fir_texts"],
        },
    },
    {
        "name": "get_repeat_offenders",
        "description": (
            "List accused linked to multiple FIRs, with linked FIR numbers, "
            "districts, risk level, MO signature and match confidence."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "min_incidents": {
                    "type": "integer", "default": 2,
                    "description": "Minimum distinct FIRs to flag an offender",
                },
                "risk_level": {
                    "type": "string",
                    "enum": ["critical", "high", "medium", "low"],
                    "description": "Optional risk level filter",
                },
            },
        },
    },
    {
        "name": "get_station_summary",
        "description": (
            "Station-level crime rollup: offence breakdown, monthly trend, "
            "hotspot areas, repeat offender count and a risk assessment."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "station_name": {
                    "type": "string",
                    "description": "Station name filter; omit for all stations",
                }
            },
        },
    },
    {
        "name": "get_crime_networks",
        "description": (
            "Organised crime networks found by correlating shared offender "
            "identities and shared modus operandi across FIRs."
        ),
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "search_firs",
        "description": "Search FIRs by crime type, district, station, accused name or keyword.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search text"},
                "limit": {"type": "integer", "default": 25},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_fir",
        "description": "Full detail for one FIR by its FIR number.",
        "inputSchema": {
            "type": "object",
            "properties": {"fir_number": {"type": "string"}},
            "required": ["fir_number"],
        },
    },
    {
        "name": "ask_intelligence",
        "description": (
            "Ask a natural-language question about the corpus — patterns, "
            "offenders, networks, districts, severity or a named individual — "
            "and get an answer computed from the analysed FIRs."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"question": {"type": "string"}},
            "required": ["question"],
        },
    },
    {
        "name": "generate_intelligence_report",
        "description": (
            "Full crime intelligence report: executive summary, pattern "
            "analysis, repeat offender alerts, networks, station trends, "
            "recommended actions and risk assessment."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "focus_area": {
                    "type": "string",
                    "description": "Optional district or crime type to focus on",
                }
            },
        },
    },
]


async def handle_tool_call(name: str, arguments: dict) -> str:
    result = await _ensure_ready()

    if name == "analyze_firs":
        texts = arguments.get("fir_texts") or []
        if not texts:
            return json.dumps({"error": "fir_texts must contain at least one FIR"})
        batch = [
            {
                "fir_number": f"ADHOC/{i + 1:03d}",
                "date_filed": "2024-01-01",
                "police_station": "Unknown",
                "district": "Unknown",
                "raw_text": text,
            }
            for i, text in enumerate(texts)
        ]
        # Analyse into a local variable: overwriting the shared cache here made
        # every later tool call report on the ad-hoc batch instead of the corpus.
        adhoc = await analyze_fir_batch(batch)
        crime_counts: dict[str, int] = {}
        for fir in adhoc.fir_records:
            key = fir.crime_type.value if fir.crime_type else "other"
            crime_counts[key] = crime_counts.get(key, 0) + 1
        return json.dumps({
            "total_processed": adhoc.total_firs_processed,
            "crime_types": crime_counts,
            "entities_extracted": adhoc.entity_stats,
            "repeat_offenders_within_batch": len(adhoc.repeat_offenders),
            "records": [
                {
                    "fir_number": f.fir_number,
                    "crime_type": f.crime_type.value if f.crime_type else "other",
                    "severity_score": f.severity_score,
                    "ipc_sections": f.ipc_sections,
                    "accused": [a.model_dump() for a in f.accused],
                    "victims": [v.model_dump() for v in f.victims],
                    "modus_operandi": (f.modus_operandi.model_dump()
                                       if f.modus_operandi else None),
                    "summary": f.summary,
                }
                for f in adhoc.fir_records
            ],
        }, indent=2)

    if name == "get_repeat_offenders":
        minimum = int(arguments.get("min_incidents", 2))
        risk = arguments.get("risk_level")
        offenders = [o for o in result.repeat_offenders if o.total_incidents >= minimum]
        if risk:
            offenders = [o for o in offenders if o.risk_level.value == risk]
        return json.dumps([o.model_dump(mode="json") for o in offenders], indent=2)

    if name == "get_station_summary":
        station = arguments.get("station_name")
        summaries = result.station_summaries
        if station:
            summaries = [s for s in summaries
                         if station.lower() in s.station_name.lower()]
        return json.dumps([s.model_dump(mode="json") for s in summaries], indent=2)

    if name == "get_crime_networks":
        return json.dumps(networks_cache, indent=2, default=str)

    if name == "search_firs":
        query = (arguments.get("query") or "").lower().strip()
        limit = int(arguments.get("limit", 25))
        if not query:
            return json.dumps({"error": "query must not be empty"})
        matches = [
            {
                "fir_number": fir.fir_number,
                "date_filed": fir.date_filed.isoformat(),
                "crime_type": fir.crime_type.value if fir.crime_type else "other",
                "district": fir.district,
                "station": fir.police_station,
                "severity_score": fir.severity_score,
                "summary": fir.summary,
                "accused": [a.name for a in fir.accused],
            }
            for fir in result.fir_records
            if query in fir.raw_text.lower()
            or query == (fir.crime_type.value if fir.crime_type else "")
            or query in fir.district.lower()
            or query in fir.police_station.lower()
            or query in fir.fir_number.lower()
            or any(query in a.name.lower() for a in fir.accused)
        ]
        return json.dumps({"total": len(matches), "results": matches[:limit]}, indent=2)

    if name == "get_fir":
        number = arguments.get("fir_number", "")
        for fir in result.fir_records:
            if fir.fir_number == number:
                return json.dumps(fir.model_dump(mode="json"), indent=2)
        return json.dumps({"error": f"FIR {number} not found"})

    if name == "ask_intelligence":
        question = arguments.get("question", "")
        return intel_qa.answer_question(question, result, networks_cache)

    if name == "generate_intelligence_report":
        focus = (arguments.get("focus_area") or "").strip()
        report = intel_qa.build_report(result, networks_cache)
        if focus and focus.lower() != "all":
            focused = intel_qa.answer_question(focus, result, networks_cache)
            report += f"\n\n8. FOCUS: {focus.upper()}\n{focused}"
        return report

    return json.dumps({"error": f"Unknown tool: {name}"})


def _response(req_id, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _error(req_id, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


async def dispatch(request: dict) -> dict | None:
    """Handle one JSON-RPC request. Returns ``None`` for notifications."""
    method = request.get("method", "")
    req_id = request.get("id")

    # Notifications carry no id and MUST NOT be answered. The previous version
    # replied with `{"id": null, "result": {}}`, which is a protocol violation.
    if req_id is None:
        return None

    if method == "initialize":
        return _response(req_id, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": SERVER_INFO,
        })

    if method == "tools/list":
        return _response(req_id, {"tools": TOOLS})

    if method == "tools/call":
        params = request.get("params") or {}
        tool_name = params.get("name", "")
        if not any(tool["name"] == tool_name for tool in TOOLS):
            return _error(req_id, -32602, f"Unknown tool: {tool_name}")
        try:
            text = await handle_tool_call(tool_name, params.get("arguments") or {})
        except Exception as exc:  # noqa: BLE001 - report, never kill the server
            return _response(req_id, {
                "content": [{"type": "text", "text": f"Tool failed: {exc}"}],
                "isError": True,
            })
        return _response(req_id, {"content": [{"type": "text", "text": text}]})

    if method == "ping":
        return _response(req_id, {})

    return _error(req_id, -32601, f"Method not found: {method}")


async def run_stdio_server() -> None:
    """Serve MCP over stdio."""
    await initialize()
    print(f"FIR Intelligence MCP server ready — "
          f"{analysis_cache.total_firs_processed} FIRs, "
          f"{len(analysis_cache.repeat_offenders)} repeat offenders, "
          f"{len(networks_cache)} networks", file=sys.stderr, flush=True)

    loop = asyncio.get_running_loop()
    while True:
        line = await loop.run_in_executor(None, sys.stdin.readline)
        if not line:  # EOF — the client closed the pipe
            break
        line = line.strip()
        if not line:
            continue

        try:
            request = json.loads(line)
        except json.JSONDecodeError as exc:
            # A single malformed line used to terminate the whole server.
            # Report a parse error and keep serving.
            _write(_error(None, -32700, f"Parse error: {exc}"))
            continue

        try:
            response = await dispatch(request)
        except Exception as exc:  # noqa: BLE001
            response = _error(request.get("id"), -32603, str(exc))

        if response is not None:
            _write(response)


def _write(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload) + "\n")
    sys.stdout.flush()


if __name__ == "__main__":
    try:
        asyncio.run(run_stdio_server())
    except KeyboardInterrupt:
        pass
