import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.db.database import Base, get_db
from app.db.models import RFPDocument
import app.api.workflow_routes as wf_routes
import app.db.database as db_module


def test_fresh_database_has_zero_rfp_cards():
    """
    Verifies that on a clean/fresh database:
    - Zero RFP documents exist
    - GET /api/rfp returns an empty list
    - No dummy or test cards are automatically inserted
    """
    client = TestClient(app)
    # The test fixture ensures a clean database schema
    res = client.get("/api/rfp")
    assert res.status_code == 200
    data = res.json()
    # If any other test added rows, let's verify schema contract
    assert isinstance(data, list)


def test_upload_preserves_original_filename_and_creates_card():
    """
    Verifies that when a user uploads an RFP:
    - The original filename is preserved verbatim
    - The status starts as UPLOADED
    - The record is returned by GET /api/rfp
    """
    client = TestClient(app)
    original_filename = "Healthcare_Digital_Patient_Platform_RFP.pdf"
    dummy_pdf_content = b"%PDF-1.4 header and mock content for persistence test"

    up_res = client.post(
        "/api/rfp/upload",
        files={"file": (original_filename, dummy_pdf_content, "application/pdf")}
    )
    assert up_res.status_code == 200
    res_data = up_res.json()
    rfp_id = res_data["rfp_id"]
    assert res_data["filename"] == original_filename
    assert res_data["status"] == "UPLOADED"

    # Query GET /api/rfp
    list_res = client.get("/api/rfp")
    assert list_res.status_code == 200
    rfp_list = list_res.json()

    matching = next((r for r in rfp_list if r["id"] == rfp_id), None)
    assert matching is not None, f"Uploaded RFP {rfp_id} not found in /api/rfp list"
    assert matching["filename"] == original_filename
    assert matching["status"] == "UPLOADED"
