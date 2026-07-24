"""Deterministic service and marketing signal extraction."""

import re
from collections.abc import Mapping

from sevah.affinity_models import (
    ServiceMarketingExtraction,
    WebsiteDocument,
    WebsiteEvidenceSource,
)

SERVICE_PATTERNS: Mapping[str, tuple[str, ...]] = {
    "skilled_nursing": ("skilled nursing",),
    "rehabilitation": ("rehabilitation", "rehab services"),
    "physical_therapy": ("physical therapy",),
    "occupational_therapy": ("occupational therapy",),
    "speech_therapy": ("speech therapy", "speech-language therapy"),
    "memory_care": ("memory care", "dementia care", "alzheimer's care"),
    "medication_management": ("medication management",),
    "assisted_living": ("assisted living",),
    "long_term_care": ("long-term care", "long term care"),
}

TECHNOLOGY_PATTERNS: Mapping[str, tuple[str, ...]] = {
    "robotics": ("robotics", "robot-assisted", "robotic assistance"),
    "remote_monitoring": ("remote monitoring", "remote patient monitoring"),
    "telehealth": ("telehealth", "telemedicine", "virtual care"),
    "electronic_health_records": (
        "electronic health record",
        "electronic medical record",
        "digital health record",
    ),
    "resident_portal": ("resident portal", "family portal", "patient portal"),
    "smart_technology": ("smart technology", "smart home", "smart room"),
    "fall_detection": ("fall detection", "fall prevention technology"),
    "wifi": ("wi-fi", "wifi", "wireless internet"),
}

MARKETING_PATTERNS: Mapping[str, tuple[str, ...]] = {
    "innovation": ("innovative care", "innovative", "innovation", "cutting-edge"),
    "technology_enabled": (
        "technology-enabled",
        "technology enabled",
        "advanced technology",
    ),
    "personalized_care": ("personalized care", "individualized care"),
    "aging_in_place": ("aging in place", "age in place"),
    "independence": ("maintain independence", "promote independence"),
}

_NEGATION = re.compile(
    r"\b(?:do not|does not|don t|doesn t|not currently|no)\b.{0,35}$"
)
_CLAUSE_BOUNDARY = "sevahclauseboundary"


def extract_service_marketing(
    document: WebsiteDocument,
) -> ServiceMarketingExtraction:
    """Extract known signals without inference, generation, or an LLM."""

    normalized_text = _normalize_text(document.text)
    service_matches = _match_taxonomy(normalized_text, SERVICE_PATTERNS)
    technology_matches = _match_taxonomy(normalized_text, TECHNOLOGY_PATTERNS)
    marketing_matches = _match_taxonomy(normalized_text, MARKETING_PATTERNS)
    matched_terms = {
        **service_matches,
        **technology_matches,
        **marketing_matches,
    }
    return ServiceMarketingExtraction(
        source=WebsiteEvidenceSource.LIVE_WEBSITE,
        url=document.url,
        services=tuple(service_matches),
        technology_signals=tuple(technology_matches),
        marketing_signals=tuple(marketing_matches),
        matched_terms=matched_terms,
        pages_analyzed=1,
        content_characters=document.content_characters,
        notice=(
            "Signals were extracted deterministically from visible website text; "
            "absence means only that a configured phrase was not found."
        ),
    )


def unavailable_extraction(url: str | None, reason: str) -> ServiceMarketingExtraction:
    """Return a structured extraction result when website evidence is missing."""

    return ServiceMarketingExtraction(
        source=WebsiteEvidenceSource.UNAVAILABLE,
        url=url,
        notice=reason,
    )


def _match_taxonomy(
    normalized_text: str,
    taxonomy: Mapping[str, tuple[str, ...]],
) -> dict[str, str]:
    matches: dict[str, str] = {}
    for signal, phrases in taxonomy.items():
        for phrase in phrases:
            normalized_phrase = _normalize_text(phrase)
            pattern = re.compile(rf"\b{re.escape(normalized_phrase)}\b")
            for match in pattern.finditer(normalized_text):
                preceding_text = normalized_text[: match.start()].rsplit(
                    _CLAUSE_BOUNDARY,
                    1,
                )[-1][-50:]
                if not _NEGATION.search(preceding_text):
                    matches[signal] = phrase
                    break
            if signal in matches:
                break
    return matches


def _normalize_text(text: str) -> str:
    with_boundaries = re.sub(
        r"[\n.!?;,:]+",
        f" {_CLAUSE_BOUNDARY} ",
        text.lower().replace("’", "'"),
    )
    return " ".join(
        re.sub(r"[^a-z0-9]+", " ", with_boundaries).split()
    )
