from __future__ import annotations

from app.api.common import require_db_session_factory
from app.api.requirement_review_service.documents import _serialize_requirement_review_document
from app.api.requirement_review_service.results import _serialize_requirement_review_result
from app.db.access import (
    get_requirement_review_batch_detail,
    get_requirement_review_overview,
    list_requirement_review_batches,
    parse_uuid,
)
from app.db.session import session_scope
from app.schemas.requirement_review_service import (
    RequirementReviewBatchDetailResponse,
    RequirementReviewBatchListResponse,
    RequirementReviewOverviewResponse,
)
from fastapi import APIRouter, HTTPException, Query, Request

router = APIRouter(tags=["requirement-review-service"])


def _serialize_batch_summary(item: dict[str, object]) -> dict[str, object]:
    latest_created_at = item.get("latest_created_at")
    return {
        "batch_id": item["batch_id"],
        "documents_count": int(item["documents_count"]),
        "results_count": int(item["results_count"]),
        "latest_created_at": latest_created_at.isoformat() if latest_created_at else None,
        "parse_status_summary": item.get("parse_status_summary") or {},
        "quality_gate_summary": item.get("quality_gate_summary") or {},
    }


@router.get("/overview", response_model=RequirementReviewOverviewResponse)
async def get_overview(
    request: Request,
    project_id: str | None = Query(None),
):
    project_uuid = parse_uuid(project_id) if project_id else None
    if project_id and project_uuid is None:
        raise HTTPException(status_code=400, detail="invalid_project_id")
    session_factory = require_db_session_factory(request)
    with session_scope(session_factory) as session:
        overview = get_requirement_review_overview(session, project_id=project_uuid)
        latest_activity_at = overview.get("latest_activity_at")
        return {
            "project_id": str(project_uuid) if project_uuid else None,
            "documents_total": int(overview["documents_total"]),
            "parsed_documents_total": int(overview["parsed_documents_total"]),
            "failed_documents_total": int(overview["failed_documents_total"]),
            "results_total": int(overview["results_total"]),
            "pass_results_total": int(overview["pass_results_total"]),
            "conditional_results_total": int(overview["conditional_results_total"]),
            "fail_results_total": int(overview["fail_results_total"]),
            "latest_batch_id": overview.get("latest_batch_id"),
            "latest_activity_at": latest_activity_at.isoformat() if latest_activity_at else None,
        }


@router.get("/batches", response_model=RequirementReviewBatchListResponse)
async def list_batches(
    request: Request,
    project_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    project_uuid = parse_uuid(project_id) if project_id else None
    if project_id and project_uuid is None:
        raise HTTPException(status_code=400, detail="invalid_project_id")
    session_factory = require_db_session_factory(request)
    with session_scope(session_factory) as session:
        rows, total = list_requirement_review_batches(
            session,
            project_id=project_uuid,
            limit=limit,
            offset=offset,
        )
        return {"items": [_serialize_batch_summary(row) for row in rows], "total": total}


@router.get("/batches/{batch_id}", response_model=RequirementReviewBatchDetailResponse)
async def get_batch_detail(
    request: Request,
    batch_id: str,
    project_id: str | None = Query(None),
    document_limit: int = Query(50, ge=1, le=500),
    document_offset: int = Query(0, ge=0),
    result_limit: int = Query(50, ge=1, le=500),
    result_offset: int = Query(0, ge=0),
):
    project_uuid = parse_uuid(project_id) if project_id else None
    if project_id and project_uuid is None:
        raise HTTPException(status_code=400, detail="invalid_project_id")
    session_factory = require_db_session_factory(request)
    with session_scope(session_factory) as session:
        payload = get_requirement_review_batch_detail(
            session,
            project_id=project_uuid,
            batch_id=batch_id,
            document_limit=document_limit,
            document_offset=document_offset,
            result_limit=result_limit,
            result_offset=result_offset,
        )
        if payload is None:
            raise HTTPException(status_code=404, detail="batch_not_found")
        documents = payload["documents"]
        results = payload["results"]
        return {
            "batch": _serialize_batch_summary(payload["batch"]),
            "documents": {
                "items": [
                    _serialize_requirement_review_document(row)
                    for row in documents["items"]
                ],
                "total": int(documents["total"]),
            },
            "results": {
                "items": [
                    _serialize_requirement_review_result(row)
                    for row in results["items"]
                ],
                "total": int(results["total"]),
            },
        }
