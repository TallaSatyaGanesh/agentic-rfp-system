import pytest
import os
from unittest.mock import MagicMock, patch
from app.agents.writer_agent import (
    write_proposal_node,
    _apply_writer_programmatic_safety_guard,
    _sanitize_response_text,
    _validate_claim_evidence_grounding,
    _generate_proposal_draft
)
from app.agents.state import RFPProposalState
from app.models.schemas import (
    ProposalDraft,
    ProposalSection,
    RequirementResponse
)
from app.services.exporter import ProposalExporterService

# ==============================================================================
# TEST A: COMPLIANT response uses only verified evidence
# ==============================================================================
def test_compliant_response_uses_supported_facts():
    state: RFPProposalState = {
        "metadata": {
            "title": "Cloud Infrastructure Modernization",
            "issuer": "Department of Transportation",
            "submission_deadline": "November 30, 2026"
        },
        "requirements": [
            {
                "req_code": "REQ-BACKUP-01",
                "text": "The platform must support automated daily encrypted database backups.",
                "category": "Technical",
                "is_mandatory": True,
                "source_page": 6,
                "source_section": "Disaster Recovery"
            }
        ],
        "compliance_matrix": [
            {
                "req_code": "REQ-BACKUP-01",
                "status": "COMPLIANT",
                "confidence": 0.95,
                "evidence_text": "Platform performs automated daily encrypted backups retained for 30 days.",
                "company_source_doc": "Acme Backup and Storage Whitepaper",
                "company_doc_id": "doc_backup_01",
                "chunk_id": "chunk_backup_0",
                "citations": [
                    {
                        "document_title": "Acme Backup and Storage Whitepaper",
                        "company_doc_id": "doc_backup_01",
                        "snippet": "Platform performs automated daily encrypted backups retained for 30 days."
                    }
                ]
            }
        ],
        "risks": [],
        "clarification_questions": [],
        "current_version": 0,
        "proposal_drafts": []
    }

    result = write_proposal_node(state)
    drafts = result["proposal_drafts"]
    assert len(drafts) == 1
    draft = drafts[0]

    responses = draft["requirement_responses"]
    assert len(responses) == 1
    resp = responses[0]
    assert resp["requirement_id"] == "REQ-BACKUP-01"
    assert resp["compliance_status"] == "COMPLIANT"
    assert resp["response_type"] == "COMPLIANT_RESPONSE"
    assert "automated daily encrypted backups" in resp["response"].lower() or "supports" in resp["response"].lower()
    assert len(resp["citations"]) == 1
    assert resp["citations"][0]["company_doc_id"] == "doc_backup_01"


# ==============================================================================
# TEST B: PARTIALLY_COMPLIANT response explicitly preserves limitation
# ==============================================================================
def test_partially_compliant_response_preserves_limitation():
    state: RFPProposalState = {
        "metadata": {"title": "Enterprise Support RFP"},
        "requirements": [
            {
                "req_code": "REQ-SUPP-01",
                "text": "Vendor must provide 24/7 dedicated phone and email support.",
                "category": "Support",
                "is_mandatory": True,
                "source_page": 14,
                "source_section": "Operations"
            }
        ],
        "compliance_matrix": [
            {
                "req_code": "REQ-SUPP-01",
                "status": "PARTIALLY_COMPLIANT",
                "confidence": 0.85,
                "evidence_text": "Email support is 24/7; phone support is available during business hours 8am-6pm EST.",
                "notes": "24/7 email supported; phone support is business hours only.",
                "company_source_doc": "Support Service SLA Guide",
                "citations": []
            }
        ],
        "risks": [],
        "clarification_questions": [],
        "current_version": 0,
        "proposal_drafts": []
    }

    result = write_proposal_node(state)
    resp = result["proposal_drafts"][0]["requirement_responses"][0]

    assert resp["requirement_id"] == "REQ-SUPP-01"
    assert resp["compliance_status"] == "PARTIALLY_COMPLIANT"
    assert resp["response_type"] == "PARTIAL_RESPONSE"
    # Limitation must be clearly stated
    assert "business hours" in resp["response"].lower() or "limitation" in resp["response"].lower() or "partial" in resp["response"].lower()


