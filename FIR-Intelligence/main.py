"""FIR Intelligence & Crime Pattern Detector — HTTP API.

Boots by seeding a corpus of NCRB-shaped FIRs, running the NLP + correlation
pipeline over it, and serving the results to the dashboard in ``static/``.
Storage is MongoDB when available and an in-memory store otherwise, so the
service starts with no infrastructure (see :mod:`database`).
"""

from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, ORJSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

import database as db
import intel_qa
from bob_client import (
    chat_with_bob,
    generate_intelligence_report,
    is_configured as watsonx_configured,
)
from models import AnalysisResult, ChatRequest, ChatResponse, FIRRecord
from nlp_engine import analyze_fir_batch, get_analysis_context
from pattern_detector import FUZZY_THRESHOLD, detect_crime_networks

STATIC_DIR = Path(__file__).parent / "static"
SEED_VERSION = 3
SEED_SIZE = int(os.getenv("FIR_SEED_SIZE", "100"))
MAX_UPLOAD_BYTES = int(os.getenv("FIR_MAX_UPLOAD_BYTES", str(8 * 1024 * 1024)))

#: Browsers reject ``Access-Control-Allow-Origin: *`` when credentials are
#: allowed, so the wildcard default is paired with credentials disabled.
#: Set FIR_CORS_ORIGINS to a comma-separated list to allow credentialed calls.
_configured_origins = [o.strip() for o in
                       os.getenv("FIR_CORS_ORIGINS", "").split(",") if o.strip()]
CORS_ORIGINS = _configured_origins or ["*"]
CORS_CREDENTIALS = bool(_configured_origins)

analysis_cache: AnalysisResult | None = None
networks_cache: list[dict] = []
#: Analysis rebuilds mutate shared state, so uploads must not interleave.
_analysis_lock = asyncio.Lock()


def _require_analysis() -> AnalysisResult:
    if analysis_cache is None:
        raise HTTPException(503, "Analysis not ready — the service is still starting")
    return analysis_cache


def _severity_band(score: float) -> str:
    if score >= 80:
        return "critical"
    if score >= 60:
        return "high"
    if score >= 40:
        return "medium"
    return "low"


def _fir_payload(record: FIRRecord, *, full_text: bool = False) -> dict:
    """One serialisation for both the list and the detail endpoint.

    The two previously returned different field names for the same data
    (``date`` vs ``date_filed``, flat vs nested entities), which meant the
    detail view could not reuse anything the list had already rendered.
    """
    text = record.raw_text
    return {
        "fir_number": record.fir_number,
        "date": record.date_filed.isoformat(),
        "police_station": record.police_station,
        "district": record.district,
        "state": record.state,
        "crime_type": record.crime_type.value if record.crime_type else "other",
        "ipc_sections": record.ipc_sections,
        "severity": _severity_band(record.severity_score),
        "severity_score": record.severity_score,
        "summary": record.summary,
        "text": text if full_text else text[:400],
        "text_truncated": not full_text and len(text) > 400,
        "entities": {
            "accused": [a.model_dump() for a in record.accused],
            "victims": [v.model_dump() for v in record.victims],
            "location": record.location.model_dump() if record.location else None,
            "modus_operandi": (record.modus_operandi.model_dump()
                               if record.modus_operandi else None),
            "ipc_sections": record.ipc_sections,
        },
    }


def _offender_payload(offender) -> dict:
    return {
        "primary_name": offender.name,
        "aliases": offender.aliases,
        "linked_firs": offender.linked_firs,
        "crime_types": offender.crime_types,
        "stations": offender.stations,
        "districts": offender.districts,
        "risk_level": offender.risk_level.value,
        "mo_signature": offender.mo_signature,
        "fir_count": offender.total_incidents,
        "match_confidence": offender.confidence_score,
        "first_seen": offender.first_seen.isoformat() if offender.first_seen else None,
        "last_seen": offender.last_seen.isoformat() if offender.last_seen else None,
        "intelligence_assessment": (
            f"Cross-FIR correlation links {offender.name} to "
            f"{offender.total_incidents} FIRs across {len(offender.districts)} "
            f"district(s): {', '.join(offender.districts)}. "
            f"Offences: {', '.join(c.replace('_', ' ') for c in offender.crime_types)}. "
            f"{'MO signature: ' + offender.mo_signature + '. ' if offender.mo_signature else ''}"
            f"Identity resolved with {offender.confidence_score:.0%} confidence; "
            f"risk assessed {offender.risk_level.value.upper()}."
        ),
    }


# ── Startup ────────────────────────────────────────────────────────────────


