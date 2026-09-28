"""Cross-FIR pattern detection: repeat offenders, station rollups, networks.

Identity resolution uses union-find so links are transitive: if FIR-1 names
"Bablu alias Bhura", FIR-2 names "Bhura" and FIR-3 names "Bablu Kumar", all
three collapse into one identity even though no single pairwise comparison
connects the first and last.

Fuzzy name matches alone are deliberately *not* enough to merge two identities.
Common Indian name pairs score high on token similarity ("Sunil Yadav" vs
"Sunny Yadav"), and in a policing context a false link is worse than a missed
one, so an approximate match must be corroborated by a shared alias, station,
district, or modus operandi before it is accepted.
"""

from __future__ import annotations

import os
import re
from collections import Counter, defaultdict
from datetime import date

from rapidfuzz import fuzz

from models import AccusedProfile, FIRRecord, RepeatOffender, RiskLevel, StationSummary

#: Token-similarity score above which two names are *candidates* for merging.
FUZZY_THRESHOLD = float(os.getenv("FIR_NAME_MATCH_THRESHOLD", "82"))

#: Alias strings must be at least this similar to be treated as the same alias.
ALIAS_THRESHOLD = 88.0

#: Honorifics and relationship markers that carry no identifying information.
_STOP_WORDS = {
    "alias", "aka", "a.k.a", "s/o", "d/o", "w/o", "h/o", "late",
    "shri", "sri", "smt", "smt.", "mr", "mrs", "dr", "md",
}

_PUNCT = re.compile(r"[^\w\s]")


def normalize_name(name: str) -> str:
    """Lowercase, strip honorifics/punctuation, collapse whitespace."""
    cleaned = _PUNCT.sub(" ", (name or "").lower())
    parts = [p for p in cleaned.split() if p and p not in _STOP_WORDS]
    return " ".join(parts)


def names_match(name1: str, name2: str, threshold: float = FUZZY_THRESHOLD) -> bool:
    """True when two names are the same or similar enough to be candidates."""
    n1, n2 = normalize_name(name1), normalize_name(name2)
    if not n1 or not n2:
        return False
    if n1 == n2:
        return True
    # A single token ("Bablu") should not fuzzy-match another single token;
    # short names are too collision-prone to link on similarity alone.
    if " " not in n1 and " " not in n2:
        return False
    return fuzz.token_sort_ratio(n1, n2) >= threshold


def alias_overlap(aliases1: list[str], aliases2: list[str]) -> bool:
    return any(
        fuzz.ratio(normalize_name(a1), normalize_name(a2)) >= ALIAS_THRESHOLD
        for a1 in aliases1 for a2 in aliases2
        if normalize_name(a1) and normalize_name(a2)
    )


def mo_similarity(mo1: str, mo2: str) -> float:
    if not mo1 or not mo2:
        return 0.0
    return fuzz.token_set_ratio(mo1.lower(), mo2.lower()) / 100.0


class _UnionFind:
    """Minimal disjoint-set with path compression."""

    def __init__(self) -> None:
        self._parent: dict[str, str] = {}

    def add(self, key: str) -> None:
        self._parent.setdefault(key, key)

    def find(self, key: str) -> str:
        self.add(key)
        root = key
        while self._parent[root] != root:
            root = self._parent[root]
        while self._parent[key] != root:  # path compression
            self._parent[key], key = root, self._parent[key]
        return root

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self._parent[rb] = ra

    def keys(self) -> list[str]:
        return list(self._parent)


class _Mention:
    """One accused named in one FIR.

    ``key`` is the normalised *recorded name* and is the only thing that can
    open an identity. Aliases are kept separately: nicknames like "Chhotu" or
    "Guddu" are shared by thousands of unrelated people, so treating one as an
    identifier chains every FIR in the corpus into a single bogus offender.
    """

    __slots__ = ("fir", "accused", "key", "alias_keys")

    def __init__(self, fir: FIRRecord, accused: AccusedProfile) -> None:
        self.fir = fir
        self.accused = accused
        self.key = normalize_name(accused.name)
        self.alias_keys = {k for k in (normalize_name(a) for a in accused.aliases) if k}


def _mo_text(fir: FIRRecord) -> str:
    mo = fir.modus_operandi
    if not mo:
        return ""
    return " ".join(filter(None, [mo.approach_method, mo.weapon_used, mo.description]))


