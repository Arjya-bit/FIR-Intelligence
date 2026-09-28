"""Deterministic question answering and report writing over analysed FIRs.

Everything here is computed from the live :class:`AnalysisResult`. Nothing is
templated prose about findings — if the corpus holds no drug cases, the drug
question says so rather than describing a trafficking ring that is not there.

This matters beyond tidiness. The previous fallback returned a fixed narrative
naming specific offenders and FIR numbers whatever the data contained, so an
officer running the tool on a new district would have been handed confident,
fabricated intelligence. These answers degrade to "no records match" instead.
"""

from __future__ import annotations

import re
from collections import Counter

from models import AnalysisResult, RepeatOffender

_MAX_LIST = 8


def _crime_counts(result: AnalysisResult) -> Counter:
    return Counter(
        getattr(fir.crime_type, "value", "other") for fir in result.fir_records
    )


def _district_counts(result: AnalysisResult) -> Counter:
    return Counter(fir.district for fir in result.fir_records)


def _pretty(value: str) -> str:
    return value.replace("_", " ")


def _offender_line(offender: RepeatOffender) -> str:
    aliases = f" (alias {', '.join(offender.aliases[:3])})" if offender.aliases else ""
    return (
        f"- {offender.name}{aliases} — {offender.total_incidents} FIRs across "
        f"{', '.join(offender.districts)}; risk {offender.risk_level.value.upper()}, "
        f"match confidence {offender.confidence_score:.0%}. "
        f"FIRs: {', '.join(offender.linked_firs[:6])}"
    )


def _network_line(network: dict) -> str:
    members = network.get("key_members") or []
    return (
        f"- {network['name']} — {network['fir_count']} FIRs across "
        f"{', '.join(network['districts'])} "
        f"({network['active_period']['start']} to {network['active_period']['end']})."
        f"{' Members: ' + ', '.join(members[:4]) + '.' if members else ''}"
        f" Linked by: {', '.join(network.get('link_basis') or ['correlation'])}."
    )


# ── Intent handlers ────────────────────────────────────────────────────────


def _answer_offenders(result: AnalysisResult, _networks, _q) -> str | None:
    if not result.repeat_offenders:
        return ("No repeat offenders were identified in the current corpus of "
                f"{result.total_firs_processed} FIRs. An accused must appear in "
                "at least two distinct FIRs to be flagged.")
    top = result.repeat_offenders[:_MAX_LIST]
    lines = [f"{len(result.repeat_offenders)} repeat offenders identified "
             f"across {result.total_firs_processed} FIRs. Highest activity:", ""]
    lines += [_offender_line(o) for o in top]
    return "\n".join(lines)


def _answer_networks(_result: AnalysisResult, networks: list[dict], _q) -> str | None:
    if not networks:
        return ("No organised networks were detected. Networks require at least "
                "two FIRs linked by a shared offender identity or a distinctive "
                "shared modus operandi.")
    lines = [f"{len(networks)} organised crime networks detected:", ""]
    lines += [_network_line(n) for n in networks[:_MAX_LIST]]
    return "\n".join(lines)


def _answer_districts(result: AnalysisResult, _networks, _q) -> str | None:
    counts = _district_counts(result)
    if not counts:
        return "No district information is present in the current corpus."
    lines = ["District-wise caseload:", ""]
    for district, count in counts.most_common(_MAX_LIST):
        share = count / result.total_firs_processed * 100
        top_crime = Counter(
            getattr(f.crime_type, "value", "other")
            for f in result.fir_records if f.district == district
        ).most_common(1)
        lead = f" — mostly {_pretty(top_crime[0][0])}" if top_crime else ""
        lines.append(f"- {district}: {count} FIRs ({share:.0f}%){lead}")
    return "\n".join(lines)


def _answer_stations(result: AnalysisResult, _networks, _q) -> str | None:
    if not result.station_summaries:
        return "No station summaries are available for the current corpus."
    lines = ["Station-level analysis (highest caseload first):", ""]
    for station in result.station_summaries[:_MAX_LIST]:
        lines.append(
            f"- {station.station_name}, {station.district}: {station.total_firs} FIRs, "
            f"top offence {_pretty(station.top_crime)}, "
            f"{station.repeat_offenders_count} repeat offenders. "
            f"{station.risk_assessment}"
        )
    return "\n".join(lines)


