"""End-to-end HTTP tests against the real app, on the in-memory store."""

import json
import os

import pytest

os.environ.setdefault("FIR_STORAGE", "memory")
os.environ.setdefault("FIR_SEED_SIZE", "40")

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(main.app) as test_client:
        yield test_client


class TestMeta:
    def test_health(self, client):
        body = client.get("/api/health").json()
        assert body["status"] == "ok"
        assert body["storage"] == "in-memory"
        assert body["firs_analyzed"] > 0

    def test_health_reports_no_credentials_honestly(self, client):
        body = client.get("/api/health").json()
        assert body["language_model"] == "rule-based analysis"
        assert body["ai_enabled"] is False
        assert body["llm"]["configured"] is False

    def test_filters_drive_the_ui_dropdowns(self, client):
        body = client.get("/api/filters").json()
        assert body["crime_types"] and body["districts"] and body["stations"]
        assert body["severities"] == ["critical", "high", "medium", "low"]

    def test_openapi_schema_builds(self, client):
        assert client.get("/openapi.json").status_code == 200


class TestDashboard:
    def test_shape(self, client):
        body = client.get("/api/dashboard").json()
        for key in ("total_firs", "total_accused", "total_districts",
                    "crime_breakdown", "district_breakdown", "monthly_trend",
                    "severity_distribution", "crime_networks",
                    "name_match_threshold"):
            assert key in body, key

    def test_counts_are_internally_consistent(self, client):
        body = client.get("/api/dashboard").json()
        assert sum(body["crime_breakdown"].values()) == body["total_firs"]
        assert sum(body["district_breakdown"].values()) == body["total_firs"]
        assert sum(body["severity_distribution"].values()) == body["total_firs"]

    def test_district_count_matches_the_breakdown(self, client):
        """The UI used to print a hardcoded "across 7 districts"."""
        body = client.get("/api/dashboard").json()
        assert body["total_districts"] == len(body["district_breakdown"])


class TestFIRs:
    def test_returns_a_paginated_envelope(self, client):
        body = client.get("/api/firs?limit=5").json()
        assert set(body) >= {"items", "total", "limit", "offset", "has_more"}
        assert len(body["items"]) == 5
        assert body["has_more"] is True

    def test_paging_does_not_repeat_records(self, client):
        first = client.get("/api/firs?limit=5&offset=0").json()["items"]
        second = client.get("/api/firs?limit=5&offset=5").json()["items"]
        assert not ({f["fir_number"] for f in first} & {f["fir_number"] for f in second})

    def test_offset_past_the_end_is_empty_not_an_error(self, client):
        body = client.get("/api/firs?limit=5&offset=100000").json()
        assert body["items"] == []
        assert body["has_more"] is False

    def test_filters(self, client):
        body = client.get("/api/firs?crime_type=theft&limit=100").json()
        assert all(f["crime_type"] == "theft" for f in body["items"])

    def test_severity_filter(self, client):
        body = client.get("/api/firs?severity=critical&limit=100").json()
        assert all(f["severity"] == "critical" for f in body["items"])

    def test_search(self, client):
        body = client.get("/api/firs?q=burglary&limit=100").json()
        assert body["total"] >= 1

    def test_search_with_no_hits_is_empty_not_an_error(self, client):
        body = client.get("/api/firs?q=zzzznotpresentzzzz").json()
        assert body["total"] == 0 and body["items"] == []

    def test_invalid_limit_is_rejected(self, client):
        assert client.get("/api/firs?limit=99999").status_code == 422
        assert client.get("/api/firs?severity=bogus").status_code == 422

    def test_list_and_detail_agree_on_field_names(self, client):
        """The two endpoints used to disagree (date vs date_filed, flat vs
        nested entities), so the detail view could not reuse list data."""
        item = client.get("/api/firs?limit=1").json()["items"][0]
        detail = client.get(f"/api/firs/{item['fir_number']}").json()
        for key in ("fir_number", "date", "district", "crime_type", "severity",
                    "entities"):
            assert key in detail
            assert detail[key] == item[key] or key == "entities"

    def test_detail_handles_slashes_in_the_fir_number(self, client):
        number = client.get("/api/firs?limit=1").json()["items"][0]["fir_number"]
        assert "/" in number
        assert client.get(f"/api/firs/{number}").json()["fir_number"] == number

    def test_detail_returns_untruncated_text_and_links(self, client):
        number = client.get("/api/firs?limit=1").json()["items"][0]["fir_number"]
        detail = client.get(f"/api/firs/{number}").json()
        assert detail["text_truncated"] is False
        assert isinstance(detail["related"], list)

    def test_missing_fir(self, client):
        assert client.get("/api/firs/NOPE/2099/ZZ/999").status_code == 404


