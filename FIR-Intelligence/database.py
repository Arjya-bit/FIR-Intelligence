from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import IndexModel, ASCENDING, DESCENDING, TEXT
from datetime import datetime
import os

MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.getenv("MONGO_DB", "fir_intelligence")

client: AsyncIOMotorClient = None
db = None


async def connect():
    global client, db
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    await _ensure_indexes()
    print(f"Connected to MongoDB: {MONGO_URL}/{DB_NAME}")


async def disconnect():
    global client
    if client:
        client.close()


async def _ensure_indexes():
    await db.firs.create_indexes([
        IndexModel([("fir_number", ASCENDING)], unique=True),
        IndexModel([("district", ASCENDING)]),
        IndexModel([("crime_type", ASCENDING)]),
        IndexModel([("date_filed", DESCENDING)]),
        IndexModel([("police_station", ASCENDING)]),
        IndexModel([("severity_score", DESCENDING)]),
        IndexModel([("state", ASCENDING)]),
        IndexModel([("raw_text", TEXT)]),
    ])
    await db.offenders.create_indexes([
        IndexModel([("name", ASCENDING)]),
        IndexModel([("risk_level", ASCENDING)]),
        IndexModel([("districts", ASCENDING)]),
    ])
    await db.stations.create_indexes([
        IndexModel([("station_name", ASCENDING)]),
        IndexModel([("district", ASCENDING)]),
    ])
    await db.networks.create_indexes([
        IndexModel([("name", ASCENDING)]),
    ])
    await db.analysis_meta.create_indexes([
        IndexModel([("generated_at", DESCENDING)]),
    ])


# ── FIR Operations ──

async def insert_firs(fir_docs: list[dict]) -> int:
    if not fir_docs:
        return 0
    for doc in fir_docs:
        doc["_id"] = doc["fir_number"]
        doc["inserted_at"] = datetime.utcnow()
    result = await db.firs.insert_many(fir_docs, ordered=False)
    return len(result.inserted_ids)


async def upsert_fir(doc: dict):
    doc["updated_at"] = datetime.utcnow()
    await db.firs.replace_one(
        {"fir_number": doc["fir_number"]}, doc, upsert=True
    )


async def get_all_firs(crime_type=None, district=None, station=None,
                       skip=0, limit=500) -> list[dict]:
    query = {}
    if crime_type:
        query["crime_type"] = crime_type
    if district:
        query["district"] = {"$regex": district, "$options": "i"}
    if station:
        query["police_station"] = {"$regex": station, "$options": "i"}
    cursor = db.firs.find(query).sort("date_filed", DESCENDING).skip(skip).limit(limit)
    return await cursor.to_list(length=limit)


async def get_fir(fir_number: str) -> dict | None:
    return await db.firs.find_one({"fir_number": fir_number})


async def count_firs(query=None) -> int:
    return await db.firs.count_documents(query or {})


async def search_firs(text: str, limit=50) -> list[dict]:
    cursor = db.firs.find(
        {"$text": {"$search": text}},
        {"score": {"$meta": "textScore"}}
    ).sort([("score", {"$meta": "textScore"})]).limit(limit)
    return await cursor.to_list(length=limit)


async def get_fir_stats() -> dict:
    pipeline = [
        {"$group": {
            "_id": None,
            "total": {"$sum": 1},
            "total_accused": {"$sum": {"$size": {"$ifNull": ["$accused", []]}}},
            "total_victims": {"$sum": {"$size": {"$ifNull": ["$victims", []]}}},
            "districts": {"$addToSet": "$district"},
            "avg_severity": {"$avg": "$severity_score"},
        }}
    ]
    result = await db.firs.aggregate(pipeline).to_list(1)
    return result[0] if result else {}


async def get_crime_breakdown() -> dict:
    pipeline = [
        {"$group": {"_id": "$crime_type", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    result = await db.firs.aggregate(pipeline).to_list(50)
    return {r["_id"]: r["count"] for r in result if r["_id"]}


async def get_district_breakdown() -> dict:
    pipeline = [
        {"$group": {"_id": "$district", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    result = await db.firs.aggregate(pipeline).to_list(50)
    return {r["_id"]: r["count"] for r in result if r["_id"]}


async def get_monthly_trend() -> dict:
    pipeline = [
        {"$project": {"month": {"$substr": ["$date_filed", 0, 7]}}},
        {"$group": {"_id": "$month", "count": {"$sum": 1}}},
        {"$sort": {"_id": 1}},
    ]
    result = await db.firs.aggregate(pipeline).to_list(100)
    return {r["_id"]: r["count"] for r in result}


async def get_severity_distribution() -> dict:
    pipeline = [
        {"$project": {
            "level": {"$switch": {
                "branches": [
                    {"case": {"$gte": [{"$ifNull": ["$severity_score", 0]}, 80]}, "then": "critical"},
                    {"case": {"$gte": [{"$ifNull": ["$severity_score", 0]}, 60]}, "then": "high"},
                    {"case": {"$gte": [{"$ifNull": ["$severity_score", 0]}, 40]}, "then": "medium"},
                ],
                "default": "low",
            }}
        }},
        {"$group": {"_id": "$level", "count": {"$sum": 1}}},
    ]
    result = await db.firs.aggregate(pipeline).to_list(10)
    dist = {"low": 0, "medium": 0, "high": 0, "critical": 0}
    for r in result:
        if r["_id"] in dist:
            dist[r["_id"]] = r["count"]
    return dist


# ── Offender Operations ──

async def save_offenders(offenders: list[dict]):
    if not offenders:
        return
    await db.offenders.delete_many({})
    for o in offenders:
        o["updated_at"] = datetime.utcnow()
    await db.offenders.insert_many(offenders)


async def get_offenders() -> list[dict]:
    return await db.offenders.find().sort("total_incidents", DESCENDING).to_list(200)


# ── Station Operations ──

async def save_stations(stations: list[dict]):
    if not stations:
        return
    await db.stations.delete_many({})
    for s in stations:
        s["updated_at"] = datetime.utcnow()
    await db.stations.insert_many(stations)


async def get_stations() -> list[dict]:
    return await db.stations.find().sort("total_firs", DESCENDING).to_list(200)


# ── Network Operations ──

async def save_networks(networks: list[dict]):
    if not networks:
        return
    await db.networks.delete_many({})
    for n in networks:
        n["updated_at"] = datetime.utcnow()
    await db.networks.insert_many(networks)


async def get_networks() -> list[dict]:
    return await db.networks.find().sort("fir_count", DESCENDING).to_list(50)


# ── Analysis Metadata ──

async def save_analysis_meta(meta: dict):
    meta["generated_at"] = datetime.utcnow()
    await db.analysis_meta.insert_one(meta)


async def get_latest_meta() -> dict | None:
    return await db.analysis_meta.find_one(sort=[("generated_at", DESCENDING)])


async def is_db_seeded() -> bool:
    return await db.firs.count_documents({}) > 0


async def clear_all():
    await db.firs.delete_many({})
    await db.offenders.delete_many({})
    await db.stations.delete_many({})
    await db.networks.delete_many({})
    await db.analysis_meta.delete_many({})
