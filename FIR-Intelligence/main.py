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
from collections import Counter
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import (Depends, FastAPI, File, HTTPException, Query, Request,
                     Response, UploadFile)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, ORJSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

import auth
import database as db
import intel_qa
import llm_client
from bob_client import (
    chat_with_bob,
    generate_intelligence_report,
    is_configured as watsonx_configured,
)
from models import (AnalysisResult, ChatRequest, ChatResponse, FIRRecord,
                    LoginRequest, NewUserRequest, PasswordChangeRequest)
from nlp_engine import analyze_fir_batch, get_analysis_context
from pattern_detector import FUZZY_THRESHOLD, detect_crime_networks

STATIC_DIR = Path(__file__).parent / "static"
SEED_VERSION = 3
SEED_SIZE = int(os.getenv("FIR_SEED_SIZE", "100"))
MAX_UPLOAD_BYTES = int(os.getenv("FIR_MAX_UPLOAD_BYTES", str(8 * 1024 * 1024)))

#: RBAC is on by default. Turning it off is for local development only and
#: makes every request act as a full administrator.
AUTH_ENABLED = os.getenv("FIR_AUTH_ENABLED", "true").strip().lower() not in {
    "0", "false", "no", "off"}
#: Cookies are marked Secure unless explicitly serving plain HTTP locally.
COOKIE_SECURE = os.getenv("FIR_COOKIE_SECURE", "").strip().lower() in {
    "1", "true", "yes"}

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


# ── Access control ─────────────────────────────────────────────────────────

#: Stand-in identity when FIR_AUTH_ENABLED=false, so route handlers can always
#: ask `user.can(...)` without branching on whether auth is on.
_DEV_SUPERUSER = auth.User(username="dev", password_hash="", role="admin",
                           full_name="Auth disabled (development)")


def current_user(request: Request) -> auth.User:
    """Resolve the signed session cookie to a user, or raise 401."""
    if not AUTH_ENABLED:
        return _DEV_SUPERUSER

    token = request.cookies.get(auth.COOKIE_NAME)
    payload = auth.read_token(token) if token else None
    if not payload:
        raise HTTPException(401, "Not signed in", headers={"WWW-Authenticate": "Cookie"})

    user = auth.get_user(payload["sub"])
    if not user or not user.active:
        raise HTTPException(401, "Session no longer valid")
    # The role is re-read from the store, not trusted from the token, so a
    # demotion takes effect immediately instead of at the next login.
    return user


def requires(*permissions: str):
    """Dependency factory enforcing every listed permission."""
    def dependency(user: auth.User = Depends(current_user)) -> auth.User:
        missing = [p for p in permissions if not user.can(p)]
        if missing:
            raise HTTPException(
                403, f"Your role ({user.role}) lacks: {', '.join(missing)}")
        return user
    return dependency


def _set_session_cookie(response: Response, user: auth.User) -> None:
    response.set_cookie(
        auth.COOKIE_NAME,
        auth.issue_token(user.username, user.role),
        max_age=auth.SESSION_TTL_SECONDS,
        httponly=True,          # unreadable from JavaScript
        samesite="lax",         # blocks cross-site form submissions
        secure=COOKIE_SECURE,
        path="/",
    )


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

    if AUTH_ENABLED:
        created = auth.seed_demo_users()
        if created:
            print(f"\nCreated {len(created)} demo accounts: {', '.join(created)}")
    else:
        print("\n!! RBAC DISABLED (FIR_AUTH_ENABLED=false) — every request has "
              "full administrator access.")

    print("\nRunning NLP analysis...")
    async with _analysis_lock:
        await _run_analysis()
    print(f"Analysed {analysis_cache.total_firs_processed} FIRs — "
          f"{len(analysis_cache.repeat_offenders)} repeat offenders, "
          f"{len(networks_cache)} networks")
    status = _llm_status()
    print(f"Assistant: {status['source']}"
          f"{' · ' + status['model'] if status['model'] else ''}"
          f"{' (streaming)' if status['engine'] == 'llm' else ''}")
    if status["engine"] == "analysis":
        print("           No LLM configured — answers are computed from the corpus. "
              "Set ZAI_API_KEY to enable the AI assistant.")
    print(f"Storage: {backend}")

    if AUTH_ENABLED:
        insecure = auth.using_demo_credentials()
        print(f"Access control: enabled · {len(auth.list_users())} accounts · "
              f"{len(auth.ROLE_ORDER)} roles")
        if insecure:
            print("  !! DEMO PASSWORDS STILL IN USE for: "
                  f"{', '.join(insecure)}")
            print("     They are published in the README. Change them before "
                  "this is reachable by anyone else.")
        if auth.SECRET_IS_EPHEMERAL:
            print("  !! FIR_SECRET_KEY is not set — sessions are signed with a "
                  "random per-process key,")
            print("     so everyone is signed out when the server restarts.")

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


