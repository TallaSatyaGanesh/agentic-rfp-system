import pytest
from unittest.mock import MagicMock, patch
from app.agents.risk_agent import (
    assess_risks_node,
    _apply_programmatic_safety_guard,
    _fallback_risk_analysis,
    _calibrate_risk_severity,
    _sanitize_unverified_claim
)
from app.agents.state import RFPProposalState
from app.models.schemas import RiskItem, ClarificationQuestion, RiskAndClarificationOutput

# ==============================================================================
# TEST A: Mandatory NON_COMPLIANT requirement produces CRITICAL/HIGH risk
# ==============================================================================
def test_non_compliant_mandatory_requirement():
    """
    Verifies that a mandatory NON_COMPLIANT requirement generates an appropriate
    CRITICAL or HIGH risk and an actionable decision clarification.
    """
    state: RFPProposalState = {
        "requirements": [
            {
                "req_code": "REQ-LEGACY-01",
                "text": "The platform must provide mainframe COBOL emulation and IBM z/OS integration.",
                "category": "Architecture",
                "is_mandatory": True,
                "source_page": 5,
                "source_section": "Architecture"
            }
        ],
        "compliance_matrix": [
            {
                "req_code": "REQ-LEGACY-01",
                "status": "NON_COMPLIANT",
                "confidence": 0.95,
                "evidence_text": "Mainframe COBOL emulation is out of scope and explicitly excluded.",
                "company_source_doc": "Architecture Scope and Exclusions (exclusions.txt)",
                "company_doc_id": "comp_excl_01",
                "chunk_id": "comp_excl_01_chunk_0",
                "source_page": 12,
                "source_section": "Exclusions",
                "citations": [
                    {
                        "document_title": "Architecture Scope and Exclusions",
                        "company_doc_id": "comp_excl_01",
                        "snippet": "Mainframe COBOL emulation is out of scope and explicitly excluded."
                    }
                ],
                "notes": "Explicitly excluded in company documentation."
            }
        ]
    }

    result = assess_risks_node(state)
    risks = result["risks"]
    clarifications = result["clarification_questions"]

    assert len(risks) == 1
    assert risks[0]["requirement_id"] == "REQ-LEGACY-01"
    assert risks[0]["severity"] == "CRITICAL"
    assert "unsupported" in risks[0]["description"].lower() or "non-compliant" in risks[0]["description"].lower()
    assert risks[0]["compliance_status"] == "NON_COMPLIANT"

    assert len(clarifications) == 1
    assert clarifications[0]["requirement_id"] == "REQ-LEGACY-01"
    assert clarifications[0]["priority"] == "CRITICAL"
    assert "alternative" in clarifications[0]["question_text"].lower() or "exception" in clarifications[0]["question_text"].lower()


# ==============================================================================
# TEST B: Mandatory INFORMATION_REQUIRED requirement produces risk & clarification
# ==============================================================================
def test_information_required_mandatory_requirement():
    """
    Verifies that a mandatory requirement with INFORMATION_REQUIRED produces a HIGH/CRITICAL
    risk and clarification, but is NEVER converted into NON_COMPLIANT.
    """
    state: RFPProposalState = {
        "requirements": [
            {
                "req_code": "REQ-DISASTER-01",
                "text": "Vendor must guarantee RPO < 15 minutes and RTO < 1 hour for cross-region disaster recovery.",
                "category": "Technical",
                "is_mandatory": True,
                "source_page": 10,
                "source_section": "Disaster Recovery"
            }
        ],
        "compliance_matrix": [
            {
                "req_code": "REQ-DISASTER-01",
                "status": "INFORMATION_REQUIRED",
                "confidence": 0.0,
                "evidence_text": None,
                "company_source_doc": None,
                "citations": [],
                "notes": "No verified DR replication metrics found in knowledge base exceeding threshold."
            }
        ]
    }

    result = assess_risks_node(state)
    risks = result["risks"]
    clarifications = result["clarification_questions"]

    assert len(risks) == 1
    assert risks[0]["requirement_id"] == "REQ-DISASTER-01"
    assert risks[0]["severity"] == "HIGH"
    assert risks[0]["compliance_status"] == "INFORMATION_REQUIRED"
    assert "could not be verified" in risks[0]["description"].lower() or "missing" in risks[0]["description"].lower()

    assert len(clarifications) == 1
    assert clarifications[0]["requirement_id"] == "REQ-DISASTER-01"
    assert clarifications[0]["compliance_status"] == "INFORMATION_REQUIRED"
    assert "confirm" in clarifications[0]["question_text"].lower() or "clarify" in clarifications[0]["question_text"].lower()


