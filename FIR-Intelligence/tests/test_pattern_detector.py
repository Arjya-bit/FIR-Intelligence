"""Identity resolution, station rollups and network detection."""

from datetime import date

import pytest

from models import AccusedProfile, CrimeType, FIRRecord, ModusOperandi, RiskLevel
from pattern_detector import (
    detect_crime_networks,
    detect_repeat_offenders,
    generate_station_summaries,
    names_match,
    normalize_name,
)


def make_fir(number, *, accused=(), district="Lucknow", station="Hazratganj PS",
             crime=CrimeType.ROBBERY, day=1, approach=None, severity=60.0,
             text=""):
    return FIRRecord(
        fir_number=number,
        date_filed=date(2024, 1, day),
        police_station=station,
        district=district,
        raw_text=text or f"FIR {number} narrative.",
        crime_type=crime,
        severity_score=severity,
        accused=[a if isinstance(a, AccusedProfile) else AccusedProfile(name=a)
                 for a in accused],
        modus_operandi=ModusOperandi(description="", approach_method=approach)
        if approach else None,
    )


class TestNameNormalisation:
    def test_strips_honorifics_and_punctuation(self):
        assert normalize_name("Shri  Rajesh Kumar.") == "rajesh kumar"
        assert normalize_name("Smt. Priya Tiwari") == "priya tiwari"

    def test_exact_match(self):
        assert names_match("Chhote Lal", "chhote lal")

    def test_close_multi_token_names_match(self):
        assert names_match("Shakeel Ahmed Khan", "Shakeel Ahmad Khan")

    def test_single_token_names_never_fuzzy_match(self):
        # "Bablu" and "Bablo" are far too collision-prone to link on similarity.
        assert not names_match("Bablu", "Bablo")

    def test_unrelated_names_do_not_match(self):
        assert not names_match("Sunil Yadav", "Pappu Yadav")


class TestRepeatOffenders:
    def test_same_full_name_across_districts_is_one_identity(self):
        firs = [
            make_fir("A/1", accused=["Chhote Lal"], district="Gorakhpur"),
            make_fir("A/2", accused=["Chhote Lal"], district="Meerut"),
        ]
        offenders = detect_repeat_offenders(firs)
        assert len(offenders) == 1
        assert offenders[0].total_incidents == 2
        assert sorted(offenders[0].districts) == ["Gorakhpur", "Meerut"]

    def test_alias_links_two_firs_within_a_district(self):
        firs = [
            make_fir("B/1", accused=[AccusedProfile(name="Bablu", aliases=["Bhura"])]),
            make_fir("B/2", accused=["Bhura"]),
        ]
        offenders = detect_repeat_offenders(firs)
        assert len(offenders) == 1
        assert offenders[0].total_incidents == 2

    def test_shared_common_alias_does_not_merge_strangers(self):
        """Regression: nicknames are shared by thousands of unrelated people.

        Treating one as an identifier chained every FIR in the corpus into a
        single bogus offender with 86 linked FIRs.
        """
        firs = [
            make_fir("C/1", accused=[AccusedProfile(name="Ramesh Gupta", aliases=["Chhotu"])],
                     district="Agra"),
            make_fir("C/2", accused=[AccusedProfile(name="Suresh Verma", aliases=["Chhotu"])],
                     district="Meerut"),
            make_fir("C/3", accused=[AccusedProfile(name="Dinesh Rawat", aliases=["Chhotu"])],
                     district="Jhansi"),
        ]
        assert detect_repeat_offenders(firs) == []

    def test_identity_linking_is_transitive(self):
        """FIR-1 <-> FIR-2 and FIR-2 <-> FIR-3 must put all three together."""
        firs = [
            make_fir("D/1", accused=[AccusedProfile(name="Bablu", aliases=["Bhura"])]),
            make_fir("D/2", accused=[AccusedProfile(name="Bhura", aliases=["Bablu Kumar"])]),
            make_fir("D/3", accused=["Bablu Kumar"]),
        ]
        offenders = detect_repeat_offenders(firs)
        assert len(offenders) == 1
        assert offenders[0].total_incidents == 3

    def test_one_person_twice_in_one_fir_is_not_a_repeat_offender(self):
        firs = [make_fir("E/1", accused=["Ram Kumar", "Ram Kumar"])]
        assert detect_repeat_offenders(firs) == []

    def test_min_incidents_threshold(self):
        firs = [make_fir(f"F/{i}", accused=["Ram Kumar"]) for i in range(1, 4)]
        assert len(detect_repeat_offenders(firs, min_incidents=2)) == 1
        assert detect_repeat_offenders(firs, min_incidents=4) == []

    def test_risk_escalates_with_spread(self):
        firs = [make_fir(f"G/{i}", accused=["Ram Kumar"], district=d)
                for i, d in enumerate(["Agra", "Meerut", "Jhansi"], start=1)]
        assert detect_repeat_offenders(firs)[0].risk_level == RiskLevel.CRITICAL

    def test_empty_corpus(self):
        assert detect_repeat_offenders([]) == []