def _corroborated(m1: _Mention, m2: _Mention) -> bool:
    """Is there independent evidence that two similar names are one person?

    Deliberately narrow. Modus operandi is *not* accepted here: FIR narratives
    for the same offence type read almost identically, so an MO match carries
    almost no identifying signal at the level of an individual.
    """
    if m1.accused.father_name and m1.accused.father_name == m2.accused.father_name:
        return True  # "S/o X" is the strongest identifier an FIR records
    if alias_overlap(m1.accused.aliases, m2.accused.aliases):
        return True
    if m1.fir.police_station == m2.fir.police_station:
        return True
    return m1.fir.district == m2.fir.district


def _build_identities(fir_records: list[FIRRecord]) -> dict[str, list[_Mention]]:
    """Group accused mentions into resolved identities.

    The union-find operates over *mentions*, not names, so an alias can join
    two mentions without becoming an identity of its own.
    """
    mentions = [_Mention(fir, acc) for fir in fir_records for acc in fir.accused]
    mentions = [m for m in mentions if m.key]  # drop honorific-only names
    uf = _UnionFind()
    ids = [str(i) for i in range(len(mentions))]
    for mention_id in ids:
        uf.add(mention_id)

    by_key: dict[str, list[int]] = defaultdict(list)
    for index, mention in enumerate(mentions):
        by_key[mention.key].append(index)

    def link(i: int, j: int) -> None:
        uf.union(ids[i], ids[j])

    # 1. Identical recorded names. A full name ("Chhote Lal") is specific
    #    enough to merge outright; a bare first name ("Bablu") is not, so it
    #    needs something else in common.
    for key, indexes in by_key.items():
        multi_token = " " in key
        for pos, i in enumerate(indexes):
            for j in indexes[pos + 1:]:
                if multi_token or _corroborated(mentions[i], mentions[j]):
                    link(i, j)

    # 2. Near-identical names, blocked on the first token so we compare only
    #    plausibly related pairs instead of every pair in the corpus.
    blocks: dict[str, list[str]] = defaultdict(list)
    for key in by_key:
        blocks[key.split()[0][:4]].append(key)
    for block in blocks.values():
        for pos, key1 in enumerate(sorted(block)):
            for key2 in sorted(block)[pos + 1:]:
                if not names_match(key1, key2):
                    continue
                for i in by_key[key1]:
                    for j in by_key[key2]:
                        if _corroborated(mentions[i], mentions[j]):
                            link(i, j)

    # 3. An alias recorded against one mention matching another's real name
    #    ("Bablu alias Bhura" in FIR-1, "Bhura" in FIR-2) — still corroborated,
    #    because common nicknames collide constantly.
    for index, mention in enumerate(mentions):
        for alias_key in mention.alias_keys:
            for other in by_key.get(alias_key, ()):
                if other != index and _corroborated(mention, mentions[other]):
                    link(index, other)

    identities: dict[str, list[_Mention]] = defaultdict(list)
    for index, mention in enumerate(mentions):
        identities[uf.find(ids[index])].append(mention)
    return identities


def _risk_for(n_firs: int, n_districts: int, severity: float) -> RiskLevel:
    if n_firs >= 5 or (n_firs >= 3 and n_districts >= 3) or severity >= 85:
        return RiskLevel.CRITICAL
    if n_firs >= 3 or (n_firs >= 2 and n_districts >= 2) or severity >= 70:
        return RiskLevel.HIGH
    if n_firs >= 2:
        return RiskLevel.MEDIUM
    return RiskLevel.LOW


