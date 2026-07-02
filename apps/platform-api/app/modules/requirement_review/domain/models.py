from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.core.schemas import OffsetPage


class RequirementReviewOverview(BaseModel):
    model_config = ConfigDict(frozen=True)

    project_id: str
    documents_total: int = 0
    parsed_documents_total: int = 0
    failed_documents_total: int = 0
    results_total: int = 0
    pass_results_total: int = 0
    conditional_results_total: int = 0
    fail_results_total: int = 0
    latest_batch_id: str | None = None
    latest_activity_at: datetime | None = None


class RequirementReviewBatchSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    batch_id: str
    documents_count: int = 0
    results_count: int = 0
    latest_created_at: datetime | None = None
    parse_status_summary: dict[str, int] = Field(default_factory=dict)
    quality_gate_summary: dict[str, int] = Field(default_factory=dict)


class RequirementReviewBatchPage(OffsetPage[RequirementReviewBatchSummary]):
    pass


class RequirementReviewDocument(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    project_id: str
    batch_id: str | None = None
    thread_id: str | None = None
    idempotency_key: str | None = None
    filename: str
    content_type: str
    storage_path: str | None = None
    source_kind: str
    parse_status: str
    summary_for_model: str = ""
    parsed_text: str | None = None
    structured_data: dict[str, Any] | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)
    error: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime


class RequirementReviewDocumentPage(OffsetPage[RequirementReviewDocument]):
    pass


class RequirementReviewRoleView(BaseModel):
    model_config = ConfigDict(frozen=True)

    project_id: str
    role: str
    can_write_requirement_review: bool


class RequirementReviewResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    project_id: str
    batch_id: str | None = None
    thread_id: str | None = None
    idempotency_key: str | None = None
    document_ids: list[str] = Field(default_factory=list)
    requirement_summary: str = ""
    review_score: float | None = None
    quality_gate: str
    dimension_scores: dict[str, Any] = Field(default_factory=dict)
    key_findings: list[str] = Field(default_factory=list)
    major_risks: list[str] = Field(default_factory=list)
    missing_or_ambiguous_items: list[str] = Field(default_factory=list)
    suggestions_to_improve: list[str] = Field(default_factory=list)
    generation_policy: str
    generation_policy_reason: str = ""
    assumptions: list[str] = Field(default_factory=list)
    raw_result: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class RequirementReviewResultPage(OffsetPage[RequirementReviewResult]):
    pass


class RequirementReviewBatchDetail(BaseModel):
    model_config = ConfigDict(frozen=True)

    batch: RequirementReviewBatchSummary
    documents: RequirementReviewDocumentPage
    results: RequirementReviewResultPage
