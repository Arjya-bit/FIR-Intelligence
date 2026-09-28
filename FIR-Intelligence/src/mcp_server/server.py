"""
MCP Server for FIR Intelligence & Crime Pattern Detector.

This server exposes tools that IBM Bob CLI can call via the Model Context Protocol.
It provides FIR analysis, entity extraction, repeat offender detection,
and crime intelligence reporting capabilities.
"""
import json
import sys
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from models import AnalysisResult
from nlp_engine import load_mock_firs, analyze_fir_batch, get_analysis_context
from pattern_detector import detect_crime_networks
from bob_client import classify_crime, chat_with_bob

analysis_cache: AnalysisResult | None = None


async def initialize():
    global analysis_cache
    mock_data = load_mock_firs()
    analysis_cache = await analyze_fir_batch(mock_data)
    return analysis_cache


TOOLS = [
    {
        "name": "analyze_firs",
        "description": "Analyze a batch of FIR text samples. Categorizes each by crime type, extracts named entities (accused, location, MO, victim profile), and returns structured results.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "fir_texts": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Array of FIR text content to analyze"
                }
            },
            "required": ["fir_texts"]
        }
    },
    {
        "name": "get_repeat_offenders",
        "description": "Detect repeat-offender signatures across all analyzed FIRs. Returns flagged offenders with linked FIR numbers, crime types, risk levels, and MO signatures.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "min_incidents": {
                    "type": "integer",
                    "description": "Minimum number of linked FIRs to flag as repeat offender",
                    "default": 2
                }
            }
        }
    },
    {
        "name": "get_station_summary",
        "description": "Generate a station-level crime trend summary with crime breakdown, monthly trends, hotspot areas, and risk assessment.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "station_name": {
                    "type": "string",
                    "description": "Police station name (optional, returns all if omitted)"
                }
            }
        }
    },
    {
        "name": "get_crime_networks",
        "description": "Identify organized crime networks by analyzing cross-FIR patterns, shared accused, and similar modus operandi across districts.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "search_firs",
        "description": "Search FIRs by crime type, district, accused name, or keyword.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query — crime type, district name, accused name, or keyword"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "generate_intelligence_report",
        "description": "Generate a comprehensive crime intelligence report covering patterns, repeat offenders, station analysis, and recommended actions.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "focus_area": {
                    "type": "string",
                    "description": "Optional focus area: district name, crime type, or 'all'"
                }
            }
        }
    },
]


async def handle_tool_call(name: str, arguments: dict) -> str:
    global analysis_cache

    if analysis_cache is None:
        await initialize()

    if name == "analyze_firs":
        fir_texts = arguments.get("fir_texts", [])
        fir_data = [
            {
                "fir_number": f"UPLOADED/{i+1:03d}",
                "date_filed": "2024-01-01",
                "police_station": "Unknown",
                "district": "Unknown",
                "state": "Uttar Pradesh",
                "raw_text": text,
            }
            for i, text in enumerate(fir_texts)
        ]
        result = await analyze_fir_batch(fir_data)
        analysis_cache = result
        return json.dumps({
            "total_processed": result.total_firs_processed,
            "crime_types": {
                fir.crime_type.value if fir.crime_type else "other": 1
                for fir in result.fir_records
            },
            "entities_extracted": result.entity_stats,
            "repeat_offenders": len(result.repeat_offenders),
        }, indent=2)

    elif name == "get_repeat_offenders":
        min_inc = arguments.get("min_incidents", 2)
        offenders = [
            ro for ro in analysis_cache.repeat_offenders
            if ro.total_incidents >= min_inc
        ]
        return json.dumps([
            {
                "name": ro.name,
                "aliases": ro.aliases,
                "linked_firs": ro.linked_firs,
                "crime_types": ro.crime_types,
                "districts": ro.districts,
                "risk_level": ro.risk_level.value,
                "total_incidents": ro.total_incidents,
                "mo_signature": ro.mo_signature,
                "confidence": ro.confidence_score,
            }
            for ro in offenders
        ], indent=2)

    elif name == "get_station_summary":
        station = arguments.get("station_name")
        summaries = analysis_cache.station_summaries
        if station:
            summaries = [s for s in summaries if station.lower() in s.station_name.lower()]
        return json.dumps([s.model_dump() for s in summaries], indent=2)

    elif name == "get_crime_networks":
        networks = detect_crime_networks(analysis_cache.fir_records)
        return json.dumps(networks, indent=2)

    elif name == "search_firs":
        query = arguments.get("query", "").lower()
        matches = []
        for fir in analysis_cache.fir_records:
            if (query in fir.raw_text.lower() or
                query in (fir.crime_type.value if fir.crime_type else "") or
                query in fir.district.lower() or
                query in fir.police_station.lower() or
                any(query in a.name.lower() for a in fir.accused)):
                matches.append({
                    "fir_number": fir.fir_number,
                    "crime_type": fir.crime_type.value if fir.crime_type else "other",
                    "district": fir.district,
                    "station": fir.police_station,
                    "summary": fir.summary,
                    "accused": [a.name for a in fir.accused],
                })
        return json.dumps(matches, indent=2)

    elif name == "generate_intelligence_report":
        context = await get_analysis_context(analysis_cache)
        return context

    return json.dumps({"error": f"Unknown tool: {name}"})


async def run_stdio_server():
    """Run as MCP server using stdio transport."""
    await initialize()

    while True:
        try:
            line = await asyncio.get_event_loop().run_in_executor(
                None, sys.stdin.readline
            )
            if not line:
                break

            request = json.loads(line.strip())
            method = request.get("method", "")
            req_id = request.get("id")

            if method == "initialize":
                response = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {"listChanged": False}},
                        "serverInfo": {
                            "name": "fir-intelligence-server",
                            "version": "1.0.0",
                        },
                    },
                }
            elif method == "tools/list":
                response = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"tools": TOOLS},
                }
            elif method == "tools/call":
                params = request.get("params", {})
                tool_name = params.get("name", "")
                tool_args = params.get("arguments", {})
                result_text = await handle_tool_call(tool_name, tool_args)
                response = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": result_text}],
                    },
                }
            else:
                response = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {},
                }

            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()

        except (json.JSONDecodeError, EOFError):
            break
        except Exception as e:
            error_resp = {
                "jsonrpc": "2.0",
                "id": req_id if 'req_id' in dir() else None,
                "error": {"code": -32603, "message": str(e)},
            }
            sys.stdout.write(json.dumps(error_resp) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    asyncio.run(run_stdio_server())
