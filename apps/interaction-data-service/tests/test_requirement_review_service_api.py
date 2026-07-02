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

from app.api.requirement_review_service.aggregates import (  # noqa: E402
    get_batch_detail,
    get_overview,
    list_batches,
)
from app.api.requirement_review_service.documents import (  # noqa: E402
    create_document_asset,
    create_document,
    download_document_asset,
    get_single_document,
    list_documents,
    patch_document,
    preview_document_asset,
    remove_document,
)
from app.api.requirement_review_service.results import (  # noqa: E402
    create_result,
    get_single_result,
    list_results,
    patch_result,
    remove_result,
)
from app.db.init_db import create_core_tables  # noqa: E402
from app.schemas.requirement_review_service import (  # noqa: E402
    CreateRequirementReviewDocumentRequest,
    CreateRequirementReviewResultRequest,
    UpdateRequirementReviewDocumentRequest,
    UpdateRequirementReviewResultRequest,
)


def _build_fake_request(session_factory: sessionmaker) -> Any:
    return cast(
        Any,
        SimpleNamespace(
            app=SimpleNamespace(
                state=SimpleNamespace(
                    db_session_factory=session_factory,
                    document_asset_root="",
                )
            )
        ),
    )


def _build_test_context(tmp_path: Path) -> tuple[Any, sessionmaker]:
    db_path = tmp_path / "interaction-data-requirement-review.db"
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
    request = _build_fake_request(session_factory)
    request.app.state.document_asset_root = str((tmp_path / "document-assets").resolve())
    return request, session_factory


def test_requirement_review_service_persists_documents_results_and_aggregates(
    tmp_path: Path,
) -> None:
    request, _ = _build_test_context(tmp_path)
    project_id = str(uuid.uuid4())
    other_project_id = str(uuid.uuid4())
    batch_id = "requirement-review:thread-1"

    document = asyncio.run(
        create_document(
            request,
            CreateRequirementReviewDocumentRequest(
                project_id=project_id,
                batch_id=batch_id,
                thread_id="thread-1",
                idempotency_key="doc:prd:v1",
                filename="requirement-review-sample.pdf",
                content_type="application/pdf",
                storage_path="requirement-review/demo/batch-1/sample.pdf",
                parse_status="parsed",
                summary_for_model="coupon requirement summary",
                parsed_text="coupon flow covers claim, inventory and expiry",
                structured_data={"modules": ["coupon"]},
                provenance={"runtime": {"agent_key": "requirement_review_agent"}},
            ),
        )
    )

    result = asyncio.run(
        create_result(
            request,
            CreateRequirementReviewResultRequest(
                project_id=project_id,
                batch_id=batch_id,
                thread_id="thread-1",
                idempotency_key="review:thread-1:prd",
                document_ids=[document["id"]],
                requirement_summary="requirement is mostly complete",
                review_score=78,
                quality_gate="conditional",
                dimension_scores={"business_objective": 18, "testability": 17},
                key_findings=["claim flow is clear"],
                major_risks=["refund restore rule is incomplete"],
                missing_or_ambiguous_items=["compensation after inventory deduction failure"],
                suggestions_to_improve=["add concurrent claim and refund restore rules"],
                generation_policy="allow_generation_with_assumptions",
                generation_policy_reason="test case generation can proceed with explicit assumptions",
                assumptions=["coupon is not stackable by default"],
                raw_result={"quality_gate": "conditional", "review_score": 78},
            ),
        )
    )

    asyncio.run(
        create_result(
            request,
            CreateRequirementReviewResultRequest(
                project_id=other_project_id,
                batch_id="requirement-review:other",
                idempotency_key="review:other",
                document_ids=[],
                requirement_summary="other project requirement",
                review_score=50,
                quality_gate="fail",
                generation_policy="block_generation",
            ),
        )
    )

    listed_documents = asyncio.run(
        list_documents(
            request,
            project_id=project_id,
            batch_id=batch_id,
            parse_status=None,
            query="sample",
            limit=20,
            offset=0,
        )
    )
    assert listed_documents["total"] == 1
    assert listed_documents["items"][0]["id"] == document["id"]
    assert listed_documents["items"][0]["storage_path"] == "requirement-review/demo/batch-1/sample.pdf"

    listed_results = asyncio.run(
        list_results(
            request,
            project_id=project_id,
            batch_id=batch_id,
            quality_gate="conditional",
            generation_policy=None,
            query="mostly complete",
            limit=20,
            offset=0,
        )
    )
    assert listed_results["total"] == 1
    assert listed_results["items"][0]["id"] == result["id"]

    overview = asyncio.run(get_overview(request, project_id=project_id))
    assert overview["documents_total"] == 1
    assert overview["parsed_documents_total"] == 1
    assert overview["results_total"] == 1
    assert overview["conditional_results_total"] == 1
    assert overview["pass_results_total"] == 0
    assert overview["fail_results_total"] == 0
    assert overview["latest_batch_id"] == batch_id

    batches = asyncio.run(list_batches(request, project_id=project_id, limit=20, offset=0))
    assert batches["total"] == 1
    assert batches["items"][0]["batch_id"] == batch_id
    assert batches["items"][0]["documents_count"] == 1
    assert batches["items"][0]["results_count"] == 1
    assert batches["items"][0]["parse_status_summary"] == {"parsed": 1}
    assert batches["items"][0]["quality_gate_summary"] == {"conditional": 1}

    batch_detail = asyncio.run(
        get_batch_detail(
            request,
            batch_id=batch_id,
            project_id=project_id,
            document_limit=20,
            document_offset=0,
            result_limit=20,
            result_offset=0,
        )
    )
    assert batch_detail["batch"]["batch_id"] == batch_id
    assert batch_detail["documents"]["total"] == 1
    assert batch_detail["documents"]["items"][0]["id"] == document["id"]
    assert batch_detail["results"]["total"] == 1
    assert batch_detail["results"]["items"][0]["id"] == result["id"]

    single_document = asyncio.run(get_single_document(request, document["id"]))
    assert single_document["id"] == document["id"]
    assert single_document["storage_path"] == "requirement-review/demo/batch-1/sample.pdf"
    single_result = asyncio.run(get_single_result(request, result["id"]))
    assert single_result["id"] == result["id"]

    updated_document = asyncio.run(
        patch_document(
            request,
            document["id"],
            UpdateRequirementReviewDocumentRequest(
                filename="requirement-review-updated.pdf",
                storage_path="requirement-review/demo/batch-1/updated.pdf",
                parse_status="failed",
                summary_for_model="updated summary",
                parsed_text="updated parsed text",
                structured_data={"modules": ["coupon", "refund"]},
                provenance={"runtime": {"agent_key": "requirement_review_agent", "version": "v2"}},
                error={"message": "parser warning"},
            ),
        )
    )
    assert updated_document["filename"] == "requirement-review-updated.pdf"
    assert updated_document["storage_path"] == "requirement-review/demo/batch-1/updated.pdf"
    assert updated_document["parse_status"] == "failed"
    assert updated_document["error"] == {"message": "parser warning"}

    updated_result = asyncio.run(
        patch_result(
            request,
            result["id"],
            UpdateRequirementReviewResultRequest(
                review_score=81,
                quality_gate="pass",
                generation_policy="allow_generation",
                generation_policy_reason="rules clarified",
                key_findings=["claim flow is clear", "expiry rule is clarified"],
                assumptions=["inventory is deducted atomically"],
            ),
        )
    )
    assert updated_result["review_score"] == 81
    assert updated_result["quality_gate"] == "pass"
    assert updated_result["generation_policy"] == "allow_generation"

    asyncio.run(remove_result(request, result["id"]))
    remaining_results = asyncio.run(
        list_results(
            request,
            project_id=project_id,
            batch_id=batch_id,
            quality_gate=None,
            generation_policy=None,
            query=None,
            limit=20,
            offset=0,
        )
    )
    assert remaining_results["total"] == 0

    asyncio.run(remove_document(request, document["id"]))
    remaining_documents = asyncio.run(
        list_documents(
            request,
            project_id=project_id,
            batch_id=batch_id,
            parse_status=None,
            query=None,
            limit=20,
            offset=0,
        )
    )
    assert remaining_documents["total"] == 0