# ==============================================================================
# TEST C: Mandatory PARTIALLY_COMPLIANT requirement produces gap risk
# ==============================================================================
def test_partially_compliant_mandatory_requirement():
    """
    Verifies that a mandatory requirement with PARTIALLY_COMPLIANT produces a gap risk
    and a targeted clarification identifying the limitation/workaround.
    """
    state: RFPProposalState = {
        "requirements": [
            {
                "req_code": "REQ-IAM-02",
                "text": "Must integrate with legacy on-premise Active Directory for directory sync.",
                "category": "Security",
                "is_mandatory": True,
                "source_page": 8,
                "source_section": "Identity Federation"
            }
        ],
        "compliance_matrix": [
            {
                "req_code": "REQ-IAM-02",
                "status": "PARTIALLY_COMPLIANT",
                "confidence": 0.83,
                "evidence_text": "Legacy on-premise Active Directory sync is partially supported via custom LDAP connector workaround.",
                "company_source_doc": "IAM Collateral",
                "company_doc_id": "comp_iam_01",
                "chunk_id": "comp_iam_01_chunk_1",
                "citations": [],
                "notes": "Partially supported via custom LDAP connector workaround."
            }
        ]
    }

    result = assess_risks_node(state)
    risks = result["risks"]
    clarifications = result["clarification_questions"]

    assert len(risks) == 1
    assert risks[0]["requirement_id"] == "REQ-IAM-02"
    assert risks[0]["severity"] == "HIGH"
    assert risks[0]["compliance_status"] == "PARTIALLY_COMPLIANT"
    assert "partially supported" in risks[0]["description"].lower() or "workaround" in risks[0]["description"].lower()

    assert len(clarifications) == 1
    assert clarifications[0]["requirement_id"] == "REQ-IAM-02"
    assert "workaround" in clarifications[0]["question_text"].lower() or "partial" in clarifications[0]["question_text"].lower()


# ==============================================================================
# TEST D: Optional requirement receives lower severity
# ==============================================================================
def test_optional_requirement_lower_severity():
    """
    Verifies that an optional requirement does NOT automatically become CRITICAL or HIGH.
    """
    state: RFPProposalState = {
        "requirements": [
            {
                "req_code": "REQ-OPT-01",
                "text": "System may optionally provide automated translation for Japanese and Spanish.",
                "category": "Technical",
                "is_mandatory": False,
                "source_page": 15,
                "source_section": "Localization"
            }
        ],
        "compliance_matrix": [
            {
                "req_code": "REQ-OPT-01",
                "status": "INFORMATION_REQUIRED",
                "confidence": 0.0,
                "evidence_text": None,
                "notes": "No translation data found."
            }
        ]
    }

    result = assess_risks_node(state)
    risks = result["risks"]
    
    if risks:
        assert risks[0]["severity"] in ["MEDIUM", "LOW"], "Optional requirement gap must not be CRITICAL or HIGH"


# ==============================================================================
# TEST E: Hallucination Prevention on Missing Certification
# ==============================================================================
def test_hallucination_prevention_certification():
    """
    Verifies that missing certification evidence produces an information-gap clarification,
    and NEVER claims the company lacks the certification as fact.
    """
    state: RFPProposalState = {
        "requirements": [
            {
                "req_code": "REQ-CERT-ISO27001",
                "text": "Vendor must hold active ISO 27001 certification.",
                "category": "Certification",
                "is_mandatory": True,
                "source_page": 3,
                "source_section": "Compliance"
            }
        ],
        "compliance_matrix": [
            {
                "req_code": "REQ-CERT-ISO27001",
                "status": "INFORMATION_REQUIRED",
                "confidence": 0.0,
                "evidence_text": None,
                "notes": "No verified certification in KB."
            }
        ]
    }

    result = assess_risks_node(state)
    risks = result["risks"]
    clarifications = result["clarification_questions"]

    assert len(risks) == 1
    assert "could not be verified" in risks[0]["description"].lower()
    assert "does not have" not in risks[0]["description"].lower()
    assert "lacks" not in risks[0]["description"].lower()

    assert len(clarifications) == 1
    assert "confirm whether the company currently holds" in clarifications[0]["question_text"].lower() or "confirm" in clarifications[0]["question_text"].lower()