def detect_repeat_offenders(fir_records: list[FIRRecord],
                            min_incidents: int = 2) -> list[RepeatOffender]:
    """Flag accused persons linked to ``min_incidents`` or more distinct FIRs."""
    offenders: list[RepeatOffender] = []

    for mentions in _build_identities(fir_records).values():
        # One person may appear twice in the same FIR; count distinct FIRs.
        by_fir: dict[str, _Mention] = {}
        for mention in mentions:
            by_fir.setdefault(mention.fir.fir_number, mention)
        if len(by_fir) < min_incidents:
            continue

        names: Counter[str] = Counter()
        aliases: set[str] = set()
        crime_types: set[str] = set()
        stations: set[str] = set()
        districts: set[str] = set()
        dates: list[date] = []
        severities: list[float] = []
        mo_parts: list[str] = []

        for mention in by_fir.values():
            names[mention.accused.name.strip()] += 1
            aliases.update(a.strip() for a in mention.accused.aliases if a.strip())
            fir = mention.fir
            if fir.crime_type:
                crime_types.add(getattr(fir.crime_type, "value", str(fir.crime_type)))
            stations.add(fir.police_station)
            districts.add(fir.district)
            dates.append(fir.date_filed)
            severities.append(fir.severity_score or 0.0)
            if fir.modus_operandi and fir.modus_operandi.approach_method:
                mo_parts.append(fir.modus_operandi.approach_method)

        # Most frequently recorded spelling wins; ties break on the longer form.
        primary_name = max(names, key=lambda n: (names[n], len(n)))
        n_firs = len(by_fir)
        avg_severity = sum(severities) / len(severities) if severities else 0.0

        # Confidence rises with corroborating evidence, not just volume.
        confidence = min(
            0.45
            + min(n_firs, 6) * 0.07
            + min(len(districts) - 1, 3) * 0.05
            + (0.08 if aliases else 0.0)
            + (0.05 if len(set(mo_parts)) == 1 and mo_parts else 0.0),
            0.99,
        )

        offenders.append(RepeatOffender(
            name=primary_name,
            aliases=sorted(aliases | (set(names) - {primary_name})),
            linked_firs=sorted(by_fir),
            crime_types=sorted(crime_types),
            stations=sorted(stations),
            districts=sorted(districts),
            risk_level=_risk_for(n_firs, len(districts), avg_severity),
            mo_signature="; ".join(dict.fromkeys(mo_parts)),
            total_incidents=n_firs,
            confidence_score=round(confidence, 2),
            first_seen=min(dates) if dates else None,
            last_seen=max(dates) if dates else None,
        ))

    offenders.sort(key=lambda o: (-o.total_incidents, -o.confidence_score, o.name))
    return offenders


def generate_station_summaries(fir_records: list[FIRRecord],
                               repeat_offenders: list[RepeatOffender]) -> list[StationSummary]:
    """Per-station crime rollup with hotspots and a risk assessment."""
    station_data: dict[tuple[str, str], dict] = defaultdict(lambda: {
        "firs": [],
        "crime_counts": Counter(),
        "monthly_counts": Counter(),
        "areas": Counter(),
    })

    for fir in fir_records:
        # Station names such as "Kotwali PS" repeat across districts, so the
        # district has to be part of the key or their counts get merged.
        data = station_data[(fir.police_station, fir.district)]
        data["firs"].append(fir)
        data["crime_counts"][
            getattr(fir.crime_type, "value", str(fir.crime_type or "other"))
        ] += 1
        month = (fir.date_filed.strftime("%Y-%m")
                 if isinstance(fir.date_filed, date) else str(fir.date_filed)[:7])
        data["monthly_counts"][month] += 1
        if fir.location and fir.location.place:
            data["areas"][fir.location.place] += 1

    summaries = []
    for (station, district), data in station_data.items():
        crime_breakdown = dict(data["crime_counts"].most_common())
        top_crime = next(iter(crime_breakdown), "N/A")
        n_firs = len(data["firs"])

        ro_count = sum(
            1 for ro in repeat_offenders
            if station in ro.stations and district in ro.districts
        )
        critical_ro = sum(
            1 for ro in repeat_offenders
            if station in ro.stations and district in ro.districts
            and ro.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL)
        )
        avg_severity = sum(f.severity_score or 0 for f in data["firs"]) / max(n_firs, 1)

        if critical_ro >= 2 or (n_firs >= 8 and ro_count >= 2):
            risk = ("HIGH — sustained caseload with active high-risk repeat "
                    f"offenders ({critical_ro} flagged)")
        elif n_firs >= 5 or ro_count >= 1 or avg_severity >= 70:
            risk = (f"MEDIUM — elevated activity ({n_firs} FIRs, "
                    f"avg severity {avg_severity:.0f}/100)")
        else:
            risk = "LOW — within normal parameters"

        summaries.append(StationSummary(
            station_name=station,
            district=district,
            total_firs=n_firs,
            crime_breakdown=crime_breakdown,
            monthly_trend=dict(sorted(data["monthly_counts"].items())),
            top_crime=top_crime,
            repeat_offenders_count=ro_count,
            hotspot_areas=[area for area, _ in data["areas"].most_common(5)],
            risk_assessment=risk,
        ))

    summaries.sort(key=lambda s: (-s.total_firs, s.station_name))
    return summaries


