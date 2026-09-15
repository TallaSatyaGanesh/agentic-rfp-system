import os
import re
import pytest
from typing import Dict, Any, List
from fastapi.testclient import TestClient

from app.main import app
from app.agents.graph import rfp_graph
from app.agents.state import RFPProposalState
from app.rag.retriever import KnowledgeBaseRetriever
from app.services.exporter import ProposalExporterService
from app.agents.writer_agent import write_proposal_node
from app.agents.reviewer_agent import review_proposal_node


@pytest.fixture(scope="module")
def seeded_knowledge_base():
    """Indexes realistic company collateral into the vector store."""
    retriever = KnowledgeBaseRetriever()
    cloud_doc_path = os.path.abspath("sample_data/company_collateral/cloud_capabilities.txt")
    sec_doc_path = os.path.abspath("sample_data/company_collateral/security_and_compliance.txt")

    if os.path.exists(cloud_doc_path):
        with open(cloud_doc_path, "r", encoding="utf-8") as f:
            retriever.index_document("comp_e2e_cloud", "Cloud Capabilities Overview", "cloud_capabilities.txt", f.read(), "Technical")
    if os.path.exists(sec_doc_path):
        with open(sec_doc_path, "r", encoding="utf-8") as f:
            retriever.index_document("comp_e2e_sec", "Security and Compliance Whitepaper", "security_and_compliance.txt", f.read(), "Security")

    return retriever


