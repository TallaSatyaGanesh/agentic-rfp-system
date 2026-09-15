import pytest
from unittest.mock import MagicMock, patch
from app.agents.compliance_agent import (
    analyze_compliance_node,
    _apply_programmatic_safety_guard,
    _fallback_compliance_eval
)
from app.agents.state import RFPProposalState
from app.models.schemas import ComplianceItem
from app.rag.retriever import KnowledgeBaseRetriever
from app.core.config import settings

@pytest.fixture
def seeded_retriever():
    """
    Sets up a KnowledgeBaseRetriever seeded with specific company collateral
    representing verified capabilities, partial workarounds, and explicit limitations.
    """
    retriever = KnowledgeBaseRetriever()
    
    # 1. Cloud Capabilities (Fully compliant)
    retriever.index_document(
        doc_id="comp_cloud_test_01",
        title="Enterprise Cloud Infrastructure Guide",
        filename="cloud_guide.txt",
        content=(
            "Acme Cloud guarantees automated daily database backups with 30-day retention and multi-region replication. "
            "All cloud services operate with a 99.95% monthly uptime SLA backed by financial credits. "
            "Data in transit is encrypted using TLS 1.3 and data at rest is secured with AES-256 GCM."
        ),
        category="Technical",
        page_number=4,
        section="Backup and Availability"
    )

    # 2. Hybrid AD Connector (Partially compliant / limitation)
    retriever.index_document(
        doc_id="comp_id_test_02",
        title="Identity & Access Management Collateral",
        filename="identity_collateral.txt",
        content=(
            "Acme IAM natively supports SAML 2.0 and OIDC for federated single sign-on. "
            "Legacy on-premise Active Directory sync is partially supported via custom LDAP connector workaround. "
            "Full bi-directional Kerberos sync is not supported and is out of scope."
        ),
        category="Security",
        page_number=8,
        section="Directory Federation"
    )

    # 3. Mainframe Legacy (Explicitly unsupported)
    retriever.index_document(
        doc_id="comp_legacy_test_03",
        title="Architecture Scope and Exclusions",
        filename="architecture_exclusions.txt",
        content=(
            "Mainframe COBOL emulation and IBM z/OS integration is out of scope and explicitly excluded from the platform. "
            "Acme Cloud does not support and cannot support legacy 3270 terminal emulation."
        ),
        category="Architecture",
        page_number=12,
        section="Exclusions"
    )

    return retriever


# ==============================================================================
# TEST A: COMPLIANT with verified company evidence
# ==============================================================================
def test_compliant_with_company_evidence(seeded_retriever):
    """
    Verifies that a requirement directly supported by company collateral is evaluated
    as COMPLIANT with appropriate citations and traceability.
    """
    state: RFPProposalState = {
        "requirements": [
            {
                "req_code": "REQ-TECH-001",
                "text": "The platform must support automated daily database backups with multi-region replication and 30-day retention.",
                "category": "Technical"
            }
        ]
    }

    result = analyze_compliance_node(state)
    matrix = result["compliance_matrix"]

    assert len(matrix) == 1
    item = matrix[0]
    assert item["req_code"] == "REQ-TECH-001"
    assert item["status"] == "COMPLIANT"
    assert item["company_doc_id"] == "comp_cloud_test_01"
    assert item["source_page"] == 4
    assert item["source_section"] == "Backup and Availability"
    assert "automated daily database backups" in item["evidence_text"]
    assert len(item["citations"]) >= 1
    assert item["similarity_score"] >= settings.SIMILARITY_THRESHOLD


# ==============================================================================
# TEST B: PARTIALLY_COMPLIANT with limitations/workarounds
# ==============================================================================
def test_partially_compliant_with_limitations(seeded_retriever):
    """
    Verifies that when company evidence mentions partial support or workarounds,
    the requirement is classified as PARTIALLY_COMPLIANT.
    """
    state: RFPProposalState = {
        "requirements": [
            {
                "req_code": "REQ-SEC-002",
                "text": "Must integrate with legacy on-premise Active Directory for directory sync.",
                "category": "Security"
            }
        ]
    }

    result = analyze_compliance_node(state)
    matrix = result["compliance_matrix"]

    assert len(matrix) == 1
    item = matrix[0]
    assert item["req_code"] == "REQ-SEC-002"
    assert item["status"] == "PARTIALLY_COMPLIANT"
    assert "partially supported" in item["evidence_text"].lower() or "workaround" in item["evidence_text"].lower()
    assert item["company_doc_id"] == "comp_id_test_02"
    assert item["source_page"] == 8


