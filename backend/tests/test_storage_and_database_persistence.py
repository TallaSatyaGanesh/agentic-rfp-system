import os
import tempfile
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import settings
from app.db.database import normalize_db_url
from app.services.storage_service import StorageService
from app.db.models import RFPDocument


def test_postgres_url_normalization():
    """Verifies that legacy postgres:// URLs are normalized to postgresql:// for SQLAlchemy."""
    raw_supabase_url = "postgres://postgres.abcdef:secret_pass@aws-0-us-east-1.pooler.supabase.com:6543/postgres"
    normalized = normalize_db_url(raw_supabase_url)
    assert normalized.startswith("postgresql://")
    assert "postgres.abcdef:secret_pass" in normalized

    # Already standard postgresql URL remains untouched
    std_url = "postgresql://user:pass@localhost:5432/db"
    assert normalize_db_url(std_url) == std_url

    # SQLite URL remains untouched
    sqlite_url = "sqlite:///backend/storage/rfp_system.db"
    assert normalize_db_url(sqlite_url) == sqlite_url


def test_storage_service_local_mode():
    """Verifies StorageService operates seamlessly in local mode when Supabase is disabled."""
    with patch.object(settings, "SUPABASE_URL", ""), patch.object(settings, "SUPABASE_KEY", ""):
        assert StorageService.is_supabase_enabled() is False

        rfp_id = "test_local_storage_001"
        filename = "Sample_Local_Test_RFP.pdf"
        sample_bytes = b"%PDF-1.4 Mock Local RFP content for unit testing"

        local_path = StorageService.upload_rfp_document(rfp_id, filename, sample_bytes)
        assert os.path.exists(local_path)
        with open(local_path, "rb") as f:
            assert f.read() == sample_bytes

        # Ensure local file check
        ensured_path = StorageService.ensure_local_file(local_path, rfp_id, filename)
        assert ensured_path == local_path
        assert os.path.exists(ensured_path)


def test_storage_service_supabase_mode_mocked():
    """Verifies StorageService uploads and recovers files from Supabase Storage using mocked HTTP."""
    with patch.object(settings, "SUPABASE_URL", "https://mock-project.supabase.co"), \
         patch.object(settings, "SUPABASE_KEY", "mock-service-role-key"), \
         patch.object(settings, "SUPABASE_STORAGE_BUCKET", "rfp-documents"):

        assert StorageService.is_supabase_enabled() is True

        rfp_id = "test_supabase_mock_001"
        filename = "Enterprise_Patient_Platform_RFP.pdf"
        sample_bytes = b"%PDF-1.4 Mock Supabase remote document content"

        # Mock httpx.Client post for upload
        mock_post_res = MagicMock()
        mock_post_res.status_code = 200

        mock_get_res = MagicMock()
        mock_get_res.status_code = 200
        mock_get_res.content = sample_bytes

        with patch("httpx.Client.post", return_value=mock_post_res) as mock_post, \
             patch("httpx.Client.get", return_value=mock_get_res) as mock_get:

            # 1. Upload
            local_path = StorageService.upload_rfp_document(rfp_id, filename, sample_bytes)
            assert os.path.exists(local_path)
            assert mock_post.called

            # 2. Simulate local cache deletion (Render restart simulation)
            if os.path.exists(local_path):
                os.remove(local_path)
            assert not os.path.exists(local_path)

            # 3. Recovery via ensure_local_file
            recovered_path = StorageService.ensure_local_file(local_path, rfp_id, filename)
            assert recovered_path is not None
            assert os.path.exists(recovered_path)
            with open(recovered_path, "rb") as f:
                assert f.read() == sample_bytes
            assert mock_get.called


def test_api_upload_and_filename_preservation_e2e():
    """Verifies end-to-end API upload preserves the exact original filename in both DB and storage."""
    client = TestClient(app)
    original_filename = "Healthcare_Digital_Patient_Platform_RFP.pdf"
    content = b"%PDF-1.4 header and mock content for e2e storage persistence test"

    res = client.post(
        "/api/rfp/upload",
        files={"file": (original_filename, content, "application/pdf")}
    )
    assert res.status_code == 200
    data = res.json()
    assert data["filename"] == original_filename
    assert data["status"] == "UPLOADED"
    rfp_id = data["rfp_id"]

    # Verify GET /api/rfp returns exact filename
    list_res = client.get("/api/rfp")
    assert list_res.status_code == 200
    records = list_res.json()
    item = next((r for r in records if r["id"] == rfp_id), None)
    assert item is not None
    assert item["filename"] == original_filename
    assert item["status"] == "UPLOADED"