# ==============================================================================
# INTEGRATION TEST 1: Full Lifecycle Pipeline, State Contracts, and Traceability
# ==============================================================================
def test_e2e_full_workflow_lifecycle_and_data_contracts(seeded_knowledge_base):
    """
    Validates complete lifecycle from real RFP document input to final DOCX export:
    - Agent 1 -> Agent 2 contract (raw clauses passed, metadata extracted)
    - Agent 2 -> Agent 3 contract (classified requirements with canonical IDs)
    - Agent 3 -> Agent 4 contract (compliance verdicts and notes)
    - Agent 4 -> Agent 5 contract (risks and clarifications reach writer)
    - Gate 1 HITL pause and resume
    - Agent 5 -> Agent 6 contract (proposal draft with RequirementResponse objects)
    - Reviewer revision cycle: Draft v1 -> REVISION_REQUIRED -> Draft v2 -> APPROVED
    - Gate 2 HITL pause and resume
    - Immutability of compliance matrix
    - Preservation of source page, section, company doc ID, chunk citations
    - Successful DOCX proposal export
    """
    rfp_file = os.path.abspath("sample_data/sample_rfp_enterprise_cloud.txt")
    assert os.path.exists(rfp_file), f"RFP file not found: {rfp_file}"
    rfp_id = "test_e2e_lifecycle_001"
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
        "workflow_status": "EXTRACTING",
        "logs": [],
        "error": None
    }

    # Step 1: Run graph until Gate 1 interrupt
    for _ in rfp_graph.stream(initial_state, config, stream_mode="updates"):
        pass

    state_gate1 = rfp_graph.get_state(config)
    assert state_gate1.next, "Graph should interrupt at Human Gate 1"
    assert "human_go_nogo_gate" in state_gate1.next
    vals1 = state_gate1.values

    # Check 1: Agent 1 output
    assert vals1["metadata"] is not None
    assert "National Transit" in vals1["metadata"].get("issuer", "") or "NTSCA" in vals1["metadata"].get("issuer", "") or "Enterprise" in vals1["metadata"].get("title", "")
    assert len(vals1["raw_clauses"]) >= 10, f"Expected >= 10 raw clauses, got {len(vals1['raw_clauses'])}"

    # Check 2: Agent 2 output (requirements classified with canonical IDs)
    reqs = vals1["requirements"]
    assert len(reqs) >= 10, f"Expected >= 10 classified requirements, got {len(reqs)}"
    for r in reqs:
        assert r["req_code"].startswith("REQ-")
        assert "source_clause_id" in r
        assert "source_page" in r
        assert "source_section" in r

    # Check 3: Agent 3 output (compliance matrix)
    comp_matrix = vals1["compliance_matrix"]
    assert len(comp_matrix) == len(reqs), "Compliance matrix count must match requirement count"
    comp_map = {c["req_code"]: c for c in comp_matrix}

    # Australian data sovereignty is in RFP (section 3.4) but APAC residency is not in standard Acme collateral
    # -> Must be INFORMATION_REQUIRED or PARTIALLY_COMPLIANT, NEVER falsely COMPLIANT
    sovereignty_req = next((r for r in reqs if "sovereignty" in r["text"].lower() or "australian" in r["text"].lower()), None)
    if sovereignty_req:
        s_res = comp_map.get(sovereignty_req["req_code"])
        assert s_res is not None
        assert s_res["status"] in ["INFORMATION_REQUIRED", "PARTIALLY_COMPLIANT"], f"Australian sovereignty must not be fully COMPLIANT, got {s_res['status']}"

    # Check 4: Agent 4 output (risks and clarifications)
    risks = vals1["risks"]
    clarifs = vals1["clarification_questions"]
    assert len(risks) > 0, "Expected at least one risk identified"
    assert len(clarifs) > 0, "Expected at least one clarification question generated"

    # Step 2: Resume Gate 1 with "GO" decision
    rfp_graph.update_state(config, {
        "go_nogo_decision": "GO",
        "go_nogo_notes": "Approved by Bid Committee. Proceed to proposal authoring."
    })

    # Step 3: Stream through authoring, reviewer, and revision cycle until Gate 2 interrupt
    for _ in rfp_graph.stream(None, config, stream_mode="updates"):
        pass

    state_gate2 = rfp_graph.get_state(config)
    assert state_gate2.next, "Graph should interrupt at Human Gate 2"
    assert "human_final_approval_gate" in state_gate2.next
    vals2 = state_gate2.values

    # Check 5: Revision cycle verified
    # Draft v1 was critiqued and required revision -> Draft v2 was generated
    drafts = vals2["proposal_drafts"]
    assert len(drafts) >= 2, f"Expected at least 2 proposal drafts (v1 and v2), got {len(drafts)}"
    assert drafts[0]["version"] == 1
    assert drafts[1]["version"] == 2
    assert vals2["current_version"] == 2
    assert vals2["revision_count"] >= 1

    # Check 6: Review reports history preserved
    review_reports = vals2["review_reports"]
    assert len(review_reports) >= 2, f"Expected at least 2 review reports, got {len(review_reports)}"
    # Report 1 was REVISION_REQUIRED
    assert review_reports[0]["overall_status"] == "REVISION_REQUIRED"
    # Latest report should be APPROVED or awaiting sign-off
    latest_report = review_reports[-1]
    assert latest_report["overall_status"] in ["APPROVED", "HUMAN_REVIEW_REQUIRED"]

    # Check 7: Compliance status immutability
    # The compliance matrix in state must match the original Agent 3 results exactly
    final_comp = vals2["compliance_matrix"]
    assert len(final_comp) == len(comp_matrix)
    for orig, curr in zip(comp_matrix, final_comp):
        assert orig["req_code"] == curr["req_code"]
        assert orig["status"] == curr["status"]

    # Check 8: Traceability through requirement responses
    latest_draft = drafts[-1]
    req_responses = latest_draft.get("requirement_responses", [])
    assert len(req_responses) > 0
    for resp in req_responses:
        assert resp["requirement_id"].startswith("REQ-")
        # Ensure status matches authoritative Agent 3 status
        auth_status = comp_map[resp["requirement_id"]]["status"]
        assert resp["compliance_status"] == auth_status

    # Step 4: Resume Gate 2 with "APPROVED" decision
    rfp_graph.update_state(config, {
        "final_approval_decision": "APPROVED",
        "human_feedback": "Approved for official tender submission."
    })

    for _ in rfp_graph.stream(None, config, stream_mode="updates"):
        pass

    final_state = rfp_graph.get_state(config)
    assert not final_state.next, "Graph should have reached END"
    assert final_state.values["workflow_status"] == "APPROVED_FOR_EXPORT"

    # Step 5: Test Proposal Export to DOCX
    out_docx = os.path.abspath(f"backend/storage/exports/e2e_proposal_{rfp_id}.docx")
    os.makedirs(os.path.dirname(out_docx), exist_ok=True)
    exported_file = ProposalExporterService.export_to_docx(
        rfp_metadata=final_state.values["metadata"],
        proposal_draft=final_state.values["proposal_drafts"][-1],
        compliance_matrix=final_state.values["compliance_matrix"],
        risks=final_state.values["risks"],
        clarifications=final_state.values["clarification_questions"],
        output_path=out_docx
    )
    assert os.path.exists(exported_file)
    assert os.path.getsize(exported_file) > 5000, f"Exported DOCX too small: {os.path.getsize(exported_file)} bytes"