def _answer_patterns(result: AnalysisResult, networks: list[dict], _q) -> str | None:
    counts = _crime_counts(result)
    if not counts:
        return "The current corpus contains no classified FIRs."
    lines = [f"Crime pattern summary over {result.total_firs_processed} FIRs:", ""]
    for crime, count in counts.most_common(_MAX_LIST):
        share = count / result.total_firs_processed * 100
        lines.append(f"- {_pretty(crime).title()}: {count} FIRs ({share:.0f}%)")

    mo_counts = Counter(
        fir.modus_operandi.approach_method for fir in result.fir_records
        if fir.modus_operandi and fir.modus_operandi.approach_method
    )
    if mo_counts:
        lines += ["", "Most frequent modus operandi:"]
        lines += [f"- {method}: {count} FIRs"
                  for method, count in mo_counts.most_common(5)]
    if networks:
        lines += ["", f"{len(networks)} organised networks span these offences; "
                      "ask about networks for the breakdown."]
    return "\n".join(lines)


def _answer_severity(result: AnalysisResult, _networks, _q) -> str | None:
    records = result.fir_records
    if not records:
        return "The current corpus is empty."
    buckets = Counter()
    for fir in records:
        score = fir.severity_score or 0
        buckets["critical" if score >= 80 else "high" if score >= 60
                else "medium" if score >= 40 else "low"] += 1
    worst = sorted(records, key=lambda f: -(f.severity_score or 0))[:5]
    lines = ["Severity distribution:", ""]
    lines += [f"- {level.title()}: {buckets.get(level, 0)}"
              for level in ("critical", "high", "medium", "low")]
    lines += ["", "Highest-severity FIRs:"]
    lines += [f"- {f.fir_number} ({_pretty(getattr(f.crime_type, 'value', 'other'))}, "
              f"{f.district}) — severity {f.severity_score:.0f}/100" for f in worst]
    return "\n".join(lines)


def _answer_named_entity(result: AnalysisResult, networks: list[dict], question: str) -> str | None:
    """Answer questions naming a specific person, FIR number, or district."""
    lowered = question.lower()

    fir_match = re.search(r"\b((?:fir[/\s-]*)?[a-z]{0,4}[/\d][\w/\-]*\d)\b", question, re.I)
    if fir_match:
        token = fir_match.group(1).strip().lower()
        for fir in result.fir_records:
            if token in fir.fir_number.lower() or fir.fir_number.lower() in token:
                accused = ", ".join(a.name for a in fir.accused) or "none recorded"
                mo = fir.modus_operandi.description if fir.modus_operandi else "n/a"
                return (
                    f"{fir.fir_number} — {_pretty(getattr(fir.crime_type, 'value', 'other'))}, "
                    f"filed {fir.date_filed} at {fir.police_station}, {fir.district}.\n"
                    f"Severity: {fir.severity_score:.0f}/100. "
                    f"Sections: {', '.join(fir.ipc_sections) or 'not recorded'}.\n"
                    f"Accused: {accused}.\nModus operandi: {mo}.\n\n{fir.summary}"
                )

    for offender in result.repeat_offenders:
        candidates = [offender.name, *offender.aliases]
        if any(c and c.lower() in lowered for c in candidates):
            return (
                f"{offender.name} — repeat offender profile\n\n"
                f"Risk level: {offender.risk_level.value.upper()}\n"
                f"Aliases: {', '.join(offender.aliases) or 'none recorded'}\n"
                f"Linked FIRs ({offender.total_incidents}): "
                f"{', '.join(offender.linked_firs)}\n"
                f"Districts: {', '.join(offender.districts)}\n"
                f"Stations: {', '.join(offender.stations)}\n"
                f"Offences: {', '.join(_pretty(c) for c in offender.crime_types)}\n"
                f"MO signature: {offender.mo_signature or 'not established'}\n"
                f"Match confidence: {offender.confidence_score:.0%} "
                f"(identity resolved by name, alias and locality correlation)\n"
                f"Active: {offender.first_seen} to {offender.last_seen}"
            )

    for network in networks:
        if network["name"].lower() in lowered:
            return _network_line(network).lstrip("- ")

    for district in _district_counts(result):
        if district.lower() in lowered:
            firs = [f for f in result.fir_records if f.district == district]
            crimes = Counter(getattr(f.crime_type, "value", "other") for f in firs)
            offenders = [o for o in result.repeat_offenders if district in o.districts]
            lines = [f"{district}: {len(firs)} FIRs.", "", "Offence breakdown:"]
            lines += [f"- {_pretty(c).title()}: {n}" for c, n in crimes.most_common(6)]
            if offenders:
                lines += ["", f"{len(offenders)} repeat offenders active here:"]
                lines += [_offender_line(o) for o in offenders[:5]]
            return "\n".join(lines)

    # A crime type named directly ("show me the drug cases")
    for crime in _crime_counts(result):
        if crime.replace("_", " ") in lowered or crime in lowered:
            firs = [f for f in result.fir_records
                    if getattr(f.crime_type, "value", "") == crime]
            lines = [f"{len(firs)} {_pretty(crime)} FIRs recorded.", ""]
            for fir in sorted(firs, key=lambda f: -(f.severity_score or 0))[:_MAX_LIST]:
                lines.append(
                    f"- {fir.fir_number} ({fir.district}, {fir.date_filed}) — "
                    f"severity {fir.severity_score:.0f}; "
                    f"{', '.join(a.name for a in fir.accused) or 'accused not named'}"
                )
            return "\n".join(lines)
    return None


