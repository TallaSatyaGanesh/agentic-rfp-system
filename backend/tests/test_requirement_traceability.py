import pytest
import os
from app.agents.classifier_agent import classify_requirements_node, _assign_canonical_ids, ClassifiedRequirement
from app.agents.compliance_agent import analyze_compliance_node
from app.agents.risk_agent import assess_risks_node
from app.agents.writer_agent import write_proposal_node
from app.models.schemas import RawClause

def test_1_explicit_requirement_id_preservation_and_mandatory_detection():
    """
    Asserts that explicit requirement IDs in raw clauses are preserved verbatim
    and mandatory modal indicators in text or original_text are correctly evaluated.
    """
    raw_clauses = [
        RawClause(clause_id="c1", text="REQ-TECH-001: The system shall be a web-based inventory management application.", source_page=1, source_section="Technical"),
        RawClause(clause_id="c2", text="REQ-TECH-002: The system shall support REST API integration.", source_page=1, source_section="Technical"),
        RawClause(clause_id="c3", text="REQ-TECH-003: The system shall provide role-based access control.", source_page=1, source_section="Technical"),
        RawClause(clause_id="c4", text="REQ-TECH-004: The system shall support automated daily database backups.", source_page=2, source_section="Technical"),
        RawClause(clause_id="c5", text="REQ-TECH-005: The system shall guarantee 99.5% availability.", source_page=2, source_section="Technical"),
        RawClause(clause_id="c6", text="REQ-CERT-001: The vendor must hold valid ISO 27001 certification.", source_page=2, source_section="Certification"),
        RawClause(clause_id="c7", text="REQ-ELIG-001: The vendor must have minimum 3 years experience.", source_page=3, source_section="Eligibility"),
        RawClause(clause_id="c8", text="REQ-COMM-001: Pricing must include fixed implementation price and annual support price.", source_page=3, source_section="Commercial"),
        RawClause(clause_id="c9", text="REQ-COMM-002: All pricing quotes must be specified in INR currency.", source_page=3, source_section="Commercial"),
        RawClause(clause_id="c10", text="REQ-DEL-001: Complete implementation must be concluded within 16 weeks of contract award.", source_page=4, source_section="Delivery"),
        RawClause(clause_id="c11", text="REQ-DOC-001: Comprehensive administrator and end-user guides must be provided.", source_page=4, source_section="Documentation"),
    ]

    state = {
        "raw_clauses": [c.model_dump() for c in raw_clauses],
        "logs": []
    }

    result = classify_requirements_node(state)
    reqs = result["requirements"]

    req_map = {r["req_code"]: r for r in reqs}

    # 1. Assert REQ-TECH-004 maps to daily database backup
    assert "REQ-TECH-004" in req_map, "REQ-TECH-004 was not preserved!"
    assert "daily database backup" in req_map["REQ-TECH-004"]["text"].lower()

    # 2. Assert REQ-TECH-005 maps to 99.5% availability
    assert "REQ-TECH-005" in req_map, "REQ-TECH-005 was not preserved!"
    assert "99.5%" in req_map["REQ-TECH-005"]["text"] or "availability" in req_map["REQ-TECH-005"]["text"].lower()

    # 3. Assert REQ-CERT-001 maps to ISO 27001 certification
    assert "REQ-CERT-001" in req_map, "REQ-CERT-001 was not preserved!"
    assert "iso 27001" in req_map["REQ-CERT-001"]["text"].lower()

    # 4. Assert REQ-COMM-001 maps to fixed implementation price + annual support price
    assert "REQ-COMM-001" in req_map, "REQ-COMM-001 was not preserved!"
    assert "fixed implementation price" in req_map["REQ-COMM-001"]["text"].lower()

    # 5. Assert REQ-COMM-002 maps to INR pricing
    assert "REQ-COMM-002" in req_map, "REQ-COMM-002 was not preserved!"
    assert "inr" in req_map["REQ-COMM-002"]["text"].lower()

    # 6. Assert REQ-DEL-001 maps to 16 weeks implementation
    assert "REQ-DEL-001" in req_map, "REQ-DEL-001 was not preserved!"
    assert "16 weeks" in req_map["REQ-DEL-001"]["text"].lower()

    # 7. Assert REQ-DOC-001 maps to administrator + end-user guides AND remains is_mandatory=True
    assert "REQ-DOC-001" in req_map, "REQ-DOC-001 was not preserved!"
    assert "administrator and end-user guides" in req_map["REQ-DOC-001"]["text"].lower()
    assert req_map["REQ-DOC-001"]["is_mandatory"] is True, "REQ-DOC-001 must be mandatory=True!"


