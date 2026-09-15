import pytest
import re
from typing import Dict, Any, List
from app.agents.classifier_agent import (
    classify_requirements_node,
    _fallback_classify_batch,
    _determine_category,
    _determine_mandatory,
    _assign_canonical_ids,
    CATEGORY_PREFIX_MAP
)
from app.models.schemas import ClassifiedRequirement, ClassificationAgentOutput
from app.agents.state import RFPProposalState
from app.agents.llm_factory import LLMFactory

def _make_raw_clause(clause_id: str, text: str, page: int = 1, section: str = "General") -> Dict[str, Any]:
    return {
        "clause_id": clause_id,
        "text": text,
        "source_page": page,
        "source_section": section
    }

def _make_state(clauses: List[Dict[str, Any]]) -> RFPProposalState:
    return {
        "rfp_id": "test_rfp_classifier",
        "file_path": "dummy.txt",
        "metadata": None,
        "raw_clauses": clauses,
        "requirements": [],
        "compliance_matrix": [],
        "overall_compliance_score": 0.0,
        "risks": [],
        "clarification_questions": [],
        "go_nogo_decision": None,
        "go_nogo_notes": None,
        "proposal_drafts": [],
        "current_version": 0,
        "review_reports": [],
        "revision_count": 0,
        "max_revisions": 2,
        "final_approval_decision": None,
        "human_feedback": None,
        "active_agent": "Classification Agent",
        "workflow_status": "CLASSIFYING",
        "logs": [],
        "error": None
    }


def test_technical_requirement_classification():
    """Requirement A: Technical requirement classification."""
    clause = _make_raw_clause(
        "CLAUSE-001",
        "The cloud platform MUST maintain automated horizontal autoscaling to handle 10,000 concurrent active users.",
        page=2,
        section="Section 2: Technical & Infrastructure"
    )
    res = classify_requirements_node(_make_state([clause]))
    reqs = res["requirements"]

    assert len(reqs) == 1
    assert reqs[0]["category"] == "Technical"
    assert reqs[0]["req_code"].startswith("REQ-TECH-")
    assert reqs[0]["is_mandatory"] is True


def test_commercial_requirement_classification():
    """Requirement B: Commercial requirement classification."""
    clause = _make_raw_clause(
        "CLAUSE-002",
        "The fee structure SHALL be based on fixed-price milestones with net-30 invoicing upon departmental sign-off.",
        page=5,
        section="Section 5: Commercial Pricing Terms"
    )
    res = classify_requirements_node(_make_state([clause]))
    reqs = res["requirements"]

    assert len(reqs) == 1
    assert reqs[0]["category"] == "Commercial"
    assert reqs[0]["req_code"].startswith("REQ-COMM-")
    assert reqs[0]["is_mandatory"] is True


def test_contractual_requirement_classification():
    """Requirement C: Contractual requirement classification."""
    clause = _make_raw_clause(
        "CLAUSE-003",
        "The contractor SHALL agree to unlimited liability for data loss and a 10% penalty for service outages.",
        page=6,
        section="Section 6: Legal & Contract Terms"
    )
    res = classify_requirements_node(_make_state([clause]))
    reqs = res["requirements"]

    assert len(reqs) == 1
    assert reqs[0]["category"] == "Contractual"
    assert reqs[0]["req_code"].startswith("REQ-CONTRACT-")
    assert reqs[0]["is_mandatory"] is True


def test_certification_requirement_classification():
    """Requirement D: Certification requirement classification."""
    clause = _make_raw_clause(
        "CLAUSE-004",
        "The vendor MUST hold an active SOC2 Type II certification and ISO/IEC 27001 accreditation across all hosting regions.",
        page=3,
        section="Section 3: Security & Compliance"
    )
    res = classify_requirements_node(_make_state([clause]))
    reqs = res["requirements"]

    assert len(reqs) == 1
    assert reqs[0]["category"] == "Certification"
    assert reqs[0]["req_code"].startswith("REQ-CERT-")
    assert reqs[0]["is_mandatory"] is True


