"""Tests for conservative CMS fuzzy matching and enrichment."""

import unittest

from sevah.cms_enrichment import enrich_facilities_with_cms
from sevah.cms_models import (
    CmsDataSource,
    CmsProviderRecord,
    OwnershipDataSource,
    OwnershipResult,
)
from sevah.models import Coordinates, Facility
from sevah.services.cms_api import CmsProviderError


def _facility(facility_id: str, name: str) -> Facility:
    return Facility(
        facility_id=facility_id,
        name=name,
        address="1366 W Fullerton Ave, Chicago, IL 60614",
        coordinates=Coordinates(latitude=41.9252, longitude=-87.663),
    )


def _provider(ccn: str, name: str) -> CmsProviderRecord:
    return CmsProviderRecord(
        ccn=ccn,
        provider_name=name,
        zip_code="60614",
        bed_count=248,
        overall_rating=2,
        staffing_rating=2,
        ownership_type="For profit - Corporation",
        chain_name="LEGACY HEALTHCARE",
    )


class _StubOwnershipAdapter:
    def __init__(self) -> None:
        self.requested_ccns: list[str] = []

    def get_for_ccn(self, ccn: str) -> OwnershipResult:
        self.requested_ccns.append(ccn)
        return OwnershipResult(
            requested_ccn=ccn,
            source=OwnershipDataSource.LIVE_CMS,
            records=(),
            notice="Test live CMS ownership result.",
        )


class CmsEnrichmentTests(unittest.TestCase):
    def test_reliable_name_match_returns_requested_cms_fields(self) -> None:
        adapter = _StubOwnershipAdapter()
        result = enrich_facilities_with_cms(
            [_facility("place-1", "Avantara Lincoln Park")],
            "60614",
            provider_loader=lambda _: [
                _provider("145510", "AVANTARA LINCOLN PARK")
            ],
            ownership_adapter=adapter,
            aco_loader=lambda: (),
        )

        enrichment = result.enrichments[0]
        self.assertEqual(result.source, CmsDataSource.LIVE_CMS)
        self.assertTrue(enrichment.matched)
        self.assertEqual(enrichment.match_score, 100)
        self.assertEqual(enrichment.ccn, "145510")
        self.assertEqual(enrichment.bed_count, 248)
        self.assertEqual(enrichment.overall_rating, 2)
        self.assertEqual(enrichment.staffing_rating, 2)
        self.assertEqual(enrichment.ownership_type, "For profit - Corporation")
        self.assertEqual(enrichment.chain_name, "LEGACY HEALTHCARE")
        self.assertEqual(adapter.requested_ccns, ["145510"])

    def test_weak_name_match_is_rejected_without_guessing(self) -> None:
        adapter = _StubOwnershipAdapter()
        result = enrich_facilities_with_cms(
            [_facility("place-1", "Completely Different Residence")],
            "60614",
            provider_loader=lambda _: [
                _provider("145510", "AVANTARA LINCOLN PARK")
            ],
            ownership_adapter=adapter,
            aco_loader=lambda: (),
        )

        enrichment = result.enrichments[0]
        self.assertFalse(enrichment.matched)
        self.assertIsNotNone(enrichment.match_score)
        self.assertIsNone(enrichment.ccn)
        self.assertIsNone(enrichment.bed_count)
        self.assertIsNone(enrichment.management)
        self.assertEqual(adapter.requested_ccns, [])

    def test_ambiguous_high_scoring_candidates_are_rejected(self) -> None:
        result = enrich_facilities_with_cms(
            [_facility("place-1", "Shared Nursing Center")],
            "60614",
            provider_loader=lambda _: [
                _provider("145001", "Shared Nursing Center"),
                _provider("145002", "Shared Nursing Center"),
            ],
            ownership_adapter=_StubOwnershipAdapter(),
            aco_loader=lambda: (),
        )

        enrichment = result.enrichments[0]
        self.assertFalse(enrichment.matched)
        self.assertEqual(enrichment.match_score, 100)
        self.assertIsNone(enrichment.ccn)

    def test_provider_api_failure_returns_unmatched(self) -> None:
        def unavailable(_: str) -> list[CmsProviderRecord]:
            raise CmsProviderError("unavailable")

        result = enrich_facilities_with_cms(
            [_facility("place-1", "Avantara Lincoln Park")],
            "60614",
            provider_loader=unavailable,
        )

        self.assertEqual(result.source, CmsDataSource.UNAVAILABLE)
        self.assertFalse(result.enrichments[0].matched)
        self.assertIsNone(result.enrichments[0].match_score)
        self.assertIn("unavailable", result.notice)


if __name__ == "__main__":
    unittest.main()
