import re
import json
from models import (
    AccusedProfile, VictimProfile, LocationInfo, ModusOperandi, Entity
)


DISTRICTS_UP = {
    "Lucknow", "Kanpur", "Agra", "Varanasi", "Gorakhpur", "Meerut",
    "Prayagraj", "Ghaziabad", "Noida", "Bareilly", "Moradabad",
    "Aligarh", "Jhansi", "Mathura", "Firozabad", "Saharanpur",
    "Muzaffarnagar", "Bijnor", "Rampur", "Shahjahanpur", "Budaun",
    "Etawah", "Mainpuri", "Farrukhabad", "Kannauj", "Unnao",
    "Hardoi", "Sitapur", "Lakhimpur Kheri", "Bahraich", "Shravasti",
    "Balrampur", "Gonda", "Basti", "Sant Kabir Nagar", "Maharajganj",
    "Deoria", "Kushinagar", "Azamgarh", "Mau", "Ballia", "Jaunpur",
    "Ghazipur", "Chandauli", "Mirzapur", "Sonbhadra", "Bhadohi",
    "Sultanpur", "Amethi", "Pratapgarh", "Kaushambi", "Fatehpur",
    "Banda", "Chitrakoot", "Hamirpur", "Mahoba", "Lalitpur",
}

CRIME_KEYWORDS = {
    "robbery": ["snatched", "robbed", "looted", "snatching", "robbery", "loot"],
    "burglary": ["broke into", "break-in", "burgled", "burglary", "gas cutter", "cutting the lock"],
    "fraud": ["fraud", "cheated", "scam", "phishing", "OTP", "KYC"],
    "murder": ["murdered", "killed", "dead body", "stab wounds", "death"],
    "drug_offense": ["ganja", "heroin", "smack", "MDMA", "NDPS", "brown sugar", "drug"],
    "kidnapping": ["kidnapped", "abducted", "missing", "did not return"],
    "extortion": ["extortion", "protection money", "threatening", "demanded money"],
    "cybercrime": ["cyberstalking", "fake profile", "identity theft", "hacking"],
    "assault": ["assaulted", "beaten", "attacked", "fractures", "injuries"],
    "arson": ["set on fire", "arson", "burnt", "inflammable"],
}

IPC_PATTERN = re.compile(
    r'(?:Sections?|Sec\.?|U/[Ss])\s*:?\s*([\d]+(?:[A-Z])?(?:\s*[,/&]\s*[\d]+(?:[A-Z])?)*)'
    r'(?:\s+(?:IPC|BNS|IT Act|NDPS Act|Arms Act|POCSO)[\w\s]*)?',
    re.IGNORECASE
)

PERSON_PATTERN = re.compile(
    r'(?:(?:Shri|Smt\.?|Dr\.?|Mr\.?|Mrs\.?)\s+)?'
    r'([A-Z][a-z]+(?:\s+(?:alias\s+)?[A-Z][a-z]+){1,4})'
    r'(?:\s*(?:alias|a\.k\.a\.?|@)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*))?'
    r'(?:,?\s*age\s*(?:approximately\s*)?(\d{1,3})\s*(?:years?)?)?'
    r'(?:,?\s*([MFTO]|male|female))?'
    r'(?:,?\s*(?:S/o|D/o|W/o|H/o)\s+(?:(?:Late\s+)?(?:Shri|Smt\.?)\s+)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*))?'
    r'(?:,?\s*R/o\s+(.+?)(?=\.|,\s*(?:age|S/o|D/o|The|who|He|She|\d)))?',
    re.IGNORECASE
)

