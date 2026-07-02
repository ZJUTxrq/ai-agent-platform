from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.modules.requirement_review.application.contracts import (
    CreateRequirementReviewDocumentCommand,
    ExportRequirementReviewResultsQuery,
    UpdateRequirementReviewResultCommand,
)
from app.modules.requirement_review.application.service import RequirementReviewService


class RequirementReviewServiceRegressionTest(unittest.TestCase):
    def test_ensure_project_match_normalizes_project_id(self) -> None:
        service = RequirementReviewService(
            session_factory=None,
            upstream=SimpleNamespace(),
        )

        payload = service._ensure_project_match(
            {"project_id": " project-1 ", "id": "result-1"},
            project_id="project-1",
            code="requirement_review_result_not_found",
        )

        self.assertEqual(payload["id"], "result-1")

    def test_resolve_role_marks_editor_as_writable(self) -> None:
        service = RequirementReviewService(
            session_factory=None,
            upstream=SimpleNamespace(),
        )
        actor = SimpleNamespace(
            has_platform_role=lambda role: False,
            project_role_set=lambda project_id: ["project_editor"],
        )

        role = service._resolve_role(actor=actor, project_id="project-1")

        self.assertEqual(role, "editor")

    def test_update_result_normalizes_payload_and_uses_patch(self) -> None:
        upstream = SimpleNamespace(
            require_json=AsyncMock(
                return_value={
                    "id": "result-1",
                    "project_id": "project-1",
                    "batch_id": "batch-2",
                    "thread_id": "thread-2",
                    "idempotency_key": None,
                    "document_ids": ["doc-1"],
                    "requirement_summary": "updated summary",
                    "review_score": 88,
                    "quality_gate": "pass",
                    "dimension_scores": {},
                    "key_findings": [],
                    "major_risks": [],
                    "missing_or_ambiguous_items": [],
                    "suggestions_to_improve": [],
                    "generation_policy": "allow_generation",
                    "generation_policy_reason": "",
                    "assumptions": [],
                    "raw_result": {},
                    "created_at": "2026-06-20T00:00:00Z",
                    "updated_at": "2026-06-20T00:00:01Z",
                }
            )
        )
        service = RequirementReviewService(session_factory=None, upstream=upstream)
        service._prepare_project_scope = AsyncMock()  # type: ignore[method-assign]
        service.get_result = AsyncMock(  # type: ignore[method-assign]
            return_value=SimpleNamespace(id="result-1")
        )
        actor = SimpleNamespace()

        result = asyncio.run(
            service.update_result(
                actor=actor,
                project_id="project-1",
                result_id="result-1",
                command=UpdateRequirementReviewResultCommand(
                    batch_id=" batch-2 ",
                    quality_gate=" pass ",
                    generation_policy=" allow_generation ",
                    requirement_summary="updated summary",
                    review_score=88,
                ),
            )
        )

        self.assertEqual(result.id, "result-1")
        upstream.require_json.assert_awaited_once()
        method, path = upstream.require_json.await_args.args[:2]
        payload = upstream.require_json.await_args.kwargs["payload"]
        self.assertEqual(method, "PATCH")
        self.assertEqual(path, "/api/requirement-review-service/results/result-1")
        self.assertEqual(payload["batch_id"], "batch-2")
        self.assertEqual(payload["quality_gate"], "pass")
        self.assertEqual(payload["generation_policy"], "allow_generation")

    def test_create_document_includes_project_id_and_uses_post(self) -> None:
        upstream = SimpleNamespace(
            require_json=AsyncMock(
                return_value={
                    "id": "doc-1",
                    "project_id": "project-1",
                    "batch_id": "batch-1",
                    "thread_id": "thread-1",
                    "idempotency_key": None,
                    "filename": "prd.pdf",
                    "content_type": "application/pdf",
                    "source_kind": "upload",
                    "parse_status": "parsed",
                    "summary_for_model": "summary",
                    "parsed_text": "body",
                    "structured_data": {},
                    "provenance": {},
                    "error": None,
                    "created_at": "2026-06-20T00:00:00Z",
                    "updated_at": "2026-06-20T00:00:00Z",
                }
            )
        )
        service = RequirementReviewService(session_factory=None, upstream=upstream)
        service._prepare_project_scope = AsyncMock()  # type: ignore[method-assign]
        actor = SimpleNamespace()

        result = asyncio.run(
            service.create_document(
                actor=actor,
                project_id="project-1",
                command=CreateRequirementReviewDocumentCommand(
                    batch_id=" batch-1 ",
                    thread_id=" thread-1 ",
                    filename="prd.pdf",
                    content_type="application/pdf",
                ),
            )
        )

        self.assertEqual(result.id, "doc-1")
        method, path = upstream.require_json.await_args.args[:2]
        payload = upstream.require_json.await_args.kwargs["payload"]
        self.assertEqual(method, "POST")
        self.assertEqual(path, "/api/requirement-review-service/documents")
        self.assertEqual(payload["project_id"], "project-1")
        self.assertEqual(payload["batch_id"], "batch-1")
        self.assertEqual(payload["thread_id"], "thread-1")

    def test_export_results_builds_workbook(self) -> None:
        service = RequirementReviewService(session_factory=None, upstream=SimpleNamespace())
        service._prepare_project_scope = AsyncMock()  # type: ignore[method-assign]
        service._list_all_results_for_export = AsyncMock(  # type: ignore[method-assign]
            return_value=[
                {
                    "id": "result-1",
                    "project_id": "project-1",
                    "batch_id": "batch-1",
                    "thread_id": "thread-1",
                    "document_ids": ["doc-1"],
                    "requirement_summary": "summary",
                    "review_score": 81,
                    "quality_gate": "conditional",
                    "dimension_scores": {"testability": 17},
                    "key_findings": ["finding-1"],
                    "major_risks": ["risk-1"],
                    "missing_or_ambiguous_items": ["gap-1"],
                    "suggestions_to_improve": ["suggestion-1"],
                    "generation_policy": "allow_generation_with_assumptions",
                    "generation_policy_reason": "reason",
                    "assumptions": ["assumption-1"],
                    "raw_result": {"ok": True},
                    "created_at": "2026-06-20T00:00:00Z",
                    "updated_at": "2026-06-20T00:00:00Z",
                }
            ]
        )
        actor = SimpleNamespace()

        filename, media_type, payload = asyncio.run(
            service.export_results(
                actor=actor,
                project_id="project-1",
                query=ExportRequirementReviewResultsQuery(
                    batch_id="batch-1",
                    quality_gate="conditional",
                ),
            )
        )

        self.assertTrue(filename.startswith("requirement-review-results-"))
        self.assertEqual(
            media_type,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        self.assertGreater(len(payload), 0)


if __name__ == "__main__":
    unittest.main()
