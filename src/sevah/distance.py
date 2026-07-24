"""Geospatial distance helpers."""

from math import asin, cos, radians, sin, sqrt
from typing import Iterable

from sevah.models import Coordinates, Facility, FacilityDistance

EARTH_RADIUS_MILES = 3_958.7613


def haversine_miles(origin: Coordinates, destination: Coordinates) -> float:
    """Return straight-line great-circle distance between two coordinates."""

    latitude_delta = radians(destination.latitude - origin.latitude)
    longitude_delta = radians(destination.longitude - origin.longitude)
    origin_latitude = radians(origin.latitude)
    destination_latitude = radians(destination.latitude)

    haversine_value = (
        sin(latitude_delta / 2) ** 2
        + cos(origin_latitude)
        * cos(destination_latitude)
        * sin(longitude_delta / 2) ** 2
    )
    return 2 * EARTH_RADIUS_MILES * asin(sqrt(haversine_value))


def rank_facilities(
    zip_center: Coordinates,
    facilities: Iterable[Facility],
    *,
    limit: int = 5,
) -> tuple[FacilityDistance, ...]:
    """Calculate distance and return facilities from nearest to farthest."""

    ranked = (
        FacilityDistance(
            facility=facility,
            distance_miles=haversine_miles(zip_center, facility.coordinates),
        )
        for facility in facilities
    )
    return tuple(
        sorted(ranked, key=lambda item: item.distance_miles)[: max(limit, 0)]
    )

