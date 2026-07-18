from __future__ import annotations

from io import BytesIO

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import sessionmaker

from app.adapters.interaction_data import InteractionDataClient
from app.core.config import Settings
from app.core.context.models import ActorContext
from app.core.schemas import AckResponse
from app.entrypoints.http.dependencies import get_actor_context
from app.modules.requirement_review.application import (
    ConfirmRequirementFeatureListCommand,
    CreateRequirementFeatureListCommand,
    CreateRequirementReviewDocumentCommand,
    CreateRequirementReviewResultCommand,
    ExportRequirementReviewDocumentsQuery,
    ExportRequirementReviewResultsQuery,
    GetRequirementReviewBatchDetailQuery,
    ListRequirementFeatureListsQuery,
    ListRequirementReviewBatchesQuery,
    ListRequirementReviewDocumentsQuery,
    ListRequirementReviewResultsQuery,
    RequirementReviewService,
    UpdateRequirementFeatureListCommand,
    UpdateRequirementReviewDocumentCommand,
    UpdateRequirementReviewResultCommand,
)
from app.modules.requirement_review.application.exporters import (
    build_requirement_review_content_disposition,
)
from app.modules.requirement_review.domain import (
    RequirementFeatureList,
    RequirementFeatureListPage,
    RequirementReviewBatchDetail,
    RequirementReviewBatchPage,
    RequirementReviewDocument,
    RequirementReviewDocumentPage,
    RequirementReviewOverview,
    RequirementReviewRoleView,
    RequirementReviewResult,
    RequirementReviewResultPage,
)

router = APIRouter(prefix="/api/projects/{project_id}/requirement-review", tags=["requirement-review"])


def _bind_project_audit_scope(request: Request, project_id: str) -> None:
    request.state.audit_project_id = project_id


def get_requirement_review_service(request: Request) -> RequirementReviewService:
    settings: Settings = request.app.state.settings
    session_factory = getattr(request.app.state, "db_session_factory", None)
    if session_factory is not None and not isinstance(session_factory, sessionmaker):
        session_factory = None
    upstream = InteractionDataClient(
        base_url=settings.interaction_data_service_url,
        token=settings.interaction_data_service_token,
        timeout_seconds=settings.interaction_data_service_timeout_seconds,
        forwarded_headers={
            "x-request-id": str(getattr(request.state, "request_id", "") or "")
        },
    )
    return RequirementReviewService(
        session_factory=session_factory,
        upstream=upstream,
    )


@router.get("/overview", response_model=RequirementReviewOverview)
async def get_requirement_review_overview(
    request: Request,
    project_id: str,
    actor: ActorContext = Depends(get_actor_context),
    service: RequirementReviewService = Depends(get_requirement_review_service),
) -> RequirementReviewOverview:
    _bind_project_audit_scope(request, project_id)
    return await service.get_overview(actor=actor, project_id=project_id)


@router.get("/role", response_model=RequirementReviewRoleView)
async def get_requirement_review_role(
    request: Request,
    project_id: str,
    actor: ActorContext = Depends(get_actor_context),
    service: RequirementReviewService = Depends(get_requirement_review_service),
) -> RequirementReviewRoleView:
    _bind_project_audit_scope(request, project_id)
    return await service.get_role(actor=actor, project_id=project_id)


@router.get("/batches", response_model=RequirementReviewBatchPage)
async def list_requirement_review_batches(
    request: Request,
    project_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    actor: ActorContext = Depends(get_actor_context),
    service: RequirementReviewService = Depends(get_requirement_review_service),
) -> RequirementReviewBatchPage:
    _bind_project_audit_scope(request, project_id)
    return await service.list_batches(
        actor=actor,
        project_id=project_id,
        query=ListRequirementReviewBatchesQuery(limit=limit, offset=offset),
    )


@router.get("/documents", response_model=RequirementReviewDocumentPage)
async def list_requirement_review_documents(
    request: Request,
    project_id: str,
    batch_id: str | None = Query(default=None),
    parse_status: str | None = Query(default=None),
    query: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    actor: ActorContext = Depends(get_actor_context),
    service: RequirementReviewService = Depends(get_requirement_review_service),
) -> RequirementReviewDocumentPage:
    _bind_project_audit_scope(request, project_id)
    return await service.list_documents(
        actor=actor,
        project_id=project_id,
        query=ListRequirementReviewDocumentsQuery(
            batch_id=batch_id,
            parse_status=parse_status,
            query=query,
            limit=limit,
            offset=offset,
        ),
    )


