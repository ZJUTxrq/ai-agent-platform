from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from app.core.context.models import ActorContext
from app.core.db import SqlAlchemyUnitOfWork
from app.core.errors import (
    BadRequestError,
    ForbiddenError,
    NotFoundError,
    PlatformApiError,
    ServiceUnavailableError,
)
from app.core.identifiers import parse_uuid
from app.core.normalization import clean_str, payload_to_dict
from app.modules.iam.application import AuthorizationRequest, IamPolicyEngine, PermissionCode
from app.modules.iam.domain import ProjectRole
from app.modules.projects.infra.sqlalchemy.repository import SqlAlchemyProjectsRepository
from app.modules.requirement_review.application.contracts import (
    ConfirmRequirementFeatureListCommand,
    CreateRequirementFeatureListCommand,
    CreateRequirementReviewDocumentCommand,
    CreateRequirementReviewResultCommand,
    ListRequirementFeatureListsQuery,
    UpdateRequirementFeatureListCommand,
    ExportRequirementReviewDocumentsQuery,
    ExportRequirementReviewResultsQuery,
    GetRequirementReviewBatchDetailQuery,
    ListRequirementReviewBatchesQuery,
    ListRequirementReviewDocumentsQuery,
    ListRequirementReviewResultsQuery,
    UpdateRequirementReviewDocumentCommand,
    UpdateRequirementReviewResultCommand,
)
from app.modules.requirement_review.application.exporters import (
    MAX_REQUIREMENT_REVIEW_DOCUMENT_EXPORT_ROWS,
    MAX_REQUIREMENT_REVIEW_RESULT_EXPORT_ROWS,
    REQUIREMENT_REVIEW_EXPORT_MEDIA_TYPE,
    build_requirement_review_documents_workbook,
    build_requirement_review_results_workbook,
)
from app.modules.requirement_review.application.ports import RequirementReviewDataPort
from app.modules.requirement_review.domain import (
    RequirementFeatureList,
    RequirementFeatureListPage,
    RequirementReviewBatchDetail,
    RequirementReviewBatchPage,
    RequirementReviewBatchSummary,
    RequirementReviewDocument,
    RequirementReviewDocumentPage,
    RequirementReviewOverview,
    RequirementReviewRoleView,
    RequirementReviewResult,
    RequirementReviewResultPage,
)

_RESULTS_PATH = "/api/requirement-review-service/results"
_DOCUMENTS_PATH = "/api/requirement-review-service/documents"
_FEATURE_LISTS_PATH = "/api/requirement-review-service/feature-lists"
_OVERVIEW_PATH = "/api/requirement-review-service/overview"
_BATCHES_PATH = "/api/requirement-review-service/batches"
_DEFAULT_EXPORT_PAGE_SIZE = 200
_ROLE_PRIORITY: tuple[tuple[str, str], ...] = (
    (ProjectRole.ADMIN.value, "admin"),
    (ProjectRole.EDITOR.value, "editor"),
    (ProjectRole.EXECUTOR.value, "executor"),
)


def _normalize_requirement_review_document_payload(payload: dict[str, Any]) -> dict[str, Any]:
    next_payload = dict(payload)
    for key in ("batch_id", "thread_id", "filename", "content_type", "source_kind", "parse_status"):
        if key in next_payload:
            next_payload[key] = clean_str(next_payload.get(key))
    return next_payload


def _normalize_requirement_review_result_payload(payload: dict[str, Any]) -> dict[str, Any]:
    next_payload = dict(payload)
    for key in ("batch_id", "thread_id", "quality_gate", "generation_policy"):
        if key in next_payload:
            next_payload[key] = clean_str(next_payload.get(key))
    if "requirement_summary" in next_payload and next_payload.get("requirement_summary") is None:
        next_payload["requirement_summary"] = ""
    if "generation_policy_reason" in next_payload and next_payload.get("generation_policy_reason") is None:
        next_payload["generation_policy_reason"] = ""
    return next_payload


