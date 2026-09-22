import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.main import app
from app.db.database import Base, get_db
from app.db.models import RFPDocument
from app.agents.graph import rfp_graph

import app.api.workflow_routes as wf_routes
import app.db.database as db_module

os.makedirs("./backend/storage", exist_ok=True)
DB_PATH = "./backend/storage/test_state_sync.db"
SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

@pytest.fixture(autouse=True)
def setup_db():
    app.dependency_overrides[get_db] = override_get_db
    wf_routes.SessionLocal = TestingSessionLocal
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    app.dependency_overrides.clear()
    wf_routes.SessionLocal = getattr(db_module, "SessionLocal", TestingSessionLocal)
    if os.path.exists(DB_PATH):
        try:
            os.remove(DB_PATH)
        except OSError:
            pass


client = TestClient(app)

def test_1_processing_with_stale_checkpointer():
    db = TestingSessionLocal()
    rfp = RFPDocument(
        id="rfp_proc_test",
        title="Processing RFP",
        filename="test.txt",
        file_path="dummy.txt",
        status="PROCESSING"
    )
    db.add(rfp)
    db.commit()

    config = {"configurable": {"thread_id": "rfp_proc_test"}}
    rfp_graph.update_state(config, {"workflow_status": "PROCESSING", "active_agent": "Extraction Agent"})

    response = client.get("/api/workflow/rfp_proc_test/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "PROCESSING"
    assert data["is_interrupted"] is False
    assert data["interrupt_type"] is None

def test_2_extracting_with_stale_checkpointer():
    db = TestingSessionLocal()
    rfp = RFPDocument(
        id="rfp_ext_test",
        title="Extracting RFP",
        filename="test.txt",
        file_path="dummy.txt",
        status="EXTRACTING"
    )
    db.add(rfp)
    db.commit()

    response = client.get("/api/workflow/rfp_ext_test/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ["EXTRACTING", "PROCESSING"]
    assert data["is_interrupted"] is False

def test_3_failed_with_stale_checkpointer():
    db = TestingSessionLocal()
    rfp = RFPDocument(
        id="rfp_fail_test",
        title="Failed RFP",
        filename="test.txt",
        file_path="dummy.txt",
        status="FAILED"
    )
    db.add(rfp)
    db.commit()

    response = client.get("/api/workflow/rfp_fail_test/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "FAILED"
    assert data["is_interrupted"] is False

def test_4_awaiting_go_nogo():
    db = TestingSessionLocal()
    rfp = RFPDocument(
        id="rfp_gonogo_test",
        title="Go NoGo RFP",
        filename="test.txt",
        file_path="dummy.txt",
        status="AWAITING_GO_NOGO"
    )
    db.add(rfp)
    db.commit()

    response = client.get("/api/workflow/rfp_gonogo_test/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "AWAITING_GO_NOGO"

def test_5_awaiting_final_approval():
    db = TestingSessionLocal()
    rfp = RFPDocument(
        id="rfp_appr_test",
        title="Approval RFP",
        filename="test.txt",
        file_path="dummy.txt",
        status="AWAITING_FINAL_APPROVAL"
    )
    db.add(rfp)
    db.commit()

    response = client.get("/api/workflow/rfp_appr_test/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "AWAITING_FINAL_APPROVAL"

def test_6_human_review_required():
    db = TestingSessionLocal()
    rfp = RFPDocument(
        id="rfp_revreq_test",
        title="Escalated RFP",
        filename="test.txt",
        file_path="dummy.txt",
        status="HUMAN_REVIEW_REQUIRED"
    )
    db.add(rfp)
    db.commit()

    response = client.get("/api/workflow/rfp_revreq_test/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "HUMAN_REVIEW_REQUIRED"

def test_7_missing_rfp_file_protection():
    db = TestingSessionLocal()
    rfp = RFPDocument(
        id="rfp_missing_file",
        title="Missing File RFP",
        filename="nonexistent.txt",
        file_path="./backend/storage/uploads/nonexistent_file_path_12345.txt",
        status="UPLOADED"
    )
    db.add(rfp)
    db.commit()

    response = client.post("/api/workflow/rfp_missing_file/start")
    assert response.status_code == 400
    assert "Document file not found" in response.json()["detail"]

    db.refresh(rfp)
    assert rfp.status == "FAILED"

def test_8_background_workflow_exception_handling():
    import app.api.workflow_routes as wf_routes
    import asyncio

    orig_session_local = wf_routes.SessionLocal
    wf_routes.SessionLocal = TestingSessionLocal
    try:
        db = TestingSessionLocal()
        rfp = RFPDocument(
            id="rfp_bg_fail",
            title="Background Fail RFP",
            filename="bad.txt",
            file_path="./nonexistent_path_bg.txt",
            status="PROCESSING"
        )
        db.add(rfp)
        db.commit()

        asyncio.run(wf_routes.run_workflow_async("rfp_bg_fail", "./nonexistent_path_bg.txt"))

        db.refresh(rfp)
        assert rfp.status == "FAILED"
    finally:
        wf_routes.SessionLocal = orig_session_local

def test_9_two_projects_same_title_isolation():
    db = TestingSessionLocal()
    rfp1 = RFPDocument(
        id="rfp_same_title_1",
        title="Duplicate RFP Title",
        filename="file1.txt",
        file_path="file1.txt",
        status="PROCESSING"
    )
    rfp2 = RFPDocument(
        id="rfp_same_title_2",
        title="Duplicate RFP Title",
        filename="file2.txt",
        file_path="file2.txt",
        status="APPROVED_FOR_EXPORT"
    )
    db.add_all([rfp1, rfp2])
    db.commit()

    st1 = client.get("/api/workflow/rfp_same_title_1/status").json()
    st2 = client.get("/api/workflow/rfp_same_title_2/status").json()

    assert st1["status"] == "PROCESSING"
    assert st1["is_interrupted"] is False

    assert st2["status"] == "APPROVED_FOR_EXPORT"
    assert st2["is_interrupted"] is False


def test_10_gate1_persistence_and_data_output_coordination():
    """Validates that Gate 1 results are persisted to DB and data endpoints return populated records."""
    import app.api.workflow_routes as wf_routes
    orig_session_local = wf_routes.SessionLocal
    wf_routes.SessionLocal = TestingSessionLocal

    try:
        db = TestingSessionLocal()
        rfp = RFPDocument(
            id="rfp_gate1_sync_test",
            title="Gate 1 Sync RFP",
            filename="sync_test.txt",
            file_path="sync_test.txt",
            status="AWAITING_GO_NOGO"
        )
        db.add(rfp)
        db.commit()

        mock_state = {
            "workflow_status": "AWAITING_GO_NOGO",
            "overall_compliance_score": 85.5,
            "requirements": [
                {
                    "req_code": "REQ-TECH-001",
                    "category": "Technical",
                    "priority": "High",
                    "is_mandatory": True,
                    "text": "The platform must support high availability.",
                    "source_page": 1,
                    "source_section": "Technical"
                },
                {
                    "req_code": "REQ-SEC-001",
                    "category": "Certification",
                    "priority": "High",
                    "is_mandatory": True,
                    "text": "The vendor must hold active ISO 27001.",
                    "source_page": 2,
                    "source_section": "Security"
                }
            ],
            "compliance_matrix": [
                {
                    "req_code": "REQ-TECH-001",
                    "status": "COMPLIANT",
                    "confidence": 0.95,
                    "evidence_text": "Company supports multi-region HA.",
                    "company_source_doc": "cloud_capabilities.txt",
                    "notes": "Verified in collateral."
                },
                {
                    "req_code": "REQ-SEC-001",
                    "status": "INFORMATION_REQUIRED",
                    "confidence": 0.0,
                    "evidence_text": None,
                    "company_source_doc": None,
                    "notes": "Information required from compliance team."
                }
            ],
            "risks": [
                {
                    "category": "Certification",
                    "severity": "HIGH",
                    "likelihood": "High",
                    "description": "ISO 27001 evidence unverified.",
                    "mitigation_strategy": "Obtain certificate copy.",
                    "rfp_reference": "REQ-SEC-001"
                },
                {
                    "category": "Contractual",
                    "severity": "CRITICAL",
                    "likelihood": "High",
                    "description": "Uncapped indemnification clause.",
                    "mitigation_strategy": "Request liability cap.",
                    "rfp_reference": "REQ-LEG-001"
                }
            ],
            "clarification_questions": [
                {
                    "q_number": 1,
                    "rfp_section_reference": "Security",
                    "question_text": "Please confirm ISO 27001 status.",
                    "rationale": "Required for compliance."
                }
            ]
        }

        # Persist results to DB
        wf_routes._persist_workflow_results_to_db("rfp_gate1_sync_test", mock_state)

        # 1. Verify compliance matrix endpoint returns 2 records
        comp_resp = client.get("/api/rfp/rfp_gate1_sync_test/compliance-matrix")
        assert comp_resp.status_code == 200
        comp_items = comp_resp.json()
        assert len(comp_items) == 2
        assert comp_items[0]["req_code"] == "REQ-TECH-001"
        assert comp_items[0]["status"] == "COMPLIANT"
        assert comp_items[1]["req_code"] == "REQ-SEC-001"
        assert comp_items[1]["status"] == "INFORMATION_REQUIRED"

        # 2. Verify risks endpoint returns 2 records with correct severities
        risk_resp = client.get("/api/rfp/rfp_gate1_sync_test/risks")
        assert risk_resp.status_code == 200
        risk_data = risk_resp.json()
        assert len(risk_data["risks"]) == 2
        assert len(risk_data["clarification_questions"]) == 1

        severities = [r["severity"].upper() for r in risk_data["risks"]]
        assert "HIGH" in severities
        assert "CRITICAL" in severities

        # 3. Verify workflow status returns AWAITING_GO_NOGO
        status_resp = client.get("/api/workflow/rfp_gate1_sync_test/status")
        assert status_resp.status_code == 200
        assert status_resp.json()["status"] == "AWAITING_GO_NOGO"
    finally:
        wf_routes.SessionLocal = orig_session_local


def test_11_case_insensitive_risk_severity_handling():
    """Validates case-insensitive risk severity handling across mixed casing in database."""
    import app.api.workflow_routes as wf_routes
    orig_session_local = wf_routes.SessionLocal
    wf_routes.SessionLocal = TestingSessionLocal

    try:
        db = TestingSessionLocal()
        rfp = RFPDocument(
            id="rfp_case_test",
            title="Mixed Case Risk RFP",
            filename="case_test.txt",
            file_path="case_test.txt",
            status="AWAITING_GO_NOGO"
        )
        db.add(rfp)
        db.commit()

        mock_state = {
            "workflow_status": "AWAITING_GO_NOGO",
            "risks": [
                {"category": "A", "severity": "High", "description": "Risk 1"},
                {"category": "B", "severity": "HIGH", "description": "Risk 2"},
                {"category": "C", "severity": "Critical", "description": "Risk 3"},
                {"category": "D", "severity": "CRITICAL", "description": "Risk 4"},
                {"category": "E", "severity": "Medium", "description": "Risk 5"},
                {"category": "F", "severity": "low", "description": "Risk 6"},
            ]
        }

        wf_routes._persist_workflow_results_to_db("rfp_case_test", mock_state)

        risk_resp = client.get("/api/rfp/rfp_case_test/risks")
        assert risk_resp.status_code == 200
        risks = risk_resp.json()["risks"]

        critical_risks = [r for r in risks if (r.get("severity") or "").upper() == "CRITICAL"]
        high_risks = [r for r in risks if (r.get("severity") or "").upper() == "HIGH"]
        medium_risks = [r for r in risks if (r.get("severity") or "").upper() == "MEDIUM"]
        low_risks = [r for r in risks if (r.get("severity") or "").upper() == "LOW"]

        assert len(critical_risks) == 2
        assert len(high_risks) == 2
        assert len(medium_risks) == 1
        assert len(low_risks) == 1
    finally:
        wf_routes.SessionLocal = orig_session_local


def test_12_reopening_rfp_preserves_gate1_metrics():
    """Validates that reopening an existing persisted RFP returns full compliance and risk outputs."""
    import app.api.workflow_routes as wf_routes
    orig_session_local = wf_routes.SessionLocal
    wf_routes.SessionLocal = TestingSessionLocal

    try:
        db = TestingSessionLocal()
        rfp = RFPDocument(
            id="rfp_reopen_test",
            title="Reopen Persistence RFP",
            filename="reopen.pdf",
            file_path="reopen.pdf",
            status="AWAITING_GO_NOGO",
            page_count=5
        )
        db.add(rfp)
        db.commit()

        mock_state = {
            "workflow_status": "AWAITING_GO_NOGO",
            "overall_compliance_score": 92.0,
            "requirements": [
                {"req_code": f"REQ-{i:03d}", "category": "Technical", "priority": "High", "is_mandatory": True, "text": f"Requirement {i}"}
                for i in range(1, 11)
            ],
            "compliance_matrix": [
                {"req_code": f"REQ-{i:03d}", "status": "COMPLIANT", "confidence": 0.9, "evidence_text": f"Evidence {i}", "company_source_doc": "doc.txt"}
                for i in range(1, 11)
            ],
            "risks": [
                {"category": "Technical", "severity": "HIGH", "description": f"Risk {i}"}
                for i in range(1, 6)
            ]
        }

        wf_routes._persist_workflow_results_to_db("rfp_reopen_test", mock_state)

        # Simulate fresh workspace load (GET details, GET status, GET compliance, GET risks)
        details = client.get("/api/rfp/rfp_reopen_test").json()
        assert details["summary_counts"]["requirements"] == 10
        assert details["summary_counts"]["risks"] == 5

        comp = client.get("/api/rfp/rfp_reopen_test/compliance-matrix").json()
        assert len(comp) == 10

        risks = client.get("/api/rfp/rfp_reopen_test/risks").json()["risks"]
        assert len(risks) == 5

        status = client.get("/api/workflow/rfp_reopen_test/status").json()
        assert status["status"] == "AWAITING_GO_NOGO"
        assert status["is_interrupted"] is True
        assert status["interrupt_type"] == "GO_NOGO"
    finally:
        wf_routes.SessionLocal = orig_session_local


def test_13_gate1_recovery_when_checkpoint_missing():
    """Validates that Gate 1 can be resumed (GO) even if in-memory checkpointer lost state."""
    import app.api.workflow_routes as wf_routes
    from app.agents.graph import checkpointer
    orig_session_local = wf_routes.SessionLocal
    wf_routes.SessionLocal = TestingSessionLocal

    try:
        db = TestingSessionLocal()
        rfp_id = "rfp_recon_gate1_test"
        rfp = RFPDocument(
            id=rfp_id,
            title="Gate 1 Lost Checkpoint RFP",
            filename="gate1_lost.pdf",
            file_path="gate1_lost.pdf",
            status="AWAITING_GO_NOGO"
        )
        db.add(rfp)
        db.commit()

        mock_state = {
            "workflow_status": "AWAITING_GO_NOGO",
            "overall_compliance_score": 88.0,
            "requirements": [
                {"req_code": "REQ-001", "category": "Technical", "priority": "High", "is_mandatory": True, "text": "Requirement 1"}
            ],
            "compliance_matrix": [
                {"req_code": "REQ-001", "status": "COMPLIANT", "confidence": 0.95, "evidence_text": "Evidence 1"}
            ],
            "risks": [
                {"category": "Operational", "severity": "MEDIUM", "description": "Risk 1"}
            ]
        }
        wf_routes._persist_workflow_results_to_db(rfp_id, mock_state)

        # Explicitly ensure in-memory checkpointer has no state for this thread (simulate restart)
        if hasattr(checkpointer, "storage") and rfp_id in checkpointer.storage:
            del checkpointer.storage[rfp_id]

        # Verify status endpoint returns interrupted state from DB
        status_res = client.get(f"/api/workflow/{rfp_id}/status")
        assert status_res.status_code == 200
        st = status_res.json()
        assert st["status"] == "AWAITING_GO_NOGO"
        assert st["is_interrupted"] is True
        assert st["interrupt_type"] == "GO_NOGO"

        # Resume Gate 1 with GO decision
        resume_res = client.post(
            f"/api/workflow/{rfp_id}/resume",
            json={"decision": "GO", "notes": "Proceeding with proposal generation"}
        )
        assert resume_res.status_code == 200
        assert "Human input accepted" in resume_res.json()["message"]
    finally:
        wf_routes.SessionLocal = orig_session_local


def test_14_gate1_with_active_checkpoint_happy_path():
    """Validates that existing happy-path works normally when checkpoint is present."""
    import app.api.workflow_routes as wf_routes
    from app.agents.graph import rfp_graph
    orig_session_local = wf_routes.SessionLocal
    wf_routes.SessionLocal = TestingSessionLocal

    try:
        db = TestingSessionLocal()
        rfp_id = "rfp_happy_gate1_test"
        rfp = RFPDocument(
            id=rfp_id,
            title="Happy Gate 1 RFP",
            filename="happy1.pdf",
            file_path="happy1.pdf",
            status="AWAITING_GO_NOGO"
        )
        db.add(rfp)
        db.commit()

        # Pre-populate state in checkpointer
        config = {"configurable": {"thread_id": rfp_id}}
        rfp_graph.update_state(config, {
            "rfp_id": rfp_id,
            "workflow_status": "AWAITING_GO_NOGO",
            "requirements": [{"req_code": "REQ-1", "text": "T"}],
            "compliance_matrix": [{"req_code": "REQ-1", "status": "COMPLIANT"}],
            "risks": []
        }, as_node="assess_risks")

        # Resume Gate 1 with GO
        res = client.post(
            f"/api/workflow/{rfp_id}/resume",
            json={"decision": "GO", "notes": "All good"}
        )
        assert res.status_code == 200
        assert "Human input accepted" in res.json()["message"]
    finally:
        wf_routes.SessionLocal = orig_session_local


def test_15_gate2_recovery_when_checkpoint_missing():
    """Validates that Gate 2 can be resumed (APPROVED) even if in-memory checkpointer lost state."""
    import app.api.workflow_routes as wf_routes
    from app.agents.graph import checkpointer
    orig_session_local = wf_routes.SessionLocal
    wf_routes.SessionLocal = TestingSessionLocal

    try:
        db = TestingSessionLocal()
        rfp_id = "rfp_recon_gate2_test"
        rfp = RFPDocument(
            id=rfp_id,
            title="Gate 2 Lost Checkpoint RFP",
            filename="gate2_lost.pdf",
            file_path="gate2_lost.pdf",
            status="AWAITING_FINAL_APPROVAL"
        )
        db.add(rfp)
        db.commit()

        mock_state = {
            "workflow_status": "AWAITING_FINAL_APPROVAL",
            "overall_compliance_score": 95.0,
            "requirements": [
                {"req_code": "REQ-001", "category": "Technical", "priority": "High", "is_mandatory": True, "text": "Requirement 1"}
            ],
            "compliance_matrix": [
                {"req_code": "REQ-001", "status": "COMPLIANT", "confidence": 0.95, "evidence_text": "Evidence 1"}
            ],
            "risks": [],
            "proposal_drafts": [
                {
                    "version": 1,
                    "title": "Complete Proposal Response",
                    "executive_summary": "Executive summary text.",
                    "full_markdown": "# Proposal\nFull details."
                }
            ],
            "review_reports": [
                {
                    "overall_score": 92,
                    "overall_status": "APPROVED",
                    "feedback": "Ready for client submission."
                }
            ]
        }
        wf_routes._persist_workflow_results_to_db(rfp_id, mock_state)

        # Clear in-memory checkpoint (simulate restart)
        if hasattr(checkpointer, "storage") and rfp_id in checkpointer.storage:
            del checkpointer.storage[rfp_id]

        # Verify status endpoint returns interrupted state from DB
        status_res = client.get(f"/api/workflow/{rfp_id}/status")
        assert status_res.status_code == 200
        st = status_res.json()
        assert st["status"] == "AWAITING_FINAL_APPROVAL"
        assert st["is_interrupted"] is True
        assert st["interrupt_type"] == "FINAL_APPROVAL"

        # Resume Gate 2 with APPROVED decision
        resume_res = client.post(
            f"/api/workflow/{rfp_id}/resume",
            json={"decision": "APPROVED", "feedback": "Final sign-off granted"}
        )
        assert resume_res.status_code == 200
        assert "Human input accepted" in resume_res.json()["message"]
    finally:
        wf_routes.SessionLocal = orig_session_local


def test_16_missing_checkpoint_non_human_gate_returns_400():
    """Validates that missing checkpoint with non-human-gate status returns HTTP 400."""
    import app.api.workflow_routes as wf_routes
    from app.agents.graph import checkpointer
    orig_session_local = wf_routes.SessionLocal
    wf_routes.SessionLocal = TestingSessionLocal

    try:
        db = TestingSessionLocal()
        rfp_id = "rfp_non_gate_fail_test"
        rfp = RFPDocument(
            id=rfp_id,
            title="Processing RFP",
            filename="proc.pdf",
            file_path="proc.pdf",
            status="PROCESSING"
        )
        db.add(rfp)
        db.commit()

        if hasattr(checkpointer, "storage") and rfp_id in checkpointer.storage:
            del checkpointer.storage[rfp_id]

        res = client.post(
            f"/api/workflow/{rfp_id}/resume",
            json={"decision": "GO"}
        )
        assert res.status_code == 400
        assert "Workflow is not currently awaiting human input" in res.json()["detail"]
    finally:
        wf_routes.SessionLocal = orig_session_local


def test_17_recovery_does_not_duplicate_records():
    """Validates that state reconstruction and repeated persistence do not duplicate DB records."""
    import app.api.workflow_routes as wf_routes
    from app.db.models import Requirement, RiskRecord, ClarificationQuestion
    orig_session_local = wf_routes.SessionLocal
    wf_routes.SessionLocal = TestingSessionLocal

    try:
        db = TestingSessionLocal()
        rfp_id = "rfp_no_dups_test"
        rfp = RFPDocument(
            id=rfp_id,
            title="No Duplicates RFP",
            filename="no_dups.pdf",
            file_path="no_dups.pdf",
            status="AWAITING_GO_NOGO"
        )
        db.add(rfp)
        db.commit()

        mock_state = {
            "workflow_status": "AWAITING_GO_NOGO",
            "overall_compliance_score": 90.0,
            "requirements": [
                {"req_code": "REQ-001", "category": "Technical", "priority": "High", "is_mandatory": True, "text": "Requirement 1"},
                {"req_code": "REQ-002", "category": "Security", "priority": "High", "is_mandatory": True, "text": "Requirement 2"}
            ],
            "compliance_matrix": [
                {"req_code": "REQ-001", "status": "COMPLIANT", "confidence": 0.95, "evidence_text": "Evidence 1"},
                {"req_code": "REQ-002", "status": "COMPLIANT", "confidence": 0.90, "evidence_text": "Evidence 2"}
            ],
            "risks": [
                {"category": "Operational", "severity": "MEDIUM", "description": "Risk 1"},
                {"category": "Technical", "severity": "LOW", "description": "Risk 2"}
            ],
            "clarification_questions": [
                {"q_number": 1, "rfp_section_reference": "General", "question_text": "Question 1", "rationale": "Rationale 1"}
            ]
        }
        # Initial persist
        wf_routes._persist_workflow_results_to_db(rfp_id, mock_state)

        # Reconstruct from DB
        recon_state, target_node = wf_routes._reconstruct_state_from_db(rfp_id, db, rfp)
        assert recon_state is not None
        assert target_node == "assess_risks"
        assert len(recon_state["requirements"]) == 2
        assert len(recon_state["risks"]) == 2
        assert len(recon_state["clarification_questions"]) == 1

        # Re-persist reconstructed state
        wf_routes._persist_workflow_results_to_db(rfp_id, recon_state)

        # Verify DB row counts did not duplicate
        req_count = db.query(Requirement).filter(Requirement.rfp_id == rfp_id).count()
        risk_count = db.query(RiskRecord).filter(RiskRecord.rfp_id == rfp_id).count()
        q_count = db.query(ClarificationQuestion).filter(ClarificationQuestion.rfp_id == rfp_id).count()

        assert req_count == 2
        assert risk_count == 2
        assert q_count == 1
    finally:
        wf_routes.SessionLocal = orig_session_local


def test_18_gate1_recovery_exact_node_execution_trace():
    """Validates that Gate 1 recovery routes directly to write_proposal or abort_workflow without re-running extract/assess."""
    from app.agents.graph import rfp_graph

    config = {"configurable": {"thread_id": "test_node_trace_gate1"}}
    reconstructed = {
        "rfp_id": "test_node_trace_gate1",
        "file_path": "dummy.pdf",
        "metadata": {"title": "Test RFP"},
        "requirements": [{"req_code": "REQ-1", "text": "test"}],
        "compliance_matrix": [{"req_code": "REQ-1", "status": "COMPLIANT"}],
        "risks": [{"category": "Tech", "severity": "HIGH", "description": "Risk 1"}],
        "clarification_questions": [],
        "workflow_status": "AWAITING_GO_NOGO",
        "go_nogo_decision": "NO_GO",
        "go_nogo_notes": "Aborting for test",
        "current_version": 0,
        "revision_count": 0,
        "max_revisions": 2,
        "proposal_drafts": [],
        "review_reports": [],
        "logs": []
    }

    # Inject with target_node='assess_risks'
    rfp_graph.update_state(config, reconstructed, as_node="assess_risks")
    state = rfp_graph.get_state(config)
    assert state.next == ("human_go_nogo_gate",)

    executed_nodes = []
    for output in rfp_graph.stream(None, config, stream_mode="updates"):
        if isinstance(output, dict):
            for node_name in output.keys():
                if node_name != "__interrupt__":
                    executed_nodes.append(node_name)

    assert executed_nodes == ["human_go_nogo_gate", "abort_workflow"]
    assert "extract_rfp" not in executed_nodes
    assert "assess_risks" not in executed_nodes
    assert "analyze_compliance" not in executed_nodes
    assert "classify_requirements" not in executed_nodes


def test_19_gate2_recovery_and_status_preserves_revision_count():
    """Validates that Gate 2 DB reconstruction and status endpoint correctly derive revision_count = max(0, version - 1)."""
    from app.db.models import Requirement, ComplianceRecord, Proposal
    db = TestingSessionLocal()
    orig_session_local = wf_routes.SessionLocal
    wf_routes.SessionLocal = TestingSessionLocal
    try:
        rfp_id = "test_gate2_rev_count_sync"
        rfp = RFPDocument(
            id=rfp_id,
            title="Gate 2 Revision Sync RFP",
            filename="test.pdf",
            file_path="dummy.pdf",
            status="AWAITING_FINAL_APPROVAL"
        )
        db.add(rfp)
        db.commit()

        req = Requirement(
            id="req_sync_01",
            rfp_id=rfp_id,
            req_code="REQ-01",
            category="Technical",
            priority="High",
            is_mandatory=True,
            text="Cloud storage"
        )
        db.add(req)
        db.commit()

        comp = ComplianceRecord(
            id="comp_sync_01",
            requirement_id=req.id,
            status="COMPLIANT",
            confidence=0.95,
            evidence_text="Cloud storage evidence"
        )
        db.add(comp)
        db.commit()

        # Add Proposal v1 and Proposal v2
        p1 = Proposal(
            id="prop_sync_01",
            rfp_id=rfp_id,
            version=1,
            title="Proposal Draft v1",
            executive_summary="Summary v1",
            content_markdown="# v1",
            review_score=90,
            review_feedback_json='{"overall_status": "REVISION_REQUIRED", "score": 90, "findings": []}'
        )
        p2 = Proposal(
            id="prop_sync_02",
            rfp_id=rfp_id,
            version=2,
            title="Proposal Draft v2",
            executive_summary="Summary v2",
            content_markdown="# v2",
            review_score=100,
            review_feedback_json='{"overall_status": "APPROVED", "score": 100, "findings": []}'
        )
        db.add_all([p1, p2])
        db.commit()

        # 1. Test _reconstruct_state_from_db
        recon_state, target_node = wf_routes._reconstruct_state_from_db(rfp_id, db, rfp)
        assert recon_state is not None
        assert target_node == "review_proposal"
        assert recon_state["current_version"] == 2
        assert recon_state["revision_count"] == 1, f"Expected revision_count 1 for Proposal v2, got {recon_state['revision_count']}"

        # 2. Test status endpoint when LangGraph checkpointer is empty
        response = client.get(f"/api/workflow/{rfp_id}/status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "AWAITING_FINAL_APPROVAL"
        assert data["current_version"] == 2
        assert data["revision_count"] == 1, f"Expected revision_count 1 from status endpoint, got {data['revision_count']}"
        assert data["is_interrupted"] is True
        assert data["interrupt_type"] == "FINAL_APPROVAL"
    finally:
        wf_routes.SessionLocal = orig_session_local