# ── Authentication ─────────────────────────────────────────────────────────


@app.post("/api/auth/login", tags=["auth"])
async def login(req: LoginRequest, response: Response):
    if not AUTH_ENABLED:
        return {"user": _DEV_SUPERUSER.public(), "auth_enabled": False}
    try:
        user = auth.authenticate(req.username, req.password)
    except auth.AuthError as exc:
        headers = {"Retry-After": str(exc.retry_after)} if exc.retry_after else None
        raise HTTPException(401, str(exc), headers=headers) from exc
    _set_session_cookie(response, user)
    return {"user": user.public(), "auth_enabled": True}


@app.post("/api/auth/logout", tags=["auth"])
async def logout(response: Response):
    response.delete_cookie(auth.COOKIE_NAME, path="/")
    return {"detail": "Signed out"}


@app.get("/api/auth/me", tags=["auth"])
async def whoami(user: auth.User = Depends(current_user)):
    return {"user": user.public(), "auth_enabled": AUTH_ENABLED}


@app.get("/api/auth/roles", tags=["auth"])
async def list_roles():
    """Public: the login screen explains what each role can do."""
    return [{"role": name, "label": entry["label"],
             "description": entry["description"],
             "permissions": sorted(entry["permissions"])}
            for name, entry in ((r, auth.ROLES[r]) for r in auth.ROLE_ORDER)]


@app.post("/api/auth/password", tags=["auth"])
async def change_password(req: PasswordChangeRequest,
                          user: auth.User = Depends(current_user)):
    if not auth.verify_password(req.current_password, user.password_hash):
        raise HTTPException(403, "Current password is incorrect.")
    try:
        auth.set_password(user.username, req.new_password)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"detail": "Password updated."}


@app.get("/api/auth/users", tags=["auth"])
async def get_users(user: auth.User = Depends(requires(auth.ADMIN_USERS))):
    return [u.public() for u in auth.list_users()]


@app.post("/api/auth/users", tags=["auth"])
async def add_user(req: NewUserRequest,
                   user: auth.User = Depends(requires(auth.ADMIN_USERS))):
    try:
        created = auth.create_user(
            req.username, req.password, req.role, full_name=req.full_name,
            station=req.station, district=req.district)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return created.public()


@app.post("/api/auth/users/{username}/active", tags=["auth"])
async def set_user_active(username: str, active: bool = Query(...),
                          user: auth.User = Depends(requires(auth.ADMIN_USERS))):
    if username == user.username and not active:
        raise HTTPException(400, "You cannot disable your own account.")
    try:
        return auth.set_active(username, active).public()
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.post("/api/auth/users/{username}/role", tags=["auth"])
async def set_user_role(username: str, role: str = Query(...),
                        user: auth.User = Depends(requires(auth.ADMIN_USERS))):
    if username == user.username:
        raise HTTPException(400, "You cannot change your own role.")
    try:
        return auth.set_role(username, role).public()
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/health", tags=["meta"])
async def health():
    status = _llm_status()
    return {
        "status": "ok" if analysis_cache else "starting",
        "auth_enabled": AUTH_ENABLED,
        "storage": db.backend_name(),
        "persistent": db.is_persistent(),
        "language_model": status["source"],
        "model": status["model"],
        "ai_enabled": status["engine"] != "analysis",
        "streaming": status["engine"] == "llm",
        "llm": llm_client.describe(),
        "watsonx_configured": watsonx_configured(),
        "firs_in_db": await db.count_firs(),
        "firs_analyzed": analysis_cache.total_firs_processed if analysis_cache else 0,
        "repeat_offenders": len(analysis_cache.repeat_offenders) if analysis_cache else 0,
        "networks": len(networks_cache),
    }


