"""Deterministic facility analysis workflow with human review."""

from enum import Enum
from functools import lru_cache
from typing import TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from pydantic import Field

from sevah.affinity_models import RoboticsAffinityAssessment
from sevah.cms_enrichment import enrich_discovery_result_with_cms
from sevah.cms_models import CmsEnrichmentBatch
from sevah.discovery import discover_facilities
from sevah.models import DiscoveryResult, SevahModel, ZipCodeQuery
from sevah.robotics_affinity import analyze_facilities_robotics_affinity


class ReviewDecision(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"


class ReviewStatus(str, Enum):
    AWAITING_REVIEW = "awaiting_review"
    APPROVED = "approved"
    REJECTED = "rejected"


class HumanReviewDecision(SevahModel):
    decision: ReviewDecision
    note: str | None = Field(default=None, max_length=2_000)


class ReviewItem(SevahModel):
    facility_id: str
    facility_name: str
    score: int
    confidence: int
    components: dict[str, int]
    reasons: tuple[str, ...]


class ReviewRequest(SevahModel):
    zip_code: str
    allowed_decisions: tuple[ReviewDecision, ...]
    facilities: tuple[ReviewItem, ...]


class ReviewWorkflowResult(SevahModel):
    thread_id: str
    status: ReviewStatus
    discovery: DiscoveryResult
    cms_enrichment: CmsEnrichmentBatch
    review_request: ReviewRequest | None = None
    decision: HumanReviewDecision | None = None
    assessments: tuple[RoboticsAffinityAssessment, ...] = ()


class ReviewWorkflowState(TypedDict, total=False):
    zip_code: str
    discovery: dict[str, object]
    cms_enrichment: dict[str, object]
    assessments: tuple[dict[str, object], ...]
    decision: dict[str, object]
    status: str


_CHECKPOINTER = InMemorySaver()


def _discover(state: ReviewWorkflowState) -> ReviewWorkflowState:
    result = discover_facilities(state["zip_code"])
    return {"discovery": result.model_dump(mode="json")}


def _enrich(state: ReviewWorkflowState) -> ReviewWorkflowState:
    discovery = DiscoveryResult.model_validate(state["discovery"])
    result = enrich_discovery_result_with_cms(discovery)
    return {"cms_enrichment": result.model_dump(mode="json")}


def _score(state: ReviewWorkflowState) -> ReviewWorkflowState:
    discovery = DiscoveryResult.model_validate(state["discovery"])
    cms_enrichment = CmsEnrichmentBatch.model_validate(state["cms_enrichment"])
    assessments = analyze_facilities_robotics_affinity(
        (item.facility for item in discovery.facilities),
        cms_batch=cms_enrichment,
    )
    return {
        "assessments": tuple(
            assessment.model_dump(mode="json") for assessment in assessments
        )
    }


def _review(state: ReviewWorkflowState) -> ReviewWorkflowState:
    discovery = DiscoveryResult.model_validate(state["discovery"])
    assessments = tuple(
        RoboticsAffinityAssessment.model_validate(assessment)
        for assessment in state["assessments"]
    )
    names = {
        item.facility.facility_id: item.facility.name
        for item in discovery.facilities
    }
    request = ReviewRequest(
        zip_code=state["zip_code"],
        allowed_decisions=(ReviewDecision.APPROVE, ReviewDecision.REJECT),
        facilities=tuple(
            ReviewItem(
                facility_id=assessment.facility_id,
                facility_name=names[assessment.facility_id],
                score=assessment.score,
                confidence=assessment.confidence,
                components=assessment.components.model_dump(),
                reasons=tuple(reason.reason for reason in assessment.reasons),
            )
            for assessment in assessments
        ),
    )
    response = interrupt(request.model_dump(mode="json"))
    decision = HumanReviewDecision.model_validate(response)
    return {"decision": decision.model_dump(mode="json")}


def _finalize(state: ReviewWorkflowState) -> ReviewWorkflowState:
    decision = HumanReviewDecision.model_validate(state["decision"])
    status = (
        ReviewStatus.APPROVED
        if decision.decision is ReviewDecision.APPROVE
        else ReviewStatus.REJECTED
    )
    return {"status": status.value}


@lru_cache(maxsize=1)
def _graph():
    builder = StateGraph(ReviewWorkflowState)
    builder.add_node("discover", _discover)
    builder.add_node("enrich", _enrich)
    builder.add_node("score", _score)
    builder.add_node("review", _review)
    builder.add_node("finalize", _finalize)
    builder.add_edge(START, "discover")
    builder.add_edge("discover", "enrich")
    builder.add_edge("enrich", "score")
    builder.add_edge("score", "review")
    builder.add_edge("review", "finalize")
    builder.add_edge("finalize", END)
    return builder.compile(checkpointer=_CHECKPOINTER)


def start_review_workflow(zip_code: str, thread_id: str) -> ReviewWorkflowResult:
    """Run deterministic analysis until human review is required."""

    validated_zip = ZipCodeQuery(zip_code=zip_code).zip_code
    return _invoke(
        {"zip_code": validated_zip},
        thread_id=thread_id,
    )


def resume_review_workflow(
    thread_id: str,
    decision: HumanReviewDecision,
) -> ReviewWorkflowResult:
    """Resume a paused workflow with a validated human decision."""

    return _invoke(
        Command(resume=decision.model_dump(mode="json")),
        thread_id=thread_id,
    )


def _invoke(input_value, *, thread_id: str) -> ReviewWorkflowResult:
    if not thread_id.strip():
        raise ValueError("thread_id is required.")
    state = _graph().invoke(
        input_value,
        config={"configurable": {"thread_id": thread_id}},
    )
    interrupts = state.get("__interrupt__", ())
    discovery = DiscoveryResult.model_validate(state["discovery"])
    cms_enrichment = CmsEnrichmentBatch.model_validate(state["cms_enrichment"])
    assessments = tuple(
        RoboticsAffinityAssessment.model_validate(assessment)
        for assessment in state["assessments"]
    )
    if interrupts:
        return ReviewWorkflowResult(
            thread_id=thread_id,
            status=ReviewStatus.AWAITING_REVIEW,
            discovery=discovery,
            cms_enrichment=cms_enrichment,
            review_request=ReviewRequest.model_validate(interrupts[0].value),
            assessments=assessments,
        )
    return ReviewWorkflowResult(
        thread_id=thread_id,
        status=state["status"],
        discovery=discovery,
        cms_enrichment=cms_enrichment,
        decision=HumanReviewDecision.model_validate(state["decision"]),
        assessments=assessments,
    )
