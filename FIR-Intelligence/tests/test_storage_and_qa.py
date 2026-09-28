"""In-memory storage backend and the deterministic intelligence answerer."""

import pytest

import database as db
import intel_qa
from models import AnalysisResult, CrimeType, RiskLevel
from nlp_engine import analyze_fir_batch
from pattern_detector import detect_crime_networks


@pytest.fixture
async def memory_db(monkeypatch):
    monkeypatch.setattr(db, "STORAGE_PREFERENCE", "memory")
    await db.connect()
    yield db
    await db.disconnect()


def fir_doc(number, *, district="Lucknow", crime="theft", severity=35.0,
            day=1, accused=None, victims=None):
    return {
        "fir_number": number,
        "date_filed": f"2024-0{day}-15",
        "police_station": "Hazratganj PS",
        "district": district,
        "state": "Uttar Pradesh",
        "raw_text": f"FIR {number}: narrative text about a {crime}.",
        "crime_type": crime,
        "severity_score": severity,
        "accused": accused or [{"name": "Ram Kumar", "aliases": []}],
        "victims": victims or [{"name": "Shyam Lal"}],
        "ipc_sections": ["379 IPC"],
    }


class TestMemoryBackend:
    async def test_falls_back_without_mongodb(self, memory_db):
        """The service must boot with no database server running."""
        assert memory_db.backend_name() == "in-memory"
        assert memory_db.is_persistent() is False

    async def test_insert_and_read_back(self, memory_db):
        assert await memory_db.insert_firs([fir_doc("A/1"), fir_doc("A/2")]) == 2
        assert await memory_db.count_firs() == 2
        assert (await memory_db.get_fir("A/1"))["district"] == "Lucknow"
        assert await memory_db.get_fir("missing") is None

    async def test_duplicate_fir_numbers_are_skipped(self, memory_db):
        await memory_db.insert_firs([fir_doc("B/1")])
        assert await memory_db.insert_firs([fir_doc("B/1")]) == 0
        assert await memory_db.count_firs() == 1

    async def test_upsert_replaces(self, memory_db):
        await memory_db.insert_firs([fir_doc("C/1", district="Agra")])
        await memory_db.upsert_fir(fir_doc("C/1", district="Meerut"))
        assert (await memory_db.get_fir("C/1"))["district"] == "Meerut"
        assert await memory_db.count_firs() == 1

    async def test_filters_and_pagination(self, memory_db):
        await memory_db.insert_firs([
            fir_doc("D/1", district="Agra", crime="theft"),
            fir_doc("D/2", district="Meerut", crime="fraud"),
            fir_doc("D/3", district="Agra", crime="fraud"),
        ])
        assert len(await memory_db.get_all_firs(district="Agra")) == 2
        assert len(await memory_db.get_all_firs(crime_type="fraud")) == 2
        assert len(await memory_db.get_all_firs(limit=2)) == 2
        assert len(await memory_db.get_all_firs(skip=2, limit=10)) == 1

    async def test_aggregations(self, memory_db):
        await memory_db.insert_firs([
            fir_doc("E/1", crime="theft", severity=85.0, day=1),
            fir_doc("E/2", crime="theft", severity=45.0, day=2),
            fir_doc("E/3", crime="murder", severity=95.0, day=2),
        ])
        assert await memory_db.get_crime_breakdown() == {"theft": 2, "murder": 1}
        assert await memory_db.get_monthly_trend() == {"2024-01": 1, "2024-02": 2}
        assert await memory_db.get_severity_distribution() == {
            "low": 0, "medium": 1, "high": 0, "critical": 2}
        stats = await memory_db.get_fir_stats()
        assert stats["total"] == 3
        assert stats["total_accused"] == 3

    async def test_stats_on_empty_store(self, memory_db):
        assert await memory_db.get_fir_stats() == {}
        assert await memory_db.get_crime_breakdown() == {}
        assert await memory_db.get_severity_distribution() == {
            "low": 0, "medium": 0, "high": 0, "critical": 0}

    async def test_search(self, memory_db):
        await memory_db.insert_firs([fir_doc("F/1", crime="burglary"),
                                     fir_doc("F/2", crime="theft")])
        assert len(await memory_db.search_firs("burglary")) == 1
        assert await memory_db.search_firs("") == []

    async def test_stored_documents_are_isolated_copies(self, memory_db):
        """A caller mutating a returned dict must not corrupt the store."""
        await memory_db.insert_firs([fir_doc("G/1")])
        doc = await memory_db.get_fir("G/1")
        doc["district"] = "TAMPERED"
        assert (await memory_db.get_fir("G/1"))["district"] == "Lucknow"

    async def test_clear_all(self, memory_db):
        await memory_db.insert_firs([fir_doc("H/1")])
        await memory_db.save_offenders([{"name": "x", "total_incidents": 2}])
        await memory_db.clear_all()
        assert await memory_db.count_firs() == 0
        assert await memory_db.get_offenders() == []

    async def test_driver_import_panic_falls_back(self, monkeypatch):
        """Regression: a broken system `cryptography` makes pymongo's TLS import
        raise pyo3_runtime.PanicException, which derives from BaseException.
        `except Exception` missed it and the service refused to start."""
        class Panic(BaseException):
            pass

        async def boom(*_args, **_kwargs):
            raise Panic("Python API call failed")

        monkeypatch.setattr(db, "STORAGE_PREFERENCE", "auto")
        monkeypatch.setattr(db.MongoBackend, "create", boom)
        assert await db.connect() == "in-memory"
        await db.disconnect()

    async def test_explicit_mongodb_still_fails_loudly(self, monkeypatch):
        async def boom(*_args, **_kwargs):
            raise ConnectionError("refused")

        monkeypatch.setattr(db, "STORAGE_PREFERENCE", "mongodb")
        monkeypatch.setattr(db.MongoBackend, "create", boom)
        with pytest.raises(RuntimeError, match="could not be used"):
            await db.connect()

    async def test_cancellation_is_not_swallowed(self, monkeypatch):
        import asyncio

        async def cancelled(*_args, **_kwargs):
            raise asyncio.CancelledError

        monkeypatch.setattr(db, "STORAGE_PREFERENCE", "auto")
        monkeypatch.setattr(db.MongoBackend, "create", cancelled)
        with pytest.raises(asyncio.CancelledError):
            await db.connect()

    async def test_requires_connect(self, monkeypatch):
        monkeypatch.setattr(db, "_backend", None)
        with pytest.raises(RuntimeError, match="call database.connect"):
            await db.count_firs()


