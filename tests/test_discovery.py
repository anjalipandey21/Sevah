"""Tests for source selection and facility discovery orchestration."""

import unittest
from unittest.mock import patch

from pydantic import ValidationError

from sevah.discovery import discover_facilities
from sevah.models import Coordinates, DataSource, Facility
from sevah.services.google_places import GooglePlacesError


def _facility(
    facility_id: str,
    latitude: float,
    longitude: float,
) -> Facility:
    return Facility(
        facility_id=facility_id,
        name=f"Facility {facility_id}",
        address="1 Test Way, Chicago, IL 60601",
        coordinates=Coordinates(latitude=latitude, longitude=longitude),
        website="https://example.com",
        rating=4.5,
        place_id=facility_id,
    )


class DiscoveryTests(unittest.TestCase):
    def test_input_must_be_exactly_five_digits(self) -> None:
        for invalid_zip_code in ("6060", "60601-1234", "ABCDE"):
            with self.subTest(zip_code=invalid_zip_code):
                with self.assertRaises(ValidationError):
                    discover_facilities(invalid_zip_code, api_key="")

    def test_missing_api_key_uses_sample_data(self) -> None:
        result = discover_facilities("60601", api_key="")

        self.assertEqual(result.source, DataSource.SAMPLE)
        self.assertEqual(len(result.facilities), 5)
        self.assertIn("not configured", result.notice)
        self.assertTrue(
            all(
                left.distance_miles <= right.distance_miles
                for left, right in zip(result.facilities, result.facilities[1:])
            )
        )

    @patch("sevah.discovery.search_assisted_living_facilities")
    def test_successful_live_search_uses_and_sorts_live_data(
        self,
        search_live,
    ) -> None:
        search_live.return_value = [
            _facility("far", 42.1, -87.6),
            _facility("near", 41.886, -87.623),
        ]

        result = discover_facilities("60601", api_key="test-key")

        self.assertEqual(result.source, DataSource.LIVE)
        self.assertEqual(
            [item.facility.place_id for item in result.facilities],
            ["near", "far"],
        )
        self.assertIn("Live results", result.notice)

    @patch("sevah.discovery.search_assisted_living_facilities")
    def test_failed_live_search_falls_back_to_sample_data(
        self,
        search_live,
    ) -> None:
        search_live.side_effect = GooglePlacesError("service unavailable")

        result = discover_facilities("60601", api_key="test-key")

        self.assertEqual(result.source, DataSource.SAMPLE)
        self.assertEqual(len(result.facilities), 5)
        self.assertIn("request was unavailable", result.notice)


if __name__ == "__main__":
    unittest.main()