# ==============================================================================
# TEST C: NON_COMPLIANT response uses exception treatment, no false commitment
# ==============================================================================
def test_non_compliant_response_uses_exception_treatment():
    state: RFPProposalState = {
        "metadata": {"title": "Legacy Modernization"},
        "requirements": [
            {
                "req_code": "REQ-LEGACY-01",
                "text": "Platform must support native IBM 3270 mainframe terminals.",
                "category": "Architecture",
                "is_mandatory": True,
                "source_page": 8,
                "source_section": "Integration"
            }
        ],
        "compliance_matrix": [
            {
                "req_code": "REQ-LEGACY-01",
                "status": "NON_COMPLIANT",
                "confidence": 0.95,
                "evidence_text": "IBM 3270 emulation is unsupported and out of product scope.",
                "notes": "Unsupported scope."
            }
        ],
        "risks": [],
        "clarification_questions": [],
        "current_version": 0,
        "proposal_drafts": []
    }

    result = write_proposal_node(state)
    resp = result["proposal_drafts"][0]["requirement_responses"][0]

    assert resp["requirement_id"] == "REQ-LEGACY-01"
    assert resp["compliance_status"] == "NON_COMPLIANT"
    assert resp["response_type"] == "EXCEPTION_RESPONSE"
    assert "exception" in resp["response"].lower() or "variance" in resp["response"].lower() or "not currently supported" in resp["response"].lower()
    assert "we support 3270" not in resp["response"].lower()


# ==============================================================================
# TEST D: INFORMATION_REQUIRED response preserves uncertainty
# ==============================================================================
def test_information_required_response_no_invented_facts():
    state: RFPProposalState = {
        "metadata": {"title": "Multi-Region Cloud RFP"},
        "requirements": [
            {
                "req_code": "REQ-DR-99",
                "text": "Multi-region RTO must be strictly less than 15 minutes.",
                "category": "Architecture",
                "is_mandatory": True,
                "source_page": 10,
                "source_section": "SLA"
            }
        ],
        "compliance_matrix": [
            {
                "req_code": "REQ-DR-99",
                "status": "INFORMATION_REQUIRED",
                "confidence": 0.0,
                "evidence_text": None,
                "notes": "No verified RTO benchmark in collateral."
            }
        ],
        "risks": [],
        "clarification_questions": [],
        "current_version": 0,
        "proposal_drafts": []
    }

    result = write_proposal_node(state)
    resp = result["proposal_drafts"][0]["requirement_responses"][0]

    assert resp["requirement_id"] == "REQ-DR-99"
    assert resp["compliance_status"] == "INFORMATION_REQUIRED"
    assert resp["response_type"] == "INFORMATION_REQUIRED_RESPONSE"
    assert "information required" in resp["response"].lower() or "unconfirmed" in resp["response"].lower()
    # Must not invent an RTO promise
    assert "guarantee" not in resp["response"].lower()


# ==============================================================================
# TEST E: Certification Hallucination Prevention
# ==============================================================================
def test_certification_hallucination_prevention():
    state: RFPProposalState = {
        "metadata": {"title": "Federal Security Tender"},
        "requirements": [
            {
                "req_code": "REQ-FEDRAMP-HIGH",
                "text": "Bidder must possess active FedRAMP High certification.",
                "category": "Certification",
                "is_mandatory": True,
                "source_page": 2,
                "source_section": "Security"
            }
        ],
        "compliance_matrix": [
            {
                "req_code": "REQ-FEDRAMP-HIGH",
                "status": "INFORMATION_REQUIRED",
                "confidence": 0.0,
                "evidence_text": None,
                "notes": "No FedRAMP certificate in collateral."
            }
        ],
        "risks": [],
        "clarification_questions": [],
        "current_version": 0,
        "proposal_drafts": []
    }

    result = write_proposal_node(state)
    draft = result["proposal_drafts"][0]
    resp = draft["requirement_responses"][0]

    assert resp["compliance_status"] == "INFORMATION_REQUIRED"
    assert "we hold fedramp" not in resp["response"].lower()
    assert "certified" not in resp["response"].lower() or "unconfirmed" in resp["response"].lower() or "certificate" in resp["response"].lower()
    assert "INFORMATION REQUIRED" in draft["full_markdown"]


