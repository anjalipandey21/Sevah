"""Tests for LangGraph human-review interrupt and resume."""

import unittest
from uuid import uuid4
from unittest.mock import patch

from sevah.affinity_models import (
    AffinityComponents,
    ConfidenceLevel,
    RoboticsAffinityAssessment,
    ScoreReason,
    ServiceMarketingExtraction,
    WebsiteEvidenceSource,
)
from sevah.cms_models import CmsDataSource, CmsEnrichmentBatch
from sevah.models import (
    Coordinates,
    DataSource,
    DiscoveryResult,
    Facility,
    FacilityDistance,
    ZipCodeQuery,
)
from sevah.review_workflow import (
    HumanReviewDecision,
    ReviewDecision,
    ReviewStatus,
    resume_review_workflow,
    start_review_workflow,
)


def _discovery() -> DiscoveryResult:
    facility = Facility(
        facility_id="facility-1",
        name="Example Care",
        address="1 Test Way",
        coordinates=Coordinates(latitude=41.9, longitude=-87.6),
    )
    return DiscoveryResult(
        query=ZipCodeQuery(zip_code="60614"),
        zip_center=facility.coordinates,
        source=DataSource.SAMPLE,
        facilities=(FacilityDistance(facility=facility, distance_miles=0),),
        notice="Test discovery.",
    )


def _cms() -> CmsEnrichmentBatch:
    return CmsEnrichmentBatch(
        zip_code="60614",
        source=CmsDataSource.LIVE_CMS,
        enrichments=(),
        notice="Test CMS.",
        limitation="Test limitation.",
    )


def _assessment() -> RoboticsAffinityAssessment:
    return RoboticsAffinityAssessment(
        facility_id="facility-1",
        score=25,
        confidence=70,
        confidence_level=ConfidenceLevel.MEDIUM,
        components=AffinityComponents(
            service_fit=10,
            technology_readiness=10,
            operating_scale=5,
            innovation_marketing=0,
        ),
        reasons=(
            ScoreReason(category="service_fit", points=10, reason="Test reason."),
        ),
        confidence_reasons=("Test confidence.",),
        extraction=ServiceMarketingExtraction(
            source=WebsiteEvidenceSource.UNAVAILABLE,
            notice="Test extraction.",
        ),
        limitation="Test limitation.",
    )


class ReviewWorkflowTests(unittest.TestCase):
    @patch("sevah.review_workflow.analyze_facilities_robotics_affinity")
    @patch("sevah.review_workflow.enrich_discovery_result_with_cms")
    @patch("sevah.review_workflow.discover_facilities")
    def test_interrupts_then_resumes_without_rerunning_prior_nodes(
        self,
        discover,
        enrich,
        score,
    ) -> None:
        discover.return_value = _discovery()
        enrich.return_value = _cms()
        score.return_value = (_assessment(),)
        thread_id = str(uuid4())

        paused = start_review_workflow("60614", thread_id)

        self.assertEqual(paused.status, ReviewStatus.AWAITING_REVIEW)
        self.assertEqual(paused.review_request.facilities[0].score, 25)

        completed = resume_review_workflow(
            thread_id,
            HumanReviewDecision(
                decision=ReviewDecision.APPROVE,
                note="Reviewed.",
            ),
        )

        self.assertEqual(completed.status, ReviewStatus.APPROVED)
        self.assertEqual(completed.decision.note, "Reviewed.")
        discover.assert_called_once()
        enrich.assert_called_once()
        score.assert_called_once()

    @patch("sevah.review_workflow.analyze_facilities_robotics_affinity")
    @patch("sevah.review_workflow.enrich_discovery_result_with_cms")
    @patch("sevah.review_workflow.discover_facilities")
    def test_reject_decision_is_preserved(
        self,
        discover,
        enrich,
        score,
    ) -> None:
        discover.return_value = _discovery()
        enrich.return_value = _cms()
        score.return_value = (_assessment(),)
        thread_id = str(uuid4())

        start_review_workflow("60614", thread_id)
        completed = resume_review_workflow(
            thread_id,
            HumanReviewDecision(
                decision=ReviewDecision.REJECT,
                note="Evidence is insufficient.",
            ),
        )

        self.assertEqual(completed.status, ReviewStatus.REJECTED)
        self.assertEqual(completed.decision.note, "Evidence is insufficient.")


if __name__ == "__main__":
    unittest.main()

