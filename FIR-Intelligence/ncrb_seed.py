"""
NCRB-Based FIR Data Generator
------------------------------
Generates realistic FIR records based on actual NCRB (National Crime Records Bureau)
crime statistics for Uttar Pradesh districts. Crime type distributions, district
hotspots, and modus operandi patterns are derived from:
  - NCRB "Crime in India" 2022 & 2023 reports
  - UP Police annual crime review data
  - District-wise IPC crime head statistics

This module produces 100 FIRs covering all major IPC crime categories with
realistic accused/victim profiles, MO patterns, and cross-district networks.
"""

import json
import random
from datetime import date, timedelta
from pathlib import Path

random.seed(42)

# ── NCRB Crime Distribution for UP (per 100 FIRs, approximate) ──
# Source: NCRB Crime in India 2022, Table 1A.2 - UP state totals
CRIME_DISTRIBUTION = {
    "theft": 18,
    "robbery": 8,
    "burglary": 10,
    "assault": 12,
    "murder": 5,
    "fraud": 8,
    "cybercrime": 7,
    "drug_offense": 5,
    "kidnapping": 8,
    "extortion": 5,
    "dacoity": 3,
    "arson": 2,
    "sexual_offense": 4,
    "rioting": 3,
    "other": 2,
}

# ── NCRB District-wise crime rates (top districts in UP) ──
# Source: NCRB Crime in India 2022, District-wise IPC crimes
DISTRICTS = {
    "Lucknow": {"weight": 15, "stations": [
        "Hazratganj PS", "Charbagh PS", "Gomti Nagar PS", "Aliganj PS",
        "Husainabad PS", "Kaiserbagh PS", "Sarojini Nagar PS", "Chinhat PS",
        "Gudamba PS", "Thakurganj PS", "Wazirganj PS", "Mahila PS",
    ]},
    "Kanpur Nagar": {"weight": 12, "stations": [
        "Kotwali Nagar PS", "Swaroop Nagar PS", "Gwaltoli PS", "Chakeri PS",
        "Barra PS", "Kalyanpur PS", "Govind Nagar PS", "Naubasta PS",
        "Panki PS", "Kidwai Nagar PS",
    ]},
    "Agra": {"weight": 10, "stations": [
        "Civil Lines PS", "Tajganj PS", "Sadar PS", "Hariparwat PS",
        "Shahganj PS", "Etmadpur PS", "Trans Yamuna PS", "Fatehpur Sikri PS",
    ]},
    "Varanasi": {"weight": 9, "stations": [
        "Lanka PS", "Bhelupur PS", "Sigra PS", "Chetganj PS",
        "Cantt PS", "Dashashwamedh PS", "Adampur PS", "Shivpur PS",
    ]},
    "Gorakhpur": {"weight": 8, "stations": [
        "Rapti Nagar PS", "Kotwali PS", "Cantt PS", "Medical College PS",
        "Shahmaroof PS", "Pipraich PS", "Campierganj PS",
    ]},
    "Prayagraj": {"weight": 8, "stations": [
        "Civil Lines PS", "Kydganj PS", "George Town PS", "Kareli PS",
        "Jhunsi PS", "Naini PS", "Dhoomanganj PS", "Kotwali PS",
    ]},
    "Ghaziabad": {"weight": 8, "stations": [
        "Kotwali PS", "Indirapuram PS", "Kavi Nagar PS", "Sahibabad PS",
        "Loni PS", "Muradnagar PS", "Masuri PS", "Wave City PS",
    ]},
    "Meerut": {"weight": 7, "stations": [
        "Kotwali PS", "Medical College PS", "Civil Lines PS", "Lisari Gate PS",
        "Partapur PS", "Brahmpuri PS", "Shastri Nagar PS",
    ]},
    "Bareilly": {"weight": 6, "stations": [
        "Kotwali PS", "Cantt PS", "Baradari PS", "Izzatnagar PS",
        "Faridpur PS", "Prem Nagar PS",
    ]},
    "Aligarh": {"weight": 5, "stations": [
        "Kotwali PS", "Civil Lines PS", "Sasni Gate PS", "Gandhi Park PS",
        "Bannadevi PS", "Quarsi PS",
    ]},
    "Moradabad": {"weight": 4, "stations": [
        "Kotwali PS", "Civil Lines PS", "Katghar PS", "Pakbara PS",
    ]},
    "Jhansi": {"weight": 4, "stations": [
        "Kotwali PS", "Sipri PS", "Civil Lines PS", "Nawabad PS",
    ]},
    "Mathura": {"weight": 4, "stations": [
        "Kotwali PS", "Highway PS", "Refinery PS", "Govardhan PS",
    ]},
}