# ==============================================================================
# TEST F: Unsupported capability hallucination sanitized by programmatic guard
# ==============================================================================
def test_unsupported_capability_hallucination_sanitized():
    req_map = {
        "REQ-QUANTUM-01": {
            "req_code": "REQ-QUANTUM-01",
            "text": "Must integrate with quantum key distribution hardware.",
            "is_mandatory": True,
            "category": "Cryptography",
            "source_page": 19,
            "source_section": "Security"
        }
    }
    comp_map = {
        "REQ-QUANTUM-01": {
            "req_code": "REQ-QUANTUM-01",
            "status": "INFORMATION_REQUIRED",
            "evidence_text": None
        }
    }

    # Simulate LLM hallucinating full compliance and commitment
    hallucinated_draft = ProposalDraft(
        version=1,
        title="Hallucinated Proposal",
        executive_summary="Summary",
        sections=[],
        requirement_responses=[
            RequirementResponse(
                requirement_id="REQ-QUANTUM-01",
                requirement_text="Must integrate with quantum key distribution hardware.",
                category="Cryptography",
                is_mandatory=True,
                compliance_status="COMPLIANT",  # Hallucinated!
                response_type="COMPLIANT_RESPONSE",  # Hallucinated!
                response="We guarantee 100% compliance and our platform fully supports quantum key distribution hardware out of the box."  # Hallucinated!
            )
        ]
    )

    safe_draft = _apply_writer_programmatic_safety_guard(
        llm_draft=hallucinated_draft,
        req_map=req_map,
        comp_map=comp_map,
        risk_map={},
        clarif_map={},
        metadata={"title": "Test Tender"},
        version=1
    )

    safe_resp = safe_draft.requirement_responses[0]
    assert safe_resp.compliance_status == "INFORMATION_REQUIRED", "Safety guard must revert status to Agent 3 finding"
    assert safe_resp.response_type == "INFORMATION_REQUIRED_RESPONSE"
    assert "guarantee" not in safe_resp.response.lower()
    assert "information required" in safe_resp.response.lower()


# ==============================================================================
# TEST G: Citation and Metadata Preservation
# ==============================================================================
def test_citation_preservation():
    state: RFPProposalState = {
        "metadata": {"title": "Enterprise Cloud"},
        "requirements": [
            {
                "req_code": "REQ-ENC-01",
                "text": "All data must be encrypted with AES-256.",
                "category": "Security",
                "is_mandatory": True,
                "source_page": 12,
                "source_section": "Encryption"
            }
        ],
        "compliance_matrix": [
            {
                "req_code": "REQ-ENC-01",
                "status": "COMPLIANT",
                "confidence": 0.98,
                "evidence_text": "FIPS 140-2 validated AES-256 encryption at rest and in transit.",
                "company_source_doc": "Enterprise Security Standards",
                "company_doc_id": "doc_sec_01",
                "chunk_id": "sec_chunk_4",
                "citations": [
                    {
                        "document_title": "Enterprise Security Standards",
                        "company_doc_id": "doc_sec_01",
                        "chunk_id": "sec_chunk_4",
                        "snippet": "FIPS 140-2 validated AES-256 encryption at rest and in transit."
                    }
                ]
            }
        ],
        "risks": [],
        "clarification_questions": [],
        "current_version": 0,
        "proposal_drafts": []
    }

    result = write_proposal_node(state)
    resp = result["proposal_drafts"][0]["requirement_responses"][0]

    assert resp["requirement_id"] == "REQ-ENC-01"
    assert resp["company_doc_id"] == "doc_sec_01"
    assert resp["chunk_id"] == "sec_chunk_4"
    assert resp["source_page"] == 12
    assert resp["source_section"] == "Encryption"
    assert len(resp["citations"]) == 1
    assert resp["citations"][0]["chunk_id"] == "sec_chunk_4"


# ==============================================================================
# TEST H: Requirement Traceability
# ==============================================================================
def test_requirement_traceability():
    state: RFPProposalState = {
        "metadata": {"title": "Traceability Test"},
        "requirements": [
            {"req_code": "REQ-01", "text": "Spec 1", "category": "Tech", "is_mandatory": True, "source_page": 1},
            {"req_code": "REQ-02", "text": "Spec 2", "category": "Legal", "is_mandatory": False, "source_page": 2}
        ],
        "compliance_matrix": [
            {"req_code": "REQ-01", "status": "COMPLIANT", "evidence_text": "Spec 1 supported."},
            {"req_code": "REQ-02", "status": "INFORMATION_REQUIRED"}
        ],
        "risks": [],
        "clarification_questions": [],
        "current_version": 0,
        "proposal_drafts": []
    }

    result = write_proposal_node(state)
    responses = result["proposal_drafts"][0]["requirement_responses"]

    req_ids = [r["requirement_id"] for r in responses]
    assert req_ids == ["REQ-01", "REQ-02"]