def test_requirement_review_document_asset_upload_preview_and_download(tmp_path: Path) -> None:
    request, _ = _build_test_context(tmp_path)
    project_id = str(uuid.uuid4())
    batch_id = "requirement-review:asset-batch"
    pdf_bytes = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF"

    class _UploadFile:
        filename = "requirement-review-asset.pdf"
        content_type = "application/pdf"

        async def read(self) -> bytes:
            return pdf_bytes

    upload = asyncio.run(
        create_document_asset(
            request,
            project_id=project_id,
            batch_id=batch_id,
            idempotency_key="asset:prd:v1",
            filename="requirement-review-asset.pdf",
            content_type="application/pdf",
            file=_UploadFile(),
        )
    )
    assert upload["storage_path"].startswith(f"requirement-review/{project_id}/{batch_id}/")

    document = asyncio.run(
        create_document(
            request,
            CreateRequirementReviewDocumentRequest(
                project_id=project_id,
                batch_id=batch_id,
                thread_id="thread-asset-1",
                idempotency_key="doc:asset:v1",
                filename="requirement-review-asset.pdf",
                content_type="application/pdf",
                storage_path=upload["storage_path"],
                parse_status="parsed",
                summary_for_model="asset summary",
                provenance={"asset": upload},
            ),
        )
    )

    preview_response = asyncio.run(preview_document_asset(request, document["id"]))
    download_response = asyncio.run(download_document_asset(request, document["id"]))
    assert preview_response.media_type == "application/pdf"
    assert download_response.media_type == "application/pdf"
    assert "inline;" in preview_response.headers["content-disposition"]
    assert "attachment;" in download_response.headers["content-disposition"]