# ==============================================================================
# TEST F: Traceability preserved on risks and clarifications
# ==============================================================================
def test_traceability_preserved():
    """
    Verifies that requirement_id, source_page, source_section, compliance_status,
    company_doc_id, chunk_id, and citations are properly populated.
    """
    state: RFPProposalState = {
        "requirements": [
            {
                "req_code": "REQ-SLA-999",
                "text": "Vendor must provide 99.999% monthly uptime SLA with 100% service fee penalties.",
                "category": "Legal",
                "is_mandatory": True,
                "source_page": 22,
                "source_section": "SLA Penalties"
            }
        ],
        "compliance_matrix": [
            {
                "req_code": "REQ-SLA-999",
                "status": "NON_COMPLIANT",
                "confidence": 0.90,
                "evidence_text": "Standard uptime SLA is 99.95% backed by service credits.",
                "company_source_doc": "Cloud SLA Guide",
                "company_doc_id": "comp_sla_01",
                "chunk_id": "comp_sla_01_chunk_2",
                "source_page": 4,
                "source_section": "Availability",
                "citations": [
                    {
                        "document_title": "Cloud SLA Guide",
                        "company_doc_id": "comp_sla_01",
                        "chunk_id": "comp_sla_01_chunk_2",
                        "snippet": "Standard uptime SLA is 99.95% backed by service credits."
                    }
                ],
                "notes": "Conflict between 99.999% requested and 99.95% supported."
            }
        ]
    }

    result = assess_risks_node(state)
    risk = result["risks"][0]
    clarif = result["clarification_questions"][0]

    assert risk["requirement_id"] == "REQ-SLA-999"
    assert risk["source_page"] == 22
    assert risk["source_section"] == "SLA Penalties"
    assert risk["compliance_status"] == "NON_COMPLIANT"
    assert risk["company_doc_id"] == "comp_sla_01"
    assert risk["chunk_id"] == "comp_sla_01_chunk_2"
    assert len(risk["citations"]) > 0

    assert clarif["requirement_id"] == "REQ-SLA-999"
    assert clarif["compliance_status"] == "NON_COMPLIANT"
    assert len(clarif["citations"]) > 0


# ==============================================================================
# TEST G: Duplicate Handling
# ==============================================================================
def test_duplicate_handling():
    """
    Verifies that duplicate mentions of the same requirement do not produce duplicate risks or clarifications.
    """
    state: RFPProposalState = {
        "requirements": [
            {
                "req_code": "REQ-DUP-01",
                "text": "Mandatory FedRAMP High certification.",
                "category": "Certification",
                "is_mandatory": True,
                "source_page": 2,
                "source_section": "Security"
            }
        ],
        "compliance_matrix": [
            {
                "req_code": "REQ-DUP-01",
                "status": "INFORMATION_REQUIRED",
                "confidence": 0.0,
                "evidence_text": None,
                "citations": []
            }
        ]
    }

    # Simulate LLM returning 3 duplicate risk items for REQ-DUP-01
    mock_llm_output = RiskAndClarificationOutput(
        risks=[
            RiskItem(
                risk_id="RISK-1",
                requirement_id="REQ-DUP-01",
                category="Certification",
                severity="HIGH",
                description="First duplicate risk for REQ-DUP-01",
                mitigation_strategy="Mitigation 1"
            ),
            RiskItem(
                risk_id="RISK-2",
                requirement_id="REQ-DUP-01",
                category="Certification",
                severity="HIGH",
                description="Second duplicate risk for REQ-DUP-01",
                mitigation_strategy="Mitigation 2"
            )
        ],
        clarification_questions=[
            ClarificationQuestion(
                q_number=1,
                requirement_id="REQ-DUP-01",
                rfp_section_reference="Ref: REQ-DUP-01",
                question_text="First duplicate question?",
                rationale="Rationale 1"
            ),
            ClarificationQuestion(
                q_number=2,
                requirement_id="REQ-DUP-01",
                rfp_section_reference="Ref: REQ-DUP-01",
                question_text="Second duplicate question?",
                rationale="Rationale 2"
            )
        ]
    )

    req_map = {"REQ-DUP-01": state["requirements"][0]}
    comp_map = {"REQ-DUP-01": state["compliance_matrix"][0]}

    deduped_risks, deduped_clarifs = _apply_programmatic_safety_guard(
        mock_llm_output, req_map, comp_map
    )

    assert len(deduped_risks) == 1, "Expected exactly 1 deduplicated risk for REQ-DUP-01"
    assert len(deduped_clarifs) == 1, "Expected exactly 1 deduplicated clarification for REQ-DUP-01"


