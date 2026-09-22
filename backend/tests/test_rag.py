import pytest
import os
from app.rag.vector_store import VectorStoreManager
from app.rag.retriever import KnowledgeBaseRetriever

def test_rag_knowledge_base():
    retriever = KnowledgeBaseRetriever()
    
    # 1. Ingest sample documents
    cloud_doc_path = os.path.abspath("sample_data/company_collateral/cloud_capabilities.txt")
    sec_doc_path = os.path.abspath("sample_data/company_collateral/security_and_compliance.txt")
    
    with open(cloud_doc_path, "r", encoding="utf-8") as f:
        cloud_content = f.read()
    with open(sec_doc_path, "r", encoding="utf-8") as f:
        sec_content = f.read()

    chunks1 = retriever.index_document(
        doc_id="comp_cloud_01",
        title="Acme Cloud Infrastructure Overview",
        filename="cloud_capabilities.txt",
        content=cloud_content,
        category="Technical"
    )
    chunks2 = retriever.index_document(
        doc_id="comp_sec_01",
        title="Acme Security & Compliance White Paper",
        filename="security_and_compliance.txt",
        content=sec_content,
        category="Security"
    )

    assert chunks1 > 0
    assert chunks2 > 0

    # 2. Test verified capability retrieval (Uptime SLA)
    query_sla = "guaranteed monthly uptime SLA 99.95%"
    results_sla = retriever.retrieve_relevant_evidence(query=query_sla, threshold=0.35)
    assert len(results_sla) > 0, "Failed to retrieve SLA evidence"
    assert "99.95%" in results_sla[0]["evidence_text"]

    # 3. Test verified security retrieval (SOC2 Type II)
    query_soc2 = "SOC2 Type II certification ISO 27001"
    results_soc2 = retriever.retrieve_relevant_evidence(query=query_soc2, threshold=0.35)
    assert len(results_soc2) > 0
    assert "SOC2 Type II" in results_soc2[0]["evidence_text"]

    # 4. Test completely ungrounded capability (e.g. quantum computing hardware)
    query_quantum = "Quantum computing hardware integration with dilution refrigerators cryogenic qubits"
    results_quantum = retriever.retrieve_relevant_evidence(query=query_quantum, threshold=0.35)
    assert len(results_quantum) == 0, "Ungrounded query should return zero results above threshold"

    print(f"\n[RAG Test Passed] Indexed {chunks1 + chunks2} chunks. Verified grounding and zero-hallucination filter.")


def test_sanitize_requirement_query_generalized():
    """
    Verifies that sanitize_requirement_query accurately strips diverse requirement code formats
    and boilerplate while preserving true domain vocabulary across arbitrary RFPs.
    """
    from app.rag.retriever import sanitize_requirement_query

    # 1. Standard prefix formats
    assert "web-based inventory management application" in sanitize_requirement_query(
        "REQ-TECH-001 Technical The vendor MUST provide a web-based inventory management application."
    )
    assert "REST API integration" in sanitize_requirement_query(
        "REQ-TECH-002 Technical The platform MUST provide REST API integration with the customer order system."
    )
    assert "Role-based access control" in sanitize_requirement_query(
        "R-SEC-99 Security Role-based access control for admin and staff."
    )
    assert "administrator manuals" in sanitize_requirement_query(
        "Section 4.1.2 Documentation The vendor shall provide administrator manuals."
    )
    assert "Implementation within 16 weeks" in sanitize_requirement_query(
        "MANDATORY-REQ-001 Delivery Implementation within 16 weeks."
    )
    assert "helpdesk for incident logging" in sanitize_requirement_query(
        "A11 The vendor shall provide a helpdesk for incident logging."
    )

    # 2. Natural language without prefix should preserve substantive terms
    assert sanitize_requirement_query("Web-based application accessible via browser.") == "Web-based application accessible via browser."
    assert sanitize_requirement_query("Role-based access control with granular permissions.") == "Role-based access control with granular permissions."
    assert sanitize_requirement_query("RESTful API integration with JSON payloads.") == "RESTful API integration with JSON payloads."


def test_retriever_prefix_invariance():
    """
    Verifies that a requirement formatted with different ID prefixes (or no prefix)
    retrieves the same underlying capability chunk above the threshold.
    """
    retriever = KnowledgeBaseRetriever()
    retriever.index_document(
        doc_id="comp_test_api_01",
        title="Demo Company APIs",
        filename="api_doc.txt",
        content="Demo Company provides comprehensive RESTful API integration supporting JSON payloads and automated webhook triggers.",
        category="Technical"
    )

    query_prefixed_1 = "REQ-TECH-002 Technical The platform MUST provide REST API integration with JSON payloads."
    query_prefixed_2 = "Section 5.3.1 Technical The vendor shall provide REST API integration with JSON payloads."
    query_prefixed_3 = "R-API-99 Mandatory The contractor agrees to provide REST API integration with JSON payloads."
    query_unprefixed = "REST API integration with JSON payloads."

    res1 = retriever.retrieve_relevant_evidence(query=query_prefixed_1, threshold=0.35)
    res2 = retriever.retrieve_relevant_evidence(query=query_prefixed_2, threshold=0.35)
    res3 = retriever.retrieve_relevant_evidence(query=query_prefixed_3, threshold=0.35)
    res4 = retriever.retrieve_relevant_evidence(query=query_unprefixed, threshold=0.35)

    assert len(res1) > 0, "Prefixed REQ-TECH-002 should retrieve REST API evidence"
    assert len(res2) > 0, "Prefixed Section 5.3.1 should retrieve REST API evidence"
    assert len(res3) > 0, "Prefixed R-API-99 should retrieve REST API evidence"
    assert len(res4) > 0, "Unprefixed query should retrieve REST API evidence"

    # All should point to the exact same document
    assert res1[0]["company_doc_id"] == res2[0]["company_doc_id"] == res3[0]["company_doc_id"] == res4[0]["company_doc_id"]
    assert "REST" in res1[0]["evidence_text"]

