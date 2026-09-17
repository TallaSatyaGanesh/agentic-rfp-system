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
