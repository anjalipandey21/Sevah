"""Pydantic contracts for CMS nursing-home enrichment.

CMS-certified nursing homes are an MVP proxy only. Assisted-living facilities
may not be Medicare- or Medicaid-certified nursing homes and often will not
have a CMS match.
"""

from enum import Enum

from pydantic import Field

from sevah.models import SevahModel, ZipCode


class CmsDataSource(str, Enum):
    """Availability of CMS Provider Information data."""

    LIVE_CMS = "live_cms"
    UNAVAILABLE = "unavailable"


class OwnershipDataSource(str, Enum):
    """Origin of management and ownership records."""

    LIVE_CMS = "live_cms"
    SAMPLE = "sample"
    UNAVAILABLE = "unavailable"


class AcoAffiliationStatus(str, Enum):
    """Outcome of exact-CCN ACO SNF affiliate lookup."""

    CONFIRMED = "confirmed"
    NOT_FOUND = "not_found"
    UNAVAILABLE = "unavailable"
    NOT_APPLICABLE = "not_applicable"


class AcoAffiliateRecord(SevahModel):
    """Normalized ACO SNF affiliate row with an explicit SNF CCN."""

    snf_ccn: str = Field(min_length=1)
    aco_id: str = Field(min_length=1)
    aco_name: str = Field(min_length=1)
    program_year: str | None = None
    track_or_model: str | None = None


class AcoAffiliationResult(SevahModel):
    """Conservative exact-CCN ACO affiliation result."""

    status: AcoAffiliationStatus
    aco_id: str | None = None
    aco_name: str | None = None
    snf_ccn: str | None = None
    match_method: str | None = None
    confidence: int = Field(default=0, ge=0, le=100)
    program_year: str | None = None
    track_or_model: str | None = None
    source_name: str = Field(min_length=1)
    source_url: str = Field(min_length=1)
    notice: str = Field(min_length=1)


def not_applicable_aco_result() -> AcoAffiliationResult:
    """Return the default state before a reliable CMS provider match exists."""

    return AcoAffiliationResult(
        status=AcoAffiliationStatus.NOT_APPLICABLE,
        source_name="CMS ACO Skilled Nursing Facility Affiliates",
        source_url=(
            "https://data.cms.gov/medicare-shared-savings-program/"
            "accountable-care-organization-skilled-nursing-facility-affiliates"
        ),
        notice="ACO lookup requires a reliable CMS provider match with a CCN.",
    )


class CmsProviderRecord(SevahModel):
    """Relevant fields from one CMS Provider Information row."""

    ccn: str = Field(min_length=1)
    provider_name: str = Field(min_length=1)
    zip_code: ZipCode
    bed_count: int | None = Field(default=None, ge=0)
    overall_rating: int | None = Field(default=None, ge=1, le=5)
    staffing_rating: int | None = Field(default=None, ge=1, le=5)
    ownership_type: str | None = None
    chain_name: str | None = None
    processing_date: str | None = None


class OwnershipRecord(SevahModel):
    """One owner or manager associated with a CMS-certified nursing home."""

    ccn: str | None = None
    role: str = Field(min_length=1)
    owner_type: str = Field(min_length=1)
    owner_name: str = Field(min_length=1)
    ownership_percentage: str | None = None
    association_date: str | None = None


class OwnershipResult(SevahModel):
    """Ownership records and an explicit live-or-sample provenance label."""

    requested_ccn: str = Field(min_length=1)
    source: OwnershipDataSource
    records: tuple[OwnershipRecord, ...]
    notice: str = Field(min_length=1)


class CmsFacilityEnrichment(SevahModel):
    """CMS enrichment result for one discovery facility."""

    facility_id: str = Field(min_length=1)
    matched: bool
    match_score: float | None = Field(default=None, ge=0, le=100)
    match_threshold: float = Field(ge=0, le=100)
    ccn: str | None = None
    cms_provider_name: str | None = None
    bed_count: int | None = Field(default=None, ge=0)
    overall_rating: int | None = Field(default=None, ge=1, le=5)
    staffing_rating: int | None = Field(default=None, ge=1, le=5)
    ownership_type: str | None = None
    chain_name: str | None = None
    management: OwnershipResult | None = None
    aco_affiliation: AcoAffiliationResult = Field(
        default_factory=not_applicable_aco_result
    )


class CmsEnrichmentBatch(SevahModel):
    """CMS enrichment results for a ZIP-scoped facility collection."""

    zip_code: ZipCode
    source: CmsDataSource
    enrichments: tuple[CmsFacilityEnrichment, ...]
    notice: str = Field(min_length=1)
    limitation: str = Field(min_length=1)