async def _seed_database() -> None:
    """Populate the store with the NCRB-shaped corpus if it is empty/stale."""
    meta = await db.get_latest_meta()
    if meta and meta.get("seed_version") == SEED_VERSION:
        print(f"Corpus already seeded (v{SEED_VERSION}): "
              f"{await db.count_firs()} FIRs")
        return

    print(f"Seeding corpus with {SEED_SIZE} NCRB-based FIR records...")
    await db.clear_all()

    from ncrb_seed import generate_ncrb_dataset

    dataset = generate_ncrb_dataset(SEED_SIZE)
    for doc in dataset:
        doc.pop("_source", None)
        doc.pop("_network", None)
        doc.pop("_id", None)

    inserted = await db.insert_firs(dataset)
    await db.save_analysis_meta({"seed_version": SEED_VERSION})
    print(f"Seeded {inserted} FIR records")


async def _run_analysis() -> None:
    """Load FIRs, run the NLP + correlation pipeline, persist the results."""
    global analysis_cache, networks_cache

    fir_docs = await db.get_all_firs(limit=10_000)
    for doc in fir_docs:
        for field in ("_id", "inserted_at", "updated_at"):
            doc.pop(field, None)

    result = await analyze_fir_batch(fir_docs)
    networks = detect_crime_networks(result.fir_records)
    analysis_cache, networks_cache = result, networks

    offender_docs = []
    for offender in result.repeat_offenders:
        doc = offender.model_dump(mode="json")
        offender_docs.append(doc)
    await db.save_offenders(offender_docs)
    await db.save_stations([s.model_dump(mode="json") for s in result.station_summaries])
    await db.save_networks(networks)
    await db.save_analysis_meta({
        "seed_version": SEED_VERSION,
        "total_firs": result.total_firs_processed,
        "repeat_offenders": len(result.repeat_offenders),
        "stations": len(result.station_summaries),
        "networks": len(networks),
    })


@asynccontextmanager
async def lifespan(app: FastAPI):
    global analysis_cache, networks_cache

    print("=" * 62)
    print("  FIR Intelligence & Crime Pattern Detector")
    print("  NLP + cross-FIR correlation for CCTNS-style records")
    print("=" * 62)

    backend = await db.connect()
    await _seed_database()

    print("\nRunning NLP analysis...")
    async with _analysis_lock:
        await _run_analysis()
    print(f"Analysed {analysis_cache.total_firs_processed} FIRs — "
          f"{len(analysis_cache.repeat_offenders)} repeat offenders, "
          f"{len(networks_cache)} networks")
    print(f"Language model: "
          f"{'IBM watsonx.ai' if watsonx_configured() else 'rule-based (no credentials)'}")
    print(f"Storage: {backend}")
    print("\nDashboard: http://localhost:8000")
    print("API docs:  http://localhost:8000/docs")
    print("=" * 62)

    yield

    await db.disconnect()
    analysis_cache, networks_cache = None, []