# ==============================================================================
# TEST H: LLM Failure Fallback
# ==============================================================================
def test_llm_failure_fallback():
    """
    Verifies that when LLM evaluation fails or encounters an exception,
    the deterministic fallback executes and produces valid, evidence-grounded risks and clarifications.
    """
    failing_llm = MagicMock()
    failing_llm.with_structured_output.side_effect = RuntimeError("LLM rate limit / timeout")

    with patch("app.agents.risk_agent.LLMFactory.get_chat_model", return_value=failing_llm):
        state: RFPProposalState = {
            "requirements": [
                {
                    "req_code": "REQ-FB-01",
                    "text": "Mainframe COBOL emulation is mandatory.",
                    "category": "Architecture",
                    "is_mandatory": True
                },
                {
                    "req_code": "REQ-FB-02",
                    "text": "ISO 27001 certification is mandatory.",
                    "category": "Certification",
                    "is_mandatory": True
                }
            ],
            "compliance_matrix": [
                {
                    "req_code": "REQ-FB-01",
                    "status": "NON_COMPLIANT",
                    "confidence": 0.95,
                    "evidence_text": "COBOL is unsupported."
                },
                {
                    "req_code": "REQ-FB-02",
                    "status": "INFORMATION_REQUIRED",
                    "confidence": 0.0,
                    "evidence_text": None
                }
            ]
        }

        result = assess_risks_node(state)
        assert len(result["risks"]) == 2
        assert len(result["clarification_questions"]) == 2

        status_map = {r["requirement_id"]: r["severity"] for r in result["risks"]}
        assert status_map["REQ-FB-01"] == "CRITICAL"
        assert status_map["REQ-FB-02"] == "HIGH"  # Mandatory INFORMATION_REQUIRED is HIGH by default, NOT CRITICAL


# ==============================================================================
# TEST I: Invalid Requirement Reference Rejected
# ==============================================================================
def test_invalid_requirement_reference_rejected():
    """
    Verifies that if an LLM invents a non-existent requirement ID,
    the safety guard rejects it to prevent orphan risks/clarifications.
    """
    mock_llm_output = RiskAndClarificationOutput(
        risks=[
            RiskItem(
                risk_id="RISK-VALID-01",
                requirement_id="REQ-VALID-01",
                category="Technical",
                severity="HIGH",
                description="Valid risk",
                mitigation_strategy="Valid mitigation"
            ),
            RiskItem(
                risk_id="RISK-GHOST-999",
                requirement_id="REQ-GHOST-999",  # Hallucinated!
                category="Technical",
                severity="HIGH",
                description="Hallucinated risk for phantom requirement",
                mitigation_strategy="Phantom mitigation"
            )
        ],
        clarification_questions=[
            ClarificationQuestion(
                q_number=1,
                requirement_id="REQ-GHOST-999",  # Hallucinated!
                rfp_section_reference="Ref: REQ-GHOST-999",
                question_text="Hallucinated question?",
                rationale="Phantom rationale"
            )
        ]
    )

    req_map = {
        "REQ-VALID-01": {
            "req_code": "REQ-VALID-01",
            "text": "Valid technical specification.",
            "is_mandatory": True,
            "category": "Technical"
        }
    }
    comp_map = {
        "REQ-VALID-01": {
            "req_code": "REQ-VALID-01",
            "status": "INFORMATION_REQUIRED"
        }
    }

    validated_risks, validated_clarifs = _apply_programmatic_safety_guard(
        mock_llm_output, req_map, comp_map
    )

    assert len(validated_risks) == 1
    assert validated_risks[0].requirement_id == "REQ-VALID-01"
    assert len(validated_clarifs) == 0, "Hallucinated clarification must be rejected"


