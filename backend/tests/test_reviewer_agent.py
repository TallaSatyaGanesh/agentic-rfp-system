import pytest
import copy
from typing import Dict, Any, List
from app.agents.reviewer_agent import (
    review_proposal_node,
    _run_deterministic_review_checks
)
from app.agents.writer_agent import write_proposal_node
from app.agents.graph import route_review_outcome
from app.agents.state import RFPProposalState
from app.models.schemas import (
    ProposalDraft,
    RequirementResponse,
    ReviewReport,
    ReviewFinding
)


# ==============================================================================
# Helper to build a standard compliant proposal draft
# ==============================================================================
def _build_test_draft(
    responses: List[RequirementResponse],
    version: int = 1,
    title: str = "Test Proposal Response"
) -> ProposalDraft:
    return ProposalDraft(
        version=version,
        title=f"{title} (v{version})",
        executive_summary="Executive summary for proposal testing.",
        sections=[],
        full_markdown="# Executive Summary\nTest content for proposal.",
        requirement_responses=responses
    )


# ==============================================================================
# TEST 1: Reviewer approves fully compliant grounded proposal
# ==============================================================================
def test_reviewer_approves_fully_compliant_grounded_proposal():
    reqs = [
        {
            "req_code": "REQ-01",
            "text": "The platform must support automated daily encrypted backups.",
            "category": "Technical",
            "is_mandatory": True,
            "source_page": 4,
            "source_section": "Storage"
        }
    ]
    comp = [
        {
            "req_code": "REQ-01",
            "status": "COMPLIANT",
            "evidence_text": "Platform performs automated daily encrypted backups retained for 30 days.",
            "company_source_doc": "Acme Backup Specification",
            "company_doc_id": "doc_backup_01",
            "chunk_id": "chk_01",
            "citations": [
                {
                    "document_title": "Acme Backup Specification",
                    "company_doc_id": "doc_backup_01",
                    "chunk_id": "chk_01",
                    "snippet": "Platform performs automated daily encrypted backups retained for 30 days."
                }
            ]
        }
    ]
    responses = [
        RequirementResponse(
            requirement_id="REQ-01",
            requirement_text="The platform must support automated daily encrypted backups.",
            category="Technical",
            is_mandatory=True,
            compliance_status="COMPLIANT",
            response_type="COMPLIANT_RESPONSE",
            response="The proposed solution fully supports this requirement based on verified company documentation. Specifically: Platform performs automated daily encrypted backups retained for 30 days. [Company: Acme Backup Specification]",
            company_doc_id="doc_backup_01",
            chunk_id="chk_01",
            source_page=4,
            source_section="Storage",
            evidence_snippet="Platform performs automated daily encrypted backups retained for 30 days.",
            citations=[
                {
                    "document_title": "Acme Backup Specification",
                    "company_doc_id": "doc_backup_01",
                    "chunk_id": "chk_01",
                    "snippet": "Platform performs automated daily encrypted backups retained for 30 days."
                }
            ]
        )
    ]

    draft = _build_test_draft(responses, version=1)

    state: RFPProposalState = {
        "metadata": {"title": "Test Cloud Modernization"},
        "requirements": reqs,
        "compliance_matrix": comp,
        "risks": [],
        "clarification_questions": [],
        "proposal_drafts": [draft.model_dump()],
        "current_version": 1,
        "revision_count": 0,
        "max_revisions": 2
    }

    result = review_proposal_node(state)
    report = result["review_reports"][-1]

    assert report["overall_status"] == "APPROVED"
    assert report["score"] >= 80
    assert report["revision_required"] is False
    assert len(report["critical_findings"]) == 0
    assert len(report["missing_requirements"]) == 0
    assert len(report["unsupported_claims"]) == 0


