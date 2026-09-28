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


def extract_accused(text: str) -> list[AccusedProfile]:
    accused_list = []
    accused_section = re.findall(
        r'(?:accused|arrested|suspected|identified as|apprehended)[:\s]+(.+?)(?:\.|Sections|Sec\.)',
        text, re.IGNORECASE | re.DOTALL
    )

    names_found = set()

    patterns = [
        re.compile(
            r'(?:accused[^.]*?|arrested[^.]*?|identified as[^.]*?)'
            r'(?:(?:\d\)\s*)|(?:\(\d\)\s*))?'
            r'([A-Z][a-z]+(?:\s+(?:alias\s+)?[A-Z][a-z]+){0,3})'
            r'(?:\s+alias\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*))?'
            r'(?:,?\s*age\s*(?:approximately\s*)?(\d{1,3}))?',
            re.IGNORECASE
        ),
        re.compile(
            r'(?:\(\d\)|(?:^|\n)\s*\d\))\s*'
            r'([A-Z][a-z]+(?:\s+(?:alias\s+)?[A-Z][a-z]+){0,3})'
            r'(?:\s+alias\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*))?'
            r'(?:,?\s*age\s*(?:approximately\s*)?(\d{1,3}))?',
            re.IGNORECASE
        ),
        re.compile(
            r"'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)'\s*(?:who|is|was|has|had)",
            re.IGNORECASE
        ),
    ]

    for pattern in patterns:
        for match in pattern.finditer(text):
            name = match.group(1).strip() if match.group(1) else ""
            if not name or name.lower() in {"the", "one", "two", "three", "this", "that"}:
                continue

            skip_words = {"Shri", "Smt", "Station", "House", "Officer", "Investigation",
                          "Sections", "Total", "Complainant", "District", "Police"}
            if any(w in name for w in skip_words):
                continue

            name_key = name.lower().split("alias")[0].strip()
            if name_key in names_found:
                continue
            names_found.add(name_key)

            alias = match.group(2).strip() if len(match.groups()) > 1 and match.group(2) else ""
            age_str = match.group(3) if len(match.groups()) > 2 and match.group(3) else None
            age = int(age_str) if age_str and age_str.isdigit() else None

            aliases = [alias] if alias else []
            if "alias" in name:
                parts = re.split(r'\s+alias\s+', name, flags=re.IGNORECASE)
                name = parts[0].strip()
                if len(parts) > 1:
                    aliases.append(parts[1].strip())

            id_marks = []
            scar_match = re.search(
                rf'{re.escape(name)}.*?(scar[^,.]+|tattoo[^,.]+|birthmark[^,.]+)',
                text, re.IGNORECASE
            )
            if scar_match:
                id_marks.append(scar_match.group(1).strip())

            addr_match = re.search(
                rf'{re.escape(name)}[^.]*?R/o\s+([^,.]+)',
                text, re.IGNORECASE
            )
            address = addr_match.group(1).strip() if addr_match else None

            father_match = re.search(
                rf'{re.escape(name)}[^.]*?S/o\s+(?:(?:Late\s+)?(?:Shri|Smt\.?)\s+)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',
                text, re.IGNORECASE
            )
            father = father_match.group(1).strip() if father_match else None

            accused_list.append(AccusedProfile(
                name=name,
                aliases=aliases,
                age=age,
                father_name=father,
                address=address,
                id_marks=id_marks,
            ))

    return accused_list


def extract_victims(text: str) -> list[VictimProfile]:
    victims = []
    complainant_match = re.search(
        r'Complainant:\s*(?:Shri|Smt\.?|Dr\.?)\s+'
        r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,4})'
        r'(?:,?\s*age\s*(\d{1,3}))?'
        r'(?:.*?([MFTO]|male|female))?'
        r'(?:.*?R/o\s+([^,.]+))?',
        text, re.IGNORECASE
    )
    if complainant_match:
        name = complainant_match.group(1).strip()
        age_str = complainant_match.group(2)
        addr = complainant_match.group(4)

        gender = None
        if "Smt." in text[:text.find(name) + len(name)] or "W/o" in text[:text.find(name) + 200]:
            gender = "Female"
        elif "Shri" in text[:text.find(name) + len(name)] or "S/o" in text[:text.find(name) + 200]:
            gender = "Male"

        victims.append(VictimProfile(
            name=name,
            age=int(age_str) if age_str else None,
            gender=gender,
            address=addr.strip() if addr else None,
        ))

    victim_matches = re.finditer(
        r'(?:victim|injured|deceased)\s+(?:Shri|Smt\.?|Dr\.?)?\s*'
        r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})'
        r'(?:\s*\(age\s*(\d+)\))?',
        text, re.IGNORECASE
    )
    for m in victim_matches:
        victims.append(VictimProfile(
            name=m.group(1).strip(),
            age=int(m.group(2)) if m.group(2) else None,
        ))

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
    return PHONE_PATTERN.findall(text)


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