# ==============================================================================
# TEST C: NON_COMPLIANT with explicit unsupported statement
# ==============================================================================
def test_non_compliant_with_explicit_unsupported(seeded_retriever):
    """
    Verifies that when company evidence explicitly states a capability is unsupported or out of scope,
    it is classified as NON_COMPLIANT.
    """
    state: RFPProposalState = {
        "requirements": [
            {
                "req_code": "REQ-ARCH-003",
                "text": "The solution must provide mainframe COBOL emulation and IBM z/OS integration.",
                "category": "Architecture"
            }
        ]
    }

    result = analyze_compliance_node(state)
    matrix = result["compliance_matrix"]

    assert len(matrix) == 1
    item = matrix[0]
    assert item["req_code"] == "REQ-ARCH-003"
    assert item["status"] == "NON_COMPLIANT"
    assert "out of scope" in item["evidence_text"].lower() or "not support" in item["evidence_text"].lower()
    assert item["company_doc_id"] == "comp_legacy_test_03"


# ==============================================================================
# TEST D: INFORMATION_REQUIRED when NO evidence is found
# ==============================================================================
def test_information_required_when_no_evidence():
    """
    Verifies that when NO evidence exists in the company knowledge base,
    the status is strictly INFORMATION_REQUIRED, NEVER NON_COMPLIANT.
    """
    state: RFPProposalState = {
        "requirements": [
            {
                "req_code": "REQ-COMP-999",
                "text": "The vendor must hold FedRAMP High Authorization and Department of Defense IL6 certification.",
                "category": "Compliance"
            }
        ]
    }

    result = analyze_compliance_node(state)
    matrix = result["compliance_matrix"]

    assert len(matrix) == 1
    item = matrix[0]
    assert item["req_code"] == "REQ-COMP-999"
    assert item["status"] == "INFORMATION_REQUIRED", "Missing evidence must NEVER be marked NON_COMPLIANT"
    assert item["confidence"] == 0.0
    assert item["evidence_text"] is None
    assert item["company_source_doc"] is None
    assert item["citations"] == []
    assert "No verified company capability" in item["notes"]


# ==============================================================================
# TEST E: Programmatic safety gate overrides hallucinating LLM on zero evidence
# ==============================================================================
def test_no_evidence_safety_gate_overrides_llm():
    """
    Verifies that even if an LLM is configured or mocked to hallucinate COMPLIANT
    for an ungrounded requirement, the programmatic safety gate bypasses the LLM
    and assigns INFORMATION_REQUIRED.
    """
    fake_hallucinating_llm = MagicMock()
    fake_hallucinating_llm.with_structured_output.return_value.invoke.return_value = ComplianceItem(
        req_code="REQ-FAKE-01",
        requirement_text="Vendor must have a lunar data center operating on the moon.",
        category="Technical",
        status="COMPLIANT",  # Hallucinated!
        confidence=0.99,
        notes="We definitely have lunar data centers."
    )

    with patch("app.agents.compliance_agent.LLMFactory.get_chat_model", return_value=fake_hallucinating_llm):
        state: RFPProposalState = {
            "requirements": [
                {
                    "req_code": "REQ-FAKE-01",
                    "text": "Vendor must have a lunar data center operating on the moon with zero-gravity cooling.",
                    "category": "Technical"
                }
            ]
        }

        result = analyze_compliance_node(state)
        item = result["compliance_matrix"][0]

        # LLM should never even have been invoked because retriever returned 0 chunks above threshold
        assert fake_hallucinating_llm.with_structured_output.return_value.invoke.call_count == 0
        assert item["status"] == "INFORMATION_REQUIRED"
        assert item["confidence"] == 0.0


# ==============================================================================
# TEST F: Source Traceability Fields Preserved
# ==============================================================================
def test_source_traceability_preserved(seeded_retriever):
    """
    Verifies that all source traceability metadata is populated correctly:
    company_doc_id, chunk_id, source_page, source_section, similarity_score, citations.
    """
    state: RFPProposalState = {
        "requirements": [
            {
                "req_code": "REQ-SLA-001",
                "text": "Provider must guarantee 99.95% monthly uptime SLA with financial credits.",
                "category": "Technical"
            }
        ]
    }

    result = analyze_compliance_node(state)
    item = result["compliance_matrix"][0]

    assert item["company_doc_id"] == "comp_cloud_test_01"
    assert "comp_cloud_test_01_chunk_" in item["chunk_id"]
    assert item["source_page"] == 4
    assert item["source_section"] == "Backup and Availability"
    assert item["similarity_score"] > 0.35
    assert len(item["citations"]) > 0

    citation = item["citations"][0]
    assert citation["company_doc_id"] == "comp_cloud_test_01"
    assert citation["document_title"] == "Enterprise Cloud Infrastructure Guide"
    assert citation["filename"] == "cloud_guide.txt"
    assert citation["source_page"] == 4
    assert citation["source_section"] == "Backup and Availability"
    assert "99.95%" in citation["snippet"]


