"""Structured domain models for the facility discovery flow."""

from enum import Enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


ZipCode = Annotated[
    str,
    StringConstraints(pattern=r"^\d{5}$", strip_whitespace=True),
]


class SevahModel(BaseModel):
    """Base model with strict, immutable domain data."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class Coordinates(SevahModel):
    """A point expressed in decimal degrees."""

    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class Facility(SevahModel):
    """A facility available to the proximity search."""

    facility_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    address: str = Field(min_length=1)
    coordinates: Coordinates
    website: str | None = None
    rating: float | None = Field(default=None, ge=0, le=5)
    place_id: str | None = None


class ZipCodeQuery(SevahModel):
    """Validated input supplied by a user."""

    zip_code: ZipCode


class FacilityDistance(SevahModel):
    """A facility paired with a calculated straight-line distance."""

    facility: Facility
    distance_miles: float = Field(ge=0)


class DataSource(str, Enum):
    """Origin of the facilities returned to the user."""

    LIVE = "live"
    SAMPLE = "sample"


class DiscoveryResult(SevahModel):
    """Complete, display-ready facility discovery response."""

    query: ZipCodeQuery
    zip_center: Coordinates
    source: DataSource
    facilities: tuple[FacilityDistance, ...]
    notice: str = Field(min_length=1)
