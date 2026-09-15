from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import List
import os
from pathlib import Path

# Base project paths
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
STORAGE_DIR = BACKEND_DIR / "storage"

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    ENVIRONMENT: str = "development"
    PORT: int = 8000
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173"
    
    # LLM Settings
    LLM_PROVIDER: str = "openai"  # openai, gemini, or mock
    OPENAI_API_KEY: str = Field(default="")
    OPENAI_MODEL: str = "gpt-4o-mini"
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"
    
    GEMINI_API_KEY: str = Field(default="")
    GEMINI_MODEL: str = "gemini-1.5-flash"
    
    # Storage and Database
    DATABASE_URL: str = f"sqlite:///{STORAGE_DIR / 'rfp_system.db'}"
    CHROMA_PERSIST_DIRECTORY: str = str(STORAGE_DIR / "chromadb")
    UPLOAD_DIR: str = str(STORAGE_DIR / "uploads")
    EXPORT_DIR: str = str(STORAGE_DIR / "exports")
    
    # RAG and Agent Limits
    SIMILARITY_THRESHOLD: float = 0.35
    RAG_TOP_K: int = 4
    MAX_REVISION_CYCLES: int = 2
    REVIEW_PASS_SCORE: int = 80

    @property
    def cors_origin_list(self) -> List[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

settings = Settings()

# Ensure directories exist
os.makedirs(STORAGE_DIR, exist_ok=True)
os.makedirs(settings.CHROMA_PERSIST_DIRECTORY, exist_ok=True)
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
os.makedirs(settings.EXPORT_DIR, exist_ok=True)
os.makedirs(os.path.join(settings.UPLOAD_DIR, "rfp"), exist_ok=True)
os.makedirs(os.path.join(settings.UPLOAD_DIR, "company"), exist_ok=True)