# ==============================================================================
# TEST I: Risk & Clarification Integration
# ==============================================================================
def test_risk_and_clarification_integration():
    state: RFPProposalState = {
        "metadata": {"title": "Integrated Risk Tender"},
        "requirements": [
            {
                "req_code": "REQ-LIABILITY-01",
                "text": "Vendor agrees to unlimited consequential damages.",
                "category": "Contractual",
                "is_mandatory": True,
                "source_page": 25,
                "source_section": "Terms"
            }
        ],
        "compliance_matrix": [
            {
                "req_code": "REQ-LIABILITY-01",
                "status": "NON_COMPLIANT",
                "notes": "Standard policy caps liability at 12 months fees."
            }
        ],
        "risks": [
            {
                "requirement_id": "REQ-LIABILITY-01",
                "severity": "CRITICAL",
                "title": "Severe Financial Liability Exposure",
                "mitigation_strategy": "Propose standard mutual limitation of liability cap."
            }
        ],
        "clarification_questions": [
            {
                "requirement_id": "REQ-LIABILITY-01",
                "clarification_type": "ISSUER_CLARIFICATION",
                "question_text": "Will the Authority accept a standard mutual liability cap?"
            }
        ],
        "current_version": 0,
        "proposal_drafts": []
    }

    result = write_proposal_node(state)
    resp = result["proposal_drafts"][0]["requirement_responses"][0]

    assert resp["requirement_id"] == "REQ-LIABILITY-01"
    assert resp["risk_summary"] is not None
    assert "CRITICAL" in resp["risk_summary"]
    assert resp["clarification_required"] is not None
    assert "liability cap" in resp["clarification_required"].lower()


# ==============================================================================
# TEST J: Multiple Requirements Isolation
# ==============================================================================
def test_multiple_requirements_isolation():
    state: RFPProposalState = {
        "metadata": {"title": "Multi-Requirement Isolation Test"},
        "requirements": [
            {"req_code": "REQ-A", "text": "Requirement A - PostgreSQL database", "category": "Tech", "is_mandatory": True},
            {"req_code": "REQ-B", "text": "Requirement B - ISO 27001 certificate", "category": "Cert", "is_mandatory": True},
            {"req_code": "REQ-C", "text": "Requirement C - Mainframe COBOL support", "category": "Arch", "is_mandatory": True}
        ],
        "compliance_matrix": [
            {"req_code": "REQ-A", "status": "COMPLIANT", "evidence_text": "Managed PostgreSQL 15 fully supported."},
            {"req_code": "REQ-B", "status": "INFORMATION_REQUIRED", "notes": "Missing certificate."},
            {"req_code": "REQ-C", "status": "NON_COMPLIANT", "evidence_text": "Mainframe COBOL unsupported."}
        ],
        "risks": [],
        "clarification_questions": [],
        "current_version": 0,
        "proposal_drafts": []
    }

    result = write_proposal_node(state)
    responses = result["proposal_drafts"][0]["requirement_responses"]

    assert len(responses) == 3
    resp_a = [r for r in responses if r["requirement_id"] == "REQ-A"][0]
    resp_b = [r for r in responses if r["requirement_id"] == "REQ-B"][0]
    resp_c = [r for r in responses if r["requirement_id"] == "REQ-C"][0]

    assert resp_a["response_type"] == "COMPLIANT_RESPONSE"
    assert resp_b["response_type"] == "INFORMATION_REQUIRED_RESPONSE"
    assert resp_c["response_type"] == "EXCEPTION_RESPONSE"

    # Ensure no evidence leakage between responses
    assert "postgresql" in resp_a["response"].lower()
    assert "postgresql" not in resp_b["response"].lower()
    assert "postgresql" not in resp_c["response"].lower()