# ==============================================================================
# TEST J: Compliance Preservation
# ==============================================================================
def test_compliance_preservation():
    """
    Verifies that Agent 4 does NOT modify Agent 3's compliance matrix or overall score.
    """
    state: RFPProposalState = {
        "requirements": [
            {"req_code": "REQ-1", "text": "Spec 1", "is_mandatory": True, "category": "Technical"}
        ],
        "compliance_matrix": [
            {"req_code": "REQ-1", "status": "NON_COMPLIANT", "confidence": 0.90}
        ],
        "overall_compliance_score": 0.0
    }

    result = assess_risks_node(state)
    # assess_risks_node returns {"risks": ..., "clarification_questions": ...}
    # It must not overwrite compliance_matrix in state
    assert "compliance_matrix" not in result or result["compliance_matrix"] == state["compliance_matrix"]


# ==============================================================================
# TEST K: Unsupported LLM Claim Sanitization
# ==============================================================================
def test_unsupported_llm_claim_sanitization():
    """
    Verifies that if an LLM claims as fact that the company lacks a capability
    when status is INFORMATION_REQUIRED, the guard sanitizes it to evidence-grounded wording.
    """
    mock_llm_output = RiskAndClarificationOutput(
        risks=[
            RiskItem(
                risk_id="RISK-UNGROUNDED",
                requirement_id="REQ-FEDRAMP",
                category="Certification",
                severity="HIGH",
                description="The company does not have FedRAMP certification and failed the federal audit.",
                mitigation_strategy="Seek exception."
            )
        ],
        clarification_questions=[
            ClarificationQuestion(
                q_number=1,
                requirement_id="REQ-FEDRAMP",
                rfp_section_reference="Ref: REQ-FEDRAMP",
                question_text="Because the company lacks FedRAMP certification, can we apply for a waiver?",
                rationale="The company has no FedRAMP certification."
            )
        ]
    )

    req_map = {
        "REQ-FEDRAMP": {
            "req_code": "REQ-FEDRAMP",
            "text": "Bidder must possess FedRAMP High certification.",
            "is_mandatory": True,
            "category": "Certification"
        }
    }
    comp_map = {
        "REQ-FEDRAMP": {
            "req_code": "REQ-FEDRAMP",
            "status": "INFORMATION_REQUIRED"
        }
    }

    validated_risks, validated_clarifs = _apply_programmatic_safety_guard(
        mock_llm_output, req_map, comp_map
    )

    assert len(validated_risks) == 1
    assert "company does not have" not in validated_risks[0].description.lower()
    assert "could not be verified" in validated_risks[0].description.lower()

    assert len(validated_clarifs) == 1
    assert "lacks" not in validated_clarifs[0].question_text.lower()
    assert "could not be verified" in validated_clarifs[0].question_text.lower()


# ==============================================================================
# TEST L: Mandatory INFORMATION_REQUIRED -> HIGH, not CRITICAL
# ==============================================================================
def test_mandatory_information_required_is_high_not_critical():
    """
    RFP: 'Vendor must hold ISO 27001 certification.'
    Company evidence: No ISO 27001 evidence.
    Agent 3: INFORMATION_REQUIRED.
    Expected Agent 4: HIGH, NOT CRITICAL.
    Missing company evidence alone must never be treated as proof that the company lacks
    the certification, nor should it be assigned CRITICAL merely because evidence is missing.
    """
    state: RFPProposalState = {
        "requirements": [
            {
                "req_code": "REQ-SEC-ISO",
                "text": "Vendor must hold ISO 27001 certification.",
                "category": "Certification",
                "is_mandatory": True,
                "source_page": 4,
                "source_section": "Security"
            }
        ],
        "compliance_matrix": [
            {
                "req_code": "REQ-SEC-ISO",
                "status": "INFORMATION_REQUIRED",
                "confidence": 0.0,
                "evidence_text": None,
                "notes": "No ISO 27001 evidence in knowledge base."
            }
        ]
    }

    result = assess_risks_node(state)
    risks = result["risks"]
    clarifs = result["clarification_questions"]

    assert len(risks) == 1
    assert risks[0]["requirement_id"] == "REQ-SEC-ISO"
    assert risks[0]["severity"] == "HIGH", f"Expected HIGH, got {risks[0]['severity']}. Missing evidence alone must NOT be CRITICAL."
    assert "could not be verified" in risks[0]["description"].lower()

    assert len(clarifs) == 1
    assert clarifs[0]["clarification_type"] == "INTERNAL_INFORMATION_REQUEST"
    assert "confirm whether the company currently holds" in clarifs[0]["question_text"].lower() or "confirm" in clarifs[0]["question_text"].lower()