# ── Realistic Names Pool (Hindi/UP context) ──
MALE_NAMES = [
    "Rajesh Kumar", "Sunil Yadav", "Mohd Saleem", "Ravi Shankar Pandey",
    "Amit Singh", "Bablu", "Guddu Khan", "Pappu Yadav", "Shivam Tiwari",
    "Arun Verma", "Deepak Chauhan", "Mohd Irfan", "Sanjay Dubey",
    "Vikram Sharma", "Rohit Mishra", "Pradeep Gupta", "Ramesh Chandra",
    "Munna", "Chhote Lal", "Shakeel Ahmed", "Vinod Kashyap",
    "Akhilesh Yadav", "Manoj Verma", "Suresh Pal", "Rakesh Dixit",
    "Anil Agarwal", "Devendra Pratap", "Firoz Khan", "Wasim Baig",
    "Santosh Mishra", "Pankaj Srivastava", "Yogesh Tripathi",
    "Raju", "Sunny", "Rinku Pandey", "Sonu Tiwari", "Kallu",
    "Bittu", "Pintu Pal", "Dinesh Rajput", "Harish Chandra",
    "Mohd Aslam", "Nadeem Ahmad", "Ajay Pratap Singh", "Balram Yadav",
    "Ghanshyam Tiwari", "Jai Prakash", "Kamal Kishore", "Lakshman Prasad",
    "Nand Kishore Sharma", "Om Prakash Verma", "Prem Chand",
    "Qamar Jahan", "Ram Naresh", "Satish Kumar", "Trilok Nath",
    "Umesh Chandra Pandey", "Vijay Bahadur", "Waris Ali",
]

FEMALE_NAMES = [
    "Sunita Devi", "Priya Tiwari", "Neha Agarwal", "Asha Srivastava",
    "Kamla Devi", "Rani Devi", "Meera Sahu", "Pooja Singh",
    "Rekha Yadav", "Savitri Devi", "Anita Kumari", "Geeta Sharma",
    "Kavita Mishra", "Laxmi Devi", "Manju Pandey", "Nirmala Gupta",
    "Parvati Devi", "Ritu Singh", "Sushma Verma", "Tulsi Devi",
]

ALIASES = [
    "Bhura", "Kalu", "Chhotu", "Guddu", "Pappu", "Bittu", "Pintu",
    "Munna", "Babloo", "Tinku", "Raju", "Chintu", "Firu", "Deepu",
    "Sonu", "Monu", "Golu", "Bunty", "Lucky", "Raja",
]

# ── Combinatorial name pool for unaffiliated (non-network) persons ──
# The curated lists above are small on purpose: they name the members of the
# seeded criminal networks. Drawing *every* accused from them would make
# unrelated FIRs collide on name constantly, and the pattern detector would
# then report those coincidences as cross-district "networks". A first x
# surname product gives ~2,800 distinct names so a collision is rare enough to
# be genuine signal.
FIRST_NAMES_M = [
    "Aakash", "Abhishek", "Ajeet", "Alok", "Aman", "Ambrish", "Anurag",
    "Ashok", "Avinash", "Badri", "Bhupendra", "Brijesh", "Chandan",
    "Dhirendra", "Dilip", "Gaurav", "Girish", "Hemant", "Hriday", "Indrajeet",
    "Jitendra", "Kailash", "Karan", "Keshav", "Kuldeep", "Lalit", "Mahendra",
    "Mukesh", "Naveen", "Nitin", "Parvez", "Prashant", "Rajeev", "Ranjeet",
    "Rupesh", "Sachin", "Shailendra", "Shashank", "Shyam", "Sudhir", "Tarun",
    "Udai", "Vikas", "Vishal", "Yashpal", "Zafar", "Imran", "Rizwan",
    "Salman", "Tabrez",
]
FIRST_NAMES_F = [
    "Aarti", "Alka", "Anjali", "Archana", "Babita", "Chanda", "Deepti",
    "Ekta", "Gayatri", "Hemlata", "Indu", "Jyoti", "Kiran", "Madhu",
    "Nandini", "Preeti", "Radha", "Sarita", "Shalini", "Urmila", "Vandana",
    "Yashoda", "Nazma", "Rukhsana", "Shabnam",
]
SURNAMES = [
    "Agnihotri", "Awasthi", "Bajpai", "Bhargava", "Chaturvedi", "Dwivedi",
    "Gaur", "Goswami", "Kushwaha", "Lodhi", "Maurya", "Nigam", "Pathak",
    "Prajapati", "Rastogi", "Saxena", "Shukla", "Sengar", "Trivedi",
    "Upadhyay", "Vaish", "Bhadauria", "Chauhan", "Katiyar", "Nishad",
    "Rawat", "Sahu", "Solanki", "Ansari", "Qureshi", "Siddiqui", "Usmani",
]

