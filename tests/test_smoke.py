"""
End-to-end smoke test for the CORESWAP pipeline.
Uses sample text files (no real PDF, no real LLM calls) to verify every
module wires together and produces a readable PDF artifact.
"""

import os
import sys
import json
import pytest

# Ensure project root is on path when run from any directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from coreswap.db import init_db, save_report, load_report
from coreswap.models import FactoryProfile, ExtractedEPDData
from coreswap.extraction import extract_text_from_txt
from coreswap.validation import validate_extraction
from coreswap.lca import run_lca
from coreswap.report import render_pdf


SAMPLE_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "sample_epds")


def _fake_extracted(gwp: float, insulation_type: str) -> ExtractedEPDData:
    return ExtractedEPDData(
        product_name="Test Product",
        manufacturer="Test Mfg",
        declared_unit="1 sq ft at R-20",
        gwp_kg_co2e_per_sqft=gwp,
        reference_standard="ISO 14025",
        validity_year=2025,
        extraction_confidence="high",
        extraction_notes="Synthetic test value.",
    )


class TestSampleTextExtraction:
    def test_spray_foam_txt_readable(self):
        path = os.path.join(SAMPLE_DIR, "spray_foam_hfc_sample.txt")
        with open(path) as f:
            text = extract_text_from_txt(f.read())
        assert "43.10" in text
        assert len(text) > 100

    def test_fiberglass_txt_readable(self):
        path = os.path.join(SAMPLE_DIR, "fiberglass_sample.txt")
        with open(path) as f:
            text = extract_text_from_txt(f.read())
        assert "7.50" in text

    def test_cellulose_txt_readable(self):
        path = os.path.join(SAMPLE_DIR, "cellulose_sample.txt")
        with open(path) as f:
            text = extract_text_from_txt(f.read())
        assert "-7.50" in text


class TestValidation:
    def test_spray_foam_hfc_passes(self):
        epd = _fake_extracted(4.0, "spray_foam_hfc")
        result = validate_extraction(epd, "spray_foam_hfc")
        assert result.passed is True

    def test_fiberglass_passes(self):
        epd = _fake_extracted(0.70, "fiberglass")
        result = validate_extraction(epd, "fiberglass")
        assert result.passed is True

    def test_cellulose_passes(self):
        epd = _fake_extracted(-0.70, "cellulose")
        result = validate_extraction(epd, "cellulose")
        assert result.passed is True

    def test_mislabeled_cellulose_as_hfc_fails(self):
        epd = _fake_extracted(-0.70, "cellulose")
        result = validate_extraction(epd, "spray_foam_hfc")
        assert result.passed is False
        assert result.insulation_type_inferred == "cellulose"
        assert result.flagged_reason is not None

    def test_implausible_value_fails(self):
        epd = _fake_extracted(999.0, "fiberglass")
        result = validate_extraction(epd, "fiberglass")
        assert result.passed is False
        assert "implausible" in result.flagged_reason.lower()


class TestLCA:
    def test_known_values(self):
        profile = FactoryProfile(
            company_name="Smoke Test Co",
            province="ON",
            annual_units=100,
            avg_home_sqft=1500,
            current_insulation="spray_foam_hfc",
        )
        lca = run_lca(profile, 4.0)
        assert lca.annual_emissions_current_tonnes == pytest.approx(960.0)
        assert lca.annual_emissions_cellulose_tonnes == pytest.approx(-175.2)
        assert lca.annual_switch_benefit_tonnes == pytest.approx(1135.2)
        assert lca.carbon_credit_value_low_cad == pytest.approx(90816.0)

    def test_lca_positive_benefit_for_hfc(self):
        profile = FactoryProfile(
            company_name="Test",
            province="BC",
            annual_units=50,
            avg_home_sqft=1200,
            current_insulation="spray_foam_hfc",
        )
        lca = run_lca(profile, 4.5)
        assert lca.annual_switch_benefit_tonnes > 0


class TestEndToEnd:
    def test_full_pipeline_produces_pdf(self, tmp_path, monkeypatch):
        # Redirect DB and reports to tmp_path
        monkeypatch.setenv("HOME", str(tmp_path))
        import coreswap.config as cfg
        cfg.DB_PATH = str(tmp_path / "coreswap.db")
        cfg.REPORTS_DIR = str(tmp_path / "reports")

        # Re-import db with patched config
        import coreswap.db as db_mod
        db_mod.DB_PATH = cfg.DB_PATH

        init_db()

        profile = FactoryProfile(
            company_name="Smoke Test Homes",
            province="ON",
            annual_units=200,
            avg_home_sqft=1400,
            current_insulation="spray_foam_hfc",
        )
        lca = run_lca(profile, 4.0)
        narrative = (
            "Current State. Smoke test narrative placeholder paragraph one. "
            "Switch Impact. Placeholder paragraph two. "
            "Regulatory Position. Placeholder paragraph three."
        )

        report_id = save_report(profile, lca, narrative, "pending")
        pdf_path = render_pdf(profile, lca, narrative, report_id)

        assert os.path.exists(pdf_path), f"PDF not found at {pdf_path}"
        assert os.path.getsize(pdf_path) > 1000, "PDF is suspiciously small"

        loaded = load_report(report_id)
        assert loaded is not None
        assert loaded.profile.company_name == "Smoke Test Homes"
        assert loaded.lca.annual_switch_benefit_tonnes > 0