@router.get("/documents/export")
async def export_requirement_review_documents(
    request: Request,
    project_id: str,
    batch_id: str | None = Query(default=None),
    parse_status: str | None = Query(default=None),
    query: str | None = Query(default=None),
    actor: ActorContext = Depends(get_actor_context),
    service: RequirementReviewService = Depends(get_requirement_review_service),
) -> StreamingResponse:
    _bind_project_audit_scope(request, project_id)
    filename, media_type, payload = await service.export_documents(
        actor=actor,
        project_id=project_id,
        query=ExportRequirementReviewDocumentsQuery(
            batch_id=batch_id,
            parse_status=parse_status,
            query=query,
        ),
    )
    return StreamingResponse(
        BytesIO(payload),
        media_type=media_type,
        headers={"Content-Disposition": build_requirement_review_content_disposition(filename)},
    )


@router.post("/documents", response_model=RequirementReviewDocument)
async def create_requirement_review_document(
    request: Request,
    project_id: str,
    payload: CreateRequirementReviewDocumentCommand,
    actor: ActorContext = Depends(get_actor_context),
    service: RequirementReviewService = Depends(get_requirement_review_service),
) -> RequirementReviewDocument:
    _bind_project_audit_scope(request, project_id)
    return await service.create_document(
        actor=actor,
        project_id=project_id,
        command=payload,
    )


@router.get("/documents/{document_id}", response_model=RequirementReviewDocument)
async def get_requirement_review_document(
    request: Request,
    project_id: str,
    document_id: str,
    actor: ActorContext = Depends(get_actor_context),
    service: RequirementReviewService = Depends(get_requirement_review_service),
) -> RequirementReviewDocument:
    _bind_project_audit_scope(request, project_id)
    return await service.get_document(
        actor=actor,
        project_id=project_id,
        document_id=document_id,
    )


@router.get("/documents/{document_id}/preview")
async def preview_requirement_review_document(
    request: Request,
    project_id: str,
    document_id: str,
    actor: ActorContext = Depends(get_actor_context),
    service: RequirementReviewService = Depends(get_requirement_review_service),
) -> StreamingResponse:
    _bind_project_audit_scope(request, project_id)
    payload, headers = await service.get_document_binary(
        actor=actor,
        project_id=project_id,
        document_id=document_id,
        inline=True,
    )
    response_headers: dict[str, str] = {}
    content_disposition = headers.get("content-disposition")
    if content_disposition:
        response_headers["Content-Disposition"] = content_disposition
    return StreamingResponse(
        BytesIO(payload),
        media_type=headers.get("content-type", "application/octet-stream"),
        headers=response_headers,
    )


@router.get("/documents/{document_id}/download")
async def download_requirement_review_document(
    request: Request,
    project_id: str,
    document_id: str,
    actor: ActorContext = Depends(get_actor_context),
    service: RequirementReviewService = Depends(get_requirement_review_service),
) -> StreamingResponse:
    _bind_project_audit_scope(request, project_id)
    payload, headers = await service.get_document_binary(
        actor=actor,
        project_id=project_id,
        document_id=document_id,
        inline=False,
    )
    response_headers: dict[str, str] = {}
    content_disposition = headers.get("content-disposition")
    if content_disposition:
        response_headers["Content-Disposition"] = content_disposition
    return StreamingResponse(
        BytesIO(payload),
        media_type=headers.get("content-type", "application/octet-stream"),
        headers=response_headers,
    )


@router.patch("/documents/{document_id}", response_model=RequirementReviewDocument)
async def update_requirement_review_document(
    request: Request,
    project_id: str,
    document_id: str,
    payload: UpdateRequirementReviewDocumentCommand,
    actor: ActorContext = Depends(get_actor_context),
    service: RequirementReviewService = Depends(get_requirement_review_service),
) -> RequirementReviewDocument:
    _bind_project_audit_scope(request, project_id)
    return await service.update_document(
        actor=actor,
        project_id=project_id,
        document_id=document_id,
        command=payload,
    )


