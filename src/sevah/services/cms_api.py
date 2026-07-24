"""Clients for the public CMS Provider Data Catalog APIs."""

import json
from collections.abc import Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from pydantic import ValidationError

from sevah.cms_models import CmsProviderRecord, OwnershipRecord

CMS_PROVIDER_DATASET_ID = "4pq5-n9py"
CMS_OWNERSHIP_DATASET_ID = "y2hd-n93e"
CMS_DATASTORE_URL = (
    "https://data.cms.gov/provider-data/api/1/datastore/query/{dataset_id}/0"
)


class CmsProviderError(RuntimeError):
    """Raised when CMS Provider Information cannot be loaded safely."""


class CmsOwnershipError(RuntimeError):
    """Raised when CMS Ownership records cannot be loaded safely."""


def fetch_cms_providers_by_zip(
    zip_code: str,
    *,
    timeout_seconds: float = 10,
) -> list[CmsProviderRecord]:
    """Load real CMS-certified nursing homes for an exact five-digit ZIP."""

    try:
        rows = _query_dataset(
            CMS_PROVIDER_DATASET_ID,
            property_name="zip_code",
            value=zip_code,
            timeout_seconds=timeout_seconds,
        )
        return [_provider_from_row(row) for row in rows]
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise CmsProviderError("CMS Provider Information request failed.") from exc
    except (KeyError, TypeError, ValueError, ValidationError) as exc:
        raise CmsProviderError("CMS Provider Information was invalid.") from exc


def fetch_cms_ownership_by_ccn(
    ccn: str,
    *,
    timeout_seconds: float = 10,
) -> list[OwnershipRecord]:
    """Load live CMS ownership and management rows for one CCN."""

    try:
        rows = _query_dataset(
            CMS_OWNERSHIP_DATASET_ID,
            property_name="cms_certification_number_ccn",
            value=ccn,
            timeout_seconds=timeout_seconds,
        )
        return [_ownership_from_row(row) for row in rows]
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise CmsOwnershipError("CMS Ownership request failed.") from exc
    except (KeyError, TypeError, ValueError, ValidationError) as exc:
        raise CmsOwnershipError("CMS Ownership data was invalid.") from exc


def _query_dataset(
    dataset_id: str,
    *,
    property_name: str,
    value: str,
    timeout_seconds: float,
) -> list[Mapping[str, object]]:
    params = urlencode(
        (
            ("offset", "0"),
            ("limit", "1500"),
            ("conditions[0][property]", property_name),
            ("conditions[0][value]", value),
            ("conditions[0][operator]", "="),
        )
    )
    request = Request(
        f"{CMS_DATASTORE_URL.format(dataset_id=dataset_id)}?{params}",
        headers={
            "Accept": "application/json",
            "User-Agent": "Sevah/0.1 CMS enrichment",
        },
    )
    with urlopen(request, timeout=timeout_seconds) as response:
        payload = json.load(response)

    if not isinstance(payload, Mapping):
        raise TypeError("Unexpected CMS response shape.")
    rows = payload.get("results")
    if not isinstance(rows, list) or any(not isinstance(row, Mapping) for row in rows):
        raise TypeError("Unexpected CMS response shape.")
    return rows


def _provider_from_row(row: Mapping[str, object]) -> CmsProviderRecord:
    return CmsProviderRecord(
        ccn=str(row["cms_certification_number_ccn"]).strip(),
        provider_name=str(row["provider_name"]).strip(),
        zip_code=str(row["zip_code"]).strip()[:5],
        bed_count=_optional_int(row.get("number_of_certified_beds")),
        overall_rating=_optional_int(row.get("overall_rating")),
        staffing_rating=_optional_int(row.get("staffing_rating")),
        ownership_type=_optional_text(row.get("ownership_type")),
        chain_name=_optional_text(row.get("chain_name")),
        processing_date=_optional_text(row.get("processing_date")),
    )


def _ownership_from_row(row: Mapping[str, object]) -> OwnershipRecord:
    return OwnershipRecord(
        ccn=str(row["cms_certification_number_ccn"]).strip(),
        role=str(row["role_played_by_owner_or_manager_in_facility"]).strip(),
        owner_type=str(row["owner_type"]).strip(),
        owner_name=str(row["owner_name"]).strip(),
        ownership_percentage=_optional_text(row.get("ownership_percentage")),
        association_date=_optional_text(row.get("association_date")),
    )


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _optional_int(value: object) -> int | None:
    normalized = _optional_text(value)
    return int(normalized) if normalized is not None else None

