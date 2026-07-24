"""Tests for Google Places response mapping."""

import io
import json
import unittest
from unittest.mock import patch

from sevah.models import Coordinates
from sevah.services.google_places import search_assisted_living_facilities


class _FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class GooglePlacesTests(unittest.TestCase):
    @patch("sevah.services.google_places.urlopen")
    def test_search_maps_required_live_fields(self, urlopen) -> None:
        urlopen.return_value = _FakeResponse(
            json.dumps(
                {
                    "places": [
                        {
                            "id": "google-place-123",
                            "displayName": {"text": "Test Assisted Living"},
                            "formattedAddress": "1 Main St, Chicago, IL 60601",
                            "location": {
                                "latitude": 41.88,
                                "longitude": -87.63,
                            },
                            "websiteUri": "https://example.com",
                            "rating": 4.7,
                        }
                    ]
                }
            ).encode("utf-8")
        )

        facilities = search_assisted_living_facilities(
            "test-key",
            Coordinates(latitude=41.88, longitude=-87.63),
        )

        self.assertEqual(len(facilities), 1)
        self.assertEqual(facilities[0].name, "Test Assisted Living")
        self.assertEqual(facilities[0].place_id, "google-place-123")
        self.assertEqual(facilities[0].website, "https://example.com")
        self.assertEqual(facilities[0].rating, 4.7)


if __name__ == "__main__":
    unittest.main()

