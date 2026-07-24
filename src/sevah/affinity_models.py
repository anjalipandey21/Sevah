"""Models for deterministic website extraction and robotics-affinity scoring."""

from enum import Enum

from pydantic import Field, model_validator

from sevah.models import SevahModel


class WebsiteEvidenceSource(str, Enum):
    """Availability of facility website evidence."""

    LIVE_WEBSITE = "live_website"
    UNAVAILABLE = "unavailable"


class ConfidenceLevel(str, Enum):
    """Human-readable confidence band for an affinity assessment."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class WebsiteDocument(SevahModel):
    """Bounded text extracted from a facility website response."""

    url: str = Field(min_length=1)
    text: str
    content_characters: int = Field(ge=0)
    links: tuple[str, ...] = ()


class ServiceMarketingExtraction(SevahModel):
    """Deterministic signals extracted from website text."""

    source: WebsiteEvidenceSource
    url: str | None = None
    services: tuple[str, ...] = ()
    technology_signals: tuple[str, ...] = ()
    marketing_signals: tuple[str, ...] = ()
    matched_terms: dict[str, str] = Field(default_factory=dict)
    pages_analyzed: int = Field(default=0, ge=0)
    content_characters: int = Field(default=0, ge=0)
    notice: str = Field(min_length=1)


class TechnologyEvidence(SevahModel):
    """One explicitly matched technology phrase with page provenance."""

    signal: str = Field(min_length=1)
    matched_term: str = Field(min_length=1)
    source_url: str = Field(min_length=1)


class TechnologyResearchResult(SevahModel):
    """Bounded official-website technology research result."""

    status: str = Field(min_length=1)
    signals: tuple[str, ...] = ()
    evidence: tuple[TechnologyEvidence, ...] = ()
    pages_checked: tuple[str, ...] = ()
    effective_prompt: str = Field(min_length=1)
    notice: str = Field(min_length=1)

    @model_validator(mode="after")
    def require_provenance_for_every_signal(self) -> "TechnologyResearchResult":
        if len(self.signals) != len(set(self.signals)):
            raise ValueError("Technology research signals must be deduplicated.")
        evidence_signals = tuple(item.signal for item in self.evidence)
        if set(evidence_signals) != set(self.signals):
            raise ValueError(
                "Every technology research signal must have sourced evidence."
            )
        return self


class AffinityComponents(SevahModel):
    """Weighted components that sum to the final score."""

    service_fit: int = Field(ge=0, le=40)
    technology_readiness: int = Field(ge=0, le=35)
    operating_scale: int = Field(ge=0, le=15)
    innovation_marketing: int = Field(ge=0, le=10)


class ScoreReason(SevahModel):
    """One explainable contribution to an affinity score."""

    category: str = Field(min_length=1)
    points: int = Field(ge=0)
    reason: str = Field(min_length=1)
    evidence: tuple[str, ...] = ()


class RoboticsAffinityAssessment(SevahModel):
    """Explainable deterministic robotics-affinity assessment."""

    facility_id: str = Field(min_length=1)
    score: int = Field(ge=0, le=100)
    confidence: int = Field(ge=0, le=100)
    confidence_level: ConfidenceLevel
    components: AffinityComponents
    reasons: tuple[ScoreReason, ...]
    confidence_reasons: tuple[str, ...]
    extraction: ServiceMarketingExtraction
    limitation: str = Field(min_length=1)