ADDRESSES_BY_DISTRICT = {
    "Lucknow": ["Gomti Nagar", "Indira Nagar", "Aliganj", "Rajajipuram", "Alambagh",
                 "Thakurganj", "Aminabad", "Charbagh", "Kaiserbagh", "Husainabad"],
    "Kanpur Nagar": ["Civil Lines", "Swaroop Nagar", "Kidwai Nagar", "Barra", "Kakadeo",
                      "Collectorganj", "Birhana Road", "Panki", "Govind Nagar"],
    "Agra": ["Sadar Bazaar", "Shahganj", "Lohamandi", "Fatehpur Sikri Road",
             "Taj Ganj", "Sanjay Place", "Kamla Nagar"],
    "Varanasi": ["Assi Ghat", "Lanka", "Sigra", "Godowlia", "Madanpura",
                 "Ramnagar", "Cantt", "Dashashwamedh"],
    "Gorakhpur": ["Medical College Road", "Basharatpur", "Golghar", "Rapti Nagar",
                  "Sahjanwa", "Pipraich"],
    "Prayagraj": ["George Town", "Civil Lines", "Teliarganj", "Naini",
                  "Jhunsi", "Kydganj", "Sangam area"],
    "Ghaziabad": ["Indirapuram", "Vaishali", "Kaushambi", "Raj Nagar Extension",
                  "Sahibabad", "Loni", "Crossing Republik"],
    "Meerut": ["Shastri Nagar", "Lisari Gate", "Sadar Bazaar", "Cantt",
               "Partapur", "Abu Lane"],
    "Bareilly": ["Izzatnagar", "Baradari", "Prem Nagar", "Subhash Nagar",
                 "Rajendra Nagar", "Cantt"],
    "Aligarh": ["Sasni Gate", "Gandhi Park", "Bannadevi", "Quarsi",
                "Ramghat Road", "Dodhpur"],
    "Moradabad": ["Katghar", "Pakbara", "Civil Lines", "Mughalpura",
                  "Buddhi Vihar"],
    "Jhansi": ["Sipri Bazaar", "Civil Lines", "Nawabad", "Gwalior Road",
               "Talpura"],
    "Mathura": ["Govardhan", "Vrindavan", "Krishna Nagar", "Highway Colony",
                "Chhata"],
}

# ── IPC Sections by Crime Type (from NCRB classification) ──
IPC_SECTIONS = {
    "theft": ["379 IPC", "380 IPC", "381 IPC", "382 IPC"],
    "robbery": ["392 IPC", "393 IPC", "394 IPC", "397 IPC", "356 IPC"],
    "burglary": ["457 IPC", "380 IPC", "411 IPC", "454 IPC", "459 IPC"],
    "assault": ["323 IPC", "324 IPC", "325 IPC", "326 IPC", "307 IPC", "308 IPC"],
    "murder": ["302 IPC", "304 IPC", "394 IPC", "201 IPC", "120B IPC"],
    "fraud": ["420 IPC", "406 IPC", "467 IPC", "468 IPC", "471 IPC", "120B IPC"],
    "cybercrime": ["66C IT Act", "66D IT Act", "67 IT Act", "420 IPC", "419 IPC"],
    "drug_offense": ["20 NDPS Act", "21 NDPS Act", "22 NDPS Act", "29 NDPS Act"],
    "kidnapping": ["363 IPC", "364 IPC", "366 IPC", "366A IPC", "8/12 POCSO"],
    "extortion": ["384 IPC", "385 IPC", "506 IPC", "120B IPC", "387 IPC"],
    "dacoity": ["395 IPC", "396 IPC", "397 IPC", "398 IPC", "399 IPC", "25 Arms Act"],
    "arson": ["435 IPC", "436 IPC", "427 IPC", "120B IPC"],
    "sexual_offense": ["376 IPC", "354 IPC", "354A IPC", "509 IPC", "5/6 POCSO"],
    "rioting": ["147 IPC", "148 IPC", "149 IPC", "323 IPC", "427 IPC", "153A IPC"],
    "other": ["188 IPC", "294 IPC", "504 IPC", "506 IPC"],
}