class TestAnalytics:
    def test_repeat_offenders(self, client):
        body = client.get("/api/repeat-offenders").json()
        assert all(o["fir_count"] >= 2 for o in body)
        assert all(len(o["linked_firs"]) == o["fir_count"] for o in body)

    def test_repeat_offender_filters(self, client):
        body = client.get("/api/repeat-offenders?risk_level=critical").json()
        assert all(o["risk_level"] == "critical" for o in body)
        assert client.get("/api/repeat-offenders?risk_level=nope").status_code == 422
        assert client.get("/api/repeat-offenders?min_incidents=1").status_code == 422

    def test_stations_carry_a_risk_badge(self, client):
        body = client.get("/api/stations").json()
        assert body
        assert all(s["risk_level"] in {"low", "medium", "high"} for s in body)

    def test_networks_are_bounded_and_annotated(self, client):
        total = client.get("/api/dashboard").json()["total_firs"]
        for net in client.get("/api/networks").json():
            assert 2 <= net["fir_count"] <= total
            assert net["link_basis"]
            assert net["risk_level"] in {"low", "medium", "high", "critical"}

    def test_networks_do_not_swallow_the_corpus(self, client):
        """Regression: single-linkage put 96 of 100 FIRs in one 'network'."""
        total = client.get("/api/dashboard").json()["total_firs"]
        nets = client.get("/api/networks").json()
        assert all(n["fir_count"] <= max(8, total // 6) for n in nets)

    def test_trends(self, client):
        body = client.get("/api/trends").json()
        assert all(isinstance(v, dict) for v in body.values())


class TestChatAndReport:
    def test_chat_answers_from_the_corpus(self, client):
        body = client.post("/api/chat", json={"message": "Who are the repeat offenders?"}).json()
        assert body["response"]
        total = client.get("/api/dashboard").json()["total_firs"]
        assert str(total) in body["response"] or "repeat offender" in body["response"].lower()

    def test_chat_cites_real_fir_numbers(self, client):
        body = client.post("/api/chat", json={"message": "Who are the repeat offenders?"}).json()
        known = {f["fir_number"] for f in client.get("/api/firs?limit=500").json()["items"]}
        assert all(number in known for number in body["firs_referenced"])

    def test_chat_rejects_an_empty_message(self, client):
        assert client.post("/api/chat", json={"message": "   "}).status_code == 400
        assert client.post("/api/chat", json={}).status_code == 422

    def test_report_matches_the_corpus(self, client):
        body = client.get("/api/report").json()
        total = client.get("/api/dashboard").json()["total_firs"]
        assert body["metadata"]["total_firs"] == total
        assert f"{total} FIRs" in body["report"]
        assert body["source"] == "rule-based analysis"
        # The computed analysis is always returned alongside the prose, so the
        # UI can show what the narrative was derived from.
        assert body["analysis"]

    def test_report_is_regenerated_not_cached(self, client):
        """The corpus changes as FIRs are ingested; a cached report goes stale."""
        first = client.get("/api/report").json()["generated_at"]
        second = client.get("/api/report").json()["generated_at"]
        assert first != second

    def test_report_accepts_a_focus(self, client):
        body = client.get("/api/report", params={"focus": "narcotics"}).json()
        assert body["focus"] == "narcotics"


class TestUpload:
    def _post(self, client, payload, name="batch.json"):
        data = payload if isinstance(payload, (str, bytes)) else json.dumps(payload)
        return client.post("/api/upload-firs",
                           files={"file": (name, data, "application/json")})

    def test_valid_batch_is_ingested_and_analysed(self, client):
        before = client.get("/api/dashboard").json()["total_firs"]
        res = self._post(client, [{
            "fir_number": "UPLOAD/TEST/001",
            "date_filed": "2025-03-04",
            "police_station": "Hazratganj PS",
            "district": "Lucknow",
            "raw_text": "Two bike-borne persons snatched a gold chain near "
                        "Hazratganj. Accused identified as Bablu alias Bhura. "
                        "Sections: 392 IPC.",
        }])
        assert res.status_code == 200
        assert res.json()["accepted"] == 1
        assert client.get("/api/dashboard").json()["total_firs"] == before + 1
        detail = client.get("/api/firs/UPLOAD/TEST/001").json()
        assert detail["crime_type"] == "robbery"

    @pytest.mark.parametrize("payload,expected", [
        ("not json at all", 400),
        ({"not": "an array"}, 400),
        ([], 400),
        ([{"raw_text": "no fir number"}], 400),
        ([{"fir_number": "X/1"}], 400),
        (["a bare string"], 400),
    ])
    def test_malformed_batches_are_rejected(self, client, payload, expected):
        assert self._post(client, payload).status_code == expected

    def test_rejection_explains_which_record_failed(self, client):
        body = self._post(client, [{"raw_text": "no number"}]).json()
        assert body["detail"]["errors"][0]["index"] == 0
        assert "fir_number" in body["detail"]["errors"][0]["error"]

    def test_oversized_upload_is_refused(self, client, monkeypatch):
        monkeypatch.setattr(main, "MAX_UPLOAD_BYTES", 10)
        assert self._post(client, [{"fir_number": "Y/1", "raw_text": "x" * 200}]
                          ).status_code == 413


class TestDashboardAssets:
    def test_index_is_served(self, client):
        res = client.get("/")
        assert res.status_code == 200
        assert "FIR Intelligence" in res.text

    def test_compiled_bundle_and_vendor_assets_are_served(self, client):
        """Regression: only "/" was routed, so every asset 404'd."""
        assert client.get("/app.js").status_code == 200
        assert client.get("/vendor/react.min.js").status_code == 200

    def test_the_bundle_is_in_sync_with_its_source(self):
        """A stale app.js silently ships the previous UI."""
        from pathlib import Path

        root = Path(main.__file__).parent
        source = root / "static" / "app.jsx"
        bundle = root / "static" / "app.js"
        assert bundle.stat().st_mtime >= source.stat().st_mtime, (
            "static/app.js is older than static/app.jsx — run ./scripts/build-ui.sh"
        )
