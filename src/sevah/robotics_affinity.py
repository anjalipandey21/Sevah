"""Explainable deterministic robotics-affinity scoring."""

from collections.abc import Callable, Iterable

from sevah.affinity_models import (
    AffinityComponents,
    ConfidenceLevel,
    RoboticsAffinityAssessment,
    ScoreReason,
    ServiceMarketingExtraction,
    WebsiteDocument,
    WebsiteEvidenceSource,
)
from sevah.cms_models import (
    AcoAffiliationStatus,
    CmsEnrichmentBatch,
    CmsFacilityEnrichment,
)
from sevah.models import Facility
from sevah.service_marketing import (
    extract_service_marketing,
    unavailable_extraction,
)
from sevah.services.website_content import (
    WebsiteFetchError,
    fetch_website_document,
)

SERVICE_WEIGHTS = {
    "skilled_nursing": 10,
    "rehabilitation": 8,
    "physical_therapy": 5,
    "occupational_therapy": 5,
    "speech_therapy": 4,
    "memory_care": 4,
    "medication_management": 4,
    "assisted_living": 4,
    "long_term_care": 4,
}
TECHNOLOGY_WEIGHTS = {
    "robotics": 15,
    "remote_monitoring": 8,
    "telehealth": 6,
    "electronic_health_records": 4,
    "resident_portal": 4,
    "smart_technology": 6,
    "fall_detection": 5,
    "wifi": 2,
}
MARKETING_WEIGHTS = {
    "innovation": 3,
    "technology_enabled": 3,
    "personalized_care": 2,
    "aging_in_place": 2,
    "independence": 1,
}

ROBOTICS_SCORE_LIMITATION = (
    "This deterministic score is an explainable prioritization heuristic, not a "
    "clinical-quality rating, procurement recommendation, or proof that robotics "
    "would be safe, useful, affordable, or accepted at this facility."
)


def analyze_robotics_affinity(
    facility: Facility,
    *,
    cms_enrichment: CmsFacilityEnrichment | None = None,
    website_loader: Callable[[str], WebsiteDocument] | None = None,
) -> RoboticsAffinityAssessment:
    """Extract website evidence and produce one deterministic assessment."""

    if not facility.website:
        extraction = unavailable_extraction(
            None,
            "No facility website was available for deterministic extraction.",
        )
    else:
        load_website = website_loader or fetch_website_document
        try:
            extraction = extract_service_marketing(load_website(facility.website))
        except WebsiteFetchError:
            extraction = unavailable_extraction(
                facility.website,
                "The facility website could not be retrieved safely.",
            )
    return score_robotics_affinity(
        facility,
        extraction,
        cms_enrichment=cms_enrichment,
    )


def analyze_facilities_robotics_affinity(
    facilities: Iterable[Facility],
    *,
    cms_batch: CmsEnrichmentBatch | None = None,
    website_loader: Callable[[str], WebsiteDocument] | None = None,
) -> tuple[RoboticsAffinityAssessment, ...]:
    """Assess a facility collection without changing discovery orchestration."""

    cms_by_facility_id = (
        {item.facility_id: item for item in cms_batch.enrichments}
        if cms_batch
        else {}
    )
    return tuple(
        analyze_robotics_affinity(
            facility,
            cms_enrichment=cms_by_facility_id.get(facility.facility_id),
            website_loader=website_loader,
        )
        for facility in facilities
    )