@router.delete("/documents/{document_id}", response_model=AckResponse)
async def delete_requirement_review_document(
    request: Request,
    project_id: str,
    document_id: str,
    actor: ActorContext = Depends(get_actor_context),
    service: RequirementReviewService = Depends(get_requirement_review_service),
) -> AckResponse:
    _bind_project_audit_scope(request, project_id)
    await service.delete_document(
        actor=actor,
        project_id=project_id,
        document_id=document_id,
    )
    return AckResponse()


@router.get("/results", response_model=RequirementReviewResultPage)
async def list_requirement_review_results(
    request: Request,
    project_id: str,
    batch_id: str | None = Query(default=None),
    quality_gate: str | None = Query(default=None),
    generation_policy: str | None = Query(default=None),
    query: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    actor: ActorContext = Depends(get_actor_context),
    service: RequirementReviewService = Depends(get_requirement_review_service),
) -> RequirementReviewResultPage:
    _bind_project_audit_scope(request, project_id)
    return await service.list_results(
        actor=actor,
        project_id=project_id,
        query=ListRequirementReviewResultsQuery(
            batch_id=batch_id,
            quality_gate=quality_gate,
            generation_policy=generation_policy,
            query=query,
            limit=limit,
            offset=offset,
        ),
    )


@router.get("/results/export")
async def export_requirement_review_results(
    request: Request,
    project_id: str,
    batch_id: str | None = Query(default=None),
    quality_gate: str | None = Query(default=None),
    generation_policy: str | None = Query(default=None),
    query: str | None = Query(default=None),
    actor: ActorContext = Depends(get_actor_context),
    service: RequirementReviewService = Depends(get_requirement_review_service),
) -> StreamingResponse:
    _bind_project_audit_scope(request, project_id)
    filename, media_type, payload = await service.export_results(
        actor=actor,
        project_id=project_id,
        query=ExportRequirementReviewResultsQuery(
            batch_id=batch_id,
            quality_gate=quality_gate,
            generation_policy=generation_policy,
            query=query,
        ),
    )
    return StreamingResponse(
        BytesIO(payload),
        media_type=media_type,
        headers={"Content-Disposition": build_requirement_review_content_disposition(filename)},
    )


@router.post("/results", response_model=RequirementReviewResult)
async def create_requirement_review_result(
    request: Request,
    project_id: str,
    payload: CreateRequirementReviewResultCommand,
    actor: ActorContext = Depends(get_actor_context),
    service: RequirementReviewService = Depends(get_requirement_review_service),
) -> RequirementReviewResult:
    _bind_project_audit_scope(request, project_id)
    return await service.create_result(
        actor=actor,
        project_id=project_id,
        command=payload,
    )


@router.get("/results/{result_id}", response_model=RequirementReviewResult)
async def get_requirement_review_result(
    request: Request,
    project_id: str,
    result_id: str,
    actor: ActorContext = Depends(get_actor_context),
    service: RequirementReviewService = Depends(get_requirement_review_service),
) -> RequirementReviewResult:
    _bind_project_audit_scope(request, project_id)
    return await service.get_result(
        actor=actor,
        project_id=project_id,
        result_id=result_id,
    )


@router.patch("/results/{result_id}", response_model=RequirementReviewResult)
async def update_requirement_review_result(
    request: Request,
    project_id: str,
    result_id: str,
    payload: UpdateRequirementReviewResultCommand,
    actor: ActorContext = Depends(get_actor_context),
    service: RequirementReviewService = Depends(get_requirement_review_service),
) -> RequirementReviewResult:
    _bind_project_audit_scope(request, project_id)
    return await service.update_result(
        actor=actor,
        project_id=project_id,
        result_id=result_id,
        command=payload,
    )


@router.delete("/results/{result_id}", response_model=AckResponse)
async def delete_requirement_review_result(
    request: Request,
    project_id: str,
    result_id: str,
    actor: ActorContext = Depends(get_actor_context),
    service: RequirementReviewService = Depends(get_requirement_review_service),
) -> AckResponse:
    _bind_project_audit_scope(request, project_id)
    await service.delete_result(
        actor=actor,
        project_id=project_id,
        result_id=result_id,
    )
    return AckResponse()