# ==============================================================================
# INTEGRATION TEST 2: Deal Breaker Escalates Directly to Human Review
# ==============================================================================
def test_e2e_pipeline_deal_breaker_escalation_to_hitl():
    """
    Validates that when an unresolvable tender deal-breaker exists:
    - Reviewer immediately assigns overall_status = 'HUMAN_REVIEW_REQUIRED'
    - LangGraph route_review_outcome routes directly to human_final_approval_gate
    - The system does NOT enter a futile automated revision loop
    """
    rfp_id = "test_e2e_dealbreaker_001"
    config = {"configurable": {"thread_id": rfp_id}}

    reqs = [
        {"req_code": "REQ-MAND-FAIL", "text": "Must possess certified Australian data center.", "is_mandatory": True, "category": "Legal"}
    ]
    comp = [
        {"req_code": "REQ-MAND-FAIL", "status": "NON_COMPLIANT", "notes": "No Australian data center exists.", "evidence_text": None}
    ]
    risks = [
        {"requirement_id": "REQ-MAND-FAIL", "severity": "CRITICAL", "is_bid_blocking": True, "title": "Disqualification Risk: In-Country Residency"}
    ]

    state: RFPProposalState = {
        "rfp_id": rfp_id,
        "file_path": "dummy.txt",
        "metadata": {"title": "Deal Breaker Tender"},
        "raw_clauses": [],
        "requirements": reqs,
        "compliance_matrix": comp,
        "overall_compliance_score": 0.0,
        "risks": risks,
        "clarification_questions": [],
        "go_nogo_decision": "GO",
        "go_nogo_notes": "Attempting proposal authoring",
        "proposal_drafts": [],
        "current_version": 0,
        "review_reports": [],
        "revision_count": 0,
        "max_revisions": 2,
        "final_approval_decision": None,
        "human_feedback": None,
        "active_agent": "Proposal Writer Agent",
        "workflow_status": "WRITING_PROPOSAL",
        "logs": [],
        "error": None
    }

    # Execute Writer
    writer_res = write_proposal_node(state)
    state["proposal_drafts"] = writer_res["proposal_drafts"]
    state["current_version"] = writer_res["current_version"]

    # Execute Reviewer
    reviewer_res = review_proposal_node(state)
    state["review_reports"] = reviewer_res["review_reports"]
    report = state["review_reports"][-1]

    # Reviewer must recognize the unresolvable deal-breaker
    assert report["overall_status"] == "HUMAN_REVIEW_REQUIRED"
    assert report["approval_required"] is True
    assert report["revision_required"] is False
    assert reviewer_res["workflow_status"] == "HUMAN_REVIEW_REQUIRED"

    # Workflow router check
    from app.agents.graph import route_review_outcome
    next_route = route_review_outcome(state)
    assert next_route == "human_final_approval_gate", "Deal-breaker must route directly to Human Gate 2"


# ==============================================================================
# INTEGRATION TEST 3: MAX_REVISIONS Circuit Breaker
# ==============================================================================
def test_e2e_pipeline_max_revisions_circuit_breaker():
    """
    Validates that when a proposal requires revision but revision_count reaches max_revisions:
    - Reviewer assigns HUMAN_REVIEW_REQUIRED
    - Revision loop stops and routes to human_final_approval_gate
    """
    rfp_id = "test_e2e_max_rev_001"
    reqs = [
        {"req_code": "REQ-GAP", "text": "FedRAMP High Certification", "is_mandatory": False, "category": "Cert"}
    ]
    comp = [
        {"req_code": "REQ-GAP", "status": "COMPLIANT", "notes": "Supported.", "evidence_text": "Supported."}
    ]

    # Draft has a response lacking provenance (triggers HIGH finding)
    from app.models.schemas import RequirementResponse, ProposalDraft
    responses = [
        RequirementResponse(
            requirement_id="REQ-GAP",
            requirement_text="FedRAMP High Certification",
            category="Cert",
            is_mandatory=False,
            compliance_status="COMPLIANT",
            response_type="COMPLIANT_RESPONSE",
            response="FedRAMP High is supported.",
            company_doc_id=None,
            citations=[]
        )
    ]
    draft = ProposalDraft(
        version=2,
        title="Max Revisions Draft",
        executive_summary="Executive Summary",
        sections=[],
        full_markdown="# Proposal",
        requirement_responses=responses
    )

    state: RFPProposalState = {
        "rfp_id": rfp_id,
        "file_path": "dummy.txt",
        "metadata": {"title": "Max Revisions Tender"},
        "raw_clauses": [],
        "requirements": reqs,
        "compliance_matrix": comp,
        "overall_compliance_score": 0.0,
        "risks": [],
        "clarification_questions": [],
        "go_nogo_decision": "GO",
        "go_nogo_notes": "Proceeding",
        "proposal_drafts": [draft.model_dump()],
        "current_version": 2,
        "review_reports": [],
        "revision_count": 2,  # Already at MAX_REVISIONS
        "max_revisions": 2,
        "final_approval_decision": None,
        "human_feedback": None,
        "active_agent": "Reviewer / Critic Agent",
        "workflow_status": "REVIEWING",
        "logs": [],
        "error": None
    }

    # Reviewer reviews
    r_out = review_proposal_node(state)
    report = r_out["review_reports"][-1]

    # Reaching max revisions forces HUMAN_REVIEW_REQUIRED
    assert report["overall_status"] == "HUMAN_REVIEW_REQUIRED"
    assert report["revision_required"] is False
    assert report["approval_required"] is True

    from app.agents.graph import route_review_outcome
    state["review_reports"] = r_out["review_reports"]
    next_route = route_review_outcome(state)
    assert next_route == "human_final_approval_gate"


