import pytest

from src.models import RateUnavailable, UnknownSection
from src.tools import convert_to_eur, get_handbook_section, search_handbook


def test_convert_to_eur_eur_passthrough():
    assert convert_to_eur(100.0, "EUR", "2026-01-15") == 100.0


def test_convert_to_eur_known_month():
    result = convert_to_eur(100.0, "SEK", "2026-01-15")
    assert result > 0
    assert result != 100.0


def test_convert_to_eur_missing_month_boundary_raises():
    with pytest.raises(RateUnavailable):
        convert_to_eur(100.0, "SEK", "2026-02-15")
    convert_to_eur(100.0, "SEK", "2026-01-31")
    convert_to_eur(100.0, "SEK", "2026-03-01")


def test_get_handbook_section_unknown_raises():
    with pytest.raises(UnknownSection):
        get_handbook_section("S99")


def test_get_handbook_section_returns_full_text():
    text = get_handbook_section("S3")
    assert "S3" in text
    assert "per night" in text


def test_search_handbook_finds_lodging_cap():
    hits = search_handbook("lodging cap per night")
    section_ids = [h["section_id"] for h in hits]
    assert "S3" in section_ids
