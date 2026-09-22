import re
import uuid
import logging
from typing import Dict, Any, List, Optional, Tuple, Set
from datetime import datetime, timezone
from langchain_core.messages import SystemMessage, HumanMessage

from app.agents.state import RFPProposalState
from app.agents.llm_factory import LLMFactory
from app.core.prompts import REVIEWER_AGENT_PROMPT
from app.core.config import settings
from app.models.schemas import ReviewReport, ReviewFinding, RubricScore
from app.agents.writer_agent import (
    UNSUPPORTED_COMMITMENT_PATTERNS,
    INVENTED_CLAIMS_PATTERNS,
    CRITICAL_CAPABILITY_TERMS,
    _validate_claim_evidence_grounding
)

logger = logging.getLogger(__name__)


def review_proposal_node(state: RFPProposalState) -> Dict[str, Any]:
    """
    Agent 6: Reviewer / Critic Agent
    Acts as the final quality gate for the generated proposal.
    Evaluates the current draft against:
    1. Extracted RFP metadata (Agent 1)
    2. Classified requirements (Agent 2)
    3. Compliance matrix (Agent 3)
    4. Risks & Clarifications (Agent 4)
    5. Company evidence & citations (Agent 3/5)
    6. Current proposal draft & version (Agent 5)

    Authoritative Precedence:
    Agent 2 -> Agent 3 -> Agent 4 -> Agent 5 -> Agent 6
    The Reviewer never mutates the compliance matrix and never invents company facts.
    """
    drafts = state.get("proposal_drafts", [])
    if not drafts:
        raise ValueError("No proposal draft available for review.")

    latest_draft = drafts[-1]
    current_version = latest_draft.get("version", state.get("current_version", 1))
    revision_count = max(state.get("revision_count", 0), max(0, current_version - 1))
    max_revisions = state.get("max_revisions", settings.MAX_REVISION_CYCLES)
    requirements = state.get("requirements", [])
    compliance_matrix = state.get("compliance_matrix", [])
    risks = state.get("risks", [])
    clarifications = state.get("clarification_questions", [])
    metadata = state.get("metadata") or {}

    # 1. Run deterministic review checks (authoritative safety gate)
    deterministic_report = _run_deterministic_review_checks(
        requirements=requirements,
        compliance_matrix=compliance_matrix,
        risks=risks,
        clarifications=clarifications,
        metadata=metadata,
        draft=latest_draft,
        version=current_version,
        revision_count=revision_count,
        max_revisions=max_revisions
    )

    # 2. Invoke LLM Reviewer if available (advisory qualitative feedback)
    llm = LLMFactory.get_chat_model()
    review_report: ReviewReport = deterministic_report

    if llm:
        try:
            prompt = (
                f"RFP Title: {metadata.get('title', 'Tender')}\n"
                f"Proposal Version: {current_version}\n"
                f"Revision Count: {revision_count} (Max: {max_revisions})\n"
                f"Classified Requirements Count: {len(requirements)}\n"
                f"Deterministic Findings Count: {len(deterministic_report.findings)} "
                f"(Critical: {len(deterministic_report.critical_findings)})\n\n"
                f"Proposal Markdown Content:\n{latest_draft.get('full_markdown', '')[:6000]}\n\n"
                f"Evaluate this proposal rigorously against the 4 rubric criteria and provide actionable feedback."
            )
            structured_reviewer = llm.with_structured_output(ReviewReport)
            llm_report: ReviewReport = structured_reviewer.invoke([
                SystemMessage(content=REVIEWER_AGENT_PROMPT),
                HumanMessage(content=prompt)
            ])
            review_report = _merge_review_reports(deterministic_report, llm_report)
        except Exception as e:
            logger.warning(f"[Agent 6: Reviewer] LLM evaluation error ({e}). Using deterministic review report.")
            review_report = deterministic_report

    # 3. Determine workflow routing and status
    should_revise = (review_report.overall_status == "REVISION_REQUIRED")
    new_revision_count = revision_count + 1 if should_revise else revision_count

    if review_report.overall_status == "REVISION_REQUIRED":
        next_status = "REVISING"
    elif review_report.overall_status == "HUMAN_REVIEW_REQUIRED":
        next_status = "HUMAN_REVIEW_REQUIRED"
    else:
        next_status = "AWAITING_FINAL_APPROVAL"

    log_entry = {
        "agent": "Reviewer / Critic Agent",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": (
            f"Evaluated Draft v{current_version} (Review {review_report.review_id}). "
            f"Score: {review_report.score}/100. Status: {review_report.overall_status}. "
            f"Findings: {len(review_report.findings)} (Critical: {len(review_report.critical_findings)}). "
            f"Revision Count: {new_revision_count}/{max_revisions}."
        )
    }

    return {
        "review_reports": state.get("review_reports", []) + [review_report.model_dump()],
        "revision_count": new_revision_count,
        "active_agent": "Reviewer / Critic Agent",
        "workflow_status": next_status,
        "logs": state.get("logs", []) + [log_entry]
    }


