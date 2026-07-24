"""Streamlit UI for the facility discovery flow."""

import streamlit as st
from dotenv import load_dotenv
from pydantic import ValidationError

from sevah.discovery import discover_facilities
from sevah.models import DataSource
from sevah.services.zip_codes import UnknownZipCodeError


def render_app() -> None:
    """Render the Sevah facility discovery page."""

    load_dotenv()
    st.set_page_config(page_title="Sevah", page_icon="📍")
    st.title("Find assisted-living facilities")
    st.caption("Enter a five-digit US ZIP code to see the five nearest results.")

    with st.form("facility-search"):
        zip_code = st.text_input(
            "ZIP code",
            max_chars=5,
            placeholder="60601",
        )
        submitted = st.form_submit_button("Find facilities", type="primary")

    if not submitted:
        return

    try:
        result = discover_facilities(zip_code)
    except ValidationError:
        st.error("Enter a valid five-digit ZIP code.")
        return
    except UnknownZipCodeError:
        st.error("That ZIP code could not be located. Enter a valid US ZIP code.")
        return

    if result.source is DataSource.LIVE:
        st.success(f"Source: Live Google Places data. {result.notice}")
    else:
        st.warning(f"Source: Bundled sample data. {result.notice}")

    if not result.facilities:
        st.info("No assisted-living facilities were found near this ZIP code.")
        return

    for position, item in enumerate(result.facilities, start=1):
        facility = item.facility
        with st.container(border=True):
            st.subheader(f"{position}. {facility.name}")
            st.write(facility.address)
            st.write(f"**Straight-line distance:** {item.distance_miles:.1f} miles")
            st.write(
                f"**Rating:** {facility.rating:.1f}"
                if facility.rating is not None
                else "**Rating:** Not available"
            )
            st.write(f"**Place ID:** {facility.place_id or 'Sample data'}")
            if facility.website:
                st.link_button("Visit website", facility.website)
            else:
                st.caption("Website not available")