@app.get("/api/filters", tags=["meta"])
async def get_filters(user: auth.User = Depends(requires(auth.FIR_READ))):
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
async def db_stats(user: auth.User = Depends(requires(auth.ANALYTICS_READ))):
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
async def get_dashboard(user: auth.User = Depends(requires(auth.ANALYTICS_READ))):
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
    user: auth.User = Depends(requires(auth.FIR_READ)),
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
    show_pii = user.can(auth.FIR_READ_PII)
    items = [_fir_payload(r) for r in page]
    if not show_pii:
        items = [auth.redact_fir(item) for item in items]
    return {
        "items": items,
        "pii_redacted": not show_pii,
        "total": len(records),
        "limit": limit,
        "offset": offset,
        "has_more": offset + len(page) < len(records),
    }


@app.get("/api/firs/{fir_number:path}", tags=["firs"])
async def get_fir_detail(
        fir_number: str,
        user: auth.User = Depends(requires(auth.FIR_READ))):
    """Full detail for one FIR. FIR numbers contain slashes, hence ``:path``."""
    result = _require_analysis()
    for record in result.fir_records:
        if record.fir_number == fir_number:
            payload = _fir_payload(record, full_text=True)
            payload["related"] = _related_firs(record, result)
            return payload if user.can(auth.FIR_READ_PII) else {
                **auth.redact_fir(payload), "related": payload["related"]}
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
    user: auth.User = Depends(requires(auth.OFFENDER_READ)),
):
    result = _require_analysis()
    offenders = [o for o in result.repeat_offenders
                 if o.total_incidents >= min_incidents]
    if risk_level:
        offenders = [o for o in offenders if o.risk_level.value == risk_level]
    payloads = [_offender_payload(o) for o in offenders]
    if not user.can(auth.FIR_READ_PII):
        payloads = [auth.redact_offender(p) for p in payloads]
    return payloads


@app.get("/api/stations", tags=["analytics"])
async def get_station_summaries(
        user: auth.User = Depends(requires(auth.ANALYTICS_READ))):
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
async def get_crime_networks(
        user: auth.User = Depends(requires(auth.ANALYTICS_READ))):
    _require_analysis()
    return networks_cache


@app.get("/api/trends", tags=["analytics"])
async def get_crime_trends(
        user: auth.User = Depends(requires(auth.ANALYTICS_READ))):
    return _require_analysis().crime_trend


@app.get("/api/crime-types/{crime_type}", tags=["analytics"])
async def get_crime_type_detail(
        crime_type: str, sample: int = Query(8, ge=1, le=50),
        user: auth.User = Depends(requires(auth.ANALYTICS_READ))):
    """Everything the dashboard needs to drill into one crime type.

    Backs the click-through on the crime distribution chart: selecting a slice
    should answer "so what is actually in that slice?" without a round trip per
    panel.
    """
    result = _require_analysis()
    records = [r for r in result.fir_records
               if (r.crime_type.value if r.crime_type else "other") == crime_type]
    if not records:
        raise HTTPException(404, f"No FIRs classified as '{crime_type}'")

    total = result.total_firs_processed or 1
    severities = [r.severity_score or 0.0 for r in records]
    severity_distribution = Counter(_severity_band(s) for s in severities)

    districts = Counter(r.district for r in records)
    stations = Counter(f"{r.police_station} ({r.district})" for r in records)
    monthly = Counter(r.date_filed.strftime("%Y-%m") for r in records)
    sections = Counter(s for r in records for s in r.ipc_sections)
    methods = Counter(r.modus_operandi.approach_method for r in records
                      if r.modus_operandi and r.modus_operandi.approach_method)
    weapons = Counter(r.modus_operandi.weapon_used for r in records
                      if r.modus_operandi and r.modus_operandi.weapon_used)
    times = Counter(r.modus_operandi.time_of_day for r in records
                    if r.modus_operandi and r.modus_operandi.time_of_day)

    numbers = {r.fir_number for r in records}
    offenders = [
        {
            "name": o.name,
            "aliases": o.aliases,
            "risk_level": o.risk_level.value,
            "linked_firs_in_type": sorted(numbers & set(o.linked_firs)),
            "total_incidents": o.total_incidents,
            "districts": o.districts,
        }
        for o in result.repeat_offenders if crime_type in o.crime_types
    ]
    offenders.sort(key=lambda o: -len(o["linked_firs_in_type"]))

    networks = [
        {"name": n["name"], "fir_count": n["fir_count"],
         "districts": n["districts"], "risk_level": n["risk_level"],
         "matching_firs": sorted(numbers & set(n["fir_numbers"]))}
        for n in networks_cache if numbers & set(n["fir_numbers"])
    ]

    top_severity = sorted(records, key=lambda r: -(r.severity_score or 0))[:sample]
    show_pii = user.can(auth.FIR_READ_PII)
    if not show_pii:
        offenders = [auth.redact_offender({**o, "fir_count": o["total_incidents"]})
                     for o in offenders]
    return {
        "pii_redacted": not show_pii,
        "crime_type": crime_type,
        "label": crime_type.replace("_", " "),
        "total": len(records),
        "share_percent": round(len(records) / total * 100, 1),
        "avg_severity": round(sum(severities) / len(severities), 1),
        "max_severity": round(max(severities), 1),
        "severity_distribution": {band: severity_distribution.get(band, 0)
                                  for band in ("critical", "high", "medium", "low")},
        "accused_count": sum(len(r.accused) for r in records),
        "victim_count": sum(len(r.victims) for r in records),
        "date_range": {"start": str(min(r.date_filed for r in records)),
                       "end": str(max(r.date_filed for r in records))},
        "districts": [{"name": k, "count": v} for k, v in districts.most_common()],
        "stations": [{"name": k, "count": v} for k, v in stations.most_common(8)],
        "monthly_trend": dict(sorted(monthly.items())),
        "ipc_sections": [{"section": k, "count": v} for k, v in sections.most_common(10)],
        "modus_operandi": [{"method": k, "count": v} for k, v in methods.most_common(6)],
        "weapons": [{"weapon": k, "count": v} for k, v in weapons.most_common(6)],
        "time_of_day": dict(times.most_common()),
        "repeat_offenders": offenders[:10],
        "networks": networks,
        "top_firs": [_fir_payload(r) if show_pii else auth.redact_fir(_fir_payload(r))
                     for r in top_severity],
    }