app = FastAPI(
    title="FIR Intelligence & Crime Pattern Detector",
    description=(
        "NLP intelligence tool for analysing First Information Reports, "
        "detecting cross-district crime patterns and identifying repeat offenders."
    ),
    version="2.1.0",
    default_response_class=ORJSONResponse,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=CORS_CREDENTIALS,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Return a JSON error instead of an empty connection reset."""
    print(f"Unhandled error on {request.method} {request.url.path}: {exc!r}")
    return ORJSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "path": request.url.path},
    )


# ── Meta ───────────────────────────────────────────────────────────────────


@app.get("/api/health", tags=["meta"])
async def health():
    return {
        "status": "ok" if analysis_cache else "starting",
        "storage": db.backend_name(),
        "persistent": db.is_persistent(),
        "language_model": "watsonx.ai" if watsonx_configured() else "rule-based",
        "firs_in_db": await db.count_firs(),
        "firs_analyzed": analysis_cache.total_firs_processed if analysis_cache else 0,
        "repeat_offenders": len(analysis_cache.repeat_offenders) if analysis_cache else 0,
        "networks": len(networks_cache),
    }


@app.get("/api/filters", tags=["meta"])
async def get_filters():
    """Filter options, so the UI does not have to derive them from a full fetch."""
    result = _require_analysis()
    crime_types = sorted({r.crime_type.value if r.crime_type else "other"
                          for r in result.fir_records})
    districts = sorted({r.district for r in result.fir_records if r.district})
    stations = sorted({r.police_station for r in result.fir_records if r.police_station})
    return {
        "crime_types": crime_types,
        "districts": districts,
        "stations": stations,
        "severities": ["critical", "high", "medium", "low"],
        "total_firs": result.total_firs_processed,
    }


@app.get("/api/db-stats", tags=["meta"])
async def db_stats():
    stats = await db.get_fir_stats()
    stats.pop("_id", None)
    return {
        "storage": db.backend_name(),
        "persistent": db.is_persistent(),
        "url": db.MONGO_URL if db.is_persistent() else None,
        "db_name": db.DB_NAME if db.is_persistent() else None,
        "stats": stats,
    }


# ── Analytics ──────────────────────────────────────────────────────────────


@app.get("/api/dashboard", tags=["analytics"])
async def get_dashboard():
    result = _require_analysis()
    stats = await db.get_fir_stats()
    return {
        "total_firs": stats.get("total", result.total_firs_processed),
        "total_accused": stats.get("total_accused", result.entity_stats.get("total_accused", 0)),
        "total_victims": stats.get("total_victims", result.entity_stats.get("total_victims", 0)),
        "total_districts": len(stats.get("districts") or
                               {r.district for r in result.fir_records}),
        "total_stations": len(result.station_summaries),
        "avg_severity": stats.get("avg_severity", 0),
        "repeat_offenders_count": len(result.repeat_offenders),
        "networks_count": len(networks_cache),
        "crime_breakdown": await db.get_crime_breakdown(),
        "district_breakdown": await db.get_district_breakdown(),
        "monthly_trend": dict(sorted((await db.get_monthly_trend()).items())),
        "severity_distribution": await db.get_severity_distribution(),
        "crime_networks": networks_cache,
        "name_match_threshold": FUZZY_THRESHOLD,
    }


@app.get("/api/firs", tags=["firs"])
async def get_firs(
    crime_type: str | None = None,
    district: str | None = None,
    station: str | None = None,
    severity: str | None = Query(None, pattern="^(critical|high|medium|low)$"),
    q: str | None = Query(None, description="Free-text search across FIR content"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """Paginated, filtered FIR list.

    Returns an envelope rather than a bare array: the previous endpoint sent
    every record on every request, which does not survive a real CCTNS corpus.
    """
    result = _require_analysis()
    records = result.fir_records

    if crime_type:
        records = [r for r in records
                   if r.crime_type and r.crime_type.value == crime_type]
    if district:
        records = [r for r in records if r.district.lower() == district.lower()]
    if station:
        records = [r for r in records if station.lower() in r.police_station.lower()]
    if severity:
        records = [r for r in records if _severity_band(r.severity_score) == severity]
    if q:
        needle = q.lower().strip()
        records = [
            r for r in records
            if needle in r.fir_number.lower()
            or needle in r.raw_text.lower()
            or needle in r.district.lower()
            or needle in r.police_station.lower()
            or needle in r.summary.lower()
            or any(needle in a.name.lower() for a in r.accused)
            or any(needle in alias.lower() for a in r.accused for alias in a.aliases)
            or any(needle in v.name.lower() for v in r.victims)
        ]

    records = sorted(records, key=lambda r: (r.date_filed, r.fir_number), reverse=True)
    page = records[offset:offset + limit]
    return {
        "items": [_fir_payload(r) for r in page],
        "total": len(records),
        "limit": limit,
        "offset": offset,
        "has_more": offset + len(page) < len(records),
    }


@app.get("/api/firs/{fir_number:path}", tags=["firs"])
async def get_fir_detail(fir_number: str):
    """Full detail for one FIR. FIR numbers contain slashes, hence ``:path``."""
    result = _require_analysis()
    for record in result.fir_records:
        if record.fir_number == fir_number:
            payload = _fir_payload(record, full_text=True)
            payload["related"] = _related_firs(record, result)
            return payload
    raise HTTPException(404, f"FIR {fir_number} not found")


def _related_firs(record: FIRRecord, result: AnalysisResult) -> list[dict]:
    """Other FIRs tied to this one through a shared offender or network."""
    related: dict[str, str] = {}
    for offender in result.repeat_offenders:
        if record.fir_number in offender.linked_firs:
            for number in offender.linked_firs:
                if number != record.fir_number:
                    related[number] = f"shared offender: {offender.name}"
    for network in networks_cache:
        if record.fir_number in network["fir_numbers"]:
            for number in network["fir_numbers"]:
                related.setdefault(number, f"network: {network['name']}")
    return [{"fir_number": number, "reason": reason}
            for number, reason in sorted(related.items())]


@app.get("/api/repeat-offenders", tags=["analytics"])
async def get_repeat_offenders(
    risk_level: str | None = Query(None, pattern="^(critical|high|medium|low)$"),
    min_incidents: int = Query(2, ge=2, le=100),
):
    result = _require_analysis()
    offenders = [o for o in result.repeat_offenders
                 if o.total_incidents >= min_incidents]
    if risk_level:
        offenders = [o for o in offenders if o.risk_level.value == risk_level]
    return [_offender_payload(o) for o in offenders]


@app.get("/api/stations", tags=["analytics"])
async def get_station_summaries():
    result = _require_analysis()
    payload = []
    for station in result.station_summaries:
        doc = station.model_dump(mode="json")
        # Derive the badge from the assessment the detector already made,
        # instead of re-deriving it from the FIR count alone.
        assessment = station.risk_assessment
        doc["risk_level"] = assessment.split(" ")[0].lower().rstrip("—").strip() or "low"
        doc["assessment"] = assessment
        payload.append(doc)
    return payload


@app.get("/api/networks", tags=["analytics"])
async def get_crime_networks():
    _require_analysis()
    return networks_cache


@app.get("/api/trends", tags=["analytics"])
async def get_crime_trends():
    return _require_analysis().crime_trend


# ── Conversational + reporting ─────────────────────────────────────────────


@app.post("/api/chat", response_model=ChatResponse, tags=["bob"])
async def chat_endpoint(req: ChatRequest):
    result = _require_analysis()
    message = (req.message or "").strip()
    if not message:
        raise HTTPException(400, "message must not be empty")

    grounded = intel_qa.answer_question(message, result, networks_cache)
    context = await get_analysis_context(result, networks_cache)
    response = await chat_with_bob(message, context, deterministic_answer=grounded)

    referenced = [f.fir_number for f in result.fir_records if f.fir_number in response]
    entities = [o.name for o in result.repeat_offenders if o.name in response]
    return ChatResponse(
        response=response,
        firs_referenced=referenced,
        entities_referenced=entities,
    )


@app.get("/api/report", tags=["bob"])
async def generate_report():
    result = _require_analysis()
    grounded = intel_qa.build_report(result, networks_cache)
    metadata = {
        "total_firs": result.total_firs_processed,
        "crime_breakdown": await db.get_crime_breakdown(),
        "repeat_offender_count": len(result.repeat_offenders),
        "districts": sorted({f.district for f in result.fir_records}),
        "patterns": [n["name"] for n in networks_cache],
    }
    report = await generate_intelligence_report(metadata,
                                                deterministic_report=grounded)
    return {
        "report": report,
        "metadata": metadata,
        "source": "watsonx.ai" if watsonx_configured() else "rule-based analysis",
        "generated_at": result.generated_at.isoformat(),
    }


@app.post("/api/upload-firs", tags=["firs"])
async def upload_firs(file: UploadFile = File(...)):
    """Ingest a JSON array of FIR records and re-run the analysis."""
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            413, f"File exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit")

    try:
        payload = json.loads(content)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(400, f"Invalid JSON: {exc}") from exc

    if not isinstance(payload, list):
        raise HTTPException(400, "Expected a JSON array of FIR records")
    if not payload:
        raise HTTPException(400, "The uploaded array is empty")

    accepted, rejected = [], []
    for index, doc in enumerate(payload):
        if not isinstance(doc, dict):
            rejected.append({"index": index, "error": "not a JSON object"})
            continue
        doc.pop("_id", None)
        if not doc.get("fir_number"):
            rejected.append({"index": index, "error": "missing 'fir_number'"})
            continue
        if not doc.get("raw_text"):
            rejected.append({"index": index, "error": "missing 'raw_text'"})
            continue
        accepted.append(doc)

    if not accepted:
        raise HTTPException(
            400, {"message": "No valid FIR records found", "errors": rejected[:20]})

    # Validate through the pipeline before touching the store, so a bad batch
    # cannot leave the corpus half-updated.
    try:
        await analyze_fir_batch(accepted)
    except (ValidationError, ValueError, TypeError) as exc:
        raise HTTPException(422, f"Records failed validation: {exc}") from exc

    async with _analysis_lock:
        for doc in accepted:
            await db.upsert_fir(doc)
        await _run_analysis()

    return {
        "message": f"Ingested {len(accepted)} FIRs",
        "accepted": len(accepted),
        "rejected": len(rejected),
        "errors": rejected[:20],
        "total_firs": analysis_cache.total_firs_processed,
        "repeat_offenders_found": len(analysis_cache.repeat_offenders),
        "networks_found": len(networks_cache),
        "stations_analyzed": len(analysis_cache.station_summaries),
    }


# ── Static dashboard ───────────────────────────────────────────────────────


@app.get("/", include_in_schema=False)
async def serve_frontend():
    index = STATIC_DIR / "index.html"
    if not index.is_file():
        raise HTTPException(404, "Dashboard not built — static/index.html is missing")
    return FileResponse(index)


# The dashboard loads app.js and vendor/*.js as siblings of index.html. Without
# this mount only "/" was served, so every asset 404'd.
if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=os.getenv("FIR_HOST", "127.0.0.1"),
        port=int(os.getenv("FIR_PORT", "8000")),
        reload=os.getenv("FIR_RELOAD", "").lower() in {"1", "true", "yes"},
    )
