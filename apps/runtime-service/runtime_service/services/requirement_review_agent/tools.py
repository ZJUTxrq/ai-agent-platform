from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from langchain.tools import ToolRuntime
from langchain_core.tools import tool
from runtime_service.integrations import (
    InteractionDataServiceClient,
    build_interaction_data_service_config,
)
from runtime_service.runtime.context import RuntimeContext
from runtime_service.services.requirement_review_agent.document_persistence import (
    INVALID_PROJECT_ID_ERROR,
    MISSING_PROJECT_ID_ERROR,
    _coerce_optional_text,
    _coerce_string_list,
    _get_runtime_state,
    _require_uuid_project_id,
    _resolve_batch_id,
    _resolve_runtime_meta,
    collect_persisted_document_ids,
    persist_requirement_review_documents,
)
from runtime_service.services.requirement_review_agent.schemas import (
    RequirementReviewAgentConfig,
    RequirementReviewResult,
)
from runtime_service.tools.multimodal import read_multimodal_attachments

REQUIREMENT_REVIEW_RESULTS_PATH = "/api/requirement-review-service/results"


def _build_review_idempotency_key(
    *,
    batch_id: str,
    structured_result: RequirementReviewResult,
    runtime_meta: Mapping[str, Any],
) -> str:
    payload = {
        "batch_id": batch_id,
        "thread_id": _coerce_optional_text(runtime_meta.get("thread_id")),
        "review_result": structured_result.model_dump(mode="json"),
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"rr:{hashlib.sha256(encoded).hexdigest()[:40]}"


def build_requirement_review_agent_tools(
    service_config: RequirementReviewAgentConfig,
) -> list[Any]:
    @tool(
        "persist_requirement_review_result",
        description=(
            "Persist the final requirement review result and uploaded requirement documents to "
            "interaction-data-service. Use this only after the review markdown and structured "
            "JSON are finalized."
        ),
    )
    def persist_requirement_review_result(
        requirement_summary: str,
        review_score: int,
        quality_gate: str,
        dimension_scores: dict[str, Any],
        generation_policy: str,
        generation_policy_reason: str,
        runtime: ToolRuntime[RuntimeContext | Mapping[str, Any] | None, dict[str, Any]],
        key_findings: list[str] | None = None,
        major_risks: list[str] | None = None,
        missing_or_ambiguous_items: list[str] | None = None,
        suggestions_to_improve: list[str] | None = None,
        assumptions: list[str] | None = None,
    ) -> str:
        if not service_config.persistence_enabled:
            return json.dumps(
                {
                    "status": "skipped_persistence_disabled",
                    "reason": "requirement_review_persistence_enabled=false",
                },
                ensure_ascii=False,
            )

        try:
            structured_result = RequirementReviewResult.model_validate(
                {
                    "requirement_summary": requirement_summary,
                    "review_score": review_score,
                    "quality_gate": quality_gate,
                    "dimension_scores": dimension_scores,
                    "key_findings": key_findings or [],
                    "major_risks": major_risks or [],
                    "missing_or_ambiguous_items": missing_or_ambiguous_items or [],
                    "suggestions_to_improve": suggestions_to_improve or [],
                    "assumptions": assumptions or [],
                    "generation_policy": generation_policy,
                    "generation_policy_reason": generation_policy_reason,
                }
            )
        except Exception as exc:
            return json.dumps(
                {
                    "status": "failed_invalid_review_result",
                    "reason": str(exc),
                },
                ensure_ascii=False,
            )

        batch_id = _resolve_batch_id(runtime)
        runtime_meta = _resolve_runtime_meta(runtime)
        try:
            project_id = _require_uuid_project_id(runtime)
        except ValueError as exc:
            reason = str(exc)
            status = (
                "failed_missing_project_id"
                if reason == MISSING_PROJECT_ID_ERROR
                else "failed_invalid_project_id"
            )
            return json.dumps(
                {
                    "status": status,
                    "reason": reason,
                    "batch_id": batch_id,
                },
                ensure_ascii=False,
            )

        state = _get_runtime_state(runtime)
        client = InteractionDataServiceClient(
            build_interaction_data_service_config(runtime.config)
        )
        if not client.is_configured:
            return json.dumps(
                {
                    "status": "skipped_remote_not_configured",
                    "project_id": project_id,
                    "batch_id": batch_id,
                },
                ensure_ascii=False,
            )

        document_outcome = persist_requirement_review_documents(
            runtime=runtime,
            state=state,
            service_config=service_config,
            client=client,
            messages=state.get("messages") if isinstance(state.get("messages"), list) else None,
        )
        if isinstance(state, dict):
            state["multimodal_attachments"] = document_outcome.attachments
        document_ids = collect_persisted_document_ids(
            {"multimodal_attachments": document_outcome.attachments}
        )
        if not document_ids and document_outcome.persisted_documents:
            document_ids = _coerce_string_list(
                [item.get("id") for item in document_outcome.persisted_documents]
            )

        payload = {
            "project_id": project_id,
            "batch_id": batch_id,
            "thread_id": runtime_meta.get("thread_id"),
            "idempotency_key": _build_review_idempotency_key(
                batch_id=batch_id,
                structured_result=structured_result,
                runtime_meta=runtime_meta,
            ),
            "document_ids": document_ids,
            "requirement_summary": structured_result.requirement_summary,
            "review_score": structured_result.review_score,
            "quality_gate": structured_result.quality_gate,
            "dimension_scores": structured_result.dimension_scores.model_dump(mode="json"),
            "key_findings": structured_result.key_findings,
            "major_risks": structured_result.major_risks,
            "missing_or_ambiguous_items": structured_result.missing_or_ambiguous_items,
            "suggestions_to_improve": structured_result.suggestions_to_improve,
            "generation_policy": structured_result.generation_policy,
            "generation_policy_reason": structured_result.generation_policy_reason,
            "assumptions": structured_result.assumptions,
            "raw_result": structured_result.model_dump(mode="json"),
        }

        try:
            persisted = client.post_json(REQUIREMENT_REVIEW_RESULTS_PATH, payload)
        except Exception as exc:
            return json.dumps(
                {
                    "status": "failed_remote_request",
                    "project_id": project_id,
                    "batch_id": batch_id,
                    "document_status": document_outcome.status,
                    "persisted_document_count": len(document_ids),
                    "persisted_document_ids": document_ids,
                    "error": str(exc),
                },
                ensure_ascii=False,
            )

        return json.dumps(
            {
                "status": "persisted",
                "project_id": project_id,
                "batch_id": batch_id,
                "document_status": document_outcome.status,
                "persisted_document_count": len(document_ids),
                "persisted_document_ids": document_ids,
                "persisted_result_id": _coerce_optional_text(persisted.get("id")),
            },
            ensure_ascii=False,
        )

    return [persist_requirement_review_result, read_multimodal_attachments]


__all__ = ["build_requirement_review_agent_tools", "REQUIREMENT_REVIEW_RESULTS_PATH"]
