from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from runtime_service.services.test_case_service_v2.requirement_gate import (
    GATE_ACTION_BLOCK,
    GATE_ACTION_INJECT,
    GATE_ACTION_PASS,
    REQUIREMENT_REVIEW_RESULTS_PATH,
    TestCaseRequirementGateMiddleware,
    decide_requirement_gate,
    fetch_latest_review_result,
)


class _FakeClient:
    def __init__(self, payload: Any = None, error: Exception | None = None) -> None:
        self.payload = payload
        self.error = error
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def get_json(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        self.calls.append((path, dict(params or {})))
        if self.error is not None:
            raise self.error
        return self.payload


def _make_result(**overrides: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "id": "11111111-1111-1111-1111-111111111111",
        "project_id": "00000000-0000-0000-0000-000000000001",
        "requirement_summary": "闪购特惠房需求",
        "review_score": 62.0,
        "quality_gate": "blocked",
        "generation_policy": "block_generation",
        "generation_policy_reason": "支付时限与现有系统约束冲突",
        "missing_or_ambiguous_items": ["未定义并发下单行为"],
        "suggestions_to_improve": ["对齐 15 分钟支付时限"],
        "assumptions": [],
    }
    result.update(overrides)
    return result


def test_fetch_latest_review_result_returns_first_item() -> None:
    client = _FakeClient(payload={"items": [_make_result()], "total": 1})
    result, available = fetch_latest_review_result(
        "00000000-0000-0000-0000-000000000001", client=client
    )
    assert available is True
    assert result is not None
    assert result["generation_policy"] == "block_generation"
    path, params = client.calls[0]
    assert path == REQUIREMENT_REVIEW_RESULTS_PATH
    assert params == {
        "project_id": "00000000-0000-0000-0000-000000000001",
        "limit": 1,
        "offset": 0,
    }


def test_fetch_latest_review_result_empty_items() -> None:
    client = _FakeClient(payload={"items": [], "total": 0})
    result, available = fetch_latest_review_result(
        "00000000-0000-0000-0000-000000000001", client=client
    )
    assert result is None
    assert available is True


def test_fetch_latest_review_result_query_failure_means_unavailable() -> None:
    client = _FakeClient(error=RuntimeError("connection refused"))
    result, available = fetch_latest_review_result(
        "00000000-0000-0000-0000-000000000001", client=client
    )
    assert result is None
    assert available is False


def test_decide_gate_service_unavailable_passes_through() -> None:
    decision = decide_requirement_gate(None, service_available=False)
    assert decision.action == GATE_ACTION_PASS
    assert decision.block_message is None
    assert decision.system_note is None


def test_decide_gate_no_record_injects_warning_note() -> None:
    decision = decide_requirement_gate(None, service_available=True)
    assert decision.action == GATE_ACTION_INJECT
    assert decision.system_note is not None
    assert "未经过需求评审门禁" in decision.system_note


def test_decide_gate_block_policy_blocks_with_reason() -> None:
    decision = decide_requirement_gate(_make_result(), service_available=True)
    assert decision.action == GATE_ACTION_BLOCK
    assert decision.block_message is not None
    assert "blocked" in decision.block_message
    assert "支付时限与现有系统约束冲突" in decision.block_message
    assert "未定义并发下单行为" in decision.block_message


def test_decide_gate_with_assumptions_injects_assumptions() -> None:
    decision = decide_requirement_gate(
        _make_result(
            quality_gate="conditional",
            generation_policy="allow_generation_with_assumptions",
            generation_policy_reason="评分处于条件通过区间",
            assumptions=["假设退款仍走原路退回"],
        ),
        service_available=True,
    )
    assert decision.action == GATE_ACTION_INJECT
    assert decision.system_note is not None
    assert "conditional" in decision.system_note
    assert "假设退款仍走原路退回" in decision.system_note


def _make_request(text: str, *, attachments: list[Any] | None = None) -> Any:
    state: dict[str, Any] = {}
    if attachments is not None:
        state["multimodal_attachments"] = attachments
    return SimpleNamespace(
        messages=[{"role": "user", "content": text}],
        state=state,
    )


def test_is_generation_request_matches_generation_intent_text() -> None:
    request = _make_request("请根据这份需求生成测试用例")
    assert TestCaseRequirementGateMiddleware._is_generation_request(request) is True


def test_is_generation_request_ignores_attachment_without_intent() -> None:
    request = _make_request("帮我总结一下这份文档", attachments=[{"id": "a1"}])
    assert TestCaseRequirementGateMiddleware._is_generation_request(request) is False


def test_is_generation_request_with_attachment_and_intent() -> None:
    request = _make_request("基于附件生成测试用例", attachments=[{"id": "a1"}])
    assert TestCaseRequirementGateMiddleware._is_generation_request(request) is True


def test_decide_gate_allow_policy_injects_pass_note() -> None:
    decision = decide_requirement_gate(
        _make_result(
            review_score=90.0,
            quality_gate="pass",
            generation_policy="allow_generation",
        ),
        service_available=True,
    )
    assert decision.action == GATE_ACTION_INJECT
    assert decision.system_note is not None
    assert "pass" in decision.system_note
    assert "90.0" in decision.system_note
