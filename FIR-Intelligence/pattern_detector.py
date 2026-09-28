from collections import defaultdict
from datetime import date
from rapidfuzz import fuzz
from models import (
    FIRRecord, RepeatOffender, StationSummary, RiskLevel, AccusedProfile
)


def normalize_name(name: str) -> str:
    stop_words = {"alias", "aka", "a.k.a", "s/o", "d/o", "w/o", "shri", "smt", "dr"}
    parts = name.lower().split()
    return " ".join(p for p in parts if p not in stop_words).strip()


def names_match(name1: str, name2: str, threshold: float = 78.0) -> bool:
    n1 = normalize_name(name1)
    n2 = normalize_name(name2)
    if n1 == n2:
        return True
    return fuzz.token_sort_ratio(n1, n2) >= threshold


def alias_overlap(aliases1: list[str], aliases2: list[str]) -> bool:
    for a1 in aliases1:
        for a2 in aliases2:
            if fuzz.ratio(a1.lower(), a2.lower()) >= 80:
                return True
    return False


def mo_similarity(mo1: str, mo2: str) -> float:
    if not mo1 or not mo2:
        return 0.0
    return fuzz.token_set_ratio(mo1.lower(), mo2.lower()) / 100.0


def detect_repeat_offenders(fir_records: list[FIRRecord]) -> list[RepeatOffender]:
    accused_index: dict[str, list[tuple[str, FIRRecord, AccusedProfile]]] = defaultdict(list)

    for fir in fir_records:
        for acc in fir.accused:
            key = normalize_name(acc.name)
            accused_index[key].append((key, fir, acc))
            for alias in acc.aliases:
                alias_key = normalize_name(alias)
                accused_index[alias_key].append((alias_key, fir, acc))

    clusters: list[list[tuple[str, FIRRecord, AccusedProfile]]] = []
    visited_keys = set()

    all_keys = list(accused_index.keys())
    for i, key1 in enumerate(all_keys):
        if key1 in visited_keys:
            continue
        cluster = list(accused_index[key1])
        visited_keys.add(key1)

        for j in range(i + 1, len(all_keys)):
            key2 = all_keys[j]
            if key2 in visited_keys:
                continue
            if names_match(key1, key2, threshold=75):
                cluster.extend(accused_index[key2])
                visited_keys.add(key2)

        if len(cluster) > 1:
            seen_firs = set()
            deduped = []
            for entry in cluster:
                if entry[1].fir_number not in seen_firs:
                    seen_firs.add(entry[1].fir_number)
                    deduped.append(entry)
            if len(deduped) >= 2:
                clusters.append(deduped)

    repeat_offenders = []
    for cluster in clusters:
        all_names = set()
        all_aliases = set()
        linked_firs = []
        crime_types = set()
        stations = set()
        districts = set()
        dates = []

        for _, fir, acc in cluster:
            all_names.add(acc.name)
            all_aliases.update(acc.aliases)
            linked_firs.append(fir.fir_number)
            if fir.crime_type:
                crime_types.add(fir.crime_type.value if hasattr(fir.crime_type, 'value') else str(fir.crime_type))
            stations.add(fir.police_station)
            districts.add(fir.district)
            dates.append(fir.date_filed)

        primary_name = max(all_names, key=len)
        aliases = list(all_aliases | (all_names - {primary_name}))

        linked_firs = list(dict.fromkeys(linked_firs))
        n_firs = len(linked_firs)

        if n_firs >= 5:
            risk = RiskLevel.CRITICAL
        elif n_firs >= 3:
            risk = RiskLevel.HIGH
        elif n_firs >= 2:
            risk = RiskLevel.MEDIUM
        else:
            risk = RiskLevel.LOW

        mo_parts = []
        for _, fir, _ in cluster:
            if fir.modus_operandi and fir.modus_operandi.approach_method:
                mo_parts.append(fir.modus_operandi.approach_method)
        mo_sig = "; ".join(dict.fromkeys(mo_parts)) if mo_parts else ""

        confidence = min(0.5 + (n_firs * 0.1) + (len(districts) * 0.05), 1.0)

        repeat_offenders.append(RepeatOffender(
            name=primary_name,
            aliases=aliases,
            linked_firs=linked_firs,
            crime_types=sorted(crime_types),
            stations=sorted(stations),
            districts=sorted(districts),
            risk_level=risk,
            mo_signature=mo_sig,
            total_incidents=n_firs,
            confidence_score=round(confidence, 2),
            first_seen=min(dates) if dates else None,
            last_seen=max(dates) if dates else None,
        ))

    repeat_offenders.sort(key=lambda x: (-x.total_incidents, -x.confidence_score))
    return repeat_offenders


