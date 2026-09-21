from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

def normalize_db_url(url: str) -> str:
    """
    Normalizes PostgreSQL connection strings:
    - Replaces legacy postgres:// with standard postgresql://
    - Ensures standard driver compatibility
    """
    if not url:
        return url
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql://", 1)
    return url

db_url = normalize_db_url(settings.DATABASE_URL)
is_sqlite = "sqlite" in db_url.lower()

engine_kwargs = {}
if is_sqlite:
    engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    # PostgreSQL / Supabase pooler settings
    engine_kwargs.update({
        "pool_pre_ping": True,
        "pool_recycle": 300,
        "pool_size": 5,
        "max_overflow": 10
    })

engine = create_engine(db_url, **engine_kwargs)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

from sqlalchemy import text

def ensure_schema_migrations(bind_engine):
    """
    Safely runs idempotent schema additions across PostgreSQL and SQLite
    for columns introduced in incremental updates.
    """
    url_str = str(bind_engine.url).lower()
    with bind_engine.begin() as conn:
        if "sqlite" in url_str:
            # Check if archived_at column exists in rfp_documents
            res = conn.execute(text("PRAGMA table_info(rfp_documents);")).fetchall()
            col_names = [r[1] for r in res] if res else []
            if col_names and "archived_at" not in col_names:
                conn.execute(text("ALTER TABLE rfp_documents ADD COLUMN archived_at DATETIME;"))
        else:
            # PostgreSQL / Supabase
            conn.execute(text("ALTER TABLE rfp_documents ADD COLUMN IF NOT EXISTS archived_at TIMESTAMP WITH TIME ZONE;"))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


