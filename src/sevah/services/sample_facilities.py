"""Repository for bundled sample facilities."""

import json
from pathlib import Path

from pydantic import TypeAdapter

from sevah.models import Facility

DEFAULT_DATA_PATH = Path(__file__).parents[1] / "data" / "facilities.json"
FACILITY_LIST_ADAPTER = TypeAdapter(list[Facility])


def load_sample_facilities(data_path: str | Path | None = None) -> list[Facility]:
    """Load and validate bundled sample facility records."""

    path = Path(data_path) if data_path else DEFAULT_DATA_PATH
    with path.open(encoding="utf-8") as data_file:
        return FACILITY_LIST_ADAPTER.validate_python(json.load(data_file))

