import json
import sys
from pathlib import Path
from datetime import date
from contextlib import asynccontextmanager

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from models import (
    AnalysisResult, ChatRequest, ChatResponse, FIRRecord
)
from nlp_engine import load_mock_firs, analyze_fir_batch, get_analysis_context
from pattern_detector import detect_crime_networks
from bob_client import chat_with_bob, generate_intelligence_report

analysis_cache: AnalysisResult | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global analysis_cache
    print("Loading and analyzing mock FIR data...")
    mock_data = load_mock_firs()
    analysis_cache = await analyze_fir_batch(mock_data)
    print(f"Analyzed {analysis_cache.total_firs_processed} FIRs, "
          f"found {len(analysis_cache.repeat_offenders)} repeat offenders")
    yield
    analysis_cache = None


app = FastAPI(
    title="FIR Intelligence & Crime Pattern Detector",
    description="Bob-powered NLP intelligence tool for analyzing FIRs, detecting crime patterns, and identifying repeat offenders",
    version="1.0.0",
    default_response_class=ORJSONResponse,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def serialize_date(obj):
    if isinstance(obj, date):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")


@app.get("/api/health")
async def health():
    return {"status": "ok", "firs_loaded": analysis_cache.total_firs_processed if analysis_cache else 0}


@app.get("/api/dashboard")
async def get_dashboard():
    if not analysis_cache:
        raise HTTPException(503, "Analysis not ready")

    crime_breakdown = {}
    district_breakdown = {}
    monthly_trend = {}
    severity_distribution = {"low": 0, "medium": 0, "high": 0, "critical": 0}

    for fir in analysis_cache.fir_records:
        ct = fir.crime_type.value if fir.crime_type else "other"
        crime_breakdown[ct] = crime_breakdown.get(ct, 0) + 1

        district_breakdown[fir.district] = district_breakdown.get(fir.district, 0) + 1

        month = fir.date_filed.isoformat()[:7]
        monthly_trend[month] = monthly_trend.get(month, 0) + 1

        if fir.severity_score >= 80:
            severity_distribution["critical"] += 1
        elif fir.severity_score >= 60:
            severity_distribution["high"] += 1
        elif fir.severity_score >= 40:
            severity_distribution["medium"] += 1
        else:
            severity_distribution["low"] += 1

    return {
        "total_firs": analysis_cache.total_firs_processed,
        "total_accused": analysis_cache.entity_stats.get("total_accused", 0),
        "total_victims": analysis_cache.entity_stats.get("total_victims", 0),
        "repeat_offenders_count": len(analysis_cache.repeat_offenders),
        "crime_breakdown": crime_breakdown,
        "district_breakdown": district_breakdown,
        "monthly_trend": dict(sorted(monthly_trend.items())),
        "severity_distribution": severity_distribution,
        "crime_networks": detect_crime_networks(analysis_cache.fir_records),
    }


@app.get("/api/firs")
async def get_firs(crime_type: str | None = None, district: str | None = None,
                   station: str | None = None):
    if not analysis_cache:
        raise HTTPException(503, "Analysis not ready")

    records = analysis_cache.fir_records

    if crime_type:
        records = [r for r in records if r.crime_type and r.crime_type.value == crime_type]
    if district:
        records = [r for r in records if r.district.lower() == district.lower()]
    if station:
        records = [r for r in records if station.lower() in r.police_station.lower()]

    return [
        {
            "fir_number": r.fir_number,
            "date_filed": r.date_filed.isoformat(),
            "police_station": r.police_station,
            "district": r.district,
            "crime_type": r.crime_type.value if r.crime_type else "other",
            "ipc_sections": r.ipc_sections,
            "accused": [a.model_dump() for a in r.accused],
            "victims": [v.model_dump() for v in r.victims],
            "location": r.location.model_dump() if r.location else None,
            "modus_operandi": r.modus_operandi.model_dump() if r.modus_operandi else None,
            "severity_score": r.severity_score,
            "summary": r.summary,
        }
        for r in records
    ]


@app.get("/api/firs/{fir_number}")
async def get_fir_detail(fir_number: str):
    if not analysis_cache:
        raise HTTPException(503, "Analysis not ready")

    for r in analysis_cache.fir_records:
        if r.fir_number == fir_number:
            return {
                "fir_number": r.fir_number,
                "date_filed": r.date_filed.isoformat(),
                "police_station": r.police_station,
                "district": r.district,
                "state": r.state,
                "raw_text": r.raw_text,
                "crime_type": r.crime_type.value if r.crime_type else "other",
                "ipc_sections": r.ipc_sections,
                "accused": [a.model_dump() for a in r.accused],
                "victims": [v.model_dump() for v in r.victims],
                "location": r.location.model_dump() if r.location else None,
                "modus_operandi": r.modus_operandi.model_dump() if r.modus_operandi else None,
                "severity_score": r.severity_score,
                "summary": r.summary,
            }

    raise HTTPException(404, f"FIR {fir_number} not found")


@app.get("/api/repeat-offenders")
async def get_repeat_offenders():
    if not analysis_cache:
        raise HTTPException(503, "Analysis not ready")

    return [
        {
            "name": ro.name,
            "aliases": ro.aliases,
            "linked_firs": ro.linked_firs,
            "crime_types": ro.crime_types,
            "stations": ro.stations,
            "districts": ro.districts,
            "risk_level": ro.risk_level.value,
            "mo_signature": ro.mo_signature,
            "total_incidents": ro.total_incidents,
            "confidence_score": ro.confidence_score,
            "first_seen": ro.first_seen.isoformat() if ro.first_seen else None,
            "last_seen": ro.last_seen.isoformat() if ro.last_seen else None,
        }
        for ro in analysis_cache.repeat_offenders
    ]


@app.get("/api/stations")
async def get_station_summaries():
    if not analysis_cache:
        raise HTTPException(503, "Analysis not ready")

    return [s.model_dump() for s in analysis_cache.station_summaries]


@app.get("/api/networks")
async def get_crime_networks():
    if not analysis_cache:
        raise HTTPException(503, "Analysis not ready")
    return detect_crime_networks(analysis_cache.fir_records)


@app.get("/api/trends")
async def get_crime_trends():
    if not analysis_cache:
        raise HTTPException(503, "Analysis not ready")
    return analysis_cache.crime_trend


@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest):
    if not analysis_cache:
        raise HTTPException(503, "Analysis not ready")

    context = await get_analysis_context(analysis_cache)
    response = await chat_with_bob(req.message, context)

    firs_ref = []
    for fir in analysis_cache.fir_records:
        if fir.fir_number in response:
            firs_ref.append(fir.fir_number)

    return ChatResponse(
        response=response,
        firs_referenced=firs_ref,
    )