# ==============================================================================
# TEST 2: Reviewer detects missing mandatory requirement
# ==============================================================================
def test_reviewer_detects_missing_mandatory_requirement():
    reqs = [
        {"req_code": "REQ-MAND-01", "text": "Mandatory security policy.", "is_mandatory": True, "category": "Security"},
        {"req_code": "REQ-OPT-02", "text": "Optional dark mode.", "is_mandatory": False, "category": "UI"}
    ]
    comp = [
        {"req_code": "REQ-MAND-01", "status": "COMPLIANT", "evidence_text": "Security policy active."},
        {"req_code": "REQ-OPT-02", "status": "COMPLIANT", "evidence_text": "Dark mode active."}
    ]
    # Draft only responds to REQ-OPT-02, omitting REQ-MAND-01
    responses = [
        RequirementResponse(
            requirement_id="REQ-OPT-02",
            requirement_text="Optional dark mode.",
            category="UI",
            is_mandatory=False,
            compliance_status="COMPLIANT",
            response_type="COMPLIANT_RESPONSE",
            response="Dark mode is supported.",
            company_doc_id="doc_ui",
            citations=[{"snippet": "Dark mode supported"}]
        )
    ]
    draft = _build_test_draft(responses, version=1)
    state: RFPProposalState = {
        "metadata": {"title": "Tender"},
        "requirements": reqs,
        "compliance_matrix": comp,
        "risks": [],
        "clarification_questions": [],
        "proposal_drafts": [draft.model_dump()],
        "current_version": 1,
        "revision_count": 0,
        "max_revisions": 2
    }

    result = review_proposal_node(state)
    report = result["review_reports"][-1]

    assert report["overall_status"] != "APPROVED"
    assert "REQ-MAND-01" in report["missing_requirements"]
    crit_findings = [f for f in report["critical_findings"] if f["requirement_id"] == "REQ-MAND-01"]
    assert len(crit_findings) > 0
    assert crit_findings[0]["category"] == "REQUIREMENT_COVERAGE"


# ==============================================================================
# TEST 3: Reviewer detects compliance status mismatch
# ==============================================================================
def test_reviewer_detects_compliance_status_mismatch():
    reqs = [{"req_code": "REQ-01", "text": "Mainframe connectivity.", "is_mandatory": True, "category": "Arch"}]
    comp = [{"req_code": "REQ-01", "status": "NON_COMPLIANT", "evidence_text": "Mainframe terminal unsupported."}]
    # Proposal falsely claims COMPLIANT
    responses = [
        RequirementResponse(
            requirement_id="REQ-01",
            requirement_text="Mainframe connectivity.",
            category="Arch",
            is_mandatory=True,
            compliance_status="COMPLIANT",  # Status mismatch!
            response_type="COMPLIANT_RESPONSE",
            response="We support mainframe connectivity."
        )
    ]
    draft = _build_test_draft(responses, version=1)
    state: RFPProposalState = {
        "requirements": reqs,
        "compliance_matrix": comp,
        "risks": [],
        "clarification_questions": [],
        "proposal_drafts": [draft.model_dump()],
        "current_version": 1,
        "revision_count": 0,
        "max_revisions": 2
    }

    result = review_proposal_node(state)
    report = result["review_reports"][-1]

    assert report["overall_status"] != "APPROVED"
    mismatch_findings = [f for f in report["critical_findings"] if f["category"] == "COMPLIANCE_CONSISTENCY"]
    assert len(mismatch_findings) > 0
    assert "status mismatch" in mismatch_findings[0]["description"].lower()


