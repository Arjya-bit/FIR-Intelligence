import json
import sys
from pathlib import Path
from datetime import date
from contextlib import asynccontextmanager

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from models import AnalysisResult, ChatRequest, ChatResponse, FIRRecord
from nlp_engine import analyze_fir_batch, get_analysis_context
from pattern_detector import detect_crime_networks
from bob_client import chat_with_bob, generate_intelligence_report
import database as db

analysis_cache: AnalysisResult | None = None

STATIC_DIR = Path(__file__).parent / "static"


SEED_VERSION = 2

async def _seed_database():
    """Seed MongoDB with NCRB data if empty or outdated."""
    meta = await db.get_latest_meta()
    if meta and meta.get("seed_version") == SEED_VERSION:
        count = await db.count_firs()
        print(f"Database already seeded (v{SEED_VERSION}) with {count} FIRs")
        return

    print("Seeding database with NCRB crime records (v2 - all structured)...")
    await db.clear_all()

    from ncrb_seed import generate_ncrb_dataset

    dataset = generate_ncrb_dataset(100)
    for doc in dataset:
        doc.pop("_source", None)
        doc.pop("_network", None)
        if "_id" in doc:
            del doc["_id"]

    await db.insert_firs(dataset)
    await db.save_analysis_meta({"seed_version": SEED_VERSION})
    print(f"Seeded {len(dataset)} NCRB-based FIR records into MongoDB")


async def _run_analysis():
    """Load FIRs from MongoDB, run NLP analysis, save results back."""
    global analysis_cache

    fir_docs = await db.get_all_firs(limit=500)
    for doc in fir_docs:
        doc.pop("_id", None)
        doc.pop("inserted_at", None)
        doc.pop("updated_at", None)

    analysis_cache = await analyze_fir_batch(fir_docs)

    offender_docs = []
    for ro in analysis_cache.repeat_offenders:
        d = ro.model_dump()
        for key in ("first_seen", "last_seen"):
            if d.get(key):
                d[key] = d[key].isoformat()
        d["risk_level"] = d["risk_level"].value if hasattr(d.get("risk_level", ""), "value") else d.get("risk_level", "low")
        offender_docs.append(d)
    await db.save_offenders(offender_docs)

    station_docs = []
    for ss in analysis_cache.station_summaries:
        d = ss.model_dump()
        station_docs.append(d)
    await db.save_stations(station_docs)

    networks = detect_crime_networks(analysis_cache.fir_records)
    await db.save_networks(networks)

    await db.save_analysis_meta({
        "total_firs": analysis_cache.total_firs_processed,
        "repeat_offenders": len(analysis_cache.repeat_offenders),
        "stations": len(analysis_cache.station_summaries),
        "networks": len(networks),
    })


@asynccontextmanager
async def lifespan(app: FastAPI):
    global analysis_cache
    print("=" * 60)
    print("  FIR Intelligence & Crime Pattern Detector")
    print("  Powered by IBM watsonx.ai Granite 3 + MongoDB")
    print("=" * 60)

    await db.connect()
    await _seed_database()

    print("\nRunning NLP analysis on FIR records...")
    await _run_analysis()
    print(f"Analyzed {analysis_cache.total_firs_processed} FIRs, "
          f"found {len(analysis_cache.repeat_offenders)} repeat offenders")
    print(f"\nDashboard ready at: http://localhost:8000")
    print(f"API docs at: http://localhost:8000/docs")
    print("=" * 60)
    yield
    await db.disconnect()
    analysis_cache = None


app = FastAPI(
    title="FIR Intelligence & Crime Pattern Detector",
    description="Bob-powered NLP intelligence tool for analyzing FIRs, detecting crime patterns, and identifying repeat offenders",
    version="2.0.0",
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


@app.get("/")
async def serve_frontend():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
async def health():
    count = await db.count_firs()
    return {
        "status": "ok",
        "database": "mongodb",
        "firs_in_db": count,
        "firs_analyzed": analysis_cache.total_firs_processed if analysis_cache else 0,
    }


@app.get("/api/dashboard")
async def get_dashboard():
    if not analysis_cache:
        raise HTTPException(503, "Analysis not ready")

    crime_breakdown = await db.get_crime_breakdown()
    district_breakdown = await db.get_district_breakdown()
    monthly_trend = await db.get_monthly_trend()
    severity_distribution = await db.get_severity_distribution()
    stats = await db.get_fir_stats()

    return {
        "total_firs": stats.get("total", analysis_cache.total_firs_processed),
        "total_accused": stats.get("total_accused", 0),
        "total_victims": stats.get("total_victims", 0),
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
            "date": r.date_filed.isoformat(),
            "police_station": r.police_station,
            "district": r.district,
            "crime_type": r.crime_type.value if r.crime_type else "other",
            "ipc_sections": r.ipc_sections,
            "severity": "critical" if r.severity_score >= 80 else "high" if r.severity_score >= 60 else "medium" if r.severity_score >= 40 else "low",
            "text": r.raw_text,
            "entities": {
                "accused": [a.model_dump() for a in r.accused],
                "victims": [v.model_dump() for v in r.victims],
                "location": r.location.model_dump() if r.location else None,
                "modus_operandi": r.modus_operandi.model_dump() if r.modus_operandi else None,
                "ipc_sections": r.ipc_sections,
            },
            "summary": r.summary,
        }
        for r in records
    ]


