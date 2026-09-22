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

    # 4. REST API & Web Capabilities (Fully compliant)
    retriever.index_document(
        doc_id="comp_api_test_04",
        title="REST API & Web Integration Guide",
        filename="api_guide.txt",
        content=(
            "Acme Cloud builds modern cloud-native web-based applications accessible via standard web browsers. "
            "Features comprehensive RESTful API integration capabilities: "
            "Standard REST API endpoints supporting JSON payloads for inbound and outbound data synchronization. "
            "Bi-directional REST API integration for external inventory syncing, catalog updates, and order fulfillment. "
            "Enforces multi-factor authentication (MFA) across all administrative accounts."
        ),
        category="Technical",
        page_number=6,
        section="API Architecture"
    )

    # 5. Technical Documentation Suite (Fully compliant)
    retriever.index_document(
        doc_id="comp_doc_test_05",
        title="Technical & User Documentation Suite",
        filename="documentation_suite.txt",
        content=(
            "Acme provides thorough, up-to-date documentation: "
            "Comprehensive administrator manuals detailing configuration, user permissions, and backup management; "
            "End-user operational guides explaining everyday workflows, inventory adjustment, and reporting functions; "
            "Developer technical documentation including OpenAPI/Swagger specifications for all REST API endpoints."
        ),
        category="Documentation",
        page_number=10,
        section="Documentation"
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


# ==============================================================================
# TEST Q: Wording Variations for Core Supported Capabilities
# ==============================================================================
def test_wording_variations_supported_capabilities(seeded_retriever):
    """
    Verifies that various natural phrasing styles of supported capabilities
    (REST API, Web UI, Backups, MFA, Documentation) evaluate accurately to COMPLIANT.
    """
    variations = [
        "The system must provide REST API integration supporting standard JSON payloads.",
        "RESTful API endpoints for inbound data synchronization.",
        "Integration through REST endpoints with automated webhooks.",
        "Web-based application accessible via modern web browsers with responsive interface.",
        "Automated daily database backups with point-in-time recovery.",
        "Multi-factor authentication (MFA) enforcement for administrator accounts.",
        "Comprehensive administrator manuals and end-user operational guides."
    ]

    # Index additional documentation and web capabilities into seeded retriever
    seeded_retriever.index_document(
        doc_id="comp_doc_test_04",
        title="Technical & User Documentation Suite",
        filename="documentation_suite.txt",
        content=(
            "Demo Company provides thorough, up-to-date documentation: "
            "Comprehensive administrator manuals detailing configuration, user permissions, and backup management; "
            "End-user operational guides explaining everyday workflows, inventory adjustment, and reporting functions; "
            "Developer technical documentation including OpenAPI/Swagger specifications for all REST API endpoints."
        ),
        category="Documentation"
    )
    seeded_retriever.index_document(
        doc_id="comp_web_test_05",
        title="Web Platform Overview",
        filename="platform_overview.txt",
        content=(
            "Demo Company builds modern web-based applications accessible through standard web browsers. "
            "Features responsive user interface, RESTful API integration framework, and multi-factor authentication (MFA) enforcement."
        ),
        category="Technical"
    )

    state: RFPProposalState = {
        "requirements": [
            {"req_code": f"REQ-VAR-{i}", "text": text, "category": "Technical"}
            for i, text in enumerate(variations, 1)
        ]
    }

    result = analyze_compliance_node(state)
    matrix = result["compliance_matrix"]

    for item in matrix:
        assert item["status"] == "COMPLIANT", f"Failed for requirement: {item['requirement_text']}"
        assert item["confidence"] >= 0.75
        assert item["evidence_text"] is not None


# ==============================================================================
# TEST R: Strict Rejection of Unsupported Capabilities
# ==============================================================================
def test_unsupported_capabilities_strict_rejection(seeded_retriever):
    """
    Verifies that capabilities not present in the knowledge base (or explicitly excluded)
    strictly yield INFORMATION_REQUIRED or NON_COMPLIANT, never COMPLIANT.
    """
    unsupported = [
        ("REQ-UNSUPP-1", "Vendor must possess ISO/IEC 27001 Information Security certification.", "Certification"),
        ("REQ-UNSUPP-2", "Solution must feature quantum key distribution encryption hardware.", "Technical"),
        ("REQ-UNSUPP-3", "Vendor shall provide 24/7 on-site emergency dispatch technicians.", "Support"),
        ("REQ-UNSUPP-4", "Physical courier delivery of cryptographic token cards within 4 hours.", "Delivery"),
        ("REQ-UNSUPP-5", "Contractor must maintain FedRAMP High provisional authorization.", "Compliance")
    ]

    state: RFPProposalState = {
        "requirements": [
            {"req_code": code, "text": text, "category": cat}
            for code, text, cat in unsupported
        ]
    }

    result = analyze_compliance_node(state)
    matrix = result["compliance_matrix"]

    for item in matrix:
        assert item["status"] in ["INFORMATION_REQUIRED", "NON_COMPLIANT"], f"Must not be compliant: {item['requirement_text']}"
        assert item["status"] != "COMPLIANT"


# ==============================================================================
# TEST S: Customer-Specific Context Tolerance vs Specific Proprietary Requirement
# ==============================================================================
def test_customer_context_tolerance_vs_proprietary_requirement(seeded_retriever):
    """
    Case 1: 'REST API integration with customer order system' -> COMPLIANT (REST API capability verified).
    Case 2: 'Native proprietary SAP S/4HANA ABAP direct connector' -> INFORMATION_REQUIRED (SAP ABAP connector unverified).
    """
    state: RFPProposalState = {
        "requirements": [
            {
                "req_code": "REQ-CUST-1",
                "text": "The platform MUST provide REST API integration with the customer order system.",
                "category": "Technical"
            },
            {
                "req_code": "REQ-CUST-2",
                "text": "Vendor MUST provide native proprietary SAP S/4HANA ABAP direct connector.",
                "category": "Technical"
            }
        ]
    }

    result = analyze_compliance_node(state)
    matrix = result["compliance_matrix"]

    status_map = {item["req_code"]: item["status"] for item in matrix}
    assert status_map["REQ-CUST-1"] == "COMPLIANT", "General REST API capability with customer context should be compliant"
    assert status_map["REQ-CUST-2"] == "INFORMATION_REQUIRED", "Specific proprietary unverified SAP connector must be INFORMATION_REQUIRED"


# ==============================================================================
# TEST T: Diverse Requirement Formatting & Prefix Resilience
# ==============================================================================
def test_diverse_formatting_resilience(seeded_retriever):
    """
    Verifies that different requirement formatting styles (prefixes, section numbers, long/short text)
    retrieve and evaluate the underlying capability identically.
    """
    test_formats = [
        "REQ-TECH-004 Technical The platform SHOULD provide automated daily database backups.",
        "Section 8.2 Backup Services: The contractor must maintain automated daily database backups.",
        "MANDATORY-01 Automated daily database backups with 30-day retention.",
        "R-SEC-99 Automated daily database backups.",
        "Automated daily database backups."
    ]

    state: RFPProposalState = {
        "requirements": [
            {"req_code": f"REQ-FMT-{i}", "text": text, "category": "Technical"}
            for i, text in enumerate(test_formats, 1)
        ]
    }

    result = analyze_compliance_node(state)
    matrix = result["compliance_matrix"]

    for item in matrix:
        assert item["status"] == "COMPLIANT", f"Formatting failed for: {item['requirement_text']}"
        assert item["confidence"] >= 0.75


# ==============================================================================
# TEST U: Completely Unseen Synthetic RFP Generalization
# ==============================================================================
def test_completely_unseen_rfp_generalization(seeded_retriever):
    """
    Tests an end-to-end batch evaluation of a novel synthetic RFP with mixed capabilities:
    - 4 Supported: Web UI, REST API, Database backups, MFA
    - 4 Unsupported: ISO 27001, Quantum Encryption, 24/7 on-site support, FedRAMP High
    Verifies that the overall compliance score reflects the true proportion (50.0%) without hardcoding.
    """
    novel_rfp_requirements = [
        {"req_code": "LOG-SYS-01", "text": "Cloud-native web-based application accessible via standard browsers.", "category": "Technical"},
        {"req_code": "LOG-API-02", "text": "RESTful API integration supporting JSON payloads and automated synchronization.", "category": "Technical"},
        {"req_code": "LOG-DAT-03", "text": "Automated daily database backups with point-in-time recovery and retention.", "category": "Technical"},
        {"req_code": "LOG-SEC-04", "text": "Multi-factor authentication enforcement for administrative users.", "category": "Security"},
        {"req_code": "LOG-ISO-05", "text": "Vendor must possess ISO/IEC 27001 certification.", "category": "Certification"},
        {"req_code": "LOG-CRY-06", "text": "Quantum key distribution hardware encryption.", "category": "Security"},
        {"req_code": "LOG-SUP-07", "text": "24/7 on-site emergency technician dispatch.", "category": "Support"},
        {"req_code": "LOG-FED-08", "text": "FedRAMP High provisional authorization.", "category": "Compliance"},
    ]

    state: RFPProposalState = {
        "requirements": novel_rfp_requirements
    }

    result = analyze_compliance_node(state)
    matrix = result["compliance_matrix"]

    assert len(matrix) == 8
    compliant_items = [item for item in matrix if item["status"] == "COMPLIANT"]
    info_req_items = [item for item in matrix if item["status"] in ["INFORMATION_REQUIRED", "NON_COMPLIANT"]]

    assert len(compliant_items) == 4, "Exactly 4 supported items must be COMPLIANT"
    assert len(info_req_items) == 4, "Exactly 4 unsupported items must be INFORMATION_REQUIRED / NON_COMPLIANT"

    # Overall compliance score: 4/8 * 100 = 50.0%
    assert result["overall_compliance_score"] == 50.0


# ==============================================================================
# TEST V: Evidence Grounding and Accurate Specification Source Selection
# ==============================================================================
def test_evidence_grounding_and_source_selection_accuracy():
    """
    Regression test validating that requirement compliance evidence is strictly grounded
    in the authoritative specification documents and not incidental case studies or overlapping text.
    Tests A through K:
    A. Web application retrieves Platform Overview or Technical Capabilities rather than Experience References.
    B. REST API retrieves Technical & AI Capabilities rather than Delivery.
    C. RBAC retrieves Security & Governance.
    D. Daily backups retrieves Technical & AI Capabilities.
    E. Documentation retrieves Delivery & Implementation.
    F. A generic unrelated document with lexical overlap cannot become supporting evidence.
    G. ISO 27001 explicit negative evidence remains NON_COMPLIANT.
    H. 3 years experience remains INFORMATION_REQUIRED.
    I. Two customer references remains INFORMATION_REQUIRED.
    J. 99.5% availability remains INFORMATION_REQUIRED.
    K. Zero requirement-specific or test-specific hardcoding is used.
    """
    retriever = KnowledgeBaseRetriever()
    coll = retriever.vector_store._collection
    if coll:
        all_ids = coll.get()["ids"]
        if all_ids:
            coll.delete(ids=all_ids)

    # 1. Seed the 5 Demo Company collateral documents
    retriever.index_document(
        doc_id="doc_demo_overview",
        title="Demo Company – Company & Platform Overview",
        filename="Demo_Company_Platform_Overview.txt",
        content=(
            "2. Web-Based Application Architecture\n"
            "Demo Company develops modern web-based applications accessible through standard web browsers (Google Chrome, Mozilla Firefox, Apple Safari, Microsoft Edge).\n"
            "Platform characteristics: Responsive web user interface, zero local installation requirements, modular dashboard for inventory management.\n"
            "5. Verification & Procurement Notice: Specific commercial pricing proposals, currency terms (such as INR quotations), customized liquidated damages terms, and project-specific SLA commitments must be confirmed separately during formal procurement."
        ),
        category="General"
    )

    retriever.index_document(
        doc_id="doc_demo_tech",
        title="Demo Company – Technical & AI Capabilities",
        filename="Demo_Company_Technical_AI_Capabilities.txt",
        content=(
            "1. Web Application & Interface Framework: Demo Company builds cloud-native, web-based applications engineered for high performance and accessibility.\n"
            "2. REST API Integration Architecture: Demo Company platforms feature comprehensive REST API integration capabilities: standard REST API endpoints supporting JSON payloads for inbound and outbound data interchange.\n"
            "3. Database Architecture & Automated Backup Capabilities: Automated daily database backups with point-in-time recovery capabilities and 30-day retention.\n"
            "5. High Availability: While Demo Company platforms are engineered for high availability, specific binding SLA percentages (such as 99.5% uptime guarantees) require separate commercial negotiation."
        ),
        category="Technical"
    )

    retriever.index_document(
        doc_id="doc_demo_sec",
        title="Demo Company – Security & Governance",
        filename="Demo_Company_Security_Governance.txt",
        content=(
            "1. Role-Based Access Control (RBAC) & User Permissions: Demo Company provides and enforces granular Role-Based Access Control across all application modules.\n"
            "2. Multi-Factor Authentication (MFA): Multi-factor authentication (MFA) enforcement for all administrative accounts.\n"
            "3. Data Encryption Standards: Provides data encryption at rest using AES-256 and TLS 1.3 in transit.\n"
            "5. Compliance & Certification Position: Formal third-party certifications such as ISO/IEC 27001 or FedRAMP are not currently held and require separate qualification."
        ),
        category="Security"
    )

    retriever.index_document(
        doc_id="doc_demo_deliv",
        title="Demo Company – Delivery & Implementation",
        filename="Demo_Company_Delivery_Implementation.txt",
        content=(
            "2. Deployment & Configuration Support: Deployment assistance and integration configuration for customer REST API order and inventory endpoints.\n"
            "4. Technical & User Documentation Suite: Comprehensive administrator manuals and end-user operational guides.\n"
            "6. Project Delivery Schedule Notice: Typical implementation timelines range from 12 to 20 weeks. Specific fixed delivery commitments, such as a guaranteed 16-week completion deadline, require formal scoping validation."
        ),
        category="Delivery"
    )

    retriever.index_document(
        doc_id="doc_demo_exp",
        title="Demo Company – Experience & References",
        filename="Demo_Company_Experience_References.txt",
        content=(
            "2. Representative Project Case Studies\n"
            "Case Study 1: Retail & Distribution Inventory Management - Implemented a web-based inventory and product management application for a regional retail distributor.\n"
            "3. Reference & Eligibility Verification Notice: Representative project summaries and contactable technical references are available upon request following mutual confidentiality agreement."
        ),
        category="Experience"
    )

    test_cases = [
        {"req_code": "REQ-A", "text": "The vendor must provide a web-based inventory application accessible via browser.", "cat": "Technical", "expected_status": "COMPLIANT", "expected_docs": ["Demo Company – Company & Platform Overview", "Demo Company – Technical & AI Capabilities"], "forbidden_docs": ["Experience & References"]},
        {"req_code": "REQ-B", "text": "The platform shall provide REST API integration with customer order systems.", "cat": "Technical", "expected_status": "COMPLIANT", "expected_docs": ["Demo Company – Technical & AI Capabilities"], "forbidden_docs": ["Delivery & Implementation"]},
        {"req_code": "REQ-C", "text": "Role-based access control (RBAC) across administrative and operational roles.", "cat": "Security", "expected_status": "COMPLIANT", "expected_docs": ["Demo Company – Security & Governance"], "forbidden_docs": []},
        {"req_code": "REQ-D", "text": "Automated daily database backups with point-in-time recovery.", "cat": "Technical", "expected_status": "COMPLIANT", "expected_docs": ["Demo Company – Technical & AI Capabilities"], "forbidden_docs": []},
        {"req_code": "REQ-E", "text": "Comprehensive administrator guide and end-user documentation.", "cat": "Documentation", "expected_status": "COMPLIANT", "expected_docs": ["Demo Company – Delivery & Implementation"], "forbidden_docs": []},
        {"req_code": "REQ-F", "text": "Proprietary blockchain ledger connector for real-time cryptocurrency reconciliation.", "cat": "Technical", "expected_status": "INFORMATION_REQUIRED", "expected_docs": [], "forbidden_docs": []},
        {"req_code": "REQ-G", "text": "Bidder must hold active ISO 27001 information security certification.", "cat": "Certification", "expected_status": "NON_COMPLIANT", "expected_docs": ["Demo Company – Security & Governance"], "forbidden_docs": []},
        {"req_code": "REQ-H", "text": "The bidder must have a minimum of 3 years corporate operating experience.", "cat": "Eligibility", "expected_status": "INFORMATION_REQUIRED", "expected_docs": [], "forbidden_docs": []},
        {"req_code": "REQ-I", "text": "The vendor must provide two verifiable customer reference contacts with email and phone.", "cat": "Eligibility", "expected_status": "INFORMATION_REQUIRED", "expected_docs": [], "forbidden_docs": []},
        {"req_code": "REQ-J", "text": "The platform must guarantee 99.5% uptime SLA with financial penalty credits.", "cat": "Technical", "expected_status": "INFORMATION_REQUIRED", "expected_docs": [], "forbidden_docs": []}
    ]

    state: RFPProposalState = {
        "requirements": [{"req_code": tc["req_code"], "text": tc["text"], "category": tc["cat"]} for tc in test_cases]
    }

    try:
        result = analyze_compliance_node(state)
        matrix = {item["req_code"]: item for item in result["compliance_matrix"]}

        for tc in test_cases:
            code = tc["req_code"]
            item = matrix[code]
            assert item["status"] == tc["expected_status"], f"Requirement {code} ({tc['text']}) status mismatch: got {item['status']}, expected {tc['expected_status']}"

            if tc["expected_docs"]:
                assert item["company_source_doc"] is not None, f"Expected source doc for {code}"
                matched_doc = any(exp in item["company_source_doc"] for exp in tc["expected_docs"])
                assert matched_doc, f"Requirement {code} source doc '{item['company_source_doc']}' did not match expected {tc['expected_docs']}"

            if tc["forbidden_docs"]:
                for forbidden in tc["forbidden_docs"]:
                    assert forbidden not in (item["company_source_doc"] or ""), f"Requirement {code} source doc '{item['company_source_doc']}' must NOT contain forbidden '{forbidden}'"
    finally:
        for did in ["doc_demo_overview", "doc_demo_tech", "doc_demo_sec", "doc_demo_deliv", "doc_demo_exp"]:
            try:
                if coll:
                    coll.delete(where={"company_doc_id": did})
            except Exception:
                pass


def test_adversarial_evidence_ranking_and_contradiction_handling():
    """
    Adversarial regression test verifying that:
    1. Contradictory evidence (affirmative vs refusal on same capability) does not blindly pick COMPLIANT,
       but safely resolves to INFORMATION_REQUIRED.
    2. Negative statements on unrelated topics do not contaminate positive verdicts.
    3. Ambiguous positive/negative scope on same topic avoids false certainty.
    4. Explicit negative statements on certifications correctly evaluate to NON_COMPLIANT.
    5. Strong semantic specification docs are selected over weak case studies.
    6. Core technical specs are selected over past project mentions.
    7. Targeted documentation collateral is selected over generic delivery services.
    8. High-authority refusals are never overridden by low-authority vague case studies to claim COMPLIANT.
    """
    retriever = KnowledgeBaseRetriever()
    coll = retriever.vector_store._collection
    if coll:
        all_ids = coll.get()["ids"]
        if all_ids:
            coll.delete(ids=all_ids)

    try:
        # ======================================================================
        # TEST 1: CONTRADICTORY CAPABILITY
        # Doc A: "We support REST API integration with external systems."
        # Doc B: "We do not currently support REST API integration with external systems."
        # ======================================================================
        retriever.index_document(
            doc_id="doc_adv_api_pos",
            title="Standard Platform Architecture",
            filename="platform_architecture.txt",
            content="We support REST API integration with external systems.",
            category="Technical"
        )
        retriever.index_document(
            doc_id="doc_adv_api_neg",
            title="System Constraints & Exclusions",
            filename="system_exclusions.txt",
            content="We do not currently support REST API integration with external systems.",
            category="Technical"
        )

        state1: RFPProposalState = {
            "requirements": [{"req_code": "ADV-01", "text": "The platform must provide REST API integration with external systems.", "category": "Technical"}]
        }
        res1 = analyze_compliance_node(state1)["compliance_matrix"][0]
        assert res1["status"] == "INFORMATION_REQUIRED", f"Contradictory evidence must resolve to INFORMATION_REQUIRED, got {res1['status']}"
        assert "conflicting" in (res1["notes"] or "").lower() or "clarification" in (res1["notes"] or "").lower()

        # Clean up test 1 docs
        coll.delete(ids=coll.get()["ids"])

        # ======================================================================
        # TEST 2: NEGATIVE + UNRELATED POSITIVE
        # Doc A: "We provide REST API integration."
        # Doc B: "We do not provide ISO 27001 certification."
        # Requirement: "Vendor must provide REST API integration."
        # ======================================================================
        retriever.index_document(
            doc_id="doc_adv_api_good",
            title="Core API Specifications",
            filename="api_spec.txt",
            content="We provide REST API integration with JSON payload support.",
            category="Technical"
        )
        retriever.index_document(
            doc_id="doc_adv_iso_neg",
            title="Security Certification Position",
            filename="security_cert.txt",
            content="We do not provide ISO 27001 certification and do not hold ISO credentials.",
            category="Security"
        )

        state2: RFPProposalState = {
            "requirements": [{"req_code": "ADV-02", "text": "Vendor must provide REST API integration.", "category": "Technical"}]
        }
        res2 = analyze_compliance_node(state2)["compliance_matrix"][0]
        assert res2["status"] == "COMPLIANT", f"Unrelated ISO refusal must not contaminate REST API, got {res2['status']}"
        assert "Core API Specifications" in (res2["company_source_doc"] or "")

        # Clean up test 2 docs
        coll.delete(ids=coll.get()["ids"])

        # ======================================================================
        # TEST 3: POSITIVE + NEGATIVE SAME TOPIC (AMBIGUOUS SCOPE)
        # Doc A: "We provide role-based access control across all applications."
        # Doc B: "Legacy deployments do not provide role-based access control."
        # Requirement: "The platform must provide RBAC."
        # ======================================================================
        retriever.index_document(
            doc_id="doc_adv_rbac_pos",
            title="Application Security Guide",
            filename="app_security.txt",
            content="We provide role-based access control across all applications.",
            category="Security"
        )
        retriever.index_document(
            doc_id="doc_adv_rbac_neg",
            title="Deployment Release Notes",
            filename="deployment_notes.txt",
            content="Legacy deployments do not provide role-based access control.",
            category="Security"
        )

        state3: RFPProposalState = {
            "requirements": [{"req_code": "ADV-03", "text": "The platform must provide RBAC role-based access control.", "category": "Security"}]
        }
        res3 = analyze_compliance_node(state3)["compliance_matrix"][0]
        assert res3["status"] in ["INFORMATION_REQUIRED", "PARTIALLY_COMPLIANT"], f"Ambiguous scope on same topic must avoid false certainty, got {res3['status']}"

        # Clean up test 3 docs
        coll.delete(ids=coll.get()["ids"])

        # ======================================================================
        # TEST 4: EXPLICIT NEGATIVE CERTIFICATION
        # Doc: "Formal ISO/IEC 27001 certification is not currently held."
        # Requirement: "Vendor MUST provide valid ISO 27001 certification."
        # ======================================================================
        retriever.index_document(
            doc_id="doc_adv_iso_held",
            title="Security & Governance Overview",
            filename="security_governance.txt",
            content="Formal ISO/IEC 27001 certification is not currently held and requires separate qualification.",
            category="Security"
        )

        state4: RFPProposalState = {
            "requirements": [{"req_code": "ADV-04", "text": "Vendor MUST provide valid ISO 27001 certification.", "category": "Certification"}]
        }
        res4 = analyze_compliance_node(state4)["compliance_matrix"][0]
        assert res4["status"] == "NON_COMPLIANT", f"Explicit negative certification must be NON_COMPLIANT, got {res4['status']}"

        # Clean up test 4 docs
        coll.delete(ids=coll.get()["ids"])

        # ======================================================================
        # TEST 5: WEAK LEXICAL MATCH VS STRONG SEMANTIC MATCH
        # Doc A: "Past project experience included web applications."
        # Doc B: "The platform architecture provides browser-accessible web applications with zero client installation."
        # Requirement: "Vendor must provide a web-based application."
        # ======================================================================
        retriever.index_document(
            doc_id="doc_adv_web_weak",
            title="Past Client Case Studies",
            filename="case_studies.txt",
            content="Past project experience included web applications for local clients.",
            category="Experience"
        )
        retriever.index_document(
            doc_id="doc_adv_web_strong",
            title="Platform Architecture Specifications",
            filename="platform_architecture.txt",
            content="The platform architecture provides browser-accessible web applications with zero client installation.",
            category="Technical"
        )

        state5: RFPProposalState = {
            "requirements": [{"req_code": "ADV-05", "text": "Vendor must provide a web-based application.", "category": "Technical"}]
        }
        res5 = analyze_compliance_node(state5)["compliance_matrix"][0]
        assert res5["status"] == "COMPLIANT"
        assert "Platform Architecture Specifications" in (res5["company_source_doc"] or "")
        assert "case_studies" not in (res5["company_source_doc"] or "")

        # Clean up test 5 docs
        coll.delete(ids=coll.get()["ids"])

        # ======================================================================
        # TEST 6: CASE STUDY VS CORE TECHNICAL SPEC
        # Doc A: "Previous customer project integrated an external API."
        # Doc B: "Our platform provides REST API endpoints for bi-directional integration."
        # Requirement: "Platform must provide REST API integration."
        # ======================================================================
        retriever.index_document(
            doc_id="doc_adv_case_api",
            title="Experience & Case Studies",
            filename="case_studies.txt",
            content="Previous customer project integrated an external API for warehouse data.",
            category="Experience"
        )
        retriever.index_document(
            doc_id="doc_adv_spec_api",
            title="Technical Platform Specifications",
            filename="technical_spec.txt",
            content="Our platform provides REST API endpoints for bi-directional integration.",
            category="Technical"
        )

        state6: RFPProposalState = {
            "requirements": [{"req_code": "ADV-06", "text": "Platform must provide REST API integration.", "category": "Technical"}]
        }
        res6 = analyze_compliance_node(state6)["compliance_matrix"][0]
        assert res6["status"] == "COMPLIANT"
        assert "Technical Platform Specifications" in (res6["company_source_doc"] or "")

        # Clean up test 6 docs
        coll.delete(ids=coll.get()["ids"])

        # ======================================================================
        # TEST 7: DOCUMENTATION VS GENERIC DELIVERY
        # Doc A: "We provide implementation and deployment services."
        # Doc B: "We provide administrator manuals and end-user operational guides."
        # Requirement: "Vendor must provide administrator and end-user guides."
        # ======================================================================
        retriever.index_document(
            doc_id="doc_adv_gen_deliv",
            title="Implementation Services Overview",
            filename="services.txt",
            content="We provide implementation and deployment services for enterprise rollouts.",
            category="Delivery"
        )
        retriever.index_document(
            doc_id="doc_adv_doc_suite",
            title="Documentation & Knowledge Suite",
            filename="documentation.txt",
            content="We provide administrator manuals and end-user operational guides for all platform workflows.",
            category="Delivery"
        )

        state7: RFPProposalState = {
            "requirements": [{"req_code": "ADV-07", "text": "Vendor must provide administrator and end-user guides.", "category": "Documentation"}]
        }
        res7 = analyze_compliance_node(state7)["compliance_matrix"][0]
        assert res7["status"] == "COMPLIANT"
        assert "Documentation & Knowledge Suite" in (res7["company_source_doc"] or "")

        # Clean up test 7 docs
        coll.delete(ids=coll.get()["ids"])

        # ======================================================================
        # TEST 8: AUTHORITY SHOULD NOT CREATE FALSE COMPLIANCE
        # High-authority spec doc: "Mainframe COBOL emulation is out of scope and explicitly excluded."
        # Low-authority case study: "Past project included mainframe connectivity assessment."
        # Requirement: "Platform must support mainframe COBOL emulation."
        # ======================================================================
        retriever.index_document(
            doc_id="doc_adv_high_neg",
            title="Core Platform Scope and Exclusions",
            filename="platform_exclusions.txt",
            content="Mainframe COBOL emulation is out of scope and explicitly excluded.",
            category="Technical"
        )
        retriever.index_document(
            doc_id="doc_adv_low_pos",
            title="Representative Project Summaries",
            filename="case_summaries.txt",
            content="Past project included mainframe connectivity assessment and support consultation.",
            category="Experience"
        )

        state8: RFPProposalState = {
            "requirements": [{"req_code": "ADV-08", "text": "Platform must support mainframe COBOL emulation.", "category": "Technical"}]
        }
        res8 = analyze_compliance_node(state8)["compliance_matrix"][0]
        assert res8["status"] in ["NON_COMPLIANT", "INFORMATION_REQUIRED"], f"High-authority refusal must never be overridden to COMPLIANT, got {res8['status']}"
        assert res8["status"] != "COMPLIANT"

    finally:
        if coll:
            all_ids = coll.get()["ids"]
            if all_ids:
                coll.delete(ids=all_ids)


