"""Conservative CMS nursing-home enrichment for discovery facilities."""

import re
import unicodedata
from collections.abc import Callable, Iterable

from rapidfuzz import fuzz

from sevah.cms_models import (
    AcoAffiliateRecord,
    CmsDataSource,
    CmsEnrichmentBatch,
    CmsFacilityEnrichment,
    CmsProviderRecord,
)
from sevah.models import DiscoveryResult, Facility, ZipCodeQuery
from sevah.services.cms_api import CmsProviderError, fetch_cms_providers_by_zip
from sevah.services.ownership import (
    CmsOwnershipAdapter,
    ManagementOwnershipAdapter,
)
from sevah.services.cms_aco import find_aco_affiliation

MIN_RELIABLE_MATCH_SCORE = 90.0
MIN_RUNNER_UP_MARGIN = 5.0
CMS_PROXY_LIMITATION = (
    "CMS records describe Medicare- or Medicaid-certified nursing homes, not "
    "assisted-living facilities. An assisted-living facility may have no CMS "
    "record, and no match must not be interpreted as a quality or eligibility signal."
)

_TOKEN_REPLACEMENTS = {
    "ctr": "center",
    "rehab": "rehabilitation",
    "nsg": "nursing",
}
_LEGAL_SUFFIXES = {"inc", "llc", "ltd", "corp", "corporation", "company", "co"}


def enrich_facilities_with_cms(
    facilities: Iterable[Facility],
    zip_code: str,
    *,
    threshold: float = MIN_RELIABLE_MATCH_SCORE,
    runner_up_margin: float = MIN_RUNNER_UP_MARGIN,
    provider_loader: Callable[[str], list[CmsProviderRecord]] | None = None,
    ownership_adapter: ManagementOwnershipAdapter | None = None,
    aco_loader: Callable[[], tuple[AcoAffiliateRecord, ...]] | None = None,
) -> CmsEnrichmentBatch:
    """Enrich facilities from a single ZIP-scoped CMS Provider query."""

    validated_zip = ZipCodeQuery(zip_code=zip_code).zip_code
    facility_list = list(facilities)
    load_providers = provider_loader or fetch_cms_providers_by_zip
    adapter = ownership_adapter or CmsOwnershipAdapter()

    try:
        cms_records = load_providers(validated_zip)
    except CmsProviderError:
        return CmsEnrichmentBatch(
            zip_code=validated_zip,
            source=CmsDataSource.UNAVAILABLE,
            enrichments=tuple(
                _unmatched(facility, threshold=threshold)
                for facility in facility_list
            ),
            notice=(
                "CMS Provider Information was unavailable. Facilities were left "
                "unmatched rather than enriched from uncertain data."
            ),
            limitation=CMS_PROXY_LIMITATION,
        )

    enrichments = tuple(
        _match_and_enrich(
            facility,
            cms_records,
            threshold=threshold,
            runner_up_margin=runner_up_margin,
            ownership_adapter=adapter,
            aco_loader=aco_loader,
        )
        for facility in facility_list
    )
    return CmsEnrichmentBatch(
        zip_code=validated_zip,
        source=CmsDataSource.LIVE_CMS,
        enrichments=enrichments,
        notice=(
            "CMS Provider Information candidates were restricted to the entered "
            "ZIP code and matched conservatively by facility name."
        ),
        limitation=CMS_PROXY_LIMITATION,
    )


def enrich_discovery_result_with_cms(
    discovery_result: DiscoveryResult,
    **kwargs,
) -> CmsEnrichmentBatch:
    """Convenience adapter for an existing discovery response.

    This function does not alter the LangGraph workflow or mutate the discovery
    response. It returns a separate enrichment batch.
    """

    return enrich_facilities_with_cms(
        (item.facility for item in discovery_result.facilities),
        discovery_result.query.zip_code,
        **kwargs,
    )


def _match_and_enrich(
    facility: Facility,
    cms_records: list[CmsProviderRecord],
    *,
    threshold: float,
    runner_up_margin: float,
    ownership_adapter: ManagementOwnershipAdapter,
    aco_loader: Callable[[], tuple[AcoAffiliateRecord, ...]] | None,
) -> CmsFacilityEnrichment:
    scored = sorted(
        (
            (
                float(
                    fuzz.ratio(
                        _normalize_name(facility.name),
                        _normalize_name(record.provider_name),
                    )
                ),
                record,
            )
            for record in cms_records
        ),
        key=lambda item: item[0],
        reverse=True,
    )
    if not scored:
        return _unmatched(facility, threshold=threshold)

    best_score, best_record = scored[0]
    runner_up_score = scored[1][0] if len(scored) > 1 else None
    reliable = best_score >= threshold and (
        runner_up_score is None or best_score - runner_up_score >= runner_up_margin
    )
    if not reliable:
        return _unmatched(
            facility,
            threshold=threshold,
            match_score=best_score,
        )

    return CmsFacilityEnrichment(
        facility_id=facility.facility_id,
        matched=True,
        match_score=best_score,
        match_threshold=threshold,
        ccn=best_record.ccn,
        cms_provider_name=best_record.provider_name,
        bed_count=best_record.bed_count,
        overall_rating=best_record.overall_rating,
        staffing_rating=best_record.staffing_rating,
        ownership_type=best_record.ownership_type,
        chain_name=best_record.chain_name,
        management=ownership_adapter.get_for_ccn(best_record.ccn),
        aco_affiliation=find_aco_affiliation(
            best_record.ccn,
            loader=aco_loader,
        ),
    )


def _unmatched(
    facility: Facility,
    *,
    threshold: float,
    match_score: float | None = None,
) -> CmsFacilityEnrichment:
    return CmsFacilityEnrichment(
        facility_id=facility.facility_id,
        matched=False,
        match_score=match_score,
        match_threshold=threshold,
    )


def _normalize_name(name: str) -> str:
    decomposed = unicodedata.normalize("NFKD", name)
    ascii_name = decomposed.encode("ascii", "ignore").decode("ascii").lower()
    tokens = re.sub(r"[^a-z0-9]+", " ", ascii_name).split()
    normalized_tokens = (
        _TOKEN_REPLACEMENTS.get(token, token)
        for token in tokens
        if token not in _LEGAL_SUFFIXES
    )
    return " ".join(normalized_tokens)