# ==============================================================================
# TEST K: LLM Failure Fallback
# ==============================================================================
def test_llm_failure_fallback():
    failing_llm = MagicMock()
    failing_llm.with_structured_output.side_effect = RuntimeError("OpenAI API Timeout")

    with patch("app.agents.writer_agent.LLMFactory.get_chat_model", return_value=failing_llm):
        state: RFPProposalState = {
            "metadata": {"title": "Fallback Test RFP"},
            "requirements": [
                {"req_code": "REQ-FB-01", "text": "Automated backups.", "is_mandatory": True, "category": "Tech"}
            ],
            "compliance_matrix": [
                {"req_code": "REQ-FB-01", "status": "COMPLIANT", "evidence_text": "Daily backups supported."}
            ],
            "risks": [],
            "clarification_questions": [],
            "current_version": 0,
            "proposal_drafts": []
        }

        result = write_proposal_node(state)
        draft = result["proposal_drafts"][0]
        assert len(draft["sections"]) == 5
        assert len(draft["requirement_responses"]) == 1
        assert draft["requirement_responses"][0]["response_type"] == "COMPLIANT_RESPONSE"


# ==============================================================================
# TEST L: Compliance Status Immutability
# ==============================================================================
def test_compliance_status_immutability():
    req_map = {
        "REQ-IMMUTABLE": {
            "req_code": "REQ-IMMUTABLE",
            "text": "Strict specification.",
            "is_mandatory": True,
            "category": "Tech"
        }
    }
    comp_map = {
        "REQ-IMMUTABLE": {
            "req_code": "REQ-IMMUTABLE",
            "status": "NON_COMPLIANT",
            "evidence_text": "Unsupported."
        }
    }

    # Attempt to pass an LLM response asserting COMPLIANT for a NON_COMPLIANT item
    mock_draft = ProposalDraft(
        version=1,
        title="Test",
        executive_summary="Summary",
        sections=[],
        requirement_responses=[
            RequirementResponse(
                requirement_id="REQ-IMMUTABLE",
                requirement_text="Strict specification.",
                category="Tech",
                is_mandatory=True,
                compliance_status="COMPLIANT",  # Illegal override!
                response_type="COMPLIANT_RESPONSE",
                response="We comply."
            )
        ]
    )

    safe_draft = _apply_writer_programmatic_safety_guard(
        llm_draft=mock_draft,
        req_map=req_map,
        comp_map=comp_map,
        risk_map={},
        clarif_map={},
        metadata={"title": "Test"},
        version=1
    )

    assert safe_draft.requirement_responses[0].compliance_status == "NON_COMPLIANT"
    assert safe_draft.requirement_responses[0].response_type == "EXCEPTION_RESPONSE"


# ==============================================================================
# TEST M: No Unsupported Commitments (Pricing, SLAs, References)
# ==============================================================================
def test_no_unsupported_commitment():
    sanitized = _sanitize_response_text(
        text="We guarantee 99.999% SLA uptime, offer over 20 years of experience, and a fixed price of $50,000.",
        status="INFORMATION_REQUIRED",
        evidence_text=None,
        notes=None,
        req_code="REQ-CLAIM"
    )

    assert "fixed price" not in sanitized.lower()
    assert "years of experience" not in sanitized.lower()
    assert "information required" in sanitized.lower()


