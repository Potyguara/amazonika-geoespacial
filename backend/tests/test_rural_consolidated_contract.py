"""Fail-closed data-contract tests for the full-farm consolidated report.

No SICAR, Earth Engine, PostGIS, network or paid operations.
"""
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.schemas.rural_consolidated import (
    ConsolidatedReportSnapshot,
    ConsolidatedSection,
    PropertySnapshot,
    SectionCode,
    SectionStatus,
    SourceEvidence,
    status_label,
)

NOW = datetime(2026, 11, 5, tzinfo=timezone.utc)


def evidence(count=0, completed=True):
    return SourceEvidence(
        source_name="IBAMA — Embargos", institution="IBAMA",
        queried_at=NOW, query_completed=completed,
        result_count=count if completed else None,
        source_version="WFS consulta 2026-11-05",
    )


def test_no_occurrence_requires_real_completed_query():
    with pytest.raises(ValidationError, match="pelo menos uma consulta"):
        ConsolidatedSection(code=SectionCode.ENVIRONMENTAL_ENFORCEMENT, status=SectionStatus.NO_OCCURRENCE)


def test_no_occurrence_requires_zero_results():
    with pytest.raises(ValidationError, match="retornam zero"):
        ConsolidatedSection(
            code=SectionCode.ENVIRONMENTAL_ENFORCEMENT,
            status=SectionStatus.NO_OCCURRENCE, evidence=[evidence(count=2)],
        )


def test_completed_cannot_hide_failed_provider():
    with pytest.raises(ValidationError, match="fontes inconclusivas"):
        ConsolidatedSection(
            code=SectionCode.ENVIRONMENTAL_ENFORCEMENT,
            status=SectionStatus.COMPLETE,
            evidence=[evidence(2), evidence(completed=False)],
        )


def test_source_counts_not_asserted_on_failed_query():
    with pytest.raises(ValidationError, match="inconclusiva"):
        SourceEvidence(
            source_name="SICAR", institution="SFB",
            queried_at=NOW, query_completed=False, result_count=0,
        )


def test_successfully_queried_zero_is_allowed():
    item = ConsolidatedSection(
        code=SectionCode.ENVIRONMENTAL_ENFORCEMENT,
        status=SectionStatus.NO_OCCURRENCE, evidence=[evidence(0)],
    )
    assert status_label(item.status) == "Consulta concluída sem ocorrências"


def test_budget_block_cannot_create_quantitative_conclusion():
    with pytest.raises(ValidationError, match="seção concluída"):
        ConsolidatedSection(
            code=SectionCode.LAND_COVER_MAPBIOMAS,
            status=SectionStatus.SKIPPED_BUDGET,
            metrics={"forest_area_ha": 0},
        )


def test_consolidated_report_requires_unique_sections():
    prop = PropertySnapshot(
        name="Imóvel de homologação", geometry_sha256="a" * 64,
        geometry_crs="EPSG:4674", area_hectares=186.6908,
        cadastral_origin="SIGEF", captured_at=NOW,
    )
    with pytest.raises(ValidationError, match="duplicado"):
        ConsolidatedReportSnapshot(
            property=prop, created_at=NOW,
            sections=[
                ConsolidatedSection(code=SectionCode.TERRITORIAL_OVERLAYS),
                ConsolidatedSection(code=SectionCode.TERRITORIAL_OVERLAYS),
            ],
        )


def test_valid_consolidated_contract_preserves_unavailable_section():
    prop = PropertySnapshot(
        name="Imóvel de homologação", geometry_sha256="b" * 64,
        geometry_crs="EPSG:4674", area_hectares=186.6908,
        cadastral_origin="SIGEF", captured_at=NOW,
    )
    report = ConsolidatedReportSnapshot(
        property=prop, created_at=NOW,
        sections=[
            ConsolidatedSection(
                code=SectionCode.ENVIRONMENTAL_ENFORCEMENT,
                status=SectionStatus.NO_OCCURRENCE,
                evidence=[evidence(0)],
            ),
            ConsolidatedSection(
                code=SectionCode.LAND_COVER_MAPBIOMAS,
                status=SectionStatus.SKIPPED_BUDGET,
            ),
        ],
    )
    assert report.report_type == "FULL_FARM_CONSOLIDATED"
    assert report.sections[1].status is SectionStatus.SKIPPED_BUDGET
