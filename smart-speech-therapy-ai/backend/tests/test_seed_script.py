"""Direct test of scripts/seed.py's content-seeding functions, run against
an isolated in-memory database (not the shared test.db used by the rest of
the suite) so it's never affected by data other tests may have already
created, and vice versa."""
import importlib
import sys
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base
from app.models.disorders import Disorder, DisorderCategory
from app.models.exercises import Exercise
from app.models.games import Game
from app.models.knowledge_base import KnowledgeDocument
from app.models.rbac import Role
from app.models.user import User

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


def _load_seed_module():
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    if "seed" in sys.modules:
        importlib.reload(sys.modules["seed"])
        return sys.modules["seed"]
    return importlib.import_module("seed")


def _fresh_session():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return SessionLocal()


def test_seed_script_creates_full_expected_content():
    seed = _load_seed_module()
    db = _fresh_session()

    roles_by_name = seed.seed_roles_and_permissions(db)
    assert set(roles_by_name.keys()) == {"USER", "SPECIALIST", "ADMIN"}

    seed.seed_first_admin(db, roles_by_name)
    seed.seed_first_specialist(db, roles_by_name)
    seed.seed_sample_content(db)

    assert db.query(DisorderCategory).count() == 6
    assert db.query(Disorder).count() == 9
    assert db.query(Exercise).count() == 20
    assert db.query(Game).count() == 5
    assert db.query(KnowledgeDocument).count() == 9
    # Every seeded KB document must have actually finished indexing —
    # the seed script isn't exempt from the same honesty rule the upload
    # endpoint follows (spec section 6): a document claiming to exist
    # without being searchable would be misleading.
    assert all(d.status == "INDEXED" for d in db.query(KnowledgeDocument).all())
    assert all(len(d.chunks) > 0 for d in db.query(KnowledgeDocument).all())

    # Every disorder must have the full required page structure (spec
    # section 17): Overview, Characteristics, Speech Features, Assessment
    # Considerations — none left blank.
    for disorder in db.query(Disorder).all():
        assert disorder.overview and len(disorder.overview) > 20
        assert disorder.possible_characteristics
        assert disorder.speech_features
        assert disorder.assessment_notes

    # Every disorder should have at least one linked exercise (spec section
    # 17: "Relevant Exercises").
    for disorder in db.query(Disorder).all():
        linked = db.scalar(select(Exercise).where(Exercise.disorder_id == disorder.id))
        assert linked is not None, f"disorder '{disorder.slug}' has no linked exercise"

    admin = db.scalar(select(User).where(User.email == "admin@example.com"))
    specialist = db.scalar(select(User).where(User.email == "specialist@example.com"))
    assert admin is not None and any(r.name == "ADMIN" for r in admin.roles)
    assert specialist is not None and any(r.name == "SPECIALIST" for r in specialist.roles)

    db.close()


def test_seed_script_is_idempotent():
    """Running the seed functions twice must not duplicate content or error
    (spec section: a redeploy/restart must not corrupt seeded data)."""
    seed = _load_seed_module()
    db = _fresh_session()

    roles_by_name = seed.seed_roles_and_permissions(db)
    seed.seed_first_admin(db, roles_by_name)
    seed.seed_first_specialist(db, roles_by_name)
    seed.seed_sample_content(db)

    # Second pass — should be a safe no-op (roles/admin/specialist have
    # explicit existing-check guards; seed_sample_content bails out early
    # if any DisorderCategory already exists).
    seed.seed_roles_and_permissions(db)
    seed.seed_first_admin(db, roles_by_name)
    seed.seed_first_specialist(db, roles_by_name)
    seed.seed_sample_content(db)

    assert db.query(Role).count() == 3
    assert db.query(User).count() == 2
    assert db.query(DisorderCategory).count() == 6
    assert db.query(Disorder).count() == 9

    db.close()
