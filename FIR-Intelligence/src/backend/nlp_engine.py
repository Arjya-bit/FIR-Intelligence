import json
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
from pattern_detector import (
    detect_repeat_offenders, generate_station_summaries, detect_crime_networks
)
from bob_client import classify_crime


DATA_DIR = Path(__file__).parent / "data"


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

    crime_type_str = await classify_crime(raw_text)
    try:
        crime_type = CrimeType(crime_type_str)
    except ValueError:
        crime_type = CrimeType.OTHER

    accused = extract_accused(raw_text)
    victims = extract_victims(raw_text)
    location = extract_location(raw_text, ps, district)
    mo = extract_modus_operandi(raw_text)
    ipc_sections = extract_ipc_sections(raw_text)

    weapons = []
    if mo.weapon_used:
        weapons.append(mo.weapon_used)
    stolen_value = extract_stolen_values(raw_text)

    severity = compute_severity(
        crime_type_str, stolen_value, weapons, len(victims)
    )

    summary_parts = [
        f"Crime: {crime_type.value.replace('_', ' ').title()}",
        f"Location: {location.place}, {district}",
    ]
    if accused:
        summary_parts.append(f"Accused: {', '.join(a.name for a in accused[:3])}")
    if mo.approach_method:
        summary_parts.append(f"MO: {mo.approach_method}")

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
        summary="; ".join(summary_parts),
    )


async def analyze_fir_batch(fir_data_list: list[dict]) -> AnalysisResult:
    fir_records = []
    for fir_data in fir_data_list:
        record = await process_single_fir(fir_data)
        fir_records.append(record)

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


async def get_analysis_context(result: AnalysisResult) -> str:
    lines = [
        f"Total FIRs: {result.total_firs_processed}",
        f"Repeat Offenders: {len(result.repeat_offenders)}",
        "",
        "Crime Breakdown:",
    ]

    crime_counts: dict[str, int] = {}
    for fir in result.fir_records:
        ct = fir.crime_type.value if fir.crime_type else "other"
        crime_counts[ct] = crime_counts.get(ct, 0) + 1
    for ct, count in sorted(crime_counts.items(), key=lambda x: -x[1]):
        lines.append(f"  {ct}: {count}")

    lines.append("\nRepeat Offenders:")
    for ro in result.repeat_offenders:
        lines.append(
            f"  {ro.name} (aliases: {', '.join(ro.aliases)}) - "
            f"{ro.total_incidents} FIRs across {', '.join(ro.districts)} - "
            f"Risk: {ro.risk_level.value} - Crimes: {', '.join(ro.crime_types)}"
        )

    networks = detect_crime_networks(result.fir_records)
    if networks:
        lines.append("\nIdentified Crime Networks:")
        for net in networks:
            lines.append(
                f"  {net['name']}: {net['fir_count']} FIRs across {', '.join(net['districts'])}"
            )

    lines.append("\nStation Summaries:")
    for ss in result.station_summaries:
        lines.append(
            f"  {ss.station_name} ({ss.district}): {ss.total_firs} FIRs, "
            f"Top crime: {ss.top_crime}, Risk: {ss.risk_assessment[:20]}"
        )

    return "\n".join(lines)
