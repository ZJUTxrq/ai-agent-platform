from __future__ import annotations

from typing import Any

from app.db import models  # noqa: F401
from app.db.base import Base
from sqlalchemy import inspect, text


def create_core_tables(engine: Any) -> None:
    Base.metadata.create_all(bind=engine)
    _ensure_test_case_document_columns(engine)
    _ensure_test_case_record_columns(engine)
    _ensure_requirement_review_document_indexes(engine)
    _ensure_requirement_review_result_indexes(engine)


def _ensure_test_case_document_columns(engine: Any) -> None:
    inspector = inspect(engine)
    if "test_case_documents" not in set(inspector.get_table_names()):
        return

    existing_columns = {
        str(column.get("name"))
        for column in inspector.get_columns("test_case_documents")
    }
    dialect = str(getattr(engine.dialect, "name", "")).lower()
    statements: list[str] = []

    if "idempotency_key" not in existing_columns:
        statements.append(
            "ALTER TABLE test_case_documents ADD COLUMN idempotency_key VARCHAR(255)"
        )

    if dialect in {"postgresql", "sqlite"}:
        statements.append(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_test_case_documents_project_batch_idempotency "
            "ON test_case_documents (project_id, batch_id, idempotency_key) "
            "WHERE idempotency_key IS NOT NULL"
        )

    if not statements:
        return

    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


def _ensure_test_case_record_columns(engine: Any) -> None:
    inspector = inspect(engine)
    if "test_cases" not in set(inspector.get_table_names()):
        return

    existing_columns = {
        str(column.get("name"))
        for column in inspector.get_columns("test_cases")
    }
    dialect = str(getattr(engine.dialect, "name", "")).lower()
    statements: list[str] = []

    if "idempotency_key" not in existing_columns:
        statements.append(
            "ALTER TABLE test_cases ADD COLUMN idempotency_key VARCHAR(255)"
        )

    if dialect in {"postgresql", "sqlite"}:
        statements.append(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_test_cases_project_batch_idempotency "
            "ON test_cases (project_id, batch_id, idempotency_key) "
            "WHERE idempotency_key IS NOT NULL"
        )

    if not statements:
        return

    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


def _ensure_requirement_review_document_indexes(engine: Any) -> None:
    inspector = inspect(engine)
    if "requirement_review_documents" not in set(inspector.get_table_names()):
        return

    existing_columns = {
        str(column.get("name"))
        for column in inspector.get_columns("requirement_review_documents")
    }
    dialect = str(getattr(engine.dialect, "name", "")).lower()
    statements: list[str] = []

    if "storage_path" not in existing_columns:
        statements.append(
            "ALTER TABLE requirement_review_documents "
            "ADD COLUMN storage_path VARCHAR(1024)"
        )

    if dialect in {"postgresql", "sqlite"}:
        statements.append(
            "CREATE UNIQUE INDEX IF NOT EXISTS "
            "uq_requirement_review_documents_project_batch_idempotency "
            "ON requirement_review_documents (project_id, batch_id, idempotency_key) "
            "WHERE idempotency_key IS NOT NULL"
        )

    if not statements:
        return

    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


def _ensure_requirement_review_result_indexes(engine: Any) -> None:
    inspector = inspect(engine)
    if "requirement_review_results" not in set(inspector.get_table_names()):
        return

    dialect = str(getattr(engine.dialect, "name", "")).lower()
    if dialect not in {"postgresql", "sqlite"}:
        return

    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS "
                "uq_requirement_review_results_project_batch_idempotency "
                "ON requirement_review_results (project_id, batch_id, idempotency_key) "
                "WHERE idempotency_key IS NOT NULL"
            )
        )
