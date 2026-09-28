"""FIR ingestion pipeline: classify, extract entities, correlate."""

from __future__ import annotations

import asyncio
import json
import os
from datetime import date, datetime
from pathlib import Path

from models import (
    FIRRecord, CrimeType, AnalysisResult, AccusedProfile,
    VictimProfile, LocationInfo, ModusOperandi
)
from entity_extractor import (
    extract_accused, extract_victims, extract_location,
    extract_modus_operandi, extract_ipc_sections, compute_severity,
    extract_vehicles, extract_phone_numbers, extract_stolen_values,
)
from pattern_detector import detect_repeat_offenders, generate_station_summaries
from bob_client import classify_crime


DATA_DIR = Path(__file__).parent / "data"

#: Bound on concurrent classification calls. Sequential awaits made a
#: 100-FIR startup take 100 round trips to watsonx.ai; unbounded gather
#: trips the API rate limit.
CLASSIFY_CONCURRENCY = int(os.getenv("FIR_CLASSIFY_CONCURRENCY", "8"))


def load_mock_firs() -> list[dict]:
    fir_path = DATA_DIR / "mock_firs.json"
    with open(fir_path, "r", encoding="utf-8") as f:
        return json.load(f)


def parse_date(d) -> date:
    if isinstance(d, date):
        return d
    if isinstance(d, str):
        return datetime.strptime(d, "%Y-%m-%d").date()
    return date.today()


async def process_single_fir(fir_data: dict) -> FIRRecord:
    raw_text = fir_data.get("raw_text", "")
    ps = fir_data.get("police_station", "")
    district = fir_data.get("district", "")

    # Use pre-classified crime_type if present (NCRB data), else NLP classify
    crime_type_str = fir_data.get("crime_type") or await classify_crime(raw_text)
    try:
        crime_type = CrimeType(crime_type_str)
    except ValueError:
        crime_type = CrimeType.OTHER

    # Use pre-structured entities if present (NCRB data), else extract via NLP
    accused_raw = fir_data.get("accused")
    if accused_raw and isinstance(accused_raw, list) and accused_raw and isinstance(accused_raw[0], dict):
        accused = [AccusedProfile(**a) for a in accused_raw]
    else:
        accused = extract_accused(raw_text)

    victims_raw = fir_data.get("victims")
    if victims_raw and isinstance(victims_raw, list) and victims_raw and isinstance(victims_raw[0], dict):
        victims = [VictimProfile(**v) for v in victims_raw]
    else:
        victims = extract_victims(raw_text)

    loc_raw = fir_data.get("location")
    if loc_raw and isinstance(loc_raw, dict) and "place" in loc_raw:
        location = LocationInfo(**loc_raw)
    else:
        location = extract_location(raw_text, ps, district)

    mo_raw = fir_data.get("modus_operandi")
    if mo_raw and isinstance(mo_raw, dict) and "description" in mo_raw:
        mo = ModusOperandi(**mo_raw)
    else:
        mo = extract_modus_operandi(raw_text)

    ipc_sections = fir_data.get("ipc_sections") or extract_ipc_sections(raw_text)

    # Use pre-computed severity or compute from NLP
    severity = fir_data.get("severity_score")
    if severity is None:
        weapons = [mo.weapon_used] if mo.weapon_used else []
        stolen_value = extract_stolen_values(raw_text)
        severity = compute_severity(crime_type_str, stolen_value, weapons, len(victims))

    summary = fir_data.get("summary")
    if not summary:
        summary_parts = [
            f"Crime: {crime_type.value.replace('_', ' ').title()}",
            f"Location: {location.place}, {district}",
        ]
        if accused:
            summary_parts.append(f"Accused: {', '.join(a.name for a in accused[:3])}")
        if mo.approach_method:
            summary_parts.append(f"MO: {mo.approach_method}")
        summary = "; ".join(summary_parts)

    return FIRRecord(
        fir_number=fir_data.get("fir_number", ""),
        date_filed=parse_date(fir_data.get("date_filed", date.today())),
        police_station=ps,
        district=district,
        state=fir_data.get("state", "Uttar Pradesh"),
        raw_text=raw_text,
        crime_type=crime_type,
        ipc_sections=ipc_sections,
        accused=accused,
        victims=victims,
        location=location,
        modus_operandi=mo,
        severity_score=severity,
        summary=summary,
    )


