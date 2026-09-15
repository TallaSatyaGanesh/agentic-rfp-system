import pytest
import os
from app.agents.graph import rfp_graph
from app.agents.state import RFPProposalState
from app.rag.retriever import KnowledgeBaseRetriever
from app.services.exporter import ProposalExporterService

def test_full_langgraph_workflow_and_hitl():
    # 1. Prepare RAG Knowledge Base
    retriever = KnowledgeBaseRetriever()
    cloud_doc_path = os.path.abspath("sample_data/company_collateral/cloud_capabilities.txt")
    sec_doc_path = os.path.abspath("sample_data/company_collateral/security_and_compliance.txt")
    
    with open(cloud_doc_path, "r", encoding="utf-8") as f:
        retriever.index_document("comp_01", "Cloud Overview", "cloud_capabilities.txt", f.read())
    with open(sec_doc_path, "r", encoding="utf-8") as f:
        retriever.index_document("comp_02", "Security Whitepaper", "security_and_compliance.txt", f.read())

    # 2. Setup initial state
    rfp_file = os.path.abspath("sample_data/sample_rfp_enterprise_cloud.txt")
    rfp_id = "test_rfp_workflow_001"
    config = {"configurable": {"thread_id": rfp_id}}

    initial_state: RFPProposalState = {
        "rfp_id": rfp_id,
        "file_path": rfp_file,
        "metadata": None,
        "raw_clauses": [],
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
        "active_agent": "Extraction Agent",
        "workflow_status": "PENDING",
        "logs": [],
        "error": None
    }

    # 3. Stream graph execution until Gate 1 interrupt
    for _ in rfp_graph.stream(initial_state, config, stream_mode="updates"):
        pass

    state_gate1 = rfp_graph.get_state(config)
    assert state_gate1.next, "Graph should have interrupted at Human Gate 1"
    assert "human_go_nogo_gate" in state_gate1.next

    # Verify Agents 1-4 completed work
    vals1 = state_gate1.values
    assert len(vals1["raw_clauses"]) > 0, "No raw clauses extracted"
    assert len(vals1["requirements"]) > 0, "No requirements classified"
    assert len(vals1["compliance_matrix"]) > 0, "No compliance matrix generated"
    assert len(vals1["risks"]) > 0, "No risks generated"
    assert len(vals1["clarification_questions"]) > 0, "No clarification questions generated"

    # Verify INFORMATION_REQUIRED guardrail:
    # Australian data sovereignty was in the RFP but NOT in Acme collateral!
    info_needed_items = [c for c in vals1["compliance_matrix"] if c["status"] == "INFORMATION_REQUIRED"]
    assert len(info_needed_items) > 0, "Expected at least one INFORMATION_REQUIRED item due to missing regional collateral"

    # 4. Resume Gate 1 with Human Decision "GO"
    rfp_graph.update_state(config, {"go_nogo_decision": "GO", "go_nogo_notes": "Approved. Emphasize cloud failover."})
    
    # Continue stream: runs writer -> reviewer -> revision loop -> reaches Gate 2
    for _ in rfp_graph.stream(None, config, stream_mode="updates"):
        pass

    state_gate2 = rfp_graph.get_state(config)
    assert state_gate2.next, "Graph should have interrupted at Human Gate 2"
    assert "human_final_approval_gate" in state_gate2.next

    vals2 = state_gate2.values
    # Verify revision cycle occurred!
    assert len(vals2["proposal_drafts"]) >= 2, f"Expected at least 2 drafts (initial + revision), got {len(vals2['proposal_drafts'])}"
    assert len(vals2["review_reports"]) >= 1, "Expected at least 1 review report"
    assert vals2["review_reports"][0]["overall_score"] > 0

    # 5. Resume Gate 2 with Final Approval "APPROVED"
    rfp_graph.update_state(config, {"final_approval_decision": "APPROVED", "human_feedback": "Looks great for tender submission."})
    
    for _ in rfp_graph.stream(None, config, stream_mode="updates"):
        pass

    final_state = rfp_graph.get_state(config)
    assert not final_state.next, "Graph should have finished execution"
    assert final_state.values["workflow_status"] == "APPROVED_FOR_EXPORT"

    # 6. Verify Export to DOCX
    out_docx = os.path.abspath(f"backend/storage/exports/test_proposal_{rfp_id}.docx")
    exported_file = ProposalExporterService.export_to_docx(
        rfp_metadata=final_state.values["metadata"],
        proposal_draft=final_state.values["proposal_drafts"][-1],
        compliance_matrix=final_state.values["compliance_matrix"],
        risks=final_state.values["risks"],
        clarifications=final_state.values["clarification_questions"],
        output_path=out_docx
    )
    assert os.path.exists(exported_file), f"Exported DOCX file not found at {exported_file}"
    assert os.path.getsize(exported_file) > 1000, "Exported DOCX file is too small"

    print(f"\n[Full Multi-Agent Workflow Test Passed!]")
    print(f"  Requirements: {len(final_state.values['requirements'])}")
    print(f"  Compliance Score: {final_state.values['overall_compliance_score']}%")
    print(f"  Draft Versions: {len(final_state.values['proposal_drafts'])}")
    print(f"  Review Reports: {len(final_state.values['review_reports'])}")
    print(f"  Exported Document: {exported_file}")