# ── Conversational + reporting ─────────────────────────────────────────────


def _llm_status() -> dict:
    """Which engine will answer, and why."""
    info = llm_client.describe()
    if info["configured"]:
        return {"source": info["provider"], "model": info["model"],
                "engine": "llm"}
    if watsonx_configured():
        return {"source": "IBM watsonx.ai", "model": os.getenv(
            "WATSONX_MODEL", "ibm/granite-3-8b-instruct"), "engine": "watsonx"}
    return {"source": "rule-based analysis", "model": None, "engine": "analysis"}


async def _report_metadata(result: AnalysisResult) -> dict:
    return {
        "total_firs": result.total_firs_processed,
        "crime_breakdown": await db.get_crime_breakdown(),
        "district_breakdown": await db.get_district_breakdown(),
        "repeat_offender_count": len(result.repeat_offenders),
        "districts": sorted({f.district for f in result.fir_records}),
        "patterns": [n["name"] for n in networks_cache],
        "stations_analysed": len(result.station_summaries),
    }


def _sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, default=str)}\n\n"


@app.post("/api/chat", response_model=ChatResponse, tags=["assistant"])
async def chat_endpoint(req: ChatRequest,
                        user: auth.User = Depends(requires(auth.ASSISTANT_USE))):
    """Answer a question about the corpus (buffered).

    The deterministic answer is computed first and handed to the model as
    grounding, so a model answer is constrained by the detection pipeline
    rather than free to invent offenders — and if no model is configured or the
    call fails, that same computed answer is returned instead of nothing.
    """
    result = _require_analysis()
    message = (req.message or "").strip()
    if not message:
        raise HTTPException(400, "message must not be empty")

    grounded = intel_qa.answer_question(message, result, networks_cache)
    facts = await get_analysis_context(result, networks_cache)
    status = _llm_status()
    response, source, model = grounded, "rule-based analysis", None

    if llm_client.is_configured():
        messages = llm_client.build_chat_messages(
            message, facts, grounded,
            history=[m.model_dump() for m in req.history])
        try:
            response = await llm_client.complete(messages, max_tokens=1200)
            source, model = status["source"], status["model"]
        except llm_client.LLMError as exc:
            print(f"LLM chat failed, using computed answer: {exc}")
            source = f"rule-based analysis ({status['source']} unavailable)"
    elif watsonx_configured():
        response = await chat_with_bob(message, facts, deterministic_answer=grounded)
        source, model = status["source"], status["model"]

    referenced = [f.fir_number for f in result.fir_records if f.fir_number in response]
    entities = [o.name for o in result.repeat_offenders if o.name in response]
    return ChatResponse(response=response, firs_referenced=referenced,
                        entities_referenced=entities, source=source, model=model)