@router.get("/feature-lists", response_model=RequirementFeatureListPage)
async def list_requirement_feature_lists(
    request: Request,
    project_id: str,
    batch_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    query: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    actor: ActorContext = Depends(get_actor_context),
    service: RequirementReviewService = Depends(get_requirement_review_service),
) -> RequirementFeatureListPage:
    _bind_project_audit_scope(request, project_id)
    return await service.list_feature_lists(
        actor=actor,
        project_id=project_id,
        query=ListRequirementFeatureListsQuery(
            batch_id=batch_id,
            status=status,
            query=query,
            limit=limit,
            offset=offset,
        ),
    )


@router.post("/feature-lists", response_model=RequirementFeatureList)
async def create_requirement_feature_list(
    request: Request,
    project_id: str,
    payload: CreateRequirementFeatureListCommand,
    actor: ActorContext = Depends(get_actor_context),
    service: RequirementReviewService = Depends(get_requirement_review_service),
) -> RequirementFeatureList:
    _bind_project_audit_scope(request, project_id)
    return await service.create_feature_list(
        actor=actor,
        project_id=project_id,
        command=payload,
    )


@router.get("/feature-lists/{feature_list_id}", response_model=RequirementFeatureList)
async def get_requirement_feature_list(
    request: Request,
    project_id: str,
    feature_list_id: str,
    actor: ActorContext = Depends(get_actor_context),
    service: RequirementReviewService = Depends(get_requirement_review_service),
) -> RequirementFeatureList:
    _bind_project_audit_scope(request, project_id)
    return await service.get_feature_list(
        actor=actor,
        project_id=project_id,
        feature_list_id=feature_list_id,
    )


@router.patch("/feature-lists/{feature_list_id}", response_model=RequirementFeatureList)
async def update_requirement_feature_list(
    request: Request,
    project_id: str,
    feature_list_id: str,
    payload: UpdateRequirementFeatureListCommand,
    actor: ActorContext = Depends(get_actor_context),
    service: RequirementReviewService = Depends(get_requirement_review_service),
) -> RequirementFeatureList:
    _bind_project_audit_scope(request, project_id)
    return await service.update_feature_list(
        actor=actor,
        project_id=project_id,
        feature_list_id=feature_list_id,
        command=payload,
    )


@router.post(
    "/feature-lists/{feature_list_id}/confirm",
    response_model=RequirementFeatureList,
)
async def confirm_requirement_feature_list(
    request: Request,
    project_id: str,
    feature_list_id: str,
    payload: ConfirmRequirementFeatureListCommand,
    actor: ActorContext = Depends(get_actor_context),
    service: RequirementReviewService = Depends(get_requirement_review_service),
) -> RequirementFeatureList:
    _bind_project_audit_scope(request, project_id)
    return await service.confirm_feature_list(
        actor=actor,
        project_id=project_id,
        feature_list_id=feature_list_id,
        command=payload,
    )


@router.delete("/feature-lists/{feature_list_id}", response_model=AckResponse)
async def delete_requirement_feature_list(
    request: Request,
    project_id: str,
    feature_list_id: str,
    actor: ActorContext = Depends(get_actor_context),
    service: RequirementReviewService = Depends(get_requirement_review_service),
) -> AckResponse:
    _bind_project_audit_scope(request, project_id)
    await service.delete_feature_list(
        actor=actor,
        project_id=project_id,
        feature_list_id=feature_list_id,
    )
    return AckResponse()


@router.get("/batches/{batch_id}", response_model=RequirementReviewBatchDetail)
async def get_requirement_review_batch_detail(
    request: Request,
    project_id: str,
    batch_id: str,
    document_limit: int = Query(default=100, ge=1, le=500),
    document_offset: int = Query(default=0, ge=0),
    result_limit: int = Query(default=50, ge=1, le=500),
    result_offset: int = Query(default=0, ge=0),
    actor: ActorContext = Depends(get_actor_context),
    service: RequirementReviewService = Depends(get_requirement_review_service),
) -> RequirementReviewBatchDetail:
    _bind_project_audit_scope(request, project_id)
    return await service.get_batch_detail(
        actor=actor,
        project_id=project_id,
        batch_id=batch_id,
        query=GetRequirementReviewBatchDetailQuery(
            document_limit=document_limit,
            document_offset=document_offset,
            result_limit=result_limit,
            result_offset=result_offset,
        ),
    )
