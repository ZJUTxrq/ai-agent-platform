from __future__ import annotations

import base64
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from runtime_service.middlewares.multimodal import (
    MULTIMODAL_ATTACHMENTS_KEY,
    MULTIMODAL_SOURCE_BLOCKS_KEY,
)
from runtime_service.middlewares.multimodal import protocol as multimodal_protocol
from runtime_service.runtime.context import RuntimeContext
from runtime_service.services.test_case_service_v2.document_persistence import (
    PERSIST_STATUS_PERSISTED,
    persist_runtime_documents,
)
from runtime_service.services.test_case_service_v2.schemas import (
    TestCaseServiceConfig as ServiceConfig,
)


class _FakeInteractionDataClient:
    def __init__(self) -> None:
        self.multipart_requests: list[dict[str, Any]] = []
        self.json_requests: list[dict[str, Any]] = []

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
                f"test-case-service/{form_data['project_id']}/"
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
            "id": "doc-v2-1",
            "storage_path": payload.get("storage_path"),
            "created_at": "2026-06-05T07:56:00+08:00",
        }


def test_persist_runtime_documents_uploads_asset_from_cached_source_block_when_messages_are_rewritten() -> None:
    pdf_bytes = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"
    pdf_base64 = base64.b64encode(pdf_bytes).decode("ascii")
    source_block = {
        "type": "file",
        "mimeType": "application/pdf",
        "data": pdf_base64,
        "metadata": {"filename": "runtime-web-upload.pdf"},
    }
    source_message = {
        "type": "human",
        "content": [{"type": "text", "text": "分析 PDF"}, source_block],
    }
    normalized_messages = multimodal_protocol.normalize_messages([source_message])
    attachments = multimodal_protocol.collect_current_turn_attachment_artifacts(
        normalized_messages
    )
    attachment = dict(attachments[0])
    attachment.pop("source_payload_base64", None)
    attachment["status"] = "parsed"
    attachment["summary_for_model"] = "PDF 已解析"
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
                "thread_id": "thread-v2",
                "batch_id": "test-case-service:batch-v2",
            }
        },
        context=RuntimeContext(project_id="5f419550-a3c7-49c6-9450-09154fd1bf7d"),
    )
    rewritten_messages = [
        {
            "type": "human",
            "content": [
                {"type": "text", "text": "分析 PDF"},
                {"type": "text", "text": "PDF 已解析"},
            ],
        }
    ]
    client = _FakeInteractionDataClient()

    outcome = persist_runtime_documents(
        runtime=runtime,
        state=state,
        service_config=ServiceConfig(),
        client=client,
        messages=rewritten_messages,
    )

    assert outcome.status == "persisted"
    assert len(client.multipart_requests) == 1
    assert client.multipart_requests[0]["file_bytes"] == pdf_bytes
    assert client.multipart_requests[0]["file_name"] == "runtime-web-upload.pdf"
    assert outcome.attachments[0]["persist_status"] == PERSIST_STATUS_PERSISTED
    assert outcome.attachments[0].get("persist_error") is None