@app.post("/api/chat/stream", tags=["assistant"])
async def chat_stream(req: ChatRequest,
                      user: auth.User = Depends(requires(auth.ASSISTANT_USE))):
    """Same as /api/chat, streamed token by token over SSE."""
    result = _require_analysis()
    message = (req.message or "").strip()
    if not message:
        raise HTTPException(400, "message must not be empty")

    grounded = intel_qa.answer_question(message, result, networks_cache)
    facts = await get_analysis_context(result, networks_cache)
    status = _llm_status()

    async def events():
        yield _sse("start", status)
        collected: list[str] = []

        if llm_client.is_configured():
            messages = llm_client.build_chat_messages(
                message, facts, grounded,
                history=[m.model_dump() for m in req.history])
            try:
                async for piece in llm_client.stream(messages, max_tokens=1200):
                    collected.append(piece)
                    yield _sse("delta", {"text": piece})
            except llm_client.LLMError as exc:
                # Fall back mid-stream rather than leaving the user with a
                # half-written answer and no explanation.
                collected.clear()
                yield _sse("fallback", {"reason": str(exc)[:300]})
                yield _sse("delta", {"text": grounded})
                collected.append(grounded)
        else:
            yield _sse("delta", {"text": grounded})
            collected.append(grounded)

        answer = "".join(collected)
        yield _sse("done", {
            "firs_referenced": [f.fir_number for f in result.fir_records
                                if f.fir_number in answer],
            "entities_referenced": [o.name for o in result.repeat_offenders
                                    if o.name in answer],
        })

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


@app.get("/api/report", tags=["assistant"])
async def generate_report(
        focus: str = Query("", max_length=400),
        user: auth.User = Depends(requires(auth.REPORT_GENERATE))):
    """Generate an intelligence report from the current analysis.

    Regenerated on every request — the corpus changes as FIRs are ingested, so
    a cached report goes stale the moment someone uploads a batch.
    """
    result = _require_analysis()
    grounded = intel_qa.build_report(result, networks_cache)
    metadata = await _report_metadata(result)
    status = _llm_status()
    report, source = grounded, "rule-based analysis"

    if llm_client.is_configured():
        try:
            report = await llm_client.complete(
                llm_client.build_report_messages(grounded, metadata, focus),
                max_tokens=3000, temperature=0.35)
            source = status["source"]
        except llm_client.LLMError as exc:
            print(f"LLM report failed, using computed report: {exc}")
            source = f"rule-based analysis ({status['source']} unavailable)"
    elif watsonx_configured():
        report = await generate_intelligence_report(
            metadata, deterministic_report=grounded)
        source = status["source"]

    return {
        "report": report,
        "analysis": grounded,
        "metadata": metadata,
        "focus": focus,
        "source": source,
        "model": status["model"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "corpus_analysed_at": result.generated_at.isoformat(),
    }


@app.get("/api/report/stream", tags=["assistant"])
async def report_stream(
        focus: str = Query("", max_length=400),
        user: auth.User = Depends(requires(auth.REPORT_GENERATE))):
    """Stream the intelligence report as the model writes it."""
    result = _require_analysis()
    grounded = intel_qa.build_report(result, networks_cache)
    metadata = await _report_metadata(result)
    status = _llm_status()

    async def events():
        yield _sse("start", {**status, "metadata": metadata, "focus": focus,
                             "generated_at": datetime.now(timezone.utc).isoformat()})
        if llm_client.is_configured():
            try:
                async for piece in llm_client.stream(
                    llm_client.build_report_messages(grounded, metadata, focus),
                    max_tokens=3000, temperature=0.35,
                ):
                    yield _sse("delta", {"text": piece})
            except llm_client.LLMError as exc:
                yield _sse("fallback", {"reason": str(exc)[:300]})
                yield _sse("delta", {"text": grounded})
        else:
            yield _sse("delta", {"text": grounded})
        yield _sse("done", {"analysis": grounded})

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


@app.post("/api/upload-firs", tags=["firs"])
async def upload_firs(file: UploadFile = File(...),
                      user: auth.User = Depends(requires(auth.FIR_INGEST))):
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