@app.post("/api/upload-firs")
async def upload_firs(file: UploadFile = File(...)):
    global analysis_cache

    content = await file.read()
    try:
        fir_data = json.loads(content)
    except json.JSONDecodeError:
        raise HTTPException(400, "Invalid JSON file")

    if not isinstance(fir_data, list):
        raise HTTPException(400, "Expected a JSON array of FIR records")

    analysis_cache = await analyze_fir_batch(fir_data)

    return {
        "message": f"Successfully processed {analysis_cache.total_firs_processed} FIRs",
        "repeat_offenders_found": len(analysis_cache.repeat_offenders),
        "stations_analyzed": len(analysis_cache.station_summaries),
    }


@app.get("/api/report")
async def generate_report():
    if not analysis_cache:
        raise HTTPException(503, "Analysis not ready")

    crime_breakdown = {}
    for fir in analysis_cache.fir_records:
        ct = fir.crime_type.value if fir.crime_type else "other"
        crime_breakdown[ct] = crime_breakdown.get(ct, 0) + 1

    report_data = {
        "total_firs": analysis_cache.total_firs_processed,
        "crime_breakdown": crime_breakdown,
        "repeat_offender_count": len(analysis_cache.repeat_offenders),
        "districts": list(set(f.district for f in analysis_cache.fir_records)),
        "patterns": [
            n["name"] for n in detect_crime_networks(analysis_cache.fir_records)
        ],
    }

    report = await generate_intelligence_report(report_data)

    return {
        "report": report,
        "metadata": report_data,
        "generated_at": analysis_cache.generated_at.isoformat(),
    }


STATIC_DIR = Path(__file__).parent / "static"


@app.get("/")
async def serve_frontend():
    return FileResponse(STATIC_DIR / "index.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