# ==============================================================================
# TEST M: Explicit RFP Disqualification Condition Allows CRITICAL
# ==============================================================================
def test_explicit_disqualification_condition_allows_critical():
    """
    RFP: 'Failure to hold ISO 27001 certification makes the bidder ineligible.'
    Compliance: INFORMATION_REQUIRED.
    Expected Agent 4: CRITICAL is allowed because the RFP explicitly establishes bid eligibility impact.
    """
    state: RFPProposalState = {
        "requirements": [
            {
                "req_code": "REQ-DISQ-01",
                "text": "Failure to hold ISO 27001 certification makes the bidder ineligible.",
                "category": "Certification",
                "is_mandatory": True,
                "source_page": 2,
                "source_section": "Mandatory Eligibility Criteria"
            }
        ],
        "compliance_matrix": [
            {
                "req_code": "REQ-DISQ-01",
                "status": "INFORMATION_REQUIRED",
                "confidence": 0.0,
                "evidence_text": None,
                "notes": "No certificate found in collateral."
            }
        ]
    }

    result = assess_risks_node(state)
    risks = result["risks"]
    assert len(risks) == 1
    assert risks[0]["requirement_id"] == "REQ-DISQ-01"
    assert risks[0]["severity"] == "CRITICAL", "Explicit RFP disqualification clause must trigger CRITICAL severity."


# ==============================================================================
# TEST N: Issuer Clarification vs Internal Information Request Classification
# ==============================================================================
def test_issuer_clarification_classification():
    """
    RFP: 'Vendor shall provide 24/7 support with rapid response.'
    RFP does not specify response/resolution SLA metrics.
    Expected Agent 4:
    - clarification_type: ISSUER_CLARIFICATION
    - Asks client authority about required response and resolution time SLAs
    """
    state: RFPProposalState = {
        "requirements": [
            {
                "req_code": "REQ-SUPP-247",
                "text": "Vendor shall provide 24/7 support with rapid response.",
                "category": "Support",
                "is_mandatory": True,
                "source_page": 11,
                "source_section": "Technical Support"
            }
        ],
        "compliance_matrix": [
            {
                "req_code": "REQ-SUPP-247",
                "status": "INFORMATION_REQUIRED",
                "confidence": 0.0,
                "evidence_text": None,
                "notes": "Clause lacks concrete SLA metrics in RFP."
            }
        ]
    }

    result = assess_risks_node(state)
    clarifs = result["clarification_questions"]

    assert len(clarifs) == 1
    c = clarifs[0]
    assert c["clarification_type"] == "ISSUER_CLARIFICATION"
    assert "sla" in c["question_text"].lower() or "response" in c["question_text"].lower()
    assert "issuing authority" in c["target_owner"].lower() or "authority" in c["target_owner"].lower()


def test_internal_information_request_classification():
    """
    RFP: 'Vendor must hold ISO 27001 certification.'
    Company KB has no evidence.
    Expected Agent 4:
    - clarification_type: INTERNAL_INFORMATION_REQUEST
    - Asks internal team/SME to confirm whether company holds valid ISO 27001
    - Must NOT claim company lacks ISO 27001
    """
    state: RFPProposalState = {
        "requirements": [
            {
                "req_code": "REQ-CERT-ISO",
                "text": "Vendor must hold ISO 27001 certification.",
                "category": "Certification",
                "is_mandatory": True,
                "source_page": 3,
                "source_section": "Compliance"
            }
        ],
        "compliance_matrix": [
            {
                "req_code": "REQ-CERT-ISO",
                "status": "INFORMATION_REQUIRED",
                "confidence": 0.0,
                "evidence_text": None,
                "notes": "No collateral found."
            }
        ]
    }

    result = assess_risks_node(state)
    clarifs = result["clarification_questions"]

    assert len(clarifs) == 1
    c = clarifs[0]
    assert c["clarification_type"] == "INTERNAL_INFORMATION_REQUEST"
    assert "internal" in c["target_owner"].lower()
    assert "confirm whether the company currently holds" in c["question_text"].lower() or "confirm" in c["question_text"].lower()
    assert "does not have" not in c["question_text"].lower()
    assert "lacks" not in c["question_text"].lower()


