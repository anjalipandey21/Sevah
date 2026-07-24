"""Streamlit UI for discovery, enrichment, scoring, and human review."""

from uuid import uuid4

import streamlit as st
from dotenv import load_dotenv
from pydantic import ValidationError

from sevah.cms_models import AcoAffiliationStatus, OwnershipDataSource
from sevah.models import DataSource
from sevah.review_workflow import (
    HumanReviewDecision,
    ReviewDecision,
    ReviewStatus,
    ReviewWorkflowResult,
    resume_review_workflow,
    start_review_workflow,
)
from sevah.safe_feedback import (
    NODE_REGISTRY,
    EvaluationInput,
    EvaluationResult,
    WorkflowEvaluationConfig,
    apply_feedback,
    build_evaluation_graph,
    run_evaluation,
)
from sevah.service_marketing import SERVICE_PATTERNS
from sevah.services.technology_research import (
    DEFAULT_TECHNOLOGY_RESEARCH_PROMPT,
)
from sevah.services.zip_codes import UnknownZipCodeError


def render_app() -> None:
    """Render the complete Sevah workflow."""

    load_dotenv()
    st.set_page_config(
        page_title="Sevah",
        page_icon=":material/health_and_safety:",
        layout="wide",
    )
    _initialize_state()

    st.title("Facility robotics-affinity review")
    st.caption(
        "Discover nearby facilities, inspect CMS and website evidence, and review "
        "the deterministic affinity assessment."
    )
    st.warning(
        "CMS-certified nursing homes are an MVP proxy for assisted-living "
        "facilities. A missing CMS match is expected for many facilities.",
        icon=":material/info:",
    )

    with st.form("facility-search", border=False):
        with st.container(horizontal=True, vertical_alignment="bottom"):
            zip_code = st.text_input(
                "Five-digit US ZIP code",
                max_chars=5,
                placeholder="60614",
                key="zip_code",
            )
            submitted = st.form_submit_button(
                "Run analysis",
                type="primary",
                icon=":material/search:",
            )

    if submitted:
        _start_analysis(zip_code)

    run: ReviewWorkflowResult | None = st.session_state.review_run
    if run is None:
        st.info(
            "Enter a ZIP code to begin the deterministic workflow.",
            icon=":material/location_on:",
        )
        return

    _render_source(run)
    _render_summary(run)
    evaluations = _render_facilities(run)
    _render_feedback(run, evaluations)
    _render_review(run)


def _initialize_state() -> None:
    st.session_state.setdefault("review_run", None)
    st.session_state.setdefault(
        "evaluation_config",
        WorkflowEvaluationConfig(),
    )


def _start_analysis(zip_code: str) -> None:
    try:
        with st.status(
            "Running discovery and deterministic evaluation…",
            expanded=False,
        ) as status:
            run = start_review_workflow(zip_code, str(uuid4()))
            status.update(
                label="Analysis ready for review",
                state="complete",
            )
        st.session_state.review_run = run
        st.session_state.pop("feedback_action", None)
    except ValidationError:
        st.error("Enter exactly five digits.", icon=":material/error:")
    except UnknownZipCodeError:
        st.error(
            "That ZIP code could not be located.",
            icon=":material/error:",
        )
    except Exception:
        st.error(
            "The analysis could not be completed. Try again.",
            icon=":material/error:",
        )


def _render_source(run: ReviewWorkflowResult) -> None:
    if run.discovery.source is DataSource.LIVE:
        st.success(
            "Facility source: live Google Places data.",
            icon=":material/cloud_done:",
        )
    else:
        st.warning(
            f"Facility source: Bundled sample data. {run.discovery.notice}",
            icon=":material/science:",
        )


def _render_summary(run: ReviewWorkflowResult) -> None:
    config: WorkflowEvaluationConfig = st.session_state.evaluation_config
    metrics = st.columns(4)
    metrics[0].metric("Facilities", len(run.discovery.facilities))
    metrics[1].metric(
        "CMS matches",
        sum(item.matched for item in run.cms_enrichment.enrichments),
    )
    metrics[2].metric("Review status", run.status.value.replace("_", " ").title())
    metrics[3].metric("Graph revision", config.graph_spec.revision)