def test_delivery_requirement_classification():
    """Requirement E: Delivery requirement classification."""
    clause = _make_raw_clause(
        "CLAUSE-005",
        "Complete platform migration and system handover MUST be concluded within 24 weeks of contract award.",
        page=4,
        section="Section 4: Implementation Schedule"
    )
    res = classify_requirements_node(_make_state([clause]))
    reqs = res["requirements"]

    assert len(reqs) == 1
    assert reqs[0]["category"] == "Delivery"
    assert reqs[0]["req_code"].startswith("REQ-DELIVERY-")
    assert reqs[0]["is_mandatory"] is True


def test_documentation_and_submission_classification():
    """Requirement F: Documentation and Submission requirement classification."""
    clause_doc = _make_raw_clause(
        "CLAUSE-006",
        "The vendor SHALL provide documented RESTful APIs and comprehensive system administration runbooks.",
        page=2,
        section="Section 2: Architecture Documentation"
    )
    clause_sub = _make_raw_clause(
        "CLAUSE-007",
        "The bidder SHALL submit the technical proposal via the electronic procurement portal before the closing date.",
        page=1,
        section="Section 1: Submission Guidelines"
    )
    res = classify_requirements_node(_make_state([clause_doc, clause_sub]))
    reqs = res["requirements"]

    assert len(reqs) == 2
    doc_req = next(r for r in reqs if r["source_clause_id"] == "CLAUSE-006")
    sub_req = next(r for r in reqs if r["source_clause_id"] == "CLAUSE-007")

    assert doc_req["category"] == "Documentation"
    assert doc_req["req_code"].startswith("REQ-DOC-")

    assert sub_req["category"] == "Submission"
    assert sub_req["req_code"].startswith("REQ-SUBMISSION-")


def test_eligibility_requirement_classification():
    """Requirement G: Eligibility requirement classification."""
    clause = _make_raw_clause(
        "CLAUSE-008",
        "The bidder MUST demonstrate a minimum of 5 years of enterprise cloud migration experience and provide 3 verified case studies.",
        page=1,
        section="Section 1: Vendor Eligibility"
    )
    res = classify_requirements_node(_make_state([clause]))
    reqs = res["requirements"]

    assert len(reqs) == 1
    assert reqs[0]["category"] == "Eligibility"
    assert reqs[0]["req_code"].startswith("REQ-ELIGIBILITY-")
    assert reqs[0]["is_mandatory"] is True


def test_mandatory_vs_optional_classification():
    """Requirement H: Mandatory vs optional classification."""
    mandatory_clause = _make_raw_clause(
        "CLAUSE-009",
        "The system SHALL enforce mandatory multi-factor authentication for administrative users.",
        page=3,
        section="Section 3: Security"
    )
    optional_clause = _make_raw_clause(
        "CLAUSE-010",
        "The vendor SHOULD provide optional mobile telemetry dashboards if available.",
        page=4,
        section="Section 4: User Workflows"
    )
    res = classify_requirements_node(_make_state([mandatory_clause, optional_clause]))
    reqs = res["requirements"]

    req_m = next(r for r in reqs if r["source_clause_id"] == "CLAUSE-009")
    req_o = next(r for r in reqs if r["source_clause_id"] == "CLAUSE-010")

    assert req_m["is_mandatory"] is True
    assert req_m["priority"] == "High"
    assert req_m["mandatory_confidence"] == 1.0
    assert "explicit mandatory" in req_m["mandatory_reasoning"].lower()

    assert req_o["is_mandatory"] is False
    assert req_o["priority"] == "Low"
    assert req_o["mandatory_confidence"] == 1.0
    assert "explicit optional" in req_o["mandatory_reasoning"].lower()


