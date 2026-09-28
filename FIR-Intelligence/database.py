"""Storage layer for the FIR Intelligence platform.

Two interchangeable backends sit behind one async API:

* **MongoDB** (via Motor) — used when a server is reachable at ``MONGO_URL``.
* **In-memory** — a pure-Python fallback so the app boots with zero
  infrastructure. Data lives for the lifetime of the process only.

``connect()`` probes MongoDB with a short timeout and silently degrades to the
in-memory backend, so ``python main.py`` works on a laptop with nothing
installed while the same code runs against a real cluster in production.
Set ``FIR_STORAGE=memory`` to force the fallback, or ``FIR_STORAGE=mongodb``
to make a failed connection a hard error instead of degrading.
"""

from __future__ import annotations

import asyncio
import copy
import os
import re
from collections import defaultdict
from datetime import datetime, timezone

MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.getenv("MONGO_DB", "fir_intelligence")
STORAGE_PREFERENCE = os.getenv("FIR_STORAGE", "auto").strip().lower()
CONNECT_TIMEOUT_MS = int(os.getenv("MONGO_TIMEOUT_MS", "2000"))

_backend: "_Backend | None" = None


def _utcnow() -> datetime:
    """Timezone-aware UTC now (``datetime.utcnow()`` is deprecated in 3.12+)."""
    return datetime.now(timezone.utc)


def _month_of(doc: dict) -> str:
    value = doc.get("date_filed")
    if isinstance(value, (datetime,)):
        return value.strftime("%Y-%m")
    return str(value or "")[:7]


def _severity_bucket(score) -> str:
    try:
        score = float(score or 0)
    except (TypeError, ValueError):
        score = 0.0
    if score >= 80:
        return "critical"
    if score >= 60:
        return "high"
    if score >= 40:
        return "medium"
    return "low"


# ── Backend interface ──────────────────────────────────────────────────────


class _Backend:
    """Common surface implemented by both storage backends."""

    name = "unknown"

    async def close(self) -> None: ...

    async def insert_firs(self, docs: list[dict]) -> int: ...

    async def upsert_fir(self, doc: dict) -> None: ...

    async def get_all_firs(self, crime_type=None, district=None, station=None,
                           skip=0, limit=500) -> list[dict]: ...

    async def get_fir(self, fir_number: str) -> dict | None: ...

    async def count_firs(self, query: dict | None = None) -> int: ...

    async def search_firs(self, text: str, limit: int = 50) -> list[dict]: ...

    async def get_fir_stats(self) -> dict: ...

    async def get_crime_breakdown(self) -> dict: ...

    async def get_district_breakdown(self) -> dict: ...

    async def get_monthly_trend(self) -> dict: ...

    async def get_severity_distribution(self) -> dict: ...

    async def save_collection(self, name: str, docs: list[dict]) -> None: ...

    async def get_collection(self, name: str, sort_key: str | None = None,
                             limit: int = 200) -> list[dict]: ...

    async def save_analysis_meta(self, meta: dict) -> None: ...

    async def get_latest_meta(self) -> dict | None: ...

    async def clear_all(self) -> None: ...


# ── In-memory backend ──────────────────────────────────────────────────────