def _render_facilities(
    run: ReviewWorkflowResult,
) -> dict[str, EvaluationResult]:
    st.header("Facility assessments")
    cms_by_id = {
        item.facility_id: item for item in run.cms_enrichment.enrichments
    }
    assessment_by_id = {
        item.facility_id: item for item in run.assessments
    }
    config: WorkflowEvaluationConfig = st.session_state.evaluation_config
    evaluation_graph = build_evaluation_graph(config)
    evaluations: dict[str, EvaluationResult] = {}

    for position, distance_result in enumerate(run.discovery.facilities, start=1):
        facility = distance_result.facility
        assessment = assessment_by_id[facility.facility_id]
        cms = cms_by_id.get(facility.facility_id)
        evaluated = run_evaluation(
            evaluation_graph,
            EvaluationInput(
                facility_id=facility.facility_id,
                services=assessment.extraction.services,
                affinity_score=assessment.score,
                facility_website=facility.website,
                baseline_technology_signals=(
                    assessment.extraction.technology_signals
                ),
            ),
            graph_revision=config.graph_spec.revision,
        )
        evaluations[facility.facility_id] = evaluated

        with st.container(border=True):
            st.subheader(f"{position}. {facility.name}")
            st.write(facility.address)
            metadata = st.columns(4)
            metadata[0].metric(
                "Distance",
                f"{distance_result.distance_miles:.1f} mi",
            )
            metadata[1].metric(
                "Affinity",
                f"{evaluated.affinity_score}/100",
            )
            metadata[2].metric(
                "Confidence",
                f"{assessment.confidence}/100",
            )
            metadata[3].metric(
                "Google rating",
                f"{facility.rating:.1f}" if facility.rating is not None else "N/A",
            )
            st.progress(
                evaluated.affinity_score / 100,
                text="Deterministic robotics-affinity score",
            )
            st.info(
                _decision_summary(assessment, evaluated),
                icon=":material/summarize:",
            )

            if evaluated.affinity_score != assessment.score:
                st.caption(
                    f"Reviewer-adjusted from {assessment.score} to "
                    f"{evaluated.affinity_score}."
                )
            if evaluated.service_score_delta:
                st.caption(
                    f"Service corrections contributed "
                    f"{evaluated.service_score_delta:+d} points."
                )
            if evaluated.approved:
                st.success(
                    "This facility result has structured reviewer approval.",
                    icon=":material/verified:",
                )

            with st.expander(
                "Evidence and score reasons",
                icon=":material/fact_check:",
            ):
                st.write(
                    {
                        "Service fit": assessment.components.service_fit,
                        "Technology readiness": (
                            assessment.components.technology_readiness
                        ),
                        "Operating scale": assessment.components.operating_scale,
                        "Innovation marketing": (
                            assessment.components.innovation_marketing
                        ),
                    }
                )
                for reason in assessment.reasons:
                    st.write(f"**{reason.category.replace('_', ' ').title()}:** "
                             f"{reason.reason} (+{reason.points})")
                st.caption(assessment.limitation)

            if evaluated.technology_research.status != "not_run":
                with st.expander(
                    "Technology research evidence",
                    icon=":material/biotech:",
                ):
                    research = evaluated.technology_research
                    st.write(f"Status: **{research.status.replace('_', ' ')}**")
                    st.write(
                        f"Technology score impact: "
                        f"**{evaluated.technology_score_delta:+d} points**"
                    )
                    st.caption(research.notice)
                    if research.evidence:
                        st.dataframe(
                            [
                                {
                                    "Signal": item.signal.replace("_", " "),
                                    "Matched term": item.matched_term,
                                    "Source URL": item.source_url,
                                }
                                for item in research.evidence
                            ],
                            hide_index=True,
                        )
                    else:
                        st.write("No additional supported technology signals found.")
                    st.write(
                        {
                            "Pages checked": research.pages_checked,
                            "Effective prompt": research.effective_prompt,
                        }
                    )

            with st.expander(
                "CMS and ownership details",
                icon=":material/database:",
            ):
                if cms and cms.matched:
                    st.write(
                        {
                            "CCN": cms.ccn,
                            "Certified beds": cms.bed_count,
                            "Overall rating": cms.overall_rating,
                            "Staffing rating": cms.staffing_rating,
                            "Ownership type": cms.ownership_type,
                            "Chain": cms.chain_name,
                            "Match score": cms.match_score,
                        }
                    )
                    if cms.management:
                        _render_management(cms.management)
                    aco = cms.aco_affiliation
                    st.divider()
                    st.write("**ACO affiliation**")
                    st.write(
                        {
                            "Status": aco.status.value,
                            "ACO ID": aco.aco_id,
                            "ACO name": aco.aco_name,
                            "SNF CCN": aco.snf_ccn,
                            "Match method": aco.match_method,
                            "Confidence": aco.confidence,
                            "Program year": aco.program_year,
                            "Track or model": aco.track_or_model,
                        }
                    )
                    if aco.status is AcoAffiliationStatus.CONFIRMED:
                        st.success(aco.notice, icon=":material/verified:")
                    elif aco.status is AcoAffiliationStatus.UNAVAILABLE:
                        st.warning(aco.notice, icon=":material/database_off:")
                    else:
                        st.caption(aco.notice)
                    st.link_button(
                        "Open CMS ACO source",
                        aco.source_url,
                        icon=":material/open_in_new:",
                    )
                else:
                    st.write("No reliable ZIP-scoped CMS name match.")
                    if cms:
                        st.caption(cms.aco_affiliation.notice)

            if facility.website:
                st.link_button(
                    "Visit facility website",
                    facility.website,
                    icon=":material/open_in_new:",
                )
    return evaluations