# ==============================================================================
# TEST N: DOCX Generation from Structured Proposal
# ==============================================================================
def test_docx_generation_from_structured_proposal(tmp_path):
    state: RFPProposalState = {
        "metadata": {
            "title": "DOCX Export Validation Tender",
            "issuer": "Global Logistics Corp",
            "submission_deadline": "December 15, 2026"
        },
        "requirements": [
            {"req_code": "REQ-D-01", "text": "Daily backups.", "category": "Tech", "is_mandatory": True, "source_page": 3},
            {"req_code": "REQ-D-02", "text": "ISO 27001 cert.", "category": "Cert", "is_mandatory": True, "source_page": 5},
            {"req_code": "REQ-D-03", "text": "24/7 Phone.", "category": "Support", "is_mandatory": False, "source_page": 8},
            {"req_code": "REQ-D-04", "text": "COBOL terminal.", "category": "Arch", "is_mandatory": False, "source_page": 9}
        ],
        "compliance_matrix": [
            {"req_code": "REQ-D-01", "status": "COMPLIANT", "evidence_text": "Automated backups supported."},
            {"req_code": "REQ-D-02", "status": "INFORMATION_REQUIRED"},
            {"req_code": "REQ-D-03", "status": "PARTIALLY_COMPLIANT", "notes": "Business hours phone only."},
            {"req_code": "REQ-D-04", "status": "NON_COMPLIANT", "evidence_text": "COBOL unsupported."}
        ],
        "risks": [],
        "clarification_questions": [],
        "current_version": 0,
        "proposal_drafts": []
    }

    result = write_proposal_node(state)
    draft = result["proposal_drafts"][0]

    out_file = os.path.join(tmp_path, "test_output_proposal.docx")
    exported_path = ProposalExporterService.export_to_docx(
        rfp_metadata=state["metadata"],
        proposal_draft=draft,
        compliance_matrix=state["compliance_matrix"],
        risks=state["risks"],
        clarifications=state["clarification_questions"],
        output_path=out_file
    )

    assert os.path.exists(exported_path)
    assert os.path.getsize(exported_path) > 1000


# ==============================================================================
# REMEDIATION TEST A: Unsupported capability without forbidden regex
# ==============================================================================
def test_unsupported_capability_without_forbidden_regex():
    """
    Evidence: 'Company provides automated daily database backups.'
    LLM response: 'Our platform provides automated cross-region disaster recovery.'
    Must be detected as ungrounded even though it lacks explicit forbidden regex patterns,
    and safely replaced with the verified evidence.
    """
    req_map = {
        "REQ-BACKUP-99": {
            "req_code": "REQ-BACKUP-99",
            "text": "The platform must support automated daily database backups.",
            "category": "Technical",
            "is_mandatory": True,
            "source_page": 4,
            "source_section": "Storage"
        }
    }
    comp_map = {
        "REQ-BACKUP-99": {
            "req_code": "REQ-BACKUP-99",
            "status": "COMPLIANT",
            "evidence_text": "Company provides automated daily database backups.",
            "company_source_doc": "Acme Storage Specification",
            "company_doc_id": "doc_storage_01"
        }
    }

    mock_draft = ProposalDraft(
        version=1,
        title="Disaster Recovery Proposal",
        executive_summary="Summary",
        sections=[],
        requirement_responses=[
            RequirementResponse(
                requirement_id="REQ-BACKUP-99",
                requirement_text="The platform must support automated daily database backups.",
                category="Technical",
                is_mandatory=True,
                compliance_status="COMPLIANT",
                response_type="COMPLIANT_RESPONSE",
                response="Our platform provides automated cross-region disaster recovery."
            )
        ]
    )

    safe_draft = _apply_writer_programmatic_safety_guard(
        llm_draft=mock_draft,
        req_map=req_map,
        comp_map=comp_map,
        risk_map={},
        clarif_map={},
        metadata={"title": "Test RFP"},
        version=1
    )

    safe_resp = safe_draft.requirement_responses[0]
    assert safe_resp.compliance_status == "COMPLIANT"
    assert safe_resp.response_type == "COMPLIANT_RESPONSE"
    assert "cross-region" not in safe_resp.response.lower()
    assert "disaster" not in safe_resp.response.lower()
    assert "recovery" not in safe_resp.response.lower()
    assert "automated daily database backups" in safe_resp.response.lower()


# ==============================================================================
# REMEDIATION TEST B: Supported paraphrase accepted without false positive
# ==============================================================================
def test_supported_paraphrase_accepted():
    """
    Evidence: 'Platform performs automated daily encrypted backups retained for 30 days.'
    Requirement: 'The platform must support automated daily encrypted database backups.'
    LLM response: 'The proposed solution provides automated daily database backup capability.'
    The validator must recognize this as a valid grounded paraphrase and preserve it.
    """
    is_valid, reason = _validate_claim_evidence_grounding(
        response_text="The proposed solution provides automated daily database backup capability.",
        status="COMPLIANT",
        evidence_text="Platform performs automated daily encrypted backups retained for 30 days.",
        notes=None,
        req_text="The platform must support automated daily encrypted database backups.",
        citations=[],
        company_source_doc="Acme Backup Architecture"
    )
    assert is_valid is True, f"Legitimate paraphrase should be accepted, but was rejected: {reason}"


