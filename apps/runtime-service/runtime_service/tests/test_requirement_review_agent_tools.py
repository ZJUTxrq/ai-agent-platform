from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from runtime_service.middlewares.multimodal import MULTIMODAL_ATTACHMENTS_KEY
from runtime_service.runtime.context import RuntimeContext
from runtime_service.services.requirement_review_agent import tools as review_tools
from runtime_service.services.requirement_review_agent.document_persistence import (
    DocumentPersistenceOutcome,
)
from runtime_service.services.requirement_review_agent.schemas import (
    RequirementReviewAgentConfig,
)
from runtime_service.services.requirement_review_agent.tools import (
    build_requirement_review_agent_tools,
)

VALID_PROJECT_ID = "5f419550-a3c7-49c6-9450-09154fd1bf7d"


def _build_runtime(
    *,
    project_id: str | None = None,
    thread_id: str = "thread-1",
    state: dict[str, Any] | None = None,
) -> Any:
    return SimpleNamespace(
        config={"configurable": {"thread_id": thread_id}},
        state=state or {},
        context=RuntimeContext(project_id=project_id),
    )


def _tool_payload() -> dict[str, Any]:
    return {
        "requirement_summary": "白银用户优惠券需求包含领取、发放、展示、核销与退款影响。",
        "review_score": 82,
        "quality_gate": "conditional",
        "dimension_scores": {
            "business_objective": 18,
            "scope_boundary": 16,
            "workflow_and_rules": 17,
            "testability": 16,
            "risks_and_dependencies": 15,
        },
        "key_findings": ["主流程较完整"],
        "major_risks": ["退款后券状态未定义"],
        "missing_or_ambiguous_items": ["部分退款是否退券未说明"],
        "suggestions_to_improve": ["补充退款处理规则"],
        "assumptions": ["默认同一订单仅能使用一张券"],
        "generation_policy": "allow_generation_with_assumptions",
        "generation_policy_reason": "主体流程可测，但需要带假设继续。",
    }


def test_persist_requirement_review_result_fails_when_project_id_missing() -> None:
    tool = build_requirement_review_agent_tools(RequirementReviewAgentConfig())[0]

    result = json.loads(
        tool.func(
            runtime=_build_runtime(project_id=None),
            **_tool_payload(),
        )
    )

    assert result["status"] == "failed_missing_project_id"
    assert result["reason"] == "requirement_review_project_id_required"


def test_persist_requirement_review_result_skips_when_remote_not_configured(
    monkeypatch,
) -> None:
    class DummyClient:
        def __init__(self, _config: Any) -> None:
            self.is_configured = False

    monkeypatch.setattr(review_tools, "InteractionDataServiceClient", DummyClient)
    monkeypatch.setattr(
        review_tools,
        "build_interaction_data_service_config",
        lambda config: object(),
    )

    tool = build_requirement_review_agent_tools(RequirementReviewAgentConfig())[0]
    result = json.loads(
        tool.func(
            runtime=_build_runtime(project_id=VALID_PROJECT_ID),
            **_tool_payload(),
        )
    )

    assert result["status"] == "skipped_remote_not_configured"
    assert result["project_id"] == VALID_PROJECT_ID


def test_persist_requirement_review_result_persists_documents_and_review(
    monkeypatch,
) -> None:
    posted_payloads: list[dict[str, Any]] = []

    class DummyClient:
        def __init__(self, _config: Any) -> None:
            self.is_configured = True

        def post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
            posted_payloads.append({"path": path, "payload": payload})
            return {"id": "review-result-1"}

    monkeypatch.setattr(review_tools, "InteractionDataServiceClient", DummyClient)
    monkeypatch.setattr(
        review_tools,
        "build_interaction_data_service_config",
        lambda config: object(),
    )
    monkeypatch.setattr(
        review_tools,
        "persist_requirement_review_documents",
        lambda **_: DocumentPersistenceOutcome(
            status="persisted",
            project_id=VALID_PROJECT_ID,
            batch_id="requirement-review:thread-fixed",
            attachments=[
                {
                    "persist_status": "persisted",
                    "persisted_document_id": "doc-1",
                }
            ],
            persisted_documents=[{"id": "doc-1"}],
            persisted_document_ids=["doc-1"],
        ),
    )
    monkeypatch.setattr(
        review_tools,
        "_resolve_batch_id",
        lambda runtime: "requirement-review:thread-fixed",
    )
    monkeypatch.setattr(
        review_tools,
        "_resolve_runtime_meta",
        lambda runtime: {
            "thread_id": "thread-fixed",
            "run_id": "run-fixed",
            "agent_key": "requirement_review_agent",
        },
    )

    runtime = _build_runtime(
        project_id=VALID_PROJECT_ID,
        state={MULTIMODAL_ATTACHMENTS_KEY: []},
    )
    tool = build_requirement_review_agent_tools(RequirementReviewAgentConfig())[0]
    result = json.loads(
        tool.func(
            runtime=runtime,
            **_tool_payload(),
        )
    )

    assert result["status"] == "persisted"
    assert result["project_id"] == VALID_PROJECT_ID
    assert result["batch_id"] == "requirement-review:thread-fixed"
    assert result["persisted_document_ids"] == ["doc-1"]
    assert result["persisted_result_id"] == "review-result-1"
    assert runtime.state["multimodal_attachments"] == [
        {
            "persist_status": "persisted",
            "persisted_document_id": "doc-1",
        }
    ]

    assert len(posted_payloads) == 1
    posted = posted_payloads[0]
    assert posted["path"] == review_tools.REQUIREMENT_REVIEW_RESULTS_PATH
    assert posted["payload"]["project_id"] == VALID_PROJECT_ID
    assert posted["payload"]["document_ids"] == ["doc-1"]
    assert posted["payload"]["major_risks"] == ["退款后券状态未定义"]


def test_build_requirement_review_agent_tools_exposes_multimodal_reader() -> None:
    tools = build_requirement_review_agent_tools(RequirementReviewAgentConfig())
    assert [tool.name for tool in tools] == [
        "persist_requirement_review_result",
        "read_multimodal_attachments",
    ]