# ==============================================================================
# TEST 4: Reviewer detects unsupported capability
# ==============================================================================
def test_reviewer_detects_unsupported_capability():
    reqs = [{"req_code": "REQ-01", "text": "Database backup system.", "is_mandatory": True, "category": "Tech"}]
    comp = [
        {
            "req_code": "REQ-01",
            "status": "COMPLIANT",
            "evidence_text": "Company provides automated daily database backups.",
            "company_source_doc": "Backup Collateral"
        }
    ]
    # Response introduces ungrounded cross-region disaster recovery
    responses = [
        RequirementResponse(
            requirement_id="REQ-01",
            requirement_text="Database backup system.",
            category="Tech",
            is_mandatory=True,
            compliance_status="COMPLIANT",
            response_type="COMPLIANT_RESPONSE",
            response="Our platform provides automated cross-region disaster recovery for all systems.",
            company_doc_id="doc_bk",
            citations=[{"snippet": "daily database backups"}]
        )
    ]
    draft = _build_test_draft(responses, version=1)
    state: RFPProposalState = {
        "requirements": reqs,
        "compliance_matrix": comp,
        "risks": [],
        "clarification_questions": [],
        "proposal_drafts": [draft.model_dump()],
        "current_version": 1,
        "revision_count": 0,
        "max_revisions": 2
    }

    result = review_proposal_node(state)
    report = result["review_reports"][-1]

    assert report["overall_status"] != "APPROVED"
    grounding_findings = [f for f in report["findings"] if f["category"] == "EVIDENCE_GROUNDING"]
    assert len(grounding_findings) > 0
    assert any(term in grounding_findings[0]["description"].lower() for term in ["recovery", "disaster", "cross-region"])


# ==============================================================================
# TEST 5: Reviewer detects unsupported certification
# ==============================================================================
def test_reviewer_detects_unsupported_certification():
    reqs = [{"req_code": "REQ-CERT", "text": "Must hold ISO 27001 certification.", "is_mandatory": True, "category": "Cert"}]
    comp = [{"req_code": "REQ-CERT", "status": "INFORMATION_REQUIRED", "evidence_text": None}]
    responses = [
        RequirementResponse(
            requirement_id="REQ-CERT",
            requirement_text="Must hold ISO 27001 certification.",
            category="Cert",
            is_mandatory=True,
            compliance_status="INFORMATION_REQUIRED",
            response_type="INFORMATION_REQUIRED_RESPONSE",
            response="Our company is ISO 27001 certified and complies with all information security requirements."  # False certification claim!
        )
    ]
    draft = _build_test_draft(responses, version=1)
    state: RFPProposalState = {
        "requirements": reqs,
        "compliance_matrix": comp,
        "risks": [],
        "clarification_questions": [],
        "proposal_drafts": [draft.model_dump()],
        "current_version": 1,
        "revision_count": 0,
        "max_revisions": 2
    }

    result = review_proposal_node(state)
    report = result["review_reports"][-1]

    assert report["overall_status"] != "APPROVED"
    cert_findings = [f for f in report["critical_findings"] if f["category"] == "UNGROUNDED_COMMITMENT"]
    assert len(cert_findings) > 0
    assert "certification" in cert_findings[0]["description"].lower() or "unconfirmed" in cert_findings[0]["description"].lower()


# ==============================================================================
# TEST 6: Reviewer detects unsupported SLA
# ==============================================================================
def test_reviewer_detects_unsupported_sla():
    reqs = [{"req_code": "REQ-SLA", "text": "Vendor must respond within 15 minutes 24/7.", "is_mandatory": True, "category": "SLA"}]
    comp = [
        {
            "req_code": "REQ-SLA",
            "status": "COMPLIANT",
            "evidence_text": "Support team operates during business hours 8am-5pm EST.",
            "company_source_doc": "Support Collateral"
        }
    ]
    responses = [
        RequirementResponse(
            requirement_id="REQ-SLA",
            requirement_text="Vendor must respond within 15 minutes 24/7.",
            category="SLA",
            is_mandatory=True,
            compliance_status="COMPLIANT",
            response_type="COMPLIANT_RESPONSE",
            response="We guarantee 24/7 response within 15 minutes across all incidents.",  # SLA not in evidence!
            company_doc_id="doc_supp",
            citations=[{"snippet": "Support team operates during business hours 8am-5pm EST."}]
        )
    ]
    draft = _build_test_draft(responses, version=1)
    state: RFPProposalState = {
        "requirements": reqs,
        "compliance_matrix": comp,
        "risks": [],
        "clarification_questions": [],
        "proposal_drafts": [draft.model_dump()],
        "current_version": 1,
        "revision_count": 0,
        "max_revisions": 2
    }

    result = review_proposal_node(state)
    report = result["review_reports"][-1]

    assert report["overall_status"] != "APPROVED"
    assert len(report["unsupported_claims"]) > 0


