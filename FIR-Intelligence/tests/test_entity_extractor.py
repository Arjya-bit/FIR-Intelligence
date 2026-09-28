"""Regex entity extraction from FIR narrative text."""

import pytest

from entity_extractor import (
    compute_severity,
    extract_accused,
    extract_ipc_sections,
    extract_modus_operandi,
    extract_phone_numbers,
    extract_stolen_values,
    extract_victims,
)


class TestAccused:
    def test_trigger_word_is_not_captured_as_the_name(self):
        """Regression: the patterns were compiled with re.IGNORECASE, which
        makes [A-Z][a-z]+ match lowercase words, so this yielded an accused
        called "identified as Bablu"."""
        accused = extract_accused(
            "Accused identified as Bablu alias Bhura. Sections: 392 IPC.")
        assert [a.name for a in accused] == ["Bablu"]
        assert accused[0].aliases == ["Bhura"]

    def test_multiple_comma_separated_accused(self):
        accused = extract_accused(
            "Accused: Bablu alias Bhura, Sunny alias Sonu, Deepak. Sections: 392 IPC.")
        assert [a.name for a in accused] == ["Bablu", "Sunny", "Deepak"]

    def test_numbered_list_with_attributes(self):
        accused = extract_accused(
            "Arrested: (1) Shakeel Ahmed alias Kalu, age 35, S/o Shri Jameel Ahmed, "
            "R/o Lisari Gate, Meerut — the kingpin, (2) Guddu Khan, age 28.")
        assert [a.name for a in accused] == ["Shakeel Ahmed", "Guddu Khan"]
        assert accused[0].age == 35
        assert accused[0].father_name == "Jameel Ahmed"
        assert accused[0].address == "Lisari Gate"
        assert accused[1].age == 28

    def test_quoted_nickname(self):
        accused = extract_accused(
            "One passerby identified the knife-wielding accused as 'Bablu' who is "
            "known in the Charbagh area.")
        assert [a.name for a in accused] == ["Bablu"]

    def test_place_names_are_not_people(self):
        """Regression: "(arrested in FIR/2024/MR/014, Meerut)" produced an
        accused named Meerut."""
        accused = extract_accused(
            "Phone records reveal contacts with Shakeel Ahmed alias Kalu "
            "(arrested in FIR/2024/MR/014, Meerut) and Guddu Khan "
            "(arrested in FIR/2024/VN/008, Varanasi).")
        assert "Meerut" not in [a.name for a in accused]
        assert "Varanasi" not in [a.name for a in accused]

    def test_narrative_nouns_are_not_accused(self):
        assert extract_accused(
            "The accused persons fled towards Charbagh railway station.") == []
        assert extract_accused(
            "Accused entered by cutting the rear wall and dismantled the alarm.") == []

    def test_as_inside_a_word_is_not_a_trigger(self):
        """Regression: "as" lacked a word boundary, so "associates" matched."""
        accused = extract_accused(
            "The accused were identified as associates of the Munna Bhai gang.")
        assert accused == []

    def test_unnamed_accused_yields_nothing(self):
        assert extract_accused("Unknown persons broke into the shop at night.") == []

    def test_empty_text(self):
        assert extract_accused("") == []


class TestVictims:
    def test_complainant_with_gender_age_and_address(self):
        victims = extract_victims(
            "Complainant: Shri Rajesh Kumar Sharma, age 45 years, "
            "S/o Late Shri Hari Prasad, R/o Gomti Nagar, Lucknow.")
        assert victims[0].name == "Rajesh Kumar Sharma"
        assert victims[0].age == 45
        assert victims[0].gender == "Male"
        assert victims[0].address == "Gomti Nagar"

    def test_female_honorific(self):
        victims = extract_victims("Complainant: Smt. Priya Tiwari, age 32 years.")
        assert victims[0].gender == "Female"

    def test_additional_named_victim(self):
        victims = extract_victims(
            "Complainant: Shri Ram Kumar, age 40. The deceased Mohan Lal (age 55) "
            "was found at the site.")
        assert {v.name for v in victims} == {"Ram Kumar", "Mohan Lal"}

    def test_no_duplicates(self):
        victims = extract_victims(
            "Complainant: Shri Ram Kumar, age 40. The victim Ram Kumar was hospitalised.")
        assert len(victims) == 1


class TestOtherExtractors:
    def test_ipc_sections(self):
        assert extract_ipc_sections("Sections: 392, 397 IPC.") == ["392", "397 IPC"]

    def test_phone_numbers(self):
        assert extract_phone_numbers("Contact 9876543210 or +91-8123456789") == [
            "9876543210", "8123456789"]

    @pytest.mark.parametrize("text,expected", [
        ("stolen goods worth Rs. 1,25,000", 125000.0),
        ("seizure valued at Rs. 5 crore", 50_000_000.0),
        ("cash of Rs. 2 lakh", 200_000.0),
        ("no monetary value mentioned", 0.0),
    ])
    def test_stolen_values(self, text, expected):
        assert extract_stolen_values(text) == expected

    def test_modus_operandi(self):
        mo = extract_modus_operandi(
            "Two persons on a motorcycle snatched the chain at 2230 hours "
            "after threatening with a knife.")
        assert mo.weapon_used == "knife"
        assert mo.time_of_day == "night"
        assert mo.approach_method == "bike-borne snatching"

    def test_severity_is_bounded_and_ordered(self):
        murder = compute_severity("murder", 0, [], 1)
        theft = compute_severity("theft", 0, [], 1)
        assert 0 <= theft < murder <= 100
        assert compute_severity("murder", 50_000_000, ["pistol"], 10) == 100