# ── Crime networks ─────────────────────────────────────────────────────────

#: Curated labels for networks UP Police already track by name. Purely
#: cosmetic: detection is structural, these only supply a familiar title when
#: a detected component matches a known signature.
KNOWN_NETWORK_LABELS: list[tuple[str, tuple[str, ...]]] = [
    ("Jamtara Cyber Fraud Network", ("jamtara",)),
    ("Munna Bhai Extortion Gang", ("munna bhai",)),
    ("Nepal Border Drug Supply Network", ("nepal",)),
    ("Kanpur Commercial Burglary Ring", ("gas cutter",)),
    ("Bablu Chain Snatching Gang", ("bablu", "snatch")),
]


def _label_for(firs: list[FIRRecord], members: list[str], crime_types: list[str],
               districts: list[str]) -> str:
    """Prefer a known gang name, else build a descriptive one from the data."""
    texts = [f.raw_text.lower() for f in firs]
    # The keyword has to characterise the component, not merely appear once
    # somewhere in it — otherwise a single stray mention names the network.
    majority = max(2, len(texts) // 2)
    for label, keywords in KNOWN_NETWORK_LABELS:
        if all(sum(kw in t for t in texts) >= majority for kw in keywords):
            return label

    lead = members[0] if members else "Unattributed"
    crime = (crime_types[0] if crime_types else "mixed").replace("_", " ")
    where = districts[0] if len(districts) == 1 else f"{len(districts)} districts"
    return f"{lead} — {crime} network ({where})"


#: Edge weights for the co-offending graph. A shared identity is the strongest
#: signal; locality and offence type corroborate it.
_W_SHARED_OFFENDER = 6
_W_SHARED_MO = 3
_W_SAME_DISTRICT = 2
_W_SAME_CRIME = 1

#: An edge must clear this to be considered at all, which keeps pairs that
#: merely happen to share a district and offence type out of the graph.
_MIN_EDGE_WEIGHT = 5


def _network_edges(fir_records: list[FIRRecord],
                   identities: dict[str, list[_Mention]]) -> tuple[list, dict, dict]:
    """Weighted co-offending edges plus per-FIR member and basis annotations."""
    by_number = {fir.fir_number: fir for fir in fir_records}
    weights: dict[tuple[str, str], int] = defaultdict(int)
    bases: dict[tuple[str, str], set[str]] = defaultdict(set)
    members_of: dict[str, set[str]] = defaultdict(set)

    def add(a: str, b: str, weight: int, basis: str) -> None:
        key = (a, b) if a < b else (b, a)
        weights[key] += weight
        bases[key].add(basis)

    for mentions in identities.values():
        numbers = sorted({m.fir.fir_number for m in mentions})
        if len(numbers) < 2:
            continue
        display = max((m.accused.name for m in mentions), key=len)
        for number in numbers:
            members_of[number].add(display)
        for i, a in enumerate(numbers):
            for b in numbers[i + 1:]:
                add(a, b, _W_SHARED_OFFENDER, "shared offender")

    # A distinctive MO repeated within one district and offence type is
    # evidence in its own right, even when no accused was ever named.
    generic_mo = {"", "standard", "none", "unknown", "other"}
    mo_groups: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    for fir in fir_records:
        mo = fir.modus_operandi
        approach = (mo.approach_method or "").strip().lower() if mo else ""
        if approach and approach not in generic_mo:
            crime = getattr(fir.crime_type, "value", "other")
            mo_groups[(fir.district, crime, approach)].append(fir.fir_number)
    for numbers in mo_groups.values():
        if len(numbers) < 3:  # two FIRs sharing an MO in a district is chance
            continue
        for i, a in enumerate(sorted(numbers)):
            for b in sorted(numbers)[i + 1:]:
                add(a, b, _W_SHARED_MO, "shared modus operandi")

    for (a, b) in list(weights):
        fir_a, fir_b = by_number[a], by_number[b]
        if fir_a.district == fir_b.district:
            weights[(a, b)] += _W_SAME_DISTRICT
        if fir_a.crime_type == fir_b.crime_type:
            weights[(a, b)] += _W_SAME_CRIME

    edges = sorted(
        ((w, pair) for pair, w in weights.items() if w >= _MIN_EDGE_WEIGHT),
        key=lambda item: (-item[0], item[1]),
    )
    return edges, members_of, bases


def detect_crime_networks(fir_records: list[FIRRecord], min_size: int = 2,
                          max_size: int | None = None) -> list[dict]:
    """Group FIRs into organised crime networks.

    FIRs form a weighted co-offending graph: a shared resolved offender is the
    strongest edge, a distinctive shared modus operandi a weaker one, with the
    same district and offence type adding corroboration. Clusters are grown by
    merging the strongest edges first and refusing any merge that would push a
    cluster past ``max_size``.

    Plain connected components are deliberately *not* used. Indian FIRs record
    a small pool of very common names, so single-linkage over name matches
    chains almost every record into one 70-FIR "network" that means nothing.
    Capped, strength-ordered agglomeration keeps clusters tight and lets a
    genuine ring stay separate from an unrelated one next door.
    """
    by_number = {fir.fir_number: fir for fir in fir_records}
    if max_size is None:
        # Past roughly a sixth of the corpus a cluster describes a crime
        # *pattern* rather than an organisation, so stop growing it.
        max_size = max(8, len(by_number) // 6)

    uf = _UnionFind()
    for number in by_number:
        uf.add(number)

    identities = _build_identities(fir_records)
    edges, members_of, edge_bases = _network_edges(fir_records, identities)

    sizes: Counter = Counter({number: 1 for number in by_number})
    basis_of: dict[str, set[str]] = defaultdict(set)

    for _weight, (a, b) in edges:
        root_a, root_b = uf.find(a), uf.find(b)
        if root_a == root_b:
            continue
        if sizes[root_a] + sizes[root_b] > max_size:
            continue
        merged = sizes.pop(root_a) + sizes.pop(root_b)
        uf.union(a, b)
        sizes[uf.find(a)] = merged
        for number in (a, b):
            basis_of[number] |= edge_bases[(a, b) if a < b else (b, a)]

    components: dict[str, list[str]] = defaultdict(list)
    for number in by_number:
        components[uf.find(number)].append(number)

    networks = []
    for numbers in components.values():
        if len(numbers) < min_size:
            continue
        firs = [by_number[n] for n in sorted(numbers)]
        # Rank members by how many of the cluster's FIRs name them, so the
        # network is labelled after its most active figure rather than
        # whoever happens to sort first.
        member_counts = Counter(
            name for n in numbers for name in members_of.get(n, ())
        )
        members = [name for name, _ in
                   sorted(member_counts.items(), key=lambda kv: (-kv[1], kv[0]))]
        crime_types = [c for c, _ in Counter(
            getattr(f.crime_type, "value", "other") for f in firs
        ).most_common()]
        districts = [d for d, _ in Counter(f.district for f in firs).most_common()]
        mo_signature = "; ".join(dict.fromkeys(
            f.modus_operandi.approach_method for f in firs
            if f.modus_operandi and f.modus_operandi.approach_method
        ))
        avg_severity = sum(f.severity_score or 0 for f in firs) / len(firs)
        start, end = min(f.date_filed for f in firs), max(f.date_filed for f in firs)
        name = _label_for(firs, members, crime_types, districts)

        networks.append({
            "name": name,
            "fir_count": len(firs),
            "fir_numbers": [f.fir_number for f in firs],
            "districts": districts,
            "crime_types": crime_types,
            "key_members": members,
            "link_basis": sorted({b for n in numbers for b in basis_of.get(n, ())}),
            "mo_signature": mo_signature,
            "avg_severity": round(avg_severity, 1),
            "risk_level": _risk_for(len(firs), len(districts), avg_severity).value,
            "active_period": {"start": str(start), "end": str(end)},
            "intelligence_brief": (
                f"{len(firs)} FIRs linked across {', '.join(districts)} between "
                f"{start} and {end}. Predominant offence: "
                f"{crime_types[0].replace('_', ' ') if crime_types else 'mixed'}"
                f"{'. Key members: ' + ', '.join(members[:5]) if members else ''}"
                f"{'. Shared MO: ' + mo_signature if mo_signature else ''}."
            ),
        })

    networks.sort(key=lambda n: (-n["fir_count"], -n["avg_severity"], n["name"]))
    return networks