# ==============================================================================
# TEST 7: Reviewer detects missing partial limitation
# ==============================================================================
def test_reviewer_detects_missing_partial_limitation():
    reqs = [{"req_code": "REQ-SUPP", "text": "24/7 dedicated support.", "is_mandatory": True, "category": "Support"}]
    comp = [
        {
            "req_code": "REQ-SUPP",
            "status": "PARTIALLY_COMPLIANT",
            "evidence_text": "Email is 24/7; phone support is available during business hours 8am-6pm EST.",
            "notes": "Business hours limitation applies to phone support."
        }
    ]
    responses = [
        RequirementResponse(
            requirement_id="REQ-SUPP",
            requirement_text="24/7 dedicated support.",
            category="Support",
            is_mandatory=True,
            compliance_status="PARTIALLY_COMPLIANT",
            response_type="PARTIAL_RESPONSE",
            response="We provide complete 24/7 phone and email support.",  # Claims complete support, hides business hours limitation!
            company_doc_id="doc_supp"
        )
    ]
    draft = _build_test_draft(responses, version=1)
    state: RFPProposalState = {
        "requirements": reqs,
        "compliance_matrix": comp,
        "risks": [],
        "clarification_questions": [],
        "proposal_drafts": [draft.model_dump()],
        "current_version": 1,
        "revision_count": 0,
        "max_revisions": 2
    }

    result = review_proposal_node(state)
    report = result["review_reports"][-1]

    assert report["overall_status"] != "APPROVED"
    partial_findings = [f for f in report["findings"] if f["category"] == "COMPLIANCE_CONSISTENCY"]
    assert len(partial_findings) > 0
    assert any("business hours" in f["description"].lower() or "complete" in f["description"].lower() for f in partial_findings)


# ==============================================================================
# TEST 8: Reviewer detects missing provenance
# ==============================================================================
def test_reviewer_detects_missing_provenance():
    reqs = [{"req_code": "REQ-SEC", "text": "AES-256 encryption.", "is_mandatory": True, "category": "Security"}]
    comp = [{"req_code": "REQ-SEC", "status": "COMPLIANT", "evidence_text": "AES-256 supported."}]
    responses = [
        RequirementResponse(
            requirement_id="REQ-SEC",
            requirement_text="AES-256 encryption.",
            category="Security",
            is_mandatory=True,
            compliance_status="COMPLIANT",
            response_type="COMPLIANT_RESPONSE",
            response="We support AES-256 encryption.",
            company_doc_id=None,  # Missing provenance!
            citations=[],         # Missing citations!
            evidence_snippet=None # Missing snippet!
        )
    ]
    draft = _build_test_draft(responses, version=1)
    state: RFPProposalState = {
        "requirements": reqs,
        "compliance_matrix": comp,
        "risks": [],
        "clarification_questions": [],
        "proposal_drafts": [draft.model_dump()],
        "current_version": 1,
        "revision_count": 0,
        "max_revisions": 2
    }

    result = review_proposal_node(state)
    report = result["review_reports"][-1]

    assert len(report["traceability_issues"]) > 0
    prov_findings = [f for f in report["findings"] if f["category"] == "TRACEABILITY"]
    assert len(prov_findings) > 0


