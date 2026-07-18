from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ListRequirementReviewBatchesQuery(BaseModel):
    model_config = ConfigDict(frozen=True)

    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class ListRequirementReviewDocumentsQuery(BaseModel):
    model_config = ConfigDict(frozen=True)

    batch_id: str | None = None
    parse_status: str | None = None
    query: str | None = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class ExportRequirementReviewDocumentsQuery(BaseModel):
    model_config = ConfigDict(frozen=True)

    batch_id: str | None = None
    parse_status: str | None = None
    query: str | None = None


class ListRequirementReviewResultsQuery(BaseModel):
    model_config = ConfigDict(frozen=True)

    batch_id: str | None = None
    quality_gate: str | None = None
    generation_policy: str | None = None
    query: str | None = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class ExportRequirementReviewResultsQuery(BaseModel):
    model_config = ConfigDict(frozen=True)

    batch_id: str | None = None
    quality_gate: str | None = None
    generation_policy: str | None = None
    query: str | None = None


class GetRequirementReviewBatchDetailQuery(BaseModel):
    model_config = ConfigDict(frozen=True)

    document_limit: int = Field(default=100, ge=1, le=500)
    document_offset: int = Field(default=0, ge=0)
    result_limit: int = Field(default=50, ge=1, le=500)
    result_offset: int = Field(default=0, ge=0)


class ListRequirementFeatureListsQuery(BaseModel):
    model_config = ConfigDict(frozen=True)

    batch_id: str | None = None
    status: str | None = None
    query: str | None = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class CreateRequirementFeatureListCommand(BaseModel):
    batch_id: str | None = None
    thread_id: str | None = None
    idempotency_key: str | None = None
    decomposable: bool = True
    undecomposable_reason: str | None = None
    requirement_text: str = ""
    requirement_summary: str = ""
    modules: list[dict[str, object]] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    raw_result: dict[str, object] = Field(default_factory=dict)


class UpdateRequirementFeatureListCommand(BaseModel):
    batch_id: str | None = None
    thread_id: str | None = None
    decomposable: bool | None = None
    undecomposable_reason: str | None = None
    requirement_text: str | None = None
    requirement_summary: str | None = None
    modules: list[dict[str, object]] | None = None
    open_questions: list[str] | None = None
    assumptions: list[str] | None = None
    raw_result: dict[str, object] | None = None


class ConfirmRequirementFeatureListCommand(BaseModel):
    expected_version: int | None = Field(default=None, ge=1)


class CreateRequirementReviewDocumentCommand(BaseModel):
    batch_id: str | None = None
    thread_id: str | None = None
    filename: str = Field(min_length=1)
    content_type: str = Field(min_length=1)
    storage_path: str | None = None
    source_kind: str = "upload"
    parse_status: str = "parsed"
    summary_for_model: str = ""
    parsed_text: str | None = None
    structured_data: dict[str, object] | None = None
    provenance: dict[str, object] | None = None
    error: dict[str, object] | None = None


class UpdateRequirementReviewDocumentCommand(BaseModel):
    batch_id: str | None = None
    thread_id: str | None = None
    filename: str | None = None
    content_type: str | None = None
    storage_path: str | None = None
    source_kind: str | None = None
    parse_status: str | None = None
    summary_for_model: str | None = None
    parsed_text: str | None = None
    structured_data: dict[str, object] | None = None
    provenance: dict[str, object] | None = None
    error: dict[str, object] | None = None


class CreateRequirementReviewResultCommand(BaseModel):
    batch_id: str | None = None
    thread_id: str | None = None
    document_ids: list[str] = Field(default_factory=list)
    requirement_summary: str = ""
    review_score: float | None = Field(default=None, ge=0, le=100)
    quality_gate: str = "conditional"
    dimension_scores: dict[str, object] = Field(default_factory=dict)
    key_findings: list[str] = Field(default_factory=list)
    major_risks: list[str] = Field(default_factory=list)
    missing_or_ambiguous_items: list[str] = Field(default_factory=list)
    suggestions_to_improve: list[str] = Field(default_factory=list)
    generation_policy: str = Field(min_length=1)
    generation_policy_reason: str = ""
    assumptions: list[str] = Field(default_factory=list)
    raw_result: dict[str, object] = Field(default_factory=dict)


class UpdateRequirementReviewResultCommand(BaseModel):
    batch_id: str | None = None
    thread_id: str | None = None
    document_ids: list[str] | None = None
    requirement_summary: str | None = None
    review_score: float | None = Field(default=None, ge=0, le=100)
    quality_gate: str | None = None
    dimension_scores: dict[str, object] | None = None
    key_findings: list[str] | None = None
    major_risks: list[str] | None = None
    missing_or_ambiguous_items: list[str] | None = None
    suggestions_to_improve: list[str] | None = None
    generation_policy: str | None = None
    generation_policy_reason: str | None = None
    assumptions: list[str] | None = None
    raw_result: dict[str, object] | None = None
