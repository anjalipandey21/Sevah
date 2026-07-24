"""Exact-CCN enrichment from the official CMS ACO SNF affiliate dataset."""

import json
from collections.abc import Callable, Mapping
from functools import lru_cache
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pydantic import ValidationError

from sevah.cms_models import (
    AcoAffiliateRecord,
    AcoAffiliationResult,
    AcoAffiliationStatus,
)

CMS_ACO_SNF_DATASET_ID = "5b227bd9-82d4-4145-86fd-809e02ca7f18"
CMS_ACO_DATA_URL = (
    "https://data.cms.gov/data-api/v1/dataset/"
    f"{CMS_ACO_SNF_DATASET_ID}/data"
)
CMS_ACO_SOURCE_NAME = "CMS ACO Skilled Nursing Facility Affiliates"
CMS_ACO_SOURCE_URL = (
    "https://data.cms.gov/medicare-shared-savings-program/"
    "accountable-care-organization-skilled-nursing-facility-affiliates"
)


class CmsAcoError(RuntimeError):
    """Raised when exact-CCN ACO affiliate data cannot be loaded safely."""


def fetch_cms_aco_affiliates(
    *,
    timeout_seconds: float = 15,
) -> tuple[AcoAffiliateRecord, ...]:
    """Download and cache normalized ACO affiliate rows.

    The current official 2026 response publishes ``Aff_LBN`` but no SNF CCN.
    Exact affiliation is therefore unavailable until CMS publishes a CCN-bearing
    field. Name-only affiliation is intentionally rejected.
    """

    payload = _download_cms_aco_rows(timeout_seconds)
    if payload and "SNF_CCN" not in payload[0]:
        raise CmsAcoError(
            "The current CMS ACO SNF affiliate dataset does not publish "
            "an SNF CCN, so exact-CCN affiliation is unavailable."
        )
    try:
        return tuple(_affiliate_from_row(row) for row in payload)
    except (KeyError, TypeError, ValueError, ValidationError) as exc:
        raise CmsAcoError("CMS ACO affiliate data was invalid.") from exc


@lru_cache(maxsize=4)
def _download_cms_aco_rows(
    timeout_seconds: float,
) -> tuple[Mapping[str, object], ...]:
    """Download rows once per timeout setting, including schema-limited rows."""

    request = Request(
        f"{CMS_ACO_DATA_URL}?size=5000",
        headers={
            "Accept": "application/json",
            "User-Agent": "Sevah/0.1 CMS ACO enrichment",
        },
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            payload = json.load(response)
        if not isinstance(payload, list) or any(
            not isinstance(row, Mapping) for row in payload
        ):
            raise TypeError("Unexpected CMS ACO response shape.")
        return tuple(payload)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise CmsAcoError("CMS ACO affiliate request failed.") from exc
    except (TypeError, ValueError) as exc:
        raise CmsAcoError("CMS ACO affiliate data was invalid.") from exc


def find_aco_affiliation(
    ccn: str | None,
    *,
    loader: Callable[[], tuple[AcoAffiliateRecord, ...]] | None = None,
) -> AcoAffiliationResult:
    """Find an ACO affiliate using exact normalized CCN only."""

    normalized_ccn = _normalize_ccn(ccn)
    if normalized_ccn is None:
        return _result(
            AcoAffiliationStatus.NOT_APPLICABLE,
            notice="ACO lookup requires a reliable CMS provider match with a CCN.",
        )

    load_rows = loader or fetch_cms_aco_affiliates
    try:
        rows = load_rows()
    except CmsAcoError as exc:
        return _result(
            AcoAffiliationStatus.UNAVAILABLE,
            snf_ccn=normalized_ccn,
            notice=str(exc),
        )

    matches = [
        row for row in rows
        if _normalize_ccn(row.snf_ccn) == normalized_ccn
    ]
    if not matches:
        return _result(
            AcoAffiliationStatus.NOT_FOUND,
            snf_ccn=normalized_ccn,
            match_method="exact_normalized_ccn",
            confidence=100,
            notice="No ACO SNF affiliate row contained this exact CCN.",
        )

    match = matches[0]
    return _result(
        AcoAffiliationStatus.CONFIRMED,
        aco_id=match.aco_id,
        aco_name=match.aco_name,
        snf_ccn=normalized_ccn,
        match_method="exact_normalized_ccn",
        confidence=100,
        program_year=match.program_year,
        track_or_model=match.track_or_model,
        notice="Confirmed by exact normalized CCN; no facility-name inference was used.",
    )


def _affiliate_from_row(row: Mapping[str, object]) -> AcoAffiliateRecord:
    return AcoAffiliateRecord(
        snf_ccn=str(row["SNF_CCN"]).strip(),
        aco_id=str(row["ACO_ID"]).strip(),
        aco_name=str(row["ACO_Name"]).strip(),
        program_year=_optional_text(row.get("Program_Year")),
        track_or_model=_track_or_model(row),
    )


def _track_or_model(row: Mapping[str, object]) -> str | None:
    if str(row.get("ENHANCED_Track", "")).strip() == "1":
        return "ENHANCED"
    if str(row.get("BASIC_Track", "")).strip() == "1":
        level = _optional_text(row.get("BASIC_Track_Level"))
        return f"BASIC {level}" if level else "BASIC"
    if str(row.get("pc_flex_agreement_status", "")).strip() == "1":
        return "ACO PC Flex"
    return None


def _normalize_ccn(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = "".join(character for character in value if character.isalnum())
    return normalized.upper() or None


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _result(
    status: AcoAffiliationStatus,
    **values: object,
) -> AcoAffiliationResult:
    return AcoAffiliationResult(
        status=status,
        source_name=CMS_ACO_SOURCE_NAME,
        source_url=CMS_ACO_SOURCE_URL,
        **values,
    )