@pytest.fixture
async def analysis() -> tuple[AnalysisResult, list[dict]]:
    docs = [
        fir_doc("N/1", crime="robbery", severity=75.0,
                accused=[{"name": "Bablu", "aliases": ["Bhura"]}]),
        fir_doc("N/2", crime="robbery", severity=70.0,
                accused=[{"name": "Bablu", "aliases": ["Bhura"]}]),
        fir_doc("N/3", crime="theft", severity=35.0, district="Agra",
                accused=[{"name": "Mohan Lal", "aliases": []}]),
    ]
    result = await analyze_fir_batch(docs)
    return result, detect_crime_networks(result.fir_records)


class TestIntelQA:
    async def test_offender_question_uses_real_data(self, analysis):
        result, nets = analysis
        answer = intel_qa.answer_question("Who are the repeat offenders?", result, nets)
        assert "Bablu" in answer
        assert "N/1" in answer and "N/2" in answer
        # Nothing from the old canned narrative should appear.
        assert "Jamtara" not in answer

    async def test_named_person_lookup(self, analysis):
        result, nets = analysis
        answer = intel_qa.answer_question("Tell me about Bablu", result, nets)
        assert "repeat offender profile" in answer
        assert "Bhura" in answer

    async def test_fir_number_lookup(self, analysis):
        result, nets = analysis
        assert "N/3" in intel_qa.answer_question("Show me N/3", result, nets)

    async def test_district_question(self, analysis):
        result, nets = analysis
        answer = intel_qa.answer_question("Which districts have the most crime?",
                                          result, nets)
        assert "Lucknow" in answer and "Agra" in answer

    async def test_absent_topic_is_not_fabricated(self, analysis):
        """The corpus has no drug cases, so the answer must not invent one."""
        result, nets = analysis
        answer = intel_qa.answer_question("Tell me about the heroin supply chain",
                                          result, nets)
        assert "Nepal" not in answer
        assert "15kg" not in answer and "15 kg" not in answer

    async def test_empty_corpus_is_stated_plainly(self):
        empty = AnalysisResult(total_firs_processed=0, fir_records=[],
                               repeat_offenders=[], station_summaries=[],
                               crime_trend={}, entity_stats={})
        answer = intel_qa.answer_question("Who are the repeat offenders?", empty, [])
        assert "nothing to report" in answer.lower()

    async def test_report_reflects_the_corpus(self, analysis):
        result, nets = analysis
        report = intel_qa.build_report(result, nets)
        assert "3 FIRs" in report
        assert "EXECUTIVE SUMMARY" in report
        assert "RECOMMENDED ACTIONS" in report
        assert "verification by the investigating officer" in report

    async def test_report_on_empty_corpus(self):
        empty = AnalysisResult(total_firs_processed=0, fir_records=[],
                               repeat_offenders=[], station_summaries=[],
                               crime_trend={}, entity_stats={})
        assert "No FIRs analysed" in intel_qa.build_report(empty, [])


class TestPipeline:
    async def test_structured_fields_are_preserved(self, analysis):
        result, _ = analysis
        record = next(f for f in result.fir_records if f.fir_number == "N/1")
        assert record.crime_type == CrimeType.ROBBERY
        assert record.severity_score == 75.0
        assert [a.name for a in record.accused] == ["Bablu"]

    async def test_crime_type_inferred_when_absent(self):
        result = await analyze_fir_batch([{
            "fir_number": "X/1", "date_filed": "2024-01-01",
            "police_station": "PS", "district": "Lucknow",
            "raw_text": "Complainant reports the accused broke into the shop by "
                        "cutting the lock with a gas cutter. Sections: 457 IPC.",
        }])
        assert result.fir_records[0].crime_type == CrimeType.BURGLARY

    async def test_repeat_offender_risk(self, analysis):
        result, _ = analysis
        assert result.repeat_offenders[0].risk_level in set(RiskLevel)

    async def test_empty_batch(self):
        result = await analyze_fir_batch([])
        assert result.total_firs_processed == 0
        assert result.repeat_offenders == []
