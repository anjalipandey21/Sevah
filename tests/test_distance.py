"""Tests for Haversine calculation and ranking."""

import unittest

from sevah.distance import haversine_miles, rank_facilities
from sevah.models import Coordinates, Facility


def _facility(facility_id: str, latitude: float, longitude: float) -> Facility:
    return Facility(
        facility_id=facility_id,
        name=facility_id.title(),
        address="1 Test Way",
        coordinates=Coordinates(latitude=latitude, longitude=longitude),
    )


class DistanceTests(unittest.TestCase):
    def test_same_location_has_zero_distance(self) -> None:
        point = Coordinates(latitude=41.88, longitude=-87.63)
        self.assertEqual(haversine_miles(point, point), 0)

    def test_rank_facilities_returns_nearest_first_and_applies_limit(self) -> None:
        origin = Coordinates(latitude=0, longitude=0)
        facilities = [
            _facility("far", 3, 0),
            _facility("nearest", 0.25, 0),
            _facility("middle", 1, 0),
        ]

        ranked = rank_facilities(origin, facilities, limit=2)

        self.assertEqual(
            [item.facility.facility_id for item in ranked],
            ["nearest", "middle"],
        )


if __name__ == "__main__":
    unittest.main()