# ==============================================================================
# REMEDIATION TEST C: Unsupported certification on INFORMATION_REQUIRED
# ==============================================================================
def test_unsupported_certification_on_information_required():
    """
    Requirement: 'Vendor must possess ISO 27001 certification.'
    Evidence: None (status: INFORMATION_REQUIRED).
    LLM response: 'Our company is ISO 27001 certified and complies with all security guidelines.'
    Must be rejected and replaced with safe unconfirmed / verification-required response.
    """
    req_map = {
        "REQ-CERT-01": {
            "req_code": "REQ-CERT-01",
            "text": "Vendor must possess ISO 27001 certification.",
            "category": "Certification",
            "is_mandatory": True,
            "source_page": 7,
            "source_section": "Compliance"
        }
    }
    comp_map = {
        "REQ-CERT-01": {
            "req_code": "REQ-CERT-01",
            "status": "INFORMATION_REQUIRED",
            "evidence_text": None
        }
    }

    mock_draft = ProposalDraft(
        version=1,
        title="Security Proposal",
        executive_summary="Summary",
        sections=[],
        requirement_responses=[
            RequirementResponse(
                requirement_id="REQ-CERT-01",
                requirement_text="Vendor must possess ISO 27001 certification.",
                category="Certification",
                is_mandatory=True,
                compliance_status="INFORMATION_REQUIRED",
                response_type="INFORMATION_REQUIRED_RESPONSE",
                response="Our company is ISO 27001 certified and complies with all security guidelines."
            )
        ]
    )

    safe_draft = _apply_writer_programmatic_safety_guard(
        llm_draft=mock_draft,
        req_map=req_map,
        comp_map=comp_map,
        risk_map={},
        clarif_map={},
        metadata={"title": "Test RFP"},
        version=1
    )

    safe_resp = safe_draft.requirement_responses[0]
    assert safe_resp.compliance_status == "INFORMATION_REQUIRED"
    assert safe_resp.response_type == "INFORMATION_REQUIRED_RESPONSE"
    assert "our company is iso 27001 certified" not in safe_resp.response.lower()
    assert "information required" in safe_resp.response.lower() or "unconfirmed" in safe_resp.response.lower()


# ==============================================================================
# REMEDIATION TEST D: Unsupported SLA claim rejected
# ==============================================================================
def test_unsupported_sla_rejected():
    """
    Requirement: 'Vendor must respond to incidents within 15 minutes 24/7.'
    Evidence: 'Support team is available during standard business hours 8am-5pm EST.'
    LLM response: 'We guarantee 24/7 response within 15 minutes.'
    Must be rejected because 24/7 and 15 minutes are absent from company evidence.
    """
    is_valid, reason = _validate_claim_evidence_grounding(
        response_text="We guarantee 24/7 response within 15 minutes.",
        status="COMPLIANT",
        evidence_text="Support team is available during standard business hours 8am-5pm EST.",
        notes=None,
        req_text="Vendor must respond to incidents within 15 minutes 24/7.",
        citations=[],
        company_source_doc="Standard Support SLA"
    )
    assert is_valid is False
    assert "ungrounded sla or metric" in reason.lower()