class MemoryBackend(_Backend):
    """Dict-backed store mirroring the Mongo queries the app actually uses."""

    name = "in-memory"

    def __init__(self) -> None:
        self._firs: dict[str, dict] = {}
        self._collections: dict[str, list[dict]] = defaultdict(list)
        self._meta: list[dict] = []

    async def close(self) -> None:
        return None

    async def insert_firs(self, docs: list[dict]) -> int:
        inserted = 0
        for doc in docs:
            number = doc.get("fir_number")
            if not number or number in self._firs:
                continue
            stored = copy.deepcopy(doc)
            stored["inserted_at"] = _utcnow()
            self._firs[number] = stored
            inserted += 1
        return inserted

    async def upsert_fir(self, doc: dict) -> None:
        stored = copy.deepcopy(doc)
        stored["updated_at"] = _utcnow()
        self._firs[doc["fir_number"]] = stored

    async def get_all_firs(self, crime_type=None, district=None, station=None,
                           skip=0, limit=500) -> list[dict]:
        rows = list(self._firs.values())
        if crime_type:
            rows = [r for r in rows if r.get("crime_type") == crime_type]
        if district:
            rows = [r for r in rows
                    if district.lower() in str(r.get("district", "")).lower()]
        if station:
            rows = [r for r in rows
                    if station.lower() in str(r.get("police_station", "")).lower()]
        rows.sort(key=lambda r: str(r.get("date_filed", "")), reverse=True)
        return copy.deepcopy(rows[skip:skip + limit])

    async def get_fir(self, fir_number: str) -> dict | None:
        doc = self._firs.get(fir_number)
        return copy.deepcopy(doc) if doc else None

    async def count_firs(self, query: dict | None = None) -> int:
        if not query:
            return len(self._firs)
        return len([r for r in self._firs.values()
                    if all(r.get(k) == v for k, v in query.items())])

    async def search_firs(self, text: str, limit: int = 50) -> list[dict]:
        terms = [t for t in re.split(r"\W+", text.lower()) if t]
        if not terms:
            return []
        scored = []
        for row in self._firs.values():
            haystack = " ".join(str(row.get(f, "")) for f in
                                ("raw_text", "summary", "district",
                                 "police_station", "fir_number")).lower()
            score = sum(haystack.count(term) for term in terms)
            if score:
                scored.append((score, row))
        scored.sort(key=lambda pair: -pair[0])
        return [copy.deepcopy(row) for _, row in scored[:limit]]

    async def get_fir_stats(self) -> dict:
        rows = list(self._firs.values())
        if not rows:
            return {}
        severities = [float(r.get("severity_score") or 0) for r in rows]
        return {
            "total": len(rows),
            "total_accused": sum(len(r.get("accused") or []) for r in rows),
            "total_victims": sum(len(r.get("victims") or []) for r in rows),
            "districts": sorted({r.get("district", "") for r in rows if r.get("district")}),
            "avg_severity": round(sum(severities) / len(severities), 2),
        }

    def _count_by(self, field: str) -> dict:
        counts: dict[str, int] = defaultdict(int)
        for row in self._firs.values():
            key = row.get(field)
            if key:
                counts[key] += 1
        return dict(sorted(counts.items(), key=lambda kv: -kv[1]))

    async def get_crime_breakdown(self) -> dict:
        return self._count_by("crime_type")

    async def get_district_breakdown(self) -> dict:
        return self._count_by("district")

    async def get_monthly_trend(self) -> dict:
        counts: dict[str, int] = defaultdict(int)
        for row in self._firs.values():
            month = _month_of(row)
            if month:
                counts[month] += 1
        return dict(sorted(counts.items()))

    async def get_severity_distribution(self) -> dict:
        dist = {"low": 0, "medium": 0, "high": 0, "critical": 0}
        for row in self._firs.values():
            dist[_severity_bucket(row.get("severity_score"))] += 1
        return dist

    async def save_collection(self, name: str, docs: list[dict]) -> None:
        stamped = []
        for doc in docs:
            item = copy.deepcopy(doc)
            item["updated_at"] = _utcnow()
            stamped.append(item)
        self._collections[name] = stamped

    async def get_collection(self, name: str, sort_key: str | None = None,
                             limit: int = 200) -> list[dict]:
        rows = list(self._collections.get(name, []))
        if sort_key:
            rows.sort(key=lambda r: r.get(sort_key) or 0, reverse=True)
        return copy.deepcopy(rows[:limit])

    async def save_analysis_meta(self, meta: dict) -> None:
        item = copy.deepcopy(meta)
        item["generated_at"] = _utcnow()
        self._meta.append(item)

    async def get_latest_meta(self) -> dict | None:
        if not self._meta:
            return None
        return copy.deepcopy(max(self._meta, key=lambda m: m["generated_at"]))

    async def clear_all(self) -> None:
        self._firs.clear()
        self._collections.clear()
        self._meta.clear()