def _render_feedback(
    run: ReviewWorkflowResult,
    evaluations: dict[str, EvaluationResult],
) -> None:
    st.header("Safe Agent Harness")
    st.caption(
        "Feedback is validated against registered services and nodes, increments "
        "the graph revision, and applies to the next evaluation."
    )
    config: WorkflowEvaluationConfig = st.session_state.evaluation_config
    facilities = {
        item.facility.facility_id: item.facility.name
        for item in run.discovery.facilities
    }
    facility_actions = (
        "Approve result",
        "Correct service",
        "Adjust score",
    ) if facilities else ()
    action = st.segmented_control(
        "Feedback action",
        (
            *facility_actions,
            "Update node prompt",
            "Enable technology research",
        ),
        default=facility_actions[0] if facility_actions else "Update node prompt",
        key="feedback_action",
    )

    with st.form(f"feedback-{action}"):
        payload: dict[str, object]
        if action == "Update node prompt":
            node_name = st.selectbox("Registered node", tuple(NODE_REGISTRY))
            prompt = st.text_area(
                "Prompt override",
                value=NODE_REGISTRY[node_name].default_prompt,
                max_chars=4_000,
            )
            payload = {
                "action": "update_node_prompt",
                "node_name": node_name,
                "prompt": prompt,
            }
        elif action == "Enable technology research":
            st.write(
                "Next path: positioning → technology_research → scope → scoring"
            )
            prompt = st.text_area(
                "Technology research prompt",
                value=DEFAULT_TECHNOLOGY_RESEARCH_PROMPT,
                max_chars=4_000,
            )
            payload = {
                "action": "enable_node_with_prompt",
                "node_name": "technology_research",
                "prompt": prompt,
            }
        else:
            facility_id = st.selectbox(
                "Facility",
                tuple(facilities),
                format_func=facilities.get,
            )
            if action == "Correct service":
                service = st.selectbox(
                    "Registered service",
                    tuple(SERVICE_PATTERNS),
                    format_func=lambda value: value.replace("_", " ").title(),
                )
                correction = st.segmented_control(
                    "Correction",
                    ("Present", "Not present"),
                    default="Present",
                )
                payload = {
                    "action": "correct_service",
                    "facility_id": facility_id,
                    "service": service,
                    "present": correction == "Present",
                }
            elif action == "Adjust score":
                score = st.slider("Adjusted affinity score", 0, 100, 50)
                reason = st.text_area(
                    "Reason",
                    max_chars=1_000,
                    placeholder="State the evidence supporting this adjustment.",
                )
                payload = {
                    "action": "adjust_affinity_score",
                    "facility_id": facility_id,
                    "score": score,
                    "reason": reason,
                }
            else:
                payload = {
                    "action": "approve_result",
                    "facility_id": facility_id,
                }

        applied = st.form_submit_button(
            "Apply feedback",
            icon=":material/save:",
        )

    if applied:
        try:
            rebuilt = apply_feedback(config, payload)
            st.session_state.evaluation_config = rebuilt.config
            st.toast(
                f"Feedback applied at revision "
                f"{rebuilt.config.graph_spec.revision}.",
                icon=":material/check_circle:",
            )
            st.rerun()
        except ValidationError as exc:
            st.error(
                exc.errors()[0]["msg"],
                icon=":material/error:",
            )

    enabled = config.graph_spec.enabled_nodes
    path = ["positioning"]
    if "technology_research" in enabled:
        path.append("technology_research")
    path.extend(("scope", "scoring"))
    with st.expander(
        "Graph evolution",
        icon=":material/account_tree:",
    ):
        st.write(
            {
                "Revision": config.graph_spec.revision,
                "Enabled nodes": sorted(config.graph_spec.enabled_nodes),
                "Active path": " → ".join(path),
                "Prompt overrides": config.graph_spec.prompt_overrides,
            }
        )
        st.write("**Executed nodes for this facility**")
        for facility_id, evaluation in evaluations.items():
            facility_name = facilities.get(facility_id, facility_id)
            st.write(f"{facility_name}: {' → '.join(evaluation.executed_nodes)}")
        if "technology_research" in enabled:
            st.write("**Before:** positioning → scope → scoring")
            st.write(
                "**After:** positioning → technology_research → scope → scoring"
            )
    st.caption(f"Active evaluation path: {' → '.join(path)}")


