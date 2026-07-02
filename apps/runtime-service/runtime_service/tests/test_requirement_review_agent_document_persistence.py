from __future__ import annotations

import sys
import base64
from pathlib import Path
from types import SimpleNamespace
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from runtime_service.devtools.multimodal_frontend_compat import (  # noqa: E402
    build_human_message_from_paths,
)
from runtime_service.middlewares.multimodal import (  # noqa: E402
    MULTIMODAL_ATTACHMENTS_KEY,
    MULTIMODAL_SOURCE_BLOCKS_KEY,
)
from runtime_service.middlewares.multimodal import protocol as multimodal_protocol  # noqa: E402
from runtime_service.runtime.context import RuntimeContext  # noqa: E402
from runtime_service.services.requirement_review_agent.document_persistence import (  # noqa: E402
    MISSING_PROJECT_ID_ERROR,
    PERSIST_STATUS_PERSISTED,
    persist_requirement_review_documents,
)
from runtime_service.services.requirement_review_agent.schemas import (  # noqa: E402
    RequirementReviewAgentConfig as ServiceConfig,
)


class _FakeInteractionDataClient:
    def __init__(self) -> None:
        self.multipart_requests: list[dict[str, Any]] = []
        self.json_requests: list[dict[str, Any]] = []
        self.missing_document_ids: set[str] = set()

    @property
    def is_configured(self) -> bool:
        return True

    def post_multipart(
        self,
        path: str,
        *,
        form_data: dict[str, Any],
        file_field_name: str,
        file_name: str,
        file_bytes: bytes,
        content_type: str,
    ) -> dict[str, Any]:
        self.multipart_requests.append(
            {
                "path": path,
                "form_data": dict(form_data),
                "file_field_name": file_field_name,
                "file_name": file_name,
                "file_bytes": file_bytes,
                "content_type": content_type,
            }
        )
        return {
            "storage_path": (
                f"requirement-review/{form_data['project_id']}/"
                f"{form_data['batch_id']}/asset.pdf"
            ),
            "filename": file_name,
            "content_type": content_type,
            "size": len(file_bytes),
            "sha256": "fake-sha256",
        }

    def post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.json_requests.append({"path": path, "payload": dict(payload)})
        return {
            "id": "rr-doc-1",
            "storage_path": payload.get("storage_path"),
            "created_at": "2026-06-17T12:00:00+08:00",
        }

    def get_json(self, path: str) -> dict[str, Any]:
        document_id = path.rsplit("/", 1)[-1]
        if document_id in self.missing_document_ids:
            error = RuntimeError("document_not_found")
            error.response = SimpleNamespace(status_code=404)  # type: ignore[attr-defined]
            raise error
        return {"id": document_id}


def test_persist_requirement_review_documents_persists_parsed_pdf_attachment(
    tmp_path: Path,
) -> None:
    pdf_path = tmp_path / "requirement-review.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF")

    message = build_human_message_from_paths("请评审这个 PRD", [pdf_path])
    normalized_messages = multimodal_protocol.normalize_messages([message])
    attachments = multimodal_protocol.collect_current_turn_attachment_artifacts(
        normalized_messages
    )
    assert len(attachments) == 1

    attachment = dict(attachments[0])
    attachment["status"] = "parsed"
    attachment["summary_for_model"] = "PRD 已解析"
    attachment["parsed_text"] = "这是 PRD 解析后的文本。"

    state = {MULTIMODAL_ATTACHMENTS_KEY: [attachment]}
    runtime = SimpleNamespace(
        state=state,
        config={
            "configurable": {
                "thread_id": "thread-rr-1",
                "batch_id": "requirement-review:batch-1",
            }
        },
        context=RuntimeContext(project_id="5f419550-a3c7-49c6-9450-09154fd1bf7d"),
    )
    client = _FakeInteractionDataClient()

    outcome = persist_requirement_review_documents(
        runtime=runtime,
        state=state,
        service_config=ServiceConfig(),
        client=client,
        messages=normalized_messages,
    )

    assert outcome.status == "persisted"
    assert len(client.multipart_requests) == 1
    assert len(client.json_requests) == 1
    assert client.json_requests[0]["payload"]["storage_path"] == (
        "requirement-review/5f419550-a3c7-49c6-9450-09154fd1bf7d/requirement-review:batch-1/asset.pdf"
    )
    assert (
        client.json_requests[0]["payload"]["provenance"]["asset"]["storage_path"]
        == "requirement-review/5f419550-a3c7-49c6-9450-09154fd1bf7d/requirement-review:batch-1/asset.pdf"
    )
    assert client.json_requests[0]["payload"]["project_id"] == (
        "5f419550-a3c7-49c6-9450-09154fd1bf7d"
    )
    assert client.json_requests[0]["payload"]["filename"] == "requirement-review.pdf"
    assert client.json_requests[0]["payload"]["thread_id"] == "thread-rr-1"
    assert outcome.attachments[0]["persist_status"] == PERSIST_STATUS_PERSISTED
    assert outcome.attachments[0]["persisted_document_id"] == "rr-doc-1"