def test_explicit_must_mandatory():
    """Verify explicit MUST is classified as mandatory with High priority and confidence 1.0."""
    clause = _make_raw_clause("C-MUST", "The vendor MUST provide automated weekly database snapshots.", 2, "Technical")
    res = classify_requirements_node(_make_state([clause]))
    req = res["requirements"][0]

    assert req["is_mandatory"] is True
    assert req["priority"] == "High"
    assert req["mandatory_confidence"] == 1.0
    assert "MUST" in req["mandatory_reasoning"]


def test_explicit_shall_mandatory():
    """Verify explicit SHALL is classified as mandatory with High priority and confidence 1.0."""
    clause = _make_raw_clause("C-SHALL", "The contractor SHALL submit monthly SLA compliance reports.", 3, "Contractual")
    res = classify_requirements_node(_make_state([clause]))
    req = res["requirements"][0]

    assert req["is_mandatory"] is True
    assert req["priority"] == "High"
    assert req["mandatory_confidence"] == 1.0
    assert "SHALL" in req["mandatory_reasoning"]


def test_explicit_should_optional():
    """Verify explicit SHOULD is classified as optional with Low priority and confidence 1.0."""
    clause = _make_raw_clause("C-SHOULD", "The platform SHOULD support dark mode theme customization.", 4, "Functional")
    res = classify_requirements_node(_make_state([clause]))
    req = res["requirements"][0]

    assert req["is_mandatory"] is False
    assert req["priority"] == "Low"
    assert req["mandatory_confidence"] == 1.0
    assert "SHOULD" in req["mandatory_reasoning"]


def test_explicit_may_optional():
    """Verify explicit MAY is classified as optional with Low priority and confidence 1.0."""
    clause = _make_raw_clause("C-MAY", "The contractor MAY submit alternative cloud storage pricing tiers.", 5, "Commercial")
    res = classify_requirements_node(_make_state([clause]))
    req = res["requirements"][0]

    assert req["is_mandatory"] is False
    assert req["priority"] == "Low"
    assert req["mandatory_confidence"] == 1.0
    assert "MAY" in req["mandatory_reasoning"]


def test_ambiguous_no_modal_does_not_claim_mandatory():
    """Verify ambiguous/no-modal clause does NOT falsely claim high-confidence mandatory status."""
    clause = _make_raw_clause(
        "C-AMBIGUOUS",
        "Real-time freight telemetry data streams to regional edge gateways every 5 minutes.",
        page=2,
        section="Section 2: Architecture"
    )
    res = classify_requirements_node(_make_state([clause]))
    req = res["requirements"][0]

    # Must NOT claim that it is mandatory
    assert req["is_mandatory"] is False
    assert req["priority"] != "High"
    assert req["mandatory_confidence"] == 0.0
    assert "ambiguous" in req["mandatory_reasoning"].lower() or "inferred" in req["mandatory_reasoning"].lower()


def test_requirement_ids_unique_and_correctly_formatted():
    """Requirement I: Requirement IDs are unique, sequential, and correctly formatted."""
    clauses = [
        _make_raw_clause("C-01", "The platform MUST support REST APIs.", 1, "Technical"),
        _make_raw_clause("C-02", "The system SHALL provide automated failover.", 1, "Technical"),
        _make_raw_clause("C-03", "The bidder SHALL submit 3 copies of pricing.", 2, "Commercial"),
        _make_raw_clause("C-04", "The vendor MUST hold ISO 27001 certification.", 3, "Security"),
        _make_raw_clause("C-05", "The contractor SHALL accept mutual indemnification.", 4, "Legal"),
        _make_raw_clause("C-06", "The project MUST conclude within 12 weeks.", 5, "Schedule")
    ]
    res = classify_requirements_node(_make_state(clauses))
    reqs = res["requirements"]

    req_codes = [r["req_code"] for r in reqs]
    # Check uniqueness
    assert len(req_codes) == len(set(req_codes)), f"Duplicate req_codes detected: {req_codes}"

    # Check format: REQ-{PREFIX}-\d{3}
    pattern = re.compile(r'^REQ-(?:TECH|COMM|CONTRACT|ADMIN|CERT|DELIVERY|DOC|SUBMISSION|ELIGIBILITY)-\d{3}$')
    for code in req_codes:
        assert pattern.match(code), f"Invalid req_code format: {code}"


