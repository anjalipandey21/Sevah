"""Offline US ZIP-code centroid lookup."""

import zipcodes

from sevah.models import Coordinates


class UnknownZipCodeError(ValueError):
    """Raised when a syntactically valid ZIP code has no known centroid."""


def get_zip_center(zip_code: str) -> Coordinates:
    """Resolve a five-digit US ZIP code to its approximate centroid."""

    matches = zipcodes.matching(zip_code)
    if not matches:
        raise UnknownZipCodeError(f"ZIP code {zip_code} was not found.")

    match = matches[0]
    latitude = match.get("lat")
    longitude = match.get("long")
    if latitude in (None, "") or longitude in (None, ""):
        raise UnknownZipCodeError(f"ZIP code {zip_code} has no known coordinates.")

    return Coordinates(latitude=float(latitude), longitude=float(longitude))

