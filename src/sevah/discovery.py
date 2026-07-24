"""LangGraph-orchestrated facility discovery flow."""

import os
from functools import lru_cache
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from sevah.distance import rank_facilities
from sevah.models import (
    Coordinates,
    DataSource,
    DiscoveryResult,
    Facility,
    FacilityDistance,
    ZipCodeQuery,
)
from sevah.services.google_places import (
    GooglePlacesError,
    search_assisted_living_facilities,
)
from sevah.services.sample_facilities import load_sample_facilities
from sevah.services.zip_codes import get_zip_center


class DiscoveryState(TypedDict, total=False):
    query: ZipCodeQuery
    api_key: str | None
    limit: int
    zip_center: Coordinates
    facilities: list[Facility]
    ranked_facilities: tuple[FacilityDistance, ...]
    source: DataSource
    notice: str
    live_search_failed: bool


def _resolve_zip(state: DiscoveryState) -> DiscoveryState:
    return {"zip_center": get_zip_center(state["query"].zip_code)}


def _choose_source(state: DiscoveryState) -> str:
    return "search_live" if state.get("api_key") else "load_sample"


def _search_live(state: DiscoveryState) -> DiscoveryState:
    try:
        facilities = search_assisted_living_facilities(
            api_key=state["api_key"] or "",
            zip_center=state["zip_center"],
        )
        return {
            "facilities": facilities,
            "source": DataSource.LIVE,
            "notice": "Live results from Google Places.",
            "live_search_failed": False,
        }
    except GooglePlacesError:
        return {"live_search_failed": True}


def _after_live_search(state: DiscoveryState) -> str:
    return "load_sample" if state.get("live_search_failed") else "rank"


def _load_sample(state: DiscoveryState) -> DiscoveryState:
    data_path = os.getenv("SEVAH_FACILITY_DATA_PATH")
    reason = (
        "the Google Places request was unavailable"
        if state.get("live_search_failed")
        else "GOOGLE_PLACES_API_KEY is not configured"
    )
    return {
        "facilities": load_sample_facilities(data_path),
        "source": DataSource.SAMPLE,
        "notice": f"Sample data is shown because {reason}.",
    }


def _rank(state: DiscoveryState) -> DiscoveryState:
    return {
        "ranked_facilities": rank_facilities(
            state["zip_center"],
            state["facilities"],
            limit=state["limit"],
        )
    }


@lru_cache(maxsize=1)
def _build_discovery_graph():
    graph = StateGraph(DiscoveryState)
    graph.add_node("resolve_zip", _resolve_zip)
    graph.add_node("search_live", _search_live)
    graph.add_node("load_sample", _load_sample)
    graph.add_node("rank", _rank)

    graph.add_edge(START, "resolve_zip")
    graph.add_conditional_edges(
        "resolve_zip",
        _choose_source,
        {"search_live": "search_live", "load_sample": "load_sample"},
    )
    graph.add_conditional_edges(
        "search_live",
        _after_live_search,
        {"load_sample": "load_sample", "rank": "rank"},
    )
    graph.add_edge("load_sample", "rank")
    graph.add_edge("rank", END)
    return graph.compile()


def discover_facilities(
    zip_code: str,
    *,
    api_key: str | None = None,
    limit: int = 5,
) -> DiscoveryResult:
    """Discover and rank assisted-living facilities for one US ZIP code."""

    query = ZipCodeQuery(zip_code=zip_code)
    resolved_api_key = api_key if api_key is not None else os.getenv(
        "GOOGLE_PLACES_API_KEY"
    )
    state = _build_discovery_graph().invoke(
        {
            "query": query,
            "api_key": resolved_api_key,
            "limit": limit,
        }
    )
    return DiscoveryResult(
        query=query,
        zip_center=state["zip_center"],
        source=state["source"],
        facilities=state["ranked_facilities"],
        notice=state["notice"],
    )

