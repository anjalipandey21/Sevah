"""Safe, deterministic workflow configuration from structured human feedback."""

from collections.abc import Callable, Mapping
from enum import Enum
from types import MappingProxyType
from typing import Annotated, Literal, NamedTuple, TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import (
    Field,
    StringConstraints,
    TypeAdapter,
    field_validator,
    model_validator,
)

from sevah.models import SevahModel
from sevah.affinity_models import TechnologyResearchResult
from sevah.robotics_affinity import SERVICE_WEIGHTS, TECHNOLOGY_WEIGHTS
from sevah.service_marketing import SERVICE_PATTERNS, TECHNOLOGY_PATTERNS
from sevah.services.technology_research import (
    DEFAULT_TECHNOLOGY_RESEARCH_PROMPT,
    research_facility_technology,
)

PromptText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=4_000),
]


class RegisteredNode(SevahModel):
    name: str
    optional: bool
    default_prompt: str


NODE_REGISTRY: Mapping[str, RegisteredNode] = MappingProxyType(
    {
        "positioning": RegisteredNode(
            name="positioning",
            optional=False,
            default_prompt="Summarize the facility evidence without adding claims.",
        ),
        "technology_research": RegisteredNode(
            name="technology_research",
            optional=True,
            default_prompt=DEFAULT_TECHNOLOGY_RESEARCH_PROMPT,
        ),
        "scope": RegisteredNode(
            name="scope",
            optional=False,
            default_prompt="Apply approved service corrections.",
        ),
        "scoring": RegisteredNode(
            name="scoring",
            optional=False,
            default_prompt="Apply the deterministic affinity scoring rules.",
        ),
    }
)


class GraphSpec(SevahModel):
    enabled_nodes: frozenset[str] = frozenset(
        {"positioning", "scope", "scoring"}
    )
    prompt_overrides: dict[str, PromptText] = Field(default_factory=dict)
    revision: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_registry_membership(self) -> "GraphSpec":
        unknown_nodes = self.enabled_nodes - NODE_REGISTRY.keys()
        if unknown_nodes:
            raise ValueError(f"Unknown enabled nodes: {sorted(unknown_nodes)}")
        required_nodes = {
            name for name, registration in NODE_REGISTRY.items()
            if not registration.optional
        }
        missing_nodes = required_nodes - self.enabled_nodes
        if missing_nodes:
            raise ValueError(f"Required nodes cannot be disabled: {sorted(missing_nodes)}")
        unknown_prompts = self.prompt_overrides.keys() - NODE_REGISTRY.keys()
        if unknown_prompts:
            raise ValueError(f"Unknown prompt nodes: {sorted(unknown_prompts)}")
        return self


class ScoreOverride(SevahModel):
    score: int = Field(ge=0, le=100)
    reason: str = Field(min_length=1, max_length=1_000)


class FeedbackOverrides(SevahModel):
    approved_facilities: frozenset[str] = frozenset()
    service_corrections: dict[str, dict[str, bool]] = Field(default_factory=dict)
    score_overrides: dict[str, ScoreOverride] = Field(default_factory=dict)


class WorkflowEvaluationConfig(SevahModel):
    graph_spec: GraphSpec = Field(default_factory=GraphSpec)
    feedback: FeedbackOverrides = Field(default_factory=FeedbackOverrides)


class ApproveResultFeedback(SevahModel):
    action: Literal["approve_result"]
    facility_id: str = Field(min_length=1)


class CorrectServiceFeedback(SevahModel):
    action: Literal["correct_service"]
    facility_id: str = Field(min_length=1)
    service: str
    present: bool

    @field_validator("service")
    @classmethod
    def service_must_be_registered(cls, value: str) -> str:
        if value not in SERVICE_PATTERNS:
            raise ValueError(f"Unknown service: {value}")
        return value


class AdjustAffinityScoreFeedback(SevahModel):
    action: Literal["adjust_affinity_score"]
    facility_id: str = Field(min_length=1)
    score: int = Field(ge=0, le=100)
    reason: str = Field(min_length=1, max_length=1_000)


class UpdateNodePromptFeedback(SevahModel):
    action: Literal["update_node_prompt"]
    node_name: str
    prompt: PromptText

    @field_validator("node_name")
    @classmethod
    def node_must_be_registered(cls, value: str) -> str:
        if value not in NODE_REGISTRY:
            raise ValueError(f"Unknown node: {value}")
        return value


class EnableNodeFeedback(SevahModel):
    action: Literal["enable_node"]
    node_name: str

    @field_validator("node_name")
    @classmethod
    def node_must_be_optional(cls, value: str) -> str:
        registration = NODE_REGISTRY.get(value)
        if registration is None or not registration.optional:
            raise ValueError(f"Node is not an optional registered node: {value}")
        return value