PHONE_PATTERN = re.compile(r'(?:\+91[-\s]?)?[6-9]\d{9}')
IMEI_PATTERN = re.compile(r'IMEI:\s*(\d{15})')
VEHICLE_PATTERN = re.compile(
    r'(?:UP[-\s]?\d{2}\s*[A-Z]{1,2}\s*\d{4})|'
    r'(?:(?:black|white|red|blue|grey|silver)\s+(?:Pulsar|Honda|Maruti|Hyundai|Alto|Activa|Eeco|Creta|Bullet|Splendor)\s*[\w\s]*)',
    re.IGNORECASE
)
VALUE_PATTERN = re.compile(r'Rs\.?\s*([\d,]+(?:\.\d{2})?)\s*(?:lakh|crore)?', re.IGNORECASE)


#: A proper name: capitalised tokens. Patterns built on this must NOT be
#: compiled with ``re.IGNORECASE`` — that makes ``[A-Z][a-z]+`` match lowercase
#: words, so "Accused identified as Bablu" yields the name "identified as
#: Bablu". Keyword prefixes get scoped ``(?i:...)`` groups instead.
_NAME = r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3}"

#: Constructs that actually *name* someone. Matching on bare trigger words
#: instead pulls in narrative nouns — "The accused persons fled towards
#: Charbagh railway station" would yield an accused called "Charbagh".
_ACCUSED_TRIGGER = re.compile(
    r"(?i:"
    r"identified\s+(?:(?:(?!\bas\b)[^,.]){0,45}\s)?as\b"
    r"|known\s+(?:(?:(?!\bas\b)[^,.]){0,30}\s)?as\b"
    r"|claiming\s+to\s+be"
    r"|identified\s*:"
    r"|(?:accused|arrested|apprehended|detained|suspects?|wanted)\s*:"
    r"|arrested\s+(?=[A-Z(])"
    r"|apprehended\s+(?=[A-Z(])"
    r"|named\s+(?=[A-Z])"
    r"|suspects?\s+(?:one\s+)?(?=[A-Z])"
    r")"
    r"\s*[:\-]?\s*(?i:one\s+|the\s+)?"
)

#: A comma segment opening with one of these describes the previous person
#: rather than introducing a new one.
_ATTRIBUTE_SEGMENT = re.compile(
    r"^\s*(?i:age[ds]?\b|approximately\b|s/o\b|d/o\b|w/o\b|h/o\b|r/o\b"
    r"|resident\b|residing\b|with\b|who\b|whose\b|a\b|an\b|the\b|and\s+the\b"
    r"|alias\b|aka\b|both\b|all\b|others?\b|unidentified\b|prior\b)"
)

_AGE_IN_SEGMENT = re.compile(r"(?i:age[ds]?)\s*(?:approximately\s*)?(\d{1,3})")

#: Numbered list markers used for multiple accused: "(1) X, age 28, (2) Y".
_LIST_MARKER = re.compile(r"\(\s*\d+\s*\)")

#: Words that look like names but never are, in FIR prose.
_NOT_A_NAME = {
    "the", "one", "two", "three", "this", "that", "he", "she", "they",
    "shri", "smt", "sri", "station", "house", "officer", "investigation",
    "sections", "section", "total", "complainant", "district", "police",
    "hospitalized", "post", "mortem", "forensic", "motive", "victim",
    "deceased", "unknown", "accused", "arrested", "identified", "suspect",
    "sub", "inspector", "constable", "court", "magistrate", "fir",
}

_PERSON_IN_CLAUSE = re.compile(
    rf"(?P<name>{_NAME})"
    rf"(?:\s+(?i:alias|aka|a\.k\.a\.?|@)\s+(?P<alias>{_NAME}))?"
    rf"(?:,?\s*(?i:age)\s*(?i:approximately\s*)?(?P<age>\d{{1,3}}))?"
)


def _is_plausible_name(name: str) -> bool:
    tokens = [t for t in name.split() if t]
    if not tokens:
        return False
    if any(t.lower() in _NOT_A_NAME for t in tokens):
        return False
    # "... (arrested in FIR/2024/MR/014, Meerut)" must not yield an accused
    # called Meerut. Places are never people.
    if name in DISTRICTS_UP or name.title() in DISTRICTS_UP:
        return False
    return "PS" not in tokens


