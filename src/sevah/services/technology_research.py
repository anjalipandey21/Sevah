"""Bounded deterministic technology research on one official website."""

from collections.abc import Callable
from functools import lru_cache
from urllib.parse import urlparse

from sevah.affinity_models import (
    TechnologyEvidence,
    TechnologyResearchResult,
    WebsiteDocument,
)
from sevah.service_marketing import (
    TECHNOLOGY_PATTERNS,
    extract_service_marketing,
)
from sevah.services.website_content import (
    WebsiteFetchError,
    fetch_website_document,
)

MAX_RESEARCH_PAGES = 3
RESEARCH_LINK_TERMS = (
    "technology",
    "innovation",
    "services",
    "telehealth",
    "digital",
    "safety",
    "resident",
    "experience",
)
DEFAULT_TECHNOLOGY_RESEARCH_PROMPT = (
    "Prioritize official facility evidence and identify only explicitly "
    "documented healthcare technology signals."
)


def research_facility_technology(
    official_website: str | None,
    baseline_signals: tuple[str, ...] = (),
    *,
    effective_prompt: str = DEFAULT_TECHNOLOGY_RESEARCH_PROMPT,
    website_loader: Callable[[str], WebsiteDocument] | None = None,
) -> TechnologyResearchResult:
    """Inspect at most three same-origin pages using the fixed taxonomy."""

    if not official_website:
        return _unavailable(
            effective_prompt,
            "No official facility website was available for technology research.",
        )

    try:
        documents = (
            _cached_documents(official_website)
            if website_loader is None
            else _load_documents(official_website, website_loader)
        )
    except WebsiteFetchError:
        return _unavailable(
            effective_prompt,
            "The official facility website could not be retrieved safely.",
        )
    if not documents:
        return _unavailable(
            effective_prompt,
            "The official facility website could not be retrieved safely.",
        )

    evidence_by_signal: dict[str, TechnologyEvidence] = {}
    for document in documents:
        extraction = extract_service_marketing(document)
        for signal in extraction.technology_signals:
            evidence_by_signal.setdefault(
                signal,
                TechnologyEvidence(
                    signal=signal,
                    matched_term=extraction.matched_terms[signal],
                    source_url=document.url,
                ),
            )

    supported_new = tuple(
        signal for signal in evidence_by_signal
        if signal not in baseline_signals
    )
    return TechnologyResearchResult(
        status="completed",
        signals=supported_new,
        evidence=tuple(
            evidence_by_signal[signal] for signal in supported_new
        ),
        pages_checked=tuple(document.url for document in documents),
        effective_prompt=effective_prompt,
        notice=(
            "Technology signals were matched deterministically on the official "
            "website. The prompt provided guidance but could not alter page, "
            "origin, taxonomy, network-safety, or scoring limits."
        ),
    )


@lru_cache(maxsize=128)
def _cached_documents(official_website: str) -> tuple[WebsiteDocument, ...]:
    try:
        return _load_documents(
            official_website,
            fetch_website_document,
            enforce_redirect_origin=True,
        )
    except WebsiteFetchError:
        return ()


def _load_documents(
    official_website: str,
    loader: Callable[[str], WebsiteDocument],
    *,
    enforce_redirect_origin: bool = False,
) -> tuple[WebsiteDocument, ...]:
    homepage = loader(official_website)
    origin = _origin(homepage.url)
    candidates = sorted(
        (
            link for link in homepage.links
            if _origin(link) == origin and link != homepage.url
        ),
        key=_link_priority,
    )
    documents = [homepage]
    for link in candidates:
        if len(documents) >= MAX_RESEARCH_PAGES:
            break
        try:
            document = (
                fetch_website_document(
                    link,
                    allowed_origin_url=homepage.url,
                )
                if enforce_redirect_origin
                else loader(link)
            )
        except WebsiteFetchError:
            continue
        if _origin(document.url) == origin:
            documents.append(document)
    return tuple(documents)


def _origin(url: str) -> tuple[str, str, int | None]:
    parsed = urlparse(url)
    port = parsed.port
    if port is None:
        port = 443 if parsed.scheme == "https" else 80
    return parsed.scheme.lower(), (parsed.hostname or "").lower(), port


def _link_priority(url: str) -> tuple[int, str]:
    normalized = url.lower()
    for index, term in enumerate(RESEARCH_LINK_TERMS):
        if term in normalized:
            return index, normalized
    return len(RESEARCH_LINK_TERMS), normalized


def _unavailable(
    effective_prompt: str,
    notice: str,
) -> TechnologyResearchResult:
    return TechnologyResearchResult(
        status="unavailable",
        effective_prompt=effective_prompt,
        notice=notice,
    )