def test_non_compliant_exception_clarification_type():
    """
    Company evidence explicitly says a required capability is unsupported (NON_COMPLIANT).
    Expected Agent 4:
    - clarification_type: ISSUER_CLARIFICATION
    - Question addresses whether an alternative/exception is permissible
    - Does NOT falsely claim company can comply
    """
    state: RFPProposalState = {
        "requirements": [
            {
                "req_code": "REQ-EXCL-01",
                "text": "Vendor must support mainframe COBOL emulation.",
                "category": "Architecture",
                "is_mandatory": True,
                "source_page": 9,
                "source_section": "Infrastructure"
            }
        ],
        "compliance_matrix": [
            {
                "req_code": "REQ-EXCL-01",
                "status": "NON_COMPLIANT",
                "confidence": 0.95,
                "evidence_text": "COBOL emulation is out of scope and unsupported.",
                "notes": "Unsupported."
            }
        ]
    }

    result = assess_risks_node(state)
    clarifs = result["clarification_questions"]

    assert len(clarifs) == 1
    c = clarifs[0]
    assert c["clarification_type"] == "ISSUER_CLARIFICATION"
    assert "alternative" in c["question_text"].lower() or "exception" in c["question_text"].lower() or "clarify" in c["question_text"].lower()
    assert "company supports" not in c["question_text"].lower()


# ==============================================================================
# CALIBRATED RISK SEVERITY REGRESSION TESTS
# ==============================================================================

def test_unverified_normal_technical_requirement_is_not_high_risk():
    """Verifies that an unverified ordinary technical requirement does NOT automatically become HIGH risk."""
    sev = _calibrate_risk_severity(
        raw_severity=None,
        status="INFORMATION_REQUIRED",
        is_mandatory=True,
        category="Technical",
        req_text="The proposed platform shall provide a web-based appointment management application accessible through Chrome, Edge and Firefox."
    )
    assert sev in ["LOW", "MEDIUM"], f"Expected LOW/MEDIUM for ordinary technical web app, got {sev}"


def test_unverified_ordinary_documentation_and_delivery_not_high_risk():
    """Verifies that unverified ordinary documentation and training requirements do not become HIGH risk."""
    sev_doc = _calibrate_risk_severity(
        raw_severity=None,
        status="INFORMATION_REQUIRED",
        is_mandatory=True,
        category="Documentation",
        req_text="The vendor shall provide a monthly service report covering availability, incidents and support performance."
    )
    assert sev_doc in ["LOW", "MEDIUM"], f"Expected LOW/MEDIUM for periodic service report, got {sev_doc}"

    sev_deliv = _calibrate_risk_severity(
        raw_severity=None,
        status="INFORMATION_REQUIRED",
        is_mandatory=True,
        category="Delivery",
        req_text="The vendor shall conduct administrator and clinic-staff training before production deployment."
    )
    assert sev_deliv in ["LOW", "MEDIUM"], f"Expected LOW/MEDIUM for ordinary staff training, got {sev_deliv}"


def test_unverified_mandatory_iso_certification_remains_high_risk():
    """Verifies that an unverified mandatory ISO/security certification requirement remains HIGH risk."""
    sev = _calibrate_risk_severity(
        raw_severity=None,
        status="INFORMATION_REQUIRED",
        is_mandatory=True,
        category="Certification",
        req_text="The bidder must provide evidence of ISO 27001 or an equivalent recognized information-security certification."
    )
    assert sev == "HIGH", f"Expected HIGH for mandatory ISO certification, got {sev}"


def test_unverified_eligibility_threshold_remains_high_risk():
    """Verifies that unverified mandatory eligibility criteria remain HIGH risk."""
    sev = _calibrate_risk_severity(
        raw_severity=None,
        status="INFORMATION_REQUIRED",
        is_mandatory=True,
        category="Eligibility",
        req_text="The bidder must have at least five years of experience delivering enterprise software or digital platforms."
    )
    assert sev == "HIGH", f"Expected HIGH for mandatory 5-year experience eligibility, got {sev}"


