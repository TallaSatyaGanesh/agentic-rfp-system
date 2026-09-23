import pytest
import asyncio
import time
import os
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import app
import app.db.database as db_module
from app.db.models import RFPDocument, Requirement, ComplianceRecord, RiskRecord, ClarificationQuestion, Proposal
from app.api.workflow_routes import broadcast_event_threadsafe, get_event_queue, stream_workflow

@pytest.fixture
def client():
    return TestClient(app)

@pytest.fixture
def test_rfp_id():
    db = db_module.SessionLocal()
    rfp_id = f"test_nb_{int(time.time() * 1000)}"
    sample_file = os.path.abspath("sample_data/sample_rfp_enterprise_cloud.txt")
    
    rfp = RFPDocument(
        id=rfp_id,
        filename="sample_rfp_enterprise_cloud.txt",
        file_path=sample_file,
        file_size=1000,
        page_count=2,
        title="Test Non-Blocking Concurrency RFP",
        status="UPLOADED"
    )
    db.add(rfp)
    db.commit()
    db.close()
    yield rfp_id
    
    # Cleanup
    db = db_module.SessionLocal()
    db.query(ComplianceRecord).filter(ComplianceRecord.requirement_id.like(f"{rfp_id}%")).delete(synchronize_session=False)
    db.query(Requirement).filter(Requirement.rfp_id == rfp_id).delete(synchronize_session=False)
    db.query(RiskRecord).filter(RiskRecord.rfp_id == rfp_id).delete(synchronize_session=False)
    db.query(ClarificationQuestion).filter(ClarificationQuestion.rfp_id == rfp_id).delete(synchronize_session=False)
    db.query(Proposal).filter(Proposal.rfp_id == rfp_id).delete(synchronize_session=False)
    db.query(RFPDocument).filter(RFPDocument.id == rfp_id).delete(synchronize_session=False)
    db.commit()
    db.close()

def test_workflow_start_endpoint_dispatches_task(client, test_rfp_id):
    """
    Verifies that POST /api/workflow/{rfp_id}/start registers status and returns success.
    """
    with patch("app.api.workflow_routes.run_workflow_sync") as mock_worker:
        res_start = client.post(f"/api/workflow/{test_rfp_id}/start")
        assert res_start.status_code == 200
        assert res_start.json()["message"] == "Workflow started successfully"
        assert res_start.json()["rfp_id"] == test_rfp_id
        assert mock_worker.called

def test_threadsafe_event_broadcast():
    """
    Verifies that broadcast_event_threadsafe successfully queues events from synchronous worker contexts.
    """
    rfp_id = f"test_broadcast_{int(time.time() * 1000)}"
    q = get_event_queue(rfp_id)
    
    broadcast_event_threadsafe(rfp_id, "test_event", {"message": "Hello from worker thread"})
    assert not q.empty(), "Event queue should contain the dispatched payload"
    
    item = q.get_nowait()
    assert item["event"] == "test_event"
    assert item["rfp_id"] == rfp_id
    assert item["data"]["message"] == "Hello from worker thread"

@pytest.mark.asyncio
async def test_sse_stream_has_ping_heartbeat(test_rfp_id):
    """
    Verifies that stream_workflow returns EventSourceResponse configured with 15-second heartbeat.
    """
    response = await stream_workflow(test_rfp_id)
    assert response.status_code == 200
    assert response.media_type == "text/event-stream"
    assert getattr(response, "ping_interval", None) == 15

def test_status_endpoint_responsive(client, test_rfp_id):
    """
    Verifies that /api/workflow/{rfp_id}/status responds immediately with current state.
    """
    t0 = time.time()
    res = client.get(f"/api/workflow/{test_rfp_id}/status")
    dur = time.time() - t0
    assert res.status_code == 200
    assert dur < 0.5
    data = res.json()
    assert data["status"] == "UPLOADED"
    assert data["is_interrupted"] is False
