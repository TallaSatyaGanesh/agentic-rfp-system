import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.db.database import get_db, engine, ensure_schema_migrations
from app.db.models import RFPDocument


def test_schema_migration_idempotent():
    """Verifies that ensure_schema_migrations executes idempotently without error."""
    ensure_schema_migrations(engine)


def test_archive_stale_rfp_lifecycle():
    """
    Verifies that an inactive / awaiting go-nogo RFP can be safely archived,
    is excluded from GET /api/rfp by default, included when include_archived=true,
    and can be restored via unarchive.
    """
    client = TestClient(app)
    rfp_id = f"test_archive_lifecycle_{int(datetime.now().timestamp())}"

    # 1. Create a test RFP directly in DB
    db: Session = next(get_db())
    try:
        doc = RFPDocument(
            id=rfp_id,
            filename="Stale_Healthcare_Test_RFP.pdf",
            file_path="mock/path/Stale_Healthcare_Test_RFP.pdf",
            file_size=1024,
            page_count=5,
            title="Stale Healthcare RFP",
            status="AWAITING_GO_NOGO",
        )
        db.add(doc)
        db.commit()
    finally:
        db.close()

    # 2. Verify it shows up in active GET /api/rfp initially
    res = client.get("/api/rfp")
    assert res.status_code == 200
    active_ids = [r["id"] for r in res.json()]
    assert rfp_id in active_ids

    # 3. Archive the RFP
    archive_res = client.post(f"/api/rfp/{rfp_id}/archive")
    assert archive_res.status_code == 200
    archive_data = archive_res.json()
    assert archive_data["id"] == rfp_id
    assert archive_data["archived_at"] is not None
    assert "archived successfully" in archive_data["message"]

    # 4. Confirm it is now EXCLUDED from active GET /api/rfp
    res_after = client.get("/api/rfp")
    assert res_after.status_code == 200
    active_ids_after = [r["id"] for r in res_after.json()]
    assert rfp_id not in active_ids_after, f"Archived RFP {rfp_id} should not appear in active list"

    # 5. Confirm it IS returned when include_archived=true
    res_all = client.get("/api/rfp?include_archived=true")
    assert res_all.status_code == 200
    all_records = {r["id"]: r for r in res_all.json()}
    assert rfp_id in all_records
    assert all_records[rfp_id]["archived_at"] is not None

    # 6. Unarchive the RFP
    unarchive_res = client.post(f"/api/rfp/{rfp_id}/unarchive")
    assert unarchive_res.status_code == 200
    assert unarchive_res.json()["archived_at"] is None

    # 7. Confirm it appears in the active list again
    res_restored = client.get("/api/rfp")
    assert res_restored.status_code == 200
    restored_ids = [r["id"] for r in res_restored.json()]
    assert rfp_id in restored_ids


def test_archive_running_pipeline_is_blocked():
    """Verifies that archiving actively running pipeline states is strictly rejected."""
    client = TestClient(app)
    running_statuses = [
        "PROCESSING",
        "EXTRACTING",
        "CLASSIFYING",
        "ANALYZING_COMPLIANCE",
        "ASSESSING_RISKS",
        "WRITING_PROPOSAL",
        "REVISING",
        "REVIEWING",
    ]

    for status in running_statuses:
        rfp_id = f"test_running_{status.lower()}_{int(datetime.now().timestamp())}"
        db: Session = next(get_db())
        try:
            doc = RFPDocument(
                id=rfp_id,
                filename=f"Running_{status}.pdf",
                file_path=f"mock/path/Running_{status}.pdf",
                file_size=1024,
                page_count=5,
                title=f"Running {status} RFP",
                status=status,
            )
            db.add(doc)
            db.commit()
        finally:
            db.close()

        res = client.post(f"/api/rfp/{rfp_id}/archive")
        assert res.status_code == 400
        assert "actively executing" in res.json()["detail"]


def test_archive_approved_and_completed_projects_is_blocked():
    """Verifies that finalized/approved/completed projects cannot be inadvertently archived."""
    client = TestClient(app)
    protected_statuses = ["APPROVED_FOR_EXPORT", "COMPLETED"]

    for status in protected_statuses:
        rfp_id = f"test_protected_{status.lower()}_{int(datetime.now().timestamp())}"
        db: Session = next(get_db())
        try:
            doc = RFPDocument(
                id=rfp_id,
                filename=f"Protected_{status}.pdf",
                file_path=f"mock/path/Protected_{status}.pdf",
                file_size=1024,
                page_count=5,
                title=f"Protected {status} RFP",
                status=status,
            )
            db.add(doc)
            db.commit()
        finally:
            db.close()

        res = client.post(f"/api/rfp/{rfp_id}/archive")
        assert res.status_code == 400
        assert "Cannot archive approved/completed project" in res.json()["detail"]


def test_archive_nonexistent_rfp_returns_404():
    """Verifies archiving a non-existent RFP returns 404."""
    client = TestClient(app)
    res = client.post("/api/rfp/non_existent_rfp_9999/archive")
    assert res.status_code == 404