# ==============================================================================
# TEST 9: Reviewer detects orphan requirement ID
# ==============================================================================
def test_reviewer_detects_orphan_requirement_id():
    reqs = [{"req_code": "REQ-REAL", "text": "Real requirement.", "is_mandatory": True, "category": "Tech"}]
    comp = [{"req_code": "REQ-REAL", "status": "COMPLIANT", "evidence_text": "Supported."}]
    responses = [
        RequirementResponse(
            requirement_id="REQ-REAL",
            requirement_text="Real requirement.",
            category="Tech",
            is_mandatory=True,
            compliance_status="COMPLIANT",
            response_type="COMPLIANT_RESPONSE",
            response="Supported.",
            company_doc_id="doc_1",
            citations=[{"snippet": "Supported."}]
        ),
        RequirementResponse(
            requirement_id="REQ-GHOST-999",  # Orphan response!
            requirement_text="Invented clause.",
            category="Misc",
            is_mandatory=False,
            compliance_status="COMPLIANT",
            response_type="COMPLIANT_RESPONSE",
            response="Invented capability."
        )
    ]
    draft = _build_test_draft(responses, version=1)
    state: RFPProposalState = {
        "requirements": reqs,
        "compliance_matrix": comp,
        "risks": [],
        "clarification_questions": [],
        "proposal_drafts": [draft.model_dump()],
        "current_version": 1,
        "revision_count": 0,
        "max_revisions": 2
    }

    result = review_proposal_node(state)
    report = result["review_reports"][-1]

    orphan_findings = [f for f in report["findings"] if "orphan" in f["description"].lower()]
    assert len(orphan_findings) > 0
    assert "REQ-GHOST-999" in orphan_findings[0]["description"]


# ==============================================================================
# TEST 10: Reviewer flags unresolved INFORMATION_REQUIRED
# ==============================================================================
def test_reviewer_flags_unresolved_information_required():
    reqs = [{"req_code": "REQ-UNCONF-01", "text": "Australian data sovereignty.", "is_mandatory": True, "category": "Legal"}]
    comp = [{"req_code": "REQ-UNCONF-01", "status": "INFORMATION_REQUIRED", "evidence_text": None}]
    responses = [
        RequirementResponse(
            requirement_id="REQ-UNCONF-01",
            requirement_text="Australian data sovereignty.",
            category="Legal",
            is_mandatory=True,
            compliance_status="INFORMATION_REQUIRED",
            response_type="INFORMATION_REQUIRED_RESPONSE",
            response="Information Required: Verification data for REQ-UNCONF-01 is unconfirmed. Internal verification required.",
            clarification_required="Confirm Australian data center availability."
        )
    ]
    draft = _build_test_draft(responses, version=1)
    state: RFPProposalState = {
        "requirements": reqs,
        "compliance_matrix": comp,
        "risks": [],
        "clarification_questions": [],
        "proposal_drafts": [draft.model_dump()],
        "current_version": 1,
        "revision_count": 0,
        "max_revisions": 2
    }

    result = review_proposal_node(state)
    report = result["review_reports"][-1]

    assert report["missing_information_count"] == 1
    assert any("unconfirmed company documentation" in w for w in report["warnings"])