# ── MO Templates by Crime Type ──
MO_TEMPLATES = {
    "theft": [
        "The accused {accused} stole {item} worth Rs. {value} from the complainant's {location}. The theft was discovered on {discovery}. {extra}",
        "Mobile phone theft near {area} market. The accused snatched the phone from the victim's hand while they were walking. IMEI: {imei}.",
        "Theft of two-wheeler ({vehicle}) from outside {place}. The lock was broken using a master key. Vehicle value Rs. {value}.",
        "Pickpocketing incident at {area} bus stand. Wallet containing Rs. {cash} cash, Aadhaar card, and ATM cards stolen from complainant's pocket.",
    ],
    "robbery": [
        "At approximately {time} hours, two bike-borne persons intercepted the complainant near {area}. One accused put a knife to the throat while the other snatched {items}. Total loss Rs. {value}. Accused fled towards {direction}.",
        "Armed robbery at {place}. Three persons armed with {weapon} entered the establishment and looted Rs. {value} in cash and {items}. Complainant sustained {injury}.",
        "Chain snatching incident near {area}. The accused on a {vehicle} grabbed the gold chain ({weight} grams, value Rs. {value}) and sped away. {witness}.",
    ],
    "burglary": [
        "Between {time1} and {time2} hours, unknown persons broke into {place} at {area} market by {method}. Stolen: {items}. Total loss Rs. {value}. CCTV DVR also taken. {vehicle_seen}.",
        "Residential burglary at {address}. Entry through {entry_point}. Stolen items: gold jewelry ({weight}g), cash Rs. {cash}, electronics. Family was away. {evidence}.",
    ],
    "assault": [
        "On {date} at {time} hours, the complainant was attacked by {accused} near {area} using {weapon}. Victim sustained {injuries}. Motive: {motive}. Victim hospitalized at {hospital}.",
        "Group assault by {count} persons at {area}. Attackers used iron rods and hockey sticks. Victim {victim} suffered {injuries}. Accused identified as members of {gang}.",
    ],
    "murder": [
        "The deceased {victim} (age {age}) was found dead at {location} with {cause}. Time of death estimated between {time1} and {time2} hours. Suspect: {accused}, motive: {motive}. Forensic evidence collected.",
        "Shooting incident at {area}. The victim was shot {times} times with a {weapon}. Accused {accused} had prior enmity over {motive}. Multiple witnesses. Post-mortem at {hospital}.",
    ],
    "fraud": [
        "The complainant was defrauded of Rs. {value} through {method}. The accused {accused} gained trust by {approach} and siphoned funds through {channels}. Money trail leads to {destination}.",
        "Real estate fraud: Complainant paid Rs. {value} for property at {area} which turned out to be disputed. Accused {accused} produced forged documents. Investigation reveals {count} similar victims.",
    ],
    "cybercrime": [
        "Cyber fraud: Complainant received call from person claiming to be {impersonation}. Under threat of {threat}, complainant transferred Rs. {value} to accounts specified by accused. Money trail traced to {destination}.",
        "Online fraud through {platform}. The accused created fake {profile_type} and lured {count} victims. Total fraud amount Rs. {value}. IP addresses traced to {location}.",
        "Digital arrest scam: Complainant was shown fake {document} on video call. Under extreme duress, transferred Rs. {value} from fixed deposit. Same MO as Jamtara network.",
    ],
    "drug_offense": [
        "During raid at {location}, police recovered {drug_type} ({quantity}) valued at Rs. {value}, along with {other_items}. Arrested: {accused}. Part of supply chain from {source}.",
        "Suo motu FIR: Vehicle intercepted at {area}. Recovered {drug_type} ({quantity}) concealed in {hiding}. Arrested: {accused}. Investigation reveals connection to {network}.",
    ],
    "kidnapping": [
        "Missing person report: {victim} (age {age}) did not return from {place} on {date}. Last seen at {last_seen}. Suspect: {accused}, who was seen near the area. Mobile phone switched off.",
        "Kidnapping for ransom: {victim} was abducted from {location} by {count} armed persons. Ransom demand of Rs. {value} received. Vehicle used: {vehicle}.",
    ],
    "extortion": [
        "Complainant received threatening calls from {caller} demanding Rs. {value} as 'protection money' for {business_type}. Caller referenced {gang_name}. Similar calls to {count} other businesses in {area}.",
        "Extortion through social media: Accused {accused} obtained compromising photos and demanded Rs. {value}. Threatening to upload on {platform}.",
    ],
    "dacoity": [
        "Gang of {count} armed persons entered {location} at {time} hours. At gunpoint, looted {items} worth Rs. {value}. {injuries}. Gang leader identified as {accused}. Fled in {vehicle}.",
    ],
    "arson": [
        "Fire set at {location} at approximately {time} hours. {method}. Estimated damage Rs. {value}. Motive: {motive}. {suspects}.",
    ],
    "sexual_offense": [
        "Complaint of {offense_type} at {location} on {date}. Victim: {victim}. Accused: {accused}. Medical examination conducted at {hospital}. FIR registered under relevant sections.",
    ],
    "rioting": [
        "Group clash between {group1} and {group2} at {area} over {motive}. {count} persons injured. Police used {force_type} to control the mob. {arrests} persons arrested.",
    ],
}

