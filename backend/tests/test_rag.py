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