class RequirementReviewService:
    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session] | None,
        upstream: RequirementReviewDataPort,
        policy_engine: IamPolicyEngine | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._upstream = upstream
        self._policy_engine = policy_engine or IamPolicyEngine()

    def _require_session_factory(self) -> sessionmaker[Session]:
        if self._session_factory is None:
            raise ServiceUnavailableError(
                code="platform_database_not_enabled",
                message="Platform database is not enabled",
            )
        return self._session_factory

    def _require_permission(self, *, actor: ActorContext, project_id: str, write: bool) -> None:
        self._policy_engine.require(
            actor=actor,
            authorization=AuthorizationRequest(
                permission=(
                    PermissionCode.PROJECT_RUNTIME_WRITE
                    if write
                    else PermissionCode.PROJECT_RUNTIME_READ
                ),
                project_id=project_id,
            ),
        )

    async def _prepare_project_scope(
        self,
        *,
        actor: ActorContext,
        project_id: str,
        write: bool,
    ) -> None:
        session_factory = self._require_session_factory()
        self._require_permission(actor=actor, project_id=project_id, write=write)
        async with SqlAlchemyUnitOfWork(session_factory) as uow:
            project_uuid = parse_uuid(project_id, code="invalid_project_id")
            repository = SqlAlchemyProjectsRepository(uow.session)
            project = repository.get_project_by_id(project_uuid)
            if project is None or project.status == "deleted":
                raise NotFoundError(message="Project not found", code="project_not_found")

    def _resolve_role(self, *, actor: ActorContext, project_id: str) -> str:
        if actor.has_platform_role("platform_super_admin"):
            return "admin"

        role_set = set(actor.project_role_set(project_id))
        for role_value, label in _ROLE_PRIORITY:
            if role_value in role_set:
                return label

        raise ForbiddenError(code="project_role_missing", message="project_role_missing")

    @staticmethod
    def _ensure_object(payload: Any, *, code: str) -> dict[str, Any]:
        if isinstance(payload, dict):
            return payload
        raise PlatformApiError(
            code=code,
            status_code=502,
            message="Interaction-data-service returned an invalid object payload",
        )

    def _ensure_project_match(
        self,
        payload: Any,
        *,
        project_id: str,
        code: str,
    ) -> dict[str, Any]:
        payload_dict = self._ensure_object(payload, code="interaction_data_invalid_response")
        if clean_str(payload_dict.get("project_id")) != project_id:
            raise NotFoundError(message=code, code=code)
        return payload_dict

    @staticmethod
    def _normalize_total(payload: dict[str, Any], *, fallback_items: list[Any]) -> int:
        total = payload.get("total")
        if isinstance(total, int):
            return total
        return len(fallback_items)

    @staticmethod
    def _normalize_items(value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, dict)]

    async def _list_all_documents_for_export(
        self,
        *,
        actor: ActorContext,
        project_id: str,
        query: ExportRequirementReviewDocumentsQuery,
        max_items: int,
    ) -> list[dict[str, Any]]:
        first_page = await self.list_documents(
            actor=actor,
            project_id=project_id,
            query=ListRequirementReviewDocumentsQuery(
                batch_id=query.batch_id,
                parse_status=query.parse_status,
                query=query.query,
                limit=min(_DEFAULT_EXPORT_PAGE_SIZE, max_items),
                offset=0,
            ),
            skip_scope_check=True,
        )
        items = [item.model_dump(mode="python") for item in first_page.items]
        total = min(first_page.total, max_items)
        offset = len(items)
        while offset < total:
            page_payload = self._ensure_object(
                await self._upstream.require_json(
                    "GET",
                    _DOCUMENTS_PATH,
                    params={
                        "project_id": project_id,
                        "batch_id": query.batch_id,
                        "parse_status": query.parse_status,
                        "query": query.query,
                        "limit": min(_DEFAULT_EXPORT_PAGE_SIZE, total - offset),
                        "offset": offset,
                    },
                ),
                code="interaction_data_invalid_response",
            )
            chunk = self._normalize_items(page_payload.get("items"))
            items.extend(chunk)
            if not chunk:
                break
            offset = len(items)
        return items[:total]

    async def _list_all_results_for_export(
        self,
        *,
        actor: ActorContext,
        project_id: str,
        query: ExportRequirementReviewResultsQuery,
        max_items: int,
    ) -> list[dict[str, Any]]:
        first_page = await self.list_results(
            actor=actor,
            project_id=project_id,
            query=ListRequirementReviewResultsQuery(
                batch_id=query.batch_id,
                quality_gate=query.quality_gate,
                generation_policy=query.generation_policy,
                query=query.query,
                limit=min(_DEFAULT_EXPORT_PAGE_SIZE, max_items),
                offset=0,
            ),
            skip_scope_check=True,
        )
        items = [item.model_dump(mode="python") for item in first_page.items]
        total = min(first_page.total, max_items)
        offset = len(items)
        while offset < total:
            page_payload = self._ensure_object(
                await self._upstream.require_json(
                    "GET",
                    _RESULTS_PATH,
                    params={
                        "project_id": project_id,
                        "batch_id": query.batch_id,
                        "quality_gate": query.quality_gate,
                        "generation_policy": query.generation_policy,
                        "query": query.query,
                        "limit": min(_DEFAULT_EXPORT_PAGE_SIZE, total - offset),
                        "offset": offset,
                    },
                ),
                code="interaction_data_invalid_response",
            )
            chunk = self._normalize_items(page_payload.get("items"))
            items.extend(chunk)
            if not chunk:
                break
            offset = len(items)
        return items[:total]

    async def get_overview(
        self,
        *,
        actor: ActorContext,
        project_id: str,
    ) -> RequirementReviewOverview:
        await self._prepare_project_scope(actor=actor, project_id=project_id, write=False)
        payload = await self._upstream.require_json(
            "GET",
            _OVERVIEW_PATH,
            params={"project_id": project_id},
        )
        normalized = self._ensure_project_match(
            payload,
            project_id=project_id,
            code="requirement_review_overview_not_found",
        )
        return RequirementReviewOverview.model_validate(normalized)

    async def get_role(
        self,
        *,
        actor: ActorContext,
        project_id: str,
    ) -> RequirementReviewRoleView:
        await self._prepare_project_scope(actor=actor, project_id=project_id, write=False)
        role = self._resolve_role(actor=actor, project_id=project_id)
        return RequirementReviewRoleView(
            project_id=project_id,
            role=role,
            can_write_requirement_review=role in {"admin", "editor"},
        )

    async def list_batches(
        self,
        *,
        actor: ActorContext,
        project_id: str,
        query: ListRequirementReviewBatchesQuery,
    ) -> RequirementReviewBatchPage:
        await self._prepare_project_scope(actor=actor, project_id=project_id, write=False)
        payload = self._ensure_object(
            await self._upstream.require_json(
                "GET",
                _BATCHES_PATH,
                params={
                    "project_id": project_id,
                    "limit": query.limit,
                    "offset": query.offset,
                },
            ),
            code="interaction_data_invalid_response",
        )
        items = [
            RequirementReviewBatchSummary.model_validate(item)
            for item in self._normalize_items(payload.get("items"))
        ]
        return RequirementReviewBatchPage(
            items=items,
            total=self._normalize_total(payload, fallback_items=items),
        )

    async def get_batch_detail(
        self,
        *,
        actor: ActorContext,
        project_id: str,
        batch_id: str,
        query: GetRequirementReviewBatchDetailQuery,
    ) -> RequirementReviewBatchDetail:
        await self._prepare_project_scope(actor=actor, project_id=project_id, write=False)
        normalized_batch_id = clean_str(batch_id)
        if normalized_batch_id is None:
            raise BadRequestError(code="invalid_batch_id", message="invalid_batch_id")

        payload = self._ensure_object(
            await self._upstream.require_json(
                "GET",
                f"{_BATCHES_PATH}/{normalized_batch_id}",
                params={
                    "project_id": project_id,
                    "document_limit": query.document_limit,
                    "document_offset": query.document_offset,
                    "result_limit": query.result_limit,
                    "result_offset": query.result_offset,
                },
            ),
            code="interaction_data_invalid_response",
        )
        batch_payload = self._ensure_object(
            payload.get("batch"),
            code="interaction_data_invalid_response",
        )
        if clean_str(batch_payload.get("batch_id")) != normalized_batch_id:
            raise NotFoundError(
                code="requirement_review_batch_not_found",
                message="requirement_review_batch_not_found",
            )

        document_page_payload = self._ensure_object(
            payload.get("documents"),
            code="interaction_data_invalid_response",
        )
        result_page_payload = self._ensure_object(
            payload.get("results"),
            code="interaction_data_invalid_response",
        )
        document_items = [
            RequirementReviewDocument.model_validate(item)
            for item in self._normalize_items(document_page_payload.get("items"))
        ]
        result_items = [
            RequirementReviewResult.model_validate(item)
            for item in self._normalize_items(result_page_payload.get("items"))
        ]
        return RequirementReviewBatchDetail(
            batch=RequirementReviewBatchSummary.model_validate(batch_payload),
            documents=RequirementReviewDocumentPage(
                items=document_items,
                total=self._normalize_total(document_page_payload, fallback_items=document_items),
            ),
            results=RequirementReviewResultPage(
                items=result_items,
                total=self._normalize_total(result_page_payload, fallback_items=result_items),
            ),
        )

    async def list_documents(
        self,
        *,
        actor: ActorContext,
        project_id: str,
        query: ListRequirementReviewDocumentsQuery,
        skip_scope_check: bool = False,
    ) -> RequirementReviewDocumentPage:
        if not skip_scope_check:
            await self._prepare_project_scope(actor=actor, project_id=project_id, write=False)
        params: dict[str, Any] = {
            "project_id": project_id,
            "limit": query.limit,
            "offset": query.offset,
        }
        if clean_str(query.batch_id):
            params["batch_id"] = query.batch_id
        if clean_str(query.parse_status):
            params["parse_status"] = query.parse_status
        if clean_str(query.query):
            params["query"] = query.query

        payload = self._ensure_object(
            await self._upstream.require_json("GET", _DOCUMENTS_PATH, params=params),
            code="interaction_data_invalid_response",
        )
        items = [
            RequirementReviewDocument.model_validate(item)
            for item in self._normalize_items(payload.get("items"))
        ]
        return RequirementReviewDocumentPage(
            items=items,
            total=self._normalize_total(payload, fallback_items=items),
        )

    async def get_document(
        self,
        *,
        actor: ActorContext,
        project_id: str,
        document_id: str,
    ) -> RequirementReviewDocument:
        await self._prepare_project_scope(actor=actor, project_id=project_id, write=False)
        payload = await self._upstream.require_json("GET", f"{_DOCUMENTS_PATH}/{document_id}")
        normalized = self._ensure_project_match(
            payload,
            project_id=project_id,
            code="requirement_review_document_not_found",
        )
        return RequirementReviewDocument.model_validate(normalized)

    async def get_document_binary(
        self,
        *,
        actor: ActorContext,
        project_id: str,
        document_id: str,
        inline: bool,
    ) -> tuple[bytes, dict[str, str]]:
        await self._prepare_project_scope(actor=actor, project_id=project_id, write=False)
        await self.get_document(actor=actor, project_id=project_id, document_id=document_id)
        suffix = "preview" if inline else "download"
        return await self._upstream.get_binary(f"{_DOCUMENTS_PATH}/{document_id}/{suffix}")

    async def create_document(
        self,
        *,
        actor: ActorContext,
        project_id: str,
        command: CreateRequirementReviewDocumentCommand,
    ) -> RequirementReviewDocument:
        await self._prepare_project_scope(actor=actor, project_id=project_id, write=True)
        payload = _normalize_requirement_review_document_payload(payload_to_dict(command))
        payload["project_id"] = project_id
        created = await self._upstream.require_json("POST", _DOCUMENTS_PATH, payload=payload)
        normalized = self._ensure_project_match(
            created,
            project_id=project_id,
            code="requirement_review_document_not_found",
        )
        return RequirementReviewDocument.model_validate(normalized)

    async def list_results(
        self,
        *,
        actor: ActorContext,
        project_id: str,
        query: ListRequirementReviewResultsQuery,
        skip_scope_check: bool = False,
    ) -> RequirementReviewResultPage:
        if not skip_scope_check:
            await self._prepare_project_scope(actor=actor, project_id=project_id, write=False)
        params: dict[str, Any] = {
            "project_id": project_id,
            "limit": query.limit,
            "offset": query.offset,
        }
        if clean_str(query.batch_id):
            params["batch_id"] = query.batch_id
        if clean_str(query.quality_gate):
            params["quality_gate"] = query.quality_gate
        if clean_str(query.generation_policy):
            params["generation_policy"] = query.generation_policy
        if clean_str(query.query):
            params["query"] = query.query

        payload = self._ensure_object(
            await self._upstream.require_json("GET", _RESULTS_PATH, params=params),
            code="interaction_data_invalid_response",
        )
        items = [
            RequirementReviewResult.model_validate(item)
            for item in self._normalize_items(payload.get("items"))
        ]
        return RequirementReviewResultPage(
            items=items,
            total=self._normalize_total(payload, fallback_items=items),
        )

    async def export_documents(
        self,
        *,
        actor: ActorContext,
        project_id: str,
        query: ExportRequirementReviewDocumentsQuery,
    ) -> tuple[str, str, bytes]:
        await self._prepare_project_scope(actor=actor, project_id=project_id, write=False)
        items = await self._list_all_documents_for_export(
            actor=actor,
            project_id=project_id,
            query=query,
            max_items=MAX_REQUIREMENT_REVIEW_DOCUMENT_EXPORT_ROWS,
        )
        filename, workbook_bytes = build_requirement_review_documents_workbook(
            project_id=project_id,
            documents=items,
            filters={
                "batch_id": query.batch_id,
                "parse_status": query.parse_status,
                "query": query.query,
            },
        )
        return filename, REQUIREMENT_REVIEW_EXPORT_MEDIA_TYPE, workbook_bytes

    async def get_result(
        self,
        *,
        actor: ActorContext,
        project_id: str,
        result_id: str,
    ) -> RequirementReviewResult:
        await self._prepare_project_scope(actor=actor, project_id=project_id, write=False)
        payload = await self._upstream.require_json("GET", f"{_RESULTS_PATH}/{result_id}")
        normalized = self._ensure_project_match(
            payload,
            project_id=project_id,
            code="requirement_review_result_not_found",
        )
        return RequirementReviewResult.model_validate(normalized)

    async def create_result(
        self,
        *,
        actor: ActorContext,
        project_id: str,
        command: CreateRequirementReviewResultCommand,
    ) -> RequirementReviewResult:
        await self._prepare_project_scope(actor=actor, project_id=project_id, write=True)
        payload = _normalize_requirement_review_result_payload(payload_to_dict(command))
        payload["project_id"] = project_id
        created = await self._upstream.require_json("POST", _RESULTS_PATH, payload=payload)
        normalized = self._ensure_project_match(
            created,
            project_id=project_id,
            code="requirement_review_result_not_found",
        )
        return RequirementReviewResult.model_validate(normalized)

    async def update_document(
        self,
        *,
        actor: ActorContext,
        project_id: str,
        document_id: str,
        command: UpdateRequirementReviewDocumentCommand,
    ) -> RequirementReviewDocument:
        await self._prepare_project_scope(actor=actor, project_id=project_id, write=True)
        existing = await self.get_document(actor=actor, project_id=project_id, document_id=document_id)
        payload = _normalize_requirement_review_document_payload(payload_to_dict(command))
        updated = await self._upstream.require_json(
            "PATCH",
            f"{_DOCUMENTS_PATH}/{document_id}",
            payload=payload,
        )
        normalized = self._ensure_project_match(
            updated,
            project_id=project_id,
            code="requirement_review_document_not_found",
        )
        if clean_str(normalized.get("id")) != existing.id:
            raise NotFoundError(
                message="requirement_review_document_not_found",
                code="requirement_review_document_not_found",
            )
        return RequirementReviewDocument.model_validate(normalized)

    async def delete_document(
        self,
        *,
        actor: ActorContext,
        project_id: str,
        document_id: str,
    ) -> None:
        await self._prepare_project_scope(actor=actor, project_id=project_id, write=True)
        await self.get_document(actor=actor, project_id=project_id, document_id=document_id)
        await self._upstream.require_json("DELETE", f"{_DOCUMENTS_PATH}/{document_id}")

    async def update_result(
        self,
        *,
        actor: ActorContext,
        project_id: str,
        result_id: str,
        command: UpdateRequirementReviewResultCommand,
    ) -> RequirementReviewResult:
        await self._prepare_project_scope(actor=actor, project_id=project_id, write=True)
        existing = await self.get_result(actor=actor, project_id=project_id, result_id=result_id)
        payload = _normalize_requirement_review_result_payload(payload_to_dict(command))
        updated = await self._upstream.require_json(
            "PATCH",
            f"{_RESULTS_PATH}/{result_id}",
            payload=payload,
        )
        normalized = self._ensure_project_match(
            updated,
            project_id=project_id,
            code="requirement_review_result_not_found",
        )
        if clean_str(normalized.get("id")) != existing.id:
            raise NotFoundError(
                message="requirement_review_result_not_found",
                code="requirement_review_result_not_found",
            )
        return RequirementReviewResult.model_validate(normalized)

    async def delete_result(
        self,
        *,
        actor: ActorContext,
        project_id: str,
        result_id: str,
    ) -> None:
        await self._prepare_project_scope(actor=actor, project_id=project_id, write=True)
        await self.get_result(actor=actor, project_id=project_id, result_id=result_id)
        await self._upstream.require_json("DELETE", f"{_RESULTS_PATH}/{result_id}")

    async def list_feature_lists(
        self,
        *,
        actor: ActorContext,
        project_id: str,
        query: ListRequirementFeatureListsQuery,
    ) -> RequirementFeatureListPage:
        await self._prepare_project_scope(actor=actor, project_id=project_id, write=False)
        params: dict[str, Any] = {
            "project_id": project_id,
            "limit": query.limit,
            "offset": query.offset,
        }
        if clean_str(query.batch_id):
            params["batch_id"] = query.batch_id
        if clean_str(query.status):
            params["status"] = query.status
        if clean_str(query.query):
            params["query"] = query.query

        payload = self._ensure_object(
            await self._upstream.require_json("GET", _FEATURE_LISTS_PATH, params=params),
            code="interaction_data_invalid_response",
        )
        items = [
            RequirementFeatureList.model_validate(item)
            for item in self._normalize_items(payload.get("items"))
        ]
        return RequirementFeatureListPage(
            items=items,
            total=self._normalize_total(payload, fallback_items=items),
        )

    async def get_feature_list(
        self,
        *,
        actor: ActorContext,
        project_id: str,
        feature_list_id: str,
    ) -> RequirementFeatureList:
        await self._prepare_project_scope(actor=actor, project_id=project_id, write=False)
        payload = await self._upstream.require_json(
            "GET", f"{_FEATURE_LISTS_PATH}/{feature_list_id}"
        )
        normalized = self._ensure_project_match(
            payload,
            project_id=project_id,
            code="requirement_feature_list_not_found",
        )
        return RequirementFeatureList.model_validate(normalized)

    async def create_feature_list(
        self,
        *,
        actor: ActorContext,
        project_id: str,
        command: CreateRequirementFeatureListCommand,
    ) -> RequirementFeatureList:
        await self._prepare_project_scope(actor=actor, project_id=project_id, write=True)
        payload = payload_to_dict(command)
        for key in ("batch_id", "thread_id", "idempotency_key"):
            if key in payload:
                payload[key] = clean_str(payload.get(key))
        payload["project_id"] = project_id
        created = await self._upstream.require_json(
            "POST", _FEATURE_LISTS_PATH, payload=payload
        )
        normalized = self._ensure_project_match(
            created,
            project_id=project_id,
            code="requirement_feature_list_not_found",
        )
        return RequirementFeatureList.model_validate(normalized)

    async def update_feature_list(
        self,
        *,
        actor: ActorContext,
        project_id: str,
        feature_list_id: str,
        command: UpdateRequirementFeatureListCommand,
    ) -> RequirementFeatureList:
        await self._prepare_project_scope(actor=actor, project_id=project_id, write=True)
        existing = await self.get_feature_list(
            actor=actor, project_id=project_id, feature_list_id=feature_list_id
        )
        payload = payload_to_dict(command)
        updated = await self._upstream.require_json(
            "PATCH",
            f"{_FEATURE_LISTS_PATH}/{feature_list_id}",
            payload=payload,
        )
        normalized = self._ensure_project_match(
            updated,
            project_id=project_id,
            code="requirement_feature_list_not_found",
        )
        if clean_str(normalized.get("id")) != existing.id:
            raise NotFoundError(
                message="requirement_feature_list_not_found",
                code="requirement_feature_list_not_found",
            )
        return RequirementFeatureList.model_validate(normalized)

    async def confirm_feature_list(
        self,
        *,
        actor: ActorContext,
        project_id: str,
        feature_list_id: str,
        command: ConfirmRequirementFeatureListCommand,
    ) -> RequirementFeatureList:
        await self._prepare_project_scope(actor=actor, project_id=project_id, write=True)
        await self.get_feature_list(
            actor=actor, project_id=project_id, feature_list_id=feature_list_id
        )
        # confirmed_by 取自登录态，不信任客户端传入
        confirmed = await self._upstream.require_json(
            "POST",
            f"{_FEATURE_LISTS_PATH}/{feature_list_id}/confirm",
            payload={
                "confirmed_by": clean_str(actor.subject),
                "expected_version": command.expected_version,
            },
        )
        normalized = self._ensure_project_match(
            confirmed,
            project_id=project_id,
            code="requirement_feature_list_not_found",
        )
        return RequirementFeatureList.model_validate(normalized)

    async def delete_feature_list(
        self,
        *,
        actor: ActorContext,
        project_id: str,
        feature_list_id: str,
    ) -> None:
        await self._prepare_project_scope(actor=actor, project_id=project_id, write=True)
        await self.get_feature_list(
            actor=actor, project_id=project_id, feature_list_id=feature_list_id
        )
        await self._upstream.require_json(
            "DELETE", f"{_FEATURE_LISTS_PATH}/{feature_list_id}"
        )

    async def export_results(
        self,
        *,
        actor: ActorContext,
        project_id: str,
        query: ExportRequirementReviewResultsQuery,
    ) -> tuple[str, str, bytes]:
        await self._prepare_project_scope(actor=actor, project_id=project_id, write=False)
        items = await self._list_all_results_for_export(
            actor=actor,
            project_id=project_id,
            query=query,
            max_items=MAX_REQUIREMENT_REVIEW_RESULT_EXPORT_ROWS,
        )
        filename, workbook_bytes = build_requirement_review_results_workbook(
            project_id=project_id,
            results=items,
            filters={
                "batch_id": query.batch_id,
                "quality_gate": query.quality_gate,
                "generation_policy": query.generation_policy,
                "query": query.query,
            },
        )
        return filename, REQUIREMENT_REVIEW_EXPORT_MEDIA_TYPE, workbook_bytes