# ==============================================================================
# TEST G: Threshold Gating (Sub-threshold matches filtered out)
# ==============================================================================
def test_threshold_gating():
    """
    Verifies that evidence with similarity below SIMILARITY_THRESHOLD (0.35)
    is discarded and produces INFORMATION_REQUIRED.
    """
    retriever = KnowledgeBaseRetriever()
    
    # Query something completely distant from general cloud collateral
    results = retriever.retrieve_relevant_evidence(
        query="Cryogenic dilution refrigerator qubit coherence at millikelvin temperatures",
        threshold=0.35
    )
    assert len(results) == 0, "Distant query should yield no results above 0.35"

    state: RFPProposalState = {
        "requirements": [
            {
                "req_code": "REQ-PHYS-001",
                "text": "Cryogenic dilution refrigerator qubit coherence at millikelvin temperatures.",
                "category": "Physical"
            }
        ]
    }
    result = analyze_compliance_node(state)
    item = result["compliance_matrix"][0]
    assert item["status"] == "INFORMATION_REQUIRED"


# ==============================================================================
# TEST H: Hallucination Prevention on Certification Requirements
# ==============================================================================
def test_hallucination_prevention_certification():
    """
    Verifies that a requirement for an unheld certification returns INFORMATION_REQUIRED,
    preventing fabricated compliance claims.
    """
    state: RFPProposalState = {
        "requirements": [
            {
                "req_code": "REQ-CERT-ISO14001",
                "text": "Bidder must possess ISO 14001 Environmental Management certification and carbon offset documentation.",
                "category": "Certification"
            }
        ]
    }

    result = analyze_compliance_node(state)
    item = result["compliance_matrix"][0]

    assert item["status"] == "INFORMATION_REQUIRED"
    assert item["evidence_text"] is None
    assert item["confidence"] == 0.0


# ==============================================================================
# TEST I: Multiple Requirements Isolation & Overall Score
# ==============================================================================
def test_multiple_requirements_isolation(seeded_retriever):
    """
    Verifies that multiple requirements in a batch are evaluated strictly independently
    without cross-contamination, and the overall compliance score is calculated properly.
    """
    state: RFPProposalState = {
        "requirements": [
            {
                "req_code": "REQ-1",
                "text": "Automated daily database backups with 30-day retention.",
                "category": "Technical"
            },
            {
                "req_code": "REQ-2",
                "text": "Legacy on-premise Active Directory directory sync support.",
                "category": "Security"
            },
            {
                "req_code": "REQ-3",
                "text": "Mainframe COBOL emulation and IBM z/OS integration.",
                "category": "Architecture"
            },
            {
                "req_code": "REQ-4",
                "text": "Quantum computing cryptographic key exchange with entanglement.",
                "category": "Cryptography"
            }
        ]
    }

    result = analyze_compliance_node(state)
    matrix = result["compliance_matrix"]

    assert len(matrix) == 4
    status_map = {item["req_code"]: item["status"] for item in matrix}

    assert status_map["REQ-1"] == "COMPLIANT"
    assert status_map["REQ-2"] == "PARTIALLY_COMPLIANT"
    assert status_map["REQ-3"] == "NON_COMPLIANT"
    assert status_map["REQ-4"] == "INFORMATION_REQUIRED"

    # Overall score formula: (1.0 * Compliant + 0.5 * Partial) / Total * 100
    # (1.0 + 0.5 + 0.0 + 0.0) / 4 * 100 = 37.5%
    expected_score = round(((1.0 + 0.5) / 4) * 100, 1)
    assert result["overall_compliance_score"] == expected_score


# ==============================================================================
# TEST J: Deterministic Fallback on LLM Failure
# ==============================================================================
def test_llm_failure_fallback(seeded_retriever):
    """
    Verifies that when LLM evaluation fails or encounters an exception,
    the agent falls back gracefully to the deterministic rule-based evaluator.
    """
    failing_llm = MagicMock()
    failing_llm.with_structured_output.side_effect = RuntimeError("LLM rate limit / API timeout")

    with patch("app.agents.compliance_agent.LLMFactory.get_chat_model", return_value=failing_llm):
        state: RFPProposalState = {
            "requirements": [
                {
                    "req_code": "REQ-FALLBACK-01",
                    "text": "Platform must support automated daily database backups with multi-region replication.",
                    "category": "Technical"
                },
                {
                    "req_code": "REQ-FALLBACK-02",
                    "text": "Mainframe COBOL emulation and IBM z/OS support.",
                    "category": "Architecture"
                }
            ]
        }

        result = analyze_compliance_node(state)
        matrix = result["compliance_matrix"]

        assert len(matrix) == 2
        assert matrix[0]["status"] == "COMPLIANT"
        assert matrix[1]["status"] == "NON_COMPLIANT"


