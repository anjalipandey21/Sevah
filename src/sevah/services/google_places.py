"""Google Places API integration.

All Google-specific request and response handling is isolated in this module.
"""

import json
from collections.abc import Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pydantic import ValidationError

from sevah.models import Coordinates, Facility

PLACES_TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
PLACES_FIELD_MASK = ",".join(
    (
        "places.id",
        "places.displayName",
        "places.formattedAddress",
        "places.location",
        "places.websiteUri",
        "places.rating",
    )
)


class GooglePlacesError(RuntimeError):
    """Raised when live facility discovery cannot produce a valid response."""


def search_assisted_living_facilities(
    api_key: str,
    zip_center: Coordinates,
    *,
    page_size: int = 20,
    radius_meters: float = 50_000,
    timeout_seconds: float = 10,
) -> list[Facility]:
    """Search Google Places for assisted-living facilities near a ZIP center."""

    if not api_key.strip():
        raise GooglePlacesError("A Google Places API key is required.")

    body = json.dumps(
        {
            "textQuery": "assisted living facility",
            "pageSize": min(max(page_size, 1), 20),
            "regionCode": "US",
            "rankPreference": "DISTANCE",
            "locationBias": {
                "circle": {
                    "center": {
                        "latitude": zip_center.latitude,
                        "longitude": zip_center.longitude,
                    },
                    "radius": radius_meters,
                }
            },
        }
    ).encode("utf-8")
    request = Request(
        PLACES_TEXT_SEARCH_URL,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": PLACES_FIELD_MASK,
        },
    )

    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            payload = json.load(response)
        if not isinstance(payload, Mapping):
            raise TypeError("Unexpected Google Places response shape.")
        places = payload.get("places", [])
        if not isinstance(places, list):
            raise TypeError("Unexpected Google Places response shape.")
        return [_parse_place(place) for place in places]
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise GooglePlacesError("Google Places request failed.") from exc
    except (KeyError, TypeError, ValidationError) as exc:
        raise GooglePlacesError("Google Places returned an invalid response.") from exc


def _parse_place(place: Mapping[str, object]) -> Facility:
    """Map one Google Place response into the Sevah domain model."""

    place_id = str(place["id"])
    display_name = place["displayName"]
    location = place["location"]
    if not isinstance(display_name, dict) or not isinstance(location, dict):
        raise TypeError("Unexpected Google Place response shape.")

    return Facility(
        facility_id=place_id,
        name=display_name["text"],
        address=place["formattedAddress"],
        coordinates=Coordinates(
            latitude=location["latitude"],
            longitude=location["longitude"],
        ),
        website=place.get("websiteUri"),
        rating=place.get("rating"),
        place_id=place_id,
    )