# ── Known Criminal Networks (based on real UP crime patterns) ──
NETWORKS = {
    "bablu_gang": {
        "members": ["Bablu alias Bhura", "Sunny alias Sonu", "Deepak alias Deepu"],
        "crime": "robbery", "area": "Lucknow", "keywords": ["Bablu", "snatched", "chain", "Pulsar", "black hoodie"],
    },
    "jamtara_network": {
        "members": ["Vikram Sharma", "Rahul Mandal", "Sohan Das"],
        "crime": "cybercrime", "area": "multi-district", "keywords": ["Vikram Sharma", "Jamtara", "KYC", "digital arrest", "OTP"],
    },
    "munna_gang": {
        "members": ["Munna alias Mohammad Shahid", "Rinku Pandey", "Sonu Tiwari", "Asif Khan"],
        "crime": "extortion", "area": "Varanasi-Prayagraj", "keywords": ["Munna Bhai", "protection money", "threatening"],
    },
    "kanpur_burglary": {
        "members": ["Pappu Kallu alias Kallu", "Ram Swaroop", "Dharamveer"],
        "crime": "burglary", "area": "Kanpur Nagar", "keywords": ["gas cutter", "Eeco van", "shutter", "DVR"],
    },
    "nepal_drugs": {
        "members": ["Shakeel Ahmed alias Kalu", "Guddu Khan", "Pappu Yadav", "Sunny Yadav"],
        "crime": "drug_offense", "area": "Gorakhpur-Lucknow-Meerut", "keywords": ["Nepal", "heroin", "smack", "NDPS", "supply chain"],
    },
    "raju_kidnapping": {
        "members": ["Raju alias Chhotu", "Mohd Arif"],
        "crime": "kidnapping", "area": "Agra", "keywords": ["school", "social media", "Instagram", "luring", "minor"],
    },
    "chhote_lal_gang": {
        "members": ["Chhote Lal alias Chhotu", "Balram", "Rajkumar"],
        "crime": "dacoity", "area": "Gorakhpur", "keywords": ["country-made pistol", "gunpoint", "scar on left cheek"],
    },
    "ghaziabad_auto_theft": {
        "members": ["Bittu alias Ankit", "Mohd Shahid", "Ravi Thakur"],
        "crime": "theft", "area": "Ghaziabad", "keywords": ["master key", "two-wheeler", "UP-14"],
    },
}


def _pick_district() -> tuple[str, str]:
    districts = list(DISTRICTS.keys())
    weights = [DISTRICTS[d]["weight"] for d in districts]
    d = random.choices(districts, weights=weights, k=1)[0]
    station = random.choice(DISTRICTS[d]["stations"])
    return d, station


def _pick_date(year=2024) -> str:
    start = date(year, 1, 1)
    offset = random.randint(0, 364)
    return (start + timedelta(days=offset)).isoformat()


def _random_value(low, high, step=1000):
    return random.randrange(low, high, step)


def _gen_imei():
    return "".join([str(random.randint(0, 9)) for _ in range(15)])


def _gen_phone():
    return f"+91-{random.choice(['9','8','7','6'])}{random.randint(100000000, 999999999)}"


def _random_person(gender: str = "Male") -> str:
    """A distinct full name for someone unconnected to the seeded networks."""
    first = random.choice(FIRST_NAMES_F if gender == "Female" else FIRST_NAMES_M)
    return f"{first} {random.choice(SURNAMES)}"


