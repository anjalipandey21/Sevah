"""Tests for the management and ownership adapter."""

import unittest
from pathlib import Path

from sevah.cms_models import OwnershipDataSource, OwnershipRecord
from sevah.services.cms_api import CmsOwnershipError
from sevah.services.ownership import CmsOwnershipAdapter


class OwnershipAdapterTests(unittest.TestCase):
    def test_live_cms_ownership_is_preferred(self) -> None:
        live_record = OwnershipRecord(
            ccn="145510",
            role="Managing employee",
            owner_type="Organization",
            owner_name="Live Management LLC",
        )
        adapter = CmsOwnershipAdapter(live_loader=lambda _: [live_record])

        result = adapter.get_for_ccn("145510")

        self.assertEqual(result.source, OwnershipDataSource.LIVE_CMS)
        self.assertEqual(result.records, (live_record,))
        self.assertIn("Live", result.notice)

    def test_failed_live_request_returns_unavailable_by_default(self) -> None:
        def unavailable(_: str) -> list[OwnershipRecord]:
            raise CmsOwnershipError("unavailable")

        result = CmsOwnershipAdapter(live_loader=unavailable).get_for_ccn("145510")

        self.assertEqual(result.source, OwnershipDataSource.UNAVAILABLE)
        self.assertEqual(result.records, ())
        self.assertIn("No verified CMS", result.notice)

    def test_sample_fallback_requires_explicit_injection(self) -> None:
        def unavailable(_: str) -> list[OwnershipRecord]:
            raise CmsOwnershipError("unavailable")

        sample_path = (
            Path(__file__).parents[1]
            / "src"
            / "sevah"
            / "data"
            / "sample_ownership.json"
        )
        result = CmsOwnershipAdapter(
            live_loader=unavailable,
            sample_path=sample_path,
        ).get_for_ccn("145510")

        self.assertIn("fictional sample", result.notice)
        self.assertIn("does not describe CCN 145510", result.notice)
        self.assertIn("Sample", result.records[0].role)


if __name__ == "__main__":
    unittest.main()