async def analyze_fir_batch(fir_data_list: list[dict]) -> AnalysisResult:
    """Run the full pipeline over a batch of raw FIR dicts."""
    semaphore = asyncio.Semaphore(CLASSIFY_CONCURRENCY)

    async def process(fir_data: dict) -> FIRRecord:
        async with semaphore:
            return await process_single_fir(fir_data)

    fir_records = list(await asyncio.gather(*(process(d) for d in fir_data_list)))

    repeat_offenders = detect_repeat_offenders(fir_records)
    station_summaries = generate_station_summaries(fir_records, repeat_offenders)

    crime_trend: dict[str, dict[str, int]] = {}
    for fir in fir_records:
        month = fir.date_filed.strftime("%Y-%m") if isinstance(fir.date_filed, date) else str(fir.date_filed)[:7]
        ct = fir.crime_type.value if fir.crime_type else "other"
        if month not in crime_trend:
            crime_trend[month] = {}
        crime_trend[month][ct] = crime_trend[month].get(ct, 0) + 1

    entity_stats = {
        "total_accused": sum(len(f.accused) for f in fir_records),
        "total_victims": sum(len(f.victims) for f in fir_records),
        "unique_locations": len(set(
            f.location.place for f in fir_records if f.location
        )),
        "repeat_offenders": len(repeat_offenders),
        "total_ipc_sections": len(set(
            sec for f in fir_records for sec in f.ipc_sections
        )),
    }

    return AnalysisResult(
        total_firs_processed=len(fir_records),
        fir_records=fir_records,
        repeat_offenders=repeat_offenders,
        station_summaries=station_summaries,
        crime_trend=dict(sorted(crime_trend.items())),
        entity_stats=entity_stats,
    )


async def get_analysis_context(result: AnalysisResult,
                               networks: list[dict] | None = None,
                               max_items: int = 15) -> str:
    """A compact factual digest of the corpus, used to ground LLM prompts.

    ``networks`` is passed in by the caller because recomputing it here made
    every chat turn re-run the whole correlation pass.
    """
    districts: dict[str, int] = {}
    crime_counts: dict[str, int] = {}
    for fir in result.fir_records:
        ct = fir.crime_type.value if fir.crime_type else "other"
        crime_counts[ct] = crime_counts.get(ct, 0) + 1
        districts[fir.district] = districts.get(fir.district, 0) + 1

    lines = [
        f"Total FIRs analysed: {result.total_firs_processed}",
        f"Districts: {len(districts)} | Stations: {len(result.station_summaries)}",
        f"Repeat offenders flagged: {len(result.repeat_offenders)}",
        "",
        "Crime breakdown:",
    ]
    lines += [f"  {ct}: {count}"
              for ct, count in sorted(crime_counts.items(), key=lambda x: -x[1])]

    lines += ["", "District caseload:"]
    lines += [f"  {d}: {count}" for d, count in
              sorted(districts.items(), key=lambda x: -x[1])[:max_items]]

    if result.repeat_offenders:
        lines += ["", "Repeat offenders (most active first):"]
        for offender in result.repeat_offenders[:max_items]:
            aliases = f" (aliases: {', '.join(offender.aliases)})" if offender.aliases else ""
            lines.append(
                f"  {offender.name}{aliases} — {offender.total_incidents} FIRs "
                f"[{', '.join(offender.linked_firs[:6])}] across "
                f"{', '.join(offender.districts)}; risk {offender.risk_level.value}; "
                f"offences {', '.join(offender.crime_types)}"
            )

    if networks:
        lines += ["", "Identified crime networks:"]
        for net in networks[:max_items]:
            lines.append(
                f"  {net['name']}: {net['fir_count']} FIRs across "
                f"{', '.join(net['districts'])} "
                f"[{', '.join(net['fir_numbers'][:6])}]"
            )

    lines += ["", "Station summaries (busiest first):"]
    for station in result.station_summaries[:max_items]:
        lines.append(
            f"  {station.station_name} ({station.district}): "
            f"{station.total_firs} FIRs, top crime {station.top_crime}, "
            f"{station.repeat_offenders_count} repeat offenders"
        )

    return "\n".join(lines)