# ==============================================================================
# TEST 11: Reviewer requires human for critical issue
# ==============================================================================
def test_reviewer_requires_human_for_critical_issue():
    reqs = [{"req_code": "REQ-DEALBREAKER", "text": "Mandatory security clearance.", "is_mandatory": True, "category": "Security"}]
    comp = [{"req_code": "REQ-DEALBREAKER", "status": "NON_COMPLIANT", "evidence_text": "Clearance not held."}]
    risks = [{
        "requirement_id": "REQ-DEALBREAKER",
        "severity": "CRITICAL",
        "is_bid_blocking": True,
        "title": "Bid Disqualification Risk: Missing Mandatory Clearance"
    }]
    responses = [
        RequirementResponse(
            requirement_id="REQ-DEALBREAKER",
            requirement_text="Mandatory security clearance.",
            category="Security",
            is_mandatory=True,
            compliance_status="NON_COMPLIANT",
            response_type="EXCEPTION_RESPONSE",
            response="Exception: Security clearance is not currently held."
        )
    ]
    draft = _build_test_draft(responses, version=1)
    state: RFPProposalState = {
        "requirements": reqs,
        "compliance_matrix": comp,
        "risks": risks,
        "clarification_questions": [],
        "proposal_drafts": [draft.model_dump()],
        "current_version": 1,
        "revision_count": 0,
        "max_revisions": 2
    }

    result = review_proposal_node(state)
    report = result["review_reports"][-1]

    assert report["overall_status"] == "HUMAN_REVIEW_REQUIRED"
    assert report["approval_required"] is True
    assert result["workflow_status"] == "HUMAN_REVIEW_REQUIRED"


# ==============================================================================
# TEST 12: Writer <-> Reviewer revision cycle
# ==============================================================================
def test_writer_reviewer_revision_cycle():
    reqs = [
        {"req_code": "REQ-REV-01", "text": "Cloud backups.", "category": "Tech", "is_mandatory": True},
        {"req_code": "REQ-REV-02", "text": "Australian regional presence.", "category": "Legal", "is_mandatory": False}
    ]
    comp = [
        {"req_code": "REQ-REV-01", "status": "COMPLIANT", "evidence_text": "Cloud backups supported.", "company_source_doc": "Doc 1"},
        {"req_code": "REQ-REV-02", "status": "INFORMATION_REQUIRED", "evidence_text": None}
    ]
    risks = [{"requirement_id": "REQ-REV-02", "severity": "MEDIUM", "title": "Regional Presence Gap"}]
    clarifs = [{"requirement_id": "REQ-REV-02", "question": "Confirm regional data center."}]

    state: RFPProposalState = {
        "metadata": {"title": "Multi-Agent Revision Tender"},
        "requirements": reqs,
        "compliance_matrix": comp,
        "risks": risks,
        "clarification_questions": clarifs,
        "proposal_drafts": [],
        "current_version": 0,
        "review_reports": [],
        "revision_count": 0,
        "max_revisions": 2
    }

    # Step 1: Writer produces Draft v1
    writer_res_1 = write_proposal_node(state)
    state["proposal_drafts"] = writer_res_1["proposal_drafts"]
    state["current_version"] = writer_res_1["current_version"]
    assert len(state["proposal_drafts"]) == 1
    assert state["current_version"] == 1

    # Step 2: Reviewer reviews Draft v1 (detects initial draft with open information item & risk -> REVISION_REQUIRED)
    review_res_1 = review_proposal_node(state)
    state["review_reports"] = review_res_1["review_reports"]
    state["revision_count"] = review_res_1["revision_count"]
    report_1 = state["review_reports"][-1]
    assert report_1["overall_status"] == "REVISION_REQUIRED"
    assert state["revision_count"] == 1

    # Route checks: Should route back to write_proposal
    next_route = route_review_outcome(state)
    assert next_route == "write_proposal"

    # Step 3: Writer produces Draft v2 incorporating review feedback
    writer_res_2 = write_proposal_node(state)
    state["proposal_drafts"] = writer_res_2["proposal_drafts"]
    state["current_version"] = writer_res_2["current_version"]
    assert len(state["proposal_drafts"]) == 2
    assert state["current_version"] == 2

    # Step 4: Reviewer reviews Draft v2 (now approved)
    review_res_2 = review_proposal_node(state)
    state["review_reports"] = review_res_2["review_reports"]
    report_2 = state["review_reports"][-1]
    assert report_2["overall_status"] == "APPROVED"
    assert report_2["revision_required"] is False

    # Route checks: Should now route to human final approval gate
    final_route = route_review_outcome(state)
    assert final_route == "human_final_approval_gate"