def test_source_traceability_preserved():
    """Requirement J: Source page, section, and clause ID are strictly preserved."""
    clause = _make_raw_clause(
        "CLAUSE-XYZ-777",
        "The vendor SHALL provide TLS 1.3 encryption across all communication links.",
        page=9,
        section="Section 9: Network Security Safeguards"
    )
    res = classify_requirements_node(_make_state([clause]))
    req = res["requirements"][0]

    assert req["source_clause_id"] == "CLAUSE-XYZ-777"
    assert req["source_page"] == 9
    assert req["source_section"] == "Section 9: Network Security Safeguards"
    assert "TLS 1.3" in req["text"]
    assert req["original_text"] == clause["text"]


def test_llm_failure_fallback(monkeypatch):
    """Requirement K: LLM failure fallback works deterministically."""
    # Force LLMFactory to return a mock LLM that raises an exception
    class FailingChatModel:
        def with_structured_output(self, schema):
            def _invoke(*args, **kwargs):
                raise RuntimeError("Simulated LLM API outage")
            return type("Invoker", (), {"invoke": _invoke})()

    monkeypatch.setattr(LLMFactory, "get_chat_model", lambda: FailingChatModel())

    clause = _make_raw_clause(
        "CLAUSE-F-01",
        "The vendor MUST provide SOC2 Type II compliance audit reports annually.",
        page=3,
        section="Compliance"
    )
    res = classify_requirements_node(_make_state([clause]))
    reqs = res["requirements"]

    # Even with LLM throwing runtime error, fallback succeeds seamlessly
    assert len(reqs) == 1
    assert reqs[0]["category"] == "Certification"
    assert reqs[0]["is_mandatory"] is True
    assert reqs[0]["req_code"].startswith("REQ-CERT-")


def test_classifier_does_not_invent_requirements():
    """Requirement L: Classifier does not invent requirements beyond supplied RawClause input."""
    # Test 1: Empty input returns empty requirements
    res_empty = classify_requirements_node(_make_state([]))
    assert res_empty["requirements"] == []

    # Test 2: Exactly 3 clauses in -> exactly 3 requirements out
    three_clauses = [
        _make_raw_clause("C-01", "The bidder SHALL submit technical architecture documentation.", 1),
        _make_raw_clause("C-02", "The contractor SHALL agree to 99.95% uptime SLA.", 2),
        _make_raw_clause("C-03", "The pricing MUST include all applicable licensing fees.", 3),
    ]
    res_three = classify_requirements_node(_make_state(three_clauses))
    assert len(res_three["requirements"]) == 3


def test_duplicate_handling():
    """Requirement M: Duplicate handling detects redundant clauses while preserving distinct cross-section requirements."""
    # Case 1: Identical text, identical page and section -> filtered to 1 requirement
    dup_clause_1 = _make_raw_clause("C-D1", "The system MUST support OAuth 2.0 authentication.", 2, "Security")
    dup_clause_2 = _make_raw_clause("C-D2", "The system MUST support OAuth 2.0 authentication.", 2, "Security")

    # Case 2: Identical requirement text, but appears on different pages/sections -> both preserved for traceability
    cross_section_clause = _make_raw_clause("C-D3", "The system MUST support OAuth 2.0 authentication.", 8, "API Architecture")

    clauses = [dup_clause_1, dup_clause_2, cross_section_clause]
    res = classify_requirements_node(_make_state(clauses))
    reqs = res["requirements"]

    # Exactly 2 requirements should be produced (1 from page 2, 1 from page 8)
    assert len(reqs) == 2
    pages = [r["source_page"] for r in reqs]
    assert 2 in pages
    assert 8 in pages
    assert reqs[0]["req_code"] != reqs[1]["req_code"]
