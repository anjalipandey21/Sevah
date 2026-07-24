"""Tests for CMS Provider Data Catalog response mapping."""

import io
import json
import unittest
from unittest.mock import patch

from sevah.services.cms_api import (
    fetch_cms_ownership_by_ccn,
    fetch_cms_providers_by_zip,
)


class _FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class CmsApiTests(unittest.TestCase):
    @patch("sevah.services.cms_api.urlopen")
    def test_provider_information_fields_are_mapped(self, urlopen) -> None:
        urlopen.return_value = _FakeResponse(
            json.dumps(
                {
                    "results": [
                        {
                            "cms_certification_number_ccn": "145510",
                            "provider_name": "AVANTARA LINCOLN PARK",
                            "zip_code": "60614",
                            "number_of_certified_beds": "248",
                            "overall_rating": "2",
                            "staffing_rating": "2",
                            "ownership_type": "For profit - Corporation",
                            "chain_name": "LEGACY HEALTHCARE",
                            "processing_date": "2026-06-01",
                        }
                    ]
                }
            ).encode("utf-8")
        )

        providers = fetch_cms_providers_by_zip("60614")

        self.assertEqual(len(providers), 1)
        self.assertEqual(providers[0].ccn, "145510")
        self.assertEqual(providers[0].bed_count, 248)
        self.assertEqual(providers[0].overall_rating, 2)
        self.assertEqual(providers[0].staffing_rating, 2)
        request = urlopen.call_args.args[0]
        self.assertIn("4pq5-n9py", request.full_url)
        self.assertIn("zip_code", request.full_url)

    @patch("sevah.services.cms_api.urlopen")
    def test_ownership_fields_are_mapped(self, urlopen) -> None:
        urlopen.return_value = _FakeResponse(
            json.dumps(
                {
                    "results": [
                        {
                            "cms_certification_number_ccn": "145510",
                            "role_played_by_owner_or_manager_in_facility": (
                                "5% OR GREATER DIRECT OWNERSHIP INTEREST"
                            ),
                            "owner_type": "Organization",
                            "owner_name": "TEST OWNER LLC",
                            "ownership_percentage": "60%",
                            "association_date": "since 10/06/2023",
                        }
                    ]
                }
            ).encode("utf-8")
        )

        ownership = fetch_cms_ownership_by_ccn("145510")

        self.assertEqual(len(ownership), 1)
        self.assertEqual(ownership[0].owner_name, "TEST OWNER LLC")
        request = urlopen.call_args.args[0]
        self.assertIn("y2hd-n93e", request.full_url)
        self.assertIn("cms_certification_number_ccn", request.full_url)


if __name__ == "__main__":
    unittest.main()