class EnableNodeWithPromptFeedback(SevahModel):
    action: Literal["enable_node_with_prompt"]
    node_name: str
    prompt: PromptText

    @field_validator("node_name")
    @classmethod
    def node_must_be_optional(cls, value: str) -> str:
        registration = NODE_REGISTRY.get(value)
        if registration is None or not registration.optional:
            raise ValueError(f"Node is not an optional registered node: {value}")
        return value


StructuredFeedback = (
    ApproveResultFeedback
    | CorrectServiceFeedback
    | AdjustAffinityScoreFeedback
    | UpdateNodePromptFeedback
    | EnableNodeFeedback
    | EnableNodeWithPromptFeedback
)
STRUCTURED_FEEDBACK_ADAPTER = TypeAdapter(StructuredFeedback)


class EvaluationInput(SevahModel):
    facility_id: str = Field(min_length=1)
    services: tuple[str, ...]
    affinity_score: int = Field(ge=0, le=100)
    facility_website: str | None = None
    baseline_technology_signals: tuple[str, ...] = ()

    @field_validator("services")
    @classmethod
    def services_must_be_registered(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        unknown = set(values) - SERVICE_PATTERNS.keys()
        if unknown:
            raise ValueError(f"Unknown services: {sorted(unknown)}")
        return values

    @field_validator("baseline_technology_signals")
    @classmethod
    def technology_signals_must_be_registered(
        cls,
        values: tuple[str, ...],
    ) -> tuple[str, ...]:
        unknown = set(values) - TECHNOLOGY_PATTERNS.keys()
        if unknown:
            raise ValueError(f"Unknown technology signals: {sorted(unknown)}")
        return values


def _not_run_technology_research() -> TechnologyResearchResult:
    return TechnologyResearchResult(
        status="not_run",
        effective_prompt="Technology research was not enabled.",
        notice="Enable the registered technology_research node to run research.",
    )


class EvaluationResult(SevahModel):
    facility_id: str
    services: tuple[str, ...]
    affinity_score: int = Field(ge=0, le=100)
    approved: bool
    executed_nodes: tuple[str, ...]
    effective_prompts: dict[str, str]
    graph_revision: int
    service_score_delta: int = Field(default=0, ge=-40, le=40)
    technology_research: TechnologyResearchResult = Field(
        default_factory=_not_run_technology_research
    )
    technology_score_delta: int = Field(default=0, ge=0, le=35)


class EvaluationState(TypedDict, total=False):
    facility_id: str
    services: tuple[str, ...]
    affinity_score: int
    approved: bool
    executed_nodes: tuple[str, ...]
    effective_prompts: dict[str, str]
    graph_revision: int
    service_score_delta: int
    facility_website: str | None
    baseline_technology_signals: tuple[str, ...]
    technology_research: dict[str, object]
    technology_score_delta: int


class RebuiltEvaluation(NamedTuple):
    config: WorkflowEvaluationConfig
    graph: object


def build_evaluation_graph(
    config: WorkflowEvaluationConfig,
    *,
    technology_researcher: Callable[..., TechnologyResearchResult] | None = None,
):
    """Build only allowlisted nodes and predetermined legal edges."""

    spec = config.graph_spec

    def mark_node(name: str, state: EvaluationState) -> EvaluationState:
        prompt = spec.prompt_overrides.get(
            name,
            NODE_REGISTRY[name].default_prompt,
        )
        return {
            "executed_nodes": (*state.get("executed_nodes", ()), name),
            "effective_prompts": {
                **state.get("effective_prompts", {}),
                name: prompt,
            },
        }

    def positioning(state: EvaluationState) -> EvaluationState:
        return mark_node("positioning", state)

    def technology_research(state: EvaluationState) -> EvaluationState:
        result = mark_node("technology_research", state)
        research = (technology_researcher or research_facility_technology)(
            state.get("facility_website"),
            state.get("baseline_technology_signals", ()),
            effective_prompt=result["effective_prompts"]["technology_research"],
        )
        baseline = set(state.get("baseline_technology_signals", ()))
        combined = baseline | set(research.signals)
        baseline_points = min(
            sum(TECHNOLOGY_WEIGHTS[signal] for signal in baseline),
            35,
        )
        combined_points = min(
            sum(TECHNOLOGY_WEIGHTS[signal] for signal in combined),
            35,
        )
        result["technology_research"] = research.model_dump(mode="json")
        result["technology_score_delta"] = combined_points - baseline_points
        return result

    def scope(state: EvaluationState) -> EvaluationState:
        result = mark_node("scope", state)
        original_services = set(state["services"])
        services = set(original_services)
        for service, present in config.feedback.service_corrections.get(
            state["facility_id"],
            {},
        ).items():
            services.add(service) if present else services.discard(service)
        result["services"] = tuple(sorted(services))
        original_points = min(
            sum(SERVICE_WEIGHTS[service] for service in original_services),
            40,
        )
        corrected_points = min(
            sum(SERVICE_WEIGHTS[service] for service in services),
            40,
        )
        result["service_score_delta"] = corrected_points - original_points
        return result

    def scoring(state: EvaluationState) -> EvaluationState:
        result = mark_node("scoring", state)
        override = config.feedback.score_overrides.get(state["facility_id"])
        result["affinity_score"] = (
            override.score
            if override
            else max(
                0,
                min(
                    100,
                    (
                        state["affinity_score"]
                        + state.get("service_score_delta", 0)
                        + state.get("technology_score_delta", 0)
                    ),
                ),
            )
        )
        result["approved"] = (
            state["facility_id"] in config.feedback.approved_facilities
        )
        return result

    builder = StateGraph(EvaluationState)
    builder.add_node("positioning", positioning)
    if "technology_research" in spec.enabled_nodes:
        builder.add_node("technology_research", technology_research)
    builder.add_node("scope", scope)
    builder.add_node("scoring", scoring)
    builder.add_edge(START, "positioning")
    if "technology_research" in spec.enabled_nodes:
        builder.add_edge("positioning", "technology_research")
        builder.add_edge("technology_research", "scope")
    else:
        builder.add_edge("positioning", "scope")
    builder.add_edge("scope", "scoring")
    builder.add_edge("scoring", END)
    return builder.compile()


def apply_feedback(
    config: WorkflowEvaluationConfig,
    feedback: StructuredFeedback | Mapping[str, object],
) -> RebuiltEvaluation:
    """Apply validated feedback, increment revision, and rebuild for the next run."""

    if isinstance(feedback, Mapping):
        feedback = STRUCTURED_FEEDBACK_ADAPTER.validate_python(feedback)
    spec = config.graph_spec
    overrides = config.feedback
    if isinstance(feedback, ApproveResultFeedback):
        overrides = overrides.model_copy(
            update={
                "approved_facilities": (
                    overrides.approved_facilities | {feedback.facility_id}
                )
            }
        )
    elif isinstance(feedback, CorrectServiceFeedback):
        corrections = {
            facility_id: dict(values)
            for facility_id, values in overrides.service_corrections.items()
        }
        corrections.setdefault(feedback.facility_id, {})[feedback.service] = (
            feedback.present
        )
        overrides = overrides.model_copy(update={"service_corrections": corrections})
    elif isinstance(feedback, AdjustAffinityScoreFeedback):
        score_overrides = dict(overrides.score_overrides)
        score_overrides[feedback.facility_id] = ScoreOverride(
            score=feedback.score,
            reason=feedback.reason,
        )
        overrides = overrides.model_copy(update={"score_overrides": score_overrides})
    elif isinstance(feedback, UpdateNodePromptFeedback):
        prompts = dict(spec.prompt_overrides)
        prompts[feedback.node_name] = feedback.prompt
        spec = spec.model_copy(update={"prompt_overrides": prompts})
    elif isinstance(feedback, EnableNodeFeedback):
        spec = spec.model_copy(
            update={"enabled_nodes": spec.enabled_nodes | {feedback.node_name}}
        )
    elif isinstance(feedback, EnableNodeWithPromptFeedback):
        prompts = dict(spec.prompt_overrides)
        prompts[feedback.node_name] = feedback.prompt
        spec = spec.model_copy(
            update={
                "enabled_nodes": spec.enabled_nodes | {feedback.node_name},
                "prompt_overrides": prompts,
            }
        )

    spec = GraphSpec.model_validate(
        {
            **spec.model_dump(),
            "revision": spec.revision + 1,
        }
    )
    updated = WorkflowEvaluationConfig(
        graph_spec=spec,
        feedback=overrides,
    )
    return RebuiltEvaluation(updated, build_evaluation_graph(updated))


def run_evaluation(
    graph,
    evaluation_input: EvaluationInput,
    *,
    graph_revision: int,
) -> EvaluationResult:
    """Execute a previously built safe evaluation graph."""

    state = graph.invoke(
        {
            **evaluation_input.model_dump(mode="json"),
            "executed_nodes": (),
            "effective_prompts": {},
            "graph_revision": graph_revision,
        }
    )
    return EvaluationResult.model_validate(
        {
            name: value
            for name, value in state.items()
            if name in EvaluationResult.model_fields
        }
    )