def _render_management(management) -> None:
    if management.source is OwnershipDataSource.LIVE_CMS and management.records:
        st.caption(
            "Verified CMS ownership and management records. These records are "
            "not necessarily the facility's complete current executive leadership team."
        )
        st.dataframe(
            [
                {
                    "Name": record.owner_name,
                    "Role": record.role,
                    "Owner type": record.owner_type,
                    "Ownership percentage": record.ownership_percentage,
                    "Association date": record.association_date,
                }
                for record in management.records
            ],
            hide_index=True,
        )
        return
    st.write("No verified CMS ownership or management records were available.")
    if management.source is OwnershipDataSource.SAMPLE:
        st.warning(
            "Fictional sample management records are excluded from verified results.",
            icon=":material/science:",
        )
    st.caption(management.notice)


def _decision_summary(assessment, evaluated: EvaluationResult) -> str:
    strongest = max(
        assessment.components.model_dump().items(),
        key=lambda item: item[1],
    )
    adjustment = evaluated.affinity_score - assessment.score
    adjustment_text = (
        f" The Safe Agent Harness changed the result by {adjustment:+d} points."
        if adjustment
        else ""
    )
    return (
        f"Decision summary: {evaluated.affinity_score}/100 affinity with "
        f"{assessment.confidence}/100 evidence confidence. The strongest component "
        f"is {strongest[0].replace('_', ' ')} ({strongest[1]} points)."
        f"{adjustment_text}"
    )


def _render_review(run: ReviewWorkflowResult) -> None:
    st.header("Human review")
    if run.status is ReviewStatus.AWAITING_REVIEW:
        with st.form("human-review"):
            decision_label = st.segmented_control(
                "Decision",
                ("Approve", "Reject"),
                default="Approve",
            )
            note = st.text_area(
                "Reviewer note",
                max_chars=2_000,
                placeholder="Optional review context.",
            )
            submitted = st.form_submit_button(
                "Submit review",
                type="primary",
                icon=":material/how_to_reg:",
            )
        if submitted:
            decision = (
                ReviewDecision.APPROVE
                if decision_label == "Approve"
                else ReviewDecision.REJECT
            )
            try:
                st.session_state.review_run = resume_review_workflow(
                    run.thread_id,
                    HumanReviewDecision(
                        decision=decision,
                        note=note or None,
                    ),
                )
                st.rerun()
            except Exception:
                st.error(
                    "The review could not be resumed. Try again.",
                    icon=":material/error:",
                )
        return

    if run.status is ReviewStatus.APPROVED:
        st.success(
            "The workflow result was approved.",
            icon=":material/check_circle:",
        )
    else:
        st.warning(
            "The workflow result was rejected.",
            icon=":material/cancel:",
        )
    if run.decision and run.decision.note:
        st.caption(f"Reviewer note: {run.decision.note}")