def _attribute_near(text: str, name: str, pattern: str) -> str | None:
    """Pull an attribute that appears shortly after a person's name."""
    match = re.search(rf"{re.escape(name)}[^.]{{0,120}}?{pattern}", text)
    return match.group(1).strip() if match else None


def extract_accused(text: str) -> list[AccusedProfile]:
    """Extract accused persons from FIR narrative text.

    Works clause-first: locate the fragment introducing the accused, then parse
    each comma/"and"-separated person inside it. The previous implementation
    matched a name immediately after the trigger word and stopped, so only the
    first of several named accused was ever captured.
    """
    accused_list: list[AccusedProfile] = []
    seen: set[str] = set()

    def record(name: str, alias: str | None, age: int | None) -> None:
        name = name.strip().strip("'\"")
        if not _is_plausible_name(name) or name.lower() in seen:
            return
        seen.add(name.lower())
        aliases = []
        if alias:
            alias = alias.strip().strip("'\"")
            if _is_plausible_name(alias) and alias.lower() != name.lower():
                aliases.append(alias)
        accused_list.append(AccusedProfile(
            name=name,
            aliases=aliases,
            age=age,
            father_name=_attribute_near(
                text, name,
                rf"(?i:s/o|son\s+of)\s+(?:(?i:late\s+)?(?i:shri|smt\.?)\s+)?({_NAME})"),
            address=_attribute_near(text, name, r"(?i:r/o)\s+([^,.]+)"),
            id_marks=[m for m in [_attribute_near(
                text, name, r"((?i:scar|tattoo|birthmark)[^,.]+)")] if m],
        ))

    def parse_chunk(chunk: str) -> bool:
        """Parse one person plus the attribute segments that follow them.

        Returns whether a person was found, so callers can stop walking a
        comma-separated run once it stops naming people.
        """
        segments = chunk.split(",")
        match = _PERSON_IN_CLAUSE.match(segments[0].strip().lstrip("'\""))
        if not match:
            return False
        age = match.group("age")
        age = int(age) if age and age.isdigit() else None
        # Walk the following comma segments only while they describe this
        # person; the first non-attribute segment belongs to someone else.
        for segment in segments[1:]:
            if not _ATTRIBUTE_SEGMENT.match(segment):
                break
            if age is None:
                found = _AGE_IN_SEGMENT.search(segment)
                if found:
                    age = int(found.group(1))
        before = len(accused_list)
        record(match.group("name"), match.group("alias"), age)
        return len(accused_list) > before

    for trigger in _ACCUSED_TRIGGER.finditer(text):
        rest = text[trigger.end():]
        end = re.search(r"\.\s+[A-Z]|\bSections?\b|\bSec\.|$", rest)
        clause = rest[:end.start()] if end else rest[:250]

        if _LIST_MARKER.search(clause):
            # "(1) Guddu alias Guddu Khan, age 28, (2) Sunil Yadav, age 31"
            for chunk in _LIST_MARKER.split(clause):
                parse_chunk(chunk.strip())
        else:
            # "Bablu alias Bhura, Sunny alias Sonu" — commas separate people
            # until one of them starts an attribute run.
            parse_chunk(clause)
            for chunk in re.split(r",|\band\b|;|—|--", clause)[1:]:
                chunk = chunk.strip()
                if _ATTRIBUTE_SEGMENT.match(chunk) or not parse_chunk(chunk):
                    break

    return accused_list


#: Honorifics that also disclose gender.
_GENDER_BY_HONORIFIC = {"shri": "Male", "sri": "Male", "smt": "Female"}

_COMPLAINANT = re.compile(
    rf"(?i:complainant)\s*[:\-]?\s*"
    rf"(?P<honorific>(?i:Shri|Sri|Smt\.?|Dr\.?|Mr\.?|Mrs\.?)\s+)?"
    rf"(?P<name>{_NAME})"
    rf"(?:,?\s*(?i:age)\s*(?P<age>\d{{1,3}}))?"
    rf"(?:[^.]*?(?i:r/o)\s+(?P<address>[^,.]+))?"
)