_GREETINGS = {"hi", "hello", "hey", "yo", "hii", "helo", "namaste", "namaskar",
              "good morning", "good afternoon", "good evening", "greetings",
              "hi there", "hello there", "sup", "start"}
_THANKS = {"thanks", "thank you", "thanks a lot", "ty", "cheers", "great",
           "nice", "ok", "okay", "cool", "got it", "perfect", "good"}


def _answer_conversational(result: AnalysisResult, networks, question) -> str | None:
    """Reply to the thing actually said.

    Without this, "hi" fell through to the default branch and returned a
    statistics dump — which is exactly the canned-reply behaviour this module
    exists to avoid, just pointed at the wrong prompt.
    """
    text = (question or "").strip().lower().rstrip("!?. ")
    if not text:
        return None

    if text in _GREETINGS:
        districts = len(_district_counts(result))
        return (
            f"Hello. I have {result.total_firs_processed} FIRs loaded from "
            f"{districts} districts, with {len(result.repeat_offenders)} repeat "
            f"offenders and {len(networks)} networks identified.\n\n"
            "What would you like to look at? You can ask me about a district, a "
            "crime type, a named accused, a specific FIR number, or ask which "
            "cases are most urgent."
        )

    if text in _THANKS:
        return "Happy to help. Ask me anything else about the corpus."

    if text in {"bye", "goodbye", "exit", "quit"}:
        return "Closing. The analysis stays loaded if you come back."

    if any(phrase in text for phrase in
           ("what can you do", "who are you", "what are you", "help me",
            "how do you work", "what do you know", "capabilities", "/help")):
        return (
            "I answer questions about the FIR corpus currently loaded — "
            f"{result.total_firs_processed} records analysed by the NLP "
            "pipeline. I can:\n\n"
            "- Summarise crime patterns, trends and severity\n"
            "- Profile a named accused and list their linked FIRs\n"
            "- Explain an organised network and who is in it\n"
            "- Break down a district or a police station's caseload\n"
            "- Open a specific FIR by number\n\n"
            "Everything I say is computed from the analysed records — I will "
            "tell you when something is not in the data rather than guess."
        )
    return None


def _answer_unmatched(result: AnalysisResult, networks: list[dict], question: str) -> str:
    """Say plainly that the question was not understood, and offer next steps.

    Better than silently returning a statistics dump, which reads as though the
    question was answered when it was not.
    """
    counts = _crime_counts(result)
    districts = _district_counts(result)
    asked = (question or "").strip()
    preview = asked if len(asked) <= 90 else asked[:87] + "…"
    return (
        f'I could not match "{preview}" to anything in the analysed corpus.\n\n'
        f"What I currently hold: {result.total_firs_processed} FIRs across "
        f"{len(districts)} districts and {len(result.station_summaries)} "
        f"stations, {len(result.repeat_offenders)} repeat offenders and "
        f"{len(networks)} networks.\n\n"
        "Try naming one of these:\n"
        f"- a district, e.g. {', '.join(list(districts)[:3])}\n"
        f"- a crime type, e.g. {', '.join(_pretty(c) for c in list(counts)[:3])}\n"
        "- an accused person, an FIR number, or a police station\n"
        "- or ask about patterns, networks, severity or repeat offenders"
    )


#: Ordered intent table. Specific lookups run before broad summaries so
#: "who is Bablu" is not swallowed by the repeat-offender overview.
_INTENTS = [
    (None, _answer_conversational),
    (None, _answer_named_entity),
    (("repeat offender", "habitual", "serial", "who are the offenders",
      "wanted", "accused list"), _answer_offenders),
    (("network", "gang", "syndicate", "organised", "organized", "ring"),
     _answer_networks),
    (("station", "thana", "police station"), _answer_stations),
    (("district", "highest crime", "crime rate", "where is", "hotspot"),
     _answer_districts),
    (("severity", "serious", "worst", "critical", "priority"), _answer_severity),
    (("pattern", "trend", "top crime", "breakdown", "statistics", "summary",
      "overview", "common"), _answer_patterns),
]


