"""Tests for safe feedback-driven graph rebuilding."""

import unittest

from pydantic import ValidationError

from sevah.safe_feedback import (
    AdjustAffinityScoreFeedback,
    ApproveResultFeedback,
    CorrectServiceFeedback,
    EnableNodeFeedback,
    EnableNodeWithPromptFeedback,
    EvaluationInput,
    GraphSpec,
    UpdateNodePromptFeedback,
    WorkflowEvaluationConfig,
    apply_feedback,
    build_evaluation_graph,
    run_evaluation,
)


class SafeFeedbackTests(unittest.TestCase):
    def test_default_and_research_paths_use_only_legal_edges(self) -> None:
        config = WorkflowEvaluationConfig()
        default_result = run_evaluation(
            build_evaluation_graph(config),
            EvaluationInput(
                facility_id="facility-1",
                services=("skilled_nursing",),
                affinity_score=40,
            ),
            graph_revision=0,
        )
        self.assertEqual(
            default_result.executed_nodes,
            ("positioning", "scope", "scoring"),
        )

        rebuilt = apply_feedback(
            config,
            EnableNodeFeedback(
                action="enable_node",
                node_name="technology_research",
            ),
        )
        research_result = run_evaluation(
            rebuilt.graph,
            EvaluationInput(
                facility_id="facility-1",
                services=("skilled_nursing",),
                affinity_score=40,
            ),
            graph_revision=rebuilt.config.graph_spec.revision,
        )
        self.assertEqual(
            research_result.executed_nodes,
            ("positioning", "technology_research", "scope", "scoring"),
        )
        self.assertEqual(research_result.graph_revision, 1)

    def test_structured_feedback_changes_only_next_execution(self) -> None:
        config = WorkflowEvaluationConfig()
        service_update = apply_feedback(
            config,
            {
                "action": "correct_service",
                "facility_id": "facility-1",
                "service": "memory_care",
                "present": True,
            },
        )
        service_result = run_evaluation(
            service_update.graph,
            EvaluationInput(
                facility_id="facility-1",
                services=("skilled_nursing",),
                affinity_score=40,
            ),
            graph_revision=service_update.config.graph_spec.revision,
        )
        self.assertEqual(service_result.affinity_score, 44)
        score_update = apply_feedback(
            service_update.config,
            AdjustAffinityScoreFeedback(
                action="adjust_affinity_score",
                facility_id="facility-1",
                score=72,
                reason="Reviewer verified deployment readiness.",
            ),
        )
        approval = apply_feedback(
            score_update.config,
            ApproveResultFeedback(
                action="approve_result",
                facility_id="facility-1",
            ),
        )

        result = run_evaluation(
            approval.graph,
            EvaluationInput(
                facility_id="facility-1",
                services=("skilled_nursing",),
                affinity_score=40,
            ),
            graph_revision=approval.config.graph_spec.revision,
        )

        self.assertIn("memory_care", result.services)
        self.assertEqual(result.affinity_score, 72)
        self.assertTrue(result.approved)
        self.assertEqual(result.graph_revision, 3)

    def test_prompt_updates_are_restricted_to_registered_nodes(self) -> None:
        rebuilt = apply_feedback(
            WorkflowEvaluationConfig(),
            UpdateNodePromptFeedback(
                action="update_node_prompt",
                node_name="scope",
                prompt="Use reviewer-confirmed services only.",
            ),
        )
        result = run_evaluation(
            rebuilt.graph,
            EvaluationInput(
                facility_id="facility-1",
                services=(),
                affinity_score=0,
            ),
            graph_revision=rebuilt.config.graph_spec.revision,
        )
        self.assertEqual(
            result.effective_prompts["scope"],
            "Use reviewer-confirmed services only.",
        )

        with self.assertRaises(ValidationError):
            UpdateNodePromptFeedback(
                action="update_node_prompt",
                node_name="arbitrary_node",
                prompt="Run code.",
            )

    def test_atomic_feedback_enables_node_prompt_and_route_once(self) -> None:
        rebuilt = apply_feedback(
            WorkflowEvaluationConfig(),
            EnableNodeWithPromptFeedback(
                action="enable_node_with_prompt",
                node_name="technology_research",
                prompt="Use only explicit official evidence.",
            ),
        )
        result = run_evaluation(
            rebuilt.graph,
            EvaluationInput(
                facility_id="facility-1",
                services=(),
                affinity_score=0,
            ),
            graph_revision=rebuilt.config.graph_spec.revision,
        )

        self.assertEqual(rebuilt.config.graph_spec.revision, 1)
        self.assertIn(
            "technology_research",
            rebuilt.config.graph_spec.enabled_nodes,
        )
        self.assertEqual(
            rebuilt.config.graph_spec.prompt_overrides["technology_research"],
            "Use only explicit official evidence.",
        )
        self.assertEqual(
            result.executed_nodes,
            ("positioning", "technology_research", "scope", "scoring"),
        )
        self.assertEqual(
            result.effective_prompts["technology_research"],
            "Use only explicit official evidence.",
        )

    def test_unknown_nodes_services_and_edges_are_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            EnableNodeFeedback(
                action="enable_node",
                node_name="arbitrary_node",
            )
        with self.assertRaises(ValidationError):
            EnableNodeWithPromptFeedback(
                action="enable_node_with_prompt",
                node_name="scope",
                prompt="Not optional.",
            )
        with self.assertRaises(ValidationError):
            CorrectServiceFeedback(
                action="correct_service",
                facility_id="facility-1",
                service="invented_service",
                present=True,
            )
        with self.assertRaises(ValidationError):
            GraphSpec.model_validate(
                {
                    "enabled_nodes": ["positioning", "scope", "scoring"],
                    "prompt_overrides": {},
                    "revision": 0,
                    "edges": [["positioning", "arbitrary_node"]],
                }
            )


if __name__ == "__main__":
    unittest.main()