def generate_fir(idx: int, crime_type: str, network_key: str = None) -> dict:
    district, station = _pick_district()
    fir_date = _pick_date()
    fir_number = f"FIR/2024/{district[:2].upper()}/{idx:03d}"

    # Determine if this FIR is part of a network
    net = NETWORKS.get(network_key) if network_key else None
    if net:
        crime_type = net["crime"]
        if "area" in net and "-" not in net["area"] and net["area"] != "multi-district":
            district = net["area"]
            station = random.choice(DISTRICTS.get(district, DISTRICTS["Lucknow"])["stations"])
            fir_number = f"FIR/2024/{district[:2].upper()}/{idx:03d}"

    # Generate accused
    num_accused = random.randint(1, 3)
    accused = []
    if net:
        for m in random.sample(net["members"], min(num_accused, len(net["members"]))):
            parts = m.split(" alias ")
            name = parts[0]
            alias = parts[1] if len(parts) > 1 else ""
            accused.append({
                "name": name,
                "aliases": [alias] if alias else [],
                "age": random.randint(20, 45),
                "gender": "Male",
                "father_name": _random_person("Male"),
                "address": random.choice(ADDRESSES_BY_DISTRICT.get(district, ["Unknown area"])),
                "id_marks": random.choice([[], ["scar on left cheek"], ["tattoo on right arm"], []]),
                "phone": None,
            })
    else:
        for _ in range(num_accused):
            accused.append({
                "name": _random_person("Male"),
                # Nicknames are common but far from unique, so only a minority
                # of records carry one — matching on them alone is unsafe.
                "aliases": [random.choice(ALIASES)] if random.random() > 0.8 else [],
                "age": random.randint(18, 55),
                "gender": "Male",
                "father_name": _random_person("Male"),
                "address": random.choice(ADDRESSES_BY_DISTRICT.get(district, ["Unknown area"])),
                "id_marks": [],
                "phone": None,
            })

    # Generate victims
    num_victims = random.randint(1, 2)
    victims = []
    for _ in range(num_victims):
        is_female = random.random() > 0.6
        victims.append({
            "name": _random_person("Female" if is_female else "Male"),
            "age": random.randint(20, 70),
            "gender": "Female" if is_female else "Male",
            "occupation": random.choice(["Businessman", "Shopkeeper", "Teacher", "Farmer", "Housewife", "Student", "Doctor", "Engineer", "Retired", "Labourer"]),
            "address": random.choice(ADDRESSES_BY_DISTRICT.get(district, ["Unknown area"])),
        })

    # IPC sections
    sections = random.sample(IPC_SECTIONS.get(crime_type, ["379 IPC"]),
                             min(random.randint(1, 3), len(IPC_SECTIONS.get(crime_type, ["379"]))))

    # Severity
    base_scores = {
        "murder": 95, "dacoity": 85, "kidnapping": 80, "sexual_offense": 85,
        "drug_offense": 75, "robbery": 70, "extortion": 65, "arson": 70,
        "assault": 60, "burglary": 55, "fraud": 50, "cybercrime": 45,
        "theft": 35, "rioting": 60, "other": 30,
    }
    severity = base_scores.get(crime_type, 30) + random.randint(-10, 15)
    severity = max(10, min(100, severity))

    # Location
    area = random.choice(ADDRESSES_BY_DISTRICT.get(district, ["Main market area"]))
    coords = {
        "Lucknow": (26.8467, 80.9462), "Kanpur Nagar": (26.4499, 80.3319),
        "Agra": (27.1767, 78.0081), "Varanasi": (25.3176, 82.9739),
        "Gorakhpur": (26.7606, 83.3732), "Meerut": (28.9845, 77.7064),
        "Prayagraj": (25.4358, 81.8463), "Ghaziabad": (28.6692, 77.4538),
        "Bareilly": (28.3670, 79.4304), "Aligarh": (27.8974, 78.0880),
        "Moradabad": (28.8386, 78.7733), "Jhansi": (25.4484, 78.5685),
        "Mathura": (27.4924, 77.6737),
    }
    lat, lon = coords.get(district, (26.85, 80.95))
    lat += random.uniform(-0.05, 0.05)
    lon += random.uniform(-0.05, 0.05)

    location = {
        "place": area,
        "district": district,
        "state": "Uttar Pradesh",
        "latitude": round(lat, 4),
        "longitude": round(lon, 4),
    }

    # MO
    weapons_pool = ["knife", "pistol", "country-made pistol", "rod", "hockey stick", "acid", "desi katta"]
    weapon = random.choice(weapons_pool) if crime_type in ("robbery", "dacoity", "murder", "assault") else None
    time_hours = random.choice(["0200", "0330", "1430", "1830", "2100", "2230", "2345", "0100"])
    hour = int(time_hours[:2])
    time_of_day = "early morning" if hour < 6 else "morning" if hour < 12 else "afternoon" if hour < 17 else "evening" if hour < 21 else "night"

    mo_approaches = {
        "robbery": "bike-borne snatching",
        "burglary": "shop burglary with gas cutter" if net and network_key == "kanpur_burglary" else "lock breaking",
        "cybercrime": "phone scam / vishing",
        "extortion": "extortion racket",
        "drug_offense": "drug trafficking",
        "kidnapping": "social media luring" if net and network_key == "raju_kidnapping" else "abduction",
        "murder": "premeditated attack",
        "fraud": "impersonation fraud",
        "dacoity": "armed gang raid",
    }
    approach = mo_approaches.get(crime_type, "standard")
    if net:
        keywords = net["keywords"]
    else:
        keywords = [crime_type, approach]

    modus_operandi = {
        "description": f"Method: {approach}; Weapons: {weapon or 'none'}; Time: {time_of_day}",
        "keywords": keywords[:5],
        "weapon_used": weapon,
        "time_of_day": time_of_day,
        "approach_method": approach,
    }

    # Generate raw_text (realistic FIR narrative)
    complainant = victims[0]
    accused_names = ", ".join(a["name"] + (f" alias {a['aliases'][0]}" if a['aliases'] else "") for a in accused)
    stolen_value = _random_value(5000, 5000000, 5000)
    items = random.choice(["mobile phone", "gold chain", "cash and jewelry", "laptops", "medicines", "garments", "electronics"])

    raw_text = (
        f"FIR No. {idx:03d}/2024 dated {fir_date}. "
        f"PS {station.removesuffix(' PS')}, District {district}. "
        f"Complainant: {'Shri' if complainant['gender']=='Male' else 'Smt.'} {complainant['name']}, "
        f"age {complainant['age']} years, "
        f"R/o {complainant['address']}, {district}. "
    )

    # Add crime-specific narrative
    if crime_type == "robbery":
        raw_text += (
            f"The complainant states that on {fir_date} at approximately {time_hours} hours, "
            f"near {area}, {'two bike-borne persons' if len(accused) >= 2 else 'an unknown person'} "
            f"intercepted {'him' if complainant['gender']=='Male' else 'her'}. "
            f"{'One accused put a ' + weapon + ' to the throat while the second person ' if weapon else 'The accused '}"
            f"snatched {items} worth Rs. {stolen_value:,}. "
            f"Accused identified as {accused_names}. "
            f"Sections: {', '.join(sections)}."
        )
    elif crime_type == "burglary":
        method = "cutting the lock with a gas cutter" if net and network_key == "kanpur_burglary" else "breaking the rear lock"
        raw_text += (
            f"The complainant reports that between {_random_value(2200, 2400, 100)} hours and "
            f"{_random_value(100, 500, 100):04d} hours, unknown persons broke into "
            f"{'his' if complainant['gender']=='Male' else 'her'} shop at {area} market by {method}. "
            f"Stolen property: {items} worth Rs. {stolen_value:,}. "
            f"{'A white Maruti Eeco van was spotted nearby. ' if net and network_key == 'kanpur_burglary' else ''}"
            f"Sections: {', '.join(sections)}."
        )
    elif crime_type == "cybercrime":
        scam_type = random.choice(["KYC expiry", "digital arrest", "investment fraud", "lottery scam"])
        raw_text += (
            f"The complainant reports cyber fraud. A person claiming to be "
            f"{'Vikram Sharma from SBI customer care' if net and network_key == 'jamtara_network' else 'bank official'} "
            f"contacted {'him' if complainant['gender']=='Male' else 'her'} regarding {scam_type}. "
            f"Under duress, complainant transferred Rs. {stolen_value:,} to accounts specified by the accused. "
            f"Money trail leads to Jamtara, Jharkhand. "
            f"Sections: {', '.join(sections)}."
        )
    elif crime_type == "drug_offense":
        drug = random.choice(["ganja (2.5 kg)", "heroin (500g)", "smack (200g)", "MDMA (100g)", "brown sugar (300g)"])
        raw_text += (
            f"Suo motu FIR: During {'raid' if random.random() > 0.5 else 'routine patrol'} "
            f"at {area}, police recovered {drug} "
            f"valued at Rs. {stolen_value:,}. "
            f"Arrested: {accused_names}. "
            f"{'Part of supply chain from Nepal border through Gorakhpur. ' if net and network_key == 'nepal_drugs' else ''}"
            f"Sections: {', '.join(sections)}."
        )
    elif crime_type == "extortion":
        raw_text += (
            f"The complainant received threatening calls demanding Rs. {stolen_value:,} "
            f"as 'protection money' for {'his' if complainant['gender']=='Male' else 'her'} "
            f"{random.choice(['restaurant', 'shop', 'business', 'showroom'])} at {area}. "
            f"{'Caller identified himself as working for Munna Bhai. ' if net and network_key == 'munna_gang' else ''}"
            f"Accused: {accused_names}. "
            f"Sections: {', '.join(sections)}."
        )
    elif crime_type == "murder":
        cause = random.choice(["multiple stab wounds", "gunshot wounds", "blunt force trauma", "strangulation"])
        motive = random.choice(["property dispute", "personal enmity", "robbery gone wrong", "honour killing", "gang rivalry"])
        raw_text += (
            f"The deceased {victims[0]['name']} (age {victims[0]['age']}) was found dead at {area} "
            f"with {cause}. Suspect: {accused_names}. Motive: {motive}. "
            f"Forensic evidence collected. Post-mortem at District Hospital. "
            f"Sections: {', '.join(sections)}."
        )
    elif crime_type == "kidnapping":
        raw_text += (
            f"Missing person: {victims[0]['name']} (age {victims[0]['age']}) did not return from "
            f"{random.choice(['school', 'tuition class', 'market', 'work'])} on {fir_date}. "
            f"Suspect: {accused_names}. "
            f"{'Accused uses social media to befriend victims near schools. ' if net and network_key == 'raju_kidnapping' else ''}"
            f"Mobile phone switched off. Sections: {', '.join(sections)}."
        )
    elif crime_type == "assault":
        injuries = random.choice(["fractures to left arm", "head injuries", "lacerations on face", "multiple bruises"])
        raw_text += (
            f"On {fir_date} at {time_hours} hours, the complainant was attacked by {accused_names} "
            f"near {area} using {weapon or 'bare hands'}. Victim sustained {injuries}. "
            f"Hospitalized at District Hospital. "
            f"Sections: {', '.join(sections)}."
        )
    elif crime_type == "fraud":
        method = random.choice(["fake investment scheme", "forged property documents", "Ponzi scheme", "fake job offer"])
        raw_text += (
            f"The complainant was defrauded of Rs. {stolen_value:,} through {method} by {accused_names}. "
            f"Investigation reveals {random.randint(3, 20)} similar victims in the area. "
            f"Sections: {', '.join(sections)}."
        )
    elif crime_type == "dacoity":
        raw_text += (
            f"A gang of {len(accused)+2} armed persons entered {complainant['name']}'s residence at {area} "
            f"at {time_hours} hours. At gunpoint, looted jewelry, cash, and valuables worth Rs. {stolen_value:,}. "
            f"Gang leader identified as {accused[0]['name']}. "
            f"Sections: {', '.join(sections)}."
        )
    elif crime_type == "arson":
        raw_text += (
            f"Fire set at {random.choice(['warehouse', 'shop', 'godown'])} at {area} at approximately {time_hours} hours. "
            f"Inflammable liquid used. Damage estimated Rs. {stolen_value:,}. "
            f"Motive: {random.choice(['extortion refusal', 'business rivalry', 'personal enmity'])}. "
            f"Accused: {accused_names}. Sections: {', '.join(sections)}."
        )
    else:
        raw_text += (
            f"The complainant reports an incident at {area} on {fir_date}. "
            f"Accused: {accused_names}. "
            f"Sections: {', '.join(sections)}. Investigation initiated."
        )

    summary_parts = [
        f"Crime: {crime_type.replace('_', ' ').title()}",
        f"Location: {area}, {district}",
    ]
    if accused:
        summary_parts.append(f"Accused: {', '.join(a['name'] for a in accused[:3])}")
    if approach:
        summary_parts.append(f"MO: {approach}")

    return {
        "fir_number": fir_number,
        "date_filed": fir_date,
        "police_station": station,
        "district": district,
        "state": "Uttar Pradesh",
        "raw_text": raw_text,
        "crime_type": crime_type,
        "ipc_sections": sections,
        "accused": accused,
        "victims": victims,
        "location": location,
        "modus_operandi": modus_operandi,
        "severity_score": severity,
        "summary": "; ".join(summary_parts),
    }