_OTHER_VICTIM = re.compile(
    rf"(?i:victim|injured|deceased)\s+"
    rf"(?:(?i:Shri|Sri|Smt\.?|Dr\.?)\s+)?"
    rf"(?P<name>{_NAME})"
    rf"(?:\s*\((?i:age)\s*(?P<age>\d{{1,3}})\)|,?\s*\((?P<age2>\d{{1,3}})\))?"
)


def extract_victims(text: str) -> list[VictimProfile]:
    """Extract the complainant and any separately named victims."""
    victims: list[VictimProfile] = []
    seen: set[str] = set()

    def add(name: str, age: str | None = None, gender: str | None = None,
            address: str | None = None) -> None:
        name = name.strip()
        if not _is_plausible_name(name) or name.lower() in seen:
            return
        seen.add(name.lower())
        victims.append(VictimProfile(
            name=name,
            age=int(age) if age and age.isdigit() else None,
            gender=gender,
            address=address.strip() if address else None,
        ))

    match = _COMPLAINANT.search(text)
    if match:
        honorific = (match.group("honorific") or "").strip().rstrip(".").lower()
        gender = _GENDER_BY_HONORIFIC.get(honorific)
        if gender is None:
            # Fall back to the relationship marker following the name.
            tail = text[match.end("name"):match.end("name") + 200]
            if re.search(r"(?i:\bW/o\b|\bD/o\b)", tail):
                gender = "Female"
            elif re.search(r"(?i:\bS/o\b)", tail):
                gender = "Male"
        add(match.group("name"), match.group("age"), gender, match.group("address"))

    for match in _OTHER_VICTIM.finditer(text):
        add(match.group("name"), match.group("age") or match.group("age2"))

    return victims


def extract_location(text: str, ps_name: str, district: str) -> LocationInfo:
    places = []

    near_matches = re.findall(r'near\s+(?:the\s+)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})', text)
    places.extend(near_matches)

    at_matches = re.findall(r'at\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\s+(?:market|area|road|chowk|ghat)', text, re.IGNORECASE)
    places.extend(at_matches)

    place_str = ", ".join(places[:3]) if places else ps_name

    lat, lon = _get_coords(district)

    return LocationInfo(
        place=place_str,
        district=district,
        state="Uttar Pradesh",
        latitude=lat,
        longitude=lon,
    )


def _get_coords(district: str) -> tuple[float | None, float | None]:
    coords = {
        "Lucknow": (26.8467, 80.9462),
        "Kanpur": (26.4499, 80.3319),
        "Agra": (27.1767, 78.0081),
        "Varanasi": (25.3176, 82.9739),
        "Gorakhpur": (26.7606, 83.3732),
        "Meerut": (28.9845, 77.7064),
        "Prayagraj": (25.4358, 81.8463),
    }
    return coords.get(district, (None, None))


