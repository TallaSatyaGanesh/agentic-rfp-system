import os
import tempfile
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import settings
from app.db.database import get_db
import app.db.database as db_module
from app.db.models import CompanyDocument
from app.services.storage_service import StorageService
from app.rag.retriever import KnowledgeBaseRetriever
from app.rag.vector_store import VectorStoreManager


def test_company_document_upload_supabase_sync_mocked():
    """
    Verifies that when Supabase is enabled, uploading a company document
    syncs bytes to Supabase Storage at company/{doc_id}/{filename}.
    """
    with patch.object(settings, "SUPABASE_URL", "https://mock-project.supabase.co"), \
         patch.object(settings, "SUPABASE_KEY", "mock-key"), \
         patch.object(settings, "SUPABASE_STORAGE_BUCKET", "rfp-documents"):

        assert StorageService.is_supabase_enabled() is True

        mock_post = MagicMock()
        mock_post.status_code = 200

        doc_id = "doc_sync_test_001"
        filename = "Demo_Platform_Spec.txt"
        sample_bytes = b"Demo Company provides an enterprise software platform."

        with patch("httpx.Client.post", return_value=mock_post) as post_call:
            local_path = StorageService.upload_company_document(doc_id, filename, sample_bytes)
            assert os.path.exists(local_path)
            assert post_call.called

            # Check remote URL
            url_called = post_call.call_args[0][0]
            assert f"company/{doc_id}/{filename}" in url_called


def test_ensure_local_company_file_recovery_from_supabase():
    """
    Verifies that when a local file is missing on container restart,
    ensure_local_company_file pulls it from Supabase Storage.
    """
    with patch.object(settings, "SUPABASE_URL", "https://mock-project.supabase.co"), \
         patch.object(settings, "SUPABASE_KEY", "mock-key"), \
         patch.object(settings, "SUPABASE_STORAGE_BUCKET", "rfp-documents"):

        doc_id = "doc_recover_test_002"
        filename = "Demo_Security_Doc.txt"
        sample_bytes = b"Demo Company enforces granular role-based access control and governance."

        mock_get = MagicMock()
        mock_get.status_code = 200
        mock_get.content = sample_bytes

        with patch("httpx.Client.get", return_value=mock_get) as get_call:
            missing_path = os.path.join(settings.UPLOAD_DIR, "company", f"{doc_id}_{filename}")
            if os.path.exists(missing_path):
                os.remove(missing_path)
            assert not os.path.exists(missing_path)

            recovered_path = StorageService.ensure_local_company_file(missing_path, doc_id, filename)
            assert recovered_path is not None
            assert os.path.exists(recovered_path)
            with open(recovered_path, "rb") as f:
                assert f.read() == sample_bytes
            assert get_call.called


def test_sync_knowledge_base_from_db_idempotency_and_recovery(tmp_path):
    """
    Verifies that:
    1. An empty ChromaDB automatically syncs and indexes registered CompanyDocument records.
    2. Repeated synchronization is idempotent and does not create duplicate vectors.
    """
    client = TestClient(app)
    db = db_module.SessionLocal()
    doc_id = "doc_demo_sync_001"
    filename = "Demo_Test_Overview.txt"

    # Create local source file
    doc_content = "Demo Company provides an enterprise software platform designed to coordinate web applications across business workflows with strict access governance."
    local_dir = os.path.join(settings.UPLOAD_DIR, "company")
    os.makedirs(local_dir, exist_ok=True)
    file_path = os.path.join(local_dir, f"{doc_id}_{filename}")
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(doc_content)

    try:
        # Register in database
        company_doc = CompanyDocument(
            id=doc_id,
            title="Demo Company Test Overview",
            filename=filename,
            file_path=file_path,
            category="Technical",
            chunk_count=1
        )
        db.add(company_doc)
        db.commit()

        retriever = KnowledgeBaseRetriever()

        # 1. Clear ChromaDB to simulate fresh container launch
        retriever.vector_store.clear()
        assert retriever.vector_store._collection.count() == 0

        # 2. Run sync_knowledge_base_from_db
        synced = retriever.sync_knowledge_base_from_db(db)
        assert synced == 1
        count_after_first = retriever.vector_store._collection.count()
        assert count_after_first > 0

        # 3. Test search retrieval against recovered vector
        results = retriever.retrieve_relevant_evidence("enterprise software platform access governance", top_k=3, threshold=0.1)
        assert len(results) > 0
        assert any(r["company_doc_id"] == doc_id for r in results)

        # 4. Run second sync -> MUST be idempotent (0 new synced, same vector count)
        synced_second = retriever.sync_knowledge_base_from_db(db)
        assert synced_second == 0
        assert retriever.vector_store._collection.count() == count_after_first

    finally:
        # Cleanup
        rec = db.query(CompanyDocument).filter(CompanyDocument.id == doc_id).first()
        if rec:
            db.delete(rec)
            db.commit()
        db.close()


def test_reindex_api_endpoint():
    """Verifies POST /api/company-knowledge/reindex endpoint."""
    client = TestClient(app)
    res = client.post("/api/company-knowledge/reindex")
    assert res.status_code == 200
    data = res.json()
    assert "synchronized into ChromaDB" in data["message"]
    assert "total_documents" in data
    assert "synchronized_count" in data
