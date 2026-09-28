from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, date
from enum import Enum


class CrimeType(str, Enum):
    THEFT = "theft"
    ROBBERY = "robbery"
    BURGLARY = "burglary"
    ASSAULT = "assault"
    MURDER = "murder"
    FRAUD = "fraud"
    CYBERCRIME = "cybercrime"
    DRUG_OFFENSE = "drug_offense"
    KIDNAPPING = "kidnapping"
    SEXUAL_OFFENSE = "sexual_offense"
    EXTORTION = "extortion"
    DACOITY = "dacoity"
    ARSON = "arson"
    RIOTING = "rioting"
    OTHER = "other"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Entity(BaseModel):
    text: str
    label: str
    start: int = 0
    end: int = 0
    confidence: float = 0.0


class AccusedProfile(BaseModel):
    name: str
    aliases: list[str] = []
    age: Optional[int] = None
    gender: Optional[str] = None
    father_name: Optional[str] = None
    address: Optional[str] = None
    id_marks: list[str] = []
    phone: Optional[str] = None


class VictimProfile(BaseModel):
    name: str
    age: Optional[int] = None
    gender: Optional[str] = None
    occupation: Optional[str] = None
    address: Optional[str] = None


class LocationInfo(BaseModel):
    place: str
    district: str = ""
    state: str = "Uttar Pradesh"
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class ModusOperandi(BaseModel):
    description: str
    keywords: list[str] = []
    weapon_used: Optional[str] = None
    time_of_day: Optional[str] = None
    approach_method: Optional[str] = None


class FIRRecord(BaseModel):
    fir_number: str
    date_filed: date
    police_station: str
    district: str
    state: str = "Uttar Pradesh"
    raw_text: str
    crime_type: Optional[CrimeType] = None
    ipc_sections: list[str] = []
    accused: list[AccusedProfile] = []
    victims: list[VictimProfile] = []
    location: Optional[LocationInfo] = None
    modus_operandi: Optional[ModusOperandi] = None
    severity_score: float = 0.0
    summary: str = ""


class RepeatOffender(BaseModel):
    name: str
    aliases: list[str] = []
    linked_firs: list[str] = []
    crime_types: list[str] = []
    stations: list[str] = []
    districts: list[str] = []
    risk_level: RiskLevel = RiskLevel.LOW
    mo_signature: str = ""
    total_incidents: int = 0
    confidence_score: float = 0.0
    first_seen: Optional[date] = None
    last_seen: Optional[date] = None


class StationSummary(BaseModel):
    station_name: str
    district: str
    total_firs: int = 0
    crime_breakdown: dict[str, int] = {}
    monthly_trend: dict[str, int] = {}
    top_crime: str = ""
    repeat_offenders_count: int = 0
    hotspot_areas: list[str] = []
    risk_assessment: str = ""


class AnalysisResult(BaseModel):
    total_firs_processed: int
    fir_records: list[FIRRecord]
    repeat_offenders: list[RepeatOffender]
    station_summaries: list[StationSummary]
    crime_trend: dict[str, dict[str, int]]
    entity_stats: dict[str, int]
    generated_at: datetime = Field(default_factory=datetime.now)


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    context: Optional[str] = None
    #: Prior turns, so the assistant can resolve follow-ups like "and in Agra?".
    history: list[ChatMessage] = []


class ChatResponse(BaseModel):
    response: str
    entities_referenced: list[str] = []
    firs_referenced: list[str] = []
    #: Which engine produced the answer, so the UI can say so rather than
    #: passing a computed fallback off as a model response.
    source: str = "analysis"
    model: Optional[str] = None