def test_persist_requirement_review_documents_uploads_asset_from_cached_source_block_when_messages_are_rewritten() -> None:
    pdf_bytes = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"
    pdf_base64 = base64.b64encode(pdf_bytes).decode("ascii")
    source_block = {
        "type": "file",
        "mimeType": "application/pdf",
        "data": pdf_base64,
        "metadata": {"filename": "requirement-review-upload.pdf"},
    }
    source_message = {
        "type": "human",
        "content": [{"type": "text", "text": "评审 PRD"}, source_block],
    }
    normalized_messages = multimodal_protocol.normalize_messages([source_message])
    attachments = multimodal_protocol.collect_current_turn_attachment_artifacts(
        normalized_messages
    )
    attachment = dict(attachments[0])
    attachment.pop("source_payload_base64", None)
    attachment["status"] = "parsed"
    attachment["summary_for_model"] = "PRD 已解析"
    attachment["parsed_text"] = "PDF text"
    fingerprint = attachment["provenance"]["fingerprint"]

    state = {
        MULTIMODAL_ATTACHMENTS_KEY: [attachment],
        MULTIMODAL_SOURCE_BLOCKS_KEY: {fingerprint: normalized_messages[0]["content"][1]},
    }
    runtime = SimpleNamespace(
        state=state,
        config={
            "configurable": {
                "thread_id": "thread-rr-cached",
                "batch_id": "requirement-review:batch-cached",
            }
        },
        context=RuntimeContext(project_id="5f419550-a3c7-49c6-9450-09154fd1bf7d"),
    )
    rewritten_messages = [
        {
            "type": "human",
            "content": [
                {"type": "text", "text": "评审 PRD"},
                {"type": "text", "text": "PDF 已解析"},
            ],
        }
    ]
    client = _FakeInteractionDataClient()

    outcome = persist_requirement_review_documents(
        runtime=runtime,
        state=state,
        service_config=ServiceConfig(),
        client=client,
        messages=rewritten_messages,
    )

    assert outcome.status == "persisted"
    assert len(client.multipart_requests) == 1
    assert client.multipart_requests[0]["file_bytes"] == pdf_bytes
    assert client.multipart_requests[0]["file_name"] == "requirement-review-upload.pdf"


def test_persist_requirement_review_documents_recreates_deleted_persisted_document() -> None:
    pdf_bytes = b"%PDF-1.4\n%%EOF"
    pdf_base64 = base64.b64encode(pdf_bytes).decode("ascii")
    source_message = {
        "type": "human",
        "content": [
            {"type": "text", "text": "review PRD"},
            {
                "type": "file",
                "mimeType": "application/pdf",
                "data": pdf_base64,
                "metadata": {"filename": "deleted-document.pdf"},
            },
        ],
    }
    normalized_messages = multimodal_protocol.normalize_messages([source_message])
    attachment = dict(
        multimodal_protocol.collect_current_turn_attachment_artifacts(
            normalized_messages
        )[0]
    )
    attachment.update(
        {
            "status": "parsed",
            "summary_for_model": "parsed PRD",
            "parsed_text": "PDF text",
            "persist_status": PERSIST_STATUS_PERSISTED,
            "persisted_document_id": "deleted-document-id",
        }
    )
    state = {MULTIMODAL_ATTACHMENTS_KEY: [attachment]}
    runtime = SimpleNamespace(
        state=state,
        config={
            "configurable": {
                "thread_id": "thread-rr-deleted",
                "batch_id": "requirement-review:batch-deleted",
            }
        },
        context=RuntimeContext(project_id="5f419550-a3c7-49c6-9450-09154fd1bf7d"),
    )
    client = _FakeInteractionDataClient()
    client.missing_document_ids.add("deleted-document-id")

    outcome = persist_requirement_review_documents(
        runtime=runtime,
        state=state,
        service_config=ServiceConfig(),
        client=client,
        messages=normalized_messages,
    )

    assert outcome.status == "persisted"
    assert len(client.multipart_requests) == 1
    assert len(client.json_requests) == 1
    assert outcome.attachments[0]["persisted_document_id"] == "rr-doc-1"


def test_persist_requirement_review_documents_requires_project_id(
    tmp_path: Path,
) -> None:
    pdf_path = tmp_path / "requirement-review.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%%EOF")

    message = build_human_message_from_paths("请评审这个 PRD", [pdf_path])
    normalized_messages = multimodal_protocol.normalize_messages([message])
    attachments = multimodal_protocol.collect_current_turn_attachment_artifacts(
        normalized_messages
    )
    attachment = dict(attachments[0])
    attachment["status"] = "parsed"
    attachment["summary_for_model"] = "PRD 已解析"
    attachment["parsed_text"] = "这是 PRD 解析后的文本。"
    state = {MULTIMODAL_ATTACHMENTS_KEY: [attachment]}
    runtime = SimpleNamespace(
        state=state,
        config={"configurable": {"thread_id": "thread-rr-2"}},
        context=RuntimeContext(),
    )
    client = _FakeInteractionDataClient()

    try:
        persist_requirement_review_documents(
            runtime=runtime,
            state=state,
            service_config=ServiceConfig(),
            client=client,
            messages=normalized_messages,
        )
    except ValueError as exc:
        assert str(exc) == MISSING_PROJECT_ID_ERROR
    else:
        raise AssertionError(
            "persist_requirement_review_documents should require project_id"
        )