def test_unverified_performance_security_remains_high_risk():
    """Verifies that an unverified performance security/PBG requirement remains HIGH risk."""
    sev = _calibrate_risk_severity(
        raw_severity=None,
        status="INFORMATION_REQUIRED",
        is_mandatory=True,
        category="Contractual",
        req_text="A performance security of 5% of the contract value shall be submitted by the selected vendor in the form specified in the final agreement."
    )
    assert sev == "HIGH", f"Expected HIGH for 5% performance security bond, got {sev}"


def test_unverified_serious_technical_security_and_sla_remains_high_risk():
    """Verifies that technical requirements with critical security controls or strict SLAs remain HIGH risk."""
    # 2FA authentication
    sev_2fa = _calibrate_risk_severity(
        raw_severity=None,
        status="INFORMATION_REQUIRED",
        is_mandatory=True,
        category="Technical",
        req_text="The solution shall support two-factor authentication for privileged administrative accounts."
    )
    assert sev_2fa == "HIGH", f"Expected HIGH for 2FA privileged security requirement, got {sev_2fa}"

    # Strict uptime SLA
    sev_sla = _calibrate_risk_severity(
        raw_severity=None,
        status="INFORMATION_REQUIRED",
        is_mandatory=True,
        category="Technical",
        req_text="The service shall target monthly availability of at least 99.5%, excluding approved scheduled maintenance."
    )
    assert sev_sla == "HIGH", f"Expected HIGH for 99.5% availability SLA, got {sev_sla}"

    # Critical incident response turnaround
    sev_resp = _calibrate_risk_severity(
        raw_severity=None,
        status="INFORMATION_REQUIRED",
        is_mandatory=True,
        category="Technical",
        req_text="Critical production incidents shall receive an initial response within 30 minutes of logging."
    )
    assert sev_resp == "HIGH", f"Expected HIGH for 30-min incident turnaround SLA, got {sev_resp}"


def test_disqualifying_condition_produces_critical_risk():
    """Verifies that an explicit disqualification condition produces CRITICAL risk when unverified."""
    sev = _calibrate_risk_severity(
        raw_severity=None,
        status="INFORMATION_REQUIRED",
        is_mandatory=True,
        category="Technical",
        req_text="Failure to provide FIPS 140-2 validated encryption shall be grounds for automatic disqualification and bid rejection."
    )
    assert sev == "CRITICAL", f"Expected CRITICAL for explicit disqualification clause, got {sev}"


def test_mandatory_alone_does_not_imply_high_risk():
    """Contrasts an ordinary mandatory technical feature (LOW) with a mandatory certification (HIGH)."""
    ordinary_sev = _calibrate_risk_severity(
        raw_severity=None,
        status="INFORMATION_REQUIRED",
        is_mandatory=True,
        category="Technical",
        req_text="A6 The solution shall provide configurable SMS and email notifications for appointment confirmations."
    )
    cert_sev = _calibrate_risk_severity(
        raw_severity=None,
        status="INFORMATION_REQUIRED",
        is_mandatory=True,
        category="Certification",
        req_text="The bidder must provide evidence of ISO 27001 certification."
    )
    assert ordinary_sev in ["LOW", "MEDIUM"]
    assert cert_sev == "HIGH"


def test_information_required_generates_clarification_questions_regardless_of_severity():
    """Verifies that unverified requirements generate targeted clarification questions even when risk is LOW."""
    state: RFPProposalState = {
        "requirements": [
            {
                "req_code": "REQ-NOTIF-01",
                "text": "The platform shall support SMS and email appointment notifications.",
                "category": "Technical",
                "is_mandatory": True,
                "source_page": 2,
                "source_section": "Notifications"
            }
        ],
        "compliance_matrix": [
            {
                "req_code": "REQ-NOTIF-01",
                "status": "INFORMATION_REQUIRED",
                "confidence": 0.0,
                "evidence_text": None,
                "notes": "No SMS gateway collateral found in knowledge base."
            }
        ]
    }
    result = assess_risks_node(state)
    risks = result["risks"]
    clarifs = result["clarification_questions"]

    assert len(risks) == 1
    assert risks[0]["severity"] in ["LOW", "MEDIUM"]
    assert len(clarifs) == 1
    assert clarifs[0]["requirement_id"] == "REQ-NOTIF-01"
    assert clarifs[0]["clarification_type"] == "INTERNAL_INFORMATION_REQUEST"