# ==============================================================================
# TEST K: RFP Documents Cannot Be Indexed as Company Collateral
# ==============================================================================
def test_rfp_not_treated_as_company_evidence():
    """
    Verifies that attempts to index RFP, tender, or RFQ documents into the company
    knowledge base are rejected with a ValueError.
    """
    retriever = KnowledgeBaseRetriever()

    with pytest.raises(ValueError, match="cannot be indexed into company knowledge base"):
        retriever.index_document(
            doc_id="rfp_doc_001",
            title="City Transit Authority RFP",
            filename="rfp_city_transit.pdf",
            content="The contractor shall provide cloud hosting services...",
            category="RFP"
        )

    with pytest.raises(ValueError, match="cannot be indexed into company knowledge base"):
        retriever.index_document(
            doc_id="tender_doc_002",
            title="Government Tender Specification",
            filename="tender_spec_2026.docx",
            content="Mandatory tender requirement for all bidders...",
            category="General"
        )


# ==============================================================================
# TEST L: Weak/Related Evidence produces INFORMATION_REQUIRED, NOT PARTIAL
# ==============================================================================
def test_weak_evidence_produces_information_required_not_partially_compliant():
    """
    Verifies that weak or distantly related collateral (e.g., internal quality standards)
    retrieved above threshold must produce INFORMATION_REQUIRED, NEVER PARTIALLY_COMPLIANT.
    """
    retriever = KnowledgeBaseRetriever()
    retriever.index_document(
        doc_id="comp_quality_std_01",
        title="Acme Quality Standards Collateral",
        filename="quality_collateral.txt",
        content="Acme Quality Collateral: The contractor adheres to quality management and engineering standards across all development teams.",
        category="General"
    )

    state: RFPProposalState = {
        "requirements": [
            {
                "req_code": "REQ-ISO9001-01",
                "text": "Contractor must hold ISO 9001 Quality Management certification and adhere to continuous quality standards.",
                "category": "Compliance"
            }
        ]
    }

    result = analyze_compliance_node(state)
    item = result["compliance_matrix"][0]

    assert item["status"] == "INFORMATION_REQUIRED", "Weak or generic evidence must NOT be marked PARTIALLY_COMPLIANT"
    assert item["confidence"] == 0.0
    assert item["evidence_text"] is None


# ==============================================================================
# TEST M: High Similarity but Semantically Insufficient Evidence
# ==============================================================================
def test_high_similarity_semantically_insufficient_evidence():
    """
    RFP: 'Company MUST possess FedRAMP High certification.'
    Collateral: 'Company provides cloud security monitoring and threat detection.'
    Even if retrieved above threshold, semantically insufficient evidence must yield INFORMATION_REQUIRED.
    """
    retriever = KnowledgeBaseRetriever()
    retriever.index_document(
        doc_id="comp_sec_monitor_01",
        title="Cloud Security Monitoring Overview",
        filename="sec_monitoring.txt",
        content="Acme Cloud provides cloud security monitoring, threat detection, and continuous vulnerability assessment.",
        category="Security"
    )

    state: RFPProposalState = {
        "requirements": [
            {
                "req_code": "REQ-FEDRAMP-01",
                "text": "Company MUST possess FedRAMP High certification.",
                "category": "Compliance"
            }
        ]
    }

    result = analyze_compliance_node(state)
    item = result["compliance_matrix"][0]

    assert item["status"] == "INFORMATION_REQUIRED", "Semantically insufficient evidence must NOT claim compliance"
    assert item["confidence"] == 0.0