# ==============================================================================
# TEST 13: Max revision limit prevents infinite loop
# ==============================================================================
def test_max_revision_limit_prevents_infinite_loop():
    # Setup state where draft still has a flaw and revision_count has reached max_revisions (2)
    reqs = [{"req_code": "REQ-01", "text": "Spec.", "is_mandatory": False, "category": "Tech"}]
    comp = [{"req_code": "REQ-01", "status": "COMPLIANT", "evidence_text": "Supported."}]
    # Missing provenance triggers HIGH finding
    responses = [
        RequirementResponse(
            requirement_id="REQ-01",
            requirement_text="Spec.",
            category="Tech",
            is_mandatory=False,
            compliance_status="COMPLIANT",
            response_type="COMPLIANT_RESPONSE",
            response="Supported.",
            company_doc_id=None,
            citations=[]
        )
    ]
    draft = _build_test_draft(responses, version=2)
    state: RFPProposalState = {
        "requirements": reqs,
        "compliance_matrix": comp,
        "risks": [],
        "clarification_questions": [],
        "proposal_drafts": [draft.model_dump()],
        "current_version": 2,
        "revision_count": 2,  # Max reached!
        "max_revisions": 2
    }

    result = review_proposal_node(state)
    report = result["review_reports"][-1]

    # Must transition to HUMAN_REVIEW_REQUIRED, NOT another revision cycle
    assert report["overall_status"] == "HUMAN_REVIEW_REQUIRED"
    assert report["revision_required"] is False
    assert report["approval_required"] is True

    # Routing must proceed to human gate, not writer
    route = route_review_outcome(state)
    assert route == "human_final_approval_gate"


# ==============================================================================
# TEST 14: Revision preserves review history
# ==============================================================================
def test_revision_preserves_review_history():
    prior_report = ReviewReport(
        review_id="rev_historical_001",
        proposal_version=1,
        overall_status="REVISION_REQUIRED",
        approval_required=False,
        revision_required=True,
        score=75,
        summary="Historical critique",
        findings=[]
    )
    reqs = [{"req_code": "REQ-01", "text": "Spec.", "is_mandatory": True, "category": "Tech"}]
    comp = [{"req_code": "REQ-01", "status": "COMPLIANT", "evidence_text": "Supported.", "company_doc_id": "doc1"}]
    responses = [
        RequirementResponse(
            requirement_id="REQ-01",
            requirement_text="Spec.",
            category="Tech",
            is_mandatory=True,
            compliance_status="COMPLIANT",
            response_type="COMPLIANT_RESPONSE",
            response="Supported.",
            company_doc_id="doc1",
            citations=[{"snippet": "Supported."}]
        )
    ]
    draft = _build_test_draft(responses, version=2)
    state: RFPProposalState = {
        "requirements": reqs,
        "compliance_matrix": comp,
        "risks": [],
        "clarification_questions": [],
        "proposal_drafts": [draft.model_dump()],
        "current_version": 2,
        "review_reports": [prior_report.model_dump()],
        "revision_count": 1,
        "max_revisions": 2
    }

    result = review_proposal_node(state)
    all_reports = result["review_reports"]

    assert len(all_reports) == 2
    assert all_reports[0]["review_id"] == "rev_historical_001"
    assert all_reports[0]["proposal_version"] == 1
    assert all_reports[1]["proposal_version"] == 2
    assert all_reports[1]["review_id"] != all_reports[0]["review_id"]


