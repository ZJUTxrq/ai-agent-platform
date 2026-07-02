from __future__ import annotations

from app.api.common import require_db_session_factory
from app.db.access import (
    create_requirement_review_result,
    delete_requirement_review_result,
    get_requirement_review_result,
    list_requirement_review_results,
    parse_uuid,
    update_requirement_review_result,
)
from app.db.session import session_scope
from app.schemas.requirement_review_service import (
    CreateRequirementReviewResultRequest,
    RequirementReviewResultListResponse,
    RequirementReviewResultResponse,
    UpdateRequirementReviewResultRequest,
)
from fastapi import APIRouter, HTTPException, Query, Request

router = APIRouter(prefix="/results", tags=["requirement-review-service"])


def _serialize_requirement_review_result(row) -> dict[str, object]:
    return {
        "id": str(row.id),
        "project_id": str(row.project_id),
        "batch_id": row.batch_id,
        "thread_id": row.thread_id,
        "idempotency_key": row.idempotency_key,
        "document_ids": row.document_ids,
        "requirement_summary": row.requirement_summary,
        "review_score": row.review_score,
        "quality_gate": row.quality_gate,
        "dimension_scores": row.dimension_scores,
        "key_findings": row.key_findings,
        "major_risks": row.major_risks,
        "missing_or_ambiguous_items": row.missing_or_ambiguous_items,
        "suggestions_to_improve": row.suggestions_to_improve,
        "generation_policy": row.generation_policy,
        "generation_policy_reason": row.generation_policy_reason,
        "assumptions": row.assumptions,
        "raw_result": row.raw_result,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


@router.post("", response_model=RequirementReviewResultResponse)
async def create_result(request: Request, payload: CreateRequirementReviewResultRequest):
    project_id = parse_uuid(payload.project_id)
    if project_id is None:
        raise HTTPException(status_code=400, detail="invalid_project_id")
    session_factory = require_db_session_factory(request)
    with session_scope(session_factory) as session:
        row = create_requirement_review_result(
            session,
            project_id=project_id,
            batch_id=payload.batch_id,
            thread_id=payload.thread_id,
            idempotency_key=payload.idempotency_key,
            document_ids=payload.document_ids,
            requirement_summary=payload.requirement_summary,
            review_score=payload.review_score,
            quality_gate=payload.quality_gate,
            dimension_scores=payload.dimension_scores,
            key_findings=payload.key_findings,
            major_risks=payload.major_risks,
            missing_or_ambiguous_items=payload.missing_or_ambiguous_items,
            suggestions_to_improve=payload.suggestions_to_improve,
            generation_policy=payload.generation_policy,
            generation_policy_reason=payload.generation_policy_reason,
            assumptions=payload.assumptions,
            raw_result=payload.raw_result,
        )
        return _serialize_requirement_review_result(row)


@router.get("", response_model=RequirementReviewResultListResponse)
async def list_results(
    request: Request,
    project_id: str | None = Query(None),
    batch_id: str | None = Query(None),
    quality_gate: str | None = Query(None),
    generation_policy: str | None = Query(None),
    query: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    project_uuid = parse_uuid(project_id) if project_id else None
    if project_id and project_uuid is None:
        raise HTTPException(status_code=400, detail="invalid_project_id")
    session_factory = require_db_session_factory(request)
    with session_scope(session_factory) as session:
        rows, total = list_requirement_review_results(
            session,
            project_id=project_uuid,
            batch_id=batch_id,
            quality_gate=quality_gate,
            generation_policy=generation_policy,
            query=query,
            limit=limit,
            offset=offset,
        )
        return {
            "items": [_serialize_requirement_review_result(row) for row in rows],
            "total": total,
        }


@router.get("/{result_id}", response_model=RequirementReviewResultResponse)
async def get_single_result(request: Request, result_id: str):
    result_uuid = parse_uuid(result_id)
    if result_uuid is None:
        raise HTTPException(status_code=400, detail="invalid_result_id")
    session_factory = require_db_session_factory(request)
    with session_scope(session_factory) as session:
        row = get_requirement_review_result(session, result_uuid)
        if row is None:
            raise HTTPException(status_code=404, detail="result_not_found")
        return _serialize_requirement_review_result(row)


@router.patch("/{result_id}", response_model=RequirementReviewResultResponse)
async def patch_result(
    request: Request,
    result_id: str,
    payload: UpdateRequirementReviewResultRequest,
):
    result_uuid = parse_uuid(result_id)
    if result_uuid is None:
        raise HTTPException(status_code=400, detail="invalid_result_id")
    session_factory = require_db_session_factory(request)
    with session_scope(session_factory) as session:
        row = get_requirement_review_result(session, result_uuid)
        if row is None:
            raise HTTPException(status_code=404, detail="result_not_found")
        row = update_requirement_review_result(
            session,
            row,
            batch_id=payload.batch_id,
            thread_id=payload.thread_id,
            document_ids=payload.document_ids,
            requirement_summary=payload.requirement_summary,
            review_score=payload.review_score,
            quality_gate=payload.quality_gate,
            dimension_scores=payload.dimension_scores,
            key_findings=payload.key_findings,
            major_risks=payload.major_risks,
            missing_or_ambiguous_items=payload.missing_or_ambiguous_items,
            suggestions_to_improve=payload.suggestions_to_improve,
            generation_policy=payload.generation_policy,
            generation_policy_reason=payload.generation_policy_reason,
            assumptions=payload.assumptions,
            raw_result=payload.raw_result,
        )
        return _serialize_requirement_review_result(row)


@router.delete("/{result_id}")
async def remove_result(request: Request, result_id: str):
    result_uuid = parse_uuid(result_id)
    if result_uuid is None:
        raise HTTPException(status_code=400, detail="invalid_result_id")
    session_factory = require_db_session_factory(request)
    with session_scope(session_factory) as session:
        row = get_requirement_review_result(session, result_uuid)
        if row is None:
            raise HTTPException(status_code=404, detail="result_not_found")
        delete_requirement_review_result(session, row)
        return {"ok": True}