# ==============================================================================
# INTEGRATION TEST 4: FastAPI REST API Workflow Execution
# ==============================================================================
def test_e2e_fastapi_rest_api_workflow_execution(seeded_knowledge_base):
    """
    Validates complete REST API lifecycle via FastAPI TestClient:
    - POST /api/rfp/upload
    - POST /api/workflow/{rfp_id}/start -> runs until Gate 1 interrupt
    - GET /api/workflow/{rfp_id}/status -> verifies Gate 1 state
    - GET /api/rfp/{rfp_id}/requirements -> verifies DB persistence
    - GET /api/rfp/{rfp_id}/compliance-matrix -> verifies DB persistence
    - GET /api/rfp/{rfp_id}/risks -> verifies DB persistence
    - POST /api/workflow/{rfp_id}/resume (GO) -> runs until Gate 2 interrupt
    - GET /api/workflow/{rfp_id}/status -> verifies Gate 2 state
    - GET /api/rfp/{rfp_id}/proposals -> verifies proposal drafts persisted
    - POST /api/workflow/{rfp_id}/resume (APPROVED) -> finishes workflow
    - GET /api/rfp/{rfp_id}/export/docx -> downloads valid proposal document
    """
    client = TestClient(app)

    # 1. Upload RFP
    sample_path = "sample_data/sample_rfp_enterprise_cloud.txt"
    with open(sample_path, "rb") as f:
        up_res = client.post("/api/rfp/upload", files={"file": ("test_rfp_api_e2e.txt", f, "text/plain")})
    assert up_res.status_code == 200, f"RFP Upload failed: {up_res.text}"
    rfp_id = up_res.json()["rfp_id"]

    # 2. Start Workflow
    start_res = client.post(f"/api/workflow/{rfp_id}/start")
    assert start_res.status_code == 200

    # 3. Check status at Gate 1
    st1 = client.get(f"/api/workflow/{rfp_id}/status").json()
    assert st1["is_interrupted"] is True
    assert st1["interrupt_type"] == "GO_NOGO"
    assert st1["status"] == "AWAITING_GO_NOGO"

    # 4. Check DB tables populated at Gate 1
    reqs = client.get(f"/api/rfp/{rfp_id}/requirements").json()
    comp = client.get(f"/api/rfp/{rfp_id}/compliance-matrix").json()
    risks_data = client.get(f"/api/rfp/{rfp_id}/risks").json()

    assert len(reqs) > 0, "Requirements not saved to DB"
    assert len(comp) > 0, "Compliance records not saved to DB"
    assert len(risks_data.get("risks", [])) > 0, "Risks not saved to DB"

    # 5. Resume Gate 1 with "GO"
    res1 = client.post(f"/api/workflow/{rfp_id}/resume", json={
        "decision": "GO",
        "notes": "Approved to draft proposal."
    })
    assert res1.status_code == 200

    # 6. Check status at Gate 2
    st2 = client.get(f"/api/workflow/{rfp_id}/status").json()
    assert st2["is_interrupted"] is True
    assert st2["interrupt_type"] == "FINAL_APPROVAL"
    assert st2["status"] == "AWAITING_FINAL_APPROVAL"
    assert st2["current_version"] >= 2  # Revision loop occurred

    # 7. Check proposals table
    props = client.get(f"/api/rfp/{rfp_id}/proposals").json()
    assert len(props) >= 2, f"Expected at least 2 proposal versions in DB, got {len(props)}"
    versions = [p["version"] for p in props]
    assert 1 in versions
    assert 2 in versions

    # 8. Resume Gate 2 with "APPROVED"
    res2 = client.post(f"/api/workflow/{rfp_id}/resume", json={
        "decision": "APPROVED",
        "feedback": "Approved for submission."
    })
    assert res2.status_code == 200

    # 9. Check final status
    st3 = client.get(f"/api/workflow/{rfp_id}/status").json()
    assert st3["status"] == "APPROVED_FOR_EXPORT"
    assert st3["is_interrupted"] is False

    # 10. Test DOCX Export
    exp = client.get(f"/api/rfp/{rfp_id}/export/docx")
    assert exp.status_code == 200
    assert exp.headers["content-type"] == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    assert len(exp.content) > 5000, "Downloaded DOCX file is unexpectedly small"


