import os
import shutil
import logging
from typing import Optional
import httpx
from app.core.config import settings

logger = logging.getLogger(__name__)


class StorageService:
    """
    Dual-mode Storage Service:
    1. Remote Mode: When SUPABASE_URL and SUPABASE_KEY are provided, syncs files
       to/from Supabase Storage bucket ('rfp-documents' by default).
    2. Local Mode: When Supabase credentials are not set (local dev / pytest),
       operates seamlessly on local disk directories.
    """

    @classmethod
    def is_supabase_enabled(cls) -> bool:
        """Returns True if Supabase Storage credentials are configured."""
        return bool(settings.SUPABASE_URL and settings.SUPABASE_KEY)

    @classmethod
    def get_headers(cls) -> dict:
        """Constructs authentication headers for Supabase REST API."""
        return {
            "Authorization": f"Bearer {settings.SUPABASE_KEY}",
            "apikey": settings.SUPABASE_KEY
        }

    @classmethod
    def _build_storage_url(cls, remote_path: str) -> str:
        """Constructs the Supabase Storage object endpoint URL."""
        import re
        raw_url = settings.SUPABASE_URL.strip().rstrip("/")
        clean_domain = re.sub(r"^(https?:/*)+", "", raw_url)
        base_url = f"https://{clean_domain}"
        bucket = settings.SUPABASE_STORAGE_BUCKET
        clean_path = remote_path.lstrip("/")
        return f"{base_url}/storage/v1/object/{bucket}/{clean_path}"

    @classmethod
    def _sanitize_log_message(cls, message: str) -> str:
        """Removes any accidental occurrences of SUPABASE_KEY from log messages."""
        if settings.SUPABASE_KEY and settings.SUPABASE_KEY in message:
            return message.replace(settings.SUPABASE_KEY, "[REDACTED]")
        return message

    @classmethod
    def upload_rfp_document(cls, rfp_id: str, filename: str, content_bytes: bytes) -> str:
        """
        Saves uploaded RFP document to local staging path and syncs to Supabase Storage if enabled.
        Returns the canonical local file path for immediate parsing.
        Raises an exception if Supabase is enabled and the remote upload fails.
        """
        # 1. Local staging write
        local_dir = os.path.join(settings.UPLOAD_DIR, "rfp", rfp_id)
        os.makedirs(local_dir, exist_ok=True)
        local_path = os.path.join(local_dir, filename)

        with open(local_path, "wb") as f:
            f.write(content_bytes)

        # 2. Remote Supabase Storage sync (only if Supabase is enabled)
        if cls.is_supabase_enabled():
            remote_path = f"rfps/{rfp_id}/{filename}"
            cls._upload_to_supabase(remote_path, content_bytes)
            logger.info(
                f"[StorageService] Successfully synced RFP {rfp_id} ({filename}) to Supabase Storage: {remote_path}"
            )

        return local_path

    @classmethod
    def archive_proposal_export(cls, filename: str, content_bytes: bytes) -> Optional[str]:
        """
        Saves proposal DOCX export locally and syncs to Supabase Storage if enabled.
        Returns the remote path or local path.
        Raises an exception if Supabase is enabled and the remote upload fails.
        """
        local_path = os.path.join(settings.EXPORT_DIR, filename)
        os.makedirs(settings.EXPORT_DIR, exist_ok=True)

        with open(local_path, "wb") as f:
            f.write(content_bytes)

        if cls.is_supabase_enabled():
            remote_path = f"exports/{filename}"
            cls._upload_to_supabase(remote_path, content_bytes)
            logger.info(
                f"[StorageService] Successfully archived proposal export ({filename}) to Supabase Storage: {remote_path}"
            )
            return remote_path

        return local_path

    @classmethod
    def ensure_local_file(cls, file_path: str, rfp_id: str, filename: str) -> Optional[str]:
        """
        Guarantees the document exists on the local filesystem before workflow parsing starts.
        If the file exists locally, returns file_path immediately.
        If missing locally (e.g. after a Render container restart/spin-down) but Supabase is enabled,
        downloads the file from Supabase Storage to the local cache and returns the path.
        """
        # Check local existence
        if file_path and os.path.exists(file_path):
            return file_path

        # Determine target local cache destination
        local_dir = os.path.join(settings.UPLOAD_DIR, "rfp", rfp_id)
        os.makedirs(local_dir, exist_ok=True)
        target_path = file_path if file_path else os.path.join(local_dir, filename)

        if os.path.exists(target_path):
            return target_path

        # If Supabase is enabled, pull remote document
        if cls.is_supabase_enabled():
            remote_path = f"rfps/{rfp_id}/{filename}"
            try:
                downloaded_bytes = cls._download_from_supabase(remote_path)
                if downloaded_bytes:
                    with open(target_path, "wb") as f:
                        f.write(downloaded_bytes)
                    logger.info(
                        f"[StorageService] Recovered RFP {rfp_id} from Supabase Storage to local cache: {target_path}"
                    )
                    return target_path
            except Exception as e:
                err_str = cls._sanitize_log_message(f"{type(e).__name__}: {str(e)}")
    @classmethod
    def upload_company_document(cls, doc_id: str, filename: str, content_bytes: bytes) -> str:
        """
        Saves uploaded company knowledge document to local staging path and syncs to Supabase Storage if enabled.
        Returns the canonical local file path for immediate parsing.
        Raises an exception if Supabase is enabled and the remote upload fails.
        """
        local_dir = os.path.join(settings.UPLOAD_DIR, "company")
        os.makedirs(local_dir, exist_ok=True)
        local_path = os.path.join(local_dir, f"{doc_id}_{filename}")

        with open(local_path, "wb") as f:
            f.write(content_bytes)

        if cls.is_supabase_enabled():
            remote_path = f"company/{doc_id}/{filename}"
            cls._upload_to_supabase(remote_path, content_bytes)
            logger.info(
                f"[StorageService] Successfully synced company document {doc_id} ({filename}) to Supabase Storage: {remote_path}"
            )

        return local_path

    @classmethod
    def ensure_local_company_file(cls, file_path: str, doc_id: str, filename: str) -> Optional[str]:
        """
        Guarantees company document exists on local filesystem before chunking/indexing.
        If file exists locally, returns file_path immediately.
        If missing locally (e.g. after a Render container restart/spin-down) but Supabase is enabled,
        downloads from Supabase Storage and returns the local path.
        """
        if file_path and os.path.exists(file_path):
            return file_path

        local_dir = os.path.join(settings.UPLOAD_DIR, "company")
        os.makedirs(local_dir, exist_ok=True)
        target_path = file_path if file_path else os.path.join(local_dir, f"{doc_id}_{filename}")

        if os.path.exists(target_path):
            return target_path

        if cls.is_supabase_enabled():
            remote_path = f"company/{doc_id}/{filename}"
            try:
                downloaded_bytes = cls._download_from_supabase(remote_path)
                if downloaded_bytes:
                    with open(target_path, "wb") as f:
                        f.write(downloaded_bytes)
                    logger.info(
                        f"[StorageService] Recovered company document {doc_id} from Supabase Storage to local cache: {target_path}"
                    )
                    return target_path
            except Exception as e:
                err_str = cls._sanitize_log_message(f"{type(e).__name__}: {str(e)}")
                logger.error(
                    f"[StorageService] Error recovering company document from Supabase Storage ({remote_path}): {err_str}"
                )

        return None

    @classmethod
    def _upload_to_supabase(cls, remote_path: str, content_bytes: bytes) -> bool:
        """
        Internal helper: Uploads bytes to Supabase Storage object endpoint.
        Raises a RuntimeError containing the HTTP status and response body if status is not 200 or 201.
        """
        url = cls._build_storage_url(remote_path)
        headers = cls.get_headers()
        headers["x-upsert"] = "true"

        # Auto-detect content-type based on extension
        ext = os.path.splitext(remote_path)[1].lower()
        content_type = "application/octet-stream"
        if ext == ".pdf":
            content_type = "application/pdf"
        elif ext in [".docx", ".doc"]:
            content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        elif ext in [".txt", ".md"]:
            content_type = "text/plain"

        with httpx.Client(timeout=30.0, verify=False) as client:
            res = client.post(url, headers=headers, content=content_bytes)
            if res.status_code in [200, 201]:
                return True
            else:
                err_msg = cls._sanitize_log_message(
                    f"Supabase Storage upload failed for '{remote_path}' "
                    f"with HTTP {res.status_code}: {res.text}"
                )
                logger.error(f"[StorageService] {err_msg}")
                raise RuntimeError(err_msg)

    @classmethod
    def _download_from_supabase(cls, remote_path: str) -> Optional[bytes]:
        """Internal helper: Downloads bytes from Supabase Storage object endpoint."""
        url = cls._build_storage_url(remote_path)
        headers = cls.get_headers()

        with httpx.Client(timeout=30.0, verify=False) as client:
            res = client.get(url, headers=headers)
            if res.status_code == 200:
                return res.content
            else:
                err_msg = cls._sanitize_log_message(
                    f"Supabase Storage download for '{remote_path}' "
                    f"returned HTTP {res.status_code}: {res.text}"
                )
                logger.warning(f"[StorageService] {err_msg}")
                return None
