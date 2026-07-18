from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CreateRequirementReviewDocumentRequest(BaseModel):
    project_id: str
    batch_id: str | None = None
    thread_id: str | None = Field(default=None, max_length=255)
    idempotency_key: str | None = Field(default=None, max_length=255)
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(min_length=1, max_length=128)
    storage_path: str | None = None
    source_kind: str = Field(default="upload", min_length=1, max_length=64)
    parse_status: str = Field(default="parsed", min_length=1, max_length=64)
    summary_for_model: str = ""
    parsed_text: str | None = None
    structured_data: dict[str, Any] | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)
    error: dict[str, Any] | None = None


class RequirementReviewDocumentResponse(BaseModel):
    id: str
    project_id: str
    batch_id: str | None
    thread_id: str | None
    idempotency_key: str | None
    filename: str
    content_type: str
    storage_path: str | None = None
    source_kind: str
    parse_status: str
    summary_for_model: str
    parsed_text: str | None
    structured_data: dict[str, Any] | None
    provenance: dict[str, Any]
    error: dict[str, Any] | None
    created_at: str
    updated_at: str


class RequirementReviewDocumentListResponse(BaseModel):
    items: list[RequirementReviewDocumentResponse]
    total: int


class RequirementReviewDocumentAssetResponse(BaseModel):
    storage_path: str
    filename: str
    content_type: str
    size: int
    sha256: str


class UpdateRequirementReviewDocumentRequest(BaseModel):
    batch_id: str | None = None
    thread_id: str | None = Field(default=None, max_length=255)
    filename: str | None = Field(default=None, min_length=1, max_length=255)
    content_type: str | None = Field(default=None, min_length=1, max_length=128)
    storage_path: str | None = None
    source_kind: str | None = Field(default=None, min_length=1, max_length=64)
    parse_status: str | None = Field(default=None, min_length=1, max_length=64)
    summary_for_model: str | None = None
    parsed_text: str | None = None
    structured_data: dict[str, Any] | None = None
    provenance: dict[str, Any] | None = None
    error: dict[str, Any] | None = None


class CreateRequirementReviewResultRequest(BaseModel):
    project_id: str
    batch_id: str | None = None
    thread_id: str | None = Field(default=None, max_length=255)
    idempotency_key: str | None = Field(default=None, max_length=255)
    document_ids: list[str] = Field(default_factory=list)
    requirement_summary: str = ""
    review_score: float | None = Field(default=None, ge=0, le=100)
    quality_gate: str = Field(default="conditional", min_length=1, max_length=64)
    dimension_scores: dict[str, Any] = Field(default_factory=dict)
    key_findings: list[str] = Field(default_factory=list)
    major_risks: list[str] = Field(default_factory=list)
    missing_or_ambiguous_items: list[str] = Field(default_factory=list)
    suggestions_to_improve: list[str] = Field(default_factory=list)
    generation_policy: str = Field(min_length=1, max_length=128)
    generation_policy_reason: str = ""
    assumptions: list[str] = Field(default_factory=list)
    raw_result: dict[str, Any] = Field(default_factory=dict)


class RequirementReviewResultResponse(BaseModel):
    id: str
    project_id: str
    batch_id: str | None
    thread_id: str | None
    idempotency_key: str | None
    document_ids: list[str]
    requirement_summary: str
    review_score: float | None
    quality_gate: str
    dimension_scores: dict[str, Any]
    key_findings: list[str]
    major_risks: list[str]
    missing_or_ambiguous_items: list[str]
    suggestions_to_improve: list[str]
    generation_policy: str
    generation_policy_reason: str
    assumptions: list[str]
    raw_result: dict[str, Any]
    created_at: str
    updated_at: str


class RequirementReviewResultListResponse(BaseModel):
    items: list[RequirementReviewResultResponse]
    total: int


class UpdateRequirementReviewResultRequest(BaseModel):
    batch_id: str | None = None
    thread_id: str | None = Field(default=None, max_length=255)
    document_ids: list[str] | None = None
    requirement_summary: str | None = None
    review_score: float | None = Field(default=None, ge=0, le=100)
    quality_gate: str | None = Field(default=None, min_length=1, max_length=64)
    dimension_scores: dict[str, Any] | None = None
    key_findings: list[str] | None = None
    major_risks: list[str] | None = None
    missing_or_ambiguous_items: list[str] | None = None
    suggestions_to_improve: list[str] | None = None
    generation_policy: str | None = Field(default=None, min_length=1, max_length=128)
    generation_policy_reason: str | None = None
    assumptions: list[str] | None = None
    raw_result: dict[str, Any] | None = None


class CreateRequirementFeatureListRequest(BaseModel):
    project_id: str
    batch_id: str | None = None
    thread_id: str | None = Field(default=None, max_length=255)
    idempotency_key: str | None = Field(default=None, max_length=255)
    decomposable: bool = True
    undecomposable_reason: str | None = None
    requirement_text: str = ""
    requirement_summary: str = ""
    modules: list[dict[str, Any]] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    raw_result: dict[str, Any] = Field(default_factory=dict)


class UpdateRequirementFeatureListRequest(BaseModel):
    batch_id: str | None = None
    thread_id: str | None = Field(default=None, max_length=255)
    decomposable: bool | None = None
    undecomposable_reason: str | None = None
    requirement_text: str | None = None
    requirement_summary: str | None = None
    modules: list[dict[str, Any]] | None = None
    open_questions: list[str] | None = None
    assumptions: list[str] | None = None
    raw_result: dict[str, Any] | None = None


class ConfirmRequirementFeatureListRequest(BaseModel):
    confirmed_by: str | None = Field(default=None, max_length=255)
    # 乐观校验：调用方声明确认的是哪个版本，不匹配则拒绝
    expected_version: int | None = Field(default=None, ge=1)


class RequirementFeatureListResponse(BaseModel):
    id: str
    project_id: str
    batch_id: str | None
    thread_id: str | None
    idempotency_key: str | None
    version: int
    status: str
    decomposable: bool
    undecomposable_reason: str | None
    requirement_text: str
    requirement_summary: str
    modules: list[dict[str, Any]]
    open_questions: list[str]
    assumptions: list[str]
    raw_result: dict[str, Any]
    confirmed_at: str | None
    confirmed_by: str | None
    created_at: str
    updated_at: str


class RequirementFeatureListListResponse(BaseModel):
    items: list[RequirementFeatureListResponse]
    total: int


class RequirementReviewOverviewResponse(BaseModel):
    project_id: str | None = None
    documents_total: int
    parsed_documents_total: int
    failed_documents_total: int
    results_total: int
    pass_results_total: int
    conditional_results_total: int
    fail_results_total: int
    latest_batch_id: str | None = None
    latest_activity_at: str | None = None


class RequirementReviewBatchSummary(BaseModel):
    batch_id: str
    documents_count: int
    results_count: int
    latest_created_at: str | None = None
    parse_status_summary: dict[str, int] = Field(default_factory=dict)
    quality_gate_summary: dict[str, int] = Field(default_factory=dict)


class RequirementReviewBatchListResponse(BaseModel):
    items: list[RequirementReviewBatchSummary]
    total: int


class RequirementReviewBatchDetailResponse(BaseModel):
    batch: RequirementReviewBatchSummary
    documents: RequirementReviewDocumentListResponse
    results: RequirementReviewResultListResponse