# ==============================================================================
# INTEGRATION TEST 5: Anti-Hallucination and Evidence Provenance Isolation
# ==============================================================================
def test_e2e_anti_hallucination_and_provenance_isolation():
    """
    Validates anti-hallucination and evidence integrity across the pipeline:
    - RFP files cannot be indexed into company knowledge base
    - Unconfirmed requirements retain [INFORMATION REQUIRED] framing
    - Non-compliant requirements retain exception/variance framing
    """
    retriever = KnowledgeBaseRetriever()

    # Guardrail 1: RFP document cannot be indexed as company collateral
    with pytest.raises(ValueError, match="cannot be indexed into company knowledge base"):
        retriever.index_document(
            doc_id="rfp_doc_bad",
            title="Sample RFP Solicitation",
            filename="solicitation_rfp_2026.pdf",
            content="The vendor must provide 24/7 support.",
            category="RFP"
        )

    # Guardrail 2: Requirement responses properly differentiate grounded vs ungrounded
    reqs = [
        {"req_code": "REQ-E2E-IR", "text": "Australian regional presence", "is_mandatory": True, "category": "Legal"},
        {"req_code": "REQ-E2E-NC", "text": "Unlimited liability", "is_mandatory": True, "category": "Legal"}
    ]
    comp = [
        {"req_code": "REQ-E2E-IR", "status": "INFORMATION_REQUIRED", "notes": "No APAC presence in collateral", "evidence_text": None},
        {"req_code": "REQ-E2E-NC", "status": "NON_COMPLIANT", "notes": "Standard liability capped at 1x contract value", "evidence_text": "Liability capped."}
    ]

    state: RFPProposalState = {
        "rfp_id": "test_e2e_guardrails",
        "file_path": "dummy.txt",
        "metadata": {"title": "Guardrails RFP"},
        "raw_clauses": [],
        "requirements": reqs,
        "compliance_matrix": comp,
        "overall_compliance_score": 0.0,
        "risks": [],
        "clarification_questions": [],
        "go_nogo_decision": "GO",
        "go_nogo_notes": "Proceeding",
        "proposal_drafts": [],
        "current_version": 0,
        "review_reports": [],
        "revision_count": 0,
        "max_revisions": 2,
        "final_approval_decision": None,
        "human_feedback": None,
        "active_agent": "Proposal Writer Agent",
        "workflow_status": "WRITING_PROPOSAL",
        "logs": [],
        "error": None
    }

    w_out = write_proposal_node(state)
    draft = w_out["proposal_drafts"][-1]
    responses = draft.get("requirement_responses", [])

    resp_ir = next(r for r in responses if r["requirement_id"] == "REQ-E2E-IR")
    resp_nc = next(r for r in responses if r["requirement_id"] == "REQ-E2E-NC")

    # INFORMATION_REQUIRED response must not promise capability
    assert "information required" in resp_ir["response"].lower() or "unconfirmed" in resp_ir["response"].lower()
    assert "we will provide australian" not in resp_ir["response"].lower()

    # NON_COMPLIANT response must not promise compliance
    assert "exception" in resp_nc["response"].lower() or "variance" in resp_nc["response"].lower() or "not currently supported" in resp_nc["response"].lower()
    assert "fully compliant" not in resp_nc["response"].lower()