# ==============================================================================
# TEST 15: Reviewer does not mutate compliance matrix
# ==============================================================================
def test_reviewer_does_not_mutate_compliance_matrix():
    comp = [
        {"req_code": "REQ-01", "status": "COMPLIANT", "evidence_text": "Evidence 1", "confidence": 0.95},
        {"req_code": "REQ-02", "status": "NON_COMPLIANT", "evidence_text": "Unsupported", "confidence": 0.90},
        {"req_code": "REQ-03", "status": "INFORMATION_REQUIRED", "evidence_text": None, "confidence": 0.0}
    ]
    comp_copy = copy.deepcopy(comp)
    reqs = [
        {"req_code": "REQ-01", "text": "Spec 1", "is_mandatory": True, "category": "Tech"},
        {"req_code": "REQ-02", "text": "Spec 2", "is_mandatory": True, "category": "Tech"},
        {"req_code": "REQ-03", "text": "Spec 3", "is_mandatory": False, "category": "Legal"}
    ]
    responses = [
        RequirementResponse(
            requirement_id="REQ-01",
            requirement_text="Spec 1",
            category="Tech",
            is_mandatory=True,
            compliance_status="COMPLIANT",
            response_type="COMPLIANT_RESPONSE",
            response="Evidence 1 supported.",
            company_doc_id="d1",
            citations=[{"snippet": "Evidence 1"}]
        ),
        RequirementResponse(
            requirement_id="REQ-02",
            requirement_text="Spec 2",
            category="Tech",
            is_mandatory=True,
            compliance_status="NON_COMPLIANT",
            response_type="EXCEPTION_RESPONSE",
            response="Exception: Out of scope."
        ),
        RequirementResponse(
            requirement_id="REQ-03",
            requirement_text="Spec 3",
            category="Legal",
            is_mandatory=False,
            compliance_status="INFORMATION_REQUIRED",
            response_type="INFORMATION_REQUIRED_RESPONSE",
            response="Information Required: Unconfirmed."
        )
    ]
    draft = _build_test_draft(responses, version=2)
    state: RFPProposalState = {
        "requirements": reqs,
        "compliance_matrix": comp,
        "risks": [],
        "clarification_questions": [],
        "proposal_drafts": [draft.model_dump()],
        "current_version": 2,
        "revision_count": 1,
        "max_revisions": 2
    }

    result = review_proposal_node(state)

    # Compliance matrix must be strictly unmodified
    assert comp == comp_copy
    assert "compliance_matrix" not in result, "Reviewer must not return or overwrite compliance_matrix in state"


# ==============================================================================
# TEST 16: Reviewer does not invent company facts
# ==============================================================================
def test_reviewer_does_not_invent_company_facts():
    reqs = [{"req_code": "REQ-UNVERIFIED", "text": "FedRAMP High authorization.", "is_mandatory": True, "category": "Security"}]
    comp = [{"req_code": "REQ-UNVERIFIED", "status": "INFORMATION_REQUIRED", "evidence_text": None}]
    responses = [
        RequirementResponse(
            requirement_id="REQ-UNVERIFIED",
            requirement_text="FedRAMP High authorization.",
            category="Security",
            is_mandatory=True,
            compliance_status="INFORMATION_REQUIRED",
            response_type="INFORMATION_REQUIRED_RESPONSE",
            response="Information Required: Verification collateral is currently unconfirmed in company documentation."
        )
    ]
    draft = _build_test_draft(responses, version=2)
    state: RFPProposalState = {
        "requirements": reqs,
        "compliance_matrix": comp,
        "risks": [],
        "clarification_questions": [],
        "proposal_drafts": [draft.model_dump()],
        "current_version": 2,
        "revision_count": 1,
        "max_revisions": 2
    }

    result = review_proposal_node(state)
    report = result["review_reports"][-1]

    # Reviewer's recommendations and findings must not state that company has FedRAMP
    all_reviewer_text = report["summary"] + " " + " ".join(report["recommended_actions"])
    for f in report["findings"]:
        all_reviewer_text += " " + f["description"] + " " + f["recommended_action"]

    assert "we hold fedramp" not in all_reviewer_text.lower()
    assert "company is fedramp certified" not in all_reviewer_text.lower()
    assert "platform supports fedramp" not in all_reviewer_text.lower()
