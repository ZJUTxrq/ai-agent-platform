from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.db.models import (
    RequirementFeatureList,
    RequirementReviewDocument,
    RequirementReviewResult,
    TestCaseDocument,
    TestCaseRecord,
)
from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session


def parse_uuid(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(value)
    except (ValueError, TypeError):
        return None


def create_test_case_document(
    session: Session,
    *,
    project_id: uuid.UUID,
    batch_id: str | None,
    idempotency_key: str | None,
    filename: str,
    content_type: str,
    storage_path: str | None,
    source_kind: str,
    parse_status: str,
    summary_for_model: str,
    parsed_text: str | None,
    structured_data: dict | None,
    provenance: dict,
    confidence: float | None,
    error: dict | None,
) -> TestCaseDocument:
    normalized_batch_id = batch_id.strip() if isinstance(batch_id, str) and batch_id.strip() else None
    normalized_idempotency_key = (
        idempotency_key.strip()
        if isinstance(idempotency_key, str) and idempotency_key.strip()
        else None
    )
    if normalized_idempotency_key is not None:
        existing_stmt = select(TestCaseDocument).where(
            TestCaseDocument.project_id == project_id,
            TestCaseDocument.idempotency_key == normalized_idempotency_key,
        )
        if normalized_batch_id is None:
            existing_stmt = existing_stmt.where(TestCaseDocument.batch_id.is_(None))
        else:
            existing_stmt = existing_stmt.where(TestCaseDocument.batch_id == normalized_batch_id)
        existing = session.scalar(existing_stmt)
        if existing is not None:
            if normalized_batch_id is not None and not existing.batch_id:
                existing.batch_id = normalized_batch_id
            if storage_path is not None:
                existing.storage_path = storage_path
            if parse_status == "parsed" or existing.parse_status == "unprocessed":
                existing.parse_status = parse_status
            if summary_for_model:
                existing.summary_for_model = summary_for_model
            if parsed_text:
                existing.parsed_text = parsed_text
            if structured_data is not None:
                existing.structured_data = structured_data
            if provenance:
                existing.provenance = provenance
            if confidence is not None:
                existing.confidence = confidence
            if error is not None:
                existing.error = error
            elif parse_status == "parsed":
                existing.error = None
            session.flush()
            return existing

    row = TestCaseDocument(
        project_id=project_id,
        batch_id=normalized_batch_id,
        idempotency_key=normalized_idempotency_key,
        filename=filename,
        content_type=content_type,
        storage_path=storage_path,
        source_kind=source_kind,
        parse_status=parse_status,
        summary_for_model=summary_for_model,
        parsed_text=parsed_text,
        structured_data=structured_data,
        provenance=provenance,
        confidence=confidence,
        error=error,
    )
    session.add(row)
    session.flush()
    return row


def list_test_case_documents(
    session: Session,
    *,
    project_id: uuid.UUID | None,
    batch_id: str | None,
    parse_status: str | None,
    query: str | None,
    limit: int,
    offset: int,
) -> tuple[list[TestCaseDocument], int]:
    base_stmt = select(TestCaseDocument)
    if project_id is not None:
        base_stmt = base_stmt.where(TestCaseDocument.project_id == project_id)
    if isinstance(batch_id, str) and batch_id.strip():
        base_stmt = base_stmt.where(TestCaseDocument.batch_id == batch_id.strip())
    if isinstance(parse_status, str) and parse_status.strip():
        base_stmt = base_stmt.where(TestCaseDocument.parse_status == parse_status.strip())
    if isinstance(query, str) and query.strip():
        pattern = f"%{query.strip()}%"
        base_stmt = base_stmt.where(
            or_(
                TestCaseDocument.filename.ilike(pattern),
                TestCaseDocument.summary_for_model.ilike(pattern),
            )
        )
    stmt = base_stmt.order_by(desc(TestCaseDocument.created_at)).offset(offset).limit(limit)
    count_stmt = select(func.count()).select_from(base_stmt.subquery())
    rows = list(session.scalars(stmt).all())
    total = int(session.scalar(count_stmt) or 0)
    return rows, total


def get_test_case_document(
    session: Session, document_id: uuid.UUID
) -> TestCaseDocument | None:
    return session.get(TestCaseDocument, document_id)


def list_test_cases_for_document(
    session: Session,
    *,
    project_id: uuid.UUID,
    document_id: str,
) -> list[TestCaseRecord]:
    stmt = (
        select(TestCaseRecord)
        .where(TestCaseRecord.project_id == project_id)
        .order_by(desc(TestCaseRecord.updated_at), desc(TestCaseRecord.id))
    )
    rows = list(session.scalars(stmt).all())
    return [
        row
        for row in rows
        if isinstance(row.source_document_ids, list) and document_id in row.source_document_ids
    ]


def create_test_case(
    session: Session,
    *,
    project_id: uuid.UUID,
    batch_id: str | None,
    idempotency_key: str | None,
    case_id: str | None,
    title: str,
    description: str,
    status: str,
    module_name: str | None,
    priority: str | None,
    source_document_ids: list[str],
    content_json: dict,
) -> TestCaseRecord:
    normalized_batch_id = batch_id.strip() if isinstance(batch_id, str) and batch_id.strip() else None
    normalized_idempotency_key = (
        idempotency_key.strip()
        if isinstance(idempotency_key, str) and idempotency_key.strip()
        else None
    )
    if normalized_idempotency_key is not None:
        existing_stmt = select(TestCaseRecord).where(
            TestCaseRecord.project_id == project_id,
            TestCaseRecord.idempotency_key == normalized_idempotency_key,
        )
        if normalized_batch_id is None:
            existing_stmt = existing_stmt.where(TestCaseRecord.batch_id.is_(None))
        else:
            existing_stmt = existing_stmt.where(TestCaseRecord.batch_id == normalized_batch_id)
        existing = session.scalar(existing_stmt)
        if existing is not None:
            existing.batch_id = normalized_batch_id
            existing.case_id = case_id
            existing.title = title
            existing.description = description
            existing.status = status
            existing.module_name = module_name
            existing.priority = priority
            existing.source_document_ids = source_document_ids
            existing.content_json = content_json
            session.flush()
            return existing

    row = TestCaseRecord(
        project_id=project_id,
        batch_id=normalized_batch_id,
        idempotency_key=normalized_idempotency_key,
        case_id=case_id,
        title=title,
        description=description,
        status=status,
        module_name=module_name,
        priority=priority,
        source_document_ids=source_document_ids,
        content_json=content_json,
    )
    session.add(row)
    session.flush()
    return row


def list_test_cases(
    session: Session,
    *,
    project_id: uuid.UUID | None,
    status: str | None,
    batch_id: str | None,
    query: str | None,
    limit: int,
    offset: int,
) -> tuple[list[TestCaseRecord], int]:
    base_stmt = select(TestCaseRecord)
    if project_id is not None:
        base_stmt = base_stmt.where(TestCaseRecord.project_id == project_id)
    if isinstance(status, str) and status.strip():
        base_stmt = base_stmt.where(TestCaseRecord.status == status.strip())
    if isinstance(batch_id, str) and batch_id.strip():
        base_stmt = base_stmt.where(TestCaseRecord.batch_id == batch_id.strip())
    if isinstance(query, str) and query.strip():
        pattern = f"%{query.strip()}%"
        base_stmt = base_stmt.where(
            or_(
                TestCaseRecord.title.ilike(pattern),
                TestCaseRecord.description.ilike(pattern),
                TestCaseRecord.module_name.ilike(pattern),
                TestCaseRecord.case_id.ilike(pattern),
            )
        )
    stmt = base_stmt.order_by(desc(TestCaseRecord.created_at)).offset(offset).limit(limit)
    count_stmt = select(func.count()).select_from(base_stmt.subquery())
    rows = list(session.scalars(stmt).all())
    total = int(session.scalar(count_stmt) or 0)
    return rows, total


def get_test_case(session: Session, test_case_id: uuid.UUID) -> TestCaseRecord | None:
    return session.get(TestCaseRecord, test_case_id)


def update_test_case(
    session: Session,
    row: TestCaseRecord,
    *,
    batch_id: str | None,
    case_id: str | None,
    title: str | None,
    description: str | None,
    status: str | None,
    module_name: str | None,
    priority: str | None,
    source_document_ids: list[str] | None,
    content_json: dict | None,
) -> TestCaseRecord:
    if batch_id is not None:
        row.batch_id = batch_id
    if case_id is not None:
        row.case_id = case_id
    if title is not None:
        row.title = title
    if description is not None:
        row.description = description
    if status is not None:
        row.status = status
    if module_name is not None:
        row.module_name = module_name
    if priority is not None:
        row.priority = priority
    if source_document_ids is not None:
        row.source_document_ids = source_document_ids
    if content_json is not None:
        row.content_json = content_json
    session.flush()
    return row


def delete_test_case(session: Session, row: TestCaseRecord) -> None:
    session.delete(row)
    session.flush()


def get_test_case_overview(
    session: Session,
    *,
    project_id: uuid.UUID | None,
) -> dict[str, object]:
    documents_stmt = select(func.count()).select_from(TestCaseDocument)
    parsed_stmt = select(func.count()).select_from(TestCaseDocument).where(
        TestCaseDocument.parse_status == "parsed"
    )
    failed_stmt = select(func.count()).select_from(TestCaseDocument).where(
        TestCaseDocument.parse_status == "failed"
    )
    cases_stmt = select(func.count()).select_from(TestCaseRecord)
    latest_document_stmt = select(TestCaseDocument).order_by(
        desc(TestCaseDocument.created_at),
        desc(TestCaseDocument.id),
    )
    latest_case_stmt = select(TestCaseRecord).order_by(
        desc(TestCaseRecord.updated_at),
        desc(TestCaseRecord.id),
    )

    if project_id is not None:
        documents_stmt = documents_stmt.where(TestCaseDocument.project_id == project_id)
        parsed_stmt = parsed_stmt.where(TestCaseDocument.project_id == project_id)
        failed_stmt = failed_stmt.where(TestCaseDocument.project_id == project_id)
        cases_stmt = cases_stmt.where(TestCaseRecord.project_id == project_id)
        latest_document_stmt = latest_document_stmt.where(TestCaseDocument.project_id == project_id)
        latest_case_stmt = latest_case_stmt.where(TestCaseRecord.project_id == project_id)

    latest_document = session.scalar(latest_document_stmt.limit(1))
    latest_case = session.scalar(latest_case_stmt.limit(1))
    latest_batch_id: str | None = None
    latest_activity_at: datetime | None = None

    if latest_document is not None:
        latest_batch_id = latest_document.batch_id
        latest_activity_at = latest_document.created_at
    if latest_case is not None and (
        latest_activity_at is None or latest_case.updated_at >= latest_activity_at
    ):
        latest_batch_id = latest_case.batch_id
        latest_activity_at = latest_case.updated_at

    return {
        "documents_total": int(session.scalar(documents_stmt) or 0),
        "parsed_documents_total": int(session.scalar(parsed_stmt) or 0),
        "failed_documents_total": int(session.scalar(failed_stmt) or 0),
        "test_cases_total": int(session.scalar(cases_stmt) or 0),
        "latest_batch_id": latest_batch_id,
        "latest_activity_at": latest_activity_at,
    }


def list_test_case_batches(
    session: Session,
    *,
    project_id: uuid.UUID | None,
    limit: int,
    offset: int,
) -> tuple[list[dict[str, object]], int]:
    documents_stmt = (
        select(
            TestCaseDocument.batch_id,
            func.count().label("documents_count"),
            func.max(TestCaseDocument.created_at).label("latest_document_at"),
        )
        .where(TestCaseDocument.batch_id.is_not(None))
        .group_by(TestCaseDocument.batch_id)
    )
    parse_summary_stmt = (
        select(
            TestCaseDocument.batch_id,
            TestCaseDocument.parse_status,
            func.count().label("status_count"),
        )
        .where(TestCaseDocument.batch_id.is_not(None))
        .group_by(TestCaseDocument.batch_id, TestCaseDocument.parse_status)
    )
    cases_stmt = (
        select(
            TestCaseRecord.batch_id,
            func.count().label("test_cases_count"),
            func.max(TestCaseRecord.updated_at).label("latest_case_at"),
        )
        .where(TestCaseRecord.batch_id.is_not(None))
        .group_by(TestCaseRecord.batch_id)
    )

    if project_id is not None:
        documents_stmt = documents_stmt.where(TestCaseDocument.project_id == project_id)
        parse_summary_stmt = parse_summary_stmt.where(TestCaseDocument.project_id == project_id)
        cases_stmt = cases_stmt.where(TestCaseRecord.project_id == project_id)

    batches: dict[str, dict[str, object]] = {}
    for row in session.execute(documents_stmt):
        batch_id = str(row.batch_id or "").strip()
        if not batch_id:
            continue
        batches[batch_id] = {
            "batch_id": batch_id,
            "documents_count": int(row.documents_count or 0),
            "test_cases_count": 0,
            "latest_created_at": row.latest_document_at,
            "parse_status_summary": {},
        }

    for row in session.execute(parse_summary_stmt):
        batch_id = str(row.batch_id or "").strip()
        if not batch_id:
            continue
        entry = batches.setdefault(
            batch_id,
            {
                "batch_id": batch_id,
                "documents_count": 0,
                "test_cases_count": 0,
                "latest_created_at": None,
                "parse_status_summary": {},
            },
        )
        summary = entry["parse_status_summary"]
        if isinstance(summary, dict):
            summary[str(row.parse_status)] = int(row.status_count or 0)

    for row in session.execute(cases_stmt):
        batch_id = str(row.batch_id or "").strip()
        if not batch_id:
            continue
        entry = batches.setdefault(
            batch_id,
            {
                "batch_id": batch_id,
                "documents_count": 0,
                "test_cases_count": 0,
                "latest_created_at": None,
                "parse_status_summary": {},
            },
        )
        entry["test_cases_count"] = int(row.test_cases_count or 0)
        latest_created_at = entry.get("latest_created_at")
        latest_case_at = row.latest_case_at
        if latest_case_at is not None and (
            latest_created_at is None or latest_case_at >= latest_created_at
        ):
            entry["latest_created_at"] = latest_case_at

    ordered = sorted(
        batches.values(),
        key=lambda item: (
            item.get("latest_created_at") is not None,
            item.get("latest_created_at").isoformat()
            if item.get("latest_created_at") is not None
            else "",
            item.get("batch_id") or "",
        ),
        reverse=True,
    )
    total = len(ordered)
    return ordered[offset : offset + limit], total


def get_test_case_batch_detail(
    session: Session,
    *,
    project_id: uuid.UUID | None,
    batch_id: str,
    document_limit: int,
    document_offset: int,
    case_limit: int,
    case_offset: int,
) -> dict[str, object] | None:
    normalized_batch_id = batch_id.strip()
    if not normalized_batch_id:
        return None

    documents_base_stmt = select(TestCaseDocument).where(
        TestCaseDocument.batch_id == normalized_batch_id
    )
    cases_base_stmt = select(TestCaseRecord).where(
        TestCaseRecord.batch_id == normalized_batch_id
    )
    parse_summary_stmt = (
        select(
            TestCaseDocument.parse_status,
            func.count().label("status_count"),
        )
        .where(TestCaseDocument.batch_id == normalized_batch_id)
        .group_by(TestCaseDocument.parse_status)
    )
    latest_document_stmt = select(func.max(TestCaseDocument.created_at)).where(
        TestCaseDocument.batch_id == normalized_batch_id
    )
    latest_case_stmt = select(func.max(TestCaseRecord.updated_at)).where(
        TestCaseRecord.batch_id == normalized_batch_id
    )

    if project_id is not None:
        documents_base_stmt = documents_base_stmt.where(TestCaseDocument.project_id == project_id)
        cases_base_stmt = cases_base_stmt.where(TestCaseRecord.project_id == project_id)
        parse_summary_stmt = parse_summary_stmt.where(TestCaseDocument.project_id == project_id)
        latest_document_stmt = latest_document_stmt.where(TestCaseDocument.project_id == project_id)
        latest_case_stmt = latest_case_stmt.where(TestCaseRecord.project_id == project_id)

    documents_total = int(
        session.scalar(select(func.count()).select_from(documents_base_stmt.subquery())) or 0
    )
    cases_total = int(
        session.scalar(select(func.count()).select_from(cases_base_stmt.subquery())) or 0
    )
    if documents_total <= 0 and cases_total <= 0:
        return None

    latest_document_at = session.scalar(latest_document_stmt)
    latest_case_at = session.scalar(latest_case_stmt)
    latest_created_at = latest_document_at
    if latest_case_at is not None and (
        latest_created_at is None or latest_case_at >= latest_created_at
    ):
        latest_created_at = latest_case_at

    parse_status_summary = {
        str(row.parse_status): int(row.status_count or 0)
        for row in session.execute(parse_summary_stmt)
    }

    document_rows = list(
        session.scalars(
            documents_base_stmt
            .order_by(desc(TestCaseDocument.created_at), desc(TestCaseDocument.id))
            .offset(document_offset)
            .limit(document_limit)
        ).all()
    )
    case_rows = list(
        session.scalars(
            cases_base_stmt
            .order_by(desc(TestCaseRecord.updated_at), desc(TestCaseRecord.id))
            .offset(case_offset)
            .limit(case_limit)
        ).all()
    )

    return {
        "batch": {
            "batch_id": normalized_batch_id,
            "documents_count": documents_total,
            "test_cases_count": cases_total,
            "latest_created_at": latest_created_at,
            "parse_status_summary": parse_status_summary,
        },
        "documents": {
            "items": document_rows,
            "total": documents_total,
        },
        "test_cases": {
            "items": case_rows,
            "total": cases_total,
        },
    }


def create_requirement_review_document(
    session: Session,
    *,
    project_id: uuid.UUID,
    batch_id: str | None,
    thread_id: str | None,
    idempotency_key: str | None,
    filename: str,
    content_type: str,
    storage_path: str | None,
    source_kind: str,
    parse_status: str,
    summary_for_model: str,
    parsed_text: str | None,
    structured_data: dict | None,
    provenance: dict,
    error: dict | None,
) -> RequirementReviewDocument:
    normalized_batch_id = batch_id.strip() if isinstance(batch_id, str) and batch_id.strip() else None
    normalized_idempotency_key = (
        idempotency_key.strip()
        if isinstance(idempotency_key, str) and idempotency_key.strip()
        else None
    )
    normalized_thread_id = thread_id.strip() if isinstance(thread_id, str) and thread_id.strip() else None
    if normalized_idempotency_key is not None:
        existing_stmt = select(RequirementReviewDocument).where(
            RequirementReviewDocument.project_id == project_id,
            RequirementReviewDocument.idempotency_key == normalized_idempotency_key,
        )
        if normalized_batch_id is None:
            existing_stmt = existing_stmt.where(RequirementReviewDocument.batch_id.is_(None))
        else:
            existing_stmt = existing_stmt.where(RequirementReviewDocument.batch_id == normalized_batch_id)
        existing = session.scalar(existing_stmt)
        if existing is not None:
            existing.batch_id = normalized_batch_id
            existing.thread_id = normalized_thread_id
            existing.filename = filename
            existing.content_type = content_type
            if storage_path is not None:
                existing.storage_path = storage_path
            existing.source_kind = source_kind
            existing.parse_status = parse_status
            existing.summary_for_model = summary_for_model
            existing.parsed_text = parsed_text
            existing.structured_data = structured_data
            existing.provenance = provenance
            existing.error = error
            session.flush()
            return existing

    row = RequirementReviewDocument(
        project_id=project_id,
        batch_id=normalized_batch_id,
        thread_id=normalized_thread_id,
        idempotency_key=normalized_idempotency_key,
        filename=filename,
        content_type=content_type,
        storage_path=storage_path,
        source_kind=source_kind,
        parse_status=parse_status,
        summary_for_model=summary_for_model,
        parsed_text=parsed_text,
        structured_data=structured_data,
        provenance=provenance,
        error=error,
    )
    session.add(row)
    session.flush()
    return row


def list_requirement_review_documents(
    session: Session,
    *,
    project_id: uuid.UUID | None,
    batch_id: str | None,
    parse_status: str | None,
    query: str | None,
    limit: int,
    offset: int,
) -> tuple[list[RequirementReviewDocument], int]:
    base_stmt = select(RequirementReviewDocument)
    if project_id is not None:
        base_stmt = base_stmt.where(RequirementReviewDocument.project_id == project_id)
    if isinstance(batch_id, str) and batch_id.strip():
        base_stmt = base_stmt.where(RequirementReviewDocument.batch_id == batch_id.strip())
    if isinstance(parse_status, str) and parse_status.strip():
        base_stmt = base_stmt.where(RequirementReviewDocument.parse_status == parse_status.strip())
    if isinstance(query, str) and query.strip():
        pattern = f"%{query.strip()}%"
        base_stmt = base_stmt.where(
            or_(
                RequirementReviewDocument.filename.ilike(pattern),
                RequirementReviewDocument.summary_for_model.ilike(pattern),
            )
        )
    stmt = (
        base_stmt.order_by(desc(RequirementReviewDocument.updated_at), desc(RequirementReviewDocument.id))
        .offset(offset)
        .limit(limit)
    )
    count_stmt = select(func.count()).select_from(base_stmt.subquery())
    rows = list(session.scalars(stmt).all())
    total = int(session.scalar(count_stmt) or 0)
    return rows, total


def get_requirement_review_document(
    session: Session,
    document_id: uuid.UUID,
) -> RequirementReviewDocument | None:
    return session.get(RequirementReviewDocument, document_id)


def update_requirement_review_document(
    session: Session,
    row: RequirementReviewDocument,
    *,
    batch_id: str | None,
    thread_id: str | None,
    filename: str | None,
    content_type: str | None,
    storage_path: str | None,
    source_kind: str | None,
    parse_status: str | None,
    summary_for_model: str | None,
    parsed_text: str | None,
    structured_data: dict | None,
    provenance: dict | None,
    error: dict | None,
) -> RequirementReviewDocument:
    if batch_id is not None:
        row.batch_id = batch_id
    if thread_id is not None:
        row.thread_id = thread_id
    if filename is not None:
        row.filename = filename
    if content_type is not None:
        row.content_type = content_type
    if storage_path is not None:
        row.storage_path = storage_path
    if source_kind is not None:
        row.source_kind = source_kind
    if parse_status is not None:
        row.parse_status = parse_status
    if summary_for_model is not None:
        row.summary_for_model = summary_for_model
    if parsed_text is not None:
        row.parsed_text = parsed_text
    if structured_data is not None:
        row.structured_data = structured_data
    if provenance is not None:
        row.provenance = provenance
    if error is not None:
        row.error = error
    session.flush()
    return row


def delete_requirement_review_document(session: Session, row: RequirementReviewDocument) -> None:
    session.delete(row)
    session.flush()


def create_requirement_review_result(
    session: Session,
    *,
    project_id: uuid.UUID,
    batch_id: str | None,
    thread_id: str | None,
    idempotency_key: str | None,
    document_ids: list[str],
    requirement_summary: str,
    review_score: float | None,
    quality_gate: str,
    dimension_scores: dict,
    key_findings: list[str],
    major_risks: list[str],
    missing_or_ambiguous_items: list[str],
    suggestions_to_improve: list[str],
    generation_policy: str,
    generation_policy_reason: str,
    assumptions: list[str],
    raw_result: dict,
) -> RequirementReviewResult:
    normalized_batch_id = batch_id.strip() if isinstance(batch_id, str) and batch_id.strip() else None
    normalized_idempotency_key = (
        idempotency_key.strip()
        if isinstance(idempotency_key, str) and idempotency_key.strip()
        else None
    )
    normalized_thread_id = thread_id.strip() if isinstance(thread_id, str) and thread_id.strip() else None
    if normalized_idempotency_key is not None:
        existing_stmt = select(RequirementReviewResult).where(
            RequirementReviewResult.project_id == project_id,
            RequirementReviewResult.idempotency_key == normalized_idempotency_key,
        )
        if normalized_batch_id is None:
            existing_stmt = existing_stmt.where(RequirementReviewResult.batch_id.is_(None))
        else:
            existing_stmt = existing_stmt.where(RequirementReviewResult.batch_id == normalized_batch_id)
        existing = session.scalar(existing_stmt)
        if existing is not None:
            existing.batch_id = normalized_batch_id
            existing.thread_id = normalized_thread_id
            existing.document_ids = document_ids
            existing.requirement_summary = requirement_summary
            existing.review_score = review_score
            existing.quality_gate = quality_gate
            existing.dimension_scores = dimension_scores
            existing.key_findings = key_findings
            existing.major_risks = major_risks
            existing.missing_or_ambiguous_items = missing_or_ambiguous_items
            existing.suggestions_to_improve = suggestions_to_improve
            existing.generation_policy = generation_policy
            existing.generation_policy_reason = generation_policy_reason
            existing.assumptions = assumptions
            existing.raw_result = raw_result
            session.flush()
            return existing

    row = RequirementReviewResult(
        project_id=project_id,
        batch_id=normalized_batch_id,
        thread_id=normalized_thread_id,
        idempotency_key=normalized_idempotency_key,
        document_ids=document_ids,
        requirement_summary=requirement_summary,
        review_score=review_score,
        quality_gate=quality_gate,
        dimension_scores=dimension_scores,
        key_findings=key_findings,
        major_risks=major_risks,
        missing_or_ambiguous_items=missing_or_ambiguous_items,
        suggestions_to_improve=suggestions_to_improve,
        generation_policy=generation_policy,
        generation_policy_reason=generation_policy_reason,
        assumptions=assumptions,
        raw_result=raw_result,
    )
    session.add(row)
    session.flush()
    return row


def list_requirement_review_results(
    session: Session,
    *,
    project_id: uuid.UUID | None,
    batch_id: str | None,
    quality_gate: str | None,
    generation_policy: str | None,
    query: str | None,
    limit: int,
    offset: int,
) -> tuple[list[RequirementReviewResult], int]:
    base_stmt = select(RequirementReviewResult)
    if project_id is not None:
        base_stmt = base_stmt.where(RequirementReviewResult.project_id == project_id)
    if isinstance(batch_id, str) and batch_id.strip():
        base_stmt = base_stmt.where(RequirementReviewResult.batch_id == batch_id.strip())
    if isinstance(quality_gate, str) and quality_gate.strip():
        base_stmt = base_stmt.where(RequirementReviewResult.quality_gate == quality_gate.strip())
    if isinstance(generation_policy, str) and generation_policy.strip():
        base_stmt = base_stmt.where(
            RequirementReviewResult.generation_policy == generation_policy.strip()
        )
    if isinstance(query, str) and query.strip():
        pattern = f"%{query.strip()}%"
        base_stmt = base_stmt.where(
            or_(
                RequirementReviewResult.requirement_summary.ilike(pattern),
                RequirementReviewResult.generation_policy_reason.ilike(pattern),
            )
        )
    stmt = (
        base_stmt.order_by(desc(RequirementReviewResult.updated_at), desc(RequirementReviewResult.id))
        .offset(offset)
        .limit(limit)
    )
    count_stmt = select(func.count()).select_from(base_stmt.subquery())
    rows = list(session.scalars(stmt).all())
    total = int(session.scalar(count_stmt) or 0)
    return rows, total


def get_requirement_review_result(
    session: Session,
    result_id: uuid.UUID,
) -> RequirementReviewResult | None:
    return session.get(RequirementReviewResult, result_id)


def update_requirement_review_result(
    session: Session,
    row: RequirementReviewResult,
    *,
    batch_id: str | None,
    thread_id: str | None,
    document_ids: list[str] | None,
    requirement_summary: str | None,
    review_score: float | None,
    quality_gate: str | None,
    dimension_scores: dict | None,
    key_findings: list[str] | None,
    major_risks: list[str] | None,
    missing_or_ambiguous_items: list[str] | None,
    suggestions_to_improve: list[str] | None,
    generation_policy: str | None,
    generation_policy_reason: str | None,
    assumptions: list[str] | None,
    raw_result: dict | None,
) -> RequirementReviewResult:
    if batch_id is not None:
        row.batch_id = batch_id
    if thread_id is not None:
        row.thread_id = thread_id
    if document_ids is not None:
        row.document_ids = document_ids
    if requirement_summary is not None:
        row.requirement_summary = requirement_summary
    if review_score is not None:
        row.review_score = review_score
    if quality_gate is not None:
        row.quality_gate = quality_gate
    if dimension_scores is not None:
        row.dimension_scores = dimension_scores
    if key_findings is not None:
        row.key_findings = key_findings
    if major_risks is not None:
        row.major_risks = major_risks
    if missing_or_ambiguous_items is not None:
        row.missing_or_ambiguous_items = missing_or_ambiguous_items
    if suggestions_to_improve is not None:
        row.suggestions_to_improve = suggestions_to_improve
    if generation_policy is not None:
        row.generation_policy = generation_policy
    if generation_policy_reason is not None:
        row.generation_policy_reason = generation_policy_reason
    if assumptions is not None:
        row.assumptions = assumptions
    if raw_result is not None:
        row.raw_result = raw_result
    session.flush()
    return row


def delete_requirement_review_result(session: Session, row: RequirementReviewResult) -> None:
    session.delete(row)
    session.flush()


FEATURE_LIST_STATUS_DRAFT = "draft"
FEATURE_LIST_STATUS_CONFIRMED = "confirmed"

_FEATURE_LIST_CONTENT_FIELDS = (
    "requirement_text",
    "requirement_summary",
    "modules",
    "open_questions",
    "assumptions",
    "decomposable",
    "undecomposable_reason",
    "raw_result",
)


def create_requirement_feature_list(
    session: Session,
    *,
    project_id: uuid.UUID,
    batch_id: str | None,
    thread_id: str | None,
    idempotency_key: str | None,
    decomposable: bool,
    undecomposable_reason: str | None,
    requirement_text: str,
    requirement_summary: str,
    modules: list[dict],
    open_questions: list[str],
    assumptions: list[str],
    raw_result: dict,
) -> RequirementFeatureList:
    normalized_batch_id = batch_id.strip() if isinstance(batch_id, str) and batch_id.strip() else None
    normalized_thread_id = thread_id.strip() if isinstance(thread_id, str) and thread_id.strip() else None
    normalized_idempotency_key = (
        idempotency_key.strip()
        if isinstance(idempotency_key, str) and idempotency_key.strip()
        else None
    )
    if normalized_idempotency_key is not None:
        existing_stmt = select(RequirementFeatureList).where(
            RequirementFeatureList.project_id == project_id,
            RequirementFeatureList.idempotency_key == normalized_idempotency_key,
        )
        if normalized_batch_id is None:
            existing_stmt = existing_stmt.where(RequirementFeatureList.batch_id.is_(None))
        else:
            existing_stmt = existing_stmt.where(RequirementFeatureList.batch_id == normalized_batch_id)
        existing = session.scalar(existing_stmt)
        if existing is not None:
            return existing

    row = RequirementFeatureList(
        project_id=project_id,
        batch_id=normalized_batch_id,
        thread_id=normalized_thread_id,
        idempotency_key=normalized_idempotency_key,
        version=1,
        status=FEATURE_LIST_STATUS_DRAFT,
        decomposable=decomposable,
        undecomposable_reason=undecomposable_reason,
        requirement_text=requirement_text,
        requirement_summary=requirement_summary,
        modules=modules,
        open_questions=open_questions,
        assumptions=assumptions,
        raw_result=raw_result,
    )
    session.add(row)
    session.flush()
    return row


def list_requirement_feature_lists(
    session: Session,
    *,
    project_id: uuid.UUID | None,
    batch_id: str | None,
    status: str | None,
    query: str | None,
    limit: int,
    offset: int,
) -> tuple[list[RequirementFeatureList], int]:
    base_stmt = select(RequirementFeatureList)
    if project_id is not None:
        base_stmt = base_stmt.where(RequirementFeatureList.project_id == project_id)
    if isinstance(batch_id, str) and batch_id.strip():
        base_stmt = base_stmt.where(RequirementFeatureList.batch_id == batch_id.strip())
    if isinstance(status, str) and status.strip():
        base_stmt = base_stmt.where(RequirementFeatureList.status == status.strip())
    if isinstance(query, str) and query.strip():
        pattern = f"%{query.strip()}%"
        base_stmt = base_stmt.where(
            or_(
                RequirementFeatureList.requirement_summary.ilike(pattern),
                RequirementFeatureList.requirement_text.ilike(pattern),
            )
        )
    stmt = (
        base_stmt.order_by(desc(RequirementFeatureList.updated_at), desc(RequirementFeatureList.id))
        .offset(offset)
        .limit(limit)
    )
    count_stmt = select(func.count()).select_from(base_stmt.subquery())
    rows = list(session.scalars(stmt).all())
    total = int(session.scalar(count_stmt) or 0)
    return rows, total


def get_requirement_feature_list(
    session: Session,
    feature_list_id: uuid.UUID,
) -> RequirementFeatureList | None:
    return session.get(RequirementFeatureList, feature_list_id)


def update_requirement_feature_list(
    session: Session,
    row: RequirementFeatureList,
    *,
    batch_id: str | None,
    thread_id: str | None,
    decomposable: bool | None,
    undecomposable_reason: str | None,
    requirement_text: str | None,
    requirement_summary: str | None,
    modules: list[dict] | None,
    open_questions: list[str] | None,
    assumptions: list[str] | None,
    raw_result: dict | None,
) -> RequirementFeatureList:
    if batch_id is not None:
        row.batch_id = batch_id
    if thread_id is not None:
        row.thread_id = thread_id

    updates = {
        "decomposable": decomposable,
        "undecomposable_reason": undecomposable_reason,
        "requirement_text": requirement_text,
        "requirement_summary": requirement_summary,
        "modules": modules,
        "open_questions": open_questions,
        "assumptions": assumptions,
        "raw_result": raw_result,
    }
    content_changed = False
    for field_name in _FEATURE_LIST_CONTENT_FIELDS:
        value = updates.get(field_name)
        if value is None:
            continue
        if getattr(row, field_name) != value:
            setattr(row, field_name, value)
            content_changed = True

    # 内容变更即产生新版本，已确认状态失效，必须重新人工确认
    if content_changed:
        row.version = int(row.version or 1) + 1
        row.status = FEATURE_LIST_STATUS_DRAFT
        row.confirmed_at = None
        row.confirmed_by = None

    session.flush()
    return row


def confirm_requirement_feature_list(
    session: Session,
    row: RequirementFeatureList,
    *,
    confirmed_by: str | None,
) -> RequirementFeatureList:
    if not row.decomposable:
        raise ValueError("feature_list_not_decomposable")
    if row.status == FEATURE_LIST_STATUS_CONFIRMED:
        return row
    row.status = FEATURE_LIST_STATUS_CONFIRMED
    row.confirmed_at = datetime.now(timezone.utc)
    row.confirmed_by = (
        confirmed_by.strip()
        if isinstance(confirmed_by, str) and confirmed_by.strip()
        else None
    )
    session.flush()
    return row


def delete_requirement_feature_list(session: Session, row: RequirementFeatureList) -> None:
    session.delete(row)
    session.flush()


def get_requirement_review_overview(
    session: Session,
    *,
    project_id: uuid.UUID | None,
) -> dict[str, object]:
    documents_stmt = select(func.count()).select_from(RequirementReviewDocument)
    parsed_stmt = select(func.count()).select_from(RequirementReviewDocument).where(
        RequirementReviewDocument.parse_status == "parsed"
    )
    failed_stmt = select(func.count()).select_from(RequirementReviewDocument).where(
        RequirementReviewDocument.parse_status == "failed"
    )
    results_stmt = select(func.count()).select_from(RequirementReviewResult)
    pass_stmt = select(func.count()).select_from(RequirementReviewResult).where(
        RequirementReviewResult.quality_gate == "pass"
    )
    conditional_stmt = select(func.count()).select_from(RequirementReviewResult).where(
        RequirementReviewResult.quality_gate == "conditional"
    )
    fail_stmt = select(func.count()).select_from(RequirementReviewResult).where(
        RequirementReviewResult.quality_gate == "fail"
    )
    latest_document_stmt = select(RequirementReviewDocument).order_by(
        desc(RequirementReviewDocument.updated_at),
        desc(RequirementReviewDocument.id),
    )
    latest_result_stmt = select(RequirementReviewResult).order_by(
        desc(RequirementReviewResult.updated_at),
        desc(RequirementReviewResult.id),
    )

    if project_id is not None:
        documents_stmt = documents_stmt.where(RequirementReviewDocument.project_id == project_id)
        parsed_stmt = parsed_stmt.where(RequirementReviewDocument.project_id == project_id)
        failed_stmt = failed_stmt.where(RequirementReviewDocument.project_id == project_id)
        results_stmt = results_stmt.where(RequirementReviewResult.project_id == project_id)
        pass_stmt = pass_stmt.where(RequirementReviewResult.project_id == project_id)
        conditional_stmt = conditional_stmt.where(RequirementReviewResult.project_id == project_id)
        fail_stmt = fail_stmt.where(RequirementReviewResult.project_id == project_id)
        latest_document_stmt = latest_document_stmt.where(
            RequirementReviewDocument.project_id == project_id
        )
        latest_result_stmt = latest_result_stmt.where(RequirementReviewResult.project_id == project_id)

    latest_document = session.scalar(latest_document_stmt.limit(1))
    latest_result = session.scalar(latest_result_stmt.limit(1))
    latest_batch_id: str | None = None
    latest_activity_at: datetime | None = None
    if latest_document is not None:
        latest_batch_id = latest_document.batch_id
        latest_activity_at = latest_document.updated_at
    if latest_result is not None and (
        latest_activity_at is None or latest_result.updated_at >= latest_activity_at
    ):
        latest_batch_id = latest_result.batch_id
        latest_activity_at = latest_result.updated_at

    return {
        "documents_total": int(session.scalar(documents_stmt) or 0),
        "parsed_documents_total": int(session.scalar(parsed_stmt) or 0),
        "failed_documents_total": int(session.scalar(failed_stmt) or 0),
        "results_total": int(session.scalar(results_stmt) or 0),
        "pass_results_total": int(session.scalar(pass_stmt) or 0),
        "conditional_results_total": int(session.scalar(conditional_stmt) or 0),
        "fail_results_total": int(session.scalar(fail_stmt) or 0),
        "latest_batch_id": latest_batch_id,
        "latest_activity_at": latest_activity_at,
    }


def list_requirement_review_batches(
    session: Session,
    *,
    project_id: uuid.UUID | None,
    limit: int,
    offset: int,
) -> tuple[list[dict[str, object]], int]:
    documents_stmt = (
        select(
            RequirementReviewDocument.batch_id,
            func.count().label("documents_count"),
            func.max(RequirementReviewDocument.updated_at).label("latest_document_at"),
        )
        .where(RequirementReviewDocument.batch_id.is_not(None))
        .group_by(RequirementReviewDocument.batch_id)
    )
    parse_summary_stmt = (
        select(
            RequirementReviewDocument.batch_id,
            RequirementReviewDocument.parse_status,
            func.count().label("status_count"),
        )
        .where(RequirementReviewDocument.batch_id.is_not(None))
        .group_by(RequirementReviewDocument.batch_id, RequirementReviewDocument.parse_status)
    )
    results_stmt = (
        select(
            RequirementReviewResult.batch_id,
            func.count().label("results_count"),
            func.max(RequirementReviewResult.updated_at).label("latest_result_at"),
        )
        .where(RequirementReviewResult.batch_id.is_not(None))
        .group_by(RequirementReviewResult.batch_id)
    )
    gate_summary_stmt = (
        select(
            RequirementReviewResult.batch_id,
            RequirementReviewResult.quality_gate,
            func.count().label("gate_count"),
        )
        .where(RequirementReviewResult.batch_id.is_not(None))
        .group_by(RequirementReviewResult.batch_id, RequirementReviewResult.quality_gate)
    )

    if project_id is not None:
        documents_stmt = documents_stmt.where(RequirementReviewDocument.project_id == project_id)
        parse_summary_stmt = parse_summary_stmt.where(
            RequirementReviewDocument.project_id == project_id
        )
        results_stmt = results_stmt.where(RequirementReviewResult.project_id == project_id)
        gate_summary_stmt = gate_summary_stmt.where(RequirementReviewResult.project_id == project_id)

    batches: dict[str, dict[str, object]] = {}
    for row in session.execute(documents_stmt):
        batch_id = str(row.batch_id or "").strip()
        if not batch_id:
            continue
        batches[batch_id] = {
            "batch_id": batch_id,
            "documents_count": int(row.documents_count or 0),
            "results_count": 0,
            "latest_created_at": row.latest_document_at,
            "parse_status_summary": {},
            "quality_gate_summary": {},
        }

    for row in session.execute(parse_summary_stmt):
        batch_id = str(row.batch_id or "").strip()
        if not batch_id:
            continue
        entry = batches.setdefault(
            batch_id,
            {
                "batch_id": batch_id,
                "documents_count": 0,
                "results_count": 0,
                "latest_created_at": None,
                "parse_status_summary": {},
                "quality_gate_summary": {},
            },
        )
        summary = entry["parse_status_summary"]
        if isinstance(summary, dict):
            summary[str(row.parse_status)] = int(row.status_count or 0)

    for row in session.execute(results_stmt):
        batch_id = str(row.batch_id or "").strip()
        if not batch_id:
            continue
        entry = batches.setdefault(
            batch_id,
            {
                "batch_id": batch_id,
                "documents_count": 0,
                "results_count": 0,
                "latest_created_at": None,
                "parse_status_summary": {},
                "quality_gate_summary": {},
            },
        )
        entry["results_count"] = int(row.results_count or 0)
        latest_created_at = entry.get("latest_created_at")
        latest_result_at = row.latest_result_at
        if latest_result_at is not None and (
            latest_created_at is None or latest_result_at >= latest_created_at
        ):
            entry["latest_created_at"] = latest_result_at

    for row in session.execute(gate_summary_stmt):
        batch_id = str(row.batch_id or "").strip()
        if not batch_id:
            continue
        entry = batches.setdefault(
            batch_id,
            {
                "batch_id": batch_id,
                "documents_count": 0,
                "results_count": 0,
                "latest_created_at": None,
                "parse_status_summary": {},
                "quality_gate_summary": {},
            },
        )
        summary = entry["quality_gate_summary"]
        if isinstance(summary, dict):
            summary[str(row.quality_gate)] = int(row.gate_count or 0)

    ordered = sorted(
        batches.values(),
        key=lambda item: (
            item.get("latest_created_at") is not None,
            item.get("latest_created_at").isoformat()
            if item.get("latest_created_at") is not None
            else "",
            item.get("batch_id") or "",
        ),
        reverse=True,
    )
    total = len(ordered)
    return ordered[offset : offset + limit], total


def get_requirement_review_batch_detail(
    session: Session,
    *,
    project_id: uuid.UUID | None,
    batch_id: str,
    document_limit: int,
    document_offset: int,
    result_limit: int,
    result_offset: int,
) -> dict[str, object] | None:
    normalized_batch_id = batch_id.strip()
    if not normalized_batch_id:
        return None

    documents_base_stmt = select(RequirementReviewDocument).where(
        RequirementReviewDocument.batch_id == normalized_batch_id
    )
    results_base_stmt = select(RequirementReviewResult).where(
        RequirementReviewResult.batch_id == normalized_batch_id
    )
    parse_summary_stmt = (
        select(
            RequirementReviewDocument.parse_status,
            func.count().label("status_count"),
        )
        .where(RequirementReviewDocument.batch_id == normalized_batch_id)
        .group_by(RequirementReviewDocument.parse_status)
    )
    gate_summary_stmt = (
        select(
            RequirementReviewResult.quality_gate,
            func.count().label("gate_count"),
        )
        .where(RequirementReviewResult.batch_id == normalized_batch_id)
        .group_by(RequirementReviewResult.quality_gate)
    )
    latest_document_stmt = select(func.max(RequirementReviewDocument.updated_at)).where(
        RequirementReviewDocument.batch_id == normalized_batch_id
    )
    latest_result_stmt = select(func.max(RequirementReviewResult.updated_at)).where(
        RequirementReviewResult.batch_id == normalized_batch_id
    )

    if project_id is not None:
        documents_base_stmt = documents_base_stmt.where(
            RequirementReviewDocument.project_id == project_id
        )
        results_base_stmt = results_base_stmt.where(RequirementReviewResult.project_id == project_id)
        parse_summary_stmt = parse_summary_stmt.where(
            RequirementReviewDocument.project_id == project_id
        )
        gate_summary_stmt = gate_summary_stmt.where(RequirementReviewResult.project_id == project_id)
        latest_document_stmt = latest_document_stmt.where(
            RequirementReviewDocument.project_id == project_id
        )
        latest_result_stmt = latest_result_stmt.where(RequirementReviewResult.project_id == project_id)

    documents_total = int(
        session.scalar(select(func.count()).select_from(documents_base_stmt.subquery())) or 0
    )
    results_total = int(
        session.scalar(select(func.count()).select_from(results_base_stmt.subquery())) or 0
    )
    if documents_total <= 0 and results_total <= 0:
        return None

    latest_document_at = session.scalar(latest_document_stmt)
    latest_result_at = session.scalar(latest_result_stmt)
    latest_created_at = latest_document_at
    if latest_result_at is not None and (
        latest_created_at is None or latest_result_at >= latest_created_at
    ):
        latest_created_at = latest_result_at

    parse_status_summary = {
        str(row.parse_status): int(row.status_count or 0)
        for row in session.execute(parse_summary_stmt)
    }
    quality_gate_summary = {
        str(row.quality_gate): int(row.gate_count or 0)
        for row in session.execute(gate_summary_stmt)
    }

    document_rows = list(
        session.scalars(
            documents_base_stmt
            .order_by(desc(RequirementReviewDocument.updated_at), desc(RequirementReviewDocument.id))
            .offset(document_offset)
            .limit(document_limit)
        ).all()
    )
    result_rows = list(
        session.scalars(
            results_base_stmt
            .order_by(desc(RequirementReviewResult.updated_at), desc(RequirementReviewResult.id))
            .offset(result_offset)
            .limit(result_limit)
        ).all()
    )

    return {
        "batch": {
            "batch_id": normalized_batch_id,
            "documents_count": documents_total,
            "results_count": results_total,
            "latest_created_at": latest_created_at,
            "parse_status_summary": parse_status_summary,
            "quality_gate_summary": quality_gate_summary,
        },
        "documents": {
            "items": document_rows,
            "total": documents_total,
        },
        "results": {
            "items": result_rows,
            "total": results_total,
        },
    }