@app.get("/api/firs/{fir_number:path}")
async def get_fir_detail(fir_number: str):
    doc = await db.get_fir(fir_number)
    if not doc:
        raise HTTPException(404, f"FIR {fir_number} not found")

    doc.pop("_id", None)
    doc.pop("inserted_at", None)
    doc.pop("updated_at", None)
    return doc


@app.get("/api/repeat-offenders")
async def get_repeat_offenders():
    if not analysis_cache:
        raise HTTPException(503, "Analysis not ready")

    return [
        {
            "primary_name": ro.name,
            "aliases": ro.aliases,
            "linked_firs": ro.linked_firs,
            "crime_types": ro.crime_types,
            "stations": ro.stations,
            "districts": ro.districts,
            "risk_level": ro.risk_level.value,
            "mo_signature": ro.mo_signature,
            "fir_count": ro.total_incidents,
            "match_confidence": ro.confidence_score,
            "first_seen": ro.first_seen.isoformat() if ro.first_seen else None,
            "last_seen": ro.last_seen.isoformat() if ro.last_seen else None,
            "intelligence_assessment": f"Cross-FIR correlation identified {ro.name} across {len(ro.districts)} districts with {ro.total_incidents} linked incidents. "
                                       f"Primary crime types: {', '.join(ro.crime_types)}. "
                                       f"{'MO Signature: ' + ro.mo_signature + '. ' if ro.mo_signature else ''}"
                                       f"Risk level: {ro.risk_level.value.upper()}.",
        }
        for ro in analysis_cache.repeat_offenders
    ]


@app.get("/api/stations")
async def get_station_summaries():
    if not analysis_cache:
        raise HTTPException(503, "Analysis not ready")

    result = []
    for s in analysis_cache.station_summaries:
        d = s.model_dump()
        if s.total_firs >= 3:
            d["risk_level"] = "high"
        elif s.total_firs >= 2:
            d["risk_level"] = "medium"
        else:
            d["risk_level"] = "low"
        d["assessment"] = s.risk_assessment
        result.append(d)
    return result


@app.get("/api/networks")
async def get_crime_networks():
    if not analysis_cache:
        raise HTTPException(503, "Analysis not ready")

    networks = detect_crime_networks(analysis_cache.fir_records)
    for net in networks:
        members = set()
        for fir in analysis_cache.fir_records:
            if fir.fir_number in net.get("fir_numbers", []):
                for acc in fir.accused:
                    members.add(acc.name)
        net["key_members"] = sorted(members)
        net["intelligence_brief"] = (
            f"Network '{net['name']}' operates across {', '.join(net['districts'])} "
            f"with {net['fir_count']} linked FIRs. "
            f"Crime types: {', '.join(net['crime_types'])}. "
            f"Active period: {net['active_period']['start']} to {net['active_period']['end']}."
        )
    return networks


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

    for doc in fir_data:
        doc.pop("_id", None)
        await db.upsert_fir(doc)

    await _run_analysis()

    return {
        "message": f"Successfully processed {analysis_cache.total_firs_processed} FIRs",
        "repeat_offenders_found": len(analysis_cache.repeat_offenders),
        "stations_analyzed": len(analysis_cache.station_summaries),
    }


@app.get("/api/report")
async def generate_report():
    if not analysis_cache:
        raise HTTPException(503, "Analysis not ready")

    crime_breakdown = await db.get_crime_breakdown()

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


@app.get("/api/db-stats")
async def db_stats():
    """MongoDB statistics endpoint."""
    stats = await db.get_fir_stats()
    stats.pop("_id", None)
    return {
        "database": "MongoDB",
        "url": db.MONGO_URL,
        "db_name": db.DB_NAME,
        "stats": stats,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