# ==============================================================================
# TEST N: Similarity Score Alone Cannot Produce COMPLIANT
# ==============================================================================
def test_similarity_score_alone_cannot_produce_compliant():
    """
    Simulates a scenario where an LLM is tricked or hallucinates COMPLIANT with 0.95 confidence
    on text that does not actually provide the requested biometric capability.
    The programmatic safety guard must override to INFORMATION_REQUIRED.
    """
    fake_llm = MagicMock()
    fake_llm.with_structured_output.return_value.invoke.return_value = ComplianceItem(
        req_code="REQ-BIO-01",
        requirement_text="Platform must support facial recognition biometric authentication.",
        category="Technical",
        status="COMPLIANT",
        confidence=0.95,
        notes="We comply based on cloud security."
    )

    retriever = KnowledgeBaseRetriever()
    retriever.index_document(
        doc_id="comp_auth_01",
        title="Database Cluster Security",
        filename="db_security.txt",
        content="Database clusters utilize encrypted authentication tokens and SSL certificates for database connectivity.",
        category="Security"
    )

    with patch("app.agents.compliance_agent.LLMFactory.get_chat_model", return_value=fake_llm):
        state: RFPProposalState = {
            "requirements": [
                {
                    "req_code": "REQ-BIO-01",
                    "text": "Platform must support facial recognition biometric authentication.",
                    "category": "Technical"
                }
            ]
        }

        result = analyze_compliance_node(state)
        item = result["compliance_matrix"][0]

        assert item["status"] == "INFORMATION_REQUIRED", "Programmatic safety guard must override unsupported COMPLIANT"
        assert item["confidence"] == 0.0


# ==============================================================================
# TEST O: Explicit 24/7 Support: PARTIALLY_COMPLIANT vs NON_COMPLIANT
# ==============================================================================
def test_explicit_24_7_support_partial_vs_non_compliant():
    """
    Verifies the two prompt examples:
    Case 1: RFP asks for 24/7 phone and email support; Evidence offers 24/7 email but business hours phone -> PARTIALLY_COMPLIANT.
    Case 2: RFP asks for 24/7 support; Evidence offers standard support during business hours -> NON_COMPLIANT.
    """
    # Case 1: Split requirement -> PARTIALLY_COMPLIANT
    split_ev = {
        "document_title": "Support Policy - Split Coverage",
        "filename": "support_split.txt",
        "evidence_text": "The company provides customer support services. 24/7 email support is provided; phone support is available only during business hours.",
        "similarity": 0.60
    }
    item_partial = _fallback_compliance_eval(
        req_code="REQ-SUPP-PARTIAL",
        req_text="Company must provide 24/7 support including phone and email support.",
        category="Commercial",
        best_evidence=split_ev,
        citations=[]
    )
    assert item_partial.status == "PARTIALLY_COMPLIANT"

    # Case 2: Pure 24/7 requirement vs business hours only -> NON_COMPLIANT
    biz_ev = {
        "document_title": "Support Policy - Standard Hours",
        "filename": "support_business.txt",
        "evidence_text": "The company provides customer support services. Standard support is available during business hours only.",
        "similarity": 0.55
    }
    item_non_compliant = _fallback_compliance_eval(
        req_code="REQ-SUPP-FAIL",
        req_text="Company must provide 24/7 support.",
        category="Commercial",
        best_evidence=biz_ev,
        citations=[]
    )
    assert item_non_compliant.status == "NON_COMPLIANT"


# ==============================================================================
# TEST P: Fallback Evaluator Never Uses Score Alone
# ==============================================================================
def test_fallback_evaluator_never_uses_score_alone():
    """
    Directly tests _fallback_compliance_eval with varying similarity scores
    on semantically insufficient evidence, verifying it never marks them COMPLIANT or PARTIAL.
    """
    citations = []
    
    # 1. High similarity (0.85) but unrelated evidence -> INFORMATION_REQUIRED
    high_sim_insufficient = {
        "document_title": "Database Overview",
        "filename": "db.txt",
        "evidence_text": "Database clusters operate across three availability zones.",
        "similarity": 0.85
    }
    item1 = _fallback_compliance_eval(
        req_code="REQ-TEST-1",
        req_text="Platform must possess FedRAMP High certification.",
        category="Compliance",
        best_evidence=high_sim_insufficient,
        citations=citations
    )
    assert item1.status == "INFORMATION_REQUIRED"
    assert item1.confidence == 0.0

    # 2. Moderate similarity (0.45) but unrelated evidence -> INFORMATION_REQUIRED (NOT PARTIAL!)
    mod_sim_insufficient = {
        "document_title": "Database Overview",
        "filename": "db.txt",
        "evidence_text": "Database clusters operate across three availability zones.",
        "similarity": 0.45
    }
    item2 = _fallback_compliance_eval(
        req_code="REQ-TEST-2",
        req_text="Platform must possess FedRAMP High certification.",
        category="Compliance",
        best_evidence=mod_sim_insufficient,
        citations=citations
    )
    assert item2.status == "INFORMATION_REQUIRED"
    assert item2.confidence == 0.0