def _normalize_responses(draft: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Helper to convert requirement_responses into list of dicts."""
    raw = draft.get("requirement_responses", [])
    normalized = []
    for r in raw:
        if isinstance(r, dict):
            normalized.append(r)
        elif hasattr(r, "model_dump"):
            normalized.append(r.model_dump())
        elif hasattr(r, "__dict__"):
            normalized.append(r.__dict__)
        else:
            normalized.append(dict(r))
    return normalized


def _run_deterministic_review_checks(
    requirements: List[Dict[str, Any]],
    compliance_matrix: List[Dict[str, Any]],
    risks: List[Dict[str, Any]],
    clarifications: List[Dict[str, Any]],
    metadata: Dict[str, Any],
    draft: Dict[str, Any],
    version: int,
    revision_count: int,
    max_revisions: int
) -> ReviewReport:
    """
    Executes deterministic safety checks prior to advisory LLM grading.
    Guarantees that critical safety violations are never downgraded.
    """
    req_map = {r.get("req_code", f"REQ-{i}"): r for i, r in enumerate(requirements)}
    comp_map = {c.get("req_code", f"REQ-{i}"): c for i, c in enumerate(compliance_matrix)}
    risk_map = {rk.get("requirement_id"): rk for rk in risks if rk.get("requirement_id")}
    clarif_map = {cl.get("requirement_id"): cl for cl in clarifications if cl.get("requirement_id")}

    responses = _normalize_responses(draft)
    resp_map = {r.get("requirement_id"): r for r in responses if r.get("requirement_id")}

    findings: List[ReviewFinding] = []
    req_findings: Dict[str, List[ReviewFinding]] = {}
    critical_findings: List[ReviewFinding] = []
    missing_requirements: List[str] = []
    unsupported_claims: List[str] = []
    traceability_issues: List[str] = []
    risk_coverage_issues: List[str] = []
    clarification_issues: List[str] = []
    warnings: List[str] = []
    recommended_actions: List[str] = []

    def add_finding(
        severity: str,
        category: str,
        description: str,
        rec_action: str,
        req_id: Optional[str] = None,
        evidence: Optional[str] = None
    ):
        f = ReviewFinding(
            finding_id=f"fnd_{uuid.uuid4().hex[:8]}",
            requirement_id=req_id,
            severity=severity,
            category=category,
            description=description,
            evidence=evidence,
            recommended_action=rec_action
        )
        findings.append(f)
        if req_id:
            req_findings.setdefault(req_id, []).append(f)
        if severity == "CRITICAL":
            critical_findings.append(f)
        if rec_action not in recommended_actions:
            recommended_actions.append(rec_action)

    # --------------------------------------------------------------------------
    # 1. REQUIREMENT COVERAGE: Detect missing requirements
    # --------------------------------------------------------------------------
    for req_id, req in req_map.items():
        if req_id not in resp_map:
            is_mandatory = req.get("is_mandatory", False)
            missing_requirements.append(req_id)
            if is_mandatory:
                add_finding(
                    severity="CRITICAL",
                    category="REQUIREMENT_COVERAGE",
                    description=f"Mandatory requirement '{req_id}' is missing a proposal response.",
                    rec_action=f"Add an evidence-grounded response for mandatory requirement '{req_id}'.",
                    req_id=req_id
                )
            else:
                add_finding(
                    severity="HIGH",
                    category="REQUIREMENT_COVERAGE",
                    description=f"Optional requirement '{req_id}' is missing a proposal response.",
                    rec_action=f"Add a proposal response for optional requirement '{req_id}'.",
                    req_id=req_id
                )

    # --------------------------------------------------------------------------
    # 2. REQUIREMENT COVERAGE: Detect orphan responses
    # --------------------------------------------------------------------------
    for resp_id in resp_map:
        if resp_id not in req_map:
            add_finding(
                severity="HIGH",
                category="REQUIREMENT_COVERAGE",
                description=f"Proposal contains orphan response '{resp_id}' not found in RFP requirements.",
                rec_action=f"Remove orphan response '{resp_id}' or link it to a valid requirement.",
                req_id=resp_id
            )

    # --------------------------------------------------------------------------
    # 3. COMPLIANCE CONSISTENCY & GROUNDING
    # --------------------------------------------------------------------------
    for req_id, resp in resp_map.items():
        if req_id not in req_map:
            continue

        req = req_map[req_id]
        comp = comp_map.get(req_id, {})
        auth_status = comp.get("status", "INFORMATION_REQUIRED")
        resp_status = resp.get("compliance_status", "")
        resp_text = resp.get("response", "") or ""
        is_mandatory = req.get("is_mandatory", False)

        # A. Status mismatch check
        if resp_status != auth_status:
            if auth_status in ["NON_COMPLIANT", "INFORMATION_REQUIRED"] and resp_status == "COMPLIANT":
                add_finding(
                    severity="CRITICAL",
                    category="COMPLIANCE_CONSISTENCY",
                    description=(
                        f"Compliance status mismatch on {req_id}: proposal asserts '{resp_status}', "
                        f"but authoritative Agent 3 finding is '{auth_status}'."
                    ),
                    rec_action=f"Revert compliance status of {req_id} to authoritative '{auth_status}'.",
                    req_id=req_id,
                    evidence=f"Authoritative: {auth_status} vs Proposal: {resp_status}"
                )
            else:
                add_finding(
                    severity="HIGH",
                    category="COMPLIANCE_CONSISTENCY",
                    description=(
                        f"Compliance status mismatch on {req_id}: proposal has '{resp_status}', "
                        f"authoritative status is '{auth_status}'."
                    ),
                    rec_action=f"Align status with authoritative Agent 3 status '{auth_status}'.",
                    req_id=req_id
                )

        # B. Mandatory NON_COMPLIANT incorrectly written as compliant
        if auth_status == "NON_COMPLIANT":
            claims_support = bool(re.search(
                r'\b(?:we\s+(?:will\s+implement|support|can\s+provide)|fully\s+compliant|meets\s+the\s+requirement)\b',
                resp_text,
                re.IGNORECASE
            ))
            has_exception = bool(re.search(
                r'\b(?:exception|out\s+of\s+scope|variance|unsupported|not\s+(?:currently\s+)?supported|limitation)\b',
                resp_text,
                re.IGNORECASE
            ))
            if claims_support or not has_exception:
                sev = "CRITICAL" if is_mandatory else "HIGH"
                add_finding(
                    severity=sev,
                    category="COMPLIANCE_CONSISTENCY",
                    description=(
                        f"Requirement {req_id} is NON_COMPLIANT, but proposal response improperly promises "
                        f"compliance or omits the formal exception/variance disclosure."
                    ),
                    rec_action=f"State formal exception/variance for {req_id}; do not promise compliance.",
                    req_id=req_id,
                    evidence=resp_text[:200]
                )

        # C. Mandatory INFORMATION_REQUIRED represented as confirmed capability
        elif auth_status == "INFORMATION_REQUIRED":
            has_commitment = bool(UNSUPPORTED_COMMITMENT_PATTERNS.search(resp_text))
            has_invented = bool(INVENTED_CLAIMS_PATTERNS.search(resp_text))
            has_unconfirmed_marker = bool(re.search(
                r'\b(?:information\s+required|unconfirmed|requires?\s+(?:internal\s+)?confirmation|'
                r'pending\s+(?:verification|confirmation)|to\s+be\s+confirmed|confirmation\s+is\s+required|verify)\b',
                resp_text,
                re.IGNORECASE
            ))

            if has_commitment or has_invented:
                sev = "CRITICAL" if is_mandatory else "HIGH"
                claim_msg = f"Requirement {req_id} is INFORMATION_REQUIRED, but response asserts unconfirmed capability or certification."
                unsupported_claims.append(f"{req_id}: {claim_msg}")
                add_finding(
                    severity=sev,
                    category="UNGROUNDED_COMMITMENT",
                    description=claim_msg,
                    rec_action=f"Remove affirmative capability/certification claim on {req_id}; insert [INFORMATION REQUIRED] notice.",
                    req_id=req_id,
                    evidence=resp_text[:200]
                )
            elif not has_unconfirmed_marker:
                add_finding(
                    severity="HIGH",
                    category="COMPLIANCE_CONSISTENCY",
                    description=f"Requirement {req_id} is INFORMATION_REQUIRED, but response lacks required unconfirmed/verification notice.",
                    rec_action=f"Add explicit [INFORMATION REQUIRED] notice and internal verification request for {req_id}.",
                    req_id=req_id
                )

        # D. PARTIALLY_COMPLIANT response removing/hiding limitation
        elif auth_status == "PARTIALLY_COMPLIANT":
            claims_full = bool(re.search(
                r'\b(?:fully\s+compliant|complete\s+(?:24/7|support|compliance)|100%\s+compliant)\b',
                resp_text,
                re.IGNORECASE
            ))
            ev_full = (comp.get("evidence_text") or "") + " " + (comp.get("notes") or "")
            omits_hours = bool(
                re.search(r'\b(?:business\s+hours|office\s+hours|standard\s+hours)\b', ev_full, re.IGNORECASE) and
                not re.search(r'\b(?:business\s+hours|office\s+hours|standard\s+hours)\b', resp_text, re.IGNORECASE)
            )

            if claims_full:
                add_finding(
                    severity="HIGH",
                    category="COMPLIANCE_CONSISTENCY",
                    description=f"Requirement {req_id} is PARTIALLY_COMPLIANT, but response improperly claims complete compliance.",
                    rec_action=f"Disclose partial scope and documented limitations for {req_id}.",
                    req_id=req_id,
                    evidence=resp_text[:200]
                )
            elif omits_hours:
                add_finding(
                    severity="HIGH",
                    category="COMPLIANCE_CONSISTENCY",
                    description=f"Requirement {req_id} has a documented 'business hours' limitation in evidence that is omitted from response.",
                    rec_action=f"Include documented business hours limitation for {req_id}.",
                    req_id=req_id,
                    evidence=resp_text[:200]
                )

        # E. COMPLIANT response: Validate factual claim evidence grounding
        elif auth_status == "COMPLIANT":
            is_grounded, grounding_reason = _validate_claim_evidence_grounding(
                response_text=resp_text,
                status=auth_status,
                evidence_text=comp.get("evidence_text"),
                notes=comp.get("notes"),
                req_text=req.get("text", ""),
                citations=comp.get("citations", []),
                company_source_doc=comp.get("company_source_doc")
            )
            if not is_grounded:
                sev = "CRITICAL" if (is_mandatory or "critical technical capability" in grounding_reason.lower() or "certification" in grounding_reason.lower()) else "HIGH"
                unsupported_claims.append(f"{req_id}: {grounding_reason}")
                add_finding(
                    severity=sev,
                    category="EVIDENCE_GROUNDING",
                    description=f"Response for {req_id} contains ungrounded claims: {grounding_reason}",
                    rec_action=f"Ground response for {req_id} strictly in verified company evidence; eliminate ungrounded capabilities.",
                    req_id=req_id,
                    evidence=resp_text[:200]
                )

        # ----------------------------------------------------------------------
        # 4. TRACEABILITY CHECKS: Missing provenance for factual claims
        # ----------------------------------------------------------------------
        if auth_status in ["COMPLIANT", "PARTIALLY_COMPLIANT"]:
            doc_id = resp.get("company_doc_id")
            citations = resp.get("citations") or []
            evidence_snip = resp.get("evidence_snippet")

            if not doc_id and not citations and not evidence_snip:
                traceability_issues.append(f"{req_id}: Missing company document ID and citations")
                add_finding(
                    severity="HIGH",
                    category="TRACEABILITY",
                    description=f"Requirement {req_id} claims compliance but lacks company provenance metadata or citations.",
                    rec_action=f"Attach verified company document ID and chunk citations for {req_id}.",
                    req_id=req_id
                )

            src_page = resp.get("source_page")
            src_sec = resp.get("source_section")
            if src_page is None and not src_sec:
                traceability_issues.append(f"{req_id}: Missing RFP source page/section")
                add_finding(
                    severity="LOW",
                    category="TRACEABILITY",
                    description=f"Requirement {req_id} lacks source page/section traceability from RFP.",
                    rec_action=f"Populate source page and section for {req_id}.",
                    req_id=req_id
                )

        # ----------------------------------------------------------------------
        # 5. RISK & CLARIFICATION COVERAGE
        # ----------------------------------------------------------------------
        clarif = clarif_map.get(req_id)
        if clarif:
            c_type = clarif.get("clarification_type", "ISSUER_CLARIFICATION")
            if c_type == "ISSUER_CLARIFICATION" and auth_status in ["INFORMATION_REQUIRED", "NON_COMPLIANT"]:
                has_clarif_ref = bool(
                    resp.get("clarification_required") or
                    re.search(
                        r'\b(?:clarif\w*|question\w*|inquir\w*|issuer\w*|pending|confirm\w*|unconfirmed|exception\w*|variance\w*)\b',
                        resp_text,
                        re.IGNORECASE
                    )
                )
                if not has_clarif_ref:
                    clarification_issues.append(f"{req_id}: Unresolved issuer clarification presented as fact")
                    add_finding(
                        severity="HIGH",
                        category="CLARIFICATION_ISSUE",
                        description=f"Unresolved issuer clarification for {req_id} is presented as fact without referencing pending inquiry.",
                        rec_action=f"Qualify response for {req_id} by referencing outstanding clarification request.",
                        req_id=req_id
                    )

        risk = risk_map.get(req_id)
        if risk:
            r_sev = risk.get("severity", "MEDIUM")
            if r_sev in ["CRITICAL", "HIGH"] and auth_status == "NON_COMPLIANT":
                r_sum = resp.get("risk_summary")
                has_risk_ack = bool(
                    r_sum or
                    re.search(r'\b(?:risk\w*|exception\w*|mitigat\w*|limitation\w*|variance\w*)\b', resp_text, re.IGNORECASE)
                )
                if not has_risk_ack:
                    risk_coverage_issues.append(f"{req_id}: High/Critical risk omitted from proposal response")
                    add_finding(
                        severity="HIGH",
                        category="RISK_COVERAGE",
                        description=f"High/Critical tender risk for {req_id} ('{risk.get('title')}') is omitted from proposal response.",
                        rec_action=f"Acknowledge risk and attach mitigation strategy in proposal response for {req_id}.",
                        req_id=req_id
                    )

    # --------------------------------------------------------------------------
    # 6. UNRESOLVED INFORMATION REQUIRED ITEMS & DRAFT V1 REFINEMENT
    # --------------------------------------------------------------------------
    info_needed_count = len([c for c in comp_map.values() if c.get("status") == "INFORMATION_REQUIRED"])
    if info_needed_count > 0:
        warnings.append(f"{info_needed_count} requirements have unconfirmed company documentation ([INFORMATION REQUIRED]).")

    # Initial Draft v1 refinement directive:
    # An initial proposal draft containing unverified information items, risks, or open clarifications
    # requires at least one Red Team critique and revision cycle before final approval.
    if version == 1 and revision_count == 0 and (info_needed_count > 0 or len(risks) > 0 or len(clarifications) > 0):
        add_finding(
            severity="HIGH",
            category="PROPOSAL_QUALITY",
            description=(
                f"Initial Draft v1 requires red team revision to expand risk mitigations ({len(risks)} tender risks) "
                f"and detail verification registers for {info_needed_count} unverified requirements."
            ),
            rec_action="Incorporate red team revision directives, detailed risk mitigations, and verification registers in Draft v2."
        )

    # --------------------------------------------------------------------------
    # 7. SCORE & RUBRIC CALCULATION
    # --------------------------------------------------------------------------
    deduction_comp = 0
    deduction_grounding = 0
    deduction_feasibility = 0
    deduction_clarity = 0

    for f in findings:
        pts = 25 if f.severity == "CRITICAL" else (10 if f.severity == "HIGH" else (5 if f.severity == "MEDIUM" else 2))
        if f.category in ["COMPLIANCE_CONSISTENCY", "REQUIREMENT_COVERAGE"]:
            deduction_comp += pts
        elif f.category in ["EVIDENCE_GROUNDING", "UNGROUNDED_COMMITMENT"]:
            deduction_grounding += pts
        elif f.category in ["TRACEABILITY", "RISK_COVERAGE"]:
            deduction_feasibility += pts
        else:
            deduction_clarity += pts

    score_comp = max(0, 25 - deduction_comp)
    score_grounding = max(0, 25 - deduction_grounding)
    score_feasibility = max(0, 25 - deduction_feasibility)
    score_clarity = max(0, 25 - deduction_clarity)
    overall_score = score_comp + score_grounding + score_feasibility + score_clarity

    rubric = [
        RubricScore(criterion="Compliance Alignment", score=score_comp, feedback="Alignment with mandatory RFP requirements and Agent 3 verdicts."),
        RubricScore(criterion="Technical Depth & Feasibility", score=score_feasibility, feedback="Traceability, risk mitigation, and technical feasibility."),
        RubricScore(criterion="Grounding & Hallucination Defense", score=score_grounding, feedback="Strict evidence provenance and absence of ungrounded commitments."),
        RubricScore(criterion="Professionalism & Clarity", score=score_clarity, feedback="Clarity, structure, and proper [INFORMATION REQUIRED] formatting.")
    ]

    # --------------------------------------------------------------------------
    # 8. STATUS & REVISION DETERMINATION
    # --------------------------------------------------------------------------
    has_bid_blocking = any(
        r.get("is_bid_blocking") or r.get("severity") == "CRITICAL"
        for r in risks
    )
    has_critical_findings = len(critical_findings) > 0

    # Inherent deal-breakers cannot be resolved by rewriting alone
    is_unresolvable_deal_breaker = (
        has_bid_blocking or
        any(f.category == "REQUIREMENT_COVERAGE" for f in critical_findings) or
        any(
            comp_map.get(f.requirement_id, {}).get("status") == "NON_COMPLIANT" and
            req_map.get(f.requirement_id, {}).get("is_mandatory")
            for f in critical_findings if f.requirement_id
        )
    )

    if has_critical_findings or has_bid_blocking:
        if revision_count >= max_revisions or is_unresolvable_deal_breaker:
            overall_status = "HUMAN_REVIEW_REQUIRED"
            approval_required = True
            revision_required = False
        else:
            overall_status = "REVISION_REQUIRED"
            revision_required = True
            approval_required = True
    elif overall_score < settings.REVIEW_PASS_SCORE or any(f.severity == "HIGH" for f in findings):
        if revision_count < max_revisions:
            overall_status = "REVISION_REQUIRED"
            revision_required = True
            approval_required = False
        else:
            overall_status = "HUMAN_REVIEW_REQUIRED"
            approval_required = True
            revision_required = False
    else:
        overall_status = "APPROVED"
        approval_required = True
        revision_required = False

    critical_flaws = [f.description for f in critical_findings]
    summary_text = (
        f"Proposal Draft v{version} Review: Overall Score {overall_score}/100. Status: {overall_status}. "
        f"Findings: {len(findings)} total ({len(critical_findings)} critical, {len([f for f in findings if f.severity == 'HIGH'])} high). "
        f"{'Revisions recommended.' if revision_required else ('Human review required prior to final sign-off.' if approval_required and overall_status != 'APPROVED' else 'Proposal approved for final sign-off.')}"
    )

    return ReviewReport(
        review_id=f"rev_{uuid.uuid4().hex[:10]}",
        proposal_version=version,
        overall_status=overall_status,
        approval_required=approval_required,
        revision_required=revision_required,
        score=overall_score,
        summary=summary_text,
        findings=findings,
        requirement_findings=req_findings,
        critical_findings=critical_findings,
        warnings=warnings,
        missing_requirements=missing_requirements,
        unsupported_claims=unsupported_claims,
        traceability_issues=traceability_issues,
        risk_coverage_issues=risk_coverage_issues,
        clarification_issues=clarification_issues,
        recommended_actions=recommended_actions,
        reviewed_at=datetime.now(timezone.utc).isoformat(),
        # Backward compatibility fields
        overall_score=overall_score,
        rubric_scores=rubric,
        strengths=[
            "Compliance matrix directly references authoritative Agent 3 findings.",
            "Information items are properly distinguished from confirmed capabilities.",
            "Clear executive structure aligned with RFP evaluation framework."
        ] if overall_score >= 70 else [],
        critical_flaws=critical_flaws,
        ungrounded_or_hallucinated_claims=unsupported_claims,
        missing_information_count=info_needed_count,
        needs_revision=revision_required,
        actionable_revision_instructions=recommended_actions
    )


def _merge_review_reports(
    deterministic: ReviewReport,
    llm_report: ReviewReport
) -> ReviewReport:
    """
    Merges deterministic safety findings with LLM qualitative observations.
    Ensures that deterministic safety checks ALWAYS take precedence.
    """
    # Deterministic critical and high findings cannot be removed by LLM
    merged_findings = list(deterministic.findings)
    seen_descriptions = {f.description.lower() for f in merged_findings}

    # Append any unique qualitative findings from LLM
    for f in llm_report.findings:
        if f.description.lower() not in seen_descriptions:
            merged_findings.append(f)
            seen_descriptions.add(f.description.lower())

    # Score cannot exceed deterministic score if safety violations exist
    final_score = min(deterministic.score, llm_report.score) if deterministic.critical_findings else deterministic.score

    # Deterministic status takes precedence: LLM cannot downgrade a safety violation
    if deterministic.overall_status in ["HUMAN_REVIEW_REQUIRED", "REVISION_REQUIRED"]:
        final_status = deterministic.overall_status
        approval_req = deterministic.approval_required
        rev_req = deterministic.revision_required
    else:
        final_status = llm_report.overall_status
        approval_req = llm_report.approval_required
        rev_req = llm_report.revision_required

    # Combine recommendations without duplicates
    merged_recs = list(deterministic.recommended_actions)
    for r in llm_report.recommended_actions:
        if r not in merged_recs:
            merged_recs.append(r)

    # Combine strengths
    merged_strengths = list(deterministic.strengths)
    for s in llm_report.strengths:
        if s not in merged_strengths:
            merged_strengths.append(s)

    return ReviewReport(
        review_id=deterministic.review_id,
        proposal_version=deterministic.proposal_version,
        overall_status=final_status,
        approval_required=approval_req,
        revision_required=rev_req,
        score=final_score,
        summary=llm_report.summary or deterministic.summary,
        findings=merged_findings,
        requirement_findings=deterministic.requirement_findings,
        critical_findings=deterministic.critical_findings,
        warnings=list(set(deterministic.warnings + llm_report.warnings)),
        missing_requirements=deterministic.missing_requirements,
        unsupported_claims=list(set(deterministic.unsupported_claims + llm_report.unsupported_claims)),
        traceability_issues=deterministic.traceability_issues,
        risk_coverage_issues=deterministic.risk_coverage_issues,
        clarification_issues=deterministic.clarification_issues,
        recommended_actions=merged_recs,
        reviewed_at=deterministic.reviewed_at,
        overall_score=final_score,
        rubric_scores=deterministic.rubric_scores,
        strengths=merged_strengths,
        critical_flaws=deterministic.critical_flaws,
        ungrounded_or_hallucinated_claims=deterministic.ungrounded_or_hallucinated_claims,
        missing_information_count=deterministic.missing_information_count,
        needs_revision=rev_req,
        actionable_revision_instructions=merged_recs
    )