# ── MongoDB backend ────────────────────────────────────────────────────────


class MongoBackend(_Backend):
    """Motor-backed store. Instantiate through :func:`MongoBackend.create`."""

    name = "mongodb"

    def __init__(self, client, db) -> None:
        self._client = client
        self._db = db

    @classmethod
    async def create(cls, url: str, db_name: str, timeout_ms: int) -> "MongoBackend":
        from motor.motor_asyncio import AsyncIOMotorClient

        client = AsyncIOMotorClient(url, serverSelectionTimeoutMS=timeout_ms)
        # Forces server selection now instead of on the first real query, so a
        # missing server degrades at startup rather than mid-request.
        await client.admin.command("ping")
        backend = cls(client, client[db_name])
        await backend._ensure_indexes()
        return backend

    async def _ensure_indexes(self) -> None:
        from pymongo import ASCENDING, DESCENDING, TEXT, IndexModel

        await self._db.firs.create_indexes([
            IndexModel([("fir_number", ASCENDING)], unique=True),
            IndexModel([("district", ASCENDING)]),
            IndexModel([("crime_type", ASCENDING)]),
            IndexModel([("date_filed", DESCENDING)]),
            IndexModel([("police_station", ASCENDING)]),
            IndexModel([("severity_score", DESCENDING)]),
            IndexModel([("state", ASCENDING)]),
            IndexModel([("raw_text", TEXT)]),
        ])
        await self._db.offenders.create_indexes([
            IndexModel([("name", ASCENDING)]),
            IndexModel([("risk_level", ASCENDING)]),
            IndexModel([("districts", ASCENDING)]),
        ])
        await self._db.stations.create_indexes([
            IndexModel([("station_name", ASCENDING)]),
            IndexModel([("district", ASCENDING)]),
        ])
        await self._db.networks.create_indexes([IndexModel([("name", ASCENDING)])])
        await self._db.analysis_meta.create_indexes([
            IndexModel([("generated_at", DESCENDING)]),
        ])

    async def close(self) -> None:
        self._client.close()

    async def insert_firs(self, docs: list[dict]) -> int:
        if not docs:
            return 0
        from pymongo.errors import BulkWriteError

        payload = []
        for doc in docs:
            item = dict(doc)
            item["_id"] = item["fir_number"]
            item["inserted_at"] = _utcnow()
            payload.append(item)
        try:
            result = await self._db.firs.insert_many(payload, ordered=False)
            return len(result.inserted_ids)
        except BulkWriteError as exc:
            # Duplicate FIR numbers are expected on re-seed; count the rest.
            return exc.details.get("nInserted", 0)

    async def upsert_fir(self, doc: dict) -> None:
        item = dict(doc)
        item["updated_at"] = _utcnow()
        await self._db.firs.replace_one(
            {"fir_number": item["fir_number"]}, item, upsert=True
        )

    async def get_all_firs(self, crime_type=None, district=None, station=None,
                           skip=0, limit=500) -> list[dict]:
        from pymongo import DESCENDING

        query: dict = {}
        if crime_type:
            query["crime_type"] = crime_type
        if district:
            query["district"] = {"$regex": re.escape(district), "$options": "i"}
        if station:
            query["police_station"] = {"$regex": re.escape(station), "$options": "i"}
        cursor = (self._db.firs.find(query)
                  .sort("date_filed", DESCENDING).skip(skip).limit(limit))
        return await cursor.to_list(length=limit)

    async def get_fir(self, fir_number: str) -> dict | None:
        return await self._db.firs.find_one({"fir_number": fir_number})

    async def count_firs(self, query: dict | None = None) -> int:
        return await self._db.firs.count_documents(query or {})

    async def search_firs(self, text: str, limit: int = 50) -> list[dict]:
        cursor = self._db.firs.find(
            {"$text": {"$search": text}}, {"score": {"$meta": "textScore"}}
        ).sort([("score", {"$meta": "textScore"})]).limit(limit)
        return await cursor.to_list(length=limit)

    async def get_fir_stats(self) -> dict:
        pipeline = [{"$group": {
            "_id": None,
            "total": {"$sum": 1},
            "total_accused": {"$sum": {"$size": {"$ifNull": ["$accused", []]}}},
            "total_victims": {"$sum": {"$size": {"$ifNull": ["$victims", []]}}},
            "districts": {"$addToSet": "$district"},
            "avg_severity": {"$avg": "$severity_score"},
        }}]
        result = await self._db.firs.aggregate(pipeline).to_list(1)
        if not result:
            return {}
        stats = result[0]
        stats.pop("_id", None)
        stats["districts"] = sorted(d for d in stats.get("districts", []) if d)
        if stats.get("avg_severity") is not None:
            stats["avg_severity"] = round(stats["avg_severity"], 2)
        return stats

    async def _count_by(self, field: str) -> dict:
        pipeline = [
            {"$group": {"_id": f"${field}", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
        ]
        result = await self._db.firs.aggregate(pipeline).to_list(200)
        return {r["_id"]: r["count"] for r in result if r["_id"]}

    async def get_crime_breakdown(self) -> dict:
        return await self._count_by("crime_type")

    async def get_district_breakdown(self) -> dict:
        return await self._count_by("district")

    async def get_monthly_trend(self) -> dict:
        # date_filed is stored as an ISO string; $substrBytes is safe on ASCII.
        pipeline = [
            {"$project": {"month": {"$substrBytes": [
                {"$toString": "$date_filed"}, 0, 7]}}},
            {"$group": {"_id": "$month", "count": {"$sum": 1}}},
            {"$sort": {"_id": 1}},
        ]
        result = await self._db.firs.aggregate(pipeline).to_list(500)
        return {r["_id"]: r["count"] for r in result if r["_id"]}

    async def get_severity_distribution(self) -> dict:
        pipeline = [
            {"$project": {"level": {"$switch": {
                "branches": [
                    {"case": {"$gte": [{"$ifNull": ["$severity_score", 0]}, 80]},
                     "then": "critical"},
                    {"case": {"$gte": [{"$ifNull": ["$severity_score", 0]}, 60]},
                     "then": "high"},
                    {"case": {"$gte": [{"$ifNull": ["$severity_score", 0]}, 40]},
                     "then": "medium"},
                ],
                "default": "low",
            }}}},
            {"$group": {"_id": "$level", "count": {"$sum": 1}}},
        ]
        result = await self._db.firs.aggregate(pipeline).to_list(10)
        dist = {"low": 0, "medium": 0, "high": 0, "critical": 0}
        for row in result:
            if row["_id"] in dist:
                dist[row["_id"]] = row["count"]
        return dist

    async def save_collection(self, name: str, docs: list[dict]) -> None:
        collection = self._db[name]
        await collection.delete_many({})
        if not docs:
            return
        payload = []
        for doc in docs:
            item = dict(doc)
            item["updated_at"] = _utcnow()
            payload.append(item)
        await collection.insert_many(payload)

    async def get_collection(self, name: str, sort_key: str | None = None,
                             limit: int = 200) -> list[dict]:
        from pymongo import DESCENDING

        cursor = self._db[name].find()
        if sort_key:
            cursor = cursor.sort(sort_key, DESCENDING)
        return await cursor.to_list(limit)

    async def save_analysis_meta(self, meta: dict) -> None:
        item = dict(meta)
        item["generated_at"] = _utcnow()
        await self._db.analysis_meta.insert_one(item)

    async def get_latest_meta(self) -> dict | None:
        from pymongo import DESCENDING

        return await self._db.analysis_meta.find_one(
            sort=[("generated_at", DESCENDING)]
        )

    async def clear_all(self) -> None:
        for name in ("firs", "offenders", "stations", "networks", "analysis_meta"):
            await self._db[name].delete_many({})


# ── Module-level facade ────────────────────────────────────────────────────


def _require() -> _Backend:
    if _backend is None:
        raise RuntimeError("Storage not initialised — call database.connect() first")
    return _backend


async def connect() -> str:
    """Select and initialise a backend. Returns the backend name."""
    global _backend

    if STORAGE_PREFERENCE == "memory":
        _backend = MemoryBackend()
        print("Storage: in-memory (FIR_STORAGE=memory)")
        return _backend.name

    try:
        _backend = await MongoBackend.create(MONGO_URL, DB_NAME, CONNECT_TIMEOUT_MS)
        print(f"Storage: MongoDB at {MONGO_URL}/{DB_NAME}")
        return _backend.name
    except BaseException as exc:
        # Deliberately broader than `Exception`. Importing the driver can fail
        # below the Python exception hierarchy — a broken system `cryptography`
        # install makes pymongo's TLS import raise pyo3_runtime.PanicException,
        # which derives from BaseException and would otherwise stop the service
        # from starting at all, which is precisely what this fallback exists to
        # prevent. Genuine control-flow exceptions still propagate.
        if isinstance(exc, (KeyboardInterrupt, SystemExit, asyncio.CancelledError)):
            raise
        if STORAGE_PREFERENCE == "mongodb":
            raise RuntimeError(
                f"FIR_STORAGE=mongodb but {MONGO_URL} could not be used: "
                f"{type(exc).__name__}: {exc}"
            ) from exc
        _backend = MemoryBackend()
        print(f"Storage: in-memory fallback — MongoDB at {MONGO_URL} "
              f"unavailable ({type(exc).__name__}). Data will not persist.")
        return _backend.name


async def disconnect() -> None:
    global _backend
    if _backend is not None:
        await _backend.close()
        _backend = None


def backend_name() -> str:
    return _backend.name if _backend else "not connected"


def is_persistent() -> bool:
    return isinstance(_backend, MongoBackend)


async def insert_firs(fir_docs: list[dict]) -> int:
    return await _require().insert_firs(fir_docs)


async def upsert_fir(doc: dict) -> None:
    await _require().upsert_fir(doc)


async def get_all_firs(crime_type=None, district=None, station=None,
                       skip=0, limit=500) -> list[dict]:
    return await _require().get_all_firs(crime_type, district, station, skip, limit)


async def get_fir(fir_number: str) -> dict | None:
    return await _require().get_fir(fir_number)


async def count_firs(query: dict | None = None) -> int:
    return await _require().count_firs(query)


async def search_firs(text: str, limit: int = 50) -> list[dict]:
    return await _require().search_firs(text, limit)


async def get_fir_stats() -> dict:
    return await _require().get_fir_stats()


async def get_crime_breakdown() -> dict:
    return await _require().get_crime_breakdown()


async def get_district_breakdown() -> dict:
    return await _require().get_district_breakdown()


async def get_monthly_trend() -> dict:
    return await _require().get_monthly_trend()


async def get_severity_distribution() -> dict:
    return await _require().get_severity_distribution()


async def save_offenders(offenders: list[dict]) -> None:
    await _require().save_collection("offenders", offenders)


async def get_offenders() -> list[dict]:
    return await _require().get_collection("offenders", sort_key="total_incidents")


async def save_stations(stations: list[dict]) -> None:
    await _require().save_collection("stations", stations)


async def get_stations() -> list[dict]:
    return await _require().get_collection("stations", sort_key="total_firs")


async def save_networks(networks: list[dict]) -> None:
    await _require().save_collection("networks", networks)


async def get_networks() -> list[dict]:
    return await _require().get_collection("networks", sort_key="fir_count", limit=50)


async def save_analysis_meta(meta: dict) -> None:
    await _require().save_analysis_meta(meta)


async def get_latest_meta() -> dict | None:
    return await _require().get_latest_meta()


async def is_db_seeded() -> bool:
    return await _require().count_firs() > 0


async def clear_all() -> None:
    await _require().clear_all()
