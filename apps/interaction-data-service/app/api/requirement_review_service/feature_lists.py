from __future__ import annotations

from app.api.common import require_db_session_factory
from app.db.access import (
    confirm_requirement_feature_list,
    create_requirement_feature_list,
    delete_requirement_feature_list,
    get_requirement_feature_list,
    list_requirement_feature_lists,
    parse_uuid,
    update_requirement_feature_list,
)
from app.db.session import session_scope
from app.schemas.requirement_review_service import (
    ConfirmRequirementFeatureListRequest,
    CreateRequirementFeatureListRequest,
    RequirementFeatureListListResponse,
    RequirementFeatureListResponse,
    UpdateRequirementFeatureListRequest,
)
from fastapi import APIRouter, HTTPException, Query, Request

router = APIRouter(prefix="/feature-lists", tags=["requirement-review-service"])


def _serialize_requirement_feature_list(row) -> dict[str, object]:
    return {
        "id": str(row.id),
        "project_id": str(row.project_id),
        "batch_id": row.batch_id,
        "thread_id": row.thread_id,
        "idempotency_key": row.idempotency_key,
        "version": row.version,
        "status": row.status,
        "decomposable": row.decomposable,
        "undecomposable_reason": row.undecomposable_reason,
        "requirement_text": row.requirement_text,
        "requirement_summary": row.requirement_summary,
        "modules": row.modules,
        "open_questions": row.open_questions,
        "assumptions": row.assumptions,
        "raw_result": row.raw_result,
        "confirmed_at": row.confirmed_at.isoformat() if row.confirmed_at else None,
        "confirmed_by": row.confirmed_by,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


@router.post("", response_model=RequirementFeatureListResponse)
async def create_feature_list(
    request: Request, payload: CreateRequirementFeatureListRequest
):
    project_id = parse_uuid(payload.project_id)
    if project_id is None:
        raise HTTPException(status_code=400, detail="invalid_project_id")
    session_factory = require_db_session_factory(request)
    with session_scope(session_factory) as session:
        row = create_requirement_feature_list(
            session,
            project_id=project_id,
            batch_id=payload.batch_id,
            thread_id=payload.thread_id,
            idempotency_key=payload.idempotency_key,
            decomposable=payload.decomposable,
            undecomposable_reason=payload.undecomposable_reason,
            requirement_text=payload.requirement_text,
            requirement_summary=payload.requirement_summary,
            modules=payload.modules,
            open_questions=payload.open_questions,
            assumptions=payload.assumptions,
            raw_result=payload.raw_result,
        )
        return _serialize_requirement_feature_list(row)


@router.get("", response_model=RequirementFeatureListListResponse)
async def list_feature_lists(
    request: Request,
    project_id: str | None = Query(None),
    batch_id: str | None = Query(None),
    status: str | None = Query(None),
    query: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    project_uuid = parse_uuid(project_id) if project_id else None
    if project_id and project_uuid is None:
        raise HTTPException(status_code=400, detail="invalid_project_id")
    session_factory = require_db_session_factory(request)
    with session_scope(session_factory) as session:
        rows, total = list_requirement_feature_lists(
            session,
            project_id=project_uuid,
            batch_id=batch_id,
            status=status,
            query=query,
            limit=limit,
            offset=offset,
        )
        return {
            "items": [_serialize_requirement_feature_list(row) for row in rows],
            "total": total,
        }


@router.get("/{feature_list_id}", response_model=RequirementFeatureListResponse)
async def get_single_feature_list(request: Request, feature_list_id: str):
    feature_list_uuid = parse_uuid(feature_list_id)
    if feature_list_uuid is None:
        raise HTTPException(status_code=400, detail="invalid_feature_list_id")
    session_factory = require_db_session_factory(request)
    with session_scope(session_factory) as session:
        row = get_requirement_feature_list(session, feature_list_uuid)
        if row is None:
            raise HTTPException(status_code=404, detail="feature_list_not_found")
        return _serialize_requirement_feature_list(row)


@router.patch("/{feature_list_id}", response_model=RequirementFeatureListResponse)
async def patch_feature_list(
    request: Request,
    feature_list_id: str,
    payload: UpdateRequirementFeatureListRequest,
):
    feature_list_uuid = parse_uuid(feature_list_id)
    if feature_list_uuid is None:
        raise HTTPException(status_code=400, detail="invalid_feature_list_id")
    session_factory = require_db_session_factory(request)
    with session_scope(session_factory) as session:
        row = get_requirement_feature_list(session, feature_list_uuid)
        if row is None:
            raise HTTPException(status_code=404, detail="feature_list_not_found")
        row = update_requirement_feature_list(
            session,
            row,
            batch_id=payload.batch_id,
            thread_id=payload.thread_id,
            decomposable=payload.decomposable,
            undecomposable_reason=payload.undecomposable_reason,
            requirement_text=payload.requirement_text,
            requirement_summary=payload.requirement_summary,
            modules=payload.modules,
            open_questions=payload.open_questions,
            assumptions=payload.assumptions,
            raw_result=payload.raw_result,
        )
        return _serialize_requirement_feature_list(row)


@router.post("/{feature_list_id}/confirm", response_model=RequirementFeatureListResponse)
async def confirm_feature_list(
    request: Request,
    feature_list_id: str,
    payload: ConfirmRequirementFeatureListRequest,
):
    feature_list_uuid = parse_uuid(feature_list_id)
    if feature_list_uuid is None:
        raise HTTPException(status_code=400, detail="invalid_feature_list_id")
    session_factory = require_db_session_factory(request)
    with session_scope(session_factory) as session:
        row = get_requirement_feature_list(session, feature_list_uuid)
        if row is None:
            raise HTTPException(status_code=404, detail="feature_list_not_found")
        if payload.expected_version is not None and row.version != payload.expected_version:
            raise HTTPException(status_code=409, detail="feature_list_version_mismatch")
        try:
            row = confirm_requirement_feature_list(
                session, row, confirmed_by=payload.confirmed_by
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        return _serialize_requirement_feature_list(row)


@router.delete("/{feature_list_id}")
async def remove_feature_list(request: Request, feature_list_id: str):
    feature_list_uuid = parse_uuid(feature_list_id)
    if feature_list_uuid is None:
        raise HTTPException(status_code=400, detail="invalid_feature_list_id")
    session_factory = require_db_session_factory(request)
    with session_scope(session_factory) as session:
        row = get_requirement_feature_list(session, feature_list_uuid)
        if row is None:
            raise HTTPException(status_code=404, detail="feature_list_not_found")
        delete_requirement_feature_list(session, row)
        return {"ok": True}