def score_robotics_affinity(
    facility: Facility,
    extraction: ServiceMarketingExtraction,
    *,
    cms_enrichment: CmsFacilityEnrichment | None = None,
) -> RoboticsAffinityAssessment:
    """Calculate a transparent 0–100 score from configured evidence weights."""

    service_points = min(
        sum(SERVICE_WEIGHTS[signal] for signal in extraction.services),
        40,
    )
    technology_points = min(
        sum(
            TECHNOLOGY_WEIGHTS[signal]
            for signal in extraction.technology_signals
        ),
        35,
    )
    marketing_points = min(
        sum(MARKETING_WEIGHTS[signal] for signal in extraction.marketing_signals),
        10,
    )
    scale_points, scale_evidence, scale_reason = _score_scale(cms_enrichment)

    components = AffinityComponents(
        service_fit=service_points,
        technology_readiness=technology_points,
        operating_scale=scale_points,
        innovation_marketing=marketing_points,
    )
    score = sum(
        (
            components.service_fit,
            components.technology_readiness,
            components.operating_scale,
            components.innovation_marketing,
        )
    )
    confidence, confidence_reasons = _score_confidence(
        facility,
        extraction,
        cms_enrichment,
    )
    return RoboticsAffinityAssessment(
        facility_id=facility.facility_id,
        score=score,
        confidence=confidence,
        confidence_level=_confidence_level(confidence),
        components=components,
        reasons=(
            _website_reason(
                "service_fit",
                service_points,
                extraction.services,
                "configured care-service signals",
            ),
            _website_reason(
                "technology_readiness",
                technology_points,
                extraction.technology_signals,
                "configured technology signals",
            ),
            ScoreReason(
                category="operating_scale",
                points=scale_points,
                reason=scale_reason,
                evidence=scale_evidence,
            ),
            _website_reason(
                "innovation_marketing",
                marketing_points,
                extraction.marketing_signals,
                "configured innovation-marketing signals",
            ),
        ),
        confidence_reasons=confidence_reasons,
        extraction=extraction,
        limitation=ROBOTICS_SCORE_LIMITATION,
    )


def _score_scale(
    cms_enrichment: CmsFacilityEnrichment | None,
) -> tuple[int, tuple[str, ...], str]:
    if not cms_enrichment or not cms_enrichment.matched:
        return 0, (), "No reliable CMS match was available for scale evidence."

    points = 0
    evidence: list[str] = []
    beds = cms_enrichment.bed_count
    if beds is not None:
        if beds >= 200:
            points += 9
        elif beds >= 100:
            points += 7
        elif beds >= 50:
            points += 5
        elif beds > 0:
            points += 3
        evidence.append(f"{beds} CMS-certified beds")
    if cms_enrichment.chain_name:
        points += 3
        evidence.append(f"CMS chain: {cms_enrichment.chain_name}")
    aco = cms_enrichment.aco_affiliation
    if aco.status is AcoAffiliationStatus.CONFIRMED:
        points += 3
        evidence.append(
            f"CMS ACO: {aco.aco_name} ({aco.match_method})"
        )
    return (
        min(points, 15),
        tuple(evidence),
        (
            "Points reflect CMS-certified bed count, documented chain membership, "
            "and confirmed exact-CCN ACO affiliation."
        ),
    )


def _score_confidence(
    facility: Facility,
    extraction: ServiceMarketingExtraction,
    cms_enrichment: CmsFacilityEnrichment | None,
) -> tuple[int, tuple[str, ...]]:
    confidence = 10
    reasons = ["10 points: basic structured facility record was available."]

    if extraction.source is WebsiteEvidenceSource.LIVE_WEBSITE:
        if extraction.content_characters >= 500:
            confidence += 60
            reasons.append("60 points: at least 500 characters of live website text.")
        else:
            confidence += 40
            reasons.append("40 points: live website text was available but limited.")
    else:
        reasons.append("0 website points: live website evidence was unavailable.")

    if cms_enrichment and cms_enrichment.matched:
        confidence += 30
        reasons.append("30 points: a reliable ZIP-scoped CMS match was available.")
    else:
        reasons.append("0 CMS points: no reliable CMS match was available.")

    return min(confidence, 100), tuple(reasons)


def _confidence_level(confidence: int) -> ConfidenceLevel:
    if confidence >= 80:
        return ConfidenceLevel.HIGH
    if confidence >= 50:
        return ConfidenceLevel.MEDIUM
    return ConfidenceLevel.LOW


def _website_reason(
    category: str,
    points: int,
    signals: tuple[str, ...],
    description: str,
) -> ScoreReason:
    if signals:
        return ScoreReason(
            category=category,
            points=points,
            reason=f"Points came from {description} found in website text.",
            evidence=signals,
        )
    return ScoreReason(
        category=category,
        points=0,
        reason=f"No {description} were found in available website text.",
    )
