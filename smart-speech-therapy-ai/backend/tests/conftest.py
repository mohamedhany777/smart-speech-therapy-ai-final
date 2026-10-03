import os

os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("STORAGE_LOCAL_PATH", "./test_storage")
os.environ.setdefault("QDRANT_PATH", "./test_qdrant_storage")
# Disable rate limiting by default so unrelated tests hitting /auth/login or
# the AI endpoints many times in a loop don't flake with 429s; the dedicated
# rate-limit tests override this per-request via the app's dependency_overrides.
os.environ.setdefault("RATE_LIMIT_LOGIN_PER_MINUTE", "0")
os.environ.setdefault("RATE_LIMIT_AI_PER_MINUTE", "0")

import shutil  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.db.session import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.rbac import DEFAULT_PERMISSIONS, DEFAULT_ROLES, Permission, Role  # noqa: E402
from app.models.user import User  # noqa: E402
from app.security.tokens import create_access_token, hash_password  # noqa: E402

TEST_DATABASE_URL = "sqlite:///:memory:"

# StaticPool + check_same_thread=False: TestClient dispatches requests onto a
# worker thread pool, so the in-memory SQLite DB needs a single shared
# connection across threads, or each thread sees an empty (fresh) database.
engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="session", autouse=True)
def setup_database():
    Base.metadata.create_all(bind=engine)

    # Background tasks (assessment processing) open their own DB session
    # via app.db.session.SessionLocal directly, bypassing FastAPI's
    # dependency-injection override below — patch the module attribute
    # itself so background tasks in tests also hit the in-memory test DB
    # instead of trying to open the real (non-existent, in tests)
    # configured database.
    import app.db.session as db_session_module

    original_session_local = db_session_module.SessionLocal
    db_session_module.SessionLocal = TestingSessionLocal

    db = TestingSessionLocal()
    permissions_by_code = {}
    for code, description in DEFAULT_PERMISSIONS.items():
        perm = Permission(code=code, description=description)
        db.add(perm)
        permissions_by_code[code] = perm
    db.flush()

    for role_name, perm_codes in DEFAULT_ROLES.items():
        role = Role(name=role_name, description=f"{role_name} role")
        role.permissions = [permissions_by_code[c] for c in perm_codes]
        db.add(role)
    db.commit()
    db.close()

    yield
    Base.metadata.drop_all(bind=engine)
    db_session_module.SessionLocal = original_session_local
    shutil.rmtree(os.environ["STORAGE_LOCAL_PATH"], ignore_errors=True)
    shutil.rmtree(os.environ["QDRANT_PATH"], ignore_errors=True)
    for db_file in ("test.db",):
        if os.path.exists(db_file):
            os.remove(db_file)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture()
def client():
    return TestClient(app)


def _create_user_with_role(role_name: str, email: str) -> str:
    """Create a user directly against the DB with a given role (bypassing
    the register endpoint, which always assigns USER) and return a bearer
    access token for it."""
    db = TestingSessionLocal()
    try:
        role = db.scalar(select(Role).where(Role.name == role_name))
        user = User(
            email=email,
            hashed_password=hash_password("StrongPass123"),
            full_name=f"{role_name} Test User",
            preferred_language="en",
            is_active=True,
            is_email_verified=True,
            roles=[role],
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return create_access_token(subject=str(user.id), roles=[role_name])
    finally:
        db.close()


@pytest.fixture()
def admin_token():
    import uuid

    return _create_user_with_role("ADMIN", f"admin-{uuid.uuid4().hex}@example.com")


@pytest.fixture()
def specialist_token():
    import uuid

    return _create_user_with_role("SPECIALIST", f"specialist-{uuid.uuid4().hex}@example.com")


@pytest.fixture()
def user_token():
    import uuid

    return _create_user_with_role("USER", f"regularuser-{uuid.uuid4().hex}@example.com")


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def wait_for_assessment(client, token, assessment_id, timeout=15, interval=0.2):
    """Poll GET /assessments/{id} until background processing finishes
    (status leaves pending/processing) or timeout — background tasks now
    run asynchronously (see assessment_service's load-handling design), so
    tests exercise that real path instead of assuming synchronous
    completion."""
    import time

    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = client.get(f"/api/v1/assessments/{assessment_id}", headers=auth_headers(token))
        assessment = resp.json()
        if assessment["status"] not in ("pending", "processing"):
            return assessment
        time.sleep(interval)
    raise TimeoutError(f"Assessment {assessment_id} did not finish processing within {timeout}s")
