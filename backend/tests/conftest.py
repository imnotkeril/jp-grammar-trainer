from __future__ import annotations

import os
import uuid
from collections.abc import Generator
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base, get_db
from app.main import app
from app.models.grammar import Grammar
from app.models.grammar_progress import GrammarProgress, GrammarStatus
from app.models.question import Question, QuestionSource, ValidationStatus

# Integration tests (routers/*, services/review.py) need a real Postgres — the schema uses
# Postgres-only types (JSONB, ARRAY, native ENUM) that SQLite can't represent. Point this at a
# disposable local/CI Postgres via TEST_DATABASE_URL; defaults to the throwaway container used
# during Phase 2 development (see ARCHITECTURE.md §9 task 2.4-2.6). Tests that need a DB are
# skipped automatically when it isn't reachable, so `uv run pytest` still passes in an
# environment with no Postgres available (matching the pure-unit-test suite that existed
# before this task).
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://postgres:test@localhost:5544/jp_grammar_test"
)


def _db_available() -> bool:
    try:
        # short connect_timeout: an unreachable host must fail fast, not hang the whole
        # `pytest` invocation waiting on a TCP timeout.
        engine = create_engine(TEST_DATABASE_URL, connect_args={"connect_timeout": 2})
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
        return True
    except Exception:  # noqa: BLE001 — any connection failure means "skip DB tests"
        return False


DB_AVAILABLE = _db_available()

requires_db = pytest.mark.skipif(not DB_AVAILABLE, reason=f"no Postgres reachable at {TEST_DATABASE_URL}")


@pytest.fixture(scope="session")
def engine():  # type: ignore[no-untyped-def]
    if not DB_AVAILABLE:
        pytest.skip(f"no Postgres reachable at {TEST_DATABASE_URL}")
    eng = create_engine(TEST_DATABASE_URL)
    # Start from a clean, fully-reset schema each test session — independent of whatever
    # state `alembic upgrade head` may have left the DB in (this fixture uses the ORM
    # metadata directly, not the migration, so table/enum drift between the two would
    # otherwise cause confusing failures).
    with eng.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture()
def db_session(engine) -> Generator[Session, None, None]:  # type: ignore[no-untyped-def]
    """One transaction per test, rolled back at the end — tests never see each other's data."""
    connection = engine.connect()
    transaction = connection.begin()
    TestingSessionLocal = sessionmaker(bind=connection, autoflush=False, autocommit=False)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture()
def client(db_session: Session) -> Generator[TestClient, None, None]:
    def _override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def make_grammar(
    db: Session,
    *,
    target_construction: str,
    pattern_text: str = "Паттерн: テスト / Значение: test",
    meaning_ru: str = "тестовое значение",
    source_note_id: int | None = None,
) -> Grammar:
    grammar = Grammar(
        source_note_id=source_note_id or int(uuid.uuid4().int % 10_000_000_000),
        expression_html=f"text<b>{target_construction}</b>text",
        expression_clean=f"text{target_construction}text",
        reading=target_construction,
        meaning_ru=meaning_ru,
        pattern_text=pattern_text,
        formation_rules=[],
        level="N3",
        tags=[],
        target_construction=target_construction,
    )
    db.add(grammar)
    db.flush()
    return grammar


def make_progress(
    db: Session,
    grammar: Grammar,
    *,
    status: GrammarStatus = GrammarStatus.NEW,
    next_review: datetime | None = None,
) -> GrammarProgress:
    progress = GrammarProgress(
        grammar_id=grammar.id,
        status=status,
        next_review=next_review or datetime.now(timezone.utc),
    )
    db.add(progress)
    db.flush()
    return progress


def make_question(
    db: Session,
    grammar: Grammar,
    *,
    correct_text: str | None = None,
    distractor_texts: tuple[str, str, str] = ("A案", "B案", "C案"),
    validation_status: ValidationStatus = ValidationStatus.VALID,
    used_count: int = 0,
) -> Question:
    correct = correct_text or grammar.target_construction
    keys = ["A", "B", "C", "D"]
    texts = [correct, *distractor_texts]
    options = [{"key": k, "text": t} for k, t in zip(keys, texts, strict=True)]
    question = Question(
        grammar_id=grammar.id,
        sentence_with_blank_html="___を使う。",
        sentence_full_html=f"<b>{correct}</b>を使う。",
        options=options,
        correct_option="A",
        explanation_ru="説明。",
        source=QuestionSource.SEED,
        validation_status=validation_status,
        used_count=used_count,
    )
    db.add(question)
    db.flush()
    return question
