"""Headless smoke test for the Streamlit facility discovery page."""

import os
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest


class StreamlitUiTests(unittest.TestCase):
    def test_sample_results_are_clearly_labeled(self) -> None:
        with patch.dict(os.environ, {"GOOGLE_PLACES_API_KEY": ""}):
            app = AppTest.from_file("streamlit_app.py")
            app.run(timeout=30)
            app.text_input[0].set_value("60601")
            app.button[0].click()
            app.run(timeout=30)

        self.assertEqual(len(app.exception), 0)
        self.assertTrue(
            any("Bundled sample data" in warning.value for warning in app.warning)
        )
        self.assertEqual(len(app.subheader), 5)


if __name__ == "__main__":
    unittest.main()

