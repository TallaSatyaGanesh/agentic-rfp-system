import os
import sys
import tempfile
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Ensure backend directory is in sys.path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

import app.db.database as db_module
import app.api.workflow_routes as wf_routes
from app.main import app
from app.db.database import Base, get_db


@pytest.fixture(scope="session", autouse=True)
def isolate_test_database():
    """
    Creates an isolated temporary SQLite database for the entire test session,
    ensuring that the runtime database (backend/storage/rfp_system.db) is
    NEVER read or modified during automated test runs.
    """
    temp_dir = tempfile.mkdtemp(prefix="rfp_test_db_")
    test_db_path = os.path.join(temp_dir, "isolated_test_rfp.db")
    test_db_url = f"sqlite:///{test_db_path}"

    test_engine = create_engine(
        test_db_url,
        connect_args={"check_same_thread": False}
    )
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    # Save original references
    orig_engine = db_module.engine
    orig_session_local = db_module.SessionLocal
    orig_wf_session_local = getattr(wf_routes, "SessionLocal", None)

    # Patch global engine and SessionLocal
    db_module.engine = test_engine
    db_module.SessionLocal = TestSessionLocal
    wf_routes.SessionLocal = TestSessionLocal

    def test_get_db():
        db = TestSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = test_get_db

    # Create tables on test database
    Base.metadata.create_all(bind=test_engine)

    yield {
        "engine": test_engine,
        "SessionLocal": TestSessionLocal,
        "db_path": test_db_path
    }

    # Teardown
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=test_engine)
    test_engine.dispose()

    # Restore original references
    db_module.engine = orig_engine
    db_module.SessionLocal = orig_session_local
    if orig_wf_session_local is not None:
        wf_routes.SessionLocal = orig_wf_session_local

    try:
        if os.path.exists(test_db_path):
            os.remove(test_db_path)
        if os.path.exists(temp_dir):
            os.rmdir(temp_dir)
    except OSError:
        pass


@pytest.fixture(autouse=True)
def restore_dependency_overrides_after_test():
    """Ensures test_get_db remains active even if an individual test clears overrides."""
    yield
    # Re-apply session test_get_db if cleared by another fixture
    if get_db not in app.dependency_overrides:
        def test_get_db():
            db = db_module.SessionLocal()
            try:
                yield db
            finally:
                db.close()
        app.dependency_overrides[get_db] = test_get_db
