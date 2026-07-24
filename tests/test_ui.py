"""Headless smoke test for the Streamlit facility discovery page."""

import os
import unittest
from unittest.mock import MagicMock, patch

from streamlit.testing.v1 import AppTest

from sevah.affinity_models import TechnologyEvidence, TechnologyResearchResult
from sevah.cms_models import (
    OwnershipDataSource,
    OwnershipRecord,
    OwnershipResult,
)
from sevah.ui import _render_management


class StreamlitUiTests(unittest.TestCase):
    def test_live_management_records_are_displayed_as_verified(self) -> None:
        result = OwnershipResult(
            requested_ccn="145510",
            source=OwnershipDataSource.LIVE_CMS,
            records=(
                OwnershipRecord(
                    ccn="145510",
                    role="Managing employee",
                    owner_type="Organization",
                    owner_name="Verified Manager LLC",
                    ownership_percentage="25",
                    association_date="2024-01-01",
                ),
            ),
            notice="Live CMS.",
        )
        streamlit = MagicMock()
        with patch("sevah.ui.st", streamlit):
            _render_management(result)

        rows = streamlit.dataframe.call_args.args[0]
        self.assertEqual(rows[0]["Name"], "Verified Manager LLC")
        self.assertEqual(rows[0]["Role"], "Managing employee")

    def test_unavailable_management_is_not_displayed_as_verified(self) -> None:
        result = OwnershipResult(
            requested_ccn="145510",
            source=OwnershipDataSource.UNAVAILABLE,
            records=(),
            notice="Unavailable.",
        )
        streamlit = MagicMock()
        with patch("sevah.ui.st", streamlit):
            _render_management(result)

        streamlit.dataframe.assert_not_called()
        self.assertTrue(
            any(
                "No verified CMS" in call.args[0]
                for call in streamlit.write.call_args_list
            )
        )

    def test_sample_results_are_clearly_labeled(self) -> None:
        with (
            patch.dict(os.environ, {"GOOGLE_PLACES_API_KEY": ""}),
            patch(
                "sevah.cms_enrichment.fetch_cms_providers_by_zip",
                return_value=[],
            ),
        ):
            app = AppTest.from_file("streamlit_app.py")
            app.run(timeout=30)
            app.text_input[0].set_value("60601")
            app.button[0].click()
            app.run(timeout=30)

            self.assertEqual(len(app.exception), 0)
            self.assertTrue(
                any(
                    "Bundled sample data" in warning.value
                    for warning in app.warning
                )
            )
            self.assertEqual(len(app.subheader), 5)

            next(
                button for button in app.button
                if button.label == "Apply feedback"
            ).click()
            app.run(timeout=30)
            self.assertTrue(
                any(
                    metric.label == "Graph revision" and str(metric.value) == "1"
                    for metric in app.metric
                )
            )

            next(
                button for button in app.button
                if button.label == "Submit review"
            ).click()
            app.run(timeout=30)
            self.assertEqual(len(app.exception), 0)
            self.assertTrue(
                any(
                    "workflow result was approved" in message.value
                    for message in app.success
                )
            )

    def test_atomic_technology_feedback_is_visible_in_demo(self) -> None:
        research = TechnologyResearchResult(
            status="completed",
            signals=("telehealth",),
            evidence=(
                TechnologyEvidence(
                    signal="telehealth",
                    matched_term="telehealth",
                    source_url="https://facility.test/technology",
                ),
            ),
            pages_checked=("https://facility.test/technology",),
            effective_prompt=(
                "Prioritize official facility evidence and identify only "
                "explicitly documented healthcare technology signals."
            ),
            notice="Test bounded research.",
        )
        with (
            patch.dict(os.environ, {"GOOGLE_PLACES_API_KEY": ""}),
            patch(
                "sevah.cms_enrichment.fetch_cms_providers_by_zip",
                return_value=[],
            ),
            patch(
                "sevah.safe_feedback.research_facility_technology",
                return_value=research,
            ),
        ):
            app = AppTest.from_file("streamlit_app.py")
            app.run(timeout=30)
            app.text_input[0].set_value("60601")
            app.button[0].click()
            app.run(timeout=30)

            app.segmented_control[0].set_value("Enable technology research")
            app.run(timeout=30)
            next(
                button for button in app.button
                if button.label == "Apply feedback"
            ).click()
            app.run(timeout=30)

            self.assertEqual(len(app.exception), 0)
            self.assertTrue(
                any(
                    metric.label == "Graph revision" and str(metric.value) == "1"
                    for metric in app.metric
                )
            )
            rendered_text = " ".join(item.value for item in app.markdown)
            self.assertIn(
                "positioning → technology_research → scope → scoring",
                rendered_text,
            )
            self.assertIn("Technology score impact", rendered_text)


if __name__ == "__main__":
    unittest.main()
