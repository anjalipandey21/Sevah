"""Tests for deterministic service and marketing extraction."""

import unittest

from sevah.affinity_models import WebsiteDocument, WebsiteEvidenceSource
from sevah.service_marketing import extract_service_marketing


class ServiceMarketingExtractionTests(unittest.TestCase):
    def test_extracts_configured_signals_and_respects_simple_negation(self) -> None:
        document = WebsiteDocument(
            url="https://example.com",
            text=(
                "We offer skilled nursing, rehabilitation, and physical therapy. "
                "We do not offer memory care. Our innovative care uses telehealth "
                "and remote patient monitoring to provide personalized care."
            ),
            content_characters=600,
        )

        extraction = extract_service_marketing(document)

        self.assertEqual(extraction.source, WebsiteEvidenceSource.LIVE_WEBSITE)
        self.assertIn("skilled_nursing", extraction.services)
        self.assertIn("rehabilitation", extraction.services)
        self.assertIn("physical_therapy", extraction.services)
        self.assertNotIn("memory_care", extraction.services)
        self.assertIn("telehealth", extraction.technology_signals)
        self.assertIn("remote_monitoring", extraction.technology_signals)
        self.assertIn("innovation", extraction.marketing_signals)
        self.assertIn("personalized_care", extraction.marketing_signals)
        self.assertEqual(extraction.pages_analyzed, 1)


if __name__ == "__main__":
    unittest.main()