def generate_ncrb_dataset(count: int = 100) -> list[dict]:
    firs = []
    idx = 1

    # Skip raw mock_firs.json — they lack structured fields (crime_type,
    # severity_score, accused, etc.) which causes "other" buckets in MongoDB
    # aggregations. The generated network-linked FIRs below cover the same
    # criminal networks with proper structured data.

    # Generate network-linked FIRs (for cross-FIR pattern detection)
    network_firs_per_net = {
        "bablu_gang": 5,
        "jamtara_network": 6,
        "munna_gang": 4,
        "kanpur_burglary": 5,
        "nepal_drugs": 4,
        "raju_kidnapping": 3,
        "chhote_lal_gang": 3,
        "ghaziabad_auto_theft": 4,
    }

    for net_key, net_count in network_firs_per_net.items():
        for _ in range(net_count):
            fir = generate_fir(idx, NETWORKS[net_key]["crime"], network_key=net_key)
            fir["_source"] = "ncrb_generated"
            fir["_network"] = net_key
            firs.append(fir)
            idx += 1

    # Fill remaining with NCRB-distributed random FIRs
    remaining = count - len(firs)
    crime_pool = []
    for crime, freq in CRIME_DISTRIBUTION.items():
        crime_pool.extend([crime] * freq)

    for _ in range(max(0, remaining)):
        crime_type = random.choice(crime_pool)
        fir = generate_fir(idx, crime_type)
        fir["_source"] = "ncrb_generated"
        firs.append(fir)
        idx += 1

    # Deduplicate FIR numbers
    seen = set()
    for fir in firs:
        while fir["fir_number"] in seen:
            idx += 1
            fir["fir_number"] = f"FIR/2024/{fir['district'][:2].upper()}/{idx:03d}"
        seen.add(fir["fir_number"])

    return firs


if __name__ == "__main__":
    dataset = generate_ncrb_dataset(100)
    print(f"Generated {len(dataset)} FIRs")
    types = {}
    districts = {}
    for f in dataset:
        ct = f.get("crime_type", "other")
        types[ct] = types.get(ct, 0) + 1
        d = f["district"]
        districts[d] = districts.get(d, 0) + 1
    print("\nCrime breakdown:")
    for ct, count in sorted(types.items(), key=lambda x: -x[1]):
        print(f"  {ct}: {count}")
    print("\nDistrict breakdown:")
    for d, count in sorted(districts.items(), key=lambda x: -x[1]):
        print(f"  {d}: {count}")