# ==============================================================================
# REMEDIATION TEST E: Partial compliance limitation preservation
# ==============================================================================
def test_partially_compliant_limitation_preservation():
    """
    Requirement: 'Vendor must provide 24/7 dedicated phone and email support.'
    Evidence: 'Email support is 24/7; phone support is available during business hours 8am-6pm EST.'
    Notes: '24/7 email supported; phone support is business hours only.'
    LLM response: 'We provide complete 24/7 phone and email support across all enterprise channels.'
    Must be rejected for claiming complete 24/7 support and omitting business hours limitation.
    """
    req_map = {
        "REQ-SUPP-PARTIAL": {
            "req_code": "REQ-SUPP-PARTIAL",
            "text": "Vendor must provide 24/7 dedicated phone and email support.",
            "category": "Support",
            "is_mandatory": True,
            "source_page": 10,
            "source_section": "Operations"
        }
    }
    comp_map = {
        "REQ-SUPP-PARTIAL": {
            "req_code": "REQ-SUPP-PARTIAL",
            "status": "PARTIALLY_COMPLIANT",
            "evidence_text": "Email support is 24/7; phone support is available during business hours 8am-6pm EST.",
            "notes": "24/7 email supported; phone support is business hours only."
        }
    }

    mock_draft = ProposalDraft(
        version=1,
        title="Support Proposal",
        executive_summary="Summary",
        sections=[],
        requirement_responses=[
            RequirementResponse(
                requirement_id="REQ-SUPP-PARTIAL",
                requirement_text="Vendor must provide 24/7 dedicated phone and email support.",
                category="Support",
                is_mandatory=True,
                compliance_status="PARTIALLY_COMPLIANT",
                response_type="PARTIAL_RESPONSE",
                response="We provide complete 24/7 phone and email support across all enterprise channels."
            )
        ]
    )

    safe_draft = _apply_writer_programmatic_safety_guard(
        llm_draft=mock_draft,
        req_map=req_map,
        comp_map=comp_map,
        risk_map={},
        clarif_map={},
        metadata={"title": "Test RFP"},
        version=1
    )

    safe_resp = safe_draft.requirement_responses[0]
    assert safe_resp.compliance_status == "PARTIALLY_COMPLIANT"
    assert safe_resp.response_type == "PARTIAL_RESPONSE"
    assert "complete 24/7" not in safe_resp.response.lower()
    assert "business hours" in safe_resp.response.lower() or "limitation" in safe_resp.response.lower()


# ==============================================================================
# REMEDIATION TEST F: Citation and provenance preservation after replacement
# ==============================================================================
def test_citation_preservation_after_replacement():
    """
    When an LLM response contains an ungrounded claim and is replaced by the safe guard,
    the citations, company_doc_id, chunk_id, source_page, and source_section MUST remain intact.
    """
    req_map = {
        "REQ-CRYPTO-01": {
            "req_code": "REQ-CRYPTO-01",
            "text": "All customer data must be encrypted with AES-256.",
            "category": "Security",
            "is_mandatory": True,
            "source_page": 12,
            "source_section": "Encryption"
        }
    }
    comp_map = {
        "REQ-CRYPTO-01": {
            "req_code": "REQ-CRYPTO-01",
            "status": "COMPLIANT",
            "evidence_text": "Platform supports AES-256 encryption at rest and in transit.",
            "company_source_doc": "Enterprise Security Guide",
            "company_doc_id": "doc_sec_01",
            "chunk_id": "sec_chunk_4",
            "citations": [
                {
                    "document_title": "Enterprise Security Guide",
                    "company_doc_id": "doc_sec_01",
                    "chunk_id": "sec_chunk_4",
                    "snippet": "Platform supports AES-256 encryption at rest and in transit."
                }
            ]
        }
    }

    # Response introduces ungrounded quantum encryption capability
    mock_draft = ProposalDraft(
        version=1,
        title="Crypto Proposal",
        executive_summary="Summary",
        sections=[],
        requirement_responses=[
            RequirementResponse(
                requirement_id="REQ-CRYPTO-01",
                requirement_text="All customer data must be encrypted with AES-256.",
                category="Security",
                is_mandatory=True,
                compliance_status="COMPLIANT",
                response_type="COMPLIANT_RESPONSE",
                response="Our platform provides automated cross-region disaster recovery and quantum encryption."
            )
        ]
    )

    safe_draft = _apply_writer_programmatic_safety_guard(
        llm_draft=mock_draft,
        req_map=req_map,
        comp_map=comp_map,
        risk_map={},
        clarif_map={},
        metadata={"title": "Test RFP"},
        version=1
    )

    safe_resp = safe_draft.requirement_responses[0]
    assert safe_resp.compliance_status == "COMPLIANT"
    assert safe_resp.response_type == "COMPLIANT_RESPONSE"
    assert "quantum" not in safe_resp.response.lower()
    assert "cross-region" not in safe_resp.response.lower()
    # Metadata and citations must be completely preserved
    assert safe_resp.company_doc_id == "doc_sec_01"
    assert safe_resp.chunk_id == "sec_chunk_4"
    assert safe_resp.source_page == 12
    assert safe_resp.source_section == "Encryption"
    assert len(safe_resp.citations) == 1
    assert safe_resp.citations[0]["company_doc_id"] == "doc_sec_01"
    assert safe_resp.citations[0]["chunk_id"] == "sec_chunk_4"

