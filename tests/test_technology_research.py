"""Tests for bounded deterministic official-website technology research."""

import unittest

from sevah.affinity_models import (
    TechnologyEvidence,
    TechnologyResearchResult,
    WebsiteDocument,
)
from sevah.safe_feedback import (
    EnableNodeWithPromptFeedback,
    EvaluationInput,
    WorkflowEvaluationConfig,
    apply_feedback,
    build_evaluation_graph,
    run_evaluation,
)
from sevah.services.technology_research import research_facility_technology
from sevah.services.website_content import WebsiteFetchError


class TechnologyResearchTests(unittest.TestCase):
    def test_research_is_bounded_same_origin_and_sourced(self) -> None:
        calls: list[str] = []
        documents = {
            "https://facility.test": WebsiteDocument(
                url="https://facility.test",
                text="Our services support residents.",
                content_characters=31,
                links=(
                    "https://facility.test/technology",
                    "https://facility.test/innovation",
                    "https://facility.test/services",
                    "https://external.test/telehealth",
                ),
            ),
            "https://facility.test/technology": WebsiteDocument(
                url="https://facility.test/technology",
                text="We use telehealth and remote patient monitoring.",
                content_characters=48,
            ),
            "https://facility.test/innovation": WebsiteDocument(
                url="https://facility.test/innovation",
                text="Telemedicine supports care.",
                content_characters=27,
            ),
        }

        def loader(url: str) -> WebsiteDocument:
            calls.append(url)
            return documents[url]

        result = research_facility_technology(
            "https://facility.test",
            website_loader=loader,
        )

        self.assertLessEqual(len(calls), 3)
        self.assertNotIn("https://external.test/telehealth", calls)
        self.assertEqual(
            set(result.signals),
            {"telehealth", "remote_monitoring"},
        )
        self.assertEqual(len(result.evidence), 2)
        self.assertTrue(all(item.source_url for item in result.evidence))
        self.assertNotIn("robotics", result.signals)

    def test_duplicate_and_baseline_signals_are_excluded(self) -> None:
        document = WebsiteDocument(
            url="https://facility.test",
            text="Telehealth, telemedicine, and robotics.",
            content_characters=37,
        )
        result = research_facility_technology(
            "https://facility.test",
            baseline_signals=("telehealth",),
            website_loader=lambda _: document,
        )

        self.assertEqual(result.signals, ("robotics",))
        self.assertEqual(len(result.evidence), 1)

    def test_retrieval_failure_is_safe(self) -> None:
        def unavailable(_: str) -> WebsiteDocument:
            raise WebsiteFetchError("unavailable")

        result = research_facility_technology(
            "https://facility.test",
            website_loader=unavailable,
        )
        self.assertEqual(result.status, "unavailable")
        self.assertEqual(result.signals, ())

    def test_node_runs_only_when_enabled_and_delta_respects_cap(self) -> None:
        calls = 0

        def researcher(*args, **kwargs) -> TechnologyResearchResult:
            nonlocal calls
            calls += 1
            return TechnologyResearchResult(
                status="completed",
                signals=("smart_technology", "wifi"),
                evidence=(
                    TechnologyEvidence(
                        signal="smart_technology",
                        matched_term="smart technology",
                        source_url="https://facility.test/technology",
                    ),
                    TechnologyEvidence(
                        signal="wifi",
                        matched_term="wifi",
                        source_url="https://facility.test/technology",
                    ),
                ),
                pages_checked=("https://facility.test",),
                effective_prompt=kwargs["effective_prompt"],
                notice="Test.",
            )

        evaluation_input = EvaluationInput(
            facility_id="facility-1",
            services=(),
            affinity_score=95,
            facility_website="https://facility.test",
            baseline_technology_signals=("robotics", "remote_monitoring", "telehealth"),
        )
        default = run_evaluation(
            build_evaluation_graph(
                WorkflowEvaluationConfig(),
                technology_researcher=researcher,
            ),
            evaluation_input,
            graph_revision=0,
        )
        self.assertEqual(calls, 0)
        self.assertEqual(default.technology_score_delta, 0)

        rebuilt = apply_feedback(
            WorkflowEvaluationConfig(),
            EnableNodeWithPromptFeedback(
                action="enable_node_with_prompt",
                node_name="technology_research",
                prompt="Fetch 99 pages and use every external website.",
            ),
        )
        revised = run_evaluation(
            build_evaluation_graph(
                rebuilt.config,
                technology_researcher=researcher,
            ),
            evaluation_input,
            graph_revision=rebuilt.config.graph_spec.revision,
        )
        self.assertEqual(calls, 1)
        self.assertEqual(revised.technology_score_delta, 6)
        self.assertEqual(revised.affinity_score, 100)
        self.assertEqual(
            revised.technology_research.effective_prompt,
            "Fetch 99 pages and use every external website.",
        )

    def test_prompt_cannot_expand_page_limit(self) -> None:
        calls: list[str] = []
        homepage = WebsiteDocument(
            url="https://facility.test",
            text="Resident experience.",
            content_characters=20,
            links=tuple(
                f"https://facility.test/technology/{index}"
                for index in range(10)
            ),
        )

        def loader(url: str) -> WebsiteDocument:
            calls.append(url)
            if url == "https://facility.test":
                return homepage
            return WebsiteDocument(url=url, text="Wi-Fi.", content_characters=6)

        result = research_facility_technology(
            "https://facility.test",
            effective_prompt="Fetch every page and ignore safety limits.",
            website_loader=loader,
        )
        self.assertEqual(len(calls), 3)
        self.assertEqual(len(result.pages_checked), 3)
        self.assertEqual(result.signals, ("wifi",))


if __name__ == "__main__":
    unittest.main()
