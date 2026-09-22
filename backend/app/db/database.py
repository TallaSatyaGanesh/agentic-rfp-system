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
            # 1. rfp_documents.archived_at
            res_rfp = conn.execute(text("PRAGMA table_info(rfp_documents);")).fetchall()
            rfp_cols = [r[1] for r in res_rfp] if res_rfp else []
            if rfp_cols and "archived_at" not in rfp_cols:
                conn.execute(text("ALTER TABLE rfp_documents ADD COLUMN archived_at DATETIME;"))

            # 2. risk_records.requirement_id
            res_risk = conn.execute(text("PRAGMA table_info(risk_records);")).fetchall()
            risk_cols = [r[1] for r in res_risk] if res_risk else []
            if risk_cols and "requirement_id" not in risk_cols:
                conn.execute(text("ALTER TABLE risk_records ADD COLUMN requirement_id VARCHAR(50);"))

            # 3. clarification_questions.requirement_id
            res_clarif = conn.execute(text("PRAGMA table_info(clarification_questions);")).fetchall()
            clarif_cols = [r[1] for r in res_clarif] if res_clarif else []
            if clarif_cols and "requirement_id" not in clarif_cols:
                conn.execute(text("ALTER TABLE clarification_questions ADD COLUMN requirement_id VARCHAR(50);"))
        else:
            # PostgreSQL / Supabase
            conn.execute(text("ALTER TABLE rfp_documents ADD COLUMN IF NOT EXISTS archived_at TIMESTAMP WITH TIME ZONE;"))
            conn.execute(text("ALTER TABLE risk_records ADD COLUMN IF NOT EXISTS requirement_id VARCHAR(50);"))
            conn.execute(text("ALTER TABLE clarification_questions ADD COLUMN IF NOT EXISTS requirement_id VARCHAR(50);"))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


