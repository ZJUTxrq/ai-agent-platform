from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from runtime_service.middlewares.multimodal import MULTIMODAL_ATTACHMENTS_KEY  # noqa: E402
from runtime_service.runtime.context import RuntimeContext  # noqa: E402
from runtime_service.services.requirement_review_agent.document_persistence import (  # noqa: E402
    DocumentPersistenceOutcome,
)
from runtime_service.services.requirement_review_agent.middleware import (  # noqa: E402
    RequirementReviewDocumentPersistenceMiddleware,
)
from runtime_service.services.requirement_review_agent.schemas import (  # noqa: E402
    RequirementReviewAgentConfig,
)


class _DummyRequest:
    def __init__(
        self,
        *,
        state: dict[str, Any],
        messages: list[Any] | None = None,
        runtime: Any | None = None,
    ) -> None:
        self.state = state
        self.messages = messages or []
        self.runtime = runtime or SimpleNamespace(
            context=RuntimeContext(project_id="5f419550-a3c7-49c6-9450-09154fd1bf7d"),
            config={},
        )

    def override(self, **kwargs: Any) -> "_DummyRequest":
        return _DummyRequest(
            state=kwargs.get("state", self.state),
            messages=kwargs.get("messages", self.messages),
            runtime=kwargs.get("runtime", self.runtime),
        )


def test_requirement_review_document_persistence_middleware_updates_state(
    monkeypatch,
) -> None:
    middleware = RequirementReviewDocumentPersistenceMiddleware(
        RequirementReviewAgentConfig()
    )
    observed_states: list[dict[str, Any]] = []

    monkeypatch.setattr(
        "runtime_service.services.requirement_review_agent.middleware.persist_requirement_review_documents",
        lambda **_: DocumentPersistenceOutcome(
            status="persisted",
            project_id="5f419550-a3c7-49c6-9450-09154fd1bf7d",
            batch_id="requirement-review:batch-1",
            attachments=[
                {
                    "attachment_id": "att-1",
                    "persist_status": "persisted",
                    "persisted_document_id": "rr-doc-1",
                }
            ],
            persisted_documents=[{"id": "rr-doc-1"}],
            persisted_document_ids=["rr-doc-1"],
        ),
    )

    request = _DummyRequest(
        state={
            MULTIMODAL_ATTACHMENTS_KEY: [
                {
                    "attachment_id": "att-1",
                    "kind": "doc",
                    "status": "parsed",
                    "summary_for_model": "ok",
                    "provenance": {"fingerprint": "fp-1"},
                }
            ]
        },
        messages=[{"type": "human", "content": "请评审"}],
    )

    def handler(next_request: _DummyRequest) -> str:
        observed_states.append(next_request.state)
        return "ok"

    response = middleware.wrap_model_call(request, handler)

    assert observed_states == [
        {
            MULTIMODAL_ATTACHMENTS_KEY: [
                {
                    "attachment_id": "att-1",
                    "persist_status": "persisted",
                    "persisted_document_id": "rr-doc-1",
                }
            ]
        }
    ]
    assert response.model_response == "ok"
    assert response.command.update == {
        MULTIMODAL_ATTACHMENTS_KEY: [
            {
                "attachment_id": "att-1",
                "persist_status": "persisted",
                "persisted_document_id": "rr-doc-1",
            }
        ]
    }
