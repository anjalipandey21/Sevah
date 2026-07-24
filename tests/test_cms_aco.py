"""Tests for conservative CMS ACO SNF affiliate enrichment."""

import unittest

from sevah.affinity_models import (
    ServiceMarketingExtraction,
    WebsiteEvidenceSource,
)
from sevah.cms_models import (
    AcoAffiliateRecord,
    AcoAffiliationResult,
    AcoAffiliationStatus,
    CmsFacilityEnrichment,
)
from sevah.models import Coordinates, Facility
from sevah.robotics_affinity import score_robotics_affinity
from sevah.services.cms_aco import (
    CMS_ACO_SOURCE_NAME,
    CMS_ACO_SOURCE_URL,
    CmsAcoError,
    find_aco_affiliation,
)


def _affiliate(ccn: str = "145510") -> AcoAffiliateRecord:
    return AcoAffiliateRecord(
        snf_ccn=ccn,
        aco_id="A1234",
        aco_name="Example Coordinated Care ACO",
        program_year="2026",
        track_or_model="BASIC E",
    )


def _cms(aco: AcoAffiliationResult) -> CmsFacilityEnrichment:
    return CmsFacilityEnrichment(
        facility_id="facility-1",
        matched=True,
        match_score=100,
        match_threshold=90,
        ccn="145510",
        cms_provider_name="EXAMPLE CARE CENTER",
        bed_count=248,
        chain_name="EXAMPLE CHAIN",
        aco_affiliation=aco,
    )


def _assessment(aco: AcoAffiliationResult):
    facility = Facility(
        facility_id="facility-1",
        name="Example Care Center",
        address="1 Test Way, Chicago, IL 60614",
        coordinates=Coordinates(latitude=41.9, longitude=-87.6),
    )
    extraction = ServiceMarketingExtraction(
        source=WebsiteEvidenceSource.UNAVAILABLE,
        notice="No website.",
    )
    return score_robotics_affinity(
        facility,
        extraction,
        cms_enrichment=_cms(aco),
    )


class CmsAcoTests(unittest.TestCase):
    def test_exact_normalized_ccn_match(self) -> None:
        calls = 0

        def loader() -> tuple[AcoAffiliateRecord, ...]:
            nonlocal calls
            calls += 1
            return (_affiliate("14-5510"),)

        result = find_aco_affiliation("145510", loader=loader)

        self.assertEqual(calls, 1)
        self.assertEqual(result.status, AcoAffiliationStatus.CONFIRMED)
        self.assertEqual(result.aco_id, "A1234")
        self.assertEqual(result.match_method, "exact_normalized_ccn")
        self.assertEqual(result.confidence, 100)

    def test_no_ccn_is_not_applicable(self) -> None:
        result = find_aco_affiliation(None, loader=lambda: (_affiliate(),))
        self.assertEqual(result.status, AcoAffiliationStatus.NOT_APPLICABLE)

    def test_missing_affiliate_is_not_found_without_name_inference(self) -> None:
        result = find_aco_affiliation(
            "145510",
            loader=lambda: (_affiliate("999999"),),
        )
        self.assertEqual(result.status, AcoAffiliationStatus.NOT_FOUND)
        self.assertIsNone(result.aco_name)

    def test_api_failure_is_unavailable(self) -> None:
        def unavailable() -> tuple[AcoAffiliateRecord, ...]:
            raise CmsAcoError("unavailable")

        result = find_aco_affiliation("145510", loader=unavailable)
        self.assertEqual(result.status, AcoAffiliationStatus.UNAVAILABLE)

    def test_confirmed_affiliation_adds_only_three_scale_points(self) -> None:
        confirmed = AcoAffiliationResult(
            status=AcoAffiliationStatus.CONFIRMED,
            aco_id="A1234",
            aco_name="Example ACO",
            snf_ccn="145510",
            match_method="exact_normalized_ccn",
            confidence=100,
            source_name=CMS_ACO_SOURCE_NAME,
            source_url=CMS_ACO_SOURCE_URL,
            notice="Confirmed.",
        )
        not_found = confirmed.model_copy(
            update={
                "status": AcoAffiliationStatus.NOT_FOUND,
                "aco_id": None,
                "aco_name": None,
                "confidence": 0,
            }
        )

        confirmed_score = _assessment(confirmed)
        unconfirmed_score = _assessment(not_found)

        self.assertEqual(confirmed_score.components.operating_scale, 15)
        self.assertEqual(unconfirmed_score.components.operating_scale, 12)
        self.assertEqual(confirmed_score.score - unconfirmed_score.score, 3)
        self.assertTrue(
            any(
                "Example ACO (exact_normalized_ccn)" in evidence
                for reason in confirmed_score.reasons
                for evidence in reason.evidence
            )
        )


if __name__ == "__main__":
    unittest.main()