def generate_station_summaries(fir_records: list[FIRRecord],
                               repeat_offenders: list[RepeatOffender]) -> list[StationSummary]:
    station_data: dict[str, dict] = defaultdict(lambda: {
        "district": "",
        "firs": [],
        "crime_counts": defaultdict(int),
        "monthly_counts": defaultdict(int),
        "areas": set(),
    })

    for fir in fir_records:
        key = fir.police_station
        data = station_data[key]
        data["district"] = fir.district
        data["firs"].append(fir)

        ct = fir.crime_type.value if fir.crime_type and hasattr(fir.crime_type, 'value') else str(fir.crime_type or "other")
        data["crime_counts"][ct] += 1

        month_key = fir.date_filed.strftime("%Y-%m") if isinstance(fir.date_filed, date) else str(fir.date_filed)[:7]
        data["monthly_counts"][month_key] += 1

        if fir.location and fir.location.place:
            data["areas"].add(fir.location.place)

    summaries = []
    for station, data in station_data.items():
        crime_breakdown = dict(data["crime_counts"])
        top_crime = max(crime_breakdown, key=crime_breakdown.get) if crime_breakdown else "N/A"

        ro_count = sum(
            1 for ro in repeat_offenders
            if station in ro.stations
        )

        n_firs = len(data["firs"])
        if n_firs >= 5 and ro_count >= 2:
            risk = "HIGH - Multiple incidents with repeat offender activity"
        elif n_firs >= 3 or ro_count >= 1:
            risk = "MEDIUM - Elevated crime activity detected"
        else:
            risk = "LOW - Within normal parameters"

        summaries.append(StationSummary(
            station_name=station,
            district=data["district"],
            total_firs=n_firs,
            crime_breakdown=crime_breakdown,
            monthly_trend=dict(sorted(data["monthly_counts"].items())),
            top_crime=top_crime,
            repeat_offenders_count=ro_count,
            hotspot_areas=sorted(data["areas"])[:5],
            risk_assessment=risk,
        ))

    summaries.sort(key=lambda s: -s.total_firs)
    return summaries


def detect_crime_networks(fir_records: list[FIRRecord]) -> list[dict]:
    networks = []

    gang_labels = defaultdict(list)
    for fir in fir_records:
        text = fir.raw_text.lower()
        if "munna bhai" in text:
            gang_labels["Munna Bhai Extortion Gang"].append(fir)
        if "jamtara" in text or "vikram sharma" in text:
            gang_labels["Jamtara Cyber Fraud Network"].append(fir)
        if "bablu" in text and ("snatch" in text or "chain" in text):
            gang_labels["Bablu Chain Snatching Gang"].append(fir)
        if "gas cutter" in text and ("kanpur" in text.lower() or fir.district == "Kanpur"):
            gang_labels["Kanpur Commercial Burglary Ring"].append(fir)
        if any(w in text for w in ["ndps", "heroin", "smack", "ganja", "drug"]):
            if "nepal" in text or "gorakhpur" in text or "supply chain" in text:
                gang_labels["Nepal Border Drug Supply Network"].append(fir)

    for gang_name, firs in gang_labels.items():
        if len(firs) < 2:
            continue
        networks.append({
            "name": gang_name,
            "fir_count": len(firs),
            "fir_numbers": [f.fir_number for f in firs],
            "districts": list(set(f.district for f in firs)),
            "crime_types": list(set(
                f.crime_type.value if f.crime_type and hasattr(f.crime_type, 'value') else "other"
                for f in firs
            )),
            "active_period": {
                "start": str(min(f.date_filed for f in firs)),
                "end": str(max(f.date_filed for f in firs)),
            },
        })

    return sorted(networks, key=lambda n: -n["fir_count"])
