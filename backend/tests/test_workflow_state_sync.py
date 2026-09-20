import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.main import app
from app.db.database import Base, get_db
from app.db.models import RFPDocument
from app.agents.graph import rfp_graph

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
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    app.dependency_overrides.clear()
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
    finally:
        wf_routes.SessionLocal = orig_session_local

