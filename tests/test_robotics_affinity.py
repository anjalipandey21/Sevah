"""Tests for explainable robotics-affinity scoring."""

import unittest

from sevah.affinity_models import (
    ConfidenceLevel,
    ServiceMarketingExtraction,
    WebsiteDocument,
    WebsiteEvidenceSource,
)
from sevah.cms_models import (
    AcoAffiliationResult,
    AcoAffiliationStatus,
    CmsFacilityEnrichment,
)
from sevah.models import Coordinates, Facility
from sevah.robotics_affinity import (
    analyze_robotics_affinity,
    score_robotics_affinity,
)
from sevah.service_marketing import extract_service_marketing


def _facility(website: str | None = "https://example.com") -> Facility:
    return Facility(
        facility_id="facility-1",
        name="Example Care Center",
        address="1 Test Way, Chicago, IL 60614",
        coordinates=Coordinates(latitude=41.9, longitude=-87.6),
        website=website,
    )


def _cms_match() -> CmsFacilityEnrichment:
    return CmsFacilityEnrichment(
        facility_id="facility-1",
        matched=True,
        match_score=100,
        match_threshold=90,
        ccn="145510",
        cms_provider_name="EXAMPLE CARE CENTER",
        bed_count=248,
        overall_rating=2,
        staffing_rating=2,
        ownership_type="For profit - Corporation",
        chain_name="EXAMPLE CHAIN",
        aco_affiliation=AcoAffiliationResult(
            status=AcoAffiliationStatus.CONFIRMED,
            aco_id="A1234",
            aco_name="Example ACO",
            snf_ccn="145510",
            match_method="exact_normalized_ccn",
            confidence=100,
            source_name="CMS ACO Skilled Nursing Facility Affiliates",
            source_url="https://data.cms.gov/example",
            notice="Confirmed.",
        ),
    )


class RoboticsAffinityTests(unittest.TestCase):
    def test_score_is_weighted_explainable_and_high_confidence(self) -> None:
        extraction = extract_service_marketing(
            WebsiteDocument(
                url="https://example.com",
                text=(
                    "Skilled nursing and rehabilitation services. Telehealth and "
                    "remote monitoring support our innovative, personalized care."
                ),
                content_characters=600,
            )
        )

        assessment = score_robotics_affinity(
            _facility(),
            extraction,
            cms_enrichment=_cms_match(),
        )

        self.assertEqual(assessment.components.service_fit, 18)
        self.assertEqual(assessment.components.technology_readiness, 14)
        self.assertEqual(assessment.components.operating_scale, 15)
        self.assertEqual(assessment.components.innovation_marketing, 5)
        self.assertEqual(assessment.score, 52)
        self.assertEqual(assessment.confidence, 100)
        self.assertEqual(assessment.confidence_level, ConfidenceLevel.HIGH)
        self.assertEqual(sum(reason.points for reason in assessment.reasons), 52)
        self.assertIn("not a clinical-quality rating", assessment.limitation)

    def test_missing_website_and_cms_evidence_produces_zero_low_confidence(self) -> None:
        assessment = analyze_robotics_affinity(_facility(website=None))

        self.assertEqual(assessment.score, 0)
        self.assertEqual(assessment.confidence, 10)
        self.assertEqual(assessment.confidence_level, ConfidenceLevel.LOW)
        self.assertEqual(
            assessment.extraction.source,
            WebsiteEvidenceSource.UNAVAILABLE,
        )

    def test_all_component_scores_are_capped_at_one_hundred(self) -> None:
        extraction = ServiceMarketingExtraction(
            source=WebsiteEvidenceSource.LIVE_WEBSITE,
            url="https://example.com",
            services=(
                "skilled_nursing",
                "rehabilitation",
                "physical_therapy",
                "occupational_therapy",
                "speech_therapy",
                "memory_care",
                "medication_management",
                "assisted_living",
                "long_term_care",
            ),
            technology_signals=(
                "robotics",
                "remote_monitoring",
                "telehealth",
                "electronic_health_records",
                "resident_portal",
                "smart_technology",
                "fall_detection",
                "wifi",
            ),
            marketing_signals=(
                "innovation",
                "technology_enabled",
                "personalized_care",
                "aging_in_place",
                "independence",
            ),
            pages_analyzed=1,
            content_characters=1000,
            notice="Test evidence.",
        )

        assessment = score_robotics_affinity(
            _facility(),
            extraction,
            cms_enrichment=_cms_match(),
        )

        self.assertEqual(assessment.score, 100)


if __name__ == "__main__":
    unittest.main()