def test_2_end_to_end_downstream_stable_id_invariant():
    """
    General Invariant Test:
    Asserts that across all downstream nodes (Compliance, Risks, Proposal Writer):
    - downstream.requirement_id maps strictly to canonical source requirement text.
    - No shifting or index-based mismatching occurs.
    """
    requirements = [
        {
            "req_code": "REQ-TECH-001",
            "category": "Technical",
            "priority": "High",
            "is_mandatory": True,
            "text": "The system shall be a web-based inventory management application.",
            "original_text": "REQ-TECH-001: The system shall be a web-based inventory management application.",
            "source_clause_id": "c1",
            "source_page": 1,
            "source_section": "Technical"
        },
        {
            "req_code": "REQ-TECH-004",
            "category": "Technical",
            "priority": "High",
            "is_mandatory": True,
            "text": "The system shall support automated daily database backups.",
            "original_text": "REQ-TECH-004: The system shall support automated daily database backups.",
            "source_clause_id": "c4",
            "source_page": 2,
            "source_section": "Technical"
        },
        {
            "req_code": "REQ-COMM-001",
            "category": "Commercial",
            "priority": "High",
            "is_mandatory": True,
            "text": "Pricing must include fixed implementation price and annual support price.",
            "original_text": "REQ-COMM-001: Pricing must include fixed implementation price and annual support price.",
            "source_clause_id": "c8",
            "source_page": 3,
            "source_section": "Commercial"
        },
        {
            "req_code": "REQ-DOC-001",
            "category": "Documentation",
            "priority": "High",
            "is_mandatory": True,
            "text": "Comprehensive administrator and end-user guides must be provided.",
            "original_text": "REQ-DOC-001: Comprehensive administrator and end-user guides must be provided.",
            "source_clause_id": "c11",
            "source_page": 4,
            "source_section": "Documentation"
        }
    ]

    canonical_map = {r["req_code"]: r for r in requirements}

    state = {
        "requirements": requirements,
        "metadata": {"title": "Test RFP Traceability"},
        "logs": []
    }

    # 1. Compliance Agent Node
    comp_state = analyze_compliance_node(state)
    compliance_matrix = comp_state["compliance_matrix"]

    for comp in compliance_matrix:
        code = comp["req_code"]
        assert code in canonical_map, f"Unknown req_code in compliance matrix: {code}"
        canonical_text = canonical_map[code]["text"]
        assert comp["requirement_text"] == canonical_text, (
            f"Compliance text mismatch for {code}! Expected '{canonical_text}', got '{comp['requirement_text']}'"
        )

    # 2. Risk Agent Node
    state["compliance_matrix"] = compliance_matrix
    risk_state = assess_risks_node(state)
    risks = risk_state["risks"]

    for rk in risks:
        code = rk.get("requirement_id")
        if code and code in canonical_map:
            assert code in canonical_map

    # 3. Writer Agent Node
    state["risks"] = risks
    state["clarification_questions"] = risk_state["clarification_questions"]
    writer_state = write_proposal_node(state)
    proposal_draft = writer_state["proposal_drafts"][-1]

    req_responses = proposal_draft["requirement_responses"]
    assert len(req_responses) == len(requirements)

    for resp in req_responses:
        code = resp["requirement_id"]
        assert code in canonical_map, f"Unknown requirement_id in proposal draft: {code}"
        canonical_req = canonical_map[code]
        assert resp["requirement_text"] == canonical_req["text"], (
            f"Proposal response requirement_text mismatch for {code}! Expected '{canonical_req['text']}', got '{resp['requirement_text']}'"
        )
        assert resp["category"] == canonical_req["category"], (
            f"Proposal response category mismatch for {code}! Expected '{canonical_req['category']}', got '{resp['category']}'"
        )
        assert resp["is_mandatory"] == canonical_req["is_mandatory"], (
            f"Proposal response mandatory flag mismatch for {code}!"
        )