def extract_modus_operandi(text: str) -> ModusOperandi:
    mo_keywords = []
    weapons = []
    approach = None
    time_of_day = None

    weapon_matches = re.findall(
        r'(?:knife|pistol|gun|rod|hockey stick|country-made|desi katta|acid|pepper spray|gas cutter)',
        text, re.IGNORECASE
    )
    weapons = list(set(weapon_matches))

    for category, keywords in CRIME_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in text.lower():
                mo_keywords.append(kw)

    time_match = re.search(r'at\s+(?:approximately\s+)?(\d{4})\s+hours', text)
    if time_match:
        hour = int(time_match.group(1)[:2])
        if hour < 6:
            time_of_day = "early morning"
        elif hour < 12:
            time_of_day = "morning"
        elif hour < 17:
            time_of_day = "afternoon"
        elif hour < 21:
            time_of_day = "evening"
        else:
            time_of_day = "night"

    approach_patterns = {
        "bike-borne snatching": r'motorcycle.*snatch|bike.*snatch',
        "shop burglary with gas cutter": r'gas cutter.*shop|shop.*gas cutter|cutting.*shutter',
        "phone scam / vishing": r'phone call.*claim|KYC.*expir|digital arrest',
        "armed robbery": r'armed|pistol|gunpoint|knife.*throat',
        "social media luring": r'social media.*befriend|instagram.*lur|snapchat',
        "extortion racket": r'protection money|extortion.*call|threatening.*call',
        "drug trafficking": r'drug.*supply|smuggl|Nepal.*border|supply chain',
    }
    for method, pattern in approach_patterns.items():
        if re.search(pattern, text, re.IGNORECASE):
            approach = method
            break

    description_parts = []
    if approach:
        description_parts.append(f"Method: {approach}")
    if weapons:
        description_parts.append(f"Weapons: {', '.join(weapons)}")
    if time_of_day:
        description_parts.append(f"Time: {time_of_day}")

    return ModusOperandi(
        description="; ".join(description_parts) if description_parts else "Standard",
        keywords=list(set(mo_keywords)),
        weapon_used=weapons[0] if weapons else None,
        time_of_day=time_of_day,
        approach_method=approach,
    )


def extract_ipc_sections(text: str) -> list[str]:
    sections = []
    section_block = re.search(r'Sections?:\s*(.+?)(?:\.|$)', text, re.IGNORECASE)
    if section_block:
        raw = section_block.group(1)
        parts = re.split(r'[,/&]\s*', raw)
        for part in parts:
            cleaned = part.strip().rstrip('.')
            if cleaned:
                sections.append(cleaned)

    act_matches = re.findall(
        r'(?:Sec\.?\s*)?(\d+(?:[A-Z])?(?:/\d+)?)\s+(NDPS Act|Arms Act|IT Act|POCSO)',
        text, re.IGNORECASE
    )
    for sec, act in act_matches:
        sections.append(f"{sec} {act}")

    return list(dict.fromkeys(sections))


def extract_phone_numbers(text: str) -> list[str]:
    """Indian mobile numbers, normalised to the 10-digit national number.

    The raw matches carry an optional "+91-" prefix, so the same number written
    two ways compared as two different numbers — which defeats the point of
    extracting them for cross-FIR correlation.
    """
    seen: dict[str, None] = {}
    for match in PHONE_PATTERN.finditer(text):
        seen.setdefault(re.sub(r"\D", "", match.group(0))[-10:], None)
    return list(seen)


def extract_vehicles(text: str) -> list[str]:
    return [m.group(0).strip() for m in VEHICLE_PATTERN.finditer(text)]


def extract_stolen_values(text: str) -> float:
    total = 0.0
    for match in VALUE_PATTERN.finditer(text):
        val_str = match.group(1).replace(",", "")
        try:
            val = float(val_str)
            context = text[max(0, match.start()-20):match.end()+20].lower()
            if "crore" in context:
                val *= 10_000_000
            elif "lakh" in context:
                val *= 100_000
            total += val
        except ValueError:
            pass
    return total


def compute_severity(crime_type: str, stolen_value: float, weapons: list[str],
                     victim_count: int) -> float:
    base_scores = {
        "murder": 95, "dacoity": 85, "kidnapping": 80, "sexual_offense": 85,
        "drug_offense": 75, "robbery": 70, "extortion": 65, "arson": 70,
        "assault": 60, "burglary": 55, "fraud": 50, "cybercrime": 45,
        "theft": 35, "rioting": 60, "other": 30,
    }
    score = base_scores.get(crime_type, 30)

    if stolen_value > 10_000_000:
        score += 15
    elif stolen_value > 1_000_000:
        score += 10
    elif stolen_value > 100_000:
        score += 5

    if weapons:
        score += 10

    if victim_count > 3:
        score += 5

    return min(score, 100)