def answer_question(question: str, result: AnalysisResult,
                    networks: list[dict] | None = None) -> str:
    """Answer an officer's question using only the analysed corpus."""
    networks = networks or []
    if not result or not result.fir_records:
        return "No FIRs have been analysed yet, so there is nothing to report."

    lowered = (question or "").lower()
    for keywords, handler in _INTENTS:
        if keywords is None or any(k in lowered for k in keywords):
            answer = handler(result, networks, question)
            if answer:
                return answer

    return _answer_unmatched(result, networks, question)


def build_report(result: AnalysisResult, networks: list[dict] | None = None) -> str:
    """Compose a crime intelligence report from the analysed corpus."""
    networks = networks or []
    if not result or not result.fir_records:
        return "No FIRs analysed — no intelligence report can be produced."

    crimes = _crime_counts(result)
    districts = _district_counts(result)
    total = result.total_firs_processed
    high_risk = [o for o in result.repeat_offenders
                 if o.risk_level.value in ("high", "critical")]
    cross_district = [o for o in result.repeat_offenders if len(o.districts) > 1]
    period = sorted(f.date_filed for f in result.fir_records)

    out: list[str] = [
        "UTTAR PRADESH POLICE — CRIME INTELLIGENCE REPORT",
        f"Corpus: {total} FIRs | {len(districts)} districts | "
        f"{len(result.station_summaries)} stations",
        f"Period covered: {period[0]} to {period[-1]}",
        f"Generated: {result.generated_at:%Y-%m-%d %H:%M}",
        "",
        "1. EXECUTIVE SUMMARY",
        f"Analysis of {total} FIRs identified {len(result.repeat_offenders)} repeat "
        f"offenders ({len(high_risk)} at high or critical risk) and "
        f"{len(networks)} organised networks. "
        f"{len(cross_district)} offenders operate across district boundaries, which "
        f"is the category least likely to be detected by single-station review.",
        "",
        "2. CRIME PATTERN ANALYSIS",
    ]
    for crime, count in crimes.most_common():
        out.append(f"   - {_pretty(crime).title()}: {count} FIRs "
                   f"({count / total * 100:.0f}%)")

    out += ["", "3. REPEAT OFFENDER ALERTS"]
    if result.repeat_offenders:
        out += [f"   {_offender_line(o)[2:]}" for o in result.repeat_offenders[:10]]
    else:
        out.append("   None flagged in this corpus.")

    out += ["", "4. ORGANISED NETWORKS"]
    if networks:
        out += [f"   {_network_line(n)[2:]}" for n in networks[:10]]
    else:
        out.append("   None detected in this corpus.")

    out += ["", "5. STATION-WISE TREND ANALYSIS"]
    for station in result.station_summaries[:10]:
        out.append(f"   - {station.station_name}, {station.district}: "
                   f"{station.total_firs} FIRs, top offence "
                   f"{_pretty(station.top_crime)}. {station.risk_assessment}")

    out += ["", "6. RECOMMENDED ACTIONS"]
    actions: list[str] = []
    if cross_district:
        actions.append(
            f"   - Constitute an inter-district task force: {len(cross_district)} "
            f"offenders span multiple districts "
            f"({', '.join(o.name for o in cross_district[:5])})."
        )
    for network in networks[:3]:
        actions.append(
            f"   - Prioritise '{network['name']}' — {network['fir_count']} linked "
            f"FIRs in {', '.join(network['districts'])}."
        )
    busiest = districts.most_common(1)
    if busiest:
        actions.append(f"   - Reinforce deployment in {busiest[0][0]} "
                       f"({busiest[0][1]} FIRs, highest caseload).")
    if high_risk:
        actions.append(f"   - Issue lookout circulars for {len(high_risk)} "
                       f"high/critical-risk offenders.")
    out += actions or ["   - No escalations indicated by the current corpus."]

    out += ["", "7. RISK ASSESSMENT"]
    for offender in high_risk[:5]:
        out.append(f"   {offender.risk_level.value.upper()}: {offender.name} — "
                   f"{offender.total_incidents} FIRs across "
                   f"{len(offender.districts)} districts")
    if not high_risk:
        out.append("   No offender meets the high-risk threshold in this corpus.")

    out += ["",
            "Note: findings are derived from automated NLP correlation of FIR text "
            "and require verification by the investigating officer before action."]
    return "\n".join(out)
