"""Management and ownership adapter with explicit sample fallback."""

import json
from pathlib import Path
from typing import Callable, Protocol

from pydantic import TypeAdapter

from sevah.cms_models import (
    OwnershipDataSource,
    OwnershipRecord,
    OwnershipResult,
)
from sevah.services.cms_api import CmsOwnershipError, fetch_cms_ownership_by_ccn

DEFAULT_SAMPLE_OWNERSHIP_PATH = (
    Path(__file__).parents[1] / "data" / "sample_ownership.json"
)
OWNERSHIP_LIST_ADAPTER = TypeAdapter(list[OwnershipRecord])


class ManagementOwnershipAdapter(Protocol):
    """Boundary for retrieving management or ownership information."""

    def get_for_ccn(self, ccn: str) -> OwnershipResult:
        """Return ownership data with explicit provenance."""


class CmsOwnershipAdapter:
    """Use live CMS Ownership data with explicit unavailable handling."""

    def __init__(
        self,
        *,
        live_loader: Callable[[str], list[OwnershipRecord]] | None = None,
        sample_path: str | Path | None = None,
    ) -> None:
        self._live_loader = live_loader or fetch_cms_ownership_by_ccn
        self._sample_path = Path(sample_path) if sample_path else None

    def get_for_ccn(self, ccn: str) -> OwnershipResult:
        try:
            records = self._live_loader(ccn)
        except CmsOwnershipError:
            return self._fallback_result(
                ccn,
                "Live CMS Ownership data was unavailable.",
            )

        if not records:
            return self._fallback_result(
                ccn,
                "CMS returned no ownership or management rows for this CCN.",
            )

        return OwnershipResult(
            requested_ccn=ccn,
            source=OwnershipDataSource.LIVE_CMS,
            records=tuple(records),
            notice="Live management and ownership data from the CMS Ownership dataset.",
        )

    def _fallback_result(self, ccn: str, reason: str) -> OwnershipResult:
        if self._sample_path is None:
            return OwnershipResult(
                requested_ccn=ccn,
                source=OwnershipDataSource.UNAVAILABLE,
                records=(),
                notice=(
                    f"{reason} No verified CMS ownership or management records "
                    "were available."
                ),
            )
        with self._sample_path.open(encoding="utf-8") as sample_file:
            records = OWNERSHIP_LIST_ADAPTER.validate_python(json.load(sample_file))
        return OwnershipResult(
            requested_ccn=ccn,
            source=OwnershipDataSource.SAMPLE,
            records=tuple(records),
            notice=(
                f"{reason} Showing fictional sample management data; it does not "
                f"describe CCN {ccn}."
            ),
        )
