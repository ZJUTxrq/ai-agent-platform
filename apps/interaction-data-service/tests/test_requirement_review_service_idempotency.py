from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from app.api.requirement_review_service.documents import create_document, list_documents  # noqa: E402
from app.api.requirement_review_service.results import create_result, list_results  # noqa: E402
from app.db.init_db import create_core_tables  # noqa: E402
from app.schemas.requirement_review_service import (  # noqa: E402
    CreateRequirementReviewDocumentRequest,
    CreateRequirementReviewResultRequest,
)


def _build_fake_request(session_factory: sessionmaker) -> Any:
    return cast(
        Any,
        SimpleNamespace(
            app=SimpleNamespace(
                state=SimpleNamespace(
                    db_session_factory=session_factory,
                )
            )
        ),
    )


def _build_test_context(tmp_path: Path) -> Any:
    db_path = tmp_path / "interaction-data-requirement-review-idempotency.db"
    engine = create_engine(
        f"sqlite+pysqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    create_core_tables(engine)
    session_factory = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )
    return _build_fake_request(session_factory)


def test_create_requirement_review_document_reuses_existing_row_when_idempotency_key_matches(
    tmp_path: Path,
) -> None:
    request = _build_test_context(tmp_path)
    project_id = str(uuid.uuid4())
    batch_id = "requirement-review:idempotency"
    idempotency_key = "doc:requirement:v1"

    first = asyncio.run(
        create_document(
            request,
            CreateRequirementReviewDocumentRequest(
                project_id=project_id,
                batch_id=batch_id,
                thread_id="thread-idempotency",
                idempotency_key=idempotency_key,
                filename="requirement-review-sample.pdf",
                content_type="application/pdf",
                parse_status="parsed",
                summary_for_model="initial summary",
                parsed_text="initial text",
                structured_data={"version": 1},
                provenance={"runtime": {"run_id": "run-1"}},
            ),
        )
    )
    second = asyncio.run(
        create_document(
            request,
            CreateRequirementReviewDocumentRequest(
                project_id=project_id,
                batch_id=batch_id,
                thread_id="thread-idempotency",
                idempotency_key=idempotency_key,
                filename="requirement-review-sample-updated.pdf",
                content_type="application/pdf",
                parse_status="failed",
                summary_for_model="updated summary",
                parsed_text="updated text",
                structured_data={"version": 2},
                provenance={"runtime": {"run_id": "run-2"}},
                error={"message": "parser_failed"},
            ),
        )
    )

    assert first["id"] == second["id"]
    assert second["filename"] == "requirement-review-sample-updated.pdf"
    assert second["parse_status"] == "failed"
    assert second["summary_for_model"] == "updated summary"
    assert second["structured_data"] == {"version": 2}
    assert second["error"] == {"message": "parser_failed"}

    listing = asyncio.run(
        list_documents(
            request,
            project_id=project_id,
            batch_id=batch_id,
            parse_status=None,
            query="updated",
            limit=20,
            offset=0,
        )
    )
    assert listing["total"] == 1
    assert listing["items"][0]["id"] == first["id"]


def test_create_requirement_review_result_reuses_existing_row_when_idempotency_key_matches(
    tmp_path: Path,
) -> None:
    request = _build_test_context(tmp_path)
    project_id = str(uuid.uuid4())
    batch_id = "requirement-review:idempotency"
    idempotency_key = "review:thread:prd"

    first = asyncio.run(
        create_result(
            request,
            CreateRequirementReviewResultRequest(
                project_id=project_id,
                batch_id=batch_id,
                thread_id="thread-idempotency",
                idempotency_key=idempotency_key,
                document_ids=["doc-1"],
                requirement_summary="initial review summary",
                review_score=70,
                quality_gate="conditional",
                dimension_scores={"testability": 16},
                key_findings=["initial finding"],
                major_risks=["initial risk"],
                missing_or_ambiguous_items=["initial gap"],
                suggestions_to_improve=["initial suggestion"],
                generation_policy="allow_generation_with_assumptions",
                generation_policy_reason="initial reason",
                assumptions=["initial assumption"],
                raw_result={"version": 1},
            ),
        )
    )
    second = asyncio.run(
        create_result(
            request,
            CreateRequirementReviewResultRequest(
                project_id=project_id,
                batch_id=batch_id,
                thread_id="thread-idempotency",
                idempotency_key=idempotency_key,
                document_ids=["doc-2"],
                requirement_summary="updated review summary",
                review_score=91,
                quality_gate="pass",
                dimension_scores={"testability": 19},
                key_findings=["updated finding"],
                major_risks=[],
                missing_or_ambiguous_items=[],
                suggestions_to_improve=["updated suggestion"],
                generation_policy="allow_generation",
                generation_policy_reason="updated reason",
                assumptions=[],
                raw_result={"version": 2},
            ),
        )
    )

    assert first["id"] == second["id"]
    assert second["document_ids"] == ["doc-2"]
    assert second["review_score"] == 91
    assert second["quality_gate"] == "pass"
    assert second["generation_policy"] == "allow_generation"
    assert second["raw_result"] == {"version": 2}

    listing = asyncio.run(
        list_results(
            request,
            project_id=project_id,
            batch_id=batch_id,
            quality_gate="pass",
            generation_policy=None,
            query="updated",
            limit=20,
            offset=0,
        )
    )
    assert listing["total"] == 1
    assert listing["items"][0]["id"] == first["id"]