class TestStationSummaries:
    def test_same_station_name_in_two_districts_stays_separate(self):
        """"Kotwali PS" exists in most UP districts; keying on the name alone
        merged their caseloads into one inflated station."""
        firs = [
            make_fir("H/1", station="Kotwali PS", district="Meerut"),
            make_fir("H/2", station="Kotwali PS", district="Jhansi"),
        ]
        summaries = generate_station_summaries(firs, [])
        assert len(summaries) == 2
        assert {s.district for s in summaries} == {"Meerut", "Jhansi"}
        assert all(s.total_firs == 1 for s in summaries)

    def test_counts_and_top_crime(self):
        firs = [make_fir("I/1", crime=CrimeType.THEFT),
                make_fir("I/2", crime=CrimeType.THEFT),
                make_fir("I/3", crime=CrimeType.MURDER)]
        summary = generate_station_summaries(firs, [])[0]
        assert summary.total_firs == 3
        assert summary.top_crime == "theft"


class TestCrimeNetworks:
    def test_shared_offender_forms_a_network(self):
        firs = [make_fir(f"J/{i}", accused=["Chhote Lal"]) for i in range(1, 4)]
        networks = detect_crime_networks(firs)
        assert len(networks) == 1
        assert networks[0]["fir_count"] == 3
        assert "Chhote Lal" in networks[0]["key_members"]
        assert "shared offender" in networks[0]["link_basis"]

    def test_unrelated_firs_form_no_network(self):
        firs = [make_fir("K/1", accused=["Ram Kumar"], district="Agra"),
                make_fir("K/2", accused=["Shyam Singh"], district="Meerut",
                         crime=CrimeType.FRAUD)]
        assert detect_crime_networks(firs) == []

    def test_clusters_are_capped(self):
        """Regression: single-linkage over a shared MO chained 96 of 100 FIRs
        into one meaningless 'network'."""
        firs = [make_fir(f"L/{i}", approach="bike-borne snatching")
                for i in range(1, 41)]
        networks = detect_crime_networks(firs, max_size=8)
        assert networks, "expected at least one cluster"
        assert all(n["fir_count"] <= 8 for n in networks)

    def test_known_gang_label_requires_majority_mention(self):
        """A single stray mention must not name the whole network."""
        firs = [make_fir("M/1", accused=["Ram Kumar"], text="Money trail leads to Jamtara."),
                make_fir("M/2", accused=["Ram Kumar"], text="Routine theft near the market."),
                make_fir("M/3", accused=["Ram Kumar"], text="Routine theft near the market.")]
        assert detect_crime_networks(firs)[0]["name"] != "Jamtara Cyber Fraud Network"

    def test_network_carries_period_and_risk(self):
        firs = [make_fir("N/1", accused=["Ram Kumar"], day=3),
                make_fir("N/2", accused=["Ram Kumar"], day=17)]
        net = detect_crime_networks(firs)[0]
        assert net["active_period"] == {"start": "2024-01-03", "end": "2024-01-17"}
        assert net["risk_level"] in {"low", "medium", "high", "critical"}

    def test_empty_corpus(self):
        assert detect_crime_networks([]) == []


@pytest.mark.parametrize("count", [0, 1, 2, 25])
def test_detectors_never_raise_on_arbitrary_sizes(count):
    firs = [make_fir(f"P/{i}", accused=["Ram Kumar"]) for i in range(count)]
    detect_repeat_offenders(firs)
    generate_station_summaries(firs, [])
    detect_crime_networks(firs)
